"""Host durable SQLite transaction runner。

本模块提供 Host durable foundation 内部使用的 typed transaction wrapper。
runner 只负责短 ``BEGIN IMMEDIATE`` write transaction、busy / locked 有限重试、
rollback、commit 与 after-commit callback 顺序；它不实现任何 EventLog、
payload、idempotency、liveness 或 command path 业务语义。
"""

from __future__ import annotations

import logging
import sqlite3
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, TypeVar, cast

from dayu.host.durable.errors import (
    HostAfterCommitError,
    HostDurableError,
    HostForeignKeyError,
    HostTransactionRetryExhaustedError,
    HostUniqueConstraintError,
)
from dayu.host.durable.options import HostSQLiteStoragePolicy

_SQLITE_CONSTRAINT_UNIQUE = sqlite3.SQLITE_CONSTRAINT_UNIQUE
_SQLITE_CONSTRAINT_PRIMARYKEY = sqlite3.SQLITE_CONSTRAINT_PRIMARYKEY
_SQLITE_CONSTRAINT_FOREIGNKEY = sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY
_SQLITE_CONSTRAINT_CHECK = sqlite3.SQLITE_CONSTRAINT_CHECK
_SQLITE_EXTENDED_RESULT_CODE_MASK = 0xFF
_SQLITE_MILLISECONDS_PER_SECOND = 1000
_SQLITE_WAL_AUTOCHECKPOINT_PAGES = 256
_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)
SQLiteScalar = None | int | float | str | bytes
SQLParameters = tuple[SQLiteScalar, ...] | Mapping[str, SQLiteScalar]


class AfterCommitCallback(Protocol):
    """durable commit 成功后执行的同步回调协议。"""

    def __call__(self) -> None:
        """执行 after-commit 回调。

        :returns: ``None``。
        :raises Exception: 回调实现可抛出任意异常，runner 会转为
            :class:`HostAfterCommitError`。
        """


class HostTransactionOperation(Protocol[T_co]):
    """Host durable write transaction body 协议。

    :param transaction: 当前 write transaction wrapper。
    :returns: operation 自定义返回值。
    :raises Exception: operation 失败时由 runner rollback 并透传或结构化转换。
    """

    def __call__(self, transaction: "HostTransaction") -> T_co:
        """执行 transaction body。

        :param transaction: 当前 write transaction wrapper。
        :returns: operation 自定义返回值。
        :raises Exception: operation 失败时由 runner rollback 并透传或结构化转换。
        """

        ...


class _SQLiteErrorCodeCarrier(Protocol):
    """Python 运行时 ``sqlite3.Error`` 扩展错误码承载协议。

    :param sqlite_errorcode: SQLite 直接错误码。
    """

    sqlite_errorcode: int


class HostReadTransactionOperation(Protocol[T_co]):
    """Host durable read transaction body 协议。

    :param transaction: 当前 read transaction wrapper。
    :returns: operation 自定义返回值。
    :raises Exception: operation 失败时由 runner rollback 并透传或结构化转换。
    """

    def __call__(self, transaction: "HostTransaction") -> T_co:
        """执行 read transaction body。

        :param transaction: 当前 read transaction wrapper。
        :returns: operation 自定义返回值。
        :raises Exception: operation 失败时由 runner rollback 并透传或结构化转换。
        """

        ...


@dataclass(frozen=True, slots=True)
class HostRow:
    """Host durable SQLite row 的强类型只读视图。

    :param columns: 查询结果列名。
    :param values: 查询结果值，元素必须是 SQLite scalar。
    """

    columns: tuple[str, ...]
    values: tuple[SQLiteScalar, ...]

    def get(self, column: str) -> SQLiteScalar:
        """按列名读取 SQLite scalar 值。

        :param column: 列名。
        :returns: 对应 SQLite scalar 值。
        :raises KeyError: 列名不存在时抛出。
        """

        for index, name in enumerate(self.columns):
            if name == column:
                return self.values[index]
        raise KeyError(column)


@dataclass(frozen=True, slots=True)
class HostExecuteResult:
    """SQLite write execute 结果摘要。

    :param rowcount: cursor ``rowcount``。
    :param lastrowid: cursor ``lastrowid``；没有 rowid 时为 ``None``。
    """

    rowcount: int
    lastrowid: int | None


