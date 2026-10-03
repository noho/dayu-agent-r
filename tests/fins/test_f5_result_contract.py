"""F5 完整结果 owner、fresh job schema 与取消保全契约；全部资产为隔离合成数据。"""

import json
from dataclasses import replace
from pathlib import Path, PurePosixPath

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.fins import ingestion_runtime as runtime
from dayu.fins.direct_events import FinsResultStatus
from dayu.fins.download_contract import (
    FinsDownloadDocumentDisposition, FinsDownloadDocumentResult, FinsDownloadEffectiveFilters,
    FinsDownloadResultSummary, FinsDownloadSource, FinsDownloadTerminalDisposition,
    FinsDownloadUncertainReport, build_fins_download_request, validate_download_json_summary,
)
from tests.fins.test_fins_ingestion_runtime import (
    _HoldingExecutor, _PersistedSummaryDownloadAdapter, _build_ingestion_runtime,
    _collect_direct_events, _OperationFailureDownloadAdapter,
)

_BUDGET = 4096


def _summary(*, known: int = 1, unknown: int = 1, id_chars: int = 8) -> FinsDownloadResultSummary:
    """参数为确认/未知数量及引用长度；返回完整合成 HK 结果；非法 contract 原样抛出。"""
    rows = tuple(FinsDownloadDocumentResult(
        document_id=f"A{i}".ljust(id_chars, "a"), form_or_period="Q3", filing_date="2025-11-13",
        report_date="2025-09-30", covered_fiscal_periods=("Q3",),
        disposition=FinsDownloadDocumentDisposition.DOWNLOADED, reason_category=None, reason_message=None,
        artifact_locator=PurePosixPath(f"source/0700/A{i}"),
    ) for i in range(known))
    reports = tuple(FinsDownloadUncertainReport(
        source_id=f"B{i:03}".ljust(id_chars, "b"), filing_date="2025-11-13", report_date=None,
        existing_document_id=None, reason_category="uncertain_hk_period",
    ) for i in range(unknown))
    return FinsDownloadResultSummary.from_document_rows(
        source=FinsDownloadSource.HKEXNEWS, canonical_ticker="0700",
        effective_filters=FinsDownloadEffectiveFilters(("Q3",), "2025-01-01", "2025-12-31", False, False),
        document_rows=rows, uncertain_reports=reports,
    )


@pytest.mark.parametrize(("known", "unknown", "id_chars"), ((0, 0, 8), (0, 1, 8), (11, 11, 8), (12, 12, 240)))
def test_public_and_durable_share_unknown_budget_and_conserve_counts(known: int, unknown: int, id_chars: int) -> None:
    """参数为极值结果；返回无；真实 ID、双 omission、4096 或终态不守恒时断言失败。"""
    summary = _summary(known=known, unknown=unknown, id_chars=id_chars)
    durable = summary.to_json_summary(max_json_chars=_BUDGET)
    public = runtime._public_download_summary(summary)
    validate_download_json_summary(durable)
    assert len(json.dumps(durable, ensure_ascii=False, sort_keys=True)) <= _BUDGET
    assert durable["uncertain_reports"] == [r.to_json_value() for r in public.uncertain_reports]
    assert public.omitted_count == max(0, known - 10)
    assert len(public.uncertain_reports) + public.omitted_uncertain_count == unknown
    assert len(public.document_rows) + public.omitted_count + unknown == summary.discovered_count
    assert len(public.uncertain_reports) <= 10
    if unknown:
        assert public.uncertain_reports
        assert len(public.uncertain_reports[0].source_id) == id_chars
        assert summary.terminal_disposition is (FinsDownloadTerminalDisposition.PARTIAL_FAILURE if known else FinsDownloadTerminalDisposition.FAILED)
    else:
        assert summary.terminal_disposition is FinsDownloadTerminalDisposition.SUCCEEDED
    written = durable["written_document_ids"]
    assert isinstance(written, list)
    assert all(isinstance(item, str) and len(item) == id_chars for item in written)
    omitted = durable["omitted_written_document_count"]
    assert isinstance(omitted, int)
    assert len(written) + omitted == known
    with pytest.raises(ValueError, match="fit"):
        summary.to_json_summary(max_json_chars=1)


