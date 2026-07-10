"""Host Phase 5 本地执行 terminal closeout 集成测试。"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.error_codes import adapter_error_code
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    RunCancelledData,
    RunFailedData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
from dayu.host import (
    AuthorizationClaim,
    CancelRunRequest,
    HostCallContext,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
    OperationContext,
    cancel_run,
    ensure_session as ensure_public_session,
)
from dayu.host.admission import PendingDispatchRecord
from dayu.host.api import (
    HostInput,
    AttemptDispatchSnapshot,
    AttemptStatus,
    CancelMode,
    EnsureSessionRequest,
    HostCommandHandleOptions,
    HostLocalExecutionOptions,
    RunStatus,
    StartRunRequest,
)
from dayu.host.command import HostCommandHandle, create_host_command_handle, start_run
from dayu.host.dispatch import ActiveWorkerRegistry, HostDispatchScheduler
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.connection import HostDurableStore, open_host_durable_store
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.liveness import (
    HostInstanceIdentity,
    register_current_instance,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.run_transition import (
    AcceptWorkerRunningInput,
    CancelActiveAttemptInput,
    CreateRunningRunInput,
    accept_worker_running_in_transaction,
    create_running_run_with_starting_attempt_in_transaction,
    request_active_attempt_cancel_in_transaction,
)
from dayu.host.durable.session_lifecycle import ensure_session
from dayu.host.durable.state import (
    RunStartReason,
    WorkerKind,
    mark_dispatch_waiting_for_lane_row,
    mark_dispatching_after_lane_row,
    read_attempt_by_id,
    read_run_by_id,
)
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.engine_ingest import (
    EngineEventCandidate,
    EngineEventIngestor,
    EngineIngestStatus,
    LocalEngineEnvelope,
)

_NOW = datetime(2026, 5, 15, 1, 2, 3, tzinfo=UTC)
_CALL_CONTEXT_DIGEST = sha256_digest_json({"context": "phase5-integration-test"})
_LANE_NAME = "llm"
_WORKER_MODE_FINAL = "final"
_WORKER_MODE_FAILED = "failed"
_WORKER_MODE_EOF = "eof"
_WORKER_MODE_CRASH = "crash"
_WORKER_MODE_CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class _SeededRun:
    """测试中创建的 active Engine run。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


@dataclass(frozen=True, slots=True)
class _RunRefs:
    """public start_run 创建出的 Run durable 引用。"""

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    dispatch_record_id: str


@dataclass(frozen=True, slots=True)
class _AcceptedPublicRun:
    """public start_run 创建出的 pre-start Run 引用。"""

    session_id: str
    run_id: str


