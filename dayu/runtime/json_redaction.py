"""层中立 JSON 敏感字段脱敏 helper。

本模块只根据 JSON object 字段名递归脱敏敏感值，用于把运行期 JSON 参数
投影成可进入诊断、日志或 LLM replay 的低风险结构。它不理解 Host 事件、
Engine 消息、工具 schema 或任何财报业务字段。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from dayu.contracts.json_value import JsonValue

JSON_REDACTION_MARKER: Final[str] = "<redacted>"
"""JSON 敏感字段统一脱敏标记。"""

_SENSITIVE_KEY_FRAGMENTS: Final[tuple[str, ...]] = (
    "api_key",
    "password",
    "secret",
    "token",
)


def redact_sensitive_json_fields(value: JsonValue) -> JsonValue:
    """递归脱敏 JSON 值中敏感字段名对应的字段值。

    该函数只在 object 字段名命中敏感片段时替换对应字段值；数组元素和非敏感
    object 字段会继续递归处理。字段名匹配会统一小写并把 ``-`` 规范化为
    ``_``，因此 ``api-key``、``api_key``、``password``、``secret`` 与
    ``token`` 等字段名均会命中。

    :param value: 待脱敏的 JSON 值。
    :returns: 脱敏后的 JSON 值；原值不会被就地修改。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, Mapping):
        return {
            key: JSON_REDACTION_MARKER if _is_sensitive_key(key) else redact_sensitive_json_fields(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_json_fields(item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    """判断 JSON object 字段名是否命中敏感片段。

    :param key: JSON object 字段名。
    :returns: 命中敏感片段时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    normalized = key.lower().replace("-", "_")
    return any(fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS)
