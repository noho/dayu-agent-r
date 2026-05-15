"""Host Phase 5 dispatch scheduler 测试。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import EngineEvent
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host.admission import PendingDispatchRecord
from dayu.host.api import (
    AttemptDispatchSnapshot,
    AttemptStatus,
    CancelMode,
    EnsureSessionRequest,
    HostLocalExecutionOptions,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
    RunStatus,
)
from dayu.host.dispatch import (
    ActiveCancelMessage,
    ActiveWorkerRegistry,
    HostDispatchScheduler,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import HostDurableStore, open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.run_transition import (
    CancelPredispatchStartingInput,
    CreateRunningRunInput,
    cancel_predispatch_starting_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    RunRow,
    RunStartReason,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_attempt_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.local_proxy import DefaultLocalEngineWorkerFactory
from dayu.runtime.lane import (
    LaneAcquired,
    LaneConfig,
    LaneController,
    SQLiteLaneCoordinatorConfig,
)

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "dispatch-test"})
_LANE_NAME = "llm"


@dataclass(frozen=True, slots=True)
class _SeededRun:
    """测试中创建的 running Run。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


class _FakeHandle:
    """测试用 worker handle。"""

    def __init__(self, local_worker_id: str = "local-worker-test") -> None:
        """初始化 fake handle。

        :param local_worker_id: 本地 worker id。
        :returns: ``None``。
        """

        self._local_worker_id = local_worker_id
        self.closed = False

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        """

        return self._local_worker_id

    async def events(self) -> AsyncIterator[EngineEvent]:
        """返回空事件流。

        :returns: 空异步迭代器。
        """

        if False:
            yield _unreachable_engine_event()

    def cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason

    async def close(self) -> None:
        """关闭 fake handle。

        :returns: ``None``。
        """

        self.closed = True


class _CrashingHandle(_FakeHandle):
    """事件流抛异常的 fake handle。"""

    async def events(self) -> AsyncIterator[EngineEvent]:
        """抛出 worker stream 异常。

        :returns: 不会正常返回事件。
        :raises RuntimeError: 始终模拟 worker stream crash。
        """

        raise RuntimeError("worker stream crashed")
        if False:
            yield _unreachable_engine_event()


class _CloseFailingHandle(_FakeHandle):
    """关闭时抛异常的 fake handle。"""

    async def events(self) -> AsyncIterator[EngineEvent]:
        """保持事件流未结束直到 scheduler close。

        :returns: 不会正常返回事件。
        """

        await asyncio.sleep(10.0)
        if False:
            yield _unreachable_engine_event()

    def cancel(self, reason: str) -> None:
        """模拟 handle cancel 异常。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises RuntimeError: 始终抛出取消异常。
        """

        del reason
        raise RuntimeError("cancel failed")

    async def close(self) -> None:
        """模拟 handle close 异常。

        :returns: ``None``。
        :raises RuntimeError: 始终抛出关闭异常。
        """

        raise RuntimeError("close failed")


class _CloseCountingHandle(_FakeHandle):
    """记录 cancel / close 次数且事件流长期挂起的 fake handle。"""

    def __init__(self) -> None:
        """初始化计数 handle。

        :returns: ``None``。
        """

        super().__init__()
        self.cancel_count = 0
        self.close_count = 0

    async def events(self) -> AsyncIterator[EngineEvent]:
        """保持事件流未结束直到 scheduler close。

        :returns: 不会正常返回事件。
        """

        await asyncio.sleep(10.0)
        if False:
            yield _unreachable_engine_event()

    def cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason
        self.cancel_count += 1

    async def close(self) -> None:
        """记录关闭次数。

        :returns: ``None``。
        """

        self.close_count += 1
        await super().close()


class _FlakyLocalWorkerIdHandle(_FakeHandle):
    """第二次读取 ``local_worker_id`` 时抛错的 fake handle。"""

    def __init__(self) -> None:
        """初始化 fake handle。

        :returns: ``None``。
        """

        super().__init__("local-worker-first-read")
        self.local_worker_id_reads = 0
        self.close_count = 0

    @property
    def local_worker_id(self) -> str:
        """第一次返回 worker id，后续模拟 pre-event envelope 构造失败。

        :returns: 本地 worker id。
        :raises RuntimeError: 第二次及后续读取时抛出。
        """

        self.local_worker_id_reads += 1
        if self.local_worker_id_reads == 1:
            return "local-worker-first-read"
        raise RuntimeError("local worker id unavailable")

    async def events(self) -> AsyncIterator[EngineEvent]:
        """该测试路径不应进入事件流。

        :returns: 不会正常返回事件。
        :raises AssertionError: 若被调用则抛出。
        """

        raise AssertionError("events must not be consumed")
        if False:
            yield _unreachable_engine_event()

    async def close(self) -> None:
        """记录关闭次数。

        :returns: ``None``。
        """

        self.close_count += 1
        await super().close()


class _AcceptingWorker:
    """测试用立即 accept worker。"""

    def __init__(self, factory: "_FakeWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """接受 worker 请求。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: fake handle。
        """

        self._factory.accepted_snapshots.append(snapshot)
        self._factory.accepted_requests.append(request)
        return _FakeHandle()


class _HandleWorker:
    """返回指定 handle 的 fake worker。"""

    def __init__(self, handle: LocalWorkerHandle) -> None:
        """初始化 worker。

        :param handle: accept 返回的 handle。
        :returns: ``None``。
        """

        self._handle = handle

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """返回预置 handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 预置 handle。
        """

        del snapshot, request
        return self._handle


class _FailingAcceptWorker:
    """accept 时抛异常的 fake worker。"""

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """模拟非 timeout accept 异常。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出 accept 异常。
        """

        del snapshot, request
        raise RuntimeError("accept failed")


class _SlowWorker:
    """测试用超时 worker。"""

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """阻塞直到 scheduler startup timeout。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 不会返回的 fake handle。
        """

        del snapshot, request
        await asyncio.sleep(1.0)
        return _FakeHandle()


class _FakeWorkerFactory:
    """测试用 worker factory。"""

    def __init__(
        self, *, slow: bool = False, worker: LocalEngineWorker | None = None
    ) -> None:
        """初始化 factory。

        :param slow: 是否返回超时 worker。
        :param worker: 指定 worker；不传时按 ``slow`` 构造。
        :returns: ``None``。
        """

        self.created = 0
        self.accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self.accepted_requests: list[AgentRunRequest] = []
        self._slow = slow
        self._worker = worker

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 fake worker。

        :param snapshot: dispatch snapshot。
        :returns: fake worker。
        """

        del snapshot
        self.created += 1
        if self._worker is not None:
            return self._worker
        if self._slow:
            return _SlowWorker()
        return _AcceptingWorker(self)


