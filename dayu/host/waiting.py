"""Host Tool Awaiting accept path。

本模块实现 ToolRuntime 提交 ``ToolAwaitingOutcome`` 后的 Host canonical
等待接收路径：在单个 durable transaction 内写入 awaiting facts、创建
wait record，并把 Run / Attempt 推进到 ``WAITING`` / ``SUSPENDED``。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from dayu.contracts.tool_await import ToolAwaitSpec
from dayu.host._event_payload import (
    attempt_suspended_payload,
    run_waiting_payload,
    tool_awaiting_payload,
)
from dayu.host.api import AttemptStatus, RunStatus
from dayu.host.durable.codec import format_utc_timestamp, sha256_digest_json
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
    IdempotencyScope,
    IdempotencyStore,
)
from dayu.host.durable.state import (
    DispatchRecordStatus,
    ExternalJobRef,
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
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.wait_adapter import WaitAdapterBinding

_TOOL_AWAITING_ACCEPT_SCOPE_KIND = "tool_awaiting_accept"
_TOOL_AWAITING_ACCEPT_RESULT_KIND = "tool_awaiting_accept_ack"
_EVENT_TYPE_TOOL_AWAITING = "TOOL_AWAITING"
_EVENT_TYPE_RUN_WAITING = "RUN_WAITING"
_EVENT_TYPE_ATTEMPT_SUSPENDED = "ATTEMPT_SUSPENDED"
_AWAITING_ACCEPT_ACTOR = "host.tool_runtime"
_AWAITING_ACCEPT_SOURCE = "host.tool_runtime.awaiting_accept"
_EVENT_ID_TOOL_AWAITING_PREFIX = "event-tool-awaiting-"
_EVENT_ID_RUN_WAITING_PREFIX = "event-run-waiting-"
_EVENT_ID_ATTEMPT_SUSPENDED_PREFIX = "event-attempt-suspended-"


class _AwaitingAcceptStateConflictError(HostDurableError):
    """awaiting accept 已通过 precondition 后的状态 CAS 冲突。"""


class ToolAwaitingAcceptRejectReason(StrEnum):
    """Host awaiting accept 拒绝原因。"""

    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    INVALID_ATTEMPT = "invalid_attempt"
    STALE_EXECUTION = "stale_execution"
    CAS_CONFLICT = "cas_conflict"


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
            if not value.startswith("sha256:") or len(value) != 71:
                raise ValueError(f"{field_name} must be sha256 digest")
        if self.binding.resume_policy is WaitResumePolicy.POLL:
            if self.external_job_ref is None:
                raise ValueError("poll awaiting candidate requires external_job_ref")
        if (
            self.external_job_ref is not None
            and self.external_job_ref.adapter_key != self.binding.adapter_key
        ):
            raise ValueError("external_job_ref adapter_key must match binding")


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
    """

    attempt_count: int
    last_error_code: str | None


ToolAwaitingAcceptResult = (
    ToolAwaitingAcceptedAck | ToolAwaitingRejectedAck | ToolAwaitingAcceptTimedOut
)
"""awaiting accept 结果封闭联合。"""


class HostToolAwaitingAcceptPort:
    """工具 awaiting canonical fact accept barrier 端口协议。"""

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
            return self._transaction_runner.run_write(
                lambda transaction: self._accept_in_transaction(
                    transaction, candidate
                )
            )
        except HostIdempotencyConflictError:
            return ToolAwaitingRejectedAck(
                reason_code=ToolAwaitingAcceptRejectReason.IDEMPOTENCY_CONFLICT,
                message="tool awaiting accept idempotency conflict",
                retryable=False,
            )
        except _AwaitingAcceptStateConflictError:
            return ToolAwaitingRejectedAck(
                reason_code=ToolAwaitingAcceptRejectReason.CAS_CONFLICT,
                message="tool awaiting accept state CAS failed",
                retryable=False,
            )

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
            tool_awaiting=tool_awaiting,
            run_waiting=run_waiting,
            attempt_suspended=attempt_suspended,
            idempotency_record=record,
        )


@dataclass(frozen=True, slots=True)
class _AwaitingEventPlan:
    """awaiting accept path 的稳定事件 id 规划。"""

    tool_awaiting_id: str
    run_waiting_id: str
    attempt_suspended_id: str


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
    tool_awaiting = event_log_store.read_event_by_id(
        transaction, plan.tool_awaiting_id
    )
    run_waiting = event_log_store.read_event_by_id(transaction, plan.run_waiting_id)
    attempt_suspended = event_log_store.read_event_by_id(
        transaction, plan.attempt_suspended_id
    )
    if tool_awaiting is None or run_waiting is None or attempt_suspended is None:
        raise RuntimeError("accepted tool awaiting event is missing")
    if read_wait_record_by_id(transaction, candidate.wait_id) is None:
        raise RuntimeError("accepted tool awaiting wait record is missing")
    return _accepted_ack_from_rows(
        candidate=candidate,
        tool_awaiting=tool_awaiting,
        run_waiting=run_waiting,
        attempt_suspended=attempt_suspended,
        idempotency_record=record,
    )


def _accepted_ack_from_rows(
    *,
    candidate: ToolAwaitingAcceptCandidate,
    tool_awaiting: EventLogRow,
    run_waiting: EventLogRow,
    attempt_suspended: EventLogRow,
    idempotency_record: IdempotencyRecord,
) -> ToolAwaitingAcceptedAck:
    """从 EventLog rows 组装 accepted ack。

    :param candidate: awaiting candidate。
    :param tool_awaiting: ``TOOL_AWAITING`` row。
    :param run_waiting: ``RUN_WAITING`` row。
    :param attempt_suspended: ``ATTEMPT_SUSPENDED`` row。
    :param idempotency_record: 幂等记录。
    :returns: accepted ack。
    """

    tool_awaiting_ref = _event_ref_from_row(tool_awaiting)
    run_waiting_ref = _event_ref_from_row(run_waiting)
    attempt_suspended_ref = _event_ref_from_row(attempt_suspended)
    return ToolAwaitingAcceptedAck(
        accepted_event_refs=(
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
