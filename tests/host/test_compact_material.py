"""P12.6 compact material selection 与 pack builder 测试。"""

from __future__ import annotations

import pytest

from dayu.host.compact_material import (
    CompactMemorySnapshotRepairRequired,
    DuplicateMaterialSectionOwnerError,
    InlineDeltaRepairMaterialView,
    RunInputMaterialBlock,
    build_compact_material_pack,
    check_compact_memory_snapshot_cursor,
    run_input_material_block,
    select_compact_segment,
)
from dayu.host.compaction import (
    CompactMaterialBlockKind,
    CompactMaterialSection,
    CompactSegmentTrigger,
)
from dayu.host.memory import (
    CONVERSATION_MEMORY_CONSUMER_ID,
    ConversationContinuityView,
    ConversationMemorySnapshot,
    MemoryProjectionPolicy,
    MemorySnapshotCursor,
    PinnedStateView,
    calculate_memory_snapshot_digest,
    digest_memory_projection_policy,
)

_SESSION_ID = "session-compact-material"
_POLICY_DIGEST = "policy-digest-compact-material"
_NOW = "2026-05-24T00:00:00.000000Z"


def test_segment_selection_is_deterministic_for_same_inputs() -> None:
    """相同输入必须得到相同 selected ids 与 digest。"""

    blocks = (
        _history_block("history-2", event_sequence=2, text="older user"),
        _evidence_block("evidence-3", event_sequence=3, text="tool result"),
        _current_block("current-4", event_sequence=4, text="current input"),
    )

    first = select_compact_segment(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=4,
        memory_snapshot_cursor=3,
        policy_digest=_POLICY_DIGEST,
        material_blocks=blocks,
    )
    second = select_compact_segment(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=4,
        memory_snapshot_cursor=3,
        policy_digest=_POLICY_DIGEST,
        material_blocks=tuple(reversed(blocks)),
    )

    assert first.selected_block_ids == second.selected_block_ids
    assert first.selection_digest == second.selection_digest


def test_proactive_segment_excludes_current_anchor_and_recent_raw_floor() -> None:
    """Proactive selection 不能压缩当前 anchor 与 recent raw floor。"""

    blocks = (
        _history_block("history-old", event_sequence=1, text="old user"),
        _history_block("history-recent", event_sequence=3, text="recent user"),
        _current_block("current", event_sequence=4, text="current user"),
    )

    selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=4,
        memory_snapshot_cursor=3,
        policy_digest=_POLICY_DIGEST,
        material_blocks=blocks,
        recent_raw_turns_floor=1,
    )

    assert selection.selected_block_ids == ("history-old",)
    assert selection.excluded_reason_codes["current"] == "protected_current_input"
    assert (
        selection.excluded_reason_codes["history-recent"]
        == "protected_recent_raw_floor"
    )


def test_reactive_segment_uses_frozen_overflow_material_list() -> None:
    """Reactive selection 只消费传入的 frozen overflow material list。"""

    frozen_blocks = (
        _history_block(
            "frozen-overflow-old",
            event_sequence=10,
            text="frozen overflow old material",
        ),
        _current_block("frozen-current", event_sequence=12, text="frozen current"),
    )

    selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.REACTIVE,
        input_cursor=12,
        memory_snapshot_cursor=9,
        policy_digest=_POLICY_DIGEST,
        material_blocks=frozen_blocks,
    )

    assert selection.selected_block_ids == ("frozen-overflow-old",)
    assert selection.excluded_reason_codes == {
        "frozen-current": "protected_current_input"
    }


def test_already_represented_blocks_are_not_reexpanded() -> None:
    """已被 stable fact 或 compact output 代表的 block 不再展开 raw content。"""

    blocks = (
        _history_block(
            "already-represented",
            event_sequence=1,
            text="already summarized",
            already_represented=True,
        ),
        _history_block("needs-compact", event_sequence=2, text="needs compact"),
    )

    selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=2,
        memory_snapshot_cursor=2,
        policy_digest=_POLICY_DIGEST,
        material_blocks=blocks,
    )

    assert selection.selected_block_ids == ("needs-compact",)
    assert (
        selection.excluded_reason_codes["already-represented"]
        == "already_represented"
    )


