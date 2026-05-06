"""Host P1.5 最小 Run harness。

本模块提供 public ``start_run`` 的内存态测试入口，以及内部
``LocalRunHarness``。它不提供生产级 Session / Run governance。
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from typing import Protocol, runtime_checkable

from dayu.contracts import ToolExecutor
from dayu.contracts.tool_call import ToolExecutionRequest
from dayu.contracts.tool_outcome import ToolExecutionOutcome, ToolFailedOutcome
from dayu.contracts.tool_result import ToolResultFailure
from dayu.engine import EngineEvent
from dayu.host._event_store import InMemoryRunEventStore, RunEventStore
from dayu.host._event_translation import (
    host_failure_draft,
    terminal_result_from_event,
    translate_engine_event,
)
from dayu.host._proxy import LocalProxy, WorkerProxy
from dayu.host._worker import EngineWorker
from dayu.host.contracts import (
    RunEvent,
    RunEventCursor,
    RunHandle,
    RunResult,
    RunState,
    RunStream,
    StartRunRequest,
)

_INITIAL_CURSOR_SEQUENCE: int = -1
_ERROR_TOOL_EXECUTOR_NOT_CONFIGURED: str = "tool_executor_not_configured"
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
    """

    proxy: WorkerProxy
    event_store: RunEventStore = field(default_factory=InMemoryRunEventStore)

    async def start_run(self, request: StartRunRequest) -> RunStream:
        """启动 P1.5 内存态 Run。

        后台 task 将 EngineEvent 翻译为 RunEventDraft 并先 append 到
        RunEventStore；返回的事件流只是 store 的订阅视图。

        :param request: start_run 请求。
        :returns: RunStream，包含句柄与事件流。
        :raises Exception: 构造后台任务失败时透传底层异常。
        """

        task = asyncio.create_task(self._run_to_store(request=request))
        task.add_done_callback(
            partial(_log_background_task_failure, request)
        )
        _LOGGER.debug(
            "host.run.start_accepted session_id=%s run_id=%s",
            request.session_id,
            request.run_id,
        )
        handle = RunHandle(
            session_id=request.session_id,
            run_id=request.run_id,
            state=RunState.RUNNING,
            event_cursor=RunEventCursor(sequence=_INITIAL_CURSOR_SEQUENCE),
        )
        return RunStream(
            handle=handle,
            events=self.event_store.subscribe(
                run_id=request.run_id,
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
            await self._append_worker_failure_if_needed(
                request=request,
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
                    await self._append_worker_failure_if_needed(
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
        finally:
            await _close_engine_events_if_supported(engine_events)
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
    ) -> None:
        """按 worker / proxy 异常追加 Host-owned failure。

        本 helper 只应从 worker / proxy 取事件边界调用；Host 自身翻译、
        append 或终态推导错误不得进入该路径。

        :param request: start_run 请求。
        :param error: worker / proxy 抛出的异常。
        :param event_count: 已成功取得的 EngineEvent 数量。
        :param terminal_seen: 是否已经从已 append 事件推导出终态。
        :returns: 无返回值。
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
            return
        await self.event_store.append(
            host_failure_draft(
                run_id=request.run_id,
                session_id=request.session_id,
                occurred_at=datetime.now(tz=timezone.utc),
                error=error,
            )
        )

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


async def _close_engine_events_if_supported(
    engine_events: AsyncIterator[EngineEvent],
) -> None:
    """在提前停止消费时关闭 worker stream。

    ``WorkerProxy`` 的稳定契约只承诺返回 ``AsyncIterator``；本 helper 通过
    运行时协议识别 async generator 等支持 ``aclose`` 的实现，避免 harness
    在首个终态后停止消费时泄漏底层 runner close 流程。

    :param engine_events: worker 返回的 EngineEvent 异步流。
    :returns: 无返回值。
    :raises Exception: 底层 ``aclose`` 失败时透传。
    """

    if isinstance(engine_events, _ClosableAsyncIterator):
        await engine_events.aclose()


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
    return LocalRunHarness(proxy=LocalProxy(worker=EngineWorker(executor)))


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


__all__ = [
    "LocalRunHarness",
    "get_run_result",
    "start_run",
    "stream_run_events",
]
