"""Host terminal payload 文本源选择 helper。

本模块只负责从已经允许作为 assistant final answer continuity 的 payload
字段中读取非空文本，不负责截断、预算控制或展示格式化。terminal payload
artifact 的顶层 ``content`` 只是在 ``RUN_SUCCEEDED`` continuity 路径中，
由上层 descriptor 校验后使用的 fallback 文本源；它不是 compact
session_summary、answer anchor 或 evidence-backed fact 来源。
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.errors import HostDurableError

_PAYLOAD_FIELD_CONTENT = "content"
_PAYLOAD_FIELD_FINAL_ANSWER = "final_answer"


class PayloadTextReadPolicy(StrEnum):
    """assistant final-answer continuity payload 文本字段读取策略。

    - ``STRICT_NON_EMPTY``：字段存在但非文本时抛错，空文本按缺失处理。
    - ``LENIENT_NON_EMPTY``：字段非文本或空文本均按缺失处理。
    """

    STRICT_NON_EMPTY = "strict_non_empty"
    LENIENT_NON_EMPTY = "lenient_non_empty"


def assistant_final_answer_text_from_run_payload(
    payload: Mapping[str, JsonValue], *, text_policy: PayloadTextReadPolicy
) -> str | None:
    """从 ``RUN_SUCCEEDED`` payload 读取 assistant final-answer continuity 文本。

    仅 ``final_answer`` 字段可作为 inline assistant final answer。裸
    ``content``、``summary_text`` 或 nested ``summary`` 不在本 helper 的读取范围内。
    本 helper 不截断过长文本，调用方应在自身展示、存储或上下文预算边界处理长度。

    :param payload: ``RUN_SUCCEEDED`` payload。
    :param text_policy: 文本字段读取策略。
    :returns: 非空 ``final_answer``；缺失或空白时返回 ``None``。
    :raises HostDurableError: strict 策略下 ``final_answer`` 类型非法时抛出。
    """

    return _text_field(
        payload, field_name=_PAYLOAD_FIELD_FINAL_ANSWER, text_policy=text_policy
    )


def terminal_payload_content_text_from_payload(
    payload: Mapping[str, JsonValue], *, text_policy: PayloadTextReadPolicy
) -> str | None:
    """从 terminal payload artifact 读取 continuity fallback ``content``。

    该 ``content`` 只供 ``RUN_SUCCEEDED`` 的 assistant final-answer continuity
    fallback 使用，前提是调用方已经通过 terminal payload descriptor 完成 artifact
    定位与 digest 校验。它不是失败、取消或 lost 终态的 assistant final answer，
    也不会被本 helper 升级为 compact fact。本 helper 不执行过长文本截断。

    :param payload: terminal payload artifact。
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
    """按策略读取允许的 assistant final-answer continuity 文本字段。

    本 helper 只处理字段存在性、文本类型和空白文本判断；不会读取未授权字段，也不做
    截断或 budget 适配。

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
    "terminal_payload_content_text_from_payload",
]
