"""Host-owned EngineEvent ingest 与 terminal closeout。

本模块把 Engine 公共 ``EngineEvent`` 包装在 Host-owned envelope 中进入
durable EventLog，并在 Phase 5 范围内完成 preview、projection signal、
diagnostic 与 terminal canonical facts 的映射。Engine contract 不携带
Host Attempt identity；attempt / execution / dispatch identity 只来自
本模块的 envelope 与 durable state 校验。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_outcome import (
    ToolCancelledOutcome,
    ToolCompletedOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_await import ToolAwaitSnapshot
from dayu.engine.contracts.engine_events import (
    ContentCompleteData,
    ContentDeltaData,
    ContextCompactionRequestedData,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    IterationCompletedData,
    IterationStartedData,
    ProviderProtocolErrorData,
    RUN_SUSPENDED_REASON_TOOL_AWAITING,
    ReasoningDeltaData,
    RunCancelledData,
    RunFailedData,
    RunSuspendedData,
    ToolAwaitingData,
    ToolCallRequestedData,
    ToolCallDeltaData,
    ToolCallsBatchDoneData,
    ToolCallsBatchReadyData,
    ToolResultAcceptedData,
    UsageReportedData,
)
from dayu.host.admission import (
    AdmissionWakeupPort,
    NoopAdmissionWakeupPort,
    PendingDispatchRecord,
)
from dayu.host.api import AttemptStatus, RunStatus
from dayu.host.compact_payload import (
    COMPACT_ARTIFACT_MEDIA_TYPE_VNEXT,
    COMPACT_PROJECTION_SIGNAL_MEMORY_CATCHUP,
    accepted_evidence_mapping_refs_for_candidate,
    compact_artifact_descriptor_metadata_vnext,
    compact_artifact_json_vnext,
    compact_artifact_payload_ref,
    prompt_local_label_mapping_refs,
    source_boundary_refs,
)
from dayu.host.compact_material import (
    RunInputMaterialBlock,
    build_compact_material_pack,
    run_input_material_block,
    select_compact_segment,
    selected_material_source_refs,
)
from dayu.host.compaction import (
    CompactQualityCheckResultVNext,
    CompactMaterialBlockKind,
    CompactMaterialSection,
    CompactSegmentSelection,
    CompactSegmentTrigger,
    CompactionRequest,
    ContextCompactor,
    ConversationCompactOutputVNext,
)
from dayu.host.compaction_operation import (
    CompactionAttemptRejected,
    CompactionOperationResult,
    run_compaction_operation,
)
from dayu.host.context_budget import (
    BudgetEstimate,
    BudgetEstimateInput,
    BudgetTextFragment,
    ContextBudgetDecision,
    UsageObservation,
    UsageObservationDiagnostic,
    USAGE_OBSERVATION_STATUS_ESTIMATE_UNAVAILABLE,
    USAGE_OBSERVATION_STATUS_OBSERVED,
    build_usage_observation_diagnostic,
    decide_context_budget,
    estimate_context_budget,
)
from dayu.host.context_fallback import (
    FALLBACK_ACTION_DISPATCH,
    FALLBACK_ACTION_FAIL_CLOSED,
    FALLBACK_ACTION_NOT_APPLICABLE,
    FALLBACK_POLICY_DECISION_RECENT_WINDOW,
    FALLBACK_POLICY_DECISION_SELECTION_FAILED,
    build_recent_window_fallback_selection,
    build_selection_failure_budget_payload,
    build_selection_failure_window_payload,
    estimate_recent_window_fallback_budget,
    fallback_window_digest,
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
from dayu.host.context_policy import (
    ContextBudgetPolicy,
    ContextCompactionTriggerSource,
)
from dayu.host.durable.codec import (
    canonical_json_dumps,
    format_utc_timestamp,
    parse_utc_timestamp,
    sha256_digest_json,
)
from dayu.host.durable.event_log import (
    EventClass,
    EventPayloadTextEqualsFilter,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.payload import (
    PayloadDescriptor,
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.run_transition import (
    ActiveCancelCloseoutInput,
    ContextRecoveryCloseInput,
    FailRecoveringRunInput,
    StartRecoveryRunInput,
    TerminalCloseoutInput,
    active_cancel_closeout_in_transaction,
    close_attempt_for_context_recovery_in_transaction,
    fail_recovering_run_in_transaction,
    start_recovery_run_with_starting_attempt_in_transaction,
    terminal_closeout_in_transaction,
)
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    RunRow,
    StateMutationStatus,
    WaitRecordRow,
    WaitRecordStatus,
    WorkerKind,
    read_active_wait_records_for_run,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
)
from dayu.host.durable.artifact import LocalArtifactStore
from dayu.host._event_payload import (
    payload_object as _payload_object,
)
from dayu.host._event_payload import (
    required_payload_text as _required_payload_text,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.memory import MemoryProjectionPolicy, default_memory_projection_policy
from dayu.host.memory_repair import catch_up_conversation_memory_projection
from dayu.host.run_input import (
    CompactArtifactView,
    CurrentRunFacts,
    MemorySnapshotView,
    SessionContinuityView,
    build_run_input_material_blocks,
)
from dayu.host.payload_resolution import event_payload_object
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_LOGGER = logging.getLogger(__name__)
_DELTA_ENGINE_EVENT_TYPES = frozenset(
    {
        EngineEventType.CONTENT_DELTA,
        EngineEventType.REASONING_DELTA,
    }
)
_EVENT_SOURCE = "host.engine_ingest"
_EVENT_ACTOR = "host.engine_ingest"
_EVENT_ID_PREFIX = "event-engine-"
_PAYLOAD_REF_PREFIX = "payload-engine-terminal"
_PAYLOAD_ID_PREFIX = "sqlite-payload-engine-terminal"
_EVENT_TYPE_ENGINE_EVENT_REJECTED = "ENGINE_EVENT_REJECTED"
_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC = "ENGINE_EVENT_DIAGNOSTIC"
_EVENT_TYPE_PROVIDER_PROTOCOL_ERROR = "PROVIDER_PROTOCOL_ERROR"
_EVENT_TYPE_ATTEMPT_SUCCEEDED = "ATTEMPT_SUCCEEDED"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_ATTEMPT_FAILED = "ATTEMPT_FAILED"
_EVENT_TYPE_RUN_FAILED = "RUN_FAILED"
_EVENT_TYPE_ATTEMPT_CANCELLED = "ATTEMPT_CANCELLED"
_EVENT_TYPE_RUN_CANCELLED = "RUN_CANCELLED"
_EVENT_TYPE_ATTEMPT_LOST = "ATTEMPT_LOST"
_EVENT_TYPE_RUN_LOST = "RUN_LOST"
_EVENT_TYPE_RUN_CANCELLING = "RUN_CANCELLING"
_EVENT_TYPE_RUN_RECOVERING = "RUN_RECOVERING"
_EVENT_TYPE_TOOL_AWAITING = "TOOL_AWAITING"
_EVENT_TYPE_RUN_WAITING = "RUN_WAITING"
_EVENT_TYPE_ATTEMPT_SUSPENDED = "ATTEMPT_SUSPENDED"
_REASON_FINAL_ANSWER = "final_answer"
_REASON_UNSUPPORTED_RECOVERY_POLICY = "unsupported_recovery_policy"
_REASON_UNSUPPORTED_WAITING_PATH = "unsupported_waiting_path"
_REASON_STREAM_ENDED_WITHOUT_TERMINAL = "stream_ended_without_terminal"
_REASON_WORKER_LOST_BEFORE_TERMINAL = "worker_lost_before_terminal"
_REASON_EMPTY_FINAL_ANSWER = "empty_final_answer"
_REASON_STALE_EXECUTION_ID = "stale_execution_id"
_REASON_TERMINAL_ALREADY_CLOSED = "terminal_already_closed"
_REASON_WAITING_EVENT_CONFIRMATION = "waiting_event_confirmation"
_REASON_WAITING_EVENT_WITHOUT_HOST_ACCEPTED_REFS = (
    "waiting_event_without_host_accepted_refs"
)
_REASON_RUN_CANCELLED_INVALID_ACTIVE_CANCEL_PAYLOAD = (
    "run_cancelled_invalid_active_cancel_payload"
)
_REASON_CONTEXT_COMPACTION_REQUIRED = "context_compaction_required"
_REASON_CONTEXT_COMPACTION_RECOVERY_FAILED = "context_compaction_recovery_failed"
_RECOVERY_FAILURE_POLICY_DECISION = "reactive_compact_failed"
_REACTIVE_PRECONDITION_OPERATION_PREFIX = "reactive_precondition"
_OWNER_PHASE7 = "phase7"
_OWNER_PHASE10 = "phase10"
_DEFAULT_MEMORY_PROJECTION_CATCHUP_BATCH_SIZE = 100
_NO_CONTEXT_BUDGET_POLICY_REF = "none"
_USAGE_OBSERVATION_STATUS_USAGE_INVALID = "usage_invalid"


class EngineIngestStatus(StrEnum):
    """Engine ingest 结果状态。"""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class LocalEngineEnvelope:
    """Host-owned 本地 Engine envelope。

    :param session_id: Host durable Session id。
    :param run_id: Host durable Run id。
    :param attempt_id: Host durable Attempt id。
    :param execution_id: Host durable execution id。
    :param dispatch_record_id: Host durable dispatch record id。
    :param worker_kind: worker 类型。
    :param execution_target: dispatch execution target。
    :param local_worker_id: 本地 worker 诊断 id。
    :param cancellation_token: Host 注入 Engine 的取消观察 token。
    """

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str
    worker_kind: WorkerKind
    execution_target: str
    local_worker_id: str
    cancellation_token: CancellationToken


@dataclass(frozen=True, slots=True)
class EngineEventCandidate:
    """进入 Host ingest 的 EngineEvent candidate。

    :param envelope: Host-owned identity envelope。
    :param worker_event_index: 单个 execution 内 Host 分配的 worker event 序号，从 1 开始。
    :param engine_event: Engine 公共事件。
    :param observed_at: Host 观察到事件的 UTC aware 时间。
    """

    envelope: LocalEngineEnvelope
    worker_event_index: int
    engine_event: EngineEvent
    observed_at: datetime


@dataclass(frozen=True, slots=True)
class EngineIngestResult:
    """EngineEvent ingest 结果。

    :param status: 本次 ingest 状态。
    :param events: 本次接受或命中重复的 EventLog rows。
    :param terminal_closeout: 本次是否完成 Run terminal closeout。
    :param promotion_triggered: terminal closeout 成功后是否触发 queue promotion wakeup。
    :param reason: 诊断 reason；无时为 ``None``。
    :param stop_worker_stream: 本次是否要求 scheduler 停止当前 worker stream。
    """

    status: EngineIngestStatus
    events: tuple[EventLogRow, ...]
    terminal_closeout: bool
    promotion_triggered: bool
    reason: str | None
    stop_worker_stream: bool = False


@dataclass(frozen=True, slots=True)
class _ValidatedCandidate:
    """已通过 durable identity 校验的 candidate 上下文。"""

    candidate: EngineEventCandidate
    run: RunRow
    attempt: AttemptRow
    dispatch_record: DispatchRecordRow


@dataclass(frozen=True, slots=True)
class _TerminalPlan:
    """terminal closeout 事件规划。"""

    attempt_event_type: str
    run_event_type: str
    attempt_status: AttemptStatus
    run_status: RunStatus
    reason: str
    terminal_summary: Mapping[str, JsonValue]
    finish_reason: str | None
    filtered: bool | None
    degraded: bool | None
    error_code: str | None
    message: str | None
    provider_request_id: str | None
    client_correlation_id: str | None
    recoverable: bool | None
    unsupported_later_owner: str | None
    worker_lifecycle_signal: str | None
    stream_error_code: str | None
    last_observed_worker_event_index: int | None
    last_accepted_event_id: str | None


@dataclass(frozen=True, slots=True)
class _WaitingConfirmationCheck:
    """Engine waiting confirmation 与 Host accepted refs 的匹配结果。

    :param accepted: 是否可作为已接受等待的确认。
    :param wait_record: 匹配到的 active wait record；未匹配时为 ``None``。
    :param mismatch_reason: 未确认时的内部诊断原因；确认成功时为 ``None``。
    """

    accepted: bool
    wait_record: WaitRecordRow | None
    mismatch_reason: str | None


@dataclass(frozen=True, slots=True)
class _AcceptedWaitingRefs:
    """Host accepted waiting refs 的已校验视图。

    :param tool_awaiting_payload: ``TOOL_AWAITING`` canonical payload。
    """

    tool_awaiting_payload: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class _ReactiveRecoveryAccepted:
    """reactive recovery 允许创建新 Attempt 的待启动摘要。

    :param result: 已提交 recovery 前置 facts 的 ingest 结果。
    :param run_id: 目标 Run id。
    :param session_id: Session id。
    :param source_attempt_id: 已关闭的旧 Attempt id。
    :param compacted_event_id: accepted compact event id；fallback recovery 为
        ``None``。
    :param compacted_event_sequence: accepted compact event sequence；fallback
        recovery 为 ``None``。
    """

    result: EngineIngestResult
    run_id: str
    session_id: str
    source_attempt_id: str
    compacted_event_id: str | None
    compacted_event_sequence: int | None


@dataclass(frozen=True, slots=True)
class _ReactiveCompactPending:
    """已写入 request/closeout、待事务外执行的 reactive compact。

    :param result_prefix: request / closeout 已提交后的结果前缀。
    :param context: Engine event durable context。
    :param expected_input_event_sequence: 冻结 ordinary material list 对应 cursor。
    :param display_text: 当前输入展示文本。
    :param frozen_material_blocks: overflow 时冻结的 ordinary input material list。
    :param frozen_material_list_digest: 冻结 material list digest。
    :param frozen_material_refs: 冻结 material source refs。
    :param operation_id: request fact event id。
    :param estimate: reactive compact 前估算。
    :param decision: reactive compact 前预算决策。
    :param policy: reactive context budget policy。
    :param selected_recent_window_turn_floor: fallback selected recent-window turn floor。
    """

    result_prefix: EngineIngestResult
    context: _ValidatedCandidate
    expected_input_event_sequence: int
    display_text: str
    frozen_material_blocks: tuple[RunInputMaterialBlock, ...]
    frozen_material_list_digest: str
    frozen_material_refs: tuple[str, ...]
    operation_id: str
    estimate: BudgetEstimate
    decision: ContextBudgetDecision
    policy: ContextBudgetPolicy
    selected_recent_window_turn_floor: int


@dataclass(frozen=True, slots=True)
class _ReactiveRecoveryStarted:
    """reactive recovery start 后的 dispatch 摘要。"""

    result: EngineIngestResult
    pending_dispatch: PendingDispatchRecord


@dataclass(frozen=True, slots=True)
class _ReactiveFallbackDecision:
    """reactive compact failed 后的 deterministic fallback 决策。

    :param action: fallback 动作。
    :param policy_decision: fallback policy decision。
    :param input_window: fallback input window 诊断。
    :param input_digest: fallback input window digest。
    :param budget_result: fallback budget 诊断。
    """

    action: str
    policy_decision: str
    input_window: Mapping[str, JsonValue]
    input_digest: str
    budget_result: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class _StartReactiveRecoveryOperation:
    """reactive recovery accepted 后的 start transaction。"""

    event_log_store: EventLogStore
    accepted: _ReactiveRecoveryAccepted

    def __call__(self, transaction: HostTransaction) -> _ReactiveRecoveryStarted:
        """执行 recovery start transaction。

        :param transaction: 当前 Host transaction。
        :returns: recovery started 摘要。
        :raises HostDurableError: transition precondition 失败时抛出。
        """

        attempt_id = _new_id("attempt-recovery")
        execution_id = _new_id("execution-recovery")
        dispatch_record_id = _new_id("dispatch-recovery")
        run_started_event_id = _new_id("event-run-started-recovery")
        attempt_started_event_id = _new_id("event-attempt-started-recovery")
        result = start_recovery_run_with_starting_attempt_in_transaction(
            transaction,
            self.event_log_store,
            StartRecoveryRunInput(
                run_id=self.accepted.run_id,
                source_attempt_id=self.accepted.source_attempt_id,
                run_started_event_id=run_started_event_id,
                attempt_started_event_id=attempt_started_event_id,
                attempt_id=attempt_id,
                execution_id=execution_id,
                dispatch_record_id=dispatch_record_id,
                occurred_at=datetime.now(UTC),
                actor=_EVENT_ACTOR,
                source=_EVENT_SOURCE,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
                context_compacted_event_id=self.accepted.compacted_event_id,
                context_compacted_event_sequence=(
                    self.accepted.compacted_event_sequence
                ),
            ),
        )
        if (
            result.status != StateMutationStatus.UPDATED
            or result.run is None
            or result.attempt is None
            or result.dispatch_record is None
        ):
            raise HostDurableError("reactive recovery start precondition failed")
        rows = _existing_rows(
            self.event_log_store,
            transaction,
            (run_started_event_id, attempt_started_event_id),
        )
        pending_dispatch = PendingDispatchRecord(
            dispatch_record_id=result.dispatch_record.dispatch_record_id,
            run_id=result.run.run_id,
            attempt_id=result.attempt.attempt_id,
            execution_id=result.attempt.execution_id,
            execution_target=result.dispatch_record.execution_target,
            worker_kind=result.dispatch_record.worker_kind,
        )
        return _ReactiveRecoveryStarted(
            result=EngineIngestResult(
                status=EngineIngestStatus.ACCEPTED,
                events=self.accepted.result.events + rows,
                terminal_closeout=False,
                promotion_triggered=False,
                reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
                stop_worker_stream=True,
            ),
            pending_dispatch=pending_dispatch,
        )


class EngineEventIngestor:
    """Host-owned EngineEvent ingest 服务。"""

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        event_log_store: EventLogStore | None = None,
        payload_store: PayloadStore | None = None,
        wakeup_port: AdmissionWakeupPort | None = None,
        context_budget_policy: ContextBudgetPolicy | None = None,
        context_compactor: ContextCompactor | None = None,
        compact_artifact_root: Path | None = None,
        compact_artifact_create_parent_dirs: bool = True,
        memory_projection_policy: MemoryProjectionPolicy | None = None,
        memory_projection_catchup_batch_size: int = (
            _DEFAULT_MEMORY_PROJECTION_CATCHUP_BATCH_SIZE
        ),
    ) -> None:
        """初始化 EngineEvent ingestor。

        :param transaction_runner: Host durable transaction runner。
        :param event_log_store: EventLog primitive。
        :param payload_store: payload descriptor primitive。
        :param wakeup_port: terminal closeout 后的 queue promotion wakeup 端口。
        :param context_budget_policy: reactive context governance policy。
        :param context_compactor: reactive context compactor。
        :param compact_artifact_root: compact artifact 根目录。
        :param compact_artifact_create_parent_dirs: artifact 根目录缺失时是否创建。
        :param memory_projection_policy: compact accepted 后的 memory projection policy。
        :param memory_projection_catchup_batch_size: memory projection catch-up 批大小。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._event_log_store = (
            event_log_store if event_log_store is not None else EventLogStore()
        )
        self._payload_store = (
            payload_store if payload_store is not None else PayloadStore()
        )
        self._wakeup_port = (
            wakeup_port if wakeup_port is not None else NoopAdmissionWakeupPort()
        )
        self._context_budget_policy = context_budget_policy
        self._context_compactor = context_compactor
        self._compact_artifact_root = compact_artifact_root
        self._compact_artifact_create_parent_dirs = compact_artifact_create_parent_dirs
        self._memory_projection_policy = (
            memory_projection_policy
            if memory_projection_policy is not None
            else default_memory_projection_policy()
        )
        self._memory_projection_catchup_batch_size = (
            memory_projection_catchup_batch_size
        )

    def ingest(self, candidate: EngineEventCandidate) -> EngineIngestResult:
        """同步接收一个不需要 reactive compaction 的 EngineEvent candidate。

        :param candidate: 待 ingest 的 EngineEvent candidate。
        :returns: ingest 结果。
        :raises ValueError: candidate envelope、时间戳或 event index 非法时抛出。
        :raises RuntimeError: candidate 触发 reactive compaction 时抛出。
        :raises HostDurableError: durable 写入或状态 CAS 失败时抛出。
        """

        result = self._ingest_before_reactive_compaction(candidate)
        if isinstance(result, _ReactiveCompactPending):
            raise RuntimeError("reactive context compaction requires ingest_async")
        if isinstance(result, _ReactiveRecoveryAccepted):
            result = self._complete_reactive_recovery(result)
        return self._finish_ingest(
            result,
            candidate=candidate,
            promotion_triggered_session_id=candidate.envelope.session_id,
        )

    async def ingest_async(
        self, candidate: EngineEventCandidate
    ) -> EngineIngestResult:
        """接收一个可执行 reactive compaction 的 EngineEvent candidate。

        :param candidate: 待 ingest 的 EngineEvent candidate。
        :returns: ingest 结果。
        :raises ValueError: candidate envelope、时间戳或 event index 非法时抛出。
        :raises HostDurableError: durable 写入或状态 CAS 失败时抛出。
        """

        result = self._ingest_before_reactive_compaction(candidate)
        if isinstance(result, _ReactiveCompactPending):
            result = await self._execute_reactive_compaction(result)
        if isinstance(result, _ReactiveRecoveryAccepted):
            result = self._complete_reactive_recovery(result)
        return self._finish_ingest(
            result,
            candidate=candidate,
            promotion_triggered_session_id=candidate.envelope.session_id,
        )

    def _ingest_before_reactive_compaction(
        self, candidate: EngineEventCandidate
    ) -> EngineIngestResult | _ReactiveRecoveryAccepted | _ReactiveCompactPending:
        """执行 reactive compaction 前的同步 ingest 事务。

        :param candidate: 待 ingest 的 EngineEvent candidate。
        :returns: ingest 结果、reactive recovery 摘要或待 compact 摘要。
        """

        _validate_candidate_shape(candidate)
        _LOGGER.log(
            _engine_ingest_log_level(candidate.engine_event.type),
            (
                "host.engine_ingest.accepted session_id=%s run_id=%s "
                "attempt_id=%s execution_id=%s worker_event_index=%s "
                "engine_event_type=%s"
            ),
            candidate.envelope.session_id,
            candidate.envelope.run_id,
            candidate.envelope.attempt_id,
            candidate.envelope.execution_id,
            candidate.worker_event_index,
            candidate.engine_event.type.value,
        )

        def _operation(
            transaction: HostTransaction,
        ) -> EngineIngestResult | _ReactiveRecoveryAccepted | _ReactiveCompactPending:
            context = self._validate_durable_context(transaction, candidate)
            if context is None:
                return self._append_rejected_diagnostic(
                    transaction,
                    candidate=candidate,
                    reason=_REASON_STALE_EXECUTION_ID,
                )
            duplicate = self._duplicate_terminal_result(transaction, context)
            if duplicate is not None:
                return duplicate
            late = _late_rejection_reason(context)
            if late is not None:
                return self._append_rejected_diagnostic(
                    transaction,
                    candidate=candidate,
                    reason=late,
                )
            return self._ingest_validated(transaction, context)

        return self._transaction_runner.run_write(_operation)

    def _finish_ingest(
        self,
        result: EngineIngestResult,
        *,
        candidate: EngineEventCandidate,
        promotion_triggered_session_id: str,
    ) -> EngineIngestResult:
        """完成 ingest 后的 promotion 与日志记录。

        :param result: 已完成 reactive recovery 处理的 ingest 结果。
        :param candidate: 原始 Engine event candidate。
        :param promotion_triggered_session_id: terminal promotion 的 Session id。
        :returns: 最终 ingest 结果。
        """

        promoted = self._with_terminal_promotion_retry(
            result,
            session_id=promotion_triggered_session_id,
        )
        _LOGGER.log(
            _engine_ingest_log_level(candidate.engine_event.type),
            (
                "host.engine_ingest.committed session_id=%s run_id=%s "
                "attempt_id=%s execution_id=%s worker_event_index=%s "
                "engine_event_type=%s ingest_status=%s event_count=%s "
                "terminal_closeout=%s promotion_triggered=%s reason=%s"
            ),
            candidate.envelope.session_id,
            candidate.envelope.run_id,
            candidate.envelope.attempt_id,
            candidate.envelope.execution_id,
            candidate.worker_event_index,
            candidate.engine_event.type.value,
            promoted.status.value,
            len(promoted.events),
            promoted.terminal_closeout,
            promoted.promotion_triggered,
            promoted.reason,
        )
        return promoted

    def _duplicate_terminal_result(
        self, transaction: HostTransaction, context: _ValidatedCandidate
    ) -> EngineIngestResult | None:
        """识别 terminal candidate 的完整重复写入。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :returns: duplicate 结果；不是完整重复时返回 ``None``。
        """

        event_ids = _duplicate_terminal_event_ids(context.candidate)
        if event_ids == ():
            return None
        existing = _existing_rows(self._event_log_store, transaction, event_ids)
        if len(existing) != len(event_ids):
            return None
        if (
            context.candidate.engine_event.type
            == EngineEventType.CONTEXT_COMPACTION_REQUESTED
        ):
            return EngineIngestResult(
                status=EngineIngestStatus.DUPLICATE,
                events=existing,
                terminal_closeout=False,
                promotion_triggered=False,
                reason="duplicate_candidate",
                stop_worker_stream=True,
            )
        return EngineIngestResult(
            status=EngineIngestStatus.DUPLICATE,
            events=existing,
            terminal_closeout=True,
            promotion_triggered=False,
            reason="duplicate_candidate",
        )

    def close_clean_eof(
        self,
        envelope: LocalEngineEnvelope,
        *,
        observed_at: datetime,
        last_observed_worker_event_index: int,
    ) -> EngineIngestResult:
        """Engine stream clean EOF 但未见 terminal 时失败收口。

        :param envelope: Host-owned identity envelope。
        :param observed_at: Host 观察到 EOF 的 UTC aware 时间。
        :param last_observed_worker_event_index: 最后观察到的 worker event index。
        :returns: closeout 结果。
        :raises ValueError: envelope 或时间戳非法时抛出。
        """

        _validate_observed_at(observed_at)
        if last_observed_worker_event_index < 0:
            raise ValueError("last_observed_worker_event_index must be non-negative")
        return self._close_worker_lifecycle(
            envelope,
            observed_at=observed_at,
            event_index=last_observed_worker_event_index + 1,
            plan=_failed_lifecycle_plan(
                reason=_REASON_STREAM_ENDED_WITHOUT_TERMINAL,
                last_observed_worker_event_index=last_observed_worker_event_index,
            ),
        )

    def close_worker_lost(
        self,
        envelope: LocalEngineEnvelope,
        *,
        observed_at: datetime,
        worker_lifecycle_signal: str,
        stream_error_code: str | None,
        last_observed_worker_event_index: int,
        last_accepted_event_id: str | None = None,
    ) -> EngineIngestResult:
        """Engine stream error、worker crash 或 terminal unknown 时 lost 收口。

        :param envelope: Host-owned identity envelope。
        :param observed_at: Host 观察到 worker lost 的 UTC aware 时间。
        :param worker_lifecycle_signal: worker lifecycle signal。
        :param stream_error_code: stream error code；无时为 ``None``。
        :param last_observed_worker_event_index: 最后观察到的 worker event index。
        :param last_accepted_event_id: 最后已接受 EventLog id；无时为 ``None``。
        :returns: closeout 结果。
        :raises ValueError: 输入字段非法时抛出。
        """

        _validate_observed_at(observed_at)
        if worker_lifecycle_signal.strip() == "":
            raise ValueError("worker_lifecycle_signal must be non-empty")
        if last_observed_worker_event_index < 0:
            raise ValueError("last_observed_worker_event_index must be non-negative")
        return self._close_worker_lifecycle(
            envelope,
            observed_at=observed_at,
            event_index=last_observed_worker_event_index + 1,
            plan=_lost_lifecycle_plan(
                worker_lifecycle_signal=worker_lifecycle_signal,
                stream_error_code=stream_error_code,
                last_observed_worker_event_index=last_observed_worker_event_index,
                last_accepted_event_id=last_accepted_event_id,
            ),
        )

    def _ingest_validated(
        self, transaction: HostTransaction, context: _ValidatedCandidate
    ) -> EngineIngestResult | _ReactiveRecoveryAccepted | _ReactiveCompactPending:
        """处理已通过 durable 校验的 candidate。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :returns: ingest 结果。
        """

        event = context.candidate.engine_event
        if event.type == EngineEventType.FINAL_ANSWER and isinstance(
            event.data, FinalAnswerData
        ):
            return self._close_terminal(
                transaction,
                context,
                _final_answer_plan(event.data),
            )
        if event.type == EngineEventType.RUN_FAILED and isinstance(
            event.data, RunFailedData
        ):
            if event.data.recoverable:
                diagnostic = self._append_diagnostic_event(
                    transaction,
                    context=context,
                    event_type=_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC,
                    reason=_REASON_UNSUPPORTED_RECOVERY_POLICY,
                    payload={
                        "attempt_id": context.attempt.attempt_id,
                        "execution_id": context.attempt.execution_id,
                        "error_code": event.data.error_code,
                        "message": event.data.message,
                        "provider_request_id": event.data.provider_request_id,
                        "client_correlation_id": event.data.client_correlation_id,
                        "recoverable": True,
                        "unsupported_later_owner": _OWNER_PHASE10,
                    },
                    sub_index=0,
                )
                closeout = self._close_terminal(
                    transaction,
                    context,
                    _run_failed_plan(event.data),
                    sub_index_offset=1,
                )
                return _merge_diagnostic_and_closeout(diagnostic, closeout)
            return self._close_terminal(
                transaction,
                context,
                _run_failed_plan(event.data),
            )
        if event.type == EngineEventType.RUN_CANCELLED and isinstance(
            event.data, RunCancelledData
        ):
            return self._close_active_cancel(transaction, context, event.data)
        if event.type == EngineEventType.CONTEXT_COMPACTION_REQUESTED and isinstance(
            event.data, ContextCompactionRequestedData
        ):
            return self._start_reactive_context_recovery(
                transaction, context, event.data
            )
        if event.type == EngineEventType.RUN_SUSPENDED and isinstance(
            event.data, RunSuspendedData
        ):
            return self._confirm_waiting_engine_event(
                transaction,
                context,
                event.data,
                _run_suspended_payload(context, event.data),
            )
        if event.type == EngineEventType.TOOL_AWAITING and isinstance(
            event.data, ToolAwaitingData
        ):
            return self._confirm_waiting_engine_event(
                transaction,
                context,
                event.data,
                _tool_awaiting_payload(context, event.data),
            )
        if event.type == EngineEventType.USAGE_REPORTED and isinstance(
            event.data, UsageReportedData
        ):
            row = self._append_projection_signal(transaction, context, event.data)
            return _single_event_result(row)
        if _is_preview_event(event):
            row = self._append_preview_event(transaction, context)
            return _single_event_result(row)
        if event.type == EngineEventType.PROVIDER_PROTOCOL_ERROR and isinstance(
            event.data, ProviderProtocolErrorData
        ):
            row = self._append_provider_protocol_error(transaction, context, event.data)
            return _single_event_result(row)
        return self._append_rejected_diagnostic(
            transaction,
            candidate=context.candidate,
            reason="unsupported_engine_event_type",
            stop_worker_stream=True,
        )

    def _validate_durable_context(
        self, transaction: HostTransaction, candidate: EngineEventCandidate
    ) -> _ValidatedCandidate | None:
        """校验 candidate 与 durable Run / Attempt / dispatch 是否同源。

        :param transaction: 当前 Host transaction。
        :param candidate: 待校验 candidate。
        :returns: 校验通过的上下文；不匹配时返回 ``None``。
        """

        envelope = candidate.envelope
        run = read_run_by_id(transaction, envelope.run_id)
        attempt = read_attempt_by_id(transaction, envelope.attempt_id)
        dispatch_record = read_dispatch_record_by_attempt_id(
            transaction, envelope.attempt_id
        )
        if run is None or attempt is None or dispatch_record is None:
            return None
        if (
            run.session_id != envelope.session_id
            or run.run_id != envelope.run_id
            or run.current_attempt_id != envelope.attempt_id
            or attempt.run_id != envelope.run_id
            or attempt.execution_id != envelope.execution_id
            or dispatch_record.dispatch_record_id != envelope.dispatch_record_id
            or dispatch_record.execution_id != envelope.execution_id
        ):
            return None
        return _ValidatedCandidate(
            candidate=candidate,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        )

    def _close_terminal(
        self,
        transaction: HostTransaction,
        context: _ValidatedCandidate,
        plan: _TerminalPlan,
        *,
        sub_index_offset: int = 0,
    ) -> EngineIngestResult:
        """按 terminal plan 写入 Attempt / Run terminal facts。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param plan: terminal closeout 规划。
        :param sub_index_offset: 多事件映射时的 sub-index 偏移。
        :returns: ingest 结果。
        """

        candidate = context.candidate
        attempt_event_id = _event_id(
            candidate,
            EventClass.CANONICAL_FACT,
            plan.attempt_event_type,
            sub_index_offset,
        )
        run_event_id = _event_id(
            candidate,
            EventClass.CANONICAL_FACT,
            plan.run_event_type,
            sub_index_offset + 1,
        )
        existing = _existing_rows(
            self._event_log_store,
            transaction,
            (attempt_event_id, run_event_id),
        )
        if len(existing) == 2:
            return EngineIngestResult(
                status=EngineIngestStatus.DUPLICATE,
                events=existing,
                terminal_closeout=True,
                promotion_triggered=False,
                reason=plan.reason,
            )
        descriptor = self._write_terminal_summary(
            transaction,
            candidate=candidate,
            event_id=attempt_event_id,
            summary=plan.terminal_summary,
        )
        result = terminal_closeout_in_transaction(
            transaction,
            self._event_log_store,
            TerminalCloseoutInput(
                run_id=context.run.run_id,
                attempt_id=context.attempt.attempt_id,
                attempt_terminal_event_id=attempt_event_id,
                run_terminal_event_id=run_event_id,
                attempt_terminal_status=plan.attempt_status,
                run_terminal_status=plan.run_status,
                occurred_at=candidate.observed_at,
                actor=_EVENT_ACTOR,
                source=_EVENT_SOURCE,
                reason=plan.reason,
                terminal_summary_ref=descriptor.payload_ref,
                terminal_summary_digest=descriptor.payload_digest,
                engine_event_ref=_engine_event_ref(candidate),
                finish_reason=plan.finish_reason,
                filtered=plan.filtered,
                degraded=plan.degraded,
                error_code=plan.error_code,
                message=plan.message,
                provider_request_id=plan.provider_request_id,
                client_correlation_id=plan.client_correlation_id,
                recoverable=plan.recoverable,
                unsupported_later_owner=plan.unsupported_later_owner,
                worker_lifecycle_signal=plan.worker_lifecycle_signal,
                stream_error_code=plan.stream_error_code,
                last_observed_worker_event_index=(
                    plan.last_observed_worker_event_index
                ),
                last_accepted_event_id=plan.last_accepted_event_id,
            ),
        )
        if result.status != StateMutationStatus.UPDATED:
            return EngineIngestResult(
                status=EngineIngestStatus.REJECTED,
                events=(),
                terminal_closeout=True,
                promotion_triggered=False,
                reason="terminal_closeout_precondition_failed",
            )
        rows = _existing_rows(
            self._event_log_store,
            transaction,
            (attempt_event_id, run_event_id),
        )
        return EngineIngestResult(
            status=EngineIngestStatus.ACCEPTED,
            events=rows,
            terminal_closeout=True,
            promotion_triggered=False,
            reason=plan.reason,
        )

    def _close_active_cancel(
        self,
        transaction: HostTransaction,
        context: _ValidatedCandidate,
        data: RunCancelledData,
    ) -> EngineIngestResult:
        """处理 Engine ``run_cancelled`` terminal event。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param data: Engine run_cancelled data。
        :returns: ingest 结果。
        """

        candidate = context.candidate
        attempt_event_id = _event_id(
            candidate,
            EventClass.CANONICAL_FACT,
            _EVENT_TYPE_ATTEMPT_CANCELLED,
            0,
        )
        run_event_id = _event_id(
            candidate,
            EventClass.CANONICAL_FACT,
            _EVENT_TYPE_RUN_CANCELLED,
            1,
        )
        existing = _existing_rows(
            self._event_log_store,
            transaction,
            (attempt_event_id, run_event_id),
        )
        if len(existing) == 2:
            return EngineIngestResult(
                status=EngineIngestStatus.DUPLICATE,
                events=existing,
                terminal_closeout=True,
                promotion_triggered=False,
                reason=data.reason,
            )
        cancelling = self._event_log_store.read_latest_run_event_by_type(
            transaction,
            run_id=context.run.run_id,
            event_type=_EVENT_TYPE_RUN_CANCELLING,
        )
        if cancelling is None:
            return self._append_rejected_diagnostic(
                transaction,
                candidate=candidate,
                reason="run_cancelled_without_active_cancel",
            )
        cancel_request_event_id = _cancel_request_event_id_from_cancelling(cancelling)
        if cancel_request_event_id is None:
            return self._append_rejected_diagnostic(
                transaction,
                candidate=candidate,
                reason=_REASON_RUN_CANCELLED_INVALID_ACTIVE_CANCEL_PAYLOAD,
            )
        result = active_cancel_closeout_in_transaction(
            transaction,
            self._event_log_store,
            ActiveCancelCloseoutInput(
                run_id=context.run.run_id,
                attempt_id=context.attempt.attempt_id,
                attempt_cancelled_event_id=attempt_event_id,
                run_cancelled_event_id=run_event_id,
                occurred_at=candidate.observed_at,
                actor=_EVENT_ACTOR,
                source=_EVENT_SOURCE,
                reason=data.reason,
                cancel_request_event_id=cancel_request_event_id,
                engine_event_ref=_engine_event_ref(candidate),
                requested_at=format_utc_timestamp(data.requested_at),
                accepted_at=format_utc_timestamp(data.accepted_at),
                finished_at=format_utc_timestamp(data.finished_at),
            ),
        )
        if result.status != StateMutationStatus.UPDATED:
            return EngineIngestResult(
                status=EngineIngestStatus.REJECTED,
                events=(),
                terminal_closeout=True,
                promotion_triggered=False,
                reason="active_cancel_closeout_precondition_failed",
            )
        rows = _existing_rows(
            self._event_log_store,
            transaction,
            (attempt_event_id, run_event_id),
        )
        return EngineIngestResult(
            status=EngineIngestStatus.ACCEPTED,
            events=rows,
            terminal_closeout=True,
            promotion_triggered=False,
            reason=data.reason,
        )

    def _start_reactive_context_recovery(
        self,
        transaction: HostTransaction,
        context: _ValidatedCandidate,
        data: ContextCompactionRequestedData,
    ) -> EngineIngestResult | _ReactiveCompactPending:
        """处理 Engine reactive context compaction 请求。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param data: Engine context compaction requested data。
        :returns: ingest 结果或 compact accepted 后的待启动摘要。
        """

        candidate = context.candidate
        policy = self._context_budget_policy
        if policy is None:
            return self._fail_reactive_recovery_without_request(
                transaction,
                context=context,
                data=data,
                failure_reason="context_budget_policy_missing",
                message="Context budget policy is not configured",
            )
        input_event = self._event_log_store.read_event_by_id(
            transaction, context.run.input_event_id
        )
        if input_event is None:
            return self._fail_reactive_recovery_without_request(
                transaction,
                context=context,
                data=data,
                failure_reason="input_event_missing",
                message="Input event is missing before reactive recovery",
            )
        display_text = _display_text_from_input_event(transaction, input_event)
        estimate = estimate_context_budget(
            policy,
            BudgetEstimateInput(
                session_id=context.run.session_id,
                run_id=context.run.run_id,
                message_fragments=(
                    BudgetTextFragment(
                        fragment_ref=context.run.input_event_id,
                        text=display_text,
                    ),
                ),
                current_prompt_ref=context.run.input_event_id,
            ),
        )
        decision = decide_context_budget(estimate)
        try:
            compact_count = self._committed_reactive_compact_count(
                transaction, context.run
            )
        except Exception:
            return self._fail_reactive_recovery_without_request(
                transaction,
                context=context,
                data=data,
                failure_reason="reactive_compact_count_unreadable",
                message="Committed reactive compact facts are unreadable",
                estimate=estimate,
            )
        if compact_count >= policy.max_reactive_compactions_per_run:
            return self._fail_reactive_recovery_without_request(
                transaction,
                context=context,
                data=data,
                failure_reason="reactive_compact_limit_reached",
                message="Run already used its reactive compaction budget",
                estimate=estimate,
            )
        frozen_material_blocks = _frozen_reactive_material_blocks(
            transaction=transaction,
            context=context,
            display_text=display_text,
        )
        frozen_material_list_digest = _material_list_digest(frozen_material_blocks)
        frozen_material_refs = _material_source_refs(frozen_material_blocks)
        requested = self._append_reactive_compaction_requested_event(
            transaction,
            context=context,
            data=data,
            estimate=estimate,
            decision=decision,
            frozen_material_list_digest=frozen_material_list_digest,
            frozen_material_refs=frozen_material_refs,
        )
        closeout = self._close_attempt_for_context_recovery(
            transaction,
            context=context,
            data=data,
            sub_index_offset=1,
        )
        if closeout.status is not EngineIngestStatus.ACCEPTED:
            return closeout
        return _ReactiveCompactPending(
            result_prefix=EngineIngestResult(
                status=EngineIngestStatus.ACCEPTED,
                events=(requested, *closeout.events),
                terminal_closeout=False,
                promotion_triggered=False,
                reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
                stop_worker_stream=True,
            ),
            context=context,
            expected_input_event_sequence=context.run.input_event_sequence,
            display_text=display_text,
            frozen_material_blocks=frozen_material_blocks,
            frozen_material_list_digest=frozen_material_list_digest,
            frozen_material_refs=frozen_material_refs,
            operation_id=requested.event_id,
            estimate=estimate,
            decision=decision,
            policy=policy,
            selected_recent_window_turn_floor=(
                self._memory_projection_policy.selected_recent_window_turn_floor
            ),
        )

    def _fail_reactive_recovery_without_request(
        self,
        transaction: HostTransaction,
        *,
        context: _ValidatedCandidate,
        data: ContextCompactionRequestedData,
        failure_reason: str,
        message: str,
        estimate: BudgetEstimate | None = None,
    ) -> EngineIngestResult:
        """不追加新 request fact，关闭旧 Attempt 后失败收口 Run。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param data: Engine context compaction requested data。
        :param failure_reason: compact failure reason。
        :param message: failure message。
        :param estimate: 可选 Host budget estimate。
        :returns: ingest 结果。
        """

        closeout = self._close_attempt_for_context_recovery(
            transaction,
            context=context,
            data=data,
            sub_index_offset=1,
        )
        if closeout.status is not EngineIngestStatus.ACCEPTED:
            return closeout
        failed = self._append_reactive_compaction_failed_event(
            transaction,
            context=context,
            estimate=estimate,
            operation_id=_reactive_precondition_compaction_operation_id(
                context=context,
                failure_reason=failure_reason,
            ),
            failure_reason=failure_reason,
            attempt_count=0,
            retry_repair_budget_exhausted=False,
            budget_after_attempted_compact=None,
        )
        run_failed = self._fail_recovering_run(
            transaction,
            context=context,
            failed_event=failed,
            error_code=failure_reason,
            message=message,
        )
        return EngineIngestResult(
            status=EngineIngestStatus.ACCEPTED,
            events=(*closeout.events, failed, *run_failed.events),
            terminal_closeout=True,
            promotion_triggered=False,
            reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
        )

    def _close_attempt_for_context_recovery(
        self,
        transaction: HostTransaction,
        *,
        context: _ValidatedCandidate,
        data: ContextCompactionRequestedData,
        sub_index_offset: int,
    ) -> EngineIngestResult:
        """关闭当前 Attempt 并写入 ``RUN_RECOVERING``。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param data: Engine context compaction requested data。
        :param sub_index_offset: 事件 id sub-index 起点。
        :returns: ingest 结果。
        """

        candidate = context.candidate
        attempt_event_id = _event_id(
            candidate,
            EventClass.CANONICAL_FACT,
            _EVENT_TYPE_ATTEMPT_FAILED,
            sub_index_offset,
        )
        recovering_event_id = _event_id(
            candidate,
            EventClass.CANONICAL_FACT,
            _EVENT_TYPE_RUN_RECOVERING,
            sub_index_offset + 1,
        )
        existing = _existing_rows(
            self._event_log_store,
            transaction,
            (attempt_event_id, recovering_event_id),
        )
        if len(existing) == 2:
            return EngineIngestResult(
                status=EngineIngestStatus.DUPLICATE,
                events=existing,
                terminal_closeout=True,
                promotion_triggered=False,
                reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
            )
        result = close_attempt_for_context_recovery_in_transaction(
            transaction,
            self._event_log_store,
            ContextRecoveryCloseInput(
                run_id=context.run.run_id,
                attempt_id=context.attempt.attempt_id,
                attempt_failed_event_id=attempt_event_id,
                run_recovering_event_id=recovering_event_id,
                occurred_at=candidate.observed_at,
                actor=_EVENT_ACTOR,
                source=_EVENT_SOURCE,
                reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
                engine_event_ref=_engine_event_ref(candidate),
                provider_request_id=data.provider_request_id,
                client_correlation_id=data.client_correlation_id,
                message=data.reason,
            ),
        )
        if result.status != StateMutationStatus.UPDATED:
            return EngineIngestResult(
                status=EngineIngestStatus.REJECTED,
                events=(),
                terminal_closeout=True,
                promotion_triggered=False,
                reason="context_recovery_close_precondition_failed",
            )
        rows = _existing_rows(
            self._event_log_store,
            transaction,
            (attempt_event_id, recovering_event_id),
        )
        return EngineIngestResult(
            status=EngineIngestStatus.ACCEPTED,
            events=rows,
            terminal_closeout=True,
            promotion_triggered=False,
            reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
        )

    def _committed_reactive_compact_count(
        self, transaction: HostTransaction, run: RunRow
    ) -> int:
        """读取本 Run 已提交 reactive compact request 数。

        :param transaction: 当前 Host transaction。
        :param run: 目标 Run。
        :returns: reactive request 数。
        """

        return self._event_log_store.count_committed_events_by_run_and_type(
            transaction,
            run_id=run.run_id,
            event_type=CONTEXT_COMPACTION_REQUESTED,
            payload_filter=EventPayloadTextEqualsFilter(
                field_name="trigger_source",
                expected_value=ContextCompactionTriggerSource.REACTIVE.value,
                allowed_values=(
                    ContextCompactionTriggerSource.PROACTIVE.value,
                    ContextCompactionTriggerSource.REACTIVE.value,
                ),
            ),
        )

    def _append_reactive_compaction_requested_event(
        self,
        transaction: HostTransaction,
        *,
        context: _ValidatedCandidate,
        data: ContextCompactionRequestedData,
        estimate: BudgetEstimate,
        decision: ContextBudgetDecision,
        frozen_material_list_digest: str,
        frozen_material_refs: tuple[str, ...],
    ) -> EventLogRow:
        """追加 reactive ``CONTEXT_COMPACTION_REQUESTED`` fact。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param data: Engine context compaction requested data。
        :param estimate: Host budget estimate。
        :param decision: Host budget decision。
        :param frozen_material_list_digest: overflow material list digest。
        :param frozen_material_refs: overflow material source refs。
        :returns: EventLog row。
        """

        candidate = context.candidate
        policy_ref = (
            self._context_budget_policy.policy_ref
            if self._context_budget_policy is not None
            else "none"
        )
        return self._event_log_store.append_event(
            transaction,
            EventLogAppendRequest(
                event_id=_event_id(
                    candidate,
                    EventClass.CANONICAL_FACT,
                    CONTEXT_COMPACTION_REQUESTED,
                    0,
                ),
                event_class=EventClass.CANONICAL_FACT,
                session_id=context.run.session_id,
                run_id=context.run.run_id,
                attempt_id=context.attempt.attempt_id,
                execution_id=context.attempt.execution_id,
                event_type=CONTEXT_COMPACTION_REQUESTED,
                occurred_at=candidate.observed_at,
                actor=_EVENT_ACTOR,
                source=_EVENT_SOURCE,
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason={"decision": decision.value, "engine_reason": data.reason},
                payload_json={
                    **build_context_compaction_requested_payload(
                        trigger_source=ContextCompactionTriggerSource.REACTIVE,
                        budget_reason=data.reason,
                        budget_snapshot_ref=estimate.estimator_digest,
                        input_snapshot_cursor=context.run.input_event_sequence,
                        estimator_digest=estimate.estimator_digest,
                        policy_ref=policy_ref,
                        provider_request_id=data.provider_request_id,
                        provider_error_ref=_engine_event_ref(candidate),
                        attempt_id=context.attempt.attempt_id,
                        execution_id=context.attempt.execution_id,
                        frozen_material_list_digest=frozen_material_list_digest,
                        frozen_material_refs=frozen_material_refs,
                    ),
                    "client_correlation_id": data.client_correlation_id,
                },
                payload_ref=None,
                payload_digest=None,
            ),
        ).row

    async def _execute_reactive_compaction(
        self, pending: _ReactiveCompactPending
    ) -> EngineIngestResult | _ReactiveRecoveryAccepted:
        """在事务外执行 reactive compact，并在新事务内写入结果。

        :param pending: 已写 request/closeout fact 的 reactive compact。
        :returns: ingest result 或 accepted recovery 摘要。
        """

        request = _reactive_compaction_request(pending)
        pass_queue = _reactive_compaction_pass_queue(pending, request)
        compactor = self._context_compactor
        artifact_root = self._compact_artifact_root
        if compactor is None or artifact_root is None:
            operation_result = CompactionOperationResult(
                accepted_candidate=None,
                quality_result=None,
                rejected_attempts=(),
                failure_reason="compactor_or_artifact_store_missing",
                budget_after_attempted_compact=None,
            )
        else:
            attempts = (
                self._context_budget_policy.max_compaction_attempts_per_operation
                if self._context_budget_policy is not None
                else 1
            )
            operation_result = await run_compaction_operation(
                request=request,
                compactor=compactor,
                max_attempts=attempts,
                cancellation_token=(
                    pending.context.candidate.envelope.cancellation_token
                ),
                pass_queue=pass_queue,
            )

        def _operation(
            transaction: HostTransaction,
        ) -> EngineIngestResult | _ReactiveRecoveryAccepted:
            latest = self._validate_durable_context(
                transaction, pending.context.candidate
            )
            if latest is None:
                return pending.result_prefix
            sequence_stale = (
                latest.run.input_event_sequence
                != pending.expected_input_event_sequence
            )
            if latest.run.status is RunStatus.RECOVERING and sequence_stale:
                stale_failed = self._append_reactive_compaction_failed_event(
                    transaction,
                    context=latest,
                    estimate=pending.estimate,
                    operation_id=pending.operation_id,
                    failure_reason="stale_compaction_result",
                    attempt_count=len(operation_result.rejected_attempts),
                    retry_repair_budget_exhausted=False,
                    budget_after_attempted_compact=(
                        operation_result.budget_after_attempted_compact
                    ),
                )
                return EngineIngestResult(
                    status=EngineIngestStatus.ACCEPTED,
                    events=(*pending.result_prefix.events, stale_failed),
                    terminal_closeout=False,
                    promotion_triggered=False,
                    reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
                    stop_worker_stream=True,
                )
            if (
                latest.run.status is not RunStatus.RECOVERING
                or latest.attempt.terminal_event_id is None
            ):
                return pending.result_prefix
            attempt_rows: list[EventLogRow] = []
            for rejected in operation_result.rejected_attempts:
                attempt_rows.append(
                    self._append_reactive_compaction_attempt_rejected_event(
                        transaction,
                        context=latest,
                        operation_id=pending.operation_id,
                        rejected=rejected,
                    )
                )
            if (
                operation_result.accepted_candidate is None
                or operation_result.quality_result is None
                or operation_result.failure_reason is not None
            ):
                fallback = _reactive_fallback_decision(
                    pending=pending,
                    failure_reason=(
                        operation_result.failure_reason or "compaction_failed"
                    ),
                )
                failed = self._append_reactive_compaction_failed_event(
                    transaction,
                    context=latest,
                    estimate=pending.estimate,
                    operation_id=pending.operation_id,
                    failure_reason=(
                        operation_result.failure_reason or "compaction_failed"
                    ),
                    attempt_count=len(operation_result.rejected_attempts),
                    retry_repair_budget_exhausted=(
                        len(operation_result.rejected_attempts) > 0
                    ),
                    budget_after_attempted_compact=(
                        operation_result.budget_after_attempted_compact
                    ),
                    fallback_policy_decision=fallback.policy_decision,
                    fallback_input_window=fallback.input_window,
                    fallback_input_digest=fallback.input_digest,
                    fallback_budget_result=fallback.budget_result,
                    fallback_action=fallback.action,
                )
                if fallback.action == FALLBACK_ACTION_DISPATCH:
                    return _ReactiveRecoveryAccepted(
                        result=EngineIngestResult(
                            status=EngineIngestStatus.ACCEPTED,
                            events=(
                                *pending.result_prefix.events,
                                *tuple(attempt_rows),
                                failed,
                            ),
                            terminal_closeout=False,
                            promotion_triggered=False,
                            reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
                            stop_worker_stream=True,
                        ),
                        run_id=latest.run.run_id,
                        session_id=latest.run.session_id,
                        source_attempt_id=latest.attempt.attempt_id,
                        compacted_event_id=None,
                        compacted_event_sequence=None,
                    )
                fail_result = self._fail_recovering_run(
                    transaction,
                    context=latest,
                    failed_event=failed,
                    error_code="context_compaction_failed",
                    message="Context compaction failed during reactive recovery",
                )
                return EngineIngestResult(
                    status=EngineIngestStatus.ACCEPTED,
                    events=(
                        *pending.result_prefix.events,
                        *tuple(attempt_rows),
                        failed,
                        *fail_result.events,
                    ),
                    terminal_closeout=True,
                    promotion_triggered=False,
                    reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
                )
            compacted = self._append_reactive_compacted_event(
                transaction,
                context=latest,
                request=request,
                decision=pending.decision,
                operation_id=pending.operation_id,
                accepted_attempt_number=len(operation_result.rejected_attempts) + 1,
                candidate=operation_result.accepted_candidate,
                quality=operation_result.quality_result,
                budget_after_compact=(
                    operation_result.budget_after_attempted_compact
                    if operation_result.budget_after_attempted_compact is not None
                    else pending.estimate.estimated_input_tokens
                ),
            )
            return _ReactiveRecoveryAccepted(
                result=EngineIngestResult(
                    status=EngineIngestStatus.ACCEPTED,
                    events=(
                        *pending.result_prefix.events,
                        *tuple(attempt_rows),
                        compacted,
                    ),
                    terminal_closeout=False,
                    promotion_triggered=False,
                    reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
                    stop_worker_stream=True,
                ),
                run_id=latest.run.run_id,
                session_id=latest.run.session_id,
                source_attempt_id=latest.attempt.attempt_id,
                compacted_event_id=compacted.event_id,
                compacted_event_sequence=compacted.event_sequence,
            )

        return self._transaction_runner.run_write(_operation)

    def _append_reactive_compacted_event(
        self,
        transaction: HostTransaction,
        *,
        context: _ValidatedCandidate,
        request: CompactionRequest,
        decision: ContextBudgetDecision,
        operation_id: str,
        accepted_attempt_number: int,
        candidate: ConversationCompactOutputVNext,
        quality: CompactQualityCheckResultVNext,
        budget_after_compact: int,
    ) -> EventLogRow:
        """写入 reactive accepted compact artifact 与 fact。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param request: Host compaction request。
        :param decision: compact 前预算决策。
        :param operation_id: reactive compaction request event id。
        :param accepted_attempt_number: accepted operation attempt number。
        :param candidate: accepted vNext compaction candidate。
        :param quality: accepted vNext quality result。
        :param budget_after_compact: Host 估算的 compact 后预算。
        :returns: ``CONTEXT_COMPACTED`` row。
        """

        if self._compact_artifact_root is None:
            raise RuntimeError("compact artifact root is missing")
        policy_digest = sha256_digest_json(
            {
                "policy_ref": self._context_budget_policy.policy_ref
                if self._context_budget_policy is not None
                else _NO_CONTEXT_BUDGET_POLICY_REF
            }
        )
        artifact_ref = LocalArtifactStore(
            self._compact_artifact_root,
            create_artifact_root=self._compact_artifact_create_parent_dirs,
        ).write_artifact_bytes(
            canonical_json_dumps(
                compact_artifact_json_vnext(
                    request=request,
                    candidate=candidate,
                    quality=quality,
                    policy_digest=policy_digest,
                    budget_after_compact=budget_after_compact,
                )
            ).encode("utf-8")
        )
        payload_ref = compact_artifact_payload_ref(artifact_ref.artifact_digest)
        descriptor = self._payload_store.write_payload_descriptor_for_artifact(
            transaction,
            payload_ref,
            artifact_ref,
            COMPACT_ARTIFACT_MEDIA_TYPE_VNEXT,
            compact_artifact_descriptor_metadata_vnext(
                request=request,
                candidate=candidate,
                artifact_digest=artifact_ref.artifact_digest,
                policy_digest=policy_digest,
            ),
        )
        return self._event_log_store.append_event(
            transaction,
            EventLogAppendRequest(
                event_id=_event_id(
                    context.candidate,
                    EventClass.CANONICAL_FACT,
                    CONTEXT_COMPACTED,
                    3,
                ),
                event_class=EventClass.CANONICAL_FACT,
                session_id=context.run.session_id,
                run_id=context.run.run_id,
                attempt_id=context.attempt.attempt_id,
                execution_id=context.attempt.execution_id,
                event_type=CONTEXT_COMPACTED,
                occurred_at=context.candidate.observed_at,
                actor=_EVENT_ACTOR,
                source=_EVENT_SOURCE,
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason={"decision": decision.value},
                payload_json=build_context_compacted_payload(
                    operation_id=operation_id,
                    accepted_attempt_number=accepted_attempt_number,
                    compact_artifact_ref=descriptor.payload_ref,
                    compact_artifact_digest=artifact_ref.artifact_digest,
                    accepted_candidate=candidate,
                    quality_check_result=quality,
                    budget_after_compact=budget_after_compact,
                    prompt_local_label_mapping_refs=prompt_local_label_mapping_refs(request),
                    source_boundary_refs=source_boundary_refs(request),
                    accepted_evidence_mapping_refs=accepted_evidence_mapping_refs_for_candidate(request, candidate),
                    projection_signal=COMPACT_PROJECTION_SIGNAL_MEMORY_CATCHUP,
                ),
                payload_ref=None,
                payload_digest=None,
            ),
        ).row

    def _append_reactive_compaction_failed_event(
        self,
        transaction: HostTransaction,
        *,
        context: _ValidatedCandidate,
        estimate: BudgetEstimate | None,
        operation_id: str,
        failure_reason: str,
        attempt_count: int,
        retry_repair_budget_exhausted: bool,
        budget_after_attempted_compact: int | None,
        fallback_policy_decision: str | None = None,
        fallback_input_window: Mapping[str, JsonValue] | None = None,
        fallback_input_digest: str | None = None,
        fallback_budget_result: Mapping[str, JsonValue] | None = None,
        fallback_action: str = FALLBACK_ACTION_NOT_APPLICABLE,
    ) -> EventLogRow:
        """追加 reactive ``CONTEXT_COMPACTION_FAILED`` fact。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param estimate: 可选 Host budget estimate。
        :param operation_id: compact operation 诊断 id。
        :param failure_reason: 失败原因。
        :param attempt_count: operation 内已拒绝 proposal attempt 数。
        :param retry_repair_budget_exhausted: semantic retry / repair 预算是否耗尽。
        :param budget_after_attempted_compact: compact 后估算；未知时为 ``None``。
        :param fallback_policy_decision: fallback policy decision。
        :param fallback_input_window: fallback input window 诊断。
        :param fallback_input_digest: fallback input window digest。
        :param fallback_budget_result: fallback budget 诊断。
        :param fallback_action: fallback 动作。
        :returns: EventLog row。
        """

        diagnostic_refs = (
            (_engine_event_ref(context.candidate),)
            if estimate is None
            else (_engine_event_ref(context.candidate), estimate.estimator_digest)
        )
        return self._event_log_store.append_event(
            transaction,
            EventLogAppendRequest(
                event_id=_event_id(
                    context.candidate,
                    EventClass.CANONICAL_FACT,
                    CONTEXT_COMPACTION_FAILED,
                    3,
                ),
                event_class=EventClass.CANONICAL_FACT,
                session_id=context.run.session_id,
                run_id=context.run.run_id,
                attempt_id=context.attempt.attempt_id,
                execution_id=context.attempt.execution_id,
                event_type=CONTEXT_COMPACTION_FAILED,
                occurred_at=context.candidate.observed_at,
                actor=_EVENT_ACTOR,
                source=_EVENT_SOURCE,
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason={"failure_reason": failure_reason},
                payload_json=build_context_compaction_failed_payload(
                    operation_id=operation_id,
                    failure_reason=failure_reason,
                    policy_decision=_RECOVERY_FAILURE_POLICY_DECISION,
                    retryable=False,
                    attempt_count=attempt_count,
                    retry_repair_budget_exhausted=(
                        retry_repair_budget_exhausted
                    ),
                    diagnostic_refs=diagnostic_refs,
                    budget_after_attempted_compact=budget_after_attempted_compact,
                    fallback_policy_decision=fallback_policy_decision,
                    fallback_input_window=fallback_input_window,
                    fallback_input_digest=fallback_input_digest,
                    fallback_budget_result=fallback_budget_result,
                    fallback_action=fallback_action,
                ),
                payload_ref=None,
                payload_digest=None,
            ),
        ).row

    def _append_reactive_compaction_attempt_rejected_event(
        self,
        transaction: HostTransaction,
        *,
        context: _ValidatedCandidate,
        operation_id: str,
        rejected: CompactionAttemptRejected,
    ) -> EventLogRow:
        """追加 reactive ``CONTEXT_COMPACTION_ATTEMPT_REJECTED`` fact。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param operation_id: 对应 request fact 的 stable event id。
        :param rejected: attempt reject 摘要。
        :returns: EventLog row。
        """

        return self._event_log_store.append_event(
            transaction,
            EventLogAppendRequest(
                event_id=_event_id(
                    context.candidate,
                    EventClass.CANONICAL_FACT,
                    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                    20 + rejected.attempt_number,
                ),
                event_class=EventClass.CANONICAL_FACT,
                session_id=context.run.session_id,
                run_id=context.run.run_id,
                attempt_id=context.attempt.attempt_id,
                execution_id=context.attempt.execution_id,
                event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
                occurred_at=context.candidate.observed_at,
                actor=_EVENT_ACTOR,
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
                    runner_attempt_summary_refs=(
                        rejected.runner_attempt_summary_refs
                    ),
                    diagnostic_refs=rejected.diagnostic_refs,
                    next_policy_decision=rejected.next_policy_decision.value,
                    budget_after_attempted_compact=(
                        rejected.budget_after_attempted_compact
                    ),
                ),
                payload_ref=None,
                payload_digest=None,
            ),
        ).row

    def _fail_recovering_run(
        self,
        transaction: HostTransaction,
        *,
        context: _ValidatedCandidate,
        failed_event: EventLogRow,
        error_code: str,
        message: str,
    ) -> EngineIngestResult:
        """将 recovering Run 失败收口。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param failed_event: ``CONTEXT_COMPACTION_FAILED`` row。
        :param error_code: Run failure error code。
        :param message: Run failure message。
        :returns: ingest 结果。
        """

        run_failed_event_id = _event_id(
            context.candidate,
            EventClass.CANONICAL_FACT,
            _EVENT_TYPE_RUN_FAILED,
            4,
        )
        result = fail_recovering_run_in_transaction(
            transaction,
            self._event_log_store,
            FailRecoveringRunInput(
                run_id=context.run.run_id,
                source_attempt_id=context.attempt.attempt_id,
                run_failed_event_id=run_failed_event_id,
                occurred_at=context.candidate.observed_at,
                actor=_EVENT_ACTOR,
                source=_EVENT_SOURCE,
                reason=_REASON_CONTEXT_COMPACTION_RECOVERY_FAILED,
                error_code=error_code,
                message=message,
                context_compaction_failed_event_id=failed_event.event_id,
            ),
        )
        if result.status != StateMutationStatus.UPDATED:
            return EngineIngestResult(
                status=EngineIngestStatus.REJECTED,
                events=(),
                terminal_closeout=True,
                promotion_triggered=False,
                reason="recovering_run_failed_precondition_failed",
            )
        rows = _existing_rows(
            self._event_log_store,
            transaction,
            (run_failed_event_id,),
        )
        return EngineIngestResult(
            status=EngineIngestStatus.ACCEPTED,
            events=rows,
            terminal_closeout=True,
            promotion_triggered=False,
            reason=_REASON_CONTEXT_COMPACTION_RECOVERY_FAILED,
        )

    def _complete_reactive_recovery(
        self, accepted: _ReactiveRecoveryAccepted
    ) -> EngineIngestResult:
        """reactive recovery accepted 后启动新 Attempt。

        compact accepted recovery 先追平 memory projection；fallback recovery
        不写 compact fact，也不物化 memory projection，直接创建新 Attempt。

        :param accepted: recovery accepted 摘要。
        :returns: 最终 ingest 结果。
        """

        if accepted.compacted_event_sequence is not None:
            catch_up_conversation_memory_projection(
                self._transaction_runner,
                policy=self._memory_projection_policy,
                batch_size=self._memory_projection_catchup_batch_size,
                max_event_sequence=accepted.compacted_event_sequence,
            )
        started = self._transaction_runner.run_write(
            _StartReactiveRecoveryOperation(
                event_log_store=self._event_log_store,
                accepted=accepted,
            )
        )
        self._wakeup_port.wake_dispatch(started.pending_dispatch)
        return started.result

    def _confirm_waiting_engine_event(
        self,
        transaction: HostTransaction,
        context: _ValidatedCandidate,
        data: ToolAwaitingData | RunSuspendedData,
        payload: Mapping[str, JsonValue],
    ) -> EngineIngestResult:
        """写 Engine 等待事件确认 diagnostic，不改变 Host wait 状态。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param data: Engine waiting confirmation data。
        :param payload: diagnostic payload。
        :returns: ingest 结果。
        """

        check = _validate_waiting_confirmation(
            transaction=transaction,
            event_log_store=self._event_log_store,
            context=context,
            data=data,
        )
        reason = (
            _REASON_WAITING_EVENT_CONFIRMATION
            if check.accepted
            else _REASON_WAITING_EVENT_WITHOUT_HOST_ACCEPTED_REFS
        )
        event_id = _event_id(
            context.candidate,
            EventClass.DIAGNOSTIC,
            _EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC,
            0,
        )
        existing = _existing_rows(self._event_log_store, transaction, (event_id,))
        if len(existing) == 1:
            return EngineIngestResult(
                status=EngineIngestStatus.DUPLICATE,
                events=existing,
                terminal_closeout=False,
                promotion_triggered=False,
                reason=reason,
            )
        diagnostic_payload: dict[str, JsonValue] = dict(payload)
        diagnostic_payload["run_status"] = context.run.status.value
        diagnostic_payload["attempt_status"] = context.attempt.status.value
        diagnostic_payload["waiting_confirmation_accepted"] = check.accepted
        diagnostic_payload["wait_id"] = (
            check.wait_record.wait_id if check.wait_record is not None else None
        )
        diagnostic_payload["waiting_confirmation_mismatch_reason"] = (
            check.mismatch_reason
        )
        row = self._append_diagnostic_event(
            transaction,
            context=context,
            event_type=_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC,
            reason=reason,
            payload=diagnostic_payload,
            sub_index=0,
        )
        return EngineIngestResult(
            status=EngineIngestStatus.ACCEPTED,
            events=(row,),
            terminal_closeout=False,
            promotion_triggered=False,
            reason=reason,
        )

    def _close_worker_lifecycle(
        self,
        envelope: LocalEngineEnvelope,
        *,
        observed_at: datetime,
        event_index: int,
        plan: _TerminalPlan,
    ) -> EngineIngestResult:
        """按 worker lifecycle signal 执行 terminal closeout。

        :param envelope: Host-owned identity envelope。
        :param observed_at: Host 观察时间。
        :param event_index: 合成 worker event index。
        :param plan: terminal closeout 规划。
        :returns: closeout 结果。
        """

        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.engine_ingest.lifecycle_closeout.accepted session_id=%s "
            "run_id=%s attempt_id=%s execution_id=%s event_index=%s "
            "reason=%s",
            envelope.session_id,
            envelope.run_id,
            envelope.attempt_id,
            envelope.execution_id,
            event_index,
            plan.reason,
        )
        event = EngineEvent(
            occurred_at=observed_at,
            session_id=envelope.session_id,
            run_id=envelope.run_id,
            type=EngineEventType.RUN_FAILED,
            data=RunFailedData(
                error_code=plan.reason,
                message=plan.reason,
                provider_request_id=None,
                recoverable=False,
            ),
            metadata=None,
        )
        candidate = EngineEventCandidate(
            envelope=envelope,
            worker_event_index=event_index,
            engine_event=event,
            observed_at=observed_at,
        )

        def _operation(transaction: HostTransaction) -> EngineIngestResult:
            context = self._validate_durable_context(transaction, candidate)
            if context is None:
                return self._append_rejected_diagnostic(
                    transaction,
                    candidate=candidate,
                    reason=_REASON_STALE_EXECUTION_ID,
                )
            duplicate = self._duplicate_terminal_result(transaction, context)
            if duplicate is not None:
                return duplicate
            late = _late_rejection_reason(context)
            if late is not None:
                return self._append_rejected_diagnostic(
                    transaction,
                    candidate=candidate,
                    reason=late,
                )
            return self._close_terminal(transaction, context, plan)

        result = self._transaction_runner.run_write(_operation)
        promoted = self._with_terminal_promotion_retry(
            result,
            session_id=envelope.session_id,
        )
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.engine_ingest.lifecycle_closeout.committed session_id=%s "
            "run_id=%s attempt_id=%s execution_id=%s event_index=%s "
            "ingest_status=%s event_count=%s terminal_closeout=%s "
            "promotion_triggered=%s reason=%s",
            envelope.session_id,
            envelope.run_id,
            envelope.attempt_id,
            envelope.execution_id,
            event_index,
            promoted.status.value,
            len(promoted.events),
            promoted.terminal_closeout,
            promoted.promotion_triggered,
            promoted.reason,
        )
        return promoted

    def _with_terminal_promotion_retry(
        self, result: EngineIngestResult, *, session_id: str
    ) -> EngineIngestResult:
        """对成功或重复 terminal closeout 触发 queue promotion wakeup。

        :param result: transaction 内得到的 ingest 结果。
        :param session_id: terminal Run 所属 Session id。
        :returns: 已更新 promotion 标记的结果。
        """

        if result.terminal_closeout and result.status in (
            EngineIngestStatus.ACCEPTED,
            EngineIngestStatus.DUPLICATE,
        ):
            self._wakeup_port.wake_queue_promotion(session_id)
            return EngineIngestResult(
                status=result.status,
                events=result.events,
                terminal_closeout=True,
                promotion_triggered=True,
                reason=result.reason,
                stop_worker_stream=result.stop_worker_stream,
            )
        return result

    def _append_preview_event(
        self, transaction: HostTransaction, context: _ValidatedCandidate
    ) -> EventLogRow:
        """追加 preview Engine event。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :returns: EventLog row。
        """

        candidate = context.candidate
        event_type = _host_event_type(candidate.engine_event.type)
        return self._event_log_store.append_event(
            transaction,
            _event_request(
                candidate=candidate,
                event_id=_event_id(candidate, EventClass.PREVIEW, event_type, 0),
                event_class=EventClass.PREVIEW,
                event_type=event_type,
                payload=_preview_payload(context),
                reason=None,
            ),
        ).row

    def _append_projection_signal(
        self,
        transaction: HostTransaction,
        context: _ValidatedCandidate,
        data: UsageReportedData,
    ) -> EventLogRow:
        """追加 usage projection signal。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param data: usage_reported data。
        :returns: EventLog row。
        """

        candidate = context.candidate
        diagnostic = self._usage_observation_diagnostic(
            transaction,
            context=context,
            data=data,
        )
        return self._event_log_store.append_event(
            transaction,
            _event_request(
                candidate=candidate,
                event_id=_event_id(
                    candidate,
                    EventClass.PROJECTION_SIGNAL,
                    "USAGE_REPORTED",
                    0,
                ),
                event_class=EventClass.PROJECTION_SIGNAL,
                event_type="USAGE_REPORTED",
                payload={
                    "session_id": context.run.session_id,
                    "run_id": context.run.run_id,
                    "attempt_id": context.attempt.attempt_id,
                    "execution_id": context.attempt.execution_id,
                    "iteration_id": data.iteration_id,
                    "prompt_tokens": data.prompt_tokens,
                    "completion_tokens": data.completion_tokens,
                    "total_tokens": data.total_tokens,
                    "provider_request_id": None,
                    "policy_ref": diagnostic.policy_ref,
                    "estimator_digest": diagnostic.estimator_digest,
                    "estimated_input_tokens": diagnostic.estimated_input_tokens,
                    "usage_observation_status": diagnostic.status,
                    "usage_observation_digest": diagnostic.observation_digest,
                    "prompt_token_delta": diagnostic.prompt_token_delta,
                },
                reason=None,
            ),
        ).row

    def _usage_observation_diagnostic(
        self,
        transaction: HostTransaction,
        *,
        context: _ValidatedCandidate,
        data: UsageReportedData,
    ) -> UsageObservationDiagnostic:
        """构造 usage observation diagnostic，失败时降级为估算不可用。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param data: usage_reported data。
        :returns: usage observation diagnostic。
        """

        estimate = self._estimate_usage_observation_input(transaction, context)
        policy_ref = (
            self._context_budget_policy.policy_ref
            if self._context_budget_policy is not None
            else _NO_CONTEXT_BUDGET_POLICY_REF
        )
        estimator_digest = estimate.estimator_digest if estimate is not None else None
        estimated_input_tokens = (
            estimate.estimated_input_tokens if estimate is not None else None
        )
        status = (
            USAGE_OBSERVATION_STATUS_OBSERVED
            if estimate is not None
            else USAGE_OBSERVATION_STATUS_ESTIMATE_UNAVAILABLE
        )
        try:
            observation = UsageObservation(
                session_id=context.run.session_id,
                run_id=context.run.run_id,
                attempt_id=context.attempt.attempt_id,
                execution_id=context.attempt.execution_id,
                iteration_id=data.iteration_id,
                prompt_tokens=data.prompt_tokens,
                completion_tokens=data.completion_tokens,
                total_tokens=data.total_tokens,
                provider_request_id=None,
                estimator_digest=estimator_digest,
                policy_ref=policy_ref,
                observed_at=context.candidate.observed_at,
            )
            return build_usage_observation_diagnostic(
                observation,
                estimated_input_tokens=estimated_input_tokens,
                status=status,
            )
        except (TypeError, ValueError):
            _LOGGER.debug(
                (
                    "host.engine_ingest.usage_observation_invalid "
                    "session_id=%s run_id=%s attempt_id=%s execution_id=%s"
                ),
                context.run.session_id,
                context.run.run_id,
                context.attempt.attempt_id,
                context.attempt.execution_id,
                exc_info=True,
            )
            return UsageObservationDiagnostic(
                observation_digest=_invalid_usage_observation_digest(
                    context=context,
                    data=data,
                    estimated_input_tokens=estimated_input_tokens,
                    policy_ref=policy_ref,
                    estimator_digest=estimator_digest,
                ),
                estimator_digest=estimator_digest,
                policy_ref=policy_ref,
                estimated_input_tokens=estimated_input_tokens,
                prompt_token_delta=None,
                status=_USAGE_OBSERVATION_STATUS_USAGE_INVALID,
            )

    def _estimate_usage_observation_input(
        self, transaction: HostTransaction, context: _ValidatedCandidate
    ) -> BudgetEstimate | None:
        """为 usage observation 尝试重建当前 Run 输入估算。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :returns: 估算结果；policy、input event 或 payload 不可用时返回
            ``None``。
        """

        policy = self._context_budget_policy
        if policy is None:
            return None
        input_event = self._event_log_store.read_event_by_id(
            transaction, context.run.input_event_id
        )
        if input_event is None:
            return None
        try:
            display_text = _display_text_from_input_event(transaction, input_event)
            return estimate_context_budget(
                policy,
                BudgetEstimateInput(
                    session_id=context.run.session_id,
                    run_id=context.run.run_id,
                    message_fragments=(
                        BudgetTextFragment(
                            fragment_ref=context.run.input_event_id,
                            text=display_text,
                        ),
                    ),
                    current_prompt_ref=context.run.input_event_id,
                ),
            )
        except (HostDurableError, TypeError, ValueError):
            _LOGGER.debug(
                (
                    "host.engine_ingest.usage_observation_estimate_unavailable "
                    "session_id=%s run_id=%s attempt_id=%s execution_id=%s"
                ),
                context.run.session_id,
                context.run.run_id,
                context.attempt.attempt_id,
                context.attempt.execution_id,
                exc_info=True,
            )
            return None

    def _append_provider_protocol_error(
        self,
        transaction: HostTransaction,
        context: _ValidatedCandidate,
        data: ProviderProtocolErrorData,
    ) -> EventLogRow:
        """追加 provider protocol diagnostic。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param data: provider protocol error data。
        :returns: EventLog row。
        """

        raw_descriptor = self._write_raw_payload(
            transaction,
            context=context,
            raw_payload=data.raw_payload,
        )
        candidate = context.candidate
        payload: dict[str, JsonValue] = {
            "attempt_id": context.attempt.attempt_id,
            "execution_id": context.attempt.execution_id,
            "iteration_id": data.iteration_id,
            "error_code": data.error_code,
            "message": data.message,
            "provider_request_id": data.provider_request_id,
            "client_correlation_id": data.client_correlation_id,
            "raw_payload_ref": (
                raw_descriptor.payload_ref if raw_descriptor is not None else None
            ),
            "raw_payload_digest": (
                raw_descriptor.payload_digest if raw_descriptor is not None else None
            ),
            "partial_tool_call_count": len(data.partial_tool_calls),
        }
        return self._event_log_store.append_event(
            transaction,
            _event_request(
                candidate=candidate,
                event_id=_event_id(
                    candidate,
                    EventClass.DIAGNOSTIC,
                    _EVENT_TYPE_PROVIDER_PROTOCOL_ERROR,
                    0,
                ),
                event_class=EventClass.DIAGNOSTIC,
                event_type=_EVENT_TYPE_PROVIDER_PROTOCOL_ERROR,
                payload=payload,
                reason={"reason": data.error_code},
            ),
        ).row

    def _append_diagnostic_event(
        self,
        transaction: HostTransaction,
        *,
        context: _ValidatedCandidate,
        event_type: str,
        reason: str,
        payload: Mapping[str, JsonValue],
        sub_index: int,
    ) -> EventLogRow:
        """追加 diagnostic event。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param event_type: Host event type。
        :param reason: diagnostic reason。
        :param payload: diagnostic payload。
        :param sub_index: event id 派生 sub-index。
        :returns: EventLog row。
        """

        candidate = context.candidate
        return self._event_log_store.append_event(
            transaction,
            _event_request(
                candidate=candidate,
                event_id=_event_id(
                    candidate,
                    EventClass.DIAGNOSTIC,
                    event_type,
                    sub_index,
                ),
                event_class=EventClass.DIAGNOSTIC,
                event_type=event_type,
                payload=payload,
                reason={"reason": reason},
            ),
        ).row

    def _append_rejected_diagnostic(
        self,
        transaction: HostTransaction,
        *,
        candidate: EngineEventCandidate,
        reason: str,
        stop_worker_stream: bool = False,
    ) -> EngineIngestResult:
        """追加 rejected diagnostic。

        :param transaction: 当前 Host transaction。
        :param candidate: 被拒绝的 candidate。
        :param reason: 拒绝原因。
        :param stop_worker_stream: 是否要求 worker stream fail-closed 停止。
        :returns: rejected ingest 结果。
        """

        row = self._event_log_store.append_event(
            transaction,
            _event_request(
                candidate=candidate,
                event_id=_event_id(
                    candidate,
                    EventClass.DIAGNOSTIC,
                    _EVENT_TYPE_ENGINE_EVENT_REJECTED,
                    0,
                ),
                event_class=EventClass.DIAGNOSTIC,
                event_type=_EVENT_TYPE_ENGINE_EVENT_REJECTED,
                payload={
                    "attempt_id": candidate.envelope.attempt_id,
                    "execution_id": candidate.envelope.execution_id,
                    "dispatch_record_id": candidate.envelope.dispatch_record_id,
                    "worker_event_index": candidate.worker_event_index,
                    "engine_event_type": candidate.engine_event.type.value,
                    "reason": reason,
                },
                reason={"reason": reason},
            ),
        ).row
        return EngineIngestResult(
            status=EngineIngestStatus.REJECTED,
            events=(row,),
            terminal_closeout=False,
            promotion_triggered=False,
            reason=reason,
            stop_worker_stream=stop_worker_stream,
        )

    def _write_terminal_summary(
        self,
        transaction: HostTransaction,
        *,
        candidate: EngineEventCandidate,
        event_id: str,
        summary: Mapping[str, JsonValue],
    ) -> PayloadDescriptor:
        """写入 terminal summary payload descriptor。

        :param transaction: 当前 Host transaction。
        :param candidate: 触发 terminal 的 candidate。
        :param event_id: terminal attempt event id。
        :param summary: terminal summary JSON。
        :returns: payload descriptor。
        """

        return self._payload_store.write_sqlite_payload(
            transaction,
            SQLitePayloadWriteRequest(
                payload_ref=f"{_PAYLOAD_REF_PREFIX}-{event_id}",
                payload_id=f"{_PAYLOAD_ID_PREFIX}-{event_id}",
                payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                payload_json={
                    "attempt_id": candidate.envelope.attempt_id,
                    "execution_id": candidate.envelope.execution_id,
                    "worker_event_index": candidate.worker_event_index,
                    "summary": summary,
                },
                payload_bytes=None,
                media_type="application/json",
                metadata={
                    "kind": "engine_terminal_summary",
                    "engine_event_type": candidate.engine_event.type.value,
                },
                expected_digest=None,
            ),
        )

    def _write_raw_payload(
        self,
        transaction: HostTransaction,
        *,
        context: _ValidatedCandidate,
        raw_payload: JsonValue,
    ) -> PayloadDescriptor | None:
        """写入 provider raw payload descriptor。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param raw_payload: provider raw payload；为 ``None`` 时不写入。
        :returns: payload descriptor 或 ``None``。
        """

        if raw_payload is None:
            return None
        event_id = _event_id(
            context.candidate,
            EventClass.DIAGNOSTIC,
            _EVENT_TYPE_PROVIDER_PROTOCOL_ERROR,
            0,
        )
        return self._payload_store.write_sqlite_payload(
            transaction,
            SQLitePayloadWriteRequest(
                payload_ref=f"payload-engine-raw-{event_id}",
                payload_id=f"sqlite-payload-engine-raw-{event_id}",
                payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                payload_json=raw_payload,
                payload_bytes=None,
                media_type="application/json",
                metadata={"kind": "provider_protocol_raw_payload"},
                expected_digest=None,
            ),
        )


