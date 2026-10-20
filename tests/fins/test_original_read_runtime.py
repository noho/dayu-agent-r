"""原文公开读取与 storage 实际身份的 owner 契约测试。"""

from pathlib import Path
import hashlib
import json
from io import BytesIO
from datetime import datetime
from typing import cast
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from dayu.fins.processors.original_content import OriginalContent, OriginalStructure
from dayu.fins.domain.original_read_contract import OriginalTextResult, SourceAssetIdentity
from dayu.fins.domain.original_read_contract import ExpandedName
from dayu.contracts.cancellation import CancellationToken

import pytest

from dayu.fins.domain.enums import SourceKind
from dayu.fins.storage import FsSourceDocumentRepository, FsDocumentBlobRepository, FsBatchingRepository
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from tests.fins.test_fins_storage_atomicity import _publish_snapshot_version, _create_complete_source
from tests.fins.company_meta_test_support import stage_company_meta_fixture
from dayu.fins.storage import FsCompanyMetaRepository
from dayu.fins.domain.document_models import CompanyMeta, SourceDocumentUpsertRequest, SourceHandle, now_iso8601
from dayu.fins.ticker_normalization import build_company_ticker_identity
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.tools.read_runtime_helpers import FinsReadArgumentError, FinsReadBusinessError
from dayu.fins.cancellation import FinsReadCancelledError
from tests.fins.test_original_read_contract import HTML


def publish_original(
    root: Path, text: str | bytes = HTML, *, replace: bool = False, kind: SourceKind = SourceKind.FILING,
    filename: str = "main.html", content_type: str = "text/html", document_id: str = "original-doc",
) -> None:
    """参数：隔离根、原文或待解码字节、替换标志、namespace、exact 资产名/媒体及文档 ID。返回：无。异常：真实 Fs 发布错误。"""
    repos = build_fs_repository_set(workspace_root=root)
    sources = FsSourceDocumentRepository(workspace_root=root, repository_set=repos)
    blobs = FsDocumentBlobRepository(workspace_root=root, repository_set=repos)
    batches = FsBatchingRepository(workspace_root=root, repository_set=repos)
    companies = FsCompanyMetaRepository(workspace_root=root, repository_set=repos)
    batch = batches.begin_batch("TEST")
    try:
        stage_company_meta_fixture(
            companies,
            CompanyMeta(
                company_id="test-company",
                company_name="Test",
                ticker_identity=build_company_ticker_identity("TEST", ()),
                resolver_version="test",
                updated_at=now_iso8601(),
            ),
            batch=batch,
        )
        if replace:
            sources.reset_source_document("TEST", document_id, kind, batch=batch)
        handle = SourceHandle("TEST", document_id, kind.value)
        first = blobs.store_file(
            handle, filename, BytesIO(b"\xef\xbb\xbf" + (text.encode() if isinstance(text, str) else text)), content_type=content_type, batch=batch
        )
        second = blobs.store_file(
            handle,
            "attachment.html",
            BytesIO(b"<html><body>attachment</body></html>"),
            content_type="text/html",
            batch=batch,
        )
        binary = blobs.store_file(
            handle, "report.pdf", BytesIO(b"%PDF-fake-binary"), content_type="application/pdf", batch=batch
        )
        sources.create_source_document(
            SourceDocumentUpsertRequest(
                ticker="TEST",
                document_id=document_id,
                internal_document_id=document_id,
                form_type="6-K" if kind is SourceKind.FILING else None,
                primary_document="attachment.html",
                files=[first, second, binary],
                meta={"amended": False, "ingest_method": "download", "source_provider": "sec_edgar"},
            ),
            kind,
            batch=batch,
        )
    except BaseException:
        batches.rollback_batch(batch)
        raise
    batches.commit_batch(batch)


