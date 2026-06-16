"""Dayu CLI 输出格式化 helper。

本模块只处理终端展示文本与退出码映射，不判断 Host 状态真源，也不读取业务
存储。
"""

from __future__ import annotations

import json
import re
import sys
from typing import Final, TextIO

from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
)
from dayu.fins.direct_events import (
    FinsEvent,
    FinsEventDetail,
    FinsEventType,
    FinsResultStatus,
    FinsResultSummary,
)
from dayu.host.api import HostTerminalStatus
from dayu.service.entrypoint_runtime import EntrypointRunTerminalResult

_FAILED_FALLBACK_MESSAGE: str = "Host run failed without error message."
_LOST_FALLBACK_MESSAGE: str = "Host run lost without error message."
_CANCELLED_FALLBACK_MESSAGE: str = "Host run cancelled."
_MISSING_FINAL_ANSWER_MESSAGE: str = "Host run succeeded without final answer."
_FINS_CANCEL_REQUESTED_MESSAGE: str = "Fins operation cancel requested."
_FINS_LOCAL_EXIT_AFTER_CANCEL_MESSAGE: str = (
    "Fins operation already cancelling; local process exiting."
)
_FINS_FAILED_FALLBACK_MESSAGE: str = "Fins operation failed."
_FINS_EVENT_PROGRESS_PREFIX: Final[str] = "Fins progress"
_FINS_EVENT_SUMMARY_PREFIX: Final[str] = "Fins summary"
_FINS_EVENT_FAILURE_PREFIX: Final[str] = "Fins failure"
_FINS_EVENT_CANCELLED_PREFIX: Final[str] = "Fins cancelled"
_FINS_EVENT_SUCCEEDED_PREFIX: Final[str] = "Fins succeeded"
_FINS_SUMMARY_MAX_ITEMS: Final[int] = 8
_FINS_TEXT_MAX_CHARS: Final[int] = 120
_FINS_TRUNCATED_SUFFIX: Final[str] = "..."


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


