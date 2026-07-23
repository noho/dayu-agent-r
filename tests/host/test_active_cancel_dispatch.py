"""Host Phase 5 active cancel 与 dispatch cancel 集成测试。"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar, cast

import pytest

import dayu.host.admission as host_admission
from dayu.contracts.json_value import JsonValue
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
from dayu.host._durable_actor import open_durable_actor
from dayu.host.admission import AdmissionWakeupPort, PendingDispatchRecord
from dayu.host.api import (
    HostInput,
    AttemptDispatchSnapshot,
    AttemptStatus,
    EnsureSessionRequest,
    HostApiError,
    HostApiErrorCode,
    HostCommandHandleOptions,
    HostLocalExecutionOptions,
    OrdinaryRunExecutionBaseline,
    StartRunRequest,
)
from dayu.host.command import HostCommandHandle, start_run
from dayu.host.dispatch import (
    ActiveCancelMessage,
    ActiveWorkerRegistry,
    HostDispatchScheduler,
    OwnedSessionReconciliationResult,
    _HostCancellationToken,
)
from dayu.host.open_host import _ThreadsafeActiveWorkerCancelPort
from dayu.host.durable.connection import HostDurableStore, open_host_durable_store
from dayu.host.durable.event_log import EventClass, EventLogAppendRequest, EventLogStore
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.run_transition import (
    CancelActiveAttemptInput,
    RunTransitionResult,
)
from dayu.host.durable.schema import TABLE_HOST_ATTEMPT_DISPATCH_RECORDS
from dayu.host.durable.state import (
    AttemptExecutionIdentity,
    DispatchRecordRow,
    DispatchRecordStatus,
    StateMutationStatus,
    WorkerKind,
    is_dispatch_record_direct_cancelable,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatch_worker_accepted_row,
    mark_dispatching_after_lane_row,
)
from dayu.host.durable.transaction import (
    HostReadTransactionOperation,
    HostTransaction,
    HostTransactionOperation,
    HostTransactionRunner,
)
from dayu.host.terminal_post_commit import (
    TerminalPostCommitNotice,
    TerminalPostCommitPort,
)
from tests.host.transient_delta_support import NOOP_TRANSIENT_DELTA_PUBLISHER
from tests.host.fake_session_access import ExplicitFakeSessionAccess
from dayu.host.memory import default_memory_projection_policy
from tests.host.execution_handle_support import create_execution_command_handle

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_LANE_NAME = "llm"
T = TypeVar("T")


def _reject_transaction_read(
    transaction_runner: HostTransactionRunner,
    operation: HostReadTransactionOperation[T],
) -> T:
    """拒绝测试目标路径进入 durable read。

    :param transaction_runner: 被替换的 transaction runner。
    :param operation: 不应执行的 read operation。
    :returns: 本 helper 不返回。
    :raises AssertionError: 一旦发生 durable read 即抛出。
    """

    del transaction_runner, operation
    raise AssertionError("empty owner reconcile must not open a read")


class _PromotingTerminalPort(TerminalPostCommitPort):
    """模拟 coordinator 完成 notice 后 ordinary promotion 的测试端口。"""

    def __init__(self, promotion_port: AdmissionWakeupPort) -> None:
        """保存 scheduler ordinary promotion capability。

        :param promotion_port: scheduler promotion capability。
        :returns: ``None``。
        """

        self._promotion_port = promotion_port

    def notify_terminal_post_commit(
        self,
        notice: TerminalPostCommitNotice,
    ) -> None:
        """消费 exact terminal notice，并按 flag 唤醒 ordinary promotion。

        :param notice: 已提交的通知。
        :returns: ``None``。
        """

        if notice.wake_queue_promotion:
            self._promotion_port.wake_queue_promotion(notice.session_id)


class _TerminalPortFactory:
    """为测试 scheduler 显式创建最终 terminal port。"""

    def create_terminal_post_commit_port(
        self,
        *,
        promotion_port: AdmissionWakeupPort,
    ) -> TerminalPostCommitPort:
        """返回显式 discard 端点。

        :param promotion_port: scheduler ordinary promotion capability。
        :returns: discard terminal port。
        """

        return _PromotingTerminalPort(promotion_port)

    async def close_after_failed_scheduler_open(self) -> None:
        """确认当前 factory 没有独立待清理资源。

        :returns: ``None``。
        """

        return None


class _BlockingOwnedSessionReconciliation:
    """用 barrier 阻塞 attachment-authorized Session reconciliation。"""

    def __init__(self) -> None:
        """初始化进入、放行与取消信号。

        :returns: ``None``。
        """

        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def run(
        self,
        *,
        fixed_now: datetime,
    ) -> OwnedSessionReconciliationResult:
        """阻塞 Session reconciliation 直到测试放行或 scheduler close。

        :param fixed_now: production loop 传入的本轮固定时间。
        :returns: 放行后的空 reconciliation 摘要。
        :raises asyncio.CancelledError: scheduler close 取消 task 时透传。
        """

        del fixed_now
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return OwnedSessionReconciliationResult(
            owned_session_count=0,
            leased_session_count=0,
            dispatched_session_count=0,
            skipped_session_count=0,
        )


@dataclass(frozen=True, slots=True)
class _RunRefs:
    """测试 Run 的 durable 引用。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


