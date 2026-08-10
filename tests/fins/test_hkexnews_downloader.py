"""``dayu/fins/downloaders/hkexnews_downloader.py`` 单元测试。

覆盖披露易 stock list 解析、title search 参数、语言策略、多代码匹配、
季度空结果、Q2/Q4 独立识别与 PDF 校验。所有测试都通过 ``httpx.MockTransport`` 注入 fixture，
禁止访问真实披露易网络。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn, TypeAlias, cast
from urllib.parse import parse_qs

import httpx
import pytest

from dayu.fins.download_contract import (
    FinsDownloadProviderError,
    FinsDownloadSource,
    FinsDownloadTransportCategory,
)
from dayu.fins.downloaders import hkexnews_downloader as _hkexnews_downloader
from dayu.fins.downloaders.hkexnews_downloader import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_SLEEP_SECONDS,
    DEFAULT_USER_AGENT,
    HKEXNEWS_ACTIVE_STOCK_ZH_URL,
    HKEXNEWS_BASE_URL,
    HKEXNEWS_INACTIVE_STOCK_ZH_URL,
    HKEXNEWS_TITLE_SEARCH_URL,
    HkexnewsDiscoveryClient,
    HkexnewsProviderProtocolError,
)
from dayu.fins.pipelines.cn_download_models import (
    CnCompanyProfile,
    CnDownloadCancelledError,
    CnFiscalPeriod,
    CnLanguage,
    CnReportCandidate,
    CnReportQuery,
)

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

_PDF_URL = f"{HKEXNEWS_BASE_URL}/listedco/listconews/sehk/2025/0401/2025040100001.pdf"


@dataclass
class _RecordingCheckpoint:
    """记录 no-arg cancellation checkpoint 的精确调用顺序。"""

    events: list[str]
    errors_by_call: dict[int, RuntimeError] = field(default_factory=dict)
    call_count: int = 0

    def __call__(self) -> None:
        """记录一次调用，并在配置的序号抛出指定异常。

        Args:
            无。

        Returns:
            无。

        Raises:
            RuntimeError: 当前调用序号配置了异常时原样抛出。
        """

        self.call_count += 1
        self.events.append(f"CP{self.call_count}")
        error = self.errors_by_call.get(self.call_count)
        if error is not None:
            raise error


def test_hkexnews_default_user_agent_and_rate_limit_constants_are_explicit() -> None:
    """默认 UA、限流间隔和重试次数应由 typed 常量显式承载。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    assert DEFAULT_USER_AGENT == "DayuAgent/1.0 (+hk-download)"
    assert DEFAULT_SLEEP_SECONDS == 0.3
    assert DEFAULT_MAX_RETRIES == 3


def _build_pdf_payload(size: int = 4096, marker: bytes = b"%PDF-1.7\n") -> bytes:
    """构造测试 PDF 字节。

    Args:
        size: 字节数。
        marker: 文件前缀。

    Returns:
        PDF 字节。

    Raises:
        无。
    """

    return marker + b"0" * (size - len(marker))


def _stock_mapping_payload() -> dict[str, list[dict[str, str]]]:
    """构造披露易 stock list fixture。

    Args:
        无。

    Returns:
        stock list JSON。

    Raises:
        无。
    """

    return {
        "stockInfo": [
            {"c": "00700", "i": "7609", "n": "腾讯控股"},
            {"c": "00005", "i": "5", "n": "汇丰控股"},
        ]
    }


def _empty_stock_mapping_payload() -> dict[str, list[dict[str, str]]]:
    """构造空 stock list fixture。

    Args:
        无。

    Returns:
        空 stock list JSON。

    Raises:
        无。
    """

    return {"stockInfo": []}


def _inactive_duplicate_stock_mapping_payload() -> dict[str, list[dict[str, str]]]:
    """构造含历史重复代码的 inactive stock list fixture。

    Args:
        无。

    Returns:
        inactive stock list JSON。

    Raises:
        无。
    """

    return {"stockInfo": [{"c": "00700", "i": "1639", "n": "八佰伴國際"}]}


def _announcement(
    *,
    document_id: str,
    title: str,
    file_link: str = "/listedco/listconews/sehk/2025/0401/2025040100001.pdf",
    stock_code: str = "00700<br/>80700",
    date_time: str = "01/04/2025 16:30",
    category_text: str = "Financial Statements/ESG Information - [Annual Report]",
) -> dict[str, str]:
    """构造 title search 单条公告 fixture。

    Args:
        document_id: 披露易文档 ID。
        title: 公告标题。
        file_link: PDF 链接。
        stock_code: ``STOCK_CODE`` 字段。
        date_time: 披露时间。
        category_text: 披露易分类文本。

    Returns:
        公告 JSON dict。

    Raises:
        无。
    """

    return {
        "NEWS_ID": document_id,
        "TITLE": title,
        "FILE_LINK": file_link,
        "STOCK_CODE": stock_code,
        "DATE_TIME": date_time,
        "FILE_TYPE": "PDF",
        "LONG_TEXT": category_text,
    }


def _announcement_rows(
    count: int,
    *,
    prefix: str,
    title_year: int = 2024,
) -> list[dict[str, str]]:
    """构造可区分来源的累计公告行。

    Args:
        count: 公告行数。
        prefix: document/file 识别前缀。
        title_year: 标题内的财年。

    Returns:
        公告 row list。

    Raises:
        无。
    """

    return [
        _announcement(
            document_id=f"{prefix}_{index}",
            title=f"腾讯控股有限公司：{title_year}年年度报告 {prefix} {index}",
            file_link=(f"/listedco/listconews/sehk/2025/0401/{prefix.lower()}_{index}.pdf"),
        )
        for index in range(count)
    ]


def _query_from_request(request: httpx.Request) -> dict[str, tuple[str, ...]]:
    """解析 GET query 参数。

    Args:
        request: HTTP 请求。

    Returns:
        字段名到值 tuple 的映射。

    Raises:
        无。
    """

    parsed = parse_qs(str(request.url).split("?", 1)[1] if "?" in str(request.url) else "")
    return {key: tuple(values) for key, values in parsed.items()}


def _title_search_payload(
    rows: list[dict[str, str]],
    *,
    row_range: int = 100,
    has_next_row: bool = False,
    loaded_record: int | None = None,
    record_count: int | None = None,
) -> dict[str, JsonValue]:
    """构造披露易 title search 响应。

    Args:
        rows: 结果行。
        row_range: provider 回显的当轮累计 range。
        has_next_row: provider 是否声明还有后续记录。
        loaded_record: provider 声明的已加载记录数；默认等于行数。
        record_count: provider 声明的最新总数；默认等于已加载数。

    Returns:
        ``result`` 为字符串 JSON 的响应 dict。

    Raises:
        无。
    """

    effective_loaded_record = len(rows) if loaded_record is None else loaded_record
    effective_record_count = effective_loaded_record if record_count is None else record_count
    return {
        "hasNextRow": has_next_row,
        "rowRange": row_range,
        "loadedRecord": effective_loaded_record,
        "recordCnt": effective_record_count,
        "result": json.dumps(rows, ensure_ascii=False),
    }


