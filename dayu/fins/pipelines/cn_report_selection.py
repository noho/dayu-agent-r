"""CN/HK raw announcement 到财报候选的业务选择真源。

下载器只负责 HTTP、JSON 与 provider raw 字段归一；本模块负责产品级财报
筛选、语言过滤、财期/财年推断、同 period/year 去重以及
``CnReportCandidate`` 构造。
"""

from __future__ import annotations

import re
from datetime import date
from collections.abc import Callable, Mapping
from typing import Final, Optional, TypeAlias

from dayu.fins.pipelines.cn_download_models import (
    CN_FISCAL_PERIOD_ORDER,
    CnFiscalPeriod,
    CnReportCandidate,
    CnReportHeadMeta,
    CnReportPeriodProjection,
    CnReportQuery,
    CninfoRawAnnouncement,
    HkexnewsRawAnnouncement,
)


from dayu.fins.pipelines.hk_fiscal_calendar import (
    annual_end_dates,
    fiscal_quarter_at,
    has_unresolved_end_date,
    report_end_date,
)

ReadHeadMeta: TypeAlias = Callable[[str], CnReportHeadMeta]
"""读取 PDF HEAD 元数据的窄 callable 类型。"""

_PERIOD_SORT_KEY: Final[dict[CnFiscalPeriod, int]] = {
    period: index for index, period in enumerate(CN_FISCAL_PERIOD_ORDER)
}

_CNINFO_TITLE_BLOCKLIST: Final[tuple[str, ...]] = (
    "摘要",
    "已取消",
    "已撤销",
    "撤回",
    "取消",
    "更正前",
    "募集说明书",
    "ESG",
    "可持续发展",
    "审计报告",
    "财务报表",
    "意见",
    "（英文）",
    "(英文)",
    "英文)",
    "英文）",
    "英文版",
    "英文简版",
    "英文简本",
    "english",
    "港股公告",
    "h股公告",
    "h股",
)
_CNINFO_REPORT_NOTICE_TITLE_TOKENS: Final[tuple[str, ...]] = (
    "公告",
    "提示性公告",
    "自愿性披露公告",
)
_CNINFO_REPORT_TITLE_TOKENS: Final[tuple[str, ...]] = (
    "年度报告",
    "年报",
    "半年度报告",
    "一季度报告",
    "第一季度报告",
    "三季度报告",
    "第三季度报告",
)
_CNINFO_TITLE_AMENDED_TOKENS: Final[tuple[str, ...]] = ("更正", "更正后", "修订", "补充", "修正")
_CNINFO_TITLE_FY_PATTERN: Final[re.Pattern[str]] = re.compile(r"(\d{4})\s*年[年度]?\s*(年度报告|年报)")
_CNINFO_TITLE_FISCAL_YEAR_FALLBACK: Final[re.Pattern[str]] = re.compile(r"(\d{4})\s*年")

