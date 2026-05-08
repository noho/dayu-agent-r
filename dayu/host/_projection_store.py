"""Host P6 projection checkpoint store.

本模块在 ``HostStorage`` 之上提供 projection checkpoint 的 durable 查询/
写入入口。checkpoint 写入必须经由 :class:`HostStorageTransaction`，与
sink 写入共享同一事务（at-least-once + 幂等 sink）。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from dayu.host._host_storage_transaction import (
    HostStorage,
    HostStorageTransaction,
)
from dayu.host._internal_contracts import (
    GlobalEventPosition,
    ObserverStatus,
    ProjectionCheckpoint,
)

_ERROR_CHECKPOINT_REGRESSION: str = (
    "projection checkpoint cannot regress last_success_position"
)


@dataclass(slots=True)
class ProjectionStore:
    """Projection checkpoint durable 入口。

    :param storage: 共享 :class:`HostStorage`。
    """

    storage: HostStorage

    def get(
        self,
        *,
        observer_id: str,
        projection_name: str,
        schema_version: int,
    ) -> ProjectionCheckpoint | None:
        """读取 checkpoint。

        :param observer_id: observer id。
        :param projection_name: projection 名。
        :param schema_version: schema 版本。
        :returns: :class:`ProjectionCheckpoint`；不存在为 ``None``。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        rows = self.storage.execute_read(
            """
            SELECT observer_id, projection_name, schema_version,
                last_success_position, last_attempted_position, status,
                retry_count, last_error_code, last_error_message,
                last_success_at, updated_at
            FROM host_projection_checkpoints
            WHERE observer_id = ? AND projection_name = ?
                AND schema_version = ?
            """,
            (observer_id, projection_name, schema_version),
        )
        if not rows:
            return None
        return _row_to_checkpoint(rows[0], lag_events=self._lag_events_for(rows[0]))

    def list_all(self) -> tuple[ProjectionCheckpoint, ...]:
        """列出全部 checkpoint。

        :returns: ProjectionCheckpoint 元组。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        rows = self.storage.execute_read(
            """
            SELECT observer_id, projection_name, schema_version,
                last_success_position, last_attempted_position, status,
                retry_count, last_error_code, last_error_message,
                last_success_at, updated_at
            FROM host_projection_checkpoints
            """
        )
        return tuple(
            _row_to_checkpoint(row, lag_events=self._lag_events_for(row))
            for row in rows
        )

    def ensure(
        self,
        *,
        tx: HostStorageTransaction,
        observer_id: str,
        projection_name: str,
        schema_version: int,
    ) -> None:
        """确保 checkpoint 行存在。

        :param tx: 当前事务。
        :param observer_id: observer id。
        :param projection_name: projection 名。
        :param schema_version: schema 版本。
        :returns: 无返回值。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        now_iso = datetime.now(tz=timezone.utc).isoformat()
        tx.execute(
            """
            INSERT OR IGNORE INTO host_projection_checkpoints (
                observer_id, projection_name, schema_version,
                last_success_position, last_attempted_position, status,
                retry_count, last_error_code, last_error_message,
                last_success_at, updated_at
            ) VALUES (?, ?, ?, NULL, NULL, ?, 0, NULL, NULL, NULL, ?)
            """,
            (
                observer_id,
                projection_name,
                schema_version,
                ObserverStatus.IDLE.value,
                now_iso,
            ),
        )

    def advance_success(
        self,
        *,
        tx: HostStorageTransaction,
        observer_id: str,
        projection_name: str,
        schema_version: int,
        position: GlobalEventPosition,
        status: ObserverStatus,
    ) -> None:
        """记录一次成功消费并前进 checkpoint。

        checkpoint 只能前进；尝试写入比已有 ``last_success_position`` 更小
        的位置时抛出。

        :param tx: 当前事务。
        :param observer_id: observer id。
        :param projection_name: projection 名。
        :param schema_version: schema 版本。
        :param position: 成功消费位置。
        :param status: 新状态（``RUNNING`` / ``CAUGHT_UP`` 等）。
        :returns: 无返回值。
        :raises ValueError: checkpoint 倒退时抛出。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        existing = tx.execute(
            """
            SELECT last_success_position FROM host_projection_checkpoints
            WHERE observer_id = ? AND projection_name = ?
                AND schema_version = ?
            """,
            (observer_id, projection_name, schema_version),
        ).fetchone()
        if existing is not None and existing[0] is not None:
            if int(existing[0]) > position.value:
                raise ValueError(_ERROR_CHECKPOINT_REGRESSION)
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        tx.execute(
            """
            UPDATE host_projection_checkpoints
            SET last_success_position = ?, last_attempted_position = ?,
                status = ?, retry_count = 0, last_error_code = NULL,
                last_error_message = NULL, last_success_at = ?,
                updated_at = ?
            WHERE observer_id = ? AND projection_name = ?
                AND schema_version = ?
            """,
            (
                position.value,
                position.value,
                status.value,
                now_iso,
                now_iso,
                observer_id,
                projection_name,
                schema_version,
            ),
        )

    def record_failure(
        self,
        *,
        tx: HostStorageTransaction,
        observer_id: str,
        projection_name: str,
        schema_version: int,
        attempted_position: GlobalEventPosition,
        status: ObserverStatus,
        error_code: str,
        error_message: str,
    ) -> None:
        """记录一次失败尝试，retry_count 递增，但不前进 success position。

        :param tx: 当前事务。
        :param observer_id: observer id。
        :param projection_name: projection 名。
        :param schema_version: schema 版本。
        :param attempted_position: 尝试消费的位置。
        :param status: 新状态（``RETRYABLE_FAILED`` / ``BLOCKED_FAILED``）。
        :param error_code: 错误码。
        :param error_message: 错误消息。
        :returns: 无返回值。
        :raises sqlite3.DatabaseError: 写入失败时抛出。
        """

        now_iso = datetime.now(tz=timezone.utc).isoformat()
        tx.execute(
            """
            UPDATE host_projection_checkpoints
            SET last_attempted_position = ?, status = ?,
                retry_count = retry_count + 1,
                last_error_code = ?, last_error_message = ?,
                updated_at = ?
            WHERE observer_id = ? AND projection_name = ?
                AND schema_version = ?
            """,
            (
                attempted_position.value,
                status.value,
                error_code,
                error_message,
                now_iso,
                observer_id,
                projection_name,
                schema_version,
            ),
        )

    def _lag_events_for(self, row: sqlite3.Row) -> int:
        """根据当前最大 event_position 计算 lag。

        :param row: checkpoint 行。
        :returns: 落后事件数；checkpoint 未推进时返回总事件数。
        :raises sqlite3.DatabaseError: 读取失败时抛出。
        """

        latest_rows = self.storage.execute_read(
            "SELECT MAX(event_position) FROM host_run_events"
        )
        if not latest_rows or latest_rows[0][0] is None:
            return 0
        latest = int(latest_rows[0][0])
        last_success = row["last_success_position"]  # type: ignore[index]
        if last_success is None:
            return latest
        return max(0, latest - int(last_success))


def _row_to_checkpoint(
    row: sqlite3.Row,
    *,
    lag_events: int,
) -> ProjectionCheckpoint:
    """SQLite 行转换为 :class:`ProjectionCheckpoint`。

    :param row: sqlite3.Row。
    :param lag_events: 落后事件数。
    :returns: ProjectionCheckpoint。
    :raises ValueError: status 非法时抛出。
    """

    return ProjectionCheckpoint(
        observer_id=row["observer_id"],  # type: ignore[index]
        projection_name=row["projection_name"],  # type: ignore[index]
        schema_version=int(row["schema_version"]),  # type: ignore[index]
        last_success_position=(
            None if row["last_success_position"] is None  # type: ignore[index]
            else GlobalEventPosition(value=int(row["last_success_position"]))  # type: ignore[index]
        ),
        last_attempted_position=(
            None if row["last_attempted_position"] is None  # type: ignore[index]
            else GlobalEventPosition(value=int(row["last_attempted_position"]))  # type: ignore[index]
        ),
        status=ObserverStatus(row["status"]),  # type: ignore[index]
        retry_count=int(row["retry_count"]),  # type: ignore[index]
        last_error_code=row["last_error_code"],  # type: ignore[index]
        last_error_message=row["last_error_message"],  # type: ignore[index]
        last_success_at=(
            None if row["last_success_at"] is None  # type: ignore[index]
            else datetime.fromisoformat(row["last_success_at"])  # type: ignore[index]
        ),
        updated_at=datetime.fromisoformat(row["updated_at"]),  # type: ignore[index]
        lag_events=lag_events,
    )


__all__ = [
    "ProjectionStore",
]
