"""DEF 14A 表单公共常量与 marker 构建逻辑。

本模块提取 DEF 14A 相关的共享常量和 marker 函数，供
``Def14AFormProcessor``（edgartools 路线）和
``BsDef14AFormProcessor``（BeautifulSoup 路线）共同使用。

两侧处理器均从本模块 import，互不依赖，保持架构独立。
"""

from __future__ import annotations

import re
from typing import Optional

from .sec_form_section_common import (
    SIGNATURE_PATTERN as _SIGNATURE_PATTERN,
    _dedupe_markers,
    _find_lettered_marker_after,
    _find_marker_after,
)

_DEF14A_PROPOSAL_PATTERN = re.compile(r"(?i)\bproposal(?:\s+no\.?)?\s*([1-9]\d?)\b")
_DEF14A_ANNEX_PATTERN = re.compile(r"(?i)\bannex\s+([A-Z])\b")
_DEF14A_APPENDIX_PATTERN = re.compile(r"(?i)\bappendix\s+([A-Z])\b")
_DEF14A_SECTION_MARKERS = (
    ("Proxy Statement Summary", re.compile(r"(?i)\bproxy statement summary\b")),
    ("Executive Compensation", re.compile(r"(?i)\bexecutive compensation\b")),
    (
        "Directors",
        re.compile(
            r"(?i)\b(?:nominees?\s+to\s+.*board\s+of\s+directors|board\s+of\s+directors|directors)\b"
        ),
    ),
    ("Security Ownership", re.compile(r"(?i)\bsecurity ownership\b")),
    ("Audit Matters", re.compile(r"(?i)\baudit(?: and finance committee| committee| matters)?\b")),
    ("Shareholder Proposals", re.compile(r"(?i)\bshareholder proposals?\b")),
    ("Questions and Answers", re.compile(r"(?i)\bquestions?\s+and\s+answers?\b")),
    ("Voting Procedures", re.compile(r"(?i)\bvoting procedures\b")),
)

# DEF 14A 支持的表单类型集合
_DEF14A_FORMS = frozenset({"DEF 14A"})


def _build_def14a_markers(full_text: str) -> list[tuple[int, Optional[str]]]:
    """构建 DEF 14A 专项边界。

    切分策略：
    1. 以 `Proposal No. N` 作为主轴。
    2. 叠加治理章节强标题（如 Executive Compensation）。
    3. 在尾段识别 `Annex/Appendix/SIGNATURE`。
    4. 若有效标记不足，返回空列表触发父类回退。

    Args:
        full_text: 文档全文。

    Returns:
        标记列表。

    Raises:
        RuntimeError: 构建失败时抛出。
    """

    markers: list[tuple[int, Optional[str]]] = []
    proposal_markers = _select_def14a_proposal_markers(full_text)
    markers.extend((position, f"Proposal No. {proposal_no}") for proposal_no, position in proposal_markers)

    for title, pattern in _DEF14A_SECTION_MARKERS:
        match = pattern.search(full_text)
        if match is None:
            continue
        # 将治理类强标题并入主 marker 集合，提升 DEF 14A 章节可读性。
        markers.append((int(match.start()), title))

    # 尾段标记从已识别章节之后开始，减少与前文重复命中。
    tail_cursor = max((position for position, _ in markers), default=0)
    annex_marker = _find_lettered_marker_after(
        _DEF14A_ANNEX_PATTERN,
        full_text,
        tail_cursor,
        "Annex",
    )
    appendix_marker = _find_lettered_marker_after(
        _DEF14A_APPENDIX_PATTERN,
        full_text,
        tail_cursor,
        "Appendix",
    )
    signature_marker = _find_marker_after(
        _SIGNATURE_PATTERN,
        full_text,
        tail_cursor,
        "SIGNATURE",
    )
    if annex_marker is not None:
        markers.append(annex_marker)
    if appendix_marker is not None:
        markers.append(appendix_marker)
    if signature_marker is not None:
        markers.append(signature_marker)

    deduped_markers = _dedupe_markers(markers)
    if len(deduped_markers) < 3:
        return []
    return deduped_markers


def _select_def14a_proposal_markers(full_text: str) -> list[tuple[int, int]]:
    """选择 DEF 14A 的 Proposal 编号边界。

    Args:
        full_text: 文档全文。

    Returns:
        `(proposal_no, start_index)` 列表。

    Raises:
        RuntimeError: 选择失败时抛出。
    """

    matches: list[tuple[int, int]] = []
    for match in _DEF14A_PROPOSAL_PATTERN.finditer(full_text):
        proposal_no = int(match.group(1))
        matches.append((proposal_no, int(match.start())))
    if not matches:
        return []

    selected: list[tuple[int, int]] = []
    cursor = 0
    unique_numbers = sorted({item_no for item_no, _ in matches})
    for proposal_no in unique_numbers:
        found_position = _find_proposal_position_after(matches, proposal_no, cursor)
        if found_position is None:
            continue
        selected.append((proposal_no, found_position))
        cursor = found_position + 1
    return selected


def _find_proposal_position_after(
    matches: list[tuple[int, int]],
    target_proposal_no: int,
    cursor: int,
) -> Optional[int]:
    """查找指定 Proposal 在 cursor 之后的首次位置。

    Args:
        matches: 全部匹配结果。
        target_proposal_no: 目标 Proposal 编号。
        cursor: 起始游标位置。

    Returns:
        命中位置；未命中返回 `None`。

    Raises:
        RuntimeError: 查找失败时抛出。
    """

    for proposal_no, position in matches:
        if proposal_no != target_proposal_no:
            continue
        if position < cursor:
            continue
        return position
    return None
