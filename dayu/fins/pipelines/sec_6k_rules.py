"""SEC 6-K 规则真源模块。"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue
from dayu.fins.processors.source_text import decode_source_bytes

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dayu.fins.downloaders.sec_downloader import RemoteFileDescriptor


@dataclass(frozen=True)
class _SixKCandidateDiagnosis:
    """6-K 候选文件的同源分类结果。"""

    filename: str
    filename_priority: int
    classification: str
    is_primary_document: bool


_6K_CONTEXTUAL_ANNUAL_EXCLUDE_PATTERNS: tuple[str, ...] = (
    r"\bannual\s+report\b",
    r"\bintegrated\s+annual\s+report\b",
    r"\bannual\s+financial\s+statements?\b",
)

_6K_TITLE_EXCLUDE_SCAN_CHARS = 420
_6K_EXCLUDE_PREFIX_SCAN_CHARS = 1600
_6K_ANNUAL_CONTEXT_SCAN_CHARS = 800
_6K_KEEP_SCAN_CHARS = 4000

_6K_TITLE_EXCLUDE_PATTERNS: tuple[str, ...] = (
    r"\banalyst\s+(visit|day)\b",
    r"Repurchase Right Notification",
    r"\b(?:proposed\s+offering|pricing|issuance|exchange|repurchase)\b.{0,80}\bConvertible Senior Notes\b",
    r"Updates on Its Investments",
    r"\bstrategic\s+review\b",
    r"\bquarterly\s+activities\s+and\s+cashflow\s+report\b",
    r"\b(?:agrees\s+to\s+acquire|completes?\s+acquisition\s+of|entered\s+into\s+a\s+definitive\s+merger\s+agreement)\b",
    r"\bcapitalization\s+and\s+indebtedness\b",
    r"\bnext\s+day\s+disclosure\s+return\b",
    r"\bdiscloseable\s+transaction\b",
    r"(clinical|trial|study).{0,60}(interim|half.?year).{0,60}results?",
    r"(open-label|extension).{0,80}(clinical\s+dataset|interim\s+results?)",
)

_6K_STRONG_EXCLUDE_PATTERNS: tuple[str, ...] = (
    r"\bdate\s+of\s+(audit\s+committee|board)\s+meeting\b",
    r"\bfinancial\s+results?\s+announcement\s+date\b",
    r"\binvitation\s+to\s+the\s+annual\s+general\s+meeting\b",
    r"\bprofit\s+warning\b",
    r"\bprofit\s+alert\b",
    r"\btranscript\s+of\s+the\s+earnings\s+call\b",
    r"\bearnings\s+(conference\s+call\s+)?transcript\b",
    r"DATE OF AUDIT COMMITTEE MEETING AND ANNOUNCEMENT DATE OF",
    r"\bproduction\s+results?\b.{0,160}\b(earnings?\s+call|conference\s+call|financial\s+results?\s+will\s+be\s+released|will\s+be\s+released)\b",
    r"\boperating\s+update\b.{0,240}\bfinancial\s+results?\s+are\s+only\s+provided\s+on\s+a\s+six-?monthly\s+basis\b",
)

_6K_STRONG_KEEP_PATTERNS: tuple[str, ...] = (
    r"Financial Results and Business Updates",
    r"Key Highlights for the (First|Second|Third|Fourth) Quarter",
    r"Reports?\s+(?:the\s+)?(?:(?:First|Second|Third|Fourth)[-\s]+Quarter|Q[1-4])(?:\s+and\s+(?:Full[-\s]+Year(?:\s+\d{4})?|\d{4}\s+Full[-\s]+Year))?\s+Financial\s+Results",
    r"Reports?\s+Full[-\s]+Year(?:\s+\d{4})?\s+Financial\s+Results?\b.{0,120}\b(?:Provides?|with)\b.{0,120}\b(?:Fourth[-\s]+Quarter|Q4)\b.{0,80}\bBusiness\s+Update\b",
    r"Reports?\s+Half[-\s]+Year(?:\s+\d{4})?\s+Financial\s+Results?\b.{0,120}\b(?:Provides?|with)\b.{0,120}\b(?:Second[-\s]+Quarter|Q2)\b.{0,80}\bBusiness\s+Update\b",
    r"Reports Unaudited .* Financial Results",
    r"\b(?:(?:[1-4]Q(?:\s+\d{2,4})?|[1-4]Q\d{2,4})|(?:Q[1-4](?:\s+\d{2,4})?))\s+(results?|earnings?|financial\s+results?)\b",
    r"\b(?:Financial\s+Management\s+Review|Management\s+Review)\b.{0,60}\b(?:[1-4]Q\d{2,4}|Q[1-4](?:\s+\d{2,4})?)\b",
    r"\b(?:[1-4]Q\d{2,4}|Q[1-4](?:\s+\d{2,4})?)\b.{0,80}\b(?:Financial\s+Management\s+Review|Quarterly\s+YTD\s+Report)\b",
    r"\bQ[1-4](?:\s+\d{4})?\s+and\s+Full\s+Year(?:\s+\d{4})?\s+Financial\s+Results\b",
    r"\bQ[1-4](?:\s+\d{4})?\s+Update\b.{0,240}\bFinancial\s+Statements\b",
    r"\bFinancial\s+Report\b.{0,80}\b(?:[1-4](?:st|nd|rd|th)\.?\s+quarter|first\s+quarter|second\s+quarter|third\s+quarter|fourth\s+quarter)\b",
    r"(?<![-/])Announces.{0,80}Quarter.{0,80}Results",
    r"\b(?:reports?|published|publish(?:es|ed)?)\b.{0,80}\b(?:first|second|third|fourth)[-\s]+quarter\b.{0,40}\bresults?\b",
    r"\breported\s+its\s+financial\s+results\s+for\s+the\s+three\s+and\s+twelve\s+month\s+periods\s+ending\b",
    r"announced its financial results for the quarter",
    r"QUARTER \d{4} RESULTS",
    r"Unaudited.{1,60}Financial Results",
    r"\bunaudited\s+condensed\s+consolidated\s+financial\s+statements?\b.{0,160}\b(?:three\s+and\s+six|three\s+and\s+nine|quarter\s+ended|six\s+months?\s+ended|nine\s+months?\s+ended)\b",
    r"(first|second|third|fourth)[-\s]+quarter(?:\s+\d{4})?\s+(results?|earnings?|financial)",
    r"\bQ[1-4](?:\s+\d{4})?\s+(earnings?|financial\s+results?)\b",
    r"\b(earnings?|financial\s+results?)\b.{0,30}\bQ[1-4](?:\s+\d{4})?\b",
    r"(interim|half.?year|semi.?annual).{0,30}(financial\s+(statement|report)|earnings?|results?\s+(announcement|release|report))",
    r"\binterim\s+report\b.{0,120}\bquarter\s+ended\b",
    r"\b(?:unaudited\s+)?condensed\s+consolidated\s+financial\s+statements?\b.{0,240}\b(?:three\s+and\s+six|three\s+and\s+nine)\s+months?\s+ended\b",
    r"\binterim\s+report(?:\b|(?=[A-Z0-9])).{0,240}\b(financial\s+information|financial\s+statements?|balance\s+sheets?|statement\s+of\s+cash\s+flows?|statement\s+of\s+comprehensive\s+(income|loss))\b",
    r"(results?|earnings?|financial\s+results?|financial\s+report).{0,80}(quarter|three\s+months?|six\s+months?|nine\s+months?|half.?year|interim).{0,40}(ended|end)",
    r"(quarter|three\s+months?|six\s+months?|nine\s+months?|half.?year|interim).{0,40}(ended|end).{0,80}(results?|earnings?|financial\s+results?|financial\s+report)",
    r"Quarterly\s+Report\s+for\s+(the\s+)?(Period|Quarter)",
    r"Interim\s+Results?\s+Announcement",
    r"Exhibit\s+99\.[12]\b.{0,80}(quarter|quarterly|interim).{0,40}(results?|report|financial)",
)

_6K_IFRS_RECON_PATTERNS: tuple[str, ...] = (
    r"RECONCILIATION BETWEEN U\.S\. GAAP AND IFRS",
    r"UNAUDITED INTERIM CONDENSED CONSOLIDATED",
    r"unaudited consolidated (results|financial statements)",
)

_6K_NEUTRAL_PATTERNS: tuple[str, ...] = (
    r"Announcement from [A-Za-z0-9][A-Za-z0-9.,&' -]*(Group|Holdings?|Limited|Ltd\.?|Inc\.?|Corp\.?|Corporation)",
    r"\binvestor\s+meeting\b",
    r"\binvestor\s+presentation\b",
    r"\bquarterly\s+results?\s+presentations?\b",
)

_6K_XBRL_TAXONOMY_PATTERNS: tuple[str, ...] = (
    r"xbrli:",
    r"iso4217:",
    r"(?:us-gaap|ifrs-full):",
)

_6K_XBRL_FISCAL_QUARTER_PATTERN = re.compile(r"20\d{2}Q[1-4](?:true|false)?", re.IGNORECASE)
_6K_XBRL_COMPACT_DATE_RANGE_PATTERN = re.compile(r"(20\d{2}-\d{2}-\d{2})(20\d{2}-\d{2}-\d{2})")
_6K_VALID_QUARTER_END_MONTH_DAYS: frozenset[tuple[int, int]] = frozenset(
    {(3, 31), (6, 30), (9, 30), (12, 31)}
)
_6K_QUARTER_RANGE_MIN_DAYS = 80
_6K_QUARTER_RANGE_MAX_DAYS = 100
_6K_HALF_YEAR_RANGE_MIN_DAYS = 170
_6K_HALF_YEAR_RANGE_MAX_DAYS = 190


def _infer_filename_from_uri(uri: str) -> str:
    """从 URI 推断文件名。

    Args:
        uri: 文件 URI。

    Returns:
        文件名或空字符串。

    Raises:
        无。
    """

    raw = str(uri or "").strip()
    if not raw:
        return ""
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.rstrip("/")
    if not raw:
        return ""
    return Path(raw).name or raw.split("/")[-1]


def _extract_head_text(payload: bytes, max_lines: int) -> str:
    """提取文件前若干行可读文本，自动剥离 HTML 标签。

    若内容检测为 HTML（去除前置空白后以 ``<`` 开头），使用 lxml 提取纯文本
    后过滤空行再截取；否则直接按 UTF-8 行分割。

    Args:
        payload: 文件内容字节。
        max_lines: 最大行数。

    Returns:
        文本内容（空行已过滤）。

    Raises:
        FinsSourceDecodeError: payload 不是合法 UTF-8 时抛出。
    """

    from lxml import html as lxml_html

    raw = decode_source_bytes(payload)
    if raw.lstrip().startswith("<"):
        try:
            tree = lxml_html.fromstring(raw)
            text = tree.text_content()
        except Exception:
            text = raw
    else:
        text = raw
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:max_lines])


def _normalize_6k_document_type(raw_type: JsonValue) -> Optional[str]:
    """规范化 6-K 文档类型文本。

    Args:
        raw_type: 原始文档类型（可能为空）。

    Returns:
        规范化后的类型字符串；空值返回 `None`。

    Raises:
        无。
    """

    normalized = str(raw_type or "").strip().upper()
    if not normalized:
        return None
    return normalized


def _score_6k_filename(
    filename: str,
    primary_document: str,
    sec_document_type: Optional[str] = None,
) -> tuple[int, str]:
    """计算 6-K 文件名的排序权重。

    Donnelley 体系使用 ``dex991`` 命名，Edgar Filing Services 体系使用
    ``ex99-1`` / ``ex99_1`` 命名。两种格式均需识别。

    Args:
        filename: 文件名。
        primary_document: 主文件名。
        sec_document_type: SEC 文档类型（如 `EX-99.1`）。

    Returns:
        排序权重元组。值越小优先级越高。

    Raises:
        无。
    """

    lowered = filename.lower()
    normalized_type = _normalize_6k_document_type(sec_document_type)
    if normalized_type == "EX-99.1":
        return (0, lowered)
    if normalized_type in {"EX-99.2", "EX-99.3"}:
        return (1, lowered)
    if normalized_type and normalized_type.startswith("EX-99"):
        return (2, lowered)
    if "dex991" in lowered or re.search(r"ex99[\-_]?1", lowered):
        return (0, lowered)
    if "dex992" in lowered or "dex993" in lowered or re.search(r"ex99[\-_]?[23]", lowered):
        return (1, lowered)
    if "dex99" in lowered or "ex99" in lowered:
        return (2, lowered)
    if primary_document and lowered == primary_document.lower():
        return (3, lowered)
    return (4, lowered)


def _collect_6k_candidate_entries(
    file_entries: list[dict[str, JsonValue]],
    primary_document: str,
) -> list[tuple[str, Optional[str]]]:
    """收集 6-K 候选文件名及文档类型。

    规则：
    - 始终保留当前 `primary_document`，即使它不是 HTML；
    - 其余候选仅纳入 `.htm/.html` 文件；
    - 同名条目重复出现时，优先保留非空 `sec_document_type`。

    Args:
        file_entries: 文件条目列表。
        primary_document: 当前主文件名。

    Returns:
        去重后的 `(filename, sec_document_type)` 列表。

    Raises:
        无。
    """

    normalized_primary = str(primary_document).strip()
    primary_lower = normalized_primary.lower()
    indexed: dict[str, tuple[str, Optional[str]]] = {}
    if normalized_primary:
        indexed[primary_lower] = (normalized_primary, None)

    for item in file_entries:
        name = str(item.get("name") or _infer_filename_from_uri(str(item.get("uri") or ""))).strip()
        if not name:
            continue
        lowered_name = name.lower()
        if lowered_name != primary_lower and not lowered_name.endswith((".htm", ".html")):
            continue
        normalized_type = _normalize_6k_document_type(
            item.get("sec_document_type") or item.get("type")
        )
        existing = indexed.get(lowered_name)
        if existing is None:
            indexed[lowered_name] = (name, normalized_type)
            continue
        if existing[1] is None and normalized_type is not None:
            indexed[lowered_name] = (existing[0], normalized_type)

    return sorted(indexed.values(), key=lambda item: item[0].lower())


def _is_positive_6k_classification(classification: str) -> bool:
    """判断 6-K 分类是否属于应保留的季度结果。

    Args:
        classification: `_classify_6k_text()` 返回的分类标签。

    Returns:
        属于季度结果返回 `True`。

    Raises:
        无。
    """

    return classification in {"RESULTS_RELEASE", "IFRS_RECON"}


def _select_best_positive_6k_candidate(
    diagnoses: list[_SixKCandidateDiagnosis],
) -> Optional[_SixKCandidateDiagnosis]:
    """从已分类的 6-K 候选中选出最佳季度正文。

    选择过程严格依赖 `_classify_6k_text()`：
    - 只在候选被真源判成季度结果时参与竞争；
    - 命中多个季度候选时，再用 `_score_6k_filename()` 打破平局。

    Args:
        diagnoses: 候选分类结果列表。

    Returns:
        最佳季度候选；若不存在季度候选则返回 `None`。

    Raises:
        无。
    """

    positive_candidates = [item for item in diagnoses if _is_positive_6k_classification(item.classification)]
    if not positive_candidates:
        return None
    return min(
        positive_candidates,
        key=lambda item: (item.filename_priority, item.filename.lower()),
    )


def _select_6k_target_name(file_entries: list[dict[str, JsonValue]], primary_document: str) -> str:
    """选择 6-K 用于筛选的目标文件名。

    Args:
        file_entries: 文件条目列表。
        primary_document: 主文件名。

    Returns:
        目标文件名。

    Raises:
        ValueError: 无可用文件时抛出。
    """

    candidates: list[tuple[str, Optional[str]]] = []
    for item in file_entries:
        name = str(item.get("name") or _infer_filename_from_uri(str(item.get("uri") or ""))).strip()
        if name:
            candidates.append(
                (
                    name,
                    _normalize_6k_document_type(
                        item.get("sec_document_type") or item.get("type")
                    ),
                )
            )
    if not candidates:
        raise ValueError("6-K 文件列表为空，无法筛选")
    primary = str(primary_document).strip()
    candidates.sort(
        key=lambda value: _score_6k_filename(
            filename=value[0],
            primary_document=primary,
            sec_document_type=value[1],
        )
    )
    return candidates[0][0]


def _try_parse_iso_date(value: str) -> Optional[dt.date]:
    """尝试解析 ISO 日期文本。

    Args:
        value: 形如 ``YYYY-MM-DD`` 的日期字符串。

    Returns:
        解析成功返回日期对象；否则返回 `None`。

    Raises:
        无。
    """

    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _is_quarter_like_date_range(start_value: str, end_value: str) -> bool:
    """判断紧凑日期区间是否像季度披露区间。"""

    start_date = _try_parse_iso_date(start_value)
    end_date = _try_parse_iso_date(end_value)
    if start_date is None or end_date is None or end_date < start_date:
        return False
    duration_days = (end_date - start_date).days + 1
    if duration_days < _6K_QUARTER_RANGE_MIN_DAYS or duration_days > _6K_QUARTER_RANGE_MAX_DAYS:
        return False
    if start_date.day != 1:
        return False
    return (end_date.month, end_date.day) in _6K_VALID_QUARTER_END_MONTH_DAYS


def _is_half_year_like_date_range(start_value: str, end_value: str) -> bool:
    """判断紧凑日期区间是否像半年/中报披露区间。"""

    start_date = _try_parse_iso_date(start_value)
    end_date = _try_parse_iso_date(end_value)
    if start_date is None or end_date is None or end_date < start_date:
        return False
    duration_days = (end_date - start_date).days + 1
    if duration_days < _6K_HALF_YEAR_RANGE_MIN_DAYS or duration_days > _6K_HALF_YEAR_RANGE_MAX_DAYS:
        return False
    return start_date.month == 1 and start_date.day == 1 and end_date.month == 6 and end_date.day == 30


def _has_xbrl_quarter_instance_signal(content: str) -> bool:
    """判断文本是否像季度 XBRL instance 头部。"""

    normalized_prefix = content[:_6K_KEEP_SCAN_CHARS]
    if not _match_any(normalized_prefix, list(_6K_XBRL_TAXONOMY_PATTERNS)):
        return False
    if _6K_XBRL_FISCAL_QUARTER_PATTERN.search(normalized_prefix) is None:
        return False
    for start_value, end_value in _6K_XBRL_COMPACT_DATE_RANGE_PATTERN.findall(normalized_prefix):
        if _is_quarter_like_date_range(start_value, end_value) or _is_half_year_like_date_range(start_value, end_value):
            return True
    return False


def _classify_6k_text(content: str) -> str:
    """根据关键词判定 6-K 分类。"""

    if not content:
        return "NO_MATCH"
    normalized_content = " ".join(str(content).split())
    if not normalized_content:
        return "NO_MATCH"
    if _has_future_result_announcement_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_board_meeting_financial_results_notice_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_results_call_or_release_schedule_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_asx_results_transmittal_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_asx_aware_letter_response_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_monthly_operating_results_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_preliminary_results_estimate_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_conference_presentation_notice_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_management_change_announcement_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_agm_announcement_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_annual_financial_statements_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_reporting_change_datapack_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_earnings_call_artifact_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_dividend_distribution_notice_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_capital_return_announcement_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_board_minutes_financial_approval_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_update_note_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_local_exchange_financial_statement_summary_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_official_letter_response_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_operating_statistics_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_investor_event_update_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_forum_presentation_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_capital_markets_adjustment_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_strategy_presentation_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_trading_statement_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _has_operating_update_without_financial_statement_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    normalized_title_prefix = normalized_content[:_6K_TITLE_EXCLUDE_SCAN_CHARS]
    if _match_any(normalized_title_prefix, list(_6K_TITLE_EXCLUDE_PATTERNS)):
        return "EXCLUDE_NON_QUARTERLY"
    normalized_exclude_prefix = normalized_content[:_6K_EXCLUDE_PREFIX_SCAN_CHARS]
    if _match_any(normalized_exclude_prefix, list(_6K_STRONG_EXCLUDE_PATTERNS)):
        return "EXCLUDE_NON_QUARTERLY"
    normalized_keep_prefix = normalized_content[:_6K_KEEP_SCAN_CHARS]
    if _match_any(normalized_keep_prefix, list(_6K_STRONG_KEEP_PATTERNS)):
        return "RESULTS_RELEASE"
    if _match_any(normalized_keep_prefix, list(_6K_IFRS_RECON_PATTERNS)):
        return "IFRS_RECON"
    if _has_xbrl_quarter_instance_signal(normalized_keep_prefix):
        return "RESULTS_RELEASE"
    if _has_non_quarterly_annual_report_signal(normalized_content):
        return "EXCLUDE_NON_QUARTERLY"
    if _match_any(normalized_content, list(_6K_NEUTRAL_PATTERNS)):
        return "NO_MATCH"
    return "NO_MATCH"


def _has_6k_exhibit_candidate(remote_files: list[RemoteFileDescriptor]) -> bool:
    """判断 6-K 远端文件是否包含 EX-99 附件候选。"""

    for descriptor in remote_files:
        document_type = _normalize_6k_document_type(descriptor.sec_document_type)
        if document_type and document_type.startswith("EX-99"):
            return True
        lowered_name = descriptor.name.lower()
        if "dex99" in lowered_name or "ex99" in lowered_name:
            return True
    return False


def _has_6k_xbrl_instance(remote_files: list[RemoteFileDescriptor]) -> bool:
    """判断 6-K 文件集合是否包含 XBRL instance。"""

    for descriptor in remote_files:
        lowered_name = descriptor.name.lower()
        if lowered_name.endswith("_htm.xml"):
            return True
    return False


def _remote_files_have_xbrl_instance(remote_files: list[RemoteFileDescriptor]) -> bool:
    """判断远端文件列表是否包含 XBRL instance。"""

    for descriptor in remote_files:
        if descriptor.name.lower().endswith("_htm.xml"):
            return True
    return False


def _has_future_result_announcement_signal(content: str) -> bool:
    """判断文本是否为“预告型业绩公告”信号。"""

    announcement_patterns = [
        r"\b(to|will)\s+(announce|report|release|publish)\b.{0,100}\b(results?|earnings?)\b",
        r"\bwill\s+issue\s+(its\s+)?(financial\s+)?results?\b",
        r"\b(results?|earnings?)\s+will\s+be\s+released\b",
        r"\bsets?\s+date\s+for\b.{0,120}\b(first|second|third|fourth|q[1-4]|interim|half.?year|full\s+year)\b.{0,80}\b(earnings?|financial)\s+results?\b",
        r"\b(results?|earnings?|financial\s+results?)\s+release\s+schedule(?:\b|[A-Z])",
        r"\bconference\s+call\b.{0,120}\brelated\s+to\s+this\s+release\b",
        r"\bwill\s+hold\b.{0,80}\bconference\s+call\b",
        r"\bwill\s+(host|provide)\b.{0,120}\bupdate\b.{0,80}\b(interim|quarter|half.?year|full\s+year|q[1-4])\b.{0,80}\bresults?\b",
        r"\bconference\s+call\b.{0,80}\b(on|at)\b.{0,40}\b(ET|EDT|GMT|AM|PM)\b",
        r"\bbefore\s+the\s+market\s+opens\b",
        r"\bto\s+report\b.{0,100}\b(interim|quarter|half.?year|full\s+year).{0,80}\bresults?\b",
        r"\bto\s+announce\b.{0,100}\bq[1-4]\b.{0,80}\bresults?\b",
        r"\bnotice\s+of\s+board\s+meeting\b",
        r"\bboard\s+(meeting|of\s+directors)\b.{0,160}\b(considering|approving|approve)\b.{0,160}\b(interim|quarter|half.?year|full\s+year).{0,80}\bresults?\b",
    ]
    disclosed_result_patterns = [
        r"\b(announced|announces)\b.{0,120}\b(financial\s+results?|interim\s+results?|quarter.{0,40}results?)\b(?!\s+release\s+schedule)",
        r"\breported\b.{0,80}\b(results?|earnings?)\b.{0,80}\b(for|ended)\b",
        r"\b(?:announced|announce[sd]?)\b.{0,120}\bhalf\s+year\b.{0,120}\bresults?\b",
        r"\b(?:provides?|provided)\b.{0,120}\b(?:second|fourth|q[24])\b.{0,80}\bbusiness\s+update\b",
        r"\binterim\s+report(?:\b|(?=[A-Z0-9])).{0,240}\b(financial\s+information|balance\s+sheets?|statement\s+of\s+cash\s+flows?|statement\s+of\s+comprehensive\s+(income|loss))\b",
        r"\bunaudited\s+(condensed\s+)?consolidated\s+financial\s+statements?\b",
        r"\bconsolidated\s+balance\s+sheets?\b",
        r"\bconsolidated\s+statements?\s+of\s+(income|operations|cash\s+flows?)\b",
    ]
    return _match_any(content, announcement_patterns) and not _match_any(content, disclosed_result_patterns)


def _has_board_meeting_financial_results_notice_signal(content: str) -> bool:
    """判断文本是否为“董事会将审议财报”的预告公告。

    这类 6-K 常包含：
    - 董事会/审计委员会会议日期；
    - 会议将“consider/approve”财务结果；
    - trading window closure 等配套治理语句。

    共同特点是：尚未披露季度财务正文，只是预告将披露结果。

    Args:
        content: 规范化后的文本。

    Returns:
        命中该类预告公告时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:2200]
    has_board_meeting = _match_any(
        normalized_prefix,
        [
            r"\bnotice\s+of\s+board\s+meeting\b",
            r"\bmeeting\s+of\s+the\s+board\s+of\s+directors\b",
            r"\bboard\s+meeting\b",
            r"\bboard\s+of\s+directors\b.{0,120}\bscheduled\s+to\s+be\s+held\b",
        ],
    )
    if not has_board_meeting:
        return False

    has_future_approval = _match_any(
        normalized_prefix,
        [
            r"\bto\s+consider\s+and\s+approve\b",
            r"\bconsider\s+and\s+approve\b",
            r"\bto\s+consider\b",
            r"\bapproval\s+of\b",
            r"\bapprove\s+the\b",
        ],
    )
    if not has_future_approval:
        return False

    has_financial_results_scope = _match_any(
        normalized_prefix,
        [
            r"\b(audited|unaudited|standalone|consolidated)\b.{0,80}\bfinancial\s+results?\b",
            r"\bfinancial\s+results?\b.{0,120}\b(for|of)\b.{0,80}\b(quarter|year|half.?year|six\s+months?|nine\s+months?)\b",
            r"\b(interim|final)\s+results?\b.{0,120}\b(for|of)\b.{0,80}\b(year|quarter|half.?year|six\s+months?|nine\s+months?)\b",
            r"\bearnings?\b.{0,120}\b(for|of)\b.{0,80}\b(quarter|year|half.?year|six\s+months?|nine\s+months?)\b",
            r"\bquarter(?:/year)?\s+ended\b",
            r"\byear\s+ending\b",
        ],
    )
    if has_financial_results_scope:
        return True

    return re.search(r"\btrading\s+window\b", normalized_prefix, re.IGNORECASE) is not None


