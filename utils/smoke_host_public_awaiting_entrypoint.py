"""Host public entrypoint 等待态 smoke 脚本。"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dayu.contracts import (
    AsyncDirectToolExecutionCapability,
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolAwaitKind,
    ToolAwaitSpec,
    ToolAwaitingOutcome,
    ToolBundle,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
    ToolCallRequest,
    ToolDefinition,
    ToolExecutionOutcome,
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolResultSuccess,
    ToolSchema,
)
from dayu.engine import (
    AgentFallbackMode,
    AgentPolicy,
    AgentRunRequest,
    AssistantToolCallBatchSnapshot,
    AwaitingToolExecutionRecord,
    ClientCorrelationPolicy,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    FinishReason,
    RUN_SUSPENDED_REASON_TOOL_AWAITING,
    RunSuspendedData,
    RunnerCallOptions,
    RunnerSpec,
    ToolAwaitingData,
)
from dayu.host import (
    AttemptDispatchSnapshot,
    AuthorizationClaim,
    EnsureSessionRequest,
    FollowupBehavior,
    HostCallContext,
    HostTerminalStatus,
    HostToolingOptions,
    LocalEngineWorker,
    LocalWorkerHandle,
    OpenHostOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    OutboxTerminalCursor,
    ReadOutboxTerminalItemsRequest,
    ResolveWaitCompletedOutcome,
    RunStatus,
    WaitAdapterKey,
    open_host,
)
from dayu.host.memory import default_memory_projection_policy
from dayu.host.wait_adapter import (
    WaitAdapterBinding,
    WaitAdapterRegistry,
    WaitAdapterSnapshot,
    WaitExternalJobLifecycleResult,
    WaitExternalJobLifecycleUnsupported,
    WaitExternalJobRefSource,
    WaitPollAdapterRegistration,
    WaitPollAdapterRegistry,
    WaitPollNotReady,
    WaitPollReady,
    WaitPollerRuntimePolicy,
    WaitPollResult,
    WaitResumePolicy,
)
from dayu.runtime.assembly import (
    ExecutionProfileCompatibilityDiagnostic,
    MergedAgentPolicyConfig,
    RuntimeSelectionDiagnostic,
    RunnerOptionHintSelection,
)
from dayu.runtime.config_loader import (
    AgentPolicyConfig,
    BinaryBytesLimitConfig,
    CompactorBaselineConfig,
    ContextBudgetConfig,
    ExecutionBaselineConfig,
    ExecutionProfileConfig,
    HostRuntimeProfileConfig,
    ListItemsLimitConfig,
    MemoryProjectionConfig,
    ModelConfig,
    ModelRuntimeHintsConfig,
    ProcessCapsuleInterruptPolicyConfig,
    RunnerKind,
    RunnerOptionHintConfig,
    RuntimeLaneConfig,
    SQLiteRuntimeConfig,
    TextCharsLimitConfig,
    TextLinesLimitConfig,
    ToolDuplicateGovernanceMessagesConfig,
    ToolDuplicateGovernancePolicyConfig,
    ToolTruncationDefaultLimitsConfig,
    ToolTruncationPolicyConfig,
)
from dayu.runtime.scene_prepare import (
    PreparedSceneInputs,
    SceneSourceKind,
    SceneSourceRef,
    SceneToolSelectionMode,
    SceneToolSelectionResult,
)
from dayu.service.entrypoint_runtime import (
    EntrypointActivity,
    EntrypointActivityStatus,
    EntrypointTerminalSource,
    EntrypointTurnRequest,
    submit_entrypoint_turn_and_wait,
)
from dayu.service.host_assembly import (
    ServiceOpenHostAssemblyDiagnostics,
    ServiceOpenHostAssemblyResult,
    ServiceRunOverrides,
)

_AWAITING_TOOL_NAME = "await_public_smoke_job"
_ADAPTER_KEY = WaitAdapterKey("service.awaiting-smoke")
_NOW = datetime(2026, 7, 5, 0, 0, 0, tzinfo=UTC)
_FINAL_ANSWER = "等待任务已完成，已收到轮询恢复结果。"
_RESUME_TOKEN = "service-awaiting-smoke-token"
_SOURCE_REF = ToolBundleSourceRef(
    source_kind=ToolBundleSourceKind.SERVICE_COMPOSITION,
    source_id="utils.smoke_host_public_awaiting_entrypoint",
    version_ref=None,
)
_DEFAULT_WORKSPACE_PARENT = Path("workspace/tmp")
_DEFAULT_WORKSPACE_PREFIX = "host-public-awaiting-entrypoint-smoke"
_DEFAULT_SLOT_KEY_PREFIX = "manual-smoke-awaiting-entrypoint"
_TERMINAL_TIMEOUT_SECONDS = 5.0
_POLL_INTERVAL_SECONDS = 0.01


@dataclass(frozen=True, slots=True)
class SmokeArgs:
    """解析后的 smoke 参数。"""

    workspace_root: Path
    keep_workspace: bool


async def run_smoke(args: SmokeArgs, env: Mapping[str, str]) -> int:
    """运行 public entrypoint awaiting smoke。

    :param args: smoke 参数。
    :param env: 环境变量映射。
    :returns: 进程退出码。
    :raises RuntimeError: public 行为不符合预期时抛出。
    """

    del env
    poll_adapter = _GatedReadyPollAdapter()
    worker_factory = _AwaitingThenAnswerWorkerFactory()
    options = _open_options(
        args.workspace_root,
        worker_factory=worker_factory,
        poll_adapter=poll_adapter,
    )
    scene_inputs = _scene_inputs()
    host_assembly = _host_assembly(options=options, effective_tool_bundle=_tool_bundle())
    accepted_run_ids: list[str] = []
    activities: list[EntrypointActivity] = []
    waiting_activity_seen = asyncio.Event()

    print("SMOKE START Host public awaiting entrypoint")
    print(f"SMOKE WORKSPACE_ROOT {args.workspace_root}")
    print("SMOKE CONTRACT open_host -> ensure_session -> submit_entrypoint_turn_and_wait")
    print("SMOKE WAIT_RECOVERY production poller via public wait poll adapter registry")

    async with open_host(options) as host:
        session = await host.ensure_session(
            EnsureSessionRequest(
                scope="workspace",
                slot_key=f"{_DEFAULT_SLOT_KEY_PREFIX}-{uuid4().hex[:12]}",
                metadata=(),
            )
        )
        print(f"SMOKE SESSION_ID {session.session_id}")

        def on_activity(activity: EntrypointActivity) -> None:
            """记录 Service activity 并在等待态出现时释放测试检查。

            :param activity: Service 投影后的 activity。
            :returns: ``None``。
            :raises Exception: 不主动抛出异常。
            """

            activities.append(activity)
            if activity.status is EntrypointActivityStatus.WAITING:
                waiting_activity_seen.set()

        submit_task = asyncio.create_task(
            submit_entrypoint_turn_and_wait(
                host,
                request=_turn_request(session_id=session.session_id),
                scene_inputs=scene_inputs,
                host_assembly=host_assembly,
                on_run_accepted=accepted_run_ids.append,
                on_activity=on_activity,
                poll_interval_seconds=_POLL_INTERVAL_SECONDS,
            )
        )
        try:
            await asyncio.wait_for(
                waiting_activity_seen.wait(), timeout=_TERMINAL_TIMEOUT_SECONDS
            )
            _require(len(accepted_run_ids) > 0, message="run was not accepted")
            accepted_run_id = accepted_run_ids[0]
            print(f"SMOKE ACCEPTED_RUN_ID {accepted_run_id}")
            waiting_snapshot = await host.get_run(accepted_run_id)
            _require(
                waiting_snapshot.status is RunStatus.WAITING,
                message=f"run did not enter WAITING: {waiting_snapshot.status}",
            )
            print("SMOKE OBSERVED_WAITING true")

            poll_adapter.open_gate()
            result = await asyncio.wait_for(
                submit_task, timeout=_TERMINAL_TIMEOUT_SECONDS
            )

            _require(
                result.source is EntrypointTerminalSource.LIVE_EVENT,
                message=f"terminal source mismatch: {result.source}",
            )
            _require(
                result.run_id == accepted_run_id,
                message=f"terminal run id mismatch: {result.run_id}",
            )
            _require(
                result.terminal_status is HostTerminalStatus.SUCCEEDED,
                message=f"terminal status mismatch: {result.terminal_status}",
            )
            final_answer = result.final_answer
            if final_answer is None:
                raise RuntimeError("missing final answer")
            _require(final_answer.content.strip() != "", message="blank final answer")
            _require(
                worker_factory.accept_count == 2,
                message=f"worker accept count mismatch: {worker_factory.accept_count}",
            )
            _require(
                poll_adapter.ready_count == 1,
                message=f"poll ready count mismatch: {poll_adapter.ready_count}",
            )
            _require(
                any(
                    activity.status is EntrypointActivityStatus.WAITING
                    for activity in activities
                ),
                message="WAITING activity was not recorded",
            )
            print(f"SMOKE TERMINAL_EVENT_ID {result.terminal_event_id}")
            print("SMOKE TERMINAL_STATUS SUCCEEDED")

            batch = await host.read_outbox_terminal_items(
                session.session_id,
                ReadOutboxTerminalItemsRequest(
                    after=OutboxTerminalCursor(event_sequence=0),
                    seen_terminal_event_ids=(),
                    limit=50,
                ),
            )
            matching_items = tuple(
                item
                for item in batch.items
                if item.run_id == accepted_run_id
                and item.terminal_status is HostTerminalStatus.SUCCEEDED
            )
            _require(
                len(matching_items) == 1,
                message=f"terminal outbox match count mismatch: {len(matching_items)}",
            )
            _require(
                matching_items[0].terminal_event_id == result.terminal_event_id,
                message="terminal outbox event id mismatch",
            )
            print("SMOKE OUTBOX_TERMINAL_MATCH true")
            print(f"SMOKE WORKER_ACCEPT_COUNT {worker_factory.accept_count}")
            print(f"SMOKE POLL_READY_COUNT {poll_adapter.ready_count}")
            print("SMOKE PASS Host public awaiting entrypoint")
            if args.keep_workspace:
                print("SMOKE WORKSPACE_KEPT true  # smoke never deletes Host artifacts")
            return 0
        finally:
            if not submit_task.done():
                submit_task.cancel()
                try:
                    await submit_task
                except asyncio.CancelledError:
                    pass


def parse_args(argv: Sequence[str]) -> SmokeArgs:
    """解析命令行参数。

    :param argv: 不含程序名的参数序列。
    :returns: 解析后的 smoke 参数。
    :raises SystemExit: argparse 在参数非法时抛出。
    """

    parser = argparse.ArgumentParser(
        description="Run Host public awaiting entrypoint smoke."
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
        "--keep-workspace",
        action="store_true",
        help="输出中标记保留 workspace；脚本不会删除 Host/runtime artifacts。",
    )
    namespace = parser.parse_args(list(argv))
    workspace_root_text: str | None = namespace.workspace_root
    keep_workspace: bool = namespace.keep_workspace
    return SmokeArgs(
        workspace_root=_resolve_workspace_root(workspace_root_text),
        keep_workspace=keep_workspace,
    )


def _resolve_workspace_root(workspace_root_text: str | None) -> Path:
    """解析 smoke workspace root。

    :param workspace_root_text: CLI 显式传入的 workspace root；为 ``None`` 时
        生成 fresh smoke workspace root。
    :returns: 归一化后的 workspace root。
    :raises Exception: 不主动抛出异常。
    """

    if workspace_root_text is not None:
        return Path(workspace_root_text).resolve()
    return (
        _DEFAULT_WORKSPACE_PARENT
        / f"{_DEFAULT_WORKSPACE_PREFIX}-{uuid4().hex[:12]}"
    ).resolve()


def _require(condition: bool, *, message: str) -> None:
    """校验 smoke 条件成立。

    :param condition: 待校验条件。
    :param message: 条件不成立时的错误消息。
    :returns: ``None``。
    :raises RuntimeError: 条件不成立时抛出。
    """

    if not condition:
        raise RuntimeError(message)


class _GatedReadyPollAdapter:
    """由测试门控控制 ready 时机的 poll adapter。"""

    not_ready_count: int
    ready_count: int
    _gate: asyncio.Event

    def __init__(self) -> None:
        """初始化 adapter 状态。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.not_ready_count = 0
        self.ready_count = 0
        self._gate = asyncio.Event()

    def open_gate(self) -> None:
        """允许下一次 poll 返回完成结果。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._gate.set()

    def poll_wait(self, snapshot: WaitAdapterSnapshot) -> WaitPollResult:
        """按测试门控返回未就绪或完成结果。

        :param snapshot: Host 传入的等待快照；本 smoke 不读取其字段。
        :returns: poll 结果。
        :raises Exception: 不主动抛出异常。
        """

        del snapshot
        if not self._gate.is_set():
            self.not_ready_count += 1
            return WaitPollNotReady()
        self.ready_count += 1
        return WaitPollReady(
            ResolveWaitCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value={"message": "ready"},
                    meta=None,
                ),
                payload_ref=None,
            )
        )

    def abandon_wait(
        self, snapshot: WaitAdapterSnapshot
    ) -> WaitExternalJobLifecycleResult:
        """返回当前 smoke 不支持外部放弃动作。

        :param snapshot: Host 传入的等待快照；本 smoke 不读取其字段。
        :returns: unsupported 结果。
        :raises Exception: 不主动抛出异常。
        """

        del snapshot
        return WaitExternalJobLifecycleUnsupported(reason="not-supported-in-smoke")


class _AwaitingThenAnswerWorkerFactory:
    """第一次运行进入等待态，恢复运行返回最终回答的 worker factory。"""

    accept_count: int

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.accept_count = 0

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 deterministic worker。

        :param snapshot: 当前运行快照。
        :returns: worker。
        :raises Exception: 不主动抛出异常。
        """

        del snapshot
        return _AwaitingThenAnswerWorker(self)


