"""Host 本地 dispatch scheduler。

本模块实现 Phase 5 本地 dispatch 的最小调度闭环：commit 后接收
pending dispatch 摘要，获取 runtime lane capacity，durable recheck 后
调用 LocalProxy，并在 worker accept 后追加 ``ATTEMPT_RUNNING`` 与推进
Attempt ``RUNNING``。``dispatching`` 与 lane token 只作为诊断和容量控制，
不表达 owner truth、lease、fencing 或 takeover proof。
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.host.admission import PendingDispatchRecord, create_host_admission_service
from dayu.host.api import (
    AttemptDispatchSnapshot,
    AttemptStatus,
    HostLocalExecutionOptions,
    LocalWorkerHandle,
    RunStatus,
)
from dayu.host.durable.codec import format_utc_timestamp
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogStore,
)
from dayu.host.durable.liveness import (
    HostInstanceIdentity,
    register_current_instance,
)
from dayu.host.durable.run_transition import (
    TerminalCloseoutInput,
    terminal_closeout_in_transaction,
)
from dayu.host.durable.state import (
    AttemptRow,
    DispatchRecordRow,
    DispatchRecordStatus,
    RunRow,
    StateMutationStatus,
    WorkerKind,
    mark_attempt_running_row,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatch_worker_accepted_row,
    mark_dispatching_after_lane_row,
    read_attempt_by_id,
    read_dispatch_record_by_id,
    read_dispatch_record_by_attempt_id,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.engine_ingest import (
    EngineEventCandidate,
    EngineEventIngestor,
    EngineIngestStatus,
    LocalEngineEnvelope,
)
from dayu.host.run_input import PolicySnapshot, create_no_tool_run_input_builder
from dayu.runtime.lane import (
    LaneAcquireCancelled,
    LaneAcquired,
    LaneAcquireTimedOut,
    LaneClaimToken,
    LaneConfig,
    LaneController,
    LaneOwner,
    SQLiteLaneCoordinatorConfig,
)

_EVENT_SOURCE = "host.dispatch"
_EVENT_ACTOR = "host.dispatch"
_EVENT_TYPE_ATTEMPT_RUNNING = "ATTEMPT_RUNNING"
_WORKER_ACCEPT_REASON = "local_worker_accepted"
_WORKER_STARTUP_TIMEOUT_REASON = "worker_startup_timeout"
_LOCAL_POLICY_SNAPSHOT_REF = "host-local-no-tool-policy"
_EVENT_ID_ATTEMPT_RUNNING_PREFIX = "event-attempt-running"
_EVENT_ID_ATTEMPT_FAILED_PREFIX = "event-attempt-failed"
_EVENT_ID_RUN_FAILED_PREFIX = "event-run-failed"
_LANE_OWNER_PREFIX = "host-dispatch"


@dataclass(frozen=True, slots=True)
class DispatchDrainResult:
    """一次 dispatch drain 摘要。

    :param processed: 已处理 wakeup 数。
    :param dispatched: 成功进入 worker accept 的数量。
    :param skipped: durable recheck 或状态前置不满足而跳过的数量。
    :param timed_out: lane acquire 或 worker startup timeout 数量。
    """

    processed: int
    dispatched: int
    skipped: int
    timed_out: int


@dataclass(frozen=True, slots=True)
class ActiveCancelMessage:
    """active worker cancel registry 的最小取消消息。

    :param run_id: 目标 Run id。
    :param attempt_id: 目标 Attempt id。
    :param execution_id: 目标 execution id。
    :param reason: 取消原因。
    """

    run_id: str
    attempt_id: str
    execution_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class _ActiveWorkerEntry:
    """active worker registry 内部条目。

    :param run_id: 目标 Run id。
    :param handle: worker handle。
    :param cancellation_token: Host 注入 Engine 的取消 token。
    """

    run_id: str
    handle: LocalWorkerHandle
    cancellation_token: "_HostCancellationToken"


class ActiveWorkerRegistry:
    """进程内 active worker handle registry。

    registry 只提供 best-effort cancel 传播；durable EventLog / Run state
    仍是取消请求是否被接受的真源。
    """

    def __init__(self) -> None:
        """初始化空 registry。

        :returns: ``None``。
        """

        self._lock = RLock()
        self._entries: dict[tuple[str, str], _ActiveWorkerEntry] = {}

    def register(
        self,
        *,
        run_id: str,
        attempt_id: str,
        execution_id: str,
        handle: LocalWorkerHandle,
        cancellation_token: "_HostCancellationToken",
    ) -> None:
        """注册 active worker handle。

        :param run_id: 目标 Run id。
        :param attempt_id: active Attempt id。
        :param execution_id: active execution id。
        :param handle: worker handle。
        :param cancellation_token: 注入 Engine 的取消 token。
        :returns: ``None``。
        """

        with self._lock:
            self._entries[(attempt_id, execution_id)] = _ActiveWorkerEntry(
                run_id=run_id,
                handle=handle,
                cancellation_token=cancellation_token,
            )

    def unregister(self, *, attempt_id: str, execution_id: str) -> None:
        """注销 active worker handle。

        :param attempt_id: active Attempt id。
        :param execution_id: active execution id。
        :returns: ``None``。
        """

        with self._lock:
            self._entries.pop((attempt_id, execution_id), None)

    def cancel(self, message: ActiveCancelMessage) -> bool:
        """向 active worker best-effort 传播 cancel。

        :param message: 最小取消消息。
        :returns: 找到匹配 active worker 时返回 ``True``。
        """

        with self._lock:
            entry = self._entries.get((message.attempt_id, message.execution_id))
        if entry is None or entry.run_id != message.run_id:
            return False
        entry.cancellation_token.request_cancel(message.reason)
        try:
            entry.handle.cancel(message.reason)
        except RuntimeError:
            return True
        return True


class _HostCancellationToken:
    """Host 可写入、Engine 可观察的取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 已请求取消时返回 ``True``。
        """

        with self._lock:
            return self._reason is not None

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 取消原因；未取消时返回 ``None``。
        """

        with self._lock:
            return self._reason

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 请求时间；未取消时返回 ``None``。
        """

        with self._lock:
            return self._requested_at

    def __init__(self) -> None:
        """初始化未取消 token。

        :returns: ``None``。
        """

        self._lock = RLock()
        self._reason: str | None = None
        self._requested_at: datetime | None = None

    def request_cancel(self, reason: str) -> None:
        """标记 token 已请求取消。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        with self._lock:
            if self._reason is None:
                self._reason = reason
                self._requested_at = datetime.now(UTC)


