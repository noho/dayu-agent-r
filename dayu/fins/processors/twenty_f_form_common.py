"""20-F 表单公共常量与 marker 构建逻辑。

本模块提取 20-F 相关的共享常量和 marker 函数，供
``TwentyFFormProcessor``（edgartools 路线）和
``BsTwentyFFormProcessor``（BeautifulSoup 路线）共同使用。

两侧处理器均从本模块 import，互不依赖，保持架构独立。

维护说明(不拆分本模块):
    本模块虽超 3000 行, 但 56 个私有函数全部围绕 20-F marker 构建
    这一个领域问题, 且内部调用图高度耦合: 核心 repair 函数调用 15 个
    兄弟函数, 横跨 cross-reference / contamination / context validation /
    order preservation 四个区域. 按子关注点拆分会产生约 20 个跨模块
    import 而无法降低耦合, 只会增加阅读和维护负担.
"""

from __future__ import annotations

import html
import re
from collections.abc import Collection
from typing import Optional

from .sec_form_section_common import (
    SIGNATURE_PATTERN as _SIGNATURE_PATTERN,
    _dedupe_markers,
    _find_marker_after,
    _looks_like_reference_guide_content,
)
from .sec_report_form_common import (
    _looks_like_inline_toc_snippet,
    _looks_like_toc_page_line_generic,
    _select_ordered_item_markers,
    _select_ordered_item_markers_after_toc,
)

# ── SEC Form 20-F 法定 Item 顺序 ──────────────────────────────
# 参考 SEC Form 20-F General Instructions, Part I–IV
_TWENTY_F_ITEM_ORDER: tuple[str, ...] = (
    "1",
    "2",
    "3",
    "4",
    "4A",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
    "11",
    "12",
    "13",
    "14",
    "15",
    "16A",
    "16B",
    "16C",
    "16D",
    "16E",
    "16F",
    "16G",
    "16H",
    "16I",
    "16J",
    "17",
    "18",
    "19",
)

# Item 匹配正则：匹配 "Item 3." / "Item 16A:" / "ITEM 18 -" 等格式
# 使用精确枚举防止 Item 1 匹配到 Item 10/11/12 等前缀。
# 同时支持 "Item 5 Operating..." 这类无标点分隔格式（下一字符必须是字母，
# 可避免命中封面 "Item 18 ☐" 勾选框）。
_TWENTY_F_ITEM_PATTERN = re.compile(
    r"(?im)(?:\bitem\s+(16[A-J]|4A|1[0-9]|[1-9])(?:\s*[\.\:\-\u2013\u2014]\s*|\s+(?=[A-Za-z])))"
    r"|(?:^|\n)\s*(16[A-J]|4A|1[0-9]|[1-9])\s*(?:[\.\:\-\u2013\u2014]\s*|\s+)"
    r"(?=(?:key\s+information|information\s+on\s+the\s+company|operating\s+and\s+financial\s+review|"
    r"financial\s+statements|controls\s+and\s+procedures|additional\s+information|exhibits)\b)"
)
# 分为"精确 Item 前缀"和"bare phrase"两层，避免 bare phrase 在超大文档
# 中产生数百个命中并逐一调用过滤函数（O(matches * filters)）。
# 精确层匹配极少，可快速命中或跳过；bare phrase 仅在精确层无果时触发。
_TWENTY_F_KEY_ITEM_FALLBACK_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "3": (
        re.compile(r"(?i)\bitem\s+3\s*[\.\:\-\u2013\u2014]\s*key\s+information\b"),
        re.compile(r"(?i)\bkey\s+information\b"),
        re.compile(r"(?i)\bsummary\s+of\s+risk\s+factors\b"),
        re.compile(r"(?i)\bgroup\s+principal\s+risks\b"),
        re.compile(r"(?i)\bprincipal\s+risks?\s+and\s+uncertainties\b"),
        re.compile(r"(?i)\brisk\s+factors\b"),
    ),
    "4": (
        re.compile(r"(?i)\bitem\s+4\s*[\.\:\-\u2013\u2014]\s*information\s+on\s+the\s+company\b"),
        re.compile(r"(?i)\binformation\s+on\s+the\s+company\b"),
    ),
    "5": (
        re.compile(r"(?i)\bitem\s+5\s*[\.\:\-\u2013\u2014]\s*operating\s+and\s+financial\s+review\s+and\s+prospects\b"),
        re.compile(r"(?i)\boperating\s+and\s+financial\s+review\s+and\s+prospects\b"),
        re.compile(r"(?i)\bchief\s+financial\s+officer(?:'|’)?s\s+review\b"),
        re.compile(r"(?i)\bfinancial\s+review\b"),
        re.compile(r"(?i)\bfinancial\s+performance\b"),
        re.compile(r"(?i)\bfinancial\s+performance\s+summary\b"),
        re.compile(r"(?i)\boperating\s+results\b"),
        re.compile(r"(?i)\bliquidity\s+and\s+capital\s+resources\b"),
        re.compile(r"(?i)\bkey\s+performance\s+indicators\b"),
    ),
    "18": (
        re.compile(r"(?i)\bitem\s+18\s*[\.\:\-\u2013\u2014]\s*financial\s+statements\b"),
        re.compile(r"(?i)\breport\s+of\s+independent\s+registered\s+public\s+accounting\s+firm\b"),
        re.compile(r"(?i)\bconsolidated\s+financial\s+statements\b"),
        re.compile(r"(?i)\bgroup\s+financial\s+statements\b"),
        re.compile(r"(?i)\bgroup\s+companies\s+and\s+undertakings\b"),
        re.compile(r"(?i)\bfinancial\s+statements\b"),
    ),
}
_TWENTY_F_ITEM_5_SUBHEADING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(?:item\s+5\s*[\.\:\-\u2013\u2014]\s*)?operating\s+and\s+financial\s+review\s+and\s+prospects\b"),
    re.compile(r"(?i)\bfinancial\s+review\b"),
    re.compile(r"(?i)\bfinancial\s+performance\b"),
    re.compile(r"(?i)\boperating\s+results\b"),
    re.compile(r"(?i)\bliquidity\s+and\s+capital\s+resources\b"),
    re.compile(r"(?i)\btrend\s+information\b"),
    re.compile(r"(?i)\bkey\s+performance\s+indicators\b"),
)
_TWENTY_F_KEY_ITEMS = ("3", "5", "18")
_TWENTY_F_REPAIR_ITEMS = ("3", "4", "5", "18")
_TOC_PAGE_LINE_PATTERN = re.compile(r"(?im)^\s*[A-Za-z][^\n]{0,220}\b\d{1,3}\s*$")
_TOC_PAGE_SNIPPET_PATTERN = re.compile(
    r"(?is)^\s*(?:item\s+(?:16[A-J]|4A|1[0-9]|[1-9])\s*[\.\:\-\u2013\u2014]?\s*)?"
    r"[A-Za-z][^\n]{0,220}\b\d{1,3}\b(?:\s+item\s+(?:16[A-J]|4A|1[0-9]|[1-9])\b|\s*$)"
)
_TOC_PAGE_LEADING_NUMBER_LINE_PATTERN = re.compile(
    r"(?im)^\s*\d{1,3}\s+(?:[^\w\n]{0,3}\s*)?[A-Za-z][^\n]{0,220}$"
)

# ── SEC 20-F 法定 Item→Part 映射 ──────────────────────────────
# 参考 SEC Form 20-F 法定结构：
#   Part I:   Items 1, 2, 3, 4, 4A
#   Part II:  Items 5, 6, 7, 8, 9, 10, 11, 12
#   Part III: Items 13, 14, 15, 16, 16A–16J
#   Part IV:  Items 17, 18, 19
_TWENTY_F_ITEM_PART_MAP: dict[str, str] = {
    "1": "I", "2": "I", "3": "I", "4": "I", "4A": "I",
    "5": "II", "6": "II", "7": "II", "8": "II",
    "9": "II", "10": "II", "11": "II", "12": "II",
    "13": "III", "14": "III", "15": "III", "16": "III",
    "16A": "III", "16B": "III", "16C": "III", "16D": "III",
    "16E": "III", "16F": "III", "16G": "III", "16H": "III",
    "16I": "III", "16J": "III",
    "17": "IV", "18": "IV", "19": "IV",
}

# ── SEC 20-F 法定 Item 标准描述 ────────────────────────────────
# 参考 SEC Form 20-F Table of Contents 法定条目名称。
# 仅为高频分析 Item 提供描述（治理类 16A–16J 因过于细碎省略），
# 帮助 LLM 按标题快速定位目标章节。
_TWENTY_F_ITEM_DESCRIPTIONS: dict[str, str] = {
    "1": "Identity of Directors, Senior Management and Advisers",
    "2": "Offer Statistics and Expected Timetable",
    "3": "Key Information",
    "4": "Information on the Company",
    "4A": "Unresolved Staff Comments",
    "5": "Operating and Financial Review and Prospects",
    "6": "Directors, Senior Management and Employees",
    "7": "Major Shareholders and Related Party Transactions",
    "8": "Financial Information",
    "9": "The Offer and Listing",
    "10": "Additional Information",
    "11": "Quantitative and Qualitative Disclosures About Market Risk",
    "12": "Description of Securities Other Than Equity Securities",
    "13": "Defaults, Dividend Arrearages and Delinquencies",
    "14": "Material Modifications to the Rights of Security Holders",
    "15": "Controls and Procedures",
    "17": "Financial Statements",
    "18": "Financial Statements",
    "19": "Exhibits",
}
_TWENTY_F_REPORT_START_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)annual\s+report\s+pursuant\s+to\s+section\s+13\s+or\s+15\(d\)\s+of\s+the\s+securities\s+exchange\s+act\s+of\s+1934"
    ),
    re.compile(
        r"(?i)transition\s+report\s+pursuant\s+to\s+section\s+13\s+or\s+15\(d\)\s+of\s+the\s+securities\s+exchange\s+act\s+of\s+1934"
    ),
    re.compile(
        r"(?i)securities\s+registered\s+or\s+to\s+be\s+registered\s+pursuant\s+to\s+section\s+12\(b\)\s+of\s+the\s+act"
    ),
)
_TWENTY_F_XBRL_QNAME_RE = re.compile(r"\b[a-z][a-z0-9_-]*:[A-Za-z][A-Za-z0-9_-]+\b")
_TWENTY_F_XBRL_PREAMBLE_MIN_QNAME_COUNT = 40
_TWENTY_F_MIN_PREAMBLE_TRIM_OFFSET = 50_000
_TWENTY_F_REPORT_START_BACKTRACK_CHARS = 4_000
_TWENTY_F_REPORT_START_MAX_GAP_TO_ITEM = 20_000
_TWENTY_F_COMMISSION_FILE_RE = re.compile(r"(?i)commission\s+file\s+number")
_TWENTY_F_FRONT_MATTER_CONTEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)cross\s+reference\s+guide"),
    re.compile(r"(?i)response\s+or\s+location\s+in\s+this\s+filing"),
    re.compile(r"(?i)location\s+in\s+this\s+document"),
    re.compile(r"(?i)indicate\s+by\s+check\s+mark"),
    re.compile(r"(?i)if\s+this\s+is\s+an\s+annual\s+report"),
    re.compile(r"(?i)form\s+20-f\s+caption"),
)
_TWENTY_F_FRONT_MATTER_LOOKBACK_CHARS = 320
_TWENTY_F_FRONT_MATTER_LOOKAHEAD_CHARS = 1600
_TWENTY_F_REFERENCE_GUIDE_LOOKBACK_CHARS = 1600
_TWENTY_F_REFERENCE_GUIDE_LOOKAHEAD_CHARS = 800
_TWENTY_F_MIN_RETRY_MARKERS_AFTER_FRONT_MATTER = 3
_TWENTY_F_FRONT_MATTER_MAX_SKIP_RETRIES = 3
_TWENTY_F_FRONT_MATTER_SINGLE_SKIP_MIN_GAP = 20_000
_TWENTY_F_HEADING_PREFIX_WORD_RE = re.compile(r"[A-Za-z]{2,}")
_TWENTY_F_HEADING_PREFIX_ENUM_RE = re.compile(
    r"(?i)(?:^|[\s(])(?:item\s+(?:16[A-J]|4A|1[0-9]|[1-9])|[A-D]|\d{1,2}(?:-\d{1,2})?)\s*[\.\-–—:)]?\s*$"
)
_TWENTY_F_ANNUAL_REPORT_PAGE_NUMBER_RE = re.compile(r"\b\d{1,3}\s*$")
_TWENTY_F_ANNUAL_REPORT_PAGE_RANGE_RE = re.compile(r"\b\d{1,3}\s*[–—-]\s*\d{1,3}\b")
_TWENTY_F_ANNUAL_REPORT_HEADING_PREFIX_WORD_RE = re.compile(r"[A-Za-z]{2,}")
_TWENTY_F_ANNUAL_REPORT_FOOTER_CONTEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)annual\s+report\s+and\s+form\s+20-f"),
    re.compile(r"(?i)\bstrategic\s+report\b"),
    re.compile(r"(?i)\bgovernance\s+report\b"),
    re.compile(r"(?i)\bfinancial\s+statements\b"),
    re.compile(r"(?i)\bother\s+information\b"),
)
_TWENTY_F_ANNUAL_REPORT_FOOTER_CONTEXT_LOOKBACK_CHARS = 240
_TWENTY_F_ANNUAL_REPORT_FOOTER_CONTEXT_MIN_HITS = 2
_TWENTY_F_ANNUAL_REPORT_REPEAT_LOOKAHEAD_CHARS = 80
_TWENTY_F_ANNUAL_REPORT_PAGE_HEADING_MAX_PREFIX_WORDS = 6
_TWENTY_F_ANNUAL_REPORT_PAGE_HEADING_NEIGHBOR_LINES = 3
_TWENTY_F_DIRECT_ITEM_BODY_LOOKAHEAD_LINES = 10
_TWENTY_F_ANNUAL_REPORT_PAGE_HEADING_MIN_PROSE_WORDS = 12
_TWENTY_F_INLINE_REFERENCE_PREFIX_RE = re.compile(
    r"(?i)\b(?:"
    r"see|under|described\s+under|described\s+in|discussed\s+under|discussed\s+in|"
    r"included\s+in|contained\s+in|set\s+forth\s+in|presented\s+in|provided\s+in|"
    r"within|refer(?:ring)?\s+to|addressed\s+in|found\s+in"
    r")\b[^\n]{0,120}$"
)
_TWENTY_F_ITEM_18_TOKEN_RE = re.compile(r"(?i)\bitem\s+18\b")
_TWENTY_F_FINANCIAL_STATEMENTS_RE = re.compile(r"(?i)\bfinancial\s+statements\b")
_TWENTY_F_INLINE_REFERENCE_PREFIX_HINTS: tuple[str, ...] = (
    "see",
    "under",
    "described",
    "discussed",
    "included",
    "contained",
    "set forth",
    "presented",
    "provided",
    "within",
    "refer",
    "addressed",
    "found",
)
_TWENTY_F_REFERENCE_GUIDE_LOCAL_PROBE_RE = re.compile(
    r"(?i)\b(?:"
    r"annual\s+report|form\s+20-f|cross[\s-]*reference|location\s+in\s+(?:this\s+)?(?:document|filing)|"
    r"response\s+or\s+location|caption|guide|note\s+\d+|pages?\s+[A-Z]?-?\d+|afr"
    r")\b"
)
_TWENTY_F_GUIDE_ANCHOR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)form\s+20-f\s+caption"),
    re.compile(r"(?i)form\s+20-f\s+references?"),
    re.compile(r"(?i)cross[\s-]*reference(?:\s+guide|\s+to\s+form\s+20-f)?"),
    re.compile(r"(?i)cross[\s-]*reference\s+table(?:\s+below)?"),
    re.compile(r"(?i)location\s+in\s+this\s+document"),
    re.compile(r"(?i)location\s+in\s+the\s+document"),
)
_TWENTY_F_GUIDE_ITEM_TOKENS: tuple[str, ...] = (
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "10",
    "11",
    "12",
    "13",
    "14",
    "15",
    "18",
    "19",
)
_TWENTY_F_GUIDE_WINDOW_LOOKAHEAD_CHARS = 60_000
_TWENTY_F_GUIDE_TAIL_LOOKBACK_CHARS = 25_000
_TWENTY_F_ITEM18_BODY_LOOKAHEAD_LINES = 6
_TWENTY_F_ITEM18_BODY_PROBE_LOOKBACK_CHARS = 32
_TWENTY_F_ITEM18_BODY_PROBE_LOOKAHEAD_CHARS = 220
_TWENTY_F_GUIDE_PAGE_TOKEN_RE = re.compile(
    r"(?i)\b(?:page(?:s)?\s*)?\d{1,3}(?:\s*(?:-|–|—|to)\s*\d{1,3})?\b"
)
_TWENTY_F_GUIDE_QUOTED_PHRASE_RE = re.compile(r"[\"“”']([^\"“”']{3,160})[\"“”']")
_TWENTY_F_GUIDE_SPLIT_RE = re.compile(r"\s*[|;,]\s*")
_TWENTY_F_GUIDE_SEGMENT_SPLIT_RE = re.compile(r"\s*(?:—|–|:|\s+-\s+)\s*")
_TWENTY_F_GUIDE_NOISE_PHRASES = frozenset({
    "annual report",
    "annual report and form 20-f",
    "annual report on form 20-f",
    "cross reference to form 20-f",
    "cross-reference to form 20-f",
    "cross reference guide",
    "form 20-f caption",
    "location in this document",
    "location in the document",
    "not applicable",
    "n/a",
    "page",
    "pages",
    "cover",
    "contents",
    "other information",
    "strategic report",
    "governance report",
})
_TWENTY_F_REPORT_SUITE_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bintegrated\s+annual\s+report\b"),
    re.compile(r"(?i)\bannual\s+financial\s+report\b"),
    re.compile(r"(?i)\bgovernance\s+report\b"),
    re.compile(r"(?i)\bnotice\s+of\s+annual\s+general\s+meeting\b"),
    re.compile(r"(?i)\breport\s+to\s+stakeholders\b"),
    re.compile(r"(?i)\bclimate\s+change\s+report\b"),
    re.compile(r"(?i)\bgri\s+content\s+index\b"),
    re.compile(r"(?i)\bmineral\s+resources\b.{0,40}\bsupplement\b"),
)
_TWENTY_F_REPORT_SUITE_COVER_CUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\babout\s+our\s+cover\b"),
    re.compile(r"(?i)\bsend\s+us\s+your\s+feedback\b"),
    re.compile(r"(?i)\breporting\s+suite\b"),
    re.compile(r"(?i)\bcontents\b"),
    re.compile(r"(?i)\bfurther\s+reading\s+available\s+within\s+this\s+report\b"),
)
_TWENTY_F_SEC_FILING_START_RE = re.compile(
    r"(?i)as\s+filed\s+with\s+the\s+securities\s+and\s+exchange\s+commission"
)
_TWENTY_F_REPORT_SUITE_LOOKAHEAD_CHARS = 8_000


