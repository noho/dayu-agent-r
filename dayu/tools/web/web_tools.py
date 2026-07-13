"""联网检索工具模块。

该模块提供写作流水线使用的联网检索能力，包含：
- `search_web`：按关键词检索公开网页。
- `fetch_web_page`：抓取网页正文文本。

设计约束：
- 仅允许访问 `http/https` 地址。
- 拒绝内网、回环地址与本地地址。
- Provider 选择遵循：`tavily` -> `serper` -> `duckduckgo`。

维护说明(不拆分本模块):
    本模块约 2000 行, 核心是 search_web 和 fetch_web_page 两个工厂
    函数. fetch 路径是一条线性 pipeline(requests -> content-type 探测
    -> docling 转换 -> playwright fallback -> URL 安全检查), 各工具
    函数互相依赖. Playwright 子系统虽有 330 行, 但深度嵌入 fetch 的
    重试/fallback 逻辑, 拆分会引入大量参数传递. 外部仅消费
    build_web_tool_definitions 一个符号.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import ssl
import time
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final, NoReturn, Optional, TypeAlias, TypedDict, cast
from urllib.parse import quote, urlparse

import requests
from requests.utils import requote_uri
from urllib3.exceptions import ReadTimeoutError as Urllib3ReadTimeoutError

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_execution import (
    ProcessBackedToolContext,
    ProcessBackedToolExecutionCapability,
    process_tool_completed_envelope,
    process_tool_failed_envelope,
)
from dayu.contracts.tool_declaration import ToolDefinition, tool
from dayu.contracts.tool_outcome import ToolExecutionOutcome
from dayu.contracts.tool_schema import ToolParametersSchema, ToolTruncateSpec, ToolTruncationStrategy
from dayu.documents.processors.html_pipeline import HtmlPipelineStageError, convert_html_to_llm_markdown
from dayu.runtime.tool_call_projection import (
    ToolArgumentValidationFailure,
    completed_outcome,
    failed_outcome,
    host_cancelled_outcome,
    validate_and_project_arguments,
)

from . import web_fetch_orchestrator as _web_fetch_orchestrator
from . import web_playwright_backend as _web_playwright_backend
from .web_challenge_detection import (
    BotChallengeDecision,
    ChallengeFallbackAction,
    challenge_fallback_action,
    detect_bot_challenge as _detect_bot_challenge,
)
from .web_http_encoding import (
    _decode_response_text,
    _extract_charset_from_content_type,
    _extract_charset_from_html_bytes,
    _extract_content_encoding_tokens,
    _normalize_charset_name,
    _resolve_response_text_encoding,
)
from .web_egress_policy import WebEgressPolicy
from .web_http_session import (
    _compute_deadline_monotonic,
    _create_no_retry_session,
    _create_retry_session,
    _get_no_retry_web_session,
    _get_web_session,
    _normalize_timeout_budget,
    _prepare_call_session,
    _resolve_timeout_budget,
    _safe_timeout,
)
from .web_diagnostics import (
    WebDiagnosticBackend,
    WebDiagnosticProjection,
    completed_text_projection,
    failed_projection,
    project_safe_url_or_empty,
)
from .web_recovery import (
    NEXT_ACTION_CHANGE_SOURCE,
    NEXT_ACTION_CONTINUE_WITHOUT_WEB,
    NEXT_ACTION_RETRY,
    REASON_BLOCKED_BY_SITE_POLICY,
    REASON_CONTENT_CONVERSION_FAILED,
    REASON_EMPTY_CONTENT,
    REASON_HTTP_ERROR,
    REASON_REDIRECT_CHAIN_TOO_LONG,
    REASON_REQUEST_TIMEOUT,
    build_hint,
    normalize_next_action,
    normalize_reason,
)
from .web_search_projection import SearchWebOutput, build_search_web_output
from .web_search_providers import (
    SearchWebProviderResult,
    WebSearchCancelledError,
    WebSearchProviderResourceError,
    WebSearchProviderResponseError,
    WebSearchProviderUnavailableError,
    search_public_web,
)
from .web_resource_budget import WebResourceBudget
from .web_tool_projection_text import (
    WEB_CANCELLED_HINT,
    WEB_FETCH_CANCELLED_MESSAGE,
    WEB_SEARCH_PROVIDER_UNAVAILABLE_HINT,
    WEB_SEARCH_RESPONSE_BODY_TOO_LARGE_HINT,
    WEB_SEARCH_PROVIDER_RESPONSE_INVALID_HINT,
    WEB_SEARCH_CANCELLED_MESSAGE,
)

MODULE = "ENGINE.WEB_TOOLS"
_LOGGER = logging.getLogger(__name__)
SEC_USER_AGENT_ENV = "SEC_USER_AGENT"

_ALLOWED_SCHEMES = {"http", "https"}
_BOUNDED_ACCEPT_ENCODING: Final[str] = "gzip, deflate"

_DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
_DEFAULT_SEC_USER_AGENT = "Codex Web Fetcher support@example.com"
_DEFAULT_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
_DEFAULT_ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9,en;q=0.8"

# --- Client Hints（现代 Chrome 必带，缺失是典型爬虫特征）---
_DEFAULT_SEC_CH_UA = '"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"'
_DEFAULT_SEC_CH_UA_MOBILE = "?0"
_DEFAULT_SEC_CH_UA_PLATFORM = '"macOS"'

_EMPTY_CONTENT_MIN_CHARS = 5
_SEARCH_WEB_TOOL_NAME: Final[str] = "search_web"
_FETCH_WEB_PAGE_TOOL_NAME: Final[str] = "fetch_web_page"
_WEB_TOOL_TAGS: Final[tuple[str, ...]] = ("web",)
_SEARCH_WEB_DEFAULT_MAX_RESULTS: Final[int] = 8
_SEARCH_TRUNCATE_ITEMS: Final[int] = 10
_FETCH_WEB_PAGE_PARAMETERS: Final[ToolParametersSchema] = ToolParametersSchema(
    type="object",
    properties={
        "url": {
            "type": "string",
        },
    },
    required=("url",),
    additional_properties=False,
)
_SEARCH_PROVIDER_UNAVAILABLE_ERROR: Final[str] = "search_provider_unavailable"
_SEARCH_PROVIDER_RESPONSE_INVALID_ERROR: Final[str] = "search_provider_response_invalid"
_RESPONSE_BODY_TOO_LARGE_ERROR: Final[str] = "response_body_too_large"
_DEFAULT_WEB_DIAGNOSTIC_ERROR_CHARS: Final[int] = (
    WebResourceBudget().diagnostic_error_chars
)
WebPayload: TypeAlias = dict[str, JsonValue]
WebMapping: TypeAlias = Mapping[str, JsonValue]
StagePayload: TypeAlias = dict[str, str | bool | int | float | None]
ContentProbePayload: TypeAlias = dict[str, str | bool | int | None]
_FetchContentRuntimeContext = _web_fetch_orchestrator._FetchContentRuntimeContext


@dataclass(frozen=True, slots=True)
class WebToolsConfig:
    """Web 工具 provider 配置。

    :param provider: 搜索 provider 策略。
    :param request_timeout_seconds: HTTP 请求超时秒数。
    :param max_search_results: 搜索最大返回条数。
    :param fetch_truncate_chars: 抓取正文截断声明字符数。
    :param allow_private_network_url: 是否允许内网 / 本地 URL。
    :param playwright_channel: Playwright fallback 使用的浏览器 channel。
    :param playwright_storage_state_dir: Playwright storage state 目录。
    :param resource_budget: HTTP、browser 与诊断共享的完整资源预算。
    :returns: dataclass 实例本身。
    :raises Exception: 构造期不主动抛出异常。
    """

    provider: str = "auto"
    request_timeout_seconds: float = 12.0
    max_search_results: int = 20
    fetch_truncate_chars: int = 80_000
    allow_private_network_url: bool = False
    playwright_channel: str | None = "chrome"
    playwright_storage_state_dir: str = ""
    resource_budget: WebResourceBudget = WebResourceBudget()


class _FetchContentResult(TypedDict, total=False):
    """requests 抓取转换结果的窄结构。"""

    title: str
    content: str
    extraction_source: str
    renderer_source: str
    normalization_applied: bool
    quality_flags: list[str]
    content_stats: WebMapping
    http_status: int
    final_url: str
    redirect_hops: int
    response_headers: Mapping[str, str]
    response_content_length: int
    response_content_digest: str


class _PlaywrightFallbackKwargs(TypedDict, total=False):
    """fetch 主流程复用的 Playwright fallback 参数。"""

    timeout_seconds: float
    headers: dict[str, str]
    timeout_budget: float | None
    deadline_monotonic: float | None
    playwright_channel: str | None
    playwright_storage_state_path: str
    egress_policy: WebEgressPolicy
    resource_budget: WebResourceBudget
    cancellation_token: CancellationToken


class _StageFetchKwargs(TypedDict, total=False):
    """requests 阶段调用的共享参数。"""

    url: str
    timeout_seconds: float
    headers: dict[str, str]
    timeout_budget: float | None
    deadline_monotonic: float | None
    egress_policy: WebEgressPolicy
    resource_budget: WebResourceBudget
    cancellation_token: CancellationToken


class _FetchConvertKwargs(TypedDict, total=False):
    """正文下载转换阶段的共享参数。"""

    timeout_seconds: float
    session: requests.Session
    headers: dict[str, str]
    content_type_probe: ContentProbePayload
    timeout_budget: float | None
    deadline_monotonic: float | None
    egress_policy: WebEgressPolicy
    resource_budget: WebResourceBudget
    cancellation_token: CancellationToken


class Log:
    """迁移 Web 工具的窄日志适配器。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    @staticmethod
    def debug(message: str, *, module: str | None = None) -> None:
        """记录 debug 日志。

        Args:
            message: 日志正文。
            module: 模块标签。

        Returns:
            无。

        Raises:
            无。
        """

        _LOGGER.debug("[%s] %s", module or MODULE, message)

    @staticmethod
    def verbose(message: str, *, module: str | None = None) -> None:
        """记录 verbose 日志。

        Args:
            message: 日志正文。
            module: 模块标签。

        Returns:
            无。

        Raises:
            无。
        """

        _LOGGER.debug("[%s] %s", module or MODULE, message)


