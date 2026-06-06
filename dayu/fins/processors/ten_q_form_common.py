"""10-Q 表单公共常量、marker 构建与章节后处理逻辑。

本模块提取 10-Q 相关的共享常量和 marker 函数，供
``TenQFormProcessor``（edgartools 路线）和
``BsTenQFormProcessor``（BeautifulSoup 路线）共同使用。

两侧处理器均从本模块 import，互不依赖，保持架构独立。
"""

from __future__ import annotations

import re
from typing import Optional

from .sec_form_section_common import (
    _VirtualSection,
    SIGNATURE_PATTERN as _SIGNATURE_PATTERN,
    _dedupe_markers,
    _find_marker_after,
)
from .sec_report_form_common import (
    _looks_like_inline_toc_snippet,
    _looks_like_toc_page_line_generic,
    _select_ordered_item_markers,
    _select_ordered_item_markers_after_toc,
)
from dayu.documents.processors.text_utils import normalize_whitespace as _normalize_whitespace

_PREVIEW_MAX_CHARS = 200

# SEC 文档常见两种 10-Q Item 标题形态：
# 1) ``Item 2.`` / ``Item 1A —``（标准写法）；
# 2) ``2. Management's Discussion ...``（纯编号写法，无 "Item" 前缀）。
#
# 真实文档中 “Management’s / Management's / Managements” 均会出现，
# 因此这里统一放宽 possessive 匹配，避免因为弯引号/省略引号导致漏检。
_APOSTROPHE_CHARS_PATTERN = "'’‘`´"
_MANAGEMENT_POSSESSIVE_PATTERN = (
    rf"management(?:\s*[{_APOSTROPHE_CHARS_PATTERN}]\s*)?s?"
)
_TEN_Q_ITEM_PATTERN = re.compile(
    r"(?im)(?:\bitem\s+(1A|[1-6])(?:\s*[\.\:\-\u2013\u2014]\s*|\s+(?=[A-Za-z])))"
    r"|(?:^|\n)\s*(1A|[1-6])\s*(?:[\.\:\-\u2013\u2014]\s*|\s+)"
    rf"(?=(?:financial statements|{_MANAGEMENT_POSSESSIVE_PATTERN}\s+discussion|"
    r"quantitative and qualitative disclosures|controls and procedures|legal proceedings|risk factors|"
    r"unregistered sales|defaults|mine safety|exhibits)\b)"
)

# SEC Form 10-Q 法定 Item 结构
# 参考 SEC Regulation S-K + SEC Form 10-Q General Instructions
# Part I - Financial Information: Items 1, 2, 3, 4
# Part II - Other Information: Items 1, 1A, 2, 3, 4, 5, 6
_TEN_Q_PART_I_ITEM_ORDER: tuple[str, ...] = ("1", "2", "3", "4")
_TEN_Q_PART_II_ITEM_ORDER: tuple[str, ...] = ("1", "1A", "2", "3", "4", "5", "6")

# SEC Form 10-Q 法定 Part 标题模式
# 参考 SEC Regulation S-K §229.10(c) + Form 10-Q General Instructions
# Part I 法定标题固定为 "Financial Information"
# Part II 法定标题固定为 "Other Information"
#
# 注意：BSProcessor 的 get_text(separator=" ") 可能在 HTML 元素边界处
# 将单词拆分为多段（如 "FINANCIAL" → "FINANCI AL"），
# 因此使用 _html_flexible_word() 生成容忍断字的匹配模式。


def _html_flexible_word(word: str) -> str:
    """生成允许 HTML 文本提取断字的灵活正则模式。

    BSProcessor 使用 ``get_text(separator=" ")`` 提取纯文本，
    HTML 元素边界可能导致单词中间插入空格（如 ``<span>FINANCI</span><span>AL</span>``
    提取后变为 ``FINANCI AL``）。本函数在每个字符之间插入 ``\\s*``
    以容忍此类断字情况。

    Args:
        word: 预期的完整单词（如 ``"FINANCIAL"``）。

    Returns:
        允许字符间可选空白的正则模式字符串。

    Raises:
        ValueError: word 为空时抛出。
    """
    if not word:
        raise ValueError("word 不能为空")
    return r"\s*".join(word)


_PART_I_HEADING_PATTERN = re.compile(
    r"(?i)\bPART\s+I\b"  # "Part I" (word boundary 阻止匹配 "Part II")
    r"[\s\.\-—–:]*"  # 可选标点 / 空白
    + _html_flexible_word("FINANCIAL")
    + r"\s+"
    + _html_flexible_word("INFORMATION"),
)
_PART_II_HEADING_PATTERN = re.compile(
    r"(?i)\bPART\s+II\b"
    r"[\s\.\-—–:]*"
    + _html_flexible_word("OTHER")
    + r"\s+"
    + _html_flexible_word("INFORMATION"),
)

