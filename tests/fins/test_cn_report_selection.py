"""CN/HK report selection helper 测试。"""

from __future__ import annotations

from dayu.fins.pipelines.cn_download_models import (
    CnFiscalPeriod,
    CnLanguage,
    CnReportHeadMeta,
    CnReportQuery,
    CninfoRawAnnouncement,
    HkexnewsRawAnnouncement,
)
from dayu.fins.pipelines.cn_report_selection import (
    select_cninfo_report_candidates,
    select_hkexnews_report_candidates,
)


def _head_meta(_source_url: str) -> CnReportHeadMeta:
    """构造确定性 HEAD 元数据。

    Args:
        _source_url: PDF URL；测试不按 URL 区分。

    Returns:
        HEAD 元数据。

    Raises:
        无。
    """

    return CnReportHeadMeta(content_length=4096, etag='"fixture"', last_modified="Wed, 01 Jan 2025 00:00:00 GMT")


def _cn_query(periods: tuple[CnFiscalPeriod, ...]) -> CnReportQuery:
    """构造 CN 查询。

    Args:
        periods: 目标财期。

    Returns:
        CN report query。

    Raises:
        无。
    """

    return CnReportQuery(
        market="CN",
        normalized_ticker="002594",
        start_date="2024-01-01",
        end_date="2026-12-31",
        discovery_periods=periods,
    )


def _hk_query(periods: tuple[CnFiscalPeriod, ...]) -> CnReportQuery:
    """构造 HK 查询。

    Args:
        periods: 目标财期。

    Returns:
        HK report query。

    Raises:
        无。
    """

    return CnReportQuery(
        market="HK",
        normalized_ticker="0700",
        start_date="2024-01-01",
        end_date="2026-12-31",
        discovery_periods=periods,
    )


def _cn_raw(
    *,
    announcement_id: str,
    title: str,
    announcement_date: str = "2025-04-01",
) -> CninfoRawAnnouncement:
    """构造巨潮 raw announcement。

    Args:
        announcement_id: 公告 ID。
        title: 公告标题。
        announcement_date: 披露日期。

    Returns:
        巨潮 raw announcement。

    Raises:
        无。
    """

    return CninfoRawAnnouncement(
        sec_code="002594",
        announcement_id=announcement_id,
        title=title,
        announcement_date=announcement_date,
        adjunct_url=f"finalpage/{announcement_id}.PDF",
        source_url=f"http://static.cninfo.com.cn/finalpage/{announcement_id}.PDF",
    )


def _hk_raw(
    *,
    document_id: str,
    title: str,
    category_text: str,
    filing_date: str = "2025-04-01",
    language: CnLanguage = "zh",
) -> HkexnewsRawAnnouncement:
    """构造披露易 raw announcement。

    Args:
        document_id: 文档 ID。
        title: 标题。
        category_text: 分类文本。
        filing_date: 披露日期。
        language: 查询语言。

    Returns:
        披露易 raw announcement。

    Raises:
        无。
    """

    return HkexnewsRawAnnouncement(
        document_id=document_id,
        title=title,
        source_url=f"https://www1.hkexnews.hk/listedco/{document_id}.pdf",
        stock_code_payload="00700",
        category_text=category_text,
        filing_date=filing_date,
        language=language,
    )


def test_cninfo_selection_filters_blocklisted_titles_and_builds_candidate() -> None:
    """巨潮 title blocklist 与 candidate 构造归 pipeline helper 所有。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    candidates = select_cninfo_report_candidates(
        query=_cn_query(("FY",)),
        announcements_by_period={
            "FY": (
                _cn_raw(announcement_id="FULL", title="比亚迪：2024年年度报告"),
                _cn_raw(announcement_id="SUMMARY", title="比亚迪：2024年年度报告摘要"),
                _cn_raw(announcement_id="EN", title="比亚迪：2024年年度报告（英文）"),
            )
        },
        read_head_meta=_head_meta,
    )

    assert [(item.source_id, item.fiscal_year, item.fiscal_period) for item in candidates] == [("FULL", 2024, "FY")]
    assert candidates[0].content_length == 4096
    assert candidates[0].etag == '"fixture"'


def test_cninfo_selection_keeps_years_and_prefers_amended_per_year() -> None:
    """巨潮同年更正优先，但不同 fiscal_year 不能互相覆盖。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    candidates = select_cninfo_report_candidates(
        query=_cn_query(("FY",)),
        announcements_by_period={
            "FY": (
                _cn_raw(announcement_id="A1", title="贵州茅台：2024年年度报告", announcement_date="2025-04-01"),
                _cn_raw(
                    announcement_id="A2", title="贵州茅台：2024年年度报告（更正后）", announcement_date="2025-04-15"
                ),
                _cn_raw(announcement_id="A3", title="贵州茅台：2023年年度报告", announcement_date="2024-04-01"),
            )
        },
        read_head_meta=_head_meta,
    )

    assert [(item.fiscal_year, item.source_id, item.amended) for item in candidates] == [
        (2024, "A2", True),
        (2023, "A3", False),
    ]


def test_hkexnews_selection_filters_english_and_infers_periods() -> None:
    """披露易语言过滤与财期推断归 pipeline helper 所有。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    candidates = select_hkexnews_report_candidates(
        query=_hk_query(("FY", "Q2")),
        announcements=(
            _hk_raw(
                document_id="FY_ZH",
                title="2024 年報",
                category_text="財務報表/環境、社會及管治資料 - [年報]",
                filing_date="2025-04-01",
            ),
            _hk_raw(
                document_id="FY_EN",
                title="Tencent Holdings Limited: 2024 Annual Report",
                category_text="Financial Statements/ESG Information - [Annual Report]",
                filing_date="2025-04-02",
            ),
            _hk_raw(
                document_id="Q2_ZH",
                title="截至二零二五年六月三十日止三個月及六個月業績公佈",
                category_text="公告及通告 - [季度業績]",
                filing_date="2025-08-13",
            ),
        ),
        read_head_meta=_head_meta,
    )

    assert [(item.source_id, item.fiscal_year, item.fiscal_period) for item in candidates] == [
        ("Q2_ZH", 2025, "Q2"),
        ("FY_ZH", 2024, "FY"),
    ]


def test_hkexnews_selection_groups_by_year_and_prefers_amended() -> None:
    """披露易同 period/year 更正版本优先。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    candidates = select_hkexnews_report_candidates(
        query=_hk_query(("H1",)),
        announcements=(
            _hk_raw(
                document_id="H1_ORIGINAL",
                title="中期報告 2025",
                category_text="財務報表/環境、社會及管治資料 - [中期/半年度報告]",
                filing_date="2025-08-26",
            ),
            _hk_raw(
                document_id="H1_REVISED",
                title="中期報告 2025 修訂",
                category_text="財務報表/環境、社會及管治資料 - [中期/半年度報告]",
                filing_date="2025-08-27",
            ),
        ),
        read_head_meta=_head_meta,
    )

    assert [(item.source_id, item.fiscal_period, item.amended) for item in candidates] == [("H1_REVISED", "H1", True)]
