"""Fins 上传 awaiting tool 定义。

本模块把 Fins shared ingestion runtime 的上传 start 入口适配为当前
``ToolDefinition``。工具只负责参数解析、本地上传路径 allowlist 校验和
durable job 启动，不复制 SEC/CN/HK 上传业务规则，也不等待 Docling 或仓储
长事务完成。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Literal, TypeAlias

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolDefinition, ToolDisplayInfo
from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolCancelledOutcome,
    ToolExecutionOutcome,
)
from dayu.contracts.tool_result import ToolResultMeta
from dayu.contracts.tool_schema import ToolFunctionSchema, ToolParametersSchema, ToolSchema
from dayu.fins.ingestion_runtime import (
    FinsIngestionJobStatus,
    FinsIngestionRuntime,
    FinsIngestionStartCancelledError,
    FinsUploadFilingRequest,
    FinsUploadMaterialRequest,
    FinsUploadRequest,
)
from dayu.fins.tools._ingestion_tool_helpers import (
    _awaiting_outcome_from_job_start,
    _failed_outcome,
    _optional_bool,
    _optional_int,
    _optional_nullable_text,
    _optional_text,
    _optional_text_tuple,
    _required_int,
    _required_text,
)

UPLOAD_TOOL_NAME: Final[str] = "start_fins_upload"
"""Fins upload awaiting tool 的稳定名称。"""

_ERROR_INVALID_ARGUMENT: Final[str] = "invalid_argument"
_ERROR_JOB_START_FAILED: Final[str] = "fins_upload_start_failed"
_DEFAULT_ACTION: Final[str] = "auto"
_UPLOAD_KIND_FILING: Final[str] = "filing"
_UPLOAD_KIND_MATERIAL: Final[str] = "material"
_UPLOAD_ACTION_DELETE: Final[str] = "delete"
_UPLOAD_ACTIONS: Final[frozenset[str]] = frozenset({"auto", "create", "update", "delete"})
_UPLOAD_KINDS: Final[frozenset[str]] = frozenset({_UPLOAD_KIND_FILING, _UPLOAD_KIND_MATERIAL})
_CANCELLED_MESSAGE: Final[str] = "Fins upload start was cancelled by the host."
_CANCELLED_HINT: Final[str] = "Continue without this Fins upload job unless the user asks to retry."

UploadKind: TypeAlias = Literal["filing", "material"]


@dataclass(frozen=True)
class FinsUploadToolCallable:
    """启动 Fins 上传 job 的工具 callable。

    Attributes:
        runtime: Fins shared ingestion runtime。
        allowed_upload_roots: 允许读取上传文件的绝对目录集合。
    """

    runtime: FinsIngestionRuntime
    allowed_upload_roots: tuple[Path, ...]

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行单次上传工具调用。

        Args:
            call: 当前工具调用请求。
            context: 批式工具执行上下文；本工具只观察取消 token。

        Returns:
            参数、路径或启动失败时返回 ``ToolFailedOutcome``；durable job 创建
            成功后返回 ``ToolAwaitingOutcome``；启动边界观察到取消时返回
            ``ToolCancelledOutcome``。

        Raises:
            无。工具边界内的启动异常会被归一化为失败 outcome。
        """

        started_at = datetime.now(timezone.utc)
        cancellation_token = context.cancellation_token
        if cancellation_token.is_cancelled():
            return _cancelled_outcome(started_at)
        try:
            request = _upload_request_from_arguments(
                call.arguments,
                allowed_upload_roots=self.allowed_upload_roots,
            )
            start = self.runtime.start_upload(request, cancellation_token=cancellation_token)
            if start.status in {FinsIngestionJobStatus.CANCELLING, FinsIngestionJobStatus.CANCELLED}:
                return _cancelled_outcome(started_at)
        except FinsIngestionStartCancelledError:
            return _cancelled_outcome(started_at)
        except ValueError as exc:
            return _failed_outcome(
                tool_name=UPLOAD_TOOL_NAME,
                started_at=started_at,
                error=_ERROR_INVALID_ARGUMENT,
                message=str(exc),
                hint="请检查 ticker、upload_kind、action、文件路径、会计期间和材料字段。",
            )
        except OSError:
            return _failed_outcome(
                tool_name=UPLOAD_TOOL_NAME,
                started_at=started_at,
                error=_ERROR_JOB_START_FAILED,
                message="上传任务启动失败，未能保存任务记录。",
                hint="请稍后重试，或让系统维护者检查 Fins workspace 存储权限。",
            )
        except Exception:
            return _failed_outcome(
                tool_name=UPLOAD_TOOL_NAME,
                started_at=started_at,
                error=_ERROR_JOB_START_FAILED,
                message="上传任务启动失败，未进入等待状态。",
                hint="请确认 Fins workspace 存储目录存在且有写入权限，或联系系统管理员。",
            )
        return _awaiting_outcome_from_job_start(start)


