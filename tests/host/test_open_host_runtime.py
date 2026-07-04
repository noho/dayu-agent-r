"""P10.5 Slice 2 ``open_host`` production runtime 接线测试。"""

from __future__ import annotations

import asyncio
import pathlib
import sqlite3
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest

from dayu.contracts.tool_result import ToolResultSuccess
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
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
    FollowupBehavior,
    Host,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    HostEvent,
    HostEventKind,
    HostTerminalStatus,
    HostToolingOptions,
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
    OpenHostOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    PurgeSessionRequest,
    ResolveWaitCompletedOutcome,
    RunSnapshot,
    RunStatus,
    SubmitFollowupRequest,
    WaitAdapterKey,
    open_host,
)
from dayu.host.api import AuthorizationClaim, HostInput, HostLocalExecutionOptions
from dayu.host.command import HostCommandHandle, create_host_command_handle
from dayu.host.dispatch import ActiveWorkerRegistry, HostDispatchScheduler
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.outbox import read_outbox_terminal_items_after
from dayu.host.durable.state import WaitRecordRow
from dayu.host.durable.transaction import HostTransaction, HostTransactionRunner
from dayu.host.context_policy import default_context_budget_policy
from dayu.host.memory import default_memory_projection_policy
from dayu.host.open_host import (
    _CompositeProjectionCatchupPort,
    _PublicHostHandle,
    _command_options_from_open_host_options,
    _local_execution_options_from_open_host_options,
)
from dayu.host.llm_compaction import LLMContextCompactor
from dayu.host.projection import ProjectionCatchupPort
from dayu.host.recovery import StartupRecoveryScanner
from dayu.host.wait_adapter import (
    WaitExternalJobLifecycleResult,
    WaitPollAdapterRegistration,
    WaitPollAdapterRegistry,
    WaitPollReady,
    WaitPollResult,
    WaitPollerRuntimePolicy,
    WaitPollerSupervisor,
)
from tests.host.public_smoke_support import awaiting_tooling_options
from tests.host.test_resolve_wait_command import _seed_waiting_run

_SCHEDULER_CLOSE_FAILURE_MESSAGE = "scheduler close failed after cleanup"
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

    def poll_wait(self, wait_record: WaitRecordRow) -> WaitPollResult:
        """记录 poll 并返回 completed result。

        :param wait_record: wait record。
        :returns: ready poll result。
        """

        del wait_record
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
        self, wait_record: WaitRecordRow
    ) -> WaitExternalJobLifecycleResult:
        """本测试不处理 cancelled wait。

        :param wait_record: wait record。
        :returns: applied lifecycle result。
        :raises AssertionError: 被错误调用时抛出。
        """

        raise AssertionError(f"unexpected abandon {wait_record.wait_id}")


@pytest.mark.asyncio
async def test_submit_followup_queue_auto_wakes_scheduler(
    tmp_path: pathlib.Path,
) -> None:
    """public submit_followup(queue) 经 open_host 自动唤醒 scheduler 并完成 Run。"""

    factory = _FinalAnswerWorkerFactory()
    options = _options(tmp_path, factory)

    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        followup = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-auto-wakeup"),
        )

        final_run = await _wait_for_run_status(
            host, followup.accepted_run_id, RunStatus.SUCCEEDED
        )

    assert final_run.status == RunStatus.SUCCEEDED
    assert len(factory.accepted_snapshots) == 1
    assert factory.accepted_snapshots[0].run_id == followup.accepted_run_id
    assert factory.accepted_requests[0].disable_tools is True


