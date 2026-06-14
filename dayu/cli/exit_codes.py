"""Dayu CLI 退出码定义。

本模块只保存命令行入口使用的进程退出码常量，不承载命令执行逻辑。
"""

from __future__ import annotations

EXIT_SUCCESS: int = 0
EXIT_FAILURE: int = 1
EXIT_USAGE_ERROR: int = 2
EXIT_KEYBOARD_INTERRUPT: int = 130
EXIT_NOT_IMPLEMENTED: int = EXIT_FAILURE

__all__: tuple[str, ...] = (
    "EXIT_SUCCESS",
    "EXIT_FAILURE",
    "EXIT_USAGE_ERROR",
    "EXIT_KEYBOARD_INTERRUPT",
    "EXIT_NOT_IMPLEMENTED",
)
