"""Host Phase 7 waiting integration tests。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_await import ToolAwaitKind, ToolAwaitSpec
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_outcome import (
    BatchToolExecutionOutcome,
    ToolAwaitingOutcome,
    ToolExecutionOutcome,
)
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import EngineEvent
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host import (
    AttemptStatus,
    AuthorizationClaim,
    HostCallContext,
    HostInput,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
    OperationContext,
    RunStatus,
    ensure_session as ensure_public_session,
    resolve_wait,
)
from dayu.host.admission import PendingDispatchRecord
from dayu.host.api import (
    AttemptDispatchSnapshot,
    EnsureSessionRequest,
    HostLocalExecutionOptions,
    StartRunRequest,
    WaitAdapterKey,
)
from dayu.host.command import create_host_command_handle, start_run
from dayu.host.dispatch import HostDispatchScheduler
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    DispatchRecordRow,
    RunRow,
    WaitRecordRow,
    WaitRecordStatus,
    WaitResumePolicy,
    WorkerKind,
    read_attempt_by_id,
    read_active_wait_records_for_run,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostTransactionRunner
from dayu.host.tool_runtime import (
    DefaultHostToolFactAcceptPort,
    DefaultToolRuntimeFactory,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    ToolRuntimeBuildRequest,
    ToolRuntimeExecutionScope,
)
from dayu.host.tooling import (
    HostToolingOptions,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
    default_framework_tool_policy_view,
)
from dayu.host.wait_adapter import (
    WaitAdapterBinding,
    WaitAdapterRegistry,
    WaitExternalJobRefSource,
)
from dayu.host.waiting import DefaultHostToolAwaitingAcceptPort
from tests.host.test_resolve_wait_command import (
    _SeededWaitingRun,
    _build_resume_request,
    _completed_request,
    _options,
    _read_wait,
    _seed_active_run,
)

_ITERATION_ID = "iteration-phase7-waiting-integration"
_POLICY_DIGEST = "sha256:7777777777777777777777777777777777777777777777777777777777777777"
_RESUME_TOKEN = "external-job-phase7-integration"
_TOOL_NAME = "awaiting_tool"


class _NeverCancelledToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终为 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终为 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终为 ``None``。
        """

        return None