def _build_http_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.Client:
    """构造 MockTransport HTTP client。

    Args:
        handler: 请求处理函数。

    Returns:
        HTTP client。

    Raises:
        无。
    """

    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


def _build_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> HkexnewsDiscoveryClient:
    """构造测试用披露易客户端。

    Args:
        handler: 请求处理函数。

    Returns:
        披露易 downloader。

    Raises:
        无。
    """

    return HkexnewsDiscoveryClient(
        client=_build_http_client(handler),
        sleep_seconds=0.0,
        max_retries=2,
        sleep_func=lambda _delay: None,
    )


def _query(
    *,
    ticker: str = "0700",
    periods: tuple[CnFiscalPeriod, ...] = ("FY",),
) -> CnReportQuery:
    """构造 HK 查询对象。

    Args:
        ticker: ticker。
        periods: 财期 tuple。

    Returns:
        查询对象。

    Raises:
        无。
    """

    return CnReportQuery(
        market="HK",
        normalized_ticker=ticker,
        start_date="2024-01-01",
        end_date="2026-12-31",
        discovery_periods=periods,
    )


def _profile(ticker: str = "0700") -> CnCompanyProfile:
    """构造 HK 公司元数据。

    Args:
        ticker: ticker。

    Returns:
        公司元数据。

    Raises:
        无。
    """

    return CnCompanyProfile(
        provider="hkexnews",
        company_id="HKEX:7609",
        company_name="腾讯控股",
        ticker=ticker,
    )


def test_resolve_company_parses_active_stock_list_and_normalizes_ticker() -> None:
    """验证 ``0700/00700/700.HK`` 都能命中 5 位 stock code。"""

    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if str(request.url) == HKEXNEWS_ACTIVE_STOCK_ZH_URL:
            return httpx.Response(200, json=_stock_mapping_payload())
        if str(request.url) == HKEXNEWS_INACTIVE_STOCK_ZH_URL:
            return httpx.Response(200, json=_inactive_duplicate_stock_mapping_payload())
        raise AssertionError(f"unexpected url {request.url}")

    client = _build_client(handler)

    for ticker in ("0700", "00700", "700.HK"):
        profile = client.resolve_company(_query(ticker=ticker))
        assert profile == CnCompanyProfile(
            provider="hkexnews",
            company_id="HKEX:7609",
            company_name="腾讯控股",
            ticker=ticker,
        )

    assert requested_urls == [
        HKEXNEWS_ACTIVE_STOCK_ZH_URL,
        HKEXNEWS_INACTIVE_STOCK_ZH_URL,
    ]


def test_resolve_company_rejects_non_hk_market() -> None:
    """``market != HK`` 时立即拒绝。"""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_empty_stock_mapping_payload())

    client = _build_client(handler)
    with pytest.raises(ValueError):
        client.resolve_company(
            CnReportQuery(
                market="CN",
                normalized_ticker="0700",
                start_date="2024-01-01",
                end_date="2026-12-31",
                discovery_periods=("FY",),
            )
        )


def test_list_report_candidates_gets_title_search_and_builds_absolute_url() -> None:
    """验证 title search GET 参数、``FILE_LINK`` 绝对 URL 与多代码过滤。"""

    posted_forms: list[dict[str, tuple[str, ...]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL) and request.method == "GET":
            form = _query_from_request(request)
            posted_forms.append(form)
            if form["lang"] == ("zh",):
                return httpx.Response(
                    200,
                    json=_title_search_payload(
                        [
                            _announcement(
                                document_id="DOC1",
                                title="腾讯控股有限公司：2024年年度报告",
                            ),
                            _announcement(
                                document_id="DOC2",
                                title="汇丰控股有限公司：2024年年度报告",
                                stock_code="00005",
                            ),
                        ]
                    ),
                )
            return httpx.Response(
                200,
                json=_title_search_payload(
                    [
                        _announcement(
                            document_id="DOC1_EN",
                            title="Tencent Holdings Limited: 2024 Annual Report",
                        )
                    ]
                ),
            )
        if str(request.url) == _PDF_URL and request.method == "HEAD":
            return httpx.Response(
                200,
                headers={
                    "Content-Length": "4096",
                    "ETag": '"hk-v1"',
                    "Last-Modified": "Tue, 01 Apr 2025 00:00:00 GMT",
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = _build_client(handler)
    candidates = client.list_report_candidates(_query(), _profile())

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.provider == "hkexnews"
    assert candidate.source_id == "DOC1"
    assert candidate.source_url == _PDF_URL
    assert candidate.language == "zh"
    assert candidate.fiscal_year == 2024
    assert candidate.fiscal_period == "FY"
    assert candidate.content_length == 4096
    assert candidate.etag == '"hk-v1"'
    assert candidate.last_modified == "Tue, 01 Apr 2025 00:00:00 GMT"
    assert posted_forms[0]["stockId"] == ("7609",)
    assert posted_forms[0]["searchType"] == ("1",)
    assert posted_forms[0]["t1code"] == ("40000",)
    assert posted_forms[0]["t2Gcode"] == ("-2",)
    assert posted_forms[0]["t2code"] == ("40100",)
    assert posted_forms[0]["fromDate"] == ("20240101",)
    assert posted_forms[0]["toDate"] == ("20261231",)


def test_list_report_candidates_accepts_exact_100_complete_with_ordered_checkpoint() -> None:
    """官方字段证明完整时，首轮恰好 100 条应正常返回。"""

    events: list[str] = []
    checkpoint = _RecordingCheckpoint(events)

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL):
            events.append("GET(100)")
            rows = _announcement_rows(100, prefix="EXACT")
            return httpx.Response(200, json=_title_search_payload(rows))
        if request.method == "HEAD":
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    candidates = _build_client(handler).list_report_candidates(
        _query(),
        _profile(),
        cancellation_checkpoint=checkpoint,
    )

    assert events[:3] == ["CP1", "GET(100)", "CP2"]
    assert checkpoint.call_count == 2
    assert len(candidates) == 1


def test_list_report_candidates_fetches_two_round_cumulative_snapshot_with_invariant_query() -> None:
    """两轮累计续取应只改 ``rowRange`` 并仅消费最终快照。"""

    events: list[str] = []
    checkpoint = _RecordingCheckpoint(events)
    requested: list[dict[str, tuple[str, ...]]] = []
    final_rows = _announcement_rows(150, prefix="FINAL")

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL):
            params = _query_from_request(request)
            requested.append(params)
            row_range = int(params["rowRange"][0])
            events.append(f"GET({row_range})")
            if row_range == 100:
                return httpx.Response(
                    200,
                    json=_title_search_payload(
                        _announcement_rows(100, prefix="FIRST"),
                        has_next_row=True,
                        record_count=150,
                    ),
                )
            assert row_range == 200
            return httpx.Response(
                200,
                json=_title_search_payload(final_rows, row_range=200),
            )
        if request.method == "HEAD":
            assert "first_" not in str(request.url)
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    candidates = _build_client(handler).list_report_candidates(
        _query(),
        _profile(),
        cancellation_checkpoint=checkpoint,
    )

    assert events[:6] == ["CP1", "GET(100)", "CP2", "CP3", "GET(200)", "CP4"]
    assert [params["rowRange"] for params in requested] == [("100",), ("200",)]
    without_range = [{key: value for key, value in params.items() if key != "rowRange"} for params in requested]
    assert without_range[0] == without_range[1]
    assert len(candidates) == 1
    assert candidates[0].source_id.startswith("FINAL_")


def test_list_report_candidates_uses_latest_record_count_for_next_range_and_growth() -> None:
    """每轮应使用最新 ``recordCnt`` 按公式扩大累计 range。"""

    ranges: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL):
            row_range = int(_query_from_request(request)["rowRange"][0])
            ranges.append(row_range)
            if row_range == 100:
                return httpx.Response(
                    200,
                    json=_title_search_payload(
                        _announcement_rows(100, prefix="GROW1"),
                        has_next_row=True,
                        record_count=150,
                    ),
                )
            if row_range == 200:
                return httpx.Response(
                    200,
                    json=_title_search_payload(
                        _announcement_rows(200, prefix="GROW2"),
                        row_range=200,
                        has_next_row=True,
                        record_count=350,
                    ),
                )
            assert row_range == 400
            return httpx.Response(
                200,
                json=_title_search_payload(
                    _announcement_rows(350, prefix="GROW3"),
                    row_range=400,
                ),
            )
        if request.method == "HEAD":
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    candidates = _build_client(handler).list_report_candidates(_query(), _profile())

    assert ranges == [100, 200, 400]
    assert len(candidates) == 1
    assert candidates[0].source_id.startswith("GROW3_")


