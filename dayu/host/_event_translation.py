"""EngineEvent 到 Host RunEventDraft 的 P1.5 翻译。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from dayu.engine import (
    EngineEvent,
    FinalAnswerData,
    RunCancelledData,
    RunFailedData,
    RunSuspendedData,
)
from dayu.host.contracts import (
    ContextCompactFailureReason,
    HostContextAttemptRetryData,
    HostContextCompactCompletedData,
    HostContextCompactFailedData,
    HostContextCompactRequestedData,
    HostContextOverflowObservedData,
    HostRunFailedData,
    RunCancelledResult,
    RunEvent,
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
    RunFailedResult,
    RunResult,
    RunSucceededResult,
    RunSuspendedResult,
    UserInputScope,
    UserInputAcceptedData,
)

_ERROR_FINAL_ANSWER_DATA_TYPE: str = (
    "FINAL_ANSWER event data must be FinalAnswerData"
)
_ERROR_RUN_FAILED_DATA_TYPE: str = "RUN_FAILED event data must be RunFailedData"
_ERROR_HOST_RUN_FAILED_DATA_TYPE: str = (
    "RUN_FAILED host event data must be HostRunFailedData"
)
_ERROR_RUN_CANCELLED_DATA_TYPE: str = (
    "RUN_CANCELLED event data must be RunCancelledData"
)
_ERROR_RUN_SUSPENDED_DATA_TYPE: str = (
    "RUN_SUSPENDED event data must be RunSuspendedData"
)
_HOST_WORKER_FAILURE_ERROR_CODE: str = "host_worker_failed"
_HOST_CONTEXT_COMPACT_FAILED_ERROR_CODE: str = "host_context_compact_failed"
_FILTERED_INTERNAL_ECHO_CONTENT: str = (
    "回答包含内部治理上下文，Host 已过滤该结果。请重试或缩小问题范围。"
)
_INTERNAL_ECHO_MARKERS: tuple[str, ...] = (
    "## host memory",
    "## host compact memory",
    "## tool facts",
    "## evidence anchors",
    "## 历史工具摘要",
    "tool_fact_id=",
    "cursor_fingerprint=",
    "source_event_cursor=",
    "scope_token=",
    "raw eventlog metadata",
    "tool result repr",
    "source_engine_event_id",
    "toolcompletedoutcome(",
    "toolresultsuccess(",
    "toolresultfailure(",
    "toolresulttruncateddata(",
    "runevent(",
)
_PREVIEW_ENGINE_EVENT_TYPES: frozenset[RunEventType] = frozenset(
    {
        RunEventType.RUNNER_CONTENT_DELTA,
        RunEventType.RUNNER_REASONING_DELTA,
        RunEventType.RUNNER_CONTENT_COMPLETED,
    }
)


def translate_engine_event(event: EngineEvent) -> RunEventDraft:
    """将 EngineEvent 翻译为 Host RunEventDraft。

    :param event: Engine 产出的强类型事件。
    :returns: 对应的 Host RunEventDraft。
    :raises ValueError: EngineEventType 尚未被 Host 类型镜像时抛出。
    """

    event_type = RunEventType(event.type.value)
    data = event.data
    if isinstance(data, FinalAnswerData):
        data = _filter_internal_echo_final_answer(data)
    return RunEventDraft(
        run_id=event.run_id,
        session_id=event.session_id,
        kind=_classify_event_kind(event_type),
        source=RunEventSource.ENGINE,
        type=event_type,
        occurred_at=event.occurred_at,
        data=data,
        source_engine_event_id=event.event_id,
    )


def _filter_internal_echo_final_answer(data: FinalAnswerData) -> FinalAnswerData:
    """过滤明显回显 Host 内部 memory / provenance 的 final answer。

    P4 只做最小输出边界治理：当模型把 Host Memory 标题、工具事实字段、
    cursor 指纹或 raw EventLog 元数据原样输出时，Host 不把该内容作为干净
    成功结果透传，而是返回 filtered/degraded 的安全占位内容。

    :param data: Engine final answer data。
    :returns: 过滤后的 final answer data；未命中时原样返回。
    :raises Exception: 不主动抛出异常。
    """

    if not _contains_internal_echo_marker(data.content):
        return data
    return replace(
        data,
        content=_FILTERED_INTERNAL_ECHO_CONTENT,
        filtered=True,
        degraded=True,
    )


def _contains_internal_echo_marker(content: str) -> bool:
    """判断 final answer 是否包含明显 Host 内部字段。

    :param content: final answer 正文。
    :returns: 命中内部回显标记时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    lowered = content.lower()
    return any(marker in lowered for marker in _INTERNAL_ECHO_MARKERS)


