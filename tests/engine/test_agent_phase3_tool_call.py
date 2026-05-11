"""Phase 3 tool calling 与 Phase 5 continuation 回归测试。"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest
from _pytest.logging import LogCaptureFixture

from dayu.contracts.json_value import JsonValue
from dayu.contracts.tool_call import (
    GeminiToolCallState,
    ToolCallRequest,
    ToolExecutionRequest,
)
from dayu.contracts.tool_outcome import (
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
    RUN_SUSPENDED_REASON_TOOL_AWAITING,
    RunFailedData,
    RunSuspendedData,
    ToolAwaitingData,
    ToolCallRequestedData,
    ToolResultAcceptedData,
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
    RunnerToolCallDeltaData,
    RunnerToolCallsCompletedData,
)
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.engine.runners.openai.non_stream_parser import parse_non_stream_response
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
from tests.engine.runners.openai._sse_helpers import make_no_thought_hook


def _utc_now() -> datetime:
    """返回测试用 UTC 当前时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


@dataclass(slots=True)
class _Token:
    """测试用 cancellation token。"""

    cancelled: bool = False
    reason: str | None = None
    requested: datetime | None = None

    def is_cancelled(self) -> bool:
        """返回是否已取消。

        :returns: 已取消返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self.cancelled

    def cancel_reason(self) -> str | None:
        """返回取消原因。

        :returns: 取消原因或 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return self.reason

    def requested_at(self) -> datetime | None:
        """返回取消请求时间。

        :returns: 请求时间或 ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return self.requested

    def trigger(self, reason: str = "test_cancelled") -> None:
        """触发取消。

        :param reason: 取消原因。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.cancelled = True
        self.reason = reason
        self.requested = _utc_now()


@dataclass(slots=True)
class _ScriptedRunner:
    """按调用次数产出 RunnerEvent 的 fake Runner。"""

    scripts: tuple[tuple[RunnerEvent, ...], ...]
    supports_tools: bool = True
    raise_on_call_indices: frozenset[int] = field(default_factory=frozenset)
    token_to_cancel: _Token | None = None
    cancel_after_call_indices: frozenset[int] = field(default_factory=frozenset)
    call_count: int = 0
    close_count: int = 0
    tools_seen: list[tuple[ToolSchema, ...]] = field(default_factory=list)
    messages_seen: list[tuple[AgentMessage, ...]] = field(default_factory=list)

    def call(
        self,
        messages: Sequence[AgentMessage],
        options: RunnerCallOptions,
        tools: Sequence[ToolSchema],
    ) -> AsyncIterator[RunnerEvent]:
        """返回脚本化 RunnerEvent 流。

        :param messages: Agent 消息。
        :param options: Runner 调用参数。
        :param tools: 本轮工具 schema。
        :returns: RunnerEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        self.messages_seen.append(tuple(messages))
        self.tools_seen.append(tuple(tools))
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
            self.token_to_cancel.trigger()


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
    ) -> AsyncIterator[RunnerEvent]:
        """返回会破坏迭代状态不变量的 RunnerEvent 流。

        :param messages: Agent 消息。
        :param options: Runner 调用参数。
        :param tools: 本轮工具 schema。
        :returns: RunnerEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

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
    """记录请求并返回预设 outcome 的 fake ToolExecutor。"""

    outcomes: Mapping[str, ToolExecutionOutcome]
    token_to_cancel: _Token | None = None
    raise_for_call_id: str | None = None
    requests: list[ToolExecutionRequest] = field(default_factory=list)

    async def execute(self, request: ToolExecutionRequest) -> ToolExecutionOutcome:
        """执行 fake 工具调用。

        :param request: 工具执行请求。
        :returns: 预设工具 outcome。
        :raises RuntimeError: 配置 ``raise_for_call_id`` 时抛出。
        """

        self.requests.append(request)
        if self.raise_for_call_id == request.call.tool_call_id:
            raise RuntimeError("tool exploded")
        if self.token_to_cancel is not None:
            self.token_to_cancel.trigger()
        return self.outcomes[request.call.tool_call_id]


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


