"""Host 私有 framework 工具声明。

本模块用公共 ``@tool`` 声明机制构造 Host 内置 framework 工具，但只在
Host 内部投影 schema 和绑定 callable。Engine 只能看到普通
``ToolSchema``；不会接收 ``ToolDefinition``、callable、manager 或 cursor
实现类型。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from dayu.contracts import (
    ToolDefinition,
    ToolParametersSchema,
    ToolSchema,
    tool,
)
from dayu.contracts.tool_call import ToolExecutionRequest
from dayu.contracts.tool_outcome import ToolExecutionOutcome
from dayu.host._runtime_truncate_manager import RuntimeTruncateManager

FRAMEWORK_FETCH_MORE_NAME: str = "fetch_more"
"""Host 私有 framework 补读工具名。"""


@dataclass(slots=True)
class FrameworkToolSet:
    """Host 私有 framework 工具集合。

    :param manager: 截断管理器。
    """

    manager: RuntimeTruncateManager
    _fetch_more_definition: ToolDefinition = field(init=False)

    def __post_init__(self) -> None:
        """初始化并缓存 framework 工具定义。

        :returns: 无返回值。
        :raises Exception: 构造工具定义失败时透传。
        """

        self._fetch_more_definition = self._build_fetch_more_definition()

    def fetch_more_definition(self) -> ToolDefinition:
        """返回缓存的 ``fetch_more`` 工具定义。

        :returns: Host 私有 framework 工具定义。
        :raises Exception: 不主动抛出异常。
        """

        return self._fetch_more_definition

    def _build_fetch_more_definition(self) -> ToolDefinition:
        """构造 ``fetch_more`` 工具定义。

        :returns: Host 私有 framework 工具定义。
        :raises Exception: 不主动抛出异常。
        """

        # 这里使用闭包是为了让公共 @tool callable 只暴露标准
        # ToolExecutionRequest，同时把 manager 保持在 Host 私有边界内。
        manager = self.manager

        @tool(
            name=FRAMEWORK_FETCH_MORE_NAME,
            description=(
                "继续读取上一条已截断的工具结果。只有当最新工具结果里的 "
                'truncation.next_action="fetch_more" 时才调用；直接使用同一条 '
                "truncation.fetch_more_args，不要复用更早返回里的旧 cursor。"
            ),
            parameters=ToolParametersSchema(
                type="object",
                properties={
                    "cursor": {
                        "type": "string",
                        "description": (
                            "单次有效的补读游标，直接使用最新工具结果里的 " "truncation.fetch_more_args.cursor。"
                        ),
                    },
                    "scope_token": {
                        "type": "string",
                        "description": (
                            "范围校验令牌，直接使用同一条工具结果里的 " "truncation.fetch_more_args.scope_token。"
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "description": ("可选的单次读取上限；如果 hint 未提供则不要自行编造。"),
                    },
                },
                required=("cursor", "scope_token"),
                additional_properties=False,
            ),
        )
        async def _fetch_more(
            request: ToolExecutionRequest,
        ) -> ToolExecutionOutcome:
            """标记 Host 私有 framework 补读工具的 schema callable。

            :param request: Engine 发起的普通工具执行请求。
            :returns: 不返回；真实执行路径由 ``HostToolRuntime`` 拦截。
            :raises AssertionError: 该 callable 被直接执行时抛出。
            """

            _ = manager
            _ = request
            raise AssertionError("framework fetch_more must be intercepted by HostToolRuntime")

        return _fetch_more

    def tool_schemas(self) -> tuple[ToolSchema, ...]:
        """返回 Engine-visible framework 工具 schema。

        :returns: Host 内置 framework 工具 schema 元组。
        :raises Exception: 不主动抛出异常。
        """

        return (self.fetch_more_definition().to_tool_schema(),)


__all__: list[str] = []
