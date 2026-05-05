"""工具 schema 强类型契约。

本模块用于在 Engine 公共契约层描述 LLM 可见的工具 schema 形态。
schema 内的字段值（``type``、``function``）是 OpenAI 风格协议字面量，
本契约通过 :class:`Literal` 收窄；参数 schema 内部子节点遵循
:data:`JsonValue`，由具体工具发布方提供合法 JSON Schema。

设计要点：

- ``ToolParametersSchema`` 仅承诺三个稳定字段：``type``、``properties``、
  ``required``，外加可选的 ``additional_properties``。本 Phase 不实现
  JSON Schema runtime validator。
- ``ToolSchema`` / ``ToolFunctionSchema`` 严格遵循 OpenAI Function-call
  格式以利 Runner 直接传递；其它 provider 适配由 Phase 1+ 处理。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from dayu.contracts.json_value import JsonValue


@dataclass(frozen=True, slots=True)
class ToolParametersSchema:
    """工具参数 JSON Schema 顶层结构。

    :param type: 顶层 schema 类型，固定为 ``"object"``。
    :param properties: 顶层属性 schema 映射。
    :param required: 必填字段名元组。
    :param additional_properties: ``additionalProperties`` 字段；为
        ``None`` 表示不显式声明。
    """

    type: Literal["object"]
    properties: Mapping[str, JsonValue]
    required: tuple[str, ...]
    additional_properties: bool | None


@dataclass(frozen=True, slots=True)
class ToolFunctionSchema:
    """工具函数定义。

    :param name: 工具名（同一 Agent run 内必须唯一）。
    :param description: 工具描述，供 LLM 理解。
    :param parameters: 工具参数 schema。
    """

    name: str
    description: str
    parameters: ToolParametersSchema


@dataclass(frozen=True, slots=True)
class ToolSchema:
    """工具 schema 顶层包装。

    :param type: schema 类型，固定为 ``"function"``。
    :param function: 工具函数定义。
    """

    type: Literal["function"]
    function: ToolFunctionSchema


__all__ = ["ToolSchema", "ToolFunctionSchema", "ToolParametersSchema"]
