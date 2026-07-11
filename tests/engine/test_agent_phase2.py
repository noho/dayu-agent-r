"""Phase 2 Agent run loop 行为测试。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

import dayu.engine.agent as agent_module
import dayu.engine._default_runner as default_runner_module
from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.tool_call import BatchToolExecutionRequest
from dayu.contracts.tool_outcome import (
    BatchToolExecutionOutcome,
    BatchToolExecutionRecord,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure
from dayu.engine.agent import _AsyncAgent
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.agent_run import (
    AgentRunRequest,
    EngineRunOutcomeCancelled,
    EngineRunOutcomeFailed,
    EngineRunOutcomeFinalAnswer,
    EngineRunOutcomeSuspended,
)
from dayu.engine.contracts.error_codes import (
    EngineErrorCode,
    EngineRunErrorCode,
    RunnerSpecificErrorCode,
    RunnerSpecificErrorSource,
    adapter_error_code,
    runner_protocol_error_code,
    serialize_engine_error_code,
)
from dayu.engine.contracts.engine_events import (
    ContextCompactionRequestedData,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    IterationCompletedData,
    ProviderDiagnosticData,
    RUN_SUSPENDED_REASON_TOOL_AWAITING,
    RunCancelledData,
    RunFailedData,
    RunSuspendedData,
    TERMINAL_ENGINE_EVENT_TYPES,
    ToolCallDeltaData,
    UsageReportedData,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import (
    AgentMessage,
    AgentMessageRole,
    UserMessage,
)
from dayu.engine.contracts.runner import AsyncRunner
from dayu.engine.contracts.runner_events import (
    ContextOverflowDetection,
    ContextOverflowDetectionKind,
    RunnerContentCompletedData,
    RunnerContentDeltaData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventData,
    RunnerEventType,
    RunnerHTTPErrorCode,
    RunnerHTTPErrorData,
    RunnerProtocolErrorData,
    RunnerProviderDiagnosticData,
    RunnerDiagnosticSeverity,
    RunnerDiagnosticSource,
    RunnerReasoningDeltaData,
    RunnerToolCallDeltaData,
    RunnerToolCallsCompletedData,
    RunnerUsageRecordedData,
)
from dayu.engine.contracts.runner_identity import RunnerRequestIdentity
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
from dayu.contracts.tool_await import (
    ToolAwaitKind,
    ToolAwaitSnapshot,
    ToolAwaitSpec,
)
from dayu.contracts.tool_call import ToolCallRequest
from dayu.engine.contracts.tool_records import (
    AssistantToolCallBatchSnapshot,
    AwaitingToolExecutionRecord,
)
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from tests.host.fake_cancellation import ControllableCancellationToken

_TOOL_EXECUTION_TIMEOUT_SECONDS: float = 5.0
_CONTINUATION_MAX_ATTEMPTS: int = 3


def _assert_engine_run_error_code(
    actual: EngineErrorCode, expected: EngineRunErrorCode
) -> None:
    """断言 Engine-owned 失败码保持枚举身份并可序列化。

    :param actual: 被测失败码。
    :param expected: 期望的 Engine-owned 失败码枚举成员。
    :returns: 无返回值。
    :raises AssertionError: 失败码身份或序列化文本不符合预期时抛出。
    """

    assert actual is expected
    assert serialize_engine_error_code(actual) == expected.value


def _assert_runner_specific_error_code(
    actual: EngineErrorCode,
    *,
    expected_value: str,
    expected_source: RunnerSpecificErrorSource,
) -> None:
    """断言 provider / runner 专有失败码保持 wrapper 类型与来源。

    :param actual: 被测失败码。
    :param expected_value: 期望的序列化文本。
    :param expected_source: 期望的失败码来源闭集成员。
    :returns: 无返回值。
    :raises AssertionError: 失败码类型、来源或序列化文本不符合预期时抛出。
    """

    assert isinstance(actual, RunnerSpecificErrorCode)
    assert actual.source is expected_source
    assert serialize_engine_error_code(actual) == expected_value


def _utc_now() -> datetime:
    """返回测试用 UTC 当前时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


class _NoopToolExecutor:
    """测试用 no-op ToolExecutor。"""

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """返回失败 outcome，防止 Phase 2 误执行工具。

        :param request: 批式工具执行请求。
        :returns: 与输入 ``calls`` 一一对应的失败 outcome 批次。
        :raises Exception: 不主动抛出异常。
        """

        records = tuple(
            BatchToolExecutionRecord(
                tool_call_id=call.tool_call_id,
                outcome=ToolFailedOutcome(
                    result=ToolResultFailure(
                        ok=False,
                        error="unexpected_tool_execution",
                        message=call.name,
                        hint=None,
                        meta=None,
                    )
                ),
            )
            for call in request.calls
        )
        return BatchToolExecutionOutcome(records=records)


