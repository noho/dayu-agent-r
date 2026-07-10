"""SecPipeline 下载流程测试。"""

from __future__ import annotations

from dayu.contracts.json_value import JsonValue

import json
import logging
from collections.abc import AsyncIterator, Callable, Mapping
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Optional, cast

import pytest

from dayu.fins.downloaders.sec_downloader import (
    BrowseEdgarFiling,
    DownloaderEvent,
    RemoteFileDescriptor,
    Sc13PartyRoles,
    SecDownloader,
    build_source_fingerprint,
)
from dayu.fins.domain.document_models import FileObjectMeta
from dayu.fins.ingestion_runtime import FinsSourceDownloadAdapterRequest
from dayu.fins.pipelines import sec_download_filing_workflow as _sec_download_filing_workflow
from dayu.fins.pipelines import sec_6k_primary_document_repair as _sec_6k_primary_repair
from dayu.fins.pipelines import sec_pipeline
from dayu.fins.domain.filing_semantics import (
    expand_sec_form_aliases,
    normalize_document_quality,
    normalize_financial_data_quality,
    normalize_fiscal_period,
    parse_sec_form_filter_value,
    parse_sec_form_type,
)
from dayu.fins.processors.registry import build_fins_processor_registry
from dayu.fins.pipelines.sec_download_event_mapping import DownloadFileResult
from dayu.fins.pipelines.sec_pipeline import (
    SEC_PIPELINE_DOWNLOAD_VERSION,
    SecPipeline as _SecPipeline,
)
from dayu.fins.pipelines.sec_sc13_filtering import SC13_FORMS as _SC13_FORMS, SC13_RETRY_MAX as _SC13_RETRY_MAX
from dayu.fins.storage import SourceDocumentRepositoryProtocol
from dayu.fins.ticker_normalization import normalize_ticker
from dayu.documents.processors.processor_registry import ProcessorRegistry


class _NeverCancelled:
    """测试用取消检查器。"""

    def __call__(self) -> bool:
        """始终返回未取消。"""

        return False


def _require_json_mapping(value: JsonValue) -> Mapping[str, JsonValue]:
    """断言 JSON 值是对象并返回只读 mapping。"""

    assert isinstance(value, Mapping)
    return value


def _require_json_list(value: JsonValue) -> list[JsonValue]:
    """断言 JSON 值是数组并返回 list。"""

    assert isinstance(value, list)
    return value


