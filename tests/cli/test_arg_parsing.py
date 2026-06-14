"""Dayu CLI 参数解析与退出码骨架测试。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence

import pytest

from dayu.cli.__main__ import run_module
import dayu.cli.main as cli_main
from dayu.cli.arg_parsing import (
    CLI_COMMAND_NAMES,
    EXCLUDED_COMMAND_NAMES,
    ParsedCliArgs,
    build_parser,
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
        "--model-name",
        "--temperature",
        "--tool-timeout-seconds",
        "--max-iterations",
    ),
    "interactive": (
        "--ticker",
        "--label",
        "--new-session",
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
}


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
    capsys: pytest.CaptureFixture[str],
) -> None:
    """验证已注册命令被分发时返回清晰的 not-implemented 结果。

    :param capsys: pytest 标准输出捕获夹具。
    :returns: ``None``。
    :raises AssertionError: 退出码或错误文本不符合占位契约时抛出。
    """

    exit_code = cli_main.main(("prompt", "请分析收入变化"))
    captured = capsys.readouterr()

    assert exit_code == EXIT_NOT_IMPLEMENTED
    assert "尚未实现" in captured.err
    assert "prompt" in captured.err


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
        ("--base", "workspace-a", "prompt", "hello"),
        namespace=argparse.Namespace(),
    )
    after_command = parser.parse_args(
        ("prompt", "hello", "--base", "workspace-b"),
        namespace=argparse.Namespace(),
    )

    assert before_command.workspace_root == "workspace-a"
    assert after_command.workspace_root == "workspace-b"
