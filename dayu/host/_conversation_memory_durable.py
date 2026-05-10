"""Host P8-S8 Durable Conversation Memory Store。

本模块实现 :class:`ConversationMemoryStore` 协议的 durable 版本。它把
session memory snapshot 持久化到 ``host_conversation_memory_snapshots``
表，关闭“projection checkpoint 已 caught up，但进程重启后 in-memory
memory 丢失，``startup_reconcile()`` 因 checkpoint 已推进而不再 replay
EventLog” 的恢复洞。

约束：

- EventLog 仍是事实真源；本模块只承载 read model snapshot 复用。
- snapshot 写入必须与 projection checkpoint 推进在 **同一**
  :class:`HostStorageTransaction` 内完成；本模块为 observer 提供
  ``project_run_events_in_transaction``，禁止 observer 在自己事务内嵌
  套开新事务。
- ``project_run_events`` 仅作为非 observer 路径的 convenience：自行开
  短事务后委托同事务版本。
- snapshot payload 通过结构化 JSON encode/decode 完成 round-trip，
  不存 owner token / scope token / cursor 原文 / 大 prompt / 大工具
  结果。
- 不实现 P9 lifecycle admission、不固定 public memory edit/reset/forget
  API、不迁移业务 long-term memory。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Protocol, TypeAlias

from dayu.contracts.json_value import JsonValue
from dayu.host._conversation_memory import (
    AssumptionRegister,
    ClaimCorrectionPatch,
    ClaimStatus,
    ConversationMemoryPatch,
    ConversationMemorySnapshot,
    ConversationPinnedState,
    ConversationRawTurn,
    ConversationToolFact,
    EvidenceAnchor,
    MemoryClaim,
    MemoryIngestionPolicy,
    MemoryProducerKind,
    MemoryProvenance,
    MemoryResetPatch,
    MemoryScope,
    MemoryTrustLevel,
    ScopeClearPatch,
    TaskFrame,
    UserPreferenceProfileRef,
    _project_canonical_events,
)
from dayu.host._durable_event_store import DurableRunEventStore
from dayu.host._host_storage_transaction import (
    HostStorage,
    HostStorageTransaction,
)
from dayu.host.contracts import (
    TERMINAL_RUN_EVENT_TYPES,
    RunEvent,
    RunEventCursor,
    RunEventKind,
    RunEventType,
)
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

# 与 P3 ``InMemoryConversationMemoryStore`` 默认值保持一致, 避免 read
# model 行为在替换默认装配时静默漂移。
DEFAULT_RECENT_TURN_LIMIT: int = 4
_LOGGER: logging.Logger = logging.getLogger(__name__)
_ERROR_SCOPE_CLEAR_UNSUPPORTED_SCOPE: str = "scope_clear_only_supports_session"
_ERROR_SNAPSHOT_DECODE: str = "host_conversation_memory_snapshot_decode_failed"
_ERROR_SNAPSHOT_ENCODE: str = "host_conversation_memory_snapshot_encode_failed"
_ERROR_SNAPSHOT_SCHEMA_VERSION: str = (
    "host_conversation_memory_snapshot_schema_version_mismatch"
)
_TABLE_NAME: str = "host_conversation_memory_snapshots"
# repair 路径分页拉取 EventLog 的 batch 大小，避免单次 SELECT 全量加载。
_REPAIR_FETCH_BATCH_LIMIT: int = 256

_JsonObject: TypeAlias = Mapping[str, JsonValue]

_SCHEMA_STATEMENTS: tuple[str, ...] = (
    f"""
    CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (
        session_id TEXT PRIMARY KEY,
        snapshot_payload TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
)


class UtcClock(Protocol):
    """durable memory 使用的 UTC clock 协议。

    该协议与 Host 其它 durable state store 的 clock 形状保持一致，使
    snapshot ``updated_at`` 可在测试中确定性断言。
    """

    def now(self) -> datetime:
        """返回当前 timezone-aware UTC 时间。

        :returns: timezone-aware UTC datetime。
        :raises Exception: 具体 clock 失败时透传。
        """
        ...


class _SystemUtcClock:
    """系统 UTC clock 默认实现。"""

    def now(self) -> datetime:
        """返回当前 timezone-aware UTC 时间。

        :returns: timezone-aware UTC datetime。
        :raises Exception: 不主动抛出异常。
        """

        return datetime.now(tz=timezone.utc)


