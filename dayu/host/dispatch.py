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
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol, TypeAlias
from uuid import uuid4

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_schema import ToolSchema
from dayu.contracts.tool_executor import ToolExecutor
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    RunCancelledData,
)
from dayu.engine.contracts.runner_identity import SuccessfulRunnerResponseIdentity
from dayu.host.admission import (
    AdmissionWakeupPort,
    EffectiveToolFacts,
    PendingDispatchRecord,
    parse_effective_tool_facts,
    validate_effective_tool_facts_runtime,
)
from dayu.host.api import (
    AttemptDispatchSnapshot,
    AttemptStatus,
    HostLocalExecutionOptions,
    LocalWorkerHandle,
    RunStatus,
    SessionStatus,
    SourceRunRelation,
)
from dayu.host.durable.codec import (
    canonical_json_dumps,
    format_utc_timestamp,
    parse_utc_timestamp,
    sha256_digest_json,
)
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.errors import HostDurableError, HostTransactionRetryExhaustedError
from dayu.host.durable.liveness import (
    HostInstanceIdentity,
    heartbeat_current_instance,
    mark_current_instance_stopped,
    mark_current_instance_stopping,
    register_current_instance,
)
from dayu.host.durable.run_transition import (
    ActiveCancelWatchdogCloseoutInput,
    FailUnstartedRunInput,
    OwnedAttemptCancelDelivery,
    OwnedAttemptCancelTarget,
    StartGovernedRunInput,
    TerminalCloseoutInput,
    active_cancel_watchdog_closeout_in_transaction,
    fail_unstarted_run_in_transaction,
    project_terminal_notice_from_exact_run_event,
    read_cancel_requested_event_from_run_link,
    read_exact_owned_attempt_cancel_deliveries,
    read_exact_owned_attempt_cancel_targets,
    start_governed_run_with_starting_attempt_in_transaction,
    terminal_closeout_in_transaction,
)
from dayu.host.durable.state import (
    AttemptExecutionIdentity,
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
    read_cancelling_runs_for_session,
    read_dispatch_record_by_id,
    read_dispatch_record_by_attempt_id,
    read_earliest_queued_run,
    read_run_by_id,
    read_session_by_id,
)
from dayu.host.durable.transaction import HostRow, HostTransaction, HostTransactionRunner
from dayu.host._execution_health import HostExecutionHealthGate
from dayu.host.session_attachment import (
    SessionNewWorkAccessPort,
    SessionWorkLease,
)
from dayu.host._execution_config_projection import (
    effective_execution_snapshot_from_json as _effective_execution_snapshot_from_json,
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
from dayu.host.transient_delta import HostTransientDeltaPublisher
from dayu.host.terminal_post_commit import (
    TerminalPostCommitNotice,
    TerminalPostCommitPort,
)
from dayu.host.payload_resolution import event_payload_object
from dayu.host.run_input import (
    NoToolExecutor,
    PolicySnapshot,
    PreparedRunnerCallCandidate,
    SessionContinuityView,
    ToolExecutionMode,
    agent_run_request_from_prepared_candidate,
    estimate_prepared_runner_call_candidate,
    load_prepared_runner_call_candidate,
    prepare_runner_call_candidate_in_transaction,
    record_prepared_runner_call_candidate_in_transaction,
    resolve_prepared_runner_call_context_anchor_in_transaction,
)
from dayu.host._runner_call_manifest import (
    RunnerCallSizingUnavailableReason,
    complete_runner_call_sizing_snapshot,
    unavailable_runner_call_sizing_snapshot,
)
from dayu.host.memory import digest_memory_projection_policy
from dayu.host.memory_repair import (
    ConversationMemoryProjectionRepairResult,
    catch_up_conversation_memory_projection,
)
from dayu.host.compact_payload import (
    COMPACT_ARTIFACT_MEDIA_TYPE_VNEXT,
    COMPACT_PROJECTION_SIGNAL_MEMORY_CATCHUP,
    compact_artifact_descriptor_metadata_vnext,
    compact_artifact_json_vnext,
    compact_artifact_payload_ref,
    prompt_local_label_mapping_refs,
)
from dayu.host.compact_material import (
    PreDispatchCompactMaterialView,
    build_pre_dispatch_compact_material_view,
)
from dayu.host.compact_pipeline import (
    CompactPipelineRequestPlan,
    CompactPipelineSourceSnapshot,
    build_fallback_decision_input,
    build_normal_compact_request_plan,
    build_tier_recovery_request_plans,
    compact_pipeline_source_snapshot_from_pre_dispatch_view,
)
from dayu.host.compaction import (
    CompactAcceptedTruthV4,
    CompactionRequest,
    CompactRepairFeedbackV4,
)
from dayu.host.compaction_operation import (
    CompactionAttemptRejected,
    CompactionRejectedAttemptDiagnosticReference,
    CompactionOperationResult,
    DurableCompactorProposalManifestRecorder,
    run_compaction_attempt,
    write_compaction_rejected_attempt_diagnostic_artifact,
)
from dayu.host.context_event_payload import store_context_compacted_payload
from dayu.host.context_events import CompactorProposalManifestReference
from dayu.host.compaction_terminal import (
    COMPACTION_TERMINAL_INVALID_MULTIPLE_ERROR,
    CompactionOperationTerminalDisposition,
    CompactionTerminalClosed,
    begin_compaction_terminal_commit_in_transaction,
)
from dayu.host.context_budget import (
    BudgetEstimate,
    ContextBudgetDecision,
    ContextSizingFallbackReason,
    ContextSizingResult,
    ContextSizingStage,
    build_conservative_context_sizing_result,
    build_context_sizing_result,
)
from dayu.host.context_fallback import (
    FALLBACK_ACTION_DISPATCH,
    FALLBACK_ACTION_NOT_APPLICABLE,
)
from dayu.host.context_events import (
    CONTEXT_COMPACTED,
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    CONTEXT_COMPACTION_FAILED,
    CONTEXT_COMPACTION_REQUESTED,
    append_context_budget_evaluated_in_transaction,
    build_context_compaction_attempt_rejected_payload,
    build_context_compacted_payload,
    build_context_compaction_failed_payload,
    build_context_compaction_requested_payload,
)
from dayu.host.context_policy import (
    ContextBudgetPolicy,
    ContextCompactionTriggerSource,
)
from dayu.host.proactive_compaction import (
    ProactiveCompactionAttemptPlan,
    ProactiveCompactionAttemptStage,
    ProactiveCompactionDecision,
    ProactiveCompactionState,
    ProactiveCompactionTierRequest,
    build_proactive_compaction_attempt_schedule,
    read_proactive_compaction_projection,
    validate_proactive_compaction_attempt_schedule,
)
from dayu.host.durable.artifact import LocalArtifactStore
from dayu.host.durable.payload import PayloadStore
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.tool_runtime import (
    DefaultHostToolFactAcceptPort,
    DefaultToolRuntimeFactory,
    EffectiveToolBundleBuildRequest,
    EffectiveToolBundleBuilder,
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
_ACTIVE_CANCEL_WATCHDOG_ACTOR = "host.active_cancel_watchdog"
_ACTIVE_CANCEL_WATCHDOG_SOURCE = "host.dispatch"
_ACTIVE_CANCEL_WATCHDOG_OWNER = "host.active_cancel_watchdog"
_ACTIVE_CANCEL_WORKER_LIFECYCLE_SIGNAL = "active_cancel_watchdog_closeout"
_WORKER_STARTUP_TIMEOUT_REASON = "worker_startup_timeout"
_MEMORY_PROJECTION_REPAIR_REQUIRED_REASON = "memory_projection_repair_required"
_LOCAL_POLICY_SNAPSHOT_REF = "host-local-no-tool-policy"
_PAYLOAD_FIELD_EFFECTIVE_EXECUTION_CONFIG = "effective_execution_config"
_PAYLOAD_FIELD_EFFECTIVE_TOOL_SET = "effective_tool_set"
_EVENT_ID_ATTEMPT_RUNNING_PREFIX = "event-attempt-running"
_EVENT_ID_ATTEMPT_FAILED_PREFIX = "event-attempt-failed"
_EVENT_ID_RUN_FAILED_PREFIX = "event-run-failed"
_EVENT_ID_ATTEMPT_CANCELLED_WATCHDOG_PREFIX = "event-attempt-cancelled-watchdog"
_EVENT_ID_RUN_CANCELLED_WATCHDOG_PREFIX = "event-run-cancelled-watchdog"
_EVENT_ID_CONTEXT_COMPACTION_REQUESTED_PREFIX = "event-context-compact-requested"
_EVENT_ID_CONTEXT_COMPACTED_PREFIX = "event-context-compacted"
_EVENT_ID_CONTEXT_COMPACTION_ATTEMPT_REJECTED_PREFIX = "event-context-compaction-attempt-rejected"
_LANE_OWNER_PREFIX = "host-dispatch"
_GOVERNANCE_ACTOR = "host.context_governance"
_GOVERNANCE_FAILURE_REASON = "pre_dispatch_context_governance"
_CONTEXT_HARD_THRESHOLD_BEFORE_DISPATCH = "context_hard_threshold_before_dispatch"
_CONTEXT_HARD_THRESHOLD_AFTER_COMPACTION = "context_hard_threshold_after_compaction"
_CONTEXT_HARD_THRESHOLD_AFTER_FALLBACK = "context_hard_threshold_after_fallback"
_COMPACT_FAILURE_POLICY_DECISION = "compact_failed_before_dispatch"
_PROACTIVE_INVALID_OR_EXHAUSTED_REASON = "proactive_operation_invalid_or_exhausted"
_COMPACTION_CANCEL_REASON_RUN_MISSING = "run_missing"
_COMPACTION_CANCEL_REASON_SESSION_MISSING = "session_missing"
_COMPACTION_CANCEL_REASON_SESSION_CLOSED = "session_closed"
_COMPACTION_CANCEL_REASON_INPUT_CHANGED = "run_input_event_sequence_changed"
_COMPACTION_CANCEL_REASON_STATUS_PREFIX = "run_status_changed"
_COMPACTION_CANCEL_REASON_DURABLE_UNAVAILABLE = "durable_unavailable"
_COMPACTION_PRECONDITION_OPERATION_PREFIX = "precondition"
_HOST_INSTANCE_HEARTBEAT_INTERVAL_SECONDS = 1.0
_LOCAL_WORKER_CLOSE_GRACE_SECONDS = 3.0
_SCHEDULER_CLOSE_REASON = "scheduler_close"
_SCHEDULER_UNAVAILABLE_REASON = "scheduler_not_accepting_wake"
_CRITICAL_FATAL_REASON = "critical_task_unexpected_exit"
_CRITICAL_COMPONENT_HEARTBEAT = "heartbeat"
_CRITICAL_COMPONENT_DISPATCH = "dispatch"
_CRITICAL_COMPONENT_PROMOTION = "promotion"
_CRITICAL_COMPONENT_ACTIVE_CANCEL_WATCHDOG = "active_cancel_watchdog"
_CRITICAL_COMPONENT_ACTIVE_CANCEL_OWNER = "active_cancel_owner_reconciliation"


class _MemoryProjectionDispatchDiagnosticError(HostDurableError):
    """dispatch 前 memory projection repair 未覆盖 required cursor 的诊断错误。

    :param operation: 触发错误的 repair 操作。
    :param run_id: 目标 Run id。
    :param attempt_id: 目标 Attempt id。
    :param execution_id: 目标 execution id。
    :param required_event_sequence: dispatch 必须覆盖的 EventLog cursor。
    :param result: repair 执行结果。
    """

    operation: str
    run_id: str
    attempt_id: str
    execution_id: str
    required_event_sequence: int
    result: ConversationMemoryProjectionRepairResult

    def __init__(
        self,
        *,
        operation: str,
        run_id: str,
        attempt_id: str,
        execution_id: str,
        required_event_sequence: int,
        result: ConversationMemoryProjectionRepairResult,
    ) -> None:
        """初始化 diagnostic error。

        :param operation: 触发错误的 repair 操作。
        :param run_id: 目标 Run id。
        :param attempt_id: 目标 Attempt id。
        :param execution_id: 目标 execution id。
        :param required_event_sequence: dispatch 必须覆盖的 EventLog cursor。
        :param result: repair 执行结果。
        :returns: ``None``。
        """

        self.operation = operation
        self.run_id = run_id
        self.attempt_id = attempt_id
        self.execution_id = execution_id
        self.required_event_sequence = required_event_sequence
        self.result = result
        super().__init__(
            "dispatch memory projection repair did not reach required cursor: "
            f"operation={operation}, run_id={run_id}, attempt_id={attempt_id}, "
            f"execution_id={execution_id}, required_event_sequence="
            f"{required_event_sequence}, finished_cursor={result.finished_cursor}, "
            f"stop_reason={result.stop_reason.value}"
        )


_LOG_DRAIN_LOOP_IDLE = "dispatch.drain_loop.idle host_handle_id=%s interval_seconds=%s"
_LOG_DRAIN_LOOP_CLOSE_EXIT = "dispatch drain loop exiting after close host_handle_id=%s"
_LOG_DRAIN_LOOP_CANCELLED_FOR_CLOSE = "dispatch drain loop cancelled during close host_handle_id=%s"
_LOG_DRAIN_LOOP_CANCELLED_EXTERNALLY = "dispatch drain loop cancelled externally host_handle_id=%s"
_LOG_DRAIN_LOOP_UNEXPECTED_EXCEPTION = (
    "dispatch drain loop stopped unexpectedly; reporting fatal host_handle_id=%s error_type=%s"
)
_LOG_DRAIN_LOOP_DURABLE_RETRY_EXHAUSTED = (
    "dispatch drain loop durable retry exhausted; backing off and retrying host_handle_id=%s error_type=%s"
)
_LOG_WORKER_LOST_CLOSEOUT_FAILED = (
    "dispatch.worker_events.close_worker_lost_failed run_id=%s "
    "attempt_id=%s execution_id=%s dispatch_record_id=%s "
    "local_worker_id=%s worker_lifecycle_signal=%s "
    "last_observed_worker_event_index=%s closeout_error_type=%s "
    "original_error_type=%s"
)
_LOGGER = logging.getLogger(__name__)


def _raise_if_memory_projection_target_not_reached(
    *,
    operation: str,
    record: PendingDispatchRecord,
    required_event_sequence: int,
    result: ConversationMemoryProjectionRepairResult,
) -> None:
    """确认 dispatch 前 memory projection 已覆盖 required cursor。

    :param operation: repair 操作名称。
    :param record: pending dispatch 摘要。
    :param required_event_sequence: dispatch 必须覆盖的 EventLog cursor。
    :param result: repair 执行结果。
    :returns: ``None``。
    :raises _MemoryProjectionDispatchDiagnosticError: repair 未覆盖目标时抛出。
    """

    if result.failures == 0 and result.target_reached:
        return
    raise _MemoryProjectionDispatchDiagnosticError(
        operation=operation,
        run_id=record.run_id,
        attempt_id=record.attempt_id,
        execution_id=record.execution_id,
        required_event_sequence=required_event_sequence,
        result=result,
    )


def _precondition_compaction_operation_id(*, failure_reason: str, estimate: BudgetEstimate) -> str:
    """构造未写 request fact 的 precondition failure operation id。

    :param failure_reason: precondition failure reason。
    :param estimate: 触发该分支的预算估算。
    :returns: 可写入 failed payload 的稳定 operation id。
    """

    return f"{_COMPACTION_PRECONDITION_OPERATION_PREFIX}:{failure_reason}:{estimate.estimator_digest}"


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
class OwnedSessionReconciliationResult:
    """一次 ACTIVE RW Session durable reconciliation 摘要。

    :param owned_session_count: 入口稳定快照包含的 ACTIVE RW Session 数。
    :param leased_session_count: 快照后仍成功取得 new-work lease 的 Session 数。
    :param dispatched_session_count: 本轮创建 stable dispatch 的 Session 数。
    :param skipped_session_count: close race 或没有可推进工作而跳过的 Session 数。
    """

    owned_session_count: int
    leased_session_count: int
    dispatched_session_count: int
    skipped_session_count: int


@dataclass(slots=True)
class _PreStartGovernanceFlight:
    """同一 Session 的 scheduler-local pre-start sole flight。

    :param task: 执行 coalesced durable governance passes 的唯一 task。
    :param rerun_requested: flight 运行期间是否收到新的 level-bit signal。
    """

    task: asyncio.Task[bool]
    rerun_requested: bool


@dataclass(frozen=True, slots=True)
class ActiveWorkerCancelReconciliationResult:
    """一次 execution-owner active cancel reconciliation 摘要。

    :param snapshot_count: 本轮 registry exact identity 快照数量。
    :param target_count: durable strict query 返回的 owned cancel target 数量。
    :param propagated_count: transaction 外仍命中同一 local worker 的数量。
    :param closed_count: 本轮 exact watchdog 成功写入 terminal closeout 的数量。
    """

    snapshot_count: int
    target_count: int
    propagated_count: int
    closed_count: int


@dataclass(frozen=True, slots=True)
class ActiveCancelWatchdogTickResult:
    """active cancel watchdog 单次 tick 摘要。

    :param scanned: 本轮扫描到的 ``CANCELLING`` Run 数。
    :param eligible: 本轮满足 accepted-cancel 收口前置条件的 Run 数。
    :param closed: 本轮成功收口为 ``CANCELLED`` 的 Run 数。
    :param ignored: 本轮因缺少 accepted cancel / current Attempt / dispatch
        accepted 事实或 CAS 前置不满足而跳过的 Run 数。
    """

    scanned: int
    eligible: int
    closed: int
    ignored: int


@dataclass(frozen=True, slots=True)
class _ActiveCancelWatchdogCandidate:
    """active cancel watchdog 可扫描候选。

    :param run_id: 目标 Run id。
    :param session_id: 目标 Session id。
    :param attempt_id: 当前 Running Attempt id。
    :param cancel_requested_at: durable ``CANCEL_REQUESTED`` 发生时间。
    """

    run_id: str
    session_id: str
    attempt_id: str
    cancel_requested_at: datetime


@dataclass(frozen=True, slots=True)
class _ActiveCancelWatchdogSessionScope:
    """caller / fresh attachment 指定的 Session watchdog scope。

    :param session_id: 目标 Session id。
    """

    session_id: str


@dataclass(frozen=True, slots=True)
class _ActiveCancelWatchdogOwnedTargetScope:
    """execution owner 已严格验证的 exact target watchdog scope。

    :param target: 需要在写事务内重验的 exact owned target。
    """

    target: OwnedAttemptCancelTarget


@dataclass(frozen=True, slots=True)
class _ActiveCancelWatchdogOperationResult:
    """active cancel watchdog write transaction 结果。

    :param scanned: 本轮扫描到的 ``CANCELLING`` Run 数。
    :param eligible: 本轮满足 accepted-cancel 收口前置条件的 Run 数。
    :param terminal_notices: 本轮按 terminal event sequence 排序的通知。
    :param ignored: 本轮跳过的 Run 数。
    """

    scanned: int
    eligible: int
    terminal_notices: tuple[TerminalPostCommitNotice, ...]
    ignored: int


@dataclass(frozen=True, slots=True)
class _ReadCommittedCancelRequestedAtOperation:
    """读取 Run linked ``CANCEL_REQUESTED`` canonical fact 的发生时间。

    :param event_log_store: EventLog primitive。
    :param run_id: 目标 Run id。
    """

    event_log_store: EventLogStore
    run_id: str

    def __call__(self, transaction: HostTransaction) -> datetime | None:
        """执行 durable read 并返回 committed cancel 请求时间。

        :param transaction: Host durable read transaction。
        :returns: linked ``CANCEL_REQUESTED`` 发生时间；Run 缺失或 link
            不存在时返回 ``None``。
        """

        run = read_run_by_id(transaction, self.run_id)
        if run is None:
            return None
        cancel_requested = read_cancel_requested_event_from_run_link(
            transaction,
            self.event_log_store,
            run,
        )
        if cancel_requested is None:
            return None
        return parse_utc_timestamp(cancel_requested.occurred_at)


@dataclass(frozen=True, slots=True)
class ActiveCancelMessage:
    """active worker cancel registry 的最小取消消息。

    :param session_id: 目标 Session id。
    :param run_id: 目标 Run id。
    :param attempt_id: 目标 Attempt id。
    :param execution_id: 目标 execution id。
    :param reason: 取消原因。
    """

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    reason: str


class ActiveWorkerCancelPort(Protocol):
    """command path 传播 active worker cancel 的最小 typed port。"""

    def cancel(self, message: ActiveCancelMessage) -> bool:
        """向匹配的 active execution 传播取消。

        :param message: durable commit 后的 active cancel 消息。
        :returns: 找到匹配 active execution 时返回 ``True``。
        :raises Exception: port 或 event-loop bridge 失败时透传。
        """

        ...


class NoActiveWorkerCancelPort:
    """未装配 execution worker 时使用的显式空 cancel port。"""

    def cancel(self, message: ActiveCancelMessage) -> bool:
        """确认当前没有可传播的 active worker。

        :param message: durable commit 后的 active cancel 消息。
        :returns: 固定返回 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        return False


class _TerminalPostCommitPortFactory(Protocol):
    """scheduler 构造期创建 terminal post-commit port 的内部工厂。"""

    def create_terminal_post_commit_port(
        self,
        *,
        promotion_port: AdmissionWakeupPort,
    ) -> TerminalPostCommitPort:
        """以稳定 ordinary promotion capability 创建最终端口。

        :param promotion_port: 已构造但尚未启动的 scheduler promotion capability。
        :returns: 本 opener 唯一 terminal post-commit port。
        :raises Exception: coordinator 或 port 构造失败时透传。
        """

        ...

    async def close_after_failed_scheduler_open(self) -> None:
        """清理 scheduler 构造失败前已创建的 coordinator 资源。

        :returns: ``None``。
        :raises Exception: coordinator 清理失败时透传。
        """

        ...


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
    :param source_snapshot: request 使用的 compact source snapshot。
    :param request_plan: request 的 pipeline-owned 构造结果。
    :param material_view: request 使用的冻结 material view。
    :param operation_id: 对应 ``CONTEXT_COMPACTION_REQUESTED`` event id。
    :param estimate: compact 前预算估算。
    :param decision: 预算决策。
    :param first_attempt_number: 本次 execution 的首个全局 attempt number。
    :param max_attempt_number: request 冻结的全局 attempt 上限。
    """

    run_id: str
    session_id: str
    expected_status: RunStatus
    expected_input_event_sequence: int
    request: CompactionRequest
    source_snapshot: CompactPipelineSourceSnapshot
    request_plan: CompactPipelineRequestPlan
    material_view: PreDispatchCompactMaterialView
    operation_id: str
    estimate: BudgetEstimate
    decision: ContextBudgetDecision
    first_attempt_number: int
    max_attempt_number: int


@dataclass(frozen=True, slots=True)
class _GovernanceStageResult:
    """pre-start governance 阶段结果。

    :param pending_dispatch: 已直接启动时的 pending dispatch。
    :param compact_accepted: compact accepted 但尚未 memory catch-up/start 的摘要。
    :param compact_pending: 已写 request fact、待事务外执行的 compact。
    :param terminal_notice: attempt-free terminal commit 的精确通知。
    """

    pending_dispatch: PendingDispatchRecord | None
    compact_accepted: _GovernanceCompactAccepted | None
    compact_pending: _GovernanceCompactPending | None = None
    terminal_notice: TerminalPostCommitNotice | None = None


@dataclass(frozen=True, slots=True)
class BudgetedDispatchStart:
    """有 Host context policy 的 allow start plan。

    :param start_input: allow 后唯一生成的 durable start input。
    :param sizing: complete candidate conservative sizing truth。
    """

    start_input: StartGovernedRunInput
    sizing: ContextSizingResult


@dataclass(frozen=True, slots=True)
class NoBudgetDispatchStart:
    """context policy unavailable 的 allow-without-budget start plan。

    :param start_input: allow 后唯一生成的 durable start input。
    :param stage: 当前 candidate 的实际 sizing stage。
    """

    start_input: StartGovernedRunInput
    stage: ContextSizingStage


DispatchStartPlan: TypeAlias = BudgetedDispatchStart | NoBudgetDispatchStart


class _StartCandidateCasMissRollback(Exception):
    """start precondition miss 的 transaction-private rollback 信号。"""


def _build_candidate_sizing_result(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    stage: ContextSizingStage,
    candidate: PreparedRunnerCallCandidate,
    policy: ContextBudgetPolicy,
    estimate: BudgetEstimate,
) -> ContextSizingResult:
    """在当前 dispatch transaction 内构造唯一 candidate sizing 结果。

    accepted compact 后的 immediate candidate 没有可证明的普通 lineage
    continuity，因此固定使用完整 conservative estimate；其余 dispatch
    candidate 在同一 snapshot 内解析 durable anchor，再交给 budget owner
    计算预测与五阶段动作。

    :param transaction: 调用方当前 Host transaction。
    :param event_log_store: stateless EventLog primitive。
    :param stage: 当前 candidate sizing stage。
    :param candidate: complete prepared runner-call candidate。
    :param policy: frozen context budget policy。
    :param estimate: 当前 complete candidate 的 conservative estimate。
    :returns: anchored 或 conservative sizing result。
    :raises TypeError: typed 参数非法时抛出。
    :raises ValueError: candidate、policy、estimate 或 resolver atoms 不一致时抛出。
    """

    if stage in (
        ContextSizingStage.POST_COMPACT,
        ContextSizingStage.REACTIVE_POST_COMPACT,
    ):
        return build_conservative_context_sizing_result(
            stage=stage,
            candidate_input_cursor=candidate.candidate_input_cursor,
            candidate_input_projection_ref=(candidate.candidate_input_projection_ref),
            candidate_input_digest=candidate.input_snapshot_digest,
            policy=policy,
            estimate=estimate,
            fallback_reason=(ContextSizingFallbackReason.ACCEPTED_COMPACT_INVALIDATED),
        )
    anchor_resolution = resolve_prepared_runner_call_context_anchor_in_transaction(
        transaction,
        event_log_store,
        candidate=candidate,
        context_window_size=policy.context_window_size,
    )
    return build_context_sizing_result(
        stage=stage,
        candidate_input_cursor=candidate.candidate_input_cursor,
        candidate_input_projection_ref=(candidate.candidate_input_projection_ref),
        candidate_input_digest=candidate.input_snapshot_digest,
        policy=policy,
        estimate=estimate,
        anchor_resolution=anchor_resolution,
    )


@dataclass(frozen=True, slots=True)
class _DispatchCandidateOutcome:
    """post-compact / fallback candidate 的封闭事务结果。

    :param pending_dispatch: allow 后创建的唯一 pending dispatch。
    :param terminal_notice: hard pressure closeout 的精确 terminal notice。
    """

    pending_dispatch: PendingDispatchRecord | None
    terminal_notice: TerminalPostCommitNotice | None

    def __post_init__(self) -> None:
        """校验 pending 与 terminal 恰有一个成立。

        :returns: ``None``。
        :raises ValueError: 两个结果同时存在或同时缺失时抛出。
        """

        if (self.pending_dispatch is None) == (self.terminal_notice is None):
            raise ValueError("dispatch candidate outcome requires exactly one result")


def _hard_threshold_closeout(
    stage: ContextSizingStage,
) -> tuple[str, str]:
    """返回各 sizing stage 的 hard closeout 错误语义。

    :param stage: 当前 candidate sizing stage。
    :returns: ``(error_code, message)``。
    :raises ValueError: stage 不是已冻结的三种治理阶段时抛出。
    """

    if stage is ContextSizingStage.ORDINARY:
        return (
            _CONTEXT_HARD_THRESHOLD_BEFORE_DISPATCH,
            "Context estimate exceeds hard threshold before dispatch",
        )
    if stage is ContextSizingStage.POST_COMPACT:
        return (
            _CONTEXT_HARD_THRESHOLD_AFTER_COMPACTION,
            "Context estimate exceeds hard threshold after compaction",
        )
    if stage is ContextSizingStage.DISPATCH_FALLBACK:
        return (
            _CONTEXT_HARD_THRESHOLD_AFTER_FALLBACK,
            "Context estimate exceeds hard threshold after fallback",
        )
    raise ValueError("unsupported context sizing stage")


@dataclass(frozen=True, slots=True)
class _ProactiveCompactionExecutionResult:
    """proactive compaction 事务外执行后的 Host 后续动作。

    :param compacted_event_sequence: accepted compact event sequence。
    :param pending_dispatch: fallback dispatch 已启动时的 pending dispatch。
    :param terminal_notice: attempt-free terminal commit 的精确通知。
    """

    compacted_event_sequence: int | None
    pending_dispatch: PendingDispatchRecord | None
    terminal_notice: TerminalPostCommitNotice | None = None


@dataclass(frozen=True, slots=True)
class _EffectiveDispatchDecision:
    """一次 dispatch 从 durable input event 读取的冻结决策。

    :param policy_snapshot: effective runner / agent policy snapshot。
    :param effective_tool_facts: admission 冻结的完整 exact tool facts。
    """

    policy_snapshot: PolicySnapshot
    effective_tool_facts: EffectiveToolFacts


@dataclass(frozen=True, slots=True)
class _CandidateToolSelection:
    """pre-start candidate 的 Attempt-free selected tool snapshot。

    :param tool_schemas: frozen selected schemas。
    :param disable_tools: 是否禁用工具。
    :param execution_mode: scene 与 actual runtime 共用的工具模式。
    """

    tool_schemas: tuple[ToolSchema, ...]
    disable_tools: bool
    execution_mode: ToolExecutionMode


@dataclass(frozen=True, slots=True)
class _ActiveWorkerEntry:
    """active worker registry 内部条目。

    :param identity: 目标 worker 的 exact durable identity。
    :param handle: worker handle。
    :param cancellation_token: Host 注入 Engine 的取消 token。
    """

    identity: AttemptExecutionIdentity
    handle: LocalWorkerHandle
    cancellation_token: "_HostCancellationToken"


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
        session_id: str,
        run_id: str,
        attempt_id: str,
        execution_id: str,
        handle: LocalWorkerHandle,
        cancellation_token: "_HostCancellationToken",
    ) -> None:
        """注册 active worker handle。

        :param session_id: 目标 Session id。
        :param run_id: 目标 Run id。
        :param attempt_id: active Attempt id。
        :param execution_id: active execution id。
        :param handle: worker handle。
        :param cancellation_token: 注入 Engine 的取消 token。
        :returns: ``None``。
        """

        with self._lock:
            self._entries[(attempt_id, execution_id)] = _ActiveWorkerEntry(
                identity=AttemptExecutionIdentity(
                    session_id=session_id,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    execution_id=execution_id,
                ),
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
        """向 active worker best-effort 传播取消。

        :param message: 最小取消消息。
        :returns: 找到匹配 active worker 时返回 ``True``。
        """

        with self._lock:
            entry = self._entries.get((message.attempt_id, message.execution_id))
        if entry is None or entry.identity != AttemptExecutionIdentity(
            session_id=message.session_id,
            run_id=message.run_id,
            attempt_id=message.attempt_id,
            execution_id=message.execution_id,
        ):
            return False
        _propagate_active_worker_cancel(message, entry)
        return True

    def snapshot_identities(self) -> tuple[AttemptExecutionIdentity, ...]:
        """返回当前 active workers 的稳定 exact identity 快照。

        快照不暴露 handle 或 cancellation token，供 scheduler 在 transaction
        外按同一 identity 传播已验证的 durable cancel truth。

        :returns: 按 Session / Run / Attempt / execution 排序的 identity 元组。
        :raises Exception: 不主动抛出异常。
        """

        with self._lock:
            identities = tuple(entry.identity for entry in self._entries.values())
        return tuple(
            sorted(
                identities,
                key=lambda identity: (
                    identity.session_id,
                    identity.run_id,
                    identity.attempt_id,
                    identity.execution_id,
                ),
            )
        )

    def cancel_all(self, reason: str) -> int:
        """向所有当前 active worker best-effort 传播取消。

        :param reason: 取消原因。
        :returns: 已找到并传播取消的 active worker 数量。
        """

        with self._lock:
            entries = tuple(
                (
                    ActiveCancelMessage(
                        session_id=entry.identity.session_id,
                        run_id=entry.identity.run_id,
                        attempt_id=attempt_id,
                        execution_id=execution_id,
                        reason=reason,
                    ),
                    entry,
                )
                for (attempt_id, execution_id), entry in self._entries.items()
            )
        for message, entry in entries:
            _propagate_active_worker_cancel(message, entry)
        return len(entries)

    def clear(self) -> None:
        """清空 active worker registry。

        :returns: ``None``。
        """

        with self._lock:
            self._entries.clear()


def _propagate_active_worker_cancel(
    message: ActiveCancelMessage,
    entry: _ActiveWorkerEntry,
) -> None:
    """通过统一 active entry 向 worker 传播取消。

    Host 注入 Engine 的 cancellation token 是本地执行的主取消通道；
    worker handle 的 ``on_cancel`` 只作为补充的 best-effort 边界 hook。

    :param message: 最小取消消息。
    :param entry: 已注册的 active worker entry。
    :returns: ``None``。
    """

    entry.cancellation_token.request_cancel(message.reason)
    try:
        entry.handle.on_cancel(message.reason)
    except Exception as exc:
        _LOGGER.warning(
            "active worker cancel hook failed; continuing attempt_id=%s execution_id=%s run_id=%s error_type=%s",
            message.attempt_id,
            message.execution_id,
            message.run_id,
            exc.__class__.__name__,
        )


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


@dataclass(frozen=True, slots=True)
class _ReadCompactionCancelReasonOperation:
    """读取 proactive compaction 是否已失效的 durable operation。

    :param run_id: 目标 Run id。
    :param session_id: 目标 Session id。
    :param expected_status: compaction request 写入时的 Run 状态。
    :param expected_input_event_sequence: compaction request 对应输入 cursor。
    """

    run_id: str
    session_id: str
    expected_status: RunStatus
    expected_input_event_sequence: int

    def __call__(self, transaction: HostTransaction) -> str | None:
        """读取 durable Run 并派生取消原因。

        :param transaction: Host durable read transaction。
        :returns: 取消原因；Run 仍满足 request 前置条件时为 ``None``。
        """

        run = read_run_by_id(transaction, self.run_id)
        if run is None:
            return _COMPACTION_CANCEL_REASON_RUN_MISSING
        session = read_session_by_id(transaction, self.session_id)
        if session is None:
            return _COMPACTION_CANCEL_REASON_SESSION_MISSING
        if session.status is not SessionStatus.OPEN or session.closed_at is not None:
            return _COMPACTION_CANCEL_REASON_SESSION_CLOSED
        if run.input_event_sequence != self.expected_input_event_sequence:
            return _COMPACTION_CANCEL_REASON_INPUT_CHANGED
        if run.status != self.expected_status:
            return f"{_COMPACTION_CANCEL_REASON_STATUS_PREFIX}:{run.status.value}"
        return None


class _DurableRunCancellationToken(CancellationToken):
    """通过 durable Run 状态观察 proactive compaction 是否应取消。

    proactive compaction 发生在 worker 启动前，尚没有 active worker registry
    可以接收 cancel。因此此 token 直接读取 Host durable Run 真源：只要 Run
    缺失、输入 cursor 改变或状态离开 request 写入时的期望状态，就让 Engine
    看到取消信号。
    """

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        run_id: str,
        session_id: str,
        expected_status: RunStatus,
        expected_input_event_sequence: int,
    ) -> None:
        """初始化 durable Run 观察 token。

        :param transaction_runner: Host durable transaction runner。
        :param run_id: 目标 Run id。
        :param session_id: 目标 Session id。
        :param expected_status: compaction request 写入时的 Run 状态。
        :param expected_input_event_sequence: compaction request 对应输入 cursor。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._run_id = run_id
        self._session_id = session_id
        self._expected_status = expected_status
        self._expected_input_event_sequence = expected_input_event_sequence

    def is_cancelled(self) -> bool:
        """返回 proactive compaction 是否已失效。

        :returns: durable Run 已离开原 request 前置条件，或 durable 状态不可读时
            返回 ``True``。
        """

        return self.cancel_reason() is not None

    def cancel_reason(self) -> str | None:
        """读取 durable Run 状态并返回取消原因。

        :returns: 取消原因；Run 仍满足 request 前置条件时为 ``None``。durable
            状态不可读时 fail-closed 返回 ``durable_unavailable``。
        """

        try:
            return self._transaction_runner.run_read(
                _ReadCompactionCancelReasonOperation(
                    run_id=self._run_id,
                    session_id=self._session_id,
                    expected_status=self._expected_status,
                    expected_input_event_sequence=(self._expected_input_event_sequence),
                )
            )
        except HostTransactionRetryExhaustedError:
            return _COMPACTION_CANCEL_REASON_DURABLE_UNAVAILABLE

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        durable 状态观察不到原始取消请求时间，因此这里不合成时间。

        :returns: 始终返回 ``None``。
        """

        return None


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
        transient_delta_publisher: HostTransientDeltaPublisher,
        terminal_post_commit_port: TerminalPostCommitPort,
        session_new_work_access: SessionNewWorkAccessPort,
        host_instance_identity: HostInstanceIdentity | None = None,
        active_registry: ActiveWorkerRegistry | None = None,
        projection_catchup_port: ProjectionCatchupPort | None = None,
        health_gate: HostExecutionHealthGate | None = None,
    ) -> None:
        """初始化 dispatch scheduler。

        :param transaction_runner: Host durable transaction runner。
        :param event_log_store: EventLog append primitive。
        :param local_execution: 本地执行配置。
        :param lane_controller: 已打开的 runtime lane controller。
        :param host_handle_id: Host handle 诊断 id。
        :param transient_delta_publisher: 已验证 Engine delta 的 Host 瞬态发布端口。
        :param terminal_post_commit_port: terminal commit 后的本地最终通知端口。
        :param session_new_work_access: Session 新工作资格的唯一只读端口。
        :param host_instance_identity: 当前 scheduler 的 Host instance 身份；
            不传时创建仅供测试直接构造使用的身份。
        :param active_registry: active worker registry；不传时创建 scheduler 私有 registry。
        :param projection_catchup_port: commit 后 best-effort projection catch-up 端口。
        :param health_gate: execution opener 与 scheduler critical task 共享的 health
            gate；直接测试未传时创建并立即置为 READY。
        :returns: ``None``。
        :raises ValueError: ``host_handle_id`` 为空时抛出。
        """

        self._initialize_inert(
            transaction_runner=transaction_runner,
            event_log_store=event_log_store,
            local_execution=local_execution,
            lane_controller=lane_controller,
            host_handle_id=host_handle_id,
            transient_delta_publisher=transient_delta_publisher,
            session_new_work_access=session_new_work_access,
            host_instance_identity=host_instance_identity,
            active_registry=active_registry,
            projection_catchup_port=projection_catchup_port,
            health_gate=health_gate,
        )
        self._bind_terminal_post_commit_port(terminal_post_commit_port)

    def _initialize_inert(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        event_log_store: EventLogStore,
        local_execution: HostLocalExecutionOptions,
        lane_controller: LaneController,
        host_handle_id: str,
        transient_delta_publisher: HostTransientDeltaPublisher,
        session_new_work_access: SessionNewWorkAccessPort,
        host_instance_identity: HostInstanceIdentity | None,
        active_registry: ActiveWorkerRegistry | None,
        projection_catchup_port: ProjectionCatchupPort | None,
        health_gate: HostExecutionHealthGate | None,
    ) -> None:
        """初始化不可运行且未绑定 terminal port 的 scheduler。

        :param transaction_runner: Host durable transaction runner。
        :param event_log_store: EventLog primitive。
        :param local_execution: 本地执行配置。
        :param lane_controller: 已打开的 runtime lane controller。
        :param host_handle_id: Host handle 诊断 id。
        :param transient_delta_publisher: Host 瞬态发布端口。
        :param session_new_work_access: Session 新工作资格的唯一只读端口。
        :param host_instance_identity: Host instance 身份。
        :param active_registry: active worker registry。
        :param projection_catchup_port: projection catch-up 端口。
        :param health_gate: execution health gate。
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
        self._transient_delta_publisher = transient_delta_publisher
        self._session_new_work_access = session_new_work_access
        self._host_instance_identity = (
            host_instance_identity
            if host_instance_identity is not None
            else _new_dispatch_host_instance_identity(host_handle_id)
        )
        self._active_registry = active_registry if active_registry is not None else ActiveWorkerRegistry()
        self._projection_catchup_port = projection_catchup_port
        self._terminal_post_commit_port: TerminalPostCommitPort | None = None
        if health_gate is None:
            health_gate = HostExecutionHealthGate()
            health_gate.mark_ready()
        self._health_gate = health_gate
        self._queue: asyncio.Queue[PendingDispatchRecord] = asyncio.Queue()
        self._promotion_queue: asyncio.Queue[str] = asyncio.Queue()
        self._pre_start_flights: dict[str, _PreStartGovernanceFlight] = {}
        self._promotion_pending_session_ids: set[str] = set()
        self._active_cancel_watchdog_event = asyncio.Event()
        self._active_cancel_watchdog_session_ids: set[str] = set()
        self._closed = False
        self._close_cleanup_done = False
        self._host_instance_stopping_marked = False
        self._lane_close_done = False
        self._host_instance_stopped_marked = False
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._drain_task: asyncio.Task[None] | None = None
        self._promotion_drain_task: asyncio.Task[None] | None = None
        self._owned_session_reconciliation_task: asyncio.Task[None] | None = None
        self._active_worker_cancel_reconciliation_task: asyncio.Task[None] | None = None
        self._active_cancel_watchdog_task: asyncio.Task[None] | None = None
        self._active_tasks: set[asyncio.Task[None] | asyncio.Task[bool]] = set()
        self._active_handles: set[LocalWorkerHandle] = set()

    def _bind_terminal_post_commit_port(
        self,
        terminal_post_commit_port: TerminalPostCommitPort,
    ) -> None:
        """构造期一次性绑定 terminal post-commit port。

        :param terminal_post_commit_port: 本 opener 唯一最终端口。
        :returns: ``None``。
        :raises RuntimeError: 重复绑定时抛出。
        """

        if self._terminal_post_commit_port is not None:
            raise RuntimeError("terminal post-commit port is already bound")
        self._terminal_post_commit_port = terminal_post_commit_port

    def _notify_terminal_post_commit(
        self,
        notice: TerminalPostCommitNotice,
    ) -> None:
        """向已绑定的最终端口发送 terminal commit 通知。

        :param notice: transaction-local exact terminal 通知。
        :returns: ``None``。
        :raises RuntimeError: 构造期尚未绑定时抛出。
        :raises Exception: 最终端口失败时透传。
        """

        self._required_terminal_post_commit_port().notify_terminal_post_commit(notice)

    def _required_terminal_post_commit_port(self) -> TerminalPostCommitPort:
        """返回构造期已绑定的 terminal post-commit port。

        :returns: 本 opener 唯一最终端口。
        :raises RuntimeError: 构造期尚未绑定时抛出。
        """

        terminal_post_commit_port = self._terminal_post_commit_port
        if terminal_post_commit_port is None:
            raise RuntimeError("terminal post-commit port is not bound")
        return terminal_post_commit_port

    @classmethod
    async def open(
        cls,
        *,
        transaction_runner: HostTransactionRunner,
        local_execution: HostLocalExecutionOptions,
        host_handle_id: str,
        transient_delta_publisher: HostTransientDeltaPublisher,
        terminal_post_commit_port_factory: _TerminalPostCommitPortFactory,
        session_new_work_access: SessionNewWorkAccessPort,
        active_registry: ActiveWorkerRegistry | None = None,
        projection_catchup_port: ProjectionCatchupPort | None = None,
        health_gate: HostExecutionHealthGate | None = None,
    ) -> "HostDispatchScheduler":
        """打开本地 dispatch scheduler。

        :param transaction_runner: Host durable transaction runner。
        :param local_execution: 本地执行配置。
        :param host_handle_id: Host handle 诊断 id。
        :param transient_delta_publisher: 已验证 Engine delta 的 Host 瞬态发布端口。
        :param terminal_post_commit_port_factory: 构造最终 terminal port 的内部工厂。
        :param session_new_work_access: Session 新工作资格的唯一只读端口。
        :param active_registry: active worker registry；不传时创建 scheduler 私有 registry。
        :param projection_catchup_port: commit 后 best-effort projection catch-up 端口。
        :param health_gate: execution opener 持有的共享 health gate。
        :returns: 已打开 scheduler。
        """

        if host_handle_id.strip() == "":
            raise ValueError("host_handle_id must be non-empty")
        host_identity = _new_dispatch_host_instance_identity(host_handle_id)
        lane_controller = await LaneController.open(
            [
                LaneConfig(
                    name=local_execution.lane_name,
                    capacity=local_execution.lane_capacity,
                    default_timeout_seconds=(local_execution.lane_default_timeout_seconds),
                    claim_ttl_seconds=local_execution.lane_claim_ttl_seconds,
                    heartbeat_interval_seconds=(local_execution.lane_heartbeat_interval_seconds),
                )
            ],
            coordinator=SQLiteLaneCoordinatorConfig(db_path=local_execution.lane_db_path),
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
            "dispatch.scheduler.opened host_handle_id=%s lane_name=%s lane_capacity=%s",
            host_handle_id,
            local_execution.lane_name,
            local_execution.lane_capacity,
        )
        scheduler = cls.__new__(cls)
        scheduler._initialize_inert(
            transaction_runner=transaction_runner,
            event_log_store=EventLogStore(),
            local_execution=local_execution,
            lane_controller=lane_controller,
            host_handle_id=host_handle_id,
            transient_delta_publisher=transient_delta_publisher,
            session_new_work_access=session_new_work_access,
            host_instance_identity=host_identity,
            active_registry=active_registry,
            projection_catchup_port=projection_catchup_port,
            health_gate=health_gate,
        )
        try:
            terminal_post_commit_port = terminal_post_commit_port_factory.create_terminal_post_commit_port(
                promotion_port=scheduler,
            )
            scheduler._bind_terminal_post_commit_port(terminal_post_commit_port)
            scheduler._start_host_instance_heartbeat()
            scheduler._start_active_cancel_watchdog_loop()
            scheduler._start_active_worker_cancel_reconciliation_loop()
            scheduler._start_owned_session_reconciliation_loop()
            return scheduler
        except BaseException:
            try:
                await terminal_post_commit_port_factory.close_after_failed_scheduler_open()
            finally:
                await scheduler.close()
            raise

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
        :raises HostApiError: scheduler 已关闭或 execution unavailable 时抛出。
        """

        self._raise_if_wake_unavailable(component=_CRITICAL_COMPONENT_DISPATCH)
        self._queue.put_nowait(record)
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.wake_dispatch run_id=%s attempt_id=%s execution_id=%s dispatch_record_id=%s queue_size=%s",
            record.run_id,
            record.attempt_id,
            record.execution_id,
            record.dispatch_record_id,
            self._queue.qsize(),
        )
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = self._start_critical_task(
                self._drain_loop,
                component=_CRITICAL_COMPONENT_DISPATCH,
            )

    def wake_queue_promotion(self, session_id: str) -> None:
        """唤醒同 Session 的 queued Run promotion。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        :raises HostApiError: scheduler lifecycle 不可用时抛出。
        """

        self._raise_if_wake_unavailable(component=_CRITICAL_COMPONENT_PROMOTION)
        eligibility = self._session_new_work_access.try_acquire_new_work_lease(session_id)
        if eligibility is None:
            _LOGGER.debug(
                "dispatch.queue_promotion.drop_ineligible session_id=%s",
                session_id,
            )
            return
        eligibility.release()
        flight = self._pre_start_flights.get(session_id)
        if flight is not None:
            flight.rerun_requested = True
            return
        if session_id in self._promotion_pending_session_ids:
            return
        self._promotion_pending_session_ids.add(session_id)
        self._promotion_queue.put_nowait(session_id)
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.queue_promotion.wake session_id=%s queue_size=%s",
            session_id,
            self._promotion_queue.qsize(),
        )
        if self._promotion_drain_task is None or self._promotion_drain_task.done():
            self._promotion_drain_task = self._start_critical_task(
                self._promotion_drain_loop,
                component=_CRITICAL_COMPONENT_PROMOTION,
            )

    def wake_active_cancel_watchdog(self, session_id: str) -> None:
        """唤醒 active cancel watchdog 收口目标 Session。

        :param session_id: 已提交 cancel command 的目标 Session id。
        :returns: ``None``。
        :raises ValueError: Session id 为空时抛出。
        :raises HostApiError: scheduler 已关闭或 execution unavailable 时抛出。
        """

        if session_id.strip() == "":
            raise ValueError("session_id must be non-empty")
        self._raise_if_wake_unavailable(component=_CRITICAL_COMPONENT_ACTIVE_CANCEL_WATCHDOG)
        self._active_cancel_watchdog_session_ids.add(session_id)
        self._active_cancel_watchdog_event.set()
        self._start_active_cancel_watchdog_loop()

    def tick_active_cancel_watchdog_for_session(
        self,
        session_id: str,
        now: datetime,
    ) -> ActiveCancelWatchdogTickResult:
        """同步收口目标 Session 已接受的 active cancel。

        :param session_id: fresh RW attachment 对应的目标 Session id。
        :param now: 本轮 watchdog 判定使用的 UTC aware 时间。
        :returns: 单次 target tick 摘要。
        :raises ValueError: Session id 为空或 ``now`` 非 UTC aware 时抛出。
        :raises HostTransactionRetryExhaustedError: durable 写事务重试耗尽时抛出。
        """

        if session_id.strip() == "":
            raise ValueError("session_id must be non-empty")
        return self._tick_active_cancel_watchdog(
            now=now,
            scope=_ActiveCancelWatchdogSessionScope(session_id=session_id),
        )

    def _tick_active_cancel_watchdog(
        self,
        *,
        now: datetime,
        scope: (_ActiveCancelWatchdogSessionScope | _ActiveCancelWatchdogOwnedTargetScope),
    ) -> ActiveCancelWatchdogTickResult:
        """在唯一 terminal producer 内执行一次 accepted-cancel closeout。

        :param now: 本轮 watchdog 判定使用的 UTC aware 时间。
        :param scope: target Session 或 exact execution-owner target。
        :returns: 单次 tick 摘要。
        :raises ValueError: ``now`` 不是 UTC aware 时间时抛出。
        :raises HostDurableError: exact target 的 cancel link 非法时抛出。
        :raises HostTransactionRetryExhaustedError: durable 写事务重试耗尽时抛出。
        """

        _validate_watchdog_now(now)

        def _operation(
            transaction: HostTransaction,
        ) -> _ActiveCancelWatchdogOperationResult:
            if isinstance(scope, _ActiveCancelWatchdogSessionScope):
                candidates, scanned, ignored = _read_active_cancel_watchdog_candidates(
                    transaction,
                    self._event_log_store,
                    session_id=scope.session_id,
                )
            else:
                candidates, scanned, ignored = _read_exact_owned_active_cancel_watchdog_candidate(
                    transaction,
                    self._event_log_store,
                    owner_host_instance_id=(self._host_instance_identity.host_instance_id),
                    target=scope.target,
                )
            eligible = 0
            terminal_notices: list[TerminalPostCommitNotice] = []
            for candidate in candidates:
                eligible += 1
                run_cancelled_event_id = _new_event_id(_EVENT_ID_RUN_CANCELLED_WATCHDOG_PREFIX)
                result = active_cancel_watchdog_closeout_in_transaction(
                    transaction,
                    self._event_log_store,
                    ActiveCancelWatchdogCloseoutInput(
                        run_id=candidate.run_id,
                        attempt_id=candidate.attempt_id,
                        attempt_cancelled_event_id=_new_event_id(_EVENT_ID_ATTEMPT_CANCELLED_WATCHDOG_PREFIX),
                        run_cancelled_event_id=run_cancelled_event_id,
                        occurred_at=now,
                        actor=_ACTIVE_CANCEL_WATCHDOG_ACTOR,
                        source=_ACTIVE_CANCEL_WATCHDOG_SOURCE,
                        cancel_requested_at=format_utc_timestamp(candidate.cancel_requested_at),
                        closed_out_at=now,
                        watchdog_owner=_ACTIVE_CANCEL_WATCHDOG_OWNER,
                        worker_lifecycle_signal=(_ACTIVE_CANCEL_WORKER_LIFECYCLE_SIGNAL),
                    ),
                )
                if result.status is StateMutationStatus.UPDATED and result.run is not None:
                    terminal_notices.append(
                        project_terminal_notice_from_exact_run_event(
                            result.run,
                            result.run_event,
                            wake_queue_promotion=(
                                result.run_event is not None and result.run_event.event_id == run_cancelled_event_id
                            ),
                        )
                    )
                else:
                    ignored += 1
            return _ActiveCancelWatchdogOperationResult(
                scanned=scanned,
                eligible=eligible,
                terminal_notices=tuple(
                    sorted(
                        terminal_notices,
                        key=lambda notice: notice.terminal_event_sequence,
                    )
                ),
                ignored=ignored,
            )

        operation_result = self._transaction_runner.run_write(_operation)
        if operation_result.terminal_notices:
            for notice in operation_result.terminal_notices:
                self._notify_terminal_post_commit(notice)
            catch_up_projection_best_effort(self._projection_catchup_port)
        return ActiveCancelWatchdogTickResult(
            scanned=operation_result.scanned,
            eligible=operation_result.eligible,
            closed=len(operation_result.terminal_notices),
            ignored=operation_result.ignored,
        )

    async def run_queue_promotion(self, session_id: str) -> None:
        """执行同 Session queued Run promotion。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        :raises RuntimeError: scheduler 已关闭时抛出。
        :raises Exception: sole flight durable governance 失败时透传。
        """

        if self._closed:
            raise RuntimeError("HostDispatchScheduler is closed")
        await self._signal_pre_start_governance(session_id)

    async def _signal_pre_start_governance(self, session_id: str) -> bool:
        """把一个合格 signal 合并到目标 Session 的 sole flight 并等待结果。

        signal 资格只来自当前 active READ_WRITE attachment；短暂取得的 lease
        仅用于确认当前 signal 资格，实际 durable pass 会取得自己的 fresh lease。

        :param session_id: 目标 Session id。
        :returns: 本次共享 flight 任一 pass 创建 stable dispatch 时返回 ``True``。
        :raises RuntimeError: scheduler 已关闭时抛出。
        :raises Exception: sole flight governance 失败时向所有 awaiter 透传。
        """

        if self._closed:
            raise RuntimeError("HostDispatchScheduler is closed")
        eligibility = self._session_new_work_access.try_acquire_new_work_lease(session_id)
        if eligibility is None:
            return False
        eligibility.release()
        flight = self._pre_start_flights.get(session_id)
        if flight is not None:
            flight.rerun_requested = True
            return await asyncio.shield(flight.task)
        task = asyncio.create_task(self._run_pre_start_governance_flight(session_id))
        flight = _PreStartGovernanceFlight(
            task=task,
            rerun_requested=False,
        )
        self._pre_start_flights[session_id] = flight
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)
        return await asyncio.shield(task)

    async def _run_pre_start_governance_flight(self, session_id: str) -> bool:
        """串行执行一个 Session 的全部 coalesced governance passes。

        每个 pass 前清除 level bit，并在该 pass 内取得 fresh work lease。pass
        返回后若 bit 再次置位，则从新的 durable truth 执行恰好一个后续 pass；
        检查 bit 与删除 flight entry 之间没有 ``await``。

        :param session_id: 目标 Session id。
        :returns: 任一 pass 创建 stable pending dispatch 时返回 ``True``。
        :raises RuntimeError: flight identity 丢失或 scheduler 已关闭时抛出。
        :raises Exception: governance 或 durable mutation 失败时透传。
        """

        flight = self._pre_start_flights.get(session_id)
        if flight is None:
            raise RuntimeError("pre-start governance flight identity is missing")
        dispatched = False
        try:
            while True:
                if self._closed:
                    raise RuntimeError("HostDispatchScheduler is closed")
                flight.rerun_requested = False
                work_lease = self._session_new_work_access.try_acquire_new_work_lease(session_id)
                if work_lease is None:
                    return dispatched
                try:
                    pass_dispatched = await self._run_queue_promotion_with_lease(
                        session_id,
                        work_lease=work_lease,
                    )
                finally:
                    work_lease.release()
                dispatched = dispatched or pass_dispatched
                current = self._pre_start_flights.get(session_id)
                if current is not flight:
                    raise RuntimeError("pre-start governance flight identity changed")
                if flight.rerun_requested:
                    continue
                del self._pre_start_flights[session_id]
                return dispatched
        finally:
            if self._pre_start_flights.get(session_id) is flight:
                del self._pre_start_flights[session_id]

    async def _run_queue_promotion_with_lease(
        self,
        session_id: str,
        *,
        work_lease: SessionWorkLease,
    ) -> bool:
        """在 caller 已持真实 work lease 时执行一次 promotion/governance。

        :param session_id: 目标 Session id。
        :param work_lease: 覆盖 pre-start 与 stable dispatch commit 的真实 lease。
        :returns: 本轮创建 stable pending dispatch 时返回 ``True``。
        :raises RuntimeError: scheduler 已关闭时抛出。
        :raises Exception: governance 或 durable mutation 失败时透传。
        """

        if self._closed:
            raise RuntimeError("HostDispatchScheduler is closed")
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.queue_promotion.start session_id=%s",
            session_id,
        )
        catch_up_projection_best_effort(self._projection_catchup_port)
        stage = await self._run_pre_start_governance(
            session_id,
            work_lease=work_lease,
        )
        pending_dispatch = stage.pending_dispatch
        if stage.compact_accepted is not None:
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "dispatch.queue_promotion.compact_accepted session_id=%s run_id=%s compacted_event_sequence=%s",
                session_id,
                stage.compact_accepted.run_id,
                stage.compact_accepted.compacted_event_sequence,
            )
            pending_dispatch = self._start_governed_after_compact(stage.compact_accepted)
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.queue_promotion.done session_id=%s dispatch_ready=%s compact_accepted=%s",
            session_id,
            pending_dispatch is not None,
            stage.compact_accepted is not None,
        )
        if pending_dispatch is not None:
            self.wake_dispatch(pending_dispatch)
            return True
        return False

    async def _run_pre_start_governance(
        self,
        session_id: str,
        *,
        work_lease: SessionWorkLease,
    ) -> _GovernanceStageResult:
        """执行一次 pre-start Context Governance。

        :param session_id: 目标 Session id。
        :param work_lease: caller 持有并覆盖本次事务外治理的真实 new-work lease。
        :returns: governance 阶段结果。
        """

        del work_lease
        self._catch_up_memory_projection_before_candidate(session_id)

        def _operation(transaction: HostTransaction) -> _GovernanceStageResult:
            run = _read_startable_run(transaction, session_id)
            if run is None:
                _LOGGER.debug(
                    "dispatch.governance.no_startable_run session_id=%s",
                    session_id,
                )
                return _GovernanceStageResult(pending_dispatch=None, compact_accepted=None)
            input_event = self._event_log_store.read_event_by_id(transaction, run.input_event_id)
            if input_event is None:
                _LOGGER.critical(
                    "dispatch.governance.input_missing session_id=%s run_id=%s input_event_id=%s",
                    run.session_id,
                    run.run_id,
                    run.input_event_id,
                )
                return _GovernanceStageResult(
                    pending_dispatch=None,
                    compact_accepted=None,
                    terminal_notice=self._fail_unstarted_in_transaction(
                        transaction,
                        run,
                        reason="input_event_missing",
                        error_code="context_governance_input_missing",
                        message="Input event is missing before dispatch",
                    ),
                )
            input_payload = event_payload_object(
                transaction,
                input_event,
                payload_label="USER_INPUT_ACCEPTED",
            )
            effective_decision = _effective_dispatch_decision_from_payload(
                input_payload,
            )
            tool_selection = self._candidate_tool_selection(
                run,
                effective_decision=effective_decision,
            )
            try:
                candidate = prepare_runner_call_candidate_in_transaction(
                    transaction,
                    self._event_log_store,
                    run=run,
                    current_input_event=input_event,
                    continuity=SessionContinuityView(
                        messages=(),
                        source_refs=(),
                    ),
                    policy_snapshot=effective_decision.policy_snapshot,
                    tool_schemas=tool_selection.tool_schemas,
                    disable_tools=tool_selection.disable_tools,
                    tool_execution_mode=tool_selection.execution_mode,
                    memory_projection_policy=(self._local_execution.memory_projection_policy),
                )
            except Exception as exc:
                _LOGGER.error(
                    "dispatch.governance.candidate_source_failed session_id=%s run_id=%s failure_reason=%s",
                    run.session_id,
                    run.run_id,
                    exc.__class__.__name__,
                    exc_info=True,
                )
                return _GovernanceStageResult(
                    pending_dispatch=None,
                    compact_accepted=None,
                    terminal_notice=self._fail_unstarted_in_transaction(
                        transaction,
                        run,
                        reason="runner_candidate_invalid",
                        error_code="runner_candidate_invalid",
                        message="Runner input candidate could not be frozen before dispatch",
                    ),
                )
            policy = self._local_execution.context_budget_policy
            if policy is None:
                _LOGGER.log(
                    VERBOSE_LOG_LEVEL,
                    "dispatch.governance.allow_without_budget session_id=%s run_id=%s run_status=%s",
                    run.session_id,
                    run.run_id,
                    run.status.value,
                )
                start_plan = NoBudgetDispatchStart(
                    start_input=self._new_governed_start_input(run),
                    stage=ContextSizingStage.ORDINARY,
                )
                return _GovernanceStageResult(
                    pending_dispatch=(
                        self._commit_dispatch_candidate_in_transaction(
                            transaction,
                            run,
                            candidate,
                            start_plan,
                        )
                    ),
                    compact_accepted=None,
                )
            estimate = estimate_prepared_runner_call_candidate(
                candidate,
                policy,
            )
            sizing = _build_candidate_sizing_result(
                transaction,
                self._event_log_store,
                stage=ContextSizingStage.ORDINARY,
                candidate=candidate,
                policy=policy,
                estimate=estimate,
            )
            decision = sizing.budget_decision
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "dispatch.governance.decision session_id=%s run_id=%s decision=%s policy_ref=%s",
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
                start_plan = BudgetedDispatchStart(
                    start_input=self._new_governed_start_input(run),
                    sizing=sizing,
                )
                return _GovernanceStageResult(
                    pending_dispatch=(
                        self._commit_dispatch_candidate_in_transaction(
                            transaction,
                            run,
                            candidate,
                            start_plan,
                        )
                    ),
                    compact_accepted=None,
                )
            append_context_budget_evaluated_in_transaction(
                transaction,
                self._event_log_store,
                session_id=run.session_id,
                run_id=run.run_id,
                attempt_id=None,
                execution_id=None,
                occurred_at=datetime.now(UTC),
                result=sizing,
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
                    operation_id=_precondition_compaction_operation_id(
                        failure_reason="hard_threshold_before_dispatch",
                        estimate=estimate,
                    ),
                    failure_reason="hard_threshold_before_dispatch",
                    attempt_count=0,
                    retry_repair_budget_exhausted=False,
                )
                return _GovernanceStageResult(
                    pending_dispatch=None,
                    compact_accepted=None,
                    terminal_notice=self._fail_unstarted_in_transaction(
                        transaction,
                        run,
                        reason=_GOVERNANCE_FAILURE_REASON,
                        error_code="context_hard_threshold_before_dispatch",
                        message="Context estimate exceeds hard threshold before dispatch",
                    ),
                )
            display_text = _display_text_from_input_event(
                transaction,
                input_event,
            )
            try:
                material_view = build_pre_dispatch_compact_material_view(
                    transaction,
                    self._event_log_store,
                    run=run,
                    current_display_text=display_text,
                )
            except Exception as exc:
                _LOGGER.error(
                    "dispatch.governance.material_source_failed session_id=%s run_id=%s failure_reason=%s",
                    run.session_id,
                    run.run_id,
                    exc.__class__.__name__,
                    exc_info=True,
                )
                self._append_compaction_failed_event(
                    transaction,
                    run=run,
                    estimate=estimate,
                    decision=decision,
                    operation_id=_precondition_compaction_operation_id(
                        failure_reason="material_source_failed",
                        estimate=estimate,
                    ),
                    failure_reason="material_source_failed",
                    attempt_count=0,
                    retry_repair_budget_exhausted=False,
                )
                return _GovernanceStageResult(
                    pending_dispatch=None,
                    compact_accepted=None,
                    terminal_notice=self._fail_unstarted_in_transaction(
                        transaction,
                        run,
                        reason=_GOVERNANCE_FAILURE_REASON,
                        error_code="context_compaction_failed",
                        message=("Context compaction material source failed before dispatch"),
                    ),
                )
            projection = read_proactive_compaction_projection(
                transaction,
                self._event_log_store,
                session_id=run.session_id,
                run_id=run.run_id,
            )
            if projection.decision is ProactiveCompactionDecision.USE_COMPACTED:
                compacted_sequence = projection.state.compacted_event_sequence
                if compacted_sequence is None:
                    raise RuntimeError("COMPACTED proactive state is missing sequence")
                return _GovernanceStageResult(
                    pending_dispatch=None,
                    compact_accepted=_GovernanceCompactAccepted(
                        run_id=run.run_id,
                        session_id=run.session_id,
                        expected_status=run.status,
                        compacted_event_sequence=compacted_sequence,
                    ),
                )
            if projection.decision is ProactiveCompactionDecision.USE_FAILED_FALLBACK:
                outcome = self._prepare_and_commit_start_in_transaction(
                    transaction,
                    run,
                    stage=ContextSizingStage.DISPATCH_FALLBACK,
                )
                return _GovernanceStageResult(
                    pending_dispatch=outcome.pending_dispatch,
                    compact_accepted=None,
                    terminal_notice=outcome.terminal_notice,
                )
            if projection.decision is ProactiveCompactionDecision.FAIL_EXISTING_OPERATION:
                operation_id = projection.state.operation_id
                if operation_id is None:
                    return _GovernanceStageResult(
                        pending_dispatch=None,
                        compact_accepted=None,
                        terminal_notice=self._fail_unstarted_in_transaction(
                            transaction,
                            run,
                            reason=_GOVERNANCE_FAILURE_REASON,
                            error_code=_PROACTIVE_INVALID_OR_EXHAUSTED_REASON,
                            message=("Proactive compaction history has no safe operation identity"),
                        ),
                    )
                terminal_commit = begin_compaction_terminal_commit_in_transaction(
                    transaction,
                    self._event_log_store,
                    operation_id=operation_id,
                    expected_trigger_source=(ContextCompactionTriggerSource.PROACTIVE),
                )
                if isinstance(terminal_commit, CompactionTerminalClosed):
                    if terminal_commit.disposition is CompactionOperationTerminalDisposition.INVALID_MULTIPLE:
                        raise HostDurableError(COMPACTION_TERMINAL_INVALID_MULTIPLE_ERROR)
                    _LOGGER.warning(
                        "dispatch.compact.terminal_closed_noop operation_id=%s "
                        "disposition=%s first_terminal_sequence=%s "
                        "first_terminal_type=%s",
                        operation_id,
                        terminal_commit.disposition.value,
                        terminal_commit.first_terminal_event_sequence,
                        terminal_commit.first_terminal_event_type,
                    )
                    return _GovernanceStageResult(
                        pending_dispatch=None,
                        compact_accepted=None,
                    )
                if (
                    projection.state.compacted_event_sequence is not None
                    or projection.state.failed_event_sequence is not None
                ):
                    return _GovernanceStageResult(
                        pending_dispatch=None,
                        compact_accepted=None,
                        terminal_notice=self._fail_unstarted_in_transaction(
                            transaction,
                            run,
                            reason=_GOVERNANCE_FAILURE_REASON,
                            error_code=_PROACTIVE_INVALID_OR_EXHAUSTED_REASON,
                            message=("Proactive compaction operation has invalid terminal history"),
                        ),
                    )
                fallback_outcome = self._append_compaction_failed_with_proactive_fallback(
                    transaction,
                    run=run,
                    material_view=material_view,
                    estimate=estimate,
                    decision=decision,
                    operation_id=operation_id,
                    failure_reason=_PROACTIVE_INVALID_OR_EXHAUSTED_REASON,
                    attempt_count=len(
                        frozenset(
                            (
                                *projection.state.prepared_attempt_numbers,
                                *projection.state.rejected_attempt_numbers,
                            )
                        )
                    ),
                    retry_repair_budget_exhausted=True,
                )
                if fallback_outcome is not None:
                    return _GovernanceStageResult(
                        pending_dispatch=fallback_outcome.pending_dispatch,
                        compact_accepted=None,
                        terminal_notice=fallback_outcome.terminal_notice,
                    )
                return _GovernanceStageResult(
                    pending_dispatch=None,
                    compact_accepted=None,
                    terminal_notice=self._fail_unstarted_in_transaction(
                        transaction,
                        run,
                        reason=_GOVERNANCE_FAILURE_REASON,
                        error_code=_PROACTIVE_INVALID_OR_EXHAUSTED_REASON,
                        message="Proactive compaction operation is invalid or exhausted",
                    ),
                )
            prepared = self._prepare_compact_before_dispatch(
                transaction,
                run=run,
                candidate=candidate,
                material_view=material_view,
                estimate=estimate,
                decision=decision,
                existing_state=(
                    projection.state if projection.decision is ProactiveCompactionDecision.RESUME_EXISTING else None
                ),
            )
            return prepared

        try:
            stage = self._transaction_runner.run_write(_operation)
        except _StartCandidateCasMissRollback:
            _LOGGER.debug(
                "dispatch.governance.start_precondition_miss_rolled_back session_id=%s",
                session_id,
            )
            return _GovernanceStageResult(
                pending_dispatch=None,
                compact_accepted=None,
            )
        if stage.terminal_notice is not None:
            self._notify_terminal_post_commit(stage.terminal_notice)
        if stage.compact_pending is None:
            return stage
        compacted = await self._execute_proactive_compaction(stage.compact_pending)
        if compacted.pending_dispatch is not None:
            return _GovernanceStageResult(
                pending_dispatch=compacted.pending_dispatch,
                compact_accepted=None,
            )
        if compacted.compacted_event_sequence is None:
            return _GovernanceStageResult(pending_dispatch=None, compact_accepted=None)
        pending = stage.compact_pending
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.governance.compact_accepted session_id=%s run_id=%s compacted_event_sequence=%s",
            pending.session_id,
            pending.run_id,
            compacted.compacted_event_sequence,
        )
        return _GovernanceStageResult(
            pending_dispatch=None,
            compact_accepted=_GovernanceCompactAccepted(
                run_id=pending.run_id,
                session_id=pending.session_id,
                expected_status=pending.expected_status,
                compacted_event_sequence=compacted.compacted_event_sequence,
            ),
        )

    async def _execute_proactive_compaction(
        self, pending: _GovernanceCompactPending
    ) -> _ProactiveCompactionExecutionResult:
        """在事务外执行 proactive compact，并在新事务内写入结果。

        :param pending: 已写 request fact 的 compact 摘要。
        :returns: accepted compact sequence 或 fallback pending dispatch。
        """

        compactor = self._local_execution.context_compactor
        if compactor is None:
            return _ProactiveCompactionExecutionResult(
                compacted_event_sequence=None,
                pending_dispatch=None,
            )
        cancellation_token = _DurableRunCancellationToken(
            transaction_runner=self._transaction_runner,
            run_id=pending.run_id,
            session_id=pending.session_id,
            expected_status=pending.expected_status,
            expected_input_event_sequence=pending.expected_input_event_sequence,
        )
        proposal_manifest_recorder = self._compactor_proposal_manifest_recorder()
        schedule = self._proactive_compaction_attempt_schedule(pending)
        execution_plans = schedule[pending.first_attempt_number - 1 :]
        if len(execution_plans) == 0:
            raise RuntimeError("proactive attempt schedule has no remaining attempt")
        accepted_request = execution_plans[0].request
        accepted_result: CompactionOperationResult | None = None
        accepted_attempt_number: int | None = None
        operation_rejected_attempts: list[CompactionAttemptRejected] = []
        budget_after_attempted_compact: int | None = None
        repair_feedback: CompactRepairFeedbackV4 | None = None
        for attempt_plan in execution_plans:
            attempt_feedback = _repair_feedback_for_request(
                repair_feedback,
                attempt_plan.request,
            )
            attempt_result = await run_compaction_attempt(
                request=attempt_plan.request,
                compactor=compactor,
                attempt_number=attempt_plan.attempt_number,
                max_attempt_number=pending.max_attempt_number,
                cancellation_token=cancellation_token,
                compaction_operation_id=pending.operation_id,
                proposal_manifest_recorder=proposal_manifest_recorder,
                memory_policy=self._local_execution.memory_projection_policy,
                repair_feedback=attempt_feedback,
            )
            accepted_request = attempt_plan.request
            accepted_result = attempt_result
            operation_rejected_attempts.extend(attempt_result.rejected_attempts)
            if attempt_result.budget_after_attempted_compact is not None:
                budget_after_attempted_compact = attempt_result.budget_after_attempted_compact
            if _compaction_result_accepted(attempt_result):
                accepted_attempt_number = attempt_result.accepted_attempt_number
                if attempt_plan.stage not in (
                    ProactiveCompactionAttemptStage.ROOT,
                    ProactiveCompactionAttemptStage.ROOT_REPAIR,
                ):
                    _LOGGER.log(
                        VERBOSE_LOG_LEVEL,
                        "dispatch.compact.recovery_accepted session_id=%s run_id=%s operation_id=%s reason=%s",
                        pending.session_id,
                        pending.run_id,
                        pending.operation_id,
                        attempt_plan.stage.value,
                    )
                break
            if _compaction_result_is_non_repairable(attempt_result):
                break
            repair_feedback = attempt_result.next_repair_feedback
            if cancellation_token.is_cancelled():
                break
        if accepted_result is None:
            raise RuntimeError("proactive attempt execution produced no result")
        rejected_attempts = tuple(operation_rejected_attempts)
        attempt_count = max(
            pending.first_attempt_number - 1,
            _highest_attempt_number(
                rejected_attempts,
                accepted_attempt_number=accepted_attempt_number,
            ),
        )

        def _operation(transaction: HostTransaction) -> _ProactiveCompactionExecutionResult:
            terminal_commit = begin_compaction_terminal_commit_in_transaction(
                transaction,
                self._event_log_store,
                operation_id=pending.operation_id,
                expected_trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            )
            if isinstance(terminal_commit, CompactionTerminalClosed):
                if terminal_commit.disposition is CompactionOperationTerminalDisposition.INVALID_MULTIPLE:
                    raise HostDurableError(COMPACTION_TERMINAL_INVALID_MULTIPLE_ERROR)
                _LOGGER.warning(
                    "dispatch.compact.late_terminal_noop operation_id=%s "
                    "disposition=%s first_terminal_sequence=%s "
                    "first_terminal_type=%s",
                    pending.operation_id,
                    terminal_commit.disposition.value,
                    terminal_commit.first_terminal_event_sequence,
                    terminal_commit.first_terminal_event_type,
                )
                return _ProactiveCompactionExecutionResult(
                    compacted_event_sequence=None,
                    pending_dispatch=None,
                )
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
                        operation_id=pending.operation_id,
                        failure_reason="stale_compaction_result",
                        attempt_count=attempt_count,
                        retry_repair_budget_exhausted=False,
                        budget_after_attempted_compact=budget_after_attempted_compact,
                    )
                return _ProactiveCompactionExecutionResult(
                    compacted_event_sequence=None,
                    pending_dispatch=None,
                )
            for rejected in rejected_attempts:
                self._append_compaction_attempt_rejected_event(
                    transaction,
                    run=run,
                    operation_id=pending.operation_id,
                    rejected=rejected,
                )
            if not _run_session_allows_proactive_compaction(transaction, run):
                self._append_compaction_failed_event(
                    transaction,
                    run=run,
                    estimate=pending.estimate,
                    decision=pending.decision,
                    operation_id=pending.operation_id,
                    failure_reason="stale_compaction_result",
                    attempt_count=attempt_count,
                    retry_repair_budget_exhausted=False,
                    budget_after_attempted_compact=budget_after_attempted_compact,
                )
                return _ProactiveCompactionExecutionResult(
                    compacted_event_sequence=None,
                    pending_dispatch=None,
                )
            if not _compaction_result_accepted(accepted_result):
                fallback_outcome = self._append_compaction_failed_with_proactive_fallback(
                    transaction,
                    run=run,
                    material_view=pending.material_view,
                    estimate=pending.estimate,
                    decision=pending.decision,
                    operation_id=pending.operation_id,
                    failure_reason=accepted_result.failure_reason or "compaction_failed",
                    attempt_count=attempt_count,
                    retry_repair_budget_exhausted=(attempt_count >= pending.max_attempt_number),
                    budget_after_attempted_compact=budget_after_attempted_compact,
                )
                if fallback_outcome is not None:
                    return _ProactiveCompactionExecutionResult(
                        compacted_event_sequence=None,
                        pending_dispatch=fallback_outcome.pending_dispatch,
                        terminal_notice=fallback_outcome.terminal_notice,
                    )
                return _ProactiveCompactionExecutionResult(
                    compacted_event_sequence=None,
                    pending_dispatch=None,
                    terminal_notice=self._fail_unstarted_in_transaction(
                        transaction,
                        run,
                        reason=_GOVERNANCE_FAILURE_REASON,
                        error_code="context_compaction_failed",
                        message="Context compaction failed before dispatch",
                    ),
                )
            if accepted_result.accepted_truth is None:
                raise RuntimeError("accepted compaction result is incomplete")
            compacted_sequence = self._append_compacted_event(
                transaction,
                run=run,
                estimate=pending.estimate,
                decision=pending.decision,
                request=accepted_request,
                accepted_truth=accepted_result.accepted_truth,
                operation_id=pending.operation_id,
                accepted_attempt_number=_required_accepted_attempt_number(accepted_attempt_number),
                budget_after_compact=(
                    accepted_result.budget_after_attempted_compact
                    if accepted_result.budget_after_attempted_compact is not None
                    else pending.estimate.estimated_input_tokens
                ),
                accepted_proposal_manifest_reference=(accepted_result.required_proposal_manifest_reference()),
                successful_response_identity=(accepted_result.required_successful_response_identity()),
            )
            return _ProactiveCompactionExecutionResult(
                compacted_event_sequence=compacted_sequence,
                pending_dispatch=None,
            )

        operation_result = self._transaction_runner.run_write(_operation)
        if operation_result.terminal_notice is not None:
            self._notify_terminal_post_commit(operation_result.terminal_notice)
        return operation_result

    def _proactive_compaction_attempt_schedule(
        self, pending: _GovernanceCompactPending
    ) -> tuple[ProactiveCompactionAttemptPlan, ...]:
        """构造 proactive root repair 与 tier 1-3 frozen attempt schedule。

        所有 stage 都基于 pending 中冻结的 source snapshot，不重新读取 EventLog；
        attempt number 到 stage/request 的映射由 proactive operation owner 统一分配。

        :param pending: 已冻结的 proactive compact pending 摘要。
        :returns: 长度精确等于 frozen max 的全局 attempt plans。
        :raises ValueError: pipeline tier 名称或 schedule 非法时抛出。
        """

        return self._build_proactive_compaction_attempt_schedule(
            source_snapshot=pending.source_snapshot,
            root_request_plan=pending.request_plan,
            max_attempt_number=pending.max_attempt_number,
        )

    def _build_proactive_compaction_attempt_schedule(
        self,
        *,
        source_snapshot: CompactPipelineSourceSnapshot,
        root_request_plan: CompactPipelineRequestPlan,
        max_attempt_number: int,
    ) -> tuple[ProactiveCompactionAttemptPlan, ...]:
        """由 frozen pipeline inputs 构造唯一 proactive attempt schedule。

        :param source_snapshot: request 使用的 frozen source snapshot。
        :param root_request_plan: normal/root request plan。
        :param max_attempt_number: operation frozen semantic budget。
        :returns: root repair 与可用 tier 的连续 attempt plans。
        :raises ValueError: tier 名称或 schedule 非法时抛出。
        """

        tier_requests = tuple(
            ProactiveCompactionTierRequest(
                stage=ProactiveCompactionAttemptStage(plan.tier_name),
                request=plan.request_plan.request,
            )
            for plan in build_tier_recovery_request_plans(
                source_snapshot=source_snapshot,
                root_request_plan=root_request_plan,
                memory_policy=self._local_execution.memory_projection_policy,
            )
        )
        return build_proactive_compaction_attempt_schedule(
            root_request=root_request_plan.request,
            tier_requests=tier_requests,
            max_attempt_number=max_attempt_number,
        )

    def _compactor_proposal_manifest_recorder(
        self,
    ) -> DurableCompactorProposalManifestRecorder:
        """构造 compactor proposal durable manifest recorder。

        :returns: durable manifest recorder。
        :raises Exception: 不主动抛出异常。
        """

        return DurableCompactorProposalManifestRecorder(
            transaction_runner=self._transaction_runner,
            event_log_store=self._event_log_store,
            event_source=_EVENT_SOURCE,
        )

    def _start_governed_after_compact(
        self,
        accepted: _GovernanceCompactAccepted,
    ) -> PendingDispatchRecord | None:
        """compact catch-up 后启动同一个未启动 Run。

        :param accepted: compact accepted 摘要。
        :returns: pending dispatch 摘要；状态已变化时返回 ``None``。
        """

        self._catch_up_memory_projection_before_candidate(accepted.session_id)

        def _operation(
            transaction: HostTransaction,
        ) -> _DispatchCandidateOutcome | None:
            run = read_run_by_id(transaction, accepted.run_id)
            if run is None or run.status != accepted.expected_status:
                _LOGGER.debug(
                    "dispatch.governance.start_after_compact_skipped session_id=%s run_id=%s expected_status=%s",
                    accepted.session_id,
                    accepted.run_id,
                    accepted.expected_status.value,
                )
                return None
            return self._prepare_and_commit_start_in_transaction(
                transaction,
                run,
                stage=ContextSizingStage.POST_COMPACT,
            )

        try:
            outcome = self._transaction_runner.run_write(_operation)
        except _StartCandidateCasMissRollback:
            _LOGGER.debug(
                "dispatch.governance.post_compact_start_precondition_miss session_id=%s run_id=%s",
                accepted.session_id,
                accepted.run_id,
            )
            return None
        if outcome is None:
            return None
        if outcome.terminal_notice is not None:
            self._notify_terminal_post_commit(outcome.terminal_notice)
        return outcome.pending_dispatch

    def _prepare_and_commit_start_in_transaction(
        self,
        transaction: HostTransaction,
        run: RunRow,
        *,
        stage: ContextSizingStage,
    ) -> _DispatchCandidateOutcome:
        """为 post-compact/fallback 冻结新 candidate 并按 decision 提交。

        :param transaction: 当前 write transaction。
        :param run: 当前 startable Run。
        :param stage: 本次 conservative sizing stage。
        :returns: allow 的 pending dispatch 或 hard closeout terminal notice。
        :raises _StartCandidateCasMissRollback: start precondition miss时抛出。
        :raises HostDurableError: candidate、manifest 或 transition integrity失败时抛出。
        """

        input_event = self._event_log_store.read_event_by_id(
            transaction,
            run.input_event_id,
        )
        if input_event is None:
            raise HostDurableError("dispatch candidate input event is missing")
        input_payload = event_payload_object(
            transaction,
            input_event,
            payload_label="USER_INPUT_ACCEPTED",
        )
        effective_decision = _effective_dispatch_decision_from_payload(
            input_payload,
        )
        tool_selection = self._candidate_tool_selection(
            run,
            effective_decision=effective_decision,
        )
        candidate = prepare_runner_call_candidate_in_transaction(
            transaction,
            self._event_log_store,
            run=run,
            current_input_event=input_event,
            continuity=SessionContinuityView(
                messages=(),
                source_refs=(),
            ),
            policy_snapshot=effective_decision.policy_snapshot,
            tool_schemas=tool_selection.tool_schemas,
            disable_tools=tool_selection.disable_tools,
            tool_execution_mode=tool_selection.execution_mode,
            memory_projection_policy=(self._local_execution.memory_projection_policy),
        )
        policy = self._local_execution.context_budget_policy
        if policy is None:
            return _DispatchCandidateOutcome(
                pending_dispatch=self._commit_dispatch_candidate_in_transaction(
                    transaction,
                    run,
                    candidate,
                    NoBudgetDispatchStart(
                        start_input=self._new_governed_start_input(run),
                        stage=stage,
                    ),
                ),
                terminal_notice=None,
            )
        estimate = estimate_prepared_runner_call_candidate(candidate, policy)
        sizing = _build_candidate_sizing_result(
            transaction,
            self._event_log_store,
            stage=stage,
            candidate=candidate,
            policy=policy,
            estimate=estimate,
        )
        if sizing.budget_decision is ContextBudgetDecision.ALLOW_DISPATCH:
            return _DispatchCandidateOutcome(
                pending_dispatch=self._commit_dispatch_candidate_in_transaction(
                    transaction,
                    run,
                    candidate,
                    BudgetedDispatchStart(
                        start_input=self._new_governed_start_input(run),
                        sizing=sizing,
                    ),
                ),
                terminal_notice=None,
            )
        append_context_budget_evaluated_in_transaction(
            transaction,
            self._event_log_store,
            session_id=run.session_id,
            run_id=run.run_id,
            attempt_id=None,
            execution_id=None,
            occurred_at=datetime.now(UTC),
            result=sizing,
        )
        error_code, message = _hard_threshold_closeout(stage)
        terminal_notice = self._fail_unstarted_in_transaction(
            transaction,
            run,
            reason=_GOVERNANCE_FAILURE_REASON,
            error_code=error_code,
            message=message,
        )
        if terminal_notice is None:
            raise _StartCandidateCasMissRollback()
        return _DispatchCandidateOutcome(
            pending_dispatch=None,
            terminal_notice=terminal_notice,
        )

    def _new_governed_start_input(
        self,
        run: RunRow,
    ) -> StartGovernedRunInput:
        """仅在 allow decision 后生成唯一 governed start identity。

        :param run: 当前 startable Run。
        :returns: caller-owned exact start input。
        :raises Exception: 不主动抛出异常。
        """

        return StartGovernedRunInput(
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
                RunStartReason.INITIAL if run.status is RunStatus.ACCEPTED else RunStartReason.QUEUE_PROMOTION
            ),
            worker_kind=WorkerKind.LOCAL,
            owner_host_instance_id=(self._host_instance_identity.host_instance_id),
        )

    def _candidate_tool_selection(
        self,
        run: RunRow,
        *,
        effective_decision: _EffectiveDispatchDecision,
    ) -> _CandidateToolSelection:
        """在 Attempt identity 生成前冻结 candidate 的工具 schema。

        :param run: 当前 startable Run。
        :param effective_decision: admission 已冻结的执行与工具选择。
        :returns: identity-free selected tool snapshot。
        :raises ValueError: effective tool bundle 配置非法时抛出。
        """

        policy_snapshot = effective_decision.policy_snapshot
        tooling_options = (
            None if run.source_run_relation is SourceRunRelation.REPLAY else self._local_execution.tooling_options
        )
        selected_business_tool_names = validate_effective_tool_facts_runtime(
            effective_decision.effective_tool_facts,
            tooling_options=tooling_options,
        )
        if tooling_options is None or not policy_snapshot.agent_policy.allow_tool_calls:
            return _CandidateToolSelection(
                tool_schemas=(),
                disable_tools=True,
                execution_mode=(
                    ToolExecutionMode.NO_TOOL_REPLAY
                    if run.source_run_relation is SourceRunRelation.REPLAY
                    else ToolExecutionMode.NO_TOOL_DISABLED
                ),
            )
        effective_bundle = EffectiveToolBundleBuilder().build(
            EffectiveToolBundleBuildRequest(
                business_tool_bundle=tooling_options.business_tool_bundle,
                source_refs=tooling_options.source_refs,
                framework_tool_policy=tooling_options.framework_tool_policy,
                policy_snapshot_digest=_policy_snapshot_digest(policy_snapshot),
                selected_business_tool_names=selected_business_tool_names,
                enable_truncation_manager=(self._local_execution.enable_truncation_manager),
            )
        )
        return _CandidateToolSelection(
            tool_schemas=effective_bundle.tool_schemas,
            disable_tools=False,
            execution_mode=ToolExecutionMode.TOOL_ENABLED,
        )

    def _catch_up_memory_projection_before_candidate(
        self,
        session_id: str,
    ) -> None:
        """在 candidate transaction 前追平该 Session 的 memory projection。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        :raises HostDurableError: memory projection 未覆盖当前 durable cursor 时抛出。
        """

        def _required_cursor(transaction: HostTransaction) -> int:
            row = transaction.fetchone(
                f"""
                SELECT COALESCE(MAX(event_sequence), 0) AS event_sequence
                FROM {TABLE_EVENT_LOG}
                WHERE session_id = ?
                """,
                (session_id,),
            )
            if row is None:
                return 0
            value = row.get("event_sequence")
            if not isinstance(value, int) or value < 0:
                raise HostDurableError("candidate memory projection cursor is invalid")
            return value

        required_event_sequence = self._transaction_runner.run_read(_required_cursor)
        result = catch_up_conversation_memory_projection(
            self._transaction_runner,
            policy=self._local_execution.memory_projection_policy,
            batch_size=(self._local_execution.memory_projection_catchup_batch_size),
            max_event_sequence=required_event_sequence,
        )
        if result.failures == 0 and result.target_reached:
            return
        raise HostDurableError(
            "candidate memory projection did not reach required cursor: "
            f"session_id={session_id}, required_event_sequence="
            f"{required_event_sequence}, finished_cursor={result.finished_cursor}, "
            f"stop_reason={result.stop_reason.value}"
        )

    def _commit_dispatch_candidate_in_transaction(
        self,
        transaction: HostTransaction,
        run: RunRow,
        candidate: PreparedRunnerCallCandidate,
        plan: DispatchStartPlan,
    ) -> PendingDispatchRecord:
        """按 manifest-before-start 顺序提交一个 allow candidate。

        :param transaction: 调用方 write transaction。
        :param run: 当前 startable Run。
        :param candidate: identity-free frozen candidate。
        :param plan: budgeted/no-budget closed start plan。
        :returns: exact pending dispatch。
        :raises _StartCandidateCasMissRollback: start precondition miss或完整 rows
            缺失时触发整笔 rollback。
        :raises HostDurableError: identity/digest/CAS integrity failure时传播。
        """

        if isinstance(plan, BudgetedDispatchStart):
            start_input = plan.start_input
            sizing = plan.sizing
            if (
                sizing.candidate_input_digest != candidate.input_snapshot_digest
                or sizing.candidate_input_cursor != candidate.candidate_input_cursor
            ):
                raise HostDurableError("dispatch sizing does not match frozen candidate")
            sizing_snapshot = complete_runner_call_sizing_snapshot(
                sizing_stage=sizing.stage,
                estimator_id=sizing.estimator_contract.estimator_id,
                estimator_version=(sizing.estimator_contract.estimator_version),
                estimator_digest=sizing.estimator_digest,
                conservative_input_tokens=(sizing.conservative_input_tokens),
                context_window_size=sizing.context_window_size,
                provider=candidate.policy_snapshot.runner_spec.provider,
                model=candidate.policy_snapshot.runner_spec.model,
                request_semantics_digest=(candidate.request_semantics_digest),
                input_snapshot_digest=candidate.input_snapshot_digest,
                policy_ref=sizing.policy_ref,
                policy_snapshot_digest=sizing.policy_snapshot_digest,
            )
        else:
            start_input = plan.start_input
            sizing_snapshot = unavailable_runner_call_sizing_snapshot(
                RunnerCallSizingUnavailableReason.CONTEXT_POLICY_UNAVAILABLE,
                sizing_stage=plan.stage,
            )
        record_prepared_runner_call_candidate_in_transaction(
            transaction,
            self._event_log_store,
            PayloadStore(),
            run=run,
            attempt_id=start_input.attempt_id,
            execution_id=start_input.execution_id,
            occurred_at=start_input.occurred_at,
            candidate=candidate,
            sizing_snapshot=sizing_snapshot,
        )
        if isinstance(plan, BudgetedDispatchStart):
            append_context_budget_evaluated_in_transaction(
                transaction,
                self._event_log_store,
                session_id=run.session_id,
                run_id=run.run_id,
                attempt_id=start_input.attempt_id,
                execution_id=start_input.execution_id,
                occurred_at=start_input.occurred_at,
                result=plan.sizing,
            )
        result = start_governed_run_with_starting_attempt_in_transaction(
            transaction,
            self._event_log_store,
            start_input,
        )
        if result.status is not StateMutationStatus.UPDATED:
            raise _StartCandidateCasMissRollback()
        if result.run is None or result.attempt is None or result.dispatch_record is None:
            raise _StartCandidateCasMissRollback()
        dispatch_record = result.dispatch_record
        if (
            result.run.current_attempt_id != start_input.attempt_id
            or result.attempt.attempt_id != start_input.attempt_id
            or result.attempt.execution_id != start_input.execution_id
            or dispatch_record.attempt_id != start_input.attempt_id
            or dispatch_record.execution_id != start_input.execution_id
            or dispatch_record.dispatch_record_id != start_input.dispatch_record_id
        ):
            raise HostDurableError("governed start rows do not match caller-owned identity")
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.start_governed.committed session_id=%s run_id=%s "
            "attempt_id=%s execution_id=%s dispatch_record_id=%s",
            run.session_id,
            dispatch_record.run_id,
            dispatch_record.attempt_id,
            dispatch_record.execution_id,
            dispatch_record.dispatch_record_id,
        )
        return PendingDispatchRecord(
            dispatch_record_id=dispatch_record.dispatch_record_id,
            run_id=dispatch_record.run_id,
            attempt_id=dispatch_record.attempt_id,
            execution_id=dispatch_record.execution_id,
            execution_target=dispatch_record.execution_target,
            worker_kind=dispatch_record.worker_kind,
        )

    def _fail_unstarted_in_transaction(
        self,
        transaction: HostTransaction,
        run: RunRow,
        *,
        reason: str,
        error_code: str,
        message: str,
    ) -> TerminalPostCommitNotice | None:
        """在当前事务内 attempt-free 失败收口 Run。

        :param transaction: 当前 Host transaction。
        :param run: 待收口 Run。
        :param reason: 失败原因。
        :param error_code: 错误码。
        :param message: 失败消息。
        :returns: transition 成功时返回不唤醒 promotion 的精确 terminal notice。
        """

        result = fail_unstarted_run_in_transaction(
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
        if result.status is not StateMutationStatus.UPDATED or result.run is None:
            return None
        return project_terminal_notice_from_exact_run_event(
            result.run,
            result.run_event,
            wake_queue_promotion=False,
        )

    def _prepare_compact_before_dispatch(
        self,
        transaction: HostTransaction,
        *,
        run: RunRow,
        candidate: PreparedRunnerCallCandidate,
        material_view: PreDispatchCompactMaterialView,
        estimate: BudgetEstimate,
        decision: ContextBudgetDecision,
        existing_state: ProactiveCompactionState | None,
    ) -> _GovernanceStageResult:
        """在当前事务内写入 proactive compact request 并冻结请求。

        :param transaction: 当前 Host transaction。
        :param run: 待 compact Run。
        :param candidate: 本轮已冻结的 ordinary runner candidate。
        :param material_view: 已冻结的 EventLog-backed compact material view。
        :param estimate: compact 前预算估算。
        :param decision: 触发 compact 的预算决策。
        :param existing_state: 可恢复的既有 INCOMPLETE operation；新 operation
            时为 ``None``。
        :returns: 待事务外执行的 compact 或 fallback dispatch / fail closed 结果。
        """

        compactor = self._local_execution.context_compactor
        artifact_root = self._local_execution.compact_artifact_root
        policy = self._local_execution.context_budget_policy
        if policy is None:
            raise RuntimeError("proactive compaction requires context budget policy")
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
        source_snapshot = compact_pipeline_source_snapshot_from_pre_dispatch_view(
            trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            run=run,
            material_view=material_view,
        )
        memory_policy = self._local_execution.memory_projection_policy
        request_plan = build_normal_compact_request_plan(
            source_snapshot=source_snapshot,
            selection_policy_digest=digest_memory_projection_policy(memory_policy),
            memory_policy=memory_policy,
            budget_before_compact=estimate,
            selected_recent_window_turn_floor=(memory_policy.selected_recent_window_turn_floor),
        )
        request = request_plan.request
        compact_input = request.compact_input
        if existing_state is None and len(compact_input.source_boundary) == 0:
            fallback_sizing = _build_candidate_sizing_result(
                transaction,
                self._event_log_store,
                stage=ContextSizingStage.DISPATCH_FALLBACK,
                candidate=candidate,
                policy=policy,
                estimate=estimate,
            )
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "dispatch.compact.no_citable_boundary session_id=%s run_id=%s",
                run.session_id,
                run.run_id,
            )
            return _GovernanceStageResult(
                pending_dispatch=self._commit_dispatch_candidate_in_transaction(
                    transaction,
                    run,
                    candidate,
                    BudgetedDispatchStart(
                        start_input=self._new_governed_start_input(run),
                        sizing=fallback_sizing,
                    ),
                ),
                compact_accepted=None,
            )
        if existing_state is None:
            operation_id = _new_event_id(_EVENT_ID_CONTEXT_COMPACTION_REQUESTED_PREFIX)
            self._append_compaction_requested_event(
                transaction,
                operation_id=operation_id,
                run=run,
                estimate=estimate,
                decision=decision,
                source_snapshot=source_snapshot,
                max_attempt_number=(policy.max_compaction_attempts_per_operation),
            )
            first_attempt_number = 1
            max_attempt_number = policy.max_compaction_attempts_per_operation
        else:
            operation_id = _required_proactive_operation_id(existing_state)
            first_attempt_number = _required_proactive_next_attempt(existing_state)
            max_attempt_number = _required_proactive_max_attempt(existing_state)
            try:
                _validate_proactive_resume_snapshot(
                    existing_state,
                    source_snapshot=source_snapshot,
                    attempt_schedule=(
                        self._build_proactive_compaction_attempt_schedule(
                            source_snapshot=source_snapshot,
                            root_request_plan=request_plan,
                            max_attempt_number=max_attempt_number,
                        )
                    ),
                    expected_input_event_sequence=run.input_event_sequence,
                )
            except RuntimeError:
                attempt_count = len(
                    frozenset(
                        (
                            *existing_state.prepared_attempt_numbers,
                            *existing_state.rejected_attempt_numbers,
                        )
                    )
                )
                terminal_commit = begin_compaction_terminal_commit_in_transaction(
                    transaction,
                    self._event_log_store,
                    operation_id=operation_id,
                    expected_trigger_source=(ContextCompactionTriggerSource.PROACTIVE),
                )
                if isinstance(terminal_commit, CompactionTerminalClosed):
                    if terminal_commit.disposition is CompactionOperationTerminalDisposition.INVALID_MULTIPLE:
                        raise HostDurableError(COMPACTION_TERMINAL_INVALID_MULTIPLE_ERROR)
                    _LOGGER.warning(
                        "dispatch.compact.resume_terminal_closed_noop "
                        "operation_id=%s disposition=%s "
                        "first_terminal_sequence=%s first_terminal_type=%s",
                        operation_id,
                        terminal_commit.disposition.value,
                        terminal_commit.first_terminal_event_sequence,
                        terminal_commit.first_terminal_event_type,
                    )
                    return _GovernanceStageResult(
                        pending_dispatch=None,
                        compact_accepted=None,
                    )
                fallback_outcome = self._append_compaction_failed_with_proactive_fallback(
                    transaction,
                    run=run,
                    material_view=material_view,
                    estimate=estimate,
                    decision=decision,
                    operation_id=operation_id,
                    failure_reason=_PROACTIVE_INVALID_OR_EXHAUSTED_REASON,
                    attempt_count=attempt_count,
                    retry_repair_budget_exhausted=True,
                )
                if fallback_outcome is not None:
                    return _GovernanceStageResult(
                        pending_dispatch=fallback_outcome.pending_dispatch,
                        compact_accepted=None,
                        terminal_notice=fallback_outcome.terminal_notice,
                    )
                return _GovernanceStageResult(
                    pending_dispatch=None,
                    compact_accepted=None,
                    terminal_notice=self._fail_unstarted_in_transaction(
                        transaction,
                        run,
                        reason=_GOVERNANCE_FAILURE_REASON,
                        error_code=_PROACTIVE_INVALID_OR_EXHAUSTED_REASON,
                        message=("Proactive compaction resume snapshot is invalid"),
                    ),
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
            terminal_commit = begin_compaction_terminal_commit_in_transaction(
                transaction,
                self._event_log_store,
                operation_id=operation_id,
                expected_trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            )
            if isinstance(terminal_commit, CompactionTerminalClosed):
                if terminal_commit.disposition is CompactionOperationTerminalDisposition.INVALID_MULTIPLE:
                    raise HostDurableError(COMPACTION_TERMINAL_INVALID_MULTIPLE_ERROR)
                _LOGGER.warning(
                    "dispatch.compact.missing_compactor_terminal_closed_noop "
                    "operation_id=%s disposition=%s "
                    "first_terminal_sequence=%s first_terminal_type=%s",
                    operation_id,
                    terminal_commit.disposition.value,
                    terminal_commit.first_terminal_event_sequence,
                    terminal_commit.first_terminal_event_type,
                )
                return _GovernanceStageResult(
                    pending_dispatch=None,
                    compact_accepted=None,
                )
            fallback_outcome = self._append_compaction_failed_with_proactive_fallback(
                transaction,
                run=run,
                material_view=material_view,
                estimate=estimate,
                decision=decision,
                operation_id=operation_id,
                failure_reason="compactor_or_artifact_store_missing",
                attempt_count=0,
                retry_repair_budget_exhausted=False,
            )
            if fallback_outcome is not None:
                return _GovernanceStageResult(
                    pending_dispatch=fallback_outcome.pending_dispatch,
                    compact_accepted=None,
                    terminal_notice=fallback_outcome.terminal_notice,
                )
            return _GovernanceStageResult(
                pending_dispatch=None,
                compact_accepted=None,
                terminal_notice=self._fail_unstarted_in_transaction(
                    transaction,
                    run,
                    reason=_GOVERNANCE_FAILURE_REASON,
                    error_code="context_compactor_missing",
                    message="Context compactor or artifact store is not configured",
                ),
            )
        return _GovernanceStageResult(
            pending_dispatch=None,
            compact_accepted=None,
            compact_pending=_GovernanceCompactPending(
                run_id=run.run_id,
                session_id=run.session_id,
                expected_status=run.status,
                expected_input_event_sequence=run.input_event_sequence,
                request=request,
                source_snapshot=source_snapshot,
                request_plan=request_plan,
                material_view=material_view,
                operation_id=operation_id,
                estimate=estimate,
                decision=decision,
                first_attempt_number=first_attempt_number,
                max_attempt_number=max_attempt_number,
            ),
        )

    def _append_compacted_event(
        self,
        transaction: HostTransaction,
        *,
        run: RunRow,
        estimate: BudgetEstimate,
        decision: ContextBudgetDecision,
        request: CompactionRequest,
        accepted_truth: CompactAcceptedTruthV4,
        operation_id: str,
        accepted_attempt_number: int,
        budget_after_compact: int,
        accepted_proposal_manifest_reference: CompactorProposalManifestReference,
        successful_response_identity: SuccessfulRunnerResponseIdentity,
    ) -> int:
        """写入 accepted compact artifact 与 ``CONTEXT_COMPACTED`` fact。

        :param transaction: 当前 Host transaction。
        :param run: 目标 Run。
        :param estimate: compact 前预算估算。
        :param decision: 触发 compact 的预算决策。
        :param request: Host compaction request。
        :param accepted_truth: Context Governance final accepted truth。
        :param operation_id: requested event id。
        :param accepted_attempt_number: accepted operation attempt number。
        :param budget_after_compact: Host 估算的 compact 后预算。
        :param accepted_proposal_manifest_reference: accepted proposal 对应的
            typed manifest reference。
        :param successful_response_identity: accepted candidate 对应的实际成功
            Runner call 身份。
        :returns: ``CONTEXT_COMPACTED`` event sequence。
        """

        artifact_root = self._local_execution.compact_artifact_root
        if artifact_root is None:
            raise RuntimeError("compact artifact root is missing")
        policy_digest = sha256_digest_json(
            {
                "policy_ref": (
                    self._local_execution.context_budget_policy.policy_ref
                    if self._local_execution.context_budget_policy is not None
                    else "none"
                )
            }
        )
        artifact_ref = LocalArtifactStore(
            artifact_root,
            create_artifact_root=(self._local_execution.compact_artifact_create_parent_dirs),
        ).write_artifact_bytes(
            canonical_json_dumps(
                compact_artifact_json_vnext(
                    request=request,
                    accepted_truth=accepted_truth,
                    policy_digest=policy_digest,
                    budget_after_compact=budget_after_compact,
                )
            ).encode("utf-8")
        )
        payload_ref = compact_artifact_payload_ref(artifact_ref.artifact_digest)
        descriptor = PayloadStore().write_payload_descriptor_for_artifact(
            transaction,
            payload_ref,
            artifact_ref,
            COMPACT_ARTIFACT_MEDIA_TYPE_VNEXT,
            compact_artifact_descriptor_metadata_vnext(
                request=request,
                accepted_truth=accepted_truth,
                artifact_digest=artifact_ref.artifact_digest,
                policy_digest=policy_digest,
            ),
        )
        event_id = _new_event_id(_EVENT_ID_CONTEXT_COMPACTED_PREFIX)
        compacted_payload = build_context_compacted_payload(
            operation_id=operation_id,
            accepted_attempt_number=accepted_attempt_number,
            compact_artifact_ref=descriptor.payload_ref,
            compact_artifact_digest=artifact_ref.artifact_digest,
            accepted_truth=accepted_truth,
            budget_after_compact=budget_after_compact,
            prompt_local_label_mapping_refs=prompt_local_label_mapping_refs(request),
            projection_signal=COMPACT_PROJECTION_SIGNAL_MEMORY_CATCHUP,
            accepted_proposal_manifest_reference=(accepted_proposal_manifest_reference),
            successful_response_identity=successful_response_identity,
        )
        payload_storage = store_context_compacted_payload(
            transaction,
            PayloadStore(),
            event_id=event_id,
            payload=compacted_payload,
        )
        event = self._event_log_store.append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
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
                payload_json=payload_storage.event_payload,
                payload_ref=payload_storage.payload_ref,
                payload_digest=payload_storage.payload_digest,
            ),
        ).row
        return event.event_sequence

    def _append_compaction_requested_event(
        self,
        transaction: HostTransaction,
        *,
        operation_id: str,
        run: RunRow,
        estimate: BudgetEstimate,
        decision: ContextBudgetDecision,
        source_snapshot: CompactPipelineSourceSnapshot,
        max_attempt_number: int,
    ) -> EventLogRow:
        """追加 proactive ``CONTEXT_COMPACTION_REQUESTED``。

        :param transaction: 当前 Host transaction。
        :param operation_id: 预生成且同时作为 request event id 的 operation id。
        :param run: 目标 Run。
        :param estimate: budget estimate。
        :param decision: budget decision。
        :param source_snapshot: request 冻结的 material snapshot。
        :param max_attempt_number: operation 冻结的全局 attempt 上限。
        :returns: 已写入的 request EventLog row。
        """

        return self._event_log_store.append_event(
            transaction,
            EventLogAppendRequest(
                event_id=operation_id,
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
                    operation_id=operation_id,
                    max_compaction_attempts_per_operation=max_attempt_number,
                    trigger_source=ContextCompactionTriggerSource.PROACTIVE,
                    budget_reason=decision.value,
                    budget_snapshot_ref=estimate.estimator_digest,
                    input_snapshot_cursor=run.input_event_sequence,
                    estimator_digest=estimate.estimator_digest,
                    policy_ref=(
                        self._local_execution.context_budget_policy.policy_ref
                        if self._local_execution.context_budget_policy is not None
                        else "none"
                    ),
                    provider_request_id=None,
                    provider_error_ref=None,
                    attempt_id=None,
                    execution_id=None,
                    client_correlation_id=None,
                    frozen_material_list_digest=(source_snapshot.material_view_digest),
                    frozen_material_refs=source_snapshot.material_source_refs,
                ),
                payload_ref=None,
                payload_digest=None,
            ),
        ).row

    def _append_compaction_failed_with_proactive_fallback(
        self,
        transaction: HostTransaction,
        *,
        run: RunRow,
        material_view: PreDispatchCompactMaterialView,
        estimate: BudgetEstimate,
        decision: ContextBudgetDecision,
        operation_id: str,
        failure_reason: str,
        attempt_count: int,
        retry_repair_budget_exhausted: bool,
        budget_after_attempted_compact: int | None = None,
    ) -> _DispatchCandidateOutcome | None:
        """写入 proactive failed event，并按 recent-window fallback 决定是否启动。

        :param transaction: 当前 Host transaction。
        :param run: 目标 Run。
        :param material_view: compact request 使用的可信冻结 material view。
        :param estimate: compact 前预算估算。
        :param decision: 触发 compact 的预算决策。
        :param operation_id: compact operation id。
        :param failure_reason: compact failure reason。
        :param attempt_count: operation 内已拒绝 proposal attempt 数。
        :param retry_repair_budget_exhausted: retry / repair 预算是否耗尽。
        :param budget_after_attempted_compact: compact 尝试后预算；未知为 ``None``。
        :returns: fallback action为dispatch时返回封闭candidate outcome；否则返回
            ``None``。
        """

        policy = self._local_execution.context_budget_policy
        if policy is None:
            self._append_compaction_failed_event(
                transaction,
                run=run,
                estimate=estimate,
                decision=decision,
                operation_id=operation_id,
                failure_reason=failure_reason,
                attempt_count=attempt_count,
                retry_repair_budget_exhausted=retry_repair_budget_exhausted,
                budget_after_attempted_compact=budget_after_attempted_compact,
            )
            return None
        source_snapshot = compact_pipeline_source_snapshot_from_pre_dispatch_view(
            trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            run=run,
            material_view=material_view,
        )
        fallback_decision = build_fallback_decision_input(
            source_snapshot=source_snapshot,
            context_policy=policy,
            memory_policy=self._local_execution.memory_projection_policy,
            operation_id=operation_id,
            failure_reason=failure_reason,
            attempt_count=attempt_count,
            retry_repair_budget_exhausted=retry_repair_budget_exhausted,
            budget_after_attempted_compact=budget_after_attempted_compact,
        )
        failed_input = fallback_decision.failed_payload_input
        if fallback_decision.selection is None:
            _LOGGER.error(
                "dispatch.compact.fallback_selection_failed session_id=%s run_id=%s failure_reason=%s",
                run.session_id,
                run.run_id,
                failed_input.fallback_policy_decision,
            )
        self._append_compaction_failed_event(
            transaction,
            run=run,
            estimate=estimate,
            decision=decision,
            operation_id=failed_input.operation_id,
            failure_reason=failed_input.failure_reason,
            attempt_count=failed_input.attempt_count,
            retry_repair_budget_exhausted=(failed_input.retry_repair_budget_exhausted),
            budget_after_attempted_compact=(failed_input.budget_after_attempted_compact),
            fallback_policy_decision=failed_input.fallback_policy_decision,
            fallback_input_window=failed_input.fallback_input_window,
            fallback_input_digest=failed_input.fallback_input_digest,
            fallback_budget_result=failed_input.fallback_budget_result,
            fallback_action=failed_input.fallback_action,
        )
        if fallback_decision.action_hint != FALLBACK_ACTION_DISPATCH:
            return None
        return self._prepare_and_commit_start_in_transaction(
            transaction,
            run,
            stage=ContextSizingStage.DISPATCH_FALLBACK,
        )

    def _append_compaction_failed_event(
        self,
        transaction: HostTransaction,
        *,
        run: RunRow,
        estimate: BudgetEstimate,
        decision: ContextBudgetDecision,
        operation_id: str,
        failure_reason: str,
        attempt_count: int,
        retry_repair_budget_exhausted: bool,
        budget_after_attempted_compact: int | None = None,
        fallback_policy_decision: str | None = None,
        fallback_input_window: Mapping[str, JsonValue] | None = None,
        fallback_input_digest: str | None = None,
        fallback_budget_result: Mapping[str, JsonValue] | None = None,
        fallback_action: str = FALLBACK_ACTION_NOT_APPLICABLE,
    ) -> None:
        """追加 ``CONTEXT_COMPACTION_FAILED``。

        :param transaction: 当前 Host transaction。
        :param run: 目标 Run。
        :param estimate: budget estimate。
        :param decision: budget decision。
        :param operation_id: compact operation 诊断 id。
        :param failure_reason: compact failure reason。
        :param attempt_count: operation 内已拒绝 proposal attempt 数。
        :param retry_repair_budget_exhausted: semantic retry / repair 预算是否耗尽。
        :param budget_after_attempted_compact: compact 后预算；未执行时为 ``None``。
        :param fallback_policy_decision: fallback policy decision。
        :param fallback_input_window: fallback input window 诊断。
        :param fallback_input_digest: fallback input digest。
        :param fallback_budget_result: fallback budget 诊断。
        :param fallback_action: fallback 动作。
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
                    operation_id=operation_id,
                    failure_reason=failure_reason,
                    policy_decision=_COMPACT_FAILURE_POLICY_DECISION,
                    retryable=False,
                    attempt_count=attempt_count,
                    retry_repair_budget_exhausted=(retry_repair_budget_exhausted),
                    diagnostic_refs=(estimate.estimator_digest,),
                    budget_after_attempted_compact=(budget_after_attempted_compact),
                    fallback_policy_decision=fallback_policy_decision,
                    fallback_input_window=fallback_input_window,
                    fallback_input_digest=fallback_input_digest,
                    fallback_budget_result=fallback_budget_result,
                    fallback_action=fallback_action,
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

        diagnostic_reference = self._write_compaction_rejected_diagnostic(
            transaction,
            operation_id=operation_id,
            rejected=rejected,
        )
        self._event_log_store.append_event(
            transaction,
            EventLogAppendRequest(
                event_id=_new_event_id(_EVENT_ID_CONTEXT_COMPACTION_ATTEMPT_REJECTED_PREFIX),
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
                reason={"failure_category": rejected.failure_category.value},
                payload_json=build_context_compaction_attempt_rejected_payload(
                    operation_id=operation_id,
                    attempt_number=rejected.attempt_number,
                    failure_category=rejected.failure_category.value,
                    repairable=rejected.repairable,
                    runner_attempt_summary_refs=(rejected.runner_attempt_summary_refs),
                    diagnostic_refs=rejected.diagnostic_refs,
                    next_policy_decision=rejected.next_policy_decision.value,
                    budget_after_attempted_compact=(rejected.budget_after_attempted_compact),
                    proposal_manifest_reference=(rejected.proposal_manifest_reference),
                    successful_response_identity=(rejected.successful_response_identity),
                    diagnostic_artifact_ref=(
                        None if diagnostic_reference is None else diagnostic_reference.payload_ref
                    ),
                    diagnostic_artifact_digest=(
                        None if diagnostic_reference is None else diagnostic_reference.payload_digest
                    ),
                    failure_stage=(
                        None if diagnostic_reference is None else diagnostic_reference.diagnostic.failure_stage
                    ),
                    diagnostic_suffix=(
                        None if diagnostic_reference is None else diagnostic_reference.diagnostic.diagnostic_suffix
                    ),
                    parser_or_validator=(
                        None if diagnostic_reference is None else diagnostic_reference.diagnostic.parser_or_validator
                    ),
                    exception_class=(
                        None if diagnostic_reference is None else diagnostic_reference.diagnostic.exception_class
                    ),
                    exception_message=(
                        None if diagnostic_reference is None else diagnostic_reference.diagnostic.exception_message
                    ),
                    offending_block_section=_diagnostic_offending_section(diagnostic_reference),
                    offending_block_kind=_diagnostic_offending_kind(diagnostic_reference),
                    offending_block_label=_diagnostic_offending_label(diagnostic_reference),
                    offending_block_ordinal=_diagnostic_offending_ordinal(diagnostic_reference),
                    offending_block_text_digest=_diagnostic_offending_text_digest(diagnostic_reference),
                    offending_block_text_length=_diagnostic_offending_text_length(diagnostic_reference),
                    material_pack_digest=(
                        None if diagnostic_reference is None else diagnostic_reference.diagnostic.material_pack_digest
                    ),
                ),
                payload_ref=None,
                payload_digest=None,
            ),
        )

    def _write_compaction_rejected_diagnostic(
        self,
        transaction: HostTransaction,
        *,
        operation_id: str,
        rejected: CompactionAttemptRejected,
    ) -> CompactionRejectedAttemptDiagnosticReference | None:
        """写入 proactive rejected attempt diagnostic artifact。

        :param transaction: 当前 Host transaction。
        :param operation_id: compaction operation id。
        :param rejected: rejected attempt 摘要。
        :returns: 已持久化 diagnostic 引用；没有 diagnostic 或写入失败时为
            ``None``。
        """

        diagnostic = rejected.diagnostic
        artifact_root = self._local_execution.compact_artifact_root
        if diagnostic is None or artifact_root is None:
            return None
        try:
            reference = write_compaction_rejected_attempt_diagnostic_artifact(
                transaction=transaction,
                artifact_store=LocalArtifactStore(
                    artifact_root,
                    create_artifact_root=(self._local_execution.compact_artifact_create_parent_dirs),
                ),
                payload_store=PayloadStore(),
                diagnostic=diagnostic,
                compaction_operation_id=operation_id,
                compaction_attempt_number=rejected.attempt_number,
            )
        except HostDurableError as exc:
            _LOGGER.warning(
                "dispatch.compact.rejected_diagnostic_write_failed "
                "operation_id=%s attempt_number=%s failure_stage=%s "
                "error_code=%s message=%s",
                operation_id,
                rejected.attempt_number,
                diagnostic.failure_stage,
                None,
                str(exc),
            )
            return None
        _LOGGER.info(
            "dispatch.compact.rejected_diagnostic_artifact "
            "operation_id=%s attempt_number=%s failure_stage=%s "
            "payload_ref=%s payload_digest=%s artifact_path=%s",
            operation_id,
            rejected.attempt_number,
            diagnostic.failure_stage,
            reference.payload_ref,
            reference.payload_digest,
            reference.artifact_relative_path,
        )
        return reference

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
            try:
                outcome = await self._dispatch_one(record)
            except HostTransactionRetryExhaustedError:
                self._queue.put_nowait(record)
                raise
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

    def reconcile_active_worker_cancels_once(
        self,
        *,
        fixed_now: datetime,
    ) -> ActiveWorkerCancelReconciliationResult:
        """按本 scheduler 的 active registry 快照传播 durable cancel truth。

        本方法只查询 ``dispatch_record.owner_host_instance_id`` 精确等于当前
        scheduler 且仍匹配同一 Session / Run / Attempt / execution 的 targets。
        它不依赖当前 attachment，也不授予 queued promotion 或新 Attempt 治理资格。

        :param fixed_now: 本轮 exact watchdog closeout 共用的 UTC aware 时间。
        :returns: execution-owner reconciliation typed 摘要。
        :raises ValueError: ``fixed_now`` 不是 UTC aware 时间时抛出。
        :raises RuntimeError: scheduler 已关闭时抛出。
        :raises HostDurableError: durable cancel link 或 canonical fact 非法时抛出。
        :raises HostTransactionRetryExhaustedError: durable transaction 重试耗尽时抛出。
        """

        _validate_watchdog_now(fixed_now)
        if self._closed:
            raise RuntimeError("HostDispatchScheduler is closed")
        identities = self._active_registry.snapshot_identities()
        if len(identities) == 0:
            return ActiveWorkerCancelReconciliationResult(
                snapshot_count=0,
                target_count=0,
                propagated_count=0,
                closed_count=0,
            )

        def _read(
            transaction: HostTransaction,
        ) -> tuple[OwnedAttemptCancelDelivery, ...]:
            return read_exact_owned_attempt_cancel_deliveries(
                transaction,
                self._event_log_store,
                owner_host_instance_id=(self._host_instance_identity.host_instance_id),
                identities=identities,
            )

        deliveries = self._transaction_runner.run_read(_read)
        propagated = 0
        closed = 0
        for delivery in deliveries:
            target = delivery.target
            identity = target.identity
            if self._active_registry.cancel(
                ActiveCancelMessage(
                    session_id=identity.session_id,
                    run_id=identity.run_id,
                    attempt_id=identity.attempt_id,
                    execution_id=identity.execution_id,
                    reason=delivery.reason,
                )
            ):
                propagated += 1
            closeout = self._tick_active_cancel_watchdog(
                now=fixed_now,
                scope=_ActiveCancelWatchdogOwnedTargetScope(target=target),
            )
            if closeout.closed > 0:
                closed += 1
        return ActiveWorkerCancelReconciliationResult(
            snapshot_count=len(identities),
            target_count=len(deliveries),
            propagated_count=propagated,
            closed_count=closed,
        )

    async def reconcile_owned_sessions_once(
        self,
        *,
        fixed_now: datetime,
    ) -> OwnedSessionReconciliationResult:
        """对入口快照中的 ACTIVE RW Session 执行一次 durable reconciliation。

        本方法是 production interval loop 与确定性测试共用的唯一 one-shot
        semantic step；它不扫描 RO/closing/未 attach Session。

        :param fixed_now: 本轮所有 target 判定共用的 UTC aware 时间。
        :returns: 不携带业务 payload 的严格 typed 诊断摘要。
        :raises ValueError: ``fixed_now`` 不是 UTC aware 时间时抛出。
        :raises RuntimeError: scheduler 已关闭时抛出。
        :raises Exception: target promotion 或 durable read/write 失败时透传。
        """

        _validate_watchdog_now(fixed_now)
        if self._closed:
            raise RuntimeError("HostDispatchScheduler is closed")
        session_ids = self._session_new_work_access.active_read_write_session_ids()
        leased = 0
        dispatched = 0
        skipped = 0
        for session_id in session_ids:
            work_lease = self._session_new_work_access.try_acquire_new_work_lease(session_id)
            if work_lease is None:
                skipped += 1
                continue
            leased += 1
            work_lease.release()
            did_dispatch = await self._signal_pre_start_governance(session_id)
            if did_dispatch:
                dispatched += 1
            else:
                skipped += 1
        return OwnedSessionReconciliationResult(
            owned_session_count=len(session_ids),
            leased_session_count=leased,
            dispatched_session_count=dispatched,
            skipped_session_count=skipped,
        )

    async def close(self) -> None:
        """关闭 scheduler 并完成必须成功的 lifecycle 收口。

        :returns: ``None``。
        :raises Exception: mandatory cleanup 或 durable lifecycle 写入失败时透传；
            此时不宣称 cleanup 完成，后续 ``close`` 可重试。
        """

        if self._closed and self._close_cleanup_done:
            return
        self._closed = True
        if not self._host_instance_stopping_marked:
            self._mark_host_instance_stopping()
            self._host_instance_stopping_marked = True
        _LOGGER.info(
            "dispatch.scheduler.close_start host_handle_id=%s active_tasks=%s active_handles=%s",
            self._host_handle_id,
            len(self._active_tasks),
            len(self._active_handles),
        )
        background_tasks = tuple(
            task
            for task in (
                self._heartbeat_task,
                self._drain_task,
                self._promotion_drain_task,
                self._owned_session_reconciliation_task,
                self._active_worker_cancel_reconciliation_task,
                self._active_cancel_watchdog_task,
            )
            if task is not None
        )
        active_tasks = tuple(self._active_tasks)
        self._active_registry.cancel_all(_SCHEDULER_CLOSE_REASON)
        # 先同步发出全部取消，避免逐个 await 时尚未启动的任务获得执行窗口。
        for task in (*background_tasks, *active_tasks):
            task.cancel()
        for task in background_tasks:
            await _suppress_task_cancel(task)
        for active_task in active_tasks:
            await _suppress_task_cancel(active_task)
        for active_handle in tuple(self._active_handles):
            await _close_worker_handle_mandatory(active_handle)
            self._active_handles.discard(active_handle)
        self._active_registry.clear()
        if not self._lane_close_done:
            await self._lane_controller.close(reason=_SCHEDULER_CLOSE_REASON)
            self._lane_close_done = True
        if not self._host_instance_stopped_marked:
            self._mark_host_instance_stopped()
            self._host_instance_stopped_marked = True
        self._close_cleanup_done = True
        _LOGGER.info(
            "dispatch.scheduler.close_done host_handle_id=%s",
            self._host_handle_id,
        )

    def _mark_host_instance_stopping(self) -> None:
        """必须成功地把当前 Host instance 标记为 ``STOPPING``。

        :returns: ``None``。
        :raises HostTransactionRetryExhaustedError: durable 写重试耗尽时抛出。
        :raises Exception: durable lifecycle 写失败时透传。
        """

        def _operation(transaction: HostTransaction) -> None:
            mark_current_instance_stopping(transaction, self._host_instance_identity)

        self._transaction_runner.run_write(_operation)

    def _mark_host_instance_stopped(self) -> None:
        """必须成功地把当前 Host instance 标记为 ``STOPPED``。

        :returns: ``None``。
        :raises HostTransactionRetryExhaustedError: durable 写重试耗尽时抛出。
        :raises Exception: durable lifecycle 写失败时透传。
        """

        def _operation(transaction: HostTransaction) -> None:
            mark_current_instance_stopped(transaction, self._host_instance_identity)

        self._transaction_runner.run_write(_operation)

    def _start_host_instance_heartbeat(self) -> None:
        """启动当前 Host instance heartbeat 后台任务。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = self._start_critical_task(
                self._host_instance_heartbeat_loop,
                component=_CRITICAL_COMPONENT_HEARTBEAT,
            )

    def _start_active_cancel_watchdog_loop(self) -> None:
        """启动 active cancel watchdog 后台任务。

        :returns: ``None``。
        """

        if self._active_cancel_watchdog_task is None or self._active_cancel_watchdog_task.done():
            self._active_cancel_watchdog_task = self._start_critical_task(
                self._active_cancel_watchdog_loop,
                component=_CRITICAL_COMPONENT_ACTIVE_CANCEL_WATCHDOG,
            )

    def _start_owned_session_reconciliation_loop(self) -> None:
        """启动 ACTIVE RW Session 的 bounded periodic reconciliation loop。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._owned_session_reconciliation_task is None or self._owned_session_reconciliation_task.done():
            self._owned_session_reconciliation_task = self._start_critical_task(
                self._owned_session_reconciliation_loop,
                component=_CRITICAL_COMPONENT_PROMOTION,
            )

    def _start_active_worker_cancel_reconciliation_loop(self) -> None:
        """启动 execution-owner exact cancel periodic reconciliation loop。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if (
            self._active_worker_cancel_reconciliation_task is None
            or self._active_worker_cancel_reconciliation_task.done()
        ):
            self._active_worker_cancel_reconciliation_task = self._start_critical_task(
                self._active_worker_cancel_reconciliation_loop,
                component=_CRITICAL_COMPONENT_ACTIVE_CANCEL_OWNER,
            )

    def _start_critical_task(
        self,
        operation_factory: Callable[[], Awaitable[None]],
        *,
        component: str,
    ) -> asyncio.Task[None]:
        """启动由 shared health gate 监督的 scheduler critical task。

        :param operation_factory: 延迟创建 critical loop awaitable 的 factory。
        :param component: 稳定 fatal component 标识。
        :returns: 已启动的 asyncio task。
        :raises RuntimeError: 当前没有 running event loop 时抛出。
        """

        return asyncio.create_task(
            self._supervise_critical_task(
                operation_factory,
                component=component,
            )
        )

    async def _supervise_critical_task(
        self,
        operation_factory: Callable[[], Awaitable[None]],
        *,
        component: str,
    ) -> None:
        """把 critical task 非预期异常或提前退出映射为 typed fatal。

        :param operation_factory: 延迟创建 critical loop awaitable 的 factory。
        :param component: 稳定 fatal component 标识。
        :returns: ``None``。
        :raises asyncio.CancelledError: scheduler 正常 close 取消时透传。
        """

        try:
            await operation_factory()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _LOGGER.error(
                "dispatch.critical_task.fatal component=%s host_handle_id=%s error_type=%s",
                component,
                self._host_handle_id,
                exc.__class__.__name__,
                exc_info=True,
            )
        else:
            if self._closed:
                return
            _LOGGER.error(
                "dispatch.critical_task.unexpected_exit component=%s host_handle_id=%s",
                component,
                self._host_handle_id,
            )
        if not self._closed:
            await self._health_gate.report_fatal(
                component=component,
                reason_code=_CRITICAL_FATAL_REASON,
            )

    def _raise_if_wake_unavailable(self, *, component: str) -> None:
        """让 scheduler wake 对 lifecycle 不可用 fail closed。

        :param component: 当前 wake component。
        :returns: ``None``。
        :raises HostApiError: scheduler 已关闭或 shared health 已不可用时抛出。
        """

        if self._closed:
            self._health_gate.raise_if_scheduler_unavailable(
                component=component,
                reason_code=_SCHEDULER_UNAVAILABLE_REASON,
                force=True,
            )
        self._health_gate.raise_if_scheduler_unavailable(
            component=component,
            reason_code=_SCHEDULER_UNAVAILABLE_REASON,
        )

    async def _active_cancel_watchdog_loop(self) -> None:
        """按 target-scoped commit wake 运行 active cancel watchdog。

        execution-owner 的跨 opener 传播由 dispatch poll loop 独立读取本地 worker
        exact identity；本循环只消费 caller/fresh-attach 指定的 Session，不进行
        workspace-wide periodic scan。event 在读取 target 集合前 clear，使本轮
        期间到达的新 wake 保持 set 并驱动下一轮。

        :returns: ``None``。
        :raises asyncio.CancelledError: scheduler close 时透传取消。
        """

        try:
            while not self._closed:
                await self._active_cancel_watchdog_event.wait()
                if self._closed:
                    break
                self._active_cancel_watchdog_event.clear()
                session_ids = tuple(sorted(self._active_cancel_watchdog_session_ids))
                self._active_cancel_watchdog_session_ids.clear()
                fixed_now = datetime.now(UTC)
                for session_id in session_ids:
                    result = self.tick_active_cancel_watchdog_for_session(
                        session_id,
                        fixed_now,
                    )
                    if result.scanned > 0 or result.closed > 0:
                        _LOGGER.log(
                            VERBOSE_LOG_LEVEL,
                            "dispatch.active_cancel_watchdog.tick session_id=%s "
                            "scanned=%s eligible=%s closed=%s ignored=%s",
                            session_id,
                            result.scanned,
                            result.eligible,
                            result.closed,
                            result.ignored,
                        )
        except asyncio.CancelledError:
            _LOGGER.debug(
                "dispatch.active_cancel_watchdog.cancelled host_handle_id=%s",
                self._host_handle_id,
            )
            raise

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
                    self._best_effort_mark_host_instance_stopping("heartbeat_fatal_exit")
                    return
        except asyncio.CancelledError:
            _LOGGER.debug(
                "dispatch.host_instance_heartbeat.cancelled host_handle_id=%s host_instance_id=%s",
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
                                (self._local_execution.dispatch_poll_interval_seconds),
                            )
                            idle_sleep_logged = True
                        await asyncio.sleep(self._local_execution.dispatch_poll_interval_seconds)
                    else:
                        idle_sleep_logged = False
                    result = await self.drain_once()
                    if result.processed > 0:
                        idle_sleep_logged = False
                except HostTransactionRetryExhaustedError as exc:
                    _LOGGER.warning(
                        _LOG_DRAIN_LOOP_DURABLE_RETRY_EXHAUSTED,
                        self._host_handle_id,
                        exc.__class__.__name__,
                        exc_info=True,
                    )
                    await asyncio.sleep(self._local_execution.dispatch_poll_interval_seconds)
                except Exception as exc:
                    _LOGGER.warning(
                        _LOG_DRAIN_LOOP_UNEXPECTED_EXCEPTION,
                        self._host_handle_id,
                        exc.__class__.__name__,
                        exc_info=True,
                    )
                    raise
            _LOGGER.debug(_LOG_DRAIN_LOOP_CLOSE_EXIT, self._host_handle_id)
        except asyncio.CancelledError:
            _LOGGER.debug(
                _LOG_DRAIN_LOOP_CANCELLED_FOR_CLOSE if self._closed else _LOG_DRAIN_LOOP_CANCELLED_EXTERNALLY,
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
                self._promotion_pending_session_ids.discard(session_id)
                try:
                    await self._signal_pre_start_governance(session_id)
                except RuntimeError as exc:
                    if self._closed:
                        _LOGGER.debug(
                            "dispatch.queue_promotion.cancelled_for_close host_handle_id=%s session_id=%s",
                            self._host_handle_id,
                            session_id,
                        )
                    else:
                        self._requeue_promotion_after_backoff(session_id)
                        _LOGGER.warning(
                            "dispatch.queue_promotion.runtime_error host_handle_id=%s session_id=%s error_type=%s",
                            self._host_handle_id,
                            session_id,
                            exc.__class__.__name__,
                            exc_info=True,
                        )
                except HostTransactionRetryExhaustedError as exc:
                    self._requeue_promotion_after_backoff(session_id)
                    _LOGGER.warning(
                        "dispatch.queue_promotion.durable_retry_exhausted "
                        "host_handle_id=%s session_id=%s error_type=%s",
                        self._host_handle_id,
                        session_id,
                        exc.__class__.__name__,
                        exc_info=True,
                    )
                except Exception as exc:
                    self._requeue_promotion_after_backoff(session_id)
                    _LOGGER.warning(
                        "dispatch.queue_promotion.unexpected_exception host_handle_id=%s session_id=%s error_type=%s",
                        self._host_handle_id,
                        session_id,
                        exc.__class__.__name__,
                        exc_info=True,
                    )
                    raise
        except asyncio.CancelledError:
            _LOGGER.debug(
                "dispatch.queue_promotion.cancelled host_handle_id=%s",
                self._host_handle_id,
            )
            raise

    async def _owned_session_reconciliation_loop(self) -> None:
        """周期运行 attachment-authorized Session new-work reconciliation。

        :returns: ``None``。
        :raises asyncio.CancelledError: scheduler close 时透传取消。
        :raises Exception: one-shot durable reconciliation 失败时透传给 health owner。
        """

        try:
            while not self._closed:
                await asyncio.sleep(self._local_execution.dispatch_poll_interval_seconds)
                if self._closed:
                    return
                await self.reconcile_owned_sessions_once(
                    fixed_now=datetime.now(UTC),
                )
        except asyncio.CancelledError:
            _LOGGER.debug(
                "dispatch.owned_session_reconciliation.cancelled host_handle_id=%s",
                self._host_handle_id,
            )
            raise

    async def _active_worker_cancel_reconciliation_loop(self) -> None:
        """周期传播本 scheduler exact worker identities 的 durable cancel。

        本任务不进入 Session promotion 或 proactive compactor await 链，确保旧
        execution owner 的 physical cancel poll 拥有独立进度。

        :returns: ``None``。
        :raises asyncio.CancelledError: scheduler close 时透传取消。
        :raises Exception: exact durable reconciliation 失败时透传给 health owner。
        """

        try:
            while not self._closed:
                await asyncio.sleep(self._local_execution.dispatch_poll_interval_seconds)
                if self._closed:
                    return
                self.reconcile_active_worker_cancels_once(
                    fixed_now=datetime.now(UTC),
                )
        except asyncio.CancelledError:
            _LOGGER.debug(
                "dispatch.active_worker_cancel_reconciliation.cancelled host_handle_id=%s",
                self._host_handle_id,
            )
            raise

    def _requeue_promotion_after_backoff(self, session_id: str) -> None:
        """在 promotion transient failure 后重新投递 session wakeup。

        :param session_id: 需要重新执行 promotion reconciliation 的 Session id。
        :returns: ``None``。
        """

        if self._closed:
            return
        loop = asyncio.get_running_loop()
        loop.call_later(
            self._local_execution.dispatch_poll_interval_seconds,
            self._enqueue_requeued_promotion,
            session_id,
        )

    def _enqueue_requeued_promotion(self, session_id: str) -> None:
        """在 transient backoff 后按同一 level-bit 规则重新投递 signal。

        :param session_id: 需要重新检查 durable truth 的 Session id。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        if self._closed:
            return
        flight = self._pre_start_flights.get(session_id)
        if flight is not None:
            flight.rerun_requested = True
            return
        if session_id in self._promotion_pending_session_ids:
            return
        self._promotion_pending_session_ids.add(session_id)
        self._promotion_queue.put_nowait(session_id)

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
            self._safe_closeout_worker_startup_timeout(record, reason=_WORKER_STARTUP_TIMEOUT_REASON)
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
            self._safe_closeout_worker_startup_timeout(record, reason=_WORKER_STARTUP_TIMEOUT_REASON)
            return "timed_out"
        if not isinstance(acquire, LaneAcquired):
            return "skipped"
        token = acquire.token
        try:
            dispatching_row = self._mark_dispatching_after_recheck(record, token)
            if dispatching_row is None:
                await _safe_release_lane_token(token)
                return "skipped"
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

    def _rewake_dispatch_after_current_drain(self, record: PendingDispatchRecord) -> None:
        """在当前 drain 轮次之后重新投递 dispatch wakeup。

        :param record: 需要重试的 pending dispatch 摘要。
        :returns: ``None``。
        """

        asyncio.get_running_loop().call_soon(self._queue.put_nowait, record)

    def _mark_waiting_for_lane(self, record: PendingDispatchRecord) -> DispatchRecordRow | None:
        """把 pending dispatch 标记为 waiting_for_lane。

        :param record: pending dispatch 摘要。
        :returns: 可继续 dispatch 的 dispatch row；不可继续时为 ``None``。
        """

        def _operation(transaction: HostTransaction) -> DispatchRecordRow | None:
            latest = read_dispatch_record_by_id(transaction, record.dispatch_record_id)
            if latest is None:
                return None
            if latest.status == DispatchRecordStatus.WAITING_FOR_LANE:
                return latest
            result = mark_dispatch_waiting_for_lane_row(
                transaction,
                attempt_id=record.attempt_id,
                owner_host_instance_id=(self._host_instance_identity.host_instance_id),
                lane_name=self._local_execution.lane_name,
                waiting_for_lane_at=format_utc_timestamp(datetime.now(UTC)),
            )
            if result.status == StateMutationStatus.UPDATED:
                return result.row
            return None

        row = self._transaction_runner.run_write(_operation)
        if row is None:
            _LOGGER.debug(
                "dispatch.waiting_for_lane.skipped run_id=%s attempt_id=%s execution_id=%s dispatch_record_id=%s",
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
            dispatch_record = read_dispatch_record_by_id(transaction, record.dispatch_record_id)
            session_exists = run is not None and read_session_by_id(transaction, run.session_id) is not None
            if not _is_dispatchable_recheck(
                run=run,
                attempt=attempt,
                dispatch_record=dispatch_record,
                record=record,
                session_exists=session_exists,
            ):
                return None
            result = mark_dispatching_after_lane_row(
                transaction,
                attempt_id=record.attempt_id,
                owner_host_instance_id=(self._host_instance_identity.host_instance_id),
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

    def _dispatch_record_still_pre_accept(self, dispatch_record: DispatchRecordRow) -> bool:
        """确认 dispatching row 仍处于 worker accept 前。

        :param dispatch_record: dispatching row。
        :returns: 仍可调用 worker 时返回 ``True``。
        """

        def _operation(transaction: HostTransaction) -> bool:
            latest = read_dispatch_record_by_id(transaction, dispatch_record.dispatch_record_id)
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
            request = self._build_frozen_run_input(
                snapshot=snapshot,
                policy_snapshot=effective_decision.policy_snapshot,
                effective_tool_facts=effective_decision.effective_tool_facts,
            )
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
        except _MemoryProjectionDispatchDiagnosticError as exc:
            try:
                _LOGGER.warning(
                    "dispatch.memory_projection.repair_not_reached "
                    "operation=%s run_id=%s attempt_id=%s execution_id=%s "
                    "required_event_sequence=%s started_cursor=%s "
                    "finished_cursor=%s events_scanned=%s batches_used=%s "
                    "stop_reason=%s failures=%s",
                    exc.operation,
                    exc.run_id,
                    exc.attempt_id,
                    exc.execution_id,
                    exc.required_event_sequence,
                    exc.result.started_cursor,
                    exc.result.finished_cursor,
                    exc.result.events_scanned,
                    exc.result.batches_used,
                    exc.result.stop_reason.value,
                    exc.result.failures,
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
            "dispatch.worker_accept.committed run_id=%s attempt_id=%s execution_id=%s dispatch_record_id=%s",
            record.run_id,
            record.attempt_id,
            record.execution_id,
            record.dispatch_record_id,
        )
        self._active_registry.register(
            session_id=snapshot.session_id,
            run_id=record.run_id,
            attempt_id=record.attempt_id,
            execution_id=record.execution_id,
            handle=handle,
            cancellation_token=cancellation_token,
        )
        consumer_started = asyncio.Event()
        consumer_continue = asyncio.Event()
        consumer_ready = asyncio.Event()
        consumer_stream_continue = asyncio.Event()
        task = asyncio.create_task(
            self._consume_worker_events(
                record=record,
                handle=handle,
                token=token,
                cancellation_token=cancellation_token,
                consumer_started=consumer_started,
                consumer_continue=consumer_continue,
                consumer_ready=consumer_ready,
                consumer_stream_continue=consumer_stream_continue,
            )
        )
        self._active_handles.add(handle)
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)
        # ``dispatched`` 返回前让 consumer 建立自己的 durable closeout/finally
        # owner；显式 barrier 同时阻止它提前消费并递归填充当前 drain queue。
        await consumer_started.wait()
        consumer_continue.set()
        # ``ready`` 在初始化成功及外层 finally 两条路径都置位，因此同步初始化
        # 失败也不会挂 caller；成功路径则先把取消处理安装在 stream barrier 上。
        await consumer_ready.wait()
        consumer_stream_continue.set()
        return "dispatched"

    def _build_frozen_run_input(
        self,
        *,
        snapshot: AttemptDispatchSnapshot,
        policy_snapshot: PolicySnapshot,
        effective_tool_facts: EffectiveToolFacts,
    ) -> AgentRunRequest:
        """从 pre-start frozen candidate 构造 Engine request。

        :param snapshot: 当前 Attempt dispatch snapshot。
        :param policy_snapshot: admission 冻结的 policy snapshot。
        :param effective_tool_facts: admission 冻结的完整 exact tool facts。
        :returns: Engine run request。
        :raises HostDurableError: candidate、policy 或 tool runtime 不一致时抛出。
        """

        candidate = load_prepared_runner_call_candidate(
            self._transaction_runner,
            attempt_snapshot=snapshot,
            policy_snapshot=policy_snapshot,
        )
        tool_executor = self._tool_executor_for_frozen_candidate(
            snapshot=snapshot,
            policy_snapshot=policy_snapshot,
            effective_tool_facts=effective_tool_facts,
            candidate=candidate,
        )
        return agent_run_request_from_prepared_candidate(
            candidate=candidate,
            attempt_snapshot=snapshot,
            tool_executor=tool_executor,
        )

    def _tool_executor_for_frozen_candidate(
        self,
        *,
        snapshot: AttemptDispatchSnapshot,
        policy_snapshot: PolicySnapshot,
        effective_tool_facts: EffectiveToolFacts,
        candidate: PreparedRunnerCallCandidate,
    ) -> ToolExecutor:
        """为 frozen selected schema 构造 runtime，并拒绝 schema drift。

        :param snapshot: 当前 Attempt dispatch snapshot。
        :param policy_snapshot: admission-frozen policy。
        :param effective_tool_facts: admission-frozen exact tool facts。
        :param candidate: pre-start frozen candidate。
        :returns: no-tool executor 或同源 ToolRuntime executor。
        :raises HostDurableError: 当前 runtime 无法精确实现 frozen schema 时抛出。
        """

        tooling_options = (
            None
            if candidate.tool_execution_mode is ToolExecutionMode.NO_TOOL_REPLAY
            else self._local_execution.tooling_options
        )
        selected_business_tool_names = validate_effective_tool_facts_runtime(
            effective_tool_facts,
            tooling_options=tooling_options,
        )
        if candidate.disable_tools:
            if candidate.tool_schemas:
                raise HostDurableError("disabled frozen candidate must not expose tool schemas")
            return NoToolExecutor()
        if tooling_options is None:
            raise HostDurableError("tool-enabled frozen candidate has no tooling runtime")
        handle = DefaultToolRuntimeFactory(EffectiveToolBundleBuilder()).create_tool_runtime(
            ToolRuntimeBuildRequest(
                effective_bundle_request=EffectiveToolBundleBuildRequest(
                    business_tool_bundle=tooling_options.business_tool_bundle,
                    source_refs=tooling_options.source_refs,
                    framework_tool_policy=(tooling_options.framework_tool_policy),
                    policy_snapshot_digest=_policy_snapshot_digest(policy_snapshot),
                    selected_business_tool_names=selected_business_tool_names,
                    enable_truncation_manager=(self._local_execution.enable_truncation_manager),
                ),
                execution_scope=ToolRuntimeExecutionScope(
                    session_id=snapshot.session_id,
                    run_id=snapshot.run_id,
                    attempt_id=snapshot.attempt_id,
                    execution_id=snapshot.execution_id,
                    allow_tool_calls=(policy_snapshot.agent_policy.allow_tool_calls),
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
                wait_activation_registry=(tooling_options.wait_activation_registry),
                duplicate_governance_policy=(tooling_options.duplicate_governance_policy),
                process_capsule_interrupt_policy=(tooling_options.process_capsule_interrupt_policy),
            )
        )
        if handle.tool_schemas != candidate.tool_schemas:
            raise HostDurableError("tool runtime schemas do not match frozen candidate")
        return handle.tool_executor

    def _catch_up_memory_projection_before_worker(self, record: PendingDispatchRecord) -> None:
        """在构造 Engine request 前追平 conversation memory projection。

        :param record: pending dispatch 摘要。
        :returns: ``None``。
        :raises HostDurableError: projection runner 或 durable 操作失败时抛出。
        """

        required_event_sequence = self._required_memory_event_sequence_for_dispatch(record)
        result = catch_up_conversation_memory_projection(
            self._transaction_runner,
            policy=self._local_execution.memory_projection_policy,
            batch_size=(self._local_execution.memory_projection_catchup_batch_size),
            max_event_sequence=required_event_sequence,
        )
        _raise_if_memory_projection_target_not_reached(
            operation="catch_up_before_dispatch",
            record=record,
            required_event_sequence=required_event_sequence,
            result=result,
        )

    def _required_memory_event_sequence_for_dispatch(self, record: PendingDispatchRecord) -> int:
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

    def _effective_dispatch_decision(self, record: PendingDispatchRecord) -> _EffectiveDispatchDecision:
        """读取当前 Run 在 admission 冻结的 dispatch 决策。

        :param record: pending dispatch 摘要。
        :returns: effective dispatch 冻结决策。
        """

        def _operation(transaction: HostTransaction) -> _EffectiveDispatchDecision:
            run = read_run_by_id(transaction, record.run_id)
            if run is None:
                raise RuntimeError("dispatch Run is missing")
            event = self._event_log_store.read_event_by_id(transaction, run.input_event_id)
            if event is None:
                raise RuntimeError("dispatch input event is missing")
            payload = event_payload_object(transaction, event, payload_label="USER_INPUT_ACCEPTED")
            return _effective_dispatch_decision_from_payload(payload)

        return self._transaction_runner.run_read(_operation)

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
            latest_dispatch = read_dispatch_record_by_attempt_id(transaction, record.attempt_id)
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
                "dispatch.worker_accept.cas_miss run_id=%s attempt_id=%s execution_id=%s dispatch_record_id=%s",
                record.run_id,
                record.attempt_id,
                record.execution_id,
                dispatch_record.dispatch_record_id,
            )
        return accepted

    def _closeout_worker_startup_timeout(self, record: PendingDispatchRecord, *, reason: str) -> None:
        """worker accept timeout 后关闭 STARTING Attempt。

        :param record: pending dispatch 摘要。
        :param reason: 写入 terminal closeout 的失败原因。
        :returns: ``None``。
        """

        def _operation(
            transaction: HostTransaction,
        ) -> TerminalPostCommitNotice | None:
            attempt_event_id = _new_event_id(_EVENT_ID_ATTEMPT_FAILED_PREFIX)
            run_event_id = _new_event_id(_EVENT_ID_RUN_FAILED_PREFIX)
            result = terminal_closeout_in_transaction(
                transaction,
                self._event_log_store,
                TerminalCloseoutInput(
                    run_id=record.run_id,
                    attempt_id=record.attempt_id,
                    attempt_terminal_event_id=attempt_event_id,
                    run_terminal_event_id=run_event_id,
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
            if result.status != StateMutationStatus.UPDATED or result.run is None:
                return None
            notice = project_terminal_notice_from_exact_run_event(
                result.run,
                result.run_event,
                wake_queue_promotion=(result.run_event is not None and result.run_event.event_id == run_event_id),
            )
            event = self._event_log_store.read_event_by_id(
                transaction,
                attempt_event_id,
            )
            if event is None:
                return notice
            cancel_starting_dispatch_record_row(
                transaction,
                attempt_id=record.attempt_id,
                cancelled_event_id=event.event_id,
                cancelled_event_sequence=event.event_sequence,
                cancelled_at=format_utc_timestamp(datetime.now(UTC)),
            )
            return notice

        terminal_notice = self._transaction_runner.run_write(_operation)
        if terminal_notice is not None:
            self._notify_terminal_post_commit(terminal_notice)
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "dispatch.worker_startup.closeout_committed run_id=%s attempt_id=%s execution_id=%s reason=%s",
            record.run_id,
            record.attempt_id,
            record.execution_id,
            reason,
        )

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
            original_error_type = original_error.__class__.__name__ if original_error is not None else "None"
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

    def _safe_close_worker_lost(
        self,
        *,
        ingestor: EngineEventIngestor,
        envelope: LocalEngineEnvelope,
        record: PendingDispatchRecord,
        local_worker_id: str | None,
        worker_lifecycle_signal: str,
        stream_error_code: str,
        last_observed_worker_event_index: int,
        last_accepted_event_id: str | None,
        original_error: BaseException,
    ) -> bool:
        """best-effort 执行 worker lost closeout 并保留原始异常诊断。

        :param ingestor: Engine event ingestor。
        :param envelope: 当前 worker envelope。
        :param record: pending dispatch 摘要。
        :param local_worker_id: 本地 worker id；构造 envelope 前失败时为
            ``None``。
        :param worker_lifecycle_signal: worker lifecycle signal。
        :param stream_error_code: 原始 stream/ingest 异常类型名。
        :param last_observed_worker_event_index: 最后观测到的 worker event index。
        :param last_accepted_event_id: 最后已接受 EventLog id；无时为
            ``None``。
        :param original_error: 触发 lost closeout 的原始异常。
        :returns: closeout 成功且关闭 Run 时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        try:
            result = ingestor.close_worker_lost(
                envelope,
                observed_at=datetime.now(UTC),
                worker_lifecycle_signal=worker_lifecycle_signal,
                stream_error_code=stream_error_code,
                last_observed_worker_event_index=last_observed_worker_event_index,
                last_accepted_event_id=last_accepted_event_id,
            )
        except Exception as exc:
            _LOGGER.error(
                _LOG_WORKER_LOST_CLOSEOUT_FAILED,
                record.run_id,
                record.attempt_id,
                record.execution_id,
                record.dispatch_record_id,
                local_worker_id,
                worker_lifecycle_signal,
                last_observed_worker_event_index,
                exc.__class__.__name__,
                original_error.__class__.__name__,
                exc_info=True,
            )
            return False
        return _ingest_closed_run(result)

    async def _consume_worker_events(
        self,
        *,
        record: PendingDispatchRecord,
        handle: LocalWorkerHandle,
        token: LaneClaimToken,
        cancellation_token: _HostCancellationToken,
        consumer_started: asyncio.Event,
        consumer_continue: asyncio.Event,
        consumer_ready: asyncio.Event,
        consumer_stream_continue: asyncio.Event,
    ) -> None:
        """消费 worker EngineEvent stream 并在结束时释放 lane。

        :param record: pending dispatch 摘要。
        :param handle: worker handle。
        :param token: runtime lane token。
        :param cancellation_token: Host 注入 Engine 的取消 token。
        :param consumer_started: consumer 已建立 closeout owner 的一次性信号。
        :param consumer_continue: 允许 consumer 执行同步初始化的 barrier。
        :param consumer_ready: 初始化成功或失败后的必达握手信号。
        :param consumer_stream_continue: dispatch 返回前禁止消费 stream 的 barrier。
        :returns: ``None``。
        """

        run_terminal_closed = False
        local_worker_id: str | None = None
        try:
            # 最外层 owner 一建立就完成握手；后续任何同步初始化失败都只能让
            # consumer task 失败，不能让 dispatch caller 永久等待 started。
            consumer_started.set()
            await consumer_continue.wait()
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
                transient_delta_publisher=self._transient_delta_publisher,
                terminal_post_commit_port=self._required_terminal_post_commit_port(),
                wakeup_port=self,
                context_budget_policy=self._local_execution.context_budget_policy,
                context_compactor=self._local_execution.context_compactor,
                compact_artifact_root=self._local_execution.compact_artifact_root,
                compact_artifact_create_parent_dirs=(self._local_execution.compact_artifact_create_parent_dirs),
                memory_projection_policy=(self._local_execution.memory_projection_policy),
                memory_projection_catchup_batch_size=(self._local_execution.memory_projection_catchup_batch_size),
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
                    consumer_ready.set()
                    await consumer_stream_continue.wait()
                    event = await anext(events)
                except StopAsyncIteration:
                    if not terminal_seen:
                        if cancellation_token.is_cancelled():
                            cancel_requested_at = _read_committed_cancel_requested_at(
                                transaction_runner=self._transaction_runner,
                                event_log_store=self._event_log_store,
                                run_id=record.run_id,
                            )
                            if cancel_requested_at is not None:
                                result = ingestor.ingest(
                                    _cancelled_eof_candidate(
                                        envelope=envelope,
                                        worker_event_index=worker_event_index + 1,
                                        observed_at=datetime.now(UTC),
                                        cancel_requested_at=cancel_requested_at,
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
                    if cancellation_token.is_cancelled():
                        try:
                            cancel_requested_at = _read_committed_cancel_requested_at(
                                transaction_runner=self._transaction_runner,
                                event_log_store=self._event_log_store,
                                run_id=record.run_id,
                            )
                            if cancel_requested_at is not None:
                                result = ingestor.ingest(
                                    _cancelled_eof_candidate(
                                        envelope=envelope,
                                        worker_event_index=worker_event_index + 1,
                                        observed_at=datetime.now(UTC),
                                        cancel_requested_at=cancel_requested_at,
                                        cancellation_token=cancellation_token,
                                    )
                                )
                                run_terminal_closed = _ingest_closed_run(result)
                        except Exception as closeout_exc:
                            run_terminal_closed = self._safe_close_worker_lost(
                                ingestor=ingestor,
                                envelope=envelope,
                                record=record,
                                local_worker_id=local_worker_id,
                                worker_lifecycle_signal="worker_stream_cancelled",
                                stream_error_code=closeout_exc.__class__.__name__,
                                last_observed_worker_event_index=worker_event_index,
                                last_accepted_event_id=last_accepted_event_id,
                                original_error=closeout_exc,
                            )
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
                    run_terminal_closed = self._safe_close_worker_lost(
                        ingestor=ingestor,
                        envelope=envelope,
                        record=record,
                        local_worker_id=local_worker_id,
                        worker_lifecycle_signal="worker_stream_error",
                        stream_error_code=exc.__class__.__name__,
                        last_observed_worker_event_index=worker_event_index,
                        last_accepted_event_id=last_accepted_event_id,
                        original_error=exc,
                    )
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
                    run_terminal_closed = self._safe_close_worker_lost(
                        ingestor=ingestor,
                        envelope=envelope,
                        record=record,
                        local_worker_id=local_worker_id,
                        worker_lifecycle_signal="ingest_exception",
                        stream_error_code=exc.__class__.__name__,
                        last_observed_worker_event_index=worker_event_index,
                        last_accepted_event_id=last_accepted_event_id,
                        original_error=exc,
                    )
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
            consumer_ready.set()
            self._active_registry.unregister(
                attempt_id=record.attempt_id,
                execution_id=record.execution_id,
            )
            handle_closed = await _safe_close_worker_handle(handle)
            if handle_closed:
                self._active_handles.discard(handle)
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
    session_exists: bool,
) -> bool:
    """判断 lane acquired 后 durable facts 是否仍可 dispatch。

    :param run: Run row。
    :param attempt: Attempt row。
    :param dispatch_record: dispatch row。
    :param record: pending dispatch 摘要。
    :param session_exists: Run 所属 Session row 是否仍存在。
    :returns: 可 dispatch 时返回 ``True``。
    """

    return (
        run is not None
        and attempt is not None
        and dispatch_record is not None
        and session_exists
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


def _read_committed_cancel_requested_at(
    *,
    transaction_runner: HostTransactionRunner,
    event_log_store: EventLogStore,
    run_id: str,
) -> datetime | None:
    """读取 Run linked ``CANCEL_REQUESTED`` canonical fact 的发生时间。

    :param transaction_runner: Host durable transaction runner。
    :param event_log_store: EventLog primitive。
    :param run_id: 目标 Run id。
    :returns: committed cancel 请求时间；Run 缺失或 link 不存在时返回
        ``None``。
    :raises HostTransactionRetryExhaustedError: durable read transaction 重试耗尽时抛出。
    :raises HostDurableError: durable read 失败时抛出。
    """

    return transaction_runner.run_read(
        _ReadCommittedCancelRequestedAtOperation(
            event_log_store=event_log_store,
            run_id=run_id,
        )
    )


def _cancelled_eof_candidate(
    *,
    envelope: LocalEngineEnvelope,
    worker_event_index: int,
    observed_at: datetime,
    cancel_requested_at: datetime,
    cancellation_token: _HostCancellationToken,
) -> EngineEventCandidate:
    """把 cancel 后的 clean EOF 转为明确 run_cancelled candidate。

    :param envelope: 当前 worker envelope。
    :param worker_event_index: 合成 EngineEvent 的 worker event 序号。
    :param observed_at: Host 观察时间。
    :param cancel_requested_at: committed ``CANCEL_REQUESTED`` canonical fact
        的发生时间。
    :param cancellation_token: Host 注入 Engine 的取消 token。
    :returns: 可交给 EngineEventIngestor 的 cancel candidate。
    :raises Exception: 不主动抛出异常。
    """

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
                requested_at=cancel_requested_at,
                accepted_at=observed_at,
                finished_at=observed_at,
            ),
            metadata=None,
        ),
    )


