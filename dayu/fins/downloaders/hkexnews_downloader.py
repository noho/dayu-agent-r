"""披露易 HK 财报下载器。

本模块实现 ``CnReportDiscoveryClientProtocol``：从披露易 stock list 解析
``stockId``，通过 ``titleSearchServlet.do`` 发现年报、半年报与季度公告，并
下载 PDF。模块只依赖 HTTP 客户端、CN/HK typed model 和 pipeline-owned
report selection helper；不依赖 storage/docling，也不生成 ``document_id``。
语言过滤、财期/财年推断、同 period/year 去重、amended 优先与
``CnReportCandidate`` 构造由 ``dayu.fins.pipelines.cn_report_selection`` 持有。
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Optional, TypeAlias, cast

import httpx

from dayu.fins.download_contract import (
    FinsDownloadProviderError,
    FinsDownloadSource,
    FinsDownloadTransportCategory,
)
from dayu.fins.pipelines.cn_download_models import (
    CnCompanyProfile,
    CnFiscalPeriod,
    CnLanguage,
    CnReportCandidate,
    CnReportHeadMeta,
    CnReportQuery,
    DownloadedReportAsset,
    HkexnewsRawAnnouncement,
)
from dayu.fins.pipelines.cn_report_selection import select_hkexnews_report_candidates
from dayu.fins._log import Log

_MODULE: Final[str] = "FINS.HKEXNEWS_DOWNLOADER"

JsonScalar: TypeAlias = str | int | float | bool | None
"""JSON 标量值。"""

JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
"""披露易接口 JSON 响应值。"""

HKEXNEWS_BASE_URL: Final[str] = "https://www1.hkexnews.hk"
HKEXNEWS_ACTIVE_STOCK_ZH_URL: Final[str] = f"{HKEXNEWS_BASE_URL}/ncms/script/eds/activestock_sehk_c.json"
HKEXNEWS_INACTIVE_STOCK_ZH_URL: Final[str] = f"{HKEXNEWS_BASE_URL}/ncms/script/eds/inactivestock_sehk_c.json"
HKEXNEWS_TITLE_SEARCH_URL: Final[str] = f"{HKEXNEWS_BASE_URL}/search/titleSearchServlet.do"

DEFAULT_USER_AGENT: Final[str] = "DayuAgent/1.0 (+hk-download)"
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final[float] = 30.0
DEFAULT_SLEEP_SECONDS: Final[float] = 0.3
DEFAULT_MAX_RETRIES: Final[int] = 3
RETRY_BACKOFF_BASE_SECONDS: Final[float] = 0.8
DEFAULT_LANGUAGES: Final[tuple[CnLanguage, ...]] = ("zh",)

_PDF_MAGIC_BYTES: Final[bytes] = b"%PDF-"
_PDF_MIN_BYTES: Final[int] = 1024
_HKEXNEWS_CATEGORY_MARKET: Final[str] = "SEHK"
_HKEXNEWS_CATEGORY_ZERO: Final[str] = "0"
_HKEXNEWS_SEARCH_TYPE_BY_STOCK: Final[str] = "1"
_HKEXNEWS_DOCUMENT_TYPE_ALL: Final[str] = "-1"
_HKEXNEWS_T1_FINANCIAL_STATEMENTS: Final[str] = "40000"
_HKEXNEWS_T1_ANNOUNCEMENTS: Final[str] = "10000"
_HKEXNEWS_T2_GROUP_ALL: Final[str] = "-2"
_HKEXNEWS_T2_GROUP_RESULTS: Final[str] = "3"
_HKEXNEWS_T2_ANNUAL_REPORT: Final[str] = "40100"
_HKEXNEWS_T2_INTERIM_REPORT: Final[str] = "40200"
_HKEXNEWS_T2_QUARTERLY_RESULTS: Final[str] = "13600"
_HKEXNEWS_INITIAL_CUMULATIVE_ROW_RANGE: Final[int] = 100
_HKEXNEWS_MB_DATE_RANGE: Final[str] = "0"
_HKEXNEWS_SORT_BY_DATETIME: Final[str] = "DateTime"
_HKEXNEWS_SORT_DIR_DESC: Final[str] = "0"
_HKEXNEWS_FILE_TYPE_PDF: Final[str] = "PDF"
_HKEXNEWS_FIELD_HAS_NEXT_ROW: Final[str] = "hasNextRow"
_HKEXNEWS_FIELD_ROW_RANGE: Final[str] = "rowRange"
_HKEXNEWS_FIELD_LOADED_RECORD: Final[str] = "loadedRecord"
_HKEXNEWS_FIELD_RECORD_COUNT: Final[str] = "recordCnt"
_HKEXNEWS_FIELD_RESULT: Final[str] = "result"
_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?P<year>\d{4})[-/](?P<month>\d{1,2})[-/](?P<day>\d{1,2})")
_BR_PATTERN: Final[re.Pattern[str]] = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_PATTERN: Final[re.Pattern[str]] = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class _HkCategorySpec:
    """披露易 title search 标题分类参数。"""

    t1code: str
    t2_group_code: str
    t2code: str


@dataclass(frozen=True)
class _HkStockMappingEntry:
    """披露易 stock list 单只股票记录。"""

    stock_code: str
    stock_id: str
    company_name: str


@dataclass(frozen=True)
class _HkexnewsTitleSearchSnapshot:
    """披露易 title search 单轮已验证累计快照。"""

    requested_row_range: int
    response_row_range: int
    has_next_row: bool
    loaded_record: int
    record_count: int
    rows: tuple[dict[str, JsonValue], ...]


class HkexnewsProviderProtocolError(FinsDownloadProviderError):
    """披露易来源响应违反官方协议。"""

    def __init__(self) -> None:
        """构造不含 provider payload 或查询参数的协议失败。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        super().__init__(
            source=FinsDownloadSource.HKEXNEWS,
            transport_category=FinsDownloadTransportCategory.PROTOCOL,
            retryable=False,
            safe_message="披露易来源响应格式不符合预期",
        )


