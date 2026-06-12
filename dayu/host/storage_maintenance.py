"""Host storage maintenance public facade。

本 slice 只实现只读 ``report_storage_usage``。本模块不提供 checkpoint、
artifact root 扫描、orphan proof 或删除入口。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dayu.host.api import HostApiError, HostApiErrorCode
from dayu.host.command import HostCommandHandle
from dayu.host.durable.storage_lifecycle import (
    HostStorageUsageReport,
    read_storage_usage,
)
from dayu.host.durable.transaction import HostTransaction


def report_storage_usage(host: HostCommandHandle) -> HostStorageUsageReport:
    """读取当前 Host durable storage usage report。

    :param host: Host command handle。
    :returns: storage usage report。
    :raises dayu.host.api.HostApiError: durable 读取失败或 DB/WAL 文件 stat 失败时抛出。
    """

    try:
        return host._run_read(_ReadStorageUsageOperation(db_path=host._db_path()))
    except OSError as exc:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Storage usage file stat failed",
            retryable=False,
        ) from exc


@dataclass(frozen=True, slots=True)
class _ReadStorageUsageOperation:
    """storage usage report read transaction body。

    :param db_path: Host durable SQLite DB 文件路径。
    """

    db_path: Path

    def __call__(self, transaction: HostTransaction) -> HostStorageUsageReport:
        """执行 storage usage report durable reader。

        :param transaction: 当前 Host read transaction。
        :returns: storage usage report。
        """

        return read_storage_usage(transaction, db_path=self.db_path)


__all__ = [
    "HostStorageUsageReport",
    "report_storage_usage",
]