def test_material_pack_one_to_one_section_mapping_rejects_duplicate_content() -> None:
    """同一 canonical source ref set + digest 不能进入两个 LLM-facing section。"""

    snapshot = _snapshot_with_goal(
        snapshot_id="snapshot-duplicate",
        checkpoint_event_sequence=2,
        current_goal="same goal",
    )
    duplicate = run_input_material_block(
        block_id="history-duplicate",
        section=CompactMaterialSection.HISTORY_INPUT,
        kind=CompactMaterialBlockKind.RAW_USER_TURN,
        text="current_goal=same goal",
        canonical_source_refs=("snapshot-duplicate",),
        event_sequence=1,
    )
    selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=2,
        memory_snapshot_cursor=2,
        policy_digest=_POLICY_DIGEST,
        material_blocks=(duplicate,),
    )

    with pytest.raises(DuplicateMaterialSectionOwnerError):
        build_compact_material_pack(
            selected_segment=selection,
            material_blocks=(duplicate,),
            memory_snapshot=snapshot,
            inline_delta_repair_view=None,
            current_input_ref="event-current",
            current_input_text="current input",
        )


def test_current_input_anchor_does_not_duplicate_history_raw_turn() -> None:
    """当前输入 anchor 进入 C1 后不能再作为 history raw turn 出现。"""

    current_history = run_input_material_block(
        block_id="history-current",
        section=CompactMaterialSection.HISTORY_INPUT,
        kind=CompactMaterialBlockKind.RAW_USER_TURN,
        text="current input",
        canonical_source_refs=("event-current",),
        event_sequence=5,
    )
    old_history = _history_block("history-old", event_sequence=1, text="old input")
    selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.REACTIVE,
        input_cursor=5,
        memory_snapshot_cursor=4,
        policy_digest=_POLICY_DIGEST,
        material_blocks=(old_history, current_history),
    )

    pack = build_compact_material_pack(
        selected_segment=selection,
        material_blocks=(old_history, current_history),
        memory_snapshot=None,
        inline_delta_repair_view=None,
        current_input_ref="event-current",
        current_input_text="current input",
    )

    assert pack.current_input_anchor.anchor_text == "current input"
    assert tuple(block.text for block in pack.history_input) == ("old input",)


def test_snapshot_cursor_lag_requires_catchup_or_inline_delta() -> None:
    """Snapshot lag 超阈值需要 catch-up；阈值内可使用 inline delta view。"""

    lagged = _empty_snapshot("snapshot-lagged", checkpoint_event_sequence=2)
    repaired = _empty_snapshot("snapshot-repaired", checkpoint_event_sequence=4)
    strict_policy = _policy(max_lag_events_for_inline_delta=1)

    with pytest.raises(CompactMemorySnapshotRepairRequired) as exc_info:
        check_compact_memory_snapshot_cursor(
            session_id=_SESSION_ID,
            required_event_sequence=4,
            policy=strict_policy,
            snapshot=lagged,
        )

    permissive_policy = _policy(max_lag_events_for_inline_delta=2)
    result = check_compact_memory_snapshot_cursor(
        session_id=_SESSION_ID,
        required_event_sequence=4,
        policy=permissive_policy,
        snapshot=lagged,
        inline_delta_repair_view=InlineDeltaRepairMaterialView(
            snapshot=repaired,
            diagnostics=(),
        ),
    )

    assert exc_info.value.repair_request.reason.value == "snapshot_lag_over_threshold"
    assert result.snapshot.cursor.checkpoint_event_sequence == 4
    assert result.inline_delta_repair_view is not None


