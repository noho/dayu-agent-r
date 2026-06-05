"""基于 BeautifulSoup 的 20-F 表单专项处理器。

本模块实现基于 BSProcessor（BeautifulSoup）的 20-F 切分策略，
与 ``twenty_f_processor.py``（基于 edgartools/SecProcessor）平行：
- 共享同一套 ``Part + Item + 描述`` marker 扫描逻辑（``_build_twenty_f_markers``）；
- HTML 解析完全由 BeautifulSoup 驱动，无 edgartools 黑箱；
- XBRL 通过独立文件发现加载，不依赖 edgartools 文档对象。

设计意图：
- 为 20-F 提供 BS 路线主处理器（priority 200），
  ``TwentyFFormProcessor`` 降级为回退（priority 190）；
- BS 路线独立提供 XBRL 财务报表能力（``get_financial_statement`` / ``query_xbrl_facts``），
  提升 D_consistency 维度评分。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Optional

from dayu.documents.processors.source import Source

from .bs_report_form_common import _BaseBsReportFormProcessor
from .sec_report_form_common import _extract_source_text_preserving_lines
from .twenty_f_form_common import (
    _build_twenty_f_markers,
    _select_preferred_twenty_f_text,
    _trim_twenty_f_source_text,
)

_ITEM_TITLE_PATTERN = re.compile(r"(?i)\bitem\s+(16[a-j]|4a|1[0-9]|[1-9])\b")
_TWENTY_F_KEY_ITEMS = frozenset({"3", "5", "18"})
_MIN_TOTAL_ITEMS_FOR_BS = 3
_MAX_SAFE_SECTION_CHARS_FOR_BS = 300000
_TOC_PAGE_LINE_PATTERN = re.compile(r"(?im)^\s*[A-Za-z][^\n]{0,180}\b\d{1,3}\s*$")
_ITEM_18_REFERENCE_PHRASE_PATTERN = re.compile(
    r"(?i)\binformation\s+required\s+by\s+this\s+item\s+is\s+set\s+forth\b"
)
_ITEM_18_PAGE_RANGE_REFERENCE_PATTERN = re.compile(
    r"(?is)\b(?:included|set\s+forth|contained|appear(?:s|ing)?|presented)\b"
    r".{0,120}\bpages?\s+F-\d+\s*(?:through|to|[-\u2013\u2014])\s*F-\d+\b"
)


def _has_minimum_twenty_f_marker_quality(full_text: str) -> bool:
    """判断全文 marker 质量是否已满足 BS 20-F 的最低要求。

    该函数复用 20-F marker 构建结果，不依赖具体 HTML 解析链路。
    用途是判断 BS 默认全文抽取是否已经足够好，从而避免把
    ``source_text`` 的更激进替换扩散到本来正常的文档。

    Args:
        full_text: 候选全文文本。

    Returns:
        达到最低 Item 质量要求返回 ``True``，否则返回 ``False``。

    Raises:
        无。
    """

    titles = [title for _, title in _build_twenty_f_markers(str(full_text or ""))]
    return _has_minimum_twenty_f_item_quality(titles)


def _has_minimum_twenty_f_item_quality(section_titles: list[Optional[str]]) -> bool:
    """判断 BS 20-F 切分结果是否满足最小 Item 结构质量。

    Args:
        section_titles: 虚拟章节标题列表。

    Returns:
        满足最小质量阈值返回 ``True``，否则返回 ``False``。

    Raises:
        无。
    """

    recognized_items: set[str] = set()
    for title in section_titles:
        if not title:
            continue
        match = _ITEM_TITLE_PATTERN.search(str(title))
        if match is None:
            continue
        recognized_items.add(str(match.group(1)).upper())

    if len(recognized_items) < _MIN_TOTAL_ITEMS_FOR_BS:
        return False
    # 20-F 的 BS 主路径只有在核心分析骨架 Item 3 / 5 / 18 全部齐备时，
    # 才说明当前 marker 质量达到了可继续增强的最低分析门槛。
    return _TWENTY_F_KEY_ITEMS.issubset(recognized_items)


def _has_risky_twenty_f_section_profile(sections: Sequence[object]) -> bool:
    """判断 BS 20-F 切分是否存在高风险结构。

    风险条件：
    1. 任一章节内容超过 CI 硬门禁阈值（>300000）；
    2. Item 18 呈现“短文本 + 标题页码行”目录桩特征。

    Args:
        sections: 虚拟章节对象列表（需包含 ``title``、``content`` 属性）。

    Returns:
        命中风险返回 ``True``，否则返回 ``False``。

    Raises:
        无。
    """

    for section in sections:
        title = str(getattr(section, "title", "") or "")
        content = str(getattr(section, "content", "") or "")
        normalized = " ".join(content.split())
        if len(normalized) > _MAX_SAFE_SECTION_CHARS_FOR_BS:
            return True
        if "item 18" in title.lower():
            has_reference_phrase = _ITEM_18_REFERENCE_PHRASE_PATTERN.search(normalized) is not None
            has_toc_like_line = _TOC_PAGE_LINE_PATTERN.search(content) is not None
            has_page_range_reference = (
                _ITEM_18_PAGE_RANGE_REFERENCE_PATTERN.search(normalized) is not None
            )
            # Item 18 合法地允许“引用财报附页”写法（常见于
            # "The information required by this item is set forth ..."），
            # 不应误判为目录桩；这里只输出结构风险信号，供后续分析使用。
            if len(normalized) < 120 and has_toc_like_line and not has_reference_phrase:
                return True
            # 若仅剩短页码区间引用（如 "included on pages F-1 through F-86"），
            # 当前 BS 切分通常已把真正财务报表丢失，应视为高风险信号。
            if len(normalized) < 220 and has_page_range_reference:
                return True
    return False


class BsTwentyFFormProcessor(_BaseBsReportFormProcessor):
    """基于 BeautifulSoup 的 20-F 表单专项处理器。

    继承链：
    ``BsTwentyFFormProcessor → _BaseBsReportFormProcessor
    → _VirtualSectionProcessorMixin → FinsBSProcessor → BSProcessor``

    与 ``TwentyFFormProcessor``（基于 SecProcessor）平行，
    共享 ``_build_twenty_f_markers()`` marker 策略。
    """

    PARSER_VERSION = "bs_twenty_f_processor_v1.1.8"
    _SUPPORTED_FORMS = frozenset({"20-F"})

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

        self._cached_marker_source_text: Optional[str] = None
        self._cached_marker_source_result: list[tuple[int, Optional[str]]] = []
        super().__init__(source=source, form_type=form_type, media_type=media_type)
        section_titles = [section.title for section in self._virtual_sections]

    def _collect_document_text(self) -> str:
        """提取更适合 20-F marker 检测的全文文本。

        BS 路线默认使用 ``root.get_text(separator="\\n")`` 保留换行，
        但 20-F 常见的 iXBRL 前导噪声与标题压平问题仍需要额外修正。

        与 edgartools 路线不同，BS 路线的默认全文抽取已经基于清洗后的
        DOM，通常比直接源文本更稳。因此这里采用更保守的迁移策略：
        1. 先使用 BS 默认全文抽取；
        2. 若该文本已经满足最低 Item 质量，则直接返回，避免全局替换；
        3. 仅当默认抽取失真到连最低 Item 质量都不满足时，才启用
           raw source text + XBRL 前导裁切 + marker 质量择优。

        Args:
            无。

        Returns:
            更适合 20-F 虚拟章节切分的全文文本。

        Raises:
            RuntimeError: 读取失败时抛出。
        """

        try:
            # 20-F 的目录和正文标题常由多个相邻 DOM 节点拼出。
            # 这里不能使用 ``strip=True``，否则节点边界会被压平，
            # 容易把 ``Item 5`` 等标题重新挤回 ToC/guide 形态。
            parsed_text = self._root.get_text(separator="\n").strip()
        except Exception:
            parsed_text = super()._collect_document_text()
        if self._has_minimum_twenty_f_marker_quality_with_cache(parsed_text):
            return parsed_text

        extracted = _trim_twenty_f_source_text(
            _extract_source_text_preserving_lines(self._source)
        )
        return _select_preferred_twenty_f_text(
            source_text=extracted,
            parsed_text=parsed_text,
        )

    def _has_minimum_twenty_f_marker_quality_with_cache(self, full_text: str) -> bool:
        """基于实例级 marker 缓存判断全文是否满足最小质量。

        Args:
            full_text: 待检测的全文文本。

        Returns:
            达到最低 Item 质量要求时返回 ``True``。

        Raises:
            RuntimeError: marker 构建失败时抛出。
        """

        cached_markers = self._get_cached_twenty_f_markers(full_text)
        return _has_minimum_twenty_f_item_quality([title for _, title in cached_markers])

    def _get_cached_twenty_f_markers(
        self,
        full_text: str,
    ) -> list[tuple[int, Optional[str]]]:
        """读取当前 Processor 生命周期内的 20-F marker 缓存。

        20-F 在初始化阶段会对同一份 ``full_text`` 先做质量判断，再做正式切分。
        UBS 一类带超长 cross-reference guide 的文档里，这两步若重复重跑
        ``_build_twenty_f_markers()``，会额外支付整套 Item/guide 回查成本。
        这里使用实例级单槽缓存，命中时直接复用 marker 结果。

        Args:
            full_text: 待构建 marker 的全文文本。

        Returns:
            ``(position, title)`` marker 列表副本。

        Raises:
            RuntimeError: marker 构建失败时抛出。
        """

        normalized_text = str(full_text or "")
        if normalized_text == self._cached_marker_source_text:
            return list(self._cached_marker_source_result)

        markers = list(_build_twenty_f_markers(normalized_text))
        self._cached_marker_source_text = normalized_text
        self._cached_marker_source_result = markers
        return list(markers)

    def _build_markers(self, full_text: str) -> list[tuple[int, Optional[str]]]:
        """构建 20-F 专项边界标记。

        复用 ``_build_twenty_f_markers()``，该函数仅依赖纯文本正则扫描，
        与底层 HTML 解析引擎无关。

        Args:
            full_text: 文档全文。

        Returns:
            ``(start_index, title)`` 列表。

        Raises:
            RuntimeError: 构建失败时抛出。
        """

        return self._get_cached_twenty_f_markers(full_text)


__all__ = [
    "BsTwentyFFormProcessor",
    "_has_minimum_twenty_f_marker_quality",
    "_has_minimum_twenty_f_item_quality",
    "_has_risky_twenty_f_section_profile",
]
