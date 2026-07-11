"""Host Tool Awaiting accept path。

本模块实现 ToolRuntime 提交 ``ToolAwaitingOutcome`` 后的 Host canonical
等待接收路径：在单个 durable transaction 内写入 awaiting facts、创建
wait record，并把 Run / Attempt 推进到 ``WAITING`` / ``SUSPENDED``。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_await import ToolAwaitSpec
from dayu.host._event_payload import (
    attempt_suspended_payload,
    llm_safe_replay_arguments,
    payload_object,
    required_payload_text,
    resume_requested_payload,
    run_waiting_payload,
    tool_awaiting_payload,
    tool_result_wait_resolution_payload,
    wait_late_result_rejected_payload,
)
from dayu.host.api import (
    AttemptStatus,
    HostApiError,
    HostApiErrorCode,
    HostPayloadRef,
    ResolveWaitCancelledOutcome,
    ResolveWaitCompletedOutcome,
    ResolveWaitFailedOutcome,
    ResolveWaitLostOutcome,
    ResolveWaitOutcome,
    ResolveWaitRequest,
    RunStatus,
    WaitProviderStatusRef,
)
from dayu.host.durable.codec import (
    canonical_json_dumps,
    format_utc_timestamp,
    is_sha256_digest,
    sha256_digest_json,
)
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.errors import HostDurableError, HostIdempotencyConflictError
from dayu.host.durable.idempotency import (
    IdempotencyRecord,
    IdempotencyResultRef,
    IdempotencyResultKind,
    IdempotencyScope,
    IdempotencyScopeKind,
    IdempotencyStore,
)
from dayu.host.durable.schema import (
    TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT,
)
from dayu.host.durable.run_transition import (
    ResumeRunFromWaitingInput,
    WaitingRunTerminalInput,
    fail_run_from_waiting_in_transaction,
    mark_run_lost_from_waiting_in_transaction,
    resume_run_from_waiting_in_transaction,
)
from dayu.host.durable.state import (
    DispatchRecordStatus,
    DispatchRecordRow,
    ExternalJobRef,
    RunRow,
    StateMutationStatus,
    WaitRecordRow,
    WaitRecordStatus,
    WaitResumePolicy,
    WaitSnapshotRef,
    insert_wait_record,
    mark_attempt_suspended_row,
    mark_run_waiting_row,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
    read_wait_record_by_id,
    run_snapshot_from_row,
    WorkerKind,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    AcceptedEvidenceResultRef,
    AcceptedEvidenceToolQuery,
    accepted_evidence_envelope_to_json_value,
    derive_accepted_evidence_id,
)
from dayu.host.durable.wait_resolution_digest import (
    WAIT_RESOLUTION_OUTCOME_KIND_CANCELLED as _TOOL_FACT_KIND_CANCELLED,
    WAIT_RESOLUTION_OUTCOME_KIND_COMPLETED as _TOOL_FACT_KIND_COMPLETED,
    WAIT_RESOLUTION_OUTCOME_KIND_FAILED as _TOOL_FACT_KIND_FAILED,
    WAIT_RESOLUTION_OUTCOME_KIND_LOST as _TOOL_FACT_KIND_LOST,
    resolve_wait_outcome_json,
    resolve_wait_cancelled_result_json as _tool_cancelled_json,
    resolve_wait_completed_result_json as _tool_success_json,
    resolve_wait_failed_result_json as _tool_failure_json,
    resolve_wait_lost_result_json as _tool_lost_json,
    wait_resolution_digest,
)
from dayu.host.projection import (
    ProjectionCatchupPort,
    catch_up_projection_best_effort,
)
from dayu.host.wait_adapter import WaitAdapterBinding
from dayu.host.wait_boundary import (
    WaitBoundaryDecisionKind,
    classify_wait_time_boundary,
)
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_LOGGER = logging.getLogger(__name__)
_TOOL_AWAITING_ACCEPT_SCOPE_KIND = IdempotencyScopeKind.TOOL_AWAITING_ACCEPT
_TOOL_AWAITING_ACCEPT_RESULT_KIND = IdempotencyResultKind.TOOL_AWAITING_ACCEPT_ACK
_EVENT_TYPE_TOOL_CALL_REQUESTED = "TOOL_CALL_REQUESTED"
_EVENT_TYPE_TOOL_AWAITING = "TOOL_AWAITING"
_EVENT_TYPE_RUN_WAITING = "RUN_WAITING"
_EVENT_TYPE_ATTEMPT_SUSPENDED = "ATTEMPT_SUSPENDED"
_WAIT_RESOLUTION_SCOPE_KIND = IdempotencyScopeKind.WAIT_RESOLUTION
_WAIT_RESOLUTION_RESULT_KIND = IdempotencyResultKind.WAIT_RESOLUTION
_WAIT_LATE_REJECTION_SCOPE_KIND = IdempotencyScopeKind.WAIT_LATE_REJECTION
_WAIT_LATE_REJECTION_RESULT_KIND = (
    IdempotencyResultKind.WAIT_LATE_REJECTION_DIAGNOSTIC
)
_AWAITING_ACCEPT_ACTOR = "host.tool_runtime"
_AWAITING_ACCEPT_SOURCE = "host.tool_runtime.awaiting_accept"
_EVENT_ID_TOOL_CALL_REQUESTED_PREFIX = "event-tool-call-requested-awaiting-"
_EVENT_ID_TOOL_AWAITING_PREFIX = "event-tool-awaiting-"
_EVENT_ID_RUN_WAITING_PREFIX = "event-run-waiting-"
_EVENT_ID_ATTEMPT_SUSPENDED_PREFIX = "event-attempt-suspended-"
_EVENT_ID_RESUME_REQUESTED_PREFIX = "event-resume-requested-"
_EVENT_ID_WAIT_TOOL_RESULT_PREFIX = "event-tool-result-wait-resolution-"
_EVENT_ID_RESUME_RUN_STARTED_PREFIX = "event-run-started-resume-"
_EVENT_ID_RESUME_ATTEMPT_STARTED_PREFIX = "event-attempt-started-resume-"
_EVENT_ID_WAIT_RUN_FAILED_PREFIX = "event-run-failed-wait-resolution-"
_EVENT_ID_WAIT_RUN_LOST_PREFIX = "event-run-lost-wait-resolution-"
_EVENT_ID_WAIT_LATE_RESULT_REJECTED_PREFIX = "event-wait-late-result-rejected-"
_RESUME_ATTEMPT_ID_PREFIX = "attempt-resume-"
_RESUME_EXECUTION_ID_PREFIX = "execution-resume-"
_RESUME_DISPATCH_ID_PREFIX = "dispatch-resume-"
_TOOL_FACT_ID_PREFIX = "tool-fact-wait-"
_WAIT_RESOLUTION_SOURCE = "host.resolve_wait"
_WAIT_TERMINAL_REASON_FAILED = "wait_result_failed"
_WAIT_TERMINAL_REASON_LOST = "wait_result_lost"
_EVENT_TYPE_WAIT_LATE_RESULT_REJECTED = "WAIT_LATE_RESULT_REJECTED"


class _AwaitingAcceptStateConflictError(HostDurableError):
    """awaiting accept 已通过 precondition 后的状态 CAS 冲突。"""


class ToolAwaitingAcceptRejectReason(StrEnum):
    """Host awaiting accept 拒绝原因。"""

    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    INVALID_ATTEMPT = "invalid_attempt"
    STALE_EXECUTION = "stale_execution"
    CAS_CONFLICT = "cas_conflict"


class WaitLateRejectionReason(StrEnum):
    """晚到 wait result 拒绝原因。"""

    WAIT_CANCELLED = "wait_cancelled"
    WAIT_EXPIRED = "wait_expired"
    WAIT_LOST = "wait_lost"
    WAIT_ALREADY_RESOLVED = "wait_already_resolved"
    WAIT_ALREADY_FAILED = "wait_already_failed"
    RUN_TERMINAL = "run_terminal"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    INVALID_WAIT_STATE = "invalid_wait_state"


@dataclass(frozen=True, slots=True)
class ToolAwaitingEventRef:
    """Host awaiting accept 返回的 EventLog 引用。

    :param event_id: EventLog 事件标识。
    :param event_sequence: EventLog 全局递增序号。
    """

    event_id: str
    event_sequence: int

    def __post_init__(self) -> None:
        """校验事件引用字段。

        :returns: ``None``。
        :raises ValueError: 事件标识为空或序号非法时抛出。
        """

        if self.event_id.strip() == "":
            raise ValueError("event_id must be non-empty")
        if self.event_sequence <= 0:
            raise ValueError("event_sequence must be positive")


@dataclass(frozen=True, slots=True)
class ToolAwaitingAcceptCandidate:
    """Host awaiting accept candidate。

    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :param iteration_id: Engine iteration id。
    :param tool_call_id: 工具调用 id。
    :param tool_name: 工具名。
    :param tool_schema_digest: 工具 schema digest。
    :param tool_identity_digest: 工具身份 digest。
    :param normalized_arguments_digest: 规范化参数 digest。
    :param accepted_arguments: 与 ``normalized_arguments_digest`` 同源的工具参数。
    :param await_spec: 工具等待规约。
    :param snapshot_ref: 可选等待快照引用。
    :param binding: Host 选择的等待 adapter binding。
    :param external_job_ref: 可选外部 job 引用。
    :param wait_id: Host wait record id。
    :param accept_idempotency_key: Host awaiting accept 幂等键。
    :param semantic_input_digest: Host awaiting accept 语义 digest。
    """

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    iteration_id: str
    tool_call_id: str
    tool_name: str
    tool_schema_digest: str
    tool_identity_digest: str
    normalized_arguments_digest: str
    accepted_arguments: Mapping[str, JsonValue]
    await_spec: ToolAwaitSpec
    snapshot_ref: WaitSnapshotRef | None
    binding: WaitAdapterBinding
    external_job_ref: ExternalJobRef | None
    wait_id: str
    accept_idempotency_key: str
    semantic_input_digest: str

    def __post_init__(self) -> None:
        """校验 awaiting accept candidate 字段。

        :returns: ``None``。
        :raises ValueError: 任一必填字段为空或 digest 非法时抛出。
        """

        for value, field_name in (
            (self.session_id, "session_id"),
            (self.run_id, "run_id"),
            (self.attempt_id, "attempt_id"),
            (self.execution_id, "execution_id"),
            (self.iteration_id, "iteration_id"),
            (self.tool_call_id, "tool_call_id"),
            (self.tool_name, "tool_name"),
            (self.wait_id, "wait_id"),
            (self.accept_idempotency_key, "accept_idempotency_key"),
        ):
            if value.strip() == "":
                raise ValueError(f"{field_name} must be non-empty")
        for value, field_name in (
            (self.tool_schema_digest, "tool_schema_digest"),
            (self.tool_identity_digest, "tool_identity_digest"),
            (self.normalized_arguments_digest, "normalized_arguments_digest"),
            (self.semantic_input_digest, "semantic_input_digest"),
        ):
            if not is_sha256_digest(value):
                raise ValueError(f"{field_name} must be sha256 digest")
        if self.binding.resume_policy is WaitResumePolicy.POLL:
            if self.external_job_ref is None:
                raise ValueError("background task candidate requires external_job_ref")
        if (
            self.external_job_ref is not None
            and self.external_job_ref.adapter_key != self.binding.adapter_key
        ):
            raise ValueError("external_job_ref adapter_key must match binding")
        if (
            sha256_digest_json({"arguments": dict(self.accepted_arguments)})
            != self.normalized_arguments_digest
        ):
            raise ValueError("accepted_arguments digest mismatch")


@dataclass(frozen=True, slots=True)
class ToolAwaitingAcceptedAck:
    """Host 已接受 awaiting candidate 的 ack。

    :param accepted_event_refs: 本次 accept 关联的 canonical EventLog refs。
    :param wait_id: Host wait record id。
    :param tool_awaiting_event_ref: ``TOOL_AWAITING`` event ref。
    :param run_waiting_event_ref: ``RUN_WAITING`` event ref。
    :param attempt_suspended_event_ref: ``ATTEMPT_SUSPENDED`` event ref。
    :param result_digest: accepted ack 的稳定 digest。
    :param idempotency_record_ref: Host accept 幂等记录引用。
    """

    accepted_event_refs: tuple[ToolAwaitingEventRef, ...]
    wait_id: str
    tool_awaiting_event_ref: ToolAwaitingEventRef
    run_waiting_event_ref: ToolAwaitingEventRef
    attempt_suspended_event_ref: ToolAwaitingEventRef
    result_digest: str
    idempotency_record_ref: str


@dataclass(frozen=True, slots=True)
class ToolAwaitingRejectedAck:
    """Host 明确拒绝 awaiting candidate 的 ack。

    :param reason_code: 拒绝原因码。
    :param message: 诊断说明。
    :param retryable: 调用方是否可重试同一 candidate。
    """

    reason_code: ToolAwaitingAcceptRejectReason
    message: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class ToolAwaitingAcceptTimedOut:
    """Host awaiting accept barrier 未确认结果。

    :param attempt_count: 已尝试次数。
    :param last_error_code: 最后错误码；无则为 ``None``。
    :param diagnostic_refs: 工具运行时诊断引用 id。
    """

    attempt_count: int
    last_error_code: str | None
    diagnostic_refs: tuple[str, ...] = ()


ToolAwaitingAcceptResult = (
    ToolAwaitingAcceptedAck | ToolAwaitingRejectedAck | ToolAwaitingAcceptTimedOut
)
"""awaiting accept 结果封闭联合。"""


@dataclass(frozen=True, slots=True)
class ResolveWaitResult:
    """resolve wait command 内部结果。

    :param run: resolve 后最新 Run row。
    :param dispatch_record: 新建 resume dispatch record；无则为 ``None``。
    :param idempotent_replay: 本次是否为幂等重放。
    """

    run: RunRow
    dispatch_record: DispatchRecordRow | None
    idempotent_replay: bool


@dataclass(frozen=True, slots=True)
class _LateRejectResult:
    """late wait result 已完成 durable diagnostic 后的内部拒绝结果。

    :param message: 对外错误消息。
    """

    message: str


@dataclass(frozen=True, slots=True)
class _ResolveWaitEventPlan:
    """resolve wait 派生 id 规划。"""

    suffix: str
    tool_fact_id: str
    resume_requested_event_id: str
    tool_result_event_id: str
    run_started_event_id: str
    attempt_started_event_id: str
    run_failed_event_id: str
    run_lost_event_id: str
    resume_attempt_id: str
    resume_execution_id: str
    resume_dispatch_record_id: str


@dataclass(frozen=True, slots=True)
class _WaitResolutionPayloadPlan:
    """resolve wait transition payload 规划。"""

    resolution_kind: str
    tool_fact_kind: str
    outcome_digest: str
    payload_digest: str | None
    payload_ref: HostPayloadRef | None
    provider_status_ref: WaitProviderStatusRef | None
    result_json: JsonValue


class HostToolAwaitingAcceptPort(ABC):
    """工具 awaiting canonical fact accept barrier 抽象端口。"""

    @abstractmethod
    def accept_tool_awaiting(
        self, candidate: ToolAwaitingAcceptCandidate
    ) -> ToolAwaitingAcceptResult:
        """接受工具 awaiting candidate。

        :param candidate: awaiting candidate。
        :returns: accepted / rejected / timeout 结构化结果。
        """

        raise NotImplementedError


class DefaultHostToolAwaitingAcceptPort(HostToolAwaitingAcceptPort):
    """基于 Host durable store 的 awaiting accept barrier 实现。"""

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        event_log_store: EventLogStore | None = None,
        idempotency_store: IdempotencyStore | None = None,
    ) -> None:
        """初始化默认 awaiting accept port。

        :param transaction_runner: Host durable transaction runner。
        :param event_log_store: EventLog primitive；无则创建默认实现。
        :param idempotency_store: Idempotency primitive；无则创建默认实现。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._event_log_store = (
            event_log_store if event_log_store is not None else EventLogStore()
        )
        self._idempotency_store = (
            idempotency_store
            if idempotency_store is not None
            else IdempotencyStore()
        )

    def accept_tool_awaiting(
        self, candidate: ToolAwaitingAcceptCandidate
    ) -> ToolAwaitingAcceptResult:
        """接受 awaiting candidate 并写入 canonical EventLog / wait record。

        :param candidate: awaiting candidate。
        :returns: accepted ack、rejected ack 或 timeout 结果。
        """

        try:
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                (
                    "host.waiting.accept_tool_awaiting.accepted "
                    "session_id=%s run_id=%s attempt_id=%s execution_id=%s "
                    "tool_call_id=%s tool_name=%s adapter_key=%s"
                ),
                candidate.session_id,
                candidate.run_id,
                candidate.attempt_id,
                candidate.execution_id,
                candidate.tool_call_id,
                candidate.tool_name,
                candidate.binding.adapter_key.value,
            )
            result = self._transaction_runner.run_write(
                lambda transaction: self._accept_in_transaction(
                    transaction, candidate
                )
            )
            _log_tool_awaiting_accept_result(candidate, result)
            return result
        except HostIdempotencyConflictError:
            result = ToolAwaitingRejectedAck(
                reason_code=ToolAwaitingAcceptRejectReason.IDEMPOTENCY_CONFLICT,
                message="tool awaiting accept idempotency conflict",
                retryable=False,
            )
            _log_tool_awaiting_accept_result(candidate, result)
            return result
        except _AwaitingAcceptStateConflictError:
            result = ToolAwaitingRejectedAck(
                reason_code=ToolAwaitingAcceptRejectReason.CAS_CONFLICT,
                message="tool awaiting accept state CAS failed",
                retryable=False,
            )
            _log_tool_awaiting_accept_result(candidate, result)
            return result

    def _accept_in_transaction(
        self, transaction: HostTransaction, candidate: ToolAwaitingAcceptCandidate
    ) -> ToolAwaitingAcceptResult:
        """在单个 Host write transaction 内执行 awaiting accept。

        :param transaction: 当前 Host transaction。
        :param candidate: awaiting candidate。
        :returns: awaiting accept 结果。
        """

        scope = _accept_idempotency_scope(candidate)
        existing = self._idempotency_store.read_idempotency_record(
            transaction, scope
        )
        if existing is not None:
            if existing.semantic_input_digest != candidate.semantic_input_digest:
                return ToolAwaitingRejectedAck(
                    reason_code=ToolAwaitingAcceptRejectReason.IDEMPOTENCY_CONFLICT,
                    message="tool awaiting accept idempotency conflict",
                    retryable=False,
                )
            return _accepted_ack_from_existing(
                self._event_log_store, transaction, candidate, existing
            )

        invalid = _invalid_awaiting_precondition(transaction, candidate)
        if invalid is not None:
            return ToolAwaitingRejectedAck(
                reason_code=invalid,
                message="tool awaiting accept precondition failed",
                retryable=False,
            )

        plan = _event_plan(candidate)
        occurred_at = datetime.now(UTC)
        tool_call_requested = self._event_log_store.append_event(
            transaction,
            _tool_call_requested_event_request(
                candidate, plan.tool_call_requested_id, occurred_at
            ),
        ).row
        tool_awaiting = self._event_log_store.append_event(
            transaction,
            _tool_awaiting_event_request(candidate, plan.tool_awaiting_id, occurred_at),
        ).row
        run_waiting = self._event_log_store.append_event(
            transaction,
            _run_waiting_event_request(
                candidate, plan.run_waiting_id, occurred_at, tool_awaiting
            ),
        ).row
        attempt_suspended = self._event_log_store.append_event(
            transaction,
            _attempt_suspended_event_request(
                candidate,
                plan.attempt_suspended_id,
                occurred_at,
                run_waiting,
            ),
        ).row
        timestamp = format_utc_timestamp(occurred_at)
        insert_wait_record(
            transaction,
            _wait_record_row(
                candidate=candidate,
                created_event=tool_awaiting,
                updated_event=attempt_suspended,
                timestamp=timestamp,
            ),
        )
        run_result = mark_run_waiting_row(
            transaction,
            run_id=candidate.run_id,
            current_attempt_id=candidate.attempt_id,
            updated_at=timestamp,
        )
        attempt_result = mark_attempt_suspended_row(
            transaction,
            attempt_id=candidate.attempt_id,
            terminal_event_id=attempt_suspended.event_id,
            terminal_event_sequence=attempt_suspended.event_sequence,
            terminal_at=timestamp,
        )
        if (
            run_result.status is not StateMutationStatus.UPDATED
            or attempt_result.status is not StateMutationStatus.UPDATED
        ):
            raise _AwaitingAcceptStateConflictError(
                "tool awaiting accept state CAS failed"
            )
        record = self._idempotency_store.record_idempotent_result(
            transaction,
            scope,
            candidate.semantic_input_digest,
            IdempotencyResultRef(
                result_kind=_TOOL_AWAITING_ACCEPT_RESULT_KIND,
                result_ref=candidate.wait_id,
                created_event_id=attempt_suspended.event_id,
                created_event_sequence=attempt_suspended.event_sequence,
            ),
        )
        return _accepted_ack_from_rows(
            candidate=candidate,
            tool_call_requested=tool_call_requested,
            tool_awaiting=tool_awaiting,
            run_waiting=run_waiting,
            attempt_suspended=attempt_suspended,
            idempotency_record=record,
        )


