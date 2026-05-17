"""Host-owned EngineEvent ingest 与 terminal closeout。

本模块把 Engine 公共 ``EngineEvent`` 包装在 Host-owned envelope 中进入
durable EventLog，并在 Phase 5 范围内完成 preview、projection signal、
diagnostic 与 terminal canonical facts 的映射。Engine contract 不携带
Host Attempt identity；attempt / execution / dispatch identity 只来自
本模块的 envelope 与 durable state 校验。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

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
from dayu.host.admission import AdmissionWakeupPort, NoopAdmissionWakeupPort
from dayu.host.api import AttemptStatus, RunStatus
from dayu.host.durable.codec import (
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
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.payload import (
    PayloadDescriptor,
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.run_transition import (
    ActiveCancelCloseoutInput,
    TerminalCloseoutInput,
    active_cancel_closeout_in_transaction,
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
from dayu.host._event_payload import (
    payload_object as _payload_object,
)
from dayu.host._event_payload import (
    required_payload_text as _required_payload_text,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner

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
_EVENT_TYPE_TOOL_AWAITING = "TOOL_AWAITING"
_EVENT_TYPE_RUN_WAITING = "RUN_WAITING"
_EVENT_TYPE_ATTEMPT_SUSPENDED = "ATTEMPT_SUSPENDED"
_REASON_FINAL_ANSWER = "final_answer"
_REASON_UNSUPPORTED_RECOVERY_POLICY = "unsupported_recovery_policy"
_REASON_UNSUPPORTED_WAITING_PATH = "unsupported_waiting_path"
_REASON_STREAM_ENDED_WITHOUT_TERMINAL = "stream_ended_without_terminal"
_REASON_WORKER_LOST_BEFORE_TERMINAL = "worker_lost_before_terminal"
_REASON_STALE_EXECUTION_ID = "stale_execution_id"
_REASON_TERMINAL_ALREADY_CLOSED = "terminal_already_closed"
_REASON_WAITING_EVENT_CONFIRMATION = "waiting_event_confirmation"
_REASON_WAITING_EVENT_WITHOUT_HOST_ACCEPTED_REFS = (
    "waiting_event_without_host_accepted_refs"
)
_REASON_RUN_CANCELLED_INVALID_ACTIVE_CANCEL_PAYLOAD = (
    "run_cancelled_invalid_active_cancel_payload"
)
_OWNER_PHASE7 = "phase7"
_OWNER_PHASE10 = "phase10"


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
    :param terminal_closeout: 本次是否尝试 terminal closeout。
    :param promotion_triggered: terminal closeout 成功后是否触发 queue promotion wakeup。
    :param reason: 诊断 reason；无时为 ``None``。
    """

    status: EngineIngestStatus
    events: tuple[EventLogRow, ...]
    terminal_closeout: bool
    promotion_triggered: bool
    reason: str | None


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


class EngineEventIngestor:
    """Host-owned EngineEvent ingest 服务。"""

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        event_log_store: EventLogStore | None = None,
        payload_store: PayloadStore | None = None,
        wakeup_port: AdmissionWakeupPort | None = None,
    ) -> None:
        """初始化 EngineEvent ingestor。

        :param transaction_runner: Host durable transaction runner。
        :param event_log_store: EventLog primitive。
        :param payload_store: payload descriptor primitive。
        :param wakeup_port: terminal closeout 后的 queue promotion wakeup 端口。
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

    def ingest(self, candidate: EngineEventCandidate) -> EngineIngestResult:
        """接收一个 EngineEvent candidate 并写入 Host durable facts。

        :param candidate: 待 ingest 的 EngineEvent candidate。
        :returns: ingest 结果。
        :raises ValueError: candidate envelope、时间戳或 event index 非法时抛出。
        :raises HostDurableError: durable 写入或状态 CAS 失败时抛出。
        """

        _validate_candidate_shape(candidate)

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
            return self._ingest_validated(transaction, context)

        result = self._transaction_runner.run_write(_operation)
        return self._with_terminal_promotion_retry(
            result,
            session_id=candidate.envelope.session_id,
        )

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
    ) -> EngineIngestResult:
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
            diagnostic = self._append_diagnostic_event(
                transaction,
                context=context,
                event_type=_EVENT_TYPE_ENGINE_EVENT_DIAGNOSTIC,
                reason=_REASON_UNSUPPORTED_RECOVERY_POLICY,
                payload=_context_compaction_payload(context, event.data),
                sub_index=0,
            )
            closeout = self._close_terminal(
                transaction,
                context,
                _unsupported_recovery_plan(event.data.provider_request_id),
                sub_index_offset=1,
            )
            return _merge_diagnostic_and_closeout(diagnostic, closeout)
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
        return self._with_terminal_promotion_retry(
            result,
            session_id=envelope.session_id,
        )

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
                    "attempt_id": context.attempt.attempt_id,
                    "execution_id": context.attempt.execution_id,
                    "iteration_id": data.iteration_id,
                    "prompt_tokens": data.prompt_tokens,
                    "completion_tokens": data.completion_tokens,
                    "total_tokens": data.total_tokens,
                },
                reason=None,
            ),
        ).row

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
    ) -> EngineIngestResult:
        """追加 rejected diagnostic。

        :param transaction: 当前 Host transaction。
        :param candidate: 被拒绝的 candidate。
        :param reason: 拒绝原因。
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
            "recoverable": data.recoverable,
        },
        finish_reason=None,
        filtered=None,
        degraded=None,
        error_code=data.error_code,
        message=data.message,
        provider_request_id=data.provider_request_id,
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
    recoverable: bool,
    unsupported_later_owner: str | None,
) -> _TerminalPlan:
    """构造 failed terminal plan。

    :param reason: terminal reason。
    :param error_code: error code。
    :param message: error message。
    :param provider_request_id: provider request id。
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
            "recoverable": recoverable,
        },
        finish_reason=None,
        filtered=None,
        degraded=None,
        error_code=error_code,
        message=message,
        provider_request_id=provider_request_id,
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
    )


__all__ = [
    "EngineEventCandidate",
    "EngineEventIngestor",
    "EngineIngestResult",
    "EngineIngestStatus",
    "LocalEngineEnvelope",
]
