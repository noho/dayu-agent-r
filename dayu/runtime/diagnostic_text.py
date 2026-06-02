"""层中立 diagnostic 文本脱敏与截断 primitive。

本模块只处理运行期诊断文本中的敏感值识别、敏感值字面替换和有界截断。
它不理解 Exception、Run、Attempt、Host diagnostic ref、Engine event、provider
payload、tool trace 或任何财报业务字段。
"""

from __future__ import annotations

import re
from typing import Final

_REDACTED_BEARER_PREFIX: Final[str] = "Bearer "
_BEARER_SECRET_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bBearer\s+([^\s,;]+)",
    re.IGNORECASE,
)
_ASSIGNED_SECRET_VALUE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"(?:api\s+key|api[_-]?key)\b\s*[:=]\s*"
    r"|(?:api\s+key|apikey)\b\s+"
    r"|(?:authorization|password|secret|token)\b\s*[:=]\s*"
    r")([^\s,;]+)",
    re.IGNORECASE,
)
_INVALID_MAX_CHARS_MESSAGE: Final[str] = "max_chars must be a positive integer"
_INVALID_SUFFIX_LENGTH_MESSAGE: Final[str] = (
    "truncated_suffix length must be smaller than max_chars"
)


def contains_sensitive_diagnostic_value(message: str) -> bool:
    """判断 diagnostic 文本是否包含可脱敏的敏感值。

    该函数只识别携带值的 Bearer token、API key、authorization、password、
    secret 与 token 赋值片段。普通诊断句中的 ``token`` 或 header 字样不会因为
    缺少赋值分隔符而命中。

    :param message: 待检查的 diagnostic 文本。
    :returns: 包含敏感值时返回 ``True``，否则返回 ``False``。
    :raises TypeError: 当调用方传入非字符串时，由 ``re`` 匹配过程抛出。
    """

    return (
        _BEARER_SECRET_PATTERN.search(message) is not None
        or _ASSIGNED_SECRET_VALUE_PATTERN.search(message) is not None
    )


def redact_sensitive_diagnostic_values(
    message: str, *, redaction_marker: str
) -> str:
    """替换 diagnostic 文本中的敏感值并保留非敏感上下文。

    ``redaction_marker`` 会按字面文本写入结果，不会被 ``re.sub`` 当作 group
    reference 或反斜杠转义解析。Bearer 片段统一输出为 ``Bearer `` 加 marker；
    赋值类片段保留原字段名前缀和分隔符，只替换 value。

    :param message: 待脱敏的 diagnostic 文本。
    :param redaction_marker: 用于替换敏感值的字面文本。
    :returns: 已替换敏感值后的文本；未命中敏感值时返回原文本内容。
    :raises TypeError: 当调用方传入非字符串时，由 ``re`` 替换过程抛出。
    """

    redacted_bearer = _BEARER_SECRET_PATTERN.sub(
        lambda _match: _REDACTED_BEARER_PREFIX + redaction_marker,
        message,
    )
    return _ASSIGNED_SECRET_VALUE_PATTERN.sub(
        lambda match: match.group(1) + redaction_marker,
        redacted_bearer,
    )


def truncate_diagnostic_text(
    message: str, *, max_chars: int, truncated_suffix: str
) -> str:
    """把 diagnostic 文本截断到指定最大字符数。

    当 ``len(message) <= max_chars`` 时函数原样返回 ``message``，包括空字符串和
    精确边界字符串。只有超限文本会被截断为正文前缀加 ``truncated_suffix``。

    :param message: 待截断的 diagnostic 文本。
    :param max_chars: 允许返回的最大字符数，必须为正整数。
    :param truncated_suffix: 截断发生时追加的后缀，长度必须小于 ``max_chars``。
    :returns: 原文本或长度正好不超过 ``max_chars`` 的截断文本。
    :raises ValueError: ``max_chars`` 非正，或后缀长度大于等于 ``max_chars``。
    """

    if max_chars <= 0:
        raise ValueError(_INVALID_MAX_CHARS_MESSAGE)
    if len(truncated_suffix) >= max_chars:
        raise ValueError(_INVALID_SUFFIX_LENGTH_MESSAGE)
    if len(message) <= max_chars:
        return message
    return message[: max_chars - len(truncated_suffix)] + truncated_suffix
