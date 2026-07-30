"""Dayu CLI 参数解析与退出码骨架测试。"""

from __future__ import annotations

import argparse
import io
import logging
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import pytest

from dayu.cli.__main__ import run_module
import dayu.cli.main as cli_main
import dayu.runtime.log as runtime_log
from dayu.cli.arg_parsing import (
    CLI_COMMAND_NAMES,
    EXCLUDED_COMMAND_NAMES,
    ParsedCliArgs,
    build_parser,
    parse_cli_args,
)
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_NOT_IMPLEMENTED,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)

COMMAND_HELP_EXPECTATIONS: dict[str, tuple[str, ...]] = {
    "init": ("--base", "--workspace", "--reset", "--overwrite"),
    "prompt": (
        "prompt",
        "--ticker",
        "--label",
        "--detail",
        "--no-detail",
        "--model",
        "--temperature",
        "--tool-timeout-seconds",
        "--max-iterations",
    ),
    "interactive": (
        "--ticker",
        "--label",
        "--detail",
        "--no-detail",
        "--model",
        "--temperature",
    ),
    "download": ("--ticker", "--forms", "--start", "--end", "--overwrite"),
    "upload_filing": (
        "--ticker",
        "--action",
        "--files",
        "--fiscal-year",
        "--filing-date",
        "--company-name",
        "--overwrite",
    ),
    "upload_material": (
        "--ticker",
        "--action",
        "--forms",
        "--material-name",
        "--files",
        "--document-id",
        "--internal-document-id",
    ),
    "upload_filings_from": (
        "--ticker",
        "--from",
        "--action",
        "--output",
        "--recursive",
        "--material-forms",
        "--infer",
        "--overwrite",
    ),
    "process": ("--ticker", "--document-id", "--overwrite"),
    "process_filing": ("--ticker", "--document-id", "--overwrite"),
    "process_material": ("--ticker", "--document-id", "--overwrite"),
    "session": ("list", "resume", "purge"),
    "tool_trace": ("analyze",),
}
_TEST_LOGGER_NAME: str = "dayu.cli.test_arg_parsing"
_FIRST_LOG_FILE_DIAGNOSTIC: str = "first run diagnostic"
_SECOND_STDERR_DIAGNOSTIC: str = "second run diagnostic"
_RESTORE_FAILURE_MESSAGE: str = "restore stderr failed"
_ROOT_README_PATH: Path = Path(__file__).resolve().parents[2] / "README.md"


@dataclass(frozen=True, slots=True)
class _LogAssemblyCall:
    """CLI main 日志装配调用记录。"""

    log_level: str | None
    debug: bool
    debug_stream: bool
    verbose: bool
    info: bool
    quiet: bool
    stream: TextIO | None


class _TrackingLogStream(io.StringIO):
    """记录 close 顺序的测试日志流。"""

    events: list[str]

    def __init__(self, events: list[str]) -> None:
        """初始化测试日志流。

        :param events: 共享事件列表。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__()
        self.events = events

    def close(self) -> None:
        """记录关闭事件后关闭底层流。

        :returns: ``None``。
        :raises Exception: 底层 ``StringIO.close`` 失败时透传。
        """

        self.events.append("close")
        super().close()


def _capture_help(
    capsys: pytest.CaptureFixture[str], argv: Sequence[str]
) -> str:
    """捕获指定 CLI 参数的 help 输出。

    :param capsys: pytest 标准输出捕获夹具。
    :param argv: 不含程序名的 CLI 参数。
    :returns: argparse 写入 stdout 的 help 文本。
    :raises AssertionError: help 没有以成功退出码结束时抛出。
    """

    parser = build_parser()
    with pytest.raises(SystemExit) as raised:
        parser.parse_args([*argv, "--help"])
    assert raised.value.code == EXIT_SUCCESS
    return capsys.readouterr().out


def _raise_keyboard_interrupt(_args: ParsedCliArgs) -> int:
    """测试用命令 runner，模拟用户中断。

    :param _args: 已解析的 CLI 参数。
    :returns: 正常路径不会返回。
    :raises KeyboardInterrupt: 始终抛出以验证 main 的退出码映射。
    """

    raise KeyboardInterrupt


def _return_success(_args: ParsedCliArgs) -> int:
    """测试用命令 runner，直接返回成功。

    :param _args: 已解析的 CLI 参数。
    :returns: 成功退出码。
    :raises Exception: 不主动抛出异常。
    """

    return EXIT_SUCCESS


def _log_prompt_and_return_success(args: ParsedCliArgs) -> int:
    """测试用命令 runner，把 prompt 文本写入 Dayu 诊断日志后返回成功。

    :param args: 已解析的 CLI 参数。
    :returns: 成功退出码。
    :raises Exception: stdlib logging handler 写入失败时透传。
    """

    logging.getLogger(_TEST_LOGGER_NAME).info(args.prompt)
    return EXIT_SUCCESS


def _raise_runtime_error(_args: ParsedCliArgs) -> int:
    """测试用命令 runner，模拟未预期异常。

    :param _args: 已解析的 CLI 参数。
    :returns: 正常路径不会返回。
    :raises RuntimeError: 始终抛出以验证 main 的 finally 清理。
    """

    raise RuntimeError("runner boom")


def test_top_level_help_registers_scoped_commands(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证顶层 help 只展示当前 S1 允许注册的 scoped commands。

    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: help 文本与命令注册范围不一致时抛出。
    """

    help_text = _capture_help(capsys, ())

    for command_name in CLI_COMMAND_NAMES:
        assert command_name in help_text
    for command_name in EXCLUDED_COMMAND_NAMES:
        assert command_name not in help_text


