"""Host P4 最小 Run harness。

本模块提供 public ``start_run`` 的内存态测试入口，以及内部
``LocalRunHarness``。它不提供生产级 Session / Run governance。
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from functools import partial
from typing import Protocol, runtime_checkable

from dayu.contracts import ToolExecutor
from dayu.contracts.tool_call import ToolExecutionRequest
from dayu.contracts.tool_outcome import ToolExecutionOutcome, ToolFailedOutcome
from dayu.contracts.tool_result import ToolResultFailure
from dayu.engine import (
    AssistantMessage,
    ContextCompactionRequestedData,
    EngineEvent,
    EngineEventType,
    RunFailedData,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from dayu.host._context_compaction import (
    ContextCompactCoordinator,
    ContextCompactDecisionStatus,
)
from dayu.host._conversation_memory import (
    ConversationMemoryStore,
    InMemoryConversationMemoryStore,
    snapshot_with_transient_tool_facts,
)
from dayu.host._event_store import InMemoryRunEventStore, RunEventStore
from dayu.host._event_translation import (
    context_attempt_retrying_draft,
    context_compact_completed_draft,
    context_compact_failed_draft,
    context_compact_requested_draft,
    context_overflow_observed_draft,
    host_context_compact_failure_terminal_draft,
    host_failure_draft,
    terminal_result_from_event,
    translate_engine_event,
    user_input_accepted_draft,
)
from dayu.host._proxy import LocalProxy, WorkerProxy
from dayu.host._run_input_builder import (
    DefaultRunInputBuilder,
    RunInputBuildTrace,
    RunInputBuilder,
)
from dayu.host._tool_runtime import (
    InMemoryToolRuntime,
    ToolRuntimeToolExecutor,
)
from dayu.host._worker import EngineWorker
from dayu.host.contracts import (
    ContextCompactFailureReason,
    HostContextAttemptRetryData,
    HostContextOverflowObservedData,
    RunEvent,
    RunEventCursor,
    RunHandle,
    RunResult,
    RunState,
    RunStream,
    StartRunRequest,
    ToolFetchMoreHandleRequest,
    ToolFetchMoreHandleResult,
    ToolFetchMoreRequest,
    ToolFetchMoreResult,
)

_INITIAL_CURSOR_SEQUENCE: int = -1
_ERROR_TOOL_EXECUTOR_NOT_CONFIGURED: str = "tool_executor_not_configured"
_ERROR_TOOL_RUNTIME_NOT_CONFIGURED: str = "tool_runtime_not_configured"
_ERROR_CURRENT_USER_INPUT_REQUIRED: str = "current_user_input_required"
_ERROR_CURRENT_USER_INPUT_SHAPE_EMPTY: str = (
    "start_run_input_requires_trailing_non_empty_user_message"
)
_ERROR_CURRENT_USER_INPUT_SHAPE_TRAILING_USER: str = (
    "start_run_input_must_end_with_single_current_user_message"
)
_ERROR_CURRENT_USER_INPUT_SHAPE_MULTIPLE_USER: str = (
    "start_run_input_allows_only_one_trailing_current_user_message"
)
_ERROR_CURRENT_USER_INPUT_SHAPE_UNSUPPORTED_HISTORY: str = (
    "start_run_input_allows_only_leading_system_messages_before_current_user"
)
_ERROR_RUN_INPUT_TRACE_CACHE_LIMIT_INVALID: str = (
    "run_input_trace_cache_limit_must_be_positive"
)
_ERROR_CONTEXT_COMPACT_RETRY_LIMIT_INVALID: str = (
    "context_compact_retry_limit_must_be_non_negative"
)
_ERROR_ENGINE_STREAM_ENDED_WITHOUT_TERMINAL: str = (
    "engine_stream_ended_without_terminal"
)
_RUN_INPUT_TRACE_CACHE_LIMIT: int = 32
_CONTEXT_COMPACT_RETRY_LIMIT: int = 1
_ERROR_CONTEXT_COMPACTION_REQUIRED: str = "context_compaction_required"
_COMPACT_TRACE_MISSING_MESSAGE: str = "run input build trace is missing"
_UNEXPECTED_COMPACTION_TERMINAL_MESSAGE: str = (
    "engine produced terminal event after context compaction request"
)
_LOGGER: logging.Logger = logging.getLogger(__name__)


@runtime_checkable
class _ClosableAsyncIterator(Protocol):
    """支持显式关闭的异步迭代器协议。"""

    async def aclose(self) -> None:
        """关闭异步迭代器。

        :returns: 无返回值。
        :raises Exception: 关闭失败时透传底层异常。
        """
        ...


@dataclass(frozen=True, slots=True)
class _NeverCancelledToken:
    """当前默认未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 始终返回 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None