def test_list_report_candidates_uses_record_count_when_larger_than_doubled_range() -> None:
    """最新总数大于翻倍值时，下轮 range 应精确取 ``recordCnt``。"""

    ranges: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL):
            row_range = int(_query_from_request(request)["rowRange"][0])
            ranges.append(row_range)
            if row_range == 100:
                return httpx.Response(
                    200,
                    json=_title_search_payload(
                        _announcement_rows(100, prefix="FORMULA1"),
                        has_next_row=True,
                        record_count=350,
                    ),
                )
            assert row_range == 350
            return httpx.Response(
                200,
                json=_title_search_payload(
                    _announcement_rows(350, prefix="FORMULA2"),
                    row_range=350,
                ),
            )
        if request.method == "HEAD":
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    _build_client(handler).list_report_candidates(_query(), _profile())

    assert ranges == [100, 350]


def test_list_report_candidates_replaces_overlapping_snapshot_and_accepts_terminal_shrink() -> None:
    """最终自洽快照应优先于历史进度，不 append 或推测 prefix。"""

    head_urls: list[str] = []
    first = _announcement_rows(1, prefix="FIRST_ONLY")
    final = _announcement_rows(1, prefix="FINAL_ONLY")

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL):
            row_range = int(_query_from_request(request)["rowRange"][0])
            if row_range == 100:
                return httpx.Response(
                    200,
                    json=_title_search_payload(
                        first,
                        has_next_row=True,
                        record_count=2,
                    ),
                )
            return httpx.Response(
                200,
                json=_title_search_payload(final, row_range=200),
            )
        if request.method == "HEAD":
            head_urls.append(str(request.url))
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    candidates = _build_client(handler).list_report_candidates(_query(), _profile())

    assert [candidate.source_id for candidate in candidates] == ["FINAL_ONLY_0"]
    assert len(head_urls) == 1
    assert "final_only_0.pdf" in head_urls[0]


def test_list_report_candidates_rejects_continuation_without_loaded_progress() -> None:
    """续取后 loaded rows 不增加时应有限 typed fail 且不做 HEAD。"""

    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL):
            request_count += 1
            row_range = int(_query_from_request(request)["rowRange"][0])
            return httpx.Response(
                200,
                json=_title_search_payload(
                    _announcement_rows(1, prefix="STALL"),
                    row_range=row_range,
                    has_next_row=True,
                    record_count=2 if row_range == 100 else 3,
                ),
            )
        raise AssertionError("no HEAD or additional request is allowed")

    with pytest.raises(HkexnewsProviderProtocolError) as exc_info:
        _build_client(handler).list_report_candidates(_query(), _profile())

    assert exc_info.value.transport_category is FinsDownloadTransportCategory.PROTOCOL
    assert exc_info.value.retryable is False
    assert request_count == 2


@pytest.mark.parametrize(
    "missing_field",
    ["hasNextRow", "rowRange", "loadedRecord", "recordCnt", "result"],
)
def test_list_report_candidates_requires_all_official_fields(missing_field: str) -> None:
    """五个官方协议字段任一缺失都应 typed fail。"""

    payload = _title_search_payload([])
    del payload[missing_field]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(HkexnewsProviderProtocolError):
        _build_client(handler).list_report_candidates(_query(), _profile())


@pytest.mark.parametrize("invalid_value", ["true", 1, None, [], {}])
def test_list_report_candidates_requires_exact_has_next_bool(invalid_value: JsonValue) -> None:
    """``hasNextRow`` 只接受 JSON bool。"""

    payload = _title_search_payload([])
    payload["hasNextRow"] = invalid_value

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(HkexnewsProviderProtocolError):
        _build_client(handler).list_report_candidates(_query(), _profile())


@pytest.mark.parametrize("field_name", ["rowRange", "loadedRecord", "recordCnt"])
@pytest.mark.parametrize("invalid_value", ["0", True, 0.0, 0.5, None, []])
def test_list_report_candidates_requires_exact_count_ints(
    field_name: str,
    invalid_value: JsonValue,
) -> None:
    """三个 range/count 字段只接受非负 exact int，bool 不得冒充。"""

    payload = _title_search_payload([])
    payload[field_name] = invalid_value

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(HkexnewsProviderProtocolError):
        _build_client(handler).list_report_candidates(_query(), _profile())


@pytest.mark.parametrize("field_name", ["rowRange", "loadedRecord", "recordCnt"])
def test_list_report_candidates_rejects_negative_count_fields(field_name: str) -> None:
    """三个 range/count 字段的负值均应 typed fail。"""

    payload = _title_search_payload([])
    payload[field_name] = -1

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(HkexnewsProviderProtocolError):
        _build_client(handler).list_report_candidates(_query(), _profile())


