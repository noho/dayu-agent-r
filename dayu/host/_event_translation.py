"""EngineEvent 到 Host RunEvent 的 P1 薄翻译。"""

from __future__ import annotations

from dayu.engine import (
    EngineEvent,
    FinalAnswerData,
    RunCancelledData,
    RunFailedData,
    RunSuspendedData,
)
from dayu.host.contracts import (
    RunCancelledResult,
    RunEvent,
    RunEventCursor,
    RunEventType,
    RunFailedResult,
    RunResult,
    RunSucceededResult,
    RunSuspendedResult,
)

_ERROR_FINAL_ANSWER_DATA_TYPE: str = (
    "FINAL_ANSWER event data must be FinalAnswerData"
)
_ERROR_RUN_FAILED_DATA_TYPE: str = "RUN_FAILED event data must be RunFailedData"
_ERROR_RUN_CANCELLED_DATA_TYPE: str = (
    "RUN_CANCELLED event data must be RunCancelledData"
)
_ERROR_RUN_SUSPENDED_DATA_TYPE: str = (
    "RUN_SUSPENDED event data must be RunSuspendedData"
)


def translate_engine_event(event: EngineEvent) -> RunEvent:
    """将 EngineEvent 翻译为 Host RunEvent。

    :param event: Engine 产出的强类型事件。
    :returns: 对应的 Host RunEvent。
    :raises ValueError: EngineEventType 尚未被 Host P1 类型镜像时抛出。
    """

    return RunEvent(
        run_id=event.run_id,
        session_id=event.session_id,
        cursor=RunEventCursor(sequence=event.sequence),
        type=RunEventType(event.type.value),
        occurred_at=event.occurred_at,
        data=event.data,
        source_engine_event_id=event.event_id,
    )


def terminal_result_from_event(event: RunEvent) -> RunResult | None:
    """从 Host RunEvent 构造 P1 终态结果。

    :param event: Host RunEvent。
    :returns: 若为终态事件则返回 RunResult，否则返回 ``None``。
    :raises TypeError: 终态事件类型与 data 类型不一致时抛出。
    """

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


__all__ = ["terminal_result_from_event", "translate_engine_event"]
