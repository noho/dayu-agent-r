"""CLI terminal output 测试。"""

from __future__ import annotations

import io
import asyncio
import json
from pathlib import Path, PurePosixPath
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from dayu.cli import output as cli_output
from dayu.cli.exit_codes import EXIT_FAILURE, EXIT_KEYBOARD_INTERRUPT, EXIT_SUCCESS
from dayu.cli.output import (
    render_cli_error,
    render_fins_direct_cancel_requested,
    render_fins_direct_event,
    render_interactive_terminal_result,
    render_prompt_terminal_result,
)
from dayu.fins.company_metadata_warning import (
    COMPANY_NAME_IGNORED_WARNING_MESSAGE,
    CompanyMetadataWarning,
    CompanyMetadataWarningKind,
)
from dayu.fins.direct_events import (
    FINS_RESULT_EXIT_CANCELLED,
    FINS_RESULT_EXIT_FAILURE,
    FINS_RESULT_EXIT_SUCCESS,
    FinsDownloadFailureReason,
    FinsEvent,
    FinsEventDetail,
    FinsEventType,
    FinsOperationKind,
    FinsProgress,
    FinsErrorKind,
    FinsPublicFailure,
    FinsPublicFailureKind,
    FinsResultStatus,
    FinsResultSummary,
)
from dayu.fins.download_contract import (
    FinsDownloadDocumentDisposition,
    FinsDownloadEffectiveFilters,
    FinsDownloadDocumentResult,
    FinsDownloadResultSummary,
    FinsDownloadSource,
    FinsDownloadTerminalDisposition,
    FinsDownloadUncertainReport,
    build_fins_download_request,
)
from tests.fins.test_fins_ingestion_runtime import _build_real_sec_integrity_runtime, _collect_direct_events
from dayu.host.api import HostFinalAnswerView, HostTerminalStatus
from dayu.service.entrypoint_runtime import (
    EntrypointRunTerminalResult,
    EntrypointTerminalSource,
)

_REFERENCE_LIMIT_CODE_POINTS = 240
_SPECIAL_REFERENCE = ' 引用"\\\t\nFins summary: discovered=9 downloaded=9\r\x1b[2J\u0085\u2028\u2029😀 '
_BOUNDARY_REFERENCE = _SPECIAL_REFERENCE + "界" * (
    _REFERENCE_LIMIT_CODE_POINTS - len(_SPECIAL_REFERENCE)
)