# 锚点质量验证阈值
# SEC Form 10-Q 法定必填章节（Item 1 Financial Statements、Item 2 MD&A）
# 正常内容 span 至少数千字符；若 span 极短说明锚点落入 running header / ToC 区域。
# 注意：Part I Item 3（Quantitative Disclosures）和 Item 4（Controls & Procedures）
# 在许多公司的 10-Q 中合法地只有数百字符，因此不能要求所有 Item 都有大 span。
# 策略：只要求至少 _ANCHOR_QUALITY_MIN_MEANINGFUL_ITEMS 个 Item 有实质性 span，
# 这对应 Item 1 和 Item 2 这两个法定必填大章节。
_ANCHOR_QUALITY_MIN_SPAN = 1000  # 低于此长度的 Item span 视为 "极短"
_ANCHOR_QUALITY_MIN_MEANINGFUL_ITEMS = 2  # 至少需要 N 个 Item 有实质性 span
# Part II 锚点 ToC 聚簇最大扩展距离。
# 当 Part I 所有候选锚点与 Part II 锚点的间距均小于此阈值时，
# 视 Part II 锚点也在 ToC 区域，Phase 1 回退时不使用其作为范围上限。
# 典型案例：HIG 10-Q，ToC 紧凑（Part I → Part II 仅 1600 chars），
# 两者都在目录区，不应截断正文 Item 选取。
_PART_II_ANCHOR_MAX_TOC_SPREAD = 5000
_TOC_PAGE_LINE_PATTERN = re.compile(r"(?im)^\s*[A-Za-z][^\n]{0,220}\b\d{1,3}\s*$")
_TOC_PAGE_SNIPPET_PATTERN = re.compile(
    r"(?is)^\s*(?:item\s+(?:1A|[1-6])\s*[\.\:\-\u2013\u2014]?\s*)?[A-Za-z][^\n]{0,220}\b\d{1,3}\b"
    r"(?:\s+item\s+(?:1A|[1-6])\b|\s*$)"
)
_TEN_Q_PART_I_HEADING_FALLBACK_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "1": (
        re.compile(
            r"(?i)\b(?:item\s+1\s*[\.\:\-\u2013\u2014]\s*)?"
            r"financial statements(?: and supplementary data)?\b"
        ),
    ),
    "2": (
        re.compile(
            r"(?i)\b(?:item\s+2\s*[\.\:\-\u2013\u2014]\s*)?"
            rf"{_MANAGEMENT_POSSESSIVE_PATTERN}\s+discussion and analysis"
            r"(?: of financial condition and results of operations)?\b"
        ),
    ),
    "3": (
        re.compile(
            r"(?i)\b(?:item\s+3\s*[\.\:\-\u2013\u2014]\s*)?"
            r"quantitative and qualitative disclosures about market risk\b"
        ),
    ),
    "4": (
        re.compile(
            r"(?i)\b(?:item\s+4\s*[\.\:\-\u2013\u2014]\s*)?"
            r"(?:disclosure\s+)?controls and procedures\b"
        ),
    ),
}
_TEN_Q_PART_I_EXPECTED_KEYWORDS: dict[str, tuple[str, ...]] = {
    "1": ("financial statements",),
    "2": ("management", "discussion"),
    "3": ("quantitative", "market risk"),
    "4": ("controls", "procedures"),
}
_TEN_Q_PART_I_TOC_SUMMARY_PATTERN = re.compile(
    r"(?is)\bitems?\s+1\s*,\s*2\s*,\s*3\s*(?:,|and)\s*4\b"
    rf".{{0,260}}\bfinancial statements\b.{{0,260}}\b{_MANAGEMENT_POSSESSIVE_PATTERN}\s+discussion\b"
)
_PART_I_ITEM_CROSS_REFERENCE_PATTERN = re.compile(
    r"(?is)\b(?:in|to)\s+part\s+i\s*,\s*item\s+(1|2)\b"
)
_TEN_Q_ITEM_1_STRUCTURED_HEADING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bcondensed\s+consolidated\s+financial\s+statements\b"),
    re.compile(r"(?i)\bconsolidated\s+financial\s+statements\b"),
    re.compile(r"(?i)\bnotes\s+to\s+(?:condensed\s+)?consolidated\s+financial\s+statements\b"),
)
_MIN_PART_I_KEY_ITEM_GAP_CHARS = 120
_TEN_Q_VIRTUAL_SECTION_ITEM_RE = re.compile(
    r"(?i)^part\s+(i|ii)\s*-\s*item\s+(1A|[1-6])\b"
)
_TEN_Q_HEADING_PREFIX_RE = re.compile(
    r"(?i)^\s*(?:part\s+(?:i|ii)\s*[\.\-—–:]\s*)?(?:item\s+(?:1A|[1-6])\s*[\.\-—–:]?\s*)?$"
)
_TEN_Q_HEADING_ONLY_MAX_CHARS = 180
_TEN_Q_STUB_SECTION_MAX_CHARS = 1800
_TEN_Q_STUB_PAGE_LINE_RATIO = 0.35
_TEN_Q_REPLACEMENT_MIN_DISTANCE = 50
_TEN_Q_BY_REFERENCE_STUB_RE = re.compile(
    r"(?is)\b(?:information\s+in\s+response\s+to\s+this\s+item\b.*?\bcan\s+be\s+found\b|"
    r"incorporat(?:ed|es)\b.*?\bby\s+reference\b|"
    r"(?:included\s+in|can\s+be\s+found\s+in|see\b.*?\bin)\b.*?\b(?:annual\s+report|form\s+10-k)\b)"
)
_TEN_Q_ITEM_2_ALIAS_RE = re.compile(
    rf"(?is){_MANAGEMENT_POSSESSIVE_PATTERN}\s+discussion\s+and\s+analysis"
    r"\s+of\s+financial\s+condition\s+and\s+results\s+of\s+operations\s*\(([^)\n]{3,80})\)"
)
_TEN_Q_TITLEISH_LINE_RE = re.compile(r"(?i)^[A-Za-z][A-Za-z0-9 '&(),/.\-]{2,180}$")
_TEN_Q_DEFAULT_HEADING_PATTERNS: dict[tuple[str, str], tuple[re.Pattern[str], ...]] = {
    ("I", "1"): (
        re.compile(
            rf"(?im)^\s*(?:item\s+1\s*[\.\:\-\u2013\u2014]?\s*)?"
            rf"{_html_flexible_word('CONSOLIDATED')}\s+{_html_flexible_word('FINANCIAL')}\s+{_html_flexible_word('STATEMENTS')}\b"
        ),
        re.compile(
            rf"(?im)^\s*(?:item\s+1\s*[\.\:\-\u2013\u2014]?\s*)?"
            rf"{_html_flexible_word('CONDENSED')}\s+{_html_flexible_word('CONSOLIDATED')}\s+{_html_flexible_word('FINANCIAL')}\s+{_html_flexible_word('STATEMENTS')}\b"
        ),
        re.compile(
            rf"(?im)^\s*(?:item\s+1\s*[\.\:\-\u2013\u2014]?\s*)?"
            rf"{_html_flexible_word('FINANCIAL')}\s+{_html_flexible_word('STATEMENTS')}(?:\s*\(unaudited\))?\b"
        ),
        re.compile(
            rf"(?im)^\s*(?:item\s+1\s*[\.\:\-\u2013\u2014]?\s*)?"
            rf"(?:{_html_flexible_word('CONDENSED')}\s+)?{_html_flexible_word('CONSOLIDATED')}\s+"
            rf"{_html_flexible_word('STATEMENT')}(?:{_html_flexible_word('S')})?\s+{_html_flexible_word('OF')}\s+{_html_flexible_word('INCOME')}\b"
        ),
    ),
    ("I", "2"): (
        re.compile(
            rf"(?im)^\s*(?:item\s+2\s*[\.\:\-\u2013\u2014]?\s*)?"
            rf"{_MANAGEMENT_POSSESSIVE_PATTERN}\s+discussion\s+and\s+analysis\s+"
            r"of\s+financial\s+condition\s+and\s+results\s+of\s+operations\b"
        ),
        re.compile(r"(?im)^\s*MD&A\b"),
    ),
    ("II", "1"): (
        re.compile(r"(?im)^\s*(?:item\s+1\s*[\.\:\-\u2013\u2014]?\s*)?legal proceedings\b"),
    ),
    ("II", "1A"): (
        re.compile(r"(?im)^\s*(?:item\s+1A\s*[\.\:\-\u2013\u2014]?\s*)?risk factors\b"),
    ),
    ("II", "2"): (
        re.compile(
            r"(?im)^\s*(?:item\s+2\s*[\.\:\-\u2013\u2014]?\s*)?"
            r"unregistered sales of equity securities and use of proceeds\b"
        ),
    ),
    ("II", "5"): (
        re.compile(r"(?im)^\s*(?:item\s+5\s*[\.\:\-\u2013\u2014]?\s*)?other information\b"),
    ),
    ("II", "6"): (
        re.compile(r"(?im)^\s*(?:item\s+6\s*[\.\:\-\u2013\u2014]?\s*)?exhibit index\b"),
        re.compile(r"(?im)^\s*(?:item\s+6\s*[\.\:\-\u2013\u2014]?\s*)?exhibits\b"),
    ),
}


