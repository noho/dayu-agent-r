"""Host P3 RunInputBuilder 测试。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from dayu.engine import AgentMessage, AgentMessageRole, SystemMessage, UserMessage
from dayu.host._conversation_memory import (
    AssumptionRegister,
    ClaimStatus,
    ConversationMemorySnapshot,
    ConversationPinnedState,
    ConversationRawTurn,
    ConversationToolFact,
    EvidenceAnchor,
    MemoryClaim,
    MemoryIngestionPolicy,
    MemoryProducerKind,
    MemoryProvenance,
    MemoryScope,
    MemoryTrustLevel,
    TaskFrame,
    UserPreferenceProfileRef,
)
from dayu.host._event_translation import user_input_accepted_draft
from dayu.host._run_input_builder import (
    DefaultRunInputBuilder,
    RunInputTraceItemKind,
    RunInputTraceStatus,
)
from dayu.host.contracts import RunEvent, RunEventCursor, RunEventType


def _utc_now() -> datetime:
    """返回测试用 UTC 当前时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


def _provenance(
    *,
    run_id: str,
    cursor: int,
    producer_kind: MemoryProducerKind,
    trust_level: MemoryTrustLevel,
) -> MemoryProvenance:
    """构造测试溯源。

    :param run_id: 来源 run id。
    :param cursor: 来源 cursor sequence。
    :param producer_kind: 生产者类型。
    :param trust_level: 信任等级。
    :returns: MemoryProvenance。
    :raises Exception: 不主动抛出异常。
    """

    return MemoryProvenance(
        source_run_id=run_id,
        source_event_cursor=RunEventCursor(sequence=cursor),
        producer_kind=producer_kind,
        ingestion_policy=MemoryIngestionPolicy.PRIMARY_SESSION_CANONICAL,
        scope=MemoryScope.SESSION,
        trust_level=trust_level,
    )


def _current_user_event(content: str = "当前问题") -> RunEvent:
    """构造当前用户输入事件。

    :param content: 用户输入正文。
    :returns: 已成形 RunEvent。
    :raises Exception: 不主动抛出异常。
    """

    draft = user_input_accepted_draft(
        run_id="run-current",
        session_id="session-builder",
        occurred_at=_utc_now(),
        turn_id="run-current",
        content=content,
    )
    return RunEvent(
        run_id=draft.run_id,
        session_id=draft.session_id,
        cursor=RunEventCursor(sequence=0),
        kind=draft.kind,
        source=draft.source,
        type=draft.type,
        occurred_at=draft.occurred_at,
        data=draft.data,
        source_engine_event_id=draft.source_engine_event_id,
    )