class ToolBusinessError(Exception):
    """Web 工具业务错误。

    Args:
        code: 错误码。
        message: 面向 LLM 的错误说明。
        hint: 恢复提示。
        url: 原始 URL。
        next_action: 建议下一步动作。
        http_status: 可选 HTTP 状态码。
        internal_diagnostics: 内部诊断信息。

    Returns:
        无。

    Raises:
        无。
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        hint: str = "",
        url: str = "",
        next_action: str = "",
        http_status: int | None = None,
        internal_diagnostics: WebMapping | None = None,
    ) -> None:
        """初始化 Web 工具业务错误。

        Args:
            code: 错误码。
            message: 错误说明。
            hint: 恢复提示。
            url: 原始 URL。
            next_action: 建议下一步动作。
            http_status: 可选 HTTP 状态码。
            internal_diagnostics: 内部诊断。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.url = url
        self.next_action = next_action
        self.http_status = http_status
        self.internal_diagnostics = internal_diagnostics or {}


class WebToolCancelledError(Exception):
    """Web 工具观察到 Host 取消时的模块内异常。

    :param message: 面向 LLM 的取消说明。
    :param hint: 恢复提示。
    :returns: 无。
    :raises Exception: 构造期不主动抛出异常。
    """

    def __init__(self, message: str, hint: str) -> None:
        """初始化取消异常。

        :param message: 取消说明。
        :param hint: 恢复提示。
        :returns: ``None``。
        :raises Exception: 构造期不主动抛出异常。
        """

        super().__init__(message)
        self.message = message
        self.hint = hint


class _WebProcessCancellationToken:
    """Web process target 内部使用的不可取消 token。

    子进程不共享 Host cancellation token；生产取消、超时和 hard kill 由
    父进程 ToolRuntime process capsule 独占治理。本 token 只满足 Web
    同步业务 helper 的类型边界，避免子进程伪造 host_cancelled / timeout
    结果。
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


@dataclass(frozen=True, slots=True)
class _WebProcessTarget:
    """Web process-backed 子进程目标。

    本目标只保存 spawn 可序列化的工具名、参数 JSON 副本、Web provider
    配置和 timeout 标量；不得捕获 requests Session、provider lock、
    CancellationToken、Host / Run / Session 对象或 Playwright runtime /
    browser 对象。

    Args:
        tool_name: 工具名。
        arguments: 工具调用参数 JSON 副本。
        config: Web provider 可序列化配置。
        timeout_seconds: 父进程投影的批级 timeout 标量；真实超时 closeout
            由父进程 Host capsule 独占治理，同时该值继续传入 HTTP /
            browser 阶段作为预算。

    Returns:
        dataclass 实例。

    Raises:
        无。
    """

    tool_name: str
    arguments: dict[str, JsonValue]
    config: WebToolsConfig
    timeout_seconds: float | None

    def __call__(self) -> JsonValue:
        """在子进程内重建 Web runtime 并执行同步业务。

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
            value = _execute_web_process_business_value(
                tool_name=self.tool_name,
                call=call,
                config=self.config,
                timeout_budget=self.timeout_seconds,
            )
        except ToolBusinessError as failure:
            return _web_process_failed_envelope(
                error_type=failure.code,
                message=failure.message,
                hint=failure.hint,
            )
        except WebSearchProviderResponseError as failure:
            return _web_process_failed_envelope(
                error_type=_SEARCH_PROVIDER_RESPONSE_INVALID_ERROR,
                message=failure.message,
                hint=WEB_SEARCH_PROVIDER_RESPONSE_INVALID_HINT,
            )
        except WebSearchProviderResourceError as failure:
            return _web_process_failed_envelope(
                error_type=_RESPONSE_BODY_TOO_LARGE_ERROR,
                message=failure.message,
                hint=WEB_SEARCH_RESPONSE_BODY_TOO_LARGE_HINT,
            )
        except WebSearchProviderUnavailableError as failure:
            return _web_process_failed_envelope(
                error_type=_SEARCH_PROVIDER_UNAVAILABLE_ERROR,
                message=failure.message,
                hint=WEB_SEARCH_PROVIDER_UNAVAILABLE_HINT,
            )
        except (WebToolCancelledError, WebSearchCancelledError):
            return _web_process_failed_envelope(
                error_type="execution_error",
                message=f"Tool {self.tool_name!r} execution was interrupted inside child process.",
                hint="Parent ToolRuntime owns cancellation and timeout closeout.",
            )
        except Exception:
            return process_tool_failed_envelope(
                error_type="execution_error",
                message=f"Tool {self.tool_name!r} execution failed.",
            )
        return process_tool_completed_envelope(value)


@dataclass(frozen=True, slots=True)
class _WebProcessTargetFactory:
    """Web process-backed target factory。

    本 factory 只保存 spawn 可序列化的 Web provider 配置，不捕获
    requests Session、provider lock、CancellationToken、Host / Run /
    Session 对象或 Playwright runtime / browser 对象。

    Args:
        config: Web provider 可序列化配置。

    Returns:
        dataclass 实例。

    Raises:
        无。
    """

    config: WebToolsConfig

    def build_process_target(
        self,
        call: ToolCallRequest,
        context: ProcessBackedToolContext,
    ) -> _WebProcessTarget:
        """构造可序列化 Web 子进程目标。

        Args:
            call: 单次工具调用请求。
            context: Host 投影出的可序列化 process-backed 上下文。

        Returns:
            Web 子进程目标。

        Raises:
            无。
        """

        return _WebProcessTarget(
            tool_name=call.name,
            arguments=dict(call.arguments),
            config=self.config,
            timeout_seconds=context.timeout_seconds,
        )


_FetchBodyLimitExceeded = _web_fetch_orchestrator._FetchBodyLimitExceeded
_FetchContentConversionError = _web_fetch_orchestrator._FetchContentConversionError
_FetchUrlSafetyError = _web_fetch_orchestrator._FetchUrlSafetyError


def _load_storage_state_cookies(storage_state_path: str) -> list[WebMapping]:
    """从 Playwright storage state 文件读取 cookie 列表。

    Args:
        storage_state_path: storage state 文件路径。

    Returns:
        storage state 中声明的 cookie 列表；文件不可用或结构非法时返回空列表。

    Raises:
        无。
    """

    normalized_path = str(storage_state_path or "").strip()
    if not normalized_path or not os.path.isfile(normalized_path):
        return []

    try:
        with open(normalized_path, "r", encoding="utf-8") as handle:
            payload = cast(JsonValue, json.load(handle))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []

    raw_cookies = payload.get("cookies") if isinstance(payload, Mapping) else None
    if not isinstance(raw_cookies, list):
        return []

    normalized_cookies: list[WebMapping] = []
    for item in raw_cookies:
        if isinstance(item, Mapping):
            normalized_cookies.append(item)
    return normalized_cookies


def _apply_storage_state_cookies_to_session(
    session: requests.Session,
    *,
    storage_state_path: str,
) -> int:
    """把 Playwright storage state 里的 cookie 注入 requests Session。

    诊断流程里人工浏览器验证后拿到的 storage state，往往包含能让
    `requests` 主路径直接恢复正文访问的 cookie。这里把该状态机械复制到
    当前 `Session`，避免只把 storage state 用在 Playwright fallback。

    Args:
        session: 当前调用使用的 requests Session。
        storage_state_path: storage state 文件路径。

    Returns:
        成功注入的 cookie 数量。

    Raises:
        无。
    """

    if not isinstance(session, requests.Session):
        return 0

    applied_count = 0
    for cookie in _load_storage_state_cookies(storage_state_path):
        name = str(cookie.get("name", "") or "").strip()
        value = str(cookie.get("value", "") or "")
        domain = str(cookie.get("domain", "") or "").strip() or None
        path = str(cookie.get("path", "") or "").strip() or "/"
        if not name:
            continue
        # HTTP header 值使用 latin-1 编码；含非 latin-1 字符的 cookie
        # （如本地化日期时间戳）会导致 requests 发送时 UnicodeEncodeError。
        # 这类 cookie 通常不含认证信息，直接跳过。
        try:
            name.encode("latin-1")
            value.encode("latin-1")
        except UnicodeEncodeError:
            continue
        session.cookies.set(
            name,
            value,
            domain=domain,
            path=path,
            secure=bool(cookie.get("secure", False)),
        )
        applied_count += 1
    return applied_count


def _iter_exception_chain(error: BaseException) -> list[BaseException]:
    """展开异常对象的因果链与嵌套 reason。

    Args:
        error: 起始异常。

    Returns:
        按遍历顺序展开后的异常对象列表。

    Raises:
        无。
    """

    pending: list[BaseException] = [error]
    visited: set[int] = set()
    collected: list[BaseException] = []
    while pending:
        current = pending.pop()
        marker = id(current)
        if marker in visited:
            continue
        visited.add(marker)
        collected.append(current)
        nested_candidates = [
            getattr(current, "__cause__", None),
            getattr(current, "__context__", None),
            getattr(current, "reason", None),
        ]
        first_arg = current.args[0] if getattr(current, "args", ()) else None
        if isinstance(first_arg, BaseException):
            nested_candidates.append(first_arg)
        for nested in nested_candidates:
            if isinstance(nested, BaseException):
                pending.append(nested)
    return collected


def _is_timeout_like_request_exception(error: BaseException) -> bool:
    """判断 requests 异常是否本质上由读超时引起。

    真实链路里，`requests` 可能直接抛 `requests.Timeout`，也可能把
    `urllib3.ReadTimeoutError` 包成 `requests.ConnectionError(MaxRetryError(...))`。

    Args:
        error: 待判断的异常对象。

    Returns:
        `True` 表示属于超时类异常，否则返回 `False`。

    Raises:
        无。
    """

    for current in _iter_exception_chain(error):
        if isinstance(current, (requests.Timeout, Urllib3ReadTimeoutError)):
            return True
    return False


def _is_timeout_like_exception(error: BaseException) -> bool:
    """判断任意异常是否本质上属于超时类异常。

    Args:
        error: 待判断的异常对象。

    Returns:
        `True` 表示异常链中存在超时语义，否则返回 `False`。

    Raises:
        无。
    """

    return _is_timeout_like_request_exception(error)


def _is_search_result_url_allowed(
    url: str,
    *,
    allow_private_network_url: bool = False,
) -> bool:
    """把 search result filtering 投影到统一 Web egress owner。

    Args:
        url: provider 返回的候选结果 URL。
        allow_private_network_url: 是否使用显式 local/dev profile。

    Returns:
        统一 policy 可授权该 URL 时返回 ``True``。

    Raises:
        无。
    """

    return WebEgressPolicy(allow_private_network=allow_private_network_url).is_url_allowed(url)