def _build_twenty_f_guide_item_patterns() -> tuple[dict[str, re.Pattern[str]], re.Pattern[str]]:
    """为 20-F guide item 描述匹配预编译正则。

    Args:
        无。

    Returns:
        ``(token -> compiled pattern, combined pattern)`` 二元组。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    patterns: dict[str, re.Pattern[str]] = {}
    alternations: list[str] = []
    for token in _TWENTY_F_GUIDE_ITEM_TOKENS:
        description = _TWENTY_F_ITEM_DESCRIPTIONS.get(token)
        if not description:
            continue
        description_pattern = r"\s+".join(re.escape(part) for part in description.split())
        # 分隔符使用单层字符类避免 \s* + (?:\s+)+ 嵌套量词导致的灾难性回溯
        item_pattern = rf"(?:item\s+)?{re.escape(token)}[\s.\-–—:]+{description_pattern}"
        patterns[token] = re.compile(rf"(?is){item_pattern}")
        group_name = f"token_{token.lower().replace('-', '_')}"
        alternations.append(rf"(?P<{group_name}>{item_pattern})")
    combined_pattern = re.compile(rf"(?is){'|'.join(alternations)}")
    return patterns, combined_pattern


_TWENTY_F_GUIDE_ITEM_PATTERNS, _TWENTY_F_GUIDE_ITEM_COMBINED_PATTERN = (
    _build_twenty_f_guide_item_patterns()
)
_TWENTY_F_GUIDE_BODY_START_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bstrategic\s+report\b"),
    re.compile(r"(?i)\bat\s+a\s+glance\b"),
    re.compile(r"(?i)\bour\s+purpose\b"),
    re.compile(r"(?i)\bbusiness\s+model\b"),
    re.compile(r"(?i)\bchair(?:'|’)?s\s+statement\b"),
)
_TWENTY_F_ITEM_LABEL_TEMPLATE = (
    r"(?is)(?:^|[\n|])\s*(?:item\s+)?{token}(?!\s*(?:[A-Z]\b|\.|[-–—]\s*\d))\b"
)
_TWENTY_F_ANNUAL_REPORT_ITEM_CANDIDATES: dict[str, tuple[str, ...]] = {
    "3": (
        "group principal risks",
        "principal risks and uncertainties",
        "risk factors",
    ),
    "4": (
        "our purpose and strategy",
        "our business model",
        "business model",
        "at a glance",
        "strategic report",
    ),
    "5": (
        "financial review",
        "financial performance",
        "financial performance summary",
        "chief financial officer",
        "operating results",
        "liquidity and capital resources",
        "operating and financial review",
    ),
    "6": (
        "governance report",
        "board of directors",
        "management board",
        "directors and senior management",
    ),
    "7": (
        "shareholder information",
        "major shareholders",
        "related party transactions",
    ),
    "8": (
        "financial information",
        "financial statements",
    ),
    "10": (
        "additional information",
        "shareholder information",
        "document on display",
        "registered offices",
    ),
    "11": (
        "market risk",
        "quantitative and qualitative disclosures about market risk",
    ),
    "15": (
        "controls and procedures",
        "disclosure controls and procedures",
        "internal control over financial reporting",
    ),
    "18": (
        "financial statements",
        "group income statement",
        "consolidated financial statements",
        "group financial statements",
        "group companies and undertakings",
    ),
    "19": (
        "exhibits",
    ),
}
_TWENTY_F_GUIDE_MIN_MARKER_GAP_CHARS = 1_000


def _build_twenty_f_markers(full_text: str) -> list[tuple[int, Optional[str]]]:
    """构建 20-F 的 Part + Item 带描述边界。

    策略：
    1. 使用 ``_select_ordered_item_markers_after_toc`` 自适应跳过 ToC
       并按法定顺序选取 Item 标记；
    2. 以 SEC 法定映射补全每个 Item 的 Part 标签；
    3. 为高频分析 Item 附加 SEC 标准描述，提升标题可辨识度；
    4. 在最后一个 Item 之后追加 SIGNATURE 章节。

    Args:
        full_text: 文档全文。

    Returns:
        标记列表；标记不足时返回空列表触发父类回退。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    item_markers = _select_ordered_item_markers_after_toc(
        full_text,
        item_pattern=_TWENTY_F_ITEM_PATTERN,
        ordered_tokens=_TWENTY_F_ITEM_ORDER,
        min_items_after_toc=4,
    )
    item_markers = _repair_twenty_f_key_items_with_heading_fallback(full_text, item_markers)
    item_markers = _repair_twenty_f_items_with_cross_reference_guide(full_text, item_markers)
    item_markers = _skip_twenty_f_front_matter_markers(full_text, item_markers)
    if len(item_markers) < 3:
        return []

    markers: list[tuple[int, Optional[str]]] = []
    for item_token, position in item_markers:
        title = _build_item_title(item_token)
        markers.append((position, title))

    # 在最后一个 Item 之后查找 SIGNATURE
    furthest_item_position = max(position for _, position in item_markers)
    signature_marker = _find_marker_after(
        _SIGNATURE_PATTERN,
        full_text,
        furthest_item_position,
        "SIGNATURE",
    )
    if signature_marker is not None:
        markers.append(signature_marker)
    return _dedupe_markers(markers)


def _select_preferred_twenty_f_text(*, source_text: str, parsed_text: str) -> str:
    """在两个 20-F 全文候选之间选择更适合切分的文本。

    20-F 标题在不同解析链路下容易出现两类偏差：
    1. 标题换行被压平，导致 ``Item`` marker 数量不足；
    2. 原始 HTML 保留了更多行边界，但也可能混入额外噪声。

    该函数以 ``_build_twenty_f_markers`` 的可用性为同源质量信号，只在
    ``source_text`` 的 marker 质量明显更好时才优先采用。

    Args:
        source_text: 候选文本 A，通常来自保留行边界的源 HTML 提取。
        parsed_text: 候选文本 B，通常来自处理器默认全文抽取。

    Returns:
        更适合 20-F marker 构建的全文文本。

    Raises:
        RuntimeError: 选择失败时抛出。
    """

    normalized_source_text = str(source_text or "")
    normalized_parsed_text = str(parsed_text or "")
    if not normalized_source_text:
        return normalized_parsed_text
    if not normalized_parsed_text:
        return normalized_source_text

    # 两个候选文本相同时跳过重复的 marker 构建（大型 20-F 每次构建数秒）
    if normalized_source_text == normalized_parsed_text:
        return normalized_parsed_text

    source_marker_count = len(_build_twenty_f_markers(normalized_source_text))
    parsed_marker_count = len(_build_twenty_f_markers(normalized_parsed_text))
    if source_marker_count >= 3 and source_marker_count > parsed_marker_count:
        return normalized_source_text
    if parsed_marker_count >= 3:
        return normalized_parsed_text
    if source_marker_count >= 3:
        return normalized_source_text
    return normalized_parsed_text


# ---------- guide 聚簇检测 ----------

# 重建 marker 位置 span 占文档总长的最低比例阈值
_GUIDE_CLUSTER_MIN_SPAN_RATIO = 0.10

# 若所有 marker 位置都超过文档此比例位置，视为聚集在末尾
_GUIDE_CLUSTER_TAIL_START_RATIO = 0.80


def _has_guide_clustered_markers(
    markers: list[tuple[str, int]],
    text_length: int,
) -> bool:
    """检测重建的 markers 是否聚集在 guide 表区域而非分散在正文中。

    欧洲公司 20-F 的 cross-reference guide 表将所有 Item 映射到年报页码。
    当正文中找不到对应标题时，``_find_twenty_f_locator_heading_position``
    可能把 guide 表自身的文本当作命中，导致所有 marker 聚簇在文档末尾。

    检测规则：
      1. marker 位置 span（最大 - 最小）占文档总长 < 10%。
      2. 或所有 marker 都在文档 80% 之后。

    Args:
        markers: 重建的 ``(token, position)`` 列表。
        text_length: 文档全文长度。

    Returns:
        聚簇时返回 ``True``。
    """

    if not markers or text_length <= 0:
        return False

    positions = [pos for _, pos in markers]
    min_pos = min(positions)
    max_pos = max(positions)
    span = max_pos - min_pos

    # 规则 1：span 太小，说明 marker 密集在一小段区域
    if span < text_length * _GUIDE_CLUSTER_MIN_SPAN_RATIO:
        return True

    # 规则 2：所有 marker 都在文档末尾区域
    if min_pos > text_length * _GUIDE_CLUSTER_TAIL_START_RATIO:
        return True

    return False


def _has_monotonic_twenty_f_key_positions(fallback_map: dict[str, int]) -> bool:
    """判断 key-item fallback 是否完整覆盖并满足 ``Item 3 < 5 < 18``。

    Args:
        fallback_map: token → position 映射。

    Returns:
        三个关键 Item 都存在且位置递增时返回 ``True``。
    """

    item_3 = fallback_map.get("3")
    item_5 = fallback_map.get("5")
    item_18 = fallback_map.get("18")
    if item_3 is None or item_5 is None or item_18 is None:
        return False
    return int(item_3) < int(item_5) < int(item_18)


