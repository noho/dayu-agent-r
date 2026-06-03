"""Host Phase 5 dispatch scheduler 测试。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar, cast

import pytest

from dayu.contracts.cancellation import CancellationToken
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
from dayu.engine.contracts.messages import AgentMessage, AgentMessageRole, UserMessage
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
from dayu.host.compaction import CompactionCandidate, CompactionRequest, ContextCompactor
from dayu.host.context_budget import ContextBudgetDecision
from dayu.host.context_events import (
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    CONTEXT_COMPACTION_FAILED,
    CONTEXT_COMPACTION_REQUESTED,
    build_context_compaction_requested_payload,
)
from dayu.host.context_policy import (
    ContextBudgetPolicy,
    ContextCompactionTriggerSource,
    DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN,
    context_budget_policy_from_threshold_tokens,
)
from tests.host._context_compaction_assertions import assert_failed_payload_no_fallback
from tests.host.fake_compaction import FakeContextCompactor
from dayu.host.tooling import (
    HostToolingOptions,
)
from dayu.host.tool_duplicate_governance import (
    DuplicateDecisionKind,
    DuplicateGovernancePolicy,
)
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef
from dayu.host.dispatch import (
    ActiveCancelMessage,
    ActiveWorkerRegistry,
    DispatchDrainResult,
    HostDispatchScheduler,
    _DurableRunCancellationToken,
    _HostCancellationToken,
    _safe_close_worker_handle,
    _safe_release_lane_token,
)
from dayu.host.engine_ingest import (
    EngineIngestResult,
    EngineEventIngestor,
    LocalEngineEnvelope,
)
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    MemoryRepairReason,
    MemoryRepairRequest,
    MemorySnapshotCursor,
    default_memory_projection_policy,
    digest_memory_projection_policy,
)
from dayu.host.run_input import (
    MemoryProjectionRepairRequired,
    NoToolExecutor,
    PolicySnapshot,
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
    _attempt_terminal_event_type,
    _run_terminal_event_type,
    cancel_predispatch_starting_in_transaction,
    create_accepted_run_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
    FailUnstartedRunInput,
    fail_unstarted_run_in_transaction,
)
from dayu.host.durable.liveness import HostInstanceIdentity, register_current_instance
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
from dayu.host.durable.transaction import (
    HostReadTransactionOperation,
    HostTransaction,
    HostTransactionRunner,
)
from dayu.host.local_proxy import DefaultLocalEngineWorkerFactory
from dayu.host.projection import ProjectionCatchupPort
from dayu.runtime.lane import (
    LaneAcquired,
    LaneAcquireOutcome,
    LaneClaimToken,
    LaneConfig,
    LaneController,
    LaneOwner,
    RuntimeLaneClosedError,
    SQLiteLaneCoordinatorConfig,
)

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "dispatch-test"})
_LANE_NAME = "llm"
_SOFT_THRESHOLD_PROMPT_CHAR_COUNT = 120
_HARD_THRESHOLD_PROMPT_CHAR_COUNT = 240
_SOFT_CONTEXT_WINDOW_SIZE = 110
_SOFT_RESERVED_OUTPUT_TOKENS = 10
_SOFT_HARD_THRESHOLD_TOKENS = 80
_SOFT_SAFETY_MARGIN_RATIO = 0.5
_REPEATED_OVERFLOW_SYNC_TIMEOUT_SECONDS = 2.0
_SCHEDULER_CLOSE_REASON = "scheduler_close"
_EVENT_LOG_TEST_READ_LIMIT = 200
_ATTEMPT_TERMINAL_STATUSES = (
    AttemptStatus.SUCCEEDED,
    AttemptStatus.FAILED,
    AttemptStatus.CANCELLED,
    AttemptStatus.LOST,
)
_RUN_TERMINAL_STATUSES = (
    RunStatus.SUCCEEDED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
    RunStatus.LOST,
)
_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class _SchedulerCloseLifecycleCase:
    """scheduler close lifecycle proof matrix 的单行场景。"""

    scenario_id: str
    window: str
    expected_close_action: str
    expected_durable_mutation: str
    expected_resource_cleanup: str
    coverage_classification: str


_SCHEDULER_CLOSE_LIFECYCLE_MATRIX = (
    _SchedulerCloseLifecycleCase(
        scenario_id="close-active-worker",
        window="active worker event stream",
        expected_close_action="cancel active token with scheduler_close and await active task cleanup",
        expected_durable_mutation="no scheduler-close-created terminal canonical fact",
        expected_resource_cleanup="handle close once, registry unregister, lane token release",
        coverage_classification="existing",
    ),
    _SchedulerCloseLifecycleCase(
        scenario_id="cancel-all-after-register",
        window="ActiveWorkerRegistry.cancel_all snapshot propagation",
        expected_close_action="cancel only entries captured before lock release",
        expected_durable_mutation="none",
        expected_resource_cleanup="later registered entries require a later cancel_all call",
        coverage_classification="new",
    ),
    _SchedulerCloseLifecycleCase(
        scenario_id="dispatch-queue-non-empty-close",
        window="pending dispatch queue before drain",
        expected_close_action="fail closed without drain-until-empty",
        expected_durable_mutation="run attempt and dispatch row remain recoverable by next open",
        expected_resource_cleanup="wakeup and drain APIs reject after close",
        coverage_classification="new",
    ),
    _SchedulerCloseLifecycleCase(
        scenario_id="promotion-queue-non-empty-close",
        window="promotion task running with queued session behind it",
        expected_close_action="cancel tracked promotion task without draining queued sessions",
        expected_durable_mutation="no terminal canonical fact",
        expected_resource_cleanup="promotion task done and pending promotion queue remains local-only",
        coverage_classification="new",
    ),
    _SchedulerCloseLifecycleCase(
        scenario_id="lane-wait-pre-worker-close",
        window="dispatch has entered lane wait before worker accept",
        expected_close_action="cancel drain path or receive lane close cancellation",
        expected_durable_mutation="no worker_startup_timeout terminal fact",
        expected_resource_cleanup="drain task done and lane controller closed",
        coverage_classification="new",
    ),
    _SchedulerCloseLifecycleCase(
        scenario_id="worker-accepted-before-consumer-start-close",
        window="worker accepted and active task registered before event consume body starts",
        expected_close_action="cancel active token and close residual active handle",
        expected_durable_mutation="no scheduler-close-created terminal canonical fact",
        expected_resource_cleanup="handle close once, registry clear, active task done",
        coverage_classification="new",
    ),
    _SchedulerCloseLifecycleCase(
        scenario_id="close-cancelled-mid-cleanup-retry",
        window="outer task cancellation during scheduler close cleanup",
        expected_close_action="propagate CancelledError and allow later close retry to finish cleanup",
        expected_durable_mutation="no scheduler-close-created terminal canonical fact",
        expected_resource_cleanup="active registry empty, active tasks done, lane closed",
        coverage_classification="new",
    ),
    _SchedulerCloseLifecycleCase(
        scenario_id="close-drain-until-empty",
        window="graceful completion of all pending local work",
        expected_close_action="not a scheduler close contract",
        expected_durable_mutation="none",
        expected_resource_cleanup="none",
        coverage_classification="non-goal",
    ),
)


class _RetryExhaustedReadRunner(HostTransactionRunner):
    """测试用 read transaction runner，始终模拟 durable 不可读。"""

    def __init__(self) -> None:
        """跳过真实 SQLite runner 初始化。

        :returns: ``None``。
        """

    def run_read(self, operation: HostReadTransactionOperation[_T]) -> _T:
        """模拟 read transaction busy 重试耗尽。

        :param operation: Host read transaction operation。
        :returns: 不会返回。
        :raises HostTransactionRetryExhaustedError: 始终抛出。
        """

        del operation
        raise HostTransactionRetryExhaustedError(
            "Host durable read transaction busy retry exhausted",
            attempts=3,
        )


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

    def on_cancel(self, reason: str) -> None:
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


class _TransactionReadableCompactor(ContextCompactor):
    """测试 compactor 调用期可开启独立读事务。"""

    def __init__(self, transaction_runner: HostTransactionRunner) -> None:
        """初始化 compactor。

        :param transaction_runner: Host transaction runner。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(self, request: CompactionRequest, cancellation_token: CancellationToken) -> CompactionCandidate:
        """执行 compact 并验证当前不在外层 write transaction 内。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: fake compaction candidate。
        """

        self.calls += 1
        row = self._transaction_runner.run_read(lambda transaction: read_run_by_id(transaction, request.run_id))
        assert row is not None
        return await self._fake.compact(request, cancellation_token)


class _StaleMutatingCompactor(ContextCompactor):
    """测试 compactor 返回前让源 Run 状态变化。"""

    def __init__(self, transaction_runner: HostTransactionRunner) -> None:
        """初始化 compactor。

        :param transaction_runner: Host transaction runner。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._fake = FakeContextCompactor()

    async def compact(self, request: CompactionRequest, cancellation_token: CancellationToken) -> CompactionCandidate:
        """先把源 Run 失败收口，再返回 candidate。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: fake compaction candidate。
        """

        def _operation(transaction: HostTransaction) -> None:
            run = read_run_by_id(transaction, request.run_id)
            assert run is not None
            fail_unstarted_run_in_transaction(
                transaction,
                EventLogStore(),
                FailUnstartedRunInput(
                    run_id=request.run_id,
                    expected_status=run.status,
                    run_failed_event_id=f"event-stale-run-failed-{request.run_id}",
                    occurred_at=datetime.now(UTC),
                    actor="pytest",
                    source="pytest",
                    reason="stale-test",
                    error_code="stale_test",
                    message="stale test",
                ),
            )

        self._transaction_runner.run_write(_operation)
        return await self._fake.compact(request, cancellation_token)


class _RaisingCompactor(ContextCompactor):
    """测试用始终失败 compactor。"""

    async def compact(self, request: CompactionRequest, cancellation_token: CancellationToken) -> CompactionCandidate:
        """模拟 proposal failure。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出测试错误。
        """

        del request
        del cancellation_token
        raise RuntimeError("proposal failed")


class _QualityRejectOnceCompactor(ContextCompactor):
    """首次返回 quality rejection，第二次返回 accepted candidate。"""

    def __init__(self) -> None:
        """初始化 fake compactor 与调用计数。

        :returns: ``None``。
        """

        self.calls = 0
        self._fake = FakeContextCompactor()

    async def compact(self, request: CompactionRequest, cancellation_token: CancellationToken) -> CompactionCandidate:
        """构造一次可修复 quality rejection。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: compaction candidate。
        """

        self.calls += 1
        candidate = await self._fake.compact(request, cancellation_token)
        if self.calls == 1:
            return replace(candidate, retained_current_user_input_ref="wrong-input")
        return candidate


class _RequestCapturingCompactor(ContextCompactor):
    """记录 proactive compaction request 的测试 compactor。"""

    def __init__(self) -> None:
        """初始化 request recorder。

        :returns: ``None``。
        """

        self.requests: list[CompactionRequest] = []
        self._fake = FakeContextCompactor()

    async def compact(self, request: CompactionRequest, cancellation_token: CancellationToken) -> CompactionCandidate:
        """记录 request 并返回 fake candidate。

        :param request: compaction request。
        :param cancellation_token: Host 注入的取消 token。
        :returns: fake compaction candidate。
        """

        self.requests.append(request)
        return await self._fake.compact(request, cancellation_token)


class _CloseFailingHandle(_FakeHandle):
    """关闭时抛异常的 fake handle。"""

    async def events(self) -> AsyncIterator[EngineEvent]:
        """保持事件流未结束直到 scheduler close。

        :returns: 不会正常返回事件。
        """

        await asyncio.sleep(10.0)
        if False:
            yield _unreachable_engine_event()

    def on_cancel(self, reason: str) -> None:
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

    def on_cancel(self, reason: str) -> None:
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

    def on_cancel(self, reason: str) -> None:
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


class _RegisteringCancelHandle(_FakeHandle):
    """取消回调中注册第二个 active entry 的测试 handle。"""

    def __init__(
        self,
        *,
        registry: ActiveWorkerRegistry,
        second_token: _HostCancellationToken,
        second_handle: _FakeHandle,
    ) -> None:
        """初始化测试 handle。

        :param registry: 待测试 active worker registry。
        :param second_token: 后注册 entry 的 cancellation token。
        :param second_handle: 后注册 entry 的 worker handle。
        :returns: ``None``。
        """

        super().__init__()
        self._registry = registry
        self._second_token = second_token
        self._second_handle = second_handle
        self.cancel_reasons: list[str] = []

    def on_cancel(self, reason: str) -> None:
        """记录取消原因并在传播过程中注册第二个 entry。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        self.cancel_reasons.append(reason)
        self._registry.register(
            run_id="run-second",
            attempt_id="attempt-second",
            execution_id="execution-second",
            handle=self._second_handle,
            cancellation_token=self._second_token,
        )


