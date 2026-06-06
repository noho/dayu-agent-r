"""10-K 表单公共常量与 marker 构建逻辑。

本模块提取 10-K 相关的共享常量和 marker 函数，供
``TenKFormProcessor``（edgartools 路线）和
``BsTenKFormProcessor``（BeautifulSoup 路线）共同使用。

两侧处理器均从本模块 import，互不依赖，保持架构独立。
"""

from __future__ import annotations

import re
from typing import Optional

from dayu.documents.processors.text_utils import (
    PREVIEW_MAX_CHARS as _PREVIEW_MAX_CHARS,
    normalize_whitespace as _normalize_whitespace,
)

from .sec_form_section_common import (
    SIGNATURE_PATTERN as _SIGNATURE_PATTERN,
    _VirtualSection,
    _dedupe_markers,
    _find_marker_after,
)
from .sec_report_form_common import (
    _find_table_of_contents_cutoff,
    _looks_like_inline_toc_snippet,
    _looks_like_toc_page_line_generic,
    _select_ordered_item_markers_after_toc,
)

_TEN_K_ITEM_ORDER = (
    "1",
    "1A",
    "1B",
    "1C",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "7A",
    "8",
    "9",
    "9A",
    "9B",
    "9C",
    "10",
    "11",
    "12",
    "13",
    "14",
    "15",
)
# 10-K 常见法定 Item 标题关键词（用于识别"仅编号 + 标题"的 heading 形态）。
# 该规则基于 SEC Form 10-K Item 体系，不依赖公司特定写法。
_TEN_K_NUMBERED_HEADING_KEYWORDS = (
    "business",
    "risk factors",
    "cybersecurity",
    "properties",
    "legal proceedings",
    "mine safety",
    "market for",
    "management",
    "quantitative",
    "financial statements",
    "changes in and disagreements",
    "controls and procedures",
    "selected financial",
    "directors",
    "executive compensation",
    "security ownership",
    "certain relationships",
    "principal accountant",
    "exhibits",
)
# 真实 10-K 中 MD&A 标题常见弯引号/省略引号变体：
# ``Management's`` / ``Management’s`` / ``Managements``。
_APOSTROPHE_CHARS_PATTERN = "'’‘`´"
_MANAGEMENT_POSSESSIVE_PATTERN = (
    rf"management(?:\s*[{_APOSTROPHE_CHARS_PATTERN}]\s*)?s?"
)
# 兼容 "Item 1. ..." / "Item 1 — ..." / "Item 1 Business ..." 三类标题格式；
# 无标点格式要求下一字符为字母，避免命中封面勾选框等噪声 token。
_TEN_K_ITEM_PATTERN = re.compile(
    r"(?im)"
    r"(?:\bitem\s+(1A|1B|1C|7A|9A|9B|9C|1[0-5]|[1-9])"
    r"(?:\s*[\.\:\-\u2013\u2014]\s*|\s+(?=[A-Za-z])))"
    r"|(?:^|\n)\s*(1A|1B|1C|7A|9A|9B|9C|1[0-5]|[1-9])\s*"
    r"(?:[\.\:\-\u2013\u2014]\s*|\s+)"
    r"(?=(?:"
    + "|".join(re.escape(keyword) for keyword in _TEN_K_NUMBERED_HEADING_KEYWORDS)
    + r")\b)"
)
_TEN_K_PART_PATTERN = re.compile(r"(?i)part\s+(I{1,3}|IV)\b")
_TEN_K_HEADING_FALLBACK_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "1": (
        re.compile(r"(?im)^\s*Business\s*$"),
    ),
    "1A": (
        re.compile(r"(?im)^\s*Risk Factors\s*$"),
    ),
    "1C": (
        re.compile(r"(?im)^\s*Cybersecurity\s*$"),
    ),
    "7": (
        re.compile(
            rf"(?im)^\s*{_MANAGEMENT_POSSESSIVE_PATTERN}\s+Discussion and Analysis"
            r"(?: of Financial Condition and Results of Operations)?\s*$"
        ),
    ),
    "7A": (
        re.compile(r"(?im)^\s*Quantitative and Qualitative Disclosures About Market Risk\s*$"),
        re.compile(r"(?im)^\s*Quantitative and Qualitative Disclosures About Market Risks\s*$"),
        re.compile(r"(?im)^\s*Quantitative and Qualitative Disclosures About Risk\s*$"),
    ),
    "8": (
        re.compile(r"(?im)^\s*Financial Statements(?: and Supplementary Data)?\s*$"),
        re.compile(r"(?im)^\s*Consolidated Financial Statements(?: and Supplementary Data)?\s*$"),
    ),
}
_TEN_K_HEADING_FALLBACK_SEARCH_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "1": (
        re.compile(r"(?i)\bbusiness\b"),
    ),
    "1A": (
        re.compile(r"(?i)\brisk factors\b"),
    ),
    "1C": (
        re.compile(r"(?i)\bcybersecurity\b"),
    ),
    "7": (
        re.compile(
            rf"(?i)\b{_MANAGEMENT_POSSESSIVE_PATTERN}\s+discussion and analysis"
            r"(?: of financial condition and results of operations)?\b"
        ),
    ),
    "7A": (
        re.compile(r"(?i)\bquantitative and qualitative disclosures about market risk\b"),
        re.compile(r"(?i)\bquantitative and qualitative disclosures about market risks\b"),
        re.compile(r"(?i)\bquantitative and qualitative disclosures about risk\b"),
    ),
    "8": (
        re.compile(r"(?im)^\s*consolidated financial statements(?: and supplementary data)?\s*$"),
        re.compile(r"(?i)\bfinancial statements(?: and supplementary data)?\b"),
        re.compile(r"(?i)\bconsolidated financial statements(?: and supplementary data)?\b"),
    ),
}
_TEN_K_HEADING_FALLBACK_REQUIRED_ITEMS = ("1A", "7", "8")
# 尾部目录/索引检测阈值：若所有标记的总跨度占文档长度的比例低于此值，
# 判定为尾部 Item 索引（而非正文章节边界），触发标题兜底。
# 正常 10-K 正文标记跨度通常 > 80%；MCD 等嵌入式年报的尾部索引 < 2%。
_TRAILING_TOC_SPAN_RATIO = 0.05

# 标题兜底标记的最小章节跨度（chars）：连续两个标记间距低于此值时
# 判定为目录条目而非正文章节边界，触发跳过并向后搜索下一匹配。
_MIN_HEADING_SECTION_SPAN = 500

