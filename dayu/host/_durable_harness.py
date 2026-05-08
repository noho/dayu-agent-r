"""Host P6 durable harness 装配入口。

本模块为上层（Service / smoke / 测试）提供以 :class:`DurableRunEventStore`
为后端、并自动驱动 :class:`ProjectionCoordinator` 的 :class:`LocalRunHarness`
装配函数。它不替换 :func:`_build_default_harness`，而是作为 durable
存储路径的显式入口；调用方负责保留 :class:`HostStorage` 的 close 责任。

约束：

- 装配函数不引入跨层依赖：仅装配 Host 内部组件。
- 必须在调用方使用完毕后通过返回的 ``close`` 回调释放 ``HostStorage``。
- 默认绑定 memory / timeline / audit 三个 observer；其中 memory 是
  required projection。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from dayu.contracts import ToolExecutor
from dayu.host._audit_projection import AuditProjectionObserver
from dayu.host._conversation_memory import (
    ConversationMemoryStore,
    InMemoryConversationMemoryStore,
)
from dayu.host._durable_event_store import (
    DurableRunEventStore,
    open_durable_event_store,
)
from dayu.host._event_observer import ProjectionCoordinator
from dayu.host._host_storage_transaction import HostStorage
from dayu.host._memory_projection import MemoryProjectionObserver
from dayu.host._projection_store import ProjectionStore
from dayu.host._run_harness import (
    EngineWorker,
    LocalProxy,
    LocalRunHarness,
    _NoopToolExecutor,
)
from dayu.host._timeline_projection import TimelineProjectionObserver
from dayu.host._tool_runtime import (
    InMemoryToolRuntime,
    ToolRuntimeToolExecutor,
)


@dataclass(slots=True)
class DurableHarnessBundle:
    """durable harness 装配产物。

    :param harness: 装配完成的 :class:`LocalRunHarness`。
    :param storage: 持有 SQLite 连接的 :class:`HostStorage`。
    :param event_store: durable :class:`DurableRunEventStore`。
    :param coordinator: :class:`ProjectionCoordinator`，调用方负责驱动。
    :param memory_store: 内存对话 read model。
    :param timeline_observer: timeline observer 实例（非 required）。
    :param audit_observer: audit observer 实例（非 required）。
    :param close: 释放 storage 的回调。
    """

    harness: LocalRunHarness
    storage: HostStorage
    event_store: DurableRunEventStore
    coordinator: ProjectionCoordinator
    memory_store: ConversationMemoryStore
    timeline_observer: TimelineProjectionObserver
    audit_observer: AuditProjectionObserver
    close: Callable[[], None]


def build_durable_harness(
    *,
    database_path: str,
    executor: ToolExecutor | None = None,
    memory_store: ConversationMemoryStore | None = None,
) -> DurableHarnessBundle:
    """装配 durable :class:`LocalRunHarness`。

    :param database_path: SQLite 路径（``":memory:"`` 用于测试）。
    :param executor: 自定义 ToolExecutor；默认为 ``_NoopToolExecutor``。
    :param memory_store: 自定义对话 memory store；默认为
        :class:`InMemoryConversationMemoryStore`。
    :returns: :class:`DurableHarnessBundle`。
    :raises Exception: 装配失败时透传底层异常。
    """

    storage = HostStorage(database_path=database_path)
    event_store = open_durable_event_store(storage)

    actual_memory: ConversationMemoryStore = (
        memory_store if memory_store is not None else InMemoryConversationMemoryStore()
    )
    memory_observer = MemoryProjectionObserver(memory_store=actual_memory)
    timeline_observer = TimelineProjectionObserver()
    audit_observer = AuditProjectionObserver()

    projection_store = ProjectionStore(storage=storage)
    coordinator = ProjectionCoordinator(
        storage=storage,
        event_store=event_store,
        projection_store=projection_store,
        observers=(memory_observer, timeline_observer, audit_observer),
    )

    actual_executor: ToolExecutor = (
        executor if executor is not None else _NoopToolExecutor()
    )
    runtime = InMemoryToolRuntime(
        executor=actual_executor,
        event_store=event_store,
    )
    harness = LocalRunHarness(
        proxy=LocalProxy(
            worker=EngineWorker(ToolRuntimeToolExecutor(runtime))
        ),
        event_store=event_store,
        tool_runtime=runtime,
    )

    return DurableHarnessBundle(
        harness=harness,
        storage=storage,
        event_store=event_store,
        coordinator=coordinator,
        memory_store=actual_memory,
        timeline_observer=timeline_observer,
        audit_observer=audit_observer,
        close=storage.close,
    )


__all__ = [
    "DurableHarnessBundle",
    "build_durable_harness",
]
