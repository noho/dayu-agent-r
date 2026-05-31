"""Host projection checkpoint 与 failure durable store。

本模块只提供 projection-owned checkpoint / failure row 的 transaction-scoped
读写 primitive。它不持有 SQLite connection，不启动 transaction，也不读取
或修改 Run / Attempt / wait / dispatch 等 Host governance truth。
"""

from __future__ import annotations

from dataclasses import dataclass

from dayu.host.durable._validation import (
    optional_text as _optional_text,
    require_int as _require_int,
    require_non_empty_text as _require_non_empty_text,
    require_optional_non_empty_text as _require_optional_non_empty_text,
    require_text as _require_text,
)
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.schema import (
    TABLE_HOST_PROJECTION_CHECKPOINTS,
    TABLE_HOST_PROJECTION_FAILURES,
)
from dayu.host.durable.transaction import HostRow, HostTransaction

_INITIAL_CHECKPOINT_SEQUENCE = 0
_CHECKPOINT_EVENT_ID_COLUMN = "checkpoint_event_id"
_FAILED_EVENT_ID_COLUMN = "failed_event_id"


@dataclass(frozen=True, slots=True)
class ProjectionCheckpointRow:
    """projection consumer checkpoint row。

    :param consumer_id: 稳定 consumer id。
    :param checkpoint_event_sequence: 已成功扫描的最大 EventLog sequence；``0`` 表示从头开始。
    :param checkpoint_event_id: 已成功扫描的 EventLog id；初始 cursor 为 ``None``。
    :param last_success_at: 最近一次成功推进 checkpoint 的 UTC timestamp。
    :param updated_at: row 最近更新时间 UTC timestamp。
    """

    consumer_id: str
    checkpoint_event_sequence: int
    checkpoint_event_id: str | None
    last_success_at: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class ProjectionFailureRow:
    """projection consumer failure row。

    :param consumer_id: 稳定 consumer id。
    :param failed_event_sequence: 失败 EventLog sequence。
    :param failed_event_id: 失败 EventLog id。
    :param failure_count: 该 consumer 连续失败记录次数。
    :param last_error_code: 最近一次失败的结构化错误码。
    :param last_error_message: 最近一次失败的诊断消息。
    :param first_failed_at: 首次失败 UTC timestamp。
    :param last_failed_at: 最近失败 UTC timestamp。
    :param retry_after: 可选重试时间 UTC timestamp。
    """

    consumer_id: str
    failed_event_sequence: int
    failed_event_id: str
    failure_count: int
    last_error_code: str
    last_error_message: str
    first_failed_at: str
    last_failed_at: str
    retry_after: str | None


@dataclass(frozen=True, slots=True)
class ProjectionResetResult:
    """projection reset 删除结果。

    :param deleted_checkpoints: 删除的 checkpoint row 数量。
    :param deleted_failures: 删除的 failure row 数量。
    """

    deleted_checkpoints: int
    deleted_failures: int


def read_projection_checkpoint(
    transaction: HostTransaction, consumer_id: str
) -> ProjectionCheckpointRow | None:
    """读取 projection checkpoint row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param consumer_id: 稳定 consumer id。
    :returns: 存在时返回 checkpoint row，否则返回 ``None``。
    :raises HostDurableError: ``consumer_id`` 无效或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(consumer_id, field_name="consumer_id")
    row = transaction.fetchone(
        f"""
        SELECT
          consumer_id,
          checkpoint_event_sequence,
          checkpoint_event_id,
          last_success_at,
          updated_at
        FROM {TABLE_HOST_PROJECTION_CHECKPOINTS}
        WHERE consumer_id = ?
        """,
        (consumer_id,),
    )
    if row is None:
        return None
    return _checkpoint_row_from_host_row(row)


def ensure_projection_checkpoint(
    transaction: HostTransaction, consumer_id: str, *, now: str
) -> ProjectionCheckpointRow:
    """读取或初始化 projection checkpoint row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param consumer_id: 稳定 consumer id。
    :param now: 初始化 row 使用的 UTC timestamp 文本。
    :returns: 既有或新建的 checkpoint row。
    :raises HostDurableError: 输入无效、插入后无法读回或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(consumer_id, field_name="consumer_id")
    _require_non_empty_text(now, field_name="now")
    existing = read_projection_checkpoint(transaction, consumer_id)
    if existing is not None:
        return existing
    transaction.execute(
        f"""
        INSERT INTO {TABLE_HOST_PROJECTION_CHECKPOINTS} (
          consumer_id,
          checkpoint_event_sequence,
          checkpoint_event_id,
          last_success_at,
          updated_at
        ) VALUES (?, ?, NULL, NULL, ?)
        """,
        (consumer_id, _INITIAL_CHECKPOINT_SEQUENCE, now),
    )
    created = read_projection_checkpoint(transaction, consumer_id)
    if created is None:
        raise HostDurableError("projection checkpoint initialization failed")
    return created