_TOC_PAGE_LINE_PATTERN = re.compile(r"(?im)^\s*[A-Za-z][^\n]{0,220}\b\d{1,3}\s*$")
_TOC_PAGE_SNIPPET_PATTERN = re.compile(
    r"(?is)^\s*(?:item\s+(?:1A|1B|1C|7A|9A|9B|9C|1[0-5]|[1-9])\s*[\.\:\-\u2013\u2014]?\s*)?"
    r"[A-Za-z][^\n]{0,220}\b\d{1,3}\b(?:\s+item\s+(?:1A|1B|1C|7A|9A|9B|9C|1[0-5]|[1-9])\b|\s*$)"
)
_ITEM_7_CROSS_REFERENCE_PATTERN = re.compile(
    r"(?is)\b(?:in|to|see)\s+(?:part\s+ii\s*,\s*)?item\s+7\b"
)
_TEN_K_HEADING_PREFIX_WORD_RE = re.compile(r"[A-Za-z]{2,}")
_TEN_K_HEADING_PREFIX_ENUM_RE = re.compile(
    r"(?i)(?:^|[\s(])(?:item\s+(?:1A|1B|1C|7A|9A|9B|9C|1[0-5]|[1-9])|part\s+(?:i{1,3}|iv)|[A-D])\s*[\.\-–—:)]?\s*$"
)
_TEN_K_VIRTUAL_SECTION_ITEM_RE = re.compile(r"(?i)\bitem\s+(1A|1B|1C|7A|9A|9B|9C|1[0-5]|[1-9])\b")
_TEN_K_BY_REFERENCE_STUB_RE = re.compile(
    r"(?is)\b(?:information\s+in\s+response\s+to\s+this\s+item\b.*?|that\s+information\b.*?)?"
    r"\bincorporat(?:ed|es)\b.*?\bby\s+reference\b"
)
_TEN_K_REFERENCE_HEADING_RE = re.compile(
    r"(?is)\bunder\s+(?:the\s+)?headings?\s+([\"“][^\"”]{3,160}[\"”](?:\s*(?:,|and)\s*[\"“][^\"”]{3,160}[\"”])*)"
)
_TEN_K_QUOTED_TEXT_RE = re.compile(r"[\"“]([^\"”]{3,160})[\"”]")
_TEN_K_HEADING_STUB_LINE_RE = re.compile(
    r"(?im)^\s*[A-Za-z][A-Za-z0-9 '&’,/\-]{3,120}\s*(?:\d{1,3}(?:\s*[—–-]\s*\d{1,3})?)?\s*$"
)
_TEN_K_PAGE_LOCATOR_STUB_LINE_RE = re.compile(
    r"(?im)^\s*(?:\d{1,3}(?:\s*[—–,\-]\s*\d{1,3})*|[—–,\-])\s*$"
)
_TEN_K_STUB_MAX_WORDS = 64
_TEN_K_STUB_MAX_BODY_WORDS = 24
_TEN_K_MIN_EXPANDED_WORDS = 80
_TEN_K_MIN_EXPANDED_GROWTH = 2.5
_TEN_K_FALLBACK_DIRECTIONAL_SEARCH_MAX = 12
_TEN_K_BY_REFERENCE_WINDOW_MAX_CHARS = 1600
_TEN_K_TOC_CONTEXT_LOOKAROUND_CHARS = 240
_TEN_K_TOC_CONTEXT_PROBE_LOOKAROUND_CHARS = 120
_TEN_K_TOC_CONTEXT_MIN_PAGE_REFS = 3
_TEN_K_TOC_PAGE_REFERENCE_RE = re.compile(
    r"(?<![\d,])\d{1,3}(?:\s*[–—-]\s*\d{1,3})?(?![\d,])"
)
_TEN_K_HEADING_BODY_LOOKAHEAD_CHARS = 520
_TEN_K_HEADING_BODY_WORD_WINDOW_CHARS = 360
_TEN_K_HEADING_BODY_MIN_WORDS = 24
_TEN_K_HEADING_BODY_SKIP_RE = re.compile(
    r"(?is)^\s*(?:table\s+of\s+contents|index\s+to\s+financial\s+statements|page|see\s+page)\b[\s:.-]*"
)
_TEN_K_HEADING_TRANSLATION_TABLE = str.maketrans(
    {
        "’": "'",
        "‘": "'",
        "`": "'",
        "´": "'",
        "“": '"',
        "”": '"',
        "—": "-",
        "–": "-",
        "\xa0": " ",
    }
)

# SEC 监管规则：10-K 表单 Item → Part 的法定映射
# 参考 SEC Regulation S-K (17 CFR Part 229)
# Part I: Items 1, 1A, 1B, 1C, 2 (Properties), 3 (Legal Proceedings), 4 (Mine Safety)
# Part II: Items 5–9C
# Part III: Items 10–14
# Part IV: Items 15–16
_TEN_K_ITEM_PART_MAP: dict[str, str] = {
    "1": "I", "1A": "I", "1B": "I", "1C": "I",
    "2": "I", "3": "I", "4": "I",
    "5": "II", "6": "II", "7": "II", "7A": "II", "8": "II",
    "9": "II", "9A": "II", "9B": "II", "9C": "II",
    "10": "III", "11": "III", "12": "III", "13": "III", "14": "III",
    "15": "IV", "16": "IV",
}

_TEN_K_BY_REFERENCE_DEFAULT_HEADINGS: dict[str, tuple[str, ...]] = {
    "1A": ("Risk Factors",),
    "7": (
        "Management's Discussion and Analysis",
        "Management’s Discussion and Analysis",
        "Financial Review",
        "Operating and Financial Review",
    ),
    "7A": (
        "Quantitative and Qualitative Disclosures About Market Risk",
        "Quantitative and Qualitative Disclosures About Market Risks",
        "Corporate Risk Profile",
        "Asset/Liability Management",
        "Risk Management",
    ),
    "8": (
        "Financial Statements and Supplementary Data",
        "Financial Statements",
        "Consolidated Financial Statements",
        "Notes to Financial Statements",
        "Notes to Consolidated Financial Statements",
        "Report of Management",
    ),
}
_TEN_K_ITEM_7_ALIAS_TITLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?im)^\s*overview\s*(?:and|&)\s*outlook\s*$"),
)


