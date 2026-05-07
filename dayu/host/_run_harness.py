"""Host P1.5 最小 Run harness。

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
    EngineEvent,
    SystemMessage,
    ToolMessage,
    UserMessage,
)
from dayu.host._conversation_memory import (
    ConversationMemoryStore,
    InMemoryConversationMemoryStore,
)
from dayu.host._event_store import InMemoryRunEventStore, RunEventStore
from dayu.host._event_translation import (
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
_ERROR_CURRENT_USER_INPUT_SINGLE_MESSAGE: str = (
    "current_user_input_must_be_single_user_message"
)
_ERROR_RUN_INPUT_TRACE_CACHE_LIMIT_INVALID: str = (
    "run_input_trace_cache_limit_must_be_positive"
)
_ERROR_ENGINE_STREAM_ENDED_WITHOUT_TERMINAL: str = (
    "engine_stream_ended_without_terminal"
)
_RUN_INPUT_TRACE_CACHE_LIMIT: int = 32
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
class LocalRunHarness:
    """Host 内部本地 Run harness。

    :param proxy: Host 内部 worker proxy。
    :param event_store: Host 内部 RunEventStore。
    :param tool_runtime: Host 内部 ToolRuntime。
    :param memory_store: Host 内部 ConversationMemoryStore。
    :param run_input_builder: Host 内部 RunInputBuilder。
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
    run_input_trace_cache_limit: int = _RUN_INPUT_TRACE_CACHE_LIMIT
    last_run_input_build_trace_by_run: OrderedDict[
        str, RunInputBuildTrace
    ] = field(
        default_factory=OrderedDict,
        init=False,
    )

    def __post_init__(self) -> None:
        """校验 harness 内部调试缓存配置。

        :returns: 无返回值。
        :raises ValueError: trace 缓存容量不是正数时抛出。
        """

        if self.run_input_trace_cache_limit <= 0:
            raise ValueError(_ERROR_RUN_INPUT_TRACE_CACHE_LIMIT_INVALID)

    async def start_run(self, request: StartRunRequest) -> RunStream:
        """启动 P1.5 内存态 Run。

        后台 task 将 EngineEvent 翻译为 RunEventDraft 并先 append 到
        RunEventStore；返回的事件流只是 store 的订阅视图。P3 起，本方法
        会先追加 Host-owned ``USER_INPUT_ACCEPTED`` 事件，并从 EventLog
        与 memory snapshot 构造真正交给 Engine 的 RunInput；若追加失败，
        不会启动 Engine。

        :param request: start_run 请求。
        :returns: RunStream，包含句柄与事件流。
        :raises Exception: 构造后台任务失败时透传底层异常。
        """

        current_user_text = _extract_current_user_text(request=request)
        current_user_event = await self.event_store.append(
            user_input_accepted_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                turn_id=request.run_id,
                content=current_user_text,
            )
        )
        snapshot = await self.memory_store.get_snapshot(request.session_id)
        build_result = self.run_input_builder.build(
            snapshot=snapshot,
            current_user_event=current_user_event,
        )
        self._remember_run_input_build_trace(
            run_id=request.run_id,
            trace=build_result.trace,
        )
        engine_request = replace(request, input=build_result.run_input)
        task = asyncio.create_task(self._run_to_store(request=engine_request))
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
    ) -> None:
        """立即执行 Engine 事件流并写入 RunEventStore。

        :param request: start_run 请求。
        :returns: 无返回值。
        :raises Exception: 翻译、append 或终态结果推导失败时暴露底层错误；
            worker / proxy 取事件异常会转为 Host-owned failure RunEvent。
        """

        token = _NeverCancelledToken()
        event_count = 0
        terminal_seen = False
        _LOGGER.debug(
            "host.run.background_start session_id=%s run_id=%s",
            request.session_id,
            request.run_id,
        )
        try:
            engine_events = self.proxy.stream_engine_events(
                request=request,
                cancellation_token=token,
            )
        except Exception as exc:
            terminal_seen = await self._append_worker_failure_if_needed(
                request=request,
                error=exc,
                event_count=event_count,
                terminal_seen=terminal_seen,
            )
            if terminal_seen:
                await self._project_run_events(request.run_id)
            return
        try:
            while True:
                try:
                    event = await anext(engine_events)
                except StopAsyncIteration:
                    break
                except Exception as exc:
                    terminal_seen = await self._append_worker_failure_if_needed(
                        request=request,
                        error=exc,
                        event_count=event_count,
                        terminal_seen=terminal_seen,
                    )
                    break
                event_count += 1
                stored_event = await self.event_store.append(
                    translate_engine_event(event)
                )
                if terminal_result_from_event(stored_event) is not None:
                    terminal_seen = True
                    break
            if not terminal_seen:
                terminal_seen = (
                    await self._append_missing_terminal_failure_if_needed(
                        request=request,
                        event_count=event_count,
                        terminal_seen=terminal_seen,
                    )
                )
        finally:
            if terminal_seen:
                await self._project_run_events(request.run_id)
            await _close_engine_events_if_supported(
                engine_events=engine_events,
                request=request,
            )
            _LOGGER.debug(
                "host.run.background_finished session_id=%s run_id=%s "
                "event_count=%s",
                request.session_id,
                request.run_id,
                event_count,
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


def _extract_current_user_text(*, request: StartRunRequest) -> str:
    """从入口 RunInput 中提取当前用户输入正文。

    该函数只位于 ingress 边界，用于在 Engine 启动前写入 Host-owned
    ``USER_INPUT_ACCEPTED``。后续 memory projection、RunInputBuilder 与
    replay 均不得继续从 ``StartRunRequest.input`` 读取用户输入。

    :param request: start_run 请求。
    :returns: 当前用户输入正文。
    :raises ValueError: 请求中不是且仅有一条非空 UserMessage 时抛出。
    """

    messages = request.input.messages
    if len(messages) != 1:
        raise ValueError(_ERROR_CURRENT_USER_INPUT_SINGLE_MESSAGE)
    message = messages[0]
    if isinstance(message, (SystemMessage, AssistantMessage, ToolMessage)):
        raise ValueError(_ERROR_CURRENT_USER_INPUT_SINGLE_MESSAGE)
    if not isinstance(message, UserMessage):
        raise ValueError(_ERROR_CURRENT_USER_INPUT_SINGLE_MESSAGE)
    content = message.content.strip()
    if content == "":
        raise ValueError(_ERROR_CURRENT_USER_INPUT_REQUIRED)
    return content


__all__ = [
    "LocalRunHarness",
    "fetch_more_tool_result",
    "get_run_result",
    "get_tool_fetch_more_handle",
    "start_run",
    "stream_run_events",
]