class HostTransaction:
    """Host durable 内部 SQLite transaction wrapper。

    :param connection: 已进入 transaction 的 SQLite connection。
    :param payload_inline_threshold_bytes: 当前 durable store 的 payload inline 阈值。
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        payload_inline_threshold_bytes: int,
    ) -> None:
        """初始化 transaction wrapper。

        :param connection: 已进入 transaction 的 SQLite connection。
        :param payload_inline_threshold_bytes: 当前 durable store 的 payload inline 阈值。
        :returns: ``None``。
        """

        self._connection = connection
        self._payload_inline_threshold_bytes = payload_inline_threshold_bytes

    @property
    def payload_inline_threshold_bytes(self) -> int:
        """返回当前 durable store 的 payload inline 阈值。

        :returns: payload inline 阈值字节数。
        """

        return self._payload_inline_threshold_bytes

    def execute(self, sql: str, parameters: SQLParameters = ()) -> HostExecuteResult:
        """执行一条 SQL statement 并返回写入摘要。

        :param sql: SQL statement。
        :param parameters: SQLite scalar tuple 或 named parameter mapping。
        :returns: 写入摘要。
        :raises sqlite3.Error: SQLite 执行失败时抛出。
        """

        cursor = self._connection.execute(sql, parameters)
        return HostExecuteResult(
            rowcount=cursor.rowcount,
            lastrowid=cursor.lastrowid,
        )

    def fetchone(self, sql: str, parameters: SQLParameters = ()) -> HostRow | None:
        """执行查询并读取一行。

        :param sql: SQL query。
        :param parameters: SQLite scalar tuple 或 named parameter mapping。
        :returns: 查询结果 row；无结果时为 ``None``。
        :raises sqlite3.Error: SQLite 执行失败时抛出。
        """

        cursor = self._connection.execute(sql, parameters)
        row = cursor.fetchone()
        if row is None:
            return None
        return _build_host_row(cursor, row)

    def fetchall(self, sql: str, parameters: SQLParameters = ()) -> tuple[HostRow, ...]:
        """执行查询并读取所有行。

        :param sql: SQL query。
        :param parameters: SQLite scalar tuple 或 named parameter mapping。
        :returns: 查询结果 row 元组。
        :raises sqlite3.Error: SQLite 执行失败时抛出。
        """

        cursor = self._connection.execute(sql, parameters)
        rows = cursor.fetchall()
        return tuple(_build_host_row(cursor, row) for row in rows)


class HostTransactionRunner:
    """Host durable write transaction runner。

    :param connection: runner 持有的 SQLite connection。
    :param sqlite_policy: busy timeout 与 write retry 策略。
    :param payload_inline_threshold_bytes: 当前 durable store 的 payload inline 阈值。
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        sqlite_policy: HostSQLiteStoragePolicy,
        *,
        payload_inline_threshold_bytes: int,
    ) -> None:
        """初始化 transaction runner。

        :param connection: runner 持有的 SQLite connection。
        :param sqlite_policy: busy timeout 与 write retry 策略。
        :param payload_inline_threshold_bytes: 当前 durable store 的 payload inline 阈值。
        :returns: ``None``。
        """

        self._connection = connection
        self._sqlite_policy = sqlite_policy
        self._payload_inline_threshold_bytes = payload_inline_threshold_bytes
        self._active_transaction_count = 0
        self._connection_unusable = False

    @property
    def has_active_transaction(self) -> bool:
        """返回当前 runner 是否持有未收口 transaction。

        :returns: 存在已 ``BEGIN`` 且尚未 commit / rollback 的 transaction
            时返回 ``True``，否则返回 ``False``。
        """

        return self._active_transaction_count > 0

    def run_write(
        self,
        operation: HostTransactionOperation[T],
        *,
        after_commit: tuple[AfterCommitCallback, ...] = (),
    ) -> T:
        """在 ``BEGIN IMMEDIATE`` write transaction 内运行 operation。

        :param operation: transaction body。
        :param after_commit: commit 成功后执行的回调元组。
        :returns: ``operation`` 的返回值。
        :raises HostTransactionRetryExhaustedError: busy / locked 重试耗尽时抛出。
        :raises HostUniqueConstraintError: unique / primary-key constraint 失败时抛出。
        :raises HostForeignKeyError: foreign-key constraint 失败时抛出。
        :raises HostAfterCommitError: durable commit 后 callback 失败时抛出。
        :raises HostDurableError: operation 抛出的 durable domain error 会透传。
        :raises Exception: operation 抛出的非 durable 错误会在 rollback 后透传。
        """

        attempt = 0
        max_attempts = self._sqlite_policy.write_busy_retry_count + 1
        delay_seconds = self._sqlite_policy.write_retry_initial_delay_seconds
        while True:
            self._raise_if_connection_unusable()
            attempt += 1
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                self._active_transaction_count += 1
                try:
                    result = operation(
                        HostTransaction(
                            self._connection,
                            payload_inline_threshold_bytes=(self._payload_inline_threshold_bytes),
                        )
                    )
                    self._connection.execute("COMMIT")
                finally:
                    self._active_transaction_count -= 1
            except sqlite3.Error as exc:
                if not self._rollback_if_needed_or_mark_unusable():
                    raise HostDurableError(
                        "Host durable transaction rollback failed; connection is unusable"
                    ) from exc
                durable_error = _classify_sqlite_error(exc)
                if _is_busy_or_locked(exc):
                    if attempt >= max_attempts:
                        raise HostTransactionRetryExhaustedError(
                            "Host durable write transaction busy retry exhausted",
                            attempts=attempt,
                        ) from exc
                    time.sleep(delay_seconds)
                    delay_seconds = min(
                        delay_seconds * self._sqlite_policy.write_retry_backoff_multiplier,
                        self._sqlite_policy.write_retry_max_delay_seconds,
                    )
                    continue
                raise durable_error from exc
            except HostDurableError as exc:
                if not self._rollback_if_needed_or_mark_unusable():
                    raise HostDurableError(
                        "Host durable transaction rollback failed; connection is unusable"
                    ) from exc
                raise
            except Exception as exc:
                if not self._rollback_if_needed_or_mark_unusable():
                    raise HostDurableError(
                        "Host durable transaction rollback failed; connection is unusable"
                    ) from exc
                raise
            _run_after_commit(after_commit)
            return result

    def run_read(self, operation: HostReadTransactionOperation[T]) -> T:
        """在普通 read transaction 内运行 operation。

        :param operation: transaction body。
        :returns: ``operation`` 的返回值。
        :raises HostTransactionRetryExhaustedError: busy / locked 重试耗尽时抛出。
        :raises HostDurableError: SQLite read transaction 失败时抛出结构化错误。
        :raises Exception: operation 抛出的非 durable 错误会在 rollback 后透传。
        """

        attempt = 0
        max_attempts = self._sqlite_policy.write_busy_retry_count + 1
        delay_seconds = self._sqlite_policy.write_retry_initial_delay_seconds
        while True:
            self._raise_if_connection_unusable()
            attempt += 1
            try:
                self._connection.execute("BEGIN")
                self._active_transaction_count += 1
                try:
                    result = operation(
                        HostTransaction(
                            self._connection,
                            payload_inline_threshold_bytes=(self._payload_inline_threshold_bytes),
                        )
                    )
                    self._connection.execute("COMMIT")
                finally:
                    self._active_transaction_count -= 1
            except sqlite3.Error as exc:
                if not self._rollback_if_needed_or_mark_unusable():
                    raise HostDurableError(
                        "Host durable transaction rollback failed; connection is unusable"
                    ) from exc
                if _is_busy_or_locked(exc):
                    if attempt >= max_attempts:
                        raise HostTransactionRetryExhaustedError(
                            "Host durable read transaction busy retry exhausted",
                            attempts=attempt,
                        ) from exc
                    time.sleep(delay_seconds)
                    delay_seconds = min(
                        delay_seconds * self._sqlite_policy.write_retry_backoff_multiplier,
                        self._sqlite_policy.write_retry_max_delay_seconds,
                    )
                    continue
                raise _classify_sqlite_error(exc) from exc
            except HostDurableError as exc:
                if not self._rollback_if_needed_or_mark_unusable():
                    raise HostDurableError(
                        "Host durable transaction rollback failed; connection is unusable"
                    ) from exc
                raise
            except Exception as exc:
                if not self._rollback_if_needed_or_mark_unusable():
                    raise HostDurableError(
                        "Host durable transaction rollback failed; connection is unusable"
                    ) from exc
                raise
            return result

    def _raise_if_connection_unusable(self) -> None:
        """拒绝继续复用已知不可收口的 SQLite connection。

        :returns: ``None``。
        :raises HostDurableError: 连接已因 rollback 失败被标记为不可用时抛出。
        """

        if self._connection_unusable:
            raise HostDurableError(
                "Host durable transaction runner connection is unusable"
            )

    def _rollback_if_needed_or_mark_unusable(self) -> bool:
        """在仍处于 transaction 时执行 rollback。

        :returns: rollback 成功时返回 ``True``，失败时返回 ``False``。
        """

        if not self._connection.in_transaction:
            return True
        if _rollback(self._connection):
            return True
        self._connection_unusable = True
        try:
            self._connection.close()
        except sqlite3.Error:
            _LOGGER.warning(
                "Host durable transaction rollback failed and connection close failed"
            )
        return False


