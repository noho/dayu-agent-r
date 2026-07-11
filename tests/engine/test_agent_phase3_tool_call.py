"""Phase 3 tool calling 与 Phase 5 continuation 回归测试。"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import cast

import pytest
from _pytest.logging import LogCaptureFixture

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_executor import ToolExecutor
from dayu.contracts.tool_call import (
    BatchToolExecutionRequest,
    GeminiToolCallState,
    ToolCallRequest,
)
from dayu.contracts.tool_outcome import (
    BatchToolExecutionOutcome,
    BatchToolExecutionRecord,
    ToolAwaitingOutcome,
    ToolCompletedOutcome,
    ToolExecutionOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import (
    ToolResultFailure,
    ToolResultSuccess,
)
from dayu.engine.agent import _AsyncAgent, _project_tool_outcome_for_llm
from dayu.engine.contracts.agent_policy import AgentFallbackMode, AgentPolicy
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import (
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    IterationCompletedData,
    IterationStartedData,
    RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION,
    RUN_SUSPENDED_REASON_TOOL_AWAITING,
    RunFailedData,
    RunSuspendedData,
    ToolAwaitingData,
    ToolCallsBatchDoneData,
    ToolCallsBatchReadyData,
    ToolCallRequestedData,
    ToolResultAcceptedData,
    runner_role_sequence_digest,
)
from dayu.engine.contracts.finish_reason import FinishReason
from dayu.engine.contracts.messages import (
    AgentMessage,
    AgentMessageRole,
    AssistantMessage,
    ToolMessage,
    UserMessage,
)
from dayu.engine.contracts.runner_events import (
    RunnerContentCompletedData,
    RunnerContentDeltaData,
    RunnerDoneData,
    RunnerEvent,
    RunnerEventData,
    RunnerEventType,
    RunnerReasoningDeltaData,
    RunnerToolCallDeltaData,
    RunnerToolCallsCompletedData,
)
from dayu.engine.contracts.runner_identity import RunnerRequestIdentity
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
from dayu.contracts.tool_await import (
    ToolAwaitKind,
    ToolAwaitSnapshot,
    ToolAwaitSpec,
)
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from tests.host.fake_cancellation import ControllableCancellationToken

_TOOL_EXECUTION_TIMEOUT_SECONDS: float = 5.0
_FAST_TOOL_EXECUTION_TIMEOUT_SECONDS: float = 0.01
_SLOW_TOOL_EXECUTION_SECONDS: float = 5.0
_MINIMAL_MAX_ITERATIONS: int = 1
_NO_CONTINUATION_ATTEMPTS: int = 0
_TEST_FALLBACK_PROMPT: str = "test fallback prompt"
_TEST_CONTINUATION_PROMPT: str = "test continuation prompt"
_INVALID_CONTINUATION_ATTEMPTS: int = -1
_INVALID_FAILED_BATCH_THRESHOLDS: tuple[int, ...] = (0, -1)
_INVALID_TOOL_EXECUTION_TIMEOUTS: tuple[float, ...] = (
    0.0,
    -1.0,
    math.nan,
    math.inf,
)
_OVERSIZED_RESUME_TOKEN_LENGTH: int = 2049
_OVERSIZED_INLINE_CONTENT_LENGTH: int = 70000
_TOOL_EXECUTOR_EXCEPTION_ERROR: str = "tool_executor_exception"


def _utc_now() -> datetime:
    """返回测试用 UTC 当前时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


@dataclass(slots=True)
class _ScriptedRunner:
    """按调用次数产出 RunnerEvent 的 fake Runner。"""

    scripts: tuple[tuple[RunnerEvent, ...], ...]
    supports_tools: bool = True
    raise_on_call_indices: frozenset[int] = field(default_factory=frozenset)
    token_to_cancel: ControllableCancellationToken | None = None
    cancel_after_call_indices: frozenset[int] = field(default_factory=frozenset)
    call_count: int = 0
    close_count: int = 0
    token_to_cancel_on_close: ControllableCancellationToken | None = None
    tools_seen: list[tuple[ToolSchema, ...]] = field(default_factory=list)
    messages_seen: list[tuple[AgentMessage, ...]] = field(default_factory=list)
    request_identities_seen: list[RunnerRequestIdentity | None] = field(
        default_factory=list
    )

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
        :param options: Runner 调用参数。
        :param tools: 本轮工具 schema。
        :param request_identity: 本次逻辑 Runner 调用的请求身份。
        :returns: RunnerEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        del options
        self.messages_seen.append(tuple(messages))
        self.tools_seen.append(tuple(tools))
        self.request_identities_seen.append(request_identity)
        script_index = self.call_count
        self.call_count += 1
        if script_index in self.raise_on_call_indices:
            return self._raise_runtime_error()
        if script_index >= len(self.scripts):
            return self._iter_events(())
        if script_index in self.cancel_after_call_indices:
            return self._iter_events_then_cancel(self.scripts[script_index])
        return self._iter_events(self.scripts[script_index])

    def is_supports_tool_calling(self) -> bool:
        """返回是否支持工具调用。

        :returns: 支持返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.supports_tools

    async def close(self) -> None:
        """记录 close 调用。

        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.close_count += 1
        if self.token_to_cancel_on_close is not None:
            self.token_to_cancel_on_close.request_cancel()

    async def _iter_events(
        self, events: tuple[RunnerEvent, ...]
    ) -> AsyncIterator[RunnerEvent]:
        """产出脚本事件。

        :param events: RunnerEvent 元组。
        :returns: RunnerEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        for event in events:
            yield event

    async def _raise_runtime_error(self) -> AsyncIterator[RunnerEvent]:
        """产出时抛出测试用 Runner 异常。

        :returns: 不会正常产出 RunnerEvent。
        :raises RuntimeError: 始终抛出测试异常。
        """

        raise RuntimeError("runner exploded")
        yield

    async def _iter_events_then_cancel(
        self, events: tuple[RunnerEvent, ...]
    ) -> AsyncIterator[RunnerEvent]:
        """产出脚本事件后触发测试 token 取消。

        :param events: RunnerEvent 元组。
        :returns: RunnerEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        for event in events:
            yield event
        if self.token_to_cancel is not None:
            self.token_to_cancel.request_cancel()


