"""P10.5 Slice 5 public retry / replay 控制命令测试。"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    RunFailedData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
from dayu.host import (
    AttemptDispatchSnapshot,
    EnsureSessionRequest,
    FollowupBehavior,
    Host,
    HostApiError,
    HostApiErrorCode,
    HostCallContext,
    LocalEngineWorker,
    LocalWorkerHandle,
    OpenHostOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    ReplayRunRequest,
    RetryRunRequest,
    RunStatus,
    SourceRunRelation,
    SubmitFollowupRequest,
    open_host,
)
from dayu.host.api import AuthorizationClaim
from dayu.host.memory import default_memory_projection_policy

_NOW = datetime(2026, 5, 18, 1, 2, 3, tzinfo=UTC)
_FINAL = "final"
_FAILED = "failed"
_BLOCK = "block"


class _SequencedHandle:
    """按指定模式产出 Engine 事件的测试 handle。"""

    def __init__(self, snapshot: AttemptDispatchSnapshot, mode: str) -> None:
        """初始化 handle。

        :param snapshot: dispatch snapshot。
        :param mode: 事件模式。
        :returns: ``None``。
        """

        self._snapshot = snapshot
        self._mode = mode
        self.cancel_reasons: list[str] = []
        self.events_started = asyncio.Event()
        self.cancelled = asyncio.Event()

    @property
    def local_worker_id(self) -> str:
        """返回本地 worker id。

        :returns: worker id。
        """

        return "slice5-sequenced-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """按模式产出终态事件或保持阻塞。

        :returns: EngineEvent 异步迭代器。
        """

        self.events_started.set()
        if self._mode == _FINAL:
            yield EngineEvent(
                occurred_at=_NOW,
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
            return
        if self._mode == _FAILED:
            yield EngineEvent(
                occurred_at=_NOW,
                session_id=self._snapshot.session_id,
                run_id=self._snapshot.run_id,
                type=EngineEventType.RUN_FAILED,
                data=RunFailedData(
                    error_code="slice5_failed",
                    message="slice5 failed",
                    provider_request_id=None,
                    recoverable=False,
                ),
                metadata=None,
            )
            return
        await self.cancelled.wait()
        if False:
            yield _unreachable_engine_event()

    async def close(self) -> None:
        """关闭测试 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """记录取消原因。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        self.cancel_reasons.append(reason)
        self.cancelled.set()


class _SequencedWorker:
    """测试用 worker。"""

    def __init__(self, factory: "_SequencedWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 所属 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """接受 dispatch 并记录请求。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: worker handle。
        """

        mode = self._factory.next_mode()
        handle = _SequencedHandle(snapshot, mode)
        self._factory.accepted_snapshots.append(snapshot)
        self._factory.accepted_requests.append(request)
        self._factory.handles.append(handle)
        self._factory.accepted_event.set()
        return handle


class _SequencedWorkerFactory:
    """按顺序返回测试 worker mode 的 factory。"""

    def __init__(self, modes: list[str]) -> None:
        """初始化 factory。

        :param modes: worker accept 顺序对应的模式。
        :returns: ``None``。
        """

        self._modes = modes
        self.accepted_snapshots: list[AttemptDispatchSnapshot] = []
        self.accepted_requests: list[AgentRunRequest] = []
        self.handles: list[_SequencedHandle] = []
        self.accepted_event = asyncio.Event()

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建测试 worker。

        :param snapshot: dispatch snapshot。
        :returns: 测试 worker。
        """

        del snapshot
        return _SequencedWorker(self)

    def next_mode(self) -> str:
        """弹出下一个 worker mode。

        :returns: mode 文本。
        :raises AssertionError: 没有预置 mode 时抛出。
        """

        if not self._modes:
            raise AssertionError("worker mode exhausted")
        return self._modes.pop(0)


@pytest.mark.asyncio
async def test_retry_failed_run_creates_related_run_public_path(
    tmp_path: pathlib.Path,
) -> None:
    """retry_run 只通过 public opener 为 FAILED 源 Run 创建关联新 Run。"""

    factory = _SequencedWorkerFactory([_FAILED, _FINAL])
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request("retry"))
        source = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "retry-source"),
        )
        await _wait_for_run_status(host, source.accepted_run_id, RunStatus.FAILED)

        retried = await host.retry_run(
            source.accepted_run_id,
            RetryRunRequest(
                context=_context("retry-control"),
                client_request_id="retry-control",
                reason="ordinary_failed_retry",
            ),
        )

        assert retried.source_run_id == source.accepted_run_id
        assert retried.source_run_relation is SourceRunRelation.RETRY
        await _wait_for_run_status(host, retried.run_id, RunStatus.SUCCEEDED)


