"""SEC 年报/季报类表单处理器公共能力。

本模块提供 10-K/10-Q/20-F 专项处理器共享的能力，包括：
- 报告类表单标准化；
- 基于虚拟章节的通用切分基座；
- TOC 去噪 + 顺序 Item 标记选择工具。
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, ClassVar, Optional

from bs4 import BeautifulSoup
import pandas as pd

from dayu.documents.processors.source import Source

from dayu.documents.processors.text_utils import (
    PREVIEW_MAX_CHARS as _PREVIEW_MAX_CHARS,
    normalize_whitespace as _normalize_whitespace,
)

from dayu.fins.domain.filing_semantics import normalize_sec_form_type_for_matching as _parse_report_sec_form
from .sec_form_section_common import (
    _VirtualSection,
    _VirtualSectionProcessorMixin,
    _format_section_ref,
    _normalize_optional_string,
    _trim_trailing_page_locator,
    _trim_trailing_part_heading,
)
from .sec_processor import SecProcessor
from .sec_section_build import (
    _build_section_title,
    _iter_sections,
    _safe_section_text,
)
from .sec_table_extraction import _safe_table_dataframe
from .financial_base import FinancialMeta, FinancialStatementResult
from .html_financial_statement_common import (
    build_html_statement_result_from_tables as _build_html_statement_result_from_tables,
)
from .report_form_financial_statement_common import (
    REPORT_FORM_SUPPORTED_STATEMENT_TYPES,
    select_report_statement_tables as _select_report_statement_tables,
    should_apply_report_statement_html_fallback as _should_apply_report_statement_html_fallback,
)

_TABLE_OF_CONTENTS_TOKEN = "table of contents"
_TABLE_OF_CONTENTS_CUTOFF_BUFFER_CHARS = 1500
_TOC_START_PENALTY_TOLERANCE_CHARS = 500
_LATE_NOTES_TOC_LOOKBACK_CHARS = 320
_LATE_NOTES_TOC_CONTEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bnotes?\s+to\s+(?:the\s+)?consolidated\s+financial\s+statements?\b"),
    re.compile(r"(?i)\bnotes?\s+to\s+financial\s+statements?\b"),
)

# ToC 条目自适应检测参数
# 相邻 marker 之间 span 低于此阈值视为 ToC 条目（标题 + 页码，通常 < 300 字符）
_TOC_ENTRY_MAX_SPAN_CHARS = 500
# inter-marker span 中"短 span"占比 ≥ 此比例时判定为 ToC 区域
_TOC_SHORT_SPAN_RATIO = 0.8
# 从文档开头起，连续短 span 数 ≥ 此值时判定为 ToC 列表区域
_TOC_MIN_CONSECUTIVE_SHORT_SPANS = 5
# 自适应 ToC 跳过最大重试次数（防止无限循环）
_MAX_TOC_SKIP_RETRIES = 3
# 部分 ToC 检测：连续短 span 数量下界（至少 2 个连续短 span + 戏剧性跳跃才判定为部分 ToC）
_PARTIAL_TOC_MIN_CONSECUTIVE = 2
# 部分 ToC 检测：跳跃倍率阈值——下一个 span 是连续短 span 最大值的 N 倍以上视为戏剧性跳跃
_PARTIAL_TOC_JUMP_RATIO = 50
# 行内交叉引用检测：SEC 20-F/10-K 正文中常含 "see Item 4. Title—Subsection—Detail"
# 此类引用不是真实 heading，应跳过。最小 section span 低于此值时触发重定位检查
_INLINE_REF_MIN_SPAN_CHARS = 3000
_INLINE_REF_NEXT_WORD_STOPWORDS = frozenset(
    {
        "in",
        "and",
        "or",
        "of",
        "to",
        "for",
        "from",
        "under",
        "above",
        "below",
        "herein",
        "therein",
        "within",
        "with",
        "on",
        "at",
        "as",
        "by",
    }
)
_INLINE_TOC_PAGE_TOKEN_PATTERN = re.compile(r"\b\d{1,3}(?:\s*[–—-]\s*\d{1,3})?\b")
_INLINE_TOC_PAGE_RANGE_PATTERN = re.compile(r"\b\d{1,3}\s*[–—-]\s*\d{1,3}\b")
_INLINE_TOC_NEXT_HEADING_PATTERN = re.compile(
    r"\b(?:item\s+(?:16[a-j]|(?:1[0-9]|[1-9])[a-z]?)|part\s+(?:i{1,3}|iv))\b",
    re.IGNORECASE,
)
_INLINE_TOC_HEADING_WITH_PAGE_PATTERN = re.compile(
    r"(?:^|\b)(?:(?i:item\s+(?:16[a-j]|(?:1[0-9]|[1-9])[a-z]?))\s+)?"
    r"[A-Za-z][A-Za-z0-9 '&,/\-]{8,}"
    r"\s+\d{1,3}(?:\s*[–—-]\s*\d{1,3})?"
    r"\s+(?:[A-Z][A-Za-z]{2,}|(?i:item\s+(?:16[a-j]|(?:1[0-9]|[1-9])[a-z]?))|(?i:part\s+(?:i{1,3}|iv)))",
)
_LINE_PRESERVING_BLOCK_TAGS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "caption",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
)
_LINE_PRESERVING_SKIP_TAGS = frozenset({"script", "style", "noscript"})
_LINE_PRESERVING_WHITESPACE_RE = re.compile(r"[^\S\n]+")
_LINE_PRESERVING_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


class _LinePreservingHtmlTextExtractor(HTMLParser):
    """流式提取 HTML 文本并尽量保留标题/表格换行边界。

    该提取器用于替代 ``BeautifulSoup(...).get_text(separator="\\n")`` 的全量 DOM
    构建路径，避免在超大 20-F/iXBRL 文档上产生高额 CPU 和内存开销。
    """

    def __init__(self) -> None:
        """初始化提取器。

        Args:
            无。

        Returns:
            无。

        Raises:
            RuntimeError: 初始化失败时抛出。
        """

        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0
        self._last_was_newline = True

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, Optional[str]]],
    ) -> None:
        """处理开始标签。

        Args:
            tag: 标签名。
            attrs: 标签属性；仅为兼容 ``HTMLParser`` 签名，当前不使用。

        Returns:
            无。

        Raises:
            RuntimeError: 处理失败时抛出。
        """

        del attrs
        normalized_tag = str(tag or "").lower()
        if normalized_tag in _LINE_PRESERVING_SKIP_TAGS:
            self._skip_depth += 1
            return
        if normalized_tag in _LINE_PRESERVING_BLOCK_TAGS:
            self._append_newline()

    def handle_endtag(self, tag: str) -> None:
        """处理结束标签。

        Args:
            tag: 标签名。

        Returns:
            无。

        Raises:
            RuntimeError: 处理失败时抛出。
        """

        normalized_tag = str(tag or "").lower()
        if normalized_tag in _LINE_PRESERVING_SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if normalized_tag in _LINE_PRESERVING_BLOCK_TAGS:
            self._append_newline()

    def handle_data(self, data: str) -> None:
        """处理文本节点。

        Args:
            data: 原始文本。

        Returns:
            无。

        Raises:
            RuntimeError: 处理失败时抛出。
        """

        if self._skip_depth > 0:
            return
        normalized = _normalize_line_preserving_chunk(data)
        if not normalized:
            return
        self._parts.append(normalized)
        self._last_was_newline = normalized.endswith("\n")

    def get_text(self) -> str:
        """返回规范化后的文本结果。

        Args:
            无。

        Returns:
            保留主要换行边界的纯文本。

        Raises:
            RuntimeError: 生成失败时抛出。
        """

        joined = "".join(self._parts).replace("\r\n", "\n").replace("\r", "\n")
        collapsed = _LINE_PRESERVING_MULTI_NEWLINE_RE.sub("\n\n", joined)
        lines = [_LINE_PRESERVING_WHITESPACE_RE.sub(" ", line).strip() for line in collapsed.split("\n")]
        return "\n".join(line for line in lines if line)

    def _append_newline(self) -> None:
        """在需要时追加换行，避免重复空行爆炸。

        Args:
            无。

        Returns:
            无。

        Raises:
            RuntimeError: 追加失败时抛出。
        """

        if self._skip_depth > 0 or self._last_was_newline:
            return
        self._parts.append("\n")
        self._last_was_newline = True


def _normalize_line_preserving_chunk(text: str) -> str:
    """规范化流式 HTML 文本块。

    Args:
        text: 原始文本块。

    Returns:
        去除无意义空白后的文本块；若为空则返回空字符串。

    Raises:
        RuntimeError: 规范化失败时抛出。
    """

    normalized = str(text or "").replace("\xa0", " ")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = _LINE_PRESERVING_WHITESPACE_RE.sub(" ", normalized)
    return normalized


class _BaseSecReportFormProcessor(_VirtualSectionProcessorMixin, SecProcessor):
    """SEC 报告类表单处理器基类。"""

    _SUPPORTED_FORMS: ClassVar[frozenset[str]] = frozenset()
    _MIN_VIRTUAL_SECTIONS: ClassVar[int] = 3
    # 性能优化：报告类处理器的虚拟章节完全基于 document.text() + markers 构建，
    # 不使用 _build_sections 产出的逐 section 数据，因此跳过昂贵的逐 section
    # .tables()/.text()/get_sec_section_info() 调用，直接将全文作为单 section 返回。
    _ENABLE_FAST_SECTION_BUILD = True
    _FAST_SECTION_BUILD_SINGLE_FULL_TEXT = True

    def __init__(
        self,
        source: Source,
        *,
        form_type: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> None:
        """初始化处理器。

        Args:
            source: 文档来源抽象。
            form_type: 可选表单类型。
            media_type: 可选媒体类型。

        Returns:
            无。

        Raises:
            ValueError: 参数非法时抛出。
            RuntimeError: 解析失败时抛出。
        """

        super().__init__(source=source, form_type=form_type, media_type=media_type)
        # 报告类处理器默认启用虚拟章节切分，标记不足时自动回退 SecProcessor。
        self._initialize_virtual_sections(min_sections=self._MIN_VIRTUAL_SECTIONS)

    @classmethod
    def supports(
        cls,
        source: Source,
        *,
        form_type: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> bool:
        """判断是否支持处理指定报告类表单。

        Args:
            source: 文档来源抽象。
            form_type: 可选表单类型。
            media_type: 可选媒体类型。

        Returns:
            是否支持。

        Raises:
            OSError: 文件访问失败时可能抛出。
        """

        normalized_form = _parse_report_sec_form(form_type)
        if normalized_form not in cls._SUPPORTED_FORMS:
            return False
        # 复用 SecProcessor 的文件类型与底层可解析能力判断。
        return SecProcessor.supports(
            source,
            form_type=normalized_form,
            media_type=media_type,
        )

    def _build_virtual_sections_from_base(self) -> list[_VirtualSection]:
        """从父类章节构建一级虚拟章节（覆盖 mixin 默认实现）。

        当 ``single_full_text`` 优化启用时，基类 ``_build_sections`` 仅产出
        1 个全文 section，导致父类 ``_build_virtual_sections_from_base`` 的
        回退路径只能生成 1 个大虚拟章节，质量劣于 edgartools 多 section 输出。

        本覆盖方法在检测到 single_full_text + 基类仅 1 section 时，
        **惰性重建** edgartools sections——仅在 marker 不足触发回退时
        才执行昂贵的逐 section 解析，绝大多数文档不会进入此路径。

        Args:
            无。

        Returns:
            一级虚拟章节列表。

        Raises:
            RuntimeError: 构建失败时抛出。
        """

        # 非 single_full_text 或基类已有多 section 时，直接走通用路径
        if not self._should_use_single_full_text_section() or len(self._sections) != 1:
            return _VirtualSectionProcessorMixin._build_virtual_sections_from_base(self)

        # single_full_text 回退：惰性从 edgartools sections 重建
        return _rebuild_virtual_sections_from_edgartools(self._document)

    def get_financial_statement(
        self,
        statement_type: str,
        financials: Optional[dict[str, Any]] = None,
        *,
        meta: Optional[FinancialMeta] = None,
    ) -> FinancialStatementResult:
        """获取报告类财务报表，支持 XBRL 失败后的 HTML fallback。

        Args:
            statement_type: 报表类型。
            financials: 预留财务缓存，当前未使用。
            meta: 预留元信息，当前未使用。

        Returns:
            财务报表结果。

        Raises:
            RuntimeError: 读取失败时抛出。
        """

        result = super().get_financial_statement(
            statement_type=statement_type,
            financials=financials,
            meta=meta,
        )
        normalized_statement_type = statement_type.strip().lower()
        if normalized_statement_type not in REPORT_FORM_SUPPORTED_STATEMENT_TYPES:
            return result
        if not _should_apply_report_statement_html_fallback(result.get("reason")):
            return result

        candidate_tables = self._get_report_statement_tables(normalized_statement_type)
        if not candidate_tables:
            return result

        extracted = self._build_html_statement_from_tables(
            statement_type=normalized_statement_type,
            tables=candidate_tables,
        )
        if extracted is None:
            result["reason"] = "low_confidence_extraction"
            return result
        return extracted

    def _get_report_statement_tables(self, statement_type: str) -> list[Any]:
        """获取报告类表单的财务报表候选表。

        Args:
            statement_type: 目标报表类型。

        Returns:
            候选表格列表。

        Raises:
            RuntimeError: 筛选失败时抛出。
        """

        return _select_report_statement_tables(
            statement_type=statement_type,
            tables=list(getattr(self, "_tables", [])),
            parse_table_dataframe=_parse_report_table_dataframe_from_sec,
        )

    def _build_html_statement_from_tables(
        self,
        *,
        statement_type: str,
        tables: list[Any],
    ) -> Optional[FinancialStatementResult]:
        """从候选 HTML 表中构建结构化财务报表。

        Args:
            statement_type: 目标报表类型。
            tables: 候选表格列表。

        Returns:
            结构化财务报表结果；失败时返回 ``None``。

        Raises:
            RuntimeError: 构建失败时抛出。
        """

        return _build_html_statement_result_from_tables(
            statement_type=statement_type,
            tables=tables,
            parse_table_dataframe=_parse_report_table_dataframe_from_sec,
        )


def _rebuild_virtual_sections_from_edgartools(document: object) -> list[_VirtualSection]:
    """从 edgartools sections 惰性重建虚拟章节。

    当 ``single_full_text`` 优化启用但 marker 检测不足时调用。
    直接读取 edgartools ``document.sections``，跳过基类 ``_build_sections``
    的指纹/锚点计算，仅提取文本和标题以构建虚拟章节。

    Args:
        document: edgartools 文档对象。

    Returns:
        虚拟章节列表。

    Raises:
        RuntimeError: edgartools 解析失败时抛出。
    """

    section_items = _iter_sections(document)
    if not section_items:
        return []

    virtual_sections: list[_VirtualSection] = []
    for index, (section_key, section_obj) in enumerate(section_items, start=1):
        content = _normalize_whitespace(_safe_section_text(section_obj))
        if not content:
            continue
        title = _normalize_optional_string(
            _build_section_title(section_key=section_key, section_obj=section_obj)
        )
        content = _trim_trailing_part_heading(content)
        content = _trim_trailing_page_locator(content, title)
        if not content:
            continue
        preview = _normalize_whitespace(content)[:_PREVIEW_MAX_CHARS]
        virtual_sections.append(
            _VirtualSection(
                ref=_format_section_ref(index),
                title=title,
                content=content,
                preview=preview,
                table_refs=[],
                level=1,
                parent_ref=None,
                child_refs=[],
                start=0,
                end=len(content),
            )
        )
    return virtual_sections


def _parse_report_table_dataframe_from_sec(table: Any) -> Optional[pd.DataFrame]:
    """从 SecProcessor 表格对象安全提取 DataFrame。

    Args:
        table: 内部表格对象。

    Returns:
        DataFrame 副本；不可用时返回 ``None``。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    precomputed_dataframe = getattr(table, "dataframe", None)
    if isinstance(precomputed_dataframe, pd.DataFrame):
        return precomputed_dataframe.copy()

    table_obj = getattr(table, "table_obj", None)
    if table_obj is None:
        return None
    dataframe = _safe_table_dataframe(table_obj)
    if dataframe is None:
        return None
    return dataframe.copy()


