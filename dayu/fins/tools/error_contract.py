"""Fins read tools 使用的错误码枚举。"""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """Fins read tools 的稳定错误码。

    Attributes:
        NOT_FOUND: 资源不存在。
        INVALID_ARGUMENT: 参数校验失败。
        NOT_SUPPORTED: 当前处理器或文档不支持该操作。
        XBRL_QUERY_FAILED: 所有可执行 XBRL concept 查询均失败。
        SOURCE_DECODE_FAILED: source 无法被可靠读取或解码。
        SEARCH_INDEX_FAILED: 搜索索引或语义画像构建失败。
        SOURCE_CHANGED_DURING_READ: 读取期间 source revision 发生变化。
    """

    NOT_FOUND = "not_found"
    INVALID_ARGUMENT = "invalid_argument"
    NOT_SUPPORTED = "not_supported"
    XBRL_QUERY_FAILED = "xbrl_query_failed"
    SOURCE_DECODE_FAILED = "source_decode_failed"
    SEARCH_INDEX_FAILED = "search_index_failed"
    SOURCE_CHANGED_DURING_READ = "source_changed_during_read"
