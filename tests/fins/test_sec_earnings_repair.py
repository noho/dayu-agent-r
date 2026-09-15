"""以原始公告和封面字节验证分类 owner、真实下载器及公开 CLI 缓存补源。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest

from dayu.cli.main import main
from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import ProcessedCreateRequest
from dayu.fins.domain.enums import SourceKind
from dayu.fins.downloaders import sec_downloader
from dayu.fins.downloaders.sec_downloader import (
    RemoteFileDescriptor,
    SecDownloadCancelledError,
    SecDownloader,
    build_source_fingerprint,
)
from dayu.fins.pipelines import sec_6k_rules, sec_pipeline
from dayu.fins.storage import (
    FsBatchingRepository,
    FsDocumentBlobRepository,
    FsProcessedDocumentRepository,
    FsSourceDocumentRepository,
    SourceIntegrityStatus,
)
from dayu.fins.storage._fs_repository_factory import build_fs_repository_set
from dayu.fins.storage.local_file_store import LocalFileStore

_FIXTURES = Path(__file__).parent / "fixtures/sec_earnings_repair_v1"


@dataclass(frozen=True)
class _Filing:
    """隔离测试的披露身份与原始文件选择参数。"""

    ticker: str
    cik: str
    accession: str
    day: str
    form: str
    cover: str
    exhibit: str

    @property
    def document_id(self) -> str:
        """无参数；返回稳定 accession 文档 ID；无异常。"""
        return f"fil_{self.accession}"

    @property
    def archive(self) -> str:
        """无参数；返回同披露目录 URL；无异常。"""
        return f"https://www.sec.gov/Archives/edgar/data/{self.cik}/{self.accession.replace('-', '')}/"


_ATAT = (
    _Filing(
        "ATAT", "1853717", "0001104659-24-120329", "2024-11-19", "6-K", "tm2428837d1_6k.htm", "tm2428837d1_ex99-1.htm"
    ),
    _Filing(
        "ATAT", "1853717", "0001104659-25-027458", "2025-03-25", "6-K", "tm2510227d1_6k.htm", "tm2510227d1_ex99-1.htm"
    ),
)
_EIGHT_K = (
    _Filing("MSFT", "789019", "0000950170-25-100226", "2025-07-30", "8-K", "msft-20250730.htm", "msft-ex99_1.htm"),
    _Filing(
        "META",
        "1326801",
        "0001326801-24-000010",
        "2024-02-01",
        "8-K",
        "meta-20240201.htm",
        "meta-12312023xexhibit991.htm",
    ),
    _Filing(
        "META",
        "1326801",
        "0001326801-25-000014",
        "2025-01-29",
        "8-K",
        "meta-20250129.htm",
        "meta-12312024xexhibit991.htm",
    ),
    _Filing(
        "META",
        "1326801",
        "0001628280-26-003832",
        "2026-01-28",
        "8-K",
        "meta-20260128.htm",
        "meta-12312025xexhibit991.htm",
    ),
)


def _raw(name: str) -> bytes:
    """参数为 Raw 文件名；经 storage 返回字节；读取异常透传。"""
    return LocalFileStore(_FIXTURES).get_object(f"data/raw/{name}").read()


def _payload(filing: _Filing, name: str) -> bytes:
    """参数为披露与文件名；返回真实回源 Raw；非法选择断言失败，读取异常透传。"""
    assert name in {filing.cover, filing.exhibit}
    return _raw(name)


@dataclass
class _SecNetwork:
    """仅替换 HTTP transport；生产 CLI、分类、文件选择和仓储均真实执行。"""

    requests: list[str] = field(default_factory=list)
    fail_exhibit: str | None = None
    clients: list[httpx.AsyncClient] = field(default_factory=list)

    def respond(self, request: httpx.Request) -> httpx.Response:
        """参数为 HTTP 请求；返回隔离响应；未声明的 URL 立即断言失败。"""
        url = str(request.url)
        self.requests.append(url)
        filings = (*_ATAT, *_EIGHT_K)
        if url == sec_downloader.SEC_TICKER_MAP_URL:
            return httpx.Response(
                200,
                json={
                    str(i): {"ticker": f.ticker, "cik_str": int(f.cik), "title": f.ticker}
                    for i, f in enumerate(filings)
                },
            )
        for cik in {f.cik for f in filings}:
            if url == sec_downloader.SEC_SUBMISSIONS_URL.format(cik10=cik.zfill(10)):
                rows = [f for f in filings if f.cik == cik]
                recent = {
                    "form": [f.form for f in rows],
                    "filingDate": [f.day for f in rows],
                    "reportDate": [f.day for f in rows],
                    "accessionNumber": [f.accession for f in rows],
                    "primaryDocument": [f.cover for f in rows],
                }
                return httpx.Response(
                    200,
                    json={
                        "name": rows[0].ticker,
                        "tickers": [rows[0].ticker],
                        "filings": {"recent": recent, "files": []},
                    },
                )
        for filing in filings:
            if not url.startswith(filing.archive):
                continue
            name = url.removeprefix(filing.archive)
            if name == "index.json":
                return httpx.Response(
                    200,
                    json={
                        "directory": {
                            "item": [
                                {"name": filing.cover},
                                {"name": filing.exhibit},
                                {"name": "agreement.htm"},
                                {"name": "chart.jpg"},
                            ]
                        }
                    },
                )
            if name == f"{filing.accession}-index-headers.html":
                return httpx.Response(
                    200,
                    text=f"<DOCUMENT>\n<TYPE>EX-99.1\n<FILENAME>{filing.exhibit}\n<DESCRIPTION>Earnings release\n</DOCUMENT>",
                )
            assert name in {filing.cover, filing.exhibit}, url
            if name == self.fail_exhibit:
                return httpx.Response(404, text="Missing test attachment")
            payload = _payload(filing, name)
            return httpx.Response(
                200, content=payload, headers={"Content-Type": "text/html", "ETag": hashlib.sha256(payload).hexdigest()}
            )
        raise AssertionError(f"Unexpected network request: {url}")

    def downloader(self, workspace_root: Path, user_agent: str | None = None) -> SecDownloader:
        """参数为临时 workspace 和身份；返回真实下载器；构造异常透传。"""
        client = httpx.AsyncClient(transport=httpx.MockTransport(self.respond))
        self.clients.append(client)
        return SecDownloader(
            workspace_root, client=client, user_agent=user_agent or "Dayu isolated test contact@example.com"
        )


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> Iterator[_SecNetwork]:
    """参数为 monkeypatch；返回 HTTP 替身；异常透传。"""
    network = _SecNetwork()
    monkeypatch.setattr(sec_pipeline, "SecDownloader", network.downloader)
    yield network
    for client in network.clients:
        asyncio.run(client.aclose())


def _cli(root: Path, filing: _Filing, *, overwrite: bool = False) -> int:
    """参数为临时目录、披露和覆盖开关；返回公开 CLI 退出码；入口异常透传。"""
    args = [
        "download",
        "--base",
        str(root),
        "--ticker",
        filing.ticker,
        "--forms",
        filing.form,
        "--start",
        filing.day,
        "--end",
        filing.day,
        "--log-file",
        str(root / "cli.log"),
    ]
    if overwrite:
        args.append("--overwrite")
    return main(args)


def _no_exhibits(items: Sequence[Mapping[str, JsonValue]]) -> list[str]:
    """参数为索引项；模拟历史版本未选取 8-K 附件，返回空列表；无异常。"""
    return []


def _no_current_signal(text: str) -> bool:
    """参数为公告文本；模拟历史强信号漏判，返回假；无异常。"""
    return False


def _snapshot(root: Path) -> dict[str, bytes]:
    """参数为临时目录；经 storage 返回受管文档文件快照，忽略锁；读取异常透传。"""
    store = LocalFileStore(root)
    return {
        str(path.relative_to(root)): store.get_object(str(path.relative_to(root))).read()
        for path in (root / "portfolio").rglob("*")
        if path.is_file() and not path.name.endswith(".lock")
    }


def _seed_processed(root: Path, filing: _Filing) -> FsProcessedDocumentRepository:
    """参数为隔离目录与已缓存披露；通过仓储生成历史处理结果并返回仓储；存储异常透传。"""
    repositories = build_fs_repository_set(workspace_root=root)
    batching = FsBatchingRepository(root, repository_set=repositories)
    processed = FsProcessedDocumentRepository(root, repository_set=repositories)
    batch = batching.begin_batch(filing.ticker)
    try:
        processed.create_processed(
            ProcessedCreateRequest(
                ticker=filing.ticker,
                document_id=filing.document_id,
                internal_document_id=filing.accession,
                source_kind=SourceKind.FILING.value,
                form_type=filing.form,
                meta={"reprocess_required": False},
                sections=[],
                tables=[],
            ),
            batch=batch,
        )
    except BaseException:
        batching.rollback_batch(batch)
        raise
    batching.commit_batch(batch)
    return processed


def _assert_registered(root: Path, filing: _Filing, names: set[str]) -> dict[str, JsonValue]:
    """参数为目录、披露与预期文件；校验完整性、真实 hash、清单和索引；返回 meta，断言失败透传。"""
    source = FsSourceDocumentRepository(root)
    blobs = FsDocumentBlobRepository(root)
    meta = dict(source.get_source_meta(filing.ticker, filing.document_id, SourceKind.FILING))
    assert (
        source.classify_source_integrity(filing.ticker, filing.document_id, SourceKind.FILING).status
        is SourceIntegrityStatus.COMPLETE
    )
    handle = source.get_source_handle(filing.ticker, filing.document_id, SourceKind.FILING)
    files = meta["files"]
    assert isinstance(files, list)
    assert {entry["name"] for entry in files if isinstance(entry, dict)} == names
    for entry in files:
        assert isinstance(entry, dict)
        name = entry["name"]
        assert isinstance(name, str)
        payload = blobs.read_file_bytes(handle, name)
        assert payload == _payload(filing, name)
        assert entry["sha256"] == hashlib.sha256(payload).hexdigest()
        assert entry["size"] == len(payload)
    # get/list 使用仓储的正式清单索引，完整性检查另核对 meta 与 manifest。
    assert filing.document_id in source.list_source_document_ids(filing.ticker, SourceKind.FILING)
    return meta


@pytest.mark.parametrize("filing", _EIGHT_K, ids=lambda f: f.accession)
def test_cli_repairs_complete_cover_and_then_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, network: _SecNetwork, filing: _Filing
) -> None:
    """参数为隔离夹具和四个真实封面；返回无；补源、hash、范围或幂等契约不符时失败。"""
    with monkeypatch.context() as old:
        old.setattr(sec_downloader, "pick_exhibit_files", _no_exhibits)
        for cached in _EIGHT_K:
            assert _cli(tmp_path, cached) == 0
    before = _assert_registered(tmp_path, filing, {filing.cover})
    processed = _seed_processed(tmp_path, filing)
    untouched = {f.document_id: _assert_registered(tmp_path, f, {f.cover}) for f in _EIGHT_K if f != filing}
    network.requests.clear()
    assert _cli(tmp_path, filing) == 0
    assert not any("/Archives/" in url for url in network.requests)
    assert _cli(tmp_path, filing, overwrite=True) == 0
    after = _assert_registered(tmp_path, filing, {filing.cover, filing.exhibit})
    assert after["document_id"] == before["document_id"]
    assert after["source_fingerprint"] != before["source_fingerprint"]
    assert processed.get_processed_meta(filing.ticker, filing.document_id)["reprocess_required"] is True
    assert after["source_fingerprint"] == build_source_fingerprint(
        [
            RemoteFileDescriptor(
                name=name, source_url=filing.archive + name, http_etag=None, http_last_modified=None, remote_size=None
            )
            for name in (filing.cover, filing.exhibit)
        ]
    )
    for f in _EIGHT_K:
        if f != filing:
            assert _assert_registered(tmp_path, f, {f.cover}) == untouched[f.document_id]
    snapshot = _snapshot(tmp_path)
    network.requests.clear()
    assert _cli(tmp_path, filing) == 0
    assert not any("/Archives/" in url for url in network.requests)
    assert _snapshot(tmp_path) == snapshot


@pytest.mark.parametrize("filing", _ATAT, ids=lambda f: f.accession)
def test_cli_retries_rejection_and_registers_actual_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, network: _SecNetwork, filing: _Filing
) -> None:
    """参数为隔离夹具和两份原始公告；返回无；重试必须重新分类且正式登记，否则失败。"""
    with monkeypatch.context() as old:
        old.setattr(sec_6k_rules, "_has_strong_current_results_disclosure_signal", _no_current_signal)
        assert _cli(tmp_path, filing) == 0
    source = FsSourceDocumentRepository(tmp_path)
    assert source.list_source_document_ids(filing.ticker, SourceKind.FILING) == []
    network.requests.clear()
    assert _cli(tmp_path, filing) == 0
    assert not any("/Archives/" in url for url in network.requests)
    assert _cli(tmp_path, filing, overwrite=True) == 0
    meta = _assert_registered(tmp_path, filing, {filing.cover, filing.exhibit})
    assert meta["primary_document"] == filing.exhibit
    snapshot = _snapshot(tmp_path)
    network.requests.clear()
    assert _cli(tmp_path, filing) == 0
    assert not any("/Archives/" in url for url in network.requests)
    assert _snapshot(tmp_path) == snapshot


def test_cli_failed_attachment_does_not_replace_complete_cover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, network: _SecNetwork
) -> None:
    """参数为隔离夹具；返回无；附件失败必须保留旧完整来源，不能发布半成品。"""
    filing = _EIGHT_K[0]
    with monkeypatch.context() as old:
        old.setattr(sec_downloader, "pick_exhibit_files", _no_exhibits)
        assert _cli(tmp_path, filing) == 0
    before = _assert_registered(tmp_path, filing, {filing.cover})
    network.fail_exhibit = filing.exhibit
    assert _cli(tmp_path, filing, overwrite=True) != 0
    assert _assert_registered(tmp_path, filing, {filing.cover}) == before
    network.fail_exhibit = None
    assert _cli(tmp_path, filing, overwrite=True) == 0
    _assert_registered(tmp_path, filing, {filing.cover, filing.exhibit})


def test_raw_manifest_and_actual_atat_classifier() -> None:
    """无参数；返回无；验证 Raw 完整性及生产 120 行输入，hash 或分类不符则失败。"""
    for manifest_name in ("sources.json", "downloaded_sources.json"):
        manifest = json.loads((_FIXTURES / "data/source_manifest" / manifest_name).read_text())
        for row in manifest["records"]:
            payload = _raw(Path(row["raw_path"]).name)
            assert len(payload) == row["size"]
            assert hashlib.sha256(payload).hexdigest() == row["sha256"]
    for filing in _ATAT:
        head = sec_6k_rules._extract_head_text(_raw(filing.exhibit), max_lines=120)
        normalized = " ".join(head.split())
        assert normalized.lower().index("reports ") < 4200
        assert sec_6k_rules._classify_6k_text(head) == "RESULTS_RELEASE"


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Example Reports First Quarter of 2024 Unaudited Financial Results", "RESULTS_RELEASE"),
        ("Example Reports Second Quarter 2024 Consolidated Financial Results", "RESULTS_RELEASE"),
        ("Example Reports Third Quarter of 2024 Unaudited Financial Results", "RESULTS_RELEASE"),
        ("Example Reports Fourth Quarter and Full Year 2024 Unaudited Financial Results", "RESULTS_RELEASE"),
        ("Example Reports Q4 2024 and Full Year 2024 Financial Results", "RESULTS_RELEASE"),
        ("Example Reports Full Year 2024 Unaudited Financial Results", "EXCLUDE_NON_QUARTERLY"),
        (
            "Example Will Report Third Quarter of 2024 Unaudited Financial Results on November 19",
            "EXCLUDE_NON_QUARTERLY",
        ),
        ("Example to Report Fourth Quarter and Full Year 2024 Unaudited Financial Results", "EXCLUDE_NON_QUARTERLY"),
        ("Example Announces Third Quarter Earnings Conference Call Schedule", "EXCLUDE_NON_QUARTERLY"),
        ("Example Reports Third Quarter 2024 Operating Update", "EXCLUDE_NON_QUARTERLY"),
        ("Example Reports September 2024 Monthly Operating Results", "EXCLUDE_NON_QUARTERLY"),
    ],
)
def test_current_earnings_title_is_not_operating_update(title: str, expected: str) -> None:
    """参数为非公司绑定标题和预期分类；返回无；当前业绩与预告、经营更新边界错误则失败。"""
    text = title + "\nOperational Highlights\nHotel openings and operational performance."
    assert sec_6k_rules._classify_6k_text(text) == expected


@dataclass
class _ListingNetwork:
    """附件索引、正文链接与取消检查点的 HTTP 响应夹具。"""

    requested: list[str] = field(default_factory=list)
    cancel_after: str | None = None
    cancelled: bool = False

    def respond(self, request: httpx.Request) -> httpx.Response:
        """参数为请求；返回边界测试响应；意外请求断言失败。"""
        name = request.url.path.rsplit("/", 1)[-1]
        self.requested.append(name)
        self.cancelled = name == self.cancel_after
        if request.method == "HEAD":
            return httpx.Response(200, headers={"ETag": '"test-etag"', "Content-Length": "123"})
        if name == "index.json":
            return httpx.Response(
                200,
                json={
                    "directory": {
                        "item": [
                            {"name": "ex99.htm"},
                            {"name": "agreement.htm"},
                            {"name": "ex99.jpg"},
                            {"name": "https://outside.test/ex99.htm"},
                            {"name": "../ex99.htm"},
                            {"name": "%2e%2e%2fex99.htm"},
                            {"name": "nested/ex99.htm"},
                        ]
                    }
                },
            )
        if name.endswith("-index-headers.html"):
            return httpx.Response(
                200,
                text="<DOCUMENT>\n<TYPE>EX-99.1\n<FILENAME>release.htm\n<DESCRIPTION>Quarterly earnings\n</DOCUMENT>\n<DOCUMENT>\n<TYPE>EX-10.1\n<FILENAME>agreement.htm\n</DOCUMENT>",
            )
        assert name == "cover.htm"
        return httpx.Response(
            200,
            text="""<html>
            <a href="ex99.htm">duplicate</a><a href="./ex99.htm?source=cover">duplicate</a>
            <a href="meta-exhibit991.htm">EX99 fallback</a><a href="generic-release.htm">6-K only</a>
            <a href="https://outside.test/ex99.htm">external</a><a href="//outside.test/ex99.htm">external</a>
            <a href="../other/ex99.htm">other filing</a><a href="/Archives/ex99.htm">absolute</a>
            <a href="%252e%252e%252fex99.htm">encoded parent</a><a href="nested/ex99.htm">nested</a>
            <a href="chart.jpg">image</a><a href="#ex99.htm">anchor</a></html>""",
        )

    def is_cancelled(self) -> bool:
        """无参数；返回注入取消状态；无异常。"""
        return self.cancelled


async def _list_files(
    root: Path, network: _ListingNetwork, form: str, include_exhibits: bool, metadata: bool = False
) -> list[RemoteFileDescriptor]:
    """参数为隔离目录、HTTP 夹具和选择开关；返回生产描述符；下载与取消异常透传。"""
    async with httpx.AsyncClient(transport=httpx.MockTransport(network.respond)) as client:
        downloader = SecDownloader(root, client=client, user_agent="Dayu tests contact@example.com")
        return await downloader.list_filing_files(
            cik="789019",
            accession_no_dash="000095017025100226",
            primary_document="cover.htm",
            form_type=form,
            include_xbrl=False,
            include_exhibits=include_exhibits,
            include_http_metadata=metadata,
            cancellation_checker=network.is_cancelled,
        )


@pytest.mark.parametrize(
    "form,enabled,names",
    [
        ("8-K", True, {"cover.htm", "ex99.htm", "meta-exhibit991.htm", "release.htm"}),
        ("8-K", False, {"cover.htm"}),
        ("10-K", True, {"cover.htm"}),
    ],
)
def test_eight_k_selection_boundaries(tmp_path: Path, form: str, enabled: bool, names: set[str]) -> None:
    """参数为选择矩阵；返回无；URL、附件类型、重复或公开选择开关不符时失败。"""
    network = _ListingNetwork()
    descriptors = asyncio.run(_list_files(tmp_path, network, form, enabled, metadata=True))
    assert {d.name for d in descriptors} == names
    assert len(descriptors) == len(names)
    assert all(d.http_etag == '"test-etag"' and d.remote_size == 123 for d in descriptors)
    if form == "8-K" and enabled:
        release = next(d for d in descriptors if d.name == "release.htm")
        assert release.sec_document_type == "EX-99.1"
        assert release.sec_description == "Quarterly earnings"
    else:
        assert not any(name.endswith("-index-headers.html") for name in network.requested)


@pytest.mark.parametrize("cancel_after", ["index.json", "0000950170-25-100226-index-headers.html", "cover.htm"])
def test_eight_k_discovery_cancellation(tmp_path: Path, cancel_after: str) -> None:
    """参数为三个真实请求边界；返回无；取消后继续列举或获取文件则失败。"""
    network = _ListingNetwork(cancel_after=cancel_after)
    with pytest.raises(SecDownloadCancelledError):
        asyncio.run(_list_files(tmp_path, network, "8-K", True))
    assert network.requested[-1] == cancel_after