class DefaultHostResolveWaitService:
    """基于 Host durable store 的 resolve wait command service。"""

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        event_log_store: EventLogStore | None = None,
        idempotency_store: IdempotencyStore | None = None,
        projection_catchup_port: ProjectionCatchupPort | None = None,
    ) -> None:
        """初始化默认 resolve wait service。

        :param transaction_runner: Host durable transaction runner。
        :param event_log_store: EventLog primitive；无则创建默认实现。
        :param idempotency_store: Idempotency primitive；无则创建默认实现。
        :param projection_catchup_port: commit 后 best-effort projection catch-up 端口。
        :returns: ``None``。
        """

        self._transaction_runner = transaction_runner
        self._event_log_store = (
            event_log_store if event_log_store is not None else EventLogStore()
        )
        self._idempotency_store = (
            idempotency_store
            if idempotency_store is not None
            else IdempotencyStore()
        )
        self._projection_catchup_port = projection_catchup_port

    def resolve_wait(self, wait_id: str, request: ResolveWaitRequest) -> ResolveWaitResult:
        """接收等待结果并推进 Run。

        :param wait_id: wait record id。
        :param request: typed resolve wait 请求。
        :returns: resolve 后最新 Run 与可选 resume dispatch。
        :raises HostApiError: wait 缺失、状态非法或幂等冲突时抛出。
        """

        if wait_id.strip() == "":
            raise HostApiError(
                code=HostApiErrorCode.INVALID_STATE,
                message="wait_id must be non-empty",
                retryable=False,
            )
        try:
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "host.waiting.resolve_wait.accepted wait_id=%s",
                wait_id,
            )
            result = self._transaction_runner.run_write(
                lambda transaction: self._resolve_in_transaction(
                    transaction, wait_id, request
                )
            )
            if isinstance(result, _LateRejectResult):
                raise HostApiError(
                    code=HostApiErrorCode.INVALID_STATE,
                    message=result.message,
                    retryable=False,
                )
            catch_up_projection_best_effort(self._projection_catchup_port)
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                (
                    "host.waiting.resolve_wait.committed session_id=%s "
                    "run_id=%s run_status=%s wait_id=%s dispatch_record_id=%s "
                    "idempotent_replay=%s"
                ),
                result.run.session_id,
                result.run.run_id,
                result.run.status.value,
                wait_id,
                None
                if result.dispatch_record is None
                else result.dispatch_record.dispatch_record_id,
                result.idempotent_replay,
            )
            return result
        except HostIdempotencyConflictError as exc:
            raise HostApiError(
                code=HostApiErrorCode.IDEMPOTENCY_CONFLICT,
                message="resolve wait idempotency conflict",
                retryable=False,
            ) from exc

    def _resolve_in_transaction(
        self,
        transaction: HostTransaction,
        wait_id: str,
        request: ResolveWaitRequest,
    ) -> ResolveWaitResult | _LateRejectResult:
        """在单个 Host write transaction 内执行 resolve wait。

        :param transaction: 当前 Host transaction。
        :param wait_id: wait record id。
        :param request: typed resolve wait 请求。
        :returns: resolve 结果。
        """

        wait_record = read_wait_record_by_id(transaction, wait_id)
        if wait_record is None:
            raise HostApiError(
                code=HostApiErrorCode.NOT_FOUND,
                message="wait record not found",
                retryable=False,
            )
        scope = _wait_resolution_scope(wait_id, request.idempotency_key)
        resolution_digest = _wait_resolution_digest(wait_id, request)
        owner_run = read_run_by_id(transaction, wait_record.run_id)
        if owner_run is None:
            raise HostApiError(
                code=HostApiErrorCode.NOT_FOUND,
                message="wait owner run not found",
                retryable=False,
            )
        if wait_record.status in (
            WaitRecordStatus.RESOLVED,
            WaitRecordStatus.FAILED,
            WaitRecordStatus.LOST,
        ):
            replay = self._replay_terminal_resolution_or_none(
                transaction=transaction,
                wait_record=wait_record,
                scope=scope,
                resolution_digest=resolution_digest,
            )
            if replay is not None:
                return replay
            if wait_record.status in (
                WaitRecordStatus.RESOLVED,
                WaitRecordStatus.FAILED,
            ):
                raise HostApiError(
                    code=HostApiErrorCode.INVALID_STATE,
                    message="wait record is already resolved by another key",
                    retryable=False,
                )
            return self._reject_late_result(
                transaction=transaction,
                wait_record=wait_record,
                request=request,
                rejection_reason=_terminal_wait_rejection_reason(wait_record.status),
            )
        if wait_record.status is WaitRecordStatus.CANCELLED:
            return self._reject_late_result(
                transaction=transaction,
                wait_record=wait_record,
                request=request,
                rejection_reason=WaitLateRejectionReason.WAIT_CANCELLED,
            )
        if wait_record.status is not WaitRecordStatus.WAITING:
            return self._reject_late_result(
                transaction=transaction,
                wait_record=wait_record,
                request=request,
                rejection_reason=WaitLateRejectionReason.INVALID_WAIT_STATE,
            )
        boundary_decision = classify_wait_time_boundary(
            wait_record, observed_at=request.observed_at
        )
        if boundary_decision.kind is WaitBoundaryDecisionKind.INVALID:
            raise HostApiError(
                code=HostApiErrorCode.INVALID_STATE,
                message="wait record contains invalid time boundary",
                retryable=False,
            )
        if boundary_decision.kind is WaitBoundaryDecisionKind.EXPIRED:
            return self._reject_late_result(
                transaction=transaction,
                wait_record=wait_record,
                request=request,
                rejection_reason=WaitLateRejectionReason.WAIT_EXPIRED,
            )
        if owner_run.status in (
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.LOST,
        ):
            return self._reject_late_result(
                transaction=transaction,
                wait_record=wait_record,
                request=request,
                rejection_reason=WaitLateRejectionReason.RUN_TERMINAL,
            )
        existing = self._idempotency_store.read_idempotency_record(
            transaction, scope
        )
        if existing is not None:
            if existing.semantic_input_digest != resolution_digest:
                raise HostApiError(
                    code=HostApiErrorCode.IDEMPOTENCY_CONFLICT,
                    message="resolve wait idempotency conflict",
                    retryable=False,
                )
            return _resolve_wait_result_from_existing(transaction, wait_record)

        payload_plan = _wait_resolution_payload_plan(request)
        event_plan = _resolve_wait_event_plan(resolution_digest)
        if isinstance(
            request.outcome,
            (ResolveWaitCompletedOutcome, ResolveWaitCancelledOutcome),
        ):
            result = self._resolve_resume(
                transaction=transaction,
                wait_record=wait_record,
                request=request,
                resolution_digest=resolution_digest,
                event_plan=event_plan,
                payload_plan=payload_plan,
            )
        elif isinstance(request.outcome, ResolveWaitFailedOutcome):
            result = self._resolve_failed(
                transaction=transaction,
                wait_record=wait_record,
                request=request,
                resolution_digest=resolution_digest,
                event_plan=event_plan,
                payload_plan=payload_plan,
            )
        elif isinstance(request.outcome, ResolveWaitLostOutcome):
            result = self._resolve_lost(
                transaction=transaction,
                wait_record=wait_record,
                request=request,
                resolution_digest=resolution_digest,
                event_plan=event_plan,
                payload_plan=payload_plan,
            )
        else:
            raise HostApiError(
                code=HostApiErrorCode.INVALID_STATE,
                message="resolve wait outcome is invalid",
                retryable=False,
            )
        created_event_id, created_event_sequence = _resolve_created_event_ref(result)
        self._idempotency_store.record_idempotent_result(
            transaction,
            scope,
            resolution_digest,
            IdempotencyResultRef(
                result_kind=_WAIT_RESOLUTION_RESULT_KIND,
                result_ref=wait_id,
                created_event_id=created_event_id,
                created_event_sequence=created_event_sequence,
            ),
        )
        return result

    def _replay_terminal_resolution_or_none(
        self,
        *,
        transaction: HostTransaction,
        wait_record: WaitRecordRow,
        scope: IdempotencyScope,
        resolution_digest: str,
    ) -> ResolveWaitResult | None:
        """重放已完成的 wait resolution。

        :param transaction: 当前 Host transaction。
        :param wait_record: 已终态 wait record。
        :param scope: resolve wait 幂等作用域。
        :param resolution_digest: 本次请求 digest。
        :returns: 幂等重放结果；不同 key 晚到结果返回 ``None``。
        :raises HostApiError: 相同 key 但 digest 冲突时抛出。
        """

        record = self._idempotency_store.read_idempotency_record(
            transaction, scope
        )
        if record is None:
            return None
        if record.semantic_input_digest != resolution_digest:
            raise HostApiError(
                code=HostApiErrorCode.IDEMPOTENCY_CONFLICT,
                message="resolve wait idempotency conflict",
                retryable=False,
            )
        return _resolve_wait_result_from_existing(transaction, wait_record)

    def _reject_late_result(
        self,
        *,
        transaction: HostTransaction,
        wait_record: WaitRecordRow,
        request: ResolveWaitRequest,
        rejection_reason: WaitLateRejectionReason,
    ) -> _LateRejectResult:
        """记录晚到 wait result diagnostic 并拒绝请求。

        :param transaction: 当前 Host transaction。
        :param wait_record: 非可解析 wait record。
        :param request: resolve wait 请求。
        :param rejection_reason: 拒绝原因。
        :returns: transaction commit 后由外层转成 ``HostApiError`` 的拒绝结果。
        :raises HostApiError: 幂等冲突时抛出。
        """

        payload_plan = _wait_resolution_payload_plan(request)
        late_digest = _wait_late_rejection_digest(
            wait_record=wait_record,
            request=request,
            rejection_reason=rejection_reason,
            payload_plan=payload_plan,
        )
        scope = _wait_late_rejection_scope(wait_record.wait_id, request.idempotency_key)
        existing = self._idempotency_store.read_idempotency_record(transaction, scope)
        if existing is not None:
            if existing.semantic_input_digest != late_digest:
                raise HostApiError(
                    code=HostApiErrorCode.IDEMPOTENCY_CONFLICT,
                    message="late wait result idempotency conflict",
                    retryable=False,
                )
            return _LateRejectResult(
                message="late wait result was already rejected"
            )
        event = self._event_log_store.append_event(
            transaction,
            _wait_late_result_rejected_event_request(
                event_id=_wait_late_result_rejected_event_id(late_digest),
                wait_record=wait_record,
                request=request,
                rejection_reason=rejection_reason,
                payload_plan=payload_plan,
            ),
        ).row
        self._idempotency_store.record_idempotent_result(
            transaction,
            scope,
            late_digest,
            IdempotencyResultRef(
                result_kind=_WAIT_LATE_REJECTION_RESULT_KIND,
                result_ref=event.event_id,
                created_event_id=event.event_id,
                created_event_sequence=event.event_sequence,
            ),
        )
        return _LateRejectResult(message="wait result is late and was rejected")

    def _resolve_resume(
        self,
        *,
        transaction: HostTransaction,
        wait_record: WaitRecordRow,
        request: ResolveWaitRequest,
        resolution_digest: str,
        event_plan: _ResolveWaitEventPlan,
        payload_plan: _WaitResolutionPayloadPlan,
    ) -> ResolveWaitResult:
        """处理 completed/cancelled 等待结果并创建 resume Attempt。

        :param transaction: 当前 Host transaction。
        :param wait_record: active wait record。
        :param request: resolve wait 请求。
        :param resolution_digest: 语义 digest。
        :param event_plan: 稳定 id 规划。
        :param payload_plan: payload 规划。
        :returns: resolve 结果。
        """

        transition = resume_run_from_waiting_in_transaction(
            transaction,
            self._event_log_store,
            ResumeRunFromWaitingInput(
                wait_id=wait_record.wait_id,
                run_id=wait_record.run_id,
                suspended_attempt_id=wait_record.attempt_id,
                resume_attempt_id=event_plan.resume_attempt_id,
                resume_execution_id=event_plan.resume_execution_id,
                resume_dispatch_record_id=event_plan.resume_dispatch_record_id,
                resume_requested_event_id=event_plan.resume_requested_event_id,
                tool_result_event_id=event_plan.tool_result_event_id,
                run_started_event_id=event_plan.run_started_event_id,
                attempt_started_event_id=event_plan.attempt_started_event_id,
                occurred_at=request.observed_at,
                actor=request.context.actor,
                source=_WAIT_RESOLUTION_SOURCE,
                resolution_idempotency_key=request.idempotency_key,
                resolution_digest=resolution_digest,
                resume_requested_payload=_resume_requested_payload(
                    wait_record=wait_record,
                    request=request,
                    payload_plan=payload_plan,
                    event_plan=event_plan,
                ),
                tool_result_payload=_tool_result_resolution_payload(
                    transaction=transaction,
                    event_log_store=self._event_log_store,
                    wait_record=wait_record,
                    request=request,
                    payload_plan=payload_plan,
                    event_plan=event_plan,
                    wait_status_after=WaitRecordStatus.RESOLVED,
                    resume=True,
                ),
                tool_result_payload_ref=_payload_ref_text(payload_plan.payload_ref),
                tool_result_payload_digest=_event_payload_digest(payload_plan),
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
            ),
        )
        if transition.status is not StateMutationStatus.UPDATED or transition.run is None:
            raise HostApiError(
                code=HostApiErrorCode.INVALID_STATE,
                message="wait record is no longer resolvable",
                retryable=True,
            )
        return ResolveWaitResult(
            run=transition.run,
            dispatch_record=transition.dispatch_record,
            idempotent_replay=False,
        )

    def _resolve_failed(
        self,
        *,
        transaction: HostTransaction,
        wait_record: WaitRecordRow,
        request: ResolveWaitRequest,
        resolution_digest: str,
        event_plan: _ResolveWaitEventPlan,
        payload_plan: _WaitResolutionPayloadPlan,
    ) -> ResolveWaitResult:
        """处理 failed 等待结果并收口 Run。

        :param transaction: 当前 Host transaction。
        :param wait_record: active wait record。
        :param request: resolve wait 请求。
        :param resolution_digest: 语义 digest。
        :param event_plan: 稳定 id 规划。
        :param payload_plan: payload 规划。
        :returns: resolve 结果。
        """

        outcome = request.outcome
        if not isinstance(outcome, ResolveWaitFailedOutcome):
            raise TypeError("resolve wait failed path received non-failed outcome")
        transition = fail_run_from_waiting_in_transaction(
            transaction,
            self._event_log_store,
            WaitingRunTerminalInput(
                wait_id=wait_record.wait_id,
                run_id=wait_record.run_id,
                suspended_attempt_id=wait_record.attempt_id,
                tool_result_event_id=event_plan.tool_result_event_id,
                run_terminal_event_id=event_plan.run_failed_event_id,
                run_terminal_status=RunStatus.FAILED,
                wait_terminal_status=WaitRecordStatus.FAILED,
                occurred_at=request.observed_at,
                actor=request.context.actor,
                source=_WAIT_RESOLUTION_SOURCE,
                reason=_WAIT_TERMINAL_REASON_FAILED,
                message=_failed_wait_terminal_message(outcome),
                resolution_idempotency_key=request.idempotency_key,
                resolution_digest=resolution_digest,
                tool_result_payload=_tool_result_resolution_payload(
                    transaction=transaction,
                    event_log_store=self._event_log_store,
                    wait_record=wait_record,
                    request=request,
                    payload_plan=payload_plan,
                    event_plan=event_plan,
                    wait_status_after=WaitRecordStatus.FAILED,
                    resume=False,
                ),
                tool_result_payload_ref=_payload_ref_text(payload_plan.payload_ref),
                tool_result_payload_digest=_event_payload_digest(payload_plan),
            ),
        )
        if transition.status is not StateMutationStatus.UPDATED or transition.run is None:
            raise HostApiError(
                code=HostApiErrorCode.INVALID_STATE,
                message="wait record is no longer resolvable",
                retryable=True,
            )
        return ResolveWaitResult(
            run=transition.run,
            dispatch_record=None,
            idempotent_replay=False,
        )

    def _resolve_lost(
        self,
        *,
        transaction: HostTransaction,
        wait_record: WaitRecordRow,
        request: ResolveWaitRequest,
        resolution_digest: str,
        event_plan: _ResolveWaitEventPlan,
        payload_plan: _WaitResolutionPayloadPlan,
    ) -> ResolveWaitResult:
        """处理 lost 等待结果并收口 Run。

        :param transaction: 当前 Host transaction。
        :param wait_record: active wait record。
        :param request: resolve wait 请求。
        :param resolution_digest: 语义 digest。
        :param event_plan: 稳定 id 规划。
        :param payload_plan: payload 规划。
        :returns: resolve 结果。
        """

        outcome = request.outcome
        if not isinstance(outcome, ResolveWaitLostOutcome):
            raise TypeError("resolve wait lost path received non-lost outcome")
        transition = mark_run_lost_from_waiting_in_transaction(
            transaction,
            self._event_log_store,
            WaitingRunTerminalInput(
                wait_id=wait_record.wait_id,
                run_id=wait_record.run_id,
                suspended_attempt_id=wait_record.attempt_id,
                tool_result_event_id=event_plan.tool_result_event_id,
                run_terminal_event_id=event_plan.run_lost_event_id,
                run_terminal_status=RunStatus.LOST,
                wait_terminal_status=WaitRecordStatus.LOST,
                occurred_at=request.observed_at,
                actor=request.context.actor,
                source=_WAIT_RESOLUTION_SOURCE,
                reason=_WAIT_TERMINAL_REASON_LOST,
                message=outcome.message,
                resolution_idempotency_key=request.idempotency_key,
                resolution_digest=resolution_digest,
                tool_result_payload=_tool_result_resolution_payload(
                    transaction=transaction,
                    event_log_store=self._event_log_store,
                    wait_record=wait_record,
                    request=request,
                    payload_plan=payload_plan,
                    event_plan=event_plan,
                    wait_status_after=WaitRecordStatus.LOST,
                    resume=False,
                ),
                tool_result_payload_ref=_payload_ref_text(payload_plan.payload_ref),
                tool_result_payload_digest=_event_payload_digest(payload_plan),
            ),
        )
        if transition.status is not StateMutationStatus.UPDATED or transition.run is None:
            raise HostApiError(
                code=HostApiErrorCode.INVALID_STATE,
                message="wait record is no longer resolvable",
                retryable=True,
            )
        return ResolveWaitResult(
            run=transition.run,
            dispatch_record=None,
            idempotent_replay=False,
        )


