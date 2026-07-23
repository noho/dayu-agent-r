"""Host-owned EngineEvent ingest 与 terminal closeout。

本模块把 Engine 公共 ``EngineEvent`` 包装在 Host-owned envelope 中进入
durable EventLog，并在 Phase 5 范围内完成 preview、projection signal、
diagnostic 与 terminal canonical facts 的映射。Engine contract 不携带
Host Attempt identity；attempt / execution / dispatch identity 只来自
本模块的 envelope 与 durable state 校验。
"""

from __future__ import annotations

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
from dayu.engine.contracts.error_codes import serialize_engine_error_code
from dayu.engine.contracts.engine_events import (
    ContentCompleteData,
    ContentDeltaData,
    ContextCompactionRequestedData,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    IterationCompletedData,
    IterationStartedData,
    ProviderDiagnosticData,
    ProviderProtocolErrorData,
    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION,
    RUN_SUSPENDED_REASON_TOOL_AWAITING,
    ReasoningDeltaData,
    RunnerInputMessageProjection,
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
from dayu.engine.contracts.partial_tool_call import PartialToolCallSummary
from dayu.host._runner_call_manifest import (
    RunnerCallHotAtoms,
    RunnerCallHotDiagnostic,
    RunnerCallProjectorMetadata,
    complete_runner_call_hot_diagnostic,
    parse_runner_call_hot_payload,
    parse_runner_call_manifest,
    runner_call_hot_diagnostic_from_json,
    runner_call_hot_payload,
    runner_call_projector_metadata_descriptor,
)
from dayu.host.admission import (
    AdmissionWakeupPort,
    NoopAdmissionWakeupPort,
    PendingDispatchRecord,
)
from dayu.host.api import (
    AttemptStatus,
    HostContentDelta,
    HostReasoningDelta,
    HostToolCallDelta,
    HostTransientDeltaType,
    RunStatus,
)
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
    PreDispatchCompactMaterialView,
    RunInputMaterialBlock,
    build_pre_dispatch_compact_material_view,
    run_input_material_block,
)
from dayu.host.compact_pipeline import (
    CompactPipelineSourceSnapshot,
    build_fallback_decision_input,
    build_normal_compact_request_plan,
    build_reactive_pass_queue_plan,
    compact_pipeline_source_snapshot_from_pre_dispatch_view,
)
from dayu.host.compaction import (
    CompactQualityCheckResultVNext,
    CompactMaterialBlockKind,
    CompactMaterialSection,
    CompactionRequest,
    ContextCompactor,
    ConversationCompactOutputVNext,
)
from dayu.host.compaction_operation import (
    CompactionAttemptRejected,
    CompactionRejectedAttemptDiagnosticReference,
    CompactionOperationResult,
    DurableCompactorProposalManifestRecorder,
    run_compaction_operation,
    write_compaction_rejected_attempt_diagnostic_artifact,
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
    FALLBACK_ACTION_NOT_APPLICABLE,
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
    BoundedJsonPayloadWriteRequest,
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
    confirm_terminal_run_in_transaction,
    fail_recovering_run_in_transaction,
    project_terminal_notice_from_exact_run_event,
    read_cancel_requested_event_from_run_link,
    start_recovery_run_with_starting_attempt_in_transaction,
    terminal_closeout_in_transaction,
)
from dayu.host.terminal_post_commit import (
    TerminalPostCommitNotice,
    TerminalPostCommitPort,
)
from dayu.host.durable.schema import (
    PayloadDescriptorKind,
    RUNNER_CALL_INPUT_MANIFEST_MEDIA_TYPE,
    RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
    RUNNER_CALL_INPUT_PROJECTION_MEDIA_TYPE,
    RUNNER_CALL_INPUT_PROJECTION_SCHEMA_VERSION,
    TABLE_EVENT_LOG,
    payload_descriptor_metadata,
)
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    RunRow,
    StateMutationStatus,
    WaitRecordRow,
    WaitRecordStatus,
    WorkerKind,
    is_terminal_attempt_status,
    is_terminal_run_status,
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
from dayu.host.lifecycle_events import (
    closeout_attempt_terminal_event_type_for_status,
    run_terminal_event_type_for_status,
)
from dayu.host.memory import (
    MemoryProjectionPolicy,
    default_memory_projection_policy,
    digest_memory_projection_policy,
)
from dayu.host.memory_repair import catch_up_conversation_memory_projection
from dayu.host.payload_resolution import event_payload_object
from dayu.host.tool_trace_signals import (
    CONTEXT_PRESSURE_SCHEMA_VERSION as _CONTEXT_PRESSURE_SCHEMA_VERSION,
    FAILURE_KIND_PROVIDER_PROTOCOL_ERROR as _FAILURE_KIND_PROVIDER_PROTOCOL_ERROR,
    FAILURE_METADATA_SCHEMA_VERSION as _FAILURE_METADATA_SCHEMA_VERSION,
    PARTIAL_TOOL_CALL_SIGNAL_SCHEMA_VERSION as _PARTIAL_TOOL_CALL_SIGNAL_SCHEMA_VERSION,
    PARTIAL_TOOL_CALL_SIGNAL_STATUS_NONE as _PARTIAL_TOOL_CALL_SIGNAL_STATUS_NONE,
    PARTIAL_TOOL_CALL_SIGNAL_STATUS_PRESENT as _PARTIAL_TOOL_CALL_SIGNAL_STATUS_PRESENT,
)
from dayu.host.transient_delta import (
    HostTransientDeltaPublisher,
    ValidatedTransientDeltaCandidate,
)
from dayu.runtime.log_levels import STREAM_DEBUG_LOG_LEVEL, VERBOSE_LOG_LEVEL

_LOGGER = logging.getLogger(__name__)
_DELTA_ENGINE_EVENT_TYPES = frozenset(
    {
        EngineEventType.CONTENT_DELTA,
        EngineEventType.REASONING_DELTA,
        EngineEventType.TOOL_CALL_DELTA,
    }
)
_EVENT_SOURCE = "host.engine_ingest"
_EVENT_ACTOR = "host.engine_ingest"
_EVENT_ID_PREFIX = "event-engine-"
_PAYLOAD_REF_PREFIX = "payload-engine-terminal"
_PAYLOAD_ID_PREFIX = "sqlite-payload-engine-terminal"
_HOST_LIFECYCLE_EVENT_SOURCE = "host.worker_lifecycle"
_HOST_LIFECYCLE_EVENT_ACTOR = "host.worker_lifecycle"
_HOST_LIFECYCLE_EVENT_ID_PREFIX = "event-host-lifecycle-"
_HOST_LIFECYCLE_PAYLOAD_REF_PREFIX = "payload-host-lifecycle-terminal"
_HOST_LIFECYCLE_PAYLOAD_ID_PREFIX = "sqlite-payload-host-lifecycle-terminal"
_EVENT_TYPE_ENGINE_EVENT_REJECTED = "ENGINE_EVENT_REJECTED"
_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC = "ENGINE_EVENT_DIAGNOSTIC"
_EVENT_TYPE_HOST_LIFECYCLE_DIAGNOSTIC = "HOST_LIFECYCLE_DIAGNOSTIC"
_EVENT_TYPE_PROVIDER_DIAGNOSTIC = "PROVIDER_DIAGNOSTIC"
_EVENT_TYPE_PROVIDER_PROTOCOL_ERROR = "PROVIDER_PROTOCOL_ERROR"
_EVENT_TYPE_RUN_RECOVERING = "RUN_RECOVERING"
_EVENT_TYPE_TOOL_AWAITING = "TOOL_AWAITING"
_EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED = "RUNNER_CALL_INPUT_ASSEMBLED"
_EVENT_TYPE_RUNNER_CALL_INPUT_ITERATION_LINKED = "RUNNER_CALL_INPUT_ITERATION_LINKED"
_EVENT_TYPE_RUN_WAITING = "RUN_WAITING"
_EVENT_TYPE_ATTEMPT_SUSPENDED = "ATTEMPT_SUSPENDED"
_REASON_FINAL_ANSWER = "final_answer"
_REASON_UNSUPPORTED_RECOVERY_POLICY = "unsupported_recovery_policy"
_REASON_UNSUPPORTED_WAITING_PATH = "unsupported_waiting_path"
_REASON_STREAM_ENDED_WITHOUT_TERMINAL = "stream_ended_without_terminal"
_REASON_WORKER_LOST_BEFORE_TERMINAL = "worker_lost_before_terminal"
_REASON_STALE_EXECUTION_ID = "stale_execution_id"
_REASON_TERMINAL_ALREADY_CLOSED = "terminal_already_closed"
_REASON_TERMINAL_CLOSEOUT_PRECONDITION_FAILED = "terminal_closeout_precondition_failed"
_REASON_LATE_TERMINAL_AFTER_ACTIVE_CANCEL = "late_terminal_after_active_cancel"
_REASON_HOST_LIFECYCLE_AFTER_ACTIVE_CANCEL = "host_lifecycle_after_active_cancel"
_REASON_WAITING_EVENT_CONFIRMATION = "waiting_event_confirmation"
_REASON_WAITING_EVENT_WITHOUT_HOST_ACCEPTED_REFS = "waiting_event_without_host_accepted_refs"
_REASON_RUN_CANCELLED_INVALID_ACTIVE_CANCEL_PAYLOAD = "run_cancelled_invalid_active_cancel_link"
_REASON_CONTEXT_COMPACTION_REQUIRED = "context_compaction_required"
_REASON_CONTEXT_COMPACTION_RECOVERY_FAILED = "context_compaction_recovery_failed"
_REASON_AMBIGUOUS_RUNNER_CALL_MANIFEST = "ambiguous_runner_call_manifest"
_REASON_RUNNER_CALL_ITERATION_LINK_CONFLICT = "runner_call_iteration_link_conflict"
_REASON_RUNNER_CALL_MANIFEST_MISMATCH = "runner_call_manifest_mismatch"
_RECOVERY_FAILURE_POLICY_DECISION = "reactive_compact_failed"
_REACTIVE_PRECONDITION_OPERATION_PREFIX = "reactive_precondition"
_OWNER_PHASE7 = "phase7"
_OWNER_PHASE10 = "phase10"
_DEFAULT_MEMORY_PROJECTION_CATCHUP_BATCH_SIZE = 100
_NO_CONTEXT_BUDGET_POLICY_REF = "none"
_USAGE_OBSERVATION_STATUS_USAGE_INVALID = "usage_invalid"
_CONTEXT_PRESSURE_SOURCE_USAGE_REPORTED = "USAGE_REPORTED"
_CONTEXT_PRESSURE_BUDGET_DECISION_UNKNOWN = "unknown"
_RUNNER_CALL_MANIFEST_STATUS_COMPLETE = "complete"
_RUNNER_CALL_MANIFEST_STATUS_LIMITED_SIGNAL = "limited_signal"
_RUNNER_CALL_MANIFEST_STATUS_MISMATCH = "mismatch"
_RUNNER_CALL_MANIFEST_REASON_MISSING = "missing_runner_call_manifest"
_RUNNER_CALL_MANIFEST_REASON_MISSING_PROJECTION = "missing_projection_artifact"
_RUNNER_CALL_MANIFEST_REASON_MESSAGE_COUNT = "message_count_mismatch"
_RUNNER_CALL_MANIFEST_REASON_ROLE_DIGEST = "role_sequence_digest_mismatch"
_RUNNER_CALL_MANIFEST_REF_PREFIX = "payload-runner-call-input-manifest"
_RUNNER_CALL_MANIFEST_SQLITE_PAYLOAD_ID_PREFIX = "sqlite-payload-runner-call-input-manifest"
_RUNNER_CALL_PROJECTION_REF_PREFIX = "payload-runner-call-input-projection"
_RUNNER_CALL_PROJECTION_SQLITE_PAYLOAD_ID_PREFIX = "sqlite-payload-runner-call-input-projection"
_RUNNER_CALL_MANIFEST_ID_PREFIX = "runner-call-manifest"
_RUNNER_CALL_KIND_INITIAL_USER_DISPATCH = "initial_user_dispatch"
_RUNNER_CALL_KIND_FOLLOWUP_USER_DISPATCH = "followup_user_dispatch"
_RUNNER_CALL_KIND_POST_COMPACTION_DISPATCH = "post_compaction_dispatch"
_RUNNER_CALL_KIND_TOOL_RESULT_CONTINUATION = "tool_result_continuation"
_RUNNER_CALL_TRIGGER_INITIAL_USER_INPUT = "initial_user_input"
_RUNNER_CALL_TRIGGER_TOOL_RESULTS_AVAILABLE = "tool_results_available"
_RUNNER_CALL_DIAGNOSTIC_MISSING_REF_KIND_PROJECTION_ARTIFACT = "artifact_ref"
_RUNNER_CALL_PROJECTOR_PURPOSE_TOOL_CONTINUATION = "tool_continuation_input"
_ORDINARY_RUNNER_CALL_KINDS = frozenset(
    (
        _RUNNER_CALL_KIND_INITIAL_USER_DISPATCH,
        _RUNNER_CALL_KIND_FOLLOWUP_USER_DISPATCH,
        _RUNNER_CALL_KIND_POST_COMPACTION_DISPATCH,
    )
)


class EngineIngestStatus(StrEnum):
    """Engine ingest 结果状态。"""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class _HostLifecycleSource(StrEnum):
    """Host worker lifecycle closeout 的强类型来源。"""

    WORKER_CLEAN_EOF = "worker_clean_eof"
    WORKER_LOST = "worker_lost"


class _TerminalCloseoutRollback(Exception):
    """terminal closeout 未更新 durable state 时触发整笔事务回滚。"""


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
    :param terminal_notice: transaction-local exact terminal notice；非终态为 ``None``。
    :param reason: 诊断 reason；无时为 ``None``。
    :param transient_delta: 事务提交后待发布的已验证瞬态候选；其它结果为
        ``None``。
    :param stop_worker_stream: 本次是否要求 scheduler 停止当前 worker stream。
    """

    status: EngineIngestStatus
    events: tuple[EventLogRow, ...]
    terminal_closeout: bool
    terminal_notice: TerminalPostCommitNotice | None
    reason: str | None
    transient_delta: ValidatedTransientDeltaCandidate | None
    stop_worker_stream: bool = False


@dataclass(frozen=True, slots=True)
class _ValidatedCandidate:
    """已通过 durable identity 校验的 candidate 上下文。"""

    candidate: EngineEventCandidate
    run: RunRow
    attempt: AttemptRow
    dispatch_record: DispatchRecordRow


@dataclass(frozen=True, slots=True)
class _RunnerCallIterationResolution:
    """runner-call manifest 与 Engine iteration 的 link resolution。

    :param status: runner-call reconstruction validation status。
    :param reason: 诊断 reason；成功时为 ``None``。
    :param link_event_id: link canonical event id；未写入 link 时为 ``None``。
    :param manifest_event_id: prepared 或 limited manifest event id。
    :param manifest_payload_ref: manifest payload descriptor ref。
    :param manifest_digest: manifest body digest。
    :param expected_count: manifest 中的 message count。
    :param expected_digest: manifest 中的 role sequence digest。
    :param observed_count: Engine observed message count。
    :param observed_digest: Engine observed role sequence digest。
    :param continuation_limited_signal: 是否为 Engine-only continuation limited signal。
    """

    status: str
    reason: str | None
    link_event_id: str | None
    manifest_event_id: str | None
    manifest_payload_ref: str | None
    manifest_digest: str | None
    expected_count: int | None
    expected_digest: str | None
    observed_count: int
    observed_digest: str
    continuation_limited_signal: bool


@dataclass(frozen=True, slots=True)
class _TerminalFactPlan:
    """两类 terminal 来源共享的 canonical fact 规划。"""

    attempt_event_type: str
    run_event_type: str
    attempt_status: AttemptStatus
    run_status: RunStatus
    reason: str
    terminal_payload: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class _EngineTerminalPlan:
    """Engine-origin terminal closeout 规划。"""

    terminal: _TerminalFactPlan
    finish_reason: str | None
    filtered: bool | None
    degraded: bool | None
    error_code: str | None
    message: str | None
    provider_request_id: str | None
    client_correlation_id: str | None
    recoverable: bool | None
    unsupported_later_owner: str | None


@dataclass(frozen=True, slots=True)
class _HostLifecycleTerminalPlan:
    """Host worker lifecycle terminal closeout 规划。"""

    terminal: _TerminalFactPlan
    error_code: str | None
    message: str | None
    recoverable: bool | None
    worker_lifecycle_signal: str | None
    stream_error_code: str | None
    last_observed_worker_event_index: int | None
    last_accepted_event_id: str | None


@dataclass(frozen=True, slots=True)
class _HostLifecycleCloseoutCandidate:
    """进入 Host lifecycle closeout 的强类型 candidate。

    :param envelope: Host-owned worker identity envelope。
    :param observed_at: Host 观察到 lifecycle signal 的 UTC aware 时间。
    :param worker_event_index: 单个 execution 内 Host 分配的 lifecycle 序号。
    :param plan: Host terminal closeout 规划。
    :param lifecycle_source: worker lifecycle signal 的强类型来源。
    """

    envelope: LocalEngineEnvelope
    observed_at: datetime
    worker_event_index: int
    plan: _HostLifecycleTerminalPlan
    lifecycle_source: _HostLifecycleSource


@dataclass(frozen=True, slots=True)
class _ValidatedHostLifecycleCloseoutCandidate:
    """已通过 durable identity 校验的 Host lifecycle candidate 上下文。

    :param candidate: Host lifecycle closeout candidate。
    :param run: 当前 durable Run row。
    :param attempt: 当前 durable Attempt row。
    :param dispatch_record: 当前 durable dispatch record row。
    """

    candidate: _HostLifecycleCloseoutCandidate
    run: RunRow
    attempt: AttemptRow
    dispatch_record: DispatchRecordRow


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
    :param source_snapshot: reactive compact 使用的 source snapshot。
    :param operation_id: request fact event id。
    :param estimate: reactive compact 前估算。
    :param decision: reactive compact 前预算决策。
    :param policy: reactive context budget policy。
    :param memory_projection_policy: reactive fallback selected window policy。
    """

    result_prefix: EngineIngestResult
    context: _ValidatedCandidate
    expected_input_event_sequence: int
    source_snapshot: CompactPipelineSourceSnapshot
    operation_id: str
    estimate: BudgetEstimate
    decision: ContextBudgetDecision
    policy: ContextBudgetPolicy
    memory_projection_policy: MemoryProjectionPolicy


@dataclass(frozen=True, slots=True)
class _ReactiveRecoveryStarted:
    """reactive recovery start 后的 dispatch 摘要。"""

    result: EngineIngestResult
    pending_dispatch: PendingDispatchRecord


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
                terminal_notice=None,
                reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
                transient_delta=None,
                stop_worker_stream=True,
            ),
            pending_dispatch=pending_dispatch,
        )


