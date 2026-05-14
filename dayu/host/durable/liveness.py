"""Host instance liveness durable primitive。

本模块只实现当前 Host instance 注册、heartbeat、stopping / stopped 标记和读取。
这些 row 是后续 recovery 的输入之一，但本模块不实现 lease、fencing、takeover、
dispatch join、orphan classifier、Attempt ``LOST`` 或 Run ``RECOVERING``。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from dayu.host.durable.codec import format_utc_timestamp
from dayu.host.durable.errors import (
    HostDurableError,
    HostInstanceIdentityConflictError,
    HostInstanceNotRegisteredError,
)
from dayu.host.durable.schema import TABLE_HOST_INSTANCES
from dayu.host.durable.transaction import HostRow, HostTransaction
from dayu.host.durable._validation import (
    optional_text as _optional_text,
    require_int as _require_int,
    require_non_empty_text as _require_non_empty_text,
    require_optional_non_empty_text as _require_optional_non_empty_text,
    require_text as _require_text,
)


class HostInstanceStatus(StrEnum):
    """Host instance lifecycle 诊断状态。"""

    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    CRASHED_SUSPECTED = "crashed_suspected"


@dataclass(frozen=True, slots=True)
class HostInstanceIdentity:
    """当前 Host instance 身份。

    :param host_instance_id: Host 进程启动时生成的实例标识。
    :param pid: 当前进程 pid。
    :param process_start_token: 当前进程启动指纹。
    :param boot_id: 可选 boot id；不可用时为 ``None``。
    """

    host_instance_id: str
    pid: int
    process_start_token: str
    boot_id: str | None


@dataclass(frozen=True, slots=True)
class HostInstanceRow:
    """已持久化 host instance liveness row。

    :param host_instance_id: Host instance 标识。
    :param pid: 进程 pid。
    :param process_start_token: 进程启动指纹。
    :param boot_id: 可选 boot id。
    :param created_at: 创建时间，固定 UTC 微秒精度 ``Z`` timestamp 文本。
    :param heartbeat_at: 最近 heartbeat 时间，固定 UTC 微秒精度 ``Z`` timestamp 文本。
    :param status: lifecycle 诊断状态。
    """

    host_instance_id: str
    pid: int
    process_start_token: str
    boot_id: str | None
    created_at: str
    heartbeat_at: str
    status: HostInstanceStatus


class HostInstanceLivenessStore:
    """Host instance liveness primitive 的轻量方法集合。

    该类不持有连接、不创建 transaction；所有 mutation 都必须发生在调用方
    传入的 ``HostTransaction`` 中。
    """

    def register_current_instance(
        self, transaction: HostTransaction, identity: HostInstanceIdentity
    ) -> HostInstanceRow:
        """注册当前 Host instance。

        :param transaction: 调用方提供的 Host durable transaction。
        :param identity: 当前 Host instance 身份。
        :returns: 已注册或刷新后的 liveness row。
        :raises HostDurableError: identity 字段无效时抛出。
        :raises HostInstanceIdentityConflictError: 同一 id 已绑定不同进程身份时抛出。
        :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
        """

        return register_current_instance(transaction, identity)

    def heartbeat_current_instance(
        self, transaction: HostTransaction, identity: HostInstanceIdentity
    ) -> HostInstanceRow:
        """刷新当前 Host instance heartbeat。

        :param transaction: 调用方提供的 Host durable transaction。
        :param identity: 当前 Host instance 身份。
        :returns: 刷新后的 liveness row。
        :raises HostInstanceNotRegisteredError: 当前 instance 未注册时抛出。
        :raises HostInstanceIdentityConflictError: 同一 id 已绑定不同进程身份时抛出。
        :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
        """

        return heartbeat_current_instance(transaction, identity)

    def mark_current_instance_stopping(
        self, transaction: HostTransaction, identity: HostInstanceIdentity
    ) -> HostInstanceRow | None:
        """将当前 Host instance 标记为 stopping。

        :param transaction: 调用方提供的 Host durable transaction。
        :param identity: 当前 Host instance 身份。
        :returns: row 存在时返回更新后的 row；不存在时返回 ``None``。
        :raises HostInstanceIdentityConflictError: 同一 id 已绑定不同进程身份时抛出。
        :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
        """

        return mark_current_instance_stopping(transaction, identity)

    def mark_current_instance_stopped(
        self, transaction: HostTransaction, identity: HostInstanceIdentity
    ) -> HostInstanceRow | None:
        """将当前 Host instance 标记为 stopped。

        :param transaction: 调用方提供的 Host durable transaction。
        :param identity: 当前 Host instance 身份。
        :returns: row 存在时返回更新后的 row；不存在时返回 ``None``。
        :raises HostInstanceIdentityConflictError: 同一 id 已绑定不同进程身份时抛出。
        :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
        """

        return mark_current_instance_stopped(transaction, identity)

    def read_host_instance(
        self, transaction: HostTransaction, host_instance_id: str
    ) -> HostInstanceRow | None:
        """读取 host instance row。

        :param transaction: 调用方提供的 Host durable transaction。
        :param host_instance_id: Host instance 标识。
        :returns: 找到时返回 row，否则返回 ``None``。
        :raises HostDurableError: ``host_instance_id`` 为空时抛出。
        """

        return read_host_instance(transaction, host_instance_id)


def register_current_instance(
    transaction: HostTransaction, identity: HostInstanceIdentity
) -> HostInstanceRow:
    """注册或幂等刷新当前 Host instance。

    :param transaction: 调用方提供的 Host durable transaction。
    :param identity: 当前 Host instance 身份。
    :returns: 已注册或刷新后的 liveness row。
    :raises HostDurableError: identity 字段无效时抛出。
    :raises HostInstanceIdentityConflictError: 同一 id 已绑定不同进程身份时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_identity(identity)
    existing = read_host_instance(transaction, identity.host_instance_id)
    now = format_utc_timestamp(datetime.now(UTC))
    if existing is None:
        transaction.execute(
            f"""
            INSERT INTO {TABLE_HOST_INSTANCES} (
              host_instance_id,
              pid,
              process_start_token,
              boot_id,
              created_at,
              heartbeat_at,
              status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity.host_instance_id,
                identity.pid,
                identity.process_start_token,
                identity.boot_id,
                now,
                now,
                HostInstanceStatus.RUNNING.value,
            ),
        )
    else:
        _require_same_identity(existing, identity)
        transaction.execute(
            f"""
            UPDATE {TABLE_HOST_INSTANCES}
            SET heartbeat_at = ?, status = ?
            WHERE host_instance_id = ?
            """,
            (
                now,
                HostInstanceStatus.RUNNING.value,
                identity.host_instance_id,
            ),
        )
    refreshed = read_host_instance(transaction, identity.host_instance_id)
    if refreshed is None:
        raise HostDurableError("Host instance register did not return row")
    return refreshed


def heartbeat_current_instance(
    transaction: HostTransaction, identity: HostInstanceIdentity
) -> HostInstanceRow:
    """刷新当前 Host instance heartbeat。

    :param transaction: 调用方提供的 Host durable transaction。
    :param identity: 当前 Host instance 身份。
    :returns: 刷新后的 liveness row。
    :raises HostInstanceNotRegisteredError: 当前 instance 未注册时抛出。
    :raises HostInstanceIdentityConflictError: 同一 id 已绑定不同进程身份时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_identity(identity)
    existing = read_host_instance(transaction, identity.host_instance_id)
    if existing is None:
        raise HostInstanceNotRegisteredError("Host instance is not registered")
    _require_same_identity(existing, identity)
    now = format_utc_timestamp(datetime.now(UTC))
    transaction.execute(
        f"""
        UPDATE {TABLE_HOST_INSTANCES}
        SET heartbeat_at = ?, status = ?
        WHERE host_instance_id = ? AND process_start_token = ?
        """,
        (
            now,
            HostInstanceStatus.RUNNING.value,
            identity.host_instance_id,
            identity.process_start_token,
        ),
    )
    refreshed = read_host_instance(transaction, identity.host_instance_id)
    if refreshed is None:
        raise HostInstanceNotRegisteredError("Host instance is not registered")
    return refreshed


def mark_current_instance_stopping(
    transaction: HostTransaction, identity: HostInstanceIdentity
) -> HostInstanceRow | None:
    """将当前 Host instance 标记为 stopping。

    :param transaction: 调用方提供的 Host durable transaction。
    :param identity: 当前 Host instance 身份。
    :returns: row 存在时返回更新后的 row；不存在时返回 ``None``。
    :raises HostInstanceIdentityConflictError: 同一 id 已绑定不同进程身份时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    return _mark_current_instance_status(
        transaction, identity, HostInstanceStatus.STOPPING
    )


def mark_current_instance_stopped(
    transaction: HostTransaction, identity: HostInstanceIdentity
) -> HostInstanceRow | None:
    """将当前 Host instance 标记为 stopped。

    :param transaction: 调用方提供的 Host durable transaction。
    :param identity: 当前 Host instance 身份。
    :returns: row 存在时返回更新后的 row；不存在时返回 ``None``。
    :raises HostInstanceIdentityConflictError: 同一 id 已绑定不同进程身份时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    return _mark_current_instance_status(
        transaction, identity, HostInstanceStatus.STOPPED
    )


def read_host_instance(
    transaction: HostTransaction, host_instance_id: str
) -> HostInstanceRow | None:
    """按 Host instance id 读取 liveness row。

    :param transaction: 调用方提供的 Host durable transaction。
    :param host_instance_id: Host instance 标识。
    :returns: 找到时返回 row，否则返回 ``None``。
    :raises HostDurableError: ``host_instance_id`` 为空时抛出。
    """

    _require_non_empty_text(host_instance_id, field_name="host_instance_id")
    row = transaction.fetchone(
        f"""
        SELECT
          host_instance_id,
          pid,
          process_start_token,
          boot_id,
          created_at,
          heartbeat_at,
          status
        FROM {TABLE_HOST_INSTANCES}
        WHERE host_instance_id = ?
        """,
        (host_instance_id,),
    )
    if row is None:
        return None
    return _host_instance_row_from_host_row(row)


def _mark_current_instance_status(
    transaction: HostTransaction,
    identity: HostInstanceIdentity,
    status: HostInstanceStatus,
) -> HostInstanceRow | None:
    """按当前身份更新 lifecycle 诊断状态。

    :param transaction: 调用方提供的 Host durable transaction。
    :param identity: 当前 Host instance 身份。
    :param status: 目标状态。
    :returns: row 存在时返回更新后的 row；不存在时返回 ``None``。
    :raises HostInstanceIdentityConflictError: 同一 id 已绑定不同进程身份时抛出。
    :raises sqlite3.Error: SQLite 写入失败时由 transaction runner 结构化转换。
    """

    _validate_identity(identity)
    existing = read_host_instance(transaction, identity.host_instance_id)
    if existing is None:
        return None
    _require_same_identity(existing, identity)
    now = format_utc_timestamp(datetime.now(UTC))
    transaction.execute(
        f"""
        UPDATE {TABLE_HOST_INSTANCES}
        SET heartbeat_at = ?, status = ?
        WHERE host_instance_id = ? AND process_start_token = ?
        """,
        (
            now,
            status.value,
            identity.host_instance_id,
            identity.process_start_token,
        ),
    )
    return read_host_instance(transaction, identity.host_instance_id)


def _validate_identity(identity: HostInstanceIdentity) -> None:
    """校验 Host instance identity。

    :param identity: 当前 Host instance 身份。
    :returns: ``None``。
    :raises HostDurableError: 任一字段无效时抛出。
    """

    _require_non_empty_text(identity.host_instance_id, field_name="host_instance_id")
    _require_non_empty_text(
        identity.process_start_token, field_name="process_start_token"
    )
    _require_optional_non_empty_text(identity.boot_id, field_name="boot_id")
    if identity.pid <= 0:
        raise HostDurableError("host instance pid must be positive")


def _require_same_identity(
    row: HostInstanceRow, identity: HostInstanceIdentity
) -> None:
    """确认 durable row 属于当前 Host instance 身份。

    :param row: 已持久化 liveness row。
    :param identity: 当前 Host instance 身份。
    :returns: ``None``。
    :raises HostInstanceIdentityConflictError: durable row 身份与当前身份不一致时抛出。
    """

    boot_id_conflicts = (
        row.boot_id is not None
        and identity.boot_id is not None
        and row.boot_id != identity.boot_id
    )
    if (
        row.pid != identity.pid
        or row.process_start_token != identity.process_start_token
        or boot_id_conflicts
    ):
        raise HostInstanceIdentityConflictError(
            "Host instance id already exists with different identity"
        )


def _host_instance_row_from_host_row(row: HostRow) -> HostInstanceRow:
    """把通用 HostRow 转换为 HostInstanceRow。

    :param row: HostTransaction 查询返回的 row。
    :returns: HostInstanceRow。
    :raises HostDurableError: durable row 类型或 enum 值不符合 schema 预期时抛出。
    """

    status_text = _require_text(row.get("status"), field_name="status")
    try:
        status = HostInstanceStatus(status_text)
    except ValueError as exc:
        raise HostDurableError("Host instance row has invalid status") from exc
    return HostInstanceRow(
        host_instance_id=_require_text(
            row.get("host_instance_id"), field_name="host_instance_id"
        ),
        pid=_require_int(row.get("pid"), field_name="pid"),
        process_start_token=_require_text(
            row.get("process_start_token"), field_name="process_start_token"
        ),
        boot_id=_optional_text(row.get("boot_id"), field_name="boot_id"),
        created_at=_require_text(row.get("created_at"), field_name="created_at"),
        heartbeat_at=_require_text(row.get("heartbeat_at"), field_name="heartbeat_at"),
        status=status,
    )

