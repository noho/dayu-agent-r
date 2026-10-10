"""下载完整失败诊断的 owner 契约与单行公共输出验证。"""

from __future__ import annotations

import io
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import cast

import pytest
from unittest.mock import Mock

import dayu.fins.direct_events as direct_events

from dayu.cli.output import render_fins_direct_event
from dayu.fins.direct_events import (
    FinsDownloadPublicSummary, FinsErrorKind, FinsEvent, FinsEventType,
    FinsOperationKind, FinsPublicFailure, FinsPublicFailureKind,
    FinsResultStatus, FinsResultSummary,
)
from dayu.fins.download_contract import (
    FinsDownloadDocumentDisposition, FinsDownloadDocumentResult,
    FinsDownloadEffectiveFilters, FinsDownloadResultSummary,
    FinsDownloadSource, FinsDownloadTerminalDisposition,
    FINS_DOWNLOAD_SUMMARY_MAX_JSON_CHARS, validate_download_json_summary,
)

_DIAGNOSTICS_PREFIX = "Fins download diagnostics: "
_SPECIAL_ID = ('引号"换行\n反斜杠\\分隔\u2028\u2029' + '界' * 240)[:240]


def _document(index: int, disposition: FinsDownloadDocumentDisposition, *, unknown: bool = False) -> FinsDownloadDocumentResult:
    """生成独立 typed 候选事实。

    Args:
        index: 候选原序编号。
        disposition: 来源已经确认的结果。
        unknown: 是否明确保留未知日期和期间。

    Returns:
        来源级文档结果。

    Raises:
        ValueError: 固定事实违反下载契约时抛出。
    """

    downloaded = disposition is FinsDownloadDocumentDisposition.DOWNLOADED
    return FinsDownloadDocumentResult(
        document_id=_SPECIAL_ID if index == 0 else f"candidate-{index}",
        form_or_period=None if unknown else "FY",
        filing_date=None if unknown else "2025-04-01",
        report_date=None if unknown else "2024-12-31",
        covered_fiscal_periods=() if unknown else ("FY",),
        disposition=disposition,
        reason_category=None if downloaded else ("integrity_complete" if disposition is FinsDownloadDocumentDisposition.SKIPPED else "provider_timeout"),
        reason_message=None if downloaded else ("本地来源完整，跳过下载" if disposition is FinsDownloadDocumentDisposition.SKIPPED else "来源请求超时，请稍后重试"),
        artifact_locator=PurePosixPath(f"source/example/{index}") if downloaded else None,
    )


def _download_summary(*, failed: int = 0, skipped: int = 0, downloaded: int = 0, source: FinsDownloadSource = FinsDownloadSource.HKEXNEWS, unknown: bool = False) -> FinsDownloadResultSummary:
    """从独立来源事实创建完整结果，不从公开摘要反推。

    Args:
        failed: 已确认失败候选数。
        skipped: 已确认跳过候选数。
        downloaded: 已确认下载候选数。
        source: 下载来源。
        unknown: 候选日期和期间是否未知。

    Returns:
        下载 owner 派生计数的完整结果。

    Raises:
        ValueError: 候选不满足下载契约时抛出。
    """

    dispositions = (FinsDownloadDocumentDisposition.SKIPPED,) * skipped + (FinsDownloadDocumentDisposition.DOWNLOADED,) * downloaded + (FinsDownloadDocumentDisposition.FAILED,) * failed
    return FinsDownloadResultSummary.from_document_rows(
        source=source, canonical_ticker={FinsDownloadSource.SEC: "AAPL", FinsDownloadSource.CNINFO: "600519", FinsDownloadSource.HKEXNEWS: "0700"}[source],
        effective_filters=FinsDownloadEffectiveFilters(("10-K",) if source is FinsDownloadSource.SEC else ("FY",), "2018-01-01", "2026-10-10", False, False),
        document_rows=tuple(_document(index, disposition, unknown=unknown) for index, disposition in enumerate(dispositions)),
        uncertain_reports=(),
    )