_HK_TITLE_AMENDED_TOKENS: Final[tuple[str, ...]] = (
    "更正",
    "修訂",
    "修订",
    "補充",
    "补充",
    "REVISED",
    "SUPPLEMENTAL",
)
_HK_ENGLISH_REPORT_TITLE_TOKENS: Final[tuple[str, ...]] = (
    "ANNUAL REPORT",
    "INTERIM REPORT",
    "QUARTERLY REPORT",
    "QUARTERLY RESULTS",
    "FIRST QUARTER",
    "SECOND QUARTER",
    "THIRD QUARTER",
    "FOURTH QUARTER",
)
_HK_CATEGORY_RESULTS_MARKERS: Final[tuple[str, ...]] = ("業績", "业绩", "RESULTS")
_HK_CATEGORY_REPORT_MARKERS: Final[tuple[str, ...]] = (
    "年報",
    "年报",
    "年度報告",
    "年度报告",
    "REPORT",
    "中期報告",
    "中期报告",
    "半年報",
    "半年报",
    "半年度報告",
    "半年度报告",
)
_HK_REPORT_FY_TOKENS: Final[tuple[str, ...]] = (
    "ANNUAL REPORT",
    "FULL YEAR REPORT",
    "FULL-YEAR",
    "FULL YEAR",
    "年報",
    "年报",
    "年度報告",
    "年度报告",
    "全年",
)
_HK_REPORT_H1_TOKENS: Final[tuple[str, ...]] = (
    "INTERIM REPORT",
    "HALF-YEAR REPORT",
    "HALF YEAR REPORT",
    "HALF-YEAR",
    "HALF YEAR",
    "中期報告",
    "中期报告",
    "半年報",
    "半年报",
    "半年度報告",
    "半年度报告",
    "半年",
)
_HK_REPORT_FORBIDDEN_RESULT_TOKENS: Final[tuple[str, ...]] = (
    "QUARTER",
    "RESULTS",
    "季度",
    "季業績",
    "季业绩",
)
_HK_QUARTER_LENGTH_TOKENS: Final[tuple[str, ...]] = (
    "三個月",
    "三个月",
    "3個月",
    "3个月",
    "THREE MONTHS",
    "3 MONTHS",
)
_HK_RESULTS_PERIOD_TOKENS: Final[dict[CnFiscalPeriod, tuple[str, ...]]] = {
    "Q1": (
        "Q1",
        "FIRST QUARTER",
        "FIRST QUARTERLY",
        "第一季度",
        "第一季",
        "一季度",
        "一季",
    ),
    "Q2": (
        "INTERIM RESULTS",
        "SECOND QUARTER",
        "SECOND QUARTERLY",
        "SIX MONTHS",
        "6 MONTHS",
        "HALF YEAR",
        "Q2",
        "第二季度",
        "第二季",
        "二季度",
        "二季",
        "六個月",
        "六个月",
        "半年",
        "中期業績",
        "中期业绩",
    ),
    "Q3": (
        "Q3",
        "THIRD QUARTER",
        "THIRD QUARTERLY",
        "NINE MONTHS",
        "9 MONTHS",
        "第三季度",
        "第三季",
        "三季度",
        "三季",
        "九個月",
        "九个月",
    ),
    "Q4": (
        "FINAL RESULTS",
        "FOURTH QUARTER",
        "FOURTH QUARTERLY",
        "TWELVE MONTHS",
        "12 MONTHS",
        "FULL YEAR",
        "Q4",
        "第四季度",
        "第四季",
        "四季度",
        "四季",
        "十二個月",
        "十二个月",
        "全年",
        "ANNUAL RESULTS",
        "末期業績",
        "末期业绩",
    ),
}
_HK_TITLE_YEAR_PATTERN: Final[re.Pattern[str]] = re.compile(r"(20\d{2}|19\d{2})")
_HK_TITLE_CHINESE_YEAR_PATTERN: Final[re.Pattern[str]] = re.compile(r"([零〇一二三四五六七八九]{4})年")
_HK_FISCAL_YEAR_LABEL: Final[re.Pattern[str]] = re.compile(
    r"FY\s*(19\d{2}|20\d{2})|(19\d{2}|20\d{2})\s*(?:財年|财年|FISCAL YEAR)",
    re.IGNORECASE,
)
_HK_CHINESE_DIGIT_TO_INT: Final[dict[str, int]] = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def select_cninfo_report_candidates(
    *,
    query: CnReportQuery,
    announcements_by_period: Mapping[CnFiscalPeriod, tuple[CninfoRawAnnouncement, ...]],
    read_head_meta: Callable[[str], CnReportHeadMeta],
) -> tuple[CnReportCandidate, ...]:
    """从巨潮 raw announcements 选择财报候选。

    Args:
        query: 单次 CN download 查询。
        announcements_by_period: downloader 按巨潮 category 拉回的 raw 公告。
        read_head_meta: 读取 PDF HEAD 元数据的 HTTP 边界函数。

    Returns:
        已按 fiscal year 降序、period 稳定顺序排序的候选 tuple。

    Raises:
        无。
    """

    per_period_year: dict[tuple[CnFiscalPeriod, int], list[CninfoRawAnnouncement]] = {}
    for period in query.discovery_periods:
        for item in announcements_by_period.get(period, ()):
            if _is_title_blocked(item.title):
                continue
            fiscal_year = _infer_cninfo_fiscal_year(item.title, item.announcement_date)
            if fiscal_year is None:
                continue
            per_period_year.setdefault((period, fiscal_year), []).append(item)

    candidates: list[CnReportCandidate] = []
    for (period, fiscal_year), items in per_period_year.items():
        best = _pick_best_cninfo_announcement(items)
        if best is None:
            continue
        candidates.append(
            _build_cninfo_candidate(
                announcement=best,
                period=period,
                fiscal_year=fiscal_year,
                head_meta=read_head_meta(best.source_url),
            )
        )
    candidates.sort(key=lambda item: (-item.fiscal_year, _PERIOD_SORT_KEY[item.period_projection.identity_period]))
    return tuple(candidates)


