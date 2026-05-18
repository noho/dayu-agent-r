"""Host Phase 5 dispatch scheduler 测试。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    ContextCompactionRequestedData,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    RunFailedData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import AgentMessage
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolBundle, ToolDefinition
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolExecutionOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.host.admission import PendingDispatchRecord
from dayu.host.api import (
    AttemptDispatchSnapshot,
    AttemptStatus,
    CancelMode,
    EnsureSessionRequest,
    HostLocalExecutionOptions,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
    RunStatus,
)
from dayu.host.compaction import ContextCompactor
from dayu.host.context_budget import ContextBudgetDecision
from dayu.host.context_events import (
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_FAILED,
    CONTEXT_COMPACTION_REQUESTED,
    build_context_compaction_requested_payload,
)
from dayu.host.context_policy import (
    ContextBudgetPolicy,
    ContextCompactionTriggerSource,
    default_context_budget_policy,
)
from dayu.host.fake_compaction import FakeContextCompactor
from dayu.host.tooling import (
    HostToolingOptions,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
)
from dayu.host.dispatch import (
    ActiveCancelMessage,
    ActiveWorkerRegistry,
    DispatchDrainResult,
    HostDispatchScheduler,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import HostDurableStore, open_host_durable_store
from dayu.host.durable.errors import HostTransactionRetryExhaustedError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.run_transition import (
    CancelPredispatchStartingInput,
    CreateAcceptedRunInput,
    CreateRunningRunInput,
    cancel_predispatch_starting_in_transaction,
    create_accepted_run_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    RunRow,
    RunStartReason,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.local_proxy import DefaultLocalEngineWorkerFactory
from dayu.host.projection import ProjectionCatchupPort
from dayu.runtime.lane import (
    LaneAcquired,
    LaneClaimToken,
    LaneConfig,
    LaneController,
    LaneOwner,
    SQLiteLaneCoordinatorConfig,
)

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "dispatch-test"})
_LANE_NAME = "llm"
_SOFT_THRESHOLD_PROMPT_CHAR_COUNT = 120
_SOFT_CONTEXT_WINDOW_SIZE = 110
_SOFT_RESERVED_OUTPUT_TOKENS = 10
_SOFT_HARD_THRESHOLD_TOKENS = 80
_SOFT_SAFETY_MARGIN_RATIO = 0.5


@dataclass(frozen=True, slots=True)
class _SeededRun:
    """测试中创建的 running Run。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


@dataclass(frozen=True, slots=True)
class _AcceptedSeededRun:
    """测试中创建的 pre-start accepted Run。"""

    session_id: str
    run_id: str


@dataclass(slots=True)
class _FailingProjectionCatchup(ProjectionCatchupPort):
    """测试用失败 projection catch-up port。"""

    calls: int = 0

    def catch_up_projection(self) -> None:
        """记录调用并模拟 catch-up 失败。

        :returns: ``None``。
        :raises RuntimeError: 始终抛出测试错误。
        """

        self.calls += 1
        raise RuntimeError("forced scheduler projection catch-up failure")


class _FakeHandle:
    """测试用 worker handle。"""

    def __init__(self, local_worker_id: str = "local-worker-test") -> None:
        """初始化 fake handle。

        :param local_worker_id: 本地 worker id。
        :returns: ``None``。
        """

        self._local_worker_id = local_worker_id
        self.closed = False

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        """

        return self._local_worker_id

    async def events(self) -> AsyncIterator[EngineEvent]:
        """返回空事件流。

        :returns: 空异步迭代器。
        """

        if False:
            yield _unreachable_engine_event()

    def cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason

    async def close(self) -> None:
        """关闭 fake handle。

        :returns: ``None``。
        """

        self.closed = True


class _CrashingHandle(_FakeHandle):
    """事件流抛异常的 fake handle。"""

    async def events(self) -> AsyncIterator[EngineEvent]:
        """抛出 worker stream 异常。

        :returns: 不会正常返回事件。
        :raises RuntimeError: 始终模拟 worker stream crash。
        """

        raise RuntimeError("worker stream crashed")
        if False:
            yield _unreachable_engine_event()


class _CloseFailingHandle(_FakeHandle):
    """关闭时抛异常的 fake handle。"""

    async def events(self) -> AsyncIterator[EngineEvent]:
        """保持事件流未结束直到 scheduler close。

        :returns: 不会正常返回事件。
        """

        await asyncio.sleep(10.0)
        if False:
            yield _unreachable_engine_event()

    def cancel(self, reason: str) -> None:
        """模拟 handle cancel 异常。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises RuntimeError: 始终抛出取消异常。
        """

        del reason
        raise RuntimeError("cancel failed")

    async def close(self) -> None:
        """模拟 handle close 异常。

        :returns: ``None``。
        :raises RuntimeError: 始终抛出关闭异常。
        """

        raise RuntimeError("close failed")


class _CloseCountingHandle(_FakeHandle):
    """记录 cancel / close 次数且事件流长期挂起的 fake handle。"""

    def __init__(self) -> None:
        """初始化计数 handle。

        :returns: ``None``。
        """

        super().__init__()
        self.cancel_count = 0
        self.close_count = 0

    async def events(self) -> AsyncIterator[EngineEvent]:
        """保持事件流未结束直到 scheduler close。

        :returns: 不会正常返回事件。
        """

        await asyncio.sleep(10.0)
        if False:
            yield _unreachable_engine_event()

    def cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason
        self.cancel_count += 1

    async def close(self) -> None:
        """记录关闭次数。

        :returns: ``None``。
        """

        self.close_count += 1
        await super().close()


class _ControlledBlockingHandle(_FakeHandle):
    """用 asyncio.Event 控制事件流生命周期的 fake handle。"""

    def __init__(self) -> None:
        """初始化受控 handle。

        :returns: ``None``。
        """

        super().__init__()
        self.cancel_count = 0
        self.close_count = 0
        self.events_started = asyncio.Event()
        self.events_finalized = asyncio.Event()
        self.release_events = asyncio.Event()

    async def events(self) -> AsyncIterator[EngineEvent]:
        """阻塞事件流直到测试释放或 task 被取消。

        :returns: 不会自然返回事件，除非测试显式释放。
        """

        self.events_started.set()
        try:
            await self.release_events.wait()
        finally:
            self.events_finalized.set()
        if False:
            yield _unreachable_engine_event()

    def cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason
        self.cancel_count += 1

    async def close(self) -> None:
        """记录关闭请求。

        :returns: ``None``。
        """

        self.close_count += 1
        await super().close()


class _FlakyLocalWorkerIdHandle(_FakeHandle):
    """第二次读取 ``local_worker_id`` 时抛错的 fake handle。"""

    def __init__(self) -> None:
        """初始化 fake handle。

        :returns: ``None``。
        """

        super().__init__("local-worker-first-read")
        self.local_worker_id_reads = 0
        self.close_count = 0

    @property
    def local_worker_id(self) -> str:
        """第一次返回 worker id，后续模拟 pre-event envelope 构造失败。

        :returns: 本地 worker id。
        :raises RuntimeError: 第二次及后续读取时抛出。
        """

        self.local_worker_id_reads += 1
        if self.local_worker_id_reads == 1:
            return "local-worker-first-read"
        raise RuntimeError("local worker id unavailable")

    async def events(self) -> AsyncIterator[EngineEvent]:
        """该测试路径不应进入事件流。

        :returns: 不会正常返回事件。
        :raises AssertionError: 若被调用则抛出。
        """

        raise AssertionError("events must not be consumed")
        if False:
            yield _unreachable_engine_event()

    async def close(self) -> None:
        """记录关闭次数。

        :returns: ``None``。
        """

        self.close_count += 1
        await super().close()


class _AcceptingWorker:
    """测试用立即 accept worker。"""

    def __init__(self, factory: "_FakeWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """接受 worker 请求。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: fake handle。
        """

        self._factory.accepted_snapshots.append(snapshot)
        self._factory.accepted_requests.append(request)
        if self._factory.accepted_handle is not None:
            return self._factory.accepted_handle
        return _FakeHandle()


class _HandleWorker:
    """返回指定 handle 的 fake worker。"""

    def __init__(self, handle: LocalWorkerHandle) -> None:
        """初始化 worker。

        :param handle: accept 返回的 handle。
        :returns: ``None``。
        """

        self._handle = handle

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """返回预置 handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 预置 handle。
        """

        del snapshot, request
        return self._handle


class _FailingAcceptWorker:
    """accept 时抛异常的 fake worker。"""

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """模拟非 timeout accept 异常。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出 accept 异常。
        """

        del snapshot, request
        raise RuntimeError("accept failed")


class _SlowWorker:
    """测试用超时 worker。"""

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """阻塞直到 scheduler startup timeout。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 不会返回的 fake handle。
        """

        del snapshot, request
        await asyncio.sleep(1.0)
        return _FakeHandle()


class _FakeWorkerFactory:
    """测试用 worker factory。"""

    def __init__(
        self,
        *,
        slow: bool = False,
        worker: LocalEngineWorker | None = None,
        accepted_handle: LocalWorkerHandle | None = None,
    ) -> None:
        """初始化 factory。

        :param slow: 是否返回超时 worker。
        :param worker: 指定 worker；不传时按 ``slow`` 构造。
        :param accepted_handle: 默认 accepting worker 返回的指定 handle。
        :returns: ``None``。
        """

        self.created = 0
        self.accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self.accepted_requests: list[AgentRunRequest] = []
        self._slow = slow
        self._worker = worker
        self.accepted_handle = accepted_handle

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 fake worker。

        :param snapshot: dispatch snapshot。
        :returns: fake worker。
        """

        del snapshot
        self.created += 1
        if self._worker is not None:
            return self._worker
        if self._slow:
            return _SlowWorker()
        return _AcceptingWorker(self)