def _has_results_call_or_release_schedule_signal(content: str) -> bool:
    """判断文本是否为“结果发布时间/电话会通知”。

    与真实结果新闻稿的区别在于，这类文本会反复描述“将披露/将讨论结果”，
    但正文本身不包含稳定的财务指标或报表标题。

    Args:
        content: 规范化后的文本。

    Returns:
        命中未来结果通知类文本时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:4200]
    explicit_schedule_notice = _match_any(
        normalized_prefix,
        [
            r"\bnotice\s+of\s+announcement\s+of\b.{0,160}\b(?:first|second|third|fourth|q[1-4]|interim|half.?year|full\s+year|\d{4})\b.{0,80}\bresults?\b",
            r"\bsets?\s+date\s+for\s+the\s+release\s+of\b.{0,120}\b(?:full\s+year|half.?year|interim|first|second|third|fourth|q[1-4]|\d{4})\b.{0,80}\bresults?\b",
            r"\bannounced\s+today\s+that\s+it\s+will\s+publish\s+its\b.{0,160}\b(?:first|second|third|fourth|q[1-4]|interim|half.?year|full\s+year|\d{4})\b.{0,80}\bfinancial\s+results?\b",
            r"\bwill\s+publish\b.{0,120}\bfinancial\s+results?\b",
            r"\bwill\s+release\b.{0,120}\bfinancial\s+results?\b.{0,80}\bbefore\s+market\s+open\b",
            r"\bwill\s+report\b.{0,160}\bresults?\b.{0,240}\bhost\s+a\s+conference\s+call\b",
            r"\bannounced\s+today\s+that\s+it\s+will\s+report\b.{0,180}\bresults?\b",
            r"\bplans?\s+to\s+hold\b.{0,140}\bconference\s+call\b.{0,160}\b(?:earnings?|financial\s+results?)\b",
            r"\bannounces?\s+date\s+of\b.{0,80}\bresults?\b.{0,120}\bconference\s+call\b",
            r"\bannouncement\s+regarding\b.{0,120}\bresults?\s+conference\s+call\b",
            r"\b(?:results?|earnings?)\s+release\s+conference\s+and\s+blackout\s+period\b",
            r"\bearnings?\s+release\s+conference\s+call\b",
            r"\bresults?\s+conference\s+call\b",
            r"\bearnings?\s+release\s+date\b",
            r"\b(?:q[1-4]|first|second|third|fourth|full\s+year|half.?year|\d{4}).{0,40}\bresults?\s+call\b",
            r"\bprior\s+notice\s+on\s+disclosure\s+of\s+final\s+earnings\b",
            r"\bfinancial\s+results?\s+and\s+corporate\s+update\s+webcast\b",
            r"\bearnings?\s+release\s+zoom\s+meeting\b",
            r"\bdetails\s+of\s+earning\s+call\b",
            r"\bresults?\s+will\s+be\s+published\s+on\s+the\s+investor\s+relations\s+website\b",
            r"\bresults?\s+release\s+date\s+and\s+conference\s+call\s+date\b",
            r"\bconference\s+call\s+scheduled\s+for\b",
            r"\bconference\s+call\s+for\b.{0,140}\b(?:earnings?|financial\s+results?)\b.{0,80}\bas\s+follows\b",
            r"\bconference\s+call\s+and\s+(?:a\s+)?live\s+audio\s+webcast\s+presentation\b",
            r"\bdetails\s+of\s+the\s+earnings?\s+release\s+conference\s+are\s+as\s+follows\b",
            r"\bdetails\s+for\s+the\s+call\s+are\s+below\b",
            r"\bagenda\s*:\s*(?:first|second|third|fourth|q[1-4]|full\s+year|\d{4}).{0,80}\bearnings?\s+release\b",
            r"\bperformance\s+report\s+dates\b",
            r"\bfinancial\s+performance\s+report\s*:\s*date\b",
            r"\bdate\s+of\b.{0,80}\bearnings?\s+release\b",
            r"\bfinancial\s+results?\s+calendar\b",
            r"\bplanned\s+to\s+be\s+publicly\s+announced\b",
            r"\ba\s+webcast\s+will\s+be\s+held\s+to\s+present\b.{0,200}\bresults?\b",
            r"\bwebcast\s+will\s+be\s+held\s+to\s+present\b.{0,180}\bresults?\b",
            r"\binteractive\s+meeting\b.{0,180}\bq\s*&\s*a\b",
            r"\bwe\s+wi\W*ll\s+present\s+our\b.{0,120}\bresults?\b.{0,180}\binteractive\s+meeting\b",
            r"\bparticipant\s+dial\s+in\b.{0,260}\blive\s+webcast\b",
            r"\bfiling\s+of\s+the\s+company'?s\b.{0,120}\bfinancial\s+statements?\b.{0,200}\bwill\s+be\s+postponed\b",
        ],
    )

    has_call_or_schedule = explicit_schedule_notice or _match_any(
        normalized_prefix,
        [
            r"\bwill\s+host\b.{0,120}\bconference\s+call\b",
            r"\bwill\s+hold\b.{0,120}\bconference\s+call\b",
            r"\bwill\s+hold\b.{0,120}\bearnings\s+conference\b",
            r"\bwill\s+be\s+holding\s+its\b.{0,160}\bearnings?\s+release\s+conference\b",
            r"\bhost\s+conference\s+call\s+and\s+webcast\b",
            r"\bresults?\s+release\s+schedule\b",
            r"\bresults?\s+release\s+scheduled\b",
            r"\bto\s+report\b.{0,120}\b(results?|earnings?)\b",
            r"\bwill\s+report\b.{0,140}\b(results?|earnings?)\b",
            r"\bto\s+announce\b.{0,120}\b(results?|earnings?)\b",
            r"\bto\s+release\b.{0,120}\b(results?|earnings?)\b",
            r"\bwill\s+be\s+releasing\b.{0,120}\bresults?\b",
            r"\bannounces?\b.{0,120}\bresults?\s+release\s+date\b",
            r"\bin\s+advance\s+of\s+the\s+publication\s+of\b.{0,120}\bearnings?\s+release\b",
            r"\bconference\s+call\b.{0,160}\bto\s+discuss\b.{0,120}\bfinancial\s+results?\b",
            r"\bhost\s+an\s+earnings?\s+call\b.{0,220}\bfinancial\s+results?\b",
            r"\bearnings?\s+call\b.{0,180}\bfinancial\s+results?\b",
            r"\bzoom\s+meeting\b.{0,160}\binvestors?\s+and\s+analysts?\b",
            r"\blive\s+webcast\s+of\s+the\s+conference\s+and\s+the\s+presentation\s+materials\s+will\s+be\s+available\b",
            r"\bearnings\s+release\s+materials\s+will\s+be\s+posted\s+on\s+the\s+website\b",
            r"\bpurpose\s+of\s+ir\s*:\s*attending\s+the\s+conferences?\b",
        ],
    )
    if not has_call_or_schedule:
        return False

    has_results_subject = explicit_schedule_notice or _match_any(
        normalized_prefix,
        [
            r"\bfinancial\s+results?\b",
            r"\bearnings?\b",
            r"\bquarterly\s+results?\b",
            r"\bresults?\s+call\b",
            r"\bresults?\s+release\b",
            r"\b(?:first|second|third|fourth|q[1-4]|full\s+year|half.?year|\d{4})\b.{0,60}\bresults?\b",
        ],
    )
    if not has_results_subject:
        return False

    # 预告类 notice 常在尾部“About the Company”段落里提到历史 revenues / net income，
    # 这些弱指标信号不足以推翻前缀中已经成立的“将发布结果”语义。只有出现稳定的
    # statements / financial highlights / results-for 结构，才视为当前文档已真正披露结果。
    has_strong_actual_disclosure = _has_strong_current_results_disclosure_signal(normalized_prefix)
    has_actual_disclosure = _has_current_period_financial_disclosure_signal(normalized_prefix)
    if explicit_schedule_notice and not has_strong_actual_disclosure:
        return True
    return not has_actual_disclosure


def _has_current_period_financial_disclosure_signal(content: str) -> bool:
    """判断文本是否包含“当期结果已披露”的稳定信号。

    这里只接受两类证据：
    - 财报正文常见的结构化信号，如 financial highlights / statements；
    - 与当期期间锚点绑定的指标披露，而不是公司简介里的泛化指标。

    Args:
        content: 规范化后的文本。

    Returns:
        命中当期结果披露信号时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:4200]
    if _has_strong_current_results_disclosure_signal(normalized_prefix):
        return True
    return _match_any(
        normalized_prefix,
        [
            r"\bquarterly\s+results?\s+include\b.{0,120}\b(?:revenues?|net\s+income|adjusted\s+ebitda|ebitda|operating\s+income|cash\s+flow)\b",
            r"\b(?:first|second|third|fourth|q[1-4]|half.?year|full\s+year|interim|three\s+months?|six\s+months?|nine\s+months?)\b.{0,120}\b(?:revenues?|net\s+income|adjusted\s+ebitda|ebitda|operating\s+income|cash\s+flow)\b",
            r"\b(?:revenues?|net\s+income|adjusted\s+ebitda|ebitda|operating\s+income|cash\s+flow)\b.{0,120}\b(?:first|second|third|fourth|q[1-4]|half.?year|full\s+year|interim|three\s+months?|six\s+months?|nine\s+months?|quarter|year)\b",
            r"\b(?:revenues?|sales|net\s+income|adjusted\s+ebitda|ebitda|operating\s+income|cash\s+flow)\b.{0,40}\b(?:was|were|amounted\s+to|totaled|reached)\b",
        ],
    )