def _build_ten_k_markers(full_text: str) -> list[tuple[int, Optional[str]]]:
    """构建 10-K 的 Part + Item 边界。

    Args:
        full_text: 文档全文。

    Returns:
        标记列表；标记不足时返回空列表触发父类回退。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    item_markers = _select_ordered_item_markers_after_toc(
        full_text,
        item_pattern=_TEN_K_ITEM_PATTERN,
        ordered_tokens=_TEN_K_ITEM_ORDER,
        min_items_after_toc=4,
    )
    # 尾部目录/索引检测：若所有标记聚集在文档极小区间内（< 5%），
    # 说明命中了尾部 Item 索引而非正文章节边界。
    # 策略：优先尝试标题兜底（限定在索引区域前搜索）；
    # 若标题兜底成功（≥ 3 个关键 Item）则直接采用，跳过后续 repair
    # 和全局 heading fallback（后者不含 end_at 会污染正文标记）；
    # 若失败则保留原始 trailing markers 继续正常流程（C / GE / MS 场景）。
    _trailing_heading_used = False
    if len(item_markers) >= 2:
        marker_span = item_markers[-1][1] - item_markers[0][1]
        if marker_span < len(full_text) * _TRAILING_TOC_SPAN_RATIO:
            trailing_toc_start = item_markers[0][1]
            heading_markers = _select_ten_k_heading_fallback_markers(
                full_text, end_at=trailing_toc_start,
            )
            if len(heading_markers) >= 3:
                # 标题兜底成功，直接使用正文标题标记
                item_markers = heading_markers
                _trailing_heading_used = True
            # 否则保留原始 trailing markers，继续下方 repair 流程
    if not _trailing_heading_used:
        # 仅在非 trailing heading 路径执行 repair + 全局 fallback
        item_markers = _repair_ten_k_key_items_with_heading_fallback(full_text, item_markers)
        if len(item_markers) < 4:
            item_markers = _select_ten_k_heading_fallback_markers(full_text)
    if len(item_markers) < 3:
        return []

    part_markers = _build_part_markers(full_text)
    markers: list[tuple[int, Optional[str]]] = []
    for item_token, position in item_markers:
        part_title = _resolve_part_title(part_markers, position)
        # Step 8: 用 SEC 监管规则修正/补全 Part 标签
        part_title = _correct_part_from_sec_rules(item_token, part_title)
        if part_title is None:
            title = f"Item {item_token}"
        else:
            title = f"{part_title} - Item {item_token}"
        markers.append((position, title))

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


def expand_ten_k_virtual_sections_content(
    *,
    full_text: str,
    virtual_sections: list[_VirtualSection],
) -> None:
    """修正 10-K 虚拟章节中的目录 stub 与 by-reference stub。

    目标不是改变法定 Item 骨架，而是在保留章节顺序的前提下，
    用同一 filing 内更可信的正文片段替换 ``Item 1A/7/7A/8`` 的空壳内容。

    处理两类真实场景：
    1. 目录误切：章节正文仅包含标题与页码范围；
    2. incorporated-by-reference 包装句：法定 Item 仅给出“见 Annual Report 某标题”，
       真正正文位于同文档其它位置。

    Args:
        full_text: 用于切分的完整文本。
        virtual_sections: 已构建好的虚拟章节列表。

    Returns:
        无。

    Raises:
        RuntimeError: 修正失败时抛出。
    """

    if not full_text or not virtual_sections:
        return

    fallback_positions = _find_ten_k_heading_fallback_positions(full_text)
    section_by_token = _collect_ten_k_virtual_item_sections(virtual_sections)
    if not section_by_token:
        return

    replacement_starts: dict[str, int] = {}
    for token in ("1A", "7", "7A", "8"):
        section = section_by_token.get(token)
        if section is None:
            continue
        is_heading_stub = _looks_like_ten_k_heading_stub(section.content)
        replacement = _resolve_ten_k_virtual_section_replacement_start(
            full_text=full_text,
            token=token,
            section=section,
            fallback_positions=fallback_positions,
        )
        if replacement is None:
            if is_heading_stub:
                replacement_starts[token] = section.start
            continue
        replacement_starts[token] = replacement

    if not replacement_starts:
        _recover_missing_ten_k_item_7_from_alias_heading(
            full_text=full_text,
            virtual_sections=virtual_sections,
        )
        return

    ordered_sections = [
        (token, section_by_token[token])
        for token in ("1A", "7", "7A", "8")
        if token in section_by_token
    ]
    boundary_starts = _collect_ten_k_replacement_boundary_starts(
        ordered_sections=ordered_sections,
        replacement_starts=replacement_starts,
    )
    for index, (token, section) in enumerate(ordered_sections):
        replacement_start = replacement_starts.get(token)
        if replacement_start is None:
            continue
        replacement_end = _resolve_ten_k_virtual_section_replacement_end(
            token=token,
            replacement_start=replacement_start,
            ordered_sections=ordered_sections,
            ordered_index=index,
            replacement_starts=replacement_starts,
            boundary_starts=boundary_starts,
        )
        if replacement_end is None or replacement_end <= replacement_start:
            continue
        replacement_content = full_text[replacement_start:replacement_end].strip()
        if not _should_apply_ten_k_virtual_section_replacement(
            current_content=section.content,
            replacement_content=replacement_content,
        ):
            continue
        section.content = replacement_content
        section.preview = _normalize_whitespace(replacement_content)[:_PREVIEW_MAX_CHARS]
        section.start = replacement_start
        section.end = replacement_end

    _recover_missing_ten_k_item_7_from_alias_heading(
        full_text=full_text,
        virtual_sections=virtual_sections,
    )


def _collect_ten_k_virtual_item_sections(
    virtual_sections: list[_VirtualSection],
) -> dict[str, _VirtualSection]:
    """提取 10-K 关键 Item 对应的顶层虚拟章节。

    Args:
        virtual_sections: 虚拟章节列表。

    Returns:
        ``item_token -> _VirtualSection`` 映射。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    mapping: dict[str, _VirtualSection] = {}
    for section in virtual_sections:
        if section.level != 1:
            continue
        title = str(section.title or "")
        match = _TEN_K_VIRTUAL_SECTION_ITEM_RE.search(title)
        if match is None:
            continue
        token = str(match.group(1) or "").upper()
        if token:
            mapping[token] = section
    return mapping


def _collect_ten_k_top_level_sections(
    virtual_sections: list[_VirtualSection],
) -> list[_VirtualSection]:
    """返回按起点排序的顶层虚拟章节。"""

    return sorted(
        (section for section in virtual_sections if section.level == 1),
        key=lambda section: (section.start, section.ref),
    )


def _recover_missing_ten_k_item_7_from_alias_heading(
    *,
    full_text: str,
    virtual_sections: list[_VirtualSection],
) -> None:
    """从结构化别名子标题中恢复缺失的 Item 7。

    少数 10-K 会在 Item 6 之后直接进入 MD&A 正文，
    仅保留 ``Overview and Outlook`` 这类子标题，而不再重复
    ``Item 7`` 法定标题，导致大段正文被上一节吞并。

    该修复仅在以下条件同时满足时触发：
    - 顶层缺失 Item 7；
    - 后续已经存在 Item 7A / 8 等 Part II 关键边界；
    - 上一顶层章节内部存在 MD&A 结构化子标题别名；
    - 该别名到下一个边界之间具有足够正文长度。

    Args:
        full_text: 文档全文。
        virtual_sections: 虚拟章节列表。

    Returns:
        无。

    Raises:
        RuntimeError: 恢复失败时抛出。
    """

    if not full_text or not virtual_sections:
        return

    section_by_token = _collect_ten_k_virtual_item_sections(virtual_sections)
    if "7" in section_by_token:
        return

    top_level_sections = _collect_ten_k_top_level_sections(virtual_sections)
    if not top_level_sections:
        return

    boundary_section = _find_ten_k_item_7_boundary_section(top_level_sections)
    if boundary_section is None:
        return

    previous_section = _find_ten_k_previous_top_level_section(
        top_level_sections=top_level_sections,
        boundary_start=boundary_section.start,
    )
    if previous_section is None:
        return

    alias_section = _find_ten_k_item_7_alias_child_section(
        virtual_sections=virtual_sections,
        parent_section=previous_section,
        boundary_start=boundary_section.start,
    )
    if alias_section is None:
        return

    recovered_content = full_text[alias_section.start:boundary_section.start].strip()
    if len(recovered_content.split()) < _TEN_K_MIN_EXPANDED_WORDS:
        return

    _trim_ten_k_section_to_boundary(
        section=previous_section,
        full_text=full_text,
        new_end=alias_section.start,
    )
    recovered_ref = _allocate_ten_k_recovered_section_ref(
        virtual_sections=virtual_sections,
        base_ref="s_recovered_item7",
    )
    recovered_section = _VirtualSection(
        ref=recovered_ref,
        title="Part II - Item 7",
        content=recovered_content,
        preview=_normalize_whitespace(recovered_content)[:_PREVIEW_MAX_CHARS],
        table_refs=[],
        level=1,
        parent_ref=None,
        child_refs=[],
        start=alias_section.start,
        end=boundary_section.start,
    )
    _reparent_ten_k_child_sections(
        virtual_sections=virtual_sections,
        previous_section=previous_section,
        recovered_section=recovered_section,
    )
    virtual_sections.append(recovered_section)
    virtual_sections.sort(key=lambda section: (section.start, section.level, section.ref))


def _find_ten_k_item_7_boundary_section(
    top_level_sections: list[_VirtualSection],
) -> Optional[_VirtualSection]:
    """定位缺失 Item 7 时可用的下一个 Part II 边界。"""

    for section in top_level_sections:
        title = str(section.title or "")
        match = _TEN_K_VIRTUAL_SECTION_ITEM_RE.search(title)
        if match is None:
            continue
        token = str(match.group(1) or "").upper()
        if token in {"7A", "8", "9", "9A", "9B", "9C", "10", "15"}:
            return section
    return None


def _find_ten_k_previous_top_level_section(
    *,
    top_level_sections: list[_VirtualSection],
    boundary_start: int,
) -> Optional[_VirtualSection]:
    """返回边界前最近的顶层章节。"""

    previous: Optional[_VirtualSection] = None
    for section in top_level_sections:
        if section.start >= boundary_start:
            break
        previous = section
    return previous