DEFAULT_ACTIVE_WORKER_REGISTRY = ActiveWorkerRegistry()


def cancel_active_worker(message: ActiveCancelMessage) -> bool:
    """通过默认 active registry best-effort 传播 cancel。

    :param message: 最小取消消息。
    :returns: 找到匹配 active worker 时返回 ``True``。
    """

    return DEFAULT_ACTIVE_WORKER_REGISTRY.cancel(message)


class HostDispatchScheduler:
    """Host 本地 dispatch scheduler。"""

    def __init__(
        self,
        *,
        transaction_runner: HostTransactionRunner,
        event_log_store: EventLogStore,
        local_execution: HostLocalExecutionOptions,
        lane_controller: LaneController,
        host_handle_id: str,
        active_registry: ActiveWorkerRegistry | None = None,
    ) -> None:
        """初始化 dispatch scheduler。

        :param transaction_runner: Host durable transaction runner。
        :param event_log_store: EventLog append primitive。
        :param local_execution: 本地执行配置。
        :param lane_controller: 已打开的 runtime lane controller。
        :param host_handle_id: Host handle 诊断 id。
        :param active_registry: active worker registry；不传时使用默认 registry。
        :returns: ``None``。
        :raises ValueError: ``host_handle_id`` 为空时抛出。
        """

        if host_handle_id.strip() == "":
            raise ValueError("host_handle_id must be non-empty")
        self._transaction_runner = transaction_runner
        self._event_log_store = event_log_store
        self._local_execution = local_execution
        self._lane_controller = lane_controller
        self._host_handle_id = host_handle_id
        self._active_registry = (
            active_registry
            if active_registry is not None
            else DEFAULT_ACTIVE_WORKER_REGISTRY
        )
        self._queue: asyncio.Queue[PendingDispatchRecord] = asyncio.Queue()
        self._closed = False
        self._drain_task: asyncio.Task[None] | None = None
        self._active_tasks: set[asyncio.Task[None]] = set()
        self._active_handles: set[LocalWorkerHandle] = set()

    @classmethod
    async def open(
        cls,
        *,
        transaction_runner: HostTransactionRunner,
        local_execution: HostLocalExecutionOptions,
        host_handle_id: str,
        active_registry: ActiveWorkerRegistry | None = None,
    ) -> "HostDispatchScheduler":
        """打开本地 dispatch scheduler。

        :param transaction_runner: Host durable transaction runner。
        :param local_execution: 本地执行配置。
        :param host_handle_id: Host handle 诊断 id。
        :param active_registry: active worker registry；不传时使用默认 registry。
        :returns: 已打开 scheduler。
        """

        lane_controller = await LaneController.open(
            [
                LaneConfig(
                    name=local_execution.lane_name,
                    capacity=local_execution.lane_capacity,
                    default_timeout_seconds=(
                        local_execution.lane_default_timeout_seconds
                    ),
                    claim_ttl_seconds=local_execution.lane_claim_ttl_seconds,
                    heartbeat_interval_seconds=(
                        local_execution.lane_heartbeat_interval_seconds
                    ),
                )
            ],
            coordinator=SQLiteLaneCoordinatorConfig(
                db_path=local_execution.lane_db_path
            ),
            owner=LaneOwner(
                owner_id=f"{_LANE_OWNER_PREFIX}-{host_handle_id}",
                pid=os.getpid(),
                process_start_token=None,
            ),
        )
        _register_dispatch_host_instance(
            transaction_runner=transaction_runner,
            host_handle_id=host_handle_id,
        )
        return cls(
            transaction_runner=transaction_runner,
            event_log_store=EventLogStore(),
            local_execution=local_execution,
            lane_controller=lane_controller,
            host_handle_id=host_handle_id,
            active_registry=active_registry,
        )

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """唤醒 dispatch scheduler。

        :param record: 已持久化的 pending dispatch 摘要。
        :returns: ``None``。
        :raises RuntimeError: scheduler 已关闭时抛出。
        """

        if self._closed:
            raise RuntimeError("HostDispatchScheduler is closed")
        self._queue.put_nowait(record)
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = asyncio.create_task(self._drain_loop())

    def wake_queue_promotion(self, session_id: str) -> None:
        """唤醒同 Session 的 queued Run promotion。

        :param session_id: 目标 Session id。
        :returns: ``None``。
        :raises RuntimeError: scheduler 已关闭时抛出。
        """

        if self._closed:
            raise RuntimeError("HostDispatchScheduler is closed")
        create_host_admission_service(
            self._transaction_runner,
            wakeup_port=self,
        ).promote_next_queued_run(session_id)

    async def drain_once(self) -> DispatchDrainResult:
        """同步处理当前队列中的 dispatch wakeup。

        :returns: 本次 drain 摘要。
        :raises RuntimeError: scheduler 已关闭时抛出。
        """

        if self._closed:
            raise RuntimeError("HostDispatchScheduler is closed")
        processed = 0
        dispatched = 0
        skipped = 0
        timed_out = 0
        while not self._queue.empty():
            record = self._queue.get_nowait()
            processed += 1
            outcome = await self._dispatch_one(record)
            if outcome == "dispatched":
                dispatched += 1
            elif outcome == "timed_out":
                timed_out += 1
            else:
                skipped += 1
        return DispatchDrainResult(
            processed=processed,
            dispatched=dispatched,
            skipped=skipped,
            timed_out=timed_out,
        )

    async def close(self) -> None:
        """关闭 scheduler 并 best-effort 收尾 active workers。

        :returns: ``None``。
        """

        if self._closed:
            return
        self._closed = True
        task = self._drain_task
        if task is not None:
            task.cancel()
            await _suppress_task_cancel(task)
        for handle in tuple(self._active_handles):
            handle.cancel("scheduler_close")
            await handle.close()
        for active_task in tuple(self._active_tasks):
            active_task.cancel()
            await _suppress_task_cancel(active_task)
        await self._lane_controller.close(reason="scheduler_close")

    async def _drain_loop(self) -> None:
        """后台 drain 队列。

        :returns: ``None``。
        :raises asyncio.CancelledError: scheduler close 时透传取消。
        """

        while not self._closed:
            if self._queue.empty():
                await asyncio.sleep(
                    self._local_execution.dispatch_poll_interval_seconds
                )
                if self._queue.empty():
                    return
            await self.drain_once()

    async def _dispatch_one(self, record: PendingDispatchRecord) -> str:
        """处理一个 dispatch wakeup。

        :param record: pending dispatch 摘要。
        :returns: ``dispatched``、``skipped`` 或 ``timed_out``。
        """

        wait_row = self._mark_waiting_for_lane(record)
        if wait_row is None:
            return "skipped"
        acquire = await self._lane_controller.acquire(
            self._local_execution.lane_name,
            timeout_seconds=self._local_execution.lane_default_timeout_seconds,
        )
        if isinstance(acquire, LaneAcquireTimedOut):
            self._closeout_worker_startup_timeout(record)
            return "timed_out"
        if isinstance(acquire, LaneAcquireCancelled):
            return "skipped"
        if not isinstance(acquire, LaneAcquired):
            return "skipped"
        token = acquire.token
        dispatching_row = self._mark_dispatching_after_recheck(record, token)
        if dispatching_row is None:
            await token.release()
            return "skipped"
        await asyncio.sleep(0)
        if not self._dispatch_record_still_pre_accept(dispatching_row):
            await token.release()
            return "skipped"
        return await self._start_worker(record, dispatching_row, token)

    def _mark_waiting_for_lane(
        self, record: PendingDispatchRecord
    ) -> DispatchRecordRow | None:
        """把 pending dispatch 标记为 waiting_for_lane。

        :param record: pending dispatch 摘要。
        :returns: 可继续 dispatch 的 dispatch row；不可继续时为 ``None``。
        """

        def _operation(transaction: HostTransaction) -> DispatchRecordRow | None:
            latest = read_dispatch_record_by_id(
                transaction, record.dispatch_record_id
            )
            if latest is None:
                return None
            if latest.status == DispatchRecordStatus.WAITING_FOR_LANE:
                return latest
            result = mark_dispatch_waiting_for_lane_row(
                transaction,
                attempt_id=record.attempt_id,
                owner_host_instance_id=self._host_handle_id,
                lane_name=self._local_execution.lane_name,
                waiting_for_lane_at=format_utc_timestamp(datetime.now(UTC)),
            )
            if result.status == StateMutationStatus.UPDATED:
                return result.row
            return None

        return self._transaction_runner.run_write(_operation)

    def _mark_dispatching_after_recheck(
        self, record: PendingDispatchRecord, token: LaneClaimToken
    ) -> DispatchRecordRow | None:
        """lane acquired 后做 durable recheck 并标记 dispatching。

        :param record: pending dispatch 摘要。
        :param token: runtime lane token。
        :returns: dispatching row；前置不满足时为 ``None``。
        """

        def _operation(transaction: HostTransaction) -> DispatchRecordRow | None:
            run = read_run_by_id(transaction, record.run_id)
            attempt = read_attempt_by_id(transaction, record.attempt_id)
            dispatch_record = read_dispatch_record_by_id(
                transaction, record.dispatch_record_id
            )
            if not _is_dispatchable_recheck(
                run=run,
                attempt=attempt,
                dispatch_record=dispatch_record,
                record=record,
            ):
                return None
            result = mark_dispatching_after_lane_row(
                transaction,
                attempt_id=record.attempt_id,
                owner_host_instance_id=self._host_handle_id,
                lane_name=token.name,
                lane_claim_id=token.claim_id,
                lane_owner_id=token.owner.owner_id,
                lane_acquired_at=format_utc_timestamp(datetime.now(UTC)),
                dispatching_at=format_utc_timestamp(datetime.now(UTC)),
            )
            if result.status != StateMutationStatus.UPDATED:
                return None
            return result.row

        return self._transaction_runner.run_write(_operation)

    def _dispatch_record_still_pre_accept(
        self, dispatch_record: DispatchRecordRow
    ) -> bool:
        """确认 dispatching row 仍处于 worker accept 前。

        :param dispatch_record: dispatching row。
        :returns: 仍可调用 worker 时返回 ``True``。
        """

        def _operation(transaction: HostTransaction) -> bool:
            latest = read_dispatch_record_by_id(
                transaction, dispatch_record.dispatch_record_id
            )
            return (
                latest is not None
                and latest.status == DispatchRecordStatus.DISPATCHING
                and latest.worker_accept_event_id is None
                and latest.cancelled_event_id is None
            )

        return self._transaction_runner.run_read(_operation)

    async def _start_worker(
        self,
        record: PendingDispatchRecord,
        dispatch_record: DispatchRecordRow,
        token: LaneClaimToken,
    ) -> str:
        """构造 Engine request，调用 worker accept，并启动事件消费任务。

        :param record: pending dispatch 摘要。
        :param dispatch_record: dispatching row。
        :param token: runtime lane token。
        :returns: ``dispatched``、``skipped`` 或 ``timed_out``。
        """

        cancellation_token = _HostCancellationToken()
        snapshot = self._snapshot_from_dispatch(record, cancellation_token)
        request = create_no_tool_run_input_builder(
            transaction_runner=self._transaction_runner,
            policy_snapshot=PolicySnapshot(
                runner_spec=self._local_execution.runner_spec,
                runner_options=self._local_execution.runner_options,
                agent_policy=self._local_execution.agent_policy,
                policy_snapshot_ref=_LOCAL_POLICY_SNAPSHOT_REF,
            ),
        ).build(snapshot)
        worker = self._local_execution.worker_factory.create_worker(snapshot)
        try:
            handle = await asyncio.wait_for(
                worker.accept(snapshot, request),
                timeout=self._local_execution.worker_startup_timeout_seconds,
            )
        except TimeoutError:
            self._closeout_worker_startup_timeout(record)
            await token.release()
            return "timed_out"
        if not self._accept_worker_running(
            record=record,
            dispatch_record=dispatch_record,
            token=token,
            handle=handle,
        ):
            await handle.close()
            await token.release()
            return "skipped"
        self._active_registry.register(
            run_id=record.run_id,
            attempt_id=record.attempt_id,
            execution_id=record.execution_id,
            handle=handle,
            cancellation_token=cancellation_token,
        )
        task = asyncio.create_task(
            self._consume_worker_events(
                record=record,
                handle=handle,
                token=token,
                cancellation_token=cancellation_token,
            )
        )
        self._active_handles.add(handle)
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)
        return "dispatched"

    def _snapshot_from_dispatch(
        self, record: PendingDispatchRecord, cancellation_token: _HostCancellationToken
    ) -> AttemptDispatchSnapshot:
        """从 durable dispatch row 构造 RunInputBuilder snapshot。

        :param record: pending dispatch 摘要。
        :param cancellation_token: Host 注入 Engine 的取消 token。
        :returns: Attempt dispatch snapshot。
        """

        token: CancellationToken = cancellation_token
        return AttemptDispatchSnapshot(
            session_id=self._read_run_session_id(record.run_id),
            run_id=record.run_id,
            attempt_id=record.attempt_id,
            execution_id=record.execution_id,
            dispatch_record_id=record.dispatch_record_id,
            execution_target=record.execution_target,
            policy_snapshot_ref=_LOCAL_POLICY_SNAPSHOT_REF,
            cancellation_token=token,
        )

    def _read_run_session_id(self, run_id: str) -> str:
        """读取 Run 所属 Session id。

        :param run_id: Run id。
        :returns: Session id。
        :raises RuntimeError: Run 缺失时抛出。
        """

        def _operation(transaction: HostTransaction) -> str:
            run = read_run_by_id(transaction, run_id)
            if run is None:
                raise RuntimeError("dispatch Run is missing")
            return run.session_id

        return self._transaction_runner.run_read(_operation)

    def _accept_worker_running(
        self,
        *,
        record: PendingDispatchRecord,
        dispatch_record: DispatchRecordRow,
        token: LaneClaimToken,
        handle: LocalWorkerHandle,
    ) -> bool:
        """worker accept 后追加 ``ATTEMPT_RUNNING`` 并推进 Attempt。

        :param record: pending dispatch 摘要。
        :param dispatch_record: dispatching row。
        :param token: runtime lane token。
        :param handle: accepted worker handle。
        :returns: durable transition 成功时返回 ``True``。
        """

        accepted_at = datetime.now(UTC)
        accepted_at_text = format_utc_timestamp(accepted_at)

        def _operation(transaction: HostTransaction) -> bool:
            run = read_run_by_id(transaction, record.run_id)
            attempt = read_attempt_by_id(transaction, record.attempt_id)
            latest_dispatch = read_dispatch_record_by_attempt_id(
                transaction, record.attempt_id
            )
            if not _is_worker_acceptable(
                run=run,
                attempt=attempt,
                dispatch_record=latest_dispatch,
                record=record,
                original_dispatch_record=dispatch_record,
            ):
                return False
            if run is None or attempt is None or latest_dispatch is None:
                return False
            event = self._event_log_store.append_event(
                transaction,
                _attempt_running_event_request(
                    event_id=_new_event_id(_EVENT_ID_ATTEMPT_RUNNING_PREFIX),
                    occurred_at=accepted_at,
                    accepted_at_text=accepted_at_text,
                    run=run,
                    attempt=attempt,
                    dispatch_record=latest_dispatch,
                    local_worker_id=handle.local_worker_id,
                    lane_name=token.name,
                    lane_claim_id=token.claim_id,
                ),
            ).row
            attempt_result = mark_attempt_running_row(
                transaction,
                attempt_id=record.attempt_id,
                updated_at=accepted_at_text,
            )
            dispatch_result = mark_dispatch_worker_accepted_row(
                transaction,
                attempt_id=record.attempt_id,
                worker_accept_event_id=event.event_id,
                worker_accept_event_sequence=event.event_sequence,
                worker_accepted_at=accepted_at_text,
            )
            return (
                attempt_result.status == StateMutationStatus.UPDATED
                and dispatch_result.status == StateMutationStatus.UPDATED
            )

        return self._transaction_runner.run_write(_operation)

    def _closeout_worker_startup_timeout(
        self, record: PendingDispatchRecord
    ) -> None:
        """worker accept timeout 后关闭 STARTING Attempt。

        :param record: pending dispatch 摘要。
        :returns: ``None``。
        """

        def _operation(transaction: HostTransaction) -> None:
            terminal_closeout_in_transaction(
                transaction,
                self._event_log_store,
                TerminalCloseoutInput(
                    run_id=record.run_id,
                    attempt_id=record.attempt_id,
                    attempt_terminal_event_id=_new_event_id(
                        _EVENT_ID_ATTEMPT_FAILED_PREFIX
                    ),
                    run_terminal_event_id=_new_event_id(_EVENT_ID_RUN_FAILED_PREFIX),
                    attempt_terminal_status=AttemptStatus.FAILED,
                    run_terminal_status=RunStatus.FAILED,
                    occurred_at=datetime.now(UTC),
                    actor=_EVENT_ACTOR,
                    source=_EVENT_SOURCE,
                    reason=_WORKER_STARTUP_TIMEOUT_REASON,
                    terminal_summary_ref=None,
                    terminal_summary_digest=None,
                ),
            )

        self._transaction_runner.run_write(_operation)

    async def _consume_worker_events(
        self,
        *,
        record: PendingDispatchRecord,
        handle: LocalWorkerHandle,
        token: LaneClaimToken,
        cancellation_token: _HostCancellationToken,
    ) -> None:
        """消费 worker EngineEvent stream 并在结束时释放 lane。

        :param record: pending dispatch 摘要。
        :param handle: worker handle。
        :param token: runtime lane token。
        :param cancellation_token: Host 注入 Engine 的取消 token。
        :returns: ``None``。
        """

        envelope = LocalEngineEnvelope(
            session_id=self._read_run_session_id(record.run_id),
            run_id=record.run_id,
            attempt_id=record.attempt_id,
            execution_id=record.execution_id,
            dispatch_record_id=record.dispatch_record_id,
            worker_kind=record.worker_kind,
            execution_target=record.execution_target,
            local_worker_id=handle.local_worker_id,
            cancellation_token=cancellation_token,
        )
        ingestor = EngineEventIngestor(
            transaction_runner=self._transaction_runner,
            wakeup_port=self,
        )
        worker_event_index = 0
        terminal_seen = False
        last_accepted_event_id: str | None = None
        try:
            events = handle.events()
            while True:
                try:
                    event = await anext(events)
                except StopAsyncIteration:
                    if not terminal_seen:
                        ingestor.close_clean_eof(
                            envelope,
                            observed_at=datetime.now(UTC),
                            last_observed_worker_event_index=worker_event_index,
                        )
                    break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    ingestor.close_worker_lost(
                        envelope,
                        observed_at=datetime.now(UTC),
                        worker_lifecycle_signal="worker_stream_error",
                        stream_error_code=exc.__class__.__name__,
                        last_observed_worker_event_index=worker_event_index,
                        last_accepted_event_id=last_accepted_event_id,
                    )
                    break
                worker_event_index += 1
                result = ingestor.ingest(
                    EngineEventCandidate(
                        envelope=envelope,
                        worker_event_index=worker_event_index,
                        engine_event=event,
                        observed_at=datetime.now(UTC),
                    )
                )
                if result.status in (
                    EngineIngestStatus.ACCEPTED,
                    EngineIngestStatus.DUPLICATE,
                ):
                    if result.events:
                        last_accepted_event_id = result.events[-1].event_id
                    if result.terminal_closeout:
                        terminal_seen = True
        finally:
            self._active_handles.discard(handle)
            self._active_registry.unregister(
                attempt_id=record.attempt_id,
                execution_id=record.execution_id,
            )
            await handle.close()
            await token.release()


