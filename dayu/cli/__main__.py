"""``python -m dayu.cli`` 入口。"""

from __future__ import annotations

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


if __name__ == "__main__":
    raise SystemExit(run_module())
