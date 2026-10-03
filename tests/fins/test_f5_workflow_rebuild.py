"""F5 真实 Fs 下载 A+未知 B、日期共享 writer 和 rebuild 原资产保全；仅合成资产。"""

import asyncio
import io
import json
from dayu.cli.output import render_fins_direct_event
from dayu.fins.direct_events import FinsResultStatus
from dayu.service.fins_wait_adapter import FinsIngestionWaitPollAdapter
from dayu.host.wait_adapter import WaitPollReady
from dayu.host.api import ResolveWaitFailedOutcome, ResolveWaitCancelledOutcome
from tests.fins.test_fins_ingestion_runtime import _HoldingExecutor, _build_ingestion_runtime, _NeverCancelledToken
from tests.service.test_fins_wait_adapter import _wait_snapshot, _reject_integrity_wait_job_read
from dayu.fins.tools.download_tools import DOWNLOAD_TOOL_NAME
from dayu.fins.download_contract import build_fins_download_request
from dayu.fins.direct_events import FinsEvent, FinsEventType, FinsOperationKind
from datetime import datetime, timezone

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins.domain.document_models import DocumentQuery, ProcessedCreateRequest
from dayu.fins.domain.enums import SourceKind
from dayu.fins.download_contract import FinsDownloadSource
from dayu.fins.pipelines.cn_download_models import (
    CnCompanyProfile, CnReportDiscoveryResult, CnReportQuery, HkexnewsRawAnnouncement,
)
from dayu.fins.pipelines.cn_form_utils import PeriodDownloadWindow, build_cn_filing_ids
from dayu.fins.pipelines.cn_pipeline import CnDownloadAdapter
from dayu.fins.pipelines.cn_report_selection import local_hk_annual_ends, select_hkexnews_report_candidates
from dayu.fins.pipelines.hk_download_rebuild import rebuild_hk_periods
from dayu.fins.storage import SourceIntegrityStatus, SourceIntegrityReason, SourceDocumentRepositoryProtocol
from tests.fins.test_cn_report_selection import _hk_raw, _head_meta
from tests.fins.test_cn_download_workflow import _FakeConverter, _FakeDiscoveryClient, _build_pipeline, _candidate
from tests.fins.test_cn_download_runtime import _cn_projection_request


class _RawDiscovery(_FakeDiscoveryClient):
    """仅运输明确标记的合成 raw，使用真实 selector 决定财期与未知。"""
    def __init__(self, temp_dir: Path, raw: tuple[HkexnewsRawAnnouncement, ...]) -> None:
        """参数为隔离目录与合成 raw；返回无；异常无。"""
        super().__init__(temp_dir=temp_dir, candidates=())
        self.raw = raw
    def list_report_candidates(self, query: CnReportQuery, profile: CnCompanyProfile, *, local_annual_ends: tuple[date, ...], cancellation_checkpoint: Callable[[], None] | None = None) -> CnReportDiscoveryResult:
        """参数为 mandatory discovery 输入；返回真实 selection；取消与来源冲突原样抛出。"""
        del profile
        self.queries.append(query)
        if cancellation_checkpoint is not None:
            cancellation_checkpoint()
        return select_hkexnews_report_candidates(query=query, announcements=self.raw, local_annual_ends=local_annual_ends, read_head_meta=_head_meta)


def _tree(root: Path) -> dict[str, bytes]:
    """参数为隔离目录；返回逐文件字节映射；原 I/O 异常透传。"""
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _manifest_row(root: Path, document_id: str, *, processed: bool) -> dict[str, JsonValue]:
    """参数为真实测试根、文档 ID 和清单类型；返回唯一持久索引行；I/O/结构错误或缺行断言失败。"""
    name = "manifest.json" if processed else "filing_manifest.json"
    rows: list[dict[str, JsonValue]] = []
    for path in (root / "portfolio").rglob(name):
        value: JsonValue = json.loads(path.read_text())
        assert isinstance(value, dict)
        documents = value["documents"]
        assert isinstance(documents, list)
        for row in documents:
            if isinstance(row, dict) and row["document_id"] == document_id:
                rows.append(row)
    assert len(rows) == 1
    return rows[0]


