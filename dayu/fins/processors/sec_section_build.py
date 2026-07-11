"""SEC 文档章节切分与定位。"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Optional, Protocol, runtime_checkable

import pandas as pd

from dayu.documents.processors.text_utils import (
    PREVIEW_MAX_CHARS as _PREVIEW_MAX_CHARS,
    format_section_ref as _format_section_ref,
    normalize_optional_string as _normalize_optional_string_base,
    normalize_whitespace as _normalize_whitespace,
)
from dayu.fins._log import Log

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_SECTION_MARKER_WORD_COUNTS = (28, 24, 20, 16, 12)
_SECTION_MARKER_MIN_CHARS = 80
_CONTEXT_TAIL_MARKER_WORD_COUNTS = (24, 20, 16, 12, 8)
_CONTEXT_TAIL_MARKER_MIN_CHARS = 48
_TABLE_OF_CONTENTS_TOKEN = "table of contents"
_TOC_CUTOFF_BUFFER_CHARS = 1500
_SECTION_ANCHOR_SEQUENCE_PATTERN = re.compile(r"_(\d+)$")
_TABLE_FINGERPRINT_MAX_CHARS = 240


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class _SectionBlock:
    """内部章节结构。"""

    ref: str
    title: Optional[str]
    level: int
    parent_ref: Optional[str]
    preview: str
    text: str
    table_refs: list[str]
    table_fingerprints: set[str]
    contains_full_text: bool


@runtime_checkable
class _TableTextLike(Protocol):
    """edgartools 表格文本能力协议。"""

    def text(self) -> str:
        """读取表格文本。

        Args:
            无。

        Returns:
            表格文本。

        Raises:
            RuntimeError: 底层读取失败时可能抛出。
        """

        ...


# ---------------------------------------------------------------------------
# 章节构建主函数
# ---------------------------------------------------------------------------


def _build_sections(
    document: Any,
    *,
    fast_mode: bool = False,
    single_full_text: bool = False,
    full_text_override: Optional[str] = None,
) -> list[_SectionBlock]:
    """从文档对象构建章节列表。

    Args:
        document: edgartools 文档对象。
        fast_mode: 是否启用快速章节构建。
        single_full_text: 快速模式下是否将全文合并为单章节。
        full_text_override: 可选预加载全文文本（用于避免重复 `document.text()`）。

    Returns:
        章节块列表。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    if fast_mode and single_full_text:
        result = _build_single_full_text_section(document, full_text_override=full_text_override)
        # 当 document.text() 失败或返回空时，单全文章节无内容；
        # 降级到标准逐 section 路径（per-section text 仍可能有效）。
        if result and result[0].text:
            return result
        Log.debug(
            "single_full_text 返回空文本，降级到标准路径",
            module="FINS.SEC_PROCESSOR",
        )

    section_items = _iter_sections(document)
    if not section_items:
        return _build_single_full_text_section(document, full_text_override=full_text_override)
    if fast_mode:
        return _build_sections_fast(
            document=document,
            section_items=section_items,
            single_full_text=single_full_text,
            full_text_override=full_text_override,
        )

    document_text = _normalize_searchable_text(_safe_document_text(document))
    section_entries: list[dict[str, Any]] = []
    for original_index, (section_key, section_obj) in enumerate(section_items, start=1):
        section_text = _normalize_whitespace(_safe_section_text(section_obj))
        title = _build_section_title(section_key=section_key, section_obj=section_obj)
        table_fingerprints = _extract_section_table_fingerprints(section_obj)
        marker_occurrences, anchor_occurrences = _collect_section_appearance_candidates(
            document_text=document_text,
            section_key=section_key,
            section_obj=section_obj,
            section_text=section_text,
        )
        section_entries.append(
            {
                "original_index": original_index,
                "section_key": section_key,
                "section_obj": section_obj,
                "title": title,
                "section_text": section_text,
                "table_fingerprints": table_fingerprints,
                "marker_occurrences": marker_occurrences,
                "anchor_occurrences": anchor_occurrences,
                "appearance_index": None,
                "anchor_sequence": _resolve_section_anchor_sequence(document=document, section_key=section_key),
            }
        )

    body_anchor_index = _resolve_document_body_anchor_index(section_entries)
    toc_cutoff_index = _resolve_toc_cutoff_index(document_text)
    for entry in section_entries:
        entry["appearance_index"] = _locate_section_appearance(
            marker_occurrences=entry["marker_occurrences"],
            anchor_occurrences=entry["anchor_occurrences"],
            body_anchor_index=body_anchor_index,
            toc_cutoff_index=toc_cutoff_index,
            is_primary_body_anchor=_is_primary_body_anchor_section(
                section_key=str(entry["section_key"]),
                section_obj=entry["section_obj"],
            ),
        )

    # 复杂逻辑说明：修复 section 乱序 bug，仅按"文档出现顺序 + 原始序号"排序，
    # 不做 title/语义重排，保证输出与阅读路径一致。
    # None 值排到末尾：先用 bool 标记把 None 排后，再用 float("inf") 作为数值占位
    section_entries.sort(
        key=lambda item: (
            item["anchor_sequence"] is None,
            item["anchor_sequence"] if item["anchor_sequence"] is not None else float("inf"),
            item["appearance_index"] is None,
            item["appearance_index"] if item["appearance_index"] is not None else float("inf"),
            item["original_index"],
        )
    )

    sections: list[_SectionBlock] = []
    for normalized_index, entry in enumerate(section_entries, start=1):
        sections.append(
            _SectionBlock(
                ref=_format_section_ref(normalized_index),
                title=entry["title"],
                level=1,
                parent_ref=None,
                preview=entry["section_text"][:_PREVIEW_MAX_CHARS],
                text=entry["section_text"],
                table_refs=[],
                table_fingerprints=entry["table_fingerprints"],
                # Step 13: 只有 1 个 section 时，该 section 包含全部文本
                contains_full_text=len(section_entries) == 1,
            )
        )
    return sections


