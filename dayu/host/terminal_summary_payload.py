"""Host assistant final answer continuity payload 提取 helper。"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.errors import HostDurableError

_PAYLOAD_FIELD_CONTENT = "content"
_PAYLOAD_FIELD_FINAL_ANSWER = "final_answer"


class PayloadTextReadPolicy(StrEnum):
    """assistant continuity payload 文本字段读取策略。

    - ``STRICT_NON_EMPTY``：字段存在但非文本时抛错，空文本按缺失处理。
    - ``LENIENT_NON_EMPTY``：字段非文本或空文本均按缺失处理。
    """

    STRICT_NON_EMPTY = "strict_non_empty"
    LENIENT_NON_EMPTY = "lenient_non_empty"


def assistant_final_answer_text_from_run_payload(
    payload: Mapping[str, JsonValue], *, text_policy: PayloadTextReadPolicy
) -> str | None:
    """从 ``RUN_SUCCEEDED`` payload 读取 assistant final answer。

    :param payload: ``RUN_SUCCEEDED`` payload。
    :param text_policy: 文本字段读取策略。
    :returns: 非空 ``final_answer``；缺失或空白时返回 ``None``。
    :raises HostDurableError: strict 策略下 ``final_answer`` 类型非法时抛出。
    """

    return _text_field(
        payload, field_name=_PAYLOAD_FIELD_FINAL_ANSWER, text_policy=text_policy
    )


def terminal_summary_content_text_from_payload(
    payload: Mapping[str, JsonValue], *, text_policy: PayloadTextReadPolicy
) -> str | None:
    """从 terminal summary artifact payload 读取 final answer content。

    :param payload: terminal summary artifact payload。
    :param text_policy: 文本字段读取策略。
    :returns: 非空 ``content``；缺失或空白时返回 ``None``。
    :raises HostDurableError: strict 策略下 ``content`` 类型非法时抛出。
    """

    return _text_field(
        payload, field_name=_PAYLOAD_FIELD_CONTENT, text_policy=text_policy
    )


def _text_field(
    payload: Mapping[str, JsonValue],
    *,
    field_name: str,
    text_policy: PayloadTextReadPolicy,
) -> str | None:
    """按策略读取允许的 assistant continuity 文本字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :param text_policy: 文本字段读取策略。
    :returns: 文本值或 ``None``。
    :raises HostDurableError: strict 策略下字段类型非法时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        if text_policy is PayloadTextReadPolicy.LENIENT_NON_EMPTY:
            return None
        raise HostDurableError(f"payload field {field_name} must be text")
    if value.strip() == "":
        return None
    return value


__all__ = [
    "PayloadTextReadPolicy",
    "assistant_final_answer_text_from_run_payload",
    "terminal_summary_content_text_from_payload",
]