def _extract_source_text_preserving_lines(source: Source) -> str:
    """直接从源 HTML 提取保留换行结构的文本。

    Args:
        source: 文档来源抽象。

    Returns:
        使用 DOM 顺序和换行分隔提取的文本；失败时返回空字符串。

    Raises:
        RuntimeError: 读取失败时抛出。
    """

    try:
        source_path = source.materialize(suffix=".html")
    except Exception:
        return ""
    path = Path(source_path)
    try:
        raw_html = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    if not raw_html.strip():
        return ""
    parser = _LinePreservingHtmlTextExtractor()
    parser.feed(raw_html)
    parser.close()
    return parser.get_text()


def _find_table_of_contents_cutoff(full_text: str) -> int:
    """计算 TOC 之后的建议切分起点。

    Args:
        full_text: 文档全文。

    Returns:
        切分起始位置；未识别 TOC 时返回 0。

    Raises:
        RuntimeError: 计算失败时抛出。
    """

    lowered = str(full_text or "").lower()
    toc_index = lowered.find(_TABLE_OF_CONTENTS_TOKEN)
    if toc_index < 0:
        return 0
    context_start = max(0, toc_index - _LATE_NOTES_TOC_LOOKBACK_CHARS)
    toc_context = full_text[context_start:toc_index]
    if any(pattern.search(toc_context) is not None for pattern in _LATE_NOTES_TOC_CONTEXT_PATTERNS):
        return 0
    return max(0, toc_index + _TABLE_OF_CONTENTS_CUTOFF_BUFFER_CHARS)


