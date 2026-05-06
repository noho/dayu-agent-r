"""Host P1 最小 Run harness。

本模块提供 public ``start_run`` 的内存态测试入口，以及内部
``LocalRunHarness``。它不提供生产级 Session / Run governance。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime

from dayu.contracts import ToolExecutor
from dayu.contracts.tool_call import ToolExecutionRequest
from dayu.contracts.tool_outcome import ToolExecutionOutcome, ToolFailedOutcome
from dayu.contracts.tool_result import ToolResultFailure
from dayu.host._event_translation import translate_engine_event
from dayu.host._proxy import LocalProxy, WorkerProxy
from dayu.host._worker import EngineWorker
from dayu.host.contracts import (
    RunEvent,
    RunEventCursor,
    RunHandle,
    RunState,
    RunStream,
    StartRunRequest,
)

_INITIAL_CURSOR_SEQUENCE: int = -1
_ERROR_TOOL_EXECUTOR_NOT_CONFIGURED: str = "tool_executor_not_configured"
_RUN_EVENT_QUEUE_MAX_SIZE: int = 256
_LOGGER: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _RunEventQueueData:
    """RunEvent 队列的数据条目。

    :param event: Host RunEvent。
    """

    event: RunEvent


@dataclass(frozen=True, slots=True)
class _RunEventQueueError:
    """RunEvent 队列的异常条目。

    :param error: 后台执行捕获的异常。
    """

    error: Exception


@dataclass(frozen=True, slots=True)
class _RunEventQueueCompleted:
    """RunEvent 队列的完成哨兵。"""


RunEventQueueItem = (
    _RunEventQueueData | _RunEventQueueError | _RunEventQueueCompleted
)
"""P1 内存队列条目封闭联合。"""


@dataclass(frozen=True, slots=True)
class _NeverCancelledToken:
    """P1 默认未取消 token。"""

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
    """P1 public ``start_run`` 默认工具执行器。"""

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
    """

    proxy: WorkerProxy

    async def start_run(self, request: StartRunRequest) -> RunStream:
        """启动 P1 内存态 Run。

        P1 只提供单 run smoke harness；后台 task 只由事件流队列间接观测，
        本阶段不保存 task handle，也不提供 Host 级取消治理入口。

        :param request: P1 start_run 请求。
        :returns: RunStream，包含句柄与事件流。
        :raises Exception: 构造后台任务失败时透传底层异常；消费事件流时
            重新抛出后台执行捕获的 Engine / WorkerProxy 异常。
        """

        queue: asyncio.Queue[RunEventQueueItem] = asyncio.Queue(
            maxsize=_RUN_EVENT_QUEUE_MAX_SIZE
        )
        asyncio.create_task(self._run_to_queue(request=request, queue=queue))
        _LOGGER.debug(
            "host.run.start_accepted session_id=%s run_id=%s queue_max_size=%s",
            request.session_id,
            request.run_id,
            _RUN_EVENT_QUEUE_MAX_SIZE,
        )
        handle = RunHandle(
            session_id=request.session_id,
            run_id=request.run_id,
            state=RunState.RUNNING,
            event_cursor=RunEventCursor(sequence=_INITIAL_CURSOR_SEQUENCE),
        )
        return RunStream(
            handle=handle,
            events=self._stream_queue(queue),
        )

    async def _run_to_queue(
        self,
        request: StartRunRequest,
        queue: asyncio.Queue[RunEventQueueItem],
    ) -> None:
        """立即执行 Engine 事件流并写入内存队列。

        :param request: P1 start_run 请求。
        :param queue: RunEvent 队列。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常；异常进入队列供消费者观察。
        """

        token = _NeverCancelledToken()
        event_count = 0
        _LOGGER.debug(
            "host.run.background_start session_id=%s run_id=%s",
            request.session_id,
            request.run_id,
        )
        try:
            async for event in self.proxy.stream_engine_events(
                request=request,
                cancellation_token=token,
            ):
                event_count += 1
                await queue.put(
                    _RunEventQueueData(event=translate_engine_event(event))
                )
        except Exception as exc:
            _LOGGER.warning(
                "host.run.background_failed session_id=%s run_id=%s "
                "event_count=%s exc_type=%s",
                request.session_id,
                request.run_id,
                event_count,
                type(exc).__name__,
            )
            await queue.put(_RunEventQueueError(error=exc))
        finally:
            _LOGGER.debug(
                "host.run.background_finished session_id=%s run_id=%s "
                "event_count=%s",
                request.session_id,
                request.run_id,
                event_count,
            )
            await queue.put(_RunEventQueueCompleted())

    async def _stream_queue(
        self,
        queue: asyncio.Queue[RunEventQueueItem],
    ) -> AsyncIterator[RunEvent]:
        """从内存队列读取 Host RunEvent。

        :param queue: RunEvent 队列。
        :returns: RunEvent 异步流。
        :raises Exception: 重新抛出后台执行捕获的异常。
        """

        while True:
            item = await queue.get()
            if isinstance(item, _RunEventQueueData):
                yield item.event
                continue
            if isinstance(item, _RunEventQueueError):
                raise item.error
            break


def _default_harness() -> LocalRunHarness:
    """构造默认 P1 harness。

    :returns: 默认本地 Run harness。
    :raises Exception: 不主动抛出异常。
    """

    executor: ToolExecutor = _NoopToolExecutor()
    return LocalRunHarness(proxy=LocalProxy(worker=EngineWorker(executor)))


async def start_run(request: StartRunRequest) -> RunStream:
    """启动 P1 最小 Run。

    这是 public 测试入口，不暴露 EngineWorker 或 ToolExecutor。需要定制
    ToolExecutor 的测试应使用内部 harness，而不是把 ToolExecutor 提升
    为 Host public API。

    :param request: P1 start_run 请求。
    :returns: RunStream，包含句柄与事件流。
    :raises Exception: 构造后台任务失败时透传底层异常；消费事件流时
        重新抛出后台执行捕获的 Engine / WorkerProxy 异常。
    """

    return await _default_harness().start_run(request)


__all__ = ["LocalRunHarness", "start_run"]