def test_snapshot_cursor_inline_delta_uses_inline_lag_threshold_only() -> None:
    """Inline delta repair 只受 inline lag policy 阈值约束。"""

    lagged = _empty_snapshot("snapshot-lagged", checkpoint_event_sequence=2)
    repaired = _empty_snapshot("snapshot-repaired", checkpoint_event_sequence=4)
    policy = _policy(
        max_lag_events_for_inline_delta=2,
        max_delta_repair_events=1,
    )

    result = check_compact_memory_snapshot_cursor(
        session_id=_SESSION_ID,
        required_event_sequence=4,
        policy=policy,
        snapshot=lagged,
        inline_delta_repair_view=InlineDeltaRepairMaterialView(
            snapshot=repaired,
            diagnostics=(),
        ),
    )

    assert result.snapshot.cursor.checkpoint_event_sequence == 4
    assert result.inline_delta_repair_view is not None


def test_snapshot_lag_failure_does_not_request_run_recovery() -> None:
    """Memory snapshot lag failure 不得要求 Run 进入 RECOVERING。"""

    lagged = _empty_snapshot("snapshot-lagged", checkpoint_event_sequence=2)

    with pytest.raises(CompactMemorySnapshotRepairRequired) as exc_info:
        check_compact_memory_snapshot_cursor(
            session_id=_SESSION_ID,
            required_event_sequence=4,
            policy=_policy(max_lag_events_for_inline_delta=0),
            snapshot=lagged,
        )

    assert exc_info.value.requests_run_recovery is False


def _history_block(
    block_id: str,
    *,
    event_sequence: int,
    text: str,
    already_represented: bool = False,
) -> RunInputMaterialBlock:
    """构造 history material block。

    :param block_id: block id。
    :param event_sequence: event sequence。
    :param text: 文本。
    :param already_represented: 是否已被代表。
    :returns: RunInputMaterialBlock。
    """

    return run_input_material_block(
        block_id=block_id,
        section=CompactMaterialSection.HISTORY_INPUT,
        kind=CompactMaterialBlockKind.RAW_USER_TURN,
        text=text,
        canonical_source_refs=(f"event:{block_id}",),
        event_sequence=event_sequence,
        already_represented=already_represented,
    )


def _evidence_block(
    block_id: str, *, event_sequence: int, text: str
) -> RunInputMaterialBlock:
    """构造 evidence material block。

    :param block_id: block id。
    :param event_sequence: event sequence。
    :param text: raw evidence 文本。
    :returns: RunInputMaterialBlock。
    """

    return run_input_material_block(
        block_id=block_id,
        section=CompactMaterialSection.EVIDENCE_INPUT,
        kind=CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
        text=text,
        canonical_source_refs=(f"event:{block_id}",),
        event_sequence=event_sequence,
        accepted_evidence_id=f"evidence:{block_id}",
        tool_result_event_ref=f"tool-result:{block_id}",
        tool_call_event_ref=f"tool-call:{block_id}",
        readable_tool_name="read_tool",
        readable_query_text="query",
        readable_source_text="source",
    )


def _current_block(
    block_id: str, *, event_sequence: int, text: str
) -> RunInputMaterialBlock:
    """构造 current input material block。

    :param block_id: block id。
    :param event_sequence: event sequence。
    :param text: 当前输入文本。
    :returns: RunInputMaterialBlock。
    """

    return run_input_material_block(
        block_id=block_id,
        section=CompactMaterialSection.CURRENT_INPUT_ANCHOR,
        kind=CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
        text=text,
        canonical_source_refs=(f"event:{block_id}",),
        event_sequence=event_sequence,
    )


def _policy(
    *,
    max_lag_events_for_inline_delta: int,
    max_delta_repair_events: int = 16,
) -> MemoryProjectionPolicy:
    """构造测试 memory policy。

    :param max_lag_events_for_inline_delta: inline delta lag 阈值。
    :param max_delta_repair_events: delta repair 事件预算。
    :returns: MemoryProjectionPolicy。
    """

    return MemoryProjectionPolicy(
        context_window_size=8192,
        max_pinned_items=8,
        max_evidence_backed_facts=16,
        max_working_assumptions=8,
        recent_raw_turns_floor=2,
        raw_turn_context_ratio=0.125,
        raw_turn_size_floor=256,
        raw_turn_size_cap=1024,
        history_pool_context_ratio=0.5,
        history_pool_size_floor=1024,
        history_pool_size_cap=4096,
        stable_layer_context_ratio=0.25,
        stable_layer_size_floor=512,
        stable_layer_size_cap=2048,
        max_lag_events_for_inline_delta=max_lag_events_for_inline_delta,
        max_delta_repair_events=max_delta_repair_events,
    )


