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
    "address article aside blockquote details dialog div dl fieldset figcaption figure footer form h1 h2 h3 h4 h5 h6 header hgroup hr main menu nav ol p pre search section table ul".split()
)
# noscript 可承载 head 内的 link/style/meta；其起点不能触发 head 的省略闭合。
_HEAD_CONTENT = frozenset("base basefont bgsound link meta noframes noscript script style template title".split())
_OPTIONAL_PARENT_END = {
    "html": frozenset({""}),
    "head": frozenset({"html"}),
    "body": frozenset({"html", ""}),
    "li": frozenset({"ul", "ol", "menu"}),
    "dd": frozenset({"dl"}),
    "tr": frozenset({"table", "thead", "tbody", "tfoot"}),
    "td": frozenset({"tr"}),
    "th": frozenset({"tr"}),
    "tbody": frozenset({"table"}),
    "tfoot": frozenset({"table"}),
    "colgroup": frozenset({"table"}),
    "option": frozenset({"select", "datalist", "optgroup"}),
    "optgroup": frozenset({"select"}),
    "rt": frozenset({"ruby"}),
    "rp": frozenset({"ruby"}),
}
_P_END_FORBIDDEN = frozenset({"a", "audio", "del", "ins", "map", "noscript", "video"})
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


@dataclass(frozen=True, slots=True)
class OriginalFormat:
    """原文格式能力与索引语法的同一判定结果。"""

    text: bool
    syntax: Literal["html", "xml"] | None
    inline_facts: bool


def original_format(filename: str, content_type: str | None) -> OriginalFormat:
    """参数：仓储资产名和媒体声明。返回：统一格式能力及语法，明确媒体优先于后缀。异常：无。"""
    suffix = filename.rsplit(".", 1)[-1].lower()
    media = (content_type or "").lower().split(";", 1)[0].strip()
    syntax: Literal["html", "xml"] | None
    if media in {"application/xhtml+xml", "application/xml", "text/xml"}:
        syntax = "xml"
    elif media == "text/html":
        syntax = "html"
    else:
        syntax = "xml" if suffix in {"xml", "xhtml"} else "html" if suffix in {"htm", "html"} else None
    inline = media == "application/xhtml+xml" or suffix == "xhtml" or syntax == "html"
    text = (
        syntax is not None
        or suffix in {"txt", "md", "markdown", "json"}
        or media.startswith("text/")
        or media == "application/json"
    )
    return OriginalFormat(text, syntax, inline)


def _omittable_at_parent_end(name: str, parent: str) -> bool:
    """参数：HTML 元素名和直接父名（空为片段根）。返回：能否在父级结束时省略闭合。异常：无。"""
    return parent not in _P_END_FORBIDDEN if name == "p" else parent in _OPTIONAL_PARENT_END.get(name, ())