class _AwaitingThenAnswerWorker:
    """按运行顺序切换脚本行为的 worker。"""

    _factory: _AwaitingThenAnswerWorkerFactory

    def __init__(self, factory: _AwaitingThenAnswerWorkerFactory) -> None:
        """初始化 worker。

        :param factory: 共享状态。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._factory = factory

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受一次运行并返回脚本 handle。

        :param snapshot: 当前运行快照。
        :param request: Engine agent 请求。
        :returns: worker handle。
        :raises Exception: 不主动抛出异常。
        """

        self._factory.accept_count += 1
        if self._factory.accept_count == 1:
            return _AwaitingHandle(request=request)
        del snapshot
        return _AnswerHandle(request=request)


class _AwaitingHandle:
    """通过 public ToolExecutor 协议产生等待结果的 worker handle。"""

    _request: AgentRunRequest

    def __init__(self, *, request: AgentRunRequest) -> None:
        """初始化 handle。

        :param request: Engine agent 请求。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._request = request

    @property
    def local_worker_id(self) -> str:
        """返回 worker id。

        :returns: worker id。
        :raises Exception: 不主动抛出异常。
        """

        return "service-awaiting-agent-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """执行 public 工具协议并返回等待事件流。

        :returns: public Engine 事件流。
        :raises Exception: 底层运行失败时透传。
        """

        iteration_id = "awaiting-smoke-iteration"
        tool_call = _awaiting_tool_call()
        batch_snapshot = AssistantToolCallBatchSnapshot(
            iteration_id=iteration_id,
            tool_calls=(tool_call,),
            content=None,
            reasoning_content=None,
            provider_request_id=None,
        )
        outcome = await self._request.tool_executor.execute(
            BatchToolExecutionRequest(
                calls=(tool_call,),
                context=BatchToolExecutionContext(
                    run_id=self._request.run_id,
                    session_id=self._request.session_id,
                    iteration_id=iteration_id,
                    timeout_seconds=(
                        self._request.agent_policy.tool_execution_timeout_seconds
                    ),
                    cancellation_token=self._request.cancellation_token,
                    correlation_id=f"{self._request.run_id}:{iteration_id}:tool_batch",
                ),
            )
        )
        if len(outcome.records) != 1:
            raise RuntimeError(f"tool execution record count mismatch: {len(outcome.records)}")
        record = outcome.records[0]
        if record.tool_call_id != tool_call.tool_call_id:
            raise RuntimeError(f"tool call id mismatch: {record.tool_call_id}")
        record_outcome = record.outcome
        if not isinstance(record_outcome, ToolAwaitingOutcome):
            raise RuntimeError(
                f"tool outcome type mismatch: {type(record_outcome).__name__}"
            )
        awaiting_record = AwaitingToolExecutionRecord(
            batch_snapshot=batch_snapshot,
            call=tool_call,
            await_spec=record_outcome.await_spec,
            snapshot=record_outcome.snapshot,
        )
        yield EngineEvent(
            occurred_at=_NOW,
            session_id=self._request.session_id,
            run_id=self._request.run_id,
            type=EngineEventType.TOOL_AWAITING,
            data=ToolAwaitingData(
                iteration_id=iteration_id,
                record=awaiting_record,
            ),
            metadata=None,
        )
        yield EngineEvent(
            occurred_at=_NOW,
            session_id=self._request.session_id,
            run_id=self._request.run_id,
            type=EngineEventType.RUN_SUSPENDED,
            data=RunSuspendedData(
                reason=RUN_SUSPENDED_REASON_TOOL_AWAITING,
                resume_hint=None,
                accepted_records=(),
                awaiting_records=(awaiting_record,),
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消通知。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        del reason


class _AnswerHandle:
    """返回最终回答的 worker handle。"""

    _request: AgentRunRequest

    def __init__(self, *, request: AgentRunRequest) -> None:
        """初始化 handle。

        :param request: Engine agent 请求。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._request = request

    @property
    def local_worker_id(self) -> str:
        """返回 worker id。

        :returns: worker id。
        :raises Exception: 不主动抛出异常。
        """

        return "service-awaiting-answer-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """返回最终回答事件流。

        :returns: public Engine 事件流。
        :raises Exception: 不主动抛出异常。
        """

        yield EngineEvent(
            occurred_at=_NOW,
            session_id=self._request.session_id,
            run_id=self._request.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content=_FINAL_ANSWER,
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消通知。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        del reason


class _AwaitingTool:
    """返回等待 outcome 的业务工具。"""

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行等待型业务工具。

        :param call: 工具调用。
        :param context: 执行上下文。
        :returns: 等待型 outcome。
        :raises Exception: 不主动抛出异常。
        """

        del call, context
        return ToolAwaitingOutcome(
            await_spec=ToolAwaitSpec(
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                deadline=None,
                resume_token=_RESUME_TOKEN,
            ),
            snapshot=None,
        )