def test_real_workflow_continues_a_without_download_or_identity_for_b(tmp_path: Path) -> None:
    """参数为真实 Fs 根；返回无；未知触发 PDF/身份/错误 missing 或 A 未发布时断言失败。"""
    raw = (
        _hk_raw(document_id="A", title="截至2025年9月30日止第三季度業績", category_text="季度業績", filing_date="2025-11-13"),
        _hk_raw(document_id="B", title="截至2025年8月31日止三個月業績", category_text="季度業績", filing_date="2025-11-13"),
    )
    discovery = _RawDiscovery(tmp_path, raw)
    converter = _FakeConverter()
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, hk_discovery=discovery, converter=converter)
    result = pipeline.download(ticker="0700", form_type="Q3", start_date="2025", end_date="2025", start_is_explicit=True)
    rows = result["filings"]
    unknown = result["uncertain_reports"]
    assert isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict)
    assert rows[0]["status"] == "downloaded"
    assert isinstance(unknown, list) and len(unknown) == 1 and isinstance(unknown[0], dict)
    assert unknown[0]["source_id"] == "B" and unknown[0]["existing_document_id"] is None
    assert result["missing_periods"] == []
    assert discovery.download_calls == converter.calls == 1
    ids = pipeline.source_repository.list_source_document_ids("0700", SourceKind.FILING)
    assert ids == [rows[0]["document_id"]]
    assert not any("B" == pipeline.source_repository.get_source_meta("0700", n, SourceKind.FILING)["source_id"] for n in ids)


def test_local_complete_annual_is_shared_with_remote_and_rebuild(tmp_path: Path) -> None:
    """参数为真实 Fs 根；返回无；本地可信年度遗漏、删除/损坏/跨公司被信任或等证据漂移时断言失败。"""
    annual = replace(_candidate(source_id="annual", fiscal_year=2024, fiscal_period="FY", provider="hkexnews"), title="ANNUAL RESULTS FOR YEAR ENDED 31 DECEMBER 2024", category_text="Annual Results", language="en")
    seed = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(annual,))
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=seed, hk_discovery=seed, converter=_FakeConverter())
    pipeline.download(ticker="0700", form_type="FY", start_date="2024", end_date="2026", start_is_explicit=True)
    entries = pipeline.source_repository.read_source_meta_integrity_view("0700", SourceKind.FILING, batch=None)
    assert tuple(local_hk_annual_ends(entries).values()) == (date(2024, 12, 31),)
    entry = entries[0]
    for meta in ({**entry.source_meta, "is_deleted": True}, {**entry.source_meta, "company_id": "HKEX:foreign"}, {**entry.source_meta, "ticker": "0005"}):
        assert local_hk_annual_ends((replace(entry, source_meta=meta),)) == {}
    assert local_hk_annual_ends((replace(entry, integrity=replace(entry.integrity, status=SourceIntegrityStatus.UNSAFE, revision=None, reasons=(SourceIntegrityReason.SOURCE_MANIFEST_UNTRUSTED,))),)) == {}
    raw = (_hk_raw(document_id="quarter", title="截至2025年9月30日止三個月業績", category_text="季度業績", filing_date="2025-11-13"),)
    discovery = _RawDiscovery(tmp_path, raw)
    follow = _build_pipeline(tmp_path=tmp_path, discovery=discovery, hk_discovery=discovery, converter=_FakeConverter())
    result = follow.download(ticker="0700", form_type="Q3", start_date="2025-11-13", end_date="2025-11-13", start_is_explicit=True)
    rows = result["filings"]
    assert isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict)
    assert rows[0]["form_type"] == "Q3" and result["uncertain_reports"] == []
    rebuilt, unknown, cancelled = rebuild_hk_periods(follow, "0700", (PeriodDownloadWindow(fiscal_period="Q3", start_date="2025-11-13", end_date="2025-11-13"),), None)
    assert not cancelled and not unknown
    assert len(rebuilt) == 1 and rebuilt[0]["form_type"] == "Q3"


