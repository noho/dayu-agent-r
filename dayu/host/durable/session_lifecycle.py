"""Host durable Session lifecycle command helpers。

本模块实现 Phase 3 Session / slot lifecycle 的内部命令语义：确保 slot
Session、显式创建 Session、关闭 Session。它只依赖 durable EventLog、
idempotency、state helper 与调用方提供的 transaction runner，不实现 Run /
Attempt、admission、scheduler、Engine dispatch 或 public facade。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from dayu.contracts.json_value import JsonValue
from dayu.host.api import (
    AuthorizationClaim,
    CloseSessionRequest,
    CreateSessionRequest,
    EnsureSessionRequest,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostMetadataEntry,
    OperationContext,
    SessionSnapshot,
    SessionStatus,
)
from dayu.host.durable._validation import (
    require_non_empty_text as _require_non_empty_text,
    require_sha256_digest as _require_sha256_digest,
)
from dayu.host.durable.codec import (
    canonical_json_dumps,
    format_utc_timestamp,
    sha256_digest_json,
)
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogStore,
)
from dayu.host.durable.idempotency import (
    IdempotencyRecord,
    IdempotencyResultRef,
    IdempotencyResultKind,
    IdempotencyScope,
    IdempotencyScopeKind,
    IdempotencyStore,
)
from dayu.host.durable.state import (
    SessionRow,
    SessionSlotRow,
    close_open_session_row,
    insert_session,
    insert_session_slot,
    read_session_by_id,
    read_session_slot,
    read_session_slot_by_session_id,
    session_snapshot_from_rows,
    upsert_session_slot,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner

_EVENT_TYPE_SESSION_CREATED = "SESSION_CREATED"
_EVENT_TYPE_SESSION_CLOSED = "SESSION_CLOSED"
_OPERATION_ENSURE_SESSION = IdempotencyScopeKind.ENSURE_SESSION
_OPERATION_CREATE_SESSION = IdempotencyScopeKind.CREATE_SESSION
_OPERATION_CLOSE_SESSION = IdempotencyScopeKind.CLOSE_SESSION
_IDEMPOTENCY_SCOPE_ID_HOST = "host"
_IDEMPOTENCY_RESULT_KIND_SESSION = IdempotencyResultKind.SESSION
_EVENT_SOURCE = "host.session_lifecycle"
_EVENT_ID_PREFIX = "event"
_SESSION_ID_PREFIX = "session"
_CREATED_BY_OPERATION_FIELD = "created_by_operation"
_CLOSED_BY_OPERATION_FIELD = "closed_by_operation"


@dataclass(frozen=True, slots=True)
class SessionLifecycleResult:
    """Session lifecycle 命令结果。

    :param snapshot: 命令完成后读取到的 Session snapshot。
    :param created: 本次调用是否创建了新的 Session row。
    :param rebound_slot: 本次调用是否写入或重绑定 slot。
    :param closed: 本次调用是否把 Session 从 open 推进到 closed。
    :param idempotent_replay: 是否命中既有幂等记录并返回既有结果。
    """

    snapshot: SessionSnapshot
    created: bool
    rebound_slot: bool
    closed: bool
    idempotent_replay: bool


def ensure_session(
    transaction_runner: HostTransactionRunner,
    request: EnsureSessionRequest,
) -> SessionLifecycleResult:
    """确保 ``(scope, slot_key)`` 绑定到一个 durable Session。

    :param transaction_runner: Host durable write transaction runner。
    :param request: ensure session 请求。
    :returns: Session lifecycle 结果；slot 已存在时返回既有 Session。
    :raises HostApiError: slot 指向的 Session 缺失等 durable 不一致时抛出。
    :raises HostDurableError: durable 编码或 SQLite 写入失败时由底层抛出。
    """

    return transaction_runner.run_write(
        _EnsureSessionOperation(request=request, event_log_store=EventLogStore())
    )


def create_session(
    transaction_runner: HostTransactionRunner,
    request: CreateSessionRequest,
    *,
    caller_semantic_digest: str,
) -> SessionLifecycleResult:
    """显式创建 Session，并可选择原子重绑定 slot。

    :param transaction_runner: Host durable write transaction runner。
    :param request: create session 请求。
    :param caller_semantic_digest: 上层调用方语义输入摘要。
    :returns: Session lifecycle 结果；同幂等 key 同 digest 返回既有 Session。
    :raises HostApiError: 同幂等 key 不同 digest 时抛出 idempotency conflict。
    :raises HostDurableError: durable 编码或 SQLite 写入失败时由底层抛出。
    """

    _require_sha256_digest(
        caller_semantic_digest, field_name="caller_semantic_digest"
    )
    return transaction_runner.run_write(
        _CreateSessionOperation(
            request=request,
            caller_semantic_digest=caller_semantic_digest,
            event_log_store=EventLogStore(),
            idempotency_store=IdempotencyStore(),
        )
    )


def close_session(
    transaction_runner: HostTransactionRunner,
    session_id: str,
    request: CloseSessionRequest,
    *,
    caller_semantic_digest: str,
) -> SessionLifecycleResult:
    """关闭 open Session，不修改该 Session 下已有 Run rows。

    :param transaction_runner: Host durable write transaction runner。
    :param session_id: 目标 Session id。
    :param request: close session 请求。
    :param caller_semantic_digest: 上层调用方语义输入摘要。
    :returns: Session lifecycle 结果；同幂等 key 同 digest 返回既有 closed snapshot。
    :raises HostApiError: Session 缺失、状态非法或幂等冲突时抛出。
    :raises HostDurableError: durable 编码或 SQLite 写入失败时由底层抛出。
    """

    _require_non_empty_text(session_id, field_name="session_id")
    _require_sha256_digest(
        caller_semantic_digest, field_name="caller_semantic_digest"
    )
    return transaction_runner.run_write(
        _CloseSessionOperation(
            session_id=session_id,
            request=request,
            caller_semantic_digest=caller_semantic_digest,
            event_log_store=EventLogStore(),
            idempotency_store=IdempotencyStore(),
        )
    )


@dataclass(frozen=True, slots=True)
class _EnsureSessionOperation:
    """``ensure_session`` transaction body。"""

    request: EnsureSessionRequest
    event_log_store: EventLogStore

    def __call__(self, transaction: HostTransaction) -> SessionLifecycleResult:
        """执行 ensure session transaction body。

        :param transaction: 当前 Host transaction。
        :returns: Session lifecycle 结果。
        :raises HostApiError: slot 指向的 Session 缺失时抛出。
        """

        metadata_json = _metadata_json(self.request.metadata)
        existing_slot = read_session_slot(
            transaction, self.request.scope, self.request.slot_key
        )
        if existing_slot is not None:
            session = _require_session(
                transaction,
                existing_slot.session_id,
                missing_message="Session slot points to missing Session",
            )
            return SessionLifecycleResult(
                snapshot=session_snapshot_from_rows(
                    transaction, session, existing_slot
                ),
                created=False,
                rebound_slot=False,
                closed=False,
                idempotent_replay=False,
            )

        session_id = _new_prefixed_id(_SESSION_ID_PREFIX)
        now = datetime.now(UTC)
        created_at = format_utc_timestamp(now)
        metadata_digest = _metadata_digest(self.request.metadata)
        event = self.event_log_store.append_event(
            transaction,
            _session_created_event_request(
                event_id=_new_prefixed_id(_EVENT_ID_PREFIX),
                session_id=session_id,
                occurred_at=now,
                actor=None,
                source=_EVENT_SOURCE,
                client_request_id=None,
                idempotency_key=None,
                slot_scope=self.request.scope,
                slot_key=self.request.slot_key,
                metadata_digest=metadata_digest,
                created_by_operation=_OPERATION_ENSURE_SESSION,
                call_context_digest=_ensure_call_context_digest(),
            ),
        ).row
        session = SessionRow(
            session_id=session_id,
            status=SessionStatus.OPEN,
            metadata_json=metadata_json,
            created_event_id=event.event_id,
            created_event_sequence=event.event_sequence,
            closed_event_id=None,
            closed_event_sequence=None,
            created_at=created_at,
            closed_at=None,
        )
        slot = SessionSlotRow(
            scope=self.request.scope,
            slot_key=self.request.slot_key,
            session_id=session_id,
            bound_event_id=event.event_id,
            bound_event_sequence=event.event_sequence,
            metadata_json=metadata_json,
            updated_at=created_at,
        )
        insert_session(transaction, session)
        insert_session_slot(transaction, slot)
        return SessionLifecycleResult(
            snapshot=session_snapshot_from_rows(transaction, session, slot),
            created=True,
            rebound_slot=True,
            closed=False,
            idempotent_replay=False,
        )


@dataclass(frozen=True, slots=True)
class _CreateSessionOperation:
    """``create_session`` transaction body。"""

    request: CreateSessionRequest
    caller_semantic_digest: str
    event_log_store: EventLogStore
    idempotency_store: IdempotencyStore

    def __call__(self, transaction: HostTransaction) -> SessionLifecycleResult:
        """执行 create session transaction body。

        :param transaction: 当前 Host transaction。
        :returns: Session lifecycle 结果。
        :raises HostApiError: 幂等冲突或既有结果缺失时抛出。
        """

        semantic_digest = _create_session_semantic_digest(
            self.request, caller_semantic_digest=self.caller_semantic_digest
        )
        scope = _idempotency_scope(
            operation=_OPERATION_CREATE_SESSION,
            scope_id=_IDEMPOTENCY_SCOPE_ID_HOST,
            idempotency_key=self.request.client_request_id,
        )
        existing = self.idempotency_store.read_idempotency_record(transaction, scope)
        if existing is not None:
            _raise_if_digest_conflict(existing, semantic_digest)
            return _idempotent_session_result(transaction, existing)

        session_id = _new_prefixed_id(_SESSION_ID_PREFIX)
        now = datetime.now(UTC)
        created_at = format_utc_timestamp(now)
        metadata_json = _metadata_json(self.request.metadata)
        metadata_digest = _metadata_digest(self.request.metadata)
        call_context_digest = _call_context_digest(self.request.context)
        event = self.event_log_store.append_event(
            transaction,
            _session_created_event_request(
                event_id=_new_prefixed_id(_EVENT_ID_PREFIX),
                session_id=session_id,
                occurred_at=now,
                actor=self.request.context.actor,
                source=self.request.context.source,
                client_request_id=self.request.client_request_id,
                idempotency_key=self.request.client_request_id,
                slot_scope=self.request.scope,
                slot_key=self.request.slot_key,
                metadata_digest=metadata_digest,
                created_by_operation=_OPERATION_CREATE_SESSION,
                call_context_digest=call_context_digest,
            ),
        ).row
        session = SessionRow(
            session_id=session_id,
            status=SessionStatus.OPEN,
            metadata_json=metadata_json,
            created_event_id=event.event_id,
            created_event_sequence=event.event_sequence,
            closed_event_id=None,
            closed_event_sequence=None,
            created_at=created_at,
            closed_at=None,
        )
        insert_session(transaction, session)
        slot = _create_bound_slot(self.request, session, event.event_sequence)
        if slot is not None:
            upsert_session_slot(transaction, slot)
        self.idempotency_store.record_idempotent_result(
            transaction,
            scope,
            semantic_digest,
            IdempotencyResultRef(
                result_kind=_IDEMPOTENCY_RESULT_KIND_SESSION,
                result_ref=session_id,
                created_event_id=event.event_id,
                created_event_sequence=event.event_sequence,
            ),
        )
        return SessionLifecycleResult(
            snapshot=session_snapshot_from_rows(transaction, session, slot),
            created=True,
            rebound_slot=slot is not None,
            closed=False,
            idempotent_replay=False,
        )


@dataclass(frozen=True, slots=True)
class _CloseSessionOperation:
    """``close_session`` transaction body。"""

    session_id: str
    request: CloseSessionRequest
    caller_semantic_digest: str
    event_log_store: EventLogStore
    idempotency_store: IdempotencyStore

    def __call__(self, transaction: HostTransaction) -> SessionLifecycleResult:
        """执行 close session transaction body。

        :param transaction: 当前 Host transaction。
        :returns: Session lifecycle 结果。
        :raises HostApiError: Session 缺失、状态非法或幂等冲突时抛出。
        """

        semantic_digest = _close_session_semantic_digest(
            self.request, caller_semantic_digest=self.caller_semantic_digest
        )
        scope = _idempotency_scope(
            operation=_OPERATION_CLOSE_SESSION,
            scope_id=self.session_id,
            idempotency_key=self.request.client_request_id,
        )
        existing = self.idempotency_store.read_idempotency_record(transaction, scope)
        if existing is not None:
            _raise_if_digest_conflict(existing, semantic_digest)
            return _idempotent_session_result(transaction, existing)

        session = read_session_by_id(transaction, self.session_id)
        if session is None:
            raise HostApiError(
                code=HostApiErrorCode.NOT_FOUND,
                message="Session not found",
                retryable=False,
            )
        if session.status != SessionStatus.OPEN:
            raise HostApiError(
                code=HostApiErrorCode.INVALID_STATE,
                message="Session is not open",
                retryable=False,
            )

        now = datetime.now(UTC)
        closed_at = format_utc_timestamp(now)
        call_context_digest = _call_context_digest(self.request.context)
        event = self.event_log_store.append_event(
            transaction,
            _session_closed_event_request(
                event_id=_new_prefixed_id(_EVENT_ID_PREFIX),
                session_id=self.session_id,
                occurred_at=now,
                actor=self.request.context.actor,
                source=self.request.context.source,
                client_request_id=self.request.client_request_id,
                idempotency_key=self.request.client_request_id,
                reason=self.request.reason,
                call_context_digest=call_context_digest,
            ),
        ).row
        updated = close_open_session_row(
            transaction,
            session_id=self.session_id,
            closed_event_id=event.event_id,
            closed_event_sequence=event.event_sequence,
            closed_at=closed_at,
        )
        if not updated:
            _raise_close_cas_lost(transaction, self.session_id)
        self.idempotency_store.record_idempotent_result(
            transaction,
            scope,
            semantic_digest,
            IdempotencyResultRef(
                result_kind=_IDEMPOTENCY_RESULT_KIND_SESSION,
                result_ref=self.session_id,
                created_event_id=event.event_id,
                created_event_sequence=event.event_sequence,
            ),
        )
        closed_session = _require_session(
            transaction,
            self.session_id,
            missing_message="Closed Session disappeared",
        )
        return SessionLifecycleResult(
            snapshot=session_snapshot_from_rows(
                transaction,
                closed_session,
                read_session_slot_by_session_id(transaction, self.session_id),
            ),
            created=False,
            rebound_slot=False,
            closed=True,
            idempotent_replay=False,
        )


def _metadata_json(entries: tuple[HostMetadataEntry, ...]) -> str:
    """把 metadata entries 编码为 canonical JSON 文本。

    :param entries: Host metadata entries。
    :returns: canonical JSON 文本。
    :raises TypeError: metadata value 不是 JSON 可序列化值时抛出。
    :raises ValueError: metadata value 含非法 JSON 数值时抛出。
    """

    return canonical_json_dumps(_metadata_json_value(entries))


def _metadata_digest(entries: tuple[HostMetadataEntry, ...]) -> str:
    """计算 metadata entries 的 canonical digest。

    :param entries: Host metadata entries。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(_metadata_json_value(entries))


