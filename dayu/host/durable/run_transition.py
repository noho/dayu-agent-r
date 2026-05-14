"""Host durable Run / Attempt transition primitives。

本模块实现 Phase 3 P3-S3 的低层 Run / Attempt / dispatch record 状态迁移。
所有 helper 都接收调用方提供的 ``HostTransaction``，在同一 transaction 内
append canonical EventLog facts 并更新 durable state row；本模块不打开事务、
不注册 after-commit callback、不做 admission policy、queue scanning
orchestration、WorkerProxy、Engine dispatch 或 public facade。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from dayu.host.api import AttemptStatus, CancelMode, RunStatus
from dayu.host.durable._validation import (
    require_non_empty_text as _require_non_empty_text,
    require_optional_non_empty_text as _require_optional_non_empty_text,
    require_optional_sha256_digest as _require_optional_sha256_digest,
    require_sha256_digest as _require_sha256_digest,
)
from dayu.host.durable.codec import format_utc_timestamp
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogStore,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.state import (
    AttemptMutationResult,
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordMutationResult,
    DispatchRecordStatus,
    RunRow,
    RunMutationResult,
    RunStartReason,
    StateMutationStatus,
    WorkerKind,
    cancel_pending_dispatch_record_row,
    cancel_queued_run_row,
    cancel_running_run_row,
    cancel_starting_attempt_row,
    insert_attempt,
    insert_dispatch_record,
    insert_run,
    promote_queued_run_row,
    read_active_run_for_session,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_earliest_queued_run,
    read_run_by_id,
    terminal_attempt_row,
    terminal_run_row,
)
from dayu.host.durable.transaction import HostTransaction

_EVENT_TYPE_RUN_ACCEPTED = "RUN_ACCEPTED"
_EVENT_TYPE_RUN_QUEUED = "RUN_QUEUED"
_EVENT_TYPE_RUN_STARTED = "RUN_STARTED"
_EVENT_TYPE_ATTEMPT_STARTED = "ATTEMPT_STARTED"
_EVENT_TYPE_CANCEL_REQUESTED = "CANCEL_REQUESTED"
_EVENT_TYPE_ATTEMPT_CANCELLED = "ATTEMPT_CANCELLED"
_EVENT_TYPE_RUN_CANCELLED = "RUN_CANCELLED"
_EVENT_TYPE_ATTEMPT_SUCCEEDED = "ATTEMPT_SUCCEEDED"
_EVENT_TYPE_ATTEMPT_FAILED = "ATTEMPT_FAILED"
_EVENT_TYPE_ATTEMPT_LOST = "ATTEMPT_LOST"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_RUN_FAILED = "RUN_FAILED"
_EVENT_TYPE_RUN_LOST = "RUN_LOST"


class PromotionSkipReason(StrEnum):
    """queue promotion 跳过原因文本常量。"""

    NO_QUEUED_RUN = "no_queued_run"
    ACTIVE_RUN_EXISTS = "active_run_exists"
    CAS_LOST_OR_NO_LONGER_ELIGIBLE = "cas_lost_or_no_longer_eligible"


@dataclass(frozen=True, slots=True)
class CreateQueuedRunInput:
    """创建 queued Run 的输入。

    :param session_id: 所属 Session id。
    :param run_id: 调用方生成的 Run id。
    :param client_request_id: 客户端幂等请求 id。
    :param input_event_id: 已存在 ``USER_INPUT_ACCEPTED`` event id。
    :param input_event_sequence: 已存在 ``USER_INPUT_ACCEPTED`` event sequence。
    :param run_accepted_event_id: 调用方生成的 ``RUN_ACCEPTED`` event id。
    :param run_queued_event_id: 调用方生成的 ``RUN_QUEUED`` event id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param idempotency_key: 幂等 key。
    :param execution_target: 已解析执行目标。
    :param queue_policy: Run queue policy。
    :param queue_reason: 排队原因。
    :param active_run_id: 接受时阻塞该 Run 的 active Run id。
    :param call_context_digest: 调用上下文 digest。
    """

    session_id: str
    run_id: str
    client_request_id: str
    input_event_id: str
    input_event_sequence: int
    run_accepted_event_id: str
    run_queued_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    idempotency_key: str
    execution_target: str
    queue_policy: str
    queue_reason: str
    active_run_id: str
    call_context_digest: str


@dataclass(frozen=True, slots=True)
class CreateRunningRunInput:
    """创建 running Run、STARTING Attempt 与 pending dispatch 的输入。

    :param session_id: 所属 Session id。
    :param run_id: 调用方生成的 Run id。
    :param client_request_id: 客户端幂等请求 id。
    :param input_event_id: 已存在 ``USER_INPUT_ACCEPTED`` event id。
    :param input_event_sequence: 已存在 ``USER_INPUT_ACCEPTED`` event sequence。
    :param run_accepted_event_id: 调用方生成的 ``RUN_ACCEPTED`` event id。
    :param run_started_event_id: 调用方生成的 ``RUN_STARTED`` event id。
    :param attempt_started_event_id: 调用方生成的 ``ATTEMPT_STARTED`` event id。
    :param attempt_id: 调用方生成的 Attempt id。
    :param execution_id: 调用方生成的 execution id。
    :param dispatch_record_id: 调用方生成的 dispatch record id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param idempotency_key: 幂等 key。
    :param execution_target: 已解析执行目标。
    :param queue_policy: Run queue policy。
    :param start_reason: Run start reason。
    :param worker_kind: worker 类型。
    :param owner_host_instance_id: owner Host instance id；Phase 3 可为 ``None``。
    :param call_context_digest: 调用上下文 digest。
    """

    session_id: str
    run_id: str
    client_request_id: str
    input_event_id: str
    input_event_sequence: int
    run_accepted_event_id: str
    run_started_event_id: str
    attempt_started_event_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str
    occurred_at: datetime
    actor: str
    source: str
    idempotency_key: str
    execution_target: str
    queue_policy: str
    start_reason: RunStartReason
    worker_kind: WorkerKind
    owner_host_instance_id: str | None
    call_context_digest: str


@dataclass(frozen=True, slots=True)
class PromoteQueuedRunInput:
    """promotion 最早 queued Run 的输入。

    :param session_id: 目标 Session id。
    :param run_started_event_id: 调用方生成的 ``RUN_STARTED`` event id。
    :param attempt_started_event_id: 调用方生成的 ``ATTEMPT_STARTED`` event id。
    :param attempt_id: 调用方生成的 Attempt id。
    :param execution_id: 调用方生成的 execution id。
    :param dispatch_record_id: 调用方生成的 dispatch record id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param worker_kind: worker 类型。
    :param owner_host_instance_id: owner Host instance id；Phase 3 可为 ``None``。
    """

    session_id: str
    run_started_event_id: str
    attempt_started_event_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str
    occurred_at: datetime
    actor: str
    source: str
    worker_kind: WorkerKind
    owner_host_instance_id: str | None


@dataclass(frozen=True, slots=True)
class TerminalCloseoutInput:
    """terminal closeout helper 输入。

    :param run_id: 目标 Run id。
    :param attempt_id: 目标 Attempt id。
    :param attempt_terminal_event_id: 调用方生成的具体 Attempt terminal event id。
    :param run_terminal_event_id: 调用方生成的具体 Run terminal event id。
    :param attempt_terminal_status: 具体 Attempt 终态。
    :param run_terminal_status: 具体 Run 终态。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param reason: terminal reason。
    :param terminal_summary_ref: terminal summary 引用；无摘要时为 ``None``。
    :param terminal_summary_digest: terminal summary digest；无摘要时为 ``None``。
    """

    run_id: str
    attempt_id: str
    attempt_terminal_event_id: str
    run_terminal_event_id: str
    attempt_terminal_status: AttemptStatus
    run_terminal_status: RunStatus
    occurred_at: datetime
    actor: str
    source: str
    reason: str
    terminal_summary_ref: str | None
    terminal_summary_digest: str | None


@dataclass(frozen=True, slots=True)
class CancelQueuedRunInput:
    """取消 queued Run 的输入。

    :param run_id: 目标 Run id。
    :param cancel_request_event_id: 调用方生成的 ``CANCEL_REQUESTED`` event id。
    :param run_cancelled_event_id: 调用方生成的 ``RUN_CANCELLED`` event id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param client_request_id: 客户端幂等请求 id。
    :param idempotency_key: 幂等 key。
    :param reason: cancel reason。
    :param mode: cancel mode。
    :param call_context_digest: 调用上下文 digest。
    """

    run_id: str
    cancel_request_event_id: str
    run_cancelled_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    client_request_id: str
    idempotency_key: str
    reason: str
    mode: CancelMode
    call_context_digest: str


@dataclass(frozen=True, slots=True)
class CancelPredispatchStartingInput:
    """取消 pre-dispatch STARTING Attempt 的输入。

    :param run_id: 目标 Run id。
    :param cancel_request_event_id: 调用方生成的 ``CANCEL_REQUESTED`` event id。
    :param attempt_cancelled_event_id: 调用方生成的 ``ATTEMPT_CANCELLED`` event id。
    :param run_cancelled_event_id: 调用方生成的 ``RUN_CANCELLED`` event id。
    :param occurred_at: canonical facts 的发生时间。
    :param actor: 事件 actor。
    :param source: 事件 source。
    :param client_request_id: 客户端幂等请求 id。
    :param idempotency_key: 幂等 key。
    :param reason: cancel reason。
    :param mode: cancel mode。
    :param call_context_digest: 调用上下文 digest。
    """

    run_id: str
    cancel_request_event_id: str
    attempt_cancelled_event_id: str
    run_cancelled_event_id: str
    occurred_at: datetime
    actor: str
    source: str
    client_request_id: str
    idempotency_key: str
    reason: str
    mode: CancelMode
    call_context_digest: str


@dataclass(frozen=True, slots=True)
class RunTransitionResult:
    """Run transition helper 结果。

    :param status: transition 结果分类。
    :param run: 最新 Run row。
    :param attempt: 最新 Attempt row；无 Attempt 时为 ``None``。
    :param dispatch_record: 最新 dispatch record row；无 dispatch 时为 ``None``。
    """

    status: StateMutationStatus
    run: RunRow | None
    attempt: AttemptRow | None
    dispatch_record: DispatchRecordRow | None


@dataclass(frozen=True, slots=True)
class PromotionResult:
    """queued Run promotion 结果。

    :param status: mutation 结果分类。
    :param promoted_run: 成功 promotion 的 Run row。
    :param attempt: 新建 Attempt row。
    :param dispatch_record: 新建 dispatch record row。
    :param skip_reason: 未 promotion 时的跳过原因。
    """

    status: StateMutationStatus
    promoted_run: RunRow | None
    attempt: AttemptRow | None
    dispatch_record: DispatchRecordRow | None
    skip_reason: str | None


def create_queued_run_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: CreateQueuedRunInput,
) -> RunTransitionResult:
    """创建 accepted queued Run。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: 创建 queued Run 输入。
    :returns: transition 结果，成功时 ``status`` 为 ``updated``。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_create_queued_input(request)
    accepted_event = event_log_store.append_event(
        transaction, _run_accepted_event_request(request)
    ).row
    queued_event = event_log_store.append_event(
        transaction,
        _run_queued_event_request(
            request=request,
            accepted_event_id=accepted_event.event_id,
            accepted_event_sequence=accepted_event.event_sequence,
        ),
    ).row
    created_at = format_utc_timestamp(request.occurred_at)
    run = RunRow(
        run_id=request.run_id,
        session_id=request.session_id,
        status=RunStatus.QUEUED,
        client_request_id=request.client_request_id,
        input_event_id=request.input_event_id,
        input_event_sequence=request.input_event_sequence,
        accepted_event_id=accepted_event.event_id,
        accepted_event_sequence=accepted_event.event_sequence,
        queued_event_id=queued_event.event_id,
        queued_event_sequence=queued_event.event_sequence,
        started_event_id=None,
        started_event_sequence=None,
        terminal_event_id=None,
        terminal_event_sequence=None,
        current_attempt_id=None,
        source_run_id=None,
        source_run_relation=None,
        execution_target=request.execution_target,
        queue_policy=request.queue_policy,
        created_at=created_at,
        updated_at=created_at,
        terminal_at=None,
    )
    insert_run(transaction, run)
    return RunTransitionResult(
        status=StateMutationStatus.UPDATED,
        run=read_run_by_id(transaction, request.run_id),
        attempt=None,
        dispatch_record=None,
    )