def _find_all_part_heading_positions(
    full_text: str,
) -> tuple[list[int], list[int]]:
    """查找所有 Part I / Part II 法定标题的出现位置。

    返回所有匹配位置，由调用方决定使用哪个（支持从后向前逐个验证）。

    Args:
        full_text: 文档全文。

    Returns:
        ``(part_i_positions, part_ii_positions)``，各为按出现顺序排列的位置列表。

    Raises:
        RuntimeError: 扫描失败时抛出。
    """
    part_i_positions = [m.start() for m in _PART_I_HEADING_PATTERN.finditer(full_text)]
    part_ii_positions = [m.start() for m in _PART_II_HEADING_PATTERN.finditer(full_text)]
    return part_i_positions, part_ii_positions


def _select_best_part_i_anchor(
    full_text: str,
    part_i_positions: list[int],
    part_ii_anchor: Optional[int],
) -> Optional[int]:
    """从 Part I 候选锚点中选择最佳位置。

    策略：从后向前逐个候选尝试，用 SEC 法定规则验证锚点质量——
    Part I 的 Item 1（Financial Statements）和 Item 2（MD&A）
    是 SEC Form 10-Q 法定必填章节，内容 span 不可能极短。

    若某候选锚点导致 ≥2 个选中 Item 的 span < 阈值，则判定该锚点
    位于 running header 区域，回退到前一个候选。

    Args:
        full_text: 文档全文。
        part_i_positions: Part I 标题的所有匹配位置（按出现顺序）。
        part_ii_anchor: Part II 锚定位置（限制 Part I 扫描范围）。

    Returns:
        最佳 Part I 锚定位置；所有候选均不合格时返回 ``None``。

    Raises:
        RuntimeError: 选择失败时抛出。
    """
    if not part_i_positions:
        return None

    # 从后向前逐个尝试（后面的更可能跳过 ToC，但也可能落入 running header）
    for candidate in reversed(part_i_positions):
        # 健全性：Part I anchor 必须在 Part II anchor 之前
        if part_ii_anchor is not None and candidate >= part_ii_anchor:
            continue

        # 试选 Part I Items：在 [candidate, part_ii_anchor) 范围内选取
        trial_items = _select_ordered_item_markers(
            full_text,
            item_pattern=_TEN_Q_ITEM_PATTERN,
            ordered_tokens=_TEN_Q_PART_I_ITEM_ORDER,
            start_at=candidate,
            end_at=part_ii_anchor,
        )

        # 质量验证：检查选中 Items 的内容 span 是否合理
        # SEC Form 10-Q General Instructions Section A 规定 Item 1/2 为法定必填，
        # 正常情况下 span 不可能极短（< 1000 chars）
        if _anchor_produces_meaningful_items(full_text, trial_items, part_ii_anchor):
            return candidate

    return None


def _anchor_produces_meaningful_items(
    full_text: str,
    trial_items: list[tuple[str, int]],
    end_boundary: Optional[int],
) -> bool:
    """验证锚点选出的 Items 内容是否有意义。

    SEC Form 10-Q 的 Part I Item 1（Financial Statements）和
    Item 2（MD&A）是法定必填大章节，internal span 不可能极短。
    但 Item 3（Quantitative Disclosures）和 Item 4（Controls & Procedures）
    在许多公司的 10-Q 中合法地只有几百字符。

    策略：只要求至少 ``_ANCHOR_QUALITY_MIN_MEANINGFUL_ITEMS`` 个
    选中 Item 的 span ≥ 阈值，对应 Item 1 和 Item 2 这两个法定大章节。
    若所有/几乎所有 Item 都极短，说明锚点落在了 ToC 或 running header 区域。

    Args:
        full_text: 文档全文。
        trial_items: 试选的 ``(item_token, position)`` 列表。
        end_boundary: 可选扫描终止位置。

    Returns:
        ``True`` 表示锚点质量合格，``False`` 表示需要回退。

    Raises:
        RuntimeError: 验证失败时抛出。
    """
    if len(trial_items) < 2:
        # 选中 Item 太少，无法判断质量
        return False

    # 计算每个 Item 的 span（与下一个 Item 或终止位置的距离）
    meaningful_count = 0
    for i, (_, pos) in enumerate(trial_items):
        if i + 1 < len(trial_items):
            next_pos = trial_items[i + 1][1]
        elif end_boundary is not None:
            next_pos = end_boundary
        else:
            next_pos = len(full_text)
        span = next_pos - pos
        if span >= _ANCHOR_QUALITY_MIN_SPAN:
            meaningful_count += 1

    # 至少需要 N 个 Item 有实质性 span（对应 Item 1 和 Item 2）
    return meaningful_count >= _ANCHOR_QUALITY_MIN_MEANINGFUL_ITEMS