def _validate_watchdog_now(now: datetime) -> None:
    """校验 watchdog tick 时间为 UTC aware。

    :param now: 待校验时间。
    :returns: ``None``。
    :raises ValueError: ``now`` 不是 UTC aware 时间时抛出。
    """

    if now.tzinfo is None or now.utcoffset() != UTC.utcoffset(None):
        raise ValueError("watchdog now must be timezone.utc aware")


def _read_active_cancel_watchdog_candidates(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    session_id: str,
) -> tuple[tuple[_ActiveCancelWatchdogCandidate, ...], int, int]:
    """读取目标 Session 的 active cancel watchdog 可评估候选。

    :param transaction: Host transaction。
    :param event_log_store: EventLog primitive。
    :param session_id: 目标 Session id。
    :returns: 候选集合、扫描到的 ``CANCELLING`` Run 数和跳过数量。
    """

    candidates: list[_ActiveCancelWatchdogCandidate] = []
    scanned = 0
    ignored = 0
    runs = read_cancelling_runs_for_session(transaction, session_id)
    for run in runs:
        scanned += 1
        candidate = _active_cancel_watchdog_candidate_from_run(
            transaction,
            event_log_store,
            run,
        )
        if candidate is None:
            ignored += 1
        else:
            candidates.append(candidate)
    return tuple(candidates), scanned, ignored


