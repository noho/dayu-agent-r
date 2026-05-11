"""Host 内部 Engine-visible 工具 schema 投影端口。"""

from __future__ import annotations

from typing import Protocol

from dayu.engine import ToolSchema


class EngineToolSchemaProvider(Protocol):
    """Host 内部工具 schema provider。

    该端口只返回 Engine 可见的 ``ToolSchema``，不暴露工具定义、callable、
    executor、manager 或 cursor 状态。
    """

    def engine_visible_tool_schemas(
        self,
        user_tool_schemas: tuple[ToolSchema, ...],
    ) -> tuple[ToolSchema, ...]:
        """合成真正传给 Engine 的工具 schema。

        :param user_tool_schemas: 调用方传入的业务工具 schema。
        :returns: 业务 schema 与 Host 私有 framework schema 的合成元组。
        :raises ValueError: 业务 schema 与 Host 私有工具名冲突时抛出。
        """
        ...


__all__: list[str] = []