@dataclass(frozen=True, slots=True)
class _NoopToolExecutor:
    """public ``start_run`` 默认工具执行器。"""

    async def execute(
        self,
        request: ToolExecutionRequest,
    ) -> ToolExecutionOutcome:
        """返回失败 outcome，避免 public 入口隐式拥有工具能力。

        :param request: 工具执行请求。
        :returns: 失败 outcome。
        :raises Exception: 不主动抛出异常。
        """

        return ToolFailedOutcome(
            result=ToolResultFailure(
                ok=False,
                error=_ERROR_TOOL_EXECUTOR_NOT_CONFIGURED,
                message=request.call.name,
                hint=None,
                meta=None,
            )
        )


@dataclass(frozen=True, slots=True)
class _AcceptedStartInput:
    """Host ingress 接纳后的消息结构。

    :param current_user_text: 当前用户输入正文。
    :param caller_system_messages: 调用方提供的 leading system prompt。
    """

    current_user_text: str
    caller_system_messages: tuple[SystemMessage, ...]


@dataclass(frozen=True, slots=True)
class LocalRunHarness:
    """Host 内部本地 Run harness。

    :param proxy: Host 内部 worker proxy。
    :param event_store: Host 内部 RunEventStore。
    :param tool_runtime: Host 内部 ToolRuntime。
    :param memory_store: Host 内部 ConversationMemoryStore。
    :param run_input_builder: Host 内部 RunInputBuilder。
    :param compact_coordinator: Host 内部 context compact coordinator。
    :param context_compact_retry_limit: context overflow compact retry 上限。
    :param run_input_trace_cache_limit: RunInput 构造 trace 保留上限。
    """

    proxy: WorkerProxy
    event_store: RunEventStore = field(default_factory=InMemoryRunEventStore)
    tool_runtime: InMemoryToolRuntime | None = None
    memory_store: ConversationMemoryStore = field(
        default_factory=InMemoryConversationMemoryStore
    )
    run_input_builder: RunInputBuilder = field(
        default_factory=DefaultRunInputBuilder
    )
    compact_coordinator: ContextCompactCoordinator = field(
        default_factory=ContextCompactCoordinator
    )
    context_compact_retry_limit: int = _CONTEXT_COMPACT_RETRY_LIMIT
    run_input_trace_cache_limit: int = _RUN_INPUT_TRACE_CACHE_LIMIT
    last_run_input_build_trace_by_run: OrderedDict[
        str, RunInputBuildTrace
    ] = field(
        default_factory=OrderedDict,
        init=False,
    )

    def __post_init__(self) -> None:
        """校验 harness 内部 compact retry 与调试缓存配置。

        :returns: 无返回值。
        :raises ValueError: compact retry 上限为负数，或 trace 缓存容量
            不是正数时抛出。
        """

        if self.context_compact_retry_limit < 0:
            raise ValueError(_ERROR_CONTEXT_COMPACT_RETRY_LIMIT_INVALID)
        if self.run_input_trace_cache_limit <= 0:
            raise ValueError(_ERROR_RUN_INPUT_TRACE_CACHE_LIMIT_INVALID)

    async def start_run(self, request: StartRunRequest) -> RunStream:
        """启动 P1.5 内存态 Run。

        后台 task 将 EngineEvent 翻译为 RunEventDraft 并先 append 到
        RunEventStore；返回的事件流只是 store 的订阅视图。P3 起，本方法
        会先追加 Host-owned ``USER_INPUT_ACCEPTED`` 事件，并从 EventLog
        与 memory snapshot 构造真正交给 Engine 的 RunInput；若追加失败，
        不会启动 Engine。P4 起，context overflow 后可在同一 Run 下启动
        compacted internal attempt，但不会再次追加 ``USER_INPUT_ACCEPTED``。

        :param request: start_run 请求。
        :returns: RunStream，包含句柄与事件流。
        :raises Exception: 构造后台任务失败时透传底层异常。
        """

        accepted_input = _extract_accepted_start_input(request=request)
        current_user_event = await self.event_store.append(
            user_input_accepted_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                turn_id=request.run_id,
                content=accepted_input.current_user_text,
            )
        )
        snapshot = await self.memory_store.get_snapshot(request.session_id)
        build_result = self.run_input_builder.build(
            snapshot=snapshot,
            current_user_event=current_user_event,
            caller_system_messages=accepted_input.caller_system_messages,
        )
        self._remember_run_input_build_trace(
            run_id=request.run_id,
            trace=build_result.trace,
        )
        engine_request = replace(request, input=build_result.run_input)
        task = asyncio.create_task(
            self._run_to_store(
                request=engine_request,
                current_user_event=current_user_event,
            )
        )
        task.add_done_callback(
            partial(_log_background_task_failure, engine_request)
        )
        _LOGGER.debug(
            "host.run.start_accepted session_id=%s run_id=%s",
            engine_request.session_id,
            engine_request.run_id,
        )
        handle = RunHandle(
            session_id=engine_request.session_id,
            run_id=engine_request.run_id,
            state=RunState.RUNNING,
            event_cursor=RunEventCursor(sequence=_INITIAL_CURSOR_SEQUENCE),
        )
        return RunStream(
            handle=handle,
            events=self.event_store.subscribe(
                run_id=engine_request.run_id,
                after=handle.event_cursor,
            ),
        )

    async def _run_to_store(
        self,
        request: StartRunRequest,
        current_user_event: RunEvent | None = None,
    ) -> None:
        """立即执行 Engine 事件流并写入 RunEventStore。

        :param request: start_run 请求。
        :param current_user_event: 本 Run 原始 USER_INPUT_ACCEPTED 事件；仅
            context compact retry 路径必需。
        :returns: 无返回值。
        :raises Exception: 翻译、append 或终态结果推导失败时暴露底层错误；
            worker / proxy 取事件异常会转为 Host-owned failure RunEvent。
        """

        token = _NeverCancelledToken()
        attempt_request = request
        attempt_index = 0
        event_count = 0
        terminal_seen = False
        _LOGGER.debug(
            "host.run.background_start session_id=%s run_id=%s",
            request.session_id,
            request.run_id,
        )
        try:
            while True:
                overflow_trigger_seen = False
                overflow_observed_seen = False
                overflow_trigger_event: EngineEvent | None = None
                try:
                    engine_events = self.proxy.stream_engine_events(
                        request=attempt_request,
                        cancellation_token=token,
                    )
                except Exception as exc:
                    terminal_seen = await self._append_worker_failure_if_needed(
                        request=attempt_request,
                        error=exc,
                        event_count=event_count,
                        terminal_seen=terminal_seen,
                    )
                    return
                try:
                    while True:
                        try:
                            event = await anext(engine_events)
                        except StopAsyncIteration:
                            break
                        except Exception as exc:
                            terminal_seen = (
                                await self._append_worker_failure_if_needed(
                                    request=attempt_request,
                                    error=exc,
                                    event_count=event_count,
                                    terminal_seen=terminal_seen,
                                )
                            )
                            return
                        event_count += 1
                        if _is_context_compaction_requested(event):
                            overflow_trigger_seen = True
                            overflow_trigger_event = event
                            await self.event_store.append(
                                translate_engine_event(event)
                            )
                            continue
                        if _is_context_compaction_required_terminal(event):
                            overflow_trigger_seen = True
                            await self._append_overflow_observed(
                                request=attempt_request,
                                event=event,
                                attempt_index=attempt_index,
                            )
                            overflow_observed_seen = True
                            break
                        if overflow_trigger_seen and _is_terminal_engine_event(
                            event
                        ):
                            await self._append_unexpected_compaction_terminal_closure(
                                request=attempt_request,
                                event=event,
                                attempt_index=attempt_index,
                            )
                        stored_event = await self.event_store.append(
                            translate_engine_event(event)
                        )
                        if terminal_result_from_event(stored_event) is not None:
                            terminal_seen = True
                            return
                    if overflow_trigger_seen:
                        if (
                            not overflow_observed_seen
                            and overflow_trigger_event is not None
                        ):
                            await self._append_overflow_observed(
                                request=attempt_request,
                                event=overflow_trigger_event,
                                attempt_index=attempt_index,
                            )
                        if current_user_event is None:
                            raise RuntimeError(
                                "context compact requires current_user_event"
                            )
                        try:
                            next_request = await self._compact_or_fail(
                                request=attempt_request,
                                current_user_event=current_user_event,
                                attempt_index=attempt_index,
                            )
                        except Exception as exc:
                            terminal_seen = (
                                await self._append_compact_exception_failure(
                                    request=attempt_request,
                                    attempt_index=attempt_index,
                                    error=exc,
                                )
                            )
                            return
                        if next_request is None:
                            terminal_seen = True
                            return
                        attempt_request = next_request
                        attempt_index += 1
                        continue
                    terminal_seen = (
                        await self._append_missing_terminal_failure_if_needed(
                            request=attempt_request,
                            event_count=event_count,
                            terminal_seen=terminal_seen,
                        )
                    )
                    return
                finally:
                    await _close_engine_events_if_supported(
                        engine_events=engine_events,
                        request=attempt_request,
                    )
        finally:
            if terminal_seen:
                await self._project_run_events(request.run_id)
            _LOGGER.debug(
                "host.run.background_finished session_id=%s run_id=%s "
                "event_count=%s",
                request.session_id,
                request.run_id,
                event_count,
            )

    async def _compact_or_fail(
        self,
        *,
        request: StartRunRequest,
        current_user_event: RunEvent,
        attempt_index: int,
    ) -> StartRunRequest | None:
        """执行 Host-owned compact 并返回下一次 attempt 请求。

        :param request: 当前 attempt 请求。
        :param current_user_event: 本 Run 原始用户输入事件。
        :param attempt_index: 当前 attempt 序号。
        :returns: 成功返回 compact 后请求；失败返回 ``None``。
        :raises Exception: append 事件或 compact 失败时透传。
        """

        if attempt_index >= self.context_compact_retry_limit:
            failed_data = self.compact_coordinator.retry_limit_failed(
                request=request,
                attempt_index=attempt_index,
            )
            await self.event_store.append(
                context_compact_failed_draft(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    occurred_at=datetime.now(tz=timezone.utc),
                    data=failed_data,
                )
            )
            await self.event_store.append(
                host_context_compact_failure_terminal_draft(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    occurred_at=datetime.now(tz=timezone.utc),
                    reason=failed_data.reason,
                    message=failed_data.message,
                )
            )
            return None
        snapshot = await self.memory_store.get_snapshot(request.session_id)
        current_run_events = await self.event_store.list_events(
            run_id=request.run_id,
            after=None,
        )
        snapshot = snapshot_with_transient_tool_facts(
            snapshot=snapshot,
            events=current_run_events,
        )
        if request.run_id not in self.last_run_input_build_trace_by_run:
            failed_data = self.compact_coordinator.exception_failed(
                request=request,
                attempt_index=attempt_index,
                reason=ContextCompactFailureReason.TRACE_MISSING,
                message=_COMPACT_TRACE_MISSING_MESSAGE,
            )
            await self.event_store.append(
                context_compact_failed_draft(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    occurred_at=datetime.now(tz=timezone.utc),
                    data=failed_data,
                )
            )
            await self.event_store.append(
                host_context_compact_failure_terminal_draft(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    occurred_at=datetime.now(tz=timezone.utc),
                    reason=failed_data.reason,
                    message=failed_data.message,
                )
            )
            return None
        decision = self.compact_coordinator.compact(
            request=request,
            snapshot=snapshot,
            current_user_event=current_user_event,
            attempt_index=attempt_index,
        )
        await self.event_store.append(
            context_compact_requested_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                data=decision.requested_data,
            )
        )
        if decision.status is ContextCompactDecisionStatus.FAILED:
            failed_data = decision.failed_data
            if failed_data is None:
                raise RuntimeError("context compact failed without failed_data")
            await self.event_store.append(
                context_compact_failed_draft(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    occurred_at=datetime.now(tz=timezone.utc),
                    data=failed_data,
                )
            )
            await self.event_store.append(
                host_context_compact_failure_terminal_draft(
                    run_id=request.run_id,
                    session_id=request.session_id,
                    occurred_at=datetime.now(tz=timezone.utc),
                    reason=failed_data.reason,
                    message=failed_data.message,
                )
            )
            return None
        completed_data = decision.completed_data
        compacted_input = decision.run_input
        if completed_data is None or compacted_input is None:
            raise RuntimeError("context compact completed without run_input")
        await self.event_store.append(
            context_compact_completed_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                data=completed_data,
            )
        )
        next_attempt_index = attempt_index + 1
        await self.event_store.append(
            context_attempt_retrying_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                data=HostContextAttemptRetryData(
                    from_attempt_index=attempt_index,
                    next_attempt_index=next_attempt_index,
                    policy_id=completed_data.policy_id,
                    reason="context_overflow_compacted",
                ),
            )
        )
        return replace(request, input=compacted_input)

    async def _append_compact_exception_failure(
        self,
        *,
        request: StartRunRequest,
        attempt_index: int,
        error: Exception,
    ) -> bool:
        """将 compact 分支异常收口为 Host-owned 失败终态。

        :param request: 当前 attempt 请求。
        :param attempt_index: 当前 attempt 序号。
        :param error: compact 分支抛出的异常。
        :returns: 已追加终态时返回 ``True``。
        :raises Exception: append 失败时透传。
        """

        _LOGGER.error(
            "host.run.context_compact_failed session_id=%s run_id=%s "
            "attempt_index=%s exc_type=%s",
            request.session_id,
            request.run_id,
            attempt_index,
            type(error).__name__,
            exc_info=(type(error), error, error.__traceback__),
        )
        failed_data = self.compact_coordinator.exception_failed(
            request=request,
            attempt_index=attempt_index,
            reason=ContextCompactFailureReason.INTERNAL_ERROR,
            message=str(error),
        )
        await self.event_store.append(
            context_compact_failed_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                data=failed_data,
            )
        )
        stored_event = await self.event_store.append(
            host_context_compact_failure_terminal_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                reason=failed_data.reason,
                message=failed_data.message,
            )
        )
        return terminal_result_from_event(stored_event) is not None

    async def _append_overflow_observed(
        self,
        *,
        request: StartRunRequest,
        event: EngineEvent,
        attempt_index: int,
    ) -> None:
        """追加 Host-owned overflow observed 事实。

        :param request: 当前 attempt 请求。
        :param event: Engine overflow 触发事件；可以是 terminal
            ``RUN_FAILED(context_compaction_required)``，也可以是非 terminal
            ``CONTEXT_COMPACTION_REQUESTED``。
        :param attempt_index: 当前 attempt 序号。
        :returns: 无返回值。
        :raises Exception: append 失败时透传。
        """

        data = event.data
        engine_error_code: str | None = None
        recoverable = False
        reason = "engine_context_compaction_required"
        if isinstance(data, RunFailedData):
            engine_error_code = data.error_code
            recoverable = data.recoverable
            reason = data.message
        if isinstance(data, ContextCompactionRequestedData):
            recoverable = True
            reason = data.reason
        await self.event_store.append(
            context_overflow_observed_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                data=HostContextOverflowObservedData(
                    attempt_index=attempt_index,
                    engine_event_type=event.type.value,
                    engine_error_code=engine_error_code,
                    recoverable=recoverable,
                    reason=reason,
                ),
            )
        )

    async def _append_unexpected_compaction_terminal_closure(
        self,
        *,
        request: StartRunRequest,
        event: EngineEvent,
        attempt_index: int,
    ) -> None:
        """闭合 Engine context compaction requested 后的意外终态序列。

        Engine 契约要求 ``CONTEXT_COMPACTION_REQUESTED`` 后跟
        recoverable ``RUN_FAILED(context_compaction_required)``。若 Engine
        产出其它终态，Host 先追加 Host-owned ``CONTEXT_COMPACT_FAILED``
        事实闭合 compact 序列，再保留 Engine 原终态作为本 Run 终态。

        :param request: 当前 attempt 请求。
        :param event: Engine 意外终态事件。
        :param attempt_index: 当前 attempt 序号。
        :returns: 无返回值。
        :raises Exception: append 失败时透传。
        """

        _LOGGER.warning(
            "host.run.context_compact_unexpected_terminal "
            "session_id=%s run_id=%s attempt_index=%s engine_event_type=%s",
            request.session_id,
            request.run_id,
            attempt_index,
            event.type.value,
        )
        failed_data = self.compact_coordinator.exception_failed(
            request=request,
            attempt_index=attempt_index,
            reason=ContextCompactFailureReason.INTERNAL_ERROR,
            message=_UNEXPECTED_COMPACTION_TERMINAL_MESSAGE,
        )
        await self.event_store.append(
            context_compact_failed_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                data=failed_data,
            )
        )

    async def _append_worker_failure_if_needed(
        self,
        *,
        request: StartRunRequest,
        error: Exception,
        event_count: int,
        terminal_seen: bool,
    ) -> bool:
        """按 worker / proxy 异常追加 Host-owned failure。

        本 helper 只应从 worker / proxy 取事件边界调用；Host 自身翻译、
        append 或终态推导错误不得进入该路径。

        :param request: start_run 请求。
        :param error: worker / proxy 抛出的异常。
        :param event_count: 已成功取得的 EngineEvent 数量。
        :param terminal_seen: 是否已经从已 append 事件推导出终态。
        :returns: 已存在或新追加终态时返回 ``True``。
        :raises Exception: append Host-owned failure 失败时透传。
        """

        _LOGGER.warning(
            "host.run.background_failed session_id=%s run_id=%s "
            "event_count=%s exc_type=%s",
            request.session_id,
            request.run_id,
            event_count,
            type(error).__name__,
        )
        if terminal_seen:
            return True
        stored_event = await self.event_store.append(
            host_failure_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                error=error,
            )
        )
        return terminal_result_from_event(stored_event) is not None

    async def _append_missing_terminal_failure_if_needed(
        self,
        *,
        request: StartRunRequest,
        event_count: int,
        terminal_seen: bool,
    ) -> bool:
        """Engine stream 正常结束但无终态时追加 Host-owned failure。

        这是 Host 对 Engine 协议缺口的治理收口：正常耗尽事件流却没有
        terminal 时，不能把本轮投影为成功，也不能丢弃已接纳用户输入。

        :param request: start_run 请求。
        :param event_count: 已成功取得的 EngineEvent 数量。
        :param terminal_seen: 是否已经从已 append 事件推导出终态。
        :returns: 已存在或新追加终态时返回 ``True``。
        :raises Exception: append Host-owned failure 失败时透传。
        """

        if terminal_seen:
            return True
        _LOGGER.critical(
            "host.run.engine_stream_ended_without_terminal "
            "session_id=%s run_id=%s event_count=%s",
            request.session_id,
            request.run_id,
            event_count,
        )
        stored_event = await self.event_store.append(
            host_failure_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                error=RuntimeError(_ERROR_ENGINE_STREAM_ENDED_WITHOUT_TERMINAL),
                error_code=_ERROR_ENGINE_STREAM_ENDED_WITHOUT_TERMINAL,
            )
        )
        return terminal_result_from_event(stored_event) is not None

    async def _project_run_events(self, run_id: str) -> None:
        """将指定 run 的已落库事件投影到 memory。

        :param run_id: Run id。
        :returns: 无返回值。
        :raises Exception: 读取事件或投影失败时透传。
        """

        events = await self.event_store.list_events(
            run_id=run_id,
            after=None,
        )
        await self.memory_store.project_run_events(events)

    def _remember_run_input_build_trace(
        self,
        *,
        run_id: str,
        trace: RunInputBuildTrace,
    ) -> None:
        """记录最近 RunInput 构造 trace，并按 FIFO 淘汰旧 run。

        :param run_id: Run id。
        :param trace: RunInput 构造 trace。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        traces = self.last_run_input_build_trace_by_run
        if run_id in traces:
            del traces[run_id]
        traces[run_id] = trace
        while len(traces) > self.run_input_trace_cache_limit:
            traces.popitem(last=False)

    def stream_run_events(
        self,
        run_id: str,
        after: RunEventCursor | None,
    ) -> AsyncIterator[RunEvent]:
        """订阅某个 run 的 RunEvent 流。

        :param run_id: Run id。
        :param after: exclusive 起点 cursor；为 ``None`` 时从头订阅。
        :returns: RunEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        return self.event_store.subscribe(run_id=run_id, after=after)

    async def get_run_result(self, run_id: str) -> RunResult | None:
        """从已 append 的 terminal RunEvent 推导 RunResult 快照。

        :param run_id: Run id。
        :returns: 已终态时返回 RunResult，否则返回 ``None``。
        :raises TypeError: 终态事件类型与 data 类型不一致时抛出。
        """

        events = await self.event_store.list_events(run_id=run_id, after=None)
        for event in reversed(events):
            result = terminal_result_from_event(event)
            if result is not None:
                return result
        return None

    async def get_tool_fetch_more_handle(
        self,
        request: ToolFetchMoreHandleRequest,
    ) -> ToolFetchMoreHandleResult:
        """读取工具补读受控 handle。

        :param request: handle 读取请求。
        :returns: handle 读取结果。
        :raises RuntimeError: harness 未装配 ToolRuntime 时抛出。
        """

        if self.tool_runtime is None:
            raise RuntimeError(_ERROR_TOOL_RUNTIME_NOT_CONFIGURED)
        return await self.tool_runtime.get_tool_fetch_more_handle(request)

    async def fetch_more_tool_result(
        self,
        request: ToolFetchMoreRequest,
    ) -> ToolFetchMoreResult:
        """补读已截断工具结果。

        :param request: 补读请求。
        :returns: 补读结果。
        :raises RuntimeError: harness 未装配 ToolRuntime 时抛出。
        """

        if self.tool_runtime is None:
            raise RuntimeError(_ERROR_TOOL_RUNTIME_NOT_CONFIGURED)
        return await self.tool_runtime.fetch_more(request)


