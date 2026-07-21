"""R03 semantic ownership 的真实 Host public-run smoke。

本脚本通过 ``ConfigLoader -> ToolsDiscovery -> ScenePrepare/Service assembly ->
open_host -> ensure_session -> submit_followup`` 运行真实 Doc、Web 与 Fins 工具。
运行结束后只用 Host owner 的 durable projection API 做 internal diagnostic read，
验证 request atom、Memory、Compact、RunInput projection 与 LLM-ready Tool Trace
的一致性。internal read 不是 public product API，也不参与工具结果 accept/resume。

脚本不会输出 provider secret、headers、完整 prompt、完整结果 payload、opaque
refs 或本地 credential；stdout 只包含有界计数与 PASS/FAIL 摘要。
"""

# ruff: noqa: E402 -- 直接运行 utils 脚本时先把项目根加入 sys.path。

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Final, cast
from uuid import uuid4

_PROJECT_ROOT: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dayu.contracts.json_value import JsonValue
from dayu.host import (
    AuthorizationClaim,
    EnsureSessionRequest,
    FollowupBehavior,
    Host,
    HostCallContext,
    HostEvent,
    HostEventKind,
    HostSessionEvent,
    OpenHostOptions,
    OperationContext,
    open_host,
)
from dayu.host.accepted_result_projection import (
    AcceptedToolResultProjection,
    AcceptedToolResultSourceState,
    project_accepted_tool_result,
)
from dayu.host.compact_material import (
    build_compact_material_pack,
    build_pre_dispatch_compact_material_view,
    conversation_compact_input_vnext_from_material_pack,
    select_compact_segment,
)
from dayu.host.compaction import CompactSegmentTrigger
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.event_log import EventClass, EventLogRow, EventLogStore
from dayu.host.durable.memory import read_latest_memory_snapshot
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.state import RunRow, read_run_by_id
from dayu.host.durable.tool_trace import (
    read_runner_call_reconstruction_signals_by_run,
    read_tool_trace_hot_row,
    resolve_runner_call_projection_from_signal,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    digest_memory_projection_policy,
)
from dayu.host.memory_repair import catch_up_conversation_memory_projection
from dayu.host.open_host import _tool_trace_sink_options_from_open_host_options
from dayu.host.payload_resolution import (
    ToolCallRequestAtoms,
    event_payload_object,
    tool_call_request_atoms,
)
from dayu.host.tool_trace import catch_up_tool_trace_projection
from dayu.runtime.config_loader import (
    ConfigLoader,
    RuntimeConfig,
    ToolDiscoveryProviderConfig,
)
from dayu.runtime.location import resolve_runtime_locations
from dayu.runtime.scene_prepare import (
    PreparedSceneInputs,
    ScenePrepareRequest,
    SceneToolCatalog,
    prepare_scene,
)
from dayu.service.host_assembly import (
    ServiceAssemblyOverrides,
    ServiceDiscoveredTools,
    ServiceOpenHostAssemblyDiagnostics,
    ServiceOpenHostAssemblyRequest,
    assemble_effective_tool_provider_configs,
    compose_open_host_options,
    compose_submit_followup_request,
    discover_service_tools,
)
from dayu.service.scene_context import CURRENT_TIME_SLOT, current_time

_PACKAGE_CONFIG_ROOT: Final[pathlib.Path] = _PROJECT_ROOT / "dayu" / "config"
_DEFAULT_SCENE_ID: Final[str] = "interactive"
_DEFAULT_ACTOR: Final[str] = "r03-semantic-ownership-smoke"
_SESSION_SLOT_PREFIX: Final[str] = "r03-semantic-ownership"
_TERMINAL_WAIT_SECONDS: Final[float] = 1_200.0
_EVENT_READ_LIMIT: Final[int] = 20_000
_PROJECTION_READ_LIMIT: Final[int] = 256
_FAILURE_SUMMARY_MAX_CHARS: Final[int] = 240
_EVENT_TYPE_TOOL_CALL_REQUESTED: Final[str] = "TOOL_CALL_REQUESTED"
_EVENT_TYPE_TOOL_AWAITING: Final[str] = "TOOL_AWAITING"
_EVENT_TYPE_TOOL_RESULT_ACCEPTED: Final[str] = "TOOL_RESULT_ACCEPTED"
_FINS_LIST_TOOL_NAME: Final[str] = "list_documents"
_FINS_READ_TOOL_NAME: Final[str] = "get_document_sections"
_FINAL_OBSERVATION_PROMPT: Final[str] = (
    "请只根据本次会话中已经接受的工具证据，用一句话确认证据仍可用于回答；"
    "本轮不要调用任何工具。"
)
_OPAQUE_SENTINELS: Final[tuple[str, ...]] = (
    "fliing-typo",
    "opaque-should-never-reach-llm",
    "eventlog",
    "event-internal-only",
    "eventlogg",
    "event-typo-should-never-reach-llm",
)
_SECRET_MARKERS: Final[tuple[str, ...]] = (
    "api_key",
    "apikey",
    "authorization",
    "bearer ",
    "token",
    "secret",
    "cookie",
)


class FinsAwaitingTool(StrEnum):
    """smoke 允许的真实 Fins awaiting 工具。"""

    PREPROCESS = "start_fins_preprocess"
    DOWNLOAD = "start_fins_download"
    UPLOAD = "start_fins_upload"


@dataclass(frozen=True, slots=True)
class SmokeArgs:
    """R03 smoke 命令行参数。

    :param workspace_root: Host runtime workspace 根目录。
    :param scene_id: ScenePrepare scene id。
    :param doc_file: Doc 工具读取的调用方文件。
    :param web_query: Web 搜索文本。
    :param fins_ticker: Fins 股票代码。
    :param fins_document_id: Fins 文档 id。
    :param fins_awaiting_tool: 真实 Fins awaiting 工具。
    :param keep_workspace: 调用方是否显式要求保留 workspace；脚本始终不删除。
    """

    workspace_root: pathlib.Path
    scene_id: str
    doc_file: pathlib.Path
    web_query: str
    fins_ticker: str
    fins_document_id: str
    fins_awaiting_tool: FinsAwaitingTool
    keep_workspace: bool