@dataclass(slots=True)
class _ScriptedRunner:
    """按脚本产出 RunnerEvent 的 fake Runner。"""

    events: tuple[RunnerEvent, ...]
    token_to_cancel_after_event_index: int | None = None
    token: ControllableCancellationToken | None = None
    raise_on_call: bool = False
    raise_on_close: bool = False
    raise_cancelled_on_close: bool = False
    block_after_first_event: bool = False
    close_count: int = 0
    call_count: int = 0
    close_completed_at: datetime | None = None
    tools_seen: tuple[ToolSchema, ...] = ()
    request_identities_seen: list[RunnerRequestIdentity | None] = field(
        default_factory=list
    )
    release_event: asyncio.Event = field(default_factory=asyncio.Event)

    def call(
        self,
        messages: Sequence[AgentMessage],
        options: RunnerCallOptions,
        tools: Sequence[ToolSchema],
        *,
        request_identity: RunnerRequestIdentity | None,
    ) -> AsyncIterator[RunnerEvent]:
        """返回脚本化 RunnerEvent 流。

        :param messages: Agent 消息。
        :param options: Runner 调用选项。
        :param tools: 暴露给模型的工具 schema。
        :param request_identity: 本次逻辑 Runner 调用的请求身份。
        :returns: RunnerEvent 异步流。
        :raises RuntimeError: 配置 ``raise_on_call`` 时抛出。
        """

        del messages, options
        self.call_count += 1
        self.tools_seen = tuple(tools)
        self.request_identities_seen.append(request_identity)
        return self._iter_events()

    def is_supports_tool_calling(self) -> bool:
        """声明支持工具调用。

        :returns: ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return True

    async def close(self) -> None:
        """记录 close 调用。

        :returns: 无返回值。
        :raises asyncio.CancelledError: 配置 ``raise_cancelled_on_close`` 时抛出。
        :raises RuntimeError: 配置 ``raise_on_close`` 时抛出。
        """

        self.close_count += 1
        self.close_completed_at = _utc_now()
        if self.raise_cancelled_on_close:
            raise asyncio.CancelledError()
        if self.raise_on_close:
            raise RuntimeError("close failed")

    async def _iter_events(self) -> AsyncIterator[RunnerEvent]:
        """产出脚本事件。

        :returns: RunnerEvent 异步流。
        :raises RuntimeError: 配置 ``raise_on_call`` 时抛出。
        """

        if self.raise_on_call:
            raise RuntimeError("runner exploded")
        for index, event in enumerate(self.events):
            yield event
            if (
                self.token_to_cancel_after_event_index is not None
                and self.token is not None
                and index == self.token_to_cancel_after_event_index
            ):
                self.token.request_cancel()
            if index == 0 and self.block_after_first_event:
                await self.release_event.wait()


class _PublicEntryDefaultRunner:
    """测试 public entry 默认 Runner 装配与关闭的 fake OpenAI Runner。"""

    constructed: list["_PublicEntryDefaultRunner"] = []

    def __init__(
        self,
        *,
        spec: RunnerSpec,
        cancellation_token: CancellationToken,
    ) -> None:
        """记录默认 Runner 构造参数。

        :param spec: Runner 规约。
        :param cancellation_token: 取消 token。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.spec: RunnerSpec = spec
        self.cancellation_token: CancellationToken = cancellation_token
        self.close_count: int = 0
        type(self).constructed.append(self)

    def call(
        self,
        messages: Sequence[AgentMessage],
        options: RunnerCallOptions,
        tools: Sequence[ToolSchema],
        *,
        request_identity: RunnerRequestIdentity | None,
    ) -> AsyncIterator[RunnerEvent]:
        """返回空 RunnerEvent 流。

        :param messages: Agent 消息。
        :param options: Runner 调用选项。
        :param tools: 暴露给模型的工具 schema。
        :param request_identity: 本次逻辑 Runner 调用的请求身份。
        :returns: 空 RunnerEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        del messages, options, tools, request_identity
        return self._iter_events()

    def is_supports_tool_calling(self) -> bool:
        """声明支持工具调用。

        :returns: ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return True

    async def close(self) -> None:
        """记录 close 调用。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.close_count += 1

    async def _iter_events(self) -> AsyncIterator[RunnerEvent]:
        """产出空事件流。

        :returns: 空 RunnerEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        events: tuple[RunnerEvent, ...] = ()
        for event in events:
            yield event


class _ExplodingDefaultRunner:
    """若 ``_AsyncAgent`` 误走默认 Runner 装配，本类会使测试失败。"""

    def __init__(
        self,
        *,
        spec: RunnerSpec,
        cancellation_token: CancellationToken,
    ) -> None:
        """阻止测试误实例化默认 Runner。

        :param spec: Runner 规约。
        :param cancellation_token: 取消 token。
        :returns: 无返回值。
        :raises AssertionError: 始终抛出，表示走错路径。
        """

        raise AssertionError("_AsyncAgent must use the injected runner")


def _event(event_type: RunnerEventType, data: RunnerEventData) -> RunnerEvent:
    """构造 RunnerEvent。

    :param event_type: RunnerEventType。
    :param data: RunnerEvent data。
    :returns: RunnerEvent。
    :raises Exception: 不主动抛出异常。
    """

    return RunnerEvent(
        type=event_type,
        data=data,
        occurred_at=_utc_now(),
    )


def _request(
    *,
    token: ControllableCancellationToken | None = None,
    max_iterations: int = 1,
    tool_schemas: tuple[ToolSchema, ...] = (),
) -> AgentRunRequest:
    """构造 AgentRunRequest。

    :param token: cancellation token。
    :param max_iterations: 最大迭代次数。
    :param tool_schemas: 工具 schema。
    :returns: AgentRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    actual_token = token or ControllableCancellationToken()
    return AgentRunRequest(
        run_id="run_phase2",
        session_id="session_phase2",
        messages=(
            UserMessage(role=AgentMessageRole.USER, content="hello"),
        ),
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
            stream=True,
        ),
        agent_policy=AgentPolicy(
            max_iterations=max_iterations,
            continuation_max_attempts=_CONTINUATION_MAX_ATTEMPTS,
            allow_tool_calls=True,
            tool_execution_timeout_seconds=_TOOL_EXECUTION_TIMEOUT_SECONDS,
            fallback_prompt="test fallback prompt",
            continuation_prompt="test continuation prompt",
        ),
        tool_schemas=tool_schemas,
        tool_executor=_NoopToolExecutor(),
        cancellation_token=actual_token,
        attempt_id="attempt_phase2",
        execution_id="execution_phase2",
    )


async def _collect(agent: _AsyncAgent) -> list[EngineEvent]:
    """收集 Agent 事件流。

    :param agent: 私有 Agent。
    :returns: EngineEvent 列表。
    :raises Exception: 透传 Agent 运行异常。
    """

    events: list[EngineEvent] = []
    async for event in agent.run_messages():
        events.append(event)
    return events


def _final_event(events: Sequence[EngineEvent]) -> EngineEvent:
    """返回最后一个事件。

    :param events: EngineEvent 序列。
    :returns: 最后一个事件。
    :raises AssertionError: 事件列表为空时抛出。
    """

    assert events
    return events[-1]


def _assert_single_terminal_at_end(events: Sequence[EngineEvent]) -> None:
    """断言 EngineEvent 流只有一个终态事件且终态位于最后。

    :param events: 完整收集到的 EngineEvent 序列。
    :returns: 无返回值。
    :raises AssertionError: 事件流为空、终态数量不为一或终态不是最后一个时抛出。
    """

    assert events
    terminal_events = [
        event for event in events if event.type in TERMINAL_ENGINE_EVENT_TYPES
    ]
    assert len(terminal_events) == 1
    assert terminal_events[0] is events[-1]


@pytest.mark.asyncio
async def test_success_run_lifts_runner_events_and_agent_final() -> None:
    """无工具成功 run 会提升 RunnerEvent 并由 Agent 产出 final_answer。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_DELTA,
                RunnerContentDeltaData(delta="你"),
            ),
            _event(
                RunnerEventType.RUNNER_REASONING_DELTA,
                RunnerReasoningDeltaData(delta="想"),
            ),
            _event(
                RunnerEventType.RUNNER_USAGE_RECORDED,
                RunnerUsageRecordedData(
                    prompt_tokens=1,
                    completion_tokens=2,
                    total_tokens=3,
                    provider_request_id="req-usage",
                ),
            ),
            _event(
                RunnerEventType.RUNNER_CONTENT_COMPLETED,
                RunnerContentCompletedData(
                    content="你好",
                    reasoning_content="想",
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.STOP, provider_request_id=None),
            ),
        )
    )
    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert [event.type for event in events] == [
        EngineEventType.ITERATION_STARTED,
        EngineEventType.CONTENT_DELTA,
        EngineEventType.REASONING_DELTA,
        EngineEventType.USAGE_REPORTED,
        EngineEventType.CONTENT_COMPLETED,
        EngineEventType.ITERATION_COMPLETED,
        EngineEventType.FINAL_ANSWER,
    ]
    final = _final_event(events)
    assert isinstance(final.data, FinalAnswerData)
    assert final.data.content == "你好"
    assert final.data.degraded is False
    assert {event.session_id for event in events} == {"session_phase2"}
    assert {event.run_id for event in events} == {"run_phase2"}
    assert runner.close_count == 1
    assert len(runner.request_identities_seen) == 1
    request_identity = runner.request_identities_seen[0]
    assert request_identity is not None
    assert request_identity.run_id == "run_phase2"
    assert request_identity.attempt_id == "attempt_phase2"
    assert request_identity.execution_id == "execution_phase2"
    assert request_identity.iteration_id == "run_phase2_iteration_1"
    assert request_identity.iteration_index == 0
    assert request_identity.runner_call_index == 1
    assert request_identity.client_correlation_id.startswith("dayu-")
    iteration_completed = [
        event
        for event in events
        if event.type is EngineEventType.ITERATION_COMPLETED
    ]
    assert len(iteration_completed) == 1
    assert isinstance(iteration_completed[0].data, IterationCompletedData)
    assert (
        iteration_completed[0].data.client_correlation_id
        == request_identity.client_correlation_id
    )
    usage_reported = [
        event for event in events if event.type is EngineEventType.USAGE_REPORTED
    ]
    assert len(usage_reported) == 1
    assert isinstance(usage_reported[0].data, UsageReportedData)
    assert usage_reported[0].data.provider_request_id == "req-usage"
    _assert_single_terminal_at_end(events)


