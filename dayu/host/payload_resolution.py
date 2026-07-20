"""Host EventLog payload 引用解析 helper。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventLogRow
from dayu.host.durable.payload import read_payload_descriptor
from dayu.host.durable.payload_resolution import resolve_json_payload
from dayu.host.durable.schema import (
    PayloadDescriptorKind,
    TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
    TOOL_CALL_ARGUMENTS_STORAGE_PAYLOAD_DESCRIPTOR,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_ABSENT,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_PAYLOAD_DESCRIPTOR,
    parse_payload_descriptor_kind,
)
from dayu.host.durable.transaction import HostTransaction

_FIELD_DESCRIPTOR_KIND = "descriptor_kind"
_FIELD_ARGUMENTS = "arguments"
_FIELD_SEMANTIC_QUERY_TEXT = "semantic_query_text"


@dataclass(frozen=True, slots=True)
class ToolCallRequestAtoms:
    """持久化 ``TOOL_CALL_REQUESTED`` accepted request atoms。

    :param tool_call_id: 工具调用 id。
    :param tool_name: 工具名。
    :param arguments_json: Host 已接受的 exact canonical 参数 JSON。
    :param normalized_arguments_digest: 参数 canonical digest。
    :param arguments_payload_digest: exact canonical 参数 JSON digest。
    :param semantic_input_digest: Host accept semantic input digest。
    :param semantic_query_text: 可选业务可读 semantic query。
    :param semantic_query_digest: semantic query digest；缺失时为 ``None``。
    """

    tool_call_id: str
    tool_name: str
    arguments_json: Mapping[str, JsonValue]
    normalized_arguments_digest: str
    arguments_payload_digest: str
    semantic_input_digest: str
    semantic_query_text: str | None
    semantic_query_digest: str | None


def event_payload_object(
    transaction: HostTransaction, event: EventLogRow, *, payload_label: str
) -> Mapping[str, JsonValue]:
    """读取 EventLog payload object，必要时跟随 SQLite payload descriptor。

    :param transaction: 当前 Host transaction。
    :param event: EventLog row。
    :param payload_label: 错误消息中的 payload 名称。
    :returns: payload JSON object。
    :raises HostDurableError: inline JSON、descriptor、digest 或 SQLite payload 非法时抛出。
    """

    if event.payload_ref is None:
        return _json_object(event.payload_json, payload_label=payload_label)
    if event.payload_digest is None:
        raise HostDurableError(f"{payload_label} payload digest is missing")
    return sqlite_payload_object(
        transaction,
        payload_ref=event.payload_ref,
        payload_digest=event.payload_digest,
        payload_label=payload_label,
    )


def event_payload_object_for_result_ref(
    transaction: HostTransaction,
    event: EventLogRow,
    *,
    expected_payload_ref: str | None,
    expected_payload_digest: str | None,
    payload_label: str,
) -> Mapping[str, JsonValue]:
    """按 accepted result ref 读取 EventLog payload object。

    :param transaction: 当前 Host transaction。
    :param event: EventLog row。
    :param expected_payload_ref: accepted envelope 中声明的 payload descriptor ref。
    :param expected_payload_digest: accepted envelope 中声明的 payload digest。
    :param payload_label: 错误消息中的 payload 名称。
    :returns: payload JSON object。
    :raises HostDurableError: EventLog payload ref / digest 与 accepted result ref
        不一致，或 payload descriptor / JSON 非法时抛出。
    """

    if event.payload_ref != expected_payload_ref:
        raise HostDurableError(f"{payload_label} payload ref mismatch")
    if event.payload_ref is not None and expected_payload_digest is not None:
        if event.payload_digest != expected_payload_digest:
            raise HostDurableError(f"{payload_label} payload digest mismatch")
    return event_payload_object(
        transaction,
        event,
        payload_label=payload_label,
    )


def tool_call_request_atoms(
    transaction: HostTransaction, event: EventLogRow
) -> ToolCallRequestAtoms:
    """读取并校验 ``TOOL_CALL_REQUESTED`` accepted request atoms。

    :param transaction: 当前 Host transaction。
    :param event: ``TOOL_CALL_REQUESTED`` canonical EventLog row。
    :returns: 解析后的 accepted request atoms。
    :raises HostDurableError: event type、storage kind、descriptor kind、digest 或
        payload body 不一致时抛出。
    """

    if event.event_type != "TOOL_CALL_REQUESTED":
        raise HostDurableError("tool call request atom event type mismatch")
    payload = event_payload_object(
        transaction,
        event,
        payload_label="tool call request",
    )
    tool_call_id = _required_text(payload, "tool_call_id")
    tool_name = _required_text(payload, "tool_name")
    normalized_digest = _required_text(payload, "normalized_arguments_digest")
    arguments_payload_digest = _required_text(payload, "arguments_payload_digest")
    if arguments_payload_digest != normalized_digest:
        raise HostDurableError(
            "tool call arguments payload digest must match normalized digest"
        )
    arguments_json = _read_arguments_json(
        transaction,
        payload,
        expected_digest=arguments_payload_digest,
    )
    if sha256_digest_json(arguments_json) != arguments_payload_digest:
        raise HostDurableError("tool call arguments payload digest mismatch")
    semantic_query_text, semantic_query_digest = _read_semantic_query(
        transaction,
        payload,
    )
    return ToolCallRequestAtoms(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        arguments_json=arguments_json,
        normalized_arguments_digest=normalized_digest,
        arguments_payload_digest=arguments_payload_digest,
        semantic_input_digest=_required_text(payload, "semantic_input_digest"),
        semantic_query_text=semantic_query_text,
        semantic_query_digest=semantic_query_digest,
    )


def sqlite_payload_object(
    transaction: HostTransaction,
    *,
    payload_ref: str,
    payload_digest: str,
    payload_label: str,
) -> Mapping[str, JsonValue]:
    """按 payload descriptor 读取完整性已校验的 durable JSON object。

    :param transaction: 当前 Host transaction。
    :param payload_ref: payload descriptor ref。
    :param payload_digest: 调用方持有的 payload digest。
    :param payload_label: 错误消息中的 payload 名称。
    :returns: payload JSON object。
    :raises HostDurableError: descriptor、caller digest、row、artifact 或 canonical
        JSON bytes 任一不一致时抛出。
    """

    try:
        return resolve_json_payload(
            transaction,
            payload_ref=payload_ref,
            expected_digest=payload_digest,
        ).payload
    except HostDurableError as exc:
        raise HostDurableError(
            f"{payload_label} payload integrity validation failed: {exc}"
        ) from exc


def _json_object(payload_json: str, *, payload_label: str) -> Mapping[str, JsonValue]:
    """解析 JSON object payload。

    :param payload_json: canonical JSON 文本。
    :param payload_label: 错误消息中的 payload 名称。
    :returns: payload JSON object。
    :raises HostDurableError: JSON 不是 object 时抛出。
    """

    try:
        value = cast(JsonValue, json.loads(payload_json))
    except json.JSONDecodeError as exc:
        raise HostDurableError(f"{payload_label} payload JSON is invalid") from exc
    if not isinstance(value, Mapping):
        raise HostDurableError(f"{payload_label} payload JSON must be object")
    return cast(Mapping[str, JsonValue], value)


def _read_arguments_json(
    transaction: HostTransaction,
    payload: Mapping[str, JsonValue],
    *,
    expected_digest: str,
) -> Mapping[str, JsonValue]:
    """读取 accepted arguments canonical JSON。

    :param transaction: 当前 Host transaction。
    :param payload: ``TOOL_CALL_REQUESTED`` hot payload。
    :param expected_digest: 调用方声明的 arguments digest。
    :returns: accepted arguments canonical JSON object。
    :raises HostDurableError: storage kind、payload ref、descriptor 或 JSON 非法时抛出。
    """

    storage_kind = _required_text(payload, "arguments_storage_kind")
    if storage_kind == TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON:
        if payload.get("arguments_payload_ref") is not None:
            raise HostDurableError("inline tool call arguments must not carry payload ref")
        value = payload.get("arguments_inline_json")
        if not isinstance(value, Mapping):
            raise HostDurableError("tool call inline arguments must be object")
        arguments_json = cast(Mapping[str, JsonValue], value)
    elif storage_kind == TOOL_CALL_ARGUMENTS_STORAGE_PAYLOAD_DESCRIPTOR:
        if payload.get("arguments_inline_json") is not None:
            raise HostDurableError(
                "descriptor tool call arguments must not carry inline JSON"
            )
        payload_ref = _required_text(payload, "arguments_payload_ref")
        _validate_descriptor_kind(
            transaction,
            payload_ref=payload_ref,
            expected_kind=PayloadDescriptorKind.TOOL_CALL_ARGUMENTS_JSON,
            payload_label="tool call arguments",
        )
        arguments_json = sqlite_payload_object(
            transaction,
            payload_ref=payload_ref,
            payload_digest=expected_digest,
            payload_label="tool call arguments",
        )
    else:
        raise HostDurableError("tool call arguments storage kind is invalid")
    accepted_arguments = arguments_json.get(_FIELD_ARGUMENTS)
    if not isinstance(accepted_arguments, Mapping):
        raise HostDurableError("tool call arguments JSON arguments must be object")
    if _payload_size_bytes(arguments_json) != _required_int(
        payload, "arguments_json_size_bytes"
    ):
        raise HostDurableError("tool call arguments size mismatch")
    return arguments_json


def _read_semantic_query(
    transaction: HostTransaction,
    payload: Mapping[str, JsonValue],
) -> tuple[str | None, str | None]:
    """读取可选 semantic query atom。

    :param transaction: 当前 Host transaction。
    :param payload: ``TOOL_CALL_REQUESTED`` hot payload。
    :returns: ``(query_text, query_digest)``。
    :raises HostDurableError: storage kind、descriptor、digest 或 JSON 非法时抛出。
    """

    storage_kind = _required_text(payload, "semantic_query_storage_kind")
    if storage_kind == TOOL_CALL_SEMANTIC_QUERY_STORAGE_ABSENT:
        if payload.get("semantic_query_text") is not None:
            raise HostDurableError("absent semantic query must not carry text")
        if payload.get("semantic_query_payload_ref") is not None:
            raise HostDurableError("absent semantic query must not carry payload ref")
        if payload.get("semantic_query_digest") is not None:
            raise HostDurableError("absent semantic query must not carry digest")
        return None, None
    semantic_query_digest = _required_text(payload, "semantic_query_digest")
    if storage_kind == TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT:
        if payload.get("semantic_query_payload_ref") is not None:
            raise HostDurableError("inline semantic query must not carry payload ref")
        query_text = _required_text(payload, "semantic_query_text")
    elif storage_kind == TOOL_CALL_SEMANTIC_QUERY_STORAGE_PAYLOAD_DESCRIPTOR:
        if payload.get("semantic_query_text") is not None:
            raise HostDurableError(
                "descriptor semantic query must not carry inline text"
            )
        payload_ref = _required_text(payload, "semantic_query_payload_ref")
        _validate_descriptor_kind(
            transaction,
            payload_ref=payload_ref,
            expected_kind=PayloadDescriptorKind.TOOL_CALL_SEMANTIC_QUERY_TEXT,
            payload_label="tool call semantic query",
        )
        query_json = sqlite_payload_object(
            transaction,
            payload_ref=payload_ref,
            payload_digest=semantic_query_digest,
            payload_label="tool call semantic query",
        )
        query_text = _required_text(query_json, _FIELD_SEMANTIC_QUERY_TEXT)
    else:
        raise HostDurableError("tool call semantic query storage kind is invalid")
    if sha256_digest_json({_FIELD_SEMANTIC_QUERY_TEXT: query_text}) != semantic_query_digest:
        raise HostDurableError("tool call semantic query digest mismatch")
    return query_text, semantic_query_digest


def _validate_descriptor_kind(
    transaction: HostTransaction,
    *,
    payload_ref: str,
    expected_kind: PayloadDescriptorKind,
    payload_label: str,
) -> None:
    """校验 payload descriptor metadata 中的业务 descriptor kind。

    :param transaction: 当前 Host transaction。
    :param payload_ref: payload descriptor ref。
    :param expected_kind: 期望的业务 descriptor kind。
    :param payload_label: 错误消息中的 payload 名称。
    :returns: ``None``。
    :raises HostDurableError: descriptor 缺失、metadata 非法或 kind 不匹配时抛出。
    """

    descriptor = read_payload_descriptor(transaction, payload_ref)
    if descriptor is None:
        raise HostDurableError(f"{payload_label} payload descriptor is missing")
    expected_descriptor_kind = parse_payload_descriptor_kind(expected_kind)
    metadata = _json_object(
        descriptor.metadata_json,
        payload_label=f"{payload_label} descriptor metadata",
    )
    descriptor_kind = metadata.get(_FIELD_DESCRIPTOR_KIND)
    if not isinstance(descriptor_kind, str) or descriptor_kind.strip() == "":
        raise HostDurableError(f"{payload_label} descriptor kind is missing")
    actual_descriptor_kind = parse_payload_descriptor_kind(descriptor_kind)
    if actual_descriptor_kind is not expected_descriptor_kind:
        raise HostDurableError(f"{payload_label} descriptor kind mismatch")


def _required_text(payload: Mapping[str, JsonValue], field_name: str) -> str:
    """读取 JSON object 中的必填非空文本字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 文本值。
    :raises HostDurableError: 字段缺失或不是非空文本时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    raise HostDurableError(f"{field_name} must be non-empty text")


def _required_int(payload: Mapping[str, JsonValue], field_name: str) -> int:
    """读取 JSON object 中的必填整数字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 整数值。
    :raises HostDurableError: 字段缺失或不是非负整数时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HostDurableError(f"{field_name} must be non-negative integer")
    return value


def _payload_size_bytes(payload: Mapping[str, JsonValue]) -> int:
    """计算 canonical JSON payload 的 UTF-8 字节数。

    :param payload: JSON object。
    :returns: UTF-8 字节数。
    """

    return len(canonical_json_dumps(payload).encode("utf-8"))


__all__ = [
    "event_payload_object",
    "event_payload_object_for_result_ref",
    "sqlite_payload_object",
    "tool_call_request_atoms",
    "ToolCallRequestAtoms",
]