def _metadata_json_value(entries: tuple[HostMetadataEntry, ...]) -> JsonValue:
    """把 metadata entries 转为 JSON 值。

    :param entries: Host metadata entries。
    :returns: JSON 数组值，按调用方给定顺序保存。
    """

    values: list[JsonValue] = []
    for entry in entries:
        values.append({"key": entry.key, "value": entry.value})
    return values


def _call_context_digest(context: HostCallContext) -> str:
    """计算调用上下文 digest，排除 tracing 用 ``request_id``。

    :param context: Host call context。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(_call_context_json_value(context))


def _ensure_call_context_digest() -> str:
    """计算 ``ensure_session`` 无调用上下文时的固定 digest。

    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {"operation": _OPERATION_ENSURE_SESSION, "context": None}
    )


def _call_context_json_value(context: HostCallContext) -> JsonValue:
    """把调用上下文转成参与审计 digest 的 JSON 值。

    :param context: Host call context。
    :returns: JSON 对象值。
    """

    return {
        "actor": context.actor,
        "source": context.source,
        "authorization_claims": _authorization_claims_json_value(
            context.authorization_claims
        ),
        "operation_context": _operation_context_json_value(
            context.operation_context
        ),
    }


def _authorization_claims_json_value(
    claims: tuple[AuthorizationClaim, ...]
) -> JsonValue:
    """把授权声明转成 JSON 值。

    :param claims: 授权声明元组。
    :returns: JSON 数组值。
    """

    values: list[JsonValue] = []
    for claim in claims:
        values.append({"name": claim.name, "value": claim.value})
    return values


