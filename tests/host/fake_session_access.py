"""scheduler 单测使用的显式 Session access fake。

本 fake 不模拟 native mutex 或 public attachment factory；它只让 scheduler
单测显式声明哪些 Session 可取得真实 ``SessionWorkLease`` 对象，并严格维护
lease 计数。production 构造没有默认 access port。
"""

from __future__ import annotations

from dayu.host.api import HostSessionAccessMode
from dayu.host.session_attachment import (
    HostSessionAttachmentRegistry,
    SessionWorkLease,
    _AttachmentLifecycleState,
    _AttachmentRecord,
    _SessionLeaseKind,
)


class ExplicitFakeSessionAccess(HostSessionAttachmentRegistry):
    """返回真实 ``SessionWorkLease`` 的 scheduler 显式 fake access port。

    :param allowed_session_ids: 可取得 lease 的 Session 集合；``None`` 表示
        测试显式选择任意非空 Session 均允许。
    """

    __slots__ = ("_allowed_session_ids", "_fake_records")

    def __init__(self, *, allowed_session_ids: frozenset[str] | None) -> None:
        """初始化 fake access truth 与空 record index。

        :param allowed_session_ids: 允许的 Session id 集合；``None`` 表示全部。
        :returns: ``None``。
        :raises ValueError: 集合中包含空 Session id 时抛出。
        """

        if allowed_session_ids is not None and any(
            session_id.strip() == "" for session_id in allowed_session_ids
        ):
            raise ValueError("allowed_session_ids cannot contain empty id")
        self._allowed_session_ids = allowed_session_ids
        self._fake_records: dict[str, _AttachmentRecord] = {}

    def try_acquire_new_work_lease(
        self,
        session_id: str,
    ) -> SessionWorkLease | None:
        """按显式 allowlist 返回真实 work lease。

        :param session_id: scheduler 请求的 Session id。
        :returns: 允许时返回真实 ``SessionWorkLease``，否则返回 ``None``。
        :raises ValueError: Session id 为空时抛出。
        """

        if session_id.strip() == "":
            raise ValueError("session_id must be non-empty")
        if (
            self._allowed_session_ids is not None
            and session_id not in self._allowed_session_ids
        ):
            return None
        record = self._fake_records.get(session_id)
        if record is None:
            record = _AttachmentRecord(
                session_id=session_id,
                access_mode=HostSessionAccessMode.READ_WRITE,
                state=_AttachmentLifecycleState.ACTIVE,
                mutex_handle=None,
            )
            self._fake_records[session_id] = record
        record.new_work_lease_count += 1
        record.new_work_drained.clear()
        return SessionWorkLease(
            registry=self,
            record=record,
            kind=_SessionLeaseKind.NEW_WORK,
        )

    def active_read_write_session_ids(self) -> tuple[str, ...]:
        """返回已经被测试请求过且仍允许的 Session id 快照。

        :returns: 稳定排序的 Session id 元组。
        :raises Exception: 不主动抛出异常。
        """

        return tuple(sorted(self._fake_records))

    def require_work_lease(self, session_id: str) -> SessionWorkLease:
        """为 direct pre-start 单测取得必须存在的真实 lease。

        :param session_id: 目标 Session id。
        :returns: 真实 work lease。
        :raises RuntimeError: Session 不在 fake allowlist 时抛出。
        """

        lease = self.try_acquire_new_work_lease(session_id)
        if lease is None:
            raise RuntimeError("fake Session access rejected required lease")
        return lease

    def _release_lease(
        self,
        record: _AttachmentRecord,
        kind: _SessionLeaseKind,
    ) -> None:
        """接收真实 ``SessionWorkLease`` 的幂等 release callback。

        :param record: lease 对应 fake record。
        :param kind: lease 类别；本 fake 只允许 new-work。
        :returns: ``None``。
        :raises RuntimeError: 类别非法或计数下溢时抛出。
        """

        if kind is not _SessionLeaseKind.NEW_WORK:
            raise RuntimeError("fake Session access only owns new-work leases")
        if record.new_work_lease_count <= 0:
            raise RuntimeError("fake Session work lease count underflow")
        record.new_work_lease_count -= 1
        if record.new_work_lease_count == 0:
            record.new_work_drained.set()


__all__ = ["ExplicitFakeSessionAccess"]
