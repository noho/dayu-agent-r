"""联网检索 provider 与结构化事实组装。

本模块只负责 `search_web` 的 provider 选择、请求发送、结果解析与
返回结构化检索事实，不承载网页抓取、HTML 转换、浏览器回退逻辑或
面向 LLM 的下一步动作提示。
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Final, NotRequired, Optional, Protocol, TypedDict
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue

from . import web_fetch_orchestrator as _web_fetch_orchestrator
from .web_challenge_detection import BotChallengeDecision, detect_bot_challenge
from .web_egress_policy import WebEgressPolicy
from .web_http_session import (
    ProxyPeerProofIncompatibleError,
    WebHttpTransportPolicy,
    _send_authorized_plain_request,
)
from .web_resource_budget import HttpResourceBudget

MODULE = "ENGINE.WEB_SEARCH"
_LOGGER = logging.getLogger(__name__)
SERPER_API_KEY_ENV = "SERPER_API_KEY"
TAVILY_API_KEY_ENV = "TAVILY_API_KEY"
_TAVILY_ENDPOINT: Final[str] = "https://api.tavily.com/search"
_SERPER_ENDPOINT: Final[str] = "https://google.serper.dev/search"
_DUCKDUCKGO_ENDPOINT: Final[str] = "https://duckduckgo.com/html/"

_ALL_PROVIDERS_UNAVAILABLE_MESSAGE: Final[str] = "联网检索失败：所有 provider 均不可用"
_SEARCH_CANCELLED_MESSAGE: Final[str] = "工具调用已取消"
_SEARCH_ACCEPT_ENCODING: Final[str] = "gzip, deflate"
_DUCKDUCKGO_NO_RESULTS_TEXT: Final[frozenset[str]] = frozenset({"No results.", "No more results."})
_DUCKDUCKGO_CHALLENGE_SELECTORS: Final[tuple[str, ...]] = (
    "form#challenge-form",
    "form[action*='challenge']",
    ".anomaly-modal",
    "#anomaly-modal",
    "div.captcha",
    "input[name='captcha']",
)
_DUCKDUCKGO_LOGIN_ACTION_TOKENS: Final[tuple[str, ...]] = (
    "login",
    "signin",
    "auth",
)


class Log:
    """迁移 Web search provider 的窄日志适配器。

    Args:
        无。

    Returns:
        无。

    Raises:
        无。
    """

    @staticmethod
    def warn(message: str, *, module: str | None = None) -> None:
        """记录 warning 日志。

        Args:
            message: 日志正文。
            module: OLD 模块标签。

        Returns:
            无。

        Raises:
            无。
        """

        _LOGGER.warning("[%s] %s", module or MODULE, message)


class SearchResultRow(TypedDict):
    """联网检索单条结果。"""

    title: str
    url: str
    snippet: str
    published_date: str


class SearchWebProviderResult(TypedDict):
    """联网检索 provider 返回的结构化事实。"""

    query: str
    domains: list[str]
    total: int
    preferred_result: SearchResultRow | None
    results: list[SearchResultRow]


class WebSearchCancelledError(Exception):
    """联网检索观察到 Host 取消时的模块内异常。

    :param message: 中性的取消说明；不包含 Host 治理字段或恢复提示。
    :returns: 无。
    :raises Exception: 构造期不主动抛出异常。
    """

    def __init__(self, message: str) -> None:
        """初始化取消异常。

        :param message: 中性的取消说明。
        :returns: ``None``。
        :raises Exception: 构造期不主动抛出异常。
        """

        super().__init__(message)
        self.message = message


class WebSearchProviderUnavailableError(RuntimeError):
    """所有搜索 provider 均不可用时的稳定业务失败。

    :param message: 稳定业务失败说明。
    :returns: 无。
    :raises Exception: 构造期不主动抛出异常。
    """

    def __init__(self, message: str) -> None:
        """初始化 provider 不可用异常。

        :param message: 稳定业务失败说明。
        :returns: ``None``。
        :raises Exception: 构造期不主动抛出异常。
        """

        super().__init__(message)
        self.message = message


class WebSearchProviderResponseError(RuntimeError):
    """搜索 provider response shape 无法按冻结协议解释。

    Args:
        reason: provider response 失败原因。
        message: 中性诊断说明。

    Returns:
        异常实例。

    Raises:
        无。
    """

    def __init__(self, *, reason: str, message: str) -> None:
        """初始化 provider response error。

        Args:
            reason: provider response 失败原因。
            message: 中性诊断说明。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(message)
        self.reason = reason
        self.message = message


