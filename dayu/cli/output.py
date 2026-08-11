"""Dayu CLI 输出格式化 helper。

本模块只处理终端展示文本与退出码映射，不判断 Host 状态真源，也不读取业务
存储。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from typing import Final, TextIO

from dayu.cli.exit_codes import (
    EXIT_FAILURE,
    EXIT_KEYBOARD_INTERRUPT,
    EXIT_SUCCESS,
)
from dayu.cli.session_identity import display_identity_from_slot
from dayu.fins.direct_events import (
    FinsDownloadPublicDocument,
    FinsDownloadPublicSummary,
    FinsEvent,
    FinsEventDetail,
    FinsEventType,
    FinsResultStatus,
    FinsResultSummary,
    FinsPublicFailure,
)
from dayu.host.api import (
    HostTerminalStatus,
    ListSessionsResult,
    PurgeSessionResult,
    SessionListItem,
)
from dayu.service.entrypoint_runtime import EntrypointRunTerminalResult

_EMPTY_CELL: Final[str] = "-"
_SESSION_LIST_EMPTY_MESSAGE: Final[str] = "No sessions."
_SESSION_LIST_HEADER: Final[str] = "\t".join(
    (
        "SESSION_ID",
        "STATUS",
        "KIND",
        "LABEL",
        "ACTIVE_RUN",
        "QUEUED",
        "CREATED_AT",
        "CLOSED_AT",
    )
)
_PURGE_TOMBSTONE_PREFIX_CHARS: Final[int] = 12
_FAILED_FALLBACK_MESSAGE: str = "Host run failed without error message."
_LOST_FALLBACK_MESSAGE: str = "Host run lost without error message."
_USER_CANCELLED_MESSAGE: str = "Cancelled."
_MISSING_FINAL_ANSWER_MESSAGE: str = "Host run succeeded without final answer."
_FINS_CANCEL_REQUESTED_MESSAGE: str = "Fins operation cancel requested."
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
            _public_cancel_message(),
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
            _public_cancel_message(),
            file=effective_stderr,
        )
        return EXIT_SUCCESS
    print(result.error_message or _LOST_FALLBACK_MESSAGE, file=effective_stderr)
    return EXIT_FAILURE


def _public_cancel_message() -> str:
    """返回 CLI 用户可读的取消终态文案。

    :returns: 面向终端用户的取消说明。
    :raises Exception: 不主动抛出异常。
    """

    return _USER_CANCELLED_MESSAGE


def render_cli_error(message: str, *, stderr: TextIO | None = None) -> None:
    """输出 CLI 错误消息。

    :param message: 已归一化的错误消息。
    :param stderr: 标准错误流；``None`` 表示使用当前 ``sys.stderr``。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    print(message, file=sys.stderr if stderr is None else stderr)


def render_session_list(
    result: ListSessionsResult,
    *,
    stdout: TextIO | None = None,
) -> None:
    """输出 CLI Session 列表。

    :param result: Host public ``list_sessions`` 读取结果。
    :param stdout: 标准输出流；``None`` 表示使用当前 ``sys.stdout``。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    effective_stdout = sys.stdout if stdout is None else stdout
    if result.sessions == ():
        print(_SESSION_LIST_EMPTY_MESSAGE, file=effective_stdout)
        return
    print(_SESSION_LIST_HEADER, file=effective_stdout)
    for item in result.sessions:
        print(_session_list_row(item), file=effective_stdout)


def render_session_purge_result(
    result: PurgeSessionResult,
    *,
    stdout: TextIO | None = None,
) -> None:
    """输出 CLI Session purge 成功结果。

    :param result: Host public ``purge_session`` 结果。
    :param stdout: 标准输出流；``None`` 表示使用当前 ``sys.stdout``。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    effective_stdout = sys.stdout if stdout is None else stdout
    if result.purged:
        print(
            (
                f"Purged session {result.session_id} "
                f"(tombstone: {_purge_tombstone_prefix(result.purge_tombstone_ref)}...)"
            ),
            file=effective_stdout,
        )
        return
    print(f"Session {result.session_id} was not purged.", file=effective_stdout)


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
        _print_terminal_business_summary(event.result, effective_stdout)
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
    _print_terminal_business_summary(event.result, effective_stderr)


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


def _session_list_row(item: SessionListItem) -> str:
    """把 Session list item 转成 CLI 列表行。

    :param item: Host public Session list item。
    :returns: tab 分隔的 Session 列表行。
    :raises Exception: 不主动抛出异常。
    """

    identity = display_identity_from_slot(item.slot)
    return "\t".join(
        (
            item.session_id,
            item.status.value,
            identity.kind.value,
            identity.label,
            _optional_text_cell(item.active_run_id),
            str(len(item.queued_run_ids)),
            _format_session_datetime(item.created_at),
            _format_session_datetime(item.closed_at),
        )
    )