@pytest.mark.parametrize("with_end", (False, True))
def test_date_source_normal_rebuild_overwrite_same_owner(tmp_path: Path, with_end: bool) -> None:
    """参数为真实根及直接日期分支；返回无；三 writer 时序/旧 processed 清 None/v3/内容版本错误时断言失败。"""
    report_date = "2025-09-30" if with_end else None
    title = "截至2025年9月30日止第三季度業績" if with_end else "2025年第三季度業績"
    candidate = replace(_candidate(source_id="same", fiscal_year=2025, fiscal_period="Q3", provider="hkexnews", filing_date="2025-11-13"), title=title, category_text="季度業績", report_date=report_date)
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(candidate,))
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, hk_discovery=discovery, converter=_FakeConverter())
    first = pipeline.download(ticker="0700", form_type="Q3", start_date="2025", end_date="2025", start_is_explicit=True)
    ids = pipeline.source_repository.list_source_document_ids("0700", SourceKind.FILING)
    assert len(ids) == 1
    doc = ids[0]
    source = pipeline.source_repository.get_source_meta("0700", doc, SourceKind.FILING)
    expected_source = "source_title" if with_end else None
    assert source["report_date"] == report_date and source["report_date_source"] == expected_source
    internal_id = source["internal_document_id"]
    assert isinstance(internal_id, str)
    batch = pipeline.batching_repository.begin_batch("0700")
    pipeline.processed_repository.create_processed(ProcessedCreateRequest(
        ticker="0700", document_id=doc, internal_document_id=internal_id, source_kind="filing", form_type="Q3",
        meta={"report_date": "2020-01-01", "report_date_source": "old_source", "fiscal_period": "Q3"},
        sections=[{"id": "s", "text": "保全内容"}], tables=[], financials={"unchanged": 1},
    ), batch=batch)
    pipeline.batching_repository.commit_batch(batch)
    assert pipeline.processed_repository.get_processed_meta("0700", doc)["report_date"] == "2020-01-01"
    before = pipeline.source_repository.get_source_meta("0700", doc, SourceKind.FILING)
    content = {k: v for k, v in _tree(tmp_path).items() if k.endswith(("sections.json", "tables.json", "financials.json"))}
    rows, unknown, cancelled = rebuild_hk_periods(pipeline, "0700", (PeriodDownloadWindow(fiscal_period="Q3", start_date="2025-01-01", end_date="2025-12-31"),), None)
    assert not unknown and not cancelled and rows[0]["report_date"] == report_date
    for meta in (pipeline.source_repository.get_source_meta("0700", doc, SourceKind.FILING), pipeline.processed_repository.get_processed_meta("0700", doc)):
        assert meta["report_date"] == report_date and meta["report_date_source"] == expected_source
        assert meta["period_resolution_version"] == "hk-period-v3"
    assert pipeline.source_repository.classify_source_integrity("0700", doc, SourceKind.FILING).status is SourceIntegrityStatus.COMPLETE
    assert _manifest_row(tmp_path, doc, processed=False)["report_date"] == report_date
    assert _manifest_row(tmp_path, doc, processed=True)["report_date"] == report_date
    assert pipeline.processed_repository.list_processed_documents("0700", DocumentQuery())[0].report_date == report_date
    overwritten = pipeline.download(ticker="0700", form_type="Q3", start_date="2025", end_date="2025", overwrite=True, start_is_explicit=True)
    raw_rows = overwritten["filings"]
    assert isinstance(raw_rows, list) and isinstance(raw_rows[0], dict) and raw_rows[0]["report_date"] == report_date
    after = pipeline.source_repository.get_source_meta("0700", doc, SourceKind.FILING)
    assert after["report_date_source"] == expected_source
    for key in ("internal_document_id", "document_id", "document_version", "source_fingerprint"):
        assert after[key] == before[key]
    assert pipeline.processed_repository.get_processed_meta("0700", doc)["report_date"] == report_date
    assert content == {k: v for k, v in _tree(tmp_path).items() if k.endswith(("sections.json", "tables.json", "financials.json"))}
    assert first["uncertain_reports"] == []


