"""Host 本地 dispatch scheduler。

本模块实现 Phase 5 本地 dispatch 的最小调度闭环：commit 后接收
pending dispatch 摘要，获取 runtime lane capacity，durable recheck 后
调用 LocalProxy，并在 worker accept 后追加 ``ATTEMPT_RUNNING`` 与推进
Attempt ``RUNNING``。``dispatching`` 与 lane token 只作为诊断和容量控制，
不表达 owner truth、lease、fencing 或 takeover proof。
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    RunCancelledData,
)
from dayu.host.admission import (
    PendingDispatchRecord,
    create_host_admission_service,
)
from dayu.host.api import (
    AttemptDispatchSnapshot,
    AttemptStatus,
    HostLocalExecutionOptions,
    LocalWorkerHandle,
    RunStatus,
    SourceRunRelation,
)
from dayu.host.durable.codec import format_utc_timestamp, sha256_digest_json
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventPayloadTextEqualsFilter,
    EventLogStore,
)
from dayu.host.durable.errors import HostTransactionRetryExhaustedError
from dayu.host.durable.liveness import (
    HostInstanceIdentity,
    heartbeat_current_instance,
    mark_current_instance_stopped,
    mark_current_instance_stopping,
    register_current_instance,
)
from dayu.host.durable.run_transition import (
    FailUnstartedRunInput,
    StartGovernedRunInput,
    TerminalCloseoutInput,
    fail_unstarted_run_in_transaction,
    start_governed_run_with_starting_attempt_in_transaction,
    terminal_closeout_in_transaction,
)
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    RunRow,
    RunStartReason,
    StateMutationStatus,
    WorkerKind,
    cancel_starting_dispatch_record_row,
    mark_attempt_running_row,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatch_worker_accepted_row,
    mark_dispatching_after_lane_row,
    read_active_run_for_session,
    read_accepted_run_for_session,
    read_attempt_by_id,
    read_dispatch_record_by_id,
    read_dispatch_record_by_attempt_id,
    read_earliest_queued_run,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host._execution_config_projection import (
    effective_execution_snapshot_from_json as _effective_execution_snapshot_from_json,
    required_json_mapping as _required_json_mapping,
    required_json_text as _required_json_text,
)
from dayu.host.engine_ingest import (
    EngineEventCandidate,
    EngineEventIngestor,
    EngineIngestResult,
    EngineIngestStatus,
    LocalEngineEnvelope,
)
from dayu.host.projection import (
    ProjectionCatchupPort,
    catch_up_projection_best_effort,
)
from dayu.host.payload_resolution import event_payload_object
from dayu.host.run_input import (
    DurableCompactArtifactProvider,
    DurableMemorySnapshotProvider,
    MemoryProjectionRepairRequired,
    PolicySnapshot,
    RunInputBuilder,
    ToolExecutionMode,
    create_no_tool_run_input_builder,
    create_tool_enabled_run_input_builder,
)
from dayu.host.memory_repair import catch_up_conversation_memory_projection
from dayu.host._event_payload import payload_object as _payload_object
from dayu.host.compact_artifact import (
    CompactArtifactStore,
    CompactArtifactWriteRequest,
)
from dayu.host.compaction import (
    CompactQualityCheckResult,
    CompactionCandidate,
    CompactionRequest,
    CurrentMessageSummary,
)
from dayu.host.compaction_operation import (
    CompactionAttemptRejected,
    run_compaction_operation,
)
from dayu.host.context_budget import (
    BudgetEstimate,
    BudgetEstimateInput,
    BudgetTextFragment,
    ContextBudgetDecision,
    decide_context_budget,
    estimate_context_budget,
)
from dayu.host.context_events import (
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    CONTEXT_COMPACTION_FAILED,
    CONTEXT_COMPACTION_REQUESTED,
    build_context_compaction_attempt_rejected_payload,
    build_context_compacted_payload,
    build_context_compaction_failed_payload,
    build_context_compaction_requested_payload,
)
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.artifact import LocalArtifactStore
from dayu.host.tool_runtime import (
    DefaultHostToolFactAcceptPort,
    DefaultToolRuntimeFactory,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
    InMemoryRunScopedDuplicateGovernanceRegistry,
    ToolRuntimeBuildRequest,
    ToolRuntimeExecutionScope,
)
from dayu.host.waiting import DefaultHostToolAwaitingAcceptPort
from dayu.runtime.lane import (
    LaneAcquireCancelled,
    LaneAcquired,
    LaneAcquireTimedOut,
    LaneClaimToken,
    LaneConfig,
    LaneController,
    LaneOwner,
    SQLiteLaneCoordinatorConfig,
)
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_EVENT_SOURCE = "host.dispatch"
_EVENT_ACTOR = "host.dispatch"
_EVENT_TYPE_ATTEMPT_RUNNING = "ATTEMPT_RUNNING"
_WORKER_ACCEPT_REASON = "local_worker_accepted"
_WORKER_STARTUP_TIMEOUT_REASON = "worker_startup_timeout"
_MEMORY_PROJECTION_REPAIR_REQUIRED_REASON = "memory_projection_repair_required"
_LOCAL_POLICY_SNAPSHOT_REF = "host-local-no-tool-policy"
_PAYLOAD_FIELD_EFFECTIVE_EXECUTION_CONFIG = "effective_execution_config"
_PAYLOAD_FIELD_EFFECTIVE_TOOL_SET = "effective_tool_set"
_EVENT_ID_ATTEMPT_RUNNING_PREFIX = "event-attempt-running"
_EVENT_ID_ATTEMPT_FAILED_PREFIX = "event-attempt-failed"
_EVENT_ID_RUN_FAILED_PREFIX = "event-run-failed"
_EVENT_ID_CONTEXT_COMPACTION_REQUESTED_PREFIX = "event-context-compact-requested"
_EVENT_ID_CONTEXT_COMPACTED_PREFIX = "event-context-compacted"
_EVENT_ID_CONTEXT_COMPACTION_ATTEMPT_REJECTED_PREFIX = (
    "event-context-compaction-attempt-rejected"
)
_LANE_OWNER_PREFIX = "host-dispatch"
_GOVERNANCE_ACTOR = "host.context_governance"
_GOVERNANCE_FAILURE_REASON = "pre_dispatch_context_governance"
_COMPACT_FAILURE_POLICY_DECISION = "compact_failed_before_dispatch"
_HOST_INSTANCE_HEARTBEAT_INTERVAL_SECONDS = 1.0
_LOG_DRAIN_LOOP_IDLE = (
    "dispatch.drain_loop.idle host_handle_id=%s interval_seconds=%s"
)
_LOG_DRAIN_LOOP_CLOSE_EXIT = "dispatch drain loop exiting after close host_handle_id=%s"
_LOG_DRAIN_LOOP_CANCELLED_FOR_CLOSE = (
    "dispatch drain loop cancelled during close host_handle_id=%s"
)
_LOG_DRAIN_LOOP_CANCELLED_EXTERNALLY = (
    "dispatch drain loop cancelled externally host_handle_id=%s"
)
_LOG_DRAIN_LOOP_UNEXPECTED_EXCEPTION = (
    "dispatch drain loop stopped unexpectedly; continuing host_handle_id=%s "
    "error_type=%s"
)
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DispatchDrainResult:
    """一次 dispatch drain 摘要。

    :param processed: 已处理 wakeup 数。
    :param dispatched: 成功进入 worker accept 的数量。
    :param skipped: durable recheck 或状态前置不满足而跳过的数量。
    :param timed_out: lane acquire 或 worker startup timeout 数量。
    """

    processed: int
    dispatched: int
    skipped: int
    timed_out: int


@dataclass(frozen=True, slots=True)
class ActiveCancelMessage:
    """active worker cancel registry 的最小取消消息。

    :param run_id: 目标 Run id。
    :param attempt_id: 目标 Attempt id。
    :param execution_id: 目标 execution id。
    :param reason: 取消原因。
    """

    run_id: str
    attempt_id: str
    execution_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class _GovernanceCompactAccepted:
    """pre-start compact accepted 后待启动摘要。

    :param run_id: 目标 Run id。
    :param session_id: Session id。
    :param expected_status: compact 前 Run 源状态。
    :param compacted_event_sequence: ``CONTEXT_COMPACTED`` event sequence。
    """

    run_id: str
    session_id: str
    expected_status: RunStatus
    compacted_event_sequence: int


@dataclass(frozen=True, slots=True)
class _GovernanceCompactPending:
    """已写入 request fact、待事务外执行的 proactive compact。

    :param run_id: 目标 Run id。
    :param session_id: Session id。
    :param expected_status: compact request 写入时 Run 状态。
    :param expected_input_event_sequence: compact request 对应输入 cursor。
    :param request: Host-owned compaction request。
    :param operation_id: 对应 ``CONTEXT_COMPACTION_REQUESTED`` event id。
    :param estimate: compact 前预算估算。
    :param decision: 预算决策。
    """

    run_id: str
    session_id: str
    expected_status: RunStatus
    expected_input_event_sequence: int
    request: CompactionRequest
    operation_id: str
    estimate: BudgetEstimate
    decision: ContextBudgetDecision


@dataclass(frozen=True, slots=True)
class _GovernanceStageResult:
    """pre-start governance 阶段结果。

    :param pending_dispatch: 已直接启动时的 pending dispatch。
    :param compact_accepted: compact accepted 但尚未 memory catch-up/start 的摘要。
    :param compact_pending: 已写 request fact、待事务外执行的 compact。
    """

    pending_dispatch: PendingDispatchRecord | None
    compact_accepted: _GovernanceCompactAccepted | None
    compact_pending: _GovernanceCompactPending | None = None


@dataclass(frozen=True, slots=True)
class _EffectiveDispatchDecision:
    """一次 dispatch 从 durable input event 读取的冻结决策。

    :param policy_snapshot: effective runner / agent policy snapshot。
    :param selected_business_tool_names: effective 业务工具名集合；``None`` 表示全量。
    """

    policy_snapshot: PolicySnapshot
    selected_business_tool_names: frozenset[str] | None


@dataclass(frozen=True, slots=True)
class _ActiveWorkerEntry:
    """active worker registry 内部条目。

    :param run_id: 目标 Run id。
    :param handle: worker handle。
    :param cancellation_token: Host 注入 Engine 的取消 token。
    """

    run_id: str
    handle: LocalWorkerHandle
    cancellation_token: "_HostCancellationToken"


@dataclass(frozen=True, slots=True)
class _IsReplayRunOperation:
    """读取 Run source relation 以识别 replay 关联 Run。

    :param run_id: 目标 Run id。
    """

    run_id: str

    def __call__(self, transaction: HostTransaction) -> bool:
        """执行 replay Run 判定读事务。

        :param transaction: 当前 Host 读事务。
        :returns: Run source relation 为 replay 时返回 ``True``。
        :raises RuntimeError: durable Run 缺失时抛出。
        """

        run = read_run_by_id(transaction, self.run_id)
        if run is None:
            raise RuntimeError("dispatch Run is missing")
        return run.source_run_relation is SourceRunRelation.REPLAY


class ActiveWorkerRegistry:
    """进程内 active worker handle registry。

    registry 只提供 best-effort cancel 传播；durable EventLog / Run state
    仍是取消请求是否被接受的真源。
    """

    def __init__(self) -> None:
        """初始化空 registry。

        :returns: ``None``。
        """

        self._lock = RLock()
        self._entries: dict[tuple[str, str], _ActiveWorkerEntry] = {}

    def register(
        self,
        *,
        run_id: str,
        attempt_id: str,
        execution_id: str,
        handle: LocalWorkerHandle,
        cancellation_token: "_HostCancellationToken",
    ) -> None:
        """注册 active worker handle。

        :param run_id: 目标 Run id。
        :param attempt_id: active Attempt id。
        :param execution_id: active execution id。
        :param handle: worker handle。
        :param cancellation_token: 注入 Engine 的取消 token。
        :returns: ``None``。
        """

        with self._lock:
            self._entries[(attempt_id, execution_id)] = _ActiveWorkerEntry(
                run_id=run_id,
                handle=handle,
                cancellation_token=cancellation_token,
            )

    def unregister(self, *, attempt_id: str, execution_id: str) -> None:
        """注销 active worker handle。

        :param attempt_id: active Attempt id。
        :param execution_id: active execution id。
        :returns: ``None``。
        """

        with self._lock:
            self._entries.pop((attempt_id, execution_id), None)

    def cancel(self, message: ActiveCancelMessage) -> bool:
        """向 active worker best-effort 传播 cancel。

        :param message: 最小取消消息。
        :returns: 找到匹配 active worker 时返回 ``True``。
        """

        with self._lock:
            entry = self._entries.get((message.attempt_id, message.execution_id))
        if entry is None or entry.run_id != message.run_id:
            return False
        entry.cancellation_token.request_cancel(message.reason)
        try:
            entry.handle.cancel(message.reason)
        except Exception as exc:
            _LOGGER.warning(
                "active worker cancel failed; continuing attempt_id=%s "
                "execution_id=%s run_id=%s error_type=%s",
                message.attempt_id,
                message.execution_id,
                message.run_id,
                exc.__class__.__name__,
            )
            return True
        return True


class _HostCancellationToken(CancellationToken):
    """Host 可写入、Engine 可观察的取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 已请求取消时返回 ``True``。
        """

        with self._lock:
            return self._reason is not None

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 取消原因；未取消时返回 ``None``。
        """

        with self._lock:
            return self._reason

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 请求时间；未取消时返回 ``None``。
        """

        with self._lock:
            return self._requested_at

    def __init__(self) -> None:
        """初始化未取消 token。

        :returns: ``None``。
        """

        self._lock = RLock()
        self._reason: str | None = None
        self._requested_at: datetime | None = None

    def request_cancel(self, reason: str) -> None:
        """标记 token 已请求取消。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        with self._lock:
            if self._reason is None:
                self._reason = reason
                self._requested_at = datetime.now(UTC)