class _AwaitingBusinessTool:
    """返回 awaiting outcome 的本地 fake business tool。"""

    def __init__(self) -> None:
        """初始化 fake tool。

        :returns: ``None``。
        """

        self.call_count = 0

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行本地 awaiting 工具。

        :param call: 工具调用请求。
        :param context: 批式工具上下文。
        :returns: awaiting outcome。
        """

        del call, context
        self.call_count += 1
        return ToolAwaitingOutcome(
            await_spec=ToolAwaitSpec(
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                deadline=None,
                resume_token=_RESUME_TOKEN,
            ),
            snapshot=None,
        )


class _HoldingWorkerHandle:
    """保持 Engine 事件流打开的 fake worker handle。"""

    def __init__(self) -> None:
        """初始化 fake worker handle。

        :returns: ``None``。
        """

        self._closed = asyncio.Event()
        self.cancel_reasons: list[str] = []
        self.closed = False

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 稳定测试 worker id。
        """

        return "phase7-awaiting-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """保持 worker event stream 打开直到测试关闭 scheduler。

        :returns: 空 EngineEvent 异步迭代器。
        """

        await self._closed.wait()
        if False:
            yield _unreachable_engine_event()

    def cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        self.cancel_reasons.append(reason)
        self._closed.set()

    async def close(self) -> None:
        """关闭 fake worker handle。

        :returns: ``None``。
        """

        self.closed = True
        self._closed.set()


class _CapturingWorker:
    """捕获 scheduler 构造出的 Engine request。"""

    def __init__(self, factory: "_CapturingWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """接受 scheduler dispatch 请求。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 保持事件流打开的 fake handle。
        """

        self._factory.accepted_snapshots.append(snapshot)
        self._factory.accepted_requests.append(request)
        return self._factory.handle


class _CapturingWorkerFactory:
    """测试用本地 worker factory。"""

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        """

        self.accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self.accepted_requests: list[AgentRunRequest] = []
        self.handle = _HoldingWorkerHandle()

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建捕获请求的 worker。

        :param snapshot: dispatch snapshot。
        :returns: fake worker。
        """

        del snapshot
        return _CapturingWorker(self)


def test_phase7_resolve_wait_public_entry_is_importable() -> None:
    """P7 integration 测试集包含 public resolve_wait 入口。"""

    assert resolve_wait.__name__ == "resolve_wait"


def test_local_awaiting_tool_manual_resolve_resumes_run(
    tmp_path: Path,
) -> None:
    """本地 awaiting 工具进入 WAITING 后可通过 manual resolve 恢复 Run。"""

    host = create_host_command_handle(_options(tmp_path))
    try:
        seeded = _seed_active_integration_run(host._transaction_runner())
        tool = _AwaitingBusinessTool()
        tool_runtime = DefaultToolRuntimeFactory(
            EffectiveToolBundleBuilder()
        ).create_tool_runtime(
            ToolRuntimeBuildRequest(
                effective_bundle_request=EffectiveToolBundleBuildRequest(
                    business_tool_bundle=ToolBundle(
                        definitions=(_definition(tool),)
                    ),
                    source_refs=(_source_ref(),),
                    framework_tool_policy=default_framework_tool_policy_view(),
                    policy_snapshot_digest=_POLICY_DIGEST,
                ),
                execution_scope=ToolRuntimeExecutionScope(
                    session_id=seeded.session_id,
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    allow_tool_calls=True,
                ),
                accept_port=DefaultHostToolFactAcceptPort(
                    transaction_runner=host._transaction_runner()
                ),
                awaiting_accept_port=DefaultHostToolAwaitingAcceptPort(
                    transaction_runner=host._transaction_runner()
                ),
                wait_adapter_registry=_wait_adapter_registry(),
            )
        )

        batch = _awaiting_tool_request(seeded)
        outcome = _execute_tool_runtime(tool_runtime.tool_executor, batch)
        wait = _active_wait(host._transaction_runner(), seeded.run_id)
        wait_record = _read_wait(host._transaction_runner(), wait.wait_id)
        run_before_resolve = _run(host._transaction_runner(), seeded.run_id)
        attempt_before_resolve = _attempt_status(
            host._transaction_runner(), seeded.attempt_id
        )
        snapshot = resolve_wait(
            host,
            wait.wait_id,
            _completed_request("phase7-integration-manual-resolve"),
        )
        resume_request = _build_resume_request(
            host._transaction_runner(),
            seeded.session_id,
            snapshot.current_attempt_id,
        )

        assert isinstance(outcome.records[0].outcome, ToolAwaitingOutcome)
        assert tool.call_count == 1
        assert run_before_resolve.status is RunStatus.WAITING
        assert attempt_before_resolve is AttemptStatus.SUSPENDED
        assert wait_record.status is WaitRecordStatus.WAITING
        assert snapshot.status is RunStatus.RUNNING
        assert snapshot.current_attempt_id is not None
        assert snapshot.current_attempt_id != seeded.attempt_id
        assert any(
            isinstance(message.content, str)
            and "Accepted wait result fact:" in message.content
            and wait.wait_id in message.content
            for message in resume_request.messages
        )
    finally:
        host.close()


@pytest.mark.asyncio
async def test_scheduler_awaiting_tool_enters_waiting_and_manual_resolve_resumes(
    tmp_path: Path,
) -> None:
    """真实 scheduler 生产 ToolRuntime wiring 支持 awaiting -> WAITING -> resume。"""

    host = create_host_command_handle(_options(tmp_path))
    factory = _CapturingWorkerFactory()
    tool = _AwaitingBusinessTool()
    scheduler = await HostDispatchScheduler.open(
        transaction_runner=host._transaction_runner(),
        local_execution=_local_execution_options(tmp_path, factory, tool),
        host_handle_id="phase7-awaiting-production",
    )
    try:
        session = ensure_public_session(
            host,
            EnsureSessionRequest(
                scope="workspace",
                slot_key="phase7-production",
                metadata=(),
            ),
        )
        started = start_run(
            host,
            StartRunRequest(
                context=_public_context(),
                session_id=session.session_id,
                client_request_id="phase7-production-start",
                input=HostInput(
                    display_text="start awaiting production path",
                    payload_ref=None,
                    payload_digest=None,
                ),
                execution_target="phase7-production-target",
                queue_policy="queue",
            ),
        )
        stage = scheduler._run_pre_start_governance(session.session_id)
        assert stage.pending_dispatch is not None
        pending = stage.pending_dispatch
        assert pending.run_id == started.run_id

        scheduler.wake_dispatch(pending)
        result = await scheduler.drain_once()
        request = factory.accepted_requests[0]
        tool_outcome = await request.tool_executor.execute(
            _scheduler_awaiting_tool_request(
                session_id=session.session_id,
                run_id=started.run_id,
                request=request,
            )
        )
        wait = _active_wait(host._transaction_runner(), started.run_id)
        run_before_resolve = _run(host._transaction_runner(), started.run_id)
        attempt_before_resolve = _attempt_status(
            host._transaction_runner(), pending.attempt_id
        )

        assert result.dispatched == 1
        assert request.disable_tools is False
        assert isinstance(tool_outcome.records[0].outcome, ToolAwaitingOutcome)
        assert tool.call_count == 1
        assert run_before_resolve.status is RunStatus.WAITING
        assert attempt_before_resolve is AttemptStatus.SUSPENDED
        assert wait.status is WaitRecordStatus.WAITING
        assert wait.external_job_ref is not None
        assert wait.external_job_ref.external_job_id == _RESUME_TOKEN

        resolved = resolve_wait(
            host,
            wait.wait_id,
            _completed_request("phase7-production-manual-resolve"),
        )
        resume_dispatch = _dispatch_for_attempt(
            host._transaction_runner(), resolved.current_attempt_id
        )

        assert resolved.status is RunStatus.RUNNING
        assert resolved.current_attempt_id is not None
        assert resolved.current_attempt_id != pending.attempt_id
        assert resume_dispatch.run_id == started.run_id
        assert resume_dispatch.worker_kind is WorkerKind.LOCAL
    finally:
        await scheduler.close()
        host.close()


def _seed_active_integration_run(
    transaction_runner: HostTransactionRunner,
) -> _SeededWaitingRun:
    """创建 active Run。

    :param transaction_runner: Host transaction runner。
    :returns: seeded waiting run refs。
    """

    session_id = ensure_session(
        transaction_runner,
        EnsureSessionRequest(scope="workspace", slot_key="phase7", metadata=()),
    ).snapshot.session_id
    seeded = _SeededWaitingRun(
        session_id=session_id,
        run_id="run-resolve",
        attempt_id="attempt-resolve",
        execution_id="execution-resolve",
        dispatch_record_id="dispatch-resolve",
        wait_id="",
    )
    _seed_active_run(transaction_runner, seeded)
    return seeded


def _awaiting_tool_request(seeded: _SeededWaitingRun) -> BatchToolExecutionRequest:
    """构造 awaiting tool 执行请求。

    :param seeded: seeded Run refs。
    :returns: 批式工具执行请求。
    """

    return BatchToolExecutionRequest(
        calls=(
            ToolCallRequest(
                tool_call_id="tool-call-phase7-awaiting",
                name=_TOOL_NAME,
                arguments={"ticker": "DAYU"},
                index_in_iteration=0,
                provider_state=None,
            ),
        ),
        context=BatchToolExecutionContext(
            run_id=seeded.run_id,
            session_id=seeded.session_id,
            iteration_id=_ITERATION_ID,
            timeout_seconds=10.0,
            cancellation_token=_NeverCancelledToken(),
            correlation_id="phase7-waiting-integration",
        ),
    )


def _execute_tool_runtime(
    tool_executor: ToolExecutor, request: BatchToolExecutionRequest
) -> BatchToolExecutionOutcome:
    """同步执行 ToolRuntime async executor。

    :param tool_executor: ToolRuntimeHandle 暴露的 executor。
    :param request: 批式工具执行请求。
    :returns: 批式工具执行结果。
    """

    return asyncio.run(tool_executor.execute(request))


def _scheduler_awaiting_tool_request(
    *, session_id: str, run_id: str, request: AgentRunRequest
) -> BatchToolExecutionRequest:
    """构造 scheduler 生产 ToolRuntime 的 awaiting 工具请求。

    :param session_id: Session id。
    :param run_id: Run id。
    :param request: scheduler 交给 worker 的 Engine request。
    :returns: 批式工具执行请求。
    """

    return BatchToolExecutionRequest(
        calls=(
            ToolCallRequest(
                tool_call_id="tool-call-phase7-production-awaiting",
                name=_TOOL_NAME,
                arguments={"ticker": "DAYU"},
                index_in_iteration=0,
                provider_state=None,
            ),
        ),
        context=BatchToolExecutionContext(
            run_id=run_id,
            session_id=session_id,
            iteration_id="iteration-phase7-production-awaiting",
            timeout_seconds=10.0,
            cancellation_token=request.cancellation_token,
            correlation_id="phase7-production-awaiting",
        ),
    )


def _pending_dispatch_from_started_run(
    transaction_runner: HostTransactionRunner, attempt_id: str | None
) -> PendingDispatchRecord:
    """从 public start_run 结果读取 pending dispatch 摘要。

    :param transaction_runner: Host transaction runner。
    :param attempt_id: start_run 创建的 current Attempt id。
    :returns: pending dispatch 摘要。
    """

    dispatch = _dispatch_for_attempt(transaction_runner, attempt_id)
    return PendingDispatchRecord(
        dispatch_record_id=dispatch.dispatch_record_id,
        run_id=dispatch.run_id,
        attempt_id=dispatch.attempt_id,
        execution_id=dispatch.execution_id,
        execution_target=dispatch.execution_target,
        worker_kind=dispatch.worker_kind,
    )


def _dispatch_for_attempt(
    transaction_runner: HostTransactionRunner, attempt_id: str | None
) -> DispatchRecordRow:
    """读取 Attempt 对应 dispatch record。

    :param transaction_runner: Host transaction runner。
    :param attempt_id: Attempt id。
    :returns: dispatch record row。
    """

    assert attempt_id is not None
    row = transaction_runner.run_read(
        lambda transaction: read_dispatch_record_by_attempt_id(
            transaction, attempt_id
        )
    )
    assert row is not None
    return row


def _active_wait(
    transaction_runner: HostTransactionRunner, run_id: str
) -> WaitRecordRow:
    """读取 Run 下唯一 active wait。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: active wait record。
    """

    waits = transaction_runner.run_read(
        lambda transaction: read_active_wait_records_for_run(transaction, run_id)
    )
    assert len(waits) == 1
    return waits[0]


def _run(transaction_runner: HostTransactionRunner, run_id: str) -> RunRow:
    """读取 Run row。

    :param transaction_runner: Host transaction runner。
    :param run_id: Run id。
    :returns: Run row。
    """

    run = transaction_runner.run_read(
        lambda transaction: read_run_by_id(transaction, run_id)
    )
    assert run is not None
    return run


def _attempt_status(
    transaction_runner: HostTransactionRunner, attempt_id: str
) -> AttemptStatus:
    """读取 Attempt 状态。

    :param transaction_runner: Host transaction runner。
    :param attempt_id: Attempt id。
    :returns: AttemptStatus。
    """

    attempt = transaction_runner.run_read(
        lambda transaction: read_attempt_by_id(transaction, attempt_id)
    )
    assert attempt is not None
    return attempt.status


def _definition(callable_: _AwaitingBusinessTool) -> ToolDefinition:
    """构造 awaiting fake tool definition。

    :param callable_: fake callable。
    :returns: ToolDefinition。
    """

    return ToolDefinition(
        name=_TOOL_NAME,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=_TOOL_NAME,
                description="fake awaiting business tool",
                parameters=ToolParametersSchema(
                    type="object",
                    properties={"ticker": {"type": "string"}},
                    required=("ticker",),
                    additional_properties=False,
                ),
            ),
        ),
        callable=callable_,
        truncate=None,
        display=None,
        tags=("test",),
    )


def _local_execution_options(
    tmp_path: Path,
    factory: LocalEngineWorkerFactory,
    tool: _AwaitingBusinessTool,
) -> HostLocalExecutionOptions:
    """构造真实 scheduler 使用的本地执行配置。

    :param tmp_path: pytest 临时目录。
    :param factory: 本地 worker factory。
    :param tool: awaiting 业务工具。
    :returns: HostLocalExecutionOptions。
    """

    return HostLocalExecutionOptions(
        lane_db_path=tmp_path / "lane.sqlite3",
        lane_name="llm",
        lane_capacity=1,
        lane_default_timeout_seconds=0.1,
        lane_claim_ttl_seconds=1.0,
        lane_heartbeat_interval_seconds=0.1,
        worker_startup_timeout_seconds=1.0,
        dispatch_poll_interval_seconds=0.01,
        runner_spec=_runner_spec(),
        runner_options=RunnerCallOptions(
            temperature=None,
            max_tokens=None,
            top_p=None,
            stream=False,
        ),
        agent_policy=AgentPolicy(
            max_iterations=1,
            continuation_max_attempts=0,
            allow_tool_calls=True,
            tool_execution_timeout_seconds=10.0,
        ),
        worker_factory=factory,
        tooling_options=HostToolingOptions(
            business_tool_bundle=ToolBundle(definitions=(_definition(tool),)),
            source_refs=(_source_ref(),),
            framework_tool_policy=default_framework_tool_policy_view(),
            wait_adapter_registry=_wait_adapter_registry(),
        ),
    )


def _runner_spec() -> RunnerSpec:
    """构造支持工具调用的测试 RunnerSpec。

    :returns: RunnerSpec。
    """

    return RunnerSpec(
        provider="test",
        model="test-model",
        endpoint="https://example.invalid",
        api_key_ref="secret:test",
        headers={},
        supports_tool_calling=True,
        supports_streaming=False,
        supports_stream_usage=False,
        default_timeout_seconds=1.0,
        max_retries=0,
        provider_request=None,
    )


def _public_context() -> HostCallContext:
    """构造 public start_run 调用上下文。

    :returns: HostCallContext。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id="trace-phase7-production-awaiting",
        authorization_claims=(AuthorizationClaim(name="role", value="research"),),
        operation_context=OperationContext(
            operation_name="phase7_awaiting_production_wiring",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase7",
            correlation_id="corr-phase7-production-awaiting",
        ),
    )


def _unreachable_engine_event() -> EngineEvent:
    """构造不可达 EngineEvent 占位。

    :returns: 不会返回。
    :raises AssertionError: 始终抛出。
    """

    raise AssertionError("unreachable engine event")


def _source_ref() -> ToolBundleSourceRef:
    """构造工具来源引用。

    :returns: ToolBundleSourceRef。
    """

    return ToolBundleSourceRef(
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id="phase7-waiting-integration",
    )


def _wait_adapter_registry() -> WaitAdapterRegistry:
    """构造等待 adapter registry。

    :returns: WaitAdapterRegistry。
    """

    return WaitAdapterRegistry(
        (
            WaitAdapterBinding(
                tool_name=_TOOL_NAME,
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                adapter_key=WaitAdapterKey("poll:phase7-integration"),
                resume_policy=WaitResumePolicy.POLL,
                external_job_ref_source=WaitExternalJobRefSource.RESUME_TOKEN,
            ),
        )
    )
