"""CLI terminal output 测试。"""

from __future__ import annotations

import io

from dayu.cli.exit_codes import EXIT_KEYBOARD_INTERRUPT, EXIT_SUCCESS
from dayu.cli.host_context import CLI_SIGINT_REASON
from dayu.cli.output import (
    render_interactive_terminal_result,
    render_prompt_terminal_result,
)
from dayu.host.api import HostTerminalStatus
from dayu.service.entrypoint_runtime import (
    EntrypointRunTerminalResult,
    EntrypointTerminalSource,
)


def test_prompt_terminal_result_hides_internal_sigint_reason() -> None:
    """prompt cancel 输出不泄漏内部 ``cli_sigint`` reason。"""

    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = render_prompt_terminal_result(
        _cancelled_terminal(CLI_SIGINT_REASON),
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == EXIT_KEYBOARD_INTERRUPT
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "Cancelled.\n"


def test_interactive_terminal_result_hides_internal_sigint_reason() -> None:
    """interactive cancel 输出不泄漏内部 ``cli_sigint`` reason。"""

    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = render_interactive_terminal_result(
        _cancelled_terminal(CLI_SIGINT_REASON),
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == EXIT_SUCCESS
    assert stdout.getvalue() == ""
    assert stderr.getvalue() == "Cancelled.\n"


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
