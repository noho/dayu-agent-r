"""Host durable actor 的线程、取消与 FIFO contract 测试。"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from pathlib import Path

import pytest

from dayu.host._durable_actor import open_durable_actor
from dayu.host.api import HostCommandHandleOptions
from dayu.host.command import HostCommandHandle, create_host_command_handle
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.open_host import _run_callback_on_event_loop


def _command_options(tmp_path: Path) -> HostCommandHandleOptions:
    """构造 actor 测试 command options。

    :param tmp_path: pytest 临时目录。
    :returns: command handle options。
    :raises Exception: 不主动抛出异常。
    """

    return HostCommandHandleOptions(
        host_handle_id="durable-actor-test",
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=0.2,
        sqlite_write_busy_retry_count=4,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.01,
        payload_inline_threshold_bytes=4096,
        context_window_size=8192,
        reserved_output_tokens=1024,
    )


def _durable_options(options: HostCommandHandleOptions) -> HostDurableStoreOptions:
    """把 command options 投影为同源 durable store policy。

    :param options: command handle options。
    :returns: durable store options。
    :raises Exception: 不主动抛出异常。
    """

    return HostDurableStoreOptions(
        db_path=options.db_path,
        create_parent_dirs=options.create_parent_dirs,
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=options.sqlite_busy_timeout_seconds,
            write_busy_retry_count=options.sqlite_write_busy_retry_count,
            write_retry_initial_delay_seconds=(
                options.sqlite_write_retry_initial_delay_seconds
            ),
            write_retry_backoff_multiplier=(
                options.sqlite_write_retry_backoff_multiplier
            ),
            write_retry_max_delay_seconds=(
                options.sqlite_write_retry_max_delay_seconds
            ),
        ),
        payload_policy=PayloadStoragePolicy(
            payload_inline_threshold_bytes=options.payload_inline_threshold_bytes,
            artifact_root=options.artifact_root,
            create_artifact_root=options.create_parent_dirs,
        ),
    )


def _connection_pragmas(connection: sqlite3.Connection) -> tuple[str, int, int]:
    """读取连接的关键 SQLite policy 投影。

    :param connection: 待检查 SQLite connection。
    :returns: journal mode、busy timeout 毫秒与 foreign_keys 开关。
    :raises sqlite3.Error: PRAGMA 读取失败时透传。
    """

    journal_mode_row = connection.execute("PRAGMA journal_mode").fetchone()
    busy_timeout_row = connection.execute("PRAGMA busy_timeout").fetchone()
    foreign_keys_row = connection.execute("PRAGMA foreign_keys").fetchone()
    assert journal_mode_row is not None
    assert busy_timeout_row is not None
    assert foreign_keys_row is not None
    return (
        str(journal_mode_row[0]),
        int(busy_timeout_row[0]),
        int(foreign_keys_row[0]),
    )


@pytest.mark.asyncio
async def test_actor_owns_real_sqlite_handle_on_one_worker_thread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """handle/store/connection 的 create/use/close 全部留在 actor thread。"""

    options = _command_options(tmp_path)
    create_threads: list[int] = []
    use_threads: list[int] = []
    close_threads: list[int] = []
    original_close = HostCommandHandle.close

    def factory() -> HostCommandHandle:
        """在 actor thread 打开真实 command handle。

        :returns: 真实 command handle。
        :raises Exception: durable store 打开失败时透传。
        """

        create_threads.append(threading.get_ident())
        return create_host_command_handle(options)

    def record_close(self: HostCommandHandle) -> None:
        """记录 command handle 实际关闭线程。

        :param self: 待关闭 command handle。
        :returns: ``None``。
        :raises Exception: 原始 close 失败时透传。
        """

        close_threads.append(threading.get_ident())
        original_close(self)

    monkeypatch.setattr(HostCommandHandle, "close", record_close)
    actor = await open_durable_actor(
        factory,
        thread_name_prefix="test-durable-actor-owner",
    )
    scheduler_store = open_host_durable_store(_durable_options(options))
    scheduler_connection = scheduler_store.connect()
    try:
        scheduler_connection_id = id(scheduler_connection)
        scheduler_pragmas = _connection_pragmas(scheduler_connection)

        def inspect_actor_connection(handle: HostCommandHandle) -> tuple[int, tuple[str, int, int]]:
            """在 actor thread 打开、使用并关闭独立配置连接。

            :param handle: actor 私有 command handle。
            :returns: connection identity 与关键 PRAGMA。
            :raises Exception: durable connection 操作失败时透传。
            """

            use_threads.append(threading.get_ident())
            connection = handle._open_durable_connection()
            try:
                return id(connection), _connection_pragmas(connection)
            finally:
                connection.close()

        actor_connection_id, actor_pragmas = await actor.call(
            inspect_actor_connection
        )
    finally:
        await actor.close()
        scheduler_connection.close()
        scheduler_store.close()

    assert create_threads == use_threads == close_threads
    assert create_threads[0] != threading.get_ident()
    assert actor_connection_id != scheduler_connection_id
    assert actor_pragmas == scheduler_pragmas


@pytest.mark.asyncio
async def test_caller_cancellation_preserves_underlying_fifo_completion(
    tmp_path: Path,
) -> None:
    """caller cancel 不终止已开始 operation，后续 call 按提交顺序完成。"""

    started = threading.Event()
    release = threading.Event()
    order: list[str] = []
    actor = await open_durable_actor(
        lambda: create_host_command_handle(_command_options(tmp_path)),
        thread_name_prefix="test-durable-actor-cancel",
    )

    def first_operation(_handle: HostCommandHandle) -> str:
        """阻塞首个 operation，模拟事务或 after-commit wake 尚未收口。

        :param _handle: actor 私有 command handle。
        :returns: 固定结果。
        :raises RuntimeError: barrier 未在测试时限内释放时抛出。
        """

        order.append("first-start")
        started.set()
        if not release.wait(timeout=2):
            raise RuntimeError("actor test release barrier timed out")
        order.append("first-end")
        return "first"

    def second_operation(_handle: HostCommandHandle) -> str:
        """记录 FIFO 中的第二个 operation。

        :param _handle: actor 私有 command handle。
        :returns: 固定结果。
        :raises Exception: 不主动抛出异常。
        """

        order.append("second")
        return "second"

    first_task = asyncio.create_task(actor.call(first_operation))
    assert await asyncio.to_thread(started.wait, 1)
    first_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_task
    second_task = asyncio.create_task(actor.call(second_operation))
    release.set()
    assert await second_task == "second"
    await actor.close()

    assert order == ["first-start", "first-end", "second"]


@pytest.mark.asyncio
async def test_event_loop_bridge_exception_returns_through_actor(
    tmp_path: Path,
) -> None:
    """loop callback 异常回到原 actor caller，且 actor 不被毒化。"""

    loop = asyncio.get_running_loop()
    actor = await open_durable_actor(
        lambda: create_host_command_handle(_command_options(tmp_path)),
        thread_name_prefix="test-durable-actor-bridge-error",
    )

    def raise_on_loop() -> str:
        """在 opener loop 抛出预设 bridge 错误。

        :returns: 不返回。
        :raises ValueError: 始终抛出。
        """

        raise ValueError("bridge callback failed")

    def bridge_operation(_handle: HostCommandHandle) -> str:
        """从 actor thread 同步调用 opener-loop callback。

        :param _handle: actor 私有 command handle。
        :returns: callback 返回值。
        :raises ValueError: opener-loop callback 错误原样透传。
        """

        return _run_callback_on_event_loop(loop, raise_on_loop)

    with pytest.raises(ValueError, match="bridge callback failed"):
        await actor.call(bridge_operation)
    assert await actor.call(lambda _handle: "next-call") == "next-call"
    await actor.close()