def advance_projection_checkpoint(
    transaction: HostTransaction,
    consumer_id: str,
    *,
    event_sequence: int,
    event_id: str,
    now: str,
) -> ProjectionCheckpointRow:
    """推进 projection checkpoint。

    :param transaction: 调用方提供的 Host durable transaction。
    :param consumer_id: 稳定 consumer id。
    :param event_sequence: 已成功扫描的 EventLog sequence，必须大于当前 checkpoint。
    :param event_id: 已成功扫描的 EventLog id。
    :param now: 本次成功推进的 UTC timestamp 文本。
    :returns: 推进后的 checkpoint row。
    :raises HostDurableError: 输入无效、倒退 / 重复推进或更新后无法读回时抛出。
    """

    _require_non_empty_text(consumer_id, field_name="consumer_id")
    _require_non_empty_text(event_id, field_name="event_id")
    _require_non_empty_text(now, field_name="now")
    if event_sequence <= _INITIAL_CHECKPOINT_SEQUENCE:
        raise HostDurableError("projection checkpoint event_sequence must be positive")
    checkpoint = ensure_projection_checkpoint(transaction, consumer_id, now=now)
    if event_sequence <= checkpoint.checkpoint_event_sequence:
        raise HostDurableError("projection checkpoint cannot move backwards")
    result = transaction.execute(
        f"""
        UPDATE {TABLE_HOST_PROJECTION_CHECKPOINTS}
        SET
          checkpoint_event_sequence = ?,
          checkpoint_event_id = ?,
          last_success_at = ?,
          updated_at = ?
        WHERE consumer_id = ?
          AND checkpoint_event_sequence = ?
        """,
        (
            event_sequence,
            event_id,
            now,
            now,
            consumer_id,
            checkpoint.checkpoint_event_sequence,
        ),
    )
    if result.rowcount != 1:
        raise HostDurableError("projection checkpoint advance lost CAS race")
    updated = read_projection_checkpoint(transaction, consumer_id)
    if updated is None:
        raise HostDurableError("projection checkpoint advance failed")
    if (
        updated.checkpoint_event_sequence != event_sequence
        or updated.checkpoint_event_id != event_id
    ):
        raise HostDurableError("projection checkpoint advance lost CAS race")
    return updated


def read_projection_failure(
    transaction: HostTransaction, consumer_id: str
) -> ProjectionFailureRow | None:
    """读取 projection failure row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param consumer_id: 稳定 consumer id。
    :returns: 存在时返回 failure row，否则返回 ``None``。
    :raises HostDurableError: ``consumer_id`` 无效或 durable row 类型不符合预期时抛出。
    """

    _require_non_empty_text(consumer_id, field_name="consumer_id")
    row = transaction.fetchone(
        f"""
        SELECT
          consumer_id,
          failed_event_sequence,
          failed_event_id,
          failure_count,
          last_error_code,
          last_error_message,
          first_failed_at,
          last_failed_at,
          retry_after
        FROM {TABLE_HOST_PROJECTION_FAILURES}
        WHERE consumer_id = ?
        """,
        (consumer_id,),
    )
    if row is None:
        return None
    return _failure_row_from_host_row(row)