@dataclass(frozen=True, slots=True)
class _AwaitingEventPlan:
    """awaiting accept path 的稳定事件 id 规划。"""

    tool_call_requested_id: str
    tool_awaiting_id: str
    run_waiting_id: str
    attempt_suspended_id: str


def _wait_resolution_scope(wait_id: str, idempotency_key: str) -> IdempotencyScope:
    """构造 wait resolution 幂等作用域。

    :param wait_id: wait record id。
    :param idempotency_key: resolve wait 幂等键。
    :returns: 幂等作用域。
    """

    return IdempotencyScope(
        scope_kind=_WAIT_RESOLUTION_SCOPE_KIND,
        scope_id=wait_id,
        idempotency_key=idempotency_key,
    )


def _wait_late_rejection_scope(
    wait_id: str, idempotency_key: str
) -> IdempotencyScope:
    """构造 wait late rejection 幂等作用域。

    :param wait_id: wait record id。
    :param idempotency_key: late result 幂等键。
    :returns: 幂等作用域。
    """

    return IdempotencyScope(
        scope_kind=_WAIT_LATE_REJECTION_SCOPE_KIND,
        scope_id=wait_id,
        idempotency_key=idempotency_key,
    )


def _wait_resolution_digest(wait_id: str, request: ResolveWaitRequest) -> str:
    """计算 resolve wait 语义 digest。

    :param wait_id: wait record id。
    :param request: resolve wait 请求。
    :returns: Host canonical sha256 digest。
    """

    return wait_resolution_digest(
        wait_id,
        request.idempotency_key,
        request.outcome,
    )


