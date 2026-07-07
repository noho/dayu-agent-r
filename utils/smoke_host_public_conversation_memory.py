"""Host public 财报对话记忆 smoke 的 Service-like runtime assembly 脚本。

本脚本用于人工验证真实 Host public handle 在多轮会话中能否保持由
mock 财报工具确认过的事实。脚本只通过 ``open_host``、``ensure_session``、
``submit_followup``、``watch_session_events``、``get_session`` 与必要时的
``get_run`` 观察结果，不读取 durable store、EventLog、memory 表或 compact
payload 内容。

脚本不会输出 API key、headers、完整 prompt 或完整 pressure payload。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from math import floor
from typing import Final
from uuid import uuid4

_PROJECT_ROOT: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dayu.contracts import (
    AsyncDirectToolExecutionCapability,
    JsonValue,
    ToolBundle,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
)
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolExecutionOutcome,
)
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.host import (
    EnsureSessionRequest,
    FollowupBehavior,
    Host,
    HostCallContext,
    HostEvent,
    HostEventKind,
    OpenHostOptions,
    OperationContext,
    SessionSnapshot,
    SessionStatus,
    open_host,
)
from dayu.host.api import AuthorizationClaim
from dayu.host.context_budget import DEFAULT_ESTIMATOR_CHARS_PER_TOKEN
from dayu.runtime.config_loader import (
    ConfigLoader,
    RuntimeConfig,
)
from dayu.runtime.location import resolve_runtime_locations
from dayu.runtime.log import LogLevel, configure
from dayu.runtime.scene_prepare import (
    PreparedSceneInputs,
    ScenePrepareRequest,
    SceneToolCatalog,
    prepare_scene,
)
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscovery,
    ToolsDiscoveryProviderBinding,
    ToolsDiscoveryProviderOutput,
    ToolsDiscoveryProviderSpec,
    ToolsDiscoveryResult,
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
from utils.smoke_host_public_diagnostics import (
    print_duplicate_governance_diagnostics,
)

_PACKAGE_CONFIG_ROOT: Final[pathlib.Path] = _PROJECT_ROOT / "dayu" / "config"
_DEFAULT_WORKSPACE_PARENT: Final[pathlib.Path] = _PROJECT_ROOT / "workspace" / "tmp"
_DEFAULT_WORKSPACE_PREFIX: Final[str] = "host-public-conversation-memory-smoke"
_DEFAULT_SCENE_ID: Final[str] = "smoke_host_public_conversation_memory"
_DEFAULT_SLOT_KEY_PREFIX: Final[str] = "manual-smoke-conversation-memory"
_TOOL_NAME: Final[str] = "get_mock_finance_facts"
_TOOL_TAG: Final[str] = "manual-smoke"
_PROVIDER_ID: Final[str] = "host-public-conversation-memory-smoke"
_PROVIDER_SPEC_ID: Final[str] = "host-public-conversation-memory-smoke"
_PROVIDER_IMPORT_DISPLAY_PATH: Final[str] = "__main__:discover_smoke_tools"
_SMOKE_MARKER: Final[str] = "DAYU_FINANCE_MEMORY_CMB_NIM_2024H1_V1"
_ASSERTION_PREFIX: Final[str] = "DAYU_FINANCE_MEMORY_ASSERT"
_CLIENT_REQUEST_PREFIX: Final[str] = "manual-smoke-conversation-memory"
_DEFAULT_USER_ID: Final[str] = "manual-smoke-user"
_TARGET_COMPANY: Final[str] = "招商银行"
_DEFAULT_PERIOD: Final[str] = "2024H1"
_DEFAULT_TICKER: Final[str] = "600036.SH"
_DEFAULT_TOPIC: Final[str] = "息差"
_DEFAULT_METRIC: Final[str] = "net_interest_margin"
_FACT_NIM: Final[str] = "1.88%"
_FACT_NIM_YOY: Final[str] = "-0.14pct"
_FACT_ASSET_YIELD: Final[str] = "3.45%"
_FACT_LIABILITY_COST: Final[str] = "1.74%"
_FACT_RETAIL_LOAN_SHARE: Final[str] = "52.6%"
_FACT_TIME_DEPOSIT_SHARE: Final[str] = "37.2%"
_FACT_NPL_RATIO: Final[str] = "0.94%"
_ASSERTION_LINE: Final[str] = (
    "DAYU_FINANCE_MEMORY_ASSERT "
    "marker=DAYU_FINANCE_MEMORY_CMB_NIM_2024H1_V1 "
    "company=招商银行 period=2024H1 "
    "net_interest_margin=1.88% yoy=-0.14pct"
)
_FINAL_PREVIEW_CHARS: Final[int] = 600
_SMOKE_TOOL_PRESSURE_CHARS: Final[int] = 120_000
_PRESSURE_CHUNK: Final[str] = "招商银行2024H1息差记忆压力文本"
_PRESSURE_PAD_TOKEN: Final[str] = (
    _PRESSURE_CHUNK
    + " DAYU_FINANCE_MEMORY_PRESSURE_PAD DAYU_FINANCE_MEMORY_PRESSURE_PAD"
    + " DAYU_FINANCE_MEMORY_PRESSURE_PAD DAYU_FINANCE_MEMORY_PRESSURE_PAD"
    + " DAYU_FINANCE_MEMORY_PRESSURE_PAD DAYU_FINANCE_MEMORY_PRESSURE_PAD"
    + " DAYU_FINANCE_MEMORY_PRESSURE_PAD DAYU_FINANCE_MEMORY_PRESSURE_PAD"
)
_COMPACT_PRESSURE_TARGET_EXTRA_TOKENS: Final[int] = 16_384
_COMPACT_PRESSURE_HARD_MARGIN_TOKENS: Final[int] = 24_576
_COMPACT_PRESSURE_RESERVE_TOKENS: Final[int] = 8_192
_COMPACT_PRESSURE_MIN_PROMPT_TOKENS: Final[int] = 1_024
_COMPACT_PRESSURE_LARGE_WINDOW_TOKENS: Final[int] = 1_000_000
_PRESSURE_LINE_CHARS: Final[int] = 120
_COMPACT_ARTIFACT_PRINT_LIMIT: Final[int] = 10
_TERMINAL_TIMEOUT_SECONDS: Final[float] = 600.0
_ROUND_1_LABEL: Final[str] = "round1-confirm-finance-fact"
_ROUND_2_LABEL: Final[str] = "round2-group-and-pressure"
_ROUND_3_LABEL: Final[str] = "round3-topic-shift-no-tool"
_ROUND_4_LABEL: Final[str] = "round4-confirmed-fact-consistency"
_STDOUT_PREFIX_ROUND_START: Final[str] = "SMOKE ROUND_START"
_STDOUT_PREFIX_ROUND_DONE: Final[str] = "SMOKE ROUND_DONE"
_STDOUT_PREFIX_FINAL_PREVIEW: Final[str] = "SMOKE FINAL_PREVIEW"
_STDOUT_PREFIX_ASSERT_MEMORY_VALUE: Final[str] = "SMOKE ASSERT_MEMORY_VALUE"
_STDOUT_PREFIX_COMPACT_ARTIFACT_ROOT: Final[str] = "SMOKE COMPACT_ARTIFACT_ROOT"
_STDOUT_PREFIX_COMPACT_ARTIFACT_FILE_COUNT: Final[str] = (
    "SMOKE COMPACT_ARTIFACT_FILE_COUNT"
)
_STDOUT_PREFIX_SESSION_OBSERVE: Final[str] = "SMOKE SESSION_OBSERVE"
_SOURCE_NAME: Final[str] = "utils.smoke_host_public_conversation_memory"
_OPERATION_NAME: Final[str] = "host_public_conversation_memory_smoke"
_OPERATION_KIND: Final[str] = "manual_smoke"
_BUSINESS_DOMAIN: Final[str] = "host"
_SCENARIO: Final[str] = "phase12_5_conversation_memory_smoke"
_PROVIDER_VERSION: Final[str] = "v1"
_TOOL_NOTE: Final[str] = (
    "These are deterministic mock facts for Host public conversation memory "
    "smoke, not real Fins data."
)
_NO_TOOL_SELECTION: Final[frozenset[str]] = frozenset()


@dataclass(frozen=True, slots=True)
class SmokeArgs:
    """命令行参数。

    :param workspace_root: workspace / 项目根目录，用于 location resolver。
    :param scene_id: 需要装配的 scene id。
    :param execution_profile_id: 可选 execution profile 显式 override。
    :param host_runtime_id: 可选 Host runtime 显式 override。
    :param model_id: 可选 Run/UI 模型显式 override。
    :param runner_option_hint_id: 可选 Run/UI runner option hint 显式 override。
    :param log_level: Dayu 日志级别。
    :param reuse_session: 是否复用稳定 slot key；默认每次使用 fresh slot。
    :param keep_workspace: 是否在输出中显式标记保留 workspace。
    """

    workspace_root: pathlib.Path
    scene_id: str
    execution_profile_id: str | None
    host_runtime_id: str | None
    model_id: str | None
    runner_option_hint_id: str | None
    log_level: LogLevel
    reuse_session: bool
    keep_workspace: bool


@dataclass(frozen=True, slots=True)
class RoundResult:
    """单轮 public Host 运行摘要。

    :param label: 人工可读轮次标签。
    :param run_id: Host Run id。
    :param event: terminal HostEvent。
    """

    label: str
    run_id: str
    event: HostEvent


@dataclass(frozen=True, slots=True)
class RuntimeAssemblyResult:
    """完整 runtime assembly 结果。

    :param options: 可传给 ``open_host`` 的 Host 构造期输入。
    :param scene_inputs: ScenePrepare 输出。
    :param diagnostics: 调用 Host 前的装配诊断。
    :param effective_tool_bundle: Host 打开前已应用截断默认值的工具 bundle。
    :param smoke_tool: 从 effective ToolBundle 恢复出的 mock 财报工具实例。
    """

    options: OpenHostOptions
    scene_inputs: PreparedSceneInputs
    diagnostics: ServiceOpenHostAssemblyDiagnostics
    effective_tool_bundle: ToolBundle
    smoke_tool: "MockFinanceFactTool"


class MockFinanceFactTool:
    """返回固定招商银行 2024H1 息差事实的 mock business tool。"""

    def __init__(self) -> None:
        """初始化工具调用观测状态。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.call_count = 0
        self.last_marker: str | None = None
        self._tracked_session_id: str | None = None

    def track_session(self, session_id: str) -> None:
        """限定本次 smoke 计数观察的 Session。

        Host open 时可能 recovery 旧的未完成 Run。旧 Run 可以继续拿到 mock
        工具结果，但不应污染本次 fresh session 的工具调用计数断言。

        :param session_id: 本次 smoke 新确保的 Session id。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._tracked_session_id = session_id

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """返回确定性 mock 财报事实。

        :param call: 工具调用请求；仅 ``include_pressure`` 影响压力字段。
        :param context: 批式执行上下文，本工具不读取其中字段。
        :returns: 成功工具 outcome。
        :raises Exception: 不主动抛出异常。
        """

        include_pressure = _include_pressure_argument(call.arguments)
        if context.session_id == self._tracked_session_id:
            self.call_count += 1
            self.last_marker = _SMOKE_MARKER
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value=_mock_finance_fact_payload(include_pressure=include_pressure),
                meta=None,
            )
        )


def discover_smoke_tools(
    spec: ToolsDiscoveryProviderSpec,
) -> ToolsDiscoveryProviderOutput:
    """ToolsDiscovery provider callable，用于提供 smoke mock 财报工具。

    :param spec: 工具发现 provider spec。
    :returns: smoke provider 输出。
    :raises ValueError: 工具定义字段非法时由底层抛出。
    """

    smoke_tool = MockFinanceFactTool()
    return ToolsDiscoveryProviderOutput(
        provider_id=_PROVIDER_ID,
        version_ref=_PROVIDER_VERSION,
        source_refs=(
            ToolBundleSourceRef(
                source_kind=ToolBundleSourceKind.CONFIG_BINDING,
                source_id=spec.spec_id,
            ),
        ),
        definitions=(_smoke_tool_definition(smoke_tool),),
    )


def parse_args(argv: Sequence[str]) -> SmokeArgs:
    """解析命令行参数。

    :param argv: 不含程序名的参数序列。
    :returns: 解析后的参数。
    :raises SystemExit: argparse 在参数非法时抛出。
    """

    parser = argparse.ArgumentParser(
        description="Run Host public conversation memory finance smoke."
    )
    parser.add_argument(
        "--workspace-root",
        default=None,
        help=(
            "workspace / project root；默认使用 workspace/tmp 下的 fresh smoke "
            "workspace，避免历史 durable DB schema 污染。"
        ),
    )
    parser.add_argument(
        "--scene-id",
        default=_DEFAULT_SCENE_ID,
        help=f"ScenePrepare 使用的 scene id；默认 {_DEFAULT_SCENE_ID}。",
    )
    parser.add_argument(
        "--execution-profile-id",
        default=None,
        help="显式 execution profile id；默认读取配置 default_execution_profile_id。",
    )
    parser.add_argument(
        "--host-runtime-id",
        default=None,
        help="显式 Host runtime id；默认读取配置 default_host_runtime_id。",
    )
    parser.add_argument(
        "--model-id",
        default=None,
        help="Run/UI 模型 override；只允许覆盖 model_id。",
    )
    parser.add_argument(
        "--runner-option-hint-id",
        default=None,
        help="Run/UI runner option hint override；只允许覆盖 runner_option_hint_id。",
    )
    parser.add_argument(
        "--log-level",
        choices=tuple(level.name for level in LogLevel),
        default=LogLevel.VERBOSE.name,
        help="Dayu 日志级别，默认 VERBOSE。",
    )
    parser.add_argument(
        "--reuse-session",
        action="store_true",
        help="复用稳定 durable slot key；默认每次 smoke 使用 fresh slot。",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="输出中标记保留 workspace；脚本不会删除 Host/runtime artifacts。",
    )
    namespace = parser.parse_args(list(argv))
    workspace_root_text: str | None = namespace.workspace_root
    scene_id: str = namespace.scene_id
    execution_profile_id: str | None = namespace.execution_profile_id
    host_runtime_id: str | None = namespace.host_runtime_id
    model_id: str | None = namespace.model_id
    runner_option_hint_id: str | None = namespace.runner_option_hint_id
    log_level_text: str = namespace.log_level
    reuse_session: bool = namespace.reuse_session
    keep_workspace: bool = namespace.keep_workspace
    return SmokeArgs(
        workspace_root=_resolve_workspace_root(workspace_root_text),
        scene_id=scene_id,
        execution_profile_id=execution_profile_id,
        host_runtime_id=host_runtime_id,
        model_id=model_id,
        runner_option_hint_id=runner_option_hint_id,
        log_level=LogLevel[log_level_text],
        reuse_session=reuse_session,
        keep_workspace=keep_workspace,
    )


def _resolve_workspace_root(workspace_root_text: str | None) -> pathlib.Path:
    """解析 smoke workspace root。

    :param workspace_root_text: CLI 显式传入的 workspace root；为 ``None`` 时
        生成 fresh smoke workspace root。
    :returns: 归一化后的 workspace root。
    :raises Exception: 不主动抛出异常。
    """

    if workspace_root_text is not None:
        return pathlib.Path(workspace_root_text).resolve()
    return (
        _DEFAULT_WORKSPACE_PARENT
        / f"{_DEFAULT_WORKSPACE_PREFIX}-{uuid4().hex[:12]}"
    ).resolve()


async def run_smoke(args: SmokeArgs, env: Mapping[str, str]) -> int:
    """运行 Host public 财报对话记忆 smoke。

    :param args: smoke 参数。
    :param env: 环境变量映射。
    :returns: 进程退出码。
    :raises Exception: Host public path、provider 调用或硬断言失败时向上抛出。
    """

    assembly = _prepare_runtime_assembly(args, env=env)
    _print_assembly_diagnostics(assembly.diagnostics, assembly.options)
    smoke_run_id = _new_smoke_run_id()

    print("SMOKE START Host public conversation memory finance smoke")
    print(f"SMOKE WORKSPACE_ROOT {args.workspace_root}")
    print(f"SMOKE RUN_ID {smoke_run_id}")
    print("SMOKE CONTRACT open_host -> ensure_session -> submit_followup -> watch -> get_session")
    print(f"SMOKE MEMORY_MARKER {_SMOKE_MARKER}")
    print("SMOKE LOG_LEVEL", args.log_level.name)
    _print_compact_pressure_plan(assembly.options)

    async with open_host(assembly.options) as host:
        session = await host.ensure_session(_ensure_request(args, smoke_run_id))
        assembly.smoke_tool.track_session(session.session_id)
        watcher = host.watch_session_events(session.session_id)
        print(f"SMOKE SESSION session_id={session.session_id}")
        _assert_session_open(session, label="ensure-session")
        _print_session_observation(session, label="ensure-session")

        first = await _run_round(
            host=host,
            watcher=watcher,
            session_id=session.session_id,
            label=_ROUND_1_LABEL,
            client_request_id=_round_client_request_id(smoke_run_id, 1),
            scene_inputs=assembly.scene_inputs,
            prompt=_round1_prompt(),
            tool_names=assembly.scene_inputs.tool_selection.tool_names,
        )
        _print_round(first)
        _assert_tool_state_after_round1(assembly.smoke_tool)
        _assert_round1_answer(first)
        print(f"SMOKE TOOL_CALL_COUNT_AFTER_ROUND1 {assembly.smoke_tool.call_count}")
        print(
            "SMOKE EXPECTED_FACT "
            f"marker={_SMOKE_MARKER} net_interest_margin={_FACT_NIM} "
            f"yoy={_FACT_NIM_YOY}"
        )
        first_session = await host.get_session(session.session_id)
        _assert_session_open(first_session, label=_ROUND_1_LABEL)
        _print_session_observation(first_session, label=_ROUND_1_LABEL)

        second = await _run_round(
            host=host,
            watcher=watcher,
            session_id=session.session_id,
            label=_ROUND_2_LABEL,
            client_request_id=_round_client_request_id(smoke_run_id, 2),
            scene_inputs=assembly.scene_inputs,
            prompt=_round2_prompt(assembly.options),
            tool_names=_NO_TOOL_SELECTION,
        )
        _print_round(second)
        _assert_tool_call_count(assembly.smoke_tool, expected=1, label=_ROUND_2_LABEL)
        _observe_round2_assertion(second)
        second_session = await host.get_session(session.session_id)
        _assert_session_open(second_session, label=_ROUND_2_LABEL)
        _print_session_observation(second_session, label=_ROUND_2_LABEL)

        third = await _run_round(
            host=host,
            watcher=watcher,
            session_id=session.session_id,
            label=_ROUND_3_LABEL,
            client_request_id=_round_client_request_id(smoke_run_id, 3),
            scene_inputs=assembly.scene_inputs,
            prompt=_round3_prompt(),
            tool_names=_NO_TOOL_SELECTION,
        )
        _print_round(third)
        _assert_tool_call_count(assembly.smoke_tool, expected=1, label=_ROUND_3_LABEL)
        third_session = await host.get_session(session.session_id)
        _assert_session_open(third_session, label=_ROUND_3_LABEL)
        _print_session_observation(third_session, label=_ROUND_3_LABEL)

        fourth = await _run_round(
            host=host,
            watcher=watcher,
            session_id=session.session_id,
            label=_ROUND_4_LABEL,
            client_request_id=_round_client_request_id(smoke_run_id, 4),
            scene_inputs=assembly.scene_inputs,
            prompt=_round4_prompt(),
            tool_names=_NO_TOOL_SELECTION,
        )
        _print_round(fourth)
        _assert_tool_call_count(assembly.smoke_tool, expected=1, label=_ROUND_4_LABEL)
        _assert_round4_answer(fourth)
        final_session = await host.get_session(session.session_id)
        _assert_session_open(final_session, label=_ROUND_4_LABEL)
        _print_session_observation(final_session, label=_ROUND_4_LABEL)
        print(f"SMOKE SESSION_STATUS {final_session.status.value}")

    _print_tool_summary(assembly.smoke_tool)
    _print_compact_summary(assembly.options)
    print("SMOKE PASS public Host conversation memory finance continuity")
    if args.keep_workspace:
        print("SMOKE WORKSPACE_KEPT true")
    else:
        print("SMOKE WORKSPACE_KEPT true  # smoke never deletes Host/runtime artifacts")
    return 0


def _prepare_runtime_assembly(
    args: SmokeArgs, *, env: Mapping[str, str]
) -> RuntimeAssemblyResult:
    """执行 Host 调用前的 runtime/config/tools/scene typed assembly。

    :param args: smoke 参数。
    :param env: 环境变量映射。
    :returns: 完整 runtime assembly 结果。
    :raises ValueError: 配置、工具发现、scene 或 override 无法映射时抛出。
    """

    locations = resolve_runtime_locations(
        project_root=args.workspace_root,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    discovered_tools = _discover_smoke_service_tools(
        config,
        workspace_root=args.workspace_root,
    )
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=args.scene_id,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={CURRENT_TIME_SLOT: current_time()},
            available_tools=SceneToolCatalog.from_tool_bundle(
                discovered_tools.tool_bundle
            ),
        )
    )
    assembly = compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=args.workspace_root,
            config=config,
            locations=locations,
            scene_inputs=scene_inputs,
            discovered_tools=discovered_tools,
            overrides=ServiceAssemblyOverrides(
                host_runtime_id=args.host_runtime_id,
                execution_profile_id=args.execution_profile_id,
                model_id=args.model_id,
                runner_option_hint_id=args.runner_option_hint_id,
            ),
            env=env,
        )
    )
    smoke_tool = _find_mock_finance_fact_tool(assembly.effective_tool_bundle)
    if smoke_tool is None:
        raise ValueError("effective ToolBundle does not contain MockFinanceFactTool")
    return RuntimeAssemblyResult(
        options=assembly.options,
        scene_inputs=scene_inputs,
        diagnostics=assembly.diagnostics,
        effective_tool_bundle=assembly.effective_tool_bundle,
        smoke_tool=smoke_tool,
    )


def _discover_smoke_service_tools(
    config: RuntimeConfig,
    *,
    workspace_root: pathlib.Path,
) -> ServiceDiscoveredTools:
    """发现 Service 工具并确保 smoke mock 财报工具可用。

    :param config: ``ConfigLoader`` 输出的 runtime typed config。
    :param workspace_root: 当前 smoke 的 workspace root。
    :returns: 包含 smoke mock 工具的 Service 工具发现结果。
    :raises ValueError: 已发现同名非 smoke 工具时抛出。
    :raises Exception: 工具发现 provider 失败时向上抛出。
    """

    effective_provider_configs = assemble_effective_tool_provider_configs(
        tuple(config.tool_discovery.providers.values()),
        workspace_root=workspace_root,
    )
    discovered = discover_service_tools(effective_provider_configs)
    existing_smoke_tool = _find_mock_finance_fact_tool(discovered.tool_bundle)
    if existing_smoke_tool is not None:
        return discovered
    if _has_tool_name(discovered.tool_bundle, _TOOL_NAME):
        raise ValueError(f"discovered tool bundle already contains non-smoke tool: {_TOOL_NAME}")

    smoke_result = _discover_builtin_smoke_tools()
    return ServiceDiscoveredTools(
        tool_bundle=ToolBundle(
            definitions=(
                *discovered.tool_bundle.definitions,
                *smoke_result.tool_bundle.definitions,
            )
        ),
        source_refs=(
            *discovered.source_refs,
            *smoke_result.source_refs,
        ),
        provider_reports=(
            *discovered.provider_reports,
            *(
                _format_provider_report(
                    report.provider_id,
                    report.spec_id,
                    report.version_ref,
                    report.tool_names,
                )
                for report in smoke_result.provider_reports
            ),
        ),
        effective_provider_configs=discovered.effective_provider_configs,
        fins_awaiting_runtime=discovered.fins_awaiting_runtime,
    )


def _discover_builtin_smoke_tools() -> ToolsDiscoveryResult:
    """通过 ToolsDiscovery 调用内置 smoke provider。

    :returns: 内置 smoke provider 的工具发现结果。
    :raises Exception: provider 解析或工具定义校验失败时向上抛出。
    """

    return ToolsDiscovery().discover_from_bindings(
        (
            ToolsDiscoveryProviderBinding(
                spec=ToolsDiscoveryProviderSpec(
                    spec_id=_PROVIDER_SPEC_ID,
                    location=PythonImportPathProvider(
                        import_path=_PROVIDER_IMPORT_DISPLAY_PATH
                    ),
                ),
                provider=discover_smoke_tools,
            ),
        )
    )


def _has_tool_name(tool_bundle: ToolBundle, tool_name: str) -> bool:
    """检查工具 bundle 是否包含指定工具名。

    :param tool_bundle: 待检查的工具 bundle。
    :param tool_name: 工具名。
    :returns: 存在同名工具时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return any(definition.name == tool_name for definition in tool_bundle.definitions)