def _awaiting_tool_call() -> ToolCallRequest:
    """构造等待型工具调用请求。

    :returns: 工具调用请求。
    :raises Exception: 不主动抛出异常。
    """

    return ToolCallRequest(
        tool_call_id="awaiting-smoke-tool-call",
        name=_AWAITING_TOOL_NAME,
        arguments={"subject": "DAYU"},
        index_in_iteration=0,
        provider_state=None,
    )


def _open_options(
    workspace_root: Path,
    *,
    worker_factory: _AwaitingThenAnswerWorkerFactory,
    poll_adapter: _GatedReadyPollAdapter,
) -> OpenHostOptions:
    """构造 public Host opener options。

    :param workspace_root: smoke workspace root。
    :param worker_factory: deterministic worker factory。
    :param poll_adapter: deterministic poll adapter。
    :returns: Host opener options。
    :raises Exception: typed options 字段非法时由底层抛出。
    """

    agent_policy = _agent_policy(allow_tool_calls=True)
    return OpenHostOptions(
        db_path=workspace_root / "host.sqlite3",
        artifact_root=workspace_root / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=1.0,
        sqlite_write_busy_retry_count=8,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.02,
        payload_inline_threshold_bytes=4096,
        lane_db_path=workspace_root / "lane.sqlite3",
        lane_name="service-awaiting-smoke",
        lane_capacity=1,
        lane_default_timeout_seconds=1.0,
        lane_claim_ttl_seconds=3.0,
        lane_heartbeat_interval_seconds=0.2,
        worker_startup_timeout_seconds=3.0,
        dispatch_poll_interval_seconds=0.01,
        ordinary_run_baseline=OrdinaryRunExecutionBaseline(
            runner_spec=_runner_spec(),
            runner_options=_runner_options(),
            agent_policy=agent_policy,
        ),
        worker_factory=worker_factory,
        tooling_options=HostToolingOptions(
            business_tool_bundle=_tool_bundle(),
            source_refs=(_SOURCE_REF,),
            wait_adapter_registry=WaitAdapterRegistry(
                (
                    WaitAdapterBinding(
                        tool_name=_AWAITING_TOOL_NAME,
                        await_kind=ToolAwaitKind.EXTERNAL_JOB,
                        adapter_key=_ADAPTER_KEY,
                        resume_policy=WaitResumePolicy.POLL,
                        external_job_ref_source=WaitExternalJobRefSource.RESUME_TOKEN,
                    ),
                )
            ),
            wait_poll_adapter_registry=WaitPollAdapterRegistry(
                (
                    WaitPollAdapterRegistration(
                        adapter_key=_ADAPTER_KEY,
                        adapter=poll_adapter,
                    ),
                )
            ),
        ),
        context_budget_policy=None,
        compactor_runner_baseline=None,
        memory_projection_policy=default_memory_projection_policy(),
        memory_projection_catchup_batch_size=128,
        enable_truncation_manager=True,
        wait_poller_policy=WaitPollerRuntimePolicy(
            enabled=True,
            poll_interval_seconds=0.01,
            claim_ttl_seconds=1.0,
            claim_batch_size=1,
            backoff_initial_delay_seconds=0.01,
            backoff_multiplier=1.2,
            backoff_max_delay_seconds=0.05,
            close_drain_timeout_seconds=0.2,
        ),
    )


