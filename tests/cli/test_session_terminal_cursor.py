"""``dayu.cli.session_terminal_cursor`` 测试。"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

import dayu.cli.session_terminal_cursor as cursor_module
from dayu.cli.session_terminal_cursor import (
    CLI_TERMINAL_CURSOR_SEEN_IDS_MAX_SIZE,
    CliTerminalCursorError,
    CliTerminalCursorRecord,
    advance_cli_terminal_cursor,
    cli_terminal_cursor_file_path,
    read_cli_terminal_cursor,
)
from dayu.host.api import OutboxTerminalCursor


@pytest.mark.asyncio
async def test_missing_cursor_file_returns_empty_record(tmp_path: Path) -> None:
    """cursor 文件缺失时读取应返回空记录。"""

    record = await read_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-1",
    )

    assert record.terminal_cursor == OutboxTerminalCursor(event_sequence=0)
    assert record.seen_terminal_event_ids == ()


@pytest.mark.asyncio
async def test_advance_then_read_cursor_record(tmp_path: Path) -> None:
    """advance 后再次读取应返回写入的 cursor record。"""

    updated = await advance_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-1",
        terminal_event_id="terminal-1",
        event_sequence=7,
    )
    read_back = await read_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-1",
    )

    assert updated == read_back
    assert read_back.terminal_cursor == OutboxTerminalCursor(event_sequence=7)
    assert read_back.seen_terminal_event_ids == ("terminal-1",)


@pytest.mark.asyncio
async def test_cursor_store_uses_workspace_root_dayu_dir(tmp_path: Path) -> None:
    """terminal cursor 不得在已解析 workspace root 下再创建 workspace 子目录。

    :param tmp_path: pytest 临时 workspace root。
    :returns: ``None``。
    :raises AssertionError: cursor 路径或创建目录不符合预期时抛出。
    """

    await advance_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-1",
        terminal_event_id="terminal-1",
        event_sequence=1,
    )

    assert cli_terminal_cursor_file_path(tmp_path) == (
        tmp_path / ".dayu" / "cli" / "terminal_cursors.json"
    )
    assert cli_terminal_cursor_file_path(tmp_path).is_file()
    assert not (tmp_path / "workspace").exists()


@pytest.mark.asyncio
async def test_advance_does_not_move_sequence_backward(tmp_path: Path) -> None:
    """低 sequence 更新不得回退已保存 watermark。"""

    await advance_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-1",
        terminal_event_id="terminal-high",
        event_sequence=9,
    )
    record = await advance_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-1",
        terminal_event_id="terminal-low",
        event_sequence=3,
    )

    assert record.terminal_cursor == OutboxTerminalCursor(event_sequence=9)
    assert record.seen_terminal_event_ids == ("terminal-high", "terminal-low")


@pytest.mark.asyncio
async def test_seen_terminal_ids_are_trimmed_oldest_first(tmp_path: Path) -> None:
    """seen ids 超过窗口时应裁剪最旧 id。"""

    for index in range(CLI_TERMINAL_CURSOR_SEEN_IDS_MAX_SIZE + 2):
        await advance_cli_terminal_cursor(
            workspace_root=tmp_path,
            session_id="session-1",
            terminal_event_id=f"terminal-{index}",
            event_sequence=index + 1,
        )

    record = await read_cli_terminal_cursor(
        workspace_root=tmp_path,
        session_id="session-1",
    )

    assert len(record.seen_terminal_event_ids) == CLI_TERMINAL_CURSOR_SEEN_IDS_MAX_SIZE
    assert record.seen_terminal_event_ids[0] == "terminal-2"
    assert record.seen_terminal_event_ids[-1] == (
        f"terminal-{CLI_TERMINAL_CURSOR_SEEN_IDS_MAX_SIZE + 1}"
    )


@pytest.mark.asyncio
async def test_corrupt_json_fails_fast(tmp_path: Path) -> None:
    """腐坏 JSON 不得静默 reset。"""

    path = cli_terminal_cursor_file_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(CliTerminalCursorError, match="JSON"):
        await read_cli_terminal_cursor(
            workspace_root=tmp_path,
            session_id="session-1",
        )


@pytest.mark.asyncio
async def test_invalid_record_fields_fail_fast(tmp_path: Path) -> None:
    """非法字段不应被兼容读取。"""

    path = cli_terminal_cursor_file_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"session-1":{"last_seen_terminal_event_sequence":-1,'
        '"seen_terminal_event_ids":[]}}\n',
        encoding="utf-8",
    )

    with pytest.raises(CliTerminalCursorError, match="sequence"):
        await read_cli_terminal_cursor(
            workspace_root=tmp_path,
            session_id="session-1",
        )


@pytest.mark.asyncio
async def test_duplicate_seen_ids_fail_fast(tmp_path: Path) -> None:
    """重复 seen terminal id 必须结构化失败。"""

    path = cli_terminal_cursor_file_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"session-1":{"last_seen_terminal_event_sequence":1,'
        '"seen_terminal_event_ids":["terminal-1","terminal-1"]}}\n',
        encoding="utf-8",
    )

    with pytest.raises(CliTerminalCursorError, match="重复"):
        await read_cli_terminal_cursor(
            workspace_root=tmp_path,
            session_id="session-1",
        )


@pytest.mark.asyncio
async def test_async_read_uses_executor_thread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """async facade 不得在 event loop 线程直接执行同步读。"""

    event_loop_thread_id = threading.get_ident()
    observed_thread_ids: list[int] = []

    def fake_sync_read(
        *,
        workspace_root: Path,
        session_id: str,
    ) -> CliTerminalCursorRecord:
        """记录同步读所在线程并返回空 cursor。

        :param workspace_root: workspace 根目录。
        :param session_id: Host Session id。
        :returns: 空 cursor record。
        :raises Exception: 不主动抛出异常。
        """

        observed_thread_ids.append(threading.get_ident())
        return CliTerminalCursorRecord(
            terminal_cursor=OutboxTerminalCursor(event_sequence=0),
            seen_terminal_event_ids=(),
        )

    monkeypatch.setattr(
        cursor_module,
        "_read_cli_terminal_cursor_sync",
        fake_sync_read,
    )

    await read_cli_terminal_cursor(workspace_root=tmp_path, session_id="session-1")

    assert observed_thread_ids
    assert observed_thread_ids[0] != event_loop_thread_id


@pytest.mark.asyncio
async def test_atomic_replace_failure_removes_temp_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """atomic replace 失败时不得留下本次临时文件。"""

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        """模拟 ``os.replace`` 失败。

        :param source: 临时文件路径。
        :param destination: 目标文件路径。
        :returns: ``None``。
        :raises OSError: 始终抛出测试异常。
        """

        raise OSError(f"replace failed: {source} -> {destination}")

    monkeypatch.setattr(cursor_module.os, "replace", fail_replace)

    with pytest.raises(CliTerminalCursorError, match="写入"):
        await advance_cli_terminal_cursor(
            workspace_root=tmp_path,
            session_id="session-1",
            terminal_event_id="terminal-1",
            event_sequence=1,
        )

    cursor_dir = cli_terminal_cursor_file_path(tmp_path).parent
    leftovers = [
        path
        for path in cursor_dir.iterdir()
        if path.name.startswith(".terminal_cursors.")
    ]
    assert leftovers == []