class _SnapshotEventHandle(_FakeHandle):
    """按 dispatch snapshot 生成单个 EngineEvent 的 handle。"""

    def __init__(self, snapshot: AttemptDispatchSnapshot, event: EngineEvent) -> None:
        """初始化 handle。

        :param snapshot: dispatch snapshot。
        :param event: 要产出的 EngineEvent。
        :returns: ``None``。
        """

        super().__init__(local_worker_id=f"worker-{snapshot.attempt_id}")
        self._event = event

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出单个事件后结束。

        :returns: EngineEvent 异步迭代器。
        """

        yield self._event


class _ReactiveRecoveryWorker:
    """第一轮产出 reactive overflow，第二轮产出 final answer。"""

    def __init__(self, factory: "_ReactiveRecoveryWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """按创建顺序返回 reactive 或 final handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: scripted handle。
        """

        self._factory.accepted_snapshots.append(snapshot)
        self._factory.accepted_requests.append(request)
        if len(self._factory.accepted_snapshots) == 1:
            event = EngineEvent(
                occurred_at=_NOW,
                session_id=snapshot.session_id,
                run_id=snapshot.run_id,
                type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
                data=ContextCompactionRequestedData(
                    iteration_id="iter-reactive",
                    budget_state=None,
                    reason="provider_overflow",
                    provider_request_id="req-reactive",
                ),
                metadata=None,
            )
        elif self._factory.final_blocks:
            return _ControlledBlockingHandle()
        else:
            event = EngineEvent(
                occurred_at=_NOW,
                session_id=snapshot.session_id,
                run_id=snapshot.run_id,
                type=EngineEventType.FINAL_ANSWER,
                data=FinalAnswerData(
                    content="recovered",
                    filtered=False,
                    degraded=False,
                    finish_reason=FinishReason.STOP,
                ),
                metadata=None,
            )
        return _SnapshotEventHandle(snapshot, event)


class _ReactiveRecoveryWorkerFactory:
    """测试 reactive recovery dispatch 的 worker factory。"""

    def __init__(self, *, final_blocks: bool = False) -> None:
        """初始化 factory。

        :param final_blocks: recovery Attempt 是否阻塞不产出 terminal。
        :returns: ``None``。
        """

        self.final_blocks = final_blocks
        self.created = 0
        self.accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self.accepted_requests: list[AgentRunRequest] = []

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 scripted worker。

        :param snapshot: dispatch snapshot。
        :returns: scripted worker。
        """

        del snapshot
        self.created += 1
        return _ReactiveRecoveryWorker(self)


