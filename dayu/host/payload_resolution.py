"""Host EventLog payload 引用解析 helper。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventLogRow
from dayu.host.durable.payload import PayloadKind, read_payload_descriptor
from dayu.host.durable.schema import TABLE_SQLITE_PAYLOADS
from dayu.host.durable.transaction import HostTransaction


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
    descriptor = read_payload_descriptor(transaction, event.payload_ref)
    if descriptor is None:
        raise HostDurableError(f"{payload_label} payload descriptor is missing")
    if descriptor.payload_kind is not PayloadKind.SQLITE_PAYLOAD:
        raise HostDurableError(f"{payload_label} payload must be sqlite payload")
    if descriptor.payload_digest != event.payload_digest:
        raise HostDurableError(f"{payload_label} payload digest mismatch")
    if descriptor.sqlite_payload_id is None:
        raise HostDurableError(f"{payload_label} sqlite payload id is missing")
    row = transaction.fetchone(
        f"""
        SELECT payload_json
        FROM {TABLE_SQLITE_PAYLOADS}
        WHERE payload_id = ?
        """,
        (descriptor.sqlite_payload_id,),
    )
    if row is None:
        raise HostDurableError(f"{payload_label} sqlite payload row is missing")
    payload_json = row.get("payload_json")
    if not isinstance(payload_json, str):
        raise HostDurableError(f"{payload_label} sqlite payload JSON is invalid")
    return _json_object(payload_json, payload_label=payload_label)


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


__all__ = ["event_payload_object"]
