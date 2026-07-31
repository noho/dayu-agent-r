"""``python -m dayu.cli`` 入口。"""

from __future__ import annotations

import signal
from typing import Never

from dayu.cli.exit_codes import EXIT_KEYBOARD_INTERRUPT


def run_module() -> int:
    """在统一启动中断边界内加载并运行 CLI application。

    :returns: CLI 退出码。
    :raises Exception: 除 ``KeyboardInterrupt`` 外的 import 或 application
        异常原样向上透传。
    """

    try:
        from dayu.cli.main import main

        return main()
    except KeyboardInterrupt:
        return EXIT_KEYBOARD_INTERRUPT


def exit_module() -> Never:
    """运行 CLI 并以稳定的进程退出状态结束 console/module invocation。

    已确认键盘中断后，进程余下阶段不再拥有可取消的业务操作；此时屏蔽
    后续 ``SIGINT``，避免解释器 teardown 把 canonical 130 覆盖成原始
    signal return code。

    :returns: 本函数不返回。
    :raises SystemExit: 始终携带 ``run_module`` 的规范退出码结束进程。
    :raises OSError: 安装进程收尾 SIGINT handler 失败时抛出。
    :raises ValueError: 当前线程不允许安装 signal handler 时抛出。
    """

    exit_code = run_module()
    if exit_code == EXIT_KEYBOARD_INTERRUPT:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    exit_module()