@pytest.mark.parametrize("key", ("uncertain_reports", "uncertain_count", "omitted_uncertain_count", "written_document_ids", "filters"))
def test_fresh_schema_rejects_missing_fields(key: str) -> None:
    """参数为被删必填键；返回无；新 schema 接受缺字段时断言失败。"""
    value = _summary().to_json_summary(max_json_chars=_BUDGET)
    del value[key]
    with pytest.raises(ValueError, match="schema"):
        validate_download_json_summary(value)


@pytest.mark.parametrize("key", ("source_id", "filing_date", "report_date", "existing_document_id", "reason_category", "reason_message"))
def test_uncertain_null_is_not_missing_and_message_is_same_fact(key: str) -> None:
    """参数为删除键；返回无；未知 null/缺失或说明漂移未拒绝时断言失败。"""
    report = _summary().uncertain_reports[0]
    value = report.to_json_value()
    assert FinsDownloadUncertainReport.from_json_value(value) == report
    del value[key]
    with pytest.raises(ValueError):
        FinsDownloadUncertainReport.from_json_value(value)
    value = report.to_json_value()
    value["reason_message"] = "截止日已确认"
    with pytest.raises(ValueError, match="message"):
        FinsDownloadUncertainReport.from_json_value(value)


@pytest.mark.parametrize(("key", "value"), (
    ("discovered_count", 99), ("uncertain_count", True), ("omitted_uncertain_count", 1),
    ("terminal_disposition", "succeeded"), ("source", "sec"), ("written_document_ids", ["A0", "A0"]),
    ("uncertain_reports", []),
))
def test_durable_owner_rejects_invalid_facts(key: str, value: JsonValue) -> None:
    """参数为畸形事实；返回无；owner 接受矛盾数据时断言失败。"""
    summary = _summary().to_json_summary(max_json_chars=_BUDGET)
    summary[key] = value
    with pytest.raises(ValueError):
        validate_download_json_summary(summary)


def test_real_store_rejects_succeeded_with_unknown_on_writer_reader_and_atomic(tmp_path: Path) -> None:
    """在真实 Fs 写入、回读及原子成功入口拒绝矛盾终态。

    参数：tmp_path 为独立 job 仓储根。
    返回：无。
    异常：成功状态接受未知报告、拒绝时改变原记录或回读放行时断言失败。
    """
    ingestion = _build_ingestion_runtime(tmp_path, executor=_HoldingExecutor())
    start = ingestion.start_download(build_fins_download_request(ticker="0700"))
    summary = _summary()
    value = summary.to_json_summary(max_json_chars=_BUDGET)
    store = runtime.FsFinsIngestionJobStore.from_workspace_root(tmp_path)
    with pytest.raises(ValueError, match="未确认财期"):
        store.save_job(replace(start.record, status=runtime.FinsIngestionJobStatus.SUCCEEDED, result_summary=value))
    assert ingestion.read_job(start.job_id) == start.record
    with pytest.raises(ValueError, match="未确认财期"):
        store.save_succeeded_or_cancelled(
            start.job_id, result_summary=value,
            cancelled_result_summary=runtime._cancelled_download_json_summary(summary),
            finished_at=start.record.updated_at,
        )
    assert ingestion.read_job(start.job_id) == start.record
    failed = store.save_job(replace(start.record, status=runtime.FinsIngestionJobStatus.FAILED, result_summary=value))
    assert ingestion.read_job(start.job_id) == failed
    path = store._job_path(start.job_id)
    payload: JsonValue = json.loads(path.read_text())
    assert isinstance(payload, dict)
    payload["status"] = runtime.FinsIngestionJobStatus.SUCCEEDED.value
    path.write_text(json.dumps(payload, ensure_ascii=False))
    with pytest.raises(ValueError, match="未确认财期"):
        ingestion.read_job(start.job_id)