class _BlockedLaneAcquire:
    """阻塞 lane acquire 的确定性测试替身。"""

    def __init__(self) -> None:
        """初始化阻塞 acquire 替身。

        :returns: ``None``。
        """

        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(
        self,
        name: str,
        *,
        token: CancellationToken | None = None,
        timeout_seconds: float | None = None,
    ) -> LaneAcquireOutcome:
        """阻塞 acquire，直到外层 drain task 被取消。

        :param name: lane 名称。
        :param token: 可选取消 token。
        :param timeout_seconds: acquire timeout。
        :returns: 正常路径不会返回。
        :raises AssertionError: 若测试错误释放阻塞点则抛出。
        """

        del name, token, timeout_seconds
        self.started.set()
        await self.release.wait()
        raise AssertionError("blocked lane acquire must be cancelled by scheduler close")


class _CloseOnceBlockedLaneClose:
    """第一次 lane close 阻塞，后续调用转发到真实 close。"""

    def __init__(
        self,
        original_close: Callable[[str | None], Awaitable[None]],
    ) -> None:
        """初始化阻塞 close 替身。

        :param original_close: 真实 lane controller close 方法。
        :returns: ``None``。
        """

        self._original_close = original_close
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def __call__(self, reason: str | None = None) -> None:
        """第一次调用阻塞以便测试取消 close，第二次执行真实 close。

        :param reason: close reason。
        :returns: ``None``。
        :raises asyncio.CancelledError: 第一次调用被外层取消时透传。
        """

        self.calls += 1
        if self.calls == 1:
            self.started.set()
            await self.release.wait()
        await self._original_close(reason)


async def _unstarted_active_consumer_probe(started: asyncio.Event) -> None:
    """模拟尚未进入 worker event consume body 的 active task。

    :param started: 若 task body 被调度执行则置位的事件。
    :returns: ``None``。
    """

    started.set()
    await asyncio.sleep(1)


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

    async def accept(self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest) -> LocalWorkerHandle:
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

    async def accept(self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest) -> LocalWorkerHandle:
        """返回预置 handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 预置 handle。
        """

        del snapshot, request
        return self._handle


class _FailingAcceptWorker:
    """accept 时抛异常的 fake worker。"""

    async def accept(self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest) -> LocalWorkerHandle:
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

    async def accept(self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest) -> LocalWorkerHandle:
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


class _LagRepairRunInputBuilder:
    """首次 build 抛出大滞后 repair，第二次返回最小 Engine request。"""

    def __init__(self) -> None:
        """初始化调用计数。

        :returns: ``None``。
        """

        self.calls = 0

    def build(self, snapshot: AttemptDispatchSnapshot) -> AgentRunRequest:
        """构造测试 Engine request，首次模拟 snapshot 大滞后。

        :param snapshot: dispatch snapshot。
        :returns: 最小 no-tool Engine request。
        :raises MemoryProjectionRepairRequired: 首次调用时抛出 lag repair。
        """

        self.calls += 1
        if self.calls == 1:
            policy = default_memory_projection_policy()
            raise MemoryProjectionRepairRequired(
                MemoryRepairRequest(
                    session_id=snapshot.session_id,
                    reason=MemoryRepairReason.SNAPSHOT_LAG_OVER_THRESHOLD,
                    required_event_sequence=20,
                    observed_cursor=MemorySnapshotCursor(
                        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                        checkpoint_event_sequence=0,
                        checkpoint_event_id=None,
                        session_id=snapshot.session_id,
                    ),
                    policy_digest=digest_memory_projection_policy(policy),
                )
            )
        return AgentRunRequest(
            run_id=snapshot.run_id,
            session_id=snapshot.session_id,
            messages=(UserMessage(role=AgentMessageRole.USER, content="dispatch after lag"),),
            disable_tools=True,
            runner_spec=_runner_spec(),
            runner_options=RunnerCallOptions(
                temperature=None,
                max_tokens=None,
                top_p=None,
                stream=False,
            ),
            agent_policy=_agent_policy(False),
            tool_schemas=(),
            tool_executor=NoToolExecutor(),
            cancellation_token=snapshot.cancellation_token,
        )


class _PersistentLagRepairRunInputBuilder:
    """每次 build 都抛出大滞后 repair。"""

    def __init__(self) -> None:
        """初始化调用计数。

        :returns: ``None``。
        """

        self.calls = 0

    def build(self, snapshot: AttemptDispatchSnapshot) -> AgentRunRequest:
        """构造测试 Engine request，始终模拟 snapshot 大滞后。

        :param snapshot: dispatch snapshot。
        :returns: 不会返回。
        :raises MemoryProjectionRepairRequired: 始终抛出 lag repair。
        """

        self.calls += 1
        policy = default_memory_projection_policy()
        raise MemoryProjectionRepairRequired(
            MemoryRepairRequest(
                session_id=snapshot.session_id,
                reason=MemoryRepairReason.SNAPSHOT_LAG_OVER_THRESHOLD,
                required_event_sequence=20,
                observed_cursor=MemorySnapshotCursor(
                    consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
                    checkpoint_event_sequence=0,
                    checkpoint_event_id=None,
                    session_id=snapshot.session_id,
                ),
                policy_digest=digest_memory_projection_policy(policy),
            )
        )


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


class _GatedSnapshotEventHandle(_FakeHandle):
    """等待测试同步门后再产出单个 EngineEvent 的 handle。"""

    def __init__(
        self,
        snapshot: AttemptDispatchSnapshot,
        event: EngineEvent,
        gate: asyncio.Event,
    ) -> None:
        """初始化 gated handle。

        :param snapshot: dispatch snapshot。
        :param event: 要产出的 EngineEvent。
        :param gate: 控制事件产出时机的同步门。
        :returns: ``None``。
        """

        super().__init__(local_worker_id=f"worker-{snapshot.attempt_id}")
        self._event = event
        self._gate = gate

    async def events(self) -> AsyncIterator[EngineEvent]:
        """等待同步门打开后产出单个事件。

        :returns: EngineEvent 异步迭代器。
        """

        await self._gate.wait()
        yield self._event


