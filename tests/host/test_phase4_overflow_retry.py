"""Host P4 context overflow retry 测试。"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

import pytest

from dayu.contracts import CancellationToken
from dayu.contracts.tool_outcome import ToolCompletedOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.engine import (
    AgentMessageRole,
    AgentPolicy,
    AssistantMessage,
    SystemMessage,
    ContextBudgetSnapshot,
    ContextCompactionRequestedData,
    EngineEvent,
    EngineEventData,
    EngineEventType,
    FinalAnswerData,
    FinishReason,
    RunFailedData,
    RunnerCallOptions,
    RunnerSpec,
    ToolMessage,
    ToolResultAcceptedData,
    UserMessage,
)
from dayu.host._attempt_lease import (
    AttemptFencingError,
    AttemptFencingReason,
    AttemptOwnerContext,
    AttemptTerminalLink,
)
from dayu.host._attempt_supervisor import AttemptSupervisor
from dayu.host._conversation_memory import (
    AssumptionRegister,
    ConversationMemoryPatch,
    ConversationMemorySnapshot,
    ConversationMemoryStore,
    ConversationPinnedState,
    ConversationRawTurn,
    MemoryIngestionPolicy,
    MemoryProducerKind,
    MemoryProvenance,
    MemoryScope,
    MemoryTrustLevel,
    TaskFrame,
    UserPreferenceProfileRef,
)
from dayu.host._durable_event_store import DurableRunEventStore
from dayu.host._durable_harness import (
    DurableHarnessConfig,
    build_durable_harness,
)
from dayu.host._event_store import InMemoryRunEventStore, RunEventStore
from dayu.host._internal_contracts import AttemptState
from dayu.host._run_harness import LocalRunHarness
from dayu.host.contracts import (
    TERMINAL_RUN_EVENT_TYPES,
    ContextCompactFailureReason,
    HostContextCompactCompletedData,
    HostContextCompactFailedData,
    HostContextAttemptRetryData,
    HostRunFailedData,
    RunEvent,
    RunEventCursor,
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
    HostContextOverflowObservedData,
    RunFailedResult,
    RunInput,
    RunOptions,
    RunSucceededResult,
    StartRunRequest,
)
from tests.host._memory_store_fake import FakeInMemoryConversationMemoryStore


def _utc_now() -> datetime:
    """返回测试用 UTC 当前时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


