"""Fins read tools 的 current 原生定义。

本模块把 ``FinsReadRuntime`` 的十三个只读能力暴露为当前
``ToolDefinition`` / ``ToolCallable``。工具声明、参数校验、取消 outcome
和异常投影都在本模块完成；财报文件读取仍只通过 read runtime 进入
``dayu.fins.storage`` 仓储边界。
"""

from __future__ import annotations

from dayu.fins.cancellation import FinsReadCancelledError

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolDefinition, tool
from dayu.contracts.tool_execution import (
    ProcessBackedToolContext,
    ProcessBackedToolExecutionCapability,
    process_tool_completed_envelope,
    process_tool_failed_envelope,
)
from dayu.contracts.tool_outcome import ToolExecutionOutcome
from dayu.contracts.tool_schema import (
    ToolParametersSchema,
    ToolTruncateSpec,
    ToolTruncationStrategy,
)
from dayu.fins._log import Log
from dayu.fins.domain.filing_semantics import FISCAL_PERIODS
from dayu.fins.domain.enums import SourceKind
from dayu.fins.domain.original_read_contract import ExpandedName, TEXT_PAGE_DEFAULT, TEXT_PAGE_MAX, STRUCTURE_PAGE_DEFAULT, STRUCTURE_PAGE_MAX, FACT_PAGE_DEFAULT, FACT_PAGE_MAX, CONCEPTS_MAX
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.tools.fins_limits import FinsToolLimits
from dayu.runtime.tool_call_projection import (
    ToolArgumentValidationFailure,
    completed_outcome,
    failed_outcome,
    host_cancelled_outcome,
    validate_and_project_arguments,
)

from .read_runtime import FinsReadRuntime
from .read_runtime_helpers import (
    FinsReadArgumentError,
    FinsReadBusinessError,
)
from .result_types import (
    financial_statement_result_description,
    xbrl_query_result_description,
)

MODULE: Final[str] = "FINS.FINS_TOOLS"
FINS_TOOL_TAGS: Final[tuple[str, ...]] = ("fins", "fins-read")

LIST_DOCUMENTS_TOOL_NAME: Final[str] = "list_documents"
GET_DOCUMENT_SECTIONS_TOOL_NAME: Final[str] = "get_document_sections"
READ_SECTION_TOOL_NAME: Final[str] = "read_section"
SEARCH_DOCUMENT_TOOL_NAME: Final[str] = "search_document"
LIST_TABLES_TOOL_NAME: Final[str] = "list_tables"
GET_TABLE_TOOL_NAME: Final[str] = "get_table"
GET_PAGE_CONTENT_TOOL_NAME: Final[str] = "get_page_content"
GET_FINANCIAL_STATEMENT_TOOL_NAME: Final[str] = "get_financial_statement"
QUERY_XBRL_FACTS_TOOL_NAME: Final[str] = "query_xbrl_facts"
_ORIGINAL_TOOL_NAMES: Final[tuple[str, ...]] = ("list_document_assets", "read_original_text", "read_original_structure", "query_original_facts")

FINS_READ_TOOL_NAMES: Final[tuple[str, ...]] = (
    LIST_DOCUMENTS_TOOL_NAME,
    GET_DOCUMENT_SECTIONS_TOOL_NAME,
    READ_SECTION_TOOL_NAME,
    SEARCH_DOCUMENT_TOOL_NAME,
    LIST_TABLES_TOOL_NAME,
    GET_TABLE_TOOL_NAME,
    GET_PAGE_CONTENT_TOOL_NAME,
    GET_FINANCIAL_STATEMENT_TOOL_NAME,
    QUERY_XBRL_FACTS_TOOL_NAME,
    *_ORIGINAL_TOOL_NAMES,
)

_INVALID_ARGUMENT_HINT: Final[str] = "Fix arguments to match the tool schema and retry."
_FILE_NOT_FOUND_HINT: Final[str] = "Verify the ticker, document_id, ref, or table_ref and retry."
_UNEXPECTED_FAILURE_HINT: Final[str] = "Inspect provider diagnostics or retry with narrower arguments."
_FINS_CANCELLED_HINT: Final[str] = "当前工具调用已停止；如仍需要该结果，请等待用户确认后再重新发起。"
_PROCESS_RUNTIME_CLOSE_FOLLOW_UP_ACTION: Final[str] = "runtime.close.follow_up"

_BusinessCall = Callable[[CancellationToken], JsonValue]


def _follow_up_process_runtime_close(runtime: DefaultFinsRuntime) -> None:
    """在首次关闭失败后再消费一次公共幂等 cleanup authority。

    Args:
        runtime: process target 本次创建的默认 Fins runtime。

    Returns:
        无。

    Raises:
        无；二次失败只记录 path-free 结构化诊断。
    """

    try:
        runtime.close()
    except Exception as close_error:
        errno_value = (
            str(close_error.errno) if isinstance(close_error, OSError) and close_error.errno is not None else "none"
        )
        Log.warning(
            f"action={_PROCESS_RUNTIME_CLOSE_FOLLOW_UP_ACTION} type={type(close_error).__name__} errno={errno_value}",
            module=MODULE,
        )


def build_fins_read_tool_definitions(
    read_runtime: FinsReadRuntime,
    workspace_root: Path,
    limits: FinsToolLimits,
) -> tuple[ToolDefinition, ...]:
    """构造十三个原生 Fins read 工具定义。

    Args:
        read_runtime: 通过 ``DefaultFinsRuntime`` 获取的 read runtime。
        workspace_root: Fins workspace root；用于构造 process-backed 子进程
            target factory，不得从 read runtime 私有仓储对象反推。
        limits: Fins read 工具限制配置。

    Returns:
        按稳定顺序排列的 current ``ToolDefinition`` 元组。

    Raises:
        ValueError: 工具定义构造出的名称顺序不符合 Fins provider 约定时抛出。
    """

    provider_lock = asyncio.Lock()
    process_target_factory = _FinsReadProcessTargetFactory(
        workspace_root_locator=str(workspace_root.expanduser().resolve(strict=False)),
        limits=limits,
    )
    definitions = (
        _build_list_documents_definition(read_runtime, limits, provider_lock, process_target_factory),
        _build_get_document_sections_definition(read_runtime, limits, provider_lock, process_target_factory),
        _build_read_section_definition(read_runtime, limits, provider_lock, process_target_factory),
        _build_search_document_definition(read_runtime, limits, provider_lock, process_target_factory),
        _build_list_tables_definition(read_runtime, limits, provider_lock, process_target_factory),
        _build_get_table_definition(read_runtime, limits, provider_lock, process_target_factory),
        _build_get_page_content_definition(read_runtime, limits, provider_lock, process_target_factory),
        _build_get_financial_statement_definition(read_runtime, limits, provider_lock, process_target_factory),
        _build_query_xbrl_facts_definition(read_runtime, limits, provider_lock, process_target_factory),
        *(_build_original_definition(name, read_runtime, limits, provider_lock, process_target_factory) for name in _ORIGINAL_TOOL_NAMES),
    )
    names = tuple(definition.name for definition in definitions)
    if names != FINS_READ_TOOL_NAMES:
        raise ValueError(f"fins provider expected tools {FINS_READ_TOOL_NAMES}, got {names}")
    Log.verbose(f"已注册 {len(definitions)} 个财报读取工具", module=MODULE)
    return definitions


class _FinsProcessCancellationToken:
    """Fins process target 内部使用的不可取消 token。

    子进程不共享 Host cancellation token；生产取消、超时和 hard kill 由父进程
    ToolRuntime process capsule 独占治理。本 token 只满足 read runtime 的
    类型边界，避免子进程伪造 host_cancelled / timeout 结果。
    """

    def is_cancelled(self) -> bool:
        """返回当前是否已取消。

        Args:
            无。

        Returns:
            始终返回 ``False``。

        Raises:
            无。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        Args:
            无。

        Returns:
            始终返回 ``None``。

        Raises:
            无。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        Args:
            无。

        Returns:
            始终返回 ``None``。

        Raises:
            无。
        """

        return None