def _find_ten_k_item_7_alias_child_section(
    *,
    virtual_sections: list[_VirtualSection],
    parent_section: _VirtualSection,
    boundary_start: int,
) -> Optional[_VirtualSection]:
    """在被吞并的大节内寻找 Item 7 的别名子标题。"""

    candidates: list[_VirtualSection] = []
    for section in virtual_sections:
        if section.level != 2:
            continue
        if section.start <= parent_section.start or section.start >= boundary_start:
            continue
        title = str(section.title or "")
        if any(pattern.search(title) is not None for pattern in _TEN_K_ITEM_7_ALIAS_TITLE_PATTERNS):
            candidates.append(section)
    if not candidates:
        return None
    candidates.sort(key=lambda section: (section.start, section.ref))
    return candidates[0]


def _trim_ten_k_section_to_boundary(
    *,
    section: _VirtualSection,
    full_text: str,
    new_end: int,
) -> None:
    """将被吞并的上一顶层章节截断到新边界。"""

    if new_end <= section.start:
        return
    trimmed_content = full_text[section.start:new_end].strip()
    section.content = trimmed_content
    section.preview = _normalize_whitespace(trimmed_content)[:_PREVIEW_MAX_CHARS]
    section.end = new_end


def _allocate_ten_k_recovered_section_ref(
    *,
    virtual_sections: list[_VirtualSection],
    base_ref: str,
) -> str:
    """为恢复出的顶层章节分配唯一 ref。"""

    existing_refs = {section.ref for section in virtual_sections}
    if base_ref not in existing_refs:
        return base_ref
    index = 1
    while True:
        candidate = f"{base_ref}_{index:02d}"
        if candidate not in existing_refs:
            return candidate
        index += 1


def _reparent_ten_k_child_sections(
    *,
    virtual_sections: list[_VirtualSection],
    previous_section: _VirtualSection,
    recovered_section: _VirtualSection,
) -> None:
    """把落入恢复区间内的子章节迁移到新建的 Item 7 下。"""

    moved_child_refs: list[str] = []
    retained_child_refs: list[str] = []
    for child_ref in previous_section.child_refs:
        child = next((section for section in virtual_sections if section.ref == child_ref), None)
        if child is None:
            retained_child_refs.append(child_ref)
            continue
        if recovered_section.start <= child.start < recovered_section.end:
            child.parent_ref = recovered_section.ref
            moved_child_refs.append(child.ref)
            continue
        retained_child_refs.append(child_ref)
    previous_section.child_refs = retained_child_refs
    recovered_section.child_refs = moved_child_refs


def _resolve_ten_k_virtual_section_replacement_start(
    *,
    full_text: str,
    token: str,
    section: _VirtualSection,
    fallback_positions: dict[str, int],
) -> Optional[int]:
    """为 stub 章节选择替代正文起点。

    Args:
        full_text: 文档全文。
        token: Item token。
        section: 当前虚拟章节。
        fallback_positions: 标题 fallback 命中位置映射。

    Returns:
        替代正文起点；无更优候选时返回 ``None``。

    Raises:
        RuntimeError: 选择失败时抛出。
    """

    fallback_start = fallback_positions.get(token)
    if fallback_start is None or fallback_start <= section.start:
        later_fallback_start = _find_ten_k_later_default_heading_position(
            full_text=full_text,
            token=token,
            after_position=section.end,
        )
        if later_fallback_start is not None:
            fallback_start = later_fallback_start
    if _looks_like_ten_k_by_reference_stub(section.content):
        reference_start = _find_ten_k_by_reference_target_start(
            full_text=full_text,
            token=token,
            section=section,
        )
        selected_reference_start = _select_ten_k_by_reference_replacement_start(
            section_start=section.start,
            reference_start=reference_start,
            fallback_start=fallback_start,
        )
        if selected_reference_start is not None:
            return selected_reference_start

    if _looks_like_ten_k_heading_stub(section.content):
        if fallback_start is None:
            fallback_start = _find_ten_k_default_heading_position(
                full_text=full_text,
                token=token,
            )
        if fallback_start is not None and fallback_start != section.start:
            return fallback_start
    return None


def _select_ten_k_by_reference_replacement_start(
    *,
    section_start: int,
    reference_start: Optional[int],
    fallback_start: Optional[int],
) -> Optional[int]:
    """在 by-reference 候选中选择更稳妥的正文起点。

    真实 10-K 中常见两类候选：
    1. 前文较早位置的同名泛标题（如 ``Risk Management``），容易借错正文；
    2. 当前法定 Item 之后的真实 Annual Report/Financial Section 正文。

    当 fallback 已经识别到“更靠后且更像正文”的位置时，应优先它，
    避免把 Item 7/7A 错借到文档前部的业务/风险段落。

    Args:
        section_start: 当前虚拟章节起点。
        reference_start: by-reference 标题检索出的候选起点。
        fallback_start: 标题 fallback 检索出的候选起点。

    Returns:
        最终采用的正文起点；无合适候选时返回 ``None``。

    Raises:
        RuntimeError: 选择失败时抛出。
    """

    if fallback_start is not None and fallback_start > section_start:
        if reference_start is None:
            return fallback_start
        if reference_start <= section_start:
            return fallback_start
    return reference_start


def _resolve_ten_k_virtual_section_replacement_end(
    *,
    token: str,
    replacement_start: int,
    ordered_sections: list[tuple[str, _VirtualSection]],
    ordered_index: int,
    replacement_starts: dict[str, int],
    boundary_starts: list[int],
) -> Optional[int]:
    """为替代正文起点选择合理的结束位置。

    优先使用后续关键 Item 的替代起点，其次回退到当前法定 Item 的原始起点，
    以便在不改变章节顺序的前提下借用同文档其它位置的正文。

    Args:
        token: 当前 Item token。
        replacement_start: 替代正文起点。
        ordered_sections: 关键 Item 章节列表。
        ordered_index: 当前章节在列表中的位置。
        replacement_starts: 已计算的替代起点映射。
        boundary_starts: 可作为章节边界的正文起点列表。

    Returns:
        结束位置；无法确定时返回 ``None``。

    Raises:
        RuntimeError: 选择失败时抛出。
    """

    del token

    current_section = ordered_sections[ordered_index][1]
    if current_section.start > replacement_start:
        next_boundary = next(
            (start for start in boundary_starts if start > replacement_start),
            None,
        )
        if next_boundary is not None:
            return next_boundary
        return current_section.start

    candidates: list[int] = []
    for later_token, later_section in ordered_sections[ordered_index + 1 :]:
        later_start = replacement_starts.get(later_token, later_section.start)
        if later_start > replacement_start:
            candidates.append(later_start)
            break

    if not candidates:
        return None
    return min(candidates)


def _collect_ten_k_replacement_boundary_starts(
    *,
    ordered_sections: list[tuple[str, _VirtualSection]],
    replacement_starts: dict[str, int],
) -> list[int]:
    """收集可作为扩正文边界的真实正文起点。

    Args:
        ordered_sections: 关键 Item 章节列表。
        replacement_starts: 已解析出的替代正文起点。

    Returns:
        升序正文边界列表。

    Raises:
        RuntimeError: 计算失败时抛出。
    """

    boundaries: set[int] = set()
    for token, section in ordered_sections:
        replacement_start = replacement_starts.get(token)
        if replacement_start is not None:
            boundaries.add(replacement_start)
            continue
        if _looks_like_ten_k_heading_stub(section.content):
            continue
        if _looks_like_ten_k_by_reference_stub(section.content):
            continue
        leading_sample = _normalize_whitespace(str(section.content or ""))[:140]
        if leading_sample[:1].islower():
            continue
        boundaries.add(section.start)
    return sorted(boundaries)