def _build_sections_fast(
    *,
    document: Any,
    section_items: list[tuple[str, Any]],
    single_full_text: bool = False,
    full_text_override: Optional[str] = None,
) -> list[_SectionBlock]:
    """快速构建章节列表（避免逐章节全文定位）。

    该路径面向大体量文档的性能场景，核心策略是：
    1. 保留 section 文本、标题、表格指纹等必要信息；
    2. 仅使用 ``anchor_sequence``（若存在）和原始序号排序；
    3. 跳过 marker/anchor 在全文中的多轮定位扫描。

    Args:
        document: edgartools 文档对象。
        section_items: 章节原始键值对列表。
        single_full_text: 是否将全文合并为单章节。
        full_text_override: 可选预加载全文文本。

    Returns:
        章节块列表。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    if single_full_text:
        return _build_single_full_text_section(document, full_text_override=full_text_override)

    section_entries: list[dict[str, Any]] = []
    for original_index, (section_key, section_obj) in enumerate(section_items, start=1):
        section_text = _normalize_whitespace(_safe_section_text(section_obj))
        title = _build_section_title(section_key=section_key, section_obj=section_obj)
        table_fingerprints = _extract_section_table_fingerprints(section_obj)
        section_entries.append(
            {
                "original_index": original_index,
                "title": title,
                "section_text": section_text,
                "table_fingerprints": table_fingerprints,
                "anchor_sequence": _resolve_section_anchor_sequence(
                    document=document,
                    section_key=section_key,
                ),
            }
        )

    # 复杂逻辑说明：快速模式不做全文 appearance 定位，按锚点序号优先、
    # 原始序号兜底，兼顾稳定顺序与性能。
    section_entries.sort(
        key=lambda item: (
            item["anchor_sequence"] is None,
            item["anchor_sequence"] if item["anchor_sequence"] is not None else float("inf"),
            item["original_index"],
        )
    )

    sections: list[_SectionBlock] = []
    for normalized_index, entry in enumerate(section_entries, start=1):
        sections.append(
            _SectionBlock(
                ref=_format_section_ref(normalized_index),
                title=entry["title"],
                level=1,
                parent_ref=None,
                preview=entry["section_text"][:_PREVIEW_MAX_CHARS],
                text=entry["section_text"],
                table_refs=[],
                table_fingerprints=entry["table_fingerprints"],
                contains_full_text=len(section_entries) == 1,
            )
        )
    return sections


def _build_single_full_text_section(
    document: Any,
    *,
    full_text_override: Optional[str] = None,
) -> list[_SectionBlock]:
    """构建"单全文章节"列表。

    Args:
        document: edgartools 文档对象。
        full_text_override: 可选预加载全文文本。

    Returns:
        仅包含一个章节的列表，该章节承载完整文本。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    raw_full_text = full_text_override if full_text_override is not None else _safe_document_text(document)
    # 性能关键：单全文章节模式保留原始文本，避免对超大 20-F 全文执行
    # 全量 whitespace 归一化（该步骤在大文档上可能占用数十秒）。
    full_text = str(raw_full_text or "").strip()
    return [
        _SectionBlock(
            ref=_format_section_ref(1),
            title=None,
            level=1,
            parent_ref=None,
            preview=full_text[:_PREVIEW_MAX_CHARS],
            text=full_text,
            table_refs=[],
            table_fingerprints=set(),
            contains_full_text=True,
        )
    ]