def _validate_candidate_shape(candidate: EngineEventCandidate) -> None:
    """校验 candidate envelope、event index 与 observed_at。

    :param candidate: 待校验 candidate。
    :returns: ``None``。
    :raises ValueError: 任一字段非法时抛出。
    """

    if candidate.worker_event_index <= 0:
        raise ValueError("worker_event_index must be positive")
    _validate_observed_at(candidate.observed_at)
    envelope = candidate.envelope
    if (
        envelope.session_id != candidate.engine_event.session_id
        or envelope.run_id != candidate.engine_event.run_id
    ):
        raise ValueError("EngineEvent session_id/run_id must match envelope")
    if candidate.engine_event.occurred_at.tzinfo is None:
        raise ValueError("EngineEvent.occurred_at must be timezone-aware")


def _engine_ingest_log_level(engine_event_type: EngineEventType) -> int:
    """根据 Engine event 类型选择 ingest 诊断日志级别。

    :param engine_event_type: 待记录的 Engine event 类型。
    :returns: stdlib logging level 数值。
    """

    if engine_event_type in _DELTA_ENGINE_EVENT_TYPES:
        return logging.DEBUG
    return VERBOSE_LOG_LEVEL


def _validate_observed_at(observed_at: datetime) -> None:
    """校验 observed_at 为 UTC aware 时间。

    :param observed_at: 待校验时间。
    :returns: ``None``。
    :raises ValueError: 时间不是 UTC aware 时抛出。
    """

    if observed_at.tzinfo is None or observed_at.utcoffset() != UTC.utcoffset(None):
        raise ValueError("observed_at must be timezone.utc aware")


