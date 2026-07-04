"""Host Phase 5 active cancel 与 dispatch cancel 集成测试。"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    RunCancelledData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
from dayu.host import (
    AuthorizationClaim,
    CancelMode,
    CancelRunRequest,
    CancelSessionRunsRequest,
    HostCallContext,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
    OperationContext,
    RunStatus,
    cancel_run,
    cancel_session_runs,
    ensure_session,
)
from dayu.host.admission import PendingDispatchRecord
from dayu.host.api import (
    HostInput,
    AttemptDispatchSnapshot,
    AttemptStatus,
    EnsureSessionRequest,
    HostCommandHandleOptions,
    HostLocalExecutionOptions,
    StartRunRequest,
)
from dayu.host.command import HostCommandHandle, create_host_command_handle, start_run
from dayu.host.dispatch import ActiveWorkerRegistry, HostDispatchScheduler
from dayu.host.durable.connection import HostDurableStore, open_host_durable_store
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.state import (
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_LANE_NAME = "llm"


@dataclass(frozen=True, slots=True)
class _RunRefs:
    """测试 Run 的 durable 引用。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


class _CancelAwareHandle:
    """收到 cancel 后发出 run_cancelled 的 fake worker handle。"""

    def __init__(self, *, local_worker_id: str, terminal: str) -> None:
        """初始化 fake handle。

        :param local_worker_id: 本地 worker id。
        :param terminal: terminal 行为，支持 ``cancelled``、``final``、``hang``、
            ``blocked``。
        :returns: ``None``。
        """

        self._local_worker_id = local_worker_id
        self._terminal = terminal
        self._cancelled = asyncio.Event()
        self._session_id: str | None = None
        self._run_id: str | None = None
        self.cancel_reasons: list[str] = []
        self.closed = False

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        """

        return self._local_worker_id

    async def events(self) -> AsyncIterator[EngineEvent]:
        """返回 fake EngineEvent stream。

        :returns: EngineEvent 异步迭代器。
        """

        if self._terminal == "final":
            yield EngineEvent(
                occurred_at=_NOW,
                session_id=self._bound_session_id(),
                run_id=self._bound_run_id(),
                type=EngineEventType.FINAL_ANSWER,
                data=FinalAnswerData(
                    content="done",
                    filtered=False,
                    degraded=False,
                    finish_reason=FinishReason.STOP,
                ),
                metadata=None,
            )
            return
        await self._cancelled.wait()
        if self._terminal == "blocked":
            await asyncio.Event().wait()
        if self._terminal == "cancelled":
            yield EngineEvent(
                occurred_at=_NOW,
                session_id=self._bound_session_id(),
                run_id=self._bound_run_id(),
                type=EngineEventType.RUN_CANCELLED,
                data=RunCancelledData(
                    reason="user_stop",
                    requested_at=_NOW,
                    accepted_at=_NOW,
                    finished_at=_NOW,
                ),
                metadata=None,
            )

    def on_cancel(self, reason: str) -> None:
        """记录取消请求并唤醒事件流。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        self.cancel_reasons.append(reason)
        self._cancelled.set()

    def bind_snapshot(self, snapshot: AttemptDispatchSnapshot) -> None:
        """绑定 worker accept 时的 Host dispatch identity。

        :param snapshot: dispatch snapshot。
        :returns: ``None``。
        """

        self._session_id = snapshot.session_id
        self._run_id = snapshot.run_id

    async def close(self) -> None:
        """关闭 fake handle。

        :returns: ``None``。
        """

        self.closed = True

    def _bound_session_id(self) -> str:
        """返回已绑定的 Session id。

        :returns: Session id。
        :raises RuntimeError: worker 尚未 accept 时抛出。
        """

        if self._session_id is None:
            raise RuntimeError("worker snapshot is not bound")
        return self._session_id

    def _bound_run_id(self) -> str:
        """返回已绑定的 Run id。

        :returns: Run id。
        :raises RuntimeError: worker 尚未 accept 时抛出。
        """

        if self._run_id is None:
            raise RuntimeError("worker snapshot is not bound")
        return self._run_id


