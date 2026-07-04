"""Web tools provider 迁移测试。"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import ParamSpec, TypeVar, cast

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_outcome import (
    TOOL_CANCELLED_REASON_HOST_CANCELLED,
    ToolCancelledOutcome,
    ToolCompletedOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_schema import ToolTruncateSpec, ToolTruncationStrategy
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscovery,
    ToolsDiscoveryProviderBinding,
    ToolsDiscoveryProviderSpec,
)
from dayu.tools.web import discover_tools
from dayu.tools.web import web_playwright_backend
from dayu.tools.web import web_search_providers
from dayu.tools.web import web_tools

_WEB_TOOL_NAMES = ("search_web", "fetch_web_page")
_WEB_PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "dayu" / "tools" / "web"
_CANCEL_REQUESTED_AT = datetime(2026, 6, 8)
_FORBIDDEN_CANCEL_MESSAGE_PARTS = (
    "run_id",
    "session_id",
    "payload_ref",
    "digest",
    "correlation_id",
    "cancellation_token",
)
_P = ParamSpec("_P")
_R = TypeVar("_R")
_FORBIDDEN_IMPORTS = (
    "dayu.engine.tool_registry",
    "dayu.engine.truncation_manager",
    "dayu.engine.tools.fetch_more",
    "dayu.web",
    "dayu.tools." + "_legacy" + "_adapter",
)


class _OpenCancellationToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终返回 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        """

        return None


class _ManualCancellationToken:
    """测试用可手动切换取消状态的 token。"""

    def __init__(self) -> None:
        """初始化为未取消状态。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._is_cancelled = False
        self._reason: str | None = None
        self._requested_at: datetime | None = None

    def cancel(self, reason: str) -> None:
        """请求取消。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._is_cancelled = True
        self._reason = reason
        self._requested_at = _CANCEL_REQUESTED_AT

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 已调用 ``cancel`` 后返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self._is_cancelled

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 已取消时返回原因。
        :raises Exception: 不主动抛出异常。
        """

        return self._reason

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 已取消时返回固定时间戳。
        :raises Exception: 不主动抛出异常。
        """

        return self._requested_at


def test_web_provider_discovers_search_and_fetch() -> None:
    """ToolsDiscovery 应发现两个 Web tools。"""

    spec = _spec({})
    result = ToolsDiscovery().discover_from_bindings(
        (ToolsDiscoveryProviderBinding(spec=spec, provider=discover_tools),)
    )

    assert tuple(definition.name for definition in result.tool_bundle.definitions) == _WEB_TOOL_NAMES
    assert result.provider_reports[0].tool_names == _WEB_TOOL_NAMES


def test_web_audit_matrix_context_injection_and_schema_no_leak() -> None:
    """Web 工具 schema 不得暴露 Host 治理字段。"""

    definitions = _definitions_by_name(_discover_definitions({}))

    for tool_name in _WEB_TOOL_NAMES:
        definition = definitions[tool_name]
        properties = definition.schema.function.parameters.properties
        required = definition.schema.function.parameters.required
        assert "run_id" not in properties
        assert "session_id" not in properties
        assert "execution_context" not in properties
        assert "cancellation_token" not in properties
        assert "correlation_id" not in properties
        assert "run_id" not in required
        assert "session_id" not in required
        assert "execution_context" not in required
        assert "cancellation_token" not in required
        assert "correlation_id" not in required


