"""人工观察 Host public 多轮闭环的 DeepSeek smoke 脚本。

本脚本不是 pytest，也不是稳定 CI gate。它用于人工运行并观察真实生产
接线：调用方只通过 ``open_host(options)`` 返回的 Host public handle
创建 / 读取 Session、提交多轮 prompt、订阅 Session 级 HostEvent，并观察
DeepSeek ordinary runner、DeepSeek compactor、ToolRuntime、memory catch-up
与 proactive compact 是否按日志和 stdout 摘要串起来。

脚本不会输出 API key、headers、完整 prompt 或完整 provider payload。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys
import threading
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_outcome import (
    BatchToolExecutionOutcome,
    BatchToolExecutionRecord,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.engine import AgentPolicy, AgentRunRequest, EngineRunOutcomeFinalAnswer
from dayu.engine import run_agent_and_wait
from dayu.engine.contracts.messages import AgentMessageRole, SystemMessage, UserMessage
from dayu.engine.contracts.runner_spec import (
    DeepSeekThinkingExtension,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.host import (
    CompactorExecutionBaseline,
    EnsureSessionRequest,
    FollowupBehavior,
    Host,
    HostCallContext,
    HostEvent,
    HostEventKind,
    HostToolingOptions,
    OpenHostOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    SubmitFollowupRequest,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
    open_host,
)
from dayu.host.api import AuthorizationClaim
from dayu.host.compaction import (
    CompactInputRange,
    CompactionCandidate,
    CompactionRequest,
    ContextCompactor,
    EpisodeSummaryCandidate,
    PinnedPatchOperation,
    PinnedStatePatchCandidate,
    PinnedStringTupleFieldPatch,
    PinnedTextFieldPatch,
    PreservationEvidence,
)
from dayu.host.context_policy import default_context_budget_policy
from dayu.host.local_proxy import DefaultLocalEngineWorkerFactory
from dayu.host.memory import default_memory_projection_policy
from dayu.runtime.log import LogLevel, configure

_DEEPSEEK_ENV_VAR = "DEEPSEEK_API_KEY"
_DEEPSEEK_ENDPOINT = "https://api.deepseek.com/chat/completions"
_DEEPSEEK_MODEL = "deepseek-v4-flash"
_SMOKE_TOOL_NAME = "record_smoke_fact"
_SMOKE_MARKER = "DAYU_MEMORY_ALPHA"
_SMOKE_CLIENT_REQUEST_PREFIX = "manual-smoke"
_DEFAULT_TIMEOUT_SECONDS = 90.0
_COMPACTOR_TIMEOUT_SECONDS = 120.0
_TOOL_TIMEOUT_SECONDS = 8.0
_LANE_CAPACITY = 1
_CONTEXT_WINDOW_SIZE = 900
_RESERVED_OUTPUT_TOKENS = 120
_HARD_THRESHOLD_TOKENS = 760
_SAFETY_MARGIN_RATIO = 0.25
_PROMPT_PAD_REPEAT = 90
_FINAL_PREVIEW_CHARS = 500


@dataclass(frozen=True, slots=True)
class SmokeArgs:
    """命令行参数。

    :param work_dir: smoke 运行目录。
    :param log_level: Dayu 日志级别。
    :param keep_workspace: 是否保留运行目录。
    """

    work_dir: pathlib.Path
    log_level: LogLevel
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


class _NeverCancelledToken:
    """人工 smoke compactor 使用的未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终为 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终为 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终为 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None


class _CompactorRejectingToolExecutor:
    """compactor LLM 不应调用工具的 executor。"""

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """返回工具误调用失败结果。

        :param request: 批式工具请求。
        :returns: 与输入 calls 对应的失败 outcome。
        :raises Exception: 不主动抛出异常。
        """

        return BatchToolExecutionOutcome(
            records=tuple(
                BatchToolExecutionRecord(
                    tool_call_id=call.tool_call_id,
                    outcome=ToolFailedOutcome(
                        result=ToolResultFailure(
                            ok=False,
                            error="compact_tool_call_forbidden",
                            message="manual smoke compactor does not expose tools",
                            hint=None,
                            meta=None,
                        )
                    ),
                )
                for call in request.calls
            )
        )


