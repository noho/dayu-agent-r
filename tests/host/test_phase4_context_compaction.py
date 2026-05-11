"""Host P4 deterministic context compact 测试。"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from dayu.engine import AgentMessageRole, RunnerCallOptions, RunnerSpec
from dayu.engine.contracts.agent_policy import AgentPolicy
from dayu.engine.contracts.messages import SystemMessage, UserMessage
from dayu.host._context_compaction import (
    ContextCompactCoordinator,
    ContextCompactDecisionStatus,
)
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
from dayu.host._run_input_builder import DefaultRunInputBuilder
from dayu.host.contracts import (
    RunEvent,
    RunEventCursor,
    RunInput,
    RunOptions,
    RunEventType,
    StartRunRequest,
)


def _utc_now() -> datetime:
    """返回测试用 UTC 当前时间。

    :returns: 当前 UTC 时间。
    :raises Exception: 不主动抛出异常。
    """

    return datetime.now(tz=timezone.utc)


def _provenance(*, cursor: int) -> MemoryProvenance:
    """构造 memory provenance。

    :param cursor: 来源 cursor。
    :returns: MemoryProvenance。
    :raises Exception: 不主动抛出异常。
    """

    return MemoryProvenance(
        source_run_id="run-old",
        source_event_cursor=RunEventCursor(sequence=cursor),
        producer_kind=MemoryProducerKind.HOST_TOOL_RUNTIME,
        ingestion_policy=MemoryIngestionPolicy.TOOL_FACT_CANONICAL,
        scope=MemoryScope.SESSION,
        trust_level=MemoryTrustLevel.TOOL_OBSERVED,
    )


def _current_user_event() -> RunEvent:
    """构造当前用户输入事件。

    :returns: RunEvent。
    :raises Exception: 不主动抛出异常。
    """

    draft = user_input_accepted_draft(
        run_id="run-p4",
        session_id="session-p4",
        occurred_at=_utc_now(),
        turn_id="run-p4",
        content="继续分析 A 公司 2024 年收入增长原因",
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
        source_engine_event_id=None,
    )


def _snapshot() -> ConversationMemorySnapshot:
    """构造包含 raw history 与工具证据的 memory 快照。

    :returns: ConversationMemorySnapshot。
    :raises Exception: 不主动抛出异常。
    """

    provenance = _provenance(cursor=5)
    raw_turn = ConversationRawTurn(
        turn_id="turn-old",
        user_text="请分析 A 公司。" * 200,
        assistant_final="这里是很长的旧回答。" * 200,
        user_provenance=provenance,
        assistant_provenance=provenance,
    )
    fact = ConversationToolFact(
        fact_id="tool_fact:run-old:5",
        tool_name="fins.lookup",
        tool_call_id="call-1",
        event_type=RunEventType.TOOL_RESULT_ACCEPTED,
        summary="收入同比增长 12%，来源为 2024 年年报。",
        cursor_fingerprint="fp-safe",
        has_more=True,
        provenance=provenance,
    )
    anchor = EvidenceAnchor(
        anchor_id="anchor:tool_fact:run-old:5",
        origin_event_cursor=RunEventCursor(sequence=5),
        tool_call_id="call-1",
        source_ref="tool:fins.lookup",
        chunk_ref="chunk-1",
        fingerprint="fp-safe",
        summary="收入增长证据锚点",
        provenance=provenance,
    )
    return ConversationMemorySnapshot(
        session_id="session-p4",
        pinned_state=ConversationPinnedState(
            current_goal="分析 A 公司财报",
            confirmed_subjects=("A 公司",),
            user_constraints=("只使用已给证据",),
            open_questions=(),
        ),
        task_frame=TaskFrame(topic_ref="revenue"),
        verified_claims=(),
        assumptions=AssumptionRegister(),
        evidence_anchors=(anchor,),
        recent_raw_turns=(raw_turn,),
        older_raw_turns=(),
        tool_facts=(fact,),
        user_preference_ref=UserPreferenceProfileRef(),
    )


def _request(run_input: RunInput) -> StartRunRequest:
    """构造 StartRunRequest。

    :param run_input: attempt RunInput。
    :returns: StartRunRequest。
    :raises Exception: 不主动抛出异常。
    """

    return StartRunRequest(
        session_id="session-p4",
        run_id="run-p4",
        input=run_input,
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


def test_compact_preserves_current_user_pinned_state_and_evidence() -> None:
    """compact 后必须严格变短并保留当前问题与证据锚点。"""

    snapshot = _snapshot()
    current_event = _current_user_event()
    build = DefaultRunInputBuilder().build(
        snapshot=snapshot,
        current_user_event=current_event,
    )
    decision = ContextCompactCoordinator().compact(
        request=_request(build.run_input),
        snapshot=snapshot,
        current_user_event=current_event,
        attempt_index=0,
    )

    assert decision.status is ContextCompactDecisionStatus.COMPLETED
    assert decision.completed_data is not None
    assert decision.run_input is not None
    assert decision.completed_data.after_token_estimate < (
        decision.completed_data.before_token_estimate
    )
    compact_text = "\n".join(
        "" if message.content is None else message.content
        for message in decision.run_input.messages
    )
    assert "继续分析 A 公司 2024 年收入增长原因" in compact_text
    assert "current_goal=分析 A 公司财报" in compact_text
    assert "anchor:tool_fact:run-old:5" in compact_text
    assert "source_event_cursor=5" in compact_text
    assert "tool_fact:run-old:5" in compact_text
    assert "INTERNAL_ONLY" in compact_text
    assert decision.completed_data.dropped_item_count == 1
    assert decision.completed_data.degraded_item_count == 0


def test_compact_memory_groups_repeated_sections_once() -> None:
    """多个 claim / anchor / tool fact 只渲染一次 section header。"""

    snapshot = _snapshot()
    provenance = _provenance(cursor=6)
    first_anchor = snapshot.evidence_anchors[0]
    first_fact = snapshot.tool_facts[0]
    verified_claim = MemoryClaim(
        claim_id="claim-verified-1",
        status=ClaimStatus.VERIFIED,
        text="收入增长已验证。",
        source_run_id="run-old",
        source_event_cursor=RunEventCursor(sequence=5),
        evidence_anchor_id=first_anchor.anchor_id,
        scope=MemoryScope.SESSION,
        created_at=_utc_now(),
        supersedes=(),
        provenance=first_anchor.provenance,
    )
    assumption = MemoryClaim(
        claim_id="claim-assumption-1",
        status=ClaimStatus.ASSUMPTION,
        text="增长可能来自销量提升。",
        source_run_id="run-old",
        source_event_cursor=RunEventCursor(sequence=6),
        evidence_anchor_id=None,
        scope=MemoryScope.SESSION,
        created_at=_utc_now(),
        supersedes=(),
        provenance=provenance,
    )
    snapshot = replace(
        snapshot,
        verified_claims=(verified_claim,),
        assumptions=AssumptionRegister(claims=(assumption,)),
        evidence_anchors=(
            first_anchor,
            replace(
                first_anchor,
                anchor_id="anchor:tool_fact:run-old:6",
                origin_event_cursor=RunEventCursor(sequence=6),
                provenance=provenance,
            ),
        ),
        tool_facts=(
            first_fact,
            replace(
                first_fact,
                fact_id="tool_fact:run-old:6",
                provenance=provenance,
                cursor_fingerprint="fp-safe-2",
            ),
        ),
    )
    current_event = _current_user_event()
    build = DefaultRunInputBuilder().build(
        snapshot=snapshot,
        current_user_event=current_event,
    )
    decision = ContextCompactCoordinator().compact(
        request=_request(build.run_input),
        snapshot=snapshot,
        current_user_event=current_event,
        attempt_index=0,
    )

    assert decision.status is ContextCompactDecisionStatus.COMPLETED
    assert decision.run_input is not None
    compact_text = "\n".join(
        "" if message.content is None else message.content
        for message in decision.run_input.messages
    )
    assert compact_text.count("## Stable Claims") == 1
    assert compact_text.count("## Evidence Anchors") == 1
    assert compact_text.count("## Tool Facts") == 1
    assert "claim_id=claim-verified-1" in compact_text
    assert "claim_id=claim-assumption-1" in compact_text
    assert "source_event_cursor=6" in compact_text


def test_compact_noop_fails_without_retry_input() -> None:
    """无法变短的 compact 必须失败，不能产出 retry input。"""

    snapshot = _snapshot()
    current_event = _current_user_event()
    run_input = RunInput(
        messages=(
            SystemMessage(
                role=AgentMessageRole.SYSTEM,
                content="short",
            ),
            UserMessage(
                role=AgentMessageRole.USER,
                content="继续分析 A 公司 2024 年收入增长原因",
            ),
        )
    )
    decision = ContextCompactCoordinator().compact(
        request=_request(run_input),
        snapshot=snapshot,
        current_user_event=current_event,
        attempt_index=0,
    )

    assert decision.status is ContextCompactDecisionStatus.FAILED
    assert decision.failed_data is not None
    assert decision.run_input is None
