"""Fins 包内部日志适配器。

本模块提供迁移 OLD Fins 代码所需的极窄日志接口，避免把 OLD 顶层
``dayu.log`` 兼容路径重新引入当前仓库。
"""

from __future__ import annotations

import logging


class Log:
    """迁移 Fins 代码使用的日志门面。

    该类只保留 OLD Fins read/storage/processor 闭包实际使用的静态方法，
    并转发到标准库 logging。
    """

    @staticmethod
    def debug(message: str, *, module: str | None = None) -> None:
        """写入 debug 日志。

        Args:
            message: 日志正文。
            module: 可选模块标签。

        Returns:
            无。

        Raises:
            无。
        """

        _logger(module).debug(message)

    @staticmethod
    def verbose(message: str, *, module: str | None = None) -> None:
        """写入 verbose 日志。

        Args:
            message: 日志正文。
            module: 可选模块标签。

        Returns:
            无。

        Raises:
            无。
        """

        _logger(module).debug(message)

    @staticmethod
    def info(message: str, *, module: str | None = None) -> None:
        """写入 info 日志。

        Args:
            message: 日志正文。
            module: 可选模块标签。

        Returns:
            无。

        Raises:
            无。
        """

        _logger(module).info(message)

    @staticmethod
    def warning(message: str, *, module: str | None = None) -> None:
        """写入 warning 日志。

        Args:
            message: 日志正文。
            module: 可选模块标签。

        Returns:
            无。

        Raises:
            无。
        """

        _logger(module).warning(message)

    @staticmethod
    def warn(message: str, *, module: str | None = None) -> None:
        """写入 warning 日志。

        Args:
            message: 日志正文。
            module: 可选模块标签。

        Returns:
            无。

        Raises:
            无。
        """

        _logger(module).warning(message)

    @staticmethod
    def error(message: str, *, module: str | None = None) -> None:
        """写入 error 日志。

        Args:
            message: 日志正文。
            module: 可选模块标签。

        Returns:
            无。

        Raises:
            无。
        """

        _logger(module).error(message)


def _logger(module: str | None) -> logging.Logger:
    """返回 Fins 日志器。

    Args:
        module: 可选 OLD 模块标签。

    Returns:
        标准库日志器。

    Raises:
        无。
    """

    if module is None or module.strip() == "":
        return logging.getLogger("dayu.fins")
    return logging.getLogger(f"dayu.fins.{module}")