def ensure_durable_memory_schema(storage: HostStorage) -> None:
    """初始化 durable conversation memory snapshot schema。

    :param storage: Host durable storage。
    :returns: 无返回值。
    :raises sqlite3.DatabaseError: schema bootstrap 失败时抛出。
    """

    storage.apply_schema(_SCHEMA_STATEMENTS)


@dataclass(slots=True)
class DurableConversationMemoryStore:
    """以 :class:`HostStorage` 为后端的 durable :class:`ConversationMemoryStore`。

    :param storage: Host durable storage。
    :param recent_turn_limit: recent raw turn 保留数量，与 P3 内存态语义一致。
    :param clock: Host internal UTC clock，用于 deterministic ``updated_at``。
    """

    storage: HostStorage
    recent_turn_limit: int = DEFAULT_RECENT_TURN_LIMIT
    clock: UtcClock = field(default_factory=_SystemUtcClock)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def project_run_events(self, events: tuple[RunEvent, ...]) -> None:
        """非 observer 路径的 convenience：自行开短事务后委托同事务版本。

        observer 路径必须使用
        :meth:`project_run_events_in_transaction`，避免在 observer 持有
        的事务内嵌套开新事务。

        :param events: 同一 run 的 RunEvent 元组。
        :returns: 无返回值。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        if not events:
            return
        async with self._lock:
            async with self.storage.transaction() as tx:
                self._project_in_tx(tx=tx, events=events)

    async def project_run_events_in_transaction(
        self,
        *,
        tx: HostStorageTransaction,
        events: tuple[RunEvent, ...],
    ) -> None:
        """observer 路径同事务投影。

        memory snapshot 写入必须与 projection checkpoint 推进在同一事务
        内完成；写入失败时事务整体回滚，checkpoint 不推进。

        :param tx: observer 当前 :class:`HostStorageTransaction`。
        :param events: 同一 run 的 RunEvent 元组。
        :returns: 无返回值。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        if not events:
            return
        # observer 已经持有事务, 不再获取 ``_lock`` 以免和 projection
        # coordinator 的串行化语义重复加锁; observer 进入是单线程串行。
        self._project_in_tx(tx=tx, events=events)

    async def get_snapshot(self, session_id: str) -> ConversationMemorySnapshot:
        """读取 session memory snapshot。

        :param session_id: 会话 id。
        :returns: snapshot；session 不存在时返回空 snapshot。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        :raises ValueError: 已落库 snapshot payload 解码失败时抛出。
        """

        rows = self.storage.execute_read(
            "SELECT snapshot_payload FROM "
            "host_conversation_memory_snapshots WHERE session_id = ?",
            (session_id,),
        )
        if not rows:
            return _empty_snapshot(session_id)
        payload_text = rows[0]["snapshot_payload"]
        if not isinstance(payload_text, str):
            raise ValueError(_ERROR_SNAPSHOT_DECODE)
        return _decode_snapshot_text(payload_text=payload_text)

    async def apply_patch(self, patch: ConversationMemoryPatch) -> None:
        """应用 internal-only memory patch 并持久化。

        与 P3 内存态语义一致：

        - :class:`MemoryResetPatch` / :class:`ScopeClearPatch`(SESSION)：
          清空对应 session snapshot。
        - :class:`ScopeClearPatch` 非 SESSION scope：抛 ``ValueError``。
        - :class:`ClaimCorrectionPatch`：把 corrected claim 追加进
          ``verified_claims``。

        :param patch: memory patch。
        :returns: 无返回值。
        :raises ValueError: ScopeClearPatch 使用非 SESSION scope 时抛出。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        async with self._lock:
            async with self.storage.transaction() as tx:
                match patch:
                    case MemoryResetPatch(session_id=session_id):
                        self._write_snapshot(
                            tx=tx, snapshot=_empty_snapshot(session_id)
                        )
                    case ScopeClearPatch(
                        session_id=session_id, scope=MemoryScope.SESSION
                    ):
                        self._write_snapshot(
                            tx=tx, snapshot=_empty_snapshot(session_id)
                        )
                    case ScopeClearPatch(scope=scope):
                        raise ValueError(
                            f"{_ERROR_SCOPE_CLEAR_UNSUPPORTED_SCOPE}: "
                            f"{scope.value}"
                        )
                    case ClaimCorrectionPatch(
                        session_id=session_id, corrected_claim=claim
                    ):
                        snapshot = self._read_snapshot_in_tx(
                            tx=tx, session_id=session_id
                        )
                        updated = replace(
                            snapshot,
                            verified_claims=snapshot.verified_claims
                            + (claim,),
                        )
                        self._write_snapshot(tx=tx, snapshot=updated)

    async def repair_missing_session_snapshots(
        self,
        *,
        event_store: DurableRunEventStore,
    ) -> tuple[str, ...]:
        """Host internal: 从 EventLog 重建“snapshot row 缺失”的 session memory。

        关闭 P8-S8 gap：``ProjectionCoordinator`` 的 checkpoint 已 CAUGHT_UP
        且 EventLog 无新事件时，普通 ``startup_reconcile()`` 不会再驱动
        observer 重投；若 ``host_conversation_memory_snapshots`` 因运维误
        操作或 read model 损坏而丢失某些 session row，旧 session memory 就
        无法被自动恢复。本方法显式扫描 EventLog 与 snapshot 表，按 session
        重投 canonical 事件以重建缺失 row。

        关键边界（与 intentional empty snapshot 区分）：

        - :class:`MemoryResetPatch` / :class:`ScopeClearPatch` (SESSION)
          通过 ``apply_patch`` 写入空 snapshot row（UPSERT）。该 row 仍存
          在，本方法 **不会** 把它当作“缺失”重建。
        - 仅当 EventLog 有 canonical 事件、但 snapshot 表无对应 row 时，
          才视为 read model 缺失并重建。

        :param event_store: durable EventLog，作为事实真源。
        :returns: 本次成功重建 snapshot 的 session_id 元组（按重建顺序）。
        :raises sqlite3.DatabaseError: 读取或写入失败时抛出。
        """

        async with self._lock:
            return await self._repair_missing_session_snapshots_locked(
                event_store=event_store
            )

    async def _repair_missing_session_snapshots_locked(
        self,
        *,
        event_store: DurableRunEventStore,
    ) -> tuple[str, ...]:
        """``_lock`` 持有下的 repair 实现。

        :param event_store: durable EventLog。
        :returns: 重建成功的 session_id 元组。
        :raises sqlite3.DatabaseError: 读取或写入失败时抛出。
        """

        missing_session_ids = self._collect_missing_session_ids()
        if not missing_session_ids:
            return ()
        repaired: list[str] = []
        for session_id in missing_session_ids:
            canonical_events = self._fetch_canonical_events_for_session(
                event_store=event_store, session_id=session_id
            )
            if not canonical_events:
                # EventLog 中确实没有 canonical 事件可用于重建；保持缺失
                # 状态，留给上层 lifecycle 决定是否新建 session。
                continue
            if not self._has_terminal_event(canonical_events):
                # 仅有 USER_INPUT_ACCEPTED 但无 terminal / canonical 工具
                # 事实，意味着 session 还在进行中 / 没有完整事实；本 helper
                # 不主动写入“半成品” snapshot，等待正常 projection 路径。
                continue
            async with self.storage.transaction() as tx:
                # 二次确认 row 仍缺失：避免与并发 observer 投影竞争导致
                # 覆盖刚写入的 snapshot。
                if self._snapshot_row_exists_in_tx(
                    tx=tx, session_id=session_id
                ):
                    continue
                self._project_in_tx(tx=tx, events=canonical_events)
            repaired.append(session_id)
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "host.conversation_memory.durable_repaired session_id=%s "
                "canonical_count=%s",
                session_id,
                len(canonical_events),
            )
        return tuple(repaired)

    def _collect_missing_session_ids(self) -> tuple[str, ...]:
        """扫描出 EventLog 中已有 canonical 事件、但 snapshot 表缺失的 session。

        :returns: 缺失 snapshot row 的 session_id 元组（按 session_id 升序）。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        rows = self.storage.execute_read(
            """
            SELECT DISTINCT e.session_id AS session_id
            FROM host_run_events AS e
            LEFT JOIN host_conversation_memory_snapshots AS s
                ON s.session_id = e.session_id
            WHERE e.kind = ? AND s.session_id IS NULL
            ORDER BY e.session_id ASC
            """,
            (RunEventKind.CANONICAL.value,),
        )
        return tuple(str(row["session_id"]) for row in rows)

    def _fetch_canonical_events_for_session(
        self,
        *,
        event_store: DurableRunEventStore,
        session_id: str,
    ) -> tuple[RunEvent, ...]:
        """按 session 顺序读取 canonical RunEvent 用于重投。

        通过 :meth:`DurableRunEventStore.fetch_events_by_position` 分页拉
        取，避免单次 SELECT 加载超大 EventLog。

        :param event_store: durable EventLog。
        :param session_id: 会话 id。
        :returns: 该 session 的全部 canonical RunEvent，按 global position
            升序。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        collected: list[RunEvent] = []
        after = None
        while True:
            batch = event_store.fetch_events_by_position(
                after=after, limit=_REPAIR_FETCH_BATCH_LIMIT
            )
            if not batch:
                break
            for position, event in batch:
                if (
                    event.session_id == session_id
                    and event.kind is RunEventKind.CANONICAL
                ):
                    collected.append(event)
                after = position
        return tuple(collected)

    def _has_terminal_event(
        self, events: tuple[RunEvent, ...]
    ) -> bool:
        """判断事件元组是否含 terminal 事件 (session 已落定)。

        ``TERMINAL_RUN_EVENT_TYPES`` 是唯一证明 session 已落定的信号; 只
        有命中 terminal 事件 repair 才会重建 snapshot, 否则视为 session
        仍在进行, 不写入半成品 read model。

        :param events: canonical RunEvent 元组。
        :returns: 含 terminal 事件时返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        for event in events:
            if event.type in TERMINAL_RUN_EVENT_TYPES:
                return True
        return False

    def _snapshot_row_exists_in_tx(
        self,
        *,
        tx: HostStorageTransaction,
        session_id: str,
    ) -> bool:
        """事务内判定 snapshot row 是否存在。

        :param tx: 当前事务。
        :param session_id: 会话 id。
        :returns: row 存在返回 ``True``。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        cursor = tx.execute(
            "SELECT 1 FROM host_conversation_memory_snapshots "
            "WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        return row is not None

    def _project_in_tx(
        self,
        *,
        tx: HostStorageTransaction,
        events: tuple[RunEvent, ...],
    ) -> None:
        """在已开启事务内按 canonical events 投影到 snapshot。

        :param tx: 当前事务。
        :param events: RunEvent 元组。
        :returns: 无返回值。
        """

        canonical_events = tuple(
            event for event in events if event.kind is RunEventKind.CANONICAL
        )
        if not canonical_events:
            return
        session_id = canonical_events[0].session_id
        run_id = canonical_events[0].run_id
        snapshot = self._read_snapshot_in_tx(tx=tx, session_id=session_id)
        snapshot = _project_canonical_events(
            snapshot=snapshot,
            events=canonical_events,
            recent_turn_limit=self.recent_turn_limit,
        )
        self._write_snapshot(tx=tx, snapshot=snapshot)
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.conversation_memory.durable_projected session_id=%s "
            "run_id=%s event_count=%s canonical_count=%s "
            "recent_turn_count=%s older_turn_count=%s tool_fact_count=%s",
            session_id,
            run_id,
            len(events),
            len(canonical_events),
            len(snapshot.recent_raw_turns),
            len(snapshot.older_raw_turns),
            len(snapshot.tool_facts),
        )

    def _read_snapshot_in_tx(
        self,
        *,
        tx: HostStorageTransaction,
        session_id: str,
    ) -> ConversationMemorySnapshot:
        """事务内读取 snapshot。"""

        cursor = tx.execute(
            "SELECT snapshot_payload FROM "
            "host_conversation_memory_snapshots WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        if row is None:
            return _empty_snapshot(session_id)
        payload_text = row["snapshot_payload"]
        if not isinstance(payload_text, str):
            raise ValueError(_ERROR_SNAPSHOT_DECODE)
        return _decode_snapshot_text(payload_text=payload_text)

    def _write_snapshot(
        self,
        *,
        tx: HostStorageTransaction,
        snapshot: ConversationMemorySnapshot,
    ) -> None:
        """事务内 upsert snapshot。

        :param tx: 当前事务。
        :param snapshot: 待写入的 snapshot。
        :returns: 无返回值。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        payload_text = _encode_snapshot_text(snapshot=snapshot)
        updated_at = self.clock.now().isoformat()
        tx.execute(
            "INSERT INTO host_conversation_memory_snapshots "
            "(session_id, snapshot_payload, updated_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET "
            "snapshot_payload = excluded.snapshot_payload, "
            "updated_at = excluded.updated_at",
            (snapshot.session_id, payload_text, updated_at),
        )


