"""Host P6 audit projection observer。

本模块提供最小 audit read model 示例：把 canonical 事件转换为中性
``AuditRecord`` 并按时间顺序累积，用于演示 observer 的 checkpoint /
retry / lag 机制。

audit 观察者只读取 RunEvent 元数据（run_id、cursor、type、source、
occurred_at、source_engine_event_id），不复制 RunEventData payload，避
免敏感字段流入审计读模型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from dayu.host._event_observer import (
    ObserverDescriptor,
    ProjectionEventEnvelope,
)
from dayu.host._host_storage_transaction import HostStorageTransaction
from dayu.host._internal_contracts import GlobalEventPosition
from dayu.host.contracts import (
    RunEventKind,
    RunEventSource,
    RunEventType,
)

_OBSERVER_ID: str = "host_audit_projection"
_PROJECTION_NAME: str = "run_audit"
_SCHEMA_VERSION: int = 1


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """审计记录。

    :param position: 事件全局位置。
    :param run_id: Run id。
    :param session_id: 会话 id。
    :param sequence: 同一 run 内 cursor sequence。
    :param event_type: RunEvent 类型。
    :param source: RunEvent 来源。
    :param occurred_at: 事件发生时间。
    :param source_engine_event_id: 来源 EngineEvent id。
    """

    position: GlobalEventPosition
    run_id: str
    session_id: str
    sequence: int
    event_type: RunEventType
    source: RunEventSource
    occurred_at: datetime
    source_engine_event_id: str | None


@dataclass(slots=True)
class AuditProjectionObserver:
    """audit read model observer。

    :param _records: 内部状态，按全局 position 升序累积。
    :param _seen_positions: 已写入的 position 集合，用于幂等。
    """

    _records: list[AuditRecord] = field(default_factory=list, init=False)
    _seen_positions: set[int] = field(default_factory=set, init=False)

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

    def process(
        self,
        *,
        tx: HostStorageTransaction,
        batch: tuple[ProjectionEventEnvelope, ...],
    ) -> None:
        """记录 canonical 事件审计条目。

        :param tx: 当前事务（audit read model 不写 SQL）。
        :param batch: 事件 envelope 元组。
        :returns: 无返回值。
        :raises Exception: 投影失败时透传。
        """

        del tx
        for envelope in batch:
            event = envelope.event
            if event.kind is not RunEventKind.CANONICAL:
                continue
            position_value = envelope.position.value
            if position_value in self._seen_positions:
                continue
            self._seen_positions.add(position_value)
            self._records.append(
                AuditRecord(
                    position=envelope.position,
                    run_id=event.run_id,
                    session_id=event.session_id,
                    sequence=event.cursor.sequence,
                    event_type=event.type,
                    source=event.source,
                    occurred_at=event.occurred_at,
                    source_engine_event_id=event.source_engine_event_id,
                )
            )

    def list_records(self) -> tuple[AuditRecord, ...]:
        """读取审计记录。

        :returns: 按 position 升序的记录元组。
        :raises Exception: 不主动抛出异常。
        """

        return tuple(self._records)


__all__ = [
    "AuditProjectionObserver",
    "AuditRecord",
]
