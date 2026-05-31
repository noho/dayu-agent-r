"""Host durable connection lifecycle 测试。"""

from __future__ import annotations

import sqlite3

from dayu.host.durable.connection import _close_connection_best_effort
from dayu.host.durable.options import HostSQLiteStoragePolicy
from dayu.host.durable.transaction import configure_connection_pragmas


class _FailingCloseConnection(sqlite3.Connection):
    """用于模拟 close 失败的 SQLite connection。"""

    def close(self) -> None:
        """模拟初始化失败清理阶段的 close 异常。

        :returns: 永不返回。
        :raises sqlite3.OperationalError: 始终抛出。
        """

        raise sqlite3.OperationalError("close failed")


def test_close_connection_best_effort_suppresses_close_failure() -> None:
    """初始化失败清理时 close 失败不能掩盖原始初始化错误。"""

    connection = sqlite3.connect(":memory:", factory=_FailingCloseConnection)
    try:
        _close_connection_best_effort(connection)
    finally:
        sqlite3.Connection.close(connection)


def test_configure_connection_pragmas_sets_wal_autocheckpoint() -> None:
    """SQLite 连接初始化必须显式启用 WAL auto-checkpoint 管理。"""

    connection = sqlite3.connect(":memory:")
    try:
        configure_connection_pragmas(connection, HostSQLiteStoragePolicy())
        rows = connection.execute("PRAGMA wal_autocheckpoint").fetchall()
        assert rows == [(256,)]
    finally:
        connection.close()