def _find_mock_finance_fact_tool(
    tool_bundle: ToolBundle,
) -> MockFinanceFactTool | None:
    """从 effective ToolBundle 中找出 mock 财报工具实例。

    :param tool_bundle: 已发现或已生效的工具 bundle。
    :returns: mock 财报工具实例；未发现时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    for definition in tool_bundle.definitions:
        if isinstance(definition.callable, MockFinanceFactTool):
            return definition.callable
    return None


def _smoke_tool_definition(smoke_tool: MockFinanceFactTool) -> ToolDefinition:
    """构造 mock 财报工具定义。

    :param smoke_tool: 返回固定财报事实的工具实例。
    :returns: ToolDefinition。
    :raises ValueError: schema 字段非法时由底层抛出。
    """

    properties: dict[str, JsonValue] = {
        "company": {
            "type": "string",
            "description": "Company name.",
        },
        "period": {
            "type": "string",
            "description": "Reporting period.",
        },
        "topic": {
            "type": "string",
            "description": "Finance topic.",
        },
        "metric": {
            "type": "string",
            "description": "Metric name.",
        },
        "include_pressure": {
            "type": "boolean",
            "description": "Whether to include deterministic pressure text.",
        },
    }
    return ToolDefinition(
        name=_TOOL_NAME,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=_TOOL_NAME,
                description=(
                    "Return deterministic mock finance facts for Host public "
                    "conversation memory smoke."
                ),
                parameters=ToolParametersSchema(
                    type="object",
                    properties=properties,
                    required=(
                        "company",
                        "period",
                        "topic",
                        "metric",
                        "include_pressure",
                    ),
                    additional_properties=False,
                ),
            ),
        ),
        callable=smoke_tool,
        execution=AsyncDirectToolExecutionCapability(),
        truncate=None,
        display=None,
        tags=(_TOOL_TAG,),
    )


def _include_pressure_argument(arguments: Mapping[str, JsonValue]) -> bool:
    """读取工具参数中的 ``include_pressure``。

    :param arguments: 工具调用 JSON 参数。
    :returns: 参数为布尔 ``True`` 时返回 ``True``，否则返回 ``False``。
    :raises Exception: 不主动抛出异常。
    """

    value = arguments.get("include_pressure")
    if isinstance(value, bool):
        return value
    return False


def _mock_finance_fact_payload(*, include_pressure: bool) -> Mapping[str, JsonValue]:
    """构造确定性 mock 财报事实返回值。

    :param include_pressure: 是否填充工具侧压力文本。
    :returns: JSON 兼容的工具返回值。
    :raises Exception: 不主动抛出异常。
    """

    pressure_blob = _tool_pressure_blob() if include_pressure else ""
    return {
        "marker": _SMOKE_MARKER,
        "company": _TARGET_COMPANY,
        "ticker": _DEFAULT_TICKER,
        "period": _DEFAULT_PERIOD,
        "topic": _DEFAULT_TOPIC,
        "facts": {
            "net_interest_margin": _FACT_NIM,
            "net_interest_margin_yoy_change": _FACT_NIM_YOY,
            "interest_earning_asset_yield": _FACT_ASSET_YIELD,
            "interest_bearing_liability_cost": _FACT_LIABILITY_COST,
            "retail_loan_share": _FACT_RETAIL_LOAN_SHARE,
            "time_deposit_share": _FACT_TIME_DEPOSIT_SHARE,
            "npl_ratio": _FACT_NPL_RATIO,
        },
        "assertion_line": _ASSERTION_LINE,
        "note": _TOOL_NOTE,
        "pressure_blob": pressure_blob,
    }


def _ensure_request(args: SmokeArgs, smoke_run_id: str) -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :param args: smoke 参数。
    :param smoke_run_id: 本次 smoke 批次 id。
    :returns: EnsureSessionRequest。
    :raises ValueError: 字段非法时由底层抛出。
    """

    slot_key = (
        _DEFAULT_SLOT_KEY_PREFIX
        if args.reuse_session
        else f"{_DEFAULT_SLOT_KEY_PREFIX}-{smoke_run_id}"
    )
    return EnsureSessionRequest(
        scope="workspace",
        slot_key=slot_key,
        metadata=(),
    )