def _looks_like_inline_toc_snippet(
    full_text: str,
    position: int,
    *,
    window_chars: int = 260,
    max_first_page_offset: int = 180,
) -> bool:
    """判断给定位置是否落在“单行目录条目”片段。

    真实场景中，部分 iXBRL 文本会被压平到单行，目录条目呈现为：
    ``Management ... 7 Item 7A ...``。这类片段没有换行边界，
    仅靠“行首 + 页码”规则会漏检。

    判定策略：
    1. 片段直接包含 ``table of contents``；
    2. 片段前部出现 2 个以上页码 token（典型目录连续页码）；
    3. 页码 token 后快速出现下一章节锚点（``Item/Part``）；
    4. 命中“标题 + 页码 + 下一标题”紧凑模式。

    Args:
        full_text: 文档全文。
        position: 待判断起始位置。
        window_chars: 片段窗口长度。
        max_first_page_offset: 首个页码 token 允许的最大偏移。

    Returns:
        若片段表现为单行目录结构则返回 ``True``。

    Raises:
        RuntimeError: 判定失败时抛出。
    """

    start = max(0, min(len(full_text), int(position)))
    end = min(len(full_text), start + max(64, int(window_chars)))
    snippet_raw = full_text[start:end]
    if not snippet_raw:
        return False

    snippet = " ".join(snippet_raw.split())
    lowered = snippet.lower()
    if _TABLE_OF_CONTENTS_TOKEN in lowered:
        return True

    page_matches = list(_INLINE_TOC_PAGE_TOKEN_PATTERN.finditer(snippet))
    if not page_matches:
        return False
    if page_matches[0].start() > max(0, int(max_first_page_offset)):
        return False
    if _INLINE_TOC_PAGE_RANGE_PATTERN.search(snippet) is not None:
        return True

    suffix = snippet[page_matches[0].end() : page_matches[0].end() + 160]
    if _INLINE_TOC_NEXT_HEADING_PATTERN.search(suffix) is not None:
        return True
    return _INLINE_TOC_HEADING_WITH_PAGE_PATTERN.search(snippet) is not None