class _FakeWorker:
    """返回固定 fake handle 的 worker。"""

    def __init__(self, handle: _CancelAwareHandle) -> None:
        """初始化 fake worker。

        :param handle: worker accept 返回的 handle。
        :returns: ``None``。
        """

        self._handle = handle

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """接受 worker 请求。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: fake handle。
        """

        del request
        self._handle.bind_snapshot(snapshot)
        return self._handle


class _FakeWorkerFactory:
    """测试用 worker factory。"""

    def __init__(self, handle: _CancelAwareHandle) -> None:
        """初始化 worker factory。

        :param handle: worker accept 返回的 handle。
        :returns: ``None``。
        """

        self._handle = handle
        self.created = 0

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 fake worker。

        :param snapshot: dispatch snapshot。
        :returns: fake worker。
        """

        del snapshot
        self.created += 1
        return _FakeWorker(self._handle)


class _SequencedWorkerFactory:
    """按顺序返回 fake handle 的 worker factory。"""

    def __init__(self, handles: tuple[_CancelAwareHandle, ...]) -> None:
        """初始化 sequenced worker factory。

        :param handles: 每次 dispatch 依次使用的 fake handle。
        :returns: ``None``。
        """

        self._handles = handles
        self.created = 0

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 fake worker。

        :param snapshot: dispatch snapshot。
        :returns: fake worker。
        :raises RuntimeError: fake handle 数量不足时抛出。
        """

        del snapshot
        if self.created >= len(self._handles):
            raise RuntimeError("fake worker handle is exhausted")
        handle = self._handles[self.created]
        self.created += 1
        return _FakeWorker(handle)


def test_cancel_run_waiting_for_lane_skips_later_dispatch(tmp_path: Path) -> None:
    """waiting_for_lane direct cancel 后 scheduler wake 不会 dispatch。"""

    options = _command_options(tmp_path)
    host = create_host_command_handle(options)
    handle = _CancelAwareHandle(local_worker_id="worker-wait", terminal="hang")
    try:
        session_id = _session_id(host)
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            async def _dispatch_after_cancel() -> None:
                scheduler = await _open_scheduler(tmp_path, store, handle)
                try:
                    start_run(host, _start_request(session_id, "start-wait"))
                    refs = await _start_governed_refs(scheduler, session_id)
                    _mark_waiting_for_lane(store.transaction_runner, refs)
                    cancelled = cancel_run(
                        host, refs.run_id, _cancel_request("cancel-wait")
                    )
                    assert cancelled.status == RunStatus.CANCELLED
                    assert _attempt_status(options.db_path, refs.attempt_id) == (
                        AttemptStatus.CANCELLED
                    )

                    scheduler.wake_dispatch(_pending_dispatch(refs))
                    result = await scheduler.drain_once()
                    assert result.processed == 1
                    assert result.skipped == 1
                    assert handle.cancel_reasons == []
                finally:
                    await scheduler.close()

            asyncio.run(_dispatch_after_cancel())
    finally:
        host.close()


def test_cancel_run_dispatching_pre_accept_stays_cancelled(
    tmp_path: Path,
) -> None:
    """pre-accept dispatching direct cancel 不进入 CANCELLING。"""

    options = _command_options(tmp_path)
    host = create_host_command_handle(options)
    try:
        session_id = _session_id(host)
        refs: _RunRefs | None = None
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            async def _prepare_dispatching() -> _RunRefs:
                scheduler = await _open_scheduler(
                    tmp_path,
                    store,
                    _CancelAwareHandle(
                        local_worker_id="worker-dispatching",
                        terminal="hang",
                    ),
                )
                try:
                    start_run(
                        host,
                        _start_request(session_id, "start-dispatching"),
                    )
                    refs = await _start_governed_refs(scheduler, session_id)
                    _mark_dispatching(store.transaction_runner, refs)
                    return refs
                finally:
                    await scheduler.close()

            refs = asyncio.run(_prepare_dispatching())

        assert refs is not None
        cancelled = cancel_run(host, refs.run_id, _cancel_request("cancel-dispatching"))

        assert cancelled.status == RunStatus.CANCELLED
        assert _run_status(options.db_path, refs.run_id) == RunStatus.CANCELLED
        assert _attempt_status(options.db_path, refs.attempt_id) == (
            AttemptStatus.CANCELLED
        )
    finally:
        host.close()