def _locate_section_appearance(
    *,
    marker_occurrences: list[int],
    anchor_occurrences: list[int],
    body_anchor_index: Optional[int],
    toc_cutoff_index: Optional[int],
    is_primary_body_anchor: bool,
) -> Optional[int]:
    """定位章节出现位置。

    Args:
        marker_occurrences: 章节正文 marker 命中位置（已排序去重）。
        anchor_occurrences: 章节锚点命中位置（已排序去重）。
        body_anchor_index: 文档正文起始锚点位置（通常来自 `Part I Item 1`）。
        toc_cutoff_index: 目录截止位置（`table of contents + buffer`）。
        is_primary_body_anchor: 当前章节是否为正文起始锚点章节。

    Returns:
        出现位置索引；无法定位时返回 `None`。

    Raises:
        RuntimeError: 定位失败时抛出。
    """

    filtered_markers = _filter_occurrences_by_body_anchor(
        occurrences=marker_occurrences,
        body_anchor_index=body_anchor_index,
        toc_cutoff_index=toc_cutoff_index,
        is_primary_body_anchor=is_primary_body_anchor,
    )
    if filtered_markers:
        return filtered_markers[0]

    filtered_anchors = _filter_occurrences_by_body_anchor(
        occurrences=anchor_occurrences,
        body_anchor_index=body_anchor_index,
        toc_cutoff_index=toc_cutoff_index,
        is_primary_body_anchor=is_primary_body_anchor,
    )
    if filtered_anchors:
        return filtered_anchors[0]
    return None


def _collect_section_appearance_candidates(
    *,
    document_text: str,
    section_key: str,
    section_obj: Any,
    section_text: str,
) -> tuple[list[int], list[int]]:
    """采集 section 在全文中的候选命中位置。

    Args:
        document_text: 归一化后的文档全文。
        section_key: 章节键名。
        section_obj: 章节对象。
        section_text: 章节正文。

    Returns:
        `(marker_occurrences, anchor_occurrences)`：
        - marker 命中位置（按正文前缀）
        - anchor 命中位置（按 Part/Item/标题锚点）

    Raises:
        RuntimeError: 采集失败时抛出。
    """

    if not document_text:
        return [], []

    marker_occurrences: list[int] = []
    for marker in _build_section_text_markers(section_text):
        marker_occurrences.extend(_find_text_occurrences(document_text=document_text, phrase=marker))
    marker_occurrences = sorted(set(marker_occurrences))

    anchor_occurrences: list[int] = []
    for anchor in _build_section_anchor_candidates(section_key=section_key, section_obj=section_obj):
        anchor_occurrences.extend(_find_anchor_occurrences(document_text=document_text, anchor=anchor))
    anchor_occurrences = sorted(set(anchor_occurrences))
    return marker_occurrences, anchor_occurrences