# ── 跨 Form 共享的目录页码行判断 ──────────────────────────────

_TOC_SNIPPET_MAX_CHARS = 260
"""目录片段窗口长度上限（字符），用于判断 TOC page line。"""


def _looks_like_toc_page_line_generic(
    full_text: str,
    position: int,
    toc_page_line_pattern: re.Pattern[str],
    toc_page_snippet_pattern: re.Pattern[str],
) -> bool:
    """判断给定位置是否落在目录页码行（参数化版本）。

    该函数抽取自 10-K / 10-Q / 20-F 三处相同逻辑，
    各 Form 仅在 ``toc_page_line_pattern`` / ``toc_page_snippet_pattern``
    上存在差异，核心判断逻辑完全一致。

    Args:
        full_text: 文档全文。
        position: 待判断位置。
        toc_page_line_pattern: 行级目录页码正则（匹配单行"标题+页码"）。
        toc_page_snippet_pattern: 片段级目录页码正则（匹配跨行目录片段）。

    Returns:
        若命中"标题+页码"目录行模式则返回 ``True``。
    """

    start = max(0, min(len(full_text), int(position)))
    line_end = full_text.find("\n", start)
    if line_end < 0:
        line_end = min(len(full_text), start + _TOC_SNIPPET_MAX_CHARS)
    line_text = full_text[start:line_end].strip()
    if line_text and toc_page_line_pattern.match(line_text) is not None:
        return True

    snippet_end = min(len(full_text), start + _TOC_SNIPPET_MAX_CHARS)
    snippet_text = full_text[start:snippet_end].strip()
    if not snippet_text:
        return False
    if toc_page_snippet_pattern.match(snippet_text) is not None:
        return True
    return _looks_like_inline_toc_snippet(full_text, start)