@pytest.mark.asyncio
async def test_active_cancel_bridge_runs_worker_hook_on_opener_loop_thread(
    tmp_path: Path,
) -> None:
    """actor thread 发起 cancel 时 token/hook/asyncio primitive 回到 opener loop。"""

    opener_thread_id = threading.get_ident()
    actor_thread_ids: list[int] = []
    registry = ActiveWorkerRegistry()
    handle = _CancelAwareHandle(
        local_worker_id="bridge-worker",
        terminal="hang",
    )
    token = _HostCancellationToken()
    registry.register(
        session_id="session-bridge",
        run_id="run-bridge",
        attempt_id="attempt-bridge",
        execution_id="execution-bridge",
        handle=handle,
        cancellation_token=token,
    )
    assert registry.snapshot_identities() == (
        AttemptExecutionIdentity(
            session_id="session-bridge",
            run_id="run-bridge",
            attempt_id="attempt-bridge",
            execution_id="execution-bridge",
        ),
    )
    assert (
        registry.cancel(
            ActiveCancelMessage(
                session_id="session-wrong",
                run_id="run-bridge",
                attempt_id="attempt-bridge",
                execution_id="execution-bridge",
                reason="must-not-propagate",
            )
        )
        is False
    )
    assert token.is_cancelled() is False
    port = _ThreadsafeActiveWorkerCancelPort(
        loop=asyncio.get_running_loop(),
        active_registry=registry,
    )

    actor = await open_durable_actor(
        lambda: _create_execution_handle(_command_options(tmp_path)),
        thread_name_prefix="test-active-cancel-bridge",
    )

    def cancel_from_actor(_command_handle: HostCommandHandle) -> bool:
        """从真实 durable actor worker thread 调用 opener-loop bridge。

        :param _command_handle: actor 私有 command handle。
        :returns: active registry 是否命中目标。
        :raises Exception: bridge 或 registry cancel 失败时透传。
        """

        actor_thread_ids.append(threading.get_ident())
        return port.cancel(
            ActiveCancelMessage(
                session_id="session-bridge",
                run_id="run-bridge",
                attempt_id="attempt-bridge",
                execution_id="execution-bridge",
                reason="bridge-test",
            )
        )

    try:
        found = await actor.call(cancel_from_actor)
    finally:
        await actor.close()

    assert actor_thread_ids != [opener_thread_id]
    assert found is True
    assert token.cancel_reason() == "bridge-test"
    assert handle.cancel_reasons == ["bridge-test"]
    assert handle.cancel_thread_ids == [opener_thread_id]
    assert handle._cancelled.is_set()


@pytest.mark.asyncio
async def test_owner_cancel_reconcile_empty_snapshot_skips_durable_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空 local registry 直接返回，不用无意义事务争抢调度窗口。"""

    handle = _CancelAwareHandle(
        local_worker_id="worker-empty-owner-reconcile",
        terminal="hang",
    )
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        scheduler = await _open_scheduler(tmp_path, store, handle)
        try:
            monkeypatch.setattr(
                HostTransactionRunner,
                "run_read",
                _reject_transaction_read,
            )
            result = scheduler.reconcile_active_worker_cancels_once(
                fixed_now=_NOW,
            )
            assert result.snapshot_count == 0
            assert result.target_count == 0
            assert result.propagated_count == 0
            assert result.closed_count == 0
        finally:
            monkeypatch.undo()
            await scheduler.close()


@pytest.mark.asyncio
async def test_owner_cancel_periodic_task_progresses_while_session_reconcile_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Session reconcile 阻塞时独立 owner poll 仍传播并被 close 收口。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: owner poll 被阻塞或 close 泄漏 task 时抛出。
    """

    options = _command_options(tmp_path)
    owner_registry = ActiveWorkerRegistry()
    owner_host = _create_execution_handle(
        options,
        active_registry=owner_registry,
    )
    caller_host = _create_execution_handle(options)
    handle = _CancelAwareHandle(
        local_worker_id="worker-independent-owner-cancel",
        terminal="blocked",
    )
    blocker = _BlockingOwnedSessionReconciliation()
    monkeypatch.setattr(
        HostDispatchScheduler,
        "reconcile_owned_sessions_once",
        blocker.run,
    )
    try:
        session_id = _session_id(owner_host)
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                handle,
                active_registry=owner_registry,
            )
            try:
                start_run(
                    owner_host,
                    _start_request(session_id, "start-independent-owner-cancel"),
                )
                refs = await _start_governed_refs(scheduler, session_id)
                scheduler.wake_dispatch(_pending_dispatch(refs))
                assert (await scheduler.drain_once()).dispatched == 1
                await asyncio.wait_for(blocker.started.wait(), timeout=1.0)

                session_task = scheduler._owned_session_reconciliation_task
                owner_cancel_task = (
                    scheduler._active_worker_cancel_reconciliation_task
                )
                assert session_task is not None
                assert owner_cancel_task is not None
                assert session_task.done() is False
                assert owner_cancel_task.done() is False

                cancelling = cancel_run(
                    caller_host,
                    refs.run_id,
                    _cancel_request("cancel-independent-owner-cancel"),
                )
                assert cancelling.status is RunStatus.CANCELLING
                assert handle.cancel_reasons == []

                await asyncio.wait_for(handle._cancelled.wait(), timeout=1.0)
                assert handle.cancel_reasons == ["user_stop"]

                await scheduler.close()
                assert blocker.cancelled.is_set()
                assert session_task.done()
                assert owner_cancel_task.done()
            finally:
                blocker.release.set()
                await scheduler.close()
    finally:
        caller_host.close()
        owner_host.close()