@dataclass(slots=True)
class _StateClearingRunner:
    """完成 RunnerEvent 产出后清空 Agent 迭代状态的 fake Runner。

    :param events: 需要产出的 RunnerEvent 序列。
    :param agent: 需要破坏迭代状态的 Agent。
    :param call_count: Runner 调用次数。
    :param close_count: Runner close 调用次数。
    """

    events: tuple[RunnerEvent, ...]
    agent: _AsyncAgent | None = None
    call_count: int = 0
    close_count: int = 0

    def call(
        self,
        messages: Sequence[AgentMessage],
        options: RunnerCallOptions,
        tools: Sequence[ToolSchema],
        *,
        request_identity: RunnerRequestIdentity | None,
    ) -> AsyncIterator[RunnerEvent]:
        """返回会破坏迭代状态不变量的 RunnerEvent 流。

        :param messages: Agent 消息。
        :param options: Runner 调用参数。
        :param tools: 本轮工具 schema。
        :param request_identity: 本次逻辑 Runner 调用的请求身份。
        :returns: RunnerEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        del messages, options, tools, request_identity
        self.call_count += 1
        return self._iter_events()

    def is_supports_tool_calling(self) -> bool:
        """返回是否支持工具调用。

        :returns: 始终返回 ``True``。
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
        """产出脚本事件后清空 Agent 迭代状态。

        :returns: RunnerEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        for event in self.events:
            yield event
        if self.agent is not None:
            self.agent._last_iteration_state = None


@dataclass(slots=True)
class _RecordingToolExecutor:
    """记录批式请求并返回预设 outcome 的 fake ToolExecutor。"""

    outcomes: Mapping[str, ToolExecutionOutcome]
    records_override: tuple[BatchToolExecutionRecord, ...] | None = None
    token_to_cancel: ControllableCancellationToken | None = None
    raise_for_call_id: str | None = None
    raise_cancelled_for_call_id: str | None = None
    requests: list[BatchToolExecutionRequest] = field(default_factory=list)

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """执行 fake 批式工具调用。

        :param request: 批式工具执行请求。
        :returns: 配置 ``records_override`` 时返回该覆盖记录，否则返回与
            输入 ``calls`` 一一对应的批式 outcome。
        :raises RuntimeError: 配置 ``raise_for_call_id`` 且某 call 命中时抛出。
        :raises asyncio.CancelledError: 配置 ``raise_cancelled_for_call_id``
            且某 call 命中时抛出。
        """

        self.requests.append(request)
        call_ids = {call.tool_call_id for call in request.calls}
        if (
            self.raise_for_call_id is not None
            and self.raise_for_call_id in call_ids
        ):
            raise RuntimeError("tool exploded")
        if (
            self.raise_cancelled_for_call_id is not None
            and self.raise_cancelled_for_call_id in call_ids
        ):
            raise asyncio.CancelledError()
        if self.token_to_cancel is not None:
            self.token_to_cancel.request_cancel()
        if self.records_override is not None:
            return BatchToolExecutionOutcome(records=self.records_override)
        records = tuple(
            BatchToolExecutionRecord(
                tool_call_id=call.tool_call_id,
                outcome=self.outcomes[call.tool_call_id],
            )
            for call in request.calls
        )
        return BatchToolExecutionOutcome(records=records)


@dataclass(slots=True)
class _HangingToolExecutor:
    """持续挂起直到被取消的 fake ToolExecutor。"""

    requests: list[BatchToolExecutionRequest] = field(default_factory=list)
    token_to_cancel_on_cancel: ControllableCancellationToken | None = None
    cancelled: bool = False

    async def execute(
        self, request: BatchToolExecutionRequest
    ) -> BatchToolExecutionOutcome:
        """记录批式请求并模拟不返回 outcome 的工具握手。

        :param request: 批式工具执行请求。
        :returns: 理论上不会返回；若未被取消则返回成功 outcome。
        :raises asyncio.CancelledError: task 被 Engine 取消时透传。
        """

        self.requests.append(request)
        try:
            await asyncio.sleep(_SLOW_TOOL_EXECUTION_SECONDS)
        except asyncio.CancelledError:
            self.cancelled = True
            if self.token_to_cancel_on_cancel is not None:
                self.token_to_cancel_on_cancel.request_cancel()
            raise
        records = tuple(
            BatchToolExecutionRecord(
                tool_call_id=call.tool_call_id,
                outcome=_success(0),
            )
            for call in request.calls
        )
        return BatchToolExecutionOutcome(records=records)


def _event(event_type: RunnerEventType, data: RunnerEventData) -> RunnerEvent:
    """构造 RunnerEvent。

    :param event_type: RunnerEventType。
    :param data: RunnerEvent data。
    :returns: RunnerEvent。
    :raises Exception: 不主动抛出异常。
    """

    return RunnerEvent(type=event_type, data=data, occurred_at=_utc_now())


def _tool_call(
    tool_call_id: str,
    *,
    index: int = 0,
    arguments: Mapping[str, JsonValue] | None = None,
) -> ToolCallRequest:
    """构造工具调用请求。

    :param tool_call_id: 工具调用 id。
    :param index: 迭代内序号。
    :param arguments: 工具参数。
    :returns: ToolCallRequest。
    :raises Exception: 不主动抛出异常。
    """

    return ToolCallRequest(
        tool_call_id=tool_call_id,
        name="add_numbers",
        arguments=arguments or {"a": 2, "b": 3},
        index_in_iteration=index,
        provider_state=GeminiToolCallState(thought_signature="sig"),
    )


def _tool_script(
    *tool_calls: ToolCallRequest,
    provider_request_id: str | None = None,
) -> tuple[RunnerEvent, ...]:
    """构造请求工具的 Runner 脚本。

    :param tool_calls: 工具调用请求。
    :param provider_request_id: RunnerDone 携带的 provider response request id。
    :returns: RunnerEvent 元组。
    :raises Exception: 不主动抛出异常。
    """

    return (
        _event(
            RunnerEventType.RUNNER_CONTENT_COMPLETED,
            RunnerContentCompletedData(
                content=None,
                reasoning_content="reason",
            ),
        ),
        _event(
            RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
            RunnerToolCallsCompletedData(tool_calls=tuple(tool_calls)),
        ),
        _event(
            RunnerEventType.RUNNER_DONE,
            RunnerDoneData(
                finish_reason=FinishReason.TOOL_CALLS,
                provider_request_id=provider_request_id,
            ),
        ),
    )


def _final_script(content: str, *, finish_reason: FinishReason = FinishReason.STOP) -> tuple[RunnerEvent, ...]:
    """构造最终回答 Runner 脚本。

    :param content: 最终正文。
    :param finish_reason: 完成原因。
    :returns: RunnerEvent 元组。
    :raises Exception: 不主动抛出异常。
    """

    return (
        _event(
            RunnerEventType.RUNNER_CONTENT_COMPLETED,
            RunnerContentCompletedData(
                content=content,
                reasoning_content=None,
            ),
        ),
        _event(
            RunnerEventType.RUNNER_DONE,
            RunnerDoneData(finish_reason=finish_reason, provider_request_id=None),
        ),
    )


def _schema() -> ToolSchema:
    """构造 add_numbers schema。

    :returns: ToolSchema。
    :raises Exception: 不主动抛出异常。
    """

    return ToolSchema(
        type="function",
        function=ToolFunctionSchema(
            name="add_numbers",
            description="add two numbers",
            parameters=ToolParametersSchema(
                type="object",
                properties={
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
                required=("a", "b"),
                additional_properties=False,
            ),
        ),
    )


def _success(value: JsonValue) -> ToolCompletedOutcome:
    """构造成功 outcome。

    :param value: 成功值。
    :returns: ToolCompletedOutcome。
    :raises Exception: 不主动抛出异常。
    """

    return ToolCompletedOutcome(
        result=ToolResultSuccess(
            ok=True,
            value=value,
            meta=None,
        )
    )


def _failed(hint: str | None = None) -> ToolFailedOutcome:
    """构造失败 outcome。

    :param hint: 可选提示。
    :returns: ToolFailedOutcome。
    :raises Exception: 不主动抛出异常。
    """

    return ToolFailedOutcome(
        result=ToolResultFailure(
            ok=False,
            error="tool_failed",
            message="failed",
            hint=hint,
            meta=None,
        )
    )


def _awaiting(
    *,
    resume_token: str = "resume",
    snapshot: ToolAwaitSnapshot | None = None,
) -> ToolAwaitingOutcome:
    """构造等待 outcome。

    :param resume_token: 恢复 token。
    :param snapshot: 可选等待快照。
    :returns: ToolAwaitingOutcome。
    :raises Exception: 不主动抛出异常。
    """

    return ToolAwaitingOutcome(
        await_spec=ToolAwaitSpec(
            await_kind=ToolAwaitKind.EXTERNAL_JOB,
            deadline=None,
            resume_token=resume_token,
        ),
        snapshot=snapshot,
    )


def _request(
    *,
    token: ControllableCancellationToken | None = None,
    executor: ToolExecutor | None = None,
    max_iterations: int = 2,
    fallback_mode: AgentFallbackMode = AgentFallbackMode.FORCE_ANSWER,
    disable_tools: bool = False,
    allow_tool_calls: bool = True,
    max_failed_batches: int = 2,
    continuation_max_attempts: int = 3,
    continuation_prompt: str = "请继续。",
    tool_execution_timeout_seconds: float = _TOOL_EXECUTION_TIMEOUT_SECONDS,
) -> AgentRunRequest:
    """构造 AgentRunRequest。

    :param token: cancellation token。
    :param executor: fake ToolExecutor。
    :param max_iterations: 最大普通工具轮次。
    :param fallback_mode: fallback 模式。
    :param disable_tools: 是否禁用工具。
    :param allow_tool_calls: policy 是否允许工具。
    :param max_failed_batches: 连续失败工具批次阈值。
    :param continuation_max_attempts: continuation 最大尝试次数。
    :param continuation_prompt: continuation 追加用户消息。
    :param tool_execution_timeout_seconds: 工具握手超时秒数。
    :returns: AgentRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    return AgentRunRequest(
        run_id="run_phase3",
        session_id="session_phase3",
        messages=(UserMessage(role=AgentMessageRole.USER, content="calculate"),),
        disable_tools=disable_tools,
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
            continuation_max_attempts=continuation_max_attempts,
            allow_tool_calls=allow_tool_calls,
            tool_execution_timeout_seconds=tool_execution_timeout_seconds,
            fallback_mode=fallback_mode,
            fallback_prompt="请直接回答。",
            continuation_prompt=continuation_prompt,
            max_consecutive_failed_tool_batches=max_failed_batches,
        ),
        tool_schemas=(_schema(),),
        tool_executor=executor or _RecordingToolExecutor(
            outcomes={"tc_1": _success(5)}
        ),
        cancellation_token=token or ControllableCancellationToken(),
        attempt_id="attempt_phase3",
        execution_id="execution_phase3",
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


@pytest.mark.asyncio
async def test_iteration_started_carries_role_digest_from_actual_messages() -> None:
    """iteration_started 的 role digest 来自实际传给 Runner 的 messages。"""

    runner = _ScriptedRunner(
        scripts=(
            (
                _event(
                    RunnerEventType.RUNNER_CONTENT_COMPLETED,
                    RunnerContentCompletedData(
                        content="done",
                        reasoning_content=None,
                    ),
                ),
                _event(
                    RunnerEventType.RUNNER_DONE,
                    RunnerDoneData(
                        finish_reason=FinishReason.STOP,
                        provider_request_id="req-role-digest",
                    ),
                ),
            ),
        )
    )

    events = await _collect(_AsyncAgent(request=_request(), runner=runner))
    started = events[0]

    assert started.type is EngineEventType.ITERATION_STARTED
    assert isinstance(started.data, IterationStartedData)
    assert started.data.message_count == len(runner.messages_seen[0])
    assert started.data.role_sequence_digest == runner_role_sequence_digest(
        tuple(message.role.value for message in runner.messages_seen[0])
    )
    assert (
        started.data.runner_input_serializer_schema_version
        == RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
    )


def _terminal(events: Sequence[EngineEvent]) -> EngineEvent:
    """返回 terminal 事件。

    :param events: EngineEvent 序列。
    :returns: terminal 事件。
    :raises AssertionError: 未找到 terminal 时抛出。
    """

    terminals = [
        event
        for event in events
        if event.type
        in {
            EngineEventType.FINAL_ANSWER,
            EngineEventType.RUN_FAILED,
            EngineEventType.RUN_CANCELLED,
            EngineEventType.RUN_SUSPENDED,
        }
    ]
    assert len(terminals) == 1
    return terminals[0]


def _failed_data(events: Sequence[EngineEvent]) -> RunFailedData:
    """返回 terminal run_failed data。

    :param events: EngineEvent 序列。
    :returns: RunFailedData。
    :raises AssertionError: terminal 不是 run_failed 时抛出。
    """

    data = _terminal(events).data
    assert isinstance(data, RunFailedData)
    return data


def _suspended_data(events: Sequence[EngineEvent]) -> RunSuspendedData:
    """返回 terminal run_suspended data。

    :param events: EngineEvent 序列。
    :returns: RunSuspendedData。
    :raises AssertionError: terminal 不是 run_suspended 时抛出。
    """

    data = _terminal(events).data
    assert isinstance(data, RunSuspendedData)
    return data


def _final_data(events: Sequence[EngineEvent]) -> FinalAnswerData:
    """返回 terminal final_answer data。

    :param events: EngineEvent 序列。
    :returns: FinalAnswerData。
    :raises AssertionError: terminal 不是 final_answer 时抛出。
    """

    data = _terminal(events).data
    assert isinstance(data, FinalAnswerData)
    return data


def test_agent_policy_accepts_explicit_prompt_fields() -> None:
    """AgentPolicy 必须保留调用方显式传入的 prompt 字段。"""

    policy = AgentPolicy(
        max_iterations=_MINIMAL_MAX_ITERATIONS,
        continuation_max_attempts=_NO_CONTINUATION_ATTEMPTS,
        allow_tool_calls=True,
        tool_execution_timeout_seconds=_TOOL_EXECUTION_TIMEOUT_SECONDS,
        fallback_prompt=_TEST_FALLBACK_PROMPT,
        continuation_prompt=_TEST_CONTINUATION_PROMPT,
    )

    assert policy.fallback_mode is AgentFallbackMode.FORCE_ANSWER
    assert policy.max_consecutive_failed_tool_batches == 2
    assert policy.fallback_prompt == _TEST_FALLBACK_PROMPT
    assert policy.continuation_prompt == _TEST_CONTINUATION_PROMPT


