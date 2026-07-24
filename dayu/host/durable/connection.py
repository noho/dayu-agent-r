"""Host durable SQLite connection 与 store lifecycle。

本模块负责准备 DB parent directory、打开 SQLite connection、设置 PRAGMA、
执行 fresh bootstrap / schema validation，并返回 Host durable store 内部句柄。
它不实现 EventLog append、payload descriptor、idempotency、liveness 或 Host
command path 行为。
"""

from __future__ import annotations

import sqlite3
import stat
from pathlib import Path
from types import TracebackType
from typing import TypeVar

from dayu.host.durable.errors import HostDurableConfigError, HostDurableError
from dayu.host.durable.options import HostDurableStoreOptions
from dayu.host.durable.options import HostSQLiteStoragePolicy, PayloadStoragePolicy
from dayu.host.durable.schema import (
    bootstrap_host_durable_store,
    validate_host_durable_schema,
)
from dayu.host.durable.transaction import (
    HostReadTransactionOperation,
    HostTransaction,
    HostTransactionRunner,
    configure_connection_pragmas,
    configure_read_only_connection_pragmas,
)

T = TypeVar("T")


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
            artifact_root=options.payload_policy.artifact_root,
            payload_inline_threshold_bytes=(
                options.payload_policy.payload_inline_threshold_bytes
            ),
            create_artifact_root=options.payload_policy.create_artifact_root,
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

        :returns: 已设置 PRAGMA 并校验当前 schema 结构的 SQLite connection。
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


