"""Host P3 Conversation Memory 投影测试。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import cast

import pytest

from dayu.contracts.tool_outcome import ToolCompletedOutcome
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.engine import (
    ContentDeltaData,
    FinalAnswerData,
    FinishReason,
    ReasoningDeltaData,
    SystemMessage,
    ToolResultAcceptedData,
)
from dayu.host._conversation_memory import (
    ClaimCorrectionPatch,
    ClaimStatus,
    InMemoryConversationMemoryStore,
    MemoryClaim,
    MemoryIngestionPolicy,
    MemoryProducerKind,
    MemoryScope,
    MemoryTrustLevel,
    MemoryResetPatch,
    MemoryProvenance,
    ScopeClearPatch,
)
from dayu.host._event_store import InMemoryRunEventStore
from dayu.host._event_translation import user_input_accepted_draft
from dayu.host._run_input_builder import DefaultRunInputBuilder
from dayu.host.contracts import (
    HostRunFailedData,
    RunEvent,
    RunEventDraft,
    RunEventKind,
    RunEventSource,
    RunEventType,
    UserInputAcceptedData,
    UserInputScope,
)


def _utc_now() -> datetime:
    """返回测试用 UTC 当前时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


def _memory_claim(
    *,
    claim_id: str,
    text: str,
    source_event: RunEvent,
) -> MemoryClaim:
    """构造测试用用户确认 claim。

    :param claim_id: claim id。
    :param text: claim 文本。
    :param source_event: 来源事件。
    :returns: MemoryClaim。
    :raises Exception: 不主动抛出异常。
    """

    provenance = MemoryProvenance(
        source_run_id=source_event.run_id,
        source_event_cursor=source_event.cursor,
        producer_kind=MemoryProducerKind.USER_CORRECTION,
        ingestion_policy=MemoryIngestionPolicy.USER_CONFIRMED_CORRECTION,
        scope=MemoryScope.SESSION,
        trust_level=MemoryTrustLevel.USER_PROVIDED,
    )
    return MemoryClaim(
        claim_id=claim_id,
        status=ClaimStatus.VERIFIED,
        text=text,
        source_run_id=source_event.run_id,
        source_event_cursor=source_event.cursor,
        evidence_anchor_id=None,
        scope=MemoryScope.SESSION,
        created_at=_utc_now(),
        supersedes=(),
        provenance=provenance,
    )