class DeepSeekContextCompactor(ContextCompactor):
    """调用 DeepSeek 的 Host context compactor adapter。

    :param runner_spec: compactor RunnerSpec。
    :param runner_options: compactor RunnerCallOptions。
    """

    def __init__(
        self, runner_spec: RunnerSpec, runner_options: RunnerCallOptions
    ) -> None:
        """初始化 compactor。

        :param runner_spec: compactor RunnerSpec。
        :param runner_options: compactor RunnerCallOptions。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._runner_spec = runner_spec
        self._runner_options = runner_options
        self.call_count = 0
        self.last_summary: str | None = None

    def compact(self, request: CompactionRequest) -> CompactionCandidate:
        """调用 DeepSeek 生成摘要并映射为 Host typed candidate。

        :param request: Host compaction request。
        :returns: compaction candidate。
        :raises RuntimeError: DeepSeek compactor 未返回摘要或执行失败时抛出。
        """

        self.call_count += 1
        summary = self._run_summary(request)
        self.last_summary = summary
        return _candidate_from_summary(request, summary)

    def _run_summary(self, request: CompactionRequest) -> str:
        """在线程中执行异步 compactor runner。

        :param request: Host compaction request。
        :returns: DeepSeek 摘要文本。
        :raises RuntimeError: 线程超时、执行失败或未返回摘要时抛出。
        """

        result_box: list[str] = []
        error_box: list[BaseException] = []

        def target() -> None:
            """线程入口。

            :returns: ``None``。
            :raises Exception: 线程内异常会被记录到 ``error_box``。
            """

            try:
                result_box.append(asyncio.run(self._run_summary_async(request)))
            except BaseException as exc:
                error_box.append(exc)

        thread = threading.Thread(target=target, name="host-public-smoke-compactor")
        thread.start()
        thread.join(timeout=_COMPACTOR_TIMEOUT_SECONDS)
        if thread.is_alive():
            raise RuntimeError("DeepSeek compactor timed out")
        if error_box:
            raise RuntimeError(f"DeepSeek compactor failed: {error_box[0]}")
        if not result_box:
            raise RuntimeError("DeepSeek compactor returned no summary")
        return result_box[0]

    async def _run_summary_async(self, request: CompactionRequest) -> str:
        """异步调用 DeepSeek 生成 compact 摘要。

        :param request: Host compaction request。
        :returns: 摘要文本。
        :raises RuntimeError: 未返回 final answer 或内容为空时抛出。
        """

        outcome = await run_agent_and_wait(
            AgentRunRequest(
                run_id=f"manual-compact-{request.run_id}",
                session_id=request.session_id,
                messages=(
                    SystemMessage(
                        role=AgentMessageRole.SYSTEM,
                        content=(
                            "你是 Dayu Host 手工 smoke 的上下文压缩器。"
                            "只输出一段不超过 40 字的中文摘要，保留用户目标、"
                            "工具事实标记和后续动作。"
                        ),
                    ),
                    UserMessage(
                        role=AgentMessageRole.USER,
                        content=(
                            "当前输入摘要："
                            f"{request.current_message_summary.summary_text}"
                        ),
                    ),
                ),
                disable_tools=True,
                runner_spec=self._runner_spec,
                runner_options=self._runner_options,
                agent_policy=AgentPolicy(
                    max_iterations=1,
                    continuation_max_attempts=0,
                    allow_tool_calls=False,
                    tool_execution_timeout_seconds=_TOOL_TIMEOUT_SECONDS,
                ),
                tool_schemas=(),
                tool_executor=_CompactorRejectingToolExecutor(),
                cancellation_token=_NeverCancelledToken(),
            )
        )
        if not isinstance(outcome, EngineRunOutcomeFinalAnswer):
            raise RuntimeError("DeepSeek compactor did not return final answer")
        content = outcome.content.strip()
        if content == "":
            raise RuntimeError("DeepSeek compactor returned empty summary")
        return content


class SmokeFactTool:
    """记录固定 smoke fact 的 mock business tool。"""

    def __init__(self) -> None:
        """初始化工具调用观测状态。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.call_count = 0
        self.last_marker: str | None = None

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """返回固定工具事实。

        :param call: 工具调用请求。
        :param context: 批式执行上下文。
        :returns: 成功工具 outcome。
        :raises Exception: 不主动抛出异常。
        """

        del call, context
        self.call_count += 1
        self.last_marker = _SMOKE_MARKER
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={
                    "marker": _SMOKE_MARKER,
                    "fact": "manual-smoke-tool-fact",
                    "note": "This fact should be visible to later Host runs.",
                },
                meta=None,
            )
        )