def _seed_monotonic_twenty_f_key_fallback(
    *,
    full_text: str,
    marker_map: dict[str, int],
    fallback_map: dict[str, int],
) -> dict[str, int]:
    """在 key-item fallback 已形成正文主链时优先回填关键 marker。

    某些 20-F 会同时出现两类命中：
    1. 早期正文里的真实 heading fallback；
    2. 晚期正文交叉引用或 guide/locator 派生出的伪 marker。

    当 ``fallback_map`` 已经给出单调递增的 ``Item 3 < 5 < 18`` 正文主链时，
    说明关键骨架已同源收敛完成。此时若继续保留更晚的当前 marker，后续顺序
    约束会把正确的早期 fallback 当成逆序候选删除，导致 ``Item 5`` / ``Item 18``
    仍然缺失。

    但若当前 key-item marker 已经是干净且顺序安全的正文锚点，就不能因为
    fallback 更早且“单调”而盲目回填，否则会把真实正文位置重新改写回
    ToC / annual-report guide 一类伪命中。

    Args:
        full_text: 文档全文。
        marker_map: 当前 token -> position 映射。
        fallback_map: 本轮 fallback token -> position 映射。

    Returns:
        以单调 key-item fallback 作为优先锚点回填后的 marker 映射。

    Raises:
        RuntimeError: 回填失败时抛出。
    """

    if not _has_monotonic_twenty_f_key_positions(fallback_map):
        return marker_map

    seeded_marker_map = dict(marker_map)
    for token in _TWENTY_F_REPAIR_ITEMS:
        fallback_pos = fallback_map.get(token)
        if fallback_pos is None:
            continue
        current_pos = seeded_marker_map.get(token)
        if current_pos is None:
            seeded_marker_map[token] = int(fallback_pos)
            continue

        current_pos_is_contaminated = _is_twenty_f_marker_contaminated(full_text, int(current_pos))
        if _should_preserve_current_twenty_f_key_marker(
            full_text=full_text,
            marker_map=seeded_marker_map,
            token=token,
            position=int(current_pos),
        ) and int(fallback_pos) < int(current_pos):
            # 当前 key-item 若已是可信正文锚点，
            # 不应被更早的 ToC / guide fallback 反向覆盖。
            continue

        if current_pos_is_contaminated or int(current_pos) > int(fallback_pos):
            seeded_marker_map[token] = int(fallback_pos)
    return seeded_marker_map


def _repair_twenty_f_items_with_cross_reference_guide(
    full_text: str,
    item_markers: list[tuple[str, int]],
) -> list[tuple[str, int]]:
    """用 20-F cross-reference guide 反推正文 Item 锚点。

    部分 20-F 不直接在正文中书写 ``Item 3/4/5/18`` 标题，而是在
    ``Form 20-F caption / Location in this document`` 表里把法定 Item
    映射到年报章节标题。此时纯 ``Item`` 正则会得到 0 个 marker，或只拿到
    guide 本身的伪命中。

    该函数读取 guide 中的 locator phrase，再回到正文中查找对应标题，
    从而重建 ``Item 4 / 5 / 6 / ... / 18`` 等边界。若 ``Item 3`` 只映射
    到晚期 ``Risk factors``，则会合成一个更早的起点，保证最终顺序不逆序。

    Args:
        full_text: 文档全文。
        item_markers: 现有 ``(item_token, position)`` 列表。

    Returns:
        优先返回重建后的 marker；若 guide 无法提供更好结果则回退原列表。

    Raises:
        RuntimeError: 修复失败时抛出。
    """

    needs_repair = len(item_markers) < 4 or any(
        token not in {item_token for item_token, _ in item_markers}
        for token in _TWENTY_F_KEY_ITEMS
    )
    if not needs_repair:
        needs_repair = any(
            _looks_like_toc_page_line(full_text, position)
            or _looks_like_inline_toc_snippet(full_text, position)
            or _looks_like_twenty_f_front_matter_marker(full_text, position)
            or _looks_like_twenty_f_reference_guide_marker(full_text, position)
            for _, position in item_markers
        )
    if not needs_repair:
        return item_markers

    locator_map = _extract_twenty_f_cross_reference_locator_map(full_text)
    if not locator_map:
        return item_markers

    reconstructed = _find_twenty_f_cross_reference_body_markers(
        full_text=full_text,
        locator_map=locator_map,
    )
    if len(reconstructed) < 4:
        return item_markers

    # Guide 聚簇检测：重建的 markers 应分散在正文中；
    # 如果全部聚集在文档很小的范围内，说明匹配到了 guide 表本身而非正文标题。
    if _has_guide_clustered_markers(reconstructed, len(full_text)):
        return item_markers

    # 允许 guide 先补出部分关键 Item，再与已有主链合并。
    # 真实 20-F 中常见 ``Item 3`` 只能由 guide 重建、而 ``Item 5`` / ``Item 18``
    # 已由 key-heading fallback 找回；若在这里要求 reconstructed 自身必须
    # 覆盖全部关键项，就会把后续 merge 分支提前短路。
    if not _twenty_f_reconstructed_markers_cover_key_items(
        reconstructed,
        required_tokens=_TWENTY_F_KEY_ITEMS,
    ):
        merged_reconstructed = _merge_twenty_f_reconstructed_markers_with_existing(
            full_text=full_text,
            item_markers=item_markers,
            reconstructed=reconstructed,
        )
        if _twenty_f_reconstructed_markers_cover_key_items(
            merged_reconstructed,
            required_tokens=_TWENTY_F_KEY_ITEMS,
        ):
            return merged_reconstructed
        return item_markers

    return reconstructed


def _twenty_f_reconstructed_markers_cover_key_items(
    markers: list[tuple[str, int]],
    *,
    required_tokens: Collection[str],
) -> bool:
    """判断一组 20-F marker 是否已覆盖全部关键 Item。

    Args:
        markers: ``(item_token, position)`` 列表。
        required_tokens: 必须覆盖的关键 Item token 集合。

    Returns:
        若 marker 已覆盖全部关键 Item 则返回 ``True``，否则返回 ``False``。

    Raises:
        无。
    """

    marker_tokens = {token for token, _ in markers}
    return set(required_tokens).issubset(marker_tokens)


def _merge_twenty_f_reconstructed_markers_with_existing(
    *,
    full_text: str,
    item_markers: list[tuple[str, int]],
    reconstructed: list[tuple[str, int]],
) -> list[tuple[str, int]]:
    """把 guide 重建结果与当前 20-F marker 主链合并。

    当 cross-reference guide 只能补出 ``Item 3`` / ``Item 4``，但当前
    marker 主链已经通过 key-heading fallback 找回 ``Item 5`` / ``Item 18``
    时，若仍坚持要求 guide 自身覆盖全部关键 Item，就会把更早的
    ``Item 3`` 正文锚点整组丢弃。

    这里的策略是：
    1. 以当前 ``item_markers`` 作为主链基底；
    2. 仅当 guide 重建位置更早或能替换污染 marker 时，才覆盖同 token 位置；
    3. 合并后再复用现有单调性修复逻辑，避免位置逆序回归。

    Args:
        full_text: 文档全文。
        item_markers: 当前 20-F marker 主链。
        reconstructed: guide 重建出的 marker 列表。

    Returns:
        合并后的 marker 列表。

    Raises:
        RuntimeError: 单调性修复失败时抛出。
    """

    merged_marker_map = {
        token: int(position)
        for token, position in item_markers
    }
    original_positions = dict(merged_marker_map)

    for token, position in reconstructed:
        candidate_position = int(position)
        current_position = merged_marker_map.get(token)
        if current_position is None:
            merged_marker_map[token] = candidate_position
            continue

        current_is_contaminated = _is_twenty_f_marker_contaminated(
            full_text,
            int(current_position),
        )
        candidate_is_contaminated = _is_twenty_f_marker_contaminated(
            full_text,
            candidate_position,
        )
        if current_is_contaminated and not candidate_is_contaminated:
            merged_marker_map[token] = candidate_position
            continue
        if current_is_contaminated == candidate_is_contaminated and candidate_position < int(
            current_position
        ):
            merged_marker_map[token] = candidate_position

    merged_markers = [
        (token, merged_marker_map[token])
        for token in _TWENTY_F_ITEM_ORDER
        if token in merged_marker_map
    ]
    monotonic_markers = _enforce_marker_position_monotonicity(
        full_text=full_text,
        repaired=merged_markers,
        original_positions=original_positions,
    )
    if _twenty_f_reconstructed_markers_cover_key_items(
        monotonic_markers,
        required_tokens=_TWENTY_F_KEY_ITEMS,
    ):
        return monotonic_markers
    return _enforce_twenty_f_key_item_priority_monotonicity(
        repaired=merged_markers,
        protected_tokens=_TWENTY_F_KEY_ITEMS,
    )


def _enforce_twenty_f_key_item_priority_monotonicity(
    *,
    repaired: list[tuple[str, int]],
    protected_tokens: Collection[str],
) -> list[tuple[str, int]]:
    """在 20-F monotonicity 冲突中优先保留关键 Item。

    ``_enforce_marker_position_monotonicity()`` 的默认策略会尽量保留更多
    marker，但在 guide merge 场景下，较晚插入的非关键 Item（如 9/10/11/15）
    可能反过来把较早且真实的 ``Item 18`` 挤掉，导致 hard gate 继续失败。

    该补救逻辑只在默认 monotonicity 之后关键 Item 仍不全时启用：
    1. 以法定顺序遍历 ``repaired``；
    2. 非关键 Item 冲突时直接跳过；
    3. 关键 Item 冲突时，回溯弹出末尾的非关键 Item，直到关键 Item 能放入；
    4. 已保留的关键 Item 之间不互相覆盖。

    Args:
        repaired: 按法定 token 顺序排列的 ``(item_token, position)`` 列表。
        protected_tokens: 必须优先保留的关键 Item token 集合。

    Returns:
        在冲突下优先保留关键 Item 的单调 marker 列表。

    Raises:
        无。
    """

    if len(repaired) < 2:
        return repaired

    protected_token_set = set(protected_tokens)
    prioritized: list[tuple[str, int]] = []
    for token, position in repaired:
        if not prioritized or position > prioritized[-1][1]:
            prioritized.append((token, position))
            continue
        if token not in protected_token_set:
            continue
        while (
            prioritized
            and prioritized[-1][1] >= position
            and prioritized[-1][0] not in protected_token_set
        ):
            prioritized.pop()
        if not prioritized or position > prioritized[-1][1]:
            prioritized.append((token, position))
    return prioritized


def _trim_twenty_f_source_text(source_text: str) -> str:
    """裁剪 20-F 源文本前部的 XBRL 机器前导噪声。

    部分 20-F HTML 在可见封面之前会混入大段 iXBRL / taxonomy token。
    这些内容会人为放大 ``Cover Page``，并扰乱 Item marker 和后续子切分。
    该函数仅在前导区域明确呈现 XBRL qname 噪声时执行裁剪。

    Args:
        source_text: 从源 HTML 提取的全文文本。

    Returns:
        裁剪后的文本；若未命中前导噪声则原样返回。

    Raises:
        RuntimeError: 裁剪失败时抛出。
    """

    normalized_text = str(source_text or "")
    if not normalized_text:
        return normalized_text

    candidate_starts: list[int] = []
    for pattern in _TWENTY_F_REPORT_START_PATTERNS:
        match = pattern.search(normalized_text)
        if match is not None:
            candidate_starts.append(int(match.start()))
    if not candidate_starts:
        return normalized_text

    item_match = re.search(r"(?i)\bitem\s+(?:1|2|3)\b", normalized_text)
    item_start = int(item_match.start()) if item_match is not None else len(normalized_text)
    near_item_candidates = [
        position
        for position in candidate_starts
        if position < item_start
        and item_start - position <= _TWENTY_F_REPORT_START_MAX_GAP_TO_ITEM
    ]
    report_start = min(near_item_candidates) if near_item_candidates else min(candidate_starts)
    if report_start < _TWENTY_F_MIN_PREAMBLE_TRIM_OFFSET:
        return normalized_text

    prefix = normalized_text[:report_start]
    qname_count = len(_TWENTY_F_XBRL_QNAME_RE.findall(prefix))
    if qname_count < _TWENTY_F_XBRL_PREAMBLE_MIN_QNAME_COUNT:
        return normalized_text

    trim_start = max(0, report_start - _TWENTY_F_REPORT_START_BACKTRACK_CHARS)
    commission_candidates = [
        int(match.start())
        for match in _TWENTY_F_COMMISSION_FILE_RE.finditer(normalized_text)
        if max(0, report_start - _TWENTY_F_REPORT_START_BACKTRACK_CHARS)
        <= int(match.start())
        < item_start
    ]
    if commission_candidates:
        trim_start = commission_candidates[0]
    return normalized_text[trim_start:].lstrip()