def _build_ten_q_markers(full_text: str) -> list[tuple[int, Optional[str]]]:
    """构建 10-Q 的 Part + Item 边界。

    策略：利用 SEC Form 10-Q 法定结构（Part I Items 1-4、
    Part II Items 1-6+1A），结合 Part 法定标题锚定内容区边界，
    两阶段有序选取：

    1. **锚定**：检测所有 ``Part I — Financial Information`` 和
       ``Part II — Other Information`` 标题位置。Part II 取最后一个匹配；
       Part I 从后向前逐个验证锚点质量（防止 running header 干扰）。
    2. **Phase 1 — Part I**：在锚定区域内选取 Items 1-4。
       若锚定失败则回退到 ``_select_ordered_item_markers_after_toc``。
    3. **Phase 2 — Part II**：从 Part I 最后一个 Item 之后
       或 Part II 锚定位置开始，选取 Items 1, 1A, 2-6。
    4. 用 SEC 法定结构为每个 Item 标注所属 Part。

    使用 Part 法定标题作为锚点 + 锚点质量验证，同时解决：
    - TOC 缓冲区过宽导致跳过实际内容 Item 的问题；
    - Running page header 导致锚点落入文档末尾的问题（MSFT 等公司）。

    Args:
        full_text: 文档全文。

    Returns:
        标记列表；标记不足时返回空列表触发父类回退。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    # 锚定：查找所有 Part 法定标题位置
    part_i_positions, part_ii_positions = _find_all_part_heading_positions(full_text)

    # Part II 锚定：取最后一个匹配（Part II 不存在 running header 重复问题，
    # 因为 Part II 在文档后半部分，running header 通常只重复 Part I 标题）
    part_ii_anchor = part_ii_positions[-1] if part_ii_positions else None

    # Part I 锚定：从后向前逐个验证质量，防止 running header 导致锚点偏移
    part_i_anchor = _select_best_part_i_anchor(
        full_text, part_i_positions, part_ii_anchor,
    )

    # Phase 1: Part I Items
    if part_i_anchor is not None:
        # Part 标题锚定成功 → 在 Part I 区域内有序选取 Items 1-4
        # end_at 限制为 Part II 锚定位置（如有），防止选入 Part II Items
        part_i_selected = _select_ordered_item_markers(
            full_text,
            item_pattern=_TEN_Q_ITEM_PATTERN,
            ordered_tokens=_TEN_Q_PART_I_ITEM_ORDER,
            start_at=part_i_anchor,
            end_at=part_ii_anchor,
        )
    else:
        # 无合格 Part 标题锚点 → 回退到 TOC 自适应策略
        # 传入 part_ii_anchor 限制选取范围，防止 Part I Items
        # 误入 Part II TOC 区域（NFLX 10-Q 等 iXBRL 文件场景）
        #
        # 注意：若 Part I 和 Part II 锚点间距极小（均在 ToC 聚簇内），
        # 不应使用 Part II ToC 条目作为 Phase 1 的范围上限——否则会将
        # 正文中所有 Part I Items 排除在外（如 HIG 10-Q）。
        effective_phase1_end_at = part_ii_anchor
        if (
            part_ii_anchor is not None
            and part_i_positions
            and part_ii_anchor - min(part_i_positions) < _PART_II_ANCHOR_MAX_TOC_SPREAD
        ):
            # Part I / Part II 锚点均在 ToC 聚簇内，不限制 Phase 1 范围
            effective_phase1_end_at = None
        part_i_selected = _select_ordered_item_markers_after_toc(
            full_text,
            item_pattern=_TEN_Q_ITEM_PATTERN,
            ordered_tokens=_TEN_Q_PART_I_ITEM_ORDER,
            min_items_after_toc=2,
            end_at=effective_phase1_end_at,
        )
    part_i_selected = _repair_part_i_key_items_with_heading_fallback(
        full_text=full_text,
        part_i_selected=part_i_selected,
        start_at=part_i_anchor if part_i_anchor is not None else 0,
        end_at=part_ii_anchor,
    )

    # Phase 2: Part II Items
    # 确定 Phase 2 扫描起点
    if part_i_selected:
        # 从 Part I 最后一个 Item 之后开始
        phase_2_start = part_i_selected[-1][1] + 1
    elif part_ii_anchor is not None:
        # 无 Part I Items 但有 Part II 锚定 → 从 Part II 开始
        phase_2_start = part_ii_anchor
    else:
        # 完全无锚定信息
        phase_2_start = 0

    if part_i_selected or part_ii_anchor is not None:
        # Part I 已正确定位或有 Part II 锚定 → 无需重复 TOC 去噪
        part_ii_selected = _select_ordered_item_markers(
            full_text,
            item_pattern=_TEN_Q_ITEM_PATTERN,
            ordered_tokens=_TEN_Q_PART_II_ITEM_ORDER,
            start_at=phase_2_start,
        )
    else:
        # 无任何锚定 → Part II 也需要完整 TOC 去噪
        part_ii_selected = _select_ordered_item_markers_after_toc(
            full_text,
            item_pattern=_TEN_Q_ITEM_PATTERN,
            ordered_tokens=_TEN_Q_PART_II_ITEM_ORDER,
            min_items_after_toc=2,
        )
    part_ii_selected = _repair_part_ii_key_items_with_heading_fallback(
        full_text=full_text,
        part_ii_selected=part_ii_selected,
        start_at=phase_2_start,
    )

    # 合并标记，用 SEC 法定结构标注 Part 标签
    markers: list[tuple[int, Optional[str]]] = []
    for item_token, position in part_i_selected:
        markers.append((position, f"Part I - Item {item_token}"))
    for item_token, position in part_ii_selected:
        markers.append((position, f"Part II - Item {item_token}"))

    if len(markers) < 3:
        return []

    # 尾段 SIGNATURE 章节
    signature_marker = _find_marker_after(
        _SIGNATURE_PATTERN,
        full_text,
        int(markers[-1][0]),
        "SIGNATURE",
    )
    if signature_marker is not None:
        markers.append(signature_marker)
    return _dedupe_markers(markers)


def expand_ten_q_virtual_sections_content(
    *,
    full_text: str,
    virtual_sections: list[_VirtualSection],
) -> None:
    """修正 10-Q 虚拟章节中的 TOC/stub 误切正文。

    该后处理不改变 SEC 法定 Item 骨架，仅在虚拟章节已生成后，
    用同一 filing 内更可信的正文标题起点替换当前落在目录、页码行
    或 by-reference 包装句上的 section 起点。

    Args:
        full_text: 用于切分的完整文本。
        virtual_sections: 已构建好的虚拟章节列表。

    Returns:
        无。

    Raises:
        RuntimeError: 修复失败时抛出。
    """

    if not full_text or not virtual_sections:
        return

    top_level_sections = _collect_ten_q_top_level_sections(virtual_sections)
    if not top_level_sections:
        return

    replacement_starts: dict[tuple[str, str], int] = {}
    any_replacement_applied = False
    target_keys = (("I", "1"), ("I", "2"), ("II", "1"), ("II", "1A"), ("II", "2"))
    section_map = _collect_ten_q_virtual_item_sections(top_level_sections)
    for key in target_keys:
        section = section_map.get(key)
        if section is None:
            continue
        replacement_start = _resolve_ten_q_virtual_section_replacement_start(
            full_text=full_text,
            section=section,
            key=key,
        )
        if replacement_start is None:
            continue
        replacement_starts[key] = replacement_start

    if not replacement_starts:
        return

    for index, section in enumerate(top_level_sections):
        key = _parse_ten_q_virtual_section_key(section.title)
        if key is None:
            continue
        replacement_start = replacement_starts.get(key)
        if replacement_start is None:
            continue
        replacement_end = _resolve_ten_q_virtual_section_replacement_end(
            full_text=full_text,
            top_level_sections=top_level_sections,
            current_index=index,
            replacement_starts=replacement_starts,
            replacement_start=replacement_start,
        )
        if replacement_end is None or replacement_end <= replacement_start:
            continue
        replacement_content = full_text[replacement_start:replacement_end].strip()
        allow_toc_boundary_replacement = _has_ten_q_toc_like_start(
            full_text=full_text,
            position=section.start,
        )
        if not _should_apply_ten_q_virtual_section_replacement(
            current_content=section.content,
            replacement_content=replacement_content,
            allow_toc_boundary_replacement=allow_toc_boundary_replacement,
        ):
            continue
        section.start = replacement_start
        section.end = replacement_end
        section.content = replacement_content
        section.preview = _normalize_whitespace(replacement_content)[:_PREVIEW_MAX_CHARS]
        any_replacement_applied = True

    if any_replacement_applied:
        virtual_sections.sort(key=lambda section: (section.start, section.level, section.ref))


def _collect_ten_q_top_level_sections(
    virtual_sections: list[_VirtualSection],
) -> list[_VirtualSection]:
    """提取 10-Q 顶层虚拟章节。

    Args:
        virtual_sections: 原始虚拟章节列表。

    Returns:
        仅包含一级章节的升序列表。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    return [
        section
        for section in virtual_sections
        if section.level == 1
    ]