@pytest.mark.parametrize("invalid_result", [[], "", "{", "{}", "[1]"])
def test_list_report_candidates_requires_stringified_object_list(
    invalid_result: JsonValue,
) -> None:
    """``result`` 必须是字符串化 JSON object list，不回退 generic aliases。"""

    payload = _title_search_payload([])
    payload["result"] = invalid_result

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(HkexnewsProviderProtocolError):
        _build_client(handler).list_report_candidates(_query(), _profile())


@pytest.mark.parametrize(
    "payload",
    [
        _title_search_payload([], row_range=99),
        _title_search_payload(_announcement_rows(1, prefix="MISMATCH"), loaded_record=0),
        _title_search_payload(_announcement_rows(2, prefix="COUNT"), record_count=1),
        _title_search_payload(_announcement_rows(101, prefix="RANGE")),
        _title_search_payload(
            _announcement_rows(1, prefix="TRUE_COMPLETE"),
            has_next_row=True,
        ),
        _title_search_payload(
            _announcement_rows(1, prefix="FALSE_PARTIAL"),
            record_count=2,
        ),
    ],
)
def test_list_report_candidates_rejects_same_round_contradictions(
    payload: dict[str, JsonValue],
) -> None:
    """响应 range/loaded/count/rows/terminal 事实矛盾时均应 typed fail。"""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(HkexnewsProviderProtocolError):
        _build_client(handler).list_report_candidates(_query(), _profile())


@pytest.mark.parametrize(
    ("cancel_call", "first_has_next", "expected_events"),
    [
        (1, False, ["CP1"]),
        (2, False, ["CP1", "GET(100)", "CP2"]),
        (3, True, ["CP1", "GET(100)", "CP2", "CP3"]),
    ],
)
def test_list_report_candidates_preserves_cancel_identity_and_suppresses_publication(
    cancel_call: int,
    first_has_next: bool,
    expected_events: list[str],
) -> None:
    """首请求前、响应后或下轮前取消都应保持 identity 且零发布。"""

    events: list[str] = []
    expected = CnDownloadCancelledError(f"cancel at checkpoint {cancel_call}")
    checkpoint = _RecordingCheckpoint(events, errors_by_call={cancel_call: expected})
    head_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal head_count
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL):
            row_range = int(_query_from_request(request)["rowRange"][0])
            events.append(f"GET({row_range})")
            return httpx.Response(
                200,
                json=_title_search_payload(
                    _announcement_rows(1, prefix="PARTIAL"),
                    has_next_row=first_has_next,
                    record_count=2 if first_has_next else 1,
                ),
            )
        if request.method == "HEAD":
            head_count += 1
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    with pytest.raises(CnDownloadCancelledError) as exc_info:
        _build_client(handler).list_report_candidates(
            _query(),
            _profile(),
            cancellation_checkpoint=checkpoint,
        )

    assert exc_info.value is expected
    assert events == expected_events
    assert head_count == 0


def test_list_report_candidates_preserves_non_cancel_failure_identity() -> None:
    """workflow checkpoint 非取消失败应原样传播且零 HTTP。"""

    original = ValueError("checker exploded")
    request_count = 0

    expected = RuntimeError("取消检查失败")
    expected.__cause__ = original

    def checkpoint() -> None:
        raise expected

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json=_title_search_payload([]))

    with pytest.raises(RuntimeError) as exc_info:
        _build_client(handler).list_report_candidates(
            _query(),
            _profile(),
            cancellation_checkpoint=checkpoint,
        )

    assert type(exc_info.value) is RuntimeError
    assert exc_info.value is expected
    assert exc_info.value.__cause__ is original
    assert request_count == 0


def test_list_report_candidates_preserves_provider_protocol_error_and_direct_cause() -> None:
    """provider typed error 应在 generic wrapper 前原类型传播并保留 parser cause。"""

    payload = _title_search_payload([])
    payload["result"] = "{"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    with pytest.raises(HkexnewsProviderProtocolError) as exc_info:
        _build_client(handler).list_report_candidates(_query(), _profile())

    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


def test_list_report_candidates_preserves_provider_protocol_object_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """预构造 provider protocol error 经 public generic wrapper 边界应保持 identity/cause。"""

    original = ValueError("provider parser cause")
    expected = HkexnewsProviderProtocolError()
    expected.__cause__ = original

    def raise_expected(
        payload: JsonValue,
        *,
        requested_row_range: int,
        stock_code: str,
        category_spec: _hkexnews_downloader._HkCategorySpec,
        language: CnLanguage,
    ) -> NoReturn:
        del payload, requested_row_range, stock_code, category_spec, language
        raise expected

    monkeypatch.setattr(
        _hkexnews_downloader,
        "_parse_title_search_snapshot",
        raise_expected,
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_title_search_payload([]))

    with pytest.raises(HkexnewsProviderProtocolError) as exc_info:
        _build_client(handler).list_report_candidates(_query(), _profile())

    assert exc_info.value is expected
    assert exc_info.value.__cause__ is original


def test_list_report_candidates_discards_partial_rows_when_later_http_fails() -> None:
    """后续累计 GET 重试耗尽时不得返回首轮 partial 或发起 HEAD。"""

    title_gets = 0
    head_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal title_gets, head_count
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL):
            title_gets += 1
            row_range = int(_query_from_request(request)["rowRange"][0])
            if row_range == 100:
                return httpx.Response(
                    200,
                    json=_title_search_payload(
                        _announcement_rows(1, prefix="HTTP_PARTIAL"),
                        has_next_row=True,
                        record_count=2,
                    ),
                )
            return httpx.Response(503)
        if request.method == "HEAD":
            head_count += 1
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    with pytest.raises(FinsDownloadProviderError) as exc_info:
        _build_client(handler).list_report_candidates(_query(), _profile())

    assert exc_info.value.source is FinsDownloadSource.HKEXNEWS
    assert exc_info.value.transport_category is FinsDownloadTransportCategory.HTTP_STATUS
    assert exc_info.value.retryable is True
    assert title_gets == 3
    assert head_count == 0


def test_list_report_candidates_keeps_cumulative_state_isolated_per_language() -> None:
    """不同语言查询应各自从 100 开始并保持自身查询不变式。"""

    ranges_by_language: dict[str, list[int]] = {"zh": [], "E": []}

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL):
            params = _query_from_request(request)
            language = params["lang"][0]
            row_range = int(params["rowRange"][0])
            ranges_by_language[language].append(row_range)
            if row_range == 100:
                return httpx.Response(
                    200,
                    json=_title_search_payload(
                        _announcement_rows(1, prefix=f"{language}_FIRST"),
                        has_next_row=True,
                        record_count=2,
                    ),
                )
            return httpx.Response(
                200,
                json=_title_search_payload(
                    _announcement_rows(2, prefix=f"{language}_FINAL"),
                    row_range=200,
                ),
            )
        if request.method == "HEAD":
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = HkexnewsDiscoveryClient(
        client=_build_http_client(handler),
        languages=("zh", "en"),
        sleep_seconds=0.0,
        max_retries=2,
        sleep_func=lambda _delay: None,
    )
    client.list_report_candidates(_query(), _profile())

    assert ranges_by_language == {"zh": [100, 200], "E": [100, 200]}