def _operation_context_json_value(context: OperationContext) -> JsonValue:
    """把操作上下文转成 JSON 值。

    :param context: 操作上下文。
    :returns: JSON 对象值。
    """

    return {
        "operation_name": context.operation_name,
        "operation_kind": context.operation_kind,
        "business_domain": context.business_domain,
        "business_object_type": context.business_object_type,
        "business_object_id": context.business_object_id,
        "scenario": context.scenario,
        "correlation_id": context.correlation_id,
    }


def _create_session_semantic_digest(
    request: CreateSessionRequest, *, caller_semantic_digest: str
) -> str:
    """计算 ``create_session`` semantic input digest。

    :param request: create session 请求。
    :param caller_semantic_digest: 调用方语义输入摘要。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_CREATE_SESSION,
            "bind_slot": request.bind_slot,
            "scope": request.scope,
            "slot_key": request.slot_key,
            "metadata_digest": _metadata_digest(request.metadata),
            "caller_semantic_digest": caller_semantic_digest,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _close_session_semantic_digest(
    request: CloseSessionRequest, *, caller_semantic_digest: str
) -> str:
    """计算 ``close_session`` semantic input digest。

    :param request: close session 请求。
    :param caller_semantic_digest: 调用方语义输入摘要。
    :returns: ``sha256:<hex>`` digest。
    """

    return sha256_digest_json(
        {
            "operation": _OPERATION_CLOSE_SESSION,
            "reason": request.reason,
            "caller_semantic_digest": caller_semantic_digest,
            "call_context_digest": _call_context_digest(request.context),
        }
    )


def _session_created_event_request(
    *,
    event_id: str,
    session_id: str,
    occurred_at: datetime,
    actor: str | None,
    source: str | None,
    client_request_id: str | None,
    idempotency_key: str | None,
    slot_scope: str | None,
    slot_key: str | None,
    metadata_digest: str,
    created_by_operation: str,
    call_context_digest: str,
) -> EventLogAppendRequest:
    """构造 ``SESSION_CREATED`` EventLog append 请求。

    :param event_id: 事件 id。
    :param session_id: Session id。
    :param occurred_at: 事件发生时间。
    :param actor: 调用主体。
    :param source: 调用来源。
    :param client_request_id: 客户端请求 id。
    :param idempotency_key: 幂等 key。
    :param slot_scope: slot scope。
    :param slot_key: slot key。
    :param metadata_digest: metadata digest。
    :param created_by_operation: 创建该 Session 的操作名。
    :param call_context_digest: 调用上下文 digest。
    :returns: EventLog append 请求。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=session_id,
        run_id=None,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_SESSION_CREATED,
        occurred_at=occurred_at,
        actor=actor,
        source=source,
        client_request_id=client_request_id,
        idempotency_key=idempotency_key,
        policy_decision=None,
        reason=None,
        payload_json={
            "session_id": session_id,
            "metadata_digest": metadata_digest,
            "slot_scope": slot_scope,
            "slot_key": slot_key,
            _CREATED_BY_OPERATION_FIELD: created_by_operation,
            "call_context_digest": call_context_digest,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _session_closed_event_request(
    *,
    event_id: str,
    session_id: str,
    occurred_at: datetime,
    actor: str,
    source: str,
    client_request_id: str,
    idempotency_key: str,
    reason: str,
    call_context_digest: str,
) -> EventLogAppendRequest:
    """构造 ``SESSION_CLOSED`` EventLog append 请求。

    :param event_id: 事件 id。
    :param session_id: Session id。
    :param occurred_at: 事件发生时间。
    :param actor: 调用主体。
    :param source: 调用来源。
    :param client_request_id: 客户端请求 id。
    :param idempotency_key: 幂等 key。
    :param reason: 关闭原因。
    :param call_context_digest: 调用上下文 digest。
    :returns: EventLog append 请求。
    """

    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=session_id,
        run_id=None,
        attempt_id=None,
        execution_id=None,
        event_type=_EVENT_TYPE_SESSION_CLOSED,
        occurred_at=occurred_at,
        actor=actor,
        source=source,
        client_request_id=client_request_id,
        idempotency_key=idempotency_key,
        policy_decision=None,
        reason={"reason": reason},
        payload_json={
            "session_id": session_id,
            "reason": reason,
            _CLOSED_BY_OPERATION_FIELD: _OPERATION_CLOSE_SESSION,
            "call_context_digest": call_context_digest,
        },
        payload_ref=None,
        payload_digest=None,
    )