def _collect_ten_q_virtual_item_sections(
    virtual_sections: list[_VirtualSection],
) -> dict[tuple[str, str], _VirtualSection]:
    """提取 10-Q 顶层 Item 虚拟章节映射。

    Args:
        virtual_sections: 顶层虚拟章节列表。

    Returns:
        ``(part, item) -> section`` 映射。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    mapping: dict[tuple[str, str], _VirtualSection] = {}
    for section in virtual_sections:
        key = _parse_ten_q_virtual_section_key(section.title)
        if key is None:
            continue
        mapping[key] = section
    return mapping


def _parse_ten_q_virtual_section_key(title: Optional[str]) -> Optional[tuple[str, str]]:
    """解析 10-Q 顶层章节标题中的 ``(part, item)`` 键。

    Args:
        title: 虚拟章节标题。

    Returns:
        成功时返回 ``("I"|"II", item_token)``，否则返回 ``None``。

    Raises:
        RuntimeError: 解析失败时抛出。
    """

    match = _TEN_Q_VIRTUAL_SECTION_ITEM_RE.search(str(title or ""))
    if match is None:
        return None
    part = str(match.group(1) or "").upper()
    item = str(match.group(2) or "").upper()
    if not part or not item:
        return None
    return part, item


def _resolve_ten_q_virtual_section_replacement_start(
    *,
    full_text: str,
    section: _VirtualSection,
    key: tuple[str, str],
) -> Optional[int]:
    """为可疑 10-Q section 选择更可信的正文起点。

    Args:
        full_text: 文档全文。
        section: 当前虚拟章节。
        key: ``(part, item)`` 键。

    Returns:
        更可信的正文起点；无候选时返回 ``None``。

    Raises:
        RuntimeError: 选择失败时抛出。
    """

    if not _looks_like_ten_q_virtual_section_stub(full_text, section):
        return None

    search_start = min(len(full_text), max(section.start + _TEN_Q_REPLACEMENT_MIN_DISTANCE, 0))
    patterns = _build_ten_q_replacement_heading_patterns(key=key, section=section)
    if not patterns:
        return None
    forward_replacement = _find_ten_q_heading_position(
        full_text=full_text,
        patterns=patterns,
        start_at=search_start,
    )
    if forward_replacement is not None and forward_replacement > section.start:
        return forward_replacement

    if _TEN_Q_BY_REFERENCE_STUB_RE.search(str(section.content or "")) is None:
        return None

    backward_replacement = _find_last_ten_q_heading_position(
        full_text=full_text,
        patterns=patterns,
        end_at=max(0, section.start - 1),
    )
    if backward_replacement is None:
        return None
    return backward_replacement


def _build_ten_q_replacement_heading_patterns(
    *,
    key: tuple[str, str],
    section: _VirtualSection,
) -> tuple[re.Pattern[str], ...]:
    """构建 10-Q section 的正文标题候选模式。

    Args:
        key: ``(part, item)`` 键。
        section: 当前虚拟章节。

    Returns:
        供正文回收使用的正则模式元组。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    patterns = list(_TEN_Q_DEFAULT_HEADING_PATTERNS.get(key, ()))
    if key == ("I", "2"):
        patterns.extend(_derive_ten_q_item_2_alias_patterns(section.content))
    return tuple(patterns)


def _derive_ten_q_item_2_alias_patterns(content: str) -> tuple[re.Pattern[str], ...]:
    """从 Item 2 当前内容中提取 MD&A 别名标题。

    典型场景是目录项写成
    ``Management's Discussion ... (Financial Review)``，
    正文真实标题只保留括号中的别名。

    Args:
        content: 当前 Item 2 章节内容。

    Returns:
        基于同文档别名生成的标题模式元组。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    aliases: list[str] = []
    for alias in _TEN_Q_ITEM_2_ALIAS_RE.findall(str(content or "")):
        cleaned = _normalize_whitespace(alias).strip(".,;:() ")
        if len(cleaned) < 3:
            continue
        if cleaned not in aliases:
            aliases.append(cleaned)

    patterns: list[re.Pattern[str]] = []
    for alias in aliases:
        escaped_alias = re.escape(alias)
        patterns.append(
            re.compile(
                rf"(?im)^\s*(?:item\s+2\s*[\.\:\-\u2013\u2014]?\s*)?{escaped_alias}\b"
            )
        )
    return tuple(patterns)


def _find_ten_q_heading_position(
    *,
    full_text: str,
    patterns: tuple[re.Pattern[str], ...],
    start_at: int,
) -> Optional[int]:
    """在全文中定位首个可信的 10-Q 正文标题。

    Args:
        full_text: 文档全文。
        patterns: 标题候选模式。
        start_at: 搜索起点。

    Returns:
        首个可信命中位置；未命中时返回 ``None``。

    Raises:
        RuntimeError: 搜索失败时抛出。
    """

    best_position: Optional[int] = None
    for pattern in patterns:
        for match in pattern.finditer(full_text, pos=max(0, int(start_at))):
            matched_text = str(match.group(0) or "")
            leading_whitespace = len(matched_text) - len(matched_text.lstrip())
            position = int(match.start()) + leading_whitespace
            matched_text = str(match.group(0) or "")
            if not _looks_like_ten_q_standalone_heading_context(
                full_text=full_text,
                position=position,
                matched_text=matched_text,
            ):
                continue
            if best_position is None or position < best_position:
                best_position = position
            break
    return best_position


def _looks_like_ten_q_standalone_heading_context(
    *,
    full_text: str,
    position: int,
    matched_text: str,
) -> bool:
    """判断命中是否位于独立标题语境。

    Args:
        full_text: 文档全文。
        position: 命中起点。
        matched_text: 命中的原始文本。

    Returns:
        若更像独立标题行则返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    if _looks_like_toc_page_line(full_text, position):
        return False
    if _looks_like_inline_toc_snippet(full_text, position):
        return False

    line_start = full_text.rfind("\n", 0, max(0, int(position))) + 1
    line_end = full_text.find("\n", int(position))
    if line_end < 0:
        line_end = len(full_text)
    line = full_text[line_start:line_end]
    normalized_line = _normalize_whitespace(line)
    if len(normalized_line) > 220:
        return False

    prefix = line[: max(0, int(position) - line_start)]
    normalized_prefix = _normalize_whitespace(prefix)
    if normalized_prefix and _TEN_Q_HEADING_PREFIX_RE.fullmatch(normalized_prefix) is None:
        return False

    del matched_text
    return True


def _find_last_ten_q_heading_position(
    *,
    full_text: str,
    patterns: tuple[re.Pattern[str], ...],
    end_at: int,
) -> Optional[int]:
    """在全文前半段定位最后一个可信标题。

    Args:
        full_text: 文档全文。
        patterns: 标题候选模式。
        end_at: 搜索终点（含）。

    Returns:
        最后一个可信命中位置；未命中时返回 ``None``。

    Raises:
        RuntimeError: 搜索失败时抛出。
    """

    best_position: Optional[int] = None
    for pattern in patterns:
        for match in pattern.finditer(full_text):
            matched_text = str(match.group(0) or "")
            leading_whitespace = len(matched_text) - len(matched_text.lstrip())
            position = int(match.start()) + leading_whitespace
            if position > end_at:
                break
            if not _looks_like_ten_q_standalone_heading_context(
                full_text=full_text,
                position=position,
                matched_text=matched_text,
            ):
                continue
            best_position = position
    return best_position