class _EnqueueOnSecondEmptyQueue(asyncio.Queue[PendingDispatchRecord]):
    """在第二次 empty 检查后注入一条 dispatch，用于复现 wakeup 窗口。"""

    def __init__(self, injected_record: PendingDispatchRecord) -> None:
        """初始化测试队列。

        :param injected_record: 第二次 empty 检查时注入的 dispatch 摘要。
        :returns: ``None``。
        """

        super().__init__()
        self._injected_record = injected_record
        self._empty_calls = 0

    def empty(self) -> bool:
        """第二次 empty 仍返回 True，但在返回前模拟并发入队。

        :returns: 当前测试队列是否报告为空。
        """

        self._empty_calls += 1
        if self._empty_calls == 2:
            self.put_nowait(self._injected_record)
            return True
        return super().empty()


@pytest.mark.asyncio
async def test_pending_waiting_dispatching_worker_accept_marks_running(
    tmp_path: Path,
) -> None:
    """pending dispatch 可推进到 worker accepted，Attempt 进入 RUNNING。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(
                store.transaction_runner, seeded
            )
            event = _read_event_by_type(
                store.transaction_runner, "ATTEMPT_RUNNING"
            )
            assert result.processed == 1
            assert result.dispatched == 1
            assert run.status == RunStatus.RUNNING
            assert attempt.status == AttemptStatus.RUNNING
            assert dispatch_record.status == DispatchRecordStatus.DISPATCHING
            assert dispatch_record.worker_accept_event_id == event.event_id
            payload = json.loads(event.payload_json)
            assert payload["local_worker_id"] == "local-worker-test"
            assert payload["worker_accepted_at"] == dispatch_record.worker_accepted_at
            assert payload["lane_name"] == _LANE_NAME
            assert payload["lane_claim_id"] == dispatch_record.lane_claim_id
            assert (
                factory.accepted_snapshots[0].dispatch_record_id
                == seeded.dispatch_record_id
            )
            assert factory.accepted_requests[0].disable_tools is True
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_drain_loop_continues_when_dispatch_arrives_during_empty_window(
    tmp_path: Path,
) -> None:
    """empty / sleep / return 窗口内入队的 dispatch 不应被遗留在队列中。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        scheduler._queue = _EnqueueOnSecondEmptyQueue(_pending_dispatch(seeded))
        scheduler._drain_task = asyncio.create_task(scheduler._drain_loop())
        try:
            for _ in range(50):
                if factory.created == 1:
                    break
                await asyncio.sleep(0.01)
            assert factory.created == 1
            assert scheduler._queue.empty() is True
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_cancelled_dispatch_is_skipped_before_worker_call(
    tmp_path: Path,
) -> None:
    """worker accept 前被 direct cancel 的 dispatch 不会调用 worker。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        try:
            _mark_dispatching_and_cancel(store.transaction_runner, seeded)
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            assert result.processed == 1
            assert result.skipped == 1
            assert factory.created == 0
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_pending_dispatch_can_direct_mark_dispatching_after_lane_recheck(
    tmp_path: Path,
) -> None:
    """scheduler durable recheck 接受 pending 并直跳 dispatching。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        claim = await scheduler._lane_controller.acquire(
            _LANE_NAME,
            timeout_seconds=0,
        )
        assert isinstance(claim, LaneAcquired)
        try:
            dispatch_record = scheduler._mark_dispatching_after_recheck(
                _pending_dispatch(seeded),
                claim.token,
            )

            assert dispatch_record is not None
            assert dispatch_record.status == DispatchRecordStatus.DISPATCHING
            assert dispatch_record.waiting_for_lane_at is not None
            assert dispatch_record.lane_name == _LANE_NAME
            assert dispatch_record.lane_claim_id == claim.token.claim_id
        finally:
            await claim.token.release()
            await scheduler.close()