async def _close_engine_events_if_supported(
    *,
    engine_events: AsyncIterator[EngineEvent],
    request: StartRunRequest,
) -> None:
    """在提前停止消费时关闭 worker stream。

    ``WorkerProxy`` 的稳定契约只承诺返回 ``AsyncIterator``；本 helper 通过
    运行时协议识别 async generator 等支持 ``aclose`` 的实现，避免 harness
    在首个终态后停止消费时泄漏底层 runner close 流程。关闭失败只记录诊断
    日志，不覆盖原始异常，也不生成 Host-owned failure 事实事件。

    :param engine_events: worker 返回的 EngineEvent 异步流。
    :param request: start_run 请求，用于输出诊断上下文。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if isinstance(engine_events, _ClosableAsyncIterator):
        try:
            await engine_events.aclose()
        except Exception as exc:
            _LOGGER.warning(
                "host.run.stream_close_failed session_id=%s run_id=%s "
                "exc_type=%s",
                request.session_id,
                request.run_id,
                type(exc).__name__,
                exc_info=(type(exc), exc, exc.__traceback__),
            )


_DEFAULT_HARNESS_BY_LOOP: weakref.WeakKeyDictionary[
    asyncio.AbstractEventLoop, LocalRunHarness
] = weakref.WeakKeyDictionary()


def _log_background_task_failure(
    request: StartRunRequest,
    task: asyncio.Future[None],
) -> None:
    """取回后台 task 异常并记录 ERROR 日志。

    该回调只负责诊断可观测性，不把 Host 内部错误转换为 Host-owned
    failure，也不引入完整 Run supervisor / governance。

    :param request: start_run 请求。
    :param task: 已完成的后台 Future。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    try:
        error = task.exception()
    except asyncio.CancelledError:
        return
    if error is None:
        return
    _LOGGER.error(
        "host.run.background_task_failed session_id=%s run_id=%s "
        "exc_type=%s",
        request.session_id,
        request.run_id,
        type(error).__name__,
        exc_info=(type(error), error, error.__traceback__),
    )


