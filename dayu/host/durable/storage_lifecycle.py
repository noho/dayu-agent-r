"""Host durable storage lifecycle 只读诊断。

本模块只提供 storage usage report 所需的 SQLite row count、logical payload
字节统计、DB/WAL 文件大小读取、artifact 引用证明和 dry-run 文件扫描原语。
它不写 durable 状态、不执行 WAL checkpoint，也不删除任何文件或 row。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import AbstractSet

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.artifact import iter_published_artifact_relative_paths
from dayu.host.durable.payload import PayloadKind
from dayu.host.durable.schema import (
    HOST_DURABLE_TABLES,
    TABLE_EVENT_LOG,
    TABLE_HOST_ATTEMPT_DISPATCH_RECORDS,
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_AUDIT_SINK_MARKERS,
    TABLE_HOST_INSTANCES,
    TABLE_HOST_MEMORY_DIAGNOSTICS,
    TABLE_HOST_MEMORY_ITEMS,
    TABLE_HOST_MEMORY_SNAPSHOTS,
    TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY,
    TABLE_HOST_OUTBOX_TERMINAL_ITEMS,
    TABLE_HOST_PROJECTION_CHECKPOINTS,
    TABLE_HOST_PROJECTION_FAILURES,
    TABLE_HOST_PURGE_TOMBSTONES,
    TABLE_HOST_RUN_RESULTS,
    TABLE_HOST_RUNS,
    TABLE_HOST_SESSION_SLOTS,
    TABLE_HOST_SESSION_TIMELINE_ITEMS,
    TABLE_HOST_SESSIONS,
    TABLE_HOST_TOOL_TRACE_HOT,
    TABLE_HOST_WAIT_RECORDS,
    TABLE_IDEMPOTENCY_RECORDS,
    TABLE_PAYLOAD_DESCRIPTORS,
    TABLE_SQLITE_PAYLOADS,
)
from dayu.host.durable.transaction import HostTransaction

_HOST_DURABLE_TABLE_TO_REPORT_FIELD: tuple[tuple[str, str], ...] = (
    (TABLE_EVENT_LOG, "event_log_rows"),
    (TABLE_IDEMPOTENCY_RECORDS, "idempotency_record_rows"),
    (TABLE_SQLITE_PAYLOADS, "sqlite_payload_rows"),
    (TABLE_PAYLOAD_DESCRIPTORS, "payload_descriptor_rows"),
    (TABLE_HOST_INSTANCES, "host_instance_rows"),
    (TABLE_HOST_SESSIONS, "host_session_rows"),
    (TABLE_HOST_SESSION_SLOTS, "host_session_slot_rows"),
    (TABLE_HOST_RUNS, "host_run_rows"),
    (TABLE_HOST_ATTEMPTS, "host_attempt_rows"),
    (TABLE_HOST_ATTEMPT_DISPATCH_RECORDS, "host_attempt_dispatch_record_rows"),
    (TABLE_HOST_WAIT_RECORDS, "host_wait_record_rows"),
    (TABLE_HOST_PROJECTION_CHECKPOINTS, "host_projection_checkpoint_rows"),
    (TABLE_HOST_PROJECTION_FAILURES, "host_projection_failure_rows"),
    (TABLE_HOST_RUN_RESULTS, "host_run_result_rows"),
    (TABLE_HOST_SESSION_TIMELINE_ITEMS, "host_session_timeline_item_rows"),
    (TABLE_HOST_MEMORY_SNAPSHOTS, "host_memory_snapshot_rows"),
    (TABLE_HOST_MEMORY_ITEMS, "host_memory_item_rows"),
    (TABLE_HOST_MEMORY_DIAGNOSTICS, "host_memory_diagnostic_rows"),
    (TABLE_HOST_AUDIT_SINK_MARKERS, "host_audit_sink_marker_rows"),
    (TABLE_HOST_TOOL_TRACE_HOT, "host_tool_trace_hot_rows"),
    (TABLE_HOST_OUTBOX_TERMINAL_ITEMS, "host_outbox_terminal_item_rows"),
    (TABLE_HOST_OUTBOX_DRAIN_IDEMPOTENCY, "host_outbox_drain_idempotency_rows"),
    (TABLE_HOST_PURGE_TOMBSTONES, "host_purge_tombstone_rows"),
)
"""Host durable table 到 report 字段的全量映射。"""

_REPORT_TABLES: tuple[str, ...] = tuple(
    table_name for table_name, _field_name in _HOST_DURABLE_TABLE_TO_REPORT_FIELD
)
"""report 覆盖的 durable table 名称集合。"""


@dataclass(frozen=True, slots=True)
class HostStorageUsageReport:
    """Host storage usage 的只读快照。

    所有 row count 字段都来自同一个 read transaction 内的 SQLite
    ``COUNT(*)``；logical bytes 字段来自 durable payload size metadata；
    ``db_file_bytes`` 与 ``wal_file_bytes`` 来自文件系统 ``stat``。字段均为非负
    整数，报告本身不表达 cleanup 决策。

    :param event_log_rows: EventLog row 数。
    :param idempotency_record_rows: 幂等记录 row 数。
    :param sqlite_payload_rows: SQLite payload row 数。
    :param payload_descriptor_rows: payload descriptor row 数。
    :param host_instance_rows: Host instance liveness row 数。
    :param host_session_rows: Session truth row 数。
    :param host_session_slot_rows: Session slot binding row 数。
    :param host_run_rows: Run truth row 数。
    :param host_attempt_rows: Attempt truth row 数。
    :param host_attempt_dispatch_record_rows: Attempt dispatch record row 数。
    :param host_wait_record_rows: wait record row 数。
    :param host_projection_checkpoint_rows: projection checkpoint row 数。
    :param host_projection_failure_rows: projection failure row 数。
    :param host_run_result_rows: run result projection row 数。
    :param host_session_timeline_item_rows: session timeline projection row 数。
    :param host_memory_snapshot_rows: memory snapshot row 数。
    :param host_memory_item_rows: memory item row 数。
    :param host_memory_diagnostic_rows: memory diagnostic row 数。
    :param host_audit_sink_marker_rows: audit sink marker row 数。
    :param host_tool_trace_hot_rows: tool trace hot row 数。
    :param host_outbox_terminal_item_rows: outbox terminal item row 数。
    :param host_outbox_drain_idempotency_rows: outbox drain 幂等 row 数。
    :param host_purge_tombstone_rows: purge tombstone row 数。
    :param sqlite_payload_logical_bytes: SQLite payload logical byte 总数。
    :param artifact_descriptor_logical_bytes: artifact descriptor logical byte 总数。
    :param orphan_sqlite_payload_count: 未被 descriptor 引用的 SQLite payload row 数。
    :param db_file_bytes: SQLite DB 文件大小；文件不存在时为零。
    :param wal_file_bytes: SQLite WAL 文件大小；文件不存在时为零。
    :raises TypeError: 任一字段不是严格整数时抛出。
    :raises ValueError: 任一字段为负数时抛出。
    """

    event_log_rows: int
    idempotency_record_rows: int
    sqlite_payload_rows: int
    payload_descriptor_rows: int
    host_instance_rows: int
    host_session_rows: int
    host_session_slot_rows: int
    host_run_rows: int
    host_attempt_rows: int
    host_attempt_dispatch_record_rows: int
    host_wait_record_rows: int
    host_projection_checkpoint_rows: int
    host_projection_failure_rows: int
    host_run_result_rows: int
    host_session_timeline_item_rows: int
    host_memory_snapshot_rows: int
    host_memory_item_rows: int
    host_memory_diagnostic_rows: int
    host_audit_sink_marker_rows: int
    host_tool_trace_hot_rows: int
    host_outbox_terminal_item_rows: int
    host_outbox_drain_idempotency_rows: int
    host_purge_tombstone_rows: int
    sqlite_payload_logical_bytes: int
    artifact_descriptor_logical_bytes: int
    orphan_sqlite_payload_count: int
    db_file_bytes: int
    wal_file_bytes: int

    def __post_init__(self) -> None:
        """校验 report 字段全部为非负整数。

        :returns: ``None``。
        :raises TypeError: 字段不是严格整数时抛出。
        :raises ValueError: 字段为负数时抛出。
        """

        for field_name, value in self._field_items():
            _require_non_negative_int(value, field_name=field_name)

    def json_value(self) -> JsonValue:
        """返回稳定 JSON object 形式的 report。

        :returns: 键名自解释、顺序稳定的 JSON object。
        """

        return {field_name: value for field_name, value in self._field_items()}

    def _field_items(self) -> tuple[tuple[str, int], ...]:
        """按稳定顺序返回 report 字段名和值。

        :returns: 字段名与字段值元组。
        """

        return (
            ("event_log_rows", self.event_log_rows),
            ("idempotency_record_rows", self.idempotency_record_rows),
            ("sqlite_payload_rows", self.sqlite_payload_rows),
            ("payload_descriptor_rows", self.payload_descriptor_rows),
            ("host_instance_rows", self.host_instance_rows),
            ("host_session_rows", self.host_session_rows),
            ("host_session_slot_rows", self.host_session_slot_rows),
            ("host_run_rows", self.host_run_rows),
            ("host_attempt_rows", self.host_attempt_rows),
            (
                "host_attempt_dispatch_record_rows",
                self.host_attempt_dispatch_record_rows,
            ),
            ("host_wait_record_rows", self.host_wait_record_rows),
            ("host_projection_checkpoint_rows", self.host_projection_checkpoint_rows),
            ("host_projection_failure_rows", self.host_projection_failure_rows),
            ("host_run_result_rows", self.host_run_result_rows),
            (
                "host_session_timeline_item_rows",
                self.host_session_timeline_item_rows,
            ),
            ("host_memory_snapshot_rows", self.host_memory_snapshot_rows),
            ("host_memory_item_rows", self.host_memory_item_rows),
            ("host_memory_diagnostic_rows", self.host_memory_diagnostic_rows),
            ("host_audit_sink_marker_rows", self.host_audit_sink_marker_rows),
            ("host_tool_trace_hot_rows", self.host_tool_trace_hot_rows),
            (
                "host_outbox_terminal_item_rows",
                self.host_outbox_terminal_item_rows,
            ),
            (
                "host_outbox_drain_idempotency_rows",
                self.host_outbox_drain_idempotency_rows,
            ),
            ("host_purge_tombstone_rows", self.host_purge_tombstone_rows),
            ("sqlite_payload_logical_bytes", self.sqlite_payload_logical_bytes),
            (
                "artifact_descriptor_logical_bytes",
                self.artifact_descriptor_logical_bytes,
            ),
            ("orphan_sqlite_payload_count", self.orphan_sqlite_payload_count),
            ("db_file_bytes", self.db_file_bytes),
            ("wal_file_bytes", self.wal_file_bytes),
        )


def read_storage_usage(
    transaction: HostTransaction, *, db_path: Path
) -> HostStorageUsageReport:
    """读取 Host durable storage usage report。

    :param transaction: 调用方提供的 read transaction。
    :param db_path: Host durable SQLite DB 文件路径，用于读取 DB/WAL 文件大小。
    :returns: storage usage report。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    _assert_report_tables_cover_schema()
    row_counts = {
        field_name: _count_rows(transaction, table_name)
        for table_name, field_name in _HOST_DURABLE_TABLE_TO_REPORT_FIELD
    }
    return HostStorageUsageReport(
        event_log_rows=row_counts["event_log_rows"],
        idempotency_record_rows=row_counts["idempotency_record_rows"],
        sqlite_payload_rows=row_counts["sqlite_payload_rows"],
        payload_descriptor_rows=row_counts["payload_descriptor_rows"],
        host_instance_rows=row_counts["host_instance_rows"],
        host_session_rows=row_counts["host_session_rows"],
        host_session_slot_rows=row_counts["host_session_slot_rows"],
        host_run_rows=row_counts["host_run_rows"],
        host_attempt_rows=row_counts["host_attempt_rows"],
        host_attempt_dispatch_record_rows=(
            row_counts["host_attempt_dispatch_record_rows"]
        ),
        host_wait_record_rows=row_counts["host_wait_record_rows"],
        host_projection_checkpoint_rows=(
            row_counts["host_projection_checkpoint_rows"]
        ),
        host_projection_failure_rows=row_counts["host_projection_failure_rows"],
        host_run_result_rows=row_counts["host_run_result_rows"],
        host_session_timeline_item_rows=(
            row_counts["host_session_timeline_item_rows"]
        ),
        host_memory_snapshot_rows=row_counts["host_memory_snapshot_rows"],
        host_memory_item_rows=row_counts["host_memory_item_rows"],
        host_memory_diagnostic_rows=row_counts["host_memory_diagnostic_rows"],
        host_audit_sink_marker_rows=row_counts["host_audit_sink_marker_rows"],
        host_tool_trace_hot_rows=row_counts["host_tool_trace_hot_rows"],
        host_outbox_terminal_item_rows=(
            row_counts["host_outbox_terminal_item_rows"]
        ),
        host_outbox_drain_idempotency_rows=(
            row_counts["host_outbox_drain_idempotency_rows"]
        ),
        host_purge_tombstone_rows=row_counts["host_purge_tombstone_rows"],
        sqlite_payload_logical_bytes=_sum_sqlite_payload_logical_bytes(transaction),
        artifact_descriptor_logical_bytes=(
            _sum_artifact_descriptor_logical_bytes(transaction)
        ),
        orphan_sqlite_payload_count=_count_orphan_sqlite_payloads(transaction),
        db_file_bytes=_file_size_bytes(db_path),
        wal_file_bytes=_file_size_bytes(_wal_path_for_db_path(db_path)),
    )