def write_projection_failure(
    transaction: HostTransaction,
    consumer_id: str,
    *,
    failed_event_sequence: int,
    failed_event_id: str,
    error_code: str,
    error_message: str,
    now: str,
    retry_after: str | None = None,
) -> ProjectionFailureRow:
    """写入或更新 projection failure row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param consumer_id: 稳定 consumer id。
    :param failed_event_sequence: 失败 EventLog sequence，必须为正数。
    :param failed_event_id: 失败 EventLog id。
    :param error_code: 结构化错误码。
    :param error_message: 诊断消息。
    :param now: 本次失败 UTC timestamp 文本。
    :param retry_after: 可选重试 UTC timestamp 文本。
    :returns: 写入后的 failure row。
    :raises HostDurableError: 输入无效或写入后无法读回时抛出。
    """

    _validate_failure_input(
        consumer_id,
        failed_event_sequence=failed_event_sequence,
        failed_event_id=failed_event_id,
        error_code=error_code,
        error_message=error_message,
        now=now,
        retry_after=retry_after,
    )
    existing = read_projection_failure(transaction, consumer_id)
    if existing is None:
        transaction.execute(
            f"""
            INSERT INTO {TABLE_HOST_PROJECTION_FAILURES} (
              consumer_id,
              failed_event_sequence,
              failed_event_id,
              failure_count,
              last_error_code,
              last_error_message,
              first_failed_at,
              last_failed_at,
              retry_after
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                consumer_id,
                failed_event_sequence,
                failed_event_id,
                1,
                error_code,
                error_message,
                now,
                now,
                retry_after,
            ),
        )
    else:
        transaction.execute(
            f"""
            UPDATE {TABLE_HOST_PROJECTION_FAILURES}
            SET
              failed_event_sequence = ?,
              failed_event_id = ?,
              failure_count = ?,
              last_error_code = ?,
              last_error_message = ?,
              last_failed_at = ?,
              retry_after = ?
            WHERE consumer_id = ?
            """,
            (
                failed_event_sequence,
                failed_event_id,
                existing.failure_count + 1,
                error_code,
                error_message,
                now,
                retry_after,
                consumer_id,
            ),
        )
    written = read_projection_failure(transaction, consumer_id)
    if written is None:
        raise HostDurableError("projection failure write failed")
    return written


def clear_projection_failure(
    transaction: HostTransaction, consumer_id: str
) -> None:
    """清除 projection failure row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param consumer_id: 稳定 consumer id。
    :returns: ``None``。
    :raises HostDurableError: ``consumer_id`` 无效时抛出。
    """

    _require_non_empty_text(consumer_id, field_name="consumer_id")
    transaction.execute(
        f"""
        DELETE FROM {TABLE_HOST_PROJECTION_FAILURES}
        WHERE consumer_id = ?
        """,
        (consumer_id,),
    )


def reset_projection_refs_for_deleted_events(
    transaction: HostTransaction,
    *,
    event_ids: tuple[str, ...],
    rebuildable_consumer_ids: tuple[str, ...],
) -> ProjectionResetResult:
    """删除引用被清理 EventLog rows 的可重建 projection cursor/failure。

    调用方必须已经用 Session / Run / Attempt / EventLog 真源完成 purge 前置判定。
    本 helper 只精确处理传入 EventLog ids 上的 projection-local rows，并拒绝
    不在白名单内的 consumer，避免把 projection cursor 当成治理事实。

    :param transaction: 调用方提供的 Host durable transaction。
    :param event_ids: 已确认将被删除的 EventLog ids。
    :param rebuildable_consumer_ids: 允许从剩余 EventLog 重建的 projection consumer ids。
    :returns: 删除的 checkpoint/failure row 计数。
    :raises HostDurableError: 输入无效或存在不可 reset consumer 引用目标 EventLog 时抛出。
    """

    _validate_reset_event_ids(event_ids)
    _validate_rebuildable_consumer_ids(rebuildable_consumer_ids)
    if len(event_ids) == 0:
        return ProjectionResetResult(deleted_checkpoints=0, deleted_failures=0)
    _raise_for_unsupported_projection_reset_refs(
        transaction,
        table_name=TABLE_HOST_PROJECTION_CHECKPOINTS,
        event_id_column_name=_CHECKPOINT_EVENT_ID_COLUMN,
        event_ids=event_ids,
        rebuildable_consumer_ids=rebuildable_consumer_ids,
    )
    _raise_for_unsupported_projection_reset_refs(
        transaction,
        table_name=TABLE_HOST_PROJECTION_FAILURES,
        event_id_column_name=_FAILED_EVENT_ID_COLUMN,
        event_ids=event_ids,
        rebuildable_consumer_ids=rebuildable_consumer_ids,
    )
    deleted_checkpoints = _delete_allowed_projection_reset_refs(
        transaction,
        table_name=TABLE_HOST_PROJECTION_CHECKPOINTS,
        event_id_column_name=_CHECKPOINT_EVENT_ID_COLUMN,
        event_ids=event_ids,
        rebuildable_consumer_ids=rebuildable_consumer_ids,
    )
    deleted_failures = _delete_allowed_projection_reset_refs(
        transaction,
        table_name=TABLE_HOST_PROJECTION_FAILURES,
        event_id_column_name=_FAILED_EVENT_ID_COLUMN,
        event_ids=event_ids,
        rebuildable_consumer_ids=rebuildable_consumer_ids,
    )
    return ProjectionResetResult(
        deleted_checkpoints=deleted_checkpoints,
        deleted_failures=deleted_failures,
    )


def _validate_failure_input(
    consumer_id: str,
    *,
    failed_event_sequence: int,
    failed_event_id: str,
    error_code: str,
    error_message: str,
    now: str,
    retry_after: str | None,
) -> None:
    """校验 failure 写入输入。

    :param consumer_id: 稳定 consumer id。
    :param failed_event_sequence: 失败 EventLog sequence。
    :param failed_event_id: 失败 EventLog id。
    :param error_code: 结构化错误码。
    :param error_message: 诊断消息。
    :param now: 本次失败 UTC timestamp 文本。
    :param retry_after: 可选重试 UTC timestamp 文本。
    :returns: ``None``。
    :raises HostDurableError: 输入无效时抛出。
    """

    _require_non_empty_text(consumer_id, field_name="consumer_id")
    _require_non_empty_text(failed_event_id, field_name="failed_event_id")
    _require_non_empty_text(error_code, field_name="error_code")
    _require_non_empty_text(error_message, field_name="error_message")
    _require_non_empty_text(now, field_name="now")
    _require_optional_non_empty_text(retry_after, field_name="retry_after")
    if failed_event_sequence <= _INITIAL_CHECKPOINT_SEQUENCE:
        raise HostDurableError("projection failed_event_sequence must be positive")


def _validate_reset_event_ids(event_ids: tuple[str, ...]) -> None:
    """校验 projection reset 目标 EventLog ids。

    :param event_ids: 待 reset 的 EventLog ids。
    :returns: ``None``。
    :raises HostDurableError: 任一 event id 非法或重复时抛出。
    """

    seen: set[str] = set()
    for event_id in event_ids:
        _require_non_empty_text(event_id, field_name="event_id")
        if event_id in seen:
            raise HostDurableError("projection reset event_id is duplicated")
        seen.add(event_id)


def _validate_rebuildable_consumer_ids(
    rebuildable_consumer_ids: tuple[str, ...],
) -> None:
    """校验允许 reset 的 projection consumer ids。

    :param rebuildable_consumer_ids: 允许 reset 的 consumer ids。
    :returns: ``None``。
    :raises HostDurableError: consumer id 集合为空、非法或重复时抛出。
    """

    if len(rebuildable_consumer_ids) == 0:
        raise HostDurableError("projection reset consumer allow-list cannot be empty")
    seen: set[str] = set()
    for consumer_id in rebuildable_consumer_ids:
        _require_non_empty_text(consumer_id, field_name="consumer_id")
        if consumer_id in seen:
            raise HostDurableError("projection reset consumer_id is duplicated")
        seen.add(consumer_id)


def _raise_for_unsupported_projection_reset_refs(
    transaction: HostTransaction,
    *,
    table_name: str,
    event_id_column_name: str,
    event_ids: tuple[str, ...],
    rebuildable_consumer_ids: tuple[str, ...],
) -> None:
    """检查目标 EventLog 上是否存在不可 reset 的 projection consumer row。

    :param transaction: Host transaction。
    :param table_name: projection checkpoint/failure 表名。
    :param event_id_column_name: 指向 EventLog id 的列名。
    :param event_ids: 目标 EventLog ids。
    :param rebuildable_consumer_ids: 允许 reset 的 consumer ids。
    :returns: ``None``。
    :raises HostDurableError: 非白名单 consumer 引用目标 EventLog 时抛出。
    """

    row = transaction.fetchone(
        f"""
        SELECT consumer_id
        FROM {table_name}
        WHERE {_in_clause(event_id_column_name, event_ids)}
          AND consumer_id NOT IN ({_placeholders(rebuildable_consumer_ids)})
        LIMIT 1
        """,
        event_ids + rebuildable_consumer_ids,
    )
    if row is not None:
        consumer_id = _require_text(row.get("consumer_id"), field_name="consumer_id")
        raise HostDurableError(
            f"projection consumer cannot be reset during purge: {consumer_id}"
        )


def _delete_allowed_projection_reset_refs(
    transaction: HostTransaction,
    *,
    table_name: str,
    event_id_column_name: str,
    event_ids: tuple[str, ...],
    rebuildable_consumer_ids: tuple[str, ...],
) -> int:
    """删除白名单 consumer 且引用目标 EventLog 的 projection reset rows。

    :param transaction: Host transaction。
    :param table_name: projection checkpoint/failure 表名。
    :param event_id_column_name: 指向 EventLog id 的列名。
    :param event_ids: 目标 EventLog ids。
    :param rebuildable_consumer_ids: 允许 reset 的 consumer ids。
    :returns: 删除 row 数量。
    """

    return transaction.execute(
        f"""
        DELETE FROM {table_name}
        WHERE {_in_clause(event_id_column_name, event_ids)}
          AND consumer_id IN ({_placeholders(rebuildable_consumer_ids)})
        """,
        event_ids + rebuildable_consumer_ids,
    ).rowcount


def _in_clause(column_name: str, values: tuple[str, ...]) -> str:
    """构造固定列名的 SQL IN 子句。

    :param column_name: SQL 列名，由本模块固定常量传入。
    :param values: 参数值。
    :returns: SQL IN 子句。
    """

    return f"{column_name} IN ({_placeholders(values)})"


def _placeholders(values: tuple[str, ...]) -> str:
    """按值数量生成 SQL placeholders。

    :param values: 参数值。
    :returns: 逗号分隔的 placeholders。
    """

    return ", ".join("?" for _value in values)


def _checkpoint_row_from_host_row(row: HostRow) -> ProjectionCheckpointRow:
    """把通用 HostRow 转换为 ProjectionCheckpointRow。

    :param row: HostTransaction 查询返回的 row。
    :returns: checkpoint row。
    :raises HostDurableError: durable row 类型不符合预期时抛出。
    """

    return ProjectionCheckpointRow(
        consumer_id=_require_text(row.get("consumer_id"), field_name="consumer_id"),
        checkpoint_event_sequence=_require_int(
            row.get("checkpoint_event_sequence"),
            field_name="checkpoint_event_sequence",
        ),
        checkpoint_event_id=_optional_text(
            row.get("checkpoint_event_id"), field_name="checkpoint_event_id"
        ),
        last_success_at=_optional_text(
            row.get("last_success_at"), field_name="last_success_at"
        ),
        updated_at=_require_text(row.get("updated_at"), field_name="updated_at"),
    )


def _failure_row_from_host_row(row: HostRow) -> ProjectionFailureRow:
    """把通用 HostRow 转换为 ProjectionFailureRow。

    :param row: HostTransaction 查询返回的 row。
    :returns: failure row。
    :raises HostDurableError: durable row 类型不符合预期时抛出。
    """

    return ProjectionFailureRow(
        consumer_id=_require_text(row.get("consumer_id"), field_name="consumer_id"),
        failed_event_sequence=_require_int(
            row.get("failed_event_sequence"), field_name="failed_event_sequence"
        ),
        failed_event_id=_require_text(
            row.get("failed_event_id"), field_name="failed_event_id"
        ),
        failure_count=_require_int(row.get("failure_count"), field_name="failure_count"),
        last_error_code=_require_text(
            row.get("last_error_code"), field_name="last_error_code"
        ),
        last_error_message=_require_text(
            row.get("last_error_message"), field_name="last_error_message"
        ),
        first_failed_at=_require_text(
            row.get("first_failed_at"), field_name="first_failed_at"
        ),
        last_failed_at=_require_text(
            row.get("last_failed_at"), field_name="last_failed_at"
        ),
        retry_after=_optional_text(row.get("retry_after"), field_name="retry_after"),
    )
