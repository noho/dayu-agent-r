"""Fins read tools 使用的错误码枚举。"""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """Fins read tools 的稳定错误码。

    Attributes:
        NOT_FOUND: 资源不存在。
        INVALID_ARGUMENT: 参数校验失败。
        NOT_SUPPORTED: 当前处理器或文档不支持该操作。
    """

    NOT_FOUND = "not_found"
    INVALID_ARGUMENT = "invalid_argument"
    NOT_SUPPORTED = "not_supported"