@dataclass(slots=True)
class _SnapshotMemoryStore:
    """固定返回 snapshot 的测试 memory store。"""

    snapshot: ConversationMemorySnapshot
    projected: list[tuple[RunEvent, ...]] = field(default_factory=list)

    async def project_run_events(self, events: tuple[RunEvent, ...]) -> None:
        """记录投影事件。

        :param events: 同一 run 的 RunEvent 元组。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.projected.append(events)

    async def get_snapshot(self, session_id: str) -> ConversationMemorySnapshot:
        """读取固定 snapshot。

        :param session_id: 会话 id。
        :returns: 固定 memory snapshot。
        :raises Exception: 不主动抛出异常。
        """

        return self.snapshot

    async def apply_patch(self, patch: ConversationMemoryPatch) -> None:
        """测试 store 不支持 patch。

        :param patch: memory patch。
        :returns: 无返回值。
        :raises NotImplementedError: 始终抛出。
        """

        raise NotImplementedError(type(patch).__name__)


@dataclass(slots=True)
class _OverflowThenSuccessProxy:
    """第一次 attempt overflow，第二次 attempt 成功的 fake proxy。"""

    requests: list[StartRunRequest] = field(default_factory=list)
    final_content: str = "已基于证据回答。"

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

        self.requests.append(request)
        if len(self.requests) == 1:
            return _iter_events(
                (
                    _engine_event(
                        sequence=0,
                        event_type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
                        data=ContextCompactionRequestedData(
                            iteration_id="iter-0",
                            budget_state=ContextBudgetSnapshot(
                                prompt_tokens=0,
                                completion_tokens=0,
                                total_tokens=0,
                            ),
                            reason="context_compaction_required",
                        ),
                    ),
                    _engine_event(
                        sequence=1,
                        event_type=EngineEventType.RUN_FAILED,
                        data=RunFailedData(
                            error_code="context_compaction_required",
                            message="provider context overflow",
                            recoverable=True,
                        ),
                    ),
                )
            )
        return _iter_events(
            (
                _engine_event(
                    sequence=2,
                    event_type=EngineEventType.FINAL_ANSWER,
                    data=FinalAnswerData(
                        content=self.final_content,
                        filtered=False,
                        degraded=False,
                        finish_reason=FinishReason.STOP,
                    ),
                ),
            )
        )


@dataclass(slots=True)
class _CompactionRequestedThenFinalProxy:
    """Engine 先请求 compact，随后意外给出成功终态的 fake proxy。"""

    requests: list[StartRunRequest] = field(default_factory=list)

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回异常闭合的 EngineEvent 流。

        :param request: Host start_run 请求。
        :param cancellation_token: Host 注入的取消 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        self.requests.append(request)
        return _iter_events(
            (
                _engine_event(
                    sequence=0,
                    event_type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
                    data=ContextCompactionRequestedData(
                        iteration_id="iter-0",
                        budget_state=ContextBudgetSnapshot(
                            prompt_tokens=0,
                            completion_tokens=0,
                            total_tokens=0,
                        ),
                        reason="context_compaction_required",
                    ),
                ),
                _engine_event(
                    sequence=1,
                    event_type=EngineEventType.FINAL_ANSWER,
                    data=FinalAnswerData(
                        content="最终回答仍然到达。",
                        filtered=False,
                        degraded=False,
                        finish_reason=FinishReason.STOP,
                    ),
                ),
            )
        )


@dataclass(slots=True)
class _CompactionRequestedThenEndedProxy:
    """第一次 attempt 只请求 compact 后结束，第二次 attempt 成功。"""

    requests: list[StartRunRequest] = field(default_factory=list)

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回缺少 terminal overflow 的 EngineEvent 流。

        :param request: Host start_run 请求。
        :param cancellation_token: Host 注入的取消 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        self.requests.append(request)
        if len(self.requests) == 1:
            return _iter_events(
                (
                    _engine_event(
                        sequence=0,
                        event_type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
                        data=ContextCompactionRequestedData(
                            iteration_id="iter-0",
                            budget_state=ContextBudgetSnapshot(
                                prompt_tokens=0,
                                completion_tokens=0,
                                total_tokens=0,
                            ),
                            reason="context_compaction_required",
                        ),
                    ),
                )
            )
        return _iter_events(
            (
                _engine_event(
                    sequence=1,
                    event_type=EngineEventType.FINAL_ANSWER,
                    data=FinalAnswerData(
                        content="缺少 terminal 后仍已 compact retry。",
                        filtered=False,
                        degraded=False,
                        finish_reason=FinishReason.STOP,
                    ),
                ),
            )
        )


@dataclass(slots=True)
class _ToolFactThenOverflowProxy:
    """第一次 attempt 先落工具事实再 overflow，第二次 attempt 成功。"""

    event_store: RunEventStore
    requests: list[StartRunRequest] = field(default_factory=list)

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """返回带同 Run 工具事实的脚本化 EngineEvent 流。

        :param request: Host start_run 请求。
        :param cancellation_token: Host 注入的取消 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        self.requests.append(request)
        if len(self.requests) == 1:
            return self._first_attempt(request)
        return _iter_events(
            (
                _engine_event_for_request(
                    request=request,
                    sequence=3,
                    event_type=EngineEventType.FINAL_ANSWER,
                    data=FinalAnswerData(
                        content="已基于当前工具证据回答。",
                        filtered=False,
                        degraded=False,
                        finish_reason=FinishReason.STOP,
                    ),
                ),
            )
        )

    async def _first_attempt(
        self,
        request: StartRunRequest,
    ) -> AsyncIterator[EngineEvent]:
        """产出工具结果、追加截断事实，然后触发 overflow。

        :param request: Host start_run 请求。
        :returns: EngineEvent 异步流。
        :raises Exception: append 测试事件失败时透传。
        """

        yield _engine_event_for_request(
            request=request,
            sequence=0,
            event_type=EngineEventType.TOOL_RESULT_ACCEPTED,
            data=ToolResultAcceptedData(
                iteration_id="iter-0",
                tool_call_id="call-current",
                name="fins.lookup",
                index_in_iteration=0,
                outcome=ToolCompletedOutcome(
                    result=ToolResultSuccess(
                        ok=True,
                        value={"revenue_growth": "12%"},
                        truncation=None,
                        meta=None,
                    )
                ),
            ),
        )
        await self.event_store.append(
            _tool_truncated_draft(
                run_id=request.run_id,
                session_id=request.session_id,
            )
        )
        yield _engine_event_for_request(
            request=request,
            sequence=1,
            event_type=EngineEventType.CONTEXT_COMPACTION_REQUESTED,
            data=ContextCompactionRequestedData(
                iteration_id="iter-0",
                budget_state=ContextBudgetSnapshot(
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                ),
                reason="context_compaction_required",
            ),
        )
        yield _engine_event_for_request(
            request=request,
            sequence=2,
            event_type=EngineEventType.RUN_FAILED,
            data=RunFailedData(
                error_code="context_compaction_required",
                message="provider context overflow",
                recoverable=True,
            ),
        )


