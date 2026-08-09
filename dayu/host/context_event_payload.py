"""Context Governance accepted terminal 的 durable payload owner。

本模块把 ``context_events`` 拥有的完整 ``CONTEXT_COMPACTED`` contract 映射为
EventLog inline payload 或既有 payload descriptor/blob，并提供所有 Host consumer
共用的严格 resolver。它不产生 compact 业务语义，也不推进 Run / Attempt 状态。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from dayu.contracts.json_value import JsonValue
from dayu.host.context_events import (
    CONTEXT_COMPACTED,
    validate_context_compacted_payload,
)
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventClass, EventLogRow
from dayu.host.durable.payload import (
    BoundedJsonPayloadWriteRequest,
    PayloadStore,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.payload_resolution import event_payload_object

_CONTEXT_COMPACTED_PAYLOAD_MEDIA_TYPE = "application/vnd.dayu.context-compacted-terminal+json"
_CONTEXT_COMPACTED_PAYLOAD_REF_PREFIX = "context-compacted-terminal:"
_CONTEXT_COMPACTED_PAYLOAD_ID_PREFIX = "sqlite:context-compacted-terminal:"
_EMPTY_DESCRIPTOR_BACKED_EVENT_PAYLOAD: Mapping[str, JsonValue] = {}


@dataclass(frozen=True, slots=True)
class ContextCompactedPayloadStorage:
    """``CONTEXT_COMPACTED`` canonical payload 的 EventLog 存储计划。

    :param event_payload: EventLog ``payload_json``；inline 时为完整 canonical
        payload，descriptor-backed 时为空 object。
    :param payload_ref: 完整 canonical payload descriptor 引用；inline 时为
        ``None``。
    :param payload_digest: 完整 canonical payload digest；inline 时为 ``None``。
    """

    event_payload: Mapping[str, JsonValue]
    payload_ref: str | None
    payload_digest: str | None


def store_context_compacted_payload(
    transaction: HostTransaction,
    payload_store: PayloadStore,
    *,
    event_id: str,
    payload: Mapping[str, JsonValue],
) -> ContextCompactedPayloadStorage:
    """按 EventLog inline 阈值持久化 accepted compact terminal payload。

    小 payload 继续直接进入 EventLog；超限 payload 写入既有 bounded payload
    descriptor/blob 真源，EventLog 只保存 ref/digest 与空 hot object。调用方必须
    把返回的三个字段原样写入同一 ``CONTEXT_COMPACTED`` row。

    :param transaction: 当前 Host write transaction。
    :param payload_store: Host durable payload primitive。
    :param event_id: 即将写入的 ``CONTEXT_COMPACTED`` event id。
    :param payload: 已由 canonical builder 构造的完整 terminal payload。
    :returns: EventLog payload_json/ref/digest 存储计划。
    :raises TypeError: ``payload_store`` 类型非法时抛出。
    :raises ValueError: event id 或完整 payload contract 非法时抛出。
    :raises HostDurableError: descriptor/blob 写入或 identity 校验失败时抛出。
    """

    if not isinstance(payload_store, PayloadStore):
        raise TypeError("payload_store must be PayloadStore")
    if not isinstance(event_id, str) or event_id.strip() == "":
        raise ValueError("event_id must be non-empty text")
    validate_context_compacted_payload(payload)
    payload_size_bytes = len(canonical_json_dumps(payload).encode("utf-8"))
    if payload_size_bytes <= transaction.payload_inline_threshold_bytes:
        return ContextCompactedPayloadStorage(
            event_payload=payload,
            payload_ref=None,
            payload_digest=None,
        )
    payload_digest = sha256_digest_json(payload)
    descriptor = payload_store.write_bounded_json_payload(
        transaction,
        BoundedJsonPayloadWriteRequest(
            payload_ref=f"{_CONTEXT_COMPACTED_PAYLOAD_REF_PREFIX}{event_id}",
            sqlite_payload_id=f"{_CONTEXT_COMPACTED_PAYLOAD_ID_PREFIX}{event_id}",
            payload_json=payload,
            media_type=_CONTEXT_COMPACTED_PAYLOAD_MEDIA_TYPE,
            metadata={
                "event_type": CONTEXT_COMPACTED,
                "event_id": event_id,
            },
            expected_digest=payload_digest,
        ),
    )
    return ContextCompactedPayloadStorage(
        event_payload=_EMPTY_DESCRIPTOR_BACKED_EVENT_PAYLOAD,
        payload_ref=descriptor.payload_ref,
        payload_digest=descriptor.payload_digest,
    )


def resolve_context_compacted_payload(
    transaction: HostTransaction,
    event: EventLogRow,
) -> Mapping[str, JsonValue]:
    """从 inline 或 descriptor/blob 真源严格解析 accepted compact terminal。

    :param transaction: 当前 Host transaction。
    :param event: ``CONTEXT_COMPACTED`` canonical EventLog row。
    :returns: 完整且通过 canonical contract 校验的 terminal payload。
    :raises HostDurableError: event identity、ref/digest、descriptor、blob bytes、
        canonical JSON 或 terminal contract 任一非法时抛出。
    """

    if event.event_class is not EventClass.CANONICAL_FACT or event.event_type != CONTEXT_COMPACTED:
        raise HostDurableError("CONTEXT_COMPACTED event identity is invalid")
    if (event.payload_ref is None) != (event.payload_digest is None):
        raise HostDurableError("CONTEXT_COMPACTED payload ref/digest must pair")
    payload = event_payload_object(
        transaction,
        event,
        payload_label=CONTEXT_COMPACTED,
    )
    try:
        validate_context_compacted_payload(payload)
    except (TypeError, ValueError) as exc:
        raise HostDurableError("CONTEXT_COMPACTED payload is invalid") from exc
    return payload


__all__ = [
    "ContextCompactedPayloadStorage",
    "resolve_context_compacted_payload",
    "store_context_compacted_payload",
]