def test_captured_official_title_search_shape_replays_through_strict_owner() -> None:
    """官方小响应 fixture 的 body hash、请求参数与 exact types 应可审计重放。"""

    fixture_path = Path(__file__).parent / "fixtures" / "hkexnews" / "title_search_protocol_shape.json"
    fixture = cast(JsonValue, json.loads(fixture_path.read_text(encoding="utf-8")))
    assert isinstance(fixture, dict)
    raw_body = fixture.get("raw_response_body")
    expected_hash = fixture.get("raw_response_body_sha256")
    request_params = fixture.get("request_params")
    raw_response = fixture.get("raw_json_response")
    assert isinstance(raw_body, str)
    assert isinstance(expected_hash, str)
    assert hashlib.sha256(raw_body.encode("utf-8")).hexdigest() == expected_hash
    assert isinstance(request_params, dict)
    assert isinstance(raw_response, dict)
    assert isinstance(raw_response.get("hasNextRow"), bool)
    for field_name in ("rowRange", "loadedRecord", "recordCnt"):
        field_value = raw_response.get(field_name)
        assert isinstance(field_value, int) and not isinstance(field_value, bool)
    assert isinstance(raw_response.get("result"), str)
    expected_query: dict[str, tuple[str, ...]] = {}
    for key, value in request_params.items():
        assert isinstance(value, str)
        expected_query[key] = (value,)

    def handler(request: httpx.Request) -> httpx.Response:
        assert _query_from_request(request) == expected_query
        return httpx.Response(200, json=raw_response)

    query = CnReportQuery(
        market="HK",
        normalized_ticker="0700",
        start_date="2026-07-15",
        end_date="2026-07-15",
        discovery_periods=("FY",),
    )

    assert _build_client(handler).list_report_candidates(query, _profile()) == ()


