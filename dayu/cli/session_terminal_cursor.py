"""CLI 本地 Session terminal cursor 存取。

本模块只记录当前 workspace CLI 已成功展示过的 terminal 水位，用于
interactive startup backfill 去重。它不表达 Host durable truth，不读取
Host 内部存储，也不参与 Run / Session 状态判断。
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from dayu.contracts import JsonValue
from dayu.host.api import OutboxTerminalCursor
from dayu.runtime.filelock import file_lock
from dayu.runtime.workspace_paths import workspace_paths

CLI_TERMINAL_CURSOR_SEEN_IDS_MAX_SIZE: Final[int] = 200
_CURSOR_LOCK_FILE_NAME: Final[str] = "terminal_cursors.json.lock"
_TEMP_FILE_PREFIX: Final[str] = ".terminal_cursors."
_JSON_SESSION_SEQUENCE_FIELD: Final[str] = "last_seen_terminal_event_sequence"
_JSON_SESSION_SEEN_IDS_FIELD: Final[str] = "seen_terminal_event_ids"


class CliTerminalCursorError(RuntimeError):
    """CLI terminal cursor store 错误。"""


@dataclass(frozen=True, slots=True)
class CliTerminalCursorRecord:
    """单个 Session 的 CLI terminal cursor 记录。

    :param terminal_cursor: 已成功展示的 terminal event sequence 水位。
    :param seen_terminal_event_ids: 已成功展示的 terminal event id 有界窗口。
    """

    terminal_cursor: OutboxTerminalCursor
    seen_terminal_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """校验 cursor record。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: seen id 为空时抛出。
        """

        if not isinstance(self.terminal_cursor, OutboxTerminalCursor):
            raise TypeError("CliTerminalCursorRecord.terminal_cursor must be OutboxTerminalCursor")
        if not isinstance(self.seen_terminal_event_ids, tuple):
            raise TypeError("CliTerminalCursorRecord.seen_terminal_event_ids must be tuple")
        seen: set[str] = set()
        for terminal_event_id in self.seen_terminal_event_ids:
            if terminal_event_id == "":
                raise ValueError("CliTerminalCursorRecord.seen_terminal_event_ids must be non-empty")
            if terminal_event_id in seen:
                raise ValueError("CliTerminalCursorRecord.seen_terminal_event_ids must not contain duplicates")
            seen.add(terminal_event_id)


def empty_cli_terminal_cursor_record() -> CliTerminalCursorRecord:
    """返回空 CLI terminal cursor 记录。

    :returns: sequence 为 0、seen ids 为空的记录。
    :raises Exception: 不主动抛出异常。
    """

    return CliTerminalCursorRecord(
        terminal_cursor=OutboxTerminalCursor(event_sequence=0),
        seen_terminal_event_ids=(),
    )


def cli_terminal_cursor_file_path(workspace_root: Path) -> Path:
    """计算 workspace-local CLI terminal cursor 文件路径。

    :param workspace_root: workspace 根目录。
    :returns: terminal cursor JSON 文件路径。
    :raises Exception: 不主动抛出异常。
    """

    return workspace_paths(workspace_root).cli_terminal_cursor_file


async def read_cli_terminal_cursor(
    *,
    workspace_root: Path,
    session_id: str,
) -> CliTerminalCursorRecord:
    """异步读取指定 Session 的 CLI terminal cursor。

    :param workspace_root: workspace 根目录。
    :param session_id: Host Session id。
    :returns: 该 Session 的 cursor record；文件缺失时返回空记录。
    :raises CliTerminalCursorError: JSON 腐坏或字段非法时抛出。
    """

    return await asyncio.to_thread(
        _read_cli_terminal_cursor_sync,
        workspace_root=workspace_root,
        session_id=session_id,
    )


async def advance_cli_terminal_cursor(
    *,
    workspace_root: Path,
    session_id: str,
    terminal_event_id: str,
    event_sequence: int,
) -> CliTerminalCursorRecord:
    """异步前进指定 Session 的 CLI terminal cursor。

    :param workspace_root: workspace 根目录。
    :param session_id: Host Session id。
    :param terminal_event_id: 已成功展示的 terminal event id。
    :param event_sequence: 已成功展示的 terminal event sequence。
    :returns: 更新后的 cursor record。
    :raises CliTerminalCursorError: JSON 腐坏、字段非法或写入失败时抛出。
    """

    return await asyncio.to_thread(
        _advance_cli_terminal_cursor_sync,
        workspace_root=workspace_root,
        session_id=session_id,
        terminal_event_id=terminal_event_id,
        event_sequence=event_sequence,
    )


def _read_cli_terminal_cursor_sync(
    *,
    workspace_root: Path,
    session_id: str,
) -> CliTerminalCursorRecord:
    """同步读取指定 Session cursor。

    :param workspace_root: workspace 根目录。
    :param session_id: Host Session id。
    :returns: 该 Session 的 cursor record。
    :raises CliTerminalCursorError: JSON 腐坏或字段非法时抛出。
    """

    _require_non_empty(session_id, field_name="session_id")
    store_path = cli_terminal_cursor_file_path(workspace_root)
    if not store_path.exists():
        return empty_cli_terminal_cursor_record()
    with file_lock(_lock_path(store_path)):
        records = _read_store_json(store_path)
    return records.get(session_id, empty_cli_terminal_cursor_record())


def _advance_cli_terminal_cursor_sync(
    *,
    workspace_root: Path,
    session_id: str,
    terminal_event_id: str,
    event_sequence: int,
) -> CliTerminalCursorRecord:
    """同步前进指定 Session cursor 并原子写回。

    :param workspace_root: workspace 根目录。
    :param session_id: Host Session id。
    :param terminal_event_id: 已成功展示的 terminal event id。
    :param event_sequence: 已成功展示的 terminal event sequence。
    :returns: 更新后的 cursor record。
    :raises CliTerminalCursorError: JSON 腐坏、字段非法或写入失败时抛出。
    """

    _require_non_empty(session_id, field_name="session_id")
    _require_non_empty(terminal_event_id, field_name="terminal_event_id")
    _require_non_negative_int(event_sequence, field_name="event_sequence")
    store_path = cli_terminal_cursor_file_path(workspace_root)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(_lock_path(store_path)):
        records = _read_store_json(store_path) if store_path.exists() else {}
        current = records.get(session_id, empty_cli_terminal_cursor_record())
        updated = _advanced_record(
            current=current,
            terminal_event_id=terminal_event_id,
            event_sequence=event_sequence,
        )
        records[session_id] = updated
        _write_store_json(store_path=store_path, records=records)
    return updated


def _advanced_record(
    *,
    current: CliTerminalCursorRecord,
    terminal_event_id: str,
    event_sequence: int,
) -> CliTerminalCursorRecord:
    """构造只前进不回退的新 cursor record。

    :param current: 当前 cursor record。
    :param terminal_event_id: 已成功展示的 terminal event id。
    :param event_sequence: 已成功展示的 terminal event sequence。
    :returns: 更新后的 cursor record。
    :raises Exception: 不主动抛出异常。
    """

    next_sequence = max(current.terminal_cursor.event_sequence, event_sequence)
    seen_ids = [item for item in current.seen_terminal_event_ids if item != terminal_event_id]
    seen_ids.append(terminal_event_id)
    trimmed_seen_ids = seen_ids[-CLI_TERMINAL_CURSOR_SEEN_IDS_MAX_SIZE:]
    return CliTerminalCursorRecord(
        terminal_cursor=OutboxTerminalCursor(event_sequence=next_sequence),
        seen_terminal_event_ids=tuple(trimmed_seen_ids),
    )


def _read_store_json(store_path: Path) -> dict[str, CliTerminalCursorRecord]:
    """读取并校验 cursor store JSON。

    :param store_path: cursor JSON 文件路径。
    :returns: session id 到 cursor record 的映射。
    :raises CliTerminalCursorError: JSON 腐坏或字段非法时抛出。
    """

    try:
        with store_path.open("r", encoding="utf-8") as stream:
            raw = cast(JsonValue, json.load(stream))
    except json.JSONDecodeError as exc:
        raise CliTerminalCursorError("CLI terminal cursor JSON 已损坏") from exc
    except OSError as exc:
        raise CliTerminalCursorError("读取 CLI terminal cursor 文件失败") from exc
    if not isinstance(raw, Mapping):
        raise CliTerminalCursorError("CLI terminal cursor JSON 顶层必须是对象")
    records: dict[str, CliTerminalCursorRecord] = {}
    for session_id, record_value in raw.items():
        _require_non_empty(session_id, field_name="session_id")
        records[session_id] = _record_from_json(record_value)
    return records


def _record_from_json(value: JsonValue) -> CliTerminalCursorRecord:
    """把单条 JSON record 转为 typed cursor record。

    :param value: 单条 JSON record。
    :returns: typed cursor record。
    :raises CliTerminalCursorError: 字段非法时抛出。
    """

    if not isinstance(value, Mapping):
        raise CliTerminalCursorError("CLI terminal cursor record 必须是对象")
    sequence = value.get(_JSON_SESSION_SEQUENCE_FIELD)
    if type(sequence) is not int or sequence < 0:
        raise CliTerminalCursorError("CLI terminal cursor sequence 必须是非负整数")
    seen_ids = value.get(_JSON_SESSION_SEEN_IDS_FIELD)
    if not isinstance(seen_ids, list):
        raise CliTerminalCursorError("CLI terminal cursor seen ids 必须是数组")
    parsed_seen_ids: list[str] = []
    seen_set: set[str] = set()
    for item in seen_ids:
        if not isinstance(item, str) or item == "":
            raise CliTerminalCursorError("CLI terminal cursor seen id 必须是非空字符串")
        if item in seen_set:
            raise CliTerminalCursorError("CLI terminal cursor seen ids 不能重复")
        seen_set.add(item)
        parsed_seen_ids.append(item)
    return CliTerminalCursorRecord(
        terminal_cursor=OutboxTerminalCursor(event_sequence=sequence),
        seen_terminal_event_ids=tuple(parsed_seen_ids),
    )


def _write_store_json(
    *,
    store_path: Path,
    records: Mapping[str, CliTerminalCursorRecord],
) -> None:
    """原子写回 cursor store JSON。

    :param store_path: cursor JSON 文件路径。
    :param records: session id 到 cursor record 的映射。
    :returns: ``None``。
    :raises CliTerminalCursorError: 写入失败时抛出。
    """

    payload = _records_to_json(records)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=store_path.parent,
            prefix=_TEMP_FILE_PREFIX,
            delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            json.dump(payload, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
        os.replace(temp_path, store_path)
    except OSError as exc:
        raise CliTerminalCursorError("写入 CLI terminal cursor 文件失败") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _records_to_json(records: Mapping[str, CliTerminalCursorRecord]) -> dict[str, JsonValue]:
    """把 typed records 转为 JSON payload。

    :param records: session id 到 cursor record 的映射。
    :returns: 可序列化 JSON 对象。
    :raises Exception: 不主动抛出异常。
    """

    payload: dict[str, JsonValue] = {}
    for session_id, record in records.items():
        payload[session_id] = {
            _JSON_SESSION_SEQUENCE_FIELD: record.terminal_cursor.event_sequence,
            _JSON_SESSION_SEEN_IDS_FIELD: list(record.seen_terminal_event_ids),
        }
    return payload


def _lock_path(store_path: Path) -> Path:
    """返回 cursor store 对应的 lock file 路径。

    :param store_path: cursor JSON 文件路径。
    :returns: lock file 路径。
    :raises Exception: 不主动抛出异常。
    """

    return store_path.with_name(_CURSOR_LOCK_FILE_NAME)


def _require_non_empty(value: str, *, field_name: str) -> None:
    """校验字符串非空。

    :param value: 待校验字符串。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises CliTerminalCursorError: 值为空时抛出。
    """

    if value == "":
        raise CliTerminalCursorError(f"{field_name} 必须是非空字符串")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    """校验严格非负整数。

    :param value: 待校验整数。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises CliTerminalCursorError: 值不是非负整数时抛出。
    """

    if type(value) is not int or value < 0:
        raise CliTerminalCursorError(f"{field_name} 必须是非负整数")


__all__ = [
    "CLI_TERMINAL_CURSOR_SEEN_IDS_MAX_SIZE",
    "CliTerminalCursorError",
    "CliTerminalCursorRecord",
    "advance_cli_terminal_cursor",
    "cli_terminal_cursor_file_path",
    "empty_cli_terminal_cursor_record",
    "read_cli_terminal_cursor",
]
