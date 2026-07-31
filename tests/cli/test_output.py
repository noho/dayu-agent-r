"""CLI terminal output 测试。"""

from __future__ import annotations

import io

import pytest

from dayu.cli.exit_codes import EXIT_KEYBOARD_INTERRUPT, EXIT_SUCCESS
from dayu.cli.output import (
    render_interactive_terminal_result,
    render_prompt_terminal_result,
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