def open_durable_conversation_memory_store(
    storage: HostStorage,
    *,
    recent_turn_limit: int = DEFAULT_RECENT_TURN_LIMIT,
    clock: UtcClock | None = None,
) -> DurableConversationMemoryStore:
    """打开并初始化 durable conversation memory store。

    :param storage: 已构造的 :class:`HostStorage`。
    :param recent_turn_limit: recent raw turn 保留数量。
    :param clock: 可选 Host internal UTC clock；未传入时使用系统 UTC clock。
    :returns: 已初始化 schema 的 :class:`DurableConversationMemoryStore`。
    :raises sqlite3.DatabaseError: schema bootstrap 失败时抛出。
    """

    storage.open()
    ensure_durable_memory_schema(storage)
    return DurableConversationMemoryStore(
        storage=storage,
        recent_turn_limit=recent_turn_limit,
        clock=clock if clock is not None else _SystemUtcClock(),
    )


def _empty_snapshot(session_id: str) -> ConversationMemorySnapshot:
    """构造空 memory 快照。

    :param session_id: 会话 id。
    :returns: 空快照。
    """

    return ConversationMemorySnapshot(
        session_id=session_id,
        pinned_state=ConversationPinnedState(),
        task_frame=TaskFrame(),
        verified_claims=(),
        assumptions=AssumptionRegister(),
        evidence_anchors=(),
        recent_raw_turns=(),
        older_raw_turns=(),
        tool_facts=(),
        user_preference_ref=UserPreferenceProfileRef(),
    )