@pytest.mark.asyncio
async def test_runner_done_finish_reason_is_authority(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """RunnerDoneData.finish_reason 是唯一迭代完成原因真源。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_COMPLETED,
                RunnerContentCompletedData(
                    content="partial",
                    reasoning_content=None,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(
                    finish_reason=FinishReason.LENGTH,
                    provider_request_id="req-mismatch",
                ),
            ),
        )
    )
    caplog.set_level(logging.WARNING, logger="dayu.engine.agent")

    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert not any(
        "engine.agent.finish_reason_mismatch" in record.getMessage()
        for record in caplog.records
    )
    iteration_completed = [
        event for event in events
        if event.type is EngineEventType.ITERATION_COMPLETED
    ]
    assert len(iteration_completed) == 1
    assert isinstance(iteration_completed[0].data, IterationCompletedData)
    assert iteration_completed[0].data.finish_reason is FinishReason.LENGTH


@pytest.mark.asyncio
async def test_async_agent_uses_injected_runner_without_default_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_AsyncAgent`` 主链路只消费注入的 ``AsyncRunner`` 协议实例。"""

    monkeypatch.setattr(
        default_runner_module,
        "AsyncOpenAIRunner",
        _ExplodingDefaultRunner,
    )
    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_COMPLETED,
                RunnerContentCompletedData(
                    content="ok",
                    reasoning_content=None,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(
                    finish_reason=FinishReason.STOP,
                    provider_request_id=None,
                ),
            ),
        )
    )

    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert runner.call_count == 1
    assert runner.close_count == 1
    assert _final_event(events).type is EngineEventType.FINAL_ANSWER


@pytest.mark.asyncio
async def test_phase2_passes_empty_tools_even_when_request_has_schema() -> None:
    """Phase 2 不把 request.tool_schemas 暴露给 Runner。"""

    schema = ToolSchema(
        type="function",
        function=ToolFunctionSchema(
            name="lookup",
            description="lookup",
            parameters=ToolParametersSchema(
                type="object",
                properties={},
                required=(),
                additional_properties=False,
            ),
        ),
    )
    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_COMPLETED,
                RunnerContentCompletedData(
                    content="ok",
                    reasoning_content=None,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.STOP, provider_request_id=None),
            ),
        )
    )

    await _collect(
        _AsyncAgent(
            request=_request(tool_schemas=(schema,)),
            runner=runner,
        )
    )

    assert runner.tools_seen == ()


@pytest.mark.asyncio
async def test_protocol_error_and_error_done_maps_to_run_failed() -> None:
    """provider protocol error 会提升协议错误并收口 run_failed。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.PROVIDER_PROTOCOL_ERROR,
                RunnerProtocolErrorData(
                    error_code=runner_protocol_error_code("bad_sse"),
                    message="bad stream",
                    provider_request_id="req_1",
                    raw_payload={"type": "bad"},
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(
                    finish_reason=FinishReason.ERROR,
                    provider_request_id="req_1",
                ),
            ),
        )
    )
    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert events[-2].type is EngineEventType.ITERATION_COMPLETED
    terminal = _final_event(events)
    assert terminal.type is EngineEventType.RUN_FAILED
    assert isinstance(terminal.data, RunFailedData)
    _assert_runner_specific_error_code(
        terminal.data.error_code,
        expected_value="bad_sse",
        expected_source=RunnerSpecificErrorSource.RUNNER_PROTOCOL,
    )
    assert isinstance(events[-2].data, IterationCompletedData)
    assert events[-2].data.provider_request_id == "req_1"
    assert terminal.data.provider_request_id == "req_1"
    _assert_single_terminal_at_end(events)


@pytest.mark.asyncio
async def test_provider_diagnostic_does_not_create_failure_candidate() -> None:
    """Runner 非致命诊断提升为 Engine diagnostic，不影响成功终态。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.PROVIDER_DIAGNOSTIC,
                RunnerProviderDiagnosticData(
                    diagnostic_code="usage_field_malformed",
                    severity=RunnerDiagnosticSeverity.WARNING,
                    message="usage ignored",
                    provider_request_id="req_diag",
                    raw_payload={"prompt_tokens_type": "str"},
                    diagnostic_source=RunnerDiagnosticSource.SSE_PARSER,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_CONTENT_COMPLETED,
                RunnerContentCompletedData(
                    content="ok",
                    reasoning_content=None,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(
                    finish_reason=FinishReason.STOP,
                    provider_request_id="req_diag",
                ),
            ),
        )
    )

    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert [event.type for event in events] == [
        EngineEventType.ITERATION_STARTED,
        EngineEventType.PROVIDER_DIAGNOSTIC,
        EngineEventType.CONTENT_COMPLETED,
        EngineEventType.ITERATION_COMPLETED,
        EngineEventType.FINAL_ANSWER,
    ]
    diagnostic = events[1].data
    assert isinstance(diagnostic, ProviderDiagnosticData)
    assert diagnostic.diagnostic_code == "usage_field_malformed"
    assert diagnostic.severity is RunnerDiagnosticSeverity.WARNING
    assert diagnostic.diagnostic_source is RunnerDiagnosticSource.SSE_PARSER
    assert diagnostic.provider_request_id == "req_diag"
    assert events[-1].type is EngineEventType.FINAL_ANSWER
    _assert_single_terminal_at_end(events)