def render_fins_direct_event(
    event: FinsEvent,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    """输出 Fins direct 事件。

    :param event: Service direct stream 产出的 Fins direct 事件。
    :param stdout: 标准输出流；``None`` 表示使用当前 ``sys.stdout``。
    :param stderr: 标准错误流；``None`` 表示使用当前 ``sys.stderr``。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    effective_stdout = sys.stdout if stdout is None else stdout
    effective_stderr = sys.stderr if stderr is None else stderr
    if event.event_type is FinsEventType.PROGRESS:
        print(_fins_event_line(_FINS_EVENT_PROGRESS_PREFIX, event), file=effective_stdout)
        return

    if event.result is None:
        raise ValueError("RESULT event missing result summary")

    if event.result.status is FinsResultStatus.SUCCESS:
        print(
            _fins_event_line(_FINS_EVENT_SUCCEEDED_PREFIX, event),
            file=effective_stdout,
        )
        _print_result_details(event.result, effective_stdout)
        return
    if event.result.status is FinsResultStatus.CANCELLED:
        print(
            _fins_event_line(_FINS_EVENT_CANCELLED_PREFIX, event),
            file=effective_stderr,
        )
        return

    print(
        _fins_event_line(
            _FINS_EVENT_FAILURE_PREFIX,
            event,
            message=_failure_message_or_fallback(event.result),
        ),
        file=effective_stderr,
    )
    _print_result_details(event.result, effective_stderr)


def render_fins_direct_cancel_requested(
    *,
    stderr: TextIO | None = None,
) -> None:
    """输出 Fins direct operation 已请求取消的提示。

    :param stderr: 标准错误流；``None`` 表示使用当前 ``sys.stderr``。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    print(
        _FINS_CANCEL_REQUESTED_MESSAGE,
        file=sys.stderr if stderr is None else stderr,
    )


def render_fins_direct_local_exit_after_cancel(
    *,
    stderr: TextIO | None = None,
) -> None:
    """输出本地取消后退出的提示。

    :param stderr: 标准错误流；``None`` 表示使用当前 ``sys.stderr``。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    print(
        _FINS_LOCAL_EXIT_AFTER_CANCEL_MESSAGE,
        file=sys.stderr if stderr is None else stderr,
    )


def _fins_event_line(
    prefix: str,
    event: FinsEvent,
    *,
    message: str | None = None,
) -> str:
    """构造单行 Fins event 展示文本。

    :param prefix: 行前缀。
    :param event: Fins direct event。
    :param message: 可选覆盖消息；为空时使用事件消息。
    :returns: 有界展示文本。
    :raises Exception: 不主动抛出异常。
    """

    parts = [
        f"{prefix}:",
        f"operation={_bounded_json_text(event.operation_kind.value)}",
    ]
    if event.ticker is not None:
        parts.append(f"ticker={_bounded_json_text(event.ticker)}")
    if event.filing_kind is not None:
        parts.append(f"filing_kind={_bounded_json_text(event.filing_kind)}")
    if event.document_label is not None:
        parts.append(f"document={_bounded_json_text(event.document_label)}")
    if event.progress is not None:
        parts.append(f"stage={_bounded_json_text(event.progress.stage)}")
    if event.result is not None:
        parts.append(f"status={_bounded_json_text(event.result.status.value)}")
    effective_message = event.message if message is None else message
    if effective_message.strip() != "":
        parts.append(f"message={_bounded_json_text(effective_message)}")
    return " ".join(parts)


def _print_result_details(result: FinsResultSummary, stream: TextIO) -> None:
    """输出 result details 摘要行。

    :param result: Fins direct 终态摘要。
    :param stream: 输出流。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    summary_parts = _summary_parts(result.details)
    if summary_parts:
        print(f"{_FINS_EVENT_SUMMARY_PREFIX}: {' '.join(summary_parts)}", file=stream)


def _summary_parts(values: tuple[FinsEventDetail, ...]) -> tuple[str, ...]:
    """把 result details 转为有界 key=value 片段。

    :param values: result detail 元组。
    :returns: 可安全展示的 key=value 片段。
    :raises Exception: 不主动抛出异常。
    """

    parts: list[str] = []
    for detail in values:
        if len(parts) >= _FINS_SUMMARY_MAX_ITEMS:
            break
        parts.append(
            f"{_safe_summary_key(detail.label)}={_bounded_json_text(detail.value)}"
        )
    return tuple(parts)


def _safe_summary_key(key: str) -> str:
    """把摘要字段名压缩为适合展示的 token。

    :param key: 摘要字段名。
    :returns: 安全摘要字段名。
    :raises Exception: 不主动抛出异常。
    """

    rendered = re.sub(r"[^A-Za-z0-9_.-]+", "_", key.strip())
    if rendered == "":
        return "detail"
    return rendered[:_FINS_TEXT_MAX_CHARS]


def _bounded_json_text(value: str) -> str:
    """把文本截断并编码为短 JSON 字符串。

    :param value: 原始文本。
    :returns: JSON 字符串文本。
    :raises Exception: 不主动抛出异常。
    """

    return json.dumps(
        _safe_text_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _safe_text_value(value: str) -> str:
    """生成适合 CLI 展示的有界文本值。

    :param value: 原始文本。
    :returns: 截断后的文本。
    :raises Exception: 不主动抛出异常。
    """

    if len(value) <= _FINS_TEXT_MAX_CHARS:
        return value
    return value[: _FINS_TEXT_MAX_CHARS - len(_FINS_TRUNCATED_SUFFIX)] + (
        _FINS_TRUNCATED_SUFFIX
    )


def _failure_message_or_fallback(result: FinsResultSummary) -> str:
    """读取 Fins direct 失败摘要中的用户可见错误。

    :param result: Fins direct result summary。
    :returns: 失败消息。
    :raises Exception: 不主动抛出异常。
    """

    if result.error_message is not None and result.error_message.strip() != "":
        return _safe_text_value(result.error_message)
    return _FINS_FAILED_FALLBACK_MESSAGE


__all__: tuple[str, ...] = (
    "render_interactive_terminal_result",
    "render_cli_error",
    "render_fins_direct_cancel_requested",
    "render_fins_direct_event",
    "render_fins_direct_local_exit_after_cancel",
    "render_prompt_terminal_result",
)
