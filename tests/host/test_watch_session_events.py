"""P10.5 Slice 4 session-level live HostEvent watch 测试。"""

from __future__ import annotations

import asyncio
import importlib
import pathlib
import sqlite3
import sys
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.error_codes import EngineRunErrorCode, adapter_error_code
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    ProviderDiagnosticData,
    ReasoningDeltaData,
    RunFailedData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_spec import (
    ClientCorrelationPolicy,
    RunnerCallOptions,
    RunnerSpec,
)
from dayu.engine.contracts.runner_events import RunnerDiagnosticSeverity
from dayu.host import (
    AttemptDispatchSnapshot,
    CancelMode,
    CancelRunRequest,
    CloseSessionRequest,
    EnsureSessionRequest,
    FollowupBehavior,
    Host,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostClosedError,
    HostEvent,
    HostEventClass,
    HostEventKind,
    HostSessionEventDeliveryDetail,
    HostSessionEventDeliveryReason,
    HostSessionEventAdmissionDetail,
    HostSessionEventAdmissionReason,
    HostSessionEvent,
    HostSessionEventIterator,
    HostTerminalStatus,
    HostReasoningDelta,
    HostTransientDelta,
    HostTransientDeltaType,
    LocalEngineWorker,
    LocalWorkerHandle,
    OpenHostOptions,
    HostSessionEventDeliveryPolicy,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    RunSnapshot,
    RunStatus,
    SubmitFollowupRequest,
    open_host,
)
from dayu.host.api import AuthorizationClaim
from dayu.host._execution_health import HostExecutionHealthState
from dayu.host.command import HostCommandHandle
from dayu.host.durable.schema import (
    TABLE_EVENT_LOG,
    TABLE_HOST_ATTEMPTS,
    TABLE_HOST_RUNS,
)
from dayu.host.memory import default_memory_projection_policy
from dayu.host.open_host import (
    _HostSessionEventIterator,
    _PublicHostHandle,
    _SessionEventReconciliationWaiter,
    _read_session_host_events_after,
    _session_live_event_start_cursor,
    _submit_followup,
)
from dayu.host.read_api import _SessionHostEventBatch
from dayu.host.transient_delta import (
    HostTransientDeltaHub,
    HostTransientDeltaSubscription,
    ValidatedTransientDeltaCandidate,
)
from tests.host.transient_stream_support import (
    TransientStreamCounts,
    TransientStreamWorkerFactory,
    event_log_type_count,
    read_transient_durable_snapshot,
    transient_stream_open_host_options,
)

_WORKER_MODE_FINAL = "final"
_WORKER_MODE_BLOCKING = "blocking"
_WORKER_MODE_FAILED = "failed"
_WORKER_MODE_EMPTY_FINAL = "empty_final"
_WORKER_MODE_TRANSIENT_FINAL = "transient_final"
_WORKER_MODE_CONTROLLED_TRANSIENT_FINAL = "controlled_transient_final"
_WORKER_MODE_PAGED_FINAL = "paged_final"
_OPEN_HOST_MODULE = importlib.import_module("dayu.host.open_host")


class _ImmediateFinalAnswerHandle:
    """测试用立即产出 final answer 的 worker handle。"""

    def __init__(self, snapshot: AttemptDispatchSnapshot) -> None:
        """初始化 handle。

        :param snapshot: 当前 dispatch snapshot。
        :returns: ``None``。
        """

        self._snapshot = snapshot

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        """

        return "watch-final-answer-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出 final answer EngineEvent。

        :returns: EngineEvent 异步迭代器。
        """

        yield _final_answer_event(self._snapshot, f"answer:{self._snapshot.run_id}")

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason


class _TransientThenFinalAnswerHandle:
    """测试用依次产出 reasoning delta 与 final answer 的 worker handle。"""

    def __init__(self, snapshot: AttemptDispatchSnapshot) -> None:
        """初始化 handle。

        :param snapshot: 当前 dispatch snapshot。
        :returns: ``None``。
        :raises Exception: 本构造函数不抛出异常。
        """

        self._snapshot = snapshot

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        :raises Exception: 本属性不抛出异常。
        """

        return "watch-transient-final-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """依次产出 reasoning delta 与 final answer。

        :returns: EngineEvent 异步迭代器。
        :raises Exception: 本生成器不主动抛出异常。
        """

        yield EngineEvent(
            occurred_at=datetime(2026, 5, 18, 1, 2, 3, tzinfo=UTC),
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.REASONING_DELTA,
            data=ReasoningDeltaData(
                iteration_id="iteration-1",
                delta="正在分析收入变化",
            ),
            metadata=None,
        )
        yield _final_answer_event(
            self._snapshot,
            f"answer:{self._snapshot.run_id}",
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        :raises Exception: 本方法不抛出异常。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 本方法不抛出异常。
        """

        del reason


class _ControlledTransientThenFinalAnswerHandle:
    """产出一个 transient 后等待 barrier 再提交 terminal 的 worker handle。"""

    def __init__(
        self,
        snapshot: AttemptDispatchSnapshot,
        release_event: asyncio.Event,
    ) -> None:
        """初始化受控 worker handle。

        :param snapshot: 当前 dispatch snapshot。
        :param release_event: 允许 final answer 产出的 barrier。
        :returns: 无返回值。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        self._snapshot = snapshot
        self._release_event = release_event

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        :raises Exception: 本属性不抛出异常。
        """

        return "watch-controlled-transient-final-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """先产出 transient，再等待 barrier 并产出 final answer。

        :returns: EngineEvent 异步迭代器。
        :raises asyncio.CancelledError: worker stream 被关闭时抛出。
        """

        yield EngineEvent(
            occurred_at=datetime(2026, 5, 18, 1, 2, 3, tzinfo=UTC),
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.REASONING_DELTA,
            data=ReasoningDeltaData(
                iteration_id="iteration-controlled",
                delta="正在等待终态屏障",
            ),
            metadata=None,
        )
        await self._release_event.wait()
        yield _final_answer_event(
            self._snapshot,
            f"answer:{self._snapshot.run_id}",
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        :raises Exception: 本方法不抛出异常。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 本方法不抛出异常。
        """

        del reason


class _BlockingFinalAnswerHandle:
    """测试用受控释放 final answer 的 worker handle。"""

    def __init__(
        self, snapshot: AttemptDispatchSnapshot, release_event: asyncio.Event
    ) -> None:
        """初始化 handle。

        :param snapshot: 当前 dispatch snapshot。
        :param release_event: 控制 final answer 产出的事件。
        :returns: ``None``。
        """

        self._snapshot = snapshot
        self._release_event = release_event
        self.cancel_reasons: list[str] = []

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        """

        return "watch-blocking-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """等待测试释放后产出 final answer。

        :returns: EngineEvent 异步迭代器。
        """

        await self._release_event.wait()
        yield _final_answer_event(self._snapshot, f"released:{self._snapshot.run_id}")

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        self.cancel_reasons.append(reason)


class _PagedFinalAnswerHandle:
    """等待 barrier 后产出多页 durable diagnostics 与 final 的 handle。"""

    def __init__(
        self,
        snapshot: AttemptDispatchSnapshot,
        release_event: asyncio.Event,
        diagnostic_count: int,
    ) -> None:
        """初始化多页 durable event handle。

        :param snapshot: 当前 dispatch snapshot。
        :param release_event: 允许开始产出 events 的 barrier。
        :param diagnostic_count: final 前产出的 diagnostic 数量。
        :returns: 无返回值。
        :raises ValueError: diagnostic count 不是正数时抛出。
        """

        if diagnostic_count <= 0:
            raise ValueError("diagnostic_count must be positive")
        self._snapshot = snapshot
        self._release_event = release_event
        self._diagnostic_count = diagnostic_count

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        :raises Exception: 本属性不抛出异常。
        """

        return "watch-paged-final-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出跨至少两页的 durable diagnostics，随后产出 final。

        :returns: EngineEvent 异步迭代器。
        :raises asyncio.CancelledError: worker stream 被关闭时抛出。
        """

        await self._release_event.wait()
        for index in range(self._diagnostic_count):
            yield EngineEvent(
                occurred_at=datetime(2026, 5, 18, 1, 2, 3, tzinfo=UTC),
                session_id=self._snapshot.session_id,
                run_id=self._snapshot.run_id,
                type=EngineEventType.PROVIDER_DIAGNOSTIC,
                data=ProviderDiagnosticData(
                    iteration_id=f"iteration-page-{index}",
                    diagnostic_code="page_padding",
                    severity=RunnerDiagnosticSeverity.WARNING,
                    message=f"page-padding-{index}",
                    provider_request_id=None,
                    raw_payload=None,
                    client_correlation_id=None,
                ),
                metadata=None,
            )
        yield _final_answer_event(
            self._snapshot,
            f"paged:{self._snapshot.run_id}",
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        :raises Exception: 本方法不抛出异常。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 本方法不抛出异常。
        """

        del reason


