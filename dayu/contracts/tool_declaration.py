"""工具声明契约。

本模块提供最小工具 *声明* 能力：把 LLM-facing ``ToolSchema``、Host
ToolRuntime 截断声明、展示 metadata 与 *单工具* :class:`ToolCallable`
放在同一个工具现场声明。

``ToolDefinition`` / ``ToolBundle`` 是 Host / ToolRuntime 装配输入；
Engine / Runner 只能接收由 ``to_tool_schema()`` 或
``to_tool_schemas()`` 投影得到的 ``ToolSchema``，不得消费 definition /
bundle 本体、截断声明、展示 metadata 或 ``ToolCallable``。

`ToolCallable` 只是 *单* 工具调用协议；它不参与批级握手 / 治理。把一组
``ToolDefinition.callable`` 包装为受治理的批式 :class:`ToolExecutor` 是
Host / ToolRuntime 的职责，公共契约层不提供默认执行器或 callable
适配器。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import InitVar, dataclass
from typing import Protocol, runtime_checkable

from dayu.contracts._validation import require_non_empty_text as _require_non_empty_text
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    ToolCallRequest,
)
from dayu.contracts.tool_outcome import ToolExecutionOutcome
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
    ToolTruncateSpec,
)


@runtime_checkable
class ToolCallable(Protocol):
    """单工具调用协议。

    `ToolCallable` 是工具函数在 *单次* 调用粒度的强类型形状，被 Host /
    ToolRuntime 在批式 :class:`ToolExecutor` 内部组合调用。它本身不参与
    批级握手或治理。

    实现必须为 ``async`` 函数；不允许同步实现，避免 Host 治理路径上意外
    阻塞事件循环。
    """

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行单次工具调用。

        :param call: 单次工具调用请求。
        :param context: 批式握手共享的运行期上下文。
        :returns: 工具执行结果。
        :raises Exception: 实现可透传业务异常；Host / ToolRuntime 负责
            把异常归一化为 :class:`ToolFailedOutcome`。
        """

        ...


@dataclass(frozen=True, slots=True)
class ToolDisplayInfo:
    """工具展示 metadata。

    :param name: 用户友好的工具展示名称。
    """

    name: str

    def __post_init__(self) -> None:
        """校验展示名称非空。

        :returns: ``None``。
        :raises ValueError: ``name`` 为空或只包含空白时抛出。
        """

        _require_non_empty_text(self.name, field_name="ToolDisplayInfo.name")


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """单个工具的强类型 *声明* 结果。

    本对象承载工具元数据与 *单工具* :class:`ToolCallable`，但不持有任何
    批式 executor。把 ``callable`` 组合为受治理的批式
    :class:`ToolExecutor` 是 Host / ToolRuntime 的职责。

    :param name: 工具名。
    :param schema: LLM-facing 工具 schema。
    :param callable: 单工具调用协议。
    :param truncate: Host ToolRuntime 截断声明；为 ``None`` 表示不截断。
    :param display: 展示 metadata；不进入 LLM schema。
    :param tags: 展示或装配标签；不进入 LLM schema。
    """

    name: str
    schema: ToolSchema
    callable: ToolCallable
    truncate: ToolTruncateSpec | None
    display: ToolDisplayInfo | None
    tags: tuple[str, ...]

    def __post_init__(self) -> None:
        """校验工具声明的 LLM schema 名称同源。

        :returns: 无返回值。
        :raises ValueError: ``name`` 为空，或 ``name`` 与
            ``schema.function.name`` 不一致时抛出。
        """

        _require_non_empty_text(self.name, field_name="ToolDefinition name")
        if self.name != self.schema.function.name:
            raise ValueError("ToolDefinition name must match schema.function.name")

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
    :param _allow_empty: 仅供框架 no-tool 真源构造空 bundle。
    """

    definitions: tuple[ToolDefinition, ...]
    _allow_empty: InitVar[bool] = False

    def __post_init__(self, _allow_empty: bool) -> None:
        """校验 bundle 内工具名唯一。

        :param _allow_empty: 是否允许空工具集合。
        :returns: 无返回值。
        :raises ValueError: 工具集合为空或出现重复工具名时抛出。
        """

        if not self.definitions and not _allow_empty:
            raise ValueError("ToolBundle.definitions must be non-empty")
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
            definition.name: definition.truncate for definition in self.definitions if definition.truncate is not None
        }


@dataclass(frozen=True, slots=True)
class _ToolDecorator:
    """``@tool(...)`` 装饰器实现。

    本对象只在装饰器内部使用；保存声明现场的元数据，在被调用时把传入
    的 :class:`ToolCallable` 包装成 :class:`ToolDefinition` 返回。

    :param name: 工具名。
    :param description: LLM-facing 工具描述。
    :param parameters: LLM-facing 参数 schema。
    :param truncate: Host ToolRuntime 截断声明。
    :param display: 展示 metadata；为 ``None`` 表示不声明展示名。
    :param tags: 展示或装配标签元组。
    """

    name: str
    description: str
    parameters: ToolParametersSchema
    truncate: ToolTruncateSpec | None
    display: ToolDisplayInfo | None
    tags: tuple[str, ...]

    def __call__(self, callable_: ToolCallable) -> ToolDefinition:
        """把被装饰的 :class:`ToolCallable` 凝聚为工具定义。

        :param callable_: 被装饰的单工具调用协议实现。
        :returns: 工具定义；``callable`` 字段直接保留传入引用。
        :raises Exception: 不主动抛出异常。
        """

        schema = ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=self.name,
                description=self.description,
                parameters=self.parameters,
            ),
        )
        return ToolDefinition(
            name=self.name,
            schema=schema,
            callable=callable_,
            truncate=self.truncate,
            display=self.display,
            tags=self.tags,
        )


def tool(
    *,
    name: str,
    description: str,
    parameters: ToolParametersSchema,
    truncate: ToolTruncateSpec | None = None,
    display_name: str | None = None,
    tags: Sequence[str] = (),
) -> Callable[[ToolCallable], ToolDefinition]:
    """声明一个工具并返回装饰器。

    本装饰器用于在工具函数现场同源声明 :class:`ToolSchema`、Host
    ToolRuntime 截断声明、展示 metadata、标签与 *单工具*
    :class:`ToolCallable`，凝聚为 :class:`ToolDefinition`。它 *不* 把被
    装饰对象绑定为任何批式 executor —— 批式 executor 装配由 Host /
    ToolRuntime 负责。

    :param name: LLM-facing 工具名。
    :param description: LLM-facing 工具描述。
    :param parameters: LLM-facing 参数 schema。
    :param truncate: Host ToolRuntime 截断声明。
    :param display_name: 展示友好名称；内部会转换为 ``ToolDisplayInfo``，
        且不进入 schema。
    :param tags: 展示或装配标签；不进入 schema。
    :returns: 接收单工具 :class:`ToolCallable` 并产出
        :class:`ToolDefinition` 的装饰器。
    :raises Exception: 不主动抛出异常。
    """

    return _ToolDecorator(
        name=name,
        description=description,
        parameters=parameters,
        truncate=truncate,
        display=(ToolDisplayInfo(name=display_name) if display_name is not None else None),
        tags=tuple(tags),
    )


__all__ = [
    "ToolBundle",
    "ToolCallable",
    "ToolDefinition",
    "ToolDisplayInfo",
    "tool",
]