def create_running_run_with_starting_attempt_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: CreateRunningRunInput,
) -> RunTransitionResult:
    """创建 running Run、STARTING Attempt 与 pending dispatch record。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: 创建 running Run 输入。
    :returns: transition 结果，成功时 ``status`` 为 ``updated``。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_create_running_input(request)
    accepted_event = event_log_store.append_event(
        transaction, _run_accepted_event_request(request)
    ).row
    started_event = event_log_store.append_event(
        transaction,
        _run_started_event_request(
            request=request,
            accepted_event_id=accepted_event.event_id,
            accepted_event_sequence=accepted_event.event_sequence,
        ),
    ).row
    attempt_started_event = event_log_store.append_event(
        transaction, _attempt_started_event_request(request)
    ).row
    created_at = format_utc_timestamp(request.occurred_at)
    run = RunRow(
        run_id=request.run_id,
        session_id=request.session_id,
        status=RunStatus.RUNNING,
        client_request_id=request.client_request_id,
        input_event_id=request.input_event_id,
        input_event_sequence=request.input_event_sequence,
        accepted_event_id=accepted_event.event_id,
        accepted_event_sequence=accepted_event.event_sequence,
        queued_event_id=None,
        queued_event_sequence=None,
        started_event_id=started_event.event_id,
        started_event_sequence=started_event.event_sequence,
        terminal_event_id=None,
        terminal_event_sequence=None,
        current_attempt_id=request.attempt_id,
        source_run_id=None,
        source_run_relation=None,
        execution_target=request.execution_target,
        queue_policy=request.queue_policy,
        created_at=created_at,
        updated_at=created_at,
        terminal_at=None,
    )
    attempt = _starting_attempt_row(
        request=request,
        started_event_id=attempt_started_event.event_id,
        started_event_sequence=attempt_started_event.event_sequence,
        created_at=created_at,
    )
    dispatch_record = _pending_dispatch_record_row(
        request=request,
        created_event_id=attempt_started_event.event_id,
        created_event_sequence=attempt_started_event.event_sequence,
        created_at=created_at,
    )
    insert_run(transaction, run)
    insert_attempt(transaction, attempt)
    insert_dispatch_record(transaction, dispatch_record)
    return RunTransitionResult(
        status=StateMutationStatus.UPDATED,
        run=read_run_by_id(transaction, request.run_id),
        attempt=read_attempt_by_id(transaction, request.attempt_id),
        dispatch_record=read_dispatch_record_by_attempt_id(
            transaction, request.attempt_id
        ),
    )


def promote_queued_run_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: PromoteQueuedRunInput,
) -> PromotionResult:
    """将最早 queued Run promotion 为 running 并创建 STARTING Attempt。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: promotion 输入。
    :returns: promotion 结果，未满足前置条件时返回 skip reason。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_promote_input(request)
    if read_active_run_for_session(transaction, request.session_id) is not None:
        return PromotionResult(
            status=StateMutationStatus.INVALID_STATE,
            promoted_run=None,
            attempt=None,
            dispatch_record=None,
            skip_reason=PromotionSkipReason.ACTIVE_RUN_EXISTS,
        )
    queued = read_earliest_queued_run(transaction, request.session_id)
    if queued is None:
        return PromotionResult(
            status=StateMutationStatus.NOT_FOUND,
            promoted_run=None,
            attempt=None,
            dispatch_record=None,
            skip_reason=PromotionSkipReason.NO_QUEUED_RUN,
        )

    started_event = event_log_store.append_event(
        transaction, _promotion_run_started_event_request(request, queued)
    ).row
    promoted = promote_queued_run_row(
        transaction,
        session_id=request.session_id,
        run_id=queued.run_id,
        started_event_id=started_event.event_id,
        started_event_sequence=started_event.event_sequence,
        current_attempt_id=request.attempt_id,
        updated_at=format_utc_timestamp(request.occurred_at),
    )
    promoted = _require_run_mutation_updated(
        promoted,
        mutation_name="promote queued Run",
    )

    attempt_started_event = event_log_store.append_event(
        transaction, _promotion_attempt_started_event_request(request, queued)
    ).row
    created_at = format_utc_timestamp(request.occurred_at)
    attempt = _promotion_attempt_row(
        request=request,
        run_id=queued.run_id,
        started_event_id=attempt_started_event.event_id,
        started_event_sequence=attempt_started_event.event_sequence,
        created_at=created_at,
    )
    dispatch_record = _promotion_dispatch_record_row(
        request=request,
        run_id=queued.run_id,
        execution_target=queued.execution_target,
        created_event_id=attempt_started_event.event_id,
        created_event_sequence=attempt_started_event.event_sequence,
        created_at=created_at,
    )
    insert_attempt(transaction, attempt)
    insert_dispatch_record(transaction, dispatch_record)
    return PromotionResult(
        status=StateMutationStatus.UPDATED,
        promoted_run=read_run_by_id(transaction, queued.run_id),
        attempt=read_attempt_by_id(transaction, request.attempt_id),
        dispatch_record=read_dispatch_record_by_attempt_id(
            transaction, request.attempt_id
        ),
        skip_reason=None,
    )