def _tool_bundle() -> ToolBundle:
    """构造等待型业务工具 bundle。

    :returns: Tool bundle。
    :raises Exception: typed schema 字段非法时由底层抛出。
    """

    return ToolBundle(
        definitions=(
            ToolDefinition(
                name=_AWAITING_TOOL_NAME,
                schema=ToolSchema(
                    type="function",
                    function=ToolFunctionSchema(
                        name=_AWAITING_TOOL_NAME,
                        description="提交一个测试财报观察任务，返回等待态。",
                        parameters=ToolParametersSchema(
                            type="object",
                            properties={
                                "subject": {
                                    "type": "string",
                                    "description": "财报主体名称。",
                                }
                            },
                            required=("subject",),
                            additional_properties=False,
                        ),
                    ),
                ),
                callable=_AwaitingTool(),
                truncate=None,
                display=None,
                tags=(),
                execution=AsyncDirectToolExecutionCapability(),
            ),
        )
    )


def _scene_inputs() -> PreparedSceneInputs:
    """构造 Service submit 所需 scene 输入。

    :returns: scene 输入。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    return PreparedSceneInputs(
        system_messages=("你是财报分析助手。",),
        system_prompt="你是财报分析助手。",
        tool_selection=SceneToolSelectionResult(
            mode=SceneToolSelectionMode.SELECT,
            tool_names=frozenset({_AWAITING_TOOL_NAME}),
        ),
        model_hints=None,
        agent_policy_override=None,
        fragment_refs=(),
        source_refs=(
            SceneSourceRef(
                source_kind=SceneSourceKind.ASSEMBLY_INPUT,
                source_id="service-awaiting-smoke",
                version_ref=None,
                content_digest="sha256:" + "0" * 64,
            ),
        ),
        content_digest="sha256:" + "1" * 64,
        capability_tags=(),
    )


def _turn_request(*, session_id: str) -> EntrypointTurnRequest:
    """构造 entrypoint turn 请求。

    :param session_id: Host session id。
    :returns: turn 请求。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    return EntrypointTurnRequest(
        context=_host_context("awaiting-smoke-submit"),
        session_id=session_id,
        client_request_id="awaiting-smoke-submit",
        user_prompt="请观察测试财报任务。",
        tool_names=frozenset({_AWAITING_TOOL_NAME}),
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
        run_overrides=ServiceRunOverrides(),
    )