def _late_rejection_reason(context: _ValidatedCandidate) -> str | None:
    """判断 candidate 是否为 terminal 后迟到事件。

    :param context: 已校验上下文。
    :returns: 拒绝原因；可接受时为 ``None``。
    """

    if (
        context.candidate.engine_event.type
        in (EngineEventType.RUN_SUSPENDED, EngineEventType.TOOL_AWAITING)
        and context.run.status is RunStatus.WAITING
        and context.attempt.status is AttemptStatus.SUSPENDED
    ):
        return None
    if (
        context.run.terminal_event_id is not None
        or context.attempt.terminal_event_id is not None
    ):
        return _REASON_TERMINAL_ALREADY_CLOSED
    return None


def _validate_waiting_confirmation(
    *,
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    context: _ValidatedCandidate,
    data: ToolAwaitingData | RunSuspendedData,
) -> _WaitingConfirmationCheck:
    """校验 Engine waiting event 是否匹配 Host accepted wait refs。

    Engine 的 ``TOOL_AWAITING`` / ``RUN_SUSPENDED`` 只允许确认已经由
    ToolRuntime Host accept path 写入的 durable 等待事实；本函数只读取
    durable truth，不创建 wait record、不推进 Run，也不关闭 Attempt。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog primitive。
    :param context: 已校验 candidate 上下文。
    :param data: Engine waiting event data。
    :returns: confirmation 校验结果。
    """

    if (
        context.run.status is not RunStatus.WAITING
        or context.attempt.status is not AttemptStatus.SUSPENDED
    ):
        return _waiting_confirmation_rejected("run_attempt_not_waiting")
    active_waits = tuple(
        wait_record
        for wait_record in read_active_wait_records_for_run(
            transaction, context.run.run_id
        )
        if wait_record.attempt_id == context.attempt.attempt_id
        and wait_record.execution_id == context.attempt.execution_id
    )
    if len(active_waits) != 1:
        return _waiting_confirmation_rejected("active_wait_record_not_unique")
    wait_record = active_waits[0]
    if wait_record.status is not WaitRecordStatus.WAITING:
        return _waiting_confirmation_rejected(
            "active_wait_record_not_waiting", wait_record=wait_record
        )
    refs = _accepted_waiting_refs_or_none(
        transaction=transaction,
        event_log_store=event_log_store,
        context=context,
        wait_record=wait_record,
    )
    if refs is None:
        return _waiting_confirmation_rejected(
            "accepted_wait_refs_mismatch", wait_record=wait_record
        )
    mismatch = _engine_awaiting_record_mismatch(
        data=data,
        wait_record=wait_record,
        tool_awaiting_payload=refs.tool_awaiting_payload,
    )
    if mismatch is not None:
        return _waiting_confirmation_rejected(mismatch, wait_record=wait_record)
    return _WaitingConfirmationCheck(
        accepted=True,
        wait_record=wait_record,
        mismatch_reason=None,
    )


