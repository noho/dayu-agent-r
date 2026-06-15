"""Dayu CLI 输出格式化 helper。

本模块只处理终端展示文本与退出码映射，不判断 Host 状态真源，也不读取业务
存储。
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from typing import Final, TextIO

from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
)
from dayu.contracts.json_value import JsonValue
from dayu.host.api import HostTerminalStatus
from dayu.service.entrypoint_runtime import EntrypointRunTerminalResult
from dayu.service.fins_direct import FinsDirectJobEvent, FinsDirectTerminalResult
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
_FINS_FAILURE_MESSAGE_KEY: str = "message"
_FINS_EVENT_PROGRESS_PREFIX: Final[str] = "Fins job progress"
_FINS_EVENT_SUMMARY_PREFIX: Final[str] = "Fins job summary"
_FINS_EVENT_FAILURE_PREFIX: Final[str] = "Fins job failure"
_FINS_EVENT_CANCELLED_PREFIX: Final[str] = "Fins job cancelled"
_FINS_EVENT_SUCCEEDED_PREFIX: Final[str] = "Fins job succeeded"
_FINS_SUMMARY_MAX_ITEMS: Final[int] = 8
_FINS_LIST_MAX_ITEMS: Final[int] = 5
_FINS_TEXT_MAX_CHARS: Final[int] = 120
_FINS_REDACTED_TEXT: Final[str] = "<redacted>"
_FINS_TRUNCATED_SUFFIX: Final[str] = "..."
_FINS_SENSITIVE_KEY_PARTS: Final[tuple[str, ...]] = (
    "payload",
    "raw",
    "body",
    "content",
    "path",
)
_ABSOLUTE_PATH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?P<prefix>^|[\s=,:;(\[{\"'])"
    r"(?P<path>(?:/(?!/)[^\s,;)\]}\"']+|[A-Za-z]:[\\/][^\s,;)\]}\"']+))"
)


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
    event: FinsDirectJobEvent,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    """输出 Fins direct job 事件。

    :param event: Service event stream 投影出的 Fins direct job event。
    :param stdout: 标准输出流；``None`` 表示使用当前 ``sys.stdout``。
    :param stderr: 标准错误流；``None`` 表示使用当前 ``sys.stderr``。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    effective_stdout = sys.stdout if stdout is None else stdout
    effective_stderr = sys.stderr if stderr is None else stderr
    terminal_result = event.terminal_result
    if terminal_result is None:
        print(_fins_event_line(_FINS_EVENT_PROGRESS_PREFIX, event), file=effective_stdout)
        _print_summary_line(
            prefix=_FINS_EVENT_SUMMARY_PREFIX,
            values=event.payload,
            stream=effective_stdout,
        )
        return

    if terminal_result.status is FinsIngestionJobStatus.SUCCEEDED:
        print(
            _fins_event_line(_FINS_EVENT_SUCCEEDED_PREFIX, event),
            file=effective_stdout,
        )
        _print_summary_line(
            prefix=_FINS_EVENT_SUMMARY_PREFIX,
            values=terminal_result.result_summary,
            stream=effective_stdout,
        )
        return
    if terminal_result.status is FinsIngestionJobStatus.CANCELLED:
        print(
            _fins_event_line(_FINS_EVENT_CANCELLED_PREFIX, event),
            file=effective_stderr,
        )
        return

    print(
        _fins_event_line(
            _FINS_EVENT_FAILURE_PREFIX,
            event,
            message=_failure_message_or_fallback(terminal_result),
        ),
        file=effective_stderr,
    )
    _print_summary_line(
        prefix=_FINS_EVENT_FAILURE_PREFIX,
        values=terminal_result.failure_summary,
        stream=effective_stderr,
    )


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


def _fins_event_line(
    prefix: str,
    event: FinsDirectJobEvent,
    *,
    message: str | None = None,
) -> str:
    """构造单行 Fins event 展示文本。

    :param prefix: 行前缀。
    :param event: Fins direct job event。
    :param message: 可选覆盖消息；为空时使用事件消息。
    :returns: 有界展示文本。
    :raises Exception: 不主动抛出异常。
    """

    parts = [
        f"{prefix}:",
        f"job_id={_bounded_json_text(event.job_id)}",
        f"command={_bounded_json_text(event.command_name)}",
        f"ticker={_bounded_json_text(event.ticker)}",
        f"event={_bounded_json_text(event.event_label)}",
    ]
    if event.status is not None:
        parts.append(f"status={_bounded_json_text(event.status.value)}")
    effective_message = event.message if message is None else message
    if effective_message.strip() != "":
        parts.append(f"message={_bounded_json_text(effective_message)}")
    return " ".join(parts)