def _host_context(request_id: str) -> HostCallContext:
    """构造 Host 调用上下文。

    :param request_id: 请求 id。
    :returns: Host call context。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    return HostCallContext(
        actor="analyst",
        source="utils.smoke_host_public_awaiting_entrypoint",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="tester"),),
        operation_context=OperationContext(
            operation_name="service_entrypoint_awaiting_smoke",
            operation_kind="manual_smoke",
            business_domain="service",
            business_object_type=None,
            business_object_id=None,
            scenario="wu_wait_04_s2",
            correlation_id=None,
        ),
    )


def _runner_spec() -> RunnerSpec:
    """构造 deterministic runner spec。

    :returns: Runner spec。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    return RunnerSpec(
        provider="test",
        model="awaiting-smoke-model",
        endpoint="https://example.invalid",
        api_key_ref="secret:test",
        headers={},
        client_correlation_policy=ClientCorrelationPolicy.DISABLED,
        supports_tool_calling=True,
        supports_streaming=False,
        supports_stream_usage=False,
        default_timeout_seconds=1.0,
        max_retries=0,
        provider_request=None,
        stream_idle_timeout_seconds=None,
        stream_idle_heartbeat_seconds=None,
    )


def _runner_options() -> RunnerCallOptions:
    """构造 runner options。

    :returns: Runner options。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    return RunnerCallOptions(
        temperature=0.0,
        max_tokens=256,
        top_p=None,
        stream=False,
    )


def _agent_policy(*, allow_tool_calls: bool) -> AgentPolicy:
    """构造 Agent policy。

    :param allow_tool_calls: 是否允许工具调用。
    :returns: Agent policy。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    return AgentPolicy(
        max_iterations=2 if allow_tool_calls else 1,
        continuation_max_attempts=0,
        allow_tool_calls=allow_tool_calls,
        tool_execution_timeout_seconds=1.0,
        fallback_mode=AgentFallbackMode.RAISE_ERROR,
        fallback_prompt="不允许降级回答。",
        continuation_prompt="继续。",
        max_consecutive_failed_tool_batches=1,
    )


