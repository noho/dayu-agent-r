"""Dayu CLI 输出格式化 helper。

本模块只处理终端展示文本与退出码映射，不判断 Host 状态真源，也不读取业务
存储。
"""

from __future__ import annotations

from typing import TextIO
import sys

from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
)
from dayu.host.api import HostTerminalStatus
from dayu.service.entrypoint_runtime import EntrypointRunTerminalResult
from dayu.service.fins_direct import FinsDirectTerminalResult
from dayu.fins.ingestion_runtime import FinsIngestionJobStatus

_FAILED_FALLBACK_MESSAGE: str = "Host run failed without error message."
_LOST_FALLBACK_MESSAGE: str = "Host run lost without error message."
_CANCELLED_FALLBACK_MESSAGE: str = "Host run cancelled."
_MISSING_FINAL_ANSWER_MESSAGE: str = "Host run succeeded without final answer."
_FINS_CANCEL_REQUESTED_TEMPLATE: str = "Fins job cancel requested: {job_id}"
_FINS_LOCAL_EXIT_AFTER_CANCEL_TEMPLATE: str = (
    "Fins job cancel already requested; local process exiting: {job_id}"
)
_FINS_FAILED_FALLBACK_TEMPLATE: str = "Fins job failed: {job_id}"
_FINS_CANCELLED_TEMPLATE: str = "Fins job cancelled: {job_id}"
_FINS_SUCCEEDED_TEMPLATE: str = "Fins job succeeded: {job_id}"
_FINS_FAILURE_MESSAGE_KEY: str = "message"


