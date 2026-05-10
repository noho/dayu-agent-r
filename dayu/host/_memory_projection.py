"""Host P6 memory projection observer。

本模块把 P3-P5 的 memory store 投影封装为基于 durable EventLog 的
observer，按 run_id 累积 canonical 事件，在 terminal 事件后整批投影。

P8-S8 起 observer 必须使用 transaction-aware 写入：投影写入与
projection checkpoint 推进必须在同一 :class:`HostStorageTransaction`
内提交，避免 “projection checkpoint 已 caught up，但 memory snapshot
未持久化” 的恢复洞。:class:`ConversationMemoryProjectionStore` 协议
继承 :class:`ConversationMemoryStore`，附加
``project_run_events_in_transaction`` 接口；observer 只接受该协议。

memory projection 是 required projection：

- 任意 run 的 ``USER_INPUT_ACCEPTED`` 都不能丢失。
- 成功终态写 assistant final answer。
- Engine ``RUN_FAILED`` 与 Host-owned failure 写中性 terminal summary。
- cancelled / suspended 不写 assistant terminal summary，但保留用户输入。

P8 起 ``ObserverSink.process`` 已升级为 async 协议，observer 直接
``await`` memory store，不再需要 sync-async 桥接。

P8 PR #40 follow-up 起 durable 装配在 terminal run 投影时必须从
EventLog 真源重读该 run 的完整 canonical 事件，再与 checkpoint advance
处于同一 observer transaction 内提交；进程内 pending 仅作为非 durable /
测试路径的短生命周期缓存，不承担跨 checkpoint / restart 的事实保存职责。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from dayu.host._conversation_memory import ConversationMemoryStore
from dayu.host._event_observer import (
    ObserverDescriptor,
    ProjectionEventEnvelope,
)
from dayu.host._host_storage_transaction import HostStorageTransaction
from dayu.host.contracts import (
    TERMINAL_RUN_EVENT_TYPES,
    RunEvent,
    RunEventKind,
)

_OBSERVER_ID: str = "host_memory_projection"
_PROJECTION_NAME: str = "conversation_memory"
_SCHEMA_VERSION: int = 1


class ConversationMemoryProjectionStore(ConversationMemoryStore, Protocol):
    """observer 路径专用 :class:`ConversationMemoryStore` 协议扩展。

    在 :class:`ConversationMemoryStore` 之上附加事务感知投影接口。
    observer 持有 :class:`HostStorageTransaction` 时调用
    ``project_run_events_in_transaction``，确保 snapshot 写入与
    projection checkpoint 推进在同一事务内提交。

    :param tx: 当前事务。
    :param events: 同一 run 的 RunEvent 元组。
    :returns: 无返回值。
    """

    async def project_run_events_in_transaction(
        self,
        *,
        tx: HostStorageTransaction,
        events: tuple[RunEvent, ...],
    ) -> None:
        """事务内投影 RunEvent。

        :param tx: 当前事务。
        :param events: 同一 run 的 RunEvent 元组。
        :returns: 无返回值。
        :raises Exception: 投影失败时透传。
        """
        ...


class CanonicalRunEventReader(Protocol):
    """按 run 读取 canonical EventLog facts 的 Host internal 协议。

    durable memory observer 使用该协议在 terminal 事件到达时从 EventLog
    真源重建同一 run 的完整 canonical 事件，避免 checkpoint 已推进后进程
    重启导致 ``_pending_by_run`` 丢失。
    """

    def fetch_canonical_events_for_run_in_transaction(
        self,
        *,
        tx: HostStorageTransaction,
        session_id: str,
        run_id: str,
    ) -> tuple[RunEvent, ...]:
        """在当前 observer 事务内读取同一 run 的 canonical 事件。

        :param tx: 当前 observer 事务。
        :param session_id: 会话 id。
        :param run_id: Run id。
        :returns: RunEvent 元组，按 EventLog 全局位置升序。
        :raises Exception: 读取失败时透传。
        """
        ...


@dataclass(slots=True)
class MemoryProjectionObserver:
    """memory read model observer。

    :param memory_store: 实现 :class:`ConversationMemoryProjectionStore`
        协议的 memory store。
    :param event_reader: durable EventLog canonical fact reader；提供时
        terminal 投影从 EventLog 重读完整 run facts，缺省仅用于旧单元测试。
    """

    memory_store: ConversationMemoryProjectionStore
    event_reader: CanonicalRunEventReader | None = None
    _pending_by_run: dict[str, list[RunEvent]] = field(
        default_factory=dict, init=False
    )

    @property
    def descriptor(self) -> ObserverDescriptor:
        """Observer 元数据。

        :returns: :class:`ObserverDescriptor`。
        :raises Exception: 不主动抛出异常。
        """

        return ObserverDescriptor(
            observer_id=_OBSERVER_ID,
            projection_name=_PROJECTION_NAME,
            schema_version=_SCHEMA_VERSION,
            required=True,
        )

    async def process(
        self,
        *,
        tx: HostStorageTransaction,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        """累积 canonical 事件，遇到 terminal 时整批投影。

        memory snapshot 写入与 ``ProjectionCoordinator`` checkpoint
        advance 共享同一个 :class:`HostStorageTransaction`：
        ``project_run_events_in_transaction`` 不再开新事务，写入失败时
        observer transaction 整体回滚，checkpoint 不前进。

        :param tx: 当前事务。
        :param batch: 事件 envelope 元组。
        :returns: 无返回值。
        :raises Exception: 投影失败时透传。
        """

        # at-least-once 不变量：sink 失败时 ``_pending_by_run`` 不能被破坏。
        # 因此先把本批次新增事件累积到一个临时副本中，sink 全部成功后再
        # 整体提交回 ``_pending_by_run``，并在 terminal 事件成功投影后才
        # 删除该 run 的累积条目。
        staged: dict[str, list[RunEvent]] = {
            run_id: list(events)
            for run_id, events in self._pending_by_run.items()
        }
        terminal_run_ids: list[str] = []
        for envelope in batch:
            event = envelope.event
            if event.kind is not RunEventKind.CANONICAL:
                continue
            staged.setdefault(event.run_id, []).append(event)
            if event.type in TERMINAL_RUN_EVENT_TYPES:
                if self.event_reader is None:
                    events = tuple(staged[event.run_id])
                else:
                    events = (
                        self.event_reader
                        .fetch_canonical_events_for_run_in_transaction(
                            tx=tx,
                            session_id=event.session_id,
                            run_id=event.run_id,
                        )
                    )
                await self.memory_store.project_run_events_in_transaction(
                    tx=tx, events=events
                )
                terminal_run_ids.append(event.run_id)
        # sink 全部成功后才把 staged 状态写回真源，并清掉已 terminal 的 run。
        self._pending_by_run = staged
        for run_id in terminal_run_ids:
            self._pending_by_run.pop(run_id, None)

    async def rebuild_from_events(
        self,
        events: tuple[RunEvent, ...],
    ) -> None:
        """测试 helper：从给定事件批量 rebuild memory。

        生产路径不调用本方法。生产 startup / 崩溃恢复路径由
        :meth:`ProjectionCoordinator.startup_reconcile` 经由 ``drain()``
        + observer ``process()`` 完成，复用同一份 at-least-once 累积逻辑。
        本 helper 仅供 ``tests/host/test_phase6_memory_rebuild.py`` 类型
        测试以 canonical RunEvent 序列直接驱动 memory store。它不持有
        observer transaction，因此走非事务版本 ``project_run_events``。

        :param events: 全部 RunEvent。
        :returns: 无返回值。
        :raises Exception: 投影失败时透传。
        """

        groups: dict[str, list[RunEvent]] = {}
        for event in events:
            if event.kind is not RunEventKind.CANONICAL:
                continue
            groups.setdefault(event.run_id, []).append(event)
        for run_events in groups.values():
            await self.memory_store.project_run_events(tuple(run_events))


__all__ = [
    "CanonicalRunEventReader",
    "ConversationMemoryProjectionStore",
    "MemoryProjectionObserver",
]