def parse_args(argv: Sequence[str]) -> SmokeArgs:
    """解析命令行参数。

    :param argv: 不含程序名的参数序列。
    :returns: 解析后的参数。
    :raises SystemExit: argparse 在参数非法时抛出。
    """

    parser = argparse.ArgumentParser(
        description="Run manual Host public multi-turn DeepSeek smoke."
    )
    parser.add_argument(
        "--work-dir",
        default=None,
        help="运行目录；默认 workspace/tmp/host_public_multiturn_smoke/latest",
    )
    parser.add_argument(
        "--log-level",
        choices=tuple(level.name for level in LogLevel),
        default=LogLevel.VERBOSE.name,
        help="Dayu 日志级别，默认 VERBOSE。",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="保留运行目录。当前脚本默认也不删除目录，该参数只用于输出提示。",
    )
    namespace = parser.parse_args(list(argv))
    work_dir_text: str | None = namespace.work_dir
    log_level_text: str = namespace.log_level
    keep_workspace: bool = namespace.keep_workspace
    work_dir = (
        pathlib.Path(work_dir_text)
        if work_dir_text is not None
        else pathlib.Path("workspace/tmp/host_public_multiturn_smoke/latest")
    )
    return SmokeArgs(
        work_dir=work_dir,
        log_level=LogLevel[log_level_text],
        keep_workspace=keep_workspace,
    )


async def run_smoke(args: SmokeArgs, env: Mapping[str, str]) -> int:
    """运行 Host public 多轮手工 smoke。

    :param args: smoke 参数。
    :param env: 环境变量映射。
    :returns: 进程退出码。
    :raises Exception: Host public path 或 DeepSeek 调用失败时向上抛出。
    """

    api_key = env.get(_DEEPSEEK_ENV_VAR)
    if api_key is None or api_key.strip() == "":
        print(f"SMOKE ERROR missing env {_DEEPSEEK_ENV_VAR}", file=sys.stderr)
        return 2

    args.work_dir.mkdir(parents=True, exist_ok=True)
    options, compactor, smoke_tool = _open_options(args.work_dir, api_key.strip())
    smoke_run_id = _new_smoke_run_id()

    print("SMOKE START Host public multi-turn DeepSeek")
    print(f"SMOKE WORK_DIR {args.work_dir}")
    print(f"SMOKE RUN_ID {smoke_run_id}")
    print("SMOKE CONTRACT open_host -> ensure_session -> submit_followup -> watch")
    print("SMOKE LOG_LEVEL", args.log_level.name)

    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        watcher = host.watch_session_events(session.session_id)
        print(f"SMOKE SESSION session_id={session.session_id}")

        first = await _run_round(
            host=host,
            watcher=watcher,
            session_id=session.session_id,
            label="round1-tool-fact",
            client_request_id=_round_client_request_id(smoke_run_id, 1),
            prompt=(
                "请调用工具 record_smoke_fact 记录 smoke fact。"
                "工具完成后，用一句话说明你已经收到工具事实。"
            ),
            tool_names=frozenset({_SMOKE_TOOL_NAME}),
        )
        _print_round(first)

        second = await _run_round(
            host=host,
            watcher=watcher,
            session_id=session.session_id,
            label="round2-memory-and-compact",
            client_request_id=_round_client_request_id(smoke_run_id, 2),
            prompt=_memory_compact_prompt(),
            tool_names=frozenset(),
        )
        _print_round(second)

        third = await _run_round(
            host=host,
            watcher=watcher,
            session_id=session.session_id,
            label="round3-after-compact-continuity",
            client_request_id=_round_client_request_id(smoke_run_id, 3),
            prompt=(
                "继续同一个会话。请根据你可见的历史、memory 或 compact "
                f"摘要，说明是否仍能看到标记 {_SMOKE_MARKER}。"
            ),
            tool_names=frozenset(),
        )
        _print_round(third)

        final_session = await host.get_session(session.session_id)
        print(f"SMOKE SESSION_STATUS {final_session.status.value}")

    _print_tool_summary(smoke_tool)
    _print_compact_summary(args.work_dir, compactor)
    print("SMOKE PASS public Host handle completed three-turn closure")
    if args.keep_workspace:
        print("SMOKE WORKSPACE_KEPT true")
    else:
        print("SMOKE WORKSPACE_KEPT true  # manual smoke always keeps artifacts")
    return 0