@pytest.mark.asyncio
async def test_cancel_run_active_worker_propagates_and_closes_cancelled(
    tmp_path: Path,
) -> None:
    """Attempt RUNNING cancel 进入 CANCELLING，worker run_cancelled 后终态取消。"""

    options = _command_options(tmp_path)
    active_registry = ActiveWorkerRegistry()
    host = create_host_command_handle(options, active_registry=active_registry)
    handle = _CancelAwareHandle(local_worker_id="worker-active", terminal="cancelled")
    try:
        session_id = _session_id(host)
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path, store, handle, active_registry=active_registry
            )
            try:
                start_run(host, _start_request(session_id, "start-active"))
                refs = await _start_governed_refs(scheduler, session_id)
                scheduler.wake_dispatch(_pending_dispatch(refs))
                drain = await scheduler.drain_once()
                assert drain.dispatched == 1
                assert _attempt_status(options.db_path, refs.attempt_id) == (
                    AttemptStatus.RUNNING
                )

                cancelling = cancel_run(
                    host, refs.run_id, _cancel_request("cancel-active")
                )
                assert cancelling.status == RunStatus.CANCELLING
                assert handle.cancel_reasons == ["user_stop"]

                await _wait_for_run_status(
                    options.db_path,
                    refs.run_id,
                    RunStatus.CANCELLED,
                )
                assert _attempt_status(options.db_path, refs.attempt_id) == (
                    AttemptStatus.CANCELLED
                )
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_active_cancel_watchdog_times_out_non_cooperative_worker(
    tmp_path: Path,
) -> None:
    """active cancel watchdog 无需 worker terminal 也能关闭 Run/Attempt。"""

    options = _command_options(tmp_path)
    active_registry = ActiveWorkerRegistry()
    host = create_host_command_handle(options, active_registry=active_registry)
    handle = _CancelAwareHandle(local_worker_id="worker-timeout", terminal="blocked")
    try:
        session_id = _session_id(host)
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                handle,
                active_registry=active_registry,
                active_cancel_timeout_seconds=0.5,
            )
            try:
                start_run(host, _start_request(session_id, "start-timeout"))
                refs = await _start_governed_refs(scheduler, session_id)
                scheduler.wake_dispatch(_pending_dispatch(refs))
                drain = await scheduler.drain_once()
                assert drain.dispatched == 1

                cancelling = cancel_run(
                    host, refs.run_id, _cancel_request("cancel-timeout")
                )
                assert cancelling.status == RunStatus.CANCELLING

                result = scheduler.tick_active_cancel_watchdog(
                    datetime(2030, 1, 1, tzinfo=UTC)
                )

                assert result.closed == 1
                assert _run_status(options.db_path, refs.run_id) == RunStatus.CANCELLED
                assert _attempt_status(options.db_path, refs.attempt_id) == (
                    AttemptStatus.CANCELLED
                )
                assert _event_type_count(options.db_path, "RUN_CANCELLED") == 1
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_active_cancel_watchdog_noops_before_timeout(tmp_path: Path) -> None:
    """timeout 到期前 watchdog tick 不写 terminal fact。"""

    options = _command_options(tmp_path)
    active_registry = ActiveWorkerRegistry()
    host = create_host_command_handle(options, active_registry=active_registry)
    handle = _CancelAwareHandle(local_worker_id="worker-before-timeout", terminal="blocked")
    try:
        session_id = _session_id(host)
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                handle,
                active_registry=active_registry,
                active_cancel_timeout_seconds=300.0,
            )
            try:
                start_run(host, _start_request(session_id, "start-before-timeout"))
                refs = await _start_governed_refs(scheduler, session_id)
                scheduler.wake_dispatch(_pending_dispatch(refs))
                assert (await scheduler.drain_once()).dispatched == 1

                cancel_run(host, refs.run_id, _cancel_request("cancel-before-timeout"))
                result = scheduler.tick_active_cancel_watchdog(datetime.now(UTC))

                assert result.closed == 0
                assert _run_status(options.db_path, refs.run_id) == RunStatus.CANCELLING
                assert _event_type_count(options.db_path, "RUN_CANCELLED") == 0
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_active_cancel_watchdog_zero_cancelling_runs_noops(
    tmp_path: Path,
) -> None:
    """没有 CANCELLING Run 时 watchdog scan 为空操作。"""

    with open_host_durable_store(_durable_options(tmp_path)) as store:
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            _CancelAwareHandle(local_worker_id="worker-zero", terminal="blocked"),
            active_cancel_timeout_seconds=0.5,
        )
        try:
            result = scheduler.tick_active_cancel_watchdog(
                datetime(2030, 1, 1, tzinfo=UTC)
            )

            assert result.scanned == 0
            assert result.closed == 0
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_active_cancel_watchdog_multiple_cancelling_runs_closes_each_eligible(
    tmp_path: Path,
) -> None:
    """watchdog SQL scan 可处理多个 eligible CANCELLING Run。"""

    options = _command_options(tmp_path)
    active_registry = ActiveWorkerRegistry()
    host = create_host_command_handle(options, active_registry=active_registry)
    handles = (
        _CancelAwareHandle(local_worker_id="worker-multi-1", terminal="blocked"),
        _CancelAwareHandle(local_worker_id="worker-multi-2", terminal="blocked"),
    )
    worker_factory = _SequencedWorkerFactory(handles)
    try:
        first_session_id = _session_id(host)
        second_session_id = ensure_session(
            host,
            EnsureSessionRequest(
                scope="workspace",
                slot_key="slot-active-second",
                metadata=(),
            ),
        ).session_id
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                handles[0],
                worker_factory=worker_factory,
                active_registry=active_registry,
                lane_capacity=2,
                active_cancel_timeout_seconds=0.5,
            )
            try:
                first = start_run(
                    host, _start_request(first_session_id, "start-multi-1")
                )
                second = start_run(
                    host, _start_request(second_session_id, "start-multi-2")
                )
                first_refs = await _start_governed_refs(scheduler, first_session_id)
                second_refs = await _start_governed_refs(scheduler, second_session_id)
                scheduler.wake_dispatch(_pending_dispatch(first_refs))
                scheduler.wake_dispatch(_pending_dispatch(second_refs))
                await _wait_for_attempt_status(
                    options.db_path,
                    first_refs.attempt_id,
                    AttemptStatus.RUNNING,
                )
                await _wait_for_attempt_status(
                    options.db_path,
                    second_refs.attempt_id,
                    AttemptStatus.RUNNING,
                )

                cancel_run(host, first.run_id, _cancel_request("cancel-multi-1"))
                cancel_run(host, second.run_id, _cancel_request("cancel-multi-2"))
                result = scheduler.tick_active_cancel_watchdog(
                    datetime(2030, 1, 1, tzinfo=UTC)
                )

                assert result.scanned == 2
                assert result.closed == 2
                assert _run_status(options.db_path, first.run_id) == RunStatus.CANCELLED
                assert _run_status(options.db_path, second.run_id) == RunStatus.CANCELLED
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_active_cancel_timeout_promotes_queued_run(tmp_path: Path) -> None:
    """timeout closeout 释放 Session active slot 并 promotion queued Run。"""

    options = _command_options(tmp_path)
    active_registry = ActiveWorkerRegistry()
    host = create_host_command_handle(options, active_registry=active_registry)
    active_handle = _CancelAwareHandle(local_worker_id="worker-promote-active", terminal="blocked")
    queued_handle = _CancelAwareHandle(local_worker_id="worker-promote-queued", terminal="final")
    worker_factory = _SequencedWorkerFactory((active_handle, queued_handle))
    try:
        session_id = _session_id(host)
        active = start_run(host, _start_request(session_id, "start-promote-active"))
        queued = start_run(host, _start_request(session_id, "start-promote-queued"))
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                active_handle,
                worker_factory=worker_factory,
                active_registry=active_registry,
                lane_capacity=2,
                active_cancel_timeout_seconds=0.5,
            )
            try:
                refs = await _start_governed_refs(scheduler, session_id)
                scheduler.wake_dispatch(_pending_dispatch(refs))
                assert (await scheduler.drain_once()).dispatched == 1
                cancel_run(host, active.run_id, _cancel_request("cancel-promote"))

                result = scheduler.tick_active_cancel_watchdog(
                    datetime(2030, 1, 1, tzinfo=UTC)
                )

                assert result.closed == 1
                await _wait_for_run_status(
                    options.db_path,
                    queued.run_id,
                    RunStatus.SUCCEEDED,
                )
                assert _run_status(options.db_path, active.run_id) == RunStatus.CANCELLED
                assert worker_factory.created == 2
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_late_cancel_does_not_overwrite_terminal(tmp_path: Path) -> None:
    """terminal 已先提交时 late cancel 只返回当前终态。"""

    options = _command_options(tmp_path)
    host = create_host_command_handle(options)
    handle = _CancelAwareHandle(local_worker_id="worker-final", terminal="final")
    try:
        session_id = _session_id(host)
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(tmp_path, store, handle)
            try:
                start_run(host, _start_request(session_id, "start-final"))
                refs = await _start_governed_refs(scheduler, session_id)
                scheduler.wake_dispatch(_pending_dispatch(refs))
                drain = await scheduler.drain_once()
                assert drain.dispatched == 1
                await _wait_for_run_status(
                    options.db_path,
                    refs.run_id,
                    RunStatus.SUCCEEDED,
                )

                late = cancel_run(host, refs.run_id, _cancel_request("cancel-late"))

                assert late.status == RunStatus.SUCCEEDED
                assert _run_status(options.db_path, refs.run_id) == RunStatus.SUCCEEDED
                assert handle.cancel_reasons == []
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_worker_terminal_promotes_and_dispatches_queued_run(
    tmp_path: Path,
) -> None:
    """worker terminal 后 scheduler promotion queued Run 并处理新 dispatch。"""

    options = _command_options(tmp_path)
    host = create_host_command_handle(options)
    first_handle = _CancelAwareHandle(
        local_worker_id="worker-terminal-active",
        terminal="final",
    )
    promoted_handle = _CancelAwareHandle(
        local_worker_id="worker-terminal-promoted",
        terminal="final",
    )
    worker_factory = _SequencedWorkerFactory((first_handle, promoted_handle))
    try:
        session_id = _session_id(host)
        active = start_run(host, _start_request(session_id, "start-terminal-active"))
        queued = start_run(host, _start_request(session_id, "start-terminal-queued"))
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                first_handle,
                worker_factory=worker_factory,
                lane_timeout_seconds=0.5,
            )
            try:
                active_refs = await _start_governed_refs(scheduler, session_id)
                assert active_refs.run_id == active.run_id
                scheduler.wake_dispatch(_pending_dispatch(active_refs))
                drain = await scheduler.drain_once()
                assert drain.dispatched == 1

                await _wait_for_run_status(
                    options.db_path,
                    active_refs.run_id,
                    RunStatus.SUCCEEDED,
                )
                await _wait_for_run_status(
                    options.db_path,
                    queued.run_id,
                    RunStatus.SUCCEEDED,
                )

                assert worker_factory.created == 2
                assert _event_type_count(options.db_path, "ATTEMPT_RUNNING") == 2
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_cancel_session_replay_repropagates_active_without_new_facts(
    tmp_path: Path,
) -> None:
    """session cancel replay 不追加 facts，但可重放仍 active 的 worker cancel。"""

    options = _command_options(tmp_path)
    active_registry = ActiveWorkerRegistry()
    host = create_host_command_handle(options, active_registry=active_registry)
    handle = _CancelAwareHandle(local_worker_id="worker-session", terminal="hang")
    try:
        session_id = _session_id(host)
        request = _cancel_session_request("cancel-session")
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path, store, handle, active_registry=active_registry
            )
            try:
                start_run(host, _start_request(session_id, "start-session"))
                refs = await _start_governed_refs(scheduler, session_id)
                scheduler.wake_dispatch(_pending_dispatch(refs))
                drain = await scheduler.drain_once()
                assert drain.dispatched == 1

                first = cancel_session_runs(host, session_id, request)
                after_first_events = _event_count(options.db_path)
                replay = cancel_session_runs(host, session_id, request)

                assert first.active_run_id == refs.run_id
                assert replay.active_run_id == refs.run_id
                assert _run_status(options.db_path, refs.run_id) == (
                    RunStatus.CANCELLING
                )
                assert _event_count(options.db_path) == after_first_events
                assert handle.cancel_reasons == ["user_stop_all", "user_stop_all"]
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_cancel_session_replay_after_timeout_does_not_append_or_propagate(
    tmp_path: Path,
) -> None:
    """timeout terminal 后 session cancel replay 不追加 facts 或传播 cancel。"""

    options = _command_options(tmp_path)
    active_registry = ActiveWorkerRegistry()
    host = create_host_command_handle(options, active_registry=active_registry)
    handle = _CancelAwareHandle(local_worker_id="worker-replay-timeout", terminal="blocked")
    try:
        session_id = _session_id(host)
        request = _cancel_session_request("cancel-session-timeout")
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                handle,
                active_registry=active_registry,
                active_cancel_timeout_seconds=0.5,
            )
            try:
                start_run(host, _start_request(session_id, "start-session-timeout"))
                refs = await _start_governed_refs(scheduler, session_id)
                scheduler.wake_dispatch(_pending_dispatch(refs))
                assert (await scheduler.drain_once()).dispatched == 1
                cancel_session_runs(host, session_id, request)
                scheduler.tick_active_cancel_watchdog(
                    datetime(2030, 1, 1, tzinfo=UTC)
                )
                after_timeout_events = _event_count(options.db_path)

                replay = cancel_session_runs(host, session_id, request)

                assert replay.active_run_id is None
                assert _run_status(options.db_path, refs.run_id) == RunStatus.CANCELLED
                assert _event_count(options.db_path) == after_timeout_events
                assert handle.cancel_reasons == ["user_stop_all"]
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_scheduler_close_does_not_write_active_cancel_timeout_terminal(
    tmp_path: Path,
) -> None:
    """scheduler close 只停止本地 runtime，不写 timeout terminal facts。"""

    options = _command_options(tmp_path)
    active_registry = ActiveWorkerRegistry()
    host = create_host_command_handle(options, active_registry=active_registry)
    handle = _CancelAwareHandle(local_worker_id="worker-close", terminal="blocked")
    refs: _RunRefs | None = None
    try:
        session_id = _session_id(host)
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                handle,
                active_registry=active_registry,
                active_cancel_timeout_seconds=0.5,
            )
            start_run(host, _start_request(session_id, "start-close"))
            refs = await _start_governed_refs(scheduler, session_id)
            scheduler.wake_dispatch(_pending_dispatch(refs))
            assert (await scheduler.drain_once()).dispatched == 1
            cancel_run(host, refs.run_id, _cancel_request("cancel-close"))

            await scheduler.close()

        assert refs is not None
        assert _run_status(options.db_path, refs.run_id) == RunStatus.CANCELLING
        assert _attempt_status(options.db_path, refs.attempt_id) == AttemptStatus.RUNNING
        assert _event_type_count(options.db_path, "RUN_CANCELLED") == 0
    finally:
        host.close()