@pytest.mark.asyncio
async def test_owner_cancel_task_is_joined_when_later_scheduler_open_step_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """owner cancel task 启动后的 failed-open 必须取消并 await 它。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    :raises AssertionError: failed-open 泄漏 owner cancel task 时抛出。
    """

    captured_tasks: list[asyncio.Task[None]] = []
    original_start = (
        HostDispatchScheduler._start_active_worker_cancel_reconciliation_loop
    )

    def record_owner_cancel_start(self: HostDispatchScheduler) -> None:
        """启动并记录 owner cancel task。

        :param self: 正在打开的 scheduler。
        :returns: ``None``。
        :raises Exception: production start 失败时透传。
        """

        original_start(self)
        task = self._active_worker_cancel_reconciliation_task
        assert task is not None
        captured_tasks.append(task)

    def fail_owned_session_start(self: HostDispatchScheduler) -> None:
        """模拟 owner cancel task 之后的 scheduler open 失败。

        :param self: 正在打开的 scheduler。
        :returns: 本 helper 不返回。
        :raises RuntimeError: 始终抛出测试错误。
        """

        del self
        raise RuntimeError("forced owned session reconciliation start failure")

    monkeypatch.setattr(
        HostDispatchScheduler,
        "_start_active_worker_cancel_reconciliation_loop",
        record_owner_cancel_start,
    )
    monkeypatch.setattr(
        HostDispatchScheduler,
        "_start_owned_session_reconciliation_loop",
        fail_owned_session_start,
    )
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        with pytest.raises(
            RuntimeError,
            match="forced owned session reconciliation start failure",
        ):
            await _open_scheduler(
                tmp_path,
                store,
                _CancelAwareHandle(
                    local_worker_id="worker-failed-open-owner-cancel",
                    terminal="hang",
                ),
            )

    assert len(captured_tasks) == 1
    assert captured_tasks[0].done()


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
        self.cancel_thread_ids: list[int] = []
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
        self.cancel_thread_ids.append(threading.get_ident())
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


