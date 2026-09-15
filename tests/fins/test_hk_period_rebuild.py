"""公开 CLI 对隔离合成缓存执行财期纠正；不接触投资项目或远端文件。"""

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event

import pytest

from dayu.cli.main import main
from dayu.fins.domain.document_models import (
    BatchToken,
    DocumentHandle,
    DocumentQuery,
    ProcessedCreateRequest,
    SourceDocumentUpsertRequest,
)
from dayu.fins.domain.enums import SourceKind
from dayu.fins.pipelines.cn_download_models import CnReportPeriodProjection
from dayu.fins.pipelines.cn_form_utils import PeriodDownloadWindow, build_cn_filing_ids
from dayu.fins.pipelines.hk_download_rebuild import rebuild_hk_periods
from dayu.fins.pipelines.cn_pipeline import CnPipeline
from dayu.fins.storage import SourceIntegrityStatus
from tests.fins.test_cn_download_workflow import _FakeConverter, _FakeDiscoveryClient, _build_pipeline, _candidate


def _seed(tmp_path: Path, *, annual: bool = True) -> CnPipeline:
    """生成合成旧缓存。参数为隔离目录及是否有年度证据；返回 pipeline；断言或仓储异常透传。"""
    candidates = tuple(
        replace(
            _candidate(
                source_id=f"quarter-{year}",
                fiscal_year=year,
                fiscal_period="Q1",
                provider="hkexnews",
                filing_date=f"{year}-11-{29 if year == 2024 else 28}",
            ),
            title=f"截至{year}年9月30日止三個月業績公告",
        )
        for year in (2024, 2025)
    )
    if annual:
        candidates += (
            replace(
                _candidate(source_id="annual", fiscal_year=2024, fiscal_period="Q4", provider="hkexnews"),
                title="截至2024年12月31日止全年業績",
                category_text="末期業績",
                period_projection=CnReportPeriodProjection(identity_period="Q4", covered_periods=("FY", "Q4")),
            ),
        )
    pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=()),
        hk_discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=candidates),
        converter=_FakeConverter(),
    )
    result = pipeline.download(
        ticker="3690", form_type="Q1,Q4", start_date="2024", end_date="2026", start_is_explicit=True
    )
    summary = result["summary"]
    assert isinstance(summary, dict)
    assert summary["failed"] == 0
    return pipeline


def _document_id(year: int) -> str:
    """参数为历史误判财年；返回旧 Q1 文档 ID；ID 构造异常透传。"""
    return build_cn_filing_ids(ticker="3690", form_type="Q1", fiscal_year=year, fiscal_period="Q1", amended=False)[0]


def _cli(tmp_path: Path, day: str | None = None) -> int:
    """参数为隔离目录和可选单一披露日；返回生产 CLI 退出码；入口异常透传。"""
    return main(
        (
            "download",
            "--base",
            str(tmp_path),
            "--ticker",
            "3690",
            "--forms",
            "Q1",
            "Q3",
            "--start",
            day or "2024-11-01",
            "--end",
            day or "2025-11-30",
            "--rebuild",
        )
    )