def select_hkexnews_report_candidates(
    *,
    query: CnReportQuery,
    announcements: tuple[HkexnewsRawAnnouncement, ...],
    read_head_meta: Callable[[str], CnReportHeadMeta],
) -> tuple[CnReportCandidate, ...]:
    """从披露易 raw announcements 选择财报候选。

    Args:
        query: 单次 HK download 查询。
        announcements: downloader 拉回的 raw 公告。
        read_head_meta: 读取 PDF HEAD 元数据的 HTTP 边界函数。

    Returns:
        已按 fiscal year 降序、period 稳定顺序排序的候选 tuple。

    Raises:
        无。
    """

    grouped: dict[tuple[CnFiscalPeriod, int], list[HkexnewsRawAnnouncement]] = {}
    projection_by_document_id: dict[str, CnReportPeriodProjection] = {}
    unique = _deduplicate_hk_announcements(announcements)
    annual_ends = annual_end_dates(tuple(item.title for item in unique))
    for item in unique:
        if _is_english_hk_announcement(item):
            continue
        facts = resolve_hk_report_period(
            title=item.title,
            category_text=item.category_text,
            annual_ends=annual_ends,
        )
        if facts is None:
            continue
        fiscal_year, period_projection = facts
        if period_projection.identity_period not in query.discovery_periods:
            continue
        projection_by_document_id[item.document_id] = period_projection
        grouped.setdefault((period_projection.identity_period, fiscal_year), []).append(item)

    candidates: list[CnReportCandidate] = []
    for (period, fiscal_year), items in grouped.items():
        best = _pick_best_hk_announcement(items)
        if best is None:
            continue
        candidates.append(
            _build_hk_candidate(
                announcement=best,
                period_projection=projection_by_document_id[best.document_id],
                fiscal_year=fiscal_year,
                head_meta=read_head_meta(best.source_url),
            )
        )
    candidates.sort(key=lambda item: (-item.fiscal_year, _PERIOD_SORT_KEY[item.period_projection.identity_period]))
    return tuple(candidates)


def _is_title_blocked(title: str) -> bool:
    """判断巨潮标题是否命中财报候选排除规则。

    Args:
        title: 公告标题。

    Returns:
        命中排除规则返回 `True`。

    Raises:
        无。
    """

    lowered = title.lower()
    if any(token.lower() in lowered for token in _CNINFO_TITLE_BLOCKLIST):
        return True
    if _has_cninfo_report_language_marker(title):
        return True
    has_report_title = any(token in title for token in _CNINFO_REPORT_TITLE_TOKENS)
    has_notice_title = any(token in title for token in _CNINFO_REPORT_NOTICE_TITLE_TOKENS)
    return has_report_title and has_notice_title


def _has_cninfo_report_language_marker(title: str) -> bool:
    """判断巨潮财报标题是否带英文语言标记。

    Args:
        title: 公告标题。

    Returns:
        带英文语言标记时返回 `True`。

    Raises:
        无。
    """

    if "英文" not in title:
        return False
    return any(token in title for token in _CNINFO_REPORT_TITLE_TOKENS)


def _infer_cninfo_fiscal_year(title: str, announcement_date: str) -> Optional[int]:
    """从巨潮标题与披露日期推断财年。

    Args:
        title: 公告标题。
        announcement_date: 披露日期。

    Returns:
        推断财年；无法解析返回 `None`。

    Raises:
        无。
    """

    matched = _CNINFO_TITLE_FY_PATTERN.search(title)
    if matched is not None:
        return int(matched.group(1))
    fallback = _CNINFO_TITLE_FISCAL_YEAR_FALLBACK.search(title)
    if fallback is not None:
        return int(fallback.group(1))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", announcement_date):
        return int(announcement_date[:4])
    return None


def _pick_best_cninfo_announcement(items: list[CninfoRawAnnouncement]) -> Optional[CninfoRawAnnouncement]:
    """从同一巨潮 fiscal period/year 中挑选最佳公告。

    Args:
        items: 同组 raw 公告。

    Returns:
        最佳公告；空列表返回 `None`。

    Raises:
        无。
    """

    if not items:
        return None

    def sort_key(announcement: CninfoRawAnnouncement) -> tuple[int, str]:
        is_amended = any(token in announcement.title for token in _CNINFO_TITLE_AMENDED_TOKENS)
        return (1 if is_amended else 0, announcement.announcement_date)

    return max(items, key=sort_key)