def _extract_twenty_f_cross_reference_locator_map(full_text: str) -> dict[str, str]:
    """提取 20-F cross-reference guide 中各 Item 的 locator 文本块。

    Args:
        full_text: 文档全文。

    Returns:
        ``token -> locator block`` 映射；未识别 guide 时返回空字典。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    guide_snippets = _extract_twenty_f_cross_reference_guide_snippets(full_text)
    if not guide_snippets:
        return {}

    locator_map: dict[str, str] = {}
    for snippet in guide_snippets:
        item_spans = _find_twenty_f_guide_item_spans(snippet)
        if len(item_spans) < 2:
            continue
        for index, (token, start, end) in enumerate(item_spans):
            if token in locator_map:
                continue
            block_end = item_spans[index + 1][1] if index + 1 < len(item_spans) else len(snippet)
            locator_map[token] = snippet[start:block_end]
    return locator_map


def _extract_twenty_f_cross_reference_guide_snippets(full_text: str) -> list[str]:
    """抽取可能包含 20-F locator table 的文本窗口。

    Args:
        full_text: 文档全文。

    Returns:
        guide 文本片段列表。

    Raises:
        RuntimeError: 抽取失败时抛出。
    """

    snippets: list[str] = []
    seen_ranges: set[tuple[int, int]] = set()
    for pattern in _TWENTY_F_GUIDE_ANCHOR_PATTERNS:
        for match in pattern.finditer(full_text):
            anchor_start = int(match.start())
            ranges = [
                (
                    anchor_start,
                    min(len(full_text), int(match.end()) + _TWENTY_F_GUIDE_WINDOW_LOOKAHEAD_CHARS),
                )
            ]
            # 文末 continued guide 常把早期 Item 放在前几页，此时补一个有限回看窗口，
            # 既能吃到前一页 locator，又避免把大量正文/附表误当 guide。
            if anchor_start >= int(len(full_text) * 0.7):
                ranges.append(
                    (
                        max(0, anchor_start - _TWENTY_F_GUIDE_TAIL_LOOKBACK_CHARS),
                        min(len(full_text), int(match.end()) + _TWENTY_F_GUIDE_WINDOW_LOOKAHEAD_CHARS),
                    )
                )
            for start, end in ranges:
                key = (start, end)
                if key in seen_ranges:
                    continue
                snippet = full_text[start:end]
                if (
                    re.search(r"(?i)form\s+20-f\s+caption", snippet) is None
                    and re.search(r"(?i)form\s+20-f\s+references?", snippet) is None
                    and re.search(r"(?i)location\s+in\s+this\s+document", snippet) is None
                    and re.search(r"(?i)cross[\s-]*reference(?:\s+guide|\s+to\s+form\s+20-f)?", snippet) is None
                    and re.search(r"(?i)cross[\s-]*reference\s+table(?:\s+below)?", snippet) is None
                ):
                    continue
                seen_ranges.add(key)
                snippets.append(snippet)
    return snippets


def _find_twenty_f_guide_item_spans(snippet: str) -> list[tuple[str, int, int]]:
    """在 guide 片段中定位顶层 Item block。

    Args:
        snippet: guide 片段文本。

    Returns:
        ``(token, start, end)`` 列表，按在片段中的出现顺序排列。

    Raises:
        RuntimeError: 定位失败时抛出。
    """

    spans: list[tuple[str, int, int]] = []
    token_by_group = {
        f"token_{token.lower().replace('-', '_')}": token
        for token in _TWENTY_F_GUIDE_ITEM_PATTERNS
    }
    for match in _TWENTY_F_GUIDE_ITEM_COMBINED_PATTERN.finditer(snippet):
        group_name = match.lastgroup
        if not group_name:
            continue
        token = token_by_group.get(group_name)
        if token is None:
            continue
        spans.append((token, int(match.start()), int(match.end())))
    spans.sort(key=lambda item: item[1])
    return spans


def _find_twenty_f_cross_reference_body_markers(
    *,
    full_text: str,
    locator_map: dict[str, str],
) -> list[tuple[str, int]]:
    """根据 guide locator phrase 反查正文标题位置。

    Args:
        full_text: 文档全文。
        locator_map: ``token -> locator block`` 映射。

    Returns:
        位置递增的 ``(token, position)`` 列表。

    Raises:
        RuntimeError: 查找失败时抛出。
    """

    candidate_lists: dict[str, list[str]] = {}
    for token, locator_text in locator_map.items():
        candidates = _extract_twenty_f_locator_heading_candidates(locator_text)
        fallback_candidates = list(_TWENTY_F_ANNUAL_REPORT_ITEM_CANDIDATES.get(token, ()))
        candidate_lists[token] = _dedupe_twenty_f_locator_candidates(
            candidates + fallback_candidates
        )

    candidate_map: dict[str, int] = {}
    item_4_position = _find_twenty_f_locator_heading_position(
        full_text=full_text,
        candidates=candidate_lists.get("4", []),
        start_at=0,
    )
    item_3_position = _find_twenty_f_locator_heading_position(
        full_text=full_text,
        candidates=candidate_lists.get("3", []),
        start_at=0,
    )
    if item_4_position is not None and (
        item_3_position is None or item_3_position >= item_4_position
    ):
        synthetic_item_3 = _find_twenty_f_cross_reference_item_3_start(
            full_text=full_text,
            fallback_end=item_4_position,
        )
        if synthetic_item_3 is not None and synthetic_item_3 < item_4_position:
            item_3_position = synthetic_item_3

    if item_3_position is not None:
        candidate_map["3"] = item_3_position

    ordered: list[tuple[str, int]] = []
    cursor = -1
    for token in _TWENTY_F_ITEM_ORDER:
        min_start_at = cursor + 1
        if cursor >= 0:
            min_start_at = max(min_start_at, cursor + _TWENTY_F_GUIDE_MIN_MARKER_GAP_CHARS)
        if token == "3":
            position = candidate_map.get(token)
        elif token == "4":
            position = item_4_position
            if position is not None and position <= cursor:
                position = _find_twenty_f_locator_heading_position(
                    full_text=full_text,
                    candidates=candidate_lists.get(token, []),
                    start_at=min_start_at,
                )
            elif position is not None and position < min_start_at:
                position = _find_twenty_f_locator_heading_position(
                    full_text=full_text,
                    candidates=candidate_lists.get(token, []),
                    start_at=min_start_at,
                )
        else:
            position = _find_twenty_f_locator_heading_position(
                full_text=full_text,
                candidates=candidate_lists.get(token, []),
                start_at=min_start_at,
            )
        if position is None or position <= cursor:
            continue
        ordered.append((token, position))
        cursor = position
    return ordered


def _extract_twenty_f_locator_heading_candidates(locator_text: str) -> list[str]:
    """从 guide block 中提炼可回查正文的标题候选。

    Args:
        locator_text: 单个 Item 的 guide block。

    Returns:
        去重后的候选标题列表。

    Raises:
        RuntimeError: 提炼失败时抛出。
    """

    normalized = html.unescape(str(locator_text or ""))
    if not normalized:
        return []

    candidates: list[str] = []
    for match in _TWENTY_F_GUIDE_QUOTED_PHRASE_RE.finditer(normalized):
        candidates.extend(_expand_twenty_f_locator_candidate_segments(match.group(1)))

    # 按换行拆分处理 guide 表格中行分隔的标题短语；
    # 部分 20-F guide 在 HTML 转文本后将同列标题用 newline 分隔，
    # 这些短语经空格归一化后被合并为一个候选导致在正文中无法匹配。
    for line in normalized.split("\n"):
        stripped = line.strip()
        if _is_valid_twenty_f_locator_candidate(stripped):
            candidates.append(stripped)

    cleaned_text = _TWENTY_F_GUIDE_PAGE_TOKEN_RE.sub(" | ", normalized)
    for chunk in _TWENTY_F_GUIDE_SPLIT_RE.split(cleaned_text):
        candidates.extend(_expand_twenty_f_locator_candidate_segments(chunk))
    return _dedupe_twenty_f_locator_candidates(candidates)


def _expand_twenty_f_locator_candidate_segments(raw_text: str) -> list[str]:
    """展开单个 locator 短语中的层级标题候选。

    Args:
        raw_text: locator 中的原始短语。

    Returns:
        过滤后的候选标题列表。

    Raises:
        RuntimeError: 展开失败时抛出。
    """

    normalized = " ".join(str(raw_text or "").split())
    normalized = normalized.strip(" .,:;|/\"'“”()[]")
    if not normalized:
        return []

    parts = _TWENTY_F_GUIDE_SEGMENT_SPLIT_RE.split(normalized)
    candidates: list[str] = []
    for part in parts:
        candidate = part.strip(" .,:;|/\"'“”()[]")
        if _is_valid_twenty_f_locator_candidate(candidate):
            candidates.append(candidate)
    if _is_valid_twenty_f_locator_candidate(normalized):
        candidates.append(normalized)
    return candidates


def _is_valid_twenty_f_locator_candidate(candidate: str) -> bool:
    """判断 locator phrase 是否适合回查正文标题。

    Args:
        candidate: 待判断候选标题。

    Returns:
        可用于回查正文时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized = " ".join(str(candidate or "").split()).strip().lower()
    if not normalized:
        return False
    if normalized in _TWENTY_F_GUIDE_NOISE_PHRASES:
        return False
    if len(normalized) < 4 or len(normalized) > 120:
        return False
    if re.fullmatch(r"(?:[ivxlcdm]+|\d+(?:\s*-\s*\d+)?)", normalized) is not None:
        return False
    if _TWENTY_F_GUIDE_PAGE_TOKEN_RE.fullmatch(normalized) is not None:
        return False
    alpha_chars = sum(1 for char in normalized if char.isalpha())
    return alpha_chars >= 4


def _dedupe_twenty_f_locator_candidates(candidates: list[str]) -> list[str]:
    """对 locator 候选标题按归一化文本去重。

    Args:
        candidates: 原始候选标题列表。

    Returns:
        去重后的候选标题列表。

    Raises:
        RuntimeError: 去重失败时抛出。
    """

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = " ".join(str(candidate or "").split()).strip()
        lowered = normalized.lower()
        if not normalized or lowered in seen:
            continue
        seen.add(lowered)
        deduped.append(normalized)
    return deduped


def _find_twenty_f_locator_heading_position(
    *,
    full_text: str,
    candidates: list[str],
    start_at: int = 0,
) -> Optional[int]:
    """在正文中查找 locator phrase 对应的真实标题位置。

    Args:
        full_text: 文档全文。
        candidates: 待回查的标题候选列表。

    Returns:
        最早的有效正文标题位置；找不到时返回 ``None``。

    Raises:
        RuntimeError: 查找失败时抛出。
    """

    best_position: Optional[int] = None
    normalized_start = max(0, int(start_at))
    for candidate in candidates:
        normalized_candidate = str(candidate or "")
        if not normalized_candidate.strip():
            continue

        parts = [re.escape(part) for part in normalized_candidate.split() if part]
        patterns = [re.compile(re.escape(normalized_candidate), re.IGNORECASE)]
        if len(parts) >= 2:
            flexible_pattern = re.compile(r"\\s+".join(parts), re.IGNORECASE)
            if flexible_pattern.pattern != patterns[0].pattern:
                patterns.append(flexible_pattern)

        for pattern in patterns:
            for match in pattern.finditer(full_text, normalized_start):
                position = int(match.start())
                if _looks_like_twenty_f_report_suite_cover_marker(
                    full_text=full_text,
                    position=position,
                ):
                    continue
                if _looks_like_toc_page_line(full_text, position):
                    if _looks_like_twenty_f_annual_report_page_heading(
                        full_text=full_text,
                        position=position,
                        matched_text=candidate,
                    ):
                        if best_position is None or position < best_position:
                            best_position = position
                        break
                    continue
                if _looks_like_inline_toc_snippet(full_text, position):
                    continue
                if _looks_like_twenty_f_front_matter_marker(full_text, position):
                    continue
                if not _looks_like_twenty_f_standalone_heading_context(
                    full_text=full_text,
                    position=position,
                    matched_text=candidate,
                ):
                    continue
                if _looks_like_twenty_f_reference_guide_marker(full_text, position):
                    continue
                if best_position is None or position < best_position:
                    best_position = position
                break
            if best_position is not None:
                break
    return best_position


