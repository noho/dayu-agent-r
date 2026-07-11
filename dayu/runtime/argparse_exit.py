"""argparse 退出码规范化的层中立运行时 helper。"""

from __future__ import annotations

from typing import Final

ARGPARSE_USAGE_ERROR_EXIT_CODE: Final[int] = 2


def normalize_argparse_system_exit_code(exc: SystemExit) -> int:
    """把 argparse 抛出的 ``SystemExit`` 规范化为整数退出码。

    :param exc: argparse 抛出的退出信号。
    :returns: 整数退出码；非整数 code 按 argparse usage error 处理。
    :raises Exception: 本函数不主动抛出异常。
    """

    if isinstance(exc.code, int):
        return exc.code
    return ARGPARSE_USAGE_ERROR_EXIT_CODE
