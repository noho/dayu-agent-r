"""P10.5 Slice 2 ``open_host`` production runtime 接线测试。"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol, cast

import pytest

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host import (
    AttemptDispatchSnapshot,
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
    LocalEngineWorker,
    LocalEngineWorkerFactory,
    LocalWorkerHandle,
    OpenHostOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    PurgeSessionRequest,
    PurgeSessionResult,
    RunSnapshot,
    RunStatus,
    SubmitFollowupRequest,
    open_host,
)
from dayu.host.api import HostInput
from dayu.host.api import AuthorizationClaim
from dayu.host.command import HostCommandHandle
from dayu.host.dispatch import HostDispatchScheduler
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.outbox import read_outbox_terminal_items_after
from dayu.host.durable.transaction import HostTransaction
from dayu.host.context_policy import default_context_budget_policy
from dayu.host.memory import default_memory_projection_policy
from dayu.host.open_host import (
    _PublicHostHandle,
    _command_options_from_open_host_options,
    _local_execution_options_from_open_host_options,
)
from dayu.host.llm_compaction import LLMContextCompactor
from dayu.host.projection import ProjectionCatchupPort

_SCHEDULER_CLOSE_FAILURE_MESSAGE = "scheduler close failed after cleanup"


class _PurgeCapableHost(Protocol):
    """测试 open_host concrete handle 的 purge 接线能力。"""

    async def purge_session(
        self, session_id: str, request: PurgeSessionRequest
    ) -> PurgeSessionResult:
        """清理已关闭 Session。

        :param session_id: 目标 Session id。
        :param request: purge 请求。
        :returns: concrete public purge result。
        """

        ...


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
    )

    with pytest.raises(RuntimeError, match=_SCHEDULER_CLOSE_FAILURE_MESSAGE):
        await host.close()
    await host.close()

    assert scheduler.close_count == 1
    assert projection_catchup_port.catch_up_count == 1
    assert command_handle.close_count == 1


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
        purge_host = cast(_PurgeCapableHost, host)
        result = await purge_host.purge_session(
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
