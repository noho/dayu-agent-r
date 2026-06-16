"""pytest 全局测试隔离夹具。"""

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Final

import pytest

_DAYU_LOGGER_NAME: Final[str] = "dayu"


@pytest.fixture(autouse=True)
def restore_dayu_namespace_logger() -> Generator[None, None, None]:
    """恢复每个测试前的 Dayu namespace logger 状态。

    CLI 测试会调用真实入口装配 ``dayu`` logger，并把 handler 绑定到当前
    pytest 捕获流。若该 handler 泄漏到下一个测试，捕获流关闭后会导致后续
    日志写入失败，或让 ``caplog`` 无法观察 ``dayu.*`` 记录。本夹具只恢复
    测试前已有的 logger 状态，不改变生产日志装配策略。

    :returns: pytest fixture generator。
    :raises Exception: 不主动抛出异常。
    """

    logger = logging.getLogger(_DAYU_LOGGER_NAME)
    original_handlers = tuple(logger.handlers)
    original_level = logger.level
    original_propagate = logger.propagate
    original_disabled = logger.disabled

    try:
        yield
    finally:
        current_handlers = tuple(logger.handlers)
        for handler in current_handlers:
            logger.removeHandler(handler)
            if handler not in original_handlers:
                handler.close()
        for handler in original_handlers:
            logger.addHandler(handler)
        logger.setLevel(original_level)
        logger.propagate = original_propagate
        logger.disabled = original_disabled