@pytest.mark.asyncio
async def test_http_error_maps_to_run_failed_without_extra_engine_event() -> None:
    """HTTP error 记录失败候选，经迭代完成事件收口 run_failed。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_HTTP_ERROR,
                RunnerHTTPErrorData(
                    error_code=RunnerHTTPErrorCode.RATE_LIMIT_EXCEEDED,
                    http_status=429,
                    message="rate limited",
                    provider_request_id="req_http",
                    raw_payload=None,
                    attempt=1,
                    retried=False,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(
                    finish_reason=FinishReason.ERROR,
                    provider_request_id="req_http",
                ),
            ),
        )
    )
    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert [event.type for event in events] == [
        EngineEventType.ITERATION_STARTED,
        EngineEventType.ITERATION_COMPLETED,
        EngineEventType.RUN_FAILED,
    ]
    assert isinstance(events[-1].data, RunFailedData)
    _assert_runner_specific_error_code(
        events[-1].data.error_code,
        expected_value="rate_limit_exceeded",
        expected_source=RunnerSpecificErrorSource.ADAPTER,
    )
    assert isinstance(events[-2].data, IterationCompletedData)
    assert events[-2].data.provider_request_id == "req_http"
    assert events[-1].data.provider_request_id == "req_http"


@pytest.mark.asyncio
async def test_context_overflow_http_error_maps_to_compaction_required_fact() -> None:
    """Runner context overflow 只生成强类型事实，不在 Engine 内 compact。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_HTTP_ERROR,
                RunnerHTTPErrorData(
                    error_code=RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED,
                    http_status=400,
                    message="maximum context length is 128000 tokens",
                    provider_request_id="req_context",
                    raw_payload=None,
                    attempt=1,
                    retried=False,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(
                    finish_reason=FinishReason.ERROR,
                    provider_request_id="req_context",
                ),
            ),
        )
    )
    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert [event.type for event in events] == [
        EngineEventType.ITERATION_STARTED,
        EngineEventType.CONTEXT_COMPACTION_REQUESTED,
        EngineEventType.ITERATION_COMPLETED,
        EngineEventType.RUN_FAILED,
    ]
    compact_event = events[1]
    assert isinstance(compact_event.data, ContextCompactionRequestedData)
    assert compact_event.data.budget_state is None
    assert compact_event.data.provider_request_id == "req_context"
    assert isinstance(events[-2].data, IterationCompletedData)
    assert events[-2].data.provider_request_id == "req_context"
    terminal = events[-1]
    assert isinstance(terminal.data, RunFailedData)
    _assert_engine_run_error_code(
        terminal.data.error_code,
        EngineRunErrorCode.CONTEXT_COMPACTION_REQUIRED,
    )
    assert terminal.data.provider_request_id == "req_context"
    assert terminal.data.recoverable


@pytest.mark.asyncio
async def test_context_overflow_without_detection_emits_only_compaction_request() -> None:
    """typed context overflow 无检测来源时不生成 provider diagnostic。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_HTTP_ERROR,
                RunnerHTTPErrorData(
                    error_code=RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED,
                    http_status=400,
                    message="maximum context length is 128000 tokens",
                    provider_request_id="req_context_no_detection",
                    raw_payload=None,
                    attempt=1,
                    retried=False,
                    context_overflow_detection=None,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(
                    finish_reason=FinishReason.ERROR,
                    provider_request_id="req_context_no_detection",
                ),
            ),
        )
    )

    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert [event.type for event in events] == [
        EngineEventType.ITERATION_STARTED,
        EngineEventType.CONTEXT_COMPACTION_REQUESTED,
        EngineEventType.ITERATION_COMPLETED,
        EngineEventType.RUN_FAILED,
    ]
    assert EngineEventType.PROVIDER_DIAGNOSTIC not in {
        event.type for event in events
    }
    compact_event = events[1]
    assert isinstance(compact_event.data, ContextCompactionRequestedData)
    assert compact_event.data.provider_request_id == "req_context_no_detection"


@pytest.mark.asyncio
async def test_context_overflow_marker_fallback_emits_nonfatal_diagnostic() -> None:
    """message marker fallback provenance 进入 diagnostic，不替代压缩事实。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_HTTP_ERROR,
                RunnerHTTPErrorData(
                    error_code=RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED,
                    http_status=400,
                    message="context length exceeded",
                    provider_request_id="req_context_marker",
                    raw_payload=None,
                    attempt=1,
                    retried=False,
                    context_overflow_detection=ContextOverflowDetection(
                        kind=(
                            ContextOverflowDetectionKind.MESSAGE_MARKER_FALLBACK
                        ),
                        diagnostic_code=(
                            "context_overflow_message_marker_fallback"
                        ),
                        message="marker fallback detected context overflow",
                        raw_payload={"detection_kind": "message_marker_fallback"},
                    ),
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(
                    finish_reason=FinishReason.ERROR,
                    provider_request_id="req_context_marker",
                ),
            ),
        )
    )

    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert [event.type for event in events] == [
        EngineEventType.ITERATION_STARTED,
        EngineEventType.PROVIDER_DIAGNOSTIC,
        EngineEventType.CONTEXT_COMPACTION_REQUESTED,
        EngineEventType.ITERATION_COMPLETED,
        EngineEventType.RUN_FAILED,
    ]
    diagnostic = events[1].data
    assert isinstance(diagnostic, ProviderDiagnosticData)
    assert diagnostic.diagnostic_source is (
        RunnerDiagnosticSource.CONTEXT_OVERFLOW_CLASSIFIER
    )
    assert diagnostic.diagnostic_code == (
        "context_overflow_message_marker_fallback"
    )
    compact = events[2].data
    assert isinstance(compact, ContextCompactionRequestedData)
    assert compact.provider_request_id == "req_context_marker"
    terminal = events[-1].data
    assert isinstance(terminal, RunFailedData)
    _assert_engine_run_error_code(
        terminal.error_code,
        EngineRunErrorCode.CONTEXT_COMPACTION_REQUIRED,
    )
    assert terminal.recoverable