def host_failure_draft(
    *,
    run_id: str,
    session_id: str,
    occurred_at: datetime,
    error: Exception,
    error_code: str = _HOST_WORKER_FAILURE_ERROR_CODE,
) -> RunEventDraft:
    """构造 Host-owned 失败终态事件草稿。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param occurred_at: Host 观察到异常的时间。
    :param error: worker / proxy 抛出的异常。
    :param error_code: Host-owned 失败错误码。
    :returns: Host-owned RUN_FAILED 事件草稿。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id=session_id,
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.RUN_FAILED,
        occurred_at=occurred_at,
        data=HostRunFailedData(
            error_code=error_code,
            message=str(error),
            recoverable=False,
            exception_type=type(error).__name__,
        ),
        source_engine_event_id=None,
    )


def host_context_compact_failure_terminal_draft(
    *,
    run_id: str,
    session_id: str,
    occurred_at: datetime,
    reason: ContextCompactFailureReason,
    message: str,
) -> RunEventDraft:
    """构造 Host-owned context compact 失败终态事件草稿。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param occurred_at: 失败收口时间。
    :param reason: compact 失败原因。
    :param message: 中性可读说明。
    :returns: Host-owned ``RUN_FAILED`` 事件草稿。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id=session_id,
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.RUN_FAILED,
        occurred_at=occurred_at,
        data=HostRunFailedData(
            error_code=_HOST_CONTEXT_COMPACT_FAILED_ERROR_CODE,
            message=f"{reason.value}: {message}",
            recoverable=False,
            exception_type="ContextCompactFailure",
        ),
        source_engine_event_id=None,
    )


def context_overflow_observed_draft(
    *,
    run_id: str,
    session_id: str,
    occurred_at: datetime,
    data: HostContextOverflowObservedData,
) -> RunEventDraft:
    """构造 Host-owned context overflow observed 事件草稿。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param occurred_at: Host 观察时间。
    :param data: overflow observed 事实 data。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return _host_context_draft(
        run_id=run_id,
        session_id=session_id,
        occurred_at=occurred_at,
        event_type=RunEventType.CONTEXT_OVERFLOW_OBSERVED,
        data=data,
    )


def context_compact_requested_draft(
    *,
    run_id: str,
    session_id: str,
    occurred_at: datetime,
    data: HostContextCompactRequestedData,
) -> RunEventDraft:
    """构造 Host-owned context compact requested 事件草稿。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param occurred_at: Host 请求 compact 的时间。
    :param data: compact requested 事实 data。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return _host_context_draft(
        run_id=run_id,
        session_id=session_id,
        occurred_at=occurred_at,
        event_type=RunEventType.CONTEXT_COMPACT_REQUESTED,
        data=data,
    )


def context_compact_completed_draft(
    *,
    run_id: str,
    session_id: str,
    occurred_at: datetime,
    data: HostContextCompactCompletedData,
) -> RunEventDraft:
    """构造 Host-owned context compact completed 事件草稿。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param occurred_at: compact 完成时间。
    :param data: compact completed 事实 data。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return _host_context_draft(
        run_id=run_id,
        session_id=session_id,
        occurred_at=occurred_at,
        event_type=RunEventType.CONTEXT_COMPACT_COMPLETED,
        data=data,
    )


def context_compact_failed_draft(
    *,
    run_id: str,
    session_id: str,
    occurred_at: datetime,
    data: HostContextCompactFailedData,
) -> RunEventDraft:
    """构造 Host-owned context compact failed 事件草稿。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param occurred_at: compact 失败时间。
    :param data: compact failed 事实 data。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return _host_context_draft(
        run_id=run_id,
        session_id=session_id,
        occurred_at=occurred_at,
        event_type=RunEventType.CONTEXT_COMPACT_FAILED,
        data=data,
    )


def context_attempt_retrying_draft(
    *,
    run_id: str,
    session_id: str,
    occurred_at: datetime,
    data: HostContextAttemptRetryData,
) -> RunEventDraft:
    """构造 Host-owned context attempt retrying 事件草稿。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param occurred_at: retry 决策时间。
    :param data: retry 事实 data。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return _host_context_draft(
        run_id=run_id,
        session_id=session_id,
        occurred_at=occurred_at,
        event_type=RunEventType.CONTEXT_ATTEMPT_RETRYING,
        data=data,
    )


def _host_context_draft(
    *,
    run_id: str,
    session_id: str,
    occurred_at: datetime,
    event_type: RunEventType,
    data: (
        HostContextOverflowObservedData
        | HostContextCompactRequestedData
        | HostContextCompactCompletedData
        | HostContextCompactFailedData
        | HostContextAttemptRetryData
    ),
) -> RunEventDraft:
    """构造 Host-owned context compact 非终态事件草稿。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param occurred_at: 事件时间。
    :param event_type: Host context compact event type。
    :param data: Host context compact event data。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id=session_id,
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=event_type,
        occurred_at=occurred_at,
        data=data,
        source_engine_event_id=None,
    )