# ---------------------------------------------------------------------------
# JSON encode / decode helpers
# ---------------------------------------------------------------------------

_SCHEMA_VERSION: int = 1


def _encode_snapshot_text(*, snapshot: ConversationMemorySnapshot) -> str:
    """把 snapshot 序列化为 JSON 文本。"""

    payload: _JsonObject = _encode_snapshot(snapshot)
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(_ERROR_SNAPSHOT_ENCODE) from exc


def _decode_snapshot_text(
    *, payload_text: str
) -> ConversationMemorySnapshot:
    """从 JSON 文本反序列化 snapshot。"""

    try:
        raw = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise ValueError(_ERROR_SNAPSHOT_DECODE) from exc
    if not isinstance(raw, dict):
        raise ValueError(_ERROR_SNAPSHOT_DECODE)
    return _decode_snapshot(raw)


def _encode_snapshot(snapshot: ConversationMemorySnapshot) -> _JsonObject:
    """把 ``ConversationMemorySnapshot`` 编码为 JSON 对象。"""

    return {
        "schema_version": _SCHEMA_VERSION,
        "session_id": snapshot.session_id,
        "pinned_state": _encode_pinned_state(snapshot.pinned_state),
        "task_frame": _encode_task_frame(snapshot.task_frame),
        "verified_claims": [
            _encode_memory_claim(claim) for claim in snapshot.verified_claims
        ],
        "assumptions": _encode_assumption_register(snapshot.assumptions),
        "evidence_anchors": [
            _encode_evidence_anchor(anchor)
            for anchor in snapshot.evidence_anchors
        ],
        "recent_raw_turns": [
            _encode_raw_turn(turn) for turn in snapshot.recent_raw_turns
        ],
        "older_raw_turns": [
            _encode_raw_turn(turn) for turn in snapshot.older_raw_turns
        ],
        "tool_facts": [
            _encode_tool_fact(fact) for fact in snapshot.tool_facts
        ],
        "user_preference_ref": _encode_user_preference_ref(
            snapshot.user_preference_ref
        ),
    }