def artifact_relative_path_is_referenced(
    transaction: HostTransaction,
    relative_path: str,
) -> bool:
    """判断 artifact 相对路径是否仍被存活 descriptor 引用。

    该证明只读取 ``payload_descriptors`` 中 ``payload_kind='artifact_ref'`` 且
    ``artifact_relative_path`` 完全匹配的 durable descriptor。audit JSONL、
    tool-trace JSONL、EventLog 内部 id 或其它内部治理标签都不是 artifact
    物理文件删除证明的业务事实来源。

    :param transaction: 调用方提供的 read transaction。
    :param relative_path: artifact root 下的 POSIX 相对路径。
    :returns: 存在匹配 artifact descriptor 时返回 ``True``。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    row = transaction.fetchone(
        f"""
        SELECT 1 AS referenced
        FROM {TABLE_PAYLOAD_DESCRIPTORS}
        WHERE payload_kind = ?
          AND artifact_relative_path = ?
        LIMIT 1
        """,
        (PayloadKind.ARTIFACT_REF.value, relative_path),
    )
    return row is not None


def collect_referenced_artifact_paths(
    transaction: HostTransaction,
) -> frozenset[str]:
    """收集当前所有 artifact descriptor 引用的相对路径。

    结果只来自 ``payload_descriptors`` 中 ``payload_kind='artifact_ref'`` 且
    ``artifact_relative_path`` 非空的 descriptor；它不解析 audit、tool-trace
    或 EventLog payload JSON。

    :param transaction: 调用方提供的 read transaction。
    :returns: artifact relative path 的不可变集合。
    :raises AssertionError: SQLite 返回了非字符串路径时抛出。
    :raises sqlite3.Error: SQLite 查询失败时由 transaction runner 结构化转换。
    """

    rows = transaction.fetchall(
        f"""
        SELECT artifact_relative_path
        FROM {TABLE_PAYLOAD_DESCRIPTORS}
        WHERE payload_kind = ?
          AND artifact_relative_path IS NOT NULL
        """,
        (PayloadKind.ARTIFACT_REF.value,),
    )
    paths: set[str] = set()
    for row in rows:
        value = row.get("artifact_relative_path")
        if not isinstance(value, str):
            raise AssertionError("artifact_relative_path must be returned as str")
        paths.add(value)
    return frozenset(paths)


def scan_orphan_artifact_files(
    artifact_root: Path,
    referenced: AbstractSet[str],
    *,
    now: datetime,
    grace_seconds: float,
) -> tuple[str, ...]:
    """扫描 dry-run orphan artifact 候选文件。

    扫描只使用 ``iter_published_artifact_relative_paths`` 枚举
    ``artifact_root/sha256`` 内容寻址 namespace 下的已发布普通文件，因此
    ``.tmp``、audit JSONL、tool-trace JSONL 与其它非 artifact namespace 文件
    不会进入候选。候选条件是 ``on_disk - referenced``，且文件 mtime 不晚于
    ``now - grace_seconds``。

    :param artifact_root: artifact 根目录。
    :param referenced: 当前 descriptor 引用的 artifact 相对路径集合。
    :param now: 调用方显式注入的当前时间。
    :param grace_seconds: orphan grace window 秒数，必须非负。
    :returns: 排序稳定的 orphan artifact 相对路径元组。
    :raises ValueError: ``now`` 缺少时区或 ``grace_seconds`` 为负数时抛出。
    :raises OSError: 候选文件 metadata 读取失败时抛出。
    :raises dayu.host.durable.errors.HostArtifactWriteError: artifact 枚举失败时抛出。
    """

    _require_aware_datetime(now, field_name="now")
    if grace_seconds < 0:
        raise ValueError("grace_seconds must be non-negative")
    cutoff_timestamp = now.timestamp() - grace_seconds
    candidates: list[str] = []
    for relative_path in iter_published_artifact_relative_paths(artifact_root):
        if relative_path in referenced:
            continue
        artifact_path = _artifact_file_path(artifact_root, relative_path)
        if artifact_path.stat().st_mtime <= cutoff_timestamp:
            candidates.append(relative_path)
    return tuple(sorted(candidates))


def physical_artifact_bytes(artifact_root: Path) -> int:
    """统计已发布 artifact 文件的物理字节数。

    该值只统计 ``artifact_root/sha256`` 内容寻址 namespace 下的已发布普通文件
    ``stat().st_size`` 之和，并排除 ``.tmp``、audit JSONL、tool-trace JSONL 和
    其它非 descriptor-managed namespace。它不执行 checkpoint，也不删除文件。

    :param artifact_root: artifact 根目录。
    :returns: 已发布 artifact 物理文件字节和。
    :raises OSError: 文件 metadata 读取失败时抛出。
    :raises dayu.host.durable.errors.HostArtifactWriteError: artifact 枚举失败时抛出。
    """

    total = 0
    for relative_path in iter_published_artifact_relative_paths(artifact_root):
        total += _artifact_file_path(artifact_root, relative_path).stat().st_size
    return total


def _assert_report_tables_cover_schema() -> None:
    """校验 report table 映射覆盖当前 durable schema 真源。

    :returns: ``None``。
    :raises AssertionError: report 映射与 schema 表清单不同步时抛出。
    """

    if _REPORT_TABLES != HOST_DURABLE_TABLES:
        missing = frozenset(HOST_DURABLE_TABLES) - frozenset(_REPORT_TABLES)
        extra = frozenset(_REPORT_TABLES) - frozenset(HOST_DURABLE_TABLES)
        raise AssertionError(
            f"storage usage report table mapping mismatch: missing={missing}; extra={extra}"
        )


def _count_rows(transaction: HostTransaction, table_name: str) -> int:
    """读取指定 durable table 的 row count。

    :param transaction: 调用方提供的 read transaction。
    :param table_name: durable table 名称。
    :returns: row count。
    :raises AssertionError: SQLite 未返回整数 count 时抛出。
    """

    row = transaction.fetchone(f"SELECT COUNT(*) AS row_count FROM {table_name}")
    if row is None:
        raise AssertionError(f"SQLite did not return count for {table_name}")
    return _row_int(row.get("row_count"), field_name=f"{table_name}.row_count")


def _sum_sqlite_payload_logical_bytes(transaction: HostTransaction) -> int:
    """读取 SQLite payload logical byte 总数。

    :param transaction: 调用方提供的 read transaction。
    :returns: ``host_sqlite_payloads.payload_size_bytes`` 求和，空表为零。
    """

    row = transaction.fetchone(
        f"""
        SELECT COALESCE(SUM(payload_size_bytes), 0) AS logical_bytes
        FROM {TABLE_SQLITE_PAYLOADS}
        """
    )
    if row is None:
        raise AssertionError("SQLite did not return sqlite payload byte sum")
    return _row_int(row.get("logical_bytes"), field_name="sqlite_payload_logical_bytes")


def _sum_artifact_descriptor_logical_bytes(transaction: HostTransaction) -> int:
    """读取 artifact descriptor logical byte 总数。

    该值只统计 descriptor 记录的 logical bytes，不读取也不遍历物理 artifact
    文件；内容寻址共享时它可能大于实际文件占用。

    :param transaction: 调用方提供的 read transaction。
    :returns: artifact descriptor payload size 求和，空集为零。
    """

    row = transaction.fetchone(
        f"""
        SELECT COALESCE(SUM(payload_size_bytes), 0) AS logical_bytes
        FROM {TABLE_PAYLOAD_DESCRIPTORS}
        WHERE payload_kind = ?
        """,
        (PayloadKind.ARTIFACT_REF.value,),
    )
    if row is None:
        raise AssertionError("SQLite did not return artifact descriptor byte sum")
    return _row_int(
        row.get("logical_bytes"),
        field_name="artifact_descriptor_logical_bytes",
    )


def _count_orphan_sqlite_payloads(transaction: HostTransaction) -> int:
    """统计未被 payload descriptor 引用的 SQLite payload row。

    :param transaction: 调用方提供的 read transaction。
    :returns: orphan SQLite payload row 数。
    """

    row = transaction.fetchone(
        f"""
        SELECT COUNT(*) AS orphan_count
        FROM {TABLE_SQLITE_PAYLOADS} AS payloads
        WHERE NOT EXISTS (
          SELECT 1
          FROM {TABLE_PAYLOAD_DESCRIPTORS} AS descriptors
          WHERE descriptors.sqlite_payload_id = payloads.payload_id
        )
        """
    )
    if row is None:
        raise AssertionError("SQLite did not return orphan sqlite payload count")
    return _row_int(row.get("orphan_count"), field_name="orphan_sqlite_payload_count")


def _row_int(value: int | float | str | bytes | None, *, field_name: str) -> int:
    """把 SQLite scalar 收窄为严格整数。

    :param value: SQLite scalar 值。
    :param field_name: 错误消息字段名。
    :returns: 整数值。
    :raises AssertionError: 值不是严格整数时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise AssertionError(f"{field_name} must be returned as int")
    return value