def _wait_late_rejection_digest(
    *,
    wait_record: WaitRecordRow,
    request: ResolveWaitRequest,
    rejection_reason: WaitLateRejectionReason,
    payload_plan: _WaitResolutionPayloadPlan,
) -> str:
    """计算 wait late rejection 语义 digest。

    :param wait_record: wait record。
    :param request: resolve wait 请求。
    :param rejection_reason: 拒绝原因。
    :param payload_plan: resolve payload 规划。
    :returns: Host canonical sha256 digest。
    """

    return sha256_digest_json(
        {
            "wait_id": wait_record.wait_id,
            "run_id": wait_record.run_id,
            "idempotency_key": request.idempotency_key,
            "source": request.source.value,
            "observed_at": request.observed_at.isoformat(),
            "wait_status": wait_record.status.value,
            "rejection_reason": rejection_reason.value,
            "outcome_kind": payload_plan.resolution_kind,
            "outcome_digest": payload_plan.outcome_digest,
            "outcome": resolve_wait_outcome_json(request.outcome),
        }
    )


def _wait_late_result_rejected_event_id(late_digest: str) -> str:
    """从 late rejection digest 派生 diagnostic event id。

    :param late_digest: late rejection digest。
    :returns: EventLog event id。
    """

    suffix = late_digest.removeprefix("sha256:")
    return f"{_EVENT_ID_WAIT_LATE_RESULT_REJECTED_PREFIX}{suffix}"


