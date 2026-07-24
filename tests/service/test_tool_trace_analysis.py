"""Tool Trace Analyzer Service 发现与原子发布测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

import dayu.service.tool_trace_analysis as service_analysis
from dayu.host import (
    ToolTraceAnalysisPolicy,
    ToolTraceAnalysisReport,
    ToolTraceAnalysisSource,
    ToolTraceInputMode,
)
from dayu.service.tool_trace_analysis import (
    ServiceToolTraceAnalysisPublishError,
    ServiceToolTraceAnalysisUsageError,
    analyze_and_publish_tool_trace,
    discover_tool_trace_analysis_source,
)


class _ReplaceFailure:
    """在指定调用序号模拟原子 replace 失败。"""

    call_count: int
    fail_call: int

    def __init__(self, *, fail_call: int) -> None:
        """初始化 replace failure recorder。

        :param fail_call: 从 1 开始的失败调用序号。
        :returns: ``None``。
        :raises: 无。
        """

        self.call_count = 0
        self.fail_call = fail_call

    def __call__(self, temporary_path: Path, target_path: Path) -> None:
        """执行真实 replace 或在目标调用抛出错误。

        :param temporary_path: 本次临时文件路径。
        :param target_path: 最终报告路径。
        :returns: ``None``。
        :raises OSError: 当前调用命中 ``fail_call`` 时抛出。
        """

        self.call_count += 1
        if self.call_count == self.fail_call:
            raise OSError(f"replace-{self.call_count}-failed")
        temporary_path.replace(target_path)


class _CleanupFailure:
    """记录并拒绝临时文件 cleanup。"""

    paths: list[Path]

    def __init__(self) -> None:
        """初始化 cleanup failure recorder。

        :returns: ``None``。
        :raises: 无。
        """

        self.paths = []

    def __call__(self, path: Path) -> None:
        """记录 cleanup target 后抛出错误。

        :param path: 本次 cleanup path。
        :returns: 正常路径不会返回。
        :raises OSError: 始终抛出。
        """

        self.paths.append(path)
        raise OSError("cleanup-failed")


def _write_empty_cold_file(path: Path) -> Path:
    """创建可被 strict analyzer 接受的空 cold JSONL。

    :param path: 目标文件路径。
    :returns: 目标路径。
    :raises OSError: 目录或文件创建失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def _temporary_reports(output_dir: Path) -> tuple[Path, ...]:
    """列出 output dir 内仍残留的 Analyzer 临时文件。

    :param output_dir: 报告输出目录。
    :returns: 稳定排序的临时文件路径。
    :raises OSError: 目录扫描失败时抛出。
    """

    return tuple(sorted(output_dir.glob(".tool-trace-analysis-*.tmp")))


def test_discovers_all_four_explicit_input_modes(tmp_path: Path) -> None:
    """Service 必须从显式路径发现四种模式并构造完整 source。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: mode 或显式路径布局漂移时抛出。
    """

    cold_file = _write_empty_cold_file(tmp_path / "single.jsonl")
    workspace = tmp_path / "workspace"
    workspace_cold = _write_empty_cold_file(
        workspace
        / ".dayu"
        / "artifacts"
        / "tool-trace"
        / "tool-trace-cold.jsonl"
    )
    dayu_directory = tmp_path / "runtime"
    dayu_hot = _write_empty_cold_file(
        dayu_directory / "host" / "dayu_host.sqlite3"
    )
    trace_directory = tmp_path / "trace"
    trace_cold = _write_empty_cold_file(
        trace_directory / "tool-trace-cold.jsonl"
    )

    cold_source = discover_tool_trace_analysis_source(cold_file)
    workspace_source = discover_tool_trace_analysis_source(workspace)
    dayu_source = discover_tool_trace_analysis_source(dayu_directory)
    trace_source = discover_tool_trace_analysis_source(trace_directory)

    assert cold_source.mode is ToolTraceInputMode.COLD_FILE
    assert cold_source.cold_jsonl_path == cold_file
    assert workspace_source.mode is ToolTraceInputMode.WORKSPACE_DIRECTORY
    assert workspace_source.cold_jsonl_path == workspace_cold
    assert workspace_source.hot_db_path == (
        workspace / ".dayu" / "host" / "dayu_host.sqlite3"
    )
    assert dayu_source.mode is ToolTraceInputMode.DAYU_DIRECTORY
    assert dayu_source.hot_db_path == dayu_hot
    assert dayu_source.artifact_root == dayu_directory / "artifacts"
    assert trace_source.mode is ToolTraceInputMode.TRACE_DIRECTORY
    assert trace_source.cold_jsonl_path == trace_cold
    assert trace_source.hot_db_path is None


