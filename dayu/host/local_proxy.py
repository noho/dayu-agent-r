"""Host 本地 Engine WorkerProxy。

本模块只把 Host 已构造好的 ``AgentRunRequest`` 交给本地 Engine 函数式
入口，并把 EngineEvent stream 暴露给 dispatch scheduler。它不做
EngineEvent durable ingest、terminal closeout、ToolRuntime 或 recovery。
"""

from __future__ import annotations

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

_LOCAL_WORKER_ID_PREFIX = "local-worker"


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

        del snapshot
        return _DefaultLocalWorkerHandle(
            local_worker_id=f"{_LOCAL_WORKER_ID_PREFIX}-{uuid4().hex}",
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
        self._events: AsyncGenerator[EngineEvent, None] | None = None

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker 诊断 id。

        :returns: 本地 worker id。
        """

        return self._local_worker_id

    def events(self) -> AsyncIterator[EngineEvent]:
        """返回本次 Engine run 的事件流。

        :returns: EngineEvent 异步迭代器。
        """

        if self._events is None:
            self._events = run_agent_messages(self._request)
        return self._events

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

        events = self._events
        if events is not None:
            await events.aclose()


__all__ = [
    "DefaultLocalEngineWorker",
    "DefaultLocalEngineWorkerFactory",
]
