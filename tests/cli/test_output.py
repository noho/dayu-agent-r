"""CLI terminal output 测试。"""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pytest

from dayu.cli.exit_codes import EXIT_KEYBOARD_INTERRUPT, EXIT_SUCCESS
from dayu.cli.output import (
    render_fins_direct_event,
    render_interactive_terminal_result,
    render_prompt_terminal_result,
)
from dayu.fins.direct_events import (
    FINS_RESULT_EXIT_SUCCESS,
    FinsDownloadPublicDocument,
    FinsDownloadPublicSummary,
    FinsEvent,
    FinsEventType,
    FinsOperationKind,
    FinsResultStatus,
    FinsResultSummary,
)
from dayu.fins.download_contract import (
    FinsDownloadDocumentDisposition,
    FinsDownloadEffectiveFilters,
    FinsDownloadSource,
    FinsDownloadTerminalDisposition,
)
from dayu.host.api import HostTerminalStatus
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
    assert "https://" not in output
    assert "/Users/" not in output
    assert stderr.getvalue() == ""


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