class CancelToken:
    """只用于本次调用的可变测试 token。"""

    def __init__(self, after: int = 0) -> None:
        """参数：第几次检查取消，0 为不取消。返回：无。异常：无。"""
        self.after = after
        self.calls = 0

    def is_cancelled(self) -> bool:
        """参数：无。返回：当前检查是否触发取消。异常：无。"""
        self.calls += 1
        return self.after > 0 and self.calls >= self.after

    def cancel_reason(self) -> str | None:
        """参数：无。返回：无业务内容的原因。异常：无。"""
        return None

    def requested_at(self) -> datetime | None:
        """参数：无。返回：无。异常：无。"""
        return None


def test_old_active_borrow_and_new_publication_keep_own_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """参数：隔离 Fs 根与读点探针。返回：无。异常：旧 borrow 或新 publication 身份/内容混版。"""
    publish_original(tmp_path, "<p>OLD</p>")
    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path)
    entered, release = Event(), Event()
    real = OriginalContent.read_text

    def blocked(
        self: OriginalContent,
        asset: SourceAssetIdentity,
        start: int,
        end: int,
        max_chars: int,
        token: CancellationToken | None,
    ) -> OriginalTextResult:
        """参数：实际读取输入。返回：实际原文页。异常：等待/读取失败。"""
        if "OLD" in self.text:
            entered.set()
            assert release.wait(5)
        return real(self, asset, start, end, max_chars, token)

    monkeypatch.setattr(OriginalContent, "read_text", blocked)
    try:
        reader = runtime.get_read_runtime()
        assets = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)
        old = next(a["asset"] for a in assets["assets"] if a["asset"]["filename"] == "main.html")
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                reader.read_original_text,
                ticker="TEST",
                document_id="original-doc",
                source_kind=SourceKind.FILING,
                filename="main.html",
                expected_sha256=old["sha256"],
            )
            assert entered.wait(5)
            publish_original(tmp_path, "<p>NEW</p>", replace=True)
            listing = reader.list_document_assets(
                ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING
            )
            new = next(a["asset"] for a in listing["assets"] if a["asset"]["filename"] == "main.html")
            fresh = reader.read_original_text(
                ticker="TEST",
                document_id="original-doc",
                source_kind=SourceKind.FILING,
                filename="main.html",
                expected_sha256=new["sha256"],
            )
            release.set()
            previous = future.result(5)
        assert previous["asset"] == old and previous["text"] == "<p>OLD</p>"
        assert fresh["asset"] == new and fresh["text"] == "<p>NEW</p>"
    finally:
        release.set()
        runtime.close()


def test_parse_cancellation_and_concurrent_warm_build(tmp_path: Path) -> None:
    """参数：真实大文本根。返回：无。异常：解析不观察本次 token、失败污染缓存或并发结果不同。"""
    publish_original(tmp_path, "<html><body>" + "<p>x</p>" * 3000 + "</body></html>")
    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path)
    try:
        reader = runtime.get_read_runtime()
        listing = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)
        asset = next(a["asset"] for a in listing["assets"] if a["asset"]["filename"] == "main.html")
        reader.read_original_text(
            ticker="TEST",
            document_id="original-doc",
            source_kind=SourceKind.FILING,
            filename="main.html",
            expected_sha256=asset["sha256"],
        )
        with pytest.raises(FinsReadCancelledError):
            reader.read_original_structure(
                ticker="TEST",
                document_id="original-doc",
                source_kind=SourceKind.FILING,
                filename="main.html",
                expected_sha256=asset["sha256"],
                cancellation_token=CancelToken(12),
            )
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(
                reader.read_original_structure,
                ticker="TEST",
                document_id="original-doc",
                source_kind=SourceKind.FILING,
                filename="main.html",
                expected_sha256=asset["sha256"],
                max_nodes=7,
            )
            second = executor.submit(
                reader.read_original_structure,
                ticker="TEST",
                document_id="original-doc",
                source_kind=SourceKind.FILING,
                filename="main.html",
                expected_sha256=asset["sha256"],
                max_nodes=19,
            )
            a, b = first.result(5), second.result(5)
        assert len(a["nodes"]) == 7 and len(b["nodes"]) == 19
        assert a["nodes"] == b["nodes"][:7]
        assert a["truncated"] and b["truncated"]
    finally:
        runtime.close()


