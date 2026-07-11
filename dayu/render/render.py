"""``dayu-render`` 公开命令入口。

当前代码库尚未提供可运行的 Markdown 渲染转换器。本模块只恢复已声明
公开入口的 import/help 行为，并在转换请求上给出用户可读的当前能力诊断。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Final

from dayu.runtime.argparse_exit import normalize_argparse_system_exit_code

EXIT_UNAVAILABLE: Final[int] = 1
RENDER_UNAVAILABLE_DIAGNOSTIC: Final[str] = (
    "dayu-render: 当前版本尚未提供 Markdown 到 HTML、Word 或 PDF 的转换实现；"
    "此入口目前仅支持 --help 和受控能力诊断。"
)


def main(argv: Sequence[str] | None = None) -> int:
    """运行 ``dayu-render`` 入口。

    :param argv: 不含程序名的命令行参数；为 ``None`` 时由 argparse 读取进程参数。
    :returns: 进程退出码；help 路径返回 0，当前不可用的转换请求返回非零。
    :raises OSError: 写入标准错误失败时由底层输出函数透传。
    """

    parser = _build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as exc:
        return normalize_argparse_system_exit_code(exc)

    print(RENDER_UNAVAILABLE_DIAGNOSTIC, file=sys.stderr)
    return EXIT_UNAVAILABLE


def _build_parser() -> argparse.ArgumentParser:
    """构建 ``dayu-render`` 参数解析器。

    :returns: 只描述当前 help/诊断行为的解析器。
    :raises Exception: 本函数不主动抛出异常。
    """

    parser = argparse.ArgumentParser(
        prog="dayu-render",
        description=(
            "Dayu Markdown 渲染公开入口。当前版本尚未提供真实转换实现，"
            "传入路径会返回当前能力诊断。"
        ),
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        help="Markdown 输入路径；当前仅用于识别转换请求并返回不可用诊断。",
    )
    parser.add_argument(
        "output_path",
        nargs="?",
        help="输出路径；当前仅用于识别转换请求并返回不可用诊断。",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