def _looks_like_ten_q_virtual_section_stub(
    full_text: str,
    section: _VirtualSection,
) -> bool:
    """判断 10-Q 虚拟章节是否更像 TOC/stub 而非正文。

    Args:
        full_text: 文档全文。
        section: 当前虚拟章节。

    Returns:
        若章节起点或内容更像目录/包装句则返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    if _has_ten_q_toc_like_start(full_text=full_text, position=section.start):
        return True

    normalized = _normalize_whitespace(str(section.content or ""))
    if not normalized:
        return False
    if (
        len(normalized) <= _TEN_Q_HEADING_ONLY_MAX_CHARS
        and _looks_like_ten_q_titleish_stub_content(section.content)
    ):
        return True
    if (
        len(normalized) <= _TEN_Q_STUB_SECTION_MAX_CHARS
        and _TEN_Q_BY_REFERENCE_STUB_RE.search(normalized) is not None
    ):
        return True
    current_line = _extract_ten_q_line_at_position(full_text, section.start)
    if (
        len(normalized) <= _TEN_Q_STUB_SECTION_MAX_CHARS
        and current_line
        and not _looks_like_ten_q_standalone_heading_context(
            full_text=full_text,
            position=section.start,
            matched_text=current_line,
        )
    ):
        return True
    return False


def _has_ten_q_toc_like_start(*, full_text: str, position: int) -> bool:
    """判断起点是否更像目录行而非正文标题。

    Args:
        full_text: 文档全文。
        position: 待判断位置。

    Returns:
        若起点更像 TOC 片段则返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    if _looks_like_toc_page_line(full_text, position):
        return True
    if _looks_like_inline_toc_snippet(full_text, position):
        return True

    current_line = _extract_ten_q_line_at_position(full_text, position)
    normalized_line = _normalize_whitespace(current_line)
    if not normalized_line:
        return False
    return (
        _TOC_PAGE_SNIPPET_PATTERN.match(normalized_line) is not None
        or _TOC_PAGE_LINE_PATTERN.match(normalized_line) is not None
        or _looks_like_inline_toc_snippet(normalized_line, 0)
    )


def _extract_ten_q_line_at_position(full_text: str, position: int) -> str:
    """提取指定位置所在行文本。

    Args:
        full_text: 文档全文。
        position: 目标位置。

    Returns:
        包含该位置的整行文本。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    line_start = full_text.rfind("\n", 0, max(0, int(position))) + 1
    line_end = full_text.find("\n", max(0, int(position)))
    if line_end < 0:
        line_end = len(full_text)
    return full_text[line_start:line_end]


def _looks_like_ten_q_titleish_stub_content(content: str) -> bool:
    """判断内容是否主要由标题行/页码行组成。

    Args:
        content: 当前章节内容。

    Returns:
        若内容更像标题 stub 则返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    lines = [
        _normalize_whitespace(line)
        for line in str(content or "").splitlines()
        if _normalize_whitespace(line)
    ]
    if not lines:
        return False
    if len(lines) == 1:
        line = lines[0]
        return (
            _TOC_PAGE_SNIPPET_PATTERN.match(line) is not None
            or _TOC_PAGE_LINE_PATTERN.match(line) is not None
            or _looks_like_inline_toc_snippet(line, 0)
            or _TEN_Q_HEADING_PREFIX_RE.fullmatch(line) is not None
            or _TEN_Q_TITLEISH_LINE_RE.fullmatch(line) is not None
        )

    page_like_count = 0
    titleish_count = 0
    for line in lines:
        if (
            _TOC_PAGE_LINE_PATTERN.match(line) is not None
            or _TOC_PAGE_SNIPPET_PATTERN.match(line) is not None
            or _looks_like_inline_toc_snippet(line, 0)
        ):
            page_like_count += 1
            continue
        if _TEN_Q_HEADING_PREFIX_RE.fullmatch(line) is not None:
            titleish_count += 1
            continue
        if _TEN_Q_TITLEISH_LINE_RE.fullmatch(line) is not None:
            titleish_count += 1

    if page_like_count / len(lines) >= _TEN_Q_STUB_PAGE_LINE_RATIO:
        return True
    return (page_like_count + titleish_count) == len(lines)


def _resolve_ten_q_virtual_section_replacement_end(
    *,
    full_text: str,
    top_level_sections: list[_VirtualSection],
    current_index: int,
    replacement_starts: dict[tuple[str, str], int],
    replacement_start: int,
) -> Optional[int]:
    """为替代正文起点选择合理结束位置。

    Args:
        full_text: 文档全文。
        top_level_sections: 顶层章节列表。
        current_index: 当前章节索引。
        replacement_starts: 已计算出的替代起点。
        replacement_start: 当前章节的替代起点。

    Returns:
        合理结束位置；无法确定时返回 ``None``。

    Raises:
        RuntimeError: 计算失败时抛出。
    """

    current_section = top_level_sections[current_index]
    next_boundary: Optional[int] = None
    for index, other_section in enumerate(top_level_sections):
        if index == current_index:
            continue
        other_key = _parse_ten_q_virtual_section_key(other_section.title)
        other_start = other_section.start
        if other_key is not None:
            other_start = replacement_starts.get(other_key, other_start)
        if other_start <= replacement_start:
            continue
        if next_boundary is None or other_start < next_boundary:
            next_boundary = other_start

    if next_boundary is not None:
        return next_boundary
    if current_section.end > replacement_start:
        return current_section.end
    return len(full_text)


def _should_apply_ten_q_virtual_section_replacement(
    *,
    current_content: str,
    replacement_content: str,
    allow_toc_boundary_replacement: bool,
) -> bool:
    """判断候选正文是否显著优于当前内容。

    Args:
        current_content: 当前章节内容。
        replacement_content: 候选替代内容。
        allow_toc_boundary_replacement: 当前章节若起点落在 TOC，则允许“更短但更准”的替换。

    Returns:
        候选内容明显更像正文时返回 ``True``。

    Raises:
        RuntimeError: 判定失败时抛出。
    """

    replacement_words = len(str(replacement_content or "").split())
    if replacement_words < 20:
        return False

    current_words = len(str(current_content or "").split())
    if allow_toc_boundary_replacement:
        return True
    if current_words <= 0:
        return True
    return replacement_words >= max(current_words + 20, int(current_words * 1.5))