class _FailedHandle:
    """测试用产出 RUN_FAILED 的 worker handle。"""

    def __init__(self, snapshot: AttemptDispatchSnapshot) -> None:
        """初始化 handle。

        :param snapshot: 当前 dispatch snapshot。
        :returns: ``None``。
        """

        self._snapshot = snapshot

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        """

        return "watch-failed-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出 RUN_FAILED EngineEvent。

        :returns: EngineEvent 异步迭代器。
        """

        yield EngineEvent(
            occurred_at=datetime(2026, 5, 18, 1, 2, 4, tzinfo=UTC),
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.RUN_FAILED,
            data=RunFailedData(
                error_code=adapter_error_code("provider_failed"),
                message="provider failed safely",
                provider_request_id=None,
                recoverable=False,
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason


class _EmptyFinalAnswerHandle:
    """测试用产出 Engine-owned 空 final 失败的 worker handle。"""

    def __init__(self, snapshot: AttemptDispatchSnapshot) -> None:
        """初始化 handle。

        :param snapshot: 当前 dispatch snapshot。
        :returns: ``None``。
        """

        self._snapshot = snapshot

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        """

        return "watch-empty-final-answer-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出 Engine-owned 空 final 失败 EngineEvent。

        :returns: EngineEvent 异步迭代器。
        """

        yield EngineEvent(
            occurred_at=datetime(2026, 5, 18, 1, 2, 5, tzinfo=UTC),
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.RUN_FAILED,
            data=RunFailedData(
                error_code=EngineRunErrorCode.RUNNER_EMPTY_FINAL_CONTENT,
                message="runner did not produce final content",
                provider_request_id=None,
                client_correlation_id=None,
                recoverable=False,
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason


class _HandleWorker:
    """返回预设 handle 的 worker。"""

    def __init__(self, handle: LocalWorkerHandle) -> None:
        """初始化 worker。

        :param handle: accept 后返回的 worker handle。
        :returns: ``None``。
        """

        self._handle = handle

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受 dispatch 并返回预设 handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: worker handle。
        """

        del snapshot, request
        return self._handle


class _Factory:
    """按 dispatch 顺序创建测试 worker 的 factory。"""

    def __init__(
        self,
        mode: str,
        release_event: asyncio.Event | None = None,
        *,
        diagnostic_count: int = 0,
    ) -> None:
        """初始化 factory。

        :param mode: worker 行为模式。
        :param release_event: blocking 模式使用的释放事件。
        :param diagnostic_count: paged final 模式的 durable diagnostic 数量。
        :returns: ``None``。
        """

        self._mode = mode
        self._release_event = release_event
        self._diagnostic_count = diagnostic_count
        self.accepted_event = asyncio.Event()
        self.created_handles: list[LocalWorkerHandle] = []

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建测试 worker。

        :param snapshot: dispatch snapshot。
        :returns: 测试 worker。
        :raises RuntimeError: mode 非法或 blocking 模式未提供释放事件时抛出。
        """

        if self._mode == _WORKER_MODE_FINAL:
            handle: LocalWorkerHandle = _ImmediateFinalAnswerHandle(snapshot)
        elif self._mode == _WORKER_MODE_TRANSIENT_FINAL:
            handle = _TransientThenFinalAnswerHandle(snapshot)
        elif self._mode == _WORKER_MODE_CONTROLLED_TRANSIENT_FINAL:
            if self._release_event is None:
                raise RuntimeError(
                    "controlled transient mode requires release_event"
                )
            handle = _ControlledTransientThenFinalAnswerHandle(
                snapshot,
                self._release_event,
            )
        elif self._mode == _WORKER_MODE_FAILED:
            handle = _FailedHandle(snapshot)
        elif self._mode == _WORKER_MODE_EMPTY_FINAL:
            handle = _EmptyFinalAnswerHandle(snapshot)
        elif self._mode == _WORKER_MODE_BLOCKING:
            if self._release_event is None:
                raise RuntimeError("blocking mode requires release_event")
            handle = _BlockingFinalAnswerHandle(snapshot, self._release_event)
        elif self._mode == _WORKER_MODE_PAGED_FINAL:
            if self._release_event is None:
                raise RuntimeError("paged final mode requires release_event")
            handle = _PagedFinalAnswerHandle(
                snapshot,
                self._release_event,
                self._diagnostic_count,
            )
        else:
            raise RuntimeError("unknown worker mode")
        self.created_handles.append(handle)
        self.accepted_event.set()
        return _HandleWorker(handle)


class _ControlledSessionEventReconciliationWaiter:
    """测试用可逐次释放 timeout、同时响应 owner readiness 的 waiter。"""

    def __init__(self) -> None:
        """初始化独立 opener waiter。

        :returns: 无返回值。
        :raises Exception: asyncio primitive 构造失败时透传。
        """

        self._timeout_signal = asyncio.Event()
        self.wait_call_count = 0
        self.timeout_count = 0

    def release_one_timeout(self) -> None:
        """释放当前或下一次 mailbox-empty timeout。

        :returns: ``None``。
        :raises Exception: 本方法不主动抛出异常。
        """

        self._timeout_signal.set()

    async def wait_for_readiness(
        self,
        subscription: HostTransientDeltaSubscription,
    ) -> bool:
        """竞争 subscription readiness 与测试控制的单次 timeout。

        :param subscription: 当前 iterator 的真实 delivery subscription。
        :returns: owner readiness 获胜时返回 ``True``；测试 timeout 获胜时返回
            ``False``。
        :raises asyncio.CancelledError: iterator 被取消时抛出。
        """

        self.wait_call_count += 1
        readiness_task = asyncio.create_task(
            subscription.wait_ready(3_600.0)
        )
        timeout_task = asyncio.create_task(self._wait_for_timeout_signal())
        done, pending = await asyncio.wait(
            (readiness_task, timeout_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        try:
            if readiness_task in done:
                return readiness_task.result()
            self.timeout_count += 1
            return False
        finally:
            for task in pending:
                task.cancel()
            for task in pending:
                with suppress(asyncio.CancelledError):
                    await task

    async def _wait_for_timeout_signal(self) -> None:
        """等待并消费一个测试 timeout signal。

        :returns: ``None``。
        :raises asyncio.CancelledError: readiness 先到时抛出。
        """

        await self._timeout_signal.wait()
        self._timeout_signal.clear()


class _ReconciliationWaiterFactory:
    """按 opener 创建顺序返回彼此独立的 controlled waiter。"""

    def __init__(
        self,
        waiters: tuple[_ControlledSessionEventReconciliationWaiter, ...],
    ) -> None:
        """初始化 waiter factory。

        :param waiters: 按 opener 进入顺序排列的独立 waiter。
        :returns: 无返回值。
        :raises ValueError: waiter 列表为空时抛出。
        """

        if not waiters:
            raise ValueError("waiters must be non-empty")
        self._waiters = waiters
        self._next_index = 0

    def __call__(self) -> _SessionEventReconciliationWaiter:
        """返回下一个 opener 独占 waiter。

        :returns: 下一个 controlled waiter。
        :raises RuntimeError: opener 数量超过预置 waiter 数时抛出。
        """

        if self._next_index >= len(self._waiters):
            raise RuntimeError("unexpected reconciliation waiter allocation")
        waiter = self._waiters[self._next_index]
        self._next_index += 1
        return waiter


class _TerminalWatermarkHookCallCounter:
    """按 opener 实例记录并转发 local terminal watermark hook。"""

    def __init__(
        self,
        *,
        target_hub: HostTransientDeltaHub,
        hook: Callable[[HostTransientDeltaHub, str, int], bool],
    ) -> None:
        """初始化目标 opener 的本地 hook 计数器。

        :param target_hub: 该计数器唯一允许观测的 opener-local hub。
        :param hook: production 原始未绑定 watermark hook。
        :returns: 无返回值。
        :raises Exception: 本构造函数不抛出异常。
        """

        self._target_hub = target_hub
        self._hook = hook
        self.call_count = 0

    def __call__(
        self,
        hub: HostTransientDeltaHub,
        session_id: str,
        event_sequence: int,
    ) -> bool:
        """记录目标 opener 的调用并转发给 production owner hook。

        :param hub: 实际收到 hook 调用的 opener-local hub。
        :param session_id: notice Session 标识。
        :param event_sequence: notice terminal sequence。
        :returns: production hook 的 watermark 前移结果。
        :raises AssertionError: 调用被错误路由到其它 opener 时抛出。
        :raises Exception: production hook 失败时原样透传。
        """

        if hub is not self._target_hub:
            raise AssertionError("terminal hook routed to unexpected opener")
        if not session_id or event_sequence <= 0:
            raise AssertionError("unexpected invalid terminal watermark hook call")
        self.call_count += 1
        return self._hook(hub, session_id, event_sequence)


class _SessionEventPageReadSpy:
    """记录目标 Session 每次 bounded durable page read 的 cursor。"""

    def __init__(
        self,
        original: Callable[
            [HostCommandHandle, str, int],
            _SessionHostEventBatch,
        ],
    ) -> None:
        """初始化 production read wrapper。

        :param original: production session HostEvent page reader。
        :returns: 无返回值。
        :raises Exception: 本构造函数不主动抛出异常。
        """

        self._original = original
        self._target_session_id: str | None = None
        self._lock = threading.Lock()
        self.cursors: list[int] = []

    def set_target_session(self, session_id: str) -> None:
        """设置唯一记录目标 Session。

        :param session_id: 目标 Session 标识。
        :returns: ``None``。
        :raises ValueError: Session 标识为空时抛出。
        """

        if not session_id:
            raise ValueError("session_id must be non-empty")
        self._target_session_id = session_id

    def __call__(
        self,
        host: HostCommandHandle,
        session_id: str,
        cursor: int,
    ) -> _SessionHostEventBatch:
        """记录 cursor 后调用真实 bounded page reader。

        :param host: actor-owned command handle。
        :param session_id: 读取目标 Session 标识。
        :param cursor: 本页起始 cursor。
        :returns: production bounded page。
        :raises HostApiError: production reader public failure时抛出。
        """

        if session_id == self._target_session_id:
            with self._lock:
                self.cursors.append(cursor)
        return self._original(host, session_id, cursor)


@pytest.mark.asyncio
async def test_two_watchers_observe_same_terminal_event_and_iterator_continues(
    tmp_path: pathlib.Path,
) -> None:
    """两个 watcher 观察同一 terminal，并且 terminal 不结束 iterator。"""

    factory = _Factory(_WORKER_MODE_FINAL)
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request("watch-two"))
        first_watcher = await host.watch_session_events(session.session_id)
        second_watcher = await host.watch_session_events(session.session_id)

        await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-1"),
        )
        first_terminal, second_terminal = await asyncio.gather(
            _next_terminal(first_watcher),
            _next_terminal(second_watcher),
        )

        assert first_terminal.event_id == second_terminal.event_id
        assert first_terminal.event_sequence == second_terminal.event_sequence
        assert first_terminal.dedupe_key == second_terminal.dedupe_key
        assert first_terminal.event_class is HostEventClass.CANONICAL_FACT
        assert first_terminal.event_type == "RUN_SUCCEEDED"
        assert first_terminal.kind is HostEventKind.SUCCEEDED
        assert first_terminal.final_answer is not None
        assert first_terminal.final_answer.content.startswith("answer:")

        await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-2"),
        )
        next_terminal = await _next_terminal(first_watcher)
        assert next_terminal.kind is HostEventKind.SUCCEEDED
        assert next_terminal.event_id != first_terminal.event_id

        await _close_iterator(first_watcher)
        await _close_iterator(second_watcher)


@pytest.mark.asyncio
async def test_watch_attaches_before_return_and_delivers_transient_before_terminal(
    tmp_path: pathlib.Path,
) -> None:
    """watcher 在首次迭代前已 attach，并先交付共享瞬态 envelope。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: attach、fanout、merge 或 zero-row contract 失效时抛出。
    """

    factory = _Factory(_WORKER_MODE_TRANSIENT_FINAL)
    options = _options(tmp_path, factory)
    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request("watch-transient"))
        first_watcher = await host.watch_session_events(session.session_id)
        second_watcher = await host.watch_session_events(session.session_id)

        followup = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-transient"),
        )
        first_delta, second_delta = await asyncio.gather(
            _next_transient(first_watcher),
            _next_transient(second_watcher),
        )

        assert isinstance(first_delta, HostTransientDelta)
        assert isinstance(second_delta, HostTransientDelta)
        assert first_delta is second_delta
        assert first_delta.run_id == followup.accepted_run_id
        assert isinstance(first_delta.data, HostReasoningDelta)
        assert first_delta.data.text_delta == "正在分析收入变化"

        first_terminal, second_terminal = await asyncio.gather(
            _next_terminal(first_watcher),
            _next_terminal(second_watcher),
        )
        assert first_terminal.event_id == second_terminal.event_id
        assert first_terminal.run_id == followup.accepted_run_id
        assert (
            _event_log_type_count(
                options.db_path,
                EngineEventType.REASONING_DELTA.value,
            )
            == 0
        )

        await _close_iterator(first_watcher)
        await _close_iterator(second_watcher)


@pytest.mark.asyncio
async def test_watch_factory_waits_for_actual_cursor_transaction(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cursor transaction 阻塞期间 factory 不返回且只持有 reservation。"""

    cursor_started = threading.Event()
    cursor_release = threading.Event()
    original_cursor = _session_live_event_start_cursor

    def blocked_cursor(handle: HostCommandHandle, session_id: str) -> int:
        """在 actor thread 阻塞实际 cursor transaction。

        :param handle: actor 私有 command handle。
        :param session_id: 目标 Session 标识。
        :returns: durable cursor。
        :raises RuntimeError: barrier 超时时抛出。
        """

        cursor_started.set()
        if not cursor_release.wait(timeout=2):
            raise RuntimeError("cursor barrier timed out")
        return original_cursor(handle, session_id)

    monkeypatch.setattr(
        sys.modules["dayu.host.open_host"],
        "_session_live_event_start_cursor",
        blocked_cursor,
    )
    async with open_host(_options(tmp_path, _Factory(_WORKER_MODE_FINAL))) as host:
        public_host = cast(_PublicHostHandle, host)
        session = await host.ensure_session(_ensure_request("delayed-cursor"))
        watch_task = asyncio.create_task(
            host.watch_session_events(session.session_id)
        )
        assert await asyncio.to_thread(cursor_started.wait, 1)
        assert watch_task.done() is False
        assert (
            public_host._transient_delta_hub.reservation_count(
                session.session_id
            )
            == 1
        )
        assert _subscription_count(host, session.session_id) == 0

        cursor_release.set()
        watcher = await asyncio.wait_for(watch_task, timeout=1)
        assert _subscription_count(host, session.session_id) == 1
        await watcher.aclose()
        assert (
            public_host._transient_delta_hub.reservation_count(
                session.session_id
            )
            == 0
        )


@pytest.mark.asyncio
async def test_watch_cursor_snapshot_to_return_gap_remains_durably_visible(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cursor snapshot 后、factory return 前提交的 durable Run 仍可读取。"""

    accepted_run_ids: list[str] = []
    original_cursor = _session_live_event_start_cursor

    def cursor_then_commit(handle: HostCommandHandle, session_id: str) -> int:
        """先完成 cursor read transaction，再在同 actor operation 提交 Run。

        :param handle: actor 私有 command handle。
        :param session_id: 目标 Session 标识。
        :returns: commit 前读取的 cursor。
        :raises Exception: durable read 或 follow-up commit 失败时透传。
        """

        cursor = original_cursor(handle, session_id)
        followup = _submit_followup(
            handle,
            session_id,
            _followup_request(session_id, "cursor-return-gap"),
        )
        accepted_run_ids.append(followup.accepted_run_id)
        return cursor

    monkeypatch.setattr(
        sys.modules["dayu.host.open_host"],
        "_session_live_event_start_cursor",
        cursor_then_commit,
    )
    async with open_host(_options(tmp_path, _Factory(_WORKER_MODE_FINAL))) as host:
        session = await host.ensure_session(_ensure_request("cursor-gap"))
        watcher = await host.watch_session_events(session.session_id)
        terminal = await _next_terminal(watcher)
        await watcher.aclose()

    assert accepted_run_ids == [terminal.run_id]


@pytest.mark.asyncio
async def test_concurrent_attach_cap_rejects_before_cursor_allocation_and_readmits(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cap+1 在 cursor/task/mailbox 前拒绝，detach 后可 readmit 且 Session 隔离。"""

    cursor_started = threading.Event()
    cursor_release = threading.Event()
    cursor_call_count = 0
    original_cursor = _session_live_event_start_cursor

    def blocked_first_cursor(handle: HostCommandHandle, session_id: str) -> int:
        """只阻塞首个 cursor transaction 并记录调用次数。

        :param handle: actor 私有 command handle。
        :param session_id: 目标 Session 标识。
        :returns: durable cursor。
        :raises RuntimeError: barrier 超时时抛出。
        """

        nonlocal cursor_call_count
        cursor_call_count += 1
        if cursor_call_count == 1:
            cursor_started.set()
            if not cursor_release.wait(timeout=2):
                raise RuntimeError("first cursor barrier timed out")
        return original_cursor(handle, session_id)

    monkeypatch.setattr(
        sys.modules["dayu.host.open_host"],
        "_session_live_event_start_cursor",
        blocked_first_cursor,
    )
    options = replace(
        _options(tmp_path, _Factory(_WORKER_MODE_FINAL)),
        session_event_delivery_policy=HostSessionEventDeliveryPolicy(
            transient_mailbox_max_items=512,
            max_subscriptions_per_session=1,
        ),
    )
    async with open_host(options) as host:
        public_host = cast(_PublicHostHandle, host)
        first_session = await host.ensure_session(_ensure_request("attach-cap"))
        second_session = await host.ensure_session(_ensure_request("attach-other"))
        first_task = asyncio.create_task(
            host.watch_session_events(first_session.session_id)
        )
        assert await asyncio.to_thread(cursor_started.wait, 1)

        with pytest.raises(HostApiError) as exc_info:
            await host.watch_session_events(first_session.session_id)
        assert exc_info.value.code is HostApiErrorCode.RESOURCE_EXHAUSTED
        assert exc_info.value.retryable is True
        assert exc_info.value.detail == HostSessionEventAdmissionDetail(
            reason=(
                HostSessionEventAdmissionReason.SESSION_SUBSCRIPTION_LIMIT_REACHED
            ),
        )
        assert cursor_call_count == 1
        assert _subscription_count(host, first_session.session_id) == 0
        assert (
            public_host._transient_delta_hub.reservation_count(
                first_session.session_id
            )
            == 1
        )

        cursor_release.set()
        first = await asyncio.wait_for(first_task, timeout=1)
        other = await host.watch_session_events(second_session.session_id)
        assert cursor_call_count == 2
        await first.aclose()
        replacement = await host.watch_session_events(first_session.session_id)
        assert cursor_call_count == 3
        await replacement.aclose()
        await other.aclose()


@pytest.mark.asyncio
async def test_watch_factory_cancellation_close_race_and_allocation_failure_release(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """factory 取消、Host close 与 iterator allocation 失败均精确释放 reservation。"""

    cursor_started = threading.Event()
    cursor_release = threading.Event()
    original_cursor = _session_live_event_start_cursor

    def blocked_cursor(handle: HostCommandHandle, session_id: str) -> int:
        """阻塞 cursor operation 以控制 cancellation race。

        :param handle: actor 私有 command handle。
        :param session_id: 目标 Session 标识。
        :returns: durable cursor。
        :raises RuntimeError: barrier 超时时抛出。
        """

        cursor_started.set()
        if not cursor_release.wait(timeout=2):
            raise RuntimeError("cancellation cursor barrier timed out")
        return original_cursor(handle, session_id)

    monkeypatch.setattr(
        sys.modules["dayu.host.open_host"],
        "_session_live_event_start_cursor",
        blocked_cursor,
    )
    manager = open_host(_options(tmp_path, _Factory(_WORKER_MODE_FINAL)))
    host = cast(_PublicHostHandle, await manager.__aenter__())
    session = await host.ensure_session(_ensure_request("factory-cancel"))
    cancelled_task = asyncio.create_task(
        host.watch_session_events(session.session_id)
    )
    assert await asyncio.to_thread(cursor_started.wait, 1)
    cancelled_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_task
    assert host._transient_delta_hub.reservation_count(session.session_id) == 0
    assert _subscription_count(host, session.session_id) == 0
    cursor_release.set()
    await asyncio.sleep(0)

    close_cursor_started = threading.Event()
    close_cursor_release = threading.Event()

    def close_race_cursor(handle: HostCommandHandle, session_id: str) -> int:
        """阻塞第二个 cursor operation 以控制 Host close race。

        :param handle: actor 私有 command handle。
        :param session_id: 目标 Session 标识。
        :returns: durable cursor。
        :raises RuntimeError: barrier 超时时抛出。
        """

        close_cursor_started.set()
        if not close_cursor_release.wait(timeout=2):
            raise RuntimeError("close cursor barrier timed out")
        return original_cursor(handle, session_id)

    monkeypatch.setattr(
        sys.modules["dayu.host.open_host"],
        "_session_live_event_start_cursor",
        close_race_cursor,
    )
    close_watch_task = asyncio.create_task(
        host.watch_session_events(session.session_id)
    )
    assert await asyncio.to_thread(close_cursor_started.wait, 1)
    close_task = asyncio.create_task(host.close())
    while host._health_gate.state is not HostExecutionHealthState.CLOSING:
        await asyncio.sleep(0)
    close_cursor_release.set()
    with pytest.raises(HostClosedError):
        await close_watch_task
    await close_task
    assert host._transient_delta_hub.reservation_count(session.session_id) == 0
    await manager.__aexit__(None, None, None)

    allocation_manager = open_host(
        _options(tmp_path / "allocation", _Factory(_WORKER_MODE_FINAL))
    )
    allocation_host = cast(
        _PublicHostHandle,
        await allocation_manager.__aenter__(),
    )
    allocation_session = await allocation_host.ensure_session(
        _ensure_request("allocation-failure")
    )

    def fail_iterator_allocation(
        self: _HostSessionEventIterator,
        *,
        owner: _PublicHostHandle,
        session_id: str,
        cursor: int,
        subscription: HostTransientDeltaSubscription,
    ) -> None:
        """模拟 iterator allocation 失败。

        :param self: 未完成初始化的 iterator。
        :param owner: public Host handle。
        :param session_id: 目标 Session 标识。
        :param cursor: durable cursor。
        :param subscription: 已注册 subscription。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出测试错误。
        """

        del self, owner, session_id, cursor, subscription
        raise RuntimeError("forced iterator allocation failure")

    monkeypatch.setattr(
        _HostSessionEventIterator,
        "__init__",
        fail_iterator_allocation,
    )
    with pytest.raises(RuntimeError, match="forced iterator allocation failure"):
        await allocation_host.watch_session_events(
            allocation_session.session_id
        )
    assert (
        allocation_host._transient_delta_hub.reservation_count(
            allocation_session.session_id
        )
        == 0
    )
    assert _subscription_count(allocation_host, allocation_session.session_id) == 0
    await allocation_host.close()
    await allocation_manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_capacity_slow_watcher_overflow_does_not_block_fast_watcher_or_terminal(
    tmp_path: pathlib.Path,
) -> None:
    """retained item cap 的慢 watcher overflow 不阻塞快 watcher或 terminal。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: overflow 隔离、typed detail 或 durable facts 漂移时抛出。
    """

    expected_counts = TransientStreamCounts(
        content=171,
        reasoning=171,
        tool_call=171,
    )
    factory = TransientStreamWorkerFactory(
        counts=expected_counts,
        final_answer="capacity-overflow-final",
    )
    options = transient_stream_open_host_options(tmp_path, factory)
    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request("capacity-overflow"))
        slow_watcher = await host.watch_session_events(session.session_id)
        fast_watcher = await host.watch_session_events(session.session_id)
        fast_task = asyncio.create_task(_collect_mixed_stream_until_terminal(fast_watcher))
        followup = await host.submit_followup(
            session.session_id,
            _followup_request(
                session.session_id,
                "capacity-overflow-followup",
            ),
        )

        fast_counts, fast_terminal = await asyncio.wait_for(fast_task, timeout=20.0)
        slow_prefix: list[HostTransientDelta] = []
        with pytest.raises(HostApiError) as exc_info:
            while True:
                event = await asyncio.wait_for(anext(slow_watcher), timeout=2.0)
                if not isinstance(event, HostTransientDelta):
                    raise AssertionError(
                        "slow watcher received durable event before overflow"
                    )
                slow_prefix.append(event)

        run = await host.get_run(followup.accepted_run_id)
        await _close_iterator(fast_watcher)
        await _close_iterator(slow_watcher)

    assert len(slow_prefix) == 512
    assert [event.worker_event_index for event in slow_prefix] == list(
        range(1, 513)
    )
    assert fast_counts == expected_counts
    assert fast_terminal.kind is HostEventKind.SUCCEEDED
    assert fast_terminal.final_answer is not None
    assert fast_terminal.final_answer.content == "capacity-overflow-final"
    assert run.status is RunStatus.SUCCEEDED
    assert factory.cancel_reasons == []

    overflow = exc_info.value
    assert overflow.code is HostApiErrorCode.DELIVERY_INTERRUPTED
    assert overflow.retryable is False
    assert overflow.detail == HostSessionEventDeliveryDetail(
        reason=HostSessionEventDeliveryReason.TRANSIENT_MAILBOX_OVERFLOW,
    )
    assert event_log_type_count(options.db_path, EngineEventType.CONTENT_DELTA.value) == 0
    assert event_log_type_count(options.db_path, EngineEventType.REASONING_DELTA.value) == 0
    assert event_log_type_count(options.db_path, EngineEventType.TOOL_CALL_DELTA.value) == 0
    assert event_log_type_count(options.db_path, "RUN_SUCCEEDED") == 1
    durable = read_transient_durable_snapshot(
        options.db_path,
        run_id=followup.accepted_run_id,
    )
    assert durable.run_status == "succeeded"
    assert durable.attempt_status == "succeeded"
    assert durable.run_terminal_event_id == fast_terminal.event_id
    assert durable.run_terminal_event_sequence == fast_terminal.event_sequence


@pytest.mark.asyncio
async def test_same_run_prefix_hands_off_to_terminal_before_different_run_head(
    tmp_path: pathlib.Path,
) -> None:
    """A mailbox prefix 必须先于 A terminal，B head 必须保留到 terminal 后。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: prefix、terminal 或 different-Run 顺序漂移时抛出。
    """

    terminal_release = asyncio.Event()
    factory = _Factory(
        _WORKER_MODE_CONTROLLED_TRANSIENT_FINAL,
        terminal_release,
    )
    options = _options(tmp_path, factory)
    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request("terminal-handoff"))
        watcher = await host.watch_session_events(session.session_id)
        assert isinstance(watcher, _HostSessionEventIterator)
        followup = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "terminal-handoff-a"),
        )
        for _ in range(500):
            if watcher._subscription.retained_items == 1:
                break
            await asyncio.sleep(0)
        assert watcher._subscription.retained_items == 1

        terminal_release.set()
        await _wait_run_terminal(host, followup.accepted_run_id)
        durable = read_transient_durable_snapshot(
            options.db_path,
            run_id=followup.accepted_run_id,
        )
        _publish_fenced_reasoning_delta(
            host,
            session_id=session.session_id,
            run_id="run-b-retained-head",
            attempt_id="attempt-b-retained-head",
            execution_id="execution-b-retained-head",
            durable_causal_fence_event_sequence=(
                durable.run_terminal_event_sequence
            ),
            worker_event_index=1,
        )
        assert watcher._subscription.retained_items == 2

        observed: list[HostSessionEvent] = []
        for _ in range(200):
            event = await asyncio.wait_for(anext(watcher), timeout=2.0)
            if (
                isinstance(event, HostTransientDelta)
                and event.run_id
                in {followup.accepted_run_id, "run-b-retained-head"}
            ):
                observed.append(event)
            elif (
                isinstance(event, HostEvent)
                and event.run_id == followup.accepted_run_id
                and event.terminal_status is not None
            ):
                observed.append(event)
            if len(observed) == 3:
                break

        assert len(observed) == 3
        first, second, third = observed
        assert isinstance(first, HostTransientDelta)
        assert first.run_id == followup.accepted_run_id
        assert isinstance(second, HostEvent)
        assert second.run_id == followup.accepted_run_id
        assert second.terminal_status is HostTerminalStatus.SUCCEEDED
        assert isinstance(third, HostTransientDelta)
        assert third.run_id == "run-b-retained-head"
        await _close_iterator(watcher)


@pytest.mark.asyncio
async def test_dual_opener_b_fence_catches_up_pages_before_terminal_handoff(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C opener 不接收 A local notice，B fence 仍强制多页追平 A terminal。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: opener-local waiter 与 page-read 观测注入工具。
    :returns: ``None``。
    :raises AssertionError: opener 隔离、fence 或 cursor/page 顺序漂移时抛出。
    """

    release_a = asyncio.Event()
    release_b = asyncio.Event()
    factory_a = _Factory(
        _WORKER_MODE_PAGED_FINAL,
        release_a,
        diagnostic_count=140,
    )
    factory_c = _Factory(_WORKER_MODE_BLOCKING, release_b)
    waiter_a = _ControlledSessionEventReconciliationWaiter()
    waiter_c = _ControlledSessionEventReconciliationWaiter()
    waiter_factory = _ReconciliationWaiterFactory((waiter_a, waiter_c))
    original_terminal_watermark_hook = (
        HostTransientDeltaHub.advance_committed_terminal_event_sequence_high_watermark
    )
    page_read_spy = _SessionEventPageReadSpy(
        _read_session_host_events_after
    )
    monkeypatch.setattr(
        _OPEN_HOST_MODULE,
        "_new_session_event_reconciliation_waiter",
        waiter_factory,
    )
    monkeypatch.setattr(
        _OPEN_HOST_MODULE,
        "_read_session_host_events_after",
        page_read_spy,
    )
    shared_db_path = tmp_path / "shared-host.sqlite3"
    shared_lane_db_path = tmp_path / "shared-lane.sqlite3"
    options_a = replace(
        _options(tmp_path / "opener-a", factory_a),
        db_path=shared_db_path,
        lane_db_path=shared_lane_db_path,
    )
    options_c = replace(
        _options(tmp_path / "opener-c", factory_c),
        db_path=shared_db_path,
        lane_db_path=shared_lane_db_path,
    )
    assert options_a.db_path == options_c.db_path
    assert options_a.lane_db_path == options_c.lane_db_path
    assert options_a.artifact_root != options_c.artifact_root
    assert options_a.worker_factory is not options_c.worker_factory

    manager_a = open_host(options_a)
    host_a = await manager_a.__aenter__()
    manager_c = open_host(options_c)
    watcher: HostSessionEventIterator | None = None
    first_next: asyncio.Task[HostSessionEvent] | None = None
    try:
        session = await host_a.ensure_session(_ensure_request("dual-opener-fence"))
        run_a = await host_a.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "dual-opener-run-a"),
        )
        await asyncio.wait_for(factory_a.accepted_event.wait(), timeout=2.0)

        host_c = await manager_c.__aenter__()
        assert isinstance(host_a, _PublicHostHandle)
        assert isinstance(host_c, _PublicHostHandle)
        hub_a = host_a._transient_delta_hub
        hub_c = host_c._transient_delta_hub
        hook_calls_a = _TerminalWatermarkHookCallCounter(
            target_hub=hub_a,
            hook=original_terminal_watermark_hook,
        )
        hook_calls_c = _TerminalWatermarkHookCallCounter(
            target_hub=hub_c,
            hook=original_terminal_watermark_hook,
        )

        def _record_instance_terminal_watermark_hook(
            hub: HostTransientDeltaHub,
            session_id: str,
            event_sequence: int,
        ) -> bool:
            """把 class hook 调用路由到对应 opener 实例计数器。

            :param hub: 实际收到调用的 opener-local hub。
            :param session_id: notice Session 标识。
            :param event_sequence: notice terminal sequence。
            :returns: 对应 opener production hook 的 watermark 前移结果。
            :raises AssertionError: 未登记 opener 收到调用时抛出。
            :raises Exception: production hook 失败时原样透传。
            """

            if hub is hub_a:
                return hook_calls_a(hub, session_id, event_sequence)
            if hub is hub_c:
                return hook_calls_c(hub, session_id, event_sequence)
            raise AssertionError("terminal hook called for unknown opener")

        monkeypatch.setattr(
            HostTransientDeltaHub,
            "advance_committed_terminal_event_sequence_high_watermark",
            _record_instance_terminal_watermark_hook,
        )
        page_read_spy.set_target_session(session.session_id)
        watcher = await host_c.watch_session_events(session.session_id)
        first_next = asyncio.create_task(anext(watcher))
        await _wait_for_wait_call_count(waiter_c, 1)
        pre_action_a_watermark = (
            hub_a.committed_terminal_event_sequence_high_watermark(
                session.session_id
            )
        )
        pre_action_c_watermark = (
            hub_c.committed_terminal_event_sequence_high_watermark(
                session.session_id
            )
        )
        assert pre_action_a_watermark == 0
        assert pre_action_c_watermark == 0

        release_a.set()
        terminal_a = await _wait_run_terminal(host_a, run_a.accepted_run_id)
        assert terminal_a.status is RunStatus.SUCCEEDED
        assert first_next.done() is False
        assert page_read_spy.cursors == []
        assert hook_calls_a.call_count >= 1
        assert (
            hub_a.committed_terminal_event_sequence_high_watermark(
                session.session_id
            )
            > pre_action_a_watermark
        )
        assert hook_calls_c.call_count == 0
        assert (
            hub_c.committed_terminal_event_sequence_high_watermark(
                session.session_id
            )
            == pre_action_c_watermark
        )

        run_b = await host_c.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "dual-opener-run-b"),
        )
        await asyncio.wait_for(factory_c.accepted_event.wait(), timeout=2.0)
        attempt_id, execution_id, b_fence = (
            _attempt_identity_and_started_sequence(
                options_c.db_path,
                run_id=run_b.accepted_run_id,
            )
        )
        _publish_fenced_reasoning_delta(
            host_c,
            session_id=session.session_id,
            run_id=run_b.accepted_run_id,
            attempt_id=attempt_id,
            execution_id=execution_id,
            durable_causal_fence_event_sequence=b_fence,
            worker_event_index=1,
        )
        assert isinstance(watcher, _HostSessionEventIterator)
        assert watcher._subscription.retained_items == 1

        observed_terminal_a: HostEvent | None = None
        observed_b: HostTransientDelta | None = None
        event = await asyncio.wait_for(first_next, timeout=2.0)
        first_next = None
        for _ in range(500):
            if (
                isinstance(event, HostEvent)
                and event.run_id == run_a.accepted_run_id
                and event.terminal_status is not None
            ):
                observed_terminal_a = event
            if (
                isinstance(event, HostTransientDelta)
                and event.run_id == run_b.accepted_run_id
            ):
                observed_b = event
                break
            assert watcher._subscription.retained_items == 1
            event = await asyncio.wait_for(anext(watcher), timeout=2.0)

        assert observed_terminal_a is not None
        assert observed_terminal_a.terminal_status is HostTerminalStatus.SUCCEEDED
        assert observed_b is not None
        assert len(page_read_spy.cursors) >= 3
        assert page_read_spy.cursors == sorted(set(page_read_spy.cursors))
        assert waiter_c.timeout_count == 0
        assert hook_calls_c.call_count == 0
        assert (
            hub_c.committed_terminal_event_sequence_high_watermark(
                session.session_id
            )
            == pre_action_c_watermark
        )
        assert (
            b_fence
            > observed_terminal_a.event_sequence
        )
    finally:
        if first_next is not None and not first_next.done():
            first_next.cancel()
            with suppress(asyncio.CancelledError):
                await first_next
        if watcher is not None:
            await watcher.aclose()
        await manager_c.__aexit__(None, None, None)
        await manager_a.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_dual_opener_empty_mailbox_reconciles_one_page_per_timeout_and_close_wakes(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C 每次 empty-mailbox timeout 只读一页，且 close 不等待下一 tick。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: opener-local waiter 与 page-read 观测注入工具。
    :returns: ``None``。
    :raises AssertionError: periodic reconcile 或 close readiness 漂移时抛出。
    """

    release_a = asyncio.Event()
    factory_a = _Factory(
        _WORKER_MODE_PAGED_FINAL,
        release_a,
        diagnostic_count=140,
    )
    factory_c = _Factory(_WORKER_MODE_BLOCKING, asyncio.Event())
    waiter_a = _ControlledSessionEventReconciliationWaiter()
    waiter_c = _ControlledSessionEventReconciliationWaiter()
    monkeypatch.setattr(
        _OPEN_HOST_MODULE,
        "_new_session_event_reconciliation_waiter",
        _ReconciliationWaiterFactory((waiter_a, waiter_c)),
    )
    page_read_spy = _SessionEventPageReadSpy(
        _read_session_host_events_after
    )
    monkeypatch.setattr(
        _OPEN_HOST_MODULE,
        "_read_session_host_events_after",
        page_read_spy,
    )

    shared_db_path = tmp_path / "shared-host.sqlite3"
    shared_lane_db_path = tmp_path / "shared-lane.sqlite3"
    options_a = replace(
        _options(tmp_path / "opener-a", factory_a),
        db_path=shared_db_path,
        lane_db_path=shared_lane_db_path,
    )
    options_c = replace(
        _options(tmp_path / "opener-c", factory_c),
        db_path=shared_db_path,
        lane_db_path=shared_lane_db_path,
    )
    assert options_a.db_path == options_c.db_path
    assert options_a.lane_db_path == options_c.lane_db_path
    assert options_a.artifact_root != options_c.artifact_root
    assert options_a.worker_factory is not options_c.worker_factory
    manager_a = open_host(options_a)
    host_a = await manager_a.__aenter__()
    manager_c = open_host(options_c)
    watcher: HostSessionEventIterator | None = None
    next_task: asyncio.Task[HostSessionEvent] | None = None
    try:
        session = await host_a.ensure_session(
            _ensure_request("dual-opener-periodic")
        )
        run_a = await host_a.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "dual-opener-periodic-a"),
        )
        await asyncio.wait_for(factory_a.accepted_event.wait(), timeout=2.0)
        host_c = await manager_c.__aenter__()
        page_read_spy.set_target_session(session.session_id)
        watcher = await host_c.watch_session_events(session.session_id)
        next_task = asyncio.create_task(anext(watcher))
        await _wait_for_wait_call_count(waiter_c, 1)

        release_a.set()
        await _wait_run_terminal(host_a, run_a.accepted_run_id)
        assert next_task.done() is False
        assert page_read_spy.cursors == []
        assert isinstance(host_c, _PublicHostHandle)
        assert (
            host_c._transient_delta_hub.committed_terminal_event_sequence_high_watermark(
                session.session_id
            )
            == 0
        )

        current_wait_call = 1
        observed_terminal: HostEvent | None = None
        while observed_terminal is None:
            before_page_count = len(page_read_spy.cursors)
            waiter_c.release_one_timeout()
            assert next_task is not None
            event = await asyncio.wait_for(next_task, timeout=2.0)
            next_task = None
            assert len(page_read_spy.cursors) == before_page_count + 1
            if (
                isinstance(event, HostEvent)
                and event.run_id == run_a.accepted_run_id
                and event.terminal_status is not None
            ):
                observed_terminal = event
                break

            while observed_terminal is None:
                next_task = asyncio.create_task(anext(watcher))
                completed = await _wait_for_task_or_wait_call(
                    next_task,
                    waiter_c,
                    current_wait_call + 1,
                )
                if not completed:
                    current_wait_call += 1
                    break
                event = await next_task
                next_task = None
                if (
                    isinstance(event, HostEvent)
                    and event.run_id == run_a.accepted_run_id
                    and event.terminal_status is not None
                ):
                    observed_terminal = event

        assert observed_terminal is not None
        assert observed_terminal.terminal_status is HostTerminalStatus.SUCCEEDED
        assert len(page_read_spy.cursors) >= 3
        assert waiter_c.timeout_count == len(page_read_spy.cursors)
        assert page_read_spy.cursors == sorted(set(page_read_spy.cursors))

        next_task = asyncio.create_task(anext(watcher))
        await _wait_for_wait_call_count(waiter_c, current_wait_call + 1)
        close_task = asyncio.create_task(host_c.close())
        await asyncio.wait_for(close_task, timeout=2.0)
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(next_task, timeout=0.5)
        next_task = None
    finally:
        if next_task is not None and not next_task.done():
            next_task.cancel()
            with suppress(asyncio.CancelledError):
                await next_task
        if watcher is not None:
            await watcher.aclose()
        await manager_c.__aexit__(None, None, None)
        await manager_a.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_consumer_early_cancel_does_not_cancel_run_or_write_eventlog(
    tmp_path: pathlib.Path,
) -> None:
    """consumer 提前取消只关闭订阅，不取消 Run、不写 EventLog。"""

    release_event = asyncio.Event()
    factory = _Factory(_WORKER_MODE_BLOCKING, release_event)
    options = _options(tmp_path, factory)
    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request("watch-cancel"))
        watcher = await host.watch_session_events(session.session_id)
        consumer = asyncio.create_task(_consume_forever(watcher))

        followup = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-blocking"),
        )
        await asyncio.wait_for(factory.accepted_event.wait(), timeout=2.0)
        await _wait_run_status(host, followup.accepted_run_id, RunStatus.RUNNING)
        before_cancel = await _stable_event_log_count(options.db_path)

        consumer.cancel()
        with suppress(asyncio.CancelledError):
            await consumer
        after_cancel = _event_log_count(options.db_path)

        assert after_cancel == before_cancel
        run = await host.get_run(followup.accepted_run_id)
        assert run.status is RunStatus.RUNNING
        blocking_handle = cast(_BlockingFinalAnswerHandle, factory.created_handles[0])
        assert blocking_handle.cancel_reasons == []

        release_event.set()
        terminal = await _wait_run_terminal(host, followup.accepted_run_id)
        assert terminal.status is RunStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_watch_never_started_first_cancel_missing_and_host_close_cleanup(
    tmp_path: pathlib.Path,
) -> None:
    """never-started、首次取消、missing 与 Host close 均回收 subscription。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: public error 或 subscription cleanup contract 漂移时抛出。
    """

    manager = open_host(_options(tmp_path, _Factory(_WORKER_MODE_FINAL)))
    host = await manager.__aenter__()
    session = await host.ensure_session(_ensure_request("watch-cleanup"))

    never_started = await host.watch_session_events(session.session_id)
    assert _subscription_count(host, session.session_id) == 1
    await _close_iterator(never_started)
    assert _subscription_count(host, session.session_id) == 0

    with pytest.raises(HostApiError) as missing_exc:
        await host.watch_session_events("missing-session")
    assert missing_exc.value.code is HostApiErrorCode.NOT_FOUND
    assert missing_exc.value.retryable is False
    assert _subscription_count(host, "missing-session") == 0

    first_cancel = await host.watch_session_events(session.session_id)
    first_next = asyncio.ensure_future(anext(first_cancel))
    await asyncio.sleep(0.05)
    assert _subscription_count(host, session.session_id) == 1
    first_next.cancel()
    with suppress(asyncio.CancelledError):
        await first_next
    assert _subscription_count(host, session.session_id) == 0

    started = await host.watch_session_events(session.session_id)
    await host.submit_followup(
        session.session_id,
        _followup_request(session.session_id, "started-aclose-run"),
    )
    started_terminal = await _next_terminal(started)
    assert started_terminal.kind is HostEventKind.SUCCEEDED
    assert _subscription_count(host, session.session_id) == 1
    await _close_iterator(started)
    assert _subscription_count(host, session.session_id) == 0

    close_watcher = await host.watch_session_events(session.session_id)
    close_next = asyncio.ensure_future(anext(close_watcher))
    await asyncio.sleep(0.05)
    await host.close()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(close_next, timeout=1.0)
    assert _subscription_count(host, session.session_id) == 0
    with pytest.raises(HostClosedError):
        await host.watch_session_events(session.session_id)
    await manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_watch_cancel_after_first_delta_detaches_without_cancelling_run(
    tmp_path: pathlib.Path,
) -> None:
    """后续 iteration cancel 只 detach watcher，不改变正在运行的 Run。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: detach、Run 或 worker cancel contract 漂移时抛出。
    """

    terminal_release = asyncio.Event()
    factory = TransientStreamWorkerFactory(
        counts=TransientStreamCounts(content=0, reasoning=1, tool_call=0),
        final_answer="post-delta-cancel-final",
        terminal_release_event=terminal_release,
    )
    async with open_host(
        transient_stream_open_host_options(tmp_path, factory)
    ) as host:
        session = await host.ensure_session(_ensure_request("post-delta-cancel"))
        watcher = await host.watch_session_events(session.session_id)
        followup = await host.submit_followup(
            session.session_id,
            _followup_request(
                session.session_id,
                "post-delta-cancel-followup",
            ),
        )
        transient = await _next_transient(watcher)
        assert transient.run_id == followup.accepted_run_id
        await asyncio.wait_for(factory.deltas_finished_event.wait(), timeout=1.0)
        before_cancel = await _wait_run_status(
            host,
            followup.accepted_run_id,
            RunStatus.RUNNING,
        )

        await _cancel_pending_next_iteration(watcher)

        assert _subscription_count(host, session.session_id) == 0
        after_cancel = await host.get_run(followup.accepted_run_id)
        assert before_cancel.status is RunStatus.RUNNING
        assert after_cancel.status is RunStatus.RUNNING
        assert factory.cancel_reasons == []

        terminal_release.set()
        terminal_run = await _wait_run_terminal(host, followup.accepted_run_id)
        assert terminal_run.status is RunStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_watch_does_not_replay_pre_attach_transient_and_keeps_first_post_attach_delta(
    tmp_path: pathlib.Path,
) -> None:
    """attach 前 delta 不 replay，返回后的下一 Run 首个 delta 不丢。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: live-only attach 边界或下一 Run fence 漂移时抛出。
    """

    factory = TransientStreamWorkerFactory(
        counts=TransientStreamCounts(content=1, reasoning=1, tool_call=1),
        final_answer="attach-boundary-final",
    )
    async with open_host(
        transient_stream_open_host_options(tmp_path, factory)
    ) as host:
        session = await host.ensure_session(_ensure_request("attach-boundary"))
        first = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "pre-attach-run"),
        )
        await _wait_run_terminal(host, first.accepted_run_id)

        watcher = await host.watch_session_events(session.session_id)
        second = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "post-attach-run"),
        )
        first_post_attach_delta = await _next_transient(watcher)
        terminal = await _next_terminal(watcher)

        assert first_post_attach_delta.run_id == second.accepted_run_id
        assert first_post_attach_delta.run_id != first.accepted_run_id
        assert terminal.run_id == second.accepted_run_id
        await _close_iterator(watcher)


@pytest.mark.asyncio
async def test_watch_first_and_subsequent_durable_failures_are_public_and_detach(
    tmp_path: pathlib.Path,
) -> None:
    """首次及 transient 后 durable read failure 均映射为 public error 并 detach。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: typed error mapping 或 subscription cleanup 漂移时抛出。
    """

    first_path = tmp_path / "first"
    first_options = _options(first_path, _Factory(_WORKER_MODE_FINAL))
    async with open_host(first_options) as host:
        session = await host.ensure_session(_ensure_request("durable-failure-first"))
        watcher = await host.watch_session_events(session.session_id)
        followup = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "durable-failure-first-run"),
        )
        await _wait_run_terminal(host, followup.accepted_run_id)
        durable = read_transient_durable_snapshot(
            first_options.db_path,
            run_id=followup.accepted_run_id,
        )
        original_payload = _replace_event_payload(
            first_options.db_path,
            event_id=durable.terminal_event_id,
            payload_json="{",
        )
        with pytest.raises(HostApiError) as first_exc:
            await anext(watcher)
        _replace_event_payload(
            first_options.db_path,
            event_id=durable.terminal_event_id,
            payload_json=original_payload,
        )
        _assert_public_durable_failure(first_exc.value)
        assert _subscription_count(host, session.session_id) == 0

    subsequent_path = tmp_path / "subsequent"
    subsequent_release = asyncio.Event()
    subsequent_factory = _Factory(
        _WORKER_MODE_CONTROLLED_TRANSIENT_FINAL,
        subsequent_release,
    )
    subsequent_options = _options(
        subsequent_path,
        subsequent_factory,
    )
    async with open_host(subsequent_options) as host:
        session = await host.ensure_session(
            _ensure_request("durable-failure-subsequent")
        )
        watcher = await host.watch_session_events(session.session_id)
        followup = await host.submit_followup(
            session.session_id,
            _followup_request(
                session.session_id,
                "durable-failure-subsequent-run",
            ),
        )
        transient = await _next_transient(watcher)
        assert transient.run_id == followup.accepted_run_id
        subsequent_release.set()
        await _wait_run_terminal(host, followup.accepted_run_id)
        durable = read_transient_durable_snapshot(
            subsequent_options.db_path,
            run_id=followup.accepted_run_id,
        )
        original_payload = _replace_event_payload(
            subsequent_options.db_path,
            event_id=durable.terminal_event_id,
            payload_json="{",
        )
        with pytest.raises(HostApiError) as subsequent_exc:
            while True:
                event = await anext(watcher)
                if isinstance(event, HostEvent) and event.terminal_status is not None:
                    raise AssertionError(
                        "corrupt durable terminal was exposed as a public terminal"
                    )
        _replace_event_payload(
            subsequent_options.db_path,
            event_id=durable.terminal_event_id,
            payload_json=original_payload,
        )
        _assert_public_durable_failure(subsequent_exc.value)
        assert _subscription_count(host, session.session_id) == 0


@pytest.mark.asyncio
async def test_failed_and_cancelled_terminal_events_are_typed(
    tmp_path: pathlib.Path,
) -> None:
    """FAILED / CANCELLED terminal HostEvent 提供 typed status 与展示字段。"""

    failed_factory = _Factory(_WORKER_MODE_FAILED)
    async with open_host(_options(tmp_path / "failed", failed_factory)) as host:
        session = await host.ensure_session(_ensure_request("watch-failed"))
        watcher = await host.watch_session_events(session.session_id)
        await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-failed"),
        )
        failed = await _next_terminal(watcher)
        assert failed.kind is HostEventKind.FAILED
        assert failed.event_class is HostEventClass.CANONICAL_FACT
        assert failed.event_type == "RUN_FAILED"
        assert failed.terminal_status is HostTerminalStatus.FAILED
        assert failed.error_message == "provider failed safely"
        assert failed.final_answer is None
        await _close_iterator(watcher)

    release_event = asyncio.Event()
    cancel_factory = _Factory(_WORKER_MODE_BLOCKING, release_event)
    async with open_host(_options(tmp_path / "cancelled", cancel_factory)) as host:
        session = await host.ensure_session(_ensure_request("watch-cancelled"))
        watcher = await host.watch_session_events(session.session_id)
        await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-active"),
        )
        await asyncio.wait_for(cancel_factory.accepted_event.wait(), timeout=2.0)
        queued = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-queued"),
        )

        await host.cancel_run(
            queued.accepted_run_id,
            CancelRunRequest(
                context=_context("cancel-queued"),
                client_request_id="cancel-queued",
                reason="user_stop_queued",
                mode=CancelMode.GRACEFUL,
            ),
        )
        cancelled = await _next_terminal(watcher)

        assert cancelled.kind is HostEventKind.CANCELLED
        assert cancelled.event_class is HostEventClass.CANONICAL_FACT
        assert cancelled.event_type == "RUN_CANCELLED"
        assert cancelled.terminal_status is HostTerminalStatus.CANCELLED
        assert cancelled.cancel_reason == "user_stop_queued"
        assert cancelled.final_answer is None

        release_event.set()
        await _close_iterator(watcher)


@pytest.mark.asyncio
async def test_empty_final_answer_terminal_projects_as_failed_event(
    tmp_path: pathlib.Path,
) -> None:
    """Engine-owned 空 final 失败会投影为 failed HostEvent。"""

    factory = _Factory(_WORKER_MODE_EMPTY_FINAL)
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request("watch-empty-final"))
        watcher = await host.watch_session_events(session.session_id)
        await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-empty-final"),
        )
        terminal = await _next_terminal(watcher)

    assert terminal.kind is HostEventKind.FAILED
    assert terminal.event_class is HostEventClass.CANONICAL_FACT
    assert terminal.event_type == "RUN_FAILED"
    assert terminal.terminal_status is HostTerminalStatus.FAILED
    assert terminal.final_answer is None
    assert terminal.error_message is not None
    assert "runner did not produce final content" in terminal.error_message


@pytest.mark.asyncio
async def test_watch_lifecycle_errors_and_closed_session_watch(
    tmp_path: pathlib.Path,
) -> None:
    """watch 校验 handle close、missing Session 与 Session CLOSED 语义。"""

    factory = _Factory(_WORKER_MODE_FINAL)
    manager = open_host(_options(tmp_path, factory))
    host = await manager.__aenter__()
    await host.close()
    with pytest.raises(HostClosedError):
        await host.watch_session_events("missing-session")
    await manager.__aexit__(None, None, None)

    async with open_host(
        _options(tmp_path / "open", _Factory(_WORKER_MODE_FINAL))
    ) as host:
        with pytest.raises(HostApiError) as exc_info:
            await host.watch_session_events("missing-session")
        assert exc_info.value.code is HostApiErrorCode.NOT_FOUND

        session = await host.ensure_session(_ensure_request("watch-closed"))
        await host.close_session(
            session.session_id,
            CloseSessionRequest(
                context=_context("close-session"),
                client_request_id="close-session",
                reason="user_closed_input",
            ),
        )
        watcher = await host.watch_session_events(session.session_id)
        await _close_iterator(watcher)


async def _next_terminal(iterator: AsyncIterator[HostSessionEvent]) -> HostEvent:
    """读取下一条 terminal HostEvent。

    :param iterator: HostEvent async iterator。
    :returns: 下一条 terminal HostEvent。
    :raises AssertionError: 超时仍未读取到 terminal 时抛出。
    """

    return await asyncio.wait_for(_read_next_terminal(iterator), timeout=2.0)


async def _collect_mixed_stream_until_terminal(
    iterator: AsyncIterator[HostSessionEvent],
) -> tuple[TransientStreamCounts, HostEvent]:
    """快速消费 watcher，统计三类 delta 并返回成功 terminal。

    :param iterator: Host Session event iterator。
    :returns: 三类 delta 计数与成功 terminal。
    :raises AssertionError: watcher 提前结束或出现非成功 terminal 时抛出。
    """

    content_count = 0
    reasoning_count = 0
    tool_call_count = 0
    async for event in iterator:
        if isinstance(event, HostTransientDelta):
            if event.type is HostTransientDeltaType.CONTENT_DELTA:
                content_count += 1
            elif event.type is HostTransientDeltaType.REASONING_DELTA:
                reasoning_count += 1
            elif event.type is HostTransientDeltaType.TOOL_CALL_DELTA:
                tool_call_count += 1
            else:
                raise AssertionError(f"unexpected transient type: {event.type}")
            continue
        if event.kind is HostEventKind.SUCCEEDED:
            return (
                TransientStreamCounts(
                    content=content_count,
                    reasoning=reasoning_count,
                    tool_call=tool_call_count,
                ),
                event,
            )
        if event.terminal_status is not None:
            raise AssertionError(f"unexpected terminal kind: {event.kind}")
    raise AssertionError("watcher ended before terminal")


async def _next_transient(
    iterator: AsyncIterator[HostSessionEvent],
) -> HostTransientDelta:
    """读取下一条瞬态增量，并拒绝 terminal 抢先交付。

    :param iterator: HostSessionEvent async iterator。
    :returns: 下一条 Host 瞬态增量。
    :raises AssertionError: terminal 早于应存在的瞬态增量交付时抛出。
    """

    return await asyncio.wait_for(_read_next_transient(iterator), timeout=2.0)


async def _read_next_transient(
    iterator: AsyncIterator[HostSessionEvent],
) -> HostTransientDelta:
    """跳过 durable 非终态事件，读取下一条瞬态增量。

    :param iterator: HostSessionEvent async iterator。
    :returns: 下一条 Host 瞬态增量。
    :raises AssertionError: terminal 早于瞬态增量交付时抛出。
    """

    terminal_kinds = {
        HostEventKind.SUCCEEDED,
        HostEventKind.FAILED,
        HostEventKind.CANCELLED,
        HostEventKind.LOST,
    }
    while True:
        event = await anext(iterator)
        if isinstance(event, HostTransientDelta):
            return event
        if event.kind in terminal_kinds:
            raise AssertionError("terminal event was delivered before transient delta")


async def _read_next_terminal(
    iterator: AsyncIterator[HostSessionEvent],
) -> HostEvent:
    """从 iterator 中顺序读取下一条 terminal 事件。

    :param iterator: HostEvent async iterator。
    :returns: 下一条 terminal HostEvent。
    """

    while True:
        event = await anext(iterator)
        if isinstance(event, HostEvent) and event.kind in {
            HostEventKind.SUCCEEDED,
            HostEventKind.FAILED,
            HostEventKind.CANCELLED,
            HostEventKind.LOST,
        }:
            return event


async def _consume_forever(iterator: AsyncIterator[HostSessionEvent]) -> None:
    """持续消费 watcher，直到调用方取消任务。

    :param iterator: HostEvent async iterator。
    :returns: ``None``。
    :raises asyncio.CancelledError: 调用方取消 consumer task 时抛出。
    """

    async for _event in iterator:
        await asyncio.sleep(0)


async def _cancel_pending_next_iteration(
    iterator: AsyncIterator[HostSessionEvent],
) -> None:
    """排空有限 progress，随后取消一个确定处于等待态的后续 iteration。

    :param iterator: 已至少交付一条 transient 的 Session event iterator。
    :returns: ``None``。
    :raises AssertionError: 未在有限轮次内进入等待态，或提前收到 terminal 时抛出。
    """

    for _attempt in range(20):
        next_task = asyncio.ensure_future(anext(iterator))
        await asyncio.sleep(0.05)
        if next_task.done():
            event = await next_task
            if isinstance(event, HostEvent) and event.terminal_status is not None:
                raise AssertionError("watcher reached terminal before cancellation barrier")
            continue
        next_task.cancel()
        with suppress(asyncio.CancelledError):
            await next_task
        return
    raise AssertionError("watcher did not enter a pending next iteration")


async def _wait_for_wait_call_count(
    waiter: _ControlledSessionEventReconciliationWaiter,
    expected_count: int,
) -> None:
    """等待 controlled waiter 进入指定次数的 readiness wait。

    :param waiter: 目标 opener waiter。
    :param expected_count: 期待的累计调用次数。
    :returns: ``None``。
    :raises AssertionError: bounded event-loop turns 内未进入时抛出。
    """

    for _ in range(2_000):
        if waiter.wait_call_count >= expected_count:
            return
        await asyncio.sleep(0)
    raise AssertionError("reconciliation waiter did not reach expected call count")


async def _wait_for_task_or_wait_call(
    task: asyncio.Task[HostSessionEvent],
    waiter: _ControlledSessionEventReconciliationWaiter,
    expected_wait_call_count: int,
) -> bool:
    """等待 anext 完成或 iterator 进入下一次 readiness wait。

    :param task: 当前唯一 active ``anext`` task。
    :param waiter: 当前 opener controlled waiter。
    :param expected_wait_call_count: 用于识别 page 已耗尽的下一 wait 次数。
    :returns: task 先完成时返回 ``True``；waiter 先进入时返回 ``False``。
    :raises AssertionError: bounded event-loop turns 内两者均未发生时抛出。
    """

    for _ in range(4_000):
        if task.done():
            return True
        if waiter.wait_call_count >= expected_wait_call_count:
            return False
        await asyncio.sleep(0)
    raise AssertionError("session iterator did not reach deterministic barrier")


async def _close_iterator(iterator: HostSessionEventIterator) -> None:
    """关闭测试中持有的 async generator iterator。

    :param iterator: HostSessionEvent async iterator。
    :returns: ``None``。
    """

    await iterator.aclose()


def _attempt_identity_and_started_sequence(
    db_path: pathlib.Path,
    *,
    run_id: str,
) -> tuple[str, str, int]:
    """从 durable state 读取 current Attempt identity 与 start fence。

    :param db_path: Host durable SQLite 路径。
    :param run_id: 目标 Run 标识。
    :returns: ``attempt_id``、``execution_id`` 与严格正整数 start sequence。
    :raises AssertionError: durable row 缺失或字段 shape 非法时抛出。
    """

    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            f"""
            SELECT attempt.attempt_id,
                   attempt.execution_id,
                   attempt.started_event_sequence
              FROM {TABLE_HOST_RUNS} AS run
              JOIN {TABLE_HOST_ATTEMPTS} AS attempt
                ON attempt.attempt_id = run.current_attempt_id
             WHERE run.run_id = ?
            """,
            (run_id,),
        ).fetchone()
    finally:
        connection.close()
    assert row is not None
    attempt_id, execution_id, started_event_sequence = row
    assert isinstance(attempt_id, str) and attempt_id
    assert isinstance(execution_id, str) and execution_id
    assert (
        isinstance(started_event_sequence, int)
        and not isinstance(started_event_sequence, bool)
        and started_event_sequence > 0
    )
    return attempt_id, execution_id, started_event_sequence


def _publish_fenced_reasoning_delta(
    host: Host,
    *,
    session_id: str,
    run_id: str,
    attempt_id: str,
    execution_id: str,
    durable_causal_fence_event_sequence: int,
    worker_event_index: int,
) -> None:
    """通过指定 opener 的真实 delivery owner 发布 fenced test candidate。

    :param host: ``open_host`` 返回的 C opener handle。
    :param session_id: candidate Session 标识。
    :param run_id: candidate Run 标识。
    :param attempt_id: candidate Attempt 标识。
    :param execution_id: candidate execution 标识。
    :param durable_causal_fence_event_sequence: durable Attempt start fence。
    :param worker_event_index: execution 内事件序号。
    :returns: ``None``。
    :raises AssertionError: host 不是 production handle 时抛出。
    """

    if not isinstance(host, _PublicHostHandle):
        raise AssertionError("expected production _PublicHostHandle")
    host._transient_delta_hub.publish(
        ValidatedTransientDeltaCandidate(
            session_id=session_id,
            run_id=run_id,
            attempt_id=attempt_id,
            execution_id=execution_id,
            worker_event_index=worker_event_index,
            durable_causal_fence_event_sequence=(
                durable_causal_fence_event_sequence
            ),
            observed_at=datetime(2026, 7, 21, 1, 2, 3, tzinfo=UTC),
            type=HostTransientDeltaType.REASONING_DELTA,
            data=HostReasoningDelta(
                iteration_id="iteration-fenced",
                text_delta="fenced-delta",
            ),
        )
    )


async def _wait_run_terminal(host: Host, run_id: str) -> RunSnapshot:
    """等待 Run 进入终态。

    :param host: public Host handle。
    :param run_id: 目标 Run id。
    :returns: terminal Run snapshot。
    :raises AssertionError: 超时仍未进入终态时抛出。
    """

    for _ in range(200):
        snapshot = await host.get_run(run_id)
        if snapshot.status in {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            return snapshot
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} did not reach terminal status")


async def _wait_run_status(
    host: Host, run_id: str, expected_status: RunStatus
) -> RunSnapshot:
    """等待 Run 到达指定状态。

    :param host: public Host handle。
    :param run_id: 目标 Run id。
    :param expected_status: 期待状态。
    :returns: 匹配状态的 Run snapshot。
    :raises AssertionError: 超时仍未到达期待状态时抛出。
    """

    for _ in range(200):
        snapshot = await host.get_run(run_id)
        if snapshot.status is expected_status:
            return snapshot
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} did not reach {expected_status.value} status")


def _subscription_count(host: Host, session_id: str) -> int:
    """读取真实 ``open_host`` runtime 的 Session subscription owner 计数。

    :param host: ``open_host`` 返回的 public Host handle。
    :param session_id: 目标 Session 标识。
    :returns: 当前 hub 注册的 subscription 数量。
    :raises AssertionError: 调用方传入的不是 production public handle 时抛出。
    """

    if not isinstance(host, _PublicHostHandle):
        raise AssertionError("expected production _PublicHostHandle")
    return host._transient_delta_hub.subscription_count(session_id)


def _replace_event_payload(
    db_path: pathlib.Path,
    *,
    event_id: str,
    payload_json: str,
) -> str:
    """替换一条 EventLog payload 并返回原文，用于可恢复 durable failure 注入。

    :param db_path: Host durable SQLite 路径。
    :param event_id: 目标 EventLog 标识。
    :param payload_json: 替换后的 payload JSON 文本。
    :returns: 替换前的 payload JSON 文本。
    :raises AssertionError: row 缺失或原 payload 不是字符串时抛出。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            f"SELECT payload_json FROM {TABLE_EVENT_LOG} WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            raise AssertionError("EventLog payload row is missing")
        original_payload = row[0]
        if not isinstance(original_payload, str):
            raise AssertionError("EventLog payload is not str")
        connection.execute(
            f"UPDATE {TABLE_EVENT_LOG} SET payload_json = ? WHERE event_id = ?",
            (payload_json, event_id),
        )
    return original_payload


def _assert_public_durable_failure(error: HostApiError) -> None:
    """断言 durable corruption 只暴露稳定 public HostApiError。

    :param error: watcher 对外抛出的 public error。
    :returns: ``None``。
    :raises AssertionError: code、retryable、detail 或消息漂移时抛出。
    """

    assert error.code is HostApiErrorCode.INTERNAL_ERROR
    assert error.message == "Host durable operation failed"
    assert error.retryable is False
    assert error.detail is None


def _event_log_count(db_path: pathlib.Path) -> int:
    """读取 EventLog row 数量。

    :param db_path: Host durable SQLite 路径。
    :returns: EventLog row 数量。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(f"SELECT COUNT(*) FROM {TABLE_EVENT_LOG}").fetchone()
    if row is None:
        raise AssertionError("EventLog count query returned no row")
    value = row[0]
    if not isinstance(value, int):
        raise AssertionError("EventLog count is not int")
    return value


def _event_log_type_count(db_path: pathlib.Path, event_type: str) -> int:
    """读取指定事件类型的 EventLog row 数量。

    :param db_path: Host durable SQLite 路径。
    :param event_type: 目标 Engine 事件类型值。
    :returns: 匹配的 EventLog row 数量。
    :raises AssertionError: 查询未返回整数计数时抛出。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            f"SELECT COUNT(*) FROM {TABLE_EVENT_LOG} WHERE event_type = ?",
            (event_type,),
        ).fetchone()
    if row is None:
        raise AssertionError("EventLog type count query returned no row")
    value = row[0]
    if not isinstance(value, int):
        raise AssertionError("EventLog type count is not int")
    return value


