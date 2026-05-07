"""Host P3 多轮 Conversation Memory smoke 测试。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from dayu.contracts import CancellationToken
from dayu.contracts.tool_outcome import ToolCompletedOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.engine import (
    AgentMessage,
    AgentMessageRole,
    AgentPolicy,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    FinishReason,
    RunnerCallOptions,
    RunnerSpec,
    SystemMessage,
    ToolResultAcceptedData,
    UserMessage,
)
from dayu.host._run_harness import LocalRunHarness
from dayu.host.contracts import (
    RunEvent,
    RunEventType,
    RunInput,
    RunOptions,
    StartRunRequest,
)

_WAIT_SPIN_LIMIT: int = 20
_WAIT_SLEEP_SECONDS: float = 0.0


def _utc_now() -> datetime:
    """返回测试用 UTC 当前时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


@dataclass(slots=True)
class _RecordingProxy:
    """记录 Host 交给 Engine 的 RunInput，并按 run id 产出脚本事件。"""

    messages_by_run: dict[str, tuple[AgentMessage, ...]] = field(
        default_factory=dict
    )

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回脚本化 EngineEvent 流。

        :param request: Host start_run 请求。
        :param cancellation_token: Host 注入的取消 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        self.messages_by_run[request.run_id] = request.input.messages
        return self._iter_events(request)

    async def _iter_events(
        self, request: StartRunRequest
    ) -> AsyncIterator[EngineEvent]:
        """按 run id 产出 EngineEvent。

        :param request: Host start_run 请求。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        if request.run_id == "run-1":
            yield _tool_event(request)
        yield _final_event(request)


def _tool_event(request: StartRunRequest) -> EngineEvent:
    """构造工具事实事件。

    :param request: Host start_run 请求。
    :returns: EngineEvent。
    :raises Exception: 不主动抛出异常。
    """

    return EngineEvent(
        event_id=f"{request.run_id}:tool",
        sequence=1,
        session_id=request.session_id,
        run_id=request.run_id,
        occurred_at=_utc_now(),
        type=EngineEventType.TOOL_RESULT_ACCEPTED,
        data=ToolResultAcceptedData(
            iteration_id="iter",
            tool_call_id="tool-call-1",
            name="financial_fact_lookup",
            index_in_iteration=0,
            outcome=ToolCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value={"revenue": 100},
                    truncation=None,
                    meta=None,
                )
            ),
        ),
        metadata=None,
    )


def _final_event(request: StartRunRequest) -> EngineEvent:
    """构造 final answer 事件。

    :param request: Host start_run 请求。
    :returns: EngineEvent。
    :raises Exception: 不主动抛出异常。
    """

    content = "第一轮最终回答" if request.run_id == "run-1" else "第二轮最终回答"
    return EngineEvent(
        event_id=f"{request.run_id}:final",
        sequence=2,
        session_id=request.session_id,
        run_id=request.run_id,
        occurred_at=_utc_now(),
        type=EngineEventType.FINAL_ANSWER,
        data=FinalAnswerData(
            content=content,
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
        metadata=None,
    )


def _request(*, run_id: str, content: str) -> StartRunRequest:
    """构造 StartRunRequest。

    :param run_id: Run id。
    :param content: 用户输入正文。
    :returns: StartRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    return StartRunRequest(
        session_id="session-smoke",
        run_id=run_id,
        input=RunInput(
            messages=(
                UserMessage(role=AgentMessageRole.USER, content=content),
            )
        ),
        options=RunOptions(
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
                max_iterations=3,
                continuation_max_attempts=1,
                allow_tool_calls=True,
            ),
            stream=True,
            disable_tools=True,
            tool_schemas=(),
        ),
    )


async def _collect(events: AsyncIterator[RunEvent]) -> tuple[RunEvent, ...]:
    """收集 RunEvent。

    :param events: RunEvent 异步流。
    :returns: RunEvent 元组。
    :raises Exception: 透传事件流异常。
    """

    collected: list[RunEvent] = []
    async for event in events:
        collected.append(event)
    return tuple(collected)


async def _wait_for_projection(harness: LocalRunHarness) -> None:
    """等待第一轮终态事件投影进入 memory store。

    :param harness: Host run harness。
    :returns: 无返回值。
    :raises AssertionError: 超时后仍未投影时抛出。
    """

    for _ in range(_WAIT_SPIN_LIMIT):
        snapshot = await harness.memory_store.get_snapshot("session-smoke")
        if snapshot.recent_raw_turns:
            return
        await asyncio.sleep(_WAIT_SLEEP_SECONDS)
    raise AssertionError("memory projection was not completed")


@pytest.mark.asyncio
async def test_second_run_sees_first_run_final_answer_and_tool_summary() -> None:
    """顺序第二轮通过真实 Builder 路径看到第一轮 memory。"""

    proxy = _RecordingProxy()
    harness = LocalRunHarness(proxy=proxy)

    first_stream = await harness.start_run(
        _request(run_id="run-1", content="第一轮问题")
    )
    first_events = await _collect(first_stream.events)
    await _wait_for_projection(harness)
    second_stream = await harness.start_run(
        _request(run_id="run-2", content="第二轮问题")
    )
    second_events = await _collect(second_stream.events)
    second_messages = proxy.messages_by_run["run-2"]
    first_message = second_messages[0]

    assert first_events[0].type is RunEventType.USER_INPUT_ACCEPTED
    assert second_events[0].type is RunEventType.USER_INPUT_ACCEPTED
    assert isinstance(first_message, SystemMessage)
    assert "第一轮问题" in first_message.content
    assert "第一轮最终回答" in first_message.content
    assert "financial_fact_lookup" in first_message.content
    assert "第二轮问题" not in first_message.content
    assert isinstance(second_messages[-1], UserMessage)
    assert second_messages[-1].content == "第二轮问题"
