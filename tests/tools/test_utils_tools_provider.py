"""Utils tools provider 测试。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pytest import MonkeyPatch

import dayu.tools.utils.provider as utils_provider
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolFailedOutcome
from dayu.runtime.tools_discovery import PythonImportPathProvider, ToolsDiscoveryProviderSpec
from dayu.tools.utils.provider import (
    DEFAULT_TIMEZONE,
    GET_CURRENT_TIME_TOOL_NAME,
    discover_tools,
)

_TOOL_CALL_ID: Final[str] = "call-utils-time"


class _OpenCancellationToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        Returns:
            始终返回 ``False``。

        Raises:
            无。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        Returns:
            始终返回 ``None``。

        Raises:
            无。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        Returns:
            始终返回 ``None``。

        Raises:
            无。
        """

        return None


def test_utils_provider_discovers_get_current_time_definition() -> None:
    """Utils provider 应发现带 utils/time 标签的 get_current_time。"""

    output = discover_tools(_spec())
    definition = output.definitions[0]

    assert output.provider_id == "utils-tools"
    assert tuple(definition.name for definition in output.definitions) == (GET_CURRENT_TIME_TOOL_NAME,)
    assert definition.tags == ("utils", "time")
    assert definition.schema.function.parameters.properties["timezone"] == {
        "type": "string",
        "description": "IANA timezone name. 当前仅支持 Asia/Shanghai。",
        "enum": [DEFAULT_TIMEZONE],
        "default": DEFAULT_TIMEZONE,
    }
    assert definition.schema.function.parameters.required == ()


def test_get_current_time_tool_returns_current_shanghai_time() -> None:
    """get_current_time 应返回稳定字段和可解析 ISO 时间。"""

    definition = discover_tools(_spec()).definitions[0]

    outcome = asyncio.run(
        definition.callable(
            _call({}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    value = outcome.result.value
    assert isinstance(value, dict)
    assert value["timezone"] == DEFAULT_TIMEZONE
    assert isinstance(value["time"], str)
    assert isinstance(value["weekday"], str)
    assert isinstance(value["iso"], str)
    datetime.fromisoformat(value["iso"])


def test_get_current_time_rejects_unsupported_timezone() -> None:
    """get_current_time 对非 Asia/Shanghai 时区必须 fail fast。"""

    definition = discover_tools(_spec()).definitions[0]

    outcome = asyncio.run(
        definition.callable(
            _call({"timezone": "UTC"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "invalid_argument"
    assert "仅支持 Asia/Shanghai" in outcome.result.message


def test_get_current_time_rejects_non_string_timezone_with_type_message() -> None:
    """get_current_time 对非字符串 timezone 应返回清晰类型错误。"""

    definition = discover_tools(_spec()).definitions[0]

    outcome = asyncio.run(
        definition.callable(
            _call({"timezone": 8}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "invalid_argument"
    assert "必须是字符串" in outcome.result.message
    assert outcome.result.hint is not None
    assert DEFAULT_TIMEZONE in outcome.result.hint


def test_get_current_time_returns_failed_outcome_when_timezone_data_missing(
    monkeypatch: MonkeyPatch,
) -> None:
    """ZoneInfo 加载失败时 get_current_time 应返回失败 outcome 而非抛异常。

    Args:
        monkeypatch: pytest monkeypatch 夹具，用于替换 provider 内时区加载器。

    Returns:
        无。

    Raises:
        AssertionError: 工具未返回预期失败 outcome 时由断言抛出。
    """

    definition = discover_tools(_spec()).definitions[0]

    monkeypatch.setattr(utils_provider, "ZoneInfo", _raise_zoneinfo_not_found)

    outcome = asyncio.run(
        definition.callable(
            _call({}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "timezone_load_failed"
    assert "无法加载时区" in outcome.result.message
    assert outcome.result.meta is not None


def _raise_zoneinfo_not_found(key: str) -> ZoneInfo:
    """模拟运行环境缺少 IANA timezone 数据。

    Args:
        key: 待加载时区名称。

    Returns:
        不返回；该函数总是抛出异常。

    Raises:
        ZoneInfoNotFoundError: 始终抛出，用于覆盖工具失败分支。
    """

    raise ZoneInfoNotFoundError(key)


def _spec() -> ToolsDiscoveryProviderSpec:
    """构造 utils provider spec。

    Returns:
        测试 provider spec。
    """

    return ToolsDiscoveryProviderSpec(
        spec_id="utils-tools",
        location=PythonImportPathProvider("dayu.tools.utils:discover_tools"),
        enabled=True,
        config={},
    )


def _call(arguments: dict[str, JsonValue]) -> ToolCallRequest:
    """构造工具调用请求。

    Args:
        arguments: 工具参数。

    Returns:
        工具调用请求。
    """

    return ToolCallRequest(
        tool_call_id=_TOOL_CALL_ID,
        name=GET_CURRENT_TIME_TOOL_NAME,
        arguments=arguments,
        index_in_iteration=0,
        provider_state=None,
    )


def _context() -> BatchToolExecutionContext:
    """构造工具执行上下文。

    Returns:
        批式工具执行上下文。
    """

    return BatchToolExecutionContext(
        run_id="run-utils-time",
        session_id="session-utils-time",
        iteration_id="iteration-utils-time",
        timeout_seconds=5.0,
        cancellation_token=_OpenCancellationToken(),
        correlation_id="run-utils-time:iteration-utils-time:tool_batch",
    )