def configure_connection_pragmas(connection: sqlite3.Connection, sqlite_policy: HostSQLiteStoragePolicy) -> None:
    """配置 Host durable SQLite connection 的基础 PRAGMA。

    :param connection: SQLite connection。
    :param sqlite_policy: busy timeout 配置来源。
    :returns: ``None``。
    :raises sqlite3.Error: PRAGMA 设置失败时抛出。
    """

    busy_timeout_ms = int(sqlite_policy.busy_timeout_seconds * _SQLITE_MILLISECONDS_PER_SECOND)
    connection.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(f"PRAGMA wal_autocheckpoint={_SQLITE_WAL_AUTOCHECKPOINT_PAGES}")


def _build_host_row(cursor: sqlite3.Cursor, row: sqlite3.Row) -> HostRow:
    """把 SQLite row 转换为 ``HostRow``。

    :param cursor: 已执行查询的 SQLite cursor。
    :param row: SQLite row。
    :returns: Host durable row 视图。
    """

    columns = tuple(column[0] for column in cursor.description)
    values = cast(tuple[SQLiteScalar, ...], tuple(row))
    return HostRow(columns=columns, values=values)


def _run_after_commit(callbacks: tuple[AfterCommitCallback, ...]) -> None:
    """执行 durable commit 后回调。

    :param callbacks: after-commit 回调元组。
    :returns: ``None``。
    :raises HostAfterCommitError: 任一 callback 失败时，在尝试全部 callback 后
        抛出第一个失败。
    """

    first_error: Exception | None = None
    first_error_index = 0
    for index, callback in enumerate(callbacks):
        try:
            callback()
        except Exception as exc:
            if first_error is None:
                first_error = exc
                first_error_index = index
                continue
            _LOGGER.exception(
                "Host durable after-commit callback secondary failure " "callback_index=%s first_callback_index=%s",
                index,
                first_error_index,
            )
    if first_error is not None:
        raise HostAfterCommitError(
            "Host durable after-commit callback failed",
            callback_index=first_error_index,
        ) from first_error


