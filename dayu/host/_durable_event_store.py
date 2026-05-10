"""Host P6 durable RunEventStore.

本模块在 ``HostStorage`` 之上实现 :class:`RunEventStore` 协议的 durable
版本。它在单一 SQLite 事务中完成 per-run cursor 分配、internal global
event position 分配、event row 写入、terminal guard、必要的 Run /
Attempt minimal state 推进，并在 commit 之后才通知本进程订阅者。

设计要点：

- 每次 ``append`` 自己开一个 ``BEGIN IMMEDIATE`` 事务；不依赖外层组合多个
  store commit。
- 事件 payload 通过 ``_run_event_serializer`` 强类型 round-trip。
- 多进程并发由 SQLite 唯一约束兜底：``(run_id, sequence)`` 与
  ``event_position`` 全局唯一。
- 同一 run 不允许在 terminal 之后继续 append。
- ``subscribe`` 复用 condition 通知机制，commit 后由 post-commit hook
  ``notify_all``。
- ``InMemoryRunEventStore`` 仍保留作小单元测试便利实现，不参与 P6 default
  装配。
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from dayu.host._host_storage_transaction import (
    HostStorage,
    HostStorageTransaction,
)
from dayu.host._internal_contracts import (
    ExtendedRunState,
    GlobalEventPosition,
)
from dayu.host._run_event_serializer import (
    deserialize_run_event_data,
    serialize_run_event_data,
)
from dayu.host.contracts import (
    TERMINAL_RUN_EVENT_TYPES,
    RunEvent,
    RunEventCursor,
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
)
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_FIRST_EVENT_SEQUENCE: int = 0
_ERROR_ENGINE_EVENT_ID_REQUIRED: str = (
    "engine sourced RunEventDraft requires source_engine_event_id"
)
_ERROR_HOST_EVENT_ID_FORBIDDEN: str = (
    "host sourced RunEventDraft must not set source_engine_event_id"
)
_ERROR_APPEND_AFTER_TERMINAL: str = (
    "cannot append RunEventDraft after terminal event"
)
_ERROR_DUPLICATE_ENGINE_EVENT_ID: str = (
    "duplicate source_engine_event_id for run"
)
_LOGGER: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AppendedRunEvent:
    """事务内 append 后的 RunEvent 与 internal global position。

    本类型只供 Host internal 同事务原子写入路径(P8-S4 terminal append +
    attempt close)使用; 公开的 :meth:`DurableRunEventStore.append` /
    :meth:`append_in_transaction` 不返回 ``GlobalEventPosition``,
    避免全局位置语义经由 public 接口溢出到 ``RunEventCursor``。

    :param event: 已落库的 :class:`RunEvent`。
    :param event_position: 内部全局位置, 仅 Host internal 使用。
    """

    event: RunEvent
    event_position: GlobalEventPosition


_SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS host_run_events (
        event_position INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        kind TEXT NOT NULL,
        source TEXT NOT NULL,
        type TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        payload TEXT NOT NULL,
        source_engine_event_id TEXT,
        terminal INTEGER NOT NULL,
        UNIQUE (run_id, sequence)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_host_run_events_run
    ON host_run_events (run_id, sequence)
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_host_run_events_engine_id
    ON host_run_events (run_id, source_engine_event_id)
    WHERE source_engine_event_id IS NOT NULL
    """,
    """
    CREATE TABLE IF NOT EXISTS host_runs (
        run_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        state TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        terminal_sequence INTEGER,
        terminal_event_position INTEGER,
        result_payload TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS host_fencing_tokens (
        fencing_token INTEGER PRIMARY KEY AUTOINCREMENT,
        resource_type TEXT NOT NULL,
        resource_id TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        issued_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_host_fencing_tokens_resource
    ON host_fencing_tokens (resource_type, resource_id, fencing_token)
    """,
    """
    CREATE TABLE IF NOT EXISTS host_attempts (
        attempt_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        attempt_index INTEGER NOT NULL,
        state TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        terminal_event_position INTEGER,
        failure_summary TEXT,
        owner_id TEXT,
        owner_token_hash TEXT,
        fencing_token INTEGER,
        lease_expires_at TEXT,
        lease_renewed_at TEXT,
        recovered_from_attempt_id TEXT,
        stale_marked_at TEXT,
        UNIQUE (run_id, attempt_index)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_host_attempts_run_state
    ON host_attempts (run_id, state)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_host_attempts_lease
    ON host_attempts (state, lease_expires_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_host_attempts_recovered_from
    ON host_attempts (recovered_from_attempt_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS host_projection_checkpoints (
        observer_id TEXT NOT NULL,
        projection_name TEXT NOT NULL,
        schema_version INTEGER NOT NULL,
        last_success_position INTEGER,
        last_attempted_position INTEGER,
        status TEXT NOT NULL,
        retry_count INTEGER NOT NULL,
        last_error_code TEXT,
        last_error_message TEXT,
        last_success_at TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (observer_id, projection_name, schema_version)
    )
    """,
)