def _build_default_harness() -> LocalRunHarness:
    """构造默认 harness。

    :returns: 默认本地 Run harness。
    :raises Exception: 不主动抛出异常。
    """

    executor: ToolExecutor = _NoopToolExecutor()
    event_store = InMemoryRunEventStore()
    runtime = InMemoryToolRuntime(
        executor=executor,
        event_store=event_store,
    )
    return LocalRunHarness(
        proxy=LocalProxy(worker=EngineWorker(ToolRuntimeToolExecutor(runtime))),
        event_store=event_store,
        tool_runtime=runtime,
    )


def _default_harness_for_running_loop() -> LocalRunHarness:
    """返回当前 event loop 绑定的默认 harness。

    :returns: 当前 event loop 对应的默认 LocalRunHarness。
    :raises RuntimeError: 当前线程没有运行中的 event loop 时抛出。
    """

    loop = asyncio.get_running_loop()
    harness = _DEFAULT_HARNESS_BY_LOOP.get(loop)
    if harness is None:
        harness = _build_default_harness()
        _DEFAULT_HARNESS_BY_LOOP[loop] = harness
    return harness


async def start_run(request: StartRunRequest) -> RunStream:
    """启动 P1.5 最小 Run。

    这是 public 测试入口，不暴露 EngineWorker 或 ToolExecutor。需要定制
    ToolExecutor 的测试应使用内部 harness，而不是把 ToolExecutor 提升
    为 Host public API。

    :param request: start_run 请求。
    :returns: RunStream，包含句柄与事件流。
    :raises Exception: 构造后台任务失败时透传底层异常。
    """

    return await _default_harness_for_running_loop().start_run(request)