def _read_exact_owned_active_cancel_watchdog_candidate(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    owner_host_instance_id: str,
    target: OwnedAttemptCancelTarget,
) -> tuple[tuple[_ActiveCancelWatchdogCandidate, ...], int, int]:
    """在 watchdog 写事务内重验 execution-owner exact target。

    本 helper 只把 run-transition owner 已严格校验的 target 投影为既有
    watchdog candidate；terminal transition 仍只由 ``_tick`` 的唯一调用点执行。

    :param transaction: Host write transaction。
    :param event_log_store: EventLog primitive。
    :param owner_host_instance_id: 当前 scheduler 的 durable owner id。
    :param target: bounded read transaction 返回的 exact target。
    :returns: 仍精确匹配时返回单 candidate；stale 时返回空集合。
    :raises HostDurableError: linked cancel fact 在重验时非法时抛出。
    """

    exact_targets = read_exact_owned_attempt_cancel_targets(
        transaction,
        event_log_store,
        owner_host_instance_id=owner_host_instance_id,
        identities=(target.identity,),
    )
    if exact_targets != (target,):
        return (), 0, 0
    cancel_requested = event_log_store.read_event_by_id(
        transaction,
        target.cancel_request_event_id,
    )
    if cancel_requested is None:
        raise HostDurableError("owned Attempt cancel target lost its validated event")
    identity = target.identity
    return (
        (
            _ActiveCancelWatchdogCandidate(
                run_id=identity.run_id,
                session_id=identity.session_id,
                attempt_id=identity.attempt_id,
                cancel_requested_at=parse_utc_timestamp(cancel_requested.occurred_at),
            ),
        ),
        1,
        0,
    )