@dataclass(frozen=True, slots=True)
class RuntimeAssemblyResult:
    """真实 runtime assembly 结果。

    :param options: public ``open_host`` options。
    :param scene_inputs: ScenePrepare 输出。
    :param diagnostics: Service assembly 诊断。
    :param discovered_tools: ToolsDiscovery 结果。
    """

    options: OpenHostOptions
    scene_inputs: PreparedSceneInputs
    diagnostics: ServiceOpenHostAssemblyDiagnostics
    discovered_tools: ServiceDiscoveredTools


@dataclass(frozen=True, slots=True)
class ExpectedToolCall:
    """smoke required tool call 的 typed exact arguments。

    :param tool_name: required tool 名称。
    :param arguments: LLM tool call 必须精确提交的参数 object。
    """

    tool_name: str
    arguments: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class AwaitingRequestIdentity:
    """TOOL_AWAITING 必须链接的 canonical request identity。

    :param event_id: ``TOOL_CALL_REQUESTED`` event id。
    :param event_sequence: canonical request event sequence。
    :param tool_call_id: Host accepted tool call id。
    :param tool_name: selected Fins awaiting tool 名称。
    """

    event_id: str
    event_sequence: int
    tool_call_id: str
    tool_name: str


@dataclass(frozen=True, slots=True)
class SmokeRound:
    """单轮 public Host 结果。

    :param label: 轮次标签。
    :param run_id: public Host Run id。
    :param event: terminal event。
    """

    label: str
    run_id: str
    event: HostEvent


@dataclass(frozen=True, slots=True)
class InternalProjectionObservation:
    """internal diagnostic projection 一致性摘要。

    :param request_tool_names: strict resolver 读出的工具名。
    :param accepted_result_count: canonical accepted result 数。
    :param available_citation_count: explicit citation 数。
    :param available_citation_tool_names: 产生 explicit citation 的工具名。
    :param run_input_text: 最终真实 runner-call LLM message content 汇总。
    :param memory_text: Conversation Memory selected evidence 汇总。
    :param compact_source_notes: compactor evidence source notes。
    :param trace_source_texts: LLM-ready Tool Trace business source texts。
    :param projection_source_texts: shared projection source texts。
    """

    request_tool_names: tuple[str, ...]
    accepted_result_count: int
    available_citation_count: int
    available_citation_tool_names: tuple[str, ...]
    run_input_text: str
    memory_text: str
    compact_source_notes: tuple[str, ...]
    trace_source_texts: tuple[str, ...]
    projection_source_texts: tuple[str, ...]


def parse_args(argv: Sequence[str]) -> SmokeArgs:
    """解析 R03 smoke CLI。

    :param argv: 不含程序名的参数。
    :returns: typed smoke 参数。
    :raises SystemExit: argparse 校验失败时抛出。
    """

    parser = argparse.ArgumentParser(
        description="Run the real R03 Host public semantic-ownership smoke."
    )
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--scene-id", default=_DEFAULT_SCENE_ID)
    parser.add_argument("--doc-file", required=True)
    parser.add_argument("--web-query", required=True)
    parser.add_argument("--fins-ticker", required=True)
    parser.add_argument("--fins-document-id", required=True)
    parser.add_argument(
        "--fins-awaiting-tool",
        choices=tuple(tool.value for tool in FinsAwaitingTool),
        default=FinsAwaitingTool.PREPROCESS.value,
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help=(
            "Mark that the caller explicitly requested retention; this smoke never "
            "deletes Host/runtime artifacts."
        ),
    )
    namespace = parser.parse_args(list(argv))
    workspace_root = pathlib.Path(cast(str, namespace.workspace_root)).expanduser()
    doc_file = pathlib.Path(cast(str, namespace.doc_file)).expanduser()
    return SmokeArgs(
        workspace_root=workspace_root.resolve(strict=False),
        scene_id=_required_cli_text(cast(str, namespace.scene_id), "scene_id"),
        doc_file=doc_file.resolve(strict=False),
        web_query=_required_cli_text(cast(str, namespace.web_query), "web_query"),
        fins_ticker=_required_cli_text(
            cast(str, namespace.fins_ticker), "fins_ticker"
        ),
        fins_document_id=_required_cli_text(
            cast(str, namespace.fins_document_id), "fins_document_id"
        ),
        fins_awaiting_tool=FinsAwaitingTool(
            cast(str, namespace.fins_awaiting_tool)
        ),
        keep_workspace=cast(bool, namespace.keep_workspace),
    )


def prepare_runtime_assembly(
    args: SmokeArgs,
    *,
    env: Mapping[str, str],
) -> RuntimeAssemblyResult:
    """装配真实 Config/Tools/Scene/Service public Host options。

    :param args: typed smoke 参数。
    :param env: provider credential 环境变量，只交给 Service assembly。
    :returns: runtime assembly 结果。
    :raises FileNotFoundError: Doc 输入不存在或不是普通文件时抛出。
    :raises ValueError: config、tool discovery、scene 或 provider 装配失败时抛出。
    """

    _validate_doc_file(args.doc_file)
    locations = resolve_runtime_locations(
        workspace_root=args.workspace_root,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    provider_configs = _r03_provider_configs(config, args.doc_file)
    effective_configs = assemble_effective_tool_provider_configs(
        provider_configs,
        workspace_root=args.workspace_root,
    )
    discovered = discover_service_tools(effective_configs)
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=args.scene_id,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                CURRENT_TIME_SLOT: current_time(),
                "fins_default_subject": args.fins_ticker,
            },
            available_tools=SceneToolCatalog.from_tool_bundle(
                discovered.tool_bundle
            ),
        )
    )
    assembly = compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=args.workspace_root,
            config=config,
            locations=locations,
            scene_inputs=scene_inputs,
            discovered_tools=discovered,
            overrides=ServiceAssemblyOverrides(),
            env=env,
        )
    )
    return RuntimeAssemblyResult(
        options=assembly.options,
        scene_inputs=scene_inputs,
        diagnostics=assembly.diagnostics,
        discovered_tools=discovered,
    )