def _build_cninfo_candidate(
    *,
    announcement: CninfoRawAnnouncement,
    period: CnFiscalPeriod,
    fiscal_year: int,
    head_meta: CnReportHeadMeta,
) -> CnReportCandidate:
    """把巨潮 raw announcement 构造为候选对象。

    Args:
        announcement: 已选择 raw 公告。
        period: 财期。
        fiscal_year: 财年。
        head_meta: PDF HEAD 元数据。

    Returns:
        CNInfo candidate。

    Raises:
        无。
    """

    return CnReportCandidate(
        provider="cninfo",
        source_id=announcement.announcement_id,
        source_url=announcement.source_url,
        title=announcement.title,
        language="zh",
        filing_date=announcement.announcement_date,
        fiscal_year=fiscal_year,
        period_projection=CnReportPeriodProjection(identity_period=period, covered_periods=(period,)),
        amended=any(token in announcement.title for token in _CNINFO_TITLE_AMENDED_TOKENS),
        content_length=head_meta.content_length,
        etag=head_meta.etag,
        last_modified=head_meta.last_modified,
    )


def _infer_hk_fiscal_year(title: str, annual_ends: tuple[date, ...] = ()) -> int | None:
    """从标题和有依据的年结日识别财年，日期标题采用财年结束年份。

    Args:
        title: 公告标题。
        annual_ends: 同公司年度截止日证据。

    Returns:
        推断财年；无法解析返回 `None`。

    Raises:
        无。
    """

    end = report_end_date(title)
    if end is not None:
        if end in annual_end_dates((title,)):
            return end.year
        calendar_period = fiscal_quarter_at(end, annual_ends)
        return calendar_period[0] if calendar_period is not None else None
    years = _hk_title_years(title)
    return next(iter(years)) if len(years) == 1 else None


def _hk_title_years(title: str) -> set[int]:
    """参数为原始标题；返回所有有效中英文年份；无异常，不按出现顺序挑年份。"""
    years = {int(value) for value in _HK_TITLE_YEAR_PATTERN.findall(title)}
    years.update(
        year
        for value in _HK_TITLE_CHINESE_YEAR_PATTERN.findall(title)
        if (year := _parse_chinese_digit_year(value)) is not None
    )
    return years


def resolve_hk_report_period(
    *,
    title: str,
    category_text: str,
    annual_ends: tuple[date, ...],
) -> tuple[int, CnReportPeriodProjection] | None:
    """为发现与本地重建统一解析港股财年和财期。

    参数：title、category_text 为来源事实；annual_ends 为同公司年度截止日证据。
    返回：财年和身份/覆盖投影；缺少或冲突返回 None。异常：无。
    """
    if has_unresolved_end_date(title):
        return None
    # 财年区间简写与普通日期不同；没有明确命名规则时不选择区间中的某一年。
    if re.search(r"\d{4}\s*/\s*\d{2,4}(?![/\d])", title):
        return None
    projection = _classify_hk_period_projection(
        title=title,
        category_text=category_text,
        annual_ends=annual_ends,
    )
    year = _infer_hk_fiscal_year(title, annual_ends)
    end = report_end_date(title)
    if year is None and end is not None and projection is not None and not annual_ends:
        ordinal = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "H1": 2, "FY": 4}[projection.identity_period]
        year = end.year + (end.month + (4 - ordinal) * 3 - 1) // 12
    labelled = {int(value) for match in _HK_FISCAL_YEAR_LABEL.finditer(title) for value in match.groups() if value}
    if labelled and (len(labelled) != 1 or year not in labelled):
        return None
    if not labelled and len(_hk_title_years(title)) > 1:
        return None
    return (year, projection) if year is not None and projection is not None else None


def _parse_chinese_digit_year(value: str) -> int | None:
    """解析逐位中文数字年份。

    Args:
        value: 四位中文数字年份。

    Returns:
        公历年份；格式异常返回 `None`。

    Raises:
        无。
    """

    if len(value) != 4:
        return None
    digits: list[str] = []
    for char in value:
        digit = _HK_CHINESE_DIGIT_TO_INT.get(char)
        if digit is None:
            return None
        digits.append(str(digit))
    year = int("".join(digits))
    if 1900 <= year <= 2099:
        return year
    return None


