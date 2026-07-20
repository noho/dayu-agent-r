"""FMP 公司信息 resolver。

本模块把 Financial Modeling Prep 的公司搜索能力封装为显式、可测试的
Fins public contract。resolver 只接收调用方传入的 API key 与 timeout，
不读取环境变量，也不向 LLM 投影错误文本。
"""

from __future__ import annotations

import json
import math
import unicodedata
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Protocol, cast

from dayu.contracts import JsonValue
from dayu.fins.ticker_normalization import try_normalize_ticker

_FMP_BASE_URL: Final[str] = "https://financialmodelingprep.com/stable"
_SEARCH_SYMBOL_ENDPOINT: Final[str] = "search-symbol"
_SEARCH_NAME_ENDPOINT: Final[str] = "search-name"
_SEARCH_SYMBOL_LIMIT: Final[int] = 10
_SEARCH_NAME_LIMIT: Final[int] = 50
_DEFAULT_TIMEOUT_SECONDS: Final[float] = 5.0
_UTF8_ENCODING: Final[str] = "utf-8"
_SYMBOL_FIELD: Final[str] = "symbol"
_NAME_FIELD: Final[str] = "name"


@dataclass(frozen=True, slots=True)
class FmpCompanyInfo:
    """FMP 公司信息解析结果。

    :param canonical_ticker: resolver 使用的规范 ticker，始终为 alias 首项。
    :param company_name: FMP 返回的严格公司名称。
    :param ticker_aliases: 严格同名证券 alias。使用 tuple 是为了让 public
        result 不可变，避免调用方修改 resolver 已返回的业务事实。
    """

    canonical_ticker: str
    company_name: str
    ticker_aliases: tuple[str, ...]


class FmpCompanyInfoResolutionError(RuntimeError):
    """FMP 公司信息解析失败时抛出的结构化边界异常。"""


class FmpHttpClientProtocol(Protocol):
    """FMP HTTP 文本客户端协议。

    该协议只表达 resolver 需要的最小能力，便于测试用 fake client 注入。
    """

    def fetch_text(self, url: str, *, timeout_seconds: float) -> str:
        """读取指定 URL 的 UTF-8 文本响应。

        :param url: 完整 FMP 请求 URL。
        :param timeout_seconds: 本次请求超时秒数。
        :returns: 响应正文文本。
        :raises Exception: 网络、超时或响应读取失败时可由实现抛出。
        """

        ...


@dataclass(frozen=True, slots=True)
class _FmpSearchResult:
    """FMP 搜索结果中 resolver 关心的最小字段。

    :param symbol: 搜索结果的证券代码。
    :param name: 搜索结果的公司名称。
    """

    symbol: str
    name: str


class _UrllibFmpHttpClient:
    """基于标准库 ``urllib`` 的 FMP HTTP 客户端。"""

    def fetch_text(self, url: str, *, timeout_seconds: float) -> str:
        """读取指定 URL 的 UTF-8 文本响应。

        :param url: 完整 FMP 请求 URL。
        :param timeout_seconds: 本次请求超时秒数。
        :returns: 响应正文文本。
        :raises Exception: 网络、超时或响应读取失败时由 ``urllib`` 抛出。
        """

        with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
            return response.read().decode(_UTF8_ENCODING)