def _should_apply_ten_k_virtual_section_replacement(
    *,
    current_content: str,
    replacement_content: str,
) -> bool:
    """判断是否应采用替代正文。

    Args:
        current_content: 当前章节正文。
        replacement_content: 候选替代正文。

    Returns:
        候选正文显著优于当前 stub 时返回 ``True``。

    Raises:
        RuntimeError: 判定失败时抛出。
    """

    current_words = len(str(current_content or "").split())
    replacement_words = len(str(replacement_content or "").split())
    if replacement_words < _TEN_K_MIN_EXPANDED_WORDS:
        return False
    if current_words <= 0:
        return True
    return replacement_words >= max(
        int(current_words * _TEN_K_MIN_EXPANDED_GROWTH),
        current_words + _TEN_K_MIN_EXPANDED_WORDS,
    )


def _looks_like_ten_k_by_reference_stub(content: str) -> bool:
    """判断章节正文是否为 by-reference 包装句。

    Args:
        content: 当前章节正文。

    Returns:
        若正文更像“见 Annual Report 某标题”的包装句则返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    stub_window = _extract_ten_k_by_reference_stub_window(content)
    if not stub_window:
        return False
    if len(stub_window.split()) > (_TEN_K_STUB_MAX_WORDS * 4):
        return False
    if _TEN_K_BY_REFERENCE_STUB_RE.search(stub_window) is None:
        return False
    return re.search(
        r"(?is)\b(?:annual\s+report|under\s+the\s+head(?:ing|ings)|can\s+be\s+found|that\s+information)\b",
        stub_window,
    ) is not None


def _looks_like_ten_k_heading_stub(content: str) -> bool:
    """判断章节正文是否仅包含标题/页码等无正文 stub。

    Args:
        content: 当前章节正文。

    Returns:
        更像目录标题或页码残留时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized = str(content or "").strip()
    if not normalized:
        return False
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    if not lines or len(lines) > 8:
        return False
    if len(normalized.split()) > _TEN_K_STUB_MAX_WORDS:
        return False
    body_word_count = sum(len(line.split()) for line in lines)
    if body_word_count > _TEN_K_STUB_MAX_BODY_WORDS:
        return False
    return all(
        _TEN_K_HEADING_STUB_LINE_RE.match(line) is not None
        or _TEN_K_PAGE_LOCATOR_STUB_LINE_RE.match(line) is not None
        for line in lines
    )


def _extract_ten_k_by_reference_stub_window(content: str) -> str:
    """抽取章节开头的 by-reference 包装句窗口。

    Args:
        content: 当前章节正文。

    Returns:
        仅包含章节开头包装句的文本窗口。

    Raises:
        RuntimeError: 抽取失败时抛出。
    """

    normalized = str(content or "").strip()
    if not normalized:
        return ""
    stub_window = normalized[:_TEN_K_BY_REFERENCE_WINDOW_MAX_CHARS]
    next_item_heading = re.search(
        r"(?im)^\s*item\s+(?:1A|1B|1C|7A|9A|9B|9C|1[0-5]|[1-9])\b",
        stub_window[40:],
    )
    if next_item_heading is None:
        return stub_window
    boundary = 40 + next_item_heading.start()
    return stub_window[:boundary].strip()


def _find_ten_k_by_reference_target_start(
    *,
    full_text: str,
    token: str,
    section: _VirtualSection,
) -> Optional[int]:
    """根据包装句引用的标题在同文档内寻找被引用正文起点。

    Args:
        full_text: 文档全文。
        token: Item token。
        section: 当前虚拟章节。

    Returns:
        被引用正文的起点；未找到时返回 ``None``。

    Raises:
        RuntimeError: 查找失败时抛出。
    """

    heading_candidates = _extract_ten_k_by_reference_heading_candidates(
        token=token,
        content=section.content,
    )
    if not heading_candidates:
        return None

    preferred_before: list[int] = []
    preferred_after: list[int] = []
    for heading in heading_candidates:
        positions = _find_ten_k_heading_positions_by_phrase(
            full_text=full_text,
            heading=heading,
        )
        for position in positions:
            if section.start <= position < section.end:
                continue
            if position < section.start:
                preferred_before.append(position)
            else:
                preferred_after.append(position)

    if preferred_before:
        return max(preferred_before)
    if preferred_after:
        return min(preferred_after)

    for heading in heading_candidates:
        relaxed_position = _find_ten_k_relaxed_reference_position(
            full_text=full_text,
            heading=heading,
            section_start=section.start,
            section_end=section.end,
            prefer_after=(token == "8"),
        )
        if relaxed_position is not None:
            return relaxed_position
    return None