def test_list_report_candidates_does_not_use_english_fallback_when_primary_empty() -> None:
    """主语言为空时不再用英文补位，避免英文财报进入 CN/HK active。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL) and request.method == "GET":
            form = _query_from_request(request)
            if form["lang"] == ("zh",):
                return httpx.Response(200, json=_title_search_payload([]))
            return httpx.Response(
                200,
                json=_title_search_payload(
                    [
                        _announcement(
                            document_id="DOC_EN",
                            title="Tencent Holdings Limited: 2024 Annual Report",
                        )
                    ]
                ),
            )
        if str(request.url) == _PDF_URL and request.method == "HEAD":
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = _build_client(handler)
    candidates = client.list_report_candidates(_query(), _profile())

    assert candidates == ()


def test_list_report_candidates_filters_english_title_from_primary_language() -> None:
    """即使中文入口返回英文标题，也不得进入 HK active 候选。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL) and request.method == "GET":
            form = _query_from_request(request)
            if form["lang"] == ("E",):
                return httpx.Response(200, json=_title_search_payload([]))
            return httpx.Response(
                200,
                json=_title_search_payload(
                    [
                        _announcement(
                            document_id="DOC_EN_ON_ZH",
                            title="Tencent Holdings Limited: 2024 Annual Report",
                            category_text="Financial Statements/ESG Information - [Annual Report]",
                        )
                    ]
                ),
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = _build_client(handler)
    candidates = client.list_report_candidates(_query(), _profile())

    assert candidates == ()


def test_list_report_candidates_filters_english_title_with_chinese_category() -> None:
    """英文标题即使带中文分类文本，也不得进入 HK active 候选。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL) and request.method == "GET":
            form = _query_from_request(request)
            if form["lang"] == ("E",):
                return httpx.Response(200, json=_title_search_payload([]))
            return httpx.Response(
                200,
                json=_title_search_payload(
                    [
                        _announcement(
                            document_id="DOC_EN_ZH_CATEGORY",
                            title="Tencent Holdings Limited: 2024 Annual Report",
                            category_text="財務報表/環境、社會及管治資料 - [年報]",
                        )
                    ]
                ),
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = _build_client(handler)
    candidates = client.list_report_candidates(_query(), _profile())

    assert candidates == ()


def test_list_report_candidates_maps_hk_period_codes_and_allows_empty_quarters() -> None:
    """验证 FY/H1/Q1-Q4 标题分类映射；季度查无不抛异常。"""

    category_params: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL) and request.method == "GET":
            form = _query_from_request(request)
            category_params.append(
                (
                    form["t1code"][0],
                    form["t2Gcode"][0],
                    form["t2code"][0],
                )
            )
            return httpx.Response(200, json=_title_search_payload([]))
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = _build_client(handler)
    candidates = client.list_report_candidates(
        _query(periods=("FY", "H1", "Q1", "Q2", "Q3", "Q4")),
        _profile(),
    )

    assert candidates == ()
    assert category_params == [
        ("40000", "-2", "40100"),
        ("40000", "-2", "40200"),
        ("10000", "3", "13600"),
    ]


def test_list_report_candidates_raises_on_failed_hk_period_query() -> None:
    """单个披露易分类查询失败也必须抛错，不能伪装成该财期缺报告。"""

    h1_url = f"{HKEXNEWS_BASE_URL}/listedco/listconews/sehk/2025/0826/h1.pdf"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL) and request.method == "GET":
            form = _query_from_request(request)
            if form["t2code"] == ("40100",):
                return httpx.Response(503, json={"error": "temporarily unavailable"})
            if form["lang"] == ("E",):
                return httpx.Response(200, json=_title_search_payload([]))
            return httpx.Response(
                200,
                json=_title_search_payload(
                    [
                        _announcement(
                            document_id="H1_2025",
                            title="中期報告 2025",
                            file_link="/listedco/listconews/sehk/2025/0826/h1.pdf",
                            date_time="26/08/2025 16:30",
                            category_text="Financial Statements/ESG Information - [中期/半年度報告]",
                        )
                    ]
                ),
            )
        if str(request.url) == h1_url and request.method == "HEAD":
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = _build_client(handler)
    with pytest.raises(FinsDownloadProviderError) as exc_info:
        client.list_report_candidates(
            _query(periods=("FY", "H1")),
            _profile(),
        )

    assert exc_info.value.transport_category is FinsDownloadTransportCategory.HTTP_STATUS
    assert exc_info.value.retryable is True


def test_list_report_candidates_maps_direct_q2_to_quarterly_category() -> None:
    """直接传入 Q2 时应查询季度业绩分类，不应归入中期报告。"""

    q2_url = f"{HKEXNEWS_BASE_URL}/listedco/listconews/sehk/2025/0813/q2.pdf"
    seen_t2codes: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL) and request.method == "GET":
            form = _query_from_request(request)
            seen_t2codes.append(form["t2code"][0])
            if form["lang"] == ("E",):
                return httpx.Response(200, json=_title_search_payload([]))
            return httpx.Response(
                200,
                json=_title_search_payload(
                    [
                        _announcement(
                            document_id="Q2_2025",
                            title="截至二零二五年六月三十日止三個月及六個月業績公佈",
                            file_link="/listedco/listconews/sehk/2025/0813/q2.pdf",
                            date_time="13/08/2025 16:30",
                            category_text="公告及通告 - [季度業績]",
                        )
                    ]
                ),
            )
        if str(request.url) == q2_url and request.method == "HEAD":
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = _build_client(handler)
    candidates = client.list_report_candidates(
        _query(periods=("Q2",)),
        _profile(),
    )

    assert seen_t2codes == ["13600"]
    assert len(candidates) == 1
    assert candidates[0].source_id == "Q2_2025"
    assert candidates[0].fiscal_period == "Q2"


def test_list_report_candidates_keeps_q4_distinct_from_fy() -> None:
    """港股 Q4 与 FY 是独立报告，不能把季度业绩折叠成年报。"""

    q4_url = f"{HKEXNEWS_BASE_URL}/listedco/listconews/sehk/2026/0320/q4.pdf"
    fy_url = f"{HKEXNEWS_BASE_URL}/listedco/listconews/sehk/2026/0401/fy.pdf"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL) and request.method == "GET":
            form = _query_from_request(request)
            if form["lang"] == ("E",):
                return httpx.Response(200, json=_title_search_payload([]))
            if form["t2code"] == ("40100",):
                return httpx.Response(
                    200,
                    json=_title_search_payload(
                        [
                            _announcement(
                                document_id="FY_2025",
                                title="2025 年報",
                                file_link="/listedco/listconews/sehk/2026/0401/fy.pdf",
                                date_time="01/04/2026 16:30",
                                category_text="財務報表/環境、社會及管治資料 - [年報]",
                            )
                        ]
                    ),
                )
            return httpx.Response(
                200,
                json=_title_search_payload(
                    [
                        _announcement(
                            document_id="Q4_2025",
                            title="截至二零二五年十二月三十一日止三個月及十二個月業績公佈",
                            file_link="/listedco/listconews/sehk/2026/0320/q4.pdf",
                            date_time="20/03/2026 16:30",
                            category_text="公告及通告 - [季度業績]",
                        )
                    ]
                ),
            )
        if str(request.url) in {q4_url, fy_url} and request.method == "HEAD":
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = _build_client(handler)
    candidates = client.list_report_candidates(
        _query(periods=("FY", "Q4")),
        _profile(),
    )

    assert [(candidate.source_id, candidate.fiscal_period) for candidate in candidates] == [
        ("FY_2025", "FY"),
        ("Q4_2025", "Q4"),
    ]


def test_list_report_candidates_treats_traditional_half_year_as_h1() -> None:
    """真实繁体 ``中期/半年度報告`` 分类必须归入 H1 而非 FY。"""

    h1_url = f"{HKEXNEWS_BASE_URL}/listedco/listconews/sehk/2025/0826/h1.pdf"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL) and request.method == "GET":
            form = _query_from_request(request)
            if form["lang"] == ("E",):
                return httpx.Response(200, json=_title_search_payload([]))
            return httpx.Response(
                200,
                json=_title_search_payload(
                    [
                        _announcement(
                            document_id="H1_2025",
                            title="中期報告 2025",
                            file_link="/listedco/listconews/sehk/2025/0826/h1.pdf",
                            date_time="26/08/2025 16:30",
                            category_text="財務報表/環境、社會及管治資料 - [中期/半年度報告]",
                        ),
                    ]
                ),
            )
        if str(request.url) == h1_url and request.method == "HEAD":
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = _build_client(handler)
    candidates = client.list_report_candidates(
        _query(periods=("FY", "H1")),
        _profile(),
    )

    assert [(candidate.source_id, candidate.fiscal_period) for candidate in candidates] == [
        ("H1_2025", "H1"),
    ]


def test_list_report_candidates_filters_q1_q3_by_title_period() -> None:
    """同一季度业绩分类结果必须按标题区分 Q1/Q3，不能互相误标。"""

    first_quarter_url = f"{HKEXNEWS_BASE_URL}/listedco/listconews/sehk/2025/0420/q1.pdf"
    third_quarter_url = f"{HKEXNEWS_BASE_URL}/listedco/listconews/sehk/2025/1020/q3.pdf"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL) and request.method == "GET":
            form = _query_from_request(request)
            assert form["t1code"] == ("10000",)
            assert form["t2Gcode"] == ("3",)
            assert form["t2code"] == ("13600",)
            if form["lang"] == ("E",):
                return httpx.Response(200, json=_title_search_payload([]))
            return httpx.Response(
                200,
                json=_title_search_payload(
                    [
                        _announcement(
                            document_id="Q1_2024",
                            title="二零二四年第一季度報告",
                            file_link="/listedco/listconews/sehk/2025/0420/q1.pdf",
                            date_time="2025-04-20 16:30",
                            category_text="財務報表/環境、社會及管治資料 - [季度業績]",
                        ),
                        _announcement(
                            document_id="Q3_2024",
                            title="二零二四年第三季度報告",
                            file_link="/listedco/listconews/sehk/2025/1020/q3.pdf",
                            date_time="2025-10-20 16:30",
                            category_text="財務報表/環境、社會及管治資料 - [季度業績]",
                        ),
                    ]
                ),
            )
        if str(request.url) in {first_quarter_url, third_quarter_url} and request.method == "HEAD":
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = _build_client(handler)
    candidates = client.list_report_candidates(
        _query(periods=("Q1", "Q3")),
        _profile(),
    )

    assert [(candidate.source_id, candidate.fiscal_period) for candidate in candidates] == [
        ("Q1_2024", "Q1"),
        ("Q3_2024", "Q3"),
    ]


def test_list_report_candidates_reads_hk_quarterly_results_announcements() -> None:
    """真实腾讯式 ``公告及通告 - [季度業績]`` 应归入 Q1/Q2/Q3/Q4。"""

    q1_url = f"{HKEXNEWS_BASE_URL}/listedco/listconews/sehk/2025/0514/q1.pdf"
    q2_url = f"{HKEXNEWS_BASE_URL}/listedco/listconews/sehk/2025/0813/q2.pdf"
    q3_url = f"{HKEXNEWS_BASE_URL}/listedco/listconews/sehk/2025/1113/q3.pdf"
    q4_url = f"{HKEXNEWS_BASE_URL}/listedco/listconews/sehk/2026/0320/q4.pdf"

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL) and request.method == "GET":
            form = _query_from_request(request)
            assert form["t1code"] == ("10000",)
            assert form["t2Gcode"] == ("3",)
            assert form["t2code"] == ("13600",)
            if form["lang"] == ("E",):
                return httpx.Response(200, json=_title_search_payload([]))
            return httpx.Response(
                200,
                json=_title_search_payload(
                    [
                        _announcement(
                            document_id="Q3_2025",
                            title="截至二零二五年九月三十日止三個月及九個月業績公佈",
                            file_link="/listedco/listconews/sehk/2025/1113/q3.pdf",
                            date_time="13/11/2025 16:30",
                            category_text="公告及通告 - [季度業績]",
                        ),
                        _announcement(
                            document_id="Q4_2025",
                            title="截至二零二五年十二月三十一日止三個月及十二個月業績公佈",
                            file_link="/listedco/listconews/sehk/2026/0320/q4.pdf",
                            date_time="20/03/2026 16:30",
                            category_text="公告及通告 - [季度業績]",
                        ),
                        _announcement(
                            document_id="Q2_2025",
                            title="截至二零二五年六月三十日止三個月及六個月業績公佈",
                            file_link="/listedco/listconews/sehk/2025/0813/q2.pdf",
                            date_time="13/08/2025 16:30",
                            category_text="公告及通告 - [季度業績]",
                        ),
                        _announcement(
                            document_id="Q1_2025",
                            title="截至二零二五年三月三十一日止三個月業績公佈",
                            file_link="/listedco/listconews/sehk/2025/0514/q1.pdf",
                            date_time="14/05/2025 16:31",
                            category_text="公告及通告 - [季度業績]",
                        ),
                    ]
                ),
            )
        if str(request.url) in {q1_url, q2_url, q3_url, q4_url} and request.method == "HEAD":
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = _build_client(handler)
    candidates = client.list_report_candidates(
        _query(periods=("Q1", "Q2", "Q3", "Q4")),
        _profile(),
    )

    assert [(candidate.source_id, candidate.fiscal_period) for candidate in candidates] == [
        ("Q1_2025", "Q1"),
        ("Q2_2025", "Q2"),
        ("Q3_2025", "Q3"),
        ("Q4_2025", "Q4"),
    ]


def test_list_report_candidates_groups_by_year_and_prefers_amended() -> None:
    """同一 period 多年度都保留；同年同 period 更正版优先。"""

    pdf_urls = {
        f"{HKEXNEWS_BASE_URL}/listedco/listconews/sehk/2025/0401/2024_regular.pdf",
        f"{HKEXNEWS_BASE_URL}/listedco/listconews/sehk/2025/0402/2024_amended.pdf",
        f"{HKEXNEWS_BASE_URL}/listedco/listconews/sehk/2024/0401/2023_regular.pdf",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(HKEXNEWS_TITLE_SEARCH_URL) and request.method == "GET":
            form = _query_from_request(request)
            if form["lang"] == ("E",):
                return httpx.Response(200, json=_title_search_payload([]))
            return httpx.Response(
                200,
                json=_title_search_payload(
                    [
                        _announcement(
                            document_id="FY2024_REGULAR",
                            title="腾讯控股有限公司：2024年年度报告",
                            file_link="/listedco/listconews/sehk/2025/0401/2024_regular.pdf",
                            date_time="2025-04-03 16:30",
                        ),
                        _announcement(
                            document_id="FY2024_AMENDED",
                            title="腾讯控股有限公司：2024年年度报告（修訂）",
                            file_link="/listedco/listconews/sehk/2025/0402/2024_amended.pdf",
                            date_time="2025-04-02 16:30",
                        ),
                        _announcement(
                            document_id="FY2023_REGULAR",
                            title="腾讯控股有限公司：2023年年度报告",
                            file_link="/listedco/listconews/sehk/2024/0401/2023_regular.pdf",
                            date_time="2024-04-01 16:30",
                        ),
                    ]
                ),
            )
        if str(request.url) in pdf_urls and request.method == "HEAD":
            return httpx.Response(200, headers={})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = _build_client(handler)
    candidates = client.list_report_candidates(_query(), _profile())

    assert [candidate.fiscal_year for candidate in candidates] == [2024, 2023]
    assert [candidate.source_id for candidate in candidates] == [
        "FY2024_AMENDED",
        "FY2023_REGULAR",
    ]
    assert candidates[0].amended is True


def test_download_report_pdf_returns_asset_for_valid_pdf() -> None:
    """合法 PDF 下载返回资产对象。"""

    pdf_payload = _build_pdf_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == _PDF_URL
        return httpx.Response(200, content=pdf_payload)

    candidate = CnReportCandidate(
        provider="hkexnews",
        source_id="DOC1",
        source_url=_PDF_URL,
        title="Tencent Holdings Limited: 2024 Annual Report",
        language="en",
        filing_date="2025-04-01",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
        content_length=len(pdf_payload),
        etag=None,
        last_modified=None,
    )

    client = _build_client(handler)
    asset = client.download_report_pdf(candidate)

    assert asset.candidate == candidate
    assert asset.content_length == len(pdf_payload)
    assert asset.pdf_bytes == pdf_payload
    assert asset.sha256 == hashlib.sha256(pdf_payload).hexdigest()


def test_download_report_pdf_does_not_sleep_before_first_request() -> None:
    """首次请求不应被 sleep_seconds 延迟，等待只发生在重试之间。"""

    pdf_payload = _build_pdf_payload()
    sleep_calls: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=pdf_payload)

    candidate = CnReportCandidate(
        provider="hkexnews",
        source_id="DOC1",
        source_url=_PDF_URL,
        title="Tencent Holdings Limited: 2024 Annual Report",
        language="en",
        filing_date="2025-04-01",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
        content_length=len(pdf_payload),
        etag=None,
        last_modified=None,
    )
    client = HkexnewsDiscoveryClient(
        client=_build_http_client(handler),
        sleep_seconds=0.3,
        max_retries=2,
        sleep_func=sleep_calls.append,
    )

    asset = client.download_report_pdf(candidate)

    assert sleep_calls == []
    assert asset.pdf_bytes == pdf_payload


def test_download_report_pdf_throttles_between_successful_requests() -> None:
    """连续成功请求之间应按 sleep_seconds 补足主源保护间隔。"""

    pdf_payload = _build_pdf_payload()
    sleep_calls: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=pdf_payload)

    candidate = CnReportCandidate(
        provider="hkexnews",
        source_id="DOC1",
        source_url=_PDF_URL,
        title="Tencent Holdings Limited: 2024 Annual Report",
        language="en",
        filing_date="2025-04-01",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
        content_length=len(pdf_payload),
        etag=None,
        last_modified=None,
    )
    client = HkexnewsDiscoveryClient(
        client=_build_http_client(handler),
        sleep_seconds=0.3,
        max_retries=2,
        sleep_func=sleep_calls.append,
    )
    first = client.download_report_pdf(candidate)
    second = client.download_report_pdf(candidate)

    assert len(sleep_calls) == 1
    assert 0 < sleep_calls[0] <= 0.3
    assert first.pdf_bytes == pdf_payload
    assert second.pdf_bytes == pdf_payload


def test_download_report_pdf_repeated_calls_return_complete_bytes() -> None:
    """同一披露易 candidate 重复下载均返回完整且自洽的内存资产。"""

    pdf_payload = _build_pdf_payload()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=pdf_payload)

    candidate = CnReportCandidate(
        provider="hkexnews",
        source_id="DOC1",
        source_url=_PDF_URL,
        title="Tencent Holdings Limited: 2024 Annual Report",
        language="en",
        filing_date="2025-04-01",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
        content_length=len(pdf_payload),
        etag=None,
        last_modified=None,
    )
    client = _build_client(handler)

    first = client.download_report_pdf(candidate)
    second = client.download_report_pdf(candidate)

    assert first.pdf_bytes == pdf_payload
    assert second.pdf_bytes == pdf_payload
    assert first.sha256 == second.sha256
    assert first.content_length == second.content_length == len(pdf_payload)


def test_download_report_pdf_rejects_short_or_non_pdf_payload() -> None:
    """短文件或非 PDF magic bytes 必须被拒绝。"""

    payloads = [b"%PDF-", b"not-a-pdf" + b"0" * 2048]

    for payload in payloads:

        def handler(request: httpx.Request, payload: bytes = payload) -> httpx.Response:
            assert str(request.url) == _PDF_URL
            return httpx.Response(200, content=payload)

        candidate = CnReportCandidate(
            provider="hkexnews",
            source_id="DOC_BAD",
            source_url=_PDF_URL,
            title="Tencent Holdings Limited: 2024 Annual Report",
            language="en",
            filing_date="2025-04-01",
            fiscal_year=2024,
            fiscal_period="FY",
            amended=False,
            content_length=len(payload),
            etag=None,
            last_modified=None,
        )

        client = _build_client(handler)
        with pytest.raises(FinsDownloadProviderError) as exc_info:
            client.download_report_pdf(candidate)
        assert exc_info.value.transport_category is FinsDownloadTransportCategory.PROTOCOL
        assert exc_info.value.retryable is False


@pytest.mark.parametrize(
    ("failure_kind", "expected_category", "expected_retryable", "expected_calls"),
    [
        ("timeout", FinsDownloadTransportCategory.TIMEOUT, True, 2),
        ("network", FinsDownloadTransportCategory.CONNECTION, True, 2),
        ("protocol", FinsDownloadTransportCategory.PROTOCOL, False, 1),
        ("unknown", FinsDownloadTransportCategory.UNKNOWN, True, 2),
    ],
)
def test_hkexnews_transport_owner_closed_mapping_and_safe_log(
    failure_kind: str,
    expected_category: FinsDownloadTransportCategory,
    expected_retryable: bool,
    expected_calls: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 httpx hierarchy 应在披露易 owner 处闭合且日志不含 raw/URL。"""

    calls = 0
    errors: list[httpx.HTTPError] = []
    logs: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if failure_kind == "timeout":
            error: httpx.HTTPError = httpx.ReadTimeout(
                "raw-timeout-contact@example.invalid",
                request=request,
            )
        elif failure_kind == "network":
            error = httpx.ConnectError(
                "raw-network https://secret.invalid/path",
                request=request,
            )
        elif failure_kind == "protocol":
            error = httpx.RemoteProtocolError(
                "raw-protocol https://secret.invalid/path",
                request=request,
            )
        else:
            error = httpx.HTTPError("raw-unknown https://secret.invalid/path")
        errors.append(error)
        raise error

    monkeypatch.setattr(
        _hkexnews_downloader.Log,
        "debug",
        lambda message, *, module: logs.append(f"{module}:{message}"),
    )

    with pytest.raises(FinsDownloadProviderError) as exc_info:
        _build_client(handler).resolve_company(_query())

    failure = exc_info.value
    assert failure.source is FinsDownloadSource.HKEXNEWS
    assert failure.transport_category is expected_category
    assert failure.retryable is expected_retryable
    assert failure.__cause__ is errors[-1]
    assert calls == expected_calls
    public_text = f"{failure}\n{' '.join(logs)}"
    assert "secret.invalid" not in public_text
    assert "contact@example.invalid" not in public_text
    assert "raw-" not in public_text


@pytest.mark.parametrize(
    ("status_code", "expected_retryable", "expected_calls"),
    [(404, False, 1), (503, True, 2)],
)
def test_hkexnews_http_status_retry_policy(
    status_code: int,
    expected_retryable: bool,
    expected_calls: int,
) -> None:
    """披露易 4xx 立即终止，5xx 才消耗 bounded retries。"""

    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status_code, json={"raw": "secret"})

    with pytest.raises(FinsDownloadProviderError) as exc_info:
        _build_client(handler).resolve_company(_query())

    assert exc_info.value.transport_category is FinsDownloadTransportCategory.HTTP_STATUS
    assert exc_info.value.retryable is expected_retryable
    assert calls == expected_calls


def test_hkexnews_malformed_json_is_non_retryable_protocol_failure() -> None:
    """成功 HTTP 后的 JSON parse failure 不得进入 transport retry。"""

    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"{raw-secret-url:https://secret.invalid")

    with pytest.raises(HkexnewsProviderProtocolError) as exc_info:
        _build_client(handler).resolve_company(_query())

    assert exc_info.value.transport_category is FinsDownloadTransportCategory.PROTOCOL
    assert exc_info.value.retryable is False
    assert calls == 1
    assert "secret.invalid" not in str(exc_info.value)


def test_hkexnews_preloop_provider_misuse_makes_zero_http_requests() -> None:
    """错误 candidate provider 是 API misuse，必须 ValueError 且零 HTTP。"""

    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_build_pdf_payload())

    invalid = CnReportCandidate(
        provider="cninfo",
        source_id="invalid",
        source_url=_PDF_URL,
        title="invalid",
        language="en",
        filing_date="2025-04-01",
        fiscal_year=2024,
        fiscal_period="FY",
        amended=False,
        content_length=None,
        etag=None,
        last_modified=None,
    )

    with pytest.raises(ValueError):
        _build_client(handler).download_report_pdf(invalid)
    assert calls == 0