def test_search_web_projects_optional_arguments_and_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_web optional 参数必须先经 adapter 校验/转换。"""

    calls: list[Mapping[str, JsonValue]] = []

    def fake_search_public_web(**kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录搜索调用参数并返回确定性结果。

        :param kwargs: search_web 传入的关键字参数。
        :returns: 确定性搜索结果。
        """

        calls.append(kwargs)
        return {
            "query": "revenue",
            "domains": ["sec.gov"],
            "total": 1,
            "preferred_result": {
                "title": "10-K",
                "url": "https://www.sec.gov/Archives/example.htm",
                "snippet": "annual report",
                "published_date": "",
            },
            "preferred_result_summary": "10-K annual report",
            "next_action": "fetch_web_page",
            "next_action_args": {"url": "https://www.sec.gov/Archives/example.htm"},
            "hint": "fetch the preferred result",
            "results": [
                {
                    "title": "10-K",
                    "url": "https://www.sec.gov/Archives/example.htm",
                    "snippet": "annual report",
                    "published_date": "",
                }
            ],
        }

    monkeypatch.setattr(web_tools, "search_public_web", fake_search_public_web)
    definition = _definitions_by_name(_discover_definitions({}))["search_web"]

    outcome = asyncio.run(
        definition.callable(
            _call(
                "search_web",
                {
                    "query": "revenue",
                    "domains": ["sec.gov"],
                    "recency_days": 7.0,
                    "max_results": 3.0,
                },
            ),
            _context(),
        )
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    value = _mapping_value(outcome.result.value)
    assert value["total"] == 1
    assert calls[0]["domains"] == ["sec.gov"]
    assert calls[0]["recency_days"] == 7
    assert calls[0]["max_results"] == 3
    assert "ok" not in value


def test_search_web_receives_provider_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_web 闭包必须接收 Web provider config。

    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: provider config 未传入搜索路径时抛出。
    """

    calls: list[Mapping[str, JsonValue]] = []

    def fake_search_public_web(**kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录 search_web 闭包参数。

        :param kwargs: search_web 传入的关键字参数。
        :returns: 确定性空搜索结果。
        """

        calls.append(kwargs)
        return {
            "query": "revenue",
            "domains": [],
            "total": 0,
            "preferred_result": None,
            "preferred_result_summary": "",
            "next_action": "refine_query",
            "next_action_args": {},
            "hint": "refine query",
            "results": [],
        }

    monkeypatch.setattr(web_tools, "search_public_web", fake_search_public_web)
    definition = _definitions_by_name(
        _discover_definitions(
            {
                "provider": "serper",
                "request_timeout_seconds": 3.5,
                "max_search_results": 4,
                "allow_private_network_url": True,
            }
        )
    )["search_web"]

    outcome = asyncio.run(
        definition.callable(_call("search_web", {"query": "revenue"}), _context())
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    assert calls[0]["provider"] == "serper"
    assert calls[0]["request_timeout_seconds"] == 3.5
    assert calls[0]["max_search_results"] == 4
    assert calls[0]["allow_private_network_url"] is True


def test_search_web_receives_execution_context_and_passes_cancellation_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_web 必须接收 execution context 并向 provider 传递同一个 token。"""

    token = _ManualCancellationToken()
    received_tokens: list[CancellationToken | None] = []

    def fake_search_public_web(
        *,
        query: str,
        domains: list[str] | None,
        recency_days: int | None,
        max_results: int,
        max_search_results: int,
        provider: str,
        request_timeout_seconds: float,
        timeout_budget: float | None,
        deadline_monotonic: float | None,
        allow_private_network_url: bool,
        is_safe_public_url: web_search_providers._PublicUrlSafetyChecker,
        normalize_whitespace: Callable[[str], str],
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver,
        cancellation_token: CancellationToken | None = None,
    ) -> web_search_providers.SearchWebOutput:
        """记录 token identity 并返回确定性搜索结果。

        :param query: 检索关键词。
        :param domains: 可选域名限制。
        :param recency_days: 可选最近天数。
        :param max_results: 请求结果数量。
        :param max_search_results: 注册配置中的结果上限。
        :param provider: provider 策略。
        :param request_timeout_seconds: 单次 provider 请求超时。
        :param timeout_budget: 当前工具调用预算。
        :param deadline_monotonic: 当前工具调用 deadline。
        :param allow_private_network_url: 是否允许私网结果。
        :param is_safe_public_url: URL 安全校验函数。
        :param normalize_whitespace: 空白规整函数。
        :param resolve_timeout_budget: timeout 预算解析函数。
        :param cancellation_token: execution context 注入的取消令牌。
        :returns: 确定性搜索结果。
        :raises Exception: 不主动抛出异常。
        """

        del (
            domains,
            recency_days,
            max_search_results,
            provider,
            request_timeout_seconds,
            timeout_budget,
            deadline_monotonic,
            allow_private_network_url,
            is_safe_public_url,
            normalize_whitespace,
            resolve_timeout_budget,
        )
        received_tokens.append(cancellation_token)
        return {
            "query": query,
            "domains": [],
            "total": 0,
            "preferred_result": None,
            "preferred_result_summary": "",
            "next_action": "refine_query",
            "next_action_args": {},
            "hint": f"returned {max_results} or fewer results",
            "results": [],
        }

    monkeypatch.setattr(web_tools, "search_public_web", fake_search_public_web)
    definition = _definitions_by_name(_discover_definitions({}))["search_web"]

    outcome = asyncio.run(
        definition.callable(
            _call("search_web", {"query": "revenue"}),
            _context(cancellation_token=token),
        )
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    assert received_tokens == [token]


def test_search_web_cancelled_before_provider_returns_host_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_web pre-cancel 必须返回 cancelled outcome 且不调用 provider。"""

    token = _ManualCancellationToken()
    token.cancel("run_id=run-web session_id=session-web payload_ref=payload-web")
    search_calls: list[str] = []

    def fake_search_public_web(
        *,
        query: str,
        domains: list[str] | None,
        recency_days: int | None,
        max_results: int,
        max_search_results: int,
        provider: str,
        request_timeout_seconds: float,
        timeout_budget: float | None,
        deadline_monotonic: float | None,
        allow_private_network_url: bool,
        is_safe_public_url: web_search_providers._PublicUrlSafetyChecker,
        normalize_whitespace: Callable[[str], str],
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver,
        cancellation_token: CancellationToken | None = None,
    ) -> web_search_providers.SearchWebOutput:
        """记录非预期 provider 调用。

        :param query: 检索关键词。
        :param domains: 可选域名限制。
        :param recency_days: 可选最近天数。
        :param max_results: 请求结果数量。
        :param max_search_results: 注册配置中的结果上限。
        :param provider: provider 策略。
        :param request_timeout_seconds: 单次 provider 请求超时。
        :param timeout_budget: 当前工具调用预算。
        :param deadline_monotonic: 当前工具调用 deadline。
        :param allow_private_network_url: 是否允许私网结果。
        :param is_safe_public_url: URL 安全校验函数。
        :param normalize_whitespace: 空白规整函数。
        :param resolve_timeout_budget: timeout 预算解析函数。
        :param cancellation_token: execution context 注入的取消令牌。
        :returns: 空搜索结果。
        :raises Exception: 不主动抛出异常。
        """

        del (
            domains,
            recency_days,
            max_results,
            max_search_results,
            provider,
            request_timeout_seconds,
            timeout_budget,
            deadline_monotonic,
            allow_private_network_url,
            is_safe_public_url,
            normalize_whitespace,
            resolve_timeout_budget,
            cancellation_token,
        )
        search_calls.append(query)
        return {
            "query": query,
            "domains": [],
            "total": 0,
            "preferred_result": None,
            "preferred_result_summary": "",
            "next_action": "refine_query",
            "next_action_args": {},
            "hint": "unexpected provider call",
            "results": [],
        }

    monkeypatch.setattr(web_tools, "search_public_web", fake_search_public_web)
    definition = _definitions_by_name(_discover_definitions({}))["search_web"]

    outcome = asyncio.run(
        definition.callable(
            _call("search_web", {"query": "revenue"}),
            _context(cancellation_token=token),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    assert outcome.meta is not None
    assert outcome.meta.tool_name == "search_web"
    _assert_no_governance_text(f"{outcome.message} {outcome.hint or ''}")
    assert outcome.hint is not None
    assert "continue_without_web" in outcome.hint
    assert search_calls == []


def test_search_web_deep_cancel_message_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search provider 深层取消不得把 token reason 投影给 LLM。"""

    def fake_search_public_web(
        *,
        query: str,
        domains: list[str] | None,
        recency_days: int | None,
        max_results: int,
        max_search_results: int,
        provider: str,
        request_timeout_seconds: float,
        timeout_budget: float | None,
        deadline_monotonic: float | None,
        allow_private_network_url: bool,
        is_safe_public_url: web_search_providers._PublicUrlSafetyChecker,
        normalize_whitespace: Callable[[str], str],
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver,
        cancellation_token: CancellationToken | None = None,
    ) -> web_search_providers.SearchWebOutput:
        """模拟搜索 provider 在深层 checkpoint 抛出携带治理字段的取消。

        :param query: 检索关键词。
        :param domains: 可选域名限制。
        :param recency_days: 可选最近天数。
        :param max_results: 请求结果数量。
        :param max_search_results: 注册配置中的结果上限。
        :param provider: provider 策略。
        :param request_timeout_seconds: 单次 provider 请求超时。
        :param timeout_budget: 当前工具调用预算。
        :param deadline_monotonic: 当前工具调用 deadline。
        :param allow_private_network_url: 是否允许私网结果。
        :param is_safe_public_url: URL 安全校验函数。
        :param normalize_whitespace: 空白规整函数。
        :param resolve_timeout_budget: timeout 预算解析函数。
        :param cancellation_token: execution context 注入的取消令牌。
        :returns: 不返回。
        :raises web_search_providers.WebSearchCancelledError: 始终抛出测试取消。
        """

        del (
            query,
            domains,
            recency_days,
            max_results,
            max_search_results,
            provider,
            request_timeout_seconds,
            timeout_budget,
            deadline_monotonic,
            allow_private_network_url,
            is_safe_public_url,
            normalize_whitespace,
            resolve_timeout_budget,
            cancellation_token,
        )
        raise web_search_providers.WebSearchCancelledError(
            message="run_id=run-web correlation_id=correlation-web digest=sha256:web",
            hint="[continue_without_web] Host cancelled.",
        )

    monkeypatch.setattr(web_tools, "search_public_web", fake_search_public_web)
    definition = _definitions_by_name(_discover_definitions({}))["search_web"]

    outcome = asyncio.run(
        definition.callable(
            _call("search_web", {"query": "revenue"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    _assert_no_governance_text(f"{outcome.message} {outcome.hint or ''}")


def test_search_web_cancelled_between_provider_attempts_stops_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """provider attempt 间取消后必须停止后续 fallback。"""

    token = _ManualCancellationToken()
    attempted_providers: list[str] = []

    def fake_search_with_tavily(
        *,
        query: str,
        domains: list[str],
        recency_days: int | None,
        max_results: int,
        timeout_seconds: float,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver = web_search_providers._default_resolve_timeout_budget,
    ) -> list[web_search_providers.SearchResultRow]:
        """模拟首个 provider 失败并同时触发 Host cancel。

        :param query: 检索关键词。
        :param domains: 域名限制。
        :param recency_days: 最近天数。
        :param max_results: 返回数量。
        :param timeout_seconds: HTTP 请求超时。
        :param timeout_budget: 当前工具预算。
        :param deadline_monotonic: 当前工具 deadline。
        :param resolve_timeout_budget: timeout 预算解析函数。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出 provider 失败。
        """

        del (
            query,
            domains,
            recency_days,
            max_results,
            timeout_seconds,
            timeout_budget,
            deadline_monotonic,
            resolve_timeout_budget,
        )
        attempted_providers.append("tavily")
        token.cancel("cancel after first provider")
        raise RuntimeError("tavily unavailable")

    def fake_search_with_duckduckgo(
        *,
        query: str,
        domains: list[str],
        max_results: int,
        timeout_seconds: float,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        normalize_whitespace: Callable[[str], str] = lambda value: " ".join(value.split()),
        resolve_timeout_budget: web_search_providers._TimeoutBudgetResolver = web_search_providers._default_resolve_timeout_budget,
    ) -> list[web_search_providers.SearchResultRow]:
        """记录非预期 DuckDuckGo fallback。

        :param query: 检索关键词。
        :param domains: 域名限制。
        :param max_results: 返回数量。
        :param timeout_seconds: HTTP 请求超时。
        :param timeout_budget: 当前工具预算。
        :param deadline_monotonic: 当前工具 deadline。
        :param normalize_whitespace: 空白规整函数。
        :param resolve_timeout_budget: timeout 预算解析函数。
        :returns: 空结果。
        :raises Exception: 不主动抛出异常。
        """

        del (
            query,
            domains,
            max_results,
            timeout_seconds,
            timeout_budget,
            deadline_monotonic,
            normalize_whitespace,
            resolve_timeout_budget,
        )
        attempted_providers.append("duckduckgo")
        return []

    monkeypatch.setattr(web_search_providers, "_search_with_tavily", fake_search_with_tavily)
    monkeypatch.setattr(
        web_search_providers,
        "_search_with_duckduckgo",
        fake_search_with_duckduckgo,
    )
    definition = _definitions_by_name(_discover_definitions({"provider": "tavily"}))["search_web"]

    outcome = asyncio.run(
        definition.callable(
            _call("search_web", {"query": "revenue"}),
            _context(cancellation_token=token),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    assert outcome.meta is not None
    assert outcome.meta.tool_name == "search_web"
    assert attempted_providers == ["tavily"]


def test_fetch_web_page_cancelled_before_work_returns_safe_host_cancelled() -> None:
    """fetch_web_page pre-cancel 必须返回安全 cancelled outcome。"""

    token = _ManualCancellationToken()
    token.cancel("run_id=run-web session_id=session-web cancellation_token=token-web")
    definition = _definitions_by_name(_discover_definitions({}))["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "http://example.com/report"}),
            _context(cancellation_token=token),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    assert outcome.meta is not None
    assert outcome.meta.tool_name == "fetch_web_page"
    _assert_no_governance_text(f"{outcome.message} {outcome.hint or ''}")


def test_fetch_web_page_deep_runtime_cancel_message_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fetch 深层 RuntimeError 取消不得把 token reason 投影给 LLM。"""

    token = _ManualCancellationToken()

    def fake_warmup_domain(*args: JsonValue, **kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """模拟深层联网阶段观察到取消并抛出携带治理字段的 RuntimeError。

        :param args: 位置参数。
        :param kwargs: 关键字参数。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出测试取消。
        """

        del args, kwargs
        token.cancel("run_id=run-web payload_ref=payload-web digest=sha256:web")
        raise RuntimeError("run_id=run-web payload_ref=payload-web digest=sha256:web")

    monkeypatch.setattr(web_tools, "_warmup_domain", fake_warmup_domain)
    definition = _definitions_by_name(_discover_definitions({}))["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "http://example.com/report"}),
            _context(cancellation_token=token),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    _assert_no_governance_text(f"{outcome.message} {outcome.hint or ''}")


def test_fetch_private_url_fails_closed_by_default() -> None:
    """默认配置必须拒绝 private/local URL。"""

    definition = _definitions_by_name(_discover_definitions({}))["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "http://127.0.0.1/internal"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "permission_denied"


def test_fetch_private_url_can_be_allowed_with_explicit_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """显式允许 private URL 后，抓取路径才可继续执行。"""

    monkeypatch.setattr(web_tools, "_warmup_domain", lambda *args, **kwargs: {"attempted": True, "ok": True})
    monkeypatch.setattr(web_tools, "_probe_content_type", lambda *args, **kwargs: {"attempted": True, "ok": True})
    monkeypatch.setattr(web_tools, "_try_playwright_fallback", lambda *args, **kwargs: None)

    def fake_fetch_and_convert_content(url: str, **kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """返回确定性网页内容。

        :param url: 已标准化 URL。
        :param kwargs: 抓取辅助参数。
        :returns: 确定性抓取结果。
        """

        return {
            "final_url": url,
            "title": "Internal",
            "content": "local test content",
            "http_status": 200,
            "redirect_hops": 0,
            "response_headers": {},
            "response_excerpt": "local test content",
            "extraction_source": "mock",
            "renderer_source": "mock",
            "normalization_applied": False,
            "quality_flags": [],
            "content_stats": {},
        }

    monkeypatch.setattr(web_tools, "_fetch_and_convert_content", fake_fetch_and_convert_content)
    definition = _definitions_by_name(
        _discover_definitions({"allow_private_network_url": True})
    )["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "http://127.0.0.1/internal"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    value = _mapping_value(outcome.result.value)
    assert value["fetch_backend"] == "requests"
    assert value["content"] == "local test content"
    assert "ok" not in value


def test_fetch_playwright_cancel_projects_to_host_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Playwright fallback 取消必须投影为 cancelled outcome。"""

    monkeypatch.setattr(web_tools, "_warmup_domain", lambda *args, **kwargs: {"attempted": True, "ok": False})
    monkeypatch.setattr(web_tools, "_should_escalate_stage_result_to_browser", lambda stage_result: True)
    token = _ManualCancellationToken()
    received_playwright_tokens: list[CancellationToken | None] = []

    def fake_fetch_and_convert_with_playwright(
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, JsonValue]:
        """模拟 Playwright worker 在 fallback 内部收到取消。

        :param url: 目标 URL。
        :param timeout_seconds: 浏览器抓取超时。
        :param headers: 请求头。
        :param timeout_budget: 工具总预算。
        :param deadline_monotonic: 工具调用 deadline。
        :param playwright_channel: 浏览器 channel。
        :param playwright_storage_state_path: storage state 路径。
        :param cancellation_token: 取消令牌。
        :returns: 不返回。
        :raises web_playwright_backend.CancelledError: 始终抛出。
        """

        received_playwright_tokens.append(cancellation_token)
        del (
            url,
            timeout_seconds,
            headers,
            timeout_budget,
            deadline_monotonic,
            playwright_channel,
            playwright_storage_state_path,
        )
        raise web_playwright_backend.CancelledError("cancelled by host")

    monkeypatch.setattr(
        web_tools,
        "_fetch_and_convert_with_playwright",
        fake_fetch_and_convert_with_playwright,
    )
    definition = _definitions_by_name(
        _discover_definitions({"allow_private_network_url": True})
    )["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "http://127.0.0.1/internal"}),
            _context(cancellation_token=token),
        )
    )

    assert isinstance(outcome, ToolCancelledOutcome)
    assert outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED
    assert outcome.meta is not None
    assert outcome.meta.tool_name == "fetch_web_page"
    assert outcome.hint is not None
    assert "continue_without_web" in outcome.hint
    assert received_playwright_tokens == [token]


def test_search_and_fetch_pass_tool_timeout_budget_to_business(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search/fetch 主路径必须把工具剩余预算传入 HTTP 预算边界。"""

    budgets: list[float | None] = []

    async def fake_to_thread(
        func: Callable[_P, _R],
        /,
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> _R:
        """同步执行业务函数，保留 ``asyncio.to_thread`` 调用形状。"""

        return func(*args, **kwargs)

    def fake_search_business(**kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录 search_web 传入的 timeout budget。"""

        budgets.append(cast(float | None, kwargs.get("timeout_budget")))
        return {
            "query": "revenue",
            "domains": [],
            "total": 0,
            "preferred_result": None,
            "preferred_result_summary": "",
            "next_action": "refine_query",
            "next_action_args": {},
            "hint": "refine query",
            "results": [],
        }

    def fake_fetch_business(**kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录 fetch_web_page 传入的 timeout budget。"""

        budgets.append(cast(float | None, kwargs.get("timeout_budget")))
        return {
            "url": kwargs["url"],
            "final_url": kwargs["url"],
            "title": "Example",
            "content": "budgeted content",
            "fetch_backend": "requests",
        }

    monkeypatch.setattr(web_tools.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(web_tools, "_search_web_business", fake_search_business)
    monkeypatch.setattr(web_tools, "_fetch_web_page_business", fake_fetch_business)
    definitions = _definitions_by_name(
        _discover_definitions({"allow_private_network_url": True})
    )
    context = _context(timeout_seconds=2.5)

    search_outcome = asyncio.run(
        definitions["search_web"].callable(
            _call("search_web", {"query": "revenue"}),
            context,
        )
    )
    fetch_outcome = asyncio.run(
        definitions["fetch_web_page"].callable(
            _call("fetch_web_page", {"url": "http://127.0.0.1/internal"}),
            context,
        )
    )

    assert isinstance(search_outcome, ToolCompletedOutcome)
    assert isinstance(fetch_outcome, ToolCompletedOutcome)
    assert budgets == [2.5, 2.5]


def test_try_playwright_fallback_pre_cancel_does_not_start_playwright(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fallback 入口已取消时不得启动 Playwright worker。"""

    token = _ManualCancellationToken()
    token.cancel("payload_ref=payload-web digest=sha256:web correlation_id=correlation-web")
    playwright_calls: list[str] = []

    def fake_fetch_and_convert_with_playwright(
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, JsonValue]:
        """记录非预期 Playwright worker 调用。

        :param url: 目标 URL。
        :param timeout_seconds: 浏览器抓取超时。
        :param headers: 请求头。
        :param timeout_budget: 工具总预算。
        :param deadline_monotonic: 工具调用 deadline。
        :param playwright_channel: 浏览器 channel。
        :param playwright_storage_state_path: storage state 路径。
        :param cancellation_token: 取消令牌。
        :returns: 成功结果。
        :raises Exception: 不主动抛出异常。
        """

        del (
            timeout_seconds,
            headers,
            timeout_budget,
            deadline_monotonic,
            playwright_channel,
            playwright_storage_state_path,
            cancellation_token,
        )
        playwright_calls.append(url)
        return {"ok": True, "content": "unexpected", "title": "unexpected"}

    monkeypatch.setattr(
        web_tools,
        "_fetch_and_convert_with_playwright",
        fake_fetch_and_convert_with_playwright,
    )

    with pytest.raises(web_tools.WebToolCancelledError) as captured:
        web_tools._try_playwright_fallback(
            url="http://example.com/report",
            timeout_seconds=1.0,
            headers={},
            timeout_budget=None,
            deadline_monotonic=None,
            cancellation_token=token,
        )

    assert playwright_calls == []
    _assert_no_governance_text(f"{captured.value.message} {captured.value.hint}")


def test_playwright_unpicklable_worker_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不可序列化 Playwright worker 不得回落到同进程执行。"""

    monkeypatch.setattr(
        web_playwright_backend,
        "_is_picklable_worker",
        lambda worker: False,
    )
    worker_calls: list[str] = []

    def fake_worker(
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
    ) -> dict[str, JsonValue]:
        """记录不应发生的同进程 Playwright 调用。"""

        del timeout_seconds, headers, playwright_channel, playwright_storage_state_path
        worker_calls.append(url)
        return {"ok": True, "content": "unexpected"}

    result = web_playwright_backend._fetch_and_convert_with_playwright(
        url="https://example.com/report",
        timeout_seconds=1.0,
        headers={},
        timeout_budget=1.0,
        deadline_monotonic=None,
        playwright_channel=None,
        playwright_storage_state_path="",
        cancellation_token=_OpenCancellationToken(),
        resolve_timeout_budget=lambda timeout_seconds, **kwargs: timeout_seconds,
        playwright_sync_worker=fake_worker,
        detect_bot_challenge=lambda **kwargs: web_tools.BotChallengeDetectionResult(
            challenge_detected=False,
            challenge_signals=(),
        ),
    )

    assert result["ok"] is False
    assert result["reason"] == "playwright_worker_not_picklable"
    assert worker_calls == []


def test_fetch_playwright_fallback_receives_channel_and_storage_state_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Playwright fallback 必须收到 config 派生的 channel 与 storage state。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: browser fallback 参数未由 Web config 派生时抛出。
    """

    storage_dir = tmp_path / "states"
    storage_file = storage_dir / "example.com.json"
    storage_file.parent.mkdir(parents=True)
    storage_file.write_text("{}", encoding="utf-8")
    calls: list[Mapping[str, JsonValue]] = []
    monkeypatch.setattr(web_tools, "_warmup_domain", lambda *args, **kwargs: {"attempted": True, "ok": False})
    monkeypatch.setattr(web_tools, "_should_escalate_stage_result_to_browser", lambda stage_result: True)

    def fake_fetch_and_convert_with_playwright(
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        cancellation_token: CancellationToken | None = None,
    ) -> Mapping[str, JsonValue]:
        """记录 browser fallback 参数并返回确定性内容。

        :param url: 目标 URL。
        :param timeout_seconds: 抓取超时。
        :param headers: 请求 headers。
        :param timeout_budget: 工具预算。
        :param deadline_monotonic: 工具 deadline。
        :param playwright_channel: 浏览器 channel。
        :param playwright_storage_state_path: storage state 文件路径。
        :param cancellation_token: 取消令牌。
        :returns: 确定性抓取内容。
        """

        del headers, timeout_budget, deadline_monotonic, cancellation_token
        calls.append(
            {
                "url": url,
                "timeout_seconds": timeout_seconds,
                "playwright_channel": playwright_channel,
                "playwright_storage_state_path": playwright_storage_state_path,
            }
        )
        return {
            "ok": True,
            "final_url": url,
            "title": "Example",
            "content": "browser rendered content",
            "http_status": 200,
            "redirect_hops": 0,
            "response_headers": {},
            "response_excerpt": "browser rendered content",
            "extraction_source": "playwright",
            "renderer_source": "playwright",
            "normalization_applied": False,
            "quality_flags": [],
            "content_stats": {},
        }

    monkeypatch.setattr(
        web_tools,
        "_fetch_and_convert_with_playwright",
        fake_fetch_and_convert_with_playwright,
    )
    definition = _definitions_by_name(
        _discover_definitions(
            {
                "allow_private_network_url": True,
                "playwright_channel": "msedge",
                "playwright_storage_state_dir": str(storage_dir),
            }
        )
    )["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "https://example.com/page"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    assert calls[0]["playwright_channel"] == "msedge"
    assert calls[0]["playwright_storage_state_path"] == str(storage_file.resolve())


def test_fetch_playwright_fallback_uses_empty_storage_state_when_dir_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空 storage state dir 配置必须保持 fallback storage state 为空。

    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: 空目录配置被误解析成 storage state path 时抛出。
    """

    calls: list[Mapping[str, JsonValue]] = []
    monkeypatch.setattr(web_tools, "_warmup_domain", lambda *args, **kwargs: {"attempted": True, "ok": False})
    monkeypatch.setattr(web_tools, "_should_escalate_stage_result_to_browser", lambda stage_result: True)

    def fake_fetch_and_convert_with_playwright(
        *,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
        timeout_budget: float | None = None,
        deadline_monotonic: float | None = None,
        playwright_channel: str | None = None,
        playwright_storage_state_path: str = "",
        cancellation_token: CancellationToken | None = None,
    ) -> Mapping[str, JsonValue]:
        """记录空 storage state dir 的 browser fallback 参数。

        :param url: 目标 URL。
        :param timeout_seconds: 抓取超时。
        :param headers: 请求 headers。
        :param timeout_budget: 工具预算。
        :param deadline_monotonic: 工具 deadline。
        :param playwright_channel: 浏览器 channel。
        :param playwright_storage_state_path: storage state 文件路径。
        :param cancellation_token: 取消令牌。
        :returns: 确定性抓取内容。
        """

        del headers, timeout_budget, deadline_monotonic, cancellation_token
        calls.append(
            {
                "url": url,
                "timeout_seconds": timeout_seconds,
                "playwright_channel": playwright_channel,
                "playwright_storage_state_path": playwright_storage_state_path,
            }
        )
        return {
            "ok": True,
            "final_url": url,
            "title": "Example",
            "content": "browser rendered content",
            "http_status": 200,
            "redirect_hops": 0,
            "response_headers": {},
            "response_excerpt": "browser rendered content",
            "extraction_source": "playwright",
            "renderer_source": "playwright",
            "normalization_applied": False,
            "quality_flags": [],
            "content_stats": {},
        }

    monkeypatch.setattr(
        web_tools,
        "_fetch_and_convert_with_playwright",
        fake_fetch_and_convert_with_playwright,
    )
    definition = _definitions_by_name(
        _discover_definitions(
            {
                "allow_private_network_url": True,
                "playwright_channel": "chrome",
                "playwright_storage_state_dir": "",
            }
        )
    )["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": "https://example.com/page"}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolCompletedOutcome)
    assert calls[0]["playwright_channel"] == "chrome"
    assert calls[0]["playwright_storage_state_path"] == ""


def test_invalid_fetch_url_type_fails_before_web_logic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """不可转换的 url JSON 类型必须先由 adapter 拒绝。"""

    calls: list[str] = []

    def fake_fetch_and_convert_content(url: str, **kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录是否进入抓取路径。

        :param url: URL。
        :param kwargs: 抓取辅助参数。
        :returns: 空抓取结果。
        """

        calls.append(url)
        return {}

    monkeypatch.setattr(web_tools, "_fetch_and_convert_content", fake_fetch_and_convert_content)
    definition = _definitions_by_name(_discover_definitions({}))["fetch_web_page"]

    outcome = asyncio.run(
        definition.callable(
            _call("fetch_web_page", {"url": ["https://example.com"]}),
            _context(),
        )
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "invalid_argument"
    assert calls == []


def test_search_provider_unavailable_projects_to_stable_business_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """搜索 provider 全部耗尽必须投影为稳定业务失败。"""

    attempted_providers: list[str] = []

    def fake_search_with_tavily(**kwargs: JsonValue) -> list[web_search_providers.SearchResultRow]:
        """模拟 Tavily provider 不可用。

        :param kwargs: provider 传入的关键字参数。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出 provider 失败。
        """

        del kwargs
        attempted_providers.append("tavily")
        raise RuntimeError("tavily unavailable")

    def fake_search_with_serper(**kwargs: JsonValue) -> list[web_search_providers.SearchResultRow]:
        """模拟 Serper provider 不可用。

        :param kwargs: provider 传入的关键字参数。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出 provider 失败。
        """

        del kwargs
        attempted_providers.append("serper")
        raise RuntimeError("serper unavailable")

    def fake_search_with_duckduckgo(**kwargs: JsonValue) -> list[web_search_providers.SearchResultRow]:
        """模拟 DuckDuckGo provider 不可用。

        :param kwargs: provider 传入的关键字参数。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出 provider 失败。
        """

        del kwargs
        attempted_providers.append("duckduckgo")
        raise RuntimeError("duckduckgo unavailable")

    monkeypatch.setattr(web_search_providers, "_search_with_tavily", fake_search_with_tavily)
    monkeypatch.setattr(web_search_providers, "_search_with_serper", fake_search_with_serper)
    monkeypatch.setattr(web_search_providers, "_search_with_duckduckgo", fake_search_with_duckduckgo)
    monkeypatch.setenv(web_search_providers.TAVILY_API_KEY_ENV, "test-tavily-key")
    monkeypatch.setenv(web_search_providers.SERPER_API_KEY_ENV, "test-serper-key")
    definition = _definitions_by_name(_discover_definitions({}))["search_web"]

    outcome = asyncio.run(
        definition.callable(_call("search_web", {"query": "revenue"}), _context())
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "search_provider_unavailable"
    assert "provider" in outcome.result.message
    assert outcome.result.hint is not None
    assert outcome.result.hint.strip() != ""
    assert attempted_providers == ["tavily", "serper", "duckduckgo"]


def test_web_truncate_specs_use_current_contract() -> None:
    """Web tools 必须声明 current ToolTruncateSpec。"""

    definitions = _definitions_by_name(_discover_definitions({"fetch_truncate_chars": 1234}))

    search_truncate = definitions["search_web"].truncate
    fetch_truncate = definitions["fetch_web_page"].truncate

    assert isinstance(search_truncate, ToolTruncateSpec)
    assert search_truncate.strategy is ToolTruncationStrategy.LIST_ITEMS
    assert search_truncate.target_field == "results"
    assert isinstance(fetch_truncate, ToolTruncateSpec)
    assert fetch_truncate.strategy is ToolTruncationStrategy.TEXT_CHARS
    assert fetch_truncate.limits == {"max_chars": 1234}
    assert fetch_truncate.target_field == "content"


def test_web_provider_serializes_search_and_fetch_business(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一 Web provider 内 search/fetch 不得并发进入业务体。"""

    to_thread_entries: list[str] = []
    business_entries: list[str] = []
    active_business = False
    observed_overlap = False

    def fake_search_public_web(**kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录搜索业务体进入并返回确定性结果。

        :param kwargs: search_web 传入的关键字参数。
        :returns: 确定性搜索结果。
        :raises Exception: 不主动抛出异常。
        """

        del kwargs
        business_entries.append("search")
        return {
            "query": "revenue",
            "domains": [],
            "total": 0,
            "preferred_result": None,
            "preferred_result_summary": "",
            "next_action": "refine_query",
            "next_action_args": {},
            "hint": "refine query",
            "results": [],
        }

    def fake_fetch_and_convert_content(url: str, **kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """记录 fetch 业务体进入并返回确定性页面。

        :param url: URL。
        :param kwargs: 抓取辅助参数。
        :returns: 确定性抓取结果。
        """

        del kwargs
        business_entries.append("fetch")
        return {
            "final_url": url,
            "title": "Example",
            "content": "serialized fetch content",
            "http_status": 200,
            "redirect_hops": 0,
            "response_headers": {},
            "response_excerpt": "serialized fetch content",
            "extraction_source": "mock",
            "renderer_source": "mock",
            "normalization_applied": False,
            "quality_flags": [],
            "content_stats": {},
        }

    monkeypatch.setattr(web_tools, "search_public_web", fake_search_public_web)
    monkeypatch.setattr(web_tools, "_warmup_domain", lambda *args, **kwargs: {"attempted": True, "ok": True})
    monkeypatch.setattr(web_tools, "_probe_content_type", lambda *args, **kwargs: {"attempted": True, "ok": True})
    monkeypatch.setattr(web_tools, "_try_playwright_fallback", lambda *args, **kwargs: None)
    monkeypatch.setattr(web_tools, "_fetch_and_convert_content", fake_fetch_and_convert_content)

    definitions = _definitions_by_name(
        _discover_definitions({"allow_private_network_url": True})
    )

    async def run_competing_calls() -> tuple[ToolCompletedOutcome, ToolCompletedOutcome]:
        """并发执行 search 与 fetch。

        :returns: 两个成功 outcome。
        :raises AssertionError: 搜索未进入业务体或 outcome 类型不符时抛出。
        """

        first_to_thread_entered = asyncio.Event()
        release_first_to_thread = asyncio.Event()

        async def fake_to_thread(
            func: Callable[_P, _R],
            /,
            *args: _P.args,
            **kwargs: _P.kwargs,
        ) -> _R:
            """模拟 ``asyncio.to_thread`` 并记录业务体重叠。

            :param func: 待执行的同步 callable。
            :param args: 位置参数。
            :param kwargs: 关键字参数。
            :returns: callable 返回值。
            :raises Exception: callable 执行失败时透出。
            """

            nonlocal active_business, observed_overlap
            if active_business:
                observed_overlap = True
            active_business = True
            to_thread_entries.append("enter")
            if len(to_thread_entries) == 1:
                first_to_thread_entered.set()
                await release_first_to_thread.wait()
            try:
                return func(*args, **kwargs)
            finally:
                active_business = False

        monkeypatch.setattr(web_tools.asyncio, "to_thread", fake_to_thread)
        search_task = asyncio.create_task(
            definitions["search_web"].callable(
                _call("search_web", {"query": "revenue"}),
                _context(),
            )
        )
        await first_to_thread_entered.wait()
        fetch_task = asyncio.create_task(
            definitions["fetch_web_page"].callable(
                _call("fetch_web_page", {"url": "http://127.0.0.1/internal"}),
                _context(),
            )
        )
        await asyncio.sleep(0)
        assert to_thread_entries == ["enter"]
        release_first_to_thread.set()
        search_outcome, fetch_outcome = await asyncio.gather(search_task, fetch_task)
        assert isinstance(search_outcome, ToolCompletedOutcome)
        assert isinstance(fetch_outcome, ToolCompletedOutcome)
        return search_outcome, fetch_outcome

    outcomes = asyncio.run(run_competing_calls())

    assert len(outcomes) == 2
    assert observed_overlap is False
    assert to_thread_entries == ["enter", "enter"]
    assert business_entries == ["search", "fetch"]


def test_web_modules_do_not_import_legacy_registry_truncation_fetch_more_or_ui() -> None:
    """Web 模块不得导入 legacy registry/truncation/fetch_more/UI。"""

    for source_path in _WEB_PACKAGE_ROOT.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                assert not any(
                    node.module == forbidden or node.module.startswith(f"{forbidden}.")
                    for forbidden in _FORBIDDEN_IMPORTS
                ), f"{source_path} imports {node.module}"
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not any(
                        alias.name == forbidden or alias.name.startswith(f"{forbidden}.")
                        for forbidden in _FORBIDDEN_IMPORTS
                    ), f"{source_path} imports {alias.name}"


def _discover_definitions(config: Mapping[str, JsonValue]) -> tuple[ToolDefinition, ...]:
    """发现 Web 工具定义。

    :param config: provider config。
    :returns: 工具定义元组。
    """

    return discover_tools(_spec(config)).definitions


def _definitions_by_name(
    definitions: tuple[ToolDefinition, ...],
) -> Mapping[str, ToolDefinition]:
    """按工具名索引定义。

    :param definitions: 工具定义元组。
    :returns: 工具名字典。
    """

    return {definition.name: definition for definition in definitions}


def _mapping_value(value: JsonValue) -> Mapping[str, JsonValue]:
    """把 JsonValue 收窄为 JSON object。

    :param value: 工具返回值。
    :returns: JSON object。
    :raises AssertionError: 值不是 JSON object 时抛出。
    """

    assert isinstance(value, Mapping)
    return value


def _assert_no_governance_text(text: str) -> None:
    """断言 LLM-facing 文本未泄漏 Host 治理字符串。

    :param text: 待检查的 outcome message / hint 文本。
    :returns: 无。
    :raises AssertionError: 文本包含治理字符串时抛出。
    """

    for forbidden in _FORBIDDEN_CANCEL_MESSAGE_PARTS:
        assert forbidden not in text


def _spec(config: Mapping[str, JsonValue]) -> ToolsDiscoveryProviderSpec:
    """构造 Web provider spec。

    :param config: provider config。
    :returns: provider spec。
    """

    return ToolsDiscoveryProviderSpec(
        spec_id="web-tools",
        location=PythonImportPathProvider("dayu.tools.web:discover_tools"),
        enabled=True,
        config=config,
    )


def _call(name: str, arguments: Mapping[str, JsonValue]) -> ToolCallRequest:
    """构造工具调用请求。

    :param name: 工具名。
    :param arguments: 调用参数。
    :returns: 工具调用请求。
    """

    return ToolCallRequest(
        tool_call_id=f"call-{name}",
        name=name,
        arguments=arguments,
        index_in_iteration=0,
        provider_state=None,
    )


def _context(
    cancellation_token: CancellationToken | None = None,
    timeout_seconds: float | None = 10.0,
) -> BatchToolExecutionContext:
    """构造测试工具执行上下文。

    :param cancellation_token: 可选取消令牌。
    :param timeout_seconds: 可选工具执行预算秒数。
    :returns: 批式执行上下文。
    """

    return BatchToolExecutionContext(
        run_id="run-web",
        session_id="session-web",
        iteration_id="iteration-web",
        timeout_seconds=timeout_seconds,
        cancellation_token=cancellation_token or _OpenCancellationToken(),
        correlation_id="run-web:iteration-web:tool_batch",
    )
