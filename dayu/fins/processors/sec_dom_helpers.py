"""SEC 文档 DOM/HTML 解析工具函数。

从原始 HTML 中提取纯文本、表格前文等结构化信息，
供 SecProcessor 及表格构建流程使用。
"""

from __future__ import annotations

from typing import Any, Optional

from bs4 import BeautifulSoup, Comment, Tag
from bs4.element import NavigableString

from dayu.documents.processors.text_utils import (
    PREVIEW_MAX_CHARS as _PREVIEW_MAX_CHARS,
    normalize_whitespace as _normalize_whitespace,
)

_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_HIDDEN_STYLE_TOKENS = ("display:none", "visibility:hidden")
_CONTEXT_NOISE_TAGS = {"style", "script", "head", "title", "meta", "link", "noscript", "template"}


def _extract_text_from_raw_html(html_content: str) -> str:
    """从原始 HTML 提取纯文本，作为 edgartools ``document.text()`` 失败时的回退。

    使用 BeautifulSoup 解析 HTML，针对 iXBRL filing 做专门清理：
    - 移除 ``<ix:header>`` / ``<ix:hidden>``（含 XBRL 上下文定义，体积可达数百KB）
    - 移除 ``display:none`` 隐藏块（通常包裹 XBRL header）
    - 移除 script/style/noscript 等非内容节点

    该方法不依赖 edgartools 的 section 检测，仅做文本提取。

    Args:
        html_content: 原始 HTML 字符串。

    Returns:
        提取的纯文本；解析失败时返回空字符串。
    """

    if not html_content:
        return ""
    try:
        import re as _re
        import warnings
        from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

        soup = BeautifulSoup(html_content, "lxml")
        # 移除 iXBRL header/hidden 块（含 xbrli:context/unit 定义，产生大量噪音文本）
        for tag in soup.find_all(_re.compile(r"^ix:(header|hidden)$")):
            tag.decompose()
        # 移除 display:none 隐藏元素（通常包裹 XBRL 数据块）
        for tag in soup.find_all(style=_re.compile(r"display:\s*none", _re.IGNORECASE)):
            tag.decompose()
        # 移除 script/style/noscript 等非内容节点
        for tag in soup.find_all(["script", "style", "noscript"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)
    except Exception:
        return ""


def _extract_dom_table_contexts(html_content: str, max_chars: int = _PREVIEW_MAX_CHARS) -> list[str]:
    """基于 DOM 顺序提取每张表格的前文。

    Args:
        html_content: 原始 HTML 文本。
        max_chars: 每张表格前文最大长度。

    Returns:
        与 DOM 表格顺序一致的前文列表。

    Raises:
        RuntimeError: 解析失败时抛出。
    """

    soup = BeautifulSoup(html_content, "html.parser")
    root = soup.body if soup.body else soup
    all_tables = root.find_all("table")
    # 预构建 table 标签 id 集合，用于 O(1) 表格包含判断，
    # 避免逐节点 find_parent("table") 的 O(depth) 调用。
    table_tag_ids: frozenset[int] = frozenset(id(t) for t in all_tables)
    contexts: list[str] = []
    for table_tag in all_tables:
        contexts.append(
            _extract_dom_context_before(
                table_tag=table_tag,
                max_chars=max_chars,
                table_tag_ids=table_tag_ids,
            )
        )
    return contexts


def _extract_dom_context_before(
    table_tag: Tag,
    max_chars: int = _PREVIEW_MAX_CHARS,
    table_tag_ids: Optional[frozenset[int]] = None,
) -> str:
    """提取单张表格在 DOM 中的前文。

    Args:
        table_tag: 表格节点。
        max_chars: 最大长度。
        table_tag_ids: 可选的 table 标签 id 集合，用于 O(1) 表格包含判断。

    Returns:
        前文字符串。

    Raises:
        RuntimeError: 提取失败时抛出。
    """

    text_parts: list[str] = []
    total_len = 0
    for node in table_tag.previous_elements:
        if node == table_tag:
            continue
        if _is_noise_context_node(node):
            continue
        if isinstance(node, Tag):
            tag_name = str(node.name or "").lower()
            if tag_name in _HEADING_TAGS:
                break
            if tag_name == "table":
                break
            if _is_hidden_tag(node):
                continue
        if _is_within_table(node, table_tag_ids=table_tag_ids):
            continue
        if isinstance(node, NavigableString):
            text = _normalize_whitespace(str(node))
            if not text:
                continue
            text_parts.append(text)
            total_len += len(text)
            if total_len >= max_chars:
                break
    if not text_parts:
        return ""
    text_parts.reverse()
    full_text = " ".join(text_parts)
    if len(full_text) > max_chars:
        return full_text[-max_chars:]
    return full_text


def _is_noise_context_node(node: Any) -> bool:
    """判断节点是否属于上下文噪声。

    噪声包括样式/脚本/头部标签中的文本，以及 HTML 注释内容。

    Args:
        node: BeautifulSoup 节点。

    Returns:
        是否应在上下文提取中忽略。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    if isinstance(node, Comment):
        return True
    if isinstance(node, Tag):
        return str(node.name or "").lower() in _CONTEXT_NOISE_TAGS
    if isinstance(node, NavigableString):
        parent = node.parent
        if isinstance(parent, Tag):
            return str(parent.name or "").lower() in _CONTEXT_NOISE_TAGS
    return False


def _is_within_table(node: Any, *, table_tag_ids: Optional[frozenset[int]] = None) -> bool:
    """判断节点是否位于表格内部。

    若提供 ``table_tag_ids``，使用 O(1) 集合查找替代
    ``find_parent("table")`` 的 O(depth) 搜索。

    Args:
        node: BeautifulSoup 节点。
        table_tag_ids: 可选的 table 标签 id 集合。

    Returns:
        是否位于表格内部。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    if table_tag_ids is not None:
        return _is_within_table_fast(node, table_tag_ids)
    if isinstance(node, Tag):
        return node.find_parent("table") is not None or str(node.name).lower() == "table"
    if isinstance(node, NavigableString):
        parent = node.parent
        if isinstance(parent, Tag):
            return parent.find_parent("table") is not None or str(parent.name).lower() == "table"
    return False


def _is_within_table_fast(node: Any, table_tag_ids: frozenset[int]) -> bool:
    """O(1) 集合查找判断节点是否位于表格内部。

    向上遍历 parent 链，检查任一祖先的 ``id()`` 是否在 ``table_tag_ids`` 中。

    Args:
        node: BeautifulSoup 节点。
        table_tag_ids: table 标签 id 集合。

    Returns:
        是否位于表格内部。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    # 对 Tag 节点，自身即 table 则直接判定
    if isinstance(node, Tag) and str(node.name or "").lower() == "table":
        return True
    # 向上遍历 parent 链，在 table_tag_ids 集合中做 O(1) 查找
    current = node.parent if isinstance(node, NavigableString) else node
    while current is not None:
        if isinstance(current, Tag):
            if id(current) in table_tag_ids:
                return True
        current = getattr(current, "parent", None)
    return False


def _is_hidden_tag(tag: Tag) -> bool:
    """判断标签是否为隐藏节点。

    Args:
        tag: 标签节点。

    Returns:
        是否隐藏。

    Raises:
        RuntimeError: 判断失败时抛出。
    """

    style = str(tag.get("style", "")).replace(" ", "").lower()
    if any(token in style for token in _HIDDEN_STYLE_TOKENS):
        return True
    aria_hidden = str(tag.get("aria-hidden", "")).strip().lower()
    if aria_hidden == "true":
        return True
    hidden_attr = tag.get("hidden")
    return hidden_attr is not None