def _command_options(tmp_path: Path) -> HostCommandHandleOptions:
    """构造 public command handle options。

    :param tmp_path: pytest 临时目录。
    :returns: Host command handle options。
    """

    return HostCommandHandleOptions(
        host_handle_id="host-active-cancel",
        db_path=tmp_path / "host.sqlite3",
        artifact_root=tmp_path / "artifacts",
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=1.0,
        sqlite_write_busy_retry_count=8,
        sqlite_write_retry_initial_delay_seconds=0.001,
        sqlite_write_retry_backoff_multiplier=1.2,
        sqlite_write_retry_max_delay_seconds=0.02,
        payload_inline_threshold_bytes=4096,
        context_window_size=8192,
        reserved_output_tokens=1024,
    )


def _durable_options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=1.0,
            write_busy_retry_count=8,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.02,
        ),
    )


async def _open_scheduler(
    tmp_path: Path,
    store: HostDurableStore,
    handle: _CancelAwareHandle,
    *,
    worker_factory: LocalEngineWorkerFactory | None = None,
    lane_timeout_seconds: float | None = 0.01,
    active_registry: ActiveWorkerRegistry | None = None,
    lane_capacity: int = 1,
    active_cancel_timeout_seconds: float | None = 300.0,
) -> HostDispatchScheduler:
    """打开测试 scheduler。

    :param tmp_path: pytest 临时目录。
    :param store: durable store。
    :param handle: worker handle。
    :param worker_factory: 可选 worker factory；不传时使用单 handle factory。
    :param lane_timeout_seconds: lane acquire timeout 秒数。
    :param active_registry: 可选 active worker registry。
    :param lane_capacity: 测试 lane 容量。
    :param active_cancel_timeout_seconds: active cancel watchdog timeout 秒数。
    :returns: scheduler。
    """

    return await HostDispatchScheduler.open(
        transaction_runner=store.transaction_runner,
        local_execution=HostLocalExecutionOptions(
            lane_db_path=tmp_path / "lane.sqlite3",
            lane_name=_LANE_NAME,
            lane_capacity=lane_capacity,
            lane_default_timeout_seconds=lane_timeout_seconds,
            lane_claim_ttl_seconds=1.0,
            lane_heartbeat_interval_seconds=0.1,
            worker_startup_timeout_seconds=1.0,
            dispatch_poll_interval_seconds=0.01,
            runner_spec=_runner_spec(),
            runner_options=RunnerCallOptions(
                temperature=None, max_tokens=None, top_p=None, stream=False
            ),
            agent_policy=AgentPolicy(
                max_iterations=1,
                continuation_max_attempts=0,
                allow_tool_calls=False,
                tool_execution_timeout_seconds=1.0,
            ),
            worker_factory=(
                worker_factory
                if worker_factory is not None
                else _FakeWorkerFactory(handle)
            ),
            active_cancel_timeout_seconds=active_cancel_timeout_seconds,
        ),
        host_handle_id="host-active-cancel",
        active_registry=active_registry,
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


def _context() -> HostCallContext:
    """构造测试 call context。

    :returns: Host call context。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id="trace-active-cancel",
        authorization_claims=(AuthorizationClaim(name="role", value="research"),),
        operation_context=OperationContext(
            operation_name="active_cancel_dispatch",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase5",
            correlation_id="corr-active-cancel",
        ),
    )


def _start_request(session_id: str, client_request_id: str) -> StartRunRequest:
    """构造 start_run 请求。

    :param session_id: Session id。
    :param client_request_id: client request id。
    :returns: StartRunRequest。
    """

    return StartRunRequest(
        context=_context(),
        session_id=session_id,
        client_request_id=client_request_id,
        input=HostInput(display_text="hello", payload_ref=None, payload_digest=None),
        execution_target="target-active-cancel",
        queue_policy="queue",
    )


def _cancel_request(client_request_id: str) -> CancelRunRequest:
    """构造 cancel_run 请求。

    :param client_request_id: client request id。
    :returns: CancelRunRequest。
    """

    return CancelRunRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="user_stop",
        mode=CancelMode.GRACEFUL,
    )


def _cancel_session_request(client_request_id: str) -> CancelSessionRunsRequest:
    """构造 cancel_session_runs 请求。

    :param client_request_id: client request id。
    :returns: CancelSessionRunsRequest。
    """

    return CancelSessionRunsRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="user_stop_all",
        mode=CancelMode.GRACEFUL,
    )


def _session_id(host: HostCommandHandle) -> str:
    """创建测试 Session。

    :param host: Host command handle。
    :returns: Session id。
    """

    return ensure_session(
        host,
        EnsureSessionRequest(scope="workspace", slot_key="slot-active", metadata=()),
    ).session_id


def _refs(db_path: Path, run_id: str) -> _RunRefs:
    """读取 Run 对应的 durable refs。

    :param db_path: SQLite DB 路径。
    :param run_id: Run id。
    :returns: durable refs。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT r.session_id, r.current_attempt_id, a.execution_id,
                   d.dispatch_record_id
            FROM host_runs r
            JOIN host_attempts a ON a.attempt_id = r.current_attempt_id
            JOIN host_attempt_dispatch_records d ON d.attempt_id = a.attempt_id
            WHERE r.run_id = ?
            """,
            (run_id,),
        ).fetchone()
    assert row is not None
    return _RunRefs(
        session_id=str(row[0]),
        run_id=run_id,
        attempt_id=str(row[1]),
        execution_id=str(row[2]),
        dispatch_record_id=str(row[3]),
    )


async def _start_governed_refs(
    scheduler: HostDispatchScheduler, session_id: str
) -> _RunRefs:
    """执行一次 pre-start governance 并返回生成的 dispatch refs。

    :param scheduler: Host dispatch scheduler。
    :param session_id: 目标 Session id。
    :returns: 本次启动生成的 durable refs。
    :raises AssertionError: 没有可启动 Run 时抛出。
    """

    stage = await scheduler._run_pre_start_governance(session_id)
    assert stage.pending_dispatch is not None
    pending = stage.pending_dispatch
    return _RunRefs(
        session_id=session_id,
        run_id=pending.run_id,
        attempt_id=pending.attempt_id,
        execution_id=pending.execution_id,
        dispatch_record_id=pending.dispatch_record_id,
    )


def _pending_dispatch(refs: _RunRefs) -> PendingDispatchRecord:
    """构造 pending dispatch 摘要。

    :param refs: durable refs。
    :returns: PendingDispatchRecord。
    """

    return PendingDispatchRecord(
        dispatch_record_id=refs.dispatch_record_id,
        run_id=refs.run_id,
        attempt_id=refs.attempt_id,
        execution_id=refs.execution_id,
        execution_target="target-active-cancel",
        worker_kind=WorkerKind.LOCAL,
    )


def _mark_waiting_for_lane(
    transaction_runner: HostTransactionRunner, refs: _RunRefs
) -> None:
    """复用 scheduler 注册的 owner row 标记 waiting_for_lane。

    :param transaction_runner: transaction runner。
    :param refs: durable refs。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=refs.attempt_id,
            owner_host_instance_id="host-active-cancel",
            lane_name=_LANE_NAME,
            waiting_for_lane_at="2026-05-15T01:02:03.000000Z",
        )

    transaction_runner.run_write(_operation)