def user_input_accepted_draft(
    *,
    run_id: str,
    session_id: str,
    occurred_at: datetime,
    turn_id: str,
    content: str,
) -> RunEventDraft:
    """构造 Host-owned 用户输入接纳事件草稿。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param occurred_at: Host 接纳用户输入的时间。
    :param turn_id: 会话内 turn id。
    :param content: 规范化后的用户输入正文。
    :returns: Host-owned ``USER_INPUT_ACCEPTED`` 事件草稿。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id=session_id,
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.USER_INPUT_ACCEPTED,
        occurred_at=occurred_at,
        data=UserInputAcceptedData(
            turn_id=turn_id,
            content=content,
            scope=UserInputScope.SESSION,
        ),
        source_engine_event_id=None,
    )


def _classify_event_kind(event_type: RunEventType) -> RunEventKind:
    """根据 RunEventType 分类 canonical / preview。

    ``RUNNER_CONTENT_COMPLETED`` 在 P1.5 被归为 preview：最终结果只来自
    ``FINAL_ANSWER`` canonical 终态事件，不从 completed 片段拼接。

    :param event_type: Host RunEvent 类型。
    :returns: 对应的 RunEventKind。
    :raises Exception: 不主动抛出异常。
    """

    if event_type in _PREVIEW_ENGINE_EVENT_TYPES:
        return RunEventKind.PREVIEW
    return RunEventKind.CANONICAL


def terminal_result_from_event(event: RunEvent) -> RunResult | None:
    """从已 append 的 canonical Host RunEvent 构造终态结果。

    :param event: Host RunEvent。
    :returns: 若为终态事件则返回 RunResult，否则返回 ``None``。
    :raises TypeError: 终态事件类型与 data 类型不一致时抛出。
    """

    if event.kind is not RunEventKind.CANONICAL:
        return None
    if event.type is RunEventType.FINAL_ANSWER:
        data = event.data
        if not isinstance(data, FinalAnswerData):
            raise TypeError(_ERROR_FINAL_ANSWER_DATA_TYPE)
        return RunSucceededResult(
            run_id=event.run_id,
            session_id=event.session_id,
            content=data.content,
            filtered=data.filtered,
            degraded=data.degraded,
            finish_reason=data.finish_reason,
            terminal_event_cursor=event.cursor,
        )
    if event.type is RunEventType.RUN_FAILED:
        data = event.data
        if event.source is RunEventSource.HOST:
            if not isinstance(data, HostRunFailedData):
                raise TypeError(_ERROR_HOST_RUN_FAILED_DATA_TYPE)
            return RunFailedResult(
                run_id=event.run_id,
                session_id=event.session_id,
                error_code=data.error_code,
                message=data.message,
                recoverable=data.recoverable,
                terminal_event_cursor=event.cursor,
            )
        if not isinstance(data, RunFailedData):
            raise TypeError(_ERROR_RUN_FAILED_DATA_TYPE)
        return RunFailedResult(
            run_id=event.run_id,
            session_id=event.session_id,
            error_code=data.error_code,
            message=data.message,
            recoverable=data.recoverable,
            terminal_event_cursor=event.cursor,
        )
    if event.type is RunEventType.RUN_CANCELLED:
        data = event.data
        if not isinstance(data, RunCancelledData):
            raise TypeError(_ERROR_RUN_CANCELLED_DATA_TYPE)
        return RunCancelledResult(
            run_id=event.run_id,
            session_id=event.session_id,
            reason=data.reason,
            terminal_event_cursor=event.cursor,
        )
    if event.type is RunEventType.RUN_SUSPENDED:
        data = event.data
        if not isinstance(data, RunSuspendedData):
            raise TypeError(_ERROR_RUN_SUSPENDED_DATA_TYPE)
        return RunSuspendedResult(
            run_id=event.run_id,
            session_id=event.session_id,
            reason=data.reason,
            resume_hint=data.resume_hint,
            terminal_event_cursor=event.cursor,
        )
    return None


__all__ = [
    "context_attempt_retrying_draft",
    "context_compact_completed_draft",
    "context_compact_failed_draft",
    "context_compact_requested_draft",
    "context_overflow_observed_draft",
    "host_context_compact_failure_terminal_draft",
    "host_failure_draft",
    "terminal_result_from_event",
    "translate_engine_event",
    "user_input_accepted_draft",
]