def test_agent_policy_prompt_fields_are_required() -> None:
    """缺少任一 prompt 字段时，Python 构造器必须直接报 TypeError。"""

    full_kwargs = {
        "max_iterations": _MINIMAL_MAX_ITERATIONS,
        "continuation_max_attempts": _NO_CONTINUATION_ATTEMPTS,
        "allow_tool_calls": True,
        "tool_execution_timeout_seconds": _TOOL_EXECUTION_TIMEOUT_SECONDS,
        "fallback_prompt": _TEST_FALLBACK_PROMPT,
        "continuation_prompt": _TEST_CONTINUATION_PROMPT,
    }
    without_fallback_prompt = {
        key: value for key, value in full_kwargs.items() if key != "fallback_prompt"
    }
    without_continuation_prompt = {
        key: value
        for key, value in full_kwargs.items()
        if key != "continuation_prompt"
    }

    with pytest.raises(TypeError, match="fallback_prompt"):
        AgentPolicy(**without_fallback_prompt)
    with pytest.raises(TypeError, match="continuation_prompt"):
        AgentPolicy(**without_continuation_prompt)


def test_agent_policy_rejects_invalid_values() -> None:
    """AgentPolicy 非法策略值必须在 contract 构造期 fail fast。

    :returns: ``None``。
    :raises AssertionError: 非法策略值未被构造期校验拒绝时抛出。
    """

    for threshold in _INVALID_FAILED_BATCH_THRESHOLDS:
        with pytest.raises(ValueError):
            AgentPolicy(
                max_iterations=_MINIMAL_MAX_ITERATIONS,
                continuation_max_attempts=_NO_CONTINUATION_ATTEMPTS,
                allow_tool_calls=True,
                tool_execution_timeout_seconds=_TOOL_EXECUTION_TIMEOUT_SECONDS,
                fallback_prompt=_TEST_FALLBACK_PROMPT,
                continuation_prompt=_TEST_CONTINUATION_PROMPT,
                max_consecutive_failed_tool_batches=threshold,
            )
    with pytest.raises(ValueError):
        AgentPolicy(
            max_iterations=_MINIMAL_MAX_ITERATIONS,
            continuation_max_attempts=_INVALID_CONTINUATION_ATTEMPTS,
            allow_tool_calls=True,
            tool_execution_timeout_seconds=_TOOL_EXECUTION_TIMEOUT_SECONDS,
            fallback_prompt=_TEST_FALLBACK_PROMPT,
            continuation_prompt=_TEST_CONTINUATION_PROMPT,
        )
    # continuation_prompt 为空 / 纯空白必须在构造期被拒。
    for invalid_continuation_prompt in ("", "   ", "\n\t"):
        with pytest.raises(ValueError):
            AgentPolicy(
                max_iterations=_MINIMAL_MAX_ITERATIONS,
                continuation_max_attempts=_NO_CONTINUATION_ATTEMPTS,
                allow_tool_calls=True,
                tool_execution_timeout_seconds=_TOOL_EXECUTION_TIMEOUT_SECONDS,
                fallback_prompt=_TEST_FALLBACK_PROMPT,
                continuation_prompt=invalid_continuation_prompt,
            )
    for timeout_seconds in _INVALID_TOOL_EXECUTION_TIMEOUTS:
        with pytest.raises(ValueError):
            AgentPolicy(
                max_iterations=_MINIMAL_MAX_ITERATIONS,
                continuation_max_attempts=_NO_CONTINUATION_ATTEMPTS,
                allow_tool_calls=True,
                tool_execution_timeout_seconds=timeout_seconds,
                fallback_prompt=_TEST_FALLBACK_PROMPT,
                continuation_prompt=_TEST_CONTINUATION_PROMPT,
            )
    # max_iterations < 1 必须在构造期被拒。
    for invalid_max_iterations in (0, -1):
        with pytest.raises(ValueError):
            AgentPolicy(
                max_iterations=invalid_max_iterations,
                continuation_max_attempts=_NO_CONTINUATION_ATTEMPTS,
                allow_tool_calls=True,
                tool_execution_timeout_seconds=_TOOL_EXECUTION_TIMEOUT_SECONDS,
                fallback_prompt=_TEST_FALLBACK_PROMPT,
                continuation_prompt=_TEST_CONTINUATION_PROMPT,
            )
    # fallback_prompt 为空 / 纯空白必须在构造期被拒。
    for invalid_fallback_prompt in ("", "   ", "\n\t"):
        with pytest.raises(ValueError):
            AgentPolicy(
                max_iterations=_MINIMAL_MAX_ITERATIONS,
                continuation_max_attempts=_NO_CONTINUATION_ATTEMPTS,
                allow_tool_calls=True,
                tool_execution_timeout_seconds=_TOOL_EXECUTION_TIMEOUT_SECONDS,
                fallback_prompt=invalid_fallback_prompt,
                continuation_prompt=_TEST_CONTINUATION_PROMPT,
            )
    with pytest.raises(TypeError, match="fallback_mode"):
        AgentPolicy(
            max_iterations=_MINIMAL_MAX_ITERATIONS,
            continuation_max_attempts=_NO_CONTINUATION_ATTEMPTS,
            allow_tool_calls=True,
            tool_execution_timeout_seconds=_TOOL_EXECUTION_TIMEOUT_SECONDS,
            fallback_prompt=_TEST_FALLBACK_PROMPT,
            continuation_prompt=_TEST_CONTINUATION_PROMPT,
            fallback_mode=cast(AgentFallbackMode, "unsupported"),
        )


def test_tool_await_spec_rejects_invalid_resume_token() -> None:
    """ToolAwaitSpec 的 resume token 必须有基础边界校验。"""

    for resume_token in ("", " "):
        with pytest.raises(ValueError):
            ToolAwaitSpec(
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                deadline=None,
                resume_token=resume_token,
            )
    with pytest.raises(ValueError):
        ToolAwaitSpec(
            await_kind=ToolAwaitKind.EXTERNAL_JOB,
            deadline=None,
            resume_token="x" * _OVERSIZED_RESUME_TOKEN_LENGTH,
        )


def test_llm_projection_shapes() -> None:
    """工具结果注入 LLM 前必须保持普通 JSON projection。"""

    success_object = _project_tool_outcome_for_llm(_success({"sum": 5}))
    success_scalar = _project_tool_outcome_for_llm(_success("ok"))
    failure_without_hint = _project_tool_outcome_for_llm(_failed())
    failure_with_hint = _project_tool_outcome_for_llm(_failed(hint="retry"))
    truncated = _project_tool_outcome_for_llm(
        ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={
                    "truncation": {
                        "fetch_more_args": {
                            "cursor": "cursor-value",
                            "limit": 30,
                            "scope_token": "secret_token",
                        },
                        "has_more": True,
                        "next_action": "fetch_more",
                        "ttl_seconds": 60,
                    }
                },
                meta=None,
            )
        )
    )

    assert json.loads(success_object) == {"sum": 5}
    assert json.loads(success_scalar) == {"content": "ok"}
    assert json.loads(failure_without_hint) == {
        "error": "tool_failed",
        "message": "failed",
    }
    assert json.loads(failure_with_hint)["hint"] == "retry"
    truncated_payload = json.loads(truncated)
    assert truncated_payload["truncation"] == {
        "fetch_more_args": {
            "cursor": "cursor-value",
            "limit": 30,
            "scope_token": "secret_token",
        },
        "has_more": True,
        "next_action": "fetch_more",
        "ttl_seconds": 60,
    }
    assert "secret_token" in truncated
    assert "secret_hash" not in truncated
    assert "has_more" in truncated
    assert "ok" not in success_object
    assert failure_without_hint


def test_llm_truncation_projection_without_more_hides_fetch_hint() -> None:
    """普通 value 中 has_more=False 时 Engine 只做 JSON 透传。

    :returns: 无返回值。
    :raises AssertionError: projection 结构不符合预期时抛出。
    """

    projected = _project_tool_outcome_for_llm(
        ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={"truncation": {"has_more": False}},
                meta=None,
            )
        )
    )

    payload = json.loads(projected)
    assert payload["truncation"] == {"has_more": False}
    assert "next_action" not in payload["truncation"]
    assert "fetch_more_args" not in payload["truncation"]
    assert "ttl_seconds" not in payload["truncation"]
    assert "secret_token" not in projected
    assert "secret_hash" not in projected


@pytest.mark.asyncio
async def test_completed_tool_call_injects_messages_and_reaches_final() -> None:
    """completed outcome 会进入下一轮 Runner 并最终收口 final_answer。"""

    executor = _RecordingToolExecutor(outcomes={"tc_1": _success({"sum": 5})})
    runner = _ScriptedRunner(scripts=(_tool_script(_tool_call("tc_1")), _final_script("5")))

    events = await _collect(_AsyncAgent(request=_request(executor=executor), runner=runner))

    terminal = _terminal(events)
    assert terminal.type is EngineEventType.FINAL_ANSWER
    assert isinstance(terminal.data, FinalAnswerData)
    assert terminal.data.content == "5"
    assert terminal.data.degraded is False
    assert len(executor.requests) == 1
    context = executor.requests[0].context
    assert context.session_id == "session_phase3"
    assert context.run_id == "run_phase3"
    assert context.iteration_id == "run_phase3_iteration_1"
    assert context.timeout_seconds == _TOOL_EXECUTION_TIMEOUT_SECONDS
    assert context.correlation_id == (
        "run_phase3:run_phase3_iteration_1:tool_batch"
    )
    assert [call.tool_call_id for call in executor.requests[0].calls] == ["tc_1"]

    requested = [event for event in events if event.type is EngineEventType.TOOL_CALL_REQUESTED]
    accepted = [event for event in events if event.type is EngineEventType.TOOL_RESULT_ACCEPTED]
    ready = [event for event in events if event.type is EngineEventType.TOOL_CALLS_BATCH_READY]
    done = [event for event in events if event.type is EngineEventType.TOOL_CALLS_BATCH_DONE]
    assert len(ready) == 1
    assert len(done) == 1
    assert len(requested) == 1
    assert len(accepted) == 1
    assert isinstance(ready[0].data, ToolCallsBatchReadyData)
    assert isinstance(done[0].data, ToolCallsBatchDoneData)
    assert isinstance(requested[0].data, ToolCallRequestedData)
    assert isinstance(accepted[0].data, ToolResultAcceptedData)
    assert ready[0].data.tool_calls[0].tool_call_id == "tc_1"
    assert done[0].data.tool_call_ids == ("tc_1",)
    assert done[0].data.completed_count == 1
    assert done[0].data.failed_count == 0
    assert done[0].data.cancelled_count == 0
    assert events.index(done[0]) > events.index(accepted[0])
    assert requested[0].data.provider_state == GeminiToolCallState(thought_signature="sig")
    assert accepted[0].data.record.call.index_in_iteration == 0
    assert accepted[0].data.record.call.tool_call_id == "tc_1"

    second_messages = runner.messages_seen[1]
    assert isinstance(second_messages[-2], AssistantMessage)
    assert isinstance(second_messages[-1], ToolMessage)
    assert second_messages[-2].tool_calls[0].id == "tc_1"
    assert second_messages[-2].reasoning_content == "reason"
    assert json.loads(second_messages[-1].content) == {"sum": 5}
    assert runner.tools_seen[0] == (_schema(),)
    assert [
        identity.runner_call_index
        for identity in runner.request_identities_seen
        if identity is not None
    ] == [1, 2]
    assert all(
        identity is not None
        and identity.attempt_id == "attempt_phase3"
        and identity.execution_id == "execution_phase3"
        for identity in runner.request_identities_seen
    )
    iteration_completed = [
        event
        for event in events
        if event.type is EngineEventType.ITERATION_COMPLETED
    ]
    assert len(iteration_completed) == 2
    for event, identity in zip(
        iteration_completed, runner.request_identities_seen, strict=True
    ):
        assert isinstance(event.data, IterationCompletedData)
        assert identity is not None
        assert event.data.client_correlation_id == identity.client_correlation_id
    assert runner.close_count == 1


