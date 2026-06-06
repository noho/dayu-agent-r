"""P12.6 compact material selection 与 pack builder 测试。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from dayu.host.compact_material import (
    CompactMemorySnapshotRepairRequired,
    DuplicateMaterialSectionOwnerError,
    EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS,
    InitialEvidenceMaterial,
    InitialHistoryMaterial,
    InlineDeltaRepairMaterialView,
    RunInputMaterialBlock,
    build_initial_material_pack,
    build_compact_material_pack,
    check_compact_memory_snapshot_cursor,
    conversation_compact_input_vnext_from_material_pack,
    prompt_local_evidence_map,
    run_input_material_block,
    select_compact_segment,
)
from dayu.host.compaction import (
    CompactMaterialBlockKind,
    CompactMaterialSection,
    CompactSegmentTrigger,
)
from dayu.host.evidence import OpaqueEvidenceRef
from dayu.host.memory import (
    AnswerAnchor,
    AnswerAnchorChild,
    CONVERSATION_MEMORY_CONSUMER_ID,
    ConversationMemorySnapshotVNext,
    EvidenceFactMemoryView,
    ForwardIntent,
    ForwardIntentMemoryView,
    MemoryEvidenceBackedFactKind,
    EvidenceBackedFactView,
    MemoryIncludedReason,
    MemoryRepairReason,
    MemoryProjectionPolicy,
    MemoryProducerKind,
    MemoryProvenanceRef,
    ReferenceContinuityItem,
    MemorySizeUnits,
    MemorySnapshotCursor,
    AnswerAnchorMemoryView,
    SessionSummaryMemoryView,
    TraceMemoryView,
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
        selected_recent_window_turn_floor=1,
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


def test_vnext_snapshot_does_not_bridge_old_goal_into_previous_view() -> None:
    """vNext snapshot 不把旧 goal bridge 成 previous compacted view block。"""

    snapshot = _snapshot_with_goal(
        snapshot_id="snapshot-duplicate",
        checkpoint_event_sequence=2,
        current_goal="same goal",
    )
    duplicate = run_input_material_block(
        block_id="history-duplicate",
        section=CompactMaterialSection.TRACE_MATERIAL,
        kind=CompactMaterialBlockKind.USER_INPUT,
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

    pack = build_compact_material_pack(
        selected_segment=selection,
        material_blocks=(duplicate,),
        memory_snapshot=snapshot,
        inline_delta_repair_view=None,
        current_input_ref="event-current",
        current_input_text="current input",
    )

    assert tuple(block.text for block in pack.trace_material) == (
        "current_goal=same goal",
    )
    assert pack.current_input_anchor.anchor_text == "current input"


def test_duplicate_section_owner_raises_for_vnext_previous_and_trace_material() -> None:
    """同一 canonical content 进入两个 LLM-facing section 时必须抛错。"""

    snapshot_without_digest = replace(
        _empty_snapshot(
            "snapshot-duplicate-owner",
            checkpoint_event_sequence=2,
        ),
        session_summary_memory=SessionSummaryMemoryView(
            summary_text="duplicate readable content",
            source_refs=("event:summary",),
            event_id="event-summary",
            event_sequence=2,
            size_units=MemorySizeUnits(26),
        ),
        snapshot_digest="pending",
    )
    snapshot = replace(
        snapshot_without_digest,
        snapshot_digest=calculate_memory_snapshot_digest(snapshot_without_digest),
    )
    duplicate_trace_block = run_input_material_block(
        block_id="history-duplicate-owner",
        section=CompactMaterialSection.TRACE_MATERIAL,
        kind=CompactMaterialBlockKind.USER_INPUT,
        text="duplicate readable content",
        canonical_source_refs=("snapshot-duplicate-owner",),
        event_sequence=1,
    )
    selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=2,
        memory_snapshot_cursor=2,
        policy_digest=_POLICY_DIGEST,
        material_blocks=(duplicate_trace_block,),
        selected_recent_window_turn_floor=0,
    )

    with pytest.raises(DuplicateMaterialSectionOwnerError):
        build_compact_material_pack(
            selected_segment=selection,
            material_blocks=(duplicate_trace_block,),
            memory_snapshot=snapshot,
            inline_delta_repair_view=None,
            current_input_ref="event-current",
            current_input_text="current input",
        )


def test_current_input_anchor_does_not_duplicate_history_raw_turn() -> None:
    """当前输入 anchor 进入 C1 后不能再作为 history raw turn 出现。"""

    current_history = run_input_material_block(
        block_id="history-current",
        section=CompactMaterialSection.TRACE_MATERIAL,
        kind=CompactMaterialBlockKind.USER_INPUT,
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
    assert tuple(block.text for block in pack.trace_material) == ("old input",)


def test_conversation_compact_input_vnext_maps_material_without_citable_current_anchor() -> None:
    """vNext material input 使用新顶层 section，current input readable but not citable。"""

    pack = build_initial_material_pack(
        current_input_ref="event-current",
        current_input_text="current input",
        history_materials=(
            InitialHistoryMaterial(
                canonical_source_ref="event-user-old",
                text="old input",
                kind=CompactMaterialBlockKind.USER_INPUT,
            ),
            InitialHistoryMaterial(
                canonical_source_ref="event-answer-old",
                text="old answer",
                kind=CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
            ),
        ),
        evidence_materials=(
            InitialEvidenceMaterial(
                canonical_source_ref="evidence:accepted",
                accepted_evidence_id="evidence:accepted",
                tool_result_event_ref="event-tool-result",
                tool_call_event_ref="event-tool-call",
                readable_tool_name="fins.search",
                readable_query_text="query",
                raw_result_text="accepted evidence text",
                readable_source_text="source note",
                payload_refs=("payload:accepted",),
            ),
        ),
    )

    vnext_input = conversation_compact_input_vnext_from_material_pack(pack)
    vnext_json = vnext_input.to_json()

    assert vnext_input.current_input_anchor.anchor_label == "C1"
    assert "C1" not in vnext_input.citable_source_labels
    assert tuple(item.source_label for item in vnext_input.trace_material) == ("T1",)
    assert tuple(item.source_label for item in vnext_input.answer_material) == ("A1",)
    assert tuple(item.source_label for item in vnext_input.evidence_material) == ("E1",)
    assert isinstance(vnext_json, dict)
    assert "trace_material" in vnext_json
    assert "stable_input" not in vnext_json
    assert "history_input" not in vnext_json
    assert "evidence_input" not in vnext_json


def test_conversation_compact_input_vnext_maps_user_turn_to_trace() -> None:
    """vNext material 映射必须把 user turn 放入 trace_material。"""

    pack = build_initial_material_pack(
        current_input_ref="event-current",
        current_input_text="current input",
        history_materials=(
            InitialHistoryMaterial(
                canonical_source_ref="event-user-old",
                text="old user input",
                kind=CompactMaterialBlockKind.USER_INPUT,
            ),
            InitialHistoryMaterial(
                canonical_source_ref="event-answer-old",
                text="old assistant answer",
                kind=CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
            ),
        ),
        evidence_materials=(),
    )

    vnext_input = conversation_compact_input_vnext_from_material_pack(pack)

    assert tuple(item.text for item in vnext_input.trace_material) == ("old user input",)
    assert tuple(item.source_label for item in vnext_input.trace_material) == ("T1",)


def test_conversation_compact_input_vnext_maps_assistant_turn_to_answer() -> None:
    """vNext material 映射必须把 assistant turn 放入 answer_material。"""

    pack = build_initial_material_pack(
        current_input_ref="event-current",
        current_input_text="current input",
        history_materials=(
            InitialHistoryMaterial(
                canonical_source_ref="event-user-old",
                text="old user input",
                kind=CompactMaterialBlockKind.USER_INPUT,
            ),
            InitialHistoryMaterial(
                canonical_source_ref="event-answer-old",
                text="old assistant answer",
                kind=CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
            ),
        ),
        evidence_materials=(),
    )

    vnext_input = conversation_compact_input_vnext_from_material_pack(pack)

    assert tuple(item.answer_text for item in vnext_input.answer_material) == (
        "old assistant answer",
    )
    assert tuple(item.source_label for item in vnext_input.answer_material) == ("A1",)


def test_conversation_compact_input_vnext_does_not_map_session_summary_to_answer() -> None:
    """Session summary material 不得映射为 assistant answer_material。"""

    session_summary_block = run_input_material_block(
        block_id="memory:session-summary",
        section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
        kind=CompactMaterialBlockKind.SESSION_SUMMARY,
        text="summary text is navigation only",
        canonical_source_refs=("event-compact",),
        event_sequence=1,
    )
    answer_block = run_input_material_block(
        block_id="history:assistant-answer",
        section=CompactMaterialSection.ANSWER_MATERIAL,
        kind=CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
        text="assistant final answer",
        canonical_source_refs=("event-run-succeeded",),
        event_sequence=2,
    )
    pack = build_compact_material_pack(
        selected_segment=select_compact_segment(
            trigger_source=CompactSegmentTrigger.REACTIVE,
            input_cursor=3,
            memory_snapshot_cursor=None,
            policy_digest=_POLICY_DIGEST,
            material_blocks=(session_summary_block, answer_block),
        ),
        material_blocks=(session_summary_block, answer_block),
        memory_snapshot=None,
        inline_delta_repair_view=None,
        current_input_ref="event-current",
        current_input_text="current input",
    )

    vnext_input = conversation_compact_input_vnext_from_material_pack(pack)

    assert tuple(item.answer_text for item in vnext_input.answer_material) == (
        "assistant final answer",
    )
    assert all(
        item.answer_text != "summary text is navigation only"
        for item in vnext_input.answer_material
    )


def test_conversation_compact_input_vnext_maps_evidence_to_evidence_material() -> None:
    """vNext material 映射必须把 accepted evidence 放入 evidence_material。"""

    pack = build_initial_material_pack(
        current_input_ref="event-current",
        current_input_text="current input",
        history_materials=(),
        evidence_materials=(
            InitialEvidenceMaterial(
                canonical_source_ref="evidence:accepted",
                accepted_evidence_id="evidence:accepted",
                tool_result_event_ref="event-tool-result",
                tool_call_event_ref="event-tool-call",
                readable_tool_name="fins.search",
                readable_query_text="revenue query",
                raw_result_text="accepted evidence text",
                readable_source_text="source note",
                payload_refs=("payload:accepted",),
            ),
        ),
    )

    vnext_input = conversation_compact_input_vnext_from_material_pack(pack)

    assert tuple(item.source_label for item in vnext_input.evidence_material) == ("E1",)
    assert tuple(item.response_text for item in vnext_input.evidence_material) == (
        "accepted evidence text",
    )
    assert tuple(item.tool_name for item in vnext_input.evidence_material) == (
        "fins.search",
    )


def test_conversation_compact_input_vnext_previous_view_maps_stable_blocks() -> None:
    """vNext previous view 必须映射五类 stable memory blocks。"""

    snapshot = _snapshot_with_stable_blocks(
        snapshot_id="snapshot-stable-blocks",
        checkpoint_event_sequence=2,
    )
    selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=2,
        memory_snapshot_cursor=2,
        policy_digest=_POLICY_DIGEST,
        material_blocks=(),
    )
    pack = build_compact_material_pack(
        selected_segment=selection,
        material_blocks=(),
        memory_snapshot=snapshot,
        inline_delta_repair_view=None,
        current_input_ref="event-current",
        current_input_text="current input",
    )

    vnext_input = conversation_compact_input_vnext_from_material_pack(pack)

    previous_view = vnext_input.previous_compacted_view
    assert previous_view is not None
    assert previous_view.session_summary == "summary text"
    assert tuple(
        item.claim_text
        for item in previous_view.evidence_backed_facts
    ) == (
        "fact=claim_text=Revenue increased year over year; "
        "evidence_refs=evidence:accepted; evidence_kind=derived_from_evidence",
    )
    assert tuple(
        item.anchor_title for item in previous_view.answer_anchors
    ) == ("answer title",)
    assert tuple(
        item.anchor_items[0].display_text
        for item in previous_view.answer_anchors
    ) == ("answer title",)
    assert tuple(item.text for item in previous_view.forward_intents) == (
        "follow up",
    )
    assert tuple(item.intent_type.value for item in previous_view.forward_intents) == (
        "next_step_note",
    )
    assert tuple(item.status.value for item in previous_view.forward_intents) == (
        "open",
    )
    assert tuple(item.text for item in previous_view.reference_continuity_items) == (
        "second factor",
    )
    assert tuple(
        item.reason.value for item in previous_view.reference_continuity_items
    ) == ("local_reference",)


def test_conversation_compact_input_vnext_maps_user_visible_state_to_trace() -> None:
    """vNext trace material 必须包含用户可见 Run 状态。"""

    pack = build_initial_material_pack(
        current_input_ref="event-current",
        current_input_text="current input",
        history_materials=(
            InitialHistoryMaterial(
                canonical_source_ref="event-state",
                text="run is waiting for user confirmation",
                kind=CompactMaterialBlockKind.USER_VISIBLE_RUN_STATE,
            ),
        ),
        evidence_materials=(),
    )

    vnext_input = conversation_compact_input_vnext_from_material_pack(pack)

    assert tuple(item.text for item in vnext_input.trace_material) == (
        "run is waiting for user confirmation",
    )
    assert tuple(item.trace_kind.value for item in vnext_input.trace_material) == (
        "user_visible_run_state",
    )


def test_conversation_compact_input_vnext_current_anchor_not_citable() -> None:
    """vNext material 映射必须保持 current_input_anchor readable but not citable。"""

    pack = build_initial_material_pack(
        current_input_ref="event-current",
        current_input_text="current input",
        history_materials=(
            InitialHistoryMaterial(
                canonical_source_ref="event-user-old",
                text="old user input",
                kind=CompactMaterialBlockKind.USER_INPUT,
            ),
        ),
        evidence_materials=(),
    )

    vnext_input = conversation_compact_input_vnext_from_material_pack(pack)

    assert vnext_input.current_input_anchor.anchor_label == "C1"
    assert vnext_input.current_input_anchor.text == "current input"
    assert "C1" not in vnext_input.citable_source_labels
    current_anchor_section = vnext_input.source_section("C1")
    assert current_anchor_section is not None
    assert current_anchor_section.value == "current_input_anchor"


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


def test_snapshot_cursor_missing_inline_delta_view_has_accurate_reason() -> None:
    """小滞后但缺少 inline repair view 时不得伪装成大滞后。"""

    lagged = _empty_snapshot("snapshot-lagged", checkpoint_event_sequence=2)

    with pytest.raises(CompactMemorySnapshotRepairRequired) as exc_info:
        check_compact_memory_snapshot_cursor(
            session_id=_SESSION_ID,
            required_event_sequence=4,
            policy=_policy(max_lag_events_for_inline_delta=2),
            snapshot=lagged,
            inline_delta_repair_view=None,
        )

    assert (
        exc_info.value.repair_request.reason
        is MemoryRepairReason.INLINE_DELTA_REPAIR_VIEW_MISSING
    )


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


def test_evidence_labels_are_prompt_local_and_map_to_canonical_evidence() -> None:
    """Prompt-local evidence labels 必须映射到 canonical accepted evidence。"""

    evidence = _evidence_block(
        "evidence-map",
        event_sequence=3,
        text="digest checked raw evidence",
        payload_refs=("payload:evidence-map",),
        artifact_refs=("artifact:evidence-map",),
        source_locator_refs=(
            OpaqueEvidenceRef(ref_kind="locator", ref_id="evidence-map", digest=None),
        ),
    )
    selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=3,
        memory_snapshot_cursor=3,
        policy_digest=_POLICY_DIGEST,
        material_blocks=(evidence,),
    )

    pack = build_compact_material_pack(
        selected_segment=selection,
        material_blocks=(evidence,),
        memory_snapshot=None,
        inline_delta_repair_view=None,
        current_input_ref="event-current",
        current_input_text="current input",
    )
    evidence_map = prompt_local_evidence_map(pack)

    assert pack.evidence_labels == ("E1",)
    assert tuple(evidence_map) == ("E1",)
    assert evidence_map["E1"].accepted_evidence_id == "evidence:evidence-map"
    assert evidence_map["E1"].tool_result_event_ref == "tool-result:evidence-map"
    assert evidence_map["E1"].tool_call_event_ref == "tool-call:evidence-map"
    assert evidence_map["E1"].payload_refs == ("payload:evidence-map",)
    assert evidence_map["E1"].artifact_refs == ("artifact:evidence-map",)
    assert evidence_map["E1"].source_locator_refs == (
        OpaqueEvidenceRef(ref_kind="locator", ref_id="evidence-map", digest=None),
    )


def test_single_large_evidence_block_is_chunked_under_same_provenance() -> None:
    """单个超大 evidence block 拆成 E1.1/E1.2 并保留同一 canonical provenance。"""

    large_text = "A" * (EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS + 7)
    evidence = _evidence_block(
        "evidence-large",
        event_sequence=3,
        text=large_text,
        payload_refs=("payload:evidence-large",),
    )
    selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.REACTIVE,
        input_cursor=3,
        memory_snapshot_cursor=3,
        policy_digest=_POLICY_DIGEST,
        material_blocks=(evidence,),
    )

    pack = build_compact_material_pack(
        selected_segment=selection,
        material_blocks=(evidence,),
        memory_snapshot=None,
        inline_delta_repair_view=None,
        current_input_ref="event-current",
        current_input_text="current input",
    )
    evidence_map = prompt_local_evidence_map(pack)

    assert pack.evidence_labels == ("E1.1", "E1.2")
    assert tuple(block.raw_result_text for block in pack.evidence_material) == (
        "A" * EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS,
        "A" * 7,
    )
    assert evidence_map["E1.1"].accepted_evidence_id == "evidence:evidence-large"
    assert evidence_map["E1.2"].accepted_evidence_id == "evidence:evidence-large"
    assert evidence_map["E1.1"].chunk_parent_label == "E1"
    assert evidence_map["E1.2"].chunk_parent_label == "E1"
    assert evidence_map["E1.1"].chunk_ordinal == 1
    assert evidence_map["E1.2"].chunk_ordinal == 2


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
        section=CompactMaterialSection.TRACE_MATERIAL,
        kind=CompactMaterialBlockKind.USER_INPUT,
        text=text,
        canonical_source_refs=(f"event:{block_id}",),
        event_sequence=event_sequence,
        already_represented=already_represented,
    )


def _evidence_block(
    block_id: str,
    *,
    event_sequence: int,
    text: str,
    payload_refs: tuple[str, ...] = ("payload:test",),
    artifact_refs: tuple[str, ...] = (),
    source_locator_refs: tuple[OpaqueEvidenceRef, ...] = (),
) -> RunInputMaterialBlock:
    """构造 evidence material block。

    :param block_id: block id。
    :param event_sequence: event sequence。
    :param text: raw evidence 文本。
    :param payload_refs: payload / artifact refs。
    :param artifact_refs: artifact refs。
    :param source_locator_refs: source locator refs。
    :returns: RunInputMaterialBlock。
    """

    return run_input_material_block(
        block_id=block_id,
        section=CompactMaterialSection.EVIDENCE_MATERIAL,
        kind=CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
        text=text,
        canonical_source_refs=(f"event:{block_id}",),
        event_sequence=event_sequence,
        accepted_evidence_id=f"evidence:{block_id}",
        tool_result_event_ref=f"tool-result:{block_id}",
        tool_call_event_ref=f"tool-call:{block_id}",
        payload_refs=payload_refs,
        artifact_refs=artifact_refs,
        source_locator_refs=source_locator_refs,
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
        selected_recent_window_item_cap=8,
        selected_recent_window_char_cap=2048,
        selected_recent_window_turn_floor=2,
        fallback_selected_recent_window_item_cap=4,
        fallback_selected_recent_window_char_cap=1024,
        evidence_fact_item_cap=16,
        evidence_fact_char_cap=4096,
        evidence_fact_floor=1,
        session_summary_char_cap=1024,
        answer_anchor_item_cap=4,
        answer_anchor_char_cap=1024,
        forward_intent_item_cap=4,
        forward_intent_char_cap=1024,
        reference_continuity_item_cap=4,
        reference_continuity_char_cap=1024,
        reference_continuity_item_floor=0,
        max_lag_events_for_inline_delta=max_lag_events_for_inline_delta,
        max_delta_repair_events=max_delta_repair_events,
        policy_ref="compact-material-test",
    )


def _empty_snapshot(
    snapshot_id: str, *, checkpoint_event_sequence: int
) -> ConversationMemorySnapshotVNext:
    """构造空 memory snapshot。

    :param snapshot_id: snapshot id。
    :param checkpoint_event_sequence: cursor sequence。
    :returns: ConversationMemorySnapshotVNext。
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
    snapshot_without_digest = ConversationMemorySnapshotVNext(
        schema_version="conversation_memory_snapshot_v1",
        snapshot_id=snapshot_id,
        session_id=_SESSION_ID,
        cursor=cursor,
        policy_digest=digest_memory_projection_policy(
            _policy(max_lag_events_for_inline_delta=16)
        ),
        latest_compaction_event_ref=None,
        trace_memory=TraceMemoryView(
            selected_recent_window=(),
            reference_continuity_items=(),
        ),
        evidence_fact_memory=EvidenceFactMemoryView(
            evidence_backed_facts=(),
            recent_evidence_items=(),
        ),
        session_summary_memory=SessionSummaryMemoryView(
            summary_text=None,
            source_refs=(),
            event_id=None,
            event_sequence=None,
            size_units=MemorySizeUnits(0),
        ),
        answer_anchor_memory=AnswerAnchorMemoryView(anchors=()),
        forward_intent_memory=ForwardIntentMemoryView(intents=()),
        diagnostics=(),
        built_at=_NOW,
        snapshot_digest="pending",
    )
    return replace(
        snapshot_without_digest,
        snapshot_digest=calculate_memory_snapshot_digest(snapshot_without_digest),
    )


