"""Engine 通用 structured-output 请求与能力契约。

本模块只定义 provider-neutral 的输出格式请求、Runner capability 与合法组合。
具体 provider payload 由 Runner adapter 投影；业务 schema 的产生、持久化与治理不属于
Engine。
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias, assert_never

from dayu.contracts.json_value import JsonValue


class StructuredOutputCapability(StrEnum):
    """Runner 支持的 structured-output 最高能力等级。

    成员：

    - ``NONE``：不支持 structured-output transport。
    - ``JSON_OBJECT``：支持 JSON object mode。
    - ``JSON_SCHEMA``：支持 JSON object 与 JSON Schema mode。
    """

    NONE = "none"
    JSON_OBJECT = "json_object"
    JSON_SCHEMA = "json_schema"


@dataclass(frozen=True, slots=True)
class JsonObjectStructuredOutputRequest:
    """请求 provider 返回 JSON object。

    本 variant 没有附加字段；其具体类型本身就是 mode 的唯一表达。
    """


@dataclass(frozen=True, slots=True)
class JsonSchemaStructuredOutputRequest:
    """请求 provider 按 JSON Schema 返回 structured output。

    :param name: provider-native schema 名称，必须为非空文本且不得含首尾空白。
    :param schema: provider-neutral JSON Schema mapping。
    :param strict: 是否请求 provider 启用 strict schema adherence。
    """

    name: str
    schema: Mapping[str, JsonValue]
    strict: bool

    def __post_init__(self) -> None:
        """校验 JSON Schema request 的严格入口不变量。

        :returns: ``None``。
        :raises TypeError: ``name``、``schema``、``strict`` 或 schema 内 JSON
            值类型非法时抛出。
        :raises ValueError: ``name`` 为空、含首尾空白，或 schema 含非有限浮点数
            时抛出。
        """

        if not isinstance(self.name, str):
            raise TypeError("JsonSchemaStructuredOutputRequest.name must be str")
        if not self.name or self.name != self.name.strip():
            raise ValueError(
                "JsonSchemaStructuredOutputRequest.name must be non-empty "
                "without surrounding whitespace"
            )
        if not isinstance(self.schema, Mapping):
            raise TypeError(
                "JsonSchemaStructuredOutputRequest.schema must be a mapping"
            )
        if not isinstance(self.strict, bool):
            raise TypeError("JsonSchemaStructuredOutputRequest.strict must be bool")
        _validate_json_mapping(self.schema, path="schema")


StructuredOutputRequest: TypeAlias = (
    JsonObjectStructuredOutputRequest | JsonSchemaStructuredOutputRequest
)
"""单次 run 的 provider-neutral structured-output 请求封闭联合。"""


def validate_structured_output_request(
    *,
    capability: StructuredOutputCapability,
    request: StructuredOutputRequest | None,
) -> None:
    """校验 Runner capability 与单次 structured-output request 的组合。

    :param capability: Runner 声明的最高 structured-output capability。
    :param request: 本次调用的显式 structured-output request；``None`` 表示
        不请求 structured-output transport。
    :returns: ``None``。
    :raises TypeError: capability 或 request 不是封闭契约成员时抛出。
    :raises ValueError: capability 不支持请求 mode 时抛出。
    """

    if not isinstance(capability, StructuredOutputCapability):
        raise TypeError("capability must be StructuredOutputCapability")
    if request is None:
        return
    if not isinstance(
        request,
        (JsonObjectStructuredOutputRequest, JsonSchemaStructuredOutputRequest),
    ):
        raise TypeError("request must be a StructuredOutputRequest union member")

    match capability:
        case StructuredOutputCapability.NONE:
            raise ValueError(
                "structured output capability 'none' does not support "
                f"request mode '{_request_mode(request)}'"
            )
        case StructuredOutputCapability.JSON_OBJECT:
            if isinstance(request, JsonSchemaStructuredOutputRequest):
                raise ValueError(
                    "structured output capability 'json_object' does not "
                    "support request mode 'json_schema'"
                )
        case StructuredOutputCapability.JSON_SCHEMA:
            return
        case _:
            assert_never(capability)


def _request_mode(request: StructuredOutputRequest) -> str:
    """返回 concrete request variant 对应的 mode 文本。

    :param request: structured-output request union 成员。
    :returns: ``json_object`` 或 ``json_schema``。
    :raises AssertionError: 封闭联合出现未处理成员时抛出。
    """

    match request:
        case JsonObjectStructuredOutputRequest():
            return StructuredOutputCapability.JSON_OBJECT.value
        case JsonSchemaStructuredOutputRequest():
            return StructuredOutputCapability.JSON_SCHEMA.value
    assert_never(request)


def _validate_json_mapping(
    value: Mapping[str, JsonValue], *, path: str
) -> None:
    """递归校验 JSON object 的键和值。

    :param value: 待校验 JSON object。
    :param path: 错误定位路径。
    :returns: ``None``。
    :raises TypeError: 键或值类型不属于 JSON 契约时抛出。
    :raises ValueError: 存在非有限浮点数时抛出。
    """

    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{path} keys must be str")
        _validate_json_value(item, path=f"{path}.{key}")


def _validate_json_value(value: JsonValue, *, path: str) -> None:
    """递归校验一个严格 JSON 值。

    :param value: 待校验 JSON 值。
    :param path: 错误定位路径。
    :returns: ``None``。
    :raises TypeError: 值类型不属于 JSON 契约时抛出。
    :raises ValueError: 浮点数不是有限值时抛出。
    """

    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must be a finite JSON number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        _validate_json_mapping(value, path=path)
        return
    raise TypeError(f"{path} contains a non-JSON value")


__all__ = [
    "JsonObjectStructuredOutputRequest",
    "JsonSchemaStructuredOutputRequest",
    "StructuredOutputCapability",
    "StructuredOutputRequest",
    "validate_structured_output_request",
]