@pytest.mark.asyncio
async def test_oversized_tool_message_is_passed_to_next_runner_call() -> None:
    """工具结果注入 messages 后由 Runner/provider 边界处理容量。"""

    executor = _RecordingToolExecutor(
        outcomes={
            "tc_1": _success(
                {"content": "x" * _OVERSIZED_INLINE_CONTENT_LENGTH}
            )
        }
    )
    runner = _ScriptedRunner(
        scripts=(_tool_script(_tool_call("tc_1")), _final_script("unreachable"))
    )

    events = await _collect(_AsyncAgent(request=_request(executor=executor), runner=runner))

    terminal = _terminal(events)
    assert terminal.type is EngineEventType.FINAL_ANSWER
    second_messages = runner.messages_seen[1]
    assert isinstance(second_messages[-1], ToolMessage)
    assert "x" * _OVERSIZED_INLINE_CONTENT_LENGTH in second_messages[-1].content
    assert runner.call_count == 2
    assert runner.close_count == 1
    assert len(executor.requests) == 1


@pytest.mark.asyncio
async def test_oversized_tool_message_is_passed_to_force_answer_runner_call() -> None:
    """force-answer fallback 不再执行 Engine 私有 inline byte 阈值。"""

    executor = _RecordingToolExecutor(
        outcomes={
            "tc_1": _success(
                {"content": "x" * _OVERSIZED_INLINE_CONTENT_LENGTH}
            )
        }
    )
    runner = _ScriptedRunner(
        scripts=(_tool_script(_tool_call("tc_1")), _final_script("unreachable"))
    )

    events = await _collect(
        _AsyncAgent(
            request=_request(executor=executor, max_iterations=1),
            runner=runner,
        )
    )

    terminal = _terminal(events)
    assert terminal.type is EngineEventType.FINAL_ANSWER
    second_messages = runner.messages_seen[1]
    assert isinstance(second_messages[-2], ToolMessage)
    assert "x" * _OVERSIZED_INLINE_CONTENT_LENGTH in second_messages[-2].content
    assert isinstance(second_messages[-1], UserMessage)
    assert runner.call_count == 2
    assert [
        identity.runner_call_index
        for identity in runner.request_identities_seen
        if identity is not None
    ] == [1, 2]
    assert runner.request_identities_seen[1] is not None
    assert runner.request_identities_seen[1].iteration_id == "run_phase3_iteration_2"
    assert runner.close_count == 1
    assert len(executor.requests) == 1


@pytest.mark.asyncio
async def test_tool_call_iteration_preserves_streamed_content_delta() -> None:
    """tool-call 轮次先产出 content_delta 时，assistant content 必须保留。"""

    executor = _RecordingToolExecutor(outcomes={"tc_1": _success({"sum": 5})})
    runner = _ScriptedRunner(
        scripts=(
            (
                _event(
                    RunnerEventType.RUNNER_CONTENT_DELTA,
                    RunnerContentDeltaData(delta="先说明"),
                ),
                _event(
                    RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
                    RunnerToolCallsCompletedData(
                        tool_calls=(_tool_call("tc_1"),)
                    ),
                ),
                _event(
                    RunnerEventType.RUNNER_DONE,
                    RunnerDoneData(finish_reason=FinishReason.TOOL_CALLS, provider_request_id=None),
                ),
            ),
            _final_script("5"),
        )
    )

    await _collect(_AsyncAgent(request=_request(executor=executor), runner=runner))

    second_messages = runner.messages_seen[1]
    assert isinstance(second_messages[-2], AssistantMessage)
    assert second_messages[-2].content == "先说明"


@pytest.mark.asyncio
async def test_tool_call_iteration_empty_tool_content_falls_back_to_completed_content() -> None:
    """tool_calls content 为空字符串时保留已完成正文。"""

    executor = _RecordingToolExecutor(outcomes={"tc_1": _success({"sum": 5})})
    runner = _ScriptedRunner(
        scripts=(
            (
                _event(
                    RunnerEventType.RUNNER_CONTENT_COMPLETED,
                    RunnerContentCompletedData(
                        content="先说明",
                        reasoning_content=None,
                    ),
                ),
                _event(
                    RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
                    RunnerToolCallsCompletedData(
                        tool_calls=(_tool_call("tc_1"),),
                        content="",
                    ),
                ),
                _event(
                    RunnerEventType.RUNNER_DONE,
                    RunnerDoneData(
                        finish_reason=FinishReason.TOOL_CALLS,
                        provider_request_id=None,
                    ),
                ),
            ),
            _final_script("5"),
        )
    )

    await _collect(_AsyncAgent(request=_request(executor=executor), runner=runner))

    second_messages = runner.messages_seen[1]
    assert isinstance(second_messages[-2], AssistantMessage)
    assert second_messages[-2].content == "先说明"


@pytest.mark.asyncio
async def test_non_stream_tool_calls_preserve_reasoning_content() -> None:
    """非流式 tool_calls 的 reasoning_content 必须进入下一轮 assistant。

    :returns: ``None``。
    :raises AssertionError: reasoning_content 未进入下一轮 assistant 时抛出。
    """

    first_script = (
        _event(
            RunnerEventType.RUNNER_CONTENT_COMPLETED,
            RunnerContentCompletedData(
                content=None,
                reasoning_content="非流式推理",
            ),
        ),
        _event(
            RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
            RunnerToolCallsCompletedData(tool_calls=(_tool_call("tc_1"),)),
        ),
        _event(
            RunnerEventType.RUNNER_DONE,
            RunnerDoneData(
                finish_reason=FinishReason.TOOL_CALLS,
                provider_request_id=None,
            ),
        ),
    )
    executor = _RecordingToolExecutor(outcomes={"tc_1": _success({"sum": 5})})
    runner = _ScriptedRunner(scripts=(first_script, _final_script("5")))

    await _collect(_AsyncAgent(request=_request(executor=executor), runner=runner))

    second_messages = runner.messages_seen[1]
    assert isinstance(second_messages[-2], AssistantMessage)
    assert second_messages[-2].reasoning_content == "非流式推理"


@pytest.mark.asyncio
async def test_failed_tool_result_enters_context_not_terminal() -> None:
    """failed outcome 是普通工具结果，不伪装成取消或 final。"""

    executor = _RecordingToolExecutor(outcomes={"tc_1": _failed()})
    runner = _ScriptedRunner(
        scripts=(_tool_script(_tool_call("tc_1")), _final_script("explained"))
    )

    events = await _collect(_AsyncAgent(request=_request(executor=executor), runner=runner))

    assert len(executor.requests) == 1
    assert _terminal(events).type is EngineEventType.FINAL_ANSWER
    second_messages = runner.messages_seen[1]
    assert isinstance(second_messages[-1], ToolMessage)
    assert json.loads(second_messages[-1].content) == {
        "error": "tool_failed",
        "message": "failed",
    }


@pytest.mark.asyncio
async def test_multiple_tool_calls_invoke_executor_exactly_once() -> None:
    """多个 tool call 在一轮内只调用 executor 一次，每个 call 都有 accepted 记录。"""

    executor = _RecordingToolExecutor(
        outcomes={"tc_1": _success(1), "tc_2": _success(2)}
    )
    runner = _ScriptedRunner(
        scripts=(
            _tool_script(_tool_call("tc_2", index=1), _tool_call("tc_1", index=0)),
            _final_script("done"),
        )
    )

    events = await _collect(_AsyncAgent(request=_request(executor=executor), runner=runner))

    assert len(executor.requests) == 1
    # 输入按 LLM 输出顺序，不强制排序；只要求双射成立。
    request_ids = sorted(call.tool_call_id for call in executor.requests[0].calls)
    assert request_ids == ["tc_1", "tc_2"]

    accepted = [
        event for event in events if event.type is EngineEventType.TOOL_RESULT_ACCEPTED
    ]
    assert len(accepted) == 2
    accepted_ids: list[str] = []
    for event in accepted:
        assert isinstance(event.data, ToolResultAcceptedData)
        accepted_ids.append(event.data.record.call.tool_call_id)
    assert sorted(accepted_ids) == ["tc_1", "tc_2"]

    done = [
        event for event in events if event.type is EngineEventType.TOOL_CALLS_BATCH_DONE
    ]
    assert len(done) == 1
    assert isinstance(done[0].data, ToolCallsBatchDoneData)
    assert done[0].data.completed_count == 2
    assert done[0].data.failed_count == 0
    assert done[0].data.cancelled_count == 0


@pytest.mark.asyncio
async def test_mixed_outcomes_in_single_batch_count_correctly() -> None:
    """单批 completed+failed+cancelled 同时出现时计数正确。"""

    from dayu.contracts.tool_outcome import (
        TOOL_CANCELLED_REASON_APPROVAL_DENIED,
        ToolCancelledOutcome,
    )

    outcomes: dict[str, ToolExecutionOutcome] = {
        "tc_1": _success(1),
        "tc_2": _failed(),
        "tc_3": ToolCancelledOutcome(
            reason=TOOL_CANCELLED_REASON_APPROVAL_DENIED,
            message="denied",
            hint=None,
            meta=None,
        ),
    }
    executor = _RecordingToolExecutor(outcomes=outcomes)
    runner = _ScriptedRunner(
        scripts=(
            _tool_script(
                _tool_call("tc_1", index=0),
                _tool_call("tc_2", index=1),
                _tool_call("tc_3", index=2),
            ),
            _final_script("done"),
        )
    )

    events = await _collect(_AsyncAgent(request=_request(executor=executor), runner=runner))

    done = [
        event for event in events if event.type is EngineEventType.TOOL_CALLS_BATCH_DONE
    ]
    assert len(done) == 1
    assert isinstance(done[0].data, ToolCallsBatchDoneData)
    assert done[0].data.completed_count == 1
    assert done[0].data.failed_count == 1
    assert done[0].data.cancelled_count == 1
    assert sorted(done[0].data.tool_call_ids) == ["tc_1", "tc_2", "tc_3"]