def render_prompt_terminal_result(
    result: EntrypointRunTerminalResult,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """输出 prompt Run 终态并返回 CLI 退出码。

    :param result: Service helper 返回的 Host terminal result。
    :param stdout: 标准输出流；``None`` 表示使用当前 ``sys.stdout``。
    :param stderr: 标准错误流；``None`` 表示使用当前 ``sys.stderr``。
    :returns: CLI 退出码。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    effective_stdout = sys.stdout if stdout is None else stdout
    effective_stderr = sys.stderr if stderr is None else stderr
    if result.terminal_status is HostTerminalStatus.SUCCEEDED:
        if result.final_answer is None:
            print(_MISSING_FINAL_ANSWER_MESSAGE, file=effective_stderr)
            return EXIT_FAILURE
        print(result.final_answer.content, file=effective_stdout)
        return EXIT_SUCCESS
    if result.terminal_status is HostTerminalStatus.CANCELLED:
        print(
            result.cancel_reason or _CANCELLED_FALLBACK_MESSAGE,
            file=effective_stderr,
        )
        return EXIT_KEYBOARD_INTERRUPT
    if result.terminal_status is HostTerminalStatus.LOST:
        print(result.error_message or _LOST_FALLBACK_MESSAGE, file=effective_stderr)
        return EXIT_FAILURE
    print(result.error_message or _FAILED_FALLBACK_MESSAGE, file=effective_stderr)
    return EXIT_FAILURE


def render_interactive_terminal_result(
    result: EntrypointRunTerminalResult,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """输出 interactive 单轮终态并返回是否继续交互的退出码。

    :param result: Service helper 返回的 Host terminal result。
    :param stdout: 标准输出流；``None`` 表示使用当前 ``sys.stdout``。
    :param stderr: 标准错误流；``None`` 表示使用当前 ``sys.stderr``。
    :returns: ``0`` 表示可回到输入态；``1`` 表示 fatal 终态应退出。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    effective_stdout = sys.stdout if stdout is None else stdout
    effective_stderr = sys.stderr if stderr is None else stderr
    if result.terminal_status is HostTerminalStatus.SUCCEEDED:
        if result.final_answer is None:
            print(_MISSING_FINAL_ANSWER_MESSAGE, file=effective_stderr)
            return EXIT_FAILURE
        print(result.final_answer.content, file=effective_stdout)
        return EXIT_SUCCESS
    if result.terminal_status is HostTerminalStatus.FAILED:
        print(result.error_message or _FAILED_FALLBACK_MESSAGE, file=effective_stderr)
        return EXIT_SUCCESS
    if result.terminal_status is HostTerminalStatus.CANCELLED:
        print(
            result.cancel_reason or _CANCELLED_FALLBACK_MESSAGE,
            file=effective_stderr,
        )
        return EXIT_SUCCESS
    print(result.error_message or _LOST_FALLBACK_MESSAGE, file=effective_stderr)
    return EXIT_FAILURE


def render_cli_error(message: str, *, stderr: TextIO | None = None) -> None:
    """输出 CLI 错误消息。

    :param message: 已归一化的错误消息。
    :param stderr: 标准错误流；``None`` 表示使用当前 ``sys.stderr``。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    print(message, file=sys.stderr if stderr is None else stderr)


def render_fins_direct_terminal_result(
    result: FinsDirectTerminalResult,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """输出 Fins direct job 终态并返回 CLI 退出码。

    :param result: Service helper 返回的 Fins direct terminal result。
    :param stdout: 标准输出流；``None`` 表示使用当前 ``sys.stdout``。
    :param stderr: 标准错误流；``None`` 表示使用当前 ``sys.stderr``。
    :returns: CLI 退出码。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    effective_stdout = sys.stdout if stdout is None else stdout
    effective_stderr = sys.stderr if stderr is None else stderr
    if result.status is FinsIngestionJobStatus.SUCCEEDED:
        print(
            _FINS_SUCCEEDED_TEMPLATE.format(job_id=result.job_id),
            file=effective_stdout,
        )
        return result.exit_code
    if result.status is FinsIngestionJobStatus.CANCELLED:
        print(
            _FINS_CANCELLED_TEMPLATE.format(job_id=result.job_id),
            file=effective_stderr,
        )
        return result.exit_code
    print(
        _failure_message_or_fallback(result),
        file=effective_stderr,
    )
    return result.exit_code


def render_fins_direct_cancel_requested(
    job_id: str,
    *,
    stderr: TextIO | None = None,
) -> None:
    """输出 Fins direct job 已请求取消的提示。

    :param job_id: Fins ingestion job id。
    :param stderr: 标准错误流；``None`` 表示使用当前 ``sys.stderr``。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    print(
        _FINS_CANCEL_REQUESTED_TEMPLATE.format(job_id=job_id),
        file=sys.stderr if stderr is None else stderr,
    )


def render_fins_direct_local_exit_after_cancel(
    job_id: str,
    *,
    stderr: TextIO | None = None,
) -> None:
    """输出第二次 SIGINT 后本地退出的提示。

    :param job_id: Fins ingestion job id。
    :param stderr: 标准错误流；``None`` 表示使用当前 ``sys.stderr``。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    print(
        _FINS_LOCAL_EXIT_AFTER_CANCEL_TEMPLATE.format(job_id=job_id),
        file=sys.stderr if stderr is None else stderr,
    )


def _failure_message_or_fallback(result: FinsDirectTerminalResult) -> str:
    """读取 Fins direct 失败摘要中的用户可见错误。

    :param result: Fins direct terminal result。
    :returns: 失败消息。
    :raises Exception: 不主动抛出异常。
    """

    raw_message = result.failure_summary.get(_FINS_FAILURE_MESSAGE_KEY)
    if isinstance(raw_message, str) and raw_message.strip() != "":
        return raw_message
    return _FINS_FAILED_FALLBACK_TEMPLATE.format(job_id=result.job_id)


__all__: tuple[str, ...] = (
    "render_interactive_terminal_result",
    "render_cli_error",
    "render_fins_direct_cancel_requested",
    "render_fins_direct_local_exit_after_cancel",
    "render_fins_direct_terminal_result",
    "render_prompt_terminal_result",
)