def _has_management_change_announcement_signal(content: str) -> bool:
    """判断文本是否为管理层变动公告。"""

    normalized_prefix = " ".join(content.split())[:420]
    management_change_patterns = [
        r"\b(?:appoints|appointed|appointment\s+of)\b.{0,140}\b(chief\s+financial\s+officer|cfo|chief\s+executive\s+officer|ceo)\b",
        r"\b(?:ceo|cfo)\s+transition\b",
        r"\bsuccession\s+plan\b",
        r"\bannounces?\s+change\s+of\s+independent\s+director\b",
        r"\bappointment\s+of\b.{0,80}\bindependent\s+director\b",
        r"\bresign(?:s|ed)\b.{0,80}\bindependent\s+director\b",
    ]
    return _match_any(normalized_prefix, management_change_patterns)


def _has_asx_results_transmittal_signal(content: str) -> bool:
    """判断文本是否为 ASX 结果转发壳公告。

    这类材料本身只是在告知“相关结果材料已经向 ASX 提交”，正文不会继续展开
    当期财务报表，而是把 `earnings release`、`presentation`、`Appendix 4E`
    等附件名称列成清单。

    Args:
        content: 规范化后的文本。

    Returns:
        命中 ASX 转发壳公告时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:2400]
    has_asx_cover_heading = _match_any(
        normalized_prefix,
        [
            r"\bresults?\s+for\s+announcement\s+to\s+the\s+market\b",
            r"\bhas\s+filed\s+the\s+following\s+documents?\s+with\s+the\s+asx\b",
        ],
    )
    if not has_asx_cover_heading:
        return False
    return _match_any(
        normalized_prefix,
        [
            r"\bearnings\s+release\b",
            r"\bmanagement'?s\s+analysis\s+of\s+results\b",
            r"\bearnings\s+presentation\b",
            r"\bcondensed\s+consolidated\s+financial\s+statements?\b",
            r"\bappendix\s+4e\b",
            r"\bannual\s+report\s+on\s+form\s+20-f\b",
        ],
    )


def _has_asx_aware_letter_response_signal(content: str) -> bool:
    """判断文本是否为回复 ASX aware letter 的说明函。

    Args:
        content: 规范化后的文本。

    Returns:
        命中 aware letter 回复函时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:1800]
    return _match_any(
        normalized_prefix,
        [
            r"\bresponse\s+to\s+asx\s+aware\s+letter\b",
            r"\basx\s+compliance\b.{0,120}\baware\s+letter\b",
        ],
    )