def test_public_assets_windows_and_namespace_discovery(tmp_path: Path) -> None:
    """参数：真实 Fs 根。返回：无。异常：公开身份、选件、结构发现/facts 回读或分页失败。"""
    publish_original(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path)
    try:
        reader = runtime.get_read_runtime()
        listing = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)
        assert listing["reading_primary_filename"] == "attachment.html"
        asset = next(a["asset"] for a in listing["assets"] if a["asset"]["filename"] == "main.html")
        assert all(a["role_status"] == "unrecorded" for a in listing["assets"])
        assert asset["sha256"] == hashlib.sha256(b"\xef\xbb\xbf" + HTML.encode()).hexdigest()
        structure = reader.read_original_structure(
            ticker="TEST",
            document_id="original-doc",
            source_kind=SourceKind.FILING,
            filename="main.html",
            expected_sha256=asset["sha256"],
        )
        root = structure["nodes"][0]
        namespace = next(
            a["value"]["preview"] for a in root["attributes"] if a["name"] == "xmlns:c" and a["value"] is not None
        )
        facts = reader.query_original_facts(
            ticker="TEST",
            document_id="original-doc",
            source_kind=SourceKind.FILING,
            filename="main.html",
            expected_sha256=asset["sha256"],
            concepts=[{"namespace_uri": namespace, "local_name": "Flag"}],
        )
        assert facts["total_matches"] == 1
        context = facts["facts"][0]["context"]["target"]
        assert context is not None
        span = context["span"]
        back = reader.read_original_text(
            ticker="TEST",
            document_id="original-doc",
            source_kind=SourceKind.FILING,
            filename="main.html",
            expected_sha256=asset["sha256"],
            start=span["start"],
            end=span["end"],
        )
        assert back["text"] == context["preview"]
        assert back["asset"] == asset
        assert back["truncated"] is False and back["next_start"] is None
    finally:
        runtime.close()


def test_warm_cache_uses_current_token_budget_and_publication(tmp_path: Path) -> None:
    """参数：真实 Fs 根。返回：无。异常：暖调用复用旧 token/预算、资产串读或版本身份错配。"""
    publish_original(tmp_path, "<p>" + "a" * 70_000 + "</p>")
    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path)
    try:
        reader = runtime.get_read_runtime()
        first_token = CancelToken()
        assets = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)
        asset = next(a["asset"] for a in assets["assets"] if a["asset"]["filename"] == "main.html")
        first = reader.read_original_text(
            ticker="TEST",
            document_id="original-doc",
            source_kind=SourceKind.FILING,
            filename="main.html",
            expected_sha256=asset["sha256"],
            max_chars=17,
            cancellation_token=first_token,
        )
        first_token.after = 1
        warm = reader.read_original_text(
            ticker="TEST",
            document_id="original-doc",
            source_kind=SourceKind.FILING,
            filename="main.html",
            expected_sha256=asset["sha256"],
            start=17,
            max_chars=30,
        )
        assert first["next_start"] == 17 and len(warm["text"]) == 30 and warm["returned_range"]["start"] == 17
        with pytest.raises(FinsReadCancelledError):
            reader.read_original_text(
                ticker="TEST",
                document_id="original-doc",
                source_kind=SourceKind.FILING,
                filename="main.html",
                expected_sha256=asset["sha256"],
                cancellation_token=CancelToken(1),
            )
        publish_original(tmp_path, "<p>NEW</p>", replace=True)
        with pytest.raises(FinsReadBusinessError) as mismatch:
            reader.read_original_text(
                ticker="TEST",
                document_id="original-doc",
                source_kind=SourceKind.FILING,
                filename="main.html",
                expected_sha256=asset["sha256"],
            )
        assert mismatch.value.code.value == "asset_version_mismatch"
        new_assets = reader.list_document_assets(
            ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING
        )
        new = next(a["asset"] for a in new_assets["assets"] if a["asset"]["filename"] == "main.html")
        assert new["sha256"] != asset["sha256"]
        publish_original(tmp_path, "<p>NEW</p>", replace=True)
        assert (
            reader.read_original_text(
                ticker="TEST",
                document_id="original-doc",
                source_kind=SourceKind.FILING,
                filename="main.html",
                expected_sha256=new["sha256"],
            )["text"]
            == "<p>NEW</p>"
        )
    finally:
        runtime.close()


