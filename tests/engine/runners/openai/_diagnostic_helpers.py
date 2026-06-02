"""OpenAI runner 诊断测试通用 helper。"""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping

from dayu.contracts.json_value import JsonValue


def leaf_strings(value: JsonValue) -> Iterator[str]:
    """遍历 JSON 值中的字符串叶子。

    :param value: JSON 值。
    :returns: 字符串叶子迭代器。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, str):
        yield value
        return
    if isinstance(value, Mapping):
        for child_value in value.values():
            yield from leaf_strings(child_value)
        return
    if isinstance(value, list):
        for child_value in value:
            yield from leaf_strings(child_value)


def serialized_size(value: JsonValue) -> int:
    """计算 JSON 值序列化后的 UTF-8 字节数。

    :param value: JSON 值。
    :returns: 使用非 ASCII 转义关闭后的 JSON 字节数。
    :raises Exception: 不主动抛出异常。
    """

    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


__all__ = ["leaf_strings", "serialized_size"]