def _terminal_wait_rejection_reason(
    status: WaitRecordStatus,
) -> WaitLateRejectionReason:
    """把 terminal wait 状态映射为 late rejection reason。

    :param status: wait record 状态。
    :returns: late rejection reason。
    :raises ValueError: 非 terminal 状态传入时抛出。
    """

    if status is WaitRecordStatus.RESOLVED:
        return WaitLateRejectionReason.WAIT_ALREADY_RESOLVED
    if status is WaitRecordStatus.FAILED:
        return WaitLateRejectionReason.WAIT_ALREADY_FAILED
    if status is WaitRecordStatus.LOST:
        return WaitLateRejectionReason.WAIT_LOST
    raise ValueError("wait status is not a terminal late rejection status")


def _resolve_wait_event_plan(resolution_digest: str) -> _ResolveWaitEventPlan:
    """从 resolution digest 派生稳定事件与 row id。

    :param resolution_digest: resolve wait 语义 digest。
    :returns: 事件 id 规划。
    """

    suffix = resolution_digest.removeprefix("sha256:")
    return _ResolveWaitEventPlan(
        suffix=suffix,
        tool_fact_id=f"{_TOOL_FACT_ID_PREFIX}{suffix}",
        resume_requested_event_id=f"{_EVENT_ID_RESUME_REQUESTED_PREFIX}{suffix}",
        tool_result_event_id=f"{_EVENT_ID_WAIT_TOOL_RESULT_PREFIX}{suffix}",
        run_started_event_id=f"{_EVENT_ID_RESUME_RUN_STARTED_PREFIX}{suffix}",
        attempt_started_event_id=f"{_EVENT_ID_RESUME_ATTEMPT_STARTED_PREFIX}{suffix}",
        run_failed_event_id=f"{_EVENT_ID_WAIT_RUN_FAILED_PREFIX}{suffix}",
        run_lost_event_id=f"{_EVENT_ID_WAIT_RUN_LOST_PREFIX}{suffix}",
        resume_attempt_id=f"{_RESUME_ATTEMPT_ID_PREFIX}{suffix}",
        resume_execution_id=f"{_RESUME_EXECUTION_ID_PREFIX}{suffix}",
        resume_dispatch_record_id=f"{_RESUME_DISPATCH_ID_PREFIX}{suffix}",
    )


def _wait_resolution_payload_plan(
    request: ResolveWaitRequest,
) -> _WaitResolutionPayloadPlan:
    """构造等待结果 payload 规划。

    :param request: resolve wait 请求。
    :returns: payload 规划。
    :raises TypeError: outcome envelope 非封闭联合成员时抛出。
    """

    outcome = request.outcome
    if isinstance(outcome, ResolveWaitCompletedOutcome):
        result_json = _tool_success_json(outcome.result)
        return _WaitResolutionPayloadPlan(
            resolution_kind=_TOOL_FACT_KIND_COMPLETED,
            tool_fact_kind=_TOOL_FACT_KIND_COMPLETED,
            outcome_digest=sha256_digest_json(
                {"kind": _TOOL_FACT_KIND_COMPLETED, "result": result_json}
            ),
            payload_digest=_completed_payload_digest(outcome),
            payload_ref=outcome.payload_ref,
            provider_status_ref=None,
            result_json={
                "kind": _TOOL_FACT_KIND_COMPLETED,
                "result": result_json,
            },
        )
    if isinstance(outcome, ResolveWaitFailedOutcome):
        result_json = _tool_failure_json(outcome.result)
        return _WaitResolutionPayloadPlan(
            resolution_kind=_TOOL_FACT_KIND_FAILED,
            tool_fact_kind=_TOOL_FACT_KIND_FAILED,
            outcome_digest=sha256_digest_json(
                {"kind": _TOOL_FACT_KIND_FAILED, "result": result_json}
            ),
            payload_digest=outcome.payload_ref.payload_digest
            if outcome.payload_ref is not None
            else None,
            payload_ref=outcome.payload_ref,
            provider_status_ref=None,
            result_json={"kind": _TOOL_FACT_KIND_FAILED, "result": result_json},
        )
    if isinstance(outcome, ResolveWaitCancelledOutcome):
        result_json = _tool_cancelled_json(outcome.result)
        return _WaitResolutionPayloadPlan(
            resolution_kind=_TOOL_FACT_KIND_CANCELLED,
            tool_fact_kind=_TOOL_FACT_KIND_CANCELLED,
            outcome_digest=sha256_digest_json(
                {"kind": _TOOL_FACT_KIND_CANCELLED, "result": result_json}
            ),
            payload_digest=outcome.payload_ref.payload_digest
            if outcome.payload_ref is not None
            else None,
            payload_ref=outcome.payload_ref,
            provider_status_ref=None,
            result_json={
                "kind": _TOOL_FACT_KIND_CANCELLED,
                "result": result_json,
            },
        )
    if isinstance(outcome, ResolveWaitLostOutcome):
        result_json = _tool_lost_json(outcome)
        return _WaitResolutionPayloadPlan(
            resolution_kind=_TOOL_FACT_KIND_LOST,
            tool_fact_kind=_TOOL_FACT_KIND_LOST,
            outcome_digest=sha256_digest_json(
                {"kind": _TOOL_FACT_KIND_LOST, "result": result_json}
            ),
            payload_digest=None,
            payload_ref=None,
            provider_status_ref=outcome.provider_status_ref,
            result_json={"kind": _TOOL_FACT_KIND_LOST, "result": result_json},
        )
    raise TypeError("unsupported resolve wait outcome")


def _failed_wait_terminal_message(outcome: ResolveWaitFailedOutcome) -> str:
    """从 failed wait outcome 构造同源 Run terminal 明文说明。

    :param outcome: failed wait resolution outcome。
    :returns: 用户可读 terminal message，包含 outcome message 与可选 hint。
    :raises Exception: 不主动抛出异常。
    """

    if outcome.result.hint is None:
        return outcome.result.message
    return f"{outcome.result.message} {outcome.result.hint}"


def _completed_payload_digest(outcome: ResolveWaitCompletedOutcome) -> str:
    """计算 completed outcome payload digest。

    :param outcome: completed outcome。
    :returns: payload digest。
    """

    if outcome.payload_ref is not None:
        return outcome.payload_ref.payload_digest
    return sha256_digest_json({"value": outcome.result.value})


def _resume_requested_payload(
    *,
    wait_record: WaitRecordRow,
    request: ResolveWaitRequest,
    payload_plan: _WaitResolutionPayloadPlan,
    event_plan: _ResolveWaitEventPlan,
) -> JsonValue:
    """构造 ``RESUME_REQUESTED`` payload。

    :param wait_record: active wait record。
    :param request: resolve wait 请求。
    :param payload_plan: payload 规划。
    :param event_plan: 稳定 id 规划。
    :returns: JSON payload。
    """

    return resume_requested_payload(
        session_id=wait_record.session_id,
        run_id=wait_record.run_id,
        wait_id=wait_record.wait_id,
        source_attempt_id=wait_record.attempt_id,
        resume_attempt_id=event_plan.resume_attempt_id,
        resume_dispatch_record_id=event_plan.resume_dispatch_record_id,
        resolution_source=request.source.value,
        resolution_kind=payload_plan.resolution_kind,
        resolution_idempotency_key=request.idempotency_key,
        observed_at=request.observed_at.isoformat(),
        wait_created_event_ref=_wait_created_event_ref(wait_record),
        wait_updated_event_ref=_wait_updated_event_ref(wait_record),
    )


def _tool_result_resolution_payload(
    *,
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    wait_record: WaitRecordRow,
    request: ResolveWaitRequest,
    payload_plan: _WaitResolutionPayloadPlan,
    event_plan: _ResolveWaitEventPlan,
    wait_status_after: WaitRecordStatus,
    resume: bool,
) -> JsonValue:
    """构造 resolve wait ``TOOL_RESULT_ACCEPTED`` payload。

    :param transaction: 当前 Host transaction。
    :param event_log_store: 注入的 EventLog store。
    :param wait_record: active wait record。
    :param request: resolve wait 请求。
    :param payload_plan: payload 规划。
    :param event_plan: 稳定 id 规划。
    :param wait_status_after: 本次更新后的 wait 状态。
    :param resume: 是否创建 resume Attempt。
    :returns: JSON payload。
    """

    tool_call_requested = _wait_tool_call_requested_event(
        transaction, wait_record, event_log_store=event_log_store
    )
    request_payload = payload_object(tool_call_requested)
    accepted_evidence_envelope = _wait_resolution_evidence_envelope(
        wait_record=wait_record,
        payload_plan=payload_plan,
        event_plan=event_plan,
        tool_call_requested=tool_call_requested,
        request_payload=request_payload,
    )
    return tool_result_wait_resolution_payload(
        tool_fact_id=event_plan.tool_fact_id,
        session_id=wait_record.session_id,
        run_id=wait_record.run_id,
        attempt_id=wait_record.attempt_id,
        execution_id=wait_record.execution_id,
        iteration_id=wait_record.wait_id,
        tool_call_id=wait_record.tool_call_id,
        tool_name=wait_record.tool_name,
        tool_schema_digest=required_payload_text(
            request_payload, field_name="tool_schema_digest"
        ),
        tool_identity_digest=required_payload_text(
            request_payload, field_name="tool_identity_digest"
        ),
        normalized_arguments_digest=required_payload_text(
            request_payload, field_name="normalized_arguments_digest"
        ),
        tool_fact_kind=payload_plan.tool_fact_kind,
        outcome_digest=payload_plan.outcome_digest,
        payload_digest=payload_plan.payload_digest,
        payload_ref=payload_plan.payload_ref,
        resolution_result=payload_plan.result_json,
        wait_id=wait_record.wait_id,
        resolution_source=request.source.value,
        resolution_kind=payload_plan.resolution_kind,
        resolution_idempotency_key=request.idempotency_key,
        observed_at=request.observed_at.isoformat(),
        wait_record_status_before=wait_record.status.value,
        wait_record_status_after=wait_status_after.value,
        wait_created_event_ref=_wait_created_event_ref(wait_record),
        wait_updated_event_ref={
            "event_id": event_plan.tool_result_event_id,
            "event_sequence": None,
        },
        adapter_key=wait_record.adapter_key.value,
        external_job_ref=wait_record.external_job_ref,
        snapshot_ref=wait_record.snapshot_ref,
        provider_status_ref=payload_plan.provider_status_ref,
        resume_attempt_id=event_plan.resume_attempt_id if resume else None,
        resume_dispatch_record_id=(
            event_plan.resume_dispatch_record_id if resume else None
        ),
        accepted_evidence_envelope=accepted_evidence_envelope_to_json_value(
            accepted_evidence_envelope
        ),
        raw_tool_outcome=payload_plan.result_json,
    )