@pytest.mark.asyncio
async def test_bare_error_done_maps_to_specific_run_failed() -> None:
    """裸 RunnerDone(ERROR) 不能落入 final_answer。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.ERROR, provider_request_id=None),
            ),
        )
    )
    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    terminal = _final_event(events)
    assert terminal.type is EngineEventType.RUN_FAILED
    assert isinstance(terminal.data, RunFailedData)
    _assert_engine_run_error_code(
        terminal.data.error_code,
        EngineRunErrorCode.RUNNER_ERROR_DONE_WITHOUT_DETAIL,
    )
    assert terminal.data.provider_request_id is None


@pytest.mark.asyncio
async def test_runner_exception_maps_to_run_failed_and_closes() -> None:
    """Runner 普通异常映射 run_failed 且 close Runner。"""

    runner = _ScriptedRunner(events=(), raise_on_call=True)
    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert _final_event(events).type is EngineEventType.RUN_FAILED
    assert isinstance(events[-1].data, RunFailedData)
    _assert_engine_run_error_code(
        events[-1].data.error_code,
        EngineRunErrorCode.RUNNER_EXCEPTION,
    )
    assert runner.close_count == 1


def test_exception_diagnostic_message_marks_truncation() -> None:
    """异常诊断消息被截断时必须显式携带截断标记。"""

    message = agent_module._exception_diagnostic_message(
        RuntimeError("x" * 500)
    )

    assert message.startswith("RuntimeError: ")
    assert message.endswith("... [truncated]")
    assert (
        len(message.removeprefix("RuntimeError: "))
        == agent_module._EXCEPTION_MESSAGE_MAX_LENGTH
    )


def test_exception_diagnostic_message_redacts_api_key_with_space() -> None:
    """异常诊断消息必须识别 ``api key`` 空格写法。"""

    message = agent_module._exception_diagnostic_message(
        RuntimeError("provider rejected api key sk-secret-value")
    )

    assert message == "RuntimeError: exception message redacted"
    assert "sk-secret-value" not in message


@pytest.mark.parametrize(
    "raw_message",
    (
        "JWT token has expired",
        "Content-Type header is invalid",
    ),
)
def test_exception_diagnostic_message_preserves_normal_token_and_header_words(
    raw_message: str,
) -> None:
    """异常诊断保留不含 secret 值的 token/header 普通诊断词。"""

    message = agent_module._exception_diagnostic_message(
        RuntimeError(raw_message)
    )

    assert message == f"RuntimeError: {raw_message}"


@pytest.mark.parametrize(
    "raw_message",
    (
        "provider rejected Bearer sk-secret-value",
        "provider rejected API key sk-secret-value",
        "provider rejected api_key=sk-secret-value",
        "provider rejected api-key:sk-secret-value",
        "provider rejected apikey=sk-secret-value",
        "provider rejected authorization=sk-secret-value",
        "provider rejected password=sk-secret-value",
        "provider rejected secret=sk-secret-value",
        "provider rejected token=sk-secret-value",
    ),
)
def test_exception_diagnostic_message_redacts_sensitive_value_patterns(
    raw_message: str,
) -> None:
    """异常诊断只要包含疑似 secret 明文值就整条脱敏。"""

    message = agent_module._exception_diagnostic_message(
        RuntimeError(raw_message)
    )

    assert message == "RuntimeError: exception message redacted"
    assert "sk-secret-value" not in message


@pytest.mark.parametrize(
    "raw_message",
    (
        "provider rejected api_key=;",
        "provider rejected token=;",
    ),
)
def test_exception_diagnostic_message_redacts_semicolon_value_start(
    raw_message: str,
) -> None:
    """异常诊断保留分号 value start 的整条脱敏语义。

    :param raw_message: 以分号作为敏感 value 起点的异常消息。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    message = agent_module._exception_diagnostic_message(
        RuntimeError(raw_message)
    )

    assert message == "RuntimeError: exception message redacted"


@pytest.mark.parametrize(
    "raw_message",
    (
        "provider rejected api_key=}",
        "provider rejected api_key=]",
        "provider rejected token=}",
        "provider rejected token=]",
        "provider rejected Bearer }",
        "provider rejected Bearer ]",
    ),
)
def test_exception_diagnostic_message_preserves_closing_punctuation_start(
    raw_message: str,
) -> None:
    """异常诊断不把右括号类 value start 误判为敏感值。

    :param raw_message: 以右括号类标点作为 value 起点的异常消息。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    message = agent_module._exception_diagnostic_message(
        RuntimeError(raw_message)
    )

    assert message == f"RuntimeError: {raw_message}"


@pytest.mark.parametrize("raw_message", ("", "   ", "\t\n"))
def test_safe_log_message_redacts_blank_or_whitespace(raw_message: str) -> None:
    """日志安全摘要对空白消息使用固定脱敏文本。

    :param raw_message: 空字符串或空白字符串。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    assert (
        agent_module._safe_log_message(raw_message)
        == "exception message redacted"
    )


@pytest.mark.parametrize(
    "raw_message",
    (
        "provider rejected Bearer sk-secret-value",
        "provider rejected api-key:sk-secret-value",
        "provider rejected token=sk-secret-value",
        "provider rejected api_key=;",
    ),
)
def test_safe_log_message_redacts_sensitive_message_whole(
    raw_message: str,
) -> None:
    """日志安全摘要命中敏感值时必须整条替换。

    :param raw_message: 携带敏感值的原始日志消息。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    message = agent_module._safe_log_message(raw_message)

    assert message == "exception message redacted"
    assert "sk-secret-value" not in message


def test_safe_log_message_truncates_ordinary_long_message() -> None:
    """日志安全摘要对普通长消息使用 Engine suffix 截断。

    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    message = agent_module._safe_log_message("x" * 500)

    assert message.endswith("... [truncated]")
    assert len(message) == agent_module._EXCEPTION_MESSAGE_MAX_LENGTH


