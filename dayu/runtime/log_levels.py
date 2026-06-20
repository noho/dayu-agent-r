"""Dayu 层中立日志 level 整数常量真源。

本模块只承载多层共享的 stdlib logging level 整数值与 Dayu 自定义
``VERBOSE`` 与 ``STREAM_DEBUG`` 级别整数值，不注册 level name、不安装
handler、不读取配置。
Engine / Host 可导入这些整数常量来发出日志；具体 stdlib level name
注册由 ``dayu.runtime.log`` 负责。
"""

from __future__ import annotations

import logging
from typing import Final

DEBUG_LOG_LEVEL: Final[int] = logging.DEBUG
STREAM_DEBUG_LOG_LEVEL: Final[int] = DEBUG_LOG_LEVEL - 1
VERBOSE_LOG_LEVEL: Final[int] = 15
INFO_LOG_LEVEL: Final[int] = logging.INFO
WARN_LOG_LEVEL: Final[int] = logging.WARNING
ERROR_LOG_LEVEL: Final[int] = logging.ERROR
CRITICAL_LOG_LEVEL: Final[int] = logging.CRITICAL

__all__ = [
    "CRITICAL_LOG_LEVEL",
    "DEBUG_LOG_LEVEL",
    "ERROR_LOG_LEVEL",
    "INFO_LOG_LEVEL",
    "STREAM_DEBUG_LOG_LEVEL",
    "VERBOSE_LOG_LEVEL",
    "WARN_LOG_LEVEL",
]
