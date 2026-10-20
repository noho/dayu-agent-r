"""原文文本及保真词法结构 owner；不重排 DOM，不把展示文本当作原文。"""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from html import unescape
import re
from collections.abc import Sequence
from typing import Literal

from dayu.contracts.cancellation import CancellationToken
from dayu.documents.processors.source import Source
from dayu.fins.cancellation import raise_if_fins_cancelled
from dayu.fins.domain.original_read_contract import (
    ANCESTORS_MAX,
    ATTRIBUTE_PAGE_MAX,
    PREVIEW_CHARS,
    SCAN_CHECK_INTERVAL,
    ExpandedName,
    OriginalAttribute,
    OriginalDiagnostic,
    OriginalFact,
    OriginalFactsResult,
    OriginalNode,
    OriginalPreview,
    OriginalReference,
    OriginalSpan,
    OriginalStructureResult,
    OriginalTextResult,
    ResolvedQName,
    SourceAssetIdentity,
)
from dayu.fins.processors.source_text import decode_source_bytes

INLINE_URIS = frozenset({"http://www.xbrl.org/2013/inlineXBRL", "http://www.xbrl.org/2008/inlineXBRL"})
XBRLI_URI = "http://www.xbrl.org/2003/instance"
XML_URI = "http://www.w3.org/XML/1998/namespace"
XSI_URI = "http://www.w3.org/2001/XMLSchema-instance"
_HTML_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_P_BLOCK = frozenset(
    "address article aside blockquote div dl fieldset footer form h1 h2 h3 h4 h5 h6 header hr menu nav ol p pre section table ul".split()
)
_OPTIONAL_AT_EOF = frozenset(
    {"html", "head", "body", "p", "li", "dt", "dd", "tr", "td", "th", "tbody", "thead", "tfoot", "colgroup", "option"}
)
_TOKEN = re.compile(
    r'<!--(?:[\s\S]*?-->|[\s\S]*\Z)|<!\[CDATA\[[\s\S]*?(?:\]\]>|\Z)|<![^>]*>|<\?[^>]*\?>|</?[A-Za-z_][^<>\s/]*(?:\s+(?:[^<>"\x27]|"[^"]*"|\x27[^\x27]*\x27)*)?/?>'
)
_TAG_NAME = re.compile(r"</?([^\s/>]+)")
_ATTRIBUTE = re.compile(r'([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|\x27([^\x27]*)\x27|([^\s>]+)))?')
_RAW_END = {name: re.compile(r"</" + name + r"\s*>", re.IGNORECASE) for name in ("script", "style")}
_DIAGNOSTICS_MAX = 100


class OriginalParseError(RuntimeError):
    """原文解析执行失败，不代表完整零命中。"""


def check_original_cancel(token: CancellationToken | None) -> None:
    """参数：本次 token。返回：无。异常：取消时抛出 FinsReadCancelledError。"""
    raise_if_fins_cancelled(token, message="原文读取已被取消。")


def original_capabilities(filename: str, content_type: str | None) -> tuple[bool, bool, bool]:
    """参数：资产名/媒体类型。返回：文本、结构、inline 能力。异常：无。"""
    suffix = filename.rsplit(".", 1)[-1].lower()
    media = (content_type or "").lower().split(";", 1)[0]
    html = suffix in {"htm", "html", "xhtml"} or media in {"text/html", "application/xhtml+xml"}
    xml = suffix == "xml" or media in {"application/xml", "text/xml"}
    text = (
        html
        or xml
        or suffix in {"txt", "md", "markdown", "json"}
        or media.startswith("text/")
        or media == "application/json"
    )
    return text, html or xml, html


@dataclass(slots=True)
class _Attribute:
    """内部原文属性位置；不复制长值。"""

    name: str
    start: int
    end: int
    value_start: int | None
    value_end: int | None
    quote: str | None


@dataclass(slots=True)
class _Node:
    """仅保存原文位置与作用域的内部节点。"""

    kind: Literal["element", "text", "comment", "doctype", "cdata", "processing_instruction"]
    start: int
    opening_end: int
    name: str
    parent: int | None
    namespaces: dict[str, str | None]
    attributes: tuple[_Attribute, ...] = ()
    content_end: int | None = None
    end: int | None = None
    closing_start: int | None = None
    closure: Literal["explicit", "void", "rule", "unknown", "token"] = "unknown"


