"""CN/HK raw announcement 到财报候选的业务选择真源。

下载器只负责 HTTP、JSON 与 provider raw 字段归一；本模块负责产品级财报
筛选、语言过滤、财期/财年推断、同 period/year 去重以及
``CnReportCandidate`` 构造。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Final, Optional, TypeAlias

from dayu.fins.pipelines.cn_download_models import (
    CnFiscalPeriod,
    CnReportCandidate,
    CnReportHeadMeta,
    CnReportQuery,
    CninfoRawAnnouncement,
    HkexnewsRawAnnouncement,
)


ReadHeadMeta: TypeAlias = Callable[[str], CnReportHeadMeta]
"""读取 PDF HEAD 元数据的窄 callable 类型。"""

_PERIOD_SORT_KEY: Final[dict[CnFiscalPeriod, int]] = {
    "FY": 0,
    "H1": 1,
    "Q1": 2,
    "Q2": 3,
    "Q3": 4,
    "Q4": 5,
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
_HK_PERIOD_INFERENCE_TOKENS: Final[dict[CnFiscalPeriod, tuple[str, ...]]] = {
    "FY": ("ANNUAL REPORT", "年報", "年报", "年度報告", "年度报告"),
    "H1": ("INTERIM REPORT", "HALF-YEAR", "HALF YEAR", "中期報告", "中期报告", "半年報", "半年度報告"),
    "Q1": ("FIRST QUARTER", "FIRST QUARTERLY", "THREE MONTHS", "3 MONTHS", "第一季度", "第一季", "一季度", "一季", "三個月", "三个月"),
    "Q2": ("SECOND QUARTER", "SECOND QUARTERLY", "SIX MONTHS", "6 MONTHS", "HALF YEAR", "Q2", "第二季度", "第二季", "二季度", "二季", "六個月", "六个月", "半年"),
    "Q3": ("THIRD QUARTER", "THIRD QUARTERLY", "NINE MONTHS", "9 MONTHS", "第三季度", "第三季", "三季度", "三季", "九個月", "九个月"),
    "Q4": ("FOURTH QUARTER", "FOURTH QUARTERLY", "TWELVE MONTHS", "12 MONTHS", "FULL YEAR", "Q4", "第四季度", "第四季", "四季度", "四季", "十二個月", "十二个月", "全年"),
}
_HK_TITLE_YEAR_PATTERN: Final[re.Pattern[str]] = re.compile(r"(20\d{2}|19\d{2})")
_HK_TITLE_CHINESE_YEAR_PATTERN: Final[re.Pattern[str]] = re.compile(r"([零〇一二三四五六七八九]{4})年")
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
    for period in query.target_periods:
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
    candidates.sort(key=lambda item: (-item.fiscal_year, _PERIOD_SORT_KEY[item.fiscal_period]))
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
    for item in announcements:
        if _is_english_hk_announcement(item):
            continue
        inferred_period = _infer_fiscal_period_from_text(
            title=item.title,
            category_text=item.category_text,
        )
        if inferred_period not in query.target_periods:
            continue
        fiscal_year = _infer_hk_fiscal_year(
            title=item.title,
            filing_date=item.filing_date,
        )
        if fiscal_year is None:
            continue
        grouped.setdefault((inferred_period, fiscal_year), []).append(item)

    candidates: list[CnReportCandidate] = []
    for (period, fiscal_year), items in grouped.items():
        best = _pick_best_hk_announcement(items)
        if best is None:
            continue
        candidates.append(
            _build_hk_candidate(
                announcement=best,
                period=period,
                fiscal_year=fiscal_year,
                head_meta=read_head_meta(best.source_url),
            )
        )
    candidates.sort(key=lambda item: (-item.fiscal_year, _PERIOD_SORT_KEY[item.fiscal_period]))
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
        fiscal_period=period,
        amended=any(token in announcement.title for token in _CNINFO_TITLE_AMENDED_TOKENS),
        content_length=head_meta.content_length,
        etag=head_meta.etag,
        last_modified=head_meta.last_modified,
    )


def _infer_hk_fiscal_year(title: str, filing_date: str) -> int | None:
    """从披露易标题和披露日期推断财年。

    Args:
        title: 公告标题。
        filing_date: 披露日期。

    Returns:
        推断财年；无法解析返回 `None`。

    Raises:
        无。
    """

    matched = _HK_TITLE_YEAR_PATTERN.search(title)
    if matched is not None:
        return int(matched.group(1))
    chinese_matched = _HK_TITLE_CHINESE_YEAR_PATTERN.search(title)
    if chinese_matched is not None:
        chinese_year = _parse_chinese_digit_year(chinese_matched.group(1))
        if chinese_year is not None:
            return chinese_year
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", filing_date):
        return int(filing_date[:4])
    return None


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


def _infer_fiscal_period_from_text(
    *,
    title: str,
    category_text: str,
) -> CnFiscalPeriod | None:
    """从披露易标题和分类文本推断财期。

    Args:
        title: 公告标题。
        category_text: 分类文本。

    Returns:
        推断财期；无法判定返回 `None`。

    Raises:
        无。
    """

    combined = f"{title} {category_text}".upper()
    normalized_category = category_text.upper()
    if "季度" in category_text or "QUARTER" in normalized_category:
        order: tuple[CnFiscalPeriod, ...] = ("Q4", "Q3", "Q2", "Q1", "H1", "FY")
    else:
        order = ("H1", "FY", "Q4", "Q3", "Q2", "Q1")
    for period in order:
        tokens = _HK_PERIOD_INFERENCE_TOKENS[period]
        if any(token.upper() in combined for token in tokens):
            return period
    return None


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
    period: CnFiscalPeriod,
    fiscal_year: int,
    head_meta: CnReportHeadMeta,
) -> CnReportCandidate:
    """把披露易 raw announcement 构造为候选对象。

    Args:
        announcement: 已选择 raw 公告。
        period: 财期。
        fiscal_year: 财年。
        head_meta: PDF HEAD 元数据。

    Returns:
        HKEXNews candidate。

    Raises:
        无。
    """

    return CnReportCandidate(
        provider="hkexnews",
        source_id=announcement.document_id,
        source_url=announcement.source_url,
        title=announcement.title,
        language=announcement.language,
        filing_date=announcement.filing_date,
        fiscal_year=fiscal_year,
        fiscal_period=period,
        amended=_is_hk_amended_title(announcement.title),
        content_length=head_meta.content_length,
        etag=head_meta.etag,
        last_modified=head_meta.last_modified,
    )
