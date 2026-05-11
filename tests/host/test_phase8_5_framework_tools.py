"""P8.5 Host 私有 framework tool 边界单元测试。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest

from dayu.contracts import ToolTruncateSpec
from dayu.contracts.tool_call import ToolExecutionRequest
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolExecutionOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.host._event_store import InMemoryRunEventStore
from dayu.host._framework_tools import FRAMEWORK_FETCH_MORE_NAME
from dayu.host._tool_runtime import HostToolRuntime


@dataclass(frozen=True, slots=True)
class _Executor:
    """测试用业务 executor。"""

    async def execute(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """返回固定成功结果。

        :param request: 工具执行请求。
        :returns: 成功 outcome。
        :raises Exception: 不主动抛出异常。
        """

        _ = request
        return ToolCompletedOutcome(
            result=ToolResultSuccess(ok=True, value="ok", meta=None)
        )


def _runtime() -> HostToolRuntime:
    """构造 HostToolRuntime。

    :returns: runtime。
    :raises Exception: 不主动抛出异常。
    """

    return HostToolRuntime(
        is_durable=False,
        executor=_Executor(),
        event_store=InMemoryRunEventStore(),
        truncate_specs={
            "demo": ToolTruncateSpec(
                enabled=True,
                strategy="text_chars",
                limits={"max_chars": 1},
                target_field=None,
                field_path=None,
                ttl_seconds=30,
            )
        },
    )


def test_framework_tool_set_projects_fetch_more_schema() -> None:
    """FrameworkToolSet 能投影 Host 私有 fetch_more schema。"""

    runtime = _runtime()

    schemas = runtime._framework_tools.tool_schemas()

    assert len(schemas) == 1
    assert schemas[0].function.name == FRAMEWORK_FETCH_MORE_NAME
    assert runtime._framework_tools.fetch_more_definition().to_tool_schema() == schemas[0]


@pytest.mark.asyncio
async def test_framework_fetch_more_callable_fails_fast_when_not_intercepted() -> None:
    """framework fetch_more schema callable 被直接执行时必须暴露装配错误。"""

    runtime = _runtime()
    definition = runtime._framework_tools.fetch_more_definition()

    with pytest.raises(AssertionError, match="intercepted"):
        await definition.callable(cast(ToolExecutionRequest, None))
