"""Fins 预处理工具定义。

本模块把 Fins 预处理能力适配为当前 ``ToolDefinition``，负责参数解析、
启动预处理任务并把启动结果交还给上层工具执行框架。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolDefinition, ToolDisplayInfo
from dayu.contracts.tool_execution import AsyncDirectToolExecutionCapability
from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolCancelledOutcome,
    ToolExecutionOutcome,
)
from dayu.contracts.tool_result import ToolResultMeta
from dayu.contracts.tool_schema import ToolFunctionSchema, ToolParametersSchema, ToolSchema
from dayu.fins.domain.enums import SourceKind
from dayu.fins.ingestion_runtime import (
    FinsIngestionRuntime,
    FinsIngestionStartCancelledError,
    FinsPreprocessRequest,
)
from dayu.fins.tools._ingestion_tool_helpers import (
    _awaiting_outcome_from_observation_handle,
    _failed_outcome,
    _optional_bool,
    _optional_text_tuple,
    _required_text,
)

PREPROCESS_TOOL_NAME: Final[str] = "start_fins_preprocess"
_ERROR_INVALID_ARGUMENT: Final[str] = "invalid_argument"
_ERROR_JOB_START_FAILED: Final[str] = "fins_preprocess_start_failed"
_DEFAULT_SOURCE_KIND: Final[SourceKind] = SourceKind.FILING
_CANCELLED_MESSAGE: Final[str] = "Fins preprocess start was cancelled."
_CANCELLED_HINT: Final[str] = (
    "Continue without this Fins preprocess operation unless the user asks to retry."
)


@dataclass(frozen=True)
class FinsPreprocessToolCallable:
    """启动 Fins 预处理 observation 的工具 callable。

    Attributes:
        runtime: Fins shared ingestion runtime。
    """

    runtime: FinsIngestionRuntime

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行单次预处理工具调用。

        Args:
            call: 当前工具调用请求。
            context: 批式工具执行上下文；本工具只观察取消 token。

        Returns:
            参数或启动失败时返回 ``ToolFailedOutcome``；observation 创建成功后
            返回 ``ToolAwaitingOutcome``；启动边界观察到取消时返回
            ``ToolCancelledOutcome``。

        Raises:
            无。工具边界内的启动异常会被归一化为失败 outcome。
        """

        started_at = datetime.now(timezone.utc)
        cancellation_token = context.cancellation_token
        if cancellation_token.is_cancelled():
            return _cancelled_outcome(started_at)
        try:
            request = _preprocess_request_from_arguments(call.arguments)
            handle = self.runtime.prepare_observed_preprocess(
                request,
                cancellation_token=cancellation_token,
            )
        except FinsIngestionStartCancelledError:
            return _cancelled_outcome(started_at)
        except ValueError as exc:
            return _failed_outcome(
                tool_name=PREPROCESS_TOOL_NAME,
                started_at=started_at,
                error=_ERROR_INVALID_ARGUMENT,
                message=str(exc),
                hint="请检查 ticker、source_kind、document_ids、form_types 和 rebuild_processed。",
            )
        except OSError:
            return _failed_outcome(
                tool_name=PREPROCESS_TOOL_NAME,
                started_at=started_at,
                error=_ERROR_JOB_START_FAILED,
                message="预处理任务启动失败，未进入等待状态。",
                hint="请稍后重试，或让系统维护者检查 Fins workspace 存储权限。",
            )
        except Exception:
            return _failed_outcome(
                tool_name=PREPROCESS_TOOL_NAME,
                started_at=started_at,
                error=_ERROR_JOB_START_FAILED,
                message="预处理任务启动失败，未进入等待状态。",
                hint="请确认 Fins workspace 存储目录存在且有写入权限，或联系系统管理员。",
            )
        return _awaiting_outcome_from_observation_handle(handle)