def _mark_dispatching(
    transaction_runner: HostTransactionRunner, refs: _RunRefs
) -> None:
    """复用 scheduler 注册的 owner row 标记 pre-accept dispatching。

    :param transaction_runner: transaction runner。
    :param refs: durable refs。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=refs.attempt_id,
            owner_host_instance_id="host-active-cancel",
            lane_name=_LANE_NAME,
            waiting_for_lane_at="2026-05-15T01:02:03.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id=refs.attempt_id,
            owner_host_instance_id="host-active-cancel",
            lane_name=_LANE_NAME,
            lane_claim_id="claim-active-cancel",
            lane_owner_id="owner-active-cancel",
            lane_acquired_at="2026-05-15T01:02:03.000000Z",
            dispatching_at="2026-05-15T01:02:03.000000Z",
        )

    transaction_runner.run_write(_operation)


def _run_status(db_path: Path, run_id: str) -> RunStatus:
    """读取 Run status。

    :param db_path: SQLite DB 路径。
    :param run_id: Run id。
    :returns: RunStatus。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT status FROM host_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    assert row is not None
    return RunStatus(str(row[0]))


def _attempt_status(db_path: Path, attempt_id: str) -> AttemptStatus:
    """读取 Attempt status。

    :param db_path: SQLite DB 路径。
    :param attempt_id: Attempt id。
    :returns: AttemptStatus。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT status FROM host_attempts WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
    assert row is not None
    return AttemptStatus(str(row[0]))


def _event_count(db_path: Path) -> int:
    """统计 EventLog 数量。

    :param db_path: SQLite DB 路径。
    :returns: EventLog row 数。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute("SELECT COUNT(*) FROM event_log").fetchone()
    assert row is not None
    return int(row[0])


