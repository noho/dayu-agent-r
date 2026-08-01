"""P10.5 Slice 2 ``open_host`` production runtime 接线测试。"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sqlite3
import sys
import threading
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import TypeVar, cast

import pytest

from dayu.contracts.tool_result import ToolResultSuccess
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    ReasoningDeltaData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
from dayu.host import (
    AttemptDispatchSnapshot,
    CancelMode,
    CancelRunRequest,
    CloseSessionRequest,
    CompactorRunnerBaseline,
    EnsureSessionRequest,
    FollowupSnapshot,
    FollowupBehavior,
    Host,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostEvent,
    HostEventKind,
    HostSessionAttachment,
    HostSessionEvent,
    HostSessionEventIterator,
    HostTerminalStatus,
    HostToolingOptions,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
    OpenHostAdminOptions,
    OpenHostOptions,
    HostSessionEventDeliveryPolicy,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    PurgeSessionRequest,
    ResolveWaitCompletedOutcome,
    RunSnapshot,
    RunStatus,
    SessionSnapshot,
    SubmitFollowupRequest,
    WaitAdapterKey,
    WaitResolutionSource,
    open_host,
    open_host_admin,
)
from dayu.host.api import AuthorizationClaim, HostLocalExecutionOptions
from dayu.host.command import (
    HostCommandHandle,
    expire_wait,
    start_run,
)
from dayu.host._durable_actor import DurableActor
from dayu.host._execution_health import (
    HostExecutionHealthGate,
    HostExecutionHealthState,
)
from dayu.host.dispatch import (
    ActiveWorkerRegistry,
    HostDispatchScheduler,
    _HostCancellationToken,
)
from dayu.host.admission import PendingDispatchRecord
from dayu.host.durable.connection import HostDurableStore, open_host_durable_store
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.outbox import read_outbox_terminal_items_after
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.context_policy import default_context_budget_policy
from dayu.host.memory import default_memory_projection_policy
from dayu.host.open_host import (
    _CompositeProjectionCatchupPort,
    _PublicHostHandle,
    _SessionEventReconciliationWaiter,
    _ThreadsafeSchedulerWakeupPort,
    _TerminalPostCommitCoordinator,
    _ensure_session as _actor_ensure_session,
    _get_run as _actor_get_run,
    _read_session_host_events_after as _actor_read_session_host_events_after,
    _session_live_event_start_cursor as _actor_watch_cursor,
    _submit_followup as _actor_submit_followup,
    _command_options_from_open_host_options,
    _local_execution_options_from_open_host_options,
)
from dayu.host.dispatch import _TerminalPostCommitPortFactory
from dayu.host.llm_compaction import LLMContextCompactor
from dayu.host.projection import ProjectionCatchupPort
from dayu.host.recovery import (
    SessionAttachmentRecoveryPolicy,
    SessionAttachmentRecoveryScanner,
    SessionAttachmentRecoveryScanResult,
)
from dayu.host.session_attachment import (
    HostSessionAttachmentRegistry,
    SessionNewWorkAccessPort,
)
from dayu.host.transient_delta import (
    HostTransientDeltaHub,
    HostTransientDeltaPublisher,
)
from dayu.host.wait_adapter import (
    WaitAdapterSnapshot,
    WaitExternalJobLifecycleResult,
    WaitPollAdapterRegistration,
    WaitPollAdapterRegistry,
    WaitPollReady,
    WaitPollResult,
    WaitPollerRuntimePolicy,
    WaitPollerSupervisor,
)
from dayu.host.waiting import ExpireWaitInput
from tests.host.public_smoke_support import awaiting_tooling_options
from tests.host.test_command_handle import _start_request
from tests.host.test_resolve_wait_command import (
    _failed_request,
    _seed_waiting_run,
    _set_wait_deadline_text,
)
from tests.host.execution_handle_support import create_execution_command_handle

T = TypeVar("T")
_SCHEDULER_CLOSE_FAILURE_MESSAGE = "scheduler close failed after cleanup"
_PROMOTION_BARRIER_EXPIRED_AT = datetime(2026, 5, 18, 3, 0, 0, tzinfo=UTC)


class _FinalAnswerHandle:
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

        return "open-host-final-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出单条 final answer 事件。

        :returns: EngineEvent 异步迭代器。
        """

        yield EngineEvent(
            occurred_at=datetime(2026, 5, 18, 1, 2, 3, tzinfo=UTC),
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content=f"final:{self._snapshot.run_id}",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭测试 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason


class _FinalAnswerWorker:
    """测试用立即接受并返回 final answer handle 的 worker。"""

    def __init__(self, factory: "_FinalAnswerWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受 dispatch 并记录 Engine request。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: final answer handle。
        """

        self._factory.accepted_snapshots.append(snapshot)
        self._factory.accepted_requests.append(request)
        self._factory.accepted_event.set()
        return _FinalAnswerHandle(snapshot)


class _FinalAnswerWorkerFactory:
    """测试用 deterministic no-tool worker factory。"""

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        """

        self.accepted_event = asyncio.Event()
        self.accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self.accepted_requests: list[AgentRunRequest] = []

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建测试 worker。

        :param snapshot: dispatch snapshot。
        :returns: 测试 worker。
        """

        del snapshot
        return _FinalAnswerWorker(self)


class _ControlledFinalAnswerHandle:
    """测试用受控产出 final answer 的 worker handle。"""

    def __init__(
        self,
        snapshot: AttemptDispatchSnapshot,
        release_event: asyncio.Event,
    ) -> None:
        """初始化 handle。

        :param snapshot: 当前 dispatch snapshot。
        :param release_event: 控制 final answer 产出的事件。
        :returns: ``None``。
        """

        self._snapshot = snapshot
        self._release_event = release_event

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        """

        return "open-host-controlled-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """等待测试释放后产出 final answer。

        :returns: EngineEvent 异步迭代器。
        """

        await self._release_event.wait()
        yield EngineEvent(
            occurred_at=datetime(2026, 5, 18, 1, 2, 4, tzinfo=UTC),
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content=f"recovered:{self._snapshot.run_id}",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭测试 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason


class _ControlledFinalAnswerWorker:
    """测试用受控 final answer worker。"""

    def __init__(self, factory: "_ControlledFinalAnswerWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受 dispatch 并记录 Engine request。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 受控 final answer handle。
        """

        self._factory.accepted_snapshots.append(snapshot)
        self._factory.accepted_requests.append(request)
        handle = _ControlledFinalAnswerHandle(
            snapshot,
            self._factory.release_event,
        )
        self._factory.accepted_event.set()
        return handle


class _ControlledFinalAnswerWorkerFactory:
    """测试用受控 final answer worker factory。"""

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        """

        self.accepted_event = asyncio.Event()
        self.release_event = asyncio.Event()
        self.accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self.accepted_requests: list[AgentRunRequest] = []

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建测试 worker。

        :param snapshot: dispatch snapshot。
        :returns: 测试 worker。
        """

        del snapshot
        return _ControlledFinalAnswerWorker(self)


class _TransientThenFinalHandle:
    """先产出 reasoning transient、再由 barrier 释放 terminal 的 handle。"""

    def __init__(
        self,
        *,
        snapshot: AttemptDispatchSnapshot,
        release_event: asyncio.Event,
        index: int,
    ) -> None:
        """初始化确定性两阶段 worker handle。

        :param snapshot: 当前 dispatch snapshot。
        :param release_event: terminal 释放 barrier。
        :param index: factory 分配的 worker 序号。
        :returns: ``None``。
        """

        self._snapshot = snapshot
        self._release_event = release_event
        self._index = index

    @property
    def local_worker_id(self) -> str:
        """返回稳定测试 worker id。

        :returns: 本 worker id。
        """

        return f"transient-terminal-worker-{self._index}"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """依次产出 transient candidate 与 terminal candidate。

        :returns: Engine event 异步迭代器。
        """

        yield EngineEvent(
            occurred_at=datetime(2026, 5, 18, 2, 0, self._index, tzinfo=UTC),
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.REASONING_DELTA,
            data=ReasoningDeltaData(
                iteration_id=f"iteration-{self._index}",
                delta=f"delta-{self._index}",
            ),
            metadata=None,
        )
        await self._release_event.wait()
        yield EngineEvent(
            occurred_at=datetime(2026, 5, 18, 2, 1, self._index, tzinfo=UTC),
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content=f"answer-{self._index}",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭测试 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """消费本测试不使用的 cancel hook。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason


class _TransientThenFinalWorker:
    """为单次 dispatch 创建两阶段 handle 的 worker。"""

    def __init__(
        self,
        *,
        factory: "_TransientThenFinalWorkerFactory",
        index: int,
    ) -> None:
        """保存 factory 与 worker 序号。

        :param factory: 所属 factory。
        :param index: worker 序号。
        :returns: ``None``。
        """

        self._factory = factory
        self._index = index

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受 dispatch 并发布 accepted barrier。

        :param snapshot: 当前 dispatch snapshot。
        :param request: Engine run request。
        :returns: 两阶段 worker handle。
        """

        del request
        self._factory.accepted_snapshots.append(snapshot)
        self._factory.accepted_queue.put_nowait(self._index)
        return _TransientThenFinalHandle(
            snapshot=snapshot,
            release_event=self._factory.release_events[self._index],
            index=self._index,
        )


class _TransientThenFinalWorkerFactory:
    """按 dispatch 序号提供独立 terminal barrier 的 deterministic factory。"""

    def __init__(self) -> None:
        """初始化两个 worker barrier。

        :returns: ``None``。
        """

        self.accepted_queue: asyncio.Queue[int] = asyncio.Queue()
        self.accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self.release_events = (asyncio.Event(), asyncio.Event())
        self._next_index = 0

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """为下一条 dispatch 创建 worker。

        :param snapshot: 当前 dispatch snapshot。
        :returns: 序号确定的测试 worker。
        :raises AssertionError: 测试意外创建第三个 worker 时抛出。
        """

        del snapshot
        index = self._next_index
        if index >= len(self.release_events):
            raise AssertionError("unexpected third worker")
        self._next_index += 1
        return _TransientThenFinalWorker(factory=self, index=index)


def _ignore_dispatch_wake(
    scheduler: HostDispatchScheduler,
    record: PendingDispatchRecord,
) -> None:
    """冻结测试中的 worker dispatch，但保留 admission durable transition。

    :param scheduler: 当前真实 scheduler。
    :param record: 已提交的 pending dispatch record。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    del scheduler
    del record


def _seed_waiting_run_with_queued_successor(
    options: OpenHostOptions,
    *,
    deadline_text: str | None,
) -> tuple[str, str, str]:
    """在 opener 启动前创建 waiting A 与同 Session queued B。

    :param options: 后续真实 opener 使用的同源 durable options。
    :param deadline_text: 可选 wait deadline 文本。
    :returns: ``(wait_id, run_a_id, run_b_id)``。
    :raises Exception: durable seed 或 queued admission 失败时透传。
    """

    command_options = replace(
        _command_options_from_open_host_options(
            options,
            host_handle_id="host-open-runtime-terminal-barrier-seed",
        ),
        local_execution=None,
    )
    seed_host = create_execution_command_handle(
        command_options,
        ordinary_run_baseline=options.ordinary_run_baseline,
        memory_projection_policy=options.memory_projection_policy,
        tooling_options=options.tooling_options,
        context_budget_policy=options.context_budget_policy,
        enable_truncation_manager=options.enable_truncation_manager,
    )
    try:
        seeded = _seed_waiting_run(
            seed_host,
            tooling_options=options.tooling_options,
        )
        if deadline_text is not None:
            _set_wait_deadline_text(
                seed_host._transaction_runner(),
                seeded.wait_id,
                deadline_text,
            )
        queued = start_run(
            seed_host,
            _start_request(
                seeded.session_id,
                "terminal-promotion-barrier-queued-b",
            ),
        )
        assert queued.status is RunStatus.QUEUED
        return seeded.wait_id, seeded.run_id, queued.run_id
    finally:
        seed_host.close()


async def _assert_terminal_before_promoted_start(
    *,
    watcher: HostSessionEventIterator,
    frozen_next: asyncio.Task[HostSessionEvent],
    host: _PublicHostHandle,
    run_a: RunSnapshot,
    run_b_id: str,
) -> None:
    """断言 A exact terminal 先于 promotion 后 B ``RUN_STARTED``。

    :param watcher: action 前已 attach 的真实 watcher。
    :param frozen_next: action 前已进入 pending 状态的首个 ``anext``。
    :param host: 当前 opener public handle。
    :param run_a: action 返回的 terminal A snapshot。
    :param run_b_id: 等待 promotion 的 queued B id。
    :returns: ``None``。
    :raises AssertionError: watermark、terminal handoff 或 B promotion 顺序漂移时抛出。
    """

    event = await asyncio.wait_for(frozen_next, timeout=1.0)
    while not (
        isinstance(event, HostEvent)
        and event.run_id == run_a.run_id
        and event.terminal_status is not None
    ):
        assert not (
            isinstance(event, HostEvent)
            and event.run_id == run_b_id
            and event.event_type == "RUN_STARTED"
        )
        event = await asyncio.wait_for(anext(watcher), timeout=1.0)
    assert (
        host._transient_delta_hub.committed_terminal_event_sequence_high_watermark(
            run_a.session_id
        )
        == event.event_sequence
    )

    promoted = await asyncio.wait_for(anext(watcher), timeout=1.0)
    while not (
        isinstance(promoted, HostEvent)
        and promoted.run_id == run_b_id
        and promoted.event_type == "RUN_STARTED"
    ):
        assert isinstance(promoted, HostEvent)
        assert promoted.run_id == run_b_id
        assert promoted.event_type == "RUNNER_CALL_INPUT_ASSEMBLED"
        promoted = await asyncio.wait_for(anext(watcher), timeout=1.0)


async def _close_terminal_barrier_watcher(
    watcher: HostSessionEventIterator | None,
    frozen_next: asyncio.Task[HostSessionEvent] | None,
) -> None:
    """取消未完成的 barrier read 后幂等关闭 watcher。

    :param watcher: 可选已创建 watcher。
    :param frozen_next: 可选首个 ``anext`` task。
    :returns: ``None``。
    :raises BaseException: watcher 自身 cleanup 失败时透传。
    """

    if frozen_next is not None and not frozen_next.done():
        frozen_next.cancel()
        try:
            await frozen_next
        except asyncio.CancelledError:
            pass
    if watcher is not None:
        await watcher.aclose()


class _RaisingSchedulerClose:
    """测试用 close 抛错的 scheduler 替身。"""

    def __init__(self) -> None:
        """初始化 scheduler 替身。

        :returns: ``None``。
        """

        self.close_count = 0

    async def close(self) -> None:
        """记录 close 调用后抛出测试错误。

        :returns: ``None``。
        :raises RuntimeError: 始终抛出 scheduler close 失败。
        """

        self.close_count += 1
        raise RuntimeError(_SCHEDULER_CLOSE_FAILURE_MESSAGE)


class _RecordingSchedulerClose:
    """测试用记录 close 顺序的 scheduler 替身。"""

    def __init__(self, order: list[str]) -> None:
        """初始化 scheduler 替身。

        :param order: 共享 close 顺序记录。
        :returns: ``None``。
        """

        self._order = order
        self.close_count = 0

    async def close(self) -> None:
        """记录 scheduler close 调用。

        :returns: ``None``。
        """

        self.close_count += 1
        self._order.append("scheduler")


class _RecordingWaitPollerClose:
    """测试用记录 close 顺序的 wait poller 替身。"""

    def __init__(self, order: list[str]) -> None:
        """初始化 wait poller 替身。

        :param order: 共享 close 顺序记录。
        :returns: ``None``。
        """

        self._order = order
        self.close_count = 0

    def close(self) -> None:
        """记录 wait poller close 调用。

        :returns: ``None``。
        """

        self.close_count += 1
        self._order.append("poller")


class _RecordingCommandHandleClose:
    """测试用记录 close 次数的 command handle 替身。"""

    def __init__(self) -> None:
        """初始化 command handle 替身。

        :returns: ``None``。
        """

        self.close_count = 0

    def close(self) -> None:
        """记录 command handle close 调用。

        :returns: ``None``。
        """

        self.close_count += 1


class _RecordingProjectionCatchupPort(ProjectionCatchupPort):
    """测试用记录 catch-up 次数的 projection port。"""

    def __init__(self) -> None:
        """初始化 projection port。

        :returns: ``None``。
        """

        self.catch_up_count = 0

    def catch_up_projection(self) -> None:
        """记录 projection catch-up 调用。

        :returns: ``None``。
        """

        self.catch_up_count += 1


class _ReadyPollAdapter:
    """测试用立即返回 ready 的 poll adapter。"""

    def __init__(self) -> None:
        """初始化调用记录。

        :returns: ``None``。
        """

        self.poll_count = 0

    def poll_wait(self, snapshot: WaitAdapterSnapshot) -> WaitPollResult:
        """记录 poll 并返回 completed result。

        :param snapshot: adapter snapshot。
        :returns: ready poll result。
        """

        del snapshot
        self.poll_count += 1
        return WaitPollReady(
            ResolveWaitCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value={"poller": "ready"},
                    meta=None,
                ),
                payload_ref=None,
            )
        )

    def abandon_wait(
        self, snapshot: WaitAdapterSnapshot
    ) -> WaitExternalJobLifecycleResult:
        """本测试不处理 cancelled wait。

        :param snapshot: adapter snapshot。
        :returns: applied lifecycle result。
        :raises AssertionError: 被错误调用时抛出。
        """

        raise AssertionError(f"unexpected abandon {snapshot.resume_token}")


@pytest.mark.asyncio
async def test_submit_followup_queue_auto_wakes_scheduler(
    tmp_path: pathlib.Path,
) -> None:
    """public submit_followup(queue) 经 open_host 自动唤醒 scheduler 并完成 Run。"""

    factory = _FinalAnswerWorkerFactory()
    options = _options(tmp_path, factory)

    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        attachment = await host.attach_session(session.session_id)
        try:
            followup = await host.submit_followup(
                session.session_id,
                _followup_request(session.session_id, "followup-auto-wakeup"),
            )

            final_run = await _wait_for_run_status(
                host, followup.accepted_run_id, RunStatus.SUCCEEDED
            )
        finally:
            await asyncio.shield(attachment.aclose())

    assert final_run.status == RunStatus.SUCCEEDED
    assert len(factory.accepted_snapshots) == 1
    assert factory.accepted_snapshots[0].run_id == followup.accepted_run_id
    assert factory.accepted_requests[0].disable_tools is True


@pytest.mark.asyncio
async def test_public_write_busy_retry_does_not_block_opener_event_loop(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """BEGIN IMMEDIATE 持锁时 actor busy retry 不阻塞 opener loop barrier。"""

    options = _options(tmp_path, _FinalAnswerWorkerFactory())
    actor_started = threading.Event()
    original_ensure_session = _actor_ensure_session

    def record_actor_start(
        handle: HostCommandHandle,
        request: EnsureSessionRequest,
    ) -> SessionSnapshot:
        """记录 public ensure 已进入 actor worker thread。

        :param handle: actor 私有 command handle。
        :param request: ensure session 请求。
        :returns: 原始 ensure 结果。
        :raises Exception: 原始 command 失败时透传。
        """

        actor_started.set()
        return original_ensure_session(handle, request)

    open_host_module = cast(ModuleType, sys.modules["dayu.host.open_host"])
    monkeypatch.setattr(open_host_module, "_ensure_session", record_actor_start)
    async with open_host(options) as host:
        lock_connection = sqlite3.connect(
            options.db_path,
            isolation_level=None,
        )
        lock_connection.execute("BEGIN IMMEDIATE")
        ensure_task = asyncio.create_task(host.ensure_session(_ensure_request()))
        assert await asyncio.to_thread(actor_started.wait, 1)

        probe_requested = asyncio.Event()
        loop_advanced = asyncio.Event()

        async def event_loop_probe() -> None:
            """通过 Event barrier 证明 opener loop 仍可执行 callback。

            :returns: ``None``。
            :raises Exception: 不主动抛出异常。
            """

            await probe_requested.wait()
            asyncio.get_running_loop().call_soon(loop_advanced.set)
            await loop_advanced.wait()

        probe_task = asyncio.create_task(event_loop_probe())
        probe_requested.set()
        await asyncio.wait_for(loop_advanced.wait(), timeout=1)
        assert not ensure_task.done()
        lock_connection.execute("ROLLBACK")
        lock_connection.close()
        session = await asyncio.wait_for(ensure_task, timeout=1)
        await probe_task

    assert session.session_id != ""


@pytest.mark.asyncio
async def test_public_ensure_submit_read_and_watch_share_actor_thread(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """public command/read/watch SQLite 入口全部提交到同一 actor thread。"""

    loop_thread_id = threading.get_ident()
    operation_threads: dict[str, int] = {}
    module = cast(ModuleType, sys.modules["dayu.host.open_host"])
    original_ensure = _actor_ensure_session
    original_submit = _actor_submit_followup
    original_get_run = _actor_get_run
    original_watch_cursor = _actor_watch_cursor

    def record_ensure(
        handle: HostCommandHandle,
        request: EnsureSessionRequest,
    ) -> SessionSnapshot:
        """记录 ensure operation thread。

        :param handle: actor command handle。
        :param request: ensure 请求。
        :returns: Session snapshot。
        :raises Exception: 原始 command 失败时透传。
        """

        operation_threads["ensure"] = threading.get_ident()
        return original_ensure(handle, request)

    def record_submit(
        handle: HostCommandHandle,
        session_id: str,
        request: SubmitFollowupRequest,
    ) -> FollowupSnapshot:
        """记录 submit operation thread。

        :param handle: actor command handle。
        :param session_id: 目标 Session id。
        :param request: follow-up 请求。
        :returns: Followup snapshot。
        :raises Exception: 原始 command 失败时透传。
        """

        operation_threads["submit"] = threading.get_ident()
        return original_submit(handle, session_id, request)

    def record_get_run(handle: HostCommandHandle, run_id: str) -> RunSnapshot:
        """记录 get_run operation thread。

        :param handle: actor command handle。
        :param run_id: 目标 Run id。
        :returns: Run snapshot。
        :raises Exception: 原始 read 失败时透传。
        """

        operation_threads["read"] = threading.get_ident()
        return original_get_run(handle, run_id)

    def record_watch_cursor(handle: HostCommandHandle, session_id: str) -> int:
        """记录 watch cursor attach operation thread。

        :param handle: actor command handle。
        :param session_id: 目标 Session id。
        :returns: live cursor。
        :raises Exception: 原始 read 失败时透传。
        """

        operation_threads["watch"] = threading.get_ident()
        return original_watch_cursor(handle, session_id)

    monkeypatch.setattr(module, "_ensure_session", record_ensure)
    monkeypatch.setattr(module, "_submit_followup", record_submit)
    monkeypatch.setattr(module, "_get_run", record_get_run)
    monkeypatch.setattr(module, "_session_live_event_start_cursor", record_watch_cursor)
    async with open_host(_options(tmp_path, _FinalAnswerWorkerFactory())) as host:
        session = await host.ensure_session(_ensure_request())
        attachment = await host.attach_session(session.session_id)
        try:
            followup = await host.submit_followup(
                session.session_id,
                _followup_request(session.session_id, "actor-thread-contract"),
            )
            watcher = await host.watch_session_events(session.session_id)
            await host.get_run(followup.accepted_run_id)
            await watcher.aclose()
        finally:
            await asyncio.shield(attachment.aclose())

    assert set(operation_threads) == {"ensure", "submit", "read", "watch"}
    assert len(set(operation_threads.values())) == 1
    assert next(iter(operation_threads.values())) != loop_thread_id


@pytest.mark.asyncio
async def test_open_host_close_flushes_outbox_projection(
    tmp_path: pathlib.Path,
) -> None:
    """open_host close projection flush 包含 Outbox terminal projection。"""

    factory = _FinalAnswerWorkerFactory()
    options = _options(tmp_path, factory)

    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        attachment = await host.attach_session(session.session_id)
        try:
            followup = await host.submit_followup(
                session.session_id,
                _followup_request(session.session_id, "followup-outbox-close-flush"),
            )
            await _wait_for_run_status(
                host,
                followup.accepted_run_id,
                RunStatus.SUCCEEDED,
            )
        finally:
            await asyncio.shield(attachment.aclose())

    with open_host_durable_store(_durable_options_from_open_options(options)) as store:
        page = store.transaction_runner.run_read(
            lambda transaction: read_outbox_terminal_items_after(
                transaction,
                session.session_id,
                after_event_sequence=0,
                seen_terminal_event_ids=(),
                limit=10,
            )
        )
        assert tuple(row.run_id for row in page.rows) == (followup.accepted_run_id,)
        assert page.rows[0].terminal_status == HostTerminalStatus.SUCCEEDED.value


@pytest.mark.asyncio
async def test_open_host_startup_recovery_dispatches_interrupted_run_and_watch_observes_final(
    tmp_path: pathlib.Path,
) -> None:
    """open_host ready 前恢复 interrupted Run，并通过 watch 观察最终回答。"""

    interrupted_factory = _ControlledFinalAnswerWorkerFactory()
    options = _options(tmp_path, interrupted_factory)
    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        attachment = await host.attach_session(session.session_id)
        try:
            followup = await host.submit_followup(
                session.session_id,
                _followup_request(session.session_id, "followup-interrupted"),
            )
            await asyncio.wait_for(interrupted_factory.accepted_event.wait(), timeout=1)
            run_id = followup.accepted_run_id
            session_id = session.session_id
        finally:
            await asyncio.shield(attachment.aclose())

    _mark_current_dispatch_owner_as_stale_running(options, run_id)

    recovery_factory = _ControlledFinalAnswerWorkerFactory()
    async with open_host(replace(options, worker_factory=recovery_factory)) as host:
        attachment = await host.attach_session(session_id)
        try:
            watcher = await host.watch_session_events(session_id)
            await asyncio.wait_for(recovery_factory.accepted_event.wait(), timeout=1)
            terminal_task = asyncio.create_task(_next_terminal(watcher))
            recovery_factory.release_event.set()
            terminal = await asyncio.wait_for(terminal_task, timeout=1)
            await _close_iterator(watcher)
            final_run = await _wait_for_run_status(host, run_id, RunStatus.SUCCEEDED)
        finally:
            await asyncio.shield(attachment.aclose())

    assert terminal.kind is HostEventKind.SUCCEEDED
    assert terminal.final_answer is not None
    assert terminal.final_answer.content == f"recovered:{run_id}"
    assert final_run.status is RunStatus.SUCCEEDED
    assert len(recovery_factory.accepted_snapshots) == 1
    assert recovery_factory.accepted_snapshots[0].run_id == run_id
    assert recovery_factory.accepted_snapshots[0].attempt_id != (
        interrupted_factory.accepted_snapshots[0].attempt_id
    )


@pytest.mark.asyncio
async def test_immediate_fresh_attach_delays_once_then_recovers_with_fresh_now(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fresh attach 在 threshold 前只调度一次，deadline 后用 fresh now 恢复。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: 提前 mutation、旧 now 复用或 recovery identity 漂移时抛出。
    """

    interrupted_factory = _ControlledFinalAnswerWorkerFactory()
    options = _options(tmp_path, interrupted_factory)
    async with open_host(options) as owner_host:
        session = await owner_host.ensure_session(_ensure_request())
        owner_attachment = await owner_host.attach_session(session.session_id)
        try:
            followup = await owner_host.submit_followup(
                session.session_id,
                _followup_request(
                    session.session_id,
                    "followup-immediate-delayed-recovery",
                ),
            )
            await asyncio.wait_for(
                interrupted_factory.accepted_event.wait(),
                timeout=1,
            )
            run_id = followup.accepted_run_id
            old_snapshot = interrupted_factory.accepted_snapshots[0]
        finally:
            await owner_attachment.aclose()

    initial_now = datetime.now(UTC)
    delayed_now = initial_now + timedelta(seconds=31)
    _mark_current_dispatch_owner_as_recent_running(
        options,
        run_id,
        heartbeat_at=initial_now - timedelta(seconds=5),
    )
    observed_times: list[datetime] = []
    clock_values = [initial_now, delayed_now]
    sleep_entered = asyncio.Event()
    sleep_release = asyncio.Event()
    observed_deadlines: list[datetime] = []
    module = cast(ModuleType, sys.modules["dayu.host.open_host"])

    def fake_utc_now() -> datetime:
        """为 initial 与 delayed operation 分别返回固定时间。

        :returns: 下一个 UTC-aware 测试时间。
        :raises AssertionError: production 意外重复读取时钟时抛出。
        """

        if not clock_values:
            raise AssertionError("delayed recovery unexpectedly reused the clock")
        value = clock_values.pop(0)
        observed_times.append(value)
        return value

    async def controlled_sleep(deadline: datetime) -> None:
        """在 monotonic delay 边界冻结，证明 deadline 前零 mutation。

        :param deadline: classifier 返回的 UTC deadline。
        :returns: ``None``。
        :raises asyncio.CancelledError: test cleanup 取消时抛出。
        """

        observed_deadlines.append(deadline)
        sleep_entered.set()
        await sleep_release.wait()

    monkeypatch.setattr(module, "_utc_now", fake_utc_now)
    monkeypatch.setattr(
        module,
        "_sleep_until_recovery_deadline",
        controlled_sleep,
    )
    recovery_factory = _ControlledFinalAnswerWorkerFactory()
    async with open_host(replace(options, worker_factory=recovery_factory)) as host:
        public_host = cast(_PublicHostHandle, host)
        attachment = await host.attach_session(session.session_id)
        watcher = await host.watch_session_events(session.session_id)
        try:
            await asyncio.wait_for(sleep_entered.wait(), timeout=1)
            before_deadline = await host.get_run(run_id)
            assert before_deadline.status is RunStatus.RUNNING
            assert _event_type_count(options.db_path, "ATTEMPT_LOST") == 0
            assert _event_type_count(options.db_path, "RUN_RECOVERING") == 0
            assert recovery_factory.accepted_event.is_set() is False
            assert observed_deadlines == [initial_now + timedelta(seconds=25)]

            sleep_release.set()
            await asyncio.wait_for(
                recovery_factory.accepted_event.wait(),
                timeout=2,
            )
            terminal_task = asyncio.create_task(_next_terminal(watcher))
            recovery_factory.release_event.set()
            terminal = await asyncio.wait_for(terminal_task, timeout=2)
            final_run = await _wait_for_run_status(
                host,
                run_id,
                RunStatus.SUCCEEDED,
            )
            await asyncio.sleep(0)
            assert public_host._health_gate.state is (
                HostExecutionHealthState.READY
            )
        finally:
            sleep_release.set()
            await watcher.aclose()
            await attachment.aclose()

    new_snapshot = recovery_factory.accepted_snapshots[0]
    assert observed_times == [initial_now, delayed_now]
    assert clock_values == []
    assert terminal.kind is HostEventKind.SUCCEEDED
    assert final_run.status is RunStatus.SUCCEEDED
    assert new_snapshot.run_id == old_snapshot.run_id
    assert new_snapshot.attempt_id != old_snapshot.attempt_id
    assert new_snapshot.execution_id != old_snapshot.execution_id
    assert len(interrupted_factory.accepted_snapshots) == 1
    assert len(recovery_factory.accepted_snapshots) == 1
    assert public_host._delayed_attachment_recovery_tasks == {}
    assert _event_type_count(options.db_path, "ATTEMPT_LOST") == 1
    assert _event_type_count(options.db_path, "RUN_RECOVERING") == 1
    assert _event_type_count(options.db_path, "RUN_STARTED") == 2
    event_types, recovery_start_reason = _recovery_event_order_and_reason(
        options.db_path,
        run_id,
    )
    attempt_lost_index = event_types.index("ATTEMPT_LOST")
    recovering_index = event_types.index("RUN_RECOVERING")
    recovery_started_index = max(
        index
        for index, event_type in enumerate(event_types)
        if event_type == "RUN_STARTED"
    )
    assert attempt_lost_index < recovering_index < recovery_started_index
    assert recovery_start_reason == "recovery"


@pytest.mark.asyncio
async def test_same_durable_page_two_terminals_each_preserve_transient_handoff(
    tmp_path: pathlib.Path,
) -> None:
    """同页两个 terminal 前分别交付同 Run transient，且 B 不越过 A terminal。"""

    factory = _TransientThenFinalWorkerFactory()
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request())
        attachment = await host.attach_session(session.session_id)
        try:
            watcher = await host.watch_session_events(session.session_id)
            public_host = cast(_PublicHostHandle, host)
            attached_cursor = await public_host._durable_actor.call(
                lambda handle: _actor_watch_cursor(handle, session.session_id)
            )
            first = await host.submit_followup(
                session.session_id,
                _followup_request(session.session_id, "same-page-first"),
            )
            assert await asyncio.wait_for(factory.accepted_queue.get(), timeout=1) == 0
            second = await host.submit_followup(
                session.session_id,
                _followup_request(session.session_id, "same-page-second"),
            )
            factory.release_events[0].set()
            assert await asyncio.wait_for(factory.accepted_queue.get(), timeout=1) == 1
            factory.release_events[1].set()
            await _wait_for_run_status(host, first.accepted_run_id, RunStatus.SUCCEEDED)
            await _wait_for_run_status(host, second.accepted_run_id, RunStatus.SUCCEEDED)
            durable_page = await public_host._durable_actor.call(
                lambda handle: _actor_read_session_host_events_after(
                    handle,
                    session.session_id,
                    attached_cursor,
                )
            )
            durable_page_terminals = tuple(
                event
                for event in durable_page.events
                if event.terminal_status is not None
            )
            assert tuple(event.run_id for event in durable_page_terminals) == (
                first.accepted_run_id,
                second.accepted_run_id,
            )
            collected = await asyncio.wait_for(
                _collect_until_two_terminals(watcher),
                timeout=2,
            )
            await watcher.aclose()
        finally:
            await asyncio.shield(attachment.aclose())

    terminal_events = tuple(
        event
        for event in collected
        if isinstance(event, HostEvent)
        and event.kind is not HostEventKind.PROGRESS
    )
    transient_events = tuple(
        event for event in collected if not isinstance(event, HostEvent)
    )
    assert tuple(event.run_id for event in terminal_events) == (
        first.accepted_run_id,
        second.accepted_run_id,
    )
    assert tuple(event.run_id for event in transient_events) == (
        first.accepted_run_id,
        second.accepted_run_id,
    )
    positions = {
        ("terminal" if isinstance(event, HostEvent) else "transient", event.run_id): index
        for index, event in enumerate(collected)
        if (
            not isinstance(event, HostEvent)
            or event.kind is not HostEventKind.PROGRESS
        )
    }
    assert positions[("transient", first.accepted_run_id)] < positions[
        ("terminal", first.accepted_run_id)
    ]
    assert positions[("terminal", first.accepted_run_id)] < positions[
        ("transient", second.accepted_run_id)
    ]
    assert positions[("transient", second.accepted_run_id)] < positions[
        ("terminal", second.accepted_run_id)
    ]


@pytest.mark.asyncio
async def test_pre_dispatch_cancel_terminal_precedes_queued_promotion_entry(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pre-dispatch A cancel 的 exact terminal 先于 promotion 后 B start。"""

    monkeypatch.setattr(
        HostDispatchScheduler,
        "wake_dispatch",
        _ignore_dispatch_wake,
    )
    manager = open_host(_options(tmp_path, _ControlledFinalAnswerWorkerFactory()))
    host = cast(_PublicHostHandle, await manager.__aenter__())
    watcher: HostSessionEventIterator | None = None
    frozen_next: asyncio.Task[HostSessionEvent] | None = None
    attachment: HostSessionAttachment | None = None
    try:
        session = await host.ensure_session(_ensure_request())
        attachment = await host.attach_session(session.session_id)
        run_a = await host.submit_followup(
            session.session_id,
            _followup_request(
                session.session_id,
                "terminal-barrier-pre-dispatch-a",
            ),
        )
        run_b = await host.submit_followup(
            session.session_id,
            _followup_request(
                session.session_id,
                "terminal-barrier-pre-dispatch-b",
            ),
        )
        assert (await host.get_run(run_a.accepted_run_id)).status is RunStatus.RUNNING
        assert (await host.get_run(run_b.accepted_run_id)).status is RunStatus.QUEUED
        watcher = await host.watch_session_events(session.session_id)
        frozen_next = asyncio.create_task(anext(watcher))
        await asyncio.sleep(0)
        assert not frozen_next.done()

        terminal_a = await host.cancel_run(
            run_a.accepted_run_id,
            _cancel_request("terminal-barrier-pre-dispatch-cancel"),
        )
        await _assert_terminal_before_promoted_start(
            watcher=watcher,
            frozen_next=frozen_next,
            host=host,
            run_a=terminal_a,
            run_b_id=run_b.accepted_run_id,
        )
    finally:
        await _close_terminal_barrier_watcher(watcher, frozen_next)
        if attachment is not None:
            await asyncio.shield(attachment.aclose())
        await manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_wait_failed_terminal_precedes_queued_promotion_entry(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """wait failed A 的 exact terminal 先于 promotion 后 B start。"""

    factory = _ControlledFinalAnswerWorkerFactory()
    options = _options(tmp_path, factory)
    wait_id, run_a_id, run_b_id = _seed_waiting_run_with_queued_successor(
        options,
        deadline_text=None,
    )
    monkeypatch.setattr(
        HostDispatchScheduler,
        "wake_dispatch",
        _ignore_dispatch_wake,
    )
    manager = open_host(options)
    host = cast(_PublicHostHandle, await manager.__aenter__())
    watcher: HostSessionEventIterator | None = None
    frozen_next: asyncio.Task[HostSessionEvent] | None = None
    attachment: HostSessionAttachment | None = None
    try:
        waiting_a = await host.get_run(run_a_id)
        queued_b = await host.get_run(run_b_id)
        assert waiting_a.status is RunStatus.WAITING
        assert queued_b.status is RunStatus.QUEUED
        attachment = await host.attach_session(waiting_a.session_id)
        watcher = await host.watch_session_events(waiting_a.session_id)
        frozen_next = asyncio.create_task(anext(watcher))
        await asyncio.sleep(0)
        assert not frozen_next.done()

        terminal_a = await host.resolve_wait(
            wait_id,
            _failed_request("terminal-barrier-wait-failed"),
        )
        await _assert_terminal_before_promoted_start(
            watcher=watcher,
            frozen_next=frozen_next,
            host=host,
            run_a=terminal_a,
            run_b_id=run_b_id,
        )
    finally:
        await _close_terminal_barrier_watcher(watcher, frozen_next)
        if attachment is not None:
            await asyncio.shield(attachment.aclose())
        await manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_wait_expiry_terminal_precedes_queued_promotion_entry(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """wait expiry A 的 exact terminal 先于 promotion 后 B start。"""

    factory = _ControlledFinalAnswerWorkerFactory()
    options = _options(tmp_path, factory)
    wait_id, run_a_id, run_b_id = _seed_waiting_run_with_queued_successor(
        options,
        deadline_text="2026-05-18T02:59:59.000000Z",
    )
    monkeypatch.setattr(
        HostDispatchScheduler,
        "wake_dispatch",
        _ignore_dispatch_wake,
    )
    manager = open_host(options)
    host = cast(_PublicHostHandle, await manager.__aenter__())
    watcher: HostSessionEventIterator | None = None
    frozen_next: asyncio.Task[HostSessionEvent] | None = None
    attachment: HostSessionAttachment | None = None
    try:
        waiting_a = await host.get_run(run_a_id)
        queued_b = await host.get_run(run_b_id)
        assert waiting_a.status is RunStatus.WAITING
        assert queued_b.status is RunStatus.QUEUED
        attachment = await host.attach_session(waiting_a.session_id)
        watcher = await host.watch_session_events(waiting_a.session_id)
        frozen_next = asyncio.create_task(anext(watcher))
        await asyncio.sleep(0)
        assert not frozen_next.done()

        await host._durable_actor.call(
            lambda handle: expire_wait(
                handle,
                ExpireWaitInput(
                    wait_id=wait_id,
                    observed_at=_PROMOTION_BARRIER_EXPIRED_AT,
                    actor="expiry-owner-barrier",
                    source=WaitResolutionSource.POLL,
                ),
            )
        )
        terminal_a = await host.get_run(run_a_id)
        await _assert_terminal_before_promoted_start(
            watcher=watcher,
            frozen_next=frozen_next,
            host=host,
            run_a=terminal_a,
            run_b_id=run_b_id,
        )
    finally:
        await _close_terminal_barrier_watcher(watcher, frozen_next)
        if attachment is not None:
            await asyncio.shield(attachment.aclose())
        await manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_open_host_startup_recovery_dispatches_gracefully_closed_run(
    tmp_path: pathlib.Path,
) -> None:
    """open_host 正常 close 后重启恢复已接受但未终态的 Run。"""

    interrupted_factory = _ControlledFinalAnswerWorkerFactory()
    options = _options(tmp_path, interrupted_factory)
    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        attachment = await host.attach_session(session.session_id)
        try:
            followup = await host.submit_followup(
                session.session_id,
                _followup_request(session.session_id, "followup-graceful-close"),
            )
            await asyncio.wait_for(interrupted_factory.accepted_event.wait(), timeout=1)
            run_id = followup.accepted_run_id
            session_id = session.session_id
        finally:
            await asyncio.shield(attachment.aclose())

    recovery_factory = _ControlledFinalAnswerWorkerFactory()
    async with open_host(replace(options, worker_factory=recovery_factory)) as host:
        attachment = await host.attach_session(session_id)
        try:
            watcher = await host.watch_session_events(session_id)
            await asyncio.wait_for(recovery_factory.accepted_event.wait(), timeout=1)
            terminal_task = asyncio.create_task(_next_terminal(watcher))
            recovery_factory.release_event.set()
            terminal = await asyncio.wait_for(terminal_task, timeout=1)
            await _close_iterator(watcher)
            final_run = await _wait_for_run_status(host, run_id, RunStatus.SUCCEEDED)
        finally:
            await asyncio.shield(attachment.aclose())

    assert terminal.kind is HostEventKind.SUCCEEDED
    assert terminal.final_answer is not None
    assert terminal.final_answer.content == f"recovered:{run_id}"
    assert final_run.status is RunStatus.SUCCEEDED
    assert len(recovery_factory.accepted_snapshots) == 1
    assert recovery_factory.accepted_snapshots[0].run_id == run_id
    assert recovery_factory.accepted_snapshots[0].attempt_id != (
        interrupted_factory.accepted_snapshots[0].attempt_id
    )


@pytest.mark.asyncio
async def test_open_host_active_cancel_watchdog_public_watch_observes_cancelled(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """actor cancel bridge 在 opener loop 写 event/token/hook 后 watchdog 收口。"""

    factory = _ControlledFinalAnswerWorkerFactory()
    options = _options(tmp_path, factory)
    opener_thread_id = threading.get_ident()
    watchdog_threads: list[int] = []
    watchdog_event_states: list[bool] = []
    token_threads: list[int] = []
    hook_threads: list[int] = []
    hook_event = asyncio.Event()
    original_watchdog_wake = HostDispatchScheduler.wake_active_cancel_watchdog
    original_request_cancel = _HostCancellationToken.request_cancel
    original_on_cancel = _ControlledFinalAnswerHandle.on_cancel

    def record_watchdog_wake(
        self: HostDispatchScheduler,
        session_id: str,
    ) -> None:
        """记录 watchdog Event.set 所在线程与 set 后状态。

        :param self: scheduler。
        :param session_id: cancel command 的目标 Session id。
        :returns: ``None``。
        :raises Exception: 原始 wake 失败时透传。
        """

        watchdog_threads.append(threading.get_ident())
        original_watchdog_wake(self, session_id)
        watchdog_event_states.append(
            self._active_cancel_watchdog_event.is_set()
        )

    def record_token_cancel(self: _HostCancellationToken, reason: str) -> None:
        """记录 token 写入线程后委托真实 token owner。

        :param self: Host cancellation token。
        :param reason: cancel reason。
        :returns: ``None``。
        """

        token_threads.append(threading.get_ident())
        original_request_cancel(self, reason)

    def record_worker_hook(
        self: _ControlledFinalAnswerHandle,
        reason: str,
    ) -> None:
        """记录 worker hook 线程并访问 opener-loop asyncio primitive。

        :param self: controlled worker handle。
        :param reason: cancel reason。
        :returns: ``None``。
        """

        hook_threads.append(threading.get_ident())
        hook_event.set()
        original_on_cancel(self, reason)

    monkeypatch.setattr(
        HostDispatchScheduler,
        "wake_active_cancel_watchdog",
        record_watchdog_wake,
    )
    monkeypatch.setattr(_HostCancellationToken, "request_cancel", record_token_cancel)
    monkeypatch.setattr(_ControlledFinalAnswerHandle, "on_cancel", record_worker_hook)
    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        attachment = await host.attach_session(session.session_id)
        try:
            followup = await host.submit_followup(
                session.session_id,
                _followup_request(session.session_id, "followup-active-cancel-watchdog"),
            )
            await asyncio.wait_for(factory.accepted_event.wait(), timeout=1)
            watcher = await host.watch_session_events(session.session_id)
            terminal_task = asyncio.create_task(_next_terminal(watcher))
            await asyncio.sleep(0)
            await host.get_run(followup.accepted_run_id)
            cancelling = await host.cancel_run(
                followup.accepted_run_id,
                _cancel_request("cancel-active-watchdog"),
            )
            assert hook_event.is_set()
            assert watchdog_threads == [opener_thread_id]
            assert watchdog_event_states == [True]
            assert token_threads == [opener_thread_id]
            assert hook_threads == [opener_thread_id]
            cast(
                _PublicHostHandle,
                host,
            )._scheduler.tick_active_cancel_watchdog_for_session(
                session.session_id,
                datetime(2030, 1, 1, tzinfo=UTC)
            )
            terminal = await asyncio.wait_for(terminal_task, timeout=1)
            await _close_iterator(watcher)
            final_run = await host.get_run(followup.accepted_run_id)
        finally:
            await asyncio.shield(attachment.aclose())

    assert cancelling.status is RunStatus.CANCELLING
    assert terminal.kind is HostEventKind.CANCELLED
    assert terminal.run_id == followup.accepted_run_id
    assert final_run.status is RunStatus.CANCELLED


@pytest.mark.asyncio
async def test_open_host_reopen_closes_existing_cancelling_run_as_cancelled(
    tmp_path: pathlib.Path,
) -> None:
    """clean-close/reopen 后 accepted cancel 关闭为 CANCELLED 而非 LOST。"""

    factory = _ControlledFinalAnswerWorkerFactory()
    options = _options(tmp_path, factory)
    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        attachment = await host.attach_session(session.session_id)
        try:
            followup = await host.submit_followup(
                session.session_id,
                _followup_request(session.session_id, "followup-reopen-watchdog-closeout"),
            )
            await asyncio.wait_for(factory.accepted_event.wait(), timeout=1)
            await host.cancel_run(
                followup.accepted_run_id,
                _cancel_request("cancel-reopen-watchdog-closeout"),
            )
            run_id = followup.accepted_run_id
        finally:
            await asyncio.shield(attachment.aclose())

    async with open_host(replace(options, worker_factory=_FinalAnswerWorkerFactory())) as host:
        final_run = await host.get_run(run_id)

    assert final_run.status is RunStatus.CANCELLED
    assert _event_type_count(options.db_path, "RUN_CANCELLED") == 1
    assert _event_type_count(options.db_path, "RUN_LOST") == 0


@pytest.mark.asyncio
async def test_open_host_reopen_closes_accepted_cancel_with_watchdog(
    tmp_path: pathlib.Path,
) -> None:
    """reopen 时 accepted-cancel CANCELLING 由 watchdog 收口且不写 RUN_LOST。"""

    factory = _ControlledFinalAnswerWorkerFactory()
    options = _options(tmp_path, factory)
    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        attachment = await host.attach_session(session.session_id)
        try:
            followup = await host.submit_followup(
                session.session_id,
                _followup_request(session.session_id, "followup-reopen-watchdog"),
            )
            await asyncio.wait_for(factory.accepted_event.wait(), timeout=1)
            await host.cancel_run(
                followup.accepted_run_id,
                _cancel_request("cancel-reopen-watchdog"),
            )
            run_id = followup.accepted_run_id
        finally:
            await asyncio.shield(attachment.aclose())

    async with open_host(replace(options, worker_factory=_FinalAnswerWorkerFactory())) as host:
        snapshot = await host.get_run(run_id)

    assert snapshot.status is RunStatus.CANCELLED
    assert _event_type_count(options.db_path, "RUN_LOST") == 0
    assert _event_type_count(options.db_path, "RUN_CANCELLED") == 1


@pytest.mark.asyncio
async def test_close_drains_actor_wake_before_scheduler_and_preserves_close_order(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """阻塞 actor 后按 producer→coordinator→delivery→projection 顺序关闭。"""

    manager = open_host(_options(tmp_path, _FinalAnswerWorkerFactory()))
    public_host = cast(_PublicHostHandle, await manager.__aenter__())
    loop = asyncio.get_running_loop()
    loop_thread_id = threading.get_ident()
    wake_started = threading.Event()
    wake_release = threading.Event()
    wake_on_loop = asyncio.Event()
    order: list[str] = []
    original_scheduler_close = HostDispatchScheduler.close
    original_coordinator_close = _TerminalPostCommitCoordinator.close
    original_delivery_close = HostTransientDeltaHub.close
    original_wake_queue = HostDispatchScheduler.wake_queue_promotion
    original_projection_catchup = _CompositeProjectionCatchupPort.catch_up_projection
    original_handle_close = HostCommandHandle.close
    original_executor_shutdown = ThreadPoolExecutor.shutdown
    original_store_close = HostDurableStore.close

    async def record_scheduler_close(self: HostDispatchScheduler) -> None:
        """记录 scheduler close 并委托真实实现。

        :param self: scheduler。
        :returns: ``None``。
        :raises Exception: 原始 close 失败时透传。
        """

        order.append("scheduler")
        await original_scheduler_close(self)

    async def record_coordinator_close(
        self: _TerminalPostCommitCoordinator,
    ) -> None:
        """记录 terminal coordinator drain/close。

        :param self: terminal coordinator。
        :returns: ``None``。
        :raises Exception: 原始 close 失败时透传。
        """

        order.append("coordinator")
        await original_coordinator_close(self)

    def record_delivery_close(self: HostTransientDeltaHub) -> None:
        """记录 delivery owner close 并委托真实实现。

        :param self: transient delivery hub。
        :returns: ``None``。
        :raises Exception: 原始 close 失败时透传。
        """

        order.append("delivery")
        original_delivery_close(self)

    def record_wake_queue(
        self: HostDispatchScheduler,
        session_id: str,
    ) -> None:
        """记录 scheduler wake 的 loop thread 并访问 asyncio primitive。

        :param self: scheduler。
        :param session_id: queue promotion Session id。
        :returns: ``None``。
        :raises Exception: 原始 wake 失败时透传。
        """

        assert threading.get_ident() == loop_thread_id
        wake_on_loop.set()
        original_wake_queue(self, session_id)

    def record_projection_catchup(self: _CompositeProjectionCatchupPort) -> None:
        """记录 projection close 阶段并委托真实实现。

        :param self: composite projection port。
        :returns: ``None``。
        :raises Exception: 原始 catch-up 失败时透传。
        """

        order.append("projection")
        original_projection_catchup(self)

    def record_handle_close(self: HostCommandHandle) -> None:
        """记录 actor handle close 并委托真实实现。

        :param self: actor 私有 command handle。
        :returns: ``None``。
        :raises Exception: 原始 close 失败时透传。
        """

        order.append("actor_handle")
        original_handle_close(self)

    def record_executor_shutdown(
        self: ThreadPoolExecutor,
        wait: bool = True,
        *,
        cancel_futures: bool = False,
    ) -> None:
        """记录 actor executor shutdown 并委托真实实现。

        :param self: thread pool executor。
        :param wait: 是否等待 worker 退出。
        :param cancel_futures: 是否取消未开始 futures。
        :returns: ``None``。
        :raises Exception: 原始 shutdown 失败时透传。
        """

        order.append("executor")
        original_executor_shutdown(
            self,
            wait=wait,
            cancel_futures=cancel_futures,
        )

    def record_store_close(self: HostDurableStore) -> None:
        """区分记录 actor store 与 scheduler store close。

        :param self: durable store。
        :returns: ``None``。
        :raises Exception: 原始 close 失败时透传。
        """

        order.append(
            "scheduler_store"
            if threading.get_ident() == loop_thread_id
            else "actor_store"
        )
        original_store_close(self)

    monkeypatch.setattr(HostDispatchScheduler, "close", record_scheduler_close)
    monkeypatch.setattr(
        _TerminalPostCommitCoordinator,
        "close",
        record_coordinator_close,
    )
    monkeypatch.setattr(HostTransientDeltaHub, "close", record_delivery_close)
    monkeypatch.setattr(
        HostDispatchScheduler,
        "wake_queue_promotion",
        record_wake_queue,
    )
    monkeypatch.setattr(
        _CompositeProjectionCatchupPort,
        "catch_up_projection",
        record_projection_catchup,
    )
    monkeypatch.setattr(HostCommandHandle, "close", record_handle_close)
    monkeypatch.setattr(ThreadPoolExecutor, "shutdown", record_executor_shutdown)
    monkeypatch.setattr(HostDurableStore, "close", record_store_close)
    wakeup_port = _ThreadsafeSchedulerWakeupPort(
        loop=loop,
        scheduler=public_host._scheduler,
    )

    def blocked_actor_wake(_handle: HostCommandHandle) -> None:
        """在 actor thread 等待 barrier 后同步桥接 scheduler wake。

        :param _handle: actor 私有 command handle。
        :returns: ``None``。
        :raises RuntimeError: release barrier 超时时抛出。
        """

        wake_started.set()
        if not wake_release.wait(timeout=2):
            raise RuntimeError("close-order wake barrier timed out")
        wakeup_port.wake_queue_promotion("close-order-session")

    command_task = asyncio.create_task(
        public_host._durable_actor.call(blocked_actor_wake)
    )
    assert await asyncio.to_thread(wake_started.wait, 1)
    close_task = asyncio.create_task(public_host.close())
    await asyncio.sleep(0)
    assert "scheduler" not in order
    wake_release.set()
    await command_task
    await asyncio.wait_for(wake_on_loop.wait(), timeout=1)
    await close_task
    await manager.__aexit__(None, None, None)

    assert order == [
        "scheduler",
        "coordinator",
        "delivery",
        "projection",
        "actor_handle",
        "actor_store",
        "executor",
        "scheduler_store",
    ]


@pytest.mark.asyncio
async def test_public_admission_first_commit_and_wake_precede_fatal(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """public admission 已排入 actor 后 commit+wake 必须先于 fatal transition。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    """

    manager = open_host(_options(tmp_path, _FinalAnswerWorkerFactory()))
    public_host = cast(_PublicHostHandle, await manager.__aenter__())
    session = await public_host.ensure_session(_ensure_request())
    attachment = await public_host.attach_session(session.session_id)
    actor_started = threading.Event()
    actor_release = threading.Event()
    admission_submitted = asyncio.Event()
    fatal_started = asyncio.Event()
    order: list[str] = []
    original_submit = DurableActor.submit
    original_wake = HostDispatchScheduler.wake_queue_promotion

    def actor_barrier(_handle: HostCommandHandle) -> None:
        """占住 actor worker，保证 public admission 尚未开始 transaction。

        :param _handle: actor 私有 command handle。
        :returns: ``None``。
        :raises RuntimeError: barrier 未在测试预算内释放时抛出。
        """

        actor_started.set()
        if not actor_release.wait(timeout=2):
            raise RuntimeError("public admission actor barrier timed out")

    barrier_future = original_submit(public_host._durable_actor, actor_barrier)
    assert await asyncio.to_thread(actor_started.wait, 1)

    def record_submit(
        self: DurableActor,
        operation: Callable[[HostCommandHandle], T],
    ) -> asyncio.Future[T]:
        """记录 public new-work 已持 lease 并提交到 actor。

        :param self: durable actor。
        :param operation: typed actor operation。
        :returns: 原始 actor future。
        :raises Exception: 原始 submit 异常时透传。
        """

        future = original_submit(self, operation)
        if self is public_host._durable_actor:
            admission_submitted.set()
        return future

    def record_wake(self: HostDispatchScheduler, session_id: str) -> None:
        """记录 matching governance wake 后委托真实 scheduler。

        :param self: scheduler。
        :param session_id: wake Session id。
        :returns: ``None``。
        :raises Exception: 原始 wake 异常时透传。
        """

        order.append("wake")
        original_wake(self, session_id)

    async def report_fatal() -> bool:
        """记录 fatal 开始并调用 public/scheduler 共享 health owner。

        :returns: fatal 是否提交 transition。
        :raises Exception: health owner 异常时透传。
        """

        fatal_started.set()
        transitioned = await public_host._health_gate.report_fatal(
            component="dispatch",
            reason_code="injected_critical_exit",
        )
        order.append("fatal")
        return transitioned

    monkeypatch.setattr(DurableActor, "submit", record_submit)
    monkeypatch.setattr(HostDispatchScheduler, "wake_queue_promotion", record_wake)
    submit_task = asyncio.create_task(
        public_host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "admission-first"),
        )
    )
    await admission_submitted.wait()
    fatal_task = asyncio.create_task(report_fatal())
    await fatal_started.wait()
    assert public_host._health_gate.state is HostExecutionHealthState.READY

    actor_release.set()
    try:
        result = await submit_task
        await barrier_future
        assert await fatal_task is True
        assert result.accepted_run_id != ""
        assert order[:2] == ["wake", "fatal"]
        assert public_host._health_gate.state is HostExecutionHealthState.UNAVAILABLE
        submission_count = len(order)
        with pytest.raises(HostApiError) as unavailable:
            await public_host.submit_followup(
                session.session_id,
                _followup_request(session.session_id, "fatal-rejected"),
            )
        assert unavailable.value.code is HostApiErrorCode.UNAVAILABLE
        assert len(order) == submission_count
        assert (await public_host.get_session(session.session_id)).session_id == (
            session.session_id
        )
        with pytest.raises(HostApiError) as cancel_error:
            await public_host.cancel_run(
                "missing-after-fatal",
                _cancel_request("cancel-after-fatal"),
            )
        assert cancel_error.value.code is HostApiErrorCode.NOT_FOUND
    finally:
        actor_release.set()
        await asyncio.shield(attachment.aclose())
        await manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_cancelled_public_admission_keeps_lease_until_actor_wake(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """public caller 取消不允许 fatal 越过已提交 actor command 的 matching wake。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    """

    manager = open_host(_options(tmp_path, _FinalAnswerWorkerFactory()))
    public_host = cast(_PublicHostHandle, await manager.__aenter__())
    session = await public_host.ensure_session(_ensure_request())
    attachment = await public_host.attach_session(session.session_id)
    actor_started = threading.Event()
    actor_release = threading.Event()
    admission_submitted = asyncio.Event()
    fatal_started = asyncio.Event()
    wake_seen = asyncio.Event()
    original_submit = DurableActor.submit
    original_wake = HostDispatchScheduler.wake_queue_promotion

    def actor_barrier(_handle: HostCommandHandle) -> None:
        """占住 actor worker直到 caller 取消与 fatal 均已排定。

        :param _handle: actor 私有 command handle。
        :returns: ``None``。
        :raises RuntimeError: barrier 超时未释放时抛出。
        """

        actor_started.set()
        if not actor_release.wait(timeout=2):
            raise RuntimeError("cancelled admission actor barrier timed out")

    barrier_future = original_submit(public_host._durable_actor, actor_barrier)
    assert await asyncio.to_thread(actor_started.wait, 1)

    def record_submit(
        self: DurableActor,
        operation: Callable[[HostCommandHandle], T],
    ) -> asyncio.Future[T]:
        """记录 actor submission 并委托真实实现。

        :param self: durable actor。
        :param operation: typed actor operation。
        :returns: 原始 actor future。
        :raises Exception: 原始 submit 异常时透传。
        """

        future = original_submit(self, operation)
        if self is public_host._durable_actor:
            admission_submitted.set()
        return future

    def record_wake(self: HostDispatchScheduler, session_id: str) -> None:
        """记录 matching wake 并委托真实 scheduler。

        :param self: scheduler。
        :param session_id: wake Session id。
        :returns: ``None``。
        :raises Exception: 原始 wake 异常时透传。
        """

        wake_seen.set()
        original_wake(self, session_id)

    async def report_fatal() -> bool:
        """注入 deterministic fatal transition。

        :returns: fatal 是否提交 transition。
        :raises Exception: health owner 异常时透传。
        """

        fatal_started.set()
        return await public_host._health_gate.report_fatal(
            component="dispatch",
            reason_code="cancelled_admission_race",
        )

    monkeypatch.setattr(DurableActor, "submit", record_submit)
    monkeypatch.setattr(HostDispatchScheduler, "wake_queue_promotion", record_wake)
    submit_task = asyncio.create_task(
        public_host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "cancelled-admission"),
        )
    )
    await admission_submitted.wait()
    submit_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await submit_task
    fatal_task = asyncio.create_task(report_fatal())
    await fatal_started.wait()
    assert public_host._health_gate.state is HostExecutionHealthState.READY

    actor_release.set()
    try:
        await barrier_future
        await wake_seen.wait()
        assert await fatal_task is True
        assert public_host._health_gate.state is HostExecutionHealthState.UNAVAILABLE
    finally:
        actor_release.set()
        await asyncio.shield(attachment.aclose())
        await manager.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_open_host_wait_poller_policy_without_poll_registry_fails_fast(
    tmp_path: pathlib.Path,
) -> None:
    """启用 wait poller 但缺少 poll adapter registry 时 opener fail fast。"""

    options = replace(
        _options(tmp_path, _FinalAnswerWorkerFactory()),
        wait_poller_policy=_wait_poller_policy(),
    )

    with pytest.raises(HostApiError) as exc_info:
        async with open_host(options):
            raise AssertionError("open_host must fail before yielding")

    assert exc_info.value.code is HostApiErrorCode.INVALID_STATE
    assert "wait_poll_adapter_registry" in exc_info.value.message


@pytest.mark.asyncio
async def test_open_host_disabled_wait_poller_policy_without_poll_registry_opens(
    tmp_path: pathlib.Path,
) -> None:
    """policy.enabled=False 时不要求 poll adapter registry。"""

    options = replace(
        _options(tmp_path, _FinalAnswerWorkerFactory()),
        wait_poller_policy=_wait_poller_policy(enabled=False),
    )

    async with open_host(options):
        pass


@pytest.mark.asyncio
async def test_open_host_wait_poller_resolves_waiting_run_in_background(
    tmp_path: pathlib.Path,
) -> None:
    """open_host 启用 poller 后会通过 background loop resolve WAITING run。"""

    factory = _FinalAnswerWorkerFactory()
    base_options = _options(tmp_path, factory)
    adapter = _ReadyPollAdapter()
    options = replace(
        base_options,
        tooling_options=_tooling_options_with_poll_registry(
            _poll_adapter_registry(adapter)
        ),
        wait_poller_policy=_wait_poller_policy(),
    )
    seed_command_options = replace(
        _command_options_from_open_host_options(
            options,
            host_handle_id="host-open-runtime-poller-seed",
        ),
        local_execution=None,
    )
    seed_host = create_execution_command_handle(
        seed_command_options,
        ordinary_run_baseline=options.ordinary_run_baseline,
        memory_projection_policy=options.memory_projection_policy,
        tooling_options=options.tooling_options,
        context_budget_policy=options.context_budget_policy,
        enable_truncation_manager=options.enable_truncation_manager,
    )
    try:
        seeded = _seed_waiting_run(
            seed_host,
            tooling_options=options.tooling_options,
        )
    finally:
        seed_host.close()

    async with open_host(options) as host:
        final_run = await _wait_for_run_status(
            host,
            seeded.run_id,
            RunStatus.SUCCEEDED,
        )

    assert final_run.status is RunStatus.SUCCEEDED
    assert adapter.poll_count == 1
    assert len(factory.accepted_snapshots) == 1
    assert factory.accepted_snapshots[0].run_id == seeded.run_id


@pytest.mark.asyncio
async def test_open_host_has_no_session_recovery_side_effect_before_ready(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单独 open_host 不创建 target recovery scanner。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises Exception: opener 失败时透传。
    """

    scan_calls = 0

    def record_scan(
        self: SessionAttachmentRecoveryScanner,
        policy: SessionAttachmentRecoveryPolicy | None = None,
    ) -> SessionAttachmentRecoveryScanResult:
        """记录任何意外 recovery scan。

        :param self: target recovery scanner。
        :param policy: 可选 recovery policy。
        :returns: 空 scan 结果。
        :raises Exception: 不主动抛出异常。
        """

        nonlocal scan_calls
        del self, policy
        scan_calls += 1
        return SessionAttachmentRecoveryScanResult(actions=())

    monkeypatch.setattr(SessionAttachmentRecoveryScanner, "scan", record_scan)
    async with open_host(_options(tmp_path, _FinalAnswerWorkerFactory())):
        assert scan_calls == 0
    assert scan_calls == 0


@pytest.mark.asyncio
async def test_attachment_recovery_failure_does_not_fail_open_host(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """target recovery failure 只使 attachment factory 失败。"""

    catch_up_calls = 0

    def raise_recovery_scan(
        self: SessionAttachmentRecoveryScanner,
        policy: SessionAttachmentRecoveryPolicy | None = None,
    ) -> None:
        """模拟 target recovery scan 失败。

        :param self: 被 monkeypatch 的 scanner。
        :param policy: 可选 fixed-now recovery policy。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出测试错误。
        """

        del self, policy
        raise RuntimeError("forced startup recovery failure")

    def record_catch_up(
        self: _CompositeProjectionCatchupPort,
    ) -> None:
        """记录启动失败清理路径的 projection catch-up。

        :param self: 被 monkeypatch 的 composite catch-up port。
        :returns: ``None``。
        """

        nonlocal catch_up_calls
        del self
        catch_up_calls += 1

    monkeypatch.setattr(
        SessionAttachmentRecoveryScanner,
        "scan",
        raise_recovery_scan,
    )
    monkeypatch.setattr(
        _CompositeProjectionCatchupPort,
        "catch_up_projection",
        record_catch_up,
    )
    async with open_host(_options(tmp_path, _FinalAnswerWorkerFactory())) as host:
        session = await host.ensure_session(
            EnsureSessionRequest(
                scope="workspace",
                slot_key="attach-failure",
                metadata=(),
            )
        )
        with pytest.raises(RuntimeError, match="forced startup recovery failure"):
            await host.attach_session(session.session_id)

    assert catch_up_calls == 1


@pytest.mark.asyncio
async def test_host_close_cancels_all_sleeping_delayed_recovery_tasks_before_actor_stop(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Host close 在 actor stop 前取消/join task，且不提前释放 mutex。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: task 泄漏、第二次 scan 或 mutex 释放顺序错误时抛出。
    """

    scan_calls = 0
    schedule_deadline = True
    sleep_started = asyncio.Event()
    actor_stop_entered = asyncio.Event()
    actor_stop_release = asyncio.Event()
    module = cast(ModuleType, sys.modules["dayu.host.open_host"])
    original_stop_and_drain = DurableActor.stop_and_drain

    def scheduled_scan(
        scanner: SessionAttachmentRecoveryScanner,
        policy: SessionAttachmentRecoveryPolicy | None = None,
    ) -> SessionAttachmentRecoveryScanResult:
        """首个 Host 返回 deadline，fresh Host 返回无 schedule。

        :param scanner: target scanner。
        :param policy: fixed-now policy。
        :returns: synthetic typed scan result。
        :raises Exception: 不主动抛出异常。
        """

        nonlocal scan_calls
        del scanner, policy
        scan_calls += 1
        return SessionAttachmentRecoveryScanResult(
            actions=(),
            next_reconcile_at=(
                datetime.now(UTC) + timedelta(minutes=5)
                if schedule_deadline
                else None
            ),
        )

    async def blocked_sleep(deadline: datetime) -> None:
        """让 Host close 精确取消尚未提交 actor 的 task。

        :param deadline: initial scan deadline。
        :returns: ``None``。
        :raises asyncio.CancelledError: Host close 取消时抛出。
        """

        del deadline
        sleep_started.set()
        await asyncio.Event().wait()

    async def block_target_actor_stop(actor: DurableActor) -> None:
        """在目标 Host actor stop 入口设置 mutex 顺序观察 barrier。

        :param actor: 当前关闭的 durable actor。
        :returns: ``None``。
        :raises Exception: 原始 actor stop 失败时透传。
        """

        if actor is public_host._durable_actor:
            actor_stop_entered.set()
            await actor_stop_release.wait()
        await original_stop_and_drain(actor)

    monkeypatch.setattr(SessionAttachmentRecoveryScanner, "scan", scheduled_scan)
    monkeypatch.setattr(module, "_sleep_until_recovery_deadline", blocked_sleep)
    options = _options(tmp_path, _FinalAnswerWorkerFactory())
    manager = open_host(options)
    public_host = cast(_PublicHostHandle, await manager.__aenter__())
    session = await public_host.ensure_session(_ensure_request())
    attachment = await public_host.attach_session(session.session_id)
    await asyncio.wait_for(sleep_started.wait(), timeout=1)
    monkeypatch.setattr(
        DurableActor,
        "stop_and_drain",
        block_target_actor_stop,
    )

    close_task = asyncio.create_task(public_host.close())
    await asyncio.wait_for(actor_stop_entered.wait(), timeout=1)

    assert public_host._delayed_attachment_recovery_tasks == {}
    assert scan_calls == 1
    assert close_task.done() is False

    try:
        async with open_host(options) as observer_host:
            observer_attachment = await observer_host.attach_session(
                session.session_id
            )
            try:
                assert observer_attachment.access_mode.value == "read_only"
            finally:
                await observer_attachment.aclose()
    finally:
        actor_stop_release.set()
        await close_task

    assert public_host._health_gate.state is HostExecutionHealthState.CLOSED
    await attachment.aclose()
    await manager.__aexit__(None, None, None)

    schedule_deadline = False
    async with open_host(options) as fresh_host:
        fresh_attachment = await fresh_host.attach_session(session.session_id)
        try:
            assert fresh_attachment.access_mode.value == "read_write"
        finally:
            await fresh_attachment.aclose()
    assert scan_calls == 2


@pytest.mark.asyncio
async def test_delayed_recovery_failure_reports_safe_fatal_and_does_not_leak_task(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """delayed scan 异常只以安全 type 报 fatal，正常 cleanup task 引用。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :param caplog: pytest 日志捕获 fixture。
    :returns: ``None``。
    :raises AssertionError: fatal detail、日志脱敏或 task cleanup 漂移时抛出。
    """

    scan_calls = 0
    module = cast(ModuleType, sys.modules["dayu.host.open_host"])

    def fail_delayed_scan(
        scanner: SessionAttachmentRecoveryScanner,
        policy: SessionAttachmentRecoveryPolicy | None = None,
    ) -> SessionAttachmentRecoveryScanResult:
        """首次返回 deadline，第二次抛出带敏感文本的异常。

        :param scanner: target scanner。
        :param policy: fixed-now policy。
        :returns: initial typed result。
        :raises RuntimeError: delayed scan 固定抛出。
        """

        nonlocal scan_calls
        del scanner, policy
        scan_calls += 1
        if scan_calls == 1:
            return SessionAttachmentRecoveryScanResult(
                actions=(),
                next_reconcile_at=datetime.now(UTC),
            )
        raise RuntimeError("sensitive delayed recovery detail")

    async def immediate_sleep(deadline: datetime) -> None:
        """立即进入 delayed actor scan。

        :param deadline: initial scan deadline。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        del deadline

    monkeypatch.setattr(SessionAttachmentRecoveryScanner, "scan", fail_delayed_scan)
    monkeypatch.setattr(module, "_sleep_until_recovery_deadline", immediate_sleep)
    with caplog.at_level("ERROR", logger="dayu.host.open_host"):
        async with open_host(_options(tmp_path, _FinalAnswerWorkerFactory())) as host:
            public_host = cast(_PublicHostHandle, host)
            session = await host.ensure_session(_ensure_request())
            attachment = await host.attach_session(session.session_id)
            try:
                for _ in range(100):
                    if (
                        public_host._health_gate.state
                        is HostExecutionHealthState.UNAVAILABLE
                    ):
                        break
                    await asyncio.sleep(0.01)
                assert public_host._health_gate.state is (
                    HostExecutionHealthState.UNAVAILABLE
                )
                assert public_host._delayed_attachment_recovery_tasks == {}
            finally:
                await attachment.aclose()

    assert "error_type=RuntimeError" in caplog.text
    assert "sensitive delayed recovery detail" not in caplog.text


@pytest.mark.asyncio
async def test_open_host_startup_failure_closes_poller_before_scheduler(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """open_host ready 前失败时先关闭已创建 poller，再关闭 scheduler。"""

    order: list[str] = []
    original_public_init = _PublicHostHandle.__init__
    original_poller_close = WaitPollerSupervisor.close
    original_scheduler_close = HostDispatchScheduler.close

    def raise_public_handle_init(
        self: _PublicHostHandle,
        *,
        durable_actor: DurableActor,
        health_gate: HostExecutionHealthGate,
        host_handle_id: str,
        scheduler: HostDispatchScheduler,
        session_attachment_registry: HostSessionAttachmentRegistry,
        projection_catchup_port: ProjectionCatchupPort,
        session_event_reconciliation_waiter: (
            _SessionEventReconciliationWaiter
        ),
        scheduler_store: HostDurableStore,
        terminal_post_commit_coordinator: _TerminalPostCommitCoordinator,
        transient_delta_hub: HostTransientDeltaHub,
        wait_poller: WaitPollerSupervisor | None,
    ) -> None:
        """模拟 public handle 构造失败。

        :param self: public handle。
        :param durable_actor: durable actor。
        :param health_gate: execution health gate。
        :param host_handle_id: Host handle id。
        :param scheduler: scheduler。
        :param session_attachment_registry: opener attachment registry。
        :param projection_catchup_port: projection catch-up port。
        :param session_event_reconciliation_waiter: opener-local session
            event reconciliation waiter。
        :param scheduler_store: scheduler durable store。
        :param terminal_post_commit_coordinator: opener terminal coordinator。
        :param transient_delta_hub: 当前 Host runtime 瞬态 hub。
        :param wait_poller: wait poller。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出测试错误。
        """

        del self, durable_actor, health_gate, host_handle_id, scheduler
        del session_attachment_registry
        del projection_catchup_port
        del session_event_reconciliation_waiter
        del scheduler_store
        del terminal_post_commit_coordinator
        del transient_delta_hub
        assert wait_poller is not None
        raise RuntimeError("forced public handle init failure")

    def record_poller_close(self: WaitPollerSupervisor) -> None:
        """记录 poller cleanup。

        :param self: wait poller supervisor。
        :returns: ``None``。
        """

        order.append("poller")
        original_poller_close(self)

    async def record_scheduler_close(self: HostDispatchScheduler) -> None:
        """记录 scheduler cleanup。

        :param self: scheduler。
        :returns: ``None``。
        """

        order.append("scheduler")
        await original_scheduler_close(self)

    monkeypatch.setattr(_PublicHostHandle, "__init__", raise_public_handle_init)
    monkeypatch.setattr(WaitPollerSupervisor, "close", record_poller_close)
    monkeypatch.setattr(HostDispatchScheduler, "close", record_scheduler_close)

    options = replace(
        _options(tmp_path, _FinalAnswerWorkerFactory()),
        tooling_options=_tooling_options_with_poll_registry(WaitPollAdapterRegistry(())),
        wait_poller_policy=_wait_poller_policy(),
    )

    with pytest.raises(RuntimeError, match="forced public handle init failure"):
        async with open_host(options):
            raise AssertionError("open_host must fail before yielding")

    assert order[:2] == ["poller", "scheduler"]
    monkeypatch.setattr(_PublicHostHandle, "__init__", original_public_init)


@pytest.mark.asyncio
async def test_open_host_after_commit_does_not_inject_memory_catchup_port(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """open_host after-commit 热路径不再注入 conversation memory catch-up。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    """

    options = _options(tmp_path, _FinalAnswerWorkerFactory())
    observed_ports: list[ProjectionCatchupPort | None] = []
    original_open = HostDispatchScheduler.open

    async def record_scheduler_open(
        cls: type[HostDispatchScheduler],
        *,
        transaction_runner: HostTransactionRunner,
        local_execution: HostLocalExecutionOptions,
        host_handle_id: str,
        transient_delta_publisher: HostTransientDeltaPublisher,
        terminal_post_commit_port_factory: _TerminalPostCommitPortFactory,
        session_new_work_access: SessionNewWorkAccessPort,
        active_registry: ActiveWorkerRegistry | None = None,
        projection_catchup_port: ProjectionCatchupPort | None = None,
        health_gate: HostExecutionHealthGate | None = None,
    ) -> HostDispatchScheduler:
        """记录 scheduler open 时的 projection port 并委托真实 open。

        :param cls: scheduler class。
        :param transaction_runner: Host transaction runner。
        :param local_execution: 本地执行配置。
        :param host_handle_id: Host handle id。
        :param transient_delta_publisher: Host 瞬态增量 publisher。
        :param terminal_post_commit_port_factory: terminal port 构造期工厂。
        :param session_new_work_access: Session new-work access port。
        :param active_registry: active worker registry。
        :param projection_catchup_port: commit 后 projection catch-up port。
        :param health_gate: shared execution health gate。
        :returns: 已打开 scheduler。
        """

        observed_ports.append(projection_catchup_port)
        return await original_open.__func__(
            cls,
            transaction_runner=transaction_runner,
            local_execution=local_execution,
            host_handle_id=host_handle_id,
            transient_delta_publisher=transient_delta_publisher,
            terminal_post_commit_port_factory=terminal_post_commit_port_factory,
            session_new_work_access=session_new_work_access,
            active_registry=active_registry,
            projection_catchup_port=projection_catchup_port,
            health_gate=health_gate,
        )

    monkeypatch.setattr(
        HostDispatchScheduler,
        "open",
        classmethod(record_scheduler_open),
    )

    async with open_host(options):
        pass

    assert observed_ports == [None]


@pytest.mark.asyncio
async def test_open_host_dispatch_memory_catchup_reaches_required_cursor(
    tmp_path: pathlib.Path,
) -> None:
    """dispatch 前 required memory catch-up 会追到 required cursor 后接受 worker。"""

    factory = _FinalAnswerWorkerFactory()
    options = replace(
        _options(tmp_path, factory),
        memory_projection_catchup_batch_size=1,
    )

    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        attachment = await host.attach_session(session.session_id)
        try:
            followup = await host.submit_followup(
                session.session_id,
                _followup_request(session.session_id, "required-memory-dispatch"),
            )
            final_run = await _wait_for_run_status(
                host,
                followup.accepted_run_id,
                RunStatus.SUCCEEDED,
            )
        finally:
            await asyncio.shield(attachment.aclose())

    assert final_run.status is RunStatus.SUCCEEDED
    assert len(factory.accepted_snapshots) == 1
    assert len(factory.accepted_requests) == 1


@pytest.mark.asyncio
async def test_open_host_admin_purge_keeps_execution_capability_separate(
    tmp_path: pathlib.Path,
) -> None:
    """HostAdmin purge 后 execution read fail closed，且 execution 无 purge。"""

    options = _options(tmp_path, _FinalAnswerWorkerFactory())

    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        attachment = await host.attach_session(session.session_id)
        try:
            await host.close_session(
                session.session_id,
                _close_request("close-before-purge"),
            )
            assert not hasattr(host, "purge_session")
        finally:
            await asyncio.shield(attachment.aclose())

    async with open_host_admin(_admin_options(options)) as host_admin:
        result = await host_admin.purge_session(
            session.session_id,
            _purge_request("purge-open-host"),
        )
        assert result.session_id == session.session_id
        assert result.purged is True
        assert result.purge_tombstone_ref is not None
        assert result.deleted_counts_digest is not None
    async with open_host(options) as reopened_host:
        with pytest.raises(HostApiError) as get_session_exc:
            await reopened_host.get_session(session.session_id)
        assert get_session_exc.value.code == HostApiErrorCode.NOT_FOUND


def test_compactor_runner_baseline_none_maps_to_fail_closed_no_capability(
    tmp_path: pathlib.Path,
) -> None:
    """未提供 compactor baseline 时本地执行配置不安装 fake compact 能力。"""

    local_execution = _local_execution_options_from_open_host_options(
        _options(tmp_path, _FinalAnswerWorkerFactory())
    )

    assert local_execution.context_compactor is None
    assert local_execution.compactor_runner_spec is None
    assert local_execution.compactor_runner_options is None
    assert local_execution.compactor_policy_ref is None
    assert local_execution.compact_artifact_root is None


def test_compactor_runner_baseline_maps_to_host_owned_compactor(
    tmp_path: pathlib.Path,
) -> None:
    """public runner baseline 在 opener 内部构造 Host-owned LLM compactor。"""

    runner_spec = _runner_spec()
    runner_options = RunnerCallOptions(
        temperature=0.1,
        max_tokens=128,
        top_p=None,
        stream=False,
    )
    options = _options(tmp_path, _FinalAnswerWorkerFactory())
    local_execution = _local_execution_options_from_open_host_options(
        replace(
            options,
            compactor_runner_baseline=CompactorRunnerBaseline(
                compactor_runner_spec=runner_spec,
                compactor_runner_options=runner_options,
                compactor_agent_policy=AgentPolicy(
                    max_iterations=1,
                    continuation_max_attempts=0,
                    allow_tool_calls=False,
                    tool_execution_timeout_seconds=1.0,
                    fallback_prompt="test fallback prompt",
                    continuation_prompt="test continuation prompt",
                ),
                compactor_system_prompt="test compactor system prompt",
                compactor_user_prompt_template=(
                    "test compactor user prompt <<compaction_request>>"
                ),
                compact_artifact_root=tmp_path / "compact-artifacts",
                compact_artifact_create_parent_dirs=False,
            ),
        )
    )

    assert isinstance(local_execution.context_compactor, LLMContextCompactor)
    assert local_execution.compactor_runner_spec is runner_spec
    assert local_execution.compactor_runner_options is runner_options
    assert local_execution.compactor_policy_ref is None
    assert local_execution.compact_artifact_root == tmp_path / "compact-artifacts"
    assert local_execution.compact_artifact_create_parent_dirs is False


def test_command_options_reflect_explicit_context_budget_policy(
    tmp_path: pathlib.Path,
) -> None:
    """显式 opener context budget policy 必须传入内部 command option 映射。"""

    policy = default_context_budget_policy(context_window_size=16384)
    options = replace(
        _options(tmp_path, _FinalAnswerWorkerFactory()),
        context_budget_policy=policy,
    )

    command_options = _command_options_from_open_host_options(
        options,
        host_handle_id="host-command-policy-test",
    )

    assert command_options.context_window_size == policy.context_window_size
    assert 0 < command_options.reserved_output_tokens < policy.context_window_size
    assert command_options.local_execution is not None
    assert command_options.local_execution.context_budget_policy is policy


async def _wait_for_run_status(
    host: Host,
    run_id: str,
    expected_status: RunStatus,
) -> RunSnapshot:
    """等待 Run 到达指定状态。

    :param host: public Host handle。
    :param run_id: 目标 Run id。
    :param expected_status: 期待状态。
    :returns: 最终 Run snapshot。
    :raises AssertionError: 超时仍未到达期待状态时抛出。
    """

    for _ in range(100):
        snapshot = await host.get_run(run_id)
        if snapshot.status == expected_status:
            return snapshot
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} did not reach {expected_status.value}")


async def _next_terminal(watcher: AsyncIterator[HostSessionEvent]) -> HostEvent:
    """读取下一个 terminal HostEvent。

    :param watcher: session event watcher。
    :returns: terminal HostEvent。
    :raises AssertionError: watcher 提前结束时抛出。
    """

    async for event in watcher:
        if isinstance(event, HostEvent) and event.kind in (
            HostEventKind.SUCCEEDED,
            HostEventKind.FAILED,
            HostEventKind.CANCELLED,
            HostEventKind.LOST,
        ):
            return event
    raise AssertionError("watcher ended before terminal event")


async def _collect_until_two_terminals(
    watcher: HostSessionEventIterator,
) -> tuple[HostSessionEvent, ...]:
    """收集 watcher events，直到观察到两个 non-PROGRESS terminal。

    :param watcher: Session event iterator。
    :returns: 包含第二个 terminal 的有序事件前缀。
    :raises AssertionError: watcher 提前结束时抛出。
    """

    collected: list[HostSessionEvent] = []
    terminal_count = 0
    async for event in watcher:
        collected.append(event)
        if isinstance(event, HostEvent) and event.kind is not HostEventKind.PROGRESS:
            terminal_count += 1
            if terminal_count == 2:
                return tuple(collected)
    raise AssertionError("watcher ended before two terminal events")


async def _close_iterator(iterator: HostSessionEventIterator) -> None:
    """关闭测试中持有的 async generator iterator。

    :param iterator: HostSessionEvent async iterator。
    :returns: ``None``。
    """

    await iterator.aclose()


def _mark_current_dispatch_owner_as_stale_running(
    options: OpenHostOptions,
    run_id: str,
) -> None:
    """把当前 dispatch owner liveness 改写成 startup recovery 可证明 orphan。

    :param options: open_host options。
    :param run_id: 目标 Run id。
    :returns: ``None``。
    """

    with open_host_durable_store(_durable_options_from_open_options(options)) as store:

        def operation(transaction: HostTransaction) -> None:
            """执行 liveness 改写。

            :param transaction: Host transaction。
            :returns: ``None``。
            """

            transaction.execute(
                """
                UPDATE host_instances
                SET
                  pid = ?,
                  heartbeat_at = ?,
                  status = ?
                WHERE host_instance_id = (
                  SELECT dispatch.owner_host_instance_id
                  FROM host_runs AS run
                  JOIN host_attempt_dispatch_records AS dispatch
                    ON dispatch.attempt_id = run.current_attempt_id
                  WHERE run.run_id = ?
                )
                """,
                (
                    999_999,
                    "2000-01-01T00:00:00.000000Z",
                    "running",
                    run_id,
                ),
            )

        store.transaction_runner.run_write(operation)


def _mark_current_dispatch_owner_as_recent_running(
    options: OpenHostOptions,
    run_id: str,
    *,
    heartbeat_at: datetime,
) -> None:
    """把已关闭 owner 改为 pid missing 但 heartbeat 仍 recent 的测试事实。

    :param options: 同源 open_host options。
    :param run_id: 目标 active Run id。
    :param heartbeat_at: 目标 UTC-aware heartbeat 时间。
    :returns: ``None``。
    :raises ValueError: heartbeat 缺少 timezone 时抛出。
    :raises Exception: durable write 失败时透传。
    """

    if heartbeat_at.tzinfo is None or heartbeat_at.utcoffset() is None:
        raise ValueError("heartbeat_at must be timezone-aware")
    heartbeat_text = heartbeat_at.astimezone(UTC).isoformat().replace(
        "+00:00",
        "Z",
    )
    with open_host_durable_store(_durable_options_from_open_options(options)) as store:

        def operation(transaction: HostTransaction) -> None:
            """更新 current dispatch owner liveness。

            :param transaction: Host write transaction。
            :returns: ``None``。
            :raises Exception: SQLite 写入失败时透传。
            """

            result = transaction.execute(
                """
                UPDATE host_instances
                SET
                  pid = ?,
                  heartbeat_at = ?,
                  status = ?
                WHERE host_instance_id = (
                  SELECT dispatch.owner_host_instance_id
                  FROM host_runs AS run
                  JOIN host_attempt_dispatch_records AS dispatch
                    ON dispatch.attempt_id = run.current_attempt_id
                  WHERE run.run_id = ?
                )
                """,
                (
                    999_999,
                    heartbeat_text,
                    "running",
                    run_id,
                ),
            )
            assert result.rowcount == 1

        store.transaction_runner.run_write(operation)


def _durable_options_from_open_options(
    options: OpenHostOptions,
) -> HostDurableStoreOptions:
    """从 OpenHostOptions 构造测试 durable store options。

    :param options: public open options。
    :returns: durable store options。
    """

    return HostDurableStoreOptions(
        db_path=options.db_path,
        payload_policy=PayloadStoragePolicy(
            artifact_root=options.artifact_root,
            payload_inline_threshold_bytes=options.payload_inline_threshold_bytes,
            create_artifact_root=options.create_parent_dirs,
        ),
        create_parent_dirs=options.create_parent_dirs,
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=options.sqlite_busy_timeout_seconds,
            write_busy_retry_count=options.sqlite_write_busy_retry_count,
            write_retry_initial_delay_seconds=(
                options.sqlite_write_retry_initial_delay_seconds
            ),
            write_retry_backoff_multiplier=(
                options.sqlite_write_retry_backoff_multiplier
            ),
            write_retry_max_delay_seconds=options.sqlite_write_retry_max_delay_seconds,
        ),
    )


def _event_type_count(db_path: pathlib.Path, event_type: str) -> int:
    """统计指定 EventLog 类型数量。

    :param db_path: Host durable SQLite DB 路径。
    :param event_type: event type。
    :returns: 匹配事件数。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM event_log WHERE event_type = ?",
            (event_type,),
        ).fetchone()
    assert row is not None
    return int(row[0])


def _recovery_event_order_and_reason(
    db_path: pathlib.Path,
    run_id: str,
) -> tuple[tuple[str, ...], str]:
    """读取单 Run canonical event 顺序与 recovery start reason。

    :param db_path: Host durable SQLite DB 路径。
    :param run_id: 目标 Run id。
    :returns: event type 序列与最后一条 ``RUN_STARTED`` 的 start reason。
    :raises AssertionError: recovery start row 或 payload 不完整时抛出。
    :raises Exception: SQLite 查询或 JSON 解析失败时透传。
    """

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT event_type, payload_json
            FROM event_log
            WHERE run_id = ?
            ORDER BY event_sequence ASC
            """,
            (run_id,),
        ).fetchall()
    event_types = tuple(str(row[0]) for row in rows)
    started_payloads = tuple(
        json.loads(str(row[1]))
        for row in rows
        if str(row[0]) == "RUN_STARTED"
    )
    assert len(started_payloads) == 2
    recovery_payload = started_payloads[-1]
    assert isinstance(recovery_payload, dict)
    start_reason = recovery_payload.get("start_reason")
    assert isinstance(start_reason, str)
    return event_types, start_reason


def _options(
    tmp_path: pathlib.Path,
    worker_factory: LocalEngineWorkerFactory,
) -> OpenHostOptions:
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


def _admin_options(options: OpenHostOptions) -> OpenHostAdminOptions:
    """从 execution options 投影同源 admin durable policy。

    :param options: execution opener options。
    :returns: admin opener options。
    :raises Exception: 不主动抛出异常。
    """

    return OpenHostAdminOptions(
        db_path=options.db_path,
        artifact_root=options.artifact_root,
        create_parent_dirs=options.create_parent_dirs,
        sqlite_busy_timeout_seconds=options.sqlite_busy_timeout_seconds,
        sqlite_write_busy_retry_count=options.sqlite_write_busy_retry_count,
        sqlite_write_retry_initial_delay_seconds=(
            options.sqlite_write_retry_initial_delay_seconds
        ),
        sqlite_write_retry_backoff_multiplier=(
            options.sqlite_write_retry_backoff_multiplier
        ),
        sqlite_write_retry_max_delay_seconds=(
            options.sqlite_write_retry_max_delay_seconds
        ),
        payload_inline_threshold_bytes=options.payload_inline_threshold_bytes,
    )


def _tooling_options_with_poll_registry(
    registry: WaitPollAdapterRegistry,
) -> HostToolingOptions:
    """构造带 production poll registry 的测试 tooling options。

    :param registry: wait poll adapter registry。
    :returns: Host tooling options。
    """

    return replace(
        awaiting_tooling_options(),
        wait_poll_adapter_registry=registry,
    )


def _poll_adapter_registry(adapter: _ReadyPollAdapter) -> WaitPollAdapterRegistry:
    """构造匹配 resolve_wait seed helper 的 poll adapter registry。

    :param adapter: ready poll adapter。
    :returns: wait poll adapter registry。
    """

    return WaitPollAdapterRegistry(
        (
            WaitPollAdapterRegistration(
                adapter_key=WaitAdapterKey("poll:long-tool"),
                adapter=adapter,
            ),
        )
    )


def _wait_poller_policy(*, enabled: bool = True) -> WaitPollerRuntimePolicy:
    """构造测试用 wait poller policy。

    :param enabled: 是否启用 poller。
    :returns: wait poller runtime policy。
    """

    return WaitPollerRuntimePolicy(
        enabled=enabled,
        poll_interval_seconds=0.01,
        claim_ttl_seconds=0.5,
        claim_batch_size=2,
        backoff_initial_delay_seconds=0.01,
        backoff_multiplier=2.0,
        backoff_max_delay_seconds=0.05,
        not_ready_observe_interval_seconds=0.01,
        idle_poll_interval_seconds=0.01,
        adapter_call_timeout_seconds=0.1,
        close_drain_timeout_seconds=0.2,
        max_outstanding_adapter_calls=4,
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


def _ensure_request() -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :returns: EnsureSessionRequest。
    """

    return EnsureSessionRequest(
        scope="workspace",
        slot_key="open-host-runtime",
        metadata=(),
    )


def _close_request(client_request_id: str) -> CloseSessionRequest:
    """构造 close session 请求。

    :param client_request_id: 幂等请求 id。
    :returns: CloseSessionRequest。
    """

    return CloseSessionRequest(
        context=_context(client_request_id),
        client_request_id=client_request_id,
        reason="open_host_runtime_close",
    )


def _purge_request(client_request_id: str) -> PurgeSessionRequest:
    """构造 purge session 请求。

    :param client_request_id: 幂等请求 id。
    :returns: PurgeSessionRequest。
    """

    return PurgeSessionRequest(
        context=_context(client_request_id),
        client_request_id=client_request_id,
        reason="open_host_runtime_purge",
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


def _cancel_request(client_request_id: str) -> CancelRunRequest:
    """构造 cancel_run 请求。

    :param client_request_id: 幂等请求 id。
    :returns: CancelRunRequest。
    """

    return CancelRunRequest(
        context=_context(client_request_id),
        client_request_id=client_request_id,
        reason="open_host_runtime_cancel",
        mode=CancelMode.GRACEFUL,
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
            operation_name="open_host_runtime",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="p10_5_slice2",
            correlation_id="corr-open-host-runtime",
        ),
    )