def _host_assembly(
    *,
    options: OpenHostOptions,
    effective_tool_bundle: ToolBundle,
) -> ServiceOpenHostAssemblyResult:
    """构造 Service submit helper 所需的 assembly 结果。

    :param options: Host opener options。
    :param effective_tool_bundle: 当前工具 bundle。
    :returns: Service assembly result。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    model = _model_config()
    hint = RunnerOptionHintConfig(temperature=0.0, top_p=1.0, stream=False)
    selection = RunnerOptionHintSelection(
        model_id=model.model_id,
        runner_option_hint_id="interactive",
        model=model,
        runner_option_hint=hint,
        diagnostic=RuntimeSelectionDiagnostic(
            selected_model_id=model.model_id,
            selected_model_source="test",
            selected_runner_option_hint_id="interactive",
            selected_runner_option_hint_source="test",
        ),
    )
    agent_policy_config = MergedAgentPolicyConfig(
        max_iterations=2,
        continuation_max_attempts=0,
        allow_tool_calls=True,
        tool_execution_timeout_seconds=1.0,
        fallback_mode=AgentFallbackMode.RAISE_ERROR.value,
        fallback_prompt="不允许降级回答。",
        continuation_prompt="继续。",
        max_consecutive_failed_tool_batches=1,
        field_sources={},
    )
    lane = RuntimeLaneConfig(
        lane_name="service-awaiting-smoke",
        capacity=1,
        default_timeout_seconds=1.0,
        claim_ttl_seconds=3.0,
        heartbeat_interval_seconds=0.2,
    )
    compatibility = ExecutionProfileCompatibilityDiagnostic(
        profile_id="smoke",
        context_window_class="small",
        min_context_window_tokens=4096,
        selected_model_id=model.model_id,
        model_context_window_tokens=model.context_window_tokens,
        status="compatible",
    )
    return ServiceOpenHostAssemblyResult(
        options=options,
        diagnostics=ServiceOpenHostAssemblyDiagnostics(
            config_overlay_dir=None,
            prompt_asset_root=Path("dayu/config/prompts"),
            scene_manifest_root=Path("dayu/config/scenes"),
            host_runtime_id="smoke",
            execution_profile_id="smoke",
            model_id=model.model_id,
            model_source="test",
            runner_option_hint_id="interactive",
            runner_option_hint_source="test",
            compactor_model_id=model.model_id,
            compactor_runner_option_hint_id="interactive",
            lane_name=lane.lane_name,
            tool_provider_reports=(),
            tool_selection="select",
            context_budget_policy_ref="none",
            agent_policy_sources=(),
            tool_truncation_policy="disabled",
            ordinary_provider_extension_status="none",
            compactor_provider_extension_status="none",
            ordinary_profile_compatibility=compatibility,
            compactor_profile_compatibility=compatibility,
        ),
        host_runtime=_host_runtime_config(),
        execution_profile=_execution_profile_config(),
        lane=lane,
        ordinary_selection=selection,
        compactor_selection=selection,
        agent_policy_config=agent_policy_config,
        effective_tool_bundle=effective_tool_bundle,
    )


def _model_config() -> ModelConfig:
    """构造 runtime model config。

    :returns: Model config。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    return ModelConfig(
        model_id="awaiting-smoke-model",
        runner_kind=RunnerKind.OPENAI_COMPATIBLE,
        provider="test",
        model="awaiting-smoke-model",
        endpoint="https://example.invalid",
        api_key_ref="secret:test",
        headers={},
        supports_tool_calling=True,
        supports_stream=False,
        supports_stream_usage=False,
        default_timeout_seconds=1.0,
        max_retries=0,
        sse_idle_timeout_seconds=1.0,
        sse_heartbeat_seconds=1.0,
        provider_request_extension=None,
        context_window_tokens=4096,
        runtime_hints=ModelRuntimeHintsConfig(
            runner_option_hints={
                "interactive": RunnerOptionHintConfig(
                    temperature=0.0,
                    top_p=1.0,
                    stream=False,
                )
            }
        ),
    )