def build_fins_upload_tool(
    runtime: FinsIngestionRuntime,
    *,
    allowed_upload_roots: Sequence[Path],
) -> ToolDefinition:
    """构造 Fins 上传 awaiting tool 定义。

    Args:
        runtime: Fins shared ingestion runtime。
        allowed_upload_roots: 允许读取上传文件的绝对目录集合。

    Returns:
        上传工具定义。

    Raises:
        ValueError: allowlist 为空、路径不是绝对路径，或工具 schema 与名称不一致时抛出。
    """

    normalized_roots = _normalize_allowed_upload_roots(allowed_upload_roots)
    return ToolDefinition(
        name=UPLOAD_TOOL_NAME,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=UPLOAD_TOOL_NAME,
                description=(
                    "Start a financial filing or material upload job for one company. "
                    "The tool returns immediately after the upload job is durably "
                    "recorded; it does not wait for file conversion or storage writes "
                    "to finish. Use only for local files that the user has asked to "
                    "ingest into the Fins workspace."
                ),
                parameters=_upload_parameters_schema(),
            ),
        ),
        callable=FinsUploadToolCallable(
            runtime=runtime,
            allowed_upload_roots=normalized_roots,
        ),
        truncate=None,
        display=ToolDisplayInfo(name="Start Fins Upload"),
        tags=("fins", "fins-upload"),
    )