def _decode_snapshot(payload: _JsonObject) -> ConversationMemorySnapshot:
    """把 JSON 对象解码为 ``ConversationMemorySnapshot``。

    Snapshot 是 durable read model, 编码格式必须与 :data:`_SCHEMA_VERSION`
    严格一致; 如果 payload 缺失 ``schema_version`` 或与当前版本不匹配,
    必须立即抛 :class:`ValueError`, 禁止静默放过未知版本 (会污染
    durable repair 路径 / observer 重建路径)。
    """

    raw_version = payload.get("schema_version")
    if not isinstance(raw_version, int) or raw_version != _SCHEMA_VERSION:
        raise ValueError(_ERROR_SNAPSHOT_SCHEMA_VERSION)

    return ConversationMemorySnapshot(
        session_id=_decode_str(payload, "session_id"),
        pinned_state=_decode_pinned_state(
            _decode_object(payload, "pinned_state")
        ),
        task_frame=_decode_task_frame(_decode_object(payload, "task_frame")),
        verified_claims=tuple(
            _decode_memory_claim(item)
            for item in _decode_array(payload, "verified_claims")
        ),
        assumptions=_decode_assumption_register(
            _decode_object(payload, "assumptions")
        ),
        evidence_anchors=tuple(
            _decode_evidence_anchor(item)
            for item in _decode_array(payload, "evidence_anchors")
        ),
        recent_raw_turns=tuple(
            _decode_raw_turn(item)
            for item in _decode_array(payload, "recent_raw_turns")
        ),
        older_raw_turns=tuple(
            _decode_raw_turn(item)
            for item in _decode_array(payload, "older_raw_turns")
        ),
        tool_facts=tuple(
            _decode_tool_fact(item)
            for item in _decode_array(payload, "tool_facts")
        ),
        user_preference_ref=_decode_user_preference_ref(
            _decode_object(payload, "user_preference_ref")
        ),
    )


