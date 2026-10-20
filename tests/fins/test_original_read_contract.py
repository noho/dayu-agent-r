"""原文位置、namespace、物理结构、非数值证据与分页 owner 测试。"""

from pathlib import Path

import pytest

from dayu.fins.domain.original_read_contract import SourceAssetIdentity, ExpandedName
from dayu.fins.processors.original_content import OriginalContent, OriginalStructure
from dayu.fins.storage.local_file_source import LocalFileSource
from dayu.fins.processors.sec_form_section_common import _trim_cover_page_content
from dayu.fins.cancellation import FinsReadCancelledError
from dayu.contracts.cancellation import CancellationToken

ASSET: SourceAssetIdentity = {
    "ticker": "TEST",
    "document_id": "doc",
    "source_kind": "filing",
    "filename": "test.html",
    "sha256": "a" * 64,
    "size_bytes": 0,
}
HTML = """<html xmlns:z="http://www.xbrl.org/2013/inlineXBRL" xmlns:c="urn:concept" xmlns:x="http://www.xbrl.org/2003/instance"><body>
<z:resources><x:context id="C"><x:period>原始期间</x:period></x:context></z:resources>
<table><tr><td rowspan="2">a<span></span>b<br>c<td colspan='3'><z:nonNumeric name="c:Flag" contextRef="C" format="c:fixed-true" target="" continuedAt="tail">☒ &amp; <z:exclude>忽略片段</z:exclude></z:nonNumeric></tr></table>
<z:continuation id="tail">后续</z:continuation><!--保留注释--><z:hidden><z:nonNumeric name="c:Symbol" contextRef="C">S</z:nonNumeric></z:hidden>
<div xmlns:c="urn:other"><z:nonNumeric name="c:Flag" contextRef="C">☐</z:nonNumeric></div></body></html>"""


def _parse(root: Path, text: str = HTML, *, xml: bool = False) -> tuple[OriginalContent, OriginalStructure]:
    """参数：隔离根、原文及 XML 模式。返回：实际文本和位置索引。异常：I/O 或解析失败。"""
    path = root / "original.html"
    path.write_bytes(b"\xef\xbb\xbf" + text.encode())
    content = OriginalContent(LocalFileSource(path, "test-source", "text/html"), token=None)
    return content, OriginalStructure(content, xml=xml, token=None)


def test_exact_windows_and_untrimmed_cover(tmp_path: Path) -> None:
    """参数：临时根。返回：无。异常：BOM/CRLF/实体/分页或封面静默删减时断言失败。"""
    text = "中\r\n&amp;" * 10_000
    content, _ = _parse(tmp_path, text)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        page = content.read_text(ASSET, start, len(text), 16384, None)
        chunks.append(page["text"])
        assert page["bom_bytes"] == 3
        assert page["returned_range"]["end"] == start + len(page["text"])
        start = page["next_start"] if page["next_start"] is not None else len(text)
    assert "".join(chunks) == text
    assert _trim_cover_page_content(text) == text
    assert _trim_cover_page_content("start Table of Contents tail") == "start Table of Contents"


def test_physical_nodes_namespace_and_occurrences(tmp_path: Path) -> None:
    """参数：隔离根。返回：无。异常：物理阻隔、namespace 或事实证据丢失时断言失败。"""
    content, structure = _parse(tmp_path)
    page = structure.read_structure(ASSET, 0, len(HTML), 1000, None)
    assert page["parse_status"] == "complete"
    nodes = page["nodes"]
    span_node = next(n for n in nodes if n["qname"] and n["qname"]["raw"] == "span")
    assert span_node["content"] is not None and span_node["content"]["start"] == span_node["content"]["end"]
    assert span_node["parent"] is not None
    assert any(n["qname"] and n["qname"]["raw"] == "br" and n["closure"] == "void" for n in nodes)
    assert any(n["kind"] == "comment" for n in nodes)
    facts = structure.query_facts(ASSET, [{"namespace_uri": "urn:concept", "local_name": "Flag"}], 0, 100, None)
    assert facts["total_matches"] == 1
    fact = facts["facts"][0]
    assert fact["raw_value"] and fact["raw_value"]["preview"].startswith("☒ &amp;")
    assert fact["target_raw"] and fact["target_raw"]["preview"] == ""
    assert fact["target_origin"] == "explicit"
    assert fact["format"] and fact["format"]["namespace_uri"] == "urn:concept"
    assert fact["context"]["status"] == "resolved"
    assert fact["context"].get("namespace_uri") == "http://www.xbrl.org/2003/instance"
    assert fact["context"].get("resource_target_origin") == "implicit_default"
    assert fact["context"].get("resource_span") is not None
    assert fact["node"]["continuation"]["status"] == "resolved"
    for node in nodes:
        preview = node["preview"]
        span = preview["span"]
        assert content.read_text(ASSET, span["start"], span["end"], len(HTML), None)["text"].startswith(
            preview["preview"]
        )
        assert preview["preview_complete"] == (span["end"] - span["start"] <= 512)
    symbol = structure.query_facts(ASSET, [{"namespace_uri": "urn:concept", "local_name": "Symbol"}], 0, 100, None)[
        "facts"
    ][0]
    assert symbol["visibility"]["visibility_status"] == "hidden_declaration"
    assert symbol["visibility"]["css_evaluated"] is False