@pytest.mark.parametrize(
    "raw_message",
    (
        "JWT token has expired",
        "Content-Type header is invalid",
        "provider rejected token=}",
        "provider rejected Bearer ]",
    ),
)
def test_safe_log_message_preserves_false_positive_guards(
    raw_message: str,
) -> None:
    """日志安全摘要保留非敏感普通诊断文本。

    :param raw_message: 不应被识别为敏感值的日志消息。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    assert agent_module._safe_log_message(raw_message) == raw_message


@pytest.mark.asyncio
async def test_cancelled_before_run_closes_then_emits_cancelled() -> None:
    """入口已取消时不调用 Runner，但先 close 再产出 run_cancelled。"""

    token = ControllableCancellationToken()
    token.request_cancel()
    runner = _ScriptedRunner(events=())
    events = await _collect(
        _AsyncAgent(request=_request(token=token), runner=runner)
    )

    terminal = _final_event(events)
    assert terminal.type is EngineEventType.RUN_CANCELLED
    assert isinstance(terminal.data, RunCancelledData)
    assert runner.call_count == 0
    assert runner.close_count == 1
    assert runner.close_completed_at is not None
    assert terminal.data.finished_at >= runner.close_completed_at
    _assert_single_terminal_at_end(events)


@pytest.mark.asyncio
async def test_runner_cancelled_naturally_without_done_maps_cancelled() -> None:
    """Runner 因取消自然结束且无 done 时由 Agent 收口 run_cancelled。"""

    token = ControllableCancellationToken()
    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_DELTA,
                RunnerContentDeltaData(delta="partial"),
            ),
        ),
        token_to_cancel_after_event_index=0,
        token=token,
    )
    events = await _collect(
        _AsyncAgent(request=_request(token=token), runner=runner)
    )

    assert _final_event(events).type is EngineEventType.RUN_CANCELLED
    assert EngineEventType.FINAL_ANSWER not in {event.type for event in events}


@pytest.mark.asyncio
async def test_cancel_before_final_answer_wins_over_final() -> None:
    """final_answer 前取消优先于最终回答。"""

    token = ControllableCancellationToken()
    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_COMPLETED,
                RunnerContentCompletedData(
                    content="should not final",
                    reasoning_content=None,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.STOP, provider_request_id=None),
            ),
        ),
        token_to_cancel_after_event_index=0,
        token=token,
    )
    events = await _collect(
        _AsyncAgent(request=_request(token=token), runner=runner)
    )

    assert _final_event(events).type is EngineEventType.RUN_CANCELLED
    assert EngineEventType.FINAL_ANSWER not in {event.type for event in events}


@pytest.mark.asyncio
async def test_provider_error_and_cancel_same_run_cancel_wins() -> None:
    """provider error 与取消同时出现时取消优先于 failure terminal。"""

    token = ControllableCancellationToken()
    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.PROVIDER_PROTOCOL_ERROR,
                RunnerProtocolErrorData(
                    error_code=runner_protocol_error_code("bad"),
                    message="bad",
                    provider_request_id=None,
                    raw_payload=None,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.ERROR, provider_request_id=None),
            ),
        ),
        token_to_cancel_after_event_index=0,
        token=token,
    )
    events = await _collect(
        _AsyncAgent(request=_request(token=token), runner=runner)
    )

    assert _final_event(events).type is EngineEventType.RUN_CANCELLED


@pytest.mark.asyncio
async def test_http_error_and_cancel_same_run_cancel_wins() -> None:
    """HTTP error 后若取消同时到达，取消优先于 failure terminal。"""

    token = ControllableCancellationToken()
    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_HTTP_ERROR,
                RunnerHTTPErrorData(
                    error_code=RunnerHTTPErrorCode.SERVER_ERROR,
                    http_status=503,
                    message="server busy",
                    provider_request_id=None,
                    raw_payload=None,
                    attempt=1,
                    retried=False,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.ERROR, provider_request_id=None),
            ),
        ),
        token_to_cancel_after_event_index=0,
        token=token,
    )
    events = await _collect(
        _AsyncAgent(request=_request(token=token), runner=runner)
    )

    assert _final_event(events).type is EngineEventType.RUN_CANCELLED


@pytest.mark.asyncio
async def test_close_error_does_not_override_terminal() -> None:
    """Runner close 失败不覆盖已确定 terminal。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_COMPLETED,
                RunnerContentCompletedData(
                    content="ok",
                    reasoning_content=None,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.STOP, provider_request_id=None),
            ),
        ),
        raise_on_close=True,
    )
    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert _final_event(events).type is EngineEventType.FINAL_ANSWER
    assert runner.close_count == 1
    assert _terminal_count(events) == 1


@pytest.mark.asyncio
async def test_close_runner_once_marks_closed_after_close_error() -> None:
    """Runner close 普通异常后仍按 once 语义禁止重复 close。"""

    runner = _ScriptedRunner(events=(), raise_on_close=True)
    agent = _AsyncAgent(request=_request(), runner=runner)

    await agent._close_runner_once()
    await agent._close_runner_once()

    assert runner.close_count == 1