def _has_monthly_operating_results_signal(content: str) -> bool:
    """判断文本是否为月度经营数据/销售公告。

    这类材料通常是台湾市场月度营运公告，正文会写 `operating results for June`
    或 `sales`，但不会提供季度三大表。

    Args:
        content: 规范化后的文本。

    Returns:
        命中月度经营数据公告时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:4200]
    has_monthly_heading = _match_any(
        normalized_prefix,
        [
            r"\boperating\s+results?\s+for\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+20\d{2}\b",
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+20\d{2}\s+sales\b",
        ],
    )
    if not has_monthly_heading:
        return False
    if _has_strong_current_results_disclosure_signal(normalized_prefix):
        return False
    return _match_any(
        normalized_prefix,
        [
            r"\bdate\s+of\s+events\b",
            r"\bcontents\s*:",
            r"\bhead\s+office\b",
            r"\bsales\b",
        ],
    )


def _has_preliminary_results_estimate_signal(content: str) -> bool:
    """判断文本是否为 preliminary / estimated 结果预估材料。

    只有在正文同时出现“预估性标题”和“尚未完成结账/财务报表尚不可用/仅为区间估计”
    这类明确限制语时，才视为应剔除的非季度结果正文。

    Args:
        content: 规范化后的文本。

    Returns:
        命中 preliminary estimate 材料时返回 ``True``。

    Raises:
        无。
    """

    # 这类 preliminary 样本常先铺较长的封面/免责声明，限制语会延后到正文中段。
    normalized_prefix = " ".join(content.split())[:4200]
    has_preliminary_heading = _match_any(
        normalized_prefix,
        [
            r"\bpreliminary\s+results?\s+for\s+the\b",
            r"\bpreliminary\s+expected\s+financial\s+results?\b",
            r"\bpreliminary\s+estimated\b",
            r"\bpreliminary\s+unaudited\b.{0,80}\bresults?\b",
            r"\bcertain\s+preliminary\s+estimated\b",
            r"\bestimates?\s+of\s+certain\s+preliminary\s+unaudited\s+financial\s+results?\b",
            r"\bselected\s+unaudited\s+financial\s+information\b",
        ],
    )
    if not has_preliminary_heading:
        return False
    return _match_any(
        normalized_prefix,
        [
            r"\bnot\s+yet\s+completed\s+our\s+closing\s+procedures\b",
            r"\bfinancial\s+closing\s+procedures?\b.{0,120}\bnot\s+yet\s+complete\b",
            r"\bunaudited\s+consolidated\s+financial\s+statements?\b.{0,120}\bnot\s+yet\s+available\b",
            r"\bsubject\s+to\s+(?:the\s+company(?:['’]s)?\s+)?detailed\s+quarter[\s-]*end\s+closing\s+procedures\b",
            r"\bsubject\s+to\s+revision\b",
            r"\bsubject\s+to\s+change\b.{0,120}\bcompletion\s+of\s+the\s+audit\s+process\b",
            r"\branges?\s+have\s+been\s+provided\b",
            r"\bis\s+estimated\s+to\s+be\s+in\s+the\s+range\s+of\b",
            r"\btentative\s+consolidated\b",
            r"\bfinal\s+results?\b.{0,180}\bwill\s+be\s+provided\s+by\s+(?:our|the)\s+annual\s+report\b",
            r"\bbased\s+solely\s+on\s+information\s+available\s+to\s+us\s+as\s+of\s+the\s+date\b",
            r"\bbased\s+on\s+currently\s+available\s+information\b",
            r"\bbased\s+on\s+preliminary\s+internal\s+data\s+available\s+as\s+of\s+the\s+date\s+of\s+this\s+announcement\b",
            r"\bindependent\s+registered\s+accounting\s+firm\b.{0,120}\bnot\s+reviewed\s+or\s+audited\b",
            r"\bshould\s+not\s+be\s+viewed\s+as\s+a\s+substitute\s+for\s+the\s+full\s+financial\s+statements\b",
            r"\badvised\s+not\s+to\s+base\s+their\s+investment\s+decisions\s+solely\s+on\s+such\s+preliminary\s+unaudited\s+financial\s+results\b",
        ],
    )


def _has_conference_presentation_notice_signal(content: str) -> bool:
    """判断文本是否为会议/路演展示通知。

    这类材料通常描述管理层将在 conference / investor meeting 上发言，
    并强调 presentation slides、transcript 或 webcast 会单独提供。

    Args:
        content: 规范化后的文本。

    Returns:
        命中会议/展示通知时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:4200]
    has_event_notice = _match_any(
        normalized_prefix,
        [
            r"\bwill\s+present\s+at\b.{0,160}\bconference\b",
            r"\bhost\s+an?\s+investor\s+meeting\b",
            r"\bto\s+host\s+investor\s+meeting\b",
            r"\bahead\s+of\s+(?:its|the)\s+scheduled\s+investor\s+day\b",
            r"\bbmo\s+global\b.{0,120}\bconference\b",
            r"\bbank\s+of\s+america\b.{0,160}\bconference\b",
        ],
    )
    if not has_event_notice:
        return False
    if _has_strong_current_results_disclosure_signal(normalized_prefix):
        return False
    return _match_any(
        normalized_prefix,
        [
            r"\bpresentation\s+slides?\s+(?:is|are)\s+attached\b",
            r"\bpresentation\s+slides?\b.{0,160}\bavailable\s+on\b",
            r"\btranscript\s+of\b.{0,120}\bpresentation\b.{0,120}\bavailable\b",
            r"\baffirming\s+its\s+previously\s+issued\s+business\s+outlook\b",
            r"\bupdate\s+on\b.{0,160}\bstrategic\s+initiatives\b.{0,160}\bfinancial\s+performance\b",
            r"\bupdate\s+on\b.{0,120}\bfinancial\s+performance\b.{0,120}\bmarket\s+outlook\b",
        ],
    )