async def run_smoke(args: SmokeArgs, *, env: Mapping[str, str]) -> int:
    """执行真实 public runs 与 internal diagnostic projection assertions。

    :param args: typed smoke 参数。
    :param env: provider credential 环境变量。
    :returns: 成功返回 ``0``。
    :raises RuntimeError: public run 或 projection closure 不成立时抛出。
    :raises Exception: runtime/provider/storage 失败时透出。
    """

    assembly = prepare_runtime_assembly(args, env=env)
    batch_id = uuid4().hex[:12]
    print("R03 SMOKE START real public Host semantic ownership")
    print(
        "R03 SMOKE ASSEMBLY "
        f"providers={len(assembly.discovered_tools.provider_reports)} "
        "selected_tools="
        f"{len(assembly.scene_inputs.tool_selection.tool_names or frozenset())} "
        f"wait_poller={assembly.options.wait_poller_policy is not None}"
    )
    rounds: list[SmokeRound] = []
    session_id = ""
    async with open_host(assembly.options) as host:
        session = await host.ensure_session(
            EnsureSessionRequest(
                scope="workspace",
                slot_key=f"{_SESSION_SLOT_PREFIX}-{batch_id}",
                metadata=(),
            )
        )
        session_id = session.session_id
        watcher = host.watch_session_events(session.session_id)
        round_specs = _round_specs(args)
        for ordinal, (label, prompt, tool_names) in enumerate(round_specs, start=1):
            round_result = await _run_round(
                host=host,
                watcher=watcher,
                session_id=session.session_id,
                label=label,
                client_request_id=f"r03-{batch_id}-{ordinal}",
                scene_inputs=assembly.scene_inputs,
                prompt=prompt,
                tool_names=tool_names,
            )
            rounds.append(round_result)
            print(f"R03 SMOKE ROUND_PASS label={label}")

    if session_id == "" or len(rounds) == 0:
        raise RuntimeError("public Host smoke produced no completed rounds")
    observation = _read_internal_projection_observation(
        args=args,
        options=assembly.options,
        session_id=session_id,
        final_run_id=rounds[-1].run_id,
    )
    _assert_projection_closure(args, observation)
    print(
        "R03 SMOKE PROJECTION_PASS "
        f"requests={len(observation.request_tool_names)} "
        f"accepted_results={observation.accepted_result_count} "
        f"explicit_citations={observation.available_citation_count}"
    )
    print("R03 SMOKE PASS real Doc/Web/Fins public execution closure")
    print(_workspace_retention_summary(args.keep_workspace))
    return 0


def _r03_provider_configs(
    config: RuntimeConfig,
    doc_file: pathlib.Path,
) -> tuple[ToolDiscoveryProviderConfig, ...]:
    """启用真实 Doc provider 并保留其它 configured providers。

    :param config: ConfigLoader runtime config。
    :param doc_file: Doc smoke 输入文件。
    :returns: typed provider configs。
    :raises ValueError: package config 缺 ``doc-tools`` provider 时抛出。
    """

    configs: list[ToolDiscoveryProviderConfig] = []
    doc_found = False
    for provider in config.tool_discovery.providers.values():
        if provider.provider_id != "doc-tools":
            configs.append(provider)
            continue
        doc_found = True
        doc_config: dict[str, JsonValue] = dict(provider.config)
        doc_config["allowed_paths"] = [str(doc_file.parent)]
        configs.append(replace(provider, enabled=True, config=doc_config))
    if not doc_found:
        raise ValueError("configured doc-tools provider is missing")
    return tuple(configs)


def _round_specs(
    args: SmokeArgs,
) -> tuple[tuple[str, str, frozenset[str]], ...]:
    """构造五个真实工具轮次与最终 no-tool observation 轮。

    :param args: typed smoke 参数。
    :returns: ``(label, prompt, selected tool names)`` 元组。
    :raises ValueError: awaiting 工具不受支持时抛出。
    """

    doc_prompt = _exact_tool_prompt(
        tool_name="read_file",
        arguments=_expected_read_file_arguments(args),
        completion_instruction="读取完成后用一句话结束。",
    )
    web_prompt = _exact_tool_prompt(
        tool_name="search_web",
        arguments=_expected_search_web_arguments(args),
        completion_instruction="搜索完成后用一句话结束。",
    )
    awaiting_prompt = _fins_awaiting_prompt(args)
    fins_list_prompt = _exact_tool_prompt(
        tool_name=_FINS_LIST_TOOL_NAME,
        arguments=_expected_fins_list_arguments(args),
        completion_instruction=(
            "检查结果 documents[].document_id 是否包含调用方随后提供的 "
            f"{args.fins_document_id}；不得猜测或改写 document_id。"
        ),
    )
    fins_read_prompt = _grounded_fins_read_prompt(args)
    return (
        ("doc", doc_prompt, frozenset({"read_file"})),
        ("web", web_prompt, frozenset({"search_web"})),
        (
            "fins-awaiting",
            awaiting_prompt,
            frozenset({args.fins_awaiting_tool.value}),
        ),
        ("fins-list", fins_list_prompt, frozenset({_FINS_LIST_TOOL_NAME})),
        ("fins-read", fins_read_prompt, frozenset({_FINS_READ_TOOL_NAME})),
        ("observation", _FINAL_OBSERVATION_PROMPT, frozenset()),
    )


def _grounded_fins_read_prompt(args: SmokeArgs) -> str:
    """构造以同 ticker list_documents 结果为前置条件的 citation read prompt。

    :param args: typed smoke 参数。
    :returns: 自足的条件式单工具调用 prompt。
    :raises Exception: 不主动抛出异常。
    """

    exact_call = _exact_tool_prompt(
        tool_name=_FINS_READ_TOOL_NAME,
        arguments=_expected_fins_read_arguments(args),
        completion_instruction="读取章节结构后用一句话结束。",
    )
    return (
        "上一轮 list_documents 已用于验证调用方提供的 document_id。"
        f"只有当上一轮同 ticker {args.fins_ticker} 的 documents[].document_id "
        f"确实包含 {args.fins_document_id} 时，才执行以下调用：{exact_call}"
        "如果该 ID 没有出现，本轮必须停止且不得调用工具，只说明验证失败；"
        "禁止猜测、改写或使用其它 ticker 的 document_id。"
    )


def _fins_awaiting_prompt(args: SmokeArgs) -> str:
    """构造真实 Fins awaiting 工具的显式参数 prompt。

    :param args: typed smoke 参数。
    :returns: 自足的单工具调用 prompt。
    :raises ValueError: awaiting 工具不受支持时抛出。
    """

    return _exact_tool_prompt(
        tool_name=args.fins_awaiting_tool.value,
        arguments=_expected_fins_awaiting_arguments(args),
        completion_instruction=(
            "等待 production poller 完成并恢复后，用一句话结束。"
        ),
    )