class _FinsReadBusinessFailure(Exception):
    """Fins read 同步业务路由的可恢复失败。

    Args:
        error: current failure 错误码。
        message: 面向 LLM 的错误说明。
        hint: 可选恢复提示。

    Raises:
        无。
    """

    def __init__(self, error: str, message: str, hint: str | None) -> None:
        """初始化业务失败。

        Args:
            error: current failure 错误码。
            message: 面向 LLM 的错误说明。
            hint: 可选恢复提示。

        Returns:
            无。

        Raises:
            无。
        """

        self.error = error
        self.message = message
        self.hint = hint
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class _FinsReadProcessTarget:
    """Fins read process-backed 子进程目标。

    本目标只保存 spawn 可序列化的 workspace locator、工具名、参数 JSON
    副本、limit 配置和 timeout 标量；不得捕获 read runtime、repository、
    processor cache、provider lock、CancellationToken、session 或 Host
    内部对象。

    Args:
        workspace_root_locator: Fins workspace root 字符串 locator。
        tool_name: 工具名。
        arguments: 工具调用参数 JSON 副本。
        limits: Fins 工具限制配置。
        timeout_seconds: 父进程投影的批级 timeout 标量；真实 timeout 由父进程
            Host capsule 独占治理。

    Returns:
        dataclass 实例。

    Raises:
        无。
    """

    workspace_root_locator: str
    tool_name: str
    arguments: dict[str, JsonValue]
    limits: FinsToolLimits
    timeout_seconds: float | None

    def __call__(self) -> JsonValue:
        """在子进程内重建 Fins runtime 并执行只读业务。

        Args:
            无。

        Returns:
            ``completed`` 或 ``failed`` JSON 信封；不会返回 awaiting、
            cancelled、timeout 或 host_cancelled。

        Raises:
            无；未预期异常会被转换为 failed 信封。
        """

        _ = self.timeout_seconds
        call = ToolCallRequest(
            tool_call_id=f"process-{self.tool_name}",
            name=self.tool_name,
            arguments=self.arguments,
            index_in_iteration=0,
            provider_state=None,
        )
        runtime: DefaultFinsRuntime | None = None
        outcome: JsonValue
        primary_failed = False
        try:
            runtime = DefaultFinsRuntime.create(workspace_root=Path(self.workspace_root_locator))
            read_runtime = runtime.get_read_runtime(processor_cache_max_entries=self.limits.processor_cache_max_entries)
            value = _execute_fins_read_business_value(
                tool_name=self.tool_name,
                call=call,
                parameters=_parameters_for_tool(self.tool_name),
                read_runtime=read_runtime,
                limits=self.limits,
                cancellation_token=_FinsProcessCancellationToken(),
            )
            outcome = process_tool_completed_envelope(value)
        except _FinsReadBusinessFailure as failure:
            primary_failed = True
            outcome = _process_failed_envelope(failure)
        except Exception:
            primary_failed = True
            outcome = process_tool_failed_envelope(
                error_type="execution_error",
                message=f"Tool {self.tool_name!r} execution failed.",
                hint=_UNEXPECTED_FAILURE_HINT,
            )
        finally:
            if runtime is not None:
                try:
                    runtime.close()
                except Exception:
                    if not primary_failed:
                        outcome = process_tool_failed_envelope(
                            error_type="execution_error",
                            message=f"Tool {self.tool_name!r} execution failed.",
                            hint=_UNEXPECTED_FAILURE_HINT,
                        )
                    _follow_up_process_runtime_close(runtime)
        return outcome


@dataclass(frozen=True, slots=True)
class _FinsReadProcessTargetFactory:
    """Fins read process-backed target factory。

    本 factory 只保存 spawn 可序列化的 workspace locator 与 limit 配置，不
    捕获 read runtime、repository、processor cache、provider lock、
    CancellationToken、session 或 Host 内部对象。

    Args:
        workspace_root_locator: Fins workspace root 字符串 locator。
        limits: Fins 工具限制配置。

    Returns:
        dataclass 实例。

    Raises:
        无。
    """

    workspace_root_locator: str
    limits: FinsToolLimits

    def build_process_target(
        self,
        call: ToolCallRequest,
        context: ProcessBackedToolContext,
    ) -> _FinsReadProcessTarget:
        """构造可序列化 Fins read 子进程目标。

        Args:
            call: 单次工具调用请求。
            context: Host 投影出的可序列化 process-backed 上下文。

        Returns:
            Fins read 子进程目标。

        Raises:
            无。
        """

        return _FinsReadProcessTarget(
            workspace_root_locator=self.workspace_root_locator,
            tool_name=call.name,
            arguments=dict(call.arguments),
            limits=self.limits,
            timeout_seconds=context.timeout_seconds,
        )