class HostDispatchScheduler:
    """Host 本地 dispatch scheduler。"""

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        event_log_store: EventLogStore,
        local_execution: HostLocalExecutionOptions,
        lane_controller: LaneController,
        host_handle_id: str,
        host_instance_identity: HostInstanceIdentity | None = None,
        active_registry: ActiveWorkerRegistry | None = None,
        projection_catchup_port: ProjectionCatchupPort | None = None,
    ) -> None:
        """初始化 dispatch scheduler。

        :param transaction_runner: Host durable transaction runner。
        :param event_log_store: EventLog append primitive。
        :param local_execution: 本地执行配置。
        :param lane_controller: 已打开的 runtime lane controller。
        :param host_handle_id: Host handle 诊断 id。
        :param host_instance_identity: 当前 scheduler 的 Host instance 身份；
            不传时创建仅供测试直接构造使用的身份。
        :param active_registry: active worker registry；不传时创建 scheduler 私有 registry。
        :param projection_catchup_port: commit 后 best-effort projection catch-up 端口。
        :returns: ``None``。
        :raises ValueError: ``host_handle_id`` 为空时抛出。
        """

        if host_handle_id.strip() == "":
            raise ValueError("host_handle_id must be non-empty")
        self._transaction_runner = transaction_runner
        self._event_log_store = event_log_store
        self._local_execution = local_execution
        self._lane_controller = lane_controller
        self._host_handle_id = host_handle_id
        self._host_instance_identity = (
            host_instance_identity
            if host_instance_identity is not None
            else _new_dispatch_host_instance_identity(host_handle_id)
        )
        self._active_registry = (
            active_registry if active_registry is not None else ActiveWorkerRegistry()
        )
        self._projection_catchup_port = projection_catchup_port
        self._queue: asyncio.Queue[PendingDispatchRecord] = asyncio.Queue()
        self._promotion_queue: asyncio.Queue[str] = asyncio.Queue()
        self._closed = False
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._drain_task: asyncio.Task[None] | None = None
        self._promotion_drain_task: asyncio.Task[None] | None = None
        self._active_tasks: set[asyncio.Task[None]] = set()
        self._active_handles: set[LocalWorkerHandle] = set()
        self._duplicate_governance_registry = (
            InMemoryRunScopedDuplicateGovernanceRegistry()
        )

    @classmethod
    async def open(
        cls,
        *,
        transaction_runner: HostTransactionRunner,
        local_execution: HostLocalExecutionOptions,
        host_handle_id: str,
        active_registry: ActiveWorkerRegistry | None = None,
        projection_catchup_port: ProjectionCatchupPort | None = None,
    ) -> "HostDispatchScheduler":
        """打开本地 dispatch scheduler。

        :param transaction_runner: Host durable transaction runner。
        :param local_execution: 本地执行配置。
        :param host_handle_id: Host handle 诊断 id。
        :param active_registry: active worker registry；不传时创建 scheduler 私有 registry。
        :param projection_catchup_port: commit 后 best-effort projection catch-up 端口。
        :returns: 已打开 scheduler。
        """

        host_identity = _new_dispatch_host_instance_identity(host_handle_id)
        lane_controller = await LaneController.open(
            [
                LaneConfig(
                    name=local_execution.lane_name,
                    capacity=local_execution.lane_capacity,
                    default_timeout_seconds=(
                        local_execution.lane_default_timeout_seconds
                    ),
                    claim_ttl_seconds=local_execution.lane_claim_ttl_seconds,
                    heartbeat_interval_seconds=(
                        local_execution.lane_heartbeat_interval_seconds
                    ),
                )
            ],
            coordinator=SQLiteLaneCoordinatorConfig(
                db_path=local_execution.lane_db_path
            ),
            owner=LaneOwner(
                owner_id=f"{_LANE_OWNER_PREFIX}-{host_handle_id}",
                pid=os.getpid(),
                process_start_token=host_identity.process_start_token,
            ),
        )
        _register_dispatch_host_instance(
            transaction_runner=transaction_runner,
            identity=host_identity,
        )
        _LOGGER.info(
            "dispatch.scheduler.opened host_handle_id=%s lane_name=%s "
            "lane_capacity=%s",
            host_handle_id,
            local_execution.lane_name,
            local_execution.lane_capacity,
        )
        scheduler = cls(
            transaction_runner=transaction_runner,
            event_log_store=EventLogStore(),
            local_execution=local_execution,
            lane_controller=lane_controller,
            host_handle_id=host_handle_id,
            host_instance_identity=host_identity,
            active_registry=active_registry,
            projection_catchup_port=projection_catchup_port,
        )
        scheduler._start_host_instance_heartbeat()
        return scheduler

    @property
    def host_instance_id(self) -> str:
        """返回当前 scheduler 注册的 Host instance id。

        :returns: 当前 scheduler 自己的 Host instance id。
        """

        return self._host_instance_identity.host_instance_id

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """唤醒 dispatch scheduler。

        :param record: 已持久化的 pending dispatch 摘要。
        :returns: ``None``。
        :raises RuntimeError: scheduler 已关闭时抛出。
        """

        if self._closed:
            raise RuntimeError("HostDispatchScheduler is closed")
        self._queue.put_nowait(record)
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.wake_dispatch run_id=%s attempt_id=%s execution_id=%s "
            "dispatch_record_id=%s queue_size=%s",
            record.run_id,
            record.attempt_id,
            record.execution_id,
            record.dispatch_record_id,
            self._queue.qsize(),
        )
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = asyncio.create_task(self._drain_loop())

    def wake_queue_promotion(self, session_id: str) -> None:
        """唤醒同 Session 的 queued Run promotion。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        :raises RuntimeError: scheduler 已关闭时抛出。
        """

        if self._closed:
            raise RuntimeError("HostDispatchScheduler is closed")
        self._promotion_queue.put_nowait(session_id)
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.queue_promotion.wake session_id=%s queue_size=%s",
            session_id,
            self._promotion_queue.qsize(),
        )
        if (
            self._promotion_drain_task is None
            or self._promotion_drain_task.done()
        ):
            self._promotion_drain_task = asyncio.create_task(
                self._promotion_drain_loop()
            )

    async def run_queue_promotion(self, session_id: str) -> None:
        """执行同 Session queued Run promotion。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        :raises RuntimeError: scheduler 已关闭时抛出。
        """

        if self._closed:
            raise RuntimeError("HostDispatchScheduler is closed")
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.queue_promotion.start session_id=%s",
            session_id,
        )
        catch_up_projection_best_effort(self._projection_catchup_port)
        stage = await self._run_pre_start_governance(session_id)
        pending_dispatch = stage.pending_dispatch
        if stage.compact_accepted is not None:
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "dispatch.queue_promotion.compact_catchup session_id=%s "
                "run_id=%s compacted_event_sequence=%s",
                session_id,
                stage.compact_accepted.run_id,
                stage.compact_accepted.compacted_event_sequence,
            )
            catch_up_conversation_memory_projection(
                self._transaction_runner,
                policy=self._local_execution.memory_projection_policy,
                batch_size=(
                    self._local_execution.memory_projection_catchup_batch_size
                ),
                max_event_sequence=stage.compact_accepted.compacted_event_sequence,
            )
            pending_dispatch = self._start_governed_after_compact(
                stage.compact_accepted
            )
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.queue_promotion.done session_id=%s dispatch_ready=%s "
            "compact_accepted=%s",
            session_id,
            pending_dispatch is not None,
            stage.compact_accepted is not None,
        )
        if pending_dispatch is not None:
            self.wake_dispatch(pending_dispatch)

    async def _run_pre_start_governance(
        self, session_id: str
    ) -> _GovernanceStageResult:
        """执行一次 pre-start Context Governance。

        :param session_id: 目标 Session id。
        :returns: governance 阶段结果。
        """

        def _operation(transaction: HostTransaction) -> _GovernanceStageResult:
            run = _read_startable_run(transaction, session_id)
            if run is None:
                _LOGGER.debug(
                    "dispatch.governance.no_startable_run session_id=%s",
                    session_id,
                )
                return _GovernanceStageResult(
                    pending_dispatch=None, compact_accepted=None
                )
            policy = self._local_execution.context_budget_policy
            if policy is None:
                _LOGGER.log(
                    VERBOSE_LOG_LEVEL,
                    "dispatch.governance.allow_without_budget session_id=%s "
                    "run_id=%s run_status=%s",
                    run.session_id,
                    run.run_id,
                    run.status.value,
                )
                return _GovernanceStageResult(
                    pending_dispatch=self._start_governed_in_transaction(
                        transaction, run
                    ),
                    compact_accepted=None,
                )
            input_event = self._event_log_store.read_event_by_id(
                transaction, run.input_event_id
            )
            if input_event is None:
                _LOGGER.critical(
                    "dispatch.governance.input_missing session_id=%s run_id=%s "
                    "input_event_id=%s",
                    run.session_id,
                    run.run_id,
                    run.input_event_id,
                )
                return _GovernanceStageResult(
                    pending_dispatch=self._fail_unstarted_in_transaction(
                        transaction,
                        run,
                        reason="input_event_missing",
                        error_code="context_governance_input_missing",
                        message="Input event is missing before dispatch",
                    ),
                    compact_accepted=None,
                )
            display_text = _display_text_from_input_event(
                transaction, input_event
            )
            estimate = estimate_context_budget(
                policy,
                BudgetEstimateInput(
                    session_id=run.session_id,
                    run_id=run.run_id,
                    message_fragments=(
                        BudgetTextFragment(
                            fragment_ref=run.input_event_id,
                            text=display_text,
                        ),
                    ),
                    current_prompt_ref=run.input_event_id,
                ),
            )
            decision = decide_context_budget(estimate)
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "dispatch.governance.decision session_id=%s run_id=%s "
                "decision=%s policy_ref=%s",
                run.session_id,
                run.run_id,
                decision.value,
                policy.policy_ref,
            )
            _LOGGER.debug(
                "dispatch.governance.estimate session_id=%s run_id=%s "
                "decision=%s estimated_input_tokens=%s hard_threshold_tokens=%s "
                "estimator_digest=%s",
                run.session_id,
                run.run_id,
                decision.value,
                estimate.estimated_input_tokens,
                estimate.hard_threshold_tokens,
                estimate.estimator_digest,
            )
            if decision is ContextBudgetDecision.ALLOW_DISPATCH:
                return _GovernanceStageResult(
                    pending_dispatch=self._start_governed_in_transaction(
                        transaction, run
                    ),
                    compact_accepted=None,
                )
            if decision is ContextBudgetDecision.BLOCK_HARD_THRESHOLD:
                _LOGGER.error(
                    "dispatch.governance.failed session_id=%s run_id=%s "
                    "failure_reason=%s decision=%s estimated_input_tokens=%s "
                    "hard_threshold_tokens=%s policy_ref=%s",
                    run.session_id,
                    run.run_id,
                    "hard_threshold_before_dispatch",
                    decision.value,
                    estimate.estimated_input_tokens,
                    estimate.hard_threshold_tokens,
                    policy.policy_ref,
                )
                self._append_compaction_failed_event(
                    transaction,
                    run=run,
                    estimate=estimate,
                    decision=decision,
                    failure_reason="hard_threshold_before_dispatch",
                )
                return _GovernanceStageResult(
                    pending_dispatch=self._fail_unstarted_in_transaction(
                        transaction,
                        run,
                        reason=_GOVERNANCE_FAILURE_REASON,
                        error_code="context_hard_threshold_before_dispatch",
                        message="Context estimate exceeds hard threshold before dispatch",
                    ),
                    compact_accepted=None,
                )
            try:
                compact_count = self._committed_proactive_compact_count(
                    transaction, run
                )
            except Exception:
                _LOGGER.error(
                    "dispatch.governance.compact_count_unreadable "
                    "session_id=%s run_id=%s",
                    run.session_id,
                    run.run_id,
                    exc_info=True,
                )
                self._append_compaction_failed_event(
                    transaction,
                    run=run,
                    estimate=estimate,
                    decision=decision,
                    failure_reason="proactive_compact_count_unreadable",
                )
                return _GovernanceStageResult(
                    pending_dispatch=self._fail_unstarted_in_transaction(
                        transaction,
                        run,
                        reason=_GOVERNANCE_FAILURE_REASON,
                        error_code="proactive_compact_count_unreadable",
                        message="Committed proactive compact facts are unreadable",
                    ),
                    compact_accepted=None,
                )
            if compact_count >= policy.max_proactive_compactions_per_run:
                _LOGGER.error(
                    "dispatch.governance.failed session_id=%s run_id=%s "
                    "failure_reason=%s decision=%s compact_count=%s "
                    "max_compact_count=%s policy_ref=%s",
                    run.session_id,
                    run.run_id,
                    "proactive_compact_limit_reached",
                    decision.value,
                    compact_count,
                    policy.max_proactive_compactions_per_run,
                    policy.policy_ref,
                )
                self._append_compaction_failed_event(
                    transaction,
                    run=run,
                    estimate=estimate,
                    decision=decision,
                    failure_reason="proactive_compact_limit_reached",
                )
                return _GovernanceStageResult(
                    pending_dispatch=self._fail_unstarted_in_transaction(
                        transaction,
                        run,
                        reason=_GOVERNANCE_FAILURE_REASON,
                        error_code="proactive_compact_limit_reached",
                        message="Run already used its proactive compaction budget",
                    ),
                    compact_accepted=None,
                )
            compact_pending = self._prepare_compact_before_dispatch(
                transaction,
                run=run,
                display_text=display_text,
                estimate=estimate,
                decision=decision,
            )
            if compact_pending is None:
                return _GovernanceStageResult(
                    pending_dispatch=None, compact_accepted=None
                )
            return _GovernanceStageResult(
                pending_dispatch=None,
                compact_accepted=None,
                compact_pending=compact_pending,
            )

        stage = self._transaction_runner.run_write(_operation)
        if stage.compact_pending is None:
            return stage
        compacted_sequence = await self._execute_proactive_compaction(
            stage.compact_pending
        )
        if compacted_sequence is None:
            return _GovernanceStageResult(
                pending_dispatch=None, compact_accepted=None
            )
        pending = stage.compact_pending
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.governance.compact_accepted session_id=%s run_id=%s "
            "compacted_event_sequence=%s",
            pending.session_id,
            pending.run_id,
            compacted_sequence,
        )
        return _GovernanceStageResult(
            pending_dispatch=None,
            compact_accepted=_GovernanceCompactAccepted(
                run_id=pending.run_id,
                session_id=pending.session_id,
                expected_status=pending.expected_status,
                compacted_event_sequence=compacted_sequence,
            ),
        )

    async def _execute_proactive_compaction(
        self, pending: _GovernanceCompactPending
    ) -> int | None:
        """在事务外执行 proactive compact，并在新事务内写入结果。

        :param pending: 已写 request fact 的 compact 摘要。
        :returns: accepted ``CONTEXT_COMPACTED`` sequence；失败或 stale 时为
            ``None``。
        """

        compactor = self._local_execution.context_compactor
        if compactor is None:
            return None
        attempts = (
            self._local_execution.context_budget_policy.max_compaction_attempts_per_operation
            if self._local_execution.context_budget_policy is not None
            else 1
        )
        result = await run_compaction_operation(
            request=pending.request,
            compactor=compactor,
            max_attempts=attempts,
        )

        def _operation(transaction: HostTransaction) -> int | None:
            run = read_run_by_id(transaction, pending.run_id)
            if (
                run is None
                or run.status != pending.expected_status
                or run.input_event_sequence != pending.expected_input_event_sequence
            ):
                if run is not None:
                    self._append_compaction_failed_event(
                        transaction,
                        run=run,
                        estimate=pending.estimate,
                        decision=pending.decision,
                        failure_reason="stale_compaction_result",
                        budget_after_attempted_compact=(
                            result.budget_after_attempted_compact
                        ),
                    )
                return None
            for rejected in result.rejected_attempts:
                self._append_compaction_attempt_rejected_event(
                    transaction,
                    run=run,
                    operation_id=pending.operation_id,
                    rejected=rejected,
                )
            if (
                result.accepted_candidate is None
                or result.quality_result is None
                or result.failure_reason is not None
            ):
                self._append_compaction_failed_event(
                    transaction,
                    run=run,
                    estimate=pending.estimate,
                    decision=pending.decision,
                    failure_reason=result.failure_reason or "compaction_failed",
                    budget_after_attempted_compact=(
                        result.budget_after_attempted_compact
                    ),
                )
                self._fail_unstarted_in_transaction(
                    transaction,
                    run,
                    reason=_GOVERNANCE_FAILURE_REASON,
                    error_code="context_compaction_failed",
                    message="Context compaction failed before dispatch",
                )
                return None
            return self._append_compacted_event(
                transaction,
                run=run,
                estimate=pending.estimate,
                decision=pending.decision,
                request=pending.request,
                candidate=result.accepted_candidate,
                quality=result.quality_result,
            )

        return self._transaction_runner.run_write(_operation)

    def _start_governed_after_compact(
        self, accepted: _GovernanceCompactAccepted
    ) -> PendingDispatchRecord | None:
        """compact catch-up 后启动同一个未启动 Run。

        :param accepted: compact accepted 摘要。
        :returns: pending dispatch 摘要；状态已变化时返回 ``None``。
        """

        def _operation(transaction: HostTransaction) -> PendingDispatchRecord | None:
            run = read_run_by_id(transaction, accepted.run_id)
            if run is None or run.status != accepted.expected_status:
                _LOGGER.debug(
                    "dispatch.governance.start_after_compact_skipped "
                    "session_id=%s run_id=%s expected_status=%s",
                    accepted.session_id,
                    accepted.run_id,
                    accepted.expected_status.value,
                )
                return None
            return self._start_governed_in_transaction(transaction, run)

        return self._transaction_runner.run_write(_operation)

    def _start_governed_in_transaction(
        self, transaction: HostTransaction, run: RunRow
    ) -> PendingDispatchRecord | None:
        """在当前事务内启动 accepted/queued Run。

        :param transaction: 当前 Host transaction。
        :param run: 待启动 Run。
        :returns: pending dispatch 摘要；CAS 失败时返回 ``None``。
        """

        result = start_governed_run_with_starting_attempt_in_transaction(
            transaction,
            self._event_log_store,
            StartGovernedRunInput(
                run_id=run.run_id,
                expected_status=run.status,
                run_started_event_id=_new_event_id("event-run-started"),
                attempt_started_event_id=_new_event_id("event-attempt-started"),
                attempt_id=_new_event_id("attempt"),
                execution_id=_new_event_id("execution"),
                dispatch_record_id=_new_event_id("dispatch"),
                occurred_at=datetime.now(UTC),
                actor=_EVENT_ACTOR,
                source=_EVENT_SOURCE,
                start_reason=(
                    RunStartReason.INITIAL
                    if run.status is RunStatus.ACCEPTED
                    else RunStartReason.QUEUE_PROMOTION
                ),
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
            ),
        )
        if result.status != StateMutationStatus.UPDATED:
            _LOGGER.debug(
                "dispatch.start_governed.cas_miss session_id=%s run_id=%s "
                "expected_status=%s",
                run.session_id,
                run.run_id,
                run.status.value,
            )
            return None
        if result.dispatch_record is None:
            return None
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.start_governed.committed session_id=%s run_id=%s "
            "attempt_id=%s execution_id=%s dispatch_record_id=%s",
            run.session_id,
            result.dispatch_record.run_id,
            result.dispatch_record.attempt_id,
            result.dispatch_record.execution_id,
            result.dispatch_record.dispatch_record_id,
        )
        return PendingDispatchRecord(
            dispatch_record_id=result.dispatch_record.dispatch_record_id,
            run_id=result.dispatch_record.run_id,
            attempt_id=result.dispatch_record.attempt_id,
            execution_id=result.dispatch_record.execution_id,
            execution_target=result.dispatch_record.execution_target,
            worker_kind=result.dispatch_record.worker_kind,
        )

    def _fail_unstarted_in_transaction(
        self,
        transaction: HostTransaction,
        run: RunRow,
        *,
        reason: str,
        error_code: str,
        message: str,
    ) -> None:
        """在当前事务内 attempt-free 失败收口 Run。

        :param transaction: 当前 Host transaction。
        :param run: 待收口 Run。
        :param reason: 失败原因。
        :param error_code: 错误码。
        :param message: 失败消息。
        :returns: ``None``。
        """

        fail_unstarted_run_in_transaction(
            transaction,
            self._event_log_store,
            FailUnstartedRunInput(
                run_id=run.run_id,
                expected_status=run.status,
                run_failed_event_id=_new_event_id(_EVENT_ID_RUN_FAILED_PREFIX),
                occurred_at=datetime.now(UTC),
                actor=_GOVERNANCE_ACTOR,
                source=_EVENT_SOURCE,
                reason=reason,
                error_code=error_code,
                message=message,
            ),
        )

    def _committed_proactive_compact_count(
        self, transaction: HostTransaction, run: RunRow
    ) -> int:
        """读取 durable EventLog 中本 Run proactive compact 请求数。

        :param transaction: 当前 Host transaction。
        :param run: 目标 Run。
        :returns: committed proactive request 数。
        """

        return self._event_log_store.count_committed_events_by_run_and_type(
            transaction,
            run_id=run.run_id,
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload_filter=EventPayloadTextEqualsFilter(
                field_name="trigger_source",
                expected_value=ContextCompactionTriggerSource.PROACTIVE.value,
                allowed_values=(
                    ContextCompactionTriggerSource.PROACTIVE.value,
                    ContextCompactionTriggerSource.REACTIVE.value,
                ),
            ),
        )

    def _prepare_compact_before_dispatch(
        self,
        transaction: HostTransaction,
        *,
        run: RunRow,
        display_text: str,
        estimate: BudgetEstimate,
        decision: ContextBudgetDecision,
    ) -> _GovernanceCompactPending | None:
        """在当前事务内写入 proactive compact request 并冻结请求。

        :param transaction: 当前 Host transaction。
        :param run: 待 compact Run。
        :param display_text: 当前输入展示文本。
        :param estimate: compact 前预算估算。
        :param decision: 触发 compact 的预算决策。
        :returns: 待事务外执行的 compact；失败路径返回 ``None``。
        """

        compactor = self._local_execution.context_compactor
        artifact_root = self._local_execution.compact_artifact_root
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.compact.start session_id=%s run_id=%s decision=%s "
            "estimated_input_tokens=%s hard_threshold_tokens=%s",
            run.session_id,
            run.run_id,
            decision.value,
            estimate.estimated_input_tokens,
            estimate.hard_threshold_tokens,
        )
        requested = self._append_compaction_requested_event(
            transaction,
            run=run,
            estimate=estimate,
            decision=decision,
        )
        if compactor is None or artifact_root is None:
            _LOGGER.error(
                "dispatch.compact.failed session_id=%s run_id=%s "
                "failure_reason=%s decision=%s compactor_present=%s "
                "artifact_root_present=%s",
                run.session_id,
                run.run_id,
                "compactor_or_artifact_store_missing",
                decision.value,
                compactor is not None,
                artifact_root is not None,
            )
            self._append_compaction_failed_event(
                transaction,
                run=run,
                estimate=estimate,
                decision=decision,
                failure_reason="compactor_or_artifact_store_missing",
            )
            self._fail_unstarted_in_transaction(
                transaction,
                run,
                reason=_GOVERNANCE_FAILURE_REASON,
                error_code="context_compactor_missing",
                message="Context compactor or artifact store is not configured",
            )
            return None
        request = CompactionRequest(
            trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            session_id=run.session_id,
            run_id=run.run_id,
            attempt_id=None,
            execution_id=None,
            input_event_refs=(run.input_event_id,),
            memory_snapshot_cursor=None,
            current_message_summary=CurrentMessageSummary(
                current_user_input_ref=run.input_event_id,
                summary_text=display_text,
                source_event_refs=(run.input_event_id,),
            ),
            tool_fact_refs=(),
            verified_fact_refs=(),
            recent_raw_turn_refs=(run.input_event_id,),
            older_raw_turn_refs=(),
            existing_episode_summary_refs=(),
            budget_before_compact=estimate,
        )
        return _GovernanceCompactPending(
            run_id=run.run_id,
            session_id=run.session_id,
            expected_status=run.status,
            expected_input_event_sequence=run.input_event_sequence,
            request=request,
            operation_id=requested.event_id,
            estimate=estimate,
            decision=decision,
        )

    def _append_compacted_event(
        self,
        transaction: HostTransaction,
        *,
        run: RunRow,
        estimate: BudgetEstimate,
        decision: ContextBudgetDecision,
        request: CompactionRequest,
        candidate: CompactionCandidate,
        quality: CompactQualityCheckResult,
    ) -> int:
        """写入 accepted compact artifact 与 ``CONTEXT_COMPACTED`` fact。

        :param transaction: 当前 Host transaction。
        :param run: 目标 Run。
        :param estimate: compact 前预算估算。
        :param decision: 触发 compact 的预算决策。
        :param request: Host compaction request。
        :param candidate: accepted compaction candidate。
        :param quality: accepted quality check 结果。
        :returns: ``CONTEXT_COMPACTED`` event sequence。
        """

        artifact_root = self._local_execution.compact_artifact_root
        if artifact_root is None:
            raise RuntimeError("compact artifact root is missing")
        artifact = CompactArtifactStore(
            LocalArtifactStore(
                artifact_root,
                create_artifact_root=(
                    self._local_execution.compact_artifact_create_parent_dirs
                ),
            )
        ).write_compact_artifact(
            transaction,
            CompactArtifactWriteRequest(
                compaction_request=request,
                accepted_candidate=candidate,
                quality_result=quality,
                policy_digest=sha256_digest_json(
                    {
                        "policy_ref": self._local_execution.context_budget_policy.policy_ref
                        if self._local_execution.context_budget_policy is not None
                        else "none"
                    }
                ),
            ),
        )
        event = self._event_log_store.append_event(
            transaction,
            EventLogAppendRequest(
                event_id=_new_event_id(_EVENT_ID_CONTEXT_COMPACTED_PREFIX),
                event_class=EventClass.CANONICAL_FACT,
                session_id=run.session_id,
                run_id=run.run_id,
                attempt_id=None,
                execution_id=None,
                event_type=CONTEXT_COMPACTED,
                occurred_at=datetime.now(UTC),
                actor=_GOVERNANCE_ACTOR,
                source=_EVENT_SOURCE,
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason={"decision": decision.value},
                payload_json=build_context_compacted_payload(
                    compact_artifact_ref=artifact.payload_descriptor.payload_ref,
                    compact_artifact_digest=artifact.artifact_ref.artifact_digest,
                    accepted_candidate=candidate,
                    quality_check_result=quality,
                ),
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
        return event.event_sequence

    def _append_compaction_requested_event(
        self,
        transaction: HostTransaction,
        *,
        run: RunRow,
        estimate: BudgetEstimate,
        decision: ContextBudgetDecision,
    ) -> EventLogRow:
        """追加 proactive ``CONTEXT_COMPACTION_REQUESTED``。

        :param transaction: 当前 Host transaction。
        :param run: 目标 Run。
        :param estimate: budget estimate。
        :param decision: budget decision。
        :returns: 已写入的 request EventLog row。
        """

        return self._event_log_store.append_event(
            transaction,
            EventLogAppendRequest(
                event_id=_new_event_id(_EVENT_ID_CONTEXT_COMPACTION_REQUESTED_PREFIX),
                event_class=EventClass.CANONICAL_FACT,
                session_id=run.session_id,
                run_id=run.run_id,
                attempt_id=None,
                execution_id=None,
                event_type=CONTEXT_COMPACTION_REQUESTED,
                occurred_at=datetime.now(UTC),
                actor=_GOVERNANCE_ACTOR,
                source=_EVENT_SOURCE,
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason={"decision": decision.value},
                payload_json=build_context_compaction_requested_payload(
                    trigger_source=ContextCompactionTriggerSource.PROACTIVE,
                    budget_reason=decision.value,
                    budget_snapshot_ref=estimate.estimator_digest,
                    input_snapshot_cursor=run.input_event_sequence,
                    estimator_digest=estimate.estimator_digest,
                    policy_ref=self._local_execution.context_budget_policy.policy_ref
                    if self._local_execution.context_budget_policy is not None
                    else "none",
                    provider_request_id=None,
                    provider_error_ref=None,
                    attempt_id=None,
                    execution_id=None,
                ),
                payload_ref=None,
                payload_digest=None,
            ),
        ).row

    def _append_compaction_failed_event(
        self,
        transaction: HostTransaction,
        *,
        run: RunRow,
        estimate: BudgetEstimate,
        decision: ContextBudgetDecision,
        failure_reason: str,
        budget_after_attempted_compact: int | None = None,
    ) -> None:
        """追加 ``CONTEXT_COMPACTION_FAILED``。

        :param transaction: 当前 Host transaction。
        :param run: 目标 Run。
        :param estimate: budget estimate。
        :param decision: budget decision。
        :param failure_reason: compact failure reason。
        :param budget_after_attempted_compact: compact 后预算；未执行时为 ``None``。
        :returns: ``None``。
        """

        self._event_log_store.append_event(
            transaction,
            EventLogAppendRequest(
                event_id=_new_event_id("event-context-compaction-failed"),
                event_class=EventClass.CANONICAL_FACT,
                session_id=run.session_id,
                run_id=run.run_id,
                attempt_id=None,
                execution_id=None,
                event_type=CONTEXT_COMPACTION_FAILED,
                occurred_at=datetime.now(UTC),
                actor=_GOVERNANCE_ACTOR,
                source=_EVENT_SOURCE,
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason={"failure_reason": failure_reason},
                payload_json=build_context_compaction_failed_payload(
                    failure_reason=failure_reason,
                    policy_decision=_COMPACT_FAILURE_POLICY_DECISION,
                    retryable=False,
                    diagnostic_refs=(estimate.estimator_digest,),
                    budget_after_attempted_compact=(
                        budget_after_attempted_compact
                    ),
                ),
                payload_ref=None,
                payload_digest=None,
            ),
        )

    def _append_compaction_attempt_rejected_event(
        self,
        transaction: HostTransaction,
        *,
        run: RunRow,
        operation_id: str,
        rejected: CompactionAttemptRejected,
    ) -> None:
        """追加 proactive ``CONTEXT_COMPACTION_ATTEMPT_REJECTED``。

        :param transaction: 当前 Host transaction。
        :param run: 目标 Run。
        :param operation_id: 对应 request fact 的 stable event id。
        :param rejected: attempt reject 摘要。
        :returns: ``None``。
        """

        self._event_log_store.append_event(
            transaction,
            EventLogAppendRequest(
                event_id=_new_event_id(
                    _EVENT_ID_CONTEXT_COMPACTION_ATTEMPT_REJECTED_PREFIX
                ),
                event_class=EventClass.CANONICAL_FACT,
                session_id=run.session_id,
                run_id=run.run_id,
                attempt_id=None,
                execution_id=None,
                event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                occurred_at=datetime.now(UTC),
                actor=_GOVERNANCE_ACTOR,
                source=_EVENT_SOURCE,
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason={"failure_category": rejected.failure_category},
                payload_json=build_context_compaction_attempt_rejected_payload(
                    operation_id=operation_id,
                    attempt_number=rejected.attempt_number,
                    failure_category=rejected.failure_category,
                    repairable=rejected.repairable,
                    runner_attempt_summary_refs=(
                        rejected.runner_attempt_summary_refs
                    ),
                    diagnostic_refs=rejected.diagnostic_refs,
                    next_policy_decision=rejected.next_policy_decision,
                    budget_after_attempted_compact=(
                        rejected.budget_after_attempted_compact
                    ),
                ),
                payload_ref=None,
                payload_digest=None,
            ),
        )

    async def drain_once(self) -> DispatchDrainResult:
        """同步处理当前队列中的 dispatch wakeup。

        :returns: 本次 drain 摘要。
        :raises RuntimeError: scheduler 已关闭时抛出。
        """

        if self._closed:
            raise RuntimeError("HostDispatchScheduler is closed")
        processed = 0
        dispatched = 0
        skipped = 0
        timed_out = 0
        while not self._queue.empty():
            record = self._queue.get_nowait()
            processed += 1
            outcome = await self._dispatch_one(record)
            if outcome == "dispatched":
                dispatched += 1
            elif outcome == "timed_out":
                timed_out += 1
            else:
                skipped += 1
        return DispatchDrainResult(
            processed=processed,
            dispatched=dispatched,
            skipped=skipped,
            timed_out=timed_out,
        )

    async def close(self) -> None:
        """关闭 scheduler 并 best-effort 收尾 active workers。

        :returns: ``None``。
        """

        if self._closed:
            return
        self._closed = True
        self._best_effort_mark_host_instance_stopping("scheduler_close")
        _LOGGER.info(
            "dispatch.scheduler.close_start host_handle_id=%s active_tasks=%s "
            "active_handles=%s",
            self._host_handle_id,
            len(self._active_tasks),
            len(self._active_handles),
        )
        heartbeat_task = self._heartbeat_task
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            await _suppress_task_cancel(heartbeat_task)
        task = self._drain_task
        if task is not None:
            task.cancel()
            await _suppress_task_cancel(task)
        promotion_task = self._promotion_drain_task
        if promotion_task is not None:
            promotion_task.cancel()
            await _suppress_task_cancel(promotion_task)
        for handle in tuple(self._active_handles):
            _safe_cancel_worker_handle(handle, "scheduler_close")
        for active_task in tuple(self._active_tasks):
            active_task.cancel()
            await _suppress_task_cancel(active_task)
        await self._lane_controller.close(reason="scheduler_close")
        self._duplicate_governance_registry.clear_all()
        self._best_effort_mark_host_instance_stopped("scheduler_close")
        _LOGGER.info(
            "dispatch.scheduler.close_done host_handle_id=%s",
            self._host_handle_id,
        )

    def _start_host_instance_heartbeat(self) -> None:
        """启动当前 Host instance heartbeat 后台任务。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(
                self._host_instance_heartbeat_loop()
            )

    async def _host_instance_heartbeat_loop(self) -> None:
        """后台刷新当前 Host instance heartbeat。

        :returns: ``None``。
        :raises asyncio.CancelledError: scheduler close 时透传取消。
        """

        try:
            while not self._closed:
                await asyncio.sleep(_HOST_INSTANCE_HEARTBEAT_INTERVAL_SECONDS)
                if self._closed:
                    break
                try:
                    self._refresh_current_host_instance_heartbeat()
                except HostTransactionRetryExhaustedError as exc:
                    _LOGGER.warning(
                        "dispatch.host_instance_heartbeat.refresh_retryable "
                        "host_handle_id=%s host_instance_id=%s error_type=%s "
                        "attempts=%s",
                        self._host_handle_id,
                        self._host_instance_identity.host_instance_id,
                        exc.__class__.__name__,
                        exc.attempts,
                        exc_info=True,
                    )
                except Exception as exc:
                    _LOGGER.error(
                        "dispatch.host_instance_heartbeat.fatal_exit "
                        "host_handle_id=%s host_instance_id=%s error_type=%s",
                        self._host_handle_id,
                        self._host_instance_identity.host_instance_id,
                        exc.__class__.__name__,
                        exc_info=True,
                    )
                    self._best_effort_mark_host_instance_stopping(
                        "heartbeat_fatal_exit"
                    )
                    return
        except asyncio.CancelledError:
            _LOGGER.debug(
                "dispatch.host_instance_heartbeat.cancelled host_handle_id=%s "
                "host_instance_id=%s",
                self._host_handle_id,
                self._host_instance_identity.host_instance_id,
            )
            raise

    def _refresh_current_host_instance_heartbeat(self) -> None:
        """刷新当前 scheduler 自己的 Host instance heartbeat。

        :returns: ``None``。
        :raises HostTransactionRetryExhaustedError: heartbeat write 重试耗尽时抛出。
        :raises Exception: durable write 失败时透传。
        """

        def _operation(transaction: HostTransaction) -> None:
            heartbeat_current_instance(transaction, self._host_instance_identity)

        self._transaction_runner.run_write(_operation)

    def _best_effort_mark_host_instance_stopping(self, reason: str) -> None:
        """best-effort 将当前 scheduler 自己的 instance 标记为 stopping。

        :param reason: 诊断原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        def _operation(transaction: HostTransaction) -> None:
            mark_current_instance_stopping(transaction, self._host_instance_identity)

        try:
            self._transaction_runner.run_write(_operation)
        except Exception as exc:
            _LOGGER.warning(
                "dispatch.host_instance.mark_stopping_failed host_handle_id=%s "
                "host_instance_id=%s reason=%s error_type=%s",
                self._host_handle_id,
                self._host_instance_identity.host_instance_id,
                reason,
                exc.__class__.__name__,
                exc_info=True,
            )

    def _best_effort_mark_host_instance_stopped(self, reason: str) -> None:
        """best-effort 将当前 scheduler 自己的 instance 标记为 stopped。

        :param reason: 诊断原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        def _operation(transaction: HostTransaction) -> None:
            mark_current_instance_stopped(transaction, self._host_instance_identity)

        try:
            self._transaction_runner.run_write(_operation)
        except Exception as exc:
            _LOGGER.warning(
                "dispatch.host_instance.mark_stopped_failed host_handle_id=%s "
                "host_instance_id=%s reason=%s error_type=%s",
                self._host_handle_id,
                self._host_instance_identity.host_instance_id,
                reason,
                exc.__class__.__name__,
                exc_info=True,
            )

    async def _drain_loop(self) -> None:
        """后台 drain 队列。

        :returns: ``None``。
        :raises asyncio.CancelledError: scheduler close 时透传取消。
        """

        idle_sleep_logged = False
        try:
            while not self._closed:
                try:
                    if self._queue.empty():
                        if not idle_sleep_logged:
                            _LOGGER.debug(
                                _LOG_DRAIN_LOOP_IDLE,
                                self._host_handle_id,
                                (
                                    self._local_execution
                                    .dispatch_poll_interval_seconds
                                ),
                            )
                            idle_sleep_logged = True
                        await asyncio.sleep(
                            self._local_execution.dispatch_poll_interval_seconds
                        )
                    else:
                        idle_sleep_logged = False
                    result = await self.drain_once()
                    if result.processed > 0:
                        idle_sleep_logged = False
                except Exception as exc:
                    _LOGGER.warning(
                        _LOG_DRAIN_LOOP_UNEXPECTED_EXCEPTION,
                        self._host_handle_id,
                        exc.__class__.__name__,
                        exc_info=True,
                    )
                    if not self._closed:
                        await asyncio.sleep(
                            self._local_execution.dispatch_poll_interval_seconds
                        )
            _LOGGER.debug(_LOG_DRAIN_LOOP_CLOSE_EXIT, self._host_handle_id)
        except asyncio.CancelledError:
            _LOGGER.debug(
                _LOG_DRAIN_LOOP_CANCELLED_FOR_CLOSE
                if self._closed
                else _LOG_DRAIN_LOOP_CANCELLED_EXTERNALLY,
                self._host_handle_id,
            )
            raise

    async def _promotion_drain_loop(self) -> None:
        """后台处理 queued Run promotion wakeup。

        :returns: ``None``。
        :raises asyncio.CancelledError: scheduler close 时透传取消。
        """

        try:
            while not self._closed:
                session_id = await self._promotion_queue.get()
                try:
                    await self.run_queue_promotion(session_id)
                except RuntimeError as exc:
                    if self._closed:
                        _LOGGER.debug(
                            "dispatch.queue_promotion.cancelled_for_close "
                            "host_handle_id=%s session_id=%s",
                            self._host_handle_id,
                            session_id,
                        )
                    else:
                        _LOGGER.warning(
                            "dispatch.queue_promotion.runtime_error "
                            "host_handle_id=%s session_id=%s error_type=%s",
                            self._host_handle_id,
                            session_id,
                            exc.__class__.__name__,
                            exc_info=True,
                        )
                except Exception as exc:
                    _LOGGER.warning(
                        "dispatch.queue_promotion.unexpected_exception "
                        "host_handle_id=%s session_id=%s error_type=%s",
                        self._host_handle_id,
                        session_id,
                        exc.__class__.__name__,
                        exc_info=True,
                    )
        except asyncio.CancelledError:
            _LOGGER.debug(
                "dispatch.queue_promotion.cancelled host_handle_id=%s",
                self._host_handle_id,
            )
            raise

    async def _dispatch_one(self, record: PendingDispatchRecord) -> str:
        """处理一个 dispatch wakeup。

        :param record: pending dispatch 摘要。
        :returns: ``dispatched``、``skipped`` 或 ``timed_out``。
        """

        wait_row = self._mark_waiting_for_lane(record)
        if wait_row is None:
            return "skipped"
        acquire = await self._lane_controller.acquire(
            self._local_execution.lane_name,
            timeout_seconds=self._local_execution.lane_default_timeout_seconds,
        )
        if isinstance(acquire, LaneAcquireTimedOut):
            _LOGGER.warning(
                "dispatch.lane_acquire.timed_out run_id=%s attempt_id=%s "
                "execution_id=%s dispatch_record_id=%s lane_name=%s "
                "timeout_seconds=%s",
                record.run_id,
                record.attempt_id,
                record.execution_id,
                record.dispatch_record_id,
                self._local_execution.lane_name,
                self._local_execution.lane_default_timeout_seconds,
            )
            self._safe_closeout_worker_startup_timeout(
                record, reason=_WORKER_STARTUP_TIMEOUT_REASON
            )
            return "timed_out"
        if isinstance(acquire, LaneAcquireCancelled):
            if self._closed:
                return "skipped"
            _LOGGER.warning(
                "dispatch.lane_acquire.cancelled run_id=%s attempt_id=%s "
                "execution_id=%s dispatch_record_id=%s lane_name=%s",
                record.run_id,
                record.attempt_id,
                record.execution_id,
                record.dispatch_record_id,
                self._local_execution.lane_name,
            )
            self._safe_closeout_worker_startup_timeout(
                record, reason=_WORKER_STARTUP_TIMEOUT_REASON
            )
            return "timed_out"
        if not isinstance(acquire, LaneAcquired):
            return "skipped"
        token = acquire.token
        try:
            dispatching_row = self._mark_dispatching_after_recheck(record, token)
            if dispatching_row is None:
                await _safe_release_lane_token(token)
                return "skipped"
            await asyncio.sleep(0)
            if not self._dispatch_record_still_pre_accept(dispatching_row):
                await _safe_release_lane_token(token)
                return "skipped"
            return await self._start_worker(record, dispatching_row, token)
        except asyncio.CancelledError:
            await _safe_release_lane_token(token)
            raise
        except HostTransactionRetryExhaustedError as exc:
            await _safe_release_lane_token(token)
            _LOGGER.warning(
                "dispatch durable retry exhausted; requeueing run_id=%s "
                "attempt_id=%s dispatch_record_id=%s error_type=%s",
                record.run_id,
                record.attempt_id,
                record.dispatch_record_id,
                exc.__class__.__name__,
            )
            self._rewake_dispatch_after_current_drain(record)
            return "skipped"
        except Exception as exc:
            try:
                self._safe_closeout_worker_startup_timeout(
                    record,
                    reason=_WORKER_STARTUP_TIMEOUT_REASON,
                    original_error=exc,
                )
            finally:
                await _safe_release_lane_token(token)
            return "timed_out"

    def _rewake_dispatch_after_current_drain(
        self, record: PendingDispatchRecord
    ) -> None:
        """在当前 drain 轮次之后重新投递 dispatch wakeup。

        :param record: 需要重试的 pending dispatch 摘要。
        :returns: ``None``。
        """

        asyncio.get_running_loop().call_soon(self._queue.put_nowait, record)

    def _mark_waiting_for_lane(
        self, record: PendingDispatchRecord
    ) -> DispatchRecordRow | None:
        """把 pending dispatch 标记为 waiting_for_lane。

        :param record: pending dispatch 摘要。
        :returns: 可继续 dispatch 的 dispatch row；不可继续时为 ``None``。
        """

        def _operation(transaction: HostTransaction) -> DispatchRecordRow | None:
            latest = read_dispatch_record_by_id(
                transaction, record.dispatch_record_id
            )
            if latest is None:
                return None
            if latest.status == DispatchRecordStatus.WAITING_FOR_LANE:
                return latest
            result = mark_dispatch_waiting_for_lane_row(
                transaction,
                attempt_id=record.attempt_id,
                owner_host_instance_id=self._host_handle_id,
                lane_name=self._local_execution.lane_name,
                waiting_for_lane_at=format_utc_timestamp(datetime.now(UTC)),
            )
            if result.status == StateMutationStatus.UPDATED:
                return result.row
            return None

        row = self._transaction_runner.run_write(_operation)
        if row is None:
            _LOGGER.debug(
                "dispatch.waiting_for_lane.skipped run_id=%s attempt_id=%s "
                "execution_id=%s dispatch_record_id=%s",
                record.run_id,
                record.attempt_id,
                record.execution_id,
                record.dispatch_record_id,
            )
            return None
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.status.waiting_for_lane run_id=%s attempt_id=%s "
            "execution_id=%s dispatch_record_id=%s dispatch_status=%s",
            record.run_id,
            record.attempt_id,
            record.execution_id,
            record.dispatch_record_id,
            row.status.value,
        )
        return row

    def _mark_dispatching_after_recheck(
        self, record: PendingDispatchRecord, token: LaneClaimToken
    ) -> DispatchRecordRow | None:
        """lane acquired 后做 durable recheck 并标记 dispatching。

        :param record: pending dispatch 摘要。
        :param token: runtime lane token。
        :returns: dispatching row；前置不满足时为 ``None``。
        """

        def _operation(transaction: HostTransaction) -> DispatchRecordRow | None:
            run = read_run_by_id(transaction, record.run_id)
            attempt = read_attempt_by_id(transaction, record.attempt_id)
            dispatch_record = read_dispatch_record_by_id(
                transaction, record.dispatch_record_id
            )
            if not _is_dispatchable_recheck(
                run=run,
                attempt=attempt,
                dispatch_record=dispatch_record,
                record=record,
            ):
                return None
            result = mark_dispatching_after_lane_row(
                transaction,
                attempt_id=record.attempt_id,
                owner_host_instance_id=self._host_handle_id,
                lane_name=token.name,
                lane_claim_id=token.claim_id,
                lane_owner_id=token.owner.owner_id,
                lane_acquired_at=format_utc_timestamp(datetime.now(UTC)),
                dispatching_at=format_utc_timestamp(datetime.now(UTC)),
            )
            if result.status != StateMutationStatus.UPDATED:
                return None
            return result.row

        row = self._transaction_runner.run_write(_operation)
        if row is None:
            _LOGGER.debug(
                "dispatch.dispatching.skipped run_id=%s attempt_id=%s "
                "execution_id=%s dispatch_record_id=%s lane_name=%s "
                "lane_claim_id=%s",
                record.run_id,
                record.attempt_id,
                record.execution_id,
                record.dispatch_record_id,
                token.name,
                token.claim_id,
            )
            return None
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.status.dispatching run_id=%s attempt_id=%s "
            "execution_id=%s dispatch_record_id=%s dispatch_status=%s "
            "lane_name=%s lane_claim_id=%s",
            record.run_id,
            record.attempt_id,
            record.execution_id,
            record.dispatch_record_id,
            row.status.value,
            token.name,
            token.claim_id,
        )
        return row

    def _dispatch_record_still_pre_accept(
        self, dispatch_record: DispatchRecordRow
    ) -> bool:
        """确认 dispatching row 仍处于 worker accept 前。

        :param dispatch_record: dispatching row。
        :returns: 仍可调用 worker 时返回 ``True``。
        """

        def _operation(transaction: HostTransaction) -> bool:
            latest = read_dispatch_record_by_id(
                transaction, dispatch_record.dispatch_record_id
            )
            return (
                latest is not None
                and latest.status == DispatchRecordStatus.DISPATCHING
                and latest.worker_accept_event_id is None
                and latest.cancelled_event_id is None
            )

        return self._transaction_runner.run_read(_operation)

    async def _start_worker(
        self,
        record: PendingDispatchRecord,
        dispatch_record: DispatchRecordRow,
        token: LaneClaimToken,
    ) -> str:
        """构造 Engine request，调用 worker accept，并启动事件消费任务。

        :param record: pending dispatch 摘要。
        :param dispatch_record: dispatching row。
        :param token: runtime lane token。
        :returns: ``dispatched``、``skipped`` 或 ``timed_out``。
        """

        try:
            cancellation_token = _HostCancellationToken()
            effective_decision = self._effective_dispatch_decision(record)
            snapshot = self._snapshot_from_dispatch(
                record,
                cancellation_token,
                policy_snapshot_ref=effective_decision.policy_snapshot.policy_snapshot_ref,
            )
            self._catch_up_memory_projection_before_worker(record)
            request = self._run_input_builder_for_dispatch(
                snapshot=snapshot,
                policy_snapshot=effective_decision.policy_snapshot,
                selected_business_tool_names=(
                    effective_decision.selected_business_tool_names
                ),
            ).build(snapshot)
            worker = self._local_execution.worker_factory.create_worker(snapshot)
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "dispatch.worker_accept.start session_id=%s run_id=%s "
                "attempt_id=%s execution_id=%s dispatch_record_id=%s "
                "policy_snapshot_ref=%s",
                snapshot.session_id,
                record.run_id,
                record.attempt_id,
                record.execution_id,
                record.dispatch_record_id,
                effective_decision.policy_snapshot.policy_snapshot_ref,
            )
            handle = await asyncio.wait_for(
                worker.accept(snapshot, request),
                timeout=self._local_execution.worker_startup_timeout_seconds,
            )
        except MemoryProjectionRepairRequired as exc:
            try:
                _LOGGER.warning(
                    "dispatch memory projection repair required; closing run "
                    "run_id=%s attempt_id=%s execution_id=%s reason=%s",
                    record.run_id,
                    record.attempt_id,
                    record.execution_id,
                    exc.repair_request.reason.value,
                )
                self._safe_closeout_worker_startup_timeout(
                    record,
                    reason=_MEMORY_PROJECTION_REPAIR_REQUIRED_REASON,
                    original_error=exc,
                )
            finally:
                await _safe_release_lane_token(token)
            return "timed_out"
        except TimeoutError as exc:
            try:
                _LOGGER.warning(
                    "dispatch.worker_accept.timed_out run_id=%s attempt_id=%s "
                    "execution_id=%s dispatch_record_id=%s timeout_seconds=%s",
                    record.run_id,
                    record.attempt_id,
                    record.execution_id,
                    record.dispatch_record_id,
                    self._local_execution.worker_startup_timeout_seconds,
                )
                self._safe_closeout_worker_startup_timeout(
                    record,
                    reason=_WORKER_STARTUP_TIMEOUT_REASON,
                    original_error=exc,
                )
            finally:
                await _safe_release_lane_token(token)
            return "timed_out"
        except Exception as exc:
            try:
                _LOGGER.error(
                    "dispatch.worker_accept.failed run_id=%s attempt_id=%s "
                    "execution_id=%s dispatch_record_id=%s error_type=%s",
                    record.run_id,
                    record.attempt_id,
                    record.execution_id,
                    record.dispatch_record_id,
                    exc.__class__.__name__,
                    exc_info=True,
                )
                self._safe_closeout_worker_startup_timeout(
                    record,
                    reason=_WORKER_STARTUP_TIMEOUT_REASON,
                    original_error=exc,
                )
            finally:
                await _safe_release_lane_token(token)
            return "timed_out"
        if not self._accept_worker_running(
            record=record,
            dispatch_record=dispatch_record,
            token=token,
            handle=handle,
        ):
            await _safe_close_worker_handle(handle)
            await _safe_release_lane_token(token)
            return "skipped"
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.worker_accept.committed run_id=%s attempt_id=%s "
            "execution_id=%s dispatch_record_id=%s",
            record.run_id,
            record.attempt_id,
            record.execution_id,
            record.dispatch_record_id,
        )
        self._active_registry.register(
            run_id=record.run_id,
            attempt_id=record.attempt_id,
            execution_id=record.execution_id,
            handle=handle,
            cancellation_token=cancellation_token,
        )
        task = asyncio.create_task(
            self._consume_worker_events(
                record=record,
                handle=handle,
                token=token,
                cancellation_token=cancellation_token,
            )
        )
        self._active_handles.add(handle)
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)
        return "dispatched"

    def _run_input_builder_for_dispatch(
        self,
        *,
        snapshot: AttemptDispatchSnapshot,
        policy_snapshot: PolicySnapshot,
        selected_business_tool_names: frozenset[str] | None,
    ) -> RunInputBuilder:
        """按本地执行配置构造当前 dispatch 使用的 RunInputBuilder。

        :param snapshot: 当前 Attempt dispatch snapshot。
        :param policy_snapshot: 本地执行 policy snapshot。
        :returns: no-tool 或 tool-enabled RunInputBuilder。
        """

        tooling_options = self._local_execution.tooling_options
        memory_provider = DurableMemorySnapshotProvider(
            self._transaction_runner,
            self._local_execution.memory_projection_policy,
        )
        compact_provider = DurableCompactArtifactProvider(self._transaction_runner)
        if (
            tooling_options is None
            or not policy_snapshot.agent_policy.allow_tool_calls
        ):
            return create_no_tool_run_input_builder(
                transaction_runner=self._transaction_runner,
                policy_snapshot=policy_snapshot,
                memory_snapshot_provider=memory_provider,
                compact_artifact_provider=compact_provider,
                tool_execution_mode=(
                    ToolExecutionMode.NO_TOOL_REPLAY
                    if self._is_replay_run(snapshot.run_id)
                    else ToolExecutionMode.NO_TOOL_DISABLED
                ),
            )
        tool_runtime = DefaultToolRuntimeFactory(
            EffectiveToolBundleBuilder()
        ).create_tool_runtime(
            ToolRuntimeBuildRequest(
                effective_bundle_request=EffectiveToolBundleBuildRequest(
                    business_tool_bundle=tooling_options.business_tool_bundle,
                    source_refs=tooling_options.source_refs,
                    framework_tool_policy=tooling_options.framework_tool_policy,
                    policy_snapshot_digest=_policy_snapshot_digest(
                        policy_snapshot
                    ),
                    selected_business_tool_names=selected_business_tool_names,
                    enable_truncation_manager=(
                        self._local_execution.enable_truncation_manager
                    ),
                ),
                execution_scope=ToolRuntimeExecutionScope(
                    session_id=snapshot.session_id,
                    run_id=snapshot.run_id,
                    attempt_id=snapshot.attempt_id,
                    execution_id=snapshot.execution_id,
                    allow_tool_calls=policy_snapshot.agent_policy.allow_tool_calls,
                ),
                accept_port=DefaultHostToolFactAcceptPort(
                    transaction_runner=self._transaction_runner,
                    event_log_store=self._event_log_store,
                    projection_catchup_port=self._projection_catchup_port,
                ),
                awaiting_accept_port=DefaultHostToolAwaitingAcceptPort(
                    transaction_runner=self._transaction_runner,
                    event_log_store=self._event_log_store,
                ),
                wait_adapter_registry=tooling_options.wait_adapter_registry,
                duplicate_governance_registry=self._duplicate_governance_registry,
            )
        )
        return create_tool_enabled_run_input_builder(
            transaction_runner=self._transaction_runner,
            policy_snapshot=policy_snapshot,
            tool_runtime_handle=tool_runtime,
            memory_snapshot_provider=memory_provider,
            compact_artifact_provider=compact_provider,
        )

    def _is_replay_run(self, run_id: str) -> bool:
        """判断当前 Run 是否是 replay 关联 Run。

        :param run_id: 目标 Run id。
        :returns: Run source relation 为 replay 时返回 ``True``。
        :raises RuntimeError: durable Run 缺失时抛出。
        """

        return self._transaction_runner.run_read(_IsReplayRunOperation(run_id=run_id))

    def _catch_up_memory_projection_before_worker(
        self, record: PendingDispatchRecord
    ) -> None:
        """在构造 Engine request 前追平 conversation memory projection。

        :param record: pending dispatch 摘要。
        :returns: ``None``。
        :raises HostDurableError: projection runner 或 durable 操作失败时抛出。
        """

        catch_up_conversation_memory_projection(
            self._transaction_runner,
            policy=self._local_execution.memory_projection_policy,
            batch_size=(
                self._local_execution.memory_projection_catchup_batch_size
            ),
            max_event_sequence=(
                self._required_memory_event_sequence_for_dispatch(record)
            ),
        )

    def _required_memory_event_sequence_for_dispatch(
        self, record: PendingDispatchRecord
    ) -> int:
        """读取当前 dispatch 允许 memory projection 覆盖的最大 EventLog cursor。

        :param record: pending dispatch 摘要。
        :returns: 当前 Attempt started event 之前的 EventLog sequence。
        :raises RuntimeError: Attempt 缺失或 started cursor 非法时抛出。
        """

        def _operation(transaction: HostTransaction) -> int:
            attempt = read_attempt_by_id(transaction, record.attempt_id)
            if attempt is None:
                raise RuntimeError("dispatch Attempt is missing")
            required_event_sequence = attempt.started_event_sequence - 1
            if required_event_sequence < 0:
                raise RuntimeError("dispatch memory cursor is invalid")
            return required_event_sequence

        return self._transaction_runner.run_read(_operation)

    def _effective_dispatch_decision(
        self, record: PendingDispatchRecord
    ) -> _EffectiveDispatchDecision:
        """读取当前 Run 在 admission 冻结的 dispatch 决策。

        :param record: pending dispatch 摘要。
        :returns: effective dispatch 冻结决策。
        """

        def _operation(transaction: HostTransaction) -> _EffectiveDispatchDecision:
            run = read_run_by_id(transaction, record.run_id)
            if run is None:
                raise RuntimeError("dispatch Run is missing")
            event = self._event_log_store.read_event_by_id(
                transaction, run.input_event_id
            )
            if event is None:
                raise RuntimeError("dispatch input event is missing")
            payload = event_payload_object(
                transaction, event, payload_label="USER_INPUT_ACCEPTED"
            )
            return _effective_dispatch_decision_from_payload(
                payload,
                fallback_policy_snapshot=self._local_policy_snapshot(),
            )

        return self._transaction_runner.run_read(_operation)

    def _local_policy_snapshot(self) -> PolicySnapshot:
        """构造本地 dispatch 使用的 fallback policy snapshot。

        :returns: 本地执行 fallback policy snapshot。
        """

        return PolicySnapshot(
            runner_spec=self._local_execution.runner_spec,
            runner_options=self._local_execution.runner_options,
            agent_policy=self._local_execution.agent_policy,
            policy_snapshot_ref=_LOCAL_POLICY_SNAPSHOT_REF,
        )

    def _snapshot_from_dispatch(
        self,
        record: PendingDispatchRecord,
        cancellation_token: _HostCancellationToken,
        *,
        policy_snapshot_ref: str,
    ) -> AttemptDispatchSnapshot:
        """从 durable dispatch row 构造 RunInputBuilder snapshot。

        :param record: pending dispatch 摘要。
        :param cancellation_token: Host 注入 Engine 的取消 token。
        :param policy_snapshot_ref: admission 冻结的 policy snapshot ref。
        :returns: Attempt dispatch snapshot。
        """

        token: CancellationToken = cancellation_token
        return AttemptDispatchSnapshot(
            session_id=self._read_run_session_id(record.run_id),
            run_id=record.run_id,
            attempt_id=record.attempt_id,
            execution_id=record.execution_id,
            dispatch_record_id=record.dispatch_record_id,
            execution_target=record.execution_target,
            policy_snapshot_ref=policy_snapshot_ref,
            cancellation_token=token,
        )

    def _read_run_session_id(self, run_id: str) -> str:
        """读取 Run 所属 Session id。

        :param run_id: Run id。
        :returns: Session id。
        :raises RuntimeError: Run 缺失时抛出。
        """

        def _operation(transaction: HostTransaction) -> str:
            run = read_run_by_id(transaction, run_id)
            if run is None:
                raise RuntimeError("dispatch Run is missing")
            return run.session_id

        return self._transaction_runner.run_read(_operation)

    def _accept_worker_running(
        self,
        *,
        record: PendingDispatchRecord,
        dispatch_record: DispatchRecordRow,
        token: LaneClaimToken,
        handle: LocalWorkerHandle,
    ) -> bool:
        """worker accept 后追加 ``ATTEMPT_RUNNING`` 并推进 Attempt。

        :param record: pending dispatch 摘要。
        :param dispatch_record: dispatching row。
        :param token: runtime lane token。
        :param handle: accepted worker handle。
        :returns: durable transition 成功时返回 ``True``。
        """

        accepted_at = datetime.now(UTC)
        accepted_at_text = format_utc_timestamp(accepted_at)

        def _operation(transaction: HostTransaction) -> bool:
            run = read_run_by_id(transaction, record.run_id)
            attempt = read_attempt_by_id(transaction, record.attempt_id)
            latest_dispatch = read_dispatch_record_by_attempt_id(
                transaction, record.attempt_id
            )
            if not _is_worker_acceptable(
                run=run,
                attempt=attempt,
                dispatch_record=latest_dispatch,
                record=record,
                original_dispatch_record=dispatch_record,
            ):
                return False
            if run is None or attempt is None or latest_dispatch is None:
                return False
            event = self._event_log_store.append_event(
                transaction,
                _attempt_running_event_request(
                    event_id=_new_event_id(_EVENT_ID_ATTEMPT_RUNNING_PREFIX),
                    occurred_at=accepted_at,
                    accepted_at_text=accepted_at_text,
                    run=run,
                    attempt=attempt,
                    dispatch_record=latest_dispatch,
                    local_worker_id=handle.local_worker_id,
                    lane_name=token.name,
                    lane_claim_id=token.claim_id,
                ),
            ).row
            attempt_result = mark_attempt_running_row(
                transaction,
                attempt_id=record.attempt_id,
                updated_at=accepted_at_text,
            )
            dispatch_result = mark_dispatch_worker_accepted_row(
                transaction,
                attempt_id=record.attempt_id,
                worker_accept_event_id=event.event_id,
                worker_accept_event_sequence=event.event_sequence,
                worker_accepted_at=accepted_at_text,
            )
            return (
                attempt_result.status == StateMutationStatus.UPDATED
                and dispatch_result.status == StateMutationStatus.UPDATED
            )

        accepted = self._transaction_runner.run_write(_operation)
        if not accepted:
            _LOGGER.debug(
                "dispatch.worker_accept.cas_miss run_id=%s attempt_id=%s "
                "execution_id=%s dispatch_record_id=%s",
                record.run_id,
                record.attempt_id,
                record.execution_id,
                dispatch_record.dispatch_record_id,
            )
        return accepted

    def _closeout_worker_startup_timeout(
        self, record: PendingDispatchRecord, *, reason: str
    ) -> None:
        """worker accept timeout 后关闭 STARTING Attempt。

        :param record: pending dispatch 摘要。
        :param reason: 写入 terminal closeout 的失败原因。
        :returns: ``None``。
        """

        def _operation(transaction: HostTransaction) -> None:
            attempt_event_id = _new_event_id(_EVENT_ID_ATTEMPT_FAILED_PREFIX)
            result = terminal_closeout_in_transaction(
                transaction,
                self._event_log_store,
                TerminalCloseoutInput(
                    run_id=record.run_id,
                    attempt_id=record.attempt_id,
                    attempt_terminal_event_id=attempt_event_id,
                    run_terminal_event_id=_new_event_id(_EVENT_ID_RUN_FAILED_PREFIX),
                    attempt_terminal_status=AttemptStatus.FAILED,
                    run_terminal_status=RunStatus.FAILED,
                    occurred_at=datetime.now(UTC),
                    actor=_EVENT_ACTOR,
                    source=_EVENT_SOURCE,
                    reason=reason,
                    terminal_summary_ref=None,
                    terminal_summary_digest=None,
                ),
            )
            if result.status != StateMutationStatus.UPDATED:
                return
            event = self._event_log_store.read_event_by_id(
                transaction,
                attempt_event_id,
            )
            if event is None:
                return
            cancel_starting_dispatch_record_row(
                transaction,
                attempt_id=record.attempt_id,
                cancelled_event_id=event.event_id,
                cancelled_event_sequence=event.event_sequence,
                cancelled_at=format_utc_timestamp(datetime.now(UTC)),
            )

        self._transaction_runner.run_write(_operation)
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.worker_startup.closeout_committed run_id=%s "
            "attempt_id=%s execution_id=%s reason=%s",
            record.run_id,
            record.attempt_id,
            record.execution_id,
            reason,
        )
        self._duplicate_governance_registry.clear_run(record.run_id)

    def _safe_closeout_worker_startup_timeout(
        self,
        record: PendingDispatchRecord,
        *,
        reason: str,
        original_error: BaseException | None = None,
    ) -> None:
        """best-effort 关闭 worker startup 失败路径。

        :param record: pending dispatch 摘要。
        :param reason: 写入 terminal closeout 的失败原因。
        :param original_error: 触发 startup failure 的原始异常；无原始异常时
            为 ``None``。
        :returns: ``None``。
        """

        try:
            self._closeout_worker_startup_timeout(record, reason=reason)
        except Exception as exc:
            original_error_type = (
                original_error.__class__.__name__
                if original_error is not None
                else "None"
            )
            _LOGGER.warning(
                "worker startup closeout failed; continuing run_id=%s "
                "attempt_id=%s execution_id=%s error_type=%s "
                "original_error_type=%s",
                record.run_id,
                record.attempt_id,
                record.execution_id,
                exc.__class__.__name__,
                original_error_type,
                exc_info=True,
            )

    async def _consume_worker_events(
        self,
        *,
        record: PendingDispatchRecord,
        handle: LocalWorkerHandle,
        token: LaneClaimToken,
        cancellation_token: _HostCancellationToken,
    ) -> None:
        """消费 worker EngineEvent stream 并在结束时释放 lane。

        :param record: pending dispatch 摘要。
        :param handle: worker handle。
        :param token: runtime lane token。
        :param cancellation_token: Host 注入 Engine 的取消 token。
        :returns: ``None``。
        """

        run_terminal_closed = False
        local_worker_id: str | None = None
        try:
            envelope = LocalEngineEnvelope(
                session_id=self._read_run_session_id(record.run_id),
                run_id=record.run_id,
                attempt_id=record.attempt_id,
                execution_id=record.execution_id,
                dispatch_record_id=record.dispatch_record_id,
                worker_kind=record.worker_kind,
                execution_target=record.execution_target,
                local_worker_id=handle.local_worker_id,
                cancellation_token=cancellation_token,
            )
            local_worker_id = envelope.local_worker_id
            ingestor = EngineEventIngestor(
                transaction_runner=self._transaction_runner,
                wakeup_port=self,
                context_budget_policy=self._local_execution.context_budget_policy,
                context_compactor=self._local_execution.context_compactor,
                compact_artifact_root=self._local_execution.compact_artifact_root,
                compact_artifact_create_parent_dirs=(
                    self._local_execution.compact_artifact_create_parent_dirs
                ),
                memory_projection_policy=(
                    self._local_execution.memory_projection_policy
                ),
                memory_projection_catchup_batch_size=(
                    self._local_execution.memory_projection_catchup_batch_size
                ),
            )
            worker_event_index = 0
            terminal_seen = False
            last_accepted_event_id: str | None = None
            events = handle.events()
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "dispatch.worker_events.consume_start run_id=%s attempt_id=%s "
                "execution_id=%s dispatch_record_id=%s local_worker_id=%s",
                record.run_id,
                record.attempt_id,
                record.execution_id,
                record.dispatch_record_id,
                local_worker_id,
            )
            while True:
                try:
                    event = await anext(events)
                except StopAsyncIteration:
                    if not terminal_seen:
                        if (
                            cancellation_token.is_cancelled()
                            and not self._closed
                        ):
                            result = ingestor.ingest(
                                _cancelled_eof_candidate(
                                    envelope=envelope,
                                    worker_event_index=worker_event_index + 1,
                                    observed_at=datetime.now(UTC),
                                    cancellation_token=cancellation_token,
                                )
                            )
                            run_terminal_closed = _ingest_closed_run(result)
                        if not run_terminal_closed:
                            _LOGGER.critical(
                                "dispatch.worker_events.clean_eof_without_terminal "
                                "run_id=%s attempt_id=%s execution_id=%s "
                                "dispatch_record_id=%s local_worker_id=%s "
                                "last_observed_worker_event_index=%s",
                                record.run_id,
                                record.attempt_id,
                                record.execution_id,
                                record.dispatch_record_id,
                                local_worker_id,
                                worker_event_index,
                            )
                            result = ingestor.close_clean_eof(
                                envelope,
                                observed_at=datetime.now(UTC),
                                last_observed_worker_event_index=worker_event_index,
                            )
                            run_terminal_closed = _ingest_closed_run(result)
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    _LOGGER.error(
                        "dispatch.worker_events.stream_error run_id=%s "
                        "attempt_id=%s execution_id=%s dispatch_record_id=%s "
                        "local_worker_id=%s error_type=%s",
                        record.run_id,
                        record.attempt_id,
                        record.execution_id,
                        record.dispatch_record_id,
                        local_worker_id,
                        exc.__class__.__name__,
                        exc_info=True,
                    )
                    result = ingestor.close_worker_lost(
                        envelope,
                        observed_at=datetime.now(UTC),
                        worker_lifecycle_signal="worker_stream_error",
                        stream_error_code=exc.__class__.__name__,
                        last_observed_worker_event_index=worker_event_index,
                        last_accepted_event_id=last_accepted_event_id,
                    )
                    run_terminal_closed = _ingest_closed_run(result)
                    break
                worker_event_index += 1
                try:
                    result = await ingestor.ingest_async(
                        EngineEventCandidate(
                            envelope=envelope,
                            worker_event_index=worker_event_index,
                            engine_event=event,
                            observed_at=datetime.now(UTC),
                        )
                    )
                except Exception as exc:
                    _LOGGER.error(
                        "dispatch.worker_events.ingest_exception run_id=%s "
                        "attempt_id=%s execution_id=%s dispatch_record_id=%s "
                        "local_worker_id=%s worker_event_index=%s "
                        "engine_event_type=%s error_type=%s",
                        record.run_id,
                        record.attempt_id,
                        record.execution_id,
                        record.dispatch_record_id,
                        local_worker_id,
                        worker_event_index,
                        event.type.value,
                        exc.__class__.__name__,
                        exc_info=True,
                    )
                    result = ingestor.close_worker_lost(
                        envelope,
                        observed_at=datetime.now(UTC),
                        worker_lifecycle_signal="ingest_exception",
                        stream_error_code=exc.__class__.__name__,
                        last_observed_worker_event_index=worker_event_index,
                        last_accepted_event_id=last_accepted_event_id,
                    )
                    run_terminal_closed = _ingest_closed_run(result)
                    break
                if result.status in (
                    EngineIngestStatus.ACCEPTED,
                    EngineIngestStatus.DUPLICATE,
                ):
                    if result.events:
                        last_accepted_event_id = result.events[-1].event_id
                    if result.terminal_closeout or result.stop_worker_stream:
                        terminal_seen = True
                        run_terminal_closed = _ingest_closed_run(result)
                        break
        finally:
            if run_terminal_closed:
                self._duplicate_governance_registry.clear_run(record.run_id)
            self._active_handles.discard(handle)
            self._active_registry.unregister(
                attempt_id=record.attempt_id,
                execution_id=record.execution_id,
            )
            await _safe_close_worker_handle(handle)
            await _safe_release_lane_token(token)
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "dispatch.worker_events.consume_done run_id=%s attempt_id=%s "
                "execution_id=%s dispatch_record_id=%s local_worker_id=%s "
                "run_terminal_closed=%s",
                record.run_id,
                record.attempt_id,
                record.execution_id,
                record.dispatch_record_id,
                local_worker_id,
                run_terminal_closed,
            )


def _ingest_closed_run(result: EngineIngestResult) -> bool:
    """判断 ingest 结果是否表示 Run 已完成 terminal closeout。

    :param result: EngineEvent ingest 结果。
    :returns: 已接受或确认重复 terminal closeout 时返回 ``True``。
    """

    return result.terminal_closeout and result.status in (
        EngineIngestStatus.ACCEPTED,
        EngineIngestStatus.DUPLICATE,
    )


def _is_dispatchable_recheck(
    *,
    run: RunRow | None,
    attempt: AttemptRow | None,
    dispatch_record: DispatchRecordRow | None,
    record: PendingDispatchRecord,
) -> bool:
    """判断 lane acquired 后 durable facts 是否仍可 dispatch。

    :param run: Run row。
    :param attempt: Attempt row。
    :param dispatch_record: dispatch row。
    :param record: pending dispatch 摘要。
    :returns: 可 dispatch 时返回 ``True``。
    """

    return (
        run is not None
        and attempt is not None
        and dispatch_record is not None
        and run.status == RunStatus.RUNNING
        and run.current_attempt_id == record.attempt_id
        and attempt.status == AttemptStatus.STARTING
        and attempt.execution_id == record.execution_id
        and dispatch_record.status == DispatchRecordStatus.WAITING_FOR_LANE
        and dispatch_record.dispatch_record_id == record.dispatch_record_id
        and dispatch_record.execution_id == record.execution_id
        and dispatch_record.owner_host_instance_id is not None
        and dispatch_record.waiting_for_lane_at is not None
        and dispatch_record.lane_name is not None
        and dispatch_record.worker_accept_event_id is None
        and dispatch_record.cancelled_event_id is None
    )


def _cancelled_eof_candidate(
    *,
    envelope: LocalEngineEnvelope,
    worker_event_index: int,
    observed_at: datetime,
    cancellation_token: _HostCancellationToken,
) -> EngineEventCandidate:
    """把 cancel 后的 clean EOF 转为明确 run_cancelled candidate。

    :param envelope: 当前 worker envelope。
    :param worker_event_index: 合成 EngineEvent 的 worker event 序号。
    :param observed_at: Host 观察时间。
    :param cancellation_token: Host 注入 Engine 的取消 token。
    :returns: 可交给 EngineEventIngestor 的 cancel candidate。
    :raises Exception: 不主动抛出异常。
    """

    requested_at = cancellation_token.requested_at()
    if requested_at is None:
        requested_at = observed_at
    reason = cancellation_token.cancel_reason()
    if reason is None:
        reason = "host_cancelled"
    return EngineEventCandidate(
        envelope=envelope,
        worker_event_index=worker_event_index,
        observed_at=observed_at,
        engine_event=EngineEvent(
            occurred_at=observed_at,
            session_id=envelope.session_id,
            run_id=envelope.run_id,
            type=EngineEventType.RUN_CANCELLED,
            data=RunCancelledData(
                reason=reason,
                requested_at=requested_at,
                accepted_at=observed_at,
                finished_at=observed_at,
            ),
            metadata=None,
        ),
    )


def _read_startable_run(
    transaction: HostTransaction, session_id: str
) -> RunRow | None:
    """读取当前可进入 pre-start governance 的 Run。

    :param transaction: 当前 Host transaction。
    :param session_id: Session id。
    :returns: accepted Run、无 active 时的最早 queued Run，或 ``None``。
    """

    accepted = read_accepted_run_for_session(transaction, session_id)
    if accepted is not None:
        return accepted
    active = read_active_run_for_session(transaction, session_id)
    if active is not None:
        return None
    return read_earliest_queued_run(transaction, session_id)


def _display_text_from_input_event(
    transaction: HostTransaction, event: EventLogRow
) -> str:
    """从 ``USER_INPUT_ACCEPTED`` event 读取展示文本。

    :param transaction: 当前 Host transaction。
    :param event: input event row。
    :returns: 展示文本。
    :raises RuntimeError: payload 缺失展示文本时抛出。
    """

    payload = event_payload_object(
        transaction, event, payload_label="USER_INPUT_ACCEPTED"
    )
    value = payload.get("display_text")
    if not isinstance(value, str) or value.strip() == "":
        raise RuntimeError("USER_INPUT_ACCEPTED display_text is invalid")
    return value


def _is_worker_acceptable(
    *,
    run: RunRow | None,
    attempt: AttemptRow | None,
    dispatch_record: DispatchRecordRow | None,
    record: PendingDispatchRecord,
    original_dispatch_record: DispatchRecordRow,
) -> bool:
    """判断 worker accept transition 是否仍可提交。

    :param run: Run row。
    :param attempt: Attempt row。
    :param dispatch_record: 最新 dispatch row。
    :param record: pending dispatch 摘要。
    :param original_dispatch_record: worker 调用前的 dispatch row。
    :returns: 可提交 accept 时返回 ``True``。
    """

    return (
        run is not None
        and attempt is not None
        and dispatch_record is not None
        and run.status == RunStatus.RUNNING
        and run.current_attempt_id == record.attempt_id
        and attempt.status == AttemptStatus.STARTING
        and attempt.execution_id == record.execution_id
        and dispatch_record.status == DispatchRecordStatus.DISPATCHING
        and dispatch_record.dispatch_record_id
        == original_dispatch_record.dispatch_record_id
        and dispatch_record.worker_accept_event_id is None
        and dispatch_record.cancelled_event_id is None
    )


def _attempt_running_event_request(
    *,
    event_id: str,
    occurred_at: datetime,
    accepted_at_text: str,
    run: RunRow,
    attempt: AttemptRow,
    dispatch_record: DispatchRecordRow,
    local_worker_id: str,
    lane_name: str,
    lane_claim_id: str,
) -> EventLogAppendRequest:
    """构造 ``ATTEMPT_RUNNING`` 事件。

    :param event_id: 事件 id。
    :param occurred_at: 事件发生时间。
    :param accepted_at_text: worker accept timestamp 文本。
    :param run: Run row。
    :param attempt: Attempt row。
    :param dispatch_record: dispatch row。
    :param local_worker_id: 本地 worker id。
    :param lane_name: lane 名称。
    :param lane_claim_id: lane claim id。
    :returns: EventLog append request。
    """

    payload: dict[str, JsonValue] = {
        "attempt_id": attempt.attempt_id,
        "execution_id": attempt.execution_id,
        "dispatch_record_id": dispatch_record.dispatch_record_id,
        "worker_kind": _worker_kind_text(dispatch_record.worker_kind),
        "execution_target": dispatch_record.execution_target,
        "local_worker_id": local_worker_id,
        "worker_accepted_at": accepted_at_text,
        "lane_name": lane_name,
        "lane_claim_id": lane_claim_id,
        "reason": _WORKER_ACCEPT_REASON,
    }
    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=attempt.execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_RUNNING,
        occurred_at=occurred_at,
        actor=_EVENT_ACTOR,
        source=_EVENT_SOURCE,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": _WORKER_ACCEPT_REASON},
        payload_json=payload,
        payload_ref=None,
        payload_digest=None,
    )


def _worker_kind_text(worker_kind: WorkerKind) -> str:
    """序列化 worker kind。

    :param worker_kind: worker kind enum。
    :returns: schema 文本值。
    """

    return worker_kind.value


def _new_event_id(prefix: str) -> str:
    """生成事件 id。

    :param prefix: id 前缀。
    :returns: 新事件 id。
    """

    return f"{prefix}-{uuid4().hex}"


def _policy_snapshot_digest(policy_snapshot: PolicySnapshot) -> str:
    """计算本地 dispatch policy snapshot 的诊断 digest。

    :param policy_snapshot: 本地执行 policy snapshot。
    :returns: canonical sha256 digest。
    """

    return sha256_digest_json(
        {
            "policy_snapshot_ref": policy_snapshot.policy_snapshot_ref,
            "allow_tool_calls": policy_snapshot.agent_policy.allow_tool_calls,
            "max_iterations": policy_snapshot.agent_policy.max_iterations,
            "continuation_max_attempts": (
                policy_snapshot.agent_policy.continuation_max_attempts
            ),
            "tool_execution_timeout_seconds": (
                policy_snapshot.agent_policy.tool_execution_timeout_seconds
            ),
        }
    )


def _effective_dispatch_decision_from_payload(
    payload: JsonValue,
    *,
    fallback_policy_snapshot: PolicySnapshot,
) -> _EffectiveDispatchDecision:
    """从 ``USER_INPUT_ACCEPTED`` payload 解析冻结 dispatch 决策。

    :param payload: EventLog payload JSON。
    :param fallback_policy_snapshot: 旧 start_run / 低层路径使用的 fallback。
    :returns: effective dispatch 决策。
    :raises RuntimeError: 冻结 execution config 或 tool set JSON shape 非法时抛出。
    :raises ValueError: 冻结 provider/agent policy 枚举值或字段语义非法时抛出。
    """

    if not isinstance(payload, Mapping):
        return _EffectiveDispatchDecision(
            policy_snapshot=fallback_policy_snapshot,
            selected_business_tool_names=None,
        )
    execution_value = payload.get(_PAYLOAD_FIELD_EFFECTIVE_EXECUTION_CONFIG)
    tool_value = payload.get(_PAYLOAD_FIELD_EFFECTIVE_TOOL_SET)
    policy_snapshot = (
        fallback_policy_snapshot
        if execution_value is None
        else _policy_snapshot_from_effective_execution(execution_value)
    )
    selected_tool_names = (
        None if tool_value is None else _selected_tool_names_from_effective_tool_set(tool_value)
    )
    return _EffectiveDispatchDecision(
        policy_snapshot=policy_snapshot,
        selected_business_tool_names=selected_tool_names,
    )


def _policy_snapshot_from_effective_execution(value: JsonValue) -> PolicySnapshot:
    """从冻结 execution JSON 构造 PolicySnapshot。

    :param value: ``effective_execution_config`` JSON。
    :returns: PolicySnapshot。
    :raises RuntimeError: JSON shape 非法时抛出。
    :raises ValueError: 冻结 provider/agent policy 枚举值或字段语义非法时抛出。
    """

    snapshot = _effective_execution_snapshot_from_json(value)
    return PolicySnapshot(
        runner_spec=snapshot.runner_spec,
        runner_options=snapshot.runner_options,
        agent_policy=snapshot.agent_policy,
        policy_snapshot_ref=snapshot.policy_snapshot_ref,
    )


def _selected_tool_names_from_effective_tool_set(
    value: JsonValue,
) -> frozenset[str] | None:
    """从冻结 tool set JSON 读取本次 effective 业务工具名。

    :param value: ``effective_tool_set`` JSON。
    :returns: ``None`` 表示全量，否则为冻结后的业务工具名集合。
    :raises RuntimeError: JSON shape 非法时抛出。
    """

    root = _required_json_mapping(value, field_name="effective_tool_set")
    selector = _required_json_text(root, field_name="selector")
    if selector == "all":
        return None
    names_value = root.get("effective_business_tool_names")
    if not isinstance(names_value, list):
        raise RuntimeError("effective_business_tool_names must be list")
    names: set[str] = set()
    for item in names_value:
        if not isinstance(item, str) or item.strip() == "":
            raise RuntimeError("effective_business_tool_names entries must be text")
        names.add(item)
    return frozenset(names)


def _register_dispatch_host_instance(
    *,
    transaction_runner: HostTransactionRunner,
    identity: HostInstanceIdentity,
) -> None:
    """注册 dispatch owner_host_instance_id 的 FK 诊断 row。

    :param transaction_runner: Host durable transaction runner。
    :param identity: 当前 scheduler 的 Host instance 身份。
    :returns: ``None``。
    :raises Exception: durable write 失败时透传。
    """

    def _operation(transaction: HostTransaction) -> None:
        register_current_instance(transaction, identity)

    transaction_runner.run_write(_operation)


def _new_dispatch_host_instance_identity(
    host_handle_id: str,
) -> HostInstanceIdentity:
    """创建 dispatch scheduler 的 Host instance 身份。

    :param host_handle_id: Host handle 诊断 id。
    :returns: HostInstanceIdentity。
    :raises ValueError: ``host_handle_id`` 为空时抛出。
    """

    if host_handle_id.strip() == "":
        raise ValueError("host_handle_id must be non-empty")
    return HostInstanceIdentity(
        host_instance_id=host_handle_id,
        pid=os.getpid(),
        process_start_token=uuid4().hex,
        boot_id=None,
    )


def _safe_cancel_worker_handle(handle: LocalWorkerHandle, reason: str) -> None:
    """best-effort 取消 worker handle，避免清理路径被 handle 异常打断。

    :param handle: worker handle。
    :param reason: 取消原因。
    :returns: ``None``。
    """

    try:
        handle.cancel(reason)
    except Exception as exc:
        _LOGGER.warning(
            "active worker cancel failed; continuing reason=%s error_type=%s",
            reason,
            exc.__class__.__name__,
        )
        return


async def _safe_close_worker_handle(handle: LocalWorkerHandle) -> None:
    """best-effort 关闭 worker handle。

    :param handle: worker handle。
    :returns: ``None``。
    """

    try:
        await handle.close()
    except Exception as exc:
        _LOGGER.warning(
            "dispatch.worker_handle.close_failed error_type=%s",
            exc.__class__.__name__,
            exc_info=True,
        )
        return


async def _safe_release_lane_token(token: LaneClaimToken) -> None:
    """best-effort 释放 runtime lane token。

    :param token: lane claim token。
    :returns: ``None``。
    """

    try:
        await token.release()
    except Exception as exc:
        _LOGGER.warning(
            "dispatch.lane_token.release_failed lane_name=%s claim_id=%s "
            "error_type=%s",
            token.name,
            token.claim_id,
            exc.__class__.__name__,
            exc_info=True,
        )
        return


async def _suppress_task_cancel(task: asyncio.Task[None]) -> None:
    """等待 task 结束并吞掉取消异常。

    :param task: 待等待 task。
    :returns: ``None``。
    """

    try:
        await task
    except asyncio.CancelledError:
        return


__all__ = [
    "ActiveCancelMessage",
    "ActiveWorkerRegistry",
    "DispatchDrainResult",
    "HostDispatchScheduler",
]
