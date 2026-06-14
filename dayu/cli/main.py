"""Dayu CLI 进程入口。

本模块只负责参数解析、命令分发和退出码映射。CLI-01-S1 不执行 Host 或 Fins
业务流程。
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence

from dayu.cli.arg_parsing import CLI_COMMAND_NAMES, ParsedCliArgs, parse_cli_args
from dayu.cli.commands import run_not_implemented_command
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
)

CommandRunner = Callable[[ParsedCliArgs], int]
MISSING_RUNNER_DIAGNOSTIC_TEMPLATE: str = (
    "dayu-cli: 内部错误：命令 '{command_name}' 缺少注册 runner。"
)

COMMAND_RUNNERS: dict[str, CommandRunner] = {
    command_name: run_not_implemented_command for command_name in CLI_COMMAND_NAMES
}


def main(argv: Sequence[str] | None = None) -> int:
    """运行 Dayu CLI 入口。

    :param argv: 不含程序名的命令行参数；为 ``None`` 时使用进程参数。
    :returns: 进程退出码。
    :raises OSError: 命令占位执行写 stderr 失败时由底层输出函数透传。
    """

    try:
        args = parse_cli_args(argv)
        runner = COMMAND_RUNNERS.get(args.command_name)
        if runner is None:
            print(
                MISSING_RUNNER_DIAGNOSTIC_TEMPLATE.format(
                    command_name=args.command_name
                ),
                file=sys.stderr,
            )
            return EXIT_FAILURE
        return runner(args)
    except KeyboardInterrupt:
        return EXIT_KEYBOARD_INTERRUPT
    except SystemExit as exc:
        return _normalize_system_exit_code(exc)


def _normalize_system_exit_code(exc: SystemExit) -> int:
    """把 ``SystemExit`` 载荷收敛为整数退出码。

    :param exc: argparse 或下游代码抛出的 ``SystemExit``。
    :returns: 规范化后的进程退出码。
    :raises ValueError: 本函数不主动抛出；异常输入按失败退出码处理。
    """

    code = exc.code
    if code is None:
        return EXIT_SUCCESS
    if isinstance(code, int):
        return code
    return EXIT_FAILURE


__all__: tuple[str, ...] = ("COMMAND_RUNNERS", "CommandRunner", "main")