def _snapshot_with_goal(
    *, snapshot_id: str, checkpoint_event_sequence: int, current_goal: str
) -> ConversationMemorySnapshotVNext:
    """构造带 stable goal 的 memory snapshot。

    :param snapshot_id: snapshot id。
    :param checkpoint_event_sequence: cursor sequence。
    :param current_goal: current goal。
    :returns: ConversationMemorySnapshotVNext。
    """

    base = _empty_snapshot(
        snapshot_id,
        checkpoint_event_sequence=checkpoint_event_sequence,
    )
    del current_goal
    return base


def _snapshot_with_goal_and_fact(
    *,
    snapshot_id: str,
    checkpoint_event_sequence: int,
    current_goal: str,
    claim_text: str,
) -> ConversationMemorySnapshotVNext:
    """构造同时包含非 fact stable block 与 evidence fact 的 snapshot。

    :param snapshot_id: snapshot id。
    :param checkpoint_event_sequence: cursor sequence。
    :param current_goal: current goal。
    :param claim_text: evidence-backed fact claim text。
    :returns: ConversationMemorySnapshotVNext。
    """

    base = _snapshot_with_goal(
        snapshot_id=snapshot_id,
        checkpoint_event_sequence=checkpoint_event_sequence,
        current_goal=current_goal,
    )
    snapshot_without_digest = replace(
        base,
        evidence_fact_memory=EvidenceFactMemoryView(
            evidence_backed_facts=(
            EvidenceBackedFactView(
                item_id="memory-item:fact-test",
                claim_text=claim_text,
                evidence_kind=MemoryEvidenceBackedFactKind.DERIVED_FROM_EVIDENCE,
                evidence_refs=("evidence:accepted",),
                provenance=MemoryProvenanceRef(
                    producer_kind=MemoryProducerKind.HOST_PROJECTION,
                    producer_name="conversation_memory",
                    event_id="event-memory-compact",
                    event_sequence=checkpoint_event_sequence,
                    run_id="run-memory",
                    attempt_id=None,
                    execution_id=None,
                    tool_result_ref="event-tool-result",
                    payload_ref="compact-artifact:test",
                    digest_ref="digest:fact-test",
                    source_refs=(),
                ),
                extraction_operation_ref="event:event-memory-compact",
                compact_artifact_ref="compact-artifact:test",
                candidate_id="candidate:fact-test",
                included_reason=MemoryIncludedReason.EVIDENCE_BACKED_FACT,
                excluded_reason=None,
                size_units=MemorySizeUnits(units=7),
            ),
            ),
            recent_evidence_items=(),
        ),
        snapshot_digest="pending",
    )
    return replace(
        snapshot_without_digest,
        snapshot_digest=calculate_memory_snapshot_digest(snapshot_without_digest),
    )