def _resolve_document_body_anchor_index(section_entries: list[dict[str, Any]]) -> Optional[int]:
    """解析文档正文起始锚点位置。

    Args:
        section_entries: `_build_sections` 阶段采集的 section entry 列表。

    Returns:
        正文锚点位置；无法解析时返回 `None`。

    Raises:
        RuntimeError: 解析失败时抛出。
    """

    body_anchor_candidates: list[int] = []
    for entry in section_entries:
        if not _is_primary_body_anchor_section(
            section_key=str(entry.get("section_key", "")),
            section_obj=entry.get("section_obj"),
        ):
            continue
        marker_occurrences = entry.get("marker_occurrences")
        if isinstance(marker_occurrences, list) and marker_occurrences:
            body_anchor_candidates.append(int(marker_occurrences[0]))
            continue
        anchor_occurrences = entry.get("anchor_occurrences")
        if isinstance(anchor_occurrences, list) and anchor_occurrences:
            body_anchor_candidates.append(int(anchor_occurrences[0]))
    if not body_anchor_candidates:
        return None
    return min(body_anchor_candidates)


def _resolve_section_anchor_sequence(*, document: Any, section_key: str) -> Optional[int]:
    """从 `get_sec_section_info` 解析章节锚点序号。

    Args:
        document: edgartools 文档对象。
        section_key: 章节键名。

    Returns:
        锚点序号（整数）；无法解析时返回 `None`。

    Raises:
        RuntimeError: 解析失败时抛出。
    """

    info_method = getattr(document, "get_sec_section_info", None)
    if not callable(info_method):
        return None
    try:
        info = info_method(section_key)
    except Exception:
        return None
    if not isinstance(info, dict):
        return None
    anchor_id = _normalize_optional_string(info.get("anchor_id"))
    if not anchor_id:
        return None
    match = _SECTION_ANCHOR_SEQUENCE_PATTERN.search(anchor_id)
    if match is None:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _resolve_toc_cutoff_index(document_text: str) -> Optional[int]:
    """解析目录截止位置。

    Args:
        document_text: 归一化后的文档全文。

    Returns:
        目录截止位置（`table of contents` 最后一次命中 + buffer）；未命中返回 `None`。

    Raises:
        RuntimeError: 解析失败时抛出。
    """

    if not document_text:
        return None
    last_index = document_text.rfind(_TABLE_OF_CONTENTS_TOKEN)
    if last_index < 0:
        return None
    return last_index + _TOC_CUTOFF_BUFFER_CHARS


def _is_primary_body_anchor_section(*, section_key: str, section_obj: Any) -> bool:
    """判断章节是否可作为正文起始锚点（`Part I Item 1`）。

    Args:
        section_key: 章节键名。
        section_obj: 章节对象。

    Returns:
        命中正文起始锚点章节返回 `True`。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    normalized_key = str(section_key or "").strip().lower()
    if normalized_key in {"part_i_item_1", "part1_item1", "part_i_item_1."}:
        return True
    part = _normalize_optional_string(getattr(section_obj, "part", None))
    item = _normalize_optional_string(getattr(section_obj, "item", None))
    if not part or not item:
        return False
    return part.upper() == "I" and item.upper() == "1"


def _filter_occurrences_by_body_anchor(
    *,
    occurrences: list[int],
    body_anchor_index: Optional[int],
    toc_cutoff_index: Optional[int],
    is_primary_body_anchor: bool,
) -> list[int]:
    """按正文锚点过滤候选命中位置。

    Args:
        occurrences: 原始候选位置（已排序）。
        body_anchor_index: 正文起始锚点位置。
        toc_cutoff_index: 目录截止位置。
        is_primary_body_anchor: 当前章节是否正文锚点章节。

    Returns:
        过滤后的候选位置列表。

    Raises:
        RuntimeError: 过滤失败时抛出。
    """

    if not occurrences:
        return []
    if body_anchor_index is None:
        if toc_cutoff_index is None or is_primary_body_anchor:
            return occurrences
        return [position for position in occurrences if position >= toc_cutoff_index]
    if is_primary_body_anchor:
        return occurrences
    lower_bound = max(body_anchor_index, toc_cutoff_index) if toc_cutoff_index is not None else body_anchor_index
    return [position for position in occurrences if position >= lower_bound]


def _build_section_text_markers(section_text: str) -> list[str]:
    """构建章节正文定位 marker 列表。

    Args:
        section_text: 章节正文文本。

    Returns:
        marker 列表（按"长到短"优先）。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    normalized_text = _normalize_searchable_text(section_text)
    if not normalized_text:
        return []
    words = normalized_text.split()
    if not words:
        return []

    markers: list[str] = []
    seen: set[str] = set()
    for word_count in _SECTION_MARKER_WORD_COUNTS:
        if len(words) < word_count:
            continue
        marker = " ".join(words[:word_count]).strip()
        if len(marker) < _SECTION_MARKER_MIN_CHARS:
            continue
        if marker in seen:
            continue
        seen.add(marker)
        markers.append(marker)
    if markers:
        return markers

    fallback_marker = " ".join(words[: min(10, len(words))]).strip()
    if len(fallback_marker) >= 40:
        return [fallback_marker]
    return []