class _OpenCancellationToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回取消状态。

        :returns: 始终为 ``False``。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 始终为 ``None``。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 始终为 ``None``。
        """

        return None


class _WakeupSpy:
    """测试用 wakeup port。"""

    def __init__(self) -> None:
        """初始化 spy。

        :returns: ``None``。
        """

        self.promoted_session_ids: list[str] = []

    def wake_dispatch(self, record: PendingDispatchRecord) -> None:
        """忽略 dispatch wakeup。

        :param record: pending dispatch record。
        :returns: ``None``。
        """

        del record

    def wake_queue_promotion(self, session_id: str) -> None:
        """记录 queue promotion wakeup。

        :param session_id: Session id。
        :returns: ``None``。
        """

        self.promoted_session_ids.append(session_id)


class _ScriptedLocalWorkerHandle:
    """P5-S6 端到端测试用 fake local worker handle。"""

    def __init__(self, *, local_worker_id: str, mode: str) -> None:
        """初始化 fake worker handle。

        :param local_worker_id: 本地 worker 诊断 id。
        :param mode: worker 事件脚本模式。
        :returns: ``None``。
        """

        self._local_worker_id = local_worker_id
        self._mode = mode
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
        """按脚本模式产出 fake EngineEvent stream。

        :returns: EngineEvent 异步迭代器。
        :raises RuntimeError: ``crash`` 模式模拟 worker event stream 异常。
        """

        if self._mode == _WORKER_MODE_FINAL:
            yield EngineEvent(
                occurred_at=_NOW,
                session_id=self._bound_session_id(),
                run_id=self._bound_run_id(),
                type=EngineEventType.FINAL_ANSWER,
                data=FinalAnswerData(
                    content="phase5 final",
                    filtered=False,
                    degraded=False,
                    finish_reason=FinishReason.STOP,
                ),
                metadata=None,
            )
            return
        if self._mode == _WORKER_MODE_FAILED:
            yield EngineEvent(
                occurred_at=_NOW,
                session_id=self._bound_session_id(),
                run_id=self._bound_run_id(),
                type=EngineEventType.RUN_FAILED,
                data=RunFailedData(
                    error_code=adapter_error_code("fake_worker_failed"),
                    message="fake worker failed",
                    provider_request_id=None,
                    recoverable=False,
                ),
                metadata=None,
            )
            return
        if self._mode == _WORKER_MODE_EOF:
            return
        if self._mode == _WORKER_MODE_CRASH:
            raise RuntimeError("fake worker crash")
        await self._cancelled.wait()
        if self._mode == _WORKER_MODE_CANCELLED:
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
        """记录取消请求并唤醒脚本事件流。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        self.cancel_reasons.append(reason)
        self._cancelled.set()

    async def close(self) -> None:
        """关闭 fake worker。

        :returns: ``None``。
        """

        self.closed = True

    def bind_snapshot(self, snapshot: AttemptDispatchSnapshot) -> None:
        """绑定 worker accept 时的 Host dispatch identity。

        :param snapshot: dispatch snapshot。
        :returns: ``None``。
        """

        self._session_id = snapshot.session_id
        self._run_id = snapshot.run_id

    def _bound_session_id(self) -> str:
        """返回绑定后的 Session id。

        :returns: Session id。
        :raises RuntimeError: worker 尚未绑定 snapshot 时抛出。
        """

        if self._session_id is None:
            raise RuntimeError("fake worker session id is not bound")
        return self._session_id

    def _bound_run_id(self) -> str:
        """返回绑定后的 Run id。

        :returns: Run id。
        :raises RuntimeError: worker 尚未绑定 snapshot 时抛出。
        """

        if self._run_id is None:
            raise RuntimeError("fake worker run id is not bound")
        return self._run_id


class _ScriptedLocalWorker:
    """P5-S6 fake local worker。"""

    def __init__(self, handle: _ScriptedLocalWorkerHandle) -> None:
        """初始化 fake worker。

        :param handle: accept 后返回的 worker handle。
        :returns: ``None``。
        """

        self._handle = handle

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """接受本地执行请求。

        :param snapshot: dispatch snapshot。
        :param request: RunInputBuilder 生成的 Engine request。
        :returns: fake worker handle。
        """

        assert request.disable_tools is True
        assert request.tool_schemas == ()
        self._handle.bind_snapshot(snapshot)
        return self._handle


