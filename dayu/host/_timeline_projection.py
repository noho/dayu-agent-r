"""Host P6 timeline projection observer。

本模块提供最小 timeline read model：以 in-memory 字典持有每个 run 的
display-allowed canonical 事件序列，按 cursor sequence 升序排列。
timeline 观察者用于回放、UI 渲染等只读视图，写入幂等。

约束：

- 只投影 ``RunEventKind.CANONICAL``；preview 与诊断派生事实不进入
  timeline。
- 同一 ``(run_id, cursor.sequence)`` 重复出现时按 ``replace`` 处理，保证
  observer 重投幂等。
- timeline 不缓存 RunEventData 之外的状态，调用方按需自行衍生。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dayu.host._event_observer import (
    ObserverDescriptor,
    ProjectionEventEnvelope,
)
from dayu.host._host_storage_transaction import HostStorageTransaction
from dayu.host.contracts import RunEvent, RunEventKind

_OBSERVER_ID: str = "host_timeline_projection"
_PROJECTION_NAME: str = "run_timeline"
_SCHEMA_VERSION: int = 1


@dataclass(slots=True)
class TimelineProjectionObserver:
    """timeline read model observer。

    :param _events_by_run: 内部状态，按 run_id 持有有序事件列表。
    """

    _events_by_run: dict[str, list[RunEvent]] = field(
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
            required=False,
        )

    async def process(
        self,
        *,
        tx: HostStorageTransaction,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        """累计 canonical 事件到内存 timeline。

        协议为 async（P8 起 :class:`ObserverSink` 协议升级为 async）。
        timeline 写入仍是纯内存操作，不需要 await 任何下游；保持
        async 签名以匹配协议。

        :param tx: 当前事务（timeline read model 不写 SQL，但保留接口）。
        :param batch: 事件 envelope 元组。
        :returns: 无返回值。
        :raises Exception: 投影失败时透传。
        """

        del tx
        for envelope in batch:
            event = envelope.event
            if event.kind is not RunEventKind.CANONICAL:
                continue
            self._upsert(event)

    def get_timeline(self, run_id: str) -> tuple[RunEvent, ...]:
        """读取指定 run 的 timeline。

        :param run_id: Run id。
        :returns: 按 sequence 升序的事件元组；不存在返回空元组。
        :raises Exception: 不主动抛出异常。
        """

        events = self._events_by_run.get(run_id)
        if events is None:
            return ()
        return tuple(events)

    def list_runs(self) -> tuple[str, ...]:
        """列出已观察 run id。

        :returns: run id 元组。
        :raises Exception: 不主动抛出异常。
        """

        return tuple(self._events_by_run.keys())

    def _upsert(self, event: RunEvent) -> None:
        """按 cursor.sequence 幂等插入。

        :param event: RunEvent。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        bucket = self._events_by_run.setdefault(event.run_id, [])
        for index, existing in enumerate(bucket):
            if existing.cursor.sequence == event.cursor.sequence:
                bucket[index] = event
                return
            if existing.cursor.sequence > event.cursor.sequence:
                bucket.insert(index, event)
                return
        bucket.append(event)


__all__ = [
    "TimelineProjectionObserver",
]
