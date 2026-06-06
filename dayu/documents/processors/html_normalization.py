"""HTML 轻量规范化工具。

本模块只负责把已抽取的正文 HTML 规范化为更适合 Markdown 渲染的片段，
不承担正文选择或站点级特判职责。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup, Comment, Tag
from bs4.element import NavigableString


_REMOVE_TAGS = ("script", "style", "noscript", "template", "svg", "canvas", "iframe")
_RENAME_TAGS = {
    "b": "strong",
    "i": "em",
}
_DROP_TAGS_KEEP_CHILDREN = {"html", "body", "main", "article", "section"}
_PRESERVED_ATTRS: dict[str, set[str]] = {
    "a": {"href", "title"},
    "th": {"colspan", "rowspan", "scope"},
    "td": {"colspan", "rowspan"},
}
_EMPTY_TEXT_TAGS = {"p", "div", "span", "section", "article", "li", "blockquote"}


@dataclass(frozen=True)
class NormalizedHtmlResult:
    """规范化后的 HTML 结果。"""

    html: str
    normalization_applied: bool
    content_stats: dict[str, Any]


def normalize_html_fragment(html: str) -> NormalizedHtmlResult:
    """规范化正文 HTML 片段。"""

    soup = BeautifulSoup(html or "", "html.parser")
    changed = False

    for comment in soup.find_all(string=lambda item: isinstance(item, Comment)):
        comment.extract()
        changed = True

    for tag_name in _REMOVE_TAGS:
        for node in soup.find_all(tag_name):
            node.decompose()
            changed = True

    for old_name, new_name in _RENAME_TAGS.items():
        for node in soup.find_all(old_name):
            node.name = new_name
            changed = True

    for node in soup.find_all(True):
        if node.name in _DROP_TAGS_KEEP_CHILDREN:
            node.unwrap()
            changed = True
            continue
        if _strip_meaningless_attrs(node):
            changed = True

    if _remove_empty_nodes(soup):
        changed = True
    if _collapse_redundant_line_breaks(soup):
        changed = True

    normalized_html = soup.decode().strip()
    return NormalizedHtmlResult(
        html=normalized_html,
        normalization_applied=changed,
        content_stats={
            "tag_count": len(soup.find_all(True)),
            "text_length": len(soup.get_text(" ", strip=True)),
        },
    )


def _strip_meaningless_attrs(node: Tag) -> bool:
    """删除与正文结构无关的属性。"""

    preserved = _PRESERVED_ATTRS.get(node.name, set())
    removable_keys = [key for key in list(node.attrs.keys()) if key not in preserved]
    if not removable_keys:
        return False
    for key in removable_keys:
        node.attrs.pop(key, None)
    return True


def _remove_empty_nodes(soup: BeautifulSoup) -> bool:
    """删除无文本且无结构价值的空节点。"""

    changed = False
    for node in list(soup.find_all(True)):
        if node.name not in _EMPTY_TEXT_TAGS:
            continue
        if node.find(True) is not None:
            continue
        if node.get_text(" ", strip=True):
            continue
        node.decompose()
        changed = True
    return changed


def _collapse_redundant_line_breaks(soup: BeautifulSoup) -> bool:
    """收敛重复换行容器。"""

    changed = False
    for parent in soup.find_all(True):
        consecutive_breaks = 0
        for child in list(parent.children):
            if isinstance(child, NavigableString):
                continue
            if not isinstance(child, Tag):
                continue
            if child.name == "br":
                consecutive_breaks += 1
                if consecutive_breaks > 2:
                    child.decompose()
                    changed = True
                continue
            consecutive_breaks = 0
    return changed

