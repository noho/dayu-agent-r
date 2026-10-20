"""原文审核反例：真实仓储到公开 runtime 的格式、引用、资源及借用契约。"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier, Event, Lock
from typing import Literal, TypedDict

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.documents.processors.base import DocumentProcessor
from dayu.documents.processors.processor_registry import ProcessorRegistry
from dayu.documents.processors.source import Source
from dayu.fins.domain.enums import SourceKind
from dayu.fins.processors.original_content import OriginalContent, OriginalStructure
from dayu.fins.processors.original_content import _ReferenceTarget
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.storage import FsSourceDocumentRepository
from dayu.fins.storage.repository_protocols import SourceSnapshotProtocol
from dayu.fins.tools.read_runtime_helpers import FinsReadArgumentError, FinsReadBusinessError
from tests.fins.test_original_read_contract import HTML
from tests.fins.test_original_read_runtime import publish_original


class _Selection(TypedDict):
    """真实公开 API 的五个显式选件参数。"""

    ticker: str
    document_id: str
    source_kind: SourceKind
    filename: str
    expected_sha256: str


_TARGET_DOCUMENT = """<html xmlns="http://www.w3.org/1999/xhtml" xmlns:z="http://www.xbrl.org/2013/inlineXBRL" xmlns:c="urn:concept" xmlns:x="http://www.xbrl.org/2003/instance"><head><title>引用原文</title></head><body>
<div style="display:none"><z:header><z:resources><x:context id="C"><x:entity><x:identifier scheme="urn:test">TEST</x:identifier></x:entity><x:period><x:instant>2025-12-31</x:instant></x:period></x:context></z:resources></z:header></div>
<z:nonNumeric name="c:Flag" contextRef="C" target="" continuedAt="tail">原值</z:nonNumeric>
<z:nonNumeric name="c:Symbol" contextRef="C">S</z:nonNumeric>
<z:continuation id="tail">续文</z:continuation></body></html>"""


@pytest.mark.parametrize(
    "filename,media",
    [
        ("sample.xhtml", "application/xhtml+xml"),
        ("sample.xhtml", None),
        ("sample.data", "application/xml"),
        ("sample.html", "text/xml; charset=utf-8"),
        ("sample.xml", "application/xml"),
    ],
)
def test_xml_format_and_capabilities_share_owner(tmp_path: Path, filename: str, media: str | None) -> None:
    """参数：隔离根、资产名/媒体。返回：无。异常：XML 大小写错配被 HTML 规则冒充完整时断言失败。"""
    # 无媒体声明用 application/octet-stream，以验证未知媒体回到后缀的同一格式判定。
    text = '<html xmlns="http://www.w3.org/1999/xhtml"><body><P>A</p></body></html>'
    publish_original(tmp_path, text, filename=filename, content_type=media or "application/octet-stream")
    with closing(DefaultFinsRuntime.create(workspace_root=tmp_path)) as runtime:
        reader = runtime.get_read_runtime()
        listing = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)
        selected = next(a for a in listing["assets"] if a["asset"]["filename"] == filename)
        assert selected["text_supported"] and selected["structure_supported"]
        result = reader.read_original_structure(
            ticker="TEST",
            document_id="original-doc",
            source_kind=SourceKind.FILING,
            filename=filename,
            expected_sha256=selected["asset"]["sha256"],
        )
        assert result["parse_status"] == "partial"
        node = next(n for n in result["nodes"] if n["qname"] and n["qname"]["raw"] == "P")
        assert node["closure"] == "unknown" and node["closing"] is None


@pytest.mark.parametrize(
    "text,child,parent",
    [
        ("<html><head><title>T</title><body><p>A</p></body></html>", "body", "html"),
        ("<html><head><meta charset='utf-8'><div>A</div></html>", "div", "html"),
        ("<table><colgroup><col><tbody><tr><td>A<tbody><tr><td>B</table>", "tbody", "table"),
        ("<select><optgroup><option>A<optgroup><option>B</select>", "optgroup", "select"),
        ("<ruby><rt>A<rp>B</ruby>", "rp", "ruby"),
    ],
)
def test_html_optional_boundaries_are_real_siblings(tmp_path: Path, text: str, child: str, parent: str) -> None:
    """参数：真实 HTML 和预期直接父子。返回：无。异常：合法省略闭合被错误嵌套或误标 partial。"""
    publish_original(tmp_path, text)
    with closing(DefaultFinsRuntime.create(workspace_root=tmp_path)) as runtime:
        reader = runtime.get_read_runtime()
        asset = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)[
            "assets"
        ][0]["asset"]
        result = reader.read_original_structure(
            ticker="TEST",
            document_id="original-doc",
            source_kind=SourceKind.FILING,
            filename=asset["filename"],
            expected_sha256=asset["sha256"],
        )
        assert result["parse_status"] == "complete"
        owner = next(n["opening"] for n in result["nodes"] if n["qname"] and n["qname"]["raw"] == parent)
        children = [n for n in result["nodes"] if n["qname"] and n["qname"]["raw"] == child]
        assert children and all(n["parent"] == owner for n in children)


@pytest.mark.parametrize(
    "mode",
    [
        "valid",
        "resource_declaration",
        "duplicate_context",
        "duplicate_tail",
        "missing",
        "cycle",
        "unknown_boundary",
        "invalid",
    ],
)
@pytest.mark.parametrize("content_type", ["text/html", "application/xhtml+xml"])
def test_target_is_raw_declaration_and_asset_ids_are_unique(tmp_path: Path, mode: str, content_type: str) -> None:
    """参数：隔离根、引用反例、HTML/XHTML 媒体。返回：无。异常：target 分组、后页坏引用或重复 ID 被完整旗标掩盖。"""
    text = _TARGET_DOCUMENT.replace('target=""', 'target="other"')
    if mode == "resource_declaration":
        text = text.replace("<z:resources>", '<z:resources target="declared-only">')
    elif mode == "duplicate_context":
        text = text.replace(
            "</z:resources>", '<x:context id="C" target="elsewhere">duplicate</x:context></z:resources>'
        )
    # 第一条 occurrence 正常；坏引用仅放在后一 occurrence，必须影响首个 facts 页及首个结构页。
    if mode in {"duplicate_tail", "missing", "cycle", "unknown_boundary", "invalid"}:
        text = text.replace('name="c:Symbol" contextRef="C"', 'name="c:Flag" contextRef="C" continuedAt="bad-tail"')
        tail = '<z:continuation id="bad-tail">tail</z:continuation>'
        if mode == "duplicate_tail":
            tail *= 2
        elif mode == "missing":
            tail = ""
        elif mode == "cycle":
            tail = tail.replace('id="bad-tail"', 'id="bad-tail" continuedAt="bad-tail"')
        elif mode == "unknown_boundary":
            tail = '<z:continuation id="bad-tail">tail'
        elif mode == "invalid":
            tail = '<div id="bad-tail">tail</div>'
        text = text.replace("</body>", tail + "</body>")
    publish_original(tmp_path, text, content_type=content_type)
    with closing(DefaultFinsRuntime.create(workspace_root=tmp_path)) as runtime:
        reader = runtime.get_read_runtime()
        asset = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)[
            "assets"
        ][0]["asset"]
        args: _Selection = {
            "ticker": "TEST",
            "document_id": "original-doc",
            "source_kind": SourceKind.FILING,
            "filename": "main.html",
            "expected_sha256": asset["sha256"],
        }
        first = reader.query_original_facts(
            **args, concepts=[{"namespace_uri": "urn:concept", "local_name": "Flag"}], limit=1
        )
        valid = mode in {"valid", "resource_declaration"}
        assert first["parse_status"] == ("complete" if valid else "partial")
        structure = reader.read_original_structure(**args, max_nodes=1)
        assert structure["parse_status"] == first["parse_status"]
        fact = first["facts"][0]
        assert fact["target_raw"] and fact["target_raw"]["preview"] == "other"
        assert fact["target_origin"] == "explicit"
        if mode == "duplicate_context":
            assert fact["context"]["status"] == "ambiguous"
        else:
            assert fact["context"]["status"] == "resolved"
            assert fact["node"]["continuation"]["status"] == "resolved"
        if valid:
            context = fact["context"]
            assert "resource_target_origin" in context and "resource_target_raw" in context
            assert context["resource_target_origin"] == (
                "explicit" if mode == "resource_declaration" else "implicit_default"
            )
            declared = context["resource_target_raw"]
            assert (declared["preview"] if declared else None) == (
                "declared-only" if mode == "resource_declaration" else None
            )
            for ref in (context, fact["node"]["continuation"]):
                target = ref["target"]
                assert target is not None
                span = target["span"]
                back = reader.read_original_text(**args, start=span["start"], end=span["end"])
                assert back["text"] == target["preview"]
        else:
            second = reader.query_original_facts(
                **args, concepts=[{"namespace_uri": "urn:concept", "local_name": "Flag"}], offset=1, limit=1
            )
            assert second["parse_status"] == "partial" and second["diagnostics"] == first["diagnostics"]


@pytest.mark.parametrize("filename", ["report[1].html", "report*.html", "report?.html"])
def test_enumerated_literal_asset_name_round_trips(tmp_path: Path, filename: str) -> None:
    """参数：隔离根和合法单组件名。返回：无。异常：把字面量文件名误当 glob 或路径时断言失败。"""
    publish_original(tmp_path, filename=filename)
    with closing(DefaultFinsRuntime.create(workspace_root=tmp_path)) as runtime:
        reader = runtime.get_read_runtime()
        listing = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)
        asset = next(a["asset"] for a in listing["assets"] if a["asset"]["filename"] == filename)
        result = reader.read_original_text(
            ticker="TEST",
            document_id="original-doc",
            source_kind=SourceKind.FILING,
            filename=filename,
            expected_sha256=asset["sha256"],
        )
        assert result["text"] == HTML and result["asset"] == asset


@pytest.mark.parametrize(
    "operation,missing",
    [
        ("list", "document"),
        ("text", "document"),
        ("structure", "document"),
        ("facts", "document"),
        ("text", "asset"),
        ("structure", "asset"),
        ("facts", "asset"),
    ],
)
def test_missing_original_resource_is_typed_not_found(tmp_path: Path, operation: str, missing: str) -> None:
    """参数：隔离根、公开方法、缺失维度。返回：无。异常：缺失被映射到旧 ref 提示或其它类别时断言失败。"""
    publish_original(tmp_path)
    with closing(DefaultFinsRuntime.create(workspace_root=tmp_path)) as runtime:
        reader = runtime.get_read_runtime()
        document = "absent-doc" if missing == "document" else "original-doc"
        filename = "absent.html" if missing == "asset" else "main.html"
        with pytest.raises(FinsReadBusinessError) as failure:
            if operation == "list":
                reader.list_document_assets(ticker="TEST", document_id=document, source_kind=SourceKind.FILING)
            elif operation == "text":
                reader.read_original_text(
                    ticker="TEST",
                    document_id=document,
                    source_kind=SourceKind.FILING,
                    filename=filename,
                    expected_sha256="a" * 64,
                )
            elif operation == "structure":
                reader.read_original_structure(
                    ticker="TEST",
                    document_id=document,
                    source_kind=SourceKind.FILING,
                    filename=filename,
                    expected_sha256="a" * 64,
                )
            else:
                reader.query_original_facts(
                    ticker="TEST",
                    document_id=document,
                    source_kind=SourceKind.FILING,
                    filename=filename,
                    expected_sha256="a" * 64,
                    concepts=[{"namespace_uri": "urn:c", "local_name": "Flag"}],
                )
        assert failure.value.code.value == "not_found"
        assert (
            failure.value.hint and "list_document_assets" in failure.value.hint and "source_kind" in failure.value.hint
        )
        assert "table_ref" not in failure.value.hint


@pytest.mark.parametrize("capability", ["text", "structure", "processor"])
def test_active_borrow_finishes_lazy_build_after_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capability: str
) -> None:
    """参数：隔离根、同步探针和懒能力。返回：无。异常：关闭破坏已取得借用或最终资源未释放时断言失败。"""
    publish_original(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path)
    reader = runtime.get_read_runtime()
    asset = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)[
        "assets"
    ][0]["asset"]
    entries = [reader._processor_cache.peek(key) for key in reader._processor_cache.keys_snapshot()]
    entry = entries[0]
    assert entry is not None and entry.processor is None
    root = entry.snapshot.get_primary_source().materialize().parent
    entered, release = Event(), Event()
    real_text, real_scan, real_create = (
        OriginalContent.__init__,
        OriginalStructure._scan,
        ProcessorRegistry.create_with_fallback,
    )

    def block() -> None:
        """参数：无。返回：无。异常：主线程未释放构建时断言失败。"""
        entered.set()
        assert release.wait(10)

    def text_build(self: OriginalContent, source: Source, *, token: CancellationToken | None) -> None:
        """参数：真实内容构建输入。返回：无。异常：同步/真实构建失败。"""
        block()
        real_text(self, source, token=token)

    def scan_build(self: OriginalStructure, token: CancellationToken | None) -> None:
        """参数：真实索引与 token。返回：无。异常：同步/真实扫描失败。"""
        block()
        real_scan(self, token)

    def processor_build(
        self: ProcessorRegistry, source: Source, *, form_type: str | None = None, media_type: str | None = None
    ) -> DocumentProcessor:
        """参数：真实 registry 创建输入。返回：真实便利 processor。异常：同步/构建失败。"""
        block()
        return real_create(self, source=source, form_type=form_type, media_type=media_type)

    def read() -> None:
        """参数：无。返回：无。异常：公开读取失败或内容错误。"""
        if capability == "processor":
            assert (
                reader.get_document_sections(ticker="TEST", document_id="original-doc")["source_asset"]["filename"]
                == "attachment.html"
            )
        elif capability == "text":
            assert (
                reader.read_original_text(
                    ticker="TEST",
                    document_id="original-doc",
                    source_kind=SourceKind.FILING,
                    filename="main.html",
                    expected_sha256=asset["sha256"],
                )["text"]
                == HTML
            )
        else:
            assert (
                reader.read_original_structure(
                    ticker="TEST",
                    document_id="original-doc",
                    source_kind=SourceKind.FILING,
                    filename="main.html",
                    expected_sha256=asset["sha256"],
                )["parse_status"]
                == "complete"
            )

    if capability == "text":
        monkeypatch.setattr(OriginalContent, "__init__", text_build)
    elif capability == "structure":
        monkeypatch.setattr(OriginalStructure, "_scan", scan_build)
    else:
        monkeypatch.setattr(ProcessorRegistry, "create_with_fallback", processor_build)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(read)
            try:
                assert entered.wait(10)
                runtime.close()
                assert root.exists() and reader._processor_cache.size() == 0
                with pytest.raises(RuntimeError):
                    reader.list_document_assets(
                        ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING
                    )
            finally:
                release.set()
            future.result(10)
        assert not root.exists() and not reader._retired_entries and not reader._pending_snapshots
    finally:
        release.set()
        runtime.close()


@pytest.mark.parametrize("kind", ["ref", "table_ref"])
def test_diagnosis_never_builds_enumerated_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: Literal["ref", "table_ref"]
) -> None:
    """参数：隔离根、实际 registry 计数探针、定位类别。返回：无。异常：坏定位诊断触发未读 B 的构建。"""
    publish_original(tmp_path, document_id="document-B")
    publish_original(tmp_path, document_id="document-A")
    real = ProcessorRegistry.create_with_fallback
    calls: list[str] = []

    def counted(
        self: ProcessorRegistry, source: Source, *, form_type: str | None = None, media_type: str | None = None
    ) -> DocumentProcessor:
        """参数：实际 registry 输入。返回：真实 processor。异常：真实构建失败。"""
        calls.append(source.uri)
        return real(self, source=source, form_type=form_type, media_type=media_type)

    monkeypatch.setattr(ProcessorRegistry, "create_with_fallback", counted)
    with closing(DefaultFinsRuntime.create(workspace_root=tmp_path)) as runtime:
        reader = runtime.get_read_runtime()
        reader.list_document_assets(ticker="TEST", document_id="document-B", source_kind=SourceKind.FILING)
        assert calls == []
        with pytest.raises(FinsReadArgumentError):
            if kind == "ref":
                reader.read_section(ticker="TEST", document_id="document-A", ref="s_bad")
            else:
                reader.get_table(ticker="TEST", document_id="document-A", table_ref="t_bad")
        assert len(calls) == 1
        key = next(k for k in reader._processor_cache.keys_snapshot() if k.document_id == "document-B")
        entry = reader._processor_cache.peek(key)
        assert entry is not None and entry.processor is None


def test_two_full_snapshots_compete_and_loser_is_cleaned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """参数：隔离 Fs 根、仓储同步探针。返回：无。异常：败方 snapshot 未立即关闭或胜方提前关闭。"""
    publish_original(tmp_path)
    real = FsSourceDocumentRepository.read_source_snapshot
    barrier, guard = Barrier(2), Lock()
    full: list[SourceSnapshotProtocol] = []
    roots: list[Path] = []

    def acquired(
        self: FsSourceDocumentRepository,
        ticker: str,
        document_id: str,
        source_kind: SourceKind | None = None,
        *,
        materialize_files: bool = True,
    ) -> SourceSnapshotProtocol:
        """参数：实际仓储 snapshot 请求。返回：真实 snapshot，full 在 cache publication 前同步。异常：仓储/同步失败。"""
        snapshot = real(self, ticker, document_id, source_kind, materialize_files=materialize_files)
        if materialize_files:
            with guard:
                full.append(snapshot)
                roots.append(snapshot.get_primary_source().materialize().parent)
            barrier.wait(10)
        return snapshot

    monkeypatch.setattr(FsSourceDocumentRepository, "read_source_snapshot", acquired)
    with closing(DefaultFinsRuntime.create(workspace_root=tmp_path)) as runtime:
        reader = runtime.get_read_runtime()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    reader.list_document_assets,
                    ticker="TEST",
                    document_id="original-doc",
                    source_kind=SourceKind.FILING,
                )
                for _ in range(2)
            ]
            results = [future.result(15) for future in futures]
        assert results[0] == results[1] and len(full) == 2 and roots[0] != roots[1]
        assert sum(root.exists() for root in roots) == 1 and reader._processor_cache.size() == 1
        entry = reader._processor_cache.peek(reader._processor_cache.keys_snapshot()[0])
        assert entry is not None and entry.snapshot in full
        assert entry.snapshot.get_primary_source().materialize().parent.exists()
    assert all(not root.exists() for root in roots)


def test_shared_long_continuation_chain_is_indexed_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """参数：真实 Fs 根与 owner 计数探针。返回：无。异常：分页重新解析引用或共享长链不完整时断言失败。"""
    count = 1000
    chain = "".join(
        f'<z:continuation id="tail{i}" continuedAt="tail{i + 1}">原文</z:continuation>' for i in range(count)
    )
    chain += f'<z:continuation id="tail{count}">末尾</z:continuation>'
    fact = '<z:nonNumeric name="c:Flag" contextRef="C" continuedAt="tail0">相同值</z:nonNumeric>'
    text = HTML.replace("</body>", fact * 5 + chain + "</body>")
    publish_original(tmp_path, text)
    calls: list[str | None] = []
    real = OriginalStructure._resolve_reference

    def counted(self: OriginalStructure, identifier: str | None, *, context: bool) -> _ReferenceTarget:
        """参数：owner 引用输入。返回：实际引用结果。异常：实际解析失败。"""
        calls.append(identifier)
        return real(self, identifier, context=context)

    monkeypatch.setattr(OriginalStructure, "_resolve_reference", counted)
    with closing(DefaultFinsRuntime.create(workspace_root=tmp_path)) as runtime:
        reader = runtime.get_read_runtime()
        asset = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)[
            "assets"
        ][0]["asset"]
        initial_count = 0
        for offset in range(6):
            page = reader.query_original_facts(
                ticker="TEST",
                document_id="original-doc",
                source_kind=SourceKind.FILING,
                filename="main.html",
                expected_sha256=asset["sha256"],
                concepts=[{"namespace_uri": "urn:concept", "local_name": "Flag"}],
                offset=offset,
                limit=1,
            )
            assert page["parse_status"] == "complete" and page["total_matches"] == 6
            if offset == 0:
                initial_count = len(calls)
                assert count <= initial_count < count + 20
            assert len(calls) == initial_count


@pytest.mark.parametrize(
    "text", ["<dl><dt>A</dl>", "<table><thead><tr><th>A</table>", "<html><head><title>A<body>B</body></html>"]
)
def test_unsupported_omission_is_partial_instead_of_fabricated_complete(tmp_path: Path, text: str) -> None:
    """参数：隔离根和无法按规则闭合的原文。返回：无。异常：未知闭合被声称规则完整时断言失败。"""
    publish_original(tmp_path, text)
    with closing(DefaultFinsRuntime.create(workspace_root=tmp_path)) as runtime:
        reader = runtime.get_read_runtime()
        asset = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)[
            "assets"
        ][0]["asset"]
        result = reader.read_original_structure(
            ticker="TEST",
            document_id="original-doc",
            source_kind=SourceKind.FILING,
            filename="main.html",
            expected_sha256=asset["sha256"],
        )
        assert result["parse_status"] == "partial" and result["diagnostics"]
        assert any(node["closure"] == "unknown" for node in result["nodes"])


def test_decode_and_storage_damage_are_not_missing_resources(tmp_path: Path) -> None:
    """参数：隔离真实 Fs 根。返回：无。异常：原文解码失败或物理损坏被 missing 映射吞掉。"""
    publish_original(tmp_path, b"\xff")
    with closing(DefaultFinsRuntime.create(workspace_root=tmp_path)) as runtime:
        reader = runtime.get_read_runtime()
        asset = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)[
            "assets"
        ][0]["asset"]
        with pytest.raises(FinsReadBusinessError) as error:
            reader.read_original_text(
                ticker="TEST",
                document_id="original-doc",
                source_kind=SourceKind.FILING,
                filename="main.html",
                expected_sha256=asset["sha256"],
            )
        assert error.value.code.value == "source_decode_failed"
    # 只破坏隔离测试仓储的实际文件，不改 meta/manifest/revision；完整性拒绝仍由 storage 产生。
    asset_path = next((tmp_path / "portfolio" / "TEST" / "filings").glob("*/main.html"))
    asset_path.unlink()
    with closing(DefaultFinsRuntime.create(workspace_root=tmp_path)) as runtime:
        with pytest.raises(ValueError):
            runtime.get_read_runtime().list_document_assets(
                ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING
            )
