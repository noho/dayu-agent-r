"""FMP 公司信息 resolver 测试。"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from dayu.fins.resolver import (
    FmpCompanyInfoResolutionError,
    FmpCompanyInfoResolver,
)


@dataclass(frozen=True, slots=True)
class _FakeResponse:
    """fake FMP 响应。

    :param url_part: 用于匹配请求 URL 的片段。
    :param body: 返回正文。
    """

    url_part: str
    body: str


class _FakeFmpHttpClient:
    """测试用 FMP HTTP client。"""

    calls: list[tuple[str, float]]
    _responses: tuple[_FakeResponse, ...]
    _error: Exception | None

    def __init__(
        self,
        responses: tuple[_FakeResponse, ...],
        *,
        error: Exception | None = None,
    ) -> None:
        """初始化 fake HTTP client。

        :param responses: URL 片段到正文的响应序列。
        :param error: 每次请求应抛出的测试异常。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.calls = []
        self._responses = responses
        self._error = error

    def fetch_text(self, url: str, *, timeout_seconds: float) -> str:
        """按 URL 片段返回预设响应。

        :param url: 请求 URL。
        :param timeout_seconds: 请求超时秒数。
        :returns: 响应正文。
        :raises Exception: 配置了 ``error`` 或找不到匹配响应时抛出。
        """

        self.calls.append((url, timeout_seconds))
        if self._error is not None:
            raise self._error
        for response in self._responses:
            if response.url_part in url:
                return response.body
        raise RuntimeError(f"missing fake response for {url}")


def test_resolve_company_info_uses_two_hop_same_name_aliases() -> None:
    """两跳解析应返回公司名、严格同名 alias，且 canonical ticker 恒为首项。"""

    client = _FakeFmpHttpClient(
        (
            _FakeResponse(
                url_part="search-symbol",
                body=json.dumps(
                    [
                        {"symbol": "V", "name": "Visa Inc."},
                        {"symbol": "VISA", "name": "Visa Inc. Class A"},
                        {"symbol": "V.BA", "name": "Visa Inc."},
                    ]
                ),
            ),
            _FakeResponse(
                url_part="search-name",
                body=json.dumps(
                    [
                        {"symbol": "V", "name": "Visa Inc."},
                        {"symbol": "V.BA", "name": "Visa Inc."},
                        {"symbol": "V.BA", "name": "Visa Inc."},
                        {"symbol": "VISA", "name": "Visa Inc. Class A"},
                    ]
                ),
            ),
        )
    )
    resolver = FmpCompanyInfoResolver(
        api_key="test-key",
        http_client=client,
        timeout_seconds=3.5,
    )

    result = resolver.resolve_company_info(" v ")

    assert result.canonical_ticker == "V"
    assert result.company_name == "Visa Inc."
    assert result.ticker_aliases == ("V", "V.BA")
    assert isinstance(result.ticker_aliases, tuple)
    assert len(client.calls) == 2
    assert all(call[1] == 3.5 for call in client.calls)
    assert "query=V" in client.calls[0][0]
    assert "query=Visa%20Inc." in client.calls[1][0]


def test_resolve_company_info_requires_exact_symbol_match() -> None:
    """search-symbol 无精确 ticker 时不得把第一条模糊结果注入公司身份。"""

    client = _FakeFmpHttpClient(
        (
            _FakeResponse(
                url_part="search-symbol",
                body=json.dumps([{"symbol": "V.BA", "name": "Visa Inc."}]),
            ),
        )
    )
    resolver = FmpCompanyInfoResolver(
        api_key="test-key",
        http_client=client,
    )

    with pytest.raises(FmpCompanyInfoResolutionError, match="精确 ticker"):
        resolver.resolve_company_info("V")

    assert len(client.calls) == 1
    assert "search-symbol" in client.calls[0][0]


def test_resolve_company_info_rejects_empty_symbol_results() -> None:
    """search-symbol 无有效结果时应结构化失败。"""

    client = _FakeFmpHttpClient(
        (
            _FakeResponse(url_part="search-symbol", body=json.dumps([])),
        )
    )
    resolver = FmpCompanyInfoResolver(api_key="test-key", http_client=client)

    with pytest.raises(FmpCompanyInfoResolutionError, match="未返回结果"):
        resolver.resolve_company_info("V")


def test_resolve_company_info_wraps_search_name_failure_after_symbol_success() -> None:
    """search-symbol 成功但 search-name 失败时应包成 resolver 边界异常。"""

    client = _FakeFmpHttpClient(
        (
            _FakeResponse(
                url_part="search-symbol",
                body=json.dumps([{"symbol": "V", "name": "Visa Inc."}]),
            ),
        )
    )
    resolver = FmpCompanyInfoResolver(api_key="test-key", http_client=client)

    with pytest.raises(FmpCompanyInfoResolutionError, match="search-name") as exc_info:
        resolver.resolve_company_info("V")

    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert len(client.calls) == 2
    assert "search-symbol" in client.calls[0][0]
    assert "search-name" in client.calls[1][0]


def test_resolve_company_info_rejects_invalid_json() -> None:
    """FMP 返回非 JSON 时应结构化失败。"""

    client = _FakeFmpHttpClient(
        (
            _FakeResponse(url_part="search-symbol", body="not-json"),
        )
    )
    resolver = FmpCompanyInfoResolver(api_key="test-key", http_client=client)

    with pytest.raises(FmpCompanyInfoResolutionError, match="非 JSON"):
        resolver.resolve_company_info("V")


def test_resolve_company_info_rejects_non_array_payload() -> None:
    """FMP 顶层 payload 不是数组时应结构化失败。"""

    client = _FakeFmpHttpClient(
        (
            _FakeResponse(url_part="search-symbol", body=json.dumps({"symbol": "V"})),
        )
    )
    resolver = FmpCompanyInfoResolver(api_key="test-key", http_client=client)

    with pytest.raises(FmpCompanyInfoResolutionError, match="期望数组"):
        resolver.resolve_company_info("V")


def test_resolve_company_info_wraps_http_timeout() -> None:
    """HTTP/timeout 错误应被包成 resolver 边界异常。"""

    resolver = FmpCompanyInfoResolver(
        api_key="test-key",
        http_client=_FakeFmpHttpClient((), error=TimeoutError("slow")),
    )

    with pytest.raises(FmpCompanyInfoResolutionError, match="请求 FMP"):
        resolver.resolve_company_info("V")


def test_resolver_rejects_missing_api_key_and_bad_timeout() -> None:
    """resolver 不隐式读 env，显式 key 或 timeout 非法时应失败。"""

    with pytest.raises(FmpCompanyInfoResolutionError, match="API key"):
        FmpCompanyInfoResolver(api_key=" ")
    with pytest.raises(FmpCompanyInfoResolutionError, match="timeout"):
        FmpCompanyInfoResolver(api_key="test-key", timeout_seconds=0)