def _classify_hk_period_projection(
    *,
    title: str,
    category_text: str,
    annual_ends: tuple[date, ...] = (),
) -> CnReportPeriodProjection | None:
    """先按披露易分类确定报告家族，再从分类与标题投影身份和覆盖财期。

    Args:
        title: 公告标题。
        category_text: 分类文本。
        annual_ends: 同公司有明确截止日的年度业绩证据。

    Returns:
        分类与标题共同形成的财期投影；任何歧义返回 ``None``。

    Raises:
        无。
    """

    if has_unresolved_end_date(title):
        return None
    normalized_category = category_text.strip().upper()
    if not normalized_category:
        return None
    is_results = _contains_any_token(normalized_category, _HK_CATEGORY_RESULTS_MARKERS)
    is_report = _contains_any_token(normalized_category, _HK_CATEGORY_REPORT_MARKERS)
    if is_results == is_report:
        return None
    normalized_material_facts = f"{category_text} {title}".upper()
    if is_report:
        has_h1 = _contains_any_token(normalized_material_facts, _HK_REPORT_H1_TOKENS)
        facts_without_h1_phrases = _remove_tokens(normalized_material_facts, _HK_REPORT_H1_TOKENS)
        has_fy = _contains_any_token(facts_without_h1_phrases, _HK_REPORT_FY_TOKENS)
        has_results_period = _contains_any_token(
            normalized_material_facts,
            _HK_REPORT_FORBIDDEN_RESULT_TOKENS,
        )
        if has_results_period or has_fy == has_h1:
            return None
        identity: CnFiscalPeriod = "FY" if has_fy else "H1"
        end = report_end_date(title)
        if end is not None and annual_ends:
            calendar_period = fiscal_quarter_at(end, annual_ends)
            if calendar_period is None or calendar_period[1] != (4 if has_fy else 2):
                return None
        return CnReportPeriodProjection(identity_period=identity, covered_periods=(identity,))

    matched: set[CnFiscalPeriod] = {
        period
        for period, tokens in _HK_RESULTS_PERIOD_TOKENS.items()
        if _contains_any_token(normalized_material_facts, tokens)
    }
    end = report_end_date(title)
    calendar_period = fiscal_quarter_at(end, annual_ends) if end is not None else None
    if calendar_period is not None:
        if not matched and not _contains_any_token(normalized_material_facts, _HK_QUARTER_LENGTH_TOKENS):
            return None
        calendar_identity: CnFiscalPeriod = ("Q1", "Q2", "Q3", "Q4")[calendar_period[1] - 1]
        matched.add(calendar_identity)
    elif end is not None and annual_ends:
        return None
    result_identity = _resolve_hk_results_identity(matched)
    if result_identity is None:
        return None
    if result_identity == "Q2":
        return CnReportPeriodProjection(identity_period="Q2", covered_periods=("H1", "Q2"))
    if result_identity == "Q4":
        return CnReportPeriodProjection(identity_period="Q4", covered_periods=("FY", "Q4"))
    return CnReportPeriodProjection(identity_period=result_identity, covered_periods=(result_identity,))


def _contains_any_token(text: str, tokens: tuple[str, ...]) -> bool:
    """判断大写文本是否包含任一业务 token。

    Args:
        text: 已大写的待匹配文本。
        tokens: 可匹配 token。

    Returns:
        命中任一 token 返回 ``True``。

    Raises:
        无。
    """

    return any(
        (
            bool(re.search(r"(?<![A-Z])" + token + r"(?![A-Z0-9])", text))
            if re.fullmatch(r"Q[1-4]", token)
            else token.upper() in text
        )
        for token in tokens
    )


def _remove_tokens(text: str, tokens: tuple[str, ...]) -> str:
    """移除已确认为更具体语义的短语，避免中文子串产生伪冲突。

    Args:
        text: 已大写的事实文本。
        tokens: 需要优先消费的更具体短语。

    Returns:
        移除 token 后的文本。

    Raises:
        无。
    """

    remaining = text
    for token in tokens:
        remaining = remaining.replace(token.upper(), " ")
    return remaining


def _resolve_hk_results_identity(matched: set[CnFiscalPeriod]) -> CnFiscalPeriod | None:
    """只接受唯一季度事实；期间长度三个月不产生独立季度信号。

    Args:
        matched: 标题命中的季度候选集合。

    Returns:
        唯一季度身份；缺失或相互冲突返回 ``None``。

    Raises:
        无。
    """

    return next(iter(matched)) if len(matched) == 1 else None


