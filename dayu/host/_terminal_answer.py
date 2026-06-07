"""Host assistant final answer continuity resolver。"""

from __future__ import annotations

from collections.abc import Mapping

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.transaction import HostTransaction
from dayu.host.payload_resolution import sqlite_payload_object
from dayu.host.terminal_summary_payload import (
    PayloadTextReadPolicy,
    assistant_final_answer_text_from_run_payload,
    terminal_summary_content_text_from_payload,
)

_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST = "terminal_summary_digest"
_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF = "terminal_summary_ref"


def assistant_final_answer_continuity_text(
    transaction: HostTransaction,
    run_payload: Mapping[str, JsonValue],
    *,
    text_policy: PayloadTextReadPolicy,
) -> str | None:
    """读取 assistant final answer continuity 文本。

    读取顺序固定为 ``RUN_SUCCEEDED.final_answer``，再按
    ``terminal_summary_ref`` / ``terminal_summary_digest`` 读取并校验 terminal
    summary artifact，只接受 artifact payload 的 ``content``。裸
    ``RUN_SUCCEEDED.content``、``summary_text`` 或 nested ``summary`` 均不是
    assistant final answer 来源。

    :param transaction: 当前 Host durable transaction。
    :param run_payload: ``RUN_SUCCEEDED`` payload。
    :param text_policy: 文本字段读取策略。
    :returns: final answer continuity 文本；缺失时返回 ``None``。
    :raises HostDurableError: strict 策略下允许字段类型非法，或 terminal
        summary descriptor 损坏时抛出。
    """

    final_answer = assistant_final_answer_text_from_run_payload(
        run_payload,
        text_policy=text_policy,
    )
    if final_answer is not None:
        return final_answer
    terminal_summary_ref = _optional_descriptor_text(
        run_payload, field_name=_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF
    )
    terminal_summary_digest = _optional_descriptor_text(
        run_payload, field_name=_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST
    )
    if terminal_summary_ref is None or terminal_summary_digest is None:
        return None
    terminal_summary = sqlite_payload_object(
        transaction,
        payload_ref=terminal_summary_ref,
        payload_digest=terminal_summary_digest,
        payload_label="terminal summary",
    )
    return terminal_summary_content_text_from_payload(
        terminal_summary,
        text_policy=text_policy,
    )


def _optional_descriptor_text(
    payload: Mapping[str, JsonValue], *, field_name: str
) -> str | None:
    """读取可选 terminal summary descriptor 文本字段。

    :param payload: ``RUN_SUCCEEDED`` payload。
    :param field_name: descriptor 字段名。
    :returns: 非空 descriptor 文本；缺失或空白时返回 ``None``。
    :raises HostDurableError: 字段存在但非文本时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise HostDurableError(f"payload field {field_name} must be text")
    if value.strip() == "":
        return None
    return value


__all__ = [
    "assistant_final_answer_continuity_text",
]