def _build_list_documents_definition(
    read_runtime: FinsReadRuntime,
    limits: FinsToolLimits,
    provider_lock: asyncio.Lock,
    process_target_factory: _FinsReadProcessTargetFactory,
) -> ToolDefinition:
    """构造 ``list_documents`` 工具定义。

    Args:
        read_runtime: Fins read runtime。
        limits: 工具限制配置。
        provider_lock: provider 级共享执行锁。
        process_target_factory: process-backed 目标工厂。

    Returns:
        current 工具定义。

    Raises:
        Exception: 工具声明契约构造失败时透出。
    """

    parameters = _list_documents_parameters()

    @tool(
        name=LIST_DOCUMENTS_TOOL_NAME,
        description="列出公司可用文档。先用本工具拿到 document_id，再继续读章节、表格或财务数据。推荐槽位只提供文档 ID 引用；材料当前修订事实见 documents 中 published_amended 是当前发布材料的修订布尔值，例如 {\"source_kind\":\"material\",\"published_amended\":true}。",
        parameters=parameters,
        execution=ProcessBackedToolExecutionCapability(
            target_factory=process_target_factory,
        ),
        tags=FINS_TOOL_TAGS,
        display_name="列出文档",
        truncate=_list_truncate(limits.list_documents_max_items, "documents"),
    )
    async def list_documents(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 ``list_documents`` 工具调用。

        Args:
            call: 单次工具调用请求。
            context: 批式执行上下文。

        Returns:
            工具执行 outcome。

        Raises:
            无；业务异常会在本边界投影为 failed / cancelled outcome。
        """

        started_at = datetime.now(UTC)
        return await _invoke_fins_read_business(
            tool_name=LIST_DOCUMENTS_TOOL_NAME,
            context=context,
            provider_lock=provider_lock,
            started_at=started_at,
            business_call=lambda token: _execute_fins_read_business_value(
                tool_name=LIST_DOCUMENTS_TOOL_NAME,
                call=call,
                parameters=parameters,
                read_runtime=read_runtime,
                limits=limits,
                cancellation_token=token,
            ),
        )

    return list_documents


def _build_get_document_sections_definition(
    read_runtime: FinsReadRuntime,
    limits: FinsToolLimits,
    provider_lock: asyncio.Lock,
    process_target_factory: _FinsReadProcessTargetFactory,
) -> ToolDefinition:
    """构造 ``get_document_sections`` 工具定义。

    Args:
        read_runtime: Fins read runtime。
        limits: 工具限制配置。
        provider_lock: provider 级共享执行锁。
        process_target_factory: process-backed 目标工厂。

    Returns:
        current 工具定义。

    Raises:
        Exception: 工具声明契约构造失败时透出。
    """

    parameters = _ticker_document_parameters()

    @tool(
        name=GET_DOCUMENT_SECTIONS_TOOL_NAME,
        description="读取文档章节结构，返回可定位的章节 ref 列表。",
        parameters=parameters,
        execution=ProcessBackedToolExecutionCapability(
            target_factory=process_target_factory,
        ),
        tags=FINS_TOOL_TAGS,
        display_name="浏览财报结构",
        truncate=_list_truncate(limits.get_document_sections_max_items, "sections"),
    )
    async def get_document_sections(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 ``get_document_sections`` 工具调用。

        Args:
            call: 单次工具调用请求。
            context: 批式执行上下文。

        Returns:
            工具执行 outcome。

        Raises:
            无；业务异常会在本边界投影为 failed / cancelled outcome。
        """

        started_at = datetime.now(UTC)
        return await _invoke_fins_read_business(
            tool_name=GET_DOCUMENT_SECTIONS_TOOL_NAME,
            context=context,
            provider_lock=provider_lock,
            started_at=started_at,
            business_call=lambda token: _execute_fins_read_business_value(
                tool_name=GET_DOCUMENT_SECTIONS_TOOL_NAME,
                call=call,
                parameters=parameters,
                read_runtime=read_runtime,
                limits=limits,
                cancellation_token=token,
            ),
        )

    return get_document_sections


_ORIGINAL_DESCRIPTION: Final[
    str
] = """先 list_documents 取得 exact document_id，再 list_document_assets 选文件。
资产 asset 必含 ticker/document_id/source_kind/filename/sha256/size_bytes；filename 为资产名，sha256 只是后续原样传回的内容校验标签，不是业务事实。
枚举返回 assets 数组、reading_primary_filename；每项必有 asset、is_reading_primary、role_status(recorded/unrecorded)、source_role/original_filename/derived_from/content_type(字符串或 null)、text_supported/structure_supported/inline_facts_supported(布尔)。阅读 primary 不保证是原始提交主件。
所有 span 必含 asset/start/end；start/end 为严格 UTF-8 解码且仅去开头 BOM 后的 Unicode 码点，0 基左闭右开，不是字节或渲染坐标。预览必含 span/preview/preview_complete；false 时沿 span 分页 read_original_text 取齐。
文本返回 asset、encoding(utf-8)、bom_bytes(0/3)、requested_range、returned_range、total_chars、text、truncated、next_start(整数或 null)。truncated 只表示请求范围尚未读完，局部范围完成不代表全文完成。
结构返回 asset/encoding/bom_bytes/requested_range/total_chars、nodes、total_matches、truncated、next_start、parse_status(complete/partial)、diagnostics(reason/span 数组)、diagnostics_complete。nodes 按原文起点选择；每项必含 kind(element/text/comment/doctype/cdata/processing_instruction)、order、qname(原 raw/namespace_uri/local_name/status 及各自 raw_complete/namespace_uri_complete/local_name_complete 布尔，未取齐时按 opening 回读，或不适用为 null)、opening/content/closing(span 或不适用为 null)、closure(explicit/void/rule/unknown/token)、parent、parent_status(root/resolved/unknown；unknown 的 parent=null 不表示根)、ancestors(span 数组)、ancestors_complete、attributes、attributes_complete、preview、continuation。属性保序，含 name/span/value(原值预览或 null)/quote/duplicate；xmlns 属性可用于发现定义处 URI，局部重绑定须按父链检查，属性未取齐用 opening span 回读。
facts 返回 asset/facts/total_matches/truncated/next_offset(整数或 null)/parse_status/diagnostics/diagnostics_complete。每项必含 node、name/format(QName 或 null)、raw_value/context_ref/target_raw/xml_lang/xsi_nil/escape/continued_at(原值预览或 null)、target_origin(explicit/implicit_default)、context、visibility。引用 context/continuation 必含 status(resolved/unresolved/ambiguous/absent)、reason(字符串或 null)、target(预览或 null)，context 解析成功时另含 namespace_uri、resource_span、resource_target_raw、resource_target_origin(explicit/implicit_default)，保留资源目标原声明；沿目标 span 可回读结构和下一跳；exclude 仍是独立结构节点。visibility 含 visibility_status(hidden_declaration/unknown)、css_evaluated=false、evidence(预览数组)、evidence_complete。partial 或 unknown 不能用于证明零事实/可见/业务真假；不转换 checkbox/format，不合并同值 occurrence。
当前读取页与本次显示内容分别续读：若 text/nodes/facts 被本次显示预算截断，先用返回 cursor/scope_token 调用一次 fetch_more，省略 limit 取齐本页全部余量并拼接；cursor 只是本次被截内容的引用，成功使用一次即失效，不返回新 cursor。不得传小 limit 期待后续 cursor。取齐本页后再用 next_start/next_offset 读下一页；不得将 cursor 当资产坐标。
最小例子：先 read_original_structure(..., start=0) 从节点的原始 xmlns:c 属性发现 URI（例如返回 urn:example），再 query_original_facts(..., concepts=[{"namespace_uri":"urn:example","local_name":"TradingSymbol"}])；实际调用必须使用本文件定义处发现的 URI，不猜年度/前缀。"""


def _original_parameters(name: str) -> ToolParametersSchema:
    """参数：原文工具名。返回：自足显式参数 schema。异常：schema 非法时抛出。"""
    properties: dict[str, JsonValue] = {
        "ticker": _ticker_parameter_schema(),
        "document_id": {"type": "string", "description": "list_documents 返回的 exact ID，不接受 accession 别名。"},
        "source_kind": {
            "type": "string",
            "enum": ["filing", "material"],
            "description": "显式资产 namespace，取自文档列表。",
        },
    }
    required = ["ticker", "document_id", "source_kind"]
    if name != "list_document_assets":
        properties.update(
            {
                "filename": {"type": "string", "description": "从枚举原样复制 exact 文件名，不传路径。"},
                "expected_sha256": {
                    "type": "string",
                    "description": "从枚举原样复制 sha256 内容校验标签，内容变更须重新枚举。",
                },
            }
        )
        required.extend(("filename", "expected_sha256"))
    if name in {"read_original_text", "read_original_structure"}:
        properties.update(
            {
                "start": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "可选，默认 0；原文码点起点，结构选择节点起点。",
                },
                "end": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "可选，省略为 EOF；左闭右开终点，不能超过 total_chars。",
                },
            }
        )
        field = "max_chars" if name == "read_original_text" else "max_nodes"
        default, maximum = (
            (TEXT_PAGE_DEFAULT, TEXT_PAGE_MAX)
            if name == "read_original_text"
            else (STRUCTURE_PAGE_DEFAULT, STRUCTURE_PAGE_MAX)
        )
        properties[field] = {
            "type": "integer",
            "minimum": 1,
            "maximum": maximum,
            "description": f"可选，当前读取页预算，默认 {default}，上限 {maximum}，超限拒绝。",
        }
    if name == "query_original_facts":
        properties.update(
            {
                "concepts": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": CONCEPTS_MAX,
                    "description": '必填 expanded concepts。每项是对象，只允许两个必填非空字符串 namespace_uri（定义处 exact URI）和 local_name（不含 prefix 的本地名）。先公开读取结构发现 URI，不猜年度或前缀别名。例：[{"namespace_uri":"urn:example","local_name":"TradingSymbol"}]，实际 URI 必须替换为本文件公开结构返回值。',
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "可选，默认 0；按原文顺序的 occurrence 偏移。",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": FACT_PAGE_MAX,
                    "description": f"可选，默认 {FACT_PAGE_DEFAULT}，最大 {FACT_PAGE_MAX}。",
                },
            }
        )
        required.append("concepts")
    return ToolParametersSchema(
        type="object", properties=properties, required=tuple(required), additional_properties=False
    )


def _build_original_definition(
    name: str,
    read_runtime: FinsReadRuntime,
    limits: FinsToolLimits,
    provider_lock: asyncio.Lock,
    process_target_factory: _FinsReadProcessTargetFactory,
) -> ToolDefinition:
    """参数：工具名、runtime、预算、provider 锁和进程工厂。返回：同契约 process-backed 工具。异常：声明失败。"""
    parameters = _original_parameters(name)
    truncate = (
        _text_truncate(limits.original_text_display_chars, "text")
        if name == "read_original_text"
        else (
            _list_truncate(limits.original_structure_display_items, "nodes")
            if name == "read_original_structure"
            else (
                _list_truncate(limits.original_facts_display_items, "facts") if name == "query_original_facts" else None
            )
        )
    )

    # 工具声明需要每个定义各自绑定其 schema 和名称；闭包仅持有装配依赖，不保存请求状态。
    @tool(
        name=name,
        description=_ORIGINAL_DESCRIPTION,
        parameters=parameters,
        execution=ProcessBackedToolExecutionCapability(target_factory=process_target_factory),
        tags=FINS_TOOL_TAGS,
        display_name=name,
        truncate=truncate,
    )
    async def original_read(call: ToolCallRequest, context: BatchToolExecutionContext) -> ToolExecutionOutcome:
        """参数：调用及执行上下文。返回：统一 outcome。异常：由统一业务投影处理。"""
        return await _invoke_fins_read_business(
            tool_name=name,
            context=context,
            provider_lock=provider_lock,
            started_at=datetime.now(UTC),
            business_call=lambda token: _execute_fins_read_business_value(
                tool_name=name,
                call=call,
                parameters=parameters,
                read_runtime=read_runtime,
                limits=limits,
                cancellation_token=token,
            ),
        )

    return original_read