class _SequencedLocalWorkerFactory:
    """按顺序返回 fake local worker handle 的 factory。"""

    def __init__(self, handles: tuple[_ScriptedLocalWorkerHandle, ...]) -> None:
        """初始化 factory。

        :param handles: 每次 dispatch 使用的 handle 序列。
        :returns: ``None``。
        """

        self._handles = handles
        self.created = 0

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 fake local worker。

        :param snapshot: dispatch snapshot。
        :returns: fake local worker。
        :raises RuntimeError: handle 序列耗尽时抛出。
        """

        del snapshot
        if self.created >= len(self._handles):
            raise RuntimeError("fake worker handles are exhausted")
        handle = self._handles[self.created]
        self.created += 1
        return _ScriptedLocalWorker(handle)


@pytest.mark.asyncio
async def test_start_run_fake_worker_final_answer_succeeds(
    tmp_path: Path,
) -> None:
    """public start_run 经 fake local worker final_answer 收口为 SUCCEEDED。"""

    options = _command_options(tmp_path)
    host = create_host_command_handle(options)
    handle = _ScriptedLocalWorkerHandle(
        local_worker_id="worker-final-answer",
        mode=_WORKER_MODE_FINAL,
    )
    try:
        accepted = _accept_public_run(host, "start-final-answer")
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                _SequencedLocalWorkerFactory((handle,)),
            )
            try:
                await scheduler.run_queue_promotion(accepted.session_id)
                refs = _refs(options.db_path, accepted.run_id)
                drain = await scheduler.drain_once()
                assert drain.dispatched == 1
                await _wait_for_run_status(
                    options.db_path,
                    refs.run_id,
                    RunStatus.SUCCEEDED,
                )
                assert _attempt_status(options.db_path, refs.attempt_id) == (
                    AttemptStatus.SUCCEEDED
                )
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_start_run_fake_worker_run_failed_fails(tmp_path: Path) -> None:
    """public start_run 经 fake worker run_failed 收口为 FAILED。"""

    options = _command_options(tmp_path)
    host = create_host_command_handle(options)
    handle = _ScriptedLocalWorkerHandle(
        local_worker_id="worker-run-failed",
        mode=_WORKER_MODE_FAILED,
    )
    try:
        accepted = _accept_public_run(host, "start-run-failed")
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                _SequencedLocalWorkerFactory((handle,)),
            )
            try:
                await scheduler.run_queue_promotion(accepted.session_id)
                refs = _refs(options.db_path, accepted.run_id)
                assert (await scheduler.drain_once()).dispatched == 1
                await _wait_for_run_status(
                    options.db_path,
                    refs.run_id,
                    RunStatus.FAILED,
                )
                assert _attempt_status(options.db_path, refs.attempt_id) == (
                    AttemptStatus.FAILED
                )
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_start_run_fake_worker_clean_eof_fails(tmp_path: Path) -> None:
    """public start_run 经 fake worker clean EOF 收口为 FAILED。"""

    options = _command_options(tmp_path)
    host = create_host_command_handle(options)
    handle = _ScriptedLocalWorkerHandle(
        local_worker_id="worker-clean-eof",
        mode=_WORKER_MODE_EOF,
    )
    try:
        accepted = _accept_public_run(host, "start-clean-eof")
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                _SequencedLocalWorkerFactory((handle,)),
            )
            try:
                await scheduler.run_queue_promotion(accepted.session_id)
                refs = _refs(options.db_path, accepted.run_id)
                assert (await scheduler.drain_once()).dispatched == 1
                await _wait_for_run_status(
                    options.db_path,
                    refs.run_id,
                    RunStatus.FAILED,
                )
                assert _attempt_status(options.db_path, refs.attempt_id) == (
                    AttemptStatus.FAILED
                )
                assert _event_type_count(options.db_path, "RUN_FAILED") == 1
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_start_run_fake_worker_crash_loses(tmp_path: Path) -> None:
    """public start_run 经 fake worker stream crash 收口为 LOST。"""

    options = _command_options(tmp_path)
    host = create_host_command_handle(options)
    handle = _ScriptedLocalWorkerHandle(
        local_worker_id="worker-crash",
        mode=_WORKER_MODE_CRASH,
    )
    try:
        accepted = _accept_public_run(host, "start-crash")
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                _SequencedLocalWorkerFactory((handle,)),
            )
            try:
                await scheduler.run_queue_promotion(accepted.session_id)
                refs = _refs(options.db_path, accepted.run_id)
                assert (await scheduler.drain_once()).dispatched == 1
                await _wait_for_run_status(
                    options.db_path,
                    refs.run_id,
                    RunStatus.LOST,
                )
                assert _attempt_status(options.db_path, refs.attempt_id) == (
                    AttemptStatus.LOST
                )
                assert _event_type_count(options.db_path, "RUN_LOST") == 1
            finally:
                await scheduler.close()
    finally:
        host.close()


@pytest.mark.asyncio
async def test_cancel_active_fake_worker_closes_cancelled(tmp_path: Path) -> None:
    """active fake local worker 收到 cancel 后以 RUN_CANCELLED 收口。"""

    options = _command_options(tmp_path)
    active_registry = ActiveWorkerRegistry()
    host = create_host_command_handle(options, active_registry=active_registry)
    handle = _ScriptedLocalWorkerHandle(
        local_worker_id="worker-cancelled",
        mode=_WORKER_MODE_CANCELLED,
    )
    try:
        accepted = _accept_public_run(host, "start-cancel-active")
        with open_host_durable_store(_durable_options(tmp_path)) as store:
            scheduler = await _open_scheduler(
                tmp_path,
                store,
                _SequencedLocalWorkerFactory((handle,)),
                active_registry=active_registry,
            )
            try:
                await scheduler.run_queue_promotion(accepted.session_id)
                refs = _refs(options.db_path, accepted.run_id)
                assert (await scheduler.drain_once()).dispatched == 1
                assert _attempt_status(options.db_path, refs.attempt_id) == (
                    AttemptStatus.RUNNING
                )

                cancelling = cancel_run(
                    host,
                    refs.run_id,
                    _cancel_run_request("cancel-active-fake"),
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
async def test_queue_promotion_after_terminal_and_cancel_wakes_dispatch(
    tmp_path: Path,
) -> None:
    """terminal 与 cancel 释放 active slot 后继续唤醒 promoted dispatch。"""

    terminal_options = _command_options(tmp_path / "terminal")
    terminal_host = create_host_command_handle(terminal_options)
    first_terminal = _ScriptedLocalWorkerHandle(
        local_worker_id="worker-terminal-first",
        mode=_WORKER_MODE_FINAL,
    )
    promoted_terminal = _ScriptedLocalWorkerHandle(
        local_worker_id="worker-terminal-promoted",
        mode=_WORKER_MODE_FINAL,
    )
    try:
        terminal_session_id = _session_id(terminal_host)
        terminal_active = start_run(
            terminal_host,
            _start_request(terminal_session_id, "start-terminal-active"),
        )
        terminal_queued = start_run(
            terminal_host,
            _start_request(terminal_session_id, "start-terminal-queued"),
        )
        with open_host_durable_store(
            _durable_options(tmp_path / "terminal")
        ) as store:
            scheduler = await _open_scheduler(
                tmp_path / "terminal",
                store,
                _SequencedLocalWorkerFactory(
                    (first_terminal, promoted_terminal)
                ),
            )
            try:
                await scheduler.run_queue_promotion(terminal_session_id)
                terminal_refs = _refs(
                    terminal_options.db_path, terminal_active.run_id
                )
                assert (await scheduler.drain_once()).dispatched == 1
                await _wait_for_run_status(
                    terminal_options.db_path,
                    terminal_queued.run_id,
                    RunStatus.SUCCEEDED,
                )
                assert _event_type_count(
                    terminal_options.db_path, "ATTEMPT_RUNNING"
                ) == 2
            finally:
                await scheduler.close()
    finally:
        terminal_host.close()

    cancel_options = _command_options(tmp_path / "cancel")
    active_registry = ActiveWorkerRegistry()
    cancel_host = create_host_command_handle(
        cancel_options, active_registry=active_registry
    )
    first_cancel = _ScriptedLocalWorkerHandle(
        local_worker_id="worker-cancel-first",
        mode=_WORKER_MODE_CANCELLED,
    )
    promoted_cancel = _ScriptedLocalWorkerHandle(
        local_worker_id="worker-cancel-promoted",
        mode=_WORKER_MODE_FINAL,
    )
    try:
        cancel_session_id = _session_id(cancel_host)
        cancel_active = start_run(
            cancel_host,
            _start_request(cancel_session_id, "start-cancel-active"),
        )
        cancel_queued = start_run(
            cancel_host,
            _start_request(cancel_session_id, "start-cancel-queued"),
        )
        with open_host_durable_store(_durable_options(tmp_path / "cancel")) as store:
            scheduler = await _open_scheduler(
                tmp_path / "cancel",
                store,
                _SequencedLocalWorkerFactory((first_cancel, promoted_cancel)),
                active_registry=active_registry,
            )
            try:
                await scheduler.run_queue_promotion(cancel_session_id)
                cancel_refs = _refs(cancel_options.db_path, cancel_active.run_id)
                assert (await scheduler.drain_once()).dispatched == 1
                cancelling = cancel_run(
                    cancel_host,
                    cancel_refs.run_id,
                    _cancel_run_request("cancel-promote-active"),
                )
                assert cancelling.status == RunStatus.CANCELLING
                await _wait_for_run_status(
                    cancel_options.db_path,
                    cancel_refs.run_id,
                    RunStatus.CANCELLED,
                )
                await _wait_for_run_status(
                    cancel_options.db_path,
                    cancel_queued.run_id,
                    RunStatus.SUCCEEDED,
                )
                assert _event_type_count(
                    cancel_options.db_path, "ATTEMPT_RUNNING"
                ) == 2
            finally:
                await scheduler.close()
    finally:
        cancel_host.close()


def test_clean_eof_without_terminal_closes_failed(tmp_path: Path) -> None:
    """clean EOF without terminal 收口为 FAILED，重复 closeout 会重试 promotion。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        wakeup = _WakeupSpy()
        ingestor = EngineEventIngestor(
            transaction_runner=store.transaction_runner,
            wakeup_port=wakeup,
        )
        result = ingestor.close_clean_eof(
            _envelope(seeded),
            observed_at=_NOW,
            last_observed_worker_event_index=0,
        )

        assert result.status == EngineIngestStatus.ACCEPTED
        assert [event.event_type for event in result.events] == [
            "ATTEMPT_FAILED",
            "RUN_FAILED",
        ]
        assert _payload(result.events[0])["reason"] == "stream_ended_without_terminal"
        assert _statuses(store.transaction_runner, seeded) == (
            RunStatus.FAILED,
            AttemptStatus.FAILED,
        )
        duplicate = ingestor.close_clean_eof(
            _envelope(seeded),
            observed_at=_NOW,
            last_observed_worker_event_index=0,
        )
        assert duplicate.status == EngineIngestStatus.DUPLICATE
        assert duplicate.promotion_triggered is True
        assert wakeup.promoted_session_ids == [
            seeded.session_id,
            seeded.session_id,
        ]