@pytest.mark.asyncio
async def test_retry_run_replays_same_client_request_id_idempotently(
    tmp_path: pathlib.Path,
) -> None:
    """retry_run 同一 client_request_id 重放返回同一关联 Run。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: retry 幂等重放创建重复 Run 时抛出。
    """

    factory = _SequencedWorkerFactory([_FAILED, _FINAL])
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request("retry-idempotent"))
        source = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "retry-idempotent-source"),
        )
        await _wait_for_run_status(host, source.accepted_run_id, RunStatus.FAILED)
        request = RetryRunRequest(
            context=_context("retry-idempotent"),
            client_request_id="retry-idempotent",
            reason="ordinary_failed_retry",
        )

        first = await host.retry_run(source.accepted_run_id, request)
        await _wait_for_run_status(host, first.run_id, RunStatus.SUCCEEDED)
        second = await host.retry_run(source.accepted_run_id, request)

    assert first.run_id == second.run_id
    assert len(factory.accepted_requests) == 2


@pytest.mark.asyncio
async def test_retry_run_policy_limit_rejects_second_retry(
    tmp_path: pathlib.Path,
) -> None:
    """同一 FAILED 源 Run 只允许一个 ordinary retry。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 第二个 retry 未被 policy limit 拒绝时抛出。
    """

    factory = _SequencedWorkerFactory([_FAILED, _FINAL])
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request("retry-limit"))
        source = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "retry-limit-source"),
        )
        await _wait_for_run_status(host, source.accepted_run_id, RunStatus.FAILED)
        await host.retry_run(
            source.accepted_run_id,
            RetryRunRequest(
                context=_context("retry-limit-1"),
                client_request_id="retry-limit-1",
                reason="ordinary_failed_retry",
            ),
        )

        with pytest.raises(HostApiError) as exc_info:
            await host.retry_run(
                source.accepted_run_id,
                RetryRunRequest(
                    context=_context("retry-limit-2"),
                    client_request_id="retry-limit-2",
                    reason="ordinary_failed_retry",
                ),
            )

    assert exc_info.value.code == HostApiErrorCode.INVALID_STATE


@pytest.mark.asyncio
async def test_retry_and_replay_missing_source_run_return_not_found(
    tmp_path: pathlib.Path,
) -> None:
    """retry_run / replay_run 源 Run 不存在时返回 public NOT_FOUND。"""

    factory = _SequencedWorkerFactory([])
    async with open_host(_options(tmp_path, factory)) as host:
        with pytest.raises(HostApiError) as retry_error:
            await host.retry_run(
                "missing-run",
                RetryRunRequest(
                    context=_context("retry-missing"),
                    client_request_id="retry-missing",
                    reason="ordinary_failed_retry",
                ),
            )
        with pytest.raises(HostApiError) as replay_error:
            await host.replay_run(
                "missing-run",
                ReplayRunRequest(
                    context=_context("replay-missing"),
                    client_request_id="replay-missing",
                    reason="schema_repair",
                    repair_instruction="repair output shape",
                ),
            )

    assert retry_error.value.code == HostApiErrorCode.NOT_FOUND
    assert replay_error.value.code == HostApiErrorCode.NOT_FOUND


@pytest.mark.asyncio
async def test_retry_run_same_client_request_id_different_digest_conflicts(
    tmp_path: pathlib.Path,
) -> None:
    """retry_run 同一 client_request_id 不同语义 digest 返回幂等冲突。"""

    factory = _SequencedWorkerFactory([_FAILED, _FINAL])
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request("retry-digest-conflict"))
        source = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "retry-digest-source"),
        )
        await _wait_for_run_status(host, source.accepted_run_id, RunStatus.FAILED)
        await host.retry_run(
            source.accepted_run_id,
            RetryRunRequest(
                context=_context("retry-digest"),
                client_request_id="retry-digest",
                reason="ordinary_failed_retry",
            ),
        )

        with pytest.raises(HostApiError) as exc_info:
            await host.retry_run(
                source.accepted_run_id,
                RetryRunRequest(
                    context=_context("retry-digest"),
                    client_request_id="retry-digest",
                    reason="different_retry_reason",
                ),
            )

    assert exc_info.value.code == HostApiErrorCode.IDEMPOTENCY_CONFLICT


@pytest.mark.asyncio
async def test_replay_succeeded_run_no_tool_public_path(
    tmp_path: pathlib.Path,
) -> None:
    """replay_run 为 SUCCEEDED 源 Run 创建 no-tool 关联新 Run。"""

    factory = _SequencedWorkerFactory([_FINAL, _FINAL])
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request("replay"))
        source = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "replay-source"),
        )
        await _wait_for_run_status(host, source.accepted_run_id, RunStatus.SUCCEEDED)

        replayed = await host.replay_run(
            source.accepted_run_id,
            ReplayRunRequest(
                context=_context("replay-control"),
                client_request_id="replay-control",
                reason="schema_repair",
                repair_instruction="repair output shape",
            ),
        )

        assert replayed.source_run_id == source.accepted_run_id
        assert replayed.source_run_relation is SourceRunRelation.REPLAY
        await _wait_for_run_status(host, replayed.run_id, RunStatus.SUCCEEDED)
        replay_request = factory.accepted_requests[-1]
        assert replay_request.disable_tools is True
        assert replay_request.tool_schemas == ()