def _empty_snapshot(
    snapshot_id: str, *, checkpoint_event_sequence: int
) -> ConversationMemorySnapshot:
    """构造空 memory snapshot。

    :param snapshot_id: snapshot id。
    :param checkpoint_event_sequence: cursor sequence。
    :returns: ConversationMemorySnapshot。
    """

    cursor = MemorySnapshotCursor(
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        checkpoint_event_sequence=checkpoint_event_sequence,
        checkpoint_event_id=(
            None
            if checkpoint_event_sequence == 0
            else f"event-{checkpoint_event_sequence}"
        ),
        session_id=_SESSION_ID,
    )
    snapshot_without_digest = ConversationMemorySnapshot(
        snapshot_id=snapshot_id,
        session_id=_SESSION_ID,
        cursor=cursor,
        policy_digest=digest_memory_projection_policy(
            _policy(max_lag_events_for_inline_delta=16)
        ),
        pinned_state=PinnedStateView(
            current_goal=None,
            confirmed_subjects=(),
            user_constraints=(),
            open_questions=(),
        ),
        evidence_backed_facts=(),
        working_assumptions=(),
        conversation_continuity=ConversationContinuityView(items=()),
        diagnostics=(),
        built_at=_NOW,
        snapshot_digest="pending",
    )
    return ConversationMemorySnapshot(
        snapshot_id=snapshot_without_digest.snapshot_id,
        session_id=snapshot_without_digest.session_id,
        cursor=snapshot_without_digest.cursor,
        policy_digest=snapshot_without_digest.policy_digest,
        pinned_state=snapshot_without_digest.pinned_state,
        evidence_backed_facts=snapshot_without_digest.evidence_backed_facts,
        working_assumptions=snapshot_without_digest.working_assumptions,
        conversation_continuity=snapshot_without_digest.conversation_continuity,
        diagnostics=snapshot_without_digest.diagnostics,
        built_at=snapshot_without_digest.built_at,
        snapshot_digest=calculate_memory_snapshot_digest(snapshot_without_digest),
    )


def _snapshot_with_goal(
    *, snapshot_id: str, checkpoint_event_sequence: int, current_goal: str
) -> ConversationMemorySnapshot:
    """构造带 stable goal 的 memory snapshot。

    :param snapshot_id: snapshot id。
    :param checkpoint_event_sequence: cursor sequence。
    :param current_goal: current goal。
    :returns: ConversationMemorySnapshot。
    """

    base = _empty_snapshot(
        snapshot_id,
        checkpoint_event_sequence=checkpoint_event_sequence,
    )
    snapshot_without_digest = ConversationMemorySnapshot(
        snapshot_id=base.snapshot_id,
        session_id=base.session_id,
        cursor=base.cursor,
        policy_digest=base.policy_digest,
        pinned_state=PinnedStateView(
            current_goal=current_goal,
            confirmed_subjects=(),
            user_constraints=(),
            open_questions=(),
        ),
        evidence_backed_facts=(),
        working_assumptions=(),
        conversation_continuity=ConversationContinuityView(items=()),
        diagnostics=(),
        built_at=base.built_at,
        snapshot_digest="pending",
    )
    return ConversationMemorySnapshot(
        snapshot_id=snapshot_without_digest.snapshot_id,
        session_id=snapshot_without_digest.session_id,
        cursor=snapshot_without_digest.cursor,
        policy_digest=snapshot_without_digest.policy_digest,
        pinned_state=snapshot_without_digest.pinned_state,
        evidence_backed_facts=snapshot_without_digest.evidence_backed_facts,
        working_assumptions=snapshot_without_digest.working_assumptions,
        conversation_continuity=snapshot_without_digest.conversation_continuity,
        diagnostics=snapshot_without_digest.diagnostics,
        built_at=snapshot_without_digest.built_at,
        snapshot_digest=calculate_memory_snapshot_digest(snapshot_without_digest),
    )
