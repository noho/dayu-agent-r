"""tests/host 私有 memory store fake。

本模块仅供 ``tests/host/`` 测试使用，承载 P8-S8 之前由 production
``InMemoryConversationMemoryStore`` 提供的纯内存 :class:`ConversationMemoryStore`
行为。生产代码不得再依赖该实现：durable harness 必须使用
:class:`DurableConversationMemoryStore`，legacy 内存路径只作为非 durable
测试便利。``utils/`` smoke 不得 import 本模块；smoke 私有 fake 见
``utils/_smoke_memory_store.py``，避免 ``utils/`` -> ``tests/`` 反向依赖。

行为与 P3-P5 :class:`InMemoryConversationMemoryStore` 一致：

- ``project_run_events`` / ``project_run_events_in_transaction`` 复用同
  一份 canonical 投影 helper，写入纯内存 dict。
- ``project_run_events_in_transaction`` 接受 :class:`HostStorageTransaction`
  参数但不消费，用于满足 :class:`ConversationMemoryProjectionStore`
  observer 协议。
- ``apply_patch`` 支持 reset / SESSION scope clear / claim correction，
  与 production InMemory 保持一致；非 SESSION scope clear 抛 ``ValueError``。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field, replace

from dayu.host._conversation_memory import (
    ClaimCorrectionPatch,
    ConversationMemoryPatch,
    ConversationMemorySnapshot,
    MemoryResetPatch,
    MemoryScope,
    ScopeClearPatch,
    _empty_snapshot,
    _project_canonical_events,
)
from dayu.host._host_storage_transaction import HostStorageTransaction
from dayu.host.contracts import RunEvent, RunEventKind
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_ERROR_SCOPE_CLEAR_UNSUPPORTED_SCOPE: str = "scope_clear_only_supports_session"
_LOGGER: logging.Logger = logging.getLogger("dayu.host._conversation_memory")


@dataclass(slots=True)
class FakeInMemoryConversationMemoryStore:
    """tests-only 内存 :class:`ConversationMemoryProjectionStore` fake。

    :param recent_turn_limit: recent raw turn 保留数量。
    """

    recent_turn_limit: int = 4
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _snapshot_by_session: dict[str, ConversationMemorySnapshot] = field(
        default_factory=dict,
        init=False,
    )

    async def project_run_events(self, events: tuple[RunEvent, ...]) -> None:
        """从同一 run 的已落库事件投影 memory。

        :param events: 同一 run 的 RunEvent 元组。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        if not events:
            return
        canonical_events = tuple(
            event for event in events if event.kind is RunEventKind.CANONICAL
        )
        if not canonical_events:
            return
        session_id = canonical_events[0].session_id
        run_id = canonical_events[0].run_id
        async with self._lock:
            snapshot = self._snapshot_by_session.get(
                session_id, _empty_snapshot(session_id)
            )
            snapshot = _project_canonical_events(
                snapshot=snapshot,
                events=canonical_events,
                recent_turn_limit=self.recent_turn_limit,
            )
            self._snapshot_by_session[session_id] = snapshot
            _LOGGER.log(
                VERBOSE_LOG_LEVEL,
                "host.conversation_memory.projected session_id=%s run_id=%s "
                "event_count=%s canonical_count=%s recent_turn_count=%s "
                "older_turn_count=%s tool_fact_count=%s",
                session_id,
                run_id,
                len(events),
                len(canonical_events),
                len(snapshot.recent_raw_turns),
                len(snapshot.older_raw_turns),
                len(snapshot.tool_facts),
            )

    async def project_run_events_in_transaction(
        self,
        *,
        tx: HostStorageTransaction,
        events: tuple[RunEvent, ...],
    ) -> None:
        """observer 路径同事务投影 fake。

        本 fake 不写 SQLite，``tx`` 仅用于满足
        :class:`ConversationMemoryProjectionStore` observer 协议契约。

        :param tx: 当前事务（不消费）。
        :param events: 同一 run 的 RunEvent 元组。
        :returns: 无返回值。
        """

        del tx
        await self.project_run_events(events)

    async def get_snapshot(self, session_id: str) -> ConversationMemorySnapshot:
        """读取 session memory 快照。

        :param session_id: 会话 id。
        :returns: memory 快照；不存在时返回空快照。
        :raises Exception: 不主动抛出异常。
        """

        async with self._lock:
            return self._snapshot_by_session.get(
                session_id, _empty_snapshot(session_id)
            )

    async def apply_patch(self, patch: ConversationMemoryPatch) -> None:
        """应用 internal-only memory patch。

        :param patch: memory patch。
        :returns: 无返回值。
        :raises ValueError: ScopeClearPatch 使用非 SESSION scope 时抛出。
        """

        async with self._lock:
            match patch:
                case MemoryResetPatch(session_id=session_id):
                    self._snapshot_by_session[session_id] = _empty_snapshot(
                        session_id
                    )
                case ScopeClearPatch(
                    session_id=session_id, scope=MemoryScope.SESSION
                ):
                    self._snapshot_by_session[session_id] = _empty_snapshot(
                        session_id
                    )
                case ScopeClearPatch(scope=scope):
                    raise ValueError(
                        f"{_ERROR_SCOPE_CLEAR_UNSUPPORTED_SCOPE}: "
                        f"{scope.value}"
                    )
                case ClaimCorrectionPatch(
                    session_id=session_id, corrected_claim=claim
                ):
                    snapshot = self._snapshot_by_session.get(
                        session_id, _empty_snapshot(session_id)
                    )
                    self._snapshot_by_session[session_id] = replace(
                        snapshot,
                        verified_claims=snapshot.verified_claims + (claim,),
                    )


__all__ = [
    "FakeInMemoryConversationMemoryStore",
]