@pytest.mark.asyncio
async def test_replay_run_replays_same_client_request_id_idempotently(
    tmp_path: pathlib.Path,
) -> None:
    """replay_run 同一 client_request_id 重放返回同一关联 Run。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: replay 幂等重放创建重复 Run 时抛出。
    """

    factory = _SequencedWorkerFactory([_FINAL, _FINAL])
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request("replay-idempotent"))
        source = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "replay-idempotent-source"),
        )
        await _wait_for_run_status(host, source.accepted_run_id, RunStatus.SUCCEEDED)
        request = ReplayRunRequest(
            context=_context("replay-idempotent"),
            client_request_id="replay-idempotent",
            reason="schema_repair",
            repair_instruction="repair output shape",
        )

        first = await host.replay_run(source.accepted_run_id, request)
        await _wait_for_run_status(host, first.run_id, RunStatus.SUCCEEDED)
        second = await host.replay_run(source.accepted_run_id, request)

    assert first.run_id == second.run_id
    assert len(factory.accepted_requests) == 2


@pytest.mark.asyncio
async def test_retry_and_replay_reject_non_target_source_status(
    tmp_path: pathlib.Path,
) -> None:
    """retry/replay 对非目标源状态返回 public INVALID_STATE。

    :param tmp_path: pytest 临时目录。
    :returns: ``None``。
    :raises AssertionError: 非目标状态未被拒绝时抛出。
    """

    factory = _SequencedWorkerFactory([_FINAL, _FAILED])
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request("relation-reject"))
        succeeded = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "relation-succeeded"),
        )
        await _wait_for_run_status(host, succeeded.accepted_run_id, RunStatus.SUCCEEDED)
        failed = await host.submit_followup(
            session.session_id,
            _followup_request(session.session_id, "relation-failed"),
        )
        await _wait_for_run_status(host, failed.accepted_run_id, RunStatus.FAILED)

        with pytest.raises(HostApiError) as retry_error:
            await host.retry_run(
                succeeded.accepted_run_id,
                RetryRunRequest(
                    context=_context("retry-succeeded"),
                    client_request_id="retry-succeeded",
                    reason="ordinary_failed_retry",
                ),
            )
        with pytest.raises(HostApiError) as replay_error:
            await host.replay_run(
                failed.accepted_run_id,
                ReplayRunRequest(
                    context=_context("replay-failed"),
                    client_request_id="replay-failed",
                    reason="schema_repair",
                    repair_instruction="repair output shape",
                ),
            )

    assert retry_error.value.code == HostApiErrorCode.INVALID_STATE
    assert replay_error.value.code == HostApiErrorCode.INVALID_STATE


def _options(
    tmp_path: pathlib.Path, worker_factory: _SequencedWorkerFactory
) -> OpenHostOptions:
    """构造 open_host 测试 options。

    :param tmp_path: pytest 临时目录。
    :param worker_factory: worker factory。
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
        lane_name="slice5",
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

    return EnsureSessionRequest(scope="workspace", slot_key=slot_key, metadata=())


def _followup_request(
    session_id: str, client_request_id: str
) -> SubmitFollowupRequest:
    """构造 queue follow-up 请求。

    :param session_id: Session id。
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


def _context(request_id: str) -> HostCallContext:
    """构造 Host 调用上下文。

    :param request_id: request id。
    :returns: HostCallContext。
    """

    return HostCallContext(
        actor="analyst",
        source="pytest",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="tester"),),
        operation_context=OperationContext(
            operation_name="slice5",
            operation_kind="test",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="slice5",
            correlation_id=None,
        ),
    )


async def _wait_for_run_status(
    host: Host, run_id: str, expected_status: RunStatus
) -> None:
    """等待 Run 到达目标状态。

    :param host: public Host handle。
    :param run_id: Run id。
    :param expected_status: 目标状态。
    :returns: ``None``。
    :raises TimeoutError: 超时未到达目标状态时抛出。
    """

    for _ in range(200):
        snapshot = await host.get_run(run_id)
        if snapshot.status == expected_status:
            return
        await asyncio.sleep(0.01)
    raise TimeoutError(f"Run {run_id} did not reach {expected_status.value}")


def _unreachable_engine_event() -> EngineEvent:
    """构造不可达 EngineEvent。

    :returns: EngineEvent。
    """

    raise AssertionError("unreachable")