def test_stream_error_or_worker_crash_closes_lost(tmp_path: Path) -> None:
    """stream error / worker crash 收口为 LOST。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner
        ).close_worker_lost(
            _envelope(seeded),
            observed_at=_NOW,
            worker_lifecycle_signal="worker_crash",
            stream_error_code="broken_stream",
            last_observed_worker_event_index=1,
            last_accepted_event_id="event-preview-last",
        )

        assert [event.event_type for event in result.events] == [
            "ATTEMPT_LOST",
            "RUN_LOST",
        ]
        payload = _payload(result.events[0])
        assert payload["reason"] == "worker_lost_before_terminal"
        assert payload["worker_lifecycle_signal"] == "worker_crash"
        assert _statuses(store.transaction_runner, seeded) == (
            RunStatus.LOST,
            AttemptStatus.LOST,
        )


def test_run_cancelled_after_active_cancel_closes_cancelled(tmp_path: Path) -> None:
    """active cancel 后的 run_cancelled 收口为 CANCELLED。"""

    with open_host_durable_store(_options(tmp_path)) as store:
        seeded = _seed_active_run(store.transaction_runner)
        _request_active_cancel(store.transaction_runner, seeded)
        candidate = EngineEventCandidate(
            envelope=_envelope(seeded),
            worker_event_index=2,
            engine_event=EngineEvent(
                occurred_at=_NOW,
                session_id=seeded.session_id,
                run_id=seeded.run_id,
                type=EngineEventType.RUN_CANCELLED,
                data=RunCancelledData(
                    reason="user_stop",
                    requested_at=_NOW,
                    accepted_at=_NOW,
                    finished_at=_NOW,
                ),
                metadata=None,
            ),
            observed_at=_NOW,
        )

        result = EngineEventIngestor(
            transaction_runner=store.transaction_runner
        ).ingest(candidate)

        assert result.status == EngineIngestStatus.ACCEPTED
        assert [event.event_type for event in result.events] == [
            "ATTEMPT_CANCELLED",
            "RUN_CANCELLED",
        ]
        payload = _payload(result.events[0])
        assert payload["cancel_request_event_id"] == "event-cancel-requested-active"
        assert _statuses(store.transaction_runner, seeded) == (
            RunStatus.CANCELLED,
            AttemptStatus.CANCELLED,
        )


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


def _seed_active_run(transaction_runner: HostTransactionRunner) -> _SeededRun:
    """创建已 worker accepted 的 active Run。

    :param transaction_runner: Host transaction runner。
    :returns: seeded run。
    """

    session_id = ensure_session(
        transaction_runner,
        EnsureSessionRequest(scope="workspace", slot_key="phase5-local", metadata=()),
    ).snapshot.session_id
    seeded = _SeededRun(
        session_id=session_id,
        run_id="run-phase5-local",
        attempt_id="attempt-phase5-local",
        execution_id="execution-phase5-local",
        dispatch_record_id="dispatch-phase5-local",
    )

    def _operation(transaction: HostTransaction) -> None:
        register_current_instance(
            transaction,
            HostInstanceIdentity(
                host_instance_id="host-test",
                pid=1,
                process_start_token="test-process",
                boot_id=None,
            ),
        )
        input_event = (
            EventLogStore()
            .append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="event-input-phase5-local",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=session_id,
                    run_id=seeded.run_id,
                    attempt_id=None,
                    execution_id=None,
                    event_type="USER_INPUT_ACCEPTED",
                    occurred_at=_NOW,
                    actor="tester",
                    source="pytest",
                    client_request_id="client-phase5-local",
                    idempotency_key="idem-phase5-local-input",
                    policy_decision=None,
                    reason=None,
                    payload_json={"display_text": "hello"},
                    payload_ref=None,
                    payload_digest=None,
                ),
            )
            .row
        )
        create_running_run_with_starting_attempt_in_transaction(
            transaction,
            EventLogStore(),
            CreateRunningRunInput(
                session_id=session_id,
                run_id=seeded.run_id,
                client_request_id="client-phase5-local",
                input_event_id=input_event.event_id,
                input_event_sequence=input_event.event_sequence,
                run_accepted_event_id="event-run-accepted-phase5-local",
                run_started_event_id="event-run-started-phase5-local",
                attempt_started_event_id="event-attempt-started-phase5-local",
                attempt_id=seeded.attempt_id,
                execution_id=seeded.execution_id,
                dispatch_record_id=seeded.dispatch_record_id,
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                idempotency_key="idem-phase5-local",
                execution_target="target-phase5-local",
                queue_policy="queue",
                start_reason=RunStartReason.INITIAL,
                worker_kind=WorkerKind.LOCAL,
                owner_host_instance_id=None,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )
        mark_dispatch_waiting_for_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-test",
            lane_name="llm",
            waiting_for_lane_at="2026-05-15T01:02:03.000000Z",
        )
        mark_dispatching_after_lane_row(
            transaction,
            attempt_id=seeded.attempt_id,
            owner_host_instance_id="host-test",
            lane_name="llm",
            lane_claim_id="claim-test",
            lane_owner_id="owner-test",
            lane_acquired_at="2026-05-15T01:02:03.000000Z",
            dispatching_at="2026-05-15T01:02:03.000000Z",
        )
        accept_worker_running_in_transaction(
            transaction,
            EventLogStore(),
            AcceptWorkerRunningInput(
                run_id=seeded.run_id,
                attempt_id=seeded.attempt_id,
                attempt_running_event_id="event-attempt-running-phase5-local",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                worker_accept_reason="accepted",
            ),
        )

    transaction_runner.run_write(_operation)
    return seeded


def _request_active_cancel(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> None:
    """把 active Run 推进到 CANCELLING。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded run。
    :returns: ``None``。
    """

    def _operation(transaction: HostTransaction) -> None:
        request_active_attempt_cancel_in_transaction(
            transaction,
            EventLogStore(),
            CancelActiveAttemptInput(
                run_id=seeded.run_id,
                cancel_request_event_id="event-cancel-requested-active",
                run_cancelling_event_id="event-run-cancelling-active",
                occurred_at=_NOW,
                actor="tester",
                source="pytest",
                client_request_id="client-cancel-active",
                idempotency_key="idem-cancel-active",
                reason="user_stop",
                mode=CancelMode.GRACEFUL,
                call_context_digest=_CALL_CONTEXT_DIGEST,
            ),
        )

    transaction_runner.run_write(_operation)


def _envelope(seeded: _SeededRun) -> LocalEngineEnvelope:
    """构造 LocalEngineEnvelope。

    :param seeded: seeded run。
    :returns: envelope。
    """

    return LocalEngineEnvelope(
        session_id=seeded.session_id,
        run_id=seeded.run_id,
        attempt_id=seeded.attempt_id,
        execution_id=seeded.execution_id,
        dispatch_record_id=seeded.dispatch_record_id,
        worker_kind=WorkerKind.LOCAL,
        execution_target="target-phase5-local",
        local_worker_id="local-worker-phase5",
        cancellation_token=_OpenCancellationToken(),
    )


def _statuses(
    transaction_runner: HostTransactionRunner, seeded: _SeededRun
) -> tuple[RunStatus, AttemptStatus]:
    """读取 Run / Attempt 状态。

    :param transaction_runner: Host transaction runner。
    :param seeded: seeded run。
    :returns: Run 与 Attempt 状态。
    """

    def _operation(transaction: HostTransaction) -> tuple[RunStatus, AttemptStatus]:
        run = read_run_by_id(transaction, seeded.run_id)
        attempt = read_attempt_by_id(transaction, seeded.attempt_id)
        assert run is not None
        assert attempt is not None
        return run.status, attempt.status

    return transaction_runner.run_read(_operation)


def _payload(row: EventLogRow) -> Mapping[str, JsonValue]:
    """解析 EventLog payload。

    :param row: EventLog row。
    :returns: payload mapping。
    """

    value = cast(JsonValue, json.loads(row.payload_json))
    assert isinstance(value, Mapping)
    return cast(Mapping[str, JsonValue], value)


def _command_options(tmp_path: Path) -> HostCommandHandleOptions:
    """构造 public command handle options。

    :param tmp_path: pytest 临时目录。
    :returns: Host command handle options。
    """

    return HostCommandHandleOptions(
        host_handle_id="host-phase5-integration",
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
    """构造与 public handle 共用 DB 的 durable store options。

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
    worker_factory: LocalEngineWorkerFactory,
    *,
    active_registry: ActiveWorkerRegistry | None = None,
) -> HostDispatchScheduler:
    """打开 public/scheduler 集成测试 scheduler。

    :param tmp_path: pytest 临时目录。
    :param store: Host durable store。
    :param worker_factory: fake local worker factory。
    :param active_registry: 可选 active worker registry。
    :returns: 已打开的 dispatch scheduler。
    """

    return await HostDispatchScheduler.open(
        transaction_runner=store.transaction_runner,
        local_execution=HostLocalExecutionOptions(
            lane_db_path=tmp_path / "lane.sqlite3",
            lane_name=_LANE_NAME,
            lane_capacity=1,
            lane_default_timeout_seconds=0.5,
            lane_claim_ttl_seconds=1.0,
            lane_heartbeat_interval_seconds=0.1,
            worker_startup_timeout_seconds=1.0,
            dispatch_poll_interval_seconds=0.01,
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
            worker_factory=worker_factory,
        ),
        host_handle_id="host-phase5-integration",
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


def _accept_public_run(
    host: HostCommandHandle, client_request_id: str
) -> _AcceptedPublicRun:
    """通过 public facade 创建 ACCEPTED Run。

    :param host: Host command handle。
    :param client_request_id: start_run 幂等 id。
    :returns: accepted Run 引用。
    """

    session_id = _session_id(host)
    snapshot = start_run(host, _start_request(session_id, client_request_id))
    assert snapshot.status == RunStatus.ACCEPTED
    return _AcceptedPublicRun(session_id=session_id, run_id=snapshot.run_id)


def _session_id(host: HostCommandHandle) -> str:
    """确保测试 Session 存在。

    :param host: Host command handle。
    :returns: Session id。
    """

    return ensure_public_session(
        host,
        EnsureSessionRequest(scope="workspace", slot_key="slot-phase5", metadata=()),
    ).session_id


def _start_request(session_id: str, client_request_id: str) -> StartRunRequest:
    """构造 start_run 请求。

    :param session_id: Session id。
    :param client_request_id: start_run 幂等 id。
    :returns: StartRunRequest。
    """

    return StartRunRequest(
        context=_context(),
        session_id=session_id,
        client_request_id=client_request_id,
        input=HostInput(
            display_text=f"phase5 prompt {client_request_id}",
            payload_ref=None,
            payload_digest=None,
        ),
        execution_target="target-phase5-integration",
        queue_policy="queue",
    )


def _cancel_run_request(client_request_id: str) -> CancelRunRequest:
    """构造 cancel_run 请求。

    :param client_request_id: cancel 幂等 id。
    :returns: CancelRunRequest。
    """

    return CancelRunRequest(
        context=_context(),
        client_request_id=client_request_id,
        reason="user_stop",
        mode=CancelMode.GRACEFUL,
    )


def _context() -> HostCallContext:
    """构造测试 Host call context。

    :returns: HostCallContext。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id="trace-phase5-integration",
        authorization_claims=(AuthorizationClaim(name="role", value="research"),),
        operation_context=OperationContext(
            operation_name="phase5_local_execution_integration",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase5",
            correlation_id="corr-phase5-integration",
        ),
    )


def _refs(db_path: Path, run_id: str) -> _RunRefs:
    """读取 Run 对应 durable refs。

    :param db_path: SQLite DB 路径。
    :param run_id: Run id。
    :returns: Run durable refs。
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


def _pending_dispatch(refs: _RunRefs) -> PendingDispatchRecord:
    """构造 pending dispatch wakeup 摘要。

    :param refs: Run durable refs。
    :returns: PendingDispatchRecord。
    """

    return PendingDispatchRecord(
        dispatch_record_id=refs.dispatch_record_id,
        run_id=refs.run_id,
        attempt_id=refs.attempt_id,
        execution_id=refs.execution_id,
        execution_target="target-phase5-integration",
        worker_kind=WorkerKind.LOCAL,
    )


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


def _event_type_count(db_path: Path, event_type: str) -> int:
    """统计指定 EventLog 类型数量。

    :param db_path: SQLite DB 路径。
    :param event_type: event type。
    :returns: 指定事件类型 row 数。
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
