"""Host P6 memory projection observer。

本模块把 P3-P5 已有的 ``InMemoryConversationMemoryStore.project_run_events``
封装为基于 durable EventLog 的 observer，按 run_id 累积 canonical 事件，
在 terminal 事件后整批投影到 :class:`ConversationMemoryStore`。

memory projection 是 required projection：

- 任意 run 的 ``USER_INPUT_ACCEPTED`` 都不能丢失。
- 成功终态写 assistant final answer。
- Engine ``RUN_FAILED`` 与 Host-owned failure 写中性 terminal summary。
- cancelled / suspended 不写 assistant terminal summary，但保留用户输入。

P8 起 ``ObserverSink.process`` 已升级为 async 协议，observer 直接
``await`` :class:`ConversationMemoryStore`，不再需要 sync-async 桥接。
"""

from __future__ import annotations

from dataclasses import dataclass, field

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


@dataclass(slots=True)
class MemoryProjectionObserver:
    """memory read model observer。

    :param memory_store: ConversationMemoryStore 实例。
    """

    memory_store: ConversationMemoryStore
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

        memory store 写入是内存态、幂等：``project_run_events`` 接收同一
        run 的事件元组，``InMemoryConversationMemoryStore`` 内部会用
        ``replace`` 模式合并。``tx`` 不参与 memory 写入但保留参数以保持协议
        一致。

        :param tx: 当前事务。
        :param batch: 事件 envelope 元组。
        :returns: 无返回值。
        :raises Exception: 投影失败时透传。
        """

        del tx
        # at-least-once 不变量：sink 失败时 ``_pending_by_run`` 不能被破坏。
        # 因此先把本批次新增事件累积到一个临时副本中，sink 全部成功后再
        # 整体提交回 ``_pending_by_run``，并在 terminal 事件成功投影后才
        # 删除该 run 的累积条目。这样即使 ``project_run_events`` 抛异常被
        # 上层标记为 ``RETRYABLE_FAILED`` / ``BLOCKED_FAILED``，下次 drain
        # / 重放时 observer 仍能用同一批 envelope 重放并重新累积，用户
        # 输入与 final 不会因 pop-before-sink 永久丢失。
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
                events = tuple(staged[event.run_id])
                # P8 起 observer 协议为 async，直接 await memory store；不再
                # 需要 thread + 新 event loop 的 sync-async 桥接。
                await self.memory_store.project_run_events(events)
                terminal_run_ids.append(event.run_id)
        # sink 全部成功后才把 staged 状态写回真源，并清掉已 terminal 的
        # run 条目；任何一次 ``await`` 抛异常时控制流不会到达此处，
        # ``_pending_by_run`` 维持调用前的累积视图。
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
        本 helper 仅供 ``tests/host/test_phase6_memory_rebuild.py`` 直接以
        canonical RunEvent 序列驱动 ``InMemoryConversationMemoryStore``，
        作为 memory required projection 五条事实（成功 / engine failed /
        host failed / cancelled / suspended）的最小行为契约。

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
    "MemoryProjectionObserver",
]