class _ReactiveRecoveryWorker:
    """第一轮产出 reactive overflow，第二轮产出 final answer。"""

    def __init__(self, factory: "_ReactiveRecoveryWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest) -> LocalWorkerHandle:
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
            if self._factory.first_event_gate is not None:
                return _GatedSnapshotEventHandle(
                    snapshot,
                    event,
                    self._factory.first_event_gate,
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

    def __init__(
        self,
        *,
        final_blocks: bool = False,
        first_event_gate: asyncio.Event | None = None,
    ) -> None:
        """初始化 factory。

        :param final_blocks: recovery Attempt 是否阻塞不产出 terminal。
        :param first_event_gate: 第一轮 reactive 事件产出前等待的同步门。
        :returns: ``None``。
        """

        self.final_blocks = final_blocks
        self.first_event_gate = first_event_gate
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


class _RepeatedReactiveOverflowHandle(_FakeHandle):
    """每次 dispatch 后立即产出 reactive overflow 的 fake handle。"""

    def __init__(
        self,
        snapshot: AttemptDispatchSnapshot,
        overflow_index: int,
        factory: "_RepeatedReactiveOverflowWorkerFactory",
    ) -> None:
        """初始化 repeated-overflow handle。

        :param snapshot: 当前 dispatch snapshot。
        :param overflow_index: 当前 factory accept 序号，从 1 开始。
        :param factory: 所属 factory，用于记录 close 同步点。
        :returns: ``None``。
        """

        super().__init__(local_worker_id=f"worker-overflow-{overflow_index}")
        self._snapshot = snapshot
        self._overflow_index = overflow_index
        self._factory = factory

    async def events(self) -> AsyncIterator[EngineEvent]:
        """立即产出单个 reactive overflow EngineEvent。

        :returns: 只包含一个 ``CONTEXT_COMPACTION_REQUESTED`` 的异步迭代器。
        """

        yield EngineEvent(
            occurred_at=_NOW,
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
            data=ContextCompactionRequestedData(
                iteration_id=f"iter-reactive-{self._overflow_index}",
                budget_state=None,
                reason="provider_overflow",
                provider_request_id=f"req-reactive-{self._overflow_index}",
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """记录 handle close，作为该次 overflow 已被 scheduler 收口的同步点。

        :returns: ``None``。
        """

        await super().close()
        await self._factory.record_closed()


class _RepeatedReactiveOverflowWorker:
    """每次 accept 都返回 repeated-overflow handle 的 fake worker。"""

    def __init__(self, factory: "_RepeatedReactiveOverflowWorkerFactory") -> None:
        """初始化 fake worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest) -> LocalWorkerHandle:
        """记录 dispatch accept，并返回立即 overflow 的 handle。

        :param snapshot: 当前 dispatch snapshot。
        :param request: 当前 Engine request。
        :returns: repeated-overflow handle。
        """

        accepted_index = await self._factory.record_accept(snapshot, request)
        return _RepeatedReactiveOverflowHandle(snapshot, accepted_index, self._factory)


class _RepeatedReactiveOverflowWorkerFactory:
    """连续 reactive overflow dispatch-loop 的确定性 fake factory。"""

    def __init__(self) -> None:
        """初始化 fake factory。

        :returns: ``None``。
        """

        self.created = 0
        self.accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self.accepted_requests: list[AgentRunRequest] = []
        self.closed_count = 0
        self._accepted_condition = asyncio.Condition()
        self._closed_condition = asyncio.Condition()

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 repeated-overflow worker。

        :param snapshot: 当前 dispatch snapshot。
        :returns: repeated-overflow worker。
        """

        del snapshot
        self.created += 1
        return _RepeatedReactiveOverflowWorker(self)

    async def record_accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> int:
        """记录一次 worker accept 并唤醒测试同步点。

        :param snapshot: 当前 dispatch snapshot。
        :param request: 当前 Engine request。
        :returns: 本次 accept 序号，从 1 开始。
        """

        async with self._accepted_condition:
            self.accepted_snapshots.append(snapshot)
            self.accepted_requests.append(request)
            accepted_index = len(self.accepted_snapshots)
            self._accepted_condition.notify_all()
            return accepted_index

    async def record_closed(self) -> None:
        """记录一次 handle close 并唤醒测试同步点。

        :returns: ``None``。
        """

        async with self._closed_condition:
            self.closed_count += 1
            self._closed_condition.notify_all()

    async def wait_for_accepted_count(self, expected_count: int) -> None:
        """等待 factory 观察到指定 accept 次数。

        :param expected_count: 期望 accept 次数。
        :returns: ``None``。
        :raises TimeoutError: 超时仍未达到期望次数时抛出。
        """

        await asyncio.wait_for(
            self._wait_for_accepted_count(expected_count),
            timeout=_REPEATED_OVERFLOW_SYNC_TIMEOUT_SECONDS,
        )

    async def wait_for_closed_count(self, expected_count: int) -> None:
        """等待 factory 观察到指定 handle close 次数。

        :param expected_count: 期望 close 次数。
        :returns: ``None``。
        :raises TimeoutError: 超时仍未达到期望次数时抛出。
        """

        await asyncio.wait_for(
            self._wait_for_closed_count(expected_count),
            timeout=_REPEATED_OVERFLOW_SYNC_TIMEOUT_SECONDS,
        )

    async def _wait_for_accepted_count(self, expected_count: int) -> None:
        """在 condition 上等待 accept 次数达标。

        :param expected_count: 期望 accept 次数。
        :returns: ``None``。
        """

        async with self._accepted_condition:
            await self._accepted_condition.wait_for(
                lambda: len(self.accepted_snapshots) >= expected_count
            )

    async def _wait_for_closed_count(self, expected_count: int) -> None:
        """在 condition 上等待 handle close 次数达标。

        :param expected_count: 期望 close 次数。
        :returns: ``None``。
        """

        async with self._closed_condition:
            await self._closed_condition.wait_for(
                lambda: self.closed_count >= expected_count
            )


class _FinalAnswerWorker:
    """接受请求后立即返回 final_answer 的 fake worker。"""

    def __init__(self, factory: "_FinalAnswerWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest) -> LocalWorkerHandle:
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

    async def __call__(self, call: ToolCallRequest, context: BatchToolExecutionContext) -> ToolExecutionOutcome:
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

    def __init__(self, *, target_empty_checks: int = 1) -> None:
        """初始化测试队列。

        :param target_empty_checks: 触发 ``empty_checked`` 的 empty 检查次数。
        :returns: ``None``。
        """

        super().__init__()
        self.empty_checked = asyncio.Event()
        self.empty_call_count = 0
        self._target_empty_checks = target_empty_checks

    def empty(self) -> bool:
        """记录 empty 检查并返回真实队列状态。

        :returns: 当前队列是否为空。
        """

        self.empty_call_count += 1
        if self.empty_call_count >= self._target_empty_checks:
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


class _RetryExhaustedDrainLoopScheduler(HostDispatchScheduler):
    """测试用 drain_once 持久化重试耗尽 scheduler。"""

    async def drain_once(self) -> DispatchDrainResult:
        """模拟 drain_once 遇到持久化重试耗尽。

        :returns: 不会返回。
        :raises HostTransactionRetryExhaustedError: 始终抛出测试异常。
        """

        raise HostTransactionRetryExhaustedError("drain retry exhausted", attempts=3)


class _CloseWorkerLostFailingIngestor:
    """测试用 close_worker_lost 失败 ingestor。"""

    def close_worker_lost(
        self,
        envelope: LocalEngineEnvelope,
        *,
        observed_at: datetime,
        worker_lifecycle_signal: str,
        stream_error_code: str,
        last_observed_worker_event_index: int,
        last_accepted_event_id: str | None,
    ) -> EngineIngestResult:
        """模拟 lost closeout 写入失败。

        :param envelope: worker envelope。
        :param observed_at: Host 观察时间。
        :param worker_lifecycle_signal: worker lifecycle signal。
        :param stream_error_code: 原始异常类型名。
        :param last_observed_worker_event_index: 最后观测到的 worker event index。
        :param last_accepted_event_id: 最后已接受 EventLog id。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出 closeout 失败。
        """

        del (
            envelope,
            observed_at,
            worker_lifecycle_signal,
            stream_error_code,
            last_observed_worker_event_index,
            last_accepted_event_id,
        )
        raise RuntimeError("close worker lost failed")


class _FailingCloseWorkerHandle:
    """关闭时抛错的 worker handle fake。"""

    @property
    def local_worker_id(self) -> str:
        """返回 fake worker id。

        :returns: fake worker id。
        """

        return "worker-close-fails"

    def events(self) -> AsyncIterator[EngineEvent]:
        """返回空事件流。

        :returns: 空异步迭代器。
        """

        return _empty_engine_events()

    async def close(self) -> None:
        """模拟 worker handle close 失败。

        :returns: 不返回。
        :raises RuntimeError: 始终抛出 close 失败。
        """

        raise RuntimeError("worker close failed")

    def on_cancel(self, reason: str) -> None:
        """忽略取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason


class _FailingLaneToken:
    """释放时抛错的 lane token fake。"""

    name = _LANE_NAME
    claim_id = "claim-release-fails"

    async def release(self) -> None:
        """模拟 lane token release 失败。

        :returns: 不返回。
        :raises RuntimeError: 始终抛出 release 失败。
        """

        raise RuntimeError("lane release failed")


async def _empty_engine_events() -> AsyncIterator[EngineEvent]:
    """返回空 EngineEvent 异步流。

    :returns: 空异步迭代器。
    """

    if False:
        yield _final_answer_event("unused")


def test_scheduler_close_lifecycle_matrix_covers_slice_b_windows() -> None:
    """close lifecycle matrix 必须覆盖 Slice B 要求的窗口。

    :returns: ``None``。
    :raises AssertionError: matrix 缺失必要场景或字段为空时抛出。
    """

    required_ids = {
        "cancel-all-after-register",
        "dispatch-queue-non-empty-close",
        "promotion-queue-non-empty-close",
        "lane-wait-pre-worker-close",
        "worker-accepted-before-consumer-start-close",
        "close-cancelled-mid-cleanup-retry",
    }
    actual_ids = {item.scenario_id for item in _SCHEDULER_CLOSE_LIFECYCLE_MATRIX}

    assert required_ids <= actual_ids
    assert {item.coverage_classification for item in _SCHEDULER_CLOSE_LIFECYCLE_MATRIX} == {
        "existing",
        "new",
        "non-goal",
    }
    for item in _SCHEDULER_CLOSE_LIFECYCLE_MATRIX:
        assert item.window.strip() != ""
        assert item.expected_close_action.strip() != ""
        assert item.expected_durable_mutation.strip() != ""
        assert item.expected_resource_cleanup.strip() != ""


def test_active_worker_registry_cancel_all_uses_snapshot_when_entry_registers_after_cancel() -> None:
    """``cancel_all`` 只取消调用开始时的 active entry 快照。

    :returns: ``None``。
    """

    registry = ActiveWorkerRegistry()
    first_token = _HostCancellationToken()
    second_token = _HostCancellationToken()
    second_handle = _FakeHandle()
    first_handle = _RegisteringCancelHandle(
        registry=registry,
        second_token=second_token,
        second_handle=second_handle,
    )
    registry.register(
        run_id="run-first",
        attempt_id="attempt-first",
        execution_id="execution-first",
        handle=first_handle,
        cancellation_token=first_token,
    )

    first_count = registry.cancel_all(_SCHEDULER_CLOSE_REASON)

    assert first_count == 1
    assert first_token.is_cancelled() is True
    assert first_token.cancel_reason() == _SCHEDULER_CLOSE_REASON
    assert first_handle.cancel_reasons == [_SCHEDULER_CLOSE_REASON]
    assert second_token.is_cancelled() is False

    second_count = registry.cancel_all(_SCHEDULER_CLOSE_REASON)

    assert second_count == 2
    assert second_token.is_cancelled() is True
    assert second_token.cancel_reason() == _SCHEDULER_CLOSE_REASON


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

            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
            event = _read_event_by_type(store.transaction_runner, "ATTEMPT_RUNNING")
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
            assert factory.accepted_snapshots[0].dispatch_record_id == seeded.dispatch_record_id
            assert factory.accepted_requests[0].disable_tools is True
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_dispatch_lag_repair_rebuild_retry_does_not_fail_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SNAPSHOT_LAG_OVER_THRESHOLD 触发 rebuild retry，不关闭 Run。"""

    factory = _FakeWorkerFactory(accepted_handle=_ControlledBlockingHandle())
    builder = _LagRepairRunInputBuilder()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_default_timeout_seconds=1.0,
        )

        def _noop_catch_up(record: PendingDispatchRecord) -> None:
            """跳过 dispatch 预构建 catch-up，让 builder 暴露 lag repair。

            :param record: pending dispatch 摘要。
            :returns: ``None``。
            """

            del record

        def _fake_builder_for_dispatch(
            *,
            snapshot: AttemptDispatchSnapshot,
            policy_snapshot: PolicySnapshot,
            selected_business_tool_names: frozenset[str] | None,
        ) -> _LagRepairRunInputBuilder:
            """返回会先抛 lag repair 的测试 builder。

            :param snapshot: dispatch snapshot。
            :param policy_snapshot: 冻结 policy snapshot。
            :param selected_business_tool_names: 冻结业务工具名。
            :returns: 测试 builder。
            """

            del snapshot, policy_snapshot, selected_business_tool_names
            return builder

        monkeypatch.setattr(
            scheduler,
            "_catch_up_memory_projection_before_worker",
            _noop_catch_up,
        )
        monkeypatch.setattr(
            scheduler,
            "_run_input_builder_for_dispatch",
            _fake_builder_for_dispatch,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            assert result.dispatched == 1
            assert builder.calls == 2
            assert factory.created == 1
            assert _run_status(store.transaction_runner, seeded.run_id) == (RunStatus.RUNNING)
            assert _event_count(store.transaction_runner, "RUN_FAILED") == 0
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_memory_lag_pre_dispatch_failure_does_not_enter_recovering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pre-dispatch memory lag repair 不得把 Run 推入 RECOVERING。"""

    factory = _FakeWorkerFactory(accepted_handle=_ControlledBlockingHandle())
    builder = _LagRepairRunInputBuilder()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)

        def _noop_catch_up(record: PendingDispatchRecord) -> None:
            """跳过 catch-up 以触发 builder lag repair 分支。

            :param record: pending dispatch 摘要。
            :returns: ``None``。
            """

            del record

        def _fake_builder_for_dispatch(
            *,
            snapshot: AttemptDispatchSnapshot,
            policy_snapshot: PolicySnapshot,
            selected_business_tool_names: frozenset[str] | None,
        ) -> _LagRepairRunInputBuilder:
            """返回测试 builder。

            :param snapshot: dispatch snapshot。
            :param policy_snapshot: policy snapshot。
            :param selected_business_tool_names: 业务工具名集合。
            :returns: 测试 builder。
            """

            del snapshot, policy_snapshot, selected_business_tool_names
            return builder

        monkeypatch.setattr(
            scheduler,
            "_catch_up_memory_projection_before_worker",
            _noop_catch_up,
        )
        monkeypatch.setattr(
            scheduler,
            "_run_input_builder_for_dispatch",
            _fake_builder_for_dispatch,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            await scheduler.drain_once()

            assert _event_count(store.transaction_runner, "RUN_RECOVERING") == 0
            assert _run_status(store.transaction_runner, seeded.run_id) == (RunStatus.RUNNING)
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_persistent_memory_lag_repair_failure_closes_starting_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """worker startup memory lag 修复失败不得遗留 running / dispatching 状态。"""

    factory = _FakeWorkerFactory(accepted_handle=_ControlledBlockingHandle())
    builder = _PersistentLagRepairRunInputBuilder()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_default_timeout_seconds=1.0,
        )

        def _noop_catch_up(record: PendingDispatchRecord) -> None:
            """跳过 catch-up 以触发 builder lag repair 分支。

            :param record: pending dispatch 摘要。
            :returns: ``None``。
            """

            del record

        def _fake_builder_for_dispatch(
            *,
            snapshot: AttemptDispatchSnapshot,
            policy_snapshot: PolicySnapshot,
            selected_business_tool_names: frozenset[str] | None,
        ) -> _PersistentLagRepairRunInputBuilder:
            """返回持续 lag repair 的测试 builder。

            :param snapshot: dispatch snapshot。
            :param policy_snapshot: policy snapshot。
            :param selected_business_tool_names: 业务工具名集合。
            :returns: 测试 builder。
            """

            del snapshot, policy_snapshot, selected_business_tool_names
            return builder

        monkeypatch.setattr(
            scheduler,
            "_catch_up_memory_projection_before_worker",
            _noop_catch_up,
        )
        monkeypatch.setattr(
            scheduler,
            "_run_input_builder_for_dispatch",
            _fake_builder_for_dispatch,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
            assert result.timed_out == 1
            assert builder.calls == 2
            assert factory.created == 0
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            assert dispatch_record.status == DispatchRecordStatus.CANCELLED
            assert dispatch_record.cancelled_event_id is not None
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_drain_loop_logs_unexpected_exception(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """drain loop 未预期异常后必须记录诊断并保持可关闭。"""

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
            coordinator=SQLiteLaneCoordinatorConfig(db_path=tmp_path / "lane-drain-loop.sqlite3"),
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
                runner_options=RunnerCallOptions(temperature=None, max_tokens=None, top_p=None, stream=False),
                agent_policy=_agent_policy(False),
                worker_factory=_FakeWorkerFactory(),
            ),
            lane_controller=lane_controller,
            host_handle_id="host-drain-loop-log",
        )
        try:
            scheduler._drain_task = asyncio.create_task(scheduler._drain_loop())
            await asyncio.sleep(0.03)
            assert scheduler._drain_task.done() is False
        finally:
            await scheduler.close()

    assert any("dispatch drain loop stopped unexpectedly" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_drain_loop_fail_closes_on_durable_retry_exhausted(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """drain loop 持久化重试耗尽时必须 fail-close 并可继续 close 清理。"""

    caplog.set_level(logging.ERROR, logger="dayu.host.dispatch")
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
            coordinator=SQLiteLaneCoordinatorConfig(db_path=tmp_path / "lane-drain-loop-retry-exhausted.sqlite3"),
        )
        registry = ActiveWorkerRegistry()
        active_token = _HostCancellationToken()
        registry.register(
            run_id="run-active",
            attempt_id="attempt-active",
            execution_id="execution-active",
            handle=_FakeHandle(),
            cancellation_token=active_token,
        )
        scheduler = _RetryExhaustedDrainLoopScheduler(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            local_execution=HostLocalExecutionOptions(
                lane_db_path=tmp_path / "lane-drain-loop-retry-exhausted.sqlite3",
                lane_name=_LANE_NAME,
                lane_capacity=1,
                lane_default_timeout_seconds=0.1,
                lane_claim_ttl_seconds=1.0,
                lane_heartbeat_interval_seconds=0.1,
                worker_startup_timeout_seconds=1.0,
                dispatch_poll_interval_seconds=0.01,
                runner_spec=_runner_spec(),
                runner_options=RunnerCallOptions(temperature=None, max_tokens=None, top_p=None, stream=False),
                agent_policy=_agent_policy(False),
                worker_factory=_FakeWorkerFactory(),
            ),
            lane_controller=lane_controller,
            host_handle_id="host-drain-loop-retry-exhausted",
            active_registry=registry,
        )
        scheduler._drain_task = asyncio.create_task(scheduler._drain_loop())
        await asyncio.sleep(0.03)
        assert scheduler._drain_task.done() is True
        assert active_token.is_cancelled() is True
        assert (
            active_token.cancel_reason()
            == "drain_loop_durable_retry_exhausted"
        )
        with pytest.raises(RuntimeError, match="closed"):
            scheduler.wake_dispatch(
                PendingDispatchRecord(
                    dispatch_record_id="dispatch-closed",
                    run_id="run-closed",
                    attempt_id="attempt-closed",
                    execution_id="execution-closed",
                    execution_target="target-dispatch",
                    worker_kind=WorkerKind.LOCAL,
                )
            )
        await scheduler.close()

    assert any("dispatch drain loop durable retry exhausted" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_drain_loop_retry_exhausted_closes_pending_queue_records(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """drain loop retry exhausted 关闭前尽力收口队列剩余 dispatch。"""

    caplog.set_level(logging.WARNING, logger="dayu.host.dispatch")
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
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
            coordinator=SQLiteLaneCoordinatorConfig(db_path=tmp_path / "lane-drain-loop-queue-closeout.sqlite3"),
        )
        scheduler = _RetryExhaustedDrainLoopScheduler(
            transaction_runner=store.transaction_runner,
            event_log_store=EventLogStore(),
            local_execution=HostLocalExecutionOptions(
                lane_db_path=tmp_path / "lane-drain-loop-queue-closeout.sqlite3",
                lane_name=_LANE_NAME,
                lane_capacity=1,
                lane_default_timeout_seconds=0.1,
                lane_claim_ttl_seconds=1.0,
                lane_heartbeat_interval_seconds=0.1,
                worker_startup_timeout_seconds=1.0,
                dispatch_poll_interval_seconds=0.01,
                runner_spec=_runner_spec(),
                runner_options=RunnerCallOptions(temperature=None, max_tokens=None, top_p=None, stream=False),
                agent_policy=_agent_policy(False),
                worker_factory=_FakeWorkerFactory(),
            ),
            lane_controller=lane_controller,
            host_handle_id="host-drain-loop-queue-closeout",
        )
        scheduler._queue.put_nowait(_pending_dispatch(seeded))
        scheduler._drain_task = asyncio.create_task(scheduler._drain_loop())
        await asyncio.sleep(0.03)
        await scheduler.close()

        run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
        assert scheduler._queue.qsize() == 0
        assert run.status is RunStatus.FAILED
        assert attempt.status is AttemptStatus.FAILED
        assert dispatch_record.status is DispatchRecordStatus.CANCELLED

    assert "dispatch.drain_loop.queue_closeout" in caplog.text
    assert "closeout_count=1" in caplog.text


@pytest.mark.asyncio
async def test_close_worker_lost_failure_logs_context_without_raising(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """lost closeout 自身失败时记录结构化上下文且不传播异常。"""

    caplog.set_level(logging.ERROR, logger="dayu.host.dispatch")
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, _FakeWorkerFactory())
        try:
            token = _HostCancellationToken()
            envelope = LocalEngineEnvelope(
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                dispatch_record_id=seeded.dispatch_record_id,
                worker_kind=WorkerKind.LOCAL,
                execution_target="target-dispatch",
                local_worker_id="worker-lost-closeout-fails",
                cancellation_token=token,
            )
            closed = scheduler._safe_close_worker_lost(
                ingestor=cast(
                    EngineEventIngestor,
                    _CloseWorkerLostFailingIngestor(),
                ),
                envelope=envelope,
                record=_pending_dispatch(seeded),
                local_worker_id="worker-lost-closeout-fails",
                worker_lifecycle_signal="ingest_exception",
                stream_error_code="RuntimeError",
                last_observed_worker_event_index=3,
                last_accepted_event_id=None,
                original_error=RuntimeError("original ingest failure"),
            )
            assert closed is False
        finally:
            await scheduler.close()

    assert "dispatch.worker_events.close_worker_lost_failed" in caplog.text
    assert "run_id=run-dispatch" in caplog.text
    assert "closeout_error_type=RuntimeError" in caplog.text
    assert "original_error_type=RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_safe_cleanup_helpers_log_failures(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """best-effort cleanup 失败时必须写入 warning 诊断。

    :param caplog: pytest 日志捕获 fixture。
    :returns: ``None``。
    """

    caplog.set_level(logging.WARNING, logger="dayu.host.dispatch")
    await _safe_close_worker_handle(_FailingCloseWorkerHandle())
    await _safe_release_lane_token(cast(LaneClaimToken, _FailingLaneToken()))

    messages = [record.getMessage() for record in caplog.records]
    assert any("dispatch.worker_handle.close_failed" in item for item in messages)
    assert any("dispatch.lane_token.release_failed" in item for item in messages)


@pytest.mark.asyncio
async def test_drain_loop_logs_idle_once_per_idle_streak_and_close(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """drain loop 空闲态和 close 取消路径写入有界 debug 诊断。

    :param tmp_path: pytest 临时目录。
    :param caplog: pytest 日志捕获 fixture。
    :returns: ``None``。
    """

    caplog.set_level(logging.DEBUG, logger="dayu.host.dispatch")
    factory = _FakeWorkerFactory()
    observed_queue = _ObservedEmptyQueue(target_empty_checks=3)
    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(tmp_path, store, factory)
        scheduler._queue = observed_queue
        scheduler._drain_task = asyncio.create_task(scheduler._drain_loop())
        try:
            await observed_queue.empty_checked.wait()
        finally:
            await scheduler.close()

    idle_messages = [
        record.getMessage() for record in caplog.records if "dispatch.drain_loop.idle" in record.getMessage()
    ]
    assert idle_messages == ["dispatch.drain_loop.idle " "host_handle_id=host-test interval_seconds=0.01"]
    assert observed_queue.empty_call_count >= 3
    assert any("dispatch drain loop cancelled during close" in record.getMessage() for record in caplog.records)


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
            assert [schema.function.name for schema in request.tool_schemas] == ["fake_dispatch_tool"]

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
            assert _read_event_by_type(store.transaction_runner, "TOOL_CALL_REQUESTED").run_id == seeded.run_id
            assert _read_event_by_type(store.transaction_runner, "TOOL_RESULT_ACCEPTED").run_id == seeded.run_id
            assert projection.calls == 1
        finally:
            await scheduler.close()


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
            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)

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
    host_identity = HostInstanceIdentity(
        host_instance_id="host-instance-dispatch-recheck",
        pid=1,
        process_start_token="process-token-dispatch-recheck",
        boot_id=None,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            host_handle_id="host-handle-dispatch-recheck",
            host_instance_identity=host_identity,
        )
        claim = await scheduler._lane_controller.acquire(
            _LANE_NAME,
            timeout_seconds=0,
        )
        assert isinstance(claim, LaneAcquired)
        try:
            wait_row = scheduler._mark_waiting_for_lane(_pending_dispatch(seeded))
            assert wait_row is not None
            assert wait_row.status == DispatchRecordStatus.WAITING_FOR_LANE
            assert wait_row.owner_host_instance_id == scheduler.host_instance_id
            assert wait_row.owner_host_instance_id != "host-handle-dispatch-recheck"
            dispatch_record = scheduler._mark_dispatching_after_recheck(
                _pending_dispatch(seeded),
                claim.token,
            )

            assert dispatch_record is not None
            assert dispatch_record.status == DispatchRecordStatus.DISPATCHING
            assert dispatch_record.waiting_for_lane_at is not None
            assert dispatch_record.lane_name == _LANE_NAME
            assert dispatch_record.lane_claim_id == claim.token.claim_id
            assert dispatch_record.owner_host_instance_id == scheduler.host_instance_id
            assert dispatch_record.owner_host_instance_id != "host-handle-dispatch-recheck"
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

            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
            event = _read_event_by_type(store.transaction_runner, "RUN_FAILED")
            assert result.timed_out == 1
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            assert dispatch_record.status == DispatchRecordStatus.CANCELLED
            assert json.loads(_require_text(event.reason_json))["reason"] == ("worker_startup_timeout")
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
            await scheduler.run_queue_promotion(session_id)

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

            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
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
async def test_durable_run_cancellation_token_fails_closed_on_retry_exhausted() -> None:
    """durable read 重试耗尽时，compaction 取消 token 必须 fail closed。"""

    token = _DurableRunCancellationToken(
        transaction_runner=_RetryExhaustedReadRunner(),
        run_id="run-durable-unavailable",
        expected_status=RunStatus.ACCEPTED,
        expected_input_event_sequence=1,
    )

    assert token.is_cancelled() is True
    assert token.cancel_reason() == "durable_unavailable"


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

        def raise_retry_exhausted(record: PendingDispatchRecord, token: LaneClaimToken) -> DispatchRecordRow | None:
            """模拟 dispatching recheck 写事务 busy 重试耗尽。

            :param record: pending dispatch record。
            :param token: 已获取的 lane token。
            :returns: 不会返回。
            :raises HostTransactionRetryExhaustedError: 始终抛出以模拟 busy。
            """

            del record, token
            raise HostTransactionRetryExhaustedError("dispatch recheck busy", attempts=3)

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

            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
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

            run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
            event = _read_event_by_type(store.transaction_runner, "RUN_FAILED")
            assert result.timed_out == 1
            assert result.dispatched == 0
            assert factory.created == 0
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            assert dispatch_record.status == DispatchRecordStatus.CANCELLED
            assert json.loads(_require_text(event.reason_json))["reason"] == ("worker_startup_timeout")
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
            assert json.loads(_require_text(event.reason_json))["reason"] == ("stream_ended_without_terminal")
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
            assert json.loads(_require_text(event.reason_json))["reason"] == ("worker_lost_before_terminal")
            assert handle.closed is True
            assert (
                registry.cancel(
                    ActiveCancelMessage(
                        run_id=seeded.run_id,
                        attempt_id=seeded.attempt_id,
                        execution_id=seeded.execution_id,
                        reason="after_stream_exception",
                    )
                )
                is False
            )
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
        assert "active worker cancel hook failed; continuing" in caplog.text


@pytest.mark.asyncio
async def test_scheduler_close_lets_active_task_own_handle_close(
    tmp_path: Path,
) -> None:
    """scheduler close 只发 cancel，handle close 由 active task finally 执行一次。"""

    handle = _CloseCountingHandle()
    factory = _FakeWorkerFactory(accepted_handle=handle)
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
async def test_scheduler_close_cleans_active_handle_when_consumer_task_never_started(
    tmp_path: Path,
) -> None:
    """close 必须清理尚未进入 events consume body 的 active handle。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: close 后仍残留 active handle、registry entry 或未关闭
        worker handle 时抛出。
    """

    handle = _ControlledBlockingHandle()
    registry = ActiveWorkerRegistry()
    cancellation_token = _HostCancellationToken()
    started = asyncio.Event()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            active_registry=registry,
        )
        heartbeat_task = scheduler._heartbeat_task
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            scheduler._heartbeat_task = None
        registry.register(
            run_id=seeded.run_id,
            attempt_id=seeded.attempt_id,
            execution_id=seeded.execution_id,
            handle=handle,
            cancellation_token=cancellation_token,
        )
        active_task = asyncio.create_task(_unstarted_active_consumer_probe(started))
        scheduler._active_handles.add(handle)
        scheduler._active_tasks.add(active_task)
        active_task.add_done_callback(scheduler._active_tasks.discard)

        await scheduler.close()

        assert not started.is_set()
        assert cancellation_token.is_cancelled()
        assert cancellation_token.cancel_reason() == "scheduler_close"
        assert handle.cancel_count == 1
        assert handle.close_count == 1
        assert not scheduler._active_tasks
        assert not scheduler._active_handles
        assert (
            registry.cancel(
                ActiveCancelMessage(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    reason="after_scheduler_close",
                )
            )
            is False
        )


@pytest.mark.asyncio
async def test_scheduler_close_during_active_events_releases_all_resources(
    tmp_path: Path,
) -> None:
    """scheduler close 期间活跃事件消费被取消后会释放 lane 与 registry。"""

    handle = _ControlledBlockingHandle()
    registry = ActiveWorkerRegistry()
    factory = _FakeWorkerFactory(accepted_handle=handle)
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
        assert len(factory.accepted_requests) == 1
        await scheduler.close()

        assert factory.accepted_requests[0].cancellation_token.is_cancelled()
        assert factory.accepted_requests[0].cancellation_token.cancel_reason() == "scheduler_close"
        assert handle.cancel_count == 1
        assert handle.close_count == 1
        assert handle.events_finalized.is_set()
        assert (
            registry.cancel(
                ActiveCancelMessage(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    reason="after_scheduler_close",
                )
            )
            is False
        )
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
async def test_scheduler_close_with_non_empty_dispatch_queue_does_not_drain_or_write_terminal(
    tmp_path: Path,
) -> None:
    """dispatch queue 非空 close 不处理 pending work，也不写 terminal fact。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)

        scheduler.wake_dispatch(_pending_dispatch(seeded))
        event_log_cursor = _event_log_cursor(store.transaction_runner)
        await scheduler.close()

        run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
        assert scheduler._queue.qsize() == 1
        assert factory.created == 0
        assert run.status is RunStatus.RUNNING
        assert attempt.status is AttemptStatus.STARTING
        assert dispatch_record.status is DispatchRecordStatus.PENDING
        assert dispatch_record.worker_accept_event_id is None
        _assert_scheduler_close_did_not_append_terminal_facts(
            store.transaction_runner,
            after_cursor=event_log_cursor,
        )
        with pytest.raises(RuntimeError, match="HostDispatchScheduler is closed"):
            scheduler.wake_dispatch(_pending_dispatch(seeded))
        with pytest.raises(RuntimeError, match="HostDispatchScheduler is closed"):
            await scheduler.drain_once()


@pytest.mark.asyncio
async def test_scheduler_close_during_lane_wait_skips_worker_startup_timeout_terminal_fact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pre-worker lane wait 窗口 close 取消 drain path，不写 startup timeout。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    """

    factory = _FakeWorkerFactory()
    blocked_acquire = _BlockedLaneAcquire()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        original_acquire = scheduler._lane_controller.acquire
        monkeypatch.setattr(scheduler._lane_controller, "acquire", blocked_acquire)
        scheduler.wake_dispatch(_pending_dispatch(seeded))
        scheduler._drain_task = asyncio.create_task(_run_scheduler_drain_once(scheduler))

        await blocked_acquire.started.wait()
        run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
        assert run.status is RunStatus.RUNNING
        assert attempt.status is AttemptStatus.STARTING
        assert dispatch_record.status is DispatchRecordStatus.WAITING_FOR_LANE
        event_log_cursor = _event_log_cursor(store.transaction_runner)

        await scheduler.close()
        monkeypatch.setattr(scheduler._lane_controller, "acquire", original_acquire)

        assert scheduler._drain_task is not None
        assert scheduler._drain_task.done() is True
        assert factory.created == 0
        run, attempt, dispatch_record = _read_rows(store.transaction_runner, seeded)
        assert run.status is RunStatus.RUNNING
        assert attempt.status is AttemptStatus.STARTING
        assert dispatch_record.status is DispatchRecordStatus.WAITING_FOR_LANE
        assert dispatch_record.cancelled_event_id is None
        _assert_scheduler_close_did_not_append_terminal_facts(
            store.transaction_runner,
            after_cursor=event_log_cursor,
        )
        with pytest.raises(RuntimeLaneClosedError):
            await scheduler._lane_controller.acquire(_LANE_NAME, timeout_seconds=0)


@pytest.mark.asyncio
async def test_scheduler_close_cancelled_mid_cleanup_can_retry_and_finish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close cleanup 中途被取消后，再次 close 必须补完资源清理。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    """

    handle = _ControlledBlockingHandle()
    registry = ActiveWorkerRegistry()
    factory = _FakeWorkerFactory(accepted_handle=handle)
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            active_registry=registry,
        )
        scheduler.wake_dispatch(_pending_dispatch(seeded))
        assert (await scheduler.drain_once()).dispatched == 1
        await handle.events_started.wait()
        blocked_close = _CloseOnceBlockedLaneClose(scheduler._lane_controller.close)
        monkeypatch.setattr(scheduler._lane_controller, "close", blocked_close)
        event_log_cursor = _event_log_cursor(store.transaction_runner)

        close_task = asyncio.create_task(scheduler.close())
        await blocked_close.started.wait()
        close_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await close_task

        assert scheduler._closed is True
        assert scheduler._close_cleanup_done is False

        await scheduler.close()

        assert blocked_close.calls == 2
        assert scheduler._close_cleanup_done is True
        assert not scheduler._active_tasks
        assert not scheduler._active_handles
        assert handle.cancel_count == 1
        assert handle.close_count == 1
        assert (
            registry.cancel(
                ActiveCancelMessage(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    reason="after_close_retry",
                )
            )
            is False
        )
        _assert_scheduler_close_did_not_append_terminal_facts(
            store.transaction_runner,
            after_cursor=event_log_cursor,
        )
        with pytest.raises(RuntimeLaneClosedError):
            await scheduler._lane_controller.acquire(_LANE_NAME, timeout_seconds=0)


@pytest.mark.asyncio
async def test_default_active_registry_is_scheduler_local(tmp_path: Path) -> None:
    """未显式注入 registry 时，不同 host scheduler 不共享默认 registry。"""

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
            host_handle_id="host-test-second",
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
            assert (
                registry.cancel(
                    ActiveCancelMessage(
                        run_id=seeded.run_id,
                        attempt_id=seeded.attempt_id,
                        execution_id=seeded.execution_id,
                        reason="test_cancel_after_failure",
                    )
                )
                is False
            )
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
            assert json.loads(_require_text(event.reason_json))["reason"] == ("worker_lost_before_terminal")
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
            await scheduler.run_queue_promotion(seeded.session_id)
            event_types = _event_types_for_run(store.transaction_runner, seeded.run_id)

            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 1
            assert event_types.index(CONTEXT_COMPACTION_REQUESTED) < event_types.index(CONTEXT_COMPACTED)
            assert event_types.index(CONTEXT_COMPACTED) < event_types.index("RUN_STARTED")
            assert event_types.index("RUN_STARTED") < event_types.index("ATTEMPT_STARTED")
            assert _run_status(store.transaction_runner, seeded.run_id) == (RunStatus.RUNNING)
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_governed_start_sets_dispatch_owner_immediately(
    tmp_path: Path,
) -> None:
    """标准 governed start 在创建 dispatch record 时立即写入 owner。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: dispatch record owner 未立即写入 scheduler
        instance id 时抛出。
    """

    host_identity = HostInstanceIdentity(
        host_instance_id="host-instance-governed-start",
        pid=1,
        process_start_token="process-token-governed-start",
        boot_id=None,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-governed-owner",
            display_text="需要分析当前季度收入。",
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            host_handle_id="host-handle-governed-start",
            host_instance_identity=host_identity,
        )
        try:
            run = _read_run(store.transaction_runner, seeded.run_id)
            pending = _start_governed_for_test(store.transaction_runner, scheduler, run)
            dispatch_record = _read_dispatch_record_by_attempt_id(store.transaction_runner, pending.attempt_id)

            assert dispatch_record.owner_host_instance_id == scheduler.host_instance_id
            assert dispatch_record.owner_host_instance_id is not None
            assert dispatch_record.owner_host_instance_id != "host-handle-governed-start"
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_compaction_uses_selected_material_not_session_start_range(
    tmp_path: Path,
) -> None:
    """proactive request 使用 selected ordinary material，不从 Session 起点扫描。"""

    compactor = _RequestCapturingCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-proactive-selected-material",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            assert len(compactor.requests) == 1
            request = compactor.requests[0]
            assert request.segment_selection.input_cursor == (
                _run_input_sequence(store.transaction_runner, seeded.run_id)
            )
            assert request.material_source_refs == (f"event-input-{seeded.run_id}",)
            assert request.segment_selection.selected_block_ids == ()
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view(
    tmp_path: Path,
) -> None:
    """proactive material pack 与 ordinary material 使用同一去重视图。"""

    compactor = _RequestCapturingCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-proactive-material-size",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            request = compactor.requests[0]
            ordinary_chars = len(_soft_threshold_prompt())
            pack_chars = len(str(request.llm_material_json()))
            assert pack_chars <= ordinary_chars + 512
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_wake_queue_promotion_uses_tracked_async_promotion_task(
    tmp_path: Path,
) -> None:
    """sync wakeup 入队后由 scheduler 管理的 promotion task 完成 compact。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-wake-soft-compact",
            display_text=_soft_threshold_prompt(),
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
            await _wait_for_event_count(
                store.transaction_runner,
                CONTEXT_COMPACTED,
                expected_count=1,
            )

            assert scheduler._promotion_drain_task is not None
            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 1
            assert CONTEXT_COMPACTED in _event_types_for_run(store.transaction_runner, seeded.run_id)
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_wake_queue_promotion_logs_promotion_task_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """promotion drain task 捕获并记录异常，避免 silent task exception。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(tmp_path, store, _FakeWorkerFactory())

        async def _raising_promotion(session_id: str) -> None:
            """模拟 promotion 内部异常。

            :param session_id: promotion session id。
            :returns: 不返回。
            :raises RuntimeError: 始终抛出测试异常。
            """

            del session_id
            raise RuntimeError("promotion failed")

        monkeypatch.setattr(scheduler, "run_queue_promotion", _raising_promotion)
        try:
            with caplog.at_level(logging.WARNING):
                scheduler.wake_queue_promotion("session-promotion-error")
                await _wait_for_log_message(
                    caplog,
                    "dispatch.queue_promotion.runtime_error",
                )

            assert scheduler._promotion_drain_task is not None
            assert scheduler._promotion_drain_task.done() is False
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_close_cancels_tracked_promotion_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """scheduler close 会取消 promotion task，但不无限 drain 本地 promotion queue。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        scheduler = await _open_scheduler(tmp_path, store, _FakeWorkerFactory())
        blocker = asyncio.Event()
        promotion_started = asyncio.Event()

        async def _blocked_promotion(session_id: str) -> None:
            """模拟长期运行的 promotion。

            :param session_id: promotion session id。
            :returns: ``None``。
            """

            del session_id
            promotion_started.set()
            await blocker.wait()

        monkeypatch.setattr(scheduler, "run_queue_promotion", _blocked_promotion)
        scheduler.wake_queue_promotion("session-promotion-close")
        await _wait_for_promotion_task_started(scheduler)
        await promotion_started.wait()
        promotion_task = scheduler._promotion_drain_task
        assert promotion_task is not None
        scheduler._promotion_queue.put_nowait("session-promotion-pending")
        event_log_cursor = _event_log_cursor(store.transaction_runner)

        await scheduler.close()

        assert promotion_task.done() is True
        assert scheduler._promotion_queue.qsize() == 1
        _assert_scheduler_close_did_not_append_terminal_facts(
            store.transaction_runner,
            after_cursor=event_log_cursor,
        )


@pytest.mark.asyncio
async def test_scheduler_wake_methods_fail_after_close_and_close_is_idempotent(
    tmp_path: Path,
) -> None:
    """scheduler close 后 wake 方法稳定失败，重复 close 保持幂等。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, _FakeWorkerFactory())

        await scheduler.close()
        await scheduler.close()

        with pytest.raises(RuntimeError, match="HostDispatchScheduler is closed"):
            scheduler.wake_dispatch(_pending_dispatch(seeded))
        with pytest.raises(RuntimeError, match="HostDispatchScheduler is closed"):
            scheduler.wake_queue_promotion(seeded.session_id)


@pytest.mark.asyncio
async def test_proactive_compaction_calls_llm_outside_write_transaction(
    tmp_path: Path,
) -> None:
    """proactive compactor 外部调用不持有 Host write transaction。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-proactive-outside-transaction",
            display_text=_soft_threshold_prompt(),
        )
        compactor = _TransactionReadableCompactor(store.transaction_runner)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            assert compactor.calls == 1
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_compaction_stale_result_does_not_write_compacted_event(
    tmp_path: Path,
) -> None:
    """proactive compact 返回后状态已变化时不写 ``CONTEXT_COMPACTED``。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-proactive-stale-result",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=_StaleMutatingCompactor(store.transaction_runner),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
            assert _run_status(store.transaction_runner, seeded.run_id) == (RunStatus.FAILED)
            failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_FAILED,
            )
            requested = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_REQUESTED,
            )
            payload = _event_payload(failed)
            assert payload["failure_reason"] == "stale_compaction_result"
            assert_failed_payload_no_fallback(
                payload,
                expected_operation_id=requested.event_id,
                expected_attempt_count=1,
                expected_retry_repair_budget_exhausted=False,
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_proactive_compaction_retries_quality_rejection_before_accept(
    tmp_path: Path,
) -> None:
    """proactive compact 首次 quality rejection 后 retry 并写入 accepted fact。"""

    compactor = _QualityRejectOnceCompactor()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-proactive-quality-retry",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=2,
            ),
            context_compactor=compactor,
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)
            event_types = _event_types_for_run(store.transaction_runner, seeded.run_id)

            assert compactor.calls == 2
            assert (
                _event_count(
                    store.transaction_runner,
                    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                )
                == 1
            )
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 1
            assert event_types.index(CONTEXT_COMPACTION_ATTEMPT_REJECTED) < (event_types.index(CONTEXT_COMPACTED))
            assert event_types.index(CONTEXT_COMPACTED) < event_types.index("RUN_STARTED")
            assert _run_status(store.transaction_runner, seeded.run_id) == (RunStatus.RUNNING)
            rejected = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            )
            assert _event_payload(rejected)["failure_category"] == ("quality_check_rejected")
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_compaction_repair_attempt_rejection_is_recorded_in_eventlog(
    tmp_path: Path,
) -> None:
    """semantic proposal failure 写 rejected facts 后通过 fallback dispatch。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-proactive-attempt-rejected",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(
                max_compaction_attempts_per_operation=2,
            ),
            context_compactor=_RaisingCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)
            assert (await scheduler.drain_once()).dispatched == 1

            assert (
                _event_count(
                    store.transaction_runner,
                    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                )
                == 2
            )
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTION_FAILED) == 1
            requested = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_REQUESTED,
            )
            rejected = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_ATTEMPT_REJECTED,
            )
            failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_FAILED,
            )
            assert _event_payload(rejected)["operation_id"] == requested.event_id
            payload = _event_payload(failed)
            assert payload["operation_id"] == requested.event_id
            assert payload["attempt_count"] == 2
            assert payload["retry_repair_budget_exhausted"] is True
            assert payload["fallback_action"] == "dispatch"
            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 1
            assert len(factory.accepted_requests) == 1
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_pre_start_governance_compact_failure_is_attempt_free(
    tmp_path: Path,
) -> None:
    """proactive compact 缺 compactor 后 fallback 预算通过会创建 Attempt。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-compact-failure",
            display_text=_soft_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)
            assert (await scheduler.drain_once()).dispatched == 1

            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 1
            assert _run_status(store.transaction_runner, seeded.run_id) == (RunStatus.RUNNING)
            event_types = _event_types_for_run(store.transaction_runner, seeded.run_id)
            assert event_types.index(CONTEXT_COMPACTION_FAILED) < event_types.index("RUN_STARTED")
            assert event_types.index("RUN_STARTED") < event_types.index("ATTEMPT_STARTED")
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
            assert len(factory.accepted_requests) == 1
            requested = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_REQUESTED,
            )
            failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_FAILED,
            )
            payload = _event_payload(failed)
            assert payload["operation_id"] == requested.event_id
            assert payload["fallback_action"] == "dispatch"
            assert isinstance(payload["fallback_input_window"], Mapping)
            assert payload["fallback_input_window"]["current_input_ref"] == (
                f"event-input-{seeded.run_id}"
            )
            assert isinstance(payload["fallback_budget_result"], Mapping)
            assert payload["fallback_budget_result"]["status"] == "within_hard_budget"
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_pre_start_governance_fallback_budget_fail_closes_run(
    tmp_path: Path,
) -> None:
    """fallback selected view 超过 hard budget 时 fail closed 且不创建 Attempt。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_accepted_run(
            store,
            run_id="run-fallback-over-budget",
            display_text=_hard_threshold_prompt(),
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _FakeWorkerFactory(),
            context_budget_policy=_soft_compact_policy(),
        )
        try:
            await scheduler.run_queue_promotion(seeded.session_id)

            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 0
            assert _run_status(store.transaction_runner, seeded.run_id) == RunStatus.FAILED
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
            failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_FAILED,
            )
            payload = _event_payload(failed)
            assert payload["fallback_action"] == "fail_closed"
            assert isinstance(payload["fallback_budget_result"], Mapping)
            assert payload["fallback_budget_result"]["status"] == "over_hard_budget"
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
            await scheduler.run_queue_promotion(seeded.session_id)

            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 0
            assert _run_status(store.transaction_runner, seeded.run_id) == (RunStatus.FAILED)
            assert (
                _event_types_for_run(store.transaction_runner, seeded.run_id).count(CONTEXT_COMPACTION_REQUESTED) == 1
            )
            failed = _read_event_by_type(store.transaction_runner, CONTEXT_COMPACTION_FAILED)
            payload = _event_payload(failed)
            assert payload["failure_reason"] == "proactive_compact_limit_reached"
            assert_failed_payload_no_fallback(
                payload,
                expected_operation_id=None,
                expected_attempt_count=0,
                expected_retry_repair_budget_exhausted=False,
            )
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
            await scheduler.run_queue_promotion(seeded.session_id)

            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 0
            assert _run_status(store.transaction_runner, seeded.run_id) == (RunStatus.FAILED)
            failed = _read_event_by_type(store.transaction_runner, CONTEXT_COMPACTION_FAILED)
            payload = _event_payload(failed)
            assert payload["failure_reason"] == "proactive_compact_count_unreadable"
            assert_failed_payload_no_fallback(
                payload,
                expected_operation_id=None,
                expected_attempt_count=0,
                expected_retry_repair_budget_exhausted=False,
            )
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
            second_contents = tuple(_message_text(message) for message in factory.accepted_requests[1].messages)
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
            event_types = _event_types_for_run(store.transaction_runner, compacted.run_id)
            compacted_request_contents = tuple(
                content
                for content in (_message_text(message) for message in factory.accepted_requests[2].messages)
                if content is not None
            )
            assert event_types.index(CONTEXT_COMPACTED) < event_types.index("RUN_STARTED")
            assert (
                _content_index(
                    compacted_request_contents,
                    "Accepted compact artifact is available for this run.",
                )
                < len(compacted_request_contents) - 1
            )
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
                for content in (_message_text(message) for message in factory.accepted_requests[3].messages)
                if content is not None
            )
            joined = "\n\n".join(after_compact_contents)
            goal_index = _content_index(after_compact_contents, "current_goal=")
            raw_index = after_compact_contents.index("follow-up under budget")
            episode_index = _content_index(after_compact_contents, "Memory episode summaries:")

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
async def test_reactive_compact_failure_fallback_dispatch_uses_failed_view(
    tmp_path: Path,
) -> None:
    """reactive compact failure fallback 创建新 Attempt 且不依赖 compact artifact。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        factory = _ReactiveRecoveryWorkerFactory()
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=_soft_compact_policy(),
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
            assert factory.accepted_snapshots[1].attempt_id != seeded.attempt_id
            assert factory.accepted_snapshots[1].execution_id != seeded.execution_id
            assert _attempt_count_for_run(store.transaction_runner, seeded.run_id) == 2
            assert _event_count(store.transaction_runner, CONTEXT_COMPACTED) == 0
            assert _event_count(store.transaction_runner, "RUN_LOST") == 0
            failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_FAILED,
            )
            payload = _event_payload(failed)
            assert payload["fallback_action"] == "dispatch"
            assert payload["fallback_policy_decision"] == (
                "deterministic_recent_window"
            )
            second_contents = tuple(
                content
                for content in (
                    _message_text(message)
                    for message in factory.accepted_requests[1].messages
                )
                if content is not None
            )
            assert "Accepted compact artifact is available for this run." not in (
                "\n".join(second_contents)
            )
            assert second_contents[-1] == "dispatch prompt"
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit(
    tmp_path: Path,
) -> None:
    """连续 reactive overflow 达到上限后 fail closed，不无限创建 Attempt。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        factory = _RepeatedReactiveOverflowWorkerFactory()
        policy = _soft_compact_policy(max_reactive_compactions_per_run=2)
        expected_attempt_count = 1 + policy.max_reactive_compactions_per_run
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            context_budget_policy=policy,
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            assert (await scheduler.drain_once()).dispatched == 1

            await factory.wait_for_accepted_count(expected_attempt_count)
            await factory.wait_for_closed_count(expected_attempt_count)

            run = _read_run(store.transaction_runner, seeded.run_id)
            event_types = _event_types_for_run(store.transaction_runner, seeded.run_id)
            failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                CONTEXT_COMPACTION_FAILED,
            )
            failed_payload = _event_payload(failed)
            run_failed = _latest_event_for_run(
                store.transaction_runner,
                seeded.run_id,
                "RUN_FAILED",
            )
            run_failed_payload = _event_payload(run_failed)
            actual_attempt_count = _attempt_count_for_run(
                store.transaction_runner,
                seeded.run_id,
            )

            assert run.status == RunStatus.FAILED
            assert factory.created == expected_attempt_count
            assert len(factory.accepted_snapshots) == expected_attempt_count
            assert actual_attempt_count == expected_attempt_count
            assert actual_attempt_count <= expected_attempt_count
            assert event_types.count(CONTEXT_COMPACTION_REQUESTED) == (
                policy.max_reactive_compactions_per_run
            )
            assert event_types.count(CONTEXT_COMPACTED) == (
                policy.max_reactive_compactions_per_run
            )
            assert event_types.count(CONTEXT_COMPACTION_FAILED) == 1
            assert event_types.count("RUN_LOST") == 0
            assert event_types.count("RUN_FAILED") == 1
            assert failed_payload["failure_reason"] == (
                "reactive_compact_limit_reached"
            )
            assert_failed_payload_no_fallback(
                failed_payload,
                expected_operation_id=None,
                expected_attempt_count=0,
                expected_retry_repair_budget_exhausted=False,
            )
            assert run_failed_payload["error_code"] == (
                "reactive_compact_limit_reached"
            )
            assert run_failed_payload["context_compaction_failed_event_id"] == (
                failed.event_id
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_reactive_recovery_uses_fresh_duplicate_governance_attempt(
    tmp_path: Path,
) -> None:
    """reactive recovery 新 Attempt 对相同工具参数执行 fresh request。"""

    first_event_gate = asyncio.Event()
    tool = _CountingTool()
    duplicate_policy = DuplicateGovernancePolicy(
        default_duplicate_decision=DuplicateDecisionKind.REUSE
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        factory = _ReactiveRecoveryWorkerFactory(
            final_blocks=True,
            first_event_gate=first_event_gate,
        )
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            agent_policy=_agent_policy(True),
            tooling_options=_tooling_options(
                tool,
                duplicate_governance_policy=duplicate_policy,
            ),
            context_budget_policy=_soft_compact_policy(),
            context_compactor=FakeContextCompactor(),
            compact_artifact_root=tmp_path / "compact-artifacts",
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            assert (await scheduler.drain_once()).dispatched == 1
            first_request = factory.accepted_requests[0]
            first_tool_outcome = await first_request.tool_executor.execute(
                _tool_execution_request(
                    seeded,
                    first_request,
                    ToolCallRequest(
                        tool_call_id="tool-call-first-attempt",
                        name="fake_dispatch_tool",
                        arguments={"ticker": "DAYU"},
                        index_in_iteration=0,
                        provider_state=None,
                    ),
                )
            )
            first_duplicate_outcome = await first_request.tool_executor.execute(
                _tool_execution_request(
                    seeded,
                    first_request,
                    ToolCallRequest(
                        tool_call_id="tool-call-first-attempt-duplicate",
                        name="fake_dispatch_tool",
                        arguments={"ticker": "DAYU"},
                        index_in_iteration=0,
                        provider_state=None,
                    ),
                )
            )

            assert isinstance(
                first_tool_outcome.records[0].outcome,
                ToolCompletedOutcome,
            )
            assert isinstance(
                first_duplicate_outcome.records[0].outcome,
                ToolCompletedOutcome,
            )
            assert tool.call_count == 1

            first_event_gate.set()
            await _wait_for_accepted_snapshot_count(factory, 2)
            second_request = factory.accepted_requests[1]
            second_tool_outcome = await second_request.tool_executor.execute(
                _tool_execution_request(
                    seeded,
                    second_request,
                    ToolCallRequest(
                        tool_call_id="tool-call-second-attempt",
                        name="fake_dispatch_tool",
                        arguments={"ticker": "DAYU"},
                        index_in_iteration=0,
                        provider_state=None,
                    ),
                )
            )

            assert factory.accepted_snapshots[0].attempt_id == seeded.attempt_id
            assert factory.accepted_snapshots[1].attempt_id != seeded.attempt_id
            assert isinstance(
                second_tool_outcome.records[0].outcome,
                ToolCompletedOutcome,
            )
            assert tool.call_count == 2
            assert _run_status(store.transaction_runner, seeded.run_id) == (RunStatus.RUNNING)
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
    host_handle_id: str = "host-test",
    host_instance_identity: HostInstanceIdentity | None = None,
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
    :param host_handle_id: scheduler 使用的 Host handle id。
    :param host_instance_identity: 可选 Host instance 身份；用于测试 handle
        与 instance id 不同的 owner 写入路径。
    :returns: scheduler。
    :raises Exception: lane controller 或 durable host instance 注册失败时透传。
    """

    local_execution = HostLocalExecutionOptions(
        lane_db_path=(lane_db_path if lane_db_path is not None else tmp_path / "lane.sqlite3"),
        lane_name=_LANE_NAME,
        lane_capacity=1,
        lane_default_timeout_seconds=lane_default_timeout_seconds,
        lane_claim_ttl_seconds=1.0,
        lane_heartbeat_interval_seconds=0.1,
        worker_startup_timeout_seconds=worker_startup_timeout_seconds,
        dispatch_poll_interval_seconds=0.01,
        runner_spec=_runner_spec(),
        runner_options=RunnerCallOptions(temperature=None, max_tokens=None, top_p=None, stream=False),
        agent_policy=agent_policy if agent_policy is not None else _agent_policy(False),
        worker_factory=factory,
        tooling_options=tooling_options,
        context_budget_policy=context_budget_policy,
        context_compactor=context_compactor,
        compact_artifact_root=compact_artifact_root,
    )
    if host_instance_identity is None:
        return await HostDispatchScheduler.open(
            transaction_runner=store.transaction_runner,
            local_execution=local_execution,
            host_handle_id=host_handle_id,
            active_registry=active_registry,
            projection_catchup_port=projection_catchup,
        )
    _register_host_instance(store.transaction_runner, host_instance_identity)
    lane_controller = await LaneController.open(
        [
            LaneConfig(
                name=local_execution.lane_name,
                capacity=local_execution.lane_capacity,
                default_timeout_seconds=local_execution.lane_default_timeout_seconds,
                claim_ttl_seconds=local_execution.lane_claim_ttl_seconds,
                heartbeat_interval_seconds=(local_execution.lane_heartbeat_interval_seconds),
            )
        ],
        coordinator=SQLiteLaneCoordinatorConfig(db_path=local_execution.lane_db_path),
        owner=LaneOwner(
            owner_id=f"lane-owner-{host_handle_id}",
            pid=host_instance_identity.pid,
            process_start_token=host_instance_identity.process_start_token,
        ),
    )
    return HostDispatchScheduler(
        transaction_runner=store.transaction_runner,
        event_log_store=EventLogStore(),
        local_execution=local_execution,
        lane_controller=lane_controller,
        host_handle_id=host_handle_id,
        host_instance_identity=host_instance_identity,
        active_registry=active_registry,
        projection_catchup_port=projection_catchup,
    )


