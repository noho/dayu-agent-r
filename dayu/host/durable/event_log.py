"""Host durable EventLog append 与读取 primitive。

本模块只实现 EventLog ledger 的最小持久化语义：在调用方提供的
``HostTransaction`` 中追加事件、处理 ``event_id`` 幂等重复、读取单条事件
和按全局 ``event_sequence`` cursor 补读。它不实现 Host command path、
EngineEvent ingest、projection、audit、stream fanout、payload descriptor 写入
或 Session / Run / Attempt 状态索引。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.durable._validation import (
    optional_text as _optional_text,
    require_int as _require_int,
    require_non_empty_text as _require_non_empty_text,
    require_optional_non_empty_text as _require_optional_non_empty_text,
    require_text as _require_text,
)
from dayu.host.durable.artifact import LocalArtifactRef, validate_artifact_ref
from dayu.host.durable.codec import (
    canonical_json_dumps,
    format_utc_timestamp,
    is_sha256_digest,
    sha256_digest_json,
)
from dayu.host.durable.errors import (
    HostDurableError,
    HostEventIdentityConflictError,
    HostPayloadReferenceError,
)
from dayu.host.durable.payload import PayloadKind, read_payload_descriptor
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.transaction import HostRow, HostTransaction

_MIN_READ_LIMIT = 1
_MIN_EVENT_CURSOR = 0


class EventClass(StrEnum):
    """EventLog 事件分类。

    该分类只描述 ledger row 的事件用途，不承载 command path 或 projection
    消费语义。
    """

    CANONICAL_FACT = "canonical_fact"
    PREVIEW = "preview"
    DIAGNOSTIC = "diagnostic"
    PROJECTION_SIGNAL = "projection_signal"


@dataclass(frozen=True, slots=True)
class EventLogAppendRequest:
    """EventLog append 请求。

    :param event_id: 调用方分配的全局事件标识。
    :param event_class: 事件分类。
    :param session_id: 事件所属 session 标识。
    :param run_id: 事件所属 run 标识；无 run 语义时为 ``None``。
    :param attempt_id: 事件所属 attempt 标识；无 attempt 语义时为 ``None``。
    :param execution_id: 事件所属 execution 标识；无 execution 语义时为 ``None``。
    :param event_type: 事件类型文本。
    :param occurred_at: 调用方记录的事件发生时间，必须为 timezone-aware datetime。
    :param actor: 事件 actor 文本。
    :param source: 事件 source 文本。
    :param client_request_id: 客户端请求标识。
    :param idempotency_key: 幂等 key。
    :param policy_decision: policy decision JSON 值；无值时为 ``None``。
    :param reason: reason JSON 值；无值时为 ``None``。
    :param payload_json: inline payload JSON 值；无 inline payload 时传 ``None``。
    :param payload_ref: payload descriptor 引用。
    :param payload_digest: payload descriptor 对应 digest。
    """

    event_id: str
    event_class: EventClass
    session_id: str
    run_id: str | None
    attempt_id: str | None
    execution_id: str | None
    event_type: str
    occurred_at: datetime
    actor: str | None
    source: str | None
    client_request_id: str | None
    idempotency_key: str | None
    policy_decision: JsonValue | None
    reason: JsonValue | None
    payload_json: JsonValue
    payload_ref: str | None
    payload_digest: str | None


@dataclass(frozen=True, slots=True)
class EventLogRow:
    """EventLog 已持久化 row。

    :param event_sequence: SQLite 分配的全局递增 cursor。
    :param event_id: 全局事件标识。
    :param event_body_digest: request-assigned 事件体 digest。
    :param event_class: 事件分类。
    :param session_id: session 标识。
    :param run_id: run 标识。
    :param attempt_id: attempt 标识。
    :param execution_id: execution 标识。
    :param event_type: 事件类型。
    :param occurred_at: 固定 UTC 微秒精度 ``Z`` timestamp 文本。
    :param actor: actor 文本。
    :param source: source 文本。
    :param client_request_id: 客户端请求标识。
    :param idempotency_key: 幂等 key。
    :param policy_decision_json: canonical policy decision JSON 文本。
    :param reason_json: canonical reason JSON 文本。
    :param payload_json: canonical payload JSON 文本。
    :param payload_ref: payload descriptor 引用。
    :param payload_digest: payload descriptor digest。
    :param appended_at: durable append UTC timestamp 文本。
    """

    event_sequence: int
    event_id: str
    event_body_digest: str
    event_class: EventClass
    session_id: str
    run_id: str | None
    attempt_id: str | None
    execution_id: str | None
    event_type: str
    occurred_at: str
    actor: str | None
    source: str | None
    client_request_id: str | None
    idempotency_key: str | None
    policy_decision_json: str | None
    reason_json: str | None
    payload_json: str
    payload_ref: str | None
    payload_digest: str | None
    appended_at: str


@dataclass(frozen=True, slots=True)
class EventPayloadTextEqualsFilter:
    """EventLog inline payload 文本字段等值过滤条件。

    该类型只表达 durable-neutral JSON payload 字段过滤，不承载
    context governance、policy 或 Engine 语义。

    :param field_name: payload JSON 映射中的字段名。
    :param expected_value: 期望匹配的文本值。
    :param allowed_values: 字段允许的文本值集合；空 tuple 表示只要求非空文本。
    """

    field_name: str
    expected_value: str
    allowed_values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """校验 payload 过滤条件。

        :returns: ``None``。
        :raises HostDurableError: 字段名或期望值不是非空文本时抛出。
        """

        _require_non_empty_text(self.field_name, field_name="payload_filter.field_name")
        _require_non_empty_text(
            self.expected_value, field_name="payload_filter.expected_value"
        )
        _require_text_tuple(
            self.allowed_values, field_name="payload_filter.allowed_values"
        )
        if (
            len(self.allowed_values) > 0
            and self.expected_value not in self.allowed_values
        ):
            raise HostDurableError(
                "payload_filter.expected_value must be present in allowed_values"
            )


@dataclass(frozen=True, slots=True)
class EventLogAppendResult:
    """EventLog append 结果。

    :param row: 已存在或新插入的 EventLog row。
    :param inserted: 本次调用是否插入了新 row。
    """

    row: EventLogRow
    inserted: bool


class EventLogStore:
    """EventLog primitive 的轻量方法集合。

    该类不持有连接、不创建 transaction，也不实现 command path；所有持久化
    mutation 都必须发生在调用方传入的 ``HostTransaction`` 中。
    """

    def append_event(
        self, transaction: HostTransaction, request: EventLogAppendRequest
    ) -> EventLogAppendResult:
        """追加 EventLog row。

        :param transaction: 调用方提供的 Host durable transaction。
        :param request: EventLog append 请求。
        :returns: append 结果；重复同体 ``event_id`` 返回既有 row。
        :raises HostDurableError: 请求字段无效时抛出。
        :raises HostEventIdentityConflictError: 同一 ``event_id`` 对应不同事件体时抛出。
        :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
        """

        return append_event(transaction, request)

    def read_event_by_id(
        self, transaction: HostTransaction, event_id: str
    ) -> EventLogRow | None:
        """按 ``event_id`` 读取 EventLog row。

        :param transaction: 调用方提供的 Host durable transaction。
        :param event_id: 全局事件标识。
        :returns: 找到时返回 EventLog row，否则返回 ``None``。
        :raises HostDurableError: ``event_id`` 无效时抛出。
        """

        return read_event_by_id(transaction, event_id)

    def read_events_after(
        self, transaction: HostTransaction, cursor: int, *, limit: int
    ) -> tuple[EventLogRow, ...]:
        """按全局 cursor 读取后续 EventLog rows。

        :param transaction: 调用方提供的 Host durable transaction。
        :param cursor: 已消费的全局 ``event_sequence``。
        :param limit: 最大返回 row 数，必须为正数。
        :returns: 按 ``event_sequence`` 升序排列的 EventLog row 元组。
        :raises HostDurableError: cursor 或 limit 无效时抛出。
        """

        return read_events_after(transaction, cursor, limit=limit)

    def read_latest_run_event_by_type(
        self,
        transaction: HostTransaction,
        *,
        run_id: str,
        event_type: str,
    ) -> EventLogRow | None:
        """读取某个 Run 下最近的一条指定类型事件。

        :param transaction: 调用方提供的 Host durable transaction。
        :param run_id: 目标 Run id。
        :param event_type: 目标 event type。
        :returns: 找到时返回最近事件，否则返回 ``None``。
        :raises HostDurableError: 输入字段无效时抛出。
        """

        return read_latest_run_event_by_type(
            transaction,
            run_id=run_id,
            event_type=event_type,
        )

    def count_committed_events_by_run_and_type(
        self,
        transaction: HostTransaction,
        *,
        run_id: str,
        event_type: str,
        payload_filter: EventPayloadTextEqualsFilter | None = None,
    ) -> int:
        """统计某个 Run 下已提交 canonical fact 数量。

        :param transaction: 调用方提供的 Host durable transaction。
        :param run_id: 目标 Run id。
        :param event_type: 目标 event type。
        :param payload_filter: 可选 inline payload 文本字段过滤条件。
        :returns: 匹配的 canonical fact 数量。
        :raises HostDurableError: 输入非法或 payload 无法验证时抛出。
        """

        return count_committed_events_by_run_and_type(
            transaction,
            run_id=run_id,
            event_type=event_type,
            payload_filter=payload_filter,
        )

    def count_recovery_dispatches_for_run(
        self,
        transaction: HostTransaction,
        *,
        run_id: str,
    ) -> int:
        """统计某个 Run 已提交的 recovery dispatch 次数。

        :param transaction: 调用方提供的 Host durable transaction。
        :param run_id: 目标 Run id。
        :returns: 该 Run 下 canonical ``RUN_STARTED`` 且 payload
            ``start_reason`` 为 ``recovery`` 的事件数量。
        :raises HostDurableError: 输入非法或 payload 无法验证时抛出。
        """

        return count_recovery_dispatches_for_run(transaction, run_id=run_id)


def append_event(
    transaction: HostTransaction, request: EventLogAppendRequest
) -> EventLogAppendResult:
    """在调用方 transaction 内追加 EventLog row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param request: EventLog append 请求。
    :returns: append 结果；重复同体 ``event_id`` 返回既有 row 且 ``inserted=False``。
    :raises HostDurableError: 请求字段无效时抛出。
    :raises HostEventIdentityConflictError: 同一 ``event_id`` 对应不同事件体时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_append_request(request)
    _validate_existing_payload_descriptor(
        transaction, request.payload_ref, request.payload_digest
    )
    try:
        encoded = _encode_append_request(request)
    except (TypeError, ValueError) as exc:
        raise HostDurableError("EventLog append request encoding failed") from exc
    _validate_canonical_inline_payload_size(transaction, request, encoded)
    existing = read_event_by_id(transaction, request.event_id)
    if existing is not None:
        if existing.event_body_digest == encoded.event_body_digest:
            return EventLogAppendResult(row=existing, inserted=False)
        raise HostEventIdentityConflictError(
            "EventLog event_id already exists with different event body"
        )

    appended_at = format_utc_timestamp(datetime.now(UTC))
    transaction.execute(
        f"""
        INSERT INTO {TABLE_EVENT_LOG} (
          event_id,
          event_body_digest,
          event_class,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          event_type,
          occurred_at,
          actor,
          source,
          client_request_id,
          idempotency_key,
          policy_decision_json,
          reason_json,
          payload_json,
          payload_ref,
          payload_digest,
          appended_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            request.event_id,
            encoded.event_body_digest,
            request.event_class.value,
            request.session_id,
            request.run_id,
            request.attempt_id,
            request.execution_id,
            request.event_type,
            encoded.occurred_at,
            request.actor,
            request.source,
            request.client_request_id,
            request.idempotency_key,
            encoded.policy_decision_json,
            encoded.reason_json,
            encoded.payload_json,
            request.payload_ref,
            request.payload_digest,
            appended_at,
        ),
    )
    row = read_event_by_id(transaction, request.event_id)
    if row is None:
        raise HostDurableError("EventLog append did not return inserted row")
    return EventLogAppendResult(row=row, inserted=True)


def read_event_by_id(transaction: HostTransaction, event_id: str) -> EventLogRow | None:
    """按 ``event_id`` 读取 EventLog row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param event_id: 全局事件标识。
    :returns: 找到时返回 EventLog row，否则返回 ``None``。
    :raises HostDurableError: ``event_id`` 为空时抛出。
    """

    _require_non_empty_text(event_id, field_name="event_id")
    row = transaction.fetchone(
        f"""
        SELECT
          event_sequence,
          event_id,
          event_body_digest,
          event_class,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          event_type,
          occurred_at,
          actor,
          source,
          client_request_id,
          idempotency_key,
          policy_decision_json,
          reason_json,
          payload_json,
          payload_ref,
          payload_digest,
          appended_at
        FROM {TABLE_EVENT_LOG}
        WHERE event_id = ?
        """,
        (event_id,),
    )
    if row is None:
        return None
    return _event_log_row_from_host_row(row)


def read_events_after(
    transaction: HostTransaction, cursor: int, *, limit: int
) -> tuple[EventLogRow, ...]:
    """按全局 ``event_sequence`` cursor 读取 EventLog rows。

    :param transaction: 调用方提供的 Host durable transaction。
    :param cursor: 已消费的全局 ``event_sequence``；必须大于等于零。
    :param limit: 最大返回 row 数；必须为正数。
    :returns: 按 ``event_sequence`` 升序排列的 EventLog row 元组。
    :raises HostDurableError: cursor 或 limit 无效时抛出。
    """

    if cursor < _MIN_EVENT_CURSOR:
        raise HostDurableError("EventLog cursor must be non-negative")
    if limit < _MIN_READ_LIMIT:
        raise HostDurableError("EventLog read limit must be positive")
    rows = transaction.fetchall(
        f"""
        SELECT
          event_sequence,
          event_id,
          event_body_digest,
          event_class,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          event_type,
          occurred_at,
          actor,
          source,
          client_request_id,
          idempotency_key,
          policy_decision_json,
          reason_json,
          payload_json,
          payload_ref,
          payload_digest,
          appended_at
        FROM {TABLE_EVENT_LOG}
        WHERE event_sequence > ?
        ORDER BY event_sequence ASC
        LIMIT ?
        """,
        (cursor, limit),
    )
    return tuple(_event_log_row_from_host_row(row) for row in rows)


def read_latest_run_event_by_type(
    transaction: HostTransaction,
    *,
    run_id: str,
    event_type: str,
) -> EventLogRow | None:
    """读取某个 Run 下最近的一条指定类型事件。

    :param transaction: 调用方提供的 Host durable transaction。
    :param run_id: 目标 Run id。
    :param event_type: 目标 event type。
    :returns: 找到时返回最近事件，否则返回 ``None``。
    :raises HostDurableError: 输入字段无效时抛出。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    _require_non_empty_text(event_type, field_name="event_type")
    row = transaction.fetchone(
        f"""
        SELECT
          event_sequence,
          event_id,
          event_body_digest,
          event_class,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          event_type,
          occurred_at,
          actor,
          source,
          client_request_id,
          idempotency_key,
          policy_decision_json,
          reason_json,
          payload_json,
          payload_ref,
          payload_digest,
          appended_at
        FROM {TABLE_EVENT_LOG}
        WHERE run_id = ? AND event_type = ?
        ORDER BY event_sequence DESC
        LIMIT 1
        """,
        (run_id, event_type),
    )
    if row is None:
        return None
    return _event_log_row_from_host_row(row)


def count_committed_events_by_run_and_type(
    transaction: HostTransaction,
    *,
    run_id: str,
    event_type: str,
    payload_filter: EventPayloadTextEqualsFilter | None = None,
) -> int:
    """统计某个 Run 下已提交 canonical fact 数量。

    该 helper 供 Context Governance 在同一 write transaction 内查询
    per-run compact 次数。传入 ``payload_filter`` 时会解析并校验每条匹配
    event 的 inline payload；payload 缺失、损坏、字段缺失或字段值非法会
    fail-closed 抛出 durable error。过滤条件本身不表达 Host policy 语义。

    :param transaction: 调用方提供的 Host durable transaction。
    :param run_id: 目标 Run id。
    :param event_type: 目标 event type。
    :param payload_filter: 可选 inline payload 文本字段过滤条件。
    :returns: 匹配的 canonical fact 数量。
    :raises HostDurableError: 输入非法或 payload 无法验证时抛出。
    """

    _require_non_empty_text(run_id, field_name="run_id")
    _require_non_empty_text(event_type, field_name="event_type")
    if payload_filter is not None and not isinstance(
        payload_filter, EventPayloadTextEqualsFilter
    ):
        raise HostDurableError("payload_filter is invalid")
    rows = transaction.fetchall(
        f"""
        SELECT payload_json
        FROM {TABLE_EVENT_LOG}
        WHERE run_id = ?
          AND event_type = ?
          AND event_class = ?
        ORDER BY event_sequence ASC
        """,
        (run_id, event_type, EventClass.CANONICAL_FACT.value),
    )
    if payload_filter is None:
        return len(rows)
    count = 0
    for row in rows:
        payload = _payload_mapping_from_text(
            _require_text(row.get("payload_json"), field_name="payload_json")
        )
        value = payload.get(payload_filter.field_name)
        if not isinstance(value, str) or value.strip() == "":
            raise HostDurableError("EventLog payload filter field is invalid")
        if (
            len(payload_filter.allowed_values) > 0
            and value not in payload_filter.allowed_values
        ):
            raise HostDurableError("EventLog payload filter field is invalid")
        if value == payload_filter.expected_value:
            count += 1
    return count


def count_recovery_dispatches_for_run(
    transaction: HostTransaction, *, run_id: str
) -> int:
    """统计某个 Run 已提交的 recovery dispatch 次数。

    该 helper 只读取 EventLog canonical facts，按 ``run_id`` 和
    ``RUN_STARTED`` 精确过滤，并只计入 inline payload 中
    ``start_reason == "recovery"`` 的事件；不读取 projection/read-model，也不做
    diagnostic 文本匹配。

    :param transaction: 调用方提供的 Host durable transaction。
    :param run_id: 目标 Run id。
    :returns: recovery dispatch 次数。
    :raises HostDurableError: 输入非法或 payload 无法验证时抛出。
    """

    return count_committed_events_by_run_and_type(
        transaction,
        run_id=run_id,
        event_type="RUN_STARTED",
        payload_filter=EventPayloadTextEqualsFilter(
            field_name="start_reason",
            expected_value="recovery",
            allowed_values=("initial", "queue_promotion", "resume", "steer", "recovery"),
        ),
    )


@dataclass(frozen=True, slots=True)
class _EncodedAppendRequest:
    """EventLog append 前的 canonical 编码结果。

    :param occurred_at: 固定 UTC timestamp 文本。
    :param policy_decision_json: canonical policy JSON 文本。
    :param reason_json: canonical reason JSON 文本。
    :param payload_json: canonical payload JSON 文本。
    :param event_body_digest: request-assigned 事件体 digest。
    """

    occurred_at: str
    policy_decision_json: str | None
    reason_json: str | None
    payload_json: str
    event_body_digest: str


def _encode_append_request(request: EventLogAppendRequest) -> _EncodedAppendRequest:
    """编码 append 请求中的 structured fields 并计算事件体 digest。

    :param request: EventLog append 请求。
    :returns: canonical 编码结果。
    :raises ValueError: JSON 或 timestamp 编码失败时抛出。
    :raises TypeError: JSON 值不可序列化时抛出。
    """

    occurred_at = format_utc_timestamp(request.occurred_at)
    policy_decision_json = _optional_canonical_json(request.policy_decision)
    reason_json = _optional_canonical_json(request.reason)
    payload_json = canonical_json_dumps(request.payload_json)
    digest_input: dict[str, JsonValue] = {
        "event_class": request.event_class.value,
        "session_id": request.session_id,
        "run_id": request.run_id,
        "attempt_id": request.attempt_id,
        "execution_id": request.execution_id,
        "event_type": request.event_type,
        "occurred_at": occurred_at,
        "actor": request.actor,
        "source": request.source,
        "client_request_id": request.client_request_id,
        "idempotency_key": request.idempotency_key,
        "policy_decision_json": policy_decision_json,
        "reason_json": reason_json,
        "payload_json": payload_json,
        "payload_ref": request.payload_ref,
        "payload_digest": request.payload_digest,
    }
    return _EncodedAppendRequest(
        occurred_at=occurred_at,
        policy_decision_json=policy_decision_json,
        reason_json=reason_json,
        payload_json=payload_json,
        event_body_digest=sha256_digest_json(digest_input),
    )


def _optional_canonical_json(value: JsonValue | None) -> str | None:
    """按 optional structured JSON 语义编码值。

    :param value: JSON 值；``None`` 表示 SQL NULL。
    :returns: canonical JSON 文本或 ``None``。
    :raises ValueError: JSON 值不可序列化时抛出。
    :raises TypeError: JSON 值不可序列化时抛出。
    """

    if value is None:
        return None
    return canonical_json_dumps(value)


def _payload_mapping_from_text(payload_json: str) -> Mapping[str, JsonValue]:
    """解析 EventLog inline payload JSON 映射。

    :param payload_json: canonical payload JSON 文本。
    :returns: JSON 映射。
    :raises HostDurableError: JSON 非法或不是映射时抛出。
    """

    try:
        value = cast(JsonValue, json.loads(payload_json))
    except json.JSONDecodeError as exc:
        raise HostDurableError("EventLog payload_json is invalid") from exc
    if not isinstance(value, Mapping):
        raise HostDurableError("EventLog payload_json must be a JSON mapping")
    return cast(Mapping[str, JsonValue], value)


def _require_text_tuple(value: tuple[str, ...], *, field_name: str) -> None:
    """校验文本 tuple 字段。

    :param value: 待校验 tuple。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises HostDurableError: 字段不是 tuple 或元素不是非空文本时抛出。
    """

    if not isinstance(value, tuple):
        raise HostDurableError(f"{field_name} must be tuple")
    for item in value:
        _require_non_empty_text(item, field_name=f"{field_name} item")


def _validate_append_request(request: EventLogAppendRequest) -> None:
    """校验 append request 的最小 durable 边界。

    :param request: EventLog append 请求。
    :returns: ``None``。
    :raises HostDurableError: 请求字段无效时抛出。
    """

    _require_non_empty_text(request.event_id, field_name="event_id")
    if not isinstance(request.event_class, EventClass):
        raise HostDurableError("EventLog event_class is invalid")
    _require_non_empty_text(request.session_id, field_name="session_id")
    _require_non_empty_text(request.event_type, field_name="event_type")
    _require_optional_non_empty_text(request.run_id, field_name="run_id")
    _require_optional_non_empty_text(request.attempt_id, field_name="attempt_id")
    _require_optional_non_empty_text(request.execution_id, field_name="execution_id")
    _require_optional_non_empty_text(request.actor, field_name="actor")
    _require_optional_non_empty_text(request.source, field_name="source")
    _require_optional_non_empty_text(
        request.client_request_id, field_name="client_request_id"
    )
    _require_optional_non_empty_text(
        request.idempotency_key, field_name="idempotency_key"
    )
    _validate_payload_reference(request.payload_ref, request.payload_digest)


def _validate_payload_reference(
    payload_ref: str | None, payload_digest: str | None
) -> None:
    """校验 EventLog payload 引用组合。

    :param payload_ref: payload descriptor 引用。
    :param payload_digest: payload descriptor digest。
    :returns: ``None``。
    :raises HostPayloadReferenceError: 引用组合无效时抛出。
    """

    _require_optional_non_empty_text(payload_ref, field_name="payload_ref")
    _require_optional_non_empty_text(payload_digest, field_name="payload_digest")
    if payload_ref is None and payload_digest is None:
        return
    if payload_ref is None or payload_digest is None:
        raise HostPayloadReferenceError(
            "EventLog payload_ref and payload_digest must be provided together"
        )
    if not is_sha256_digest(payload_digest):
        raise HostPayloadReferenceError("EventLog payload_digest is invalid")


def _validate_canonical_inline_payload_size(
    transaction: HostTransaction,
    request: EventLogAppendRequest,
    encoded: _EncodedAppendRequest,
) -> None:
    """校验 canonical fact 不把大内容塞入 inline payload。

    :param transaction: 调用方提供的 Host durable transaction。
    :param request: EventLog append 请求。
    :param encoded: 已 canonical 编码的 append 请求。
    :returns: ``None``。
    :raises HostPayloadReferenceError: canonical inline payload 超过当前 store 的 payload inline 阈值时抛出。
    """

    if request.event_class is not EventClass.CANONICAL_FACT:
        return
    payload_size_bytes = len(encoded.payload_json.encode("utf-8"))
    if payload_size_bytes <= transaction.payload_inline_threshold_bytes:
        return
    raise HostPayloadReferenceError(
        "EventLog canonical_fact payload_json exceeds inline payload limit; "
        "use payload_ref and payload_digest for large canonical content"
    )


def _validate_existing_payload_descriptor(
    transaction: HostTransaction,
    payload_ref: str | None,
    payload_digest: str | None,
) -> None:
    """校验已存在 payload descriptor 与 EventLog 引用一致。

    缺失 descriptor 仍交给 SQLite foreign key 约束分类为
    :class:`HostForeignKeyError`，以保持 durable schema 作为缺失引用真源。

    :param transaction: 调用方提供的 Host durable transaction。
    :param payload_ref: payload descriptor 引用。
    :param payload_digest: EventLog 记录的 payload digest。
    :returns: ``None``。
    :raises HostPayloadReferenceError: 已存在 descriptor digest 不一致或 artifact ref 无效时抛出。
    """

    if payload_ref is None:
        return
    descriptor = read_payload_descriptor(transaction, payload_ref)
    if descriptor is None:
        return
    if descriptor.payload_digest != payload_digest:
        raise HostPayloadReferenceError(
            "EventLog payload_digest does not match descriptor"
        )
    if descriptor.payload_kind is not PayloadKind.ARTIFACT_REF:
        return
    artifact_relative_path = descriptor.artifact_relative_path
    if artifact_relative_path is None:
        raise HostPayloadReferenceError("EventLog artifact descriptor is incomplete")
    try:
        validate_artifact_ref(
            LocalArtifactRef(
                artifact_relative_path=artifact_relative_path,
                artifact_digest=descriptor.payload_digest,
                artifact_size_bytes=descriptor.payload_size_bytes,
            )
        )
    except HostDurableError as exc:
        raise HostPayloadReferenceError(
            "EventLog artifact descriptor is not a published final artifact"
        ) from exc


def _event_log_row_from_host_row(row: HostRow) -> EventLogRow:
    """把通用 HostRow 转换为 EventLogRow。

    :param row: HostTransaction 查询返回的 row。
    :returns: EventLogRow。
    :raises HostDurableError: durable row 类型或 enum 值不符合 schema 预期时抛出。
    """

    event_class_text = _require_text(row.get("event_class"), field_name="event_class")
    try:
        event_class = EventClass(event_class_text)
    except ValueError as exc:
        raise HostDurableError("EventLog row has invalid event_class") from exc
    return EventLogRow(
        event_sequence=_require_int(
            row.get("event_sequence"), field_name="event_sequence"
        ),
        event_id=_require_text(row.get("event_id"), field_name="event_id"),
        event_body_digest=_require_text(
            row.get("event_body_digest"), field_name="event_body_digest"
        ),
        event_class=event_class,
        session_id=_require_text(row.get("session_id"), field_name="session_id"),
        run_id=_optional_text(row.get("run_id"), field_name="run_id"),
        attempt_id=_optional_text(row.get("attempt_id"), field_name="attempt_id"),
        execution_id=_optional_text(row.get("execution_id"), field_name="execution_id"),
        event_type=_require_text(row.get("event_type"), field_name="event_type"),
        occurred_at=_require_text(row.get("occurred_at"), field_name="occurred_at"),
        actor=_optional_text(row.get("actor"), field_name="actor"),
        source=_optional_text(row.get("source"), field_name="source"),
        client_request_id=_optional_text(
            row.get("client_request_id"), field_name="client_request_id"
        ),
        idempotency_key=_optional_text(
            row.get("idempotency_key"), field_name="idempotency_key"
        ),
        policy_decision_json=_optional_text(
            row.get("policy_decision_json"), field_name="policy_decision_json"
        ),
        reason_json=_optional_text(row.get("reason_json"), field_name="reason_json"),
        payload_json=_require_text(row.get("payload_json"), field_name="payload_json"),
        payload_ref=_optional_text(row.get("payload_ref"), field_name="payload_ref"),
        payload_digest=_optional_text(
            row.get("payload_digest"), field_name="payload_digest"
        ),
        appended_at=_require_text(row.get("appended_at"), field_name="appended_at"),
    )