def test_rebuild_commits_a_but_unknown_b_keeps_every_asset(tmp_path: Path) -> None:
    """参数为真实根；返回无；N02 旧标签泄漏、B 资产变化或 A 被回滚时断言失败。"""
    a = replace(_candidate(source_id="A", fiscal_year=2024, fiscal_period="FY", provider="hkexnews"), title="截至2024年12月31日止全年業績", category_text="末期業績")
    b = replace(_candidate(source_id="B", fiscal_year=2025, fiscal_period="Q1", provider="hkexnews", filing_date="2025-11-13"), title="2024/2025年第三季度業績", category_text="季度業績")
    discovery = _FakeDiscoveryClient(temp_dir=tmp_path, candidates=(a, b))
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, hk_discovery=discovery, converter=_FakeConverter())
    pipeline.download(ticker="0700", form_type="FY,Q1", start_date="2024", end_date="2026", start_is_explicit=True)
    doc = build_cn_filing_ids(ticker="0700", form_type="Q1", fiscal_year=2025, fiscal_period="Q1", amended=False)[0]
    handle = pipeline.source_repository.get_source_handle("0700", doc, SourceKind.FILING)
    before = pipeline.source_repository.get_source_meta("0700", doc, SourceKind.FILING)
    internal = before["internal_document_id"]
    assert isinstance(internal, str)
    batch = pipeline.batching_repository.begin_batch("0700")
    pipeline.processed_repository.create_processed(ProcessedCreateRequest(
        ticker="0700", document_id=doc, internal_document_id=internal, source_kind="filing", form_type="Q1",
        meta={"fiscal_period": "Q1", "report_date": "2000-01-01", "report_date_source": "old"},
        sections=[{"id": "b", "text": "B 原内容"}], tables=[], financials={"B": 123},
    ), batch=batch)
    pipeline.batching_repository.commit_batch(batch)
    processed_before = pipeline.processed_repository.get_processed_meta("0700", doc)
    processed_handle = pipeline.processed_repository.get_processed_handle("0700", doc)
    processed_bytes = {item.name: pipeline.blob_repository.read_file_bytes(processed_handle, item.name) for item in pipeline.blob_repository.list_entries(processed_handle)}
    source_directory = tmp_path / pipeline.source_repository.get_source_document_locator("0700", doc, SourceKind.FILING)
    source_tree = _tree(source_directory)
    original_source_manifest = _manifest_row(tmp_path, doc, processed=False)
    original_processed_manifest = _manifest_row(tmp_path, doc, processed=True)
    bbytes = {item.name: pipeline.blob_repository.read_file_bytes(handle, item.name) for item in pipeline.blob_repository.list_entries(handle)}
    windows = tuple(PeriodDownloadWindow(fiscal_period=p, start_date="2024-01-01", end_date="2026-12-31") for p in ("FY", "Q1", "Q3", "Q4"))
    rows, unknown, cancelled = rebuild_hk_periods(pipeline, "0700", windows, None)
    assert not cancelled and len(rows) == len(unknown) == 1
    assert rows[0]["status"] == "downloaded"
    assert unknown[0].source_id == "B" and unknown[0].existing_document_id == doc
    assert set(unknown[0].to_json_value()) == {"source_id", "filing_date", "report_date", "existing_document_id", "reason_category", "reason_message"}
    assert pipeline.source_repository.get_source_meta("0700", doc, SourceKind.FILING) == before
    assert pipeline.processed_repository.get_processed_meta("0700", doc) == processed_before
    assert processed_bytes == {item.name: pipeline.blob_repository.read_file_bytes(processed_handle, item.name) for item in pipeline.blob_repository.list_entries(processed_handle)}
    assert _tree(source_directory) == source_tree
    assert _manifest_row(tmp_path, doc, processed=False) == original_source_manifest
    assert _manifest_row(tmp_path, doc, processed=True) == original_processed_manifest

    assert bbytes == {item.name: pipeline.blob_repository.read_file_bytes(handle, item.name) for item in pipeline.blob_repository.list_entries(handle)}
    stable = _tree(tmp_path / "portfolio")
    repeated, repeated_unknown, cancelled = rebuild_hk_periods(pipeline, "0700", windows, None)
    assert not cancelled and repeated[0]["status"] == "skipped" and repeated_unknown == unknown
    assert _tree(tmp_path / "portfolio") == stable