def _create_bound_slot(
    request: CreateSessionRequest,
    session: SessionRow,
    bound_event_sequence: int,
) -> SessionSlotRow | None:
    """为 ``create_session(bind_slot=true)`` 构造 slot row。

    :param request: create session 请求。
    :param session: 新创建的 Session row。
    :param bound_event_sequence: 绑定事实使用的 EventLog 序号。
    :returns: 需要绑定时返回 slot row，否则返回 ``None``。
    """

    if not request.bind_slot:
        return None
    if request.scope is None or request.slot_key is None:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="CreateSessionRequest slot binding is incomplete",
            retryable=False,
        )
    return SessionSlotRow(
        scope=request.scope,
        slot_key=request.slot_key,
        session_id=session.session_id,
        bound_event_id=session.created_event_id,
        bound_event_sequence=bound_event_sequence,
        metadata_json=session.metadata_json,
        updated_at=session.created_at,
    )


def _idempotency_scope(
    *,
    operation: IdempotencyScopeKind,
    scope_id: str,
    idempotency_key: str,
) -> IdempotencyScope:
    """构造 lifecycle 幂等 scope。

    :param operation: 操作名。
    :param scope_id: 幂等 scope id。
    :param idempotency_key: 幂等 key。
    :returns: ``IdempotencyScope``。
    """

    return IdempotencyScope(
        scope_kind=operation,
        scope_id=scope_id,
        idempotency_key=idempotency_key,
    )