def _wait_tool_call_requested_event(
    transaction: HostTransaction,
    wait_record: WaitRecordRow,
    *,
    event_log_store: EventLogStore,
) -> EventLogRow:
    """读取 wait 对应的 canonical ``TOOL_CALL_REQUESTED`` request atom。

    :param transaction: 当前 Host transaction。
    :param wait_record: active wait record。
    :param event_log_store: 注入的 EventLog store。
    :returns: 对应 request atom row。
    :raises HostDurableError: request atom 缺失或身份不匹配时抛出。
    """

    event_id = _tool_call_requested_event_id_from_wait_id(wait_record.wait_id)
    row = event_log_store.read_event_by_id(transaction, event_id)
    if row is None:
        raise HostDurableError("wait tool call request atom is missing")
    if (
        row.event_type != _EVENT_TYPE_TOOL_CALL_REQUESTED
        or row.session_id != wait_record.session_id
        or row.run_id != wait_record.run_id
        or row.attempt_id != wait_record.attempt_id
        or row.execution_id != wait_record.execution_id
    ):
        raise HostDurableError("wait tool call request atom identity mismatch")
    payload = payload_object(row)
    if (
        required_payload_text(payload, field_name="tool_call_id")
        != wait_record.tool_call_id
        or required_payload_text(payload, field_name="tool_name")
        != wait_record.tool_name
    ):
        raise HostDurableError("wait tool call request atom tool mismatch")
    _validate_wait_request_arguments_digest(
        transaction,
        wait_record=wait_record,
        request_payload=payload,
        event_log_store=event_log_store,
    )
    return row


def _validate_wait_request_arguments_digest(
    transaction: HostTransaction,
    *,
    wait_record: WaitRecordRow,
    request_payload: Mapping[str, JsonValue],
    event_log_store: EventLogStore,
) -> None:
    """校验 wait request atom 与 awaiting accept 事实的参数 digest 同源。

    :param transaction: 当前 Host transaction。
    :param wait_record: active wait record。
    :param request_payload: ``TOOL_CALL_REQUESTED`` payload。
    :param event_log_store: 注入的 EventLog store。
    :returns: ``None``。
    :raises HostDurableError: awaiting 事实缺失、身份错误或参数 digest 不一致时抛出。
    """

    awaiting = event_log_store.read_event_by_id(transaction, wait_record.created_event_id)
    if awaiting is None:
        raise HostDurableError("wait created event is missing")
    if (
        awaiting.event_type != _EVENT_TYPE_TOOL_AWAITING
        or awaiting.session_id != wait_record.session_id
        or awaiting.run_id != wait_record.run_id
        or awaiting.attempt_id != wait_record.attempt_id
        or awaiting.execution_id != wait_record.execution_id
    ):
        raise HostDurableError("wait created event identity mismatch")
    awaiting_payload = payload_object(awaiting)
    awaiting_digest = required_payload_text(
        awaiting_payload, field_name="normalized_arguments_digest"
    )
    request_digest = required_payload_text(
        request_payload, field_name="normalized_arguments_digest"
    )
    if request_digest != awaiting_digest:
        raise HostDurableError("wait tool call request atom arguments digest mismatch")


def _wait_resolution_evidence_envelope(
    *,
    wait_record: WaitRecordRow,
    payload_plan: _WaitResolutionPayloadPlan,
    event_plan: _ResolveWaitEventPlan,
    tool_call_requested: EventLogRow,
    request_payload: Mapping[str, JsonValue],
) -> AcceptedEvidenceEnvelope:
    """构造 wait-resolution accepted result 的 evidence envelope。

    :param wait_record: active wait record。
    :param payload_plan: resolution payload 规划。
    :param event_plan: resolution event id 规划。
    :param tool_call_requested: 同一等待工具调用的 request atom。
    :param request_payload: request atom payload。
    :returns: accepted evidence envelope。
    """

    return AcceptedEvidenceEnvelope(
        evidence_id=derive_accepted_evidence_id(event_plan.tool_result_event_id),
        producer_event_ref=event_plan.tool_result_event_id,
        tool_name=wait_record.tool_name,
        tool_call_id=wait_record.tool_call_id,
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=tool_call_requested.event_id,
            normalized_arguments_digest=required_payload_text(
                request_payload, field_name="normalized_arguments_digest"
            ),
            semantic_input_digest=required_payload_text(
                request_payload, field_name="semantic_input_digest"
            ),
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=(
                payload_plan.payload_ref.payload_ref
                if payload_plan.payload_ref is not None
                else None
            ),
            payload_digest=payload_plan.payload_digest,
            outcome_digest=payload_plan.outcome_digest,
            truncation_applied=False,
        ),
        source_refs=(),
        locator_refs=(),
    )


def _tool_call_requested_event_id_from_wait_id(wait_id: str) -> str:
    """从 Host wait id 派生 awaiting request atom event id。

    :param wait_id: ``wait-<awaiting-accept-digest>`` 形式的 wait id。
    :returns: request atom event id。
    :raises HostDurableError: wait id 非 awaiting accept 派生形态时抛出。
    """

    prefix = "wait-"
    if not wait_id.startswith(prefix) or len(wait_id) <= len(prefix):
        raise HostDurableError("wait id cannot derive tool call request atom")
    return f"{_EVENT_ID_TOOL_CALL_REQUESTED_PREFIX}{wait_id.removeprefix(prefix)}"