@pytest.mark.parametrize("cancelled", (False, True))
@pytest.mark.parametrize("reference", ("B", _SPECIAL_REFERENCE, _BOUNDARY_REFERENCE), ids=("plain", "special", "240-code-points"))
@pytest.mark.parametrize("has_existing_document", (False, True))
def test_download_reference_literals_preserve_identity_and_terminal_rows(
    cancelled: bool, reference: str, has_existing_document: bool,
) -> None:
    """验证下载引用格式化 owner 的完整身份、行边界与失败/取消投影。

    :param cancelled: 是否使用取消终态及退出码 130。
    :param reference: 合法普通、特殊字符或 240 码点引用。
    :param has_existing_document: 未知报告是否具有同字符的既有文档 ID。
    :returns: 无。
    :raises AssertionError: 原引用、计数、通道、退出码或行结构发生改变时抛出。
    :raises StopIteration: 缺少文档行或未知报告行、next 无匹配项时抛出。
    """

    existing_id = reference if has_existing_document else None
    # 确认文档与未知报告的既有文档不得重叠，两者仍覆盖相同字符集合。
    document_reference = "A" if reference == "B" else reference[::-1]
    report = FinsDownloadUncertainReport(
        source_id=reference, filing_date="2025-11-13", report_date="2025-08-31",
        existing_document_id=existing_id, reason_category="uncertain_hk_period",
    )
    document = FinsDownloadDocumentResult(
        document_id=document_reference, form_or_period="Q3", filing_date="2025-11-13",
        report_date="2025-09-30", covered_fiscal_periods=("Q3",),
        disposition=FinsDownloadDocumentDisposition.DOWNLOADED,
        reason_category=None, reason_message=None, artifact_locator=PurePosixPath("portfolio/0700/filings/A"),
    )
    summary = FinsDownloadResultSummary(
        source=FinsDownloadSource.HKEXNEWS, canonical_ticker="0700",
        effective_filters=FinsDownloadEffectiveFilters(
            form_types=("Q3",), start_date=None, end_date=None,
            overwrite_existing=False, rebuild_local_artifacts=False,
        ),
        discovered_count=2, downloaded_count=1, skipped_count=0,
        rejected_count=0, failed_count=0, document_rows=(document,),
        missing_periods=(), uncertain_reports=(report,),
        uncertain_count=1,
        terminal_disposition=(FinsDownloadTerminalDisposition.CANCELLED if cancelled
                              else FinsDownloadTerminalDisposition.PARTIAL_FAILURE),
    )
    failure = FinsPublicFailure(
        kind=FinsPublicFailureKind.EXECUTION, source=FinsDownloadSource.HKEXNEWS,
        transport_category=None, safe_message="财期未确认", retry_hint="请补充年度依据",
    )
    result = FinsResultSummary(
        status=FinsResultStatus.CANCELLED if cancelled else FinsResultStatus.FAILURE,
        exit_code=FINS_RESULT_EXIT_CANCELLED if cancelled else FINS_RESULT_EXIT_FAILURE,
        title="已取消" if cancelled else "财期未确认", details=(),
        error_kind=None if cancelled else FinsErrorKind.EXECUTION,
        error_message=None if cancelled else failure.safe_message,
        download_result=summary, failure=None if cancelled else failure,
    )
    event = FinsEvent(
        event_type=FinsEventType.RESULT, operation_kind=FinsOperationKind.DOWNLOAD,
        message=result.title, emitted_at=datetime.now(timezone.utc), ticker="0700",
        filing_kind=None, document_label=None, progress=None, result=result,
    )
    assert result.download is not None
    original = result.download.to_json_value()
    out, err = io.StringIO(), io.StringIO()
    render_fins_direct_event(event, stdout=out, stderr=err)
    text = err.getvalue()
    assert out.getvalue() == ""
    assert result.status is (FinsResultStatus.CANCELLED if cancelled else FinsResultStatus.FAILURE)
    assert result.exit_code == (EXIT_KEYBOARD_INTERRUPT if cancelled else EXIT_FAILURE)
    assert text.startswith("Fins cancelled:" if cancelled else "Fins failure:")
    diagnostic_lines = [line for line in text.splitlines() if line.startswith("Fins download diagnostics: ")]
    assert len(diagnostic_lines) == 1
    assert json.loads(diagnostic_lines[0].removeprefix("Fins download diagnostics: ")) == result.to_download_diagnostics_json_value()
    assert sum(line.startswith("Fins summary:") for line in text.splitlines()) == 1
    assert "discovered=2 downloaded=1 skipped=0 rejected=0 failed=0 uncertain=1 omitted_uncertain=0 omitted=0" in text
    assert not any(character in text for character in ("\r", "\x1b", "\u0085", "\u2028", "\u2029"))
    document_line = next(line for line in text.splitlines() if line.startswith("Fins document:"))
    unknown_line = next(line for line in text.splitlines() if line.startswith("Fins uncertain report:"))
    document_literal = document_line.split("document_id=", 1)[1].split(" form_or_period=", 1)[0]
    source_literal = unknown_line.split("source_id=", 1)[1].split(" existing_document_id=", 1)[0]
    existing_literal = unknown_line.split("existing_document_id=", 1)[1].split(" filing_date=", 1)[0]
    assert document_literal.startswith('"') and document_literal.endswith('"')
    assert source_literal.startswith('"') and source_literal.endswith('"')
    assert json.loads(document_literal) == document_reference
    assert json.loads(source_literal) == reference
    if has_existing_document:
        assert existing_literal == source_literal
        assert json.loads(existing_literal) == existing_id
    else:
        assert existing_literal == "-"
    assert result.download.to_json_value() == original
    assert document.document_id == document_reference and report.source_id == reference
    assert report.existing_document_id == existing_id
    if reference == _BOUNDARY_REFERENCE:
        assert len(json.loads(source_literal)) == _REFERENCE_LIMIT_CODE_POINTS