class WebSearchProviderResourceError(RuntimeError):
    """搜索 provider response 超过 Web 资源预算。

    Args:
        message: 中性的资源失败说明。

    Returns:
        异常实例。

    Raises:
        无。
    """

    def __init__(self, message: str) -> None:
        """初始化 provider response 资源错误。

        Args:
            message: 中性的资源失败说明。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(message)
        self.message = message


class TavilyResultItem(TypedDict):
    """Tavily 响应结果项。"""

    title: NotRequired[str]
    url: NotRequired[str]
    content: NotRequired[str]
    published_date: NotRequired[str]


class TavilyResponsePayload(TypedDict):
    """Tavily 响应载荷。"""

    results: NotRequired[list[TavilyResultItem]]


class SerperOrganicItem(TypedDict):
    """Serper organic 结果项。"""

    title: NotRequired[str]
    link: NotRequired[str]
    snippet: NotRequired[str]


class SerperResponsePayload(TypedDict):
    """Serper 响应载荷。"""

    organic: NotRequired[list[SerperOrganicItem]]


class _TimeoutBudgetResolver(Protocol):
    """搜索请求 timeout 解析协议。"""

    def __call__(
        self,
        timeout_seconds: float,
        *,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
    ) -> float:
        """解析当前请求可用 timeout。"""

        ...


def search_public_web(
    *,
    query: str,
    domains: Optional[list[str]],
    recency_days: Optional[int],
    max_results: int,
    max_search_results: int,
    provider: str,
    request_timeout_seconds: float,
    timeout_budget: float | None,
    deadline_monotonic: float | None,
    egress_policy: WebEgressPolicy,
    transport_policy: WebHttpTransportPolicy,
    normalize_whitespace: Callable[[str], str],
    resolve_timeout_budget: _TimeoutBudgetResolver,
    http_resource_budget: HttpResourceBudget,
    cancellation_token: CancellationToken | None = None,
) -> SearchWebProviderResult:
    """执行公开网页检索并组装结构化 provider 事实。

    Args:
        query: 原始查询文本。
        domains: 原始域名限制列表。
        recency_days: 最近天数限制。
        max_results: 当前调用声明的结果上限。
        max_search_results: tool 注册时声明的最大结果上限。
        provider: provider 选择策略。
        request_timeout_seconds: provider 请求超时秒数。
        timeout_budget: 单次 tool call 总预算。
        deadline_monotonic: 当前调用 deadline。
        egress_policy: 与 fetch 同源的 private/custom-port typed policy。
        transport_policy: 与 fetch 同源的 attempt-local HTTP transport policy。
        normalize_whitespace: 文本空白规整函数。
        resolve_timeout_budget: timeout 预算解析函数。
        http_resource_budget: 搜索响应 wire/decoded body 预算。
        cancellation_token: 当前工具调用取消令牌。

    Returns:
        结构化联网检索事实，尚未包含面向 LLM 的下一步动作提示。

    Raises:
        ValueError: 当 query 或 domains 非法时抛出。
        WebSearchProviderUnavailableError: 当所有 provider 都失败时抛出。
        WebSearchProviderResourceError: 最终决定性失败为响应资源超限时抛出。
        ProxyPeerProofIncompatibleError: active proxy 与 peer proof 冲突时抛出。
    """

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query 不能为空")

    normalized_domains = _normalize_domains(domains)
    limited_results = max(1, min(int(max_results), max_search_results))
    resolved_provider = _resolve_provider(preferred=provider)
    _raise_if_search_cancelled(cancellation_token)
    last_decisive_error: WebSearchProviderResponseError | WebSearchProviderResourceError | None = None

    for candidate_provider in _candidate_providers(resolved_provider):
        _raise_if_search_cancelled(cancellation_token)
        try:
            _raise_if_search_cancelled(cancellation_token)
            if candidate_provider == "tavily":
                rows = _search_with_tavily(
                    query=normalized_query,
                    domains=normalized_domains,
                    recency_days=recency_days,
                    max_results=limited_results,
                    timeout_seconds=request_timeout_seconds,
                    timeout_budget=timeout_budget,
                    deadline_monotonic=deadline_monotonic,
                    egress_policy=egress_policy,
                    transport_policy=transport_policy,
                    resolve_timeout_budget=resolve_timeout_budget,
                    http_resource_budget=http_resource_budget,
                )
            elif candidate_provider == "serper":
                rows = _search_with_serper(
                    query=normalized_query,
                    domains=normalized_domains,
                    recency_days=recency_days,
                    max_results=limited_results,
                    timeout_seconds=request_timeout_seconds,
                    timeout_budget=timeout_budget,
                    deadline_monotonic=deadline_monotonic,
                    egress_policy=egress_policy,
                    transport_policy=transport_policy,
                    resolve_timeout_budget=resolve_timeout_budget,
                    http_resource_budget=http_resource_budget,
                )
            else:
                rows = _search_with_duckduckgo(
                    query=normalized_query,
                    domains=normalized_domains,
                    max_results=limited_results,
                    timeout_seconds=request_timeout_seconds,
                    timeout_budget=timeout_budget,
                    deadline_monotonic=deadline_monotonic,
                    egress_policy=egress_policy,
                    transport_policy=transport_policy,
                    normalize_whitespace=normalize_whitespace,
                    resolve_timeout_budget=resolve_timeout_budget,
                    http_resource_budget=http_resource_budget,
                )
            _raise_if_search_cancelled(cancellation_token)
        except Exception as exc:  # pragma: no cover - 失败路径由单测通过 monkeypatch 覆盖
            if _is_search_cancelled_error(exc):
                raise
            if isinstance(exc, ProxyPeerProofIncompatibleError):
                raise
            if isinstance(
                exc,
                (WebSearchProviderResponseError, WebSearchProviderResourceError),
            ):
                last_decisive_error = exc
            _log_search_provider_failure(
                candidate_provider=candidate_provider,
                error=exc,
            )
            continue

        visible_results = _filter_visible_results(
            rows=rows,
            egress_policy=egress_policy,
        )[:limited_results]
        preferred_result = _build_search_web_preferred_result(visible_results)
        return {
            "query": normalized_query,
            "domains": normalized_domains,
            "total": len(visible_results),
            "preferred_result": preferred_result,
            "results": visible_results,
        }

    if last_decisive_error is not None:
        raise last_decisive_error
    raise WebSearchProviderUnavailableError(_ALL_PROVIDERS_UNAVAILABLE_MESSAGE)


def _raise_if_search_cancelled(cancellation_token: CancellationToken | None) -> None:
    """检查联网检索取消令牌，并抛出模块内取消信号。

    Args:
        cancellation_token: 当前工具调用取消令牌。

    Returns:
        无。

    Raises:
        WebSearchCancelledError: 当前调用已被 Host 请求取消时抛出。
    """

    if cancellation_token is None or not cancellation_token.is_cancelled():
        return
    _ = cancellation_token.cancel_reason()
    raise WebSearchCancelledError(message=_SEARCH_CANCELLED_MESSAGE)


def _is_search_cancelled_error(error: Exception) -> bool:
    """判断异常是否为联网检索取消错误。

    Args:
        error: provider 调用阶段捕获到的异常。

    Returns:
        若异常表示工具取消则返回 ``True``。

    Raises:
        无。
    """

    return isinstance(error, WebSearchCancelledError)


def _filter_visible_results(
    *,
    rows: list[SearchResultRow],
    egress_policy: WebEgressPolicy,
) -> list[SearchResultRow]:
    """按 URL 安全策略过滤 provider 结果。

    Args:
        rows: provider 返回的原始结果列表。
        egress_policy: 与 fetch 同源的 private/custom-port typed policy。

    Returns:
        通过安全过滤的结果列表。

    Raises:
        无。
    """

    return [row for row in rows if egress_policy.is_url_allowed(row["url"])]


def _default_resolve_timeout_budget(
    timeout_seconds: float,
    *,
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
) -> float:
    """默认 timeout 解析函数。

    Args:
        timeout_seconds: 调用方声明的基础 timeout。
        timeout_budget: 未使用的总预算参数。
        deadline_monotonic: 未使用的 deadline 参数。

    Returns:
        至少为 1 秒的 timeout。

    Raises:
        无。
    """

    _ = (timeout_budget, deadline_monotonic)
    return max(1.0, float(timeout_seconds))


def _get_search_provider_api_key_env_name(provider: str) -> str | None:
    """返回联网检索 provider 对应的 API key 环境变量名。

    Args:
        provider: 已归一化的联网检索 provider。

    Returns:
        若该 provider 依赖 API key，则返回环境变量名；否则返回 `None`。

    Raises:
        无。
    """

    if provider == "tavily":
        return TAVILY_API_KEY_ENV
    if provider == "serper":
        return SERPER_API_KEY_ENV
    return None


def _has_configured_search_provider_api_key(provider: str) -> bool:
    """判断联网检索 provider 是否已配置可用 API key。

    Args:
        provider: 已归一化的联网检索 provider。

    Returns:
        若 provider 不依赖 API key，或已配置非空 API key，则返回 `True`；否则返回 `False`。

    Raises:
        无。
    """

    env_name = _get_search_provider_api_key_env_name(provider)
    if not env_name:
        return True
    return bool(os.environ.get(env_name, "").strip())


def _log_search_provider_failure(
    *,
    candidate_provider: str,
    error: Exception,
) -> None:
    """记录联网检索 provider 的真实失败日志。

    Args:
        candidate_provider: 当前尝试的 provider。
        error: provider 抛出的异常对象。

    Returns:
        无。

    Raises:
        无。
    """

    Log.warn(f"provider={candidate_provider} 检索失败: {error}", module=MODULE)


def _normalize_domains(domains: Optional[list[str]]) -> list[str]:
    """归一化域名过滤列表。

    Args:
        domains: 原始域名列表。

    Returns:
        归一化后的域名列表。

    Raises:
        ValueError: 当域名元素非法时抛出。
    """

    if domains is None:
        return []
    normalized: list[str] = []
    for item in domains:
        if not isinstance(item, str):
            raise ValueError("domains 元素必须是字符串")
        value = item.strip().lower()
        if not value:
            continue
        normalized.append(value)
    return normalized


def _resolve_provider(*, preferred: str) -> str:
    """解析 provider 策略。

    Args:
        preferred: 首选 provider。

    Returns:
        规范化 provider 名称。

    Raises:
        ValueError: 当 provider 非法时抛出。
    """

    normalized = preferred.strip().lower() if isinstance(preferred, str) else "auto"
    allowed = {"auto", "tavily", "serper", "duckduckgo"}
    if normalized not in allowed:
        raise ValueError(f"不支持的 web provider: {preferred}")
    return normalized


def _candidate_providers(provider: str) -> list[str]:
    """获取 provider 候选顺序。

    Args:
        provider: 已归一化 provider。

    Returns:
        候选 provider 列表。

    Raises:
        无。
    """

    if provider == "auto":
        candidates: list[str] = []
        if _has_configured_search_provider_api_key("tavily"):
            candidates.append("tavily")
        if _has_configured_search_provider_api_key("serper"):
            candidates.append("serper")
        candidates.append("duckduckgo")
        return candidates
    return [provider, "duckduckgo"] if provider in {"tavily", "serper"} else ["duckduckgo"]


def _search_with_tavily(
    *,
    query: str,
    domains: list[str],
    recency_days: Optional[int],
    max_results: int,
    timeout_seconds: float,
    egress_policy: WebEgressPolicy,
    transport_policy: WebHttpTransportPolicy,
    resolve_timeout_budget: _TimeoutBudgetResolver,
    http_resource_budget: HttpResourceBudget,
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
) -> list[SearchResultRow]:
    """使用 Tavily API 搜索。

    Args:
        query: 检索关键词。
        domains: 域名过滤。
        recency_days: 最近天数。
        max_results: 返回数量。
        timeout_seconds: HTTP 请求超时秒数。
        egress_policy: 与 fetch 同源的 endpoint egress policy。
        transport_policy: 与 fetch 同源的 attempt-local HTTP transport policy。
        resolve_timeout_budget: timeout 预算解析函数。
        http_resource_budget: Web response 资源预算唯一真源。
        timeout_budget: Runner 注入的单次 tool call 总预算。
        deadline_monotonic: 当前工具调用的单调时钟 deadline。

    Returns:
        结果列表。

    Raises:
        RuntimeError: 当 key 缺失或请求失败时抛出。
    """

    api_key = os.environ.get(TAVILY_API_KEY_ENV, "").strip()
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY 未配置")

    payload: dict[str, JsonValue] = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
    }
    if domains:
        payload["include_domains"] = [domain for domain in domains]
    if recency_days is not None and recency_days >= 0:
        payload["days"] = int(recency_days)

    lease = _send_authorized_plain_request(
        egress_policy=egress_policy,
        url=_TAVILY_ENDPOINT,
        method="POST",
        headers={"Accept-Encoding": _SEARCH_ACCEPT_ENCODING},
        timeout=resolve_timeout_budget(
            timeout_seconds,
            timeout_budget=timeout_budget,
            deadline_monotonic=deadline_monotonic,
        ),
        stream=True,
        transport_policy=transport_policy,
        request_params=None,
        request_json=payload,
    )
    with lease:
        response = lease.response
        _materialize_bounded_search_response(
            response,
            http_resource_budget=http_resource_budget,
        )
        _raise_for_search_provider_status(response)
        data = response.json()
    if not isinstance(data, dict):
        return []

    rows: list[SearchResultRow] = []
    for item in data.get("results", []) or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "title": str(item.get("title", "")).strip(),
                "url": str(item.get("url", "")).strip(),
                "snippet": str(item.get("content", "")).strip(),
                "published_date": str(item.get("published_date", "")).strip(),
            }
        )
    return rows


def _search_with_serper(
    *,
    query: str,
    domains: list[str],
    recency_days: Optional[int],
    max_results: int,
    timeout_seconds: float,
    egress_policy: WebEgressPolicy,
    transport_policy: WebHttpTransportPolicy,
    resolve_timeout_budget: _TimeoutBudgetResolver,
    http_resource_budget: HttpResourceBudget,
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
) -> list[SearchResultRow]:
    """使用 Serper API 搜索。

    Args:
        query: 检索关键词。
        domains: 域名过滤。
        recency_days: 最近天数。
        max_results: 返回数量。
        timeout_seconds: HTTP 请求超时秒数。
        egress_policy: 与 fetch 同源的 endpoint egress policy。
        transport_policy: 与 fetch 同源的 attempt-local HTTP transport policy。
        resolve_timeout_budget: timeout 预算解析函数。
        http_resource_budget: Web response 资源预算唯一真源。
        timeout_budget: Runner 注入的单次 tool call 总预算。
        deadline_monotonic: 当前工具调用的单调时钟 deadline。

    Returns:
        结果列表。

    Raises:
        RuntimeError: 当 key 缺失或请求失败时抛出。
    """

    api_key = os.environ.get(SERPER_API_KEY_ENV, "").strip()
    if not api_key:
        raise RuntimeError("SERPER_API_KEY 未配置")

    query_with_domain = query
    if domains:
        domain_expr = " OR ".join(f"site:{domain}" for domain in domains)
        query_with_domain = f"({query}) ({domain_expr})"

    payload: dict[str, JsonValue] = {
        "q": query_with_domain,
        "num": max_results,
    }
    if recency_days is not None and recency_days >= 0:
        payload["tbs"] = f"qdr:d{int(recency_days)}"

    lease = _send_authorized_plain_request(
        egress_policy=egress_policy,
        url=_SERPER_ENDPOINT,
        method="POST",
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
            "Accept-Encoding": _SEARCH_ACCEPT_ENCODING,
        },
        timeout=resolve_timeout_budget(
            timeout_seconds,
            timeout_budget=timeout_budget,
            deadline_monotonic=deadline_monotonic,
        ),
        stream=True,
        transport_policy=transport_policy,
        request_params=None,
        request_json=payload,
    )
    with lease:
        response = lease.response
        _materialize_bounded_search_response(
            response,
            http_resource_budget=http_resource_budget,
        )
        _raise_for_search_provider_status(response)
        data = response.json()
    if not isinstance(data, dict):
        return []

    rows: list[SearchResultRow] = []
    for item in data.get("organic", []) or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "title": str(item.get("title", "")).strip(),
                "url": str(item.get("link", "")).strip(),
                "snippet": str(item.get("snippet", "")).strip(),
                "published_date": "",
            }
        )
    return rows


def _search_with_duckduckgo(
    *,
    query: str,
    domains: list[str],
    max_results: int,
    timeout_seconds: float,
    egress_policy: WebEgressPolicy,
    transport_policy: WebHttpTransportPolicy,
    normalize_whitespace: Callable[[str], str],
    resolve_timeout_budget: _TimeoutBudgetResolver,
    http_resource_budget: HttpResourceBudget,
    timeout_budget: float | None = None,
    deadline_monotonic: float | None = None,
) -> list[SearchResultRow]:
    """使用 DuckDuckGo HTML 页面搜索。

    Args:
        query: 检索关键词。
        domains: 域名过滤。
        max_results: 返回数量。
        timeout_seconds: HTTP 请求超时秒数。
        egress_policy: 与 fetch 同源的 endpoint egress policy。
        transport_policy: 与 fetch 同源的 attempt-local HTTP transport policy。
        normalize_whitespace: 文本空白规整函数。
        resolve_timeout_budget: timeout 预算解析函数。
        http_resource_budget: Web response 资源预算唯一真源。
        timeout_budget: Runner 注入的单次 tool call 总预算。
        deadline_monotonic: 当前工具调用的单调时钟 deadline。

    Returns:
        结果列表。

    Raises:
        RuntimeError: 当请求失败时抛出。
    """

    query_with_domain = query
    if domains:
        query_with_domain = f"{query} " + " ".join(f"site:{domain}" for domain in domains)

    lease = _send_authorized_plain_request(
        egress_policy=egress_policy,
        url=_DUCKDUCKGO_ENDPOINT,
        method="GET",
        timeout=resolve_timeout_budget(
            timeout_seconds,
            timeout_budget=timeout_budget,
            deadline_monotonic=deadline_monotonic,
        ),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Encoding": _SEARCH_ACCEPT_ENCODING,
        },
        stream=True,
        transport_policy=transport_policy,
        request_params={"q": query_with_domain},
        request_json=None,
    )
    with lease:
        response = lease.response
        _materialize_bounded_search_response(
            response,
            http_resource_budget=http_resource_budget,
        )
        _raise_for_search_provider_status(response)
        return _parse_duckduckgo_html(
            html=response.text,
            response=response,
            max_results=max_results,
            normalize_whitespace=normalize_whitespace,
        )


def _materialize_bounded_search_response(
    response: requests.Response,
    *,
    http_resource_budget: HttpResourceBudget,
) -> None:
    """在解析 provider payload 前执行共享 wire/codec 资源预算。

    Args:
        response: 使用 ``stream=True`` 获得的 provider response。
        http_resource_budget: Web response 资源预算唯一真源。

    Returns:
        无。

    Raises:
        WebSearchProviderResourceError: wire 或 decoded body 超限时抛出。
        RuntimeError: content encoding 无法安全有界解码时透出。
    """

    try:
        _web_fetch_orchestrator._materialize_response_body(
            response,
            http_resource_budget=http_resource_budget,
        )
    except _web_fetch_orchestrator._FetchBodyLimitExceeded as exc:
        raise WebSearchProviderResourceError(
            "Search provider response body exceeded the configured Web resource limit."
        ) from exc


def _raise_for_search_provider_status(response: requests.Response) -> None:
    """拒绝 redirect，并对 HTTP error status 使用 requests 标准异常。

    固定 provider endpoint 不跟随自动 redirect，避免在 search module 内建立
    第二套 redirect/egress owner。

    Args:
        response: 已有界物化的 provider response。

    Returns:
        无。

    Raises:
        requests.HTTPError: response 是 redirect 或标准 HTTP error 时抛出。
    """

    if 300 <= response.status_code < 400:
        raise requests.HTTPError(
            "Search provider redirect is not allowed.",
            response=response,
        )
    response.raise_for_status()


def _parse_duckduckgo_html(
    *,
    html: str,
    response: requests.Response | None,
    max_results: int,
    normalize_whitespace: Callable[[str], str],
) -> list[SearchResultRow]:
    """按冻结的 DuckDuckGo HTML shape 解析结果。

    Args:
        html: DuckDuckGo HTML response 文本。
        response: 可选原始响应，只用于共享 challenge detector 的状态与头部证据。
        max_results: 通过完整 shape 校验后最多投影的结果数。
        normalize_whitespace: 文本空白规整函数。

    Returns:
        已知结果 shape 的有界结果，或 explicit no-results 对应的空列表。

    Raises:
        WebSearchProviderResponseError: challenge/login shape、未知 shape 或
            malformed 比例超过冻结阈值时抛出。
    """

    soup = BeautifulSoup(html, "lxml")
    challenge = detect_bot_challenge(
        response=response,
        content_text=html,
    )
    if challenge.decision is BotChallengeDecision.CONFIRMED:
        raise WebSearchProviderResponseError(
            reason="challenge_response",
            message="DuckDuckGo returned a challenge response.",
        )
    if _duckduckgo_has_login_or_anomaly_shape(soup):
        raise WebSearchProviderResponseError(
            reason="challenge_or_login_shape",
            message="DuckDuckGo returned a challenge or login shape.",
        )

    containers = soup.select("div.result")
    if not containers:
        no_result_markers = soup.select(".no-results")
        if len(no_result_markers) == 1:
            marker_text = normalize_whitespace(no_result_markers[0].get_text(" ", strip=True))
            if marker_text in _DUCKDUCKGO_NO_RESULTS_TEXT:
                return []
        raise WebSearchProviderResponseError(
            reason="response_shape_changed",
            message="DuckDuckGo response did not match a known result or no-results shape.",
        )

    results: list[SearchResultRow] = []
    malformed_count = 0
    for node in containers:
        anchor = node.select_one("a.result__a")
        if anchor is None:
            malformed_count += 1
            continue
        snippet_node = node.select_one("a.result__snippet") or node.select_one("div.result__snippet")
        title = normalize_whitespace(anchor.get_text(" ", strip=True))
        raw_href = anchor.get("href")
        if not title or not isinstance(raw_href, str) or not raw_href.strip():
            malformed_count += 1
            continue
        url = _resolve_duckduckgo_result_url(raw_href)
        parsed_url = urlparse(url)
        if parsed_url.scheme.lower() not in {"http", "https"} or not parsed_url.hostname:
            malformed_count += 1
            continue
        snippet = normalize_whitespace(snippet_node.get_text(" ", strip=True) if snippet_node else "")
        results.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "published_date": "",
            }
        )
    container_count = len(containers)
    if not results or malformed_count * 2 > container_count:
        raise WebSearchProviderResponseError(
            reason="response_shape_changed",
            message=("DuckDuckGo result containers exceeded the malformed response threshold."),
        )
    return results[:max_results]


def _duckduckgo_has_login_or_anomaly_shape(soup: BeautifulSoup) -> bool:
    """识别覆盖 result/no-results 的 challenge、anomaly 或 login shape。

    Args:
        soup: 已解析的 DuckDuckGo DOM。

    Returns:
        命中封闭 anomaly/challenge/password/login selector 时返回 ``True``。

    Raises:
        无。
    """

    if any(soup.select_one(selector) is not None for selector in _DUCKDUCKGO_CHALLENGE_SELECTORS):
        return True
    if soup.select_one("input[type='password']") is not None:
        return True
    for form in soup.select("form[action]"):
        action = form.get("action")
        if not isinstance(action, str):
            continue
        normalized_action = action.strip().lower()
        if any(token in normalized_action for token in _DUCKDUCKGO_LOGIN_ACTION_TOKENS):
            return True
    return False


def _resolve_duckduckgo_result_url(raw_url: str) -> str:
    """解析 DuckDuckGo 搜索结果链接为可访问目标 URL。

    Args:
        raw_url: 结果项中的原始 href。

    Returns:
        解析后的目标 URL；无法解析时返回原值或空字符串。

    Raises:
        无。
    """

    candidate = str(raw_url or "").strip()
    if not candidate:
        return ""

    if candidate.startswith("//"):
        candidate = f"https:{candidate}"

    if candidate.startswith("/"):
        parsed_relative = urlparse(candidate)
        if parsed_relative.path.startswith("/l"):
            uddg_values = parse_qs(parsed_relative.query).get("uddg", [])
            if uddg_values:
                return unquote(uddg_values[0]).strip()
        return ""

    parsed = urlparse(candidate)
    if parsed.hostname and parsed.hostname.lower().endswith("duckduckgo.com") and parsed.path.startswith("/l"):
        uddg_values = parse_qs(parsed.query).get("uddg", [])
        if uddg_values:
            return unquote(uddg_values[0]).strip()
    return candidate


def _build_search_web_preferred_result(
    results: list[SearchResultRow],
) -> SearchResultRow | None:
    """提取 `search_web` 的首个可见结果。

    Args:
        results: 已完成安全过滤与数量裁剪的结果列表。

    Returns:
        首条结果存在时返回其浅拷贝；否则返回 `None`。

    Raises:
        无。
    """

    if not results:
        return None
    first_result = results[0]
    return {
        "title": first_result["title"],
        "url": first_result["url"],
        "snippet": first_result["snippet"],
        "published_date": first_result["published_date"],
    }