@pytest.mark.parametrize(
    "mode", ("bool", "negative", "reverse", "eof", "budget", "filename", "hash", "pdf", "nodes_budget", "concepts")
)
def test_argument_and_unsupported_fail_closed(tmp_path: Path, mode: str) -> None:
    """参数：隔离根和反例。返回：无。异常：静默 clamp/fallback 或错误分类不符。"""
    publish_original(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path)
    try:
        reader = runtime.get_read_runtime()
        assets = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)
        filename = "report.pdf" if mode == "pdf" else "main.html"
        asset = next(a["asset"] for a in assets["assets"] if a["asset"]["filename"] == filename)
        with pytest.raises(FinsReadBusinessError if mode == "pdf" else FinsReadArgumentError):
            if mode == "concepts":
                reader.query_original_facts(
                    ticker="TEST",
                    document_id="original-doc",
                    source_kind=SourceKind.FILING,
                    filename=filename,
                    expected_sha256=asset["sha256"],
                    concepts=[],
                )
            elif mode == "nodes_budget":
                reader.read_original_structure(
                    ticker="TEST",
                    document_id="original-doc",
                    source_kind=SourceKind.FILING,
                    filename=filename,
                    expected_sha256=asset["sha256"],
                    max_nodes=1001,
                )
            else:
                reader.read_original_text(
                    ticker="TEST",
                    document_id="original-doc",
                    source_kind=SourceKind.FILING,
                    filename="../main.html" if mode == "filename" else filename,
                    expected_sha256="bad" if mode == "hash" else asset["sha256"],
                    start=(
                        True
                        if mode == "bool"
                        else -1 if mode == "negative" else 10 if mode == "reverse" else 999999 if mode == "eof" else 0
                    ),
                    end=1 if mode == "reverse" else None,
                    max_chars=65537 if mode == "budget" else 100,
                )
    finally:
        runtime.close()


def test_full_snapshot_actual_identity_and_light_rejection(tmp_path: Path) -> None:
    """参数：隔离仓储根。返回：无。异常：复制身份不实或 light 冒充实际身份时断言失败。"""
    repos = build_fs_repository_set(workspace_root=tmp_path)
    sources = FsSourceDocumentRepository(workspace_root=tmp_path, repository_set=repos)
    blobs = FsDocumentBlobRepository(workspace_root=tmp_path, repository_set=repos)
    batches = FsBatchingRepository(workspace_root=tmp_path, repository_set=repos)
    _publish_snapshot_version(sources, blobs, batches, version="A", replace_existing=False)
    with sources.read_source_snapshot("AAPL", "snapshot-doc", SourceKind.FILING, materialize_files=True) as snapshot:
        for descriptor in snapshot.files:
            with snapshot.get_source(descriptor.name).open() as stream:
                payload = stream.read()
            identity = snapshot.get_content_identity(descriptor.name)
            assert identity.sha256 == hashlib.sha256(payload).hexdigest()
            assert identity.size_bytes == len(payload)
    with sources.read_source_snapshot("AAPL", "snapshot-doc", SourceKind.FILING, materialize_files=False) as light:
        with pytest.raises(RuntimeError):
            light.get_content_identity(light.primary_filename)


def test_storage_produces_identity_without_declared_hash_or_size(tmp_path: Path) -> None:
    """参数：隔离真实根。返回：无。异常：无可选声明时伪造摘要/大小或不计算实际身份。"""
    publish_original(tmp_path)
    path = next((tmp_path / "portfolio" / "TEST" / "filings").glob("*/meta.json"))
    meta = json.loads(path.read_text())
    for entry in meta["files"]:
        entry.pop("sha256", None)
        entry.pop("size", None)
    path.write_text(json.dumps(meta))
    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path)
    try:
        result = runtime.get_read_runtime().list_document_assets(
            ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING
        )
        main = next(a["asset"] for a in result["assets"] if a["asset"]["filename"] == "main.html")
        payload = b"\xef\xbb\xbf" + HTML.encode()
        assert main["sha256"] == hashlib.sha256(payload).hexdigest()
        assert main["size_bytes"] == len(payload)
    finally:
        runtime.close()


