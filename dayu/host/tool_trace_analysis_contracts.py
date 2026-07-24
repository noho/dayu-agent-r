"""Tool Trace Analyzer 的公开输入契约。

本模块只定义可信输入阶段实际消费的输入模式、显式来源与诊断阈值。
报告、finding、vendor debugging 等后续 slice 契约不在此预定义。
"""

from __future__ import annotations

import math
import os
import stat
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

DEFAULT_TOOL_TRACE_LARGE_PAYLOAD_THRESHOLD_BYTES = 131_072
"""默认 large payload 诊断阈值。"""

DEFAULT_TOOL_TRACE_PAYLOAD_RANKING_LIMIT = 20
"""默认 payload 排名条目上限。"""

DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_SAMPLE_COUNT = 5
"""默认 latency 异常判断最小样本数。"""

DEFAULT_TOOL_TRACE_LATENCY_OUTLIER_MULTIPLIER = 3.0
"""默认 latency 异常倍数。"""

DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_DELTA_MS = 1_000
"""默认 latency 异常最小绝对差值。"""

_DAYU_DIRECTORY_NAME = ".dayu"
_HOST_DIRECTORY_NAME = "host"
_ARTIFACT_DIRECTORY_NAME = "artifacts"
_TOOL_TRACE_DIRECTORY_NAME = "tool-trace"
_TOOL_TRACE_COLD_FILE_NAME = "tool-trace-cold.jsonl"
_HOST_DATABASE_FILE_NAME = "dayu_host.sqlite3"


class ToolTraceInputMode(StrEnum):
    """Tool Trace Analyzer 支持的显式输入模式。"""

    COLD_FILE = "cold_file"
    WORKSPACE_DIRECTORY = "workspace_directory"
    DAYU_DIRECTORY = "dayu_directory"
    TRACE_DIRECTORY = "trace_directory"


@dataclass(frozen=True, slots=True)
class ToolTraceAnalysisSource:
    """Tool Trace Analyzer 的完整显式输入来源。

    :param requested_path: Service 已归一化的绝对 operator 输入路径。
    :param mode: 输入布局模式。
    :param cold_jsonl_path: 当前模式唯一预期的 cold JSONL 路径。
    :param hot_db_path: directory 模式唯一预期的 Host DB 路径。
    :param artifact_root: directory 模式唯一预期的 artifact root。
    :raises TypeError: 字段类型错误时抛出。
    :raises ValueError: 路径、布局、存在性或文件类型违反契约时抛出。
    """

    requested_path: Path
    mode: ToolTraceInputMode
    cold_jsonl_path: Path
    hot_db_path: Path | None
    artifact_root: Path | None

    def __post_init__(self) -> None:
        """复核显式来源的路径与 mode 不变量。

        :returns: ``None``。
        :raises TypeError: 字段类型错误时抛出。
        :raises ValueError: 路径、布局、存在性或文件类型违反契约时抛出。
        """

        _validate_source(self)


@dataclass(frozen=True, slots=True)
class ToolTraceAnalysisPolicy:
    """Tool Trace Analyzer 的诊断阈值策略。

    :param large_payload_threshold_bytes: large payload 字节阈值。
    :param payload_ranking_limit: payload 排名条目上限。
    :param latency_minimum_sample_count: latency 判断最小样本数。
    :param latency_outlier_multiplier: latency 异常倍数。
    :param latency_minimum_delta_ms: latency 异常最小绝对差值。
    :raises TypeError: 数值类型错误时抛出。
    :raises ValueError: 数值边界错误时抛出。
    """

    large_payload_threshold_bytes: int = DEFAULT_TOOL_TRACE_LARGE_PAYLOAD_THRESHOLD_BYTES
    payload_ranking_limit: int = DEFAULT_TOOL_TRACE_PAYLOAD_RANKING_LIMIT
    latency_minimum_sample_count: int = DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_SAMPLE_COUNT
    latency_outlier_multiplier: float = DEFAULT_TOOL_TRACE_LATENCY_OUTLIER_MULTIPLIER
    latency_minimum_delta_ms: int = DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_DELTA_MS

    def __post_init__(self) -> None:
        """校验诊断阈值。

        :returns: ``None``。
        :raises TypeError: 数值类型错误时抛出。
        :raises ValueError: 数值边界错误时抛出。
        """

        _require_positive_int(
            self.large_payload_threshold_bytes,
            field_name="large_payload_threshold_bytes",
        )
        _require_positive_int(
            self.payload_ranking_limit,
            field_name="payload_ranking_limit",
        )
        _require_positive_int(
            self.latency_minimum_sample_count,
            field_name="latency_minimum_sample_count",
        )
        if isinstance(self.latency_outlier_multiplier, bool) or not isinstance(self.latency_outlier_multiplier, float):
            raise TypeError("latency_outlier_multiplier must be float")
        if not math.isfinite(self.latency_outlier_multiplier) or self.latency_outlier_multiplier <= 1.0:
            raise ValueError("latency_outlier_multiplier must be finite and greater than 1.0")
        _require_positive_int(
            self.latency_minimum_delta_ms,
            field_name="latency_minimum_delta_ms",
        )