@pytest.mark.asyncio
async def test_close_cancelled_error_releases_run_slot() -> None:
    """Runner close 若被取消，也必须释放私有 Agent 运行槽位。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_COMPLETED,
                RunnerContentCompletedData(
                    content="ok",
                    reasoning_content=None,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.STOP, provider_request_id=None),
            ),
        ),
        raise_cancelled_on_close=True,
    )
    agent = _AsyncAgent(request=_request(), runner=runner)

    with pytest.raises(asyncio.CancelledError):
        await _collect(agent)

    assert runner.close_count == 1
    assert agent._active_run_id is None


@pytest.mark.asyncio
async def test_tool_call_delta_and_completed_fail_closed() -> None:
    """工具观测事件可见，但缺 Done 时仍 fail closed。"""

    completed_runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
                RunnerToolCallsCompletedData(
                    tool_calls=(
                        ToolCallRequest(
                            tool_call_id="tc_1",
                            name="lookup",
                            arguments={},
                            index_in_iteration=0,
                            provider_state=None,
                        ),
                    )
                ),
            ),
        )
    )
    delta_runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_TOOL_CALL_DELTA,
                RunnerToolCallDeltaData(
                    tool_call_index=0,
                    tool_call_id="tc_1",
                    name_delta="lookup",
                    arguments_delta="{}",
                ),
            ),
        )
    )

    for runner in (completed_runner, delta_runner):
        events = await _collect(_AsyncAgent(request=_request(), runner=runner))
        assert _final_event(events).type is EngineEventType.RUN_FAILED
        assert isinstance(events[-1].data, RunFailedData)
        _assert_engine_run_error_code(
            events[-1].data.error_code,
            EngineRunErrorCode.RUNNER_ABNORMAL_STOP,
        )
        assert EngineEventType.TOOL_CALL_REQUESTED not in {
            event.type for event in events
        }
    assert completed_runner.call_count == 1
    completed_events = await _collect(
        _AsyncAgent(request=_request(), runner=completed_runner)
    )
    ready_events = [
        event
        for event in completed_events
        if event.type is EngineEventType.TOOL_CALLS_BATCH_READY
    ]
    # fail-closed 路径下 executor 未被调用，TOOL_CALLS_BATCH_READY 不应出现。
    assert ready_events == []

    delta_events = await _collect(
        _AsyncAgent(request=_request(), runner=delta_runner)
    )
    tool_delta_events = [
        event
        for event in delta_events
        if event.type is EngineEventType.TOOL_CALL_DELTA
    ]
    assert len(tool_delta_events) == 1
    assert isinstance(tool_delta_events[0].data, ToolCallDeltaData)
    assert tool_delta_events[0].data.arguments_delta == "{}"


@pytest.mark.asyncio
async def test_length_and_content_filter_final_boundaries() -> None:
    """LENGTH 无续写预算时降级 final；CONTENT_FILTER 不消费 continuation。"""

    for finish_reason in (FinishReason.LENGTH, FinishReason.CONTENT_FILTER):
        runner = _ScriptedRunner(
            events=(
                _event(
                    RunnerEventType.RUNNER_CONTENT_COMPLETED,
                    RunnerContentCompletedData(
                        content="partial",
                        reasoning_content=None,
                    ),
                ),
                _event(
                    RunnerEventType.RUNNER_DONE,
                    RunnerDoneData(finish_reason=finish_reason, provider_request_id=None),
                ),
            )
        )
        events = await _collect(_AsyncAgent(request=_request(), runner=runner))
        assert _final_event(events).type is EngineEventType.FINAL_ANSWER
        assert isinstance(events[-1].data, FinalAnswerData)
        assert events[-1].data.finish_reason is finish_reason
        assert events[-1].data.filtered is (
            finish_reason is FinishReason.CONTENT_FILTER
        )
        assert events[-1].data.degraded is True
        assert runner.call_count == 1


@pytest.mark.asyncio
async def test_content_filter_final_logs_bounded_provider_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """内容过滤收口时 DEBUG 日志提供有界 provider 提示文本。

    :param caplog: pytest 日志捕获夹具。
    :returns: 无返回值。
    :raises AssertionError: 诊断日志缺少过滤原因或回答预览时抛出。
    """

    provider_message = (
        "The request was rejected because it was considered high risk"
    )
    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_COMPLETED,
                RunnerContentCompletedData(
                    content=provider_message,
                    reasoning_content=None,
                ),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(
                    finish_reason=FinishReason.CONTENT_FILTER,
                    provider_request_id=None,
                ),
            ),
        )
    )

    caplog.set_level(logging.DEBUG, logger=agent_module.__name__)
    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert _final_event(events).type is EngineEventType.FINAL_ANSWER
    diagnostic_messages = [
        record.getMessage()
        for record in caplog.records
        if "engine.agent.filtered_final_diagnostic" in record.getMessage()
    ]
    assert len(diagnostic_messages) == 1
    diagnostic = diagnostic_messages[0]
    assert "finish_reason=content_filter" in diagnostic
    assert "degraded=True" in diagnostic
    assert f"content_chars={len(provider_message)}" in diagnostic
    assert f"answer_preview={provider_message}" in diagnostic


@pytest.mark.asyncio
async def test_abnormal_stop_and_max_iterations_fail() -> None:
    """无 done 异常结束触发 run_failed；``max_iterations<1`` 在 contract 构造期被拒。"""

    abnormal = await _collect(
        _AsyncAgent(
            request=_request(),
            runner=_ScriptedRunner(
                events=(
                    _event(
                        RunnerEventType.RUNNER_CONTENT_DELTA,
                        RunnerContentDeltaData(delta="partial"),
                    ),
                )
            ),
        )
    )
    assert isinstance(abnormal[-1].data, RunFailedData)
    _assert_engine_run_error_code(
        abnormal[-1].data.error_code,
        EngineRunErrorCode.RUNNER_ABNORMAL_STOP,
    )

    exceeded = await _collect(
        _AsyncAgent(
            request=_request(),
            runner=_ScriptedRunner(events=()),
        )
    )
    assert isinstance(exceeded[-1].data, RunFailedData)

    # AgentPolicy 在构造期直接拒绝 ``max_iterations < 1``，
    # 防止非法策略对象在系统中传递。
    with pytest.raises(ValueError):
        AgentPolicy(
            max_iterations=0,
            continuation_max_attempts=0,
            allow_tool_calls=False,
            tool_execution_timeout_seconds=1.0,
            fallback_prompt="test fallback prompt",
            continuation_prompt="test continuation prompt",
        )


@pytest.mark.asyncio
async def test_private_agent_concurrent_run_fail_fast() -> None:
    """同一私有 Agent 实例并发运行 fail-fast。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_DELTA,
                RunnerContentDeltaData(delta="hold"),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.STOP, provider_request_id=None),
            ),
        ),
        block_after_first_event=True,
    )
    agent = _AsyncAgent(request=_request(), runner=runner)
    first_event_seen = asyncio.Event()

    async def consume_first_run() -> None:
        """消费第一次运行。

        :returns: 无返回值。
        :raises Exception: 透传 Agent 运行异常。
        """

        async for event in agent.run_messages():
            if event.type is EngineEventType.CONTENT_DELTA:
                first_event_seen.set()

    task = asyncio.create_task(consume_first_run())
    await first_event_seen.wait()
    with pytest.raises(RuntimeError):
        async for _event_item in agent.run_messages():
            pass
    assert runner.close_count == 0
    runner.release_event.set()
    await task


@pytest.mark.asyncio
async def test_outer_asyncio_cancelled_error_propagates_and_closes() -> None:
    """外层 task cancel 必须透传 asyncio.CancelledError，并关闭 Runner。"""

    runner = _ScriptedRunner(
        events=(
            _event(
                RunnerEventType.RUNNER_CONTENT_DELTA,
                RunnerContentDeltaData(delta="hold"),
            ),
            _event(
                RunnerEventType.RUNNER_DONE,
                RunnerDoneData(finish_reason=FinishReason.STOP, provider_request_id=None),
            ),
        ),
        block_after_first_event=True,
    )
    agent = _AsyncAgent(request=_request(), runner=runner)
    first_event_seen = asyncio.Event()

    async def consume_until_cancelled() -> None:
        """消费事件流，直到外层 task 取消。

        :returns: 无返回值。
        :raises asyncio.CancelledError: 外层 task 被取消时透传。
        """

        async for event in agent.run_messages():
            if event.type is EngineEventType.CONTENT_DELTA:
                first_event_seen.set()

    task = asyncio.create_task(consume_until_cancelled())
    await first_event_seen.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert runner.close_count == 1


