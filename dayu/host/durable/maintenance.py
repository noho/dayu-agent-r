"""Host durable 内部 WAL maintenance primitive。

本模块只服务 Host durable 内部 maintenance / test entry，用于显式执行
SQLite WAL checkpoint 并返回诊断结果；它不是 Service-facing public
maintenance API，也不改变 EventLog、state index、projection 或 recovery
correctness 的前置条件。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.transaction import SQLiteScalar

_SQLITE_CHECKPOINT_ROW_LENGTH = 3
_SQLITE_CHECKPOINT_BUSY_INDEX = 0
_SQLITE_CHECKPOINT_LOG_INDEX = 1
_SQLITE_CHECKPOINT_CHECKPOINTED_INDEX = 2
_SQLITE_DATABASE_LIST_ROW_LENGTH = 3
_SQLITE_DATABASE_LIST_NAME_INDEX = 1
_SQLITE_DATABASE_LIST_FILE_INDEX = 2
_SQLITE_MAIN_DATABASE_NAME = "main"
_SQLITE_DATABASE_LIST_PRAGMA = "PRAGMA database_list"
_HOST_WAL_CHECKPOINT_INSPECT_DATABASE_ERROR = (
    "Host durable WAL checkpoint failed to inspect connection database"
)
_HOST_WAL_CHECKPOINT_DATABASE_MISMATCH_ERROR = (
    "Host durable WAL checkpoint connection does not match db_path"
)


class HostWalCheckpointMode(StrEnum):
    """Host durable WAL checkpoint 模式。"""

    PASSIVE = "PASSIVE"
    TRUNCATE = "TRUNCATE"


@dataclass(frozen=True, slots=True)
class HostWalCheckpointResult:
    """WAL checkpoint 诊断结果。

    :param mode: 执行的 checkpoint 模式。
    :param busy_pages: SQLite 返回的 busy pages / frames 数。
    :param log_pages: WAL log pages / frames 数。
    :param checkpointed_pages: 已 checkpoint pages / frames 数。
    :param wal_size_bytes: 调用后 WAL 文件大小；文件不存在时为 ``0``。
    """

    mode: HostWalCheckpointMode
    busy_pages: int
    log_pages: int
    checkpointed_pages: int
    wal_size_bytes: int


def run_host_wal_checkpoint(
    connection: sqlite3.Connection,
    *,
    db_path: Path,
    mode: HostWalCheckpointMode = HostWalCheckpointMode.PASSIVE,
) -> HostWalCheckpointResult:
    """显式执行 Host durable SQLite WAL checkpoint 并返回诊断。

    :param connection: 已配置的 Host durable SQLite connection。
    :param db_path: Host durable SQLite DB 文件路径。
    :param mode: checkpoint 模式，只允许 ``PASSIVE`` 或 ``TRUNCATE``。
    :returns: checkpoint 诊断结果；``busy_pages`` 大于零时也原样返回。
    :raises HostDurableError: SQLite checkpoint 失败或 SQLite 未返回结果时抛出。
    """

    _assert_connection_matches_db_path(connection, db_path=db_path)
    try:
        row = connection.execute(f"PRAGMA wal_checkpoint({mode.value})").fetchone()
    except sqlite3.Error as exc:
        raise HostDurableError("Host durable WAL checkpoint failed") from exc
    if row is None:
        raise HostDurableError("Host durable WAL checkpoint returned no result")

    row_values = cast(tuple[SQLiteScalar, ...], tuple(row))
    if len(row_values) != _SQLITE_CHECKPOINT_ROW_LENGTH:
        raise HostDurableError(
            "Host durable WAL checkpoint returned unexpected result shape"
        )
    return HostWalCheckpointResult(
        mode=mode,
        busy_pages=_checkpoint_int(
            row_values[_SQLITE_CHECKPOINT_BUSY_INDEX],
            field_name="busy_pages",
        ),
        log_pages=_checkpoint_int(
            row_values[_SQLITE_CHECKPOINT_LOG_INDEX],
            field_name="log_pages",
        ),
        checkpointed_pages=_checkpoint_int(
            row_values[_SQLITE_CHECKPOINT_CHECKPOINTED_INDEX],
            field_name="checkpointed_pages",
        ),
        wal_size_bytes=_read_wal_size_bytes(db_path),
    )


def _assert_connection_matches_db_path(
    connection: sqlite3.Connection,
    *,
    db_path: Path,
) -> None:
    """校验 checkpoint connection 与 DB 路径同源。

    :param connection: 即将执行 WAL checkpoint 的 SQLite connection。
    :param db_path: 调用方声明的 Host durable SQLite DB 文件路径。
    :returns: ``None``。
    :raises HostDurableError: 无法读取 connection database list、connection 没有
        文件型 main database，或 main database 文件路径与 ``db_path`` 不一致时抛出。
    """

    connection_db_path = _read_main_database_path(connection)
    if connection_db_path.resolve(strict=False) != db_path.resolve(strict=False):
        raise HostDurableError(_HOST_WAL_CHECKPOINT_DATABASE_MISMATCH_ERROR)


def _read_main_database_path(connection: sqlite3.Connection) -> Path:
    """读取 SQLite connection 的 main database 文件路径。

    :param connection: 已配置的 Host durable SQLite connection。
    :returns: ``main`` database 对应的文件路径。
    :raises HostDurableError: database list 查询失败、返回 shape 异常、缺失
        ``main`` database，或 ``main`` database 不是文件型数据库时抛出。
    """

    try:
        rows = connection.execute(_SQLITE_DATABASE_LIST_PRAGMA).fetchall()
    except sqlite3.Error as exc:
        raise HostDurableError(_HOST_WAL_CHECKPOINT_INSPECT_DATABASE_ERROR) from exc

    for row in rows:
        row_values = cast(tuple[SQLiteScalar, ...], tuple(row))
        if len(row_values) != _SQLITE_DATABASE_LIST_ROW_LENGTH:
            raise HostDurableError(_HOST_WAL_CHECKPOINT_INSPECT_DATABASE_ERROR)
        if row_values[_SQLITE_DATABASE_LIST_NAME_INDEX] != _SQLITE_MAIN_DATABASE_NAME:
            continue

        database_file = row_values[_SQLITE_DATABASE_LIST_FILE_INDEX]
        if not isinstance(database_file, str) or database_file == "":
            raise HostDurableError(_HOST_WAL_CHECKPOINT_INSPECT_DATABASE_ERROR)
        return Path(database_file)

    raise HostDurableError(_HOST_WAL_CHECKPOINT_INSPECT_DATABASE_ERROR)


def _checkpoint_int(value: SQLiteScalar, *, field_name: str) -> int:
    """读取 SQLite checkpoint 返回列中的整数值。

    :param value: SQLite 返回的 scalar 值。
    :param field_name: 诊断字段名。
    :returns: 整数形式的 checkpoint 字段值。
    :raises HostDurableError: SQLite 返回了非整数值时抛出。
    """

    if isinstance(value, int):
        return value
    raise HostDurableError(f"Host durable WAL checkpoint invalid {field_name}")


def _read_wal_size_bytes(db_path: Path) -> int:
    """读取 SQLite WAL 文件大小。

    :param db_path: Host durable SQLite DB 文件路径。
    :returns: ``db_path`` 对应 ``-wal`` 文件大小；WAL 文件不存在或已被
        SQLite 清理时返回 ``0``。
    :raises HostDurableError: WAL 文件存在但无法读取 metadata 时抛出。
    """

    wal_path = db_path.with_name(db_path.name + "-wal")
    try:
        return wal_path.stat().st_size
    except FileNotFoundError:
        return 0
    except OSError as exc:
        raise HostDurableError(
            "Host durable WAL checkpoint failed to read WAL file size"
        ) from exc