def _terminal(summary: FinsDownloadResultSummary, status: FinsResultStatus | None = None) -> FinsResultSummary:
    """构造与 typed 下载事实一致的终态。

    Args:
        summary: 完整来源结果。
        status: 显式整体终态；缺省按既有文档终态选择。

    Returns:
        唯一完整下载结果的 direct 终态。

    Raises:
        ValueError: 终态组合不符合 owner 契约时抛出。
    """

    resolved = status or (FinsResultStatus.FAILURE if summary.terminal_disposition is FinsDownloadTerminalDisposition.FAILED else FinsResultStatus.SUCCESS)
    if resolved is FinsResultStatus.CANCELLED:
        summary = replace(summary, terminal_disposition=FinsDownloadTerminalDisposition.CANCELLED)
    failure = FinsPublicFailure(FinsPublicFailureKind.EXECUTION, summary.source, None, "未取得可用来源文档", "请检查文档失败分类后重试。") if resolved is FinsResultStatus.FAILURE else None
    return FinsResultSummary(
        status=resolved, exit_code={FinsResultStatus.SUCCESS: 0, FinsResultStatus.FAILURE: 1, FinsResultStatus.CANCELLED: 130}[resolved],
        title="下载终态", details=(), error_kind=FinsErrorKind.EXECUTION if failure else None,
        error_message=None if failure is None else failure.safe_message,
        download_result=summary, failure=failure,
    )


def _event(result: FinsResultSummary, operation: FinsOperationKind = FinsOperationKind.DOWNLOAD) -> FinsEvent:
    """把合法终态交给事件 owner 校验。

    Args:
        result: direct 终态。
        operation: 显式操作类型。

    Returns:
        校验后的事件。

    Raises:
        ValueError: 操作与结果违反 owner 约束时抛出。
    """

    return FinsEvent(FinsEventType.RESULT, operation, result.title, datetime.now(timezone.utc), None, None, None, None, result)


@pytest.mark.parametrize("index", (0, 10))
@pytest.mark.parametrize("field", ("document_id", "reason_message"))
def test_result_owner_rejects_unsafe_complete_failed_projection(index: int, field: str) -> None:
    """完整失败投影必须在 result owner 构造时通过公开安全校验。

    参数：index 为第一或第十一条失败行；field 为来源 typed 允许但公开拒绝的字段。
    返回：无。
    异常：拒绝边界迟于构造或只检查前十行时抛出 AssertionError。
    """

    summary = _download_summary(failed=11)
    rows = list(summary.document_rows)
    rows[index] = replace(rows[index], **{field: "note /Users/private/file"})
    typed = replace(summary, document_rows=tuple(rows))
    assert typed.failed_count == 11 and len(typed.document_rows) == 11
    with pytest.raises(ValueError, match="contains an absolute path"):
        _terminal(typed)


@pytest.mark.parametrize("status", tuple(FinsResultStatus))
def test_accepted_result_consumers_reuse_validated_projection(
    monkeypatch: pytest.MonkeyPatch, status: FinsResultStatus,
) -> None:
    """合法终态受理后，所有消费者只读取已校验投影。

    参数：monkeypatch 禁止受理后的公共行构造；status 为成功、失败或取消终态。
    返回：无。
    异常：投影重建、原事实改变或完整失败行丢失时抛出 AssertionError。
    """

    original = _download_summary(failed=12, downloaded=1 if status is FinsResultStatus.SUCCESS else 0)
    result = _terminal(original, status)
    public = result.download
    expected = result.to_download_diagnostics_json_value()
    projection = Mock(side_effect=AssertionError("受理后不得重新构造公共行"))
    monkeypatch.setattr(direct_events, "_download_public_document", projection)
    assert result.download is public
    assert result.to_download_diagnostics_json_value() == expected
    assert expected["failed_documents"] == [_expected_row(row) for row in original.document_rows if row.disposition is FinsDownloadDocumentDisposition.FAILED]
    projection.assert_not_called()