@pytest.mark.asyncio
async def test_worker_startup_timeout_closes_starting_attempt_failed(
    tmp_path: Path,
) -> None:
    """worker accept timeout 会把 STARTING Attempt 和 Run 关闭为 FAILED。"""

    factory = _FakeWorkerFactory(slow=True)
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            worker_startup_timeout_seconds=0.001,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(
                store.transaction_runner, seeded
            )
            event = _read_event_by_type(store.transaction_runner, "RUN_FAILED")
            assert result.timed_out == 1
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            assert dispatch_record.status == DispatchRecordStatus.CANCELLED
            assert json.loads(_require_text(event.reason_json))["reason"] == (
                "worker_startup_timeout"
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_worker_accept_exception_closes_failed_and_cancels_dispatch(
    tmp_path: Path,
) -> None:
    """worker accept 非 timeout 异常按 startup failure 收口并取消 dispatch row。"""

    factory = _FakeWorkerFactory(worker=_FailingAcceptWorker())
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(
                store.transaction_runner, seeded
            )
            assert result.timed_out == 1
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            assert dispatch_record.status == DispatchRecordStatus.CANCELLED
            assert dispatch_record.cancelled_event_id is not None
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_worker_startup_closeout_error_still_releases_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """startup closeout 抛错时仍释放 lane token。"""

    factory = _FakeWorkerFactory(worker=_FailingAcceptWorker())
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)

        def raise_closeout(record: PendingDispatchRecord) -> None:
            """模拟 durable closeout 失败。

            :param record: pending dispatch record。
            :returns: ``None``。
            :raises RuntimeError: 始终抛出 closeout 失败。
            """

            del record
            raise RuntimeError("closeout failed")

        monkeypatch.setattr(
            scheduler,
            "_closeout_worker_startup_timeout",
            raise_closeout,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            with pytest.raises(RuntimeError, match="closeout failed"):
                await scheduler.drain_once()

            claim = await scheduler._lane_controller.acquire(
                _LANE_NAME,
                timeout_seconds=0,
            )
            assert isinstance(claim, LaneAcquired)
            await claim.token.release()
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_lane_acquire_timeout_closes_starting_attempt_failed(
    tmp_path: Path,
) -> None:
    """lane acquire timeout 会把 worker accept 前 Attempt 与 Run 关闭为 FAILED。"""

    factory = _FakeWorkerFactory()
    lane_db_path = tmp_path / "lane.sqlite3"
    lane_holder = await LaneController.open(
        [
            LaneConfig(
                name=_LANE_NAME,
                capacity=1,
                default_timeout_seconds=0.001,
                claim_ttl_seconds=1.0,
                heartbeat_interval_seconds=0.1,
            )
        ],
        coordinator=SQLiteLaneCoordinatorConfig(db_path=lane_db_path),
    )
    claim = await lane_holder.acquire(_LANE_NAME, timeout_seconds=0)
    assert isinstance(claim, LaneAcquired)
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            lane_db_path=lane_db_path,
            lane_default_timeout_seconds=0.001,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()

            run, attempt, dispatch_record = _read_rows(
                store.transaction_runner, seeded
            )
            event = _read_event_by_type(store.transaction_runner, "RUN_FAILED")
            assert result.timed_out == 1
            assert result.dispatched == 0
            assert factory.created == 0
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            assert dispatch_record.status == DispatchRecordStatus.CANCELLED
            assert json.loads(_require_text(event.reason_json))["reason"] == (
                "worker_startup_timeout"
            )
        finally:
            await scheduler.close()
            await claim.token.release()
            await lane_holder.close()


@pytest.mark.asyncio
async def test_worker_clean_eof_closes_run_failed_from_scheduler(
    tmp_path: Path,
) -> None:
    """accepted worker clean EOF 由 scheduler 映射为 FAILED closeout。"""

    factory = _FakeWorkerFactory()
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            run, attempt, _dispatch_record = await _wait_for_statuses(
                store.transaction_runner,
                seeded,
                expected_run=RunStatus.FAILED,
                expected_attempt=AttemptStatus.FAILED,
            )

            assert result.dispatched == 1
            assert run.status == RunStatus.FAILED
            assert attempt.status == AttemptStatus.FAILED
            event = _read_event_by_type(store.transaction_runner, "RUN_FAILED")
            assert json.loads(_require_text(event.reason_json))["reason"] == (
                "stream_ended_without_terminal"
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_worker_stream_exception_closes_run_lost_from_scheduler(
    tmp_path: Path,
) -> None:
    """accepted worker stream 异常由 scheduler 映射为 LOST closeout。"""

    factory = _FakeWorkerFactory(worker=_HandleWorker(_CrashingHandle()))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            run, attempt, _dispatch_record = await _wait_for_statuses(
                store.transaction_runner,
                seeded,
                expected_run=RunStatus.LOST,
                expected_attempt=AttemptStatus.LOST,
            )

            assert result.dispatched == 1
            assert run.status == RunStatus.LOST
            assert attempt.status == AttemptStatus.LOST
            event = _read_event_by_type(store.transaction_runner, "RUN_LOST")
            assert json.loads(_require_text(event.reason_json))["reason"] == (
                "worker_lost_before_terminal"
            )
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_close_suppresses_handle_close_exception(
    tmp_path: Path,
) -> None:
    """scheduler close 不被 active handle cancel/close 异常打断。"""

    factory = _FakeWorkerFactory(worker=_HandleWorker(_CloseFailingHandle()))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        scheduler.wake_dispatch(_pending_dispatch(seeded))
        result = await scheduler.drain_once()

        assert result.dispatched == 1
        await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_close_lets_active_task_own_handle_close(
    tmp_path: Path,
) -> None:
    """scheduler close 只发 cancel，handle close 由 active task finally 执行一次。"""

    handle = _CloseCountingHandle()
    factory = _FakeWorkerFactory(worker=_HandleWorker(handle))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(tmp_path, store, factory)
        scheduler.wake_dispatch(_pending_dispatch(seeded))
        result = await scheduler.drain_once()

        assert result.dispatched == 1
        await scheduler.close()
        assert handle.cancel_count == 1
        assert handle.close_count == 1


@pytest.mark.asyncio
async def test_consume_pre_event_exception_releases_lane_and_unregisters(
    tmp_path: Path,
) -> None:
    """consume task 在 pre-event 构造失败时仍释放 lane 并注销 active worker。"""

    handle = _FlakyLocalWorkerIdHandle()
    registry = ActiveWorkerRegistry()
    factory = _FakeWorkerFactory(worker=_HandleWorker(handle))
    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            factory,
            active_registry=registry,
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            await _wait_for_active_tasks_to_finish(scheduler)

            assert result.dispatched == 1
            assert handle.close_count == 1
            assert registry.cancel(
                ActiveCancelMessage(
                    run_id=seeded.run_id,
                    attempt_id=seeded.attempt_id,
                    execution_id=seeded.execution_id,
                    reason="test_cancel_after_failure",
                )
            ) is False
            claim = await scheduler._lane_controller.acquire(
                _LANE_NAME,
                timeout_seconds=0,
            )
            assert isinstance(claim, LaneAcquired)
            await claim.token.release()
        finally:
            await scheduler.close()


@pytest.mark.asyncio
async def test_scheduler_with_default_local_proxy_stream_error_closes_lost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 DefaultLocalProxy 的 Engine stream 异常经 scheduler 映射为 LOST。"""

    async def raising_run_agent_messages(
        request: AgentRunRequest,
    ) -> AsyncIterator[EngineEvent]:
        """模拟 Engine public entry 在 stream 迭代时抛错。

        :param request: Engine request。
        :returns: 不会正常返回事件。
        :raises RuntimeError: 始终抛出 stream 异常。
        """

        del request
        raise RuntimeError("engine stream failed")
        if False:
            yield _unreachable_engine_event()

    monkeypatch.setattr(
        "dayu.host.local_proxy.run_agent_messages",
        raising_run_agent_messages,
    )

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_current_run(store)
        scheduler = await _open_scheduler(
            tmp_path,
            store,
            DefaultLocalEngineWorkerFactory(),
        )
        try:
            scheduler.wake_dispatch(_pending_dispatch(seeded))
            result = await scheduler.drain_once()
            run, attempt, _dispatch_record = await _wait_for_statuses(
                store.transaction_runner,
                seeded,
                expected_run=RunStatus.LOST,
                expected_attempt=AttemptStatus.LOST,
            )

            assert result.dispatched == 1
            assert run.status == RunStatus.LOST
            assert attempt.status == AttemptStatus.LOST
            event = _read_event_by_type(store.transaction_runner, "RUN_LOST")
            assert json.loads(_require_text(event.reason_json))["reason"] == (
                "worker_lost_before_terminal"
            )
        finally:
            await scheduler.close()


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造 Host durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


async def _open_scheduler(
    tmp_path: Path,
    store: HostDurableStore,
    factory: LocalEngineWorkerFactory,
    *,
    worker_startup_timeout_seconds: float = 1.0,
    lane_db_path: Path | None = None,
    lane_default_timeout_seconds: float = 0.01,
    active_registry: ActiveWorkerRegistry | None = None,
) -> HostDispatchScheduler:
    """打开测试 scheduler。

    :param tmp_path: pytest 临时目录。
    :param store: durable store。
    :param factory: worker factory。
    :param worker_startup_timeout_seconds: worker startup timeout。
    :param lane_db_path: runtime lane DB 路径。
    :param lane_default_timeout_seconds: lane acquire 默认 timeout。
    :param active_registry: active worker registry。
    :returns: scheduler。
    """

    return await HostDispatchScheduler.open(
        transaction_runner=store.transaction_runner,
        local_execution=HostLocalExecutionOptions(
            lane_db_path=lane_db_path if lane_db_path is not None else tmp_path / "lane.sqlite3",
            lane_name=_LANE_NAME,
            lane_capacity=1,
            lane_default_timeout_seconds=lane_default_timeout_seconds,
            lane_claim_ttl_seconds=1.0,
            lane_heartbeat_interval_seconds=0.1,
            worker_startup_timeout_seconds=worker_startup_timeout_seconds,
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
            worker_factory=factory,
        ),
        host_handle_id="host-test",
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
        supports_tool_calling=False,
        supports_streaming=False,
        supports_stream_usage=False,
        default_timeout_seconds=1.0,
        max_retries=0,
        provider_request=None,
    )


def _seed_current_run(store: HostDurableStore) -> _SeededRun:
    """创建 running Run、STARTING Attempt 和 pending dispatch。

    :param store: durable store。
    :returns: seeded run 摘要。
    """

    session_id = _ensure_session_id(store.transaction_runner)
    seeded = _SeededRun(
        session_id=session_id,
        run_id="run-dispatch",
        attempt_id="attempt-dispatch",
        execution_id="execution-dispatch",
        dispatch_record_id="dispatch-dispatch",
    )
    _append_user_input(
        store.transaction_runner,
        session_id=session_id,
        run_id=seeded.run_id,
        event_id="event-input-dispatch",
    )

    def _operation(transaction: HostTransaction) -> None:
        create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            CreateRunningRunInput(
                session_id=session_id,
                run_id=seeded.run_id,
                client_request_id="client-dispatch",
                input_event_id="event-input-dispatch",
                input_event_sequence=2,
                run_accepted_event_id="event-run-accepted-dispatch",
                run_started_event_id="event-run-started-dispatch",
                attempt_started_event_id="event-attempt-started-dispatch",
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                dispatch_record_id=seeded.dispatch_record_id,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                idempotency_key="idem-dispatch",
                execution_target="target-dispatch",
                queue_policy="queue",
                start_reason=RunStartReason.INITIAL,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )

    store.transaction_runner.run_write(_operation)
    return seeded


def _ensure_session_id(transaction_runner: HostTransactionRunner) -> str:
    """确保测试 Session 存在。

    :param transaction_runner: transaction runner。
    :returns: session id。
    """

    return ensure_session(
        transaction_runner,
        EnsureSessionRequest(scope="workspace", slot_key="slot", metadata=()),
    ).snapshot.session_id


def _append_user_input(
    transaction_runner: HostTransactionRunner,
    *,
    session_id: str,
    run_id: str,
    event_id: str,
) -> None:
    """追加 USER_INPUT_ACCEPTED。

    :param transaction_runner: transaction runner。
    :param session_id: Session id。
    :param run_id: Run id。
    :param event_id: event id。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id=event_id,
                event_class=EventClass.CANONICAL_FACT,
                session_id=session_id,
                run_id=run_id,
                attempt_id=None,
                execution_id=None,
                event_type="USER_INPUT_ACCEPTED",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id="client-dispatch",
                idempotency_key="idem-input",
                policy_decision=None,
                reason=None,
                payload_json={
                    "display_text": "dispatch prompt",
                    "operation_kind": "unit_test",
                    "execution_target": "target-dispatch",
                },
                payload_ref=None,
                payload_digest=None,
            ),
        )

    transaction_runner.run_write(_operation)


