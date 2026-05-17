"""Host 本地 Engine WorkerProxy。

本模块只把 Host 已构造好的 ``AgentRunRequest`` 交给本地 Engine 函数式
入口，并把 EngineEvent stream 暴露给 dispatch scheduler。它不做
EngineEvent durable ingest、terminal closeout、ToolRuntime 或 recovery。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from uuid import uuid4

from dayu.engine import run_agent_messages
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import EngineEvent
from dayu.host.api import (
    AttemptDispatchSnapshot,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
)
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

_LOCAL_WORKER_ID_PREFIX = "local-worker"
_LOGGER = logging.getLogger(__name__)


class DefaultLocalEngineWorkerFactory:
    """默认本地 Engine worker factory。"""

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建默认本地 Engine worker。

        :param snapshot: durable dispatch 快照。
        :returns: 默认本地 Engine worker。
        """

        del snapshot
        return DefaultLocalEngineWorker()


class DefaultLocalEngineWorker:
    """调用 ``run_agent_messages`` 的默认本地 Engine worker。"""

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受一次本地 Engine run。

        :param snapshot: durable dispatch 快照。
        :param request: RunInputBuilder 构造的 Engine 请求。
        :returns: 本地 worker handle。
        """

        local_worker_id = f"{_LOCAL_WORKER_ID_PREFIX}-{uuid4().hex}"
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            (
                "host.local_proxy.accept session_id=%s run_id=%s "
                "attempt_id=%s execution_id=%s dispatch_record_id=%s "
                "local_worker_id=%s message_count=%s disable_tools=%s"
            ),
            snapshot.session_id,
            snapshot.run_id,
            snapshot.attempt_id,
            snapshot.execution_id,
            snapshot.dispatch_record_id,
            local_worker_id,
            len(request.messages),
            request.disable_tools,
        )
        return _DefaultLocalWorkerHandle(
            local_worker_id=local_worker_id,
            request=request,
        )


class _DefaultLocalWorkerHandle:
    """默认本地 worker handle。"""

    def __init__(
        self, *, local_worker_id: str, request: AgentRunRequest
    ) -> None:
        """初始化默认本地 worker handle。

        :param local_worker_id: 本地 worker 诊断 id。
        :param request: Engine run 请求。
        :returns: ``None``。
        :raises ValueError: ``local_worker_id`` 为空时抛出。
        """

        if local_worker_id.strip() == "":
            raise ValueError("local_worker_id must be non-empty")
        self._local_worker_id = local_worker_id
        self._request = request
        self._event_stream: _DefaultLocalWorkerEventStream | None = None
        self._events_started = False
        self._closed = False
        self._close_lock = asyncio.Lock()

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker 诊断 id。

        :returns: 本地 worker id。
        """

        return self._local_worker_id

    def events(self) -> AsyncIterator[EngineEvent]:
        """返回本次 Engine run 的事件流。

        :returns: EngineEvent 异步迭代器。
        :raises RuntimeError: handle 已关闭或事件流已被读取时抛出。
        """

        if self._closed:
            raise RuntimeError("local worker handle is closed")
        if self._events_started:
            raise RuntimeError("local worker events have already been opened")
        self._events_started = True
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.local_proxy.events_opened local_worker_id=%s",
            self._local_worker_id,
        )
        self._event_stream = _DefaultLocalWorkerEventStream(
            run_agent_messages(self._request)
        )
        return self._event_stream

    def cancel(self, reason: str) -> None:
        """向本地 worker 发起 best-effort 取消。

        Phase 5 当前只通过 Host cancellation token 观察取消；本方法保留
        handle 边界，不把 dispatch record 或 lane token 当 worker truth。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason

    async def close(self) -> None:
        """关闭 Engine event stream。

        :returns: ``None``。
        """

        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            event_stream = self._event_stream
        if event_stream is not None:
            await event_stream.close()
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.local_proxy.closed local_worker_id=%s",
            self._local_worker_id,
        )


class _DefaultLocalWorkerEventStream:
    """默认本地 worker event stream 包装器。

    包装器确保一个 handle 只有一个 Engine async generator，并在 handle close
    与消费 task 取消时关闭底层 generator。
    """

    def __init__(self, events: AsyncGenerator[EngineEvent, None]) -> None:
        """初始化 event stream。

        :param events: Engine async generator。
        :returns: ``None``。
        """

        self._events = events
        self._closed = False
        self._lock = asyncio.Lock()
        self._active_anext: asyncio.Task[EngineEvent] | None = None

    def __aiter__(self) -> "_DefaultLocalWorkerEventStream":
        """返回异步迭代器自身。

        :returns: 当前 event stream。
        """

        return self

    async def __anext__(self) -> EngineEvent:
        """读取下一条 EngineEvent。

        :returns: 下一条 EngineEvent。
        :raises StopAsyncIteration: stream 已关闭或底层生成器结束时抛出。
        :raises RuntimeError: 同一 stream 被并发读取时抛出。
        """

        async with self._lock:
            if self._closed:
                raise StopAsyncIteration
            if self._active_anext is not None:
                raise RuntimeError("local worker events are already being consumed")
            task = asyncio.create_task(anext(self._events))
            self._active_anext = task
        try:
            return await task
        except StopAsyncIteration:
            async with self._lock:
                self._closed = True
            raise
        finally:
            async with self._lock:
                if self._active_anext is task:
                    self._active_anext = None

    async def close(self) -> None:
        """关闭 event stream 与底层 Engine generator。

        :returns: ``None``。
        """

        async with self._lock:
            if self._closed:
                return
            self._closed = True
            task = self._active_anext
        if task is not None and not task.done():
            task.cancel()
            try:
                await _suppress_task_cancel(task)
            finally:
                await self._events.aclose()
            return
        await self._events.aclose()


async def _suppress_task_cancel(task: asyncio.Task[EngineEvent]) -> None:
    """等待 task 结束并吞掉取消异常。

    :param task: 待等待 task。
    :returns: ``None``。
    """

    try:
        await task
    except asyncio.CancelledError:
        return


__all__ = [
    "DefaultLocalEngineWorker",
    "DefaultLocalEngineWorkerFactory",
]