@pytest.mark.parametrize(("known", "unknown", "status"), (
    (1, 1, runtime.FinsIngestionJobStatus.FAILED),
    (0, 1, runtime.FinsIngestionJobStatus.FAILED),
    (1, 1, runtime.FinsIngestionJobStatus.CANCELLED),
    (0, 0, runtime.FinsIngestionJobStatus.SUCCEEDED),
    (1, 0, runtime.FinsIngestionJobStatus.SUCCEEDED),
    (1, 0, runtime.FinsIngestionJobStatus.FAILED),
))
def test_real_store_preserves_legal_download_terminal_results(tmp_path: Path, known: int, unknown: int, status: runtime.FinsIngestionJobStatus) -> None:
    """验证必要拒绝规则不会扩大为拒绝合法失败、取消或真空成功。

    参数：tmp_path 为独立根；known/unknown 为合成报告数；status 为合法 job 终态。
    返回：无。
    异常：合法 typed 结果被拒、A/B 丢失或读写不一致时断言失败。
    """
    ingestion = _build_ingestion_runtime(tmp_path, executor=_HoldingExecutor())
    start = ingestion.start_download(build_fins_download_request(ticker="0700"))
    summary = _summary(known=known, unknown=unknown)
    value = runtime._cancelled_download_json_summary(summary) if status is runtime.FinsIngestionJobStatus.CANCELLED else summary.to_json_summary(max_json_chars=_BUDGET)
    saved = ingestion.job_store.save_job(replace(start.record, status=status, result_summary=value))
    assert ingestion.read_job(start.job_id) == saved
    assert saved.result_summary == value


def test_real_store_keeps_original_succeeded_partial_without_unknown(tmp_path: Path) -> None:
    """验证没有未知报告时保留原正常部分下载的成功 job 语义。

    参数：tmp_path 为独立 job 仓储根。
    返回：无。
    异常：正常 partial 被误拒或原子成功入口改变摘要时断言失败。
    """
    base = _summary(known=2, unknown=0)
    summary = FinsDownloadResultSummary.from_document_rows(
        source=base.source, canonical_ticker=base.canonical_ticker, effective_filters=base.effective_filters,
        document_rows=(base.document_rows[0], replace(
            base.document_rows[1], disposition=FinsDownloadDocumentDisposition.FAILED, artifact_locator=None,
            reason_category="download_failed", reason_message="该合成文档下载失败",
        )),
        uncertain_reports=(),
    )
    assert summary.terminal_disposition is FinsDownloadTerminalDisposition.PARTIAL_FAILURE
    ingestion = _build_ingestion_runtime(tmp_path, executor=_HoldingExecutor())
    start = ingestion.start_download(build_fins_download_request(ticker="0700"))
    value = summary.to_json_summary(max_json_chars=_BUDGET)
    saved = ingestion.job_store.save_succeeded_or_cancelled(
        start.job_id, result_summary=value,
        cancelled_result_summary=runtime._cancelled_download_json_summary(summary),
        finished_at=start.record.updated_at,
    )
    assert saved.status is runtime.FinsIngestionJobStatus.SUCCEEDED
    assert ingestion.read_job(start.job_id).result_summary == value


@pytest.mark.asyncio
@pytest.mark.parametrize(("known", "unknown"), ((1, 1), (0, 1), (0, 0)))
async def test_direct_and_job_share_whole_request_failure(tmp_path: Path, known: int, unknown: int) -> None:
    """参数为隔离根及结果数量；返回无；direct/job 不一致或已确认 A 丢失时断言失败。"""
    summary = _summary(known=known, unknown=unknown)
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(tmp_path, executor=executor, download_adapters={
        ("hkexnews", "HK"): _PersistedSummaryDownloadAdapter(summary),
    })
    request = build_fins_download_request(ticker="0700", form_types=("Q3",), start="2025", end="2025")
    events = await _collect_direct_events(ingestion.download(request))
    result = events[-1].result
    assert result is not None and result.download is not None
    assert result.status is (FinsResultStatus.FAILURE if unknown else FinsResultStatus.SUCCESS)
    assert result.exit_code == (1 if unknown else 0)
    assert result.download.downloaded_count == known
    start = ingestion.start_download(request)
    executor.run_all()
    record = ingestion.read_job(start.job_id)
    assert record.status is (runtime.FinsIngestionJobStatus.FAILED if unknown else runtime.FinsIngestionJobStatus.SUCCEEDED)
    assert record.result_summary == summary.to_json_summary(max_json_chars=_BUDGET)
    assert record.result_summary["uncertain_reports"] == result.download.to_json_value()["uncertain_reports"]