def _cancelled_outcome(started_at: datetime) -> ToolCancelledOutcome:
    """构造上传启动取消 outcome。

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
            tool_name=UPLOAD_TOOL_NAME,
            started_at=started_at,
            finished_at=finished_at,
        ),
    )


def _upload_parameters_schema() -> ToolParametersSchema:
    """构造上传工具的 LLM-facing 参数 schema。

    Args:
        无。

    Returns:
        上传工具参数 schema。

    Raises:
        ValueError: schema 必填字段与属性不一致时由契约构造抛出。
    """

    upload_kind_enum: JsonValue = [_UPLOAD_KIND_FILING, _UPLOAD_KIND_MATERIAL]
    upload_action_enum: JsonValue = list(sorted(_UPLOAD_ACTIONS))
    string_items_schema: JsonValue = {"type": "string"}
    properties: dict[str, JsonValue] = {
        "ticker": {
            "type": "string",
            "description": "Company ticker or exchange-qualified ticker for the uploaded financial document.",
        },
        "upload_kind": {
            "type": "string",
            "description": "Whether the upload is a periodic filing or a supporting material.",
            "enum": upload_kind_enum,
        },
        "action": {
            "type": "string",
            "description": "Upload action. Use auto for normal uploads; delete removes the matching stored source document and must not include files.",
            "enum": upload_action_enum,
            "default": _DEFAULT_ACTION,
        },
        "files": {
            "type": "array",
            "description": "Local file paths to upload. Paths must be under the configured upload roots. Required for auto, create and update; forbidden for delete.",
            "items": string_items_schema,
        },
        "fiscal_year": {
            "type": "integer",
            "description": "Fiscal year. Required for filing uploads; optional for material uploads.",
        },
        "fiscal_period": {
            "type": "string",
            "description": "Fiscal period such as FY, Q1, Q2, Q3 or Q4. Required for filing uploads; optional for material uploads.",
        },
        "form_type": {
            "type": "string",
            "description": "Material form type such as 8-K or MATERIAL_OTHER. Required for material uploads.",
        },
        "material_name": {
            "type": "string",
            "description": "Material display name. Required for material uploads.",
        },
        "document_id": {
            "type": "string",
            "description": "Optional explicit material document id. Omit unless the user supplied a precise stored id.",
        },
        "internal_document_id": {
            "type": "string",
            "description": "Optional explicit material internal document id. Omit unless the user supplied a precise source id.",
        },
        "amended": {
            "type": "boolean",
            "description": "Whether the uploaded document is an amended version.",
            "default": False,
        },
        "filing_date": {
            "type": "string",
            "description": "Optional filing date in YYYY-MM-DD form.",
        },
        "report_date": {
            "type": "string",
            "description": "Optional report date in YYYY-MM-DD form.",
        },
        "company_name": {
            "type": "string",
            "description": "Optional company name to store with upload metadata.",
        },
        "ticker_aliases": {
            "type": "array",
            "description": "Optional company ticker aliases.",
            "items": string_items_schema,
        },
        "overwrite": {
            "type": "boolean",
            "description": "Whether the upload may replace an existing source document.",
            "default": False,
        },
    }
    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=("ticker", "upload_kind"),
        additional_properties=False,
    )


def _upload_request_from_arguments(
    arguments: Mapping[str, JsonValue],
    *,
    allowed_upload_roots: Sequence[Path],
) -> FinsUploadRequest:
    """从工具参数构造上传请求。

    Args:
        arguments: 单次工具调用 JSON 参数。
        allowed_upload_roots: 允许读取上传文件的绝对目录集合。

    Returns:
        Fins 上传请求。

    Raises:
        ValueError: 参数类型、动作、上传类别或文件路径非法时抛出。
    """

    upload_kind = _required_upload_kind(arguments)
    action = _required_upload_action(arguments)
    files = _upload_files_from_arguments(
        arguments,
        action=action,
        allowed_upload_roots=allowed_upload_roots,
    )
    if upload_kind == _UPLOAD_KIND_FILING:
        return FinsUploadFilingRequest(
            ticker=_required_text(arguments, "ticker"),
            action=action,
            files=files,
            fiscal_year=_required_int(arguments, "fiscal_year"),
            fiscal_period=_required_text(arguments, "fiscal_period"),
            amended=_optional_bool(arguments, "amended", default=False),
            filing_date=_optional_nullable_text(arguments, "filing_date"),
            report_date=_optional_nullable_text(arguments, "report_date"),
            company_name=_optional_nullable_text(arguments, "company_name"),
            ticker_aliases=_optional_text_tuple(arguments, "ticker_aliases"),
            overwrite=_optional_bool(arguments, "overwrite", default=False),
        )
    return FinsUploadMaterialRequest(
        ticker=_required_text(arguments, "ticker"),
        action=action,
        files=files,
        form_type=_required_text(arguments, "form_type"),
        material_name=_required_text(arguments, "material_name"),
        document_id=_optional_nullable_text(arguments, "document_id"),
        internal_document_id=_optional_nullable_text(arguments, "internal_document_id"),
        fiscal_year=_optional_int(arguments, "fiscal_year"),
        fiscal_period=_optional_nullable_text(arguments, "fiscal_period"),
        amended=_optional_bool(arguments, "amended", default=False),
        filing_date=_optional_nullable_text(arguments, "filing_date"),
        report_date=_optional_nullable_text(arguments, "report_date"),
        company_name=_optional_nullable_text(arguments, "company_name"),
        ticker_aliases=_optional_text_tuple(arguments, "ticker_aliases"),
        overwrite=_optional_bool(arguments, "overwrite", default=False),
    )


def _required_upload_kind(arguments: Mapping[str, JsonValue]) -> UploadKind:
    """读取上传类别参数。

    Args:
        arguments: 工具参数。

    Returns:
        上传类别。

    Raises:
        ValueError: 上传类别缺失或不受支持时抛出。
    """

    value = _required_text(arguments, "upload_kind").lower()
    if value not in _UPLOAD_KINDS:
        raise ValueError("upload_kind must be filing or material")
    if value == _UPLOAD_KIND_FILING:
        return "filing"
    return "material"


def _required_upload_action(arguments: Mapping[str, JsonValue]) -> str:
    """读取上传动作参数。

    Args:
        arguments: 工具参数。

    Returns:
        规范化上传动作。

    Raises:
        ValueError: 动作不受支持时抛出。
    """

    action = _optional_text(arguments, "action", default=_DEFAULT_ACTION).lower()
    if action not in _UPLOAD_ACTIONS:
        raise ValueError("action must be auto, create, update or delete")
    return action


def _upload_files_from_arguments(
    arguments: Mapping[str, JsonValue],
    *,
    action: str,
    allowed_upload_roots: Sequence[Path],
) -> tuple[Path, ...]:
    """读取并校验上传文件路径。

    Args:
        arguments: 工具参数。
        action: 已规范化上传动作。
        allowed_upload_roots: 允许读取上传文件的绝对目录集合。

    Returns:
        已 resolve 的上传文件路径元组。

    Raises:
        ValueError: 文件参数类型、文件数量、路径位置或文件状态非法时抛出。
    """

    roots = _normalize_allowed_upload_roots(allowed_upload_roots)
    raw_paths = _optional_text_tuple(arguments, "files")
    if action == _UPLOAD_ACTION_DELETE:
        if raw_paths:
            raise ValueError("files must be omitted for delete uploads")
        return ()
    if not raw_paths:
        raise ValueError("files must contain at least one path for auto, create or update uploads")
    return tuple(_resolve_upload_path(raw_path, allowed_upload_roots=roots) for raw_path in raw_paths)


def _normalize_allowed_upload_roots(allowed_upload_roots: Sequence[Path]) -> tuple[Path, ...]:
    """规范化 provider 配置的上传 allowlist 根目录。

    Args:
        allowed_upload_roots: 原始 allowlist 路径集合。

    Returns:
        已 resolve 的绝对路径元组。

    Raises:
        ValueError: allowlist 为空或含非绝对路径时抛出。
    """

    normalized: list[Path] = []
    for root in allowed_upload_roots:
        expanded = root.expanduser()
        if not expanded.is_absolute():
            raise ValueError("allowed_upload_roots must contain only absolute paths")
        normalized.append(expanded.resolve(strict=False))
    if not normalized:
        raise ValueError("allowed_upload_roots must contain at least one absolute path")
    return tuple(normalized)


def _resolve_upload_path(
    raw_path: str,
    *,
    allowed_upload_roots: Sequence[Path],
) -> Path:
    """解析并校验单个上传文件路径。

    Args:
        raw_path: 工具参数中的路径文本。
        allowed_upload_roots: 已规范化的 allowlist 根目录。

    Returns:
        已 resolve 的文件路径。

    Raises:
        ValueError: 路径不在 allowlist 内或不是普通文件时抛出。
    """

    candidate = Path(raw_path).expanduser().resolve(strict=False)
    if not any(candidate.is_relative_to(root) for root in allowed_upload_roots):
        raise ValueError("upload file path is outside allowed upload roots")
    if not candidate.is_file():
        raise ValueError("upload file path must point to an existing file")
    if candidate.stat().st_size <= 0:
        raise ValueError("upload file path must point to a non-empty file")
    return candidate


__all__ = [
    "FinsUploadToolCallable",
    "UPLOAD_TOOL_NAME",
    "build_fins_upload_tool",
]