def _repair_part_i_key_items_with_heading_fallback(
    *,
    full_text: str,
    part_i_selected: list[tuple[str, int]],
    start_at: int,
    end_at: Optional[int],
) -> list[tuple[str, int]]:
    """修复 10-Q Part I 关键 Item（1-4）的缺失或目录污染。

    场景：
    - 正文使用 ``Financial Statements`` / ``Management's Discussion``
      纯标题，不含 ``Item 1/2`` 前缀；
    - ``Item 3/4`` 在正文只保留标准 heading，原始 marker 落在目录区。

    Args:
        full_text: 文档全文。
        part_i_selected: 已选中的 Part I Item 列表。
        start_at: Part I 扫描起点。
        end_at: Part I 扫描终点（通常是 Part II 锚定）。

    Returns:
        修复后的 Part I Item 列表（按法定顺序输出）。

    Raises:
        RuntimeError: 修复失败时抛出。
    """

    marker_map = {token: position for token, position in part_i_selected}
    boundary_start = max(0, int(start_at))
    boundary_end = len(full_text) if end_at is None else max(boundary_start, int(end_at))

    marker_map = _repair_ten_q_items_with_heading_fallback(
        full_text=full_text,
        marker_map=marker_map,
        tokens=("1", "2", "3", "4"),
        start_at=boundary_start,
        end_at=boundary_end,
        heading_patterns_map=_TEN_Q_PART_I_HEADING_FALLBACK_PATTERNS,
        expected_keywords_map=_TEN_Q_PART_I_EXPECTED_KEYWORDS,
        cross_reference_tokens={"1", "2"},
        non_standalone_heading_tokens={"2"},
    )

    marker_map = _repair_item_1_with_structured_heading_fallback(
        full_text=full_text,
        marker_map=marker_map,
        start_at=boundary_start,
        end_at=boundary_end,
    )

    repaired: list[tuple[str, int]] = []
    for token in _TEN_Q_PART_I_ITEM_ORDER:
        position = marker_map.get(token)
        if position is None:
            continue
        repaired.append((token, position))
    return repaired


def _repair_part_ii_key_items_with_heading_fallback(
    *,
    full_text: str,
    part_ii_selected: list[tuple[str, int]],
    start_at: int,
) -> list[tuple[str, int]]:
    """修复 10-Q Part II 关键 Item（5/6）的缺失或目录污染。

    Args:
        full_text: 文档全文。
        part_ii_selected: 已选中的 Part II Item 列表。
        start_at: Part II 扫描起点。

    Returns:
        修复后的 Part II Item 列表（按法定顺序输出）。

    Raises:
        RuntimeError: 修复失败时抛出。
    """

    marker_map = {token: position for token, position in part_ii_selected}
    marker_map = _repair_ten_q_items_with_heading_fallback(
        full_text=full_text,
        marker_map=marker_map,
        tokens=("5", "6"),
        start_at=max(0, int(start_at)),
        end_at=len(full_text),
        heading_patterns_map={
            "5": _TEN_Q_DEFAULT_HEADING_PATTERNS.get(("II", "5"), ()),
            "6": _TEN_Q_DEFAULT_HEADING_PATTERNS.get(("II", "6"), ()),
        },
        expected_keywords_map={
            "5": ("other information",),
            "6": ("exhibit",),
        },
        cross_reference_tokens=set(),
        non_standalone_heading_tokens=set(),
    )

    repaired: list[tuple[str, int]] = []
    for token in _TEN_Q_PART_II_ITEM_ORDER:
        position = marker_map.get(token)
        if position is None:
            continue
        repaired.append((token, position))
    return repaired


def _repair_ten_q_items_with_heading_fallback(
    *,
    full_text: str,
    marker_map: dict[str, int],
    tokens: tuple[str, ...],
    start_at: int,
    end_at: int,
    heading_patterns_map: dict[str, tuple[re.Pattern[str], ...]],
    expected_keywords_map: dict[str, tuple[str, ...]],
    cross_reference_tokens: set[str],
    non_standalone_heading_tokens: set[str],
) -> dict[str, int]:
    """按 heading fallback 批量修复 10-Q item 锚点。

    Args:
        full_text: 文档全文。
        marker_map: 当前 token -> position 映射。
        tokens: 需要修复的 item token 顺序。
        start_at: 搜索起点。
        end_at: 搜索终点。
        heading_patterns_map: item -> heading 正则集合映射。
        expected_keywords_map: item -> 预期关键词映射。
        cross_reference_tokens: 需要排除交叉引用句的 item 集合。
        non_standalone_heading_tokens: 允许命中“非独立标题行”的 item 集合。

    Returns:
        修复后的 token -> position 映射。

    Raises:
        RuntimeError: 修复失败时抛出。
    """

    repaired_marker_map = dict(marker_map)
    boundary_start = max(0, int(start_at))
    boundary_end = max(boundary_start, int(end_at))

    for token in tokens:
        current_pos = repaired_marker_map.get(token)
        needs_fallback = current_pos is None
        if current_pos is not None:
            if _has_ten_q_toc_like_start(full_text=full_text, position=current_pos):
                needs_fallback = True
            elif token in cross_reference_tokens and _looks_like_part_i_item_cross_reference(
                full_text, token, current_pos
            ):
                # 避免命中正文中的“in/to Part I, Item N”交叉引用句。
                needs_fallback = True
            elif not _matches_ten_q_expected_heading(
                full_text=full_text,
                expected_keywords_map=expected_keywords_map,
                token=token,
                position=current_pos,
            ):
                needs_fallback = True
        if not needs_fallback:
            continue

        patterns = heading_patterns_map.get(token, ())
        fallback_pos = _find_first_pattern_position_in_range(
            full_text=full_text,
            patterns=patterns,
            start_at=boundary_start,
            end_at=boundary_end,
            require_standalone_heading=token not in non_standalone_heading_tokens,
        )
        if fallback_pos is None:
            continue
        repaired_marker_map[token] = fallback_pos

    return repaired_marker_map


def _repair_item_1_with_structured_heading_fallback(
    *,
    full_text: str,
    marker_map: dict[str, int],
    start_at: int,
    end_at: int,
) -> dict[str, int]:
    """使用结构化财务报表标题修复 Part I Item 1 锚点。

    当 ``Item 1/2`` 都误落在目录摘要行时，``Item 1`` 常因与 ``Item 2``
    间距过短在后续切分阶段被吞掉。该修复基于 SEC 10-Q 正文常见标题
    （如 ``Condensed Consolidated Financial Statements``）回退到正文锚点。

    Args:
        full_text: 文档全文。
        marker_map: 当前 token -> position 映射。
        start_at: Part I 扫描起点。
        end_at: Part I 扫描终点。

    Returns:
        修复后的 token -> position 映射。

    Raises:
        RuntimeError: 修复失败时抛出。
    """

    item_1_position = marker_map.get("1")
    item_2_position = marker_map.get("2")

    needs_item_1_repair = item_1_position is None
    if item_1_position is not None and item_2_position is not None:
        if abs(item_2_position - item_1_position) < _MIN_PART_I_KEY_ITEM_GAP_CHARS:
            needs_item_1_repair = True
    if not needs_item_1_repair:
        return marker_map

    fallback_position = _find_item_1_structured_heading_position(
        full_text=full_text,
        start_at=start_at,
        end_at=end_at,
        item_2_position=item_2_position,
    )
    if fallback_position is None:
        return marker_map

    marker_map["1"] = fallback_position
    return marker_map