def _encode_pinned_state(state: ConversationPinnedState) -> _JsonObject:
    """编码 pinned state。"""

    return {
        "current_goal": state.current_goal,
        "confirmed_subjects": list(state.confirmed_subjects),
        "user_constraints": list(state.user_constraints),
        "open_questions": list(state.open_questions),
    }


def _decode_pinned_state(payload: _JsonObject) -> ConversationPinnedState:
    """解码 pinned state。"""

    return ConversationPinnedState(
        current_goal=_decode_optional_str(payload, "current_goal"),
        confirmed_subjects=_decode_str_tuple(payload, "confirmed_subjects"),
        user_constraints=_decode_str_tuple(payload, "user_constraints"),
        open_questions=_decode_str_tuple(payload, "open_questions"),
    )


def _encode_task_frame(frame: TaskFrame) -> _JsonObject:
    """编码 task frame。"""

    return {
        "topic_ref": frame.topic_ref,
        "entity_refs": list(frame.entity_refs),
        "period_refs": list(frame.period_refs),
        "basis_refs": list(frame.basis_refs),
        "unit_ref": frame.unit_ref,
    }


def _decode_task_frame(payload: _JsonObject) -> TaskFrame:
    """解码 task frame。"""

    return TaskFrame(
        topic_ref=_decode_optional_str(payload, "topic_ref"),
        entity_refs=_decode_str_tuple(payload, "entity_refs"),
        period_refs=_decode_str_tuple(payload, "period_refs"),
        basis_refs=_decode_str_tuple(payload, "basis_refs"),
        unit_ref=_decode_optional_str(payload, "unit_ref"),
    )


def _encode_memory_claim(claim: MemoryClaim) -> _JsonObject:
    """编码 memory claim。"""

    return {
        "claim_id": claim.claim_id,
        "status": claim.status.value,
        "text": claim.text,
        "source_run_id": claim.source_run_id,
        "source_event_cursor_sequence": claim.source_event_cursor.sequence,
        "evidence_anchor_id": claim.evidence_anchor_id,
        "scope": claim.scope.value,
        "created_at": claim.created_at.isoformat(),
        "supersedes": list(claim.supersedes),
        "provenance": _encode_provenance(claim.provenance),
    }


def _decode_memory_claim(payload: _JsonObject) -> MemoryClaim:
    """解码 memory claim。"""

    return MemoryClaim(
        claim_id=_decode_str(payload, "claim_id"),
        status=ClaimStatus(_decode_str(payload, "status")),
        text=_decode_str(payload, "text"),
        source_run_id=_decode_str(payload, "source_run_id"),
        source_event_cursor=_decode_run_event_cursor(
            sequence=_decode_int(payload, "source_event_cursor_sequence"),
        ),
        evidence_anchor_id=_decode_optional_str(payload, "evidence_anchor_id"),
        scope=MemoryScope(_decode_str(payload, "scope")),
        created_at=_decode_datetime(payload, "created_at"),
        supersedes=_decode_str_tuple(payload, "supersedes"),
        provenance=_decode_provenance(_decode_object(payload, "provenance")),
    )


def _encode_assumption_register(register: AssumptionRegister) -> _JsonObject:
    """编码 assumption register。"""

    return {
        "claims": [_encode_memory_claim(claim) for claim in register.claims],
    }


def _decode_assumption_register(payload: _JsonObject) -> AssumptionRegister:
    """解码 assumption register。"""

    return AssumptionRegister(
        claims=tuple(
            _decode_memory_claim(item)
            for item in _decode_array(payload, "claims")
        ),
    )


