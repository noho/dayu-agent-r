"""Host P4 context overflow retry 测试。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
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
from dayu.host._run_harness import LocalRunHarness
from tests.host._memory_store_fake import FakeInMemoryConversationMemoryStore
from dayu.host._event_store import InMemoryRunEventStore, RunEventStore
from dayu.host.contracts import (
    ContextCompactFailureReason,
    HostContextCompactCompletedData,
    HostContextCompactFailedData,
    HostContextAttemptRetryData,
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
    ToolResultTruncatedData,
    ToolValueSizeSummary,
)


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
    """构造测试用 Host 工具截断事实。

    :param run_id: Run id。
    :param session_id: Session id。
    :returns: RunEventDraft。
    :raises Exception: 不主动抛出异常。
    """

    return RunEventDraft(
        run_id=run_id,
        session_id=session_id,
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.TOOL_RESULT_TRUNCATED,
        occurred_at=_utc_now(),
        data=ToolResultTruncatedData(
            iteration_id="iter-0",
            tool_name="fins.lookup",
            tool_call_id="call-current",
            strategy="preview_with_cursor",
            limit=1024,
            unit="chars",
            total_estimate=4096,
            cursor_fingerprint="fp-current",
            ttl_seconds=600,
            has_more=True,
            value_summary=ToolValueSizeSummary(
                unit="chars",
                size=1024,
                total_estimate=4096,
                fingerprint="value-fp-current",
            ),
        ),
        source_engine_event_id=None,
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
    harness = LocalRunHarness(proxy=proxy, memory_store=memory_store)

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
            proxy=proxy,
            context_compact_retry_limit=-1,
            memory_store=FakeInMemoryConversationMemoryStore(),
        )


@pytest.mark.asyncio
async def test_compaction_requested_then_stream_end_observes_overflow() -> None:
    """非 terminal compact 触发路径也要追加 Host overflow observed 事实。"""

    proxy = _CompactionRequestedThenEndedProxy()
    memory_store: ConversationMemoryStore = _SnapshotMemoryStore(_large_snapshot())
    harness = LocalRunHarness(proxy=proxy, memory_store=memory_store)

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
    assert "cursor_fingerprint=fp-current" in compact_text
    assert "has_more=True" in compact_text


@pytest.mark.asyncio
async def test_missing_trace_cache_compact_failure_gets_host_terminal() -> None:
    """trace 缓存淘汰后 compact 失败必须有 Host-owned failed terminal。"""

    gate = asyncio.Event()
    proxy = _DelayedOverflowProxy(gate=gate)
    memory_store: ConversationMemoryStore = _SnapshotMemoryStore(_snapshot())
    harness = LocalRunHarness(
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
    harness = LocalRunHarness(proxy=proxy, memory_store=memory_store)

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
    harness = LocalRunHarness(proxy=proxy, memory_store=memory_store)

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
    harness = LocalRunHarness(proxy=proxy, memory_store=memory_store)
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
    harness = LocalRunHarness(proxy=proxy, memory_store=FakeInMemoryConversationMemoryStore())

    with pytest.raises(ValueError, match=expected_error):
        await harness.start_run(_request(messages=messages))