@pytest.mark.asyncio
async def test_success_batch_does_not_trigger_failed_batch_fallback() -> None:
    """成功工具批次不能触发连续失败工具批次 fallback。"""

    executor = _RecordingToolExecutor(outcomes={"tc_1": _success(1)})
    runner = _ScriptedRunner(
        scripts=(_tool_script(_tool_call("tc_1")), _final_script("done"))
    )

    events = await _collect(
        _AsyncAgent(
            request=_request(
                executor=executor,
                max_iterations=2,
                max_failed_batches=1,
            ),
            runner=runner,
        )
    )

    assert _final_data(events).degraded is False
    assert runner.call_count == 2


@pytest.mark.asyncio
async def test_tool_disabled_or_runner_unsupported_fail_closed() -> None:
    """禁用工具或 Runner 不支持工具时，收到 tool call 必须 fail closed。"""

    for request, runner, expected_provider_request_id in (
        (
            _request(disable_tools=True),
            _ScriptedRunner(
                scripts=(
                    _tool_script(
                        _tool_call("tc_1"),
                        provider_request_id="req_tools_disabled",
                    ),
                )
            ),
            "req_tools_disabled",
        ),
        (
            _request(allow_tool_calls=False),
            _ScriptedRunner(scripts=(_tool_script(_tool_call("tc_1")),)),
            None,
        ),
        (
            _request(),
            _ScriptedRunner(
                scripts=(_tool_script(_tool_call("tc_1")),),
                supports_tools=False,
            ),
            None,
        ),
    ):
        events = await _collect(_AsyncAgent(request=request, runner=runner))
        terminal = _terminal(events)
        assert terminal.type is EngineEventType.RUN_FAILED
        assert isinstance(terminal.data, RunFailedData)
        assert terminal.data.error_code == "tool_call_not_enabled"
        assert terminal.data.provider_request_id == expected_provider_request_id


@pytest.mark.asyncio
async def test_tool_calls_finish_reason_mismatch_keeps_provider_request_id() -> None:
    """工具完成数据与 finish_reason 不一致时保留 provider request id。"""

    runner = _ScriptedRunner(
        scripts=(
            (
                _event(
                    RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
                    RunnerToolCallsCompletedData(
                        tool_calls=(_tool_call("tc_1"),)
                    ),
                ),
                _event(
                    RunnerEventType.RUNNER_DONE,
                    RunnerDoneData(
                        finish_reason=FinishReason.STOP,
                        provider_request_id="req_mismatch",
                    ),
                ),
            ),
        )
    )

    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    iteration_completed = events[-2]
    terminal = _terminal(events)
    assert iteration_completed.type is EngineEventType.ITERATION_COMPLETED
    assert isinstance(iteration_completed.data, IterationCompletedData)
    assert isinstance(terminal.data, RunFailedData)
    assert terminal.data.error_code == "runner_tool_calls_finish_reason_mismatch"
    assert iteration_completed.data.provider_request_id == "req_mismatch"
    assert terminal.data.provider_request_id == "req_mismatch"
    assert runner.request_identities_seen[0] is not None
    assert (
        iteration_completed.data.client_correlation_id
        == runner.request_identities_seen[0].client_correlation_id
    )
    assert (
        terminal.data.client_correlation_id
        == runner.request_identities_seen[0].client_correlation_id
    )


@pytest.mark.asyncio
async def test_tool_call_done_without_completed_data_is_protocol_error() -> None:
    """Runner 声明 TOOL_CALLS done 但缺工具完成数据时必须 fail closed。"""

    runner = _ScriptedRunner(
        scripts=(
            (
                _event(
                    RunnerEventType.RUNNER_TOOL_CALL_DELTA,
                    RunnerToolCallDeltaData(
                        tool_call_index=0,
                        tool_call_id="tc_1",
                        name_delta="add_numbers",
                        arguments_delta="{",
                    ),
                ),
                _event(
                    RunnerEventType.RUNNER_DONE,
                    RunnerDoneData(
                        finish_reason=FinishReason.TOOL_CALLS,
                        provider_request_id="req_missing_tool_calls",
                    ),
                ),
            ),
        )
    )

    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    failed = _failed_data(events)
    assert failed.error_code == "runner_tool_calls_missing"
    assert failed.provider_request_id == "req_missing_tool_calls"


@pytest.mark.asyncio
async def test_runner_exception_after_tool_batch_is_run_failed(
    caplog: LogCaptureFixture,
) -> None:
    """第二轮 Runner 异常必须保留已注入工具上下文并收口 run_failed。"""

    executor = _RecordingToolExecutor(outcomes={"tc_1": _success({"sum": 5})})
    runner = _ScriptedRunner(
        scripts=(_tool_script(_tool_call("tc_1")), ()),
        raise_on_call_indices=frozenset({1}),
    )

    with caplog.at_level(logging.WARNING, logger="dayu.engine.agent"):
        events = await _collect(
            _AsyncAgent(request=_request(executor=executor), runner=runner)
        )

    failed = _failed_data(events)
    assert failed.error_code == "runner_exception"
    assert failed.message == "RuntimeError: runner exploded"
    assert "agent.runner_exception" in caplog.text
    assert "RuntimeError: runner exploded" in caplog.text
    assert len(executor.requests) == 1
    assert len(runner.messages_seen) == 2
    second_messages = runner.messages_seen[1]
    assert isinstance(second_messages[-2], AssistantMessage)
    assert isinstance(second_messages[-1], ToolMessage)
    assert json.loads(second_messages[-1].content) == {"sum": 5}


@pytest.mark.asyncio
async def test_runner_call_completed_missing_state_is_controlled_failure(
    caplog: LogCaptureFixture,
) -> None:
    """Runner 完成边界发现状态缺失时必须产出可控失败终态。

    :param caplog: pytest 日志捕获 fixture。
    :returns: 无返回值。
    :raises AssertionError: 终态或诊断日志不符合预期时抛出。
    """

    runner = _StateClearingRunner(events=_final_script("done"))
    agent = _AsyncAgent(request=_request(), runner=runner)
    runner.agent = agent

    with caplog.at_level(logging.CRITICAL, logger="dayu.engine.agent"):
        events = await _collect(agent)

    failed = _failed_data(events)
    assert failed.error_code == "missing_terminal"
    assert failed.recoverable is False
    assert "engine.agent.missing_iteration_state" in caplog.text
    assert "runner_call_completed=true" in caplog.text
    assert "iteration_index=0" in caplog.text
    assert runner.close_count == 1


@pytest.mark.asyncio
async def test_verbose_logs_engine_main_path_without_tool_payloads(
    caplog: LogCaptureFixture,
) -> None:
    """VERBOSE 能串起 Engine 主路径与工具闭环，且不泄漏参数 / 结果。"""

    secret_argument = "raw-cursor-and-scope-token-secret"
    secret_result = "tool-result-secret"
    executor = _RecordingToolExecutor(
        outcomes={
            "tc_1": _success(
                {
                    "answer": secret_result,
                    "cursor": "raw-cursor-secret",
                    "scope_token": "scope-token-secret",
                }
            )
        }
    )
    runner = _ScriptedRunner(
        scripts=(
            _tool_script(
                _tool_call("tc_1", arguments={"query": secret_argument})
            ),
            _final_script("done"),
        )
    )

    with caplog.at_level(15, logger="dayu.engine.agent"):
        events = await _collect(
            _AsyncAgent(request=_request(executor=executor), runner=runner)
        )

    assert _terminal(events).type is EngineEventType.FINAL_ANSWER
    log_text = caplog.text
    assert "engine.agent.run_start" in log_text
    assert "engine.agent.iteration_start" in log_text
    assert "engine.agent.runner_call_start" in log_text
    assert "engine.agent.runner_call_completed" in log_text
    assert "decision=tool_calls" in log_text
    assert "engine.agent.tool_loop_start" in log_text
    assert "engine.agent.tool_call_requested" in log_text
    assert "engine.agent.tool_batch_completed" in log_text
    assert "engine.agent.tool_messages_injected" in log_text
    assert "engine.agent.final_ready" in log_text
    assert "engine.agent.continuation_terminal" not in log_text
    assert "engine.agent.terminal" in log_text
    assert "session_id=session_phase3" in log_text
    assert "run_id=run_phase3" in log_text
    assert "iteration_id=run_phase3_iteration_1" in log_text
    assert secret_argument not in log_text
    assert secret_result not in log_text
    assert "raw-cursor-secret" not in log_text
    assert "scope-token-secret" not in log_text


@pytest.mark.asyncio
async def test_tool_awaiting_suspends_run_with_accepted_and_awaiting_records() -> None:
    """awaiting outcome 必须产出 tool_awaiting 与 run_suspended，且 RUN_SUSPENDED 携带 accepted/awaiting 记录。"""

    snapshot = ToolAwaitSnapshot(
        snapshot_id="snapshot-1",
        captured_at=_utc_now(),
    )
    awaiting = _awaiting(resume_token="resume-1", snapshot=snapshot)
    awaiting_executor = _RecordingToolExecutor(
        outcomes={"tc_1": awaiting, "tc_2": _success(2)}
    )
    runner = _ScriptedRunner(
        scripts=(
            _tool_script(_tool_call("tc_1"), _tool_call("tc_2", index=1)),
            _final_script("should-not-run"),
        )
    )

    awaiting_events = await _collect(
        _AsyncAgent(
            request=_request(executor=awaiting_executor),
            runner=runner,
        )
    )

    terminal = _terminal(awaiting_events)
    awaiting_events_only = [
        event
        for event in awaiting_events
        if event.type is EngineEventType.TOOL_AWAITING
    ]
    accepted_events = [
        event
        for event in awaiting_events
        if event.type is EngineEventType.TOOL_RESULT_ACCEPTED
    ]
    assert terminal.type is EngineEventType.RUN_SUSPENDED
    # 两个 call：一个 awaiting，一个 completed；两者都进入对应记录。
    assert len(awaiting_events_only) == 1
    assert len(accepted_events) == 1
    assert isinstance(awaiting_events_only[0].data, ToolAwaitingData)
    assert awaiting_events_only[0].data.iteration_id == "run_phase3_iteration_1"
    assert awaiting_events_only[0].data.record.call.tool_call_id == "tc_1"
    assert awaiting_events_only[0].data.record.await_spec is awaiting.await_spec
    assert awaiting_events_only[0].data.record.snapshot is snapshot

    suspended = _suspended_data(awaiting_events)
    assert suspended.reason == RUN_SUSPENDED_REASON_TOOL_AWAITING
    assert suspended.resume_hint is None
    assert len(suspended.awaiting_records) == 1
    assert suspended.awaiting_records[0].call.tool_call_id == "tc_1"
    assert suspended.awaiting_records[0].await_spec is awaiting.await_spec
    assert suspended.awaiting_records[0].snapshot is snapshot
    assert len(suspended.accepted_records) == 1
    assert suspended.accepted_records[0].call.tool_call_id == "tc_2"
    assert len(awaiting_executor.requests) == 1
    request_ids = sorted(call.tool_call_id for call in awaiting_executor.requests[0].calls)
    assert request_ids == ["tc_1", "tc_2"]
    assert runner.call_count == 1
    assert runner.close_count == 1
    assert len(runner.messages_seen) == 1