def _has_agm_announcement_signal(content: str) -> bool:
    """判断文本是否为股东大会/投票结果/财务日历公告。"""

    if _has_strong_current_results_disclosure_signal(content):
        return False
    if _match_any(content, list(_6K_IFRS_RECON_PATTERNS)):
        return False
    normalized_prefix = " ".join(content.split())[:1200]
    agm_patterns = [
        r"\bannual\s+general\s+meeting\b",
        r"\bannual\s+general\s+meeting\s+of\s+shareholders\b",
        r"\bnotice\s+of\s+meeting\b",
        r"\bnotice\s+of\s+agm\b",
        r"\bnotice\s+and\s+information\s+circular\b",
        r"\brecord\s+date\s+for\b",
        r"\bceo'?s\s+address\s+to\b.{0,80}\bannual\s+general\s+meeting\b",
        r"\bannual\s+report\s+and\s+form\s+20-f\b",
        r"\bannual\s+financial\s+report\s+and\s+notice\s+of\b",
        r"\bagm\s+statements\b",
        r"\bvoting\s+results\b",
        r"\bsubmission\s+of\s+matters\s+to\s+a\s+vote\s+of\s+security\s+holders\b",
        r"\bfinancial\s+calendar\b",
        r"\bcorporate\s+calendar\b",
    ]
    return _match_any(normalized_prefix, agm_patterns)