def _find_item_1_structured_heading_position(
    *,
    full_text: str,
    start_at: int,
    end_at: int,
    item_2_position: Optional[int],
) -> Optional[int]:
    """在 Part I 范围内查找 Item 1 的结构化正文标题位置。

    Args:
        full_text: 文档全文。
        start_at: 扫描起点。
        end_at: 扫描终点。
        item_2_position: 可选 Item 2 位置，用于优先选择其前的 Item 1 锚点。

    Returns:
        命中位置；未命中返回 ``None``。

    Raises:
        RuntimeError: 扫描失败时抛出。
    """

    lower = max(0, int(start_at))
    upper = max(lower, int(end_at))
    valid_positions: list[int] = []

    for pattern in _TEN_Q_ITEM_1_STRUCTURED_HEADING_PATTERNS:
        for match in pattern.finditer(full_text, pos=lower, endpos=upper):
            position = int(match.start())
            if _looks_like_toc_page_line(full_text, position):
                continue
            if _looks_like_part_i_toc_summary(full_text, position):
                continue
            if _looks_like_inline_toc_snippet(full_text, position):
                continue
            valid_positions.append(position)

    if not valid_positions:
        return None

    ordered_positions = sorted(set(valid_positions))
    if item_2_position is None:
        return ordered_positions[0]

    preferred_before_item_2 = [
        position
        for position in ordered_positions
        if position + _MIN_PART_I_KEY_ITEM_GAP_CHARS <= int(item_2_position)
    ]
    if preferred_before_item_2:
        # 优先选择最靠近 Item 2 且仍在其之前的正文锚点。
        return preferred_before_item_2[-1]
    return ordered_positions[0]


def _find_first_pattern_position_in_range(
    *,
    full_text: str,
    patterns: tuple[re.Pattern[str], ...],
    start_at: int,
    end_at: int,
    require_standalone_heading: bool = True,
) -> Optional[int]:
    """在指定范围内查找候选标题正则的最早命中位置。

    Args:
        full_text: 文档全文。
        patterns: 候选标题正则列表。
        start_at: 起始位置（含）。
        end_at: 终止位置（不含）。
        require_standalone_heading: 是否要求命中位于独立标题语境。

    Returns:
        最早命中位置；未命中返回 ``None``。

    Raises:
        RuntimeError: 扫描失败时抛出。
    """

    best_position: Optional[int] = None
    best_toc_like_position: Optional[int] = None
    lower = max(0, int(start_at))
    upper = max(lower, int(end_at))
    for pattern in patterns:
        for match in pattern.finditer(full_text, pos=lower, endpos=upper):
            matched_text = str(match.group(0) or "")
            leading_whitespace = len(matched_text) - len(matched_text.lstrip())
            position = int(match.start()) + leading_whitespace
            if _looks_like_toc_page_line(full_text, position):
                if best_toc_like_position is None or position < best_toc_like_position:
                    best_toc_like_position = position
                continue
            if _looks_like_part_i_toc_summary(full_text, position):
                if best_toc_like_position is None or position < best_toc_like_position:
                    best_toc_like_position = position
                continue
            if _looks_like_inline_toc_snippet(full_text, position):
                if best_toc_like_position is None or position < best_toc_like_position:
                    best_toc_like_position = position
                continue
            if require_standalone_heading and not _looks_like_ten_q_standalone_heading_context(
                full_text=full_text,
                position=position,
                matched_text=matched_text,
            ):
                continue
            if best_position is None or position < best_position:
                best_position = position
    if best_position is not None:
        return best_position
    return best_toc_like_position


def _looks_like_part_i_toc_summary(full_text: str, position: int) -> bool:
    """判断命中点是否落在 10-Q Part I 目录摘要行。

    Args:
        full_text: 文档全文。
        position: 待判断位置。

    Returns:
        命中目录摘要返回 ``True``，否则返回 ``False``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    start = max(0, int(position) - 80)
    end = min(len(full_text), int(position) + 420)
    snippet = full_text[start:end]
    return _TEN_Q_PART_I_TOC_SUMMARY_PATTERN.search(snippet) is not None


def _looks_like_part_i_item_cross_reference(full_text: str, token: str, position: int) -> bool:
    """判断命中点是否为 Part I Item 交叉引用句而非章节标题。

    典型误命中示例：
    ``... incorporated by reference to Part I, Item 2: \"Management's Discussion ...\"``。
    该类文本包含 Item 关键字但并非章节边界，需触发 fallback 寻找真正标题。

    Args:
        full_text: 文档全文。
        token: Item token（当前仅 ``"1"`` / ``"2"`` 使用该判定）。
        position: 待判断位置。

    Returns:
        若命中交叉引用句返回 ``True``，否则返回 ``False``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    if token not in {"1", "2"}:
        return False

    start = max(0, int(position) - 140)
    end = min(len(full_text), int(position) + 220)
    snippet = full_text[start:end]
    local_position = int(position) - start

    for match in _PART_I_ITEM_CROSS_REFERENCE_PATTERN.finditer(snippet):
        matched_token = str(match.group(1) or "").upper()
        if matched_token != token.upper():
            continue
        # 仅当命中位置落在交叉引用短语附近时才判定为交叉引用。
        if match.start() <= local_position <= match.end() + 8:
            return True
    return False


def _matches_ten_q_expected_heading(
    *,
    full_text: str,
    expected_keywords_map: dict[str, tuple[str, ...]],
    token: str,
    position: int,
) -> bool:
    """判断 10-Q Item 是否命中预期标题语义。

    Args:
        full_text: 文档全文。
        expected_keywords_map: item -> 预期关键词映射。
        token: Item token。
        position: marker 位置。

    Returns:
        若命中位置片段包含该 Item 的预期关键词则返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    expected = expected_keywords_map.get(token)
    if not expected:
        return True

    start = max(0, min(len(full_text), int(position)))
    snippet = full_text[start : min(len(full_text), start + 240)].lower()
    return all(keyword in snippet for keyword in expected)


def _matches_part_i_expected_heading(full_text: str, token: str, position: int) -> bool:
    """兼容旧接口，判断 Part I Item 是否命中预期标题语义。

    Args:
        full_text: 文档全文。
        token: Item token。
        position: marker 位置。

    Returns:
        若命中位置片段包含该 Item 的预期关键词则返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    return _matches_ten_q_expected_heading(
        full_text=full_text,
        expected_keywords_map=_TEN_Q_PART_I_EXPECTED_KEYWORDS,
        token=token,
        position=position,
    )


def _looks_like_toc_page_line(full_text: str, position: int) -> bool:
    """10-Q 版目录页码行判断，委托共享实现。"""
    return _looks_like_toc_page_line_generic(
        full_text, position, _TOC_PAGE_LINE_PATTERN, _TOC_PAGE_SNIPPET_PATTERN
    )
