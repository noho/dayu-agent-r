"""AgentRunRequest 契约测试。"""

from __future__ import annotations

from datetime import datetime

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.tool_call import BatchToolExecutionRequest
from dayu.contracts.tool_outcome import BatchToolExecutionOutcome
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.messages import AgentMessageRole, UserMessage
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec


class _Token(CancellationToken):
    """测试用取消 token。"""

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


class _NoopToolExecutor:
    """测试用 no-op 工具执行器。"""

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """返回空工具执行结果。

        :param request: 批式工具执行请求。
        :returns: 空结果。
        """

        del request
        return BatchToolExecutionOutcome(records=())


def test_agent_run_request_rejects_empty_messages() -> None:
    """AgentRunRequest 必须拒绝空 messages。"""

    with pytest.raises(ValueError, match="messages"):
        _request(messages=())


def test_agent_run_request_accepts_non_empty_messages() -> None:
    """AgentRunRequest 接受非空 messages。"""

    request = _request(
        messages=(UserMessage(role=AgentMessageRole.USER, content="hello"),)
    )

    assert len(request.messages) == 1


def test_agent_run_request_requires_attempt_execution_pair() -> None:
    """AgentRunRequest 的 attempt / execution identity 必须成对出现。"""

    message = UserMessage(role=AgentMessageRole.USER, content="hello")
    with pytest.raises(ValueError, match="attempt_id"):
        _request(
            messages=(message,),
            attempt_id="attempt-contract",
            execution_id=None,
        )
    with pytest.raises(ValueError, match="attempt_id"):
        _request(
            messages=(message,),
            attempt_id=None,
            execution_id="execution-contract",
        )


def test_agent_run_request_accepts_attempt_execution_pair() -> None:
    """AgentRunRequest 接受成对的 attempt / execution identity。"""

    request = _request(
        messages=(UserMessage(role=AgentMessageRole.USER, content="hello"),),
        attempt_id="attempt-contract",
        execution_id="execution-contract",
    )

    assert request.attempt_id == "attempt-contract"
    assert request.execution_id == "execution-contract"


def _request(
    *,
    messages: tuple[UserMessage, ...],
    attempt_id: str | None = None,
    execution_id: str | None = None,
) -> AgentRunRequest:
    """构造 AgentRunRequest。

    :param messages: 请求消息。
    :param attempt_id: Host attempt id。
    :param execution_id: Host execution id。
    :returns: AgentRunRequest。
    """

    return AgentRunRequest(
        run_id="run-contract",
        session_id="session-contract",
        messages=messages,
        disable_tools=True,
        runner_spec=RunnerSpec(
            provider="openai",
            model="model",
            endpoint="https://example.test/v1/chat/completions",
            api_key_ref="TEST_KEY",
            headers={},
            client_correlation_policy=ClientCorrelationPolicy.DISABLED,
            supports_tool_calling=True,
            supports_streaming=True,
            supports_stream_usage=False,
            default_timeout_seconds=30.0,
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
            fallback_prompt="test fallback prompt",
            continuation_prompt="test continuation prompt",
        ),
        tool_schemas=(),
        tool_executor=_NoopToolExecutor(),
        cancellation_token=_Token(),
        attempt_id=attempt_id,
        execution_id=execution_id,
    )