def _active_cancel_watchdog_candidate_from_run(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    run: RunRow,
) -> _ActiveCancelWatchdogCandidate | None:
    """从单个 Run 派生 active cancel watchdog 候选。

    :param transaction: Host transaction。
    :param event_log_store: EventLog primitive。
    :param run: 当前 ``CANCELLING`` Run。
    :returns: 满足 current running Attempt 与 accepted dispatch fact 时返回候选；
        否则返回 ``None``。
    """

    if run.current_attempt_id is None:
        return None
    attempt = read_attempt_by_id(transaction, run.current_attempt_id)
    if attempt is None or attempt.status is not AttemptStatus.RUNNING:
        return None
    dispatch_record = read_dispatch_record_by_attempt_id(
        transaction,
        attempt.attempt_id,
    )
    if not _dispatch_record_has_worker_accept(dispatch_record):
        return None
    cancel_requested = _read_linked_cancel_requested_event(
        transaction,
        event_log_store,
        run,
    )
    if cancel_requested is None:
        return None
    return _ActiveCancelWatchdogCandidate(
        run_id=run.run_id,
        session_id=run.session_id,
        attempt_id=attempt.attempt_id,
        cancel_requested_at=parse_utc_timestamp(cancel_requested.occurred_at),
    )


def _dispatch_record_has_worker_accept(
    dispatch_record: DispatchRecordRow | None,
) -> bool:
    """判断 dispatch record 是否已有 worker accepted durable fact。

    :param dispatch_record: 目标 dispatch record；缺失时为 ``None``。
    :returns: 已接受且未被 pre-accept cancel 时返回 ``True``。
    """

    return (
        dispatch_record is not None
        and dispatch_record.worker_accept_event_id is not None
        and dispatch_record.worker_accept_event_sequence is not None
        and dispatch_record.worker_accepted_at is not None
        and dispatch_record.cancelled_event_id is None
    )