def _register_host_instance(transaction_runner: HostTransactionRunner, identity: HostInstanceIdentity) -> None:
    """注册测试 scheduler 的 Host instance row。

    :param transaction_runner: Host transaction runner。
    :param identity: 待注册的 Host instance 身份。
    :returns: ``None``。
    :raises Exception: durable host instance 注册失败时透传。
    """

    def _operation(transaction: HostTransaction) -> None:
        register_current_instance(transaction, identity)

    transaction_runner.run_write(_operation)


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


def _tooling_options(
    tool: _CountingTool,
    *,
    duplicate_governance_policy: DuplicateGovernancePolicy | None = None,
) -> HostToolingOptions:
    """构造 tool-enabled dispatch 测试用工具装配选项。

    :param tool: 测试业务工具 callable。
    :param duplicate_governance_policy: 可选 duplicate governance 策略。
    :returns: HostToolingOptions。
    """

    return HostToolingOptions(
        business_tool_bundle=ToolBundle(definitions=(_tool_definition("fake_dispatch_tool", tool),)),
        source_refs=(
            ToolBundleSourceRef(
                source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
                source_id="dispatch-tool-test",
            ),
        ),
        duplicate_governance_policy=(
            duplicate_governance_policy
            if duplicate_governance_policy is not None
            else DuplicateGovernancePolicy()
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


def _seed_current_run(store: HostDurableStore, *, session_id: str | None = None) -> _SeededRun:
    """创建 running Run、STARTING Attempt 和 pending dispatch。

    :param store: durable store。
    :param session_id: 可选已有 Session id；不传则创建默认测试 Session。
    :returns: seeded run 摘要。
    """

    actual_session_id = _ensure_session_id(store.transaction_runner) if session_id is None else session_id
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


def _soft_compact_policy(
    *,
    max_compaction_attempts_per_operation: int = 1,
    max_reactive_compactions_per_run: int = DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN,
) -> ContextBudgetPolicy:
    """构造会对测试 prompt 触发 soft compact 的预算策略。

    :param max_compaction_attempts_per_operation: 单个 compaction operation 的 proposal attempt 上限。
    :param max_reactive_compactions_per_run: 单个 Run 允许的 reactive compact 次数。
    :returns: context budget policy。
    """

    return context_budget_policy_from_threshold_tokens(
        context_window_size=_SOFT_CONTEXT_WINDOW_SIZE,
        soft_threshold_tokens=int(
            (_SOFT_CONTEXT_WINDOW_SIZE - _SOFT_RESERVED_OUTPUT_TOKENS) * (1 - _SOFT_SAFETY_MARGIN_RATIO)
        ),
        hard_threshold_tokens=_SOFT_HARD_THRESHOLD_TOKENS,
        max_reactive_compactions_per_run=max_reactive_compactions_per_run,
        max_compaction_attempts_per_operation=(max_compaction_attempts_per_operation),
        policy_ref="test-soft-compact-policy",
    )


def _soft_threshold_prompt() -> str:
    """返回触发 soft threshold 且未达 hard threshold 的测试 prompt。

    :returns: 测试 prompt。
    """

    return "x" * _SOFT_THRESHOLD_PROMPT_CHAR_COUNT


def _hard_threshold_prompt() -> str:
    """返回触发 hard threshold 的测试 prompt。

    :returns: 测试 prompt。
    """

    return "x" * _HARD_THRESHOLD_PROMPT_CHAR_COUNT


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
        dispatch_record = read_dispatch_record_by_attempt_id(transaction, seeded.attempt_id)
        assert run is not None
        assert attempt is not None
        assert dispatch_record is not None
        return run, attempt, dispatch_record

    return transaction_runner.run_read(_operation)


def _read_run(transaction_runner: HostTransactionRunner, run_id: str) -> RunRow:
    """读取指定 Run row。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :returns: Run row。
    :raises AssertionError: Run 缺失时抛出。
    """

    def _operation(transaction: HostTransaction) -> RunRow:
        row = read_run_by_id(transaction, run_id)
        assert row is not None
        return row

    return transaction_runner.run_read(_operation)


def _read_dispatch_record_by_attempt_id(
    transaction_runner: HostTransactionRunner, attempt_id: str
) -> DispatchRecordRow:
    """读取指定 Attempt 对应的 dispatch record。

    :param transaction_runner: transaction runner。
    :param attempt_id: Attempt id。
    :returns: Dispatch record row。
    :raises AssertionError: dispatch record 缺失时抛出。
    """

    def _operation(transaction: HostTransaction) -> DispatchRecordRow:
        row = read_dispatch_record_by_attempt_id(transaction, attempt_id)
        assert row is not None
        return row

    return transaction_runner.run_read(_operation)


def _start_governed_for_test(
    transaction_runner: HostTransactionRunner,
    scheduler: HostDispatchScheduler,
    run: RunRow,
) -> PendingDispatchRecord:
    """在测试事务内执行标准 governed start。

    :param transaction_runner: transaction runner。
    :param scheduler: 待测试的 scheduler。
    :param run: 待启动 Run row。
    :returns: 新创建的 pending dispatch 摘要。
    :raises AssertionError: governed start CAS 未创建 dispatch 时抛出。
    """

    def _operation(transaction: HostTransaction) -> PendingDispatchRecord | None:
        return scheduler._start_governed_in_transaction(transaction, run)

    pending = transaction_runner.run_write(_operation)
    assert pending is not None
    return pending


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


def _run_input_sequence(transaction_runner: HostTransactionRunner, run_id: str) -> int:
    """读取 Run input event sequence。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :returns: Run input event sequence。
    :raises AssertionError: Run 缺失时抛出。
    """

    def _operation(transaction: HostTransaction) -> int:
        row = read_run_by_id(transaction, run_id)
        assert row is not None
        return row.input_event_sequence

    return transaction_runner.run_read(_operation)


def _attempt_count_for_run(transaction_runner: HostTransactionRunner, run_id: str) -> int:
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


def _event_types_for_run(transaction_runner: HostTransactionRunner, run_id: str) -> tuple[str, ...]:
    """按 sequence 读取指定 Run 的 EventLog 类型。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :returns: event type 元组。
    """

    def _operation(transaction: HostTransaction) -> tuple[str, ...]:
        rows = EventLogStore().read_events_after(
            transaction,
            0,
            limit=_EVENT_LOG_TEST_READ_LIMIT,
        )
        return tuple(row.event_type for row in rows if row.run_id == run_id)

    return transaction_runner.run_read(_operation)


def _event_log_cursor(transaction_runner: HostTransactionRunner) -> int:
    """读取测试库中当前 EventLog 最大游标。

    :param transaction_runner: transaction runner。
    :returns: 当前最大 ``event_sequence``；没有事件时返回 ``0``。
    """

    def _operation(transaction: HostTransaction) -> int:
        rows = EventLogStore().read_events_after(
            transaction,
            0,
            limit=_EVENT_LOG_TEST_READ_LIMIT,
        )
        if not rows:
            return 0
        return max(row.event_sequence for row in rows)

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
            for row in EventLogStore().read_events_after(
                transaction,
                0,
                limit=_EVENT_LOG_TEST_READ_LIMIT,
            )
            if row.event_type == event_type
        )

    return transaction_runner.run_read(_operation)


def _event_log_types_after_cursor(
    transaction_runner: HostTransactionRunner,
    after_cursor: int,
) -> tuple[str, ...]:
    """读取指定游标之后新增的 EventLog type。

    :param transaction_runner: transaction runner。
    :param after_cursor: 只读取该 EventLog cursor 之后的事件。
    :returns: 新增 EventLog type 序列。
    """

    def _operation(transaction: HostTransaction) -> tuple[str, ...]:
        rows = EventLogStore().read_events_after(
            transaction,
            after_cursor,
            limit=_EVENT_LOG_TEST_READ_LIMIT,
        )
        return tuple(row.event_type for row in rows)

    return transaction_runner.run_read(_operation)


def _scheduler_close_terminal_event_types() -> frozenset[str]:
    """读取 close 不得自行追加的当前 terminal EventLog type 集合。

    :returns: Attempt / Run 终态映射对应的 EventLog type 集合。
    """

    return frozenset(
        (
            *(_attempt_terminal_event_type(status) for status in _ATTEMPT_TERMINAL_STATUSES),
            *(_run_terminal_event_type(status) for status in _RUN_TERMINAL_STATUSES),
        )
    )


def _terminal_event_log_types_after_cursor(
    transaction_runner: HostTransactionRunner,
    after_cursor: int,
) -> tuple[str, ...]:
    """读取指定游标之后新增的 terminal EventLog type。

    :param transaction_runner: transaction runner。
    :param after_cursor: 只读取该 EventLog cursor 之后的事件。
    :returns: 新增 terminal EventLog type 序列。
    """

    terminal_event_types = _scheduler_close_terminal_event_types()
    return tuple(
        event_type
        for event_type in _event_log_types_after_cursor(transaction_runner, after_cursor)
        if event_type in terminal_event_types
    )


def _assert_scheduler_close_did_not_append_terminal_facts(
    transaction_runner: HostTransactionRunner,
    *,
    after_cursor: int,
) -> None:
    """断言 scheduler close 未追加 terminal canonical facts。

    :param transaction_runner: transaction runner。
    :param after_cursor: close 前记录的 EventLog cursor。
    :returns: ``None``。
    :raises AssertionError: close 后出现新增 terminal EventLog row 时抛出。
    """

    assert _terminal_event_log_types_after_cursor(transaction_runner, after_cursor) == ()


async def _wait_for_event_count(
    transaction_runner: HostTransactionRunner,
    event_type: str,
    *,
    expected_count: int,
) -> None:
    """等待指定 event type 达到期望数量。

    :param transaction_runner: transaction runner。
    :param event_type: event type。
    :param expected_count: 期望数量。
    :returns: ``None``。
    :raises AssertionError: 超时未达到数量时抛出。
    """

    for _index in range(200):
        if _event_count(transaction_runner, event_type) >= expected_count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"event count did not converge: {event_type}")