def _host_context(request_id: str) -> HostCallContext:
    """构造 HostCallContext。

    :param request_id: request id。
    :returns: HostCallContext。
    :raises ValueError: 字段非法时由底层抛出。
    """

    return HostCallContext(
        actor=_DEFAULT_USER_ID,
        source=_SOURCE_NAME,
        request_id=request_id,
        authorization_claims=(
            AuthorizationClaim(name="role", value="manual-smoke"),
        ),
        operation_context=OperationContext(
            operation_name=_OPERATION_NAME,
            operation_kind=_OPERATION_KIND,
            business_domain=_BUSINESS_DOMAIN,
            business_object_type=None,
            business_object_id=None,
            scenario=_SCENARIO,
            correlation_id=None,
        ),
    )


async def _run_round(
    *,
    host: Host,
    watcher: AsyncIterator[HostEvent],
    session_id: str,
    label: str,
    client_request_id: str,
    scene_inputs: PreparedSceneInputs,
    prompt: str,
    tool_names: frozenset[str] | None,
) -> RoundResult:
    """提交一轮 prompt 并等待 terminal HostEvent。

    :param host: public Host handle。
    :param watcher: session-level HostEvent iterator。
    :param session_id: Session id。
    :param label: 轮次标签。
    :param client_request_id: 幂等请求 id。
    :param scene_inputs: ScenePrepare 输出。
    :param prompt: 用户 prompt。
    :param tool_names: 本轮工具选择。
    :returns: RoundResult。
    :raises RuntimeError: terminal 不是 succeeded 或缺少 final answer 时抛出。
    """

    print(f"{_STDOUT_PREFIX_ROUND_START} label={label}")
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
    event = await _next_terminal_for_run(watcher, accepted.accepted_run_id)
    if event.kind is not HostEventKind.SUCCEEDED:
        print(
            "SMOKE ROUND_FAILED "
            + await _terminal_failure_summary(
                host=host,
                event=event,
                run_id=accepted.accepted_run_id,
                label=label,
            )
        )
        raise RuntimeError(
            f"round {label} terminal kind is {event.kind.value}; "
            f"run_id={accepted.accepted_run_id}"
        )
    if event.final_answer is None or event.final_answer.content.strip() == "":
        raise RuntimeError(f"round {label} returned empty final answer")
    return RoundResult(label=label, run_id=accepted.accepted_run_id, event=event)