class _CancelClosingHandle:
    """收到 cancel 后让事件流以 CancelledError 收口的 fake handle。"""

    def __init__(self, *, local_worker_id: str) -> None:
        """初始化 fake handle。

        :param local_worker_id: worker 诊断 id。
        :returns: ``None``。
        """

        self._local_worker_id = local_worker_id
        self._cancelled = asyncio.Event()
        self.closed = asyncio.Event()
        self.cancel_reasons: list[str] = []

    @property
    def local_worker_id(self) -> str:
        """返回 worker 诊断 id。

        :returns: worker id。
        """

        return self._local_worker_id

    async def events(self) -> AsyncIterator[EngineEvent]:
        """等待 cancel 后以 CancelledError 结束 active anext。

        :returns: EngineEvent 异步迭代器。
        :raises asyncio.CancelledError: cancel 到达后抛出。
        """

        await self._cancelled.wait()
        raise asyncio.CancelledError
        if False:
            yield EngineEvent(
                occurred_at=_NOW,
                session_id="unused-session",
                run_id="unused-run",
                type=EngineEventType.FINAL_ANSWER,
                data=FinalAnswerData(
                    content="unused",
                    filtered=False,
                    degraded=False,
                    finish_reason=FinishReason.STOP,
                ),
                metadata=None,
            )

    def on_cancel(self, reason: str) -> None:
        """记录取消并唤醒事件流。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        self.cancel_reasons.append(reason)
        self._cancelled.set()

    def bind_snapshot(self, snapshot: AttemptDispatchSnapshot) -> None:
        """绑定 worker accept 快照。

        :param snapshot: dispatch snapshot。
        :returns: ``None``。
        """

        del snapshot

    async def close(self) -> None:
        """关闭 fake handle。

        :returns: ``None``。
        """

        self.closed.set()


class _FakeWorker:
    """返回固定 fake handle 的 worker。"""

    def __init__(self, handle: _CancelAwareHandle | _CancelClosingHandle) -> None:
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

    def __init__(self, handle: _CancelAwareHandle | _CancelClosingHandle) -> None:
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

    def __init__(
        self, handles: tuple[_CancelAwareHandle | _CancelClosingHandle, ...]
    ) -> None:
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


@pytest.mark.parametrize(
    ("status", "worker_accepted", "expected"),
    (
        (DispatchRecordStatus.PENDING, False, True),
        (DispatchRecordStatus.WAITING_FOR_LANE, False, True),
        (DispatchRecordStatus.DISPATCHING, False, True),
        (DispatchRecordStatus.DISPATCHING, True, False),
        (DispatchRecordStatus.CANCELLED, False, False),
    ),
)
def test_dispatch_record_direct_cancelable_predicate_owned_by_durable_state(
    status: DispatchRecordStatus,
    worker_accepted: bool,
    expected: bool,
) -> None:
    """durable owner helper 完整覆盖 pre-worker direct-cancel 判定表。

    :param status: dispatch record status。
    :param worker_accepted: 是否写入完整 worker accepted facts。
    :param expected: 预期 direct-cancel 判定。
    :returns: ``None``。
    :raises: 断言失败时由 pytest 报告。
    """

    accepted_at = _NOW.isoformat() if worker_accepted else None
    accepted_event_id = "event-worker-accepted" if worker_accepted else None
    accepted_event_sequence = 2 if worker_accepted else None
    record = DispatchRecordRow(
        dispatch_record_id="dispatch-direct-cancel-owner",
        run_id="run-direct-cancel-owner",
        attempt_id="attempt-direct-cancel-owner",
        execution_id="execution-direct-cancel-owner",
        status=status,
        worker_kind=WorkerKind.LOCAL,
        execution_target="local-default",
        owner_host_instance_id="host-direct-cancel-owner",
        created_event_id="event-attempt-started-owner",
        created_event_sequence=1,
        waiting_for_lane_at=None,
        lane_name=None,
        lane_claim_id=None,
        lane_owner_id=None,
        lane_acquired_at=None,
        dispatching_at=None,
        worker_accepted_at=accepted_at,
        worker_accept_event_id=accepted_event_id,
        worker_accept_event_sequence=accepted_event_sequence,
        cancelled_event_id=None,
        cancelled_event_sequence=None,
        created_at=_NOW.isoformat(),
        updated_at=_NOW.isoformat(),
        cancelled_at=None,
    )

    assert is_dispatch_record_direct_cancelable(record) is expected


def test_cancel_run_waiting_for_lane_skips_later_dispatch(tmp_path: Path) -> None:
    """waiting_for_lane direct cancel 后 scheduler wake 不会 dispatch。"""

    options = _command_options(tmp_path)
    host = _create_execution_handle(options)
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
    host = _create_execution_handle(options)
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


def test_cancel_run_starting_worker_accepted_enters_active_cancel(
    tmp_path: Path,
) -> None:
    """STARTING 且 worker 已接受的竞态窗口按 active worker cancel 处理。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    options = _command_options(tmp_path)
    host = _create_execution_handle(options)
    try:
        session_id = _session_id(host)
        refs: _RunRefs | None = None
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            async def _prepare_worker_accepted_starting() -> _RunRefs:
                """构造 dispatch 已 worker accepted 但 Attempt 仍 STARTING 的窗口。

                :returns: 构造完成的 Run refs。
                """

                scheduler = await _open_scheduler(
                    tmp_path,
                    store,
                    _CancelAwareHandle(
                        local_worker_id="worker-accepted-starting",
                        terminal="hang",
                    ),
                )
                try:
                    start_run(
                        host,
                        _start_request(session_id, "start-worker-accepted"),
                    )
                    prepared = await _start_governed_refs(scheduler, session_id)
                    _mark_worker_accepted_without_attempt_running(
                        store.transaction_runner,
                        prepared,
                    )
                    return prepared
                finally:
                    await scheduler.close()

            refs = asyncio.run(_prepare_worker_accepted_starting())

        assert refs is not None
        cancelling = cancel_run(
            host,
            refs.run_id,
            _cancel_request("cancel-worker-accepted"),
        )

        assert cancelling.status == RunStatus.CANCELLING
        assert _run_status(options.db_path, refs.run_id) == RunStatus.CANCELLING
        assert _attempt_status(options.db_path, refs.attempt_id) == (
            AttemptStatus.RUNNING
        )
    finally:
        host.close()