class OriginalContent:
    """已完成解码的同版文本；不保留任何请求 token、范围或预算。"""

    def __init__(self, source: Source, *, token: CancellationToken | None) -> None:
        """参数：snapshot Source、本次 token。返回：无。异常：I/O、严格解码或取消失败。"""
        check_original_cancel(token)
        with source.open() as stream:
            payload = stream.read()
        check_original_cancel(token)
        self.text = decode_source_bytes(payload)
        self.bom_bytes = 3 if payload.startswith(b"\xef\xbb\xbf") else 0
        check_original_cancel(token)

    def span(self, asset: SourceAssetIdentity, start: int, end: int) -> OriginalSpan:
        """参数：身份和码点范围。返回：公共定位。异常：无。"""
        return {"asset": asset, "start": start, "end": end}

    def preview(self, asset: SourceAssetIdentity, start: int, end: int) -> OriginalPreview:
        """参数：身份和完整范围。返回：有界原文预览及完整定位。异常：无。"""
        return {
            "span": self.span(asset, start, end),
            "preview": self.text[start : min(end, start + PREVIEW_CHARS)],
            "preview_complete": end - start <= PREVIEW_CHARS,
        }

    def read_text(
        self, asset: SourceAssetIdentity, start: int, end: int, max_chars: int, token: CancellationToken | None
    ) -> OriginalTextResult:
        """参数：身份、已校验范围、页预算、本次 token。返回：精确原文页。异常：取消信号。"""
        check_original_cancel(token)
        stop = min(end, start + max_chars)
        result: OriginalTextResult = {
            "asset": asset,
            "encoding": "utf-8",
            "bom_bytes": self.bom_bytes,
            "requested_range": self.span(asset, start, end),
            "returned_range": self.span(asset, start, stop),
            "total_chars": len(self.text),
            "text": self.text[start:stop],
            "truncated": stop < end,
            "next_start": stop if stop < end else None,
        }
        check_original_cancel(token)
        return result