def _validate_source(source: ToolTraceAnalysisSource) -> None:
    """校验 Tool Trace 输入来源。

    :param source: 待校验来源。
    :returns: ``None``。
    :raises TypeError: 字段类型错误时抛出。
    :raises ValueError: 路径、布局、存在性或文件类型违反契约时抛出。
    """

    if not isinstance(source.mode, ToolTraceInputMode):
        raise TypeError("mode must be ToolTraceInputMode")
    _require_absolute_normalized_path(
        source.requested_path,
        field_name="requested_path",
    )
    _require_absolute_normalized_path(
        source.cold_jsonl_path,
        field_name="cold_jsonl_path",
    )
    if source.hot_db_path is not None:
        _require_absolute_normalized_path(
            source.hot_db_path,
            field_name="hot_db_path",
        )
    if source.artifact_root is not None:
        _require_absolute_normalized_path(
            source.artifact_root,
            field_name="artifact_root",
        )

    if source.mode is ToolTraceInputMode.COLD_FILE:
        _validate_cold_file_source(source)
    elif source.mode is ToolTraceInputMode.WORKSPACE_DIRECTORY:
        _validate_directory_source(
            source,
            dayu_root=source.requested_path / _DAYU_DIRECTORY_NAME,
        )
    elif source.mode is ToolTraceInputMode.DAYU_DIRECTORY:
        _validate_directory_source(source, dayu_root=source.requested_path)
    else:
        _validate_trace_directory_source(source)
    _reject_path_aliases(source)


def _validate_cold_file_source(source: ToolTraceAnalysisSource) -> None:
    """校验 cold-file 模式。

    :param source: 待校验来源。
    :returns: ``None``。
    :raises ValueError: 模式字段或文件类型不符合契约时抛出。
    """

    if source.cold_jsonl_path != source.requested_path:
        raise ValueError("cold_file cold_jsonl_path must equal requested_path")
    if source.hot_db_path is not None or source.artifact_root is not None:
        raise ValueError("cold_file must not carry hot_db_path or artifact_root")
    _require_regular_file(source.requested_path, field_name="requested_path")


def _validate_directory_source(
    source: ToolTraceAnalysisSource,
    *,
    dayu_root: Path,
) -> None:
    """校验 workspace/dayu directory 模式。

    :param source: 待校验来源。
    :param dayu_root: 当前模式预期的 ``.dayu`` 根或其内容根。
    :returns: ``None``。
    :raises ValueError: 布局、存在性或文件类型不符合契约时抛出。
    """

    _require_directory(source.requested_path, field_name="requested_path")
    expected_artifact_root = dayu_root / _ARTIFACT_DIRECTORY_NAME
    expected_cold_path = expected_artifact_root / _TOOL_TRACE_DIRECTORY_NAME / _TOOL_TRACE_COLD_FILE_NAME
    expected_hot_path = dayu_root / _HOST_DIRECTORY_NAME / _HOST_DATABASE_FILE_NAME
    if source.cold_jsonl_path != expected_cold_path:
        raise ValueError("cold_jsonl_path does not match input mode layout")
    if source.hot_db_path != expected_hot_path:
        raise ValueError("hot_db_path does not match input mode layout")
    if source.artifact_root != expected_artifact_root:
        raise ValueError("artifact_root does not match input mode layout")
    cold_exists = _path_exists(
        source.cold_jsonl_path,
        field_name="cold_jsonl_path",
    )
    hot_exists = _path_exists(expected_hot_path, field_name="hot_db_path")
    if not cold_exists and not hot_exists:
        raise ValueError("directory input requires hot DB or cold JSONL")
    if cold_exists:
        _require_regular_file(source.cold_jsonl_path, field_name="cold_jsonl_path")
    if hot_exists:
        _require_regular_file(expected_hot_path, field_name="hot_db_path")
    if _path_exists(expected_artifact_root, field_name="artifact_root"):
        _require_directory(expected_artifact_root, field_name="artifact_root")


