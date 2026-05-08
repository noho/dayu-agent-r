"""Host P6 Run / Attempt minimal state stores.

本模块在 ``HostStorage`` 之上提供 Run / Attempt 最小持久状态的查询协议
与实现。写入入口必须经由 :class:`HostStorageTransaction`，写入与
EventLog append 共享同一事务。

P6 不实现 admission、owner lease、fencing、orphan recovery。
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from dayu.contracts import JsonValue
from dayu.engine import FinishReason, RunResumeHint
from dayu.host._host_storage_transaction import (
    HostStorage,
    HostStorageTransaction,
)
from dayu.host._internal_contracts import (
    AttemptRecord,
    AttemptState,
    ExtendedRunState,
    GlobalEventPosition,
    RunRecord,
)
from dayu.host.contracts import (
    RunCancelledResult,
    RunEventCursor,
    RunFailedResult,
    RunResult,
    RunSucceededResult,
    RunSuspendedResult,
)


@dataclass(slots=True)
class RunStateStore:
    """Run minimal state durable 查询/写入入口。

    :param storage: 共享 :class:`HostStorage`。
    """

    storage: HostStorage

    def get(self, run_id: str) -> RunRecord | None:
        """读取指定 run 的最小状态。

        :param run_id: Run id。
        :returns: :class:`RunRecord`；不存在为 ``None``。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        rows = self.storage.execute_read(
            """
            SELECT run_id, session_id, state, created_at, updated_at,
                terminal_sequence, terminal_event_position, result_payload
            FROM host_runs WHERE run_id = ?
            """,
            (run_id,),
        )
        if not rows:
            return None
        return _row_to_run_record(rows[0])

    def list_runs(self) -> tuple[RunRecord, ...]:
        """列出全部 run 最小状态，便于诊断。

        :returns: RunRecord 元组。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        rows = self.storage.execute_read(
            """
            SELECT run_id, session_id, state, created_at, updated_at,
                terminal_sequence, terminal_event_position, result_payload
            FROM host_runs ORDER BY created_at ASC
            """
        )
        return tuple(_row_to_run_record(row) for row in rows)

    def write_terminal_result(
        self,
        *,
        tx: HostStorageTransaction,
        run_id: str,
        result: RunResult,
    ) -> None:
        """在事务内写入 terminal RunResult snapshot。

        :param tx: 当前事务。
        :param run_id: Run id。
        :param result: 终态 RunResult。
        :returns: 无返回值。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        payload = json.dumps(_encode_run_result(result), ensure_ascii=False)
        tx.execute(
            "UPDATE host_runs SET result_payload = ? WHERE run_id = ?",
            (payload, run_id),
        )

    def get_terminal_result(self, run_id: str) -> RunResult | None:
        """读取 terminal RunResult snapshot。

        :param run_id: Run id。
        :returns: :class:`RunResult`；未写入返回 ``None``。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        :raises ValueError: payload 解码失败时抛出。
        """

        rows = self.storage.execute_read(
            "SELECT result_payload FROM host_runs WHERE run_id = ?",
            (run_id,),
        )
        if not rows:
            return None
        raw = rows[0][0]
        if raw is None:
            return None
        return _decode_run_result(json.loads(raw))