def test_failures_after_first_ten_are_complete_and_same_source() -> None:
    """验证前十项之后的失败仍完整交付，并与有界及持久摘要同源。

    参数：无。
    返回：无（None）。
    异常：AssertionError，完整失败数量、顺序、同源字段或摘要预算不满足断言时抛出。
    """

    summary = _download_summary(skipped=11, downloaded=1, failed=12)
    result = _terminal(summary)
    assert result.download_result is summary
    public = result.download
    assert public is not None
    assert len(summary.document_rows) == 24
    assert summary.failed_count == 12
    assert len(public.document_rows) == 10 and public.omitted_count == 14
    diagnostics = result.to_download_diagnostics_json_value()
    failures = diagnostics["failed_documents"]
    assert isinstance(failures, list) and len(failures) == 12
    assert failures == [_expected_row(row) for row in summary.document_rows[12:]]
    assert diagnostics["summary"] == public.to_json_value()
    assert diagnostics["failure"] is None
    assert public.terminal_disposition is FinsDownloadTerminalDisposition.PARTIAL_FAILURE
    assert result.status is FinsResultStatus.SUCCESS and result.exit_code == 0
    durable = summary.to_json_summary(max_json_chars=FINS_DOWNLOAD_SUMMARY_MAX_JSON_CHARS)
    validate_download_json_summary(durable)
    assert len(json.dumps(durable, ensure_ascii=False, sort_keys=True)) <= FINS_DOWNLOAD_SUMMARY_MAX_JSON_CHARS
    assert "failed_documents" not in durable and "download_result" not in durable


def _expected_row(row: FinsDownloadDocumentResult) -> dict[str, str | list[str] | None]:
    """独立列出公开字段预期，避免以生产 helper 重复实现作为断言。

    Args:
        row: 原始 typed 来源事实。

    Returns:
        预期字段和值。

    Raises:
        无。
    """

    return dict(document_id=row.document_id, form_or_period=row.form_or_period, filing_date=row.filing_date, report_date=row.report_date, covered_fiscal_periods=list(row.covered_fiscal_periods), disposition=row.disposition.value, reason_category=row.reason_category, reason_message=row.reason_message, artifact_locator=None if row.artifact_locator is None else row.artifact_locator.as_posix())


@pytest.mark.parametrize("failed", (0, 1, 10, 11, 12))
@pytest.mark.parametrize("source", tuple(FinsDownloadSource))
@pytest.mark.parametrize("unknown", (False, True))
def test_complete_diagnostics_across_sources_counts_and_unknowns(failed: int, source: FinsDownloadSource, unknown: bool) -> None:
    """完整诊断在多来源、不同数量与未知元数据下保持守恒。

    参数：failed 为失败候选数；source 为下载来源；unknown 为未知报告数或元数据未知标志。
    返回：无（None）。
    异常：AssertionError，既定断言或测试前提不满足时抛出。
    """

    summary = _download_summary(failed=failed, source=source, unknown=unknown)
    result = _terminal(summary)
    public = FinsDownloadPublicSummary.from_result_summary(summary)
    value = result.to_download_diagnostics_json_value()
    assert value["failed_documents"] == [_expected_row(row) for row in summary.document_rows]
    assert public.failed_count == failed and len(public.document_rows) == min(failed, 10)
    assert public.omitted_count == max(failed - 10, 0)
    assert value["status"] == result.status.value and value["exit_code"] == result.exit_code
    assert value["failure"] == (None if result.failure is None else result.failure.to_json_value())
    assert value["scope_note"] == "诊断覆盖本次调用已返回结果的候选；取消或整体中止时，尚未返回结果的候选不作成功、跳过或失败判断。"
    if failed and unknown:
        assert summary.document_rows[0].filing_date is None
        assert summary.document_rows[0].report_date is None
        assert summary.document_rows[0].form_or_period is None
        assert summary.document_rows[0].covered_fiscal_periods == ()