def _build_section_anchor_candidates(*, section_key: str, section_obj: Any) -> list[str]:
    """构建章节锚点候选词。

    Args:
        section_key: 章节键名。
        section_obj: 章节对象。

    Returns:
        锚点候选列表。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    candidates: list[str] = []
    part = _normalize_optional_string(getattr(section_obj, "part", None))
    item = _normalize_optional_string(getattr(section_obj, "item", None))
    if part and item:
        candidates.append(f"part {part} item {item}")
    if item:
        candidates.append(f"item {item}")

    key_anchor = _normalize_optional_string(section_key.replace("_", " "))
    if key_anchor:
        candidates.append(key_anchor)

    title = _normalize_optional_string(getattr(section_obj, "title", None))
    if title:
        candidates.append(title)

    normalized_candidates: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = _normalize_searchable_text(candidate)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_candidates.append(normalized)
    return normalized_candidates


def _find_text_occurrences(*, document_text: str, phrase: str, max_matches: int = 8) -> list[int]:
    """定位短语在文档中的出现位置。

    Args:
        document_text: 归一化后的全文。
        phrase: 归一化后的短语文本。
        max_matches: 最大命中数量。

    Returns:
        升序命中位置列表。

    Raises:
        RuntimeError: 定位失败时抛出。
    """

    if not phrase or max_matches <= 0:
        return []
    matches: list[int] = []
    start = 0
    while len(matches) < max_matches:
        index = document_text.find(phrase, start)
        if index < 0:
            break
        matches.append(index)
        start = index + max(1, len(phrase))
    return matches


def _find_anchor_occurrences(*, document_text: str, anchor: str, max_matches: int = 12) -> list[int]:
    """在文档中定位锚点出现位置。

    Args:
        document_text: 归一化后的全文。
        anchor: 归一化后的锚点文本。
        max_matches: 最大命中数量。

    Returns:
        升序命中位置列表。

    Raises:
        RuntimeError: 定位失败时抛出。
    """

    if not anchor or max_matches <= 0:
        return []
    pattern = _compile_anchor_occurrence_pattern(anchor)
    matches: list[int] = []
    for match in pattern.finditer(document_text):
        matches.append(match.start())
        if len(matches) >= max_matches:
            break
    return matches


@lru_cache(maxsize=2048)
def _compile_anchor_occurrence_pattern(anchor: str) -> re.Pattern[str]:
    """编译锚点匹配正则并缓存。

    Args:
        anchor: 已规范化锚点文本。

    Returns:
        可复用的正则表达式对象。

    Raises:
        re.error: 正则编译失败时抛出。
    """

    return re.compile(rf"\b{re.escape(anchor)}\b")


def _normalize_searchable_text(text: str) -> str:
    """标准化用于定位搜索的文本。

    Args:
        text: 原始文本。

    Returns:
        归一化小写文本。

    Raises:
        RuntimeError: 标准化失败时抛出。
    """

    normalized = _normalize_whitespace(text)
    normalized = normalized.replace("'", "'").replace("`", "'")
    normalized = normalized.replace("\u201c", '"').replace("\u201d", '"')
    return normalized.lower()


# ---------------------------------------------------------------------------
# 依赖的辅助函数
# ---------------------------------------------------------------------------


def _iter_sections(document: Any) -> list[tuple[str, Any]]:
    """安全遍历文档章节。

    Args:
        document: edgartools 文档对象。

    Returns:
        `(section_key, section_obj)` 列表。

    Raises:
        RuntimeError: 访问失败时抛出。
    """

    sections_obj = getattr(document, "sections", None)
    if not isinstance(sections_obj, dict):
        return []
    return [(str(key), value) for key, value in sections_obj.items()]


def _safe_document_text(document: Any) -> str:
    """安全读取文档全文。

    Args:
        document: edgartools 文档对象。

    Returns:
        文本内容。

    Raises:
        RuntimeError: 读取失败时抛出。
    """

    try:
        text = document.text()
    except Exception:
        return ""
    return str(text or "")


def _safe_section_text(section_obj: Any) -> str:
    """安全读取章节文本。

    Args:
        section_obj: 章节对象。

    Returns:
        章节文本。

    Raises:
        RuntimeError: 读取失败时抛出。
    """

    try:
        text = section_obj.text()
    except Exception:
        return ""
    return str(text or "")


def _safe_table_text(table_obj: Any) -> str:
    """安全读取表格文本。

    Args:
        table_obj: 表格对象。

    Returns:
        表格文本。

    Raises:
        RuntimeError: 读取失败时抛出。
    """

    try:
        text = table_obj.text()
    except Exception:
        return ""
    return str(text or "")


def _normalize_table_objects(table_objects: Iterable[_TableTextLike] | None) -> list[_TableTextLike]:
    """将动态表格结果收敛为可安全遍历的对象列表。

    Args:
        table_objects: 动态表格返回值。

    Returns:
        可安全遍历的表格对象列表；非法输入返回空列表。

    Raises:
        无。
    """

    if isinstance(table_objects, Iterable) and not isinstance(table_objects, (str, bytes)):
        return list(table_objects)
    return []


def _build_section_title(section_key: str, section_obj: Any) -> Optional[str]:
    """构建可读章节标题。

    Args:
        section_key: section 字典键。
        section_obj: section 对象。

    Returns:
        可读标题；无可用信息时返回 `None`。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    title = _normalize_optional_string(getattr(section_obj, "title", None))
    name = _normalize_optional_string(getattr(section_obj, "name", None))
    part = _normalize_optional_string(getattr(section_obj, "part", None))
    item = _normalize_optional_string(getattr(section_obj, "item", None))

    if part and item:
        return f"Part {part} Item {item}"
    if title:
        return title
    if name:
        return name
    normalized_key = _normalize_optional_string(section_key)
    return normalized_key