@pytest.mark.parametrize("atomic", ("success", "failure", "cancel"))
def test_real_store_atomic_cancel_keeps_caller_projection(tmp_path: Path, atomic: str) -> None:
    """参数为隔离仓储及原子入口；返回无；竞态取消清空 A/B 或缺投影被接受时断言失败。"""
    ingestion = _build_ingestion_runtime(tmp_path, executor=_HoldingExecutor())
    start = ingestion.start_download(build_fins_download_request(ticker="0700", form_types=("Q3",), start="2025", end="2025"))
    ingestion.request_cancel(start.job_id)
    summary = _summary()
    normal = summary.to_json_summary(max_json_chars=_BUDGET)
    cancelled = runtime._cancelled_download_json_summary(summary)
    store = ingestion.job_store
    if atomic == "success":
        with pytest.raises(ValueError, match="取消投影"):
            store.save_succeeded_or_cancelled(start.job_id, result_summary=normal, cancelled_result_summary=None, finished_at=start.record.updated_at)
        saved = store.save_succeeded_or_cancelled(start.job_id, result_summary=normal, cancelled_result_summary=cancelled, finished_at=start.record.updated_at)
    elif atomic == "failure":
        with pytest.raises(ValueError, match="取消投影"):
            store.save_failed_or_cancelled_if_active(start.job_id, result_summary=normal, cancelled_result_summary=None, failure_summary={}, finished_at=start.record.updated_at)
        saved = store.save_failed_or_cancelled_if_active(start.job_id, result_summary=normal, cancelled_result_summary=cancelled, failure_summary={}, finished_at=start.record.updated_at)
    else:
        store.save_job(replace(ingestion.read_job(start.job_id), result_summary=normal))
        with pytest.raises(ValueError, match="投影"):
            store.save_cancelled_if_active(start.job_id, result_summary=None, finished_at=start.record.updated_at)
        saved = store.save_cancelled_if_active(start.job_id, result_summary=cancelled, finished_at=start.record.updated_at)
    assert saved.status is runtime.FinsIngestionJobStatus.CANCELLED
    assert saved.result_summary == cancelled
    assert ingestion.read_job(start.job_id) == saved
    assert store.save_cancelled_if_active(start.job_id, result_summary=None, finished_at=start.record.updated_at) == saved


@pytest.mark.parametrize("terminal", (runtime.FinsIngestionJobStatus.CANCELLED, runtime.FinsIngestionJobStatus.FAILED))
def test_fresh_no_typed_result_can_remain_empty(tmp_path: Path, terminal: runtime.FinsIngestionJobStatus) -> None:
    """参数为隔离根及合法未执行终态；返回无；空摘要写读/二次终态化失败时断言失败。"""
    ingestion = _build_ingestion_runtime(tmp_path, executor=_HoldingExecutor())
    start = ingestion.start_download(build_fins_download_request(ticker="0700"))
    if terminal is runtime.FinsIngestionJobStatus.CANCELLED:
        saved = ingestion.job_store.save_cancelled_if_active(start.job_id, result_summary=None, finished_at=start.record.updated_at)
    else:
        saved = ingestion.job_store.save_failed_or_cancelled_if_active(start.job_id, result_summary=None, cancelled_result_summary=None, failure_summary={"message": "发现前读取失败"}, finished_at=start.record.updated_at)
    assert saved.result_summary == {}
    assert ingestion.read_job(start.job_id) == saved
    assert ingestion.job_store.save_cancelled_if_active(start.job_id, result_summary=None, finished_at=start.record.updated_at) == saved
    with pytest.raises(ValueError, match="typed summary"):
        ingestion.job_store.save_job(replace(saved, status=runtime.FinsIngestionJobStatus.SUCCEEDED))
    with pytest.raises(ValueError, match="schema"):
        ingestion.job_store.save_job(replace(saved, result_summary={"downloaded_count": 1}))