def _deduplicate_hk_announcements(
    announcements: tuple[HkexnewsRawAnnouncement, ...],
) -> tuple[HkexnewsRawAnnouncement, ...]:
    """按 source ID 去重，并对同 ID 核心事实冲突 fail closed。

    Args:
        announcements: provider 返回的 raw 公告。

    Returns:
        保持首次出现顺序的唯一公告。

    Raises:
        ValueError: 同一 document ID 的核心事实不一致时抛出。
    """

    unique: dict[str, HkexnewsRawAnnouncement] = {}
    for announcement in announcements:
        previous = unique.get(announcement.document_id)
        if previous is None:
            unique[announcement.document_id] = announcement
            continue
        if _hk_announcement_core_facts(previous) != _hk_announcement_core_facts(announcement):
            raise ValueError(f"披露易同一 document_id 核心事实冲突: {announcement.document_id}")
    return tuple(unique.values())


def _hk_announcement_core_facts(
    announcement: HkexnewsRawAnnouncement,
) -> tuple[str, str, str, str, str]:
    """提取同一 HK source ID 必须一致的 provider 核心事实。

    Args:
        announcement: raw 公告。

    Returns:
        URL、分类、标题、披露日期与语言组成的不可变事实 tuple。

    Raises:
        无。
    """

    return (
        announcement.source_url,
        announcement.category_text,
        announcement.title,
        announcement.filing_date,
        announcement.language,
    )


def _pick_best_hk_announcement(items: list[HkexnewsRawAnnouncement]) -> HkexnewsRawAnnouncement | None:
    """从同一披露易 fiscal period/year 中挑选最佳公告。

    Args:
        items: 同组 raw 公告。

    Returns:
        最佳公告；空列表返回 `None`。

    Raises:
        无。
    """

    if not items:
        return None

    def sort_key(item: HkexnewsRawAnnouncement) -> tuple[int, str]:
        return (1 if _is_hk_amended_title(item.title) else 0, item.filing_date)

    return max(items, key=sort_key)


def _is_hk_amended_title(title: str) -> bool:
    """判断披露易标题是否为更正/修订版本。

    Args:
        title: 公告标题。

    Returns:
        是修订版本返回 `True`。

    Raises:
        无。
    """

    upper = title.upper()
    return any(token.upper() in upper for token in _HK_TITLE_AMENDED_TOKENS)


def _is_english_hk_announcement(announcement: HkexnewsRawAnnouncement) -> bool:
    """判断披露易公告是否为英文财报副本。

    Args:
        announcement: raw 公告。

    Returns:
        英文财报副本返回 `True`。

    Raises:
        无。
    """

    if announcement.language == "en":
        return True
    if _looks_like_english_report_text(announcement.title):
        return True
    if not _contains_cjk(announcement.title) and _looks_like_english_report_text(
        f"{announcement.title} {announcement.category_text}"
    ):
        return True
    return False


def _looks_like_english_report_text(text: str) -> bool:
    """判断文本是否像英文财报标题。

    Args:
        text: 待判断文本。

    Returns:
        像英文财报标题时返回 `True`。

    Raises:
        无。
    """

    upper = text.upper()
    return any(token in upper for token in _HK_ENGLISH_REPORT_TITLE_TOKENS)


def _contains_cjk(text: str) -> bool:
    """判断文本是否包含 CJK 字符。

    Args:
        text: 待判断文本。

    Returns:
        包含 CJK 字符返回 `True`。

    Raises:
        无。
    """

    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _build_hk_candidate(
    *,
    announcement: HkexnewsRawAnnouncement,
    period_projection: CnReportPeriodProjection,
    fiscal_year: int,
    head_meta: CnReportHeadMeta,
) -> CnReportCandidate:
    """把披露易 raw announcement 构造为候选对象。

    Args:
        announcement: 已选择 raw 公告。
        period_projection: 已分类的身份与覆盖财期。
        fiscal_year: 财年。
        head_meta: PDF HEAD 元数据。

    Returns:
        HKEXNews candidate。

    Raises:
        无。
    """

    end = report_end_date(announcement.title)
    return CnReportCandidate(
        provider="hkexnews",
        source_id=announcement.document_id,
        source_url=announcement.source_url,
        title=announcement.title,
        language=announcement.language,
        category_text=announcement.category_text,
        report_date=end.isoformat() if end is not None else None,
        filing_date=announcement.filing_date,
        fiscal_year=fiscal_year,
        period_projection=period_projection,
        amended=_is_hk_amended_title(announcement.title),
        content_length=head_meta.content_length,
        etag=head_meta.etag,
        last_modified=head_meta.last_modified,
    )
