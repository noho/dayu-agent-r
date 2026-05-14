"""Host LocalProxy 与 Engine 入口边界测试。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.tool_call import BatchToolExecutionRequest
from dayu.contracts.tool_outcome import BatchToolExecutionOutcome
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    RunFailedData,
)
from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.host.api import AttemptDispatchSnapshot
from dayu.host.local_proxy import DefaultLocalEngineWorkerFactory


class _NeverCancelledToken:
    """测试用未取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否取消。

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


@pytest.mark.asyncio
async def test_default_local_worker_uses_run_agent_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认 LocalProxy worker 调用 ``run_agent_messages`` 并暴露事件流。"""

    request = _request()
    emitted = _engine_event()
    seen_request: list[AgentRunRequest] = []

    async def _fake_run_agent_messages(
        incoming: AgentRunRequest,
    ) -> AsyncIterator[EngineEvent]:
        """替换 Engine 入口。

        :param incoming: Engine request。
        :returns: fake EngineEvent stream。
        """

        seen_request.append(incoming)
        yield emitted

    monkeypatch.setattr(
        "dayu.host.local_proxy.run_agent_messages",
        _fake_run_agent_messages,
    )

    worker = DefaultLocalEngineWorkerFactory().create_worker(_snapshot())
    handle = await worker.accept(_snapshot(), request)
    events = [event async for event in handle.events()]
    await handle.close()

    assert seen_request == [request]
    assert events == [emitted]
    assert handle.local_worker_id.startswith("local-worker-")


def _snapshot() -> AttemptDispatchSnapshot:
    """构造 dispatch snapshot。

    :returns: Attempt dispatch snapshot。
    """

    token: CancellationToken = _NeverCancelledToken()
    return AttemptDispatchSnapshot(
        session_id="session-local",
        run_id="run-local",
        attempt_id="attempt-local",
        execution_id="execution-local",
        dispatch_record_id="dispatch-local",
        execution_target="target-local",
        policy_snapshot_ref="policy-local",
        cancellation_token=token,
    )


def _request() -> AgentRunRequest:
    """构造 Engine request。

    :returns: AgentRunRequest。
    """

    token: CancellationToken = _NeverCancelledToken()
    return AgentRunRequest(
        run_id="run-local",
        session_id="session-local",
        messages=(
            UserMessage(role=AgentMessageRole.USER, content="hello"),
        ),
        disable_tools=True,
        runner_spec=RunnerSpec(
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
        ),
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
        tool_schemas=(),
        tool_executor=_NoopToolExecutor(),
        cancellation_token=token,
    )


class _NoopToolExecutor:
    """测试用不可达工具 executor。"""

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """执行工具。

        :param request: 工具请求。
        :returns: 当前测试不会调用。
        :raises AssertionError: 若被调用则抛出。
        """

        del request
        raise AssertionError("tools must be disabled")


def _engine_event() -> EngineEvent:
    """构造 fake EngineEvent。

    :returns: EngineEvent。
    """

    return EngineEvent(
        occurred_at=datetime.now(UTC),
        session_id="session-local",
        run_id="run-local",
        type=EngineEventType.RUN_FAILED,
        data=RunFailedData(
            error_code="fake",
            message="fake",
            provider_request_id=None,
            recoverable=False,
        ),
        metadata=None,
    )
