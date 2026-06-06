"""8-K 表单公共常量与 marker 构建逻辑。

本模块提取 8-K 相关的共享常量和 marker 函数，供
``EightKFormProcessor``（edgartools 路线）和
``BsEightKFormProcessor``（BeautifulSoup 路线）共同使用。

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

# 8-K Item 编号正则：匹配 "Item 1.01" / "Item 9.01" 等格式（X.XX）
_EIGHT_K_ITEM_PATTERN = re.compile(r"(?i)\bitem\s+(\d{1,2}\.\d{2})\b")

# 8-K 支持的表单类型集合
_EIGHT_K_FORMS = frozenset({"8-K", "8-K/A"})


def _build_eight_k_markers(full_text: str) -> list[tuple[int, Optional[str]]]:
    """构建 8-K Item + Signature 边界。

    Args:
        full_text: 文档全文。

    Returns:
        标记列表。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    markers: list[tuple[int, Optional[str]]] = []
    seen_items: set[str] = set()
    for match in _EIGHT_K_ITEM_PATTERN.finditer(full_text):
        item_no = match.group(1).strip()
        if not item_no:
            continue
        if item_no in seen_items:
            continue
        seen_items.add(item_no)
        markers.append((int(match.start()), f"Item {item_no}"))
    if not markers:
        return []
    signature_marker = _find_marker_after(
        _SIGNATURE_PATTERN,
        full_text,
        markers[-1][0],
        "SIGNATURE",
    )
    if signature_marker is not None:
        markers.append(signature_marker)
    return _dedupe_markers(markers)