def _read_linked_cancel_requested_event(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    run: RunRow,
) -> EventLogRow | None:
    """读取 Run row typed cancel link 指向的 ``CANCEL_REQUESTED`` fact。

    :param transaction: Host transaction。
    :param event_log_store: EventLog primitive。
    :param run: 目标 Run row。
    :returns: 同 Run 的 ``CANCEL_REQUESTED`` event；缺失或 link 无效时返回 ``None``。
    """

    return read_cancel_requested_event_from_run_link(transaction, event_log_store, run)


def _read_startable_run(transaction: HostTransaction, session_id: str) -> RunRow | None:
    """读取当前可进入 pre-start governance 的 Run。

    :param transaction: 当前 Host transaction。
    :param session_id: Session id。
    :returns: accepted Run、无 active 时的最早 queued Run，或 ``None``。
    """

    if read_session_by_id(transaction, session_id) is None:
        return None
    accepted = read_accepted_run_for_session(transaction, session_id)
    if accepted is not None:
        return accepted
    active = read_active_run_for_session(transaction, session_id)
    if active is not None:
        return None
    return read_earliest_queued_run(transaction, session_id)


def _display_text_from_input_event(transaction: HostTransaction, event: EventLogRow) -> str:
    """从 ``USER_INPUT_ACCEPTED`` event 读取展示文本。

    :param transaction: 当前 Host transaction。
    :param event: input event row。
    :returns: 展示文本。
    :raises RuntimeError: payload 缺失展示文本时抛出。
    """

    payload = event_payload_object(transaction, event, payload_label="USER_INPUT_ACCEPTED")
    value = payload.get("display_text")
    if not isinstance(value, str) or value.strip() == "":
        raise RuntimeError("USER_INPUT_ACCEPTED display_text is invalid")
    return value


