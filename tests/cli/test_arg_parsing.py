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
    "init": ("--base", "--workspace", "--config", "--reset", "--overwrite"),
    "prompt": (
        "prompt",
        "--ticker",
        "--label",
        "--detail",
        "--no-detail",
        "--model-name",
        "--temperature",
        "--tool-timeout-seconds",
        "--max-iterations",
    ),
    "interactive": (
        "--ticker",
        "--label",
        "--model-name",
        "--temperature",
    ),
    "download": ("--ticker", "--forms", "--start", "--end", "--overwrite", "--infer"),
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
    ),
    "process": ("--ticker", "--document-id", "--overwrite", "--ci"),
    "process_filing": ("--ticker", "--document-id", "--overwrite", "--ci"),
    "process_material": ("--ticker", "--document-id", "--overwrite", "--ci"),
    "session": ("list", "resume", "purge"),
}
_TEST_LOGGER_NAME: str = "dayu.cli.test_arg_parsing"
_FIRST_LOG_FILE_DIAGNOSTIC: str = "first run diagnostic"
_SECOND_STDERR_DIAGNOSTIC: str = "second run diagnostic"
_RESTORE_FAILURE_MESSAGE: str = "restore stderr failed"


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


def test_open_default_log_file_creates_persistent_temp_file() -> None:
    """默认日志文件必须创建为可回查的持久临时文件。

    :returns: ``None``。
    :raises AssertionError: 临时日志文件不可写或关闭后不存在时抛出。
    """

    stream = cli_main._open_default_log_file()
    assert stream is not None
    log_path = Path(stream.name)
    try:
        stream.write("default diagnostic\n")
        stream.close()
        assert log_path.exists()
        assert log_path.read_text(encoding="utf-8") == "default diagnostic\n"
    finally:
        if not stream.closed:
            stream.close()
        if log_path.exists():
            log_path.unlink()


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


def test_python_module_help_runs() -> None:
    """验证 ``python -m dayu.cli --help`` 使用同一 parser 并成功退出。

    :returns: ``None``。
    :raises AssertionError: 模块入口退出码或 help 输出不符合契约时抛出。
    """

    result = subprocess.run(
        [sys.executable, "-m", "dayu.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == EXIT_SUCCESS
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
    assert prompt_args.detail is False


def test_prompt_detail_defaults_to_no_detail() -> None:
    """验证 prompt 默认不显示运行态细节。

    :returns: ``None``。
    :raises AssertionError: ``detail`` 默认值不符合契约时抛出。
    """

    args = parse_cli_args(("prompt", "hello"))

    assert args.detail is False
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
        (("prompt", "hello", "--verbose"), False, "verbose"),
        (("prompt", "hello", "--debug"), False, "debug"),
        (("prompt", "hello", "--detail", "--verbose"), True, "verbose"),
    ),
)
def test_prompt_detail_flags_are_orthogonal_to_log_level(
    argv: tuple[str, ...],
    expected_detail: bool,
    expected_log_level: str,
) -> None:
    """验证 prompt detail flag 与日志等级互不隐式联动。

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