def _validate_trace_directory_source(source: ToolTraceAnalysisSource) -> None:
    """校验 trace-directory 模式。

    :param source: 待校验来源。
    :returns: ``None``。
    :raises ValueError: 模式字段、布局或文件类型不符合契约时抛出。
    """

    _require_directory(source.requested_path, field_name="requested_path")
    expected_cold_path = source.requested_path / _TOOL_TRACE_COLD_FILE_NAME
    if source.cold_jsonl_path != expected_cold_path:
        raise ValueError("trace_directory cold_jsonl_path does not match layout")
    if source.hot_db_path is not None or source.artifact_root is not None:
        raise ValueError("trace_directory must not carry hot_db_path or artifact_root")
    _require_regular_file(source.cold_jsonl_path, field_name="cold_jsonl_path")


def _reject_path_aliases(source: ToolTraceAnalysisSource) -> None:
    """拒绝来源中承担不同语义的路径互相 alias。

    :param source: 已通过 mode 布局检查的来源。
    :returns: ``None``。
    :raises ValueError: 两个不同语义路径指向同一文件系统对象时抛出。
    """

    paths = tuple(
        path
        for path in (
            source.cold_jsonl_path,
            source.hot_db_path,
            source.artifact_root,
        )
        if path is not None
    )
    for index, left in enumerate(paths):
        for right in paths[index + 1 :]:
            if left == right:
                raise ValueError("analysis source paths must not alias")
            if (
                _path_exists(left, field_name="analysis source path")
                and _path_exists(right, field_name="analysis source path")
                and left.samefile(right)
            ):
                raise ValueError("analysis source paths must not alias")


def _require_absolute_normalized_path(value: Path, *, field_name: str) -> None:
    """校验绝对、词法归一化路径。

    :param value: 待校验路径。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: 值不是 ``Path`` 时抛出。
    :raises ValueError: 路径不是绝对归一化路径时抛出。
    """

    if not isinstance(value, Path):
        raise TypeError(f"{field_name} must be Path")
    if not value.is_absolute():
        raise ValueError(f"{field_name} must be absolute")
    if Path(os.path.normpath(os.fspath(value))) != value:
        raise ValueError(f"{field_name} must be normalized")


def _require_regular_file(value: Path, *, field_name: str) -> None:
    """校验现存 regular file。

    :param value: 待校验路径。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises ValueError: 路径缺失或不是 regular file 时抛出。
    """

    try:
        mode = value.stat().st_mode
    except OSError as exc:
        raise ValueError(f"{field_name} must be an existing regular file") from exc
    if not stat.S_ISREG(mode):
        raise ValueError(f"{field_name} must be an existing regular file")


def _path_exists(value: Path, *, field_name: str) -> bool:
    """在不吞掉 permission/I/O error 的前提下判断路径是否缺失。

    :param value: 待检查路径。
    :param field_name: 错误消息字段名。
    :returns: 路径存在时返回 ``True``，确实缺失时返回 ``False``。
    :raises ValueError: 除缺失外的 metadata 读取失败时抛出。
    """

    try:
        value.stat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ValueError(f"{field_name} metadata is unreadable") from exc
    return True


def _require_directory(value: Path, *, field_name: str) -> None:
    """校验现存 directory。

    :param value: 待校验路径。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises ValueError: 路径缺失或不是 directory 时抛出。
    """

    try:
        mode = value.stat().st_mode
    except OSError as exc:
        raise ValueError(f"{field_name} must be an existing directory") from exc
    if not stat.S_ISDIR(mode):
        raise ValueError(f"{field_name} must be an existing directory")


def _require_positive_int(value: int, *, field_name: str) -> None:
    """校验正整数。

    :param value: 待校验值。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: 值不是整数或是布尔值时抛出。
    :raises ValueError: 值不是正数时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


__all__ = [
    "DEFAULT_TOOL_TRACE_LARGE_PAYLOAD_THRESHOLD_BYTES",
    "DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_DELTA_MS",
    "DEFAULT_TOOL_TRACE_LATENCY_MINIMUM_SAMPLE_COUNT",
    "DEFAULT_TOOL_TRACE_LATENCY_OUTLIER_MULTIPLIER",
    "DEFAULT_TOOL_TRACE_PAYLOAD_RANKING_LIMIT",
    "ToolTraceAnalysisPolicy",
    "ToolTraceAnalysisSource",
    "ToolTraceInputMode",
]
