"""EngineEvent 到 Host RunEventDraft 的 P1.5 翻译。"""

from __future__ import annotations

from datetime import datetime

from dayu.engine import (
    EngineEvent,
    FinalAnswerData,
    RunCancelledData,
    RunFailedData,
    RunSuspendedData,
)
from dayu.host.contracts import (
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
_HOST_FAILURE_ERROR_CODE: str = "host_worker_failed"
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
    return RunEventDraft(
        run_id=event.run_id,
        session_id=event.session_id,
        kind=_classify_event_kind(event_type),
        source=RunEventSource.ENGINE,
        type=event_type,
        occurred_at=event.occurred_at,
        data=event.data,
        source_engine_event_id=event.event_id,
    )


def host_failure_draft(
    *,
    run_id: str,
    session_id: str,
    occurred_at: datetime,
    error: Exception,
) -> RunEventDraft:
    """构造 Host-owned 失败终态事件草稿。

    :param run_id: Run id。
    :param session_id: 会话 id。
    :param occurred_at: Host 观察到异常的时间。
    :param error: worker / proxy 抛出的异常。
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
            error_code=_HOST_FAILURE_ERROR_CODE,
            message=str(error),
            recoverable=False,
            exception_type=type(error).__name__,
        ),
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
    "host_failure_draft",
    "terminal_result_from_event",
    "translate_engine_event",
    "user_input_accepted_draft",
]