def _waiting_confirmation_rejected(
    mismatch_reason: str, *, wait_record: WaitRecordRow | None = None
) -> _WaitingConfirmationCheck:
    """构造 Engine waiting confirmation 拒绝结果。

    :param mismatch_reason: 内部诊断原因。
    :param wait_record: 已匹配到的 wait record；没有则为 ``None``。
    :returns: 拒绝结果。
    """

    return _WaitingConfirmationCheck(
        accepted=False,
        wait_record=wait_record,
        mismatch_reason=mismatch_reason,
    )


def _accepted_waiting_refs_or_none(
    *,
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    context: _ValidatedCandidate,
    wait_record: WaitRecordRow,
) -> _AcceptedWaitingRefs | None:
    """读取并校验 Host accepted waiting canonical refs。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog primitive。
    :param context: 已校验 candidate 上下文。
    :param wait_record: active wait record。
    :returns: refs 校验通过时的 payload 视图；不匹配时返回 ``None``。
    """

    tool_awaiting = event_log_store.read_latest_run_event_by_type(
        transaction,
        run_id=context.run.run_id,
        event_type=_EVENT_TYPE_TOOL_AWAITING,
    )
    run_waiting = event_log_store.read_latest_run_event_by_type(
        transaction,
        run_id=context.run.run_id,
        event_type=_EVENT_TYPE_RUN_WAITING,
    )
    attempt_suspended = event_log_store.read_latest_run_event_by_type(
        transaction,
        run_id=context.run.run_id,
        event_type=_EVENT_TYPE_ATTEMPT_SUSPENDED,
    )
    if (
        tool_awaiting is None
        or run_waiting is None
        or attempt_suspended is None
    ):
        return None
    if not (
        _waiting_event_row_matches_context(tool_awaiting, context)
        and _waiting_event_row_matches_context(run_waiting, context)
        and _waiting_event_row_matches_context(attempt_suspended, context)
    ):
        return None
    if (
        tool_awaiting.event_id != wait_record.created_event_id
        or tool_awaiting.event_sequence != wait_record.created_event_sequence
        or attempt_suspended.event_id != wait_record.updated_event_id
        or attempt_suspended.event_sequence != wait_record.updated_event_sequence
    ):
        return None
    try:
        tool_payload = _payload_object(tool_awaiting)
        run_payload = _payload_object(run_waiting)
        attempt_payload = _payload_object(attempt_suspended)
    except HostDurableError:
        return None
    if not (
        _tool_awaiting_payload_matches_wait(tool_payload, wait_record)
        and _run_waiting_payload_matches_wait(
            run_payload, wait_record, tool_awaiting
        )
        and _attempt_suspended_payload_matches_wait(
            attempt_payload, wait_record, run_waiting
        )
    ):
        return None
    return _AcceptedWaitingRefs(tool_awaiting_payload=tool_payload)


