"""Dayu CLI 参数解析与退出码骨架测试。"""

from __future__ import annotations

import argparse
import io
import logging
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from types import ModuleType
from typing import Never, TextIO, cast
from unittest.mock import Mock

import pytest

from dayu.cli.__main__ import run_module
import dayu.cli.arg_parsing as cli_arg_parsing
import dayu.cli.main as cli_main
import dayu.runtime.log as runtime_log
from dayu.cli.arg_parsing import (
    CLI_COMMAND_NAMES,
    EXCLUDED_COMMAND_NAMES,
    INVALID_UTF8_INVOCATION_DIAGNOSTIC,
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
from dayu.fins.upload_format_contract import FINS_UPLOAD_FORMAT_TEXT

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
        "--label",
        "--detail",
        "--no-detail",
        "--model",
        "--temperature",
    ),
    "download": (
        "--ticker",
        "公司代码或财报主体（必填）。",
        "--forms",
        "--start",
        "--end",
        "--overwrite",
    ),
    "upload_filing": (
        "--ticker",
        "第一项是该公司财报归档的 canonical ticker",
        "--action",
        "--files",
        "--fiscal-year",
        "--filing-date",
        "--company-name",
        "--overwrite",
    ),
    "upload_material": (
        "--ticker",
        "成功保存公司元数据后均查询同一归档",
        "--action",
        "--forms",
        "--material-name",
        "--files",
        "--document-id",
        "--internal-document-id",
    ),
    "upload_filings_from": (
        "--ticker",
        "系统信任声明且不联网核验",
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
_LOG_LEVEL_SELECTOR_CASES: tuple[
    tuple[tuple[str, ...], runtime_log.DiagnosticLogLevel], ...
] = (
    (("--log-level", "debug"), runtime_log.DiagnosticLogLevel.DEBUG),
    (("--log-level", "verbose"), runtime_log.DiagnosticLogLevel.VERBOSE),
    (("--log-level", "info"), runtime_log.DiagnosticLogLevel.INFO),
    (("--log-level", "warn"), runtime_log.DiagnosticLogLevel.WARNING),
    (("--log-level", "warning"), runtime_log.DiagnosticLogLevel.WARNING),
    (("--log-level", "error"), runtime_log.DiagnosticLogLevel.ERROR),
    (("--log-level", "critical"), runtime_log.DiagnosticLogLevel.CRITICAL),
    (("--log-level", "quiet"), runtime_log.DiagnosticLogLevel.QUIET),
    (("--debug",), runtime_log.DiagnosticLogLevel.DEBUG),
    (("--verbose",), runtime_log.DiagnosticLogLevel.VERBOSE),
    (("--info",), runtime_log.DiagnosticLogLevel.INFO),
    (("--warn",), runtime_log.DiagnosticLogLevel.WARNING),
    (("--warning",), runtime_log.DiagnosticLogLevel.WARNING),
    (("--error",), runtime_log.DiagnosticLogLevel.ERROR),
    (("--critical",), runtime_log.DiagnosticLogLevel.CRITICAL),
    (("--quiet",), runtime_log.DiagnosticLogLevel.QUIET),
)
_NON_QUIET_LOG_LEVEL_SELECTOR_CASES = tuple(
    selector_case
    for selector_case in _LOG_LEVEL_SELECTOR_CASES
    if selector_case[1] is not runtime_log.DiagnosticLogLevel.QUIET
)
_DEBUG_STREAM_LOG_FILE_CASES: tuple[
    tuple[tuple[str, ...], runtime_log.DiagnosticLogLevel], ...
] = (
    ((), runtime_log.DiagnosticLogLevel.INFO),
    *_NON_QUIET_LOG_LEVEL_SELECTOR_CASES,
)


@dataclass(frozen=True, slots=True)
class _LogAssemblyCall:
    """CLI main 日志装配调用记录。"""

    level: runtime_log.DiagnosticLogLevel
    debug_stream: bool
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


def _collect_parser_tree(
    parser: argparse.ArgumentParser,
) -> tuple[argparse.ArgumentParser, ...]:
    """递归收集 root、command 与 action parser。

    :param parser: 当前 argparse parser。
    :returns: 包含当前 parser 及全部子 parser 的稳定元组。
    :raises AssertionError: subparser choices 不是 argparse parser 时抛出。
    """

    parsers = [parser]
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        child_parsers = cast(
            dict[str, argparse.ArgumentParser],
            action.choices,
        )
        for child_parser in child_parsers.values():
            if not isinstance(child_parser, argparse.ArgumentParser):
                raise AssertionError("subparser choice must be ArgumentParser")
            parsers.extend(_collect_parser_tree(child_parser))
    return tuple(parsers)


def _raise_keyboard_interrupt(_args: ParsedCliArgs) -> int:
    """测试用命令 runner，模拟用户中断。

    :param _args: 已解析的 CLI 参数。
    :returns: 正常路径不会返回。
    :raises KeyboardInterrupt: 始终抛出以验证 main 的退出码映射。
    """

    raise KeyboardInterrupt


class _InterruptedCliMainModule(ModuleType):
    """在 bootstrap 解析 ``main`` symbol 时模拟启动中断的模块。"""

    @property
    def main(self) -> Never:
        """模拟重型 CLI application import 尚未完成时的 Ctrl+C。

        :returns: 本属性不会返回。
        :raises KeyboardInterrupt: 始终抛出启动中断。
        """

        raise KeyboardInterrupt


def _raise_standard_stream_startup_interrupt(_stream: TextIO) -> None:
    """模拟标准流配置阶段发生 Ctrl+C。

    :param _stream: CLI 标准文本流；测试不消费。
    :returns: 本函数不会返回。
    :raises KeyboardInterrupt: 始终抛出启动中断。
    """

    raise KeyboardInterrupt


def _raise_parser_startup_interrupt(
    _argv: Sequence[str] | None = None,
) -> ParsedCliArgs:
    """模拟 parser 启动阶段发生 Ctrl+C。

    :param _argv: 待解析 argv；测试不消费。
    :returns: 本函数不会返回。
    :raises KeyboardInterrupt: 始终抛出启动中断。
    """

    raise KeyboardInterrupt


def _raise_log_resource_startup_interrupt() -> TextIO | None:
    """模拟默认日志资源准备阶段发生 Ctrl+C。

    :returns: 本函数不会返回。
    :raises KeyboardInterrupt: 始终抛出启动中断。
    """

    raise KeyboardInterrupt


def _fail_primary_operation(_args: ParsedCliArgs) -> int:
    """拒绝 startup interruption 测试误入 primary operation。

    :param _args: 已解析参数；测试不消费。
    :returns: 本函数不会返回。
    :raises AssertionError: 任何调用都表示启动边界失效。
    """

    raise AssertionError("primary operation must not start during startup interrupt")


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


def test_upload_filing_files_help_consumes_self_contained_format_projection(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """upload_filing ``--files`` help 必须直接消费 Fins owner 文本投影。

    Args:
        capsys: pytest 标准输出捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: help source、角色准入或候选格式限定文案漂移时抛出。
    """

    parser = build_parser()
    filing_parser = next(child for child in _collect_parser_tree(parser) if child.prog.endswith(" upload_filing"))
    files_action = next(action for action in filing_parser._actions if "--files" in action.option_strings)
    assert files_action.help == FINS_UPLOAD_FORMAT_TEXT.filing_files

    help_text = "".join(_capture_help(capsys, ("upload_filing",)).split())
    for expected_fragment in (
        "auto/create/update 必须至少提供一个文件",
        "首文件是主文件",
        "必须实际转换成功",
        "仅原样保存、不转换",
        ".xsd",
        ".xml 仅是 XBRL XML 候选",
        "不代表任意 XML",
        ".json 仅是 Docling JSON 候选",
        "不代表任意 JSON 内容可转换",
        "主文件后缀通过只表示具备转换资格",
        "不保证文件内容转换成功",
        "随附文件只校验可随批保存的后缀，不执行转换",
        "delete 不得提供文件",
    ):
        assert "".join(expected_fragment.split()) in help_text


def test_upload_material_files_help_consumes_self_contained_format_projection(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """upload_material ``--files`` help 必须直接消费 Fins owner 文本投影。

    Args:
        capsys: pytest 标准输出捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: help source、转换要求或文件空状态文案漂移时抛出。
    """

    parser = build_parser()
    material_parser = next(
        child for child in _collect_parser_tree(parser) if child.prog.endswith(" upload_material")
    )
    files_action = next(
        action for action in material_parser._actions if "--files" in action.option_strings
    )
    assert files_action.help == FINS_UPLOAD_FORMAT_TEXT.material_files

    help_text = "".join(_capture_help(capsys, ("upload_material",)).split())
    for expected_fragment in (
        "auto/create/update 必须至少提供一个文件",
        "每个文件都必须使用转换器支持的后缀",
        "逐个实际转换成功",
        "后缀通过只表示具备转换资格",
        "不保证文件内容转换成功",
        "delete 不得提供文件",
    ):
        assert "".join(expected_fragment.split()) in help_text


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


def test_agent_help_omits_removed_parameters(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证 Agent surface help 不暴露已删除参数。

    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: help 仍暴露已删除参数时抛出。
    """

    prompt_help = _capture_help(capsys, ("prompt",))
    interactive_help = _capture_help(capsys, ("interactive",))

    assert "--ticker" in prompt_help
    assert "--config" not in prompt_help
    assert "--ticker" not in interactive_help
    assert "--config" not in interactive_help


def test_every_parser_scope_omits_removed_config_action() -> None:
    """root、command 与 action parser 均不得注册已删除配置选项。

    :returns: ``None``。
    :raises AssertionError: 任一 parser action 仍暴露 ``--config`` 时抛出。
    """

    parser = build_parser()

    for scoped_parser in _collect_parser_tree(parser):
        option_strings = {
            option
            for action in scoped_parser._actions
            for option in action.option_strings
        }
        assert "--config" not in option_strings


@pytest.mark.parametrize(
    "command_path",
    (
        (),
        *((command_name,) for command_name in CLI_COMMAND_NAMES),
        ("session", "list"),
        ("session", "resume"),
        ("session", "purge"),
        ("tool_trace", "analyze"),
    ),
)
def test_every_parser_help_omits_removed_config(
    command_path: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """root、command 与 action help 均不得展示已删除配置选项。

    :param command_path: 待读取 help 的 parser 路径。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 任一 help 仍展示 ``--config`` 时抛出。
    """

    assert "--config" not in _capture_help(capsys, command_path)


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
    assert "--kind" not in purge_help
    assert "--yes" in purge_help
    assert "--session-id" in resume_help
    assert "--label" in resume_help
    assert "--kind" not in resume_help
    assert "--config" not in resume_help
    assert "--mode" in resume_help


def test_missing_command_exits_with_usage_error() -> None:
    """验证缺少子命令时按 argparse 用法错误返回 2。

    :returns: ``None``。
    :raises AssertionError: 退出码不是用法错误时抛出。
    """

    assert cli_main.main(()) == EXIT_USAGE_ERROR


def test_parse_cli_args_preserves_valid_unicode_invocation_text() -> None:
    """CLI invocation owner 必须原样保留合法中文与 emoji。

    :returns: ``None``。
    :raises AssertionError: 合法 UTF-8 文本被拒绝或改写时抛出。
    """

    prompt = "分析收入变化 📈"

    args = parse_cli_args(("prompt", prompt))

    assert args.prompt == prompt


@pytest.mark.parametrize(
    "argv",
    (
        ("\udcff",),
        ("prompt", "--base", "\udcff", "hello"),
        ("prompt", "\udcff"),
    ),
)
def test_main_rejects_invalid_utf8_before_primary_operation(
    argv: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """surrogateescape argv 必须在 parser 边界 exit 2 且零 primary 副作用。

    :param argv: 在 command、option value 或 positional 注入 surrogate 的参数。
    :param monkeypatch: pytest runtime owner 替换夹具。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 输入越过 parser 或 diagnostic 不可编码时抛出。
    """

    default_log_open = Mock(
        side_effect=AssertionError("invalid argv must not prepare log resources")
    )
    log_configuration = Mock(
        side_effect=AssertionError("invalid argv must not configure runtime logging")
    )
    monkeypatch.setattr(cli_main, "_open_default_log_file", default_log_open)
    monkeypatch.setattr(
        cli_main.runtime_log,
        "configure_selected_diagnostics",
        log_configuration,
    )
    monkeypatch.setitem(cli_main.COMMAND_RUNNERS, "prompt", _fail_primary_operation)

    assert cli_main.main(argv) == EXIT_USAGE_ERROR
    captured = capsys.readouterr()
    assert captured.out == ""
    assert INVALID_UTF8_INVOCATION_DIAGNOSTIC in captured.err
    assert "Traceback" not in captured.err
    assert "UnicodeEncodeError" not in captured.err
    assert "\udcff" not in captured.err
    captured.err.encode("utf-8", errors="strict")
    default_log_open.assert_not_called()
    log_configuration.assert_not_called()


@pytest.mark.skipif(os.name == "nt", reason="Windows 不使用 POSIX bytes argv")
def test_module_rejects_raw_non_utf8_argv_without_side_effects(tmp_path: Path) -> None:
    """真实 POSIX bytes argv 必须稳定 exit 2 且不创建日志或业务状态。

    :param tmp_path: pytest 临时父目录。
    :returns: ``None``。
    :raises AssertionError: raw argv、输出编码、退出码或副作用 contract 失败时抛出。
    """

    workspace_root = tmp_path / "workspace"
    log_file = tmp_path / "invalid-argv.log"
    completed = subprocess.run(
        (
            os.fsencode(sys.executable),
            b"-m",
            b"dayu.cli",
            b"prompt",
            b"--base",
            os.fsencode(workspace_root),
            b"--log-file",
            os.fsencode(log_file),
            b"\xff",
        ),
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        check=False,
    )

    stderr = completed.stderr.decode("utf-8", errors="strict")
    assert completed.returncode == EXIT_USAGE_ERROR
    assert completed.stdout == b""
    assert INVALID_UTF8_INVOCATION_DIAGNOSTIC in stderr
    assert "Traceback" not in stderr
    assert "UnicodeEncodeError" not in stderr
    assert b"\xff" not in completed.stderr
    assert not log_file.exists()
    assert not workspace_root.exists()


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
    args.log_level = runtime_log.DiagnosticLogLevel.INFO
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


def test_run_module_maps_keyboard_interrupt_during_lazy_application_import(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """公共 bootstrap 必须覆盖 CLI application lazy import 中断。

    :param monkeypatch: pytest 模块表替换夹具。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 中断未归一为 130 或输出 traceback 时抛出。
    """

    interrupted_module = _InterruptedCliMainModule("dayu.cli.main")
    monkeypatch.setitem(sys.modules, "dayu.cli.main", interrupted_module)

    assert run_module() == EXIT_KEYBOARD_INTERRUPT
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.parametrize(
    "startup_phase",
    ("standard_stream", "parser", "log_resource"),
)
def test_run_module_maps_keyboard_interrupt_before_primary_operation(
    startup_phase: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """公共 bootstrap 必须覆盖 main 内 primary operation 前的启动中断。

    :param startup_phase: 注入中断的轻量启动阶段。
    :param monkeypatch: pytest 属性与 argv 替换夹具。
    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 中断未归一为 130、误入 runner 或输出 traceback 时抛出。
    """

    monkeypatch.setattr(sys, "argv", ["dayu-cli", "prompt", "请分析收入变化"])
    monkeypatch.setitem(cli_main.COMMAND_RUNNERS, "prompt", _fail_primary_operation)
    if startup_phase == "standard_stream":
        monkeypatch.setattr(
            cli_main,
            "_configure_cli_standard_stream",
            _raise_standard_stream_startup_interrupt,
        )
    elif startup_phase == "parser":
        monkeypatch.setattr(cli_main, "parse_cli_args", _raise_parser_startup_interrupt)
    else:
        monkeypatch.setattr(
            cli_main,
            "_open_default_log_file",
            _raise_log_resource_startup_interrupt,
        )

    assert run_module() == EXIT_KEYBOARD_INTERRUPT
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


@pytest.mark.parametrize(
    ("argv", "expected_log_level", "expected_debug_stream"),
    (
        (("prompt", "hello"), runtime_log.DiagnosticLogLevel.INFO, False),
        (("prompt", "hello", "--debug"), runtime_log.DiagnosticLogLevel.DEBUG, False),
        (("prompt", "hello", "--verbose"), runtime_log.DiagnosticLogLevel.VERBOSE, False),
        (("prompt", "hello", "--warning"), runtime_log.DiagnosticLogLevel.WARNING, False),
        (("prompt", "hello", "--quiet"), runtime_log.DiagnosticLogLevel.QUIET, False),
        (("prompt", "hello", "--log-level", "warn"), runtime_log.DiagnosticLogLevel.WARNING, False),
        (("prompt", "hello", "--log-level", "critical"), runtime_log.DiagnosticLogLevel.CRITICAL, False),
        (("prompt", "hello", "--debug-stream"), runtime_log.DiagnosticLogLevel.INFO, True),
    ),
)
def test_main_configures_runtime_log_from_parsed_cli_flags(
    argv: tuple[str, ...],
    expected_log_level: runtime_log.DiagnosticLogLevel,
    expected_debug_stream: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLI main 必须把默认日志参数交给 runtime log helper 与临时文件。

    :param argv: 待执行的 CLI 参数。
    :param expected_log_level: argparse 归一后的 canonical 日志级别。
    :param expected_debug_stream: 预期传入 runtime helper 的 stream debug flag。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: main 未调用 runtime helper 或在 main 内改写参数时抛出。
    """

    calls: list[_LogAssemblyCall] = []
    events: list[str] = []
    log_stream = _TrackingLogStream(events)

    def spy_configure_selected_diagnostics(
        *,
        level: runtime_log.DiagnosticLogLevel,
        debug_stream: bool,
        stream: TextIO | None = None,
    ) -> runtime_log.LogLevel:
        """记录 main 传入 runtime log helper 的参数。

        :param level: argparse 已解析的 canonical 日志级别。
        :param debug_stream: runtime helper 的 stream debug flag。
        :param stream: runtime helper 的诊断日志输出流。
        :returns: 测试用日志级别。
        :raises Exception: 不主动抛出异常。
        """

        calls.append(
            _LogAssemblyCall(
                level=level,
                debug_stream=debug_stream,
                stream=stream,
            )
        )
        return runtime_log.LogLevel.INFO

    monkeypatch.setattr(
        cli_main.runtime_log,
        "configure_selected_diagnostics",
        spy_configure_selected_diagnostics,
    )
    monkeypatch.setattr(cli_main, "_open_default_log_file", lambda: log_stream)
    monkeypatch.setitem(cli_main.COMMAND_RUNNERS, "prompt", _return_success)

    assert cli_main.main(argv) == EXIT_SUCCESS
    assert len(calls) == 2
    assert calls[0] == _LogAssemblyCall(
        level=expected_log_level,
        debug_stream=expected_debug_stream,
        stream=log_stream,
    )
    assert calls[1] == _LogAssemblyCall(
        level=expected_log_level,
        debug_stream=expected_debug_stream,
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

    def spy_configure_selected_diagnostics(
        *,
        level: runtime_log.DiagnosticLogLevel,
        debug_stream: bool,
        stream: TextIO | None = None,
    ) -> runtime_log.LogLevel:
        """记录 runtime log helper 调用。

        :param level: argparse 已解析的 canonical 日志级别。
        :param debug_stream: runtime helper 的 stream debug flag。
        :param stream: runtime helper 的诊断日志输出流。
        :returns: 测试用日志级别。
        :raises Exception: 不主动抛出异常。
        """

        calls.append(
            _LogAssemblyCall(
                level=level,
                debug_stream=debug_stream,
                stream=stream,
            )
        )
        return runtime_log.LogLevel.INFO

    monkeypatch.setattr(
        cli_main.runtime_log,
        "configure_selected_diagnostics",
        spy_configure_selected_diagnostics,
    )
    monkeypatch.setitem(cli_main.COMMAND_RUNNERS, "prompt", _return_success)

    log_file = tmp_path / "dayu.log"

    assert (
        cli_main.main(("prompt", "请分析收入变化", "--log-file", str(log_file)))
        == EXIT_SUCCESS
    )
    assert len(calls) == 2
    assert calls[0].level is runtime_log.DiagnosticLogLevel.INFO
    assert calls[0].stream is not sys.stderr
    assert calls[0].stream is not None
    assert calls[0].stream.closed
    assert calls[1] == _LogAssemblyCall(
        level=runtime_log.DiagnosticLogLevel.INFO,
        debug_stream=False,
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

    def spy_configure_selected_diagnostics(
        *,
        level: runtime_log.DiagnosticLogLevel,
        debug_stream: bool,
        stream: TextIO | None = None,
    ) -> runtime_log.LogLevel:
        """记录恢复 stderr 与关闭文件的相对顺序。

        :param level: argparse 已解析的 canonical 日志级别。
        :param debug_stream: runtime helper 的 stream debug flag。
        :param stream: runtime helper 的诊断日志输出流。
        :returns: 测试用日志级别。
        :raises Exception: 不主动抛出异常。
        """

        if stream is sys.stderr:
            events.append("restore-stderr")
        elif stream is log_stream:
            events.append("configure-file")
        assert level is runtime_log.DiagnosticLogLevel.INFO
        assert debug_stream is False
        return runtime_log.LogLevel.INFO

    monkeypatch.setattr(cli_main, "_open_log_file", fake_open_log_file)
    monkeypatch.setattr(
        cli_main.runtime_log,
        "configure_selected_diagnostics",
        spy_configure_selected_diagnostics,
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

    def spy_configure_selected_diagnostics(
        *,
        level: runtime_log.DiagnosticLogLevel,
        debug_stream: bool,
        stream: TextIO | None = None,
    ) -> runtime_log.LogLevel:
        """模拟恢复 stderr handler 失败并记录文件关闭顺序。

        :param level: argparse 已解析的 canonical 日志级别。
        :param debug_stream: runtime helper 的 stream debug flag。
        :param stream: runtime helper 的诊断日志输出流。
        :returns: 测试用日志级别。
        :raises ValueError: 恢复 stderr handler 时按测试设定抛出。
        """

        assert level is runtime_log.DiagnosticLogLevel.INFO
        assert debug_stream is False
        if stream is sys.stderr:
            events.append("restore-stderr")
            raise ValueError(_RESTORE_FAILURE_MESSAGE)
        if stream is log_stream:
            events.append("configure-file")
        return runtime_log.LogLevel.INFO

    monkeypatch.setattr(cli_main, "_open_log_file", fake_open_log_file)
    monkeypatch.setattr(
        cli_main.runtime_log,
        "configure_selected_diagnostics",
        spy_configure_selected_diagnostics,
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

    def spy_configure_selected_diagnostics(
        *,
        level: runtime_log.DiagnosticLogLevel,
        debug_stream: bool,
        stream: TextIO | None = None,
    ) -> runtime_log.LogLevel:
        """记录 ``KeyboardInterrupt`` 路径的恢复 stderr 与关闭文件顺序。

        :param level: argparse 已解析的 canonical 日志级别。
        :param debug_stream: runtime helper 的 stream debug flag。
        :param stream: runtime helper 的诊断日志输出流。
        :returns: 测试用日志级别。
        :raises Exception: 不主动抛出异常。
        """

        assert level is runtime_log.DiagnosticLogLevel.INFO
        assert debug_stream is False
        if stream is sys.stderr:
            events.append("restore-stderr")
        elif stream is log_stream:
            events.append("configure-file")
        return runtime_log.LogLevel.INFO

    monkeypatch.setattr(cli_main, "_open_log_file", fake_open_log_file)
    monkeypatch.setattr(
        cli_main.runtime_log,
        "configure_selected_diagnostics",
        spy_configure_selected_diagnostics,
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


def test_main_returns_resource_error_when_log_file_parent_is_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺失 ``--log-file`` 父目录必须 exit 1 且不执行 primary operation。

    :param tmp_path: pytest 临时目录夹具。
    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest monkeypatch 夹具。
    :returns: ``None``。
    :raises AssertionError: 错误分类、文件副作用或执行顺序不符合 contract 时抛出。
    """

    runtime_configuration = Mock(
        side_effect=AssertionError("resource failure must precede runtime logging")
    )
    monkeypatch.setattr(
        cli_main.runtime_log,
        "configure_selected_diagnostics",
        runtime_configuration,
    )
    monkeypatch.setitem(cli_main.COMMAND_RUNNERS, "prompt", _fail_primary_operation)
    missing_parent = tmp_path / "missing" / "dayu.log"

    assert (
        cli_main.main(("prompt", "请分析收入变化", "--log-file", str(missing_parent)))
        == EXIT_FAILURE
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--log-file" in captured.err
    assert "cannot open" in captured.err
    assert str(missing_parent) in captured.err
    assert "Traceback" not in captured.err
    assert not missing_parent.parent.exists()
    assert not missing_parent.exists()
    runtime_configuration.assert_not_called()


def test_main_returns_usage_error_when_log_file_is_empty(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空白 ``--log-file`` 路径必须返回 usage error。

    :param capsys: pytest 标准输出捕获夹具。
    :param monkeypatch: pytest primary runner 替换夹具。
    :returns: ``None``。
    :raises AssertionError: 空白路径没有被拒绝时抛出。
    """

    monkeypatch.setitem(cli_main.COMMAND_RUNNERS, "prompt", _fail_primary_operation)

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
    "argv",
    (
        ("--config=/tmp/x", "prompt", "hello"),
        ("init", "--config=/tmp/x"),
        ("prompt", "--config=/tmp/x", "hello"),
        ("interactive", "--config=/tmp/x"),
        ("download", "--config=/tmp/x", "--ticker", "AAPL"),
        ("session", "--config=/tmp/x", "list"),
        ("session", "list", "--config=/tmp/x"),
        (
            "session",
            "resume",
            "--session-id",
            "session-1",
            "--mode",
            "interactive",
            "--config=/tmp/x",
        ),
        (
            "session",
            "purge",
            "--session-id",
            "session-1",
            "--yes",
            "--config=/tmp/x",
        ),
        (
            "tool_trace",
            "analyze",
            "trace.jsonl",
            "--output-dir",
            "reports",
            "--config=/tmp/x",
        ),
    ),
)
def test_removed_config_is_argparse_unknown_in_every_parser_scope(
    argv: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """已删除配置选项在 root、command 与 action scope 均走 unknown path。

    :param argv: 待解析的完整 CLI 参数。
    :param capsys: pytest 标准错误捕获夹具。
    :returns: ``None``。
    :raises AssertionError: argparse 未以 canonical unknown option 拒绝时抛出。
    """

    with pytest.raises(SystemExit) as raised:
        parse_cli_args(argv)
    captured = capsys.readouterr()

    assert raised.value.code == EXIT_USAGE_ERROR
    assert "unrecognized arguments" in captured.err
    assert "--config" in captured.err


@pytest.mark.parametrize(
    "argv",
    (
        ("--config", "/tmp/x", "prompt", "hello"),
        ("prompt", "--config", "/tmp/x", "hello"),
        ("interactive", "--config", "/tmp/x"),
        ("session", "--config", "/tmp/x", "list"),
        ("session", "list", "--config", "/tmp/x"),
    ),
)
def test_removed_config_split_value_form_never_produces_namespace(
    argv: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """旧 ``--config /tmp/x`` 形式在任意 parser scope 都必须失败。

    删除 action 后，argparse 不再把第二个 token 绑定为 option value；root 或
    command scope 可能因此把该 token 报为非法子命令，但都必须在有效 namespace
    返回和命令分发前以 parser usage error 结束。

    :param argv: 覆盖 root、command 与 action scope 的旧 split-value 调用。
    :param capsys: pytest 标准错误捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 任一旧调用仍产生有效 namespace 时抛出。
    """

    with pytest.raises(SystemExit) as raised:
        parse_cli_args(argv)
    captured = capsys.readouterr()

    assert raised.value.code == EXIT_USAGE_ERROR
    assert "error:" in captured.err


def test_parsed_namespace_omits_removed_config_field() -> None:
    """正常解析结果不得残留已删除配置字段或默认值。

    :returns: ``None``。
    :raises AssertionError: namespace 仍含 ``config_dir`` 时抛出。
    """

    args = parse_cli_args(("prompt", "hello"))

    assert "config_dir" not in vars(args)


def test_interactive_rejects_removed_ticker_and_session_kind() -> None:
    """interactive ticker 与 session kind 必须从 parser surface 消失。

    :returns: ``None``。
    :raises AssertionError: 任一 removed 参数未返回用法错误 2 时抛出。
    """

    with pytest.raises(SystemExit) as ticker_error:
        parse_cli_args(("interactive", "--ticker", "AAPL"))
    with pytest.raises(SystemExit) as kind_error:
        parse_cli_args(
            (
                "session",
                "purge",
                "--label",
                "earnings",
                "--kind",
                "prompt",
                "--yes",
            )
        )

    assert ticker_error.value.code == EXIT_USAGE_ERROR
    assert kind_error.value.code == EXIT_USAGE_ERROR


def test_prompt_and_prompt_resume_keep_ticker() -> None:
    """prompt 与 prompt-mode resume 必须保留 ticker 参数。

    :returns: ``None``。
    :raises AssertionError: 任一 prompt surface 丢失 ticker 映射时抛出。
    """

    prompt_args = parse_cli_args(("prompt", "--ticker", "AAPL", "hello"))
    resume_args = parse_cli_args(
        (
            "session",
            "resume",
            "--session-id",
            "session-1",
            "--mode",
            "prompt",
            "--ticker",
            "MSFT",
            "hello",
        )
    )

    assert prompt_args.ticker == "AAPL"
    assert resume_args.ticker == "MSFT"


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
    assert args.log_level is runtime_log.DiagnosticLogLevel.INFO


def test_interactive_detail_defaults_to_detail() -> None:
    """验证 interactive 默认显示运行态细节。

    :returns: ``None``。
    :raises AssertionError: ``detail`` 默认值不符合契约时抛出。
    """

    args = parse_cli_args(("interactive",))

    assert args.detail is True
    assert args.log_level is runtime_log.DiagnosticLogLevel.INFO


def test_parse_cli_args_accepts_debug_stream() -> None:
    """验证 ``--debug-stream`` 作为全局日志开关独立解析。

    :returns: ``None``。
    :raises AssertionError: debug-stream 或 canonical 默认等级错误时抛出。
    """

    args = parse_cli_args(("prompt", "hello", "--debug-stream"))

    assert args.debug_stream is True
    assert args.log_level is runtime_log.DiagnosticLogLevel.INFO


def test_parse_cli_args_accepts_debug_and_debug_stream_combination() -> None:
    """验证 ``--debug`` 可与 ``--debug-stream`` 同时出现。

    :returns: ``None``。
    :raises AssertionError: debug-stream 改写或拒绝 DEBUG 等级时抛出。
    """

    args = parse_cli_args(("prompt", "hello", "--debug", "--debug-stream"))

    assert args.debug_stream is True
    assert args.log_level is runtime_log.DiagnosticLogLevel.DEBUG


@pytest.mark.parametrize(("selector", "expected_level"), _LOG_LEVEL_SELECTOR_CASES)
def test_parse_cli_args_accepts_every_public_log_level_selector(
    selector: tuple[str, ...],
    expected_level: runtime_log.DiagnosticLogLevel,
) -> None:
    """全部公开 spelling 与快捷项必须收敛到唯一 canonical level。

    :param selector: 单个公开日志 selector argv 片段。
    :param expected_level: 预期 canonical diagnostic level。
    :returns: ``None``。
    :raises AssertionError: 任一公开入口缺失或归一化错误时抛出。
    """

    args = parse_cli_args(("prompt", "hello", *selector))

    assert args.log_level is expected_level


@pytest.mark.parametrize(
    ("first_selector", "second_selector"),
    tuple(product(_LOG_LEVEL_SELECTOR_CASES, repeat=2)),
)
def test_main_rejects_every_ordered_log_selector_pair_before_primary_operation(
    first_selector: tuple[tuple[str, ...], runtime_log.DiagnosticLogLevel],
    second_selector: tuple[tuple[str, ...], runtime_log.DiagnosticLogLevel],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """任意两个 selector（含同项重复）都必须 parser exit 2。

    :param first_selector: 第一个 selector case。
    :param second_selector: 第二个 selector case。
    :param monkeypatch: pytest primary runner 替换夹具。
    :returns: ``None``。
    :raises AssertionError: 互斥校验未覆盖任一有序组合时抛出。
    """

    monkeypatch.setitem(cli_main.COMMAND_RUNNERS, "prompt", _fail_primary_operation)
    first_argv, _first_level = first_selector
    second_argv, _second_level = second_selector

    assert (
        cli_main.main(("prompt", "hello", *first_argv, *second_argv))
        == EXIT_USAGE_ERROR
    )


@pytest.mark.parametrize(
    "argv",
    (
        ("--debug", "prompt", "hello", "--warning"),
        ("--log-level", "warn", "prompt", "hello", "--critical"),
        (
            "--debug",
            "session",
            "--warning",
            "resume",
            "--session-id",
            "session-1",
            "--mode",
            "prompt",
            "hello",
        ),
        (
            "--debug",
            "session",
            "resume",
            "--warning",
            "--session-id",
            "session-1",
            "--mode",
            "prompt",
            "hello",
        ),
        (
            "session",
            "--debug",
            "resume",
            "--warning",
            "--session-id",
            "session-1",
            "--mode",
            "prompt",
            "hello",
        ),
    ),
)
def test_parse_cli_args_rejects_log_selectors_across_parser_scopes(
    argv: tuple[str, ...],
) -> None:
    """root、command、action scope 的 selector occurrence 必须统一互斥。

    :param argv: 将两个 selector 分布在不同 parser scope 的参数。
    :returns: ``None``。
    :raises AssertionError: namespace merge 丢失任一 occurrence 时抛出。
    """

    with pytest.raises(SystemExit) as raised:
        parse_cli_args(argv)

    assert raised.value.code == EXIT_USAGE_ERROR


def test_log_selector_occurrences_do_not_leak_across_parser_invocations() -> None:
    """同一 parser 连续解析时 selector 列表必须由 fresh namespace 隔离。

    :returns: ``None``。
    :raises AssertionError: argparse action 保存跨 invocation mutable state 时抛出。
    """

    parser = build_parser()
    first = cast(
        ParsedCliArgs,
        parser.parse_args(
            ("prompt", "hello", "--debug"),
            namespace=cli_arg_parsing._new_default_namespace(),
        ),
    )
    cli_arg_parsing._finalize_log_level_selection(first, parser=parser)
    second = cast(
        ParsedCliArgs,
        parser.parse_args(
            ("prompt", "hello", "--warning"),
            namespace=cli_arg_parsing._new_default_namespace(),
        ),
    )
    cli_arg_parsing._finalize_log_level_selection(second, parser=parser)

    assert first.log_level is runtime_log.DiagnosticLogLevel.DEBUG
    assert second.log_level is runtime_log.DiagnosticLogLevel.WARNING
    assert first._command_log_level_selectors == [
        runtime_log.DiagnosticLogLevel.DEBUG
    ]
    assert second._command_log_level_selectors == [
        runtime_log.DiagnosticLogLevel.WARNING
    ]


@pytest.mark.parametrize(
    ("selector", "expected_level"),
    _NON_QUIET_LOG_LEVEL_SELECTOR_CASES,
)
def test_debug_stream_is_orthogonal_to_every_non_quiet_selector(
    selector: tuple[str, ...],
    expected_level: runtime_log.DiagnosticLogLevel,
) -> None:
    """debug-stream 与所有非 quiet selector 合法且不改变普通等级。

    :param selector: 非 quiet 日志 selector argv 片段。
    :param expected_level: selector 对应 canonical ordinary level。
    :returns: ``None``。
    :raises AssertionError: debug-stream 改写或拒绝普通等级时抛出。
    """

    args = parse_cli_args(("prompt", "hello", *selector, "--debug-stream"))

    assert args.log_level is expected_level
    assert args.debug_stream is True


@pytest.mark.parametrize(
    "argv",
    (
        ("prompt", "hello", "--quiet", "--debug-stream"),
        ("prompt", "hello", "--debug-stream", "--quiet"),
        ("prompt", "hello", "--log-level", "quiet", "--debug-stream"),
        ("prompt", "hello", "--debug-stream", "--log-level", "quiet"),
    ),
)
def test_quiet_and_debug_stream_are_mutually_exclusive(
    argv: tuple[str, ...],
) -> None:
    """quiet 的两种入口与 debug-stream 的两种顺序均须 exit 2。

    :param argv: quiet/debug-stream 冲突参数。
    :returns: ``None``。
    :raises AssertionError: parser 未拒绝冲突时抛出。
    """

    with pytest.raises(SystemExit) as raised:
        parse_cli_args(argv)

    assert raised.value.code == EXIT_USAGE_ERROR


@pytest.mark.parametrize(("selector", "expected_level"), _LOG_LEVEL_SELECTOR_CASES)
def test_log_file_is_independent_from_every_log_level_selector(
    selector: tuple[str, ...],
    expected_level: runtime_log.DiagnosticLogLevel,
) -> None:
    """log-file 必须与每个合法 selector 独立组合。

    :param selector: 单个公开日志 selector argv 片段。
    :param expected_level: 预期 canonical level。
    :returns: ``None``。
    :raises AssertionError: log-file 被误放入 selector 互斥组时抛出。
    """

    args = parse_cli_args(
        ("prompt", "hello", *selector, "--log-file", "diagnostics.log")
    )

    assert args.log_level is expected_level
    assert args.log_file == "diagnostics.log"


@pytest.mark.parametrize(
    ("selector", "expected_level"),
    _DEBUG_STREAM_LOG_FILE_CASES,
)
def test_log_file_is_independent_from_every_debug_stream_combination(
    selector: tuple[str, ...],
    expected_level: runtime_log.DiagnosticLogLevel,
) -> None:
    """log-file 必须与 debug-stream 的全部合法组合独立。

    :param selector: 空片段或单个非 quiet 日志 selector argv 片段。
    :param expected_level: 预期 canonical ordinary level。
    :returns: ``None``。
    :raises AssertionError: 三项组合丢失、改写或拒绝任一日志事实时抛出。
    """

    args = parse_cli_args(
        (
            "prompt",
            "hello",
            *selector,
            "--debug-stream",
            "--log-file",
            "diagnostics.log",
        )
    )

    assert args.log_level is expected_level
    assert args.debug_stream is True
    assert args.log_file == "diagnostics.log"


@pytest.mark.parametrize(
    ("argv", "expected_detail", "expected_log_level"),
    (
        (("prompt", "hello", "--detail"), True, runtime_log.DiagnosticLogLevel.INFO),
        (("prompt", "hello", "--no-detail"), False, runtime_log.DiagnosticLogLevel.INFO),
        (("prompt", "hello", "--verbose"), True, runtime_log.DiagnosticLogLevel.VERBOSE),
        (("prompt", "hello", "--debug"), True, runtime_log.DiagnosticLogLevel.DEBUG),
        (
            ("prompt", "hello", "--detail", "--verbose"),
            True,
            runtime_log.DiagnosticLogLevel.VERBOSE,
        ),
        (("interactive", "--detail"), True, runtime_log.DiagnosticLogLevel.INFO),
        (("interactive", "--no-detail"), False, runtime_log.DiagnosticLogLevel.INFO),
        (("interactive", "--debug"), True, runtime_log.DiagnosticLogLevel.DEBUG),
    ),
)
def test_agent_detail_flags_are_orthogonal_to_log_level(
    argv: tuple[str, ...],
    expected_detail: bool,
    expected_log_level: runtime_log.DiagnosticLogLevel,
) -> None:
    """验证 Agent detail flag 与日志等级互不隐式联动。

    :param argv: 待解析的 CLI 参数。
    :param expected_detail: 预期 detail 值。
    :param expected_log_level: 预期 canonical 日志等级。
    :returns: ``None``。
    :raises AssertionError: 解析结果不符合契约时抛出。
    """

    args = parse_cli_args(argv)

    assert args.detail is expected_detail
    assert args.log_level is expected_log_level


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
