"""通用工具的当前 ToolsDiscovery provider。

本模块通过原生 ``ToolDefinition`` 暴露与业务无关的工具。当前只提供
``get_current_time``，用于回答需要实时时钟的用户问题；当前日期仍由
系统 prompt 独立注入，本工具不替代财报、网页或文件事实来源。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolDefinition, tool
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure, ToolResultMeta, ToolResultSuccess
from dayu.contracts.tool_schema import ToolParametersSchema
from dayu.contracts.tool_source import ToolBundleSourceKind, ToolBundleSourceRef
from dayu.runtime.tools_discovery import (
    ToolsDiscoveryProviderOutput,
    ToolsDiscoveryProviderSpec,
)

GET_CURRENT_TIME_TOOL_NAME: Final[str] = "get_current_time"
"""获取当前时间工具的稳定名称。"""

DEFAULT_TIMEZONE: Final[str] = "Asia/Shanghai"
"""当前时间工具唯一支持的默认时区。"""

UTILS_TOOL_TAG: Final[str] = "utils"
"""通用工具选择标签。"""

TIME_TOOL_TAG: Final[str] = "time"
"""时间能力选择标签。"""

_PROVIDER_ID: Final[str] = "utils-tools"
_VERSION_REF: Final[str] = "utils-tools-provider-v1"
_SOURCE_ID: Final[str] = "dayu.tools.utils"
_TIMEZONE_ARGUMENT: Final[str] = "timezone"
_ERROR_INVALID_ARGUMENT: Final[str] = "invalid_argument"
_ERROR_TIMEZONE_LOAD_FAILED: Final[str] = "timezone_load_failed"
_SUPPORTED_TIMEZONES: Final[frozenset[str]] = frozenset({DEFAULT_TIMEZONE})
_WEEKDAY_NAMES: Final[tuple[str, ...]] = (
    "星期一",
    "星期二",
    "星期三",
    "星期四",
    "星期五",
    "星期六",
    "星期日",
)
_INVALID_ARGUMENT_HINT: Final[str] = "timezone 只能省略或填写 Asia/Shanghai；不要使用其它时区名称。"


def discover_tools(spec: ToolsDiscoveryProviderSpec) -> ToolsDiscoveryProviderOutput:
    """发现通用工具声明。

    Args:
        spec: ToolsDiscovery 传入的 provider 显式配置；当前 provider 不读取
            自有配置，仅保留该参数以符合 provider callable 契约。

    Returns:
        provider 输出，包含 ``get_current_time`` 工具定义与来源引用。

    Raises:
        Exception: 工具声明契约构造失败时透出。
    """

    del spec
    return ToolsDiscoveryProviderOutput(
        provider_id=_PROVIDER_ID,
        version_ref=_VERSION_REF,
        source_refs=(_source_ref(),),
        definitions=(build_get_current_time_tool_definition(),),
    )


def build_get_current_time_tool_definition() -> ToolDefinition:
    """构造 ``get_current_time`` 工具定义。

    Args:
        无。

    Returns:
        当前时间工具定义。

    Raises:
        Exception: 工具声明契约构造失败时透出。
    """

    @tool(
        name=GET_CURRENT_TIME_TOOL_NAME,
        description=("获取当前日期和时间。仅支持 timezone=Asia/Shanghai；返回 time、timezone、weekday、iso。"),
        parameters=_get_current_time_parameters(),
        tags=(UTILS_TOOL_TAG, TIME_TOOL_TAG),
        display_name="获取当前时间",
    )
    async def get_current_time(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行当前时间工具调用。

        Args:
            call: 当前工具调用请求。
            context: 批式工具执行上下文；本工具不读取其中的治理状态。

        Returns:
            参数合法时返回当前上海时间；参数非法或时区加载失败时返回失败
            outcome。

        Raises:
            无。可预期错误在本边界内转为 ``ToolFailedOutcome``。
        """

        del context
        started_at = _utc_now()
        timezone = _timezone_argument(call.arguments)
        if timezone is None:
            return _failed_outcome(
                started_at=started_at,
                error=_ERROR_INVALID_ARGUMENT,
                message="timezone 参数类型错误：必须是字符串，或省略以使用 Asia/Shanghai。",
                hint=_INVALID_ARGUMENT_HINT,
            )
        if timezone not in _SUPPORTED_TIMEZONES:
            return _failed_outcome(
                started_at=started_at,
                error=_ERROR_INVALID_ARGUMENT,
                message=f"不支持的时区: {timezone}，当前仅支持 {DEFAULT_TIMEZONE}。",
                hint=_INVALID_ARGUMENT_HINT,
            )
        try:
            tzinfo = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            return _failed_outcome(
                started_at=started_at,
                error=_ERROR_TIMEZONE_LOAD_FAILED,
                message=f"无法加载时区: {timezone}。",
                hint="请检查运行环境的 IANA timezone 数据。",
            )
        now = datetime.now(tzinfo)
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value=_time_payload(now=now, timezone=timezone),
                meta=_meta(started_at=started_at),
            )
        )

    return get_current_time


