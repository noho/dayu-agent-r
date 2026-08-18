"""CLI terminal output 测试。"""

from __future__ import annotations

import io
from dataclasses import replace
from datetime import datetime, timezone

import pytest

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
    FinsDownloadPublicDocument,
    FinsDownloadPublicSummary,
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
    FinsDownloadSource,
    FinsDownloadTerminalDisposition,
)
from dayu.host.api import HostFinalAnswerView, HostTerminalStatus
from dayu.service.entrypoint_runtime import (
    EntrypointRunTerminalResult,
    EntrypointTerminalSource,
)


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

    Returns:
        无。

    Raises:
        AssertionError: CLI 投影遗漏 typed 字段或泄漏禁止内容时抛出。
    """

    summary = FinsDownloadPublicSummary(
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
            FinsDownloadPublicDocument(
                document_id="fil-downloaded",
                form_or_period="10-K",
                filing_date="2024-08-01",
                report_date="2024-06-30",
                covered_fiscal_periods=(),
                disposition=FinsDownloadDocumentDisposition.DOWNLOADED,
                reason_category=None,
                reason_message=None,
                artifact_locator="source/AAPL/fil-downloaded",
            ),
        ),
        missing_periods=(),
        omitted_count=1,
        terminal_disposition=FinsDownloadTerminalDisposition.SUCCEEDED,
    )
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
            download=summary,
        ),
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    render_fins_direct_event(event, stdout=stdout, stderr=stderr)

    output = stdout.getvalue()
    assert "discovered=2 downloaded=1 skipped=1 rejected=0 failed=0 omitted=1" in output
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

    download = FinsDownloadPublicSummary(
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
            FinsDownloadPublicDocument(
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
        omitted_count=0,
        terminal_disposition=FinsDownloadTerminalDisposition.FAILED,
    )
    failure = FinsPublicFailure(
        kind=FinsPublicFailureKind.EXECUTION,
        source=FinsDownloadSource.SEC,
        transport_category=None,
        safe_message="下载执行失败",
        retry_hint="请稍后重试",
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
            error_kind=FinsErrorKind.EXECUTION,
            error_message=failure.safe_message,
            download=download,
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
    assert 'classification="execution"' in output
    assert 'retry_hint="请稍后重试"' in output


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

    Returns:
        无。

    Raises:
        AssertionError: 输出通道、fallback 或详情投影漂移时抛出。
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
