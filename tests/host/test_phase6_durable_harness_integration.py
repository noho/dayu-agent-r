"""Host P6 LocalRunHarness durable 集成测试。

覆盖:

- ``build_durable_harness`` 注入 stub proxy 后,完整 ingress 路径(start_run
  -> EngineEvent stream -> append -> terminal -> coordinator.drain)能
  推进 attempt 终态、记录 RunResult 快照、刷新 read model。
- legacy 内存路径(``coordinator is None``)的 fallback 仍然走
  ``memory_store.project_run_events``。
- 终态后 attempt_state_store 中所有 attempt 应处于 SUCCEEDED 终态。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from dayu.contracts import CancellationToken
from dayu.engine import (
    AgentMessageRole,
    AgentPolicy,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    FinishReason,
    RunnerCallOptions,
    RunnerSpec,
    UserMessage,
)
from dayu.host._durable_harness import build_durable_harness
from dayu.host._internal_contracts import AttemptState, ObserverStatus
from dayu.host.contracts import (
    RunInput,
    RunOptions,
    RunSucceededResult,
    StartRunRequest,
)


def _utc() -> datetime:
    """返回当前 UTC 时间。

    :returns: 时区感知 UTC datetime。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


@dataclass(slots=True)
class _StubIterator:
    """预定义 EngineEvent 序列异步迭代器。"""

    events: tuple[EngineEvent, ...]
    index: int = 0

    def __aiter__(self) -> "_StubIterator":
        """返回自身。

        :returns: 自身。
        :raises Exception: 不主动抛出异常。
        """

        return self

    async def __anext__(self) -> EngineEvent:
        """逐个产出事件。

        :returns: 下一个 EngineEvent。
        :raises StopAsyncIteration: 序列耗尽。
        """

        if self.index >= len(self.events):
            raise StopAsyncIteration
        event = self.events[self.index]
        self.index += 1
        return event


@dataclass(frozen=True, slots=True)
class _StubProxy:
    """注入预定义 EngineEvent 序列的 stub WorkerProxy。"""

    events: tuple[EngineEvent, ...]

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回预定义事件流。

        :param request: start_run 请求。
        :param cancellation_token: 取消 token。
        :returns: 异步 EngineEvent 流。
        :raises Exception: 不主动抛出异常。
        """

        del request, cancellation_token
        return _StubIterator(events=self.events)


def _build_request(*, run_id: str, session_id: str) -> StartRunRequest:
    """构造最小 StartRunRequest。

    :param run_id: Run id。
    :param session_id: Session id。
    :returns: StartRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    return StartRunRequest(
        session_id=session_id,
        run_id=run_id,
        input=RunInput(
            messages=(
                UserMessage(role=AgentMessageRole.USER, content="hello"),
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


def _final_event(*, run_id: str, session_id: str) -> EngineEvent:
    """构造单一 FINAL_ANSWER EngineEvent。

    :param run_id: Run id。
    :param session_id: Session id。
    :returns: EngineEvent。
    :raises Exception: 不主动抛出异常。
    """

    return EngineEvent(
        event_id="engine_final",
        sequence=1,
        occurred_at=_utc(),
        session_id=session_id,
        run_id=run_id,
        type=EngineEventType.FINAL_ANSWER,
        data=FinalAnswerData(
            content="bye",
            filtered=False,
            degraded=False,
            finish_reason=FinishReason.STOP,
        ),
        metadata=None,
    )


async def _await_terminal(harness: object, run_id: str, *, timeout: float = 5.0) -> RunSucceededResult:
    """轮询等待 harness terminal RunResult 出现。

    :param harness: LocalRunHarness。
    :param run_id: Run id。
    :param timeout: 超时秒。
    :returns: RunSucceededResult。
    :raises RuntimeError: 超时未拿到结果时抛出。
    """

    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        result = await harness.get_run_result(run_id)  # type: ignore[attr-defined]
        if result is not None:
            assert isinstance(result, RunSucceededResult)
            return result
        await asyncio.sleep(0.02)
    raise RuntimeError("timed out waiting for terminal RunResult")


@pytest.mark.asyncio
async def test_durable_harness_start_run_drains_to_read_models() -> None:
    """build_durable_harness + start_run 完整路径应推进 read model 与 attempt 状态。"""

    bundle = build_durable_harness(
        database_path=":memory:",
        proxy=_StubProxy(
            events=(_final_event(run_id="r1", session_id="s1"),),
        ),
    )
    try:
        request = _build_request(run_id="r1", session_id="s1")
        await bundle.harness.start_run(request)
        await _await_terminal(bundle.harness, "r1")

        # attempt 终态写入。
        attempts = bundle.attempt_state_store.list_for_run("r1")
        assert len(attempts) == 1
        assert attempts[0].state is AttemptState.SUCCEEDED

        # observer checkpoint 已 caught_up。
        snapshots = await bundle.coordinator.drain()
        assert all(cp.status is ObserverStatus.CAUGHT_UP for cp in snapshots)

        memory = await bundle.memory_store.get_snapshot("s1")
        assert memory.recent_raw_turns
        assert memory.recent_raw_turns[-1].assistant_final == "bye"

        timeline = bundle.timeline_observer.get_timeline("r1")
        timeline_types = {evt.type.value for evt in timeline}
        assert "user_input_accepted" in timeline_types
        assert "final_answer" in timeline_types

        terminal = bundle.run_state_store.get_terminal_result("r1")
        assert isinstance(terminal, RunSucceededResult)
    finally:
        bundle.close()


@pytest.mark.asyncio
async def test_durable_harness_shares_memory_store_with_observer() -> None:
    """传入 memory_store 必须被 LocalRunHarness 与 MemoryProjectionObserver 共享。"""

    from dayu.host._conversation_memory import InMemoryConversationMemoryStore

    shared = InMemoryConversationMemoryStore()
    bundle = build_durable_harness(
        database_path=":memory:",
        memory_store=shared,
        proxy=_StubProxy(
            events=(_final_event(run_id="r2", session_id="s2"),),
        ),
    )
    try:
        # 装配后 bundle 引用与 LocalRunHarness 引用应相同。
        assert bundle.memory_store is shared
        assert bundle.harness.memory_store is shared
        request = _build_request(run_id="r2", session_id="s2")
        await bundle.harness.start_run(request)
        await _await_terminal(bundle.harness, "r2")

        # observer drain 后 shared snapshot 必须被填充(无 split-brain)。
        memory = await shared.get_snapshot("s2")
        assert memory.recent_raw_turns
        assert memory.recent_raw_turns[-1].assistant_final == "bye"
    finally:
        bundle.close()