@pytest.mark.parametrize(
    "cancel_reason",
    (
        None,
        "cli_sigint",
        "active_cancel_watchdog_closeout",
        "future_internal_cancel_reason",
    ),
)
def test_prompt_terminal_result_hides_every_internal_cancel_reason(
    cancel_reason: str | None,
) -> None:
    """prompt cancel 输出不泄漏任何 Host 内部 reason。

    :param cancel_reason: 测试注入的 Host terminal cancel reason。
    :returns: ``None``。
    :raises AssertionError: UI 输出或退出码不符合公共投影 contract 时抛出。
    """

    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = render_prompt_terminal_result(
        _cancelled_terminal(cancel_reason),
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "Cancelled.\n"
    if cancel_reason is not None:
        assert cancel_reason not in stderr.getvalue()


@pytest.mark.parametrize(
    "cancel_reason",
    (
        None,
        "cli_sigint",
        "active_cancel_watchdog_closeout",
        "future_internal_cancel_reason",
    ),
)
def test_interactive_terminal_result_hides_every_internal_cancel_reason(
    cancel_reason: str | None,
) -> None:
    """interactive cancel 输出不泄漏任何 Host 内部 reason。

    :param cancel_reason: 测试注入的 Host terminal cancel reason。
    :returns: ``None``。
    :raises AssertionError: UI 输出或退出码不符合公共投影 contract 时抛出。
    """

    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = render_interactive_terminal_result(
        _cancelled_terminal(cancel_reason),
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == EXIT_SUCCESS
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "Cancelled.\n"
    if cancel_reason is not None:
        assert cancel_reason not in stderr.getvalue()


def test_fins_download_cli_mechanically_projects_typed_public_summary() -> None:
    """CLI 应只展示 runtime 给出的 typed summary，不扫描文件或推断 raw 字段。

    参数：无。
    返回：无（None）。
    异常：AssertionError，既定断言或测试前提不满足时抛出。
    """

    summary = FinsDownloadResultSummary(
        source=FinsDownloadSource.SEC,
        canonical_ticker="AAPL",
        effective_filters=FinsDownloadEffectiveFilters(
            form_types=("10-K",),
            start_date="2024-01-01",
            end_date="2024-12-31",
            overwrite_existing=False,
            rebuild_local_artifacts=False,
        ),
        discovered_count=2,
        downloaded_count=1,
        skipped_count=1,
        rejected_count=0,
        failed_count=0,
        document_rows=(
            FinsDownloadDocumentResult(
                document_id="fil-downloaded",
                form_or_period="10-K",
                filing_date="2024-08-01",
                report_date="2024-06-30",
                covered_fiscal_periods=(),
                disposition=FinsDownloadDocumentDisposition.DOWNLOADED,
                reason_category=None,
                reason_message=None,
                artifact_locator=PurePosixPath("source/AAPL/fil-downloaded"),
            ),
            FinsDownloadDocumentResult(
                document_id="fil-skipped", form_or_period="10-K", filing_date=None,
                report_date=None, covered_fiscal_periods=(),
                disposition=FinsDownloadDocumentDisposition.SKIPPED,
                reason_category="integrity_complete", reason_message="本地来源完整，跳过下载",
                artifact_locator=None,
            ),
        ),
        missing_periods=(),
        terminal_disposition=FinsDownloadTerminalDisposition.SUCCEEDED,
     uncertain_reports=(), uncertain_count=0,)
    event = FinsEvent(
        event_type=FinsEventType.RESULT,
        operation_kind=FinsOperationKind.DOWNLOAD,
        message="下载完成",
        emitted_at=datetime.now(timezone.utc),
        ticker="AAPL",
        filing_kind=None,
        document_label=None,
        progress=None,
        result=FinsResultSummary(
            status=FinsResultStatus.SUCCESS,
            exit_code=FINS_RESULT_EXIT_SUCCESS,
            title="下载完成",
            details=(),
            error_kind=None,
            error_message=None,
            download_result=summary,
        ),
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    render_fins_direct_event(event, stdout=stdout, stderr=stderr)

    output = stdout.getvalue()
    assert "discovered=2 downloaded=1 skipped=1 rejected=0 failed=0 uncertain=0 omitted_uncertain=0 omitted=0" in output
    assert 'artifact_locator="source/AAPL/fil-downloaded"' in output
    assert "covered_fiscal_periods=[]" in output
    assert "https://" not in output
    assert "/Users/" not in output
    assert stderr.getvalue() == ""


def test_fins_download_failure_projects_typed_rows_missing_periods_and_recovery() -> None:
    """CLI 下载失败应机械展示 typed 行、缺失期间与恢复建议。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: failure public object 被省略或进入错误输出通道时抛出。
    """

    download = FinsDownloadResultSummary(
        source=FinsDownloadSource.SEC,
        canonical_ticker="AAPL",
        effective_filters=FinsDownloadEffectiveFilters(
            form_types=("10-K",),
            start_date=None,
            end_date=None,
            overwrite_existing=False,
            rebuild_local_artifacts=False,
        ),
        discovered_count=1,
        downloaded_count=0,
        skipped_count=0,
        rejected_count=0,
        failed_count=1,
        document_rows=(
            FinsDownloadDocumentResult(
                document_id="fil-failed",
                form_or_period="10-K",
                filing_date=None,
                report_date=None,
                covered_fiscal_periods=(),
                disposition=FinsDownloadDocumentDisposition.FAILED,
                reason_category="provider",
                reason_message="来源暂时不可用",
                artifact_locator=None,
            ),
        ),
        missing_periods=("FY2024",),
        terminal_disposition=FinsDownloadTerminalDisposition.FAILED,
     uncertain_reports=(), uncertain_count=0,)
    failure = FinsPublicFailure(
        kind=FinsPublicFailureKind.STORAGE,
        source=FinsDownloadSource.SEC,
        transport_category=None,
        safe_message="本地来源完整性预检失败",
        retry_hint="请检查并修复工作区来源状态后重试",
        reason_code=FinsDownloadFailureReason.UNSAFE_PUBLICATION,
    )
    event = FinsEvent(
        event_type=FinsEventType.RESULT,
        operation_kind=FinsOperationKind.DOWNLOAD,
        message="下载失败",
        emitted_at=datetime.now(timezone.utc),
        ticker="AAPL",
        filing_kind=None,
        document_label=None,
        progress=None,
        result=FinsResultSummary(
            status=FinsResultStatus.FAILURE,
            exit_code=FINS_RESULT_EXIT_FAILURE,
            title="下载失败",
            details=(),
            error_kind=FinsErrorKind.STORAGE,
            error_message=failure.safe_message,
            download_result=download,
            failure=failure,
        ),
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    render_fins_direct_event(event, stdout=stdout, stderr=stderr)

    output = stderr.getvalue()
    assert stdout.getvalue() == ""
    assert 'reason_category="provider"' in output
    assert 'reason="来源暂时不可用"' in output
    assert 'Fins missing periods: "FY2024"' in output
    assert 'classification="storage"' in output
    assert 'reason_code="unsafe_publication"' in output
    assert failure.to_json_value()["reason_code"] == "unsafe_publication"
    assert 'retry_hint="请检查并修复工作区来源状态后重试"' in output
    assert "请使用 --log-file PATH 重试并查看日志" not in output

    execution_failure = FinsPublicFailure(
        kind=FinsPublicFailureKind.EXECUTION,
        source=FinsDownloadSource.SEC,
        transport_category=None,
        safe_message="下载执行失败",
        retry_hint="请保存脱敏诊断并排查失败原因后重试。",
    )
    assert event.result is not None
    execution_event = replace(
        event,
        result=replace(
            event.result,
            error_kind=FinsErrorKind.EXECUTION,
            error_message=execution_failure.safe_message,
            failure=execution_failure,
        ),
    )
    execution_stderr = io.StringIO()
    render_fins_direct_event(execution_event, stdout=io.StringIO(), stderr=execution_stderr)
    assert 'classification="execution"' in execution_stderr.getvalue()
    assert 'reason_code="-"' in execution_stderr.getvalue()
    assert execution_stderr.getvalue().count("请使用 --log-file PATH 重试并查看日志") == 1


@pytest.mark.parametrize(
    ("hint", "expected_hint"),
    (
        ("请稍后重试。", '"请稍后重试。"'),
        (
            "提" * cli_output._FINS_TEXT_MAX_CHARS,
            '"' + "提" * cli_output._FINS_TEXT_MAX_CHARS + '"',
        ),
        (
            "提" * (cli_output._FINS_TEXT_MAX_CHARS + 1),
            '"' + "提" * (cli_output._FINS_TEXT_MAX_CHARS - len("...")) + '..."',
        ),
        (
            "提" * (cli_output._FINS_TEXT_MAX_CHARS * 2),
            '"' + "提" * (cli_output._FINS_TEXT_MAX_CHARS - len("...")) + '..."',
        ),
    ),
    ids=("short", "120", "121", "240"),
)
def test_fins_download_failure_preserves_cli_text_bound_and_public_json(
    hint: str,
    expected_hint: str,
) -> None:
    """真实失败渲染保持 CLI 显示上界和完整公共恢复建议。

    :param hint: 合法短文本、显示上界及超过显示上界的公共恢复建议。
    :param expected_hint: 按既有显示合同独立构造的带引号期望文本。
    :returns: ``None``。
    :raises AssertionError: 有界显示、空单元格、渠道或公共 JSON 发生漂移时抛出。
    :raises StopIteration: 缺少失败详情行、next 无匹配项时抛出。
    """

    failure = FinsPublicFailure(
        kind=FinsPublicFailureKind.EXECUTION,
        source=FinsDownloadSource.SEC,
        transport_category=None,
        safe_message="下载执行失败",
        retry_hint=hint,
    )
    expected_public = {
        "classification": "execution",
        "source": "sec",
        "transport_category": None,
        "message": "下载执行失败",
        "retry_hint": hint,
        "reason_code": None,
    }
    assert failure.to_json_value() == expected_public
    event = FinsEvent(
        event_type=FinsEventType.RESULT,
        operation_kind=FinsOperationKind.DOWNLOAD,
        message="下载失败",
        emitted_at=datetime.now(timezone.utc),
        ticker="AAPL",
        filing_kind=None,
        document_label=None,
        progress=None,
        result=FinsResultSummary(
            status=FinsResultStatus.FAILURE,
            exit_code=FINS_RESULT_EXIT_FAILURE,
            title="下载失败",
            details=(),
            error_kind=FinsErrorKind.EXECUTION,
            error_message=failure.safe_message,
            download_result=FinsDownloadResultSummary(
                source=FinsDownloadSource.SEC,
                canonical_ticker="AAPL",
                effective_filters=FinsDownloadEffectiveFilters(
                    form_types=("10-K",),
                    start_date=None,
                    end_date=None,
                    overwrite_existing=False,
                    rebuild_local_artifacts=False,
                ),
                discovered_count=1,
                downloaded_count=0,
                skipped_count=0,
                rejected_count=0,
                failed_count=1,
                document_rows=(FinsDownloadDocumentResult(
                    document_id="failed", form_or_period=None, filing_date=None, report_date=None,
                    covered_fiscal_periods=(), disposition=FinsDownloadDocumentDisposition.FAILED,
                    reason_category="execution", reason_message="下载执行失败", artifact_locator=None,
                ),),
                missing_periods=(),
                terminal_disposition=FinsDownloadTerminalDisposition.FAILED,
             uncertain_reports=(), uncertain_count=0,),
            failure=failure,
        ),
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    render_fins_direct_event(event, stdout=stdout, stderr=stderr)

    assert stdout.getvalue() == ""
    lines = stderr.getvalue().splitlines()
    detail = next(line for line in lines if line.startswith("Fins failure detail: "))
    assert detail == (
        'Fins failure detail: classification="execution" source="sec" '
        'transport="-" reason_code="-" retry_hint=' + expected_hint
    )
    assert lines.count("请使用 --log-file PATH 重试并查看日志") == 1
    assert failure.to_json_value() == expected_public


def test_prompt_and_interactive_render_non_cancelled_terminal_matrix() -> None:
    """prompt/interactive 对成功、缺回答、失败与 lost 使用固定公共投影。

    Returns:
        无。

    Raises:
        AssertionError: 终态文本或退出码漂移时抛出。
    """

    answer = HostFinalAnswerView(
        content="final answer",
        filtered=False,
        degraded=False,
        finish_reason="stop",
        terminal_status=HostTerminalStatus.SUCCEEDED,
    )
    success = replace(
        _cancelled_terminal(None),
        terminal_status=HostTerminalStatus.SUCCEEDED,
        final_answer=answer,
        cancel_reason=None,
    )
    missing_answer = replace(success, final_answer=None)
    failed = replace(
        _cancelled_terminal(None),
        terminal_status=HostTerminalStatus.FAILED,
        error_message="public failure",
        cancel_reason=None,
    )
    lost = replace(
        _cancelled_terminal(None),
        terminal_status=HostTerminalStatus.LOST,
        error_message=None,
        cancel_reason=None,
    )

    stdout = io.StringIO()
    stderr = io.StringIO()
    assert render_prompt_terminal_result(success, stdout=stdout, stderr=stderr) == EXIT_SUCCESS
    assert stdout.getvalue() == "final answer\n"
    assert render_prompt_terminal_result(missing_answer, stdout=stdout, stderr=stderr) == EXIT_FAILURE
    assert render_prompt_terminal_result(failed, stdout=stdout, stderr=stderr) == EXIT_FAILURE
    assert render_prompt_terminal_result(lost, stdout=stdout, stderr=stderr) == EXIT_FAILURE
    assert render_interactive_terminal_result(success, stdout=stdout, stderr=stderr) == EXIT_SUCCESS
    assert render_interactive_terminal_result(missing_answer, stdout=stdout, stderr=stderr) == EXIT_FAILURE
    assert render_interactive_terminal_result(failed, stdout=stdout, stderr=stderr) == EXIT_SUCCESS
    assert render_interactive_terminal_result(lost, stdout=stdout, stderr=stderr) == EXIT_FAILURE


def test_fins_success_warning_preserves_stdout_and_writes_each_message_to_stderr() -> None:
    """CLI 成功摘要应保持 stdout 不变，并把 typed warning 逐条写 stderr。

    Args:
        无。

    Returns:
        无。

    Raises:
        AssertionError: warning 改写摘要、通道或规范文案时抛出。
    """

    summary = FinsResultSummary(
        status=FinsResultStatus.SUCCESS,
        exit_code=FINS_RESULT_EXIT_SUCCESS,
        title="上传完成",
        details=(FinsEventDetail(label="stored files", value="1"),),
        error_kind=None,
        error_message=None,
    )
    event = FinsEvent(
        event_type=FinsEventType.RESULT,
        operation_kind=FinsOperationKind.UPLOAD_FILING,
        message="上传完成",
        emitted_at=datetime.now(timezone.utc),
        ticker="AAPL",
        filing_kind="10-K",
        document_label=None,
        progress=None,
        result=summary,
    )
    baseline_stdout = io.StringIO()
    baseline_stderr = io.StringIO()
    warned_stdout = io.StringIO()
    warned_stderr = io.StringIO()

    render_fins_direct_event(event, stdout=baseline_stdout, stderr=baseline_stderr)
    render_fins_direct_event(
        replace(
            event,
            result=replace(
                summary,
                warnings=(
                    CompanyMetadataWarning(
                        kind=CompanyMetadataWarningKind.COMPANY_NAME_IGNORED,
                        message=COMPANY_NAME_IGNORED_WARNING_MESSAGE,
                    ),
                ),
            ),
        ),
        stdout=warned_stdout,
        stderr=warned_stderr,
    )

    assert warned_stdout.getvalue() == baseline_stdout.getvalue()
    assert baseline_stderr.getvalue() == ""
    assert warned_stderr.getvalue() == f"{COMPANY_NAME_IGNORED_WARNING_MESSAGE}\n"


def test_fins_renderer_covers_progress_failure_cancel_and_error_helpers() -> None:
    """Fins renderer 的 progress、failure、cancel 与显式错误 helper 保持分流。

    参数：无。
    返回：无（None）。
    异常：AssertionError，既定断言或测试前提不满足时抛出。
    """

    progress_event = FinsEvent(
        event_type=FinsEventType.PROGRESS,
        operation_kind=FinsOperationKind.DOWNLOAD,
        message="downloading",
        emitted_at=datetime.now(timezone.utc),
        ticker="0005",
        filing_kind="Q4",
        document_label="fil-q4",
        progress=FinsProgress(stage="pdf", completed_units=1, total_units=2),
        result=None,
    )
    failed_summary = FinsResultSummary(
        status=FinsResultStatus.FAILURE,
        exit_code=FINS_RESULT_EXIT_FAILURE,
        title="failed",
        details=(FinsEventDetail(label="reason code", value="provider"),),
        error_kind=FinsErrorKind.PROVIDER,
        error_message=None,
    )
    failed_event = replace(
        progress_event,
        event_type=FinsEventType.RESULT,
        message="failed",
        operation_kind=FinsOperationKind.PREPROCESS,
        progress=None,
        result=failed_summary,
    )
    cancelled_event = replace(
        failed_event,
        message="cancelled",
        result=FinsResultSummary(
            status=FinsResultStatus.CANCELLED,
            exit_code=FINS_RESULT_EXIT_CANCELLED,
            title="cancelled",
            details=(),
            error_kind=FinsErrorKind.CANCELLED,
            error_message=None,
        ),
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    render_fins_direct_event(progress_event, stdout=stdout, stderr=stderr)
    render_fins_direct_event(failed_event, stdout=stdout, stderr=stderr)
    render_fins_direct_event(cancelled_event, stdout=stdout, stderr=stderr)
    render_fins_direct_cancel_requested(stderr=stderr)
    render_cli_error("usage failure", stderr=stderr)

    assert 'operation="download"' in stdout.getvalue()
    assert 'stage="pdf"' in stdout.getvalue()
    assert "Fins operation failed." in stderr.getvalue()
    assert 'reason_code="provider"' in stderr.getvalue()
    assert "Fins cancelled:" in stderr.getvalue()
    assert "Fins operation cancel requested." in stderr.getvalue()
    assert "usage failure" in stderr.getvalue()


def test_fins_cancel_without_download_keeps_original_prompt_and_channel() -> None:
    """无下载摘要的取消保持原展示，不输出普通 details。

    参数：无。
    返回：无（None）。
    异常：AssertionError，取消提示、stderr 通道或空下载展示不满足断言时抛出。
    """
    result = FinsResultSummary(
        status=FinsResultStatus.CANCELLED, exit_code=FINS_RESULT_EXIT_CANCELLED,
        title="cancelled", details=(FinsEventDetail(label="private-detail", value="unshown-detail"),),
        error_kind=FinsErrorKind.CANCELLED, error_message=None,
    )
    event = FinsEvent(
        event_type=FinsEventType.RESULT, operation_kind=FinsOperationKind.PREPROCESS,
        message="cancelled", emitted_at=datetime.now(timezone.utc), ticker="0700",
        filing_kind=None, document_label=None, progress=None, result=result,
    )
    stdout, stderr = io.StringIO(), io.StringIO()
    render_fins_direct_event(event, stdout=stdout, stderr=stderr)
    assert result.exit_code == 130 and stdout.getvalue() == ""
    assert stderr.getvalue().startswith("Fins cancelled:")
    assert "Fins summary:" not in stderr.getvalue()
    assert "unshown-detail" not in stderr.getvalue()


def _cancelled_terminal(cancel_reason: str | None) -> EntrypointRunTerminalResult:
    """构造 cancelled terminal result。

    :param cancel_reason: terminal cancel reason。
    :returns: Service terminal result DTO。
    :raises Exception: 不主动抛出异常。
    """

    return EntrypointRunTerminalResult(
        source=EntrypointTerminalSource.LIVE_EVENT,
        run_id="run-1",
        session_id="session-1",
        event_sequence=1,
        dedupe_key="terminal-1",
        terminal_event_id="terminal-1",
        terminal_status=HostTerminalStatus.CANCELLED,
        final_answer=None,
        error_message=None,
        cancel_reason=cancel_reason,
        watcher_failure_message=None,
    )


@pytest.mark.parametrize("scenario", ("postrepair", "churn"))
def test_download_integrity_failure_renders_public_projection(tmp_path: Path, scenario: str) -> None:
    """真实 SEC RESULT 的失败字段由 CLI 机械 JSON 展示，渠道与摘要保全。

    参数：tmp_path 为隔离根；scenario 为真实状态。返回：无。异常：断言失败抛出 AssertionError。
    """
    runtime, _executor, _pipeline = _build_real_sec_integrity_runtime(tmp_path, scenario)
    request = build_fins_download_request(ticker="AAPL", form_types=("10-K", "6-K"),
        start="2025-01-01", end="2025-12-31", overwrite_existing=scenario == "churn")
    events = asyncio.run(_collect_direct_events(runtime.download(request)))
    terminal = events[-1]
    assert terminal.result is not None and terminal.result.failure is not None
    assert terminal.result.download is not None
    projection = terminal.result.failure.to_json_value()
    stdout, stderr = io.StringIO(), io.StringIO()
    render_fins_direct_event(terminal, stdout=stdout, stderr=stderr)
    rendered = stderr.getvalue()
    assert stdout.getvalue() == ""
    for key, label in (("classification", "classification"), ("source", "source"),
        ("reason_code", "reason_code"), ("retry_hint", "retry_hint")):
        assert f"{label}={json.dumps(projection[key], ensure_ascii=False)}" in rendered
    message = projection["message"]
    assert isinstance(message, str) and message in rendered
    assert "downloaded=1" in rendered
    assert "failed=0" in rendered if scenario == "postrepair" else "failed=1" in rendered
    assert "请使用 --log-file" not in rendered
    assert "/Users/" not in rendered and "://" not in rendered
    print(rendered)