def _raise_if_digest_conflict(
    record: IdempotencyRecord, semantic_digest: str
) -> None:
    """检查幂等记录 digest 是否冲突。

    :param record: 已存在的幂等记录。
    :param semantic_digest: 本次请求的 semantic digest。
    :returns: ``None``。
    :raises HostApiError: digest 不一致时抛出 idempotency conflict。
    """

    if record.semantic_input_digest != semantic_digest:
        raise HostApiError(
            code=HostApiErrorCode.IDEMPOTENCY_CONFLICT,
            message="Idempotency key already exists with different semantic digest",
            retryable=False,
        )


def _idempotent_session_result(
    transaction: HostTransaction, record: IdempotencyRecord
) -> SessionLifecycleResult:
    """把既有幂等记录解析为 Session lifecycle 结果。

    :param transaction: 当前 Host transaction。
    :param record: 已存在的幂等记录。
    :returns: Session lifecycle 结果。
    :raises HostApiError: 结果类型错误或结果 Session 缺失时抛出。
    """

    if record.result_kind != _IDEMPOTENCY_RESULT_KIND_SESSION:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Idempotency record result kind is not session",
            retryable=False,
        )
    session = _require_session(
        transaction,
        record.result_ref,
        missing_message="Idempotency record points to missing Session",
    )
    return SessionLifecycleResult(
        snapshot=session_snapshot_from_rows(
            transaction,
            session,
            read_session_slot_by_session_id(transaction, session.session_id),
        ),
        created=False,
        rebound_slot=False,
        closed=False,
        idempotent_replay=True,
    )