class OriginalStructure:
    """同一原文的完成索引；namespace 由原始声明在定义处解析。"""

    def __init__(self, content: OriginalContent, *, xml: bool, token: CancellationToken | None) -> None:
        """参数：完整文本、XML 严格模式、本次 token。返回：无。异常：取消或词法执行错误。"""
        self.content = content
        self.xml = xml
        self.nodes: list[_Node] = []
        self.reasons: list[tuple[str, int, int]] = []
        self.ids: dict[tuple[str, str], list[int]] = {}
        self.fact_indices: list[int] = []
        self._scan(token)
        self.starts = [node.start for node in self.nodes]
        for index, node in enumerate(self.nodes):
            if index % SCAN_CHECK_INTERVAL == 0:
                check_original_cancel(token)
            if node.kind != "element":
                continue
            expanded_attributes: set[tuple[str, str]] = set()
            for attribute_index, attribute in enumerate(node.attributes):
                if attribute_index % SCAN_CHECK_INTERVAL == 0:
                    check_original_cancel(token)
                if ":" not in attribute.name or attribute.name.startswith("xmlns:"):
                    continue
                attribute_uri, attribute_local = self.expanded(node, attribute.name)
                if attribute_uri is None:
                    self.reasons.append(("unbound_attribute_namespace", attribute.start, attribute.end))
                elif (attribute_uri, attribute_local) in expanded_attributes:
                    self.reasons.append(("duplicate_expanded_attribute", attribute.start, attribute.end))
                else:
                    expanded_attributes.add((attribute_uri, attribute_local))
            identifier = self.value(node, "id")
            if identifier is not None:
                self.ids.setdefault((self.target(index, token), identifier), []).append(index)
            uri, local = self.expanded(node, node.name)
            if uri in INLINE_URIS and local == "nonNumeric":
                self.fact_indices.append(index)
                concept = self.value(node, "name")
                if concept is None or self.expanded(node, concept)[0] is None:
                    self.reasons.append(("unresolved_concept", node.start, node.opening_end))
            elif ":" in node.name and uri is None:
                self.reasons.append(("unbound_element_namespace", node.start, node.opening_end))
        # 引用完整性按整个资产判定，不能因当前分页尚未返回坏 occurrence 而声称完整。
        for index in self.fact_indices:
            check_original_cancel(token)
            node = self.nodes[index]
            for name in ("name", "format"):
                raw_name = self.value(node, name)
                if raw_name is not None and self.expanded(node, raw_name)[0] is None:
                    self.reasons.append(("unbound_fact_qname", node.start, node.opening_end))
            context_id = self.value(node, "contextRef")
            matches = self.ids.get((self.target(index, token), context_id), []) if context_id is not None else []
            if len(matches) != 1 or self.expanded(self.nodes[matches[0]], self.nodes[matches[0]].name) != (
                XBRLI_URI,
                "context",
            ):
                self.reasons.append(("unresolved_or_ambiguous_context", node.start, node.opening_end))
        check_original_cancel(token)

    def value(self, node: _Node, name: str) -> str | None:
        """参数：节点、exact 属性名。返回：唯一属性的解码值；缺失/重复为 None。异常：无。"""
        matches = [a for a in node.attributes if a.name == name]
        if len(matches) != 1 or matches[0].value_start is None or matches[0].value_end is None:
            return None
        return unescape(self.content.text[matches[0].value_start : matches[0].value_end])

    def expanded(self, node: _Node, name: str) -> tuple[str | None, str]:
        """参数：定义节点和 QName。返回：作用域 URI/local name。异常：无。"""
        prefix, separator, local = name.partition(":")
        return (node.namespaces.get(prefix), local) if separator else (node.namespaces.get("", ""), name)

    def target(self, index: int, token: CancellationToken | None) -> str:
        """参数：节点索引、本次 token。返回：技术 target 分组，缺失为默认空组。异常：取消。"""
        current: int | None = index
        depth = 0
        while current is not None:
            if depth % SCAN_CHECK_INTERVAL == 0:
                check_original_cancel(token)
            depth += 1
            node = self.nodes[current]
            uri, local = self.expanded(node, node.name)
            if uri in INLINE_URIS and local in {"resources", "nonNumeric", "continuation"}:
                value = self.value(node, "target")
                if value is not None:
                    return value
                if local == "nonNumeric":
                    return ""
            current = node.parent
        return ""

    def _scan(self, token: CancellationToken | None) -> None:
        """参数：本次 token。返回：无。异常：取消；保全不了关系时记录 partial。"""
        text = self.content.text
        stack: list[int] = []
        position = 0
        counter = 0
        while position < len(text):
            if counter % SCAN_CHECK_INTERVAL == 0:
                check_original_cancel(token)
            counter += 1
            parent = stack[-1] if stack else None
            scope: dict[str, str | None] = self.nodes[parent].namespaces if parent is not None else {"xml": XML_URI}
            raw_parent = self.nodes[parent].name.lower() if parent is not None else ""
            match = (
                _RAW_END[raw_parent].search(text, position)
                if not self.xml and raw_parent in _RAW_END
                else _TOKEN.search(text, position)
            )
            start = match.start() if match else len(text)
            if start > position:
                self.nodes.append(
                    _Node("text", position, start, "", parent, scope, content_end=start, end=start, closure="token")
                )
                if "<" in text[position:start] and raw_parent not in _RAW_END:
                    self.reasons.append(("unrecognized_markup", position, start))
            if match is None:
                break
            end = match.end()
            raw = text[start:end]
            position = end
            if raw.startswith("<!") or raw.startswith("<?"):
                kind: Literal["comment", "doctype", "cdata", "processing_instruction"] = (
                    "comment"
                    if raw.startswith("<!--")
                    else (
                        "cdata"
                        if raw.startswith("<![CDATA[")
                        else "processing_instruction" if raw.startswith("<?") else "doctype"
                    )
                )
                self.nodes.append(_Node(kind, start, end, "", parent, scope, content_end=end, end=end, closure="token"))
                if raw.startswith("<!--") and not raw.endswith("-->"):
                    self.reasons.append(("unterminated_comment", start, end))
                if kind == "cdata" and not raw.endswith("]]>"):
                    self.reasons.append(("unterminated_cdata", start, end))
                continue
            name_match = _TAG_NAME.match(raw)
            if name_match is None:
                raise OriginalParseError("无法识别已匹配的原文标签")
            name = name_match.group(1)
            normalized = name if self.xml else name.lower()
            if raw.startswith("</"):
                found = next(
                    (
                        i
                        for i in range(len(stack) - 1, -1, -1)
                        if (self.nodes[stack[i]].name if self.xml else self.nodes[stack[i]].name.lower()) == normalized
                    ),
                    None,
                )
                if found is None:
                    self.reasons.append(("unmatched_closing_tag", start, end))
                    continue
                while len(stack) - 1 > found:
                    unfinished = self.nodes[stack.pop()]
                    if not self.xml and unfinished.name.lower() in _OPTIONAL_AT_EOF:
                        unfinished.content_end = start
                        unfinished.end = start
                        unfinished.closure = "rule"
                    else:
                        self.reasons.append(("mismatched_nesting", unfinished.start, end))
                node = self.nodes[stack.pop()]
                node.content_end, node.closing_start, node.end, node.closure = start, start, end, "explicit"
                continue
            if not self.xml:
                self._close_optional(stack, normalized, start)
                parent = stack[-1] if stack else None
                scope = self.nodes[parent].namespaces if parent is not None else {"xml": XML_URI}
            attrs: list[_Attribute] = []
            names: set[str] = set()
            namespace_changes: dict[str, str | None] = {}
            for attr_index, attr_match in enumerate(
                _ATTRIBUTE.finditer(raw, name_match.end(), len(raw) - (2 if raw.endswith("/>") else 1))
            ):
                if attr_index % SCAN_CHECK_INTERVAL == 0:
                    check_original_cancel(token)
                attr_name = attr_match.group(1)
                value_group = next((g for g in (2, 3, 4) if attr_match.group(g) is not None), None)
                value_start = start + attr_match.start(value_group) if value_group is not None else None
                value_end = start + attr_match.end(value_group) if value_group is not None else None
                attrs.append(
                    _Attribute(
                        attr_name,
                        start + attr_match.start(),
                        start + attr_match.end(),
                        value_start,
                        value_end,
                        '"' if value_group == 2 else "'" if value_group == 3 else None,
                    )
                )
                if attr_name in names:
                    self.reasons.append(("duplicate_attribute", start, end))
                if attr_name == "xmlns" or attr_name.startswith("xmlns:"):
                    prefix = attr_name.partition(":")[2]
                    namespace_changes[prefix] = (
                        None
                        if attr_name in names or value_start is None or value_end is None
                        else unescape(text[value_start:value_end])
                    )
                names.add(attr_name)
            if namespace_changes:
                scope = {**scope, **namespace_changes}
            node = _Node("element", start, end, name, parent, scope, tuple(attrs))
            self.nodes.append(node)
            if raw.endswith("/>") or not self.xml and normalized in _HTML_VOID:
                node.content_end, node.end, node.closure = end, end, "void"
            else:
                stack.append(len(self.nodes) - 1)
        for index in reversed(stack):
            node = self.nodes[index]
            if not self.xml and node.name.lower() in _OPTIONAL_AT_EOF:
                node.content_end, node.end, node.closure = len(text), len(text), "rule"
            else:
                self.reasons.append(("unclosed_element", node.start, node.opening_end))

    def _close_optional(self, stack: list[int], incoming: str, position: int) -> None:
        """参数：开放父链、新元素、起点。返回：无。异常：无。按 HTML 可省略结束规则闭合。"""
        while stack:
            node = self.nodes[stack[-1]]
            current = node.name.lower()
            closes = (
                current == "p"
                and incoming in _P_BLOCK
                or current == "li"
                and incoming == "li"
                or current in {"dt", "dd"}
                and incoming in {"dt", "dd"}
                or current in {"td", "th"}
                and incoming in {"td", "th", "tr", "thead", "tbody", "tfoot"}
                or current == "tr"
                and incoming in {"tr", "thead", "tbody", "tfoot"}
                or current == "option"
                and incoming in {"option", "optgroup"}
                or current in {"thead", "tbody", "tfoot"}
                and incoming in {"tbody", "tfoot"}
            )
            if not closes:
                break
            stack.pop()
            node.content_end, node.end, node.closure = position, position, "rule"

    def qname(self, node: _Node, raw: str) -> ResolvedQName:
        """参数：节点及原 QName。返回：有界拼写与精确绑定。异常：无。"""
        uri, local = self.expanded(node, raw)
        complete = (
            len(raw) <= PREVIEW_CHARS and (uri is None or len(uri) <= PREVIEW_CHARS) and len(local) <= PREVIEW_CHARS
        )
        return {
            "raw": raw[:PREVIEW_CHARS],
            "namespace_uri": uri[:PREVIEW_CHARS] if uri is not None else None,
            "local_name": local[:PREVIEW_CHARS],
            "status": "ambiguous" if not complete else "resolved" if uri is not None else "unbound",
            "raw_complete": len(raw) <= PREVIEW_CHARS,
            "namespace_uri_complete": uri is None or len(uri) <= PREVIEW_CHARS,
            "local_name_complete": len(local) <= PREVIEW_CHARS,
        }

    def attribute_preview(self, node: _Node, name: str, asset: SourceAssetIdentity) -> OriginalPreview | None:
        """参数：节点、属性名、身份。返回：唯一属性原值预览；缺失/歧义为 None。异常：无。"""
        matches = [attr for attr in node.attributes if attr.name == name]
        if len(matches) != 1:
            return None
        attr = matches[0]
        if attr.value_start is None or attr.value_end is None:
            return None
        return self.content.preview(asset, attr.value_start, attr.value_end)

    def expanded_attribute_preview(
        self, node: _Node, uri: str, local: str, asset: SourceAssetIdentity
    ) -> OriginalPreview | None:
        """参数：节点、标准属性 URI/local、身份。返回：唯一扩展属性原值，不依赖前缀拼写。异常：无。"""
        matches = [a for a in node.attributes if ":" in a.name and self.expanded(node, a.name) == (uri, local)]
        if len(matches) != 1:
            return None
        attribute = matches[0]
        if attribute.value_start is None or attribute.value_end is None:
            return None
        return self.content.preview(asset, attribute.value_start, attribute.value_end)

    def reference(
        self,
        index: int,
        identifier: str | None,
        *,
        context: bool,
        asset: SourceAssetIdentity,
        token: CancellationToken | None,
    ) -> OriginalReference:
        """参数：节点、引用、context 模式、身份/token。返回：同目标唯一引用或明确未决。异常：取消。"""
        if identifier is None:
            return {
                "status": "unresolved" if context else "absent",
                "reason": "missing_context_ref" if context else None,
                "target": None,
            }
        matches = self.ids.get((self.target(index, token), identifier), [])
        expected = "context" if context else "continuation"
        accepted = [
            i
            for i in matches
            if self.expanded(self.nodes[i], self.nodes[i].name)[1] == expected
            and (
                self.expanded(self.nodes[i], self.nodes[i].name)[0] == XBRLI_URI
                if context
                else self.expanded(self.nodes[i], self.nodes[i].name)[0] in INLINE_URIS
            )
        ]
        if len(matches) != 1 or len(accepted) != 1:
            return {
                "status": "ambiguous" if len(matches) > 1 else "unresolved",
                "reason": "duplicate_id" if len(matches) > 1 else "target_not_found",
                "target": None,
            }
        target = self.nodes[accepted[0]]
        if target.end is None:
            return {
                "status": "unresolved",
                "reason": "unknown_target_boundary",
                "target": self.content.preview(asset, target.start, target.opening_end),
            }
        if not context:
            seen = {index}
            cursor = accepted[0]
            while True:
                check_original_cancel(token)
                if cursor in seen:
                    return {
                        "status": "unresolved",
                        "reason": "continuation_cycle",
                        "target": self.content.preview(asset, target.start, target.end),
                    }
                seen.add(cursor)
                next_id = self.value(self.nodes[cursor], "continuedAt")
                if next_id is None:
                    break
                following = self.ids.get((self.target(cursor, token), next_id), [])
                if len(following) != 1:
                    return {
                        "status": "ambiguous" if len(following) > 1 else "unresolved",
                        "reason": "continuation_target_unresolved",
                        "target": self.content.preview(asset, target.start, target.end),
                    }
                cursor = following[0]
                uri, local = self.expanded(self.nodes[cursor], self.nodes[cursor].name)
                if uri not in INLINE_URIS or local != "continuation":
                    return {
                        "status": "unresolved",
                        "reason": "invalid_continuation_target",
                        "target": self.content.preview(asset, target.start, target.end),
                    }
        result: OriginalReference = {
            "status": "resolved",
            "reason": None,
            "target": self.content.preview(asset, target.start, target.end),
        }
        if context:
            result["namespace_uri"] = self.expanded(target, target.name)[0]
            parent = target.parent
            resources: _Node | None = None
            while parent is not None:
                check_original_cancel(token)
                candidate = self.nodes[parent]
                uri, local = self.expanded(candidate, candidate.name)
                if uri in INLINE_URIS and local == "resources":
                    resources = candidate
                    break
                parent = candidate.parent
            result["resource_span"] = (
                self.content.span(asset, resources.start, resources.opening_end) if resources is not None else None
            )
            result["resource_target_raw"] = (
                self.attribute_preview(resources, "target", asset) if resources is not None else None
            )
            result["resource_target_origin"] = (
                "explicit"
                if resources is not None and any(a.name == "target" for a in resources.attributes)
                else "implicit_default"
            )
        return result

    def project_node(self, index: int, asset: SourceAssetIdentity, token: CancellationToken | None) -> OriginalNode:
        """参数：索引、身份、本次 token。返回：有界节点投影及可回读父链。异常：取消。"""
        node = self.nodes[index]
        content = self.content
        ancestors: list[OriginalSpan] = []
        current = node.parent
        while current is not None and len(ancestors) < ANCESTORS_MAX:
            ancestor = self.nodes[current]
            # 未闭合/非法错配的开放栈只提供词法候选，不能承诺其父子关系。
            if ancestor.closure == "unknown":
                break
            ancestors.append(content.span(asset, ancestor.start, ancestor.opening_end))
            current = ancestor.parent
        attrs: list[OriginalAttribute] = []
        counts: dict[str, int] = {}
        for attr_index, attr in enumerate(node.attributes):
            if attr_index % SCAN_CHECK_INTERVAL == 0:
                check_original_cancel(token)
            counts[attr.name] = counts.get(attr.name, 0) + 1
        for attr in node.attributes[:ATTRIBUTE_PAGE_MAX]:
            attrs.append(
                {
                    "name": attr.name[:PREVIEW_CHARS],
                    "span": content.span(asset, attr.start, attr.end),
                    "value": (
                        content.preview(asset, attr.value_start, attr.value_end)
                        if attr.value_start is not None and attr.value_end is not None
                        else None
                    ),
                    "quote": attr.quote,
                    "duplicate": counts[attr.name] > 1,
                }
            )
        return {
            "kind": node.kind,
            "order": index,
            "qname": self.qname(node, node.name) if node.kind == "element" else None,
            "opening": content.span(asset, node.start, node.opening_end),
            "content": (
                content.span(asset, node.opening_end, node.content_end)
                if node.kind == "element" and node.content_end is not None
                else None
            ),
            "closing": (
                content.span(asset, node.closing_start, node.end)
                if node.closing_start is not None and node.end is not None
                else None
            ),
            "closure": node.closure,
            "parent": (
                content.span(asset, self.nodes[node.parent].start, self.nodes[node.parent].opening_end)
                if node.parent is not None and self.nodes[node.parent].closure != "unknown"
                else None
            ),
            "parent_status": (
                "root"
                if node.parent is None
                else "unknown" if self.nodes[node.parent].closure == "unknown" else "resolved"
            ),
            "ancestors": ancestors,
            "ancestors_complete": current is None,
            "attributes": attrs,
            "attributes_complete": len(node.attributes) <= ATTRIBUTE_PAGE_MAX
            and all(len(a.name) <= PREVIEW_CHARS for a in node.attributes),
            "preview": content.preview(asset, node.start, node.end if node.end is not None else node.opening_end),
            "continuation": self.reference(
                index, self.value(node, "continuedAt"), context=False, asset=asset, token=token
            ),
        }

    def diagnostics(self, asset: SourceAssetIdentity) -> list[OriginalDiagnostic]:
        """参数：身份。返回：有界固定原因及范围。异常：无。"""
        return [
            {"reason": reason, "span": self.content.span(asset, start, end)}
            for reason, start, end in self.reasons[:_DIAGNOSTICS_MAX]
        ]

    def read_structure(
        self, asset: SourceAssetIdentity, start: int, end: int, max_nodes: int, token: CancellationToken | None
    ) -> OriginalStructureResult:
        """参数：身份、已校验范围、页预算、token。返回：按起点分页的结构。异常：取消。"""
        check_original_cancel(token)
        first, stop = bisect_left(self.starts, start), bisect_left(self.starts, end)
        last = min(stop, first + max_nodes)
        nodes = [self.project_node(i, asset, token) for i in range(first, last)]
        result: OriginalStructureResult = {
            "asset": asset,
            "encoding": "utf-8",
            "bom_bytes": self.content.bom_bytes,
            "requested_range": self.content.span(asset, start, end),
            "total_chars": len(self.content.text),
            "nodes": nodes,
            "total_matches": stop - first,
            "truncated": last < stop,
            "next_start": self.starts[last] if last < stop else None,
            "parse_status": "partial" if self.reasons else "complete",
            "diagnostics": self.diagnostics(asset),
            "diagnostics_complete": len(self.reasons) <= _DIAGNOSTICS_MAX,
        }
        check_original_cancel(token)
        return result

    def project_fact(self, index: int, asset: SourceAssetIdentity, token: CancellationToken | None) -> OriginalFact:
        """参数：occurrence 索引、身份、token。返回：原生非数值证据，不做 transformation。异常：取消。"""
        node = self.nodes[index]
        evidence: list[OriginalPreview] = []
        hidden = False
        evidence_complete = True
        current: int | None = index
        while current is not None:
            check_original_cancel(token)
            ancestor = self.nodes[current]
            uri, local = self.expanded(ancestor, ancestor.name)
            ix_hidden = uri in INLINE_URIS and local == "hidden"
            attr_names = {attr.name.lower() for attr in ancestor.attributes}
            style = self.value(ancestor, "style") or ""
            hidden = (
                hidden
                or ix_hidden
                or "hidden" in attr_names
                or bool(
                    re.search(
                        r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\s*(?:!important\s*)?(?:;|$)",
                        style,
                        re.IGNORECASE,
                    )
                )
            )
            if ix_hidden or attr_names & {"hidden", "style", "class"}:
                if len(evidence) < ANCESTORS_MAX:
                    evidence.append(self.content.preview(asset, ancestor.start, ancestor.opening_end))
                else:
                    evidence_complete = False
            current = ancestor.parent
        name, fmt = self.value(node, "name"), self.value(node, "format")
        return {
            "node": self.project_node(index, asset, token),
            "name": self.qname(node, name) if name is not None else None,
            "format": self.qname(node, fmt) if fmt is not None else None,
            "raw_value": (
                self.content.preview(asset, node.opening_end, node.content_end)
                if node.content_end is not None
                else None
            ),
            "context_ref": self.attribute_preview(node, "contextRef", asset),
            "target_raw": self.attribute_preview(node, "target", asset),
            "target_origin": "explicit" if any(a.name == "target" for a in node.attributes) else "implicit_default",
            "xml_lang": self.expanded_attribute_preview(node, XML_URI, "lang", asset),
            "xsi_nil": self.expanded_attribute_preview(node, XSI_URI, "nil", asset),
            "escape": self.attribute_preview(node, "escape", asset),
            "continued_at": self.attribute_preview(node, "continuedAt", asset),
            "context": self.reference(index, self.value(node, "contextRef"), context=True, asset=asset, token=token),
            "visibility": {
                "visibility_status": "hidden_declaration" if hidden else "unknown",
                "css_evaluated": False,
                "evidence": evidence,
                "evidence_complete": evidence_complete,
            },
        }

    def query_facts(
        self,
        asset: SourceAssetIdentity,
        concepts: Sequence[ExpandedName],
        offset: int,
        limit: int,
        token: CancellationToken | None,
    ) -> OriginalFactsResult:
        """参数：身份、扩展名、分页、本次 token。返回：全部 occurrence 的一页及独立完整性。异常：取消。"""
        wanted = {(c["namespace_uri"], c["local_name"]) for c in concepts}
        matches: list[int] = []
        for ordinal, index in enumerate(self.fact_indices):
            if ordinal % SCAN_CHECK_INTERVAL == 0:
                check_original_cancel(token)
            node = self.nodes[index]
            name = self.value(node, "name")
            if name is not None and self.expanded(node, name) in wanted:
                matches.append(index)
        facts = [self.project_fact(i, asset, token) for i in matches[offset : offset + limit]]
        reference_partial = any(
            f["context"]["status"] != "resolved" or f["node"]["continuation"]["status"] in {"unresolved", "ambiguous"}
            for f in facts
        )
        check_original_cancel(token)
        return {
            "asset": asset,
            "facts": facts,
            "total_matches": len(matches),
            "truncated": offset + limit < len(matches),
            "next_offset": offset + limit if offset + limit < len(matches) else None,
            "parse_status": "partial" if self.reasons or reference_partial else "complete",
            "diagnostics": self.diagnostics(asset),
            "diagnostics_complete": len(self.reasons) <= _DIAGNOSTICS_MAX,
        }
