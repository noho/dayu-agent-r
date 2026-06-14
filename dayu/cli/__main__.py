"""``python -m dayu.cli`` 入口。"""

from __future__ import annotations

from dayu.cli.main import main


def run_module() -> int:
    """运行模块形式的 CLI 入口。

    :returns: CLI 退出码。
    :raises OSError: 底层命令输出失败时透传。
    """

    return main()


if __name__ == "__main__":
    raise SystemExit(run_module())