@dataclass(frozen=True, slots=True)
class _ReferenceTarget:
    """与投影身份无关的资产内引用校验结果；index 保留首跳位置。"""

    status: Literal["resolved", "unresolved", "ambiguous", "absent"]
    reason: str | None
    index: int | None


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
        self.ids: dict[str, list[int]] = {}
        self.fact_indices: list[int] = []
        self.contexts: dict[int, _ReferenceTarget] = {}
        self.continuations: dict[int, _ReferenceTarget] = {}
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
                self.ids.setdefault(identifier, []).append(index)
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
            reference = self._resolve_reference(self.value(node, "contextRef"), context=True)
            self.contexts[index] = reference
            if reference.status != "resolved":
                self.reasons.append(("unresolved_or_ambiguous_context", node.start, node.opening_end))
        self._index_continuations(token)
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

    def _resolve_reference(self, identifier: str | None, *, context: bool) -> _ReferenceTarget:
        """参数：原文 ID、context/continuation 模式。返回：资产内 exact ID 与元素类型校验。异常：无。"""
        if identifier is None:
            return (
                _ReferenceTarget("unresolved", "missing_context_ref", None)
                if context
                else _ReferenceTarget("absent", None, None)
            )
        matches = self.ids.get(identifier, [])
        if len(matches) != 1:
            return _ReferenceTarget(
                "ambiguous" if matches else "unresolved", "duplicate_id" if matches else "target_not_found", None
            )
        index = matches[0]
        node = self.nodes[index]
        uri, local = self.expanded(node, node.name)
        valid = (
            (uri == XBRLI_URI and local == "context") if context else (uri in INLINE_URIS and local == "continuation")
        )
        if not valid:
            return _ReferenceTarget("unresolved", "invalid_reference_target", None)
        return (
            _ReferenceTarget("unresolved", "unknown_target_boundary", index)
            if node.end is None
            else _ReferenceTarget("resolved", None, index)
        )

    def _index_continuations(self, token: CancellationToken | None) -> None:
        """参数：本次 token。返回：无；一次构建全资产引用图并缓存链状态。异常：取消。"""
        edges: dict[int, _ReferenceTarget] = {}
        for index, node in enumerate(self.nodes):
            if index % SCAN_CHECK_INTERVAL == 0:
                check_original_cancel(token)
            identifier = self.value(node, "continuedAt")
            if identifier is not None:
                edges[index] = self._resolve_reference(identifier, context=False)
        # 每个节点至多进入一条尚未求值的路径；共享长尾和循环均只校验一次。
        outcomes: dict[int, tuple[Literal["resolved", "unresolved", "ambiguous", "absent"], str | None]] = {}
        for index in edges:
            path: set[int] = set()
            cursor = index
            outcome: tuple[Literal["resolved", "unresolved", "ambiguous", "absent"], str | None] = ("resolved", None)
            while cursor in edges:
                check_original_cancel(token)
                if cursor in outcomes:
                    outcome = outcomes[cursor]
                    break
                if cursor in path:
                    outcome = ("unresolved", "continuation_cycle")
                    break
                path.add(cursor)
                edge = edges[cursor]
                if edge.status != "resolved" or edge.index is None:
                    outcome = (edge.status, edge.reason)
                    break
                cursor = edge.index
            for member in path:
                outcomes[member] = outcome
        for index, edge in edges.items():
            check_original_cancel(token)
            status, reason = outcomes[index]
            self.continuations[index] = _ReferenceTarget(status, reason, edge.index)
            if status != "resolved":
                node = self.nodes[index]
                self.reasons.append((reason or "unresolved_continuation", node.start, node.opening_end))

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
                        else "processing_instruction"
                        if raw.startswith("<?")
                        else "doctype"
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
                    parent_name = self.nodes[stack[-1]].name.lower() if stack else ""
                    if not self.xml and _omittable_at_parent_end(unfinished.name.lower(), parent_name):
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
            parent_name = self.nodes[node.parent].name.lower() if node.parent is not None else ""
            if not self.xml and _omittable_at_parent_end(node.name.lower(), parent_name):
                node.content_end, node.end, node.closure = len(text), len(text), "rule"
            else:
                self.reasons.append(("unclosed_element", node.start, node.opening_end))

    def _close_optional(self, stack: list[int], incoming: str, position: int) -> None:
        """参数：开放父链、新元素、起点。返回：无。异常：无。按 HTML 可省略结束规则闭合。"""
        while stack:
            node = self.nodes[stack[-1]]
            current = node.name.lower()
            closes = (
                current == "head"
                and incoming not in _HEAD_CONTENT
                or current == "colgroup"
                and incoming not in {"col", "template"}
                or current == "optgroup"
                and incoming == "optgroup"
                or current in {"rt", "rp"}
                and incoming in {"rt", "rp"}
                or current == "p"
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
        *,
        context: bool,
        asset: SourceAssetIdentity,
        token: CancellationToken | None,
    ) -> OriginalReference:
        """参数：节点、context 模式、身份/token。返回：已校验的资产内引用及原文投影。异常：取消。"""
        check_original_cancel(token)
        reference = (
            self.contexts[index] if context else self.continuations.get(index, _ReferenceTarget("absent", None, None))
        )
        target = self.nodes[reference.index] if reference.index is not None else None
        result: OriginalReference = {
            "status": reference.status,
            "reason": reference.reason,
            "target": self.content.preview(
                asset, target.start, target.end if target.end is not None else target.opening_end
            )
            if target is not None
            else None,
        }
        if context and target is not None and reference.status == "resolved":
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
                else "unknown"
                if self.nodes[node.parent].closure == "unknown"
                else "resolved"
            ),
            "ancestors": ancestors,
            "ancestors_complete": current is None,
            "attributes": attrs,
            "attributes_complete": len(node.attributes) <= ATTRIBUTE_PAGE_MAX
            and all(len(a.name) <= PREVIEW_CHARS for a in node.attributes),
            "preview": content.preview(asset, node.start, node.end if node.end is not None else node.opening_end),
            "continuation": self.reference(index, context=False, asset=asset, token=token),
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
            "context": self.reference(index, context=True, asset=asset, token=token),
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
        check_original_cancel(token)
        return {
            "asset": asset,
            "facts": facts,
            "total_matches": len(matches),
            "truncated": offset + limit < len(matches),
            "next_offset": offset + limit if offset + limit < len(matches) else None,
            "parse_status": "partial" if self.reasons else "complete",
            "diagnostics": self.diagnostics(asset),
            "diagnostics_complete": len(self.reasons) <= _DIAGNOSTICS_MAX,
        }
