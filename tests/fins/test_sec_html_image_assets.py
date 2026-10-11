"""SEC 直接图片发现、正式版本资格与原子 publication 的 owner 回归。"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from threading import Event
from typing import BinaryIO
from urllib.parse import quote

import httpx
import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import (
    BatchToken, DocumentHandle, FileObjectMeta, ProcessedCreateRequest, ProcessedHandle,
    SourceDocumentUpsertRequest, SourceFileEntry, SourceHandle,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.downloaders.sec_downloader import (
    RemoteFileDescriptor, SecDownloader, SecHtmlImageDependencyError, SecDownloadCancelledError,
    build_source_fingerprint,
)
from dayu.fins.pipelines.download_events import DownloadEvent, DownloadEventType
from dayu.fins.pipelines.sec_filing_collection import FilingRecord
from dayu.fins.pipelines.sec_pipeline import SEC_PIPELINE_DOWNLOAD_VERSION, SecPipeline
from dayu.fins.processors.registry import build_fins_processor_registry
from dayu.fins.storage import (
    FsBatchingRepository, FsDocumentBlobRepository, FsMaterialUploadStateRepository,
    FsProcessedDocumentRepository, FsSourceDocumentRepository, SourceIntegrityStatus,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set

_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/42/000000000000000042/"
_ACCESSION = "0000000000-00-000042"
_DOCUMENT = f"fil_{_ACCESSION}"
_OLD_VERSION = "sec_pipeline_download_v1.2.0"
_IMAGE_BYTES = b"SYNTHETIC image bytes: deterministic test asset, not an SEC original"
_TEST_BARRIER_TIMEOUT_SECONDS = 10
_ORIGINAL_STORE_FILE = FsDocumentBlobRepository.store_file
_ORIGINAL_UPDATE_SOURCE_DOCUMENT = FsSourceDocumentRepository.update_source_document
_IMAGE_ENTRY_TEMPLATES = (
    '<img src="{reference}">',
    '<img srcset="{reference} 1x">',
    '<picture><source srcset="{reference} 1x"></picture>',
)
_IMAGE_AND_BASE_TEMPLATES = (*_IMAGE_ENTRY_TEMPLATES, '<base href="{reference}"><img src="#part">')


def _descriptor(name: str, *, metadata: bool = False) -> RemoteFileDescriptor:
    """参数为名称与元数据开关；返回明确测试描述符；无异常。"""
    return RemoteFileDescriptor(name, _ARCHIVE + quote(name, safe=""), '"test"' if metadata else None, None, None)


@dataclass
class _Network:
    """只改变 HTTP 响应，生产 parser、transport、workflow 与仓储真实执行。"""

    html: bytes
    failure: str | None = None
    requests: list[tuple[str, str]] = field(default_factory=list)
    cancelled: bool = False
    cancel_method: str | None = None
    missing_head: bool = False
    failure_name: str = "plot.jpg"
    precheck_html: bytes | None = None
    html_gets: int = 0

    def respond(self, request: httpx.Request) -> httpx.Response:
        """参数为请求；返回确定性 HTTP 响应；timeout 故障按配置抛出。"""
        name = request.url.path.rsplit("/", 1)[-1]
        self.requests.append((request.method, str(request.url)))
        if name == "index.json":
            return httpx.Response(200, json={"directory": {"item": [{"name": "report.htm"}]}})
        if name.endswith("-index-headers.html"):
            return httpx.Response(200, text="<DOCUMENT>\n<TYPE>6-K\n<FILENAME>report.htm\n</DOCUMENT>")
        if name == self.failure_name and request.method == self.cancel_method:
            self.cancelled = True
        if request.method == "HEAD":
            return httpx.Response(404 if self.missing_head else 200, headers={} if self.missing_head else {"ETag": '"test"'})
        if name == "report.htm":
            if self.failure == "base404":
                return httpx.Response(404, content=b"isolated base failure")
            self.html_gets += 1
            payload = self.precheck_html if self.precheck_html is not None and self.html_gets <= 2 else self.html
            return httpx.Response(200, content=payload)
        if name.endswith(".jpg"):
            if name == self.failure_name and self.failure == "timeout":
                raise httpx.ReadTimeout("isolated image timeout", request=request)
            return httpx.Response(404 if name == self.failure_name and self.failure == "404" else 200,
                                  content=b"" if name == self.failure_name and self.failure == "empty" else _IMAGE_BYTES)
        raise AssertionError(f"unexpected transport: {request.method} {name}")

    def is_cancelled(self) -> bool:
        """无参数；返回测试协作取消状态；无异常。"""
        return self.cancelled


async def _discover(root: Path, payloads: dict[str, bytes], *, metadata: bool = False) -> list[RemoteFileDescriptor]:
    """参数为根、待发布字节和 HEAD 开关；返回真实发现结果；发现错误透传。"""
    network = _Network(b"")
    async with httpx.AsyncClient(transport=httpx.MockTransport(network.respond)) as client:
        downloader = SecDownloader(root, client=client, user_agent="Dayu test test@example.com")
        downloader.configure(user_agent="Dayu test test@example.com", sleep_seconds=0, max_retries=1)
        result = await downloader.list_filing_image_files(
            cik="00042", accession_no_dash=_ACCESSION.replace("-", ""), html_payloads=payloads,
            existing_files=[_descriptor(name) for name in payloads], include_http_metadata=metadata,
        )
        assert network.requests == [("HEAD", descriptor.source_url) for descriptor in result] if metadata else not network.requests
        return result


@pytest.mark.parametrize("markup,names", [
    ('<IMG SRC="plot.jpg?v=1&amp;x=2#p"/><img src="./plot.jpg"><img srcset="plot.jpg 1x, wide.jpg 2x">', {"plot.jpg", "wide.jpg"}),
    ('<picture><source media="never" type="unknown" srcset="plot.jpg 100w, wide.jpg 200w"/><img></picture><source srcset="ignored.jpg 1x">', {"plot.jpg", "wide.jpg"}),
    ('<img srcset="plot.jpg, wide.jpg 2x,">', {"plot.jpg", "wide.jpg"}),
    ('<img srcset="plot.jpg .5x,wide.jpg 2.0e0x">', {"plot.jpg", "wide.jpg"}),
    ('<img srcset="plot.jpg\t1x,\nwide.jpg\f2x\r">', {"plot.jpg", "wide.jpg"}),
    ('<img srcset="data:image/png;base64,AA== 1x, plot.jpg 2x">', {"plot.jpg"}),
    ('<img srcset="data:image/png,100%25 1x, plot.jpg?label=100% 2x">', {"plot.jpg"}),
    ('<picture><source srcset="data:image/png,100%25 1x, plot.jpg#%GG 2x"></picture>', {"plot.jpg"}),
    ('<img srcset="data:image/png;base64,AA==">', set()),
    ('<img src="data:image/png;base64,AA=="><img srcset=" \t\n"><img src="">', set()),
    ('<img srcset="chart%2C1.jpg 1x, chart%20wide.jpg 2x">', {"chart,1.jpg", "chart wide.jpg"}),
    ('<img src="https://outside.invalid/plot.jpg"><img src="https://www.sec.gov/Archives/edgar/data/42/000000000000000042x/plot.jpg">', set()),
    ('<img src="//www.sec.gov:443/Archives/edgar/data/42/000000000000000042/plot.jpg">', {"plot.jpg"}),
    ('<img src="#part">', set()),
])
def test_direct_candidates_owner(tmp_path: Path, markup: str, names: set[str]) -> None:
    """参数为根、合成 HTML 与全集；返回无；URL、去重或候选漏选时断言失败。"""
    descriptors = asyncio.run(_discover(tmp_path, {"report.htm": b"\xef\xbb\xbf" + markup.encode()}, metadata=True))
    assert {descriptor.name for descriptor in descriptors} == names
    assert {descriptor.source_url for descriptor in descriptors} == {_ARCHIVE + quote(name, safe="") for name in names}
    assert all(descriptor.sec_document_type is None and descriptor.sec_description is None for descriptor in descriptors)


@pytest.mark.parametrize("srcset", [
    ",plot.jpg 1x", "plot.jpg 1x,,wide.jpg 2x", "plot.jpg,,", "plot.jpg,wide.jpg", "chart,1.jpg",
    "plot.jpg 1x, wide.jpg 1.0x", "plot.jpg, wide.jpg 1x", "plot.jpg 1w, wide.jpg 1x",
    "plot.jpg 1w, wide.jpg", "plot.jpg 1x 2x", "plot.jpg 0w", "plot.jpg -1x", "plot.jpg 0x",
    "plot.jpg NaNx", "plot.jpg Infx", "plot.jpg 1h", "plot.jpg 1.0w", "plot.jpg (1x)",
    "data:image/png,%GG 1x, plot.jpg 2x", "data:image/png,100% 1x, plot.jpg 2x",
    "data:image/%GG,AA== 1x, plot.jpg 2x", "data:image/png;base64,AA==, plot.jpg 2x", "data:image/png,a,b 1x, plot.jpg 2x",
    "data:image/png;base64,AA== , plot.jpg 2x", "plot.jpg 1x, data:image/png;base64,AA== 1.0x",
])
def test_srcset_whole_list_failure(tmp_path: Path, srcset: str) -> None:
    """参数为根与非法列表；返回无；部分集合被接受或错误原因不符时失败。"""
    with pytest.raises(SecHtmlImageDependencyError, match="srcset") as caught:
        asyncio.run(_discover(tmp_path, {"report.htm": f'<img src="safe.jpg"><img srcset="{srcset}">'.encode()}))
    assert caught.value.reason_code == "html_image_reference_invalid"
    assert caught.value.__cause__ is not None


@pytest.mark.parametrize("base,source,names", [
    ("", "plot.jpg", {"plot.jpg"}), ("<base href><base href='https://outside.invalid/'>", "plot.jpg", {"plot.jpg"}),
    ("<base><base href='./'><base href='https://outside.invalid/'>", "plot.jpg", {"plot.jpg"}),
    (f"<base href='{_ARCHIVE}'>", "plot.jpg", {"plot.jpg"}),
    ("<base href='/Archives/edgar/data/42/000000000000000042/'>", "plot.jpg", {"plot.jpg"}),
    ("<base href='?seed=1#old'>", "plot.jpg", {"plot.jpg"}),
    ("<base href='anchor.jpg?seed=1#old'>", "?v=2", {"anchor.jpg"}),
    ("<base href='anchor.jpg?seed=1#old'>", "#part", {"anchor.jpg"}),
    ("<base href='sub/../'>", "plot.jpg", {"plot.jpg"}),
    (f"<base href='{_ARCHIVE}sub/../'>", "plot.jpg", {"plot.jpg"}),
    ("<base href='sub/'>", _ARCHIVE + "plot.jpg", {"plot.jpg"}),
    ("<base href='sub/'>", "/Archives/edgar/data/42/000000000000000042/plot.jpg", {"plot.jpg"}),
    ("<base href='https://outside.invalid/'>", _ARCHIVE + "plot.jpg", {"plot.jpg"}),
    ("<base href='%GG'>", "//www.sec.gov/Archives/edgar/data/42/000000000000000042/plot.jpg", {"plot.jpg"}),
    ("<base href='file:///secret/'>", _ARCHIVE + "plot.jpg", {"plot.jpg"}),
])
@pytest.mark.parametrize("base_after", [False, True])
def test_first_base_complete_url_owner(tmp_path: Path, base: str, source: str, names: set[str], base_after: bool) -> None:
    """参数为合成 base、引用、全集与顺序；返回无；首 base/完整地址语义不符时失败。"""
    img = f'<img src="{source}">'
    markup = img + base if base_after else base + img
    descriptors = asyncio.run(_discover(tmp_path, {"report.htm": markup.encode()}))
    assert {descriptor.source_url for descriptor in descriptors} == {_ARCHIVE + name for name in names}


@pytest.mark.parametrize("markup,message", [
    ("<base href='https://outside.invalid/'><base href='./'><img src='plot.jpg'>", "base"),
    ("<base href='../'><img src='#p'>", "base"),
    (f"<base href='{_ARCHIVE}../'><img src='plot.jpg'>", "base"),
    ("<base href='../'><img src='?v=1'>", "base"),
    ("<base href='https://www.sec.gov/Archives/edgar/data/43/000000000000000042/'><img src='/plot.jpg'>", "base"),
    ("<base href='%2e/'><img src='plot.jpg'>", "base"),
    ("<base href='sub/'> <img src='plot.jpg'>", "子目录"),
    ("<img src='sub/plot.jpg'>", "子目录"),
    ("<img src='../plot.jpg'>", "不安全"), ("<img src='plot%2f.jpg'>", "不安全"),
    ("<img src='plot%2520.jpg'>", "不安全"), ("<img src='plot%00.jpg'>", "不安全"),
    ("<img src='plot%FF.jpg'>", "不安全"), ("<img src='p\\lot.jpg'>", "不安全"),
    ("<img src='p&#10;lot.jpg'>", "不安全"), ("<img src='C:plot.jpg'>", "不安全"),
    ("<img src='p&#129;lot.jpg'>", "不安全"), ("<img src='plot%C2%85.jpg'>", "不安全"),
    ("<img src='meta.json'>", "冲突"), ("<img src='plot.jpg'><img src='PLOT.jpg'>", "冲突"),
    ("<img src='caf%C3%A9.jpg'><img src='cafe%CC%81.jpg'>", "冲突"),
])
def test_address_discovery_failure(tmp_path: Path, markup: str, message: str) -> None:
    """参数为非法地址输入与安全原因；返回无；未封闭失败或原因不符时断言失败。"""
    with pytest.raises(SecHtmlImageDependencyError, match=message):
        asyncio.run(_discover(tmp_path, {"report.htm": markup.encode()}))


def test_decode_collision_and_cross_html_owner(tmp_path: Path) -> None:
    """参数为根；返回无；严格解码、base 文件碰撞与跨 HTML 去重不符时失败。"""
    with pytest.raises(SecHtmlImageDependencyError) as caught:
        asyncio.run(_discover(tmp_path, {"report.htm": b"\xff"}))
    assert caught.value.reason_code == "html_image_decode_failed"
    assert asyncio.run(_discover(tmp_path, {"report.htm": b'<img src="report.htm">'})) == []
    with pytest.raises(SecHtmlImageDependencyError, match="冲突"):
        asyncio.run(_discover(tmp_path, {"report.htm": b'<img src="REPORT.htm">'}))
    descriptors = asyncio.run(_discover(tmp_path, {"report.htm": b'<img src="plot.jpg">', "other.htm": b'<img srcset="./plot.jpg 1x, wide.jpg 2x">'}))
    assert [descriptor.name for descriptor in descriptors] == ["plot.jpg", "wide.jpg"]


_HTML_FINGERPRINT = build_source_fingerprint([_descriptor("report.htm", metadata=True)])
_UNKNOWN_FINGERPRINTS: tuple[JsonValue, ...] = (
    None, 0, False, [], {}, True, 42, 1.25, ["known"], {"fingerprint": "known"}, "", " \t\r\n",
)
_UNKNOWN_FINGERPRINT_IDS = (
    "null", "zero", "false", "empty-array", "empty-mapping", "true", "integer", "float",
    "array", "mapping", "empty-string", "whitespace",
)


def _seed(root: Path, payloads: dict[str, bytes], version: str | None, *,
          source_fingerprint: JsonValue = _HTML_FINGERPRINT, omit_fp: bool = False,
          document_version: str = "v1") -> None:
    """参数为根、文件、下载/内容版本和原始指纹；经正式仓储事务发布来源；存储异常透传。"""
    repositories = build_fs_repository_set(workspace_root=root)
    batching = FsBatchingRepository(root, repository_set=repositories)
    blobs = FsDocumentBlobRepository(root, repository_set=repositories)
    source = FsSourceDocumentRepository(root, repository_set=repositories)
    batch = batching.begin_batch("TEST")
    handle = SourceHandle("TEST", _DOCUMENT, SourceKind.FILING.value)
    try:
        entries: list[dict[str, JsonValue]] = []
        for name, payload in payloads.items():
            meta = blobs.store_file(handle, name, BytesIO(payload), batch=batch)
            entries.append(SourceFileEntry(
                name=name, uri=meta.uri, etag=meta.etag, last_modified=meta.last_modified,
                size=meta.size, content_type=meta.content_type, sha256=meta.sha256,
                source_url=_ARCHIVE + name, http_etag='"test"', ingested_at=meta.last_modified,
            ).to_dict())
        metadata: dict[str, JsonValue] = {
            "ingest_method": "download", "source_provider": "sec_edgar", "company_id": "42",
            "accession_number": _ACCESSION, "filing_date": "2025-02-01", "report_date": "2024-12-31",
            "source_fingerprint": source_fingerprint,
            "document_version": document_version, "first_ingested_at": "2025-02-01T00:00:00+00:00",
            "created_at": "2025-02-01T00:00:00+00:00", "amended": False,
        }
        if version is not None:
            metadata["download_version"] = version
        if omit_fp:
            metadata.pop("source_fingerprint")
        source.create_source_document(SourceDocumentUpsertRequest(
            ticker="TEST", document_id=_DOCUMENT, internal_document_id=_ACCESSION, form_type="10-K",
            primary_document="report.htm", meta=metadata, file_entries=entries,
        ), SourceKind.FILING, batch=batch)
    except BaseException:
        batching.rollback_batch(batch)
        raise
    batching.commit_batch(batch)


def _publication(root: Path) -> tuple[dict[str, JsonValue], str, dict[str, bytes]]:
    """参数为根；经正式同版 snapshot 返回 meta/revision/bytes；仓储异常透传。"""
    source = FsSourceDocumentRepository(root)
    with source.read_source_snapshot("TEST", _DOCUMENT, SourceKind.FILING, materialize_files=True) as snapshot:
        payloads: dict[str, bytes] = {}
        for descriptor in snapshot.files:
            with snapshot.get_source(descriptor.name).open() as stream:
                payloads[descriptor.name] = stream.read()
            with source.get_source("TEST", _DOCUMENT, SourceKind.FILING, descriptor.name).open() as stream:
                assert stream.read() == payloads[descriptor.name]
            assert descriptor.sha256 == hashlib.sha256(payloads[descriptor.name]).hexdigest()
            assert descriptor.size == len(payloads[descriptor.name])
        return dict(snapshot.source_meta), str(snapshot.revision), payloads


def _seed_processed(root: Path) -> FsProcessedDocumentRepository:
    """参数为来源根；通过正式事务发布未标重处理的 processed 并返回仓储；存储异常透传。"""
    repositories = build_fs_repository_set(workspace_root=root)
    batching = FsBatchingRepository(root, repository_set=repositories)
    processed = FsProcessedDocumentRepository(root, repository_set=repositories)
    batch = batching.begin_batch("TEST")
    try:
        processed.create_processed(ProcessedCreateRequest(
            ticker="TEST", document_id=_DOCUMENT, internal_document_id=_ACCESSION,
            source_kind=SourceKind.FILING.value, form_type="10-K", meta={"reprocess_required": False},
            sections=[], tables=[],
        ), batch=batch)
    except BaseException:
        batching.rollback_batch(batch)
        raise
    batching.commit_batch(batch)
    return processed


async def _run(root: Path, network: _Network, *, overwrite: bool = False, form: str = "10-K",
               cancel_checker: Callable[[], bool] | None = None,
               listed_files: list[RemoteFileDescriptor] | None = None) -> list[DownloadEvent]:
    """参数为根、HTTP 响应与调用选项；执行真实单 filing workflow 返回事件；发布异常透传。"""
    async with httpx.AsyncClient(transport=httpx.MockTransport(network.respond)) as client:
        downloader = (
            SecDownloader(root, client=client, user_agent="Dayu test test@example.com")
            if listed_files is None else _ListedDownloader(root, client, listed_files)
        )
        downloader.configure(user_agent="Dayu test test@example.com", sleep_seconds=0, max_retries=1)
        pipeline = SecPipeline(workspace_root=root, downloader=downloader,
                               processor_registry=build_fins_processor_registry(),
                               material_upload_state_repository=FsMaterialUploadStateRepository(root))
        return [event async for event in pipeline._download_single_filing_stream(
            ticker="TEST", cik="42", filing=FilingRecord(form, "2025-02-01", "2024-12-31", _ACCESSION, "report.htm"),
            overwrite=overwrite, cancel_checker=cancel_checker,
        )]


@pytest.mark.parametrize("markup", [
    '<img srcset="plot.jpg 1x, wide.jpg 2x">',
    '<picture><source media="never" srcset="plot.jpg 100w, wide.jpg 200w"><img></picture>',
    '<img src="plot.jpg"><img srcset="plot.jpg 1x, wide.jpg 2x">',
    '<img SRC="plot.jpg" src="ignored.jpg"><img src="wide.jpg">',
    '<img SRCSET="plot.jpg 1x, wide.jpg 2x" srcset="ignored.jpg 1x">',
    '<picture><source SRCSET="plot.jpg 1x, wide.jpg 2x" srcset="ignored.jpg 1x"></picture>',
    '<base href href="https://outside.invalid/"><base href="https://outside.invalid/"><img srcset="plot.jpg 1x, wide.jpg 2x">',
])
@pytest.mark.parametrize("version", ["fresh", _OLD_VERSION, None])
def test_publish_all_candidates_and_upgrade(tmp_path: Path, markup: str, version: str | None) -> None:
    """参数为根、三类输入与旧版本状态；返回无；集合/升级/幂等/寻址不符时失败。"""
    html = markup.encode()
    if version != "fresh":
        _seed(tmp_path, {"report.htm": html}, version)
        before = _publication(tmp_path)[0]
    else:
        before = None
    network = _Network(html)
    events = asyncio.run(_run(tmp_path, network))
    assert events[-1].payload["status"] == "downloaded"
    meta, revision, payloads = _publication(tmp_path)
    assert payloads == {"report.htm": html, "plot.jpg": _IMAGE_BYTES, "wide.jpg": _IMAGE_BYTES}
    assert meta["download_version"] == SEC_PIPELINE_DOWNLOAD_VERSION
    assert meta["source_fingerprint"] == build_source_fingerprint([_descriptor(name, metadata=before is not None) for name in payloads])
    assert meta["document_version"] == ("v2" if before else "v1")
    if before:
        assert meta["first_ingested_at"] == before["first_ingested_at"]
        assert meta["created_at"] == before["created_at"]
    assert sum(method == "GET" and url == _ARCHIVE + "report.htm" for method, url in network.requests) == 1
    network.requests.clear()
    assert asyncio.run(_run(tmp_path, network))[-1].payload["reason_code"] == "already_downloaded_complete"
    assert not network.requests
    assert _publication(tmp_path) == (meta, revision, payloads)


@pytest.mark.parametrize("failure", ["404", "timeout", "empty"])
@pytest.mark.parametrize("markup", ['<img srcset="plot.jpg 1x, wide.jpg 2x">', '<picture><source srcset="plot.jpg 1x, wide.jpg 2x"></picture>'])
@pytest.mark.parametrize("upgrade", [False, True])
def test_necessary_image_failure_is_atomic(tmp_path: Path, failure: str, markup: str, upgrade: bool,
                                          caplog: pytest.LogCaptureFixture) -> None:
    """参数为根、必要失败与旧来源状态；返回无；文件事实、终态或旧发布保留不符时失败。"""
    html = markup.encode()
    before = None
    if upgrade:
        _seed(tmp_path, {"report.htm": html}, _OLD_VERSION)
        before = _publication(tmp_path)
    events = asyncio.run(_run(tmp_path, _Network(html, failure=failure)))
    assert events[-1].event_type is DownloadEventType.FILING_FAILED
    assert events[-1].payload["reason_code"] == "file_download_failed"
    failed = [event for event in events if event.event_type is DownloadEventType.FILE_FAILED]
    assert len(failed) == 1 and failed[0].payload["name"] == "plot.jpg"
    assert 'name="plot.jpg"' in caplog.text
    if before:
        assert _publication(tmp_path) == before
    else:
        assert FsSourceDocumentRepository(tmp_path).classify_source_integrity("TEST", _DOCUMENT, SourceKind.FILING).status is SourceIntegrityStatus.MISSING


@pytest.mark.parametrize("html,expected", [
    (b'<img src="plot.jpg">', "remote_files_equivalent"),
    (b'<img src="plot.jpg"><img src="wide.jpg">', "downloaded"),
    (b'<img srcset="plot.jpg 1x, bad.jpg 1.0x">', "html_image_reference_invalid"),
    (b'<base href="https://outside.invalid/"><img src="plot.jpg">', "html_image_reference_invalid"),
])
@pytest.mark.parametrize("fingerprint", _UNKNOWN_FINGERPRINTS, ids=_UNKNOWN_FINGERPRINT_IDS)
def test_unknown_fingerprint_preconditions_before_skip(tmp_path: Path, html: bytes, expected: str,
                                                      fingerprint: JsonValue, monkeypatch: pytest.MonkeyPatch) -> None:
    """参数为根、未知指纹和远端输入；返回无；GET/发现前置、失败优先或晚跳产生认证时断言失败。"""
    _seed(tmp_path, {"report.htm": b'<img src="plot.jpg">', "plot.jpg": _IMAGE_BYTES},
          SEC_PIPELINE_DOWNLOAD_VERSION, source_fingerprint=fingerprint, document_version="v7")
    before = _publication(tmp_path)
    if expected != "downloaded":
        monkeypatch.setattr(FsBatchingRepository, "begin_batch", _forbid_begin)
    network = _Network(html)
    events = asyncio.run(_run(tmp_path, network))
    terminal = events[-1].payload
    assert terminal.get("reason_code", terminal["status"]) == expected
    assert ("GET", _ARCHIVE + "report.htm") in network.requests
    if expected == "remote_files_equivalent":
        assert ("HEAD", _ARCHIVE + "plot.jpg") in network.requests
        assert ("GET", _ARCHIVE + "plot.jpg") not in network.requests
    if expected != "downloaded":
        assert _publication(tmp_path) == before


def test_prefetch_bytes_are_dependency_truth(tmp_path: Path) -> None:
    """参数为根；返回无；预筛选字节与正式字节不同时依赖或发布字节混用则失败。"""
    formal = b'<html>Unaudited Financial Results 2025 Q1<img src="plot.jpg"></html>'
    network = _Network(formal, precheck_html=b'<html>Unaudited Financial Results 2025 Q1<img src="ignored.jpg"></html>')
    assert asyncio.run(_run(tmp_path, network, form="6-K"))[-1].payload["status"] == "downloaded"
    assert _publication(tmp_path)[2] == {"report.htm": formal, "plot.jpg": _IMAGE_BYTES}
    assert ("GET", _ARCHIVE + "ignored.jpg") not in network.requests


@pytest.mark.parametrize("stage", ["HEAD", "GET"])
def test_cancel_image_transport_preserves_old(tmp_path: Path, stage: str) -> None:
    """参数为根与取消阶段；返回无；新增 HEAD/GET 取消错误发布时失败。"""
    html = b'<img src="plot.jpg">'
    _seed(tmp_path, {"report.htm": html}, _OLD_VERSION)
    before = _publication(tmp_path)
    network = _Network(html, cancel_method=stage)
    events = asyncio.run(_run(tmp_path, network, cancel_checker=network.is_cancelled))
    assert not any(event.event_type is DownloadEventType.FILING_COMPLETED for event in events)
    assert _publication(tmp_path) == before


@pytest.mark.parametrize("version", [_OLD_VERSION, SEC_PIPELINE_DOWNLOAD_VERSION, None])
@pytest.mark.parametrize("fingerprint", ["published", "empty", "omitted"])
def test_rebuild_preserves_download_certification(tmp_path: Path, version: str | None, fingerprint: str) -> None:
    """参数为根、版本及指纹输入状态；返回无；重建改变认证或阻断普通补齐时断言失败。"""
    html = b'<img src="plot.jpg">'
    _seed(tmp_path, {"report.htm": html}, version,
          source_fingerprint=_HTML_FINGERPRINT if fingerprint == "published" else "", omit_fp=fingerprint == "omitted")
    before = _publication(tmp_path)
    # 正式仓储把创建请求缺席的字段规范为空值；不手改 published meta 伪造旧状态。
    if fingerprint != "published":
        assert before[0]["source_fingerprint"] == ""
    pipeline = SecPipeline(workspace_root=tmp_path, processor_registry=build_fins_processor_registry(),
                           material_upload_state_repository=FsMaterialUploadStateRepository(tmp_path))
    assert pipeline.download(ticker="TEST", rebuild=True, start_is_explicit=False)["summary"]["downloaded"] == 1
    after = _publication(tmp_path)
    assert after[0].get("download_version") == version
    assert after[0]["document_version"] == before[0]["document_version"]
    assert after[0]["source_fingerprint"] == before[0]["source_fingerprint"]
    for key in ("files", "source_provider", "internal_document_id", "accession_number",
                "primary_document", "first_ingested_at", "created_at"):
        assert after[0][key] == before[0][key]
    assert after[2] == before[2]
    network = _Network(html)
    terminal = asyncio.run(_run(tmp_path, network))[-1].payload
    if version == SEC_PIPELINE_DOWNLOAD_VERSION and fingerprint == "published":
        assert terminal["reason_code"] == "already_downloaded_complete"
        assert network.requests == []
        assert _publication(tmp_path) == after
    else:
        assert terminal["status"] == "downloaded"
        assert ("GET", _ARCHIVE + "report.htm") in network.requests
        assert ("GET", _ARCHIVE + "plot.jpg") in network.requests
        complete = _publication(tmp_path)
        assert complete[2] == {"report.htm": html, "plot.jpg": _IMAGE_BYTES}
        assert complete[0]["download_version"] == SEC_PIPELINE_DOWNLOAD_VERSION
        assert complete[0]["source_fingerprint"] == build_source_fingerprint([_descriptor(name, metadata=True) for name in complete[2]])
        assert complete[0]["document_version"] == ("v2" if fingerprint == "published" else "v1")
        network.requests.clear()
        assert asyncio.run(_run(tmp_path, network))[-1].payload["reason_code"] == "already_downloaded_complete"
        assert network.requests == []
        assert _publication(tmp_path) == complete


@pytest.mark.parametrize("omit_fp", [False, True])
@pytest.mark.parametrize("failure", ["404", "timeout", "empty"])
def test_rebuild_uncertified_image_failure_retry(tmp_path: Path, omit_fp: bool, failure: str) -> None:
    """参数为根、指纹缺席选项和必要图片故障；返回无；旧发布保留或重试幂等不符时失败。"""
    html = b'<img src="plot.jpg">'
    _seed(tmp_path, {"report.htm": html}, SEC_PIPELINE_DOWNLOAD_VERSION, source_fingerprint="", omit_fp=omit_fp)
    pipeline = SecPipeline(workspace_root=tmp_path, processor_registry=build_fins_processor_registry(),
                           material_upload_state_repository=FsMaterialUploadStateRepository(tmp_path))
    assert pipeline.download(ticker="TEST", rebuild=True, start_is_explicit=False)["summary"]["downloaded"] == 1
    before = _publication(tmp_path)
    network = _Network(html, failure=failure)
    terminal = asyncio.run(_run(tmp_path, network))[-1]
    assert terminal.event_type is DownloadEventType.FILING_FAILED
    assert terminal.payload["reason_code"] == "file_download_failed"
    assert ("GET", _ARCHIVE + "report.htm") in network.requests
    assert ("GET", _ARCHIVE + "plot.jpg") in network.requests
    assert _publication(tmp_path) == before
    network.failure = None
    network.requests.clear()
    assert asyncio.run(_run(tmp_path, network))[-1].payload["status"] == "downloaded"
    complete = _publication(tmp_path)
    assert complete[2] == {"report.htm": html, "plot.jpg": _IMAGE_BYTES}
    assert complete[0]["source_fingerprint"] == build_source_fingerprint([_descriptor(name, metadata=True) for name in complete[2]])
    assert complete[0]["document_version"] == "v1"
    network.requests.clear()
    assert asyncio.run(_run(tmp_path, network))[-1].payload["reason_code"] == "already_downloaded_complete"
    assert network.requests == []
    assert _publication(tmp_path) == complete


@pytest.mark.parametrize("fingerprint,omit_fp", [
    *[pytest.param(value, False, id=name) for value, name in zip(_UNKNOWN_FINGERPRINTS, _UNKNOWN_FINGERPRINT_IDS)],
    pytest.param(None, True, id="missing"),
])
@pytest.mark.parametrize("version", [_OLD_VERSION, SEC_PIPELINE_DOWNLOAD_VERSION])
@pytest.mark.parametrize("rebuild", [False, True])
def test_unknown_fingerprint_complete_publication(tmp_path: Path, fingerprint: JsonValue, omit_fp: bool,
                                                version: str, rebuild: bool) -> None:
    """参数为正式发布的未知指纹、版本和重建开关；返回无；错误认证、升位或重处理时断言失败。"""
    html = b'<img src="plot.jpg">'
    _seed(tmp_path, {"report.htm": html}, version, source_fingerprint=fingerprint,
          omit_fp=omit_fp, document_version="v7")
    processed = _seed_processed(tmp_path)
    before = _publication(tmp_path)
    processed_before = dict(processed.get_processed_meta("TEST", _DOCUMENT))
    assert before[0]["source_fingerprint"] == ("" if omit_fp else fingerprint)
    if rebuild:
        pipeline = SecPipeline(workspace_root=tmp_path, processor_registry=build_fins_processor_registry(),
                               material_upload_state_repository=FsMaterialUploadStateRepository(tmp_path))
        assert pipeline.download(ticker="TEST", rebuild=True, start_is_explicit=False)["summary"]["downloaded"] == 1
        rebuilt = _publication(tmp_path)
        assert rebuilt[0]["source_fingerprint"] == before[0]["source_fingerprint"]
        assert rebuilt[0]["download_version"] == version
        assert rebuilt[0]["document_version"] == "v7"
        assert rebuilt[0]["files"] == before[0]["files"] and rebuilt[2] == before[2]
        assert dict(processed.get_processed_meta("TEST", _DOCUMENT)) == processed_before
    network = _Network(html)
    events = asyncio.run(_run(tmp_path, network))
    assert events[-1].payload["status"] == "downloaded"
    assert ("GET", _ARCHIVE + "report.htm") in network.requests
    assert network.requests.index(("GET", _ARCHIVE + "report.htm")) < network.requests.index(("HEAD", _ARCHIVE + "plot.jpg"))
    assert network.requests.index(("HEAD", _ARCHIVE + "plot.jpg")) < network.requests.index(("GET", _ARCHIVE + "plot.jpg"))
    complete = _publication(tmp_path)
    assert complete[2] == {"report.htm": html, "plot.jpg": _IMAGE_BYTES}
    assert complete[0]["source_fingerprint"] == build_source_fingerprint([_descriptor(name, metadata=True) for name in complete[2]])
    assert complete[0]["download_version"] == SEC_PIPELINE_DOWNLOAD_VERSION
    assert complete[0]["document_version"] == "v7"
    for key in ("first_ingested_at", "created_at"):
        assert complete[0][key] == before[0][key]
    assert dict(processed.get_processed_meta("TEST", _DOCUMENT)) == processed_before
    network.requests.clear()
    assert asyncio.run(_run(tmp_path, network))[-1].payload["reason_code"] == "already_downloaded_complete"
    assert not network.requests and _publication(tmp_path) == complete
    assert dict(processed.get_processed_meta("TEST", _DOCUMENT)) == processed_before


@pytest.mark.parametrize("fingerprint", _UNKNOWN_FINGERPRINTS, ids=_UNKNOWN_FINGERPRINT_IDS)
@pytest.mark.parametrize("version", [_OLD_VERSION, SEC_PIPELINE_DOWNLOAD_VERSION])
def test_unknown_fingerprint_necessary_get_failure_retry(tmp_path: Path, fingerprint: JsonValue, version: str) -> None:
    """参数为根、未知指纹及下载版本；返回无；必要 GET 失败改变旧发布或重试幂等失效时断言失败。"""
    html = b'<img src="plot.jpg">'
    _seed(tmp_path, {"report.htm": html}, version, source_fingerprint=fingerprint, document_version="v7")
    processed = _seed_processed(tmp_path)
    before = _publication(tmp_path)
    processed_before = dict(processed.get_processed_meta("TEST", _DOCUMENT))
    network = _Network(html, failure="404")
    terminal = asyncio.run(_run(tmp_path, network))[-1]
    assert terminal.event_type is DownloadEventType.FILING_FAILED
    assert terminal.payload["reason_code"] == "file_download_failed"
    assert ("GET", _ARCHIVE + "report.htm") in network.requests and ("GET", _ARCHIVE + "plot.jpg") in network.requests
    assert _publication(tmp_path) == before
    assert dict(processed.get_processed_meta("TEST", _DOCUMENT)) == processed_before
    network.failure = None
    network.requests.clear()
    assert asyncio.run(_run(tmp_path, network))[-1].payload["status"] == "downloaded"
    complete = _publication(tmp_path)
    assert complete[2] == {"report.htm": html, "plot.jpg": _IMAGE_BYTES}
    assert complete[0]["document_version"] == "v7"
    assert complete[0]["source_fingerprint"] == build_source_fingerprint([_descriptor(name, metadata=True) for name in complete[2]])
    assert dict(processed.get_processed_meta("TEST", _DOCUMENT)) == processed_before
    network.requests.clear()
    assert asyncio.run(_run(tmp_path, network))[-1].payload["reason_code"] == "already_downloaded_complete"
    assert not network.requests and _publication(tmp_path) == complete


@pytest.mark.parametrize("fingerprint", ["published-fingerprint", " \tpublished-fingerprint\n"])
@pytest.mark.parametrize("version", [_OLD_VERSION, SEC_PIPELINE_DOWNLOAD_VERSION])
def test_known_fingerprint_skip_version_and_processed(tmp_path: Path, fingerprint: str, version: str) -> None:
    """参数为已知字符串和下载版本；返回无；快跳或 v7→v8/processed 既有变化规则回退时断言失败。"""
    html = b'<img src="plot.jpg">'
    _seed(tmp_path, {"report.htm": html}, version, source_fingerprint=fingerprint, document_version="v7")
    processed = _seed_processed(tmp_path)
    before = _publication(tmp_path)
    network = _Network(html)
    terminal = asyncio.run(_run(tmp_path, network))[-1].payload
    if version == SEC_PIPELINE_DOWNLOAD_VERSION:
        assert terminal["reason_code"] == "already_downloaded_complete"
        assert not network.requests and _publication(tmp_path) == before
        assert processed.get_processed_meta("TEST", _DOCUMENT)["reprocess_required"] is False
    else:
        assert terminal["status"] == "downloaded"
        assert _publication(tmp_path)[0]["document_version"] == "v8"
        assert _publication(tmp_path)[2] == {"report.htm": html, "plot.jpg": _IMAGE_BYTES}
        assert processed.get_processed_meta("TEST", _DOCUMENT)["reprocess_required"] is True


@pytest.mark.parametrize("whitespace", [False, True])
def test_known_unchanged_fingerprint_preserves_version_and_processed(tmp_path: Path, whitespace: bool) -> None:
    """参数为根和字符串空白开关；返回无；旧下载版本升级被误判为内容变化时断言失败。"""
    html = b'<img src="plot.jpg">'
    fingerprint = build_source_fingerprint([_descriptor(name, metadata=True) for name in ("report.htm", "plot.jpg")])
    _seed(tmp_path, {"report.htm": html, "plot.jpg": _IMAGE_BYTES}, _OLD_VERSION,
          source_fingerprint=f" \t{fingerprint}\n" if whitespace else fingerprint, document_version="v7")
    processed = _seed_processed(tmp_path)
    before = dict(processed.get_processed_meta("TEST", _DOCUMENT))
    network = _Network(html)
    assert asyncio.run(_run(tmp_path, network))[-1].payload["status"] == "downloaded"
    assert _publication(tmp_path)[0]["document_version"] == "v7"
    assert _publication(tmp_path)[0]["download_version"] == SEC_PIPELINE_DOWNLOAD_VERSION
    assert _publication(tmp_path)[0]["source_fingerprint"] == fingerprint
    assert dict(processed.get_processed_meta("TEST", _DOCUMENT)) == before
    assert ("GET", _ARCHIVE + "plot.jpg") in network.requests


def _fail_rebuild_update(self: FsSourceDocumentRepository, req: SourceDocumentUpsertRequest,
                         source_kind: SourceKind, *, batch: BatchToken) -> DocumentHandle:
    """参数为正式仓储和更新请求/事务；写入真实 staging 后抛错；总是抛出 OSError。"""
    assert "source_fingerprint" not in req.meta
    assert "download_version" not in req.meta
    _ORIGINAL_UPDATE_SOURCE_DOCUMENT(self, req, source_kind, batch=batch)
    raise OSError("isolated rebuild failure after staging update")


@pytest.mark.parametrize("fingerprint", ["published", "empty", "omitted"])
def test_rebuild_failure_preserves_certification_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                            fingerprint: str) -> None:
    """参数为根、更新故障注入和指纹状态；返回无；重建失败改变旧发布或认证时断言失败。"""
    _seed(tmp_path, {"report.htm": b'<img src="plot.jpg">'}, SEC_PIPELINE_DOWNLOAD_VERSION,
          source_fingerprint=_HTML_FINGERPRINT if fingerprint == "published" else "", omit_fp=fingerprint == "omitted")
    before = _publication(tmp_path)
    monkeypatch.setattr(FsSourceDocumentRepository, "update_source_document", _fail_rebuild_update)
    pipeline = SecPipeline(workspace_root=tmp_path, processor_registry=build_fins_processor_registry(),
                           material_upload_state_repository=FsMaterialUploadStateRepository(tmp_path))
    result = pipeline.download(ticker="TEST", rebuild=True, start_is_explicit=False)
    assert result["summary"]["failed"] == 1
    assert _publication(tmp_path) == before


@pytest.mark.parametrize("fingerprint", _UNKNOWN_FINGERPRINTS, ids=_UNKNOWN_FINGERPRINT_IDS)
def test_base_get_failure_precedes_unknown_fingerprint_skip(tmp_path: Path, fingerprint: JsonValue) -> None:
    """参数为根和未知指纹；返回无；必要基础 GET 失败被晚跳覆盖时断言失败。"""
    html = b'<img src="plot.jpg">'
    _seed(tmp_path, {"report.htm": html, "plot.jpg": _IMAGE_BYTES}, SEC_PIPELINE_DOWNLOAD_VERSION,
          source_fingerprint=fingerprint)
    before = _publication(tmp_path)
    network = _Network(html, failure="base404")
    terminal = asyncio.run(_run(tmp_path, network))[-1]
    assert terminal.event_type is DownloadEventType.FILING_FAILED
    assert terminal.payload["reason_code"] == "file_download_failed"
    assert not any(url == _ARCHIVE + "plot.jpg" for _, url in network.requests)
    assert _publication(tmp_path) == before


def test_optional_head_metadata_does_not_block_image_get(tmp_path: Path) -> None:
    """参数为根；返回无；optional HEAD 失败误阻断成功 GET 或漏登记图片时失败。"""
    html = b'<img src="plot.jpg">'
    _seed(tmp_path, {"report.htm": html}, _OLD_VERSION)
    network = _Network(html, missing_head=True)
    assert asyncio.run(_run(tmp_path, network))[-1].payload["status"] == "downloaded"
    assert _publication(tmp_path)[2] == {"report.htm": html, "plot.jpg": _IMAGE_BYTES}
    assert ("GET", _ARCHIVE + "plot.jpg") in network.requests


def _fail_image_store(
    self: FsDocumentBlobRepository, handle: SourceHandle | ProcessedHandle, filename: str, data: BinaryIO,
    *, batch: BatchToken, content_type: str | None = None, metadata: dict[str, str] | None = None,
) -> FileObjectMeta:
    """参数为真实 blob 写入参数；图片写入抛 OSError，其它执行原 owner；返回真实 meta。"""
    if filename == "plot.jpg":
        raise OSError("isolated image store failure")
    return _ORIGINAL_STORE_FILE(self, handle, filename, data, batch=batch, content_type=content_type, metadata=metadata)


def _fail_source_create(
    self: FsSourceDocumentRepository, request: SourceDocumentUpsertRequest, source_kind: SourceKind,
    *, batch: BatchToken,
) -> None:
    """参数为真实 source 创建调用；返回无；模拟发布前存储错误抛 OSError。"""
    raise OSError("isolated source create failure")


@pytest.mark.parametrize("failure", ["image-store", "source-create"])
def test_publication_exception_preserves_old(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    """参数为根、存储故障与 monkeypatch；返回无；发布前异常未回滚旧来源时失败。"""
    html = b'<img src="plot.jpg">'
    _seed(tmp_path, {"report.htm": html}, _OLD_VERSION)
    before = _publication(tmp_path)
    if failure == "image-store":
        monkeypatch.setattr(FsDocumentBlobRepository, "store_file", _fail_image_store)
    else:
        monkeypatch.setattr(FsSourceDocumentRepository, "create_source_document", _fail_source_create)
    with pytest.raises(OSError, match="isolated"):
        asyncio.run(_run(tmp_path, _Network(html)))
    assert _publication(tmp_path) == before


@dataclass
class _BarrierNetwork(_Network):
    """用事件在 A 预取与 Phase B 之间发布真实竞争 winner，不替换 classifier。"""

    ready: Event = field(default_factory=Event)
    winner_committed: Event = field(default_factory=Event)
    released: bool = False

    def respond(self, request: httpx.Request) -> httpx.Response:
        """参数为请求；首次图片 GET 等待 winner，再返回原 mock 响应；超时断言失败。"""
        if request.method == "GET" and request.url.path.endswith("/plot.jpg") and not self.released:
            self.released = True
            self.ready.set()
            assert self.winner_committed.wait(_TEST_BARRIER_TIMEOUT_SECONDS)
        return super().respond(request)


@pytest.mark.parametrize("winner_version", [SEC_PIPELINE_DOWNLOAD_VERSION, _OLD_VERSION])
def test_phase_b_competing_version_qualification(tmp_path: Path, winner_version: str) -> None:
    """参数为根与竞争 writer 版本；返回无；identity 重试后版本资格或整套 winner 保留不符时失败。"""
    html = b'<img src="plot.jpg">attempt-A'
    winner_html = b'<img src="plot.jpg">winner-B'
    network = _BarrierNetwork(html)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, _run(tmp_path, network))
        assert network.ready.wait(_TEST_BARRIER_TIMEOUT_SECONDS)
        _seed(tmp_path, {"report.htm": winner_html, "plot.jpg": _IMAGE_BYTES}, winner_version,
              source_fingerprint=build_source_fingerprint([_descriptor(name, metadata=True) for name in ("report.htm", "plot.jpg")]))
        winner = _publication(tmp_path)
        network.winner_committed.set()
        events = future.result(timeout=_TEST_BARRIER_TIMEOUT_SECONDS)
    if winner_version == SEC_PIPELINE_DOWNLOAD_VERSION:
        assert events[-1].payload["reason_code"] == "already_downloaded_complete"
        assert _publication(tmp_path) == winner
    else:
        assert events[-1].payload["status"] == "downloaded"
        assert _publication(tmp_path)[0]["download_version"] == SEC_PIPELINE_DOWNLOAD_VERSION
        assert _publication(tmp_path)[2] == {"report.htm": html, "plot.jpg": _IMAGE_BYTES}
        assert _publication(tmp_path)[0]["document_version"] == winner[0]["document_version"]
        assert sum(method == "GET" and url == _ARCHIVE + "report.htm" for method, url in network.requests) == 2


@pytest.mark.parametrize("fingerprint", [None, False, ["known"]], ids=["null", "false", "array"])
def test_phase_b_unknown_fingerprint_winner_requires_new_round(tmp_path: Path, fingerprint: JsonValue) -> None:
    """参数为根和竞争发布的未知指纹；返回无；当前版本 winner 被伪认证或混合两轮事实时断言失败。"""
    html = b'<img src="plot.jpg">attempt-A'
    winner_html = b'<img src="plot.jpg">winner-B'
    network = _BarrierNetwork(html)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, _run(tmp_path, network))
        assert network.ready.wait(_TEST_BARRIER_TIMEOUT_SECONDS)
        _seed(tmp_path, {"report.htm": winner_html}, SEC_PIPELINE_DOWNLOAD_VERSION,
              source_fingerprint=fingerprint, document_version="v7")
        winner = _publication(tmp_path)
        network.winner_committed.set()
        events = future.result(timeout=_TEST_BARRIER_TIMEOUT_SECONDS)
    assert events[-1].payload["status"] == "downloaded"
    complete = _publication(tmp_path)
    assert complete[2] == {"report.htm": html, "plot.jpg": _IMAGE_BYTES}
    assert complete[0]["document_version"] == "v7" and complete[1] != winner[1]
    assert sum(method == "GET" and url == _ARCHIVE + "report.htm" for method, url in network.requests) == 2


@pytest.mark.parametrize("stage", ["HEAD", "GET"])
def test_current_unknown_fingerprint_cancel_preserves_publication(tmp_path: Path, stage: str) -> None:
    """参数为根和取消阶段；返回无；未知认证未解除快跳或取消错误发布时断言失败。"""
    html = b'<img src="plot.jpg">'
    _seed(tmp_path, {"report.htm": html}, SEC_PIPELINE_DOWNLOAD_VERSION,
          source_fingerprint={"fingerprint": "known"}, document_version="v7")
    before = _publication(tmp_path)
    network = _Network(html, cancel_method=stage)
    events = asyncio.run(_run(tmp_path, network, cancel_checker=network.is_cancelled))
    assert (stage, _ARCHIVE + "plot.jpg") in network.requests
    assert not any(event.event_type is DownloadEventType.FILING_COMPLETED for event in events)
    assert _publication(tmp_path) == before


def _forbid_begin(self: FsBatchingRepository, ticker: str) -> BatchToken:
    """参数为真实 batch owner 与 ticker；返回无；若发现失败越过 begin 边界则断言失败。"""
    raise AssertionError("图片发现失败之前不得进入 storage batch")


def test_discovery_failure_has_zero_batch_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """参数为根与批入口 guard；返回无；不安全 base 未在 begin 前失败或触及旧来源时失败。"""
    html = b'<img src="plot.jpg">'
    _seed(tmp_path, {"report.htm": html}, _OLD_VERSION)
    before = _publication(tmp_path)
    monkeypatch.setattr(FsBatchingRepository, "begin_batch", _forbid_begin)
    network = _Network(b'<base href="https://outside.invalid/"><img src="plot.jpg">')
    terminal = asyncio.run(_run(tmp_path, network))[-1]
    assert terminal.payload["reason_code"] == "html_image_reference_invalid"
    assert not any(url == _ARCHIVE + "plot.jpg" for _, url in network.requests)
    assert _publication(tmp_path) == before


def test_image_only_upgrade_marks_existing_processed(tmp_path: Path) -> None:
    """参数为根；返回无；旧来源必要图片失败损伤 processed 或补齐未标重处理时失败。"""
    html = b'<img src="plot.jpg">'
    _seed(tmp_path, {"report.htm": html}, _OLD_VERSION)
    repositories = build_fs_repository_set(workspace_root=tmp_path)
    batching = FsBatchingRepository(tmp_path, repository_set=repositories)
    processed = FsProcessedDocumentRepository(tmp_path, repository_set=repositories)
    batch = batching.begin_batch("TEST")
    processed.create_processed(ProcessedCreateRequest(
        ticker="TEST", document_id=_DOCUMENT, internal_document_id=_ACCESSION,
        source_kind=SourceKind.FILING.value, form_type="10-K", meta={"reprocess_required": False},
        sections=[], tables=[],
    ), batch=batch)
    batching.commit_batch(batch)
    before = dict(processed.get_processed_meta("TEST", _DOCUMENT))
    assert asyncio.run(_run(tmp_path, _Network(html, failure="404")))[-1].event_type is DownloadEventType.FILING_FAILED
    assert dict(processed.get_processed_meta("TEST", _DOCUMENT)) == before
    assert asyncio.run(_run(tmp_path, _Network(html)))[-1].payload["status"] == "downloaded"
    assert processed.get_processed_meta("TEST", _DOCUMENT)["reprocess_required"] is True


@pytest.mark.parametrize("markup", [
    '<img src="plot;1.jpg?v=2#p"><img src="plot%3B1.jpg"><img src="plot">',
    '<img srcset="plot;1.jpg?v=2#p 1x, plot%3B1.jpg 2x, plot 3x">',
    '<picture><source srcset="plot;1.jpg 1x, plot%3B1.jpg 2x, plot 3x"></picture>',
])
def test_semicolon_complete_path_identity(tmp_path: Path, markup: str) -> None:
    """参数为根和三入口；返回无；分号截断、编码不等价或与无分号名合并时失败。"""
    descriptors = asyncio.run(_discover(tmp_path, {"report.htm": markup.encode()}, metadata=True))
    assert [(item.name, item.source_url) for item in descriptors] == [
        ("plot", _ARCHIVE + "plot"), ("plot;1.jpg", _ARCHIVE + "plot%3B1.jpg"),
    ]


@pytest.mark.parametrize("base", [
    "anchor;1.jpg?seed=1#old", "anchor%3B1.jpg?seed=1#old",
    _ARCHIVE + "sub;1/../anchor;1.jpg?seed=1#old",
])
@pytest.mark.parametrize("reference", ["?v=2", "#part", "?v=2#part"])
def test_semicolon_file_base_retains_path(tmp_path: Path, base: str, reference: str) -> None:
    """参数为根、分号 file base 与最终 query/fragment；返回无；完整路径丢失时失败。"""
    markup = f'<img src="{reference}"><base href="{base}">'
    descriptors = asyncio.run(_discover(tmp_path, {"report.htm": markup.encode()}, metadata=True))
    assert [(item.name, item.source_url) for item in descriptors] == [("anchor;1.jpg", _ARCHIVE + "anchor%3B1.jpg")]


@pytest.mark.parametrize("markup", [
    '<img src="sub;1/plot;1.jpg">', '<base href="sub;1/"><img src="plot;1.jpg">',
    f'<base href="{_ARCHIVE}sub;1/"><img src="?v=2#part">',
    '<img src="plot;1%2F.jpg">', '<base href="anchor;1%252F.jpg"><img src="#p">',
])
def test_semicolon_unsafe_path_is_typed(tmp_path: Path, markup: str) -> None:
    """参数为根与分号路径；返回无；子目录或分号后的危险编码绕过校验时失败。"""
    with pytest.raises(SecHtmlImageDependencyError) as caught:
        asyncio.run(_discover(tmp_path, {"report.htm": markup.encode()}, metadata=True))
    assert caught.value.reason_code == "html_image_reference_invalid"
    if "sub;1/" in markup:
        assert "子目录" in caught.value.safe_message


@pytest.mark.parametrize("markup,names", [
    ('<img SRC="first.jpg" src="second.jpg">', {"first.jpg"}),
    ('<img src src="second.jpg">', set()), ('<img src="" src="second.jpg">', set()),
    ('<img SRCSET="first.jpg 1x" srcset="second.jpg 1x">', {"first.jpg"}),
    ('<img srcset srcset="second.jpg 1x">', set()), ('<img srcset="" srcset="second.jpg 1x">', set()),
    ('<picture><source SRCSET="first.jpg 1x" srcset="second.jpg 1x"></picture>', {"first.jpg"}),
    ('<picture><source srcset srcset="second.jpg 1x"></picture>', set()),
    ('<picture><source srcset="" srcset="second.jpg 1x"></picture>', set()),
    ('<base HREF="anchor;1.jpg" href="https://outside.invalid/"><base href="other.jpg"><img src="?v=2">', {"anchor;1.jpg"}),
    ('<base href href="https://outside.invalid/"><base href="https://outside.invalid/"><img src="first.jpg">', {"first.jpg"}),
    ('<base href="" href="https://outside.invalid/"><base href="https://outside.invalid/"><img src="first.jpg">', {"first.jpg"}),
])
def test_duplicate_attributes_keep_first_value(tmp_path: Path, markup: str, names: set[str]) -> None:
    """参数为根、重复属性和全集；返回无；None/空首值、大小写或后续 base 规则不符时失败。"""
    descriptors = asyncio.run(_discover(tmp_path, {"report.htm": markup.encode()}, metadata=True))
    assert {item.name for item in descriptors} == names
    assert {item.source_url for item in descriptors} == {_ARCHIVE + quote(name, safe="") for name in names}


@pytest.mark.parametrize("markup", [
    '<img src="plot%25.jpg?v=1#p"><img src="./plot%25.jpg">',
    '<img srcset="plot%25.jpg 1x, ./plot%25.jpg 2x">',
    '<picture><source srcset="plot%25.jpg 1x, ./plot%25.jpg 2x"></picture>',
    '<base href="plot%25.jpg?seed=1#old"><img src="?v=2"><img src="#part">',
])
def test_single_percent_decode_is_legal(tmp_path: Path, markup: str) -> None:
    """参数为根与合法百分号候选/base；返回无；单次解码、去重或 canonical 不符时失败。"""
    descriptors = asyncio.run(_discover(tmp_path, {"report.htm": markup.encode()}, metadata=True))
    assert [(item.name, item.source_url) for item in descriptors] == [("plot%.jpg", _ARCHIVE + "plot%25.jpg")]


@pytest.mark.parametrize("address", ["plot%2520.jpg", "plot%252F.jpg", "plot%252e.jpg", "plot%.jpg", "plot%GG.jpg"])
@pytest.mark.parametrize("entry", ["src", "srcset", "base"])
def test_percent_ambiguity_remains_typed(tmp_path: Path, address: str, entry: str) -> None:
    """参数为根、不安全编码和入口；返回无；二次 triplet/非法原始 triplet 被接受时失败。"""
    markup = (
        f'<base href="{address}"><img src="#p">' if entry == "base"
        else f'<img {entry}="{address}{" 1x" if entry == "srcset" else ""}">'
    )
    with pytest.raises(SecHtmlImageDependencyError) as caught:
        asyncio.run(_discover(tmp_path, {"report.htm": markup.encode()}, metadata=True))
    assert caught.value.reason_code == "html_image_reference_invalid"


async def _discover_with_existing(root: Path, files: list[RemoteFileDescriptor], markup: bytes) -> list[RemoteFileDescriptor]:
    """参数为根、明确基础描述符与正文；返回真实发现结果；typed 发现异常透传且不允许网络。"""
    network = _Network(b"")
    async with httpx.AsyncClient(transport=httpx.MockTransport(network.respond)) as client:
        downloader = SecDownloader(root, client=client, user_agent="Dayu test test@example.com")
        try:
            return await downloader.list_filing_image_files(
                cik="42", accession_no_dash=_ACCESSION.replace("-", ""),
                html_payloads={"report.htm": markup}, existing_files=files, include_http_metadata=True,
            )
        finally:
            assert not network.requests


@pytest.mark.parametrize("name", ["plot;1.jpg", "plot%.jpg"])
def test_canonical_existing_asset_is_reused(tmp_path: Path, name: str) -> None:
    """参数为根与合法基础图名；返回无；基础 exact 资产未复用而重复 HEAD/descriptor 时失败。"""
    encoded = quote(name, safe="")
    markup = f'<img src="{encoded}"><img srcset="./{encoded} 1x">'.encode()
    assert asyncio.run(_discover_with_existing(tmp_path, [_descriptor("report.htm"), _descriptor(name)], markup)) == []


@pytest.mark.parametrize("name", ["../private.htm", "sub/private.htm", "private\\name.htm", " private.htm", "", ".", ".."])
def test_invalid_existing_name_projects_safe_typed_error(tmp_path: Path, name: str) -> None:
    """参数为根和非法基础名；返回无；裸 ValueError、原始地址泄漏或图片请求时失败。"""
    with pytest.raises(SecHtmlImageDependencyError) as caught:
        asyncio.run(_discover_with_existing(tmp_path, [_descriptor("report.htm"), _descriptor(name)], b'<img src="plot.jpg">'))
    assert caught.value.reason_code == "html_image_reference_invalid"
    assert isinstance(caught.value.__cause__, ValueError)
    assert caught.value.html_name == "基础文件"
    assert "private" not in caught.value.safe_message


@pytest.mark.parametrize("name", ["meta.json", "REPORT.htm"])
def test_existing_collision_projects_typed_error(tmp_path: Path, name: str) -> None:
    """参数为根与控制名/基础碰撞；返回无；未 typed 关闭或开始图片请求时失败。"""
    with pytest.raises(SecHtmlImageDependencyError) as caught:
        asyncio.run(_discover_with_existing(tmp_path, [_descriptor("report.htm"), _descriptor(name)], b'<img src="plot.jpg">'))
    assert caught.value.reason_code == "html_image_asset_collision"


class _ListedDownloader(SecDownloader):
    """只在目录描述符输入边界明确注入非法/碰撞名，发现、transport 和 workflow 保持真实。"""

    def __init__(self, root: Path, client: httpx.AsyncClient, files: list[RemoteFileDescriptor]) -> None:
        """参数为根、真实 mock transport client 和输入列表；返回无；父构造异常透传。"""
        super().__init__(root, client=client, user_agent="Dayu test test@example.com")
        self._listed_files = files

    async def list_filing_files(
        self, cik: str, accession_no_dash: str, primary_document: str, form_type: str,
        include_xbrl: bool = True, include_exhibits: bool = True, include_http_metadata: bool = True,
        cancellation_checker: Callable[[], bool] | None = None,
    ) -> list[RemoteFileDescriptor]:
        """参数与正式基础 listing 相同；返回明确测试输入；无异常，不替换发现/预取结果。"""
        return self._listed_files


@pytest.mark.parametrize("name,reason", [("../private.htm", "html_image_reference_invalid"), ("REPORT.htm", "html_image_asset_collision"), ("meta.json", "html_image_asset_collision")])
@pytest.mark.parametrize("upgrade", [False, True])
def test_existing_descriptor_failure_precedes_batch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, reason: str, upgrade: bool) -> None:
    """参数为根、batch guard、坏输入及旧状态；返回无；失败投影/begin/旧 publication 保留不符时失败。"""
    html = b'<img src="plot.jpg">'
    before = None
    if upgrade:
        _seed(tmp_path, {"report.htm": html}, _OLD_VERSION)
        before = _publication(tmp_path)
    monkeypatch.setattr(FsBatchingRepository, "begin_batch", _forbid_begin)
    # 远端正文响应与坏文件名分开供数，确保检验发现 owner 而非提前失败的网络。
    invalid = RemoteFileDescriptor(name, _ARCHIVE + "report.htm", None, None, None)
    network = _Network(html)
    events = asyncio.run(_run(tmp_path, network, listed_files=[_descriptor("report.htm"), invalid]))
    assert events[-1].event_type is DownloadEventType.FILING_FAILED
    assert events[-1].payload["reason_code"] == reason
    assert "private" not in str(events[-1].payload["reason_message"])
    assert not any(url == _ARCHIVE + "plot.jpg" for _, url in network.requests)
    if before:
        assert _publication(tmp_path) == before
    else:
        assert FsSourceDocumentRepository(tmp_path).classify_source_integrity("TEST", _DOCUMENT, SourceKind.FILING).status is SourceIntegrityStatus.MISSING


@pytest.mark.parametrize("name", ["plot;1.jpg", "plot%.jpg"])
def test_special_name_requests_publication_and_failure(tmp_path: Path, name: str, caplog: pytest.LogCaptureFixture) -> None:
    """参数为根、合法特殊名和日志；返回无；exact HEAD/GET、失败名称、rollback/retry/指纹不符时失败。"""
    reference = name if ";" in name else quote(name, safe="")
    html = f'<img src="{reference}?v=1#p"><img srcset="{quote(name, safe="")} 1x">'.encode()
    _seed(tmp_path, {"report.htm": html}, _OLD_VERSION)
    before = _publication(tmp_path)
    canonical = _ARCHIVE + quote(name, safe="")
    network = _Network(html, failure="404", failure_name=name)
    events = asyncio.run(_run(tmp_path, network))
    assert events[-1].event_type is DownloadEventType.FILING_FAILED
    failed = [event for event in events if event.event_type is DownloadEventType.FILE_FAILED]
    assert len(failed) == 1 and failed[0].payload["name"] == name
    assert failed[0].payload["source_url"] == canonical
    assert f'name="{name}"' in caplog.text and "provider_http_status" in caplog.text
    assert [(method, url) for method, url in network.requests if url == canonical] == [("HEAD", canonical), ("GET", canonical)]
    assert _publication(tmp_path) == before
    network.failure = None
    network.requests.clear()
    assert asyncio.run(_run(tmp_path, network))[-1].payload["status"] == "downloaded"
    metadata, _, payloads = _publication(tmp_path)
    assert payloads == {"report.htm": html, name: _IMAGE_BYTES}
    assert metadata["source_fingerprint"] == build_source_fingerprint([_descriptor(filename, metadata=True) for filename in payloads])
    assert [(method, url) for method, url in network.requests if url == canonical] == [("HEAD", canonical), ("GET", canonical)]


@pytest.mark.parametrize("template", _IMAGE_ENTRY_TEMPLATES)
@pytest.mark.parametrize("suffix", ["?label=100%", "#%GG", "?label=%GG#100%", "?next=%2F#%2520"])
def test_discarded_url_fields_share_path_owner(tmp_path: Path, template: str, suffix: str) -> None:
    """参数为根、三入口与丢弃字段；返回无；path 身份、去重或 exact HEAD 不符时失败。"""
    reference = "plot;1%25.jpg" + suffix
    markup = template.format(reference=reference) + '<img src="./plot%3B1%25.jpg">'
    descriptors = asyncio.run(_discover(tmp_path, {"report.htm": markup.encode()}, metadata=True))
    assert [(item.name, item.source_url) for item in descriptors] == [("plot;1%.jpg", _ARCHIVE + "plot%3B1%25.jpg")]


@pytest.mark.parametrize("template", _IMAGE_ENTRY_TEMPLATES)
@pytest.mark.parametrize("base,reference,name", [
    ("anchor;1%25.jpg?seed=%GG#100%", "?v=100%", "anchor;1%.jpg"),
    ("anchor;1%25.jpg?seed=100%#%GG", "#%GG", "anchor;1%.jpg"),
    ("anchor;1%25.jpg?seed=%GG#100%", "plot.jpg?label=%GG#100%", "plot.jpg"),
    ("./?seed=100%#%GG", "plot.jpg#100%", "plot.jpg"),
    ("?seed=%GG#100%", "plot.jpg?label=100%", "plot.jpg"),
    ("?seed=100%#%GG", "#%GG", None),
    ("#100%", "?v=%GG", None),
])
def test_base_discarded_fields_preserve_urljoin(tmp_path: Path, template: str, base: str, reference: str, name: str | None) -> None:
    """参数为根、三入口、base、引用与身份；返回无；标准 query/fragment 解析或本页复用不符时失败。"""
    markup = template.format(reference=reference) + f'<base href="{base}">'
    descriptors = asyncio.run(_discover(tmp_path, {"report.htm": markup.encode()}, metadata=True))
    assert [(item.name, item.source_url) for item in descriptors] == ([] if name is None else [(name, _ARCHIVE + quote(name, safe=""))])


@pytest.mark.parametrize("template", _IMAGE_AND_BASE_TEMPLATES)
@pytest.mark.parametrize("path", [
    "plot%.jpg", "plot%GG.jpg", "plot%2520.jpg", "plot%252F.jpg", "plot%2F.jpg",
    "plot%5C.jpg", "plot%FF.jpg", "plot%ED%A0%80.jpg", "%2e%2e/plot.jpg",
])
@pytest.mark.parametrize("upgrade", [False, True])
def test_discarded_fields_do_not_rescue_unsafe_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, template: str, path: str, upgrade: bool,
) -> None:
    """参数为根、批入口 guard、入口、不安全 path 与旧状态；返回无；typed/begin/旧版保留不符时失败。"""
    before = None
    if upgrade:
        _seed(tmp_path, {"report.htm": b"old source"}, _OLD_VERSION)
        before = _publication(tmp_path)
    monkeypatch.setattr(FsBatchingRepository, "begin_batch", _forbid_begin)
    html = template.format(reference=path + "?label=100%#%GG").encode()
    network = _Network(html)
    terminal = asyncio.run(_run(tmp_path, network))[-1]
    assert terminal.event_type is DownloadEventType.FILING_FAILED
    assert terminal.payload["reason_code"] == "html_image_reference_invalid"
    assert not any(url.endswith(".jpg") for _, url in network.requests)
    if before is None:
        assert FsSourceDocumentRepository(tmp_path).classify_source_integrity("TEST", _DOCUMENT, SourceKind.FILING).status is SourceIntegrityStatus.MISSING
    else:
        assert _publication(tmp_path) == before


@pytest.mark.parametrize("template", _IMAGE_AND_BASE_TEMPLATES)
@pytest.mark.parametrize("suffix", ["?label=bad&#10;value", "#bad&#129;value", "?bad=\\value"])
def test_discarded_fields_keep_raw_character_checks(tmp_path: Path, template: str, suffix: str) -> None:
    """参数为根、入口与原始控制字符/反斜杠字段；返回无；原始安全检查被放开时失败。"""
    with pytest.raises(SecHtmlImageDependencyError) as caught:
        asyncio.run(_discover(tmp_path, {"report.htm": template.format(reference="plot.jpg" + suffix).encode()}, metadata=True))
    assert caught.value.reason_code == "html_image_reference_invalid"


@pytest.mark.parametrize("template", _IMAGE_ENTRY_TEMPLATES)
@pytest.mark.parametrize("upgrade", [False, True])
def test_query_image_exact_transport_publication_and_rollback(tmp_path: Path, template: str, upgrade: bool) -> None:
    """参数为根、三入口与旧状态；返回无；exact GET/HEAD、仓储身份、完整指纹或 rollback/retry 不符时失败。"""
    name = "plot;1%.jpg"
    canonical = _ARCHIVE + quote(name, safe="")
    html = (template.format(reference="plot;1%25.jpg?label=100%#%GG")
            + '<base href="anchor.jpg?seed=%GG#100%"><img src="./plot%3B1%25.jpg#100%">').encode()
    before = None
    if upgrade:
        _seed(tmp_path, {"report.htm": b"old source"}, _OLD_VERSION)
        before = _publication(tmp_path)
    network = _Network(html, failure="404", failure_name=name)
    events = asyncio.run(_run(tmp_path, network))
    assert events[-1].event_type is DownloadEventType.FILING_FAILED
    assert events[-1].payload["reason_code"] == "file_download_failed"
    failures = [event for event in events if event.event_type is DownloadEventType.FILE_FAILED]
    assert len(failures) == 1 and failures[0].payload["name"] == name
    assert failures[0].payload["source_url"] == canonical
    expected_requests = ([("HEAD", canonical)] if upgrade else []) + [("GET", canonical)]
    assert [(method, url) for method, url in network.requests if url == canonical] == expected_requests
    if before is None:
        assert FsSourceDocumentRepository(tmp_path).classify_source_integrity("TEST", _DOCUMENT, SourceKind.FILING).status is SourceIntegrityStatus.MISSING
    else:
        assert _publication(tmp_path) == before
    network.failure = None
    network.requests.clear()
    assert asyncio.run(_run(tmp_path, network))[-1].payload["status"] == "downloaded"
    meta, revision, payloads = _publication(tmp_path)
    assert payloads == {"report.htm": html, name: _IMAGE_BYTES}
    assert meta["source_fingerprint"] == build_source_fingerprint([_descriptor(filename, metadata=upgrade) for filename in payloads])
    entries = meta["files"]
    assert isinstance(entries, list)
    image_entry = next(entry for entry in entries if isinstance(entry, dict) and entry["name"] == name)
    assert isinstance(image_entry, dict) and image_entry["source_url"] == canonical
    assert [(method, url) for method, url in network.requests if url == canonical] == expected_requests
    network.requests.clear()
    assert asyncio.run(_run(tmp_path, network))[-1].payload["status"] == "skipped"
    assert not network.requests and _publication(tmp_path) == (meta, revision, payloads)