def _tool_script(*tool_calls: ToolCallRequest) -> tuple[RunnerEvent, ...]:
    """构造请求工具的 Runner 脚本。

    :param tool_calls: 工具调用请求。
    :returns: RunnerEvent 元组。
    :raises Exception: 不主动抛出异常。
    """

    return (
        _event(
            RunnerEventType.RUNNER_CONTENT_COMPLETED,
            RunnerContentCompletedData(
                content=None,
                reasoning_content="reason",
                finish_reason=FinishReason.TOOL_CALLS,
            ),
        ),
        _event(
            RunnerEventType.RUNNER_TOOL_CALLS_COMPLETED,
            RunnerToolCallsCompletedData(tool_calls=tuple(tool_calls)),
        ),
        _event(
            RunnerEventType.RUNNER_DONE,
            RunnerDoneData(finish_reason=FinishReason.TOOL_CALLS),
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
                finish_reason=finish_reason,
            ),
        ),
        _event(
            RunnerEventType.RUNNER_DONE,
            RunnerDoneData(finish_reason=finish_reason),
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
    token: _Token | None = None,
    executor: _RecordingToolExecutor | None = None,
    max_iterations: int = 2,
    fallback_mode: AgentFallbackMode = AgentFallbackMode.FORCE_ANSWER,
    disable_tools: bool = False,
    allow_tool_calls: bool = True,
    max_failed_batches: int = 2,
    continuation_max_attempts: int = 3,
    continuation_prompt: str = "请继续。",
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
            fallback_mode=fallback_mode,
            fallback_prompt="请直接回答。",
            continuation_prompt=continuation_prompt,
            max_consecutive_failed_tool_batches=max_failed_batches,
        ),
        tool_schemas=(_schema(),),
        tool_executor=executor or _RecordingToolExecutor(
            outcomes={"tc_1": _success(5)}
        ),
        cancellation_token=token or _Token(),
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


def test_contract_fields_are_explicit() -> None:
    """Phase 3 contract 字段必须显式存在。"""

    policy = AgentPolicy(
        max_iterations=1,
        continuation_max_attempts=0,
        allow_tool_calls=True,
    )

    assert policy.fallback_mode is AgentFallbackMode.FORCE_ANSWER
    assert policy.max_consecutive_failed_tool_batches == 2
    assert policy.fallback_prompt
    assert policy.continuation_prompt


