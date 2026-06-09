"""Web tools provider 迁移测试。"""

from __future__ import annotations

import ast
import asyncio
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import BatchToolExecutionContext, ToolCallRequest
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_outcome import ToolCompletedOutcome, ToolFailedOutcome
from dayu.contracts.tool_schema import ToolTruncateSpec, ToolTruncationStrategy
from dayu.runtime.tools_discovery import (
    PythonImportPathProvider,
    ToolsDiscovery,
    ToolsDiscoveryProviderBinding,
    ToolsDiscoveryProviderSpec,
)
from dayu.tools._legacy_adapter.registry_collector import LegacyToolDeclarationCollector
from dayu.tools.web import discover_tools
from dayu.tools.web import web_playwright_backend
from dayu.tools.web import web_search_providers
from dayu.tools.web import web_tools

_WEB_TOOL_NAMES = ("search_web", "fetch_web_page")
_WEB_PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "dayu" / "tools" / "web"
_CANCEL_REQUESTED_AT = datetime(2026, 6, 8)
_FORBIDDEN_IMPORTS = (
    "dayu.engine.tool_registry",
    "dayu.engine.truncation_manager",
    "dayu.engine.tools.fetch_more",
    "dayu.web",
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
    """Web 工具 cancellation audit matrix 必须覆盖注入声明与 schema 隔离。"""

    collector = LegacyToolDeclarationCollector()
    web_tools.register_web_tools(collector)
    declarations = collector.collected_tools()
    definitions = _definitions_by_name(_discover_definitions({}))

    assert tuple(declaration.name for declaration in declarations) == _WEB_TOOL_NAMES
    assert all(
        declaration.execution_context_param_name == "execution_context"
        for declaration in declarations
    )
    for tool_name in _WEB_TOOL_NAMES:
        definition = definitions[tool_name]
        properties = definition.schema.function.parameters.properties
        required = definition.schema.function.parameters.required
        assert "execution_context" not in properties
        assert "cancellation_token" not in properties
        assert "execution_context" not in required
        assert "cancellation_token" not in required


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


def test_search_web_cancelled_before_provider_returns_tool_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search_web pre-cancel 必须返回 tool_cancelled 且不调用 provider。"""

    token = _ManualCancellationToken()
    token.cancel("cancel before provider")
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

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "tool_cancelled"
    assert search_calls == []


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

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "tool_cancelled"
    assert attempted_providers == ["tavily"]


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


def test_fetch_playwright_cancel_projects_to_cancelled_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Playwright fallback 取消必须投影为明确的失败 outcome。"""

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
    ) -> Mapping[str, JsonValue]:
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

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "tool_cancelled"
    assert outcome.result.hint is not None
    assert "continue_without_web" in outcome.result.hint
    assert received_playwright_tokens == [token]


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


def test_search_failure_projects_to_current_failed_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """搜索业务失败必须投影为 current ToolFailedOutcome。"""

    def fake_search_public_web(**kwargs: JsonValue) -> Mapping[str, JsonValue]:
        """模拟搜索 provider 失败。

        :param kwargs: search_web 传入的关键字参数。
        :returns: 不返回。
        :raises RuntimeError: 始终抛出搜索失败。
        """

        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(web_tools, "search_public_web", fake_search_public_web)
    definition = _definitions_by_name(_discover_definitions({}))["search_web"]

    outcome = asyncio.run(
        definition.callable(_call("search_web", {"query": "revenue"}), _context())
    )

    assert isinstance(outcome, ToolFailedOutcome)
    assert outcome.result.error == "execution_error"


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


def test_web_modules_do_not_import_old_registry_truncation_fetch_more_or_ui() -> None:
    """迁移 Web 模块不得导入 OLD registry/truncation/fetch_more/UI。"""

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


def _spec(config: Mapping[str, JsonValue]) -> ToolsDiscoveryProviderSpec:
    """构造 Web provider spec。

    :param config: provider config。
    :returns: provider spec。
    """

    return ToolsDiscoveryProviderSpec(
        spec_id="web-tools",
        location=PythonImportPathProvider("dayu.tools.web:discover_tools"),
        enabled=True,
        allow_empty=False,
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
) -> BatchToolExecutionContext:
    """构造测试工具执行上下文。

    :param cancellation_token: 可选取消令牌。
    :returns: 批式执行上下文。
    """

    return BatchToolExecutionContext(
        run_id="run-web",
        session_id="session-web",
        iteration_id="iteration-web",
        timeout_seconds=10.0,
        cancellation_token=cancellation_token or _OpenCancellationToken(),
        correlation_id="run-web:iteration-web:tool_batch",
    )
