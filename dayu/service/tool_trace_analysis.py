"""Tool Trace Analyzer 的 Service 输入发现与报告发布边界。

本模块把 operator 显式路径解析为 Host public source，调用 Host public analyzer，
并把同一个 structured report 渲染为 JSON/Markdown 后原子发布。Service 不解释
Tool Trace 业务语义，也不读取 Host durable internals。
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dayu.host import (
    ToolTraceAnalysisPolicy,
    ToolTraceAnalysisReport,
    ToolTraceAnalysisSource,
    ToolTraceInputMode,
    analyze_tool_trace,
    render_tool_trace_analysis_markdown,
    tool_trace_analysis_report_to_json,
)

TOOL_TRACE_ANALYSIS_JSON_FILE_NAME = "tool-trace-analysis.json"
"""Tool Trace Analyzer JSON 报告固定文件名。"""

TOOL_TRACE_ANALYSIS_MARKDOWN_FILE_NAME = "tool-trace-analysis.md"
"""Tool Trace Analyzer Markdown 报告固定文件名。"""

_DAYU_DIRECTORY_NAME = ".dayu"
_HOST_DIRECTORY_NAME = "host"
_ARTIFACT_DIRECTORY_NAME = "artifacts"
_TOOL_TRACE_DIRECTORY_NAME = "tool-trace"
_TOOL_TRACE_COLD_FILE_NAME = "tool-trace-cold.jsonl"
_HOST_DATABASE_FILE_NAME = "dayu_host.sqlite3"
_TEMPORARY_FILE_PREFIX = ".tool-trace-analysis-"
_TEMPORARY_FILE_SUFFIX = ".tmp"
_ERROR_SUMMARY_MAX_CHARS = 240


class ServiceToolTraceAnalysisUsageError(ValueError):
    """Tool Trace Analyzer 的用户输入路径或布局错误。"""


@dataclass(frozen=True, slots=True)
class ServiceToolTracePublishFailure:
    """一次 report replace 的 primary failure。

    :param target_path: 原子 replace 的最终目标路径。
    :param error_summary: 有界底层错误摘要。
    """

    target_path: Path
    error_summary: str


@dataclass(frozen=True, slots=True)
class ServiceToolTraceCleanupFailure:
    """一次 best-effort 临时文件清理的 secondary failure。

    :param failed_paths: 未能清理的本次临时文件路径。
    :param error_summary: 有界 secondary 错误摘要。
    """

    failed_paths: tuple[Path, ...]
    error_summary: str


class ServiceToolTraceAnalysisPublishError(Exception):
    """Tool Trace 报告原子发布失败。

    :param published_paths: 本次已经成功 replace 的最终报告路径。
    :param failed_path: primary replace 失败对应的最终目标路径。
    :param primary_publish_error: primary replace 的 typed detail。
    :param cleanup_error: 可选临时文件 cleanup secondary detail。
    :param temporary_paths_cleaned: 本次仍存在的临时文件是否全部清理。
    """

    published_paths: tuple[Path, ...]
    failed_path: Path
    primary_publish_error: ServiceToolTracePublishFailure
    cleanup_error: ServiceToolTraceCleanupFailure | None
    temporary_paths_cleaned: bool

    def __init__(
        self,
        *,
        published_paths: tuple[Path, ...],
        failed_path: Path,
        primary_publish_error: ServiceToolTracePublishFailure,
        cleanup_error: ServiceToolTraceCleanupFailure | None,
        temporary_paths_cleaned: bool,
    ) -> None:
        """初始化 typed publication failure。

        :param published_paths: 本次已发布的最终路径。
        :param failed_path: primary replace 的最终目标路径。
        :param primary_publish_error: primary failure detail。
        :param cleanup_error: 可选 secondary cleanup detail。
        :param temporary_paths_cleaned: 本次临时文件是否全部清理。
        :returns: ``None``。
        :raises TypeError: 父类异常初始化失败时抛出。
        """

        self.published_paths = published_paths
        self.failed_path = failed_path
        self.primary_publish_error = primary_publish_error
        self.cleanup_error = cleanup_error
        self.temporary_paths_cleaned = temporary_paths_cleaned
        super().__init__(
            f"tool trace report publish failed: {failed_path}: "
            f"{primary_publish_error.error_summary}"
        )


@dataclass(frozen=True, slots=True)
class ServiceToolTraceAnalysisResult:
    """一次成功的 Tool Trace 分析与发布结果。

    :param source: Service 发现并由 Host public boundary 复核的输入来源。
    :param report: Host public analyzer 返回的 structured report。
    :param json_path: 已发布 JSON 报告路径。
    :param markdown_path: 已发布 Markdown 报告路径。
    """

    source: ToolTraceAnalysisSource
    report: ToolTraceAnalysisReport
    json_path: Path
    markdown_path: Path

    @property
    def published_paths(self) -> tuple[Path, Path]:
        """返回固定 JSON 后 Markdown 的已发布路径。

        :returns: 两个最终报告路径。
        :raises: 无。
        """

        return (self.json_path, self.markdown_path)


def discover_tool_trace_analysis_source(
    input_path: Path,
) -> ToolTraceAnalysisSource:
    """发现 operator 显式输入对应的四种 Tool Trace source mode。

    :param input_path: operator 显式传入的文件或目录路径。
    :returns: 绝对、词法归一化且通过 Host public contract 复核的 source。
    :raises TypeError: ``input_path`` 不是 ``Path`` 时抛出。
    :raises ServiceToolTraceAnalysisUsageError: 路径缺失、类型错误、布局不支持
        或同时匹配多个目录布局时抛出。
    """

    if not isinstance(input_path, Path):
        raise TypeError("input_path must be Path")
    requested_path = _absolute_normalized_path(input_path)
    if not requested_path.exists():
        raise ServiceToolTraceAnalysisUsageError(
            f"输入路径不存在：{requested_path}"
        )
    if requested_path.is_file():
        if requested_path.suffix.lower() != ".jsonl":
            raise ServiceToolTraceAnalysisUsageError(
                f"输入文件必须是 JSONL 文件：{requested_path}"
            )
        return _build_source(
            requested_path=requested_path,
            mode=ToolTraceInputMode.COLD_FILE,
            cold_jsonl_path=requested_path,
            hot_db_path=None,
            artifact_root=None,
        )
    if not requested_path.is_dir():
        raise ServiceToolTraceAnalysisUsageError(
            f"输入路径必须是普通文件或目录：{requested_path}"
        )
    return _discover_directory_source(requested_path)


def analyze_and_publish_tool_trace(
    input_path: Path,
    output_dir: Path,
) -> ServiceToolTraceAnalysisResult:
    """分析 Tool Trace 并把同源 JSON/Markdown 原子发布到输出目录。

    :param input_path: operator 显式输入文件或目录。
    :param output_dir: 报告输出目录；不存在时由 Service 创建。
    :returns: structured report、source 与两个已发布路径。
    :raises TypeError: 参数不是 ``Path`` 时抛出。
    :raises ServiceToolTraceAnalysisUsageError: 输入路径或布局不合法时抛出。
    :raises ServiceToolTraceAnalysisPublishError: 任一原子 replace 失败时抛出。
    :raises OSError: 输出目录创建、临时文件写入或 flush 失败时抛出。
    :raises ToolTraceAnalysisInputError: Host 无法建立可信输入边界时透传。
    """

    if not isinstance(input_path, Path):
        raise TypeError("input_path must be Path")
    if not isinstance(output_dir, Path):
        raise TypeError("output_dir must be Path")
    source = discover_tool_trace_analysis_source(input_path)
    report = analyze_tool_trace(source, ToolTraceAnalysisPolicy())
    json_text = tool_trace_analysis_report_to_json(report)
    markdown_text = render_tool_trace_analysis_markdown(report)
    normalized_output_dir = _absolute_normalized_path(output_dir)
    normalized_output_dir.mkdir(parents=True, exist_ok=True)
    if not normalized_output_dir.is_dir():
        raise NotADirectoryError(
            f"输出路径不是目录：{normalized_output_dir}"
        )
    json_path = normalized_output_dir / TOOL_TRACE_ANALYSIS_JSON_FILE_NAME
    markdown_path = (
        normalized_output_dir / TOOL_TRACE_ANALYSIS_MARKDOWN_FILE_NAME
    )
    _publish_report_pair(
        json_text=json_text,
        markdown_text=markdown_text,
        json_path=json_path,
        markdown_path=markdown_path,
    )
    return ServiceToolTraceAnalysisResult(
        source=source,
        report=report,
        json_path=json_path,
        markdown_path=markdown_path,
    )


def _discover_directory_source(
    requested_path: Path,
) -> ToolTraceAnalysisSource:
    """发现目录输入的唯一受支持布局。

    :param requested_path: 已归一化的绝对现存目录。
    :returns: 唯一匹配布局对应的 source。
    :raises ServiceToolTraceAnalysisUsageError: 没有布局或布局冲突时抛出。
    """

    workspace_dayu_root = requested_path / _DAYU_DIRECTORY_NAME
    workspace_candidate = _directory_candidate(
        mode=ToolTraceInputMode.WORKSPACE_DIRECTORY,
        dayu_root=workspace_dayu_root,
    )
    dayu_candidate = _directory_candidate(
        mode=ToolTraceInputMode.DAYU_DIRECTORY,
        dayu_root=requested_path,
    )
    trace_cold_path = requested_path / _TOOL_TRACE_COLD_FILE_NAME
    trace_candidate = (
        (
            ToolTraceInputMode.TRACE_DIRECTORY,
            trace_cold_path,
            None,
            None,
        )
        if _path_lexically_exists(trace_cold_path)
        else None
    )
    candidates = tuple(
        candidate
        for candidate in (
            workspace_candidate,
            dayu_candidate,
            trace_candidate,
        )
        if candidate is not None
    )
    if not candidates:
        raise ServiceToolTraceAnalysisUsageError(
            f"目录不包含受支持的 Tool Trace 布局：{requested_path}"
        )
    if len(candidates) != 1:
        modes = ", ".join(candidate[0].value for candidate in candidates)
        raise ServiceToolTraceAnalysisUsageError(
            f"目录同时匹配多个 Tool Trace 布局（{modes}）；"
            "请传入更具体的 .dayu 目录或 cold JSONL 文件。"
        )
    mode, cold_jsonl_path, hot_db_path, artifact_root = candidates[0]
    return _build_source(
        requested_path=requested_path,
        mode=mode,
        cold_jsonl_path=cold_jsonl_path,
        hot_db_path=hot_db_path,
        artifact_root=artifact_root,
    )


def _directory_candidate(
    *,
    mode: ToolTraceInputMode,
    dayu_root: Path,
) -> tuple[ToolTraceInputMode, Path, Path, Path] | None:
    """构造 workspace/dayu 目录布局候选。

    :param mode: workspace 或 dayu mode。
    :param dayu_root: 当前候选的 Dayu runtime 根。
    :returns: hot/cold 任一词法存在时返回候选，否则返回 ``None``。
    :raises: 无。
    """

    artifact_root = dayu_root / _ARTIFACT_DIRECTORY_NAME
    cold_path = (
        artifact_root
        / _TOOL_TRACE_DIRECTORY_NAME
        / _TOOL_TRACE_COLD_FILE_NAME
    )
    hot_path = (
        dayu_root / _HOST_DIRECTORY_NAME / _HOST_DATABASE_FILE_NAME
    )
    if not (
        _path_lexically_exists(cold_path)
        or _path_lexically_exists(hot_path)
    ):
        return None
    return (mode, cold_path, hot_path, artifact_root)


def _build_source(
    *,
    requested_path: Path,
    mode: ToolTraceInputMode,
    cold_jsonl_path: Path,
    hot_db_path: Path | None,
    artifact_root: Path | None,
) -> ToolTraceAnalysisSource:
    """在 Service discovery 后调用 Host public source boundary 复核布局。

    :param requested_path: operator 请求路径。
    :param mode: Service 发现的 mode。
    :param cold_jsonl_path: 唯一 expected cold 路径。
    :param hot_db_path: 唯一 expected hot 路径。
    :param artifact_root: 唯一 expected artifact root。
    :returns: Host public source。
    :raises ServiceToolTraceAnalysisUsageError: Host source contract 拒绝时抛出。
    """

    try:
        return ToolTraceAnalysisSource(
            requested_path=requested_path,
            mode=mode,
            cold_jsonl_path=cold_jsonl_path,
            hot_db_path=hot_db_path,
            artifact_root=artifact_root,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise ServiceToolTraceAnalysisUsageError(
            f"Tool Trace 输入布局无效：{_bounded_error_summary(exc)}"
        ) from exc


def _publish_report_pair(
    *,
    json_text: str,
    markdown_text: str,
    json_path: Path,
    markdown_path: Path,
) -> None:
    """按 JSON 后 Markdown 的固定顺序原子发布报告对。

    :param json_text: 从 structured report 渲染的 JSON。
    :param markdown_text: 从同一 report 渲染的 Markdown。
    :param json_path: JSON 最终路径。
    :param markdown_path: Markdown 最终路径。
    :returns: ``None``。
    :raises OSError: 临时文件创建、写入或 flush 失败时抛出。
    :raises ServiceToolTraceAnalysisPublishError: 任一 replace 失败时抛出。
    """

    temporary_paths: list[Path] = []
    try:
        json_temporary_path = _write_temporary_text(json_path.parent, json_text)
        temporary_paths.append(json_temporary_path)
        markdown_temporary_path = _write_temporary_text(
            markdown_path.parent,
            markdown_text,
        )
        temporary_paths.append(markdown_temporary_path)
    except OSError:
        _cleanup_temporary_paths(tuple(temporary_paths))
        raise

    published_paths: list[Path] = []
    pending_temporary_paths = list(temporary_paths)
    for temporary_path, target_path in (
        (json_temporary_path, json_path),
        (markdown_temporary_path, markdown_path),
    ):
        try:
            _replace_temporary_file(temporary_path, target_path)
        except OSError as exc:
            cleanup_error = _cleanup_temporary_paths(
                tuple(pending_temporary_paths)
            )
            primary_error = ServiceToolTracePublishFailure(
                target_path=target_path,
                error_summary=_bounded_error_summary(exc),
            )
            raise ServiceToolTraceAnalysisPublishError(
                published_paths=tuple(published_paths),
                failed_path=target_path,
                primary_publish_error=primary_error,
                cleanup_error=cleanup_error,
                temporary_paths_cleaned=cleanup_error is None,
            ) from exc
        pending_temporary_paths.remove(temporary_path)
        published_paths.append(target_path)


def _write_temporary_text(output_dir: Path, content: str) -> Path:
    """在最终目录内写入并 flush 一个严格 UTF-8 临时文件。

    :param output_dir: 最终 report 所在目录。
    :param content: 待写入文本。
    :returns: 已关闭的同目录临时文件路径。
    :raises OSError: 临时文件创建、写入、flush 或关闭失败时抛出。
    """

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        errors="strict",
        dir=output_dir,
        prefix=_TEMPORARY_FILE_PREFIX,
        suffix=_TEMPORARY_FILE_SUFFIX,
        delete=False,
    ) as temporary_file:
        temporary_file.write(content)
        temporary_file.flush()
        return Path(temporary_file.name)


def _cleanup_temporary_paths(
    temporary_paths: tuple[Path, ...],
) -> ServiceToolTraceCleanupFailure | None:
    """best-effort 清理仍存在的本次临时文件。

    :param temporary_paths: 本次创建的临时路径。
    :returns: 全部清理成功返回 ``None``；否则返回独立 secondary detail。
    :raises: 无。
    """

    failures: list[tuple[Path, str]] = []
    for path in temporary_paths:
        try:
            _unlink_temporary_file(path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            failures.append((path, _bounded_error_summary(exc)))
    if not failures:
        return None
    return ServiceToolTraceCleanupFailure(
        failed_paths=tuple(path for path, _summary in failures),
        error_summary="; ".join(
            f"{path.name}: {summary}" for path, summary in failures
        )[:_ERROR_SUMMARY_MAX_CHARS],
    )


def _replace_temporary_file(
    temporary_path: Path,
    target_path: Path,
) -> None:
    """把同目录临时文件原子替换到最终路径。

    :param temporary_path: 已 flush 并关闭的临时文件。
    :param target_path: 最终报告路径。
    :returns: ``None``。
    :raises OSError: ``os.replace`` 失败时抛出。
    """

    os.replace(temporary_path, target_path)


def _unlink_temporary_file(path: Path) -> None:
    """删除一个本次临时文件。

    :param path: 待清理路径。
    :returns: ``None``。
    :raises OSError: unlink 失败时抛出。
    """

    path.unlink()


def _absolute_normalized_path(path: Path) -> Path:
    """把路径转为绝对词法归一化形式而不解析不存在的 child。

    :param path: 原始路径。
    :returns: 绝对词法归一化路径。
    :raises OSError: 当前工作目录读取失败时抛出。
    """

    return Path(os.path.abspath(os.path.normpath(os.fspath(path))))


def _path_lexically_exists(path: Path) -> bool:
    """判断 path 或 dangling symlink 是否词法存在。

    :param path: 待检查路径。
    :returns: path entry 存在返回 ``True``。
    :raises: 无。
    """

    return os.path.lexists(path)


def _bounded_error_summary(exc: BaseException) -> str:
    """把底层错误投影为不超过固定长度的摘要。

    :param exc: 底层异常。
    :returns: 包含异常类型的有界单行摘要。
    :raises: 无。
    """

    detail = str(exc).replace("\r", " ").replace("\n", " ")
    return f"{type(exc).__name__}: {detail}"[:_ERROR_SUMMARY_MAX_CHARS]


__all__ = (
    "ServiceToolTraceAnalysisPublishError",
    "ServiceToolTraceAnalysisResult",
    "ServiceToolTraceAnalysisUsageError",
    "ServiceToolTraceCleanupFailure",
    "ServiceToolTracePublishFailure",
    "TOOL_TRACE_ANALYSIS_JSON_FILE_NAME",
    "TOOL_TRACE_ANALYSIS_MARKDOWN_FILE_NAME",
    "analyze_and_publish_tool_trace",
    "discover_tool_trace_analysis_source",
)