def _classify_sqlite_error(error: sqlite3.Error) -> HostDurableError:
    """把 SQLite error 分类为 Host durable structured error。

    :param error: SQLite error。
    :returns: Host durable structured error。
    """

    code = _sqlite_error_code(error)
    if code in (_SQLITE_CONSTRAINT_UNIQUE, _SQLITE_CONSTRAINT_PRIMARYKEY):
        return HostUniqueConstraintError("Host durable unique constraint failed")
    if code == _SQLITE_CONSTRAINT_FOREIGNKEY:
        return HostForeignKeyError("Host durable foreign key constraint failed")
    if code == _SQLITE_CONSTRAINT_CHECK:
        return HostDurableError("Host durable CHECK constraint failed")
    return HostDurableError("Host durable SQLite transaction failed")


def _is_busy_or_locked(error: sqlite3.Error) -> bool:
    """判断 SQLite error 是否是 busy / locked。

    :param error: SQLite error。
    :returns: busy 或 locked 返回 ``True``，否则返回 ``False``。
    """

    code = _sqlite_base_error_code(error)
    return code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)


def _sqlite_base_error_code(error: sqlite3.Error) -> int | None:
    """读取 SQLite base result code。

    Python 3.11 暴露的 ``sqlite_errorcode`` 可能是 extended result code；
    busy / locked retry 分类必须按低 8 位 base code 判断。

    :param error: SQLite error。
    :returns: SQLite base result code；缺失时返回 ``None``。
    """

    code = _sqlite_error_code(error)
    if code is None:
        return None
    return code & _SQLITE_EXTENDED_RESULT_CODE_MASK


def _sqlite_error_code(error: sqlite3.Error) -> int | None:
    """读取 Python 运行时 SQLite extended error code。

    ``sqlite3.Error.sqlite_errorcode`` 是 Python 3.11 暴露的 SQLite 直接错误码；
    类型 stub 可能未声明该运行时属性，因此只在缺失时按 ``None`` 收口，
    不用字符串消息猜测 busy / locked 或约束错误。

    :param error: SQLite error。
    :returns: SQLite error code；缺失或不是整数时返回 ``None``。
    """

    try:
        code = cast(_SQLiteErrorCodeCarrier, error).sqlite_errorcode
    except AttributeError:
        return None
    if isinstance(code, int):
        return code
    return None


def _rollback(connection: sqlite3.Connection) -> bool:
    """尽力回滚当前 SQLite transaction。

    :param connection: SQLite connection。
    :returns: rollback 成功时返回 ``True``，失败时返回 ``False``。
    """

    try:
        connection.execute("ROLLBACK")
    except sqlite3.Error:
        return False
    return True
