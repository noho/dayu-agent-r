"""Host P6 event observer / projection runner。

本模块定义 P6 最小 observer / sink 协议、batch runner、retry policy 与
lag 计算。observer 入参是已 append 的 durable RunEvent envelope，不消费
EngineEvent iterator；不实现完整 MQ / claim / lease。

设计要点：

- ``ObserverSink`` 协议：观察者负责 sink 写入，写入必须幂等。在同一 UoW
  内 sink 写入与 checkpoint 前进必须一起提交。``process`` 为 async 协议：
  observer 内部允许 ``await`` 异步 store / sink，不再需要 sync-async
  桥接。
- ``NonTransactionalObserverSink`` 协议：只允许非 required observer 使用。
  sink I/O 先在 SQLite checkpoint transaction 外完成，成功后再用短事务推
  进 checkpoint。sink 成功但 checkpoint 失败时允许后续重放。
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
from typing import Protocol, TypeAlias, runtime_checkable

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
_ERROR_CODE_RETRYABLE: str = "retryable"
_ERROR_CODE_NON_REQUIRED_PREFIX: str = "non_required"
_ERROR_CODE_NON_REQUIRED_IO_PREFIX: str = "non_required_io"
_ERROR_CODE_NON_REQUIRED_CHECKPOINT_PREFIX: str = "non_required_checkpoint"


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


@runtime_checkable
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

    async def process(
        self,
        *,
        tx: HostStorageTransaction,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        """在事务内处理一批事件。

        协议为 async：observer 与 projection checkpoint 推进必须在同一个
        ``HostStorage.transaction()`` 内完成；async 协议消除 P6/P7 内
        sync-async 桥接（例如 memory store 的 thread + new loop bridge），
        允许 observer 直接 ``await`` 其下游异步 store / sink。

        :param tx: 当前 :class:`HostStorageTransaction`。
        :param batch: 事件 envelope 元组，按 position 升序。
        :returns: 无返回值。
        :raises RetryableProjectionError: 可重试失败。
        :raises Exception: 其它失败标记 BLOCKED_FAILED。
        """
        ...


@runtime_checkable
class NonTransactionalObserverSink(Protocol):
    """非事务 observer / sink 写入协议。

    该协议只用于 ``descriptor.required == False`` 的 observer。实现方负责
    在 checkpoint transaction 外完成幂等 sink I/O；coordinator 会在 I/O
    成功后开启短事务推进 checkpoint。若 checkpoint 推进失败，下一轮 drain
    会重放同一 batch，因此 sink 必须允许重复写入并通过自身 record 的
    ``idempotency_key`` 等稳定字段支持读侧去重。
    """

    @property
    def descriptor(self) -> ObserverDescriptor:
        """Observer 元数据。

        :returns: :class:`ObserverDescriptor`。
        :raises Exception: 不主动抛出异常。
        """
        ...

    async def process_non_transactional(
        self,
        *,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        """在 checkpoint transaction 外处理一批事件。

        :param batch: 事件 envelope 元组，按 position 升序。
        :returns: 无返回值。
        :raises RetryableProjectionError: 可重试失败。
        :raises Exception: 其它失败标记 BLOCKED_FAILED。
        """
        ...


ObserverRuntimeSink: TypeAlias = ObserverSink | NonTransactionalObserverSink


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
    observers: tuple[ObserverRuntimeSink, ...]
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

    async def startup_reconcile(self) -> tuple[ProjectionCheckpoint, ...]:
        """启动 / 重新装配后追平 read model。

        进程崩溃在 terminal 事件持久化成功之后、``drain()`` 执行之前时，
        EventLog 已含 terminal 与 RunResult，但 observer checkpoint 仍落
        后。Host durable 装配完成后，调用方必须在自己的 async 上下文中
        显式 ``await`` 本方法；P6 不在同步 ``build_durable_harness()``
        内自动执行恢复。方法会按当前 checkpoint 与 EventLog 比较，对
        落后的 observer 触发 ``drain()`` 推进至 ``CAUGHT_UP``。本方法
        语义与 ``drain()`` 一致；保留独立入口是为了让调用方从语义上
        区分“启动追平”与“terminal 后追平”。

        :returns: 每个 observer 推进后的最新 checkpoint。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        return await self.drain()

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
        observer: ObserverRuntimeSink,
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
        observer: ObserverRuntimeSink,
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
            after = None if checkpoint is None else checkpoint.last_success_position
            rows = self.event_store.fetch_events_by_position(after=after, limit=self.batch_limit)
            if not rows:
                # 已经追平。
                if checkpoint is not None and (checkpoint.status is not ObserverStatus.CAUGHT_UP):
                    async with self.storage.transaction() as tx:
                        self.projection_store.advance_success(
                            tx=tx,
                            observer_id=desc.observer_id,
                            projection_name=desc.projection_name,
                            schema_version=desc.schema_version,
                            position=checkpoint.last_success_position or GlobalEventPosition(value=0),
                            status=ObserverStatus.CAUGHT_UP,
                        )
                refreshed = self.projection_store.get(
                    observer_id=desc.observer_id,
                    projection_name=desc.projection_name,
                    schema_version=desc.schema_version,
                )
                if refreshed is None:
                    raise RuntimeError(
                        f"projection checkpoint disappeared after caught_up: " f"observer={desc.observer_id}"
                    )
                return refreshed
            envelopes = tuple(ProjectionEventEnvelope(position=position, event=event) for position, event in rows)
            last_position = envelopes[-1].position
            if not desc.required and isinstance(observer, NonTransactionalObserverSink):
                failure_checkpoint = await self._process_non_transactional_batch(
                    observer=observer,
                    desc=desc,
                    envelopes=envelopes,
                    last_position=last_position,
                )
            elif isinstance(observer, ObserverSink):
                failure_checkpoint = await self._process_transactional_batch(
                    observer=observer,
                    desc=desc,
                    envelopes=envelopes,
                    last_position=last_position,
                )
            else:
                failure_checkpoint = await self._record_batch_failure(
                    desc=desc,
                    attempted_position=last_position,
                    status=ObserverStatus.BLOCKED_FAILED,
                    error_code="observer_protocol_mismatch",
                    error_message=(
                        "observer must implement ObserverSink when required or "
                        "when non-transactional protocol is unavailable"
                    ),
                    exc=TypeError("observer protocol mismatch"),
                )
            if failure_checkpoint is not None:
                return failure_checkpoint

    async def _process_transactional_batch(
        self,
        *,
        observer: ObserverSink,
        desc: ObserverDescriptor,
        envelopes: tuple[ProjectionEventEnvelope, ...],
        last_position: GlobalEventPosition,
    ) -> ProjectionCheckpoint | None:
        """在单个 SQLite transaction 内执行 observer 与 checkpoint 推进。

        :param observer: Observer / sink。
        :param desc: observer 描述符。
        :param envelopes: 当前 batch。
        :param last_position: batch 最后一条事件位置。
        :returns: 失败时返回刷新后的 checkpoint，成功时返回 ``None``。
        :raises RuntimeError: 失败记录后 checkpoint 行消失时抛出。
        """

        try:
            async with self.storage.transaction() as tx:
                await observer.process(tx=tx, batch=envelopes)
                self.projection_store.advance_success(
                    tx=tx,
                    observer_id=desc.observer_id,
                    projection_name=desc.projection_name,
                    schema_version=desc.schema_version,
                    position=last_position,
                    status=ObserverStatus.RUNNING,
                )
        except RetryableProjectionError as exc:
            return await self._record_batch_failure(
                desc=desc,
                attempted_position=last_position,
                status=ObserverStatus.RETRYABLE_FAILED,
                error_code=_ERROR_CODE_RETRYABLE,
                error_message=str(exc),
                exc=exc,
            )
        except Exception as exc:  # noqa: BLE001
            return await self._record_batch_failure(
                desc=desc,
                attempted_position=last_position,
                status=ObserverStatus.BLOCKED_FAILED,
                error_code=type(exc).__name__,
                error_message=str(exc),
                exc=exc,
            )
        return None

    async def _process_non_transactional_batch(
        self,
        *,
        observer: NonTransactionalObserverSink,
        desc: ObserverDescriptor,
        envelopes: tuple[ProjectionEventEnvelope, ...],
        last_position: GlobalEventPosition,
    ) -> ProjectionCheckpoint | None:
        """在 transaction 外执行非 required sink I/O，再短事务推进 checkpoint。

        :param observer: 非事务 observer / sink。
        :param desc: observer 描述符。
        :param envelopes: 当前 batch。
        :param last_position: batch 最后一条事件位置。
        :returns: 失败时返回刷新后的 checkpoint，成功时返回 ``None``。
        :raises RuntimeError: 失败记录后 checkpoint 行消失时抛出。
        """

        try:
            await observer.process_non_transactional(batch=envelopes)
        except RetryableProjectionError as exc:
            return await self._record_batch_failure(
                desc=desc,
                attempted_position=last_position,
                status=ObserverStatus.RETRYABLE_FAILED,
                error_code=f"{_ERROR_CODE_NON_REQUIRED_IO_PREFIX}:retryable",
                error_message=str(exc),
                exc=exc,
            )
        except Exception as exc:  # noqa: BLE001
            return await self._record_batch_failure(
                desc=desc,
                attempted_position=last_position,
                status=ObserverStatus.BLOCKED_FAILED,
                error_code=f"{_ERROR_CODE_NON_REQUIRED_IO_PREFIX}:{type(exc).__name__}",
                error_message=str(exc),
                exc=exc,
            )

        try:
            async with self.storage.transaction() as tx:
                self.projection_store.advance_success(
                    tx=tx,
                    observer_id=desc.observer_id,
                    projection_name=desc.projection_name,
                    schema_version=desc.schema_version,
                    position=last_position,
                    status=ObserverStatus.RUNNING,
                )
        except Exception as exc:  # noqa: BLE001
            return await self._record_batch_failure(
                desc=desc,
                attempted_position=last_position,
                status=ObserverStatus.BLOCKED_FAILED,
                error_code=f"{_ERROR_CODE_NON_REQUIRED_CHECKPOINT_PREFIX}:{type(exc).__name__}",
                error_message=str(exc),
                exc=exc,
            )
        return None

    async def _record_batch_failure(
        self,
        *,
        desc: ObserverDescriptor,
        attempted_position: GlobalEventPosition,
        status: ObserverStatus,
        error_code: str,
        error_message: str,
        exc: Exception,
    ) -> ProjectionCheckpoint:
        """记录 observer batch 失败并返回刷新后的 checkpoint。

        :param desc: observer 描述符。
        :param attempted_position: 本次尝试的最后事件位置。
        :param status: 要写入的失败状态。
        :param error_code: 稳定错误码。
        :param error_message: 错误消息。
        :param exc: 原始异常，仅用于日志。
        :returns: 刷新后的 :class:`ProjectionCheckpoint`。
        :raises RuntimeError: 失败记录后 checkpoint 行消失时抛出。
        """

        stored_error_code = _observer_scoped_error_code(desc=desc, error_code=error_code)
        async with self.storage.transaction() as tx:
            self.projection_store.record_failure(
                tx=tx,
                observer_id=desc.observer_id,
                projection_name=desc.projection_name,
                schema_version=desc.schema_version,
                attempted_position=attempted_position,
                status=status,
                error_code=stored_error_code,
                error_message=error_message,
            )
        if status is ObserverStatus.RETRYABLE_FAILED:
            _LOGGER.warning(
                "host.observer.retryable_failure observer=%s required=%s " "position=%s error_code=%s error=%s",
                desc.observer_id,
                desc.required,
                attempted_position.value,
                stored_error_code,
                exc,
            )
        else:
            _LOGGER.error(
                "host.observer.blocked_failure observer=%s required=%s " "position=%s error_code=%s error=%s",
                desc.observer_id,
                desc.required,
                attempted_position.value,
                stored_error_code,
                exc,
            )
        refreshed = self.projection_store.get(
            observer_id=desc.observer_id,
            projection_name=desc.projection_name,
            schema_version=desc.schema_version,
        )
        if refreshed is None:
            raise RuntimeError(f"projection checkpoint disappeared after failure: " f"observer={desc.observer_id}")
        return refreshed


def _observer_scoped_error_code(
    *,
    desc: ObserverDescriptor,
    error_code: str,
) -> str:
    """按 observer required 属性归一化失败错误码。

    required observer 保持既有错误码；非 required observer 使用
    ``non_required`` 前缀，让 checkpoint failure record 能与 required
    failure record 区分。已经带非 required 子类前缀的错误码保持不变。

    :param desc: observer 描述符。
    :param error_code: 原始错误码。
    :returns: 按 required 属性归一化后的错误码。
    :raises Exception: 不主动抛出异常。
    """

    if desc.required:
        return error_code
    if error_code.startswith(f"{_ERROR_CODE_NON_REQUIRED_PREFIX}_"):
        return error_code
    if error_code.startswith(f"{_ERROR_CODE_NON_REQUIRED_PREFIX}:"):
        return error_code
    return f"{_ERROR_CODE_NON_REQUIRED_PREFIX}:{error_code}"


__all__ = [
    "NonTransactionalObserverSink",
    "ObserverDescriptor",
    "ObserverSink",
    "ObserverRuntimeSink",
    "ProjectionCoordinator",
    "ProjectionEventEnvelope",
    "RetryableProjectionError",
]