def _open_options(
    work_dir: pathlib.Path, api_key: str
) -> tuple[OpenHostOptions, DeepSeekContextCompactor, SmokeFactTool]:
    """构造 open_host options 与 compactor。

    :param work_dir: 运行目录。
    :param api_key: DeepSeek API key。
    :returns: OpenHostOptions、compactor 与 smoke tool。
    :raises ValueError: typed options 字段非法时由底层抛出。
    """

    runner_spec = _deepseek_runner_spec(api_key, supports_tool_calling=True)
    compactor_runner_spec = _deepseek_runner_spec(api_key, supports_tool_calling=False)
    runner_options = RunnerCallOptions(
        temperature=0.0,
        max_tokens=512,
        top_p=None,
        stream=True,
    )
    compactor = DeepSeekContextCompactor(
        compactor_runner_spec,
        runner_options,
    )
    smoke_tool = SmokeFactTool()
    return (
        OpenHostOptions(
            db_path=work_dir / "host.sqlite3",
            artifact_root=work_dir / "artifacts",
            create_parent_dirs=True,
            sqlite_busy_timeout_seconds=2.0,
            sqlite_write_busy_retry_count=8,
            sqlite_write_retry_initial_delay_seconds=0.005,
            sqlite_write_retry_backoff_multiplier=1.5,
            sqlite_write_retry_max_delay_seconds=0.05,
            payload_inline_threshold_bytes=4096,
            lane_db_path=work_dir / "lane.sqlite3",
            lane_name="manual-host-public-multiturn-smoke",
            lane_capacity=_LANE_CAPACITY,
            lane_default_timeout_seconds=5.0,
            lane_claim_ttl_seconds=10.0,
            lane_heartbeat_interval_seconds=1.0,
            worker_startup_timeout_seconds=10.0,
            dispatch_poll_interval_seconds=0.05,
            ordinary_run_baseline=OrdinaryRunExecutionBaseline(
                runner_spec=runner_spec,
                runner_options=runner_options,
                agent_policy=AgentPolicy(
                    max_iterations=3,
                    continuation_max_attempts=0,
                    allow_tool_calls=True,
                    tool_execution_timeout_seconds=_TOOL_TIMEOUT_SECONDS,
                ),
            ),
            worker_factory=DefaultLocalEngineWorkerFactory(),
            tooling_options=_tooling_options(smoke_tool),
            context_budget_policy=default_context_budget_policy(
                context_window_size=_CONTEXT_WINDOW_SIZE,
                reserved_output_tokens=_RESERVED_OUTPUT_TOKENS,
                hard_threshold_tokens=_HARD_THRESHOLD_TOKENS,
                safety_margin_ratio=_SAFETY_MARGIN_RATIO,
                minimum_protection_tokens=1,
                max_proactive_compactions_per_run=1,
                policy_ref="manual-host-public-smoke-policy",
            ),
            compactor_baseline=CompactorExecutionBaseline(
                context_compactor=compactor,
                compactor_runner_spec=compactor_runner_spec,
                compactor_runner_options=runner_options,
                compactor_policy_ref="manual-host-public-smoke-deepseek-compactor",
                compact_artifact_root=work_dir / "compact-artifacts",
                compact_artifact_create_parent_dirs=True,
            ),
            memory_projection_policy=default_memory_projection_policy(),
            memory_projection_catchup_batch_size=128,
            enable_truncation_manager=True,
        ),
        compactor,
        smoke_tool,
    )


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

    return f"{_SMOKE_CLIENT_REQUEST_PREFIX}-{smoke_run_id}-round-{round_index}"


def _deepseek_runner_spec(api_key: str, *, supports_tool_calling: bool) -> RunnerSpec:
    """构造 DeepSeek RunnerSpec。

    :param api_key: DeepSeek API key。
    :param supports_tool_calling: 是否启用工具调用。
    :returns: RunnerSpec。
    :raises ValueError: RunnerSpec 字段非法时由底层抛出。
    """

    return RunnerSpec(
        provider="deepseek",
        model=_DEEPSEEK_MODEL,
        endpoint=_DEEPSEEK_ENDPOINT,
        api_key_ref=_DEEPSEEK_ENV_VAR,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        supports_tool_calling=supports_tool_calling,
        supports_streaming=True,
        supports_stream_usage=True,
        default_timeout_seconds=_DEFAULT_TIMEOUT_SECONDS,
        max_retries=0,
        provider_request=DeepSeekThinkingExtension(enabled=True),
        stream_idle_timeout_seconds=30.0,
        stream_idle_heartbeat_seconds=10.0,
    )


