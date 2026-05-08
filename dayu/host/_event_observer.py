"""Host P6 event observer / projection runner。

本模块定义 P6 最小 observer / sink 协议、batch runner、retry policy 与
lag 计算。observer 入参是已 append 的 durable RunEvent envelope，不消费
EngineEvent iterator；不实现完整 MQ / claim / lease。

设计要点：

- ``ObserverSink`` 协议：观察者负责 sink 写入，写入必须幂等。在同一 UoW
  内 sink 写入与 checkpoint 前进必须一起提交。
- ``ProjectionCoordinator``：组合一组 observer 与 :class:`ProjectionStore`，
  按 global event position 顺序拉取 batch，逐个调用 sink 处理。
- 失败语义：sink 抛 ``RetryableProjectionError`` 时记录 ``RETRYABLE_FAILED``，
  抛其它异常记录 ``BLOCKED_FAILED``；checkpoint 不前进。
- 成功语义：sink 处理完毕后 checkpoint 推进到 batch 最后一个事件的全局
  position。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Protocol

from dayu.host._durable_event_store import DurableRunEventStore
from dayu.host._host_storage_transaction import (
    HostStorage,
    HostStorageTransaction,
)
from dayu.host._internal_contracts import (
    GlobalEventPosition,
    ObserverStatus,
    ProjectionCheckpoint,
)
from dayu.host._projection_store import ProjectionStore
from dayu.host.contracts import RunEvent

_LOGGER: logging.Logger = logging.getLogger(__name__)
_DEFAULT_BATCH_LIMIT: int = 64


class RetryableProjectionError(Exception):
    """observer / sink 抛出的可重试错误。"""


@dataclass(frozen=True, slots=True)
class ProjectionEventEnvelope:
    """Observer 接收的事件包装。

    :param position: 事件全局位置。
    :param event: RunEvent。
    """

    position: GlobalEventPosition
    event: RunEvent


@dataclass(frozen=True, slots=True)
class ObserverDescriptor:
    """Observer 元数据。

    :param observer_id: 稳定 id。
    :param projection_name: projection 名。
    :param schema_version: read model schema 版本。
    :param required: 是否 required projection。
    """

    observer_id: str
    projection_name: str
    schema_version: int
    required: bool


class ObserverSink(Protocol):
    """Observer / sink 写入协议。

    实现必须保证 ``process`` 对同一 ``ProjectionEventEnvelope`` 序列重复
    调用幂等：sink 写入与 checkpoint 前进同事务提交。
    """

    @property
    def descriptor(self) -> ObserverDescriptor:
        """Observer 元数据。

        :returns: :class:`ObserverDescriptor`。
        :raises Exception: 不主动抛出异常。
        """
        ...

    def process(
        self,
        *,
        tx: HostStorageTransaction,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        """在事务内处理一批事件。

        :param tx: 当前 :class:`HostStorageTransaction`。
        :param batch: 事件 envelope 元组，按 position 升序。
        :returns: 无返回值。
        :raises RetryableProjectionError: 可重试失败。
        :raises Exception: 其它失败标记 BLOCKED_FAILED。
        """
        ...


@dataclass(slots=True)
class ProjectionCoordinator:
    """组合 observer + projection store + durable event store 的 batch runner。

    :param storage: 共享 :class:`HostStorage`。
    :param event_store: durable event store，用于按 position 拉取。
    :param projection_store: projection checkpoint store。
    :param observers: 注册的 observer 列表。
    :param batch_limit: 每次拉取的最大条数。
    """

    storage: HostStorage
    event_store: DurableRunEventStore
    projection_store: ProjectionStore
    observers: tuple[ObserverSink, ...]
    batch_limit: int = _DEFAULT_BATCH_LIMIT
    _drain_lock: asyncio.Lock = field(
        default_factory=asyncio.Lock,
        init=False,
    )

    async def initialize(self) -> None:
        """确保所有 observer 都有 checkpoint 行。

        :returns: 无返回值。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        async with self.storage.transaction() as tx:
            for observer in self.observers:
                desc = observer.descriptor
                self.projection_store.ensure(
                    tx=tx,
                    observer_id=desc.observer_id,
                    projection_name=desc.projection_name,
                    schema_version=desc.schema_version,
                )

    async def drain(self) -> tuple[ProjectionCheckpoint, ...]:
        """对每个 observer 推进到当前最新 position。

        ``_drain_lock`` 防止同一进程内并发 drain 互相干扰：本调用在锁内
        串行执行 ``initialize`` + 逐 observer ``run_once``，避免重入。

        :returns: 每个 observer 推进后的最新 checkpoint。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        async with self._drain_lock:
            await self.initialize()
            snapshots: list[ProjectionCheckpoint] = []
            for observer in self.observers:
                checkpoint = await self._run_once_locked(observer=observer)
                snapshots.append(checkpoint)
            return tuple(snapshots)

    async def run_once(
        self,
        *,
        observer: ObserverSink,
    ) -> ProjectionCheckpoint:
        """对单个 observer 执行一次 drain 直到追平。

        :param observer: Observer / sink。
        :returns: 最终 checkpoint。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        async with self._drain_lock:
            return await self._run_once_locked(observer=observer)

    async def _run_once_locked(
        self,
        *,
        observer: ObserverSink,
    ) -> ProjectionCheckpoint:
        """``_drain_lock`` 内的 run_once 实现。

        :param observer: Observer / sink。
        :returns: 最终 checkpoint。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        desc = observer.descriptor
        while True:
            checkpoint = self.projection_store.get(
                observer_id=desc.observer_id,
                projection_name=desc.projection_name,
                schema_version=desc.schema_version,
            )
            after = (
                None if checkpoint is None
                else checkpoint.last_success_position
            )
            rows = self.event_store.fetch_events_by_position(
                after=after, limit=self.batch_limit
            )
            if not rows:
                # 已经追平。
                if checkpoint is not None and (
                    checkpoint.status is not ObserverStatus.CAUGHT_UP
                ):
                    async with self.storage.transaction() as tx:
                        self.projection_store.advance_success(
                            tx=tx,
                            observer_id=desc.observer_id,
                            projection_name=desc.projection_name,
                            schema_version=desc.schema_version,
                            position=checkpoint.last_success_position
                            or GlobalEventPosition(value=0),
                            status=ObserverStatus.CAUGHT_UP,
                        ) if checkpoint.last_success_position is not None else None
                refreshed = self.projection_store.get(
                    observer_id=desc.observer_id,
                    projection_name=desc.projection_name,
                    schema_version=desc.schema_version,
                )
                if refreshed is None:
                    raise RuntimeError(
                        f"projection checkpoint disappeared after caught_up: "
                        f"observer={desc.observer_id}"
                    )
                return refreshed
            envelopes = tuple(
                ProjectionEventEnvelope(position=position, event=event)
                for position, event in rows
            )
            last_position = envelopes[-1].position
            try:
                async with self.storage.transaction() as tx:
                    observer.process(tx=tx, batch=envelopes)
                    self.projection_store.advance_success(
                        tx=tx,
                        observer_id=desc.observer_id,
                        projection_name=desc.projection_name,
                        schema_version=desc.schema_version,
                        position=last_position,
                        status=ObserverStatus.RUNNING,
                    )
            except RetryableProjectionError as exc:
                async with self.storage.transaction() as tx:
                    self.projection_store.record_failure(
                        tx=tx,
                        observer_id=desc.observer_id,
                        projection_name=desc.projection_name,
                        schema_version=desc.schema_version,
                        attempted_position=last_position,
                        status=ObserverStatus.RETRYABLE_FAILED,
                        error_code="retryable",
                        error_message=str(exc),
                    )
                _LOGGER.warning(
                    "host.observer.retryable_failure observer=%s position=%s "
                    "error=%s",
                    desc.observer_id,
                    last_position.value,
                    exc,
                )
                refreshed = self.projection_store.get(
                    observer_id=desc.observer_id,
                    projection_name=desc.projection_name,
                    schema_version=desc.schema_version,
                )
                if refreshed is None:
                    raise RuntimeError(
                        f"projection checkpoint disappeared after retryable: "
                        f"observer={desc.observer_id}"
                    )
                return refreshed
            except Exception as exc:  # noqa: BLE001
                async with self.storage.transaction() as tx:
                    self.projection_store.record_failure(
                        tx=tx,
                        observer_id=desc.observer_id,
                        projection_name=desc.projection_name,
                        schema_version=desc.schema_version,
                        attempted_position=last_position,
                        status=ObserverStatus.BLOCKED_FAILED,
                        error_code=type(exc).__name__,
                        error_message=str(exc),
                    )
                _LOGGER.error(
                    "host.observer.blocked_failure observer=%s position=%s "
                    "error=%s",
                    desc.observer_id,
                    last_position.value,
                    exc,
                )
                refreshed = self.projection_store.get(
                    observer_id=desc.observer_id,
                    projection_name=desc.projection_name,
                    schema_version=desc.schema_version,
                )
                if refreshed is None:
                    raise RuntimeError(
                        f"projection checkpoint disappeared after blocked: "
                        f"observer={desc.observer_id}"
                    )
                return refreshed


__all__ = [
    "ObserverDescriptor",
    "ObserverSink",
    "ProjectionCoordinator",
    "ProjectionEventEnvelope",
    "RetryableProjectionError",
]