def _build_read_section_definition(
    read_runtime: FinsReadRuntime,
    limits: FinsToolLimits,
    provider_lock: asyncio.Lock,
    process_target_factory: _FinsReadProcessTargetFactory,
) -> ToolDefinition:
    """构造 ``read_section`` 工具定义。

    Args:
        read_runtime: Fins read runtime。
        limits: 工具限制配置。
        provider_lock: provider 级共享执行锁。
        process_target_factory: process-backed 目标工厂。

    Returns:
        current 工具定义。

    Raises:
        Exception: 工具声明契约构造失败时透出。
    """

    parameters = _read_section_parameters()

    @tool(
        name=READ_SECTION_TOOL_NAME,
        description="读取章节视图，content_scope=section_view；source_asset 标识实际阅读资产。该视图不承诺完整原件；完整原文请先 list_document_assets 再 read_original_text。若正文里出现 [[t_XXXX]]，可用 get_table(t_XXXX) 读取对应表格。",
        parameters=parameters,
        execution=ProcessBackedToolExecutionCapability(
            target_factory=process_target_factory,
        ),
        tags=FINS_TOOL_TAGS,
        display_name="读取财报章节",
        truncate=_text_truncate(limits.read_section_max_chars, "content"),
    )
    async def read_section(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 ``read_section`` 工具调用。

        Args:
            call: 单次工具调用请求。
            context: 批式执行上下文。

        Returns:
            工具执行 outcome。

        Raises:
            无；业务异常会在本边界投影为 failed / cancelled outcome。
        """

        started_at = datetime.now(UTC)
        return await _invoke_fins_read_business(
            tool_name=READ_SECTION_TOOL_NAME,
            context=context,
            provider_lock=provider_lock,
            started_at=started_at,
            business_call=lambda token: _execute_fins_read_business_value(
                tool_name=READ_SECTION_TOOL_NAME,
                call=call,
                parameters=parameters,
                read_runtime=read_runtime,
                limits=limits,
                cancellation_token=token,
            ),
        )

    return read_section


def _build_search_document_definition(
    read_runtime: FinsReadRuntime,
    limits: FinsToolLimits,
    provider_lock: asyncio.Lock,
    process_target_factory: _FinsReadProcessTargetFactory,
) -> ToolDefinition:
    """构造 ``search_document`` 工具定义。

    Args:
        read_runtime: Fins read runtime。
        limits: 工具限制配置。
        provider_lock: provider 级共享执行锁。
        process_target_factory: process-backed 目标工厂。

    Returns:
        current 工具定义。

    Raises:
        Exception: 工具声明契约构造失败时透出。
    """

    parameters = _search_document_parameters()

    @tool(
        name=SEARCH_DOCUMENT_TOOL_NAME,
        description="在文档内搜索定位相关章节。先找最相关命中，再优先 read_section(top_match.ref) 精读；不要靠翻页继续猜。",
        parameters=parameters,
        execution=ProcessBackedToolExecutionCapability(
            target_factory=process_target_factory,
        ),
        tags=FINS_TOOL_TAGS,
        display_name="检索文档",
        truncate=_list_truncate(limits.search_document_max_items, "matches"),
    )
    async def search_document(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 ``search_document`` 工具调用。

        Args:
            call: 单次工具调用请求。
            context: 批式执行上下文。

        Returns:
            工具执行 outcome。

        Raises:
            无；业务异常会在本边界投影为 failed / cancelled outcome。
        """

        started_at = datetime.now(UTC)
        return await _invoke_fins_read_business(
            tool_name=SEARCH_DOCUMENT_TOOL_NAME,
            context=context,
            provider_lock=provider_lock,
            started_at=started_at,
            business_call=lambda token: _execute_fins_read_business_value(
                tool_name=SEARCH_DOCUMENT_TOOL_NAME,
                call=call,
                parameters=parameters,
                read_runtime=read_runtime,
                limits=limits,
                cancellation_token=token,
            ),
        )

    return search_document


def _build_list_tables_definition(
    read_runtime: FinsReadRuntime,
    limits: FinsToolLimits,
    provider_lock: asyncio.Lock,
    process_target_factory: _FinsReadProcessTargetFactory,
) -> ToolDefinition:
    """构造 ``list_tables`` 工具定义。

    Args:
        read_runtime: Fins read runtime。
        limits: 工具限制配置。
        provider_lock: provider 级共享执行锁。
        process_target_factory: process-backed 目标工厂。

    Returns:
        current 工具定义。

    Raises:
        Exception: 工具声明契约构造失败时透出。
    """

    parameters = _list_tables_parameters()

    @tool(
        name=LIST_TABLES_TOOL_NAME,
        description="列出文档内表格，返回可定位的 table_ref 列表。",
        parameters=parameters,
        execution=ProcessBackedToolExecutionCapability(
            target_factory=process_target_factory,
        ),
        tags=FINS_TOOL_TAGS,
        display_name="列出表格",
        truncate=_list_truncate(limits.list_tables_max_items, "tables"),
    )
    async def list_tables(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 ``list_tables`` 工具调用。

        Args:
            call: 单次工具调用请求。
            context: 批式执行上下文。

        Returns:
            工具执行 outcome。

        Raises:
            无；业务异常会在本边界投影为 failed / cancelled outcome。
        """

        started_at = datetime.now(UTC)
        return await _invoke_fins_read_business(
            tool_name=LIST_TABLES_TOOL_NAME,
            context=context,
            provider_lock=provider_lock,
            started_at=started_at,
            business_call=lambda token: _execute_fins_read_business_value(
                tool_name=LIST_TABLES_TOOL_NAME,
                call=call,
                parameters=parameters,
                read_runtime=read_runtime,
                limits=limits,
                cancellation_token=token,
            ),
        )

    return list_tables


def _build_get_table_definition(
    read_runtime: FinsReadRuntime,
    limits: FinsToolLimits,
    provider_lock: asyncio.Lock,
    process_target_factory: _FinsReadProcessTargetFactory,
) -> ToolDefinition:
    """构造 ``get_table`` 工具定义。

    Args:
        read_runtime: Fins read runtime。
        limits: 工具限制配置。
        provider_lock: provider 级共享执行锁。
        process_target_factory: process-backed 目标工厂。

    Returns:
        current 工具定义。

    Raises:
        Exception: 工具声明契约构造失败时透出。
    """

    parameters = _get_table_parameters()

    @tool(
        name=GET_TABLE_TOOL_NAME,
        description="按 table_ref 读取单个表格。",
        parameters=parameters,
        execution=ProcessBackedToolExecutionCapability(
            target_factory=process_target_factory,
        ),
        tags=FINS_TOOL_TAGS,
        display_name="查看表格",
        truncate=_list_truncate(limits.get_table_max_items, None),
    )
    async def get_table(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 ``get_table`` 工具调用。

        Args:
            call: 单次工具调用请求。
            context: 批式执行上下文。

        Returns:
            工具执行 outcome。

        Raises:
            无；业务异常会在本边界投影为 failed / cancelled outcome。
        """

        started_at = datetime.now(UTC)
        return await _invoke_fins_read_business(
            tool_name=GET_TABLE_TOOL_NAME,
            context=context,
            provider_lock=provider_lock,
            started_at=started_at,
            business_call=lambda token: _execute_fins_read_business_value(
                tool_name=GET_TABLE_TOOL_NAME,
                call=call,
                parameters=parameters,
                read_runtime=read_runtime,
                limits=limits,
                cancellation_token=token,
            ),
        )

    return get_table


def _build_get_page_content_definition(
    read_runtime: FinsReadRuntime,
    limits: FinsToolLimits,
    provider_lock: asyncio.Lock,
    process_target_factory: _FinsReadProcessTargetFactory,
) -> ToolDefinition:
    """构造 ``get_page_content`` 工具定义。

    Args:
        read_runtime: Fins read runtime。
        limits: 工具限制配置。
        provider_lock: provider 级共享执行锁。
        process_target_factory: process-backed 目标工厂。

    Returns:
        current 工具定义。

    Raises:
        Exception: 工具声明契约构造失败时透出。
    """

    parameters = _get_page_content_parameters()

    @tool(
        name=GET_PAGE_CONTENT_TOOL_NAME,
        description="按页码读取同页内容。只有已有 page_range 且需要补同页上下文时才使用。",
        parameters=parameters,
        execution=ProcessBackedToolExecutionCapability(
            target_factory=process_target_factory,
        ),
        tags=FINS_TOOL_TAGS,
        display_name="读取页面",
        truncate=_text_truncate(limits.get_page_content_max_chars, "text_preview"),
    )
    async def get_page_content(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 ``get_page_content`` 工具调用。

        Args:
            call: 单次工具调用请求。
            context: 批式执行上下文。

        Returns:
            工具执行 outcome。

        Raises:
            无；业务异常会在本边界投影为 failed / cancelled outcome。
        """

        started_at = datetime.now(UTC)
        return await _invoke_fins_read_business(
            tool_name=GET_PAGE_CONTENT_TOOL_NAME,
            context=context,
            provider_lock=provider_lock,
            started_at=started_at,
            business_call=lambda token: _execute_fins_read_business_value(
                tool_name=GET_PAGE_CONTENT_TOOL_NAME,
                call=call,
                parameters=parameters,
                read_runtime=read_runtime,
                limits=limits,
                cancellation_token=token,
            ),
        )

    return get_page_content


def _build_get_financial_statement_definition(
    read_runtime: FinsReadRuntime,
    limits: FinsToolLimits,
    provider_lock: asyncio.Lock,
    process_target_factory: _FinsReadProcessTargetFactory,
) -> ToolDefinition:
    """构造 ``get_financial_statement`` 工具定义。

    Args:
        read_runtime: Fins read runtime。
        limits: 工具限制配置。
        provider_lock: provider 级共享执行锁。
        process_target_factory: process-backed 目标工厂。

    Returns:
        current 工具定义。

    Raises:
        Exception: 工具声明契约构造失败时透出。
    """

    parameters = _get_financial_statement_parameters()

    @tool(
        name=GET_FINANCIAL_STATEMENT_TOOL_NAME,
        description=financial_statement_result_description(),
        parameters=parameters,
        execution=ProcessBackedToolExecutionCapability(
            target_factory=process_target_factory,
        ),
        tags=FINS_TOOL_TAGS,
        display_name="查看财务报表",
        truncate=_list_truncate(limits.get_financial_statement_max_items, "rows"),
    )
    async def get_financial_statement(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 ``get_financial_statement`` 工具调用。

        Args:
            call: 单次工具调用请求。
            context: 批式执行上下文。

        Returns:
            工具执行 outcome。

        Raises:
            无；业务异常会在本边界投影为 failed / cancelled outcome。
        """

        started_at = datetime.now(UTC)
        return await _invoke_fins_read_business(
            tool_name=GET_FINANCIAL_STATEMENT_TOOL_NAME,
            context=context,
            provider_lock=provider_lock,
            started_at=started_at,
            business_call=lambda token: _execute_fins_read_business_value(
                tool_name=GET_FINANCIAL_STATEMENT_TOOL_NAME,
                call=call,
                parameters=parameters,
                read_runtime=read_runtime,
                limits=limits,
                cancellation_token=token,
            ),
        )

    return get_financial_statement


def _build_query_xbrl_facts_definition(
    read_runtime: FinsReadRuntime,
    limits: FinsToolLimits,
    provider_lock: asyncio.Lock,
    process_target_factory: _FinsReadProcessTargetFactory,
) -> ToolDefinition:
    """构造 ``query_xbrl_facts`` 工具定义。

    Args:
        read_runtime: Fins read runtime。
        limits: 工具限制配置。
        provider_lock: provider 级共享执行锁。
        process_target_factory: process-backed 目标工厂。

    Returns:
        current 工具定义。

    Raises:
        Exception: 工具声明契约构造失败时透出。
    """

    parameters = _query_xbrl_facts_parameters()

    @tool(
        name=QUERY_XBRL_FACTS_TOOL_NAME,
        description=xbrl_query_result_description(),
        parameters=parameters,
        execution=ProcessBackedToolExecutionCapability(
            target_factory=process_target_factory,
        ),
        tags=FINS_TOOL_TAGS,
        display_name="查询财务数据",
        truncate=_list_truncate(limits.query_xbrl_facts_max_items, "facts"),
    )
    async def query_xbrl_facts(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 ``query_xbrl_facts`` 工具调用。

        Args:
            call: 单次工具调用请求。
            context: 批式执行上下文。

        Returns:
            工具执行 outcome。

        Raises:
            无；业务异常会在本边界投影为 failed / cancelled outcome。
        """

        started_at = datetime.now(UTC)
        return await _invoke_fins_read_business(
            tool_name=QUERY_XBRL_FACTS_TOOL_NAME,
            context=context,
            provider_lock=provider_lock,
            started_at=started_at,
            business_call=lambda token: _execute_fins_read_business_value(
                tool_name=QUERY_XBRL_FACTS_TOOL_NAME,
                call=call,
                parameters=parameters,
                read_runtime=read_runtime,
                limits=limits,
                cancellation_token=token,
            ),
        )

    return query_xbrl_facts


async def _invoke_fins_read_business(
    *,
    tool_name: str,
    context: BatchToolExecutionContext,
    provider_lock: asyncio.Lock,
    started_at: datetime,
    business_call: _BusinessCall,
) -> ToolExecutionOutcome:
    """在 fallback callable 边界执行同步 Fins read 业务并投影 outcome。

    生产默认路径不再经过本函数；十三个 Fins read ``ToolDefinition.execution``
    均声明为 process-backed，由 Host ToolRuntime 在父进程治理取消与超时。
    本函数只保留给直接调用 ``ToolDefinition.callable`` 的测试和非生产
    fallback，避免把同进程 ``asyncio.to_thread`` 误作为生产取消 closeout
    证据。

    Args:
        tool_name: 工具名。
        context: 批式执行上下文。
        provider_lock: provider 级共享锁。
        started_at: 工具调用开始时间。
        business_call: 接收 cancellation token 并返回 JSON 业务值的同步函数。

    Returns:
        completed / failed / cancelled outcome。

    Raises:
        无；业务异常会被投影。
    """

    cancellation_token = context.cancellation_token
    if cancellation_token.is_cancelled():
        return _build_fins_read_cancelled_outcome(tool_name, started_at)
    async with provider_lock:
        if cancellation_token.is_cancelled():
            return _build_fins_read_cancelled_outcome(tool_name, started_at)
        try:
            value = await asyncio.to_thread(business_call, cancellation_token)
        except _FinsReadBusinessFailure as exc:
            return failed_outcome(
                tool_name=tool_name,
                error=exc.error,
                message=exc.message,
                hint=exc.hint,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        except FinsReadCancelledError as exc:
            return host_cancelled_outcome(
                tool_name=tool_name,
                message=exc.message,
                hint=exc.hint,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        except FinsReadArgumentError as exc:
            return failed_outcome(
                tool_name=tool_name,
                error="invalid_argument",
                message=str(exc),
                hint=_INVALID_ARGUMENT_HINT,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        except FinsReadBusinessError as exc:
            return failed_outcome(
                tool_name=tool_name,
                error=exc.code.value,
                message=exc.message,
                hint=exc.hint,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        except FileNotFoundError as exc:
            return failed_outcome(
                tool_name=tool_name,
                error="file_not_found",
                message=str(exc),
                hint=_FILE_NOT_FOUND_HINT,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        except PermissionError as exc:
            return failed_outcome(
                tool_name=tool_name,
                error="permission_denied",
                message=str(exc),
                hint="Use a workspace path allowed by the Fins storage configuration.",
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        except Exception:
            return failed_outcome(
                tool_name=tool_name,
                error="execution_error",
                message=f"Tool {tool_name!r} execution failed.",
                hint=_UNEXPECTED_FAILURE_HINT,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
    return completed_outcome(
        tool_name=tool_name,
        value=value,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )


def _execute_fins_read_business_value(
    *,
    tool_name: str,
    call: ToolCallRequest,
    parameters: ToolParametersSchema,
    read_runtime: FinsReadRuntime,
    limits: FinsToolLimits,
    cancellation_token: CancellationToken,
) -> JsonValue:
    """执行 Fins read 同步业务并返回成功 JSON 值。

    本函数是 direct callable fallback 与 process-backed 子进程 target 共用的
    同步业务路由真源。它负责参数 schema 校验、read runtime 调用和成功
    载荷投影；失败通过 ``_FinsReadBusinessFailure`` 抛出，由调用边界投影
    为 Tool outcome 或 process JSON 信封。

    Args:
        tool_name: 工具名。
        call: 单次工具调用请求。
        parameters: 当前工具的参数 schema。
        read_runtime: 当前进程内重新构造或 provider 注入的 Fins read runtime。
        limits: Fins 工具限制配置。
        cancellation_token: 当前执行边界使用的取消观察 token。

    Returns:
        成功 JSON 值。

    Raises:
        _FinsReadBusinessFailure: 参数、仓储或业务访问失败时抛出。
        FinsReadCancelledError: direct callable fallback 观察到 Host 取消时抛出。
    """

    validation = validate_and_project_arguments(call, tool_name, parameters)
    if isinstance(validation, ToolArgumentValidationFailure):
        raise _FinsReadBusinessFailure(validation.error, validation.message, validation.hint)
    try:
        return _route_fins_read_business(
            tool_name=tool_name,
            arguments=validation.arguments,
            read_runtime=read_runtime,
            limits=limits,
            cancellation_token=cancellation_token,
        )
    except FinsReadCancelledError:
        # direct callable fallback 仍需要投影 Host 取消；process target 使用不可取消
        # token，真实取消由父进程 process capsule 独占治理。
        raise
    except FinsReadArgumentError as exc:
        raise _FinsReadBusinessFailure(
            "invalid_argument",
            str(exc),
            _INVALID_ARGUMENT_HINT,
        ) from exc
    except FinsReadBusinessError as exc:
        raise _FinsReadBusinessFailure(exc.code.value, exc.message, exc.hint) from exc
    except FileNotFoundError as exc:
        raise _FinsReadBusinessFailure(
            "file_not_found",
            str(exc),
            _FILE_NOT_FOUND_HINT,
        ) from exc
    except PermissionError as exc:
        raise _FinsReadBusinessFailure(
            "permission_denied",
            str(exc),
            "Use a workspace path allowed by the Fins storage configuration.",
        ) from exc
    except Exception as exc:
        raise _FinsReadBusinessFailure(
            "execution_error",
            f"Tool {tool_name!r} execution failed.",
            _UNEXPECTED_FAILURE_HINT,
        ) from exc


def _route_fins_read_business(
    *,
    tool_name: str,
    arguments: Mapping[str, JsonValue],
    read_runtime: FinsReadRuntime,
    limits: FinsToolLimits,
    cancellation_token: CancellationToken,
) -> JsonValue:
    """按工具名路由到对应 Fins read runtime 方法。

    Args:
        tool_name: 工具名。
        arguments: 已通过 schema 校验并投影的参数。
        read_runtime: Fins read runtime。
        limits: Fins 工具限制配置。
        cancellation_token: 当前执行边界使用的取消观察 token。

    Returns:
        原始业务 JSON 值。

    Raises:
        ValueError: 工具名未知时抛出。
        FinsReadArgumentError: 业务参数非法时抛出。
        FinsReadBusinessError: 业务失败时抛出。
        FinsReadCancelledError: direct callable fallback 观察到 Host 取消时抛出。
    """

    if tool_name in _ORIGINAL_TOOL_NAMES:
        ticker = _required_string(arguments, "ticker")
        document_id = _required_string(arguments, "document_id")
        kind = SourceKind(_required_string(arguments, "source_kind"))
        if tool_name == "list_document_assets":
            return cast(
                JsonValue,
                read_runtime.list_document_assets(
                    ticker=ticker, document_id=document_id, source_kind=kind, cancellation_token=cancellation_token
                ),
            )
        filename = _required_string(arguments, "filename")
        expected = _required_string(arguments, "expected_sha256")
        start = _optional_int(arguments, "start")
        end = _optional_int(arguments, "end")
        if tool_name == "read_original_text":
            max_chars = _optional_int(arguments, "max_chars")
            return cast(
                JsonValue,
                read_runtime.read_original_text(
                    ticker=ticker,
                    document_id=document_id,
                    source_kind=kind,
                    filename=filename,
                    expected_sha256=expected,
                    start=0 if start is None else start,
                    end=end,
                    max_chars=TEXT_PAGE_DEFAULT if max_chars is None else max_chars,
                    cancellation_token=cancellation_token,
                ),
            )
        if tool_name == "read_original_structure":
            max_nodes = _optional_int(arguments, "max_nodes")
            return cast(
                JsonValue,
                read_runtime.read_original_structure(
                    ticker=ticker,
                    document_id=document_id,
                    source_kind=kind,
                    filename=filename,
                    expected_sha256=expected,
                    start=0 if start is None else start,
                    end=end,
                    max_nodes=STRUCTURE_PAGE_DEFAULT if max_nodes is None else max_nodes,
                    cancellation_token=cancellation_token,
                ),
            )
        concepts_raw = arguments.get("concepts")
        if not isinstance(concepts_raw, list):
            raise ValueError("concepts 必须是 expanded name 数组")
        # JSON 传输不删改条目；完整 shape 与 QName 校验由 runtime owner 执行。
        concepts = cast(Sequence[ExpandedName], concepts_raw)
        offset = _optional_int(arguments, "offset")
        limit = _optional_int(arguments, "limit")
        return cast(
            JsonValue,
            read_runtime.query_original_facts(
                ticker=ticker,
                document_id=document_id,
                source_kind=kind,
                filename=filename,
                expected_sha256=expected,
                concepts=concepts,
                offset=0 if offset is None else offset,
                limit=FACT_PAGE_DEFAULT if limit is None else limit,
                cancellation_token=cancellation_token,
            ),
        )
    if tool_name == LIST_DOCUMENTS_TOOL_NAME:
        return cast(
            JsonValue,
            read_runtime.list_documents(
                ticker=_required_string(arguments, "ticker"),
                document_types=_optional_string_list(arguments, "document_types"),
                fiscal_years=_optional_int_list(arguments, "fiscal_years"),
                fiscal_periods=_optional_string_list(arguments, "fiscal_periods"),
                cancellation_token=cancellation_token,
            ),
        )
    if tool_name == GET_DOCUMENT_SECTIONS_TOOL_NAME:
        return cast(
            JsonValue,
            read_runtime.get_document_sections(
                ticker=_required_string(arguments, "ticker"),
                document_id=_required_string(arguments, "document_id"),
                cancellation_token=cancellation_token,
            ),
        )
    if tool_name == READ_SECTION_TOOL_NAME:
        return cast(
            JsonValue,
            read_runtime.read_section(
                ticker=_required_string(arguments, "ticker"),
                document_id=_required_string(arguments, "document_id"),
                ref=_required_string(arguments, "ref"),
                cancellation_token=cancellation_token,
            ),
        )
    if tool_name == SEARCH_DOCUMENT_TOOL_NAME:
        return _search_document_business(
            read_runtime=read_runtime,
            arguments=arguments,
            display_budget=limits.search_document_max_items,
            cancellation_token=cancellation_token,
        )
    if tool_name == LIST_TABLES_TOOL_NAME:
        return cast(
            JsonValue,
            read_runtime.list_tables(
                ticker=_required_string(arguments, "ticker"),
                document_id=_required_string(arguments, "document_id"),
                financial_only=_optional_bool(arguments, "financial_only", default=False),
                within_section_ref=_optional_string(arguments, "within_section_ref"),
                cancellation_token=cancellation_token,
            ),
        )
    if tool_name == GET_TABLE_TOOL_NAME:
        return cast(
            JsonValue,
            read_runtime.get_table(
                ticker=_required_string(arguments, "ticker"),
                document_id=_required_string(arguments, "document_id"),
                table_ref=_required_string(arguments, "table_ref"),
                cancellation_token=cancellation_token,
            ),
        )
    if tool_name == GET_PAGE_CONTENT_TOOL_NAME:
        return cast(
            JsonValue,
            read_runtime.get_page_content(
                ticker=_required_string(arguments, "ticker"),
                document_id=_required_string(arguments, "document_id"),
                page_no=_required_int(arguments, "page_no"),
                cancellation_token=cancellation_token,
            ),
        )
    if tool_name == GET_FINANCIAL_STATEMENT_TOOL_NAME:
        return cast(
            JsonValue,
            read_runtime.get_financial_statement(
                ticker=_required_string(arguments, "ticker"),
                document_id=_required_string(arguments, "document_id"),
                statement_type=_required_string(arguments, "statement_type"),
                cancellation_token=cancellation_token,
            ),
        )
    if tool_name == QUERY_XBRL_FACTS_TOOL_NAME:
        return cast(
            JsonValue,
            read_runtime.query_xbrl_facts(
                ticker=_required_string(arguments, "ticker"),
                document_id=_required_string(arguments, "document_id"),
                concepts=_optional_string_list(arguments, "concepts"),
                statement_type=_optional_string(arguments, "statement_type"),
                period_end=_optional_string(arguments, "period_end"),
                fiscal_year=_optional_int(arguments, "fiscal_year"),
                fiscal_period=_optional_string(arguments, "fiscal_period"),
                min_value=_optional_number(arguments, "min_value"),
                max_value=_optional_number(arguments, "max_value"),
                cancellation_token=cancellation_token,
            ),
        )
    raise ValueError(f"unsupported fins read tool: {tool_name}")


def _parameters_for_tool(tool_name: str) -> ToolParametersSchema:
    """按工具名构造参数 schema。

    Args:
        tool_name: 工具名。

    Returns:
        参数 schema。

    Raises:
        ValueError: 工具名未知时抛出。
    """

    if tool_name in _ORIGINAL_TOOL_NAMES:
        return _original_parameters(tool_name)
    if tool_name == LIST_DOCUMENTS_TOOL_NAME:
        return _list_documents_parameters()
    if tool_name == GET_DOCUMENT_SECTIONS_TOOL_NAME:
        return _ticker_document_parameters()
    if tool_name == READ_SECTION_TOOL_NAME:
        return _read_section_parameters()
    if tool_name == SEARCH_DOCUMENT_TOOL_NAME:
        return _search_document_parameters()
    if tool_name == LIST_TABLES_TOOL_NAME:
        return _list_tables_parameters()
    if tool_name == GET_TABLE_TOOL_NAME:
        return _get_table_parameters()
    if tool_name == GET_PAGE_CONTENT_TOOL_NAME:
        return _get_page_content_parameters()
    if tool_name == GET_FINANCIAL_STATEMENT_TOOL_NAME:
        return _get_financial_statement_parameters()
    if tool_name == QUERY_XBRL_FACTS_TOOL_NAME:
        return _query_xbrl_facts_parameters()
    raise ValueError(f"unsupported fins read tool: {tool_name}")


def _process_failed_envelope(failure: _FinsReadBusinessFailure) -> JsonValue:
    """把 Fins read 业务失败转换为 process-backed failed 信封。

    Args:
        failure: 同步业务失败。

    Returns:
        Host process capsule 可解析的 failed JSON 信封。

    Raises:
        无。
    """

    return process_tool_failed_envelope(
        error_type=failure.error,
        message=failure.message,
        hint=failure.hint,
    )


def _search_document_business(
    *,
    read_runtime: FinsReadRuntime,
    arguments: Mapping[str, JsonValue],
    display_budget: int,
    cancellation_token: CancellationToken,
) -> JsonValue:
    """执行 ``search_document`` 业务并剥离内部诊断字段。

    Args:
        read_runtime: Fins read runtime。
        arguments: 已通过 schema 投影的工具参数。
        display_budget: 展示预算上限。
        cancellation_token: Host 取消令牌。

    Returns:
        搜索结果 JSON 载荷。

    Raises:
        FinsReadArgumentError: query / queries 组合非法时抛出。
        FinsReadBusinessError: ticker 未收录等业务失败时抛出。
        FinsReadCancelledError: Host 取消时抛出。
    """

    result = read_runtime.search_document(
        ticker=_required_string(arguments, "ticker"),
        document_id=_required_string(arguments, "document_id"),
        query=_optional_string(arguments, "query"),
        queries=_optional_string_list(arguments, "queries"),
        within_section_ref=_optional_string(arguments, "within_section_ref"),
        mode=_optional_string(arguments, "mode"),
        display_budget=display_budget,
        cancellation_token=cancellation_token,
    )
    result.pop("diagnostics", None)
    return cast(JsonValue, result)


def _build_fins_read_cancelled_outcome(
    tool_name: str,
    started_at: datetime,
) -> ToolExecutionOutcome:
    """构造 Fins read 已取消 outcome。

    本函数不读取 Host token reason，避免把 run_id、session_id、digest 等
    Host 治理信息泄漏到 LLM-facing message 或 hint。

    Args:
        tool_name: 工具名。
        started_at: 工具调用开始时间。

    Returns:
        cancelled outcome。

    Raises:
        Exception: outcome 构造失败时透出。
    """

    return host_cancelled_outcome(
        tool_name=tool_name,
        message="财报读取工具调用已被取消。",
        hint=_FINS_CANCELLED_HINT,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )


def _list_documents_parameters() -> ToolParametersSchema:
    """构造 ``list_documents`` 参数 schema。

    Args:
        无。

    Returns:
        current 参数 schema。

    Raises:
        Exception: schema 构造失败时透出。
    """

    return ToolParametersSchema(
        type="object",
        properties={
            "ticker": _ticker_parameter_schema(),
            "document_types": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [
                        "annual_report",
                        "semi_annual_report",
                        "quarterly_report",
                        "current_report",
                        "proxy",
                        "ownership",
                        "earnings_call",
                        "earnings_presentation",
                        "corporate_governance",
                        "material",
                    ],
                },
                "description": "可选文档类型过滤。只在你已明确要看哪类文档时填写；否则留空先看推荐文档。",
            },
            "fiscal_years": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "可选财年过滤。只在你已明确年份时填写，例如 [2024, 2025]。",
            },
            "fiscal_periods": {
                "type": "array",
                "items": {"type": "string", "enum": ["FY", "H1", "Q1", "Q2", "Q3", "Q4"]},
                "description": "可选财期过滤。只在你已明确财期时填写，例如 FY、Q1、Q2。",
            },
        },
        required=("ticker",),
        additional_properties=False,
    )


def _ticker_document_parameters() -> ToolParametersSchema:
    """构造只含 ticker 与 document_id 的参数 schema。

    Args:
        无。

    Returns:
        current 参数 schema。

    Raises:
        Exception: schema 构造失败时透出。
    """

    return ToolParametersSchema(
        type="object",
        properties={
            "ticker": _ticker_parameter_schema(),
            "document_id": _document_id_parameter_schema(),
        },
        required=("ticker", "document_id"),
        additional_properties=False,
    )


def _read_section_parameters() -> ToolParametersSchema:
    """构造 ``read_section`` 参数 schema。

    Args:
        无。

    Returns:
        current 参数 schema。

    Raises:
        Exception: schema 构造失败时透出。
    """

    return ToolParametersSchema(
        type="object",
        properties={
            "ticker": _ticker_parameter_schema(),
            "document_id": _document_id_parameter_schema(),
            "ref": {
                "type": "string",
                "description": "章节ref。只能来自于 `get_document_sections` 的 `sections[].ref`，`search_document` 的 `next_section_to_read.section.ref`，或 `search_document` 的 `next_section_by_query[*].section.ref`。仅在当前 `document_id` 内有效；切换 `document_id` 后必须重新对新文档 grounding，禁止复用其他 `document_id` 的 `ref`。",
            },
        },
        required=("ticker", "document_id", "ref"),
        additional_properties=False,
    )


def _search_document_parameters() -> ToolParametersSchema:
    """构造 ``search_document`` 参数 schema。

    Args:
        无。

    Returns:
        current 参数 schema。

    Raises:
        Exception: schema 构造失败时透出。
    """

    return ToolParametersSchema(
        type="object",
        properties={
            "ticker": _ticker_parameter_schema(),
            "document_id": _document_id_parameter_schema(),
            "query": {
                "type": "string",
                "description": "单个搜索词。只搜一个概念时使用；避免裸数字、裸百分比或过于宽泛的词。",
            },
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 20,
                "description": "多关键词搜索时使用，一次最多 20 个；与 query 互斥。只有这些词都服务同一主题时再一起传。",
            },
            "within_section_ref": {
                "type": "string",
                "description": "章节ref。结果太多时用它收窄范围。",
            },
            "mode": {
                "type": "string",
                "enum": ["auto", "exact", "keyword", "semantic"],
                "description": "搜索模式。通常用 auto；只有你明确要精确短语匹配或关键词匹配时再手动指定。",
            },
        },
        required=("ticker", "document_id"),
        additional_properties=False,
    )


def _list_tables_parameters() -> ToolParametersSchema:
    """构造 ``list_tables`` 参数 schema。

    Args:
        无。

    Returns:
        current 参数 schema。

    Raises:
        Exception: schema 构造失败时透出。
    """

    return ToolParametersSchema(
        type="object",
        properties={
            "ticker": _ticker_parameter_schema(),
            "document_id": _document_id_parameter_schema(),
            "financial_only": {
                "type": "boolean",
                "description": "只在你明确只看财务报表类表格时设为 true；否则保持默认 false。",
                "default": False,
            },
            "within_section_ref": {
                "type": "string",
                "description": "章节ref。想只看某一章里的表格时填写。",
            },
        },
        required=("ticker", "document_id"),
        additional_properties=False,
    )


def _get_table_parameters() -> ToolParametersSchema:
    """构造 ``get_table`` 参数 schema。

    Args:
        无。

    Returns:
        current 参数 schema。

    Raises:
        Exception: schema 构造失败时透出。
    """

    return ToolParametersSchema(
        type="object",
        properties={
            "ticker": _ticker_parameter_schema(),
            "document_id": _document_id_parameter_schema(),
            "table_ref": {
                "type": "string",
                "description": "表格ref。只能来自于`list_tables` 的 `tables[].table_ref` 或 `read_section` 正文里的 `[[t_XXXX]]`。仅在当前 `document_id` 内有效；切换 `document_id` 后必须重新对新文档 grounding，禁止复用其他 `document_id` 的 `table_ref`。",
            },
        },
        required=("ticker", "document_id", "table_ref"),
        additional_properties=False,
    )


def _get_page_content_parameters() -> ToolParametersSchema:
    """构造 ``get_page_content`` 参数 schema。

    Args:
        无。

    Returns:
        current 参数 schema。

    Raises:
        Exception: schema 构造失败时透出。
    """

    return ToolParametersSchema(
        type="object",
        properties={
            "ticker": _ticker_parameter_schema(),
            "document_id": _document_id_parameter_schema(),
            "page_no": {"type": "integer", "description": "页码，从 1 开始。", "minimum": 1},
        },
        required=("ticker", "document_id", "page_no"),
        additional_properties=False,
    )


def _get_financial_statement_parameters() -> ToolParametersSchema:
    """构造 ``get_financial_statement`` 参数 schema。

    Args:
        无。

    Returns:
        current 参数 schema。

    Raises:
        Exception: schema 构造失败时透出。
    """

    return ToolParametersSchema(
        type="object",
        properties={
            "ticker": _ticker_parameter_schema(),
            "document_id": _document_id_parameter_schema(),
            "statement_type": {
                "type": "string",
                "description": "报表类型。通常先看 income、balance_sheet、cash_flow；只有明确需要时再看 equity 或 comprehensive_income。",
                "enum": ["income", "balance_sheet", "cash_flow", "equity", "comprehensive_income"],
            },
        },
        required=("ticker", "document_id", "statement_type"),
        additional_properties=False,
    )


def _query_xbrl_facts_parameters() -> ToolParametersSchema:
    """构造 ``query_xbrl_facts`` 参数 schema。

    Args:
        无。

    Returns:
        current 参数 schema。

    Raises:
        Exception: schema 构造失败时透出。
    """

    fiscal_period_values: list[JsonValue] = [fiscal_period for fiscal_period in sorted(FISCAL_PERIODS)]
    return ToolParametersSchema(
        type="object",
        properties={
            "ticker": _ticker_parameter_schema(),
            "document_id": _document_id_parameter_schema(),
            "concepts": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选 XBRL 概念列表。已明确要找某个概念时填写；不确定时可留空，先看默认概念集。",
                "minItems": 1,
            },
            "statement_type": {
                "type": "string",
                "description": "可选报表类型过滤。想把结果收窄到某一类报表时再填。",
            },
            "period_end": {"type": "string", "description": "可选期末日期过滤，格式 YYYY-MM-DD。"},
            "fiscal_year": {"type": "integer", "description": "可选财年过滤。只在你已明确年份时填写。"},
            "fiscal_period": {
                "type": "string",
                "description": "可选财期过滤。只在已明确 FY、H1 或季度归属时填写。",
                "enum": fiscal_period_values,
            },
            "min_value": {"type": "number", "description": "可选最小值过滤。只在你明确要排除过小数值时填写。"},
            "max_value": {"type": "number", "description": "可选最大值过滤。只在你明确要排除过大数值时填写。"},
        },
        required=("ticker", "document_id"),
        additional_properties=False,
    )


def _ticker_parameter_schema() -> dict[str, JsonValue]:
    """构造 Fins read 工具共用的 ticker 参数 schema。

    Args:
        无。

    Returns:
        包含自足业务语义的 ticker 参数 schema。

    Raises:
        无。
    """

    return {
        "type": "string",
        "description": (
            "公司财报代码。可传工作区已接收的主代码或该公司的任一已接收别名；"
            "两者会查询同一家公司归档。不要传公司名称，也不要手工穷举代码变体。"
        ),
    }


def _document_id_parameter_schema() -> dict[str, JsonValue]:
    """构造 Fins read 工具共用的 document_id 参数 schema。

    Args:
        无。

    Returns:
        包含来源约束的 document_id 参数 schema。

    Raises:
        无。
    """

    return {
        "type": "string",
        "description": (
            "文档 ID。只能使用同一 ticker 的 "
            "list_documents.documents[].document_id；切换 ticker 后必须重新调用 "
            "list_documents 选择，禁止猜测或复用其他 ticker 的 document_id。"
        ),
    }


def _text_truncate(max_chars: int, target_field: str) -> ToolTruncateSpec:
    """构造文本字符截断声明。

    Args:
        max_chars: 最大字符数。
        target_field: 目标字段。

    Returns:
        current 截断声明。

    Raises:
        Exception: 截断声明构造失败时透出。
    """

    return ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits={"max_chars": max_chars},
        target_field=target_field,
        field_path=None,
        ttl_seconds=None,
    )


def _list_truncate(max_items: int, target_field: str | None) -> ToolTruncateSpec:
    """构造列表项截断声明。

    Args:
        max_items: 最大条目数。
        target_field: 顶层目标字段；为 None 时由 ToolRuntime 对整个结果应用。

    Returns:
        current 截断声明。

    Raises:
        Exception: 截断声明构造失败时透出。
    """

    return ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.LIST_ITEMS,
        limits={"max_items": max_items},
        target_field=target_field,
        field_path=None,
        ttl_seconds=None,
    )


def _required_string(arguments: Mapping[str, JsonValue], field_name: str) -> str:
    """读取必填字符串参数。

    Args:
        arguments: 已投影的参数映射。
        field_name: 字段名。

    Returns:
        字符串参数值。

    Raises:
        FinsReadArgumentError: 字段缺失或类型非法时抛出。
    """

    value = arguments.get(field_name)
    if not isinstance(value, str):
        raise FinsReadArgumentError("fins_read", field_name, value, "Argument must be a string")
    return value


def _optional_string(arguments: Mapping[str, JsonValue], field_name: str) -> str | None:
    """读取可选字符串参数。

    Args:
        arguments: 已投影的参数映射。
        field_name: 字段名。

    Returns:
        字符串参数值或 None。

    Raises:
        FinsReadArgumentError: 字段类型非法时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise FinsReadArgumentError("fins_read", field_name, value, "Argument must be a string")
    return value


def _required_int(arguments: Mapping[str, JsonValue], field_name: str) -> int:
    """读取必填整数参数。

    Args:
        arguments: 已投影的参数映射。
        field_name: 字段名。

    Returns:
        整数参数值。

    Raises:
        FinsReadArgumentError: 字段缺失或类型非法时抛出。
    """

    value = arguments.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise FinsReadArgumentError("fins_read", field_name, value, "Argument must be an integer")
    return value


def _optional_int(arguments: Mapping[str, JsonValue], field_name: str) -> int | None:
    """读取可选整数参数。

    Args:
        arguments: 已投影的参数映射。
        field_name: 字段名。

    Returns:
        整数参数值或 None。

    Raises:
        FinsReadArgumentError: 字段类型非法时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise FinsReadArgumentError("fins_read", field_name, value, "Argument must be an integer")
    return value


def _optional_number(arguments: Mapping[str, JsonValue], field_name: str) -> float | None:
    """读取可选数值参数。

    Args:
        arguments: 已投影的参数映射。
        field_name: 字段名。

    Returns:
        数值参数或 None。

    Raises:
        FinsReadArgumentError: 字段类型非法时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FinsReadArgumentError("fins_read", field_name, value, "Argument must be a number")
    return float(value)


def _optional_bool(arguments: Mapping[str, JsonValue], field_name: str, *, default: bool) -> bool:
    """读取可选布尔参数。

    Args:
        arguments: 已投影的参数映射。
        field_name: 字段名。
        default: 字段缺失时使用的默认值。

    Returns:
        布尔参数值。

    Raises:
        FinsReadArgumentError: 字段类型非法时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise FinsReadArgumentError("fins_read", field_name, value, "Argument must be a boolean")
    return value


def _optional_string_list(arguments: Mapping[str, JsonValue], field_name: str) -> list[str] | None:
    """读取可选字符串数组参数。

    Args:
        arguments: 已投影的参数映射。
        field_name: 字段名。

    Returns:
        字符串数组或 None。

    Raises:
        FinsReadArgumentError: 字段类型非法时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return None
    if not isinstance(value, list):
        raise FinsReadArgumentError("fins_read", field_name, value, "Argument must be a string array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise FinsReadArgumentError("fins_read", field_name, value, "Argument must be a string array")
        result.append(item)
    return result


def _optional_int_list(arguments: Mapping[str, JsonValue], field_name: str) -> list[int] | None:
    """读取可选整数数组参数。

    Args:
        arguments: 已投影的参数映射。
        field_name: 字段名。

    Returns:
        整数数组或 None。

    Raises:
        FinsReadArgumentError: 字段类型非法时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return None
    if not isinstance(value, list):
        raise FinsReadArgumentError("fins_read", field_name, value, "Argument must be an integer array")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise FinsReadArgumentError("fins_read", field_name, value, "Argument must be an integer array")
        result.append(item)
    return result


__all__ = [
    "FINS_READ_TOOL_NAMES",
    "FINS_TOOL_TAGS",
    "build_fins_read_tool_definitions",
]
