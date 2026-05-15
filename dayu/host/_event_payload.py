"""Host 内部 EventLog payload 读取辅助函数。

本模块只承载 Host 层内部从 durable EventLog row 解析 JSON payload 的
通用逻辑。错误类型使用 Host durable error，不进入 ``dayu.runtime``，
也不表达 Engine / UI / Service 语义。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventLogRow


def payload_object(event: EventLogRow) -> Mapping[str, JsonValue]:
    """解析 EventLog payload JSON 映射。

    :param event: EventLog row。
    :returns: payload 映射。
    :raises HostDurableError: payload JSON 非法或不是 JSON 映射时抛出。
    """

    try:
        value = cast(JsonValue, json.loads(event.payload_json))
    except json.JSONDecodeError as exc:
        raise HostDurableError("EventLog payload_json is invalid") from exc
    if not isinstance(value, Mapping):
        raise HostDurableError("EventLog payload_json must be a JSON mapping")
    return cast(Mapping[str, JsonValue], value)


def required_payload_text(
    payload: Mapping[str, JsonValue], *, field_name: str
) -> str:
    """读取 payload 中的必填文本字段。

    :param payload: payload 映射。
    :param field_name: 字段名。
    :returns: 文本值。
    :raises HostDurableError: 字段缺失或不是非空文本时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, str) or value.strip() == "":
        raise HostDurableError(f"payload field {field_name} must be non-empty text")
    return value