async def _terminal_failure_summary(
    *,
    host: Host,
    event: HostEvent,
    run_id: str,
    label: str,
) -> str:
    """构造 terminal failed 的脱敏短摘要。

    :param host: public Host handle。
    :param event: terminal HostEvent。
    :param run_id: 目标 Run id。
    :param label: smoke 轮次标签。
    :returns: 可直接打印的一行短摘要。
    :raises Exception: public ``get_run`` 失败时向上抛出。
    """

    snapshot = await host.get_run(run_id)
    terminal_summary = snapshot.terminal_result_summary
    summary_ref = (
        terminal_summary.summary_ref
        if terminal_summary is not None
        else None
    )
    summary_digest = (
        terminal_summary.summary_digest
        if terminal_summary is not None
        else None
    )
    message = _safe_summary_text(event.error_message)
    terminal_status = (
        event.terminal_status.value
        if event.terminal_status is not None
        else "unknown"
    )
    return (
        f"label={label} run_id={run_id} kind={event.kind.value} "
        f"terminal_status={terminal_status} "
        f"event_id={event.event_id} event_sequence={event.event_sequence} "
        f"message={message!r} terminal_summary_ref={summary_ref!r} "
        f"terminal_summary_digest={summary_digest!r}"
    )


def _safe_summary_text(text: str | None) -> str:
    """脱敏并截断 smoke 失败摘要文本。

    :param text: Host public error message。
    :returns: 安全短文本。
    :raises Exception: 不主动抛出异常。
    """

    if text is None or text.strip() == "":
        return "none"
    secret_markers = ("api_key", "apikey", "authorization", "bearer ", "token", "secret")
    lowered = text.lower()
    if any(marker in lowered for marker in secret_markers):
        return "<redacted>"
    max_length = 240
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