def _looks_like_twenty_f_report_suite_cover_marker(*, full_text: str, position: int) -> bool:
    """判断命中是否落在真实 Form 20-F 之前的报告套件封面/目录区。

    某些 annual-report-style 20-F 会把 Integrated Annual Report、Annual
    Financial Report、Governance Report 等整套报告文本串在 SEC Form 20-F
    正文之前。guide repair 回查 locator phrase 时，若直接命中这些册子封面
    或封面目录页，会把顶层 Item 锚点提前到错误位置，进而形成超大 section。

    该判定不依赖公司名，而是结合三类稳定信号：
    1. 局部窗口里出现报告套件标题；
    2. 同窗口出现封面/目录提示语；
    3. 命中之后不远处还能看到真正的 SEC filing 起点。

    Args:
        full_text: 文档全文。
        position: 待判断命中位置。

    Returns:
        更像报告套件封面/目录页命中时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    start = max(0, int(position) - 200)
    end = min(len(full_text), int(position) + 2500)
    context = full_text[start:end]
    title_hits = sum(
        1 for pattern in _TWENTY_F_REPORT_SUITE_TITLE_PATTERNS if pattern.search(context) is not None
    )
    if title_hits <= 0:
        return False
    cue_hits = sum(
        1 for pattern in _TWENTY_F_REPORT_SUITE_COVER_CUE_PATTERNS if pattern.search(context) is not None
    )
    if cue_hits <= 0:
        return False

    filing_start_end = min(len(full_text), int(position) + _TWENTY_F_REPORT_SUITE_LOOKAHEAD_CHARS)
    filing_start_context = full_text[int(position):filing_start_end]
    if _TWENTY_F_SEC_FILING_START_RE.search(filing_start_context) is not None:
        return True
    return title_hits >= 2 and cue_hits >= 2


def _find_twenty_f_cross_reference_item_3_start(
    *,
    full_text: str,
    fallback_end: int,
) -> Optional[int]:
    """为 guide 型 20-F 合成 ``Item 3`` 起点。

    这类文档常把 ``Item 3.D Risk factors`` 放到晚期章节，若直接采用该位置，
    会导致 ``Item 4`` 先于 ``Item 3``，从而破坏 SEC Item 顺序。
    因此在 ``Item 4`` 已找到但 ``Item 3`` 仍缺失/逆序时，回退到更早的
    报告正文起点；实在找不到时使用文档起点。

    Args:
        full_text: 文档全文。
        fallback_end: 已定位的 ``Item 4`` 起点。

    Returns:
        可用于 ``Item 3`` 的更早起点；无法定位时返回 ``0``。

    Raises:
        RuntimeError: 定位失败时抛出。
    """

    search_end = max(0, int(fallback_end))
    for pattern in _TWENTY_F_GUIDE_BODY_START_PATTERNS:
        for match in pattern.finditer(full_text, 0, search_end):
            position = int(match.start())
            if _looks_like_toc_page_line(full_text, position):
                continue
            if _looks_like_inline_toc_snippet(full_text, position):
                continue
            if _looks_like_twenty_f_front_matter_marker(full_text, position):
                continue
            if _looks_like_twenty_f_reference_guide_marker(full_text, position):
                continue
            return position
    return 0


def _skip_twenty_f_front_matter_markers(
    full_text: str,
    item_markers: list[tuple[str, int]],
) -> list[tuple[str, int]]:
    """跳过 20-F front matter / cross-reference guide 中的伪 Item markers。

    常见异常场景：
    1. Cover page 勾选框中的 ``Item 17 / Item 18``；
    2. ``Form 20-F Cross Reference Guide`` 表格中的条目行。

    这些位置不是正文章节边界，但会被通用 ``Item`` 正则命中，导致
    顶层 marker 顺序错位或后续正文被整块吸入错误父节。

    Args:
        full_text: 文档全文。
        item_markers: 初始 ``(item_token, position)`` 列表。

    Returns:
        过滤后的 marker 列表。

    Raises:
        RuntimeError: 处理失败时抛出。
    """

    if len(item_markers) < _TWENTY_F_MIN_RETRY_MARKERS_AFTER_FRONT_MATTER:
        return item_markers

    current_markers = list(item_markers)
    for _ in range(_TWENTY_F_FRONT_MATTER_MAX_SKIP_RETRIES):
        front_matter_prefix_count = 0
        for _, position in current_markers:
            if not _looks_like_twenty_f_front_matter_marker(full_text, position):
                break
            front_matter_prefix_count += 1

        if front_matter_prefix_count <= 0:
            return current_markers
        if not _should_skip_twenty_f_front_matter_prefix(
            current_markers,
            prefix_count=front_matter_prefix_count,
        ):
            return current_markers

        retry_start = current_markers[front_matter_prefix_count - 1][1] + 1
        retried_markers = _select_ordered_item_markers(
            full_text,
            item_pattern=_TWENTY_F_ITEM_PATTERN,
            ordered_tokens=_TWENTY_F_ITEM_ORDER,
            start_at=retry_start,
        )
        retried_markers = _repair_twenty_f_key_items_with_heading_fallback(
            full_text,
            retried_markers,
        )
        if len(retried_markers) < _TWENTY_F_MIN_RETRY_MARKERS_AFTER_FRONT_MATTER:
            return current_markers
        current_markers = retried_markers
    return current_markers


def _should_skip_twenty_f_front_matter_prefix(
    item_markers: list[tuple[str, int]],
    *,
    prefix_count: int,
) -> bool:
    """判断 front matter marker 前缀是否足以触发重试跳过。

    Args:
        item_markers: ``(item_token, position)`` 列表。
        prefix_count: 连续 front matter marker 数。

    Returns:
        应执行跳过重试时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    if prefix_count >= 2:
        return True
    if prefix_count != 1 or len(item_markers) < 2:
        return False

    first_token, first_pos = item_markers[0]
    next_pos = item_markers[1][1]
    if first_token not in {"17", "18", "19"}:
        return False
    return next_pos - first_pos >= _TWENTY_F_FRONT_MATTER_SINGLE_SKIP_MIN_GAP


def _looks_like_twenty_f_front_matter_marker(full_text: str, position: int) -> bool:
    """判断 Item 命中是否落在 20-F front matter / cross-reference guide。

    Args:
        full_text: 文档全文。
        position: Item 命中起点。

    Returns:
        命中 front matter 特征时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    start = max(0, int(position) - _TWENTY_F_FRONT_MATTER_LOOKBACK_CHARS)
    end = min(len(full_text), int(position) + _TWENTY_F_FRONT_MATTER_LOOKAHEAD_CHARS)
    context = full_text[start:end]
    return any(pattern.search(context) is not None for pattern in _TWENTY_F_FRONT_MATTER_CONTEXT_PATTERNS)


def _is_twenty_f_marker_contaminated(full_text: str, position: int) -> bool:
    """判断 marker 是否落在 ToC / front matter / guide 污染区。

    Args:
        full_text: 文档全文。
        position: marker 位置。

    Returns:
        位置更像目录、前言或 cross-reference guide 时返回 ``True``。
    """

    return (
        _looks_like_toc_page_line(full_text, position)
        or _looks_like_inline_toc_snippet(full_text, position)
        or _looks_like_twenty_f_front_matter_marker(full_text, position)
        or _looks_like_twenty_f_reference_guide_marker(full_text, position)
    )


def _result_markers_are_all_contaminated(
    full_text: str,
    markers: list[tuple[str, int]],
) -> bool:
    """判断当前已保留 marker 是否全部仍位于污染区。

    该判断用于 annual-report-style 20-F 的最终顺序修正阶段：
    若前面暂存的都是 front matter / guide 污染 marker，而后续补出的
    ``Item 5`` 已是干净正文锚点，就不应因为物理位置更早而再次把它删除。

    Args:
        full_text: 文档全文。
        markers: 当前已保留的 ``(token, position)`` 列表。

    Returns:
        当列表非空且全部 marker 都位于污染区时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    if not markers:
        return False
    return all(_is_twenty_f_marker_contaminated(full_text, pos) for _, pos in markers)


def _discard_trailing_contaminated_markers_before_position(
    full_text: str,
    markers: list[tuple[str, int]],
    position: int,
) -> list[tuple[str, int]]:
    """移除会挡住当前干净 marker 的尾部污染 marker。

    某些 20-F 会先在 guide / ToC 区留下 ``Item 1``、``Item 2`` 等早期
    marker，随后才在正文里命中真实 ``Item 3``。这些污染 marker 虽然 token
    顺序正确，但物理位置更靠后，会在 monotonicity 阶段把后续干净 marker
    挡掉。此时应先弹出尾部连续污染 marker，再交给常规回滚逻辑处理。

    Args:
        full_text: 文档全文。
        markers: 当前已保留的 ``(token, position)`` 列表。
        position: 当前待放置 marker 的位置。

    Returns:
        清理尾部污染 marker 后的列表。

    Raises:
        RuntimeError: 判断污染状态失败时抛出。
    """

    while (
        markers
        and position <= markers[-1][1]
        and _is_twenty_f_marker_contaminated(full_text, markers[-1][1])
    ):
        # 当前 marker 已确认不是污染位；若尾部仍是污染 marker，应优先清尾，
        # 避免污染 guide/ToC 锚点把更真实的正文 item 挡掉。
        markers.pop()
    return markers


def _enforce_marker_position_monotonicity(
    full_text: str,
    repaired: list[tuple[str, int]],
    original_positions: dict[str, int],
) -> list[tuple[str, int]]:
    """确保 marker 列表的位置单调递增。

    修复操作可能将某些 Item 向后移动到更远位置，导致后继 Item
    的位置落在新位置之前，形成逆序。

    策略：
    1. 若冲突 marker 仍位于 ToC / guide 污染区，直接丢弃该旧 marker；
    2. 若冲突来自正常正文 marker，则优先把上一个被移动的 marker 回滚到原始位置；
    3. 仅在回滚后仍无法维持单调时丢弃无法放置的 marker。

    Args:
        full_text: 文档全文。
        repaired: 按法定 token 顺序排列的 ``(token, position)`` 列表。
        original_positions: 修复前的 token → position 映射。

    Returns:
        保证位置单调递增的 ``(token, position)`` 列表。
    """

    if len(repaired) < 2:
        return repaired

    # 识别被修复移动的 token（位置与原始不同）
    moved_tokens = {
        token
        for token, pos in repaired
        if original_positions.get(token) is not None and original_positions[token] != pos
    }

    # 检测是否存在位置逆序
    positions = [pos for _, pos in repaired]
    if all(positions[i] < positions[i + 1] for i in range(len(positions) - 1)):
        return repaired

    result: list[tuple[str, int]] = []
    for token, pos in repaired:
        if pos is None:
            continue

        if not result or pos > result[-1][1]:
            result.append((token, pos))
            continue

        if _is_twenty_f_marker_contaminated(full_text, pos):
            continue

        result = _discard_trailing_contaminated_markers_before_position(
            full_text,
            result,
            pos,
        )
        if not result or pos > result[-1][1]:
            result.append((token, pos))
            continue

        prev_token, _ = result[-1]
        if prev_token in moved_tokens:
            prev_prev_pos = result[-2][1] if len(result) >= 2 else -1
            reverted_prev_pos = original_positions.get(prev_token)
            if (
                reverted_prev_pos is not None
                and reverted_prev_pos > prev_prev_pos
                and reverted_prev_pos < pos
                and not _is_twenty_f_marker_contaminated(full_text, reverted_prev_pos)
            ):
                result[-1] = (prev_token, reverted_prev_pos)
                if pos > reverted_prev_pos:
                    result.append((token, pos))
                    continue

        if token in moved_tokens:
            reverted_pos = original_positions.get(token)
            prev_pos = result[-1][1] if result else -1
            if (
                reverted_pos is not None
                and reverted_pos > prev_pos
                and not _is_twenty_f_marker_contaminated(full_text, reverted_pos)
            ):
                result.append((token, reverted_pos))
                continue

        original_token_pos = original_positions.get(token)
        original_token_is_contaminated = (
            original_token_pos is not None
            and _is_twenty_f_marker_contaminated(full_text, original_token_pos)
        )
        if (
            token == "18"
            and (original_token_pos is None or original_token_is_contaminated)
            and not _is_twenty_f_marker_contaminated(full_text, pos)
        ):
            # annual-report-style 20-F 中，财报正文标题可能物理上早于后续 SEC Item 标记。
            # 对后补出的非污染 Item 18，若原始位置不存在或原始位置本身已污染，
            # 这里不因逆序直接丢弃，交给后续按位置排序后的虚拟章节切分处理，
            # 以保留真实财报边界。
            result.append((token, pos))
            continue
        if (
            token == "5"
            and (original_token_pos is None or original_token_is_contaminated)
            and not _is_twenty_f_marker_contaminated(full_text, pos)
            and _result_markers_are_all_contaminated(full_text, result)
        ):
            # annual-report-style 20-F 常先出现早期正文 ``Financial Review``，
            # 再在文末附一个 20-F cross-reference guide。若前面暂存的 Item 1-4A
            # 全是 guide 污染位，这里允许保留更早的干净 Item 5，避免其在最终
            # monotonicity 修正里再次被删掉。
            result.append((token, pos))
    return result