def _wait_late_result_rejected_event_request(
    *,
    event_id: str,
    wait_record: WaitRecordRow,
    request: ResolveWaitRequest,
    rejection_reason: WaitLateRejectionReason,
    payload_plan: _WaitResolutionPayloadPlan,
) -> EventLogAppendRequest:
    """构造 ``WAIT_LATE_RESULT_REJECTED`` diagnostic append request。

    :param event_id: diagnostic event id。
    :param wait_record: 被拒绝结果对应的 wait record。
    :param request: resolve wait 请求。
    :param rejection_reason: 拒绝原因。
    :param payload_plan: 等待结果 payload 规划。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.DIAGNOSTIC,
        session_id=wait_record.session_id,
        run_id=wait_record.run_id,
        attempt_id=wait_record.attempt_id,
        execution_id=wait_record.execution_id,
        event_type=_EVENT_TYPE_WAIT_LATE_RESULT_REJECTED,
        occurred_at=request.observed_at,
        actor=request.context.actor,
        source=_WAIT_RESOLUTION_SOURCE,
        client_request_id=None,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason={"reason_code": rejection_reason.value},
        payload_json=wait_late_result_rejected_payload(
            wait_id=wait_record.wait_id,
            run_id=wait_record.run_id,
            attempt_id=wait_record.attempt_id,
            tool_call_id=wait_record.tool_call_id,
            tool_name=wait_record.tool_name,
            source=request.source.value,
            idempotency_key=request.idempotency_key,
            observed_at=request.observed_at.isoformat(),
            wait_status=wait_record.status.value,
            rejection_reason=rejection_reason.value,
            outcome_kind=payload_plan.resolution_kind,
            outcome_digest=payload_plan.outcome_digest,
            payload_ref=payload_plan.payload_ref,
            provider_status_ref=payload_plan.provider_status_ref,
            external_job_ref=wait_record.external_job_ref,
            adapter_key=wait_record.adapter_key.value,
        ),
        payload_ref=None,
        payload_digest=None,
    )


def _resolve_wait_result_from_existing(
    transaction: HostTransaction, wait_record: WaitRecordRow
) -> ResolveWaitResult:
    """从 durable truth 重建 resolve wait 幂等重放结果。

    :param transaction: 当前 Host transaction。
    :param wait_record: 已终态 wait record。
    :returns: resolve wait 结果。
    :raises HostApiError: Run row 缺失时抛出。
    """

    run = read_run_by_id(transaction, wait_record.run_id)
    if run is None:
        raise HostApiError(
            code=HostApiErrorCode.NOT_FOUND,
            message="wait owner run not found",
            retryable=False,
        )
    dispatch_record = (
        read_dispatch_record_by_attempt_id(transaction, run.current_attempt_id)
        if run.status is RunStatus.RUNNING and run.current_attempt_id is not None
        else None
    )
    return ResolveWaitResult(
        run=run,
        dispatch_record=dispatch_record,
        idempotent_replay=True,
    )


def _payload_ref_text(payload_ref: HostPayloadRef | None) -> str | None:
    """读取 EventLog row 的 payload_ref 文本。

    :param payload_ref: payload 引用或 ``None``。
    :returns: payload_ref 文本或 ``None``。
    """

    if payload_ref is None:
        return None
    return payload_ref.payload_ref


def _event_payload_digest(payload_plan: _WaitResolutionPayloadPlan) -> str | None:
    """读取 EventLog row 的 payload_digest 文本。

    :param payload_plan: payload 规划。
    :returns: payload digest 或 ``None``。
    """

    if payload_plan.payload_ref is None:
        return None
    return payload_plan.payload_ref.payload_digest


def _wait_created_event_ref(wait_record: WaitRecordRow) -> Mapping[str, JsonValue]:
    """构造 wait created event ref JSON。

    :param wait_record: wait record row。
    :returns: JSON mapping。
    """

    return {
        "event_id": wait_record.created_event_id,
        "event_sequence": wait_record.created_event_sequence,
    }


def _wait_updated_event_ref(wait_record: WaitRecordRow) -> Mapping[str, JsonValue]:
    """构造 wait current updated event ref JSON。

    :param wait_record: wait record row。
    :returns: JSON mapping。
    """

    return {
        "event_id": wait_record.updated_event_id,
        "event_sequence": wait_record.updated_event_sequence,
    }


def _log_tool_awaiting_accept_result(
    candidate: ToolAwaitingAcceptCandidate, result: ToolAwaitingAcceptResult
) -> None:
    """记录工具等待 accept barrier 的有界结果。

    :param candidate: awaiting candidate。
    :param result: awaiting accept 结果。
    :returns: ``None``。
    """

    if isinstance(result, ToolAwaitingAcceptedAck):
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            (
                "host.waiting.accept_tool_awaiting.committed "
                "session_id=%s run_id=%s attempt_id=%s execution_id=%s "
                "tool_call_id=%s tool_name=%s adapter_key=%s wait_id=%s "
                "accepted_event_count=%s"
            ),
            candidate.session_id,
            candidate.run_id,
            candidate.attempt_id,
            candidate.execution_id,
            candidate.tool_call_id,
            candidate.tool_name,
            candidate.binding.adapter_key.value,
            result.wait_id,
            len(result.accepted_event_refs),
        )
        return
    if isinstance(result, ToolAwaitingRejectedAck):
        _LOGGER.debug(
            (
                "host.waiting.accept_tool_awaiting.rejected "
                "session_id=%s run_id=%s attempt_id=%s execution_id=%s "
                "tool_call_id=%s tool_name=%s adapter_key=%s reason=%s "
                "retryable=%s"
            ),
            candidate.session_id,
            candidate.run_id,
            candidate.attempt_id,
            candidate.execution_id,
            candidate.tool_call_id,
            candidate.tool_name,
            candidate.binding.adapter_key.value,
            result.reason_code.value,
            result.retryable,
        )
        return
    _LOGGER.debug(
        (
            "host.waiting.accept_tool_awaiting.timed_out "
            "session_id=%s run_id=%s attempt_id=%s execution_id=%s "
            "tool_call_id=%s tool_name=%s adapter_key=%s attempt_count=%s "
            "last_error_code=%s"
        ),
        candidate.session_id,
        candidate.run_id,
        candidate.attempt_id,
        candidate.execution_id,
        candidate.tool_call_id,
        candidate.tool_name,
        candidate.binding.adapter_key.value,
        result.attempt_count,
        result.last_error_code,
    )


def _accept_idempotency_scope(
    candidate: ToolAwaitingAcceptCandidate,
) -> IdempotencyScope:
    """构造 awaiting accept 幂等作用域。

    :param candidate: awaiting candidate。
    :returns: 幂等作用域。
    """

    return IdempotencyScope(
        scope_kind=_TOOL_AWAITING_ACCEPT_SCOPE_KIND,
        scope_id=f"{candidate.attempt_id}:{candidate.tool_call_id}",
        idempotency_key=candidate.accept_idempotency_key,
    )


def _event_plan(candidate: ToolAwaitingAcceptCandidate) -> _AwaitingEventPlan:
    """为 awaiting candidate 派生稳定事件 id。

    :param candidate: awaiting candidate。
    :returns: 事件 id 规划。
    """

    digest = candidate.semantic_input_digest.removeprefix("sha256:")
    return _AwaitingEventPlan(
        tool_call_requested_id=f"{_EVENT_ID_TOOL_CALL_REQUESTED_PREFIX}{digest}",
        tool_awaiting_id=f"{_EVENT_ID_TOOL_AWAITING_PREFIX}{digest}",
        run_waiting_id=f"{_EVENT_ID_RUN_WAITING_PREFIX}{digest}",
        attempt_suspended_id=f"{_EVENT_ID_ATTEMPT_SUSPENDED_PREFIX}{digest}",
    )


def _invalid_awaiting_precondition(
    transaction: HostTransaction, candidate: ToolAwaitingAcceptCandidate
) -> ToolAwaitingAcceptRejectReason | None:
    """检查 awaiting accept durable precondition。

    :param transaction: 当前 Host transaction。
    :param candidate: awaiting candidate。
    :returns: 拒绝原因；可接受时为 ``None``。
    """

    run = read_run_by_id(transaction, candidate.run_id)
    attempt = read_attempt_by_id(transaction, candidate.attempt_id)
    dispatch_record = read_dispatch_record_by_attempt_id(
        transaction, candidate.attempt_id
    )
    if run is None or attempt is None or dispatch_record is None:
        return ToolAwaitingAcceptRejectReason.INVALID_ATTEMPT
    if (
        run.session_id != candidate.session_id
        or run.current_attempt_id != candidate.attempt_id
        or attempt.run_id != candidate.run_id
        or dispatch_record.run_id != candidate.run_id
    ):
        return ToolAwaitingAcceptRejectReason.INVALID_ATTEMPT
    if (
        attempt.execution_id != candidate.execution_id
        or dispatch_record.execution_id != candidate.execution_id
    ):
        return ToolAwaitingAcceptRejectReason.STALE_EXECUTION
    if (
        run.status is not RunStatus.RUNNING
        or attempt.status is not AttemptStatus.RUNNING
        or dispatch_record.status is not DispatchRecordStatus.DISPATCHING
        or dispatch_record.worker_accept_event_id is None
    ):
        return ToolAwaitingAcceptRejectReason.INVALID_ATTEMPT
    return None


def _tool_call_requested_event_request(
    candidate: ToolAwaitingAcceptCandidate,
    event_id: str,
    occurred_at: datetime,
) -> EventLogAppendRequest:
    """构造 awaiting 工具调用的 ``TOOL_CALL_REQUESTED`` append request。

    :param candidate: awaiting candidate。
    :param event_id: 事件 id。
    :param occurred_at: 事件发生时间。
    :returns: EventLog append request。
    """

    safe_arguments = llm_safe_replay_arguments(candidate.accepted_arguments)
    arguments_json = _accepted_arguments_json(safe_arguments)
    arguments_payload_digest = sha256_digest_json(arguments_json)
    semantic_query_text = _awaiting_semantic_query_text(
        tool_name=candidate.tool_name,
        safe_arguments=safe_arguments,
    )
    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=candidate.session_id,
        run_id=candidate.run_id,
        attempt_id=candidate.attempt_id,
        execution_id=candidate.execution_id,
        event_type=_EVENT_TYPE_TOOL_CALL_REQUESTED,
        occurred_at=occurred_at,
        actor=_AWAITING_ACCEPT_ACTOR,
        source=_AWAITING_ACCEPT_SOURCE,
        client_request_id=None,
        idempotency_key=candidate.accept_idempotency_key,
        policy_decision=None,
        reason={"reason": "tool_call_requested"},
        payload_json={
            "session_id": candidate.session_id,
            "run_id": candidate.run_id,
            "attempt_id": candidate.attempt_id,
            "execution_id": candidate.execution_id,
            "iteration_id": candidate.iteration_id,
            "tool_call_id": candidate.tool_call_id,
            "tool_name": candidate.tool_name,
            "tool_schema_digest": candidate.tool_schema_digest,
            "tool_identity_digest": candidate.tool_identity_digest,
            "normalized_arguments_digest": candidate.normalized_arguments_digest,
            "arguments_json_size_bytes": _payload_size_bytes(arguments_json),
            "arguments_storage_kind": TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
            "arguments_inline_json": arguments_json,
            "arguments_payload_ref": None,
            "arguments_payload_digest": arguments_payload_digest,
            "tool_fact_kind": "awaiting",
            "accept_idempotency_key": candidate.accept_idempotency_key,
            "semantic_input_digest": candidate.semantic_input_digest,
            "semantic_query_storage_kind": TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT,
            "semantic_query_text": semantic_query_text,
            "semantic_query_payload_ref": None,
            "semantic_query_digest": sha256_digest_json(
                {"semantic_query_text": semantic_query_text}
            ),
        },
        payload_ref=None,
        payload_digest=None,
    )


def _accepted_arguments_json(arguments: Mapping[str, JsonValue]) -> Mapping[str, JsonValue]:
    """构造 request atom 使用的 accepted arguments canonical JSON。

    :param arguments: 已接受参数。
    :returns: canonical arguments JSON object。
    """

    return {"arguments": dict(arguments)}


def _awaiting_semantic_query_text(
    *, tool_name: str, safe_arguments: Mapping[str, JsonValue]
) -> str:
    """构造 awaiting 工具调用的业务可读请求摘要。

    :param tool_name: 工具名。
    :param safe_arguments: 已脱敏的工具参数投影。
    :returns: 不含 Host 等待治理概念的 LLM-facing query 文本。
    """

    return f"工具 {tool_name} 请求参数：{canonical_json_dumps(dict(safe_arguments))}"


def _payload_size_bytes(payload: Mapping[str, JsonValue]) -> int:
    """计算 canonical JSON payload 的 UTF-8 字节数。

    :param payload: JSON payload。
    :returns: 字节数。
    """

    return len(canonical_json_dumps(payload).encode("utf-8"))


def _tool_awaiting_event_request(
    candidate: ToolAwaitingAcceptCandidate, event_id: str, occurred_at: datetime
) -> EventLogAppendRequest:
    """构造 ``TOOL_AWAITING`` append request。

    :param candidate: awaiting candidate。
    :param event_id: 事件 id。
    :param occurred_at: 事件发生时间。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=candidate.session_id,
        run_id=candidate.run_id,
        attempt_id=candidate.attempt_id,
        execution_id=candidate.execution_id,
        event_type=_EVENT_TYPE_TOOL_AWAITING,
        occurred_at=occurred_at,
        actor=_AWAITING_ACCEPT_ACTOR,
        source=_AWAITING_ACCEPT_SOURCE,
        client_request_id=None,
        idempotency_key=candidate.accept_idempotency_key,
        policy_decision=None,
        reason={"reason": "tool_awaiting"},
        payload_json=tool_awaiting_payload(
            session_id=candidate.session_id,
            run_id=candidate.run_id,
            attempt_id=candidate.attempt_id,
            execution_id=candidate.execution_id,
            iteration_id=candidate.iteration_id,
            wait_id=candidate.wait_id,
            tool_call_id=candidate.tool_call_id,
            tool_name=candidate.tool_name,
            normalized_arguments_digest=candidate.normalized_arguments_digest,
            accepted_arguments=candidate.accepted_arguments,
            await_spec=candidate.await_spec,
            adapter_key=candidate.binding.adapter_key.value,
            resume_policy=candidate.binding.resume_policy.value,
            snapshot_ref=candidate.snapshot_ref,
            external_job_ref=candidate.external_job_ref,
            accept_idempotency_key=candidate.accept_idempotency_key,
            semantic_input_digest=candidate.semantic_input_digest,
        ),
        payload_ref=None,
        payload_digest=None,
    )