class _FinalAnswerWorker:
    """接受请求后立即返回 final_answer 的 fake worker。"""

    def __init__(self, factory: "_FinalAnswerWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """记录请求并返回 final_answer handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: scripted final answer handle。
        """

        self._factory.accepted_snapshots.append(snapshot)
        self._factory.accepted_requests.append(request)
        return _SnapshotEventHandle(
            snapshot,
            EngineEvent(
                occurred_at=_NOW,
                session_id=snapshot.session_id,
                run_id=snapshot.run_id,
                type=EngineEventType.FINAL_ANSWER,
                data=FinalAnswerData(
                    content=f"final:{snapshot.run_id}",
                    filtered=False,
                    degraded=False,
                    finish_reason=FinishReason.STOP,
                ),
                metadata=None,
            ),
        )


class _FinalAnswerWorkerFactory:
    """按真实 dispatch 接受顺序记录 Engine request 的 fake factory。"""

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        """

        self.created = 0
        self.accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self.accepted_requests: list[AgentRunRequest] = []

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 final answer worker。

        :param snapshot: dispatch snapshot。
        :returns: fake worker。
        """

        del snapshot
        self.created += 1
        return _FinalAnswerWorker(self)


class _CountingTool:
    """测试用业务工具 callable。"""

    def __init__(self) -> None:
        """初始化测试工具。

        :returns: ``None``。
        """

        self.call_count = 0

    async def __call__(
        self, call: ToolCallRequest, context: BatchToolExecutionContext
    ) -> ToolExecutionOutcome:
        """返回当前调用参数并记录调用次数。

        :param call: 工具调用请求。
        :param context: 批式工具执行上下文。
        :returns: 工具成功 outcome。
        """

        del context
        self.call_count += 1
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={"tool_call_id": call.tool_call_id, "arguments": call.arguments},
                meta=None,
            )
        )


class _EnqueueOnSecondEmptyQueue(asyncio.Queue[PendingDispatchRecord]):
    """在第二次 empty 检查后注入一条 dispatch，用于复现 wakeup 窗口。"""

    def __init__(self, injected_record: PendingDispatchRecord) -> None:
        """初始化测试队列。

        :param injected_record: 第二次 empty 检查时注入的 dispatch 摘要。
        :returns: ``None``。
        """

        super().__init__()
        self._injected_record = injected_record
        self._empty_calls = 0

    def empty(self) -> bool:
        """第二次 empty 仍返回 True，但在返回前模拟并发入队。

        :returns: 当前测试队列是否报告为空。
        """

        self._empty_calls += 1
        if self._empty_calls == 2:
            self.put_nowait(self._injected_record)
            return True
        return super().empty()


class _ObservedEmptyQueue(asyncio.Queue[PendingDispatchRecord]):
    """记录 empty 检查的测试队列。"""

    def __init__(self) -> None:
        """初始化测试队列。

        :returns: ``None``。
        """

        super().__init__()
        self.empty_checked = asyncio.Event()

    def empty(self) -> bool:
        """记录 empty 检查并返回真实队列状态。

        :returns: 当前队列是否为空。
        """

        self.empty_checked.set()
        return super().empty()


class _CancelBeforePreAcceptRecheck:
    """在 scheduler pre-accept recheck 前注入 durable cancel 的测试 callable。"""

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        seeded: _SeededRun,
        original_recheck: Callable[[DispatchRecordRow], bool],
    ) -> None:
        """初始化 cancel race 注入器。

        :param transaction_runner: Host transaction runner。
        :param seeded: seeded run。
        :param original_recheck: scheduler 原始 pre-accept recheck。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._seeded = seeded
        self._original_recheck = original_recheck

    def __call__(self, dispatch_record: DispatchRecordRow) -> bool:
        """注入 cancel race 后执行原始 pre-accept recheck。

        :param dispatch_record: 当前 dispatching row。
        :returns: 原始 pre-accept recheck 结果。
        """

        _cancel_predispatch_dispatching(self._transaction_runner, self._seeded)
        return self._original_recheck(dispatch_record)


class _FailingDrainLoopScheduler(HostDispatchScheduler):
    """测试用 drain_once 崩溃 scheduler。"""

    async def drain_once(self) -> DispatchDrainResult:
        """模拟 drain_once 未预期异常。

        :returns: 不会返回。
        :raises RuntimeError: 始终抛出测试异常。
        """

        raise RuntimeError("drain failure")


@pytest.mark.asyncio
async def test_pending_waiting_dispatching_worker_accept_marks_running(
    tmp_path: Path,
) -> None:
    """pending dispatch 可推进到 worker accepted，Attempt 进入 RUNNING。"""

    factory = _FakeWorkerFactory(accepted_handle=_CloseCountingHandle())
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(
                store.transaction_runner, seeded
            )
            event = _read_event_by_type(
                store.transaction_runner, "ATTEMPT_RUNNING"
            )
            assert result.processed == 1
            assert result.dispatched == 1
            assert run.status == RunStatus.RUNNING
            assert attempt.status == AttemptStatus.RUNNING
            assert dispatch_record.status == DispatchRecordStatus.DISPATCHING
            assert dispatch_record.worker_accept_event_id == event.event_id
            payload = json.loads(event.payload_json)
            assert payload["local_worker_id"] == "local-worker-test"
            assert payload["worker_accepted_at"] == dispatch_record.worker_accepted_at
            assert payload["lane_name"] == _LANE_NAME
            assert payload["lane_claim_id"] == dispatch_record.lane_claim_id
            assert (
                factory.accepted_snapshots[0].dispatch_record_id
                == seeded.dispatch_record_id
            )
            assert factory.accepted_requests[0].disable_tools is True
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_drain_loop_logs_unexpected_exception(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """drain loop 未预期异常退出时必须记录诊断日志。"""

    caplog.set_level(logging.WARNING, logger="dayu.host.dispatch")
    with open_host_durable_store(_options(tmp_path)) as store:
        lane_controller = await LaneController.open(
            [
                LaneConfig(
                    name=_LANE_NAME,
                    capacity=1,
                    default_timeout_seconds=0.1,
                    claim_ttl_seconds=1.0,
                    heartbeat_interval_seconds=0.1,
                )
            ],
            coordinator=SQLiteLaneCoordinatorConfig(
                db_path=tmp_path / "lane-drain-loop.sqlite3"
            ),
        )
        scheduler = _FailingDrainLoopScheduler(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            local_execution=HostLocalExecutionOptions(
                lane_db_path=tmp_path / "lane-drain-loop.sqlite3",
                lane_name=_LANE_NAME,
                lane_capacity=1,
                lane_default_timeout_seconds=0.1,
                lane_claim_ttl_seconds=1.0,
                lane_heartbeat_interval_seconds=0.1,
                worker_startup_timeout_seconds=1.0,
                dispatch_poll_interval_seconds=0.01,
                runner_spec=_runner_spec(),
                runner_options=RunnerCallOptions(
                    temperature=None, max_tokens=None, top_p=None, stream=False
                ),
                agent_policy=_agent_policy(False),
                worker_factory=_FakeWorkerFactory(),
            ),
            lane_controller=lane_controller,
            host_handle_id="host-drain-loop-log",
        )
        try:
            await scheduler._drain_loop()
        finally:
            await scheduler.close()

    assert any(
        "dispatch drain loop stopped unexpectedly" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_drain_loop_logs_empty_sleep_and_close(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """drain loop 空队列睡眠和 close 取消路径写入 debug 诊断。

    :param tmp_path: pytest 临时目录。
    :param caplog: pytest 日志捕获 fixture。
    :returns: ``None``。
    """

    caplog.set_level(logging.DEBUG, logger="dayu.host.dispatch")
    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(tmp_path, store, factory)
        observed_queue = _ObservedEmptyQueue()
        scheduler._queue = observed_queue
        scheduler._drain_task = asyncio.create_task(scheduler._drain_loop())
        try:
            await observed_queue.empty_checked.wait()
        finally:
            await scheduler.close()

    assert any(
        "dispatch drain loop empty queue; sleeping" in record.getMessage()
        for record in caplog.records
    )
    assert any(
        "dispatch drain loop cancelled during close" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_scheduler_injects_durable_memory_for_no_tool_dispatch(
    tmp_path: Path,
) -> None:
    """no-tool dispatch 默认接入 durable memory provider。"""

    factory = _FakeWorkerFactory(accepted_handle=_CloseCountingHandle())
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-memory-previous",
            event_id="event-input-memory-previous",
            display_text="previous memory prompt",
            client_request_id="client-memory-previous",
            idempotency_key="idem-memory-previous",
        )
        seeded = _seed_current_run(store, session_id=session_id)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            request = factory.accepted_requests[0]
            contents = tuple(_message_text(message) for message in request.messages)
            assert result.dispatched == 1
            assert "previous memory prompt" in contents
            assert contents[-1] == "dispatch prompt"
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_uses_toolruntime_when_tooling_is_configured(
    tmp_path: Path,
) -> None:
    """真实 dispatch scheduler 在 tool-enabled 配置下接入 ToolRuntime。"""

    factory = _FakeWorkerFactory(accepted_handle=_CloseCountingHandle())
    tool = _CountingTool()
    projection = _FailingProjectionCatchup()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        _append_user_input(
            store.transaction_runner,
            session_id=session_id,
            run_id="run-tool-memory-previous",
            event_id="event-input-tool-memory-previous",
            display_text="tool-enabled previous memory prompt",
            client_request_id="client-tool-memory-previous",
            idempotency_key="idem-tool-memory-previous",
        )
        seeded = _seed_current_run(store, session_id=session_id)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            agent_policy=_agent_policy(True),
            tooling_options=_tooling_options(tool),
            projection_catchup=projection,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            request = factory.accepted_requests[0]
            contents = tuple(_message_text(message) for message in request.messages)
            assert result.dispatched == 1
            assert request.disable_tools is False
            assert request.agent_policy.allow_tool_calls is True
            assert "tool-enabled previous memory prompt" in contents
            assert [schema.function.name for schema in request.tool_schemas] == [
                "fake_dispatch_tool"
            ]
            assert scheduler._duplicate_governance_registry.active_run_count() == 1

            tool_outcome = await request.tool_executor.execute(
                _tool_execution_request(
                    seeded,
                    request,
                    ToolCallRequest(
                        tool_call_id="tool-call-dispatch",
                        name="fake_dispatch_tool",
                        arguments={"ticker": "DAYU"},
                        index_in_iteration=0,
                        provider_state=None,
                    ),
                )
            )

            assert tool.call_count == 1
            assert isinstance(tool_outcome.records[0].outcome, ToolCompletedOutcome)
            assert _read_event_by_type(
                store.transaction_runner, "TOOL_CALL_REQUESTED"
            ).run_id == seeded.run_id
            assert _read_event_by_type(
                store.transaction_runner, "TOOL_RESULT_ACCEPTED"
            ).run_id == seeded.run_id
            assert projection.calls == 1
        finally:
            await scheduler.close()
            assert scheduler._duplicate_governance_registry.active_run_count() == 0


@pytest.mark.asyncio
async def test_drain_loop_continues_when_dispatch_arrives_during_empty_window(
    tmp_path: Path,
) -> None:
    """empty / sleep / return 窗口内入队的 dispatch 不应被遗留在队列中。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        scheduler._queue = _EnqueueOnSecondEmptyQueue(_pending_dispatch(seeded))
        scheduler._drain_task = asyncio.create_task(scheduler._drain_loop())
        try:
            for _ in range(50):
                if factory.created == 1:
                    break
                await asyncio.sleep(0.01)
            assert factory.created == 1
            assert scheduler._queue.empty() is True
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_cancelled_dispatch_is_skipped_before_worker_call(
    tmp_path: Path,
) -> None:
    """worker accept 前被 direct cancel 的 dispatch 不会调用 worker。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        try:
            _mark_dispatching_and_cancel(store.transaction_runner, seeded)
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            assert result.processed == 1
            assert result.skipped == 1
            assert factory.created == 0
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_cancel_race_after_lane_acquire_releases_lane_without_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """lane acquire 后 durable cancel race 会释放 lane 且不调用 worker。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    """

    factory = _FakeWorkerFactory()
    lane_db_path = tmp_path / "lane-cancel-race.sqlite3"
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_db_path=lane_db_path,
        )
        original_recheck = scheduler._dispatch_record_still_pre_accept
        monkeypatch.setattr(
            scheduler,
            "_dispatch_record_still_pre_accept",
            _CancelBeforePreAcceptRecheck(
                transaction_runner=store.transaction_runner,
                seeded=seeded,
                original_recheck=original_recheck,
            ),
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            run, attempt, dispatch_record = _read_rows(
                store.transaction_runner, seeded
            )

            assert result.processed == 1
            assert result.skipped == 1
            assert factory.created == 0
            assert run.status is RunStatus.CANCELLED
            assert attempt.status is AttemptStatus.CANCELLED
            assert dispatch_record.status is DispatchRecordStatus.CANCELLED
            verifier = await LaneController.open(
                [
                    LaneConfig(
                        name=_LANE_NAME,
                        capacity=1,
                        default_timeout_seconds=0,
                        claim_ttl_seconds=1.0,
                        heartbeat_interval_seconds=0.1,
                    )
                ],
                coordinator=SQLiteLaneCoordinatorConfig(db_path=lane_db_path),
                owner=LaneOwner(
                    owner_id="lane-cancel-race-verifier",
                    pid=1,
                    process_start_token=None,
                ),
            )
            try:
                reopened = await verifier.acquire(_LANE_NAME, timeout_seconds=0)
                assert isinstance(reopened, LaneAcquired)
                await reopened.token.release()
            finally:
                await verifier.close()
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_dispatching_after_recheck_requires_waiting_for_lane(
    tmp_path: Path,
) -> None:
    """scheduler durable recheck 只接受已进入 waiting_for_lane 的 dispatch。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        claim = await scheduler._lane_controller.acquire(
            _LANE_NAME,
            timeout_seconds=0,
        )
        assert isinstance(claim, LaneAcquired)
        try:
            wait_row = scheduler._mark_waiting_for_lane(_pending_dispatch(seeded))
            assert wait_row is not None
            assert wait_row.status == DispatchRecordStatus.WAITING_FOR_LANE
            dispatch_record = scheduler._mark_dispatching_after_recheck(
                _pending_dispatch(seeded),
                claim.token,
            )

            assert dispatch_record is not None
            assert dispatch_record.status == DispatchRecordStatus.DISPATCHING
            assert dispatch_record.waiting_for_lane_at is not None
            assert dispatch_record.lane_name == _LANE_NAME
            assert dispatch_record.lane_claim_id == claim.token.claim_id
        finally:
            await claim.token.release()
            await scheduler.close()


@pytest.mark.asyncio
async def test_pending_dispatch_recheck_without_waiting_is_skipped(
    tmp_path: Path,
) -> None:
    """scheduler durable recheck 不允许绕过 waiting_for_lane。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        claim = await scheduler._lane_controller.acquire(
            _LANE_NAME,
            timeout_seconds=0,
        )
        assert isinstance(claim, LaneAcquired)
        try:
            dispatch_record = scheduler._mark_dispatching_after_recheck(
                _pending_dispatch(seeded),
                claim.token,
            )

            assert dispatch_record is None
        finally:
            await claim.token.release()
            await scheduler.close()


@pytest.mark.asyncio
async def test_worker_startup_timeout_closes_starting_attempt_failed(
    tmp_path: Path,
) -> None:
    """worker accept timeout 会把 STARTING Attempt 和 Run 关闭为 FAILED。"""

    factory = _FakeWorkerFactory(slow=True)
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            worker_startup_timeout_seconds=0.001,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(
                store.transaction_runner, seeded
            )
            event = _read_event_by_type(store.transaction_runner, "RUN_FAILED")
            assert result.timed_out == 1
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            assert dispatch_record.status == DispatchRecordStatus.CANCELLED
            assert json.loads(_require_text(event.reason_json))["reason"] == (
                "worker_startup_timeout"
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_queue_promotion_survives_projection_catchup_failure(
    tmp_path: Path,
) -> None:
    """scheduler promotion wakeup 中 projection catch-up 失败不阻断 promotion。"""

    factory = _FakeWorkerFactory()
    projection = _FailingProjectionCatchup()
    with open_host_durable_store(_options(tmp_path)) as store:
        session_id = _ensure_session_id(store.transaction_runner)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            projection_catchup=projection,
        )
        try:
            scheduler.wake_queue_promotion(session_id)

            assert projection.calls == 1
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_worker_accept_exception_closes_failed_and_cancels_dispatch(
    tmp_path: Path,
) -> None:
    """worker accept 非 timeout 异常按 startup failure 收口并取消 dispatch row。"""

    factory = _FakeWorkerFactory(worker=_FailingAcceptWorker())
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(
                store.transaction_runner, seeded
            )
            assert result.timed_out == 1
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            assert dispatch_record.status == DispatchRecordStatus.CANCELLED
            assert dispatch_record.cancelled_event_id is not None
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_worker_startup_closeout_error_still_releases_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """startup closeout 抛错时仍返回 timed_out 并释放 lane token。"""

    factory = _FakeWorkerFactory(worker=_FailingAcceptWorker())
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)

        def raise_closeout(record: PendingDispatchRecord) -> None:
            """模拟 durable closeout 失败。

            :param record: pending dispatch record。
            :returns: ``None``。
            :raises RuntimeError: 始终抛出 closeout 失败。
            """

            del record
            raise RuntimeError("closeout failed")

        monkeypatch.setattr(
            scheduler,
            "_closeout_worker_startup_timeout",
            raise_closeout,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            with caplog.at_level(logging.WARNING, logger="dayu.host.dispatch"):
                result = await scheduler.drain_once()

            assert result.timed_out == 1
            claim = await scheduler._lane_controller.acquire(
                _LANE_NAME,
                timeout_seconds=0,
            )
            assert isinstance(claim, LaneAcquired)
            await claim.token.release()
            assert "worker startup closeout failed; continuing" in caplog.text
            assert "error_type=RuntimeError" in caplog.text
            assert "original_error_type=RuntimeError" in caplog.text
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_dispatch_retry_exhausted_requeues_without_terminal_closeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """dispatch durable 重试耗尽只释放 lane 并重排，不按 startup timeout 收口。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)

        def raise_retry_exhausted(
            record: PendingDispatchRecord, token: LaneClaimToken
        ) -> DispatchRecordRow | None:
            """模拟 dispatching recheck 写事务 busy 重试耗尽。

            :param record: pending dispatch record。
            :param token: 已获取的 lane token。
            :returns: 不会返回。
            :raises HostTransactionRetryExhaustedError: 始终抛出以模拟 busy。
            """

            del record, token
            raise HostTransactionRetryExhaustedError(
                "dispatch recheck busy", attempts=3
            )

        monkeypatch.setattr(
            scheduler,
            "_mark_dispatching_after_recheck",
            raise_retry_exhausted,
        )
        try:
            scheduler._queue.put_nowait(_pending_dispatch(seeded))
            with caplog.at_level(logging.WARNING, logger="dayu.host.dispatch"):
                result = await scheduler.drain_once()
            await asyncio.sleep(0)

            run, attempt, dispatch_record = _read_rows(
                store.transaction_runner, seeded
            )
            assert result.processed == 1
            assert result.skipped == 1
            assert result.timed_out == 0
            assert run.status is RunStatus.RUNNING
            assert attempt.status is AttemptStatus.STARTING
            assert dispatch_record.status is DispatchRecordStatus.WAITING_FOR_LANE
            assert dispatch_record.cancelled_event_id is None
            assert scheduler._queue.qsize() == 1

            claim = await scheduler._lane_controller.acquire(
                _LANE_NAME,
                timeout_seconds=0,
            )
            assert isinstance(claim, LaneAcquired)
            await claim.token.release()
            assert "dispatch durable retry exhausted; requeueing" in caplog.text
            assert seeded.run_id in caplog.text
            assert seeded.attempt_id in caplog.text
            assert seeded.dispatch_record_id in caplog.text
            assert "error_type=HostTransactionRetryExhaustedError" in caplog.text
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_lane_acquire_timeout_closes_starting_attempt_failed(
    tmp_path: Path,
) -> None:
    """lane acquire timeout 会把 worker accept 前 Attempt 与 Run 关闭为 FAILED。"""

    factory = _FakeWorkerFactory()
    lane_db_path = tmp_path / "lane.sqlite3"
    lane_holder = await LaneController.open(
        [
            LaneConfig(
                name=_LANE_NAME,
                capacity=1,
                default_timeout_seconds=0.001,
                claim_ttl_seconds=1.0,
                heartbeat_interval_seconds=0.1,
            )
        ],
        coordinator=SQLiteLaneCoordinatorConfig(db_path=lane_db_path),
    )
    claim = await lane_holder.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(claim, LaneAcquired)
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_db_path=lane_db_path,
            lane_default_timeout_seconds=0.001,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(
                store.transaction_runner, seeded
            )
            event = _read_event_by_type(store.transaction_runner, "RUN_FAILED")
            assert result.timed_out == 1
            assert result.dispatched == 0
            assert factory.created == 0
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            assert dispatch_record.status == DispatchRecordStatus.CANCELLED
            assert json.loads(_require_text(event.reason_json))["reason"] == (
                "worker_startup_timeout"
            )
        finally:
            await scheduler.close()
            await claim.token.release()
            await lane_holder.close()


@pytest.mark.asyncio
async def test_worker_clean_eof_closes_run_failed_from_scheduler(
    tmp_path: Path,
) -> None:
    """accepted worker clean EOF 由 scheduler 映射为 FAILED closeout。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            run, attempt, _dispatch_record = await _wait_for_statuses(
                store.transaction_runner,
                seeded,
                expected_run=RunStatus.FAILED,
                expected_attempt=AttemptStatus.FAILED,
            )

            assert result.dispatched == 1
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            event = _read_event_by_type(store.transaction_runner, "RUN_FAILED")
            assert json.loads(_require_text(event.reason_json))["reason"] == (
                "stream_ended_without_terminal"
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_worker_stream_exception_closes_run_lost_from_scheduler(
    tmp_path: Path,
) -> None:
    """accepted worker stream 异常由 scheduler 映射为 LOST closeout。"""

    handle = _CrashingHandle()
    registry = ActiveWorkerRegistry()
    factory = _FakeWorkerFactory(worker=_HandleWorker(handle))
    lane_db_path = tmp_path / "lane-stream-exception.sqlite3"
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_db_path=lane_db_path,
            active_registry=registry,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            run, attempt, _dispatch_record = await _wait_for_statuses(
                store.transaction_runner,
                seeded,
                expected_run=RunStatus.LOST,
                expected_attempt=AttemptStatus.LOST,
            )
            await _wait_for_active_tasks_to_finish(scheduler)

            assert result.dispatched == 1
            assert run.status == RunStatus.LOST
            assert attempt.status == AttemptStatus.LOST
            event = _read_event_by_type(store.transaction_runner, "RUN_LOST")
            assert json.loads(_require_text(event.reason_json))["reason"] == (
                "worker_lost_before_terminal"
            )
            assert handle.closed is True
            assert registry.cancel(
                ActiveCancelMessage(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    reason="after_stream_exception",
                )
            ) is False
            verifier = await LaneController.open(
                [
                    LaneConfig(
                        name=_LANE_NAME,
                        capacity=1,
                        default_timeout_seconds=0,
                        claim_ttl_seconds=1.0,
                        heartbeat_interval_seconds=0.1,
                    )
                ],
                coordinator=SQLiteLaneCoordinatorConfig(db_path=lane_db_path),
                owner=LaneOwner(
                    owner_id="lane-stream-exception-verifier",
                    pid=1,
                    process_start_token=None,
                ),
            )
            try:
                reopened = await verifier.acquire(_LANE_NAME, timeout_seconds=0)
                assert isinstance(reopened, LaneAcquired)
                await reopened.token.release()
            finally:
                await verifier.close()
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_close_suppresses_handle_close_exception(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """scheduler close 不被 active handle cancel/close 异常打断。"""

    factory = _FakeWorkerFactory(worker=_HandleWorker(_CloseFailingHandle()))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        scheduler.wake_dispatch(_pending_dispatch(seeded))
        result = await scheduler.drain_once()

        assert result.dispatched == 1
        with caplog.at_level("WARNING", logger="dayu.host.dispatch"):
            await scheduler.close()
        assert "active worker cancel failed; continuing" in caplog.text


@pytest.mark.asyncio
async def test_scheduler_close_lets_active_task_own_handle_close(
    tmp_path: Path,
) -> None:
    """scheduler close 只发 cancel，handle close 由 active task finally 执行一次。"""

    handle = _CloseCountingHandle()
    factory = _FakeWorkerFactory(worker=_HandleWorker(handle))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        scheduler.wake_dispatch(_pending_dispatch(seeded))
        result = await scheduler.drain_once()

        assert result.dispatched == 1
        await scheduler.close()
        assert handle.cancel_count == 1
        assert handle.close_count == 1


@pytest.mark.asyncio
async def test_scheduler_close_during_active_events_releases_all_resources(
    tmp_path: Path,
) -> None:
    """scheduler close 期间活跃事件消费被取消后会释放 lane 与 registry。"""

    handle = _ControlledBlockingHandle()
    registry = ActiveWorkerRegistry()
    factory = _FakeWorkerFactory(worker=_HandleWorker(handle))
    lane_db_path = tmp_path / "lane-close-active.sqlite3"
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_db_path=lane_db_path,
            active_registry=registry,
        )
        scheduler.wake_dispatch(_pending_dispatch(seeded))
        result = await scheduler.drain_once()
        await handle.events_started.wait()

        assert result.dispatched == 1
        await scheduler.close()

        assert handle.cancel_count == 1
        assert handle.close_count == 1
        assert handle.events_finalized.is_set()
        assert registry.cancel(
            ActiveCancelMessage(
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                reason="after_scheduler_close",
            )
        ) is False
        verifier = await LaneController.open(
            [
                LaneConfig(
                    name=_LANE_NAME,
                    capacity=1,
                    default_timeout_seconds=0,
                    claim_ttl_seconds=1.0,
                    heartbeat_interval_seconds=0.1,
                )
            ],
            coordinator=SQLiteLaneCoordinatorConfig(db_path=lane_db_path),
            owner=LaneOwner(
                owner_id="lane-verifier",
                pid=1,
                process_start_token=None,
            ),
        )
        try:
            reopened = await verifier.acquire(_LANE_NAME, timeout_seconds=0)
            assert isinstance(reopened, LaneAcquired)
            await reopened.token.release()
        finally:
            await verifier.close()


@pytest.mark.asyncio
async def test_default_active_registry_is_scheduler_local(tmp_path: Path) -> None:
    """未显式注入 registry 时，不同 scheduler 不共享默认 registry。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        first = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            lane_db_path=tmp_path / "lane-first.sqlite3",
        )
        second = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            lane_db_path=tmp_path / "lane-second.sqlite3",
        )
        try:
            assert first._active_registry is not second._active_registry
        finally:
            await first.close()
            await second.close()


@pytest.mark.asyncio
async def test_consume_pre_event_exception_releases_lane_and_unregisters(
    tmp_path: Path,
) -> None:
    """consume task 在 pre-event 构造失败时仍释放 lane 并注销 active worker。"""

    handle = _FlakyLocalWorkerIdHandle()
    registry = ActiveWorkerRegistry()
    factory = _FakeWorkerFactory(worker=_HandleWorker(handle))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            active_registry=registry,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            await _wait_for_active_tasks_to_finish(scheduler)

            assert result.dispatched == 1
            assert handle.close_count == 1
            assert registry.cancel(
                ActiveCancelMessage(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    reason="test_cancel_after_failure",
                )
            ) is False
            claim = await scheduler._lane_controller.acquire(
                _LANE_NAME,
                timeout_seconds=0,
            )
            assert isinstance(claim, LaneAcquired)
            await claim.token.release()
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_with_default_local_proxy_stream_error_closes_lost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 DefaultLocalProxy 的 Engine stream 异常经 scheduler 映射为 LOST。"""

    async def raising_run_agent_messages(
        request: AgentRunRequest,
    ) -> AsyncIterator[EngineEvent]:
        """模拟 Engine public entry 在 stream 迭代时抛错。

        :param request: Engine request。
        :returns: 不会正常返回事件。
        :raises RuntimeError: 始终抛出 stream 异常。
        """

        del request
        raise RuntimeError("engine stream failed")
        if False:
            yield _unreachable_engine_event()

    monkeypatch.setattr(
        "dayu.host.local_proxy.run_agent_messages",
        raising_run_agent_messages,
    )

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            DefaultLocalEngineWorkerFactory(),
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            run, attempt, _dispatch_record = await _wait_for_statuses(
                store.transaction_runner,
                seeded,
                expected_run=RunStatus.LOST,
                expected_attempt=AttemptStatus.LOST,
            )

            assert result.dispatched == 1
            assert run.status == RunStatus.LOST
            assert attempt.status == AttemptStatus.LOST
            event = _read_event_by_type(store.transaction_runner, "RUN_LOST")
            assert json.loads(_require_text(event.reason_json))["reason"] == (
                "worker_lost_before_terminal"
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_closes_default_local_proxy_after_terminal_before_late_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """terminal accepted 后 scheduler 关闭 worker stream，不继续读取 late event。"""

    stream_finalized = asyncio.Event()
    late_event_reached = asyncio.Event()

    async def terminal_then_late_run_agent_messages(
        request: AgentRunRequest,
    ) -> AsyncIterator[EngineEvent]:
        """先产出 terminal，再暴露一个不应被读取的 late event。

        :param request: Engine request。
        :returns: 受控 EngineEvent stream。
        """

        try:
            yield EngineEvent(
                occurred_at=_NOW,
                session_id=request.session_id,
                run_id=request.run_id,
                type=EngineEventType.FINAL_ANSWER,
                data=FinalAnswerData(
                    content="done",
                    filtered=False,
                    degraded=False,
                    finish_reason=FinishReason.STOP,
                ),
                metadata=None,
            )
            late_event_reached.set()
            yield EngineEvent(
                occurred_at=_NOW,
                session_id=request.session_id,
                run_id=request.run_id,
                type=EngineEventType.RUN_FAILED,
                data=RunFailedData(
                    error_code="late",
                    message="late event must not be consumed",
                    provider_request_id=None,
                    recoverable=False,
                ),
                metadata=None,
            )
        finally:
            stream_finalized.set()

    monkeypatch.setattr(
        "dayu.host.local_proxy.run_agent_messages",
        terminal_then_late_run_agent_messages,
    )

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            DefaultLocalEngineWorkerFactory(),
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            run, attempt, _dispatch_record = await _wait_for_statuses(
                store.transaction_runner,
                seeded,
                expected_run=RunStatus.SUCCEEDED,
                expected_attempt=AttemptStatus.SUCCEEDED,
            )
            await _wait_for_active_tasks_to_finish(scheduler)

            assert result.dispatched == 1
            assert run.status == RunStatus.SUCCEEDED
            assert attempt.status == AttemptStatus.SUCCEEDED
            assert stream_finalized.is_set()
            assert not late_event_reached.is_set()
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_pre_start_governance_soft_threshold_compacts_before_attempt(
    tmp_path: Path,
) -> None:
    """soft threshold 在 Attempt 创建前触发一次 proactive compact。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-soft-compact",
            display_text=_soft_threshold_prompt(),
        )
        assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 0
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            scheduler.wake_queue_promotion(seeded.session_id)
            event_types = _event_types_for_run(
                store.transaction_runner, seeded.run_id
            )

            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 1
            assert event_types.index(CONTEXT_COMPACTION_REQUESTED) < event_types.index(
                CONTEXT_COMPACTED
            )
            assert event_types.index(CONTEXT_COMPACTED) < event_types.index(
                "RUN_STARTED"
            )
            assert event_types.index("RUN_STARTED") < event_types.index(
                "ATTEMPT_STARTED"
            )
            assert _run_status(store.transaction_runner, seeded.run_id) == (
                RunStatus.RUNNING
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_pre_start_governance_compact_failure_is_attempt_free(
    tmp_path: Path,
) -> None:
    """proactive compact 缺少 compactor/artifact store 时 fail closed 且零 Attempt。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-compact-failure",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
        )
        try:
            scheduler.wake_queue_promotion(seeded.session_id)

            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 0
            assert _run_status(store.transaction_runner, seeded.run_id) == (
                RunStatus.FAILED
            )
            assert _event_types_for_run(store.transaction_runner, seeded.run_id) == (
                "USER_INPUT_ACCEPTED",
                "RUN_ACCEPTED",
                CONTEXT_COMPACTION_REQUESTED,
                CONTEXT_COMPACTION_FAILED,
                "RUN_FAILED",
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_pre_start_governance_proactive_count_limit_blocks_second_compact(
    tmp_path: Path,
) -> None:
    """durable proactive request 计数阻止同一 Run 二次 compact 循环。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-compact-limit",
            display_text=_soft_threshold_prompt(),
        )
        _append_proactive_compaction_requested(
            store.transaction_runner,
            seeded=seeded,
            event_id="event-existing-proactive-request",
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            scheduler.wake_queue_promotion(seeded.session_id)

            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 0
            assert _run_status(store.transaction_runner, seeded.run_id) == (
                RunStatus.FAILED
            )
            assert _event_types_for_run(store.transaction_runner, seeded.run_id).count(
                CONTEXT_COMPACTION_REQUESTED
            ) == 1
            failed = _read_event_by_type(
                store.transaction_runner, CONTEXT_COMPACTION_FAILED
            )
            assert json.loads(_require_text(failed.payload_json))[
                "failure_reason"
            ] == "proactive_compact_limit_reached"
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_pre_start_governance_corrupted_compact_count_fails_closed(
    tmp_path: Path,
) -> None:
    """committed compact-count fact 损坏时 dispatch 前 fail closed。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-corrupted-compact-count",
            display_text=_soft_threshold_prompt(),
        )
        _append_corrupted_compaction_requested(
            store.transaction_runner,
            seeded=seeded,
            event_id="event-corrupted-proactive-request",
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            scheduler.wake_queue_promotion(seeded.session_id)

            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 0
            assert _run_status(store.transaction_runner, seeded.run_id) == (
                RunStatus.FAILED
            )
            failed = _read_event_by_type(
                store.transaction_runner, CONTEXT_COMPACTION_FAILED
            )
            assert json.loads(_require_text(failed.payload_json))[
                "failure_reason"
            ] == "proactive_compact_count_unreadable"
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_multi_turn_proactive_compact_feeds_subsequent_run_input(
    tmp_path: Path,
) -> None:
    """多轮 Run 经 proactive compact 后把 compact memory 注入后续 Engine request。"""

    factory = _FinalAnswerWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            first = await _dispatch_accepted_final_run(
                scheduler=scheduler,
                store=store,
                factory=factory,
                run_id="run-multi-turn-1",
                display_text="first raw turn for memory",
                expected_request_count=1,
            )
            assert first.session_id != ""

            await _dispatch_accepted_final_run(
                scheduler=scheduler,
                store=store,
                factory=factory,
                run_id="run-multi-turn-2",
                display_text="follow-up under budget",
                expected_request_count=2,
            )
            second_contents = tuple(
                _message_text(message)
                for message in factory.accepted_requests[1].messages
            )
            assert "first raw turn for memory" in second_contents
            assert second_contents[-1] == "follow-up under budget"

            compacted = await _dispatch_accepted_final_run(
                scheduler=scheduler,
                store=store,
                factory=factory,
                run_id="run-multi-turn-3",
                display_text=_soft_threshold_prompt(),
                expected_request_count=3,
            )
            event_types = _event_types_for_run(
                store.transaction_runner, compacted.run_id
            )
            compacted_request_contents = tuple(
                content
                for content in (
                    _message_text(message)
                    for message in factory.accepted_requests[2].messages
                )
                if content is not None
            )
            assert event_types.index(CONTEXT_COMPACTED) < event_types.index(
                "RUN_STARTED"
            )
            assert _content_index(
                compacted_request_contents,
                "Accepted compact artifact is available for this run.",
            ) < len(compacted_request_contents) - 1
            assert compacted_request_contents[-1] == _soft_threshold_prompt()

            await _dispatch_accepted_final_run(
                scheduler=scheduler,
                store=store,
                factory=factory,
                run_id="run-multi-turn-4",
                display_text="after compact prompt",
                expected_request_count=4,
            )
            after_compact_contents = tuple(
                content
                for content in (
                    _message_text(message)
                    for message in factory.accepted_requests[3].messages
                )
                if content is not None
            )
            joined = "\n\n".join(after_compact_contents)
            goal_index = _content_index(after_compact_contents, "current_goal=")
            raw_index = after_compact_contents.index("follow-up under budget")
            episode_index = _content_index(
                after_compact_contents, "Memory episode summaries:"
            )

            assert "current_goal=" in joined
            assert "confirmed_subject=subject:" in joined
            assert "title=Session " in joined
            assert goal_index < raw_index < episode_index
            assert after_compact_contents[-1] == "after compact prompt"
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_reactive_overflow_recovers_and_dispatches_new_attempt(
    tmp_path: Path,
) -> None:
    """worker reactive overflow 经 compact 后创建新 Attempt 并完成 dispatch。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        factory = _ReactiveRecoveryWorkerFactory()
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            assert (await scheduler.drain_once()).dispatched == 1
            await _wait_for_run_status(
                store.transaction_runner,
                seeded.run_id,
                expected_run=RunStatus.SUCCEEDED,
            )
            await _wait_for_active_tasks_to_finish(scheduler)

            assert len(factory.accepted_snapshots) == 2
            assert factory.accepted_snapshots[0].attempt_id == seeded.attempt_id
            assert factory.accepted_snapshots[1].attempt_id != seeded.attempt_id
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1
            assert _event_count(store.transaction_runner, "RUN_RECOVERING") == 1
            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 2
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_reactive_recovery_does_not_clear_duplicate_registry(
    tmp_path: Path,
) -> None:
    """reactive recovery accepted 停止旧 worker 但不清理同 Run duplicate registry。"""

    tool = _CountingTool()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        factory = _ReactiveRecoveryWorkerFactory(final_blocks=True)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            agent_policy=_agent_policy(True),
            tooling_options=_tooling_options(tool),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            assert (await scheduler.drain_once()).dispatched == 1
            await _wait_for_accepted_snapshot_count(factory, 2)

            assert factory.accepted_snapshots[0].attempt_id == seeded.attempt_id
            assert factory.accepted_snapshots[1].attempt_id != seeded.attempt_id
            assert scheduler._duplicate_governance_registry.active_run_count() == 1
            assert _run_status(store.transaction_runner, seeded.run_id) == (
                RunStatus.RUNNING
            )
        finally:
            await scheduler.close()


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


async def _open_scheduler(
    tmp_path: Path,
    store: HostDurableStore,
    factory: LocalEngineWorkerFactory,
    *,
    worker_startup_timeout_seconds: float = 1.0,
    lane_db_path: Path | None = None,
    lane_default_timeout_seconds: float = 0.01,
    active_registry: ActiveWorkerRegistry | None = None,
    agent_policy: AgentPolicy | None = None,
    tooling_options: HostToolingOptions | None = None,
    projection_catchup: ProjectionCatchupPort | None = None,
    context_budget_policy: ContextBudgetPolicy | None = None,
    context_compactor: ContextCompactor | None = None,
    compact_artifact_root: Path | None = None,
) -> HostDispatchScheduler:
    """打开测试 scheduler。

    :param tmp_path: pytest 临时目录。
    :param store: durable store。
    :param factory: worker factory。
    :param worker_startup_timeout_seconds: worker startup timeout。
    :param lane_db_path: runtime lane DB 路径。
    :param lane_default_timeout_seconds: lane acquire 默认 timeout。
    :param active_registry: active worker registry。
    :param agent_policy: 可选 AgentPolicy；无则使用 no-tool policy。
    :param tooling_options: 可选 Host 工具装配选项。
    :param projection_catchup: 可选 projection catch-up port。
    :param context_budget_policy: 可选 pre-start context budget policy。
    :param context_compactor: 可选 context compactor。
    :param compact_artifact_root: 可选 compact artifact 根目录。
    :returns: scheduler。
    """

    return await HostDispatchScheduler.open(
        transaction_runner=store.transaction_runner,
        local_execution=HostLocalExecutionOptions(
            lane_db_path=lane_db_path if lane_db_path is not None else tmp_path / "lane.sqlite3",
            lane_name=_LANE_NAME,
            lane_capacity=1,
            lane_default_timeout_seconds=lane_default_timeout_seconds,
            lane_claim_ttl_seconds=1.0,
            lane_heartbeat_interval_seconds=0.1,
            worker_startup_timeout_seconds=worker_startup_timeout_seconds,
            dispatch_poll_interval_seconds=0.01,
            runner_spec=_runner_spec(),
            runner_options=RunnerCallOptions(
                temperature=None, max_tokens=None, top_p=None, stream=False
            ),
            agent_policy=(
                agent_policy if agent_policy is not None else _agent_policy(False)
            ),
            worker_factory=factory,
            tooling_options=tooling_options,
            context_budget_policy=context_budget_policy,
            context_compactor=context_compactor,
            compact_artifact_root=compact_artifact_root,
        ),
        host_handle_id="host-test",
        active_registry=active_registry,
        projection_catchup_port=projection_catchup,
    )


def _runner_spec() -> RunnerSpec:
    """构造测试 RunnerSpec。

    :returns: RunnerSpec。
    """

    return RunnerSpec(
        provider="test",
        model="test-model",
        endpoint="https://example.invalid",
        api_key_ref="secret:test",
        headers={},
        supports_tool_calling=False,
        supports_streaming=False,
        supports_stream_usage=False,
        default_timeout_seconds=1.0,
        max_retries=0,
        provider_request=None,
    )


def _tooling_options(tool: _CountingTool) -> HostToolingOptions:
    """构造 tool-enabled dispatch 测试用工具装配选项。

    :param tool: 测试业务工具 callable。
    :returns: HostToolingOptions。
    """

    return HostToolingOptions(
        business_tool_bundle=ToolBundle(
            definitions=(_tool_definition("fake_dispatch_tool", tool),)
        ),
        source_refs=(
            ToolBundleSourceRef(
                source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
                source_id="dispatch-tool-test",
            ),
        ),
    )


def _tool_definition(name: str, tool: _CountingTool) -> ToolDefinition:
    """构造测试工具声明。

    :param name: 工具名。
    :param tool: 测试工具 callable。
    :returns: ToolDefinition。
    """

    return ToolDefinition(
        name=name,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=name,
                description="dispatch fake tool",
                parameters=_tool_parameters(),
            ),
        ),
        callable=tool,
        truncate=None,
        display=None,
        tags=("dispatch",),
    )


def _tool_parameters() -> ToolParametersSchema:
    """构造测试工具参数 schema。

    :returns: ToolParametersSchema。
    """

    properties: dict[str, JsonValue] = {"ticker": {"type": "string"}}
    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=("ticker",),
        additional_properties=False,
    )


def _tool_execution_request(
    seeded: _SeededRun, request: AgentRunRequest, call: ToolCallRequest
) -> BatchToolExecutionRequest:
    """构造 ToolRuntime 批式执行请求。

    :param seeded: seeded Run refs。
    :param request: scheduler 传给 worker 的 AgentRunRequest。
    :param call: 工具调用请求。
    :returns: BatchToolExecutionRequest。
    """

    return BatchToolExecutionRequest(
        calls=(call,),
        context=BatchToolExecutionContext(
            run_id=seeded.run_id,
            session_id=seeded.session_id,
            iteration_id="iteration-dispatch-tool",
            timeout_seconds=1.0,
            cancellation_token=request.cancellation_token,
            correlation_id="correlation-dispatch-tool",
        ),
    )


def _message_text(message: AgentMessage) -> str | None:
    """读取 Agent message 的文本内容。

    :param message: Agent message。
    :returns: 文本内容；assistant 空内容时返回 ``None``。
    """

    return message.content


def _agent_policy(allow_tool_calls: bool) -> AgentPolicy:
    """构造测试 AgentPolicy。

    :param allow_tool_calls: 是否允许工具调用。
    :returns: AgentPolicy。
    """

    return AgentPolicy(
        max_iterations=1,
        continuation_max_attempts=0,
        allow_tool_calls=allow_tool_calls,
        tool_execution_timeout_seconds=1.0,
    )


def _seed_current_run(
    store: HostDurableStore, *, session_id: str | None = None
) -> _SeededRun:
    """创建 running Run、STARTING Attempt 和 pending dispatch。

    :param store: durable store。
    :param session_id: 可选已有 Session id；不传则创建默认测试 Session。
    :returns: seeded run 摘要。
    """

    actual_session_id = (
        _ensure_session_id(store.transaction_runner)
        if session_id is None
        else session_id
    )
    seeded = _SeededRun(
        session_id=actual_session_id,
        run_id="run-dispatch",
        attempt_id="attempt-dispatch",
        execution_id="execution-dispatch",
        dispatch_record_id="dispatch-dispatch",
    )
    input_event_sequence = _append_user_input(
        store.transaction_runner,
        session_id=actual_session_id,
        run_id=seeded.run_id,
        event_id="event-input-dispatch",
    )

    def _operation(transaction: HostTransaction) -> None:
        create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            CreateRunningRunInput(
                session_id=actual_session_id,
                run_id=seeded.run_id,
                client_request_id="client-dispatch",
                input_event_id="event-input-dispatch",
                input_event_sequence=input_event_sequence,
                run_accepted_event_id="event-run-accepted-dispatch",
                run_started_event_id="event-run-started-dispatch",
                attempt_started_event_id="event-attempt-started-dispatch",
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                dispatch_record_id=seeded.dispatch_record_id,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                idempotency_key="idem-dispatch",
                execution_target="target-dispatch",
                queue_policy="queue",
                start_reason=RunStartReason.INITIAL,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )

    store.transaction_runner.run_write(_operation)
    return seeded


def _seed_accepted_run(
    store: HostDurableStore,
    *,
    run_id: str,
    display_text: str,
) -> _AcceptedSeededRun:
    """创建 pre-start accepted Run，不创建 Attempt 或 dispatch。

    :param store: durable store。
    :param run_id: Run id。
    :param display_text: 当前用户输入文本。
    :returns: accepted Run 摘要。
    """

    session_id = _ensure_session_id(store.transaction_runner)
    input_event_id = f"event-input-{run_id}"
    input_event_sequence = _append_user_input(
        store.transaction_runner,
        session_id=session_id,
        run_id=run_id,
        event_id=input_event_id,
        display_text=display_text,
        client_request_id=f"client-{run_id}",
        idempotency_key=f"idem-input-{run_id}",
    )

    def _operation(transaction: HostTransaction) -> None:
        result = create_accepted_run_in_transaction(
            transaction,
            EventLogStore(),
            CreateAcceptedRunInput(
                session_id=session_id,
                run_id=run_id,
                client_request_id=f"client-{run_id}",
                input_event_id=input_event_id,
                input_event_sequence=input_event_sequence,
                run_accepted_event_id=f"event-run-accepted-{run_id}",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                idempotency_key=f"idem-run-{run_id}",
                execution_target="target-dispatch",
                queue_policy="queue",
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        assert result.run is not None
        assert result.run.status == RunStatus.ACCEPTED

    store.transaction_runner.run_write(_operation)
    return _AcceptedSeededRun(session_id=session_id, run_id=run_id)


def _soft_compact_policy() -> ContextBudgetPolicy:
    """构造会对测试 prompt 触发 soft compact 的预算策略。

    :returns: context budget policy。
    """

    return default_context_budget_policy(
        context_window_size=_SOFT_CONTEXT_WINDOW_SIZE,
        reserved_output_tokens=_SOFT_RESERVED_OUTPUT_TOKENS,
        hard_threshold_tokens=_SOFT_HARD_THRESHOLD_TOKENS,
        safety_margin_ratio=_SOFT_SAFETY_MARGIN_RATIO,
        minimum_protection_tokens=1,
        policy_ref="test-soft-compact-policy",
    )


def _soft_threshold_prompt() -> str:
    """返回触发 soft threshold 且未达 hard threshold 的测试 prompt。

    :returns: 测试 prompt。
    """

    return "x" * _SOFT_THRESHOLD_PROMPT_CHAR_COUNT


def _append_proactive_compaction_requested(
    transaction_runner: HostTransactionRunner,
    *,
    seeded: _AcceptedSeededRun,
    event_id: str,
) -> None:
    """追加一条合法 proactive compaction requested fact。

    :param transaction_runner: transaction runner。
    :param seeded: accepted Run 摘要。
    :param event_id: 事件 id。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                attempt_id=None,
                execution_id=None,
                event_type=CONTEXT_COMPACTION_REQUESTED,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json=build_context_compaction_requested_payload(
                    trigger_source=ContextCompactionTriggerSource.PROACTIVE,
                    budget_reason=ContextBudgetDecision.COMPACT_SOFT_THRESHOLD.value,
                    budget_snapshot_ref=_CALL_CONTEXT_DIGEST,
                    input_snapshot_cursor=1,
                    estimator_digest=_CALL_CONTEXT_DIGEST,
                    policy_ref="test-soft-compact-policy",
                    provider_request_id=None,
                    provider_error_ref=None,
                    attempt_id=None,
                    execution_id=None,
                ),
                payload_ref=None,
                payload_digest=None,
            ),
        )

    transaction_runner.run_write(_operation)


def _append_corrupted_compaction_requested(
    transaction_runner: HostTransactionRunner,
    *,
    seeded: _AcceptedSeededRun,
    event_id: str,
) -> None:
    """追加一条损坏的 compaction requested fact。

    :param transaction_runner: transaction runner。
    :param seeded: accepted Run 摘要。
    :param event_id: 事件 id。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                attempt_id=None,
                execution_id=None,
                event_type=CONTEXT_COMPACTION_REQUESTED,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason=None,
                payload_json={"trigger_source": 7},
                payload_ref=None,
                payload_digest=None,
            ),
        )

    transaction_runner.run_write(_operation)


def _ensure_session_id(transaction_runner: HostTransactionRunner) -> str:
    """确保测试 Session 存在。

    :param transaction_runner: transaction runner。
    :returns: session id。
    """

    return ensure_session(
        transaction_runner,
        EnsureSessionRequest(scope="workspace", slot_key="slot", metadata=()),
    ).snapshot.session_id


def _append_user_input(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
    display_text: str = "dispatch prompt",
    client_request_id: str = "client-dispatch",
    idempotency_key: str = "idem-input",
) -> int:
    """追加 USER_INPUT_ACCEPTED。

    :param transaction_runner: transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :param display_text: 用户输入展示文本。
    :param client_request_id: EventLog client request id。
    :param idempotency_key: EventLog idempotency key。
    :returns: 追加后的 EventLog sequence。
    """

    def _operation(transaction: HostTransaction) -> int:
        event = EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=run_id,
                attempt_id=None,
                execution_id=None,
                event_type="USER_INPUT_ACCEPTED",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=client_request_id,
                idempotency_key=idempotency_key,
                policy_decision=None,
                reason=None,
                payload_json={
                    "display_text": display_text,
                    "operation_kind": "unit_test",
                    "execution_target": "target-dispatch",
                },
                payload_ref=None,
                payload_digest=None,
            ),
        )
        return event.row.event_sequence

    return transaction_runner.run_write(_operation)


def _pending_dispatch(seeded: _SeededRun) -> PendingDispatchRecord:
    """构造 pending dispatch wakeup 摘要。

    :param seeded: seeded run。
    :returns: pending dispatch record。
    """

    return PendingDispatchRecord(
        dispatch_record_id=seeded.dispatch_record_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
        execution_target="target-dispatch",
        worker_kind=WorkerKind.LOCAL,
    )


def _read_rows(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> tuple[RunRow, AttemptRow, DispatchRecordRow]:
    """读取 Run、Attempt 与 dispatch row。

    :param transaction_runner: transaction runner。
    :param seeded: seeded run。
    :returns: 三个 durable row。
    """

    def _operation(
        transaction: HostTransaction,
    ) -> tuple[RunRow, AttemptRow, DispatchRecordRow]:
        run = read_run_by_id(transaction, seeded.run_id)
        attempt = read_attempt_by_id(transaction, seeded.attempt_id)
        dispatch_record = read_dispatch_record_by_attempt_id(
            transaction, seeded.attempt_id
        )
        assert run is not None
        assert attempt is not None
        assert dispatch_record is not None
        return run, attempt, dispatch_record

    return transaction_runner.run_read(_operation)


def _run_status(transaction_runner: HostTransactionRunner, run_id: str) -> RunStatus:
    """读取 Run 状态。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :returns: Run 状态。
    :raises AssertionError: Run 缺失时抛出。
    """

    def _operation(transaction: HostTransaction) -> RunStatus:
        row = read_run_by_id(transaction, run_id)
        assert row is not None
        return row.status

    return transaction_runner.run_read(_operation)


def _attempt_count_for_run(
    transaction_runner: HostTransactionRunner, run_id: str
) -> int:
    """统计指定 Run 的 Attempt row 数。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :returns: Attempt row 数。
    """

    def _operation(transaction: HostTransaction) -> int:
        row = transaction.fetchone(
            "SELECT COUNT(*) AS count FROM host_attempts WHERE run_id = ?",
            (run_id,),
        )
        assert row is not None
        value = row.get("count")
        assert isinstance(value, int)
        return value

    return transaction_runner.run_read(_operation)


def _event_types_for_run(
    transaction_runner: HostTransactionRunner, run_id: str
) -> tuple[str, ...]:
    """按 sequence 读取指定 Run 的 EventLog 类型。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :returns: event type 元组。
    """

    def _operation(transaction: HostTransaction) -> tuple[str, ...]:
        rows = EventLogStore().read_events_after(transaction, 0, limit=200)
        return tuple(row.event_type for row in rows if row.run_id == run_id)

    return transaction_runner.run_read(_operation)


def _event_count(transaction_runner: HostTransactionRunner, event_type: str) -> int:
    """统计指定 event type 数量。

    :param transaction_runner: transaction runner。
    :param event_type: event type。
    :returns: 事件数量。
    """

    def _operation(transaction: HostTransaction) -> int:
        return sum(
            1
            for row in EventLogStore().read_events_after(transaction, 0, limit=200)
            if row.event_type == event_type
        )

    return transaction_runner.run_read(_operation)


async def _wait_for_run_status(
    transaction_runner: HostTransactionRunner,
    run_id: str,
    *,
    expected_run: RunStatus,
) -> RunRow:
    """等待 Run 到达指定状态。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :param expected_run: 期望 Run 状态。
    :returns: Run row。
    :raises AssertionError: 超时未达到目标状态时抛出。
    """

    for _index in range(200):
        row = transaction_runner.run_read(
            lambda transaction: read_run_by_id(transaction, run_id)
        )
        assert row is not None
        if row.status == expected_run:
            return row
        await asyncio.sleep(0.01)
    row = transaction_runner.run_read(
        lambda transaction: read_run_by_id(transaction, run_id)
    )
    assert row is not None
    raise AssertionError(f"run status did not converge: {row.status.value}")


async def _dispatch_accepted_final_run(
    *,
    scheduler: HostDispatchScheduler,
    store: HostDurableStore,
    factory: _FinalAnswerWorkerFactory,
    run_id: str,
    display_text: str,
    expected_request_count: int,
) -> _AcceptedSeededRun:
    """创建 accepted Run，经 scheduler gate dispatch，并等待 final_answer 收口。

    :param scheduler: Host dispatch scheduler。
    :param store: durable store。
    :param factory: 记录 Engine request 的 final-answer worker factory。
    :param run_id: 新 Run id。
    :param display_text: 当前用户输入文本。
    :param expected_request_count: 期望累计 accept 次数。
    :returns: accepted Run 摘要。
    :raises AssertionError: dispatch 或状态收口未在测试时间内完成时抛出。
    """

    seeded = _seed_accepted_run(
        store,
        run_id=run_id,
        display_text=display_text,
    )
    scheduler.wake_queue_promotion(seeded.session_id)
    await _wait_for_final_request_count(factory, expected_request_count)
    await _wait_for_run_status(
        store.transaction_runner,
        seeded.run_id,
        expected_run=RunStatus.SUCCEEDED,
    )
    return seeded


async def _wait_for_final_request_count(
    factory: _FinalAnswerWorkerFactory, expected_count: int
) -> None:
    """等待 final-answer worker factory 接受指定次数。

    :param factory: final-answer worker factory。
    :param expected_count: 期望累计 accept 次数。
    :returns: ``None``。
    :raises AssertionError: 超时未达到次数时抛出。
    """

    for _index in range(200):
        if len(factory.accepted_requests) >= expected_count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(
        f"worker request count did not converge: {len(factory.accepted_requests)}"
    )


def _content_index(contents: tuple[str, ...], expected_fragment: str) -> int:
    """返回包含指定片段的 message index。

    :param contents: Engine request message 文本。
    :param expected_fragment: 需要查找的文本片段。
    :returns: 第一个匹配 index。
    :raises AssertionError: 找不到片段时抛出。
    """

    for index, content in enumerate(contents):
        if expected_fragment in content:
            return index
    raise AssertionError(f"message fragment not found: {expected_fragment}")


async def _wait_for_accepted_snapshot_count(
    factory: _ReactiveRecoveryWorkerFactory, expected_count: int
) -> None:
    """等待 reactive worker factory 接受指定次数。

    :param factory: reactive worker factory。
    :param expected_count: 期望 accept 次数。
    :returns: ``None``。
    :raises AssertionError: 超时未达到次数时抛出。
    """

    for _index in range(200):
        if len(factory.accepted_snapshots) >= expected_count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(
        "accepted snapshot count did not converge: "
        f"{len(factory.accepted_snapshots)}"
    )


async def _wait_for_statuses(
    transaction_runner: HostTransactionRunner,
    seeded: _SeededRun,
    *,
    expected_run: RunStatus,
    expected_attempt: AttemptStatus,
) -> tuple[RunRow, AttemptRow, DispatchRecordRow]:
    """等待异步 worker consume task 写入目标 Run / Attempt 状态。

    :param transaction_runner: transaction runner。
    :param seeded: seeded run。
    :param expected_run: 期望 Run 状态。
    :param expected_attempt: 期望 Attempt 状态。
    :returns: 目标状态下的 durable rows。
    :raises AssertionError: 超时未达到目标状态时抛出。
    """

    for _index in range(100):
        rows = _read_rows(transaction_runner, seeded)
        run, attempt, _dispatch_record = rows
        if run.status == expected_run and attempt.status == expected_attempt:
            return rows
        await asyncio.sleep(0.01)
    run, attempt, _dispatch_record = _read_rows(transaction_runner, seeded)
    raise AssertionError(
        "status did not converge: "
        f"run={run.status.value} attempt={attempt.status.value}"
    )


async def _wait_for_active_tasks_to_finish(
    scheduler: HostDispatchScheduler,
) -> None:
    """等待 scheduler active consume tasks 全部结束。

    :param scheduler: 目标 scheduler。
    :returns: ``None``。
    :raises AssertionError: 超时仍有 active task 时抛出。
    """

    for _index in range(100):
        if not scheduler._active_tasks:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("active tasks did not finish")


def _read_event_by_type(
    transaction_runner: HostTransactionRunner, event_type: str
) -> EventLogRow:
    """按事件类型读取单条事件。

    :param transaction_runner: transaction runner。
    :param event_type: 事件类型。
    :returns: event row。
    """

    def _operation(transaction: HostTransaction) -> EventLogRow:
        rows = EventLogStore().read_events_after(transaction, 0, limit=100)
        for row in rows:
            if row.event_type == event_type:
                return row
        raise AssertionError(f"missing event type {event_type}")

    return transaction_runner.run_read(_operation)


def _mark_dispatching_and_cancel(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> None:
    """把 dispatch 推进到 pre-accept dispatching 后 direct cancel。

    :param transaction_runner: transaction runner。
    :param seeded: seeded run。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-test",
            lane_name=_LANE_NAME,
            waiting_for_lane_at="2026-05-15T01:02:03.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-test",
            lane_name=_LANE_NAME,
            lane_claim_id="claim-before-cancel",
            lane_owner_id="owner-before-cancel",
            lane_acquired_at="2026-05-15T01:02:03.000000Z",
            dispatching_at="2026-05-15T01:02:03.000000Z",
        )
        cancel_predispatch_starting_in_transaction(
            transaction,
            EventLogStore(),
            CancelPredispatchStartingInput(
                run_id=seeded.run_id,
                cancel_request_event_id="event-cancel-requested",
                attempt_cancelled_event_id="event-attempt-cancelled",
                run_cancelled_event_id="event-run-cancelled",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id="client-cancel",
                idempotency_key="idem-cancel",
                reason="user_stop",
                mode=CancelMode.GRACEFUL,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )

    transaction_runner.run_write(_operation)


def _cancel_predispatch_dispatching(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> None:
    """取消已进入 pre-accept dispatching 的 seeded Run。

    :param transaction_runner: transaction runner。
    :param seeded: seeded run。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        """执行 durable cancel。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

        cancel_predispatch_starting_in_transaction(
            transaction,
            EventLogStore(),
            CancelPredispatchStartingInput(
                run_id=seeded.run_id,
                cancel_request_event_id="event-cancel-race-requested",
                attempt_cancelled_event_id="event-cancel-race-attempt",
                run_cancelled_event_id="event-cancel-race-run",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id="client-cancel-race",
                idempotency_key="idem-cancel-race",
                reason="user_stop",
                mode=CancelMode.GRACEFUL,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )

    transaction_runner.run_write(_operation)


def _unreachable_engine_event() -> EngineEvent:
    """构造不可达 EngineEvent 占位。

    :returns: 当前函数不会被执行。
    :raises AssertionError: 若测试错误执行到该分支则抛出。
    """

    raise AssertionError("unreachable")


def _require_text(value: str | None) -> str:
    """断言可选文本非空。

    :param value: 可选文本。
    :returns: 非空文本。
    :raises AssertionError: 文本缺失时抛出。
    """

    assert value is not None
    return value