_PERIOD_TO_CATEGORY_SPEC: Final[dict[CnFiscalPeriod, _HkCategorySpec]] = {
    "FY": _HkCategorySpec(
        t1code=_HKEXNEWS_T1_FINANCIAL_STATEMENTS,
        t2_group_code=_HKEXNEWS_T2_GROUP_ALL,
        t2code=_HKEXNEWS_T2_ANNUAL_REPORT,
    ),
    "H1": _HkCategorySpec(
        t1code=_HKEXNEWS_T1_FINANCIAL_STATEMENTS,
        t2_group_code=_HKEXNEWS_T2_GROUP_ALL,
        t2code=_HKEXNEWS_T2_INTERIM_REPORT,
    ),
    "Q2": _HkCategorySpec(
        t1code=_HKEXNEWS_T1_ANNOUNCEMENTS,
        t2_group_code=_HKEXNEWS_T2_GROUP_RESULTS,
        t2code=_HKEXNEWS_T2_QUARTERLY_RESULTS,
    ),
    "Q1": _HkCategorySpec(
        t1code=_HKEXNEWS_T1_ANNOUNCEMENTS,
        t2_group_code=_HKEXNEWS_T2_GROUP_RESULTS,
        t2code=_HKEXNEWS_T2_QUARTERLY_RESULTS,
    ),
    "Q3": _HkCategorySpec(
        t1code=_HKEXNEWS_T1_ANNOUNCEMENTS,
        t2_group_code=_HKEXNEWS_T2_GROUP_RESULTS,
        t2code=_HKEXNEWS_T2_QUARTERLY_RESULTS,
    ),
    "Q4": _HkCategorySpec(
        t1code=_HKEXNEWS_T1_ANNOUNCEMENTS,
        t2_group_code=_HKEXNEWS_T2_GROUP_RESULTS,
        t2code=_HKEXNEWS_T2_QUARTERLY_RESULTS,
    ),
}


