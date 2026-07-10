"""Host assistant final-answer continuity 文本解析器。

本模块解析 ``RUN_SUCCEEDED`` 的 assistant final-answer continuity 文本。解析顺序为：
先读取 inline ``final_answer``，缺失或空白时再通过 terminal artifact descriptor
读取并校验顶层 ``content``。artifact ``content`` 只是成功终态 continuity 的
fallback，不是失败诊断、取消原因、lost 诊断、compact session_summary、
answer anchor 或 evidence-backed fact 来源。

consumer 边界固定如下：HostEvent 与 Outbox 使用 required strict contract；compaction
material 使用 optional strict contract 并允许 digest-checked artifact fallback；durable
projection / RunInputBuilder 把 resolver 输出作为 projection-internal typed continuity
material 传给 memory consumer，不修改 EventLog payload mapping；直接 Conversation Memory
consumer 在缺少 typed material 时只消费 inline ``final_answer`` 并保持 lenient、
descriptor-blind。本模块不负责文本截断，长度治理属于调用方的展示、存储或上下文预算边界。
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
    optional contract 允许完整缺失 answer source、descriptor ``content`` 缺失或空白时
    返回 ``None``。descriptor pair、descriptor、digest、SQLite row 与 JSON 结构始终
    strict fail closed；lenient 策略只影响 inline ``final_answer`` 字段。

    :returns: final answer continuity 文本；允许省略的内容缺失时返回 ``None``。
    :raises HostDurableError: strict inline 字段类型非法、descriptor pair 损坏，或
        terminal artifact 完整性 / ``content`` 类型非法时抛出。
    """

    final_answer, _missing_error = _resolve_assistant_final_answer_continuity_text(
        transaction,
        run_payload,
        inline_text_policy=text_policy,
    )
    return final_answer


def required_assistant_final_answer_continuity_text(
    transaction: HostTransaction,
    run_payload: Mapping[str, JsonValue],
) -> str:
    """读取成功 public terminal 必需的 assistant final answer 文本。

    本 contract 与 optional resolver 共用同一个 source-selection core，并固定使用
    strict inline policy。inline answer 与 descriptor source 都缺失，或 descriptor
    ``content`` 缺失 / 空白时均抛出可诊断的 durable error，保证成功 HostEvent 与
    Outbox materialization 不产生 nullable final answer。

    :param transaction: 当前 Host durable transaction。
    :param run_payload: ``RUN_SUCCEEDED`` payload。
    :returns: 非空 final answer continuity 文本。
    :raises HostDurableError: 没有合法 answer source，或 descriptor / content 非法时抛出。
    """

    final_answer, missing_error = _resolve_assistant_final_answer_continuity_text(
        transaction,
        run_payload,
        inline_text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
    )
    if final_answer is None:
        if missing_error is None:
            raise HostDurableError("assistant final answer resolution is invalid")
        raise HostDurableError(missing_error)
    return final_answer


def _resolve_assistant_final_answer_continuity_text(
    transaction: HostTransaction,
    run_payload: Mapping[str, JsonValue],
    *,
    inline_text_policy: PayloadTextReadPolicy,
) -> tuple[str | None, str | None]:
    """统一选择 inline 或 descriptor-backed final answer source。

    返回值第二项只在没有文本 candidate 时携带 required contract 应使用的稳定诊断；
    descriptor 结构或内容类型损坏直接抛错，不降级为缺失。

    :param transaction: 当前 Host durable transaction。
    :param run_payload: ``RUN_SUCCEEDED`` payload。
    :param inline_text_policy: inline ``final_answer`` 字段读取策略。
    :returns: ``(answer_text, missing_error)``；有文本时错误为 ``None``。
    :raises HostDurableError: descriptor pair、artifact 完整性或 content 类型非法时抛出。
    """

    final_answer = assistant_final_answer_text_from_run_payload(
        run_payload,
        text_policy=inline_text_policy,
    )
    if final_answer is not None:
        return final_answer, None
    terminal_payload_ref = _optional_descriptor_text(
        run_payload, field_name=_PAYLOAD_FIELD_TERMINAL_SUMMARY_REF
    )
    terminal_payload_digest = _optional_descriptor_text(
        run_payload, field_name=_PAYLOAD_FIELD_TERMINAL_SUMMARY_DIGEST
    )
    if terminal_payload_ref is None and terminal_payload_digest is None:
        return (
            None,
            "assistant final answer inline answer and descriptor pair are missing",
        )
    if terminal_payload_ref is None or terminal_payload_digest is None:
        raise HostDurableError(
            "terminal_summary_ref and terminal_summary_digest must pair"
        )
    terminal_payload = sqlite_payload_object(
        transaction,
        payload_ref=terminal_payload_ref,
        payload_digest=terminal_payload_digest,
        payload_label="terminal payload",
    )
    content = terminal_payload_content_text_from_payload(
        terminal_payload,
        text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
    )
    if content is not None:
        return content, None
    raw_content = terminal_payload.get("content")
    if raw_content is None:
        return None, "terminal payload content is missing"
    return None, "terminal payload content is blank"


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
    "required_assistant_final_answer_continuity_text",
]