async def _next_terminal_for_run(
    iterator: AsyncIterator[HostEvent], run_id: str
) -> HostEvent:
    """读取指定 Run 的 terminal HostEvent。

    :param iterator: HostEvent iterator。
    :param run_id: Run id。
    :returns: terminal HostEvent。
    :raises TimeoutError: 超时未收到 terminal event 时抛出。
    """

    async def read() -> HostEvent:
        """读取 iterator 直到目标 Run terminal。

        :returns: terminal HostEvent。
        :raises RuntimeError: iterator 结束前没有 terminal event 时抛出。
        """

        async for event in iterator:
            if event.run_id == run_id and event.terminal_status is not None:
                return event
        raise RuntimeError("HostEvent iterator ended before terminal event")

    return await asyncio.wait_for(read(), timeout=_TERMINAL_TIMEOUT_SECONDS)


def _new_smoke_run_id() -> str:
    """生成本次手工 smoke 的调用方请求批次 id。

    :returns: 用于 stdout 和 client request id 的唯一短 id。
    :raises Exception: 不主动抛出异常。
    """

    return uuid4().hex[:12]


def _round_client_request_id(smoke_run_id: str, round_index: int) -> str:
    """构造每轮 Host command 的幂等请求 id。

    :param smoke_run_id: 本次手工 smoke 批次 id。
    :param round_index: 轮次序号。
    :returns: 本轮 ``client_request_id``。
    :raises Exception: 不主动抛出异常。
    """

    return f"{_CLIENT_REQUEST_PREFIX}-{smoke_run_id}-round-{round_index}"