def _expected_required_tool_calls(
    args: SmokeArgs,
) -> tuple[ExpectedToolCall, ...]:
    """从 typed smoke 参数构造五个 required exact tool calls。

    :param args: typed smoke 参数。
    :returns: Doc、Web、selected awaiting、Fins grounding/read 的 exact calls。
    :raises ValueError: selected awaiting tool 不受支持时抛出。
    """

    return (
        ExpectedToolCall(
            tool_name="read_file",
            arguments=_expected_read_file_arguments(args),
        ),
        ExpectedToolCall(
            tool_name="search_web",
            arguments=_expected_search_web_arguments(args),
        ),
        ExpectedToolCall(
            tool_name=args.fins_awaiting_tool.value,
            arguments=_expected_fins_awaiting_arguments(args),
        ),
        ExpectedToolCall(
            tool_name=_FINS_LIST_TOOL_NAME,
            arguments=_expected_fins_list_arguments(args),
        ),
        ExpectedToolCall(
            tool_name=_FINS_READ_TOOL_NAME,
            arguments=_expected_fins_read_arguments(args),
        ),
    )


def _expected_read_file_arguments(args: SmokeArgs) -> Mapping[str, JsonValue]:
    """构造 real Doc round 的 exact arguments。

    :param args: typed smoke 参数。
    :returns: 只含调用方绝对文件路径的参数 object。
    :raises Exception: 不主动抛出异常。
    """

    return {"file_path": str(args.doc_file)}


def _expected_search_web_arguments(args: SmokeArgs) -> Mapping[str, JsonValue]:
    """构造 real Web round 的 exact arguments。

    :param args: typed smoke 参数。
    :returns: 只含调用方 query 的参数 object。
    :raises Exception: 不主动抛出异常。
    """

    return {"query": args.web_query}


def _expected_fins_list_arguments(args: SmokeArgs) -> Mapping[str, JsonValue]:
    """构造 Fins document-id grounding round 的 exact arguments。

    :param args: typed smoke 参数。
    :returns: ``list_documents`` 的 ticker 参数 object。
    :raises Exception: 不主动抛出异常。
    """

    return {"ticker": args.fins_ticker}


def _expected_fins_read_arguments(args: SmokeArgs) -> Mapping[str, JsonValue]:
    """构造 Fins citation read round 的 exact arguments。

    :param args: typed smoke 参数。
    :returns: ``get_document_sections`` 的 ticker/document_id 参数 object。
    :raises Exception: 不主动抛出异常。
    """

    return {
        "ticker": args.fins_ticker,
        "document_id": args.fins_document_id,
    }


def _expected_fins_awaiting_arguments(
    args: SmokeArgs,
) -> Mapping[str, JsonValue]:
    """构造 selected Fins awaiting tool 的 exact arguments。

    :param args: typed smoke 参数。
    :returns: 与当前 selected awaiting schema/prompt 同源的参数 object。
    :raises ValueError: selected awaiting tool 不受支持时抛出。
    """

    if args.fins_awaiting_tool is FinsAwaitingTool.PREPROCESS:
        return {
            "ticker": args.fins_ticker,
            "document_ids": [args.fins_document_id],
            "rebuild_processed": False,
        }
    if args.fins_awaiting_tool is FinsAwaitingTool.DOWNLOAD:
        return {
            "ticker": args.fins_ticker,
            "source": "auto",
            "overwrite_existing": False,
            "rebuild_processed": False,
        }
    if args.fins_awaiting_tool is FinsAwaitingTool.UPLOAD:
        return {
            "ticker": args.fins_ticker,
            "upload_kind": "material",
            "action": "auto",
            "files": [str(args.doc_file)],
            "form_type": "R03_SMOKE",
            "material_name": "R03 semantic ownership smoke",
            "document_id": args.fins_document_id,
        }
    raise ValueError(f"unsupported Fins awaiting tool: {args.fins_awaiting_tool}")


def _exact_tool_prompt(
    *,
    tool_name: str,
    arguments: Mapping[str, JsonValue],
    completion_instruction: str,
) -> str:
    """构造自足的单工具 exact-arguments smoke prompt。

    :param tool_name: 本轮唯一允许调用的工具名。
    :param arguments: 必须原样提交的完整参数 object。
    :param completion_instruction: 工具完成后的最小动作。
    :returns: 不允许增加、省略或改写参数字段的 prompt。
    :raises ValueError: canonical JSON 编码失败时抛出。
    """

    return (
        f"只调用 {tool_name} 一次。参数 JSON 必须精确等于 "
        f"{canonical_json_dumps(dict(arguments))}，不得增加、省略或改写任何字段。"
        f"{completion_instruction}"
    )


async def _run_round(
    *,
    host: Host,
    watcher: AsyncIterator[HostSessionEvent],
    session_id: str,
    label: str,
    client_request_id: str,
    scene_inputs: PreparedSceneInputs,
    prompt: str,
    tool_names: frozenset[str],
) -> SmokeRound:
    """提交一轮 public follow-up 并等待 terminal。

    :param host: public Host handle。
    :param watcher: durable/transient 联合 session event iterator。
    :param session_id: public Session id。
    :param label: 轮次标签。
    :param client_request_id: 调用方幂等 id。
    :param scene_inputs: ScenePrepare 输出。
    :param prompt: 当前用户 prompt。
    :param tool_names: 当前轮 exact 工具集合。
    :returns: succeeded round。
    :raises RuntimeError: terminal 非 succeeded 或 final answer 为空时抛出。
    """

    accepted = await host.submit_followup(
        session_id,
        compose_submit_followup_request(
            context=_host_context(client_request_id),
            session_id=session_id,
            client_request_id=client_request_id,
            scene_inputs=scene_inputs,
            user_prompt=prompt,
            tool_names=tool_names,
            behavior=FollowupBehavior.QUEUE,
            target_run_id=None,
        ),
    )
    terminal = await _next_terminal(watcher, accepted.accepted_run_id)
    if terminal.kind is not HostEventKind.SUCCEEDED:
        raise RuntimeError(
            f"round {label} failed: {_safe_summary_text(terminal.error_message)}"
        )
    if terminal.final_answer is None or terminal.final_answer.content.strip() == "":
        raise RuntimeError(f"round {label} returned empty final answer")
    return SmokeRound(
        label=label,
        run_id=accepted.accepted_run_id,
        event=terminal,
    )


