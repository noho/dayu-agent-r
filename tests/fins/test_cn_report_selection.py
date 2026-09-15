"""CN/HK report selection helper 测试。"""

from __future__ import annotations

import pytest

from dayu.fins.pipelines.cn_download_models import (
    CnFiscalPeriod,
    CnLanguage,
    CnReportHeadMeta,
    CnReportPeriodProjection,
    CnReportQuery,
    CninfoRawAnnouncement,
    HkexnewsRawAnnouncement,
)
from dayu.fins.pipelines.cn_report_selection import (
    _classify_hk_period_projection,
    resolve_hk_report_period,
    select_cninfo_report_candidates,
    select_hkexnews_report_candidates,
)
from dayu.fins.pipelines.hk_fiscal_calendar import annual_end_dates
from dayu.fins.pipelines.docling_upload_service import build_cn_filing_ids


@pytest.mark.parametrize("duration", ("三個月", "三个月", "THREE MONTHS", "3 MONTHS"))
def test_hk_three_months_alone_is_not_q1(duration: str) -> None:
    """参数为四种期间长度；返回无；错误把期间长度当季度时抛出断言异常。"""
    assert (
        _classify_hk_period_projection(
            title=f"截至2025年9月30日止{duration}業績公告",
            category_text="季度業績",
        )
        is None
    )


@pytest.mark.parametrize(
    ("title", "annual_title", "year", "period"),
    (
        ("截至2025年3月31日止三個月業績", "截至2024年12月31日止全年業績", 2025, "Q1"),
        ("截至2025年6月30日止三个月业绩", "截至2025年12月31日止全年业绩", 2025, "Q2"),
        ("截至二零二五年九月三十日止三個月業績", "截至二零二五年十二月三十一日止全年業績", 2025, "Q3"),
        ("截至二〇二五年十二月三十一日止三個月業績", "截至二〇二四年十二月三十一日止全年業績", 2025, "Q4"),
        ("THREE MONTHS ENDED 30 SEPTEMBER 2025", "ANNUAL RESULTS FOR YEAR ENDED 31 MARCH 2025", 2026, "Q2"),
        ("3 MONTHS ENDED SEPTEMBER 30, 2025", "FINAL RESULTS FOR YEAR ENDED JUNE 30, 2025", 2026, "Q1"),
        ("截至2025年9月30日止三個月及九個月業績", "截至2024年12月31日止全年業績", 2025, "Q3"),
        ("截至2025年6月30日止三個月及六個月業績", "截至2024年12月31日止全年業績", 2025, "Q2"),
        ("2025 FIRST QUARTER RESULTS", "", 2025, "Q1"),
        ("2025 Q2 RESULTS", "", 2025, "Q2"),
        ("2025 THIRD QUARTER AND NINE MONTHS RESULTS", "", 2025, "Q3"),
        ("2025 FOURTH QUARTER AND FULL YEAR RESULTS", "", 2025, "Q4"),
        ("2025年第三季度業績", "", 2025, "Q3"),
        ("2025年第四季度业绩", "", 2025, "Q4"),
        ("FY2026 SECOND QUARTER ENDED 30 SEPTEMBER 2025", "FINAL RESULTS FOR YEAR ENDED 31 MARCH 2025", 2026, "Q2"),
    ),
)
def test_hk_period_facts_use_fiscal_evidence(
    title: str,
    annual_title: str,
    year: int,
    period: CnFiscalPeriod,
) -> None:
    """参数为标题、同公司年度证据和期望财期；返回无；财期或 coverage 漂移抛出断言异常。"""
    facts = resolve_hk_report_period(
        title=title, category_text="季度業績", annual_ends=annual_end_dates((annual_title,))
    )
    assert facts is not None
    assert facts[0] == year
    assert facts[1].identity_period == period
    assert facts[1].covered_periods == {"Q2": ("H1", "Q2"), "Q4": ("FY", "Q4")}.get(period, (period,))


@pytest.mark.parametrize(
    "title",
    (
        "2025 FIRST QUARTER AND THIRD QUARTER RESULTS",
        "2025年第一季度及九個月業績",
        "2025 Q2 AND Q3 RESULTS",
        "2025 Q10 RESULTS",
        "截至2025年9月30日止第一季度業績",
        "截至2025年8月31日止三個月業績",
        "截至2025年9月31日止第三季度業績",
        "截至2024年9月30日及2025年9月30日止第三季度業績",
        "2024/25年第三季度業績",
        "2024及2025年第三季度業績",
        "FY2024 THIRD QUARTER ENDED 30 SEPTEMBER 2025",
    ),
)
def test_hk_conflicting_period_facts_fail_closed(title: str) -> None:
    """参数为矛盾或非季度日期标题；返回无；错误接纳时抛出断言异常。"""
    assert (
        resolve_hk_report_period(
            title=title,
            category_text="季度業績",
            annual_ends=annual_end_dates(("截至2024年12月31日止全年業績",)),
        )
        is None
    )