def _waiting_event_row_matches_context(
    row: EventLogRow, context: _ValidatedCandidate
) -> bool:
    """判断 waiting canonical row 是否与 envelope identity 同源。

    :param row: EventLog row。
    :param context: 已校验 candidate 上下文。
    :returns: 同源时为 ``True``。
    """

    return (
        row.event_class is EventClass.CANONICAL_FACT
        and row.session_id == context.run.session_id
        and row.run_id == context.run.run_id
        and row.attempt_id == context.attempt.attempt_id
        and row.execution_id == context.attempt.execution_id
    )


def _tool_awaiting_payload_matches_wait(
    payload: Mapping[str, JsonValue], wait_record: WaitRecordRow
) -> bool:
    """校验 ``TOOL_AWAITING`` payload 与 wait record 同源。

    :param payload: canonical payload。
    :param wait_record: active wait record。
    :returns: 匹配时为 ``True``。
    """

    try:
        return (
            _required_payload_text(payload, field_name="session_id")
            == wait_record.session_id
            and _required_payload_text(payload, field_name="run_id")
            == wait_record.run_id
            and _required_payload_text(payload, field_name="attempt_id")
            == wait_record.attempt_id
            and _required_payload_text(payload, field_name="execution_id")
            == wait_record.execution_id
            and _required_payload_text(payload, field_name="wait_id")
            == wait_record.wait_id
            and _required_payload_text(payload, field_name="tool_call_id")
            == wait_record.tool_call_id
            and _required_payload_text(payload, field_name="tool_name")
            == wait_record.tool_name
            and _required_payload_text(payload, field_name="accept_idempotency_key")
            == wait_record.accept_idempotency_key
            and _required_payload_text(payload, field_name="adapter_key")
            == wait_record.adapter_key.value
            and _required_payload_text(payload, field_name="resume_policy")
            == wait_record.resume_policy.value
            and _payload_await_spec_matches_wait(payload, wait_record)
            and _payload_snapshot_matches_wait(payload, wait_record)
            and _payload_external_job_matches_wait(payload, wait_record)
        )
    except HostDurableError:
        return False


