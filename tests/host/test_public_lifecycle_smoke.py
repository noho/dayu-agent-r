"""P10.5 Slice 2 public Host lifecycle smoke 测试。"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import AsyncIterator

import pytest

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import EngineEvent
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
from dayu.host import (
    AttemptDispatchSnapshot,
    CancelMode,
    CancelRunRequest,
    CloseSessionRequest,
    EnsureSessionRequest,
    FollowupBehavior,
    Host,
    HostApiError,
    HostCallContext,
    HostClosedError,
    LocalEngineWorker,
    LocalWorkerHandle,
    OpenHostOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    PurgeSessionRequest,
    RunStatus,
    SessionStatus,
    SubmitFollowupRequest,
    open_host,
)
from dayu.host.api import AuthorizationClaim
from dayu.host.memory import default_memory_projection_policy


class _BlockingHandle:
    """测试用长期阻塞 worker handle。"""

    def __init__(self) -> None:
        """初始化阻塞 handle。

        :returns: ``None``。
        """

        self.cancel_reasons: list[str] = []
        self.close_count = 0
        self.events_started = asyncio.Event()

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: 本地 worker id。
        """

        return "lifecycle-blocking-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """保持事件流阻塞直到 task 被关闭。

        :returns: 不会自然返回事件。
        """

        self.events_started.set()
        await asyncio.sleep(10.0)
        if False:
            yield _unreachable_engine_event()

    async def close(self) -> None:
        """关闭测试 handle。

        :returns: ``None``。
        """

        self.close_count += 1

    def on_cancel(self, reason: str) -> None:
        """记录取消请求。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        self.cancel_reasons.append(reason)


class _BlockingWorker:
    """测试用返回固定阻塞 handle 的 worker。"""

    def __init__(self, handle: _BlockingHandle) -> None:
        """初始化 worker。

        :param handle: 固定返回的 handle。
        :returns: ``None``。
        """

        self._handle = handle

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受 dispatch 并返回阻塞 handle。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: 阻塞 handle。
        """

        del snapshot, request
        return self._handle


class _BlockingWorkerFactory:
    """测试用 blocking worker factory。"""

    def __init__(self, handle: _BlockingHandle) -> None:
        """初始化 factory。

        :param handle: 固定返回的 handle。
        :returns: ``None``。
        """

        self._handle = handle

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 blocking worker。

        :param snapshot: dispatch snapshot。
        :returns: blocking worker。
        """

        del snapshot
        return _BlockingWorker(self._handle)


@pytest.mark.asyncio
async def test_close_session_host_close_and_cancel_are_distinct(
    tmp_path: pathlib.Path,
) -> None:
    """close_session、host.close 与 cancel 写入的治理事实互不替代。"""

    handle = _BlockingHandle()
    options = _options(tmp_path, _BlockingWorkerFactory(handle))

    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request("lifecycle"))
        first = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "first"),
        )
        await _wait_for_run_status(host, first.accepted_run_id, RunStatus.RUNNING)

        second = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "second"),
        )
        assert second.accepted_run_status == RunStatus.QUEUED

        cancelled = await host.cancel_run(
            second.accepted_run_id,
            _cancel_request("cancel-second"),
        )
        assert cancelled.status == RunStatus.CANCELLED
        cancelled_snapshot = await host.get_run(second.accepted_run_id)
        assert cancelled_snapshot.status is RunStatus.CANCELLED

        closed = await host.close_session(
            session.session_id,
            _close_request("close-session"),
        )
        assert closed.status == SessionStatus.CLOSED
        still_readable = await host.get_session(session.session_id)
        assert still_readable.status == SessionStatus.CLOSED

        with pytest.raises(HostApiError):
            await host.submit_followup(
                session.session_id,
                _followup_request(session.session_id, "after-close-session"),
            )

        first_before_close = await host.get_run(first.accepted_run_id)
        second_before_close = await host.get_run(second.accepted_run_id)
        await host.close()
        await host.close()

        assert first_before_close.status is RunStatus.RUNNING
        assert second_before_close.status is RunStatus.CANCELLED
        with pytest.raises(HostClosedError):
            await host.get_session(session.session_id)
        with pytest.raises(HostClosedError):
            await host.submit_followup(
                session.session_id,
                _followup_request(session.session_id, "after-host-close"),
            )
        with pytest.raises(HostClosedError):
            await host.purge_session(
                session.session_id,
                _purge_request("purge-after-host-close"),
            )


@pytest.mark.asyncio
async def test_host_close_does_not_close_open_session_or_write_terminal_facts(
    tmp_path: pathlib.Path,
) -> None:
    """opener close 只关闭本地 runtime，不关闭 Session 或伪造 terminal facts。"""

    handle = _BlockingHandle()
    options = _options(tmp_path, _BlockingWorkerFactory(handle))

    async with open_host(options) as host:
        session = await host.ensure_session(_ensure_request("host-close"))
        followup = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "host-close-running"),
        )
        await _wait_for_run_status(host, followup.accepted_run_id, RunStatus.RUNNING)
        await host.close()

    async with open_host(options) as reopened:
        reopened_session = await reopened.get_session(session.session_id)
        reopened_run = await reopened.get_run(followup.accepted_run_id)

    assert reopened_session.status == SessionStatus.OPEN
    assert reopened_run.status == RunStatus.RUNNING


async def _wait_for_run_status(
    host: Host,
    run_id: str,
    expected_status: RunStatus,
) -> None:
    """等待 Run 到达指定状态。

    :param host: public Host handle。
    :param run_id: 目标 Run id。
    :param expected_status: 期待状态。
    :returns: ``None``。
    :raises AssertionError: 超时仍未到达期待状态时抛出。
    """

    for _ in range(100):
        snapshot = await host.get_run(run_id)
        if snapshot.status == expected_status:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"run {run_id} did not reach {expected_status.value}")


def _options(
    tmp_path: pathlib.Path,
    worker_factory: _BlockingWorkerFactory,
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

    :param slot_key: slot key。
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
        user_prompt=f"prompt:{client_request_id}",
        tool_names=None,
        runner_spec=None,
        runner_options=None,
        agent_policy=None,
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def _cancel_request(client_request_id: str) -> CancelRunRequest:
    """构造 cancel run 请求。

    :param client_request_id: 幂等请求 id。
    :returns: CancelRunRequest。
    """

    return CancelRunRequest(
        context=_context(client_request_id),
        client_request_id=client_request_id,
        reason="user_stop",
        mode=CancelMode.GRACEFUL,
    )


def _close_request(client_request_id: str) -> CloseSessionRequest:
    """构造 close session 请求。

    :param client_request_id: 幂等请求 id。
    :returns: CloseSessionRequest。
    """

    return CloseSessionRequest(
        context=_context(client_request_id),
        client_request_id=client_request_id,
        reason="done",
    )


def _purge_request(client_request_id: str) -> PurgeSessionRequest:
    """构造 purge session 请求。

    :param client_request_id: 幂等请求 id。
    :returns: PurgeSessionRequest。
    """

    return PurgeSessionRequest(
        context=_context(client_request_id),
        client_request_id=client_request_id,
        reason="public_lifecycle_purge",
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
            operation_name="public_lifecycle_smoke",
            operation_kind="unit_test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="p10_5_slice2",
            correlation_id="corr-public-lifecycle",
        ),
    )


def _unreachable_engine_event() -> EngineEvent:
    """构造不可达 EngineEvent 占位。

    :returns: 当前函数不会正常返回。
    :raises AssertionError: 始终抛出。
    """

    raise AssertionError("unreachable EngineEvent placeholder")