def terminal_closeout_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: TerminalCloseoutInput,
) -> RunTransitionResult:
    """关闭 active Run 与当前 Attempt 到具体终态。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: terminal closeout 输入。
    :returns: transition 结果，前置状态不满足时返回 not_found/invalid_state/cas_lost。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_terminal_input(request)
    run = read_run_by_id(transaction, request.run_id)
    attempt = read_attempt_by_id(transaction, request.attempt_id)
    invalid = _invalid_terminal_precondition(run, attempt, request.attempt_id)
    if invalid is not None:
        return invalid
    if run is None or attempt is None:
        raise HostDurableError("terminal precondition narrowing failed")

    attempt_event = event_log_store.append_event(
        transaction, _attempt_terminal_event_request(request, run, attempt)
    ).row
    run_event = event_log_store.append_event(
        transaction, _run_terminal_event_request(request, run, attempt_event.event_id)
    ).row
    terminal_at = format_utc_timestamp(request.occurred_at)
    attempt_result = terminal_attempt_row(
        transaction,
        attempt_id=request.attempt_id,
        terminal_status=request.attempt_terminal_status,
        terminal_event_id=attempt_event.event_id,
        terminal_event_sequence=attempt_event.event_sequence,
        terminal_at=terminal_at,
    )
    attempt_result = _require_attempt_mutation_updated(
        attempt_result,
        mutation_name="terminal Attempt",
    )
    run_result = terminal_run_row(
        transaction,
        run_id=request.run_id,
        current_attempt_id=request.attempt_id,
        terminal_status=request.run_terminal_status,
        terminal_event_id=run_event.event_id,
        terminal_event_sequence=run_event.event_sequence,
        terminal_at=terminal_at,
    )
    run_result = _require_run_mutation_updated(
        run_result,
        mutation_name="terminal Run",
    )
    return RunTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=attempt_result.row,
        dispatch_record=read_dispatch_record_by_attempt_id(
            transaction, request.attempt_id
        ),
    )


def cancel_queued_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: CancelQueuedRunInput,
) -> RunTransitionResult:
    """取消 queued Run，不创建 Attempt。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: cancel queued 输入。
    :returns: transition 结果，前置状态不满足时返回 not_found/invalid_state。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_cancel_queued_input(request)
    run = read_run_by_id(transaction, request.run_id)
    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=None,
            dispatch_record=None,
        )
    if run.status != RunStatus.QUEUED:
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=None,
            dispatch_record=None,
        )
    cancel_request_event = event_log_store.append_event(
        transaction, _cancel_requested_event_request(request, run)
    ).row
    run_cancelled_event = event_log_store.append_event(
        transaction,
        _run_cancelled_event_request(
            request=request,
            run=run,
            cancel_request_event_id=cancel_request_event.event_id,
            terminal_attempt_id=None,
            terminal_attempt_event_id=None,
        ),
    ).row
    run_result = cancel_queued_run_row(
        transaction,
        run_id=request.run_id,
        terminal_event_id=run_cancelled_event.event_id,
        terminal_event_sequence=run_cancelled_event.event_sequence,
        terminal_at=format_utc_timestamp(request.occurred_at),
    )
    run_result = _require_run_mutation_updated(
        run_result,
        mutation_name="cancel queued Run",
    )
    return RunTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=None,
        dispatch_record=None,
    )