@pytest.mark.asyncio
async def test_awaiting_cancellation_before_and_after_outcome_boundary() -> None:
    """取消在 awaiting outcome 前后命中时遵守提交边界。"""

    token_before = ControllableCancellationToken()
    before_executor = _RecordingToolExecutor(
        outcomes={"tc_1": _awaiting()},
        token_to_cancel=token_before,
    )
    before_events = await _collect(
        _AsyncAgent(
            request=_request(token=token_before, executor=before_executor),
            runner=_ScriptedRunner(scripts=(_tool_script(_tool_call("tc_1")),)),
        )
    )

    assert _terminal(before_events).type is EngineEventType.RUN_CANCELLED
    assert [
        event
        for event in before_events
        if event.type is EngineEventType.TOOL_AWAITING
    ] == []

    token_after = ControllableCancellationToken()
    after_executor = _RecordingToolExecutor(outcomes={"tc_1": _awaiting()})
    after_agent = _AsyncAgent(
        request=_request(token=token_after, executor=after_executor),
        runner=_ScriptedRunner(scripts=(_tool_script(_tool_call("tc_1")),)),
    )
    after_events: list[EngineEvent] = []
    async for event in after_agent.run_messages():
        after_events.append(event)
        if event.type is EngineEventType.TOOL_AWAITING:
            token_after.request_cancel("after_awaiting")

    assert _terminal(after_events).type is EngineEventType.RUN_SUSPENDED
    assert [
        event.type for event in after_events
        if event.type
        in {EngineEventType.TOOL_AWAITING, EngineEventType.RUN_SUSPENDED}
    ] == [EngineEventType.TOOL_AWAITING, EngineEventType.RUN_SUSPENDED]
    assert [
        event
        for event in after_events
        if event.type is EngineEventType.RUN_CANCELLED
    ] == []


