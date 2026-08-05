"""metadata / 显式契约边界测试。

通过反射列举 EngineEvent / RunnerEvent 各 data dataclass 字段，断言显式
契约事实（usage 拆分字段、provider_request_id、raw_payload、error_code、
finish_reason 等）直接出现在对应 data dataclass 中，而非塞入开放
metadata。
"""

from __future__ import annotations

from dayu.engine.contracts.structured_output import StructuredOutputRequest

from dayu.engine.contracts.structured_output import StructuredOutputCapability

import asyncio
import dataclasses
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.tool_call import BatchToolExecutionRequest
from dayu.contracts.tool_outcome import BatchToolExecutionOutcome
from dayu.contracts.tool_schema import ToolSchema
from dayu.engine.agent import _AsyncAgent
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    ProviderProtocolErrorData,
    UsageReportedData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import (
    AgentMessage,
    AgentMessageRole,
    UserMessage,
)
from dayu.engine.contracts.partial_tool_call import PartialToolCallSummary
from dayu.engine.contracts.runner import AsyncRunner
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventData,
    RunnerEventType,
    RunnerProtocolErrorData,
    RunnerUsageRecordedData,
)
from dayu.engine.contracts.runner_identity import RunnerRequestIdentity
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec

_TOOL_EXECUTION_TIMEOUT_SECONDS: float = 5.0
_RUNNER_DEFAULT_TIMEOUT_SECONDS: float = 30.0
_CONTINUATION_MAX_ATTEMPTS: int = 0


def _utc_now() -> datetime:
    """返回测试用 UTC 当前时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


@dataclass(slots=True)
class _MetadataBoundaryToken:
    """metadata 边界测试用取消 token。"""

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 固定返回 ``False``。
        :raises Exception: 不主动抛出异常。
        """

        return False

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 固定返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 固定返回 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None


class _MetadataBoundaryToolExecutor:
    """metadata 边界测试用工具执行器。"""

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """返回空工具结果批。

        :param request: 批式工具执行请求。
        :returns: 空 outcome 批；本测试不会实际触发工具执行。
        :raises Exception: 不主动抛出异常。
        """

        return BatchToolExecutionOutcome(records=())


@dataclass(slots=True)
class _MetadataBoundaryRunner:
    """按脚本产出 RunnerEvent 的 metadata 边界测试 Runner。"""

    events: tuple[RunnerEvent, ...]

    def call(
        self,
        messages: Sequence[AgentMessage],
        options: RunnerCallOptions,
        tools: Sequence[ToolSchema],
        *,
        structured_output: StructuredOutputRequest | None,
        request_identity: RunnerRequestIdentity | None,
    ) -> AsyncIterator[RunnerEvent]:
        """返回脚本化 RunnerEvent 流。

        :param messages: Agent 消息。
        :param options: Runner 调用选项。
        :param tools: 暴露给模型的工具 schema。
        :param structured_output: 本次调用的 structured-output 请求。
        :param request_identity: 本次逻辑 Runner 调用的请求身份。
        :returns: RunnerEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        del messages, options, tools, request_identity
        return self._iter_events()

    def is_supports_tool_calling(self) -> bool:
        """返回是否支持工具调用。

        :returns: 固定返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return True

    async def close(self) -> None:
        """关闭 Runner。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

    async def _iter_events(self) -> AsyncIterator[RunnerEvent]:
        """产出脚本事件。

        :returns: RunnerEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        for event in self.events:
            await asyncio.sleep(0)
            yield event


def _runner_event(event_type: RunnerEventType, data: RunnerEventData) -> RunnerEvent:
    """构造 RunnerEvent。

    :param event_type: Runner 事件类型。
    :param data: Runner 事件 data。
    :returns: RunnerEvent。
    :raises Exception: 不主动抛出异常。
    """

    return RunnerEvent(type=event_type, data=data, occurred_at=_utc_now())