def test_global_help_contains_debug_stream(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证顶层 help 暴露全局 ``--debug-stream`` 日志开关。"""

    help_text = _capture_help(capsys, ())

    assert "--debug-stream" in help_text
    assert "stream delta" in help_text
    assert "SSE" in help_text


@pytest.mark.parametrize(
    "command_name",
    tuple(COMMAND_HELP_EXPECTATIONS.keys()),
)
def test_command_help_contains_core_arguments(
    capsys: pytest.CaptureFixture[str], command_name: str
) -> None:
    """验证每个 scoped command 的 help 暴露计划要求的核心参数。

    :param capsys: pytest 标准输出捕获夹具。
    :param command_name: 待检查的命令名。
    :returns: ``None``。
    :raises AssertionError: help 缺少核心参数时抛出。
    """

    help_text = _capture_help(capsys, (command_name,))

    for expected_fragment in COMMAND_HELP_EXPECTATIONS[command_name]:
        assert expected_fragment in help_text


@pytest.mark.parametrize(
    "command_path",
    (
        ("prompt",),
        ("interactive",),
        ("session", "resume"),
    ),
)
def test_agent_command_help_uses_model_long_and_short_forms(
    capsys: pytest.CaptureFixture[str],
    command_path: tuple[str, ...],
) -> None:
    """三个 Agent surface 的 help 只展示正式 ``--model/-m``。

    :param capsys: pytest 标准输出捕获夹具。
    :param command_path: 待检查的命令及二级 action。
    :returns: ``None``。
    :raises AssertionError: help 仍展示旧参数或缺少正式参数时抛出。
    """

    help_text = _capture_help(capsys, command_path)

    assert "--model MODEL" in help_text
    assert "-m MODEL" in help_text
    assert "--model-name" not in help_text


def test_command_help_contains_debug_stream(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证命令 help 继承全局 ``--debug-stream`` 日志开关。"""

    help_text = _capture_help(capsys, ("prompt",))

    assert "--debug-stream" in help_text
    assert "stream delta" in help_text
    assert "SSE" in help_text


def test_interactive_help_contains_optional_ticker(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证 ``interactive --help`` 包含 optional ``--ticker``。

    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: help 缺少 ``--ticker`` 时抛出。
    """

    help_text = _capture_help(capsys, ("interactive",))

    assert "--ticker" in help_text


def test_tool_trace_analyze_help_and_required_arguments(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证 Analyzer action help 及 INPUT/output-dir 必填 contract。

    :param capsys: pytest 标准输出捕获。
    :returns: ``None``。
    :raises AssertionError: help 或 required 参数 contract 漂移时抛出。
    """

    help_text = _capture_help(capsys, ("tool_trace", "analyze"))

    assert "INPUT" in help_text
    assert "--output-dir" in help_text
    with pytest.raises(SystemExit) as missing_input:
        parse_cli_args(("tool_trace", "analyze", "--output-dir", "reports"))
    assert missing_input.value.code == EXIT_USAGE_ERROR
    with pytest.raises(SystemExit) as missing_output:
        parse_cli_args(("tool_trace", "analyze", "workspace"))
    assert missing_output.value.code == EXIT_USAGE_ERROR


def test_tool_trace_parser_rejects_unknown_action() -> None:
    """验证未知 Tool Trace action 由 argparse 返回用法错误。

    :returns: ``None``。
    :raises AssertionError: unknown action 没有被拒绝时抛出。
    """

    with pytest.raises(SystemExit) as raised:
        parse_cli_args(("tool_trace", "inspect"))

    assert raised.value.code == EXIT_USAGE_ERROR


def test_tool_trace_parser_returns_explicit_analyze_fields() -> None:
    """验证 Analyzer parser 不从全局 workspace 参数猜输入。

    :returns: ``None``。
    :raises AssertionError: 解析字段或显式路径 contract 漂移时抛出。
    """

    args = parse_cli_args(
        (
            "tool_trace",
            "analyze",
            "trace.jsonl",
            "--output-dir",
            "reports",
            "--base",
            "ignored-workspace",
        )
    )

    assert args.tool_trace_action == "analyze"
    assert args.tool_trace_input == "trace.jsonl"
    assert args.output_dir == "reports"
    assert args.workspace_root == "ignored-workspace"


def test_upload_actions_default_to_auto_and_batch_rejects_delete() -> None:
    """三个 upload parser 默认 auto，direct 可 delete，batch 必须拒绝 delete。"""

    filing = parse_cli_args(("upload_filing", "--ticker", "AAPL"))
    material = parse_cli_args(("upload_material", "--ticker", "AAPL"))
    batch = parse_cli_args(
        ("upload_filings_from", "--ticker", "AAPL", "--from", "source")
    )
    direct_delete = parse_cli_args(
        ("upload_filing", "--ticker", "AAPL", "--action", "delete")
    )

    assert filing.action == "auto"
    assert material.action == "auto"
    assert batch.action == "auto"
    assert batch.infer is False
    assert batch.overwrite is False
    assert direct_delete.action == "delete"
    with pytest.raises(SystemExit) as raised:
        parse_cli_args(
            (
                "upload_filings_from",
                "--ticker",
                "AAPL",
                "--from",
                "source",
                "--action",
                "delete",
            )
        )
    assert raised.value.code == EXIT_USAGE_ERROR


def test_upload_filings_from_infer_and_overwrite_are_explicit_booleans() -> None:
    """batch ``--infer``/``--overwrite`` 必须仅在显式传入时为 true。"""

    explicit = parse_cli_args(
        (
            "upload_filings_from",
            "--ticker",
            "AAPL",
            "--from",
            "source",
            "--infer",
            "--overwrite",
        )
    )

    assert explicit.infer is True
    assert explicit.overwrite is True


def test_interactive_help_omits_removed_new_session_flag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证 ``interactive --help`` 不再暴露过时 ``--new-session``。

    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: help 仍包含过时 flag 时抛出。
    """

    help_text = _capture_help(capsys, ("interactive",))

    assert "--new-session" not in help_text


def test_interactive_new_session_flag_exits_with_usage_error() -> None:
    """验证 ``interactive --new-session`` 已从 parser surface 删除。

    :returns: ``None``。
    :raises AssertionError: parser 未按 unknown argument 返回用法错误时抛出。
    """

    with pytest.raises(SystemExit) as raised:
        parse_cli_args(("interactive", "--new-session"))

    assert raised.value.code == EXIT_USAGE_ERROR


def test_root_readme_matches_current_cli_public_contract() -> None:
    """根用户手册必须投影当前 CLI init 与其它公开行为。

    :returns: ``None``。
    :raises AssertionError: README 与当前 CLI command/输出契约漂移时抛出。
    """

    readme = _ROOT_README_PATH.read_text(encoding="utf-8")
    direct_upload_section = readme.split(
        "### 5.2 上传单份 filing 或材料", maxsplit=1
    )[1].split("### 5.3 从目录生成批量上传脚本", maxsplit=1)[0]
    batch_upload_section = readme.split(
        "### 5.3 从目录生成批量上传脚本", maxsplit=1
    )[1].split("### 5.4 预处理", maxsplit=1)[0]
    init_section = readme.split("## 2. 初始化工作区", maxsplit=1)[1].split(
        "## 3. CLI 公共命令", maxsplit=1
    )[0]
    for removed_contract in (
        "`write`",
        "--ci",
        "--web-provider",
        "--new-session",
        "--doc-limits-json",
        "--fins-limits-json",
    ):
        assert removed_contract not in readme
    assert "`init` 是非交互式文件初始化命令" not in readme
    for init_mode in ("FIRST：", "PRESERVE：", "OVERWRITE：", "RESET："):
        assert init_mode in init_section
    assert "RESET 优先于 `--overwrite`" in init_section
    assert "POSIX 写入当前 shell" in init_section
    assert "Windows 使用当前用户的 `setx`" in init_section
    assert "secret 值不写入 workspace" in init_section
    assert "`.dayu-init.lock` 只用于串行多个 `init`" in init_section
    assert "执行 RESET 前必须先停止" in init_section
    assert "FIRST/RESET 发布成功后" in init_section
    assert "`prompt` 与 `interactive`" in init_section
    assert "不联网" in init_section
    assert "prewarm warning" in init_section
    assert "进程结束时自动清理" in readme
    assert "dayu-cli upload_filings_from" in batch_upload_section
    assert "--infer" in batch_upload_section
    assert "`FMP_API_KEY`" in batch_upload_section
    assert "--infer" not in direct_upload_section
    assert "`upload_filings_<TICKER>.sh`" in batch_upload_section
    assert "`upload_filings_<TICKER>.cmd`" in batch_upload_section
    assert "/bin/sh" in batch_upload_section
    assert "cmd.exe /d /c" in batch_upload_section
    for removed_batch_contract in (
        '"schema_version": 1',
        '"commands"',
        "不生成 shell",
    ):
        assert removed_batch_contract not in readme
    assert "interactive --ticker" in readme


def test_session_action_help_contains_fixed_parser_shape(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证 ``session`` 二级命令 help 冻结 list/resume/purge surface。

    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: help 缺少 S4 固定 parser surface 时抛出。
    """

    purge_help = _capture_help(capsys, ("session", "purge"))
    resume_help = _capture_help(capsys, ("session", "resume"))

    assert "--session-id" in purge_help
    assert "--label" in purge_help
    assert "--kind" in purge_help
    assert "--yes" in purge_help
    assert "--session-id" in resume_help
    assert "--label" in resume_help
    assert "--kind" in resume_help
    assert "--mode" in resume_help


def test_missing_command_exits_with_usage_error() -> None:
    """验证缺少子命令时按 argparse 用法错误返回 2。

    :returns: ``None``。
    :raises AssertionError: 退出码不是用法错误时抛出。
    """

    assert cli_main.main(()) == EXIT_USAGE_ERROR


@pytest.mark.parametrize("command_name", EXCLUDED_COMMAND_NAMES)
def test_excluded_commands_exit_with_usage_error(command_name: str) -> None:
    """验证未纳入 S1 的旧命令走 unknown command 用法错误。

    :param command_name: 计划明确排除的旧命令名。
    :returns: ``None``。
    :raises AssertionError: 排除命令没有返回用法错误时抛出。
    """

    assert cli_main.main((command_name,)) == EXIT_USAGE_ERROR


def test_placeholder_runner_returns_not_implemented(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """验证已注册命令被分发时返回清晰的 not-implemented 结果。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 退出码或错误文本不符合占位契约时抛出。
    """

    args = ParsedCliArgs()
    args.command_name = "future_command"
    args.log_level = "info"
    args.debug_stream = False
    args.log_file = None
    monkeypatch.setattr(cli_main, "parse_cli_args", lambda _argv: args)
    monkeypatch.setitem(
        cli_main.COMMAND_RUNNERS,
        "future_command",
        cli_main.run_not_implemented_command,
    )

    exit_code = cli_main.main(("future_command",))
    captured = capsys.readouterr()

    assert exit_code == EXIT_NOT_IMPLEMENTED
    assert "尚未实现" in captured.err
    assert "future_command" in captured.err


def test_main_reports_missing_command_runner(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """验证已解析命令缺少 runner 时输出内部诊断。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 退出码或错误文本不符合 dispatch 失败契约时抛出。
    """

    monkeypatch.delitem(cli_main.COMMAND_RUNNERS, "prompt")

    exit_code = cli_main.main(("prompt", "请分析收入变化"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_FAILURE
    assert "内部错误" in captured.err
    assert "缺少注册 runner" in captured.err
    assert "prompt" in captured.err


def test_cli_standard_stream_owner_reconfigures_real_wrapper_to_strict_utf8() -> None:
    """CLI 标准流 owner 必须让 redirected wrapper 可严格输出中文 UTF-8。

    :returns: ``None``。
    :raises AssertionError: wrapper 仍使用 legacy charmap 或替换错误时抛出。
    """

    raw_stream = io.BytesIO()
    text_stream = io.TextIOWrapper(
        raw_stream,
        encoding="cp1252",
        errors="strict",
    )
    try:
        cli_main._configure_cli_standard_stream(text_stream)
        text_stream.write("初始化完成：中文输出")
        text_stream.flush()

        assert text_stream.encoding == "utf-8"
        assert text_stream.errors == "strict"
        assert raw_stream.getvalue().decode("utf-8") == "初始化完成：中文输出"
    finally:
        text_stream.detach()


def test_cli_standard_stream_owner_preserves_non_wrapper_capture() -> None:
    """CLI 标准流 owner 不得把测试或调用方提供的内存 capture 伪装成 OS 流。

    :returns: ``None``。
    :raises AssertionError: 非 wrapper 流被替换或无法继续写入时抛出。
    """

    capture = io.StringIO()

    cli_main._configure_cli_standard_stream(capture)
    capture.write("中文")

    assert capture.getvalue() == "中文"


def test_main_maps_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证命令执行阶段的 ``KeyboardInterrupt`` 映射为 130。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 中断退出码不符合契约时抛出。
    """

    monkeypatch.setitem(cli_main.COMMAND_RUNNERS, "prompt", _raise_keyboard_interrupt)

    assert cli_main.main(("prompt", "请分析收入变化")) == EXIT_KEYBOARD_INTERRUPT


@pytest.mark.parametrize(
    ("argv", "expected_log_level", "expected_debug_stream"),
    (
        (("prompt", "hello"), "info", False),
        (("prompt", "hello", "--debug"), "debug", False),
        (("prompt", "hello", "--verbose"), "verbose", False),
        (("prompt", "hello", "--quiet"), "error", False),
        (("prompt", "hello", "--log-level", "warn"), "warn", False),
        (("prompt", "hello", "--log-level", "critical"), "critical", False),
        (("prompt", "hello", "--debug-stream"), "info", True),
    ),
)
def test_main_configures_runtime_log_from_parsed_cli_flags(
    argv: tuple[str, ...],
    expected_log_level: str,
    expected_debug_stream: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI main 必须把默认日志参数交给 runtime log helper 与临时文件。

    :param argv: 待执行的 CLI 参数。
    :param expected_log_level: argparse 归一后的日志级别字符串。
    :param expected_debug_stream: 预期传入 runtime helper 的 stream debug flag。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: main 未调用 runtime helper 或在 main 内改写参数时抛出。
    """

    calls: list[_LogAssemblyCall] = []
    events: list[str] = []
    log_stream = _TrackingLogStream(events)

    def spy_set_level_from_flags(
        *,
        log_level: str | None,
        debug: bool,
        debug_stream: bool,
        verbose: bool,
        info: bool,
        quiet: bool,
        stream: TextIO | None = None,
    ) -> runtime_log.LogLevel:
        """记录 main 传入 runtime log helper 的参数。

        :param log_level: argparse 已解析的日志级别字符串。
        :param debug: runtime helper 的 debug flag。
        :param debug_stream: runtime helper 的 stream debug flag。
        :param verbose: runtime helper 的 verbose flag。
        :param info: runtime helper 的 info flag。
        :param quiet: runtime helper 的 quiet flag。
        :param stream: runtime helper 的诊断日志输出流。
        :returns: 测试用日志级别。
        :raises Exception: 不主动抛出异常。
        """

        calls.append(
            _LogAssemblyCall(
                log_level=log_level,
                debug=debug,
                debug_stream=debug_stream,
                verbose=verbose,
                info=info,
                quiet=quiet,
                stream=stream,
            )
        )
        return runtime_log.LogLevel.INFO

    monkeypatch.setattr(
        cli_main.runtime_log,
        "set_level_from_flags",
        spy_set_level_from_flags,
    )
    monkeypatch.setattr(cli_main, "_open_default_log_file", lambda: log_stream)
    monkeypatch.setitem(cli_main.COMMAND_RUNNERS, "prompt", _return_success)

    assert cli_main.main(argv) == EXIT_SUCCESS
    assert len(calls) == 2
    assert calls[0] == _LogAssemblyCall(
        log_level=expected_log_level,
        debug=False,
        debug_stream=expected_debug_stream,
        verbose=False,
        info=False,
        quiet=False,
        stream=log_stream,
    )
    assert calls[1] == _LogAssemblyCall(
        log_level=expected_log_level,
        debug=False,
        debug_stream=expected_debug_stream,
        verbose=False,
        info=False,
        quiet=False,
        stream=sys.stderr,
    )
    assert events == ["close"]
    assert log_stream.closed


def test_main_configures_runtime_log_file_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--log-file`` 必须只替换 runtime log helper 的诊断 stream。

    :param tmp_path: pytest 临时目录夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: main 未把日志文件流传给 runtime helper 时抛出。
    """

    calls: list[_LogAssemblyCall] = []

    def spy_set_level_from_flags(
        *,
        log_level: str | None,
        debug: bool,
        debug_stream: bool,
        verbose: bool,
        info: bool,
        quiet: bool,
        stream: TextIO | None = None,
    ) -> runtime_log.LogLevel:
        """记录 runtime log helper 调用。

        :param log_level: argparse 已解析的日志级别字符串。
        :param debug: runtime helper 的 debug flag。
        :param debug_stream: runtime helper 的 stream debug flag。
        :param verbose: runtime helper 的 verbose flag。
        :param info: runtime helper 的 info flag。
        :param quiet: runtime helper 的 quiet flag。
        :param stream: runtime helper 的诊断日志输出流。
        :returns: 测试用日志级别。
        :raises Exception: 不主动抛出异常。
        """

        calls.append(
            _LogAssemblyCall(
                log_level=log_level,
                debug=debug,
                debug_stream=debug_stream,
                verbose=verbose,
                info=info,
                quiet=quiet,
                stream=stream,
            )
        )
        return runtime_log.LogLevel.INFO

    monkeypatch.setattr(
        cli_main.runtime_log,
        "set_level_from_flags",
        spy_set_level_from_flags,
    )
    monkeypatch.setitem(cli_main.COMMAND_RUNNERS, "prompt", _return_success)

    log_file = tmp_path / "dayu.log"

    assert (
        cli_main.main(("prompt", "请分析收入变化", "--log-file", str(log_file)))
        == EXIT_SUCCESS
    )
    assert len(calls) == 2
    assert calls[0].log_level == "info"
    assert calls[0].stream is not sys.stderr
    assert calls[0].stream is not None
    assert calls[0].stream.closed
    assert calls[1] == _LogAssemblyCall(
        log_level="info",
        debug=False,
        debug_stream=False,
        verbose=False,
        info=False,
        quiet=False,
        stream=sys.stderr,
    )


def test_open_default_log_file_uses_auto_deleted_temporary_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认日志必须使用随进程关闭的临时流，不遗留不可发现文件。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 未使用 auto-delete 临时流或流不可写时抛出。
    """

    calls: list[tuple[str, str, str, str]] = []

    def temporary_file(
        *,
        mode: str,
        encoding: str,
        prefix: str,
        suffix: str,
    ) -> TextIO:
        """记录默认临时流工厂调用。

        :param mode: 文件打开模式。
        :param encoding: 文本编码。
        :param prefix: 临时文件名前缀。
        :param suffix: 临时文件名后缀。
        :returns: 测试用内存文本流。
        :raises Exception: 不主动抛出异常。
        """

        calls.append((mode, encoding, prefix, suffix))
        return io.StringIO()

    monkeypatch.setattr(cli_main.tempfile, "TemporaryFile", temporary_file)
    stream = cli_main._open_default_log_file()
    assert stream is not None
    stream.write("default diagnostic\n")
    stream.seek(0)
    assert stream.read() == "default diagnostic\n"
    stream.close()
    assert calls == [("w+", "utf-8", "dayu-cli-", ".log")]


def test_main_uses_separate_log_files_for_explicit_and_default_calls(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """连续调用时显式日志文件不得污染后续默认临时日志文件。

    :param tmp_path: pytest 临时目录夹具。
    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 第二次调用写入 stderr 或继续写显式日志文件时抛出。
    """

    monkeypatch.setitem(
        cli_main.COMMAND_RUNNERS,
        "prompt",
        _log_prompt_and_return_success,
    )
    log_file = tmp_path / "dayu.log"
    default_log_file = tmp_path / "dayu-default.log"

    def open_default_log_file() -> TextIO:
        """打开测试用默认日志文件。

        :returns: 已打开的默认日志文件流。
        :raises OSError: 文件打开失败时由 ``open`` 透传。
        """

        return open(default_log_file, mode="a", encoding="utf-8")

    monkeypatch.setattr(cli_main, "_open_default_log_file", open_default_log_file)

    assert (
        cli_main.main(
            (
                "prompt",
                _FIRST_LOG_FILE_DIAGNOSTIC,
                "--log-file",
                str(log_file),
            )
        )
        == EXIT_SUCCESS
    )
    assert (
        cli_main.main(("prompt", _SECOND_STDERR_DIAGNOSTIC))
        == EXIT_SUCCESS
    )

    captured = capsys.readouterr()
    log_content = log_file.read_text(encoding="utf-8")
    default_log_content = default_log_file.read_text(encoding="utf-8")
    assert _FIRST_LOG_FILE_DIAGNOSTIC in log_content
    assert _SECOND_STDERR_DIAGNOSTIC not in log_content
    assert _FIRST_LOG_FILE_DIAGNOSTIC not in default_log_content
    assert _SECOND_STDERR_DIAGNOSTIC in default_log_content
    assert _FIRST_LOG_FILE_DIAGNOSTIC not in captured.err
    assert _SECOND_STDERR_DIAGNOSTIC not in captured.err


def test_main_restores_stderr_before_closing_log_file_on_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """runner 抛出未预期异常时也必须先恢复 stderr handler 再关闭文件。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 清理顺序不符合日志 handler 生命周期要求时抛出。
    """

    events: list[str] = []
    log_stream = _TrackingLogStream(events)

    def fake_open_log_file(_log_file: str) -> TextIO | None:
        """返回可追踪 close 顺序的测试日志流。

        :param _log_file: 用户传入的日志路径。
        :returns: 测试日志流。
        :raises Exception: 不主动抛出异常。
        """

        return log_stream

    def spy_set_level_from_flags(
        *,
        log_level: str | None,
        debug: bool,
        debug_stream: bool,
        verbose: bool,
        info: bool,
        quiet: bool,
        stream: TextIO | None = None,
    ) -> runtime_log.LogLevel:
        """记录恢复 stderr 与关闭文件的相对顺序。

        :param log_level: argparse 已解析的日志级别字符串。
        :param debug: runtime helper 的 debug flag。
        :param debug_stream: runtime helper 的 stream debug flag。
        :param verbose: runtime helper 的 verbose flag。
        :param info: runtime helper 的 info flag。
        :param quiet: runtime helper 的 quiet flag。
        :param stream: runtime helper 的诊断日志输出流。
        :returns: 测试用日志级别。
        :raises Exception: 不主动抛出异常。
        """

        if stream is sys.stderr:
            events.append("restore-stderr")
        elif stream is log_stream:
            events.append("configure-file")
        return runtime_log.LogLevel.INFO

    monkeypatch.setattr(cli_main, "_open_log_file", fake_open_log_file)
    monkeypatch.setattr(
        cli_main.runtime_log,
        "set_level_from_flags",
        spy_set_level_from_flags,
    )
    monkeypatch.setitem(cli_main.COMMAND_RUNNERS, "prompt", _raise_runtime_error)

    with pytest.raises(RuntimeError, match="runner boom"):
        cli_main.main(("prompt", "请分析收入变化", "--log-file", "dayu.log"))

    assert events == ["configure-file", "restore-stderr", "close"]
    assert log_stream.closed


def test_main_closes_log_file_when_restoring_stderr_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """恢复 stderr handler 抛异常时仍必须关闭已打开日志文件。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 日志文件未关闭或事件顺序不符合预期时抛出。
    """

    events: list[str] = []
    log_stream = _TrackingLogStream(events)

    def fake_open_log_file(_log_file: str) -> TextIO | None:
        """返回可追踪 close 顺序的测试日志流。

        :param _log_file: 用户传入的日志路径。
        :returns: 测试日志流。
        :raises Exception: 不主动抛出异常。
        """

        return log_stream

    def spy_set_level_from_flags(
        *,
        log_level: str | None,
        debug: bool,
        debug_stream: bool,
        verbose: bool,
        info: bool,
        quiet: bool,
        stream: TextIO | None = None,
    ) -> runtime_log.LogLevel:
        """模拟恢复 stderr handler 失败并记录文件关闭顺序。

        :param log_level: argparse 已解析的日志级别字符串。
        :param debug: runtime helper 的 debug flag。
        :param debug_stream: runtime helper 的 stream debug flag。
        :param verbose: runtime helper 的 verbose flag。
        :param info: runtime helper 的 info flag。
        :param quiet: runtime helper 的 quiet flag。
        :param stream: runtime helper 的诊断日志输出流。
        :returns: 测试用日志级别。
        :raises ValueError: 恢复 stderr handler 时按测试设定抛出。
        """

        if stream is sys.stderr:
            events.append("restore-stderr")
            raise ValueError(_RESTORE_FAILURE_MESSAGE)
        if stream is log_stream:
            events.append("configure-file")
        return runtime_log.LogLevel.INFO

    monkeypatch.setattr(cli_main, "_open_log_file", fake_open_log_file)
    monkeypatch.setattr(
        cli_main.runtime_log,
        "set_level_from_flags",
        spy_set_level_from_flags,
    )
    monkeypatch.setitem(cli_main.COMMAND_RUNNERS, "prompt", _return_success)

    with pytest.raises(ValueError, match=_RESTORE_FAILURE_MESSAGE):
        cli_main.main(("prompt", "请分析收入变化", "--log-file", "dayu.log"))

    assert events == ["configure-file", "restore-stderr", "close"]
    assert log_stream.closed


def test_main_restores_stderr_before_closing_log_file_on_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--log-file`` 下 ``KeyboardInterrupt`` 也必须先恢复 stderr 再关闭文件。

    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 中断退出码或清理顺序不符合预期时抛出。
    """

    events: list[str] = []
    log_stream = _TrackingLogStream(events)

    def fake_open_log_file(_log_file: str) -> TextIO | None:
        """返回可追踪 close 顺序的测试日志流。

        :param _log_file: 用户传入的日志路径。
        :returns: 测试日志流。
        :raises Exception: 不主动抛出异常。
        """

        return log_stream

    def spy_set_level_from_flags(
        *,
        log_level: str | None,
        debug: bool,
        debug_stream: bool,
        verbose: bool,
        info: bool,
        quiet: bool,
        stream: TextIO | None = None,
    ) -> runtime_log.LogLevel:
        """记录 ``KeyboardInterrupt`` 路径的恢复 stderr 与关闭文件顺序。

        :param log_level: argparse 已解析的日志级别字符串。
        :param debug: runtime helper 的 debug flag。
        :param debug_stream: runtime helper 的 stream debug flag。
        :param verbose: runtime helper 的 verbose flag。
        :param info: runtime helper 的 info flag。
        :param quiet: runtime helper 的 quiet flag。
        :param stream: runtime helper 的诊断日志输出流。
        :returns: 测试用日志级别。
        :raises Exception: 不主动抛出异常。
        """

        if stream is sys.stderr:
            events.append("restore-stderr")
        elif stream is log_stream:
            events.append("configure-file")
        return runtime_log.LogLevel.INFO

    monkeypatch.setattr(cli_main, "_open_log_file", fake_open_log_file)
    monkeypatch.setattr(
        cli_main.runtime_log,
        "set_level_from_flags",
        spy_set_level_from_flags,
    )
    monkeypatch.setitem(
        cli_main.COMMAND_RUNNERS,
        "prompt",
        _raise_keyboard_interrupt,
    )

    assert (
        cli_main.main(("prompt", "请分析收入变化", "--log-file", "dayu.log"))
        == EXIT_KEYBOARD_INTERRUPT
    )

    assert events == ["configure-file", "restore-stderr", "close"]
    assert log_stream.closed


def test_main_returns_usage_error_when_log_file_cannot_open(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--log-file`` 打开失败必须返回 usage error 且不执行命令 runner。

    :param tmp_path: pytest 临时目录夹具。
    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 打开失败没有被收敛为 usage error 时抛出。
    """

    monkeypatch.setitem(cli_main.COMMAND_RUNNERS, "prompt", _return_success)
    missing_parent = tmp_path / "missing" / "dayu.log"

    assert (
        cli_main.main(("prompt", "请分析收入变化", "--log-file", str(missing_parent)))
        == EXIT_USAGE_ERROR
    )
    captured = capsys.readouterr()
    assert "--log-file" in captured.err
    assert "cannot open" in captured.err


def test_main_returns_usage_error_when_log_file_is_empty(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """空白 ``--log-file`` 路径必须返回 usage error。

    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 空白路径没有被拒绝时抛出。
    """

    assert (
        cli_main.main(("prompt", "请分析收入变化", "--log-file", "   "))
        == EXIT_USAGE_ERROR
    )
    captured = capsys.readouterr()
    assert "--log-file" in captured.err
    assert "must not be empty" in captured.err


def test_python_module_help_decodes_cli_output_as_strict_utf8() -> None:
    """验证模块入口使用同一 parser，并按严格 UTF-8 消费中文输出。

    :returns: ``None``。
    :raises AssertionError: 模块入口退出码、解码或 help 输出不符合契约时抛出。
    """

    result = subprocess.run(
        [sys.executable, "-m", "dayu.cli", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        check=False,
    )

    assert result.returncode == EXIT_SUCCESS
    assert "Dayu 财报分析命令行入口。" in result.stdout
    assert "dayu-cli" in result.stdout
    assert "interactive" in result.stdout


def test_module_run_function_uses_cli_main(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """验证模块入口函数可在同进程内复用 CLI main。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 入口函数未复用 CLI main 契约时抛出。
    """

    monkeypatch.setattr(sys, "argv", ["dayu-cli", "--help"])

    assert run_module() == EXIT_SUCCESS
    assert "dayu-cli" in capsys.readouterr().out


def test_parse_args_accepts_global_options_before_and_after_command() -> None:
    """验证全局参数可出现在命令前或命令后。

    :returns: ``None``。
    :raises AssertionError: 显式全局参数被默认值覆盖时抛出。
    """

    parser = build_parser()
    before_command = parser.parse_args(
        ("--base", "workspace-a", "--log-file", "before.log", "prompt", "hello"),
        namespace=argparse.Namespace(),
    )
    after_command = parser.parse_args(
        ("prompt", "hello", "--base", "workspace-b", "--log-file", "after.log"),
        namespace=argparse.Namespace(),
    )

    assert before_command.workspace_root == "workspace-a"
    assert before_command.log_file == "before.log"
    assert after_command.workspace_root == "workspace-b"
    assert after_command.log_file == "after.log"


@pytest.mark.parametrize(
    ("argv", "expected_config_dir"),
    (
        (("--config", "config-prompt-before", "prompt", "hello"), "config-prompt-before"),
        (("prompt", "hello", "--config", "config-prompt-after"), "config-prompt-after"),
        (("--config", "config-interactive-before", "interactive"), "config-interactive-before"),
        (("interactive", "--config", "config-interactive-after"), "config-interactive-after"),
        (
            (
                "--config",
                "config-session-before",
                "session",
                "resume",
                "--session-id",
                "session-1",
                "--mode",
                "interactive",
            ),
            "config-session-before",
        ),
        (
            (
                "session",
                "resume",
                "--session-id",
                "session-1",
                "--mode",
                "interactive",
                "--config",
                "config-session-after",
            ),
            "config-session-after",
        ),
    ),
)
def test_runtime_commands_accept_config_before_and_after_command(
    argv: tuple[str, ...],
    expected_config_dir: str,
) -> None:
    """非 init runtime 命令必须在 command 前后都接受 ``--config``。

    :param argv: 待解析的完整 CLI 参数。
    :param expected_config_dir: 预期的显式配置目录。
    :returns: ``None``。
    :raises AssertionError: 参数位置改变 ``config_dir`` 映射时抛出。
    """

    args = parse_cli_args(argv)

    assert args.config_dir == expected_config_dir


@pytest.mark.parametrize(
    "argv",
    (
        ("--config", "forbidden-config", "init"),
        ("init", "--config", "forbidden-config"),
    ),
)
def test_init_rejects_config_before_and_after_command(
    argv: tuple[str, ...],
) -> None:
    """init 必须在 command 前后都由 parser owner 拒绝 ``--config``。

    :param argv: 待解析的 init 参数。
    :returns: ``None``。
    :raises AssertionError: argparse 未返回 usage error 2 时抛出。
    """

    with pytest.raises(SystemExit) as raised:
        parse_cli_args(argv)

    assert raised.value.code == EXIT_USAGE_ERROR


@pytest.mark.parametrize(
    ("argv", "expected_model"),
    (
        (("prompt", "hello", "--model", "model-prompt-long"), "model-prompt-long"),
        (("prompt", "hello", "-m", "model-prompt-short"), "model-prompt-short"),
        (("interactive", "--model", "model-interactive-long"), "model-interactive-long"),
        (("interactive", "-m", "model-interactive-short"), "model-interactive-short"),
        (
            (
                "session",
                "resume",
                "--session-id",
                "session-1",
                "--mode",
                "interactive",
                "--model",
                "model-session-long",
            ),
            "model-session-long",
        ),
        (
            (
                "session",
                "resume",
                "--session-id",
                "session-1",
                "--mode",
                "interactive",
                "-m",
                "model-session-short",
            ),
            "model-session-short",
        ),
    ),
)
def test_agent_commands_map_model_long_and_short_forms(
    argv: tuple[str, ...],
    expected_model: str,
) -> None:
    """三个 Agent surface 的 ``--model/-m`` 必须映射到同一 typed 字段。

    :param argv: 待解析的完整 CLI 参数。
    :param expected_model: 预期模型配置标识。
    :returns: ``None``。
    :raises AssertionError: long/short form 没有映射到 ``ParsedCliArgs.model`` 时抛出。
    """

    args = parse_cli_args(argv)

    assert args.model == expected_model


@pytest.mark.parametrize(
    "argv",
    (
        ("prompt", "hello", "--model-name", "legacy-model"),
        ("interactive", "--model-name", "legacy-model"),
        (
            "session",
            "resume",
            "--session-id",
            "session-1",
            "--mode",
            "interactive",
            "--model-name",
            "legacy-model",
        ),
    ),
)
def test_agent_commands_reject_removed_model_name_option(
    argv: tuple[str, ...],
) -> None:
    """三个 Agent surface 都必须拒绝已删除的 ``--model-name``。

    :param argv: 待解析的完整 CLI 参数。
    :returns: ``None``。
    :raises AssertionError: 旧参数未返回 usage error 2 时抛出。
    """

    with pytest.raises(SystemExit) as raised:
        parse_cli_args(argv)

    assert raised.value.code == EXIT_USAGE_ERROR


def test_default_namespace_initializes_reset_false() -> None:
    """验证默认 CLI namespace 显式提供 ``reset=False``。

    :returns: ``None``。
    :raises AssertionError: ``reset`` 默认值或真实 parser 行为不符合契约时抛出。
    """

    init_args = parse_cli_args(("init",))
    prompt_args = parse_cli_args(("prompt", "hello"))

    assert init_args.reset is False
    assert init_args.overwrite is False
    assert prompt_args.reset is False
    assert prompt_args.detail is True


def test_init_help_describes_reset_precedence_and_overwrite_boundary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Init help 必须描述真实四态中 RESET 与 OVERWRITE 的不同 owner boundary。

    :param capsys: pytest 标准输出捕获夹具。
    :returns: None。
    :raises AssertionError: help 仍承诺旧逐文件覆盖语义时抛出。
    """

    with pytest.raises(SystemExit) as raised:
        build_parser().parse_args(("init", "--help"))

    help_text = capsys.readouterr().out
    assert raised.value.code == 0
    assert "--config" not in help_text
    assert "优先于 --overwrite" in help_text
    assert "重建 .dayu 与 config" in help_text
    assert "保留 .dayu" in help_text


def test_prompt_detail_defaults_to_detail() -> None:
    """验证 prompt 默认显示运行态细节。

    :returns: ``None``。
    :raises AssertionError: ``detail`` 默认值不符合契约时抛出。
    """

    args = parse_cli_args(("prompt", "hello"))

    assert args.detail is True
    assert args.log_level == "info"


def test_interactive_detail_defaults_to_detail() -> None:
    """验证 interactive 默认显示运行态细节。

    :returns: ``None``。
    :raises AssertionError: ``detail`` 默认值不符合契约时抛出。
    """

    args = parse_cli_args(("interactive",))

    assert args.detail is True
    assert args.log_level == "info"


def test_parse_cli_args_accepts_debug_stream() -> None:
    """验证 ``--debug-stream`` 作为全局日志开关独立解析。"""

    args = parse_cli_args(("prompt", "hello", "--debug-stream"))

    assert args.debug_stream is True
    assert args.log_level == "info"


def test_parse_cli_args_accepts_debug_and_debug_stream_combination() -> None:
    """验证 ``--debug`` 可与 ``--debug-stream`` 同时出现。"""

    args = parse_cli_args(("prompt", "hello", "--debug", "--debug-stream"))

    assert args.debug_stream is True
    assert args.log_level == "debug"


def test_parse_cli_args_debug_stream_and_quiet_runtime_precedence() -> None:
    """验证 ``--quiet`` 不覆盖 runtime 层的 ``debug_stream`` 优先级。"""

    args = parse_cli_args(("prompt", "hello", "--debug-stream", "--quiet"))
    resolved = runtime_log.set_level_from_flags(
        log_level=args.log_level,
        debug=False,
        verbose=False,
        info=False,
        quiet=False,
        debug_stream=args.debug_stream,
    )

    assert args.log_level == "error"
    assert args.debug_stream is True
    assert resolved is runtime_log.LogLevel.STREAM_DEBUG


@pytest.mark.parametrize(
    ("argv", "expected_detail", "expected_log_level"),
    (
        (("prompt", "hello", "--detail"), True, "info"),
        (("prompt", "hello", "--no-detail"), False, "info"),
        (("prompt", "hello", "--verbose"), True, "verbose"),
        (("prompt", "hello", "--debug"), True, "debug"),
        (("prompt", "hello", "--detail", "--verbose"), True, "verbose"),
        (("interactive", "--detail"), True, "info"),
        (("interactive", "--no-detail"), False, "info"),
        (("interactive", "--debug"), True, "debug"),
    ),
)
def test_agent_detail_flags_are_orthogonal_to_log_level(
    argv: tuple[str, ...],
    expected_detail: bool,
    expected_log_level: str,
) -> None:
    """验证 Agent detail flag 与日志等级互不隐式联动。

    :param argv: 待解析的 CLI 参数。
    :param expected_detail: 预期 detail 值。
    :param expected_log_level: 预期日志等级。
    :returns: ``None``。
    :raises AssertionError: 解析结果不符合契约时抛出。
    """

    args = parse_cli_args(argv)

    assert args.detail is expected_detail
    assert args.log_level == expected_log_level


def test_prompt_detail_flags_are_mutually_exclusive() -> None:
    """验证 ``--detail`` 与 ``--no-detail`` 互斥。

    :returns: ``None``。
    :raises AssertionError: argparse 未拒绝互斥参数时抛出。
    """

    with pytest.raises(SystemExit) as raised:
        parse_cli_args(("prompt", "hello", "--detail", "--no-detail"))

    assert raised.value.code == EXIT_USAGE_ERROR


def test_interactive_detail_flags_are_mutually_exclusive() -> None:
    """验证 interactive ``--detail`` 与 ``--no-detail`` 互斥。

    :returns: ``None``。
    :raises AssertionError: argparse 未拒绝互斥参数时抛出。
    """

    with pytest.raises(SystemExit) as raised:
        parse_cli_args(("interactive", "--detail", "--no-detail"))

    assert raised.value.code == EXIT_USAGE_ERROR