def _round1_prompt() -> str:
    """构造第一轮工具确认 prompt。

    :returns: 第一轮用户 prompt。
    :raises Exception: 不主动抛出异常。
    """

    return (
        f"请调用 {_TOOL_NAME} 查询{_TARGET_COMPANY} {_DEFAULT_PERIOD} "
        f"{_DEFAULT_TOPIC}事实，参数 company={_TARGET_COMPANY}、"
        f"period={_DEFAULT_PERIOD}、topic={_DEFAULT_TOPIC}、"
        f"metric={_DEFAULT_METRIC}、include_pressure=true。\n"
        f"工具返回后，请用一小段话回答，并原样包含工具返回的核对行 "
        f"{_ASSERTION_PREFIX}。"
    )


def _round2_prompt(options: OpenHostOptions) -> str:
    """构造第二轮分组复述与压力 prompt。

    :param options: 本次 smoke 使用的 Host opener options。
    :returns: 第二轮用户 prompt。
    :raises RuntimeError: smoke 未启用 context budget policy 时抛出。
    """

    padding = _compact_pressure_padding(options)
    return (
        f"继续同一个会话，不要调用工具。请把刚才{_TARGET_COMPANY} "
        f"{_DEFAULT_PERIOD} 的息差相关事实按“资产 / 负债 / 息差”三组重排。\n"
        f"回答末尾请原样输出一行 {_ASSERTION_PREFIX}，字段必须仍为 "
        f"marker={_SMOKE_MARKER}、company={_TARGET_COMPANY}、"
        f"period={_DEFAULT_PERIOD}、net_interest_margin={_FACT_NIM}、"
        f"yoy={_FACT_NIM_YOY}。\n"
        "下面是为了触发 Host proactive compact 的人工长上下文："
        f"{padding}"
    )


def _round3_prompt() -> str:
    """构造第三轮 topic shift prompt。

    :returns: 第三轮用户 prompt。
    :raises Exception: 不主动抛出异常。
    """

    return (
        f"我换个问题：{_TARGET_COMPANY} {_DEFAULT_PERIOD} 的不良率是多少？"
        "不要调用工具，只基于你当前可见上下文回答。\n"
        "如果不确定，请明确说不确定；如果能看到已确认事实，请给出不良率。"
    )


def _round4_prompt() -> str:
    """构造第四轮最终一致性核对 prompt。

    :returns: 第四轮用户 prompt。
    :raises Exception: 不主动抛出异常。
    """

    return (
        "回到刚才的息差讨论。请只根据这个会话已经确认过的事实回答：\n"
        f"{_TARGET_COMPANY} {_DEFAULT_PERIOD} 净息差的具体数值是多少？"
        "同比变化是多少？这次确认的数是否与前面工具确认过的数据一致？\n"
        "回答最后必须单独输出一行：\n"
        f"{_ASSERTION_LINE}"
    )


def _compact_pressure_padding(options: OpenHostOptions) -> str:
    """构造预算压力 padding，使总估算值落在 soft / hard threshold 之间。

    :param options: 本次 smoke 使用的 Host opener options。
    :returns: 用于第二轮 prompt 的 padding。
    :raises RuntimeError: smoke 未启用 context budget policy 时抛出。
    """

    policy = options.context_budget_policy
    if policy is None:
        raise RuntimeError("smoke compact pressure requires context budget policy")
    soft_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.soft_threshold_context_ratio,
    )
    hard_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.hard_threshold_context_ratio,
    )
    target_tokens = min(
        soft_threshold_tokens + _COMPACT_PRESSURE_TARGET_EXTRA_TOKENS,
        hard_threshold_tokens - _COMPACT_PRESSURE_HARD_MARGIN_TOKENS,
    )
    pressure_reserve_tokens = _compact_pressure_reserve_tokens(
        context_window_size=policy.context_window_size
    )
    tool_pressure_tokens = _tool_pressure_estimated_tokens()
    prompt_tokens = max(
        _COMPACT_PRESSURE_MIN_PROMPT_TOKENS,
        target_tokens - pressure_reserve_tokens - tool_pressure_tokens,
    )
    return _repeat_to_chars(
        token=_PRESSURE_PAD_TOKEN,
        target_chars=prompt_tokens * DEFAULT_ESTIMATOR_CHARS_PER_TOKEN,
    )


def _threshold_tokens(context_window_size: int, ratio: float) -> int:
    """按 Host context budget ratio 计算阈值 token 数。

    :param context_window_size: 当前模型上下文窗口 token 数。
    :param ratio: 阈值比例。
    :returns: 阈值 token 数。
    :raises Exception: 不主动抛出异常。
    """

    return floor(context_window_size * ratio)


def _compact_pressure_reserve_tokens(*, context_window_size: int) -> int:
    """计算 compact pressure prompt 与工具压力之外预留的估算 token。

    :param context_window_size: 当前模型上下文窗口 token 数。
    :returns: prompt 与工具压力之外预留 token 数。
    :raises Exception: 不主动抛出异常。
    """

    if context_window_size >= _COMPACT_PRESSURE_LARGE_WINDOW_TOKENS:
        return _COMPACT_PRESSURE_RESERVE_TOKENS
    return _COMPACT_PRESSURE_RESERVE_TOKENS


def _tool_pressure_blob() -> str:
    """构造 smoke tool 的确定性大返回片段。

    :returns: 大工具返回文本。
    :raises Exception: 不主动抛出异常。
    """

    return _repeat_to_chars(
        token=_PRESSURE_PAD_TOKEN,
        target_chars=_SMOKE_TOOL_PRESSURE_CHARS,
    )


def _tool_pressure_estimated_tokens() -> int:
    """估算 smoke tool 大返回片段贡献的 token 数。

    :returns: 估算 token 数。
    :raises Exception: 不主动抛出异常。
    """

    return _estimate_chars_as_tokens(_SMOKE_TOOL_PRESSURE_CHARS)


def _estimate_chars_as_tokens(char_count: int) -> int:
    """按 Host conservative estimator 估算字符量对应的 token 数。

    :param char_count: 字符数量。
    :returns: 估算 token 数。
    :raises Exception: 不主动抛出异常。
    """

    return (
        char_count + DEFAULT_ESTIMATOR_CHARS_PER_TOKEN - 1
    ) // DEFAULT_ESTIMATOR_CHARS_PER_TOKEN