def _snapshot() -> ConversationMemorySnapshot:
    """构造包含所有 P3 memory slot 的测试快照。

    :returns: ConversationMemorySnapshot。
    :raises Exception: 不主动抛出异常。
    """

    user_provenance = _provenance(
        run_id="run-old",
        cursor=0,
        producer_kind=MemoryProducerKind.HOST_USER_INPUT,
        trust_level=MemoryTrustLevel.USER_PROVIDED,
    )
    assistant_provenance = _provenance(
        run_id="run-old",
        cursor=3,
        producer_kind=MemoryProducerKind.ENGINE_FINAL_ANSWER,
        trust_level=MemoryTrustLevel.ASSISTANT_CONCLUSION,
    )
    claim_provenance = _provenance(
        run_id="run-claim",
        cursor=2,
        producer_kind=MemoryProducerKind.HOST_PROJECTION,
        trust_level=MemoryTrustLevel.EVIDENCE_BACKED,
    )
    assumption_provenance = _provenance(
        run_id="run-assumption",
        cursor=1,
        producer_kind=MemoryProducerKind.USER_CORRECTION,
        trust_level=MemoryTrustLevel.ASSUMPTION,
    )
    anchor_provenance = _provenance(
        run_id="run-tool",
        cursor=4,
        producer_kind=MemoryProducerKind.ENGINE_TOOL_FACT,
        trust_level=MemoryTrustLevel.TOOL_OBSERVED,
    )
    verified_claim = MemoryClaim(
        claim_id="claim-verified",
        status=ClaimStatus.VERIFIED,
        text="已验证事实",
        source_run_id="run-claim",
        source_event_cursor=RunEventCursor(sequence=2),
        evidence_anchor_id="anchor-1",
        scope=MemoryScope.SESSION,
        created_at=_utc_now(),
        supersedes=(),
        provenance=claim_provenance,
    )
    assumption = MemoryClaim(
        claim_id="claim-assumption",
        status=ClaimStatus.ASSUMPTION,
        text="待验证假设",
        source_run_id="run-assumption",
        source_event_cursor=RunEventCursor(sequence=1),
        evidence_anchor_id=None,
        scope=MemoryScope.SESSION,
        created_at=_utc_now(),
        supersedes=(),
        provenance=assumption_provenance,
    )
    anchor = EvidenceAnchor(
        anchor_id="anchor-1",
        origin_event_cursor=RunEventCursor(sequence=4),
        tool_call_id="tool-call",
        source_ref="tool:lookup",
        chunk_ref="chunk-a",
        fingerprint="fingerprint-only",
        summary="工具证据摘要",
        provenance=anchor_provenance,
    )
    tool_fact = ConversationToolFact(
        fact_id="tool-fact-1",
        tool_name="lookup",
        tool_call_id="tool-call",
        event_type=RunEventType.TOOL_RESULT_ACCEPTED,
        summary="工具事实摘要",
        cursor_fingerprint="fingerprint-only",
        has_more=False,
        provenance=anchor_provenance,
    )
    return ConversationMemorySnapshot(
        session_id="session-builder",
        pinned_state=ConversationPinnedState(
            current_goal="分析收入质量",
            confirmed_subjects=("公司A", "2025 年报"),
            user_constraints=("使用 IFRS 口径",),
            open_questions=("解释毛利率下滑",),
        ),
        task_frame=TaskFrame(
            topic_ref="topic",
            entity_refs=("entity",),
            period_refs=("period",),
            basis_refs=("basis",),
            unit_ref="unit",
        ),
        verified_claims=(verified_claim,),
        assumptions=AssumptionRegister(claims=(assumption,)),
        evidence_anchors=(anchor,),
        recent_raw_turns=(
            ConversationRawTurn(
                turn_id="turn-recent",
                user_text="上一轮用户",
                assistant_final="上一轮最终回答",
                user_provenance=user_provenance,
                assistant_provenance=assistant_provenance,
            ),
        ),
        older_raw_turns=(
            ConversationRawTurn(
                turn_id="turn-older",
                user_text="很早的问题",
                assistant_final="很早的回答",
                user_provenance=user_provenance,
                assistant_provenance=assistant_provenance,
            ),
        ),
        tool_facts=(tool_fact,),
        user_preference_ref=UserPreferenceProfileRef(
            profile_id="profile-session",
            scope=MemoryScope.SESSION,
        ),
    )


def _system_content(result_messages: Sequence[AgentMessage]) -> str:
    """读取 RunInput 中的 system memory block。

    :param result_messages: RunInput messages。
    :returns: system content。
    :raises AssertionError: 首条消息不是 SystemMessage 时抛出。
    """

    first = result_messages[0]
    assert isinstance(first, SystemMessage)
    return first.content


def _message_text(message: AgentMessage) -> str:
    """返回测试中可拼接的消息文本。

    :param message: Agent 消息。
    :returns: 文本内容；assistant 空正文返回空字符串。
    :raises Exception: 不主动抛出异常。
    """

    if message.content is None:
        return ""
    return message.content


def test_builder_orders_memory_block_and_current_user_message() -> None:
    """memory block 顺序与 current user 末尾消息保持稳定。"""

    result = DefaultRunInputBuilder().build(
        snapshot=_snapshot(),
        current_user_event=_current_user_event("当前财报问题"),
    )
    messages = result.run_input.messages

    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[-1], UserMessage)
    assert messages[-1].content == "当前财报问题"
    content = messages[0].content
    markers = (
        "## Pinned State",
        "## Stable Frame",
        "## Verified Claims",
        "## Assumptions",
        "## Evidence Anchors",
        "## Recent Raw Turns",
        "## Older Pool",
        "## Episode Summary Slot",
    )
    positions = [content.index(marker) for marker in markers]
    assert positions == sorted(positions)
    assert "current_goal=分析收入质量" in content
    assert "confirmed_subjects=公司A; 2025 年报" in content
    assert "user_constraints=使用 IFRS 口径" in content
    assert "open_questions=解释毛利率下滑" in content