def _extract_section_table_fingerprints(section_obj: Any) -> set[str]:
    """提取 section 中表格的文本指纹集合。

    Args:
        section_obj: section 对象。

    Returns:
        指纹集合。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    table_fingerprints: set[str] = set()
    table_method = getattr(section_obj, "tables", None)
    if not callable(table_method):
        return table_fingerprints
    try:
        raw_section_tables = table_method()
    except Exception:
        return table_fingerprints
    if not isinstance(raw_section_tables, Iterable) or isinstance(raw_section_tables, (str, bytes)):
        return table_fingerprints
    section_tables: list[_TableTextLike] = []
    for table_obj in raw_section_tables:
        if not isinstance(table_obj, _TableTextLike):
            continue
        section_tables.append(table_obj)
    for table_obj in _normalize_table_objects(section_tables):
        fingerprint = _table_fingerprint(_normalize_whitespace(_safe_table_text(table_obj)))
        if fingerprint:
            table_fingerprints.add(fingerprint)
    return table_fingerprints


def _table_fingerprint(text: str) -> str:
    """计算表格文本指纹。

    Args:
        text: 表格文本。

    Returns:
        归一化指纹字符串。

    Raises:
        RuntimeError: 计算失败时抛出。
    """

    normalized = _normalize_whitespace(text)
    if not normalized:
        return ""
    return normalized[:_TABLE_FINGERPRINT_MAX_CHARS].lower()


def _normalize_optional_string(value: Any) -> Optional[str]:
    """将任意值转为可选字符串，额外处理 pandas NaN/NaT。

    对 ``None``、空字符串、``float('nan')``、``pd.NaT`` 等无意义值统一返回 ``None``。

    Args:
        value: 任意输入值。

    Returns:
        标准化字符串；空值返回 ``None``。
    """
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return _normalize_optional_string_base(value)