def _raise_fetch_cancelled() -> NoReturn:
    """将工具取消投影为 Web 模块内取消信号。

    Args:
        无。

    Returns:
        无。

    Raises:
        WebToolCancelledError: 当前调用已取消时抛出。
    """

    raise WebToolCancelledError(
        message=WEB_FETCH_CANCELLED_MESSAGE,
        hint=WEB_CANCELLED_HINT,
    )


def _is_ssl_like_request_exception(error: BaseException) -> bool:
    """判断 requests 异常是否本质上属于 SSL/TLS 握手失败。

    Args:
        error: 待判断的异常对象。

    Returns:
        `True` 表示异常链中存在 SSL/TLS 失败语义，否则返回 `False`。

    Raises:
        无。
    """

    for current in _iter_exception_chain(error):
        if isinstance(current, (requests.exceptions.SSLError, ssl.SSLError)):
            return True
        current_name = type(current).__name__.lower()
        current_message = str(current).lower()
        if "ssl" in current_name or "tls" in current_name:
            return True
        if any(
            marker in current_message
            for marker in (
                "ssl",
                "tls",
                "certificate",
                "unexpected eof while reading",
                "wrong version number",
                "handshake failure",
            )
        ):
            return True
    return False


_build_fetch_content_runtime_context = _web_fetch_orchestrator._build_fetch_content_runtime_context
_sanitize_response_headers = _web_fetch_orchestrator._sanitize_response_headers
_should_escalate_conversion_failure_to_browser = _web_fetch_orchestrator._should_escalate_conversion_failure_to_browser
_should_escalate_http_status_to_browser = _web_fetch_orchestrator._should_escalate_http_status_to_browser
_should_escalate_pipeline_failure_to_browser = _web_fetch_orchestrator._should_escalate_pipeline_failure_to_browser
_should_escalate_stage_result_to_browser = _web_fetch_orchestrator._should_escalate_stage_result_to_browser


def _sanitize_plain_response_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    """把普通响应头映射转为 sanitizer 接受的字典。

    Args:
        headers: 响应头映射。

    Returns:
        经过裁剪和规整的响应头字典。

    Raises:
        无。
    """

    return _sanitize_response_headers(dict(headers or {}))


def _response_text_for_challenge(response: requests.Response | None) -> str:
    """为 challenge owner 提供瞬时响应正文，不把正文写入诊断投影。

    Args:
        response: 可能携带已物化有界 body 的 HTTP 响应。

    Returns:
        可用于 challenge 判定的文本；解码失败时为空字符串。

    Raises:
        无。
    """

    if response is None:
        return ""
    try:
        return _web_fetch_orchestrator._decode_response_text(response)
    except Exception:
        return ""


def _build_playwright_success_payload(url: str, pw_result: WebMapping) -> WebPayload:
    """将 Playwright 回退成功结果规整为安全的 fetch_web_page 输出。

    Args:
        url: 原始请求 URL。
        pw_result: Playwright backend 返回的内部结果。

    Returns:
        ``final_url`` 已删除 userinfo/query/fragment 的工具成功 payload。

    Raises:
        无。
    """

    raw_final_url = str(pw_result.get("final_url", url) or url)

    return {
        "url": url,
        "final_url": project_safe_url_or_empty(raw_final_url),
        "title": pw_result.get("title", ""),
        "content": pw_result.get("content", ""),
        "fetch_backend": "playwright",
    }


def _raise_if_host_cancelled(cancellation_token: CancellationToken | None) -> None:
    """在进入新的联网阶段前执行协作式取消检查。

    Args:
        cancellation_token: 当前工具调用取消令牌；为空时不触发取消。

    Returns:
        无。

    Raises:
        WebToolCancelledError: 取消令牌已请求取消时抛出。
    """

    if cancellation_token is not None:
        if cancellation_token.is_cancelled():
            _raise_fetch_cancelled()


def _try_playwright_fallback(
    *,
    url: str,
    timeout_seconds: float,
    headers: dict[str, str],
    timeout_budget: float | None,
    deadline_monotonic: float | None,
    playwright_channel: str | None = None,
    playwright_storage_state_path: str = "",
    egress_policy: WebEgressPolicy,
    resource_budget: WebResourceBudget,
    cancellation_token: CancellationToken | None = None,
) -> WebPayload | None:
    """尝试使用 Playwright 浏览器回退抓取页面。

    Args:
        url: 原始网页链接。
        timeout_seconds: 浏览器抓取基础超时秒数。
        headers: 请求头。
        timeout_budget: Runner 注入的工具总预算。
        deadline_monotonic: 当前工具调用 deadline。
        playwright_channel: 浏览器回退使用的 Chromium channel。
        playwright_storage_state_path: 浏览器回退可选 storage state 文件路径。
        egress_policy: 当前 Web 调用唯一的出站策略。
        resource_budget: HTTP、browser 与诊断共享的完整资源预算。
        cancellation_token: 当前工具调用取消令牌。

    Returns:
        成功时返回标准化后的抓取结果；失败时返回 `None`。

    Raises:
        WebToolCancelledError: Playwright 执行期间 Host 取消时抛出。
        _FetchUrlSafetyError: Playwright URL 被安全策略拒绝时抛出。
    """

    _raise_if_host_cancelled(cancellation_token)
    try:
        pw_result = _fetch_and_convert_with_playwright(
            url=url,
            timeout_seconds=timeout_seconds,
            headers=headers,
            timeout_budget=timeout_budget,
            deadline_monotonic=deadline_monotonic,
            playwright_channel=playwright_channel,
            playwright_storage_state_path=playwright_storage_state_path,
            egress_policy=egress_policy,
            resource_budget=resource_budget,
            cancellation_token=cancellation_token,
        )
    except _web_playwright_backend.CancelledError:
        _raise_fetch_cancelled()
    if not pw_result.get("ok"):
        if pw_result.get("reason") == "browser_egress_policy_unavailable":
            _raise_fetch_failure(
                url=url,
                error_code="browser_egress_policy_unavailable",
                message="This page requires a browser path that is unavailable under the current network policy.",
                hint=build_hint(REASON_BLOCKED_BY_SITE_POLICY),
                next_action=NEXT_ACTION_CHANGE_SOURCE,
            )
        browser_budget_reason = pw_result.get("reason")
        if isinstance(browser_budget_reason, str) and browser_budget_reason in (
            "browser_dom_too_large",
            "browser_text_too_large",
        ):
            _raise_fetch_failure(
                url=url,
                error_code=browser_budget_reason,
                message="Browser-rendered page exceeded the configured resource budget.",
                hint=build_hint(REASON_CONTENT_CONVERSION_FAILED),
                next_action=NEXT_ACTION_CHANGE_SOURCE,
            )
        Log.debug(
            "Playwright 浏览器回退未成功: "
            f"availability={pw_result.get('availability')} "
            f"reason={pw_result.get('reason')}",
            module=MODULE,
        )
        return None
    return _build_playwright_success_payload(url, pw_result)


def _status_class(status_code: Optional[int]) -> str:
    """将状态码归类为状态段。

    Args:
        status_code: HTTP 状态码。

    Returns:
        形如 ``2xx``/``4xx`` 的分类，未知时返回 ``unknown``。

    Raises:
        无。
    """

    if status_code is None:
        return "unknown"
    hundred = status_code // 100
    if 1 <= hundred <= 5:
        return f"{hundred}xx"
    return "unknown"


def _build_domain_home_url(url: str) -> str:
    """构建同域首页 URL。

    Args:
        url: 目标链接。

    Returns:
        同域首页 URL。

    Raises:
        ValueError: 当 URL 无法解析时抛出。
    """

    parsed = urlparse(_normalize_url_for_http(url))
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"无效 URL: {url}")
    return f"{parsed.scheme}://{parsed.netloc}/"


def _normalize_url_for_http(url: str) -> str:
    """将 URL 规整为适合 HTTP 请求与 Header 传输的 ASCII 形式。

    设计意图：
    - `requests` 可以处理部分 Unicode URL，但 HTTP header 值最终会走
      `latin-1` 编码；若直接把含中文路径的 URL 放进 `Referer`，会在
      `http.client.putheader()` 阶段抛出 `UnicodeEncodeError`。
    - 因此这里统一做两件事：域名转为 IDNA，路径/查询/片段转为百分号编码。

    Args:
        url: 原始 URL。

    Returns:
        适合 HTTP 传输的 ASCII URL。

    Raises:
        ValueError: 当 URL 缺少 scheme 或 netloc 时抛出。
    """

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"无效 URL: {url}")
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(f"不允许的 URL scheme: {parsed.scheme} (url={url})")

    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError(f"无效 URL: {url}")

    username = parsed.username
    password = parsed.password
    auth_parts: list[str] = []
    if username is not None:
        auth_parts.append(quote(username, safe=""))
    if password is not None:
        auth_parts.append(quote(password, safe=""))

    host_ascii = hostname.encode("idna").decode("ascii")
    host_for_netloc = f"[{host_ascii}]" if ":" in host_ascii else host_ascii
    auth_prefix = ""
    if auth_parts:
        auth_prefix = ":".join(auth_parts) + "@"
    netloc = f"{auth_prefix}{host_for_netloc}"
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"

    normalized = parsed._replace(netloc=netloc).geturl()
    return requote_uri(normalized)


def _build_referer(url: str) -> str:
    """构建请求 Referer。

    Args:
        url: 目标链接。

    Returns:
        Referer 链接。

    Raises:
        ValueError: 当 URL 无法解析时抛出。
    """

    parsed = urlparse(_normalize_url_for_http(url))
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"无效 URL: {url}")
    path = parsed.path or "/"
    if path == "/":
        return f"{parsed.scheme}://{parsed.netloc}/"
    parent = path.rsplit("/", 1)[0]
    if not parent:
        parent = "/"
    if not parent.endswith("/"):
        parent = f"{parent}/"
    return f"{parsed.scheme}://{parsed.netloc}{parent}"


def _warmup_domain(
    session: requests.Session,
    *,
    url: str,
    timeout_seconds: float,
    headers: dict[str, str],
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
    egress_policy: WebEgressPolicy,
    resource_budget: WebResourceBudget,
    cancellation_token: CancellationToken | None = None,
) -> StagePayload:
    """对目标域做一次预热请求以建立 Cookie。"""

    return _web_fetch_orchestrator._warmup_domain(
        session,
        url=url,
        timeout_seconds=timeout_seconds,
        headers=headers,
        resolve_timeout_budget=_resolve_timeout_budget,
        build_domain_home_url=_build_domain_home_url,
        normalize_url_for_http=_normalize_url_for_http,
        is_timeout_like_exception=_is_timeout_like_exception,
        egress_policy=egress_policy,
        resource_budget=resource_budget,
        timeout_budget=timeout_budget,
        deadline_monotonic=deadline_monotonic,
        cancellation_token=cancellation_token,
    )


