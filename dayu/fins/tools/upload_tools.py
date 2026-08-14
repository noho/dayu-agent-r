"""Fins 上传工具定义。

本模块把 Fins 上传能力适配为当前 ``ToolDefinition``，负责参数解析、
本地上传文件形态校验和上传任务启动，不复制 SEC/CN/HK 上传业务规则。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Literal, TypeAlias

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
from dayu.fins.ingestion_runtime import (
    FinsIngestionRuntime,
    FinsIngestionStartCancelledError,
    FinsUploadFilingRequest,
    FinsUploadMaterialRequest,
    FinsUploadRequest,
)
from dayu.fins.tools._ingestion_tool_helpers import (
    _awaiting_outcome_from_observation_handle,
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
_CANCELLED_MESSAGE: Final[str] = "财报上传任务启动已停止。"
_CANCELLED_HINT: Final[str] = "当前工具调用已停止；如仍需要该结果，请等待用户确认后再重新发起。"

UploadKind: TypeAlias = Literal["filing", "material"]


@dataclass(frozen=True)
class FinsUploadToolCallable:
    """启动 Fins 上传 observation 的工具 callable。

    Attributes:
        runtime: Fins shared ingestion runtime。
    """

    runtime: FinsIngestionRuntime

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
            参数、路径或启动失败时返回 ``ToolFailedOutcome``；observation 创建
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
            request = _upload_request_from_arguments(call.arguments)
            handle = self.runtime.prepare_observed_upload(
                request,
                cancellation_token=cancellation_token,
            )
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
                message="上传任务未能启动。",
                hint="请稍后重试，或让系统维护者检查 Fins workspace 存储权限。",
            )
        except Exception:
            return _failed_outcome(
                tool_name=UPLOAD_TOOL_NAME,
                started_at=started_at,
                error=_ERROR_JOB_START_FAILED,
                message="上传任务未能启动。",
                hint="请确认 Fins workspace 存储目录存在且有写入权限，或联系系统管理员。",
            )
        return _awaiting_outcome_from_observation_handle(handle)


def build_fins_upload_tool(runtime: FinsIngestionRuntime) -> ToolDefinition:
    """构造 Fins 上传 awaiting tool 定义。

    Args:
        runtime: Fins shared ingestion runtime。

    Returns:
        上传工具定义。

    Raises:
        ValueError: 工具 schema 与名称不一致时由契约构造抛出。
    """

    return ToolDefinition(
        name=UPLOAD_TOOL_NAME,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=UPLOAD_TOOL_NAME,
                description=(
                    "为一家公司上传本地财报文件或补充材料。调用后等待工具结果返回；"
                    "结果会说明上传、删除、转换或失败情况。仅在用户明确要求使用本地文件补充财报资料时调用。"
                ),
                parameters=_upload_parameters_schema(),
            ),
        ),
        callable=FinsUploadToolCallable(runtime=runtime),
        execution=AsyncDirectToolExecutionCapability(),
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
            "description": (
                "公司财报归档的 canonical ticker，只填写一个股票代码，不要填写 CSV；"
                "可包含系统支持的市场或交易所前后缀。"
            ),
        },
        "upload_kind": {
            "type": "string",
            "description": "上传文件类别：定期财报 filing，或补充材料 material。",
            "enum": upload_kind_enum,
        },
        "action": {
            "type": "string",
            "description": "上传动作。普通上传使用 auto；delete 表示删除匹配的已存源文件，且不能同时提供 files。",
            "enum": upload_action_enum,
            "default": _DEFAULT_ACTION,
        },
        "files": {
            "type": "array",
            "description": "要上传的本地文件路径列表。每个路径必须指向已存在、非空的普通文件；auto、create、update 必填，delete 禁止提供。",
            "items": string_items_schema,
        },
        "fiscal_year": {
            "type": "integer",
            "description": "财年。上传 filing 时必填，且只接受 1000..9999 的整数；上传 material 时可选。",
        },
        "fiscal_period": {
            "type": "string",
            "description": "财报期间，例如 FY、Q1、Q2、Q3 或 Q4。上传 filing 时必填；上传 material 时可选。",
        },
        "form_type": {
            "type": "string",
            "description": "补充材料类型，例如 8-K 或 MATERIAL_OTHER。上传 material 时必填。",
        },
        "material_name": {
            "type": "string",
            "description": "补充材料显示名称。上传 material 时必填。",
        },
        "document_id": {
            "type": "string",
            "description": "可选的补充材料文档 ID。只有用户明确提供已存文档 ID 时才填写。",
        },
        "internal_document_id": {
            "type": "string",
            "description": "可选的补充材料内部源文件 ID。只有用户明确提供精确源文件 ID 时才填写。",
        },
        "amended": {
            "type": "boolean",
            "description": "上传文件是否为修订版本。",
            "default": False,
        },
        "filing_date": {
            "type": "string",
            "description": "可选披露日期。上传 filing 时若填写，必须是实际存在的 YYYY-MM-DD 日期；文本不会自动去除空白，空串、纯空白或首尾空白均非法。",
        },
        "report_date": {
            "type": "string",
            "description": "可选报告期日期。上传 filing 时若填写，必须是实际存在的 YYYY-MM-DD 日期；文本不会自动去除空白，空串、纯空白或首尾空白均非法。",
        },
        "company_name": {
            "type": "string",
            "description": "可选公司名称，用于随上传元数据保存。",
        },
        "ticker_aliases": {
            "type": "array",
            "description": (
                "可选的同公司 ticker 别名数组，filing 与 material 上传都适用。每项都是用户明确声明的"
                "同公司查询代码；系统信任声明且不联网核验。公司元数据成功保存后，canonical ticker 与"
                "这些别名查询同一财报归档；不要重复填写 canonical 的等价写法。"
            ),
            "items": string_items_schema,
        },
        "overwrite": {
            "type": "boolean",
            "description": "是否允许本次上传替换已有源文件。",
            "default": False,
        },
    }
    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=("ticker", "upload_kind"),
        additional_properties=False,
    )


def _upload_request_from_arguments(arguments: Mapping[str, JsonValue]) -> FinsUploadRequest:
    """从工具参数构造上传请求。

    Args:
        arguments: 单次工具调用 JSON 参数。

    Returns:
        Fins 上传请求。

    Raises:
        ValueError: 参数类型、动作、上传类别或文件路径非法时抛出。
    """

    upload_kind = _required_upload_kind(arguments)
    action = _required_upload_action(arguments)
    files = _upload_files_from_arguments(arguments, action=action)
    if upload_kind == _UPLOAD_KIND_FILING:
        return FinsUploadFilingRequest(
            ticker=_required_text(arguments, "ticker"),
            action=action,
            files=files,
            fiscal_year=_required_int(arguments, "fiscal_year"),
            fiscal_period=_required_text(arguments, "fiscal_period"),
            amended=_optional_bool(arguments, "amended", default=False),
            filing_date=_optional_raw_nullable_text(arguments, "filing_date"),
            report_date=_optional_raw_nullable_text(arguments, "report_date"),
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


def _optional_raw_nullable_text(
    arguments: Mapping[str, JsonValue],
    key: str,
) -> str | None:
    """读取 filing 分支需保留原始形态的可选文本。

    Args:
        arguments: 工具参数。
        key: 待读取的参数名。

    Returns:
        参数缺失或为 ``null`` 时返回 ``None``；字符串按原样返回。

    Raises:
        ValueError: 参数存在且不是字符串时抛出。
    """

    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string or null")
    return value


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
) -> tuple[Path, ...]:
    """读取并校验上传文件路径。

    Args:
        arguments: 工具参数。
        action: 已规范化上传动作。

    Returns:
        已 resolve 的上传文件路径元组。

    Raises:
        ValueError: 文件参数类型、文件数量或文件状态非法时抛出。
    """

    raw_paths = _optional_text_tuple(arguments, "files")
    if action == _UPLOAD_ACTION_DELETE:
        if raw_paths:
            raise ValueError("files must be omitted for delete uploads")
        return ()
    if not raw_paths:
        raise ValueError("files must contain at least one path for auto, create or update uploads")
    return tuple(_resolve_upload_file_path(raw_path) for raw_path in raw_paths)


def _resolve_upload_file_path(raw_path: str) -> Path:
    """解析并校验单个上传文件路径。

    Args:
        raw_path: 工具参数中的路径文本。

    Returns:
        已 resolve 的文件路径。

    Raises:
        ValueError: 路径不是普通文件或文件为空时抛出。
    """

    candidate = Path(raw_path).expanduser().resolve(strict=False)
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
