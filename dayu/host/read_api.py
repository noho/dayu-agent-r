"""Host public read facade。

本模块提供只读 public facade，从 durable Session / Run / queue index truth
构造 snapshot。当前 P4-S2 只实现 Session 读取，不读取 projection、不启动
background worker，也不实现 EventLog stream facade。
"""

from __future__ import annotations

from dataclasses import dataclass

from dayu.host.api import HostApiError, HostApiErrorCode, SessionSnapshot
from dayu.host.command import HostCommandHandle
from dayu.host.durable.state import (
    read_session_by_id,
    read_session_slot_by_session_id,
    session_snapshot_from_rows,
)
from dayu.host.durable.transaction import HostTransaction


def get_session(host: HostCommandHandle, session_id: str) -> SessionSnapshot:
    """读取 Session durable truth，并返回 Session snapshot。

    :param host: Host command handle。
    :param session_id: 目标 Session id。
    :returns: durable truth 生成的 Session snapshot，包含 active Run 与 queued Run 索引。
    :raises HostApiError: handle 已关闭或 Session 不存在时抛出。
    """

    return host._run_read(_GetSessionOperation(session_id=session_id))


@dataclass(frozen=True, slots=True)
class _GetSessionOperation:
    """get_session read transaction body。"""

    session_id: str

    def __call__(self, transaction: HostTransaction) -> SessionSnapshot:
        """执行 get_session 只读事务。

        :param transaction: 当前 Host transaction。
        :returns: Session snapshot。
        :raises HostApiError: Session 不存在时抛出。
        """

        session = read_session_by_id(transaction, self.session_id)
        if session is None:
            raise HostApiError(
                code=HostApiErrorCode.NOT_FOUND,
                message="Session not found",
                retryable=False,
            )
        return session_snapshot_from_rows(
            transaction,
            session,
            read_session_slot_by_session_id(transaction, self.session_id),
        )


__all__ = ["get_session"]