def test_cli_corrects_cached_periods_and_is_idempotent(tmp_path: Path) -> None:
    """参数为临时目录；返回无；CLI、索引、身份、hash、幂等或增量契约错误时断言失败。"""
    pipeline = _seed(tmp_path)
    source = pipeline.source_repository
    before = {
        year: dict(source.get_source_meta("3690", _document_id(year), SourceKind.FILING)) for year in (2024, 2025)
    }
    handles = {year: source.get_source_handle("3690", _document_id(year), SourceKind.FILING) for year in before}
    contents = {
        year: pipeline.blob_repository.read_file_bytes(handle, f"{_document_id(year)}.pdf")
        for year, handle in handles.items()
    }
    document_id = _document_id(2025)
    batch = pipeline.batching_repository.begin_batch("3690")
    pipeline.processed_repository.create_processed(
        ProcessedCreateRequest(
            ticker="3690",
            document_id=document_id,
            internal_document_id=before[2025]["internal_document_id"],
            source_kind="filing",
            form_type="Q1",
            meta={"fiscal_period": "Q1"},
            sections=[{"id": "unchanged", "text": "合成正文"}],
            tables=[],
            financials={"preserve": 123},
        ),
        batch=batch,
    )
    pipeline.batching_repository.commit_batch(batch)
    body_before = {
        p.relative_to(tmp_path): p.read_bytes()
        for p in (tmp_path / "portfolio").rglob("*")
        if p.is_file() and p.name in ("sections.json", "tables.json", "financials.json")
    }
    assert body_before
    assert _cli(tmp_path, "2024-11-29") == 0
    assert _cli(tmp_path, "2025-11-28") == 0
    assert body_before == {
        p.relative_to(tmp_path): p.read_bytes()
        for p in (tmp_path / "portfolio").rglob("*")
        if p.is_file() and p.name in ("sections.json", "tables.json", "financials.json")
    }
    after = {year: dict(source.get_source_meta("3690", _document_id(year), SourceKind.FILING)) for year in before}
    for year, meta in after.items():
        assert meta["fiscal_period"] == meta["form_type"] == meta["report_kind"] == "Q3"
        assert meta["fiscal_year"] == year
        assert meta["report_date"] == f"{year}-09-30"
        assert meta["covered_fiscal_periods"] == ["Q3"]
        for field in (
            "document_id",
            "internal_document_id",
            "files",
            "source_fingerprint",
            "remote_fingerprint",
            "pdf_sha256",
            "document_version",
            "primary_document",
        ):
            assert meta[field] == before[year][field]
        assert pipeline.blob_repository.read_file_bytes(handles[year], f"{_document_id(year)}.pdf") == contents[year]
        assert (
            source.classify_source_integrity("3690", _document_id(year), SourceKind.FILING).status
            is SourceIntegrityStatus.COMPLETE
        )
    processed = pipeline.processed_repository.get_processed_meta("3690", document_id)
    assert processed["form_type"] == processed["fiscal_period"] == "Q3"
    assert pipeline.processed_repository.list_processed_documents("3690", DocumentQuery(form_type="Q1")) == []
    assert [
        row.document_id
        for row in pipeline.processed_repository.list_processed_documents("3690", DocumentQuery(form_type="Q3"))
    ] == [document_id]
    # 包含 manifest、meta、processed 文本/索引在内的所有 published 文件逐字节比较。
    tree = {p.relative_to(tmp_path): p.read_bytes() for p in (tmp_path / "portfolio").rglob("*") if p.is_file()}
    assert _cli(tmp_path, "2024-11-29") == 0
    assert _cli(tmp_path, "2025-11-28") == 0
    assert tree == {p.relative_to(tmp_path): p.read_bytes() for p in (tmp_path / "portfolio").rglob("*") if p.is_file()}
    assert after == {
        year: dict(source.get_source_meta("3690", _document_id(year), SourceKind.FILING)) for year in before
    }
    # 再次普通增量下载同 provider/source ID 的正确候选必须复用旧 ID。
    corrected = replace(
        _candidate(
            source_id="quarter-2025",
            fiscal_year=2025,
            fiscal_period="Q3",
            provider="hkexnews",
            filing_date="2025-11-28",
        ),
        title="截至2025年9月30日止三個月業績公告",
    )
    follow = _build_pipeline(
        tmp_path=tmp_path,
        discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=()),
        hk_discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=(corrected,)),
        converter=_FakeConverter(),
    )
    ids_before = source.list_source_document_ids("3690", SourceKind.FILING)
    result = follow.download(ticker="3690", form_type="Q3", start_date="2024", end_date="2026", start_is_explicit=True)
    filings = result["filings"]
    assert isinstance(filings, list) and isinstance(filings[0], dict)
    assert filings[0]["document_id"] == document_id
    assert filings[0]["status"] == "skipped"
    assert source.list_source_document_ids("3690", SourceKind.FILING) == ids_before
    real_q1 = replace(
        corrected,
        source_id="real-q1",
        title="2025年第一季度業績",
        period_projection=CnReportPeriodProjection(identity_period="Q1", covered_periods=("Q1",)),
    )
    new_pipeline = _build_pipeline(
        tmp_path=tmp_path,
        discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=()),
        hk_discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=(real_q1,)),
        converter=_FakeConverter(),
    )
    added = new_pipeline.download(
        ticker="3690", form_type="Q1", start_date="2024", end_date="2026", start_is_explicit=True
    )
    added_filings = added["filings"]
    assert isinstance(added_filings, list) and isinstance(added_filings[0], dict)
    assert added_filings[0]["status"] == "downloaded"
    assert added_filings[0]["document_id"] not in ids_before
    assert source.get_source_meta("3690", document_id, SourceKind.FILING) == after[2025]


def test_cli_uncertain_cache_is_unchanged(tmp_path: Path) -> None:
    """参数为临时目录；返回无；无年度证据时必须退出失败并保留缓存，否则断言失败。"""
    pipeline = _seed(tmp_path, annual=False)
    before = {
        year: dict(pipeline.source_repository.get_source_meta("3690", _document_id(year), SourceKind.FILING))
        for year in (2024, 2025)
    }
    assert _cli(tmp_path) == 1
    assert before == {
        year: dict(pipeline.source_repository.get_source_meta("3690", _document_id(year), SourceKind.FILING))
        for year in before
    }