@pytest.mark.asyncio
async def test_open_host_close_flushes_outbox_projection(
    tmp_path: pathlib.Path,
) -> None:
    """open_host close projection flush 包含 Outbox terminal projection。"""

    factory = _FinalAnswerWorkerFactory()
    options = _options(tmp_path, factory)

    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        followup = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-outbox-close-flush"),
        )
        await _wait_for_run_status(
            host,
            followup.accepted_run_id,
            RunStatus.SUCCEEDED,
        )

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
        followup = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-interrupted"),
        )
        await asyncio.wait_for(interrupted_factory.accepted_event.wait(), timeout=1)
        run_id = followup.accepted_run_id
        session_id = session.session_id

    _mark_current_dispatch_owner_as_stale_running(options, run_id)

    recovery_factory = _ControlledFinalAnswerWorkerFactory()
    async with open_host(replace(options, worker_factory=recovery_factory)) as host:
        watcher = host.watch_session_events(session_id)
        await asyncio.wait_for(recovery_factory.accepted_event.wait(), timeout=1)
        terminal_task = asyncio.create_task(_next_terminal(watcher))
        recovery_factory.release_event.set()
        terminal = await asyncio.wait_for(terminal_task, timeout=1)
        await _close_iterator(watcher)
        final_run = await _wait_for_run_status(host, run_id, RunStatus.SUCCEEDED)

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
async def test_open_host_startup_recovery_dispatches_gracefully_closed_run(
    tmp_path: pathlib.Path,
) -> None:
    """open_host 正常 close 后重启恢复已接受但未终态的 Run。"""

    interrupted_factory = _ControlledFinalAnswerWorkerFactory()
    options = _options(tmp_path, interrupted_factory)
    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        followup = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-graceful-close"),
        )
        await asyncio.wait_for(interrupted_factory.accepted_event.wait(), timeout=1)
        run_id = followup.accepted_run_id
        session_id = session.session_id

    recovery_factory = _ControlledFinalAnswerWorkerFactory()
    async with open_host(replace(options, worker_factory=recovery_factory)) as host:
        watcher = host.watch_session_events(session_id)
        await asyncio.wait_for(recovery_factory.accepted_event.wait(), timeout=1)
        terminal_task = asyncio.create_task(_next_terminal(watcher))
        recovery_factory.release_event.set()
        terminal = await asyncio.wait_for(terminal_task, timeout=1)
        await _close_iterator(watcher)
        final_run = await _wait_for_run_status(host, run_id, RunStatus.SUCCEEDED)

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
) -> None:
    """watchdog closeout 后 public watch 与 get_run 观察到 cancelled 终态。"""

    factory = _ControlledFinalAnswerWorkerFactory()
    options = _options(tmp_path, factory)
    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        followup = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "followup-active-cancel-watchdog"),
        )
        await asyncio.wait_for(factory.accepted_event.wait(), timeout=1)
        cancelling = await host.cancel_run(
            followup.accepted_run_id,
            _cancel_request("cancel-active-watchdog"),
        )
        watcher = host.watch_session_events(session.session_id)
        terminal_task = asyncio.create_task(_next_terminal(watcher))
        cast(_PublicHostHandle, host)._scheduler.tick_active_cancel_watchdog(
            datetime(2030, 1, 1, tzinfo=UTC)
        )
        terminal = await asyncio.wait_for(terminal_task, timeout=1)
        await _close_iterator(watcher)
        final_run = await host.get_run(followup.accepted_run_id)

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

    async with open_host(replace(options, worker_factory=_FinalAnswerWorkerFactory())) as host:
        snapshot = await host.get_run(run_id)

    assert snapshot.status is RunStatus.CANCELLED
    assert _event_type_count(options.db_path, "RUN_LOST") == 0
    assert _event_type_count(options.db_path, "RUN_CANCELLED") == 1


@pytest.mark.asyncio
async def test_public_host_close_closes_command_handle_when_scheduler_close_raises() -> None:
    """scheduler close 抛错时仍会追平 projection 并关闭 command handle。"""

    scheduler = _RaisingSchedulerClose()
    command_handle = _RecordingCommandHandleClose()
    projection_catchup_port = _RecordingProjectionCatchupPort()
    host = _PublicHostHandle(
        command_handle=cast(HostCommandHandle, command_handle),
        host_handle_id="host-open-runtime-test",
        scheduler=cast(HostDispatchScheduler, scheduler),
        projection_catchup_port=projection_catchup_port,
        wait_poller=None,
    )

    with pytest.raises(RuntimeError, match=_SCHEDULER_CLOSE_FAILURE_MESSAGE):
        await host.close()
    await host.close()

    assert scheduler.close_count == 1
    assert projection_catchup_port.catch_up_count == 1
    assert command_handle.close_count == 1