def _repair_twenty_f_key_items_with_heading_fallback(
    full_text: str,
    item_markers: list[tuple[str, int]],
) -> list[tuple[str, int]]:
    """修复 20-F 关键 Item（3/5/18）的缺失和目录污染。

    Args:
        full_text: 文档全文。
        item_markers: 原始 ``(item_token, position)`` 列表。

    Returns:
        修复后的 marker 列表（按法定顺序输出）。

    Raises:
        RuntimeError: 修复失败时抛出。
    """

    original_positions = {token: position for token, position in item_markers}
    marker_map = dict(original_positions)
    fallback_map = _find_twenty_f_key_heading_positions(full_text)
    marker_map = _seed_monotonic_twenty_f_key_fallback(
        full_text=full_text,
        marker_map=marker_map,
        fallback_map=fallback_map,
    )

    original_markers_clustered = _has_guide_clustered_markers(item_markers, len(full_text))

    fallback_item_3 = fallback_map.get("3")
    item_3_upper_bound = _find_twenty_f_item_3_order_upper_bound(
        marker_map=marker_map,
        fallback_map=fallback_map,
        prefer_fallback_positions_only=original_markers_clustered,
    )
    if item_3_upper_bound is not None and (
        fallback_item_3 is None or int(fallback_item_3) >= int(item_3_upper_bound)
    ):
        synthetic_item_3 = _find_twenty_f_cross_reference_item_3_start(
            full_text=full_text,
            fallback_end=int(item_3_upper_bound),
        )
        if original_markers_clustered:
            # 当原始 ``Item 1/2/3`` 都聚在文末目录簇时，不能再让这些污染尾标
            # 充当 synthetic Item 3 的下界，否则会把更早的正文起点整体推回
            # 文末并直接失效。
            previous_item_3_lower_bound = _find_previous_item_position_before_token(
                marker_map=fallback_map,
                token="3",
                require_clean_marker=False,
            )
        else:
            previous_item_3_lower_bound = _find_previous_item_position_before_token(
                marker_map=marker_map,
                token="3",
                require_clean_marker=False,
            )
        if synthetic_item_3 is None:
            synthetic_item_3 = 0
        if previous_item_3_lower_bound is not None:
            synthetic_item_3 = max(
                int(synthetic_item_3),
                int(previous_item_3_lower_bound) + 1,
            )
        if synthetic_item_3 < int(item_3_upper_bound):
            fallback_map["3"] = int(synthetic_item_3)
        else:
            fallback_map.pop("3", None)

    if original_markers_clustered:
        # 聚簇 marker 说明原始 key-item 位置不可信，只让 fallback 结果参与顺序约束。
        ordering_marker_map = {
            token: position
            for token, position in marker_map.items()
            if token not in _TWENTY_F_REPAIR_ITEMS
        }
    else:
        ordering_marker_map = dict(marker_map)
    for token in _TWENTY_F_REPAIR_ITEMS:
        fallback_pos = fallback_map.get(token)
        if fallback_pos is None:
            continue
        if original_markers_clustered:
            # 当原始 Item 主链整体聚集在文末目录/guide 簇时，不能再用这些
            # 污染尾标去否决较早的 key-heading fallback；此时关键 Item 的
            # 顺序边界只应由更早的 key fallback 自身决定。
            lower_bound = _find_previous_item_position_before_token(
                marker_map=fallback_map,
                token=token,
                require_clean_marker=False,
            )
        else:
            lower_bound = _find_previous_item_position_before_token(
                marker_map=ordering_marker_map,
                token=token,
                full_text=full_text,
                require_clean_marker=True,
            )
        if lower_bound is not None and int(fallback_pos) <= int(lower_bound):
            later_fallback = _find_twenty_f_key_heading_position_after(
                full_text=full_text,
                token=token,
                start_at=int(lower_bound) + 1,
            )
            if later_fallback is not None and later_fallback > int(lower_bound):
                if _violates_existing_twenty_f_item_order(
                    marker_map=marker_map,
                    token=token,
                    candidate_position=int(later_fallback),
                ):
                    later_fallback = None
            if later_fallback is not None and later_fallback > int(lower_bound):
                fallback_map[token] = later_fallback
                ordering_marker_map[token] = later_fallback
                continue
            current_pos = marker_map.get(token)
            current_pos_is_contaminated = (
                current_pos is not None
                and _is_twenty_f_marker_contaminated(full_text, int(current_pos))
            )
            if token == "18" and current_pos_is_contaminated:
                ordering_marker_map[token] = int(fallback_pos)
                continue
            fallback_map.pop(token, None)
            continue
        ordering_marker_map[token] = int(fallback_pos)

    fallback_item_5 = fallback_map.get("5")

    if original_markers_clustered and fallback_item_5 is not None:
        item_18_lower_bound: Optional[int] = int(fallback_item_5)
    else:
        item_18_lower_bound = _find_previous_item_position_before_token(
            full_text=full_text,
            marker_map=marker_map,
            token="18",
        )
    fallback_item_18 = fallback_map.get("18")
    if item_18_lower_bound is not None and (
        fallback_item_18 is None or int(fallback_item_18) <= int(item_18_lower_bound)
    ):
        later_item_18 = _find_twenty_f_key_heading_position_after(
            full_text=full_text,
            token="18",
            start_at=int(item_18_lower_bound) + 1,
        )
        if later_item_18 is not None and later_item_18 > int(item_18_lower_bound):
            fallback_map["18"] = later_item_18
        elif fallback_item_18 is not None:
            current_item_18 = marker_map.get("18")
            current_item_18_is_contaminated = (
                current_item_18 is not None
                and _is_twenty_f_marker_contaminated(full_text, int(current_item_18))
            )
            if not current_item_18_is_contaminated:
                fallback_map.pop("18", None)

    clustered_markers = (
        _has_guide_clustered_markers(item_markers, len(full_text))
        and _has_monotonic_twenty_f_key_positions(fallback_map)
    )
    clustered_tokens = {token for token, _ in item_markers} if clustered_markers else set()
    has_monotonic_key_fallback = _has_monotonic_twenty_f_key_positions(fallback_map)

    for token in _TWENTY_F_REPAIR_ITEMS:
        fallback_pos = fallback_map.get(token)
        if fallback_pos is None:
            continue
        current_pos = marker_map.get(token)
        if current_pos is None:
            marker_map[token] = fallback_pos
            continue
        current_pos_is_contaminated = _is_twenty_f_marker_contaminated(
            full_text,
            int(current_pos),
        )
        if not clustered_markers and _should_preserve_current_twenty_f_key_marker(
            full_text=full_text,
            marker_map=marker_map,
            token=token,
            position=int(current_pos),
        ):
            if int(fallback_pos) < int(current_pos):
                # 当原始 marker 已经是干净且顺序安全的正文锚点时，
                # 不能因为 fallback 恰好命中了更早的 ToC/front-matter 文本，
                # 就把真实正文位置重新改写回去。
                continue
        if (
            has_monotonic_key_fallback
            or clustered_markers
            or current_pos_is_contaminated
        ) and fallback_pos != current_pos:
            marker_map[token] = fallback_pos

    if clustered_markers:
        for token in list(marker_map.keys()):
            if token in fallback_map:
                continue
            if token in clustered_tokens:
                marker_map.pop(token, None)

    if has_monotonic_key_fallback:
        first_key_position = min(int(position) for position in fallback_map.values())
        for token, original_pos in list(original_positions.items()):
            if token in fallback_map:
                continue
            if token not in marker_map:
                continue
            if int(original_pos) <= first_key_position:
                continue
            if _is_twenty_f_marker_contaminated(full_text, int(original_pos)):
                marker_map.pop(token, None)

    marker_map = _repair_twenty_f_item_5_with_subheading_fallback(
        full_text=full_text,
        marker_map=marker_map,
    )

    repaired: list[tuple[str, int]] = []
    for token in _TWENTY_F_ITEM_ORDER:
        position = marker_map.get(token)
        if position is None:
            continue
        repaired.append((token, position))
    monotonic_repaired = _enforce_marker_position_monotonicity(
        full_text,
        repaired,
        original_positions,
    )
    if _twenty_f_reconstructed_markers_cover_key_items(
        monotonic_repaired,
        required_tokens=_TWENTY_F_KEY_ITEMS,
    ):
        return monotonic_repaired
    if _twenty_f_reconstructed_markers_cover_key_items(
        repaired,
        required_tokens=_TWENTY_F_KEY_ITEMS,
    ):
        return _enforce_twenty_f_key_item_priority_monotonicity(
            repaired=repaired,
            protected_tokens=_TWENTY_F_KEY_ITEMS,
        )
    return monotonic_repaired


def _repair_twenty_f_item_5_with_subheading_fallback(
    *,
    full_text: str,
    marker_map: dict[str, int],
) -> dict[str, int]:
    """使用 Item 5 常见子标题修复 20-F 的 Item 5 缺失。

    一些 20-F 文档没有显式 ``Item 5`` 主标题，但会出现
    ``Liquidity and Capital Resources`` / ``Trend Information`` 等
    OFR 规范子标题。该回退仅在 ``Item 5`` 缺失时启用。

    Args:
        full_text: 文档全文。
        marker_map: 当前 token -> position 映射。

    Returns:
        修复后的 token -> position 映射。

    Raises:
        RuntimeError: 修复失败时抛出。
    """

    current_item_5 = marker_map.get("5")
    current_item_18 = marker_map.get("18")
    needs_item_5_repair = current_item_5 is None or (
        current_item_18 is not None and int(current_item_5) >= int(current_item_18)
    )
    if not needs_item_5_repair:
        return marker_map

    lower_candidates = [marker_map.get("3"), marker_map.get("4"), marker_map.get("4A")]
    normalized_lower_candidates = [position for position in lower_candidates if position is not None]
    if normalized_lower_candidates:
        lower_bound = max(normalized_lower_candidates)
    else:
        lower_bound = 0
    upper_bound = _find_next_item_position_after_token(
        marker_map=marker_map,
        token="5",
        full_text_len=len(full_text),
    )
    if upper_bound <= lower_bound:
        upper_bound = len(full_text)

    best_position: Optional[int] = None
    for pattern in _TWENTY_F_ITEM_5_SUBHEADING_PATTERNS:
        for match in pattern.finditer(full_text, pos=lower_bound, endpos=upper_bound):
            position = int(match.start())
            if _looks_like_toc_page_line(full_text, position):
                continue
            if _looks_like_inline_toc_snippet(full_text, position):
                continue
            if _looks_like_twenty_f_reference_guide_marker(full_text, position):
                continue
            best_position = position
            break
        if best_position is not None:
            break

    if best_position is not None:
        marker_map["5"] = best_position
    return marker_map


def _find_next_item_position_after_token(
    marker_map: dict[str, int],
    token: str,
    full_text_len: int,
) -> int:
    """查找给定 Item 之后最近已存在 Item 的位置作为扫描上界。

    Args:
        marker_map: token -> position 映射。
        token: 目标 token（如 ``"5"``）。
        full_text_len: 文档全文长度。

    Returns:
        扫描上界；若未找到更靠后的 Item，则返回一个极大值。

    Raises:
        RuntimeError: 计算失败时抛出。
    """

    try:
        index = _TWENTY_F_ITEM_ORDER.index(token)
    except ValueError:
        return max(0, int(full_text_len))

    candidates = [
        marker_map[next_token]
        for next_token in _TWENTY_F_ITEM_ORDER[index + 1 :]
        if next_token in marker_map
    ]
    if not candidates:
        return max(0, int(full_text_len))
    return min(candidates)


def _find_previous_item_position_before_token(
    *,
    marker_map: dict[str, int],
    token: str,
    full_text: Optional[str] = None,
    require_clean_marker: bool = True,
) -> Optional[int]:
    """查找给定 Item 之前最近的已知正文 Item 位置。

    Args:
        marker_map: token -> position 映射。
        token: 目标 token。
        full_text: 文档全文；当 ``require_clean_marker=True`` 时用于污染过滤。
        require_clean_marker: 是否跳过目录/guide 污染 marker。

    Returns:
        最近前序正文 Item 的位置；不存在时返回 ``None``。
    """

    try:
        index = _TWENTY_F_ITEM_ORDER.index(token)
    except ValueError:
        return None

    previous_positions: list[int] = []
    for previous_token in _TWENTY_F_ITEM_ORDER[:index]:
        position = marker_map.get(previous_token)
        if position is None:
            continue
        if (
            require_clean_marker
            and full_text is not None
            and _is_twenty_f_marker_contaminated(full_text, int(position))
        ):
            continue
        previous_positions.append(int(position))
    if not previous_positions:
        return None
    return max(previous_positions)


def _should_preserve_current_twenty_f_key_marker(
    *,
    full_text: str,
    marker_map: dict[str, int],
    token: str,
    position: int,
) -> bool:
    """判断当前 key-item marker 是否已经是可信正文锚点。

    仅当 marker 同时满足以下条件时，才应阻止更早的 fallback 覆盖它：
    1. 当前 marker 不在 ToC / guide / front matter 污染区；
    2. 当前位置仍满足当前 ``marker_map`` 下的法定顺序约束；
    3. 当前位置本身看起来像真正展开正文的 Item 标题，而非正文中的引用句子。

    Args:
        full_text: 文档全文。
        marker_map: 当前 token -> position 映射。
        token: 目标 token。
        position: 当前 marker 位置。

    Returns:
        当前 marker 已可视为可信正文锚点时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized_position = int(position)
    if _is_twenty_f_marker_contaminated(full_text, normalized_position):
        return False

    lower_bound = _find_previous_item_position_before_token(
        full_text=full_text,
        marker_map=marker_map,
        token=token,
    )
    upper_bound = _find_next_item_position_after_token(
        marker_map=marker_map,
        token=token,
        full_text_len=len(full_text),
    )
    is_order_safe = (
        (lower_bound is None or normalized_position > int(lower_bound))
        and normalized_position < int(upper_bound)
    )
    if not is_order_safe:
        return False

    matched_text = f"Item {token}"
    if token == "18" and _may_have_twenty_f_item18_heading_context(
        full_text=full_text,
        position=normalized_position,
    ):
        if _looks_like_twenty_f_item18_heading_with_body(full_text, normalized_position):
            return True
    return _looks_like_twenty_f_direct_item_heading_with_body(
        full_text=full_text,
        position=normalized_position,
        matched_text=matched_text,
    )


def _violates_existing_twenty_f_item_order(
    *,
    marker_map: dict[str, int],
    token: str,
    candidate_position: int,
) -> bool:
    """判断候选 fallback 是否会回跳到当前已知前序 Item 之前。

    某些 annual-report-style 20-F 会同时出现当前已选中的较晚 Item marker，
    以及通过 key-heading re-search 找到的更早 fallback。若这个更早 fallback
    实际落在当前已知前序 Item 之前，说明它更像跨页目录残留或更早伪命中，
    不能用来替换当前顺序内的 marker。

    Args:
        marker_map: 当前 token -> position 映射。
        token: 目标 token。
        candidate_position: 候选 fallback 位置。

    Returns:
        候选位置落在当前前序 Item 之前时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    previous_position = _find_previous_item_position_before_token(
        marker_map=marker_map,
        token=token,
        require_clean_marker=False,
    )
    if previous_position is None:
        return False
    return int(candidate_position) <= int(previous_position)


def _find_twenty_f_item_3_order_upper_bound(
    *,
    marker_map: dict[str, int],
    fallback_map: dict[str, int],
    prefer_fallback_positions_only: bool = False,
) -> Optional[int]:
    """返回 ``Item 3`` 在顺序上不可跨越的最早后继锚点。

    ``Item 3`` 的 heading fallback 有时会命中晚期 ``Risk Factors``，
    而 ``Item 4`` / ``Item 4A`` / ``Item 5`` 已经在正文中被正确识别。
    若直接采用这个过晚的 ``Item 3``，后续顺序修正会把已经找到的
    ``Item 4/5`` 当成逆序 marker 删除。

    Args:
        marker_map: 当前 token -> position 映射。
        fallback_map: 本轮 fallback token -> position 映射。
        prefer_fallback_positions_only: 是否只使用 fallback 命中的后继锚点。

    Returns:
        ``Item 4`` / ``Item 4A`` / ``Item 5`` 中最早的已知位置；若都缺失则返回 ``None``。

    Raises:
        RuntimeError: 计算失败时抛出。
    """

    candidates: list[int] = []
    for token in ("4", "4A", "5"):
        current_position = marker_map.get(token)
        fallback_position = fallback_map.get(token)
        if not prefer_fallback_positions_only and current_position is not None:
            candidates.append(int(current_position))
        if fallback_position is not None:
            candidates.append(int(fallback_position))
    if not candidates:
        return None
    return min(candidates)


def _find_twenty_f_key_heading_positions(full_text: str) -> dict[str, int]:
    """查找 20-F 关键 Item 标题在正文中的首个可用位置。

    Args:
        full_text: 文档全文。

    Returns:
        命中的 token→position 映射。

    Raises:
        RuntimeError: 查找失败时抛出。
    """

    positions: dict[str, int] = {}
    for token, patterns in _TWENTY_F_KEY_ITEM_FALLBACK_PATTERNS.items():
        if token == "5":
            best_position = _find_twenty_f_item_5_heading_position(
                full_text=full_text,
                start_at=0,
            )
            if best_position is not None:
                positions[token] = best_position
            continue
        best_position: Optional[int] = None
        for pattern in patterns:
            position = _find_first_valid_twenty_f_heading_position(
                full_text=full_text,
                pattern=pattern,
                start_at=0,
                token=token,
            )
            if position is None:
                continue
            if best_position is None or position < best_position:
                best_position = position
        if best_position is not None:
            positions[token] = best_position
    return positions