def _run_waiting_event_request(
    candidate: ToolAwaitingAcceptCandidate,
    event_id: str,
    occurred_at: datetime,
    tool_awaiting: EventLogRow,
) -> EventLogAppendRequest:
    """构造 ``RUN_WAITING`` append request。

    :param candidate: awaiting candidate。
    :param event_id: 事件 id。
    :param occurred_at: 事件发生时间。
    :param tool_awaiting: 已写入的 ``TOOL_AWAITING`` row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=candidate.session_id,
        run_id=candidate.run_id,
        attempt_id=candidate.attempt_id,
        execution_id=candidate.execution_id,
        event_type=_EVENT_TYPE_RUN_WAITING,
        occurred_at=occurred_at,
        actor=_AWAITING_ACCEPT_ACTOR,
        source=_AWAITING_ACCEPT_SOURCE,
        client_request_id=None,
        idempotency_key=candidate.accept_idempotency_key,
        policy_decision=None,
        reason={"reason": "tool_awaiting"},
        payload_json=run_waiting_payload(
            session_id=candidate.session_id,
            run_id=candidate.run_id,
            attempt_id=candidate.attempt_id,
            wait_id=candidate.wait_id,
            tool_awaiting_event_ref=_event_ref_json(tool_awaiting),
        ),
        payload_ref=None,
        payload_digest=None,
    )


def _attempt_suspended_event_request(
    candidate: ToolAwaitingAcceptCandidate,
    event_id: str,
    occurred_at: datetime,
    run_waiting: EventLogRow,
) -> EventLogAppendRequest:
    """构造 ``ATTEMPT_SUSPENDED`` append request。

    :param candidate: awaiting candidate。
    :param event_id: 事件 id。
    :param occurred_at: 事件发生时间。
    :param run_waiting: 已写入的 ``RUN_WAITING`` row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=candidate.session_id,
        run_id=candidate.run_id,
        attempt_id=candidate.attempt_id,
        execution_id=candidate.execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_SUSPENDED,
        occurred_at=occurred_at,
        actor=_AWAITING_ACCEPT_ACTOR,
        source=_AWAITING_ACCEPT_SOURCE,
        client_request_id=None,
        idempotency_key=candidate.accept_idempotency_key,
        policy_decision=None,
        reason={"reason": "tool_awaiting"},
        payload_json=attempt_suspended_payload(
            session_id=candidate.session_id,
            run_id=candidate.run_id,
            attempt_id=candidate.attempt_id,
            execution_id=candidate.execution_id,
            wait_id=candidate.wait_id,
            tool_call_id=candidate.tool_call_id,
            run_waiting_event_ref=_event_ref_json(run_waiting),
        ),
        payload_ref=None,
        payload_digest=None,
    )


def _wait_record_row(
    *,
    candidate: ToolAwaitingAcceptCandidate,
    created_event: EventLogRow,
    updated_event: EventLogRow,
    timestamp: str,
) -> WaitRecordRow:
    """构造待插入的 wait record row。

    :param candidate: awaiting candidate。
    :param created_event: ``TOOL_AWAITING`` row。
    :param updated_event: ``ATTEMPT_SUSPENDED`` row。
    :param timestamp: UTC timestamp 文本。
    :returns: wait record row。
    """

    deadline_at = (
        format_utc_timestamp(candidate.await_spec.deadline)
        if candidate.await_spec.deadline is not None
        else None
    )
    return WaitRecordRow(
        wait_id=candidate.wait_id,
        session_id=candidate.session_id,
        run_id=candidate.run_id,
        attempt_id=candidate.attempt_id,
        execution_id=candidate.execution_id,
        tool_call_id=candidate.tool_call_id,
        tool_name=candidate.tool_name,
        adapter_key=candidate.binding.adapter_key,
        await_kind=candidate.await_spec.await_kind.value,
        resume_policy=candidate.binding.resume_policy,
        resume_token=candidate.await_spec.resume_token,
        snapshot_ref=candidate.snapshot_ref,
        external_job_ref=candidate.external_job_ref,
        accept_idempotency_key=candidate.accept_idempotency_key,
        resolve_idempotency_key=None,
        resolve_semantic_digest=None,
        deadline_at=deadline_at,
        expires_at=None,
        status=WaitRecordStatus.WAITING,
        created_event_id=created_event.event_id,
        created_event_sequence=created_event.event_sequence,
        updated_event_id=updated_event.event_id,
        updated_event_sequence=updated_event.event_sequence,
        created_at=timestamp,
        updated_at=timestamp,
        terminal_at=None,
    )


def _resolve_created_event_ref(result: ResolveWaitResult) -> tuple[str, int]:
    """返回 resolve wait 幂等记录应引用的创建事件。

    :param result: resolve wait durable 结果。
    :returns: ``(event_id, event_sequence)``。
    :raises HostApiError: resume 或 terminal 路径缺失对应事件引用时抛出。
    """

    if result.dispatch_record is not None:
        event_id = result.run.started_event_id
        event_sequence = result.run.started_event_sequence
        missing_message = "resolve wait resume run is missing started event ref"
    else:
        event_id = result.run.terminal_event_id
        event_sequence = result.run.terminal_event_sequence
        missing_message = "resolve wait terminal run is missing terminal event ref"
    if event_id is None or event_sequence is None:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message=missing_message,
            retryable=False,
        )
    return event_id, event_sequence


def _accepted_ack_from_existing(
    event_log_store: EventLogStore,
    transaction: HostTransaction,
    candidate: ToolAwaitingAcceptCandidate,
    record: IdempotencyRecord,
) -> ToolAwaitingAcceptedAck:
    """从既有幂等记录重建 accepted ack。

    :param event_log_store: EventLog primitive。
    :param transaction: 当前 Host transaction。
    :param candidate: awaiting candidate。
    :param record: 既有幂等记录。
    :returns: accepted ack。
    :raises RuntimeError: 幂等记录指向的事实缺失时抛出。
    """

    plan = _event_plan(candidate)
    tool_call_requested = event_log_store.read_event_by_id(
        transaction, plan.tool_call_requested_id
    )
    tool_awaiting = event_log_store.read_event_by_id(
        transaction, plan.tool_awaiting_id
    )
    run_waiting = event_log_store.read_event_by_id(transaction, plan.run_waiting_id)
    attempt_suspended = event_log_store.read_event_by_id(
        transaction, plan.attempt_suspended_id
    )
    if (
        tool_call_requested is None
        or tool_awaiting is None
        or run_waiting is None
        or attempt_suspended is None
    ):
        raise RuntimeError("accepted tool awaiting event is missing")
    if read_wait_record_by_id(transaction, candidate.wait_id) is None:
        raise RuntimeError("accepted tool awaiting wait record is missing")
    return _accepted_ack_from_rows(
        candidate=candidate,
        tool_call_requested=tool_call_requested,
        tool_awaiting=tool_awaiting,
        run_waiting=run_waiting,
        attempt_suspended=attempt_suspended,
        idempotency_record=record,
    )


def _accepted_ack_from_rows(
    *,
    candidate: ToolAwaitingAcceptCandidate,
    tool_call_requested: EventLogRow,
    tool_awaiting: EventLogRow,
    run_waiting: EventLogRow,
    attempt_suspended: EventLogRow,
    idempotency_record: IdempotencyRecord,
) -> ToolAwaitingAcceptedAck:
    """从 EventLog rows 组装 accepted ack。

    :param candidate: awaiting candidate。
    :param tool_call_requested: ``TOOL_CALL_REQUESTED`` row。
    :param tool_awaiting: ``TOOL_AWAITING`` row。
    :param run_waiting: ``RUN_WAITING`` row。
    :param attempt_suspended: ``ATTEMPT_SUSPENDED`` row。
    :param idempotency_record: 幂等记录。
    :returns: accepted ack。
    """

    tool_call_requested_ref = _event_ref_from_row(tool_call_requested)
    tool_awaiting_ref = _event_ref_from_row(tool_awaiting)
    run_waiting_ref = _event_ref_from_row(run_waiting)
    attempt_suspended_ref = _event_ref_from_row(attempt_suspended)
    return ToolAwaitingAcceptedAck(
        accepted_event_refs=(
            tool_call_requested_ref,
            tool_awaiting_ref,
            run_waiting_ref,
            attempt_suspended_ref,
        ),
        wait_id=candidate.wait_id,
        tool_awaiting_event_ref=tool_awaiting_ref,
        run_waiting_event_ref=run_waiting_ref,
        attempt_suspended_event_ref=attempt_suspended_ref,
        result_digest=candidate.semantic_input_digest,
        idempotency_record_ref=(
            f"{idempotency_record.scope_kind}:{idempotency_record.scope_id}:"
            f"{idempotency_record.idempotency_key}"
        ),
    )


def _event_ref_from_row(row: EventLogRow) -> ToolAwaitingEventRef:
    """从 EventLog row 构造 awaiting event ref。

    :param row: EventLog row。
    :returns: awaiting event ref。
    """

    return ToolAwaitingEventRef(
        event_id=row.event_id, event_sequence=row.event_sequence
    )


def _event_ref_json(row: EventLogRow) -> dict[str, int | str]:
    """把 EventLog row 引用投影为 JSON 兼容 dict。

    :param row: EventLog row。
    :returns: event ref dict。
    """

    return {"event_id": row.event_id, "event_sequence": row.event_sequence}


def build_tool_awaiting_accept_identity_digest(
    *,
    session_id: str,
    run_id: str,
    attempt_id: str,
    execution_id: str,
    iteration_id: str,
    tool_call_id: str,
    tool_name: str,
    await_spec: ToolAwaitSpec,
    adapter_key: str,
    resume_policy: str,
    external_job_id: str | None,
    snapshot_id: str | None,
    normalized_arguments_digest: str,
) -> str:
    """计算 awaiting accept identity digest。

    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :param iteration_id: Engine iteration id。
    :param tool_call_id: 工具调用 id。
    :param tool_name: 工具名。
    :param await_spec: 工具等待规约。
    :param adapter_key: Host adapter key。
    :param resume_policy: resume policy 文本。
    :param external_job_id: 外部 job id；无则为 ``None``。
    :param snapshot_id: 快照 id；无则为 ``None``。
    :param normalized_arguments_digest: 规范化参数 digest。
    :returns: canonical sha256 digest。
    """

    return sha256_digest_json(
        {
            "session_id": session_id,
            "run_id": run_id,
            "attempt_id": attempt_id,
            "execution_id": execution_id,
            "iteration_id": iteration_id,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "await_kind": await_spec.await_kind.value,
            "deadline": (
                await_spec.deadline.isoformat()
                if await_spec.deadline is not None
                else None
            ),
            "resume_token": await_spec.resume_token,
            "adapter_key": adapter_key,
            "resume_policy": resume_policy,
            "external_job_id": external_job_id,
            "snapshot_id": snapshot_id,
            "normalized_arguments_digest": normalized_arguments_digest,
        }
    )


__all__ = [
    "DefaultHostToolAwaitingAcceptPort",
    "HostToolAwaitingAcceptPort",
    "ToolAwaitingAcceptCandidate",
    "ToolAwaitingAcceptRejectReason",
    "ToolAwaitingAcceptResult",
    "ToolAwaitingAcceptTimedOut",
    "ToolAwaitingAcceptedAck",
    "ToolAwaitingEventRef",
    "ToolAwaitingRejectedAck",
    "build_tool_awaiting_accept_identity_digest",
]