def _extract_ten_k_by_reference_heading_candidates(
    *,
    token: str,
    content: str,
) -> list[str]:
    """从 by-reference 包装句中提取被引用标题候选。

    Args:
        token: Item token。
        content: 当前章节正文。

    Returns:
        去重保序的标题候选列表。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    candidates: list[str] = []
    normalized = _extract_ten_k_by_reference_stub_window(content)

    match = _TEN_K_REFERENCE_HEADING_RE.search(normalized)
    if match is not None:
        for quoted in _TEN_K_QUOTED_TEXT_RE.findall(str(match.group(1) or "")):
            _append_ten_k_reference_heading_candidate(candidates, quoted)

    for quoted in _TEN_K_QUOTED_TEXT_RE.findall(normalized):
        _append_ten_k_reference_heading_candidate(candidates, quoted)

    for default_heading in _TEN_K_BY_REFERENCE_DEFAULT_HEADINGS.get(token, ()):
        _append_ten_k_reference_heading_candidate(candidates, default_heading)
    return candidates


def _append_ten_k_reference_heading_candidate(
    candidates: list[str],
    heading: str,
) -> None:
    """追加去重后的引用标题候选。

    Args:
        candidates: 候选列表。
        heading: 待追加标题。

    Returns:
        无。

    Raises:
        RuntimeError: 追加失败时抛出。
    """

    cleaned = str(heading or "").strip().strip(".,;: ")
    if len(cleaned) < 3:
        return
    if cleaned not in candidates:
        candidates.append(cleaned)


def _find_ten_k_heading_positions_by_phrase(
    *,
    full_text: str,
    heading: str,
) -> list[int]:
    """在全文中查找指定标题短语的独立标题位置。

    Args:
        full_text: 文档全文。
        heading: 标题短语。

    Returns:
        命中位置列表（按文档顺序）。

    Raises:
        RuntimeError: 查找失败时抛出。
    """

    normalized_text = _normalize_ten_k_heading_search_text(full_text)
    normalized_heading = _normalize_ten_k_heading_search_text(heading)
    if not normalized_heading:
        return []

    positions: list[int] = []
    cursor = 0
    search_count = 0
    while search_count < _TEN_K_FALLBACK_DIRECTIONAL_SEARCH_MAX:
        position = normalized_text.find(normalized_heading, cursor)
        if position < 0:
            break
        matched_text = full_text[position : position + len(heading)]
        if _looks_like_ten_k_standalone_heading_context(
            full_text=full_text,
            position=position,
            matched_text=matched_text,
        ):
            positions.append(position)
        cursor = position + 1
        search_count += 1
    return positions


def _find_ten_k_default_heading_position(
    *,
    full_text: str,
    token: str,
) -> Optional[int]:
    """根据 token 默认标题候选定位正文起点。

    Args:
        full_text: 文档全文。
        token: Item token。

    Returns:
        命中位置；未命中返回 ``None``。

    Raises:
        RuntimeError: 查找失败时抛出。
    """

    for heading in _TEN_K_BY_REFERENCE_DEFAULT_HEADINGS.get(token, ()):
        positions = _find_ten_k_heading_positions_by_phrase(
            full_text=full_text,
            heading=heading,
        )
        if positions:
            return positions[0]
    if token == "8":
        for heading in _TEN_K_BY_REFERENCE_DEFAULT_HEADINGS.get(token, ()):
            fallback_position = _find_ten_k_relaxed_reference_position(
                full_text=full_text,
                heading=heading,
                section_start=len(full_text),
                section_end=len(full_text),
            )
            if fallback_position is not None:
                return fallback_position
    return None


def _find_ten_k_later_default_heading_position(
    *,
    full_text: str,
    token: str,
    after_position: int,
) -> Optional[int]:
    """查找指定位置之后的默认标题候选。

    该函数用于 by-reference 修复场景：当前法定 Item 的标题本身往往也会命中
    默认 heading phrase，需要显式跳过当前 stub，继续寻找后续真实正文标题。

    Args:
        full_text: 文档全文。
        token: Item token。
        after_position: 仅接受大于该位置的候选。

    Returns:
        后续真实标题起点；未找到时返回 ``None``。

    Raises:
        RuntimeError: 查找失败时抛出。
    """

    for heading in _TEN_K_BY_REFERENCE_DEFAULT_HEADINGS.get(token, ()):
        positions = _find_ten_k_heading_positions_by_phrase(
            full_text=full_text,
            heading=heading,
        )
        later_positions = [position for position in positions if position > after_position]
        if later_positions:
            return min(later_positions)
    return None


def _find_ten_k_relaxed_reference_position(
    *,
    full_text: str,
    heading: str,
    section_start: int,
    section_end: int,
    prefer_after: bool = False,
) -> Optional[int]:
    """宽松回溯同名引用位置，覆盖独立标题结构丢失的 by-reference 文档。

    Args:
        full_text: 文档全文。
        heading: 目标标题。
        section_start: 当前章节起点。
        section_end: 当前章节终点。
        prefer_after: 是否优先选择章节之后的同名位置。

    Returns:
        更早的同名位置；若不存在则返回 ``None``。

    Raises:
        RuntimeError: 查找失败时抛出。
    """

    normalized_text = _normalize_ten_k_heading_search_text(full_text)
    normalized_heading = _normalize_ten_k_heading_search_text(heading)
    if not normalized_heading:
        return None

    previous_positions: list[int] = []
    later_positions: list[int] = []
    cursor = 0
    while True:
        position = normalized_text.find(normalized_heading, cursor)
        if position < 0:
            break
        matched_text = full_text[position : position + len(heading)]
        if _looks_like_ten_k_toc_heading_context(
            full_text=full_text,
            position=position,
            matched_text=matched_text,
        ):
            cursor = position + 1
            continue
        if position < section_start - 1200:
            previous_positions.append(position)
        elif position >= section_end + 1200:
            later_positions.append(position)
        cursor = position + 1
        if len(previous_positions) + len(later_positions) >= _TEN_K_FALLBACK_DIRECTIONAL_SEARCH_MAX:
            break
    if prefer_after and later_positions:
        return min(later_positions)
    if previous_positions:
        return max(previous_positions)
    if later_positions:
        return min(later_positions)
    return None


def _normalize_ten_k_heading_search_text(text: str) -> str:
    """规范化标题搜索文本。

    Args:
        text: 原始文本。

    Returns:
        适合做一对一位置映射搜索的规范化文本。

    Raises:
        RuntimeError: 规范化失败时抛出。
    """

    return str(text or "").translate(_TEN_K_HEADING_TRANSLATION_TABLE).lower()


def _select_ten_k_heading_fallback_markers(
    full_text: str,
    *,
    end_at: Optional[int] = None,
) -> list[tuple[str, int]]:
    """在 Item 前缀缺失时，按 SEC 法定标题兜底识别关键章节。

    场景：部分 iXBRL 10-K 正文使用 ``"Risk Factors"``、``"Management's Discussion..."``
    等纯标题，不包含 ``"Item 1A/7/8"`` 前缀，导致常规 Item 正则无法命中。

    该函数基于 SEC 法定标题集合进行自适应识别，并强制要求关键 Item
    ``1A/7/8`` 同时命中，避免误判。

    Args:
        full_text: 文档全文。
        end_at: 可选终止位置（不含），用于排除尾部 Item 索引区域。

    Returns:
        ``(item_token, start_index)`` 列表；未满足关键 Item 要求时返回空列表。

    Raises:
        RuntimeError: 识别失败时抛出。
    """

    start_at = max(0, _find_table_of_contents_cutoff(full_text))
    search_end = end_at  # 尾部 Item 索引截止位置，None 表示搜索到文末
    cursor = start_at
    selected: list[tuple[str, int]] = []
    for item_token in _TEN_K_ITEM_ORDER:
        patterns = _TEN_K_HEADING_FALLBACK_PATTERNS.get(item_token)
        if not patterns:
            continue
        position = _find_first_pattern_position_after(
            full_text=full_text,
            patterns=patterns,
            start_at=cursor,
            end_at=search_end,
        )
        if position is None:
            continue
        selected.append((item_token, position))
        cursor = position + 1

    # 第二轮：对缺失的必需 Item 做回溯搜索。
    # 场景：MCD 等嵌入式年报的 MD&A（Item 7）出现在 Risk Factors（Item 1A）之前，
    # 顺序游标会跳过，此处从 start_at 到首个已匹配位置的区间内回溯搜索。
    selected_tokens = {token for token, _ in selected}
    missing_required = [
        item for item in _TEN_K_HEADING_FALLBACK_REQUIRED_ITEMS
        if item not in selected_tokens
    ]
    if missing_required and selected:
        earliest_found_pos = min(pos for _, pos in selected)
        for item_token in missing_required:
            patterns = _TEN_K_HEADING_FALLBACK_PATTERNS.get(item_token)
            if not patterns:
                continue
            # 在已匹配区间之前搜索（从 start_at 到 earliest_found_pos）
            position = _find_first_pattern_position_after(
                full_text=full_text,
                patterns=patterns,
                start_at=start_at,
                end_at=earliest_found_pos,
            )
            if position is not None:
                selected.append((item_token, position))
                selected_tokens.add(item_token)

    selected_tokens = {token for token, _ in selected}
    if any(required not in selected_tokens for required in _TEN_K_HEADING_FALLBACK_REQUIRED_ITEMS):
        return []
    # 按文档位置排序输出
    selected.sort(key=lambda x: x[1])
    # 第三轮：目录条目跳过。
    # 连续标记间距过小说明命中了目录区域（如 MCD ToC 中
    # "Risk Factors\n28\nCybersecurity\n35" 连续出现），
    # 对聚簇标记逐个向后搜索下一匹配替换。
    selected = _skip_heading_toc_cluster(
        full_text, selected, start_at=start_at, end_at=search_end,
    )
    # 跳过后重新校验必需项
    selected_tokens = {token for token, _ in selected}
    if any(required not in selected_tokens for required in _TEN_K_HEADING_FALLBACK_REQUIRED_ITEMS):
        return []
    return selected


def _skip_heading_toc_cluster(
    full_text: str,
    markers: list[tuple[str, int]],
    *,
    start_at: int,
    end_at: Optional[int],
) -> list[tuple[str, int]]:
    """跳过标题兜底结果中的目录聚簇条目。

    场景：MCD 等嵌入式年报的前部区域包含简要目录，其中 ``Risk Factors``、
    ``Cybersecurity`` 等标题各占一行，与正文标题结构相同，导致标题兜底
    的首次命中落在目录区域（如 1.8%）而非正文区域（如 35%）。

    检测规则：若连续两个标记间距 < ``_MIN_HEADING_SECTION_SPAN``，
    判定前者为目录条目，替换为该模式在文档中的下一个匹配。

    Args:
        full_text: 文档全文。
        markers: 已排序的 ``(item_token, position)`` 列表。
        start_at: 标题搜索起始位置。
        end_at: 标题搜索终止位置（不含）。

    Returns:
        修正后的 ``(item_token, position)`` 列表。

    Raises:
        RuntimeError: 处理失败时抛出。
    """

    if len(markers) < 2:
        return markers

    result: list[tuple[str, int]] = list(markers)
    changed = True
    max_iterations = 5  # 防止无限循环
    iteration = 0
    while changed and iteration < max_iterations:
        changed = False
        iteration += 1
        for i in range(len(result) - 1):
            gap = result[i + 1][1] - result[i][1]
            if gap < _MIN_HEADING_SECTION_SPAN:
                # 当前标记疑似目录条目，搜索下一匹配
                item_token = result[i][0]
                patterns = _TEN_K_HEADING_FALLBACK_PATTERNS.get(item_token)
                if not patterns:
                    continue
                # 从当前位置之后搜索下一匹配
                next_pos = _find_first_pattern_position_after(
                    full_text=full_text,
                    patterns=patterns,
                    start_at=result[i][1] + 1,
                    end_at=end_at,
                )
                if next_pos is not None and next_pos != result[i][1]:
                    result[i] = (item_token, next_pos)
                    result.sort(key=lambda x: x[1])
                    changed = True
                    break  # 重新开始检查
    return result


def _repair_ten_k_key_items_with_heading_fallback(
    full_text: str,
    item_markers: list[tuple[str, int]],
) -> list[tuple[str, int]]:
    """用法定标题兜底修复 10-K 关键 Item 的缺失/目录污染。

    修复策略：
    - 若关键 Item（1A/7/8）缺失，且标题兜底能定位到正文，则补齐；
    - 若关键 Item 命中位置看起来像目录行（标题+页码），则用正文标题位置替换。

    Args:
        full_text: 文档全文。
        item_markers: 原始 ``(item_token, start_index)`` 列表。

    Returns:
        修复后的 ``(item_token, start_index)`` 列表（按法定顺序输出）。

    Raises:
        RuntimeError: 修复失败时抛出。
    """

    if not item_markers:
        return item_markers

    fallback_map = _find_ten_k_heading_fallback_positions(full_text)
    if not fallback_map:
        return item_markers
    marker_map = {token: position for token, position in item_markers}

    for token in _TEN_K_HEADING_FALLBACK_REQUIRED_ITEMS:
        fallback_pos = fallback_map.get(token)
        if fallback_pos is None:
            continue

        current_pos = marker_map.get(token)
        if current_pos is None:
            marker_map[token] = fallback_pos
            continue

        if (
            _looks_like_toc_page_line(full_text, current_pos)
            or _looks_like_inline_toc_snippet(full_text, current_pos)
            or (token == "7" and _looks_like_item_7_cross_reference(full_text, current_pos))
        ) and fallback_pos > current_pos:
            marker_map[token] = fallback_pos

    repaired: list[tuple[str, int]] = []
    for token in _TEN_K_ITEM_ORDER:
        position = marker_map.get(token)
        if position is None:
            continue
        repaired.append((token, position))
    return repaired


def _find_ten_k_heading_fallback_positions(full_text: str) -> dict[str, int]:
    """查找 10-K 关键标题在正文中的首个位置映射。

    与 ``_select_ten_k_heading_fallback_markers`` 的区别：
    - 本函数用于"局部修复"，不要求 1A/7/8 同时命中；
    - 仅返回实际命中的 token→position 映射。

    Args:
        full_text: 文档全文。

    Returns:
        命中的 token→position 映射。

    Raises:
        RuntimeError: 查找失败时抛出。
    """

    start_at = max(0, _find_table_of_contents_cutoff(full_text))
    positions: dict[str, int] = {}
    for token, patterns in _TEN_K_HEADING_FALLBACK_SEARCH_PATTERNS.items():
        best_position: Optional[int] = None
        for pattern in patterns:
            for match in pattern.finditer(full_text, pos=start_at):
                position = int(match.start())
                matched_text = str(match.group(0) or "")
                if _looks_like_toc_page_line(full_text, position):
                    continue
                if _looks_like_inline_toc_snippet(full_text, position):
                    continue
                if not _looks_like_ten_k_standalone_heading_context(
                    full_text=full_text,
                    position=position,
                    matched_text=matched_text,
                ):
                    continue
                best_position = position
                break
            if best_position is not None:
                break
        if best_position is not None:
            positions[token] = best_position
    return positions


def _looks_like_ten_k_standalone_heading_context(
    *,
    full_text: str,
    position: int,
    matched_text: str,
) -> bool:
    """判断 10-K fallback phrase 是否位于独立标题语境。

    Args:
        full_text: 文档全文。
        position: 命中起点。
        matched_text: 当前命中的原始文本。

    Returns:
        更像独立标题时返回 ``True``，正文句内引用返回 ``False``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized_match = str(matched_text or "")
    if _looks_like_ten_k_toc_heading_context(
        full_text=full_text,
        position=position,
        matched_text=normalized_match,
    ):
        return False
    if re.search(r"(?i)\bitem\s+(?:1A|1B|1C|7A|9A|9B|9C|1[0-5]|[1-9])\b", normalized_match) is not None:
        return True

    line_start = full_text.rfind("\n", 0, max(0, int(position))) + 1
    prefix = full_text[line_start:max(0, int(position))]
    if not prefix.strip():
        return True
    if _TEN_K_HEADING_PREFIX_ENUM_RE.search(prefix) is not None:
        return True
    if prefix.rstrip().endswith((".", ":", ";")) and _looks_like_ten_k_heading_text(normalized_match):
        return True

    prefix_word_count = len(_TEN_K_HEADING_PREFIX_WORD_RE.findall(prefix))
    return prefix_word_count <= 3