def _run_waiting_payload_matches_wait(
    payload: Mapping[str, JsonValue],
    wait_record: WaitRecordRow,
    tool_awaiting: EventLogRow,
) -> bool:
    """校验 ``RUN_WAITING`` payload 与 wait record / TOOL_AWAITING ref 同源。

    :param payload: canonical payload。
    :param wait_record: active wait record。
    :param tool_awaiting: ``TOOL_AWAITING`` row。
    :returns: 匹配时为 ``True``。
    """

    try:
        return (
            _required_payload_text(payload, field_name="session_id")
            == wait_record.session_id
            and _required_payload_text(payload, field_name="run_id")
            == wait_record.run_id
            and _required_payload_text(payload, field_name="attempt_id")
            == wait_record.attempt_id
            and _required_payload_text(payload, field_name="wait_id")
            == wait_record.wait_id
            and _payload_event_ref_matches(
                payload, field_name="tool_awaiting_event_ref", row=tool_awaiting
            )
        )
    except HostDurableError:
        return False


def _attempt_suspended_payload_matches_wait(
    payload: Mapping[str, JsonValue],
    wait_record: WaitRecordRow,
    run_waiting: EventLogRow,
) -> bool:
    """校验 ``ATTEMPT_SUSPENDED`` payload 与 wait record / RUN_WAITING ref 同源。

    :param payload: canonical payload。
    :param wait_record: active wait record。
    :param run_waiting: ``RUN_WAITING`` row。
    :returns: 匹配时为 ``True``。
    """

    try:
        return (
            _required_payload_text(payload, field_name="session_id")
            == wait_record.session_id
            and _required_payload_text(payload, field_name="run_id")
            == wait_record.run_id
            and _required_payload_text(payload, field_name="attempt_id")
            == wait_record.attempt_id
            and _required_payload_text(payload, field_name="execution_id")
            == wait_record.execution_id
            and _required_payload_text(payload, field_name="wait_id")
            == wait_record.wait_id
            and _required_payload_text(payload, field_name="tool_call_id")
            == wait_record.tool_call_id
            and _payload_event_ref_matches(
                payload, field_name="run_waiting_event_ref", row=run_waiting
            )
        )
    except HostDurableError:
        return False


def _payload_await_spec_matches_wait(
    payload: Mapping[str, JsonValue], wait_record: WaitRecordRow
) -> bool:
    """校验 payload 中的 await spec 与 wait record 一致。

    :param payload: ``TOOL_AWAITING`` payload。
    :param wait_record: active wait record。
    :returns: 匹配时为 ``True``。
    """

    value = payload.get("await_spec")
    if not isinstance(value, Mapping):
        return False
    deadline = value.get("deadline")
    try:
        expected_deadline = (
            parse_utc_timestamp(wait_record.deadline_at).isoformat()
            if wait_record.deadline_at is not None
            else None
        )
    except ValueError:
        return False
    return (
        value.get("await_kind") == wait_record.await_kind
        and value.get("resume_token") == wait_record.resume_token
        and deadline == expected_deadline
    )


def _payload_snapshot_matches_wait(
    payload: Mapping[str, JsonValue], wait_record: WaitRecordRow
) -> bool:
    """校验 payload 中的 snapshot ref 与 wait record 一致。

    :param payload: ``TOOL_AWAITING`` payload。
    :param wait_record: active wait record。
    :returns: 匹配时为 ``True``。
    """

    value = payload.get("snapshot_ref")
    if wait_record.snapshot_ref is None:
        return value is None
    if not isinstance(value, Mapping):
        return False
    return (
        value.get("snapshot_id") == wait_record.snapshot_ref.snapshot_id
        and value.get("captured_at") == wait_record.snapshot_ref.captured_at.isoformat()
        and value.get("snapshot_digest") == wait_record.snapshot_ref.snapshot_digest
    )


def _payload_external_job_matches_wait(
    payload: Mapping[str, JsonValue], wait_record: WaitRecordRow
) -> bool:
    """校验 payload 中的 external job ref 与 wait record 一致。

    :param payload: ``TOOL_AWAITING`` payload。
    :param wait_record: active wait record。
    :returns: 匹配时为 ``True``。
    """

    value = payload.get("external_job_ref")
    if wait_record.external_job_ref is None:
        return value is None
    if not isinstance(value, Mapping):
        return False
    return (
        value.get("adapter_key") == wait_record.external_job_ref.adapter_key.value
        and value.get("external_job_id")
        == wait_record.external_job_ref.external_job_id
    )


def _payload_event_ref_matches(
    payload: Mapping[str, JsonValue], *, field_name: str, row: EventLogRow
) -> bool:
    """校验 payload 中的 EventLog ref 是否指向指定 row。

    :param payload: canonical payload。
    :param field_name: ref 字段名。
    :param row: 目标 EventLog row。
    :returns: 匹配时为 ``True``。
    """

    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        return False
    return (
        value.get("event_id") == row.event_id
        and value.get("event_sequence") == row.event_sequence
    )


def _engine_awaiting_record_mismatch(
    *,
    data: ToolAwaitingData | RunSuspendedData,
    wait_record: WaitRecordRow,
    tool_awaiting_payload: Mapping[str, JsonValue],
) -> str | None:
    """比较 Engine awaiting record 与 Host accepted wait record。

    :param data: Engine waiting event data。
    :param wait_record: active wait record。
    :param tool_awaiting_payload: ``TOOL_AWAITING`` canonical payload。
    :returns: 不匹配原因；匹配时为 ``None``。
    """

    if isinstance(data, ToolAwaitingData):
        record = data.record
        iteration_id = data.iteration_id
    else:
        if data.reason != RUN_SUSPENDED_REASON_TOOL_AWAITING:
            return "run_suspended_reason_mismatch"
        if len(data.awaiting_records) != 1:
            return "run_suspended_awaiting_record_count_mismatch"
        record = data.awaiting_records[0]
        iteration_id = record.batch_snapshot.iteration_id
    if record.batch_snapshot.iteration_id != iteration_id:
        return "awaiting_iteration_mismatch"
    if tool_awaiting_payload.get("iteration_id") != iteration_id:
        return "awaiting_iteration_mismatch"
    if (
        record.call.tool_call_id != wait_record.tool_call_id
        or record.call.name != wait_record.tool_name
    ):
        return "awaiting_tool_identity_mismatch"
    if (
        record.await_spec.await_kind.value != wait_record.await_kind
        or record.await_spec.resume_token != wait_record.resume_token
    ):
        return "awaiting_spec_mismatch"
    try:
        deadline_at = (
            format_utc_timestamp(record.await_spec.deadline)
            if record.await_spec.deadline is not None
            else None
        )
    except ValueError:
        return "awaiting_deadline_mismatch"
    if deadline_at != wait_record.deadline_at:
        return "awaiting_deadline_mismatch"
    if not _engine_snapshot_matches_wait(record.snapshot, wait_record):
        return "awaiting_snapshot_mismatch"
    return None


def _engine_snapshot_matches_wait(
    snapshot: ToolAwaitSnapshot | None, wait_record: WaitRecordRow
) -> bool:
    """校验 Engine awaiting snapshot 与 wait record snapshot ref 一致。

    :param snapshot: Engine ``ToolAwaitSnapshot`` 或 ``None``。
    :param wait_record: active wait record。
    :returns: 匹配时为 ``True``。
    """

    if snapshot is None:
        return wait_record.snapshot_ref is None
    if wait_record.snapshot_ref is None:
        return False
    return (
        snapshot.snapshot_id == wait_record.snapshot_ref.snapshot_id
        and snapshot.captured_at == wait_record.snapshot_ref.captured_at
    )


def _event_id(
    candidate: EngineEventCandidate,
    event_class: EventClass,
    event_type: str,
    sub_index: int,
) -> str:
    """按 Phase 5 公式派生 Host event id。

    :param candidate: EngineEvent candidate。
    :param event_class: Host EventLog class。
    :param event_type: Host event type。
    :param sub_index: 单个 EngineEvent 映射多事件时的下标。
    :returns: 稳定 Host event id。
    """

    digest = sha256_digest_json(
        {
            "execution_id": candidate.envelope.execution_id,
            "worker_event_index": candidate.worker_event_index,
            "event_class": event_class.value,
            "event_type": event_type,
            "sub_index": sub_index,
        }
    ).removeprefix("sha256:")
    return f"{_EVENT_ID_PREFIX}{digest}"


def _reactive_compaction_request(
    pending: _ReactiveCompactPending,
) -> CompactionRequest:
    """构造 reactive Host compaction request。

    :param pending: reactive compact pending 摘要。
    :returns: CompactionRequest。
    """

    context = pending.context
    segment_selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.REACTIVE,
        input_cursor=context.run.input_event_sequence,
        memory_snapshot_cursor=None,
        policy_digest=pending.frozen_material_list_digest,
        material_blocks=pending.frozen_material_blocks,
    )
    material_pack = build_compact_material_pack(
        selected_segment=segment_selection,
        material_blocks=pending.frozen_material_blocks,
        memory_snapshot=None,
        inline_delta_repair_view=None,
        current_input_ref=context.run.input_event_id,
        current_input_text=pending.display_text,
    )
    return CompactionRequest(
        trigger_source=ContextCompactionTriggerSource.REACTIVE,
        session_id=context.run.session_id,
        run_id=context.run.run_id,
        attempt_id=context.attempt.attempt_id,
        execution_id=context.attempt.execution_id,
        memory_snapshot_cursor=None,
        material_pack=material_pack,
        segment_selection=segment_selection,
        evidence_backed_fact_refs=(),
        recent_raw_turn_refs=(context.run.input_event_id,),
        older_raw_turn_refs=selected_material_source_refs(
            material_blocks=pending.frozen_material_blocks,
            selected_block_ids=segment_selection.selected_block_ids,
        ),
        existing_episode_summary_refs=(),
        budget_before_compact=pending.estimate,
    )


def _reactive_compaction_pass_queue(
    pending: _ReactiveCompactPending, root_request: CompactionRequest
) -> tuple[CompactionRequest, ...]:
    """按冻结 material list 构造 reactive multi-pass request 队列。

    :param pending: reactive compact pending 摘要。
    :param root_request: 覆盖完整 selected segment 的 root request。
    :returns: pass request 队列；单 pass 时为空以复用 operation 默认语义。
    """

    selected = root_request.segment_selection.selected_block_ids
    if len(selected) <= 1:
        return ()
    pass_requests: list[CompactionRequest] = []
    for block_id in selected:
        selection = _single_block_segment_selection(
            root_request=root_request,
            block_id=block_id,
            material_blocks=pending.frozen_material_blocks,
        )
        material_pack = build_compact_material_pack(
            selected_segment=selection,
            material_blocks=pending.frozen_material_blocks,
            memory_snapshot=None,
            inline_delta_repair_view=None,
            current_input_ref=pending.context.run.input_event_id,
            current_input_text=pending.display_text,
        )
        pass_requests.append(
            CompactionRequest(
                trigger_source=root_request.trigger_source,
                session_id=root_request.session_id,
                run_id=root_request.run_id,
                attempt_id=root_request.attempt_id,
                execution_id=root_request.execution_id,
                memory_snapshot_cursor=root_request.memory_snapshot_cursor,
                material_pack=material_pack,
                segment_selection=selection,
                evidence_backed_fact_refs=(),
                recent_raw_turn_refs=root_request.recent_raw_turn_refs,
                older_raw_turn_refs=selected_material_source_refs(
                    material_blocks=pending.frozen_material_blocks,
                    selected_block_ids=selection.selected_block_ids,
                ),
                existing_episode_summary_refs=(),
                budget_before_compact=root_request.budget_before_compact,
            )
        )
    return tuple(pass_requests)


