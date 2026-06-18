"""Dayu CLI 进程入口。

本模块负责参数解析、命令分发和顶层退出码映射。具体业务流程由各命令模块
通过 Service 边界执行；本模块不直接编排 Host、Engine 或 Fins runtime。
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from typing import TextIO

from dayu.cli.arg_parsing import (
    CLI_COMMAND_NAMES,
    COMMAND_DOWNLOAD,
    COMMAND_INIT,
    COMMAND_INTERACTIVE,
    COMMAND_PROCESS,
    COMMAND_PROCESS_FILING,
    COMMAND_PROCESS_MATERIAL,
    COMMAND_PROMPT,
    COMMAND_SESSION,
    COMMAND_UPLOAD_FILING,
    COMMAND_UPLOAD_FILINGS_FROM,
    COMMAND_UPLOAD_MATERIAL,
    ParsedCliArgs,
    parse_cli_args,
)
from dayu.cli.commands import run_not_implemented_command
from dayu.cli.commands.fins import run_fins_direct_command
from dayu.cli.commands.init import run_init_command
from dayu.cli.commands.interactive import run_interactive_command
from dayu.cli.commands.prompt import run_prompt_command
from dayu.cli.commands.session import run_session_command
from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
)
import dayu.runtime.log as runtime_log

CommandRunner = Callable[[ParsedCliArgs], int]
MISSING_RUNNER_DIAGNOSTIC_TEMPLATE: str = (
    "dayu-cli: 内部错误：命令 '{command_name}' 缺少注册 runner。"
)
LOG_FILE_EMPTY_DIAGNOSTIC: str = "dayu-cli: --log-file: path must not be empty."
LOG_FILE_OPEN_FAILED_TEMPLATE: str = "dayu-cli: --log-file: cannot open '{path}': {error}"
AUTO_LOG_FILE_OPEN_FAILED_TEMPLATE: str = (
    "dayu-cli: cannot create default temporary log file: {error}"
)
AUTO_LOG_FILE_PREFIX: str = "dayu-cli-"
AUTO_LOG_FILE_SUFFIX: str = ".log"

COMMAND_RUNNERS: dict[str, CommandRunner] = {
    command_name: run_not_implemented_command for command_name in CLI_COMMAND_NAMES
}
COMMAND_RUNNERS[COMMAND_INIT] = run_init_command
COMMAND_RUNNERS[COMMAND_INTERACTIVE] = run_interactive_command
COMMAND_RUNNERS[COMMAND_PROMPT] = run_prompt_command
COMMAND_RUNNERS[COMMAND_DOWNLOAD] = run_fins_direct_command
COMMAND_RUNNERS[COMMAND_UPLOAD_FILING] = run_fins_direct_command
COMMAND_RUNNERS[COMMAND_UPLOAD_MATERIAL] = run_fins_direct_command
COMMAND_RUNNERS[COMMAND_UPLOAD_FILINGS_FROM] = run_fins_direct_command
COMMAND_RUNNERS[COMMAND_PROCESS] = run_fins_direct_command
COMMAND_RUNNERS[COMMAND_PROCESS_FILING] = run_fins_direct_command
COMMAND_RUNNERS[COMMAND_PROCESS_MATERIAL] = run_fins_direct_command
COMMAND_RUNNERS[COMMAND_SESSION] = run_session_command


def main(argv: Sequence[str] | None = None) -> int:
    """运行 Dayu CLI 入口。

    :param argv: 不含程序名的命令行参数；为 ``None`` 时使用进程参数。
    :returns: 进程退出码。
    :raises OSError: 命令占位执行写 stderr 失败时由底层输出函数透传。
    """

    opened_log_stream: TextIO | None = None
    log_level_for_cleanup: str | None = None
    try:
        try:
            args = parse_cli_args(argv)
            log_level_for_cleanup = args.log_level
            if args.log_file is not None:
                opened_log_stream = _open_log_file(args.log_file)
                if opened_log_stream is None:
                    return EXIT_USAGE_ERROR
            else:
                opened_log_stream = _open_default_log_file()
                if opened_log_stream is None:
                    return EXIT_FAILURE
            log_stream = opened_log_stream
            runtime_log.set_level_from_flags(
                log_level=args.log_level,
                debug=False,
                verbose=False,
                info=False,
                quiet=False,
                stream=log_stream,
            )
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
        finally:
            if opened_log_stream is not None:
                try:
                    runtime_log.set_level_from_flags(
                        log_level=log_level_for_cleanup,
                        debug=False,
                        verbose=False,
                        info=False,
                        quiet=False,
                        stream=sys.stderr,
                    )
                finally:
                    opened_log_stream.close()
    except KeyboardInterrupt:
        return EXIT_KEYBOARD_INTERRUPT
    except SystemExit as exc:
        return _normalize_system_exit_code(exc)


def _open_log_file(log_file: str) -> TextIO | None:
    """打开 CLI 诊断日志文件。

    :param log_file: 用户传入的日志文件路径。
    :returns: 已打开的文本写入流；输入非法或打开失败时返回 ``None``。
    :raises Exception: 本函数不主动抛出文件打开异常；打开失败通过
        usage diagnostic 与 ``None`` 返回值表达。
    """

    log_file_path = log_file.strip()
    if log_file_path == "":
        print(LOG_FILE_EMPTY_DIAGNOSTIC, file=sys.stderr)
        return None
    try:
        return open(log_file_path, mode="a", encoding="utf-8")
    except OSError as exc:
        print(
            LOG_FILE_OPEN_FAILED_TEMPLATE.format(path=log_file_path, error=exc),
            file=sys.stderr,
        )
        return None


def _open_default_log_file() -> TextIO | None:
    """打开默认 CLI 诊断日志临时文件。

    :returns: 已打开的文本写入流；临时文件创建失败时返回 ``None``。
    :raises Exception: 本函数不主动抛出文件创建异常；创建失败通过
        diagnostic 与 ``None`` 返回值表达。
    """

    try:
        file_descriptor, log_file_path = tempfile.mkstemp(
            prefix=AUTO_LOG_FILE_PREFIX,
            suffix=AUTO_LOG_FILE_SUFFIX,
        )
        os.close(file_descriptor)
        return open(log_file_path, mode="a", encoding="utf-8")
    except OSError as exc:
        print(AUTO_LOG_FILE_OPEN_FAILED_TEMPLATE.format(error=exc), file=sys.stderr)
        return None


def _normalize_system_exit_code(exc: SystemExit) -> int:
    """把 ``SystemExit`` 载荷收敛为整数退出码。

    :param exc: argparse 或下游代码抛出的 ``SystemExit``。
    :returns: 规范化后的进程退出码。
    :raises Exception: 本函数不主动抛出异常；非整数载荷按失败退出码处理。
    """

    code = exc.code
    if code is None:
        return EXIT_SUCCESS
    if isinstance(code, int):
        return code
    return EXIT_FAILURE


__all__: tuple[str, ...] = ("COMMAND_RUNNERS", "CommandRunner", "main")