class StubDownloader:
    """用于测试的下载器桩。"""

    def __init__(
        self,
        submissions: dict[str, JsonValue],
        remote_files: list[RemoteFileDescriptor],
        download_results: list[DownloadFileResult],
        content_by_name: Optional[dict[str, bytes]] = None,
        browse_entries: Optional[list[BrowseEdgarFiling]] = None,
        primary_documents: Optional[dict[str, str]] = None,
        sc13_roles_by_accession: Optional[dict[str, Optional[tuple[str, str]]]] = None,
    ) -> None:
        """初始化下载器桩。

        Args:
            submissions: submissions JSON。
            remote_files: 远端文件描述列表。
            download_results: download_files 返回值。

        Returns:
            无。

        Raises:
            无。
        """

        self._submissions = submissions
        self._remote_files = remote_files
        self._download_results = download_results
        self._content_by_name = content_by_name or {}
        self._browse_entries = browse_entries or []
        self._primary_documents = primary_documents or {}
        self._sc13_roles_by_accession = sc13_roles_by_accession or {}
        self.download_files_called = False
        self.list_filing_files_call_count = 0
        self.fetch_file_calls: list[str] = []
        self.browse_calls: list[str] = []
        self.sc13_role_calls: list[str] = []

    def configure(self, user_agent: Optional[str], sleep_seconds: float, max_retries: int) -> None:
        """配置参数（占位）。

        Args:
            user_agent: User-Agent。
            sleep_seconds: 间隔秒数。
            max_retries: 重试次数。

        Returns:
            无。

        Raises:
            无。
        """

        return None

    def normalize_ticker(self, ticker: str) -> str:
        """标准化 ticker。

        Args:
            ticker: 股票代码。

        Returns:
            标准化 ticker。

        Raises:
            ValueError: ticker 为空时抛出。
        """

        normalized = ticker.strip().upper()
        if not normalized:
            raise ValueError("ticker 不能为空")
        return normalized

    def resolve_company(
        self,
        ticker: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> tuple[str, str, str]:
        """返回固定公司信息。

        Args:
            ticker: 股票代码。
            cancellation_checker: 可选取消检查器。

        Returns:
            `(cik, company_name, cik10)`。

        Raises:
            无。
        """

        del ticker, cancellation_checker
        return ("320193", "Test Inc.", "0000320193")

    def fetch_submissions(
        self,
        cik10: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> dict[str, JsonValue]:
        """返回固定 submissions。

        Args:
            cik10: 10 位 CIK。
            cancellation_checker: 可选取消检查器。

        Returns:
            submissions JSON。

        Raises:
            无。
        """

        del cik10, cancellation_checker
        return self._submissions

    def list_filing_files(
        self,
        cik: str,
        accession_no_dash: str,
        primary_document: str,
        form_type: str,
        include_xbrl: bool = True,
        include_exhibits: bool = True,
        include_http_metadata: bool = True,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> list[RemoteFileDescriptor]:
        """返回固定远端文件列表。

        Args:
            cik: CIK。
            accession_no_dash: accession。
            primary_document: primary 文件名。
            form_type: form。
            include_xbrl: 是否含 XBRL。
            include_exhibits: 是否含 exhibits。
            include_http_metadata: 是否拉取 HTTP 元数据。
            cancellation_checker: 可选取消检查器。

        Returns:
            远端文件描述列表。

        Raises:
            无。
        """

        self.list_filing_files_call_count += 1
        del (
            cik,
            accession_no_dash,
            primary_document,
            form_type,
            include_xbrl,
            include_exhibits,
            include_http_metadata,
            cancellation_checker,
        )
        return self._remote_files

    def download_files(
        self,
        remote_files: list[RemoteFileDescriptor],
        overwrite: bool,
        store_file: Callable[[str, BinaryIO], FileObjectMeta],
        existing_files: Optional[dict[str, dict[str, JsonValue]]] = None,
        primary_document: Optional[str] = None,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> list[DownloadFileResult]:
        """模拟下载并返回文件元数据。

        Args:
            remote_files: 远端文件列表。
            overwrite: 是否覆盖。
            store_file: 文件存储回调。
            existing_files: 既有文件映射。
            primary_document: 主文档文件名。
            cancellation_checker: 可选取消检查器。

        Returns:
            下载结果列表。

        Raises:
            无。
        """

        self.download_files_called = True
        del remote_files, overwrite, existing_files, primary_document, cancellation_checker
        results: list[DownloadFileResult] = []
        for item in self._download_results:
            name = str(item.get("name", ""))
            payload = self._content_by_name.get(name, f"dummy:{name}".encode("utf-8"))
            if item.get("status") == "downloaded":
                file_meta = store_file(name, BytesIO(payload))
                enriched = dict(item)
                enriched["file_meta"] = file_meta
                results.append(enriched)
            else:
                results.append(item)
        return results

    def fetch_file_bytes(
        self,
        url: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> bytes:
        """模拟预下载文件内容。

        Args:
            url: 文件 URL。
            cancellation_checker: 可选取消检查器。

        Returns:
            文件内容字节。

        Raises:
            无。
        """

        del cancellation_checker
        self.fetch_file_calls.append(url)
        filename = url.rsplit("/", 1)[-1]
        return self._content_by_name.get(filename, f"prefetch:{filename}".encode("utf-8"))

    def fetch_browse_edgar_filenum(
        self,
        filenum: str,
        count: int = 100,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> list[BrowseEdgarFiling]:
        """模拟 browse-edgar 拉取。

        Args:
            filenum: filenum。
            count: 拉取条数上限。
            cancellation_checker: 可选取消检查器。

        Returns:
            filings 列表。

        Raises:
            无。
        """

        del count, cancellation_checker
        self.browse_calls.append(filenum)
        return self._browse_entries


    def resolve_primary_document(
        self,
        cik: str,
        accession_no_dash: str,
        form_type: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> str:
        """模拟解析 primary_document。

        Args:
            cik: CIK。
            accession_no_dash: accession。
            form_type: form。

        Returns:
            文件名。

        Raises:
            无。
        """

        del cancellation_checker
        key = f"{cik}:{accession_no_dash}:{form_type}"
        return self._primary_documents.get(key, "primary.htm")

    def fetch_sc13_party_roles(
        self,
        archive_cik: str,
        accession_number: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> Optional[Sc13PartyRoles]:
        """模拟解析 SC13 方向角色。

        Args:
            archive_cik: archive CIK。
            accession_number: accession。

        Returns:
            方向角色对象或 `None`。

        Raises:
            无。
        """

        del archive_cik, cancellation_checker
        self.sc13_role_calls.append(accession_number)
        if accession_number in self._sc13_roles_by_accession:
            role_pair = self._sc13_roles_by_accession[accession_number]
            if role_pair is None:
                return None
            filed_by_cik, subject_cik = role_pair
            return Sc13PartyRoles(filed_by_cik=filed_by_cik, subject_cik=subject_cik)
        # 默认保留：模拟“别人持股当前 ticker(320193)”。
        return Sc13PartyRoles(filed_by_cik="999999", subject_cik="320193")


class StreamStubDownloader(StubDownloader):
    """带流式文件事件的下载器桩。"""

    async def download_files_stream(
        self,
        remote_files: list[RemoteFileDescriptor],
        overwrite: bool,
        store_file: Callable[[str, BinaryIO], FileObjectMeta],
        existing_files: Optional[dict[str, dict[str, JsonValue]]] = None,
        primary_document: Optional[str] = None,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> AsyncIterator[DownloaderEvent]:
        """模拟流式下载并在每个文件结果前产出 started 事件。

        Args:
            remote_files: 远端文件列表。
            overwrite: 是否覆盖。
            store_file: 文件存储回调。
            existing_files: 既有文件映射。
            primary_document: 主文档文件名。
            cancellation_checker: 可选取消检查器。

        Yields:
            文件 started 事件与终态文件事件。

        Raises:
            无。
        """

        self.download_files_called = True
        del remote_files, overwrite, existing_files, primary_document, cancellation_checker
        for item in self._download_results:
            name = str(item.get("name", ""))
            source_url = str(item.get("source_url", ""))
            http_etag = str(item.get("http_etag", "")) or None
            http_last_modified = str(item.get("http_last_modified", "")) or None
            yield DownloaderEvent(
                event_type="file_download_started",
                name=name,
                source_url=source_url,
                http_etag=http_etag,
                http_last_modified=http_last_modified,
                http_status=200,
            )
            if item.get("status") == "downloaded":
                payload = self._content_by_name.get(name, f"dummy:{name}".encode("utf-8"))
                file_meta = store_file(name, BytesIO(payload))
                yield DownloaderEvent(
                    event_type="file_downloaded",
                    name=name,
                    source_url=source_url,
                    http_etag=http_etag,
                    http_last_modified=http_last_modified,
                    http_status=200,
                    file_meta=file_meta,
                )
                continue
            yield DownloaderEvent(
                event_type="file_failed",
                name=name,
                source_url=source_url,
                http_etag=http_etag,
                http_last_modified=http_last_modified,
                http_status=500,
                reason_code=str(item.get("reason_code", "download_error")),
                reason_message=str(item.get("reason_message", "download failed")),
                error=str(item.get("error", "download failed")),
            )


class RebuildOnlyDownloader:
    """仅用于重建模式测试的下载器桩。"""

    def __init__(self) -> None:
        """初始化调用计数。

        Args:
            无。

        Returns:
            无。

        Raises:
            无。
        """

        self.configure_called = False
        self.network_called = False

    def configure(self, user_agent: Optional[str], sleep_seconds: float, max_retries: int) -> None:
        """记录配置调用。

        Args:
            user_agent: User-Agent。
            sleep_seconds: 休眠秒数。
            max_retries: 重试次数。

        Returns:
            无。

        Raises:
            无。
        """

        del user_agent, sleep_seconds, max_retries
        self.configure_called = True

    def normalize_ticker(self, ticker: str) -> str:
        """标准化 ticker。

        Args:
            ticker: 股票代码。

        Returns:
            大写 ticker。

        Raises:
            ValueError: ticker 为空时抛出。
        """

        normalized = ticker.strip().upper()
        if not normalized:
            raise ValueError("ticker 不能为空")
        return normalized

    def resolve_company(
        self,
        ticker: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> tuple[str, str, str]:
        """重建模式不应触发远端公司解析。

        Args:
            ticker: 股票代码。
            cancellation_checker: 可选取消检查器。

        Returns:
            不返回；被调用时会抛出异常。

        Raises:
            AssertionError: 被调用时抛出。
        """

        del ticker, cancellation_checker
        self.network_called = True
        raise AssertionError("rebuild 模式不应调用 resolve_company")

    def fetch_submissions(
        self,
        cik10: str,
        cancellation_checker: Optional[Callable[[], bool]] = None,
    ) -> dict[str, JsonValue]:
        """重建模式不应触发 submissions 拉取。

        Args:
            cik10: 10 位 CIK。
            cancellation_checker: 可选取消检查器。

        Returns:
            不返回；被调用时会抛出异常。

        Raises:
            AssertionError: 被调用时抛出。
        """

        del cik10, cancellation_checker
        self.network_called = True
        raise AssertionError("rebuild 模式不应调用 fetch_submissions")


_TestDownloader = StubDownloader | RebuildOnlyDownloader | SecDownloader


def _as_sec_downloader(downloader: _TestDownloader) -> SecDownloader:
    """把测试 downloader 显式收窄到生产签名。"""

    return cast(SecDownloader, downloader)


def SecPipeline(
    *,
    workspace_root: Path,
    processor_registry: ProcessorRegistry,
    downloader: Optional[_TestDownloader] = None,
) -> sec_pipeline.SecPipeline:
    """构造测试用 SecPipeline，并在装配边界收窄 stub 类型。"""

    return _SecPipeline(
        workspace_root=workspace_root,
        processor_registry=processor_registry,
        downloader=None if downloader is None else _as_sec_downloader(downloader),
    )


def _build_submissions() -> dict[str, JsonValue]:
    """构建 submissions JSON。

    Args:
        无。

    Returns:
        submissions JSON。

    Raises:
        无。
    """

    return {
        "tickers": ["AAPL", "APC"],
        "filings": {
            "recent": {
                "form": ["10-K"],
                "filingDate": ["2025-02-01"],
                "reportDate": ["2024-12-31"],
                "accessionNumber": ["0000000000-25-000001"],
                "primaryDocument": ["sample-10k.htm"],
            },
            "files": [],
        }
    }


def _build_foreign_submissions() -> dict[str, JsonValue]:
    """构建 foreign issuer 的 submissions JSON。

    Args:
        无。

    Returns:
        submissions JSON。

    Raises:
        无。
    """

    return {
        "filings": {
            "recent": {
                "form": ["6-K"],
                "filingDate": ["2025-08-01"],
                "reportDate": ["2024-12-31"],
                "accessionNumber": ["0000000000-25-000101"],
                "primaryDocument": ["sample-6k.htm"],
            },
            "files": [],
        }
    }


def _make_descriptor(etag: str) -> RemoteFileDescriptor:
    """构建远端文件描述。

    Args:
        etag: ETag 值。

    Returns:
        `RemoteFileDescriptor`。

    Raises:
        无。
    """

    return RemoteFileDescriptor(
        name="sample-10k.htm",
        source_url="https://example.com/sample-10k.htm",
        http_etag=etag,
        http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
        remote_size=100,
        http_status=200,
    )


def test_sec_pipeline_download_writes_meta_and_manifest(tmp_path: Path) -> None:
    """验证下载成功后写 meta 与 manifest。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [_make_descriptor("etag-v1")]
    downloader = StreamStubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False)

    assert result["summary"]["downloaded"] == 1
    meta_path = tmp_path / "portfolio" / "AAPL" / "filings" / "fil_0000000000-25-000001" / "meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["files"][0]["uri"].endswith("sample-10k.htm")
    assert meta["fiscal_year"] == 2024
    assert meta["fiscal_period"] == "FY"
    assert meta["source_provider"] == "sec_edgar"
    manifest_path = tmp_path / "portfolio" / "AAPL" / "filings" / "filing_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["documents"][0]["document_id"] == "fil_0000000000-25-000001"
    company_meta_path = tmp_path / "portfolio" / "AAPL" / "meta.json"
    company_meta = json.loads(company_meta_path.read_text(encoding="utf-8"))
    assert company_meta["ticker"] == "AAPL"
    assert company_meta["market"] == "US"
    assert company_meta["ticker_aliases"] == ["AAPL", "APC"]


def test_sec_pipeline_download_merges_cli_aliases_with_sec_aliases(tmp_path: Path) -> None:
    """验证 download 会按顺序合并 SEC alias 与 CLI 传入 alias。"""

    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    pipeline.download(
        ticker="AAPL",
        overwrite=False,
        ticker_aliases=["AAPL", "AAPL.SW", "APC"],
    )

    company_meta_path = tmp_path / "portfolio" / "AAPL" / "meta.json"
    company_meta = json.loads(company_meta_path.read_text(encoding="utf-8"))
    assert company_meta["ticker_aliases"] == ["AAPL", "APC", "AAPL.SW"]


def test_sec_pipeline_rebuild_local_meta_manifest_without_redownload(tmp_path: Path) -> None:
    """验证 `download --rebuild` 基于本地文件重建 meta/manifest 且不触发远端下载。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    ticker = "AAPL"
    document_id = "fil_0000000000-25-000001"
    document_dir = tmp_path / "portfolio" / ticker / "filings" / document_id
    document_dir.mkdir(parents=True, exist_ok=True)
    (document_dir / "sample-10k.htm").write_text("<html>sample</html>", encoding="utf-8")

    meta_path = document_dir / "meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "document_id": document_id,
                "internal_document_id": "0000000000-25-000001",
                "accession_number": "0000000000-25-000001",
                "ingest_method": "download",
                "ticker": ticker,
                "company_id": "320193",
                "form_type": "10-K",
                "fiscal_year": 2024,
                "fiscal_period": "FY",
                "report_kind": None,
                "report_date": "2024-12-31",
                "filing_date": "2025-02-01",
                "first_ingested_at": "2025-02-02T00:00:00+00:00",
                "ingest_complete": True,
                "is_deleted": False,
                "deleted_at": None,
                "document_version": "v7",
                "source_fingerprint": "fingerprint_fixed",
                "amended": False,
                "download_version": "legacy_download_version",
                "legacy_field_to_remove": "legacy",
                "created_at": "2025-02-02T00:00:00+00:00",
                "updated_at": "2025-02-02T00:00:00+00:00",
                "files": [
                    {
                        "name": "sample-10k.htm",
                        "uri": f"local://{ticker}/filings/{document_id}/sample-10k.htm",
                        "etag": "etag-v1",
                        "last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
                        "size": 100,
                        "content_type": "text/html",
                        "sha256": "dummy_sha256",
                        "source_url": "https://example.com/sample-10k.htm",
                        "http_etag": "etag-v1",
                        "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
                        "ingested_at": "2025-02-02T00:00:00+00:00",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # 预置一个旧 manifest，验证重建后可被覆盖为最新字段集合。
    manifest_path = tmp_path / "portfolio" / ticker / "filings" / "filing_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "ticker": ticker,
                "updated_at": "2025-02-02T00:00:00+00:00",
                "documents": [
                    {
                        "document_id": document_id,
                        "internal_document_id": "legacy_internal",
                        "form_type": "10-Q",
                        "document_version": "v1",
                        "source_fingerprint": "legacy_fp",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    downloader = RebuildOnlyDownloader()
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    result = pipeline.download(ticker=ticker, rebuild=True)

    assert result["summary"]["downloaded"] == 1
    assert result["summary"]["failed"] == 0
    assert bool(result["filters"]["rebuild"]) is True
    assert downloader.network_called is False
    assert downloader.configure_called is False

    rebuilt_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert rebuilt_meta["document_version"] == "v7"
    assert rebuilt_meta["source_fingerprint"] == "fingerprint_fixed"
    assert rebuilt_meta["download_version"] == SEC_PIPELINE_DOWNLOAD_VERSION
    assert "legacy_field_to_remove" not in rebuilt_meta

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(manifest["documents"]) == 1
    assert manifest["documents"][0]["document_id"] == document_id
    assert manifest["documents"][0]["document_version"] == "v7"
    assert manifest["documents"][0]["form_type"] == "10-K"
    assert manifest["documents"][0]["ingest_method"] == "download"


def test_sec_pipeline_download_prefers_dei_fiscal_when_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证下载落盘优先使用 DEI fiscal 字段。

    Args:
        tmp_path: 临时目录。
        monkeypatch: pytest monkeypatch。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    from dayu.fins.pipelines import sec_fiscal_fields as _sec_fiscal_fields_mod

    monkeypatch.setattr(
        _sec_fiscal_fields_mod,
        "_extract_download_fiscal_from_xbrl",
        lambda **_kwargs: (2023, "FY"),
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    pipeline.download(ticker="AAPL", overwrite=False)

    meta_path = tmp_path / "portfolio" / "AAPL" / "filings" / "fil_0000000000-25-000001" / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["fiscal_year"] == 2023
    assert meta["fiscal_period"] == "FY"


def test_sec_pipeline_skip_when_meta_matches(tmp_path: Path) -> None:
    """验证 meta 指纹一致时跳过下载。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [_make_descriptor("etag-same")]
    fingerprint = build_source_fingerprint(remote_files)
    document_dir = tmp_path / "portfolio" / "AAPL" / "filings" / "fil_0000000000-25-000001"
    document_dir.mkdir(parents=True, exist_ok=True)
    meta_path = document_dir / "meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "document_version": "v1",
                "source_fingerprint": fingerprint,
                "download_version": SEC_PIPELINE_DOWNLOAD_VERSION,
                "ingest_complete": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False)

    assert result["summary"]["skipped"] == 1
    assert downloader.download_files_called is False
    # 快速预检跳过时不应调用 list_filing_files
    assert downloader.list_filing_files_call_count == 0
    assert result["filings"][0]["skip_reason"] == "already_downloaded_complete"
    assert result["filings"][0]["reason_code"] == "already_downloaded_complete"
    assert "完整下载结果" in str(result["filings"][0]["reason_message"])


def test_sec_pipeline_skip_with_etag_gzip_variant_without_re_download(tmp_path: Path) -> None:
    """验证 ETag `-gzip` 变体不应触发重复下载。"""

    remote_files = [_make_descriptor("etag-same-gzip")]
    document_dir = tmp_path / "portfolio" / "AAPL" / "filings" / "fil_0000000000-25-000001"
    document_dir.mkdir(parents=True, exist_ok=True)
    meta_path = document_dir / "meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "document_version": "v1",
                "source_fingerprint": "legacy-fp",
                "download_version": SEC_PIPELINE_DOWNLOAD_VERSION,
                "ingest_complete": True,
                "files": [
                    {
                        "name": "sample-10k.htm",
                        "uri": "local://AAPL/sample-10k.htm",
                        "etag": "blob-etag",
                        "last_modified": "2026-03-03T00:00:00+00:00",
                        "size": 100,
                        "http_etag": "\"etag-same\"",
                        "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-same-gzip",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False)

    assert result["summary"]["skipped"] == 1
    assert result["summary"]["downloaded"] == 0
    assert downloader.download_files_called is False
    assert result["filings"][0]["skip_reason"] == "already_downloaded_complete"
    assert result["filings"][0]["reason_code"] == "already_downloaded_complete"


def test_sec_pipeline_marks_filing_skipped_when_all_files_not_modified(tmp_path: Path) -> None:
    """验证文件级全 skipped 时 filing 级状态为 skipped 且不改写 meta。"""

    remote_files = [_make_descriptor("etag-same")]
    document_dir = tmp_path / "portfolio" / "AAPL" / "filings" / "fil_0000000000-25-000001"
    document_dir.mkdir(parents=True, exist_ok=True)
    meta_path = document_dir / "meta.json"
    original_meta = {
        "document_version": "v1",
        "source_fingerprint": "legacy-fp",
        "download_version": "legacy-download-version",
        "ingest_complete": True,
        "updated_at": "2026-03-03T00:00:00+00:00",
        "files": [
            {
                "name": "sample-10k.htm",
                "uri": "local://AAPL/sample-10k.htm",
                "etag": "blob-etag",
                "last_modified": "2026-03-03T00:00:00+00:00",
                "size": 100,
                "http_etag": "etag-same",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    }
    meta_path.write_text(
        json.dumps(original_meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    before_text = meta_path.read_text(encoding="utf-8")
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "skipped",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-same",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False)
    after_text = meta_path.read_text(encoding="utf-8")

    assert result["summary"]["skipped"] == 1
    assert result["summary"]["downloaded"] == 0
    assert before_text == after_text
    assert downloader.download_files_called is True
    assert result["filings"][0]["skip_reason"] == "not_modified"
    assert result["filings"][0]["reason_code"] == "not_modified"
    assert "未修改" in str(result["filings"][0]["reason_message"])


def test_sec_pipeline_failed_filing_does_not_write_meta(tmp_path: Path) -> None:
    """验证下载失败时不写 meta。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "failed",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False)

    assert result["summary"]["failed"] == 1
    meta_path = tmp_path / "portfolio" / "AAPL" / "filings" / "fil_0000000000-25-000001" / "meta.json"
    assert not meta_path.exists()
    assert result["filings"][0]["reason_code"] == "file_download_failed"
    assert result["filings"][0]["reason_message"] == "存在文件下载失败"


def test_sec_pipeline_remote_change_marks_reprocess(tmp_path: Path) -> None:
    """验证远端变更会重拉并标记 processed 需重处理。

    快速预检机制（_can_skip_fast）在 ingest_complete + 版本匹配时会跳过远端比较，
    因此需要 overwrite=True 才能检测到远端变更（设计取舍：避免每次下载都做大量 HEAD 请求）。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files_v1 = [_make_descriptor("etag-v1")]
    fingerprint_v1 = build_source_fingerprint(remote_files_v1)
    document_dir = tmp_path / "portfolio" / "AAPL" / "filings" / "fil_0000000000-25-000001"
    document_dir.mkdir(parents=True, exist_ok=True)
    meta_path = document_dir / "meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "document_version": "v1",
                "source_fingerprint": fingerprint_v1,
                "download_version": SEC_PIPELINE_DOWNLOAD_VERSION,
                "ingest_complete": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    processed_meta_path = (
        tmp_path / "portfolio" / "AAPL" / "processed" / "fil_0000000000-25-000001" / "tool_snapshot_meta.json"
    )
    processed_meta_path.parent.mkdir(parents=True, exist_ok=True)
    processed_meta_path.write_text(
        json.dumps({"reprocess_required": False}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    remote_files_v2 = [_make_descriptor("etag-v2")]
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files_v2,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-v2",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    # 非 overwrite 模式下，快速预检会直接跳过（不发远端请求）
    result_skip = pipeline.download(ticker="AAPL", overwrite=False)
    assert result_skip["summary"]["skipped"] == 1
    assert result_skip["summary"]["downloaded"] == 0
    # 快速预检跳过时不应调用 list_filing_files（避免 SEC HEAD 请求）
    assert downloader.list_filing_files_call_count == 0

    # overwrite=True 清空 filings 目录后重新下载，以空白 previous_meta 全量重建
    result = pipeline.download(ticker="AAPL", overwrite=True)

    assert result["summary"]["downloaded"] == 1
    updated_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    # previous_meta=None（filings 目录已清空）→ 版本从 v1 重新开始
    assert updated_meta["document_version"] == "v1"
    processed_meta = json.loads(processed_meta_path.read_text(encoding="utf-8"))
    # 清空重建时若 processed 快照存在，应标记 reprocess_required
    assert processed_meta["reprocess_required"] is True


def test_sec_pipeline_download_parses_year_month_date_inputs(tmp_path: Path) -> None:
    """验证下载入口支持 YYYY/ YYYY-MM/ YYYY-MM-DD 日期输入。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=_build_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(
        ticker="AAPL",
        start_date="2024",
        end_date="2025-02",
        overwrite=False,
    )

    start_dates = _require_json_mapping(result["filters"]["start_dates"])
    assert start_dates["10-K"] == "2024-01-01"
    assert start_dates["10-Q"] == "2024-01-01"
    assert result["filters"]["end_date"] == "2025-02-28"


def test_sec_pipeline_download_resolves_foreign_issuer_from_submissions(tmp_path: Path) -> None:
    """验证根据 submissions 自动识别 foreign issuer 并写入 company meta。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [
        RemoteFileDescriptor(
            name="sample-6k.htm",
            source_url="https://example.com/sample-6k.htm",
            http_etag="etag-v1",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
            sec_document_type="EX-99.1",
        )
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-6k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-6k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
        content_by_name={
            "sample-6k.htm": b"Financial Results and Business Updates\\n",
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="TCOM", overwrite=False)

    assert result["summary"]["downloaded"] == 1
    forms = _require_json_list(result["filters"]["forms"])
    assert "6-K" in forms
    assert "20-F" in forms
    company_meta_path = tmp_path / "portfolio" / "TCOM" / "meta.json"
    company_meta = json.loads(company_meta_path.read_text(encoding="utf-8"))
    assert company_meta["ticker"] == "TCOM"
    assert company_meta["market"] == "US"


def test_sec_pipeline_filters_6k_excluded(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """验证 6-K 命中排除规则时跳过落盘。

    Args:
        tmp_path: 临时目录。
        caplog: 日志捕获夹具。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [
        RemoteFileDescriptor(
            name="sample-6k.htm",
            source_url="https://example.com/sample-6k.htm",
            http_etag="etag-6k",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
        ),
        RemoteFileDescriptor(
            name="d123dex991.htm",
            source_url="https://example.com/d123dex991.htm",
            http_etag="etag-exhibit",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=10,
            http_status=200,
        ),
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-6k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-6k.htm",
                "http_etag": "etag-6k",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
            {
                "name": "d123dex991.htm",
                "status": "downloaded",
                "source_url": "https://example.com/d123dex991.htm",
                "http_etag": "etag-exhibit",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
        ],
        content_by_name={
            # 分类信号源改为封面文档，此处模拟封面含非季报描述
            "sample-6k.htm": b"FORM 6-K\nEXHIBIT INDEX\nExhibit 99.1 - ANNUAL GENERAL MEETING Announcement\n",
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    caplog.set_level(logging.INFO, logger="dayu.fins.FINS.SEC_PIPELINE")

    result = pipeline.download(ticker="TCOM", overwrite=False)

    assert result["summary"]["skipped"] == 0
    assert result["summary"]["rejected"] == 1
    assert (
        "美股下载完成: ticker=TCOM total=1 downloaded=0 skipped=0 rejected=1 failed=0"
        in caplog.text
    )
    assert downloader.download_files_called is True
    meta_path = tmp_path / "portfolio" / "TCOM" / "filings" / "fil_0000000000-25-000101" / "meta.json"
    assert not meta_path.exists()
    rejected_meta_path = (
        tmp_path
        / "portfolio"
        / "TCOM"
        / "filings"
        / ".rejections"
        / "fil_0000000000-25-000101"
        / "meta.json"
    )
    assert rejected_meta_path.exists()
    rejected_meta = json.loads(rejected_meta_path.read_text(encoding="utf-8"))
    assert rejected_meta["rejection_reason"] == "6k_filtered"
    assert rejected_meta["rejection_category"] == "EXCLUDE_NON_QUARTERLY"


def test_sec_download_adapter_counts_6k_filtered_as_rejected_in_persisted_summary(tmp_path: Path) -> None:
    """验证 SEC adapter persisted summary 会统计 6-K filtered rejected artifact。"""

    remote_files = [
        RemoteFileDescriptor(
            name="sample-6k.htm",
            source_url="https://example.com/sample-6k.htm",
            http_etag="etag-6k",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
        ),
        RemoteFileDescriptor(
            name="d123dex991.htm",
            source_url="https://example.com/d123dex991.htm",
            http_etag="etag-exhibit",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=10,
            http_status=200,
        ),
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-6k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-6k.htm",
                "http_etag": "etag-6k",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
            {
                "name": "d123dex991.htm",
                "status": "downloaded",
                "source_url": "https://example.com/d123dex991.htm",
                "http_etag": "etag-exhibit",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
        ],
        content_by_name={
            "sample-6k.htm": b"FORM 6-K\nEXHIBIT INDEX\nExhibit 99.1 - ANNUAL GENERAL MEETING Announcement\n",
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    adapter = sec_pipeline.SecDownloadAdapter(pipeline=pipeline)

    result = adapter.download(
        FinsSourceDownloadAdapterRequest(
            normalized_ticker=normalize_ticker("TCOM"),
            source="sec",
            form_types=(),
            filed_after=None,
            filed_before=None,
            overwrite_existing=False,
            rebuild_processed=False,
            cancellation_checker=_NeverCancelled(),
        )
    )

    summary = result.persisted_summary
    assert summary is not None
    assert summary.rejected_count == 1
    assert summary.skipped_count == 0
    assert summary.downloaded_count == 0


def test_sec_download_adapter_summary_classifies_skipped_and_rejected_exclusively() -> None:
    """SEC adapter summary 应互斥统计真实跳过与 rejected filing。"""

    result: sec_pipeline.SecPipelineDownloadResult = {
        "pipeline": "sec_download",
        "action": "download",
        "status": "ok",
        "ticker": "ATAT",
        "market_profile": {},
        "filters": {},
        "warnings": [],
        "filings": [
            {
                "document_id": "fil-downloaded",
                "status": "downloaded",
            },
            {
                "document_id": "fil-already-complete",
                "status": "skipped",
                "skip_reason": "already_downloaded_complete",
                "reason_code": "already_downloaded_complete",
            },
            {
                "document_id": "fil-filtered-6k",
                "status": "skipped",
                "skip_reason": "6k_filtered",
                "reason_code": "6k_filtered",
            },
            {
                "document_id": "fil-failed",
                "status": "failed",
            },
            {
                "document_id": "fil-unknown-status",
                "status": "provider_new_status",
            },
        ],
        "summary": {
            "total": 999,
            "downloaded": 1,
            "skipped": 2,
            "rejected": 1,
            "failed": 99,
            "elapsed_ms": 42,
            "reused_downloads": 0,
            "converted": 0,
        },
    }

    summary = sec_pipeline._summary_from_pipeline_result(result)

    assert summary.discovered_count == 5
    assert summary.downloaded_count == 1
    assert summary.skipped_count == 1
    assert summary.rejected_count == 1
    assert summary.failed_count == 2
    assert summary.discovered_count == (
        summary.downloaded_count
        + summary.skipped_count
        + summary.rejected_count
        + summary.failed_count
    )
    assert (
        summary.discovered_count
        == summary.downloaded_count
        + summary.skipped_count
        + summary.rejected_count
        + summary.failed_count
    )


def test_sec_pipeline_keeps_6k_results_release(tmp_path: Path) -> None:
    """验证 6-K 命中结果发布规则时保留落盘。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [
        RemoteFileDescriptor(
            name="sample-6k.htm",
            source_url="https://example.com/sample-6k.htm",
            http_etag="etag-6k",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
        ),
        RemoteFileDescriptor(
            name="d123dex991.htm",
            source_url="https://example.com/d123dex991.htm",
            http_etag="etag-exhibit",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=10,
            http_status=200,
        ),
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-6k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-6k.htm",
                "http_etag": "etag-6k",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
            {
                "name": "d123dex991.htm",
                "status": "downloaded",
                "source_url": "https://example.com/d123dex991.htm",
                "http_etag": "etag-exhibit",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
        ],
        content_by_name={
            # 封面自身已被真源判成季度结果时，应保留封面作为 primary_document。
            "sample-6k.htm": (
                b"FORM 6-K\nFor the month of August 2025\n"
                b"EXHIBIT INDEX\n"
                b"Exhibit 99.1 - Press Release - TCOM Announces Fourth Quarter "
                b"and Full Year 2024 Unaudited Financial Results\n"
            ),
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="TCOM", overwrite=False)

    assert result["summary"]["downloaded"] == 1
    assert downloader.download_files_called is True
    meta_path = tmp_path / "portfolio" / "TCOM" / "filings" / "fil_0000000000-25-000101" / "meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["primary_document"] == "sample-6k.htm"


def test_sec_pipeline_keeps_primary_only_6k_results_release(tmp_path: Path) -> None:
    """验证没有 EX-99/XBRL 时，命中季度结果的 6-K 主文仍会落盘。"""

    remote_files = [
        RemoteFileDescriptor(
            name="sample-6k.htm",
            source_url="https://example.com/sample-6k.htm",
            http_etag="etag-6k",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
        )
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-6k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-6k.htm",
                "http_etag": "etag-6k",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
        content_by_name={
            "sample-6k.htm": (
                b"FORM 6-K\n"
                b"For the month of August 2025\n"
                b"TCOM Announces Second Quarter 2025 Unaudited Financial Results\n"
            ),
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="TCOM", overwrite=False)

    assert result["summary"]["downloaded"] == 1
    assert downloader.download_files_called is True
    meta_path = tmp_path / "portfolio" / "TCOM" / "filings" / "fil_0000000000-25-000101" / "meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["primary_document"] == "sample-6k.htm"


def test_sec_pipeline_promotes_positive_6k_exhibit_when_cover_is_excluded(tmp_path: Path) -> None:
    """验证 6-K 封面被排除时，会提升同 filing 的季度正文 exhibit。 

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    remote_files = [
        RemoteFileDescriptor(
            name="sample-6k.htm",
            source_url="https://example.com/sample-6k.htm",
            http_etag="etag-6k",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
        ),
        RemoteFileDescriptor(
            name="d123dex991.htm",
            source_url="https://example.com/d123dex991.htm",
            http_etag="etag-exhibit",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=10,
            http_status=200,
            sec_document_type="EX-99.1",
        ),
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-6k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-6k.htm",
                "http_etag": "etag-6k",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
            {
                "name": "d123dex991.htm",
                "status": "downloaded",
                "source_url": "https://example.com/d123dex991.htm",
                "http_etag": "etag-exhibit",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
        ],
        content_by_name={
            "sample-6k.htm": (
                b"FORM 6-K\nEXHIBIT INDEX\n"
                b"Exhibit 99.1 - ANNUAL GENERAL MEETING Announcement\n"
            ),
            "d123dex991.htm": (
                b"Press Release\n"
                b"TCOM Announces Fourth Quarter and Full Year 2024 Unaudited Financial Results\n"
            ),
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="TCOM", overwrite=False)

    assert result["summary"]["downloaded"] == 1
    assert downloader.download_files_called is True
    meta_path = tmp_path / "portfolio" / "TCOM" / "filings" / "fil_0000000000-25-000101" / "meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["primary_document"] == "d123dex991.htm"


def test_sec_pipeline_repairs_cover_primary_when_attachment_has_core_statements(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证下载完成后会修复 6-K cover primary 到可提取核心报表的附件。"""

    remote_files = [
        RemoteFileDescriptor(
            name="form6-k.htm",
            source_url="https://example.com/form6-k.htm",
            http_etag="etag-cover",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
        ),
        RemoteFileDescriptor(
            name="ex99-1.htm",
            source_url="https://example.com/ex99-1.htm",
            http_etag="etag-exhibit",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
            sec_document_type="EX-99.1",
        ),
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "form6-k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/form6-k.htm",
                "http_etag": "etag-cover",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
            {
                "name": "ex99-1.htm",
                "status": "downloaded",
                "source_url": "https://example.com/ex99-1.htm",
                "http_etag": "etag-exhibit",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
        ],
        content_by_name={
            "form6-k.htm": (
                b"FORM 6-K\n"
                b"Financial Results and Business Updates\n"
                b"Company reported strong quarterly performance\n"
            ),
            "ex99-1.htm": b"EX-99.1\nCompany quarterly results attachment\n",
        },
    )

    assessment_by_filename = {
        "form6-k.htm": _sec_6k_primary_repair.SixKPrimaryCandidateAssessment(
            filename="form6-k.htm",
            income_row_count=0,
            balance_sheet_row_count=0,
            filename_priority=3,
        ),
        "ex99-1.htm": _sec_6k_primary_repair.SixKPrimaryCandidateAssessment(
            filename="ex99-1.htm",
            income_row_count=22,
            balance_sheet_row_count=31,
            filename_priority=0,
        ),
    }

    def _fake_assess_active_6k_candidate(
        *,
        source_repository: SourceDocumentRepositoryProtocol,
        ticker: str,
        document_id: str,
        filename: str,
        primary_document: str,
    ) -> _sec_6k_primary_repair.SixKPrimaryCandidateAssessment:
        """返回固定候选评估结果。"""

        del source_repository, ticker, document_id, primary_document
        return assessment_by_filename[filename]

    monkeypatch.setattr(
        _sec_6k_primary_repair,
        "_assess_active_6k_candidate",
        _fake_assess_active_6k_candidate,
    )

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="ALVO", overwrite=False)

    assert result["summary"]["downloaded"] == 1
    meta_path = tmp_path / "portfolio" / "ALVO" / "filings" / "fil_0000000000-25-000101" / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["primary_document"] == "ex99-1.htm"


def test_sec_pipeline_keeps_provisional_primary_when_reconcile_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证 6-K reconcile 抛异常时会保留预筛选主文件并继续下载。"""

    remote_files = [
        RemoteFileDescriptor(
            name="sample-6k.htm",
            source_url="https://example.com/sample-6k.htm",
            http_etag="etag-6k",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=100,
            http_status=200,
        ),
        RemoteFileDescriptor(
            name="d123dex991.htm",
            source_url="https://example.com/d123dex991.htm",
            http_etag="etag-exhibit",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=10,
            http_status=200,
            sec_document_type="EX-99.1",
        ),
    ]
    downloader = StubDownloader(
        submissions=_build_foreign_submissions(),
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-6k.htm",
                "status": "downloaded",
                "source_url": "https://example.com/sample-6k.htm",
                "http_etag": "etag-6k",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
            {
                "name": "d123dex991.htm",
                "status": "downloaded",
                "source_url": "https://example.com/d123dex991.htm",
                "http_etag": "etag-exhibit",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            },
        ],
        content_by_name={
            "sample-6k.htm": (
                b"FORM 6-K\nEXHIBIT INDEX\n"
                b"Exhibit 99.1 - ANNUAL GENERAL MEETING Announcement\n"
            ),
            "d123dex991.htm": (
                b"Press Release\n"
                b"TCOM Announces Fourth Quarter and Full Year 2024 Unaudited Financial Results\n"
            ),
        },
    )

    def _raise_reconcile(
        *,
        source_repository: SourceDocumentRepositoryProtocol,
        ticker: str,
        document_id: str,
        mark_processed_reprocess_required: Callable[[str, str], None],
    ) -> None:
        """模拟 reconcile 内部异常。"""

        del source_repository, ticker, document_id, mark_processed_reprocess_required
        raise RuntimeError("boom")

    monkeypatch.setattr(
        _sec_download_filing_workflow,
        "reconcile_active_6k_primary_document",
        _raise_reconcile,
    )

    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="TCOM", overwrite=False)

    assert result["summary"]["downloaded"] == 1
    meta_path = tmp_path / "portfolio" / "TCOM" / "filings" / "fil_0000000000-25-000101" / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["primary_document"] == "d123dex991.htm"


def test_sec_form_domain_parser_accepts_supported_aliases() -> None:
    """验证 SEC form domain parser 接受当前支持的别名。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    assert parse_sec_form_type("10K") == "10-K"
    assert parse_sec_form_type("10-K/A") == "10-K/A"
    assert parse_sec_form_type("def 14a") == "DEF 14A"
    assert parse_sec_form_filter_value("SC13D/G") == "SC 13D/G"
    assert expand_sec_form_aliases(["SC13D/G"]) == ["SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"]
    assert parse_sec_form_type("SCHEDULE 13D") == "SC 13D"


def test_shared_domain_parsers_reject_invalid_values() -> None:
    """验证共享 domain parser 对非法业务值 fail closed。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    with pytest.raises(ValueError, match="form_type 不能为空"):
        parse_sec_form_type("")
    with pytest.raises(ValueError, match="form_type 不支持"):
        parse_sec_form_type("F-1")
    with pytest.raises(ValueError, match="fiscal_period 非法"):
        normalize_fiscal_period("Q5")
    with pytest.raises(ValueError, match="quality 非法"):
        normalize_document_quality("xbrl")
    with pytest.raises(ValueError, match="data_quality 非法"):
        normalize_financial_data_quality("raw")


def test_sec_pipeline_warns_missing_sc13(tmp_path: Path) -> None:
    """验证缺失 SC 13D/G 时输出提示。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    submissions = _build_submissions()
    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False)

    warnings = result.get("warnings") or []
    assert any("SC 13D/G" in item for item in warnings)


def test_sec_pipeline_sc13_direction_filters_gs_like_records(tmp_path: Path) -> None:
    """验证 GS-like 场景（ticker 持股别人）会被 SC13 方向过滤为 0 条。"""

    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["SC 13G", "SC 13D/A"],
                "filingDate": ["2025-08-10", "2025-08-11"],
                "reportDate": ["", ""],
                "accessionNumber": ["0000000000-25-000701", "0000000000-25-000702"],
                "primaryDocument": ["sc13g-1.htm", "sc13da-1.htm"],
                "fileNumber": ["005-10001", "005-10002"],
            },
            "files": [],
        }
    }
    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
        sc13_roles_by_accession={
            "0000000000-25-000701": ("320193", "999999"),
            "0000000000-25-000702": ("320193", "888888"),
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="GS", form_type="SC13D/G", overwrite=False)

    assert result["summary"]["total"] == 0
    assert result["summary"]["downloaded"] == 0
    assert downloader.download_files_called is True
    assert (
        tmp_path
        / "portfolio"
        / "GS"
        / "filings"
        / ".rejections"
        / "fil_0000000000-25-000701"
        / "meta.json"
    ).exists()
    assert (
        tmp_path
        / "portfolio"
        / "GS"
        / "filings"
        / ".rejections"
        / "fil_0000000000-25-000702"
        / "meta.json"
    ).exists()


def test_sec_pipeline_sc13_direction_keeps_aapl_like_records(tmp_path: Path) -> None:
    """验证 AAPL-like 场景仅保留“别人持股 ticker”的 SC13。"""

    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["SC 13G", "SC 13D", "SC 13G/A"],
                "filingDate": ["2025-08-10", "2025-08-11", "2025-08-12"],
                "reportDate": ["", "", ""],
                "accessionNumber": [
                    "0000000000-25-000801",
                    "0000000000-25-000802",
                    "0000000000-25-000803",
                ],
                "primaryDocument": ["sc13g-1.htm", "sc13d-1.htm", "sc13ga-1.htm"],
                "fileNumber": ["005-20001", "005-20002", "005-20003"],
            },
            "files": [],
        }
    }
    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-10k.htm",
                "status": "downloaded",
                "path": "sample-10k.htm",
                "source_url": "https://example.com/sample-10k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
        sc13_roles_by_accession={
            "0000000000-25-000801": ("111111", "320193"),
            "0000000000-25-000802": ("320193", "999999"),
            "0000000000-25-000803": None,
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", form_type="SC13D/G", overwrite=False)

    assert result["summary"]["downloaded"] == 1
    kept_meta = tmp_path / "portfolio" / "AAPL" / "filings" / "fil_0000000000-25-000801" / "meta.json"
    filtered_meta = tmp_path / "portfolio" / "AAPL" / "filings" / "fil_0000000000-25-000802" / "meta.json"
    unknown_meta = tmp_path / "portfolio" / "AAPL" / "filings" / "fil_0000000000-25-000803" / "meta.json"
    assert kept_meta.exists()
    assert not filtered_meta.exists()
    assert not unknown_meta.exists()


def test_sec_pipeline_supplements_sc13_from_browse(tmp_path: Path) -> None:
    """验证通过 browse-edgar 补齐 SC 13D/G。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "filingDate": ["2025-08-01"],
                "reportDate": [""],
                "accessionNumber": ["0000000000-25-000010"],
                "primaryDocument": ["sample-8k.htm"],
                "fileNumber": ["005-12345"],
            },
            "files": [],
        }
    }
    browse_entries = [
        BrowseEdgarFiling(
            form_type="SCHEDULE 13G",
            filing_date="2025-08-10",
            accession_number="0000000000-25-000777",
            cik="1000",
            index_url="https://example.com/0000000000-25-000777-index.htm",
        )
    ]
    remote_files = [
        RemoteFileDescriptor(
            name="primary.htm",
            source_url="https://example.com/primary.htm",
            http_etag="etag-sc13",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=10,
            http_status=200,
        )
    ]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "primary.htm",
                "status": "downloaded",
                "source_url": "https://example.com/primary.htm",
                "http_etag": "etag-sc13",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
        browse_entries=browse_entries,
        primary_documents={
            "1000:000000000025000777:SC 13G": "primary.htm",
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", form_type="SC13D/G", overwrite=False)

    assert result["summary"]["downloaded"] == 1
    assert downloader.browse_calls == ["005-12345"]
    meta_path = tmp_path / "portfolio" / "AAPL" / "filings" / "fil_0000000000-25-000777" / "meta.json"
    assert meta_path.exists()


def test_sec_pipeline_sc13_keeps_latest_per_filer(tmp_path: Path) -> None:
    """验证同一申报主体（filenum）仅保留最新 SC 13。"""

    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "filingDate": ["2025-08-01"],
                "reportDate": [""],
                "accessionNumber": ["0000000000-25-000010"],
                "primaryDocument": ["sample-8k.htm"],
                "fileNumber": ["005-12345"],
            },
            "files": [],
        }
    }
    browse_entries = [
        BrowseEdgarFiling(
            form_type="SCHEDULE 13G",
            filing_date="2025-08-10",
            accession_number="0000000000-25-000777",
            cik="1000",
            index_url="https://example.com/0000000000-25-000777-index.htm",
        ),
        BrowseEdgarFiling(
            form_type="SCHEDULE 13G/A",
            filing_date="2025-09-01",
            accession_number="0000000000-25-000888",
            cik="1000",
            index_url="https://example.com/0000000000-25-000888-index.htm",
        ),
    ]
    remote_files = [
        RemoteFileDescriptor(
            name="primary.htm",
            source_url="https://example.com/primary.htm",
            http_etag="etag-sc13",
            http_last_modified="Mon, 01 Jan 2025 00:00:00 GMT",
            remote_size=10,
            http_status=200,
        )
    ]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "primary.htm",
                "status": "downloaded",
                "source_url": "https://example.com/primary.htm",
                "http_etag": "etag-sc13",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
        browse_entries=browse_entries,
        primary_documents={
            "1000:000000000025000777:SC 13G": "primary.htm",
            "1000:000000000025000888:SC 13G/A": "primary.htm",
        },
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )

    result = pipeline.download(ticker="AAPL", form_type="SC13D/G", overwrite=False)

    assert result["summary"]["downloaded"] == 1
    old_meta = tmp_path / "portfolio" / "AAPL" / "filings" / "fil_0000000000-25-000777" / "meta.json"
    latest_meta = tmp_path / "portfolio" / "AAPL" / "filings" / "fil_0000000000-25-000888" / "meta.json"
    assert not old_meta.exists()
    assert latest_meta.exists()


# ---------------------------------------------------------------------------
# SC 13 渐进式回溯测试
# ---------------------------------------------------------------------------


def test_sc13_constants() -> None:
    """验证 SC 13 渐进式回溯常量配置。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    assert _SC13_FORMS == frozenset({"SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A"})
    assert _SC13_RETRY_MAX == 2


def test_sc13_no_retry_when_found_in_initial_window(tmp_path: Path) -> None:
    """SC 13 在初始1年窗口内有结果时不触发重试。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    # SC 13G 在最近1年内
    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["SC 13G"],
                "filingDate": ["2025-08-01"],
                "reportDate": [""],
                "accessionNumber": ["0000000000-25-000100"],
                "primaryDocument": ["sc13g.htm"],
                "fileNumber": ["005-99999"],
            },
            "files": [],
        }
    }
    remote_files = [_make_descriptor("etag-sc13")]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "sc13g.htm",
                "status": "downloaded",
                "path": "sc13g.htm",
                "source_url": "https://example.com/sc13g.htm",
                "http_etag": "etag-sc13",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", form_type="SC13D/G", overwrite=False)

    # 找到了 SC 13G，无需重试 → browse_calls 不应被调用（submissions 无 005- filenum 除自身外）
    assert result["summary"]["downloaded"] == 1
    warnings = result.get("warnings") or []
    assert not any("SC 13D/G" in w for w in warnings)


def test_sc13_retry_expands_window_and_finds_filing(tmp_path: Path) -> None:
    """SC 13 初始窗口无结果，通过渐进式回溯在扩大窗口后找到 filing。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    # SC 13G 在2年前（超出初始1年窗口，但在第1次重试的2年窗口内）
    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["8-K", "SC 13G"],
                "filingDate": ["2025-08-01", "2024-01-15"],
                "reportDate": ["", ""],
                "accessionNumber": ["0000000000-25-000010", "0000000000-24-000050"],
                "primaryDocument": ["sample-8k.htm", "sc13g-old.htm"],
                "fileNumber": ["001-12345", "005-67890"],
            },
            "files": [],
        }
    }
    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "sc13g-old.htm",
                "status": "downloaded",
                "path": "sc13g-old.htm",
                "source_url": "https://example.com/sc13g-old.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2024 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", form_type="SC13D/G", overwrite=False)

    # 初始1年窗口找不到（2024-01-15 在1年+60天之外），重试后应找到
    assert result["summary"]["downloaded"] >= 1
    warnings = result.get("warnings") or []
    # 找到了 SC 13G，不应有缺失警告
    assert not any("SC 13D/G" in w for w in warnings)


def test_sc13_retry_warns_after_max_retries(tmp_path: Path) -> None:
    """SC 13 渐进式回溯达到最大重试次数仍无结果时发出警告。

    Args:
        tmp_path: 临时目录。

    Returns:
        无。

    Raises:
        AssertionError: 断言失败时抛出。
    """

    # 无任何 SC 13 filing
    submissions: dict[str, JsonValue] = {
        "filings": {
            "recent": {
                "form": ["8-K"],
                "filingDate": ["2025-08-01"],
                "reportDate": [""],
                "accessionNumber": ["0000000000-25-000010"],
                "primaryDocument": ["sample-8k.htm"],
                "fileNumber": ["001-12345"],
            },
            "files": [],
        }
    }
    remote_files = [_make_descriptor("etag-v1")]
    downloader = StubDownloader(
        submissions=submissions,
        remote_files=remote_files,
        download_results=[
            {
                "name": "sample-8k.htm",
                "status": "downloaded",
                "path": "sample-8k.htm",
                "source_url": "https://example.com/sample-8k.htm",
                "http_etag": "etag-v1",
                "http_last_modified": "Mon, 01 Jan 2025 00:00:00 GMT",
            }
        ],
    )
    pipeline = SecPipeline(
        workspace_root=tmp_path,
        downloader=downloader,
        processor_registry=build_fins_processor_registry(),
    )
    result = pipeline.download(ticker="AAPL", overwrite=False)

    # 最大重试后仍无 SC 13 → 应有缺失警告
    warnings = result.get("warnings") or []
    assert any("SC 13D/G" in w for w in warnings)