def stream_run_events(
    run_id: str,
    after: RunEventCursor | None = None,
) -> AsyncIterator[RunEvent]:
    """订阅默认 harness 中某个 run 的 RunEvent 流。

    :param run_id: Run id。
    :param after: exclusive 起点 cursor；为 ``None`` 时从头订阅。
    :returns: RunEvent 异步流。
    :raises Exception: 不主动抛出异常。
    """

    return _default_harness_for_running_loop().stream_run_events(
        run_id=run_id,
        after=after,
    )


async def get_run_result(run_id: str) -> RunResult | None:
    """查询默认 harness 中某个 run 的终态结果快照。

    :param run_id: Run id。
    :returns: 已终态时返回 RunResult，否则返回 ``None``。
    :raises TypeError: 终态事件类型与 data 类型不一致时抛出。
    """

    return await _default_harness_for_running_loop().get_run_result(
        run_id=run_id
    )


async def get_tool_fetch_more_handle(
    request: ToolFetchMoreHandleRequest,
) -> ToolFetchMoreHandleResult:
    """读取默认 harness 中的工具补读受控 handle。

    :param request: handle 读取请求。
    :returns: handle 读取结果。
    :raises RuntimeError: 默认 harness 未装配 ToolRuntime 时抛出。
    """

    return await _default_harness_for_running_loop().get_tool_fetch_more_handle(
        request
    )


