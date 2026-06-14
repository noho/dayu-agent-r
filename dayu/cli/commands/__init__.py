"""Dayu CLI 命令占位实现。

CLI-01-S1 只建立命令注册与分发骨架；真实 Host / Fins 命令执行会在后续
slice 中按 Service 边界补齐。
"""

from __future__ import annotations

import sys

from dayu.cli.arg_parsing import ParsedCliArgs
from dayu.cli.exit_codes import EXIT_NOT_IMPLEMENTED


def run_not_implemented_command(args: ParsedCliArgs) -> int:
    """返回当前 slice 的命令占位执行结果。

    :param args: 已解析的 CLI 参数。
    :returns: not-implemented 对应的退出码。
    :raises OSError: stderr 写入失败时由 ``print`` 透传。
    """

    print(
        f"dayu-cli {args.command_name}: 当前切片仅实现 parser/help 骨架，命令执行尚未实现。",
        file=sys.stderr,
    )
    return EXIT_NOT_IMPLEMENTED


__all__: tuple[str, ...] = ("run_not_implemented_command",)