@dataclass(slots=True)
class AttemptStateStore:
    """Attempt minimal state durable 查询/写入入口。

    :param storage: 共享 :class:`HostStorage`。
    """

    storage: HostStorage

    def create(
        self,
        *,
        tx: HostStorageTransaction,
        attempt_id: str,
        run_id: str,
        attempt_index: int,
    ) -> AttemptRecord:
        """在事务内创建 attempt 最小记录。

        :param tx: 当前事务。
        :param attempt_id: 新 attempt id。
        :param run_id: Run id。
        :param attempt_index: 同一 run 内 attempt 序号。
        :returns: 新建的 :class:`AttemptRecord`。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        now = datetime.now(tz=timezone.utc)
        tx.execute(
            """
            INSERT INTO host_attempts (
                attempt_id, run_id, attempt_index, state, started_at,
                finished_at, terminal_event_position, failure_summary
            ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL)
            """,
            (
                attempt_id,
                run_id,
                attempt_index,
                AttemptState.CREATED.value,
                now.isoformat(),
            ),
        )
        return AttemptRecord(
            attempt_id=attempt_id,
            run_id=run_id,
            attempt_index=attempt_index,
            state=AttemptState.CREATED,
            started_at=now,
            finished_at=None,
            terminal_event_position=None,
            failure_summary=None,
        )

    def update_state(
        self,
        *,
        tx: HostStorageTransaction,
        attempt_id: str,
        state: AttemptState,
        terminal_event_position: GlobalEventPosition | None = None,
        failure_summary: str | None = None,
    ) -> None:
        """在事务内推进 attempt 状态。

        :param tx: 当前事务。
        :param attempt_id: attempt id。
        :param state: 新状态。
        :param terminal_event_position: terminal 事件全局位置；非 terminal 为
            ``None``。
        :param failure_summary: 失败摘要；非失败为 ``None``。
        :returns: 无返回值。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        is_terminal = state in {
            AttemptState.SUCCEEDED,
            AttemptState.FAILED,
            AttemptState.CANCELLED,
            AttemptState.SUSPENDED,
            AttemptState.STALE_DIAGNOSTIC,
        }
        finished_at_iso = (
            datetime.now(tz=timezone.utc).isoformat() if is_terminal else None
        )
        tx.execute(
            """
            UPDATE host_attempts SET state = ?, finished_at = ?,
                terminal_event_position = ?, failure_summary = ?
            WHERE attempt_id = ?
            """,
            (
                state.value,
                finished_at_iso,
                None if terminal_event_position is None
                else terminal_event_position.value,
                failure_summary,
                attempt_id,
            ),
        )

    def get(self, attempt_id: str) -> AttemptRecord | None:
        """读取 attempt 最小记录。

        :param attempt_id: attempt id。
        :returns: :class:`AttemptRecord`；不存在为 ``None``。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        rows = self.storage.execute_read(
            """
            SELECT attempt_id, run_id, attempt_index, state, started_at,
                finished_at, terminal_event_position, failure_summary
            FROM host_attempts WHERE attempt_id = ?
            """,
            (attempt_id,),
        )
        if not rows:
            return None
        return _row_to_attempt_record(rows[0])

    def list_for_run(self, run_id: str) -> tuple[AttemptRecord, ...]:
        """列出某个 run 下全部 attempt。

        :param run_id: Run id。
        :returns: AttemptRecord 元组。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        rows = self.storage.execute_read(
            """
            SELECT attempt_id, run_id, attempt_index, state, started_at,
                finished_at, terminal_event_position, failure_summary
            FROM host_attempts WHERE run_id = ?
            ORDER BY attempt_index ASC
            """,
            (run_id,),
        )
        return tuple(_row_to_attempt_record(row) for row in rows)


def _row_to_run_record(row: sqlite3.Row) -> RunRecord:
    """SQLite 行转换为 :class:`RunRecord`。

    :param row: sqlite3.Row 对象。
    :returns: RunRecord。
    :raises ValueError: state 非法时抛出。
    """

    return RunRecord(
        run_id=row["run_id"],  # type: ignore[index]
        session_id=row["session_id"],  # type: ignore[index]
        state=ExtendedRunState(row["state"]),  # type: ignore[index]
        created_at=datetime.fromisoformat(row["created_at"]),  # type: ignore[index]
        updated_at=datetime.fromisoformat(row["updated_at"]),  # type: ignore[index]
        terminal_event_cursor=(
            None if row["terminal_sequence"] is None  # type: ignore[index]
            else RunEventCursor(sequence=int(row["terminal_sequence"]))  # type: ignore[index]
        ),
        terminal_event_position=(
            None if row["terminal_event_position"] is None  # type: ignore[index]
            else GlobalEventPosition(value=int(row["terminal_event_position"]))  # type: ignore[index]
        ),
        result=(
            None if row["result_payload"] is None  # type: ignore[index]
            else _decode_run_result(json.loads(row["result_payload"]))  # type: ignore[index]
        ),
    )


def _row_to_attempt_record(row: sqlite3.Row) -> AttemptRecord:
    """SQLite 行转换为 :class:`AttemptRecord`。

    :param row: sqlite3.Row。
    :returns: AttemptRecord。
    :raises ValueError: state 非法时抛出。
    """

    return AttemptRecord(
        attempt_id=row["attempt_id"],  # type: ignore[index]
        run_id=row["run_id"],  # type: ignore[index]
        attempt_index=int(row["attempt_index"]),  # type: ignore[index]
        state=AttemptState(row["state"]),  # type: ignore[index]
        started_at=datetime.fromisoformat(row["started_at"]),  # type: ignore[index]
        finished_at=(
            None if row["finished_at"] is None  # type: ignore[index]
            else datetime.fromisoformat(row["finished_at"])  # type: ignore[index]
        ),
        terminal_event_position=(
            None if row["terminal_event_position"] is None  # type: ignore[index]
            else GlobalEventPosition(value=int(row["terminal_event_position"]))  # type: ignore[index]
        ),
        failure_summary=row["failure_summary"],  # type: ignore[index]
    )