def _latest_event_for_run(transaction_runner: HostTransactionRunner, run_id: str, event_type: str) -> EventLogRow:
    """按 Run 读取最近一条指定 EventLog row。

    :param transaction_runner: transaction runner。
    :param run_id: Run id。
    :param event_type: event type。
    :returns: EventLog row。
    """

    def _operation(transaction: HostTransaction) -> EventLogRow:
        rows = EventLogStore().read_events_after(
            transaction,
            0,
            limit=_EVENT_LOG_TEST_READ_LIMIT,
        )
        for row in reversed(rows):
            if row.run_id == run_id and row.event_type == event_type:
                return row
        raise AssertionError(f"missing event type {event_type}")

    return transaction_runner.run_read(_operation)


def _event_payload(row: EventLogRow) -> Mapping[str, JsonValue]:
    """解析 EventLog row payload。

    :param row: EventLog row。
    :returns: payload mapping。
    """

    value = cast(JsonValue, json.loads(row.payload_json))
    assert isinstance(value, Mapping)
    return cast(Mapping[str, JsonValue], value)


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
        row = transaction_runner.run_read(lambda transaction: read_run_by_id(transaction, run_id))
        assert row is not None
        if row.status == expected_run:
            return row
        await asyncio.sleep(0.01)
    row = transaction_runner.run_read(lambda transaction: read_run_by_id(transaction, run_id))
    assert row is not None
    raise AssertionError(f"run status did not converge: {row.status.value}")


