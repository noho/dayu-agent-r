"""Host terminal summary payload 提取 helper。"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.errors import HostDurableError

_PAYLOAD_FIELD_CONTENT = "content"
_PAYLOAD_FIELD_FINAL_ANSWER = "final_answer"
_PAYLOAD_FIELD_SUMMARY = "summary"
_PAYLOAD_FIELD_SUMMARY_TEXT = "summary_text"


class PayloadSummaryTextPolicy(StrEnum):
    """assistant summary payload 文本字段读取策略。

    - ``STRICT_ALLOW_EMPTY``：字段存在但非文本时抛错，空文本可作为摘要。
    - ``STRICT_NON_EMPTY``：字段存在但非文本时抛错，空文本按缺失处理。
    - ``LENIENT_NON_EMPTY``：字段非文本或空文本均按缺失处理。
    """

    STRICT_ALLOW_EMPTY = "strict_allow_empty"
    STRICT_NON_EMPTY = "strict_non_empty"
    LENIENT_NON_EMPTY = "lenient_non_empty"


def assistant_summary_from_payload(
    payload: Mapping[str, JsonValue], *, text_policy: PayloadSummaryTextPolicy
) -> str | None:
    """从 terminal summary 或 ``RUN_SUCCEEDED`` payload 提取 assistant 摘要。

    :param payload: terminal summary 或 ``RUN_SUCCEEDED`` payload。
    :param text_policy: 文本字段读取策略。
    :returns: assistant 摘要；缺失时返回 ``None``。
    :raises HostDurableError: strict 策略下字段类型非法时抛出。
    """

    for field_name in (
        _PAYLOAD_FIELD_FINAL_ANSWER,
        _PAYLOAD_FIELD_CONTENT,
        _PAYLOAD_FIELD_SUMMARY_TEXT,
    ):
        value = _summary_text_field(
            payload, field_name=field_name, text_policy=text_policy
        )
        if value is not None:
            return value
    nested = payload.get(_PAYLOAD_FIELD_SUMMARY)
    if isinstance(nested, Mapping):
        return assistant_summary_from_payload(
            cast(Mapping[str, JsonValue], nested),
            text_policy=text_policy,
        )
    return None


def _summary_text_field(
    payload: Mapping[str, JsonValue],
    *,
    field_name: str,
    text_policy: PayloadSummaryTextPolicy,
) -> str | None:
    """按策略读取 assistant summary 候选文本字段。

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
        if text_policy is PayloadSummaryTextPolicy.LENIENT_NON_EMPTY:
            return None
        if text_policy is PayloadSummaryTextPolicy.STRICT_NON_EMPTY:
            raise HostDurableError(f"payload field {field_name} must be text")
        raise HostDurableError(f"{field_name} must be string")
    if text_policy is PayloadSummaryTextPolicy.STRICT_ALLOW_EMPTY:
        return value
    if value.strip() == "":
        return None
    return value


__all__ = [
    "PayloadSummaryTextPolicy",
    "assistant_summary_from_payload",
]