def _encode_evidence_anchor(anchor: EvidenceAnchor) -> _JsonObject:
    """编码证据锚点。"""

    return {
        "anchor_id": anchor.anchor_id,
        "origin_event_cursor_sequence": anchor.origin_event_cursor.sequence,
        "tool_call_id": anchor.tool_call_id,
        "source_ref": anchor.source_ref,
        "chunk_ref": anchor.chunk_ref,
        "fingerprint": anchor.fingerprint,
        "summary": anchor.summary,
        "provenance": _encode_provenance(anchor.provenance),
    }


def _decode_evidence_anchor(payload: _JsonObject) -> EvidenceAnchor:
    """解码证据锚点。"""

    return EvidenceAnchor(
        anchor_id=_decode_str(payload, "anchor_id"),
        origin_event_cursor=_decode_run_event_cursor(
            sequence=_decode_int(payload, "origin_event_cursor_sequence"),
        ),
        tool_call_id=_decode_optional_str(payload, "tool_call_id"),
        source_ref=_decode_optional_str(payload, "source_ref"),
        chunk_ref=_decode_optional_str(payload, "chunk_ref"),
        fingerprint=_decode_optional_str(payload, "fingerprint"),
        summary=_decode_str(payload, "summary"),
        provenance=_decode_provenance(_decode_object(payload, "provenance")),
    )


def _encode_raw_turn(turn: ConversationRawTurn) -> _JsonObject:
    """编码 raw turn。"""

    return {
        "turn_id": turn.turn_id,
        "user_text": turn.user_text,
        "assistant_final": turn.assistant_final,
        "user_provenance": _encode_provenance(turn.user_provenance),
        "assistant_provenance": (
            None
            if turn.assistant_provenance is None
            else _encode_provenance(turn.assistant_provenance)
        ),
        "terminal_summary": turn.terminal_summary,
        "terminal_provenance": (
            None
            if turn.terminal_provenance is None
            else _encode_provenance(turn.terminal_provenance)
        ),
    }


def _decode_raw_turn(payload: _JsonObject) -> ConversationRawTurn:
    """解码 raw turn。"""

    assistant_provenance_raw = payload.get("assistant_provenance")
    terminal_provenance_raw = payload.get("terminal_provenance")
    assistant_provenance: MemoryProvenance | None = None
    if isinstance(assistant_provenance_raw, Mapping):
        assistant_provenance = _decode_provenance(assistant_provenance_raw)
    terminal_provenance: MemoryProvenance | None = None
    if isinstance(terminal_provenance_raw, Mapping):
        terminal_provenance = _decode_provenance(terminal_provenance_raw)
    return ConversationRawTurn(
        turn_id=_decode_str(payload, "turn_id"),
        user_text=_decode_str(payload, "user_text"),
        assistant_final=_decode_optional_str(payload, "assistant_final"),
        user_provenance=_decode_provenance(
            _decode_object(payload, "user_provenance")
        ),
        assistant_provenance=assistant_provenance,
        terminal_summary=_decode_optional_str(payload, "terminal_summary"),
        terminal_provenance=terminal_provenance,
    )


def _encode_tool_fact(fact: ConversationToolFact) -> _JsonObject:
    """编码工具事实。"""

    return {
        "fact_id": fact.fact_id,
        "tool_name": fact.tool_name,
        "tool_call_id": fact.tool_call_id,
        "event_type": fact.event_type.value,
        "summary": fact.summary,
        "cursor_fingerprint": fact.cursor_fingerprint,
        "has_more": fact.has_more,
        "provenance": _encode_provenance(fact.provenance),
    }


def _decode_tool_fact(payload: _JsonObject) -> ConversationToolFact:
    """解码工具事实。"""

    has_more_raw = payload.get("has_more")
    has_more_value: bool | None
    if has_more_raw is None:
        has_more_value = None
    elif isinstance(has_more_raw, bool):
        has_more_value = has_more_raw
    else:
        raise ValueError(_ERROR_SNAPSHOT_DECODE)
    return ConversationToolFact(
        fact_id=_decode_str(payload, "fact_id"),
        tool_name=_decode_str(payload, "tool_name"),
        tool_call_id=_decode_str(payload, "tool_call_id"),
        event_type=RunEventType(_decode_str(payload, "event_type")),
        summary=_decode_str(payload, "summary"),
        cursor_fingerprint=_decode_optional_str(payload, "cursor_fingerprint"),
        has_more=has_more_value,
        provenance=_decode_provenance(_decode_object(payload, "provenance")),
    )