def _tooling_options(smoke_tool: SmokeFactTool) -> HostToolingOptions:
    """构造手工 smoke 的业务工具装配。

    :param smoke_tool: 记录 smoke fact 的工具实例。
    :returns: HostToolingOptions。
    :raises ValueError: 工具定义非法时由底层抛出。
    """

    return HostToolingOptions(
        business_tool_bundle=ToolBundle(
            definitions=(_smoke_tool_definition(smoke_tool),)
        ),
        source_refs=(
            ToolBundleSourceRef(
                source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
                source_id="manual-host-public-smoke",
            ),
        ),
        wait_adapter_registry=None,
    )


def _smoke_tool_definition(smoke_tool: SmokeFactTool) -> ToolDefinition:
    """构造 smoke fact 工具定义。

    :param smoke_tool: 记录 smoke fact 的工具实例。
    :returns: ToolDefinition。
    :raises ValueError: schema 字段非法时由底层抛出。
    """

    properties = {
        "marker": {
            "type": "string",
            "description": "Smoke marker to record.",
        }
    }
    return ToolDefinition(
        name=_SMOKE_TOOL_NAME,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=_SMOKE_TOOL_NAME,
                description=(
                    "Record the fixed Dayu Host public smoke memory marker."
                ),
                parameters=ToolParametersSchema(
                    type="object",
                    properties=properties,
                    required=("marker",),
                    additional_properties=False,
                ),
            ),
        ),
        callable=smoke_tool,
        truncate=None,
        display=None,
        tags=("manual-smoke",),
    )


def _ensure_request() -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :returns: EnsureSessionRequest。
    :raises ValueError: 字段非法时由底层抛出。
    """

    return EnsureSessionRequest(
        scope="workspace",
        slot_key="manual-host-public-multiturn-smoke",
        metadata=(),
    )


def _followup_request(
    *,
    session_id: str,
    client_request_id: str,
    prompt: str,
    tool_names: frozenset[str] | None,
) -> SubmitFollowupRequest:
    """构造 public submit_followup 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :param prompt: 用户 prompt。
    :param tool_names: 本轮工具选择；空集合表示禁用业务工具。
    :returns: SubmitFollowupRequest。
    :raises ValueError: 请求字段非法时由底层抛出。
    """

    return SubmitFollowupRequest(
        context=_host_context(client_request_id),
        session_id=session_id,
        client_request_id=client_request_id,
        system_prompt=(
            "你正在参与 Dayu Host public contract 手工 smoke。"
            "回答可以自然变化，但不要输出密钥、headers 或完整内部 payload。"
        ),
        user_prompt=prompt,
        tool_names=tool_names,
        runner_spec=None,
        runner_options=None,
        agent_policy=None,
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def _host_context(request_id: str) -> HostCallContext:
    """构造 HostCallContext。

    :param request_id: request id。
    :returns: HostCallContext。
    :raises ValueError: 字段非法时由底层抛出。
    """

    return HostCallContext(
        actor="manual-smoke-operator",
        source="utils.smoke_host_public_multiturn",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="manual-smoke"),),
        operation_context=OperationContext(
            operation_name="host_public_multiturn_smoke",
            operation_kind="manual_smoke",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="p10_5_public_contract",
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
    prompt: str,
    tool_names: frozenset[str] | None,
) -> RoundResult:
    """提交一轮 prompt 并等待 terminal HostEvent。

    :param host: public Host handle。
    :param watcher: session-level HostEvent iterator。
    :param session_id: Session id。
    :param label: 轮次标签。
    :param client_request_id: 幂等请求 id。
    :param prompt: 用户 prompt。
    :param tool_names: 本轮工具选择。
    :returns: RoundResult。
    :raises RuntimeError: terminal 不是 succeeded 或缺少 final answer 时抛出。
    """

    print(f"SMOKE ROUND_START label={label}")
    accepted = await host.submit_followup(
        session_id,
        _followup_request(
            session_id=session_id,
            client_request_id=client_request_id,
            prompt=prompt,
            tool_names=tool_names,
        ),
    )
    event = await _next_terminal_for_run(watcher, accepted.accepted_run_id)
    if event.kind is not HostEventKind.SUCCEEDED:
        raise RuntimeError(
            f"round {label} terminal kind is {event.kind.value}; "
            f"run_id={accepted.accepted_run_id}"
        )
    if event.final_answer is None or event.final_answer.content.strip() == "":
        raise RuntimeError(f"round {label} returned empty final answer")
    return RoundResult(label=label, run_id=accepted.accepted_run_id, event=event)


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
        :raises StopAsyncIteration: iterator 结束时由底层抛出。
        """

        async for event in iterator:
            if event.run_id == run_id and event.terminal_status is not None:
                return event
        raise RuntimeError("HostEvent iterator ended before terminal event")

    return await asyncio.wait_for(read(), timeout=180.0)