async def _next_terminal(
    watcher: AsyncIterator[HostSessionEvent],
    run_id: str,
) -> HostEvent:
    """等待指定 public Run terminal event。

    :param watcher: durable/transient 联合 session event iterator。
    :param run_id: 目标 Run id。
    :returns: terminal HostEvent。
    :raises TimeoutError: 超过 smoke timeout 时抛出。
    :raises RuntimeError: iterator 提前结束时抛出。
    """

    async def read() -> HostEvent:
        """读取 iterator 直到目标 terminal。

        :returns: terminal event。
        :raises RuntimeError: iterator 提前结束时抛出。
        """

        async for event in watcher:
            if not isinstance(event, HostEvent):
                continue
            if event.run_id == run_id and event.terminal_status is not None:
                return event
        raise RuntimeError("Host event iterator ended before terminal event")

    return await asyncio.wait_for(read(), timeout=_TERMINAL_WAIT_SECONDS)


def _read_internal_projection_observation(
    *,
    args: SmokeArgs,
    options: OpenHostOptions,
    session_id: str,
    final_run_id: str,
) -> InternalProjectionObservation:
    """通过 Host owner API做 internal diagnostic projection read。

    该函数只在所有 public runs 完成后读取 durable truth；不会写入 wait result、
    accept result 或 resume fact，也不会把 internal read 宣称为 public API。

    :param args: typed smoke 参数。
    :param options: public Host options，用于同源 durable location/policy。
    :param session_id: public Session id。
    :param final_run_id: no-tool observation Run id。
    :returns: projection 一致性摘要。
    :raises RuntimeError: projection failure、缺 row 或 typed material 时抛出。
    :raises Exception: durable corruption 时透出。
    """

    memory_policy = options.memory_projection_policy
    if memory_policy is None:
        raise RuntimeError("R03 smoke requires memory projection policy")
    durable_options = _durable_options(options)
    observation: InternalProjectionObservation | None = None
    with open_host_durable_store(durable_options) as store:
        memory_result = catch_up_conversation_memory_projection(
            store.transaction_runner,
            policy=memory_policy,
            batch_size=options.memory_projection_catchup_batch_size,
        )
        trace_result = catch_up_tool_trace_projection(
            store.transaction_runner,
            options=_tool_trace_sink_options_from_open_host_options(options),
        )
        if memory_result.failures > 0 or trace_result.failures > 0:
            raise RuntimeError("R03 internal projection catch-up recorded failure")
        observation = store.transaction_runner.run_read(
            lambda transaction: _projection_observation_in_transaction(
                transaction=transaction,
                args=args,
                options=options,
                session_id=session_id,
                final_run_id=final_run_id,
            )
        )
    if observation is None:
        raise RuntimeError("R03 internal projection observation is missing")
    return observation


def _projection_observation_in_transaction(
    *,
    transaction: HostTransaction,
    args: SmokeArgs,
    options: OpenHostOptions,
    session_id: str,
    final_run_id: str,
) -> InternalProjectionObservation:
    """在单个只读 transaction 中构造 projection 摘要。

    :param transaction: Host durable transaction。
    :param args: typed smoke 参数。
    :param options: public Host options。
    :param session_id: public Session id。
    :param final_run_id: final observation Run id。
    :returns: internal projection observation。
    :raises RuntimeError: required canonical/projection row 缺失时抛出。
    :raises Exception: strict resolver 或 projection corruption 时透出。
    """

    rows = tuple(
        row
        for row in EventLogStore().read_events_after(
            transaction,
            0,
            limit=_EVENT_READ_LIMIT,
        )
        if row.session_id == session_id
    )
    awaiting_rows = _canonical_fact_rows(
        rows,
        event_type=_EVENT_TYPE_TOOL_AWAITING,
    )
    result_rows = _canonical_fact_rows(
        rows,
        event_type=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
    )
    request_atoms = _strict_accepted_request_atoms(
        transaction,
        rows,
    )
    _validate_required_request_atoms(
        args,
        tuple(atoms for _row, atoms in request_atoms),
    )
    selected_awaiting_requests = tuple(
        (row, atoms)
        for row, atoms in request_atoms
        if atoms.tool_name == args.fins_awaiting_tool.value
    )
    if len(selected_awaiting_requests) != 1:
        raise RuntimeError("selected Fins awaiting request atom must occur exactly once")
    selected_request_row, selected_request_atoms = selected_awaiting_requests[0]
    selected_awaiting_payloads: list[Mapping[str, JsonValue]] = []
    for row in awaiting_rows:
        payload = event_payload_object(
            transaction,
            row,
            payload_label="R03 smoke TOOL_AWAITING",
        )
        if payload.get("tool_name") == args.fins_awaiting_tool.value:
            selected_awaiting_payloads.append(payload)
    if len(selected_awaiting_payloads) != 1:
        raise RuntimeError("selected Fins TOOL_AWAITING fact must occur exactly once")
    _validate_tool_awaiting_payload_contract(
        selected_awaiting_payloads[0],
        expected_request=AwaitingRequestIdentity(
            event_id=selected_request_row.event_id,
            event_sequence=selected_request_row.event_sequence,
            tool_call_id=selected_request_atoms.tool_call_id,
            tool_name=selected_request_atoms.tool_name,
        ),
    )
    projections = tuple(
        _accepted_projection(transaction, row) for row in result_rows
    )
    if any(projection.llm_material is None for projection in projections):
        raise RuntimeError("accepted result projection has no typed LLM material")
    trace_source_texts = tuple(
        _trace_business_source(transaction, row, projection)
        for row, projection in zip(result_rows, projections, strict=True)
    )
    memory_text = _memory_projection_text(
        transaction,
        options=options,
        session_id=session_id,
    )
    final_run = read_run_by_id(transaction, final_run_id)
    if final_run is None:
        raise RuntimeError("final observation Run row is missing")
    compact_source_notes = _compact_source_notes(
        transaction,
        run=final_run,
    )
    run_input_text = _runner_input_text(
        transaction,
        final_run_id=final_run_id,
    )
    return InternalProjectionObservation(
        request_tool_names=tuple(atoms.tool_name for _row, atoms in request_atoms),
        accepted_result_count=len(projections),
        available_citation_count=sum(
            1
            for projection in projections
            if projection.source.state is AcceptedToolResultSourceState.AVAILABLE
        ),
        available_citation_tool_names=tuple(
            projection.tool_name
            for projection in projections
            if projection.source.state is AcceptedToolResultSourceState.AVAILABLE
            and projection.tool_name is not None
        ),
        run_input_text=run_input_text,
        memory_text=memory_text,
        compact_source_notes=compact_source_notes,
        trace_source_texts=trace_source_texts,
        projection_source_texts=tuple(
            projection.source.text for projection in projections
        ),
    )