def _host_runtime_config() -> HostRuntimeProfileConfig:
    """构造未被当前 smoke 行为消费的 runtime config。

    :returns: Host runtime config。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    return HostRuntimeProfileConfig(
        host_runtime_id="smoke",
        store_root="workspace/tmp",
        artifact_root="workspace/tmp/artifacts",
        sqlite=SQLiteRuntimeConfig(
            path="workspace/tmp/host.sqlite3",
            busy_timeout_seconds=1.0,
            write_busy_retry_count=1,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
        host_execution_lane_name="service-awaiting-smoke",
        worker_backend="local",
        dispatch_poll_interval_seconds=0.01,
        payload_inline_threshold_bytes=4096,
        worker_startup_timeout_seconds=3.0,
        memory_projection_catch_up_batch_size=128,
        process_capsule_interrupt_policy=ProcessCapsuleInterruptPolicyConfig(
            terminate_grace_seconds=0.1,
            kill_grace_seconds=0.1,
        ),
    )


def _execution_profile_config() -> ExecutionProfileConfig:
    """构造未被当前 smoke 行为消费的 execution profile config。

    :returns: Execution profile config。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    return ExecutionProfileConfig(
        execution_profile_id="smoke",
        context_window_class="small",
        min_context_window_tokens=4096,
        run_baseline=ExecutionBaselineConfig(
            model_id="awaiting-smoke-model",
            runner_option_hint_id="interactive",
        ),
        compactor_baseline=CompactorBaselineConfig(
            model_id="awaiting-smoke-model",
            scene_id="compactor",
            runner_option_hint_id="interactive",
            user_prompt_template_path="compactor.md",
            artifact_root="workspace/tmp/compact",
        ),
        context_budget_policy=ContextBudgetConfig(
            soft_threshold_context_ratio=0.7,
            hard_threshold_context_ratio=0.9,
            max_proactive_compactions_per_run=0,
            max_reactive_compactions_per_run=0,
            max_compaction_attempts_per_operation=1,
            policy_ref="smoke",
        ),
        memory_projection_policy=MemoryProjectionConfig(
            context_window_size=4096,
            selected_recent_window_item_cap=10,
            selected_recent_window_char_cap=1000,
            selected_recent_window_turn_floor=1,
            fallback_selected_recent_window_item_cap=10,
            fallback_selected_recent_window_char_cap=1000,
            evidence_fact_item_cap=10,
            evidence_fact_char_cap=1000,
            evidence_fact_floor=0,
            session_summary_char_cap=1000,
            answer_anchor_item_cap=10,
            answer_anchor_char_cap=1000,
            forward_intent_item_cap=10,
            forward_intent_char_cap=1000,
            reference_continuity_item_cap=10,
            reference_continuity_char_cap=1000,
            reference_continuity_item_floor=0,
            max_lag_events_for_inline_delta=10,
            max_delta_repair_events=10,
            policy_ref="smoke",
        ),
        tool_truncation_policy=ToolTruncationPolicyConfig(
            enabled=False,
            default_cursor_ttl_seconds=60.0,
            default_limits=ToolTruncationDefaultLimitsConfig(
                text_chars=TextCharsLimitConfig(max_chars=1000),
                text_lines=TextLinesLimitConfig(max_lines=50),
                list_items=ListItemsLimitConfig(max_items=50),
                binary_bytes=BinaryBytesLimitConfig(max_bytes=1024),
            ),
        ),
        tool_duplicate_governance_policy=ToolDuplicateGovernancePolicyConfig(
            default_duplicate_decision="allow",
            decisions_by_tool_name={},
            justification_argument_names_by_tool_name={},
            messages=ToolDuplicateGovernanceMessagesConfig(
                allow="allow",
                reuse="reuse",
                hint="hint",
                require_justification="require",
                hard_stop="stop",
                attempt_scope_diagnostic="attempt",
                prior_accept_missing="missing",
            ),
        ),
        agent_policy=AgentPolicyConfig(
            max_iterations=2,
            continuation_max_attempts=0,
            allow_tool_calls=True,
            tool_execution_timeout_seconds=1.0,
            fallback_mode=AgentFallbackMode.RAISE_ERROR.value,
            fallback_prompt="不允许降级回答。",
            continuation_prompt="继续。",
            max_consecutive_failed_tool_batches=1,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口。

    :param argv: 命令行参数；为 ``None`` 时读取 ``sys.argv[1:]``。
    :returns: 进程退出码。
    :raises Exception: 不主动抛出；异常会被转换为退出码 1。
    """

    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return asyncio.run(run_smoke(args, os.environ))
    except Exception as exc:
        print(f"SMOKE FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