def _is_dispatchable_recheck(
    *,
    run: RunRow | None,
    attempt: AttemptRow | None,
    dispatch_record: DispatchRecordRow | None,
    record: PendingDispatchRecord,
) -> bool:
    """判断 lane acquired 后 durable facts 是否仍可 dispatch。

    :param run: Run row。
    :param attempt: Attempt row。
    :param dispatch_record: dispatch row。
    :param record: pending dispatch 摘要。
    :returns: 可 dispatch 时返回 ``True``。
    """

    return (
        run is not None
        and attempt is not None
        and dispatch_record is not None
        and run.status == RunStatus.RUNNING
        and run.current_attempt_id == record.attempt_id
        and attempt.status == AttemptStatus.STARTING
        and attempt.execution_id == record.execution_id
        and dispatch_record.status == DispatchRecordStatus.WAITING_FOR_LANE
        and dispatch_record.dispatch_record_id == record.dispatch_record_id
        and dispatch_record.execution_id == record.execution_id
        and dispatch_record.worker_accept_event_id is None
        and dispatch_record.cancelled_event_id is None
    )


def _is_worker_acceptable(
    *,
    run: RunRow | None,
    attempt: AttemptRow | None,
    dispatch_record: DispatchRecordRow | None,
    record: PendingDispatchRecord,
    original_dispatch_record: DispatchRecordRow,
) -> bool:
    """判断 worker accept transition 是否仍可提交。

    :param run: Run row。
    :param attempt: Attempt row。
    :param dispatch_record: 最新 dispatch row。
    :param record: pending dispatch 摘要。
    :param original_dispatch_record: worker 调用前的 dispatch row。
    :returns: 可提交 accept 时返回 ``True``。
    """

    return (
        run is not None
        and attempt is not None
        and dispatch_record is not None
        and run.status == RunStatus.RUNNING
        and run.current_attempt_id == record.attempt_id
        and attempt.status == AttemptStatus.STARTING
        and attempt.execution_id == record.execution_id
        and dispatch_record.status == DispatchRecordStatus.DISPATCHING
        and dispatch_record.dispatch_record_id
        == original_dispatch_record.dispatch_record_id
        and dispatch_record.worker_accept_event_id is None
        and dispatch_record.cancelled_event_id is None
    )