def _select_ordered_item_markers(
    full_text: str,
    *,
    item_pattern: re.Pattern[str],
    ordered_tokens: tuple[str, ...],
    start_at: int = 0,
    end_at: Optional[int] = None,
) -> list[tuple[str, int]]:
    """按预定义 token 顺序选择 Item 标记。

    Args:
        full_text: 文档全文。
        item_pattern: Item 匹配正则（第一个捕获组应为 Item token）。
        ordered_tokens: 预期顺序 token 列表。
        start_at: 起始扫描位置。
        end_at: 可选终止位置（不含）。

    Returns:
        `(item_token, start_index)` 列表。

    Raises:
        RuntimeError: 选择失败时抛出。
    """

    start_index = max(0, int(start_at))
    if end_at is None:
        end_index = len(full_text)
    else:
        end_index = max(start_index, int(end_at))

    matches: list[tuple[str, int]] = []
    for match in item_pattern.finditer(full_text):
        position = int(match.start())
        if position < start_index or position >= end_index:
            continue
        token_raw = _extract_item_token_from_match(match)
        if not token_raw:
            continue
        matches.append((token_raw, position))
    if not matches:
        return []

    selected: list[tuple[str, int]] = []
    cursor = start_index
    for token in ordered_tokens:
        found_position = _find_item_token_position_after(
            matches=matches,
            full_text=full_text,
            target_token=token,
            cursor=cursor,
            end_at=end_index,
        )
        if found_position is None:
            continue
        selected.append((token, found_position))
        cursor = found_position + 1
    return selected