async def _wait_for_log_message(caplog: pytest.LogCaptureFixture, expected_fragment: str) -> None:
    """等待 caplog 捕获包含指定片段的日志。

    :param caplog: pytest log capture fixture。
    :param expected_fragment: 期望日志片段。
    :returns: ``None``。
    :raises AssertionError: 超时未捕获日志时抛出。
    """

    for _index in range(200):
        if any(expected_fragment in record.message for record in caplog.records):
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"log message did not converge: {expected_fragment}")


async def _wait_for_promotion_task_started(
    scheduler: HostDispatchScheduler,
) -> None:
    """等待 scheduler promotion task 进入运行态。

    :param scheduler: dispatch scheduler。
    :returns: ``None``。
    :raises AssertionError: 超时未启动时抛出。
    """

    for _index in range(200):
        task = scheduler._promotion_drain_task
        if task is not None and not task.done():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("promotion task did not start")


async def _run_scheduler_drain_once(scheduler: HostDispatchScheduler) -> None:
    """以 ``Task[None]`` 形态运行一次 scheduler drain。

    :param scheduler: dispatch scheduler。
    :returns: ``None``。
    :raises RuntimeError: scheduler 已关闭时透传。
    """

    await scheduler.drain_once()


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
    await scheduler.run_queue_promotion(seeded.session_id)
    await _wait_for_final_request_count(factory, expected_request_count)
    await _wait_for_run_status(
        store.transaction_runner,
        seeded.run_id,
        expected_run=RunStatus.SUCCEEDED,
    )
    return seeded


async def _wait_for_final_request_count(factory: _FinalAnswerWorkerFactory, expected_count: int) -> None:
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
    raise AssertionError(f"worker request count did not converge: {len(factory.accepted_requests)}")


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


async def _wait_for_accepted_snapshot_count(factory: _ReactiveRecoveryWorkerFactory, expected_count: int) -> None:
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
    raise AssertionError("accepted snapshot count did not converge: " f"{len(factory.accepted_snapshots)}")


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
    raise AssertionError("status did not converge: " f"run={run.status.value} attempt={attempt.status.value}")


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


def _read_event_by_type(transaction_runner: HostTransactionRunner, event_type: str) -> EventLogRow:
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


def _mark_dispatching_and_cancel(transaction_runner: HostTransactionRunner, seeded: _SeededRun) -> None:
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


def _cancel_predispatch_dispatching(transaction_runner: HostTransactionRunner, seeded: _SeededRun) -> None:
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