@pytest.mark.asyncio
async def test_public_host_close_closes_wait_poller_before_scheduler() -> None:
    """public Host close 先关闭 wait poller，再关闭 scheduler。"""

    order: list[str] = []
    wait_poller = _RecordingWaitPollerClose(order)
    scheduler = _RecordingSchedulerClose(order)
    command_handle = _RecordingCommandHandleClose()
    projection_catchup_port = _RecordingProjectionCatchupPort()
    host = _PublicHostHandle(
        command_handle=cast(HostCommandHandle, command_handle),
        host_handle_id="host-open-runtime-poller-close-test",
        scheduler=cast(HostDispatchScheduler, scheduler),
        projection_catchup_port=projection_catchup_port,
        wait_poller=cast(WaitPollerSupervisor, wait_poller),
    )

    await host.close()
    await host.close()

    assert order == ["poller", "scheduler"]
    assert wait_poller.close_count == 1
    assert scheduler.close_count == 1
    assert projection_catchup_port.catch_up_count == 1
    assert command_handle.close_count == 1


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
    seed_command_options = replace(
        _command_options_from_open_host_options(
            base_options,
            host_handle_id="host-open-runtime-poller-seed",
        ),
        local_execution=None,
    )
    seed_host = create_host_command_handle(seed_command_options)
    try:
        seeded = _seed_waiting_run(seed_host)
    finally:
        seed_host.close()

    adapter = _ReadyPollAdapter()
    options = replace(
        base_options,
        tooling_options=_tooling_options_with_poll_registry(
            _poll_adapter_registry(adapter)
        ),
        wait_poller_policy=_wait_poller_policy(),
    )

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
async def test_open_host_startup_failure_flushes_projection_before_close(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """open_host ready 前失败时仍应 best-effort 追平 projection。"""

    catch_up_calls = 0

    def raise_recovery_scan(
        self: StartupRecoveryScanner,
    ) -> None:
        """模拟 startup recovery scan 失败。

        :param self: 被 monkeypatch 的 scanner。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出测试错误。
        """

        del self
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
        StartupRecoveryScanner,
        "scan",
        raise_recovery_scan,
    )
    monkeypatch.setattr(
        _CompositeProjectionCatchupPort,
        "catch_up_projection",
        record_catch_up,
    )

    with pytest.raises(RuntimeError, match="forced startup recovery failure"):
        async with open_host(_options(tmp_path, _FinalAnswerWorkerFactory())):
            raise AssertionError("open_host must fail before yielding")

    assert catch_up_calls == 1


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
        command_handle: HostCommandHandle,
        host_handle_id: str,
        scheduler: HostDispatchScheduler,
        projection_catchup_port: ProjectionCatchupPort,
        wait_poller: WaitPollerSupervisor | None,
    ) -> None:
        """模拟 public handle 构造失败。

        :param self: public handle。
        :param command_handle: command handle。
        :param host_handle_id: Host handle id。
        :param scheduler: scheduler。
        :param projection_catchup_port: projection catch-up port。
        :param wait_poller: wait poller。
        :returns: 不会返回。
        :raises RuntimeError: 始终抛出测试错误。
        """

        del self, command_handle, host_handle_id, scheduler, projection_catchup_port
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
        active_registry: ActiveWorkerRegistry | None = None,
        projection_catchup_port: ProjectionCatchupPort | None = None,
    ) -> HostDispatchScheduler:
        """记录 scheduler open 时的 projection port 并委托真实 open。

        :param cls: scheduler class。
        :param transaction_runner: Host transaction runner。
        :param local_execution: 本地执行配置。
        :param host_handle_id: Host handle id。
        :param active_registry: active worker registry。
        :param projection_catchup_port: commit 后 projection catch-up port。
        :returns: 已打开 scheduler。
        """

        observed_ports.append(projection_catchup_port)
        return await original_open.__func__(
            cls,
            transaction_runner=transaction_runner,
            local_execution=local_execution,
            host_handle_id=host_handle_id,
            active_registry=active_registry,
            projection_catchup_port=projection_catchup_port,
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
        followup = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "required-memory-dispatch"),
        )
        final_run = await _wait_for_run_status(
            host,
            followup.accepted_run_id,
            RunStatus.SUCCEEDED,
        )

    assert final_run.status is RunStatus.SUCCEEDED
    assert len(factory.accepted_snapshots) == 1
    assert len(factory.accepted_requests) == 1


@pytest.mark.asyncio
async def test_open_host_purge_session_and_watch_after_purge_fail_closed(
    tmp_path: pathlib.Path,
) -> None:
    """open_host purge 接到 command facade，purge 后 watch 不重建 Session。"""

    options = _options(tmp_path, _FinalAnswerWorkerFactory())

    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request())
        await host.close_session(
            session.session_id,
            _close_request("close-before-purge"),
        )
        result = await host.purge_session(
            session.session_id,
            _purge_request("purge-open-host"),
        )

        assert result.session_id == session.session_id
        assert result.purged is True
        assert result.purge_tombstone_ref is not None
        assert result.deleted_counts_digest is not None
        with pytest.raises(HostApiError) as get_session_exc:
            await host.get_session(session.session_id)
        with pytest.raises(HostApiError) as watch_exc:
            host.watch_session_events(session.session_id)

        assert get_session_exc.value.code == HostApiErrorCode.NOT_FOUND
        assert watch_exc.value.code == HostApiErrorCode.NOT_FOUND


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


async def _next_terminal(watcher: AsyncIterator[HostEvent]) -> HostEvent:
    """读取下一个 terminal HostEvent。

    :param watcher: session event watcher。
    :returns: terminal HostEvent。
    :raises AssertionError: watcher 提前结束时抛出。
    """

    async for event in watcher:
        if event.kind in (
            HostEventKind.SUCCEEDED,
            HostEventKind.FAILED,
            HostEventKind.CANCELLED,
            HostEventKind.LOST,
        ):
            return event
    raise AssertionError("watcher ended before terminal event")


async def _close_iterator(iterator: AsyncIterator[HostEvent]) -> None:
    """关闭测试中持有的 async generator iterator。

    :param iterator: HostEvent async iterator。
    :returns: ``None``。
    """

    await cast(AsyncGenerator[HostEvent, None], iterator).aclose()


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
            ),
        ),
        worker_factory=worker_factory,
        tooling_options=None,
        context_budget_policy=None,
        compactor_runner_baseline=None,
        memory_projection_policy=default_memory_projection_policy(),
        memory_projection_catchup_batch_size=128,
        enable_truncation_manager=True,
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
        close_drain_timeout_seconds=0.2,
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
