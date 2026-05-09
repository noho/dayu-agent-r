"""Host P6/P7 durable harness 装配入口。

本模块为上层（Service / smoke / 测试）提供以 :class:`DurableRunEventStore`
为后端、并自动驱动 :class:`ProjectionCoordinator` 的 :class:`LocalRunHarness`
装配函数。它不替换 :func:`_build_default_harness`，而是作为 durable
存储路径的显式入口；调用方负责保留 :class:`HostStorage` 的 close 责任。

约束：

- 装配函数不引入跨层依赖：仅装配 Host 内部组件。
- 必须在调用方使用完毕后通过返回的 ``close`` 回调释放 ``HostStorage``。
- 默认绑定 memory / timeline / audit 三个 observer；其中 memory 是
  required projection。
- P7：``DurableHarnessConfig.tool_trace_path`` 非空（且非空字符串）时，
  装配 :class:`ToolTraceObserver` + :class:`ToolTraceJsonlSink` 并附加进
  observer 元组；为 ``None`` / 空时不装配，行为与 P6 完全一致。
- P8-S3：``DurableHarnessConfig.attempt_lease_config`` 通过装配层注入
  attempt lease TTL / renew interval / owner_id 前缀；store 层不持有
  TTL，public ``start_run`` 也不暴露 TTL。装配产物包含
  :class:`AttemptLeaseStore` 与 :class:`AttemptSupervisor`，由
  :class:`LocalRunHarness` 薄委托使用。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dayu.contracts import ToolExecutor
from dayu.host._attempt_lease import (
    DEFAULT_ATTEMPT_LEASE_CONFIG,
    AttemptLeaseConfig,
    UtcClock,
)
from dayu.host._attempt_supervisor import AttemptSupervisor
from dayu.host._audit_projection import AuditProjectionObserver
from dayu.host._conversation_memory import (
    ConversationMemoryStore,
    InMemoryConversationMemoryStore,
)
from dayu.host._durable_event_store import (
    DurableRunEventStore,
    open_durable_event_store,
)
from dayu.host._event_observer import ObserverSink, ProjectionCoordinator
from dayu.host._host_storage_transaction import HostStorage
from dayu.host._memory_projection import MemoryProjectionObserver
from dayu.host._projection_store import ProjectionStore
from dayu.host._proxy import LocalProxy, WorkerProxy
from dayu.host._run_harness import (
    EngineWorker,
    LocalRunHarness,
    _NoopToolExecutor,
)
from dayu.host._run_input_context_fact import RunInputContextFactBuilder
from dayu.host._run_state_store import (
    AttemptLeaseStore,
    AttemptStateStore,
    RunStateStore,
)
from dayu.host._timeline_projection import TimelineProjectionObserver
from dayu.host._tool_runtime import (
    InMemoryToolRuntime,
    ToolRuntimeToolExecutor,
)
from dayu.host._tool_trace_jsonl_sink import ToolTraceJsonlSink
from dayu.host._tool_trace_projection import ToolTraceObserver


class _SystemUtcClock:
    """系统级 UTC clock 默认实现。

    生产装配默认使用本实现; 测试 / smoke 可替换为 fake clock。

    :returns: timezone-aware UTC ``datetime``。
    """

    def now(self) -> datetime:
        """返回当前 timezone-aware UTC 时间。

        :returns: timezone-aware UTC datetime。
        :raises Exception: 不主动抛出异常。
        """

        return datetime.now(tz=timezone.utc)


@dataclass(frozen=True, slots=True)
class DurableHarnessConfig:
    """durable harness 装配配置。

    :param database_path: SQLite 路径（``":memory:"`` 用于测试）。
    :param tool_trace_path: P7 tool trace JSONL 输出根目录；``None`` 或空字
        符串视为未配置 trace，不装配 :class:`ToolTraceObserver`，文件系统
        也不会被创建。
    :param attempt_lease_config: P8-S3 attempt lease 治理配置；默认使用
        :data:`DEFAULT_ATTEMPT_LEASE_CONFIG`。装配层是 lease TTL / renew
        interval 真源, public ``start_run`` 不暴露 TTL。
    """

    database_path: str
    tool_trace_path: str | None = None
    attempt_lease_config: AttemptLeaseConfig = DEFAULT_ATTEMPT_LEASE_CONFIG


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
    :param tool_trace_observer: P7 tool trace observer；未配置 trace 时为
        ``None``。
    :param run_state_store: Run minimal state durable store。
    :param attempt_state_store: Attempt minimal state durable store。
    :param attempt_lease_store: P8-S3 owner lease CAS store。
    :param attempt_supervisor: P8-S3 attempt 生命周期编排器；
        :class:`LocalRunHarness` 通过它薄委托 acquire / renew / 收口。
    :param attempt_lease_config: 当前装配生效的 :class:`AttemptLeaseConfig`。
    :param close: 释放 storage 的回调。
    """

    harness: LocalRunHarness
    storage: HostStorage
    event_store: DurableRunEventStore
    coordinator: ProjectionCoordinator
    memory_store: ConversationMemoryStore
    timeline_observer: TimelineProjectionObserver
    audit_observer: AuditProjectionObserver
    tool_trace_observer: ToolTraceObserver | None
    run_state_store: RunStateStore
    attempt_state_store: AttemptStateStore
    attempt_lease_store: AttemptLeaseStore
    attempt_supervisor: AttemptSupervisor
    attempt_lease_config: AttemptLeaseConfig
    close: Callable[[], None]

    async def startup_reconcile(self) -> None:
        """启动 / 重新装配后显式追平 read model。

        进程崩溃可能停在 terminal 事件已持久化、但 ``coordinator.drain``
        尚未执行的瞬间。重启后 EventLog 中 terminal 与 RunResult 都在，
        但 memory / timeline / audit checkpoint 仍落后。本方法委派
        :meth:`ProjectionCoordinator.startup_reconcile`，在 caller 的
        async 上下文内串行 drain 至 ``CAUGHT_UP``，不引入新 event loop /
        线程，也不与 terminal 后的 ``drain()`` 重入冲突。

        :returns: 无返回值。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        await self.coordinator.startup_reconcile()


def build_durable_harness(
    *,
    config: DurableHarnessConfig,
    executor: ToolExecutor | None = None,
    memory_store: ConversationMemoryStore | None = None,
    proxy: WorkerProxy | None = None,
    clock: UtcClock | None = None,
) -> DurableHarnessBundle:
    """装配 durable :class:`LocalRunHarness`。

    :param config: durable harness 装配配置。
    :param executor: 自定义 ToolExecutor；默认为 ``_NoopToolExecutor``。
    :param memory_store: 自定义对话 memory store；默认为
        :class:`InMemoryConversationMemoryStore`。
    :param proxy: 自定义 WorkerProxy；默认装配本地 EngineWorker + LocalProxy。
        smoke / 测试可注入 stub proxy 跳过真实 Engine。
    :param clock: 可选 :class:`UtcClock`; 默认使用 :class:`_SystemUtcClock`,
        测试 / smoke 可注入 fake clock 推进 lease 过期, 不依赖真实 sleep。
    :returns: :class:`DurableHarnessBundle`。
    :raises Exception: 装配失败时透传底层异常。
    """

    storage = HostStorage(database_path=config.database_path)
    event_store = open_durable_event_store(storage)
    actual_clock: UtcClock = clock if clock is not None else _SystemUtcClock()

    actual_memory: ConversationMemoryStore = (
        memory_store if memory_store is not None
        else InMemoryConversationMemoryStore()
    )
    memory_observer = MemoryProjectionObserver(memory_store=actual_memory)
    timeline_observer = TimelineProjectionObserver()
    audit_observer = AuditProjectionObserver()

    tool_trace_observer: ToolTraceObserver | None = None
    if config.tool_trace_path is not None and config.tool_trace_path != "":
        jsonl_sink = ToolTraceJsonlSink(
            root_path=Path(config.tool_trace_path)
        )
        tool_trace_observer = ToolTraceObserver(jsonl_sink=jsonl_sink)

    observers: tuple[ObserverSink, ...]
    if tool_trace_observer is None:
        observers = (memory_observer, timeline_observer, audit_observer)
    else:
        observers = (
            memory_observer,
            timeline_observer,
            audit_observer,
            tool_trace_observer,
        )

    projection_store = ProjectionStore(storage=storage)
    coordinator = ProjectionCoordinator(
        storage=storage,
        event_store=event_store,
        projection_store=projection_store,
        observers=observers,
    )

    actual_executor: ToolExecutor = (
        executor if executor is not None else _NoopToolExecutor()
    )
    runtime = InMemoryToolRuntime(
        executor=actual_executor,
        event_store=event_store,
    )
    run_state_store = RunStateStore(storage=storage)
    attempt_state_store = AttemptStateStore(storage=storage)
    attempt_lease_store = AttemptLeaseStore(
        storage=storage, clock=actual_clock
    )
    attempt_supervisor = AttemptSupervisor(
        storage=storage,
        lease_store=attempt_lease_store,
        lease_config=config.attempt_lease_config,
        clock=actual_clock,
    )
    actual_proxy: WorkerProxy = (
        proxy if proxy is not None
        else LocalProxy(worker=EngineWorker(ToolRuntimeToolExecutor(runtime)))
    )
    tool_trace_enabled = tool_trace_observer is not None
    harness = LocalRunHarness(
        proxy=actual_proxy,
        event_store=event_store,
        tool_runtime=runtime,
        memory_store=actual_memory,
        coordinator=coordinator,
        attempt_state_store=attempt_state_store,
        attempt_supervisor=attempt_supervisor,
        storage=storage,
        tool_trace_context_fact_enabled=tool_trace_enabled,
        run_input_context_fact_builder=(
            RunInputContextFactBuilder() if tool_trace_enabled else None
        ),
    )

    return DurableHarnessBundle(
        harness=harness,
        storage=storage,
        event_store=event_store,
        coordinator=coordinator,
        memory_store=actual_memory,
        timeline_observer=timeline_observer,
        audit_observer=audit_observer,
        tool_trace_observer=tool_trace_observer,
        run_state_store=run_state_store,
        attempt_state_store=attempt_state_store,
        attempt_lease_store=attempt_lease_store,
        attempt_supervisor=attempt_supervisor,
        attempt_lease_config=config.attempt_lease_config,
        close=storage.close,
    )


__all__ = [
    "DurableHarnessBundle",
    "DurableHarnessConfig",
    "build_durable_harness",
]