def _print_summary_line(
    *,
    prefix: str,
    values: Mapping[str, JsonValue],
    stream: TextIO,
) -> None:
    """输出有界 key=value 摘要行。

    :param prefix: 摘要行前缀。
    :param values: Service / runtime 已提供的有界 JSON 摘要。
    :param stream: 输出流。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    summary_parts = _summary_parts(values)
    if summary_parts:
        print(f"{prefix}: {' '.join(summary_parts)}", file=stream)


def _summary_parts(values: Mapping[str, JsonValue]) -> tuple[str, ...]:
    """把 JSON 摘要转为有界 key=value 片段。

    :param values: JSON 摘要。
    :returns: 可安全展示的 key=value 片段。
    :raises Exception: 不主动抛出异常。
    """

    parts: list[str] = []
    for key in sorted(values):
        if len(parts) >= _FINS_SUMMARY_MAX_ITEMS:
            break
        if not _is_summary_key_allowed(key):
            continue
        rendered = _format_summary_value(values[key])
        if rendered is None:
            continue
        parts.append(f"{key}={rendered}")
    return tuple(parts)


def _is_summary_key_allowed(key: str) -> bool:
    """判断摘要字段名是否适合直接展示。

    :param key: 摘要字段名。
    :returns: 可展示返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    lowered = key.lower()
    if lowered == _FINS_FAILURE_MESSAGE_KEY:
        return True
    return not any(part in lowered for part in _FINS_SENSITIVE_KEY_PARTS)


def _format_summary_value(value: JsonValue) -> str | None:
    """把 JSON 值压缩为一段有界展示文本。

    :param value: JSON 值。
    :returns: 有界文本；不适合展示时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(value, str):
        return _bounded_json_text(value)
    if value is None or isinstance(value, bool | int | float):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, list):
        return _format_list_summary(value)
    if isinstance(value, Mapping):
        return _bounded_json_text(f"mapping_keys={len(value)}")
    return None


def _format_list_summary(values: list[JsonValue]) -> str:
    """把 JSON list 压缩为短 JSON 文本。

    :param values: JSON list。
    :returns: 短 JSON 文本。
    :raises Exception: 不主动抛出异常。
    """

    rendered_values: list[JsonValue] = []
    for value in values[:_FINS_LIST_MAX_ITEMS]:
        if isinstance(value, str):
            rendered_values.append(_safe_text_value(value))
        elif value is None or isinstance(value, bool | int | float):
            rendered_values.append(value)
        elif isinstance(value, list):
            rendered_values.append(f"list_items={len(value)}")
        elif isinstance(value, Mapping):
            rendered_values.append(f"mapping_keys={len(value)}")
    if len(values) > _FINS_LIST_MAX_ITEMS:
        rendered_values.append(f"truncated_count={len(values) - _FINS_LIST_MAX_ITEMS}")
    return json.dumps(rendered_values, ensure_ascii=False, separators=(",", ":"))


def _bounded_json_text(value: str) -> str:
    """把文本脱敏、截断并编码为短 JSON 字符串。

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
    :returns: 脱敏、截断后的文本。
    :raises Exception: 不主动抛出异常。
    """

    if _looks_like_absolute_path(value):
        return _FINS_REDACTED_TEXT
    redacted = _ABSOLUTE_PATH_PATTERN.sub(_redact_absolute_path_match, value)
    if len(redacted) <= _FINS_TEXT_MAX_CHARS:
        return redacted
    return redacted[: _FINS_TEXT_MAX_CHARS - len(_FINS_TRUNCATED_SUFFIX)] + (
        _FINS_TRUNCATED_SUFFIX
    )


def _redact_absolute_path_match(match: re.Match[str]) -> str:
    """保留路径前的分隔符并替换绝对路径文本。

    :param match: 正则匹配到的绝对路径片段。
    :returns: 已保留原分隔符的脱敏文本。
    :raises IndexError: 正则分组缺失时由 ``Match.group`` 透传。
    """

    return f"{match.group('prefix')}{_FINS_REDACTED_TEXT}"


def _looks_like_absolute_path(value: str) -> bool:
    """判断文本整体是否像绝对文件路径。

    :param value: 原始文本。
    :returns: 像绝对路径时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    stripped = value.strip()
    return stripped.startswith("/") or (
        len(stripped) > 2
        and stripped[1] == ":"
        and stripped[2] in {"/", "\\"}
    )


def _failure_message_or_fallback(result: FinsDirectTerminalResult) -> str:
    """读取 Fins direct 失败摘要中的用户可见错误。

    :param result: Fins direct terminal result。
    :returns: 失败消息。
    :raises Exception: 不主动抛出异常。
    """

    raw_message = result.failure_summary.get(_FINS_FAILURE_MESSAGE_KEY)
    if isinstance(raw_message, str) and raw_message.strip() != "":
        return _safe_text_value(raw_message)
    return _FINS_FAILED_FALLBACK_TEMPLATE.format(job_id=result.job_id)


__all__: tuple[str, ...] = (
    "render_interactive_terminal_result",
    "render_cli_error",
    "render_fins_direct_cancel_requested",
    "render_fins_direct_event",
    "render_fins_direct_local_exit_after_cancel",
    "render_prompt_terminal_result",
)