def _run_session_allows_proactive_compaction(transaction: HostTransaction, run: RunRow) -> bool:
    """判断 proactive compaction commit 前 Session 仍允许提交。

    :param transaction: 当前 Host transaction。
    :param run: 目标 Run row。
    :returns: Session 仍 open 且未 closed 时返回 ``True``。
    """

    session = read_session_by_id(transaction, run.session_id)
    return session is not None and session.status is SessionStatus.OPEN and session.closed_at is None


def _compaction_result_accepted(result: CompactionOperationResult) -> bool:
    """判断 compaction operation result 是否包含可提交 accepted candidate。

    :param result: compaction operation result。
    :returns: accepted candidate 与 quality 均存在且无 failure reason 时返回 ``True``。
    """

    return result.accepted_truth is not None and result.failure_reason is None


def _repair_feedback_for_request(
    feedback: CompactRepairFeedbackV4 | None,
    request: CompactionRequest,
) -> CompactRepairFeedbackV4 | None:
    """只保留精确绑定当前 request 与 source boundary 的 feedback。

    :param feedback: 前一 attempt 返回的 feedback；首次为 ``None``。
    :param request: 当前 frozen attempt request。
    :returns: 双 digest 同源时返回原 feedback，否则返回 ``None``。
    """

    if feedback is None:
        return None
    if (
        feedback.request_digest != request.digest()
        or feedback.source_boundary_digest != request.source_boundary_digest()
    ):
        return None
    return feedback