def _memory_compact_prompt() -> str:
    """构造触发 memory / compact 的第二轮 prompt。

    :returns: prompt 文本。
    :raises Exception: 不主动抛出异常。
    """

    padding = " ".join(f"DAYU_CONTEXT_PAD_{index:03d}" for index in range(_PROMPT_PAD_REPEAT))
    return (
        f"上一轮如果工具事实已进入 memory，请观察是否能看到标记 {_SMOKE_MARKER}。"
        "请用两句话回答：第一句说明你看到的上一轮事实，第二句说明这是第二轮。"
        "下面是为了触发 Host proactive compact 的人工长上下文："
        f"{padding}"
    )


def _print_round(result: RoundResult) -> None:
    """打印一轮运行摘要。

    :param result: 轮次结果。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    final_answer = result.event.final_answer
    content = "" if final_answer is None else final_answer.content.strip()
    preview = content[:_FINAL_PREVIEW_CHARS]
    print(
        "SMOKE ROUND_DONE "
        f"label={result.label} run_id={result.run_id} "
        f"event_id={result.event.event_id} "
        f"event_sequence={result.event.event_sequence} "
        f"terminal={result.event.terminal_status.value if result.event.terminal_status is not None else 'none'}"
    )
    print(f"SMOKE FINAL_PREVIEW label={result.label} content={preview!r}")


def _print_tool_summary(smoke_tool: SmokeFactTool) -> None:
    """打印工具调用观测摘要。

    :param smoke_tool: smoke tool 实例。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    print(f"SMOKE TOOL_CALL_COUNT {smoke_tool.call_count}")
    print(f"SMOKE TOOL_LAST_MARKER {smoke_tool.last_marker!r}")
    if smoke_tool.call_count == 0:
        print(
            "SMOKE OBSERVE tool was not called; memory tool fact path was not "
            "exercised by this model run"
        )