class HkexnewsDiscoveryClient:
    """披露易 HK discovery / 下载客户端。"""

    def __init__(
        self,
        *,
        client: Optional[httpx.Client] = None,
        user_agent: Optional[str] = None,
        sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        languages: tuple[CnLanguage, ...] = DEFAULT_LANGUAGES,
        sleep_func: Optional[Callable[[float], None]] = None,
    ) -> None:
        """初始化披露易下载器。

        Args:
            client: 可选 ``httpx.Client``；测试可注入 ``MockTransport`` 客户端。
            user_agent: HTTP User-Agent。
            sleep_seconds: 连续请求间隔秒数。
            max_retries: 单次 HTTP 请求最大重试次数。
            request_timeout_seconds: 单次请求超时秒数。
            languages: 查询语言顺序；默认只查中文。
            sleep_func: 可注入 sleep 函数；测试可传 ``lambda _: None``。

        Raises:
            ValueError: ``max_retries`` 非正、``sleep_seconds`` 为负或语言为空时抛出。
        """

        if max_retries <= 0:
            raise ValueError("max_retries 必须大于 0")
        if sleep_seconds < 0:
            raise ValueError("sleep_seconds 不能为负数")
        if not languages:
            raise ValueError("languages 不能为空")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=request_timeout_seconds,
            headers={"User-Agent": user_agent or DEFAULT_USER_AGENT},
        )
        self._sleep_seconds = sleep_seconds
        self._max_retries = max_retries
        self._languages = languages
        self._sleep_func: Callable[[float], None] = sleep_func if sleep_func is not None else time.sleep
        self._last_request_finished_at: float | None = None
        self._stock_mapping_cache: dict[str, _HkStockMappingEntry] | None = None

    def close(self) -> None:
        """关闭底层 HTTP 客户端。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        if self._owns_client:
            self._client.close()

    def resolve_company(self, query: CnReportQuery) -> CnCompanyProfile:
        """解析 HK ticker 对应的披露易公司元数据。

        Args:
            query: 单次 download 查询参数；``query.market`` 必须为 ``"HK"``。

        Returns:
            ``CnCompanyProfile``，``company_id`` 形如 ``"HKEX:{stockId}"``。

        Raises:
            ValueError: market 非 HK，或 stock list 未命中 ticker 时抛出。
            FinsDownloadProviderError: stock list 请求或协议失败时抛出。
        """

        if query.market != "HK":
            raise ValueError(f"HkexnewsDiscoveryClient 仅支持 HK，收到 market={query.market!r}")
        stock_code = _to_hkex_stock_code(query.normalized_ticker)
        mapping = self._fetch_stock_mapping()
        entry = mapping.get(stock_code)
        if entry is None:
            raise ValueError(f"披露易 stock list 未命中 ticker={query.normalized_ticker!r}")
        return CnCompanyProfile(
            provider="hkexnews",
            company_id=f"HKEX:{entry.stock_id}",
            company_name=entry.company_name,
            ticker=query.normalized_ticker,
        )

    def list_report_candidates(
        self,
        query: CnReportQuery,
        profile: CnCompanyProfile,
        *,
        cancellation_checkpoint: Callable[[], None] | None = None,
    ) -> tuple[CnReportCandidate, ...]:
        """列出符合窗口和财期的 HK 报告候选。

        Args:
            query: 单次 download 查询参数。
            profile: ``resolve_company`` 返回的公司元数据。
            cancellation_checkpoint: 可选 workflow-owned 无参取消检查点；
                每个 title search 累计 GET 前和成功响应后调用。

        Returns:
            候选报告 tuple。HK 季度报告查无返回空 tuple，不抛异常。

        Raises:
            ValueError: market/provider/company_id 非法时抛出。
            FinsDownloadProviderError: 任一有效财期来源请求或协议失败时抛出。
        """

        if query.market != "HK":
            raise ValueError(f"HkexnewsDiscoveryClient 仅支持 HK，收到 market={query.market!r}")
        if profile.provider != "hkexnews":
            raise ValueError(f"profile.provider 必须为 hkexnews，收到 {profile.provider!r}")
        stock_id = profile.company_id.removeprefix("HKEX:")
        if not stock_id:
            raise ValueError(f"profile.company_id 缺少 HKEX: 前缀: {profile.company_id!r}")
        stock_code = _to_hkex_stock_code(query.normalized_ticker)

        raw_announcements: list[HkexnewsRawAnnouncement] = []
        periods_by_category: dict[_HkCategorySpec, list[CnFiscalPeriod]] = {}
        for period in query.target_periods:
            category_spec = _PERIOD_TO_CATEGORY_SPEC.get(period)
            if category_spec is None:
                Log.warn(f"未知 fiscal_period={period!r}，已跳过", module=_MODULE)
                continue
            periods = periods_by_category.setdefault(category_spec, [])
            if period not in periods:
                periods.append(period)

        for category_spec in periods_by_category:
            announcements = self._query_period_announcements(
                stock_id=stock_id,
                stock_code=stock_code,
                category_spec=category_spec,
                start_date=query.start_date,
                end_date=query.end_date,
                cancellation_checkpoint=cancellation_checkpoint,
            )
            raw_announcements.extend(announcements)
        return select_hkexnews_report_candidates(
            query=query,
            announcements=tuple(raw_announcements),
            read_head_meta=self._http_head_meta,
        )

    def download_report_pdf(self, candidate: CnReportCandidate) -> DownloadedReportAsset:
        """下载单份 HK PDF 并返回资产对象。

        Args:
            candidate: 远端候选报告。

        Returns:
            已下载 PDF 资产。

        Raises:
            ValueError: candidate 来源不属于披露易时抛出。
            FinsDownloadProviderError: 下载或 PDF 协议校验失败时抛出。
        """

        if candidate.provider != "hkexnews":
            raise ValueError(f"HkexnewsDiscoveryClient 不支持 provider={candidate.provider!r}")
        payload = self._http_download_bytes(candidate.source_url)
        if len(payload) < _PDF_MIN_BYTES:
            raise HkexnewsProviderProtocolError
        if not payload.startswith(_PDF_MAGIC_BYTES):
            raise HkexnewsProviderProtocolError
        sha256 = hashlib.sha256(payload).hexdigest()
        return DownloadedReportAsset(
            candidate=candidate,
            pdf_bytes=payload,
            sha256=sha256,
            content_length=len(payload),
            downloaded_at=_utc_now_isoformat(),
        )

    def _fetch_stock_mapping(self) -> dict[str, _HkStockMappingEntry]:
        """拉取并缓存披露易 active/inactive stock list。

        Args:
            无。

        Returns:
            ``STOCK_CODE -> _HkStockMappingEntry`` 映射。

        Raises:
            FinsDownloadProviderError: 来源请求或响应协议失败时抛出。
        """

        if self._stock_mapping_cache is not None:
            return self._stock_mapping_cache
        mapping: dict[str, _HkStockMappingEntry] = {}
        for url in (HKEXNEWS_ACTIVE_STOCK_ZH_URL, HKEXNEWS_INACTIVE_STOCK_ZH_URL):
            payload = self._http_get_json(url)
            for raw in _extract_json_rows(payload):
                entry = _parse_stock_mapping_entry(raw)
                if entry is not None:
                    mapping.setdefault(entry.stock_code, entry)
        self._stock_mapping_cache = mapping
        return mapping

    def _query_period_announcements(
        self,
        *,
        stock_id: str,
        stock_code: str,
        category_spec: _HkCategorySpec,
        start_date: str,
        end_date: str,
        cancellation_checkpoint: Callable[[], None] | None,
    ) -> list[HkexnewsRawAnnouncement]:
        """查询单个披露易二级分类的公告列表。

        Args:
            stock_id: 披露易 stockId。
            stock_code: 5 位股票代码。
            category_spec: 披露易标题分类参数。
            start_date: 起始日期 ``YYYY-MM-DD``。
            end_date: 结束日期 ``YYYY-MM-DD``。
            cancellation_checkpoint: 可选 workflow-owned 无参取消检查点。

        Returns:
            匹配目标股票且非英文的公告列表。

        Raises:
            FinsDownloadProviderError: 来源请求或响应协议失败时抛出。
        """

        primary: list[HkexnewsRawAnnouncement] = []
        for language in self._languages:
            base_params: Mapping[str, str] = MappingProxyType(
                {
                    "lang": _language_param(language),
                    "category": _HKEXNEWS_CATEGORY_ZERO,
                    "market": _HKEXNEWS_CATEGORY_MARKET,
                    "stockId": stock_id,
                    "searchType": _HKEXNEWS_SEARCH_TYPE_BY_STOCK,
                    "documentType": _HKEXNEWS_DOCUMENT_TYPE_ALL,
                    "t1code": category_spec.t1code,
                    "t2Gcode": category_spec.t2_group_code,
                    "t2code": category_spec.t2code,
                    "fromDate": start_date.replace("-", ""),
                    "toDate": end_date.replace("-", ""),
                    "MB-Daterange": _HKEXNEWS_MB_DATE_RANGE,
                    "sortByOptions": _HKEXNEWS_SORT_BY_DATETIME,
                    "sortDir": _HKEXNEWS_SORT_DIR_DESC,
                }
            )
            rows = self._fetch_complete_title_search_rows(
                base_params=base_params,
                stock_code=stock_code,
                category_spec=category_spec,
                language=language,
                cancellation_checkpoint=cancellation_checkpoint,
            )
            parsed_rows = [
                item
                for item in (_parse_announcement(row, language=language) for row in rows)
                if item is not None and _announcement_matches_stock(item.stock_code_payload, stock_code)
            ]
            primary.extend(parsed_rows)
        return primary

    def _fetch_complete_title_search_rows(
        self,
        *,
        base_params: Mapping[str, str],
        stock_code: str,
        category_spec: _HkCategorySpec,
        language: CnLanguage,
        cancellation_checkpoint: Callable[[], None] | None,
    ) -> tuple[dict[str, JsonValue], ...]:
        """按官方 cumulative ``rowRange`` 协议取得最终完整快照。

        Args:
            base_params: 不含 ``rowRange`` 的不变查询参数。
            stock_code: 5 位股票代码，仅用于业务可读错误上下文。
            category_spec: 披露易标题分类参数。
            language: 查询语言。
            cancellation_checkpoint: 可选 workflow-owned 无参取消检查点。

        Returns:
            provider 明确证明完整的最后一轮累计 rows。

        Raises:
            CnDownloadCancelledError: 检查点报告取消时原样传播。
            HkexnewsProviderProtocolError: 官方响应字段、轮内不变式或轮间进度矛盾时抛出。
            FinsDownloadProviderError: HTTP 请求或响应协议失败时抛出。
        """

        current_row_range = _HKEXNEWS_INITIAL_CUMULATIVE_ROW_RANGE
        previous_continuation_loaded: int | None = None
        while True:
            if cancellation_checkpoint is not None:
                cancellation_checkpoint()
            params = dict(base_params)
            params[_HKEXNEWS_FIELD_ROW_RANGE] = str(current_row_range)
            payload = self._http_get_json(HKEXNEWS_TITLE_SEARCH_URL, params=params)
            if cancellation_checkpoint is not None:
                cancellation_checkpoint()
            snapshot = _parse_title_search_snapshot(
                payload,
                requested_row_range=current_row_range,
                stock_code=stock_code,
                category_spec=category_spec,
                language=language,
            )
            latest_rows = snapshot.rows
            if not snapshot.has_next_row:
                return latest_rows
            if previous_continuation_loaded is not None and snapshot.loaded_record <= previous_continuation_loaded:
                raise HkexnewsProviderProtocolError
            previous_continuation_loaded = snapshot.loaded_record
            current_row_range = max(
                current_row_range * 2,
                snapshot.record_count,
            )

    def _http_get_json(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> JsonValue:
        """GET JSON。

        Args:
            url: 请求 URL。
            params: 可选 query 参数。

        Returns:
            JSON 响应。

        Raises:
            FinsDownloadProviderError: 请求或响应协议失败时抛出。
        """

        for attempt in range(self._max_retries):
            try:
                self._throttle_before_request()
                try:
                    response = self._client.get(url, params=params)
                    response.raise_for_status()
                finally:
                    self._mark_request_finished()
            except httpx.HTTPError as exc:
                failure = _hkexnews_http_failure(exc)
                Log.debug(
                    f"GET JSON 请求失败: attempt={attempt + 1} transport_category={failure.transport_category.value}",
                    module=_MODULE,
                )
                if not failure.retryable or attempt >= self._max_retries - 1:
                    raise failure from exc
                self._retry_backoff(attempt)
                continue
            try:
                return cast(JsonValue, response.json())
            except ValueError as exc:
                raise HkexnewsProviderProtocolError from exc
        raise AssertionError("GET JSON retry loop terminated without result")

    def _http_head_meta(self, url: str) -> CnReportHeadMeta:
        """HEAD 拉取 content-length / etag / last-modified。

        Args:
            url: PDF URL。

        Returns:
            HEAD 元数据；请求失败时返回空字段。

        Raises:
            无。
        """

        try:
            self._throttle_before_request()
            try:
                response = self._client.head(url, follow_redirects=True)
                response.raise_for_status()
            finally:
                self._mark_request_finished()
        except httpx.HTTPError as exc:
            failure = _hkexnews_http_failure(exc)
            Log.warn(
                f"HEAD 元数据请求失败: transport_category={failure.transport_category.value}",
                module=_MODULE,
            )
            return CnReportHeadMeta(content_length=None, etag=None, last_modified=None)
        raw_length = response.headers.get("Content-Length")
        try:
            content_length = int(raw_length) if raw_length is not None else None
        except ValueError:
            content_length = None
        return CnReportHeadMeta(
            content_length=content_length,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )

    def _http_download_bytes(self, url: str) -> bytes:
        """带重试下载文件字节。

        Args:
            url: PDF URL。

        Returns:
            响应字节。

        Raises:
            FinsDownloadProviderError: 请求失败时抛出。
        """

        for attempt in range(self._max_retries):
            try:
                self._throttle_before_request()
                try:
                    response = self._client.get(url, follow_redirects=True)
                    response.raise_for_status()
                    return response.content
                finally:
                    self._mark_request_finished()
            except httpx.HTTPError as exc:
                failure = _hkexnews_http_failure(exc)
                Log.debug(
                    f"PDF 下载请求失败: attempt={attempt + 1} transport_category={failure.transport_category.value}",
                    module=_MODULE,
                )
                if not failure.retryable or attempt >= self._max_retries - 1:
                    raise failure from exc
                self._retry_backoff(attempt)
        raise AssertionError("PDF retry loop terminated without result")

    def _throttle_before_request(self) -> None:
        """按连续请求间隔限制发起 HTTP 请求。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        now = time.monotonic()
        if self._sleep_seconds > 0 and self._last_request_finished_at is not None:
            elapsed = now - self._last_request_finished_at
            remaining = self._sleep_seconds - elapsed
            if remaining > 0:
                self._sleep_func(remaining)

    def _mark_request_finished(self) -> None:
        """记录最近一次 HTTP 请求结束时间。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self._last_request_finished_at = time.monotonic()

    def _retry_backoff(self, attempt_index: int) -> None:
        """指数退避。

        Args:
            attempt_index: 当前重试序号。

        Returns:
            无。

        Raises:
            无。
        """

        if attempt_index >= self._max_retries - 1:
            return
        self._sleep_func(RETRY_BACKOFF_BASE_SECONDS * (2**attempt_index))


def _hkexnews_http_failure(error: httpx.HTTPError) -> FinsDownloadProviderError:
    """把披露易 HTTP 异常映射为封闭、脱敏的来源失败。

    Args:
        error: ``httpx`` 请求或状态异常。

    Returns:
        保留来源、transport 类别和重试事实的 typed failure。

    Raises:
        无。
    """

    if isinstance(error, httpx.TimeoutException):
        category = FinsDownloadTransportCategory.TIMEOUT
        retryable = True
        safe_message = "披露易来源请求超时"
    elif isinstance(error, httpx.NetworkError):
        category = FinsDownloadTransportCategory.CONNECTION
        retryable = True
        safe_message = "无法连接披露易来源"
    elif isinstance(error, httpx.HTTPStatusError):
        category = FinsDownloadTransportCategory.HTTP_STATUS
        retryable = 500 <= error.response.status_code < 600
        safe_message = "披露易来源返回不可接受的 HTTP 状态"
    elif isinstance(error, httpx.ProtocolError):
        category = FinsDownloadTransportCategory.PROTOCOL
        retryable = False
        safe_message = "披露易来源 HTTP 协议失败"
    else:
        category = FinsDownloadTransportCategory.UNKNOWN
        retryable = True
        safe_message = "披露易来源请求失败"
    return FinsDownloadProviderError(
        source=FinsDownloadSource.HKEXNEWS,
        transport_category=category,
        retryable=retryable,
        safe_message=safe_message,
    )


def _extract_json_rows(payload: JsonValue) -> list[JsonValue]:
    """从披露易 JSON 响应中提取列表行。

    Args:
        payload: JSON 响应。

    Returns:
        已验证的列表行。

    Raises:
        HkexnewsProviderProtocolError: 响应结构无法识别时抛出。
    """

    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise HkexnewsProviderProtocolError
    for key in (
        "stockInfo",
        "stockList",
        "stocks",
        "data",
        "result",
        "records",
        "rows",
        "announcements",
    ):
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            parsed = _parse_embedded_json_list(value)
            if parsed is not None:
                return parsed
        raise HkexnewsProviderProtocolError
    raise HkexnewsProviderProtocolError


def _parse_title_search_snapshot(
    payload: JsonValue,
    *,
    requested_row_range: int,
    stock_code: str,
    category_spec: _HkCategorySpec,
    language: CnLanguage,
) -> _HkexnewsTitleSearchSnapshot:
    """严格解析并校验 title search 单轮官方累计快照。

    Args:
        payload: HTTP helper 返回的 JSON 响应。
        requested_row_range: 当轮客户端请求的 cumulative range。
        stock_code: 5 位股票代码。
        category_spec: 查询分类参数。
        language: 查询语言。

    Returns:
        已校验的 provider-private frozen snapshot。

    Raises:
        HkexnewsProviderProtocolError: 字段缺失、类型错误、负值或轮内事实矛盾时抛出。
    """

    context = (
        f"stock_code={stock_code} lang={language} "
        f"t1code={category_spec.t1code} t2code={category_spec.t2code} "
        f"requested_row_range={requested_row_range}"
    )
    if not isinstance(payload, dict):
        raise HkexnewsProviderProtocolError
    has_next_row = _require_title_search_bool(
        payload,
        field=_HKEXNEWS_FIELD_HAS_NEXT_ROW,
        context=context,
    )
    response_row_range = _require_title_search_non_negative_int(
        payload,
        field=_HKEXNEWS_FIELD_ROW_RANGE,
        context=context,
    )
    loaded_record = _require_title_search_non_negative_int(
        payload,
        field=_HKEXNEWS_FIELD_LOADED_RECORD,
        context=context,
    )
    record_count = _require_title_search_non_negative_int(
        payload,
        field=_HKEXNEWS_FIELD_RECORD_COUNT,
        context=context,
    )
    rows = _require_title_search_rows(payload, context=context)
    snapshot = _HkexnewsTitleSearchSnapshot(
        requested_row_range=requested_row_range,
        response_row_range=response_row_range,
        has_next_row=has_next_row,
        loaded_record=loaded_record,
        record_count=record_count,
        rows=rows,
    )
    row_count = len(snapshot.rows)
    if snapshot.response_row_range != snapshot.requested_row_range:
        raise HkexnewsProviderProtocolError
    if snapshot.loaded_record != row_count:
        raise HkexnewsProviderProtocolError
    if snapshot.loaded_record > snapshot.record_count:
        raise HkexnewsProviderProtocolError
    if snapshot.loaded_record > snapshot.requested_row_range:
        raise HkexnewsProviderProtocolError
    if snapshot.has_next_row and snapshot.loaded_record >= snapshot.record_count:
        raise HkexnewsProviderProtocolError
    if not snapshot.has_next_row and snapshot.loaded_record != snapshot.record_count:
        raise HkexnewsProviderProtocolError
    return snapshot


def _require_title_search_bool(
    payload: dict[str, JsonValue],
    *,
    field: str,
    context: str,
) -> bool:
    """读取 title search 必填 JSON bool 字段。

    Args:
        payload: title search 顶层 object。
        field: 官方字段名。
        context: 业务可读查询上下文。

    Returns:
        严格 JSON bool 值。

    Raises:
        HkexnewsProviderProtocolError: 字段缺失或类型不是 bool 时抛出。
    """

    value = _require_title_search_field(payload, field=field, context=context)
    if not isinstance(value, bool):
        raise HkexnewsProviderProtocolError
    return value


def _require_title_search_non_negative_int(
    payload: dict[str, JsonValue],
    *,
    field: str,
    context: str,
) -> int:
    """读取 title search 必填的非负 JSON int 字段。

    Args:
        payload: title search 顶层 object。
        field: 官方字段名。
        context: 业务可读查询上下文。

    Returns:
        非负整数。

    Raises:
        HkexnewsProviderProtocolError: 字段缺失、bool 冒充 int、类型错误或负值时抛出。
    """

    value = _require_title_search_field(payload, field=field, context=context)
    if isinstance(value, bool) or not isinstance(value, int):
        raise HkexnewsProviderProtocolError
    if value < 0:
        raise HkexnewsProviderProtocolError
    return value


def _require_title_search_rows(
    payload: dict[str, JsonValue],
    *,
    context: str,
) -> tuple[dict[str, JsonValue], ...]:
    """读取 title search 字符串化 JSON object list。

    Args:
        payload: title search 顶层 object。
        context: 业务可读查询上下文。

    Returns:
        严格解码后的 row object tuple。

    Raises:
        HkexnewsProviderProtocolError: ``result`` 缺失、非字符串、空值、非法 JSON、
            解码后非 list 或包含非 object row 时抛出。
    """

    value = _require_title_search_field(
        payload,
        field=_HKEXNEWS_FIELD_RESULT,
        context=context,
    )
    if not isinstance(value, str) or not value.strip():
        raise HkexnewsProviderProtocolError
    try:
        decoded = cast(JsonValue, json.loads(value))
    except json.JSONDecodeError as exc:
        raise HkexnewsProviderProtocolError from exc
    if not isinstance(decoded, list):
        raise HkexnewsProviderProtocolError
    rows: list[dict[str, JsonValue]] = []
    for row in decoded:
        if not isinstance(row, dict):
            raise HkexnewsProviderProtocolError
        rows.append(row)
    return tuple(rows)


def _require_title_search_field(
    payload: dict[str, JsonValue],
    *,
    field: str,
    context: str,
) -> JsonValue:
    """读取 title search 必填字段。

    Args:
        payload: title search 顶层 object。
        field: 官方字段名。
        context: 业务可读查询上下文。

    Returns:
        字段的原始 JSON 值。

    Raises:
        HkexnewsProviderProtocolError: 字段缺失时抛出。
    """

    if field not in payload:
        raise HkexnewsProviderProtocolError
    return payload[field]


def _parse_embedded_json_list(raw: str) -> list[JsonValue] | None:
    """解析披露易 ``result`` 字符串 JSON。

    Args:
        raw: 字符串 JSON，常见值为 ``"[]"`` 或 ``"[{...}]"``。

    Returns:
        列表 JSON；不是列表或无法解析时返回 ``None``。

    Raises:
        无。
    """

    text = raw.strip()
    if text in {"", "null"}:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, list):
        return cast(list[JsonValue], parsed)
    return None


def _parse_stock_mapping_entry(raw: JsonValue) -> _HkStockMappingEntry | None:
    """解析 stock list 单行。

    Args:
        raw: JSON 行。

    Returns:
        股票映射；关键字段缺失时返回 ``None``。

    Raises:
        ValueError: 股票代码字段存在但格式非法时抛出。
    """

    if not isinstance(raw, dict):
        return None
    code = _first_text(raw, ("stockCode", "STOCK_CODE", "stock_code", "code", "CODE", "c"))
    stock_id = _first_text(raw, ("stockId", "STOCK_ID", "stock_id", "id", "ID", "i"))
    name = _first_text(raw, ("stockName", "STOCK_NAME", "name", "NAME", "longName", "n"))
    if code is None or stock_id is None:
        return None
    normalized_code = _to_hkex_stock_code(code)
    return _HkStockMappingEntry(
        stock_code=normalized_code,
        stock_id=stock_id,
        company_name=_strip_html(name or normalized_code),
    )


def _parse_announcement(
    raw: JsonValue,
    *,
    language: CnLanguage,
) -> HkexnewsRawAnnouncement | None:
    """解析 title search 单行公告。

    Args:
        raw: JSON 行。
        language: 当前查询语言。

    Returns:
        公告对象；关键字段缺失时返回 ``None``。

    Raises:
        无。
    """

    if not isinstance(raw, dict):
        return None
    file_type = _first_text(raw, ("FILE_TYPE", "fileType", "file_type"))
    if file_type is not None and file_type.upper() != _HKEXNEWS_FILE_TYPE_PDF:
        return None
    document_id = _first_text(
        raw,
        ("NEWS_ID", "newsId", "DOC_ID", "docID", "documentId", "id", "SEQUENCE"),
    )
    title = _first_text(raw, ("TITLE", "title", "LONG_TEXT", "longText"))
    file_link = _first_text(raw, ("FILE_LINK", "fileLink", "url"))
    stock_code_payload = _first_text(raw, ("STOCK_CODE", "stockCode", "stock_code"))
    category_text = _first_text(raw, ("LONG_TEXT", "longText", "SHORT_TEXT", "shortText"))
    raw_date = _first_text(raw, ("DATE_TIME", "RELEASE_TIME", "dateTime", "releaseTime"))
    filing_date = _parse_filing_date(raw_date)
    if document_id is None and file_link is not None:
        document_id = _stable_id_from_url(file_link)
    if document_id is None or title is None or file_link is None or stock_code_payload is None or filing_date is None:
        return None
    return HkexnewsRawAnnouncement(
        document_id=document_id,
        title=_strip_html(title),
        source_url=_build_absolute_file_url(file_link),
        stock_code_payload=stock_code_payload,
        category_text=_strip_html(category_text or ""),
        filing_date=filing_date,
        language=language,
    )


def _first_text(data: dict[str, JsonValue], keys: tuple[str, ...]) -> str | None:
    """按 key 顺序读取首个非空文本。

    Args:
        data: JSON dict。
        keys: 备选 key。

    Returns:
        非空文本；不存在时返回 ``None``。

    Raises:
        无。
    """

    for key in keys:
        value = data.get(key)
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text:
                return text
    return None


def _to_hkex_stock_code(raw: str) -> str:
    """把 HK canonical ticker 转成披露易 5 位 STOCK_CODE。

    Args:
        raw: 原始 ticker 或 stock code，如 ``0700``、``00700``、``700.HK``。

    Returns:
        5 位股票代码。

    Raises:
        ValueError: 输入缺少数字或位数非法时抛出。
    """

    digits = re.sub(r"\D", "", raw.strip())
    if not digits:
        raise ValueError(f"HK ticker 缺少数字: {raw!r}")
    if raw.strip().upper().endswith(".HK") and len(digits) > 5:
        digits = digits[:-2]
    if len(digits) <= 4:
        return digits.zfill(5)
    if len(digits) == 5:
        return digits
    raise ValueError(f"HK ticker 位数非法: {raw!r}")


def _announcement_matches_stock(stock_code_payload: str, target_stock_code: str) -> bool:
    """判断 ``STOCK_CODE`` 多代码字段是否包含目标股票。

    Args:
        stock_code_payload: 披露易 ``STOCK_CODE`` 字段。
        target_stock_code: 目标 5 位股票代码。

    Returns:
        命中返回 ``True``。

    Raises:
        无。
    """

    tokens = _split_stock_code_tokens(stock_code_payload)
    return target_stock_code in tokens


def _split_stock_code_tokens(stock_code_payload: str) -> set[str]:
    """拆分披露易 ``STOCK_CODE`` 多代码字段。

    Args:
        stock_code_payload: 原始多代码字段，可含 ``<br/>``。

    Returns:
        5 位股票代码集合。

    Raises:
        无。
    """

    text = _BR_PATTERN.sub(",", stock_code_payload)
    text = _TAG_PATTERN.sub("", text)
    tokens: set[str] = set()
    for raw in re.split(r"[,;，\s]+", text):
        digits = re.sub(r"\D", "", raw)
        if not digits:
            continue
        if len(digits) <= 4:
            tokens.add(digits.zfill(5))
        elif len(digits) == 5:
            tokens.add(digits)
    return tokens


def _build_absolute_file_url(file_link: str) -> str:
    """把 ``FILE_LINK`` 拼成绝对 URL。

    Args:
        file_link: 相对或绝对文件链接。

    Returns:
        绝对 URL。

    Raises:
        无。
    """

    text = file_link.strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if text.startswith("/"):
        return f"{HKEXNEWS_BASE_URL}{text}"
    return f"{HKEXNEWS_BASE_URL}/{text}"


def _parse_filing_date(raw_date: str | None) -> str | None:
    """解析披露日期为 ``YYYY-MM-DD``。

    Args:
        raw_date: 原始披露日期。

    Returns:
        规范日期；无法解析返回 ``None``。

    Raises:
        无。
    """

    if raw_date is None:
        return None
    matched = _DATE_PATTERN.search(raw_date)
    if matched is not None:
        year = int(matched.group("year"))
        month = int(matched.group("month"))
        day = int(matched.group("day"))
        return f"{year:04d}-{month:02d}-{day:02d}"
    slash_parts = raw_date.strip().split("/")
    if len(slash_parts) >= 3 and all(part.isdigit() for part in slash_parts[:3]):
        day = int(slash_parts[0])
        month = int(slash_parts[1])
        year = int(slash_parts[2])
        if year >= 1900:
            return f"{year:04d}-{month:02d}-{day:02d}"
    slash_time_parts = raw_date.strip().split()
    if slash_time_parts:
        slash_parts = slash_time_parts[0].split("/")
        if len(slash_parts) == 3 and all(part.isdigit() for part in slash_parts):
            day = int(slash_parts[0])
            month = int(slash_parts[1])
            year = int(slash_parts[2])
            if year >= 1900:
                return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def _language_param(language: CnLanguage) -> str:
    """把候选语言转换为披露易 lang 参数。

    Args:
        language: 语言字面量。

    Returns:
        披露易参数值。

    Raises:
        无。
    """

    return "zh" if language == "zh" else "E"


def _strip_html(raw: str) -> str:
    """清洗 HTML 标签与多余空白。

    Args:
        raw: 原始文本。

    Returns:
        清洗后的文本。

    Raises:
        无。
    """

    unescaped = html.unescape(raw)
    without_br = _BR_PATTERN.sub(" ", unescaped)
    without_tags = _TAG_PATTERN.sub("", without_br)
    return " ".join(without_tags.split())


def _stable_id_from_url(file_link: str) -> str:
    """从 URL 派生稳定 source id。

    Args:
        file_link: 文件链接。

    Returns:
        ``sha256`` 前 16 位。

    Raises:
        无。
    """

    return hashlib.sha256(file_link.encode("utf-8")).hexdigest()[:16]


def _utc_now_isoformat() -> str:
    """生成 ISO-8601 UTC 时间戳。

    Args:
        无。

    Returns:
        UTC 时间戳。

    Raises:
        无。
    """

    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


__all__ = [
    "HKEXNEWS_ACTIVE_STOCK_ZH_URL",
    "HKEXNEWS_BASE_URL",
    "HKEXNEWS_INACTIVE_STOCK_ZH_URL",
    "HKEXNEWS_TITLE_SEARCH_URL",
    "HkexnewsDiscoveryClient",
]