def _reactive_fallback_decision(
    *, pending: _ReactiveCompactPending, failure_reason: str
) -> _ReactiveFallbackDecision:
    """为 reactive compact final failure 构造 recent-window fallback 决策。

    本函数只使用 overflow 时冻结的 ordinary material blocks 与同一个
    context budget policy；不读取 compact artifact，不写 memory，也不伪造
    ``CONTEXT_COMPACTED``。selection 或 budget 估算异常时 fail closed。

    :param pending: reactive compact pending 摘要。
    :param failure_reason: compact final failure reason。
    :returns: fallback 决策与 failed payload 诊断字段。
    """

    try:
        selection = build_recent_window_fallback_selection(
            policy=pending.policy,
            session_id=pending.context.run.session_id,
            run_id=pending.context.run.run_id,
            material_blocks=pending.frozen_material_blocks,
            current_input_ref=pending.context.run.input_event_id,
            input_cursor=pending.expected_input_event_sequence,
            selected_recent_window_turn_floor=pending.selected_recent_window_turn_floor,
            trigger_source=ContextCompactionTriggerSource.REACTIVE,
        )
        budget = estimate_recent_window_fallback_budget(
            policy=pending.policy,
            session_id=pending.context.run.session_id,
            run_id=pending.context.run.run_id,
            selection_blocks=selection.selected_blocks,
            current_input_ref=pending.context.run.input_event_id,
        )
    except Exception as error:
        window = build_selection_failure_window_payload(
            current_input_ref=pending.context.run.input_event_id,
            trigger_source=ContextCompactionTriggerSource.REACTIVE,
            policy_ref=pending.policy.policy_ref,
            input_cursor=pending.expected_input_event_sequence,
            failure_reason=_fallback_selection_failure_reason(
                error,
                compact_failure_reason=failure_reason,
            ),
        )
        return _ReactiveFallbackDecision(
            action=FALLBACK_ACTION_FAIL_CLOSED,
            policy_decision=FALLBACK_POLICY_DECISION_SELECTION_FAILED,
            input_window=window,
            input_digest=fallback_window_digest(window),
            budget_result=build_selection_failure_budget_payload(
                policy_ref=pending.policy.policy_ref
            ),
        )
    action = (
        FALLBACK_ACTION_DISPATCH
        if budget.hard_budget_passed
        else FALLBACK_ACTION_FAIL_CLOSED
    )
    return _ReactiveFallbackDecision(
        action=action,
        policy_decision=FALLBACK_POLICY_DECISION_RECENT_WINDOW,
        input_window=selection.to_window_payload(),
        input_digest=selection.digest,
        budget_result=budget.to_payload(),
    )


def _fallback_selection_failure_reason(
    error: Exception, *, compact_failure_reason: str
) -> str:
    """构造 fallback selection / estimate failure 诊断原因。

    :param error: 捕获到的 fallback 异常。
    :param compact_failure_reason: 触发 fallback 的 compact failure reason。
    :returns: 结构化 reason 文本。
    """

    return (
        "reactive_fallback_selection_failed:"
        f"{compact_failure_reason}:{type(error).__name__}"
    )


def _single_block_segment_selection(
    *,
    root_request: CompactionRequest,
    block_id: str,
    material_blocks: tuple[RunInputMaterialBlock, ...],
) -> CompactSegmentSelection:
    """构造只包含单个 selected block 的 reactive selection。

    :param root_request: root compaction request。
    :param block_id: 本 pass 选中的 block id。
    :param material_blocks: 冻结 ordinary material blocks。
    :returns: 单 block segment selection。
    :raises ValueError: block id 不在冻结列表时抛出。
    """

    known = {block.block_id for block in material_blocks}
    if block_id not in known:
        raise ValueError("reactive pass block_id is not in frozen material list")
    excluded = {
        block.block_id: "not_in_pass"
        for block in material_blocks
        if block.block_id != block_id
    }
    digest = sha256_digest_json(
        {
            "root_selection_digest": root_request.segment_selection.selection_digest,
            "selected_block_ids": [block_id],
            "excluded_reason_codes": excluded,
        }
    )
    return CompactSegmentSelection(
        selected_block_ids=(block_id,),
        excluded_protected_ids=(),
        trigger_source=CompactSegmentTrigger.REACTIVE,
        input_cursor=root_request.segment_selection.input_cursor,
        memory_snapshot_cursor=root_request.segment_selection.memory_snapshot_cursor,
        policy_digest=root_request.segment_selection.policy_digest,
        deterministic_reason_codes=("reactive_single_pass_block",),
        selection_digest=digest,
        excluded_reason_codes=excluded,
    )


def _frozen_reactive_material_blocks(
    *,
    transaction: HostTransaction,
    context: _ValidatedCandidate,
    display_text: str,
) -> tuple[RunInputMaterialBlock, ...]:
    """冻结 reactive overflow 对应 ordinary input material list。

    :param transaction: 当前 Host transaction。
    :param context: 已校验 Engine event context。
    :param display_text: 当前输入展示文本。
    :returns: 冻结 material blocks。
    """

    input_event = _require_event_row(
        transaction,
        event_log_store=EventLogStore(),
        event_id=context.run.input_event_id,
        expected_type="USER_INPUT_ACCEPTED",
    )
    accepted_event = _require_event_row(
        transaction,
        event_log_store=EventLogStore(),
        event_id=context.run.accepted_event_id,
        expected_type="RUN_ACCEPTED",
    )
    if context.run.started_event_id is None:
        return _current_only_material_blocks(
            run=context.run,
            input_event=input_event,
            display_text=display_text,
        )
    started_event = _require_event_row(
        transaction,
        event_log_store=EventLogStore(),
        event_id=context.run.started_event_id,
        expected_type="RUN_STARTED",
    )
    current_facts = CurrentRunFacts(
        run=context.run,
        attempt=context.attempt,
        dispatch_record=context.dispatch_record,
        user_input_event=input_event,
        run_accepted_event=accepted_event,
        run_started_event=started_event,
        user_prompt=display_text,
        system_prompt=None,
        operation_kind="run",
    )
    return build_run_input_material_blocks(
        current_facts=current_facts,
        memory=MemorySnapshotView(
            messages=(),
            memory_snapshot_cursor=None,
            policy_digest=None,
            diagnostics=(),
        ),
        compact=CompactArtifactView(
            messages=(),
            compact_artifact_ref=None,
            compact_artifact_digest=None,
        ),
        continuity=SessionContinuityView(messages=()),
    )


def _current_only_material_blocks(
    *,
    run: RunRow,
    input_event: EventLogRow,
    display_text: str,
) -> tuple[RunInputMaterialBlock, ...]:
    """构造 current-input-only material list。

    :param run: 当前 Run row。
    :param input_event: 当前输入 EventLog row。
    :param display_text: 当前输入展示文本。
    :returns: material blocks。
    """

    return (
        run_input_material_block(
            block_id=f"current:{run.input_event_id}",
            section=CompactMaterialSection.CURRENT_INPUT_ANCHOR,
            kind=CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
            text=display_text,
            canonical_source_refs=(run.input_event_id,),
            event_sequence=input_event.event_sequence,
        ),
    )


def _require_event_row(
    transaction: HostTransaction,
    *,
    event_log_store: EventLogStore,
    event_id: str,
    expected_type: str,
) -> EventLogRow:
    """读取并校验 EventLog row。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog store。
    :param event_id: 事件 id。
    :param expected_type: 期望 event type。
    :returns: EventLog row。
    :raises HostDurableError: 事件缺失或类型不匹配时抛出。
    """

    row = event_log_store.read_event_by_id(transaction, event_id)
    if row is None or row.event_type != expected_type:
        raise HostDurableError(f"required event is missing: {expected_type}")
    return row


def _material_list_digest(
    material_blocks: tuple[RunInputMaterialBlock, ...]
) -> str:
    """计算冻结 material list digest。

    :param material_blocks: 冻结 material blocks。
    :returns: canonical sha256 digest。
    """

    return sha256_digest_json(
        {
            "blocks": [
                {
                    "block_id": block.block_id,
                    "section": block.section.value,
                    "kind": block.kind.value,
                    "content_digest": block.content_digest,
                    "canonical_source_refs": list(block.canonical_source_refs),
                }
                for block in material_blocks
            ]
        }
    )


def _material_source_refs(
    material_blocks: tuple[RunInputMaterialBlock, ...]
) -> tuple[str, ...]:
    """返回 material list 覆盖的 canonical source refs。

    :param material_blocks: material blocks。
    :returns: 去重后的 source refs。
    """

    refs: list[str] = []
    for block in material_blocks:
        refs.extend(block.canonical_source_refs)
    return tuple(dict.fromkeys(refs))