def test_returned_typed_summary_survives_closing_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """参数为真实 job 根及收口失败注入；返回无；已返回 typed A/B 在收口错误后丢失时断言失败。"""
    executor = _HoldingExecutor()
    summary = _summary()
    ingestion = _build_ingestion_runtime(tmp_path, executor=executor, download_adapters={
        ("hkexnews", "HK"): _PersistedSummaryDownloadAdapter(summary),
    })
    start = ingestion.start_download(build_fins_download_request(ticker="0700", form_types=("Q3",), start="2025", end="2025"))
    monkeypatch.setattr(ingestion, "_save_failed", _SaveFailureOnce(ingestion))
    executor.run_all()
    record = ingestion.read_job(start.job_id)
    assert record.status is runtime.FinsIngestionJobStatus.FAILED
    assert record.result_summary == summary.to_json_summary(max_json_chars=_BUDGET)


class _SaveFailureOnce:
    """仅在已返回 typed 结果后的首次 store 收口失败，第二次保存真实投影。"""
    def __init__(self, ingestion: runtime.FinsIngestionRuntime) -> None:
        """参数为真实 store；返回无；异常无。"""
        self.original = ingestion._save_failed
        self.calls = 0
    def __call__(self, record: runtime.FinsIngestionJobRecord, *, message: str, result_summary: dict[str, JsonValue] | None, cancelled_result_summary: dict[str, JsonValue] | None) -> runtime.FinsIngestionJobRecord:
        """参数为调用方完整双投影；返回原 store 终态；首次调用抛 OSError，其后原异常透传。"""
        self.calls += 1
        if self.calls == 1:
            raise OSError("收口保存失败")
        return self.original(record, message=message, result_summary=result_summary, cancelled_result_summary=cancelled_result_summary)



def test_pretyped_ordinary_failure_does_not_invent_snapshot(tmp_path: Path) -> None:
    """参数为真实 job 根；返回无；发现前普通错误被伪造 typed 结果时断言失败。"""
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(tmp_path, executor=executor, download_adapters={
        ("hkexnews", "HK"): _OperationFailureDownloadAdapter(OSError("发现前原错误")),
    })
    start = ingestion.start_download(build_fins_download_request(ticker="0700"))
    executor.run_all()
    record = ingestion.read_job(start.job_id)
    assert record.status is runtime.FinsIngestionJobStatus.FAILED
    assert record.result_summary == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", tuple(runtime.SourceIntegrityPreflightReason))
async def test_f6_typed_reason_precedes_unknown_and_keeps_a(tmp_path: Path, reason: runtime.SourceIntegrityPreflightReason) -> None:
    """参数为真实四原因及隔离根；返回无；F6 cause 被未知原因覆盖或 A/B 丢失时断言失败。"""
    summary = _summary()
    cause = runtime.SourceIntegrityPreflightError(reason)
    abort = runtime.FinsSourceDownloadAdapterFailure(cause, summary)
    assert abort.cause is cause
    executor = _HoldingExecutor()
    ingestion = _build_ingestion_runtime(tmp_path, executor=executor, download_adapters={
        ("hkexnews", "HK"): _OperationFailureDownloadAdapter(abort),
    })
    request = build_fins_download_request(ticker="0700", form_types=("Q3",), start="2025", end="2025")
    events = await _collect_direct_events(ingestion.download(request))
    result = events[-1].result
    assert result is not None and result.failure is not None and result.download is not None
    assert result.failure.kind is runtime.FinsPublicFailureKind.STORAGE
    assert result.failure.reason_code is not None
    assert result.download.downloaded_count == result.download.uncertain_count == 1
    assert result.download.uncertain_reports == summary.uncertain_reports
    assert "财期依据" not in result.failure.safe_message
    start = ingestion.start_download(request)
    executor.run_all()
    record = ingestion.read_job(start.job_id)
    assert record.status is runtime.FinsIngestionJobStatus.FAILED
    assert record.result_summary == summary.to_json_summary(max_json_chars=_BUDGET)