def _encode_provenance(provenance: MemoryProvenance) -> _JsonObject:
    """编码 memory provenance。"""

    return {
        "source_run_id": provenance.source_run_id,
        "source_event_cursor_sequence": provenance.source_event_cursor.sequence,
        "producer_kind": provenance.producer_kind.value,
        "ingestion_policy": provenance.ingestion_policy.value,
        "scope": provenance.scope.value,
        "trust_level": provenance.trust_level.value,
    }


def _decode_provenance(payload: _JsonObject) -> MemoryProvenance:
    """解码 memory provenance。"""

    return MemoryProvenance(
        source_run_id=_decode_str(payload, "source_run_id"),
        source_event_cursor=_decode_run_event_cursor(
            sequence=_decode_int(payload, "source_event_cursor_sequence"),
        ),
        producer_kind=MemoryProducerKind(
            _decode_str(payload, "producer_kind")
        ),
        ingestion_policy=MemoryIngestionPolicy(
            _decode_str(payload, "ingestion_policy")
        ),
        scope=MemoryScope(_decode_str(payload, "scope")),
        trust_level=MemoryTrustLevel(_decode_str(payload, "trust_level")),
    )


def _encode_user_preference_ref(ref: UserPreferenceProfileRef) -> _JsonObject:
    """编码用户偏好画像引用。"""

    return {
        "profile_id": ref.profile_id,
        "scope": ref.scope.value,
    }


def _decode_user_preference_ref(
    payload: _JsonObject,
) -> UserPreferenceProfileRef:
    """解码用户偏好画像引用。"""

    return UserPreferenceProfileRef(
        profile_id=_decode_optional_str(payload, "profile_id"),
        scope=MemoryScope(_decode_str(payload, "scope")),
    )


def _decode_run_event_cursor(*, sequence: int) -> RunEventCursor:
    """构造 :class:`RunEventCursor`。

    :param sequence: 事件序号。
    :returns: :class:`RunEventCursor` 实例。
    """

    return RunEventCursor(sequence=sequence)


def _decode_str(payload: _JsonObject, key: str) -> str:
    """从 JSON 对象读取必需字符串字段。"""

    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{_ERROR_SNAPSHOT_DECODE}:{key}")
    return value


def _decode_optional_str(payload: _JsonObject, key: str) -> str | None:
    """从 JSON 对象读取可选字符串字段。"""

    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{_ERROR_SNAPSHOT_DECODE}:{key}")
    return value


def _decode_int(payload: _JsonObject, key: str) -> int:
    """从 JSON 对象读取必需整数字段。"""

    value = payload.get(key)
    # bool 是 int 子类, 这里禁止把 True/False 当 int 解码。
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{_ERROR_SNAPSHOT_DECODE}:{key}")
    return value


def _decode_datetime(payload: _JsonObject, key: str) -> datetime:
    """从 JSON 对象读取 ISO 格式 UTC 时间字段。"""

    raw = _decode_str(payload, key)
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"{_ERROR_SNAPSHOT_DECODE}:{key}") from exc


def _decode_object(payload: _JsonObject, key: str) -> _JsonObject:
    """从 JSON 对象读取必需嵌套对象字段。"""

    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{_ERROR_SNAPSHOT_DECODE}:{key}")
    return value


def _decode_array(payload: _JsonObject, key: str) -> list[_JsonObject]:
    """从 JSON 对象读取嵌套对象数组字段。"""

    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{_ERROR_SNAPSHOT_DECODE}:{key}")
    items: list[_JsonObject] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError(f"{_ERROR_SNAPSHOT_DECODE}:{key}")
        items.append(item)
    return items


def _decode_str_tuple(payload: _JsonObject, key: str) -> tuple[str, ...]:
    """从 JSON 对象读取字符串数组字段。"""

    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{_ERROR_SNAPSHOT_DECODE}:{key}")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{_ERROR_SNAPSHOT_DECODE}:{key}")
        items.append(item)
    return tuple(items)


__all__ = [
    "DEFAULT_RECENT_TURN_LIMIT",
    "DurableConversationMemoryStore",
    "UtcClock",
    "ensure_durable_memory_schema",
    "open_durable_conversation_memory_store",
]
