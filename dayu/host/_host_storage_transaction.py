"""Host P6 durable storage Unit of Work / transaction owner.

本模块定义 Host internal 唯一事务边界。durable EventLog append、cursor
allocation、Run / Attempt minimal state、terminal result snapshot、
projection checkpoint 等写入必须共享同一 SQLite connection / transaction。

设计要点：

- 单连接 + WAL 模式：保证多进程读时不阻塞写，写时通过 ``BEGIN IMMEDIATE``
  获取 RESERVED 锁。
- ``transaction()`` 异步上下文管理：在协程内串行获取写事务，事务体内可调
  用 :class:`HostStorageTransaction` 上挂载的内部 store writer。
- 事务体 ``raise`` 时自动 ``ROLLBACK``，正常退出时 ``COMMIT``。
- commit 后的 post-commit hook 用于通知本进程订阅者；hook 在 commit 之前
  采集，commit 失败时不触发。
- 本模块只暴露 internal 类型，禁止进入 ``dayu.host.__all__``。

:py:class:`HostStorage` 自身不写业务字段；具体 schema 由 P6 各 store 模块
``ensure_schema`` 完成。
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import AsyncGenerator, Callable, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TypeAlias

_PRAGMA_SETUP: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA busy_timeout=5000",
)

_BEGIN_IMMEDIATE: str = "BEGIN IMMEDIATE"
_COMMIT: str = "COMMIT"
_ROLLBACK: str = "ROLLBACK"

PostCommitHook: TypeAlias = Callable[[], None]
SqlParameter: TypeAlias = str | int | float | bool | bytes | None
"""SQLite 原生支持的绑定参数类型联合。"""


@dataclass(slots=True)
class HostStorageTransaction:
    """Host durable storage 单事务上下文。

    事务体内只能通过本对象提交 SQL 与 post-commit hook；不允许直接持有
    raw connection 跨事务复用。

    :param connection: SQLite 连接，由 :class:`HostStorage` 持有并复用。
    :param post_commit_hooks: commit 成功后触发的 hook 列表。
    """

    connection: sqlite3.Connection
    post_commit_hooks: list[PostCommitHook] = field(default_factory=list)

    def execute(
        self,
        sql: str,
        parameters: Iterable[SqlParameter] = (),
    ) -> sqlite3.Cursor:
        """在当前事务执行 SQL。

        :param sql: SQL 语句。
        :param parameters: 绑定参数。
        :returns: SQLite Cursor。
        :raises sqlite3.DatabaseError: 执行失败时抛出。
        """

        return self.connection.execute(sql, tuple(parameters))

    def executemany(
        self,
        sql: str,
        seq_of_parameters: Iterable[Iterable[SqlParameter]],
    ) -> sqlite3.Cursor:
        """在当前事务批量执行 SQL。

        :param sql: SQL 语句。
        :param seq_of_parameters: 参数序列。
        :returns: SQLite Cursor。
        :raises sqlite3.DatabaseError: 执行失败时抛出。
        """

        return self.connection.executemany(
            sql, [tuple(item) for item in seq_of_parameters]
        )

    def add_post_commit_hook(self, hook: PostCommitHook) -> None:
        """注册 commit 成功后回调。

        hook 在事务 commit 完成、锁释放之后才被同步调用；若事务回滚不会
        被触发。

        :param hook: 无参回调。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.post_commit_hooks.append(hook)


@dataclass(slots=True)
class HostStorage:
    """Host durable storage 连接拥有者。

    所有 P6 store 模块在写入时必须通过 :meth:`transaction` 获得共享事务
    上下文，禁止并行打开多个写事务，禁止在事务外写入。

    :param database_path: SQLite 数据库路径，``":memory:"`` 表示内存库。
    """

    database_path: str
    _connection: sqlite3.Connection | None = field(default=None, init=False)
    _write_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock,
        init=False,
    )
    _connection_lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
    )

    def open(self) -> None:
        """打开 SQLite 连接并配置 PRAGMA。

        重复调用是幂等的。

        :returns: 无返回值。
        :raises sqlite3.DatabaseError: 打开失败时抛出。
        """

        with self._connection_lock:
            if self._connection is not None:
                return
            connection = sqlite3.connect(
                self.database_path,
                check_same_thread=False,
                isolation_level=None,
            )
            for pragma in _PRAGMA_SETUP:
                connection.execute(pragma)
            self._connection = connection

    def close(self) -> None:
        """关闭 SQLite 连接。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        with self._connection_lock:
            if self._connection is None:
                return
            self._connection.close()
            self._connection = None

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[HostStorageTransaction, None]:
        """获取一个写事务上下文。

        采用 ``BEGIN IMMEDIATE`` 进入写锁，正常退出时 ``COMMIT``，异常时
        ``ROLLBACK``。同一进程内并发调用通过 ``asyncio.Lock`` 串行化。

        :returns: 事务上下文。
        :raises sqlite3.DatabaseError: 事务边界异常时抛出。
        """

        if self._connection is None:
            self.open()
        connection = self._connection
        if connection is None:
            raise RuntimeError("host storage connection unavailable")
        async with self._write_lock:
            await asyncio.to_thread(self._begin_immediate, connection)
            tx = HostStorageTransaction(connection=connection)
            try:
                yield tx
            except BaseException:
                await asyncio.to_thread(self._rollback, connection)
                raise
            await asyncio.to_thread(self._commit, connection)
            for hook in tx.post_commit_hooks:
                hook()

    def execute_read(
        self,
        sql: str,
        parameters: Iterable[SqlParameter] = (),
    ) -> list[sqlite3.Row]:
        """执行只读 SQL 并返回所有结果行。

        只读路径不进入写锁，但仍由同一连接序列化。

        :param sql: SQL 语句。
        :param parameters: 绑定参数。
        :returns: 结果行列表。
        :raises sqlite3.DatabaseError: 执行失败时抛出。
        """

        if self._connection is None:
            self.open()
        connection = self._connection
        if connection is None:
            raise RuntimeError("host storage connection unavailable")
        with self._connection_lock:
            cursor = connection.execute(sql, tuple(parameters))
            try:
                return list(cursor.fetchall())
            finally:
                cursor.close()

    def _begin_immediate(self, connection: sqlite3.Connection) -> None:
        """在当前线程开启 IMMEDIATE 事务。

        :param connection: SQLite 连接。
        :returns: 无返回值。
        :raises sqlite3.DatabaseError: 开启失败时抛出。
        """

        connection.execute(_BEGIN_IMMEDIATE)

    def _commit(self, connection: sqlite3.Connection) -> None:
        """在当前线程提交事务。

        :param connection: SQLite 连接。
        :returns: 无返回值。
        :raises sqlite3.DatabaseError: 提交失败时抛出。
        """

        connection.execute(_COMMIT)

    def _rollback(self, connection: sqlite3.Connection) -> None:
        """在当前线程回滚事务。

        :param connection: SQLite 连接。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        try:
            connection.execute(_ROLLBACK)
        except sqlite3.DatabaseError:
            # 某些边界（连接已关闭）下 rollback 会失败，吞掉避免覆盖原异常。
            return


__all__ = [
    "HostStorage",
    "HostStorageTransaction",
    "PostCommitHook",
]