def _has_annual_financial_statements_signal(content: str) -> bool:
    """判断文本是否为年度审计财务报表附件。"""

    normalized_prefix = " ".join(content.split())[:1800]
    has_annual_statements = _match_any(
        normalized_prefix,
        [
            r"\bconsolidated\s+financial\s+statements\b.{0,120}\bfor\s+the\s+years\s+ended\b",
            r"\bfor\s+the\s+years\s+ended\s+december\s+31\b",
        ],
    )
    if not has_annual_statements:
        return False
    return _match_any(
        normalized_prefix,
        [
            r"\breport\s+of\s+independent\s+registered\s+public\s+accounting\s+firm\b",
            r"\bmanagement'?s\s+responsibility\s+for\s+financial\s+reporting\b",
        ],
    )


def _has_reporting_change_datapack_signal(content: str) -> bool:
    """判断文本是否为“财报口径变更 / data pack”类说明材料。

    这类材料通常不会披露当期完整财务报表，只是为了即将到来的 earnings
    release 提前说明 reporting segment / comparatives 的重列方式。

    Args:
        content: 规范化后的文本。

    Returns:
        命中 reporting changes / data pack 说明时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:4200]
    has_reporting_changes = _match_any(
        normalized_prefix,
        [
            r"\bgroup\s+reporting\s+changes\b",
            r"\bsegmental\s+reporting\b",
            r"\breporting\s+segments\b",
            r"\borganisational\s+changes\b",
        ],
    )
    if not has_reporting_changes:
        return False

    return _match_any(
        normalized_prefix,
        [
            r"\bdata\s+pack\b",
            r"\bimpact\s+on\s+the\s+previously\s+reported\s+financial\s+information\b",
            r"\bin\s+advance\s+of\s+the\s+publication\s+of\b.{0,120}\bearnings?\s+release\b",
        ],
    )


def _has_earnings_call_artifact_signal(content: str) -> bool:
    """判断文本是否为 earnings call 附属材料。

    这类 6-K 本身不是结果新闻稿，而是结果发布后的电话会录音、文字稿、
    或电话会中引用的 investor presentation。即便正文里会重复出现
    ``results`` / ``earnings call`` 等词，也不应继续留在 active 结果披露集合。

    Args:
        content: 规范化后的文本。

    Returns:
        命中电话会附属材料时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:2200]
    artifact_patterns = [
        r"\baudio\s+recording\s+of\s+the\s+earnings\s+call\b",
        r"\baudio\s+recordings?\b.{0,160}\bearnings\s+call\b",
        r"\baudio\s+recording\s+of\s+the\s+call\s+with\s+media\b.{0,200}\bfinancial\s+results\b",
        r"\btranscript\s*[–\-:]?\s*(?:first|second|third|fourth|q[1-4]).{0,80}\bresults?\s+conference\s+call\b",
        r"\btranscript\s+of\s+the\s+earnings\s+call\b",
        r"\bearnings\s+call\s+transcript\b",
        r"\binvestor\s+presentation\s+referred\s+during\s+the\s+earnings\s+call\b",
        r"\binvestor\s+presentation\b.{0,120}\bwill\s+be\s+referred\s+during\s+the\s+earnings\s+call\b",
        r"\binvestor\s+presentation\s+used\s+for\s+the\s+earnings\s+call\b",
        r"\bwe\s+are\s+enclosing\s+herewith\s+the\s+presentation\s+on\s+the\s+(?:audited|unaudited)\s+financial\s+results\b",
        r"\bnewspaper\s+advertisement\s+regarding\b.{0,120}\bfinancial\s+results\b",
        r"\bpresentation\s+materials?\s+related\s+to\s+the\b.{0,160}\bfinancial\s+results\b",
        r"\bmaterials\s+and\s+a\s+webcast\s+replay\s+are\s+available\b",
        r"\banalyst\s+q\s*&?\s*a\s+session\s+transcript\b",
        r"\banalyst\s+conference\s+call\s+presentation\b",
        r"\bwe\s+will\s+present\s+our\b.{0,120}\bresults?\b.{0,120}\binteractive\s+meeting\b",
        r"\bfinancial\s+statements?\b.{0,180}\balready\s+available\s+on\s+the\s+investor\s+relations\s+website\b",
        r"\battached\s+are\s+the\s+presentation\s+slides\b.{0,160}\bresults\s+presentation\b",
        r"\bpresentation\s+slides\s+and\s+a\s+video\s+of\s+this\s+presentation\s+are\s+available\b",
        r"\benclosure:\s*.{0,120}\binvestor\s+presentation(?:\b|[A-Z])",
        r"\benclosure:\s*.{0,160}\bearnings\s+release\s+investor\s+presentation(?:\b|[A-Z])",
        r"\bq[1-4](?:\s+[a-z]{3}\s+20\d{2}|\s+20\d{2})?.{0,40}\b(?:earnings\s+release\s+|er\s+)?investor\s+presentation(?:\b|[A-Z])",
    ]
    return _match_any(normalized_prefix, artifact_patterns)


def _has_dividend_distribution_notice_signal(content: str) -> bool:
    """判断文本是否为股息/分配日程公告。

    这类材料通常是交易所制式分红通知或全年关键日期表，
    即使会提到 `full year results announcement` / `half year results announcement`，
    主体也仍然是 dividend / ex-dividend / record date 日程，而非财报正文。

    Args:
        content: 规范化后的文本。

    Returns:
        命中股息/分配日程公告时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:2400]
    appendix_distribution_patterns = [
        r"\bappendix\s+3a\.1\s*-\s*notification\s+of\s+dividend\s*/\s*distribution\b",
        r"\bnotification\s+of\s+dividend\s*/\s*distribution\b",
    ]
    if _match_any(normalized_prefix, appendix_distribution_patterns):
        return True
    return _match_any(
        normalized_prefix,
        [
            r"\bkey\s+dates\b.{0,220}\bresults?\s+announcement\b.{0,220}\bex-?dividend\s+date\b",
            r"\bdate\s+event\b.{0,220}\bfinal\s+dividend\b.{0,220}\bresults?\s+announcement\b",
        ],
    )


def _has_capital_return_announcement_signal(content: str) -> bool:
    """判断文本是否为资本回报/股东回报公告。

    这类 6-K 常见于回购、库存股交易、股息调整、股东回报政策等材料。
    它们可能顺带提到 `results announcement`、`2025 results` 或历史季度数字，
    但主语义并不是当期财务报表披露，因此不应继续留在 active 结果披露集合。

    Args:
        content: 规范化后的文本。

    Returns:
        命中资本回报公告时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:2600]
    capital_return_patterns = [
        r"\btransaction\s+in\s+own\s+shares\b",
        r"\bannouncement\s+of\s+share\s+repurchase\s+programme\b",
        r"\bshell\s+announces?\s+commencement\s+of\s+a\s+share\s+buyback\s+programme\b",
        r"adjustment\s+to\s+cash\s+dividend\s+per\s+share",
        r"\bstockholder\s+remuneration\s+policy\s*\(dividends?\s+and\s+interest\s+on\s+capital\)",
        r"\binterim\s+cash\s+dividend\s+against\s+20\d{2}\s+results\b",
        r"\b(?:subject|agenda)\s*:\s*to\s+consider\s+and\s+approve\s+proposal\s+for\s+buyback\s+of\s+equity\s+shares\b",
        r"\bto\s+consider\s+and\s+approve\s+proposal\s+for\s+buyback\s+of\s+equity\s+shares\b",
        r"\bpublic\s+announcement\s+post-buyback\b",
        r"\brenews?\s+its\b.{0,80}\bshare\s+buyback\s+program\b",
    ]
    if not _match_any(normalized_prefix, capital_return_patterns):
        return False
    return not _has_strong_current_results_disclosure_signal(normalized_prefix)


