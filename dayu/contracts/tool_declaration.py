"""工具声明契约。

本模块提供最小 OLD-like ``@tool`` 声明能力，用于把 LLM-facing
``ToolSchema``、Host ToolRuntime 截断声明、执行绑定与展示 metadata 放在
同一个工具现场声明。它不是 ToolRegistry，不负责权限治理、生命周期治理、
工具发现、middleware 或业务工具迁移。

``ToolDefinition`` / ``ToolBundle`` 是装配输入；Engine / Runner 只能接收
由 ``to_tool_schema()`` 或 ``to_tool_schemas()`` 投影得到的
``ToolSchema``，不得消费 definition / bundle 本体、截断声明、展示 metadata
或 callable / executor binding。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass

from dayu.contracts.tool_call import ToolExecutionRequest
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_outcome import ToolExecutionOutcome
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
    ToolTruncateSpec,
)

ToolFunctionCallable = Callable[
    [ToolExecutionRequest], Awaitable[ToolExecutionOutcome]
]
"""工具函数 callable 类型。

P5 仅承诺 async callable 绑定，避免在公共契约层引入同步函数调度策略。
"""


@dataclass(frozen=True, slots=True)
class FunctionToolExecutor:
    """把工具函数适配为 ``ToolExecutor``。

    :param function: 工具执行函数。
    """

    function: ToolFunctionCallable

    async def execute(
        self, request: ToolExecutionRequest
    ) -> ToolExecutionOutcome:
        """执行绑定的工具函数。

        :param request: 工具执行请求。
        :returns: 工具执行 outcome。
        :raises Exception: 底层工具函数异常会透传给调用方。
        """

        return await self.function(request)


@dataclass(frozen=True, slots=True)
class ToolDisplayInfo:
    """工具展示 metadata。

    :param name: 用户友好的工具展示名称。
    """

    name: str


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """单个工具的强类型声明结果。

    :param name: 工具名。
    :param callable: 工具函数绑定。
    :param executor: ``ToolExecutor`` 绑定。
    :param schema: LLM-facing 工具 schema。
    :param truncate: Host ToolRuntime 截断声明；为 ``None`` 表示不截断。
    :param display: 展示 metadata；不进入 LLM schema。
    :param tags: 展示或装配标签；不进入 LLM schema。
    """

    name: str
    callable: ToolFunctionCallable
    executor: ToolExecutor
    schema: ToolSchema
    truncate: ToolTruncateSpec | None
    display: ToolDisplayInfo | None
    tags: tuple[str, ...]

    def __post_init__(self) -> None:
        """校验工具声明的 LLM schema 名称同源。

        :returns: 无返回值。
        :raises ValueError: ``name`` 与 ``schema.function.name`` 不一致时抛出。
        """

        if self.name != self.schema.function.name:
            raise ValueError(
                "ToolDefinition name must match schema.function.name"
            )

    def to_tool_schema(self) -> ToolSchema:
        """投影为 Engine / Runner 可见的工具 schema。

        :returns: LLM-facing ``ToolSchema``。
        :raises Exception: 不主动抛出异常。
        """

        return self.schema


@dataclass(frozen=True, slots=True)
class ToolBundle:
    """一组工具声明。

    :param definitions: 工具定义元组。
    """

    definitions: tuple[ToolDefinition, ...]

    def __post_init__(self) -> None:
        """校验 bundle 内工具名唯一。

        :returns: 无返回值。
        :raises ValueError: 出现重复工具名时抛出。
        """

        names: set[str] = set()
        for definition in self.definitions:
            if definition.name in names:
                raise ValueError(f"duplicate tool name: {definition.name}")
            names.add(definition.name)

    def to_tool_schemas(self) -> tuple[ToolSchema, ...]:
        """投影为 Engine / Runner 可见的工具 schema 元组。

        :returns: ``ToolSchema`` 元组。
        :raises Exception: 不主动抛出异常。
        """

        return tuple(definition.to_tool_schema() for definition in self.definitions)

    def truncate_specs(self) -> Mapping[str, ToolTruncateSpec]:
        """返回 Host ToolRuntime 使用的截断声明映射。

        :returns: 按工具名索引的截断声明映射；未声明截断的工具不会出现。
        :raises Exception: 不主动抛出异常。
        """

        return {
            definition.name: definition.truncate
            for definition in self.definitions
            if definition.truncate is not None
        }


def tool(
    *,
    name: str,
    description: str,
    parameters: ToolParametersSchema,
    truncate: ToolTruncateSpec | None = None,
    display_name: str | None = None,
    tags: Sequence[str] = (),
) -> Callable[[ToolFunctionCallable], ToolDefinition]:
    """声明一个工具并返回 ``ToolDefinition``。

    :param name: LLM-facing 工具名。
    :param description: LLM-facing 工具描述。
    :param parameters: LLM-facing 参数 schema。
    :param truncate: Host ToolRuntime 截断声明。
    :param display_name: 展示友好名称；内部会转换为 ``ToolDisplayInfo``，
        且不进入 schema。
    :param tags: 展示或装配标签；不进入 schema。
    :returns: 接收工具函数并产出 ``ToolDefinition`` 的 decorator。
    :raises Exception: 不主动抛出异常。
    """

    def _decorate(function: ToolFunctionCallable) -> ToolDefinition:
        """把工具函数封装成工具定义。

        :param function: 工具执行函数。
        :returns: 工具定义。
        :raises Exception: 不主动抛出异常。
        """

        schema = ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=name,
                description=description,
                parameters=parameters,
            ),
        )
        return ToolDefinition(
            name=name,
            callable=function,
            executor=FunctionToolExecutor(function),
            schema=schema,
            truncate=truncate,
            display=(
                ToolDisplayInfo(name=display_name)
                if display_name is not None
                else None
            ),
            tags=tuple(tags),
        )

    return _decorate


__all__ = [
    "FunctionToolExecutor",
    "ToolBundle",
    "ToolDefinition",
    "ToolDisplayInfo",
    "ToolFunctionCallable",
    "tool",
]