def _cancelled_outcome(started_at: datetime) -> ToolCancelledOutcome:
    """构造预处理启动取消 outcome。

    Args:
        started_at: 工具调用开始时间。

    Returns:
        工具级取消 outcome。

    Raises:
        ValueError: outcome 字段非法时由契约构造抛出。
    """

    finished_at = datetime.now(timezone.utc)
    return ToolCancelledOutcome(
        reason=TOOL_CANCELLED_REASON_HOST_CANCELLED,
        message=_CANCELLED_MESSAGE,
        hint=_CANCELLED_HINT,
        meta=ToolResultMeta(
            tool_name=PREPROCESS_TOOL_NAME,
            started_at=started_at,
            finished_at=finished_at,
        ),
    )


def build_fins_preprocess_tool(runtime: FinsIngestionRuntime) -> ToolDefinition:
    """构造 Fins 预处理 awaiting tool 定义。

    Args:
        runtime: Fins shared ingestion runtime。

    Returns:
        预处理工具定义。

    Raises:
        ValueError: 工具 schema 与名称不一致时由契约构造抛出。
    """

    return ToolDefinition(
        name=PREPROCESS_TOOL_NAME,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=PREPROCESS_TOOL_NAME,
                description=(
                    "处理本地已有的财报源文件，使其可用于章节读取、表格读取和财务数据查询。"
                    "调用后等待工具结果返回；结果会说明选中、处理、跳过和失败的文档数量。"
                ),
                parameters=_preprocess_parameters_schema(),
            ),
        ),
        callable=FinsPreprocessToolCallable(runtime=runtime),
        execution=AsyncDirectToolExecutionCapability(),
        truncate=None,
        display=ToolDisplayInfo(name="Start Fins Preprocess"),
        tags=("fins", "fins-preprocess"),
    )


def _preprocess_parameters_schema() -> ToolParametersSchema:
    """构造预处理工具的 LLM-facing 参数 schema。

    Args:
        无。

    Returns:
        预处理工具参数 schema。

    Raises:
        ValueError: schema 必填字段与属性不一致时由契约构造抛出。
    """

    properties: dict[str, JsonValue] = {
        "ticker": {
            "type": "string",
            "description": "要处理财报的股票代码，可包含交易所后缀。",
        },
        "source_kind": {
            "type": "string",
            "description": "要处理的本地源文件类别。",
            "enum": [SourceKind.FILING.value, SourceKind.MATERIAL.value],
            "default": _DEFAULT_SOURCE_KIND.value,
        },
        "document_ids": {
            "type": "array",
            "description": "可选文档 ID 列表；省略或传空数组表示处理该股票代码下符合条件的本地源文件。",
            "items": {"type": "string"},
        },
        "form_types": {
            "type": "array",
            "description": "可选表单过滤条件，例如 10-K 或 annual-report；省略或传空数组表示不过滤。",
            "items": {"type": "string"},
        },
        "rebuild_processed": {
            "type": "boolean",
            "description": "是否允许重新处理已经处理过的文档；为 false 时会跳过已有处理结果。",
            "default": False,
        },
    }
    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=("ticker",),
        additional_properties=False,
    )


def _preprocess_request_from_arguments(arguments: Mapping[str, JsonValue]) -> FinsPreprocessRequest:
    """从工具参数构造预处理请求。

    Args:
        arguments: 单次工具调用 JSON 参数。

    Returns:
        Fins 预处理请求。

    Raises:
        ValueError: 参数类型或取值非法时抛出。
    """

    return FinsPreprocessRequest(
        ticker=_required_text(arguments, "ticker"),
        source_kind=_optional_source_kind(arguments, "source_kind"),
        document_ids=_optional_text_tuple(arguments, "document_ids"),
        form_types=_optional_text_tuple(arguments, "form_types"),
        rebuild_processed=_optional_bool(arguments, "rebuild_processed", default=False),
    )


def _optional_source_kind(arguments: Mapping[str, JsonValue], field_name: str) -> SourceKind:
    """读取可选 source kind 参数。

    Args:
        arguments: 工具参数。
        field_name: 字段名。

    Returns:
        源文档类型。

    Raises:
        ValueError: 字段存在但不是受支持的 source kind 时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return _DEFAULT_SOURCE_KIND
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    try:
        return SourceKind(value)
    except ValueError as exc:
        allowed = ", ".join(kind.value for kind in SourceKind)
        raise ValueError(f"{field_name} must be one of: {allowed}") from exc