def _repeat_to_chars(*, token: str, target_chars: int) -> str:
    """把稳定 token 重复到目标字符量。

    :param token: 重复使用的短文本。
    :param target_chars: 目标字符数。
    :returns: 至少达到目标字符数的文本。
    :raises Exception: 不主动抛出异常。
    """

    line = f"{token} " * max(1, _PRESSURE_LINE_CHARS // len(token))
    repeat_count = max(1, target_chars // len(line) + 1)
    return (line * repeat_count)[:target_chars]


def _assert_tool_state_after_round1(smoke_tool: MockFinanceFactTool) -> None:
    """断言第一轮工具调用状态。

    :param smoke_tool: effective ToolBundle 中恢复出的 mock 工具实例。
    :returns: ``None``。
    :raises RuntimeError: 工具调用次数或 marker 不符合预期时抛出。
    """

    _assert_tool_call_count(smoke_tool, expected=1, label=_ROUND_1_LABEL)
    if smoke_tool.last_marker != _SMOKE_MARKER:
        raise RuntimeError(
            f"{_ROUND_1_LABEL} tool marker mismatch: {smoke_tool.last_marker!r}"
        )


def _assert_tool_call_count(
    smoke_tool: MockFinanceFactTool, *, expected: int, label: str
) -> None:
    """断言工具调用次数。

    :param smoke_tool: effective ToolBundle 中恢复出的 mock 工具实例。
    :param expected: 期望调用次数。
    :param label: 当前轮次标签。
    :returns: ``None``。
    :raises RuntimeError: 工具调用次数不符合预期时抛出。
    """

    if smoke_tool.call_count != expected:
        raise RuntimeError(
            f"{label} tool call count expected {expected}, "
            f"got {smoke_tool.call_count}"
        )


def _assert_round1_answer(result: RoundResult) -> None:
    """检查第一轮 final answer 中可选核对行的数值。

    :param result: 第一轮运行摘要。
    :returns: ``None``。
    :raises RuntimeError: 已输出核对行但数值不匹配时抛出。
    """

    content = _final_answer_content(result)
    if _ASSERTION_PREFIX not in content:
        print("SMOKE OBSERVE round1 assertion line omitted by model")
        return
    normalized = _normalize_answer(content)
    if _normalize_answer(_FACT_NIM) not in normalized:
        raise RuntimeError(f"{_ROUND_1_LABEL} assertion line missed {_FACT_NIM}")
    if _normalize_answer(_FACT_NIM_YOY) not in normalized:
        raise RuntimeError(f"{_ROUND_1_LABEL} assertion line missed {_FACT_NIM_YOY}")


def _observe_round2_assertion(result: RoundResult) -> None:
    """打印第二轮核对行 soft observation。

    :param result: 第二轮运行摘要。
    :returns: ``None``。
    :raises RuntimeError: 已输出核对行但 marker 或数值不匹配时抛出。
    """

    content = _final_answer_content(result)
    if _ASSERTION_PREFIX not in content:
        print(
            f"{_STDOUT_PREFIX_ASSERT_MEMORY_VALUE} "
            f"label={_ROUND_2_LABEL} status=soft-missing"
        )
        return
    _assert_answer_contains_memory_values(content, label=_ROUND_2_LABEL)
    print(
        f"{_STDOUT_PREFIX_ASSERT_MEMORY_VALUE} "
        f"label={_ROUND_2_LABEL} status=pass marker={_SMOKE_MARKER} "
        f"net_interest_margin={_FACT_NIM} yoy={_FACT_NIM_YOY}"
    )


def _assert_round4_answer(result: RoundResult) -> None:
    """硬断言第四轮 final answer 保持已确认息差事实。

    :param result: 第四轮运行摘要。
    :returns: ``None``。
    :raises RuntimeError: marker 或关键数值缺失时抛出。
    """

    _assert_answer_contains_memory_values(
        _final_answer_content(result),
        label=_ROUND_4_LABEL,
    )
    print(
        f"{_STDOUT_PREFIX_ASSERT_MEMORY_VALUE} "
        f"label={_ROUND_4_LABEL} status=pass marker={_SMOKE_MARKER} "
        f"net_interest_margin={_FACT_NIM} yoy={_FACT_NIM_YOY}"
    )


def _assert_answer_contains_memory_values(content: str, *, label: str) -> None:
    """断言回答包含 marker 与两个确定性财务数值。

    :param content: final answer 文本。
    :param label: 当前轮次标签。
    :returns: ``None``。
    :raises RuntimeError: marker、净息差或同比变化缺失时抛出。
    """

    normalized = _normalize_answer(content)
    if _normalize_answer(_SMOKE_MARKER) not in normalized:
        print(
            f"{_STDOUT_PREFIX_ASSERT_MEMORY_VALUE} "
            f"label={label} status=fail missing=marker"
        )
        raise RuntimeError(f"{label} answer missed marker {_SMOKE_MARKER}")
    if _normalize_answer(_FACT_NIM) not in normalized:
        print(
            f"{_STDOUT_PREFIX_ASSERT_MEMORY_VALUE} "
            f"label={label} status=fail missing=net_interest_margin"
        )
        raise RuntimeError(f"{label} answer missed net interest margin {_FACT_NIM}")
    if _normalize_answer(_FACT_NIM_YOY) not in normalized:
        print(
            f"{_STDOUT_PREFIX_ASSERT_MEMORY_VALUE} "
            f"label={label} status=fail missing=yoy"
        )
        raise RuntimeError(f"{label} answer missed yoy {_FACT_NIM_YOY}")


def _normalize_answer(content: str) -> str:
    """归一化回答文本用于 smoke 级精确包含判断。

    :param content: 待归一化文本。
    :returns: 去空白、统一全角百分号并转小写后的文本。
    :raises Exception: 不主动抛出异常。
    """

    without_spaces = "".join(content.split())
    return without_spaces.replace("％", "%").lower()


def _final_answer_content(result: RoundResult) -> str:
    """读取单轮 final answer 内容。

    :param result: 单轮运行摘要。
    :returns: 已去首尾空白的 final answer。
    :raises RuntimeError: 缺少 final answer 时抛出。
    """

    final_answer = result.event.final_answer
    if final_answer is None:
        raise RuntimeError(f"{result.label} missing final answer")
    return final_answer.content.strip()


def _assert_session_open(snapshot: SessionSnapshot, *, label: str) -> None:
    """断言 public session 快照仍为 open。

    :param snapshot: public SessionSnapshot。
    :param label: 当前观测标签。
    :returns: ``None``。
    :raises RuntimeError: Session 已关闭时抛出。
    """

    if snapshot.status is SessionStatus.CLOSED:
        raise RuntimeError(f"{label} session is closed: {snapshot.session_id}")


def _print_session_observation(snapshot: SessionSnapshot, *, label: str) -> None:
    """打印 active / queued 软观测。

    :param snapshot: public SessionSnapshot。
    :param label: 当前观测标签。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    queued_count = len(snapshot.queued_run_ids)
    active_run_id = snapshot.active_run_id if snapshot.active_run_id is not None else "<none>"
    print(
        f"{_STDOUT_PREFIX_SESSION_OBSERVE} label={label} "
        f"status={snapshot.status.value} active_run_id={active_run_id} "
        f"queued_run_count={queued_count}"
    )


def _print_compact_pressure_plan(options: OpenHostOptions) -> None:
    """打印 compact pressure 摘要，不输出完整 pressure prompt。

    :param options: 本次 smoke 使用的 Host opener options。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    policy = options.context_budget_policy
    if policy is None:
        print("SMOKE COMPACT_PRESSURE disabled")
        return
    soft_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.soft_threshold_context_ratio,
    )
    hard_threshold_tokens = _threshold_tokens(
        policy.context_window_size,
        policy.hard_threshold_context_ratio,
    )
    prompt_chars = len(_compact_pressure_padding(options))
    estimated_prompt_tokens = _estimate_chars_as_tokens(prompt_chars)
    estimated_total_pressure_tokens = (
        estimated_prompt_tokens + _tool_pressure_estimated_tokens()
    )
    print(
        "SMOKE COMPACT_PRESSURE "
        f"context_window_tokens={policy.context_window_size} "
        f"soft_threshold_tokens={soft_threshold_tokens} "
        f"hard_threshold_tokens={hard_threshold_tokens} "
        f"tool_pressure_chars={_SMOKE_TOOL_PRESSURE_CHARS} "
        f"prompt_pressure_chars={prompt_chars} "
        f"estimated_prompt_tokens={estimated_prompt_tokens} "
        f"estimated_total_pressure_tokens={estimated_total_pressure_tokens}"
    )


def _print_assembly_diagnostics(
    diagnostics: ServiceOpenHostAssemblyDiagnostics,
    options: OpenHostOptions,
) -> None:
    """打印 Host 调用前 assembly diagnostics。

    :param diagnostics: assembly diagnostics。
    :param options: Host opener options，用于打印 effective tooling policy。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    print("SMOKE ASSEMBLY_MODE runtime")
    print(f"SMOKE ASSEMBLY config_overlay={diagnostics.config_overlay_dir}")
    print(f"SMOKE ASSEMBLY prompt_asset_root={diagnostics.prompt_asset_root}")
    print(
        "SMOKE ASSEMBLY scene_manifest_root="
        f"{diagnostics.scene_manifest_root}"
    )
    print(f"SMOKE ASSEMBLY host_runtime_id={diagnostics.host_runtime_id}")
    print(
        "SMOKE ASSEMBLY execution_profile_id="
        f"{diagnostics.execution_profile_id}"
    )
    print(
        "SMOKE ASSEMBLY model_id="
        f"{diagnostics.model_id} source={diagnostics.model_source}"
    )
    print(
        "SMOKE ASSEMBLY runner_option_hint_id="
        f"{diagnostics.runner_option_hint_id} "
        f"source={diagnostics.runner_option_hint_source}"
    )
    print(
        "SMOKE ASSEMBLY compactor_model_id="
        f"{diagnostics.compactor_model_id}"
    )
    print(
        "SMOKE ASSEMBLY compactor_runner_option_hint_id="
        f"{diagnostics.compactor_runner_option_hint_id}"
    )
    print(f"SMOKE ASSEMBLY lane_name={diagnostics.lane_name}")
    if diagnostics.tool_provider_reports:
        for report in diagnostics.tool_provider_reports:
            print(f"SMOKE ASSEMBLY tool_provider_report={report}")
    else:
        print("SMOKE ASSEMBLY tool_provider_report=<none>")
    print(f"SMOKE ASSEMBLY tool_selection={diagnostics.tool_selection}")
    print(
        "SMOKE ASSEMBLY policy_refs="
        f"context_budget:{diagnostics.context_budget_policy_ref},"
        f"tool_truncation:{diagnostics.tool_truncation_policy}"
    )
    print_duplicate_governance_diagnostics(options)
    print(
        "SMOKE ASSEMBLY agent_policy_sources="
        f"{','.join(diagnostics.agent_policy_sources)}"
    )
    print(
        "SMOKE ASSEMBLY provider_extension_status="
        f"ordinary:{diagnostics.ordinary_provider_extension_status},"
        f"compactor:{diagnostics.compactor_provider_extension_status}"
    )


def _print_round(result: RoundResult) -> None:
    """打印一轮运行摘要。

    :param result: 轮次结果。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    content = _final_answer_content(result)
    preview = content[:_FINAL_PREVIEW_CHARS]
    terminal = (
        result.event.terminal_status.value
        if result.event.terminal_status is not None
        else "none"
    )
    print(
        f"{_STDOUT_PREFIX_ROUND_DONE} "
        f"label={result.label} run_id={result.run_id} "
        f"event_id={result.event.event_id} "
        f"event_sequence={result.event.event_sequence} "
        f"terminal={terminal}"
    )
    print(f"{_STDOUT_PREFIX_FINAL_PREVIEW} label={result.label} content={preview!r}")


def _print_tool_summary(smoke_tool: MockFinanceFactTool) -> None:
    """打印 mock 工具调用观测摘要。

    :param smoke_tool: effective ToolBundle 中恢复出的 mock 工具实例。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    print(f"SMOKE TOOL_CALL_COUNT {smoke_tool.call_count}")
    print(f"SMOKE TOOL_LAST_MARKER {smoke_tool.last_marker!r}")


def _print_compact_summary(options: OpenHostOptions) -> None:
    """打印 compact 观测摘要。

    :param options: 本次 smoke 使用的 Host opener options。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    compact_root = (
        options.compactor_runner_baseline.compact_artifact_root
        if options.compactor_runner_baseline is not None
        else None
    )
    if compact_root is None:
        print(f"{_STDOUT_PREFIX_COMPACT_ARTIFACT_ROOT} <none>")
        print(f"{_STDOUT_PREFIX_COMPACT_ARTIFACT_FILE_COUNT} 0")
        return
    artifacts = (
        tuple(path for path in compact_root.rglob("*") if path.is_file())
        if compact_root.exists()
        else ()
    )
    print(f"{_STDOUT_PREFIX_COMPACT_ARTIFACT_ROOT} {compact_root}")
    print(f"{_STDOUT_PREFIX_COMPACT_ARTIFACT_FILE_COUNT} {len(artifacts)}")
    for path in artifacts[:_COMPACT_ARTIFACT_PRINT_LIMIT]:
        print(f"SMOKE COMPACT_ARTIFACT {path}")


def _format_provider_report(
    provider_id: str,
    spec_id: str,
    version_ref: str | None,
    tool_names: tuple[str, ...],
) -> str:
    """格式化 ToolsDiscovery provider report。

    :param provider_id: provider 自声明身份。
    :param spec_id: provider spec id。
    :param version_ref: provider 版本引用。
    :param tool_names: provider 产出的工具名。
    :returns: stdout 友好报告行。
    :raises Exception: 不主动抛出异常。
    """

    version = "<none>" if version_ref is None else version_ref
    names = "<none>" if not tool_names else ",".join(sorted(tool_names))
    return f"provider={provider_id},spec={spec_id},version={version},tools={names}"


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口。

    :param argv: 命令行参数；为 ``None`` 时读取 ``sys.argv[1:]``。
    :returns: 进程退出码。
    :raises Exception: 不主动抛出；异常会被转换为退出码 1。
    """

    args = parse_args(sys.argv[1:] if argv is None else argv)
    configure(level=args.log_level)
    try:
        return asyncio.run(run_smoke(args, os.environ))
    except Exception as exc:
        print(f"SMOKE FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