async def _stable_event_log_count(db_path: pathlib.Path) -> int:
    """等待 EventLog 计数在短窗口内稳定。

    :param db_path: Host durable SQLite 路径。
    :returns: 稳定后的 EventLog row 数量。
    :raises AssertionError: 计数持续变化时抛出。
    """

    previous = _event_log_count(db_path)
    for _ in range(20):
        await asyncio.sleep(0.02)
        current = _event_log_count(db_path)
        if current == previous:
            return current
        previous = current
    raise AssertionError("EventLog count did not become stable")


def _final_answer_event(snapshot: AttemptDispatchSnapshot, content: str) -> EngineEvent:
    """构造 final answer EngineEvent。

    :param snapshot: 当前 dispatch snapshot。
    :param content: final answer 内容。
    :returns: EngineEvent。
    """

    return EngineEvent(
        occurred_at=datetime(2026, 5, 18, 1, 2, 3, tzinfo=UTC),
        session_id=snapshot.session_id,
        run_id=snapshot.run_id,
        type=EngineEventType.FINAL_ANSWER,
        data=FinalAnswerData(
            content=content,
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
        metadata=None,
    )


def _options(tmp_path: pathlib.Path, worker_factory: _Factory) -> OpenHostOptions:
    """构造测试用 OpenHostOptions。

    :param tmp_path: pytest 临时目录。
    :param worker_factory: 测试 worker factory。
    :returns: OpenHostOptions。
    """

    return OpenHostOptions(
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=1.0,
        sqlite_write_busy_retry_count=8,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.02,
        payload_inline_threshold_bytes=4096,
        lane_db_path=tmp_path / "lane.sqlite3",
        lane_name="llm",
        lane_capacity=1,
        lane_default_timeout_seconds=0.2,
        lane_claim_ttl_seconds=1.0,
        lane_heartbeat_interval_seconds=0.1,
        worker_startup_timeout_seconds=1.0,
        dispatch_poll_interval_seconds=0.01,
        ordinary_run_baseline=OrdinaryRunExecutionBaseline(
            runner_spec=_runner_spec(),
            runner_options=RunnerCallOptions(
                temperature=None,
                max_tokens=None,
                top_p=None,
                stream=False,
            ),
            agent_policy=AgentPolicy(
                max_iterations=1,
                continuation_max_attempts=0,
                allow_tool_calls=False,
                tool_execution_timeout_seconds=1.0,
                fallback_prompt="test fallback prompt",
                continuation_prompt="test continuation prompt",
            ),
        ),
        worker_factory=worker_factory,
        tooling_options=None,
        context_budget_policy=None,
        compactor_runner_baseline=None,
        memory_projection_policy=default_memory_projection_policy(),
        memory_projection_catchup_batch_size=128,
        enable_truncation_manager=True,
        session_event_delivery_policy=HostSessionEventDeliveryPolicy(
            transient_mailbox_max_items=512,
            max_subscriptions_per_session=4,
        ),
    )


def _runner_spec() -> RunnerSpec:
    """构造测试 RunnerSpec。

    :returns: RunnerSpec。
    """

    return RunnerSpec(
        provider="test",
        model="test-model",
        endpoint="https://example.invalid",
        api_key_ref="secret:test",
        headers={},
        client_correlation_policy=ClientCorrelationPolicy.DISABLED,
        supports_tool_calling=False,
        supports_streaming=False,
        supports_stream_usage=False,
        default_timeout_seconds=1.0,
        max_retries=0,
        provider_request=None,
    )


def _ensure_request(slot_key: str) -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :param slot_key: session slot key。
    :returns: EnsureSessionRequest。
    """

    return EnsureSessionRequest(
        scope="workspace",
        slot_key=slot_key,
        metadata=(),
    )


def _followup_request(
    session_id: str,
    client_request_id: str,
) -> SubmitFollowupRequest:
    """构造 follow-up queue 请求。

    :param session_id: 目标 Session id。
    :param client_request_id: 幂等请求 id。
    :returns: SubmitFollowupRequest。
    """

    return SubmitFollowupRequest(
        context=_context(client_request_id),
        session_id=session_id,
        client_request_id=client_request_id,
        system_prompt=None,
        user_prompt="请给出 deterministic answer",
        tool_names=None,
        runner_spec=None,
        runner_options=None,
        agent_policy=None,
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def _context(request_id: str) -> HostCallContext:
    """构造 Host 调用上下文。

    :param request_id: 请求 id。
    :returns: HostCallContext。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="research"),),
        operation_context=OperationContext(
            operation_name="watch_session_events",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="p10_5_slice4",
            correlation_id="corr-watch-session-events",
        ),
    )