@pytest.mark.parametrize("cancel_after_a", (False, True))
@pytest.mark.parametrize("unknown_source_id", ("B", ' B"\\\nFins summary: discovered=9\r\x1b[2J\u2028\u2029😀 '))
def test_actual_adapter_observation_wait_and_cli_keep_a_and_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancel_after_a: bool,
    unknown_source_id: str,
) -> None:
    """验证真实 adapter、observed wait 和 CLI 的 A/未知 B 同源投影。

    :param tmp_path: 真实 Fs/runtime 隔离根。
    :param monkeypatch: 禁止 observed wait 读取 job 的替换夹具。
    :param cancel_after_a: 是否在 A 发布后取消。
    :param unknown_source_id: B 的原始普通或含特殊字符的来源引用。
    :returns: 无。
    :raises AssertionError: 原引用、A/B 计数、终态或行结构漂移、wait 读 job 时抛出。
    """
    raw = (
        _hk_raw(document_id="A", title="截至2025年9月30日止第三季度業績", category_text="季度業績", filing_date="2025-11-13"),
        _hk_raw(document_id=unknown_source_id, title="截至2025年8月31日止三個月業績", category_text="季度業績", filing_date="2025-11-13"),
    )
    discovery = _RawDiscovery(tmp_path, raw)
    pipeline = _build_pipeline(tmp_path=tmp_path, discovery=discovery, hk_discovery=discovery, converter=_FakeConverter())
    adapter = CnDownloadAdapter(pipeline=pipeline, source="hkexnews", market="HK")
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(tmp_path, executor=executor, download_adapters={("hkexnews", "HK"): adapter})
    monkeypatch.setattr(type(ingestion.job_store), "read_job", _reject_integrity_wait_job_read)
    request = build_fins_download_request(ticker="0700", form_types=("Q3",), start="2025", end="2025")
    handle = ingestion.prepare_observed_download(request, cancellation_token=_CancelAfterPublicationToken(pipeline.source_repository) if cancel_after_a else _NeverCancelledToken())
    ingestion.activate_observation(handle)
    executor.run_all()
    observed = asyncio.run(ingestion.poll_observation(handle))
    result = observed.result
    assert result is not None and result.status is (FinsResultStatus.CANCELLED if cancel_after_a else FinsResultStatus.FAILURE) and result.download is not None
    assert result.download.downloaded_count == result.download.uncertain_count == 1
    assert result.download.discovered_count == 2
    assert len(result.download.document_rows) == len(result.download.uncertain_reports) == 1
    confirmed_id, _ = build_cn_filing_ids(
        ticker="0700", form_type="Q3", fiscal_year=2025, fiscal_period="Q3", amended=False,
    )
    assert result.download.document_rows[0].document_id == confirmed_id
    assert result.download.uncertain_reports[0].source_id == unknown_source_id
    assert result.download.uncertain_reports[0].existing_document_id is None
    poll = FinsIngestionWaitPollAdapter(runtime=ingestion).poll_wait(_wait_snapshot(handle.handle_id, DOWNLOAD_TOOL_NAME))
    assert isinstance(poll, WaitPollReady)
    assert isinstance(poll.outcome, ResolveWaitCancelledOutcome if cancel_after_a else ResolveWaitFailedOutcome)
    message: JsonValue = json.loads(poll.outcome.result.message)
    assert isinstance(message, dict) and message["download"] == result.download.to_json_value()
    # CLI 同一 typed event 的展示。实际 CLI 主入口已由 rebuild unknown 用例锁定 exit 1。
    event = FinsEvent(event_type=FinsEventType.RESULT, operation_kind=FinsOperationKind.DOWNLOAD,
        message=result.title, emitted_at=datetime.now(timezone.utc), ticker="0700", filing_kind=None,
        document_label=None, progress=None, result=result)
    out, err = io.StringIO(), io.StringIO()
    render_fins_direct_event(event, stdout=out, stderr=err)
    assert out.getvalue() == ""
    if cancel_after_a:
        assert "Fins cancelled:" in err.getvalue()
    text = out.getvalue() + err.getvalue()
    assert "uncertain=1" in text and f"source_id={json.dumps(unknown_source_id, ensure_ascii=True)}" in text
    assert "downloaded=1" in text and "未确认" in text
    unknown_line = next(line for line in text.splitlines() if line.startswith("Fins uncertain report:"))
    source_literal = unknown_line.split("source_id=", 1)[1].split(" existing_document_id=", 1)[0]
    assert json.loads(source_literal) == unknown_source_id
    assert "existing_document_id=-" in unknown_line
    assert sum(line.startswith("Fins summary:") for line in text.splitlines()) == 1
    assert len(text.splitlines()) == text.count("\n") == (4 if cancel_after_a else 6)
    assert result.exit_code == (130 if cancel_after_a else 1)


class _CancelAfterPublicationToken(_NeverCancelledToken):
    """仅在真实 A 发布后请求取消，不伪造存储状态。"""
    def __init__(self, source: SourceDocumentRepositoryProtocol) -> None:
        """参数为真实仓储；返回无；异常无。"""
        self.source = source
    def is_cancelled(self) -> bool:
        """参数无；返回是否已有确认 A；原仓储异常透传。"""
        return bool(self.source.list_source_document_ids("0700", SourceKind.FILING))