def test_event_owner_rejects_download_result_missing_and_wrong_typed_value() -> None:
    """下载事件 owner 必须拒绝缺失或错误类型的完整真源。

    参数：无。
    返回：无（None）。
    异常：AssertionError，既定断言或测试前提不满足时抛出。
    """

    non_download = FinsResultSummary(FinsResultStatus.SUCCESS, 0, "操作完成", (), None, None)
    with pytest.raises(ValueError, match="requires download_result"):
        _event(non_download)
    with pytest.raises(TypeError, match="download_result"):
        replace(non_download, download_result=cast(FinsDownloadResultSummary, "invalid"))


@pytest.mark.parametrize("operation", tuple(operation for operation in FinsOperationKind if operation is not FinsOperationKind.DOWNLOAD))
def test_event_owner_rejects_download_result_for_other_operations(operation: FinsOperationKind) -> None:
    """非下载事件必须拒绝下载真源及下载诊断请求。

    参数：operation 为非下载操作类型。
    返回：无（None）。
    异常：AssertionError，既定断言或测试前提不满足时抛出。
    """

    with pytest.raises(ValueError, match="non-DOWNLOAD"):
        _event(_terminal(_download_summary()), operation)
    non_download = FinsResultSummary(FinsResultStatus.SUCCESS, 0, "操作完成", (), None, None)
    _event(non_download, operation)
    assert non_download.download_result is None and non_download.download is None
    with pytest.raises(ValueError, match="requires download_result"):
        non_download.to_download_diagnostics_json_value()


@pytest.mark.parametrize(("status", "failed", "downloaded"), ((FinsResultStatus.SUCCESS, 0, 0), (FinsResultStatus.SUCCESS, 12, 1), (FinsResultStatus.FAILURE, 12, 0), (FinsResultStatus.CANCELLED, 12, 1)))
def test_cli_delivers_one_complete_reversible_line_on_original_channel(status: FinsResultStatus, failed: int, downloaded: int) -> None:
    """CLI 在原终态通道交付唯一完整且可逆的诊断行。

    参数：status 为被测终态；failed 为失败候选数；downloaded 为下载成功候选数。
    返回：无（None）。
    异常：AssertionError，既定断言或测试前提不满足时抛出。
    """

    result = _terminal(_download_summary(failed=failed, downloaded=downloaded, unknown=True), status)
    out, err = io.StringIO(), io.StringIO()
    render_fins_direct_event(_event(result), stdout=out, stderr=err)
    chosen, other = (out, err) if status is FinsResultStatus.SUCCESS else (err, out)
    lines = [line for line in chosen.getvalue().splitlines() if line.startswith(_DIAGNOSTICS_PREFIX)]
    assert len(lines) == 1
    assert _DIAGNOSTICS_PREFIX not in other.getvalue()
    parsed = json.loads(lines[0][len(_DIAGNOSTICS_PREFIX):])
    assert parsed == result.to_download_diagnostics_json_value()
    assert len(parsed["failed_documents"]) == failed
    assert result.download is not None
    assert f'terminal_disposition="{result.download.terminal_disposition.value}"' in chosen.getvalue()
    if result.download_result is not None and result.download_result.document_rows:
        assert result.download_result.document_rows[0].document_id == _SPECIAL_ID
    assert len(_SPECIAL_ID) == 240


class _BrokenOutput(io.StringIO):
    """模拟 stdout/stderr 的真实写入失败，不吞输出异常。"""

    def write(self, text: str) -> int:
        """模拟标准流写入失败。

        参数：text 为待写入文本。
        返回：不返回。
        异常：OSError，始终模拟写入失败。
        """

        raise OSError("output unavailable")


def test_cli_preserves_output_write_error() -> None:
    """验证 CLI 不吞掉标准输出写入故障。

    参数：无。
    返回：无（None）。
    异常：AssertionError，捕获到的 OSError 文本不符合匹配预期时抛出；
        未抛出期望异常时 pytest.raises 使测试失败。
        OSError 是本测试期望并捕获的写入异常，不是成功测试向外传播的异常。
    """

    with pytest.raises(OSError, match="output unavailable"):
        render_fins_direct_event(_event(_terminal(_download_summary())), stdout=_BrokenOutput(), stderr=io.StringIO())