async def fetch_more_tool_result(
    request: ToolFetchMoreRequest,
) -> ToolFetchMoreResult:
    """补读默认 harness 中的截断工具结果。

    :param request: 补读请求。
    :returns: 补读结果。
    :raises RuntimeError: 默认 harness 未装配 ToolRuntime 时抛出。
    """

    return await _default_harness_for_running_loop().fetch_more_tool_result(
        request
    )


def _extract_accepted_start_input(*, request: StartRunRequest) -> _AcceptedStartInput:
    """从入口 RunInput 中提取 caller system prompt 与当前用户输入。

    该函数只位于 ingress 边界，用于在 Engine 启动前写入 Host-owned
    ``USER_INPUT_ACCEPTED``。后续 memory projection、RunInputBuilder 与
    replay 均不得继续从 ``StartRunRequest.input`` 读取用户输入。

    :param request: start_run 请求。
    :returns: 接纳后的当前用户输入和 caller system prompt。
    :raises ValueError: 请求不是若干 leading SystemMessage 加一条非空
        UserMessage 时抛出。
    """

    messages = request.input.messages
    if not messages:
        raise ValueError(_ERROR_CURRENT_USER_INPUT_SHAPE_EMPTY)
    trailing_message = messages[-1]
    if not isinstance(trailing_message, UserMessage):
        raise ValueError(_ERROR_CURRENT_USER_INPUT_SHAPE_TRAILING_USER)
    caller_system_messages: list[SystemMessage] = []
    for message in messages[:-1]:
        if isinstance(message, SystemMessage):
            caller_system_messages.append(message)
            continue
        if isinstance(message, UserMessage):
            raise ValueError(_ERROR_CURRENT_USER_INPUT_SHAPE_MULTIPLE_USER)
        raise ValueError(_ERROR_CURRENT_USER_INPUT_SHAPE_UNSUPPORTED_HISTORY)
    content = trailing_message.content.strip()
    if content == "":
        raise ValueError(_ERROR_CURRENT_USER_INPUT_REQUIRED)
    return _AcceptedStartInput(
        current_user_text=content,
        caller_system_messages=tuple(caller_system_messages),
    )