def test_hk_selection_uses_annual_announcements_before_period_filtering() -> None:
    """无参数与返回值；真实候选选择必须使用非请求财期的年度 raw 证据，否则断言失败。"""
    candidates = select_hkexnews_report_candidates(
        query=_hk_query(("Q3",)),
        announcements=(
            _hk_raw(document_id="annual", title="截至2024年12月31日止全年業績", category_text="末期業績"),
            _hk_raw(
                document_id="quarter",
                title="截至2025年9月30日止三個月業績公告",
                category_text="季度業績",
                filing_date="2026-02-01",
            ),
        ),
        read_head_meta=_head_meta,
    )
    assert [(c.source_id, c.fiscal_year, c.period_projection.identity_period) for c in candidates] == [
        ("quarter", 2025, "Q3")
    ]


def test_hk_no_disclosure_year_fallback_or_changed_year_end_guess() -> None:
    """无参数与返回值；无报告年份或变更年结日时应不确定，否则断言失败。"""
    assert (
        select_hkexnews_report_candidates(
            query=_hk_query(("Q1",)),
            announcements=(_hk_raw(document_id="no-year", title="第一季度業績", category_text="季度業績"),),
            read_head_meta=_head_meta,
        )
        == ()
    )
    assert (
        resolve_hk_report_period(
            title="截至2025年9月30日止三個月業績",
            category_text="季度業績",
            annual_ends=annual_end_dates(("截至2024年12月31日止全年業績", "截至2025年6月30日止全年業績")),
        )
        is None
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
        normalized_ticker="0005",
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
        stock_code_payload="00005",
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

    assert [(item.source_id, item.fiscal_year, item.period_projection.identity_period) for item in candidates] == [
        ("FULL", 2024, "FY")
    ]
    assert candidates[0].period_projection.covered_periods == ("FY",)
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

    assert [(item.source_id, item.fiscal_year, item.period_projection.identity_period) for item in candidates] == [
        ("Q2_ZH", 2025, "Q2"),
        ("FY_ZH", 2024, "FY"),
    ]
    assert candidates[0].period_projection.covered_periods == ("H1", "Q2")


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

    assert [(item.source_id, item.period_projection.identity_period, item.amended) for item in candidates] == [
        ("H1_REVISED", "H1", True)
    ]


@pytest.mark.parametrize(
    ("category_text", "title", "expected_identity", "expected_coverage"),
    (
        ("INTERIM RESULTS", "截至期末六個月", "Q2", ("H1", "Q2")),
        ("中期業績", "截至期末六个月", "Q2", ("H1", "Q2")),
        ("FINAL RESULTS", "全年業績", "Q4", ("FY", "Q4")),
        ("末期业绩", "ANNUAL RESULTS", "Q4", ("FY", "Q4")),
        ("INTERIM RESULTS", "業績公告", "Q2", ("H1", "Q2")),
        ("FINAL RESULTS", "業績公告", "Q4", ("FY", "Q4")),
    ),
)
def test_hkexnews_selection_uses_category_first_then_category_and_title_period_facts(
    category_text: str,
    title: str,
    expected_identity: CnFiscalPeriod,
    expected_coverage: tuple[CnFiscalPeriod, ...],
) -> None:
    """family 只由 category 判定，期间事实随后读取 category 与 title。

    Args:
        category_text: provider 分类文本。
        title: 通用公告标题片段。
        expected_identity: 预期身份财期。
        expected_coverage: 预期覆盖财期。

    Returns:
        无。

    Raises:
        AssertionError: 分类投影不符合 contract 时抛出。
    """

    candidates = select_hkexnews_report_candidates(
        query=_hk_query((expected_identity,)),
        announcements=(
            _hk_raw(
                document_id="GENERIC_PERIOD_FACT",
                title=f"2025 {title}",
                category_text=category_text,
            ),
        ),
        read_head_meta=_head_meta,
    )

    assert len(candidates) == 1
    assert candidates[0].period_projection.identity_period == expected_identity
    assert candidates[0].period_projection.covered_periods == expected_coverage


@pytest.mark.parametrize(
    ("category_text", "title"),
    (
        ("", "2025 INTERIM RESULTS"),
        ("INTERIM RESULTS / INTERIM REPORT", "2025 SIX MONTHS"),
        ("INTERIM REPORT", "2025 THIRD QUARTER"),
        ("RESULTS", "2025 RESULTS"),
        ("FINAL RESULTS", "2025 SIX MONTHS"),
    ),
)
def test_hkexnews_selection_rejects_ambiguous_family_or_period_facts(
    category_text: str,
    title: str,
) -> None:
    """family 或 family 内期间事实不唯一时必须 fail closed。

    Args:
        category_text: provider 分类文本。
        title: 通用公告标题片段。

    Returns:
        无。

    Raises:
        AssertionError: 歧义公告被错误接纳时抛出。
    """

    candidates = select_hkexnews_report_candidates(
        query=_hk_query(("FY", "H1", "Q1", "Q2", "Q3", "Q4")),
        announcements=(_hk_raw(document_id="GENERIC_AMBIGUOUS", title=title, category_text=category_text),),
        read_head_meta=_head_meta,
    )

    assert candidates == ()


@pytest.mark.parametrize(
    ("identity_period", "covered_periods"),
    (
        ("FY", ()),
        ("Q4", ("FY", "Q4", "Q4")),
        ("Q4", ("Q4", "FY")),
        ("Q4", ("FY",)),
    ),
)
def test_cn_report_period_projection_rejects_invalid_coverage(
    identity_period: CnFiscalPeriod,
    covered_periods: tuple[CnFiscalPeriod, ...],
) -> None:
    """candidate contract 拒绝空、重复、乱序或不含 identity 的 coverage。

    Args:
        identity_period: 身份财期。
        covered_periods: 非法覆盖财期。

    Returns:
        无。

    Raises:
        AssertionError: 非法 coverage 未被拒绝时抛出。
    """

    with pytest.raises(ValueError):
        CnReportPeriodProjection(
            identity_period=identity_period,
            covered_periods=covered_periods,
        )


def test_hkexnews_selection_projects_four_generic_materials_to_distinct_identities() -> None:
    """同批通用 raw material 保持 report/result 身份、coverage 与 ID 各自唯一。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: material 被折叠或 coverage/ID 漂移时抛出。
    """

    candidates = select_hkexnews_report_candidates(
        query=_hk_query(("FY", "H1", "Q2", "Q4")),
        announcements=(
            _hk_raw(document_id="RESULT_H1", title="2025 六個月業績", category_text="中期業績"),
            _hk_raw(document_id="REPORT_H1", title="2025 半年度報告", category_text="中期報告"),
            _hk_raw(document_id="RESULT_FY", title="2025 全年業績", category_text="末期業績"),
            _hk_raw(document_id="REPORT_FY", title="2025 年度報告", category_text="年報"),
        ),
        read_head_meta=_head_meta,
    )

    assert [candidate.source_id for candidate in candidates] == [
        "REPORT_FY",
        "REPORT_H1",
        "RESULT_H1",
        "RESULT_FY",
    ]
    assert [
        (
            candidate.period_projection.identity_period,
            candidate.period_projection.covered_periods,
        )
        for candidate in candidates
    ] == [
        ("FY", ("FY",)),
        ("H1", ("H1",)),
        ("Q2", ("H1", "Q2")),
        ("Q4", ("FY", "Q4")),
    ]
    document_ids = {
        build_cn_filing_ids(
            ticker="0005",
            form_type=candidate.period_projection.identity_period,
            fiscal_year=candidate.fiscal_year,
            fiscal_period=candidate.period_projection.identity_period,
            amended=candidate.amended,
        )[0]
        for candidate in candidates
    }
    assert len(document_ids) == 4


def test_hkexnews_selection_fails_closed_on_same_source_id_fact_conflict() -> None:
    """同一 source ID 的 raw 核心事实冲突必须 fail closed。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 冲突 raw 未抛错时抛出。
    """

    with pytest.raises(ValueError, match="核心事实冲突"):
        select_hkexnews_report_candidates(
            query=_hk_query(("Q2",)),
            announcements=(
                _hk_raw(document_id="CONFLICT", title="2025 六個月業績", category_text="中期業績"),
                _hk_raw(document_id="CONFLICT", title="2025 全年業績", category_text="末期業績"),
            ),
            read_head_meta=_head_meta,
        )