def _extract_item_token_from_match(match: re.Match[str]) -> str:
    """从正则匹配对象中提取 Item token。

    支持两类模式：
    1. 单捕获组模式（传统 ``group(1)``）；
    2. 多捕获组模式（正则 alternation 为不同写法分别建组），
       自动返回第一个非空捕获组。

    Args:
        match: ``re.finditer`` 产生的匹配对象。

    Returns:
        标准化后的 Item token（大写）；提取失败时返回空字符串。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    group_count = int(getattr(match.re, "groups", 0))
    if group_count <= 0:
        return ""

    for group_index in range(1, group_count + 1):
        value = str(match.group(group_index) or "").strip().upper()
        if value:
            return value
    return ""


def _refine_inline_reference_markers(
    full_text: str,
    selected: list[tuple[str, int]],
    *,
    item_pattern: re.Pattern[str],
    min_span: int = _INLINE_REF_MIN_SPAN_CHARS,
) -> list[tuple[str, int]]:
    """检测并修正行内交叉引用导致的异常短 section。

    SEC 20-F/10-K 正文中常出现引用：
    ``"see Item 4. Information on the Company—C. Organizational Structure—..."``
    贪心游标会错误选中这些行内引用而非真正的章节标题。

    检测策略：对每个选中 marker 计算其到下一个 marker 的 span，若 span
    低于 ``min_span`` 阈值，检查该匹配位置前的文本是否为典型行内上下文
    （前一个非空白字符不是换行符），若是则尝试该 token 在文档中的下一个
    匹配位置。

    此函数是自适应规则——基于"真实标题通常位于行首"的数据特征推断。

    Args:
        full_text: 文档全文。
        selected: 已选中的 ``(item_token, position)`` 列表。
        item_pattern: Item 匹配正则。
        min_span: 异常短 section 阈值。

    Returns:
        修正后的 ``(item_token, position)`` 列表。
    """

    if len(selected) < 2:
        return selected

    # 预收集所有匹配位置用于查找替代 candidate
    all_matches: dict[str, list[int]] = {}
    for match in item_pattern.finditer(full_text):
        token_raw = str(match.group(1) or "").strip().upper()
        if token_raw:
            all_matches.setdefault(token_raw, []).append(int(match.start()))

    refined = list(selected)
    for i in range(len(refined) - 1):
        token, pos = refined[i]
        next_pos = refined[i + 1][1]
        span = next_pos - pos

        if span >= min_span:
            continue

        # span 过短，检查是否为行内交叉引用。
        # 行内引用的前一个非空白字符通常是字母/标点（句子中嵌入），
        # 而真实标题前一个非空白字符通常是换行符或文档起始。
        if not _is_inline_reference_context(full_text, pos):
            continue

        # 查找同 token 的更远 candidate（在当前位置之后、下一个 marker 之前）
        candidates = all_matches.get(token, [])
        # 需要查找 pos < candidate <= next_pos 范围外的更远位置
        # 实际上应查找 max(pos+1, prev_bound) 到 next_next_pos 范围的 candidate
        # 简化：查找不在行内引用上下文中的下一个出现
        relocated = False
        for cand_pos in candidates:
            if cand_pos <= pos:
                continue
            new_span = next_pos - cand_pos if cand_pos < next_pos else 0
            # candidate 不应太靠近下一个 marker（至少要有 min_span/2 间距）
            # 或 candidate 超出 next_pos 范围（此时整个 section 会更长）
            if cand_pos >= next_pos:
                # candidate 超出 next marker，需确保不干扰后续 token 排序
                # 只有当 candidate 位于当前 token 和下一个之间更远处才有效
                # 确保不会与更后面的 marker 冲突
                if i + 2 < len(refined) and cand_pos >= refined[i + 2][1]:
                    continue
            if _is_inline_reference_context(full_text, cand_pos):
                continue
            refined[i] = (token, cand_pos)
            relocated = True
            break

    return refined


def _is_inline_reference_context(full_text: str, pos: int) -> bool:
    """判断给定位置是否处于行内交叉引用上下文。

    通过检查匹配位置前的文本特征判断：真实 heading 通常在行首
    （前一个非空白字符是换行符或不存在），而交叉引用嵌入在句子中。

    Args:
        full_text: 文档全文。
        pos: 匹配起始位置。

    Returns:
        若位置看起来是行内引用上下文则返回 ``True``。
    """

    if pos <= 0:
        return False

    # 向前查找最近的非空白字符
    idx = pos - 1
    while idx >= 0 and full_text[idx] in (" ", "\t", "\xa0"):
        idx -= 1

    if idx < 0:
        # 到达文档起始——视为行首
        return False

    # 行首标志：换行符
    return full_text[idx] != "\n"


def _markers_look_like_toc_entries(
    full_text: str,
    markers: list[tuple[str, int]],
) -> bool:
    """判断选中的 markers 是否位于 ToC（目录）区域。

    便捷包装：内部委托 ``_find_toc_cluster_end``，若返回
    非 ``None`` 则表示检测到 ToC 特征。

    Args:
        full_text: 文档全文。
        markers: 已选中的 ``(item_token, position)`` 列表。

    Returns:
        若检测到 ToC 特征则返回 ``True``。

    Raises:
        RuntimeError: 检测失败时抛出。
    """

    return _find_toc_cluster_end(full_text, markers) is not None


def _find_toc_cluster_end(
    full_text: str,
    markers: list[tuple[str, int]],
    *,
    check_partial_toc: bool = True,
) -> Optional[int]:
    """检测 markers 起始区域的 ToC 列表，返回建议的跳过位置。

    两层自适应检测：

    1. **连续短 span 检测**：从第一个 marker 开始，若连续
       ``_TOC_MIN_CONSECUTIVE_SHORT_SPANS`` 个以上的 inter-marker span
       均低于阈值，说明文档开头有密集的 ToC 列表区域。
       返回 **连续 ToC 区域结束边界**（最后一个 ToC 条目之后），
       而非最后一个 marker 之后——这确保仅跳过 ToC 部分，
       保留后续已在正文的 markers。
    2. **全局比例检测**：若 ≥ 80% 的 inter-marker span 低于阈值，
       整个 marker 序列极可能完全落在 ToC 区域，返回最后一个
       marker 之后的位置。

    Args:
        full_text: 文档全文。
        markers: 已选中的 ``(item_token, position)`` 列表。
        check_partial_toc: 是否启用部分 ToC 检测（检测 1b）。
            在已成功跳过一次完整 ToC 聚簇后，应设为 ``False``
            以避免正文中连续短节（如 "Not Applicable"）被误判。

    Returns:
        建议的重试起始位置；若未检测到 ToC 特征则返回 ``None``。

    Raises:
        RuntimeError: 检测失败时抛出。
    """

    if len(markers) < 3:
        return None

    # 计算相邻 marker 之间的 span（不含最后一个 marker 到文档末尾）
    spans: list[int] = []
    for i in range(len(markers) - 1):
        span = markers[i + 1][1] - markers[i][1]
        spans.append(span)

    if not spans:
        return None

    # 检测 1: 开头连续短 span（ToC 列表特征）
    # ToC 列表是一连串紧凑条目（标题 + 页码），正文中很少出现这种模式
    consecutive_short_from_start = 0
    for s in spans:
        if s < _TOC_ENTRY_MAX_SPAN_CHARS:
            consecutive_short_from_start += 1
        else:
            break
    if consecutive_short_from_start >= _TOC_MIN_CONSECUTIVE_SHORT_SPANS:
        # 连续 ToC 区域的最后一个条目 = markers[consecutive_short_from_start]
        # 跳到该位置之后重试，让 greedy cursor 从正文开始选取
        return markers[consecutive_short_from_start][1] + 1

    # 检测 1b: 部分 ToC + 戏剧性跳跃
    # 场景：前 N 个 marker（N < 5）在 ToC 区域，第 N+1 个 marker 直接落入正文。
    # 典型案例：TSM 20-F 的 "table of contents" 在 XBRL preamble 中，
    # cutoff 位于 ToC 列表之前，导致前 3 个 Item（1、2、3）匹配 ToC 条目，
    # 而 Item 4A 直接跳到 body（span 从 ~100 暴增到 ~117K）。
    # 注意：在已完成一次完整 ToC 跳过后不应再触发此检测，
    # 因为正文中连续短节（如 SONY 20-F 的 "Not Applicable" Items）
    # 会产生相同的短 span + 大跳跃模式，导致误判。
    if (
        check_partial_toc
        and consecutive_short_from_start >= _PARTIAL_TOC_MIN_CONSECUTIVE
        and consecutive_short_from_start < len(spans)
    ):
        max_short_span = max(spans[:consecutive_short_from_start])
        next_span = spans[consecutive_short_from_start]
        if max_short_span > 0 and next_span / max_short_span >= _PARTIAL_TOC_JUMP_RATIO:
            return markers[consecutive_short_from_start][1] + 1

    # 检测 2: 全局短 span 比例（纯 ToC 区域特征）
    short_count = sum(1 for s in spans if s < _TOC_ENTRY_MAX_SPAN_CHARS)
    if short_count / len(spans) >= _TOC_SHORT_SPAN_RATIO:
        # 整个序列都在 ToC → 跳过最后一个 marker
        return markers[-1][1] + 1

    return None


def _skip_toc_like_markers(
    full_text: str,
    *,
    item_pattern: re.Pattern[str],
    ordered_tokens: tuple[str, ...],
    initial_selected: list[tuple[str, int]],
    min_items: int,
    end_at: Optional[int] = None,
) -> list[tuple[str, int]]:
    """若初始 markers 看起来是 ToC 条目，跳过并重新选取正文 markers。

    部分 filing 没有显式的 "Table of Contents" 文本标记，
    但仍然在文档开头有 ToC 列表区域。此函数通过质量校验
    检测并跳过这些隐式 ToC 区域。

    对于 **部分 ToC** 场景（开头若干 marker 在 ToC，后续 marker
    已在正文），仅跳过 ToC 聚簇，而非全部 marker。

    Args:
        full_text: 文档全文。
        item_pattern: Item 匹配正则。
        ordered_tokens: 预期顺序 token 列表。
        initial_selected: 初始选出的 markers。
        min_items: 采用重试结果所需的最小 Item 数。
        end_at: 可选终止位置（不含），限制选取范围。

    Returns:
        若初始 markers 为 ToC 且能找到正文 markers 则返回正文 markers，
        否则返回初始 markers。

    Raises:
        RuntimeError: 选择失败时抛出。
    """

    toc_end = _find_toc_cluster_end(full_text, initial_selected)
    if toc_end is None:
        return initial_selected

    # 从 ToC 结束位置之后重新选取
    # 已成功跳过一次 ToC，后续迭代禁用部分 ToC 检测（check 1b），
    # 避免正文中连续短节（如 "Not Applicable"）被误判为部分 ToC
    start_at = toc_end
    for _ in range(_MAX_TOC_SKIP_RETRIES):
        retry = _select_ordered_item_markers(
            full_text,
            item_pattern=item_pattern,
            ordered_tokens=ordered_tokens,
            start_at=start_at,
            end_at=end_at,
        )
        if len(retry) < min_items:
            break
        next_toc_end = _find_toc_cluster_end(
            full_text, retry, check_partial_toc=False,
        )
        if next_toc_end is None:
            return retry
        # 仍有 ToC 特征 → 继续跳过
        start_at = next_toc_end

    return initial_selected


def _select_ordered_item_markers_after_toc(
    full_text: str,
    *,
    item_pattern: re.Pattern[str],
    ordered_tokens: tuple[str, ...],
    min_items_after_toc: int = 4,
    end_at: Optional[int] = None,
) -> list[tuple[str, int]]:
    """优先在 TOC 之后选择顺序 Item 标记。

    自适应策略：

    1. 定位 "table of contents" 标记，在其后开始选择 Item 标记；
    2. 对每轮选出的标记做 **质量校验**：若 inter-marker span
       绝大多数 < ``_TOC_ENTRY_MAX_SPAN_CHARS``，说明仍停留在
       ToC 列表区域（标题 + 页码），自动跳到最后一个 ToC 条目之后重试；
    3. 至多重试 ``_MAX_TOC_SKIP_RETRIES`` 次，确保不会无限循环；
    4. 兜底回退到从文档开头选取的默认结果。

    Args:
        full_text: 文档全文。
        item_pattern: Item 匹配正则。
        ordered_tokens: 预期顺序 token 列表。
        min_items_after_toc: TOC 后采用结果所需的最小 Item 数。
        end_at: 可选终止位置（不含），限制选取范围。
            典型用途：传入 Part II 锚定位置以防止 Part I Item 选取
            误入 Part II 区域。

    Returns:
        `(item_token, start_index)` 列表。

    Raises:
        RuntimeError: 选择失败时抛出。
    """

    # 兜底：从文档开头的默认选择
    default_selected = _select_ordered_item_markers(
        full_text,
        item_pattern=item_pattern,
        ordered_tokens=ordered_tokens,
        start_at=0,
        end_at=end_at,
    )
    toc_start = _find_table_of_contents_cutoff(full_text)
    if toc_start <= 0:
        # 无 "table of contents" 标记时，仍需检查默认结果是否为 ToC 条目。
        # 部分 filing 有 ToC 区域但无显式 ToC 标题文本。
        skipped = _skip_toc_like_markers(
            full_text,
            item_pattern=item_pattern,
            ordered_tokens=ordered_tokens,
            initial_selected=default_selected,
            min_items=min_items_after_toc,
        )
        # 自适应守护：若“跳过 ToC”结果明显丢失大量 Item，
        # 且默认结果从法定首个 token 开始，优先保留默认结果，
        # 避免把正文开头误判为 ToC（如部分 20-F 文档）。
        result = skipped
        if (
            len(default_selected) >= min_items_after_toc
            and len(default_selected) - len(skipped) >= 2
            and bool(default_selected)
            and default_selected[0][0] == ordered_tokens[0]
        ):
            result = default_selected
        return _refine_inline_reference_markers(
            full_text, result, item_pattern=item_pattern,
        )

    # 自适应迭代：从 toc_start 开始，逐步跳过 ToC 条目
    start_at = toc_start
    best_from_cutoff: Optional[list[tuple[str, int]]] = None
    has_skipped_toc = False  # 标记是否已完成至少一次 ToC 跳过
    for _ in range(_MAX_TOC_SKIP_RETRIES):
        selected = _select_ordered_item_markers(
            full_text,
            item_pattern=item_pattern,
            ordered_tokens=ordered_tokens,
            start_at=start_at,
            end_at=end_at,
        )
        if len(selected) < min_items_after_toc:
            # Item 数量不足，停止重试
            break
        # 已完成 ToC 跳过后禁用部分 ToC 检测（check 1b），
        # 避免正文连续短节被误判
        toc_end = _find_toc_cluster_end(
            full_text, selected,
            check_partial_toc=not has_skipped_toc,
        )
        if toc_end is None:
            # 质量合格：无 ToC 特征

            best_from_cutoff = selected
            break
        # markers 仍在 ToC 区域 → 跳过到 ToC 聚簇结束位置重试
        start_at = toc_end
        has_skipped_toc = True

    # 同时尝试对 default_selected 做 cluster-based TOC 跳过
    # 处理 "Table of Contents" 为页眉/页脚、cutoff 过度跳过 body Item 的场景
    cluster_skipped = _skip_toc_like_markers(
        full_text,
        item_pattern=item_pattern,
        ordered_tokens=ordered_tokens,
        initial_selected=default_selected,
        min_items=min_items_after_toc,
        end_at=end_at,
    )

    # 在 default / cutoff / cluster 三者间选择最佳候选。
    # 评分规则：
    # 1) 优先 marker 数量更多（覆盖更完整）；
    # 2) 若数量相同，优先首 marker 更靠前（通常更接近正文起点）；
    # 3) 若存在显式 ToC，则首 marker 落在 toc_start 之前的候选降权。
    candidates: list[list[tuple[str, int]]] = [default_selected]
    if best_from_cutoff is not None:
        candidates.append(best_from_cutoff)
    if cluster_skipped is not None:
        candidates.append(cluster_skipped)

    nonempty_candidates = [candidate for candidate in candidates if candidate]
    nonempty_candidates = _prefer_non_toc_marker_candidates(
        full_text=full_text,
        candidates=nonempty_candidates,
    )
    if not nonempty_candidates:
        best_result = default_selected
    else:
        best_result = nonempty_candidates[0]
        best_rank = _rank_marker_candidate(best_result, toc_start=toc_start)
        for candidate in nonempty_candidates[1:]:
            rank = _rank_marker_candidate(candidate, toc_start=toc_start)
            if rank > best_rank:
                best_rank = rank
                best_result = candidate

    return _refine_inline_reference_markers(
        full_text, best_result, item_pattern=item_pattern,
    )


def _prefer_non_toc_marker_candidates(
    *,
    full_text: str,
    candidates: list[list[tuple[str, int]]],
) -> list[list[tuple[str, int]]]:
    """在多候选中优先保留“非 ToC 聚簇”候选。

    现有排序规则（覆盖数量优先）在以下场景会误选目录候选：
    - 默认候选覆盖完整，但落在 ToC 区域；
    - 重试候选同样覆盖完整或接近完整，但位于正文。

    本函数先按 ToC 特征过滤候选，再交给排序函数做最终择优。
    为避免误杀，仅当至少存在一个“非 ToC”候选且该候选至少包含
    2 个 marker 时才启用过滤；否则返回原始候选列表。

    Args:
        full_text: 文档全文。
        candidates: 候选 marker 列表，每个元素是 ``(item_token, position)`` 列表。

    Returns:
        过滤后的候选列表；若不满足启用条件则返回原列表。

    Raises:
        RuntimeError: 过滤失败时抛出。
    """

    if not candidates:
        return candidates

    clean_candidates: list[list[tuple[str, int]]] = []
    for candidate in candidates:
        if len(candidate) < 2:
            continue
        toc_end = _find_toc_cluster_end(
            full_text,
            candidate,
            check_partial_toc=False,
        )
        if toc_end is None:
            clean_candidates.append(candidate)

    if not clean_candidates:
        return candidates
    return clean_candidates


def _rank_marker_candidate(
    markers: list[tuple[str, int]],
    *,
    toc_start: int,
) -> tuple[int, int, int]:
    """为 marker 候选打分，用于多候选择优。

    Args:
        markers: 候选 marker 列表。
        toc_start: 显式 ToC 截断起点（无 ToC 时为 0）。

    Returns:
        排序分值元组（越大越优）。

    Raises:
        RuntimeError: 评分失败时抛出。
    """

    if not markers:
        return (-1, -1, -1)
    first_pos = markers[0][1]
    before_toc_penalty = 0
    effective_toc_start = max(0, toc_start - _TOC_START_PENALTY_TOLERANCE_CHARS)
    if toc_start > 0 and first_pos < effective_toc_start:
        before_toc_penalty = -1
    return (before_toc_penalty, len(markers), -first_pos)


def _find_item_token_position_after(
    *,
    matches: list[tuple[str, int]],
    full_text: str,
    target_token: str,
    cursor: int,
    end_at: int,
) -> Optional[int]:
    """查找目标 Item token 在游标之后的首次位置。

    Args:
        matches: 预收集的全部匹配结果。
        target_token: 目标 token。
        cursor: 起始游标位置。
        end_at: 终止位置（不含）。

    Returns:
        命中位置；未命中返回 `None`。

    Raises:
        RuntimeError: 查找失败时抛出。
    """

    candidate_positions: list[int] = []
    for token, position in matches:
        if token != target_token:
            continue
        if position < cursor:
            continue
        if position >= end_at:
            continue
        candidate_positions.append(position)

    if not candidate_positions:
        return None

    filtered_positions = [
        position
        for position in candidate_positions
        if not _looks_like_inline_item_reference(full_text, position)
    ]
    positions_for_selection = (
        filtered_positions if filtered_positions else candidate_positions
    )

    # 优先选择“非行内引用”位置，减少 "see Item X ..." 被误当成标题。
    # 若全文结构已被压平（几乎无换行）导致所有候选都像行内引用，
    # 则回退到旧行为（首个候选），避免漏识别真实标题。
    for position in positions_for_selection:
        if not _is_inline_reference_context(full_text, position):
            return position
    return positions_for_selection[0]


def _looks_like_inline_item_reference(full_text: str, position: int) -> bool:
    """判断给定位置是否形如“Item X in/and/of ...”的行内交叉引用。

    该规则用于过滤无标点形式的交叉引用短语，例如：
    - ``Item 1A in this report``
    - ``Item 1A and Item 2``

    Args:
        full_text: 文档全文。
        position: 匹配起始位置。

    Returns:
        若看起来是行内交叉引用则返回 ``True``。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    snippet = full_text[position : position + 80]
    matched = re.match(
        r"(?i)\bitem\s+(?:16[a-j]|(?:1[0-9]|[1-9])[a-z]?)\b\s+([a-z]+)\b",
        snippet,
    )
    if matched is None:
        return False
    next_word = str(matched.group(1) or "").lower()
    return next_word in _INLINE_REF_NEXT_WORD_STOPWORDS


__all__ = [
    "_BaseSecReportFormProcessor",
    "_find_table_of_contents_cutoff",
    "_find_toc_cluster_end",
    "_looks_like_inline_toc_snippet",
    "_is_inline_reference_context",
    "_markers_look_like_toc_entries",
    "_refine_inline_reference_markers",
    "_select_ordered_item_markers",
    "_select_ordered_item_markers_after_toc",
]