class HostDurableReadStore:
    """Host durable store 的物理只读句柄。

    :param db_path: 已校验存在的 Host SQLite 文件。
    :param artifact_root: payload resolver 使用的显式 artifact root。
    :param connection: 以 SQLite ``mode=ro`` 打开的 connection。
    """

    def __init__(
        self,
        *,
        db_path: Path,
        artifact_root: Path,
        connection: sqlite3.Connection,
    ) -> None:
        """初始化物理只读 store。

        :param db_path: 已校验存在的 Host SQLite 文件。
        :param artifact_root: payload resolver 使用的显式 artifact root。
        :param connection: 以 SQLite ``mode=ro`` 打开的 connection。
        :returns: ``None``。
        :raises TypeError: 参数类型错误时抛出。
        """

        if not isinstance(db_path, Path):
            raise TypeError("db_path must be Path")
        if not isinstance(artifact_root, Path):
            raise TypeError("artifact_root must be Path")
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be sqlite3.Connection")
        payload_policy = PayloadStoragePolicy(
            artifact_root=artifact_root,
            create_artifact_root=False,
        )
        self._db_path = db_path
        self._artifact_root = artifact_root
        self._payload_inline_threshold_bytes = payload_policy.payload_inline_threshold_bytes
        self._connection = connection
        self._closed = False
        self._read_active = False

    def run_read(self, operation: HostReadTransactionOperation[T]) -> T:
        """在单个 SQLite read transaction 中运行查询。

        只读 store 不消费 write retry/backoff policy，也不暴露 write runner。

        :param operation: typed read transaction body。
        :returns: ``operation`` 的返回值。
        :raises HostDurableError: store 已关闭、嵌套读取或 SQLite 读取失败时抛出。
        :raises Exception: operation 自身的非 durable 异常在 rollback 后透传。
        """

        self._raise_if_closed()
        if self._read_active:
            raise HostDurableError("Host durable read store does not allow nesting")
        try:
            self._connection.execute("BEGIN")
            self._read_active = True
            try:
                result = operation(
                    HostTransaction(
                        self._connection,
                        artifact_root=self._artifact_root,
                        payload_inline_threshold_bytes=(self._payload_inline_threshold_bytes),
                        create_artifact_root=False,
                    )
                )
                self._connection.execute("COMMIT")
            finally:
                self._read_active = False
        except sqlite3.Error as exc:
            _rollback_read_best_effort(self._connection)
            raise HostDurableError("Host durable read-only transaction failed") from exc
        except HostDurableError:
            _rollback_read_best_effort(self._connection)
            raise
        except Exception:
            _rollback_read_best_effort(self._connection)
            raise
        return result

    def close(self) -> None:
        """关闭只读 connection。

        :returns: ``None``。
        :raises HostDurableError: 存在活跃 read transaction 时抛出。
        :raises sqlite3.Error: SQLite close 失败时抛出。
        """

        if self._closed:
            return
        if self._read_active:
            raise HostDurableError("Host durable read store cannot close with active transaction")
        self._connection.close()
        self._closed = True

    def __enter__(self) -> "HostDurableReadStore":
        """进入只读 store context。

        :returns: 当前只读 store。
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
        """退出 context 并关闭只读 store。

        :param exc_type: 异常类型。
        :param exc: 异常实例。
        :param tb: traceback。
        :returns: 始终返回 ``False``。
        :raises sqlite3.Error: SQLite close 失败时抛出。
        """

        self.close()
        return False

    def _raise_if_closed(self) -> None:
        """拒绝复用已关闭 store。

        :returns: ``None``。
        :raises HostDurableError: store 已关闭时抛出。
        """

        if self._closed:
            raise HostDurableError("Host durable read store is closed")


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
    except (sqlite3.Error, HostDurableError) as exc:
        _close_connection_best_effort(connection)
        if isinstance(exc, HostDurableError):
            raise
        raise HostDurableError("Host durable SQLite bootstrap failed") from exc
    return HostDurableStore(options, connection)


def open_host_durable_read_store(
    *,
    db_path: Path,
    artifact_root: Path,
    sqlite_policy: HostSQLiteStoragePolicy,
) -> HostDurableReadStore:
    """以物理只读模式打开并校验现有 Host durable store。

    :param db_path: 必须已存在的 absolute Host SQLite regular file。
    :param artifact_root: resolver 使用的显式 absolute artifact root。
    :param sqlite_policy: durable SQLite policy；只使用 busy timeout。
    :returns: 仅暴露 ``run_read`` 与 lifecycle 的只读 store。
    :raises HostDurableConfigError: 路径或参数无效时抛出。
    :raises HostDurableError: SQLite URI open、PRAGMA 或 schema 校验失败时抛出。
    """

    _require_read_only_database_file(db_path)
    if not isinstance(artifact_root, Path):
        raise HostDurableConfigError("artifact_root must be Path")
    if not artifact_root.is_absolute():
        raise HostDurableConfigError("artifact_root must be absolute")
    if not isinstance(sqlite_policy, HostSQLiteStoragePolicy):
        raise HostDurableConfigError("sqlite_policy must be HostSQLiteStoragePolicy")
    try:
        connection = sqlite3.connect(
            db_path.as_uri() + "?mode=ro",
            uri=True,
            timeout=sqlite_policy.busy_timeout_seconds,
            isolation_level=None,
        )
    except (sqlite3.Error, ValueError) as exc:
        raise HostDurableError("Host durable read-only SQLite open failed") from exc
    try:
        configure_read_only_connection_pragmas(connection, sqlite_policy)
        validate_host_durable_schema(connection)
    except (sqlite3.Error, HostDurableError) as exc:
        _close_connection_best_effort(connection)
        if isinstance(exc, HostDurableError):
            raise
        raise HostDurableError("Host durable read-only SQLite setup failed") from exc
    return HostDurableReadStore(
        db_path=db_path,
        artifact_root=artifact_root,
        connection=connection,
    )


def _open_configured_connection(
    options: HostDurableStoreOptions,
) -> sqlite3.Connection:
    """打开并配置独立 Host durable SQLite connection。

    :param options: Host durable store 打开选项。
    :returns: 已配置并校验当前 schema 结构的 SQLite connection。
    :raises HostDurableConfigError: DB parent 目录不可用时抛出。
    :raises HostDurableError: SQLite connection 或 schema validation 失败时抛出。
    """

    _prepare_database_parent(options.db_path, options.create_parent_dirs)
    connection = _open_raw_connection(options)
    try:
        configure_connection_pragmas(connection, options.sqlite_policy)
        validate_host_durable_schema(connection)
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


def _rollback_read_best_effort(connection: sqlite3.Connection) -> None:
    """尽力回滚失败的只读 transaction。

    :param connection: 可能仍处于 read transaction 的 connection。
    :returns: ``None``。
    :raises: 无。
    """

    if not connection.in_transaction:
        return
    try:
        connection.execute("ROLLBACK")
    except sqlite3.Error:
        return


def _require_read_only_database_file(db_path: Path) -> None:
    """校验只读 opener 的 absolute regular DB 文件。

    :param db_path: 待校验 SQLite 路径。
    :returns: ``None``。
    :raises HostDurableConfigError: 路径类型、绝对性、存在性或类型非法时抛出。
    """

    if not isinstance(db_path, Path):
        raise HostDurableConfigError("db_path must be Path")
    if not db_path.is_absolute():
        raise HostDurableConfigError("db_path must be absolute")
    try:
        mode = db_path.stat().st_mode
    except OSError as exc:
        raise HostDurableConfigError("Host durable read-only DB must exist") from exc
    if not stat.S_ISREG(mode):
        raise HostDurableConfigError("Host durable read-only DB must be regular file")


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