def _snapshot_with_stable_blocks(
    *, snapshot_id: str, checkpoint_event_sequence: int
) -> ConversationMemorySnapshotVNext:
    """构造包含五类 stable memory block 的 snapshot。

    :param snapshot_id: snapshot id。
    :param checkpoint_event_sequence: cursor sequence。
    :returns: ConversationMemorySnapshotVNext。
    """

    base = _snapshot_with_goal_and_fact(
        snapshot_id=snapshot_id,
        checkpoint_event_sequence=checkpoint_event_sequence,
        current_goal="unused",
        claim_text="Revenue increased year over year",
    )
    snapshot_without_digest = replace(
        base,
        session_summary_memory=SessionSummaryMemoryView(
            summary_text="summary text",
            source_refs=("event:summary",),
            event_id="event-summary",
            event_sequence=checkpoint_event_sequence,
            size_units=MemorySizeUnits(12),
        ),
        answer_anchor_memory=AnswerAnchorMemoryView(
            anchors=(
                AnswerAnchor(
                    item_id="memory-item:answer-anchor",
                    anchor_title="answer title",
                    anchor_items=(
                        AnswerAnchorChild(
                            display_text="first point",
                            ordinal=1,
                        ),
                    ),
                    source_refs=("event:answer",),
                    event_id="event-answer",
                    event_sequence=checkpoint_event_sequence,
                    size_units=MemorySizeUnits(12),
                ),
            )
        ),
        forward_intent_memory=ForwardIntentMemoryView(
            intents=(
                ForwardIntent(
                    item_id="memory-item:forward-intent",
                    intent_type="next_step_note",
                    text="follow up",
                    status="open",
                    source_refs=("event:intent",),
                    event_id="event-intent",
                    event_sequence=checkpoint_event_sequence,
                    size_units=MemorySizeUnits(9),
                ),
            )
        ),
        trace_memory=TraceMemoryView(
            selected_recent_window=(),
            reference_continuity_items=(
                ReferenceContinuityItem(
                    item_id="memory-item:reference-continuity",
                    text="second factor",
                    reason="local_reference",
                    source_refs=("event:reference",),
                    event_id="event-reference",
                    event_sequence=checkpoint_event_sequence,
                    size_units=MemorySizeUnits(13),
                ),
            ),
        ),
        snapshot_digest="pending",
    )
    return replace(
        snapshot_without_digest,
        snapshot_digest=calculate_memory_snapshot_digest(snapshot_without_digest),
    )