@dataclass(frozen=True, slots=True)
class _IngestValidatedOperation:
    """在单笔 durable transaction 内完成 identity/late 校验与 ingest。

    :param ingestor: 拥有 durable primitives 的 ingestor。
    :param candidate: 待校验 Engine event candidate。
    """

    ingestor: EngineEventIngestor
    candidate: EngineEventCandidate

    def __call__(
        self, transaction: HostTransaction
    ) -> EngineIngestResult | _ReactiveRecoveryAccepted | _ReactiveCompactPending:
        """执行 candidate durable validation 与 validated ingest。

        :param transaction: 当前 Host write transaction。
        :returns: ingest 结果、reactive recovery 摘要或待 compact 摘要。
        :raises HostDurableError: durable 读取或写入失败时抛出。
        """

        context = self.ingestor._validate_durable_context(
            transaction,
            self.candidate,
        )
        if context is None:
            return self.ingestor._append_rejected_diagnostic(
                transaction,
                candidate=self.candidate,
                reason=_REASON_STALE_EXECUTION_ID,
            )
        duplicate = self.ingestor._duplicate_engine_terminal_result(
            transaction,
            context,
        )
        if duplicate is not None:
            return duplicate
        late = _late_engine_event_rejection_reason(context)
        if late is not None:
            return self.ingestor._append_rejected_diagnostic(
                transaction,
                candidate=self.candidate,
                reason=late,
            )
        return self.ingestor._ingest_validated(transaction, context)