def _is_terminal_engine_event(event: EngineEvent) -> bool:
    """判断 EngineEvent 是否为 Engine 终态事件。

    :param event: EngineEvent。
    :returns: 是 final / failed / cancelled / suspended 终态时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return event.type in {
        EngineEventType.FINAL_ANSWER,
        EngineEventType.RUN_FAILED,
        EngineEventType.RUN_CANCELLED,
        EngineEventType.RUN_SUSPENDED,
    }


def _is_context_compaction_requested(event: EngineEvent) -> bool:
    """判断 Engine 事件是否为强类型 context compaction requested。

    :param event: EngineEvent。
    :returns: 是 context compaction requested 返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return event.type is EngineEventType.CONTEXT_COMPACTION_REQUESTED and isinstance(
        event.data,
        ContextCompactionRequestedData,
    )


def _is_context_compaction_required_terminal(event: EngineEvent) -> bool:
    """判断 Engine terminal 是否为可 compact 的 context overflow。

    :param event: EngineEvent。
    :returns: 可由 Host compact 接管返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    data = event.data
    return (
        event.type is EngineEventType.RUN_FAILED
        and isinstance(data, RunFailedData)
        and data.recoverable
        and data.error_code == _ERROR_CONTEXT_COMPACTION_REQUIRED
    )


__all__ = [
    "LocalRunHarness",
    "fetch_more_tool_result",
    "get_run_result",
    "get_tool_fetch_more_handle",
    "start_run",
    "stream_run_events",
]