def _require_session(
    transaction: HostTransaction, session_id: str, *, missing_message: str
) -> SessionRow:
    """读取必然存在的 Session。

    :param transaction: 当前 Host transaction。
    :param session_id: Session id。
    :param missing_message: 缺失时的错误消息。
    :returns: Session row。
    :raises HostApiError: Session 缺失时抛出。
    """

    session = read_session_by_id(transaction, session_id)
    if session is None:
        raise HostApiError(
            code=HostApiErrorCode.NOT_FOUND,
            message=missing_message,
            retryable=False,
        )
    return session


def _raise_close_cas_lost(
    transaction: HostTransaction, session_id: str
) -> None:
    """根据 close CAS loser 后的最新状态抛出结构化错误。

    :param transaction: 当前 Host transaction。
    :param session_id: Session id。
    :returns: 不返回；总是抛出异常。
    :raises HostApiError: Session 缺失或状态非法时抛出。
    """

    latest = read_session_by_id(transaction, session_id)
    if latest is None:
        raise HostApiError(
            code=HostApiErrorCode.NOT_FOUND,
            message="Session not found",
            retryable=False,
        )
    raise HostApiError(
        code=HostApiErrorCode.INVALID_STATE,
        message="Session is not open",
        retryable=False,
    )


def _new_prefixed_id(prefix: str) -> str:
    """生成带稳定诊断前缀的随机 id。

    :param prefix: id 前缀。
    :returns: ``<prefix>-<uuid4 hex>``。
    """

    _require_non_empty_text(prefix, field_name="prefix")
    return f"{prefix}-{uuid4().hex}"