def cancel_predispatch_starting_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    request: CancelPredispatchStartingInput,
) -> RunTransitionResult:
    """取消 RUNNING + STARTING + pending dispatch 的 pre-dispatch Run。

    :param transaction: 调用方提供的 Host transaction。
    :param event_log_store: EventLog append primitive。
    :param request: cancel pre-dispatch starting 输入。
    :returns: transition 结果，前置状态不满足时返回 not_found/invalid_state。
    :raises HostDurableError: 输入字段或 SQLite 写入无效时由底层抛出。
    """

    _validate_cancel_predispatch_input(request)
    run = read_run_by_id(transaction, request.run_id)
    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=None,
            dispatch_record=None,
        )
    if run.status != RunStatus.RUNNING or run.current_attempt_id is None:
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=None,
            dispatch_record=None,
        )
    attempt = read_attempt_by_id(transaction, run.current_attempt_id)
    dispatch_record = read_dispatch_record_by_attempt_id(
        transaction, run.current_attempt_id
    )
    if (
        attempt is None
        or attempt.status != AttemptStatus.STARTING
        or dispatch_record is None
        or dispatch_record.status != DispatchRecordStatus.PENDING
    ):
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
        )

    cancel_request_event = event_log_store.append_event(
        transaction, _cancel_requested_event_request(request, run)
    ).row
    attempt_cancelled_event = event_log_store.append_event(
        transaction,
        _attempt_cancelled_event_request(
            request=request,
            run=run,
            attempt=attempt,
            dispatch_record=dispatch_record,
            cancel_request_event_id=cancel_request_event.event_id,
        ),
    ).row
    run_cancelled_event = event_log_store.append_event(
        transaction,
        _run_cancelled_event_request(
            request=request,
            run=run,
            cancel_request_event_id=cancel_request_event.event_id,
            terminal_attempt_id=attempt.attempt_id,
            terminal_attempt_event_id=attempt_cancelled_event.event_id,
        ),
    ).row
    terminal_at = format_utc_timestamp(request.occurred_at)
    dispatch_result = cancel_pending_dispatch_record_row(
        transaction,
        attempt_id=attempt.attempt_id,
        cancelled_event_id=attempt_cancelled_event.event_id,
        cancelled_event_sequence=attempt_cancelled_event.event_sequence,
        cancelled_at=terminal_at,
    )
    dispatch_result = _require_dispatch_record_mutation_updated(
        dispatch_result,
        mutation_name="cancel pending dispatch record",
    )
    attempt_result = cancel_starting_attempt_row(
        transaction,
        attempt_id=attempt.attempt_id,
        terminal_event_id=attempt_cancelled_event.event_id,
        terminal_event_sequence=attempt_cancelled_event.event_sequence,
        terminal_at=terminal_at,
    )
    attempt_result = _require_attempt_mutation_updated(
        attempt_result,
        mutation_name="cancel starting Attempt",
    )
    run_result = cancel_running_run_row(
        transaction,
        run_id=run.run_id,
        current_attempt_id=attempt.attempt_id,
        terminal_event_id=run_cancelled_event.event_id,
        terminal_event_sequence=run_cancelled_event.event_sequence,
        terminal_at=terminal_at,
    )
    run_result = _require_run_mutation_updated(
        run_result,
        mutation_name="cancel running Run",
    )
    return RunTransitionResult(
        status=run_result.status,
        run=run_result.row,
        attempt=attempt_result.row,
        dispatch_record=dispatch_result.row,
    )


def _require_run_mutation_updated(
    result: RunMutationResult, *, mutation_name: str
) -> RunMutationResult:
    """断言 Run mutation 已完成。

    :param result: 低层 Run mutation 结果。
    :param mutation_name: mutation 语义名称，用于错误信息。
    :returns: ``UPDATED`` 的原始 mutation 结果。
    :raises HostDurableError: mutation 不是 ``UPDATED`` 时抛出以触发事务回滚。
    """

    if result.status != StateMutationStatus.UPDATED:
        _raise_after_event_append_mutation_failure(
            mutation_name=mutation_name,
            status=result.status,
        )
    return result


def _require_attempt_mutation_updated(
    result: AttemptMutationResult, *, mutation_name: str
) -> AttemptMutationResult:
    """断言 Attempt mutation 已完成。

    :param result: 低层 Attempt mutation 结果。
    :param mutation_name: mutation 语义名称，用于错误信息。
    :returns: ``UPDATED`` 的原始 mutation 结果。
    :raises HostDurableError: mutation 不是 ``UPDATED`` 时抛出以触发事务回滚。
    """

    if result.status != StateMutationStatus.UPDATED:
        _raise_after_event_append_mutation_failure(
            mutation_name=mutation_name,
            status=result.status,
        )
    return result