def _looks_like_ten_k_heading_text(matched_text: str) -> bool:
    """判断命中文本是否更像章节标题而非正文短语。

    Args:
        matched_text: 命中的原始文本。

    Returns:
        更像章节标题时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    words = re.findall(r"[A-Za-z]{2,}", str(matched_text or ""))
    if len(words) < 3:
        return False
    uppercase_words = sum(1 for word in words if word.isupper())
    titlecase_words = sum(1 for word in words if word[:1].isupper())
    return (uppercase_words + titlecase_words) >= max(3, len(words) - 1)


def _looks_like_ten_k_toc_heading_context(
    *,
    full_text: str,
    position: int,
    matched_text: str,
) -> bool:
    """判断命中位置是否更像目录/索引中的标题簇。

    Args:
        full_text: 文档全文。
        position: 命中起点。
        matched_text: 命中的原始文本。

    Returns:
        若上下文更像目录页码簇则返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    if not _may_be_ten_k_toc_heading_context(
        full_text=full_text,
        position=position,
        matched_text=matched_text,
    ):
        return False

    start = max(0, int(position) - _TEN_K_TOC_CONTEXT_LOOKAROUND_CHARS)
    end = min(
        len(full_text),
        int(position) + len(str(matched_text or "")) + _TEN_K_TOC_CONTEXT_LOOKAROUND_CHARS,
    )
    snippet = full_text[start:end]
    normalized_snippet = _normalize_ten_k_heading_search_text(snippet)
    if "table of contents" in normalized_snippet and not _has_ten_k_substantive_body_after_heading(
        full_text=full_text,
        position=position,
        matched_text=matched_text,
    ):
        return True

    page_ref_count = len(_TEN_K_TOC_PAGE_REFERENCE_RE.findall(snippet))
    if page_ref_count < _TEN_K_TOC_CONTEXT_MIN_PAGE_REFS:
        return False
    if _has_ten_k_substantive_body_after_heading(
        full_text=full_text,
        position=position,
        matched_text=matched_text,
    ):
        return False

    heading_hits = 0
    for headings in _TEN_K_BY_REFERENCE_DEFAULT_HEADINGS.values():
        if any(_normalize_ten_k_heading_search_text(heading) in normalized_snippet for heading in headings):
            heading_hits += 1
    if heading_hits >= 2:
        return True
    return _TEN_K_VIRTUAL_SECTION_ITEM_RE.search(snippet) is not None


