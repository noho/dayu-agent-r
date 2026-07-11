"""通用文档读取工具的 current 原生实现。

本模块提供五个只读 Doc 工具的 ``ToolDefinition`` / ``ToolCallable`` 原生
声明与同步业务实现。LLM-facing schema、展示名、标签、截断声明和成功 /
失败载荷保持与迁移前 Doc 工具一致；参数校验、路径白名单、取消 outcome
投影在本模块的 current callable 边界完成，不依赖 legacy adapter。
"""

from __future__ import annotations

import asyncio
import logging
import re
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, NoReturn, cast

from dayu.contracts import (
    BatchToolExecutionContext,
    CancellationToken,
    JsonValue,
    ProcessBackedToolContext,
    ProcessBackedToolExecutionCapability,
    ToolCallRequest,
    ToolCallable,
    ToolDefinition,
    ToolDisplayInfo,
    ToolExecutionOutcome,
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
    process_tool_completed_envelope,
    process_tool_failed_envelope,
)
from dayu.contracts.tool_schema import ToolTruncateSpec, ToolTruncationStrategy
from dayu.documents.processors._doc_processor_factory import create_doc_file_processor
from dayu.documents.processors.base import DocumentProcessor
from dayu.documents.processors.search_utils import extract_query_anchored_snippets
from dayu.runtime.tool_call_projection import (
    ToolArgumentValidationFailure,
    ToolBusinessCancelled,
    completed_outcome,
    failed_outcome,
    host_cancelled_outcome,
    validate_and_project_arguments,
)

MODULE: Final[str] = "ENGINE.DOC_TOOLS"
_LOGGER = logging.getLogger(__name__)

_SUPPORTED_FORMATS_DESCRIPTION: Final[str] = "md, markdown, html, htm, *_docling.json"
_DOC_TOOL_TAGS: Final[tuple[str, ...]] = ("doc",)

LIST_FILES_TOOL_NAME: Final[str] = "list_files"
GET_FILE_SECTIONS_TOOL_NAME: Final[str] = "get_file_sections"
SEARCH_FILES_TOOL_NAME: Final[str] = "search_files"
READ_FILE_TOOL_NAME: Final[str] = "read_file"
READ_FILE_SECTION_TOOL_NAME: Final[str] = "read_file_section"

DOC_TOOL_NAMES: Final[tuple[str, ...]] = (
    LIST_FILES_TOOL_NAME,
    GET_FILE_SECTIONS_TOOL_NAME,
    SEARCH_FILES_TOOL_NAME,
    READ_FILE_TOOL_NAME,
    READ_FILE_SECTION_TOOL_NAME,
)

_DOC_CANCELLED_HINT: Final[str] = "当前工具调用已停止；如仍需要该结果，请等待用户确认后再重新发起。"
_INVALID_ARGUMENT_HINT: Final[str] = "Fix arguments to match the tool schema and retry."
_PATH_POLICY_HINT: Final[str] = "Use a path under the provider configured allowed roots."

_READ_FILE_ENCODINGS: Final[tuple[str, ...]] = ("utf-8", "gbk", "latin1", "cp1252")
_READ_LINES_ENCODINGS: Final[tuple[str, ...]] = ("utf-8", "gbk")
_MARKDOWN_SUFFIXES: Final[frozenset[str]] = frozenset({".md", ".markdown"})
_DOC_LOOP_CANCELLATION_CHECK_INTERVAL: Final[int] = 1_000


@dataclass(frozen=True, slots=True)
class DocToolLimits:
    """文档工具限制配置。

    Args:
        list_files_max: ``list_files`` 最大返回文件数。
        get_sections_max: ``get_file_sections`` 最大返回章节数。
        search_files_max_results: ``search_files`` 最大返回命中数。
        read_file_max_chars: ``read_file`` 最大返回字符数。
        read_file_section_max_chars: ``read_file_section`` 最大返回字符数。

    Returns:
        无。

    Raises:
        无。
    """

    list_files_max: int = 200
    get_sections_max: int = 200
    search_files_max_results: int = 50
    read_file_max_chars: int = 80_000
    read_file_section_max_chars: int = 50_000


@dataclass(frozen=True, slots=True)
class _DocPathFailure:
    """Doc 路径投影失败。

    Args:
        error: current failure 错误码。
        message: 面向 LLM 的错误说明。
        hint: 可选恢复提示。

    Returns:
        dataclass 实例。

    Raises:
        无。
    """

    error: str
    message: str
    hint: str | None


class _DocBusinessFailure(Exception):
    """Doc 同步业务路由的可恢复失败。

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


class _DocToolArgumentError(Exception):
    """Doc 业务参数错误。

    Args:
        tool_name: 工具名。
        arg_name: 参数名。
        arg_value: 参数值。
        details: 详细错误说明。

    Raises:
        无。
    """

    def __init__(
        self,
        tool_name: str,
        arg_name: str,
        arg_value: JsonValue,
        details: str,
    ) -> None:
        """初始化 Doc 参数错误。

        Args:
            tool_name: 工具名。
            arg_name: 参数名。
            arg_value: 参数值。
            details: 详细错误说明。

        Returns:
            无。

        Raises:
            无。
        """

        self.tool_name = tool_name
        self.arg_name = arg_name
        self.arg_value = arg_value
        self.details = details
        super().__init__(f"Tool {tool_name!r} argument error: {arg_name}: {details}")


class _DocFileAccessError(Exception):
    """Doc 文件访问错误。

    Args:
        path: 相关路径。
        filename_or_details: 文件名或详细错误说明。
        details: 三参形式中的详细错误说明。

    Raises:
        无。
    """

    def __init__(
        self,
        path: str,
        filename_or_details: str,
        details: str | None = None,
    ) -> None:
        """初始化 Doc 文件访问错误。

        Args:
            path: 相关路径。
            filename_or_details: 二参形式时为详细说明，三参形式时为文件名。
            details: 三参形式时的详细说明。

        Returns:
            无。

        Raises:
            无。
        """

        detail_text = filename_or_details if details is None else details
        filename = "" if details is None else filename_or_details
        display_path = path if filename == "" else f"{path}/{filename}"
        self.path = display_path
        self.details = detail_text
        super().__init__(f"{display_path}: {detail_text}")


class _DocCancelledError(Exception):
    """Doc 深层 helper 观察到 Host 取消时使用的本地异常载体。

    Args:
        cancellation: 可投影为 ``ToolCancelledOutcome`` 的语义取消结果。

    Raises:
        无。
    """

    def __init__(self, cancellation: ToolBusinessCancelled) -> None:
        """初始化取消信号。

        Args:
            cancellation: helper 生成的取消语义。

        Returns:
            无。

        Raises:
            无。
        """

        self.cancellation = cancellation
        super().__init__(cancellation.message or "文档工具调用已被取消。")


class _DocProcessCancellationToken:
    """Doc 子进程内使用的不可取消 token。

    process-backed 生产路径由父进程 Host capsule 负责 terminate / kill，子
    进程目标不能返回 host_cancelled / timeout / cancelled 信封，因此子进程
    内只使用永不取消的本地观察 token。
    """

    def is_cancelled(self) -> bool:
        """返回是否已取消。

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


@dataclass(frozen=True, slots=True)
class _DocProcessTarget:
    """Doc process-backed 子进程目标。

    Args:
        tool_name: 工具名。
        arguments: 工具调用参数的 JSON 副本。
        allowed_root_locators: 允许访问根路径的可序列化字符串 locator。
        limits: Doc 工具 limit 配置。
        timeout_seconds: 父进程投影的批级 timeout 标量；仅作为可序列化上下文
            留痕，真实 timeout 仍由父进程 Host capsule 独占治理。

    Returns:
        dataclass 实例。

    Raises:
        无。
    """

    tool_name: str
    arguments: dict[str, JsonValue]
    allowed_root_locators: tuple[str, ...]
    limits: DocToolLimits
    timeout_seconds: float | None

    def __call__(self) -> JsonValue:
        """在子进程内执行 Doc 同步业务并返回 JSON 信封。

        Args:
            无。

        Returns:
            ``completed`` 或 ``failed`` JSON 信封；不会返回 awaiting、
            cancelled、timeout 或 host_cancelled。

        Raises:
            无；未预期异常会被转换为 failed 信封。
        """

        call = ToolCallRequest(
            tool_call_id=f"process-{self.tool_name}",
            name=self.tool_name,
            arguments=self.arguments,
            index_in_iteration=0,
            provider_state=None,
        )
        try:
            value = _execute_doc_business_value(
                tool_name=self.tool_name,
                call=call,
                parameters=_parameters_for_tool(self.tool_name, self.limits),
                allowed_roots=_resolve_allowed_root_locators(self.allowed_root_locators),
                limits=self.limits,
                cancellation_token=_DocProcessCancellationToken(),
            )
        except _DocBusinessFailure as failure:
            return _process_failed_envelope(failure)
        except Exception:
            return process_tool_failed_envelope(
                error_type="execution_error",
                message=f"Tool {self.tool_name!r} execution failed.",
            )
        return process_tool_completed_envelope(value)


