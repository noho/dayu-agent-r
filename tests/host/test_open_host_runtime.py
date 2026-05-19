"""P10.5 Slice 2 ``open_host`` production runtime 接线测试。"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

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
    CompactorRunnerBaseline,
    EnsureSessionRequest,
    FollowupBehavior,
    Host,
    HostCallContext,
    HostInput,
    LocalEngineWorker,
    LocalWorkerHandle,
    OpenHostOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    RunSnapshot,
    RunStatus,
    SubmitFollowupRequest,
    open_host,
)
from dayu.host.api import AuthorizationClaim
from dayu.host.command import HostCommandHandle
from dayu.host.dispatch import HostDispatchScheduler
from dayu.host.memory import default_memory_projection_policy
from dayu.host.open_host import (
    _PublicHostHandle,
    _local_execution_options_from_open_host_options,
)
from dayu.host.llm_compaction import LLMContextCompactor
from dayu.host.projection import ProjectionCatchupPort

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

    def cancel(self, reason: str) -> None:
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


def _options(
    tmp_path: pathlib.Path,
    worker_factory: _FinalAnswerWorkerFactory,
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