def _event_request(
    *,
    candidate: EngineEventCandidate,
    event_id: str,
    event_class: EventClass,
    event_type: str,
    payload: Mapping[str, JsonValue],
    reason: JsonValue,
) -> EventLogAppendRequest:
    """构造通用 Engine ingest EventLog append request。

    :param candidate: EngineEvent candidate。
    :param event_id: Host event id。
    :param event_class: Host EventLog class。
    :param event_type: Host event type。
    :param payload: inline payload JSON。
    :param reason: reason JSON。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=event_class,
        session_id=candidate.envelope.session_id,
        run_id=candidate.envelope.run_id,
        attempt_id=candidate.envelope.attempt_id,
        execution_id=candidate.envelope.execution_id,
        event_type=event_type,
        occurred_at=candidate.observed_at,
        actor=_EVENT_ACTOR,
        source=_EVENT_SOURCE,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=reason,
        payload_json=payload,
        payload_ref=None,
        payload_digest=None,
    )


def _existing_rows(
    event_log_store: EventLogStore,
    transaction: HostTransaction,
    event_ids: tuple[str, ...],
) -> tuple[EventLogRow, ...]:
    """读取一组已存在 EventLog rows。

    :param event_log_store: EventLog primitive。
    :param transaction: 当前 Host transaction。
    :param event_ids: 待读取 event ids。
    :returns: 已存在 rows，按输入 id 顺序。
    """

    rows: list[EventLogRow] = []
    for event_id in event_ids:
        row = event_log_store.read_event_by_id(transaction, event_id)
        if row is not None:
            rows.append(row)
    return tuple(rows)


def _latest_rows_for_types(
    event_log_store: EventLogStore,
    transaction: HostTransaction,
    run_id: str,
    event_types: tuple[str, ...],
) -> tuple[EventLogRow, ...]:
    """按事件类型读取指定 Run 最近 rows。

    :param event_log_store: EventLog primitive。
    :param transaction: 当前 Host transaction。
    :param run_id: Run id。
    :param event_types: event type 元组。
    :returns: 找到的 rows，按输入类型顺序。
    """

    rows: list[EventLogRow] = []
    for event_type in event_types:
        row = event_log_store.read_latest_run_event_by_type(
            transaction,
            run_id=run_id,
            event_type=event_type,
        )
        if row is not None:
            rows.append(row)
    return tuple(rows)


def _display_text_from_input_event(
    transaction: HostTransaction, event: EventLogRow
) -> str:
    """从 ``USER_INPUT_ACCEPTED`` payload 读取展示文本。

    :param transaction: 当前 Host transaction。
    :param event: input EventLog row。
    :returns: 展示文本。
    :raises HostDurableError: payload 缺少展示文本或无法解析时抛出。
    """

    payload = event_payload_object(
        transaction, event, payload_label="USER_INPUT_ACCEPTED"
    )
    return _required_payload_text(payload, field_name="display_text")


def _invalid_usage_observation_digest(
    *,
    context: _ValidatedCandidate,
    data: UsageReportedData,
    estimated_input_tokens: int | None,
    policy_ref: str,
    estimator_digest: str | None,
) -> str:
    """计算 invalid usage observation diagnostic digest。

    :param context: 已校验 candidate 上下文。
    :param data: usage_reported data。
    :param estimated_input_tokens: 对应估算输入 token 数。
    :param policy_ref: 对应 policy ref。
    :param estimator_digest: 对应估算 digest。
    :returns: sha256 digest。
    """

    payload: JsonValue = {
        "observation": {
            "session_id": context.run.session_id,
            "run_id": context.run.run_id,
            "attempt_id": context.attempt.attempt_id,
            "execution_id": context.attempt.execution_id,
            "iteration_id": data.iteration_id,
            "prompt_tokens": data.prompt_tokens,
            "completion_tokens": data.completion_tokens,
            "total_tokens": data.total_tokens,
            "provider_request_id": None,
            "observed_at": context.candidate.observed_at.isoformat(),
        },
        "diagnostic": {
            "estimator_digest": estimator_digest,
            "policy_ref": policy_ref,
            "estimated_input_tokens": estimated_input_tokens,
            "prompt_token_delta": None,
            "status": _USAGE_OBSERVATION_STATUS_USAGE_INVALID,
        },
    }
    return sha256_digest_json(payload)


def _new_id(prefix: str) -> str:
    """生成带前缀的本地唯一 id。

    :param prefix: id 前缀。
    :returns: 文本 id。
    :raises ValueError: 前缀为空时抛出。
    """

    if prefix.strip() == "":
        raise ValueError("prefix must be non-empty")
    return f"{prefix}-{uuid4().hex}"


def _duplicate_terminal_event_ids(
    candidate: EngineEventCandidate,
) -> tuple[str, ...]:
    """计算 terminal candidate 可能已写入的 event ids。

    :param candidate: EngineEvent candidate。
    :returns: terminal event id 元组；非 terminal closeout 事件返回空元组。
    """

    event = candidate.engine_event
    if event.type == EngineEventType.FINAL_ANSWER:
        return (
            _event_id(
                candidate,
                EventClass.CANONICAL_FACT,
                _EVENT_TYPE_ATTEMPT_SUCCEEDED,
                0,
            ),
            _event_id(
                candidate,
                EventClass.CANONICAL_FACT,
                _EVENT_TYPE_RUN_SUCCEEDED,
                1,
            ),
        )
    if event.type == EngineEventType.RUN_FAILED and isinstance(
        event.data, RunFailedData
    ):
        if event.data.error_code == _REASON_WORKER_LOST_BEFORE_TERMINAL:
            return (
                _event_id(
                    candidate,
                    EventClass.CANONICAL_FACT,
                    _EVENT_TYPE_ATTEMPT_LOST,
                    0,
                ),
                _event_id(
                    candidate,
                    EventClass.CANONICAL_FACT,
                    _EVENT_TYPE_RUN_LOST,
                    1,
                ),
            )
        if event.data.recoverable:
            return (
                _event_id(
                    candidate,
                    EventClass.DIAGNOSTIC,
                    _EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC,
                    0,
                ),
                _event_id(
                    candidate,
                    EventClass.CANONICAL_FACT,
                    _EVENT_TYPE_ATTEMPT_FAILED,
                    1,
                ),
                _event_id(
                    candidate,
                    EventClass.CANONICAL_FACT,
                    _EVENT_TYPE_RUN_FAILED,
                    2,
                ),
            )
        return (
            _event_id(
                candidate,
                EventClass.CANONICAL_FACT,
                _EVENT_TYPE_ATTEMPT_FAILED,
                0,
            ),
            _event_id(
                candidate,
                EventClass.CANONICAL_FACT,
                _EVENT_TYPE_RUN_FAILED,
                1,
            ),
        )
    if event.type == EngineEventType.RUN_CANCELLED:
        return (
            _event_id(
                candidate,
                EventClass.CANONICAL_FACT,
                _EVENT_TYPE_ATTEMPT_CANCELLED,
                0,
            ),
            _event_id(
                candidate,
                EventClass.CANONICAL_FACT,
                _EVENT_TYPE_RUN_CANCELLED,
                1,
            ),
        )
    if event.type == EngineEventType.CONTEXT_COMPACTION_REQUESTED:
        return (
            _event_id(
                candidate,
                EventClass.CANONICAL_FACT,
                CONTEXT_COMPACTION_REQUESTED,
                0,
            ),
            _event_id(
                candidate,
                EventClass.CANONICAL_FACT,
                _EVENT_TYPE_ATTEMPT_FAILED,
                1,
            ),
            _event_id(
                candidate,
                EventClass.CANONICAL_FACT,
                _EVENT_TYPE_RUN_RECOVERING,
                2,
            ),
        )
    return ()


def _engine_event_ref(candidate: EngineEventCandidate) -> str:
    """为 terminal payload 生成 EngineEvent 引用。

    :param candidate: EngineEvent candidate。
    :returns: EngineEvent 引用文本。
    """

    event_type = candidate.engine_event.type.value
    if (
        candidate.engine_event.type == EngineEventType.RUN_FAILED
        and isinstance(candidate.engine_event.data, RunFailedData)
        and candidate.engine_event.data.error_code == _REASON_WORKER_LOST_BEFORE_TERMINAL
    ):
        event_type = _REASON_WORKER_LOST_BEFORE_TERMINAL
    return (
        f"engine:{candidate.envelope.execution_id}:"
        f"{candidate.worker_event_index}:{event_type}"
    )


def _reactive_precondition_compaction_operation_id(
    *, context: _ValidatedCandidate, failure_reason: str
) -> str:
    """构造未写 request fact 的 reactive precondition failure operation id。

    :param context: 已校验 candidate 上下文。
    :param failure_reason: precondition failure reason。
    :returns: 可写入 failed payload 的稳定 operation id。
    """

    return (
        f"{_REACTIVE_PRECONDITION_OPERATION_PREFIX}:"
        f"{failure_reason}:{_engine_event_ref(context.candidate)}"
    )


def _host_event_type(event_type: EngineEventType) -> str:
    """把 EngineEventType 映射为 Host event type 文本。

    :param event_type: Engine event type。
    :returns: 大写 Host event type。
    """

    return event_type.value.upper()


def _final_answer_plan(data: FinalAnswerData) -> _TerminalPlan:
    """构造 final_answer terminal plan。

    :param data: final_answer data。
    :returns: terminal plan。
    """

    if data.content.strip() == "":
        return _failed_plan(
            reason=_REASON_EMPTY_FINAL_ANSWER,
            error_code=_REASON_EMPTY_FINAL_ANSWER,
            message=(
                "Engine final_answer contained no displayable content; "
                f"finish_reason={data.finish_reason.value}"
            ),
            provider_request_id=None,
            client_correlation_id=None,
            recoverable=False,
            unsupported_later_owner=None,
        )
    return _TerminalPlan(
        attempt_event_type=_EVENT_TYPE_ATTEMPT_SUCCEEDED,
        run_event_type=_EVENT_TYPE_RUN_SUCCEEDED,
        attempt_status=AttemptStatus.SUCCEEDED,
        run_status=RunStatus.SUCCEEDED,
        reason=_REASON_FINAL_ANSWER,
        terminal_summary={
            "content": data.content,
            "finish_reason": data.finish_reason.value,
            "filtered": data.filtered,
            "degraded": data.degraded,
        },
        finish_reason=data.finish_reason.value,
        filtered=data.filtered,
        degraded=data.degraded,
        error_code=None,
        message=None,
        provider_request_id=None,
        client_correlation_id=None,
        recoverable=None,
        unsupported_later_owner=None,
        worker_lifecycle_signal=None,
        stream_error_code=None,
        last_observed_worker_event_index=None,
        last_accepted_event_id=None,
    )


def _run_failed_plan(data: RunFailedData) -> _TerminalPlan:
    """构造 run_failed terminal plan。

    :param data: run_failed data。
    :returns: terminal plan。
    """

    unsupported_owner = _OWNER_PHASE10 if data.recoverable else None
    reason = (
        _REASON_UNSUPPORTED_RECOVERY_POLICY if data.recoverable else data.error_code
    )
    return _TerminalPlan(
        attempt_event_type=_EVENT_TYPE_ATTEMPT_FAILED,
        run_event_type=_EVENT_TYPE_RUN_FAILED,
        attempt_status=AttemptStatus.FAILED,
        run_status=RunStatus.FAILED,
        reason=reason,
        terminal_summary={
            "error_code": data.error_code,
            "message": data.message,
            "provider_request_id": data.provider_request_id,
            "client_correlation_id": data.client_correlation_id,
            "recoverable": data.recoverable,
        },
        finish_reason=None,
        filtered=None,
        degraded=None,
        error_code=data.error_code,
        message=data.message,
        provider_request_id=data.provider_request_id,
        client_correlation_id=data.client_correlation_id,
        recoverable=data.recoverable,
        unsupported_later_owner=unsupported_owner,
        worker_lifecycle_signal=None,
        stream_error_code=None,
        last_observed_worker_event_index=None,
        last_accepted_event_id=None,
    )


def _unsupported_recovery_plan(provider_request_id: str | None) -> _TerminalPlan:
    """构造 unsupported recovery terminal plan。

    :param provider_request_id: provider request id；无时为 ``None``。
    :returns: terminal plan。
    """

    return _failed_plan(
        reason=_REASON_UNSUPPORTED_RECOVERY_POLICY,
        error_code=_REASON_UNSUPPORTED_RECOVERY_POLICY,
        message="context compaction and recovery are unsupported in Phase 5",
        provider_request_id=provider_request_id,
        client_correlation_id=None,
        recoverable=True,
        unsupported_later_owner=_OWNER_PHASE10,
    )


def _unsupported_waiting_plan() -> _TerminalPlan:
    """构造 unsupported waiting terminal plan。

    :returns: terminal plan。
    """

    return _failed_plan(
        reason=_REASON_UNSUPPORTED_WAITING_PATH,
        error_code=_REASON_UNSUPPORTED_WAITING_PATH,
        message="waiting path is unsupported in Phase 5",
        provider_request_id=None,
        client_correlation_id=None,
        recoverable=False,
        unsupported_later_owner=_OWNER_PHASE7,
    )


def _failed_lifecycle_plan(
    *, reason: str, last_observed_worker_event_index: int
) -> _TerminalPlan:
    """构造 worker lifecycle failed closeout plan。

    :param reason: closeout reason。
    :param last_observed_worker_event_index: 最后观察到的 worker event index。
    :returns: terminal plan。
    """

    plan = _failed_plan(
        reason=reason,
        error_code=reason,
        message=reason,
        provider_request_id=None,
        client_correlation_id=None,
        recoverable=False,
        unsupported_later_owner=None,
    )
    return _replace_lifecycle_index(plan, last_observed_worker_event_index)


def _lost_lifecycle_plan(
    *,
    worker_lifecycle_signal: str,
    stream_error_code: str | None,
    last_observed_worker_event_index: int,
    last_accepted_event_id: str | None,
) -> _TerminalPlan:
    """构造 worker lost closeout plan。

    :param worker_lifecycle_signal: worker lifecycle signal。
    :param stream_error_code: stream error code；无时为 ``None``。
    :param last_observed_worker_event_index: 最后观察到的 worker event index。
    :param last_accepted_event_id: 最后已接受 EventLog id；无时为 ``None``。
    :returns: terminal plan。
    """

    return _TerminalPlan(
        attempt_event_type=_EVENT_TYPE_ATTEMPT_LOST,
        run_event_type=_EVENT_TYPE_RUN_LOST,
        attempt_status=AttemptStatus.LOST,
        run_status=RunStatus.LOST,
        reason=_REASON_WORKER_LOST_BEFORE_TERMINAL,
        terminal_summary={
            "reason": _REASON_WORKER_LOST_BEFORE_TERMINAL,
            "worker_lifecycle_signal": worker_lifecycle_signal,
            "stream_error_code": stream_error_code,
        },
        finish_reason=None,
        filtered=None,
        degraded=None,
        error_code=None,
        message=None,
        provider_request_id=None,
        client_correlation_id=None,
        recoverable=None,
        unsupported_later_owner=None,
        worker_lifecycle_signal=worker_lifecycle_signal,
        stream_error_code=stream_error_code,
        last_observed_worker_event_index=last_observed_worker_event_index,
        last_accepted_event_id=last_accepted_event_id,
    )


def _failed_plan(
    *,
    reason: str,
    error_code: str,
    message: str,
    provider_request_id: str | None,
    client_correlation_id: str | None,
    recoverable: bool,
    unsupported_later_owner: str | None,
) -> _TerminalPlan:
    """构造 failed terminal plan。

    :param reason: terminal reason。
    :param error_code: error code。
    :param message: error message。
    :param provider_request_id: provider request id。
    :param client_correlation_id: 本地客户端关联 id。
    :param recoverable: 是否可恢复。
    :param unsupported_later_owner: unsupported later owner。
    :returns: terminal plan。
    """

    return _TerminalPlan(
        attempt_event_type=_EVENT_TYPE_ATTEMPT_FAILED,
        run_event_type=_EVENT_TYPE_RUN_FAILED,
        attempt_status=AttemptStatus.FAILED,
        run_status=RunStatus.FAILED,
        reason=reason,
        terminal_summary={
            "error_code": error_code,
            "message": message,
            "provider_request_id": provider_request_id,
            "client_correlation_id": client_correlation_id,
            "recoverable": recoverable,
        },
        finish_reason=None,
        filtered=None,
        degraded=None,
        error_code=error_code,
        message=message,
        provider_request_id=provider_request_id,
        client_correlation_id=client_correlation_id,
        recoverable=recoverable,
        unsupported_later_owner=unsupported_later_owner,
        worker_lifecycle_signal=None,
        stream_error_code=None,
        last_observed_worker_event_index=None,
        last_accepted_event_id=None,
    )


def _replace_lifecycle_index(
    plan: _TerminalPlan, last_observed_worker_event_index: int
) -> _TerminalPlan:
    """复制 failed plan 并写入 lifecycle index。

    :param plan: 原 failed plan。
    :param last_observed_worker_event_index: 最后观察到的 worker event index。
    :returns: 新 terminal plan。
    """

    return _TerminalPlan(
        attempt_event_type=plan.attempt_event_type,
        run_event_type=plan.run_event_type,
        attempt_status=plan.attempt_status,
        run_status=plan.run_status,
        reason=plan.reason,
        terminal_summary=plan.terminal_summary,
        finish_reason=plan.finish_reason,
        filtered=plan.filtered,
        degraded=plan.degraded,
        error_code=plan.error_code,
        message=plan.message,
        provider_request_id=plan.provider_request_id,
        client_correlation_id=plan.client_correlation_id,
        recoverable=plan.recoverable,
        unsupported_later_owner=plan.unsupported_later_owner,
        worker_lifecycle_signal=None,
        stream_error_code=None,
        last_observed_worker_event_index=last_observed_worker_event_index,
        last_accepted_event_id=None,
    )


def _is_preview_event(event: EngineEvent) -> bool:
    """判断 Engine event 是否属于 Phase 5 preview。

    :param event: Engine event。
    :returns: type 与 data 均匹配 preview 契约时返回 ``True``。
    """

    return (
        event.type == EngineEventType.ITERATION_STARTED
        and isinstance(event.data, IterationStartedData)
    ) or (
        event.type == EngineEventType.CONTENT_DELTA
        and isinstance(event.data, ContentDeltaData)
    ) or (
        event.type == EngineEventType.REASONING_DELTA
        and isinstance(event.data, ReasoningDeltaData)
    ) or (
        event.type == EngineEventType.CONTENT_COMPLETED
        and isinstance(event.data, ContentCompleteData)
    ) or (
        event.type == EngineEventType.TOOL_CALL_DELTA
        and isinstance(event.data, ToolCallDeltaData)
    ) or (
        event.type == EngineEventType.TOOL_CALLS_BATCH_READY
        and isinstance(event.data, ToolCallsBatchReadyData)
    ) or (
        event.type == EngineEventType.TOOL_CALL_REQUESTED
        and isinstance(event.data, ToolCallRequestedData)
    ) or (
        event.type == EngineEventType.TOOL_RESULT_ACCEPTED
        and isinstance(event.data, ToolResultAcceptedData)
    ) or (
        event.type == EngineEventType.TOOL_CALLS_BATCH_DONE
        and isinstance(event.data, ToolCallsBatchDoneData)
    ) or (
        event.type == EngineEventType.ITERATION_COMPLETED
        and isinstance(event.data, IterationCompletedData)
    )


def _preview_payload(context: _ValidatedCandidate) -> Mapping[str, JsonValue]:
    """构造 preview payload。

    :param context: 已校验 candidate 上下文。
    :returns: preview payload。
    """

    event = context.candidate.engine_event
    common: dict[str, JsonValue] = {
        "attempt_id": context.attempt.attempt_id,
        "execution_id": context.attempt.execution_id,
        "worker_event_index": context.candidate.worker_event_index,
        "engine_event_type": event.type.value,
    }
    data = event.data
    if isinstance(data, IterationStartedData):
        common["iteration_id"] = data.iteration_id
        common["iteration_index"] = data.iteration_index
        common["message_count"] = data.message_count
    elif isinstance(data, ContentDeltaData):
        common["iteration_id"] = data.iteration_id
        common["delta"] = data.delta
    elif isinstance(data, ReasoningDeltaData):
        common["iteration_id"] = data.iteration_id
        common["delta"] = data.delta
    elif isinstance(data, ContentCompleteData):
        common["iteration_id"] = data.iteration_id
        common["has_content"] = data.content is not None
        common["has_reasoning_content"] = data.reasoning_content is not None
        common["finish_reason"] = data.finish_reason.value
    elif isinstance(data, ToolCallDeltaData):
        common["iteration_id"] = data.iteration_id
        common["tool_call_index"] = data.tool_call_index
        common["tool_call_id"] = data.tool_call_id
        common["has_name_delta"] = data.name_delta is not None
        common["has_arguments_delta"] = data.arguments_delta is not None
    elif isinstance(data, ToolCallsBatchReadyData):
        common["iteration_id"] = data.iteration_id
        common["tool_call_count"] = len(data.tool_calls)
    elif isinstance(data, ToolCallRequestedData):
        common["iteration_id"] = data.iteration_id
        common["tool_call_id"] = data.tool_call_id
        common["tool_name"] = data.name
        common["index_in_iteration"] = data.index_in_iteration
        common["argument_key_count"] = len(data.arguments)
        common["provider_state_present"] = data.provider_state is not None
    elif isinstance(data, ToolResultAcceptedData):
        common["iteration_id"] = data.iteration_id
        common["tool_call_id"] = data.record.call.tool_call_id
        common["tool_name"] = data.record.call.name
        common["index_in_iteration"] = data.record.call.index_in_iteration
        common["outcome_kind"] = _accepted_tool_outcome_kind(data)
    elif isinstance(data, ToolCallsBatchDoneData):
        common["iteration_id"] = data.iteration_id
        common["tool_call_count"] = len(data.tool_call_ids)
        common["completed_count"] = data.completed_count
        common["failed_count"] = data.failed_count
        common["cancelled_count"] = data.cancelled_count
    elif isinstance(data, IterationCompletedData):
        common["iteration_id"] = data.iteration_id
        common["finish_reason"] = data.finish_reason.value
        common["provider_request_id"] = data.provider_request_id
        common["client_correlation_id"] = data.client_correlation_id
    return common


def _accepted_tool_outcome_kind(data: ToolResultAcceptedData) -> str:
    """返回 accepted tool result 的中性 outcome 分类。

    :param data: tool_result_accepted data。
    :returns: ``completed``、``failed`` 或 ``cancelled``。
    :raises HostDurableError: 遇到未知 outcome 类型时抛出。
    """

    outcome = data.record.outcome
    if isinstance(outcome, ToolCompletedOutcome):
        return "completed"
    if isinstance(outcome, ToolFailedOutcome):
        return "failed"
    if isinstance(outcome, ToolCancelledOutcome):
        return "cancelled"
    raise HostDurableError("unsupported accepted tool outcome")


def _context_compaction_payload(
    context: _ValidatedCandidate, data: ContextCompactionRequestedData
) -> Mapping[str, JsonValue]:
    """构造 context compaction diagnostic payload。

    :param context: 已校验上下文。
    :param data: context compaction data。
    :returns: diagnostic payload。
    """

    return {
        "attempt_id": context.attempt.attempt_id,
        "execution_id": context.attempt.execution_id,
        "iteration_id": data.iteration_id,
        "budget_state_present": data.budget_state is not None,
        "reason": data.reason,
        "provider_request_id": data.provider_request_id,
        "client_correlation_id": data.client_correlation_id,
        "unsupported_later_owner": _OWNER_PHASE10,
    }


def _run_suspended_payload(
    context: _ValidatedCandidate, data: RunSuspendedData
) -> Mapping[str, JsonValue]:
    """构造 run_suspended diagnostic payload。

    :param context: 已校验上下文。
    :param data: run_suspended data。
    :returns: diagnostic payload。
    """

    return {
        "attempt_id": context.attempt.attempt_id,
        "execution_id": context.attempt.execution_id,
        "reason": data.reason,
        "accepted_record_count": len(data.accepted_records),
        "awaiting_record_count": len(data.awaiting_records),
        "unsupported_later_owner": _OWNER_PHASE7,
    }


def _tool_awaiting_payload(
    context: _ValidatedCandidate, data: ToolAwaitingData
) -> Mapping[str, JsonValue]:
    """构造 tool_awaiting diagnostic payload。

    :param context: 已校验上下文。
    :param data: tool_awaiting data。
    :returns: diagnostic payload。
    """

    return {
        "attempt_id": context.attempt.attempt_id,
        "execution_id": context.attempt.execution_id,
        "iteration_id": data.iteration_id,
        "unsupported_later_owner": _OWNER_PHASE7,
    }


def _cancel_request_event_id_from_cancelling(event: EventLogRow) -> str | None:
    """从 ``RUN_CANCELLING`` fact 读取 active cancel request event id。

    durable 事件 payload 可能被外部写入或历史 bug 破坏；ingest 不能让该
    结构错误逃逸出事务边界，而应把当前 Engine terminal candidate 收敛为
    受治理 rejected diagnostic。

    :param event: 最新 ``RUN_CANCELLING`` EventLog row。
    :returns: cancel request event id；payload 缺失或非法时返回 ``None``。
    """

    try:
        return _required_payload_text(
            _payload_object(event),
            field_name="cancel_request_event_id",
        )
    except HostDurableError:
        return None


def _single_event_result(row: EventLogRow) -> EngineIngestResult:
    """构造单事件接受结果。

    :param row: EventLog row。
    :returns: ingest result。
    """

    status = EngineIngestStatus.ACCEPTED
    return EngineIngestResult(
        status=status,
        events=(row,),
        terminal_closeout=False,
        promotion_triggered=False,
        reason=None,
    )


def _merge_diagnostic_and_closeout(
    diagnostic: EventLogRow, closeout: EngineIngestResult
) -> EngineIngestResult:
    """合并 diagnostic 与 terminal closeout 结果。

    :param diagnostic: diagnostic EventLog row。
    :param closeout: terminal closeout 结果。
    :returns: 合并后的 ingest 结果。
    """

    return EngineIngestResult(
        status=closeout.status,
        events=(diagnostic, *closeout.events),
        terminal_closeout=closeout.terminal_closeout,
        promotion_triggered=closeout.promotion_triggered,
        reason=closeout.reason,
        stop_worker_stream=closeout.stop_worker_stream,
    )


__all__ = [
    "EngineEventCandidate",
    "EngineEventIngestor",
    "EngineIngestResult",
    "EngineIngestStatus",
    "LocalEngineEnvelope",
]