@dataclass(frozen=True, slots=True)
class _DocProcessTargetFactory:
    """Doc process-backed target factory。

    本 factory 只保存 spawn 可序列化的路径 locator 与 limit 配置，不捕获
    provider lock、DocumentProcessor、repository、runtime、session、
    CancellationToken 或 Host 内部对象。

    Args:
        allowed_root_locators: 允许访问根路径的可序列化字符串 locator。
        limits: Doc 工具 limit 配置。

    Returns:
        dataclass 实例。

    Raises:
        无。
    """

    allowed_root_locators: tuple[str, ...]
    limits: DocToolLimits

    def build_process_target(
        self,
        call: ToolCallRequest,
        context: ProcessBackedToolContext,
    ) -> _DocProcessTarget:
        """构造可序列化 Doc 子进程目标。

        Args:
            call: 单次工具调用请求。
            context: Host 投影出的可序列化 process-backed 上下文。

        Returns:
            Doc 子进程目标。

        Raises:
            无。
        """

        return _DocProcessTarget(
            tool_name=call.name,
            arguments=dict(call.arguments),
            allowed_root_locators=self.allowed_root_locators,
            limits=self.limits,
            timeout_seconds=context.timeout_seconds,
        )


class Log:
    """Doc 工具的窄日志适配器。

    本类只保持业务逻辑中的 ``Log.warn`` / ``Log.verbose`` 调用形状，实际
    写入当前模块 logger。
    """

    @staticmethod
    def warn(message: str, *, module: str) -> None:
        """记录 warning 级别日志。

        Args:
            message: 日志正文。
            module: 模块标签。

        Returns:
            无。

        Raises:
            无。
        """

        _LOGGER.warning("[%s] %s", module, message)

    @staticmethod
    def verbose(message: str, *, module: str) -> None:
        """记录 debug 级别日志。

        Args:
            message: 日志正文。
            module: 模块标签。

        Returns:
            无。

        Raises:
            无。
        """

        _LOGGER.debug("[%s] %s", module, message)


def build_doc_tool_definitions(
    limits: DocToolLimits,
    allowed_roots: tuple[Path, ...],
) -> tuple[ToolDefinition, ...]:
    """构造五个原生 Doc 工具定义。

    Args:
        limits: 文档工具限制配置。
        allowed_roots: provider 解析出的显式允许访问根路径；为空时返回空元组。

    Returns:
        按稳定顺序排列的 current ``ToolDefinition`` 元组。

    Raises:
        ValueError: 工具定义构造出的名称顺序不符合 Doc provider 约定时抛出。
    """

    if not allowed_roots:
        return ()
    normalized_roots = tuple(root.expanduser().resolve(strict=False) for root in allowed_roots)
    provider_lock = asyncio.Lock()
    process_target_factory = _DocProcessTargetFactory(
        allowed_root_locators=tuple(str(root) for root in normalized_roots),
        limits=limits,
    )
    definitions = (
        _build_list_files_definition(limits, normalized_roots, provider_lock, process_target_factory),
        _build_get_file_sections_definition(limits, normalized_roots, provider_lock, process_target_factory),
        _build_search_files_definition(limits, normalized_roots, provider_lock, process_target_factory),
        _build_read_file_definition(limits, normalized_roots, provider_lock, process_target_factory),
        _build_read_file_section_definition(
            limits,
            normalized_roots,
            provider_lock,
            process_target_factory,
        ),
    )
    names = tuple(definition.name for definition in definitions)
    if names != DOC_TOOL_NAMES:
        raise ValueError(f"doc provider expected tools {DOC_TOOL_NAMES}, got {names}")
    return definitions


