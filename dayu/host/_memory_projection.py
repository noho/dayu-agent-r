"""Host P6 memory projection observer。

本模块把 P3-P5 已有的 ``InMemoryConversationMemoryStore.project_run_events``
封装为基于 durable EventLog 的 observer，按 run_id 累积 canonical 事件，
在 terminal 事件后整批投影到 :class:`ConversationMemoryStore`。

memory projection 是 required projection：

- 任意 run 的 ``USER_INPUT_ACCEPTED`` 都不能丢失。
- 成功终态写 assistant final answer。
- Engine ``RUN_FAILED`` 与 Host-owned failure 写中性 terminal summary。
- cancelled / suspended 不写 assistant terminal summary，但保留用户输入。
"""

from __future__ import annotations

from collections.abc import Awaitable
from dataclasses import dataclass, field

from dayu.host._conversation_memory import ConversationMemoryStore
from dayu.host._event_observer import (
    ObserverDescriptor,
    ObserverSink,
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

    def process(
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
        for envelope in batch:
            event = envelope.event
            if event.kind is not RunEventKind.CANONICAL:
                continue
            self._pending_by_run.setdefault(event.run_id, []).append(event)
            if event.type in TERMINAL_RUN_EVENT_TYPES:
                events = tuple(self._pending_by_run.pop(event.run_id))
                # 同步路径：memory store 是 asyncio 协程接口，但 observer
                # 在事务内同步运行；采用 ``run_until_complete`` 兼容内存实
                # 现的 Lock。
                _run_async(
                    self.memory_store.project_run_events(events)
                )

    def rebuild_from_events(
        self,
        events: tuple[RunEvent, ...],
    ) -> None:
        """从 durable EventLog 全量 rebuild memory。

        测试 / projection rebuild 入口：按 run_id 切片整批投影。

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
            _run_async(
                self.memory_store.project_run_events(tuple(run_events))
            )


def _run_async(coro: Awaitable[None]) -> None:
    """在同步上下文驱动一个协程到完成。

    observer 在 ``ProjectionCoordinator`` 写事务的线程内被同步调用，但
    memory store 协议是协程；本函数在没有 running loop 时用临时 loop
    驱动，在已有 running loop 时把协程派发到一个独立线程内的新 loop
    执行，避免阻塞外层 loop 也避免重入冲突。

    :param coro: awaitable 对象。
    :returns: 无返回值。
    :raises Exception: 协程内部异常透传。
    """

    import asyncio
    import threading

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    async def _await_target() -> None:
        await coro

    if running is None:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_await_target())
        finally:
            loop.close()
        return

    error_box: list[BaseException] = []

    def _runner() -> None:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_await_target())
        except BaseException as exc:  # noqa: BLE001
            error_box.append(exc)
        finally:
            loop.close()

    thread = threading.Thread(target=_runner, name="memory-projection-runner")
    thread.start()
    thread.join()
    if error_box:
        raise error_box[0]


__all__ = [
    "MemoryProjectionObserver",
]
