"""OpenAI-compatible usage 字段归一工具。

本模块只处理 provider 响应中的 ``usage`` 片段，把解析层看到的
JSON object 收敛为 Engine Runner 契约需要的三项整数 token 统计。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeGuard

from dayu.contracts.json_value import JsonValue

_PROMPT_TOKENS_FIELD: str = "prompt_tokens"
_COMPLETION_TOKENS_FIELD: str = "completion_tokens"
_TOTAL_TOKENS_FIELD: str = "total_tokens"


@dataclass(frozen=True, slots=True)
class UsageTokenCounts:
    """归一后的 token 统计。

    :param prompt_tokens: 输入 token 数。
    :param completion_tokens: 输出 token 数。
    :param total_tokens: 总 token 数。
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def _is_token_count(value: JsonValue | None) -> TypeGuard[int]:
    """判断 JSON 值是否为合法 token 计数。

    :param value: provider usage 字段中的单个值。
    :returns: 非 ``bool`` 且非负的 ``int`` 返回 ``True``；其它返回 ``False``。
    :raises Exception: 不主动抛出异常。
    """

    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def coerce_usage(usage: Mapping[str, JsonValue]) -> UsageTokenCounts | None:
    """把 provider usage object 归一为强类型 usage。

    :param usage: provider 返回的 usage JSON object。
    :returns: 三项 token 字段均为合法整数时返回归一 token 统计；
        任一字段缺失或类型错误时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    prompt_tokens = usage.get(_PROMPT_TOKENS_FIELD)
    completion_tokens = usage.get(_COMPLETION_TOKENS_FIELD)
    total_tokens = usage.get(_TOTAL_TOKENS_FIELD)
    if (
        not _is_token_count(prompt_tokens)
        or not _is_token_count(completion_tokens)
        or not _is_token_count(total_tokens)
    ):
        return None
    return UsageTokenCounts(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )


__all__ = ["UsageTokenCounts", "coerce_usage"]