@pytest.mark.asyncio
async def test_run_agent_and_wait_maps_final_failed_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_agent_and_wait 映射 final / failed / cancelled 三类终态。"""

    request = _request()
    runners = [
        _ScriptedRunner(
            events=(
                _event(
                    RunnerEventType.RUNNER_CONTENT_COMPLETED,
                    RunnerContentCompletedData(
                        content="ok",
                        reasoning_content=None,
                    ),
                ),
                _event(
                    RunnerEventType.RUNNER_DONE,
                    RunnerDoneData(finish_reason=FinishReason.STOP, provider_request_id=None),
                ),
            )
        ),
        _ScriptedRunner(
            events=(
                _event(
                    RunnerEventType.RUNNER_DONE,
                    RunnerDoneData(finish_reason=FinishReason.ERROR, provider_request_id=None),
                ),
            )
        ),
        _ScriptedRunner(events=()),
    ]
    token = ControllableCancellationToken()
    token.request_cancel("stop")
    requests = [request, request, _request(token=token)]

    for runner, current_request, expected_type in zip(
        runners,
        requests,
        (
            EngineRunOutcomeFinalAnswer,
            EngineRunOutcomeFailed,
            EngineRunOutcomeCancelled,
        ),
        strict=True,
    ):
        monkeypatch.setattr(
            agent_module,
            "_build_runner",
            lambda ignored_request, selected_runner=runner: selected_runner,
        )
        result = await agent_module.run_agent_and_wait(current_request)
        assert isinstance(result, expected_type)


@pytest.mark.asyncio
async def test_run_agent_messages_builds_default_runner_and_closes_on_stream_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """public entry 使用当前默认 OpenAI-compatible Runner 装配并在关闭流时 close。"""

    _PublicEntryDefaultRunner.constructed.clear()
    monkeypatch.setattr(
        default_runner_module,
        "AsyncOpenAIRunner",
        _PublicEntryDefaultRunner,
    )
    request = _request()
    stream = agent_module.run_agent_messages(request)

    first_event = await anext(stream)
    await stream.aclose()

    assert first_event.type is EngineEventType.ITERATION_STARTED
    assert len(_PublicEntryDefaultRunner.constructed) == 1
    runner = _PublicEntryDefaultRunner.constructed[0]
    assert runner.spec is request.runner_spec
    assert runner.cancellation_token is request.cancellation_token
    assert runner.close_count == 1


@pytest.mark.asyncio
async def test_run_agent_and_wait_preserves_provider_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``RUN_FAILED`` 请求身份字段必须透传到 ``EngineRunOutcomeFailed``。"""

    request = _request()
    expected_provider_request_id = "req_provider_xyz"
    expected_client_correlation_id = "dayu-test-client-correlation"

    async def fake_messages(
        request: AgentRunRequest,
    ) -> AsyncIterator[EngineEvent]:
        """产出携带 provider_request_id 的 ``RUN_FAILED`` 终态。

        :param request: Agent run 请求。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        yield EngineEvent(
            occurred_at=_utc_now(),
            session_id=request.session_id,
            run_id=request.run_id,
            type=EngineEventType.RUN_FAILED,
            data=RunFailedData(
                error_code=adapter_error_code("provider_http_error"),
                message="provider failed",
                provider_request_id=expected_provider_request_id,
                client_correlation_id=expected_client_correlation_id,
                recoverable=False,
            ),
            metadata=None,
        )

    monkeypatch.setattr(agent_module, "run_agent_messages", fake_messages)
    result = await agent_module.run_agent_and_wait(request)

    assert isinstance(result, EngineRunOutcomeFailed)
    assert result.provider_request_id == expected_provider_request_id
    assert result.client_correlation_id == expected_client_correlation_id
    _assert_runner_specific_error_code(
        result.error_code,
        expected_value="provider_http_error",
        expected_source=RunnerSpecificErrorSource.ADAPTER,
    )


@pytest.mark.asyncio
async def test_run_agent_and_wait_maps_suspended(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_agent_and_wait 必须把 RUN_SUSPENDED 映射为 suspended outcome。"""

    await_spec = ToolAwaitSpec(
        await_kind=ToolAwaitKind.EXTERNAL_JOB,
        deadline=None,
        resume_token="resume",
    )
    snapshot = ToolAwaitSnapshot(
        snapshot_id="snapshot",
        captured_at=_utc_now(),
    )
    tool_call = ToolCallRequest(
        tool_call_id="tc_1",
        name="add_numbers",
        arguments={},
        index_in_iteration=0,
        provider_state=None,
    )
    batch_snapshot = AssistantToolCallBatchSnapshot(
        iteration_id="run_phase2_iteration_1",
        tool_calls=(tool_call,),
        content=None,
        reasoning_content=None,
        provider_request_id=None,
    )

    async def fake_messages(
        request: AgentRunRequest,
    ) -> AsyncIterator[EngineEvent]:
        """产出 suspended terminal。

        :param request: Agent run 请求。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        yield EngineEvent(
            occurred_at=_utc_now(),
            session_id=request.session_id,
            run_id=request.run_id,
            type=EngineEventType.RUN_SUSPENDED,
            data=RunSuspendedData(
                reason=RUN_SUSPENDED_REASON_TOOL_AWAITING,
                resume_hint=None,
                accepted_records=(),
                awaiting_records=(
                    AwaitingToolExecutionRecord(
                        batch_snapshot=batch_snapshot,
                        call=tool_call,
                        await_spec=await_spec,
                        snapshot=snapshot,
                    ),
                ),
            ),
            metadata=None,
        )

    monkeypatch.setattr(agent_module, "run_agent_messages", fake_messages)
    result = await agent_module.run_agent_and_wait(_request())

    assert isinstance(result, EngineRunOutcomeSuspended)
    assert result.reason == RUN_SUSPENDED_REASON_TOOL_AWAITING
    assert result.resume_hint is None
    assert len(result.awaiting_records) == 1
    assert result.awaiting_records[0].await_spec is await_spec
    assert result.awaiting_records[0].snapshot is snapshot


@pytest.mark.asyncio
async def test_run_agent_and_wait_logs_unknown_terminal_shape(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """terminal type 与 data 不匹配时必须记录 warning。"""

    async def fake_messages(
        request: AgentRunRequest,
    ) -> AsyncIterator[EngineEvent]:
        """产出形状不匹配的 terminal event。

        :param request: Agent run 请求。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        yield EngineEvent(
            occurred_at=_utc_now(),
            session_id=request.session_id,
            run_id=request.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=RunFailedData(
                error_code=EngineRunErrorCode.MISSING_TERMINAL,
                message="bad terminal shape",
                provider_request_id=None,
                recoverable=False,
            ),
            metadata=None,
        )

    caplog.set_level(logging.WARNING, logger="dayu.engine.agent")
    monkeypatch.setattr(agent_module, "run_agent_messages", fake_messages)

    result = await agent_module.run_agent_and_wait(_request())

    assert isinstance(result, EngineRunOutcomeFailed)
    assert any(
        "engine.agent.unknown_terminal_shape" in record.getMessage()
        for record in caplog.records
    )


def _terminal_count(events: Sequence[EngineEvent]) -> int:
    """统计 terminal 事件数。

    :param events: EngineEvent 序列。
    :returns: terminal 数量。
    :raises Exception: 不主动抛出异常。
    """

    return sum(1 for event in events if event.type in TERMINAL_ENGINE_EVENT_TYPES)