def test_directory_discovery_accepts_hot_only_cold_only_and_missing_artifact_root(
    tmp_path: Path,
) -> None:
    """目录发现保留 hot/cold capability 给 Host，不在 Service 复制 bool 真源。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 合法 partial layout 被 Service 拒绝时抛出。
    """

    hot_only = tmp_path / "hot-only"
    _write_empty_cold_file(
        hot_only / ".dayu" / "host" / "dayu_host.sqlite3"
    )
    cold_only = tmp_path / "cold-only"
    _write_empty_cold_file(
        cold_only
        / ".dayu"
        / "artifacts"
        / "tool-trace"
        / "tool-trace-cold.jsonl"
    )

    hot_source = discover_tool_trace_analysis_source(hot_only)
    cold_source = discover_tool_trace_analysis_source(cold_only)

    assert hot_source.mode is ToolTraceInputMode.WORKSPACE_DIRECTORY
    assert not hot_source.cold_jsonl_path.exists()
    assert hot_source.artifact_root is not None
    assert not hot_source.artifact_root.exists()
    assert cold_source.mode is ToolTraceInputMode.WORKSPACE_DIRECTORY
    assert cold_source.hot_db_path is not None
    assert not cold_source.hot_db_path.exists()


def test_directory_discovery_rejects_ambiguous_and_unsupported_paths(
    tmp_path: Path,
) -> None:
    """Service 对多布局和无布局目录 fail closed。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 非法布局没有 typed usage failure 时抛出。
    """

    ambiguous = tmp_path / "ambiguous"
    _write_empty_cold_file(
        ambiguous
        / ".dayu"
        / "artifacts"
        / "tool-trace"
        / "tool-trace-cold.jsonl"
    )
    _write_empty_cold_file(ambiguous / "tool-trace-cold.jsonl")
    unsupported = tmp_path / "unsupported"
    unsupported.mkdir()
    non_jsonl = _write_empty_cold_file(tmp_path / "trace.txt")

    with pytest.raises(
        ServiceToolTraceAnalysisUsageError,
        match="同时匹配多个",
    ):
        discover_tool_trace_analysis_source(ambiguous)
    with pytest.raises(
        ServiceToolTraceAnalysisUsageError,
        match="不包含受支持",
    ):
        discover_tool_trace_analysis_source(unsupported)
    with pytest.raises(
        ServiceToolTraceAnalysisUsageError,
        match="JSONL",
    ):
        discover_tool_trace_analysis_source(non_jsonl)