def ensure_host_schema(storage: HostStorage) -> None:
    """在指定 storage 上初始化 P6 schema。

    schema 设计采用 ``CREATE TABLE IF NOT EXISTS``；但 schema 升级时按 P6
    plan 必须按全新起库处理，禁止旧库兼容读取。

    :param storage: HostStorage 实例。
    :returns: 无返回值。
    :raises sqlite3.DatabaseError: schema bootstrap 失败时抛出。
    """

    storage.apply_schema(_SCHEMA_STATEMENTS)


@dataclass(slots=True)
class DurableRunEventStore:
    """SQLite 后端的 durable :class:`RunEventStore` 实现。

    :param storage: 共享 :class:`HostStorage`。
    """

    storage: HostStorage
    _condition: asyncio.Condition = field(
        default_factory=asyncio.Condition,
        init=False,
    )

    def __post_init__(self) -> None:
        """在创建时确保 schema 已就绪。

        :returns: 无返回值。
        :raises sqlite3.DatabaseError: schema bootstrap 失败时抛出。
        """

        ensure_host_schema(self.storage)

    async def append(self, draft: RunEventDraft) -> RunEvent:
        """在单一事务内 append RunEvent 草稿。

        terminal 事件由 :class:`DurableRunEventStore` 自身根据 event 类型
        与 data 推导 :class:`RunResult` 并在同一事务内写入
        ``host_runs.result_payload``，调用方无需额外触发 result snapshot
        持久化。

        :param draft: 待追加的 RunEvent 草稿。
        :returns: 已落库的 RunEvent。
        :raises ValueError: draft 来源不一致、重复 ``source_engine_event_id``
            或 run 已终态时抛出。
        :raises sqlite3.DatabaseError: SQLite 写入失败时抛出。
        """

        _validate_draft_provenance(draft)
        try:
            async with self.storage.transaction() as tx:
                appended = self._append_in_transaction(tx=tx, draft=draft)
                tx.add_post_commit_hook(self._make_notify_hook())
        except sqlite3.IntegrityError as exc:
            _raise_business_error_for_integrity(exc=exc, draft=draft)
            raise
        event = appended.event
        if _should_log_append(event):
            _LOGGER.log(
                _append_log_level(event),
                "host.event_store.appended run_id=%s cursor=%s "
                "position=%s type=%s kind=%s source=%s terminal=%s",
                event.run_id,
                event.cursor.sequence,
                appended.event_position.value,
                event.type.value,
                event.kind.value,
                event.source.value,
                event.type in TERMINAL_RUN_EVENT_TYPES,
            )
        return event

    def _append_in_transaction(
        self,
        *,
        tx: HostStorageTransaction,
        draft: RunEventDraft,
    ) -> AppendedRunEvent:
        """事务内执行 append；调用方负责事务上下文。

        :param tx: 当前 :class:`HostStorageTransaction`。
        :param draft: RunEvent 草稿。
        :returns: 已落库的 RunEvent 及 internal global position。
        :raises ValueError: run 已终态时抛出。
        """

        terminal_row = tx.execute(
            """
            SELECT terminal_sequence, terminal_event_position
            FROM host_runs WHERE run_id = ?
            """,
            (draft.run_id,),
        ).fetchone()
        if terminal_row is not None and terminal_row[0] is not None:
            raise ValueError(_ERROR_APPEND_AFTER_TERMINAL)

        next_sequence_row = tx.execute(
            "SELECT COALESCE(MAX(sequence) + 1, ?) FROM host_run_events "
            "WHERE run_id = ?",
            (_FIRST_EVENT_SEQUENCE, draft.run_id),
        ).fetchone()
        sequence: int = (
            int(next_sequence_row[0]) if next_sequence_row is not None
            else _FIRST_EVENT_SEQUENCE
        )

        payload = serialize_run_event_data(
            event_type=draft.type, data=draft.data
        )
        is_terminal = draft.type in TERMINAL_RUN_EVENT_TYPES
        cursor = tx.execute(
            """
            INSERT INTO host_run_events (
                run_id, session_id, sequence, kind, source, type,
                occurred_at, payload, source_engine_event_id, terminal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft.run_id,
                draft.session_id,
                sequence,
                draft.kind.value,
                draft.source.value,
                draft.type.value,
                draft.occurred_at.isoformat(),
                payload,
                draft.source_engine_event_id,
                1 if is_terminal else 0,
            ),
        )
        event_position = int(cursor.lastrowid or 0)

        self._upsert_run_state(
            tx=tx,
            draft=draft,
            sequence=sequence,
            event_position=event_position,
            is_terminal=is_terminal,
        )

        event = RunEvent(
            run_id=draft.run_id,
            session_id=draft.session_id,
            cursor=RunEventCursor(sequence=sequence),
            kind=draft.kind,
            source=draft.source,
            type=draft.type,
            occurred_at=draft.occurred_at,
            data=draft.data,
            source_engine_event_id=draft.source_engine_event_id,
        )
        if is_terminal:
            self._write_terminal_result_snapshot(tx=tx, event=event)
        return AppendedRunEvent(
            event=event,
            event_position=GlobalEventPosition(value=event_position),
        )

    def append_in_transaction(
        self,
        *,
        tx: HostStorageTransaction,
        draft: RunEventDraft,
    ) -> RunEvent:
        """在外层 :class:`HostStorageTransaction` 内追加 RunEvent。

        本方法是 :meth:`_append_in_transaction` 的 thin 公共包装，供 Host
        其它子系统在已有事务上下文内同事务追加 Host-owned canonical fact
        （例如 P7 ``RUN_INPUT_CONTEXT_SNAPSHOT_BUILT``）。

        :param tx: 当前 :class:`HostStorageTransaction`。
        :param draft: RunEvent 草稿。
        :returns: 已落库的 RunEvent。
        :raises ValueError: run 已终态时抛出。
        """

        appended = self._append_in_transaction(tx=tx, draft=draft)
        return appended.event

    def append_with_position_in_transaction(
        self,
        *,
        tx: HostStorageTransaction,
        draft: RunEventDraft,
    ) -> AppendedRunEvent:
        """事务内追加 RunEvent 并返回 internal global position。

        本方法仅供 Host internal 同事务原子写入路径(P8-S4 terminal
        append + attempt close)使用; 与 :meth:`append_in_transaction`
        的差别在于额外暴露 ``GlobalEventPosition``, 让 supervisor 在同
        事务内把 ``host_attempts.terminal_event_position`` 与新写入
        的 RunEvent 全局位置对齐。``GlobalEventPosition`` 不允许经由
        public 接口外溢, 因此公开签名仅返回 :class:`AppendedRunEvent`
        包装而非裸值。

        :param tx: 当前 :class:`HostStorageTransaction`。
        :param draft: RunEvent 草稿。
        :returns: ``AppendedRunEvent`` 含已落库 RunEvent 与全局位置。
        :raises ValueError: run 已终态、来源不一致或 engine event id 重复。
        """

        _validate_draft_provenance(draft)
        appended = self._append_in_transaction(tx=tx, draft=draft)
        # supervisor 在同事务内 append terminal RunEvent + close attempt,
        # 之后不会再有任何 notify-hooked append 推进 ``_condition``;
        # 必须在 commit 后唤醒订阅者, 否则 RunStream subscribe 永远 wait,
        # 上层无法收到 terminal event。注: ``add_post_commit_hook`` 幂等地
        # 追加 hook, 多次 register 也只会在 commit 后多触发一次 ``notify_all``,
        # 不影响正确性。
        tx.add_post_commit_hook(self._make_notify_hook())
        return appended

    def _upsert_run_state(
        self,
        *,
        tx: HostStorageTransaction,
        draft: RunEventDraft,
        sequence: int,
        event_position: int,
        is_terminal: bool,
    ) -> None:
        """根据当前 append 推进 Run minimal state。

        - 第一次 append：创建 run 行，state = RUNNING。
        - terminal append：写入 terminal sequence / position 并将 state 切到
          对应 terminal state。

        :param tx: 当前事务。
        :param draft: RunEvent 草稿。
        :param sequence: 当前事件 cursor sequence。
        :param event_position: 当前事件全局 position。
        :param is_terminal: 是否 terminal 事件。
        :returns: 无返回值。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        now_iso = datetime.now(tz=timezone.utc).isoformat()
        existing = tx.execute(
            "SELECT 1 FROM host_runs WHERE run_id = ?", (draft.run_id,)
        ).fetchone()
        if existing is None:
            tx.execute(
                """
                INSERT INTO host_runs (
                    run_id, session_id, state, created_at, updated_at,
                    terminal_sequence, terminal_event_position, result_payload
                ) VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL)
                """,
                (
                    draft.run_id,
                    draft.session_id,
                    ExtendedRunState.RUNNING.value,
                    now_iso,
                    now_iso,
                ),
            )
        if is_terminal:
            terminal_state = _terminal_state_for_event_type(draft.type)
            tx.execute(
                """
                UPDATE host_runs SET state = ?, updated_at = ?,
                    terminal_sequence = ?, terminal_event_position = ?
                WHERE run_id = ?
                """,
                (
                    terminal_state.value,
                    now_iso,
                    sequence,
                    event_position,
                    draft.run_id,
                ),
            )
        else:
            tx.execute(
                "UPDATE host_runs SET updated_at = ? WHERE run_id = ?",
                (now_iso, draft.run_id),
            )

    def _write_terminal_result_snapshot(
        self,
        *,
        tx: HostStorageTransaction,
        event: RunEvent,
    ) -> None:
        """在 terminal append 同事务写入 RunResult snapshot。

        通过 ``terminal_result_from_event`` 推导终态结果，再用
        :class:`RunStateStore` 写入 ``host_runs.result_payload``。这是 P6
        Finding 3 的修复：终态事件、Run state、result snapshot 在同一事务
        内提交，要么全成功要么全回滚。

        :param tx: 当前事务。
        :param event: 已构造的 terminal RunEvent。
        :returns: 无返回值。
        :raises TypeError: 终态事件类型与 data 类型不一致时抛出。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        # lazy import 避免 _run_state_store ↔ _durable_event_store 循环依赖。
        from dayu.host._event_translation import terminal_result_from_event
        from dayu.host._run_state_store import RunStateStore

        result = terminal_result_from_event(event)
        if result is None:
            return
        store = RunStateStore(storage=self.storage)
        store.write_terminal_result(
            tx=tx,
            run_id=event.run_id,
            result=result,
        )

    async def list_events(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> tuple[RunEvent, ...]:
        """按 exclusive cursor 补读某个 run 的事件。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor；为 ``None`` 时返回全部事件。
        :returns: cursor 大于 ``after`` 的 RunEvent 元组。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        rows = await asyncio.to_thread(
            self._fetch_events_after,
            run_id,
            -1 if after is None else after.sequence,
        )
        return tuple(_row_to_run_event(row) for row in rows)

    def subscribe(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> AsyncIterator[RunEvent]:
        """订阅某个 run 的 replay-then-follow 事件流。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor；为 ``None`` 时从头订阅。
        :returns: RunEvent 异步流。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        return self._subscribe(run_id=run_id, after=after)

    async def _subscribe(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> AsyncGenerator[RunEvent, None]:
        """先 replay 再 follow，commit 后由 condition 唤醒。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor。
        :returns: RunEvent 异步流。
        """

        last_seen_sequence = -1 if after is None else after.sequence
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.event_store.subscribe_start run_id=%s after=%s",
            run_id,
            None if after is None else after.sequence,
        )
        while True:
            async with self._condition:
                while True:
                    rows = await asyncio.to_thread(
                        self._fetch_events_after, run_id, last_seen_sequence
                    )
                    if rows:
                        break
                    if await asyncio.to_thread(
                        self._terminal_reached, run_id, last_seen_sequence
                    ):
                        _LOGGER.log(
                            VERBOSE_LOG_LEVEL,
                            "host.event_store.subscribe_complete run_id=%s "
                            "after=%s reason=terminal_seen",
                            run_id,
                            last_seen_sequence,
                        )
                        return
                    await self._condition.wait()
                last_seen_sequence = int(rows[-1]["sequence"])
            for row in rows:
                event = _row_to_run_event(row)
                yield event
                if event.type in TERMINAL_RUN_EVENT_TYPES:
                    _LOGGER.log(
                        VERBOSE_LOG_LEVEL,
                        "host.event_store.subscribe_complete run_id=%s "
                        "after=%s reason=terminal_yielded",
                        run_id,
                        event.cursor.sequence,
                    )
                    return

    def _fetch_events_after(
        self,
        run_id: str,
        sequence_exclusive: int,
    ) -> list[sqlite3.Row]:
        """读取指定 cursor 之后的事件行。

        :param run_id: Run id。
        :param sequence_exclusive: exclusive 起点序号；``-1`` 表示从头。
        :returns: SQLite Row 列表（含 sequence、event_position 等列）。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        rows = self.storage.execute_read(
            """
            SELECT run_id, session_id, sequence, event_position, kind,
                source, type, occurred_at, payload, source_engine_event_id
            FROM host_run_events
            WHERE run_id = ? AND sequence > ?
            ORDER BY sequence ASC
            """,
            (run_id, sequence_exclusive),
        )
        return rows

    def _terminal_reached(
        self,
        run_id: str,
        sequence_exclusive: int,
    ) -> bool:
        """判断订阅起点是否已越过 terminal cursor。

        :param run_id: Run id。
        :param sequence_exclusive: exclusive 起点序号。
        :returns: 已越过返回 ``True``。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        rows = self.storage.execute_read(
            "SELECT terminal_sequence FROM host_runs WHERE run_id = ?",
            (run_id,),
        )
        if not rows:
            return False
        terminal_sequence = rows[0][0]
        if terminal_sequence is None:
            return False
        return sequence_exclusive >= int(terminal_sequence)

    def latest_event_position(self) -> GlobalEventPosition | None:
        """读取当前最大 global event position。

        :returns: 最近写入位置；空库时返回 ``None``。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        rows = self.storage.execute_read(
            "SELECT MAX(event_position) FROM host_run_events"
        )
        if not rows or rows[0][0] is None:
            return None
        return GlobalEventPosition(value=int(rows[0][0]))

    def fetch_events_by_position(
        self,
        *,
        after: GlobalEventPosition | None,
        limit: int,
    ) -> tuple[tuple[GlobalEventPosition, RunEvent], ...]:
        """按全局 position 顺序读取一批事件。

        observer / projection 跨 run 消费时使用。

        :param after: exclusive 起点 position；``None`` 表示从头。
        :param limit: 最大返回条数，必须为正。
        :returns: ``(position, event)`` 二元组元组。
        :raises ValueError: ``limit`` 非正时抛出。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        if limit <= 0:
            raise ValueError("limit must be positive")
        threshold = -1 if after is None else after.value
        rows = self.storage.execute_read(
            """
            SELECT run_id, session_id, sequence, event_position, kind,
                source, type, occurred_at, payload, source_engine_event_id
            FROM host_run_events
            WHERE event_position > ?
            ORDER BY event_position ASC
            LIMIT ?
            """,
            (threshold, limit),
        )
        result: list[tuple[GlobalEventPosition, RunEvent]] = []
        for row in rows:
            event = _row_to_run_event(row)
            position = GlobalEventPosition(value=int(row["event_position"]))
            result.append((position, event))
        return tuple(result)

    def fetch_canonical_events_for_run_in_transaction(
        self,
        *,
        tx: HostStorageTransaction,
        session_id: str,
        run_id: str,
    ) -> tuple[RunEvent, ...]:
        """在调用方事务内按 run 读取全部 canonical RunEvent。

        durable read model 在 terminal 投影时使用本 Host internal API 从
        EventLog 真源重建同一 run 的完整 canonical facts，避免依赖进程内
        pending 状态跨 checkpoint / restart 保存事实。

        :param tx: 当前 Host storage 事务。
        :param session_id: 会话 id，用于限定同一 session 边界。
        :param run_id: Run id。
        :returns: 该 run 的 canonical RunEvent 元组，按 global position 升序。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        cursor = tx.execute(
            """
            SELECT run_id, session_id, sequence, event_position, kind,
                source, type, occurred_at, payload, source_engine_event_id
            FROM host_run_events
            WHERE session_id = ? AND run_id = ? AND kind = ?
            ORDER BY event_position ASC
            """,
            (session_id, run_id, RunEventKind.CANONICAL.value),
        )
        rows = cursor.fetchall()
        cursor.close()
        return tuple(_row_to_run_event(row) for row in rows)

    def _make_notify_hook(self) -> "Callable[[], None]":
        """构造一个 commit 后通知订阅者的 hook。

        :returns: 无参回调。
        :raises Exception: 不主动抛出异常。
        """

        condition = self._condition

        def _notify() -> None:
            """commit 后唤醒所有订阅者。

            :returns: 无返回值。
            :raises Exception: 不主动抛出异常。
            """

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            loop.create_task(_notify_condition(condition))

        return _notify


async def _notify_condition(condition: asyncio.Condition) -> None:
    """获取 condition 锁后 ``notify_all``。

    :param condition: 订阅者使用的 :class:`asyncio.Condition`。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    async with condition:
        condition.notify_all()


def _row_to_run_event(row: sqlite3.Row) -> RunEvent:
    """SQLite 行转换为 :class:`RunEvent`。

    :param row: sqlite3.Row 对象。
    :returns: RunEvent。
    :raises ValueError: payload 解码失败时抛出。
    """

    event_type = RunEventType(row["type"])
    data = deserialize_run_event_data(
        event_type=event_type, raw=row["payload"]
    )
    return RunEvent(
        run_id=row["run_id"],
        session_id=row["session_id"],
        cursor=RunEventCursor(sequence=int(row["sequence"])),
        kind=RunEventKind(row["kind"]),
        source=RunEventSource(row["source"]),
        type=event_type,
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
        data=data,
        source_engine_event_id=row["source_engine_event_id"],
    )


def _validate_draft_provenance(draft: RunEventDraft) -> None:
    """校验 RunEventDraft 的来源字段。

    :param draft: 待 append 的 RunEvent 草稿。
    :returns: 无返回值。
    :raises ValueError: 来源与 ``source_engine_event_id`` 不一致时抛出。
    """

    if (
        draft.source is RunEventSource.ENGINE
        and draft.source_engine_event_id is None
    ):
        raise ValueError(_ERROR_ENGINE_EVENT_ID_REQUIRED)
    if (
        draft.source is RunEventSource.HOST
        and draft.source_engine_event_id is not None
    ):
        raise ValueError(_ERROR_HOST_EVENT_ID_FORBIDDEN)


def _raise_business_error_for_integrity(
    *,
    exc: sqlite3.IntegrityError,
    draft: RunEventDraft,
) -> None:
    """把 SQLite ``IntegrityError`` 映射为业务错误。

    重复 ``source_engine_event_id`` 是 Engine 重复发同源事件或 Host 翻译
    重复 append 的业务事实，调用方应能捕获 ``ValueError`` 并跳过；其余
    integrity 违例（``UNIQUE (run_id, sequence)`` 等）属于框架内部不变量
    破坏，原样透传不吞。

    :param exc: 原始 IntegrityError。
    :param draft: 触发错误的 RunEventDraft。
    :returns: 无返回值。
    :raises ValueError: 映射为业务错误时抛出。
    """

    message = str(exc)
    if (
        "idx_host_run_events_engine_id" in message
        or "source_engine_event_id" in message
    ):
        raise ValueError(
            f"{_ERROR_DUPLICATE_ENGINE_EVENT_ID}: run_id={draft.run_id} "
            f"engine_event_id={draft.source_engine_event_id}"
        ) from exc



def _terminal_state_for_event_type(
    event_type: RunEventType,
) -> ExtendedRunState:
    """将 terminal RunEventType 映射到 ExtendedRunState。

    :param event_type: 事件类型，必须在 :data:`TERMINAL_RUN_EVENT_TYPES` 中。
    :returns: 对应 terminal state。
    :raises ValueError: 类型不是 terminal 时抛出。
    """

    match event_type:
        case RunEventType.FINAL_ANSWER:
            return ExtendedRunState.SUCCEEDED
        case RunEventType.RUN_FAILED:
            return ExtendedRunState.FAILED
        case RunEventType.RUN_CANCELLED:
            return ExtendedRunState.CANCELLED
        case RunEventType.RUN_SUSPENDED:
            return ExtendedRunState.SUSPENDED
        case _:
            raise ValueError(
                f"non-terminal event type for terminal state: "
                f"{event_type.value}"
            )


def _should_log_append(event: RunEvent) -> bool:
    """判断 append 事件是否进入诊断日志。

    :param event: 已 append 的 RunEvent。
    :returns: 应记录返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return (
        event.kind is RunEventKind.CANONICAL
        or event.type in TERMINAL_RUN_EVENT_TYPES
    )


def _append_log_level(event: RunEvent) -> int:
    """返回 append 诊断日志级别。

    :param event: 已 append 的 RunEvent。
    :returns: stdlib logging 级别整数。
    :raises Exception: 不主动抛出异常。
    """

    if event.type in TERMINAL_RUN_EVENT_TYPES:
        return VERBOSE_LOG_LEVEL
    return logging.DEBUG


__all__ = [
    "AppendedRunEvent",
    "DurableRunEventStore",
    "ensure_host_schema",
]


# row_factory 已由 :meth:`HostStorage.open` 内部统一配置，外部模块不再持有
# raw connection；本入口只负责确保 schema 已就绪。
def open_durable_event_store(storage: HostStorage) -> DurableRunEventStore:
    """打开并初始化 durable event store。

    :param storage: 已构造的 :class:`HostStorage`。
    :returns: 初始化完成的 :class:`DurableRunEventStore`。
    :raises sqlite3.DatabaseError: schema bootstrap 失败时抛出。
    """

    storage.open()
    return DurableRunEventStore(storage=storage)