class EngineEventIngestor:
    """Host-owned EngineEvent ingest 服务。"""

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        transient_delta_publisher: HostTransientDeltaPublisher,
        terminal_post_commit_port: TerminalPostCommitPort,
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
        :param transient_delta_publisher: validation transaction 提交后的瞬态发布端口。
        :param terminal_post_commit_port: terminal commit 后的 opener-local 最终端口。
        :param event_log_store: EventLog primitive。
        :param payload_store: payload descriptor primitive。
        :param wakeup_port: reactive recovery resume commit 后的 dispatch wake 端口。
        :param context_budget_policy: reactive context governance policy。
        :param context_compactor: reactive context compactor。
        :param compact_artifact_root: compact artifact 根目录。
        :param compact_artifact_create_parent_dirs: artifact 根目录缺失时是否创建。
        :param memory_projection_policy: compact accepted 后的 memory projection policy。
        :param memory_projection_catchup_batch_size: memory projection catch-up 批大小。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._transient_delta_publisher = transient_delta_publisher
        self._terminal_post_commit_port = terminal_post_commit_port
        self._event_log_store = event_log_store if event_log_store is not None else EventLogStore()
        self._payload_store = payload_store if payload_store is not None else PayloadStore()
        self._wakeup_port = wakeup_port if wakeup_port is not None else NoopAdmissionWakeupPort()
        self._context_budget_policy = context_budget_policy
        self._context_compactor = context_compactor
        self._compact_artifact_root = compact_artifact_root
        self._compact_artifact_create_parent_dirs = compact_artifact_create_parent_dirs
        self._memory_projection_policy = (
            memory_projection_policy if memory_projection_policy is not None else default_memory_projection_policy()
        )
        self._memory_projection_catchup_batch_size = memory_projection_catchup_batch_size

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

        try:
            return self._transaction_runner.run_write(_IngestValidatedOperation(ingestor=self, candidate=candidate))
        except _TerminalCloseoutRollback:
            return _terminal_closeout_precondition_failed_result()

    def _finish_ingest(
        self,
        result: EngineIngestResult,
        *,
        candidate: EngineEventCandidate,
    ) -> EngineIngestResult:
        """完成 commit 后 terminal notice、瞬态发布与日志记录。

        :param result: 已完成 reactive recovery 处理的 ingest 结果。
        :param candidate: 原始 Engine event candidate。
        :returns: 最终 ingest 结果。
        """

        if result.terminal_notice is not None:
            self._terminal_post_commit_port.notify_terminal_post_commit(
                result.terminal_notice
            )
        if result.transient_delta is not None:
            _publish_transient_delta(
                self._transient_delta_publisher,
                result.transient_delta,
            )
        _LOGGER.log(
            _engine_ingest_log_level(candidate.engine_event.type),
            (
                "host.engine_ingest.committed session_id=%s run_id=%s "
                "attempt_id=%s execution_id=%s worker_event_index=%s "
                "engine_event_type=%s ingest_status=%s event_count=%s "
                "terminal_closeout=%s reason=%s"
            ),
            candidate.envelope.session_id,
            candidate.envelope.run_id,
            candidate.envelope.attempt_id,
            candidate.envelope.execution_id,
            candidate.worker_event_index,
            candidate.engine_event.type.value,
            result.status.value,
            len(result.events),
            result.terminal_closeout,
            result.reason,
        )
        return result

    def _duplicate_engine_terminal_result(
        self, transaction: HostTransaction, context: _ValidatedCandidate
    ) -> EngineIngestResult | None:
        """识别 Engine-origin terminal candidate 的完整重复写入。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :returns: duplicate 结果；不是完整重复时返回 ``None``。
        :raises HostDurableError: EventLog 读取失败时抛出。
        """

        event_ids = _duplicate_terminal_event_ids(context.candidate)
        if event_ids == ():
            return None
        existing = _existing_rows(self._event_log_store, transaction, event_ids)
        if len(existing) != len(event_ids):
            return None
        if context.candidate.engine_event.type == EngineEventType.CONTEXT_COMPACTION_REQUESTED:
            return EngineIngestResult(
                status=EngineIngestStatus.DUPLICATE,
                events=existing,
                terminal_closeout=False,
                terminal_notice=None,
                reason="duplicate_candidate",
                transient_delta=None,
                stop_worker_stream=True,
            )
        confirmation = confirm_terminal_run_in_transaction(
            transaction,
            self._event_log_store,
            context.run,
        )
        return EngineIngestResult(
            status=EngineIngestStatus.DUPLICATE,
            events=existing,
            terminal_closeout=True,
            terminal_notice=project_terminal_notice_from_exact_run_event(
                confirmation.run,
                confirmation.run_event,
                wake_queue_promotion=False,
            ),
            reason="duplicate_candidate",
            transient_delta=None,
        )

    def _duplicate_host_lifecycle_terminal_result(
        self,
        transaction: HostTransaction,
        context: _ValidatedHostLifecycleCloseoutCandidate,
    ) -> EngineIngestResult | None:
        """识别 Host lifecycle terminal candidate 的完整重复写入。

        :param transaction: 当前 Host transaction。
        :param context: 已校验的 Host lifecycle candidate 上下文。
        :returns: duplicate 结果；不是完整重复时返回 ``None``。
        :raises HostDurableError: EventLog 读取失败时抛出。
        """

        event_ids = _host_lifecycle_terminal_event_ids(context.candidate)
        existing = _existing_rows(self._event_log_store, transaction, event_ids)
        if len(existing) != len(event_ids):
            return None
        confirmation = confirm_terminal_run_in_transaction(
            transaction,
            self._event_log_store,
            context.run,
        )
        return EngineIngestResult(
            status=EngineIngestStatus.DUPLICATE,
            events=existing,
            terminal_closeout=True,
            terminal_notice=project_terminal_notice_from_exact_run_event(
                confirmation.run,
                confirmation.run_event,
                wake_queue_promotion=False,
            ),
            reason="duplicate_candidate",
            transient_delta=None,
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
            lifecycle_source=_HostLifecycleSource.WORKER_CLEAN_EOF,
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
            lifecycle_source=_HostLifecycleSource.WORKER_LOST,
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
        if _is_transient_delta_event(event):
            return _accepted_no_event_result(_validated_transient_delta_candidate(context, event))
        if event.type == EngineEventType.FINAL_ANSWER and isinstance(event.data, FinalAnswerData):
            return self._close_terminal(
                transaction,
                context,
                _final_answer_plan(event.data),
            )
        if event.type == EngineEventType.RUN_FAILED and isinstance(
            event.data, RunFailedData
        ):
            error_code = serialize_engine_error_code(event.data.error_code)
            if event.data.recoverable:
                diagnostic = self._append_diagnostic_event(
                    transaction,
                    context=context,
                    event_type=_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC,
                    reason=_REASON_UNSUPPORTED_RECOVERY_POLICY,
                    payload={
                        "attempt_id": context.attempt.attempt_id,
                        "execution_id": context.attempt.execution_id,
                        "error_code": error_code,
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
        if event.type == EngineEventType.ITERATION_STARTED and isinstance(
            event.data, IterationStartedData
        ):
            return self._append_iteration_started_events(
                transaction, context, event.data
            )
        if _is_preview_event(event):
            row = self._append_preview_event(transaction, context)
            return _single_event_result(row)
        if event.type == EngineEventType.PROVIDER_DIAGNOSTIC and isinstance(
            event.data, ProviderDiagnosticData
        ):
            row = self._append_provider_diagnostic(
                transaction, context, event.data
            )
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

    def _validate_host_lifecycle_context(
        self,
        transaction: HostTransaction,
        candidate: _HostLifecycleCloseoutCandidate,
    ) -> _ValidatedHostLifecycleCloseoutCandidate | None:
        """校验 Host lifecycle candidate 与 durable identity 是否同源。

        :param transaction: 当前 Host transaction。
        :param candidate: 待校验的 Host lifecycle candidate。
        :returns: 校验通过的强类型上下文；identity 不匹配时返回 ``None``。
        :raises HostDurableError: durable row 解码失败时抛出。
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
        return _ValidatedHostLifecycleCloseoutCandidate(
            candidate=candidate,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        )

    def _close_terminal(
        self,
        transaction: HostTransaction,
        context: _ValidatedCandidate,
        plan: _EngineTerminalPlan,
        *,
        sub_index_offset: int = 0,
    ) -> EngineIngestResult:
        """按 terminal plan 写入 Attempt / Run terminal facts。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param plan: terminal closeout 规划。
        :param sub_index_offset: 多事件映射时的 sub-index 偏移。
        :returns: ingest 结果。
        :raises _TerminalCloseoutRollback: terminal mutation 未更新时抛出以回滚事务。
        :raises HostDurableError: payload、EventLog 或状态写入失败时抛出。
        """

        candidate = context.candidate
        terminal = plan.terminal
        attempt_event_id = _event_id(
            candidate,
            EventClass.CANONICAL_FACT,
            terminal.attempt_event_type,
            sub_index_offset,
        )
        run_event_id = _event_id(
            candidate,
            EventClass.CANONICAL_FACT,
            terminal.run_event_type,
            sub_index_offset + 1,
        )
        existing = _existing_rows(
            self._event_log_store,
            transaction,
            (attempt_event_id, run_event_id),
        )
        if len(existing) == 2:
            confirmation = confirm_terminal_run_in_transaction(
                transaction,
                self._event_log_store,
                context.run,
            )
            return EngineIngestResult(
                status=EngineIngestStatus.DUPLICATE,
                events=existing,
                terminal_closeout=True,
                terminal_notice=project_terminal_notice_from_exact_run_event(
                    confirmation.run,
                    confirmation.run_event,
                    wake_queue_promotion=False,
                ),
                reason=terminal.reason,
                transient_delta=None,
            )
        descriptor = self._write_terminal_payload(
            transaction,
            candidate=candidate,
            event_id=attempt_event_id,
            payload=terminal.terminal_payload,
        )
        result = terminal_closeout_in_transaction(
            transaction,
            self._event_log_store,
            TerminalCloseoutInput(
                run_id=context.run.run_id,
                attempt_id=context.attempt.attempt_id,
                attempt_terminal_event_id=attempt_event_id,
                run_terminal_event_id=run_event_id,
                attempt_terminal_status=terminal.attempt_status,
                run_terminal_status=terminal.run_status,
                occurred_at=candidate.observed_at,
                actor=_EVENT_ACTOR,
                source=_EVENT_SOURCE,
                reason=terminal.reason,
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
                worker_lifecycle_signal=None,
                stream_error_code=None,
                last_observed_worker_event_index=None,
                last_accepted_event_id=None,
            ),
        )
        if result.status != StateMutationStatus.UPDATED:
            raise _TerminalCloseoutRollback(
                f"Engine terminal closeout returned {result.status.value}"
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
            terminal_notice=project_terminal_notice_from_exact_run_event(
                result.run,
                result.run_event,
                wake_queue_promotion=True,
            ),
            reason=terminal.reason,
            transient_delta=None,
        )

    def _close_host_lifecycle_terminal(
        self,
        transaction: HostTransaction,
        context: _ValidatedHostLifecycleCloseoutCandidate,
    ) -> EngineIngestResult:
        """按 Host lifecycle plan 写入 Attempt / Run terminal facts。

        :param transaction: 当前 Host transaction。
        :param context: 已校验的 Host lifecycle candidate 上下文。
        :returns: lifecycle closeout 结果。
        :raises _TerminalCloseoutRollback: terminal mutation 未更新时抛出以回滚事务。
        :raises HostDurableError: payload 或 terminal transaction 写入失败时抛出。
        """

        candidate = context.candidate
        plan = candidate.plan
        terminal = plan.terminal
        attempt_event_id, run_event_id = _host_lifecycle_terminal_event_ids(
            candidate
        )
        existing = _existing_rows(
            self._event_log_store,
            transaction,
            (attempt_event_id, run_event_id),
        )
        if len(existing) == 2:
            confirmation = confirm_terminal_run_in_transaction(
                transaction,
                self._event_log_store,
                context.run,
            )
            return EngineIngestResult(
                status=EngineIngestStatus.DUPLICATE,
                events=existing,
                terminal_closeout=True,
                terminal_notice=project_terminal_notice_from_exact_run_event(
                    confirmation.run,
                    confirmation.run_event,
                    wake_queue_promotion=False,
                ),
                reason=terminal.reason,
                transient_delta=None,
            )
        descriptor = self._write_host_lifecycle_terminal_payload(
            transaction,
            candidate=candidate,
            event_id=attempt_event_id,
        )
        result = terminal_closeout_in_transaction(
            transaction,
            self._event_log_store,
            TerminalCloseoutInput(
                run_id=context.run.run_id,
                attempt_id=context.attempt.attempt_id,
                attempt_terminal_event_id=attempt_event_id,
                run_terminal_event_id=run_event_id,
                attempt_terminal_status=terminal.attempt_status,
                run_terminal_status=terminal.run_status,
                occurred_at=candidate.observed_at,
                actor=_HOST_LIFECYCLE_EVENT_ACTOR,
                source=_HOST_LIFECYCLE_EVENT_SOURCE,
                reason=terminal.reason,
                terminal_summary_ref=descriptor.payload_ref,
                terminal_summary_digest=descriptor.payload_digest,
                engine_event_ref=None,
                finish_reason=None,
                filtered=None,
                degraded=None,
                error_code=plan.error_code,
                message=plan.message,
                provider_request_id=None,
                client_correlation_id=None,
                recoverable=plan.recoverable,
                unsupported_later_owner=None,
                worker_lifecycle_signal=plan.worker_lifecycle_signal,
                stream_error_code=plan.stream_error_code,
                last_observed_worker_event_index=(
                    plan.last_observed_worker_event_index
                ),
                last_accepted_event_id=plan.last_accepted_event_id,
            ),
        )
        if result.status != StateMutationStatus.UPDATED:
            raise _TerminalCloseoutRollback(
                f"Host lifecycle terminal closeout returned {result.status.value}"
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
            terminal_notice=project_terminal_notice_from_exact_run_event(
                result.run,
                result.run_event,
                wake_queue_promotion=True,
            ),
            reason=terminal.reason,
            transient_delta=None,
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
            _closeout_attempt_event_type(AttemptStatus.CANCELLED),
            0,
        )
        run_event_id = _event_id(
            candidate,
            EventClass.CANONICAL_FACT,
            _run_terminal_event_type(RunStatus.CANCELLED),
            1,
        )
        existing = _existing_rows(
            self._event_log_store,
            transaction,
            (attempt_event_id, run_event_id),
        )
        if len(existing) == 2:
            confirmation = confirm_terminal_run_in_transaction(
                transaction,
                self._event_log_store,
                context.run,
            )
            return EngineIngestResult(
                status=EngineIngestStatus.DUPLICATE,
                events=existing,
                terminal_closeout=True,
                terminal_notice=project_terminal_notice_from_exact_run_event(
                    confirmation.run,
                    confirmation.run_event,
                    wake_queue_promotion=False,
                ),
                reason=data.reason,
                transient_delta=None,
            )
        cancel_requested = read_cancel_requested_event_from_run_link(
            transaction,
            self._event_log_store,
            context.run,
        )
        if cancel_requested is None:
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
                cancel_request_event_id=cancel_requested.event_id,
                engine_event_ref=_engine_event_ref(candidate),
                requested_at=cancel_requested.occurred_at,
                accepted_at=format_utc_timestamp(data.accepted_at),
                finished_at=format_utc_timestamp(data.finished_at),
            ),
        )
        if result.status != StateMutationStatus.UPDATED:
            return EngineIngestResult(
                status=EngineIngestStatus.REJECTED,
                events=(),
                terminal_closeout=True,
                terminal_notice=None,
                reason="active_cancel_closeout_precondition_failed",
                transient_delta=None,
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
            terminal_notice=project_terminal_notice_from_exact_run_event(
                result.run,
                result.run_event,
                wake_queue_promotion=True,
            ),
            reason=data.reason,
            transient_delta=None,
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
        try:
            material_view = build_pre_dispatch_compact_material_view(
                transaction,
                self._event_log_store,
                run=context.run,
                current_display_text=display_text,
            )
            frozen_material_blocks = _frozen_reactive_material_blocks(
                context=context,
                display_text=display_text,
                material_view=material_view,
            )
            source_snapshot = compact_pipeline_source_snapshot_from_pre_dispatch_view(
                trigger_source=ContextCompactionTriggerSource.REACTIVE,
                run=context.run,
                material_view=material_view,
            )
        except Exception:
            _LOGGER.error(
                "engine_ingest.reactive_compact_material_source_failed session_id=%s run_id=%s",
                context.run.session_id,
                context.run.run_id,
                exc_info=True,
            )
            return self._fail_reactive_recovery_without_request(
                transaction,
                context=context,
                data=data,
                failure_reason="material_source_failed",
                message="Reactive compaction material source failed",
                estimate=estimate,
            )
        frozen_material_list_digest = _material_list_digest(frozen_material_blocks)
        frozen_material_refs = _material_source_refs(frozen_material_blocks)
        operation_id = _event_id(
            context.candidate,
            EventClass.CANONICAL_FACT,
            CONTEXT_COMPACTION_REQUESTED,
            0,
        )
        requested = self._append_reactive_compaction_requested_event(
            transaction,
            operation_id=operation_id,
            max_compaction_attempts_per_operation=(
                policy.max_compaction_attempts_per_operation
            ),
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
                terminal_notice=None,
                reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
                transient_delta=None,
                stop_worker_stream=True,
            ),
            context=context,
            expected_input_event_sequence=context.run.input_event_sequence,
            source_snapshot=source_snapshot,
            operation_id=requested.event_id,
            estimate=estimate,
            decision=decision,
            policy=policy,
            memory_projection_policy=self._memory_projection_policy,
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
            terminal_notice=run_failed.terminal_notice,
            reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
            transient_delta=None,
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
            _closeout_attempt_event_type(AttemptStatus.FAILED),
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
                terminal_notice=None,
                reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
                transient_delta=None,
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
                terminal_notice=None,
                reason="context_recovery_close_precondition_failed",
                transient_delta=None,
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
            terminal_notice=None,
            reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
            transient_delta=None,
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
        operation_id: str,
        max_compaction_attempts_per_operation: int,
        context: _ValidatedCandidate,
        data: ContextCompactionRequestedData,
        estimate: BudgetEstimate,
        decision: ContextBudgetDecision,
        frozen_material_list_digest: str,
        frozen_material_refs: tuple[str, ...],
    ) -> EventLogRow:
        """追加 reactive ``CONTEXT_COMPACTION_REQUESTED`` fact。

        :param transaction: 当前 Host transaction。
        :param operation_id: 与 request event id 同源的预生成 operation id。
        :param max_compaction_attempts_per_operation: 当前 pending policy 冻结预算。
        :param context: 已校验 candidate 上下文。
        :param data: Engine context compaction requested data。
        :param estimate: Host budget estimate。
        :param decision: Host budget decision。
        :param frozen_material_list_digest: overflow material list digest。
        :param frozen_material_refs: overflow material source refs。
        :returns: EventLog row。
        """

        candidate = context.candidate
        policy_ref = self._context_budget_policy.policy_ref if self._context_budget_policy is not None else "none"
        return self._event_log_store.append_event(
            transaction,
            EventLogAppendRequest(
                event_id=operation_id,
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
                payload_json=build_context_compaction_requested_payload(
                    operation_id=operation_id,
                    max_compaction_attempts_per_operation=(
                        max_compaction_attempts_per_operation
                    ),
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
                    client_correlation_id=data.client_correlation_id,
                    frozen_material_list_digest=frozen_material_list_digest,
                    frozen_material_refs=frozen_material_refs,
                ),
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

        memory_policy = pending.memory_projection_policy
        request_plan = build_normal_compact_request_plan(
            source_snapshot=pending.source_snapshot,
            selection_policy_digest=digest_memory_projection_policy(memory_policy),
            budget_before_compact=pending.estimate,
            selected_recent_window_turn_floor=(
                memory_policy.selected_recent_window_turn_floor
            ),
            attempt_id=pending.context.attempt.attempt_id,
            execution_id=pending.context.attempt.execution_id,
        )
        request = request_plan.request
        pass_queue = build_reactive_pass_queue_plan(
            source_snapshot=pending.source_snapshot,
            root_request_plan=request_plan,
        ).pass_requests
        compactor = self._context_compactor
        artifact_root = self._compact_artifact_root
        if compactor is None or artifact_root is None:
            operation_result = CompactionOperationResult(
                accepted_candidate=None,
                quality_result=None,
                rejected_attempts=(),
                failure_reason="compactor_or_artifact_store_missing",
                budget_after_attempted_compact=None,
                accepted_attempt_number=None,
            )
        else:
            operation_result = await run_compaction_operation(
                request=request,
                compactor=compactor,
                first_attempt_number=1,
                max_attempt_number=(
                    pending.policy.max_compaction_attempts_per_operation
                ),
                cancellation_token=(
                    pending.context.candidate.envelope.cancellation_token
                ),
                pass_queue=pass_queue,
                compaction_operation_id=pending.operation_id,
                proposal_manifest_recorder=(
                    self._compactor_proposal_manifest_recorder()
                ),
            )

        def _operation(
            transaction: HostTransaction,
        ) -> EngineIngestResult | _ReactiveRecoveryAccepted:
            latest = self._validate_durable_context(
                transaction, pending.context.candidate
            )
            if latest is None:
                return pending.result_prefix
            sequence_stale = latest.run.input_event_sequence != pending.expected_input_event_sequence
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
                    terminal_notice=None,
                    reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
                    transient_delta=None,
                    stop_worker_stream=True,
                )
            if latest.run.status is not RunStatus.RECOVERING or not is_terminal_attempt_status(latest.attempt.status):
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
                failure_reason = operation_result.failure_reason or "compaction_failed"
                attempt_count = len(operation_result.rejected_attempts)
                retry_repair_budget_exhausted = attempt_count > 0
                fallback_decision = build_fallback_decision_input(
                    source_snapshot=pending.source_snapshot,
                    context_policy=pending.policy,
                    memory_policy=pending.memory_projection_policy,
                    operation_id=pending.operation_id,
                    failure_reason=failure_reason,
                    attempt_count=attempt_count,
                    retry_repair_budget_exhausted=retry_repair_budget_exhausted,
                    budget_after_attempted_compact=(
                        operation_result.budget_after_attempted_compact
                    ),
                )
                failed_input = fallback_decision.failed_payload_input
                failed = self._append_reactive_compaction_failed_event(
                    transaction,
                    context=latest,
                    estimate=pending.estimate,
                    operation_id=failed_input.operation_id,
                    failure_reason=failed_input.failure_reason,
                    attempt_count=failed_input.attempt_count,
                    retry_repair_budget_exhausted=(
                        failed_input.retry_repair_budget_exhausted
                    ),
                    budget_after_attempted_compact=(
                        failed_input.budget_after_attempted_compact
                    ),
                    fallback_policy_decision=failed_input.fallback_policy_decision,
                    fallback_input_window=failed_input.fallback_input_window,
                    fallback_input_digest=failed_input.fallback_input_digest,
                    fallback_budget_result=failed_input.fallback_budget_result,
                    fallback_action=failed_input.fallback_action,
                )
                if fallback_decision.action_hint == FALLBACK_ACTION_DISPATCH:
                    return _ReactiveRecoveryAccepted(
                        result=EngineIngestResult(
                            status=EngineIngestStatus.ACCEPTED,
                            events=(
                                *pending.result_prefix.events,
                                *tuple(attempt_rows),
                                failed,
                            ),
                            terminal_closeout=False,
                            terminal_notice=None,
                            reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
                            transient_delta=None,
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
                if fail_result.status is not EngineIngestStatus.ACCEPTED:
                    return EngineIngestResult(
                        status=fail_result.status,
                        events=(
                            *pending.result_prefix.events,
                            *tuple(attempt_rows),
                            failed,
                            *fail_result.events,
                        ),
                        terminal_closeout=False,
                        terminal_notice=None,
                        reason=fail_result.reason,
                        transient_delta=None,
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
                    terminal_notice=fail_result.terminal_notice,
                    reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
                    transient_delta=None,
                )
            compacted = self._append_reactive_compacted_event(
                transaction,
                context=latest,
                request=request,
                decision=pending.decision,
                operation_id=pending.operation_id,
                accepted_attempt_number=_required_accepted_attempt_number(
                    operation_result
                ),
                candidate=operation_result.accepted_candidate,
                quality=operation_result.quality_result,
                budget_after_compact=(
                    operation_result.budget_after_attempted_compact
                    if operation_result.budget_after_attempted_compact is not None
                    else pending.estimate.estimated_input_tokens
                ),
                accepted_proposal_manifest_ref=(
                    operation_result.accepted_proposal_manifest_ref
                ),
                accepted_proposal_manifest_digest=(
                    operation_result.accepted_proposal_manifest_digest
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
                    terminal_notice=None,
                    reason=_REASON_CONTEXT_COMPACTION_REQUIRED,
                    transient_delta=None,
                    stop_worker_stream=True,
                ),
                run_id=latest.run.run_id,
                session_id=latest.run.session_id,
                source_attempt_id=latest.attempt.attempt_id,
                compacted_event_id=compacted.event_id,
                compacted_event_sequence=compacted.event_sequence,
            )

        return self._transaction_runner.run_write(_operation)

    def _compactor_proposal_manifest_recorder(
        self,
    ) -> DurableCompactorProposalManifestRecorder:
        """构造 reactive compactor proposal durable manifest recorder。

        :returns: durable manifest recorder。
        :raises Exception: 不主动抛出异常。
        """

        return DurableCompactorProposalManifestRecorder(
            transaction_runner=self._transaction_runner,
            event_log_store=self._event_log_store,
            event_source=_EVENT_SOURCE,
        )

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
        accepted_proposal_manifest_ref: str | None,
        accepted_proposal_manifest_digest: str | None,
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
        :param accepted_proposal_manifest_ref: accepted proposal manifest ref。
        :param accepted_proposal_manifest_digest: accepted proposal manifest digest。
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
                    accepted_proposal_manifest_ref=accepted_proposal_manifest_ref,
                    accepted_proposal_manifest_digest=(
                        accepted_proposal_manifest_digest
                    ),
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

        diagnostic_reference = self._write_reactive_compaction_rejected_diagnostic(
            transaction,
            operation_id=operation_id,
            rejected=rejected,
        )
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
                    proposal_manifest_ref=rejected.proposal_manifest_ref,
                    proposal_manifest_digest=rejected.proposal_manifest_digest,
                    diagnostic_artifact_ref=(
                        None
                        if diagnostic_reference is None
                        else diagnostic_reference.payload_ref
                    ),
                    diagnostic_artifact_digest=(
                        None
                        if diagnostic_reference is None
                        else diagnostic_reference.payload_digest
                    ),
                    failure_stage=(
                        None
                        if diagnostic_reference is None
                        else diagnostic_reference.diagnostic.failure_stage
                    ),
                    diagnostic_suffix=(
                        None
                        if diagnostic_reference is None
                        else diagnostic_reference.diagnostic.diagnostic_suffix
                    ),
                    parser_or_validator=(
                        None
                        if diagnostic_reference is None
                        else diagnostic_reference.diagnostic.parser_or_validator
                    ),
                    exception_class=(
                        None
                        if diagnostic_reference is None
                        else diagnostic_reference.diagnostic.exception_class
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
                        None
                        if diagnostic_reference is None
                        else diagnostic_reference.diagnostic.material_pack_digest
                    ),
                ),
                payload_ref=None,
                payload_digest=None,
            ),
        ).row

    def _write_reactive_compaction_rejected_diagnostic(
        self,
        transaction: HostTransaction,
        *,
        operation_id: str,
        rejected: CompactionAttemptRejected,
    ) -> CompactionRejectedAttemptDiagnosticReference | None:
        """写入 reactive rejected attempt diagnostic artifact。

        :param transaction: 当前 Host transaction。
        :param operation_id: compaction operation id。
        :param rejected: rejected attempt 摘要。
        :returns: 已持久化 diagnostic 引用；没有 diagnostic 或写入失败时为
            ``None``。
        """

        diagnostic = rejected.diagnostic
        artifact_root = self._compact_artifact_root
        if diagnostic is None or artifact_root is None:
            return None
        try:
            reference = write_compaction_rejected_attempt_diagnostic_artifact(
                transaction=transaction,
                artifact_store=LocalArtifactStore(
                    artifact_root,
                    create_artifact_root=self._compact_artifact_create_parent_dirs,
                ),
                payload_store=self._payload_store,
                diagnostic=diagnostic,
                compaction_operation_id=operation_id,
                compaction_attempt_number=rejected.attempt_number,
            )
        except HostDurableError as exc:
            _LOGGER.warning(
                "engine_ingest.compact.rejected_diagnostic_write_failed "
                "operation_id=%s attempt_number=%s failure_stage=%s message=%s",
                operation_id,
                rejected.attempt_number,
                diagnostic.failure_stage,
                str(exc),
            )
            return None
        _LOGGER.info(
            "engine_ingest.compact.rejected_diagnostic_artifact "
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
            _run_terminal_event_type(RunStatus.FAILED),
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
                terminal_notice=None,
                reason="recovering_run_failed_precondition_failed",
                transient_delta=None,
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
            terminal_notice=project_terminal_notice_from_exact_run_event(
                result.run,
                result.run_event,
                wake_queue_promotion=True,
            ),
            reason=_REASON_CONTEXT_COMPACTION_RECOVERY_FAILED,
            transient_delta=None,
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
            try:
                catch_up_conversation_memory_projection(
                    self._transaction_runner,
                    policy=self._memory_projection_policy,
                    batch_size=self._memory_projection_catchup_batch_size,
                    max_event_sequence=accepted.compacted_event_sequence,
                )
            except Exception as exc:
                _LOGGER.warning(
                    "engine_ingest.reactive_recovery.memory_catch_up_failed "
                    "session_id=%s run_id=%s compacted_event_sequence=%s "
                    "error_type=%s message=%s",
                    accepted.session_id,
                    accepted.run_id,
                    accepted.compacted_event_sequence,
                    type(exc).__name__,
                    str(exc),
                    exc_info=True,
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
                terminal_notice=None,
                reason=reason,
                transient_delta=None,
                stop_worker_stream=check.accepted,
            )
        diagnostic_payload: dict[str, JsonValue] = dict(payload)
        diagnostic_payload["run_status"] = context.run.status.value
        diagnostic_payload["attempt_status"] = context.attempt.status.value
        diagnostic_payload["waiting_confirmation_accepted"] = check.accepted
        diagnostic_payload["wait_id"] = check.wait_record.wait_id if check.wait_record is not None else None
        diagnostic_payload["waiting_confirmation_mismatch_reason"] = check.mismatch_reason
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
            terminal_notice=None,
            reason=reason,
            transient_delta=None,
            stop_worker_stream=check.accepted,
        )

    def _close_worker_lifecycle(
        self,
        envelope: LocalEngineEnvelope,
        *,
        observed_at: datetime,
        event_index: int,
        lifecycle_source: _HostLifecycleSource,
        plan: _HostLifecycleTerminalPlan,
    ) -> EngineIngestResult:
        """按 worker lifecycle signal 执行 terminal closeout。

        :param envelope: Host-owned identity envelope。
        :param observed_at: Host 观察时间。
        :param event_index: Host worker lifecycle event index。
        :param lifecycle_source: Host worker lifecycle 来源。
        :param plan: terminal closeout 规划。
        :returns: closeout 结果。
        :raises ValueError: candidate identity、时间或 event index 非法时抛出。
        :raises HostDurableError: durable identity、EventLog 或 closeout 写入失败时抛出。
        """

        candidate = _HostLifecycleCloseoutCandidate(
            envelope=envelope,
            observed_at=observed_at,
            worker_event_index=event_index,
            plan=plan,
            lifecycle_source=lifecycle_source,
        )
        _validate_host_lifecycle_candidate_shape(candidate)

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
            plan.terminal.reason,
        )

        def _operation(transaction: HostTransaction) -> EngineIngestResult:
            context = self._validate_host_lifecycle_context(transaction, candidate)
            if context is None:
                return self._append_stale_host_lifecycle_diagnostic(
                    transaction,
                    candidate=candidate,
                    reason=_REASON_STALE_EXECUTION_ID,
                )
            duplicate = self._duplicate_host_lifecycle_terminal_result(
                transaction, context
            )
            if duplicate is not None:
                return duplicate
            late = _late_host_lifecycle_rejection_reason(context)
            if late is not None:
                return self._append_host_lifecycle_diagnostic(
                    transaction,
                    context=context,
                    reason=late,
                )
            return self._close_host_lifecycle_terminal(transaction, context)

        try:
            result = self._transaction_runner.run_write(_operation)
        except _TerminalCloseoutRollback:
            result = _terminal_closeout_precondition_failed_result()
        if result.terminal_notice is not None:
            self._terminal_post_commit_port.notify_terminal_post_commit(
                result.terminal_notice
            )
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.engine_ingest.lifecycle_closeout.committed session_id=%s "
            "run_id=%s attempt_id=%s execution_id=%s event_index=%s "
            "ingest_status=%s event_count=%s terminal_closeout=%s "
            "reason=%s",
            envelope.session_id,
            envelope.run_id,
            envelope.attempt_id,
            envelope.execution_id,
            event_index,
            result.status.value,
            len(result.events),
            result.terminal_closeout,
            result.reason,
        )
        return result

    def _append_preview_event(
        self,
        transaction: HostTransaction,
        context: _ValidatedCandidate,
        *,
        payload: Mapping[str, JsonValue] | None = None,
    ) -> EventLogRow:
        """追加 preview Engine event。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param payload: 已由专用路径构造的 preview payload；为 ``None`` 时
            使用通用 preview payload builder。
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
                payload=(
                    _preview_payload(transaction, context)
                    if payload is None
                    else payload
                ),
                reason=None,
            ),
        ).row

    def _append_iteration_started_events(
        self,
        transaction: HostTransaction,
        context: _ValidatedCandidate,
        data: IterationStartedData,
    ) -> EngineIngestResult:
        """追加 iteration started 的 canonical manifest signal 与 preview。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param data: Engine iteration started data。
        :returns: 本次 ingest 结果。
        """

        rows: list[EventLogRow] = []
        existing_link = _find_runner_call_iteration_link_event(
            transaction,
            run_id=context.run.run_id,
            attempt_id=context.attempt.attempt_id,
            execution_id=context.attempt.execution_id,
            iteration_id=data.iteration_id,
        )
        if existing_link is not None:
            if not _runner_call_iteration_link_matches(
                existing_link,
                data,
            ):
                return self._append_rejected_diagnostic(
                    transaction,
                    candidate=context.candidate,
                    reason=_REASON_RUNNER_CALL_ITERATION_LINK_CONFLICT,
                    stop_worker_stream=True,
                    runner_call_iteration_link_event_id=existing_link.event_id,
                )
            resolution = _resolution_from_link_event(existing_link, data)
            if resolution.status != _RUNNER_CALL_MANIFEST_STATUS_COMPLETE:
                return self._append_rejected_diagnostic(
                    transaction,
                    candidate=context.candidate,
                    reason=_REASON_RUNNER_CALL_MANIFEST_MISMATCH,
                    stop_worker_stream=True,
                    runner_call_iteration_link_event_id=existing_link.event_id,
                    runner_call_manifest_event_id=resolution.manifest_event_id,
                    manifest_payload_ref=resolution.manifest_payload_ref,
                    manifest_digest=resolution.manifest_digest,
                )
            preview = self._append_preview_event(
                transaction,
                context,
                payload=_iteration_started_preview_payload(
                    context, data, resolution
                ),
            )
            return _event_rows_result((preview,))

        candidates = _find_unlinked_prepared_runner_call_manifest_events(
            transaction,
            run_id=context.run.run_id,
            attempt_id=context.attempt.attempt_id,
            execution_id=context.attempt.execution_id,
        )
        if len(candidates) > 1:
            return self._append_rejected_diagnostic(
                transaction,
                candidate=context.candidate,
                reason=_REASON_AMBIGUOUS_RUNNER_CALL_MANIFEST,
                stop_worker_stream=True,
            )
        if len(candidates) == 0:
            if not _has_prior_iteration_observation(
                transaction,
                run_id=context.run.run_id,
                attempt_id=context.attempt.attempt_id,
                execution_id=context.attempt.execution_id,
            ):
                return self._append_rejected_diagnostic(
                    transaction,
                    candidate=context.candidate,
                    reason=_RUNNER_CALL_MANIFEST_REASON_MISSING,
                    stop_worker_stream=True,
                )
            manifest_event = self._append_limited_runner_call_manifest_event(
                transaction,
                context,
                data,
                runner_call_kind=_RUNNER_CALL_KIND_TOOL_RESULT_CONTINUATION,
                runner_call_trigger_reason=_RUNNER_CALL_TRIGGER_TOOL_RESULTS_AVAILABLE,
            )
            rows.append(manifest_event)
            resolution = _resolution_from_limited_manifest_event(
                manifest_event,
                data,
            )
            preview = self._append_preview_event(
                transaction,
                context,
                payload=_iteration_started_preview_payload(
                    context, data, resolution
                ),
            )
            rows.append(preview)
            return _event_rows_result(tuple(rows))

        manifest_event = candidates[0]
        link_event = self._append_runner_call_iteration_link_event(
            transaction,
            context,
            data,
            manifest_event=manifest_event,
        )
        resolution = _resolution_from_link_event(link_event, data)
        if resolution.status == _RUNNER_CALL_MANIFEST_STATUS_MISMATCH:
            return self._append_rejected_diagnostic(
                transaction,
                candidate=context.candidate,
                reason=_REASON_RUNNER_CALL_MANIFEST_MISMATCH,
                stop_worker_stream=True,
                additional_events=(link_event,),
                runner_call_iteration_link_event_id=link_event.event_id,
                runner_call_manifest_event_id=manifest_event.event_id,
                manifest_payload_ref=resolution.manifest_payload_ref,
                manifest_digest=resolution.manifest_digest,
            )
        rows.append(link_event)
        rows.append(
            self._append_preview_event(
                transaction,
                context,
                payload=_iteration_started_preview_payload(
                    context, data, resolution
                ),
            )
        )
        return _event_rows_result(tuple(rows))

    def _append_limited_runner_call_manifest_event(
        self,
        transaction: HostTransaction,
        context: _ValidatedCandidate,
        data: IterationStartedData,
        *,
        runner_call_kind: str | None = None,
        runner_call_trigger_reason: str | None = None,
    ) -> EventLogRow:
        """为 Engine-only runner continuation 写入 limited-signal manifest。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param data: Engine iteration started data。
        :param runner_call_kind: Host 已判定的 runner call kind；为 ``None`` 时
            按 Engine iteration signal 推导。
        :param runner_call_trigger_reason: Host 已判定的 trigger reason；为
            ``None`` 时按 Engine iteration signal 推导。
        :returns: `RUNNER_CALL_INPUT_ASSEMBLED` canonical EventLog row。
        :raises HostDurableError: payload descriptor 或 manifest 校验失败时抛出。
        """

        event_id = _event_id(
            context.candidate,
            EventClass.CANONICAL_FACT,
            _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
            0,
        )
        runner_call_index = _next_runner_call_index(
            transaction, context.run.run_id
        )
        projection_descriptor: PayloadDescriptor | None = None
        if _has_complete_observed_input_projection(data):
            projection = _observed_runner_call_projection_body(
                context,
                data,
                runner_call_index=runner_call_index,
                projection_id=_runner_call_projection_id(event_id),
                runner_call_kind=runner_call_kind,
                runner_call_trigger_reason=runner_call_trigger_reason,
            )
            projection_digest = sha256_digest_json(projection)
            projection_descriptor = _write_runner_call_projection_payload(
                transaction,
                self._payload_store,
                event_id=event_id,
                projection=projection,
                projection_digest=projection_digest,
            )
        manifest = _limited_runner_call_manifest_body(
            context,
            data,
            runner_call_index=runner_call_index,
            manifest_id=_runner_call_manifest_id(event_id),
            runner_call_kind=runner_call_kind,
            runner_call_trigger_reason=runner_call_trigger_reason,
            projection_descriptor=projection_descriptor,
        )
        manifest_digest = sha256_digest_json(manifest)
        descriptor = _write_runner_call_manifest_payload(
            transaction,
            self._payload_store,
            event_id=event_id,
            manifest=manifest,
            manifest_digest=manifest_digest,
        )
        return self._event_log_store.append_event(
            transaction,
            _runner_call_manifest_event_request(
                context=context,
                event_id=event_id,
                manifest=manifest,
                manifest_payload_ref=descriptor.payload_ref,
                manifest_digest=manifest_digest,
            ),
        ).row

    def _append_runner_call_iteration_link_event(
        self,
        transaction: HostTransaction,
        context: _ValidatedCandidate,
        data: IterationStartedData,
        *,
        manifest_event: EventLogRow,
    ) -> EventLogRow:
        """追加 prepared manifest 与 Engine iteration 的 link fact。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param data: Engine iteration started data。
        :param manifest_event: 被 link 的 prepared manifest event。
        :returns: `RUNNER_CALL_INPUT_ITERATION_LINKED` EventLog row。
        :raises HostDurableError: manifest hot payload 字段非法时抛出。
        """

        payload = _runner_call_iteration_link_payload(
            manifest_event,
            data,
        )
        candidate = context.candidate
        return self._event_log_store.append_event(
            transaction,
            _event_request(
                candidate=candidate,
                event_id=_event_id(
                    candidate,
                    EventClass.CANONICAL_FACT,
                    _EVENT_TYPE_RUNNER_CALL_INPUT_ITERATION_LINKED,
                    0,
                ),
                event_class=EventClass.CANONICAL_FACT,
                event_type=_EVENT_TYPE_RUNNER_CALL_INPUT_ITERATION_LINKED,
                payload=payload,
                reason={"runner_call_manifest_event_id": manifest_event.event_id},
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
        estimate = self._estimate_usage_observation_input(transaction, context)
        diagnostic = self._usage_observation_diagnostic(
            context=context,
            data=data,
            estimate=estimate,
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
                    "provider_request_id": data.provider_request_id,
                    "policy_ref": diagnostic.policy_ref,
                    "estimator_digest": diagnostic.estimator_digest,
                    "estimated_input_tokens": diagnostic.estimated_input_tokens,
                    "usage_observation_status": diagnostic.status,
                    "usage_observation_digest": diagnostic.observation_digest,
                    "prompt_token_delta": diagnostic.prompt_token_delta,
                    "context_pressure": _usage_context_pressure_signal(
                        data=data,
                        diagnostic=diagnostic,
                        estimate=estimate,
                    ),
                },
                reason=None,
            ),
        ).row

    def _usage_observation_diagnostic(
        self,
        *,
        context: _ValidatedCandidate,
        data: UsageReportedData,
        estimate: BudgetEstimate | None,
    ) -> UsageObservationDiagnostic:
        """构造 usage observation diagnostic，失败时降级为估算不可用。

        :param context: 已校验 candidate 上下文。
        :param data: usage_reported data。
        :param estimate: 当前 Run 输入估算；不可用时为 ``None``。
        :returns: usage observation diagnostic。
        """

        policy_ref = (
            self._context_budget_policy.policy_ref
            if self._context_budget_policy is not None
            else _NO_CONTEXT_BUDGET_POLICY_REF
        )
        estimator_digest = estimate.estimator_digest if estimate is not None else None
        estimated_input_tokens = estimate.estimated_input_tokens if estimate is not None else None
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
                provider_request_id=data.provider_request_id,
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
                ("host.engine_ingest.usage_observation_invalid session_id=%s run_id=%s attempt_id=%s execution_id=%s"),
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
        raw_payload_present = raw_descriptor is not None
        raw_payload_ref = raw_descriptor.payload_ref if raw_descriptor is not None else None
        raw_payload_digest = raw_descriptor.payload_digest if raw_descriptor is not None else None
        candidate = context.candidate
        payload: dict[str, JsonValue] = {
            "attempt_id": context.attempt.attempt_id,
            "execution_id": context.attempt.execution_id,
            "iteration_id": data.iteration_id,
            "error_code": serialize_engine_error_code(data.error_code),
            "message": data.message,
            "provider_request_id": data.provider_request_id,
            "client_correlation_id": data.client_correlation_id,
            "raw_payload_ref": raw_payload_ref,
            "raw_payload_digest": raw_payload_digest,
            "partial_tool_call_count": len(data.partial_tool_calls),
            "partial_tool_call_signal": _provider_protocol_partial_tool_call_signal(
                partial_tool_calls=data.partial_tool_calls,
                raw_payload_present=raw_payload_present,
            ),
            "failure_metadata": _provider_protocol_failure_metadata(
                data=data,
                raw_payload_ref=raw_payload_ref,
            ),
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
                reason={"reason": serialize_engine_error_code(data.error_code)},
            ),
        ).row

    def _append_provider_diagnostic(
        self,
        transaction: HostTransaction,
        context: _ValidatedCandidate,
        data: ProviderDiagnosticData,
    ) -> EventLogRow:
        """追加 provider 非致命诊断事件。

        :param transaction: 当前 Host transaction。
        :param context: 已校验 candidate 上下文。
        :param data: provider diagnostic data。
        :returns: EventLog row。
        :raises Exception: 不主动抛出异常。
        """

        payload_descriptor = self._write_raw_payload(
            transaction,
            context=context,
            raw_payload=data.raw_payload,
        )
        payload_ref = payload_descriptor.payload_ref if payload_descriptor is not None else None
        payload_digest = payload_descriptor.payload_digest if payload_descriptor is not None else None
        candidate = context.candidate
        payload: dict[str, JsonValue] = {
            "attempt_id": context.attempt.attempt_id,
            "execution_id": context.attempt.execution_id,
            "iteration_id": data.iteration_id,
            "diagnostic_code": data.diagnostic_code,
            "severity": data.severity.value,
            "message": data.message,
            "provider_request_id": data.provider_request_id,
            "client_correlation_id": data.client_correlation_id,
            "diagnostic_source": data.diagnostic_source.value,
            "payload_ref": payload_ref,
            "payload_digest": payload_digest,
            "partial_tool_call_count": len(data.partial_tool_calls),
        }
        return self._event_log_store.append_event(
            transaction,
            _event_request(
                candidate=candidate,
                event_id=_event_id(
                    candidate,
                    EventClass.DIAGNOSTIC,
                    _EVENT_TYPE_PROVIDER_DIAGNOSTIC,
                    0,
                ),
                event_class=EventClass.DIAGNOSTIC,
                event_type=_EVENT_TYPE_PROVIDER_DIAGNOSTIC,
                payload=payload,
                reason={"reason": data.diagnostic_code},
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
        additional_events: tuple[EventLogRow, ...] = (),
        runner_call_iteration_link_event_id: str | None = None,
        runner_call_manifest_event_id: str | None = None,
        manifest_payload_ref: str | None = None,
        manifest_digest: str | None = None,
    ) -> EngineIngestResult:
        """追加 rejected diagnostic。

        :param transaction: 当前 Host transaction。
        :param candidate: 被拒绝的 candidate。
        :param reason: 拒绝原因。
        :param stop_worker_stream: 是否要求 worker stream fail-closed 停止。
        :param additional_events: 同一事务中已追加且需要随 result 返回的事件。
        :param runner_call_iteration_link_event_id: 可选 runner-call link event id。
        :param runner_call_manifest_event_id: 可选 runner-call manifest event id。
        :param manifest_payload_ref: 可选 runner-call manifest payload ref。
        :param manifest_digest: 可选 runner-call manifest digest。
        :returns: rejected ingest 结果。
        """

        payload: dict[str, JsonValue] = {
            "attempt_id": candidate.envelope.attempt_id,
            "execution_id": candidate.envelope.execution_id,
            "dispatch_record_id": candidate.envelope.dispatch_record_id,
            "worker_event_index": candidate.worker_event_index,
            "engine_event_type": candidate.engine_event.type.value,
            "reason": reason,
            "stop_worker_stream": stop_worker_stream,
        }
        if runner_call_iteration_link_event_id is not None:
            payload["runner_call_iteration_link_event_id"] = runner_call_iteration_link_event_id
        if runner_call_manifest_event_id is not None:
            payload["runner_call_manifest_event_id"] = runner_call_manifest_event_id
        if manifest_payload_ref is not None:
            payload["manifest_payload_ref"] = manifest_payload_ref
        if manifest_digest is not None:
            payload["manifest_digest"] = manifest_digest
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
                payload=payload,
                reason={"reason": reason},
            ),
        ).row
        return EngineIngestResult(
            status=EngineIngestStatus.REJECTED,
            events=additional_events + (row,),
            terminal_closeout=False,
            terminal_notice=None,
            reason=reason,
            transient_delta=None,
            stop_worker_stream=stop_worker_stream,
        )

    def _append_stale_host_lifecycle_diagnostic(
        self,
        transaction: HostTransaction,
        *,
        candidate: _HostLifecycleCloseoutCandidate,
        reason: str,
    ) -> EngineIngestResult:
        """为 durable identity 不匹配的 Host lifecycle signal 追加诊断。

        :param transaction: 当前 Host transaction。
        :param candidate: Host lifecycle closeout candidate。
        :param reason: 拒绝原因。
        :returns: rejected 或 duplicate lifecycle 诊断结果。
        :raises HostDurableError: EventLog 读写失败时抛出。
        """

        payload: dict[str, JsonValue] = {
            "attempt_id": candidate.envelope.attempt_id,
            "execution_id": candidate.envelope.execution_id,
            "dispatch_record_id": candidate.envelope.dispatch_record_id,
            "worker_event_index": candidate.worker_event_index,
            "lifecycle_source": candidate.lifecycle_source.value,
            "lifecycle_reason": candidate.plan.terminal.reason,
            "host_lifecycle_ref": _host_lifecycle_ref(candidate),
            "reason": reason,
        }
        return self._append_host_lifecycle_diagnostic_candidate(
            transaction,
            candidate=candidate,
            reason=reason,
            payload=payload,
        )

    def _append_host_lifecycle_diagnostic(
        self,
        transaction: HostTransaction,
        *,
        context: _ValidatedHostLifecycleCloseoutCandidate,
        reason: str,
    ) -> EngineIngestResult:
        """为已校验但不允许 closeout 的 Host lifecycle signal 追加诊断。

        :param transaction: 当前 Host transaction。
        :param context: 已校验的 Host lifecycle candidate 上下文。
        :param reason: 拒绝原因。
        :returns: rejected 或 duplicate lifecycle 诊断结果。
        :raises HostDurableError: EventLog 读写失败时抛出。
        """

        candidate = context.candidate
        payload: dict[str, JsonValue] = {
            "attempt_id": context.attempt.attempt_id,
            "execution_id": context.attempt.execution_id,
            "dispatch_record_id": context.dispatch_record.dispatch_record_id,
            "worker_event_index": candidate.worker_event_index,
            "lifecycle_source": candidate.lifecycle_source.value,
            "lifecycle_reason": candidate.plan.terminal.reason,
            "host_lifecycle_ref": _host_lifecycle_ref(candidate),
            "run_status": context.run.status.value,
            "attempt_status": context.attempt.status.value,
            "reason": reason,
        }
        return self._append_host_lifecycle_diagnostic_candidate(
            transaction,
            candidate=candidate,
            reason=reason,
            payload=payload,
        )

    def _append_host_lifecycle_diagnostic_candidate(
        self,
        transaction: HostTransaction,
        *,
        candidate: _HostLifecycleCloseoutCandidate,
        reason: str,
        payload: Mapping[str, JsonValue],
    ) -> EngineIngestResult:
        """按 Host lifecycle identity 幂等追加诊断事件。

        :param transaction: 当前 Host transaction。
        :param candidate: Host lifecycle closeout candidate。
        :param reason: 诊断原因。
        :param payload: Host lifecycle 诊断 payload。
        :returns: rejected 或 duplicate lifecycle 诊断结果。
        :raises HostDurableError: EventLog 读写失败时抛出。
        """

        event_id = _host_lifecycle_event_id(
            candidate,
            EventClass.DIAGNOSTIC,
            _EVENT_TYPE_HOST_LIFECYCLE_DIAGNOSTIC,
            0,
        )
        existing = _existing_rows(self._event_log_store, transaction, (event_id,))
        if len(existing) == 1:
            return EngineIngestResult(
                status=EngineIngestStatus.DUPLICATE,
                events=existing,
                terminal_closeout=False,
                terminal_notice=None,
                reason=reason,
                transient_delta=None,
            )
        row = self._event_log_store.append_event(
            transaction,
            _host_lifecycle_event_request(
                candidate=candidate,
                event_id=event_id,
                event_class=EventClass.DIAGNOSTIC,
                event_type=_EVENT_TYPE_HOST_LIFECYCLE_DIAGNOSTIC,
                payload=payload,
                reason={"reason": reason},
            ),
        ).row
        return EngineIngestResult(
            status=EngineIngestStatus.REJECTED,
            events=(row,),
            terminal_closeout=False,
            terminal_notice=None,
            reason=reason,
            transient_delta=None,
        )

    def _write_terminal_payload(
        self,
        transaction: HostTransaction,
        *,
        candidate: EngineEventCandidate,
        event_id: str,
        payload: Mapping[str, JsonValue],
    ) -> PayloadDescriptor:
        """写入 terminal payload descriptor。

        :param transaction: 当前 Host transaction。
        :param candidate: 触发 terminal 的 candidate。
        :param event_id: terminal attempt event id。
        :param payload: terminal payload JSON。
        :returns: payload descriptor。
        """

        payload_json: dict[str, JsonValue] = dict(payload)
        payload_json.update(
            {
                "attempt_id": candidate.envelope.attempt_id,
                "execution_id": candidate.envelope.execution_id,
                "worker_event_index": candidate.worker_event_index,
            }
        )
        return self._payload_store.write_sqlite_payload(
            transaction,
            SQLitePayloadWriteRequest(
                payload_ref=f"{_PAYLOAD_REF_PREFIX}-{event_id}",
                payload_id=f"{_PAYLOAD_ID_PREFIX}-{event_id}",
                payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                payload_json=payload_json,
                payload_bytes=None,
                media_type="application/json",
                metadata={
                    "kind": "engine_terminal_payload",
                    "engine_event_type": candidate.engine_event.type.value,
                },
                expected_digest=None,
            ),
        )

    def _write_host_lifecycle_terminal_payload(
        self,
        transaction: HostTransaction,
        *,
        candidate: _HostLifecycleCloseoutCandidate,
        event_id: str,
    ) -> PayloadDescriptor:
        """写入 Host lifecycle terminal payload descriptor。

        :param transaction: 当前 Host transaction。
        :param candidate: Host lifecycle closeout candidate。
        :param event_id: Host lifecycle Attempt terminal event id。
        :returns: payload descriptor。
        :raises HostDurableError: durable payload 写入失败时抛出。
        """

        payload_json: dict[str, JsonValue] = dict(
            candidate.plan.terminal.terminal_payload
        )
        payload_json.update(
            {
                "attempt_id": candidate.envelope.attempt_id,
                "execution_id": candidate.envelope.execution_id,
                "worker_event_index": candidate.worker_event_index,
                "lifecycle_source": candidate.lifecycle_source.value,
                "host_lifecycle_ref": _host_lifecycle_ref(candidate),
            }
        )
        return self._payload_store.write_sqlite_payload(
            transaction,
            SQLitePayloadWriteRequest(
                payload_ref=(
                    f"{_HOST_LIFECYCLE_PAYLOAD_REF_PREFIX}-{event_id}"
                ),
                payload_id=f"{_HOST_LIFECYCLE_PAYLOAD_ID_PREFIX}-{event_id}",
                payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                payload_json=payload_json,
                payload_bytes=None,
                media_type="application/json",
                metadata={
                    "kind": "host_lifecycle_terminal_payload",
                    "lifecycle_source": candidate.lifecycle_source.value,
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
    if envelope.session_id != candidate.engine_event.session_id or envelope.run_id != candidate.engine_event.run_id:
        raise ValueError("EngineEvent session_id/run_id must match envelope")
    if candidate.engine_event.occurred_at.tzinfo is None:
        raise ValueError("EngineEvent.occurred_at must be timezone-aware")


def _validate_host_lifecycle_candidate_shape(
    candidate: _HostLifecycleCloseoutCandidate,
) -> None:
    """校验 Host lifecycle candidate 的必填事实。

    :param candidate: 待校验的 Host lifecycle closeout candidate。
    :returns: ``None``。
    :raises ValueError: event index、时间或 identity 字段非法时抛出。
    """

    if candidate.worker_event_index <= 0:
        raise ValueError("worker_event_index must be positive")
    _validate_observed_at(candidate.observed_at)
    envelope = candidate.envelope
    required_identity = (
        envelope.session_id,
        envelope.run_id,
        envelope.attempt_id,
        envelope.execution_id,
        envelope.dispatch_record_id,
    )
    if any(value.strip() == "" for value in required_identity):
        raise ValueError("Host lifecycle envelope identity must be non-empty")


def _engine_ingest_log_level(engine_event_type: EngineEventType) -> int:
    """根据 Engine event 类型选择 ingest 诊断日志级别。

    :param engine_event_type: 待记录的 Engine event 类型。
    :returns: Python logging 可消费的整数级别；delta 事件使用 Dayu
        自定义 STREAM_DEBUG 级别。
    """

    if engine_event_type in _DELTA_ENGINE_EVENT_TYPES:
        return STREAM_DEBUG_LOG_LEVEL
    return VERBOSE_LOG_LEVEL


def _validate_observed_at(observed_at: datetime) -> None:
    """校验 observed_at 为 UTC aware 时间。

    :param observed_at: 待校验时间。
    :returns: ``None``。
    :raises ValueError: 时间不是 UTC aware 时抛出。
    """

    if observed_at.tzinfo is None or observed_at.utcoffset() != UTC.utcoffset(None):
        raise ValueError("observed_at must be timezone.utc aware")


def _late_engine_event_rejection_reason(
    context: _ValidatedCandidate,
) -> str | None:
    """判断 Engine-origin candidate 是否为迟到事件。

    :param context: 已校验上下文。
    :returns: 拒绝原因；可接受时为 ``None``。
    :raises: 无主动抛出。
    """

    if (
        context.candidate.engine_event.type
        in (EngineEventType.RUN_SUSPENDED, EngineEventType.TOOL_AWAITING)
        and context.run.status is RunStatus.WAITING
        and context.attempt.status is AttemptStatus.SUSPENDED
    ):
        return None
    if is_terminal_run_status(context.run.status) or is_terminal_attempt_status(
        context.attempt.status
    ):
        return _REASON_TERMINAL_ALREADY_CLOSED
    if context.run.status is RunStatus.CANCELLING and context.candidate.engine_event.type in (
        EngineEventType.FINAL_ANSWER,
        EngineEventType.RUN_FAILED,
    ):
        return _REASON_LATE_TERMINAL_AFTER_ACTIVE_CANCEL
    return None


def _late_host_lifecycle_rejection_reason(
    context: _ValidatedHostLifecycleCloseoutCandidate,
) -> str | None:
    """判断 Host lifecycle candidate 是否已迟到或被 active cancel 抢先。

    :param context: 已校验的 Host lifecycle candidate 上下文。
    :returns: 拒绝原因；允许 closeout 时返回 ``None``。
    :raises: 无主动抛出。
    """

    if is_terminal_run_status(context.run.status) or is_terminal_attempt_status(
        context.attempt.status
    ):
        return _REASON_TERMINAL_ALREADY_CLOSED
    if context.run.status is RunStatus.CANCELLING:
        return _REASON_HOST_LIFECYCLE_AFTER_ACTIVE_CANCEL
    return None


def _terminal_closeout_precondition_failed_result() -> EngineIngestResult:
    """构造 terminal transaction 回滚后的稳定 rejected 结果。

    :returns: 不携带未提交事件、且不触发 promotion 的 rejected 结果。
    :raises: 无主动抛出。
    """

    return EngineIngestResult(
        status=EngineIngestStatus.REJECTED,
        events=(),
        terminal_closeout=True,
        terminal_notice=None,
        reason=_REASON_TERMINAL_CLOSEOUT_PRECONDITION_FAILED,
        transient_delta=None,
    )


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

    if context.run.status is not RunStatus.WAITING or context.attempt.status is not AttemptStatus.SUSPENDED:
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
    if tool_awaiting is None or run_waiting is None or attempt_suspended is None:
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
    return value.get("event_id") == row.event_id and value.get("event_sequence") == row.event_sequence


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
    if record.call.tool_call_id != wait_record.tool_call_id or record.call.name != wait_record.tool_name:
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


def _host_lifecycle_event_id(
    candidate: _HostLifecycleCloseoutCandidate,
    event_class: EventClass,
    event_type: str,
    sub_index: int,
) -> str:
    """按 Host lifecycle identity material 派生稳定 event id。

    :param candidate: Host lifecycle closeout candidate。
    :param event_class: Host EventLog class。
    :param event_type: Host lifecycle event type。
    :param sub_index: 单个 lifecycle signal 映射多事件时的下标。
    :returns: ``event-host-lifecycle-`` 命名空间下的稳定 event id。
    :raises ValueError: identity material 含非法 JSON 数值时抛出。
    :raises TypeError: identity material 含不可序列化值时抛出。
    """

    envelope = candidate.envelope
    digest = sha256_digest_json(
        {
            "identity_kind": "host-lifecycle-terminal",
            "session_id": envelope.session_id,
            "run_id": envelope.run_id,
            "attempt_id": envelope.attempt_id,
            "execution_id": envelope.execution_id,
            "worker_event_index": candidate.worker_event_index,
            "event_class": event_class.value,
            "event_type": event_type,
            "sub_index": sub_index,
            "lifecycle_source": candidate.lifecycle_source.value,
            "reason": candidate.plan.terminal.reason,
        }
    ).removeprefix("sha256:")
    return f"{_HOST_LIFECYCLE_EVENT_ID_PREFIX}{digest}"


def _host_lifecycle_terminal_event_ids(
    candidate: _HostLifecycleCloseoutCandidate,
) -> tuple[str, str]:
    """计算 Host lifecycle Attempt / Run terminal event ids。

    :param candidate: Host lifecycle closeout candidate。
    :returns: Attempt 与 Run terminal event id 二元组。
    :raises ValueError: identity material 含非法 JSON 数值时抛出。
    :raises TypeError: identity material 含不可序列化值时抛出。
    """

    return (
        _host_lifecycle_event_id(
            candidate,
            EventClass.CANONICAL_FACT,
            candidate.plan.terminal.attempt_event_type,
            0,
        ),
        _host_lifecycle_event_id(
            candidate,
            EventClass.CANONICAL_FACT,
            candidate.plan.terminal.run_event_type,
            1,
        ),
    )


def _host_lifecycle_ref(candidate: _HostLifecycleCloseoutCandidate) -> str:
    """构造 Host lifecycle 治理来源标签。

    该标签只表达 worker lifecycle 来源，不是 Engine event ref、业务事实或
    EventLog identity。

    :param candidate: Host lifecycle closeout candidate。
    :returns: Host lifecycle 来源标签。
    :raises: 无主动抛出。
    """

    return (
        f"host-lifecycle:{candidate.envelope.execution_id}:"
        f"{candidate.worker_event_index}:{candidate.lifecycle_source.value}:"
        f"{candidate.plan.terminal.reason}"
    )


def _frozen_reactive_material_blocks(
    *,
    context: _ValidatedCandidate,
    display_text: str,
    material_view: PreDispatchCompactMaterialView,
) -> tuple[RunInputMaterialBlock, ...]:
    """冻结 reactive overflow 对应 ordinary input material list。

    :param context: 已校验 Engine event context。
    :param display_text: 当前输入展示文本。
    :param material_view: 与 reactive compact request 同源的 pre-dispatch
        compact material view。
    :returns: 冻结 material blocks。
    """

    return (
        *material_view.material_blocks,
        _current_input_anchor_material_block(
            run=context.run,
            display_text=display_text,
            event_sequence=material_view.source_boundary.current_input_event_sequence,
        ),
    )


def _current_input_anchor_material_block(
    *,
    run: RunRow,
    display_text: str,
    event_sequence: int,
) -> RunInputMaterialBlock:
    """构造 current input anchor material block。

    :param run: 当前 Run row。
    :param display_text: 当前输入展示文本。
    :param event_sequence: 当前输入 EventLog sequence。
    :returns: current input anchor material block。
    """

    return run_input_material_block(
        block_id=f"current:{run.input_event_id}",
        section=CompactMaterialSection.CURRENT_INPUT_ANCHOR,
        kind=CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
        text=display_text,
        canonical_source_refs=(run.input_event_id,),
        event_sequence=event_sequence,
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


def _host_lifecycle_event_request(
    *,
    candidate: _HostLifecycleCloseoutCandidate,
    event_id: str,
    event_class: EventClass,
    event_type: str,
    payload: Mapping[str, JsonValue],
    reason: JsonValue,
) -> EventLogAppendRequest:
    """构造 Host lifecycle EventLog append request。

    :param candidate: Host lifecycle closeout candidate。
    :param event_id: Host lifecycle event id。
    :param event_class: Host EventLog class。
    :param event_type: Host lifecycle event type。
    :param payload: inline payload JSON。
    :param reason: reason JSON。
    :returns: EventLog append request。
    :raises: 无主动抛出。
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
        actor=_HOST_LIFECYCLE_EVENT_ACTOR,
        source=_HOST_LIFECYCLE_EVENT_SOURCE,
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


def _usage_context_pressure_signal(
    *,
    data: UsageReportedData,
    diagnostic: UsageObservationDiagnostic,
    estimate: BudgetEstimate | None,
) -> Mapping[str, JsonValue]:
    """构造 usage projection 的 context pressure signal。

    本函数只序列化 Host budget owner 已产出的 ``BudgetEstimate`` 与
    ``decide_context_budget`` 结果，不重新实现阈值计算。

    :param data: Engine usage reported data。
    :param diagnostic: usage observation diagnostic。
    :param estimate: Host context budget estimate；不可用时为 ``None``。
    :returns: 可写入 projection signal payload 的 JSON object。
    """

    budget_decision = (
        decide_context_budget(estimate).value
        if estimate is not None
        else _CONTEXT_PRESSURE_BUDGET_DECISION_UNKNOWN
    )
    overage_reason = (
        estimate.overage_reason.value
        if estimate is not None and estimate.overage_reason is not None
        else None
    )
    return {
        "schema_version": _CONTEXT_PRESSURE_SCHEMA_VERSION,
        "signal_source": _CONTEXT_PRESSURE_SOURCE_USAGE_REPORTED,
        "status": diagnostic.status,
        "policy_ref": diagnostic.policy_ref,
        "estimator_digest": diagnostic.estimator_digest,
        "estimated_input_tokens": diagnostic.estimated_input_tokens,
        "input_budget_tokens": (
            estimate.input_budget_tokens if estimate is not None else None
        ),
        "soft_threshold_tokens": (
            estimate.soft_threshold_tokens if estimate is not None else None
        ),
        "hard_threshold_tokens": (
            estimate.hard_threshold_tokens if estimate is not None else None
        ),
        "soft_threshold_exceeded": (
            estimate.estimated_input_tokens >= estimate.soft_threshold_tokens
            if estimate is not None
            else None
        ),
        "hard_threshold_exceeded": (
            estimate.estimated_input_tokens >= estimate.hard_threshold_tokens
            if estimate is not None
            else None
        ),
        "budget_decision": budget_decision,
        "overage_reason": overage_reason,
        "prompt_tokens": data.prompt_tokens,
        "completion_tokens": data.completion_tokens,
        "total_tokens": data.total_tokens,
        "prompt_token_delta": diagnostic.prompt_token_delta,
    }


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
            "provider_request_id": data.provider_request_id,
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


def _closeout_attempt_event_type(status: AttemptStatus) -> str:
    """把 closeout-supported Attempt terminal status 投影为 EventLog type。

    :param status: Attempt terminal status。
    :returns: 对应 EventLog event_type 文本。
    :raises ValueError: 状态不属于 Run / Attempt 联合 closeout 支持子集时抛出。
    """

    return closeout_attempt_terminal_event_type_for_status(status).value


def _run_terminal_event_type(status: RunStatus) -> str:
    """把 Run terminal status 投影为 EventLog type。

    :param status: Run terminal status。
    :returns: 对应 EventLog event_type 文本。
    :raises ValueError: 状态不是 Run terminal status 时抛出。
    """

    return run_terminal_event_type_for_status(status).value


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
                _closeout_attempt_event_type(AttemptStatus.SUCCEEDED),
                0,
            ),
            _event_id(
                candidate,
                EventClass.CANONICAL_FACT,
                _run_terminal_event_type(RunStatus.SUCCEEDED),
                1,
            ),
        )
    if event.type == EngineEventType.RUN_FAILED and isinstance(
        event.data, RunFailedData
    ):
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
                    _closeout_attempt_event_type(AttemptStatus.FAILED),
                    1,
                ),
                _event_id(
                    candidate,
                    EventClass.CANONICAL_FACT,
                    _run_terminal_event_type(RunStatus.FAILED),
                    2,
                ),
            )
        return (
            _event_id(
                candidate,
                EventClass.CANONICAL_FACT,
                _closeout_attempt_event_type(AttemptStatus.FAILED),
                0,
            ),
            _event_id(
                candidate,
                EventClass.CANONICAL_FACT,
                _run_terminal_event_type(RunStatus.FAILED),
                1,
            ),
        )
    if event.type == EngineEventType.RUN_CANCELLED:
        return (
            _event_id(
                candidate,
                EventClass.CANONICAL_FACT,
                _closeout_attempt_event_type(AttemptStatus.CANCELLED),
                0,
            ),
            _event_id(
                candidate,
                EventClass.CANONICAL_FACT,
                _run_terminal_event_type(RunStatus.CANCELLED),
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
                _closeout_attempt_event_type(AttemptStatus.FAILED),
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

    return (
        f"engine:{candidate.envelope.execution_id}:{candidate.worker_event_index}:{candidate.engine_event.type.value}"
    )


def _reactive_precondition_compaction_operation_id(
    *, context: _ValidatedCandidate, failure_reason: str
) -> str:
    """构造未写 request fact 的 reactive precondition failure operation id。

    :param context: 已校验 candidate 上下文。
    :param failure_reason: precondition failure reason。
    :returns: 可写入 failed payload 的稳定 operation id。
    """

    return f"{_REACTIVE_PRECONDITION_OPERATION_PREFIX}:{failure_reason}:{_engine_event_ref(context.candidate)}"


def _host_event_type(event_type: EngineEventType) -> str:
    """把 EngineEventType 映射为 Host event type 文本。

    :param event_type: Engine event type。
    :returns: 大写 Host event type。
    """

    return event_type.value.upper()


def _final_answer_plan(data: FinalAnswerData) -> _EngineTerminalPlan:
    """构造 final_answer terminal plan。

    :param data: final_answer data。
    :returns: terminal plan。
    :raises: 无主动抛出。
    """

    return _EngineTerminalPlan(
        terminal=_TerminalFactPlan(
            attempt_event_type=_closeout_attempt_event_type(
                AttemptStatus.SUCCEEDED
            ),
            run_event_type=_run_terminal_event_type(RunStatus.SUCCEEDED),
            attempt_status=AttemptStatus.SUCCEEDED,
            run_status=RunStatus.SUCCEEDED,
            reason=_REASON_FINAL_ANSWER,
            terminal_payload={
                "content": data.content,
                "finish_reason": data.finish_reason.value,
                "filtered": data.filtered,
                "degraded": data.degraded,
            },
        ),
        finish_reason=data.finish_reason.value,
        filtered=data.filtered,
        degraded=data.degraded,
        error_code=None,
        message=None,
        provider_request_id=None,
        client_correlation_id=None,
        recoverable=None,
        unsupported_later_owner=None,
    )


def _run_failed_plan(data: RunFailedData) -> _EngineTerminalPlan:
    """构造 run_failed terminal plan。

    :param data: run_failed data。
    :returns: terminal plan。
    :raises: 无主动抛出。
    """

    error_code = serialize_engine_error_code(data.error_code)
    unsupported_owner = _OWNER_PHASE10 if data.recoverable else None
    reason = _REASON_UNSUPPORTED_RECOVERY_POLICY if data.recoverable else error_code
    terminal = _failed_terminal_fact_plan(
        reason=reason,
        error_code=error_code,
        message=data.message,
        provider_request_id=data.provider_request_id,
        client_correlation_id=data.client_correlation_id,
        recoverable=data.recoverable,
    )
    return _EngineTerminalPlan(
        terminal=terminal,
        finish_reason=None,
        filtered=None,
        degraded=None,
        error_code=error_code,
        message=data.message,
        provider_request_id=data.provider_request_id,
        client_correlation_id=data.client_correlation_id,
        recoverable=data.recoverable,
        unsupported_later_owner=unsupported_owner,
    )


def _unsupported_recovery_plan(
    provider_request_id: str | None,
) -> _EngineTerminalPlan:
    """构造 unsupported recovery terminal plan。

    :param provider_request_id: provider request id；无时为 ``None``。
    :returns: terminal plan。
    :raises: 无主动抛出。
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


def _unsupported_waiting_plan() -> _EngineTerminalPlan:
    """构造 unsupported waiting terminal plan。

    :returns: terminal plan。
    :raises: 无主动抛出。
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
) -> _HostLifecycleTerminalPlan:
    """构造 worker lifecycle failed closeout plan。

    :param reason: closeout reason。
    :param last_observed_worker_event_index: 最后观察到的 worker event index。
    :returns: terminal plan。
    :raises: 无主动抛出。
    """

    terminal = _failed_terminal_fact_plan(
        reason=reason,
        error_code=reason,
        message=reason,
        provider_request_id=None,
        client_correlation_id=None,
        recoverable=False,
    )
    return _HostLifecycleTerminalPlan(
        terminal=terminal,
        error_code=reason,
        message=reason,
        recoverable=False,
        worker_lifecycle_signal=None,
        stream_error_code=None,
        last_observed_worker_event_index=last_observed_worker_event_index,
        last_accepted_event_id=None,
    )


def _lost_lifecycle_plan(
    *,
    worker_lifecycle_signal: str,
    stream_error_code: str | None,
    last_observed_worker_event_index: int,
    last_accepted_event_id: str | None,
) -> _HostLifecycleTerminalPlan:
    """构造 worker lost closeout plan。

    :param worker_lifecycle_signal: worker lifecycle signal。
    :param stream_error_code: stream error code；无时为 ``None``。
    :param last_observed_worker_event_index: 最后观察到的 worker event index。
    :param last_accepted_event_id: 最后已接受 EventLog id；无时为 ``None``。
    :returns: terminal plan。
    :raises: 无主动抛出。
    """

    return _HostLifecycleTerminalPlan(
        terminal=_TerminalFactPlan(
            attempt_event_type=_closeout_attempt_event_type(AttemptStatus.LOST),
            run_event_type=_run_terminal_event_type(RunStatus.LOST),
            attempt_status=AttemptStatus.LOST,
            run_status=RunStatus.LOST,
            reason=_REASON_WORKER_LOST_BEFORE_TERMINAL,
            terminal_payload={
                "reason": _REASON_WORKER_LOST_BEFORE_TERMINAL,
                "worker_lifecycle_signal": worker_lifecycle_signal,
                "stream_error_code": stream_error_code,
            },
        ),
        error_code=None,
        message=None,
        recoverable=None,
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
) -> _EngineTerminalPlan:
    """构造 failed terminal plan。

    :param reason: terminal reason。
    :param error_code: error code。
    :param message: error message。
    :param provider_request_id: provider request id。
    :param client_correlation_id: 本地客户端关联 id。
    :param recoverable: 是否可恢复。
    :param unsupported_later_owner: unsupported later owner。
    :returns: terminal plan。
    :raises: 无主动抛出。
    """

    return _EngineTerminalPlan(
        terminal=_failed_terminal_fact_plan(
            reason=reason,
            error_code=error_code,
            message=message,
            provider_request_id=provider_request_id,
            client_correlation_id=client_correlation_id,
            recoverable=recoverable,
        ),
        finish_reason=None,
        filtered=None,
        degraded=None,
        error_code=error_code,
        message=message,
        provider_request_id=provider_request_id,
        client_correlation_id=client_correlation_id,
        recoverable=recoverable,
        unsupported_later_owner=unsupported_later_owner,
    )


def _failed_terminal_fact_plan(
    *,
    reason: str,
    error_code: str,
    message: str,
    provider_request_id: str | None,
    client_correlation_id: str | None,
    recoverable: bool,
) -> _TerminalFactPlan:
    """构造 Engine failure 与 clean EOF 共用的 FAILED canonical facts。

    :param reason: terminal reason。
    :param error_code: error code。
    :param message: error message。
    :param provider_request_id: provider request id；无时为 ``None``。
    :param client_correlation_id: 客户端关联 id；无时为 ``None``。
    :param recoverable: failure 是否可恢复。
    :returns: 由 lifecycle owner helper 派生 event type 的 terminal fact plan。
    :raises: 无主动抛出。
    """

    return _TerminalFactPlan(
        attempt_event_type=_closeout_attempt_event_type(AttemptStatus.FAILED),
        run_event_type=_run_terminal_event_type(RunStatus.FAILED),
        attempt_status=AttemptStatus.FAILED,
        run_status=RunStatus.FAILED,
        reason=reason,
        terminal_payload={
            "error_code": error_code,
            "message": message,
            "provider_request_id": provider_request_id,
            "client_correlation_id": client_correlation_id,
            "recoverable": recoverable,
        },
    )


def _is_preview_event(event: EngineEvent) -> bool:
    """判断 Engine event 是否属于 Phase 5 preview。

    :param event: Engine event。
    :returns: type 与 data 均匹配 preview 契约时返回 ``True``。
    """

    return (
        (event.type == EngineEventType.ITERATION_STARTED and isinstance(event.data, IterationStartedData))
        or (event.type == EngineEventType.CONTENT_COMPLETED and isinstance(event.data, ContentCompleteData))
        or (event.type == EngineEventType.TOOL_CALLS_BATCH_READY and isinstance(event.data, ToolCallsBatchReadyData))
        or (event.type == EngineEventType.TOOL_CALL_REQUESTED and isinstance(event.data, ToolCallRequestedData))
        or (event.type == EngineEventType.TOOL_RESULT_ACCEPTED and isinstance(event.data, ToolResultAcceptedData))
        or (event.type == EngineEventType.TOOL_CALLS_BATCH_DONE and isinstance(event.data, ToolCallsBatchDoneData))
        or (event.type == EngineEventType.ITERATION_COMPLETED and isinstance(event.data, IterationCompletedData))
    )


def _is_transient_delta_event(event: EngineEvent) -> bool:
    """判断 Engine event 是否属于默认不持久化的即时 delta。

    :param event: Engine event。
    :returns: type 与 data 均匹配 transient delta 契约时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return (
        (event.type == EngineEventType.CONTENT_DELTA and isinstance(event.data, ContentDeltaData))
        or (event.type == EngineEventType.REASONING_DELTA and isinstance(event.data, ReasoningDeltaData))
        or (event.type == EngineEventType.TOOL_CALL_DELTA and isinstance(event.data, ToolCallDeltaData))
    )


def _validated_transient_delta_candidate(
    context: _ValidatedCandidate,
    event: EngineEvent,
) -> ValidatedTransientDeltaCandidate:
    """把已通过 durable 校验的 Engine delta 映射为 Host public payload。

    :param context: 已校验 durable identity 上下文。
    :param event: 与 context candidate 相同的 Engine event。
    :returns: 尚未分配 runtime identity 的已验证瞬态候选。
    :raises ValueError: event 不是闭合的三类 typed delta 时抛出。
    """

    data = event.data
    if event.type == EngineEventType.CONTENT_DELTA and isinstance(data, ContentDeltaData):
        transient_type = HostTransientDeltaType.CONTENT_DELTA
        public_data = HostContentDelta(
            iteration_id=data.iteration_id,
            text_delta=data.delta,
        )
    elif event.type == EngineEventType.REASONING_DELTA and isinstance(data, ReasoningDeltaData):
        transient_type = HostTransientDeltaType.REASONING_DELTA
        public_data = HostReasoningDelta(
            iteration_id=data.iteration_id,
            text_delta=data.delta,
        )
    elif event.type == EngineEventType.TOOL_CALL_DELTA and isinstance(data, ToolCallDeltaData):
        transient_type = HostTransientDeltaType.TOOL_CALL_DELTA
        public_data = HostToolCallDelta(
            iteration_id=data.iteration_id,
            tool_call_index=data.tool_call_index,
            tool_call_id=data.tool_call_id,
            name_delta=data.name_delta,
            arguments_delta=data.arguments_delta,
        )
    else:
        raise ValueError("event must be a typed transient delta")
    candidate = context.candidate
    return ValidatedTransientDeltaCandidate(
        session_id=candidate.envelope.session_id,
        run_id=candidate.envelope.run_id,
        attempt_id=candidate.envelope.attempt_id,
        execution_id=candidate.envelope.execution_id,
        worker_event_index=candidate.worker_event_index,
        durable_causal_fence_event_sequence=(
            context.attempt.started_event_sequence
        ),
        observed_at=candidate.observed_at,
        type=transient_type,
        data=public_data,
    )


def _publish_transient_delta(
    publisher: HostTransientDeltaPublisher,
    candidate: ValidatedTransientDeltaCandidate,
) -> None:
    """隔离发布端口意外，不让 live delivery 污染 durable accepted 结果。

    :param publisher: 显式注入的 Host 瞬态发布端口。
    :param candidate: transaction 成功返回的已验证候选。
    :returns: ``None``。
    :raises Exception: publisher 异常会被本函数捕获并转为 sanitized diagnostic。
    """

    try:
        publisher.publish(candidate)
    except Exception as exc:
        _LOGGER.error(
            "host.engine_ingest.transient_publish_failed "
            "session_id=%s run_id=%s attempt_id=%s execution_id=%s "
            "worker_event_index=%s delta_type=%s publisher_error_type=%s",
            candidate.session_id,
            candidate.run_id,
            candidate.attempt_id,
            candidate.execution_id,
            candidate.worker_event_index,
            candidate.type.value,
            type(exc).__name__,
        )


def _preview_payload(transaction: HostTransaction, context: _ValidatedCandidate) -> Mapping[str, JsonValue]:
    """构造 preview payload。

    :param transaction: 当前 Host transaction。
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
        raise HostDurableError(
            "iteration started preview requires runner-call link resolution"
        )
    elif isinstance(data, ContentCompleteData):
        common["iteration_id"] = data.iteration_id
        common["has_content"] = data.content is not None
        common["has_reasoning_content"] = data.reasoning_content is not None
    elif isinstance(data, ToolCallsBatchReadyData):
        common["iteration_id"] = data.iteration_id
        common["tool_call_count"] = len(data.tool_calls)
    elif isinstance(data, ToolCallRequestedData):
        common["iteration_id"] = data.iteration_id
        common["tool_call_id"] = data.tool_call_id
        common["tool_name"] = data.name
        common["index_in_iteration"] = data.index_in_iteration
        common["argument_key_count"] = len(data.arguments)
        common["normalized_arguments_digest"] = sha256_digest_json(
            {"arguments": data.arguments}
        )
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


def _has_complete_observed_input_projection(data: IterationStartedData) -> bool:
    """判断 Engine iteration signal 是否携带完整 observed input projection。

    :param data: Engine iteration started data。
    :returns: projection 非空且数量与 Engine observed message count 一致时返回
        ``True``。
    """

    return len(data.input_projection) > 0 and len(data.input_projection) == data.message_count


def _observed_runner_call_projection_body(
    context: _ValidatedCandidate,
    data: IterationStartedData,
    *,
    runner_call_index: int,
    projection_id: str,
    runner_call_kind: str | None,
    runner_call_trigger_reason: str | None,
) -> Mapping[str, JsonValue]:
    """构造 Engine observed runner-call input projection body。

    :param context: 已校验 candidate 上下文。
    :param data: Engine iteration started data。
    :param runner_call_index: Host-owned runner call index。
    :param projection_id: projection logical id。
    :param runner_call_kind: Host 已判定的 runner call kind。
    :param runner_call_trigger_reason: Host 已判定的 trigger reason。
    :returns: projection canonical JSON object。
    """

    return {
        "schema_version": RUNNER_CALL_INPUT_PROJECTION_SCHEMA_VERSION,
        "projection_id": projection_id,
        "session_id": context.run.session_id,
        "host_run_id": context.run.run_id,
        "attempt_id": context.attempt.attempt_id,
        "execution_id": context.attempt.execution_id,
        "runner_call_index": runner_call_index,
        "runner_call_kind": (
            runner_call_kind
            if runner_call_kind is not None
            else _runner_call_kind_for_iteration(data)
        ),
        "runner_call_trigger_reason": (
            runner_call_trigger_reason
            if runner_call_trigger_reason is not None
            else _runner_call_trigger_for_iteration(data)
        ),
        "iteration_id": data.iteration_id,
        "iteration_index": data.iteration_index,
        "runner_input_serializer_schema_version": (
            data.runner_input_serializer_schema_version
        ),
        "message_count": data.message_count,
        "role_sequence_digest": data.role_sequence_digest,
        "messages": [
            _observed_projection_message(context, message)
            for message in data.input_projection
        ],
    }


def _observed_projection_message(
    context: _ValidatedCandidate,
    message: RunnerInputMessageProjection,
) -> Mapping[str, JsonValue]:
    """构造 Engine observed projection 的单条 message。

    :param context: 已校验 candidate 上下文。
    :param message: Engine observed message projection。
    :returns: message projection JSON object。
    """

    base: dict[str, JsonValue] = {
        "index": message.index,
        "role": message.role,
        "content": message.content,
        "content_digest": _observed_message_content_digest(message),
        "content_size_bytes": _observed_message_content_size_bytes(message),
        "source_refs": list(_limited_runner_call_source_refs(context)),
        "projector_metadata_id": f"projector:{message.index}:{message.role}",
    }
    if message.tool_call_id is not None:
        base["tool_call_id"] = message.tool_call_id
    if len(message.tool_calls) > 0:
        base["tool_calls"] = [
            {
                "tool_call_id": tool_call.tool_call_id,
                "name": tool_call.name,
                "arguments": dict(tool_call.arguments),
            }
            for tool_call in message.tool_calls
        ]
    return base


def _observed_message_content_digest(
    message: RunnerInputMessageProjection,
) -> str:
    """计算 Engine observed message content digest。

    :param message: Engine observed message projection。
    :returns: ``sha256:`` digest。
    """

    if len(message.tool_calls) > 0:
        return sha256_digest_json(
            {
                "serializer_schema_version": (
                    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
                ),
                "role": message.role,
                "content": message.content,
                "reasoning_content_digest": None,
                "tool_calls_digest": sha256_digest_json(
                    {
                        "tool_calls": [
                            {
                                "id": tool_call.tool_call_id,
                                "name": tool_call.name,
                                "arguments": dict(tool_call.arguments),
                            }
                            for tool_call in message.tool_calls
                        ]
                    }
                ),
            }
        )
    return sha256_digest_json(
        {
            "serializer_schema_version": RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION,
            "role": message.role,
            "content": _observed_message_content_text(message),
        }
    )


def _observed_message_content_size_bytes(
    message: RunnerInputMessageProjection,
) -> int:
    """计算 Engine observed message content 字节数。

    :param message: Engine observed message projection。
    :returns: UTF-8 字节数；content 为 ``None`` 时按空文本计算。
    """

    return len(_observed_message_content_text(message).encode("utf-8"))


def _observed_message_content_text(
    message: RunnerInputMessageProjection,
) -> str:
    """读取 Engine observed message 文本。

    :param message: Engine observed message projection。
    :returns: content 文本；``None`` 时返回空串。
    """

    if message.content is None:
        return ""
    return message.content


def _limited_runner_call_manifest_body(
    context: _ValidatedCandidate,
    data: IterationStartedData,
    *,
    runner_call_index: int,
    manifest_id: str,
    runner_call_kind: str | None,
    runner_call_trigger_reason: str | None,
    projection_descriptor: PayloadDescriptor | None,
) -> Mapping[str, JsonValue]:
    """构造 Engine continuation 的 limited-signal manifest body。

    :param context: 已校验 candidate 上下文。
    :param data: Engine iteration started data。
    :param runner_call_index: Host-owned runner call index。
    :param manifest_id: manifest logical id。
    :param runner_call_kind: Host 已判定的 runner call kind；为 ``None`` 时
        按 Engine iteration signal 推导。
    :param runner_call_trigger_reason: Host 已判定的 trigger reason；为
        ``None`` 时按 Engine iteration signal 推导。
    :returns: limited-signal manifest body。
    """

    diagnostic = (
        None
        if projection_descriptor is not None
        else _runner_call_manifest_diagnostic(
            status=_RUNNER_CALL_MANIFEST_STATUS_LIMITED_SIGNAL,
            reason=_RUNNER_CALL_MANIFEST_REASON_MISSING_PROJECTION,
            missing_atom_kind=None,
            missing_ref_kind=(
                _RUNNER_CALL_DIAGNOSTIC_MISSING_REF_KIND_PROJECTION_ARTIFACT
            ),
            missing_ref=None,
            observed_count=data.message_count,
            expected_count=None,
            observed_digest=data.role_sequence_digest,
            expected_digest=None,
            consumer_boundary=_EVENT_SOURCE,
        )
    )
    projector_metadata_id = _limited_runner_call_projector_metadata_id(data)
    message_entries = (
        tuple(
            _observed_runner_call_message_entry(
                context,
                message,
                projection_descriptor=projection_descriptor,
                projector_metadata_id=projector_metadata_id,
            )
            for message in data.input_projection
        )
        if projection_descriptor is not None
        else ()
    )
    input_projection_digest = (
        sha256_digest_json(
            {
                "message_entries": list(message_entries),
                "source_cursor_refs": list(_limited_runner_call_source_refs(context)),
                "projection_artifact_ref": projection_descriptor.payload_ref,
                "projection_artifact_digest": projection_descriptor.payload_digest,
            }
        )
        if projection_descriptor is not None
        else sha256_digest_json(
            {
                "signal_kind": "engine_observed_limited_runner_input",
                "iteration_id": data.iteration_id,
                "iteration_index": data.iteration_index,
                "message_count": data.message_count,
                "role_sequence_digest": data.role_sequence_digest,
                "diagnostic": diagnostic,
            }
        )
    )
    return {
        "schema_version": RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION,
        "manifest_id": manifest_id,
        "session_id": context.run.session_id,
        "host_run_id": context.run.run_id,
        "attempt_id": context.attempt.attempt_id,
        "execution_id": context.attempt.execution_id,
        "runner_call_index": runner_call_index,
        "runner_call_kind": (
            runner_call_kind
            if runner_call_kind is not None
            else _runner_call_kind_for_iteration(data)
        ),
        "runner_call_trigger_reason": (
            runner_call_trigger_reason
            if runner_call_trigger_reason is not None
            else _runner_call_trigger_for_iteration(data)
        ),
        "iteration_id": data.iteration_id,
        "iteration_index": data.iteration_index,
        "message_count": data.message_count,
        "role_sequence_digest": data.role_sequence_digest,
        "runner_input_serializer_schema_version": (
            data.runner_input_serializer_schema_version
        ),
        "input_projection_digest": input_projection_digest,
        "runner_call_projection_artifact_ref": (
            projection_descriptor.payload_ref
            if projection_descriptor is not None
            else None
        ),
        "runner_call_projection_artifact_digest": (
            projection_descriptor.payload_digest
            if projection_descriptor is not None
            else None
        ),
        "runner_call_projection_artifact_size_bytes": (
            projection_descriptor.payload_size_bytes
            if projection_descriptor is not None
            else None
        ),
        "message_entries": list(message_entries),
        "source_cursor_refs": list(_limited_runner_call_source_refs(context)),
        "tool_schema_snapshot_refs": [],
        "memory_snapshot_cursor_ref": None,
        "compact_artifact_refs": [],
        "context_fallback_decision_ref": None,
        "projector_metadata": [
            _limited_runner_call_projector_metadata(context, data)
        ],
        "compactor_identity": None,
        "diagnostic": diagnostic,
    }


def _observed_runner_call_message_entry(
    context: _ValidatedCandidate,
    message: RunnerInputMessageProjection,
    *,
    projection_descriptor: PayloadDescriptor,
    projector_metadata_id: str,
) -> Mapping[str, JsonValue]:
    """构造 Engine observed manifest message entry。

    :param context: 已校验 candidate 上下文。
    :param message: Engine observed message projection。
    :param projection_descriptor: runner-call projection descriptor。
    :param projector_metadata_id: 本次 Engine observed projector metadata id。
    :returns: manifest message entry JSON object。
    """

    return {
        "index": message.index,
        "role": message.role,
        "content_digest": _observed_message_content_digest(message),
        "content_size_bytes": _observed_message_content_size_bytes(message),
        "source_refs": list(_limited_runner_call_source_refs(context)),
        "projection_artifact_ref": projection_descriptor.payload_ref,
        "projection_artifact_digest": projection_descriptor.payload_digest,
        "projector_metadata_id": projector_metadata_id,
        "provider_tool_calls_digest": (
            sha256_digest_json(
                {
                    "tool_calls": [
                        {
                            "id": tool_call.tool_call_id,
                            "name": tool_call.name,
                            "arguments": dict(tool_call.arguments),
                        }
                        for tool_call in message.tool_calls
                    ]
                }
            )
            if len(message.tool_calls) > 0
            else None
        ),
        "reasoning_content_digest": None,
    }


def _runner_call_manifest_diagnostic(
    *,
    status: str,
    reason: str | None,
    missing_atom_kind: str | None,
    missing_ref_kind: str | None,
    missing_ref: str | None,
    observed_count: int | None,
    expected_count: int | None,
    observed_digest: str | None,
    expected_digest: str | None,
    consumer_boundary: str,
) -> Mapping[str, JsonValue]:
    """构造 runner-call reconstruction diagnostic。

    :param status: diagnostic status。
    :param reason: diagnostic reason。
    :param missing_atom_kind: 缺失 atom kind。
    :param missing_ref_kind: 缺失 ref kind。
    :param missing_ref: 缺失 ref。
    :param observed_count: Engine 观察到的 message count。
    :param expected_count: manifest 期望 message count。
    :param observed_digest: Engine 观察到的 role digest。
    :param expected_digest: manifest 期望 role digest。
    :param consumer_boundary: 产生该诊断的 consumer boundary。
    :returns: diagnostic JSON object。
    """

    return {
        "status": status,
        "reason": reason,
        "missing_atom_kind": missing_atom_kind,
        "missing_ref_kind": missing_ref_kind,
        "missing_ref": missing_ref,
        "observed_count": observed_count,
        "expected_count": expected_count,
        "observed_digest": observed_digest,
        "expected_digest": expected_digest,
        "consumer_boundary": consumer_boundary,
    }


def _limited_runner_call_source_refs(
    context: _ValidatedCandidate,
) -> tuple[str, ...]:
    """返回 limited continuation manifest 可证明的 Host source refs。

    :param context: 已校验 candidate 上下文。
    :returns: 去重后的 source refs。
    """

    refs = [
        f"event:{context.run.input_event_id}",
        f"event:{context.run.accepted_event_id}",
        f"event:{context.attempt.started_event_id}",
    ]
    if context.run.started_event_id is not None:
        refs.append(f"event:{context.run.started_event_id}")
    return tuple(dict.fromkeys(refs))


def _limited_runner_call_projector_metadata(
    context: _ValidatedCandidate, data: IterationStartedData
) -> Mapping[str, JsonValue]:
    """构造 limited continuation projector metadata。

    :param context: 已校验 candidate 上下文。
    :param data: Engine iteration started data。
    :returns: projector metadata JSON object。
    """

    projector_id = "engine_observed_runner_input_signal"
    projector_schema_version = "engine_observed_runner_input_signal.v1"
    metadata_id = _limited_runner_call_projector_metadata_id(data)
    source_contract_refs = _limited_runner_call_source_refs(context)
    projector_digest = sha256_digest_json(
        {
            "projector_id": projector_id,
            "projector_schema_version": projector_schema_version,
            "source_refs": list(source_contract_refs),
        }
    )
    return runner_call_projector_metadata_descriptor(
        RunnerCallProjectorMetadata(
            projector_metadata_id=metadata_id,
            projector_id=projector_id,
            projector_schema_version=projector_schema_version,
            projector_digest=projector_digest,
            purpose=_RUNNER_CALL_PROJECTOR_PURPOSE_TOOL_CONTINUATION,
            source_contract_refs=source_contract_refs,
        )
    )


def _limited_runner_call_projector_metadata_id(
    data: IterationStartedData,
) -> str:
    """返回 Engine continuation messages 共用的 metadata id。

    :param data: Engine iteration started data。
    :returns: 可由 manifest ``projector_metadata`` 唯一解析的 id。
    :raises: 无。
    """

    return f"projector:{data.iteration_index}:engine-observed"


def _runner_call_kind_for_iteration(data: IterationStartedData) -> str:
    """返回 Engine iteration 对应的 runner call kind。

    :param data: Engine iteration started data。
    :returns: runner call kind。
    """

    if data.iteration_index > 0:
        return _RUNNER_CALL_KIND_TOOL_RESULT_CONTINUATION
    return _RUNNER_CALL_KIND_INITIAL_USER_DISPATCH


def _runner_call_trigger_for_iteration(data: IterationStartedData) -> str:
    """返回 Engine iteration 对应的 runner call trigger reason。

    :param data: Engine iteration started data。
    :returns: runner call trigger reason。
    """

    if data.iteration_index > 0:
        return _RUNNER_CALL_TRIGGER_TOOL_RESULTS_AVAILABLE
    return _RUNNER_CALL_TRIGGER_INITIAL_USER_INPUT


def _write_runner_call_manifest_payload(
    transaction: HostTransaction,
    payload_store: PayloadStore,
    *,
    event_id: str,
    manifest: Mapping[str, JsonValue],
    manifest_digest: str,
) -> PayloadDescriptor:
    """写入 runner-call manifest payload descriptor。

    :param transaction: 当前 Host transaction。
    :param payload_store: payload store primitive。
    :param event_id: manifest canonical event id。
    :param manifest: manifest body。
    :param manifest_digest: manifest body digest。
    :returns: payload descriptor。
    :raises HostDurableError: descriptor digest 不一致时抛出。
    """

    payload_ref = _runner_call_manifest_payload_ref(event_id)
    existing = payload_store.read_payload_descriptor(transaction, payload_ref)
    if existing is not None:
        if existing.payload_digest != manifest_digest:
            raise HostDurableError("runner-call manifest payload digest mismatch")
        return existing
    return payload_store.write_sqlite_payload(
        transaction,
        SQLitePayloadWriteRequest(
            payload_ref=payload_ref,
            payload_id=_runner_call_manifest_sqlite_payload_id(event_id),
            payload_format=SQLitePayloadFormat.CANONICAL_JSON,
            payload_json=manifest,
            media_type=RUNNER_CALL_INPUT_MANIFEST_MEDIA_TYPE,
            metadata=payload_descriptor_metadata(
                PayloadDescriptorKind.RUNNER_CALL_INPUT_MANIFEST,
                {
                    "event_type": _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
                    "event_id": event_id,
                },
            ),
            expected_digest=manifest_digest,
        ),
    )


def _write_runner_call_projection_payload(
    transaction: HostTransaction,
    payload_store: PayloadStore,
    *,
    event_id: str,
    projection: Mapping[str, JsonValue],
    projection_digest: str,
) -> PayloadDescriptor:
    """写入 Engine observed runner-call input projection payload descriptor。

    :param transaction: 当前 Host transaction。
    :param payload_store: payload store primitive。
    :param event_id: manifest canonical event id。
    :param projection: projection body。
    :param projection_digest: projection body digest。
    :returns: payload descriptor。
    :raises HostDurableError: descriptor digest 不一致时抛出。
    """

    return payload_store.write_bounded_json_payload(
        transaction,
        BoundedJsonPayloadWriteRequest(
            payload_ref=_runner_call_projection_payload_ref(event_id),
            sqlite_payload_id=_runner_call_projection_sqlite_payload_id(event_id),
            payload_json=projection,
            media_type=RUNNER_CALL_INPUT_PROJECTION_MEDIA_TYPE,
            metadata=payload_descriptor_metadata(
                PayloadDescriptorKind.RUNNER_CALL_INPUT_PROJECTION,
                {
                    "schema_version": RUNNER_CALL_INPUT_PROJECTION_SCHEMA_VERSION,
                    "event_type": _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
                    "event_id": event_id,
                },
            ),
            expected_digest=projection_digest,
        ),
    )


def _runner_call_manifest_event_request(
    *,
    context: _ValidatedCandidate,
    event_id: str,
    manifest: Mapping[str, JsonValue],
    manifest_payload_ref: str,
    manifest_digest: str,
) -> EventLogAppendRequest:
    """构造 RUNNER_CALL_INPUT_ASSEMBLED append request。

    :param context: 已校验 candidate 上下文。
    :param event_id: canonical event id。
    :param manifest: manifest body。
    :param manifest_payload_ref: manifest payload descriptor ref。
    :param manifest_digest: manifest body digest。
    :returns: EventLog append request。
    """

    hot_payload = _runner_call_manifest_hot_payload(
        manifest=manifest,
        manifest_payload_ref=manifest_payload_ref,
        manifest_digest=manifest_digest,
    )
    candidate = context.candidate
    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=candidate.envelope.session_id,
        run_id=candidate.envelope.run_id,
        attempt_id=candidate.envelope.attempt_id,
        execution_id=candidate.envelope.execution_id,
        event_type=_EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED,
        occurred_at=candidate.observed_at,
        actor=_EVENT_ACTOR,
        source=_EVENT_SOURCE,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json=hot_payload,
        payload_ref=manifest_payload_ref,
        payload_digest=manifest_digest,
    )


def _runner_call_manifest_hot_payload(
    *,
    manifest: Mapping[str, JsonValue],
    manifest_payload_ref: str,
    manifest_digest: str,
) -> Mapping[str, JsonValue]:
    """构造 RUNNER_CALL_INPUT_ASSEMBLED hot payload。

    :param manifest: manifest body。
    :param manifest_payload_ref: manifest payload descriptor ref。
    :param manifest_digest: manifest body digest。
    :returns: canonical event hot payload。
    """

    validation_status = _manifest_validation_status(manifest)
    return runner_call_hot_payload(
        RunnerCallHotAtoms(
            session_id=_manifest_text(manifest, "session_id"),
            host_run_id=_manifest_text(manifest, "host_run_id"),
            attempt_id=_manifest_optional_text(manifest, "attempt_id"),
            execution_id=_manifest_optional_text(manifest, "execution_id"),
            runner_call_index=_manifest_int(manifest, "runner_call_index"),
            runner_call_kind=_manifest_text(manifest, "runner_call_kind"),
            runner_call_trigger_reason=_manifest_text(
                manifest, "runner_call_trigger_reason"
            ),
            iteration_id=_manifest_optional_text(manifest, "iteration_id"),
            iteration_index=_manifest_optional_int(manifest, "iteration_index"),
            manifest_payload_ref=manifest_payload_ref,
            manifest_digest=manifest_digest,
            manifest_schema_version=_manifest_text(manifest, "schema_version"),
            validation_status=validation_status,
            message_count=_manifest_int(manifest, "message_count"),
            role_sequence_digest=_manifest_text(
                manifest, "role_sequence_digest"
            ),
            input_projection_digest=_manifest_text(
                manifest, "input_projection_digest"
            ),
            runner_call_projection_artifact_ref=_manifest_optional_text(
                manifest, "runner_call_projection_artifact_ref"
            ),
            runner_call_projection_artifact_digest=_manifest_optional_text(
                manifest, "runner_call_projection_artifact_digest"
            ),
            runner_call_projection_artifact_size_bytes=_manifest_optional_int(
                manifest, "runner_call_projection_artifact_size_bytes"
            ),
            diagnostic=_manifest_hot_diagnostic(manifest),
        ),
        manifest=manifest,
    )


def _manifest_hot_diagnostic(
    manifest: Mapping[str, JsonValue]
) -> RunnerCallHotDiagnostic:
    """构造 runner-call manifest hot payload diagnostic。

    :param manifest: manifest body。
    :returns: complete 时返回自描述 diagnostic object；非 complete 时返回
        manifest 内 diagnostic object。
    :raises HostDurableError: manifest diagnostic 或字段类型非法时抛出。
    """

    if _manifest_validation_status(manifest) != _RUNNER_CALL_MANIFEST_STATUS_COMPLETE:
        return runner_call_hot_diagnostic_from_json(_manifest_diagnostic(manifest))
    message_count = _manifest_int(manifest, "message_count")
    role_sequence_digest = _manifest_text(manifest, "role_sequence_digest")
    return complete_runner_call_hot_diagnostic(
        status=_RUNNER_CALL_MANIFEST_STATUS_COMPLETE,
        message_count=message_count,
        role_sequence_digest=role_sequence_digest,
        consumer_boundary=_EVENT_SOURCE,
    )


def _runner_call_manifest_payload_ref(event_id: str) -> str:
    """派生 runner-call manifest payload descriptor ref。

    :param event_id: manifest canonical event id。
    :returns: payload descriptor ref。
    """

    return f"{_RUNNER_CALL_MANIFEST_REF_PREFIX}:{event_id}"


def _runner_call_projection_payload_ref(event_id: str) -> str:
    """派生 runner-call projection payload descriptor ref。

    :param event_id: manifest canonical event id。
    :returns: payload descriptor ref。
    """

    return f"{_RUNNER_CALL_PROJECTION_REF_PREFIX}:{event_id}"


def _runner_call_manifest_sqlite_payload_id(event_id: str) -> str:
    """派生 runner-call manifest SQLite payload id。

    :param event_id: manifest canonical event id。
    :returns: SQLite payload id。
    """

    return f"{_RUNNER_CALL_MANIFEST_SQLITE_PAYLOAD_ID_PREFIX}:{event_id}"


def _runner_call_projection_sqlite_payload_id(event_id: str) -> str:
    """派生 runner-call projection SQLite payload id。

    :param event_id: manifest canonical event id。
    :returns: SQLite payload id。
    """

    return f"{_RUNNER_CALL_PROJECTION_SQLITE_PAYLOAD_ID_PREFIX}:{event_id}"


def _runner_call_manifest_id(event_id: str) -> str:
    """派生 runner-call manifest logical id。

    :param event_id: manifest canonical event id。
    :returns: manifest id。
    """

    return f"{_RUNNER_CALL_MANIFEST_ID_PREFIX}:{event_id}"


def _runner_call_projection_id(event_id: str) -> str:
    """派生 runner-call projection logical id。

    :param event_id: manifest canonical event id。
    :returns: projection id。
    """

    return f"runner-call-projection:{event_id}"


def _next_runner_call_index(transaction: HostTransaction, run_id: str) -> int:
    """返回当前 Run 的下一个 runner_call_index。

    :param transaction: 当前 Host transaction。
    :param run_id: Run id。
    :returns: 下一个零基 runner call index。
    :raises HostDurableError: 计数查询失败时抛出。
    """

    row = transaction.fetchone(
        f"""
        SELECT COUNT(*) AS manifest_count
        FROM {TABLE_EVENT_LOG}
        WHERE run_id = ?
          AND event_type = ?
        """,
        (run_id, _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED),
    )
    if row is None:
        raise HostDurableError("runner-call manifest count query returned no row")
    value = row.get("manifest_count")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError("runner-call manifest count is invalid")
    return value


def _find_runner_call_iteration_link_event(
    transaction: HostTransaction,
    *,
    run_id: str,
    attempt_id: str,
    execution_id: str,
    iteration_id: str,
) -> EventLogRow | None:
    """查找当前 Engine iteration 已有的 runner-call link event。

    :param transaction: 当前 Host transaction。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :param iteration_id: Engine iteration id。
    :returns: link event；不存在时返回 ``None``。
    :raises HostDurableError: EventLog row 缺失或 payload 非法时抛出。
    """

    rows = transaction.fetchall(
        f"""
        SELECT event_id
        FROM {TABLE_EVENT_LOG}
        WHERE run_id = ?
          AND attempt_id = ?
          AND execution_id = ?
          AND event_type = ?
        ORDER BY event_sequence ASC
        """,
        (
            run_id,
            attempt_id,
            execution_id,
            _EVENT_TYPE_RUNNER_CALL_INPUT_ITERATION_LINKED,
        ),
    )
    event_log_store = EventLogStore()
    for row in rows:
        event_id = row.get("event_id")
        if not isinstance(event_id, str):
            raise HostDurableError("runner-call link event id is invalid")
        event = event_log_store.read_event_by_id(transaction, event_id)
        if event is None:
            raise HostDurableError("runner-call link event row is missing")
        payload = _payload_object(event)
        if _optional_payload_text(payload, field_name="iteration_id") == iteration_id:
            return event
    return None


def _find_unlinked_prepared_runner_call_manifest_events(
    transaction: HostTransaction,
    *,
    run_id: str,
    attempt_id: str,
    execution_id: str,
) -> tuple[EventLogRow, ...]:
    """查找当前 attempt/execution 尚未 link 的 ordinary prepared manifest。

    :param transaction: 当前 Host transaction。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :returns: unlinked prepared manifest events。
    :raises HostDurableError: EventLog row 缺失或 payload 非法时抛出。
    """

    linked_manifest_event_ids = _linked_manifest_event_ids(
        transaction,
        run_id=run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
    )
    rows = transaction.fetchall(
        f"""
        SELECT event_id
        FROM {TABLE_EVENT_LOG}
        WHERE run_id = ?
          AND attempt_id = ?
          AND execution_id = ?
          AND event_type = ?
        ORDER BY event_sequence ASC
        """,
        (run_id, attempt_id, execution_id, _EVENT_TYPE_RUNNER_CALL_INPUT_ASSEMBLED),
    )
    event_log_store = EventLogStore()
    candidates: list[EventLogRow] = []
    for row in rows:
        event_id = row.get("event_id")
        if not isinstance(event_id, str):
            raise HostDurableError("runner-call manifest event id is invalid")
        if event_id in linked_manifest_event_ids:
            continue
        event = event_log_store.read_event_by_id(transaction, event_id)
        if event is None:
            raise HostDurableError("runner-call manifest event row is missing")
        if _is_unlinked_prepared_ordinary_manifest(transaction, event):
            candidates.append(event)
    return tuple(candidates)


def _linked_manifest_event_ids(
    transaction: HostTransaction,
    *,
    run_id: str,
    attempt_id: str,
    execution_id: str,
) -> frozenset[str]:
    """读取当前 attempt/execution 已被 link 的 manifest event ids。

    :param transaction: 当前 Host transaction。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :returns: manifest event id 集合。
    :raises HostDurableError: link payload 非法时抛出。
    """

    rows = transaction.fetchall(
        f"""
        SELECT event_id
        FROM {TABLE_EVENT_LOG}
        WHERE run_id = ?
          AND attempt_id = ?
          AND execution_id = ?
          AND event_type = ?
        ORDER BY event_sequence ASC
        """,
        (
            run_id,
            attempt_id,
            execution_id,
            _EVENT_TYPE_RUNNER_CALL_INPUT_ITERATION_LINKED,
        ),
    )
    event_log_store = EventLogStore()
    linked: set[str] = set()
    for row in rows:
        event_id = row.get("event_id")
        if not isinstance(event_id, str):
            raise HostDurableError("runner-call link event id is invalid")
        event = event_log_store.read_event_by_id(transaction, event_id)
        if event is None:
            raise HostDurableError("runner-call link event row is missing")
        payload = _payload_object(event)
        linked.add(_manifest_text(payload, "manifest_event_id"))
    return frozenset(linked)


def _is_unlinked_prepared_ordinary_manifest(
    transaction: HostTransaction,
    event: EventLogRow,
) -> bool:
    """判断 manifest event 是否为 ordinary prepared input。

    :param transaction: 当前 Host transaction。
    :param event: `RUNNER_CALL_INPUT_ASSEMBLED` event。
    :returns: 满足 ordinary prepared 条件时返回 ``True``。
    :raises HostDurableError: payload 字段非法时抛出。
    """

    hot_payload = parse_runner_call_hot_payload(_payload_object(event))
    if hot_payload.validation_status != _RUNNER_CALL_MANIFEST_STATUS_COMPLETE:
        return False
    if hot_payload.iteration_id is not None:
        return False
    if hot_payload.iteration_index is not None:
        return False
    if hot_payload.runner_call_kind not in _ORDINARY_RUNNER_CALL_KINDS:
        return False
    manifest_payload = event_payload_object(
        transaction,
        event,
        payload_label="runner-call manifest",
    )
    manifest = parse_runner_call_manifest(
        manifest_payload,
        hot_payload=hot_payload,
    )
    if manifest.compactor_identity is not None:
        return False
    return True


def _has_prior_iteration_observation(
    transaction: HostTransaction,
    *,
    run_id: str,
    attempt_id: str,
    execution_id: str,
) -> bool:
    """判断当前 attempt/execution 是否已有 accepted iteration observation。

    :param transaction: 当前 Host transaction。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :returns: 存在 accepted link 或 accepted ITERATION_STARTED preview 时返回
        ``True``。
    :raises HostDurableError: SQLite 查询失败时由 transaction runner 转换。
    """

    link_rows = transaction.fetchall(
        f"""
        SELECT event_id
        FROM {TABLE_EVENT_LOG}
        WHERE run_id = ?
          AND attempt_id = ?
          AND execution_id = ?
          AND event_type = ?
        ORDER BY event_sequence ASC
        """,
        (
            run_id,
            attempt_id,
            execution_id,
            _EVENT_TYPE_RUNNER_CALL_INPUT_ITERATION_LINKED,
        ),
    )
    event_log_store = EventLogStore()
    for link_row in link_rows:
        event_id = link_row.get("event_id")
        if not isinstance(event_id, str):
            raise HostDurableError("runner-call link event id is invalid")
        event = event_log_store.read_event_by_id(transaction, event_id)
        if event is None:
            raise HostDurableError("runner-call link event row is missing")
        payload = _payload_object(event)
        if _manifest_text(payload, "validation_status") == (
            _RUNNER_CALL_MANIFEST_STATUS_COMPLETE
        ):
            return True

    preview_row = transaction.fetchone(
        f"""
        SELECT 1 AS found
        FROM {TABLE_EVENT_LOG}
        WHERE run_id = ?
          AND attempt_id = ?
          AND execution_id = ?
          AND event_type = ?
          AND event_class = ?
        LIMIT 1
        """,
        (
            run_id,
            attempt_id,
            execution_id,
            _host_event_type(EngineEventType.ITERATION_STARTED),
            EventClass.PREVIEW.value,
        ),
    )
    return preview_row is not None


def _runner_call_iteration_link_payload(
    manifest_event: EventLogRow,
    data: IterationStartedData,
) -> Mapping[str, JsonValue]:
    """构造 runner-call iteration link hot payload。

    :param manifest_event: 被 link 的 prepared manifest event。
    :param data: Engine iteration started data。
    :returns: link event hot payload。
    :raises HostDurableError: manifest hot payload 字段非法时抛出。
    """

    manifest_payload = parse_runner_call_hot_payload(
        _payload_object(manifest_event)
    )
    expected_count = manifest_payload.message_count
    expected_digest = manifest_payload.role_sequence_digest
    status = _RUNNER_CALL_MANIFEST_STATUS_COMPLETE
    reason: str | None = None
    if expected_count != data.message_count:
        status = _RUNNER_CALL_MANIFEST_STATUS_MISMATCH
        reason = _RUNNER_CALL_MANIFEST_REASON_MESSAGE_COUNT
    elif expected_digest != data.role_sequence_digest:
        status = _RUNNER_CALL_MANIFEST_STATUS_MISMATCH
        reason = _RUNNER_CALL_MANIFEST_REASON_ROLE_DIGEST
    diagnostic: Mapping[str, JsonValue] | None = None
    if status != _RUNNER_CALL_MANIFEST_STATUS_COMPLETE:
        diagnostic = _runner_call_manifest_diagnostic(
            status=status,
            reason=reason,
            missing_atom_kind=None,
            missing_ref_kind=None,
            missing_ref=None,
            observed_count=data.message_count,
            expected_count=expected_count,
            observed_digest=data.role_sequence_digest,
            expected_digest=expected_digest,
            consumer_boundary=_EVENT_SOURCE,
        )
    return {
        "session_id": manifest_payload.session_id,
        "host_run_id": manifest_payload.host_run_id,
        "attempt_id": manifest_payload.attempt_id,
        "execution_id": manifest_payload.execution_id,
        "manifest_event_id": manifest_event.event_id,
        "manifest_payload_ref": manifest_payload.manifest_payload_ref,
        "manifest_digest": manifest_payload.manifest_digest,
        "manifest_schema_version": manifest_payload.manifest_schema_version,
        "runner_call_index": manifest_payload.runner_call_index,
        "runner_call_kind": manifest_payload.runner_call_kind,
        "runner_call_trigger_reason": (
            manifest_payload.runner_call_trigger_reason
        ),
        "iteration_id": data.iteration_id,
        "iteration_index": data.iteration_index,
        "engine_message_count": data.message_count,
        "engine_role_sequence_digest": data.role_sequence_digest,
        "runner_input_serializer_schema_version": (
            data.runner_input_serializer_schema_version
        ),
        "expected_message_count": expected_count,
        "expected_role_sequence_digest": expected_digest,
        "validation_status": status,
        "diagnostic": diagnostic,
    }


def _runner_call_iteration_link_matches(
    event: EventLogRow,
    data: IterationStartedData,
) -> bool:
    """判断既有 link event 是否与当前 Engine observation 一致。

    :param event: 既有 link event。
    :param data: 当前 Engine iteration started data。
    :returns: 完全一致时返回 ``True``。
    :raises HostDurableError: link payload 字段非法时抛出。
    """

    payload = _payload_object(event)
    return (
        _optional_payload_text(payload, field_name="iteration_id")
        == data.iteration_id
        and _optional_payload_int(payload, field_name="iteration_index")
        == data.iteration_index
        and _optional_payload_int(payload, field_name="engine_message_count")
        == data.message_count
        and _optional_payload_text(
            payload, field_name="engine_role_sequence_digest"
        )
        == data.role_sequence_digest
        and _optional_payload_text(
            payload, field_name="runner_input_serializer_schema_version"
        )
        == data.runner_input_serializer_schema_version
    )


def _resolution_from_link_event(
    event: EventLogRow,
    data: IterationStartedData,
) -> _RunnerCallIterationResolution:
    """从 link event 构造 preview validation resolution。

    :param event: link event。
    :param data: Engine iteration started data。
    :returns: preview 使用的 resolution。
    :raises HostDurableError: link payload 字段非法时抛出。
    """

    payload = _payload_object(event)
    return _RunnerCallIterationResolution(
        status=_manifest_text(payload, "validation_status"),
        reason=_manifest_optional_text(_link_diagnostic(payload), "reason"),
        link_event_id=event.event_id,
        manifest_event_id=_manifest_text(payload, "manifest_event_id"),
        manifest_payload_ref=_manifest_text(payload, "manifest_payload_ref"),
        manifest_digest=_manifest_text(payload, "manifest_digest"),
        expected_count=_manifest_optional_int(payload, "expected_message_count"),
        expected_digest=_manifest_optional_text(
            payload, "expected_role_sequence_digest"
        ),
        observed_count=data.message_count,
        observed_digest=data.role_sequence_digest,
        continuation_limited_signal=False,
    )


def _resolution_from_limited_manifest_event(
    event: EventLogRow,
    data: IterationStartedData,
) -> _RunnerCallIterationResolution:
    """从 limited-signal manifest event 构造 preview validation resolution。

    :param event: limited-signal manifest event。
    :param data: Engine iteration started data。
    :returns: preview 使用的 resolution。
    :raises HostDurableError: manifest hot payload 字段非法时抛出。
    """

    hot_payload = parse_runner_call_hot_payload(_payload_object(event))
    diagnostic = _runner_call_diagnostic_projection(
        hot_payload.diagnostic,
        consumer_boundary="engine_ingest_preview",
    )
    status = _manifest_text(diagnostic, "status")
    return _RunnerCallIterationResolution(
        status=status,
        reason=_manifest_optional_text(diagnostic, "reason"),
        link_event_id=None,
        manifest_event_id=event.event_id,
        manifest_payload_ref=hot_payload.manifest_payload_ref,
        manifest_digest=hot_payload.manifest_digest,
        expected_count=_manifest_optional_int(diagnostic, "expected_count"),
        expected_digest=_manifest_optional_text(diagnostic, "expected_digest"),
        observed_count=data.message_count,
        observed_digest=data.role_sequence_digest,
        continuation_limited_signal=(
            status != _RUNNER_CALL_MANIFEST_STATUS_COMPLETE
        ),
    )


def _link_diagnostic(payload: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    """读取 link payload 中的 diagnostic object。

    :param payload: link hot payload。
    :returns: diagnostic object；complete 时返回 reason 为空的 synthetic object。
    :raises HostDurableError: diagnostic 字段非法时抛出。
    """

    if _manifest_text(payload, "validation_status") == (
        _RUNNER_CALL_MANIFEST_STATUS_COMPLETE
    ):
        return {"reason": None}
    value = payload.get("diagnostic")
    if not isinstance(value, Mapping):
        raise HostDurableError("runner-call link diagnostic must be object")
    return value


def _iteration_started_preview_payload(
    context: _ValidatedCandidate,
    data: IterationStartedData,
    resolution: _RunnerCallIterationResolution,
) -> Mapping[str, JsonValue]:
    """构造带 link resolution 的 iteration started preview payload。

    :param context: 已校验 candidate 上下文。
    :param data: Engine iteration started data。
    :param resolution: 当前 iteration 的 runner-call link resolution。
    :returns: preview payload。
    """

    payload: dict[str, JsonValue] = {
        "attempt_id": context.attempt.attempt_id,
        "execution_id": context.attempt.execution_id,
        "worker_event_index": context.candidate.worker_event_index,
        "engine_event_type": EngineEventType.ITERATION_STARTED.value,
        "iteration_id": data.iteration_id,
        "iteration_index": data.iteration_index,
        "message_count": data.message_count,
        "role_sequence_digest": data.role_sequence_digest,
        "runner_input_serializer_schema_version": (
            data.runner_input_serializer_schema_version
        ),
        "runner_call_manifest_validation": _runner_call_link_validation_summary(
            resolution
        ),
    }
    if resolution.link_event_id is not None:
        payload["runner_call_iteration_link_event_id"] = resolution.link_event_id
    if resolution.manifest_event_id is not None:
        payload["runner_call_manifest_event_id"] = resolution.manifest_event_id
    if resolution.manifest_payload_ref is not None:
        payload["manifest_payload_ref"] = resolution.manifest_payload_ref
    if resolution.manifest_digest is not None:
        payload["manifest_digest"] = resolution.manifest_digest
    return payload


def _runner_call_link_validation_summary(
    resolution: _RunnerCallIterationResolution,
) -> Mapping[str, JsonValue]:
    """构造 preview 中的 runner-call manifest validation summary。

    :param resolution: 当前 iteration 的 link resolution。
    :returns: validation summary。
    """

    return {
        "status": resolution.status,
        "reason": resolution.reason,
        "runner_call_iteration_link_event_id": resolution.link_event_id,
        "manifest_event_id": resolution.manifest_event_id,
        "manifest_payload_ref": resolution.manifest_payload_ref,
        "manifest_digest": resolution.manifest_digest,
        "observed_count": resolution.observed_count,
        "expected_count": resolution.expected_count,
        "observed_digest": resolution.observed_digest,
        "expected_digest": resolution.expected_digest,
        "continuation_limited_signal": resolution.continuation_limited_signal,
    }


def _runner_call_payload_diagnostic(
    payload: Mapping[str, JsonValue], *, consumer_boundary: str
) -> Mapping[str, JsonValue]:
    """从 RUNNER_CALL_INPUT_ASSEMBLED hot payload 读取 typed diagnostic。

    :param payload: canonical hot payload。
    :param consumer_boundary: 当前消费边界。
    :returns: diagnostic summary。
    :raises HostDurableError: hot payload 或 diagnostic contract 非法时抛出。
    """

    hot_payload = parse_runner_call_hot_payload(payload)
    return _runner_call_diagnostic_projection(
        hot_payload.diagnostic,
        consumer_boundary=consumer_boundary,
    )


def _runner_call_diagnostic_projection(
    diagnostic: RunnerCallHotDiagnostic,
    *,
    consumer_boundary: str,
) -> Mapping[str, JsonValue]:
    """把 shared owner diagnostic 投影到 Engine ingest consumer boundary。

    :param diagnostic: shared hot owner 已校验的 diagnostic。
    :param consumer_boundary: 当前 Engine ingest 消费边界。
    :returns: 只改写 consumer boundary 的 diagnostic JSON object。
    :raises HostDurableError: consumer boundary 非法时由 projection builder 抛出。
    """

    return _runner_call_manifest_diagnostic(
        status=diagnostic.status,
        reason=diagnostic.reason,
        missing_atom_kind=diagnostic.missing_atom_kind,
        missing_ref_kind=diagnostic.missing_ref_kind,
        missing_ref=diagnostic.missing_ref,
        observed_count=diagnostic.observed_count,
        expected_count=diagnostic.expected_count,
        observed_digest=diagnostic.observed_digest,
        expected_digest=diagnostic.expected_digest,
        consumer_boundary=consumer_boundary,
    )


def _optional_payload_int(
    payload: Mapping[str, JsonValue], *, field_name: str
) -> int | None:
    """读取 payload 中的可选非负整数字段。

    :param payload: payload 映射。
    :param field_name: 字段名。
    :returns: 整数值或 ``None``。
    :raises HostDurableError: 字段存在但不是非负整数时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError(f"payload field {field_name} must be non-negative int")
    return value


def _optional_payload_text(
    payload: Mapping[str, JsonValue], *, field_name: str
) -> str | None:
    """读取 payload 中的可选非空文本字段。

    :param payload: payload 映射。
    :param field_name: 字段名。
    :returns: 文本值或 ``None``。
    :raises HostDurableError: 字段存在但不是非空文本时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, str) and value.strip() != "":
        return value
    raise HostDurableError(f"payload field {field_name} must be non-empty text")


def _manifest_diagnostic(
    manifest: Mapping[str, JsonValue]
) -> Mapping[str, JsonValue]:
    """读取 manifest 中的 diagnostic object。

    :param manifest: manifest body。
    :returns: diagnostic object。
    :raises HostDurableError: diagnostic 缺失或类型非法时抛出。
    """

    value = manifest.get("diagnostic")
    if not isinstance(value, Mapping):
        raise HostDurableError("runner-call manifest diagnostic must be object")
    return value


def _manifest_optional_diagnostic(
    manifest: Mapping[str, JsonValue]
) -> Mapping[str, JsonValue] | None:
    """读取 manifest 中的可选 diagnostic object。

    :param manifest: manifest body。
    :returns: diagnostic object；complete manifest 无 diagnostic 时返回
        ``None``。
    :raises HostDurableError: diagnostic 存在但类型非法时抛出。
    """

    value = manifest.get("diagnostic")
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise HostDurableError("runner-call manifest diagnostic must be object")
    return value


def _manifest_validation_status(manifest: Mapping[str, JsonValue]) -> str:
    """读取 manifest validation status。

    :param manifest: manifest body。
    :returns: complete 或 diagnostic 中的非 complete status。
    :raises HostDurableError: diagnostic status 字段非法时抛出。
    """

    diagnostic = _manifest_optional_diagnostic(manifest)
    if diagnostic is None:
        return _RUNNER_CALL_MANIFEST_STATUS_COMPLETE
    return _manifest_text(diagnostic, "status")


def _manifest_text(payload: Mapping[str, JsonValue], field_name: str) -> str:
    """读取 manifest / diagnostic 中的必填文本字段。

    :param payload: manifest 或 diagnostic JSON object。
    :param field_name: 字段名。
    :returns: 文本值。
    :raises HostDurableError: 字段缺失或类型非法时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"runner-call manifest {field_name} must be text")
    return value


def _manifest_optional_text(
    payload: Mapping[str, JsonValue], field_name: str
) -> str | None:
    """读取 manifest / diagnostic 中的可选文本字段。

    :param payload: manifest 或 diagnostic JSON object。
    :param field_name: 字段名。
    :returns: 文本值或 ``None``。
    :raises HostDurableError: 字段类型非法时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"runner-call manifest {field_name} must be text")
    return value


def _manifest_int(payload: Mapping[str, JsonValue], field_name: str) -> int:
    """读取 manifest 中的必填非负整数字段。

    :param payload: manifest JSON object。
    :param field_name: 字段名。
    :returns: 非负整数。
    :raises HostDurableError: 字段缺失或类型非法时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError(f"runner-call manifest {field_name} must be int")
    return value


def _manifest_optional_int(
    payload: Mapping[str, JsonValue], field_name: str
) -> int | None:
    """读取 manifest / diagnostic 中的可选非负整数字段。

    :param payload: manifest 或 diagnostic JSON object。
    :param field_name: 字段名。
    :returns: 非负整数或 ``None``。
    :raises HostDurableError: 字段类型非法时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError(f"runner-call manifest {field_name} must be int")
    return value


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


def _provider_protocol_failure_metadata(
    *,
    data: ProviderProtocolErrorData,
    raw_payload_ref: str | None,
) -> Mapping[str, JsonValue]:
    """构造 provider protocol error 的失败元数据 signal。

    :param data: Engine provider protocol error data。
    :param raw_payload_ref: Host 写入的 raw payload descriptor ref；无时为
        ``None``。
    :returns: failure metadata JSON object。
    :raises Exception: 不主动抛出异常。
    """

    diagnostic_refs = tuple(
        ref
        for ref in (raw_payload_ref, data.provider_request_id)
        if ref is not None
    )
    return {
        "schema_version": _FAILURE_METADATA_SCHEMA_VERSION,
        "signal_source": _EVENT_TYPE_PROVIDER_PROTOCOL_ERROR,
        "failure_kind": _FAILURE_KIND_PROVIDER_PROTOCOL_ERROR,
        "provider_error_code": serialize_engine_error_code(data.error_code),
        "diagnostic_refs": list(diagnostic_refs),
    }


def _provider_protocol_partial_tool_call_signal(
    *,
    partial_tool_calls: tuple[PartialToolCallSummary, ...],
    raw_payload_present: bool,
) -> Mapping[str, JsonValue]:
    """构造 provider protocol error 的 partial tool-call signal。

    :param partial_tool_calls: Engine 已提供的未完成工具调用有界摘要。
    :param raw_payload_present: Host raw payload descriptor 是否存在。
    :returns: partial tool-call signal JSON object。
    :raises Exception: 不主动抛出异常。
    """

    partial_count = len(partial_tool_calls)
    summary_status = (
        _PARTIAL_TOOL_CALL_SIGNAL_STATUS_PRESENT
        if partial_count > 0
        else _PARTIAL_TOOL_CALL_SIGNAL_STATUS_NONE
    )
    return {
        "schema_version": _PARTIAL_TOOL_CALL_SIGNAL_SCHEMA_VERSION,
        "signal_source": _EVENT_TYPE_PROVIDER_PROTOCOL_ERROR,
        "partial_tool_call_count": partial_count,
        "summary_status": summary_status,
        "raw_payload_present": raw_payload_present,
        "partial_tool_calls": [
            _partial_tool_call_summary_payload(summary)
            for summary in partial_tool_calls
        ],
    }


def _partial_tool_call_summary_payload(
    summary: PartialToolCallSummary,
) -> Mapping[str, JsonValue]:
    """序列化 Engine partial tool-call 有界摘要。

    :param summary: Engine 已裁剪和脱敏的 partial tool-call summary。
    :returns: 可写入 Host diagnostic payload 的 JSON object。
    :raises Exception: 不主动抛出异常。
    """

    arguments_present = summary.arguments_sha256 is not None
    return {
        "tool_call_index": summary.tool_call_index,
        "tool_call_id": summary.tool_call_id,
        "name_fragment": summary.name_fragment,
        "arguments_byte_size": summary.arguments_byte_size,
        "arguments_sha256": summary.arguments_sha256,
        "arguments_present": arguments_present,
    }


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
        terminal_notice=None,
        reason=None,
        transient_delta=None,
    )


def _event_rows_result(rows: tuple[EventLogRow, ...]) -> EngineIngestResult:
    """构造多事件接受结果。

    :param rows: 本次 ingest 接受的 EventLog rows。
    :returns: ingest result。
    """

    return EngineIngestResult(
        status=EngineIngestStatus.ACCEPTED,
        events=rows,
        terminal_closeout=False,
        terminal_notice=None,
        reason=None,
        transient_delta=None,
    )


def _accepted_no_event_result(
    transient_delta: ValidatedTransientDeltaCandidate,
) -> EngineIngestResult:
    """构造无 EventLog row 的接受结果。

    :param transient_delta: validation transaction 提交后待发布的瞬态候选。
    :returns: 表示已接受但无 durable Host event 的 ingest result。
    :raises Exception: 不主动抛出异常。
    """

    return EngineIngestResult(
        status=EngineIngestStatus.ACCEPTED,
        events=(),
        terminal_closeout=False,
        terminal_notice=None,
        reason=None,
        transient_delta=transient_delta,
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
        terminal_notice=closeout.terminal_notice,
        reason=closeout.reason,
        transient_delta=closeout.transient_delta,
        stop_worker_stream=closeout.stop_worker_stream,
    )


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


def _required_accepted_attempt_number(result: CompactionOperationResult) -> int:
    """返回 accepted operation 的全局 attempt number。

    :param result: 已由 operation owner 生成的结果。
    :returns: 正数 accepted attempt number。
    :raises RuntimeError: accepted result 缺少 attempt number 时抛出。
    """

    value = result.accepted_attempt_number
    if value is None or value <= 0:
        raise RuntimeError("accepted compaction is missing accepted attempt number")
    return value


__all__ = [
    "EngineEventCandidate",
    "EngineEventIngestor",
    "EngineIngestResult",
    "EngineIngestStatus",
    "LocalEngineEnvelope",
]
