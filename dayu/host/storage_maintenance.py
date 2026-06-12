"""Host storage maintenance public facade。

本模块提供只读 storage usage report 和显式 maintenance entrypoint。
maintenance 默认 dry-run；只有调用方显式设置 ``reclaim_orphan_artifacts=True``
时，才会回收删除前 recheck 仍未被引用的 orphan artifact 文件。它不删除
SQLite row、不执行 VACUUM，也不实现 scheduler。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from sqlite3 import Connection

from dayu.contracts.json_value import JsonValue
from dayu.host.api import HostApiError, HostApiErrorCode
from dayu.host.command import HostCommandHandle
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.maintenance import (
    HostWalCheckpointMode,
    HostWalCheckpointResult,
    run_host_wal_checkpoint,
)
from dayu.host.durable.storage_lifecycle import (
    DurableArtifactFileError,
    HostStorageUsageReport,
    artifact_relative_path_is_referenced,
    collect_referenced_artifact_paths,
    physical_artifact_bytes as _physical_artifact_bytes,
    read_storage_usage,
    reclaim_orphan_artifact_files,
    scan_orphan_artifact_files,
)
from dayu.host.durable.transaction import HostTransaction

DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS = 3600.0
"""dry-run orphan artifact 候选的默认 grace window 秒数。"""


@dataclass(frozen=True, slots=True, kw_only=True)
class HostStorageMaintenanceRequest:
    """Host storage maintenance 请求。

    默认 dry-run 会返回 orphan artifact 候选、物理 artifact bytes、usage
    report 和可选 WAL checkpoint 诊断，但不会删除文件或 row。只有
    ``reclaim_orphan_artifacts=True`` 时才会执行 opt-in orphan artifact
    物理文件回收。

    :param reclaim_orphan_artifacts: 是否执行 destructive orphan artifact 回收；
        启用后仍会对每个候选执行删除前 recheck。
    :param orphan_grace_seconds: orphan 文件进入候选前必须超过的 mtime grace 秒数。
    :param run_wal_checkpoint: 是否用独立 SQLite connection 执行 WAL checkpoint。
    :param wal_checkpoint_mode: checkpoint 模式。
    :raises TypeError: 字段类型不符合契约时抛出。
    :raises ValueError: ``orphan_grace_seconds`` 为负数时抛出。
    """

    reclaim_orphan_artifacts: bool = False
    orphan_grace_seconds: float = DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS
    run_wal_checkpoint: bool = True
    wal_checkpoint_mode: HostWalCheckpointMode = HostWalCheckpointMode.PASSIVE

    def __post_init__(self) -> None:
        """校验 request 字段。

        :returns: ``None``。
        :raises TypeError: 字段类型不符合契约时抛出。
        :raises ValueError: ``orphan_grace_seconds`` 为负数时抛出。
        """

        _require_bool(
            self.reclaim_orphan_artifacts,
            field_name="HostStorageMaintenanceRequest.reclaim_orphan_artifacts",
        )
        _require_non_negative_float(
            self.orphan_grace_seconds,
            field_name="HostStorageMaintenanceRequest.orphan_grace_seconds",
        )
        _require_bool(
            self.run_wal_checkpoint,
            field_name="HostStorageMaintenanceRequest.run_wal_checkpoint",
        )
        if not isinstance(self.wal_checkpoint_mode, HostWalCheckpointMode):
            raise TypeError(
                "HostStorageMaintenanceRequest.wal_checkpoint_mode must be "
                "HostWalCheckpointMode"
            )


@dataclass(frozen=True, slots=True)
class HostStorageMaintenanceFileError:
    """storage maintenance 单文件错误诊断。

    该类型用于 opt-in orphan artifact 回收中的单文件失败；失败文件不会进入
    ``reclaimed_artifact_paths``，maintenance 会继续处理其它候选。

    :param path: 出错 artifact 的 POSIX 相对路径。
    :param operation: 出错操作名。
    :param message: 人类可读错误摘要。
    :raises ValueError: 任一文本字段为空时抛出。
    """

    path: str
    operation: str
    message: str

    def __post_init__(self) -> None:
        """校验错误诊断字段。

        :returns: ``None``。
        :raises ValueError: 任一文本字段为空时抛出。
        """

        _require_non_empty_text(
            self.path,
            field_name="HostStorageMaintenanceFileError.path",
        )
        _require_non_empty_text(
            self.operation,
            field_name="HostStorageMaintenanceFileError.operation",
        )
        _require_non_empty_text(
            self.message,
            field_name="HostStorageMaintenanceFileError.message",
        )

    def json_value(self) -> JsonValue:
        """返回自解释 JSON object。

        :returns: 包含相对路径、操作和错误消息的 JSON object。
        """

        return {
            "path": self.path,
            "operation": self.operation,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class HostStorageMaintenanceResult:
    """Host storage maintenance 结果。

    :param usage: maintenance 开始时读取的 storage usage report。
    :param physical_artifact_bytes: ``sha256/`` namespace 下已发布 artifact 物理字节和。
    :param orphan_artifact_candidates: 已证明无 descriptor 引用且超过 grace 的候选路径。
    :param reclaimed_artifact_paths: opt-in 回收时已删除的路径；dry-run 时为空。
    :param file_errors: 文件级错误；dry-run 或无删除错误时为空。
    :param wal_checkpoint: WAL checkpoint 诊断；请求关闭 checkpoint 时为 ``None``。
    :raises TypeError: 字段类型不符合契约时抛出。
    :raises ValueError: 整数字段为负数时抛出。
    """

    usage: HostStorageUsageReport
    physical_artifact_bytes: int
    orphan_artifact_candidates: tuple[str, ...]
    reclaimed_artifact_paths: tuple[str, ...]
    file_errors: tuple[HostStorageMaintenanceFileError, ...]
    wal_checkpoint: HostWalCheckpointResult | None

    def __post_init__(self) -> None:
        """校验 result 字段。

        :returns: ``None``。
        :raises TypeError: 字段类型不符合契约时抛出。
        :raises ValueError: 整数字段为负数时抛出。
        """

        if not isinstance(self.usage, HostStorageUsageReport):
            raise TypeError("HostStorageMaintenanceResult.usage must be HostStorageUsageReport")
        _require_non_negative_int(
            self.physical_artifact_bytes,
            field_name="HostStorageMaintenanceResult.physical_artifact_bytes",
        )
        _require_string_tuple(
            self.orphan_artifact_candidates,
            field_name="HostStorageMaintenanceResult.orphan_artifact_candidates",
        )
        _require_string_tuple(
            self.reclaimed_artifact_paths,
            field_name="HostStorageMaintenanceResult.reclaimed_artifact_paths",
        )
        for file_error in self.file_errors:
            if not isinstance(file_error, HostStorageMaintenanceFileError):
                raise TypeError(
                    "HostStorageMaintenanceResult.file_errors must contain "
                    "HostStorageMaintenanceFileError"
                )
        if self.wal_checkpoint is not None and not isinstance(
            self.wal_checkpoint,
            HostWalCheckpointResult,
        ):
            raise TypeError(
                "HostStorageMaintenanceResult.wal_checkpoint must be "
                "HostWalCheckpointResult or None"
            )

    def json_value(self) -> JsonValue:
        """返回自解释 JSON object。

        :returns: maintenance result 的 JSON object。
        """

        return {
            "usage": self.usage.json_value(),
            "physical_artifact_bytes": self.physical_artifact_bytes,
            "orphan_artifact_candidates": list(self.orphan_artifact_candidates),
            "reclaimed_artifact_paths": list(self.reclaimed_artifact_paths),
            "file_errors": [error.json_value() for error in self.file_errors],
            "wal_checkpoint": _wal_checkpoint_json_value(self.wal_checkpoint),
        }


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


def run_storage_maintenance(
    host: HostCommandHandle,
    request: HostStorageMaintenanceRequest,
) -> HostStorageMaintenanceResult:
    """执行 Host storage maintenance。

    本入口不在 command transaction 内执行 checkpoint；当请求 checkpoint 时，
    它会打开独立 durable connection，调用 ``run_host_wal_checkpoint`` 后在
    ``finally`` 中关闭。默认 dry-run 不删除任何文件；设置
    ``reclaim_orphan_artifacts=True`` 时，仅回收已由候选扫描证明为 orphan、
    且删除前 recheck 仍未被任何 descriptor 引用的 ``sha256/`` artifact
    文件。recheck 与 unlink 之间仍存在极短 TOCTOU 窗口；默认 grace、
    content-addressed artifact 可重写性与 containment-guarded delete 用于降低
    风险。

    :param host: Host command handle。
    :param request: maintenance 请求。
    :returns: maintenance 结果。
    :raises dayu.host.api.HostApiError: durable 读取、artifact 扫描、文件 stat
        或 checkpoint 失败时抛出。
    """

    db_path = host._db_path()
    artifact_root = host._artifact_root()
    try:
        read_state = host._run_read(
            _ReadStorageMaintenanceStateOperation(db_path=db_path)
        )
        candidates = scan_orphan_artifact_files(
            artifact_root,
            read_state.referenced_artifact_paths,
            now=datetime.now(UTC),
            grace_seconds=request.orphan_grace_seconds,
        )
        reclaim_result = _reclaim_orphan_artifacts_if_requested(
            host,
            artifact_root=artifact_root,
            candidates=candidates,
            request=request,
        )
        physical_bytes = _physical_artifact_bytes(artifact_root)
        wal_checkpoint = _run_wal_checkpoint_if_requested(
            host,
            db_path=db_path,
            request=request,
        )
    except OSError as exc:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Storage maintenance file operation failed",
            retryable=False,
        ) from exc
    except HostDurableError as exc:
        raise HostApiError(
            code=HostApiErrorCode.INTERNAL_ERROR,
            message="Storage maintenance durable operation failed",
            retryable=False,
        ) from exc

    return HostStorageMaintenanceResult(
        usage=read_state.usage,
        physical_artifact_bytes=physical_bytes,
        orphan_artifact_candidates=candidates,
        reclaimed_artifact_paths=reclaim_result.reclaimed_paths,
        file_errors=_maintenance_file_errors(reclaim_result.file_errors),
        wal_checkpoint=wal_checkpoint,
    )


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


@dataclass(frozen=True, slots=True)
class _StorageMaintenanceReadState:
    """storage maintenance read transaction 快照。

    :param usage: storage usage report。
    :param referenced_artifact_paths: 当前 descriptor 引用的 artifact 相对路径集合。
    """

    usage: HostStorageUsageReport
    referenced_artifact_paths: frozenset[str]


@dataclass(frozen=True, slots=True)
class _ReadStorageMaintenanceStateOperation:
    """storage maintenance read transaction body。

    :param db_path: Host durable SQLite DB 文件路径。
    """

    db_path: Path

    def __call__(self, transaction: HostTransaction) -> _StorageMaintenanceReadState:
        """读取 maintenance 扫描所需的 DB 快照。

        :param transaction: 当前 Host read transaction。
        :returns: usage report 与 referenced artifact paths。
        """

        return _StorageMaintenanceReadState(
            usage=read_storage_usage(transaction, db_path=self.db_path),
            referenced_artifact_paths=collect_referenced_artifact_paths(transaction),
        )


@dataclass(frozen=True, slots=True)
class _ArtifactPathReferencedOperation:
    """单个 artifact 相对路径引用复查 read transaction body。

    :param relative_path: artifact root 下的 POSIX 相对路径。
    """

    relative_path: str

    def __call__(self, transaction: HostTransaction) -> bool:
        """执行 artifact descriptor 引用复查。

        :param transaction: 当前 Host read transaction。
        :returns: 路径仍被任意 artifact descriptor 引用时返回 ``True``。
        """

        return artifact_relative_path_is_referenced(transaction, self.relative_path)


@dataclass(frozen=True, slots=True)
class _ArtifactPathReferenceChecker:
    """通过 Host read transaction 执行 artifact 路径引用复查。

    :param host: Host command handle。
    """

    host: HostCommandHandle

    def __call__(self, relative_path: str) -> bool:
        """判断 artifact 路径是否仍被 descriptor 引用。

        :param relative_path: artifact root 下的 POSIX 相对路径。
        :returns: 路径仍被引用时返回 ``True``。
        """

        return self.host._run_read(_ArtifactPathReferencedOperation(relative_path))


@dataclass(frozen=True, slots=True)
class _MaintenanceReclaimResult:
    """facade 内部 orphan artifact 回收结果。

    :param reclaimed_paths: 已成功删除的路径。
    :param file_errors: durable 单文件错误诊断。
    """

    reclaimed_paths: tuple[str, ...]
    file_errors: tuple[DurableArtifactFileError, ...]


def _reclaim_orphan_artifacts_if_requested(
    host: HostCommandHandle,
    *,
    artifact_root: Path,
    candidates: tuple[str, ...],
    request: HostStorageMaintenanceRequest,
) -> _MaintenanceReclaimResult:
    """按请求执行 opt-in orphan artifact 文件回收。

    :param host: Host command handle。
    :param artifact_root: artifact 根目录。
    :param candidates: 已由 dry-run 扫描产生的候选路径。
    :param request: maintenance 请求。
    :returns: 回收结果；dry-run 时为空结果。
    """

    if not request.reclaim_orphan_artifacts:
        return _MaintenanceReclaimResult(reclaimed_paths=(), file_errors=())
    result = reclaim_orphan_artifact_files(
        artifact_root,
        candidates,
        is_artifact_path_referenced=_ArtifactPathReferenceChecker(host),
    )
    return _MaintenanceReclaimResult(
        reclaimed_paths=result.reclaimed_paths,
        file_errors=result.file_errors,
    )


def _maintenance_file_errors(
    file_errors: tuple[DurableArtifactFileError, ...],
) -> tuple[HostStorageMaintenanceFileError, ...]:
    """把 durable 文件错误诊断转换为 Host facade 诊断。

    :param file_errors: durable 文件错误诊断。
    :returns: Host maintenance 文件错误诊断。
    """

    return tuple(
        HostStorageMaintenanceFileError(
            path=file_error.path,
            operation=file_error.operation,
            message=file_error.message,
        )
        for file_error in file_errors
    )


def _run_wal_checkpoint_if_requested(
    host: HostCommandHandle,
    *,
    db_path: Path,
    request: HostStorageMaintenanceRequest,
) -> HostWalCheckpointResult | None:
    """按请求执行 WAL checkpoint。

    :param host: Host command handle。
    :param db_path: Host durable SQLite DB 文件路径。
    :param request: maintenance 请求。
    :returns: checkpoint 结果；请求关闭时返回 ``None``。
    :raises HostDurableError: checkpoint 失败时抛出。
    :raises HostApiError: 打开独立 connection 失败时抛出。
    """

    if not request.run_wal_checkpoint:
        return None
    connection: Connection | None = None
    try:
        connection = host._open_durable_connection()
        return run_host_wal_checkpoint(
            connection,
            db_path=db_path,
            mode=request.wal_checkpoint_mode,
        )
    finally:
        if connection is not None:
            connection.close()


def _wal_checkpoint_json_value(
    wal_checkpoint: HostWalCheckpointResult | None,
) -> JsonValue:
    """把 checkpoint 结果转换为 JSON value。

    :param wal_checkpoint: checkpoint 结果或 ``None``。
    :returns: 自解释 JSON object 或 ``None``。
    """

    if wal_checkpoint is None:
        return None
    return {
        "mode": wal_checkpoint.mode.value,
        "busy_pages": wal_checkpoint.busy_pages,
        "log_pages": wal_checkpoint.log_pages,
        "checkpointed_pages": wal_checkpoint.checkpointed_pages,
        "wal_size_bytes": wal_checkpoint.wal_size_bytes,
    }


def _require_bool(value: bool, *, field_name: str) -> None:
    """校验字段为严格 bool。

    :param value: 待校验值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 值不是 bool 时抛出。
    """

    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be bool")


def _require_non_negative_float(value: float, *, field_name: str) -> None:
    """校验字段为非负 float。

    :param value: 待校验值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 值不是 int/float 或为 bool 时抛出。
    :raises ValueError: 值为负数时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise TypeError(f"{field_name} must be float")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_non_negative_int(value: int, *, field_name: str) -> None:
    """校验字段为非负 int。

    :param value: 待校验值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 值不是 int 时抛出。
    :raises ValueError: 值为负数时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_string_tuple(value: tuple[str, ...], *, field_name: str) -> None:
    """校验字段为字符串元组。

    :param value: 待校验值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 值不是字符串元组时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} must contain str")


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    """校验字段为非空字符串。

    :param value: 待校验值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: 字符串为空时抛出。
    """

    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


__all__ = [
    "DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS",
    "HostStorageMaintenanceFileError",
    "HostStorageMaintenanceRequest",
    "HostStorageMaintenanceResult",
    "HostStorageUsageReport",
    "report_storage_usage",
    "run_storage_maintenance",
]
