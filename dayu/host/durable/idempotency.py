"""Host durable idempotency record primitive。

本模块只实现通用幂等记录的写入、重复读取与冲突检测。它不解释 command
path 语义，不从 ``result_ref`` 推断结果类型，也不负责创建 EventLog row。
所有 mutation 都必须发生在调用方传入的 ``HostTransaction`` 中。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from dayu.host.durable._validation import (
    optional_int as _optional_int,
    optional_text as _optional_text,
    require_non_empty_text as _require_non_empty_text,
    require_optional_non_empty_text as _require_optional_non_empty_text,
    require_sha256_digest as _validate_digest,
    require_text as _require_text,
)
from dayu.host.durable.codec import format_utc_timestamp
from dayu.host.durable.errors import HostDurableError, HostIdempotencyConflictError
from dayu.host.durable.schema import TABLE_IDEMPOTENCY_RECORDS
from dayu.host.durable.transaction import HostRow, HostTransaction


@dataclass(frozen=True, slots=True)
class IdempotencyScope:
    """幂等记录作用域。

    :param scope_kind: 作用域类型，由调用方显式提供。
    :param scope_id: 作用域标识。
    :param idempotency_key: 幂等 key。
    """

    scope_kind: str
    scope_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class IdempotencyResultRef:
    """幂等记录结果引用。

    :param result_kind: 结果类型，由调用方显式提供，不从其它字段推断。
    :param result_ref: 结果引用。
    :param created_event_id: 该结果创建的 EventLog 事件标识。
    :param created_event_sequence: 该结果创建的 EventLog 全局序号。
    """

    result_kind: str
    result_ref: str
    created_event_id: str | None
    created_event_sequence: int | None


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """已持久化幂等记录。

    :param scope_kind: 作用域类型。
    :param scope_id: 作用域标识。
    :param idempotency_key: 幂等 key。
    :param semantic_input_digest: semantic input digest。
    :param result_kind: 结果类型。
    :param result_ref: 结果引用。
    :param created_event_id: 创建结果的 EventLog 事件标识。
    :param created_event_sequence: 创建结果的 EventLog 全局序号。
    :param created_at: 创建时间，固定 UTC 微秒精度 ``Z`` timestamp 文本。
    """

    scope_kind: str
    scope_id: str
    idempotency_key: str
    semantic_input_digest: str
    result_kind: str
    result_ref: str
    created_event_id: str | None
    created_event_sequence: int | None
    created_at: str


class IdempotencyStore:
    """Idempotency primitive 的轻量方法集合。

    该类不持有连接、不创建 transaction，也不引入 command path 语义；所有
    mutation 都必须发生在调用方传入的 ``HostTransaction`` 中。
    """

    def record_idempotent_result(
        self,
        transaction: HostTransaction,
        scope: IdempotencyScope,
        semantic_input_digest: str,
        result: IdempotencyResultRef,
    ) -> IdempotencyRecord:
        """写入或读取既有幂等结果。

        :param transaction: 调用方提供的 Host durable transaction。
        :param scope: 幂等作用域。
        :param semantic_input_digest: semantic input digest。
        :param result: 幂等结果引用。
        :returns: 新插入或既有的幂等记录。
        :raises HostDurableError: 输入字段无效时抛出。
        :raises HostIdempotencyConflictError: 同 key 对应不同 semantic digest 时抛出。
        :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
        """

        return record_idempotent_result(
            transaction, scope, semantic_input_digest, result
        )

    def read_idempotency_record(
        self, transaction: HostTransaction, scope: IdempotencyScope
    ) -> IdempotencyRecord | None:
        """读取幂等记录。

        :param transaction: 调用方提供的 Host durable transaction。
        :param scope: 幂等作用域。
        :returns: 找到时返回幂等记录，否则返回 ``None``。
        :raises HostDurableError: scope 字段无效时抛出。
        """

        return read_idempotency_record(transaction, scope)


def record_idempotent_result(
    transaction: HostTransaction,
    scope: IdempotencyScope,
    semantic_input_digest: str,
    result: IdempotencyResultRef,
) -> IdempotencyRecord:
    """在调用方 transaction 内写入或读取既有幂等结果。

    :param transaction: 调用方提供的 Host durable transaction。
    :param scope: 幂等作用域。
    :param semantic_input_digest: semantic input digest。
    :param result: 幂等结果引用。
    :returns: 新插入或既有的幂等记录。
    :raises HostDurableError: 输入字段无效时抛出。
    :raises HostIdempotencyConflictError: 同 key 对应不同 semantic digest 时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_scope(scope)
    _validate_digest(semantic_input_digest, field_name="semantic_input_digest")
    _validate_result_ref(result)
    existing = read_idempotency_record(transaction, scope)
    if existing is not None:
        if existing.semantic_input_digest == semantic_input_digest:
            return existing
        raise HostIdempotencyConflictError(
            "Idempotency key already exists with different semantic digest"
        )

    created_at = format_utc_timestamp(datetime.now(UTC))
    transaction.execute(
        f"""
        INSERT INTO {TABLE_IDEMPOTENCY_RECORDS} (
          scope_kind,
          scope_id,
          idempotency_key,
          semantic_input_digest,
          result_kind,
          result_ref,
          created_event_id,
          created_event_sequence,
          created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scope.scope_kind,
            scope.scope_id,
            scope.idempotency_key,
            semantic_input_digest,
            result.result_kind,
            result.result_ref,
            result.created_event_id,
            result.created_event_sequence,
            created_at,
        ),
    )
    row = read_idempotency_record(transaction, scope)
    if row is None:
        raise HostDurableError("Idempotency insert did not return inserted row")
    return row


def read_idempotency_record(
    transaction: HostTransaction, scope: IdempotencyScope
) -> IdempotencyRecord | None:
    """读取幂等记录。

    :param transaction: 调用方提供的 Host durable transaction。
    :param scope: 幂等作用域。
    :returns: 找到时返回幂等记录，否则返回 ``None``。
    :raises HostDurableError: scope 字段无效时抛出。
    """

    _validate_scope(scope)
    row = transaction.fetchone(
        f"""
        SELECT
          scope_kind,
          scope_id,
          idempotency_key,
          semantic_input_digest,
          result_kind,
          result_ref,
          created_event_id,
          created_event_sequence,
          created_at
        FROM {TABLE_IDEMPOTENCY_RECORDS}
        WHERE scope_kind = ? AND scope_id = ? AND idempotency_key = ?
        """,
        (scope.scope_kind, scope.scope_id, scope.idempotency_key),
    )
    if row is None:
        return None
    return _idempotency_record_from_host_row(row)


def _validate_scope(scope: IdempotencyScope) -> None:
    """校验幂等作用域字段。

    :param scope: 幂等作用域。
    :returns: ``None``。
    :raises HostDurableError: 任一字段为空时抛出。
    """

    _require_non_empty_text(scope.scope_kind, field_name="scope_kind")
    _require_non_empty_text(scope.scope_id, field_name="scope_id")
    _require_non_empty_text(scope.idempotency_key, field_name="idempotency_key")


def _validate_result_ref(result: IdempotencyResultRef) -> None:
    """校验幂等结果引用字段。

    :param result: 幂等结果引用。
    :returns: ``None``。
    :raises HostDurableError: 结果字段无效时抛出。
    """

    _require_non_empty_text(result.result_kind, field_name="result_kind")
    _require_non_empty_text(result.result_ref, field_name="result_ref")
    _require_optional_non_empty_text(
        result.created_event_id, field_name="created_event_id"
    )
    if result.created_event_sequence is not None and result.created_event_sequence <= 0:
        raise HostDurableError(
            "created_event_sequence must be positive when provided"
        )


def _idempotency_record_from_host_row(row: HostRow) -> IdempotencyRecord:
    """把通用 HostRow 转换为 IdempotencyRecord。

    :param row: HostTransaction 查询返回的 row。
    :returns: IdempotencyRecord。
    :raises HostDurableError: durable row 类型不符合 schema 预期时抛出。
    """

    return IdempotencyRecord(
        scope_kind=_require_text(row.get("scope_kind"), field_name="scope_kind"),
        scope_id=_require_text(row.get("scope_id"), field_name="scope_id"),
        idempotency_key=_require_text(
            row.get("idempotency_key"), field_name="idempotency_key"
        ),
        semantic_input_digest=_require_text(
            row.get("semantic_input_digest"), field_name="semantic_input_digest"
        ),
        result_kind=_require_text(row.get("result_kind"), field_name="result_kind"),
        result_ref=_require_text(row.get("result_ref"), field_name="result_ref"),
        created_event_id=_optional_text(
            row.get("created_event_id"), field_name="created_event_id"
        ),
        created_event_sequence=_optional_int(
            row.get("created_event_sequence"), field_name="created_event_sequence"
        ),
        created_at=_require_text(row.get("created_at"), field_name="created_at"),
    )