def _may_be_ten_k_toc_heading_context(
    *,
    full_text: str,
    position: int,
    matched_text: str,
) -> bool:
    """用低成本局部探针判断是否值得进入 10-K ToC 语境分析。

    `SO` / `ETR` 一类 10-K 在 fallback 扫描时会命中大量正文句内短语。若这些
    命中都进入完整的 ToC 分析，会把时间耗在页码统计、标题簇扫描和正文探测上。
    这里先在更小的局部窗口里检查是否存在目录常见信号：`Table of Contents`、
    页码引用或其它 `Item` 编号。只有局部窗口已经出现这些信号时，才继续做
    完整的 ToC 语境判定。

    Args:
        full_text: 文档全文。
        position: 命中起点。
        matched_text: 命中的原始文本。

    Returns:
        可能位于 ToC / 索引语境时返回 ``True``；否则返回 ``False``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    start = max(0, int(position) - _TEN_K_TOC_CONTEXT_PROBE_LOOKAROUND_CHARS)
    end = min(
        len(full_text),
        int(position) + len(str(matched_text or "")) + _TEN_K_TOC_CONTEXT_PROBE_LOOKAROUND_CHARS,
    )
    probe = full_text[start:end]
    lowered_probe = probe.lower()
    if "table of contents" in lowered_probe:
        return True
    if _TEN_K_TOC_PAGE_REFERENCE_RE.search(probe) is not None:
        return True
    # 目录行常在 heading 后插入很长的 dot leaders / 空白，再出现页码与后续标题。
    # 若 probe 只看局部窗口，会把这类长导点目录误放过；这里补一次轻量后视。
    matched_end = max(0, int(position)) + len(str(matched_text or ""))
    suffix_end = min(len(full_text), matched_end + (_TEN_K_TOC_CONTEXT_LOOKAROUND_CHARS * 2))
    suffix = full_text[matched_end:suffix_end]
    if _TEN_K_TOC_PAGE_REFERENCE_RE.search(suffix) is not None:
        return True
    return _TEN_K_VIRTUAL_SECTION_ITEM_RE.search(probe) is not None


def _has_ten_k_substantive_body_after_heading(
    *,
    full_text: str,
    position: int,
    matched_text: str,
) -> bool:
    """判断标题后方是否紧跟实质正文。

    部分 inline annual report 会在真实标题前残留一小段
    ``Table of Contents`` / 页码提示。若标题后立刻出现连续正文，
    就不应因为附近存在目录噪声而把该标题判成 TOC。

    Args:
        full_text: 文档全文。
        position: 标题起点。
        matched_text: 命中的标题文本。

    Returns:
        标题后方存在足够正文时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    body_start = max(0, int(position) + len(str(matched_text or "")))
    body_end = min(len(full_text), body_start + _TEN_K_HEADING_BODY_LOOKAHEAD_CHARS)
    if body_end <= body_start:
        return False

    body_window = _normalize_whitespace(full_text[body_start:body_end])
    if not body_window:
        return False
    body_window = _TEN_K_HEADING_BODY_SKIP_RE.sub("", body_window).strip()
    if not body_window:
        return False

    leading_window = body_window[:_TEN_K_HEADING_BODY_WORD_WINDOW_CHARS]
    if len(_TEN_K_TOC_PAGE_REFERENCE_RE.findall(leading_window)) >= 3:
        return False
    if len(_TEN_K_VIRTUAL_SECTION_ITEM_RE.findall(leading_window)) >= 2:
        return False

    body_words = re.findall(r"[A-Za-z]{2,}", leading_window)
    return len(body_words) >= _TEN_K_HEADING_BODY_MIN_WORDS


def _looks_like_item_7_cross_reference(full_text: str, position: int) -> bool:
    """判断 Item 7 命中点是否落在交叉引用句而非章节标题。

    Args:
        full_text: 文档全文。
        position: 待判断位置。

    Returns:
        命中 ``in/to/see ... Item 7`` 交叉引用句时返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    start = max(0, int(position) - 160)
    end = min(len(full_text), int(position) + 220)
    snippet = full_text[start:end]
    local_position = int(position) - start
    for match in _ITEM_7_CROSS_REFERENCE_PATTERN.finditer(snippet):
        if match.start() <= local_position <= match.end() + 8:
            return True
    return False


def _looks_like_toc_page_line(full_text: str, position: int) -> bool:
    """10-K 版目录页码行判断，委托共享实现。"""
    return _looks_like_toc_page_line_generic(
        full_text, position, _TOC_PAGE_LINE_PATTERN, _TOC_PAGE_SNIPPET_PATTERN
    )


def _find_first_pattern_position_after(
    *,
    full_text: str,
    patterns: tuple[re.Pattern[str], ...],
    start_at: int,
    end_at: Optional[int] = None,
) -> Optional[int]:
    """返回多个正则在指定位置后的最早命中位置。

    Args:
        full_text: 文档全文。
        patterns: 候选标题正则集合。
        start_at: 起始扫描位置。
        end_at: 可选终止位置（不含），命中位置必须小于此值。

    Returns:
        最早命中位置；未命中返回 ``None``。

    Raises:
        RuntimeError: 扫描失败时抛出。
    """

    best_position: Optional[int] = None
    for pattern in patterns:
        match = pattern.search(full_text, pos=max(0, int(start_at)))
        if match is None:
            continue
        position = int(match.start())
        # 若指定了终止位置，跳过超出范围的命中
        if end_at is not None and position >= end_at:
            continue
        if best_position is None or position < best_position:
            best_position = position
    return best_position


def _build_part_markers(full_text: str) -> list[tuple[int, str]]:
    """提取 10-K 的 Part 标记。

    Args:
        full_text: 文档全文。

    Returns:
        `(position, part_title)` 列表。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    part_markers: list[tuple[int, str]] = []
    for match in _TEN_K_PART_PATTERN.finditer(full_text):
        roman = str(match.group(1) or "").strip().upper()
        if not roman:
            continue
        part_markers.append((int(match.start()), f"Part {roman}"))
    return part_markers


def _resolve_part_title(part_markers: list[tuple[int, str]], position: int) -> Optional[str]:
    """解析指定位置所属的最近 Part 标题。

    Args:
        part_markers: Part 标记列表。
        position: Item 位置。

    Returns:
        最近 Part 标题；若不存在则返回 `None`。

    Raises:
        RuntimeError: 解析失败时抛出。
    """

    resolved_title: Optional[str] = None
    for part_position, part_title in part_markers:
        if part_position > position:
            break
        resolved_title = part_title
    return resolved_title


def _correct_part_from_sec_rules(
    item_token: str,
    resolved_part: Optional[str],
) -> Optional[str]:
    """用 SEC 监管规则修正或补全 Part 标签。

    当正则扫描未找到 Part 标记、或 edgartools 给出的 Part 与 SEC 法定映射
    不一致时，以监管规则为准进行修正。

    这不是硬编码业务规则，而是 SEC Regulation S-K 的法定结构。

    Args:
        item_token: Item 编号（如 ``"1A"``、``"7"``、``"15"``）。
        resolved_part: 正则扫描解析的 Part 标题（如 ``"Part I"``），可为 ``None``。

    Returns:
        修正后的 Part 标题（如 ``"Part II"``）；映射中无对应时返回原值。

    Raises:
        RuntimeError: 处理失败时抛出。
    """

    canonical_roman = _TEN_K_ITEM_PART_MAP.get(item_token.upper())
    if canonical_roman is None:
        # 未知 Item 编号，保持原始推断
        return resolved_part

    canonical_title = f"Part {canonical_roman}"

    if resolved_part is None:
        # 缺失 Part → 补全
        return canonical_title

    # 已有 Part → 检查是否正确
    if resolved_part != canonical_title:
        # 修正错误的 Part 标签
        return canonical_title

    return resolved_part