def _file_size_bytes(path: Path) -> int:
    """读取文件大小，缺失时返回零。

    :param path: 目标文件路径。
    :returns: 文件大小字节数；缺失时为零。
    :raises OSError: ``stat`` 发生非缺失类错误时透传。
    """

    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _wal_path_for_db_path(db_path: Path) -> Path:
    """按 SQLite 约定返回 WAL 文件路径。

    :param db_path: SQLite DB 文件路径。
    :returns: ``<db_path>-wal`` 路径。
    """

    return Path(f"{db_path}-wal")


def _artifact_file_path(artifact_root: Path, relative_path: str) -> Path:
    """把 artifact POSIX 相对路径转换为平台路径。

    :param artifact_root: artifact 根目录。
    :param relative_path: artifact POSIX 相对路径。
    :returns: artifact root 下的平台路径。
    """

    return artifact_root.joinpath(*PurePosixPath(relative_path).parts)


def _require_aware_datetime(value: datetime, *, field_name: str) -> None:
    """校验 datetime 带有可用时区。

    :param value: 待校验时间。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: ``value`` 不是 aware datetime 时抛出。
    """

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    """校验 report 字段为非负严格整数。

    :param value: 待校验值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 值不是严格整数时抛出。
    :raises ValueError: 值为负数时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


__all__ = [
    "HostStorageUsageReport",
    "artifact_relative_path_is_referenced",
    "collect_referenced_artifact_paths",
    "physical_artifact_bytes",
    "read_storage_usage",
    "scan_orphan_artifact_files",
]