def _has_strong_current_results_disclosure_signal(content: str) -> bool:
    """判断文本是否包含强结果披露信号。

    这个 helper 用来区分“未来通知 / 资本动作公告里提到 results”与
    “当前文档本身就是 results release”。它只覆盖稳定的结果披露结构信号，
    避免把真实财报正文误判为非季度材料。

    Args:
        content: 规范化后的文本。

    Returns:
        命中强结果披露信号时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:4200]
    return _match_any(
        normalized_prefix,
        [
            r"\breported\s+its\s+financial\s+results?\s+for\b",
            r"\breported\s+its\s+unaudited,?\s+consolidated\s+financial\s+and\s+operating\s+results\s+for\b",
            r"\breports?\s+(?:its\s+)?financial\s+results?\s+for\b",
            r"\bfinancial\s+highlights\b",
            r"\b\dq\d{2}\s+summary\b",
            r"\bstatements?\s+of\s+(income|operations|cash\s+flows?|financial\s+position)\b",
            r"\b(?:condensed\s+)?consolidated\s+balance\s+sheets?\b",
            r"\bunaudited\s+(?:condensed\s+)?consolidated\s+financial\s+statements?\b",
        ],
    )


def _has_board_minutes_financial_approval_signal(content: str) -> bool:
    """判断文本是否为董事会会议纪要类公告。

    此类材料通常记录董事会审议/批准财报的过程，但不是财报正文本身。

    Args:
        content: 规范化后的文本。

    Returns:
        命中会议纪要类公告时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:4200]
    has_minutes_heading = _match_any(
        normalized_prefix,
        [
            r"\bminutes\s+of\s+the\s+board\s+of\s+directors?[’']?s?\s+meeting\b",
            r"\bminutes\s+of\b.{0,160}\bboard\s+of\s+directors\b",
            r"\bminutes\s+of\b.{0,120}\baudit\s+and\s+control\s+committ?ee\b",
            r"\bminutes\s+of\b.{0,120}\baudit\s+committ?ee\b",
            r"\bminutes\s+of\b.{0,160}\bfiscal\s+council\b",
            r"\bopinion\s+of\s+the\s+fiscal\s+council\b",
            r"\bminutes\s+no\.?\s*\d+\b",
        ],
    )
    if not has_minutes_heading:
        return False
    return _match_any(
        normalized_prefix,
        [
            r"\bconsideration\s+of\s+the\s+interim\s+financial\s+statements\b",
            r"\bapprove\s+the\s+financial\s+statements\b",
            r"\bcompany[’']?s\s+quarterly\s+financial\s+report\b",
            r"\binterim\s+financial\s+statements?\b",
            r"\bappraisal\s+of\s+the\s+company[’']?s\s+financial\s+statements\b",
            r"\bindependent\s+auditors?[’']?\s+report\b",
            r"\bannual\s+management\s+report\b",
            r"\bmanagement\s+report\b",
            r"\bindividual\s+and\s+consolidated\s+financial\s+statements\b",
            r"\brecommend\s+to\s+the\s+company[’']?s\s+board\s+of\s+directors\b.{0,120}\bapproval\b",
            r"\bto\s+acknowledge\s+on\s+the\s+company[’']?s\s+quarterly\s+financial\s+report\b",
        ],
    )


def _has_update_note_signal(content: str) -> bool:
    """判断文本是否为 results update note / outlook note。

    这类材料提供对即将发布结果的预期区间与 outlook，而非最终财报正文。

    Args:
        content: 规范化后的文本。

    Returns:
        命中 update note 类材料时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:2600]
    if not re.search(r"\bupdate\s+note(?:\b|(?=[A-Z]))", normalized_prefix, re.IGNORECASE):
        return False
    return _match_any(
        normalized_prefix,
        [
            r"\boutlooks?\s+presented\s+may\s+vary\s+from\s+the\s+actual\b",
            r"\bsubject\s+to\s+finali[sz]ation\s+of\s+those\s+results\b",
            r"\bscheduled\s+to\s+be\s+published\s+on\b",
        ],
    )


def _has_local_exchange_financial_statement_summary_signal(content: str) -> bool:
    """判断文本是否为本地交易所的财报批准摘要函。

    这类 6-K 常见于巴西/阿根廷本地交易所同步披露：正文是致交易所/监管机构的
    说明函，只摘要列出“董事会已批准的 interim financial statements / equity /
    comprehensive income”等结果，不直接附完整财务报表页。

    Args:
        content: 规范化后的文本。

    Returns:
        命中本地交易所摘要函时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:4200]
    has_local_exchange_heading = _match_any(
        normalized_prefix,
        [
            r"\bdear\s+sirs\b",
            r"\bbolsas?\s+y\s+mercados\s+argentinos\b",
            r"\bnational\s+securities\s+commission\b",
            r"\bbrazilian\s+securities\s+and\s+exchange\s+commission\b",
            r"\bcomisi[oó]n\s+nacional\s+de\s+valores\b",
            r"\bmercado\s+abierto\s+electr[oó]nico\b",
            r"\bcvm\b",
            r"\bb3\b",
        ],
    )
    if not has_local_exchange_heading:
        return False
    has_financial_approval_notice = _match_any(
        normalized_prefix,
        [
            r"\bthe\s+following\s+documents\s+were\s+approved\b",
            r"\bapproved\s+the\s+condensed\s+interim\s+financial\s+statements\b",
            r"\bapproved\s+the\s+interim\s+financial\s+statements\b",
            r"\bfinancial\s+statements?\s+as\s+of\b",
            r"\brelevant\s+information\s+of\s+the\s+condensed\s+consolidated\s+interim\s+financial\s+statements\b",
        ],
    )
    if not has_financial_approval_notice:
        return False
    # 若本地交易所函件已经直接给出了当期核心报表/损益摘要，则它更接近
    # “已披露季度结果的本地同步摘要”，不应被当作纯治理说明函排除。
    if _has_local_exchange_financial_result_summary_signal(normalized_prefix):
        return False
    return _match_any(
        normalized_prefix,
        [
            r"\bthe\s+results?\s+.*\s+are\s+as\s+follow",
            r"\brelevant\s+information\b.{0,160}\bfollows\b",
            r"\bother\s+comprehensive\s+income\s+for\s+the\s+period\b",
            r"\bdetail\s+of\s+shareholders?[’']?\s+equity\b",
            r"\bdetail\s+of\s+equity\b",
        ],
    )


def _has_local_exchange_financial_result_summary_signal(content: str) -> bool:
    """判断本地交易所函件是否已经给出当期财务结果摘要。

    这类文件虽然以 `Dear Sirs` / `ByMA` / `CNV` 等本地交易所函件开头，但若正文
    已经列出当期 `net profit`、`statement of financial position`、`statement of
    comprehensive income`、`cash flows` 等核心报表或结果摘要，则应保留为季度
    结果披露，而不是按纯治理/通知函件排除。

    Args:
        content: 规范化后的文本。

    Returns:
        命中当期财务结果摘要时返回 ``True``。

    Raises:
        无。
    """

    return _match_any(
        content,
        [
            r"\bnet\s+profit\s+for\s+the\s+period\b",
            r"\btotal\s+net\s+profit\s+for\s+the\s+period\b",
            r"\bother\s+comprehensive\s+income\s+for\s+the\s+period\b",
            r"\bstatement\s+of\s+financial\s+position\b",
            r"\bstatement\s+of\s+comprehensive\s+income\b",
            r"\bstatement\s+of\s+changes\s+in\s+(?:shareholders?[’']?\s+)?equity\b",
            r"\bstatement\s+of\s+cash\s+flows?\b",
            r"\bcondensed\s+interim\s+financial\s+statements?\b.{0,160}\bfollows\b",
            r"\bcondensed\s+consolidated\s+interim\s+financial\s+statements?\b.{0,160}\bfollows\b",
        ],
    )