_SUCCESS_KIND: str = "succeeded"
_FAILED_KIND: str = "failed"
_CANCELLED_KIND: str = "cancelled"
_SUSPENDED_KIND: str = "suspended"


def _encode_run_result(result: RunResult) -> dict[str, JsonValue]:
    """将 RunResult 编码为 JSON 字典。

    :param result: terminal RunResult。
    :returns: JSON 字典。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(result, RunSucceededResult):
        return {
            "kind": _SUCCESS_KIND,
            "run_id": result.run_id,
            "session_id": result.session_id,
            "content": result.content,
            "filtered": result.filtered,
            "degraded": result.degraded,
            "finish_reason": result.finish_reason.value,
            "terminal_sequence": result.terminal_event_cursor.sequence,
        }
    if isinstance(result, RunFailedResult):
        return {
            "kind": _FAILED_KIND,
            "run_id": result.run_id,
            "session_id": result.session_id,
            "error_code": result.error_code,
            "message": result.message,
            "recoverable": result.recoverable,
            "terminal_sequence": result.terminal_event_cursor.sequence,
        }
    if isinstance(result, RunCancelledResult):
        return {
            "kind": _CANCELLED_KIND,
            "run_id": result.run_id,
            "session_id": result.session_id,
            "reason": result.reason,
            "terminal_sequence": result.terminal_event_cursor.sequence,
        }
    return {
        "kind": _SUSPENDED_KIND,
        "run_id": result.run_id,
        "session_id": result.session_id,
        "reason": result.reason,
        "resume_hint": (
            None if result.resume_hint is None else result.resume_hint.message
        ),
        "terminal_sequence": result.terminal_event_cursor.sequence,
    }


def _decode_run_result(payload: JsonValue) -> RunResult:
    """将 JSON 字典还原为 RunResult。

    :param payload: JSON 字典。
    :returns: RunResult。
    :raises ValueError: 字段非法或 kind 未知时抛出。
    """

    if not isinstance(payload, dict):
        raise ValueError("invalid run_result payload")
    kind = payload.get("kind")
    sequence_raw = payload.get("terminal_sequence")
    if not isinstance(sequence_raw, int) or isinstance(sequence_raw, bool):
        raise ValueError("invalid terminal_sequence")
    cursor = RunEventCursor(sequence=sequence_raw)
    if kind == _SUCCESS_KIND:
        return RunSucceededResult(
            run_id=_must_str(payload.get("run_id")),
            session_id=_must_str(payload.get("session_id")),
            content=_must_str(payload.get("content")),
            filtered=_must_bool(payload.get("filtered")),
            degraded=_must_bool(payload.get("degraded")),
            finish_reason=FinishReason(_must_str(payload.get("finish_reason"))),
            terminal_event_cursor=cursor,
        )
    if kind == _FAILED_KIND:
        return RunFailedResult(
            run_id=_must_str(payload.get("run_id")),
            session_id=_must_str(payload.get("session_id")),
            error_code=_must_str(payload.get("error_code")),
            message=_must_str(payload.get("message")),
            recoverable=_must_bool(payload.get("recoverable")),
            terminal_event_cursor=cursor,
        )
    if kind == _CANCELLED_KIND:
        return RunCancelledResult(
            run_id=_must_str(payload.get("run_id")),
            session_id=_must_str(payload.get("session_id")),
            reason=_must_str(payload.get("reason")),
            terminal_event_cursor=cursor,
        )
    if kind == _SUSPENDED_KIND:
        hint_raw = payload.get("resume_hint")
        return RunSuspendedResult(
            run_id=_must_str(payload.get("run_id")),
            session_id=_must_str(payload.get("session_id")),
            reason=_must_str(payload.get("reason")),
            resume_hint=(
                None if hint_raw is None
                else RunResumeHint(message=_must_str(hint_raw))
            ),
            terminal_event_cursor=cursor,
        )
    raise ValueError(f"unknown run_result kind: {kind}")


def _must_str(value: JsonValue | None) -> str:
    """强制 value 为字符串。

    :param value: 任意值。
    :returns: 字符串。
    :raises ValueError: 类型不符。
    """

    if not isinstance(value, str):
        raise ValueError("expected str")
    return value


def _must_bool(value: JsonValue | None) -> bool:
    """强制 value 为布尔。

    :param value: 任意值。
    :returns: 布尔。
    :raises ValueError: 类型不符。
    """

    if not isinstance(value, bool):
        raise ValueError("expected bool")
    return value


__all__ = [
    "AttemptStateStore",
    "RunStateStore",
]
