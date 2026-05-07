"""Host 内部 token 估算器。

本模块只服务 Host RunInputBuilder 与 context compact 的相对预算判断。
它不是 provider tokenizer，也不决定真实 context overflow 是否发生；真实
overflow 仍以 Engine / Runner 暴露的强类型事实为准。
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence

from dayu.engine import AgentMessage

TOKEN_ESTIMATOR_ALGORITHM_ID: str = "host_wide_narrow_units_v1"
"""Host 当前内部估算算法标识。"""

HALF_WIDTH_TOKEN_UNIT: int = 1
"""半角 / 窄字符估算 unit。"""

FULL_WIDTH_TOKEN_UNIT: int = 2
"""全角 / 宽字符估算 unit。"""

TOKEN_UNITS_PER_ESTIMATED_TOKEN: int = 2
"""估算 token 与 unit 的固定换算分母。"""

_WIDE_EAST_ASIAN_WIDTHS: frozenset[str] = frozenset({"F", "W"})


def estimate_text_token_units(text: str) -> int:
    """估算文本的 token unit 数。

    :param text: 待估算文本。
    :returns: token unit 数；空文本返回 ``0``。
    :raises Exception: 不主动抛出异常。
    """

    total = 0
    for char in text:
        if unicodedata.east_asian_width(char) in _WIDE_EAST_ASIAN_WIDTHS:
            total += FULL_WIDTH_TOKEN_UNIT
        else:
            total += HALF_WIDTH_TOKEN_UNIT
    return total


def token_units_to_estimated_tokens(token_units: int) -> int:
    """将 token unit 向上取整转换为估算 token。

    :param token_units: token unit 数。
    :returns: 估算 token 数；非正数返回 ``0``。
    :raises Exception: 不主动抛出异常。
    """

    if token_units <= 0:
        return 0
    return (
        token_units + TOKEN_UNITS_PER_ESTIMATED_TOKEN - 1
    ) // TOKEN_UNITS_PER_ESTIMATED_TOKEN


def estimate_text_tokens(text: str) -> int:
    """估算文本 token 数。

    :param text: 待估算文本。
    :returns: 估算 token 数。
    :raises Exception: 不主动抛出异常。
    """

    return token_units_to_estimated_tokens(estimate_text_token_units(text))


def estimate_messages_tokens(messages: Sequence[AgentMessage]) -> int:
    """估算消息序列 token 数。

    :param messages: Agent 消息序列。
    :returns: 所有消息正文合计的估算 token 数。
    :raises Exception: 不主动抛出异常。
    """

    return estimate_text_tokens(_messages_text(messages))


def estimate_messages_chars(messages: Sequence[AgentMessage]) -> int:
    """估算消息序列字符数。

    :param messages: Agent 消息序列。
    :returns: 所有消息正文合计字符数。
    :raises Exception: 不主动抛出异常。
    """

    return len(_messages_text(messages))


def _messages_text(messages: Sequence[AgentMessage]) -> str:
    """拼接消息正文用于 Host 内部估算。

    :param messages: Agent 消息序列。
    :returns: 拼接后的消息正文。
    :raises Exception: 不主动抛出异常。
    """

    return "\n".join(
        "" if message.content is None else message.content
        for message in messages
    )


__all__ = [
    "FULL_WIDTH_TOKEN_UNIT",
    "HALF_WIDTH_TOKEN_UNIT",
    "TOKEN_ESTIMATOR_ALGORITHM_ID",
    "TOKEN_UNITS_PER_ESTIMATED_TOKEN",
    "estimate_messages_chars",
    "estimate_messages_tokens",
    "estimate_text_token_units",
    "estimate_text_tokens",
    "token_units_to_estimated_tokens",
]
