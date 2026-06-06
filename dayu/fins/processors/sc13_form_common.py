"""SC 13 系列表单公共常量与 marker 构建逻辑。

本模块提取 SC 13D/G 相关的共享常量和 marker 函数，供
``Sc13FormProcessor``（edgartools 路线）和
``BsSc13FormProcessor``（BeautifulSoup 路线）共同使用。

两侧处理器均从本模块 import，互不依赖，保持架构独立。
"""

from __future__ import annotations

import re
from typing import Optional

from .sec_form_section_common import (
    SIGNATURE_PATTERN as _SIGNATURE_PATTERN,
    _dedupe_markers,
    _find_marker_after,
)

# SC 13 Item 匹配：允许 "Item 1."、"Item 1:"、"Item 1(a)"、"Item 1 " 等多种格式
# 使用 \b 单词边界区分 Item 1 与 Item 10+，避免误匹配高编号 Item
_SC13_ITEM_PATTERN = re.compile(r"(?i)\bitem\s+([1-7])\b")
_SCHEDULE_A_PATTERN = re.compile(r"(?i)\bschedule\s+a\b")
_EXHIBIT_PATTERN = re.compile(r"(?i)\bexhibit(?:s)?\b")

# SC 13 支持的表单类型集合
_SC13_FORMS = frozenset({"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"})


def _build_sc13_markers(full_text: str) -> list[tuple[int, Optional[str]]]:
    """构建 SC13 Item + 尾段边界。

    Args:
        full_text: 文档全文。

    Returns:
        标记列表。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    item_markers = _select_sc13_item_markers(full_text)
    if len(item_markers) < 3:
        return []

    markers: list[tuple[int, Optional[str]]] = [
        (position, f"Item {item_no}")
        for item_no, position in item_markers
    ]
    last_item_pos = item_markers[-1][1]
    signature_marker = _find_marker_after(_SIGNATURE_PATTERN, full_text, last_item_pos, "SIGNATURE")
    schedule_marker = _find_marker_after(_SCHEDULE_A_PATTERN, full_text, last_item_pos, "Schedule A")
    exhibit_marker = _find_marker_after(_EXHIBIT_PATTERN, full_text, last_item_pos, "Exhibit")
    if signature_marker is not None:
        markers.append(signature_marker)
    if schedule_marker is not None:
        markers.append(schedule_marker)
    if exhibit_marker is not None:
        markers.append(exhibit_marker)
    return _dedupe_markers(markers)


def _has_sufficient_sc13_markers(content: str) -> bool:
    """判断文本是否含有足够的 SC13 切分标记。

    Args:
        content: 待检测文本。

    Returns:
        可切出至少 3 个 SC13 分段时返回 `True`，否则返回 `False`。

    Raises:
        RuntimeError: 检测失败时抛出。
    """

    if not content:
        return False
    return len(_build_sc13_markers(content)) >= 3


def _select_sc13_item_markers(full_text: str) -> list[tuple[int, int]]:
    """选择 SC13 的 Item 1..7 序列边界。

    Args:
        full_text: 文档全文。

    Returns:
        `(item_no, start_index)` 列表。

    Raises:
        RuntimeError: 选择失败时抛出。
    """

    matches: list[tuple[int, int]] = []
    for match in _SC13_ITEM_PATTERN.finditer(full_text):
        item_no = int(match.group(1))
        matches.append((item_no, int(match.start())))
    if not matches:
        return []

    selected: list[tuple[int, int]] = []
    cursor = 0
    for item_no in range(1, 8):
        found_position = _find_item_position_after(matches, item_no, cursor)
        if found_position is None:
            continue
        selected.append((item_no, found_position))
        cursor = found_position + 1
    return selected


def _find_item_position_after(
    matches: list[tuple[int, int]],
    target_item_no: int,
    cursor: int,
) -> Optional[int]:
    """查找指定 Item 在 cursor 之后的首次位置。

    Args:
        matches: 全部匹配结果。
        target_item_no: 目标 Item 编号。
        cursor: 起始游标位置。

    Returns:
        命中位置；未命中返回 `None`。

    Raises:
        RuntimeError: 查找失败时抛出。
    """

    for item_no, position in matches:
        if item_no != target_item_no:
            continue
        if position < cursor:
            continue
        return position
    return None