def _has_official_letter_response_signal(content: str) -> bool:
    """判断文本是否为监管问询/媒体澄清回复函。

    这类材料本质是针对交易所或监管机构的问询函回复，哪怕正文引用了
    `quarter results` 或 conference call，也不是季度结果正文本身。

    Args:
        content: 规范化后的文本。

    Returns:
        命中回复函类材料时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:3200]
    if not _match_any(
        normalized_prefix,
        [
            r"\brequest\s+for\s+clarification\b",
            r"\bofficial\s+letter\b",
            r"\bnews\s+published\s+in\s+the\s+media\b",
            r"\bin\s+response\s+to\s+the\s+official\s+letter\b",
        ],
    ):
        return False
    return _match_any(
        normalized_prefix,
        [
            r"\bdear\s+sirs\b",
            r"\battn\.?:\b",
            r"\bconference\s+call\s+with\s+analysts\b",
            r"\bextraordinary\s+dividends?\b",
            r"\bregarding\s+the\s+news\s+article\b",
        ],
    )


def _has_operating_statistics_signal(content: str) -> bool:
    """判断文本是否为 operating statistics / operating metrics 材料。

    该类材料通常披露产量、销量、单位成本等运营指标，而非完整财务报表。

    Args:
        content: 规范化后的文本。

    Returns:
        命中 operating statistics 材料时返回 ``True``。

    Raises:
        无。
    """

    normalized_prefix = " ".join(content.split())[:2400]
    if not re.search(r"\boperating\s+statistics\b", normalized_prefix, re.IGNORECASE):
        return False
    if _match_any(
        normalized_prefix,
        [
            r"\bconsolidated\s+balance\s+sheets?\b",
            r"\bstatements?\s+of\s+financial\s+position\b",
            r"\bunaudited\s+condensed\s+consolidated\s+financial\s+statements?\b",
        ],
    ):
        return False
    return _match_any(
        normalized_prefix,
        [
            r"\ball-?in\s+sustaining\s+costs?\b",
            r"\bproduction\b",
            r"\bounces?\b",
            r"\breporting\s+method\b",
        ],
    )


def _has_investor_event_update_signal(content: str) -> bool:
    """判断文本是否为 investor conference / investor day 更新材料。"""

    normalized_prefix = " ".join(content.split())[:1800]
    has_event = _match_any(
        normalized_prefix,
        [
            r"\binvestor\s+conference\b",
            r"\binvestor\s+event\b",
            r"\binvestor\s+day\b",
        ],
    )
    if not has_event:
        return False
    return _match_any(
        normalized_prefix,
        [
            r"\bprovided\s+an\s+update\s+on\s+the\s+company'?s\s+business\b",
            r"\breaffirmed\b.{0,120}\bguidance\b",
            r"\bpresentation\s+materials\s+will\s+be\s+available\b",
            r"\blong-?range\s+financial\s+expectations\b",
        ],
    )


def _has_forum_presentation_signal(content: str) -> bool:
    """判断文本是否为论坛/路演展示材料。"""

    normalized_prefix = " ".join(content.split())[:1600]
    has_presentation = _match_any(
        normalized_prefix,
        [
            r"\bpresentation\b",
            r"\bnews\s+highlights\b",
        ],
    )
    if not has_presentation:
        return False
    return _match_any(
        normalized_prefix,
        [
            r"\bmining\s+forum\b",
            r"\bforum\s+americas\b",
            r"\bforward-?looking\s+statements\b",
        ],
    )


def _has_capital_markets_adjustment_signal(content: str) -> bool:
    """判断文本是否为资本市场条款调整公告。"""

    normalized_prefix = " ".join(content.split())[:1000]
    if not re.search(r"\badjustment\s+to\s+exercise\s+price\b", normalized_prefix, re.IGNORECASE):
        return False
    capital_markets_patterns = [
        r"\bequity\s+linked\s+securities\b",
        r"\bcall\s+spread\b",
        r"\blower\s+strike\s+call\b",
        r"\bupper\s+strike\s+warrant\b",
        r"\bconvertible\s+(senior\s+)?notes?\b",
    ]
    return _match_any(normalized_prefix, capital_markets_patterns)


def _has_strategy_presentation_signal(content: str) -> bool:
    """判断文本是否为战略/资本市场展示材料。"""

    normalized_prefix = " ".join(content.split())[:1200]
    has_strategy = re.search(r"\bour\s+strategy\b", normalized_prefix, re.IGNORECASE) is not None
    has_deck_structure = _match_any(
        normalized_prefix,
        [
            r"\bagenda\b",
            r"\bq\s*&\s*a\b",
            r"\bsummary\s+and\s+conclusions\b",
            r"\bforward\s+looking\s+statements\b",
        ],
    )
    return has_strategy and has_deck_structure


def _has_trading_statement_signal(content: str) -> bool:
    """判断文本是否为交易声明/业绩预告。"""

    normalized_prefix = " ".join(content.split())[:2600]
    if not re.search(r"\btrading\s+statement\b", normalized_prefix, re.IGNORECASE):
        return False
    trigger_patterns = [
        r"\bwill\s+publish\b.{0,160}\bfinancial\s+results?\b",
        r"\bproduction\s+update\b",
        r"\boperational\s+performance\s+update\b",
        r"\bexpects?\s+to\s+report\b.{0,120}\b(headline\s+earnings|eps|loss\s+per\s+share)\b",
        r"\bcurrent\s+estimates?\s+and\s+expectations?\b",
        r"\bnot\s+an\s+estimate\s+of\s+those\s+results\b",
        r"\breasonable\s+degree\s+of\s+certainty\s+exists\b",
        r"\bfurther\s+detail\s+will\s+be\s+provided\s+as\s+part\s+of\b.{0,240}\bresults?\s+to\s+be\s+released\b",
        r"\bresults?\s+for\b.{0,120}\bare\s+expected\s+to\s+be\s+published\s+on\b",
    ]
    return _match_any(normalized_prefix, trigger_patterns)


def _has_operating_update_without_financial_statement_signal(content: str) -> bool:
    """判断文本是否属于“经营更新而非季度财报”。"""

    normalized_prefix = " ".join(content.split())[:4200]
    if _has_strong_current_results_disclosure_signal(normalized_prefix):
        return False
    if _match_any(
        normalized_prefix,
        [
            r"\bconsolidated\s+balance\s+sheets?\b",
            r"\bstatements?\s+of\s+financial\s+position\b",
            r"\bunaudited\s+(?:condensed\s+)?consolidated\s+financial\s+statements?\b",
        ],
    ):
        return False

    has_operating_update_heading = _match_any(
        normalized_prefix,
        [
            r"\boperating\s+update\b",
            r"\bquarterly\s+activities\s+report\b",
            r"\btrading\s+update\b",
            r"\bresults?\s+for\s+production\s+and\s+volume\s+sold\b",
            r"\bpreliminary\s+vehicle\s+deliver(?:y|ies)\b",
            r"\bbitcoin\s+mining\s+updates?\b",
            r"\boperational\s+highlights\b",
        ],
    )
    if not has_operating_update_heading:
        return False
    return _match_any(
        normalized_prefix,
        [
            r"\bfinancial\s+results?\s+are\s+only\s+provided\s+on\s+a\s+six-?monthly\s+basis\b",
            r"\bproduction\s+per\s+metal\b",
            r"\bvolume\s+sold\s+per\s+metal\b",
            r"\bmineral\s+resource\s+estimate\b",
            r"\bdeliver(?:ed|ies)\b",
            r"\btraffic\b",
            r"\bguidance\b",
            r"\bresumption\s+progress\b",
            r"\boperational\s+highlights\b",
            r"\bcurrent\s+mining\s+projects\b",
            r"\bkey\s+metrics\b",
        ],
    ) or bool(
        re.search(
            r"\bsets?\s+date\s+for\s+the\s+release\s+of\b.{0,120}\bresults?\b",
            normalized_prefix,
            re.IGNORECASE,
        )
    )


def _has_non_quarterly_annual_report_signal(content: str) -> bool:
    """判断文本是否属于“年报语境且缺少季度财报主信号”。"""

    normalized_prefix = " ".join(content.split())[:_6K_ANNUAL_CONTEXT_SCAN_CHARS]
    if not _match_any(normalized_prefix, list(_6K_CONTEXTUAL_ANNUAL_EXCLUDE_PATTERNS)):
        return False
    normalized_keep_prefix = content[:_6K_KEEP_SCAN_CHARS]
    if _match_any(normalized_keep_prefix, list(_6K_STRONG_KEEP_PATTERNS)):
        return False
    if _match_any(normalized_keep_prefix, list(_6K_IFRS_RECON_PATTERNS)):
        return False
    return True


def _match_any(content: str, patterns: list[str]) -> bool:
    """判断文本是否命中任意正则。"""

    for pattern in patterns:
        if re.search(pattern, content, flags=re.IGNORECASE):
            return True
    return False