def _find_twenty_f_key_heading_position_after(
    *,
    full_text: str,
    token: str,
    start_at: int,
) -> Optional[int]:
    """在给定下界之后重搜单个 20-F key-item 正文锚点。

    Args:
        full_text: 文档全文。
        token: 目标 key item token。
        start_at: 搜索起点。

    Returns:
        最早的有效命中位置；找不到时返回 ``None``。
    """

    patterns = _TWENTY_F_KEY_ITEM_FALLBACK_PATTERNS.get(token, ())
    best_position: Optional[int] = None
    normalized_start = max(0, int(start_at))
    if token == "5":
        return _find_twenty_f_item_5_heading_position(
            full_text=full_text,
            start_at=normalized_start,
        )
    for pattern in patterns:
        position = _find_first_valid_twenty_f_heading_position(
            full_text=full_text,
            pattern=pattern,
            start_at=normalized_start,
            token=token,
        )
        if position is None:
            continue
        if best_position is None or position < best_position:
            best_position = position
    return best_position


def _find_first_valid_twenty_f_heading_position(
    *,
    full_text: str,
    pattern: re.Pattern[str],
    start_at: int,
    token: str,
) -> Optional[int]:
    """查找单个 20-F fallback pattern 的首个有效正文位置。

    Args:
        full_text: 文档全文。
        pattern: 当前 fallback 正则。
        start_at: 搜索起点。
        token: 当前正在重搜的 key-item token。

    Returns:
        首个有效正文命中位置；未命中返回 ``None``。

    Raises:
        RuntimeError: 搜索失败时抛出。
    """

    normalized_start = max(0, int(start_at))
    provisional_toc_position: Optional[int] = None
    for match in pattern.finditer(full_text, normalized_start):
        position = int(match.start())
        matched_text = str(match.group(0) or "")
        # 真实 Item 18 标题后常紧跟 “starting on page F-1” 之类正文 locator，
        # 通用 ToC 检测会把它误判成目录行；这里用正文体征做白名单豁免。
        is_real_item18_heading_with_body = False
        if token == "18" and _may_have_twenty_f_item18_heading_context(
            full_text=full_text,
            position=position,
        ):
            is_real_item18_heading_with_body = _looks_like_twenty_f_item18_heading_with_body(
                full_text,
                position,
            )
        if _looks_like_toc_page_line(full_text, position) and not is_real_item18_heading_with_body:
            if _looks_like_twenty_f_annual_report_page_heading(
                full_text=full_text,
                position=position,
                matched_text=matched_text,
            ):
                # annual-report-style 20-F 目录页常会先出现合法页眉样式的
                # ``Item 3 / 4 / 5`` 行，再在后文出现真正正文标题。
                # 若这里直接返回，会让前面的 ToC 命中挡住后续真实 heading，
                # 典型后果就是 NVS 一类文档从 Item 4/5 起切，丢失 Item 3。
                #
                # 因此把这类命中降级为 provisional fallback：先记住位置，
                # 继续向后搜索更干净的 standalone heading；只有后面完全
                # 找不到正文标题时，才回退到这个 ToC 年报页眉位置。
                if provisional_toc_position is None:
                    provisional_toc_position = position
            continue
        if _looks_like_inline_toc_snippet(full_text, position) and not is_real_item18_heading_with_body:
            continue
        if _looks_like_twenty_f_front_matter_marker(full_text, position):
            continue
        if _looks_like_twenty_f_direct_item_heading_with_body(
            full_text=full_text,
            position=position,
            matched_text=matched_text,
        ):
            return position
        if not _looks_like_twenty_f_standalone_heading_context(
            full_text=full_text,
            position=position,
            matched_text=matched_text,
        ):
            continue
        if _looks_like_twenty_f_reference_guide_marker(full_text, position):
            continue
        if _looks_like_twenty_f_inline_cross_reference(full_text=full_text, position=position):
            continue
        return position
    return provisional_toc_position


def _looks_like_twenty_f_direct_item_heading_with_body(
    *,
    full_text: str,
    position: int,
    matched_text: str,
) -> bool:
    """判断命中是否为直接展开正文的 ``Item`` 主标题。

    某些 annual-report-style 20-F 在正文里会使用标准 SEC 标题：
    ``Item 3. Key Information``、``Item 4. Information on the Company``。
    这类标题后面紧接子项或正文，但前文目录区也会出现完全相同的文本。

    为避免把目录里的早期命中当成正文，这里不只看标题行本身，还要求：
    1. 当前行以命中的 Item 标题起始；
    2. 后续相邻行里能看到真正正文，而不是纯页码/目录串。

    Args:
        full_text: 文档全文。
        position: 命中起点。
        matched_text: 命中的标题文本。

    Returns:
        更像直接展开正文的 Item 主标题时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    line_start, line_end = _extract_twenty_f_line_bounds(full_text, position)
    line_text = " ".join(full_text[line_start:line_end].split())
    normalized_match = " ".join(str(matched_text or "").split())
    if not line_text or not normalized_match:
        return False
    if not line_text.lower().startswith(normalized_match.lower()):
        return False

    next_lines = _collect_twenty_f_neighbor_lines(
        full_text,
        line_start=line_start,
        line_end=line_end,
        forward=True,
        max_lines=_TWENTY_F_DIRECT_ITEM_BODY_LOOKAHEAD_LINES,
    )
    if _count_twenty_f_contiguous_page_locator_lines(next_lines, from_end=False) >= 1:
        return False
    for line_text in next_lines:
        normalized_line = " ".join(str(line_text or "").split())
        if not normalized_line:
            continue
        if _looks_like_twenty_f_page_locator_line(normalized_line):
            continue
        lowered_line = normalized_line.lower()
        if lowered_line == "not applicable.":
            return True
        word_count = len(_TWENTY_F_ANNUAL_REPORT_HEADING_PREFIX_WORD_RE.findall(normalized_line))
        if word_count >= 4:
            return True
    return False


def _find_twenty_f_item_5_heading_position(
    *,
    full_text: str,
    start_at: int,
) -> Optional[int]:
    """按两层优先级查找 20-F Item 5 的正文锚点。

    优先级：
    1. 真实主标题 ``Operating and Financial Review and Prospects``；
    2. 若主标题不存在，再在 OFR 常见子标题中选择最早合法命中。

    Args:
        full_text: 文档全文。
        start_at: 搜索起点。

    Returns:
        最优正文命中位置；未命中返回 ``None``。

    Raises:
        RuntimeError: 搜索失败时抛出。
    """

    patterns = _TWENTY_F_KEY_ITEM_FALLBACK_PATTERNS.get("5", ())
    primary_patterns = patterns[:2]
    secondary_patterns = patterns[2:]

    for pattern in primary_patterns:
        position = _find_first_valid_twenty_f_heading_position(
            full_text=full_text,
            pattern=pattern,
            start_at=start_at,
            token="5",
        )
        if position is not None:
            return position

    best_secondary_position: Optional[int] = None
    for pattern in secondary_patterns:
        position = _find_first_valid_twenty_f_heading_position(
            full_text=full_text,
            pattern=pattern,
            start_at=start_at,
            token="5",
        )
        if position is None:
            continue
        if best_secondary_position is None or position < best_secondary_position:
            best_secondary_position = position
    return best_secondary_position


def _looks_like_twenty_f_inline_cross_reference(*, full_text: str, position: int) -> bool:
    """判断命中是否更像正文里的章节引用，而非真正标题。

    典型误命中：
    - ``see Item 3. Key Information ...``
    - ``as described under Item 5. Operating and Financial Review ...``
    - ``Risk Factors in Section D under Item 3 ...``

    Args:
        full_text: 文档全文。
        position: 命中位置。

    Returns:
        更像正文引用时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    start = max(0, int(position) - 160)
    prefix = full_text[start : max(0, int(position))]
    if not prefix:
        return False
    previous_non_space = prefix.rstrip()
    if not previous_non_space:
        return False
    if previous_non_space[-1] in {"\n", "\r"}:
        return False
    raw_prefix_lower = prefix.lower()
    has_coarse_reference_hint = any(
        hint in raw_prefix_lower for hint in _TWENTY_F_INLINE_REFERENCE_PREFIX_HINTS
    )
    has_coarse_quote_hint = any(token in prefix for token in ('"', '“', '”'))
    if not has_coarse_reference_hint and not has_coarse_quote_hint:
        return False
    normalized_prefix = " ".join(prefix.split())
    if _TWENTY_F_INLINE_REFERENCE_PREFIX_RE.search(normalized_prefix) is not None:
        return True

    line_start = full_text.rfind("\n", 0, int(position)) + 1
    line_end = full_text.find("\n", int(position))
    if line_end < 0:
        line_end = len(full_text)
    raw_line_prefix = full_text[line_start:int(position)]
    line_prefix = " ".join(raw_line_prefix.split()).lower()
    if not line_prefix:
        return False
    has_quote_prefix = has_coarse_quote_hint and any(
        token in raw_line_prefix for token in ('"', '“', '”')
    )
    has_reference_prefix = _TWENTY_F_INLINE_REFERENCE_PREFIX_RE.search(line_prefix) is not None
    if not has_quote_prefix and not has_reference_prefix:
        return False
    line_suffix = " ".join(full_text[int(position):line_end].split()).lower()
    if has_quote_prefix and any(token in line_suffix for token in ('"', '“', '”')):
        return True
    has_subitem_tail = any(
        token in line_suffix
        for token in ("5.a", "5.b", "5.c", "5.d", "5a", "5b", "5c", "5d", " - ")
    )
    return has_reference_prefix and has_subitem_tail


def _looks_like_twenty_f_reference_guide_marker(full_text: str, position: int) -> bool:
    """判断 20-F marker 命中是否落在 cross-reference guide / locator 语境中。

    与封面勾选框不同，这类内容通常已经进入正文前言或 guide 表格，会包含
    ``Annual Report`` / ``AFR`` / ``Note X to ... financial statements`` /
    页码范围等定位信息。它们能提供引用关系，但不是可切分的 Item 正文。

    Args:
        full_text: 文档全文。
        position: marker 命中起点。

    Returns:
        命中 locator guide 语境时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    probe_start = max(0, int(position) - 120)
    probe_end = min(len(full_text), int(position) + 240)
    if _TWENTY_F_REFERENCE_GUIDE_LOCAL_PROBE_RE.search(full_text[probe_start:probe_end]) is None:
        return False

    line_start, line_end = _extract_twenty_f_line_bounds(full_text, position)
    current_line = " ".join(full_text[line_start:line_end].split()).lower()
    if (
        "item 18" in current_line
        or "financial statements" in current_line
    ) and _may_have_twenty_f_item18_heading_context(
        full_text=full_text,
        position=position,
    ) and _looks_like_twenty_f_item18_heading_with_body(full_text, position):
        return False

    start = max(0, int(position) - _TWENTY_F_REFERENCE_GUIDE_LOOKBACK_CHARS)
    end = min(len(full_text), int(position) + _TWENTY_F_REFERENCE_GUIDE_LOOKAHEAD_CHARS)
    context = full_text[start:end]
    if any(pattern.search(context) is not None for pattern in _TWENTY_F_FRONT_MATTER_CONTEXT_PATTERNS):
        return True
    return _looks_like_reference_guide_content(title=None, content=context)


def _may_be_twenty_f_item18_heading_with_body(full_text: str, position: int) -> bool:
    """用低成本局部探针判断是否值得执行 `Item 18` 正文深判定。

    `UBS` 一类 annual-report-style 20-F 在 locator heading 回查阶段会命中大量
    非 `Item 18` 候选。若每个候选都进入完整的邻域扫描，CPU 会主要消耗在
    `Item 18` 白名单判断本身，而不是实际的 marker 过滤上。这里先以一个很小
    的局部窗口检查附近是否同时出现 `item 18` 与 `financial statements`；
    只有满足这两个最基本的同源信号时，才继续做后续昂贵的逐行分析。

    Args:
        full_text: 文档全文。
        position: 待判断命中位置。

    Returns:
        可能是 `Item 18` 标题并带正文时返回 ``True``；否则返回 ``False``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized_position = max(0, int(position))
    probe_start = max(0, normalized_position - _TWENTY_F_ITEM18_BODY_PROBE_LOOKBACK_CHARS)
    probe_end = min(
        len(full_text),
        normalized_position + _TWENTY_F_ITEM18_BODY_PROBE_LOOKAHEAD_CHARS,
    )
    probe_text = full_text[probe_start:probe_end].lower()
    if "item" not in probe_text or "18" not in probe_text:
        return False
    return "financial statements" in probe_text