def test_tool_facts_and_evidence_anchors_do_not_enter_assistant_history() -> None:
    """tool facts / evidence anchors 只进入独立 memory block。"""

    result = DefaultRunInputBuilder().build(
        snapshot=_snapshot(),
        current_user_event=_current_user_event(),
    )
    messages = result.run_input.messages
    system_content = _system_content(messages)

    assert "工具事实摘要" in system_content
    assert "fingerprint-only" in system_content
    assert "source_event_cursor=4" in system_content
    assert "scope_token" not in system_content
    assert not any(message.role is AgentMessageRole.ASSISTANT for message in messages)
    assert not any(message.role is AgentMessageRole.TOOL for message in messages)


def test_trace_records_included_sources_and_does_not_enter_run_input() -> None:
    """RunInputBuildTrace 记录来源与估算大小，但不进入 RunInput。"""

    result = DefaultRunInputBuilder().build(
        snapshot=_snapshot(),
        current_user_event=_current_user_event(),
    )
    trace = result.trace
    input_text = "\n".join(
        _message_text(message) for message in result.run_input.messages
    )

    assert trace.total_char_size > 0
    assert trace.total_token_estimate > 0
    assert any(
        item.item_kind is RunInputTraceItemKind.TOOL_FACT
        and item.source_run_id == "run-tool"
        and item.source_event_cursor == 4
        and item.status is RunInputTraceStatus.INCLUDED
        for item in trace.items
    )
    assert "memory_block_budget_exhausted" not in input_text
    assert "recent_turn_downgraded" not in input_text


def test_large_recent_turn_is_downgraded_instead_of_unbounded_floor() -> None:
    """超大旧轮 recent floor 以摘要进入，不无限挤占窗口。"""

    long_text = "长文本" * 1000
    snapshot = ConversationMemorySnapshot(
        session_id="session-builder",
        pinned_state=ConversationPinnedState(),
        task_frame=TaskFrame(),
        verified_claims=(),
        assumptions=AssumptionRegister(),
        evidence_anchors=(),
        recent_raw_turns=(
            ConversationRawTurn(
                turn_id="long-turn",
                user_text=long_text,
                assistant_final=long_text,
                user_provenance=_provenance(
                    run_id="run-long",
                    cursor=0,
                    producer_kind=MemoryProducerKind.HOST_USER_INPUT,
                    trust_level=MemoryTrustLevel.USER_PROVIDED,
                ),
                assistant_provenance=None,
            ),
        ),
        older_raw_turns=(),
        tool_facts=(),
        user_preference_ref=UserPreferenceProfileRef(),
    )

    result = DefaultRunInputBuilder().build(
        snapshot=snapshot,
        current_user_event=_current_user_event("当前问题不能被挤掉"),
    )
    first_message = result.run_input.messages[0]
    assert isinstance(first_message, SystemMessage)
    content = first_message.content

    assert len(content) < len(long_text)
    assert "已裁剪" in content
    assert result.run_input.messages[-1].content == "当前问题不能被挤掉"
    assert any(
        item.status is RunInputTraceStatus.EXCLUDED
        and item.item_kind is RunInputTraceItemKind.RECENT_RAW_TURN
        and item.reason == "recent_turn_downgraded"
        for item in result.trace.items
    )


def test_memory_block_budget_excludes_items_with_trace_reason() -> None:
    """预算不足时 trace 记录 excluded item 与裁剪原因。"""

    result = DefaultRunInputBuilder(memory_block_char_budget=80).build(
        snapshot=_snapshot(),
        current_user_event=_current_user_event(),
    )

    assert any(
        item.status is RunInputTraceStatus.EXCLUDED
        and item.reason == "memory_block_budget_exhausted"
        for item in result.trace.items
    )


