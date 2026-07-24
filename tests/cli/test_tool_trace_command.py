"""``dayu-cli tool_trace analyze`` 命令测试。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import dayu.cli.commands.tool_trace as tool_trace_command
import dayu.cli.main as cli_main
from dayu.cli.arg_parsing import COMMAND_TOOL_TRACE
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
from dayu.service.tool_trace_analysis import (
    ServiceToolTraceAnalysisPublishError,
    ServiceToolTraceCleanupFailure,
    ServiceToolTracePublishFailure,
)


def _write_cold_file(path: Path, content: str = "") -> Path:
    """写入测试 cold JSONL。

    :param path: 目标路径。
    :param content: JSONL 文本。
    :returns: 目标路径。
    :raises OSError: 写入失败时抛出。
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_cli_success_prints_both_published_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """真实 CLI runner 成功发布两个非空 report 并返回 0。

    :param tmp_path: pytest 临时目录。
    :param capsys: pytest 标准流捕获。
    :returns: ``None``。
    :raises AssertionError: 成功输出或退出码错误时抛出。
    """

    cold_file = _write_cold_file(tmp_path / "trace.jsonl")
    output_dir = tmp_path / "reports"

    exit_code = cli_main.main(
        (
            "tool_trace",
            "analyze",
            str(cold_file),
            "--output-dir",
            str(output_dir),
        )
    )

    captured = capsys.readouterr()
    assert exit_code == EXIT_SUCCESS
    assert "JSON report:" in captured.out
    assert "Markdown report:" in captured.out
    assert captured.err == ""
    assert (output_dir / "tool-trace-analysis.json").stat().st_size > 0
    assert (output_dir / "tool-trace-analysis.md").stat().st_size > 0


def test_cli_findings_do_not_change_success_exit_code(
    tmp_path: Path,
) -> None:
    """report 内 input finding 不改变成功发布退出码。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: diagnostic severity 被误映射为失败时抛出。
    """

    cold_file = _write_cold_file(tmp_path / "trace.jsonl", "{}\n")

    exit_code = cli_main.main(
        (
            "tool_trace",
            "analyze",
            str(cold_file),
            "--output-dir",
            str(tmp_path / "reports"),
        )
    )

    assert exit_code == EXIT_SUCCESS


def test_cli_usage_error_returns_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """不存在 input 由 Service typed usage error 映射为退出码 2。

    :param tmp_path: pytest 临时目录。
    :param capsys: pytest 标准流捕获。
    :returns: ``None``。
    :raises AssertionError: usage 映射错误时抛出。
    """

    exit_code = cli_main.main(
        (
            "tool_trace",
            "analyze",
            str(tmp_path / "missing"),
            "--output-dir",
            str(tmp_path / "reports"),
        )
    )

    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE_ERROR
    assert "输入路径不存在" in captured.err


