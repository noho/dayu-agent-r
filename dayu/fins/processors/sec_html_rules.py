"""SEC/EDGAR HTML 规则真源。

该模块集中承接财报 HTML 解析阶段的 SEC/EDGAR 领域规则，供 Fins
处理器复用。Engine 不应直接依赖这里的 helper。
"""

from __future__ import annotations

import re

from dayu.documents.processors.text_utils import normalize_whitespace as _normalize_whitespace

_SECTION_HEADING_TABLE_PATTERN = re.compile(
    r"Item\s+\d+[A-Z]?\b.*[━──\-]{4,}", re.IGNORECASE
)
_SEC_COVER_KEYWORDS = frozenset(
    {
        "annual report pursuant",
        "transition report pursuant",
        "section 13 or 15(d)",
        "securities exchange act",
        "commission file number",
    }
)
_EDGAR_HTML_START_PATTERN = re.compile(r"<html[\s>]", re.IGNORECASE)
_EDGAR_SGML_SUFFIX_PATTERN = re.compile(
    r"</TEXT>\s*</DOCUMENT>\s*$", re.IGNORECASE
)


def strip_edgar_sgml_envelope(content: str) -> str:
    """剥离 EDGAR SGML 信封标签。

    SEC EDGAR 的 exhibit HTML 可能被 ``<DOCUMENT><TEXT>`` 等 SGML 元数据
    包裹。该函数会截取真正的 HTML 起始位置，并移除尾部 SGML 关闭标签。

    Args:
        content: 原始 HTML 文件内容。

    Returns:
        去除 SGML 信封后的 HTML 内容；若未检测到信封则原样返回。

    Raises:
        无。
    """

    html_start = _EDGAR_HTML_START_PATTERN.search(content)
    if html_start and html_start.start() > 0:
        content = content[html_start.start():]
        content = _EDGAR_SGML_SUFFIX_PATTERN.sub("", content)
    return content


def is_sec_section_heading_table(text: str) -> bool:
    """判断文本是否命中 SEC 章节横线表。

    该规则用于识别形如 ``Item 7. Management Discussion ----`` 的目录/标题
    表格，这类表格属于版式噪声而非数据表。

    Args:
        text: 表格文本。

    Returns:
        是否命中 SEC 章节横线表模式。

    Raises:
        无。
    """

    return bool(_SECTION_HEADING_TABLE_PATTERN.search(text))


def is_sec_cover_page_table(text: str) -> bool:
    """判断表格文本是否为 SEC 封面页元数据。

    规则覆盖两类低价值封面表：
    1. 法律声明、注册信息等封面关键词。
    2. 勾选框密集的封面表。

    Args:
        text: 表格文本。

    Returns:
        是否为 SEC 封面页元数据表。

    Raises:
        无。
    """

    normalized_text = _normalize_whitespace(text)
    lowered = normalized_text.lower()
    if any(keyword in lowered for keyword in _SEC_COVER_KEYWORDS):
        return True
    checkbox_count = normalized_text.count("☒") + normalized_text.count("☐")
    if checkbox_count >= 2 and checkbox_count / max(len(normalized_text.split()), 1) > 0.1:
        return True
    return False


def is_sec_layout_table(row_count: int, text: str) -> bool:
    """判断表格是否应按 SEC 版式噪声处理。

    Args:
        row_count: 表格行数。
        text: 表格文本。

    Returns:
        若表格属于章节横线表，或属于少行封面元数据表，则返回 ``True``。

    Raises:
        无。
    """

    normalized_text = _normalize_whitespace(text)
    if is_sec_section_heading_table(normalized_text):
        return True
    if row_count <= 5 and is_sec_cover_page_table(normalized_text):
        return True
    return False