def test_concurrent_hk_rebuild_reads_after_writer_lock(tmp_path: Path) -> None:
    """参数为临时目录；返回无；两独立仓储并发纠正必须只有一次发布，否则断言失败。"""
    first = _seed(tmp_path)
    second = _build_pipeline(
        tmp_path=tmp_path, discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=()), converter=_FakeConverter()
    )
    barrier = Barrier(2)

    def rebuild(pipeline: CnPipeline) -> int:
        """参数为独立仓储宿主；返回发布数量；超时或流水线异常透传。"""
        barrier.wait(timeout=10)
        result = pipeline.download(
            ticker="3690", form_type="Q1,Q3", start_date="2024", end_date="2026", rebuild=True, start_is_explicit=True
        )
        summary = result["summary"]
        assert isinstance(summary, dict) and isinstance(summary["downloaded"], int)
        assert summary["failed"] == 0
        return summary["downloaded"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(rebuild, pipeline) for pipeline in (first, second)]
        assert sorted(f.result(timeout=20) for f in futures) == [0, 2]


def test_hk_rebuild_cancellation_rolls_back_all_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """参数为隔离目录与替换夹具；返回无；首份暂存后取消必须保持整棵 published tree，否则断言失败。"""
    pipeline = _seed(tmp_path)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in (tmp_path / "portfolio").rglob("*") if p.is_file()}
    staged = Event()
    original = pipeline.source_repository.update_source_document

    def stage_then_cancel(
        req: SourceDocumentUpsertRequest, source_kind: SourceKind, *, batch: BatchToken
    ) -> DocumentHandle:
        """参数为仓储更新请求；返回真实暂存结果并触发取消；仓储异常透传。"""
        handle = original(req, source_kind, batch=batch)
        staged.set()
        return handle

    monkeypatch.setattr(pipeline.source_repository, "update_source_document", stage_then_cancel)
    filings, was_cancelled = rebuild_hk_periods(
        pipeline,
        "3690",
        (PeriodDownloadWindow(fiscal_period="Q1", start_date="2024-01-01", end_date="2026-12-31"),),
        staged.is_set,
    )
    assert staged.is_set()
    assert was_cancelled
    assert all(row["status"] != "downloaded" for row in filings)
    assert before == {
        p.relative_to(tmp_path): p.read_bytes() for p in (tmp_path / "portfolio").rglob("*") if p.is_file()
    }


def test_hk_rebuild_write_failure_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """参数为隔离目录和替换夹具；返回无；仓储发布前失败必须回滚，否则断言失败。"""
    pipeline = _seed(tmp_path)
    before = {p.relative_to(tmp_path): p.read_bytes() for p in (tmp_path / "portfolio").rglob("*") if p.is_file()}

    def fail_update(req: SourceDocumentUpsertRequest, source_kind: SourceKind, *, batch: BatchToken) -> DocumentHandle:
        """参数为更新请求；不返回；确定性模拟仓储 I/O 异常。"""
        raise OSError("synthetic update failure")

    monkeypatch.setattr(pipeline.source_repository, "update_source_document", fail_update)
    with pytest.raises(OSError, match="synthetic update failure"):
        rebuild_hk_periods(
            pipeline,
            "3690",
            (PeriodDownloadWindow(fiscal_period="Q1", start_date="2024-01-01", end_date="2026-12-31"),),
            None,
        )
    assert before == {
        p.relative_to(tmp_path): p.read_bytes() for p in (tmp_path / "portfolio").rglob("*") if p.is_file()
    }


def test_incremental_mismatch_reports_rebuild_required(tmp_path: Path) -> None:
    """参数为临时目录；返回无；纠正前普通增量不得投影成已正确持久化的 skip，否则断言失败。"""
    pipeline = _seed(tmp_path)
    before = dict(pipeline.source_repository.get_source_meta("3690", _document_id(2025), SourceKind.FILING))
    corrected = _candidate(source_id="quarter-2025", fiscal_year=2025, fiscal_period="Q3", provider="hkexnews")
    follow = _build_pipeline(
        tmp_path=tmp_path,
        discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=()),
        hk_discovery=_FakeDiscoveryClient(temp_dir=tmp_path, candidates=(corrected,)),
        converter=_FakeConverter(),
    )
    result = follow.download(ticker="3690", form_type="Q3", start_date="2024", end_date="2026", start_is_explicit=True)
    filings = result["filings"]
    assert isinstance(filings, list) and isinstance(filings[0], dict)
    assert filings[0]["status"] == "failed"
    assert filings[0]["reason_code"] == "period_metadata_mismatch"
    assert before == pipeline.source_repository.get_source_meta("3690", _document_id(2025), SourceKind.FILING)