def test_cli_analysis_failure_returns_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Host/Service analysis failure 映射为退出码 1。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch。
    :param capsys: pytest 标准流捕获。
    :returns: ``None``。
    :raises AssertionError: failure 映射错误时抛出。
    """

    cold_file = _write_cold_file(tmp_path / "trace.jsonl")

    def raise_analysis_failure(
        _input_path: Path,
        _output_dir: Path,
    ) -> None:
        """模拟 Service analysis failure。

        :param _input_path: CLI input。
        :param _output_dir: CLI output dir。
        :returns: 正常路径不会返回。
        :raises RuntimeError: 始终抛出。
        """

        raise RuntimeError("analysis-failed")

    monkeypatch.setattr(
        tool_trace_command,
        "analyze_and_publish_tool_trace",
        raise_analysis_failure,
    )
    args = cli_main.parse_cli_args(
        (
            "tool_trace",
            "analyze",
            str(cold_file),
            "--output-dir",
            str(tmp_path / "reports"),
        )
    )

    exit_code = tool_trace_command.run_tool_trace_command(args)

    captured = capsys.readouterr()
    assert exit_code == EXIT_FAILURE
    assert "analysis-failed" in captured.err


def test_cli_publication_failure_prints_published_and_failed_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """partial publication failure 同时展示已发布与失败目标并返回 1。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch。
    :param capsys: pytest 标准流捕获。
    :returns: ``None``。
    :raises AssertionError: typed failure 展示漂移时抛出。
    """

    cold_file = _write_cold_file(tmp_path / "trace.jsonl")
    json_path = tmp_path / "reports" / "tool-trace-analysis.json"
    markdown_path = tmp_path / "reports" / "tool-trace-analysis.md"

    def raise_publish_failure(
        _input_path: Path,
        _output_dir: Path,
    ) -> None:
        """模拟第二次 replace 失败。

        :param _input_path: CLI input。
        :param _output_dir: CLI output dir。
        :returns: 正常路径不会返回。
        :raises ServiceToolTraceAnalysisPublishError: 始终抛出。
        """

        raise ServiceToolTraceAnalysisPublishError(
            published_paths=(json_path,),
            failed_path=markdown_path,
            primary_publish_error=ServiceToolTracePublishFailure(
                target_path=markdown_path,
                error_summary="OSError: replace-failed",
            ),
            cleanup_error=None,
            temporary_paths_cleaned=True,
        )

    monkeypatch.setattr(
        tool_trace_command,
        "analyze_and_publish_tool_trace",
        raise_publish_failure,
    )
    args = cli_main.parse_cli_args(
        (
            "tool_trace",
            "analyze",
            str(cold_file),
            "--output-dir",
            str(tmp_path / "reports"),
        )
    )

    exit_code = tool_trace_command.run_tool_trace_command(args)

    captured = capsys.readouterr()
    assert exit_code == EXIT_FAILURE
    assert f"已发布路径：{json_path}" in captured.err
    assert f"发布失败路径：{markdown_path}" in captured.err
    assert "replace-failed" in captured.err


def test_cli_publication_cleanup_failure_is_reported_separately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI 独立展示 cleanup secondary detail，不覆盖 primary target。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch。
    :param capsys: pytest 标准流捕获。
    :returns: ``None``。
    :raises AssertionError: primary/secondary 展示混合时抛出。
    """

    cold_file = _write_cold_file(tmp_path / "trace.jsonl")
    json_path = tmp_path / "reports" / "tool-trace-analysis.json"
    temporary_path = tmp_path / "reports" / ".report.tmp"

    def raise_publish_failure(
        _input_path: Path,
        _output_dir: Path,
    ) -> None:
        """模拟同时存在 primary 与 secondary failure。

        :param _input_path: CLI input。
        :param _output_dir: CLI output dir。
        :returns: 正常路径不会返回。
        :raises ServiceToolTraceAnalysisPublishError: 始终抛出。
        """

        raise ServiceToolTraceAnalysisPublishError(
            published_paths=(),
            failed_path=json_path,
            primary_publish_error=ServiceToolTracePublishFailure(
                target_path=json_path,
                error_summary="OSError: replace-failed",
            ),
            cleanup_error=ServiceToolTraceCleanupFailure(
                failed_paths=(temporary_path,),
                error_summary="OSError: cleanup-failed",
            ),
            temporary_paths_cleaned=False,
        )

    monkeypatch.setattr(
        tool_trace_command,
        "analyze_and_publish_tool_trace",
        raise_publish_failure,
    )
    args = cli_main.parse_cli_args(
        (
            "tool_trace",
            "analyze",
            str(cold_file),
            "--output-dir",
            str(tmp_path / "reports"),
        )
    )

    exit_code = tool_trace_command.run_tool_trace_command(args)

    captured = capsys.readouterr()
    assert exit_code == EXIT_FAILURE
    assert "已发布路径：无" in captured.err
    assert f"发布失败路径：{json_path}" in captured.err
    assert f"临时文件清理失败路径：{temporary_path}" in captured.err
    assert "清理错误：OSError: cleanup-failed" in captured.err


def test_cli_defensively_rejects_unknown_action(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """command runner 对非 parser 来源的未知 action 仍返回 usage error。

    :param tmp_path: pytest 临时目录。
    :param capsys: pytest 标准流捕获。
    :returns: ``None``。
    :raises AssertionError: 防御分支退出码错误时抛出。
    """

    cold_file = _write_cold_file(tmp_path / "trace.jsonl")
    args = cli_main.parse_cli_args(
        (
            "tool_trace",
            "analyze",
            str(cold_file),
            "--output-dir",
            str(tmp_path / "reports"),
        )
    )
    args.tool_trace_action = "unknown"

    exit_code = tool_trace_command.run_tool_trace_command(args)

    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE_ERROR
    assert "不支持的 action" in captured.err


def test_module_entrypoint_publishes_reports_in_subprocess(
    tmp_path: Path,
) -> None:
    """隔离 subprocess 验证 ``python -m dayu.cli`` public entry。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: subprocess 或报告发布失败时抛出。
    """

    cold_file = _write_cold_file(tmp_path / "trace.jsonl")
    output_dir = tmp_path / "reports"

    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            "dayu.cli",
            "tool_trace",
            "analyze",
            str(cold_file),
            "--output-dir",
            str(output_dir),
        ),
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )

    assert completed.returncode == EXIT_SUCCESS
    assert completed.stderr == ""
    assert (output_dir / "tool-trace-analysis.json").stat().st_size > 0
    assert (output_dir / "tool-trace-analysis.md").stat().st_size > 0


def test_main_registers_tool_trace_runner() -> None:
    """CLI main 必须把 tool_trace 映射到真实 command runner。

    :returns: ``None``。
    :raises AssertionError: runner 未注册或映射漂移时抛出。
    """

    assert (
        cli_main.COMMAND_RUNNERS[COMMAND_TOOL_TRACE]
        is tool_trace_command.run_tool_trace_command
    )