def _probe_content_type(
    session: requests.Session,
    *,
    url: str,
    timeout_seconds: float,
    headers: dict[str, str],
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
    egress_policy: WebEgressPolicy,
    resource_budget: WebResourceBudget,
    cancellation_token: CancellationToken | None = None,
) -> ContentProbePayload:
    """探测目标资源类型（HEAD 优先，失败降级到 GET）。"""

    return _web_fetch_orchestrator._probe_content_type(
        session,
        url=url,
        timeout_seconds=timeout_seconds,
        headers=headers,
        resolve_timeout_budget=_resolve_timeout_budget,
        normalize_url_for_http=_normalize_url_for_http,
        is_timeout_like_exception=_is_timeout_like_exception,
        egress_policy=egress_policy,
        resource_budget=resource_budget,
        timeout_budget=timeout_budget,
        deadline_monotonic=deadline_monotonic,
        cancellation_token=cancellation_token,
    )


def _raise_fetch_failure(
    *,
    url: str,
    error_code: str,
    message: str,
    hint: str,
    next_action: str,
    http_status: int | None = None,
) -> None:
    """记录诊断日志并抛出 ToolBusinessError。

    将失败信息写入诊断日志后，以 ToolBusinessError 的形式抛出，
    由当前 adapter 投影为 ``ToolFailedOutcome``。

    Args:
        url: 原始请求 URL。
        error_code: 错误码（对齐 ErrorCode 枚举值）。
        message: 错误说明。
        hint: LLM 可执行提示（来自 web_recovery.build_hint）。
        next_action: 下一步动作（retry/change_source/continue_without_web）。
        http_status: HTTP 状态码（可选）。

    Returns:
        无（始终抛出异常）。

    Raises:
        ToolBusinessError: 始终抛出。
    """
    normalized_action = normalize_next_action(next_action)
    projection = failed_projection(
        stage="fetch_web_page",
        url=url,
        elapsed_seconds=0.0,
        error_code=error_code,
        error_message=message,
        max_error_chars=_DEFAULT_WEB_DIAGNOSTIC_ERROR_CHARS,
        http_status=http_status,
    )
    _log_fetch_diagnostics(projection)
    # hint 中嵌入 next_action 标签，供 LLM 解析
    hint_text = f"[{normalized_action}] {hint}"
    raise ToolBusinessError(
        code=error_code,
        message=projection.error_message,
        hint=hint_text,
        url=projection.safe_url,
        next_action=normalized_action,
        http_status=http_status,
        internal_diagnostics=projection.to_json(),
    )


def _parse_retry_after_seconds(response_headers: Optional[dict[str, str]]) -> Optional[int]:
    """解析 Retry-After 头。

    Args:
        response_headers: 响应头。

    Returns:
        可解析时返回秒数，否则返回 ``None``。

    Raises:
        无。
    """

    if not response_headers:
        return None
    raw = response_headers.get("retry-after") or response_headers.get("Retry-After")
    if raw is None:
        return None
    try:
        value = int(str(raw).strip())
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


def _log_fetch_diagnostics(projection: WebDiagnosticProjection) -> None:
    """输出网页抓取诊断日志。

    Args:
        projection: 已由 Web diagnostic owner 生成的安全投影。

    Returns:
        无。

    Raises:
        无。
    """

    Log.debug(
        f"fetch_web_page diagnostics={projection.to_json()}",
        module=MODULE,
    )


def build_web_tool_definitions(config: WebToolsConfig) -> tuple[ToolDefinition, ...]:
    """构造 Web 原生工具定义。

    :param config: Web provider 配置。
    :returns: ``search_web`` 与 ``fetch_web_page`` 的 current 工具定义。
    :raises Exception: 工具 schema 或 truncate 声明构造失败时透出。
    """

    provider_lock = asyncio.Lock()
    process_target_factory = _WebProcessTargetFactory(config=config)

    @tool(
        name=_SEARCH_WEB_TOOL_NAME,
        description="搜索公开网页来源。",
        parameters=_build_search_web_parameters(config.max_search_results),
        tags=_WEB_TOOL_TAGS,
        display_name="联网搜索",
        execution=ProcessBackedToolExecutionCapability(
            target_factory=process_target_factory
        ),
        truncate=ToolTruncateSpec(
            enabled=True,
            strategy=ToolTruncationStrategy.LIST_ITEMS,
            limits={"max_items": _SEARCH_TRUNCATE_ITEMS},
            target_field="results",
            field_path=None,
            ttl_seconds=None,
        ),
    )
    async def search_web(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行单次联网搜索工具调用。

        :param call: 当前工具调用请求。
        :param context: 批式工具执行上下文。
        :returns: 工具执行 outcome。
        :raises Exception: 不主动抛出异常；预期业务异常在本边界内转为 outcome。
        """

        return await _call_search_web(
            call=call,
            context=context,
            config=config,
            provider_lock=provider_lock,
        )

    @tool(
        name=_FETCH_WEB_PAGE_TOOL_NAME,
        description=(
            "抓取网页正文并转成 Markdown。失败时先看 hint 和 next_action，再决定重试、换来源或忽略当前网页。"
        ),
        parameters=_FETCH_WEB_PAGE_PARAMETERS,
        tags=_WEB_TOOL_TAGS,
        display_name="抓取网页",
        execution=ProcessBackedToolExecutionCapability(
            target_factory=process_target_factory
        ),
        truncate=ToolTruncateSpec(
            enabled=True,
            strategy=ToolTruncationStrategy.TEXT_CHARS,
            limits={"max_chars": config.fetch_truncate_chars},
            target_field="content",
            field_path=None,
            ttl_seconds=None,
        ),
    )
    async def fetch_web_page(
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行单次网页抓取工具调用。

        :param call: 当前工具调用请求。
        :param context: 批式工具执行上下文。
        :returns: 工具执行 outcome。
        :raises Exception: 不主动抛出异常；预期业务异常在本边界内转为 outcome。
        """

        return await _call_fetch_web_page(
            call=call,
            context=context,
            config=config,
            provider_lock=provider_lock,
        )

    Log.verbose(f"已注册 2 个联网工具 provider={config.provider}", module=MODULE)
    return (search_web, fetch_web_page)


def _build_search_web_parameters(max_search_results: int) -> ToolParametersSchema:
    """构造 ``search_web`` 参数 schema。

    :param max_search_results: 当前 provider 允许的搜索结果上限。
    :returns: current 工具参数 schema。
    :raises Exception: schema 构造失败时透出。
    """

    return ToolParametersSchema(
        type="object",
        properties={
            "query": {
                "type": "string",
                "description": "检索关键词。直接写你最自然的查询。",
            },
            "domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选域名限制。只在你明确要收窄来源时填写。",
            },
            "recency_days": {
                "type": "integer",
                "minimum": 0,
                "description": "可选最近天数限制。只在你明确要限制时效时填写。",
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": max_search_results,
                "description": f"返回结果上限。只在你明确需要更少结果时调整；最大值 {max_search_results}。",
            },
        },
        required=("query",),
        additional_properties=False,
    )