def _compaction_result_is_non_repairable(
    result: CompactionOperationResult,
) -> bool:
    """判断 operation failure 是否明确禁止继续 proactive schedule。

    :param result: 当前 attempt 的 operation result。
    :returns: 最后一个 rejection 明确 non-repairable 时返回 ``True``。
    """

    return (
        result.accepted_truth is None
        and len(result.rejected_attempts) > 0
        and not result.rejected_attempts[-1].repairable
    )


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
        and dispatch_record.dispatch_record_id == original_dispatch_record.dispatch_record_id
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


def _highest_attempt_number(
    rejected_attempts: tuple[CompactionAttemptRejected, ...],
    *,
    accepted_attempt_number: int | None,
    minimum: int = 0,
) -> int:
    """返回 rejected/accepted attempt numbers 的最大值。

    :param rejected_attempts: 本次 execution 的 rejected attempts。
    :param accepted_attempt_number: 可选 accepted attempt number。
    :param minimum: 没有结果时使用的非负下界。
    :returns: 最大 attempt number。
    :raises ValueError: 下界为负数时抛出。
    """

    if minimum < 0:
        raise ValueError("minimum must be non-negative")
    numbers = [minimum]
    numbers.extend(rejected.attempt_number for rejected in rejected_attempts)
    if accepted_attempt_number is not None:
        numbers.append(accepted_attempt_number)
    return max(numbers)