def _require_dispatch_record_mutation_updated(
    result: DispatchRecordMutationResult, *, mutation_name: str
) -> DispatchRecordMutationResult:
    """断言 dispatch record mutation 已完成。

    :param result: 低层 dispatch record mutation 结果。
    :param mutation_name: mutation 语义名称，用于错误信息。
    :returns: ``UPDATED`` 的原始 mutation 结果。
    :raises HostDurableError: mutation 不是 ``UPDATED`` 时抛出以触发事务回滚。
    """

    if result.status != StateMutationStatus.UPDATED:
        _raise_after_event_append_mutation_failure(
            mutation_name=mutation_name,
            status=result.status,
        )
    return result


def _raise_after_event_append_mutation_failure(
    *, mutation_name: str, status: StateMutationStatus
) -> None:
    """在 append canonical EventLog 后的 state mutation 失败时中止事务。

    :param mutation_name: mutation 语义名称，用于错误信息。
    :param status: 非 ``UPDATED`` mutation 状态。
    :returns: ``None``。
    :raises HostDurableError: 总是抛出以阻止调用方正常 commit 孤立 EventLog。
    """

    raise HostDurableError(
        f"{mutation_name} returned {status.value} after EventLog append"
    )


def _run_accepted_event_request(
    request: CreateQueuedRunInput | CreateRunningRunInput,
) -> EventLogAppendRequest:
    """构造 ``RUN_ACCEPTED`` EventLog append request。

    :param request: 创建 Run 输入。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_accepted_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=request.session_id,
        run_id=request.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_ACCEPTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason=None,
        payload_json={
            "run_id": request.run_id,
            "client_request_id": request.client_request_id,
            "input_event_id": request.input_event_id,
            "input_event_sequence": request.input_event_sequence,
            "execution_target": request.execution_target,
            "queue_policy": request.queue_policy,
            "source_run_id": None,
            "source_run_relation": None,
            "call_context_digest": request.call_context_digest,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _run_queued_event_request(
    *,
    request: CreateQueuedRunInput,
    accepted_event_id: str,
    accepted_event_sequence: int,
) -> EventLogAppendRequest:
    """构造 ``RUN_QUEUED`` EventLog append request。

    :param request: 创建 queued Run 输入。
    :param accepted_event_id: RUN_ACCEPTED event id。
    :param accepted_event_sequence: RUN_ACCEPTED event sequence。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_queued_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=request.session_id,
        run_id=request.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_QUEUED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason={"queue_reason": request.queue_reason},
        payload_json={
            "run_id": request.run_id,
            "accepted_event_id": accepted_event_id,
            "accepted_event_sequence": accepted_event_sequence,
            "queue_reason": request.queue_reason,
            "active_run_id": request.active_run_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _run_started_event_request(
    *,
    request: CreateRunningRunInput,
    accepted_event_id: str,
    accepted_event_sequence: int,
) -> EventLogAppendRequest:
    """构造 direct start ``RUN_STARTED`` EventLog append request。

    :param request: 创建 running Run 输入。
    :param accepted_event_id: RUN_ACCEPTED event id。
    :param accepted_event_sequence: RUN_ACCEPTED event sequence。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_started_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=request.session_id,
        run_id=request.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_STARTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason={"start_reason": request.start_reason.value},
        payload_json={
            "run_id": request.run_id,
            "start_reason": request.start_reason.value,
            "accepted_event_id": accepted_event_id,
            "accepted_event_sequence": accepted_event_sequence,
            "attempt_id": request.attempt_id,
            "dispatch_record_id": request.dispatch_record_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _attempt_started_event_request(
    request: CreateRunningRunInput,
) -> EventLogAppendRequest:
    """构造 direct start ``ATTEMPT_STARTED`` EventLog append request。

    :param request: 创建 running Run 输入。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.attempt_started_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=request.session_id,
        run_id=request.run_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_STARTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason=None,
        payload_json={
            "attempt_id": request.attempt_id,
            "execution_id": request.execution_id,
            "dispatch_record_id": request.dispatch_record_id,
            "worker_kind": request.worker_kind.value,
            "execution_target": request.execution_target,
            "owner_host_instance_id": request.owner_host_instance_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _promotion_run_started_event_request(
    request: PromoteQueuedRunInput, queued: RunRow
) -> EventLogAppendRequest:
    """构造 promotion ``RUN_STARTED`` EventLog append request。

    :param request: promotion 输入。
    :param queued: 被 promotion 的 queued Run row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_started_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=request.session_id,
        run_id=queued.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_STARTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"start_reason": RunStartReason.QUEUE_PROMOTION.value},
        payload_json={
            "run_id": queued.run_id,
            "start_reason": RunStartReason.QUEUE_PROMOTION.value,
            "accepted_event_id": queued.accepted_event_id,
            "accepted_event_sequence": queued.accepted_event_sequence,
            "attempt_id": request.attempt_id,
            "dispatch_record_id": request.dispatch_record_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _promotion_attempt_started_event_request(
    request: PromoteQueuedRunInput, queued: RunRow
) -> EventLogAppendRequest:
    """构造 promotion ``ATTEMPT_STARTED`` EventLog append request。

    :param request: promotion 输入。
    :param queued: 被 promotion 的 queued Run row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.attempt_started_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=request.session_id,
        run_id=queued.run_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_STARTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason=None,
        payload_json={
            "attempt_id": request.attempt_id,
            "execution_id": request.execution_id,
            "dispatch_record_id": request.dispatch_record_id,
            "worker_kind": request.worker_kind.value,
            "execution_target": queued.execution_target,
            "owner_host_instance_id": request.owner_host_instance_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _cancel_requested_event_request(
    request: CancelQueuedRunInput | CancelPredispatchStartingInput,
    run: RunRow,
) -> EventLogAppendRequest:
    """构造 ``CANCEL_REQUESTED`` EventLog append request。

    :param request: cancel 输入。
    :param run: 被取消的 Run row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.cancel_request_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_CANCEL_REQUESTED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason={"reason": request.reason, "mode": request.mode.value},
        payload_json={
            "run_id": run.run_id,
            "client_request_id": request.client_request_id,
            "reason": request.reason,
            "mode": request.mode.value,
            "target_status_at_accept": run.status.value,
            "call_context_digest": request.call_context_digest,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _attempt_cancelled_event_request(
    *,
    request: CancelPredispatchStartingInput,
    run: RunRow,
    attempt: AttemptRow,
    dispatch_record: DispatchRecordRow,
    cancel_request_event_id: str,
) -> EventLogAppendRequest:
    """构造 ``ATTEMPT_CANCELLED`` EventLog append request。

    :param request: cancel pre-dispatch 输入。
    :param run: 被取消的 Run row。
    :param attempt: 被取消的 Attempt row。
    :param dispatch_record: 被取消的 dispatch record row。
    :param cancel_request_event_id: CANCEL_REQUESTED event id。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.attempt_cancelled_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=attempt.execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_CANCELLED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json={
            "attempt_id": attempt.attempt_id,
            "execution_id": attempt.execution_id,
            "reason": request.reason,
            "cancel_request_event_id": cancel_request_event_id,
            "dispatch_record_id": dispatch_record.dispatch_record_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _run_cancelled_event_request(
    *,
    request: CancelQueuedRunInput | CancelPredispatchStartingInput,
    run: RunRow,
    cancel_request_event_id: str,
    terminal_attempt_id: str | None,
    terminal_attempt_event_id: str | None,
) -> EventLogAppendRequest:
    """构造 ``RUN_CANCELLED`` EventLog append request。

    :param request: cancel 输入。
    :param run: 被取消的 Run row。
    :param cancel_request_event_id: CANCEL_REQUESTED event id。
    :param terminal_attempt_id: terminal Attempt id；queued cancel 时为 ``None``。
    :param terminal_attempt_event_id: Attempt terminal event id；queued cancel 时为 ``None``。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_cancelled_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=terminal_attempt_id,
        execution_id=None,
        event_type=_EVENT_TYPE_RUN_CANCELLED,
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json={
            "run_id": run.run_id,
            "reason": request.reason,
            "cancel_request_event_id": cancel_request_event_id,
            "terminal_attempt_id": terminal_attempt_id,
            "terminal_attempt_event_id": terminal_attempt_event_id,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _attempt_terminal_event_request(
    request: TerminalCloseoutInput, run: RunRow, attempt: AttemptRow
) -> EventLogAppendRequest:
    """构造具体 Attempt terminal EventLog append request。

    :param request: terminal closeout 输入。
    :param run: 目标 Run row。
    :param attempt: 目标 Attempt row。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.attempt_terminal_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=attempt.execution_id,
        event_type=_attempt_terminal_event_type(request.attempt_terminal_status),
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json={
            "attempt_id": attempt.attempt_id,
            "execution_id": attempt.execution_id,
            "reason": request.reason,
            "terminal_summary_ref": request.terminal_summary_ref,
            "terminal_summary_digest": request.terminal_summary_digest,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _run_terminal_event_request(
    request: TerminalCloseoutInput, run: RunRow, attempt_terminal_event_id: str
) -> EventLogAppendRequest:
    """构造具体 Run terminal EventLog append request。

    :param request: terminal closeout 输入。
    :param run: 目标 Run row。
    :param attempt_terminal_event_id: Attempt terminal event id。
    :returns: EventLog append request。
    """

    return EventLogAppendRequest(
        event_id=request.run_terminal_event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=request.attempt_id,
        execution_id=None,
        event_type=_run_terminal_event_type(request.run_terminal_status),
        occurred_at=request.occurred_at,
        actor=request.actor,
        source=request.source,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": request.reason},
        payload_json={
            "run_id": run.run_id,
            "terminal_attempt_id": request.attempt_id,
            "attempt_terminal_event_id": attempt_terminal_event_id,
            "terminal_summary_ref": request.terminal_summary_ref,
            "terminal_summary_digest": request.terminal_summary_digest,
            "reason": request.reason,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _starting_attempt_row(
    *,
    request: CreateRunningRunInput,
    started_event_id: str,
    started_event_sequence: int,
    created_at: str,
) -> AttemptRow:
    """构造 STARTING Attempt row。

    :param request: 创建 running Run 输入。
    :param started_event_id: ATTEMPT_STARTED event id。
    :param started_event_sequence: ATTEMPT_STARTED event sequence。
    :param created_at: 创建 timestamp。
    :returns: Attempt row。
    """

    return AttemptRow(
        attempt_id=request.attempt_id,
        run_id=request.run_id,
        execution_id=request.execution_id,
        status=AttemptStatus.STARTING,
        started_event_id=started_event_id,
        started_event_sequence=started_event_sequence,
        terminal_event_id=None,
        terminal_event_sequence=None,
        created_at=created_at,
        updated_at=created_at,
        terminal_at=None,
    )


def _pending_dispatch_record_row(
    *,
    request: CreateRunningRunInput,
    created_event_id: str,
    created_event_sequence: int,
    created_at: str,
) -> DispatchRecordRow:
    """构造 pending dispatch record row。

    :param request: 创建 running Run 输入。
    :param created_event_id: ATTEMPT_STARTED event id。
    :param created_event_sequence: ATTEMPT_STARTED event sequence。
    :param created_at: 创建 timestamp。
    :returns: dispatch record row。
    """

    return DispatchRecordRow(
        dispatch_record_id=request.dispatch_record_id,
        run_id=request.run_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        status=DispatchRecordStatus.PENDING,
        worker_kind=request.worker_kind,
        execution_target=request.execution_target,
        owner_host_instance_id=request.owner_host_instance_id,
        created_event_id=created_event_id,
        created_event_sequence=created_event_sequence,
        cancelled_event_id=None,
        cancelled_event_sequence=None,
        created_at=created_at,
        updated_at=created_at,
        cancelled_at=None,
    )


def _promotion_attempt_row(
    *,
    request: PromoteQueuedRunInput,
    run_id: str,
    started_event_id: str,
    started_event_sequence: int,
    created_at: str,
) -> AttemptRow:
    """构造 promotion STARTING Attempt row。

    :param request: promotion 输入。
    :param run_id: 被 promotion 的 Run id。
    :param started_event_id: ATTEMPT_STARTED event id。
    :param started_event_sequence: ATTEMPT_STARTED event sequence。
    :param created_at: 创建 timestamp。
    :returns: Attempt row。
    """

    return AttemptRow(
        attempt_id=request.attempt_id,
        run_id=run_id,
        execution_id=request.execution_id,
        status=AttemptStatus.STARTING,
        started_event_id=started_event_id,
        started_event_sequence=started_event_sequence,
        terminal_event_id=None,
        terminal_event_sequence=None,
        created_at=created_at,
        updated_at=created_at,
        terminal_at=None,
    )


def _promotion_dispatch_record_row(
    *,
    request: PromoteQueuedRunInput,
    run_id: str,
    execution_target: str,
    created_event_id: str,
    created_event_sequence: int,
    created_at: str,
) -> DispatchRecordRow:
    """构造 promotion pending dispatch record row。

    :param request: promotion 输入。
    :param run_id: 被 promotion 的 Run id。
    :param execution_target: Run 持久化的 execution target。
    :param created_event_id: ATTEMPT_STARTED event id。
    :param created_event_sequence: ATTEMPT_STARTED event sequence。
    :param created_at: 创建 timestamp。
    :returns: dispatch record row。
    """

    return DispatchRecordRow(
        dispatch_record_id=request.dispatch_record_id,
        run_id=run_id,
        attempt_id=request.attempt_id,
        execution_id=request.execution_id,
        status=DispatchRecordStatus.PENDING,
        worker_kind=request.worker_kind,
        execution_target=execution_target,
        owner_host_instance_id=request.owner_host_instance_id,
        created_event_id=created_event_id,
        created_event_sequence=created_event_sequence,
        cancelled_event_id=None,
        cancelled_event_sequence=None,
        created_at=created_at,
        updated_at=created_at,
        cancelled_at=None,
    )


def _invalid_terminal_precondition(
    run: RunRow | None, attempt: AttemptRow | None, attempt_id: str
) -> RunTransitionResult | None:
    """检查 terminal closeout 前置状态。

    :param run: 目标 Run row。
    :param attempt: 目标 Attempt row。
    :param attempt_id: 请求中的 Attempt id。
    :returns: 前置失败时返回 transition 结果，否则返回 ``None``。
    """

    if run is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=None,
            attempt=attempt,
            dispatch_record=None,
        )
    if attempt is None:
        return RunTransitionResult(
            status=StateMutationStatus.NOT_FOUND,
            run=run,
            attempt=None,
            dispatch_record=None,
        )
    if (
        run.status != RunStatus.RUNNING
        or run.current_attempt_id != attempt_id
        or attempt.run_id != run.run_id
        or attempt.status != AttemptStatus.STARTING
    ):
        return RunTransitionResult(
            status=StateMutationStatus.INVALID_STATE,
            run=run,
            attempt=attempt,
            dispatch_record=None,
        )
    return None


def _attempt_terminal_event_type(status: AttemptStatus) -> str:
    """把 Attempt 终态映射到具体 canonical event type。

    :param status: Attempt 终态。
    :returns: event type。
    :raises ValueError: 状态不是 P3-S3 支持的 terminal 状态时抛出。
    """

    if status == AttemptStatus.SUCCEEDED:
        return _EVENT_TYPE_ATTEMPT_SUCCEEDED
    if status == AttemptStatus.FAILED:
        return _EVENT_TYPE_ATTEMPT_FAILED
    if status == AttemptStatus.LOST:
        return _EVENT_TYPE_ATTEMPT_LOST
    raise ValueError("unsupported Attempt terminal status")


def _run_terminal_event_type(status: RunStatus) -> str:
    """把 Run 终态映射到具体 canonical event type。

    :param status: Run 终态。
    :returns: event type。
    :raises ValueError: 状态不是 P3-S3 支持的 terminal 状态时抛出。
    """

    if status == RunStatus.SUCCEEDED:
        return _EVENT_TYPE_RUN_SUCCEEDED
    if status == RunStatus.FAILED:
        return _EVENT_TYPE_RUN_FAILED
    if status == RunStatus.LOST:
        return _EVENT_TYPE_RUN_LOST
    raise ValueError("unsupported Run terminal status")


def _validate_create_queued_input(request: CreateQueuedRunInput) -> None:
    """校验 queued Run 创建输入。

    :param request: 创建 queued Run 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _validate_common_create_input(
        session_id=request.session_id,
        run_id=request.run_id,
        client_request_id=request.client_request_id,
        input_event_id=request.input_event_id,
        input_event_sequence=request.input_event_sequence,
        run_accepted_event_id=request.run_accepted_event_id,
        actor=request.actor,
        source=request.source,
        idempotency_key=request.idempotency_key,
        execution_target=request.execution_target,
        queue_policy=request.queue_policy,
        call_context_digest=request.call_context_digest,
    )
    _require_non_empty_text(
        request.run_queued_event_id, field_name="run_queued_event_id"
    )
    _require_non_empty_text(request.queue_reason, field_name="queue_reason")
    _require_non_empty_text(request.active_run_id, field_name="active_run_id")


def _validate_create_running_input(request: CreateRunningRunInput) -> None:
    """校验 running Run 创建输入。

    :param request: 创建 running Run 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _validate_common_create_input(
        session_id=request.session_id,
        run_id=request.run_id,
        client_request_id=request.client_request_id,
        input_event_id=request.input_event_id,
        input_event_sequence=request.input_event_sequence,
        run_accepted_event_id=request.run_accepted_event_id,
        actor=request.actor,
        source=request.source,
        idempotency_key=request.idempotency_key,
        execution_target=request.execution_target,
        queue_policy=request.queue_policy,
        call_context_digest=request.call_context_digest,
    )
    _require_non_empty_text(
        request.run_started_event_id, field_name="run_started_event_id"
    )
    _require_non_empty_text(
        request.attempt_started_event_id, field_name="attempt_started_event_id"
    )
    _require_non_empty_text(request.attempt_id, field_name="attempt_id")
    _require_non_empty_text(request.execution_id, field_name="execution_id")
    _require_non_empty_text(
        request.dispatch_record_id, field_name="dispatch_record_id"
    )
    if not isinstance(request.start_reason, RunStartReason):
        raise ValueError("start_reason is invalid")
    if not isinstance(request.worker_kind, WorkerKind):
        raise ValueError("worker_kind is invalid")
    _require_optional_non_empty_text(
        request.owner_host_instance_id, field_name="owner_host_instance_id"
    )


def _validate_common_create_input(
    *,
    session_id: str,
    run_id: str,
    client_request_id: str,
    input_event_id: str,
    input_event_sequence: int,
    run_accepted_event_id: str,
    actor: str,
    source: str,
    idempotency_key: str,
    execution_target: str,
    queue_policy: str,
    call_context_digest: str,
) -> None:
    """校验 Run 创建公共字段。

    :param session_id: Session id。
    :param run_id: Run id。
    :param client_request_id: client request id。
    :param input_event_id: input event id。
    :param input_event_sequence: input event sequence。
    :param run_accepted_event_id: RUN_ACCEPTED event id。
    :param actor: actor。
    :param source: source。
    :param idempotency_key: idempotency key。
    :param execution_target: execution target。
    :param queue_policy: queue policy。
    :param call_context_digest: call context digest。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    _require_non_empty_text(run_id, field_name="run_id")
    _require_non_empty_text(client_request_id, field_name="client_request_id")
    _require_non_empty_text(input_event_id, field_name="input_event_id")
    _require_positive_sequence(input_event_sequence, "input_event_sequence")
    _require_non_empty_text(
        run_accepted_event_id, field_name="run_accepted_event_id"
    )
    _require_non_empty_text(actor, field_name="actor")
    _require_non_empty_text(source, field_name="source")
    _require_non_empty_text(idempotency_key, field_name="idempotency_key")
    _require_non_empty_text(execution_target, field_name="execution_target")
    _require_non_empty_text(queue_policy, field_name="queue_policy")
    _require_sha256_digest(
        call_context_digest, field_name="call_context_digest"
    )


def _validate_promote_input(request: PromoteQueuedRunInput) -> None:
    """校验 promotion 输入。

    :param request: promotion 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(request.session_id, field_name="session_id")
    _require_non_empty_text(
        request.run_started_event_id, field_name="run_started_event_id"
    )
    _require_non_empty_text(
        request.attempt_started_event_id, field_name="attempt_started_event_id"
    )
    _require_non_empty_text(request.attempt_id, field_name="attempt_id")
    _require_non_empty_text(request.execution_id, field_name="execution_id")
    _require_non_empty_text(
        request.dispatch_record_id, field_name="dispatch_record_id"
    )
    _require_non_empty_text(request.actor, field_name="actor")
    _require_non_empty_text(request.source, field_name="source")
    if not isinstance(request.worker_kind, WorkerKind):
        raise ValueError("worker_kind is invalid")
    _require_optional_non_empty_text(
        request.owner_host_instance_id, field_name="owner_host_instance_id"
    )


def _validate_terminal_input(request: TerminalCloseoutInput) -> None:
    """校验 terminal closeout 输入。

    :param request: terminal closeout 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(request.run_id, field_name="run_id")
    _require_non_empty_text(request.attempt_id, field_name="attempt_id")
    _require_non_empty_text(
        request.attempt_terminal_event_id, field_name="attempt_terminal_event_id"
    )
    _require_non_empty_text(
        request.run_terminal_event_id, field_name="run_terminal_event_id"
    )
    _attempt_terminal_event_type(request.attempt_terminal_status)
    _run_terminal_event_type(request.run_terminal_status)
    _require_non_empty_text(request.actor, field_name="actor")
    _require_non_empty_text(request.source, field_name="source")
    _require_non_empty_text(request.reason, field_name="reason")
    _require_optional_non_empty_text(
        request.terminal_summary_ref, field_name="terminal_summary_ref"
    )
    _require_optional_sha256_digest(
        request.terminal_summary_digest, field_name="terminal_summary_digest"
    )


def _validate_cancel_queued_input(request: CancelQueuedRunInput) -> None:
    """校验 cancel queued 输入。

    :param request: cancel queued 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _validate_common_cancel_input(
        run_id=request.run_id,
        cancel_request_event_id=request.cancel_request_event_id,
        run_cancelled_event_id=request.run_cancelled_event_id,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        reason=request.reason,
        mode=request.mode,
        call_context_digest=request.call_context_digest,
    )


def _validate_cancel_predispatch_input(
    request: CancelPredispatchStartingInput,
) -> None:
    """校验 cancel pre-dispatch 输入。

    :param request: cancel pre-dispatch 输入。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _validate_common_cancel_input(
        run_id=request.run_id,
        cancel_request_event_id=request.cancel_request_event_id,
        run_cancelled_event_id=request.run_cancelled_event_id,
        actor=request.actor,
        source=request.source,
        client_request_id=request.client_request_id,
        idempotency_key=request.idempotency_key,
        reason=request.reason,
        mode=request.mode,
        call_context_digest=request.call_context_digest,
    )
    _require_non_empty_text(
        request.attempt_cancelled_event_id,
        field_name="attempt_cancelled_event_id",
    )


def _validate_common_cancel_input(
    *,
    run_id: str,
    cancel_request_event_id: str,
    run_cancelled_event_id: str,
    actor: str,
    source: str,
    client_request_id: str,
    idempotency_key: str,
    reason: str,
    mode: CancelMode,
    call_context_digest: str,
) -> None:
    """校验 cancel 公共字段。

    :param run_id: Run id。
    :param cancel_request_event_id: CANCEL_REQUESTED event id。
    :param run_cancelled_event_id: RUN_CANCELLED event id。
    :param actor: actor。
    :param source: source。
    :param client_request_id: client request id。
    :param idempotency_key: idempotency key。
    :param reason: reason。
    :param mode: cancel mode。
    :param call_context_digest: call context digest。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    _require_non_empty_text(
        cancel_request_event_id, field_name="cancel_request_event_id"
    )
    _require_non_empty_text(
        run_cancelled_event_id, field_name="run_cancelled_event_id"
    )
    _require_non_empty_text(actor, field_name="actor")
    _require_non_empty_text(source, field_name="source")
    _require_non_empty_text(client_request_id, field_name="client_request_id")
    _require_non_empty_text(idempotency_key, field_name="idempotency_key")
    _require_non_empty_text(reason, field_name="reason")
    if mode != CancelMode.GRACEFUL:
        raise ValueError("cancel mode must be graceful")
    _require_sha256_digest(
        call_context_digest, field_name="call_context_digest"
    )


def _require_positive_sequence(value: int, field_name: str) -> None:
    """校验事件序号为正整数。

    :param value: 事件序号。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises HostDurableError: 序号小于等于零时抛出。
    """

    if value <= 0:
        raise HostDurableError(f"{field_name} must be positive")