async def _append_final(
    store: InMemoryRunEventStore,
    *,
    session_id: str,
    run_id: str,
    content: str,
) -> RunEvent:
    """追加 final answer 事件。

    :param store: RunEventStore。
    :param session_id: 会话 id。
    :param run_id: Run id。
    :param content: 最终回答。
    :returns: 已 append 的 RunEvent。
    :raises Exception: 透传 store append 异常。
    """

    return await store.append(
        RunEventDraft(
            run_id=run_id,
            session_id=session_id,
            kind=RunEventKind.CANONICAL,
            source=RunEventSource.ENGINE,
            type=RunEventType.FINAL_ANSWER,
            occurred_at=_utc_now(),
            data=FinalAnswerData(
                content=content,
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            source_engine_event_id=f"{run_id}:final",
        )
    )


async def _append_tool_result(
    store: InMemoryRunEventStore,
    *,
    session_id: str,
    run_id: str,
) -> RunEvent:
    """追加工具结果接纳事件。

    :param store: RunEventStore。
    :param session_id: 会话 id。
    :param run_id: Run id。
    :returns: 已 append 的 RunEvent。
    :raises Exception: 透传 store append 异常。
    """

    return await store.append(
        RunEventDraft(
            run_id=run_id,
            session_id=session_id,
            kind=RunEventKind.CANONICAL,
            source=RunEventSource.ENGINE,
            type=RunEventType.TOOL_RESULT_ACCEPTED,
            occurred_at=_utc_now(),
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
            source_engine_event_id=f"{run_id}:tool",
        )
    )


async def _append_host_failure(
    store: InMemoryRunEventStore,
    *,
    session_id: str,
    run_id: str,
) -> RunEvent:
    """追加 Host-owned failure 事件。

    :param store: RunEventStore。
    :param session_id: 会话 id。
    :param run_id: Run id。
    :returns: 已 append 的 RunEvent。
    :raises Exception: 透传 store append 异常。
    """

    return await store.append(
        RunEventDraft(
            run_id=run_id,
            session_id=session_id,
            kind=RunEventKind.CANONICAL,
            source=RunEventSource.HOST,
            type=RunEventType.RUN_FAILED,
            occurred_at=_utc_now(),
            data=HostRunFailedData(
                error_code="host_worker_failed",
                message="proxy disconnected",
                recoverable=False,
                exception_type="RuntimeError",
            ),
            source_engine_event_id=None,
        )
    )


async def _append_preview_events(
    store: InMemoryRunEventStore,
    *,
    session_id: str,
    run_id: str,
) -> None:
    """追加 display-only preview 事件。

    :param store: RunEventStore。
    :param session_id: 会话 id。
    :param run_id: Run id。
    :returns: 无返回值。
    :raises Exception: 透传 store append 异常。
    """

    await store.append(
        RunEventDraft(
            run_id=run_id,
            session_id=session_id,
            kind=RunEventKind.PREVIEW,
            source=RunEventSource.ENGINE,
            type=RunEventType.RUNNER_REASONING_DELTA,
            occurred_at=_utc_now(),
            data=ReasoningDeltaData(iteration_id="iter", delta="hidden chain"),
            source_engine_event_id=f"{run_id}:reasoning",
        )
    )
    await store.append(
        RunEventDraft(
            run_id=run_id,
            session_id=session_id,
            kind=RunEventKind.PREVIEW,
            source=RunEventSource.ENGINE,
            type=RunEventType.RUNNER_CONTENT_DELTA,
            occurred_at=_utc_now(),
            data=ContentDeltaData(iteration_id="iter", delta="preview only"),
            source_engine_event_id=f"{run_id}:delta",
        )
    )


@pytest.mark.asyncio
async def test_projection_reads_user_input_from_canonical_eventlog() -> None:
    """用户输入、final answer 与 tool fact 从 EventLog 投影。"""

    event_store = InMemoryRunEventStore()
    memory_store = InMemoryConversationMemoryStore()
    user_event = await event_store.append(
        user_input_accepted_draft(
            run_id="run-1",
            session_id="session-a",
            occurred_at=_utc_now(),
            turn_id="turn-1",
            content="请分析收入",
        )
    )
    await _append_preview_events(
        event_store,
        session_id="session-a",
        run_id="run-1",
    )
    tool_event = await _append_tool_result(
        event_store,
        session_id="session-a",
        run_id="run-1",
    )
    await _append_final(
        event_store,
        session_id="session-a",
        run_id="run-1",
        content="收入增长。",
    )

    events = await event_store.list_events("run-1", after=None)
    await memory_store.project_run_events(events)
    snapshot = await memory_store.get_snapshot("session-a")

    assert len(snapshot.recent_raw_turns) == 1
    assert snapshot.recent_raw_turns[0].user_text == "请分析收入"
    assert snapshot.recent_raw_turns[0].assistant_final == "收入增长。"
    assert snapshot.recent_raw_turns[0].user_provenance.source_run_id == "run-1"
    assert (
        snapshot.recent_raw_turns[0].user_provenance.source_event_cursor
        == user_event.cursor
    )
    assert snapshot.tool_facts[0].tool_name == "financial_fact_lookup"
    assert snapshot.tool_facts[0].provenance.source_event_cursor == tool_event.cursor
    assert snapshot.evidence_anchors[0].tool_call_id == "tool-call-1"


@pytest.mark.asyncio
async def test_host_failure_terminal_projects_neutral_summary() -> None:
    """Host-owned failure 终态以中性摘要进入下一轮 memory。"""

    event_store = InMemoryRunEventStore()
    memory_store = InMemoryConversationMemoryStore()
    await event_store.append(
        user_input_accepted_draft(
            run_id="run-failed",
            session_id="session-failed",
            occurred_at=_utc_now(),
            turn_id="run-failed",
            content="请分析收入",
        )
    )
    failure_event = await _append_host_failure(
        event_store,
        session_id="session-failed",
        run_id="run-failed",
    )

    await memory_store.project_run_events(
        await event_store.list_events("run-failed", after=None)
    )
    snapshot = await memory_store.get_snapshot("session-failed")
    current_event = await event_store.append(
        user_input_accepted_draft(
            run_id="run-current",
            session_id="session-failed",
            occurred_at=_utc_now(),
            turn_id="run-current",
            content="继续分析",
        )
    )
    result = DefaultRunInputBuilder().build(
        snapshot=snapshot,
        current_user_event=current_event,
    )
    system_message = result.run_input.messages[0]

    assert len(snapshot.recent_raw_turns) == 1
    assert snapshot.recent_raw_turns[0].assistant_final is None
    assert snapshot.recent_raw_turns[0].terminal_summary is not None
    assert "host_worker_failed" in snapshot.recent_raw_turns[0].terminal_summary
    terminal_provenance = snapshot.recent_raw_turns[0].terminal_provenance
    assert terminal_provenance is not None
    assert terminal_provenance.source_event_cursor == failure_event.cursor
    assert isinstance(system_message, SystemMessage)
    assert "terminal: run_failed" in system_message.content
    assert "host_worker_failed" in system_message.content


@pytest.mark.asyncio
async def test_preview_and_reasoning_do_not_enter_memory_projection() -> None:
    """preview / reasoning / delta 不进入 memory pool。"""

    event_store = InMemoryRunEventStore()
    memory_store = InMemoryConversationMemoryStore()
    await event_store.append(
        user_input_accepted_draft(
            run_id="run-preview",
            session_id="session-preview",
            occurred_at=_utc_now(),
            turn_id="run-preview",
            content="当前问题",
        )
    )
    await _append_preview_events(
        event_store,
        session_id="session-preview",
        run_id="run-preview",
    )
    await _append_final(
        event_store,
        session_id="session-preview",
        run_id="run-preview",
        content="最终回答",
    )

    await memory_store.project_run_events(
        await event_store.list_events("run-preview", after=None)
    )
    snapshot = await memory_store.get_snapshot("session-preview")

    rendered_turn = snapshot.recent_raw_turns[0].user_text
    assert "hidden chain" not in rendered_turn
    assert "preview only" not in rendered_turn
    assert not snapshot.tool_facts


@pytest.mark.asyncio
async def test_assistant_final_answer_is_not_verified_claim() -> None:
    """assistant final answer 不自动升级为 verified claim。"""

    event_store = InMemoryRunEventStore()
    memory_store = InMemoryConversationMemoryStore()
    await event_store.append(
        user_input_accepted_draft(
            run_id="run-final",
            session_id="session-final",
            occurred_at=_utc_now(),
            turn_id="run-final",
            content="给出结论",
        )
    )
    await _append_final(
        event_store,
        session_id="session-final",
        run_id="run-final",
        content="这是助手结论，不是 verified fact。",
    )

    await memory_store.project_run_events(
        await event_store.list_events("run-final", after=None)
    )
    snapshot = await memory_store.get_snapshot("session-final")

    assert snapshot.recent_raw_turns[0].assistant_final is not None
    assert snapshot.verified_claims == ()
    assert snapshot.assumptions.claims == ()


@pytest.mark.asyncio
async def test_memory_items_carry_provenance_trust_and_scope() -> None:
    """memory item 必须携带 source / provenance / trust / scope 元数据。"""

    event_store = InMemoryRunEventStore()
    memory_store = InMemoryConversationMemoryStore()
    await event_store.append(
        user_input_accepted_draft(
            run_id="run-meta",
            session_id="session-meta",
            occurred_at=_utc_now(),
            turn_id="run-meta",
            content="用户输入",
        )
    )
    await _append_tool_result(
        event_store,
        session_id="session-meta",
        run_id="run-meta",
    )
    await _append_final(
        event_store,
        session_id="session-meta",
        run_id="run-meta",
        content="助手回答",
    )

    await memory_store.project_run_events(
        await event_store.list_events("run-meta", after=None)
    )
    snapshot = await memory_store.get_snapshot("session-meta")
    user_provenance = snapshot.recent_raw_turns[0].user_provenance
    tool_provenance = snapshot.tool_facts[0].provenance

    assert user_provenance.source_run_id == "run-meta"
    assert user_provenance.scope is MemoryScope.SESSION
    assert user_provenance.producer_kind is MemoryProducerKind.HOST_USER_INPUT
    assert (
        user_provenance.ingestion_policy
        is MemoryIngestionPolicy.PRIMARY_SESSION_CANONICAL
    )
    assert tool_provenance.scope is MemoryScope.SESSION
    assert tool_provenance.producer_kind is MemoryProducerKind.ENGINE_TOOL_FACT
    assert tool_provenance.source_event_cursor.sequence > 0


@pytest.mark.asyncio
async def test_user_input_scope_is_closed_enum_and_projection_fail_fast() -> None:
    """USER_INPUT_ACCEPTED scope 必须来自封闭枚举。"""

    event_store = InMemoryRunEventStore()
    memory_store = InMemoryConversationMemoryStore()
    valid_event = await event_store.append(
        user_input_accepted_draft(
            run_id="run-scope",
            session_id="session-scope",
            occurred_at=_utc_now(),
            turn_id="run-scope",
            content="用户输入",
        )
    )

    assert isinstance(valid_event.data, UserInputAcceptedData)
    assert valid_event.data.scope is UserInputScope.SESSION

    invalid_event = RunEvent(
        run_id="run-invalid-scope",
        session_id="session-scope",
        cursor=valid_event.cursor,
        kind=RunEventKind.CANONICAL,
        source=RunEventSource.HOST,
        type=RunEventType.USER_INPUT_ACCEPTED,
        occurred_at=_utc_now(),
        data=UserInputAcceptedData(
            turn_id="run-invalid-scope",
            content="非法 scope",
            scope=cast(UserInputScope, "workspace"),
        ),
        source_engine_event_id=None,
    )

    with pytest.raises(ValueError, match="scope"):
        await memory_store.project_run_events((invalid_event,))


@pytest.mark.asyncio
async def test_scope_clear_patch_rejects_non_session_scope() -> None:
    """P3 只支持 SESSION scope clear，非 SESSION scope 必须 fail fast。"""

    memory_store = InMemoryConversationMemoryStore()

    with pytest.raises(ValueError, match="scope_clear_only_supports_session"):
        await memory_store.apply_patch(
            ScopeClearPatch(
                session_id="session-scope-clear",
                scope=MemoryScope.PROJECT,
                reason="测试非 session scope",
            )
        )


@pytest.mark.asyncio
async def test_memory_reset_patch_clears_session_snapshot() -> None:
    """MemoryResetPatch 会清空指定 session 的 snapshot。"""

    event_store = InMemoryRunEventStore()
    memory_store = InMemoryConversationMemoryStore()
    user_event = await event_store.append(
        user_input_accepted_draft(
            run_id="run-reset",
            session_id="session-reset",
            occurred_at=_utc_now(),
            turn_id="run-reset",
            content="重置前问题",
        )
    )
    await _append_final(
        event_store,
        session_id="session-reset",
        run_id="run-reset",
        content="重置前回答",
    )
    await memory_store.project_run_events(
        await event_store.list_events("run-reset", after=None)
    )
    await memory_store.apply_patch(
        ClaimCorrectionPatch(
            session_id="session-reset",
            corrected_claim=_memory_claim(
                claim_id="claim-reset",
                text="重置前确认事实",
                source_event=user_event,
            ),
            reason="测试重置前 claim",
        )
    )

    await memory_store.apply_patch(
        MemoryResetPatch(
            session_id="session-reset",
            scope=MemoryScope.SESSION,
            reason="测试清空 session memory",
        )
    )
    snapshot = await memory_store.get_snapshot("session-reset")

    assert snapshot.recent_raw_turns == ()
    assert snapshot.older_raw_turns == ()
    assert snapshot.tool_facts == ()
    assert snapshot.evidence_anchors == ()
    assert snapshot.verified_claims == ()


@pytest.mark.asyncio
async def test_claim_correction_patch_appends_verified_claim() -> None:
    """ClaimCorrectionPatch 会追加用户确认 claim。"""

    event_store = InMemoryRunEventStore()
    memory_store = InMemoryConversationMemoryStore()
    user_event = await event_store.append(
        user_input_accepted_draft(
            run_id="run-claim",
            session_id="session-claim",
            occurred_at=_utc_now(),
            turn_id="run-claim",
            content="确认事实",
        )
    )
    first_claim = _memory_claim(
        claim_id="claim-1",
        text="收入同比增长。",
        source_event=user_event,
    )
    second_claim = _memory_claim(
        claim_id="claim-2",
        text="毛利率保持稳定。",
        source_event=user_event,
    )

    await memory_store.apply_patch(
        ClaimCorrectionPatch(
            session_id="session-claim",
            corrected_claim=first_claim,
            reason="测试追加第一条 claim",
        )
    )
    await memory_store.apply_patch(
        ClaimCorrectionPatch(
            session_id="session-claim",
            corrected_claim=second_claim,
            reason="测试追加第二条 claim",
        )
    )
    snapshot = await memory_store.get_snapshot("session-claim")

    assert snapshot.verified_claims == (first_claim, second_claim)


@pytest.mark.asyncio
async def test_concurrent_projection_keeps_same_session_turns() -> None:
    """同 session 并发投影不会丢失简单 raw turn 更新。"""

    event_store = InMemoryRunEventStore()
    memory_store = InMemoryConversationMemoryStore(recent_turn_limit=8)
    await event_store.append(
        user_input_accepted_draft(
            run_id="run-concurrent-a",
            session_id="session-concurrent",
            occurred_at=_utc_now(),
            turn_id="turn-concurrent-a",
            content="并发问题 A",
        )
    )
    await _append_final(
        event_store,
        session_id="session-concurrent",
        run_id="run-concurrent-a",
        content="并发回答 A",
    )
    await event_store.append(
        user_input_accepted_draft(
            run_id="run-concurrent-b",
            session_id="session-concurrent",
            occurred_at=_utc_now(),
            turn_id="turn-concurrent-b",
            content="并发问题 B",
        )
    )
    await _append_final(
        event_store,
        session_id="session-concurrent",
        run_id="run-concurrent-b",
        content="并发回答 B",
    )

    events_a = await event_store.list_events("run-concurrent-a", after=None)
    events_b = await event_store.list_events("run-concurrent-b", after=None)
    await asyncio.gather(
        memory_store.project_run_events(events_a),
        memory_store.project_run_events(events_b),
    )
    snapshot = await memory_store.get_snapshot("session-concurrent")
    turn_by_id = {turn.turn_id: turn for turn in snapshot.recent_raw_turns}

    assert set(turn_by_id) == {"turn-concurrent-a", "turn-concurrent-b"}
    assert turn_by_id["turn-concurrent-a"].assistant_final == "并发回答 A"
    assert turn_by_id["turn-concurrent-b"].assistant_final == "并发回答 B"


@pytest.mark.asyncio
async def test_different_sessions_do_not_share_memory() -> None:
    """不同 session 的 memory 不串读。"""

    event_store = InMemoryRunEventStore()
    memory_store = InMemoryConversationMemoryStore()
    await event_store.append(
        user_input_accepted_draft(
            run_id="run-a",
            session_id="session-a",
            occurred_at=_utc_now(),
            turn_id="run-a",
            content="A 的问题",
        )
    )
    await _append_final(
        event_store,
        session_id="session-a",
        run_id="run-a",
        content="A 的回答",
    )
    await memory_store.project_run_events(
        await event_store.list_events("run-a", after=None)
    )

    snapshot_a = await memory_store.get_snapshot("session-a")
    snapshot_b = await memory_store.get_snapshot("session-b")

    assert snapshot_a.recent_raw_turns[0].user_text == "A 的问题"
    assert snapshot_b.recent_raw_turns == ()
    assert snapshot_b.tool_facts == ()