@pytest.mark.parametrize(
    "fragment", ["<a><b></a>", '<x:f name="unbound:N">x</x:f>', '<a id="x" id="x">x</a>', "<!--unterminated", "<a"]
)
def test_partial_never_claims_complete_zero(tmp_path: Path, fragment: str) -> None:
    """参数：根和畸形输入。返回：无。异常：部分解析冒充完整零命中时断言失败。"""
    _, structure = _parse(tmp_path, fragment)
    concept: ExpandedName = {"namespace_uri": "urn:missing", "local_name": "Nothing"}
    result = structure.query_facts(ASSET, [concept], 0, 100, None)
    assert result["total_matches"] == 0
    assert result["parse_status"] == "partial"
    assert result["diagnostics"]


@pytest.mark.parametrize(
    "mode", ("cycle", "missing", "duplicate", "invalid", "context_duplicate", "context_missing")
)
def test_context_target_and_continuation_uncertainty(tmp_path: Path, mode: str) -> None:
    """参数：根及引用反例。返回：无。异常：循环/缺失或资产内 ID 歧义冒充完整。"""
    text = HTML
    if mode == "cycle":
        text = text.replace('id="tail"', 'id="tail" continuedAt="tail"')
    elif mode == "missing":
        text = text.replace('continuedAt="tail"', 'continuedAt="not-there"')
    elif mode == "duplicate":
        text += '<z:continuation xmlns:z="http://www.xbrl.org/2013/inlineXBRL" id="tail">two</z:continuation>'
    elif mode == "invalid":
        text = text.replace("z:continuation", "div")
    elif mode == "context_duplicate":
        text = text.replace("</z:resources>", '<x:context id="C">two</x:context></z:resources>')
    elif mode == "context_missing":
        text = text.replace('contextRef="C"', 'contextRef=""')
    _, structure = _parse(tmp_path, text)
    result = structure.query_facts(ASSET, [{"namespace_uri": "urn:concept", "local_name": "Flag"}], 0, 1, None)
    fact = result["facts"][0]
    assert result["parse_status"] == "partial"
    reference = fact["context"] if mode.startswith("context") else fact["node"]["continuation"]
    assert reference["status"] in {"ambiguous", "unresolved"}
    assert reference["reason"]


def test_large_attributes_ancestors_preview_and_structure_pages(tmp_path: Path) -> None:
    """参数：根。返回：无。异常：条目分页掩盖无界字符串或祖先伪造根节点。"""
    text = (
        "<html>"
        + "<div>" * 40
        + "<p "
        + " ".join(f'a{i}="' + "x" * 600 + '"' for i in range(40))
        + ">正文</p>"
        + "</div>" * 40
        + "</html>"
    )
    content, structure = _parse(tmp_path, text)
    start = 0
    projected: list[int] = []
    while True:
        page = structure.read_structure(ASSET, start, len(text), 7, None)
        projected.extend(n["opening"]["start"] for n in page["nodes"])
        if page["next_start"] is None:
            break
        start = page["next_start"]
    assert projected == structure.starts
    paragraph = next(
        n
        for n in structure.read_structure(ASSET, 0, len(text), 1000, None)["nodes"]
        if n["qname"] and n["qname"]["raw"] == "p"
    )
    assert paragraph["attributes_complete"] is False
    assert paragraph["ancestors_complete"] is False
    assert paragraph["parent"] is not None
    assert len(paragraph["attributes"]) == 32
    assert all(a["value"] and not a["value"]["preview_complete"] for a in paragraph["attributes"])
    opening = paragraph["opening"]
    assert content.read_text(ASSET, opening["start"], opening["end"], len(text), None)["text"].count('="') == 40