def test_exact_namespace_collision_and_empty_asset(tmp_path: Path) -> None:
    """参数：隔离 Fs 根。返回：无。异常：同 ID 跨 kind 串读、空原件冒充不存在或便利入口不拒绝歧义。"""
    repos = build_fs_repository_set(workspace_root=tmp_path)
    sources = FsSourceDocumentRepository(workspace_root=tmp_path, repository_set=repos)
    blobs = FsDocumentBlobRepository(workspace_root=tmp_path, repository_set=repos)
    batches = FsBatchingRepository(workspace_root=tmp_path, repository_set=repos)
    batch = batches.begin_batch("AAPL")
    _create_complete_source(
        sources, blobs, batch=batch, document_id="shared", source_kind=SourceKind.FILING, payload=b""
    )
    _create_complete_source(
        sources, blobs, batch=batch, document_id="shared", source_kind=SourceKind.MATERIAL, payload=b"material"
    )
    batches.commit_batch(batch)
    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path)
    try:
        reader = runtime.get_read_runtime()
        identities: list[SourceAssetIdentity] = []
        for kind, expected in ((SourceKind.FILING, ""), (SourceKind.MATERIAL, "material")):
            listing = reader.list_document_assets(ticker="AAPL", document_id="shared", source_kind=kind)
            asset = next(a["asset"] for a in listing["assets"] if a["asset"]["filename"] == "shared.txt")
            identities.append(asset)
            page = reader.read_original_text(
                ticker="AAPL",
                document_id="shared",
                source_kind=kind,
                filename="shared.txt",
                expected_sha256=asset["sha256"],
            )
            assert page["text"] == expected and page["truncated"] is False
        assert identities[0]["size_bytes"] == 0 and identities[0]["sha256"] == hashlib.sha256(b"").hexdigest()
        assert identities[0]["source_kind"] != identities[1]["source_kind"]
        with pytest.raises(ValueError):
            reader.get_document_sections(ticker="AAPL", document_id="shared")
    finally:
        runtime.close()


def test_bad_concept_shape_is_argument_failure_and_parser_failure_keeps_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """参数：真实根及执行错误探针。返回：无。异常：非法 shape 泄漏 TypeError 或解析失败冒充零事实。"""
    publish_original(tmp_path)
    runtime = DefaultFinsRuntime.create(workspace_root=tmp_path)
    try:
        reader = runtime.get_read_runtime()
        listing = reader.list_document_assets(ticker="TEST", document_id="original-doc", source_kind=SourceKind.FILING)
        asset = next(a["asset"] for a in listing["assets"] if a["asset"]["filename"] == "main.html")
        with pytest.raises(FinsReadArgumentError):
            reader.query_original_facts(
                ticker="TEST",
                document_id="original-doc",
                source_kind=SourceKind.FILING,
                filename="main.html",
                expected_sha256=asset["sha256"],
                concepts=cast(Sequence[ExpandedName], [None]),
            )

        def fail_scan(self: OriginalStructure, token: CancellationToken | None) -> None:
            """参数：实际 parser 与 token。返回：无。异常：模拟执行故障，不模拟解析结果。"""
            raise RuntimeError("parser execution fault")

        monkeypatch.setattr(OriginalStructure, "_scan", fail_scan)
        with pytest.raises(FinsReadBusinessError) as error:
            reader.read_original_structure(
                ticker="TEST",
                document_id="original-doc",
                source_kind=SourceKind.FILING,
                filename="main.html",
                expected_sha256=asset["sha256"],
            )
        assert error.value.code.value == "original_parse_failed"
        assert isinstance(error.value.__cause__, RuntimeError)
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
    finally:
        runtime.close()
