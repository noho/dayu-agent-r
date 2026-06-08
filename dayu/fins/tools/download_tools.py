"""Fins 下载 awaiting tool 定义。

本模块把 Fins shared ingestion runtime 的下载 start 入口适配为当前
``ToolDefinition``。工具只启动 durable job 并返回等待 outcome，不轮询
job 完成状态，也不暴露 Host 内部治理字段或 job record 文件路径。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolDefinition, ToolDisplayInfo
from dayu.contracts.tool_outcome import ToolExecutionOutcome
from dayu.contracts.tool_schema import ToolFunctionSchema, ToolParametersSchema, ToolSchema
from dayu.fins.ingestion_runtime import FinsDownloadRequest, FinsIngestionRuntime
from dayu.fins.tools._ingestion_tool_helpers import (
    _awaiting_outcome_from_job_start,
    _failed_outcome,
    _optional_bool,
    _optional_nullable_text,
    _optional_text,
    _optional_text_tuple,
    _required_text,
)

DOWNLOAD_TOOL_NAME: Final[str] = "start_fins_download"
_ERROR_INVALID_ARGUMENT: Final[str] = "invalid_argument"
_ERROR_JOB_START_FAILED: Final[str] = "fins_download_start_failed"
_DEFAULT_SOURCE: Final[str] = "auto"


@dataclass(frozen=True)
class FinsDownloadToolCallable:
    """启动 Fins 下载 job 的工具 callable。

    Attributes:
        runtime: Fins shared ingestion runtime。
    """

    runtime: FinsIngestionRuntime

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行单次下载工具调用。

        Args:
            call: 当前工具调用请求。
            context: 批式工具执行上下文；本工具不消费其中的 Host 治理字段。

        Returns:
            参数或启动失败时返回 ``ToolFailedOutcome``；durable job 创建成功后
            返回 ``ToolAwaitingOutcome``。

        Raises:
            无。工具边界内的启动异常会被归一化为失败 outcome。
        """

        del context
        started_at = datetime.now(timezone.utc)
        try:
            request = _download_request_from_arguments(call.arguments)
            start = self.runtime.start_download(request)
        except ValueError as exc:
            return _failed_outcome(
                tool_name=DOWNLOAD_TOOL_NAME,
                started_at=started_at,
                error=_ERROR_INVALID_ARGUMENT,
                message=str(exc),
                hint="请检查 ticker、source、表单类型、日期过滤和布尔参数。",
            )
        except OSError:
            return _failed_outcome(
                tool_name=DOWNLOAD_TOOL_NAME,
                started_at=started_at,
                error=_ERROR_JOB_START_FAILED,
                message="下载任务未能创建 durable job record。",
                hint="请稍后重试，或让系统维护者检查 Fins workspace 存储权限。",
            )
        except Exception:
            return _failed_outcome(
                tool_name=DOWNLOAD_TOOL_NAME,
                started_at=started_at,
                error=_ERROR_JOB_START_FAILED,
                message="下载任务启动失败，未进入等待状态。",
                hint="请检查输入参数和 Fins ingestion runtime 配置。",
            )
        return _awaiting_outcome_from_job_start(start)


def build_fins_download_tool(runtime: FinsIngestionRuntime) -> ToolDefinition:
    """构造 Fins 下载 awaiting tool 定义。

    Args:
        runtime: Fins shared ingestion runtime。

    Returns:
        下载工具定义。

    Raises:
        ValueError: 工具 schema 与名称不一致时由契约构造抛出。
    """

    return ToolDefinition(
        name=DOWNLOAD_TOOL_NAME,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=DOWNLOAD_TOOL_NAME,
                description=(
                    "Start a financial filing download job for one company. "
                    "The tool returns immediately with an external-job wait state "
                    "after the job is durably recorded; it does not wait for the "
                    "download to finish. Use this when source filings must be "
                    "ingested into the Fins workspace before reading or processing."
                ),
                parameters=_download_parameters_schema(),
            ),
        ),
        callable=FinsDownloadToolCallable(runtime=runtime),
        truncate=None,
        display=ToolDisplayInfo(name="Start Fins Download"),
        tags=("fins", "fins-download"),
    )


def _download_parameters_schema() -> ToolParametersSchema:
    """构造下载工具的 LLM-facing 参数 schema。

    Args:
        无。

    Returns:
        下载工具参数 schema。

    Raises:
        ValueError: schema 必填字段与属性不一致时由契约构造抛出。
    """

    properties: dict[str, JsonValue] = {
        "ticker": {
            "type": "string",
            "description": "Company ticker or exchange-qualified ticker to download, for example AAPL or 00700.HK.",
        },
        "source": {
            "type": "string",
            "description": "Financial filing source selector. Use auto unless the user explicitly names a supported source.",
            "default": _DEFAULT_SOURCE,
        },
        "form_types": {
            "type": "array",
            "description": "Optional filing form filters such as 10-K, 10-Q or annual-report. Omit or pass an empty list for all supported forms.",
            "items": {"type": "string"},
        },
        "filed_after": {
            "type": "string",
            "description": "Optional inclusive filing-date lower bound in YYYY-MM-DD form.",
        },
        "filed_before": {
            "type": "string",
            "description": "Optional inclusive filing-date upper bound in YYYY-MM-DD form.",
        },
        "overwrite_existing": {
            "type": "boolean",
            "description": "Whether downloaded source documents may replace existing source documents with the same id.",
            "default": False,
        },
        "rebuild_processed": {
            "type": "boolean",
            "description": "Whether existing processed outputs for replaced documents should be marked for rebuilding.",
            "default": False,
        },
    }
    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=("ticker",),
        additional_properties=False,
    )


def _download_request_from_arguments(arguments: Mapping[str, JsonValue]) -> FinsDownloadRequest:
    """从工具参数构造下载请求。

    Args:
        arguments: 单次工具调用 JSON 参数。

    Returns:
        Fins 下载请求。

    Raises:
        ValueError: 参数类型或取值非法时抛出。
    """

    return FinsDownloadRequest(
        ticker=_required_text(arguments, "ticker"),
        source=_optional_text(arguments, "source", default=_DEFAULT_SOURCE),
        form_types=_optional_text_tuple(arguments, "form_types"),
        filed_after=_optional_nullable_text(arguments, "filed_after"),
        filed_before=_optional_nullable_text(arguments, "filed_before"),
        overwrite_existing=_optional_bool(arguments, "overwrite_existing", default=False),
        rebuild_processed=_optional_bool(arguments, "rebuild_processed", default=False),
    )