async def _call_search_web(
    *,
    call: ToolCallRequest,
    context: BatchToolExecutionContext,
    config: WebToolsConfig,
    provider_lock: asyncio.Lock,
) -> ToolExecutionOutcome:
    """执行 search_web callable 外壳。

    :param call: 当前工具调用请求。
    :param context: 执行上下文。
    :param config: Web provider 配置。
    :param provider_lock: 当前 provider 共享串行锁。
    :returns: 工具执行 outcome。
    :raises Exception: 不主动抛出异常。
    """

    started_at = datetime.now(UTC)
    validation = validate_and_project_arguments(
        call=call,
        tool_name=_SEARCH_WEB_TOOL_NAME,
        schema=_build_search_web_parameters(config.max_search_results),
    )
    if isinstance(validation, ToolArgumentValidationFailure):
        return _validation_failed_outcome(
            tool_name=_SEARCH_WEB_TOOL_NAME,
            validation=validation,
            started_at=started_at,
        )

    cancellation_token = context.cancellation_token
    if cancellation_token.is_cancelled():
        return _host_cancelled_from_token(
            tool_name=_SEARCH_WEB_TOOL_NAME,
            started_at=started_at,
            message=WEB_SEARCH_CANCELLED_MESSAGE,
            hint=WEB_CANCELLED_HINT,
        )

    arguments = validation.arguments
    query = _required_string_argument(arguments, "query")
    domains = _optional_string_list_argument(arguments, "domains")
    recency_days = _optional_int_argument(arguments, "recency_days")
    max_results = (
        _optional_int_argument(arguments, "max_results")
        or _SEARCH_WEB_DEFAULT_MAX_RESULTS
    )

    try:
        async with provider_lock:
            if cancellation_token.is_cancelled():
                return _host_cancelled_from_token(
                    tool_name=_SEARCH_WEB_TOOL_NAME,
                    started_at=started_at,
                    message=WEB_SEARCH_CANCELLED_MESSAGE,
                    hint=WEB_CANCELLED_HINT,
                )
            value = await asyncio.to_thread(
                _search_web_business,
                query=query,
                domains=domains,
                recency_days=recency_days,
                max_results=max_results,
                config=config,
                timeout_budget=context.timeout_seconds,
                cancellation_token=cancellation_token,
            )
    except WebSearchCancelledError as exc:
        return host_cancelled_outcome(
            tool_name=_SEARCH_WEB_TOOL_NAME,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            message=WEB_SEARCH_CANCELLED_MESSAGE,
            hint=WEB_CANCELLED_HINT,
        )
    except WebSearchProviderResponseError as exc:
        return failed_outcome(
            tool_name=_SEARCH_WEB_TOOL_NAME,
            error=_SEARCH_PROVIDER_RESPONSE_INVALID_ERROR,
            message=exc.message,
            hint=WEB_SEARCH_PROVIDER_RESPONSE_INVALID_HINT,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
    except WebSearchProviderResourceError as exc:
        return failed_outcome(
            tool_name=_SEARCH_WEB_TOOL_NAME,
            error=_RESPONSE_BODY_TOO_LARGE_ERROR,
            message=exc.message,
            hint=WEB_SEARCH_RESPONSE_BODY_TOO_LARGE_HINT,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
    except WebSearchProviderUnavailableError as exc:
        return failed_outcome(
            tool_name=_SEARCH_WEB_TOOL_NAME,
            error=_SEARCH_PROVIDER_UNAVAILABLE_ERROR,
            message=exc.message,
            hint=WEB_SEARCH_PROVIDER_UNAVAILABLE_HINT,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
    except Exception as exc:
        return _unexpected_failed_outcome(
            tool_name=_SEARCH_WEB_TOOL_NAME,
            error=exc,
            started_at=started_at,
        )

    return completed_outcome(
        tool_name=_SEARCH_WEB_TOOL_NAME,
        value=cast(JsonValue, value),
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )


async def _call_fetch_web_page(
    *,
    call: ToolCallRequest,
    context: BatchToolExecutionContext,
    config: WebToolsConfig,
    provider_lock: asyncio.Lock,
) -> ToolExecutionOutcome:
    """执行 fetch_web_page callable 外壳。

    :param call: 当前工具调用请求。
    :param context: 执行上下文。
    :param config: Web provider 配置。
    :param provider_lock: 当前 provider 共享串行锁。
    :returns: 工具执行 outcome。
    :raises Exception: 不主动抛出异常。
    """

    started_at = datetime.now(UTC)
    validation = validate_and_project_arguments(
        call=call,
        tool_name=_FETCH_WEB_PAGE_TOOL_NAME,
        schema=_FETCH_WEB_PAGE_PARAMETERS,
    )
    if isinstance(validation, ToolArgumentValidationFailure):
        return _validation_failed_outcome(
            tool_name=_FETCH_WEB_PAGE_TOOL_NAME,
            validation=validation,
            started_at=started_at,
        )

    cancellation_token = context.cancellation_token
    if cancellation_token.is_cancelled():
        return _host_cancelled_from_token(
            tool_name=_FETCH_WEB_PAGE_TOOL_NAME,
            started_at=started_at,
            message=WEB_FETCH_CANCELLED_MESSAGE,
            hint=WEB_CANCELLED_HINT,
        )

    url = _required_string_argument(validation.arguments, "url")
    try:
        async with provider_lock:
            if cancellation_token.is_cancelled():
                return _host_cancelled_from_token(
                    tool_name=_FETCH_WEB_PAGE_TOOL_NAME,
                    started_at=started_at,
                    message=WEB_FETCH_CANCELLED_MESSAGE,
                    hint=WEB_CANCELLED_HINT,
                )
            value = await asyncio.to_thread(
                _fetch_web_page_business,
                url=url,
                config=config,
                timeout_budget=context.timeout_seconds,
                cancellation_token=cancellation_token,
            )
    except WebToolCancelledError as exc:
        return host_cancelled_outcome(
            tool_name=_FETCH_WEB_PAGE_TOOL_NAME,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            message=exc.message,
            hint=WEB_CANCELLED_HINT,
        )
    except ToolBusinessError as exc:
        return failed_outcome(
            tool_name=_FETCH_WEB_PAGE_TOOL_NAME,
            error=exc.code,
            message=exc.message,
            hint=exc.hint,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
    except Exception as exc:
        return _unexpected_failed_outcome(
            tool_name=_FETCH_WEB_PAGE_TOOL_NAME,
            error=exc,
            started_at=started_at,
        )

    return completed_outcome(
        tool_name=_FETCH_WEB_PAGE_TOOL_NAME,
        value=value,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )


def _search_web_business(
    *,
    query: str,
    domains: list[str] | None,
    recency_days: int | None,
    max_results: int,
    config: WebToolsConfig,
    timeout_budget: float | None,
    cancellation_token: CancellationToken,
) -> SearchWebOutput:
    """执行同步联网搜索业务逻辑。

    :param query: 检索关键词。
    :param domains: 可选域名过滤。
    :param recency_days: 可选最近天数过滤。
    :param max_results: 返回结果上限。
    :param config: Web provider 配置。
    :param timeout_budget: 单次工具调用预算，用于约束下游 HTTP 请求预算。
    :param cancellation_token: Host 取消令牌。
    :returns: 搜索结果字典。
    :raises WebSearchCancelledError: Host 取消时抛出。
    :raises WebSearchProviderUnavailableError: 搜索 provider 全部不可用时抛出。
    :raises Exception: 搜索 provider 失败时透出。
    """

    _raise_if_host_cancelled(cancellation_token)
    provider_result: SearchWebProviderResult = search_public_web(
        query=query,
        domains=domains,
        recency_days=recency_days,
        max_results=max_results,
        max_search_results=config.max_search_results,
        provider=config.provider,
        request_timeout_seconds=config.request_timeout_seconds,
        timeout_budget=timeout_budget,
        deadline_monotonic=_compute_deadline_monotonic(timeout_budget),
        allow_private_network_url=config.allow_private_network_url,
        is_safe_public_url=_is_search_result_url_allowed,
        normalize_whitespace=_normalize_whitespace,
        resolve_timeout_budget=_resolve_timeout_budget,
        resource_budget=config.resource_budget,
        cancellation_token=cancellation_token,
    )
    return build_search_web_output(provider_result)


def _execute_web_process_business_value(
    *,
    tool_name: str,
    call: ToolCallRequest,
    config: WebToolsConfig,
    timeout_budget: float | None,
) -> JsonValue:
    """执行 Web process target 内的同步业务并返回成功载荷。

    Args:
        tool_name: 工具名。
        call: 子进程内重建的工具调用请求。
        config: Web provider 配置。
        timeout_budget: 父进程投影的工具执行预算，会继续传入 HTTP /
            browser 阶段。

    Returns:
        工具成功载荷。

    Raises:
        ToolBusinessError: 参数校验、URL 安全或抓取业务失败时抛出。
        WebSearchProviderUnavailableError: 搜索 provider 不可用时抛出。
        WebToolCancelledError: 子进程内部意外观察到取消时抛出。
        WebSearchCancelledError: 搜索 provider 意外返回取消时抛出。
        ValueError: 工具名未知时抛出。
        Exception: 未预期业务异常透出给 process target 统一 fail closed。
    """

    process_token = _WebProcessCancellationToken()
    if tool_name == _SEARCH_WEB_TOOL_NAME:
        validation = validate_and_project_arguments(
            call=call,
            tool_name=_SEARCH_WEB_TOOL_NAME,
            schema=_build_search_web_parameters(config.max_search_results),
        )
        if isinstance(validation, ToolArgumentValidationFailure):
            raise ToolBusinessError(
                validation.error,
                validation.message,
                hint=validation.hint or "",
            )
        arguments = validation.arguments
        return cast(
            JsonValue,
            _search_web_business(
                query=_required_string_argument(arguments, "query"),
                domains=_optional_string_list_argument(arguments, "domains"),
                recency_days=_optional_int_argument(arguments, "recency_days"),
                max_results=(
                    _optional_int_argument(arguments, "max_results")
                    or _SEARCH_WEB_DEFAULT_MAX_RESULTS
                ),
                config=config,
                timeout_budget=timeout_budget,
                cancellation_token=process_token,
            ),
        )
    if tool_name == _FETCH_WEB_PAGE_TOOL_NAME:
        validation = validate_and_project_arguments(
            call=call,
            tool_name=_FETCH_WEB_PAGE_TOOL_NAME,
            schema=_FETCH_WEB_PAGE_PARAMETERS,
        )
        if isinstance(validation, ToolArgumentValidationFailure):
            raise ToolBusinessError(
                validation.error,
                validation.message,
                hint=validation.hint or "",
            )
        return _fetch_web_page_business(
            url=_required_string_argument(validation.arguments, "url"),
            config=config,
            timeout_budget=timeout_budget,
            cancellation_token=process_token,
        )
    raise ValueError(f"unknown web tool for process-backed execution: {tool_name}")


def _web_process_failed_envelope(
    *,
    error_type: str,
    message: str,
    hint: str | None,
) -> JsonValue:
    """构造 Web process-backed failed JSON 信封。

    Args:
        error_type: 工具失败错误码。
        message: 面向 LLM 的失败说明。
        hint: 可选恢复提示。

    Returns:
        process-backed failed JSON 信封。

    Raises:
        无。
    """

    return process_tool_failed_envelope(
        error_type=error_type.strip() or "execution_error",
        message=message.strip() or "Tool execution failed.",
        hint=hint,
    )


def _validation_failed_outcome(
    *,
    tool_name: str,
    validation: ToolArgumentValidationFailure,
    started_at: datetime,
) -> ToolExecutionOutcome:
    """把参数校验失败转为 failed outcome。

    :param tool_name: 工具名。
    :param validation: 参数校验失败结果。
    :param started_at: 工具开始时间。
    :returns: failed outcome。
    :raises Exception: outcome 构造失败时透出。
    """

    return failed_outcome(
        tool_name=tool_name,
        error=validation.error,
        message=validation.message,
        hint=validation.hint,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )


def _unexpected_failed_outcome(
    *,
    tool_name: str,
    error: Exception,
    started_at: datetime,
) -> ToolExecutionOutcome:
    """把未预期异常转为 execution_error outcome。

    :param tool_name: 工具名。
    :param error: 捕获到的异常。
    :param started_at: 工具开始时间。
    :returns: failed outcome。
    :raises Exception: outcome 构造失败时透出。
    """

    message = str(error).strip() or "Tool execution failed."
    return failed_outcome(
        tool_name=tool_name,
        error="execution_error",
        message=message,
        hint=None,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )


def _host_cancelled_from_token(
    *,
    tool_name: str,
    started_at: datetime,
    message: str,
    hint: str,
) -> ToolExecutionOutcome:
    """根据 Host token 构造取消 outcome。

    :param tool_name: 工具名。
    :param started_at: 工具开始时间。
    :param message: 固定的安全取消说明。
    :param hint: Web 语义恢复提示。
    :returns: cancelled outcome。
    :raises Exception: outcome 构造失败时透出。
    """

    return host_cancelled_outcome(
        tool_name=tool_name,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        message=message,
        hint=hint,
    )


def _required_string_argument(arguments: Mapping[str, JsonValue], field_name: str) -> str:
    """读取已校验的必填字符串参数。

    :param arguments: 已投影参数。
    :param field_name: 字段名。
    :returns: 字符串参数值。
    :raises TypeError: 参数不是字符串时抛出。
    """

    value = arguments.get(field_name)
    if not isinstance(value, str):
        raise TypeError(f"validated argument {field_name} must be string")
    return value


def _required_int_argument(arguments: Mapping[str, JsonValue], field_name: str) -> int:
    """读取已校验的必填整数参数。

    :param arguments: 已投影参数。
    :param field_name: 字段名。
    :returns: 整数参数值。
    :raises TypeError: 参数不是整数时抛出。
    """

    value = arguments.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"validated argument {field_name} must be integer")
    return value


def _optional_int_argument(arguments: Mapping[str, JsonValue], field_name: str) -> int | None:
    """读取已校验的可选整数参数。

    :param arguments: 已投影参数。
    :param field_name: 字段名。
    :returns: 整数参数值或 ``None``。
    :raises TypeError: 参数不是整数时抛出。
    """

    if field_name not in arguments:
        return None
    return _required_int_argument(arguments, field_name)


def _optional_string_list_argument(
    arguments: Mapping[str, JsonValue],
    field_name: str,
) -> list[str] | None:
    """读取已校验的可选字符串数组参数。

    :param arguments: 已投影参数。
    :param field_name: 字段名。
    :returns: 字符串列表或 ``None``。
    :raises TypeError: 参数不是字符串数组时抛出。
    """

    value = arguments.get(field_name)
    if value is None:
        return None
    if not isinstance(value, list):
        raise TypeError(f"validated argument {field_name} must be array")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"validated argument {field_name} items must be string")
        items.append(item)
    return items


def _fetch_web_page_business(
    *,
    url: str,
    config: WebToolsConfig,
    timeout_budget: float | None,
    cancellation_token: CancellationToken,
) -> WebPayload:
    """执行同步网页抓取业务逻辑。

    :param url: 目标网页 URL。
    :param config: Web provider 配置。
    :param timeout_budget: 单次工具调用预算，用于约束下游 HTTP 请求预算。
    :param cancellation_token: Host 取消令牌。
    :returns: 抓取成功载荷。
    :raises WebToolCancelledError: Host 取消时抛出。
    :raises ToolBusinessError: 抓取业务失败时抛出。
    :raises Exception: 未预期异常时透出。
    """

    request_timeout_seconds = config.request_timeout_seconds
    allow_private_network_url = config.allow_private_network_url
    playwright_channel = config.playwright_channel
    playwright_storage_state_dir = config.playwright_storage_state_dir
    resource_budget = config.resource_budget
    _raise_if_host_cancelled(cancellation_token)

    egress_policy = WebEgressPolicy(allow_private_network=allow_private_network_url)
    try:
        normalized_url = _normalize_url_for_http(url)
    except ValueError:
        _raise_fetch_failure(
            url=url,
            error_code="permission_denied",
            message=f"URL is blocked by fetch safety policy: {url}",
            hint=build_hint(REASON_BLOCKED_BY_SITE_POLICY),
            next_action=NEXT_ACTION_CHANGE_SOURCE,
        )
        raise AssertionError("unreachable fetch failure path")
    deadline_monotonic = _compute_deadline_monotonic(timeout_budget)
    playwright_storage_state_path = _resolve_playwright_storage_state_path(
        url=normalized_url,
        playwright_storage_state_dir=playwright_storage_state_dir,
    )
    base_session = _get_web_session()
    session, should_close_session = _prepare_call_session(
        base_session,
        timeout_budget=timeout_budget,
    )
    _apply_storage_state_cookies_to_session(
        session,
        storage_state_path=playwright_storage_state_path,
    )
    headers = _build_fetch_headers(normalized_url)
    headers["Referer"] = _build_referer(normalized_url)
    warmup: StagePayload = {"attempted": False}
    content_type_probe: ContentProbePayload = {"attempted": False, "ok": False}
    fetch_result: _FetchContentResult | None = None
    playwright_fallback_kwargs: _PlaywrightFallbackKwargs = {
        "timeout_seconds": request_timeout_seconds,
        "headers": headers,
        "timeout_budget": timeout_budget,
        "deadline_monotonic": deadline_monotonic,
        "playwright_channel": playwright_channel,
        "playwright_storage_state_path": playwright_storage_state_path,
        "egress_policy": egress_policy,
        "resource_budget": resource_budget,
    }
    if cancellation_token is not None:
        playwright_fallback_kwargs["cancellation_token"] = cancellation_token
    try:
        _raise_if_host_cancelled(cancellation_token)
        warmup_kwargs: _StageFetchKwargs = {
            "url": normalized_url,
            "timeout_seconds": request_timeout_seconds,
            "headers": headers,
            "timeout_budget": timeout_budget,
            "deadline_monotonic": deadline_monotonic,
            "egress_policy": egress_policy,
            "resource_budget": resource_budget,
        }
        if cancellation_token is not None:
            warmup_kwargs["cancellation_token"] = cancellation_token
        warmup = _warmup_domain(
            session,
            **warmup_kwargs,
        )
        if _should_escalate_stage_result_to_browser(warmup):
            browser_result = _try_playwright_fallback(url=url, **playwright_fallback_kwargs)
            if browser_result is not None:
                return browser_result
        _raise_if_host_cancelled(cancellation_token)
        probe_kwargs: _StageFetchKwargs = {
            "url": normalized_url,
            "timeout_seconds": request_timeout_seconds,
            "headers": headers,
            "timeout_budget": timeout_budget,
            "deadline_monotonic": deadline_monotonic,
            "egress_policy": egress_policy,
            "resource_budget": resource_budget,
        }
        if cancellation_token is not None:
            probe_kwargs["cancellation_token"] = cancellation_token
        content_type_probe = _probe_content_type(
            session,
            **probe_kwargs,
        )
        if _should_escalate_stage_result_to_browser(cast(StagePayload, content_type_probe)):
            browser_result = _try_playwright_fallback(url=url, **playwright_fallback_kwargs)
            if browser_result is not None:
                return browser_result
        _raise_if_host_cancelled(cancellation_token)
        fetch_kwargs: _FetchConvertKwargs = {
            "timeout_seconds": request_timeout_seconds,
            "session": session,
            "headers": headers,
            "content_type_probe": content_type_probe,
            "timeout_budget": timeout_budget,
            "deadline_monotonic": deadline_monotonic,
            "egress_policy": egress_policy,
            "resource_budget": resource_budget,
        }
        if cancellation_token is not None:
            fetch_kwargs["cancellation_token"] = cancellation_token
        fetch_result = _fetch_and_convert_content(
            normalized_url,
            **fetch_kwargs,
        )
    except requests.TooManyRedirects as exc:
        response = getattr(exc, "response", None)
        _raise_fetch_failure(
            url=url,
            error_code="too_many_redirects",
            message="Redirect chain too long; cannot reliably fetch this page",
            http_status=response.status_code if response is not None else None,
            hint=build_hint(REASON_REDIRECT_CHAIN_TOO_LONG),
            next_action=NEXT_ACTION_CHANGE_SOURCE,
        )
    except requests.Timeout as exc:
        browser_result = _try_playwright_fallback(url=url, **playwright_fallback_kwargs)
        if browser_result is not None:
            return browser_result
        _raise_fetch_failure(
            url=url,
            error_code="request_timeout",
            message=f"Request timed out: {exc}",
            hint=build_hint(REASON_REQUEST_TIMEOUT),
            next_action=NEXT_ACTION_RETRY,
        )
    except requests.RequestException as exc:
        response = getattr(exc, "response", None)
        http_status = response.status_code if response is not None else None
        challenge_hint = ""
        error_code = "http_error"
        next_action = (
            NEXT_ACTION_RETRY
            if http_status in {429, 500, 502, 503, 504} or http_status is None
            else NEXT_ACTION_CHANGE_SOURCE
        )
        if _is_timeout_like_request_exception(exc):
            browser_result = _try_playwright_fallback(url=url, **playwright_fallback_kwargs)
            if browser_result is not None:
                return browser_result
            _raise_fetch_failure(
                url=url,
                error_code="request_timeout",
                message=str(exc),
                hint=build_hint(REASON_REQUEST_TIMEOUT),
                next_action=NEXT_ACTION_RETRY,
            )
        if _is_ssl_like_request_exception(exc):
            browser_result = _try_playwright_fallback(url=url, **playwright_fallback_kwargs)
            if browser_result is not None:
                return browser_result
            _raise_fetch_failure(
                url=url,
                error_code="ssl_error",
                message=f"SSL/TLS 握手失败: {exc}",
                hint=build_hint(REASON_HTTP_ERROR),
                next_action=NEXT_ACTION_CHANGE_SOURCE,
            )
        challenge = _detect_bot_challenge(
            response=response,
            content_text=_response_text_for_challenge(response),
        )
        challenge_action = challenge_fallback_action(
            decision=challenge.decision,
            browser_available=True,
        )
        if challenge_action is ChallengeFallbackAction.TRY_BROWSER:
            browser_result = _try_playwright_fallback(url=url, **playwright_fallback_kwargs)
            if browser_result is not None:
                return browser_result
            terminal_challenge_action = challenge_fallback_action(
                decision=challenge.decision,
                browser_available=False,
            )
            if terminal_challenge_action is not ChallengeFallbackAction.FAIL_BLOCKED:
                raise RuntimeError("confirmed challenge did not produce terminal fallback action")
            _raise_fetch_failure(
                url=url,
                error_code="blocked",
                message="Page appears to be a bot challenge page or access gate; fetched content is unusable.",
                http_status=http_status,
                hint=build_hint(REASON_BLOCKED_BY_SITE_POLICY),
                next_action=NEXT_ACTION_CHANGE_SOURCE,
            )
        if _should_escalate_http_status_to_browser(http_status):
            browser_result = _try_playwright_fallback(url=url, **playwright_fallback_kwargs)
            if browser_result is not None:
                return browser_result
        if http_status == 403:
            browser_result = _try_playwright_fallback(url=url, **playwright_fallback_kwargs)
            if browser_result is not None:
                return browser_result
            challenge_hint = "Target site may have anti-bot or access policies; try a different source."
            next_action = NEXT_ACTION_CHANGE_SOURCE
            error_code = "blocked"
        _raise_fetch_failure(
            url=url,
            error_code=error_code,
            message=str(exc),
            http_status=http_status,
            hint=challenge_hint or build_hint(REASON_HTTP_ERROR),
            next_action=next_action,
        )
    except _FetchUrlSafetyError as exc:
        _raise_fetch_failure(
            url=url,
            error_code="permission_denied",
            message=f"URL is blocked by fetch safety policy: {exc.url}",
            hint=build_hint(REASON_BLOCKED_BY_SITE_POLICY),
            next_action=NEXT_ACTION_CHANGE_SOURCE,
        )
    except _FetchBodyLimitExceeded as exc:
        _raise_fetch_failure(
            url=url,
            error_code=_RESPONSE_BODY_TOO_LARGE_ERROR,
            message="Response body exceeded fetch size limit before conversion.",
            http_status=exc.response_context.http_status,
            hint=build_hint(REASON_CONTENT_CONVERSION_FAILED),
            next_action=NEXT_ACTION_CHANGE_SOURCE,
        )
    except RuntimeError as exc:
        if cancellation_token.is_cancelled():
            _raise_fetch_cancelled()
        challenge_context: _FetchContentRuntimeContext | None = None
        challenge_decision = BotChallengeDecision.NONE
        pipeline_error: HtmlPipelineStageError | None = None
        conversion_failure_reason = ""
        if isinstance(exc, _FetchContentConversionError):
            challenge_context = exc.response_context
            conversion_failure_reason = exc.failure_reason
            if isinstance(exc.original_error, HtmlPipelineStageError):
                pipeline_error = exc.original_error
            if isinstance(exc.original_error, _FetchUrlSafetyError):
                _raise_fetch_failure(
                    url=url,
                    error_code="permission_denied",
                    message=f"URL is blocked by fetch safety policy: {exc.original_error.url}",
                    http_status=challenge_context.http_status,
                    hint=build_hint(REASON_BLOCKED_BY_SITE_POLICY),
                    next_action=NEXT_ACTION_CHANGE_SOURCE,
                )
        elif isinstance(exc, HtmlPipelineStageError):
            pipeline_error = exc

        if conversion_failure_reason in {"unsupported_content_encoding", "meta_refresh_requires_browser"}:
            browser_result = _try_playwright_fallback(url=url, **playwright_fallback_kwargs)
            if browser_result is not None:
                return browser_result

        if challenge_context is not None:
            challenge_decision = challenge_context.challenge_decision
            challenge_action = challenge_fallback_action(
                decision=challenge_decision,
                browser_available=True,
            )
            if challenge_action is ChallengeFallbackAction.TRY_BROWSER:
                browser_result = _try_playwright_fallback(url=url, **playwright_fallback_kwargs)
                if browser_result is not None:
                    return browser_result

        if _should_escalate_pipeline_failure_to_browser(
            pipeline_error=pipeline_error,
            response_context=challenge_context,
        ):
            browser_result = _try_playwright_fallback(url=url, **playwright_fallback_kwargs)
            if browser_result is not None:
                return browser_result

        if _should_escalate_conversion_failure_to_browser(
            error_message=str(exc),
            response_context=challenge_context,
        ):
            browser_result = _try_playwright_fallback(url=url, **playwright_fallback_kwargs)
            if browser_result is not None:
                return browser_result

        _raise_fetch_failure(
            url=url,
            error_code=(
                "blocked"
                if challenge_decision is BotChallengeDecision.CONFIRMED
                else "content_conversion_failed"
            ),
            message=str(exc),
            hint=(
                build_hint(REASON_BLOCKED_BY_SITE_POLICY)
                if challenge_decision is BotChallengeDecision.CONFIRMED
                else build_hint(REASON_CONTENT_CONVERSION_FAILED)
            ),
            next_action=NEXT_ACTION_CHANGE_SOURCE,
            http_status=challenge_context.http_status if challenge_context is not None else None,
        )
    finally:
        if should_close_session:
            session.close()

    if fetch_result is None:
        raise RuntimeError("网页抓取流程异常结束，未获得抓取结果")

    challenge = _detect_bot_challenge(
        response=None,
        response_headers=fetch_result.get("response_headers"),
        http_status=fetch_result.get("http_status"),
        content_text=fetch_result.get("content", ""),
    )
    challenge_action = challenge_fallback_action(
        decision=challenge.decision,
        browser_available=True,
    )
    if challenge_action is ChallengeFallbackAction.TRY_BROWSER:
        browser_result = _try_playwright_fallback(url=url, **playwright_fallback_kwargs)
        if browser_result is not None:
            return browser_result
        terminal_challenge_action = challenge_fallback_action(
            decision=challenge.decision,
            browser_available=False,
        )
        if terminal_challenge_action is not ChallengeFallbackAction.FAIL_BLOCKED:
            raise RuntimeError("confirmed challenge did not produce terminal fallback action")
        _raise_fetch_failure(
            url=url,
            error_code="blocked",
            message="Page appears to be a bot challenge page; fetched content is unusable.",
            http_status=fetch_result.get("http_status"),
            hint=build_hint(REASON_BLOCKED_BY_SITE_POLICY),
            next_action=NEXT_ACTION_CHANGE_SOURCE,
        )

    content = fetch_result.get("content", "")
    if len(content.strip()) < _EMPTY_CONTENT_MIN_CHARS:
        _raise_fetch_failure(
            url=url,
            error_code="empty_content",
            message="Page body is empty or too short to be useful.",
            http_status=fetch_result.get("http_status"),
            hint=build_hint(REASON_EMPTY_CONTENT),
            next_action=NEXT_ACTION_CONTINUE_WITHOUT_WEB,
        )

    success: WebPayload = {
        "url": url,
        "final_url": project_safe_url_or_empty(
            str(fetch_result.get("final_url", url) or url)
        ),
        "title": fetch_result.get("title", ""),
        "content": content,
        "fetch_backend": "requests",
        "response_content_length": fetch_result.get("response_content_length"),
        "response_content_digest": fetch_result.get("response_content_digest"),
    }
    _log_fetch_diagnostics(
        completed_text_projection(
            stage="fetch_web_page",
            url=str(fetch_result.get("final_url", url) or url),
            elapsed_seconds=0.0,
            backend=WebDiagnosticBackend.REQUESTS,
            content=content,
            http_status=fetch_result.get("http_status"),
            response_headers=_sanitize_plain_response_headers(
                fetch_result.get("response_headers")
            ),
        )
    )
    return success


def _docling_convert_to_markdown(raw_bytes: bytes, stream_name: str) -> tuple[str, str, str]:
    """使用 Docling 将非 HTML 原始字节转换为 Markdown。

    Args:
        raw_bytes: 页面原始内容字节。
        stream_name: 流名称，决定 Docling 解析模式（如 ``page.pdf``）。

    Returns:
        ``(title, markdown, extraction_source)`` 三元组。

    Raises:
        RuntimeError: Docling 未安装或转换失败时抛出。
    """
    title, markdown, extraction_source = _web_fetch_orchestrator._docling_convert_to_markdown(raw_bytes, stream_name)
    if not title:
        title = _extract_first_markdown_heading(markdown)
    return title, markdown, extraction_source


def _should_route_response_to_html_pipeline(
    *,
    url: str,
    content_type: str,
    response_text: str,
    response_content: bytes,
) -> bool:
    """判断响应是否应进入 HTML 四段式流水线。"""

    return _web_fetch_orchestrator._should_route_response_to_html_pipeline(
        url=url,
        content_type=content_type,
        response_text=response_text,
        response_content=response_content,
    )


def _infer_docling_stream_name(*, url: str, content_type: str) -> str:
    """为 Docling 推断更稳定的输入流名称。

    Args:
        url: 当前响应 URL。
        content_type: 已归一化的小写 Content-Type。

    Returns:
        供 Docling 使用的伪文件名。

    Raises:
        无。
    """

    return _web_fetch_orchestrator._infer_docling_stream_name(url=url, content_type=content_type)


def _fetch_and_convert_content(
    url: str,
    *,
    timeout_seconds: float,
    session: Optional[requests.Session] = None,
    headers: Mapping[str, str] | None = None,
    content_type_probe: ContentProbePayload | None = None,
    egress_policy: WebEgressPolicy,
    resource_budget: WebResourceBudget,
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
    cancellation_token: CancellationToken | None = None,
) -> _FetchContentResult:
    """先下载页面内容，再按内容类型转换为低噪音 Markdown。"""

    return cast(
        _FetchContentResult,
        _web_fetch_orchestrator._fetch_and_convert_content(
            url,
            timeout_seconds=timeout_seconds,
            resolve_timeout_budget=_resolve_timeout_budget,
            normalize_url_for_http=_normalize_url_for_http,
            build_referer=_build_referer,
            convert_html=convert_html_to_llm_markdown,
            convert_non_html=_docling_convert_to_markdown,
            session=session,
            get_web_session=_get_web_session,
            headers=dict(headers) if headers is not None else None,
            build_fetch_headers=_build_fetch_headers,
            egress_policy=egress_policy,
            resource_budget=resource_budget,
            content_type_probe=content_type_probe,
            timeout_budget=timeout_budget,
            deadline_monotonic=deadline_monotonic,
            cancellation_token=cancellation_token,
        ),
    )


def _close_playwright_browser() -> None:
    """关闭 Playwright Browser 和 Playwright 运行时单例（atexit 注册）。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    _web_playwright_backend._close_playwright_browser()


def _normalize_playwright_channel(playwright_channel: str | None) -> str | None:
    """标准化 Playwright channel 配置。

    Args:
        playwright_channel: 原始 channel 配置。

    Returns:
        规整后的 channel；空字符串时返回 `None`。

    Raises:
        无。
    """

    return _web_playwright_backend._normalize_playwright_channel(playwright_channel)


def _normalize_playwright_storage_state_dir(path_value: str | None) -> str | None:
    """标准化 Playwright storage state 目录路径。

    Args:
        path_value: 原始路径配置。

    Returns:
        目录路径字符串；未配置时返回 `None`。

    Raises:
        无。
    """

    return _web_playwright_backend._normalize_playwright_storage_state_dir(path_value)


def _resolve_playwright_storage_state_path(
    *,
    url: str,
    playwright_storage_state_dir: str | None,
) -> str:
    """按 host 解析 Playwright storage state 文件路径。

    Args:
        url: 当前抓取 URL。
        playwright_storage_state_dir: storage state 目录配置。

    Returns:
        命中的 storage state 文件绝对路径；未命中时返回空字符串。

    Raises:
        无。
    """

    return _web_playwright_backend._resolve_playwright_storage_state_path(
        url=url,
        playwright_storage_state_dir=playwright_storage_state_dir,
    )


def _get_playwright_browser(
    *,
    playwright_channel: str | None = None,
    headless: bool = True,
) -> _web_playwright_backend._BrowserProtocol | None:
    """获取（或懒初始化）全局 Playwright Browser 单例。

    使用 double-checked locking 保证线程安全。若 playwright 未安装或启动失败，
    返回 None 而不抛异常。

    Args:
        无。

    Returns:
        playwright.sync_api.Browser 单例，或 None（不可用时）。

    Raises:
        无。
    """

    return _web_playwright_backend._get_playwright_browser(
        playwright_channel=playwright_channel,
        headless=headless,
    )


def _route_handler_abort_resources(
    route: _web_playwright_backend._RouteProtocol,
    *,
    egress_policy: WebEgressPolicy,
) -> None:
    """Playwright 路由拦截器：中止图片/字体/媒体请求，放行其余资源。

    降低页面渲染流量，加快加载速度。

    Args:
        route: playwright.sync_api.Route 对象。
        egress_policy: 当前 Web 调用唯一的出站策略。

    Returns:
        无。

    Raises:
        无。
    """

    _web_playwright_backend._route_handler_abort_resources(
        route,
        egress_policy=egress_policy,
    )


def _maybe_warmup_playwright_page(
    *,
    page: _web_playwright_backend._PageProtocol,
    url: str,
    deadline_monotonic: float,
    egress_policy: WebEgressPolicy,
) -> None:
    """在浏览器回退前先做一次同域首页预热。

    部分站点会在首页下发 Cookie、地域态或轻量挑战票据。requests 路径
    已有 warmup，这里为 Playwright 路径补齐同样的机械预热，减少
    “浏览器上下文过于冷启动”带来的差异。

    Args:
        page: Playwright Page。
        url: 目标 URL。
        deadline_monotonic: 本次浏览器抓取总预算 deadline。
        egress_policy: 当前 Web 调用唯一的出站策略。

    Returns:
        无。

    Raises:
        无。
    """

    _web_playwright_backend._maybe_warmup_playwright_page(
        page=page,
        url=url,
        deadline_monotonic=deadline_monotonic,
        build_domain_home_url=_build_domain_home_url,
        normalize_url_for_http=_normalize_url_for_http,
        egress_policy=egress_policy,
        time_monotonic=time.monotonic,
    )


def _settle_playwright_page(
    *,
    page: _web_playwright_backend._PageProtocol,
    deadline_monotonic: float,
) -> None:
    """在浏览器导航后做有上限的页面稳定化等待。

    不直接无限等待 `networkidle`，而是用一组有上限的小等待，兼顾 SPA
    首屏渲染与长连接页面，尽量逼近人工浏览器“打开后停留片刻”的效果。

    Args:
        page: Playwright Page。
        deadline_monotonic: 本次浏览器抓取总预算 deadline。

    Returns:
        无。

    Raises:
        无。
    """

    _web_playwright_backend._settle_playwright_page(
        page=page,
        deadline_monotonic=deadline_monotonic,
        time_monotonic=time.monotonic,
    )


def _get_remaining_playwright_timeout_ms(deadline_monotonic: float) -> int:
    """计算 Playwright 当前阶段还可使用的剩余超时。

    Args:
        deadline_monotonic: 本次浏览器抓取总预算 deadline。

    Returns:
        剩余可用毫秒数；预算已耗尽时返回 0。

    Raises:
        无。
    """

    return _web_playwright_backend._get_remaining_playwright_timeout_ms(
        deadline_monotonic,
        time_monotonic=time.monotonic,
    )


def _require_playwright_timeout_ms(deadline_monotonic: float) -> int:
    """为必需的 Playwright 阶段解析剩余超时。

    Args:
        deadline_monotonic: 本次浏览器抓取总预算 deadline。

    Returns:
        当前阶段可用的毫秒超时。

    Raises:
        RuntimeError: 当浏览器总预算已耗尽时抛出。
    """

    return _web_playwright_backend._require_playwright_timeout_ms(
        deadline_monotonic,
        time_monotonic=time.monotonic,
    )


def _playwright_sync_worker(
    *,
    url: str,
    timeout_seconds: float,
    headers: Mapping[str, str] | None = None,
    playwright_channel: str | None = None,
    playwright_storage_state_path: str = "",
    egress_policy: WebEgressPolicy,
    resource_budget: WebResourceBudget,
) -> WebPayload:
    """在独立线程中执行完整的 Playwright 同步抓取流程。

    不得在 asyncio event loop 所在线程直接调用；须通过 ThreadPoolExecutor 提交。

    流程：获取 Browser 单例 → 创建隔离 BrowserContext → stealth_sync → 路由拦截
    → page.goto → 检查 content-type → bounded TreeWalker 预检 → page.content()
    → 实际长度复核 → Docling 转 Markdown。

    Args:
        url: 已通过安全校验的网页链接。
        timeout_seconds: 本次浏览器回退总预算秒数。
        headers: 可选额外请求头（当前仍以浏览器默认导航画像为准，不直接覆写 Context headers）。
        playwright_channel: 浏览器回退使用的 Chromium channel。
        playwright_storage_state_path: 浏览器回退可选 storage state 文件路径。
        egress_policy: 当前 Web 调用唯一的出站策略。
        resource_budget: HTTP、browser 与诊断共享的完整资源预算。

    Returns:
        成功时返回含 ``ok=True`` 的结果字典；失败时抛出异常由调用方处理。

    Raises:
        RuntimeError: playwright 未安装、Browser 不可用、页面加载失败、内容转换失败等。
    """

    return _web_playwright_backend._playwright_sync_worker(
        url=url,
        timeout_seconds=timeout_seconds,
        headers=headers,
        playwright_channel=playwright_channel,
        playwright_storage_state_path=playwright_storage_state_path,
        get_playwright_browser=_get_playwright_browser,
        egress_policy=egress_policy,
        resource_budget=resource_budget,
        build_domain_home_url=_build_domain_home_url,
        normalize_url_for_http=_normalize_url_for_http,
        sanitize_response_headers=_sanitize_plain_response_headers,
        convert_html_to_markdown=cast(
            _web_playwright_backend._HtmlConverterProtocol,
            convert_html_to_llm_markdown,
        ),
        time_monotonic=time.monotonic,
    )


def _fetch_and_convert_with_playwright(
    *,
    url: str,
    timeout_seconds: float,
    headers: Mapping[str, str] | None = None,
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
    playwright_channel: str | None = None,
    playwright_storage_state_path: str = "",
    egress_policy: WebEgressPolicy,
    resource_budget: WebResourceBudget,
    cancellation_token: CancellationToken | None = None,
) -> WebPayload:
    """使用 Playwright 执行浏览器抓取并转换为 Markdown。

    架构：优先在独立子进程中执行同步 worker，以便在超时或取消时硬终止。
    Browser 为 worker 进程内单例，Context 为每次请求独立创建并在完成后关闭。

    Args:
        url: 已通过安全校验的网页链接。
        timeout_seconds: 浏览器回退总预算秒数。
        headers: 可选请求头（当前透传给 worker，供将来扩展使用）。
        timeout_budget: Runner 注入的单次 tool call 总预算。
        deadline_monotonic: 当前工具调用的单调时钟 deadline。
        playwright_channel: 浏览器回退使用的 Chromium channel。
        playwright_storage_state_path: 浏览器回退可选 storage state 文件路径。
        egress_policy: 当前 Web 调用唯一的出站策略。
        resource_budget: HTTP、browser 与诊断共享的完整资源预算。
        cancellation_token: 当前工具调用的取消令牌。

    Returns:
        成功时：``{ok: True, title, content, final_url}``，结构与 docling 路径一致。
        失败时：``{ok: False, availability, reason}`` 或超时字典。

    Raises:
        _FetchUrlSafetyError: Playwright URL 被安全策略拒绝时抛出。
    """

    return _web_playwright_backend._fetch_and_convert_with_playwright(
        url=url,
        timeout_seconds=timeout_seconds,
        headers=headers,
        timeout_budget=timeout_budget,
        deadline_monotonic=deadline_monotonic,
        playwright_channel=playwright_channel,
        playwright_storage_state_path=playwright_storage_state_path,
        egress_policy=egress_policy,
        resource_budget=resource_budget,
        cancellation_token=cancellation_token,
        resolve_timeout_budget=_resolve_timeout_budget,
        playwright_sync_worker=_playwright_sync_worker,
        detect_bot_challenge=_detect_bot_challenge,
    )


def _extract_first_markdown_heading(markdown: str) -> str:
    """从 Markdown 文本中提取第一个标题行的文本。

    Args:
        markdown: Markdown 格式文本。

    Returns:
        标题文本；无标题时返回空字符串。

    Raises:
        无。
    """

    for line in markdown.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return ""


def _build_fetch_headers(url: str) -> dict[str, str]:
    """构建网页抓取请求头。

    Args:
        url: 目标网页 URL。

    Returns:
        请求头字典。

    Raises:
        无。
    """

    if _is_sec_host(url):
        sec_user_agent = (os.environ.get(SEC_USER_AGENT_ENV) or _DEFAULT_SEC_USER_AGENT).strip()
        return {
            "User-Agent": sec_user_agent or _DEFAULT_SEC_USER_AGENT,
            "Accept": _DEFAULT_ACCEPT,
            "Accept-Language": _DEFAULT_ACCEPT_LANGUAGE,
            "Accept-Encoding": _BOUNDED_ACCEPT_ENCODING,
            "Connection": "keep-alive",
        }

    return {
        "User-Agent": _DEFAULT_BROWSER_USER_AGENT,
        "Accept": _DEFAULT_ACCEPT,
        "Accept-Language": _DEFAULT_ACCEPT_LANGUAGE,
        "Accept-Encoding": _BOUNDED_ACCEPT_ENCODING,
        "Connection": "keep-alive",
        # --- 现代 Chrome 标准 headers，缺失是典型爬虫特征 ---
        "Sec-Ch-Ua": _DEFAULT_SEC_CH_UA,
        "Sec-Ch-Ua-Mobile": _DEFAULT_SEC_CH_UA_MOBILE,
        "Sec-Ch-Ua-Platform": _DEFAULT_SEC_CH_UA_PLATFORM,
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }


def _is_sec_host(url: str) -> bool:
    """判断 URL 是否指向 SEC 域名。

    Args:
        url: 目标 URL。

    Returns:
        是 SEC 域名返回 ``True``，否则返回 ``False``。

    Raises:
        无。
    """

    host = (urlparse(url).hostname or "").lower().strip()
    return bool(host) and (host == "sec.gov" or host.endswith(".sec.gov") or host == "data.sec.gov")


def _normalize_whitespace(text: str) -> str:
    """规整文本中的空白字符。

    Args:
        text: 原始文本。

    Returns:
        规整后的文本。

    Raises:
        无。
    """

    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join([line for line in lines if line])