def _build_list_files_definition(
    limits: DocToolLimits,
    allowed_roots: tuple[Path, ...],
    provider_lock: asyncio.Lock,
    process_target_factory: _DocProcessTargetFactory,
) -> ToolDefinition:
    """构造 ``list_files`` 工具定义。

    Args:
        limits: Doc 工具限制配置。
        allowed_roots: 允许访问根路径。
        provider_lock: provider 级共享执行锁。
        process_target_factory: process-backed 目标工厂。

    Returns:
        current 工具定义。

    Raises:
        Exception: ``ToolDefinition`` 契约构造失败时透出。
    """

    parameters = _list_files_parameters(limits.list_files_max)

    async def list_files_callable(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 ``list_files`` current callable。

        Args:
            call: 单次工具调用请求。
            context: 批式执行上下文。

        Returns:
            工具执行 outcome。

        Raises:
            无；业务异常会投影为 failed / cancelled outcome。
        """

        started_at = datetime.now(UTC)
        return await _invoke_doc_business(
            tool_name=LIST_FILES_TOOL_NAME,
            context=context,
            provider_lock=provider_lock,
            started_at=started_at,
            business_call=lambda token: _execute_doc_business_value(
                tool_name=LIST_FILES_TOOL_NAME,
                call=call,
                parameters=parameters,
                allowed_roots=allowed_roots,
                limits=limits,
                cancellation_token=token,
            ),
        )

    return _tool_definition(
        name=LIST_FILES_TOOL_NAME,
        description=(
            "列出配置允许访问目录中的文件。先用它定位文件，再把返回的 files[].path 交给 get_file_sections、read_file 或 read_file_section。"
        ),
        parameters=parameters,
        callable_=list_files_callable,
        display_name="列出文件",
        truncate=None,
        process_target_factory=process_target_factory,
    )


def _build_get_file_sections_definition(
    limits: DocToolLimits,
    allowed_roots: tuple[Path, ...],
    provider_lock: asyncio.Lock,
    process_target_factory: _DocProcessTargetFactory,
) -> ToolDefinition:
    """构造 ``get_file_sections`` 工具定义。

    Args:
        limits: Doc 工具限制配置。
        allowed_roots: 允许访问根路径。
        provider_lock: provider 级共享执行锁。
        process_target_factory: process-backed 目标工厂。

    Returns:
        current 工具定义。

    Raises:
        Exception: ``ToolDefinition`` 契约构造失败时透出。
    """

    parameters = _get_file_sections_parameters(limits.get_sections_max)

    async def get_file_sections_callable(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 ``get_file_sections`` current callable。

        Args:
            call: 单次工具调用请求。
            context: 批式执行上下文。

        Returns:
            工具执行 outcome。

        Raises:
            无；业务异常会投影为 failed / cancelled outcome。
        """

        started_at = datetime.now(UTC)
        return await _invoke_doc_business(
            tool_name=GET_FILE_SECTIONS_TOOL_NAME,
            context=context,
            provider_lock=provider_lock,
            started_at=started_at,
            business_call=lambda token: _execute_doc_business_value(
                tool_name=GET_FILE_SECTIONS_TOOL_NAME,
                call=call,
                parameters=parameters,
                allowed_roots=allowed_roots,
                limits=limits,
                cancellation_token=token,
            ),
        )

    return _tool_definition(
        name=GET_FILE_SECTIONS_TOOL_NAME,
        description=(
            "列出文件的章节结构。先用它定位章节；若返回的 sections[].ref 不为 null，就把 ref 交给 read_file_section。若 ref 为 null，改用 read_file，不要猜 ref。"
        ),
        parameters=parameters,
        callable_=get_file_sections_callable,
        display_name="浏览文件结构",
        truncate=None,
        process_target_factory=process_target_factory,
    )


def _build_search_files_definition(
    limits: DocToolLimits,
    allowed_roots: tuple[Path, ...],
    provider_lock: asyncio.Lock,
    process_target_factory: _DocProcessTargetFactory,
) -> ToolDefinition:
    """构造 ``search_files`` 工具定义。

    Args:
        limits: Doc 工具限制配置。
        allowed_roots: 允许访问根路径。
        provider_lock: provider 级共享执行锁。
        process_target_factory: process-backed 目标工厂。

    Returns:
        current 工具定义。

    Raises:
        Exception: ``ToolDefinition`` 契约构造失败时透出。
    """

    parameters = _search_files_parameters(limits.search_files_max_results)

    async def search_files_callable(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 ``search_files`` current callable。

        Args:
            call: 单次工具调用请求。
            context: 批式执行上下文。

        Returns:
            工具执行 outcome。

        Raises:
            无；业务异常会投影为 failed / cancelled outcome。
        """

        started_at = datetime.now(UTC)
        return await _invoke_doc_business(
            tool_name=SEARCH_FILES_TOOL_NAME,
            context=context,
            provider_lock=provider_lock,
            started_at=started_at,
            business_call=lambda token: _execute_doc_business_value(
                tool_name=SEARCH_FILES_TOOL_NAME,
                call=call,
                parameters=parameters,
                allowed_roots=allowed_roots,
                limits=limits,
                cancellation_token=token,
            ),
        )

    return _tool_definition(
        name=SEARCH_FILES_TOOL_NAME,
        description=(
            "在配置允许访问目录中按关键词查找命中文件。若命中结果带 ref，优先把 matches[].file 和 ref 交给 read_file_section；若 ref 为 null，再把 matches[].file 交给 read_file。"
        ),
        parameters=parameters,
        callable_=search_files_callable,
        display_name="搜索文件",
        truncate=None,
        process_target_factory=process_target_factory,
    )


def _build_read_file_definition(
    limits: DocToolLimits,
    allowed_roots: tuple[Path, ...],
    provider_lock: asyncio.Lock,
    process_target_factory: _DocProcessTargetFactory,
) -> ToolDefinition:
    """构造 ``read_file`` 工具定义。

    Args:
        limits: Doc 工具限制配置。
        allowed_roots: 允许访问根路径。
        provider_lock: provider 级共享执行锁。
        process_target_factory: process-backed 目标工厂。

    Returns:
        current 工具定义。

    Raises:
        Exception: ``ToolDefinition`` 契约构造失败时透出。
    """

    parameters = _read_file_parameters()

    async def read_file_callable(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 ``read_file`` current callable。

        Args:
            call: 单次工具调用请求。
            context: 批式执行上下文。

        Returns:
            工具执行 outcome。

        Raises:
            无；业务异常会投影为 failed / cancelled outcome。
        """

        started_at = datetime.now(UTC)
        return await _invoke_doc_business(
            tool_name=READ_FILE_TOOL_NAME,
            context=context,
            provider_lock=provider_lock,
            started_at=started_at,
            business_call=lambda token: _execute_doc_business_value(
                tool_name=READ_FILE_TOOL_NAME,
                call=call,
                parameters=parameters,
                allowed_roots=allowed_roots,
                limits=limits,
                cancellation_token=token,
            ),
        )

    return _tool_definition(
        name=READ_FILE_TOOL_NAME,
        description="按整文件或按行范围读取内容。没有 ref、或文件不支持章节读取时用它。",
        parameters=parameters,
        callable_=read_file_callable,
        display_name="读取文件",
        truncate=_text_content_truncate(limits.read_file_max_chars),
        process_target_factory=process_target_factory,
    )


def _build_read_file_section_definition(
    limits: DocToolLimits,
    allowed_roots: tuple[Path, ...],
    provider_lock: asyncio.Lock,
    process_target_factory: _DocProcessTargetFactory,
) -> ToolDefinition:
    """构造 ``read_file_section`` 工具定义。

    Args:
        limits: Doc 工具限制配置。
        allowed_roots: 允许访问根路径。
        provider_lock: provider 级共享执行锁。
        process_target_factory: process-backed 目标工厂。

    Returns:
        current 工具定义。

    Raises:
        Exception: ``ToolDefinition`` 契约构造失败时透出。
    """

    parameters = _read_file_section_parameters()

    async def read_file_section_callable(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行 ``read_file_section`` current callable。

        Args:
            call: 单次工具调用请求。
            context: 批式执行上下文。

        Returns:
            工具执行 outcome。

        Raises:
            无；业务异常会投影为 failed / cancelled outcome。
        """

        started_at = datetime.now(UTC)
        return await _invoke_doc_business(
            tool_name=READ_FILE_SECTION_TOOL_NAME,
            context=context,
            provider_lock=provider_lock,
            started_at=started_at,
            business_call=lambda token: _execute_doc_business_value(
                tool_name=READ_FILE_SECTION_TOOL_NAME,
                call=call,
                parameters=parameters,
                allowed_roots=allowed_roots,
                limits=limits,
                cancellation_token=token,
            ),
        )

    return _tool_definition(
        name=READ_FILE_SECTION_TOOL_NAME,
        description=(
            f"按章节 ref 读取内容。ref 必须来自 get_file_sections；支持的格式有 {_SUPPORTED_FORMATS_DESCRIPTION}。若文件不支持章节读取或 ref 为 null，改用 read_file。"
        ),
        parameters=parameters,
        callable_=read_file_section_callable,
        display_name="读取文件段落",
        truncate=_text_content_truncate(limits.read_file_section_max_chars),
        process_target_factory=process_target_factory,
    )


async def _invoke_doc_business(
    *,
    tool_name: str,
    context: BatchToolExecutionContext,
    provider_lock: asyncio.Lock,
    started_at: datetime,
    business_call: Callable[[CancellationToken], JsonValue],
) -> ToolExecutionOutcome:
    """在 fallback callable 边界执行同步 Doc 业务并投影 outcome。

    生产默认路径不再经过本函数；五个 Doc ``ToolDefinition.execution`` 均
    声明为 process-backed，由 Host ToolRuntime 在父进程治理取消与超时。
    本函数只保留给直接调用 ``ToolDefinition.callable`` 的测试和非生产
    fallback，避免把同进程 ``asyncio.to_thread`` 误作为生产取消 closeout
    证据。

    Args:
        tool_name: 工具名。
        context: 批式执行上下文。
        provider_lock: provider 级共享锁。
        started_at: callable 开始时间。
        business_call: 接收 cancellation token 并返回 JSON 业务值的同步函数。

    Returns:
        completed / failed / cancelled outcome。

    Raises:
        无；业务异常会被投影。
    """

    token = context.cancellation_token
    if token.is_cancelled():
        return _cancelled_outcome(tool_name, started_at, _doc_cancelled())
    async with provider_lock:
        if token.is_cancelled():
            return _cancelled_outcome(tool_name, started_at, _doc_cancelled())
        try:
            raw_value = await asyncio.to_thread(business_call, token)
        except _DocBusinessFailure as error:
            return failed_outcome(
                tool_name=tool_name,
                error=error.error,
                message=error.message,
                hint=error.hint,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        except _DocCancelledError as error:
            return _cancelled_outcome(tool_name, started_at, error.cancellation)
        except _DocToolArgumentError as error:
            return failed_outcome(
                tool_name=tool_name,
                error="invalid_argument",
                message=str(error),
                hint=_INVALID_ARGUMENT_HINT,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        except _DocFileAccessError as error:
            return failed_outcome(
                tool_name=tool_name,
                error="permission_denied",
                message=str(error),
                hint="Use a path allowed by the provider configuration.",
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        except FileNotFoundError as error:
            return failed_outcome(
                tool_name=tool_name,
                error="file_not_found",
                message=str(error),
                hint="Verify the file path and retry.",
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        except PermissionError as error:
            return failed_outcome(
                tool_name=tool_name,
                error="permission_denied",
                message=str(error),
                hint="Use a path allowed by the provider configuration.",
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        except Exception:
            return failed_outcome(
                tool_name=tool_name,
                error="execution_error",
                message=f"Tool {tool_name!r} execution failed.",
                hint="Inspect provider diagnostics or retry with narrower arguments.",
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
    return completed_outcome(
        tool_name=tool_name,
        value=raw_value,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )


def _execute_doc_business_value(
    *,
    tool_name: str,
    call: ToolCallRequest,
    parameters: ToolParametersSchema,
    allowed_roots: tuple[Path, ...],
    limits: DocToolLimits,
    cancellation_token: CancellationToken,
) -> JsonValue:
    """执行 Doc 工具同步业务并返回成功 JSON 值。

    本函数是 fallback callable 与 process-backed 子进程 target 共用的同步
    业务路由真源。它负责参数校验、路径白名单校验、业务 helper 调用和成功
    响应路径投影；失败通过 ``_DocBusinessFailure`` 抛出，由调用边界投影
    为 Tool outcome 或 process JSON 信封。

    Args:
        tool_name: 工具名。
        call: 单次工具调用请求。
        parameters: 当前工具的参数 schema。
        allowed_roots: 已重新解析的允许访问根路径。
        limits: Doc 工具限制配置。
        cancellation_token: 当前执行边界使用的取消观察 token。

    Returns:
        成功 JSON 值。

    Raises:
        _DocBusinessFailure: 参数、路径或业务访问失败时抛出。
        _DocCancelledError: fallback callable 观察到 Host 取消时抛出。
    """

    validation = validate_and_project_arguments(call, tool_name, parameters)
    if isinstance(validation, ToolArgumentValidationFailure):
        raise _DocBusinessFailure(validation.error, validation.message, validation.hint)
    path_projection = _project_doc_paths(
        tool_name=tool_name,
        arguments=validation.arguments,
        path_param_names=_path_param_names_for_tool(tool_name),
        allowed_roots=allowed_roots,
    )
    if isinstance(path_projection, _DocPathFailure):
        raise _DocBusinessFailure(
            path_projection.error,
            path_projection.message,
            path_projection.hint,
        )
    try:
        raw_value = _route_doc_business(
            tool_name=tool_name,
            arguments=path_projection,
            allowed_roots=allowed_roots,
            limits=limits,
            cancellation_token=cancellation_token,
        )
    except _DocCancelledError:
        # 该分支服务 direct callable fallback；process target 使用不可取消 token，
        # 真实取消由父进程 process capsule 独占治理。
        raise
    except _DocToolArgumentError as error:
        raise _DocBusinessFailure(
            "invalid_argument",
            str(error),
            _INVALID_ARGUMENT_HINT,
        ) from error
    except _DocFileAccessError as error:
        raise _DocBusinessFailure(
            "permission_denied",
            str(error),
            "Use a path allowed by the provider configuration.",
        ) from error
    except FileNotFoundError as error:
        raise _DocBusinessFailure(
            "file_not_found",
            str(error),
            "Verify the file path and retry.",
        ) from error
    except PermissionError as error:
        raise _DocBusinessFailure(
            "permission_denied",
            str(error),
            "Use a path allowed by the provider configuration.",
        ) from error
    except Exception as error:
        raise _DocBusinessFailure(
            "execution_error",
            f"Tool {tool_name!r} execution failed.",
            "Inspect provider diagnostics or retry with narrower arguments.",
        ) from error
    return _project_tool_response_paths(tool_name, raw_value)


def _route_doc_business(
    *,
    tool_name: str,
    arguments: Mapping[str, JsonValue],
    allowed_roots: tuple[Path, ...],
    limits: DocToolLimits,
    cancellation_token: CancellationToken,
) -> JsonValue:
    """按工具名路由到对应 Doc 同步业务 helper。

    Args:
        tool_name: 工具名。
        arguments: 已通过 schema 与路径白名单校验的参数。
        allowed_roots: 已重新解析的允许访问根路径。
        limits: Doc 工具限制配置。
        cancellation_token: 当前执行边界使用的取消观察 token。

    Returns:
        原始业务 JSON 值。

    Raises:
        ValueError: 工具名未知时抛出。
        _DocToolArgumentError: 业务参数非法时抛出。
        _DocFileAccessError: 文件访问失败时抛出。
        _DocCancelledError: fallback callable 观察到 Host 取消时抛出。
    """

    if tool_name == LIST_FILES_TOOL_NAME:
        return _list_files_business(
            directory=_required_string(arguments, "directory"),
            pattern=_optional_string(arguments, "pattern"),
            recursive=_required_bool(arguments, "recursive"),
            limit=_required_int(arguments, "limit"),
            max_files=limits.list_files_max,
            cancellation_token=cancellation_token,
        )
    if tool_name == GET_FILE_SECTIONS_TOOL_NAME:
        return _get_file_sections_business(
            file_path=_required_string(arguments, "file_path"),
            limit=_required_int(arguments, "limit"),
            max_sections=limits.get_sections_max,
            cancellation_token=cancellation_token,
        )
    if tool_name == SEARCH_FILES_TOOL_NAME:
        return _search_files_business(
            directory=_required_string(arguments, "directory"),
            query=_required_string(arguments, "query"),
            include_types=_optional_string_list(arguments, "include_types"),
            limit=_required_int(arguments, "limit"),
            max_results=limits.search_files_max_results,
            allowed_roots=allowed_roots,
            cancellation_token=cancellation_token,
        )
    if tool_name == READ_FILE_TOOL_NAME:
        return _read_file_business(
            file_path=_required_string(arguments, "file_path"),
            start_line=_optional_int(arguments, "start_line"),
            end_line=_optional_int(arguments, "end_line"),
            cancellation_token=cancellation_token,
        )
    if tool_name == READ_FILE_SECTION_TOOL_NAME:
        return _read_file_section_business(
            file_path=_required_string(arguments, "file_path"),
            ref=_required_string(arguments, "ref"),
            cancellation_token=cancellation_token,
        )
    raise ValueError(f"unsupported doc tool: {tool_name}")


def _path_param_names_for_tool(tool_name: str) -> tuple[str, ...]:
    """返回工具需要路径白名单校验的参数名。

    Args:
        tool_name: 工具名。

    Returns:
        路径参数名元组。

    Raises:
        ValueError: 工具名未知时抛出。
    """

    if tool_name == LIST_FILES_TOOL_NAME:
        return ("directory",)
    if tool_name == GET_FILE_SECTIONS_TOOL_NAME:
        return ("file_path",)
    if tool_name == SEARCH_FILES_TOOL_NAME:
        return ("directory",)
    if tool_name == READ_FILE_TOOL_NAME:
        return ("file_path",)
    if tool_name == READ_FILE_SECTION_TOOL_NAME:
        return ("file_path",)
    raise ValueError(f"unsupported doc tool: {tool_name}")


def _parameters_for_tool(
    tool_name: str,
    limits: DocToolLimits,
) -> ToolParametersSchema:
    """按工具名构造参数 schema。

    Args:
        tool_name: 工具名。
        limits: Doc 工具限制配置。

    Returns:
        参数 schema。

    Raises:
        ValueError: 工具名未知时抛出。
    """

    if tool_name == LIST_FILES_TOOL_NAME:
        return _list_files_parameters(limits.list_files_max)
    if tool_name == GET_FILE_SECTIONS_TOOL_NAME:
        return _get_file_sections_parameters(limits.get_sections_max)
    if tool_name == SEARCH_FILES_TOOL_NAME:
        return _search_files_parameters(limits.search_files_max_results)
    if tool_name == READ_FILE_TOOL_NAME:
        return _read_file_parameters()
    if tool_name == READ_FILE_SECTION_TOOL_NAME:
        return _read_file_section_parameters()
    raise ValueError(f"unsupported doc tool: {tool_name}")


def _resolve_allowed_root_locators(locators: tuple[str, ...]) -> tuple[Path, ...]:
    """在当前进程重新解析 allowed roots locator。

    Args:
        locators: 父进程传入的路径字符串 locator。

    Returns:
        重新 expand / resolve 后的路径根元组。

    Raises:
        无。
    """

    return tuple(Path(locator).expanduser().resolve(strict=False) for locator in locators)


def _process_failed_envelope(failure: _DocBusinessFailure) -> JsonValue:
    """把 Doc 业务失败转换为 process-backed failed 信封。

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


def _project_doc_paths(
    *,
    tool_name: str,
    arguments: Mapping[str, JsonValue],
    path_param_names: tuple[str, ...],
    allowed_roots: tuple[Path, ...],
) -> Mapping[str, JsonValue] | _DocPathFailure:
    """验证并归一化 Doc 工具路径参数。

    Args:
        tool_name: 工具名。
        arguments: 已通过 schema 校验的参数。
        path_param_names: 需要验证的路径参数名。
        allowed_roots: 允许访问根路径。

    Returns:
        成功时返回投影后的参数，失败时返回路径失败结果。

    Raises:
        无。
    """

    if not allowed_roots:
        return _DocPathFailure(
            error="permission_denied",
            message="Tool path arguments require an explicit provider path policy.",
            hint="Configure allowed path roots for this provider before enabling the tool.",
        )
    projected = dict(arguments)
    for parameter_name in path_param_names:
        value = arguments.get(parameter_name)
        if not isinstance(value, str):
            return _DocPathFailure(
                error="invalid_argument",
                message=f"Path argument {parameter_name!r} must be a string.",
                hint=f"Set {parameter_name} to a file path string and retry.",
            )
        candidate = Path(value).expanduser().resolve(strict=False)
        if not any(_is_relative_to(candidate, root) for root in allowed_roots):
            return _DocPathFailure(
                error="permission_denied",
                message=f"Path is outside allowed provider roots: {value}",
                hint=_PATH_POLICY_HINT,
            )
        if not candidate.exists():
            return _DocPathFailure(
                error="file_not_found",
                message=f"Path does not exist: {value}",
                hint="Verify the file path and retry.",
            )
        if parameter_name == "directory" and not candidate.is_dir():
            return _DocPathFailure(
                error="permission_denied",
                message=f"{candidate}: 路径不是目录",
                hint="Use an existing directory under the provider configured allowed roots.",
            )
        if parameter_name != "directory" and not _is_supported_doc_file_path(
            tool_name,
            candidate,
        ):
            return _DocPathFailure(
                error="invalid_argument",
                message=f"Path argument {parameter_name!r} must point to a file: {value}",
                hint=f"Set {parameter_name} to an existing file under the provider configured allowed roots.",
            )
        projected[parameter_name] = str(candidate)
    return projected


def _is_relative_to(candidate: Path, root: Path) -> bool:
    """判断候选路径是否位于允许根路径内。

    Args:
        candidate: 候选路径。
        root: 允许根路径。

    Returns:
        等于 root 或位于 root 子树内时返回 ``True``。

    Raises:
        无。
    """

    return candidate == root or root in candidate.parents


def _is_supported_doc_file_path(tool_name: str, candidate: Path) -> bool:
    """判断 Doc file_path 是否是当前工具可读取的文件节点。

    Args:
        tool_name: 工具名。
        candidate: 已通过白名单 containment 与存在性校验的路径。

    Returns:
        普通文件返回 ``True``；``read_file`` 额外允许 POSIX FIFO，以覆盖
        process-backed 对真实阻塞 I/O 的父进程取消治理。其它工具仍只接受
        普通文件。

    Raises:
        无；stat 失败时返回 ``False``。
    """

    if candidate.is_file():
        return True
    if tool_name != READ_FILE_TOOL_NAME:
        return False
    try:
        return stat.S_ISFIFO(candidate.stat().st_mode)
    except OSError:
        return False


def _list_files_business(
    *,
    directory: str,
    pattern: str | None,
    recursive: bool,
    limit: int,
    max_files: int,
    cancellation_token: CancellationToken,
) -> JsonValue:
    """列出目录中的文件。

    Args:
        directory: 已校验并归一化的目录路径。
        pattern: 文件名 glob 模式。
        recursive: 是否递归搜索。
        limit: 最大返回数量。
        max_files: 配置硬上限。
        cancellation_token: Host 注入的取消观察令牌。

    Returns:
        文件列表 JSON 对象。

    Raises:
        _DocFileAccessError: 路径不是目录时抛出。
        _DocCancelledError: 观察到 Host 取消时抛出。
    """

    actual_limit = min(limit, max_files)
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise _DocFileAccessError(directory, "", "路径不是目录")

    files: list[JsonValue] = []
    _raise_if_doc_cancelled(cancellation_token)
    all_files = dir_path.rglob(pattern if pattern else "*") if recursive else dir_path.glob(pattern if pattern else "*")
    for file_path in all_files:
        _raise_if_doc_cancelled(cancellation_token)
        if not file_path.is_file():
            continue
        try:
            stat = file_path.stat()
            files.append(
                {
                    "name": file_path.name,
                    "path": str(file_path.relative_to(dir_path)),
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )
        except OSError as error:
            Log.warn(f"无法读取文件信息: {file_path} - {error}", module=MODULE)
            continue

    files.sort(key=_sort_record_by_name)
    total = len(files)
    filtered_files = files[:actual_limit] if actual_limit < total else files
    _raise_if_doc_cancelled(cancellation_token)
    return {
        "directory": str(dir_path),
        "files": filtered_files,
        "total": total,
        "returned": len(filtered_files),
    }


def _get_file_sections_business(
    *,
    file_path: str,
    limit: int,
    max_sections: int,
    cancellation_token: CancellationToken,
) -> JsonValue:
    """列出文件章节结构。

    Args:
        file_path: 已校验并归一化的文件路径。
        limit: 最大返回 section 数。
        max_sections: 配置硬上限。
        cancellation_token: Host 注入的取消观察令牌。

    Returns:
        章节结构 JSON 对象。

    Raises:
        _DocCancelledError: 观察到 Host 取消时抛出。
    """

    actual_limit = min(limit, max_sections)
    path = Path(file_path)
    _raise_if_doc_cancelled(cancellation_token)
    processor = _try_create_processor(path)
    if processor is not None:
        return _sections_via_processor(processor, path, actual_limit, cancellation_token)

    _raise_if_doc_cancelled(cancellation_token)
    lines = _read_file_lines(path)
    if lines is None:
        return _fallback_single_section(file_path, path, cancellation_token)

    total_lines = len(lines)
    if path.suffix.lower() in _MARKDOWN_SUFFIXES:
        _raise_if_doc_cancelled(cancellation_token)
        sections = _extract_markdown_sections(lines, cancellation_token)
        if sections:
            filtered_sections: list[JsonValue] = list(sections[:actual_limit])
            markdown_payload: dict[str, JsonValue] = {
                "file_path": str(path),
                "sections": filtered_sections,
                "total_sections": len(sections),
                "returned": len(filtered_sections),
                "total_lines": total_lines,
            }
            return markdown_payload

    return _fallback_single_section(file_path, path, cancellation_token, total_lines)


def _search_files_business(
    *,
    directory: str,
    query: str,
    include_types: list[str] | None,
    limit: int,
    max_results: int,
    allowed_roots: tuple[Path, ...],
    cancellation_token: CancellationToken,
) -> JsonValue:
    """在目录中搜索包含关键词的文件。

    Args:
        directory: 已校验并归一化的目录路径。
        query: 搜索关键词。
        include_types: 可选文件扩展名过滤。
        limit: 最大返回数量。
        max_results: 配置硬上限。
        allowed_roots: 已重新解析的允许访问根路径。
        cancellation_token: Host 注入的取消观察令牌。

    Returns:
        搜索命中 JSON 对象。

    Raises:
        _DocFileAccessError: 路径不是目录时抛出。
        _DocCancelledError: 观察到 Host 取消时抛出。
    """

    actual_limit = min(limit, max_results)
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise _DocFileAccessError(directory, "", "路径不是目录")

    matches: list[JsonValue] = []
    _raise_if_doc_cancelled(cancellation_token)
    for file_path in dir_path.rglob("*"):
        _raise_if_doc_cancelled(cancellation_token)
        if not file_path.is_file():
            continue
        resolved_file = _resolve_search_files_candidate(
            file_path=file_path,
            allowed_roots=allowed_roots,
        )
        if resolved_file is None:
            continue
        if include_types and resolved_file.suffix.lstrip(".") not in include_types:
            continue

        relative_path = str(file_path.relative_to(dir_path))
        processor = _try_create_processor(resolved_file)
        if processor is not None:
            _raise_if_doc_cancelled(cancellation_token)
            matches.extend(_search_via_processor(processor, relative_path, query, cancellation_token))
            if len(matches) >= actual_limit:
                break
            continue

        _raise_if_doc_cancelled(cancellation_token)
        matches.extend(
            _search_via_line_scan(
                resolved_file,
                relative_path,
                query,
                actual_limit - len(matches),
                cancellation_token,
            )
        )
        if len(matches) >= actual_limit:
            break

    matches = matches[:actual_limit]
    _raise_if_doc_cancelled(cancellation_token)
    return {
        "query": query,
        "directory": str(dir_path),
        "matches": matches,
        "total_matches": len(matches),
    }


def _resolve_search_files_candidate(
    *, file_path: Path, allowed_roots: tuple[Path, ...]
) -> Path | None:
    """解析 search_files 候选文件并重新校验真实路径 containment。

    Args:
        file_path: ``rglob`` 得到的候选路径。
        allowed_roots: 允许访问根路径。

    Returns:
        真实路径仍在允许根内时返回解析后的路径；否则返回 ``None``。

    Raises:
        无。
    """

    try:
        resolved_file = file_path.resolve(strict=True)
    except OSError:
        return None
    if not any(_is_relative_to(resolved_file, root) for root in allowed_roots):
        return None
    if not resolved_file.is_file():
        return None
    return resolved_file


def _read_file_business(
    *,
    file_path: str,
    start_line: int | None,
    end_line: int | None,
    cancellation_token: CancellationToken,
) -> JsonValue:
    """读取文件内容。

    Args:
        file_path: 已校验并归一化的文件路径。
        start_line: 起始行号。
        end_line: 结束行号。
        cancellation_token: Host 注入的取消观察令牌。

    Returns:
        文件内容 JSON 对象。

    Raises:
        _DocFileAccessError: 文件无法读取时抛出。
        _DocToolArgumentError: 行范围非法时抛出。
        _DocCancelledError: 观察到 Host 取消时抛出。
    """

    path = Path(file_path)
    lines: list[str] | None = None
    for encoding in _READ_FILE_ENCODINGS:
        try:
            _raise_if_doc_cancelled(cancellation_token)
            with open(path, "r", encoding=encoding) as file:
                lines = file.readlines()
            _raise_if_doc_cancelled(cancellation_token)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if lines is None:
        raise _DocFileAccessError(
            str(path.parent),
            path.name,
            f"无法读取文件，尝试过的编码: {list(_READ_FILE_ENCODINGS)}",
        )

    total_lines = len(lines)
    _raise_if_doc_cancelled(cancellation_token)
    actual_start_line = 1 if start_line is None else start_line
    actual_end_line = total_lines if end_line is None else end_line

    if actual_start_line < 1:
        raise _DocToolArgumentError(READ_FILE_TOOL_NAME, "start_line", actual_start_line, "必须 >= 1")
    if actual_end_line < actual_start_line:
        raise _DocToolArgumentError(
            READ_FILE_TOOL_NAME,
            "end_line",
            actual_end_line,
            f"必须 >= 起始行号 {actual_start_line}",
        )

    start_idx = actual_start_line - 1
    end_idx = min(actual_end_line, total_lines)
    selected_lines = lines[start_idx:end_idx]
    result: dict[str, JsonValue] = {
        "file_path": str(path),
        "content": "".join(selected_lines),
        "total_lines": total_lines,
    }
    if actual_start_line != 1 or actual_end_line != total_lines:
        result["line_range"] = [actual_start_line, end_idx]
    return result


def _read_file_section_business(
    *,
    file_path: str,
    ref: str,
    cancellation_token: CancellationToken,
) -> JsonValue:
    """按 section ref 读取文件章节内容。

    Args:
        file_path: 已校验并归一化的文件路径。
        ref: 章节 ref。
        cancellation_token: Host 注入的取消观察令牌。

    Returns:
        章节内容 JSON 对象。

    Raises:
        _DocToolArgumentError: 文件格式不支持或 ref 不存在时抛出。
        _DocCancelledError: 观察到 Host 取消时抛出。
    """

    path = Path(file_path)
    _raise_if_doc_cancelled(cancellation_token)
    processor = _try_create_processor(path)
    if processor is None:
        raise _DocToolArgumentError(
            READ_FILE_SECTION_TOOL_NAME,
            "file_path",
            file_path,
            f"该文件格式不支持 read_file_section。支持的格式: {_SUPPORTED_FORMATS_DESCRIPTION}。请使用 read_file 工具按行读取。",
        )

    try:
        _raise_if_doc_cancelled(cancellation_token)
        section_content = processor.read_section(ref)
    except KeyError:
        raise _DocToolArgumentError(
            READ_FILE_SECTION_TOOL_NAME,
            "ref",
            ref,
            "章节 ref 不存在，请通过 get_file_sections 获取有效的 ref",
        ) from None

    _raise_if_doc_cancelled(cancellation_token)
    children = _get_section_children(processor, ref, cancellation_token)
    content = section_content.get("content", "")
    table_refs: list[JsonValue] = list(section_content.get("tables", []))
    section_payload: dict[str, JsonValue] = {
        "file_path": str(path),
        "ref": ref,
        "title": section_content.get("title"),
        "content": content,
        "tables": table_refs,
        "children": children,
        "content_word_count": len(content.split()),
    }
    return section_payload


def _try_create_processor(path: Path) -> DocumentProcessor | None:
    """安全地尝试创建处理器。

    Args:
        path: 文件绝对路径。

    Returns:
        ``DocumentProcessor`` 实例或 ``None``。

    Raises:
        无；处理器创建异常会降级为 ``None``。
    """

    try:
        return create_doc_file_processor(path)
    except Exception as exc:
        Log.warn(f"创建处理器失败，降级处理: {path} - {exc}", module=MODULE)
        return None


def _sections_via_processor(
    processor: DocumentProcessor,
    path: Path,
    limit: int,
    cancellation_token: CancellationToken,
) -> JsonValue:
    """通过处理器获取章节列表并转换为工具输出格式。

    Args:
        processor: 文档处理器。
        path: 文件路径。
        limit: 最大返回数。
        cancellation_token: Host 注入的取消观察令牌。

    Returns:
        章节列表 JSON 对象。

    Raises:
        _DocCancelledError: 观察到 Host 取消时抛出。
    """

    raw_sections = processor.list_sections()
    _raise_if_doc_cancelled(cancellation_token)
    total_lines = _count_file_lines(path, cancellation_token)
    section_table_map: dict[str, list[str]] = {}
    try:
        for table in processor.list_tables():
            sec_ref = table.get("section_ref")
            if sec_ref:
                section_table_map.setdefault(sec_ref, []).append(table.get("table_ref", ""))
    except Exception:
        pass

    sections: list[JsonValue] = []
    for section_summary in raw_sections:
        ref = section_summary.get("ref")
        tbl_refs: list[JsonValue] = list(section_table_map.get(ref, [])) if ref else []
        section_payload: dict[str, JsonValue] = {
            "ref": ref,
            "title": section_summary.get("title"),
            "level": section_summary.get("level"),
            "parent_ref": section_summary.get("parent_ref"),
            "table_refs": tbl_refs,
            "table_count": len(tbl_refs),
            "preview": section_summary.get("preview", ""),
            "line_range": None,
            "line_count": None,
        }
        sections.append(section_payload)

    filtered = sections[:limit]
    return {
        "file_path": str(path),
        "sections": filtered,
        "total_sections": len(sections),
        "returned": len(filtered),
        "total_lines": total_lines,
    }


def _count_file_lines(path: Path, cancellation_token: CancellationToken) -> int:
    """计算文件总行数。

    Args:
        path: 文件路径。
        cancellation_token: Host 注入的取消观察令牌。

    Returns:
        文件行数；读取失败时返回 0。

    Raises:
        _DocCancelledError: 观察到 Host 取消时抛出。
    """

    try:
        with open(path, "r", encoding="utf-8") as file:
            total_lines = 0
            for total_lines, _line in enumerate(file, start=1):
                _raise_if_doc_cancelled_at_interval(cancellation_token, total_lines)
            _raise_if_doc_cancelled(cancellation_token)
            return total_lines
    except (UnicodeDecodeError, OSError):
        return 0


def _read_file_lines(path: Path) -> list[str] | None:
    """读取文件全部行，尝试多编码。

    Args:
        path: 文件路径。

    Returns:
        行列表；无法解码或读取失败时返回 ``None``。

    Raises:
        无。
    """

    for encoding in _READ_LINES_ENCODINGS:
        try:
            with open(path, "r", encoding=encoding) as file:
                return file.readlines()
        except UnicodeDecodeError:
            continue
        except OSError:
            return None
    return None


def _extract_markdown_sections(
    lines: list[str],
    cancellation_token: CancellationToken,
) -> list[dict[str, JsonValue]]:
    """从 Markdown 行中提取章节结构。

    Args:
        lines: 文件行列表。
        cancellation_token: Host 注入的取消观察令牌。

    Returns:
        section 字典列表；没有标题时返回空列表。

    Raises:
        _DocCancelledError: 观察到 Host 取消时抛出。
    """

    sections: list[dict[str, JsonValue]] = []
    current_section: dict[str, JsonValue] | None = None
    for line_num, line in enumerate(lines, start=1):
        _raise_if_doc_cancelled_at_interval(cancellation_token, line_num)
        match = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if match is None:
            continue
        if current_section is not None:
            line_range = cast(list[JsonValue], current_section["line_range"])
            start_line_value = cast(int, line_range[0])
            line_range[1] = line_num - 1
            current_section["line_count"] = line_num - start_line_value
            sections.append(current_section)

        title = match.group(2).strip()
        level = len(match.group(1))
        current_section = {
            "ref": None,
            "title": title,
            "level": level,
            "parent_ref": None,
            "table_refs": [],
            "table_count": 0,
            "line_range": [line_num, line_num],
            "line_count": 1,
            "preview": "",
        }

    if current_section is not None:
        line_range = cast(list[JsonValue], current_section["line_range"])
        start_line_value = cast(int, line_range[0])
        line_range[1] = len(lines)
        current_section["line_count"] = len(lines) - start_line_value + 1
        sections.append(current_section)

    for section_index, section in enumerate(sections, start=1):
        _raise_if_doc_cancelled_at_interval(cancellation_token, section_index)
        line_range = cast(list[JsonValue], section["line_range"])
        start_line = cast(int, line_range[0])
        end_line = min(cast(int, line_range[1]), start_line + 10)
        preview_lines = lines[start_line - 1:end_line]
        section["preview"] = "".join(preview_lines).strip()[:150]
    return sections


def _fallback_single_section(
    file_path: str,
    path: Path,
    cancellation_token: CancellationToken,
    total_lines: int | None = None,
) -> JsonValue:
    """返回覆盖整个文件的 fallback 单章节。

    Args:
        file_path: 文件路径字符串。
        path: 文件路径对象。
        cancellation_token: Host 注入的取消观察令牌。
        total_lines: 已知总行数。

    Returns:
        单章节 JSON 对象。

    Raises:
        _DocCancelledError: 观察到 Host 取消时抛出。
    """

    del file_path
    actual_total_lines = _count_file_lines(path, cancellation_token) if total_lines is None else total_lines
    section: dict[str, JsonValue] = {
        "ref": None,
        "title": path.name,
        "level": None,
        "parent_ref": None,
        "table_refs": [],
        "table_count": 0,
        "line_range": [1, actual_total_lines] if actual_total_lines > 0 else None,
        "line_count": actual_total_lines,
        "preview": f"整个文件（{path.name}）",
    }
    return {
        "file_path": str(path),
        "sections": [section],
        "total_sections": 1,
        "returned": 1,
        "total_lines": actual_total_lines,
    }


def _search_via_processor(
    processor: DocumentProcessor,
    relative_path: str,
    query: str,
    cancellation_token: CancellationToken,
) -> list[JsonValue]:
    """通过处理器搜索文件内容。

    Args:
        processor: 文档处理器。
        relative_path: 文件相对路径。
        query: 搜索关键词。
        cancellation_token: Host 注入的取消观察令牌。

    Returns:
        标准化匹配列表。

    Raises:
        _DocCancelledError: 观察到 Host 取消时抛出。
    """

    try:
        _raise_if_doc_cancelled(cancellation_token)
        hits = processor.search(query)
    except _DocCancelledError:
        raise
    except Exception as exc:
        Log.warn(f"处理器搜索失败: {relative_path} - {exc}", module=MODULE)
        return []

    matches: list[JsonValue] = []
    for hit in hits:
        matches.append(
            {
                "file": relative_path,
                "line_number": None,
                "ref": hit.get("section_ref"),
                "section_title": hit.get("section_title"),
                "snippet": hit.get("snippet", ""),
                "matched_line_content": None,
            }
        )
    return matches


def _search_via_line_scan(
    file_path: Path,
    relative_path: str,
    query: str,
    remaining: int,
    cancellation_token: CancellationToken,
) -> list[dict[str, JsonValue]]:
    """通过行扫描搜索文件内容。

    Args:
        file_path: 文件绝对路径。
        relative_path: 文件相对路径。
        query: 搜索关键词。
        remaining: 剩余可返回匹配数。
        cancellation_token: Host 注入的取消观察令牌。

    Returns:
        匹配字典列表。

    Raises:
        _DocCancelledError: 观察到 Host 取消时抛出。
    """

    query_lower = query.lower()
    matches: list[dict[str, JsonValue]] = []
    try:
        _raise_if_doc_cancelled(cancellation_token)
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
    except (UnicodeDecodeError, OSError):
        return []

    snippets = extract_query_anchored_snippets(content, query)
    if not snippets:
        return []

    lines = content.split("\n")
    snippet_idx = 0
    for line_num, line in enumerate(lines, start=1):
        _raise_if_doc_cancelled_at_interval(cancellation_token, line_num)
        if query_lower not in line.lower():
            continue
        snippet_text = snippets[snippet_idx] if snippet_idx < len(snippets) else line.strip()[:150]
        matches.append(
            {
                "file": relative_path,
                "line_number": line_num,
                "ref": None,
                "section_title": None,
                "snippet": snippet_text,
                "matched_line_content": line.strip(),
            }
        )
        snippet_idx += 1
        if len(matches) >= remaining:
            break
    return matches


def _raise_if_doc_cancelled_at_interval(
    cancellation_token: CancellationToken,
    item_index: int,
) -> None:
    """按固定间隔执行协作式取消检查。

    Args:
        cancellation_token: Host 注入的取消观察令牌。
        item_index: 从 1 开始的循环项序号。

    Returns:
        无。

    Raises:
        _DocCancelledError: 到达检查点且 Host 已请求取消时抛出。
    """

    if item_index % _DOC_LOOP_CANCELLATION_CHECK_INTERVAL == 0:
        _raise_if_doc_cancelled(cancellation_token)


def _get_section_children(
    processor: DocumentProcessor,
    parent_ref: str,
    cancellation_token: CancellationToken,
) -> list[JsonValue]:
    """获取指定章节的直接子章节列表。

    Args:
        processor: 文档处理器。
        parent_ref: 父章节 ref。
        cancellation_token: Host 注入的取消观察令牌。

    Returns:
        子章节导航列表。

    Raises:
        _DocCancelledError: 观察到 Host 取消时抛出。
    """

    children: list[JsonValue] = []
    try:
        _raise_if_doc_cancelled(cancellation_token)
        all_sections = processor.list_sections()
    except _DocCancelledError:
        raise
    except Exception:
        return children

    for section_summary in all_sections:
        _raise_if_doc_cancelled(cancellation_token)
        if section_summary.get("parent_ref") == parent_ref:
            children.append(
                {
                    "ref": section_summary.get("ref"),
                    "title": section_summary.get("title"),
                    "level": section_summary.get("level"),
                    "preview": section_summary.get("preview", ""),
                }
            )
    return children


def _raise_if_doc_cancelled(cancellation_token: CancellationToken | None) -> None:
    """在可能较慢的文档处理边界执行协作式取消检查。

    Args:
        cancellation_token: Host 注入的取消观察令牌。

    Returns:
        无。

    Raises:
        _DocCancelledError: Host 已请求取消当前工具调用时抛出。
    """

    if cancellation_token is not None and cancellation_token.is_cancelled():
        _raise_doc_cancelled()


def _raise_doc_cancelled() -> NoReturn:
    """抛出携带 ``ToolBusinessCancelled`` 的本地取消信号。

    Args:
        无。

    Returns:
        不返回。

    Raises:
        _DocCancelledError: 始终抛出。
    """

    raise _DocCancelledError(_doc_cancelled())


def _doc_cancelled() -> ToolBusinessCancelled:
    """构造 Doc 深层 helper 使用的取消语义。

    Args:
        无。

    Returns:
        取消语义结果。

    Raises:
        无。
    """

    return ToolBusinessCancelled(message="文档工具调用已停止。", hint=_DOC_CANCELLED_HINT)


def _cancelled_outcome(
    tool_name: str,
    started_at: datetime,
    cancellation: ToolBusinessCancelled,
) -> ToolExecutionOutcome:
    """把内部取消语义投影为 Host cancelled outcome。

    Args:
        tool_name: 工具名。
        started_at: callable 开始时间。
        cancellation: 内部取消语义。

    Returns:
        ``ToolCancelledOutcome``。

    Raises:
        Exception: outcome 契约构造失败时透出。
    """

    return host_cancelled_outcome(
        tool_name=tool_name,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        message=cancellation.message,
        hint=cancellation.hint,
    )


def _tool_definition(
    *,
    name: str,
    description: str,
    parameters: ToolParametersSchema,
    callable_: ToolCallable,
    display_name: str,
    truncate: ToolTruncateSpec | None,
    process_target_factory: _DocProcessTargetFactory,
) -> ToolDefinition:
    """构造 current ``ToolDefinition``。

    Args:
        name: 工具名。
        description: LLM-facing 描述。
        parameters: LLM-facing 参数 schema。
        callable_: current 工具 callable。
        display_name: 展示名称。
        truncate: 截断声明。
        process_target_factory: process-backed 目标工厂。

    Returns:
        工具定义。

    Raises:
        Exception: 工具定义契约构造失败时透出。
    """

    return ToolDefinition(
        name=name,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=name,
                description=description,
                parameters=parameters,
            ),
        ),
        callable=callable_,
        execution=ProcessBackedToolExecutionCapability(
            target_factory=process_target_factory,
        ),
        truncate=truncate,
        display=ToolDisplayInfo(name=display_name),
        tags=_DOC_TOOL_TAGS,
    )


def _list_files_parameters(max_files: int) -> ToolParametersSchema:
    """构造 ``list_files`` 参数 schema。

    Args:
        max_files: 最大返回文件数。

    Returns:
        current 参数 schema。

    Raises:
        Exception: schema 契约构造失败时透出。
    """

    return _parameters_schema(
        properties={
            "directory": {
                "type": "string",
                "description": "起点目录，必须是当前配置允许访问且实际存在的目录。先用它列出文件，再从返回的 files[].path 里选具体文件继续读取；不要猜不存在的路径。",
            },
            "pattern": {
                "type": "string",
                "description": "可选文件名通配符，例如 *.json、*.md。只在你明确要收窄文件范围时填写。",
            },
            "recursive": {
                "type": "boolean",
                "description": "是否递归子目录。目录层级不确定时设为 true。",
                "default": False,
            },
            "limit": {
                "type": "integer",
                "description": f"最多返回多少个文件。默认 20，最大 {max_files}。",
                "default": 20,
                "minimum": 1,
                "maximum": max_files,
            },
        },
        required=("directory",),
    )


def _get_file_sections_parameters(max_sections: int) -> ToolParametersSchema:
    """构造 ``get_file_sections`` 参数 schema。

    Args:
        max_sections: 最大返回章节数。

    Returns:
        current 参数 schema。

    Raises:
        Exception: schema 契约构造失败时透出。
    """

    return _parameters_schema(
        properties={
            "file_path": {
                "type": "string",
                "description": "文件路径，必须是当前配置允许访问且实际存在的文件。优先使用 list_files 返回的 files[].path；大文件先用本工具定位章节，再读具体章节。",
            },
            "limit": {
                "type": "integer",
                "description": f"最多返回多少个章节。默认 10，最大 {max_sections}。",
                "default": 10,
                "minimum": 1,
                "maximum": max_sections,
            },
        },
        required=("file_path",),
    )


def _search_files_parameters(max_results: int) -> ToolParametersSchema:
    """构造 ``search_files`` 参数 schema。

    Args:
        max_results: 最大返回命中数。

    Returns:
        current 参数 schema。

    Raises:
        Exception: schema 契约构造失败时透出。
    """

    return _parameters_schema(
        properties={
            "query": {
                "type": "string",
                "description": "搜索词或短语。优先传单个明确概念；避免一次塞入过多无关关键词。",
            },
            "directory": {
                "type": "string",
                "description": "起点目录，必须是当前配置允许访问且实际存在的目录。先在这个目录里找命中文件，再把匹配结果交给 read_file_section 或 read_file。",
            },
            "include_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": '可选文件扩展名过滤，例如 ["py", "md", "json"]。只在你明确要限制文件类型时填写。',
            },
            "limit": {
                "type": "integer",
                "description": f"最多返回多少条命中。默认 20，最大 {max_results}。",
                "default": 20,
                "minimum": 1,
                "maximum": max_results,
            },
        },
        required=("directory", "query"),
    )


def _read_file_parameters() -> ToolParametersSchema:
    """构造 ``read_file`` 参数 schema。

    Args:
        无。

    Returns:
        current 参数 schema。

    Raises:
        Exception: schema 契约构造失败时透出。
    """

    return _parameters_schema(
        properties={
            "file_path": {
                "type": "string",
                "description": "文件路径，必须是当前配置允许访问且实际存在的文件。优先使用 list_files 返回的 files[].path。没有章节 ref、或文件不支持章节读取时用它。",
            },
            "start_line": {
                "type": "integer",
                "description": "起始行号，从 1 开始，包含该行。不填则从第 1 行开始读。",
                "minimum": 1,
            },
            "end_line": {
                "type": "integer",
                "description": "结束行号，从 1 开始，包含该行。不填则读到文件末尾。",
                "minimum": 1,
            },
        },
        required=("file_path",),
    )


def _read_file_section_parameters() -> ToolParametersSchema:
    """构造 ``read_file_section`` 参数 schema。

    Args:
        无。

    Returns:
        current 参数 schema。

    Raises:
        Exception: schema 契约构造失败时透出。
    """

    return _parameters_schema(
        properties={
            "file_path": {
                "type": "string",
                "description": "文件路径，必须是当前配置允许访问且实际存在的文件。优先使用 list_files 返回的 files[].path，或当前已知的允许访问路径。",
            },
            "ref": {
                "type": "string",
                "description": "必须来自 get_file_sections 返回的 sections[].ref。若 get_file_sections 里 ref 为 null，就改用 read_file，不要猜 ref。",
            },
        },
        required=("file_path", "ref"),
    )


def _parameters_schema(
    *,
    properties: Mapping[str, JsonValue],
    required: tuple[str, ...],
) -> ToolParametersSchema:
    """构造 Doc 工具参数 schema。

    Args:
        properties: 顶层属性 schema。
        required: 必填字段名。

    Returns:
        current ``ToolParametersSchema``。

    Raises:
        Exception: schema 契约构造失败时透出。
    """

    return ToolParametersSchema(
        type="object",
        properties=properties,
        required=required,
        additional_properties=None,
    )


def _text_content_truncate(max_chars: int) -> ToolTruncateSpec:
    """构造 content 字段文本截断声明。

    Args:
        max_chars: 最大字符数。

    Returns:
        current 截断声明。

    Raises:
        Exception: 截断声明契约构造失败时透出。
    """

    return ToolTruncateSpec(
        enabled=True,
        strategy=ToolTruncationStrategy.TEXT_CHARS,
        limits={"max_chars": max_chars},
        target_field="content",
        field_path=None,
        ttl_seconds=None,
    )


def _project_tool_response_paths(tool_name: str, raw_value: JsonValue) -> JsonValue:
    """把 list/search 返回中的可链式路径投影为绝对路径。

    Args:
        tool_name: 工具名。
        raw_value: 原始业务返回值。

    Returns:
        路径字段已归一化的 JSON 值。

    Raises:
        无。
    """

    if tool_name == LIST_FILES_TOOL_NAME:
        return _project_list_files_response(raw_value)
    if tool_name == SEARCH_FILES_TOOL_NAME:
        return _project_search_files_response(raw_value)
    return raw_value


def _project_list_files_response(raw_value: JsonValue) -> JsonValue:
    """投影 ``list_files`` 返回的 ``files[].path`` 字段。

    Args:
        raw_value: 原始业务返回值。

    Returns:
        投影后的 JSON 值。

    Raises:
        无。
    """

    if not isinstance(raw_value, Mapping):
        return raw_value
    payload = cast(Mapping[str, JsonValue], raw_value)
    directory = payload.get("directory")
    files = payload.get("files")
    if not isinstance(directory, str) or not isinstance(files, list):
        return raw_value
    projected_files: list[JsonValue] = []
    for item in files:
        if isinstance(item, Mapping):
            projected_files.append(_project_record_path(cast(Mapping[str, JsonValue], item), base_directory=directory, field_name="path"))
        else:
            projected_files.append(item)
    projected_payload: dict[str, JsonValue] = dict(payload)
    projected_payload["files"] = projected_files
    return projected_payload


def _project_search_files_response(raw_value: JsonValue) -> JsonValue:
    """投影 ``search_files`` 返回的 ``matches[].file`` 字段。

    Args:
        raw_value: 原始业务返回值。

    Returns:
        投影后的 JSON 值。

    Raises:
        无。
    """

    if not isinstance(raw_value, Mapping):
        return raw_value
    payload = cast(Mapping[str, JsonValue], raw_value)
    directory = payload.get("directory")
    matches = payload.get("matches")
    if not isinstance(directory, str) or not isinstance(matches, list):
        return raw_value
    projected_matches: list[JsonValue] = []
    for item in matches:
        if isinstance(item, Mapping):
            projected_matches.append(_project_record_path(cast(Mapping[str, JsonValue], item), base_directory=directory, field_name="file"))
        else:
            projected_matches.append(item)
    projected_payload: dict[str, JsonValue] = dict(payload)
    projected_payload["matches"] = projected_matches
    return projected_payload


def _project_record_path(
    record: Mapping[str, JsonValue],
    *,
    base_directory: str,
    field_name: str,
) -> Mapping[str, JsonValue]:
    """把记录中的相对路径字段投影为基于目录的绝对路径。

    Args:
        record: 单条返回记录。
        base_directory: 记录所属目录。
        field_name: 需要投影的路径字段名。

    Returns:
        投影后的记录。

    Raises:
        无。
    """

    path_value = record.get(field_name)
    if not isinstance(path_value, str) or path_value.strip() == "":
        return record
    projected_record: dict[str, JsonValue] = dict(record)
    projected_record[field_name] = _project_response_path(base_directory, path_value)
    return projected_record


def _project_response_path(base_directory: str, path_value: str) -> str:
    """把工具返回路径归一化为绝对路径。

    Args:
        base_directory: 返回路径所属目录。
        path_value: 原始返回路径。

    Returns:
        绝对路径字符串。

    Raises:
        无。
    """

    path = Path(path_value).expanduser()
    if path.is_absolute():
        return str(path.resolve(strict=False))
    return str((Path(base_directory) / path).expanduser().resolve(strict=False))


def _sort_record_by_name(value: JsonValue) -> str:
    """按文件记录名称排序。

    Args:
        value: 文件记录 JSON 值。

    Returns:
        文件名；结构异常时返回空字符串。

    Raises:
        无。
    """

    if not isinstance(value, Mapping):
        return ""
    name = value.get("name")
    return name if isinstance(name, str) else ""


def _required_string(arguments: Mapping[str, JsonValue], field_name: str) -> str:
    """读取已校验的必填字符串参数。

    Args:
        arguments: 已校验参数。
        field_name: 字段名。

    Returns:
        字符串参数值。

    Raises:
        AssertionError: schema 校验后字段类型仍不符合预期时抛出。
    """

    value = arguments[field_name]
    assert isinstance(value, str)
    return value


def _optional_string(arguments: Mapping[str, JsonValue], field_name: str) -> str | None:
    """读取已校验的可选字符串参数。

    Args:
        arguments: 已校验参数。
        field_name: 字段名。

    Returns:
        字符串参数值或 ``None``。

    Raises:
        AssertionError: 字段存在但类型不符合预期时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return None
    assert isinstance(value, str)
    return value


def _required_bool(arguments: Mapping[str, JsonValue], field_name: str) -> bool:
    """读取已校验的必填布尔参数。

    Args:
        arguments: 已校验参数。
        field_name: 字段名。

    Returns:
        布尔参数值。

    Raises:
        AssertionError: schema 校验后字段类型仍不符合预期时抛出。
    """

    value = arguments[field_name]
    assert isinstance(value, bool)
    return value


def _required_int(arguments: Mapping[str, JsonValue], field_name: str) -> int:
    """读取已校验的必填整数参数。

    Args:
        arguments: 已校验参数。
        field_name: 字段名。

    Returns:
        整数参数值。

    Raises:
        AssertionError: schema 校验后字段类型仍不符合预期时抛出。
    """

    value = arguments[field_name]
    assert isinstance(value, int) and not isinstance(value, bool)
    return value


def _optional_int(arguments: Mapping[str, JsonValue], field_name: str) -> int | None:
    """读取已校验的可选整数参数。

    Args:
        arguments: 已校验参数。
        field_name: 字段名。

    Returns:
        整数参数值或 ``None``。

    Raises:
        AssertionError: 字段存在但类型不符合预期时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return None
    assert isinstance(value, int) and not isinstance(value, bool)
    return value


def _optional_string_list(
    arguments: Mapping[str, JsonValue],
    field_name: str,
) -> list[str] | None:
    """读取已校验的可选字符串列表参数。

    Args:
        arguments: 已校验参数。
        field_name: 字段名。

    Returns:
        字符串列表或 ``None``。

    Raises:
        AssertionError: 字段存在但类型不符合预期时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return None
    assert isinstance(value, list)
    result: list[str] = []
    for item in value:
        assert isinstance(item, str)
        result.append(item)
    return result


__all__ = [
    "DOC_TOOL_NAMES",
    "DocToolLimits",
    "build_doc_tool_definitions",
]
