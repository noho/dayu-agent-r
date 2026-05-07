"""Host 内部文本呈现辅助函数。

本模块只承载 Host 内部 run input 与 conversation memory 投影共享的
文本裁剪规则，不是 public API，也不表达 Engine 协议或财报业务语义。
"""

from __future__ import annotations

_EMPTY_TEXT: str = ""
_TRUNCATED_SUFFIX: str = "...[已裁剪]"


def truncate_text(*, text: str, limit: int) -> str:
    """按字符数裁剪文本。

    :param text: 原始文本。
    :param limit: 最大保留字符数；小于或等于零时返回空文本。
    :returns: 未超限时返回原文本；超限时返回前 ``limit`` 个字符并追加裁剪后缀。
    :raises Exception: 不主动抛出异常。
    """

    if limit <= 0:
        return _EMPTY_TEXT
    if len(text) <= limit:
        return text
    return text[:limit] + _TRUNCATED_SUFFIX