@pytest.mark.asyncio
async def test_duplicate_and_executor_exception_paths(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """duplicate、executor exception 均有明确收口。"""

    duplicate_executor = _RecordingToolExecutor(
        outcomes={"tc_1": _success(1)}
    )
    duplicate_events = await _collect(
        _AsyncAgent(
            request=_request(executor=duplicate_executor),
            runner=_ScriptedRunner(
                scripts=(
                    _tool_script(_tool_call("tc_1"), _tool_call("tc_1", index=1)),
                )
            ),
        )
    )
    assert _failed_data(duplicate_events).error_code == "duplicate_tool_call_id"
    assert len(duplicate_executor.requests) == 0

    mismatched_record = BatchToolExecutionRecord(
        tool_call_id="tc_other",
        outcome=_success(1),
    )
    mismatch_runner = _ScriptedRunner(
        scripts=(_tool_script(_tool_call("tc_1")),)
    )
    mismatch_events = await _collect(
        _AsyncAgent(
            request=_request(
                executor=_RecordingToolExecutor(
                    outcomes={"tc_1": _success(1)},
                    records_override=(mismatched_record,),
                )
            ),
            runner=mismatch_runner,
        )
    )
    mismatch_failed = _failed_data(mismatch_events)
    assert mismatch_failed.error_code == "tool_batch_outcome_mismatch"
    assert mismatch_runner.request_identities_seen[0] is not None
    assert (
        mismatch_failed.client_correlation_id
        == mismatch_runner.request_identities_seen[0].client_correlation_id
    )

    exploding_executor = _RecordingToolExecutor(
        outcomes={"tc_1": _success(1)},
        raise_for_call_id="tc_1",
    )
    runner = _ScriptedRunner(
        scripts=(_tool_script(_tool_call("tc_1")), _final_script("recovered"))
    )
    events = await _collect(
        _AsyncAgent(request=_request(executor=exploding_executor), runner=runner)
    )
    assert _terminal(events).type is EngineEventType.FINAL_ANSWER
    tool_message = runner.messages_seen[1][-1]
    assert isinstance(tool_message, ToolMessage)
    assert json.loads(tool_message.content)["error"] == _TOOL_EXECUTOR_EXCEPTION_ERROR

    cancelled_executor = _RecordingToolExecutor(
        outcomes={"tc_1": _success(1)},
        raise_cancelled_for_call_id="tc_1",
    )
    cancelled_runner = _ScriptedRunner(
        scripts=(_tool_script(_tool_call("tc_1")), _final_script("recovered"))
    )
    with caplog.at_level("WARNING", logger="dayu.engine.agent"):
        cancelled_events = await _collect(
            _AsyncAgent(
                request=_request(executor=cancelled_executor),
                runner=cancelled_runner,
            )
        )
    assert _terminal(cancelled_events).type is EngineEventType.FINAL_ANSWER
    cancelled_tool_message = cancelled_runner.messages_seen[1][-1]
    assert isinstance(cancelled_tool_message, ToolMessage)
    assert json.loads(cancelled_tool_message.content)["error"] == (
        _TOOL_EXECUTOR_EXCEPTION_ERROR
    )
    assert "tool_executor.cancelled_without_run_cancellation" in caplog.text


@pytest.mark.asyncio
async def test_cancel_before_tool_batch_does_not_register_tool_call_id() -> None:
    """取消命中工具批执行前时，不应先登记本批 tool_call_id。"""

    token = ControllableCancellationToken()
    executor = _RecordingToolExecutor(outcomes={"tc_1": _success(1)})
    runner = _ScriptedRunner(
        scripts=(
            _tool_script(_tool_call("tc_1")),
            _final_script("unreachable"),
        ),
        token_to_cancel=token,
        cancel_after_call_indices=frozenset({0}),
    )
    agent = _AsyncAgent(
        request=_request(token=token, executor=executor),
        runner=runner,
    )

    events = await _collect(agent)

    assert _terminal(events).type is EngineEventType.RUN_CANCELLED
    assert agent._executed_tool_call_ids == set()
    assert len(executor.requests) == 0
    assert runner.call_count == 1


@pytest.mark.asyncio
async def test_tool_execution_timeout_fails_run_without_tool_result() -> None:
    """工具握手超时时收口为不可恢复 run_failed。"""

    executor = _HangingToolExecutor()
    runner = _ScriptedRunner(
        scripts=(_tool_script(_tool_call("tc_1")), _final_script("unused"))
    )

    events = await _collect(
        _AsyncAgent(
            request=_request(
                executor=executor,
                tool_execution_timeout_seconds=_FAST_TOOL_EXECUTION_TIMEOUT_SECONDS,
            ),
            runner=runner,
        )
    )

    failed = _failed_data(events)
    assert failed.error_code == "tool_execution_timeout"
    assert failed.recoverable is False
    assert runner.request_identities_seen[0] is not None
    assert failed.client_correlation_id == (
        runner.request_identities_seen[0].client_correlation_id
    )
    assert executor.cancelled is True
    assert len(executor.requests) == 1
    assert (
        executor.requests[0].context.timeout_seconds
        == _FAST_TOOL_EXECUTION_TIMEOUT_SECONDS
    )
    assert runner.call_count == 1
    assert EngineEventType.TOOL_RESULT_ACCEPTED not in {
        event.type for event in events
    }


@pytest.mark.asyncio
async def test_tool_execution_timeout_wins_over_cleanup_cancel() -> None:
    """工具握手超时已判定后，清理阶段 late cancel 不覆盖 run_failed。"""

    token = ControllableCancellationToken()
    executor = _HangingToolExecutor(token_to_cancel_on_cancel=token)
    runner = _ScriptedRunner(scripts=(_tool_script(_tool_call("tc_1")),))

    events = await _collect(
        _AsyncAgent(
            request=_request(
                token=token,
                executor=executor,
                tool_execution_timeout_seconds=_FAST_TOOL_EXECUTION_TIMEOUT_SECONDS,
            ),
            runner=runner,
        )
    )

    failed = _failed_data(events)
    assert failed.error_code == "tool_execution_timeout"
    assert failed.recoverable is False
    assert runner.request_identities_seen[0] is not None
    assert failed.client_correlation_id == (
        runner.request_identities_seen[0].client_correlation_id
    )
    assert executor.cancelled is True
    assert token.is_cancelled()
    assert _terminal(events).type is EngineEventType.RUN_FAILED


@pytest.mark.asyncio
async def test_tool_execution_timeout_wins_over_runner_close_cancel() -> None:
    """工具超时后的 runner close 触发 late cancel 时仍保持超时失败。"""

    token = ControllableCancellationToken()
    executor = _HangingToolExecutor()
    runner = _ScriptedRunner(
        scripts=(_tool_script(_tool_call("tc_1")),),
        token_to_cancel_on_close=token,
    )

    events = await _collect(
        _AsyncAgent(
            request=_request(
                token=token,
                executor=executor,
                tool_execution_timeout_seconds=_FAST_TOOL_EXECUTION_TIMEOUT_SECONDS,
            ),
            runner=runner,
        )
    )

    failed = _failed_data(events)
    assert failed.error_code == "tool_execution_timeout"
    assert failed.recoverable is False
    assert runner.request_identities_seen[0] is not None
    assert failed.client_correlation_id == (
        runner.request_identities_seen[0].client_correlation_id
    )
    assert executor.cancelled is True
    assert token.is_cancelled()
    assert runner.close_count == 1
    assert _terminal(events).type is EngineEventType.RUN_FAILED


@pytest.mark.asyncio
async def test_max_iterations_force_answer_and_raise_error() -> None:
    """最后一轮工具照常执行，随后按 fallback mode 收口。"""

    force_executor = _RecordingToolExecutor(outcomes={"tc_1": _success(5)})
    force_runner = _ScriptedRunner(
        scripts=(_tool_script(_tool_call("tc_1")), _final_script("forced"))
    )
    force_events = await _collect(
        _AsyncAgent(
            request=_request(executor=force_executor, max_iterations=1),
            runner=force_runner,
        )
    )

    force_terminal = _terminal(force_events)
    assert force_terminal.type is EngineEventType.FINAL_ANSWER
    assert isinstance(force_terminal.data, FinalAnswerData)
    assert force_terminal.data.degraded is True
    assert len(force_executor.requests) == 1
    assert force_runner.tools_seen[1] == ()
    assert isinstance(force_runner.messages_seen[1][-1], UserMessage)

    raise_executor = _RecordingToolExecutor(outcomes={"tc_1": _success(5)})
    raise_events = await _collect(
        _AsyncAgent(
            request=_request(
                executor=raise_executor,
                max_iterations=1,
                fallback_mode=AgentFallbackMode.RAISE_ERROR,
            ),
            runner=_ScriptedRunner(scripts=(_tool_script(_tool_call("tc_1")),)),
        )
    )
    raise_failed = _failed_data(raise_events)
    assert raise_failed.error_code == "max_iterations_exceeded"
    assert raise_failed.message == "agent policy max_iterations exhausted"


@pytest.mark.asyncio
async def test_force_answer_empty_and_tool_call_are_fail_closed() -> None:
    """force-answer 空内容或继续 tool call 都不能伪装成 final。

    :returns: ``None``。
    :raises AssertionError: force-answer 失败被伪装成成功 final 时抛出。
    """

    empty_runner = _ScriptedRunner(
        scripts=(_tool_script(_tool_call("tc_1")), _final_script(""))
    )
    empty_events = await _collect(
        _AsyncAgent(
            request=_request(
                executor=_RecordingToolExecutor(outcomes={"tc_1": _success(5)}),
                max_iterations=1,
            ),
            runner=empty_runner,
        )
    )
    empty_failure = _failed_data(empty_events)
    assert empty_failure.error_code == "force_answer_empty"
    assert "trigger=max_iterations_exceeded" in empty_failure.message
    assert empty_runner.request_identities_seen[1] is not None
    assert empty_failure.client_correlation_id == (
        empty_runner.request_identities_seen[1].client_correlation_id
    )

    tool_call_runner = _ScriptedRunner(
        scripts=(
            _tool_script(_tool_call("tc_1")),
            _tool_script(
                _tool_call("tc_2"),
                provider_request_id="req_force_tool",
            ),
        )
    )
    tool_call_events = await _collect(
        _AsyncAgent(
            request=_request(
                executor=_RecordingToolExecutor(outcomes={"tc_1": _success(5)}),
                max_iterations=1,
            ),
            runner=tool_call_runner,
        )
    )
    force_tool_failure = _failed_data(tool_call_events)
    assert force_tool_failure.error_code == "tool_call_not_enabled"
    assert "trigger=max_iterations_exceeded" in force_tool_failure.message
    assert force_tool_failure.provider_request_id == "req_force_tool"
    assert tool_call_runner.request_identities_seen[1] is not None
    assert force_tool_failure.client_correlation_id == (
        tool_call_runner.request_identities_seen[1].client_correlation_id
    )

    failed_batch_runner = _ScriptedRunner(
        scripts=(
            _tool_script(_tool_call("tc_1")),
            _tool_script(_tool_call("tc_2")),
            _final_script(""),
        )
    )
    failed_batch_events = await _collect(
        _AsyncAgent(
            request=_request(
                executor=_RecordingToolExecutor(
                    outcomes={"tc_1": _failed(), "tc_2": _failed()}
                ),
                max_iterations=3,
            ),
            runner=failed_batch_runner,
        )
    )
    failed_batch_failure = _failed_data(failed_batch_events)
    assert failed_batch_failure.error_code == "force_answer_empty"
    assert (
        "trigger=consecutive_failed_tool_batches"
        in failed_batch_failure.message
    )


@pytest.mark.asyncio
async def test_normal_final_empty_content_is_fail_closed() -> None:
    """普通最终回答路径也必须拒绝空 content。"""

    events = await _collect(
        _AsyncAgent(
            request=_request(),
            runner=_ScriptedRunner(scripts=(_final_script(""),)),
        )
    )

    failed = _failed_data(events)
    assert failed.error_code == "runner_empty_final_content"
    assert failed.message == "runner did not produce final content"


@pytest.mark.asyncio
async def test_content_filter_is_degraded_final() -> None:
    """content_filter final answer 必须 filtered=True 且 degraded=True。"""

    events = await _collect(
        _AsyncAgent(
            request=_request(),
            runner=_ScriptedRunner(
                scripts=(
                    _final_script(
                        "filtered",
                        finish_reason=FinishReason.CONTENT_FILTER,
                    ),
                )
            ),
        )
    )

    data = _final_data(events)
    assert data.filtered is True
    assert data.degraded is True


@pytest.mark.asyncio
async def test_length_continuation_appends_prompt_and_joins_content() -> None:
    """finish_reason=length 后必须禁工具续写并拼接最终内容。"""

    runner = _ScriptedRunner(
        scripts=(
            _final_script("partial ", finish_reason=FinishReason.LENGTH),
            _final_script("continued"),
        )
    )
    events = await _collect(
        _AsyncAgent(
            request=_request(
                max_iterations=3,
                continuation_max_attempts=2,
                continuation_prompt="请从截断处继续。",
            ),
            runner=runner,
        )
    )

    data = _final_data(events)
    assert data.content == "partial continued"
    assert data.degraded is True
    assert data.filtered is False
    assert data.finish_reason is FinishReason.STOP
    assert runner.call_count == 2
    assert runner.tools_seen[1] == ()
    assert isinstance(runner.messages_seen[1][-2], AssistantMessage)
    assert runner.messages_seen[1][-2].content == "partial "
    assert isinstance(runner.messages_seen[1][-1], UserMessage)
    assert runner.messages_seen[1][-1].content == "请从截断处继续。"
    assert [
        identity.runner_call_index
        for identity in runner.request_identities_seen
        if identity is not None
    ] == [1, 2]
    assert runner.request_identities_seen[1] is not None
    assert runner.request_identities_seen[1].iteration_id == "run_phase3_iteration_2"
    iteration_completed = [
        event
        for event in events
        if event.type is EngineEventType.ITERATION_COMPLETED
    ]
    assert len(iteration_completed) == 2
    for event, identity in zip(
        iteration_completed, runner.request_identities_seen, strict=True
    ):
        assert isinstance(event.data, IterationCompletedData)
        assert identity is not None
        assert event.data.client_correlation_id == identity.client_correlation_id


@pytest.mark.asyncio
async def test_length_continuation_stops_at_attempt_limit() -> None:
    """达到 continuation 上限后使用已累积内容降级收口。"""

    runner = _ScriptedRunner(
        scripts=(
            _final_script("part1", finish_reason=FinishReason.LENGTH),
            _final_script("part2", finish_reason=FinishReason.LENGTH),
            _final_script("part3", finish_reason=FinishReason.LENGTH),
            _final_script("unused"),
        )
    )
    events = await _collect(
        _AsyncAgent(
            request=_request(max_iterations=5, continuation_max_attempts=2),
            runner=runner,
        )
    )

    data = _final_data(events)
    assert data.content == "part1part2part3"
    assert data.degraded is True
    assert data.finish_reason is FinishReason.LENGTH
    assert runner.call_count == 3


@pytest.mark.asyncio
async def test_length_continuation_respects_max_iterations() -> None:
    """max_iterations 耗尽时不得进入 force-answer，而应降级 final。"""

    runner = _ScriptedRunner(
        scripts=(
            _final_script("part1", finish_reason=FinishReason.LENGTH),
            _final_script("part2", finish_reason=FinishReason.LENGTH),
        )
    )
    events = await _collect(
        _AsyncAgent(
            request=_request(max_iterations=2, continuation_max_attempts=3),
            runner=runner,
        )
    )

    data = _final_data(events)
    assert data.content == "part1part2"
    assert data.degraded is True
    assert data.finish_reason is FinishReason.LENGTH
    assert runner.call_count == 2


@pytest.mark.asyncio
async def test_length_continuation_tool_call_is_fail_closed() -> None:
    """continuation 轮返回 tool calls 时不得执行工具。"""

    executor = _RecordingToolExecutor(outcomes={"tc_1": _success(5)})
    runner = _ScriptedRunner(
        scripts=(
            _final_script("partial", finish_reason=FinishReason.LENGTH),
            _tool_script(
                _tool_call("tc_1"),
                provider_request_id="req_continuation_tool",
            ),
        )
    )
    events = await _collect(
        _AsyncAgent(
            request=_request(
                executor=executor,
                max_iterations=3,
                continuation_max_attempts=2,
            ),
            runner=runner,
        )
    )

    failed = _failed_data(events)
    assert failed.error_code == "continuation_tool_call_not_allowed"
    assert failed.provider_request_id == "req_continuation_tool"
    assert len(executor.requests) == 0
    assert runner.tools_seen[1] == ()


@pytest.mark.asyncio
async def test_content_filter_does_not_trigger_continuation() -> None:
    """content_filter 即使配置 continuation 也必须直接降级 final。"""

    runner = _ScriptedRunner(
        scripts=(
            _final_script(
                "filtered",
                finish_reason=FinishReason.CONTENT_FILTER,
            ),
            _final_script("unused"),
        )
    )
    events = await _collect(
        _AsyncAgent(
            request=_request(max_iterations=3, continuation_max_attempts=2),
            runner=runner,
        )
    )

    data = _final_data(events)
    assert data.content == "filtered"
    assert data.filtered is True
    assert data.degraded is True
    assert runner.call_count == 1


@pytest.mark.asyncio
async def test_cancellation_wins_before_length_continuation() -> None:
    """截断后若 Host 已取消，下一轮 Runner 调用前必须取消收口。"""

    token = ControllableCancellationToken()
    runner = _ScriptedRunner(
        scripts=(
            _final_script("partial", finish_reason=FinishReason.LENGTH),
            _final_script("unused"),
        ),
        token_to_cancel=token,
        cancel_after_call_indices=frozenset({0}),
    )
    events = await _collect(
        _AsyncAgent(
            request=_request(
                token=token,
                max_iterations=3,
                continuation_max_attempts=2,
            ),
            runner=runner,
        )
    )

    assert _terminal(events).type is EngineEventType.RUN_CANCELLED
    assert runner.call_count == 1


@pytest.mark.asyncio
async def test_consecutive_failed_batches_force_answer_raise_and_reset() -> None:
    """连续全失败批次达到阈值后按 fallback mode 收口，成功批次清零。"""

    force_executor = _RecordingToolExecutor(
        outcomes={"tc_1": _failed(), "tc_2": _failed()}
    )
    force_runner = _ScriptedRunner(
        scripts=(
            _tool_script(_tool_call("tc_1")),
            _tool_script(_tool_call("tc_2")),
            _final_script("forced after failures"),
        )
    )
    force_events = await _collect(
        _AsyncAgent(
            request=_request(executor=force_executor, max_iterations=3),
            runner=force_runner,
        )
    )
    assert _final_data(force_events).degraded is True
    assert force_runner.tools_seen[-1] == ()

    raise_executor = _RecordingToolExecutor(
        outcomes={"tc_1": _failed(), "tc_2": _failed()}
    )
    raise_events = await _collect(
        _AsyncAgent(
            request=_request(
                executor=raise_executor,
                max_iterations=3,
                fallback_mode=AgentFallbackMode.RAISE_ERROR,
            ),
            runner=_ScriptedRunner(
                scripts=(
                    _tool_script(_tool_call("tc_1")),
                    _tool_script(_tool_call("tc_2")),
                )
            ),
        )
    )
    raise_failed = _failed_data(raise_events)
    assert raise_failed.error_code == "consecutive_failed_tool_batches"
    assert raise_failed.message == (
        "consecutive failed tool batches threshold reached"
    )

    reset_executor = _RecordingToolExecutor(
        outcomes={"tc_1": _failed(), "tc_2": _success(2), "tc_3": _failed()}
    )
    reset_events = await _collect(
        _AsyncAgent(
            request=_request(executor=reset_executor, max_iterations=3),
            runner=_ScriptedRunner(
                scripts=(
                    _tool_script(_tool_call("tc_1")),
                    _tool_script(_tool_call("tc_2")),
                    _tool_script(_tool_call("tc_3")),
                    _final_script("max forced"),
                )
            ),
        )
    )
    assert _final_data(reset_events).content == "max forced"
    assert len(reset_executor.requests) == 3


@pytest.mark.asyncio
async def test_late_cancellation_after_tool_outcome_preserves_accepted_facts() -> None:
    """工具 outcome 后 late cancel 只阻止下一轮 Runner。"""

    token = ControllableCancellationToken()
    executor = _RecordingToolExecutor(outcomes={"tc_1": _success(5)})
    runner = _ScriptedRunner(
        scripts=(
            (
                _event(
                    RunnerEventType.RUNNER_CONTENT_DELTA,
                    RunnerContentDeltaData(delta="partial"),
                ),
                _event(
                    RunnerEventType.RUNNER_REASONING_DELTA,
                    RunnerReasoningDeltaData(delta="think"),
                ),
                _event(
                    RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
                    RunnerToolCallsCompletedData(
                        tool_calls=(_tool_call("tc_1"),)
                    ),
                ),
                _event(
                    RunnerEventType.RUNNER_DONE,
                    RunnerDoneData(finish_reason=FinishReason.TOOL_CALLS, provider_request_id=None),
                ),
            ),
            _final_script("unused"),
        )
    )

    agent = _AsyncAgent(
        request=_request(token=token, executor=executor),
        runner=runner,
    )
    events: list[EngineEvent] = []
    async for event in agent.run_messages():
        events.append(event)
        if event.type is EngineEventType.TOOL_RESULT_ACCEPTED:
            token.request_cancel("after_tool_result")

    assert _terminal(events).type is EngineEventType.RUN_CANCELLED
    assert runner.call_count == 1
    assert [
        event.type
        for event in events
        if event.type
        in {
            EngineEventType.CONTENT_DELTA,
            EngineEventType.REASONING_DELTA,
            EngineEventType.TOOL_RESULT_ACCEPTED,
            EngineEventType.RUN_CANCELLED,
        }
    ] == [
        EngineEventType.CONTENT_DELTA,
        EngineEventType.REASONING_DELTA,
        EngineEventType.TOOL_RESULT_ACCEPTED,
        EngineEventType.RUN_CANCELLED,
    ]


@pytest.mark.asyncio
async def test_all_cancelled_batch_does_not_trigger_failed_fallback_and_continues() -> None:
    """全部 cancelled 的批次不计入失败、不触发 fallback，下一轮 Runner 正常继续。

    覆盖 ``_all_records_failed`` 在 all-cancelled 批次上必须返回 ``False`` 的
    语义，并验证 ``ToolCallsBatchDoneData`` 计数正确，最终走到 ``FINAL_ANSWER``。
    """

    from dayu.contracts.tool_outcome import (
        TOOL_CANCELLED_REASON_APPROVAL_DENIED,
        TOOL_CANCELLED_REASON_HOST_CANCELLED,
        ToolCancelledOutcome,
    )

    outcomes: dict[str, ToolExecutionOutcome] = {
        "tc_1": ToolCancelledOutcome(
            reason=TOOL_CANCELLED_REASON_APPROVAL_DENIED,
            message="denied a",
            hint=None,
            meta=None,
        ),
        "tc_2": ToolCancelledOutcome(
            reason=TOOL_CANCELLED_REASON_HOST_CANCELLED,
            message="host stop",
            hint=None,
            meta=None,
        ),
    }
    executor = _RecordingToolExecutor(outcomes=outcomes)
    runner = _ScriptedRunner(
        scripts=(
            _tool_script(
                _tool_call("tc_1", index=0),
                _tool_call("tc_2", index=1),
            ),
            _final_script("recovered after cancelled"),
        )
    )

    events = await _collect(
        _AsyncAgent(
            request=_request(executor=executor, max_iterations=3),
            runner=runner,
        )
    )

    # 走到 FINAL_ANSWER，未被 fallback 截断。
    assert _terminal(events).type is EngineEventType.FINAL_ANSWER
    final = _final_data(events)
    assert final.degraded is False

    done = [
        event for event in events
        if event.type is EngineEventType.TOOL_CALLS_BATCH_DONE
    ]
    assert len(done) == 1
    assert isinstance(done[0].data, ToolCallsBatchDoneData)
    assert done[0].data.cancelled_count == 2
    assert done[0].data.failed_count == 0
    assert done[0].data.completed_count == 0

    # all-cancelled 不算 failed，下一轮 Runner 被允许调用。
    assert runner.call_count == 2


@pytest.mark.asyncio
async def test_all_awaiting_batch_suspends_with_empty_accepted_records() -> None:
    """批内全部 awaiting 时仍正确产出多个 tool_awaiting 与 run_suspended。

    覆盖 ``accepted_records`` 为空、``awaiting_records`` 完整的边界。
    """

    awaiting_a = _awaiting(resume_token="rt-a")
    awaiting_b = _awaiting(resume_token="rt-b")
    executor = _RecordingToolExecutor(
        outcomes={"tc_1": awaiting_a, "tc_2": awaiting_b},
    )
    runner = _ScriptedRunner(
        scripts=(
            _tool_script(
                _tool_call("tc_1", index=0),
                _tool_call("tc_2", index=1),
            ),
            _final_script("should-not-run"),
        )
    )

    events = await _collect(
        _AsyncAgent(request=_request(executor=executor), runner=runner)
    )

    terminal = _terminal(events)
    assert terminal.type is EngineEventType.RUN_SUSPENDED

    awaiting_events = [
        event for event in events
        if event.type is EngineEventType.TOOL_AWAITING
    ]
    accepted_events = [
        event for event in events
        if event.type is EngineEventType.TOOL_RESULT_ACCEPTED
    ]
    assert len(awaiting_events) == 2
    assert accepted_events == []

    suspended = _suspended_data(events)
    assert suspended.reason == RUN_SUSPENDED_REASON_TOOL_AWAITING
    assert suspended.accepted_records == ()
    assert len(suspended.awaiting_records) == 2
    awaiting_ids = sorted(
        record.call.tool_call_id for record in suspended.awaiting_records
    )
    assert awaiting_ids == ["tc_1", "tc_2"]
    # 不下一轮：runner 仅被调用一次。
    assert runner.call_count == 1


@pytest.mark.asyncio
async def test_late_cancel_after_accepted_before_awaiting_does_not_swallow_suspend() -> None:
    """accepted 已 emit 但 TOOL_AWAITING 尚未 emit 前命中的取消不能吞掉挂起。

    依据 commit-edge：executor 返回的 outcome 视为已接受事实，仍必须发出
    tool_awaiting 与 run_suspended，不应降级为 run_cancelled。
    """

    token = ControllableCancellationToken()
    snapshot = ToolAwaitSnapshot(
        snapshot_id="snapshot-late",
        captured_at=_utc_now(),
    )
    awaiting = _awaiting(resume_token="rt-late", snapshot=snapshot)
    # 同批一个成功（先 emit accepted），一个 awaiting（之后 emit awaiting）。
    executor = _RecordingToolExecutor(
        outcomes={"tc_1": _success(1), "tc_2": awaiting},
    )
    runner = _ScriptedRunner(
        scripts=(
            _tool_script(
                _tool_call("tc_1", index=0),
                _tool_call("tc_2", index=1),
            ),
            _final_script("should-not-run"),
        )
    )

    agent = _AsyncAgent(
        request=_request(token=token, executor=executor),
        runner=runner,
    )
    events: list[EngineEvent] = []
    triggered = False
    async for event in agent.run_messages():
        events.append(event)
        # 在 TOOL_AWAITING 之前、TOOL_RESULT_ACCEPTED 之后触发取消。
        if (
            not triggered
            and event.type is EngineEventType.TOOL_RESULT_ACCEPTED
        ):
            token.request_cancel("after_accepted_before_awaiting")
            triggered = True

    assert triggered
    terminal = _terminal(events)
    assert terminal.type is EngineEventType.RUN_SUSPENDED

    awaiting_events = [
        event for event in events
        if event.type is EngineEventType.TOOL_AWAITING
    ]
    cancel_events = [
        event for event in events
        if event.type is EngineEventType.RUN_CANCELLED
    ]
    assert len(awaiting_events) == 1
    assert cancel_events == []
    awaiting_data = awaiting_events[0].data
    assert isinstance(awaiting_data, ToolAwaitingData)
    assert awaiting_data.record.call.tool_call_id == "tc_2"

    suspended = _suspended_data(events)
    assert len(suspended.accepted_records) == 1
    assert suspended.accepted_records[0].call.tool_call_id == "tc_1"
    assert len(suspended.awaiting_records) == 1
    assert suspended.awaiting_records[0].call.tool_call_id == "tc_2"