def _print_compact_summary(work_dir: pathlib.Path, compactor: DeepSeekContextCompactor) -> None:
    """打印 compact 观测摘要。

    :param work_dir: smoke 运行目录。
    :param compactor: DeepSeek compactor。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    compact_root = work_dir / "compact-artifacts"
    artifacts = tuple(
        path for path in compact_root.rglob("*") if path.is_file()
    ) if compact_root.exists() else ()
    print(f"SMOKE COMPACT_CALL_COUNT {compactor.call_count}")
    print(f"SMOKE COMPACT_LAST_SUMMARY {compactor.last_summary!r}")
    print(f"SMOKE COMPACT_ARTIFACT_ROOT {compact_root}")
    print(f"SMOKE COMPACT_ARTIFACT_FILE_COUNT {len(artifacts)}")
    for path in artifacts[:10]:
        print(f"SMOKE COMPACT_ARTIFACT {path}")


def _candidate_from_summary(
    request: CompactionRequest, summary: str
) -> CompactionCandidate:
    """把 DeepSeek 摘要映射为 Host 可校验 compaction candidate。

    :param request: compaction request。
    :param summary: DeepSeek 摘要。
    :returns: CompactionCandidate。
    :raises ValueError: candidate 字段非法时由底层抛出。
    """

    evidence = _preservation_evidence(request)
    evidence_refs = tuple(item.evidence_id for item in evidence)
    return CompactionCandidate(
        candidate_id=f"manual-compact:{request.run_id}",
        episode_summary_candidate=EpisodeSummaryCandidate(
            candidate_id=f"manual-summary:{request.run_id}",
            episode_title="Manual Host public smoke summary",
            goal=summary,
            completed_actions=("DeepSeek compactor produced summary",),
            confirmed_fact_refs=request.verified_fact_refs,
            confirmed_fact_summaries=_confirmed_fact_summaries(request),
            user_constraints=("preserve manual smoke continuity",),
            open_questions=("observe next public run",),
            next_step="continue manual public smoke",
            tool_finding_refs=request.tool_fact_refs,
            source_event_refs=request.input_event_refs,
            evidence_refs=evidence_refs,
        ),
        pinned_state_patch_candidate=PinnedStatePatchCandidate(
            candidate_id=f"manual-pinned:{request.run_id}",
            current_goal=PinnedTextFieldPatch(
                operation=PinnedPatchOperation.REPLACE,
                value=summary,
                evidence_refs=evidence_refs,
            ),
            confirmed_subjects=PinnedStringTupleFieldPatch(
                operation=PinnedPatchOperation.REPLACE,
                value=(
                    "subject:"
                    f"{request.current_message_summary.current_user_input_ref}",
                ),
                evidence_refs=evidence_refs,
            ),
            user_constraints=PinnedStringTupleFieldPatch(
                operation=PinnedPatchOperation.REPLACE,
                value=("manual-smoke-continuity",),
                evidence_refs=evidence_refs,
            ),
            open_questions=PinnedStringTupleFieldPatch(
                operation=PinnedPatchOperation.REPLACE,
                value=("observe-next-run",),
                evidence_refs=evidence_refs,
            ),
        ),
        preservation_evidence=evidence,
        retained_current_user_input_ref=(
            request.current_message_summary.current_user_input_ref
        ),
        preserved_input_event_refs=request.input_event_refs,
        preserved_tool_fact_refs=request.tool_fact_refs,
        preserved_verified_fact_refs=request.verified_fact_refs,
        dropped_ranges=(),
        summarized_ranges=_summarized_ranges(request),
        budget_after_compact=max(
            0, request.budget_before_compact.estimated_input_tokens // 2
        ),
    )


def _preservation_evidence(
    request: CompactionRequest,
) -> tuple[PreservationEvidence, ...]:
    """构造 preservation evidence。

    :param request: compaction request。
    :returns: preservation evidence。
    :raises ValueError: evidence 字段非法时由底层抛出。
    """

    return (
        PreservationEvidence(
            evidence_id=f"manual-evidence:{request.run_id}",
            input_event_refs=request.input_event_refs,
            tool_fact_refs=request.tool_fact_refs,
            memory_snapshot_cursor=request.memory_snapshot_cursor,
            compact_input_range=_range_for_request(request),
        ),
    )


def _range_for_request(request: CompactionRequest) -> CompactInputRange | None:
    """构造 compact input range。

    :param request: compaction request。
    :returns: compact range；无输入事件时为 ``None``。
    :raises ValueError: range 字段非法时由底层抛出。
    """

    if len(request.input_event_refs) == 0:
        return None
    return CompactInputRange(
        range_ref=f"manual-range:{request.run_id}:inputs",
        start_input_ref=request.input_event_refs[0],
        end_input_ref=request.input_event_refs[-1],
    )


def _summarized_ranges(request: CompactionRequest) -> tuple[CompactInputRange, ...]:
    """构造 summarized ranges。

    :param request: compaction request。
    :returns: summarized ranges。
    :raises ValueError: range 字段非法时由底层抛出。
    """

    if len(request.older_raw_turn_refs) == 0:
        return ()
    return (
        CompactInputRange(
            range_ref=f"manual-range:{request.run_id}:older",
            start_input_ref=request.older_raw_turn_refs[0],
            end_input_ref=request.older_raw_turn_refs[-1],
        ),
    )


def _confirmed_fact_summaries(request: CompactionRequest) -> tuple[str, ...]:
    """构造 confirmed fact summaries。

    :param request: compaction request。
    :returns: fact summaries。
    :raises Exception: 不主动抛出异常。
    """

    if len(request.verified_fact_refs) == 0:
        return ("manual smoke has no verified facts in compact input",)
    return tuple(f"verified:{fact_ref}" for fact_ref in request.verified_fact_refs)


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
