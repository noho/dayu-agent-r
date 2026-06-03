"""P10.5 Slice 3 submit_followup public request contract 测试。"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from dataclasses import fields
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
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
from dayu.host import (
    AttemptDispatchSnapshot,
    EnsureSessionRequest,
    FollowupBehavior,
    HostCallContext,
    LocalEngineWorker,
    LocalWorkerHandle,
    OpenHostOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    SubmitFollowupRequest,
    open_host,
)
from dayu.host.api import HostStreamCursor
from dayu.host.memory import default_memory_projection_policy


class _FinalHandle:
    """测试用立即产出 final answer 的 worker handle。"""

    def __init__(self, snapshot: AttemptDispatchSnapshot) -> None:
        """初始化 handle。

        :param snapshot: dispatch snapshot。
        :returns: ``None``。
        """

        self._snapshot = snapshot

    @property
    def local_worker_id(self) -> str:
        """返回 worker id。

        :returns: worker id。
        """

        return "slice3-contract-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """产出成功终态事件。

        :returns: EngineEvent 异步迭代器。
        """

        yield EngineEvent(
            occurred_at=datetime(2026, 5, 18, 1, 0, 0, tzinfo=UTC),
            session_id=self._snapshot.session_id,
            run_id=self._snapshot.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content="ok",
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消。

        :param reason: 取消原因。
        :returns: ``None``。
        """

        del reason


class _RecordingWorker:
    """记录 Engine request 的 worker。"""

    def __init__(self, factory: "_RecordingWorkerFactory") -> None:
        """初始化 worker。

        :param factory: 记录用 factory。
        :returns: ``None``。
        """

        self._factory = factory

    async def accept(
        self, snapshot: AttemptDispatchSnapshot, request: AgentRunRequest
    ) -> LocalWorkerHandle:
        """接受并记录 request。

        :param snapshot: dispatch snapshot。
        :param request: Engine request。
        :returns: final handle。
        """

        self._factory.snapshots.append(snapshot)
        self._factory.requests.append(request)
        self._factory.accepted.set()
        return _FinalHandle(snapshot)


class _RecordingWorkerFactory:
    """记录 worker accept 输入的 factory。"""

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        """

        self.accepted = asyncio.Event()
        self.snapshots: list[AttemptDispatchSnapshot] = []
        self.requests: list[AgentRunRequest] = []

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建记录 worker。

        :param snapshot: dispatch snapshot。
        :returns: 记录 worker。
        """

        del snapshot
        return _RecordingWorker(self)


def test_submit_followup_request_freezes_typed_public_fields() -> None:
    """SubmitFollowupRequest 只暴露 Slice 3 冻结的 prompt / override 字段。"""

    names = {field.name for field in fields(SubmitFollowupRequest)}

    assert {
        "system_prompt",
        "user_prompt",
        "tool_names",
        "runner_spec",
        "runner_options",
        "agent_policy",
    }.issubset(names)
    assert "input" not in names
    assert "payload" not in names
    assert "profile_id" not in names


def test_submit_followup_rejects_untyped_tool_selector() -> None:
    """tool_names 不接受逗号字符串或普通 list。"""

    with pytest.raises(TypeError, match="tool_names"):
        _followup(tool_names=cast(frozenset[str] | None, "lookup,search"))
    with pytest.raises(TypeError, match="tool_names"):
        _followup(tool_names=cast(frozenset[str] | None, ["lookup"]))


@pytest.mark.asyncio
async def test_repeated_client_request_returns_same_run_and_watermark(
    tmp_path: pathlib.Path,
) -> None:
    """重复提交同一 session/client_request_id 返回同一 accepted Run。"""

    factory = _RecordingWorkerFactory()
    async with open_host(_options(tmp_path, factory)) as host:
        session = await host.ensure_session(_ensure_request())
        request = _followup(
            session_id=session.session_id,
            client_request_id="client-repeat",
        )

        first = await host.submit_followup(session.session_id, request)
        await asyncio.wait_for(factory.accepted.wait(), timeout=2.0)
        second = await host.submit_followup(session.session_id, request)

    assert first.accepted_run_id == second.accepted_run_id
    assert isinstance(first.command_watermark, HostStreamCursor)
    assert len(factory.requests) == 1


def _followup(
    *,
    session_id: str = "session-public",
    client_request_id: str = "client-1",
    tool_names: frozenset[str] | None = None,
) -> SubmitFollowupRequest:
    """构造 submit_followup 请求。

    :param session_id: Session id。
    :param client_request_id: 幂等 id。
    :param tool_names: 工具选择器。
    :returns: SubmitFollowupRequest。
    """

    return SubmitFollowupRequest(
        context=_context(client_request_id),
        session_id=session_id,
        client_request_id=client_request_id,
        system_prompt=None,
        user_prompt="hello",
        tool_names=tool_names,
        runner_spec=None,
        runner_options=None,
        agent_policy=None,
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def _ensure_request() -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :returns: EnsureSessionRequest。
    """

    return EnsureSessionRequest(scope="scope", slot_key="slot", metadata=())


def _context(request_id: str) -> HostCallContext:
    """构造 HostCallContext。

    :param request_id: request id。
    :returns: HostCallContext。
    """

    return HostCallContext(
        actor="tester",
        source="pytest",
        request_id=request_id,
        authorization_claims=(),
        operation_context=OperationContext(
            operation_name="submit_followup",
            operation_kind="interactive",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario=None,
            correlation_id=None,
        ),
    )


def _options(
    tmp_path: pathlib.Path, worker_factory: _RecordingWorkerFactory
) -> OpenHostOptions:
    """构造 OpenHostOptions。

    :param tmp_path: 临时目录。
    :param worker_factory: 记录 factory。
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
            runner_spec=_runner_spec("baseline"),
            runner_options=RunnerCallOptions(
                temperature=None, max_tokens=None, top_p=None, stream=False
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


def _runner_spec(model: str) -> RunnerSpec:
    """构造 RunnerSpec。

    :param model: 模型名。
    :returns: RunnerSpec。
    """

    return RunnerSpec(
        provider="test",
        model=model,
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