def test_xml_case_and_html_raw_text(tmp_path: Path) -> None:
    """参数：根。返回：无。异常：XML 大小写/默认 namespace 或 script 内伪标签改变结构。"""
    xml = '<?xml version="1.0"?><r xmlns="urn:root"><![CDATA[<raw>&original]]><Fact ID="A"/><fact ID="b"/></r>'
    _, structure = _parse(tmp_path, xml, xml=True)
    page = structure.read_structure(ASSET, 0, len(xml), 100, None)
    assert [n["qname"]["local_name"] for n in page["nodes"] if n["qname"]] == ["r", "Fact", "fact"]
    assert page["parse_status"] == "complete"
    assert [node["kind"] for node in page["nodes"] if node["qname"] is None] == ["processing_instruction", "cdata"]
    text = '<html><script>if (a < b) {"<p>"}</script><style>a>b{}</style><p>正文'
    _, structure = _parse(tmp_path, text)
    names = [n.name for n in structure.nodes if n.kind == "element"]
    assert names == ["html", "script", "style", "p"]
    assert not structure.reasons


def test_optional_table_group_boundaries_do_not_nest_new_rows_in_previous_cell(tmp_path: Path) -> None:
    """参数：隔离根。返回：无。异常：合法省略闭合把新行组错挂到前一单元格。"""
    text = "<table><thead><tr><th>头<tbody><tr><td>值<tfoot><tr><td>尾</table>"
    _, structure = _parse(tmp_path, text)
    page = structure.read_structure(ASSET, 0, len(text), 100, None)
    assert page["parse_status"] == "complete"
    table = page["nodes"][0]["opening"]
    groups = [n for n in page["nodes"] if n["qname"] and n["qname"]["raw"] in {"thead", "tbody", "tfoot"}]
    assert len(groups) == 3 and all(n["parent"] == table for n in groups)


def test_unclosed_envelope_does_not_claim_known_complete_parent_chain(tmp_path: Path) -> None:
    """参数：隔离根。返回：无。异常：SEC 原始外层的开放栈被伪装成确定父链或根节点。"""
    text = (
        '<DOCUMENT><TYPE>6-K<TEXT><html><body><p><a href="attachment.htm">原文</a></p></body></html></TEXT></DOCUMENT>'
    )
    _, structure = _parse(tmp_path, text)
    page = structure.read_structure(ASSET, 0, len(text), 100, None)
    assert page["parse_status"] == "partial"
    text_node = next(n for n in page["nodes"] if n["qname"] and n["qname"]["raw"] == "TEXT")
    assert text_node["parent"] is None and text_node["parent_status"] == "unknown"
    assert not text_node["ancestors_complete"]
    link = next(n for n in page["nodes"] if n["qname"] and n["qname"]["raw"] == "a")
    assert link["parent_status"] == "resolved" and link["parent"] is not None
    assert link["closure"] == "explicit" and not link["ancestors_complete"]


def test_namespaced_fact_attributes_use_binding_and_keep_raw_values(tmp_path: Path) -> None:
    """参数：根。返回：无。异常：nil 固定前缀、语言原值被转换或扩展属性歧义冒充缺失。"""
    text = HTML.replace(
        'xmlns:c="urn:concept"', 'xmlns:c="urn:concept" xmlns:n="http://www.w3.org/2001/XMLSchema-instance"'
    )
    text = text.replace('name="c:Flag"', 'name="c:Flag" n:nil="false" xml:lang="en-US"')
    _, structure = _parse(tmp_path, text)
    fact = structure.query_facts(ASSET, [{"namespace_uri": "urn:concept", "local_name": "Flag"}], 0, 10, None)["facts"][
        0
    ]
    assert fact["xsi_nil"] is not None and fact["xsi_nil"]["preview"] == "false"
    assert fact["xml_lang"] is not None and fact["xml_lang"]["preview"] == "en-US"
    duplicate = text.replace(
        'n:nil="false"', 'xmlns:m="http://www.w3.org/2001/XMLSchema-instance" n:nil="false" m:nil="true"'
    )
    _, structure = _parse(tmp_path, duplicate)
    result = structure.query_facts(ASSET, [{"namespace_uri": "urn:concept", "local_name": "Flag"}], 0, 10, None)
    assert result["parse_status"] == "partial"
    assert any(d["reason"] == "duplicate_expanded_attribute" for d in result["diagnostics"])


def test_long_attribute_name_is_bounded_and_explicitly_incomplete(tmp_path: Path) -> None:
    """参数：隔离根。返回：无。异常：极长属性名被静默裁短或无界返回。"""
    text = "<p " + "a" * 1000 + '="v">原文</p>'
    content, structure = _parse(tmp_path, text)
    node = structure.read_structure(ASSET, 0, len(text), 100, None)["nodes"][0]
    assert len(node["attributes"][0]["name"]) == 512
    assert node["attributes_complete"] is False
    span = node["opening"]
    assert content.read_text(ASSET, span["start"], span["end"], len(text), None)["text"] == text[: text.index(">") + 1]