@pytest.mark.asyncio
async def test_cancel_run_deferred_classification_uses_single_write_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """deferred error 由 cancel write snapshot 产生且不再打开 read transaction。

    :param tmp_path: pytest 临时目录。
    :param monkeypatch: pytest monkeypatch fixture。
    :returns: ``None``。
    """

    options = _command_options(tmp_path)
    host = _create_execution_handle(options)
    read_calls = 0
    write_calls = 0
    original_run_read = HostTransactionRunner.run_read
    original_run_write = HostTransactionRunner.run_write
    try:
        session_id = _session_id(host)
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                _CancelAwareHandle(
                    local_worker_id="worker-deferred-snapshot",
                    terminal="hang",
                ),
            )
            try:
                active = start_run(
                    host,
                    _start_request(session_id, "start-deferred-snapshot"),
                )
                refs = await _start_governed_refs(scheduler, session_id)
                _delete_dispatch_record(store.transaction_runner, refs)
                event_count_before = _event_count(options.db_path)
                actor_runner = host._transaction_runner()

                def record_read(
                    self: HostTransactionRunner,
                    operation: HostReadTransactionOperation[T],
                ) -> T:
                    """记录目标 command runner read transaction。

                    :param self: transaction runner。
                    :param operation: read operation。
                    :returns: 原始 operation 结果。
                    :raises Exception: 原始 read 失败时透传。
                    """

                    nonlocal read_calls
                    if self is actor_runner:
                        read_calls += 1
                    return original_run_read(self, operation)

                def record_write(
                    self: HostTransactionRunner,
                    operation: HostTransactionOperation[T],
                ) -> T:
                    """记录目标 command runner write transaction。

                    :param self: transaction runner。
                    :param operation: write operation。
                    :returns: 原始 operation 结果。
                    :raises Exception: 原始 write 失败时透传。
                    """

                    nonlocal write_calls
                    if self is actor_runner:
                        write_calls += 1
                    return original_run_write(self, operation)

                monkeypatch.setattr(HostTransactionRunner, "run_read", record_read)
                monkeypatch.setattr(HostTransactionRunner, "run_write", record_write)

                with pytest.raises(HostApiError) as exc_info:
                    cancel_run(
                        host,
                        active.run_id,
                        _cancel_request("cancel-deferred-snapshot"),
                    )

                assert exc_info.value.code is HostApiErrorCode.UNSUPPORTED_OPERATION
                assert write_calls == 1
                assert read_calls == 0
                assert _event_count(options.db_path) == event_count_before

                def return_cas_lost(
                    transaction: HostTransaction,
                    event_log_store: EventLogStore,
                    request: CancelActiveAttemptInput,
                ) -> RunTransitionResult:
                    """模拟同一 write snapshot 内 transition conflict。

                    :param transaction: 当前 Host transaction。
                    :param event_log_store: EventLog primitive。
                    :param request: active cancel transition input。
                    :returns: 固定 CAS_LOST result。
                    """

                    del transaction, event_log_store, request
                    return RunTransitionResult(
                        status=StateMutationStatus.CAS_LOST,
                        run=None,
                        attempt=None,
                        dispatch_record=None,
                        run_event=None,
                    )

                monkeypatch.setattr(
                    host_admission,
                    "request_active_attempt_cancel_in_transaction",
                    return_cas_lost,
                )
                read_calls = 0
                write_calls = 0
                with pytest.raises(HostApiError) as conflict_info:
                    cancel_run(
                        host,
                        active.run_id,
                        _cancel_request("cancel-conflict-snapshot"),
                    )

                assert conflict_info.value.code is HostApiErrorCode.INVALID_STATE
                assert write_calls == 1
                assert read_calls == 0
                assert _event_count(options.db_path) == event_count_before
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_cancel_run_active_worker_propagates_and_closes_cancelled(
    tmp_path: Path,
) -> None:
    """Attempt RUNNING cancel 进入 CANCELLING，worker run_cancelled 后终态取消。"""

    options = _command_options(tmp_path)
    active_registry = ActiveWorkerRegistry()
    host = _create_execution_handle(options, active_registry=active_registry)
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
    host = _create_execution_handle(options, active_registry=active_registry)
    handle = _CancelAwareHandle(local_worker_id="worker-watchdog", terminal="blocked")
    try:
        session_id = _session_id(host)
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                handle,
                active_registry=active_registry,
            )
            try:
                start_run(host, _start_request(session_id, "start-watchdog"))
                refs = await _start_governed_refs(scheduler, session_id)
                scheduler.wake_dispatch(_pending_dispatch(refs))
                drain = await scheduler.drain_once()
                assert drain.dispatched == 1

                cancelling = cancel_run(
                    host, refs.run_id, _cancel_request("cancel-watchdog")
                )
                assert cancelling.status == RunStatus.CANCELLING

                result = scheduler.tick_active_cancel_watchdog_for_session(
                    session_id,
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
async def test_active_cancel_watchdog_closes_on_first_tick_after_cancel(
    tmp_path: Path,
) -> None:
    """cancel accepted 后第一轮 watchdog tick 即写 terminal fact。"""

    options = _command_options(tmp_path)
    active_registry = ActiveWorkerRegistry()
    host = _create_execution_handle(options, active_registry=active_registry)
    handle = _CancelAwareHandle(local_worker_id="worker-before-watchdog", terminal="blocked")
    try:
        session_id = _session_id(host)
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                handle,
                active_registry=active_registry,
            )
            try:
                start_run(host, _start_request(session_id, "start-before-watchdog"))
                refs = await _start_governed_refs(scheduler, session_id)
                scheduler.wake_dispatch(_pending_dispatch(refs))
                assert (await scheduler.drain_once()).dispatched == 1

                cancel_run(host, refs.run_id, _cancel_request("cancel-before-watchdog"))
                result = scheduler.tick_active_cancel_watchdog_for_session(
                    session_id,
                    datetime.now(UTC),
                )

                assert result.closed == 1
                assert _run_status(options.db_path, refs.run_id) == RunStatus.CANCELLED
                assert _event_type_count(options.db_path, "RUN_CANCELLED") == 1
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
        )
        try:
            result = scheduler.tick_active_cancel_watchdog_for_session(
                "session-without-cancel",
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
    host = _create_execution_handle(options, active_registry=active_registry)
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
                first_result = scheduler.tick_active_cancel_watchdog_for_session(
                    first_session_id,
                    datetime(2030, 1, 1, tzinfo=UTC)
                )
                second_result = scheduler.tick_active_cancel_watchdog_for_session(
                    second_session_id,
                    datetime(2030, 1, 1, tzinfo=UTC),
                )

                assert first_result.scanned == 1
                assert first_result.closed == 1
                assert second_result.scanned == 1
                assert second_result.closed == 1
                assert _run_status(options.db_path, first.run_id) == RunStatus.CANCELLED
                assert _run_status(options.db_path, second.run_id) == RunStatus.CANCELLED
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_active_cancel_watchdog_closeout_promotes_queued_run(tmp_path: Path) -> None:
    """watchdog closeout 释放 Session active slot 并 promotion queued Run。"""

    options = _command_options(tmp_path)
    active_registry = ActiveWorkerRegistry()
    host = _create_execution_handle(options, active_registry=active_registry)
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
            )
            try:
                refs = await _start_governed_refs(scheduler, session_id)
                scheduler.wake_dispatch(_pending_dispatch(refs))
                assert (await scheduler.drain_once()).dispatched == 1
                cancel_run(host, active.run_id, _cancel_request("cancel-promote"))

                result = scheduler.tick_active_cancel_watchdog_for_session(
                    session_id,
                    datetime(2030, 1, 1, tzinfo=UTC)
                )
                replay = scheduler.tick_active_cancel_watchdog_for_session(
                    session_id,
                    datetime(2030, 1, 1, tzinfo=UTC)
                )

                assert result.closed == 1
                assert replay.closed == 0
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
async def test_cancelled_worker_event_stream_releases_lane_for_other_session(
    tmp_path: Path,
) -> None:
    """active anext CancelledError 仍进入 finally 并释放 lane token。"""

    options = _command_options(tmp_path)
    active_registry = ActiveWorkerRegistry()
    host = _create_execution_handle(options, active_registry=active_registry)
    closing_handle = _CancelClosingHandle(local_worker_id="worker-cancel-closing")
    next_handle = _CancelAwareHandle(local_worker_id="worker-after-cancel", terminal="final")
    worker_factory = _SequencedWorkerFactory((closing_handle, next_handle))
    try:
        first_session_id = _session_id(host)
        second_session_id = ensure_session(
            host,
            EnsureSessionRequest(
                scope="workspace",
                slot_key="slot-after-cancel-close",
                metadata=(),
            ),
        ).session_id
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                closing_handle,
                worker_factory=worker_factory,
                active_registry=active_registry,
                lane_capacity=1,
                lane_timeout_seconds=0.5,
            )
            try:
                first = start_run(host, _start_request(first_session_id, "start-closing"))
                first_refs = await _start_governed_refs(scheduler, first_session_id)
                scheduler.wake_dispatch(_pending_dispatch(first_refs))
                assert (await scheduler.drain_once()).dispatched == 1
                await _wait_for_attempt_status(
                    options.db_path,
                    first_refs.attempt_id,
                    AttemptStatus.RUNNING,
                )

                cancel_run(host, first.run_id, _cancel_request("cancel-closing"))
                await asyncio.wait_for(closing_handle.closed.wait(), timeout=1.0)

                second = start_run(
                    host,
                    _start_request(second_session_id, "start-after-cancel-close"),
                )
                second_refs = await _start_governed_refs(
                    scheduler, second_session_id
                )
                scheduler.wake_dispatch(_pending_dispatch(second_refs))

                await _wait_for_run_status(
                    options.db_path,
                    second.run_id,
                    RunStatus.SUCCEEDED,
                )

                assert closing_handle.cancel_reasons == ["user_stop"]
                assert worker_factory.created == 2
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_late_cancel_does_not_overwrite_terminal(tmp_path: Path) -> None:
    """terminal 已先提交时 late cancel 只返回当前终态。"""

    options = _command_options(tmp_path)
    host = _create_execution_handle(options)
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
    host = _create_execution_handle(options)
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
    host = _create_execution_handle(options, active_registry=active_registry)
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
async def test_cancel_session_replay_after_watchdog_does_not_append_or_propagate(
    tmp_path: Path,
) -> None:
    """watchdog terminal 后 session cancel replay 不追加 facts 或传播 cancel。"""

    options = _command_options(tmp_path)
    active_registry = ActiveWorkerRegistry()
    host = _create_execution_handle(options, active_registry=active_registry)
    handle = _CancelAwareHandle(local_worker_id="worker-replay-watchdog", terminal="blocked")
    try:
        session_id = _session_id(host)
        request = _cancel_session_request("cancel-session-watchdog")
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                handle,
                active_registry=active_registry,
            )
            try:
                start_run(host, _start_request(session_id, "start-session-watchdog"))
                refs = await _start_governed_refs(scheduler, session_id)
                scheduler.wake_dispatch(_pending_dispatch(refs))
                assert (await scheduler.drain_once()).dispatched == 1
                cancel_session_runs(host, session_id, request)
                scheduler.tick_active_cancel_watchdog_for_session(
                    session_id,
                    datetime(2030, 1, 1, tzinfo=UTC)
                )
                after_watchdog_events = _event_count(options.db_path)

                replay = cancel_session_runs(host, session_id, request)

                assert replay.active_run_id is None
                assert _run_status(options.db_path, refs.run_id) == RunStatus.CANCELLED
                assert _event_count(options.db_path) == after_watchdog_events
                assert handle.cancel_reasons == ["user_stop_all"]
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_scheduler_close_writes_active_cancel_closeout_terminal(
    tmp_path: Path,
) -> None:
    """scheduler close 对 active CANCELLING Run 写 durable cancel terminal facts。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    """

    options = _command_options(tmp_path)
    active_registry = ActiveWorkerRegistry()
    host = _create_execution_handle(options, active_registry=active_registry)
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
            )
            start_run(host, _start_request(session_id, "start-close"))
            refs = await _start_governed_refs(scheduler, session_id)
            scheduler.wake_dispatch(_pending_dispatch(refs))
            assert (await scheduler.drain_once()).dispatched == 1
            cancel_run(host, refs.run_id, _cancel_request("cancel-close"))

            await scheduler.close()

        assert refs is not None
        assert _run_status(options.db_path, refs.run_id) == RunStatus.CANCELLED
        assert _attempt_status(options.db_path, refs.attempt_id) == AttemptStatus.CANCELLED
        assert _event_type_count(options.db_path, "RUN_CANCELLED") == 1
        cancel_requested_at = _latest_event_occurred_at(
            options.db_path,
            "CANCEL_REQUESTED",
        )
        run_cancelled_payload = _latest_event_payload(
            options.db_path,
            "RUN_CANCELLED",
        )
        assert run_cancelled_payload["requested_at"] == cancel_requested_at
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
    handle: _CancelAwareHandle | _CancelClosingHandle,
    *,
    worker_factory: LocalEngineWorkerFactory | None = None,
    lane_timeout_seconds: float | None = 0.01,
    active_registry: ActiveWorkerRegistry | None = None,
    lane_capacity: int = 1,
) -> HostDispatchScheduler:
    """打开测试 scheduler。

    :param tmp_path: pytest 临时目录。
    :param store: durable store。
    :param handle: worker handle。
    :param worker_factory: 可选 worker factory；不传时使用单 handle factory。
    :param lane_timeout_seconds: lane acquire timeout 秒数。
    :param active_registry: 可选 active worker registry。
    :param lane_capacity: 测试 lane 容量。
    :returns: scheduler。
    """

    return await HostDispatchScheduler.open(
        transaction_runner=store.transaction_runner,
        transient_delta_publisher=NOOP_TRANSIENT_DELTA_PUBLISHER,
        terminal_post_commit_port_factory=_TerminalPortFactory(),
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
                fallback_prompt="test fallback prompt",
                continuation_prompt="test continuation prompt",
            ),
            worker_factory=(
                worker_factory
                if worker_factory is not None
                else _FakeWorkerFactory(handle)
            ),
        ),
        host_handle_id="host-active-cancel",
        active_registry=active_registry,
        session_new_work_access=ExplicitFakeSessionAccess(
            allowed_session_ids=None
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


def _ordinary_run_baseline() -> OrdinaryRunExecutionBaseline:
    """构造与测试 scheduler 一致的 ordinary Run baseline。

    :returns: 显式 execution baseline。
    :raises TypeError: typed execution contract 非法时抛出。
    :raises ValueError: typed execution contract 字段非法时抛出。
    """

    return OrdinaryRunExecutionBaseline(
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
    )


def _create_execution_handle(
    options: HostCommandHandleOptions,
    *,
    active_registry: ActiveWorkerRegistry | None = None,
) -> HostCommandHandle:
    """创建与本文件 scheduler construction truth 一致的 command handle。

    :param options: durable command options。
    :param active_registry: 可选 active worker registry。
    :returns: 显式装配 execution admission 的 handle。
    :raises HostApiError: durable store 或 admission 装配失败时抛出。
    """

    return create_execution_command_handle(
        options,
        ordinary_run_baseline=_ordinary_run_baseline(),
        memory_projection_policy=default_memory_projection_policy(),
        active_registry=active_registry,
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

    work_lease = scheduler._session_new_work_access.try_acquire_new_work_lease(
        session_id
    )
    assert work_lease is not None
    try:
        stage = await scheduler._run_pre_start_governance(
            session_id,
            work_lease=work_lease,
        )
    finally:
        work_lease.release()
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


def _delete_dispatch_record(
    transaction_runner: HostTransactionRunner,
    refs: _RunRefs,
) -> None:
    """删除 current dispatch row，构造 deferred cancel capability snapshot。

    :param transaction_runner: transaction runner。
    :param refs: 目标 Run durable refs。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        """删除 current Attempt 的 child dispatch row。

        :param transaction: 当前 Host transaction。
        :returns: ``None``。
        """

        transaction.execute(
            f"""
            DELETE FROM {TABLE_HOST_ATTEMPT_DISPATCH_RECORDS}
            WHERE dispatch_record_id = ?
            """,
            (refs.dispatch_record_id,),
        )

    transaction_runner.run_write(_operation)


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
        waiting = mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=refs.attempt_id,
            owner_host_instance_id="host-active-cancel",
            lane_name=_LANE_NAME,
            waiting_for_lane_at="2026-05-15T01:02:03.000000Z",
        )
        assert waiting.status == StateMutationStatus.UPDATED
        dispatching = mark_dispatching_after_lane_row(
            transaction,
            attempt_id=refs.attempt_id,
            owner_host_instance_id="host-active-cancel",
            lane_name=_LANE_NAME,
            lane_claim_id="claim-active-cancel",
            lane_owner_id="owner-active-cancel",
            lane_acquired_at="2026-05-15T01:02:03.000000Z",
            dispatching_at="2026-05-15T01:02:03.000000Z",
        )
        assert dispatching.status == StateMutationStatus.UPDATED

    transaction_runner.run_write(_operation)


def _mark_worker_accepted_without_attempt_running(
    transaction_runner: HostTransactionRunner, refs: _RunRefs
) -> None:
    """构造 dispatch worker accept fact 已提交但 Attempt 仍 STARTING 的窗口。

    :param transaction_runner: transaction runner。
    :param refs: durable refs。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        """写入 worker accept event refs。

        :param transaction: Host transaction。
        :returns: ``None``。
        """

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
        event = EventLogStore().append_event(
            transaction,
            EventLogAppendRequest(
                event_id="event-worker-accepted-starting",
                event_class=EventClass.CANONICAL_FACT,
                session_id=refs.session_id,
                run_id=refs.run_id,
                attempt_id=refs.attempt_id,
                execution_id=refs.execution_id,
                event_type="ATTEMPT_RUNNING",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id=None,
                idempotency_key=None,
                policy_decision=None,
                reason="worker_accepted",
                payload_json={
                    "attempt_id": refs.attempt_id,
                    "execution_id": refs.execution_id,
                    "dispatch_record_id": refs.dispatch_record_id,
                    "reason": "worker_accepted",
                },
                payload_ref=None,
                payload_digest=None,
            ),
        ).row
        accepted = mark_dispatch_worker_accepted_row(
            transaction,
            attempt_id=refs.attempt_id,
            worker_accept_event_id=event.event_id,
            worker_accept_event_sequence=event.event_sequence,
            worker_accepted_at="2026-05-15T01:02:03.000000Z",
        )
        assert accepted.status == StateMutationStatus.UPDATED

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


def _latest_event_occurred_at(db_path: Path, event_type: str) -> str:
    """读取指定 EventLog 类型的最新发生时间。

    :param db_path: SQLite DB 路径。
    :param event_type: event type。
    :returns: 最新事件的 ``occurred_at``。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT occurred_at
            FROM event_log
            WHERE event_type = ?
            ORDER BY event_sequence DESC
            LIMIT 1
            """,
            (event_type,),
        ).fetchone()
    assert row is not None
    return str(row[0])


def _latest_event_payload(
    db_path: Path,
    event_type: str,
) -> Mapping[str, JsonValue]:
    """读取指定 EventLog 类型的最新 JSON payload。

    :param db_path: SQLite DB 路径。
    :param event_type: event type。
    :returns: 最新事件的 JSON object payload。
    """

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT payload_json
            FROM event_log
            WHERE event_type = ?
            ORDER BY event_sequence DESC
            LIMIT 1
            """,
            (event_type,),
        ).fetchone()
    assert row is not None
    value = cast(JsonValue, json.loads(str(row[0])))
    assert isinstance(value, Mapping)
    return cast(Mapping[str, JsonValue], value)


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