def test_analysis_calls_host_public_api_and_renders_same_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Service 调 Host public API，两个 renderer 必须消费同一 report identity。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch。
    :returns: ``None``。
    :raises AssertionError: call path 或 report identity 漂移时抛出。
    """

    cold_file = _write_empty_cold_file(tmp_path / "trace.jsonl")
    output_dir = tmp_path / "reports"
    original_analyze = service_analysis.analyze_tool_trace
    original_json = service_analysis.tool_trace_analysis_report_to_json
    original_markdown = service_analysis.render_tool_trace_analysis_markdown
    analyzed_sources: list[ToolTraceAnalysisSource] = []
    rendered_report_ids: list[int] = []

    def tracked_analyze(
        source: ToolTraceAnalysisSource,
        policy: ToolTraceAnalysisPolicy,
    ) -> ToolTraceAnalysisReport:
        """记录 public analyze 调用后执行真实 Host analyzer。

        :param source: Service 发现的 source。
        :param policy: 默认 Analyzer policy。
        :returns: Host structured report。
        :raises Exception: 真实 analyzer 失败时透传。
        """

        analyzed_sources.append(source)
        return original_analyze(source, policy)

    def tracked_json(report: ToolTraceAnalysisReport) -> str:
        """记录 JSON renderer 的 report identity。

        :param report: Host structured report。
        :returns: JSON 文本。
        :raises Exception: 真实 renderer 失败时透传。
        """

        rendered_report_ids.append(id(report))
        return original_json(report)

    def tracked_markdown(report: ToolTraceAnalysisReport) -> str:
        """记录 Markdown renderer 的 report identity。

        :param report: Host structured report。
        :returns: Markdown 文本。
        :raises Exception: 真实 renderer 失败时透传。
        """

        rendered_report_ids.append(id(report))
        return original_markdown(report)

    monkeypatch.setattr(service_analysis, "analyze_tool_trace", tracked_analyze)
    monkeypatch.setattr(
        service_analysis,
        "tool_trace_analysis_report_to_json",
        tracked_json,
    )
    monkeypatch.setattr(
        service_analysis,
        "render_tool_trace_analysis_markdown",
        tracked_markdown,
    )

    result = analyze_and_publish_tool_trace(cold_file, output_dir)

    assert analyzed_sources == [result.source]
    assert rendered_report_ids == [id(result.report), id(result.report)]
    assert result.json_path.read_text(encoding="utf-8").startswith("{\n")
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert markdown.startswith("# Tool Trace Analysis")
    assert "无法证明" in markdown


def test_first_replace_failure_keeps_old_reports_and_publishes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """第一次 replace 失败不得删除旧报告或漂移 published/failed paths。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch。
    :returns: ``None``。
    :raises AssertionError: partial publication contract 漂移时抛出。
    """

    cold_file = _write_empty_cold_file(tmp_path / "trace.jsonl")
    output_dir = tmp_path / "reports"
    output_dir.mkdir()
    json_path = output_dir / "tool-trace-analysis.json"
    markdown_path = output_dir / "tool-trace-analysis.md"
    json_path.write_text("old-json", encoding="utf-8")
    markdown_path.write_text("old-markdown", encoding="utf-8")
    replace_failure = _ReplaceFailure(fail_call=1)
    monkeypatch.setattr(
        service_analysis,
        "_replace_temporary_file",
        replace_failure,
    )

    with pytest.raises(ServiceToolTraceAnalysisPublishError) as raised:
        analyze_and_publish_tool_trace(cold_file, output_dir)

    error = raised.value
    assert error.published_paths == ()
    assert error.failed_path == json_path
    assert error.primary_publish_error.target_path == json_path
    assert error.cleanup_error is None
    assert error.temporary_paths_cleaned is True
    assert json_path.read_text(encoding="utf-8") == "old-json"
    assert markdown_path.read_text(encoding="utf-8") == "old-markdown"
    assert _temporary_reports(output_dir) == ()


@pytest.mark.parametrize("old_markdown_exists", (False, True))
def test_second_replace_failure_keeps_new_json_and_existing_markdown_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    old_markdown_exists: bool,
) -> None:
    """第二次 replace 失败只承诺 JSON 已发布，并保留旧 Markdown 状态。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch。
    :param old_markdown_exists: 失败前是否存在旧 Markdown。
    :returns: ``None``。
    :raises AssertionError: partial publication contract 漂移时抛出。
    """

    cold_file = _write_empty_cold_file(tmp_path / "trace.jsonl")
    output_dir = tmp_path / "reports"
    output_dir.mkdir()
    json_path = output_dir / "tool-trace-analysis.json"
    markdown_path = output_dir / "tool-trace-analysis.md"
    json_path.write_text("old-json", encoding="utf-8")
    if old_markdown_exists:
        markdown_path.write_text("old-markdown", encoding="utf-8")
    replace_failure = _ReplaceFailure(fail_call=2)
    monkeypatch.setattr(
        service_analysis,
        "_replace_temporary_file",
        replace_failure,
    )

    with pytest.raises(ServiceToolTraceAnalysisPublishError) as raised:
        analyze_and_publish_tool_trace(cold_file, output_dir)

    error = raised.value
    assert error.published_paths == (json_path,)
    assert error.failed_path == markdown_path
    assert error.primary_publish_error.target_path == markdown_path
    assert error.cleanup_error is None
    assert error.temporary_paths_cleaned is True
    assert json_path.read_text(encoding="utf-8").startswith("{\n")
    assert markdown_path.exists() is old_markdown_exists
    if old_markdown_exists:
        assert markdown_path.read_text(encoding="utf-8") == "old-markdown"
    assert _temporary_reports(output_dir) == ()


@pytest.mark.parametrize(
    ("replace_failure_call", "expected_published_name", "expected_failed_name"),
    (
        (1, None, "tool-trace-analysis.json"),
        (2, "tool-trace-analysis.json", "tool-trace-analysis.md"),
    ),
)
def test_cleanup_secondary_failure_does_not_change_primary_publication_truth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replace_failure_call: int,
    expected_published_name: str | None,
    expected_failed_name: str,
) -> None:
    """cleanup secondary failure 不得覆盖 replace primary path 与 published truth。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch。
    :param replace_failure_call: 模拟失败的 replace 调用序号。
    :param expected_published_name: 预期唯一已发布文件名。
    :param expected_failed_name: 预期 primary failed target 文件名。
    :returns: ``None``。
    :raises AssertionError: typed primary/secondary 分离失效时抛出。
    """

    cold_file = _write_empty_cold_file(tmp_path / "trace.jsonl")
    output_dir = tmp_path / "reports"
    output_dir.mkdir()
    replace_failure = _ReplaceFailure(fail_call=replace_failure_call)
    cleanup_failure = _CleanupFailure()
    monkeypatch.setattr(
        service_analysis,
        "_replace_temporary_file",
        replace_failure,
    )
    monkeypatch.setattr(
        service_analysis,
        "_unlink_temporary_file",
        cleanup_failure,
    )

    with pytest.raises(ServiceToolTraceAnalysisPublishError) as raised:
        analyze_and_publish_tool_trace(cold_file, output_dir)

    error = raised.value
    expected_published_paths = (
        ()
        if expected_published_name is None
        else (output_dir / expected_published_name,)
    )
    assert error.published_paths == expected_published_paths
    assert error.failed_path == output_dir / expected_failed_name
    assert error.primary_publish_error.target_path == error.failed_path
    assert error.cleanup_error is not None
    assert error.cleanup_error.failed_paths == tuple(cleanup_failure.paths)
    assert error.temporary_paths_cleaned is False
    assert all(path.parent == output_dir for path in cleanup_failure.paths)


def test_existing_non_directory_output_fails_without_changing_input(
    tmp_path: Path,
) -> None:
    """既有非目录 output path 属于执行失败且不得改变输入。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 输入或 output failure 语义漂移时抛出。
    """

    cold_file = _write_empty_cold_file(tmp_path / "trace.jsonl")
    original = cold_file.read_bytes()
    output_file = tmp_path / "report-target"
    output_file.write_text("sentinel", encoding="utf-8")

    with pytest.raises(FileExistsError):
        analyze_and_publish_tool_trace(cold_file, output_file)

    assert cold_file.read_bytes() == original
    assert output_file.read_text(encoding="utf-8") == "sentinel"