def _strict_accepted_request_atoms(
    transaction: HostTransaction,
    rows: Sequence[EventLogRow],
) -> tuple[tuple[EventLogRow, ToolCallRequestAtoms], ...]:
    """只解析 canonical accepted ``TOOL_CALL_REQUESTED`` request atoms。

    Engine preview 与 Host canonical fact 可以共享同一 event type；只有
    ``EventClass.CANONICAL_FACT`` 是 accepted request atom 的 typed owner
    discriminator。preview 不得按 id 前缀或字段 presence 猜测，也不得进入
    strict canonical parser。

    :param transaction: 当前 Host read transaction。
    :param rows: 同一 Session 的 EventLog rows。
    :returns: canonical request row 与 strict parsed atoms。
    :raises HostDurableError: canonical request atom 缺失或损坏时由 strict parser
        抛出。
    """

    return tuple(
        (row, tool_call_request_atoms(transaction, row))
        for row in _canonical_fact_rows(
            rows,
            event_type=_EVENT_TYPE_TOOL_CALL_REQUESTED,
        )
    )


def _canonical_fact_rows(
    rows: Sequence[EventLogRow],
    *,
    event_type: str,
) -> tuple[EventLogRow, ...]:
    """按 typed EventClass 收集指定类型的 canonical facts。

    Engine activity preview 可以与 Host canonical fact 共享 event type；只有
    ``EventClass.CANONICAL_FACT`` 承诺 strict Host semantic contract。调用方不得
    按 source、event id 或 payload 字段 presence 猜测 row 语义。

    :param rows: 同一 Session 的 EventLog rows。
    :param event_type: 需要收集的 EventLog event type。
    :returns: 保持 durable sequence 顺序的 canonical fact rows。
    :raises Exception: 不主动抛出异常。
    """

    return tuple(
        row
        for row in rows
        if row.event_class is EventClass.CANONICAL_FACT
        and row.event_type == event_type
    )


def _validate_required_request_atoms(
    args: SmokeArgs,
    request_atoms: Sequence[ToolCallRequestAtoms],
) -> None:
    """验证五个 required request atoms 的 exact arguments/digest。

    :param args: typed smoke 参数，作为 expected arguments 唯一输入。
    :param request_atoms: strict owner 已解析的 canonical request atoms。
    :returns: ``None``。
    :raises RuntimeError: required call 数量、arguments 或 digest 不同源时抛出。
    """

    for expected_call in _expected_required_tool_calls(args):
        matching_atoms = tuple(
            atoms
            for atoms in request_atoms
            if atoms.tool_name == expected_call.tool_name
        )
        if len(matching_atoms) != 1:
            raise RuntimeError(
                f"required tool {expected_call.tool_name} must occur exactly once"
            )
        _validate_expected_request_atom(expected_call, matching_atoms[0])


def _validate_expected_request_atom(
    expected_call: ExpectedToolCall,
    atoms: ToolCallRequestAtoms,
) -> None:
    """验证单个 strict request atom 与 typed expected call 完全一致。

    :param expected_call: typed expected tool/arguments。
    :param atoms: ``tool_call_request_atoms`` 的 strict 结果。
    :returns: ``None``。
    :raises RuntimeError: tool、arguments 或任一 arguments digest 漂移时抛出。
    """

    expected_arguments_json: Mapping[str, JsonValue] = {
        "arguments": dict(expected_call.arguments)
    }
    if atoms.tool_name != expected_call.tool_name:
        raise RuntimeError("strict request atom tool name mismatch")
    if atoms.arguments_json != expected_arguments_json:
        raise RuntimeError(
            f"required tool {expected_call.tool_name} exact arguments mismatch"
        )
    expected_digest = sha256_digest_json(expected_arguments_json)
    if atoms.normalized_arguments_digest != expected_digest:
        raise RuntimeError(
            f"required tool {expected_call.tool_name} normalized digest mismatch"
        )
    if atoms.arguments_payload_digest != expected_digest:
        raise RuntimeError(
            f"required tool {expected_call.tool_name} payload digest mismatch"
        )


def _validate_tool_awaiting_payload_contract(
    payload: Mapping[str, JsonValue],
    *,
    expected_request: AwaitingRequestIdentity,
) -> None:
    """验证 TOOL_AWAITING 只携带治理字段和 strict request link。

    :param payload: digest-checked canonical ``TOOL_AWAITING`` payload。
    :param expected_request: selected awaiting canonical request identity。
    :returns: ``None``。
    :raises RuntimeError: arguments/digest 副本、tool identity 或 request link 漂移时抛出。
    """

    forbidden_fields = _forbidden_awaiting_duplicate_fields(payload)
    if forbidden_fields:
        raise RuntimeError(
            "TOOL_AWAITING duplicated request arguments/digest fields: "
            + ",".join(forbidden_fields)
        )
    tool_name = payload.get("tool_name")
    tool_call_id = payload.get("tool_call_id")
    if not isinstance(tool_name, str) or tool_name != expected_request.tool_name:
        raise RuntimeError("TOOL_AWAITING tool_name mismatches selected request")
    if (
        not isinstance(tool_call_id, str)
        or tool_call_id != expected_request.tool_call_id
    ):
        raise RuntimeError("TOOL_AWAITING tool_call_id mismatches selected request")
    link_value = payload.get("tool_call_requested_event_ref")
    if not isinstance(link_value, Mapping):
        raise RuntimeError("TOOL_AWAITING canonical request link is missing")
    link = cast(Mapping[str, JsonValue], link_value)
    if frozenset(link.keys()) != frozenset({"event_id", "event_sequence"}):
        raise RuntimeError("TOOL_AWAITING canonical request link shape is invalid")
    event_id = link.get("event_id")
    event_sequence = link.get("event_sequence")
    if not isinstance(event_id, str) or event_id != expected_request.event_id:
        raise RuntimeError("TOOL_AWAITING request event_id link mismatch")
    if (
        not isinstance(event_sequence, int)
        or isinstance(event_sequence, bool)
        or event_sequence != expected_request.event_sequence
    ):
        raise RuntimeError("TOOL_AWAITING request event_sequence link mismatch")


