"""层中立运行时摘要 helper。

本模块只提供可被 runtime 多个组件复用的 JSON 规范化与 canonical
SHA-256 摘要能力，不依赖 Host / Engine / Service / UI / Fins 或业务模块。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Final

from dayu.contracts import JsonValue

_CONTENT_DIGEST_PREFIX: Final[str] = "sha256:"


def canonical_json_digest(value: JsonValue) -> str:
    """对 JSON 值计算 canonical SHA-256 摘要。

    :param value: 待摘要的 JSON 值。
    :returns: ``sha256:<hex>`` 形式的稳定摘要。
    :raises TypeError: JSON 值中包含无法序列化或非法类型的值时抛出。
    :raises ValueError: JSON 值中包含 NaN 或无穷浮点数时抛出。
    """

    normalized = normalize_json_value(value)
    payload = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return _CONTENT_DIGEST_PREFIX + hashlib.sha256(payload).hexdigest()


def text_digest(value: str) -> str:
    """对 UTF-8 文本计算 SHA-256 摘要。

    :param value: 待摘要的文本。
    :returns: ``sha256:<hex>`` 形式的稳定摘要。
    :raises Exception: 不主动抛出异常。
    """

    return _CONTENT_DIGEST_PREFIX + hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_json_value(value: JsonValue) -> JsonValue:
    """把 ``JsonValue`` 递归转换为 stdlib ``json`` 可稳定处理的结构。

    :param value: 待规范化的 JSON 值。
    :returns: 只包含 JSON 基本类型、``list`` 与 ``dict`` 的值。
    :raises TypeError: 输入不是合法 ``JsonValue`` 形态时抛出。
    """

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [normalize_json_value(item) for item in value]
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JsonValue object key must be str")
            result[key] = normalize_json_value(item)
        return result
    raise TypeError("JsonValue contains unsupported value")