def _optional_text_cell(value: str | None) -> str:
    """把可空文本转为 CLI table cell。

    :param value: 可空文本。
    :returns: 非空文本或 ``-``。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return _EMPTY_CELL
    return value


def _format_session_datetime(value: datetime | None) -> str:
    """把 Session datetime 转为 CLI table cell。

    :param value: UTC datetime 或 ``None``。
    :returns: ISO-8601 UTC 文本或 ``-``。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return _EMPTY_CELL
    return value.isoformat().replace("+00:00", "Z")


def _purge_tombstone_prefix(value: str | None) -> str:
    """生成 purge tombstone 展示前缀。

    :param value: Host public purge tombstone ref。
    :returns: 去空白后的最多 12 字符前缀；缺失时返回 ``-``。
    :raises Exception: 不主动抛出异常。
    """

    if value is None:
        return _EMPTY_CELL
    stripped = value.strip()
    if stripped == "":
        return _EMPTY_CELL
    return stripped[:_PURGE_TOMBSTONE_PREFIX_CHARS]


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


def _print_terminal_business_summary(result: FinsResultSummary, stream: TextIO) -> None:
    """机械投影 typed terminal 业务对象。

    :param result: Fins direct 终态摘要。
    :param stream: 输出流。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    if result.download is None:
        _print_result_details(result, stream)
        return
    _print_download_summary(result.download, stream)
    if result.failure is not None:
        _print_download_failure(result.failure, stream)


def _print_download_summary(summary: FinsDownloadPublicSummary, stream: TextIO) -> None:
    """输出 bounded typed 下载摘要和文档行。

    :param summary: runtime 构造的 public download 真源。
    :param stream: 输出流。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    filters = summary.effective_filters
    forms = ",".join(filters.form_types) if filters.form_types else _EMPTY_CELL
    print(
        (
            f"{_FINS_EVENT_SUMMARY_PREFIX}: "
            f"source={_bounded_json_text(summary.source.value)} "
            f"ticker={_bounded_json_text(summary.canonical_ticker)} "
            f"forms={_bounded_json_text(forms)} "
            f"start={_bounded_json_text(filters.start_date or _EMPTY_CELL)} "
            f"end={_bounded_json_text(filters.end_date or _EMPTY_CELL)} "
            f"overwrite={str(filters.overwrite_existing).lower()} "
            f"rebuild={str(filters.rebuild_local_artifacts).lower()} "
            f"discovered={summary.discovered_count} "
            f"downloaded={summary.downloaded_count} "
            f"skipped={summary.skipped_count} "
            f"rejected={summary.rejected_count} "
            f"failed={summary.failed_count} "
            f"omitted={summary.omitted_count}"
        ),
        file=stream,
    )
    for row in summary.document_rows:
        print(_download_document_line(row), file=stream)
    if summary.missing_periods:
        print(
            "Fins missing periods: " + _bounded_json_text(",".join(summary.missing_periods)),
            file=stream,
        )


def _download_document_line(row: FinsDownloadPublicDocument) -> str:
    """把 typed public document row 投影为单行文本。

    :param row: runtime 已有界化的下载文档行。
    :returns: 不读取 storage 或 raw payload 的展示行。
    :raises Exception: 不主动抛出异常。
    """

    parts = [
        "Fins document:",
        f"document_id={_bounded_json_text(row.document_id)}",
        f"form_or_period={_bounded_json_text(row.form_or_period or _EMPTY_CELL)}",
        f"filing_date={_bounded_json_text(row.filing_date or _EMPTY_CELL)}",
        f"report_date={_bounded_json_text(row.report_date or _EMPTY_CELL)}",
        f"covered_fiscal_periods={json.dumps(list(row.covered_fiscal_periods), ensure_ascii=False, separators=(',', ':'))}",
        f"disposition={_bounded_json_text(row.disposition.value)}",
    ]
    if row.reason_category is not None:
        parts.append(f"reason_category={_bounded_json_text(row.reason_category)}")
    if row.reason_message is not None:
        parts.append(f"reason={_bounded_json_text(row.reason_message)}")
    if row.artifact_locator is not None:
        parts.append(f"artifact_locator={_bounded_json_text(row.artifact_locator)}")
    return " ".join(parts)


def _print_download_failure(failure: FinsPublicFailure, stream: TextIO) -> None:
    """机械投影 closed typed download failure。

    :param failure: runtime 构造的 public failure。
    :param stream: 输出流。
    :returns: ``None``。
    :raises OSError: 输出流写入失败时由底层 ``print`` 透传。
    """

    transport = _EMPTY_CELL if failure.transport_category is None else failure.transport_category.value
    print(
        (
            "Fins failure detail: "
            f"classification={_bounded_json_text(failure.kind.value)} "
            f"source={_bounded_json_text(failure.source.value)} "
            f"transport={_bounded_json_text(transport)} "
            f"retry_hint={_bounded_json_text(failure.retry_hint)}"
        ),
        file=stream,
    )


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
        parts.append(f"{_safe_summary_key(detail.label)}={_bounded_json_text(detail.value)}")
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
    return value[: _FINS_TEXT_MAX_CHARS - len(_FINS_TRUNCATED_SUFFIX)] + (_FINS_TRUNCATED_SUFFIX)


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
    "render_prompt_terminal_result",
    "render_session_list",
    "render_session_purge_result",
)