def test_pinned_state_is_injected_outside_memory_pool_budget() -> None:
    """pinned state 全量注入且不参与历史池预算竞争。"""

    result = DefaultRunInputBuilder(memory_block_char_budget=1).build(
        snapshot=_snapshot(),
        current_user_event=_current_user_event(),
    )
    content = _system_content(result.run_input.messages)

    assert "## Pinned State" in content
    assert "current_goal=分析收入质量" in content
    assert "confirmed_subjects=公司A; 2025 年报" in content
    assert "user_constraints=使用 IFRS 口径" in content
    assert "open_questions=解释毛利率下滑" in content
    assert any(
        item.item_kind is RunInputTraceItemKind.PINNED_STATE
        and item.status is RunInputTraceStatus.INCLUDED
        for item in result.trace.items
    )


def test_verified_claims_and_assumptions_are_stable_budget_exempt() -> None:
    """verified claims / assumptions 全量注入且不参与历史池预算竞争。"""

    result = DefaultRunInputBuilder(memory_block_char_budget=1).build(
        snapshot=_snapshot(),
        current_user_event=_current_user_event(),
    )
    content = _system_content(result.run_input.messages)

    assert "claim_id=claim-verified" in content
    assert "text=已验证事实" in content
    assert "claim_id=claim-assumption" in content
    assert "text=待验证假设" in content
    assert all(
        not (
            item.source_id in {"claim-verified", "claim-assumption"}
            and item.status is RunInputTraceStatus.EXCLUDED
        )
        for item in result.trace.items
    )


def test_builder_rejects_snapshot_session_mismatch() -> None:
    """RunInputBuilder 拒绝 snapshot 与当前事件 session 不一致。"""

    bad_snapshot = replace(_snapshot(), session_id="session-other")

    with pytest.raises(ValueError, match="snapshot_session_mismatch"):
        DefaultRunInputBuilder().build(
            snapshot=bad_snapshot,
            current_user_event=_current_user_event(),
        )


def test_older_pool_consumes_budget_new_to_old_but_renders_chronologically() -> None:
    """older raw turns 从新到旧抢预算，输出仍保持时间顺序。"""

    provenance = _provenance(
        run_id="run-older",
        cursor=0,
        producer_kind=MemoryProducerKind.HOST_USER_INPUT,
        trust_level=MemoryTrustLevel.USER_PROVIDED,
    )
    snapshot = ConversationMemorySnapshot(
        session_id="session-builder",
        pinned_state=ConversationPinnedState(),
        task_frame=TaskFrame(),
        verified_claims=(),
        assumptions=AssumptionRegister(),
        evidence_anchors=(),
        recent_raw_turns=(),
        older_raw_turns=(
            ConversationRawTurn(
                turn_id="older-1",
                user_text="oldest older " + "甲" * 80,
                assistant_final="oldest answer",
                user_provenance=provenance,
                assistant_provenance=None,
            ),
            ConversationRawTurn(
                turn_id="older-2",
                user_text="middle older " + "乙" * 80,
                assistant_final="middle answer",
                user_provenance=provenance,
                assistant_provenance=None,
            ),
            ConversationRawTurn(
                turn_id="older-3",
                user_text="newest older " + "丙" * 80,
                assistant_final="newest answer",
                user_provenance=provenance,
                assistant_provenance=None,
            ),
        ),
        tool_facts=(),
        user_preference_ref=UserPreferenceProfileRef(),
    )

    result = DefaultRunInputBuilder(memory_block_char_budget=430).build(
        snapshot=snapshot,
        current_user_event=_current_user_event(),
    )
    content = _system_content(result.run_input.messages)

    assert "newest older" in content
    assert "oldest older" not in content
    if "middle older" in content:
        assert content.index("middle older") < content.index("newest older")
    assert any(
        item.item_kind is RunInputTraceItemKind.OLDER_RAW_TURN
        and item.source_id == "older-1"
        and item.status is RunInputTraceStatus.EXCLUDED
        and item.reason == "memory_block_budget_exhausted"
        for item in result.trace.items
    )
