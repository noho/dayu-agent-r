"""Host assistant final-answer continuity 文本解析器。

本模块解析 ``RUN_SUCCEEDED`` 的 assistant final-answer continuity 文本。解析顺序为：
先读取 inline ``final_answer``，缺失或空白时再通过 terminal artifact descriptor
读取并校验顶层 ``content``。artifact ``content`` 只是成功终态 continuity 的
fallback，不是失败诊断、取消原因、lost 诊断、compact session_summary、
answer anchor 或 evidence-backed fact 来源。

consumer 边界固定如下：compaction material 使用本 strict continuity resolver 并允许
digest-checked artifact fallback；Conversation Memory selected recent window 直接消费
inline ``final_answer`` 且保持 lenient；durable projection / run-input adapter 可以先把
descriptor-backed terminal artifact ``content`` hydrate 成 transient ``final_answer``，
再交给 memory consumer。本模块不负责文本截断，长度治理属于调用方的展示、存储或上下文
预算边界。
"""

from __future__ import annotations

from collections.abc import Mapping

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.transaction import HostTransaction
from dayu.host.payload_resolution import sqlite_payload_object
from dayu.host.terminal_payload import (
    PayloadTextReadPolicy,
    assistant_final_answer_text_from_run_payload,
    terminal_payload_content_text_from_payload,
)

_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST = "terminal_summary_digest"
_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF = "terminal_summary_ref"


def assistant_final_answer_continuity_text(
    transaction: HostTransaction,
    run_payload: Mapping[str, JsonValue],
    *,
    text_policy: PayloadTextReadPolicy,
) -> str | None:
    """读取 assistant final-answer continuity 文本。

    读取顺序固定为 ``RUN_SUCCEEDED.final_answer``，再按
    ``terminal_summary_ref`` / ``terminal_summary_digest`` 读取并校验 terminal
    artifact payload，只接受 artifact payload 的顶层 ``content``。裸
    ``RUN_SUCCEEDED.content``、``summary_text`` 或 nested ``summary`` 均不是
    assistant final-answer 来源。terminal artifact ``content`` 只在
    ``RUN_SUCCEEDED`` continuity 路径中作为 fallback；失败、取消和 lost 终态的
    diagnostic 文本不能通过本 resolver 变成 assistant final answer。本 resolver
    不截断过长文本。

    :param transaction: 当前 Host durable transaction。
    :param run_payload: ``RUN_SUCCEEDED`` payload。
    :param text_policy: 文本字段读取策略。
    :returns: final answer continuity 文本；缺失时返回 ``None``。
    :raises HostDurableError: strict 策略下允许字段类型非法，或 terminal
        artifact descriptor 损坏时抛出。
    """

    final_answer = assistant_final_answer_text_from_run_payload(
        run_payload,
        text_policy=text_policy,
    )
    if final_answer is not None:
        return final_answer
    terminal_payload_ref = _optional_descriptor_text(
        run_payload, field_name=_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF
    )
    terminal_payload_digest = _optional_descriptor_text(
        run_payload, field_name=_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST
    )
    if terminal_payload_ref is None or terminal_payload_digest is None:
        return None
    terminal_payload = sqlite_payload_object(
        transaction,
        payload_ref=terminal_payload_ref,
        payload_digest=terminal_payload_digest,
        payload_label="terminal payload",
    )
    return terminal_payload_content_text_from_payload(
        terminal_payload,
        text_policy=text_policy,
    )


def _optional_descriptor_text(
    payload: Mapping[str, JsonValue], *, field_name: str
) -> str | None:
    """读取可选 terminal artifact descriptor 文本字段。

    descriptor 只是 artifact 引用标签和 digest 校验材料，不是业务事实或 assistant
    final-answer 文本。字段缺失或空白代表没有可用 fallback descriptor。

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
