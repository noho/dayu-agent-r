"""基于 BeautifulSoup 的 6-K 表单专项处理器。

6-K 是外国私人发行人 (Foreign Private Issuer, FPI) 向 SEC 提交的
当期报告表单。典型 6-K 内容为**季度/年度业绩新闻稿** (Press Release)，
随 Exhibit 99.1 附件提交。

与 ``SixKFormProcessor``（基于 edgartools/SecProcessor，将来实现）平行：
- HTML 解析完全由 BeautifulSoup 驱动，无 edgartools 黑箱；
- 共享 ``six_k_form_common`` 中的 marker 扫描逻辑和财务报表解析逻辑；
- 搜索实现 token 级回退，提升短文档的搜索召回率。

设计决策：
- 6-K exhibit 文件（dex991.htm 等）在 lxml 下产生不同于 html.parser
  的解析树（如 SGML 元数据标签折叠、隐式标签修正差异），导致虚拟
  章节边界偏移和评分回归。回退为 html.parser 避免回归。
- 搜索使用两级回退策略：精确短语匹配→token OR 匹配。
  6-K 事件文档通常简短，标准化财务术语稀少，token 回退可
  从局部单词匹配中提取上下文 snippet，提高搜索命中率。

SEC 相关规则依据：
- SEC Form 6-K (17 CFR §249.306)
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re
from typing import Any, Optional

from bs4 import Tag
from edgar.xbrl import XBRL

from dayu.documents.processors.source import Source
from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.financial_result_contract import (
    FinancialStatementResult,
    determine_financial_statement_quality,
)

from .financial_base import FinancialMeta
from .fins_bs_processor import FinsBSProcessor
from .sec_form_section_common import (
    _VirtualSectionProcessorMixin,
    _check_special_form_support,
)
from .sec_xbrl_query import (
    _STATEMENT_METHODS,
    _build_period_summary,
    _build_statement_rows,
    _extract_period_columns,
    _infer_currency_from_units,
    _infer_period_semantics_from_xbrl_query,
    _infer_scale_from_xbrl_query,
    _infer_units_from_xbrl_query,
    build_statement_locator,
)
from .sec_table_extraction import _safe_statement_dataframe
from dayu.fins.xbrl_file_discovery import discover_xbrl_files
from .six_k_form_common import (
    _PRIMARY_EXTRACTABLE_STATEMENT_TYPES,
    _SECTION_TITLE_BY_STATEMENT_TYPE,
    _SIX_K_FORMS,
    _SUPPORTED_STATEMENT_TYPES,
    _build_six_k_markers,
    _build_statement_result_from_tables,
    _classify_statement_type_for_table,
    extract_statement_result_from_ocr_pages,
    select_statement_tables_by_row_signals,
)

_HIDDEN_OCR_PAGE_MIN_CHARS = 80
_HIDDEN_OCR_STYLE_SIZE_TOKENS: tuple[str, ...] = (
    "font-size:1px",
    "font-size:1pt",
    "font-size:0.5pt",
    "font-size:.5pt",
)
_HIDDEN_OCR_STYLE_COLOR_TOKENS: tuple[str, ...] = (
    "color:white",
    "color:#fff",
    "color:#ffffff",
)
_HIDDEN_OCR_STYLE_FONT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"font-size:(?P<size>\d*\.?\d+)(?P<unit>px|pt)"),
    re.compile(r"font:(?:[^;]*?)(?P<size>\d*\.?\d+)(?P<unit>px|pt)(?:/|;)"),
)
_HIDDEN_OCR_MAX_FONT_SIZE_BY_UNIT: dict[str, float] = {
    "px": 1.0,
    "pt": 1.0,
}
_PAGE_BREAK_STYLE_TOKENS: tuple[str, ...] = (
    "page-break-before:always",
    "page-break-after:always",
)
_PAGE_BREAK_TEXT_MIN_CHARS = 20
_PAGE_BREAK_PAGE_MIN_CHARS = 120
_PAGE_BREAK_TEXT_TAGS: frozenset[str] = frozenset(
    {
        "p",
        "div",
        "span",
        "font",
        "td",
        "th",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "caption",
    }
)

_TITLE_ONLY_STATEMENT_TABLE_MAX_ROWS = 4


def _normalize_inline_style(style_value: str) -> str:
    """规范化 HTML inline style 字符串。

    Args:
        style_value: 原始 style 属性值。

    Returns:
        去空白并转小写后的 style 字符串。

    Raises:
        无。
    """

    return "".join(style_value.split()).lower()


def _has_hidden_ocr_style(style_value: str) -> bool:
    """判断节点 style 是否符合隐藏 OCR 文本特征。

    Workiva / PDF 转 HTML 的 6-K 常把整页 OCR 文本放在极小字号、白色字体的
    ``font/div/span/p`` 中。样式既可能写成 `font-size:1pt;color:white`，
    也可能写成 `font:0.01px/115% Tahoma; color: White` 这类 `font` 缩写。
    当前函数统一按“极小字号 + 白色字体”识别这类版式特征。

    Args:
        style_value: 节点 style 属性值。

    Returns:
        命中隐藏 OCR 版式时返回 ``True``。

    Raises:
        无。
    """

    normalized_style = _normalize_inline_style(style_value)
    if not normalized_style:
        return False
    has_tiny_font = _has_tiny_hidden_ocr_font(normalized_style)
    if not has_tiny_font:
        return False
    return any(token in normalized_style for token in _HIDDEN_OCR_STYLE_COLOR_TOKENS)


def _has_tiny_hidden_ocr_font(normalized_style: str) -> bool:
    """判断样式中是否存在极小字号。

    Args:
        normalized_style: 经过归一化的 style 字符串。

    Returns:
        存在极小字号时返回 ``True``。

    Raises:
        无。
    """

    if any(token in normalized_style for token in _HIDDEN_OCR_STYLE_SIZE_TOKENS):
        return True
    for pattern in _HIDDEN_OCR_STYLE_FONT_PATTERNS:
        match = pattern.search(normalized_style)
        if match is None:
            continue
        unit = match.group("unit")
        limit = _HIDDEN_OCR_MAX_FONT_SIZE_BY_UNIT.get(unit)
        if limit is None:
            continue
        size = float(match.group("size"))
        if size <= limit:
            return True
    return False


def _has_page_break_boundary_style(style_value: str) -> bool:
    """判断节点样式是否声明了分页边界。

    Args:
        style_value: 原始 style 属性值。

    Returns:
        命中 `page-break-before/after: always` 时返回 `True`。

    Raises:
        无。
    """

    normalized_style = _normalize_inline_style(style_value)
    if not normalized_style:
        return False
    return any(token in normalized_style for token in _PAGE_BREAK_STYLE_TOKENS)


def _normalize_page_break_text(text: str) -> str:
    """规范化分页文本块。

    Args:
        text: 原始文本。

    Returns:
        合并空白后的文本；过短时返回空字符串。

    Raises:
        无。
    """

    normalized = " ".join(text.split())
    if len(normalized) < _PAGE_BREAK_TEXT_MIN_CHARS:
        return ""
    return normalized


class BsSixKFormProcessor(_VirtualSectionProcessorMixin, FinsBSProcessor):
    """基于 BeautifulSoup 的 6-K 表单专项处理器。

    继承链：
    ``BsSixKFormProcessor → _VirtualSectionProcessorMixin → FinsBSProcessor → BSProcessor``

    与 ``SixKFormProcessor``（基于 SecProcessor，将来实现）平行，
    共享 ``six_k_form_common`` 中的 marker 策略和财务报表解析逻辑。

    搜索增强：
    - 第一级：精确短语匹配（继承 ``_VirtualSectionProcessorMixin``）。
    - 第二级：token OR 回退（``_ENABLE_TOKEN_FALLBACK_SEARCH = True``）。
    """

    PARSER_VERSION = "six_k_section_processor_v1.0.1"
    _ENABLE_TOKEN_FALLBACK_SEARCH = True

    # 6-K exhibit 文件（dex991.htm 等）在 lxml 下产生不同于 html.parser
    # 的解析树（如 SGML 元数据标签折叠、隐式标签修正差异），导致虚拟
    # 章节边界偏移和评分回归。回退为 html.parser 避免回归。
    _html_parser: str = "html.parser"

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
        # 记录源文件路径用于独立发现并加载 XBRL 文件。
        self._source_path: Path = source.materialize(suffix=".html")
        self._xbrl: Optional[XBRL] = None
        self._xbrl_loaded: bool = False
        self._initialize_virtual_sections(min_sections=2)
        self._realign_statement_tables_to_virtual_sections()

    @classmethod
    def supports(
        cls,
        source: Source,
        *,
        form_type: Optional[str] = None,
        media_type: Optional[str] = None,
    ) -> bool:
        """判断是否支持处理该文件。

        Args:
            source: 文档来源抽象。
            form_type: 可选表单类型。
            media_type: 可选媒体类型。

        Returns:
            是否支持。

        Raises:
            OSError: 文件访问失败时可能抛出。
        """

        return _check_special_form_support(
            source,
            form_type=form_type,
            media_type=media_type,
            supported_forms=_SIX_K_FORMS,
            base_supports_fn=FinsBSProcessor.supports,
        )

    def _build_markers(self, full_text: str) -> list[tuple[int, Optional[str]]]:
        """构建 6-K 专项边界。

        Args:
            full_text: 文档全文。

        Returns:
            `(start_index, title)` 列表。

        Raises:
            RuntimeError: 构建失败时抛出。
        """

        return _build_six_k_markers(full_text)

    def get_financial_statement(
        self,
        statement_type: str,
        financials: Mapping[str, JsonValue] | None = None,
        *,
        meta: Optional[FinancialMeta] = None,
    ) -> FinancialStatementResult:
        """读取 6-K 结构化财务报表。

        Args:
            statement_type: 报表类型。
            financials: 可选财务缓存，当前未使用。
            meta: 可选元信息，当前未使用。

        Returns:
            结构化财务报表结果。

        Raises:
            RuntimeError: 解析失败时抛出。
        """

        del financials
        del meta

        normalized_statement_type = statement_type.strip().lower()
        result: FinancialStatementResult = {
            "statement_type": statement_type,
            "periods": [],
            "rows": [],
            "currency": None,
            "units": None,
            "scale": None,
            "data_quality": "partial",
            "reason": "unsupported_statement_type",
            "statement_locator": build_statement_locator(
                statement_type=statement_type,
                periods=[],
                rows=[],
            ),
        }
        if normalized_statement_type not in _SUPPORTED_STATEMENT_TYPES:
            return result

        xbrl_result = self._get_financial_statement_from_xbrl(
            statement_type=statement_type,
            normalized_statement_type=normalized_statement_type,
        )
        if xbrl_result is not None:
            return xbrl_result

        if normalized_statement_type not in _PRIMARY_EXTRACTABLE_STATEMENT_TYPES:
            result["reason"] = "statement_not_found"
            return result

        candidate_tables = self._get_statement_tables(normalized_statement_type)
        if not candidate_tables:
            ocr_result = self._get_statement_result_from_ocr_pages(normalized_statement_type)
            if ocr_result is not None:
                return ocr_result
            result["reason"] = "statement_not_found"
            return result

        extracted = _build_statement_result_from_tables(
            statement_type=normalized_statement_type,
            tables=candidate_tables,
        )
        if extracted is None:
            ocr_result = self._get_statement_result_from_ocr_pages(normalized_statement_type)
            if ocr_result is not None:
                return ocr_result
            result["reason"] = "low_confidence_extraction"
            return result
        return extracted

    def _realign_statement_tables_to_virtual_sections(self) -> None:
        """按 6-K 报表标题重映射表格到虚拟章节。

        Args:
            无。

        Returns:
            无。

        Raises:
            RuntimeError: 重映射失败时抛出。
        """

        if not self._virtual_sections:
            return

        remapped_refs: set[str] = set()
        title_to_ref = {
            str(section.title): section.ref
            for section in self._virtual_sections
            if section.title is not None
        }
        for table in self._tables:
            statement_type = _classify_statement_type_for_table(
                caption=table.caption,
                headers=table.headers,
                context_before=table.context_before,
            )
            if statement_type is None:
                continue
            section_title = _SECTION_TITLE_BY_STATEMENT_TYPE.get(statement_type)
            if section_title is None:
                continue
            section_ref = title_to_ref.get(section_title)
            if section_ref is None:
                continue
            self._table_ref_to_virtual_ref[table.ref] = section_ref
            remapped_refs.add(table.ref)

        if not remapped_refs:
            return

        for section in self._virtual_sections:
            section.table_refs = [table_ref for table_ref in section.table_refs if table_ref not in remapped_refs]

        for table_ref, section_ref in self._table_ref_to_virtual_ref.items():
            if table_ref not in remapped_refs:
                continue
            section = self._virtual_section_by_ref.get(section_ref)
            if section is None:
                continue
            if table_ref not in section.table_refs:
                section.table_refs.append(table_ref)

    def _get_statement_tables(self, statement_type: str) -> list[Any]:
        """获取某类 6-K 财务报表对应的表格列表。

        Args:
            statement_type: 报表类型。

        Returns:
            候选表格列表。

        Raises:
            RuntimeError: 读取失败时抛出。
        """

        matched_tables: list[Any] = []
        for table in self._tables:
            classified_type = _classify_statement_type_for_table(
                caption=table.caption,
                headers=table.headers,
                context_before=table.context_before,
            )
            if classified_type == statement_type:
                matched_tables.append(table)
        if matched_tables:
            return self._expand_statement_anchor_tables(
                statement_type=statement_type,
                matched_tables=matched_tables,
            )

        # 回退策略：标题归类失败时，按行标签语义信号反推报表类型。
        return select_statement_tables_by_row_signals(
            statement_type=statement_type,
            tables=self._tables,
        )

    def _expand_statement_anchor_tables(
        self,
        *,
        statement_type: str,
        matched_tables: list[Any],
    ) -> list[Any]:
        """为标题型 statement table 补上紧邻的数据表。

        一批 6-K press release 会把“报表标题”和“数值表体”拆成两个相邻
        `<table>`：前一个 table 只有公司名、statement title 与单位说明，
        真正的数据落在下一个未命名 table 中。当前函数仅在高置信场景下
        补上这类紧邻数据表，避免把标题表误当成空报表。

        Args:
            statement_type: 目标报表类型。
            matched_tables: 已按标题语义命中的候选表格。

        Returns:
            去重后的扩展候选表格列表。

        Raises:
            RuntimeError: 扩展失败时抛出。
        """

        expanded_tables: list[Any] = []
        seen_refs: set[str] = set()
        table_indexes = {
            getattr(table, "ref", f"index_{index}"): index
            for index, table in enumerate(self._tables)
        }
        for table in matched_tables:
            table_ref = str(getattr(table, "ref", ""))
            if table_ref not in seen_refs:
                expanded_tables.append(table)
                seen_refs.add(table_ref)

            if not self._is_title_only_statement_anchor(
                statement_type=statement_type,
                table=table,
            ):
                continue

            candidate_index = table_indexes.get(table_ref)
            if candidate_index is None:
                continue
            continuation_table = self._find_adjacent_statement_data_table(
                statement_type=statement_type,
                start_index=candidate_index + 1,
            )
            if continuation_table is None:
                continue
            continuation_ref = str(getattr(continuation_table, "ref", ""))
            if continuation_ref in seen_refs:
                continue
            expanded_tables.append(continuation_table)
            seen_refs.add(continuation_ref)
        return expanded_tables

    def _is_title_only_statement_anchor(
        self,
        *,
        statement_type: str,
        table: Any,
    ) -> bool:
        """判断命中的 statement table 是否只是标题锚点。

        Args:
            statement_type: 目标报表类型。
            table: 已命中的表格对象。

        Returns:
            仅包含标题、无法独立解析成报表时返回 ``True``。

        Raises:
            RuntimeError: 判定失败时抛出。
        """

        if int(getattr(table, "row_count", 0)) > _TITLE_ONLY_STATEMENT_TABLE_MAX_ROWS:
            return False
        return _build_statement_result_from_tables(
            statement_type=statement_type,
            tables=[table],
        ) is None

    def _find_adjacent_statement_data_table(
        self,
        *,
        statement_type: str,
        start_index: int,
    ) -> Optional[Any]:
        """查找标题表之后紧邻的数值数据表。

        仅接受第一个满足“当前 statement_type 可独立结构化”的后继表。
        一旦遇到另一个已命名 statement table，就停止搜索，避免跨到其他报表。

        Args:
            statement_type: 目标报表类型。
            start_index: 在 ``self._tables`` 中开始搜索的索引。

        Returns:
            命中的紧邻数据表；未找到时返回 ``None``。

        Raises:
            RuntimeError: 搜索失败时抛出。
        """

        for candidate in self._tables[start_index:]:
            classified_type = _classify_statement_type_for_table(
                caption=candidate.caption,
                headers=candidate.headers,
                context_before=candidate.context_before,
            )
            if classified_type in _PRIMARY_EXTRACTABLE_STATEMENT_TYPES:
                return None
            if _build_statement_result_from_tables(
                statement_type=statement_type,
                tables=[candidate],
            ) is not None:
                return candidate
        return None

    def _get_statement_result_from_ocr_pages(
        self,
        statement_type: str,
    ) -> Optional[FinancialStatementResult]:
        """从 image+OCR 隐藏文本页回退提取财务报表。

        Args:
            statement_type: 目标报表类型。

        Returns:
            结构化财务报表结果；无法稳定提取时返回 `None`。

        Raises:
            RuntimeError: 提取失败时抛出。
        """

        page_texts = self._collect_statement_fallback_page_texts()
        if not page_texts:
            return None
        return extract_statement_result_from_ocr_pages(
            statement_type=statement_type,
            page_texts=page_texts,
        )

    def _collect_ocr_page_texts(self) -> list[str]:
        """收集 6-K image+OCR 模式下的隐藏文本页。

        Args:
            无。

        Returns:
            候选 OCR 页文本列表。

        Raises:
            RuntimeError: 收集失败时抛出。
        """

        page_texts: list[str] = []
        seen_texts: set[str] = set()
        for node in self._root.find_all(
            lambda tag: isinstance(tag, Tag)
            and _has_hidden_ocr_style(str(tag.get("style") or ""))
        ):
            # paragraph-level hidden OCR 既可能出现在 `<p>`，也可能出现在
            # `font/div/span`；统一按样式真源采集并去重，避免遗漏字体缩写变体。
            text = " ".join(node.get_text(" ", strip=False).split())
            if len(text) < _HIDDEN_OCR_PAGE_MIN_CHARS:
                continue
            if text in seen_texts:
                continue
            seen_texts.add(text)
            page_texts.append(text)
        if page_texts:
            return page_texts
        page_texts = self._collect_hidden_ocr_page_texts_from_image_containers()
        if page_texts:
            return page_texts
        return self._collect_fixed_layout_page_texts()

    def _collect_hidden_ocr_page_texts_from_image_containers(self) -> list[str]:
        """从带图片的页容器中抽取隐藏 OCR 文本。

        部分 Workiva / slide 风格的 6-K 不把 OCR 文本放在 ``<p style=...>``，
        而是放在与页面图片同层的
        ``<div><font size="1" style="font-size:1pt;color:white">`` 结构中。
        当前函数按图片页容器重新聚合这些隐藏文本，供 OCR fallback 使用。

        Args:
            无。

        Returns:
            候选页文本列表。

        Raises:
            RuntimeError: 收集失败时抛出。
        """

        page_texts: list[str] = []
        seen_texts: set[str] = set()
        for image_node in self._root.find_all("img"):
            parent = image_node.parent
            if not isinstance(parent, Tag):
                continue
            page_text = self._collect_hidden_ocr_text_from_container(parent)
            normalized_page_text = " ".join(page_text.split())
            if len(normalized_page_text) < _HIDDEN_OCR_PAGE_MIN_CHARS:
                continue
            if normalized_page_text in seen_texts:
                continue
            seen_texts.add(normalized_page_text)
            page_texts.append(normalized_page_text)
        return page_texts

    def _collect_hidden_ocr_text_from_container(self, container: Tag) -> str:
        """提取单个图片页容器中的隐藏 OCR 文本。

        Args:
            container: 候选页容器节点。

        Returns:
            聚合后的隐藏 OCR 文本；未命中时返回空字符串。

        Raises:
            RuntimeError: 提取失败时抛出。
        """

        text_parts: list[str] = []
        seen_texts: set[str] = set()
        for node in container.find_all(
            lambda tag: isinstance(tag, Tag)
            and _has_hidden_ocr_style(str(tag.get("style") or ""))
        ):
            text = " ".join(node.get_text(" ", strip=False).split())
            if len(text) < 20:
                continue
            if text in seen_texts:
                continue
            seen_texts.add(text)
            text_parts.append(text)
        return " ".join(text_parts)

    def _collect_fixed_layout_page_texts(self) -> list[str]:
        """收集 fixed-layout HTML 中按页切分的文本。

        Args:
            无。

        Returns:
            候选页文本列表。

        Raises:
            RuntimeError: 收集失败时抛出。
        """

        page_texts: list[str] = []
        for page_node in self._root.find_all("div", id=True):
            page_id = page_node.get("id")
            if not isinstance(page_id, str) or not page_id.startswith("Page"):
                continue
            page_text = " ".join(page_node.stripped_strings)
            if page_text:
                page_texts.append(page_text)
        return page_texts

    def _collect_page_break_page_texts(self) -> list[str]:
        """按 `page-break-before/after` 样式聚合分页文本。

        一批 6-K results HTML 不会落成标准 `<table>`，也没有 `Page1/Page2`
        这类 fixed-layout 容器，而是通过 `page-break-before/after: always`
        把正文切成多页。当前函数按这些分页边界重新聚合每页文本，供
        OCR fallback 复用。

        Args:
            无。

        Returns:
            候选页文本列表。

        Raises:
            RuntimeError: 收集失败时抛出。
        """

        root = self._root.body if isinstance(self._root.body, Tag) else self._root
        page_texts: list[str] = []
        seen_pages: set[str] = set()
        current_parts: list[str] = []
        for node in root.descendants:
            if not isinstance(node, Tag):
                continue
            node_name = str(node.name or "").lower()
            if node_name not in _PAGE_BREAK_TEXT_TAGS:
                continue
            node_text = _normalize_page_break_text(node.get_text(" ", strip=False))
            if _has_page_break_boundary_style(str(node.get("style") or "")):
                self._append_page_break_page_text(
                    current_parts=current_parts,
                    page_texts=page_texts,
                    seen_pages=seen_pages,
                )
                current_parts = []
                if node_text:
                    current_parts.append(node_text)
                continue
            if node_text:
                current_parts.append(node_text)
        self._append_page_break_page_text(
            current_parts=current_parts,
            page_texts=page_texts,
            seen_pages=seen_pages,
        )
        return page_texts

    def _append_page_break_page_text(
        self,
        *,
        current_parts: list[str],
        page_texts: list[str],
        seen_pages: set[str],
    ) -> None:
        """将当前分页缓冲区收敛为单页文本。

        Args:
            current_parts: 当前页累积的文本片段。
            page_texts: 输出页文本列表。
            seen_pages: 已输出页文本集合。

        Returns:
            无。

        Raises:
            RuntimeError: 收敛失败时抛出。
        """

        page_text = " ".join(" ".join(current_parts).split())
        if len(page_text) < _PAGE_BREAK_PAGE_MIN_CHARS:
            return
        if page_text in seen_pages:
            return
        seen_pages.add(page_text)
        page_texts.append(page_text)

    def _collect_pseudo_page_texts_from_tables(self) -> list[str]:
        """从伪表格页抽取可供 OCR 回退消费的页文本。

        这类 6-K 常由 PDF/演示稿转 HTML 后落成“每页一张表”的形态，
        表格本身不再保留可结构化的二维矩阵，但 caption/header/context
        里仍然携带完整页文本。当前函数把这些页文本提取出来，交给
        `six_k_form_common` 的 OCR 解析器做统一处理。

        Args:
            无。

        Returns:
            候选伪页文本列表。

        Raises:
            RuntimeError: 收集失败时抛出。
        """

        page_texts: list[str] = []
        seen_texts: set[str] = set()
        for table in self._tables:
            text_parts: list[str] = []
            if table.caption:
                text_parts.append(table.caption)
            if table.headers:
                text_parts.extend(header for header in table.headers if header)
            if table.context_before:
                text_parts.append(table.context_before)
            page_text = " ".join(text_parts).strip()
            if len(page_text) < 120:
                continue
            normalized_page_text = " ".join(page_text.split())
            if not normalized_page_text or normalized_page_text in seen_texts:
                continue
            seen_texts.add(normalized_page_text)
            page_texts.append(normalized_page_text)
        return page_texts

    def _collect_statement_fallback_page_texts(self) -> list[str]:
        """汇总 6-K 财报提取失败时可用的 OCR/伪页文本。

        Args:
            无。

        Returns:
            候选页文本列表。

        Raises:
            RuntimeError: 收集失败时抛出。
        """

        page_texts: list[str] = []
        seen_texts: set[str] = set()
        candidates = [
            *self._collect_ocr_page_texts(),
            *self._collect_page_break_page_texts(),
            *self._collect_pseudo_page_texts_from_tables(),
        ]
        for candidate in candidates:
            normalized_text = " ".join(str(candidate or "").split())
            if not normalized_text or normalized_text in seen_texts:
                continue
            seen_texts.add(normalized_text)
            page_texts.append(normalized_text)
        return page_texts

    def _get_financial_statement_from_xbrl(
        self,
        *,
        statement_type: str,
        normalized_statement_type: str,
    ) -> Optional[FinancialStatementResult]:
        """从 XBRL 提取标准财务报表。

        Args:
            statement_type: 原始报表类型。
            normalized_statement_type: 标准化后的报表类型。

        Returns:
            XBRL 提取结果；XBRL 不可用或当前报表在 XBRL 不可提取时返回 `None`。

        Raises:
            RuntimeError: XBRL 读取失败时抛出。
        """

        method_name = _STATEMENT_METHODS.get(normalized_statement_type)
        if method_name is None:
            return None
        xbrl = self._get_xbrl()
        if xbrl is None:
            return None

        statements = getattr(xbrl, "statements", None)
        method = getattr(statements, method_name, None)
        if not callable(method):
            return None

        statement_obj = method()
        if statement_obj is None:
            return None
        statement_df = _safe_statement_dataframe(statement_obj)
        if statement_df is None or statement_df.empty:
            return None

        period_columns = _extract_period_columns(statement_df.columns)
        rows = _build_statement_rows(statement_df, period_columns)
        if not rows:
            return None
        period_evidence = _infer_period_semantics_from_xbrl_query(xbrl, period_columns)
        periods = [
            _build_period_summary(
                period,
                fiscal_year=(period_evidence[period][0] if period in period_evidence else None),
                fiscal_period=(period_evidence[period][1] if period in period_evidence else None),
            )
            for period in period_columns
        ]
        units = _infer_units_from_xbrl_query(xbrl)
        currency = _infer_currency_from_units(units)
        scale_outcome = _infer_scale_from_xbrl_query(xbrl)
        scale = None if scale_outcome.query_failed else scale_outcome.scale
        quality = determine_financial_statement_quality(
            rows=rows,
            periods=periods,
            scale=scale,
            complete_quality="xbrl",
        )
        return {
            "statement_type": statement_type,
            "periods": periods,
            "rows": rows,
            "currency": currency,
            "units": units,
            "scale": scale,
            "data_quality": quality.data_quality,
            "reason": quality.reason,
            "statement_locator": build_statement_locator(
                statement_type=statement_type,
                periods=periods,
                rows=rows,
            ),
        }

    def _get_xbrl(self) -> Optional[XBRL]:
        """延迟加载并缓存 XBRL 对象。

        Args:
            无。

        Returns:
            `XBRL` 实例；未发现可用 XBRL 文件时返回 `None`。

        Raises:
            RuntimeError: 构建 XBRL 失败时抛出。
        """

        if self._xbrl_loaded:
            return self._xbrl

        self._xbrl_loaded = True
        xbrl_files = discover_xbrl_files(self._source_path.parent)
        instance_file = xbrl_files.get("instance")
        schema_file = xbrl_files.get("schema")
        if instance_file is None or schema_file is None:
            self._xbrl = None
            return None
        try:
            self._xbrl = XBRL.from_files(
                instance_file=instance_file,
                schema_file=schema_file,
                presentation_file=xbrl_files.get("presentation"),
                calculation_file=xbrl_files.get("calculation"),
                definition_file=xbrl_files.get("definition"),
                label_file=xbrl_files.get("label"),
            )
        except Exception:
            self._xbrl = None
        return self._xbrl


__all__ = ["BsSixKFormProcessor"]