def _get_current_time_parameters() -> ToolParametersSchema:
    """构造 ``get_current_time`` 参数 schema。

    Args:
        无。

    Returns:
        LLM-facing 参数 schema。

    Raises:
        ValueError: schema 字段组合非法时由契约构造抛出。
    """

    return ToolParametersSchema(
        type="object",
        properties={
            _TIMEZONE_ARGUMENT: {
                "type": "string",
                "description": "IANA timezone name. 当前仅支持 Asia/Shanghai。",
                "enum": [DEFAULT_TIMEZONE],
                "default": DEFAULT_TIMEZONE,
            }
        },
        required=(),
        additional_properties=False,
    )


def _timezone_argument(arguments: Mapping[str, JsonValue]) -> str | None:
    """读取并校验 timezone 参数。

    Args:
        arguments: 工具调用参数映射。

    Returns:
        时区名称；缺省时返回 ``Asia/Shanghai``；类型非法时返回 ``None``。

    Raises:
        无。非法类型由调用方转为可恢复的参数错误。
    """

    value = arguments.get(_TIMEZONE_ARGUMENT)
    if value is None:
        return DEFAULT_TIMEZONE
    if not isinstance(value, str):
        return None
    return value.strip()


def _time_payload(*, now: datetime, timezone: str) -> dict[str, JsonValue]:
    """构造当前时间成功载荷。

    Args:
        now: timezone-aware 当前时间。
        timezone: IANA 时区名称。

    Returns:
        包含 ``time``、``timezone``、``weekday``、``iso`` 的 JSON object。

    Raises:
        Exception: 不主动抛出异常。
    """

    return {
        "time": f"{now:%Y}年{now:%m}月{now:%d}日 {now:%H:%M:%S}",
        "timezone": timezone,
        "weekday": _WEEKDAY_NAMES[now.weekday()],
        "iso": now.isoformat(),
    }


def _failed_outcome(
    *,
    started_at: datetime,
    error: str,
    message: str,
    hint: str,
) -> ToolFailedOutcome:
    """构造当前时间工具失败 outcome。

    Args:
        started_at: 工具调用开始时间。
        error: 错误码。
        message: 面向 LLM 的错误说明。
        hint: 可执行恢复提示。

    Returns:
        失败 outcome。

    Raises:
        ValueError: outcome 字段非法时由契约构造抛出。
    """

    return ToolFailedOutcome(
        result=ToolResultFailure(
            ok=False,
            error=error,
            message=message,
            hint=hint,
            meta=_meta(started_at=started_at),
        )
    )


def _utc_now() -> datetime:
    """返回不依赖 IANA timezone 数据的当前 UTC 时间。

    Args:
        无。

    Returns:
        带 UTC 时区信息的当前时间。

    Raises:
        无。
    """

    return datetime.now(timezone.utc)


def _meta(*, started_at: datetime) -> ToolResultMeta:
    """构造工具结果中性元信息。

    Args:
        started_at: 工具调用开始时间。

    Returns:
        工具结果元信息。

    Raises:
        ValueError: 元信息字段非法时由契约构造抛出。
    """

    return ToolResultMeta(
        tool_name=GET_CURRENT_TIME_TOOL_NAME,
        started_at=started_at,
        finished_at=_utc_now(),
    )


def _source_ref() -> ToolBundleSourceRef:
    """构造 utils provider 来源引用。

    Args:
        无。

    Returns:
        工具来源引用。

    Raises:
        ValueError: 来源引用字段非法时由契约构造抛出。
    """

    return ToolBundleSourceRef(
        source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
        source_id=_SOURCE_ID,
        version_ref=_VERSION_REF,
    )
