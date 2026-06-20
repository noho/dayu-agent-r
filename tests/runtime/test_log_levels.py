"""``dayu.runtime.log_levels`` 纯常量模块测试。

覆盖公共日志级别真源本身不执行 stdlib logging 注册，避免 Engine / Host
导入常量时意外带入日志装配副作用。
"""

from __future__ import annotations

import logging
import subprocess
import sys

from dayu.runtime.log_levels import (
    CRITICAL_LOG_LEVEL,
    DEBUG_LOG_LEVEL,
    ERROR_LOG_LEVEL,
    INFO_LOG_LEVEL,
    STREAM_DEBUG_LOG_LEVEL,
    VERBOSE_LOG_LEVEL,
    WARN_LOG_LEVEL,
)


def test_standard_log_level_constants_match_stdlib() -> None:
    """标准日志级别常量必须沿用 stdlib logging 真源。

    :returns: 无返回值。
    :raises AssertionError: 任一标准级别常量偏离 stdlib logging 时抛出。
    """

    assert DEBUG_LOG_LEVEL == logging.DEBUG
    assert INFO_LOG_LEVEL == logging.INFO
    assert WARN_LOG_LEVEL == logging.WARNING
    assert ERROR_LOG_LEVEL == logging.ERROR
    assert CRITICAL_LOG_LEVEL == logging.CRITICAL


def test_verbose_log_level_constant_is_stable() -> None:
    """公共 VERBOSE 常量应表达当前唯一真源数值。

    :returns: 无返回值。
    :raises AssertionError: 常量数值偏离当前日志契约时抛出。
    """

    assert VERBOSE_LOG_LEVEL == 15


def test_stream_debug_log_level_constant_is_below_debug() -> None:
    """STREAM_DEBUG 常量必须低于 stdlib DEBUG 以便被普通 DEBUG 阈值抑制。

    :returns: 无返回值。
    :raises AssertionError: 常量数值偏离当前日志契约时抛出。
    """

    assert STREAM_DEBUG_LOG_LEVEL == DEBUG_LOG_LEVEL - 1
    assert STREAM_DEBUG_LOG_LEVEL < logging.DEBUG


def test_importing_log_levels_does_not_register_stdlib_level() -> None:
    """只导入常量模块不应注册 stdlib logging level。

    :returns: 无返回值。
    :raises AssertionError: 常量模块导入产生 stdlib level 注册副作用时抛出。
    :raises subprocess.CalledProcessError: 隔离子进程执行失败时抛出。
    """

    code = (
        "import logging\n"
        "from dayu.runtime.log_levels import STREAM_DEBUG_LOG_LEVEL, VERBOSE_LOG_LEVEL\n"
        "print(logging.getLevelName(STREAM_DEBUG_LOG_LEVEL))\n"
        "print(logging.getLevelName(VERBOSE_LOG_LEVEL))\n"
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.splitlines() == ["Level 9", "Level 15"]
