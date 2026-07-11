"""``dayu-web`` 公开命令入口。

当前代码库尚未提供可运行的 Web UI。本模块只恢复已声明公开入口的
import/help 行为，并在非 help 执行时给出用户可读的当前能力诊断。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Final

from dayu.runtime.argparse_exit import normalize_argparse_system_exit_code

EXIT_SUCCESS: Final[int] = 0
EXIT_UNAVAILABLE: Final[int] = 1
WEB_UNAVAILABLE_DIAGNOSTIC: Final[str] = (
    "dayu-web: 当前版本尚未提供可运行的 Web UI；"
    "此入口目前仅支持 --help 和受控能力诊断。"
)


def main(argv: Sequence[str] | None = None) -> int:
    """运行 ``dayu-web`` 入口。

    :param argv: 不含程序名的命令行参数；为 ``None`` 时由 argparse 读取进程参数。
    :returns: 进程退出码；``--help`` 返回 0，当前不可用的真实执行返回非零。
    :raises OSError: 写入标准错误失败时由底层输出函数透传。
    """

    parser = _build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as exc:
        return normalize_argparse_system_exit_code(exc)

    print(WEB_UNAVAILABLE_DIAGNOSTIC, file=sys.stderr)
    return EXIT_UNAVAILABLE


def _build_parser() -> argparse.ArgumentParser:
    """构建 ``dayu-web`` 参数解析器。

    :returns: 只描述当前已实现 help/诊断行为的解析器。
    :raises Exception: 本函数不主动抛出异常。
    """

    return argparse.ArgumentParser(
        prog="dayu-web",
        description=(
            "Dayu Web 公开入口。当前版本尚未提供可运行的 Web UI，"
            "仅支持查看帮助和返回当前能力诊断。"
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