def _looks_like_twenty_f_item18_heading_with_body(full_text: str, position: int) -> bool:
    """判断命中位置是否为真实的 Item 18 标题，而非 locator guide。

    某些 20-F 的 Item 18 正文会采用如下合法 SEC 写法：

    1. 单独标题行：``Item 18.``
    2. 下一行标题延续：``FINANCIAL STATEMENTS``
    3. 紧随一段正文，说明财报“attached hereto / included herein / starting on page F-1”

    这类正文自然会同时出现 ``Annual Report``、``page F-1`` 等 locator 信号，
    若仅凭 guide 关键词统计，容易把真正的 Item 18 正文误判为
    cross-reference guide，进而丢失关键章节边界。

    Args:
        full_text: 文档全文。
        position: 待判断的 marker 命中位置。

    Returns:
        更像真实 Item 18 标题并且后续存在正文时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    if not _may_be_twenty_f_item18_heading_with_body(full_text, position):
        return False

    line_start, line_end = _extract_twenty_f_line_bounds(full_text, position)
    current_line = " ".join(full_text[line_start:line_end].split())
    if "item 18" not in current_line.lower():
        return False
    # 目录桩常把多个 Item 和页码压在同一行；真实标题行通常只承载 Item 18 自身。
    if re.search(
        r"(?i)\bfinancial\s+statements\b\s+(?:page(?:s)?\s+)?\d{1,3}(?:\s*(?:-|–|—|to)\s*\d{1,3})?\b",
        current_line,
    ) is not None:
        return False
    if len(re.findall(r"(?i)\bitem\s+(?:16[A-J]|4A|1[0-9]|[1-9])\b", current_line)) > 1:
        return False

    next_lines = _collect_twenty_f_neighbor_lines(
        full_text,
        line_start=line_start,
        line_end=line_end,
        forward=True,
        max_lines=_TWENTY_F_ITEM18_BODY_LOOKAHEAD_LINES,
    )
    if not next_lines:
        return False

    heading_window = [current_line] + next_lines[:2]
    if not any("financial statements" in line.lower() for line in heading_window):
        return False

    if _count_twenty_f_contiguous_page_locator_lines(next_lines, from_end=False) >= 2:
        return False
    return _contains_twenty_f_page_heading_prose(next_lines)


def _may_have_twenty_f_item18_heading_context(*, full_text: str, position: int) -> bool:
    """用低成本局部窗口判断是否值得继续做 Item 18 正文白名单判定。

    真实 Item 18 heading-with-body 场景至少应在局部窗口里同时出现
    ``Item 18`` 和 ``Financial Statements``。大多数误命中的
    ``financial statements`` 普通正文引用并不满足这一条件，没必要继续执行
    更昂贵的逐行邻域分析。

    Args:
        full_text: 文档全文。
        position: 当前命中位置。

    Returns:
        局部窗口同时具备 ``Item 18`` 与 ``Financial Statements`` 体征时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    start = max(0, int(position) - 120)
    end = min(len(full_text), int(position) + 180)
    snippet = full_text[start:end]
    return (
        _TWENTY_F_ITEM_18_TOKEN_RE.search(snippet) is not None
        and _TWENTY_F_FINANCIAL_STATEMENTS_RE.search(snippet) is not None
    )


def _extract_twenty_f_line_bounds(full_text: str, position: int) -> tuple[int, int]:
    """返回指定位置所在文本行的起止边界。

    Args:
        full_text: 文档全文。
        position: 文本中的命中位置。

    Returns:
        ``(line_start, line_end)``，其中 ``line_end`` 为行尾换行符位置或全文末尾。

    Raises:
        RuntimeError: 边界计算失败时抛出。
    """

    normalized_position = max(0, min(len(full_text), int(position)))
    line_start = full_text.rfind("\n", 0, normalized_position)
    if line_start < 0:
        line_start = 0
    else:
        line_start += 1
    line_end = full_text.find("\n", normalized_position)
    if line_end < 0:
        line_end = len(full_text)
    return line_start, line_end


def _collect_twenty_f_neighbor_lines(
    full_text: str,
    *,
    line_start: int,
    line_end: int,
    forward: bool,
    max_lines: int,
) -> list[str]:
    """收集当前行前后相邻的非空文本行。

    Args:
        full_text: 文档全文。
        line_start: 当前行起点。
        line_end: 当前行终点。
        forward: ``True`` 表示向后收集，``False`` 表示向前收集。
        max_lines: 最多收集的非空行数。

    Returns:
        相邻非空行列表；向前收集时按自然阅读顺序返回。

    Raises:
        RuntimeError: 收集失败时抛出。
    """

    lines: list[str] = []
    if max_lines <= 0:
        return lines

    if forward:
        cursor = line_end
        while len(lines) < max_lines and cursor < len(full_text):
            if full_text[cursor] == "\n":
                cursor += 1
            next_end = full_text.find("\n", cursor)
            if next_end < 0:
                next_end = len(full_text)
            line_text = full_text[cursor:next_end].strip()
            if line_text:
                lines.append(line_text)
            cursor = next_end
        return lines

    cursor = line_start
    while len(lines) < max_lines and cursor > 0:
        previous_end = cursor - 1
        previous_start = full_text.rfind("\n", 0, previous_end)
        if previous_start < 0:
            previous_start = 0
        else:
            previous_start += 1
        line_text = full_text[previous_start:cursor].strip()
        if line_text:
            lines.append(line_text)
        cursor = max(0, previous_start - 1)
    lines.reverse()
    return lines


def _looks_like_twenty_f_page_locator_line(line_text: str) -> bool:
    """判断单行文本是否更像“标题 + 页码”形式的目录/页眉行。

    Args:
        line_text: 待判断的单行文本。

    Returns:
        更像页码定位行时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized_line = " ".join(str(line_text or "").split())
    if not normalized_line:
        return False
    return (
        _TOC_PAGE_LINE_PATTERN.match(normalized_line) is not None
        or _TOC_PAGE_LEADING_NUMBER_LINE_PATTERN.match(normalized_line) is not None
    )


def _contains_twenty_f_page_heading_prose(lines: list[str]) -> bool:
    """判断相邻行中是否出现足够长的正文句子。

    Args:
        lines: 待检查的相邻文本行列表。

    Returns:
        存在明显正文行时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    for line_text in lines:
        normalized_line = " ".join(str(line_text or "").split())
        if not normalized_line:
            continue
        if _looks_like_twenty_f_page_locator_line(normalized_line):
            continue
        word_count = len(_TWENTY_F_ANNUAL_REPORT_HEADING_PREFIX_WORD_RE.findall(normalized_line))
        if word_count >= _TWENTY_F_ANNUAL_REPORT_PAGE_HEADING_MIN_PROSE_WORDS:
            return True
    return False


def _count_twenty_f_contiguous_page_locator_lines(
    lines: list[str],
    *,
    from_end: bool,
) -> int:
    """统计相邻行列表一侧连续出现的页码定位行数量。

    Args:
        lines: 相邻文本行列表。
        from_end: ``True`` 时从列表尾部向前统计，否则从头部向后统计。

    Returns:
        连续页码定位行数量。

    Raises:
        RuntimeError: 统计失败时抛出。
    """

    ordered_lines = list(reversed(lines)) if from_end else list(lines)
    locator_count = 0
    for line_text in ordered_lines:
        if not _looks_like_twenty_f_page_locator_line(line_text):
            break
        locator_count += 1
    return locator_count


def _looks_like_twenty_f_annual_report_page_heading(
    *,
    full_text: str,
    position: int,
    matched_text: str,
) -> bool:
    """判断命中是否为年报页标题，而非目录页码行。

    BTI 一类 annual-report-style 20-F 常把真实章节标题渲染为
    ``栏目分组 + 标题 + 页码`` 的页眉行。其文本外形与目录行接近，
    但后面紧跟正文段落，而不是更多目录条目。

    Args:
        full_text: 文档全文。
        position: 命中起点。
        matched_text: 命中的标题短语。

    Returns:
        更像真实年报页标题时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    line_start, line_end = _extract_twenty_f_line_bounds(full_text, position)
    line_text = " ".join(full_text[line_start:line_end].split())
    if not line_text:
        return False
    lowered_line_text = line_text.lower()
    if "|" in line_text or '"' in line_text or "“" in line_text or "”" in line_text:
        return False
    if lowered_line_text.startswith("item "):
        return False
    if _TWENTY_F_ANNUAL_REPORT_PAGE_RANGE_RE.search(line_text) is not None:
        return False
    if _TWENTY_F_ANNUAL_REPORT_PAGE_NUMBER_RE.search(line_text) is None:
        return False

    normalized_matched_text = " ".join(str(matched_text or "").split())
    lowered_match = normalized_matched_text.lower()
    matched_index = lowered_line_text.find(lowered_match)
    if matched_index < 0:
        return False

    footer_context_start = max(0, int(position) - _TWENTY_F_ANNUAL_REPORT_FOOTER_CONTEXT_LOOKBACK_CHARS)
    footer_context = full_text[footer_context_start:int(position)]
    footer_context_hits = sum(
        1
        for pattern in _TWENTY_F_ANNUAL_REPORT_FOOTER_CONTEXT_PATTERNS
        if pattern.search(footer_context) is not None
    )
    repeat_window_end = min(
        len(full_text),
        int(position) + len(normalized_matched_text) + _TWENTY_F_ANNUAL_REPORT_REPEAT_LOOKAHEAD_CHARS,
    )
    repeated_heading = re.search(
        re.escape(normalized_matched_text),
        full_text[int(position) + len(normalized_matched_text) : repeat_window_end],
        re.IGNORECASE,
    )
    has_footer_context = footer_context_hits >= _TWENTY_F_ANNUAL_REPORT_FOOTER_CONTEXT_MIN_HITS

    prefix_text = line_text[:matched_index].strip(" .,:;|/-")
    prefix_word_count = len(_TWENTY_F_ANNUAL_REPORT_HEADING_PREFIX_WORD_RE.findall(prefix_text))
    if (
        prefix_word_count > _TWENTY_F_ANNUAL_REPORT_PAGE_HEADING_MAX_PREFIX_WORDS
        and not has_footer_context
        and repeated_heading is None
    ):
        return False

    previous_lines = _collect_twenty_f_neighbor_lines(
        full_text,
        line_start=line_start,
        line_end=line_end,
        forward=False,
        max_lines=_TWENTY_F_ANNUAL_REPORT_PAGE_HEADING_NEIGHBOR_LINES,
    )
    next_lines = _collect_twenty_f_neighbor_lines(
        full_text,
        line_start=line_start,
        line_end=line_end,
        forward=True,
        max_lines=_TWENTY_F_ANNUAL_REPORT_PAGE_HEADING_NEIGHBOR_LINES,
    )

    if any("inside this report" in line.lower() for line in previous_lines[-2:]):
        return False

    previous_locator_run = _count_twenty_f_contiguous_page_locator_lines(
        previous_lines,
        from_end=True,
    )
    next_locator_run = _count_twenty_f_contiguous_page_locator_lines(
        next_lines,
        from_end=False,
    )
    if previous_locator_run >= 2 or next_locator_run >= 1:
        return False

    return _contains_twenty_f_page_heading_prose(next_lines)


def _looks_like_twenty_f_standalone_heading_context(
    *,
    full_text: str,
    position: int,
    matched_text: str,
) -> bool:
    """判断 bare fallback phrase 是否处在“独立标题”语境，而非正文句子中。

    20-F 的 key-item fallback 允许只靠 ``Financial Statements`` /
    ``Key Information`` 等短语命中，但若该短语位于长句中，会把正文引用
    误当成章节标题。这里仅收紧“无显式 Item token”的 bare phrase 场景；
    对 ``Item 18. Financial Statements`` 这类法定写法不做额外限制。

    Args:
        full_text: 文档全文。
        position: 命中起点。
        matched_text: 当前正则命中的原始文本。

    Returns:
        更像独立标题时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized_match = str(matched_text or "")
    if re.search(r"(?i)\bitem\s+(?:16[A-J]|4A|1[0-9]|[1-9])\b", normalized_match) is not None:
        return True

    # 限制换行回看范围：合理标题行不超过 500 字符。
    # 无限回看在缺少换行的超大文本（如 SAN 3.6M）上会生成数 MB 的 prefix，
    # 导致后续 findall / search 极慢。
    _MAX_LINE_LOOKBACK = 500
    lookback_start = max(0, int(position) - _MAX_LINE_LOOKBACK)
    newline_pos = full_text.rfind("\n", lookback_start, max(0, int(position)))
    if newline_pos >= 0:
        line_start = newline_pos + 1
    elif lookback_start > 0:
        # 500 字符内无换行，说明在超长行中，不太可能是独立标题
        return False
    else:
        line_start = 0
    line_end = full_text.find("\n", int(position))
    if line_end < 0:
        line_end = len(full_text)

    prefix = full_text[line_start:max(0, int(position))]
    if not prefix.strip():
        previous_lines = _collect_twenty_f_neighbor_lines(
            full_text,
            line_start=line_start,
            line_end=line_end,
            forward=False,
            max_lines=_TWENTY_F_ANNUAL_REPORT_PAGE_HEADING_NEIGHBOR_LINES,
        )
        next_lines = _collect_twenty_f_neighbor_lines(
            full_text,
            line_start=line_start,
            line_end=line_end,
            forward=True,
            max_lines=_TWENTY_F_ANNUAL_REPORT_PAGE_HEADING_NEIGHBOR_LINES,
        )
        previous_locator_run = _count_twenty_f_contiguous_page_locator_lines(
            previous_lines,
            from_end=True,
        )
        next_locator_run = _count_twenty_f_contiguous_page_locator_lines(
            next_lines,
            from_end=False,
        )
        if previous_locator_run >= 2 and next_locator_run >= 1:
            return False
        return True

    if _TWENTY_F_HEADING_PREFIX_ENUM_RE.search(prefix) is not None:
        return True

    prefix_word_count = len(_TWENTY_F_HEADING_PREFIX_WORD_RE.findall(prefix))
    return prefix_word_count == 0

def _looks_like_toc_page_line(full_text: str, position: int) -> bool:
    """20-F 版目录页码行判断，委托共享实现。"""
    return _looks_like_toc_page_line_generic(
        full_text, position, _TOC_PAGE_LINE_PATTERN, _TOC_PAGE_SNIPPET_PATTERN
    )


def _build_item_title(item_token: str) -> str:
    """构建 20-F Item 完整标题。

    格式：``Part {roman} - Item {token} - {description}``

    Part 标签来自 SEC 法定映射，描述来自 SEC 标准条目名。
    20-F Item 编号全局唯一，Part 前缀为信息性（帮助 LLM 理解
    文档结构层级）。

    Args:
        item_token: Item 编号（如 ``"3"``、``"16A"``、``"18"``）。

    Returns:
        完整标题字符串。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    normalized_token = item_token.strip().upper()

    # SEC 法定 Part 标签
    roman = _TWENTY_F_ITEM_PART_MAP.get(normalized_token)
    part_prefix = f"Part {roman} - " if roman else ""

    # SEC 标准描述
    description = _TWENTY_F_ITEM_DESCRIPTIONS.get(normalized_token)
    desc_suffix = f" - {description}" if description else ""

    return f"{part_prefix}Item {normalized_token}{desc_suffix}"
