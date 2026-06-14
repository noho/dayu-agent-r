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

_FAILED_FALLBACK_MESSAGE: str = "Host run failed without error message."
_LOST_FALLBACK_MESSAGE: str = "Host run lost without error message."
_CANCELLED_FALLBACK_MESSAGE: str = "Host run cancelled."
_MISSING_FINAL_ANSWER_MESSAGE: str = "Host run succeeded without final answer."


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


__all__: tuple[str, ...] = (
    "render_interactive_terminal_result",
    "render_cli_error",
    "render_prompt_terminal_result",
)
