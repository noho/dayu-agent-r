"""Host durable SQLite connection 与 store lifecycle。

本模块负责准备 DB parent directory、打开 SQLite connection、设置 PRAGMA、
执行 fresh bootstrap / schema validation，并返回 Host durable store 内部句柄。
它不实现 EventLog append、payload descriptor、idempotency、liveness 或 Host
command path 行为。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType

from dayu.host.durable.errors import HostDurableConfigError, HostDurableError
from dayu.host.durable.options import HostDurableStoreOptions
from dayu.host.durable.schema import (
    bootstrap_host_durable_store,
    validate_host_schema_version,
)
from dayu.host.durable.transaction import (
    HostTransactionRunner,
    configure_connection_pragmas,
)


class HostDurableStore:
    """Host durable store 内部句柄。

    :param options: 已校验的 Host durable store 打开选项。
    :param connection: 由本 store 持有的 SQLite connection。
    """

    def __init__(
        self,
        options: HostDurableStoreOptions,
        connection: sqlite3.Connection,
    ) -> None:
        """初始化 Host durable store 句柄。

        :param options: 已校验的 Host durable store 打开选项。
        :param connection: 由本 store 持有的 SQLite connection。
        :returns: ``None``。
        """

        self._options = options
        self._connection = connection
        self._transaction_runner = HostTransactionRunner(
            connection,
            options.sqlite_policy,
            payload_inline_threshold_bytes=(
                options.payload_policy.payload_inline_threshold_bytes
            ),
        )
        self._closed = False

    @property
    def options(self) -> HostDurableStoreOptions:
        """返回本 store 的打开选项。

        :returns: Host durable store 打开选项。
        """

        return self._options

    @property
    def transaction_runner(self) -> HostTransactionRunner:
        """返回本 store 持有的 transaction runner。

        :returns: Host durable write transaction runner。
        :raises HostDurableError: store 已关闭时抛出。
        """

        self._raise_if_closed()
        return self._transaction_runner

    def connect(self) -> sqlite3.Connection:
        """打开一条新的独立 Host durable SQLite connection。

        该方法供后续 Host durable 内部模块和测试验证 connection-level PRAGMA
        使用；调用方负责关闭返回的 connection。

        :returns: 已设置 PRAGMA 并校验 schema version 的 SQLite connection。
        :raises HostDurableConfigError: DB parent 目录不可用时抛出。
        :raises HostDurableError: SQLite connection 或 schema validation 失败时抛出。
        """

        self._raise_if_closed()
        return _open_configured_connection(self._options)

    def close(self) -> None:
        """关闭 store 持有的 SQLite connection。

        :returns: ``None``。
        :raises HostDurableError: 存在活跃 transaction 时抛出，避免 SQLite
            close 隐式 rollback 未提交写入。
        """

        if self._closed:
            return
        if self._transaction_runner.has_active_transaction:
            raise HostDurableError(
                "Host durable store cannot close with active transaction"
            )
        self._connection.close()
        self._closed = True

    def __enter__(self) -> "HostDurableStore":
        """进入 context manager。

        :returns: 当前 store。
        :raises HostDurableError: store 已关闭时抛出。
        """

        self._raise_if_closed()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        """退出 context manager 并关闭 store。

        :param exc_type: 异常类型。
        :param exc: 异常实例。
        :param tb: traceback。
        :returns: 始终返回 ``False``，不压制异常。
        """

        self.close()
        return False

    def _raise_if_closed(self) -> None:
        """检查 store 是否已关闭。

        :returns: ``None``。
        :raises HostDurableError: store 已关闭时抛出。
        """

        if self._closed:
            raise HostDurableError("Host durable store is closed")


def open_host_durable_store(
    options: HostDurableStoreOptions,
) -> HostDurableStore:
    """打开 Host durable store 并完成 fresh bootstrap / schema validation。

    :param options: Host durable store 打开选项。
    :returns: Host durable store 内部句柄。
    :raises HostDurableConfigError: DB parent 目录不可用时抛出。
    :raises HostDurableError: SQLite connection、bootstrap 或 validation 失败时抛出。
    """

    _prepare_database_parent(options.db_path, options.create_parent_dirs)
    connection = _open_raw_connection(options)
    try:
        configure_connection_pragmas(connection, options.sqlite_policy)
        bootstrap_host_durable_store(connection)
        validate_host_schema_version(connection)
    except (sqlite3.Error, HostDurableError) as exc:
        _close_connection_best_effort(connection)
        if isinstance(exc, HostDurableError):
            raise
        raise HostDurableError("Host durable SQLite bootstrap failed") from exc
    return HostDurableStore(options, connection)


def _open_configured_connection(
    options: HostDurableStoreOptions,
) -> sqlite3.Connection:
    """打开并配置独立 Host durable SQLite connection。

    :param options: Host durable store 打开选项。
    :returns: 已配置并校验 schema version 的 SQLite connection。
    :raises HostDurableConfigError: DB parent 目录不可用时抛出。
    :raises HostDurableError: SQLite connection 或 schema validation 失败时抛出。
    """

    _prepare_database_parent(options.db_path, options.create_parent_dirs)
    connection = _open_raw_connection(options)
    try:
        configure_connection_pragmas(connection, options.sqlite_policy)
        validate_host_schema_version(connection)
    except (sqlite3.Error, HostDurableError) as exc:
        _close_connection_best_effort(connection)
        if isinstance(exc, HostDurableError):
            raise
        raise HostDurableError("Host durable SQLite connection setup failed") from exc
    return connection


def _open_raw_connection(options: HostDurableStoreOptions) -> sqlite3.Connection:
    """打开未配置 PRAGMA 的 SQLite connection。

    :param options: Host durable store 打开选项。
    :returns: SQLite connection。
    :raises HostDurableError: SQLite connection 创建失败时抛出。
    """

    try:
        return sqlite3.connect(
            options.db_path,
            timeout=options.sqlite_policy.busy_timeout_seconds,
            isolation_level=None,
        )
    except sqlite3.Error as exc:
        raise HostDurableError("Host durable SQLite connection failed") from exc


def _close_connection_best_effort(connection: sqlite3.Connection) -> None:
    """尽力关闭初始化失败后的 SQLite connection。

    :param connection: 初始化过程中需要清理的 SQLite connection。
    :returns: ``None``。
    """

    try:
        connection.close()
    except sqlite3.Error:
        return


def _prepare_database_parent(db_path: Path, create_parent_dirs: bool) -> None:
    """准备 Host durable SQLite DB parent directory。

    :param db_path: Host durable SQLite DB 文件路径。
    :param create_parent_dirs: parent 缺失时是否创建。
    :returns: ``None``。
    :raises HostDurableConfigError: parent 缺失且禁止创建，或 parent 不是目录时抛出。
    """

    parent = db_path.parent
    if parent.exists():
        if not parent.is_dir():
            raise HostDurableConfigError("Host durable db_path parent is not a directory")
        return
    if not create_parent_dirs:
        raise HostDurableConfigError("Host durable db_path parent does not exist")
    parent.mkdir(parents=True, exist_ok=True)