def _attempt_running_event_request(
    *,
    event_id: str,
    occurred_at: datetime,
    accepted_at_text: str,
    run: RunRow,
    attempt: AttemptRow,
    dispatch_record: DispatchRecordRow,
    local_worker_id: str,
    lane_name: str,
    lane_claim_id: str,
) -> EventLogAppendRequest:
    """构造 ``ATTEMPT_RUNNING`` 事件。

    :param event_id: 事件 id。
    :param occurred_at: 事件发生时间。
    :param accepted_at_text: worker accept timestamp 文本。
    :param run: Run row。
    :param attempt: Attempt row。
    :param dispatch_record: dispatch row。
    :param local_worker_id: 本地 worker id。
    :param lane_name: lane 名称。
    :param lane_claim_id: lane claim id。
    :returns: EventLog append request。
    """

    payload: dict[str, JsonValue] = {
        "attempt_id": attempt.attempt_id,
        "execution_id": attempt.execution_id,
        "dispatch_record_id": dispatch_record.dispatch_record_id,
        "worker_kind": _worker_kind_text(dispatch_record.worker_kind),
        "execution_target": dispatch_record.execution_target,
        "local_worker_id": local_worker_id,
        "worker_accepted_at": accepted_at_text,
        "lane_name": lane_name,
        "lane_claim_id": lane_claim_id,
        "reason": _WORKER_ACCEPT_REASON,
    }
    return EventLogAppendRequest(
        event_id=event_id,
        event_class=EventClass.CANONICAL_FACT,
        session_id=run.session_id,
        run_id=run.run_id,
        attempt_id=attempt.attempt_id,
        execution_id=attempt.execution_id,
        event_type=_EVENT_TYPE_ATTEMPT_RUNNING,
        occurred_at=occurred_at,
        actor=_EVENT_ACTOR,
        source=_EVENT_SOURCE,
        client_request_id=None,
        idempotency_key=None,
        policy_decision=None,
        reason={"reason": _WORKER_ACCEPT_REASON},
        payload_json=payload,
        payload_ref=None,
        payload_digest=None,
    )