class FmpCompanyInfoResolver:
    """FMP 公司信息 resolver。

    resolver 执行两跳算法：先通过 ``search-symbol`` 精确定位 canonical
    ticker 对应公司名，再通过 ``search-name`` 搜索严格同名证券，并保证
    canonical ticker 在 alias tuple 首位。无精确 symbol 命中时不得注入公司身份。
    """

    _api_key: str
    _http_client: FmpHttpClientProtocol
    _timeout_seconds: float

    def __init__(
        self,
        *,
        api_key: str,
        http_client: FmpHttpClientProtocol | None = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """初始化 FMP 公司信息 resolver。

        :param api_key: 调用方显式传入的 FMP API key。
        :param http_client: 可选 HTTP 客户端；``None`` 时使用标准库实现。
        :param timeout_seconds: 单次 FMP HTTP 请求超时秒数。
        :returns: ``None``。
        :raises FmpCompanyInfoResolutionError: API key 或 timeout 非法时抛出。
        """

        normalized_api_key = api_key.strip()
        if normalized_api_key == "":
            raise FmpCompanyInfoResolutionError("FMP API key 不能为空")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise FmpCompanyInfoResolutionError("FMP timeout 必须为正有限秒数")
        self._api_key = normalized_api_key
        self._http_client = _UrllibFmpHttpClient() if http_client is None else http_client
        self._timeout_seconds = timeout_seconds

    def resolve_company_info(self, canonical_ticker: str) -> FmpCompanyInfo:
        """解析 FMP 公司名称与严格同名 ticker aliases。

        :param canonical_ticker: 调用方传入的 canonical ticker 文本。
        :returns: FMP 公司信息解析结果。
        :raises FmpCompanyInfoResolutionError: 输入、请求、JSON 或业务结果非法时抛出。
        """

        normalized_ticker = _normalize_ticker_token(canonical_ticker)
        if normalized_ticker == "":
            raise FmpCompanyInfoResolutionError("canonical ticker 不能为空")

        symbol_results = self._fetch_search_results(
            endpoint=_SEARCH_SYMBOL_ENDPOINT,
            query=normalized_ticker,
            limit=_SEARCH_SYMBOL_LIMIT,
        )
        selected_company = _select_symbol_result(
            results=symbol_results,
            canonical_ticker=normalized_ticker,
        )
        company_name = selected_company.name
        normalized_company_name = _normalize_company_name(company_name)

        same_name_symbol_results = _filter_same_name_results(
            results=symbol_results,
            normalized_company_name=normalized_company_name,
        )
        name_results = self._fetch_search_results(
            endpoint=_SEARCH_NAME_ENDPOINT,
            query=company_name,
            limit=_SEARCH_NAME_LIMIT,
        )
        same_name_name_results = _filter_same_name_results(
            results=name_results,
            normalized_company_name=normalized_company_name,
        )
        ticker_aliases = _dedupe_ticker_aliases(
            canonical_ticker=normalized_ticker,
            raw_aliases=tuple(
                result.symbol
                for result in (
                    *same_name_symbol_results,
                    *same_name_name_results,
                )
            ),
        )
        return FmpCompanyInfo(
            canonical_ticker=normalized_ticker,
            company_name=company_name,
            ticker_aliases=ticker_aliases,
        )

    def _fetch_search_results(
        self,
        *,
        endpoint: str,
        query: str,
        limit: int,
    ) -> tuple[_FmpSearchResult, ...]:
        """请求 FMP 搜索接口并解析最小结果字段。

        :param endpoint: FMP 搜索端点名称。
        :param query: 查询文本。
        :param limit: 结果上限。
        :returns: 搜索结果 tuple。
        :raises FmpCompanyInfoResolutionError: 请求失败或响应格式非法时抛出。
        """

        url = _build_fmp_search_url(
            endpoint=endpoint,
            query=query,
            limit=limit,
            api_key=self._api_key,
        )
        try:
            raw_body = self._http_client.fetch_text(
                url,
                timeout_seconds=self._timeout_seconds,
            )
        except Exception as exc:
            raise FmpCompanyInfoResolutionError(f"请求 FMP {endpoint} 失败") from exc
        return _parse_fmp_search_results(endpoint=endpoint, raw_body=raw_body)


def _build_fmp_search_url(
    *,
    endpoint: str,
    query: str,
    limit: int,
    api_key: str,
) -> str:
    """构造 FMP 搜索 URL。

    :param endpoint: FMP 搜索端点名称。
    :param query: 查询文本。
    :param limit: 结果上限。
    :param api_key: FMP API key。
    :returns: 完整请求 URL。
    :raises Exception: 不主动抛出异常。
    """

    return (
        f"{_FMP_BASE_URL}/{endpoint}"
        f"?query={urllib.parse.quote(query)}"
        f"&limit={limit}"
        f"&apikey={urllib.parse.quote(api_key)}"
    )


def _parse_fmp_search_results(
    *,
    endpoint: str,
    raw_body: str,
) -> tuple[_FmpSearchResult, ...]:
    """解析 FMP 搜索响应。

    :param endpoint: FMP 搜索端点名称，用于错误消息。
    :param raw_body: HTTP 响应正文。
    :returns: 只包含有效 ``symbol`` / ``name`` 的结果 tuple。
    :raises FmpCompanyInfoResolutionError: JSON 或顶层格式非法时抛出。
    """

    try:
        payload = cast(JsonValue, json.loads(raw_body))
    except json.JSONDecodeError as exc:
        raise FmpCompanyInfoResolutionError(f"FMP {endpoint} 返回非 JSON 内容") from exc
    if not isinstance(payload, list):
        raise FmpCompanyInfoResolutionError(f"FMP {endpoint} 返回格式非法，期望数组")
    results: list[_FmpSearchResult] = []
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        symbol = _string_field(item, _SYMBOL_FIELD)
        name = _string_field(item, _NAME_FIELD)
        if symbol == "" or name == "":
            continue
        results.append(_FmpSearchResult(symbol=symbol, name=name))
    return tuple(results)


def _select_symbol_result(
    *,
    results: Sequence[_FmpSearchResult],
    canonical_ticker: str,
) -> _FmpSearchResult:
    """从 ``search-symbol`` 结果中选择规范公司条目。

    :param results: ``search-symbol`` 返回结果。
    :param canonical_ticker: 规范 ticker。
    :returns: 选中的搜索结果。
    :raises FmpCompanyInfoResolutionError: 搜索结果为空或无精确 symbol 命中时抛出。
    """

    if len(results) == 0:
        raise FmpCompanyInfoResolutionError(
            f"FMP search-symbol 未返回结果: ticker={canonical_ticker}"
        )
    for item in results:
        normalized_symbol = _normalize_ticker_token(item.symbol)
        if normalized_symbol == canonical_ticker:
            return item
    raise FmpCompanyInfoResolutionError(
        f"FMP search-symbol 未返回精确 ticker 命中: ticker={canonical_ticker}"
    )


def _filter_same_name_results(
    *,
    results: Sequence[_FmpSearchResult],
    normalized_company_name: str,
) -> tuple[_FmpSearchResult, ...]:
    """过滤出与目标公司名严格同名的结果。

    :param results: 原始搜索结果。
    :param normalized_company_name: 已规范化的目标公司名。
    :returns: 严格同名结果 tuple。
    :raises Exception: 不主动抛出异常。
    """

    return tuple(
        result
        for result in results
        if _normalize_company_name(result.name) == normalized_company_name
    )


def _normalize_company_name(company_name: str) -> str:
    """规范化公司名，供严格同名比较使用。

    :param company_name: 原始公司名称。
    :returns: 大写、NFKC 归一且空白折叠后的公司名称。
    :raises Exception: 不主动抛出异常。
    """

    normalized = unicodedata.normalize("NFKC", company_name)
    normalized = " ".join(normalized.strip().split())
    return normalized.upper()


def _normalize_ticker_token(raw_token: str) -> str:
    """规范化 ticker token。

    :param raw_token: 原始 ticker token。
    :returns: canonical ticker 或大写去空白 token；空输入返回空字符串。
    :raises Exception: 不主动抛出异常。
    """

    normalized_source = try_normalize_ticker(raw_token)
    if normalized_source is not None:
        return normalized_source.canonical
    compact_token = "".join(raw_token.strip().split())
    return compact_token.upper()


def _dedupe_ticker_aliases(
    *,
    canonical_ticker: str,
    raw_aliases: Sequence[str],
) -> tuple[str, ...]:
    """对 alias 列表做规范化与去重。

    :param canonical_ticker: 规范 ticker。
    :param raw_aliases: 原始 alias 列表。
    :returns: 首项恒为 canonical ticker 的不可变去重 alias tuple。
    :raises Exception: 不主动抛出异常。
    """

    deduped_aliases: list[str] = []
    seen_aliases: set[str] = set()
    for raw_alias in (canonical_ticker, *raw_aliases):
        normalized_alias = _normalize_ticker_token(raw_alias)
        if normalized_alias == "" or normalized_alias in seen_aliases:
            continue
        seen_aliases.add(normalized_alias)
        deduped_aliases.append(normalized_alias)
    return tuple(deduped_aliases)


def _string_field(item: Mapping[str, JsonValue], field_name: str) -> str:
    """从 JSON object 中读取字符串字段。

    :param item: FMP 搜索结果 JSON object。
    :param field_name: 字段名。
    :returns: 去空白字符串；字段不存在或非字符串时返回空字符串。
    :raises Exception: 不主动抛出异常。
    """

    value = item.get(field_name)
    if not isinstance(value, str):
        return ""
    return value.strip()


__all__: tuple[str, ...] = (
    "FmpCompanyInfo",
    "FmpCompanyInfoResolutionError",
    "FmpCompanyInfoResolver",
    "FmpHttpClientProtocol",
)