def _required_accepted_attempt_number(value: int | None) -> int:
    """校验并返回 accepted 全局 attempt number。

    :param value: operation result 中的 accepted number。
    :returns: 正数 attempt number。
    :raises RuntimeError: accepted result 缺失或非法时抛出。
    """

    if value is None or value <= 0:
        raise RuntimeError("accepted compaction is missing attempt number")
    return value


def _required_proactive_operation_id(state: ProactiveCompactionState) -> str:
    """返回 existing proactive state 的 operation id。

    :param state: typed proactive state。
    :returns: 非空 operation id。
    :raises RuntimeError: state 缺少 operation id 时抛出。
    """

    value = state.operation_id
    if value is None or value.strip() == "":
        raise RuntimeError("proactive state is missing operation id")
    return value


def _required_proactive_next_attempt(state: ProactiveCompactionState) -> int:
    """返回 existing proactive state 的下一 attempt number。

    :param state: typed proactive state。
    :returns: 正数下一 attempt number。
    :raises RuntimeError: state 缺少合法 number 时抛出。
    """

    value = state.next_attempt_number
    if value is None or value <= 0:
        raise RuntimeError("proactive state is missing next attempt number")
    return value


def _required_proactive_max_attempt(state: ProactiveCompactionState) -> int:
    """返回 existing proactive state 的冻结 attempt 上限。

    :param state: typed proactive state。
    :returns: 正数 attempt 上限。
    :raises RuntimeError: state 缺少合法上限时抛出。
    """

    value = state.max_attempt_number
    if value is None or value <= 0:
        raise RuntimeError("proactive state is missing max attempt number")
    return value


def _validate_proactive_resume_snapshot(
    state: ProactiveCompactionState,
    *,
    source_snapshot: CompactPipelineSourceSnapshot,
    attempt_schedule: tuple[ProactiveCompactionAttemptPlan, ...],
    expected_input_event_sequence: int,
) -> None:
    """验证 resume material/request 与 request fact 冻结值同源。

    :param state: existing INCOMPLETE proactive state。
    :param source_snapshot: 当前 durable material 重建结果。
    :param attempt_schedule: 当前 frozen inputs 重建的 typed attempt schedule。
    :param expected_input_event_sequence: 当前 Run input cursor。
    :returns: ``None``。
    :raises RuntimeError: cursor、material 或 request digest 漂移时抛出。
    """

    if state.input_snapshot_cursor != expected_input_event_sequence:
        raise RuntimeError("proactive resume input cursor changed")
    if state.frozen_material_list_digest != source_snapshot.material_view_digest:
        raise RuntimeError("proactive resume material digest changed")
    if state.frozen_material_refs != source_snapshot.material_source_refs:
        raise RuntimeError("proactive resume material refs changed")
    validate_proactive_compaction_attempt_schedule(state, attempt_schedule)


def _required_row_text(row: HostRow, field_name: str) -> str:
    """读取 HostRow 中的必填文本字段。

    :param row: Host row。
    :param field_name: 字段名。
    :returns: 文本字段值。
    :raises ValueError: 字段缺失或不是非空文本时抛出。
    """

    value = row.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"row field {field_name} must be non-empty text")
    return value


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
            "continuation_max_attempts": (policy_snapshot.agent_policy.continuation_max_attempts),
            "tool_execution_timeout_seconds": (policy_snapshot.agent_policy.tool_execution_timeout_seconds),
        }
    )


def _effective_dispatch_decision_from_payload(
    payload: JsonValue,
) -> _EffectiveDispatchDecision:
    """从 ``USER_INPUT_ACCEPTED`` payload 解析冻结 dispatch 决策。

    :param payload: EventLog payload JSON。
    :returns: effective dispatch 决策。
    :raises RuntimeError: 冻结 execution config 或 tool set JSON shape 非法时抛出。
    :raises ValueError: 冻结 provider/agent policy 枚举值或字段语义非法时抛出。
    """

    if not isinstance(payload, Mapping):
        raise RuntimeError("USER_INPUT_ACCEPTED payload must be object")
    execution_value = payload.get(_PAYLOAD_FIELD_EFFECTIVE_EXECUTION_CONFIG)
    tool_value = payload.get(_PAYLOAD_FIELD_EFFECTIVE_TOOL_SET)
    if execution_value is None:
        raise RuntimeError("effective_execution_config is missing")
    if tool_value is None:
        raise RuntimeError("effective_tool_set is missing")
    policy_snapshot = _policy_snapshot_from_effective_execution(execution_value)
    effective_tool_facts = parse_effective_tool_facts(tool_value)
    return _EffectiveDispatchDecision(
        policy_snapshot=policy_snapshot,
        effective_tool_facts=effective_tool_facts,
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


async def _safe_close_worker_handle(handle: LocalWorkerHandle) -> bool:
    """best-effort 关闭 worker handle。

    :param handle: worker handle。
    :returns: handle close 成功时返回 ``True``；timeout 或异常时返回 ``False``。
    """

    try:
        await asyncio.wait_for(
            handle.close(),
            timeout=_LOCAL_WORKER_CLOSE_GRACE_SECONDS,
        )
        return True
    except TimeoutError:
        _LOGGER.warning(
            "dispatch.worker_handle.close_timed_out local_worker_id=%s timeout_seconds=%s",
            _safe_worker_id_for_log(handle),
            _LOCAL_WORKER_CLOSE_GRACE_SECONDS,
        )
        return False
    except Exception as exc:
        _LOGGER.warning(
            "dispatch.worker_handle.close_failed error_type=%s",
            exc.__class__.__name__,
            exc_info=True,
        )
        return False


async def _close_worker_handle_mandatory(handle: LocalWorkerHandle) -> None:
    """在 scheduler close owner 边界必须成功关闭残余 worker handle。

    正常执行路径继续使用 best-effort helper；scheduler lifecycle close 只有在
    handle 确认关闭后才可清除 registry、关闭 lane 并写入 ``STOPPED``。timeout
    或异常必须向上传播，让同一个 scheduler 的后续 ``close`` 重试该阶段。

    :param handle: scheduler 仍持有的残余 worker handle。
    :returns: ``None``。
    :raises TimeoutError: handle 未在既有 close grace 内完成时抛出。
    :raises Exception: handle close 失败时原样抛出。
    """

    await asyncio.wait_for(
        handle.close(),
        timeout=_LOCAL_WORKER_CLOSE_GRACE_SECONDS,
    )


def _safe_worker_id_for_log(handle: LocalWorkerHandle) -> str:
    """best-effort 读取 worker id 用于日志。

    :param handle: worker handle。
    :returns: worker id；读取失败时返回诊断占位文本。
    """

    try:
        return handle.local_worker_id
    except Exception:
        return "<unavailable>"


async def _safe_release_lane_token(token: LaneClaimToken) -> None:
    """best-effort 释放 runtime lane token。

    :param token: lane claim token。
    :returns: ``None``。
    """

    try:
        await token.release()
    except Exception as exc:
        _LOGGER.warning(
            "dispatch.lane_token.release_failed lane_name=%s claim_id=%s error_type=%s",
            token.name,
            token.claim_id,
            exc.__class__.__name__,
            exc_info=True,
        )
        return


def _diagnostic_offending_section(
    reference: CompactionRejectedAttemptDiagnosticReference | None,
) -> str | None:
    """返回 diagnostic offending block section。

    :param reference: persisted diagnostic reference。
    :returns: section；没有定位时为 ``None``。
    """

    offending = None if reference is None else reference.diagnostic.offending_block
    return None if offending is None else offending.section


def _diagnostic_offending_kind(
    reference: CompactionRejectedAttemptDiagnosticReference | None,
) -> str | None:
    """返回 diagnostic offending block kind。

    :param reference: persisted diagnostic reference。
    :returns: kind；没有定位时为 ``None``。
    """

    offending = None if reference is None else reference.diagnostic.offending_block
    return None if offending is None else offending.kind


def _diagnostic_offending_label(
    reference: CompactionRejectedAttemptDiagnosticReference | None,
) -> str | None:
    """返回 diagnostic offending block label。

    :param reference: persisted diagnostic reference。
    :returns: label；没有定位时为 ``None``。
    """

    offending = None if reference is None else reference.diagnostic.offending_block
    return None if offending is None else offending.block_label


def _diagnostic_offending_ordinal(
    reference: CompactionRejectedAttemptDiagnosticReference | None,
) -> int | None:
    """返回 diagnostic offending block ordinal。

    :param reference: persisted diagnostic reference。
    :returns: ordinal；没有定位时为 ``None``。
    """

    offending = None if reference is None else reference.diagnostic.offending_block
    return None if offending is None else offending.block_ordinal


def _diagnostic_offending_text_digest(
    reference: CompactionRejectedAttemptDiagnosticReference | None,
) -> str | None:
    """返回 diagnostic offending block text digest。

    :param reference: persisted diagnostic reference。
    :returns: text digest；没有定位时为 ``None``。
    """

    offending = None if reference is None else reference.diagnostic.offending_block
    return None if offending is None else offending.text_digest


def _diagnostic_offending_text_length(
    reference: CompactionRejectedAttemptDiagnosticReference | None,
) -> int | None:
    """返回 diagnostic offending block text length。

    :param reference: persisted diagnostic reference。
    :returns: text length；没有定位时为 ``None``。
    """

    offending = None if reference is None else reference.diagnostic.offending_block
    return None if offending is None else offending.text_length


async def _suppress_task_cancel(
    task: asyncio.Task[None] | asyncio.Task[bool],
) -> None:
    """等待 task 结束并吞掉取消异常。

    :param task: 待等待 task。
    :returns: ``None``。
    :raises Exception: task 的非取消异常原样透传。
    """

    try:
        await task
    except asyncio.CancelledError:
        return


__all__ = [
    "ActiveCancelMessage",
    "ActiveCancelWatchdogTickResult",
    "ActiveWorkerRegistry",
    "DispatchDrainResult",
    "HostDispatchScheduler",
]