def _forbidden_awaiting_duplicate_fields(
    payload: Mapping[str, JsonValue],
) -> tuple[str, ...]:
    """列出 TOOL_AWAITING 中禁止复制的 request arguments/digest 字段。

    :param payload: canonical ``TOOL_AWAITING`` payload。
    :returns: 排序后的 forbidden field names；合规时为空 tuple。
    :raises Exception: 不主动抛出异常。
    """

    return tuple(
        sorted(
            field_name
            for field_name in payload
            if "arguments" in field_name
            or field_name == "normalized_arguments_digest"
        )
    )


def _accepted_projection(
    transaction: HostTransaction,
    row: EventLogRow,
) -> AcceptedToolResultProjection:
    """读取单个 accepted result shared projection。

    :param transaction: Host durable transaction。
    :param row: canonical result row。
    :returns: shared accepted-result projection。
    :raises Exception: payload 或 shared projection corruption 时透出。
    """

    payload = event_payload_object(
        transaction,
        row,
        payload_label="R03 smoke accepted result",
    )
    return project_accepted_tool_result(
        transaction,
        row,
        resolved_payload=payload,
    )


def _trace_business_source(
    transaction: HostTransaction,
    row: EventLogRow,
    projection: AcceptedToolResultProjection,
) -> str:
    """读取 LLM-ready Tool Trace business source 并核对 shared owner。

    :param transaction: Host durable transaction。
    :param row: canonical result row。
    :param projection: shared accepted-result projection。
    :returns: trace business source text。
    :raises RuntimeError: trace row/summary 缺失或 source/state 不同源时抛出。
    """

    trace_row = read_tool_trace_hot_row(transaction, row.event_id)
    if trace_row is None:
        raise RuntimeError("accepted result Tool Trace row is missing")
    result_value = trace_row.trace_summary.get("tool_result")
    if not isinstance(result_value, Mapping):
        raise RuntimeError("LLM-ready Tool Trace tool_result is missing")
    source_text = result_value.get("business_source_text")
    source_state = result_value.get("business_source_state")
    if source_text != projection.source.text:
        raise RuntimeError("Tool Trace business source text drifted")
    if source_state != projection.source.state.value:
        raise RuntimeError("Tool Trace business source state drifted")
    if "diagnostic_reason" in result_value:
        raise RuntimeError("Tool Trace business source exposes diagnostic reason")
    return projection.source.text


def _memory_projection_text(
    transaction: HostTransaction,
    *,
    options: OpenHostOptions,
    session_id: str,
) -> str:
    """读取 latest Conversation Memory LLM-readable text。

    :param transaction: Host durable transaction。
    :param options: public Host options。
    :param session_id: public Session id。
    :returns: selected recent evidence 拼接文本。
    :raises RuntimeError: memory policy/snapshot 缺失时抛出。
    """

    policy = options.memory_projection_policy
    if policy is None:
        raise RuntimeError("memory projection policy is missing")
    row = read_latest_memory_snapshot(
        transaction,
        session_id=session_id,
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        policy_digest=digest_memory_projection_policy(policy),
    )
    if row is None:
        raise RuntimeError("Conversation Memory snapshot is missing")
    return "\n".join(
        item.text for item in row.snapshot.trace_memory.selected_recent_window
    )


def _compact_source_notes(
    transaction: HostTransaction,
    *,
    run: RunRow,
) -> tuple[str, ...]:
    """构造 final Run 同源 compactor evidence source notes。

    :param transaction: Host durable transaction。
    :param run: final observation Run row。
    :returns: ``EvidenceReadableItemVNext.source_note`` 文本。
    :raises RuntimeError: final input payload 或 compactor evidence 缺失时抛出。
    :raises Exception: compact material strict projection corruption 时透出。
    """

    input_row = EventLogStore().read_event_by_id(transaction, run.input_event_id)
    if input_row is None:
        raise RuntimeError("final observation input event is missing")
    input_payload = event_payload_object(
        transaction,
        input_row,
        payload_label="R03 final observation input",
    )
    display_text = input_payload.get("display_text")
    if not isinstance(display_text, str) or display_text.strip() == "":
        raise RuntimeError("final observation display_text is missing")
    view = build_pre_dispatch_compact_material_view(
        transaction,
        EventLogStore(),
        run=run,
        current_display_text=display_text,
    )
    selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=run.input_event_sequence,
        memory_snapshot_cursor=None,
        policy_digest="r03-smoke-internal-read",
        material_blocks=view.material_blocks,
    )
    pack = build_compact_material_pack(
        selected_segment=selection,
        material_blocks=view.material_blocks,
        memory_snapshot=None,
        inline_delta_repair_view=None,
        current_input_ref=run.input_event_id,
        current_input_text=display_text,
        previous_compacted_view=view.previous_compacted_view,
        previous_compacted_readable_view=view.previous_compacted_readable_view,
    )
    compact_input = conversation_compact_input_vnext_from_material_pack(pack)
    notes = tuple(
        item.source_note
        for item in compact_input.evidence_material
        if item.source_note is not None
    )
    if len(notes) == 0:
        raise RuntimeError("compactor evidence source notes are missing")
    return notes


def _runner_input_text(
    transaction: HostTransaction,
    *,
    final_run_id: str,
) -> str:
    """解析 final Run 的真实 runner-call LLM message projection。

    :param transaction: Host durable transaction。
    :param final_run_id: final observation Run id。
    :returns: LLM message content 拼接文本。
    :raises RuntimeError: runner-call signal/projection/message 缺失时抛出。
    :raises Exception: descriptor/digest corruption 时透出。
    """

    page = read_runner_call_reconstruction_signals_by_run(
        transaction,
        final_run_id,
        after_event_sequence=0,
        limit=_PROJECTION_READ_LIMIT,
    )
    if len(page.signals) == 0:
        raise RuntimeError("final runner-call projection signal is missing")
    resolved = resolve_runner_call_projection_from_signal(
        transaction,
        page.signals[-1],
    )
    messages = resolved.runner_input_projection.payload.get("messages")
    if not isinstance(messages, list):
        raise RuntimeError("runner input projection messages are missing")
    contents: list[str] = []
    for message in messages:
        if not isinstance(message, Mapping):
            raise RuntimeError("runner input projection message must be object")
        content = message.get("content")
        if isinstance(content, str):
            contents.append(content)
    if len(contents) == 0:
        raise RuntimeError("runner input projection has no readable content")
    return "\n".join(contents)