def _event_type_count(db_path: Path, event_type: str) -> int:
    """统计指定 EventLog 类型数量。

    :param db_path: SQLite DB 路径。
    :param event_type: event type。
    :returns: 指定类型 row 数。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM event_log WHERE event_type = ?",
            (event_type,),
        ).fetchone()
    assert row is not None
    return int(row[0])


async def _wait_for_run_status(
    db_path: Path, run_id: str, status: RunStatus
) -> None:
    """等待 Run 到达指定状态。

    :param db_path: SQLite DB 路径。
    :param run_id: Run id。
    :param status: 期望状态。
    :returns: ``None``。
    :raises AssertionError: 超时未到达状态时抛出。
    """

    for _index in range(100):
        if _run_status(db_path, run_id) == status:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Run {run_id} did not reach {status}")


async def _wait_for_attempt_status(
    db_path: Path,
    attempt_id: str,
    status: AttemptStatus,
) -> None:
    """等待 Attempt 到达指定状态。

    :param db_path: SQLite DB 路径。
    :param attempt_id: Attempt id。
    :param status: 期望状态。
    :returns: ``None``。
    :raises AssertionError: 超时未到达状态时抛出。
    """

    for _index in range(100):
        if _attempt_status(db_path, attempt_id) == status:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Attempt {attempt_id} did not reach {status}")