def _metadata_boundary_request() -> AgentRunRequest:
    """构造 metadata 边界测试用 AgentRunRequest。

    :returns: Agent run 请求。
    :raises Exception: 不主动抛出异常。
    """

    token: CancellationToken = _MetadataBoundaryToken()
    return AgentRunRequest(
        run_id="run_metadata_boundary",
        session_id="session_metadata_boundary",
        messages=(UserMessage(role=AgentMessageRole.USER, content="hello"),),
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
            structured_output_capability=StructuredOutputCapability.NONE,
            default_timeout_seconds=_RUNNER_DEFAULT_TIMEOUT_SECONDS,
            max_retries=0,
            provider_request=None,
        ),
        runner_options=RunnerCallOptions(
            temperature=None,
            max_tokens=None,
            top_p=None,
            stream=True,
        ),
        agent_policy=AgentPolicy(
            max_iterations=1,
            continuation_max_attempts=_CONTINUATION_MAX_ATTEMPTS,
            allow_tool_calls=True,
            tool_execution_timeout_seconds=_TOOL_EXECUTION_TIMEOUT_SECONDS,
            fallback_prompt="test fallback prompt",
            continuation_prompt="test continuation prompt",
        ),
        tool_schemas=(),
        tool_executor=_MetadataBoundaryToolExecutor(),
        cancellation_token=token,
        attempt_id="attempt_metadata_boundary",
        execution_id="execution_metadata_boundary",
    )


def _field_names(cls: type) -> set[str]:
    """返回 dataclass 字段名集合。"""

    return {f.name for f in dataclasses.fields(cls)}


@pytest.mark.asyncio
async def test_agent_event_metadata_does_not_carry_log_records(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Agent 提升 RunnerEvent 时不得把日志对象塞进 EngineEvent metadata。

    :param caplog: pytest 日志捕获夹具。
    :returns: 无返回值。
    :raises AssertionError: metadata 边界被破坏时由 pytest 抛出。
    """

    runner: AsyncRunner = _MetadataBoundaryRunner(
        events=(
            _runner_event(
                RunnerEventType.RUNNER_CONTENT_COMPLETED,
                RunnerContentCompletedData(
                    content="answer",
                    reasoning_content=None,
                ),
            ),
            _runner_event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(
                    finish_reason=FinishReason.STOP,
                    provider_request_id="req_metadata",
                ),
            ),
        )
    )
    agent = _AsyncAgent(request=_metadata_boundary_request(), runner=runner)

    with caplog.at_level(logging.DEBUG, logger="dayu.engine.agent"):
        events: list[EngineEvent] = []
        async for event in agent.run_messages():
            events.append(event)

    assert caplog.records
    assert events
    for event in events:
        assert event.metadata is None
        assert not isinstance(event.metadata, logging.LogRecord)
        assert not isinstance(event.data, logging.LogRecord)


def test_usage_reported_data_uses_split_token_fields() -> None:
    """Engine 侧用量上报事件必须使用拆分字段，不允许整 dict。"""

    fields = _field_names(UsageReportedData)
    assert {
        "iteration_id",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "provider_request_id",
    } == fields


def test_runner_usage_recorded_data_uses_split_token_fields() -> None:
    """Runner 侧用量事件必须使用拆分字段。"""

    fields = _field_names(RunnerUsageRecordedData)
    assert {
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "provider_request_id",
    } == fields


def test_provider_protocol_error_engine_data_has_explicit_fields() -> None:
    """provider 协议错误事件 data 必须显式承载契约字段。"""

    fields = _field_names(ProviderProtocolErrorData)
    assert {
        "iteration_id",
        "client_correlation_id",
        "error_code",
        "message",
        "partial_tool_calls",
        "provider_request_id",
        "raw_payload",
    } == fields


def test_provider_protocol_error_runner_data_has_explicit_fields() -> None:
    """Runner 侧 provider 协议错误 data 必须显式承载契约字段。"""

    fields = _field_names(RunnerProtocolErrorData)
    assert {
        "error_code",
        "message",
        "partial_tool_calls",
        "provider_request_id",
        "raw_payload",
    } == fields


def test_partial_tool_call_summary_excludes_raw_arguments() -> None:
    """partial tool call 摘要必须只暴露有界诊断字段。

    参数：无。
    返回值：无。
    异常：断言失败时由 pytest 抛出 ``AssertionError``。
    """

    fields = _field_names(PartialToolCallSummary)
    assert {
        "tool_call_index",
        "tool_call_id",
        "name_fragment",
        "arguments_byte_size",
        "arguments_sha256",
    } == fields
    assert "arguments" not in fields


def test_runner_content_completed_data_excludes_finish_reason() -> None:
    """正文完成事件不得承载 Runner 完成原因。"""

    fields = _field_names(RunnerContentCompletedData)
    assert fields == {"content", "reasoning_content"}