@dataclass(slots=True)
class _DelayedOverflowProxy:
    """按 gate 延迟 run-evicted 的 overflow，便于测试 trace 淘汰。"""

    gate: asyncio.Event

    def stream_engine_events(
        self,
        request: StartRunRequest,
        cancellation_token: CancellationToken,
    ) -> AsyncIterator[EngineEvent]:
        """按 run id 返回延迟 overflow 或直接成功。

        :param request: Host start_run 请求。
        :param cancellation_token: Host 注入的取消 token。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        if request.run_id == "run-evicted":
            return self._delayed_overflow(request)
        return _iter_events(
            (
                _engine_event_for_request(
                    request=request,
                    sequence=0,
                    event_type=EngineEventType.FINAL_ANSWER,
                    data=FinalAnswerData(
                        content="第二个 run 成功。",
                        filtered=False,
                        degraded=False,
                        finish_reason=FinishReason.STOP,
                    ),
                ),
            )
        )

    async def _delayed_overflow(
        self,
        request: StartRunRequest,
    ) -> AsyncIterator[EngineEvent]:
        """等待 gate 后产出 overflow。

        :param request: Host start_run 请求。
        :returns: EngineEvent 异步流。
        :raises Exception: 不主动抛出异常。
        """

        await self.gate.wait()
        yield _engine_event_for_request(
            request=request,
            sequence=0,
            event_type=EngineEventType.RUN_FAILED,
            data=RunFailedData(
                error_code="context_compaction_required",
                message="provider context overflow",
                recoverable=True,
            ),
        )


def _snapshot() -> ConversationMemorySnapshot:
    """构造能被 compact 明显压短的 snapshot。

    :returns: ConversationMemorySnapshot。
    :raises Exception: 不主动抛出异常。
    """

    provenance = MemoryProvenance(
        source_run_id="run-old",
        source_event_cursor=RunEventCursor(sequence=1),
        producer_kind=MemoryProducerKind.HOST_USER_INPUT,
        ingestion_policy=MemoryIngestionPolicy.PRIMARY_SESSION_CANONICAL,
        scope=MemoryScope.SESSION,
        trust_level=MemoryTrustLevel.USER_PROVIDED,
    )
    raw_turn = ConversationRawTurn(
        turn_id="turn-old",
        user_text="旧问题" * 500,
        assistant_final="旧回答" * 500,
        user_provenance=provenance,
        assistant_provenance=provenance,
    )
    return ConversationMemorySnapshot(
        session_id="session-p4",
        pinned_state=ConversationPinnedState(current_goal="分析财报"),
        task_frame=TaskFrame(),
        verified_claims=(),
        assumptions=AssumptionRegister(),
        evidence_anchors=(),
        recent_raw_turns=(raw_turn,),
        older_raw_turns=(),
        tool_facts=(),
        user_preference_ref=UserPreferenceProfileRef(),
    )


def _large_snapshot() -> ConversationMemorySnapshot:
    """构造能容纳同 Run 工具事实且仍明显压短的 snapshot。

    :returns: ConversationMemorySnapshot。
    :raises Exception: 不主动抛出异常。
    """

    snapshot = _snapshot()
    if not snapshot.recent_raw_turns:
        return snapshot
    base_turn = snapshot.recent_raw_turns[0]
    turns = tuple(
        replace(
            base_turn,
            turn_id=f"turn-old-{index}",
            user_text=f"旧问题{index}" * 500,
            assistant_final=f"旧回答{index}" * 500,
        )
        for index in range(8)
    )
    return replace(snapshot, recent_raw_turns=turns)


def _request(
    *,
    run_id: str = "run-p4",
    messages: tuple[SystemMessage | UserMessage | AssistantMessage | ToolMessage, ...] = (
        UserMessage(
            role=AgentMessageRole.USER,
            content="请继续分析 A 公司。",
        ),
    ),
) -> StartRunRequest:
    """构造 Host StartRunRequest。

    :param run_id: Run id。
    :param messages: 入口消息。
    :returns: StartRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    return StartRunRequest(
        session_id="session-p4",
        run_id=run_id,
        input=RunInput(
            messages=messages
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


def _engine_event(
    *,
    sequence: int,
    event_type: EngineEventType,
    data: EngineEventData,
) -> EngineEvent:
    """构造 EngineEvent。

    :param sequence: Engine event sequence。
    :param event_type: Engine event type。
    :param data: Engine event data。
    :returns: EngineEvent。
    :raises Exception: 不主动抛出异常。
    """

    return EngineEvent(
        event_id=f"engine-{sequence}",
        sequence=sequence,
        occurred_at=_utc_now(),
        session_id="session-p4",
        run_id="run-p4",
        type=event_type,
        data=data,
        metadata=None,
    )


def _engine_event_for_request(
    *,
    request: StartRunRequest,
    sequence: int,
    event_type: EngineEventType,
    data: EngineEventData,
) -> EngineEvent:
    """按请求构造 EngineEvent。

    :param request: Host start_run 请求。
    :param sequence: Engine event sequence。
    :param event_type: Engine event type。
    :param data: Engine event data。
    :returns: EngineEvent。
    :raises Exception: 不主动抛出异常。
    """

    return EngineEvent(
        event_id=f"{request.run_id}-engine-{sequence}",
        sequence=sequence,
        occurred_at=_utc_now(),
        session_id=request.session_id,
        run_id=request.run_id,
        type=event_type,
        data=data,
        metadata=None,
    )


def _tool_truncated_draft(
    *,
    run_id: str,
    session_id: str,
) -> RunEventDraft:
    """构造测试用普通工具结果事实。

    :param run_id: Run id。
    :param session_id: Session id。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id=session_id,
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.ENGINE,
        type=RunEventType.TOOL_RESULT_ACCEPTED,
        occurred_at=_utc_now(),
        data=ToolResultAcceptedData(
            iteration_id="iter-0",
            tool_call_id="call-current",
            name="fins.lookup",
            index_in_iteration=0,
            outcome=ToolCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value={"summary": "收入同比增长 12%"},
                    truncation=None,
                    meta=None,
                )
            ),
        ),
        source_engine_event_id="engine-tool-current",
    )


async def _iter_events(
    events: tuple[EngineEvent, ...],
) -> AsyncIterator[EngineEvent]:
    """按顺序产出 EngineEvent。

    :param events: EngineEvent 元组。
    :returns: EngineEvent 异步迭代器。
    :raises Exception: 不主动抛出异常。
    """

    for event in events:
        yield event


async def _collect(stream: AsyncIterator[RunEvent]) -> tuple[RunEvent, ...]:
    """收集 RunEvent 流。

    :param stream: RunEvent 异步流。
    :returns: RunEvent 元组。
    :raises Exception: 透传迭代异常。
    """

    events: list[RunEvent] = []
    async for event in stream:
        events.append(event)
    return tuple(events)


@pytest.mark.asyncio
async def test_overflow_compacts_and_retries_same_run_without_new_user_input() -> None:
    """overflow 后 Host compact 并在同一 Run 下启动 internal attempt。"""

    proxy = _OverflowThenSuccessProxy()
    memory_store: ConversationMemoryStore = _SnapshotMemoryStore(_large_snapshot())
    harness = LocalRunHarness(is_durable=False, proxy=proxy, memory_store=memory_store)

    stream = await harness.start_run(_request())
    events = await _collect(stream.events)
    result = await harness.get_run_result("run-p4")

    assert isinstance(result, RunSucceededResult)
    assert result.content == "已基于证据回答。"
    assert len(proxy.requests) == 2
    assert proxy.requests[0].input.messages != proxy.requests[1].input.messages
    assert [event.type for event in events].count(
        RunEventType.USER_INPUT_ACCEPTED
    ) == 1
    assert any(
        isinstance(event.data, HostContextCompactCompletedData)
        for event in events
    )
    assert any(
        isinstance(event.data, HostContextAttemptRetryData)
        for event in events
    )


@pytest.mark.asyncio
async def test_overflow_retry_limit_fails_host_owned_terminal() -> None:
    """超过 compact retry 上限后由 Host-owned RUN_FAILED 收口。"""

    proxy = _OverflowThenSuccessProxy()
    memory_store: ConversationMemoryStore = _SnapshotMemoryStore(_large_snapshot())
    harness = LocalRunHarness(
        is_durable=False,
        proxy=proxy,
        memory_store=memory_store,
        context_compact_retry_limit=0,
    )

    stream = await harness.start_run(_request())
    events = await _collect(stream.events)
    result = await harness.get_run_result("run-p4")

    assert isinstance(result, RunFailedResult)
    assert result.error_code == "host_context_compact_failed"
    assert any(
        isinstance(event.data, HostContextCompactFailedData)
        for event in events
    )
    assert [event.type for event in events].count(
        RunEventType.USER_INPUT_ACCEPTED
    ) == 1


def test_negative_context_compact_retry_limit_is_rejected() -> None:
    """负数 compact retry 上限必须在 harness 装配时 fail fast。"""

    proxy = _OverflowThenSuccessProxy()

    with pytest.raises(
        ValueError,
        match="context_compact_retry_limit_must_be_non_negative",
    ):
        LocalRunHarness(
            is_durable=False,
            proxy=proxy,
            context_compact_retry_limit=-1,
            memory_store=FakeInMemoryConversationMemoryStore(),
        )


@pytest.mark.asyncio
async def test_compaction_requested_then_stream_end_observes_overflow() -> None:
    """非 terminal compact 触发路径也要追加 Host overflow observed 事实。"""

    proxy = _CompactionRequestedThenEndedProxy()
    memory_store: ConversationMemoryStore = _SnapshotMemoryStore(_large_snapshot())
    harness = LocalRunHarness(is_durable=False, proxy=proxy, memory_store=memory_store)

    stream = await harness.start_run(_request())
    events = await _collect(stream.events)
    result = await harness.get_run_result("run-p4")

    assert isinstance(result, RunSucceededResult)
    assert result.content == "缺少 terminal 后仍已 compact retry。"
    assert len(proxy.requests) == 2
    observed_events = tuple(
        event
        for event in events
        if isinstance(event.data, HostContextOverflowObservedData)
    )
    assert len(observed_events) == 1
    observed_data = observed_events[0].data
    assert isinstance(observed_data, HostContextOverflowObservedData)
    assert observed_data.engine_event_type == (
        EngineEventType.CONTEXT_COMPACTION_REQUESTED.value
    )
    assert observed_data.engine_error_code is None
    assert observed_data.recoverable is True
    assert observed_data.reason == "context_compaction_required"


@pytest.mark.asyncio
async def test_compaction_requested_then_final_answer_closes_sequence() -> None:
    """Engine 请求 compact 后意外成功时，Host 先追加 compact_failed 闭合事实。"""

    proxy = _CompactionRequestedThenFinalProxy()
    harness = LocalRunHarness(
        is_durable=False,
        proxy=proxy, memory_store=FakeInMemoryConversationMemoryStore()
    )

    stream = await harness.start_run(_request())
    events = await _collect(stream.events)
    result = await harness.get_run_result("run-p4")

    assert isinstance(result, RunSucceededResult)
    assert result.content == "最终回答仍然到达。"
    assert any(
        isinstance(event.data, HostContextCompactFailedData)
        and event.data.reason is ContextCompactFailureReason.INTERNAL_ERROR
        for event in events
    )
    assert events[-1].type is RunEventType.FINAL_ANSWER
    assert len(proxy.requests) == 1


@pytest.mark.asyncio
async def test_same_run_tool_facts_enter_compacted_attempt() -> None:
    """同一 Run overflow 前已落库工具事实必须进入 compacted attempt。"""

    event_store = InMemoryRunEventStore()
    proxy = _ToolFactThenOverflowProxy(event_store=event_store)
    memory_store: ConversationMemoryStore = _SnapshotMemoryStore(_large_snapshot())
    harness = LocalRunHarness(
        is_durable=False,
        proxy=proxy,
        event_store=event_store,
        memory_store=memory_store,
    )

    stream = await harness.start_run(_request())
    await _collect(stream.events)

    assert len(proxy.requests) == 2
    compact_text = "\n".join(
        message.content
        for message in proxy.requests[1].input.messages
        if isinstance(message, SystemMessage)
    )
    assert "tool_call_id=call-current" in compact_text
    assert "source_event_cursor=2" in compact_text
    assert "cursor_fingerprint=None" in compact_text
    assert "has_more=None" in compact_text


@pytest.mark.asyncio
async def test_missing_trace_cache_compact_failure_gets_host_terminal() -> None:
    """trace 缓存淘汰后 compact 失败必须有 Host-owned failed terminal。"""

    gate = asyncio.Event()
    proxy = _DelayedOverflowProxy(gate=gate)
    memory_store: ConversationMemoryStore = _SnapshotMemoryStore(_snapshot())
    harness = LocalRunHarness(
        is_durable=False,
        proxy=proxy,
        memory_store=memory_store,
        run_input_trace_cache_limit=1,
    )

    first_stream = await harness.start_run(_request(run_id="run-evicted"))
    second_stream = await harness.start_run(_request(run_id="run-newer"))
    await _collect(second_stream.events)
    gate.set()
    first_events = await _collect(first_stream.events)
    result = await harness.get_run_result("run-evicted")

    assert isinstance(result, RunFailedResult)
    assert result.error_code == "host_context_compact_failed"
    assert any(
        isinstance(event.data, HostContextCompactFailedData)
        and event.data.reason.value == "trace_missing"
        for event in first_events
    )


@pytest.mark.asyncio
async def test_internal_final_answer_echo_is_filtered_result() -> None:
    """Engine final answer 回显 Host 内部字段时 Host 返回 filtered/degraded。"""

    proxy = _OverflowThenSuccessProxy(
        final_content=(
            "## Host Memory\n## Tool Facts\n"
            "tool_fact_id=tool_fact:run:1; "
            "cursor_fingerprint=fp; source_event_cursor=1"
        )
    )
    memory_store: ConversationMemoryStore = _SnapshotMemoryStore(_snapshot())
    harness = LocalRunHarness(is_durable=False, proxy=proxy, memory_store=memory_store)

    stream = await harness.start_run(_request())
    await _collect(stream.events)
    result = await harness.get_run_result("run-p4")

    assert isinstance(result, RunSucceededResult)
    assert result.filtered is True
    assert result.degraded is True
    assert "Host Memory" not in result.content
    assert "tool_fact_id" not in result.content


@pytest.mark.asyncio
async def test_natural_final_answer_with_tool_facts_words_is_not_filtered() -> None:
    """普通自然语言提到 tool facts 字样时不触发 Host 内部回显过滤。"""

    proxy = _OverflowThenSuccessProxy(
        final_content="The tool facts discussed above support the conclusion."
    )
    memory_store: ConversationMemoryStore = _SnapshotMemoryStore(_snapshot())
    harness = LocalRunHarness(is_durable=False, proxy=proxy, memory_store=memory_store)

    stream = await harness.start_run(_request())
    await _collect(stream.events)
    result = await harness.get_run_result("run-p4")

    assert isinstance(result, RunSucceededResult)
    assert result.filtered is False
    assert result.degraded is False
    assert result.content == (
        "The tool facts discussed above support the conclusion."
    )


@pytest.mark.asyncio
async def test_caller_system_prompts_precede_host_memory_and_user() -> None:
    """入口支持多条 caller system，且 Host Memory 位于其后。"""

    proxy = _OverflowThenSuccessProxy()
    memory_store: ConversationMemoryStore = _SnapshotMemoryStore(_snapshot())
    harness = LocalRunHarness(is_durable=False, proxy=proxy, memory_store=memory_store)
    request = _request(
        messages=(
            SystemMessage(
                role=AgentMessageRole.SYSTEM,
                content="caller system 1",
            ),
            SystemMessage(
                role=AgentMessageRole.SYSTEM,
                content="caller system 2",
            ),
            UserMessage(
                role=AgentMessageRole.USER,
                content="请继续分析 A 公司。",
            ),
        )
    )

    stream = await harness.start_run(request)
    await _collect(stream.events)

    first_messages = proxy.requests[0].input.messages
    second_messages = proxy.requests[1].input.messages
    assert [message.content for message in first_messages[:2]] == [
        "caller system 1",
        "caller system 2",
    ]
    assert isinstance(first_messages[2], SystemMessage)
    assert first_messages[2].content.startswith("## Host Memory")
    assert isinstance(first_messages[-1], UserMessage)
    assert [message.content for message in second_messages[:2]] == [
        "caller system 1",
        "caller system 2",
    ]
    assert isinstance(second_messages[2], SystemMessage)
    assert second_messages[2].content.startswith("## Host Compact Memory")
    assert isinstance(second_messages[-1], UserMessage)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("messages", "expected_error"),
    (
        (
            (
                UserMessage(role=AgentMessageRole.USER, content="问题一"),
                UserMessage(role=AgentMessageRole.USER, content="问题二"),
            ),
            "start_run_input_allows_only_one_trailing_current_user_message",
        ),
        (
            (
                UserMessage(role=AgentMessageRole.USER, content="问题"),
                SystemMessage(
                    role=AgentMessageRole.SYSTEM,
                    content="late system",
                ),
            ),
            "start_run_input_must_end_with_single_current_user_message",
        ),
        (
            (
                AssistantMessage(
                    role=AgentMessageRole.ASSISTANT,
                    content="history",
                    reasoning_content=None,
                    tool_calls=(),
                ),
                UserMessage(role=AgentMessageRole.USER, content="问题"),
            ),
            "start_run_input_allows_only_leading_system_messages_before_current_user",
        ),
        (
            (
                ToolMessage(
                    role=AgentMessageRole.TOOL,
                    tool_call_id="call-1",
                    content="tool history",
                ),
                UserMessage(role=AgentMessageRole.USER, content="问题"),
            ),
            "start_run_input_allows_only_leading_system_messages_before_current_user",
        ),
        (
            (
                SystemMessage(role=AgentMessageRole.SYSTEM, content="system"),
                UserMessage(role=AgentMessageRole.USER, content="   "),
            ),
            "current_user_input_required",
        ),
    ),
)
async def test_start_run_rejects_non_current_user_shapes(
    messages: tuple[
        SystemMessage | UserMessage | AssistantMessage | ToolMessage,
        ...,
    ],
    expected_error: str,
) -> None:
    """入口仍拒绝历史、tool/assistant、多个 user 与空 user。"""

    proxy = _OverflowThenSuccessProxy()
    harness = LocalRunHarness(is_durable=False, proxy=proxy, memory_store=FakeInMemoryConversationMemoryStore())

    with pytest.raises(ValueError, match=expected_error):
        await harness.start_run(_request(messages=messages))


@pytest.mark.asyncio
async def test_durable_overflow_retry_acquire_failure_writes_owner_scoped_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F5 root cause: durable 路径下 retry 新 attempt acquire 失败必须 owner-scoped terminal 收口。

    构造 durable harness + ``AttemptSupervisor`` + 真实
    ``DurableRunEventStore``, 触发一次 context overflow compact, 然后
    monkeypatch 让第二次 ``AttemptSupervisor.lease_context`` (即新
    attempt acquire) 抛 :class:`AttemptFencingError`, 验证:

    1. EventLog 中存在 Host-owned ``RUN_FAILED`` terminal RunEvent
       (``error_code=context_overflow_retry_acquire_failed``);
    2. 旧 attempt 的 ``terminal_event_position`` 已被 supervisor 在同一
       事务内写入(证明走 owner-scoped 原子终态路径,
       :class:`AttemptSupervisor.append_terminal_and_close`), 不是裸
       ``event_store.append`` (后者无法回填 ``terminal_event_position``);
    3. 旧 attempt 不残留 ``STALE`` 收口, 而是终态 ``FAILED``;
    4. 没有第二个 attempt 残留 (acquire 失败前 supervisor 没有写入新
       ``host_attempts`` 行);
    5. RunStream 订阅方收到该 terminal RunEvent 并自然结束;
    6. ``get_run_result`` 返回 :class:`RunFailedResult`。
    """

    proxy = _OverflowThenSuccessProxy()
    bundle = build_durable_harness(
        config=DurableHarnessConfig(database_path=":memory:"),
        proxy=proxy,
    )
    try:
        original_lease_context = AttemptSupervisor.lease_context
        call_count = {"n": 0}

        @asynccontextmanager
        async def _patched_lease_context(
            self: AttemptSupervisor,
            *,
            run_id: str,
            attempt_index: int,
            recovered_from_attempt_id: str | None = None,
        ) -> AsyncGenerator[AttemptOwnerContext, None]:
            call_count["n"] += 1
            if call_count["n"] >= 2:
                raise AttemptFencingError(
                    attempt_id=f"attempt-{run_id}-{attempt_index}",
                    run_id=run_id,
                    reason=AttemptFencingReason.STORAGE_CONFLICT,
                    current_state=None,
                    owner_id=None,
                    fencing_token=None,
                )
            async with original_lease_context(
                self,
                run_id=run_id,
                attempt_index=attempt_index,
                recovered_from_attempt_id=recovered_from_attempt_id,
            ) as owner_context:
                yield owner_context

        monkeypatch.setattr(
            AttemptSupervisor,
            "lease_context",
            _patched_lease_context,
        )

        # 旁路验证: 监控 ``DurableRunEventStore.append`` 是否被裸调用
        # 写入 terminal RunEvent。owner-scoped 路径下的 terminal append
        # 经由 supervisor 在事务内写, **不**走该 public ``append`` 方法。
        original_append = DurableRunEventStore.append
        bare_terminal_append_calls: list[str] = []

        async def _spy_append(
            self: DurableRunEventStore,
            draft: RunEventDraft,
        ) -> RunEvent:
            if draft.type is RunEventType.RUN_FAILED:
                bare_terminal_append_calls.append(draft.run_id)
            return await original_append(self, draft)

        monkeypatch.setattr(
            DurableRunEventStore,
            "append",
            _spy_append,
        )

        projected = asyncio.Event()
        original_project_terminal_run = LocalRunHarness._project_terminal_run

        async def _patched_project_terminal_run(
            self: LocalRunHarness,
            run_id: str,
        ) -> None:
            try:
                await original_project_terminal_run(self, run_id)
            finally:
                projected.set()

        monkeypatch.setattr(
            LocalRunHarness,
            "_project_terminal_run",
            _patched_project_terminal_run,
        )

        request = _request()
        stream = await bundle.harness.start_run(request)

        events = await asyncio.wait_for(
            _collect(stream.events), timeout=5.0
        )
        await asyncio.wait_for(projected.wait(), timeout=5.0)

        # (1) RunStream 收到 terminal event。
        terminal_events = [
            event
            for event in events
            if event.type is RunEventType.RUN_FAILED
            and isinstance(event.data, HostRunFailedData)
            and event.data.error_code
            == "context_overflow_retry_acquire_failed"
        ]
        assert len(terminal_events) == 1, (
            f"expect single overflow-retry-acquire-failed terminal, "
            f"got types={[e.type for e in events]}"
        )

        # (2) 旧 attempt 终态 FAILED 且 terminal_event_position 已被
        # supervisor 在事务内写入 (owner-scoped 原子路径独有特征)。
        attempts = bundle.attempt_state_store.list_for_run(request.run_id)
        assert len(attempts) == 1, (
            f"acquire 失败前 supervisor 不应写入第二个 host_attempts 行, "
            f"实际 attempts={attempts}"
        )
        old_attempt = attempts[0]
        assert old_attempt.state is AttemptState.FAILED
        assert old_attempt.terminal_event_position is not None, (
            "owner-scoped append_terminal_and_close 必须在同事务内回填 "
            "terminal_event_position; None 说明走了裸 event_store.append"
        )

        # (3) DurableRunEventStore.append 未被用于写 terminal RunEvent
        # (owner-scoped 路径不经过该 public 方法)。
        assert bare_terminal_append_calls == [], (
            f"terminal RunEvent 必须由 supervisor 在事务内 append, 不能"
            f"经由裸 event_store.append; 命中: {bare_terminal_append_calls}"
        )

        # (4) get_run_result 推导出 RunFailedResult。
        result = await bundle.harness.get_run_result(request.run_id)
        assert isinstance(result, RunFailedResult)

        # (5) compact 已成功完成 (CONTEXT_COMPACT_COMPLETED 已 append),
        # 即异常发生在 compact 之后、retry 边界之内。
        assert any(
            isinstance(event.data, HostContextCompactCompletedData)
            for event in events
        )
    finally:
        bundle.close()


@pytest.mark.asyncio
async def test_durable_overflow_acquire_failure_terminal_fencing_routes_owner_lost(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """N1: compact diagnostic 已成功，但旧 owner terminal close 被 fence。

    该场景证明 compact success diagnostic 可先落库；随后 terminal close
    CAS miss 时不得补写 stale Host terminal，Run 终态仍只能来自唯一
    terminal truth。

    :param monkeypatch: pytest monkeypatch fixture。
    :param caplog: pytest 日志捕获 fixture。
    :returns: 无返回值。
    :raises AssertionError: 断言不满足时由 pytest 抛出。
    """

    proxy = _OverflowThenSuccessProxy()
    bundle = build_durable_harness(
        config=DurableHarnessConfig(database_path=":memory:"),
        proxy=proxy,
    )
    try:
        original_lease_context = AttemptSupervisor.lease_context
        lease_context_call_count = 0

        @asynccontextmanager
        async def _patched_lease_context(
            self: AttemptSupervisor,
            *,
            run_id: str,
            attempt_index: int,
            recovered_from_attempt_id: str | None = None,
        ) -> AsyncGenerator[AttemptOwnerContext, None]:
            """第一次 acquire 成功，第二次 acquire 模拟 fencing 失败。

            :param self: 被 monkeypatch 的 supervisor。
            :param run_id: Run id。
            :param attempt_index: attempt 序号。
            :param recovered_from_attempt_id: 恢复来源 attempt id。
            :returns: 异步 owner context generator。
            :raises AttemptFencingError: 第二次 acquire 时主动抛出。
            """

            nonlocal lease_context_call_count

            lease_context_call_count += 1
            if lease_context_call_count >= 2:
                raise AttemptFencingError(
                    attempt_id=f"attempt-{run_id}-{attempt_index}",
                    run_id=run_id,
                    reason=AttemptFencingReason.STORAGE_CONFLICT,
                    current_state=None,
                    owner_id=None,
                    fencing_token=None,
                )
            async with original_lease_context(
                self,
                run_id=run_id,
                attempt_index=attempt_index,
                recovered_from_attempt_id=recovered_from_attempt_id,
            ) as owner_context:
                yield owner_context

        terminal_close_attempts: list[str] = []

        async def _patched_append_terminal_and_close(
            self: AttemptSupervisor,
            *,
            owner_context: AttemptOwnerContext,
            draft: RunEventDraft,
            failure_summary: str | None = None,
            terminal_state_override: AttemptState | None = None,
        ) -> AttemptTerminalLink:
            """模拟旧 owner terminal close 发生 CAS miss。

            :param self: 被 monkeypatch 的 supervisor。
            :param owner_context: 旧 attempt owner context。
            :param draft: terminal RunEvent 草稿。
            :param failure_summary: attempt failure summary。
            :param terminal_state_override: terminal state 覆盖值。
            :returns: 不返回；本 helper 总是抛出。
            :raises AttemptFencingError: 始终模拟 fencing token 不匹配。
            """

            _ = (self, draft, failure_summary, terminal_state_override)
            terminal_close_attempts.append(owner_context.attempt_id)
            raise AttemptFencingError(
                attempt_id=owner_context.attempt_id,
                run_id=owner_context.run_id,
                reason=AttemptFencingReason.FENCING_TOKEN_MISMATCH,
                current_state=AttemptState.RUNNING,
                owner_id=owner_context.owner_id,
                fencing_token=owner_context.fencing_token,
            )

        monkeypatch.setattr(
            AttemptSupervisor,
            "lease_context",
            _patched_lease_context,
        )
        monkeypatch.setattr(
            AttemptSupervisor,
            "append_terminal_and_close",
            _patched_append_terminal_and_close,
        )

        original_append = DurableRunEventStore.append
        bare_terminal_append_calls: list[str] = []

        async def _spy_append(
            self: DurableRunEventStore,
            draft: RunEventDraft,
        ) -> RunEvent:
            """记录是否存在 public append 直写 terminal。

            :param self: DurableRunEventStore 实例。
            :param draft: RunEvent 草稿。
            :returns: 落库后的 RunEvent。
            :raises Exception: 透传原 append 异常。
            """

            if draft.type is RunEventType.RUN_FAILED:
                bare_terminal_append_calls.append(draft.run_id)
            return await original_append(self, draft)

        monkeypatch.setattr(
            DurableRunEventStore,
            "append",
            _spy_append,
        )

        request = _request()
        with caplog.at_level(logging.ERROR, logger="dayu.host._run_harness"):
            stream = await bundle.harness.start_run(request)
            events = await asyncio.wait_for(
                _collect(stream.events), timeout=5.0
            )

        assert lease_context_call_count == 2
        assert len(terminal_close_attempts) == 2, (
            "acquire-failure terminal close fencing 后必须再走 "
            "_handle_owner_lost 的 append_terminal_and_close 尝试"
        )
        assert bare_terminal_append_calls == []
        assert all(
            not (
                event.type is RunEventType.RUN_FAILED
                and event.source is RunEventSource.HOST
            )
            for event in events
        ), "CAS miss 路径不应写 stale HOST terminal RunEvent"
        stored_events = await bundle.event_store.list_events(request.run_id, None)
        assert any(
            event.type is RunEventType.CONTEXT_COMPACT_COMPLETED
            for event in stored_events
        ), "compact success diagnostic 应已落库"
        terminal_events = [
            event for event in stored_events
            if event.type in TERMINAL_RUN_EVENT_TYPES
        ]
        assert len(terminal_events) <= 1, (
            "terminal close CAS miss 不得制造第二个 terminal truth"
        )
        assert all(
            not (
                event.type is RunEventType.RUN_FAILED
                and event.source is RunEventSource.HOST
            )
            for event in terminal_events
        ), "stale Host terminal 不得在 EventLog 中成为终态真源"
        assert all(
            "host.run.background_task_failed" not in record.getMessage()
            for record in caplog.records
        ), "AttemptFencingError 不应裸冒泡为 background task 失败"
    finally:
        bundle.close()