def test_agent_policy_rejects_invalid_values() -> None:
    """AgentPolicy 非法策略值必须在 contract 构造期 fail fast。"""

    for threshold in (0, -1):
        with pytest.raises(ValueError):
            AgentPolicy(
                max_iterations=1,
                continuation_max_attempts=0,
                allow_tool_calls=True,
                max_consecutive_failed_tool_batches=threshold,
            )
    with pytest.raises(ValueError):
        AgentPolicy(
            max_iterations=1,
            continuation_max_attempts=-1,
            allow_tool_calls=True,
        )
    with pytest.raises(ValueError):
        AgentPolicy(
            max_iterations=1,
            continuation_max_attempts=0,
            allow_tool_calls=True,
            continuation_prompt=" ",
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
    assert executor.requests[0].context.session_id == "session_phase3"
    assert executor.requests[0].context.run_id == "run_phase3"
    assert executor.requests[0].context.iteration_id == "run_phase3_iteration_1"
    assert executor.requests[0].context.index_in_iteration == 0
    assert executor.requests[0].context.correlation_id == (
        "run_phase3:run_phase3_iteration_1:tc_1"
    )

    requested = [event for event in events if event.type is EngineEventType.TOOL_CALL_REQUESTED]
    accepted = [event for event in events if event.type is EngineEventType.TOOL_RESULT_ACCEPTED]
    assert len(requested) == 1
    assert len(accepted) == 1
    assert isinstance(requested[0].data, ToolCallRequestedData)
    assert isinstance(accepted[0].data, ToolResultAcceptedData)
    assert requested[0].data.provider_state == GeminiToolCallState(thought_signature="sig")
    assert accepted[0].data.index_in_iteration == 0

    second_messages = runner.messages_seen[1]
    assert isinstance(second_messages[-2], AssistantMessage)
    assert isinstance(second_messages[-1], ToolMessage)
    assert second_messages[-2].tool_calls[0].id == "tc_1"
    assert second_messages[-2].reasoning_content == "reason"
    assert json.loads(second_messages[-1].content) == {"sum": 5}
    assert runner.tools_seen[0] == (_schema(),)
    assert runner.close_count == 1


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
                    RunnerDoneData(finish_reason=FinishReason.TOOL_CALLS),
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
    """非流式 tool_calls 的 reasoning_content 必须进入下一轮 assistant。"""

    payload = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning_content": "非流式推理",
                        "tool_calls": [
                            {
                                "id": "tc_1",
                                "type": "function",
                                "function": {
                                    "name": "add_numbers",
                                    "arguments": "{\"a\":2,\"b\":3}",
                                },
                            }
                        ],
                    },
                }
            ]
        }
    ).encode("utf-8")
    first_script = tuple(
        parse_non_stream_response(payload, hook=make_no_thought_hook())
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
async def test_multiple_tool_calls_sort_by_index_and_execute_once() -> None:
    """多个 tool call 按 index 稳定排序且每个最多执行一次。"""

    executor = _RecordingToolExecutor(
        outcomes={"tc_1": _success(1), "tc_2": _success(2)}
    )
    runner = _ScriptedRunner(
        scripts=(
            _tool_script(_tool_call("tc_2", index=1), _tool_call("tc_1", index=0)),
            _final_script("done"),
        )
    )

    await _collect(_AsyncAgent(request=_request(executor=executor), runner=runner))

    assert [request.call.tool_call_id for request in executor.requests] == [
        "tc_1",
        "tc_2",
    ]


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

    for request, runner in (
        (
            _request(disable_tools=True),
            _ScriptedRunner(scripts=(_tool_script(_tool_call("tc_1")),)),
        ),
        (
            _request(allow_tool_calls=False),
            _ScriptedRunner(scripts=(_tool_script(_tool_call("tc_1")),)),
        ),
        (
            _request(),
            _ScriptedRunner(
                scripts=(_tool_script(_tool_call("tc_1")),),
                supports_tools=False,
            ),
        ),
    ):
        events = await _collect(_AsyncAgent(request=request, runner=runner))
        terminal = _terminal(events)
        assert terminal.type is EngineEventType.RUN_FAILED
        assert isinstance(terminal.data, RunFailedData)
        assert terminal.data.error_code == "tool_call_not_enabled"


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
                    RunnerDoneData(finish_reason=FinishReason.TOOL_CALLS),
                ),
            ),
        )
    )

    events = await _collect(_AsyncAgent(request=_request(), runner=runner))

    assert _failed_data(events).error_code == "runner_tool_calls_missing"


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
async def test_tool_awaiting_suspends_run_without_next_tool_injection() -> None:
    """awaiting outcome 必须产出 tool_awaiting 与 run_suspended。"""

    snapshot = ToolAwaitSnapshot(
        snapshot_id="snapshot-1",
        captured_at=_utc_now(),
    )
    awaiting = _awaiting(resume_token="resume-1", snapshot=snapshot)
    awaiting_executor = _RecordingToolExecutor(outcomes={"tc_1": awaiting})
    runner = _ScriptedRunner(
        scripts=(
            _tool_script(_tool_call("tc_1")),
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
    assert len(awaiting_events_only) == 1
    assert accepted_events == []
    assert isinstance(awaiting_events_only[0].data, ToolAwaitingData)
    assert awaiting_events_only[0].data.iteration_id == "run_phase3_iteration_1"
    assert awaiting_events_only[0].data.tool_call_id == "tc_1"
    assert awaiting_events_only[0].data.await_spec is awaiting.await_spec
    assert awaiting_events_only[0].data.snapshot is snapshot

    suspended = _suspended_data(awaiting_events)
    assert suspended.reason == RUN_SUSPENDED_REASON_TOOL_AWAITING
    assert suspended.resume_hint is None
    assert suspended.await_spec is awaiting.await_spec
    assert suspended.snapshot is snapshot
    assert len(awaiting_executor.requests) == 1
    assert runner.call_count == 1
    assert runner.close_count == 1
    assert len(runner.messages_seen) == 1


@pytest.mark.asyncio
async def test_awaiting_cancellation_priority_before_and_after_event() -> None:
    """取消命中时必须优先 run_cancelled，不伪装成 suspended。"""

    token_before = _Token()
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

    token_after = _Token()
    after_executor = _RecordingToolExecutor(outcomes={"tc_1": _awaiting()})
    after_agent = _AsyncAgent(
        request=_request(token=token_after, executor=after_executor),
        runner=_ScriptedRunner(scripts=(_tool_script(_tool_call("tc_1")),)),
    )
    after_events: list[EngineEvent] = []
    async for event in after_agent.run_messages():
        after_events.append(event)
        if event.type is EngineEventType.TOOL_AWAITING:
            token_after.trigger("after_awaiting")

    assert _terminal(after_events).type is EngineEventType.RUN_CANCELLED
    assert [
        event.type for event in after_events
        if event.type
        in {EngineEventType.TOOL_AWAITING, EngineEventType.RUN_CANCELLED}
    ] == [EngineEventType.TOOL_AWAITING, EngineEventType.RUN_CANCELLED]
    assert [
        event
        for event in after_events
        if event.type is EngineEventType.RUN_SUSPENDED
    ] == []


@pytest.mark.asyncio
async def test_duplicate_and_executor_exception_paths() -> None:
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
    assert len(duplicate_executor.requests) == 1

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
    assert json.loads(tool_message.content)["error"] == "tool_executor_exception"


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
    """force-answer 空内容或继续 tool call 都不能伪装成 final。"""

    empty_events = await _collect(
        _AsyncAgent(
            request=_request(
                executor=_RecordingToolExecutor(outcomes={"tc_1": _success(5)}),
                max_iterations=1,
            ),
            runner=_ScriptedRunner(
                scripts=(_tool_script(_tool_call("tc_1")), _final_script(""))
            ),
        )
    )
    assert _failed_data(empty_events).error_code == "force_answer_empty"

    tool_call_events = await _collect(
        _AsyncAgent(
            request=_request(
                executor=_RecordingToolExecutor(outcomes={"tc_1": _success(5)}),
                max_iterations=1,
            ),
            runner=_ScriptedRunner(
                scripts=(
                    _tool_script(_tool_call("tc_1")),
                    _tool_script(_tool_call("tc_2")),
                )
            ),
        )
    )
    assert _failed_data(tool_call_events).error_code == "tool_call_not_enabled"


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
            _tool_script(_tool_call("tc_1")),
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

    token = _Token()
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
async def test_cancellation_after_tool_outcome_wins_before_injection() -> None:
    """工具 outcome 后若 token 取消，必须 run_cancelled 且不注入下一轮。"""

    token = _Token()
    executor = _RecordingToolExecutor(
        outcomes={"tc_1": _success(5)},
        token_to_cancel=token,
    )
    runner = _ScriptedRunner(scripts=(_tool_script(_tool_call("tc_1")),))

    events = await _collect(
        _AsyncAgent(
            request=_request(token=token, executor=executor),
            runner=runner,
        )
    )

    assert _terminal(events).type is EngineEventType.RUN_CANCELLED
    assert runner.call_count == 1
    assert EngineEventType.TOOL_RESULT_ACCEPTED not in {event.type for event in events}