def _pending_dispatch(seeded: _SeededRun) -> PendingDispatchRecord:
    """构造 pending dispatch wakeup 摘要。

    :param seeded: seeded run。
    :returns: pending dispatch record。
    """

    return PendingDispatchRecord(
        dispatch_record_id=seeded.dispatch_record_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
        execution_target="target-dispatch",
        worker_kind=WorkerKind.LOCAL,
    )


def _read_rows(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> tuple[RunRow, AttemptRow, DispatchRecordRow]:
    """读取 Run、Attempt 与 dispatch row。

    :param transaction_runner: transaction runner。
    :param seeded: seeded run。
    :returns: 三个 durable row。
    """

    def _operation(
        transaction: HostTransaction,
    ) -> tuple[RunRow, AttemptRow, DispatchRecordRow]:
        run = read_run_by_id(transaction, seeded.run_id)
        attempt = read_attempt_by_id(transaction, seeded.attempt_id)
        dispatch_record = read_dispatch_record_by_attempt_id(
            transaction, seeded.attempt_id
        )
        assert run is not None
        assert attempt is not None
        assert dispatch_record is not None
        return run, attempt, dispatch_record

    return transaction_runner.run_read(_operation)


async def _wait_for_statuses(
    transaction_runner: HostTransactionRunner,
    seeded: _SeededRun,
    *,
    expected_run: RunStatus,
    expected_attempt: AttemptStatus,
) -> tuple[RunRow, AttemptRow, DispatchRecordRow]:
    """等待异步 worker consume task 写入目标 Run / Attempt 状态。

    :param transaction_runner: transaction runner。
    :param seeded: seeded run。
    :param expected_run: 期望 Run 状态。
    :param expected_attempt: 期望 Attempt 状态。
    :returns: 目标状态下的 durable rows。
    :raises AssertionError: 超时未达到目标状态时抛出。
    """

    for _index in range(100):
        rows = _read_rows(transaction_runner, seeded)
        run, attempt, _dispatch_record = rows
        if run.status == expected_run and attempt.status == expected_attempt:
            return rows
        await asyncio.sleep(0.01)
    run, attempt, _dispatch_record = _read_rows(transaction_runner, seeded)
    raise AssertionError(
        "status did not converge: "
        f"run={run.status.value} attempt={attempt.status.value}"
    )


async def _wait_for_active_tasks_to_finish(
    scheduler: HostDispatchScheduler,
) -> None:
    """等待 scheduler active consume tasks 全部结束。

    :param scheduler: 目标 scheduler。
    :returns: ``None``。
    :raises AssertionError: 超时仍有 active task 时抛出。
    """

    for _index in range(100):
        if not scheduler._active_tasks:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("active tasks did not finish")


def _read_event_by_type(
    transaction_runner: HostTransactionRunner, event_type: str
) -> EventLogRow:
    """按事件类型读取单条事件。

    :param transaction_runner: transaction runner。
    :param event_type: 事件类型。
    :returns: event row。
    """

    def _operation(transaction: HostTransaction) -> EventLogRow:
        rows = EventLogStore().read_events_after(transaction, 0, limit=100)
        for row in rows:
            if row.event_type == event_type:
                return row
        raise AssertionError(f"missing event type {event_type}")

    return transaction_runner.run_read(_operation)


def _mark_dispatching_and_cancel(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> None:
    """把 dispatch 推进到 pre-accept dispatching 后 direct cancel。

    :param transaction_runner: transaction runner。
    :param seeded: seeded run。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-test",
            lane_name=_LANE_NAME,
            waiting_for_lane_at="2026-05-15T01:02:03.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-test",
            lane_name=_LANE_NAME,
            lane_claim_id="claim-before-cancel",
            lane_owner_id="owner-before-cancel",
            lane_acquired_at="2026-05-15T01:02:03.000000Z",
            dispatching_at="2026-05-15T01:02:03.000000Z",
        )
        cancel_predispatch_starting_in_transaction(
            transaction,
            EventLogStore(),
            CancelPredispatchStartingInput(
                run_id=seeded.run_id,
                cancel_request_event_id="event-cancel-requested",
                attempt_cancelled_event_id="event-attempt-cancelled",
                run_cancelled_event_id="event-run-cancelled",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id="client-cancel",
                idempotency_key="idem-cancel",
                reason="user_stop",
                mode=CancelMode.GRACEFUL,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )

    transaction_runner.run_write(_operation)


def _unreachable_engine_event() -> EngineEvent:
    """构造不可达 EngineEvent 占位。

    :returns: 当前函数不会被执行。
    :raises AssertionError: 若测试错误执行到该分支则抛出。
    """

    raise AssertionError("unreachable")


def _require_text(value: str | None) -> str:
    """断言可选文本非空。

    :param value: 可选文本。
    :returns: 非空文本。
    :raises AssertionError: 文本缺失时抛出。
    """

    assert value is not None
    return value
