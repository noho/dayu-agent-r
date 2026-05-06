"""Host 内部 WorkerProxy 与 LocalProxy。

P1 仅提供本地代理，RemoteProxy 留待后续 Phase。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from dayu.contracts import CancellationToken
from dayu.engine import EngineEvent
from dayu.host._worker import EngineWorker
from dayu.host.contracts import StartRunRequest


class WorkerProxy(Protocol):
    """Host 内部 worker proxy 协议。"""

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回 EngineEvent 异步流。

        :param request: Host P1 start_run 请求。
        :param cancellation_token: 取消观察 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 透传 worker 运行异常。
        """
        ...


@dataclass(frozen=True, slots=True)
class LocalProxy:
    """本地 EngineWorker 代理。

    :param worker: 本地 EngineWorker。
    """

    worker: EngineWorker

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """代理到本地 EngineWorker。

        :param request: Host P1 start_run 请求。
        :param cancellation_token: 取消观察 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 透传 EngineWorker 运行异常。
        """

        return self.worker.run_agent_messages(
            request=request,
            cancellation_token=cancellation_token,
        )


__all__ = ["LocalProxy", "WorkerProxy"]