def _worker_kind_text(worker_kind: WorkerKind) -> str:
    """序列化 worker kind。

    :param worker_kind: worker kind enum。
    :returns: schema 文本值。
    """

    return worker_kind.value


def _new_event_id(prefix: str) -> str:
    """生成事件 id。

    :param prefix: id 前缀。
    :returns: 新事件 id。
    """

    return f"{prefix}-{uuid4().hex}"


def _register_dispatch_host_instance(
    *,
    transaction_runner: HostTransactionRunner,
    host_handle_id: str,
) -> None:
    """注册 dispatch owner_host_instance_id 的 FK 诊断 row。

    :param transaction_runner: Host durable transaction runner。
    :param host_handle_id: Host handle 诊断 id。
    :returns: ``None``。
    """

    identity = HostInstanceIdentity(
        host_instance_id=host_handle_id,
        pid=os.getpid(),
        process_start_token=f"dispatch-{host_handle_id}",
        boot_id=None,
    )

    def _operation(transaction: HostTransaction) -> None:
        register_current_instance(transaction, identity)

    transaction_runner.run_write(_operation)


async def _suppress_task_cancel(task: asyncio.Task[None]) -> None:
    """等待 task 结束并吞掉取消异常。

    :param task: 待等待 task。
    :returns: ``None``。
    """

    try:
        await task
    except asyncio.CancelledError:
        return


__all__ = [
    "ActiveCancelMessage",
    "ActiveWorkerRegistry",
    "DEFAULT_ACTIVE_WORKER_REGISTRY",
    "DispatchDrainResult",
    "HostDispatchScheduler",
    "cancel_active_worker",
]
