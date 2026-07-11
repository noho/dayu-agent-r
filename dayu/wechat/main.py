"""``dayu-wechat`` 公开命令入口。

当前代码库尚未提供可运行的微信登录、前台 daemon 或后台 service 管理。
本模块只恢复已声明公开入口的 import/help 行为，并在非 help 执行时
给出用户可读的当前能力诊断。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Final

from dayu.runtime.argparse_exit import normalize_argparse_system_exit_code

COMMAND_LOGIN: Final[str] = "login"
COMMAND_RUN: Final[str] = "run"
COMMAND_SERVICE: Final[str] = "service"
SERVICE_COMMAND_INSTALL: Final[str] = "install"
SERVICE_COMMAND_START: Final[str] = "start"
SERVICE_COMMAND_RESTART: Final[str] = "restart"
SERVICE_COMMAND_STOP: Final[str] = "stop"
SERVICE_COMMAND_STATUS: Final[str] = "status"
SERVICE_COMMAND_LIST: Final[str] = "list"
SERVICE_COMMAND_UNINSTALL: Final[str] = "uninstall"
EXIT_UNAVAILABLE: Final[int] = 1
WECHAT_UNAVAILABLE_DIAGNOSTIC: Final[str] = (
    "dayu-wechat: 当前版本尚未提供可运行的微信登录、daemon 或后台 service；"
    "此入口目前仅支持 --help、子命令 --help 和受控能力诊断。"
)


def main(argv: Sequence[str] | None = None) -> int:
    """运行 ``dayu-wechat`` 入口。

    :param argv: 不含程序名的命令行参数；为 ``None`` 时由 argparse 读取进程参数。
    :returns: 进程退出码；help 路径返回 0，当前不可用的真实执行返回非零。
    :raises OSError: 写入标准错误失败时由底层输出函数透传。
    """

    parser = _build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as exc:
        return normalize_argparse_system_exit_code(exc)

    print(WECHAT_UNAVAILABLE_DIAGNOSTIC, file=sys.stderr)
    return EXIT_UNAVAILABLE


def _build_parser() -> argparse.ArgumentParser:
    """构建 ``dayu-wechat`` 参数解析器。

    :returns: 只描述当前 help/诊断行为的解析器。
    :raises Exception: 本函数不主动抛出异常。
    """

    parser = argparse.ArgumentParser(
        prog="dayu-wechat",
        description=(
            "Dayu WeChat 公开入口。当前版本尚未提供可运行的微信登录、"
            "daemon 或后台 service，仅支持帮助和当前能力诊断。"
        ),
    )
    subparsers = parser.add_subparsers(dest="command_name", metavar="command")

    login_parser = subparsers.add_parser(
        COMMAND_LOGIN,
        help="查看微信登录入口的当前不可用说明。",
        description="微信登录入口当前尚未实现；本命令仅提供帮助和诊断。",
    )
    login_parser.add_argument("--label", help="实例标签；当前仅用于帮助说明。")
    login_parser.add_argument(
        "--relogin",
        action="store_true",
        help="重新登录开关；当前仅用于帮助说明。",
    )

    run_parser = subparsers.add_parser(
        COMMAND_RUN,
        help="查看微信前台 daemon 入口的当前不可用说明。",
        description="微信前台 daemon 当前尚未实现；本命令仅提供帮助和诊断。",
    )
    run_parser.add_argument("--label", help="实例标签；当前仅用于帮助说明。")

    service_parser = subparsers.add_parser(
        COMMAND_SERVICE,
        help="查看微信后台 service 入口的当前不可用说明。",
        description="微信后台 service 当前尚未实现；本命令仅提供帮助和诊断。",
    )
    service_subparsers = service_parser.add_subparsers(
        dest="service_command_name",
        metavar="service-command",
    )
    for service_command in (
        SERVICE_COMMAND_INSTALL,
        SERVICE_COMMAND_START,
        SERVICE_COMMAND_RESTART,
        SERVICE_COMMAND_STOP,
        SERVICE_COMMAND_STATUS,
        SERVICE_COMMAND_LIST,
        SERVICE_COMMAND_UNINSTALL,
    ):
        service_subparsers.add_parser(
            service_command,
            help=f"查看 service {service_command} 的当前不可用说明。",
            description=(
                f"微信 service {service_command} 当前尚未实现；"
                "本命令仅提供帮助和诊断。"
            ),
        )

    return parser


if __name__ == "__main__":
    raise SystemExit(main())