def _assert_projection_closure(
    args: SmokeArgs,
    observation: InternalProjectionObservation,
) -> None:
    """断言 exact request/source 传播与 opaque absence closure。

    :param args: typed smoke 参数。
    :param observation: internal projection observation。
    :returns: ``None``。
    :raises RuntimeError: 任一 required tool/source/absence assertion 失败时抛出。
    """

    required_tools = {
        "read_file",
        "search_web",
        args.fins_awaiting_tool.value,
        _FINS_LIST_TOOL_NAME,
        _FINS_READ_TOOL_NAME,
    }
    observed_tools = set(observation.request_tool_names)
    missing_tools = required_tools.difference(observed_tools)
    if missing_tools:
        raise RuntimeError(
            "required real tool calls are missing: " + ",".join(sorted(missing_tools))
        )
    if observation.accepted_result_count < len(required_tools):
        raise RuntimeError("accepted result count is below required tool count")
    if _FINS_READ_TOOL_NAME not in observation.available_citation_tool_names:
        raise RuntimeError(
            "real get_document_sections result produced no explicit citation"
        )
    projection_sources = observation.projection_source_texts
    if tuple(observation.trace_source_texts) != tuple(projection_sources):
        raise RuntimeError("Tool Trace source sequence differs from shared projection")
    for source_text in tuple(dict.fromkeys(projection_sources)):
        if source_text not in observation.run_input_text:
            raise RuntimeError("RunInput is missing shared business source text")
        if source_text not in observation.memory_text:
            raise RuntimeError("Conversation Memory is missing shared business source text")
        if source_text not in observation.compact_source_notes:
            raise RuntimeError("Compact source_note is missing shared business source text")
    visible_text = canonical_json_dumps(
        {
            "run_input": observation.run_input_text,
            "memory": observation.memory_text,
            "compact_sources": list(observation.compact_source_notes),
            "trace_sources": list(observation.trace_source_texts),
        }
    )
    for sentinel in _OPAQUE_SENTINELS:
        if sentinel in visible_text:
            raise RuntimeError("opaque evidence sentinel reached LLM-readable material")


def _durable_options(options: OpenHostOptions) -> HostDurableStoreOptions:
    """从 public Host options 构造同源 internal read-only durable options。

    :param options: public Host options。
    :returns: durable store options。
    :raises ValueError: durable option contract 非法时抛出。
    """

    return HostDurableStoreOptions(
        db_path=options.db_path,
        payload_policy=PayloadStoragePolicy(
            artifact_root=options.artifact_root,
            payload_inline_threshold_bytes=options.payload_inline_threshold_bytes,
            create_artifact_root=options.create_parent_dirs,
        ),
        create_parent_dirs=options.create_parent_dirs,
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=options.sqlite_busy_timeout_seconds,
            write_busy_retry_count=options.sqlite_write_busy_retry_count,
            write_retry_initial_delay_seconds=(
                options.sqlite_write_retry_initial_delay_seconds
            ),
            write_retry_backoff_multiplier=(
                options.sqlite_write_retry_backoff_multiplier
            ),
            write_retry_max_delay_seconds=(
                options.sqlite_write_retry_max_delay_seconds
            ),
        ),
    )


def _host_context(request_id: str) -> HostCallContext:
    """构造 public Host 调用上下文。

    :param request_id: 调用方 request id。
    :returns: HostCallContext。
    :raises ValueError: typed context 字段非法时抛出。
    """

    return HostCallContext(
        actor=_DEFAULT_ACTOR,
        source="utils.smoke_host_public_r03_semantic_ownership",
        request_id=request_id,
        authorization_claims=(
            AuthorizationClaim(name="role", value="manual-smoke"),
        ),
        operation_context=OperationContext(
            operation_name="host_public_r03_semantic_ownership_smoke",
            operation_kind="manual_smoke",
            business_domain="financial_report",
            business_object_type="semantic_ownership_validation",
            business_object_id=None,
            scenario="r03_semantic_ownership",
            correlation_id=None,
        ),
    )


def _validate_doc_file(path: pathlib.Path) -> None:
    """校验 Doc smoke 输入文件。

    :param path: 调用方 doc file。
    :returns: ``None``。
    :raises FileNotFoundError: path 不存在或不是非空普通文件时抛出。
    """

    if not path.is_file():
        raise FileNotFoundError("R03 smoke doc file must be an existing regular file")
    if path.stat().st_size <= 0:
        raise FileNotFoundError("R03 smoke doc file must be non-empty")


def _required_cli_text(value: str, field_name: str) -> str:
    """校验并规范化 CLI 必填文本。

    :param value: CLI 文本。
    :param field_name: 字段名。
    :returns: 去除首尾空白的文本。
    :raises ValueError: 文本为空时抛出。
    """

    normalized = value.strip()
    if normalized == "":
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _safe_summary_text(text: str | None) -> str:
    """生成 stdout 可用的有界脱敏失败摘要。

    :param text: 原始异常/terminal message。
    :returns: 有界且不含常见 secret marker 的摘要。
    :raises Exception: 不主动抛出异常。
    """

    if text is None or text.strip() == "":
        return "none"
    lowered = text.lower()
    if any(marker in lowered for marker in _SECRET_MARKERS):
        return "<redacted>"
    normalized = " ".join(text.split())
    if len(normalized) <= _FAILURE_SUMMARY_MAX_CHARS:
        return normalized
    return normalized[:_FAILURE_SUMMARY_MAX_CHARS] + "..."


def _workspace_retention_summary(caller_requested: bool) -> str:
    """构造与实际 cleanup 行为一致的 workspace retention 摘要。

    :param caller_requested: 调用方是否显式传入 ``--keep-workspace``。
    :returns: 始终声明 artifacts 被保留，并附调用方标记的有界文本。
    :raises Exception: 不主动抛出异常。
    """

    return (
        "R03 SMOKE WORKSPACE_KEPT true "
        f"caller_requested={str(caller_requested).lower()} cleanup=never"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """运行 CLI 并只打印有界 PASS/FAIL 摘要。

    :param argv: 可选显式 CLI 参数；``None`` 时读取 ``sys.argv``。
    :returns: 成功 ``0``，失败 ``1``。
    :raises Exception: 不向调用方继续抛出；失败转为安全摘要。
    """

    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        return asyncio.run(run_smoke(args, env=os.environ))
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        print(f"R03 SMOKE FAIL {_safe_summary_text(str(exc))}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
