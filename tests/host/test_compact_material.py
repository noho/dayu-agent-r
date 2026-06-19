"""P12.6 compact material selection 与 pack builder 测试。"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.api import RunStatus
from dayu.host.compact_material import (
    CompactMaterialSourceBoundary,
    CompactMaterialPack,
    CompactMemorySnapshotRepairRequired,
    DuplicateMaterialSectionOwnerError,
    InitialEvidenceMaterial,
    InitialHistoryMaterial,
    InlineDeltaRepairMaterialView,
    PreDispatchCompactMaterialView,
    RunInputMaterialBlock,
    build_initial_material_pack,
    build_compact_material_pack,
    build_pre_dispatch_compact_material_view,
    check_compact_memory_snapshot_cursor,
    conversation_compact_input_vnext_from_material_pack,
    degrade_previous_compacted_view_for_recovery,
    normalized_material_text,
    prompt_local_evidence_map,
    run_input_material_block,
    select_compact_segment,
)
from dayu.host.compaction import (
    AnswerAnchorCandidateVNext,
    AnswerAnchorChildVNext,
    CompactMaterialBlock,
    CompactQualityCheckResultVNext,
    CompactMaterialBlockKind,
    CompactMaterialSection,
    CompactSegmentTrigger,
    ConversationCompactInputVNext,
    ConversationCompactOutputVNext,
    EvidenceBackedFactCandidateVNext,
    FactEvidenceKindVNext,
    ForwardIntentCandidateVNext,
    ForwardIntentStatusVNext,
    ForwardIntentTypeVNext,
    ReferenceContinuityCandidateVNext,
    ReferenceContinuityReasonVNext,
    SessionSummaryCandidateVNext,
)
from dayu.host.context_events import build_context_compacted_payload
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventLogRow,
    EventLogStore,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.payload import (
    PayloadStore,
    SQLitePayloadFormat,
    SQLitePayloadWriteRequest,
)
from dayu.host.durable.schema import (
    TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
    TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT,
)
from dayu.host.durable.state import RunRow
from dayu.host.durable.transaction import HostTransaction
from dayu.host.evidence import OpaqueEvidenceRef
from dayu.host.evidence import (
    AcceptedEvidenceEnvelope,
    AcceptedEvidenceResultRef,
    AcceptedEvidenceToolQuery,
    accepted_evidence_envelope_to_json_value,
)
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
_DIGEST = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_LONG_EVIDENCE_TEXT_CHAR_COUNT = 5000
_CURRENT_VNEXT_MATERIAL_KEYS = (
    "previous_compacted_view",
    "trace_material",
    "evidence_material",
    "answer_material",
    "current_input_anchor",
    "instruction",
)
_VNEXT_TOP_LEVEL_KEYS = ("schema_version", *_CURRENT_VNEXT_MATERIAL_KEYS)


class _MaterialPackShape(NamedTuple):
    """测试用 compact material pack prompt-local shape 摘要。"""

    previous_labels: tuple[str, ...]
    trace_labels: tuple[str, ...]
    evidence_labels: tuple[str, ...]
    answer_labels: tuple[str, ...]
    current_anchor_label: str
    citable_source_labels: tuple[str, ...]


class _VNextInputShape(NamedTuple):
    """测试用 vNext compactor input JSON shape 摘要。"""

    top_level_keys: tuple[str, ...]
    previous_count: int
    trace_count: int
    evidence_count: int
    answer_count: int
    current_anchor_label: str


def test_normalized_material_text_preserves_line_boundaries() -> None:
    """material 规范化按行折叠空白并保留非空行边界。"""

    assert normalized_material_text(" first\tline \n\n second   line ") == (
        "first line\nsecond line"
    )


def test_normalized_material_text_rejects_blank_text() -> None:
    """纯空白 material 文本不可生成有效 material digest。"""

    with pytest.raises(ValueError, match="text must be non-empty after normalization"):
        normalized_material_text(" \n\t ")


def _material_pack_shape(pack: CompactMaterialPack) -> _MaterialPackShape:
    """返回 compact material pack 的 prompt-local label shape。

    :param pack: compact material pack。
    :returns: 测试用 section label 摘要。
    """

    return _MaterialPackShape(
        previous_labels=tuple(
            block.block_label for block in pack.previous_compacted_view
        ),
        trace_labels=tuple(block.block_label for block in pack.trace_material),
        evidence_labels=tuple(
            block.evidence_label for block in pack.evidence_material
        ),
        answer_labels=tuple(block.block_label for block in pack.answer_material),
        current_anchor_label=pack.current_input_anchor.anchor_label,
        citable_source_labels=(
            *tuple(block.block_label for block in pack.previous_compacted_view),
            *tuple(block.block_label for block in pack.trace_material),
            *tuple(block.evidence_label for block in pack.evidence_material),
            *tuple(block.block_label for block in pack.answer_material),
        ),
    )


def _assert_material_pack_shape(
    pack: CompactMaterialPack, *, expected: _MaterialPackShape
) -> None:
    """断言 compact material pack 的 section / prompt-local label shape。

    :param pack: compact material pack。
    :param expected: 期望 shape。
    :returns: ``None``。
    :raises AssertionError: section 或 label shape 不符合预期时抛出。
    """

    observed = _material_pack_shape(pack)
    assert (
        observed == expected
    ), f"material pack prompt-local label shape mismatch: expected={expected!r}, observed={observed!r}"


def _vnext_input_shape(
    vnext_input: ConversationCompactInputVNext,
) -> _VNextInputShape:
    """返回 vNext compactor input 的顶层 JSON / section count shape。

    :param vnext_input: vNext compactor input。
    :returns: 测试用 vNext input shape。
    :raises AssertionError: vNext input 未输出 JSON object 时抛出。
    """

    vnext_json = vnext_input.to_json()
    assert isinstance(vnext_json, dict), "vNext material JSON must be an object"
    previous_view = vnext_input.previous_compacted_view
    previous_count = 0
    if previous_view is not None:
        previous_count = (
            (1 if previous_view.session_summary is not None else 0)
            + len(previous_view.evidence_backed_facts)
            + len(previous_view.answer_anchors)
            + len(previous_view.forward_intents)
            + len(previous_view.reference_continuity_items)
        )
    return _VNextInputShape(
        top_level_keys=tuple(vnext_json),
        previous_count=previous_count,
        trace_count=len(vnext_input.trace_material),
        evidence_count=len(vnext_input.evidence_material),
        answer_count=len(vnext_input.answer_material),
        current_anchor_label=vnext_input.current_input_anchor.anchor_label,
    )


def _assert_vnext_input_shape(
    vnext_input: ConversationCompactInputVNext, *, expected: _VNextInputShape
) -> None:
    """断言 vNext compactor input 的 section / top-level key shape。

    :param vnext_input: vNext compactor input。
    :param expected: 期望 shape。
    :returns: ``None``。
    :raises AssertionError: 顶层 JSON key 或 section count 不符合预期时抛出。
    """

    observed = _vnext_input_shape(vnext_input)
    assert (
        observed == expected
    ), f"vNext material section shape mismatch: expected={expected!r}, observed={observed!r}"


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
        _history_block(
            "history-old",
            event_sequence=1,
            text="old user",
            turn_group_id="run-old",
        ),
        _history_block(
            "history-recent",
            event_sequence=3,
            text="recent user",
            turn_group_id="run-recent",
        ),
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


def test_proactive_segment_recent_floor_uses_turn_groups() -> None:
    """Recent floor 按 Host Run group 保护多 block，而不是 raw block count。"""

    blocks = (
        _history_block(
            "run-old-user",
            event_sequence=1,
            text="old user",
            turn_group_id="run-old",
        ),
        _history_block(
            "run-mid-user",
            event_sequence=2,
            text="mid user",
            turn_group_id="run-mid",
        ),
        _evidence_block(
            "run-mid-evidence",
            event_sequence=3,
            text="mid evidence",
            turn_group_id="run-mid",
        ),
        _history_block(
            "run-new-user",
            event_sequence=4,
            text="new user",
            turn_group_id="run-new",
        ),
        _history_block(
            "run-new-answer",
            event_sequence=5,
            text="new answer",
            kind=CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
            turn_group_id="run-new",
        ),
        _current_block("current", event_sequence=6, text="current user"),
    )

    selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=6,
        memory_snapshot_cursor=5,
        policy_digest=_POLICY_DIGEST,
        material_blocks=blocks,
        selected_recent_window_turn_floor=2,
    )

    assert selection.selected_block_ids == ("run-old-user",)
    assert selection.excluded_reason_codes["run-mid-user"] == "protected_recent_raw_floor"
    assert (
        selection.excluded_reason_codes["run-mid-evidence"]
        == "protected_recent_raw_floor"
    )
    assert selection.excluded_reason_codes["run-new-user"] == "protected_recent_raw_floor"
    assert (
        selection.excluded_reason_codes["run-new-answer"]
        == "protected_recent_raw_floor"
    )


def test_proactive_segment_recent_floor_rejects_missing_turn_group_id() -> None:
    """floor 依赖的 eligible block 缺 turn_group_id 时不静默跳过。"""

    blocks = (
        _history_block(
            "history-missing-group",
            event_sequence=1,
            text="missing group",
            turn_group_id=None,
        ),
        _current_block("current", event_sequence=2, text="current user"),
    )

    with pytest.raises(ValueError, match="missing turn_group_id"):
        select_compact_segment(
            trigger_source=CompactSegmentTrigger.PROACTIVE,
            input_cursor=2,
            memory_snapshot_cursor=1,
            policy_digest=_POLICY_DIGEST,
            material_blocks=blocks,
            selected_recent_window_turn_floor=1,
        )


def test_recovery_segment_selection_enforces_fallback_item_cap() -> None:
    """S4 tier 1/3 selection 按 fallback item cap whole-drop。"""

    blocks = (
        _history_block("history-a", event_sequence=1, text="history a"),
        _history_block("history-b", event_sequence=2, text="history b"),
        _current_block("current", event_sequence=3, text="current user"),
    )

    selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=3,
        memory_snapshot_cursor=None,
        policy_digest=_POLICY_DIGEST,
        material_blocks=blocks,
        max_selected_size_units=1024,
        max_selected_item_count=1,
    )

    assert selection.selected_block_ids == ("history-a",)
    assert selection.excluded_reason_codes["history-b"] == "budget_limit"


def test_recovery_segment_selection_does_not_use_later_block_to_evade_char_cap() -> None:
    """S4 strict cap 首个 block 超预算后不选择更晚小 block 绕过顺序。"""

    blocks = (
        _history_block("history-large", event_sequence=1, text="large material"),
        _history_block("history-small", event_sequence=2, text="x"),
        _current_block("current", event_sequence=3, text="current user"),
    )

    selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=3,
        memory_snapshot_cursor=None,
        policy_digest=_POLICY_DIGEST,
        material_blocks=blocks,
        max_selected_size_units=3,
        max_selected_item_count=2,
    )

    assert selection.selected_block_ids == ()
    assert selection.excluded_reason_codes["history-large"] == "budget_limit"
    assert selection.excluded_reason_codes["history-small"] == "budget_limit"


def test_degrade_previous_compacted_view_keeps_highest_priority_section_exact() -> None:
    """Tier 2 只保留最高优先级 section，文本 byte-exact 不改写。"""

    previous = (
        _previous_compact_block(
            label="P5",
            kind=CompactMaterialBlockKind.SESSION_SUMMARY,
            text="summary must drop whole",
        ),
        _previous_compact_block(
            label="P3",
            kind=CompactMaterialBlockKind.ANSWER_ANCHOR,
            text="answer must drop whole",
        ),
        _previous_compact_block(
            label="P1",
            kind=CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
            text="fact must stay byte exact",
        ),
        _previous_compact_block(
            label="P4",
            kind=CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
            text="second fact must stay byte exact",
        ),
        _previous_compact_block(
            label="P2",
            kind=CompactMaterialBlockKind.REFERENCE_CONTINUITY,
            text="reference must drop whole",
        ),
    )

    degraded = degrade_previous_compacted_view_for_recovery(previous)

    assert tuple(block.block_label for block in degraded) == ("P1", "P4")
    assert tuple(block.text for block in degraded) == (
        "fact must stay byte exact",
        "second fact must stay byte exact",
    )


def test_degrade_previous_compacted_view_sorts_source_sequences_descending() -> None:
    """Tier 2 同 section 全有 source sequence 时按最大 sequence 降序。"""

    previous = (
        _previous_compact_block(
            label="P1",
            kind=CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
            text="older fact remains exact",
            canonical_source_refs=("eventlog-seq:10",),
        ),
        _previous_compact_block(
            label="P2",
            kind=CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
            text="newer fact remains exact",
            canonical_source_refs=("eventlog-seq:30",),
        ),
        _previous_compact_block(
            label="P3",
            kind=CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
            text="middle fact remains exact",
            canonical_source_refs=("eventlog-seq:20",),
        ),
        _previous_compact_block(
            label="P4",
            kind=CompactMaterialBlockKind.SESSION_SUMMARY,
            text="lower priority summary drops whole",
            canonical_source_refs=("eventlog-seq:40",),
        ),
    )

    degraded = degrade_previous_compacted_view_for_recovery(previous)

    assert tuple(block.block_label for block in degraded) == ("P2", "P3", "P1")
    assert tuple(block.text for block in degraded) == (
        "newer fact remains exact",
        "middle fact remains exact",
        "older fact remains exact",
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

    snapshot = _empty_snapshot(
        "snapshot-duplicate",
        checkpoint_event_sequence=2,
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

    _assert_material_pack_shape(
        pack,
        expected=_MaterialPackShape(
            previous_labels=(),
            trace_labels=("T1",),
            evidence_labels=("E1",),
            answer_labels=("A1",),
            current_anchor_label="C1",
            citable_source_labels=("T1", "E1", "A1"),
        ),
    )
    _assert_vnext_input_shape(
        vnext_input,
        expected=_VNextInputShape(
            top_level_keys=_VNEXT_TOP_LEVEL_KEYS,
            previous_count=0,
            trace_count=1,
            evidence_count=1,
            answer_count=1,
            current_anchor_label="C1",
        ),
    )
    assert "C1" not in vnext_input.citable_source_labels
    assert tuple(item.source_label for item in vnext_input.trace_material) == ("T1",)
    assert tuple(item.source_label for item in vnext_input.answer_material) == ("A1",)
    assert tuple(item.source_label for item in vnext_input.evidence_material) == ("E1",)
    assert isinstance(vnext_json, dict)
    for key in _CURRENT_VNEXT_MATERIAL_KEYS:
        assert key in vnext_json, f"vNext material JSON missing current key: {key}"
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

    long_evidence_text = "accepted evidence text " * 250
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
                raw_result_text=long_evidence_text,
                readable_source_text="source note",
                payload_refs=("payload:accepted",),
            ),
        ),
    )

    vnext_input = conversation_compact_input_vnext_from_material_pack(pack)

    assert tuple(item.source_label for item in vnext_input.evidence_material) == ("E1",)
    assert pack.evidence_labels == ("E1",)
    assert tuple(block.raw_result_text for block in pack.evidence_material) == (
        long_evidence_text,
    )
    assert tuple(item.response_text for item in vnext_input.evidence_material) == (
        long_evidence_text,
    )
    assert tuple(item.tool_name for item in vnext_input.evidence_material) == (
        "fins.search",
    )
    assert "E1.1" not in vnext_input.citable_source_labels
    assert "E1.2" not in vnext_input.citable_source_labels


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


def test_conversation_compact_input_vnext_preserves_previous_multi_record_blocks() -> None:
    """previous compacted view 多记录 block 往返时必须保留记录边界。"""

    base = _snapshot_with_stable_blocks(
        snapshot_id="snapshot-stable-multi-record-blocks",
        checkpoint_event_sequence=2,
    )
    snapshot_without_digest = replace(
        base,
        forward_intent_memory=ForwardIntentMemoryView(
            intents=(
                ForwardIntent(
                    item_id="memory-item:forward-intent-1",
                    intent_type="next_step_note",
                    text="follow up one",
                    status="open",
                    source_refs=("event:intent:1",),
                    event_id="event-intent-1",
                    event_sequence=2,
                    size_units=MemorySizeUnits(13),
                ),
                ForwardIntent(
                    item_id="memory-item:forward-intent-2",
                    intent_type="pending_user_visible_task",
                    text="follow up two\nwith wrapped source text",
                    status="superseded",
                    source_refs=("event:intent:2",),
                    event_id="event-intent-2",
                    event_sequence=2,
                    size_units=MemorySizeUnits(38),
                ),
            )
        ),
        trace_memory=TraceMemoryView(
            selected_recent_window=(),
            reference_continuity_items=(
                ReferenceContinuityItem(
                    item_id="memory-item:reference-continuity-1",
                    text="first reference",
                    reason="local_reference",
                    source_refs=("event:reference:1",),
                    event_id="event-reference-1",
                    event_sequence=2,
                    size_units=MemorySizeUnits(15),
                ),
                ReferenceContinuityItem(
                    item_id="memory-item:reference-continuity-2",
                    text="second reference\nwith wrapped source text",
                    reason="recent_state",
                    source_refs=("event:reference:2",),
                    event_id="event-reference-2",
                    event_sequence=2,
                    size_units=MemorySizeUnits(41),
                ),
            ),
        ),
        snapshot_digest="pending",
    )
    snapshot = replace(
        snapshot_without_digest,
        snapshot_digest=calculate_memory_snapshot_digest(snapshot_without_digest),
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
    assert tuple(item.text for item in previous_view.forward_intents) == (
        "follow up one",
        "follow up two with wrapped source text",
    )
    assert tuple(item.intent_type.value for item in previous_view.forward_intents) == (
        "next_step_note",
        "pending_user_visible_task",
    )
    assert tuple(item.status.value for item in previous_view.forward_intents) == (
        "open",
        "superseded",
    )
    assert tuple(item.text for item in previous_view.reference_continuity_items) == (
        "first reference",
        "second reference with wrapped source text",
    )
    assert tuple(item.reason.value for item in previous_view.reference_continuity_items) == (
        "local_reference",
        "recent_state",
    )


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


def test_single_large_evidence_block_stays_whole_with_same_provenance() -> None:
    """单个超大 evidence block 默认不拆分，并保留 canonical provenance。"""

    large_text = "A" * _LONG_EVIDENCE_TEXT_CHAR_COUNT
    locator_ref = OpaqueEvidenceRef(ref_kind="locator", ref_id="large", digest=None)
    evidence = _evidence_block(
        "evidence-large",
        event_sequence=3,
        text=large_text,
        payload_refs=("payload:evidence-large",),
        artifact_refs=("artifact:evidence-large",),
        source_locator_refs=(locator_ref,),
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

    _assert_material_pack_shape(
        pack,
        expected=_MaterialPackShape(
            previous_labels=(),
            trace_labels=(),
            evidence_labels=("E1",),
            answer_labels=(),
            current_anchor_label="C1",
            citable_source_labels=("E1",),
        ),
    )
    assert pack.evidence_labels == ("E1",)
    assert tuple(block.raw_result_text for block in pack.evidence_material) == (large_text,)
    assert tuple(block.content_digest for block in pack.evidence_material) == (
        sha256_digest_json({"text": large_text}),
    )
    assert "E1.1" not in evidence_map
    assert "E1.2" not in evidence_map
    assert evidence_map["E1"].accepted_evidence_id == "evidence:evidence-large"
    assert evidence_map["E1"].tool_result_event_ref == "tool-result:evidence-large"
    assert evidence_map["E1"].tool_call_event_ref == "tool-call:evidence-large"
    assert evidence_map["E1"].canonical_source_refs == ("event:evidence-large",)
    assert evidence_map["E1"].content_digest == sha256_digest_json({"text": large_text})
    assert evidence_map["E1"].payload_refs == ("payload:evidence-large",)
    assert evidence_map["E1"].artifact_refs == ("artifact:evidence-large",)
    assert evidence_map["E1"].source_locator_refs == (locator_ref,)
    assert evidence_map["E1"].chunk_parent_label is None
    assert evidence_map["E1"].chunk_ordinal is None
    vnext_input = conversation_compact_input_vnext_from_material_pack(pack)
    assert tuple(item.source_label for item in vnext_input.evidence_material) == ("E1",)
    assert tuple(item.response_text for item in vnext_input.evidence_material) == (
        large_text,
    )
    assert "E1.1" not in vnext_input.citable_source_labels
    assert "E1.2" not in vnext_input.citable_source_labels


def test_current_input_anchor_keeps_whole_text_without_private_cap() -> None:
    """current input anchor 不再按私有字符上限截断。"""

    long_current_input = "current " + ("segment " * 400)
    pack = build_compact_material_pack(
        selected_segment=select_compact_segment(
            trigger_source=CompactSegmentTrigger.PROACTIVE,
            input_cursor=1,
            memory_snapshot_cursor=None,
            policy_digest=_POLICY_DIGEST,
            material_blocks=(),
        ),
        material_blocks=(),
        memory_snapshot=None,
        inline_delta_repair_view=None,
        current_input_ref="event-current-long",
        current_input_text=long_current_input,
    )

    expected = " ".join(long_current_input.split())
    assert pack.current_input_anchor.anchor_text == expected
    assert pack.current_input_anchor.truncated is False
    vnext_input = conversation_compact_input_vnext_from_material_pack(pack)
    assert vnext_input.current_input_anchor.text == expected


def test_pre_dispatch_first_compact_uses_eventlog_delta_before_current_input(tmp_path: Path) -> None:
    """首次 compact 从 EventLog 构造 delta，当前输入只作为 anchor。"""

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> RunRow:
            """写入首次 compact 所需 EventLog rows。

            :param transaction: Host transaction。
            :returns: 当前 Run row。
            """

            user = _append_event(
                transaction,
                event_log,
                event_id="event-user-old",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "old user question"},
                run_id="run-old",
            )
            answer = _append_event(
                transaction,
                event_log,
                event_id="event-answer-old",
                event_type="RUN_SUCCEEDED",
                payload={"final_answer": "old assistant answer"},
                run_id="run-old",
            )
            evidence = _append_tool_result_event(
                transaction,
                event_log,
                event_id="event-tool-result-old",
                run_id="run-old",
            )
            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-input",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current user question"},
                run_id="run:event-current-input",
            )
            assert user.event_sequence < answer.event_sequence < evidence.event_sequence
            return _run_row(current)

        run = store.transaction_runner.run_write(seed)

        def build(transaction: HostTransaction) -> PreDispatchCompactMaterialView:
            """构造 pre-dispatch material view。

            :param transaction: Host transaction。
            :returns: material view。
            """

            return build_pre_dispatch_compact_material_view(
                transaction,
                event_log,
                run=run,
                current_display_text="current user question",
            )

        view = store.transaction_runner.run_read(build)

        assert isinstance(view.source_boundary, CompactMaterialSourceBoundary)
        assert view.previous_compacted_view == ()
        assert view.current_input_text == "current user question"
        assert view.source_boundary.post_compact_delta_start_sequence == 1
        assert (
            view.source_boundary.post_compact_delta_end_sequence
            == run.input_event_sequence
        )
        assert tuple(block.kind for block in view.material_blocks) == (
            CompactMaterialBlockKind.USER_INPUT,
            CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
            CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
        )
        assert tuple(block.turn_group_id for block in view.material_blocks) == (
            "run-old",
            "run-old",
            "run-old",
        )
        assert "current user question" not in tuple(
            block.text for block in view.material_blocks
        )
        assert tuple(fragment.text for fragment in view.budget_fragments)[-1] == (
            "current user question"
        )


def test_pre_dispatch_reads_delta_rows_beyond_old_cap(tmp_path: Path) -> None:
    """pre-dispatch source builder 读取超过旧 256 限制的完整 delta rows。"""

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> RunRow:
            """写入超过旧 delta cap 的历史 user facts。

            :param transaction: Host transaction。
            :returns: 当前 Run row。
            """

            for index in range(260):
                _append_event(
                    transaction,
                    event_log,
                    event_id=f"event-user-delta-{index:03d}",
                    event_type="USER_INPUT_ACCEPTED",
                    payload={"display_text": f"delta user {index:03d}"},
                )
            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-after-large-delta",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current after large delta"},
            )
            return _run_row(current)

        run = store.transaction_runner.run_write(seed)
        view = store.transaction_runner.run_read(
            lambda transaction: build_pre_dispatch_compact_material_view(
                transaction,
                event_log,
                run=run,
                current_display_text="current after large delta",
            )
        )

        assert len(view.material_blocks) == 260
        assert view.material_blocks[0].text == "delta user 000"
        assert view.material_blocks[-1].text == "delta user 259"
        assert view.budget_fragments[-1].text == "current after large delta"


def test_pre_dispatch_keeps_evidence_blocks_beyond_old_cap(tmp_path: Path) -> None:
    """accepted evidence 超过旧 8 个时 source builder 不 fail closed。"""

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> RunRow:
            """写入超过旧 evidence cap 的 accepted tool results。

            :param transaction: Host transaction。
            :returns: 当前 Run row。
            """

            for index in range(10):
                _append_tool_result_event(
                    transaction,
                    event_log,
                    event_id=f"event-tool-result-evidence-{index:02d}",
                )
            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-after-evidence",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current after evidence"},
            )
            return _run_row(current)

        run = store.transaction_runner.run_write(seed)
        view = store.transaction_runner.run_read(
            lambda transaction: build_pre_dispatch_compact_material_view(
                transaction,
                event_log,
                run=run,
                current_display_text="current after evidence",
            )
        )

        evidence_blocks = tuple(
            block
            for block in view.material_blocks
            if block.kind is CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE
        )
        assert len(evidence_blocks) == 10
        assert evidence_blocks[-1].accepted_evidence_id == (
            "evidence:event-tool-result-evidence-09"
        )


def test_pre_dispatch_evidence_uses_full_tool_call_query_atom(tmp_path: Path) -> None:
    """pre-dispatch evidence query 使用 TOOL_CALL_REQUESTED 完整 query atom。"""

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> RunRow:
            """写入完整 tool call atom 与 accepted evidence。

            :param transaction: Host transaction。
            :returns: 当前 Run row。
            """

            request = _append_tool_call_requested_event(
                transaction,
                event_log,
                event_id="event-tool-call-query-atom",
                tool_call_id="tool-call-query-atom",
                semantic_query_text="Search FY2025 revenue for MSFT",
            )
            result = _append_tool_result_event(
                transaction,
                event_log,
                event_id="event-tool-result-query-atom",
                tool_call_requested_event_ref=request.event_id,
                tool_call_id="tool-call-query-atom",
                normalized_arguments_digest=sha256_digest_json(
                    {"arguments": {"ticker": "MSFT"}}
                ),
            )
            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-query-atom",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current user question"},
            )
            assert request.event_sequence < result.event_sequence < current.event_sequence
            return _run_row(current)

        run = store.transaction_runner.run_write(seed)

        view = store.transaction_runner.run_read(
            lambda transaction: build_pre_dispatch_compact_material_view(
                transaction,
                event_log,
                run=run,
                current_display_text="current user question",
            )
        )

        evidence_blocks = tuple(
            block
            for block in view.material_blocks
            if block.kind is CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE
        )
        assert len(evidence_blocks) == 1
        assert evidence_blocks[0].readable_query_text == (
            "Search FY2025 revenue for MSFT"
        )


def test_pre_dispatch_evidence_query_text_is_not_truncated(tmp_path: Path) -> None:
    """pre-dispatch evidence query 只规范化，不按旧 1200 字符截断。"""

    long_query = " ".join(("long-query", *("segment" for _ in range(240))))
    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> RunRow:
            """写入超长 semantic query atom 与 accepted evidence。

            :param transaction: Host transaction。
            :returns: 当前 Run row。
            """

            request = _append_tool_call_requested_event(
                transaction,
                event_log,
                event_id="event-tool-call-long-query",
                tool_call_id="tool-call-long-query",
                semantic_query_text=long_query,
            )
            _append_tool_result_event(
                transaction,
                event_log,
                event_id="event-tool-result-long-query",
                tool_call_requested_event_ref=request.event_id,
                tool_call_id="tool-call-long-query",
                normalized_arguments_digest=sha256_digest_json(
                    {"arguments": {"ticker": "MSFT"}}
                ),
            )
            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-long-query",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current user question"},
            )
            return _run_row(current)

        run = store.transaction_runner.run_write(seed)
        view = store.transaction_runner.run_read(
            lambda transaction: build_pre_dispatch_compact_material_view(
                transaction,
                event_log,
                run=run,
                current_display_text="current user question",
            )
        )

        evidence_blocks = tuple(
            block
            for block in view.material_blocks
            if block.kind is CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE
        )
        assert len(evidence_blocks) == 1
        query_text = evidence_blocks[0].readable_query_text
        assert query_text is not None
        assert query_text == long_query
        assert len(query_text) > 1200


def test_pre_dispatch_evidence_reads_descriptor_raw_payload(tmp_path: Path) -> None:
    """pre-dispatch evidence 从 descriptor raw payload 读取，不读 envelope preview。"""

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> RunRow:
            """写入 descriptor-backed accepted evidence。

            :param transaction: Host transaction。
            :returns: 当前 Run row。
            """

            payload_ref = "payload-descriptor-evidence"
            envelope = _accepted_evidence_envelope_for_event(
                "event-tool-result-descriptor",
                payload_ref=payload_ref,
            )
            descriptor = PayloadStore().write_sqlite_payload(
                transaction,
                SQLitePayloadWriteRequest(
                    payload_ref=payload_ref,
                    payload_id="sqlite-payload-descriptor-evidence",
                    payload_format=SQLitePayloadFormat.CANONICAL_JSON,
                    payload_json={
                        "accepted_evidence_envelope": (
                            accepted_evidence_envelope_to_json_value(envelope)
                        ),
                        "raw_tool_outcome": {
                            "kind": "completed",
                            "result": {"content": "descriptor raw content"},
                        },
                    },
                ),
            )
            event_log.append_event(
                transaction,
                EventLogAppendRequest(
                    event_id="event-tool-result-descriptor",
                    event_class=EventClass.CANONICAL_FACT,
                    session_id=_SESSION_ID,
                    run_id=None,
                    attempt_id=None,
                    execution_id=None,
                    event_type="TOOL_RESULT_ACCEPTED",
                    occurred_at=datetime(2026, 5, 24, 0, 0, 0, tzinfo=UTC),
                    actor="pytest",
                    source="test_compact_material",
                    client_request_id=None,
                    idempotency_key=None,
                    policy_decision=None,
                    reason=None,
                    payload_json={"result_preview": "must not be used"},
                    payload_ref=descriptor.payload_ref,
                    payload_digest=descriptor.payload_digest,
                ),
            )
            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-descriptor",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current user question"},
            )
            return _run_row(current)

        run = store.transaction_runner.run_write(seed)
        view = store.transaction_runner.run_read(
            lambda transaction: build_pre_dispatch_compact_material_view(
                transaction,
                event_log,
                run=run,
                current_display_text="current user question",
            )
        )

        assert tuple(block.text for block in view.material_blocks) == (
            '{"kind":"completed","result":{"content":"descriptor raw content"}}',
        )
        assert view.material_blocks[0].payload_refs == ("payload-descriptor-evidence",)


def test_pre_dispatch_tool_result_without_envelope_yields_no_evidence_block(
    tmp_path: Path,
) -> None:
    """TOOL_RESULT_ACCEPTED 无 accepted evidence envelope 时不生成 evidence block。"""

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> RunRow:
            """写入无 evidence envelope 的工具结果与当前输入。

            :param transaction: Host transaction。
            :returns: 当前 Run row。
            """

            _append_event(
                transaction,
                event_log,
                event_id="event-tool-result-no-envelope",
                event_type="TOOL_RESULT_ACCEPTED",
                payload={"tool_name": "legacy-free"},
            )
            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-no-envelope",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current user question"},
            )
            return _run_row(current)

        run = store.transaction_runner.run_write(seed)
        view = store.transaction_runner.run_read(
            lambda transaction: build_pre_dispatch_compact_material_view(
                transaction,
                event_log,
                run=run,
                current_display_text="current user question",
            )
        )

        assert view.material_blocks == ()


def test_pre_dispatch_evidence_missing_request_atom_emits_limited_signal(
    tmp_path: Path,
) -> None:
    """缺 TOOL_CALL_REQUESTED atom 时 query 文本为 limited signal 且不泄漏 id。"""

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> RunRow:
            """写入缺 request atom 的 accepted evidence。

            :param transaction: Host transaction。
            :returns: 当前 Run row。
            """

            _append_tool_result_event(
                transaction,
                event_log,
                event_id="event-tool-result-missing-request",
            )
            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-missing-request",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current user question"},
            )
            return _run_row(current)

        run = store.transaction_runner.run_write(seed)
        view = store.transaction_runner.run_read(
            lambda transaction: build_pre_dispatch_compact_material_view(
                transaction,
                event_log,
                run=run,
                current_display_text="current user question",
            )
        )

        query_text = view.material_blocks[0].readable_query_text
        assert query_text is not None
        assert "limited_signal" in query_text
        assert "event-tool-result-missing-request" not in query_text
        assert "tool-call-event-tool-result-missing-request" not in query_text


@pytest.mark.parametrize(
    ("event_id", "include_raw", "include_preview", "message"),
    (
        (
            "event-tool-result-missing-raw",
            False,
            False,
            "raw_tool_outcome",
        ),
        (
            "event-tool-result-preview",
            True,
            True,
            "result_preview",
        ),
    ),
)
def test_pre_dispatch_evidence_payload_damage_fails_closed(
    tmp_path: Path,
    event_id: str,
    include_raw: bool,
    include_preview: bool,
    message: str,
) -> None:
    """raw evidence 缺失或旧 preview 字段出现时 fail closed。

    :param tmp_path: pytest 临时目录。
    :param event_id: TOOL_RESULT_ACCEPTED event id。
    :param include_raw: 是否写入 raw_tool_outcome。
    :param include_preview: 是否写入旧 result_preview。
    :param message: 期望错误消息片段。
    """

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> RunRow:
            """写入损坏 evidence payload 与当前输入。

            :param transaction: Host transaction。
            :returns: 当前 Run row。
            """

            payload: dict[str, JsonValue] = {
                "accepted_evidence_envelope": accepted_evidence_envelope_to_json_value(
                    _accepted_evidence_envelope_for_event(event_id)
                )
            }
            if include_raw:
                payload["raw_tool_outcome"] = {
                    "kind": "completed",
                    "result": {"content": "raw content"},
                }
            if include_preview:
                payload["result_preview"] = "legacy preview must not be used"
            _append_event(
                transaction,
                event_log,
                event_id=event_id,
                event_type="TOOL_RESULT_ACCEPTED",
                payload=payload,
            )
            current = _append_event(
                transaction,
                event_log,
                event_id=f"event-current-{event_id}",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current user question"},
            )
            return _run_row(current)

        run = store.transaction_runner.run_write(seed)
        with pytest.raises(HostDurableError, match=message):
            store.transaction_runner.run_read(
                lambda transaction: build_pre_dispatch_compact_material_view(
                    transaction,
                    event_log,
                    run=run,
                    current_display_text="current user question",
                )
            )


def test_compact_material_source_boundary_rejects_inverted_delta_boundary() -> None:
    """Source boundary 直接拒绝 inverted delta 边界。"""

    with pytest.raises(ValueError, match="post compact delta boundary is inverted"):
        CompactMaterialSourceBoundary(
            latest_compacted_event_id=None,
            latest_compacted_event_sequence=None,
            post_compact_delta_start_sequence=4,
            post_compact_delta_end_sequence=3,
            current_input_event_sequence=3,
        )


def test_compact_material_source_boundary_rejects_delta_end_mismatch() -> None:
    """Source boundary 直接拒绝 delta end 与当前 input sequence 不一致。"""

    with pytest.raises(
        ValueError,
        match="delta end sequence must equal current input sequence",
    ):
        CompactMaterialSourceBoundary(
            latest_compacted_event_id=None,
            latest_compacted_event_sequence=None,
            post_compact_delta_start_sequence=2,
            post_compact_delta_end_sequence=3,
            current_input_event_sequence=4,
        )


def test_pre_dispatch_material_view_rejects_boundary_field_mismatches() -> None:
    """Material view 直接拒绝便捷字段与 source boundary 不一致。"""

    boundary = CompactMaterialSourceBoundary(
        latest_compacted_event_id="event-compact",
        latest_compacted_event_sequence=2,
        post_compact_delta_start_sequence=3,
        post_compact_delta_end_sequence=5,
        current_input_event_sequence=5,
    )
    view = PreDispatchCompactMaterialView(
        material_blocks=(),
        previous_compacted_view=(),
        current_input_text="current input",
        source_boundary=boundary,
        latest_compacted_event_id="event-compact",
        latest_compacted_event_sequence=2,
        post_compact_delta_start_sequence=3,
        post_compact_delta_end_sequence=5,
        represented_evidence_refs=(),
        budget_fragments=(),
    )

    with pytest.raises(ValueError, match="latest compacted event id boundary mismatch"):
        replace(view, latest_compacted_event_id="event-other-compact")
    with pytest.raises(
        ValueError,
        match="latest compacted event sequence boundary mismatch",
    ):
        replace(view, latest_compacted_event_sequence=1)
    with pytest.raises(ValueError, match="post compact delta start boundary mismatch"):
        replace(view, post_compact_delta_start_sequence=4)
    with pytest.raises(ValueError, match="post compact delta end boundary mismatch"):
        replace(view, post_compact_delta_end_sequence=4)


def test_pre_dispatch_first_compact_empty_delta_starts_at_current_input(tmp_path: Path) -> None:
    """首次 compact 且 current input 前无 relevant fact 时 delta 为空。"""

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> RunRow:
            """只写入当前输入。

            :param transaction: Host transaction。
            :returns: 当前 Run row。
            """

            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-only",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current only"},
            )
            return _run_row(current)

        run = store.transaction_runner.run_write(seed)
        view = store.transaction_runner.run_read(
            lambda transaction: build_pre_dispatch_compact_material_view(
                transaction,
                event_log,
                run=run,
                current_display_text="current only",
            )
        )

        assert view.material_blocks == ()
        assert view.post_compact_delta_start_sequence == run.input_event_sequence
        assert view.post_compact_delta_end_sequence == run.input_event_sequence


def test_pre_dispatch_second_compact_rolls_from_latest_accepted_candidate(tmp_path: Path) -> None:
    """第二次 compact 使用 latest accepted candidate，不重展旧 raw turn / tool result。"""

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> RunRow:
            """写入 old raw、accepted compact、新 delta 与当前输入。

            :param transaction: Host transaction。
            :returns: 当前 Run row。
            """

            _append_event(
                transaction,
                event_log,
                event_id="event-user-before-compact",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "old user before compact"},
            )
            _append_tool_result_event(
                transaction,
                event_log,
                event_id="event-tool-result-before-compact",
            )
            _append_compacted_event(
                transaction,
                event_log,
                event_id="event-compact-accepted",
                accepted_evidence_refs=("evidence:event-tool-result-before-compact",),
            )
            _append_event(
                transaction,
                event_log,
                event_id="event-user-after-compact",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "new user after compact"},
            )
            _append_tool_result_event(
                transaction,
                event_log,
                event_id="event-tool-result-after-compact",
            )
            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-second",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current second"},
            )
            return _run_row(current)

        run = store.transaction_runner.run_write(seed)
        view = store.transaction_runner.run_read(
            lambda transaction: build_pre_dispatch_compact_material_view(
                transaction,
                event_log,
                run=run,
                current_display_text="current second",
            )
        )

        assert tuple(block.text for block in view.previous_compacted_view) == (
            "accepted session summary",
            (
                "fact=claim_text=accepted fact; evidence_refs=E1; "
                "evidence_kind=accepted_evidence_material"
            ),
            "answer_anchor=accepted anchor",
            "forward_intent=next_step_note; status=open; text=accepted next step",
            "reference_continuity=local_reference; text=accepted reference",
        )
        assert tuple(block.text for block in view.material_blocks) == (
            "new user after compact",
            '{"kind":"completed","result":{"content":"raw content event-tool-result-after-compact"}}',
        )
        assert all("before compact" not in block.text for block in view.material_blocks)
        assert view.represented_evidence_refs == (
            "evidence:event-tool-result-before-compact",
        )


def test_pre_dispatch_previous_view_splits_each_accepted_candidate_item(
    tmp_path: Path,
) -> None:
    """latest accepted candidate 的每个 semantic item 独立进入 previous view。"""

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> RunRow:
            """写入 multi-item compact fact 与当前输入。

            :param transaction: Host transaction。
            :returns: 当前 Run row。
            """

            _append_compacted_event(
                transaction,
                event_log,
                event_id="event-compact-multi-item",
                accepted_evidence_refs=("evidence:event-before-multi",),
                accepted_candidate=_accepted_candidate_with_multiple_items(),
            )
            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-multi-item",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current after multi compact"},
            )
            return _run_row(current)

        run = store.transaction_runner.run_write(seed)
        view = store.transaction_runner.run_read(
            lambda transaction: build_pre_dispatch_compact_material_view(
                transaction,
                event_log,
                run=run,
                current_display_text="current after multi compact",
            )
        )

        assert tuple(block.kind for block in view.previous_compacted_view) == (
            CompactMaterialBlockKind.SESSION_SUMMARY,
            CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
            CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
            CompactMaterialBlockKind.ANSWER_ANCHOR,
            CompactMaterialBlockKind.ANSWER_ANCHOR,
            CompactMaterialBlockKind.FORWARD_INTENT,
            CompactMaterialBlockKind.REFERENCE_CONTINUITY,
        )
        assert tuple(block.block_label for block in view.previous_compacted_view) == (
            "P1",
            "P2",
            "P3",
            "P4",
            "P5",
            "P6",
            "P7",
        )
        assert tuple(block.text for block in view.previous_compacted_view) == (
            "accepted session summary",
            (
                "fact=claim_text=accepted fact one; evidence_refs=E1; "
                "evidence_kind=accepted_evidence_material"
            ),
            (
                "fact=claim_text=accepted fact two; evidence_refs=E2; "
                "evidence_kind=accepted_evidence_material"
            ),
            "answer_anchor=accepted anchor one",
            "answer_anchor=accepted anchor two",
            "forward_intent=next_step_note; status=open; text=accepted next step",
            "reference_continuity=local_reference; text=accepted reference",
        )


def test_pre_dispatch_builder_ignores_memory_snapshot_lag_or_missing(tmp_path: Path) -> None:
    """Builder 不读取 memory snapshot，snapshot 缺失或滞后不影响输出。"""

    event_log = EventLogStore()
    lagged_snapshot = _snapshot_with_fact(
        snapshot_id="snapshot-lagged-extra",
        checkpoint_event_sequence=1,
        claim_text="memory-only fact must not affect builder",
        provenance_event_id="event-user-memory-independent",
        tool_result_ref=None,
    )
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> RunRow:
            """写入当前输入前的一条历史 user fact。

            :param transaction: Host transaction。
            :returns: 当前 Run row。
            """

            _append_event(
                transaction,
                event_log,
                event_id="event-user-memory-independent",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "eventlog user"},
            )
            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-memory-independent",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current"},
            )
            return _run_row(current)

        run = store.transaction_runner.run_write(seed)
        view = store.transaction_runner.run_read(
            lambda transaction: build_pre_dispatch_compact_material_view(
                transaction,
                event_log,
                run=run,
                current_display_text="current",
            )
        )

        assert (
            lagged_snapshot.evidence_fact_memory.evidence_backed_facts[0].claim_text
            == "memory-only fact must not affect builder"
        )
        assert tuple(block.text for block in view.material_blocks) == ("eventlog user",)
        assert view.represented_evidence_refs == ()


def test_pre_dispatch_represented_evidence_refs_only_from_latest_compact(tmp_path: Path) -> None:
    """Evidence 去重只看 latest compact accepted mapping，不看 memory facts。"""

    event_log = EventLogStore()
    memory_with_extra_evidence = _snapshot_with_fact(
        snapshot_id="snapshot-extra-evidence",
        checkpoint_event_sequence=10,
        claim_text="memory has evidence:event-tool-result-after-compact",
        provenance_event_id="event-tool-result-after-compact",
        tool_result_ref="event-tool-result-after-compact",
    )
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> RunRow:
            """写入 compact 后 evidence 与当前输入。

            :param transaction: Host transaction。
            :returns: 当前 Run row。
            """

            _append_compacted_event(
                transaction,
                event_log,
                event_id="event-compact-with-old-evidence",
                accepted_evidence_refs=("evidence:event-old-only",),
            )
            _append_tool_result_event(
                transaction,
                event_log,
                event_id="event-tool-result-after-compact",
            )
            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-evidence-boundary",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current"},
            )
            return _run_row(current)

        run = store.transaction_runner.run_write(seed)
        view = store.transaction_runner.run_read(
            lambda transaction: build_pre_dispatch_compact_material_view(
                transaction,
                event_log,
                run=run,
                current_display_text="current",
            )
        )

        assert (
            memory_with_extra_evidence
            .evidence_fact_memory
            .evidence_backed_facts[0]
            .evidence_refs
            == ("evidence:accepted",)
        )
        assert view.represented_evidence_refs == ("evidence:event-old-only",)
        assert tuple(block.accepted_evidence_id for block in view.material_blocks) == (
            "evidence:event-tool-result-after-compact",
        )


def test_pre_dispatch_payload_damage_fails_closed_without_recovery_request(tmp_path: Path) -> None:
    """Payload / artifact 损坏时 fail closed，错误不请求 Run recovery。"""

    event_log = EventLogStore()
    with open_host_durable_store(_durable_options(tmp_path)) as store:
        def seed(transaction: HostTransaction) -> RunRow:
            """写入损坏的 compact payload。

            :param transaction: Host transaction。
            :returns: 当前 Run row。
            """

            compact_payload = _compacted_payload(
                accepted_evidence_refs=("evidence:event-old",)
            )
            damaged: dict[str, JsonValue] = dict(compact_payload)
            damaged["accepted_candidate_digest"] = _DIGEST
            _append_event(
                transaction,
                event_log,
                event_id="event-compact-damaged",
                event_type="CONTEXT_COMPACTED",
                payload=damaged,
            )
            current = _append_event(
                transaction,
                event_log,
                event_id="event-current-damaged",
                event_type="USER_INPUT_ACCEPTED",
                payload={"display_text": "current"},
            )
            return _run_row(current)

        run = store.transaction_runner.run_write(seed)
        with pytest.raises(HostDurableError) as exc_info:
            store.transaction_runner.run_read(
                lambda transaction: build_pre_dispatch_compact_material_view(
                    transaction,
                    event_log,
                    run=run,
                    current_display_text="current",
                )
            )

        assert isinstance(exc_info.value, HostDurableError)


def test_build_compact_material_pack_uses_explicit_previous_view_without_snapshot() -> None:
    """显式 previous view 路径不读取 snapshot path，空 tuple 也表示明确 previous view。"""

    explicit_previous = (
        _previous_compact_block(
            label="P1",
            kind=CompactMaterialBlockKind.SESSION_SUMMARY,
            text="explicit summary",
        ),
    )
    selected = _history_block("new-delta", event_sequence=2, text="new delta")
    selection = select_compact_segment(
        trigger_source=CompactSegmentTrigger.PROACTIVE,
        input_cursor=3,
        memory_snapshot_cursor=None,
        policy_digest=_POLICY_DIGEST,
        material_blocks=(selected,),
    )
    snapshot = _snapshot_with_stable_blocks(
        snapshot_id="snapshot-must-not-be-used",
        checkpoint_event_sequence=2,
    )

    pack = build_compact_material_pack(
        selected_segment=selection,
        material_blocks=(selected,),
        memory_snapshot=snapshot,
        inline_delta_repair_view=None,
        current_input_ref="event-current",
        current_input_text="current",
        previous_compacted_view=explicit_previous,
    )
    first_pack = build_compact_material_pack(
        selected_segment=selection,
        material_blocks=(selected,),
        memory_snapshot=snapshot,
        inline_delta_repair_view=None,
        current_input_ref="event-current",
        current_input_text="current",
        previous_compacted_view=(),
    )

    assert tuple(block.text for block in pack.previous_compacted_view) == (
        "explicit summary",
    )
    _assert_material_pack_shape(
        pack,
        expected=_MaterialPackShape(
            previous_labels=("P1",),
            trace_labels=("T1",),
            evidence_labels=(),
            answer_labels=(),
            current_anchor_label="C1",
            citable_source_labels=("P1", "T1"),
        ),
    )
    _assert_vnext_input_shape(
        conversation_compact_input_vnext_from_material_pack(pack),
        expected=_VNextInputShape(
            top_level_keys=_VNEXT_TOP_LEVEL_KEYS,
            previous_count=1,
            trace_count=1,
            evidence_count=0,
            answer_count=0,
            current_anchor_label="C1",
        ),
    )
    assert first_pack.previous_compacted_view == ()
    _assert_material_pack_shape(
        first_pack,
        expected=_MaterialPackShape(
            previous_labels=(),
            trace_labels=("T1",),
            evidence_labels=(),
            answer_labels=(),
            current_anchor_label="C1",
            citable_source_labels=("T1",),
        ),
    )


def _history_block(
    block_id: str,
    *,
    event_sequence: int,
    text: str,
    already_represented: bool = False,
    kind: CompactMaterialBlockKind = CompactMaterialBlockKind.USER_INPUT,
    turn_group_id: str | None = "run:test",
) -> RunInputMaterialBlock:
    """构造 history material block。

    :param block_id: block id。
    :param event_sequence: event sequence。
    :param text: 文本。
    :param already_represented: 是否已被代表。
    :param kind: material kind。
    :param turn_group_id: Host Run turn group id。
    :returns: RunInputMaterialBlock。
    """

    return run_input_material_block(
        block_id=block_id,
        section=CompactMaterialSection.TRACE_MATERIAL,
        kind=kind,
        text=text,
        canonical_source_refs=(f"event:{block_id}",),
        event_sequence=event_sequence,
        turn_group_id=turn_group_id,
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
    turn_group_id: str | None = "run:test",
) -> RunInputMaterialBlock:
    """构造 evidence material block。

    :param block_id: block id。
    :param event_sequence: event sequence。
    :param text: raw evidence 文本。
    :param payload_refs: payload / artifact refs。
    :param artifact_refs: artifact refs。
    :param source_locator_refs: source locator refs。
    :param turn_group_id: Host Run turn group id。
    :returns: RunInputMaterialBlock。
    """

    return run_input_material_block(
        block_id=block_id,
        section=CompactMaterialSection.EVIDENCE_MATERIAL,
        kind=CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
        text=text,
        canonical_source_refs=(f"event:{block_id}",),
        event_sequence=event_sequence,
        turn_group_id=turn_group_id,
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


def _previous_compact_block(
    *,
    label: str,
    kind: CompactMaterialBlockKind,
    text: str,
    canonical_source_refs: tuple[str, ...] = ("event-explicit-compact",),
) -> CompactMaterialBlock:
    """构造测试用 explicit previous compact block。

    :param label: prompt-local label。
    :param kind: block kind。
    :param text: block text。
    :param canonical_source_refs: canonical source refs。
    :returns: CompactMaterialBlock。
    """

    return CompactMaterialBlock(
        block_label=label,
        section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
        kind=kind,
        text=text,
        size_units=len(text),
        source_labels=(),
        canonical_source_refs=canonical_source_refs,
        content_digest=sha256_digest_json({"text": text}),
    )


def _durable_options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造 compact material 测试用 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )


def _append_event(
    transaction: HostTransaction,
    event_log: EventLogStore,
    *,
    event_id: str,
    event_type: str,
    payload: JsonValue,
    run_id: str | None = None,
) -> EventLogRow:
    """向测试 EventLog 追加 canonical fact。

    :param transaction: Host transaction。
    :param event_log: EventLog store。
    :param event_id: event id。
    :param event_type: event type。
    :param payload: inline payload JSON。
    :param run_id: 可选 Host Run id。
    :returns: appended EventLog row。
    """

    return event_log.append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id=_SESSION_ID,
            run_id=run_id,
            attempt_id=None,
            execution_id=None,
            event_type=event_type,
            occurred_at=datetime(2026, 5, 24, 0, 0, 0, tzinfo=UTC),
            actor="test",
            source="test.compact_material",
            client_request_id=None,
            idempotency_key=event_id,
            policy_decision=None,
            reason=None,
            payload_json=payload,
            payload_ref=None,
            payload_digest=None,
        ),
    ).row


def _append_tool_call_requested_event(
    transaction: HostTransaction,
    event_log: EventLogStore,
    *,
    event_id: str,
    tool_call_id: str,
    semantic_query_text: str,
    run_id: str | None = None,
) -> EventLogRow:
    """追加带完整 request atom 的 TOOL_CALL_REQUESTED。

    :param transaction: Host transaction。
    :param event_log: EventLog store。
    :param event_id: event id。
    :param tool_call_id: tool call id。
    :param semantic_query_text: 业务可读 query 文本。
    :param run_id: 可选 Host Run id。
    :returns: appended EventLog row。
    """

    arguments_json: JsonValue = {"arguments": {"ticker": "MSFT"}}
    arguments_digest = sha256_digest_json(arguments_json)
    semantic_query_digest = sha256_digest_json(
        {"semantic_query_text": semantic_query_text}
    )
    return _append_event(
        transaction,
        event_log,
        event_id=event_id,
        event_type="TOOL_CALL_REQUESTED",
        run_id=run_id,
        payload={
            "tool_call_id": tool_call_id,
            "tool_name": "fins.search",
            "normalized_arguments_digest": arguments_digest,
            "arguments_payload_digest": arguments_digest,
            "arguments_storage_kind": TOOL_CALL_ARGUMENTS_STORAGE_INLINE_JSON,
            "arguments_payload_ref": None,
            "arguments_inline_json": arguments_json,
            "arguments_json_size_bytes": len(
                canonical_json_dumps(arguments_json).encode("utf-8")
            ),
            "semantic_input_digest": _DIGEST,
            "semantic_query_storage_kind": (
                TOOL_CALL_SEMANTIC_QUERY_STORAGE_INLINE_TEXT
            ),
            "semantic_query_text": semantic_query_text,
            "semantic_query_payload_ref": None,
            "semantic_query_digest": semantic_query_digest,
        },
    )


def _append_tool_result_event(
    transaction: HostTransaction,
    event_log: EventLogStore,
    *,
    event_id: str,
    tool_call_requested_event_ref: str | None = None,
    tool_call_id: str | None = None,
    normalized_arguments_digest: str = _DIGEST,
    run_id: str | None = None,
) -> EventLogRow:
    """追加带 accepted evidence envelope 的 TOOL_RESULT_ACCEPTED。

    :param transaction: Host transaction。
    :param event_log: EventLog store。
    :param event_id: tool result event id。
    :param tool_call_requested_event_ref: 可选 TOOL_CALL_REQUESTED event ref。
    :param tool_call_id: 可选 tool call id；不传时从 event id 派生。
    :param normalized_arguments_digest: envelope 参数 digest。
    :param run_id: 可选 Host Run id。
    :returns: appended EventLog row。
    """

    envelope = _accepted_evidence_envelope_for_event(
        event_id,
        tool_call_requested_event_ref=tool_call_requested_event_ref,
        tool_call_id=tool_call_id,
        normalized_arguments_digest=normalized_arguments_digest,
    )
    return _append_event(
        transaction,
        event_log,
        event_id=event_id,
        event_type="TOOL_RESULT_ACCEPTED",
        run_id=run_id,
        payload={
            "accepted_evidence_envelope": (
                accepted_evidence_envelope_to_json_value(envelope)
            ),
            "raw_tool_outcome": {
                "kind": "completed",
                "result": {"content": f"raw content {event_id}"},
            },
        },
    )


def _accepted_evidence_envelope_for_event(
    event_id: str,
    *,
    tool_call_requested_event_ref: str | None = None,
    tool_call_id: str | None = None,
    normalized_arguments_digest: str = _DIGEST,
    payload_ref: str | None = None,
    payload_digest: str | None = None,
) -> AcceptedEvidenceEnvelope:
    """构造测试用 accepted evidence envelope。

    :param event_id: producer event id。
    :param tool_call_requested_event_ref: 可选 TOOL_CALL_REQUESTED event ref。
    :param tool_call_id: 可选 tool call id；不传时从 event id 派生。
    :param normalized_arguments_digest: envelope 参数 digest。
    :param payload_ref: raw result payload descriptor ref。
    :param payload_digest: raw result payload digest。
    :returns: AcceptedEvidenceEnvelope。
    """

    actual_tool_call_id = (
        f"tool-call-{event_id}" if tool_call_id is None else tool_call_id
    )
    return AcceptedEvidenceEnvelope(
        evidence_id=f"evidence:{event_id}",
        producer_event_ref=event_id,
        tool_name="fins.search",
        tool_call_id=actual_tool_call_id,
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=tool_call_requested_event_ref,
            normalized_arguments_digest=normalized_arguments_digest,
            semantic_input_digest=_DIGEST,
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=payload_ref,
            payload_digest=payload_digest,
            outcome_digest=_DIGEST,
            truncation_applied=False,
        ),
        source_refs=(
            OpaqueEvidenceRef(ref_kind="source", ref_id=event_id, digest=None),
        ),
        locator_refs=(),
    )


def _append_compacted_event(
    transaction: HostTransaction,
    event_log: EventLogStore,
    *,
    event_id: str,
    accepted_evidence_refs: tuple[str, ...],
    accepted_candidate: ConversationCompactOutputVNext | None = None,
) -> EventLogRow:
    """追加 accepted CONTEXT_COMPACTED canonical fact。

    :param transaction: Host transaction。
    :param event_log: EventLog store。
    :param event_id: compacted event id。
    :param accepted_evidence_refs: accepted evidence mapping refs。
    :param accepted_candidate: 可选 accepted compact candidate。
    :returns: appended EventLog row。
    """

    return _append_event(
        transaction,
        event_log,
        event_id=event_id,
        event_type="CONTEXT_COMPACTED",
        payload=_compacted_payload(
            accepted_evidence_refs=accepted_evidence_refs,
            accepted_candidate=accepted_candidate,
        ),
    )


def _compacted_payload(
    *,
    accepted_evidence_refs: tuple[str, ...],
    accepted_candidate: ConversationCompactOutputVNext | None = None,
) -> dict[str, JsonValue]:
    """构造测试用 accepted compact payload。

    :param accepted_evidence_refs: accepted evidence mapping refs。
    :param accepted_candidate: 可选 accepted compact candidate。
    :returns: compacted payload。
    """

    return dict(
        build_context_compacted_payload(
            operation_id="operation-compact-test",
            accepted_attempt_number=1,
            compact_artifact_ref="artifact:compact-test",
            compact_artifact_digest=_DIGEST,
            accepted_candidate=(
                _accepted_candidate()
                if accepted_candidate is None
                else accepted_candidate
            ),
            quality_check_result=CompactQualityCheckResultVNext(
                accepted=True,
                rejection_reasons=(),
            ),
            budget_after_compact=128,
            prompt_local_label_mapping_refs=("label-map:test",),
            source_boundary_refs=("source-boundary:test",),
            accepted_evidence_mapping_refs=accepted_evidence_refs,
            projection_signal="project_memory",
        )
    )


def _accepted_candidate() -> ConversationCompactOutputVNext:
    """构造测试用 accepted compact candidate。

    :returns: ConversationCompactOutputVNext。
    """

    return ConversationCompactOutputVNext(
        schema_version="conversation_compact_output_v1",
        session_summary=SessionSummaryCandidateVNext(
            summary_text="accepted session summary",
            source_labels=("T1",),
        ),
        evidence_backed_facts=(
            EvidenceBackedFactCandidateVNext(
                claim_text="accepted fact",
                evidence_labels=("E1",),
                evidence_kind=FactEvidenceKindVNext.ACCEPTED_EVIDENCE_MATERIAL,
            ),
        ),
        answer_anchors=(
            AnswerAnchorCandidateVNext(
                anchor_title="accepted anchor",
                anchor_items=(
                    AnswerAnchorChildVNext(
                        display_text="accepted anchor item",
                        ordinal=1,
                    ),
                ),
                answer_source_labels=("A1",),
            ),
        ),
        forward_intents=(
            ForwardIntentCandidateVNext(
                intent_type=ForwardIntentTypeVNext.NEXT_STEP_NOTE,
                text="accepted next step",
                status=ForwardIntentStatusVNext.OPEN,
                source_labels=("T1",),
            ),
        ),
        reference_continuity_items=(
            ReferenceContinuityCandidateVNext(
                text="accepted reference",
                reason=ReferenceContinuityReasonVNext.LOCAL_REFERENCE,
                source_labels=("T1",),
            ),
        ),
        diagnostics=(),
    )


def _accepted_candidate_with_multiple_items() -> ConversationCompactOutputVNext:
    """构造含多 fact / anchor 的 accepted compact candidate。

    :returns: ConversationCompactOutputVNext。
    """

    return ConversationCompactOutputVNext(
        schema_version="conversation_compact_output_v1",
        session_summary=SessionSummaryCandidateVNext(
            summary_text="accepted session summary",
            source_labels=("T1",),
        ),
        evidence_backed_facts=(
            EvidenceBackedFactCandidateVNext(
                claim_text="accepted fact one",
                evidence_labels=("E1",),
                evidence_kind=FactEvidenceKindVNext.ACCEPTED_EVIDENCE_MATERIAL,
            ),
            EvidenceBackedFactCandidateVNext(
                claim_text="accepted fact two",
                evidence_labels=("E2",),
                evidence_kind=FactEvidenceKindVNext.ACCEPTED_EVIDENCE_MATERIAL,
            ),
        ),
        answer_anchors=(
            AnswerAnchorCandidateVNext(
                anchor_title="accepted anchor one",
                anchor_items=(
                    AnswerAnchorChildVNext(
                        display_text="accepted anchor item one",
                        ordinal=1,
                    ),
                ),
                answer_source_labels=("A1",),
            ),
            AnswerAnchorCandidateVNext(
                anchor_title="accepted anchor two",
                anchor_items=(
                    AnswerAnchorChildVNext(
                        display_text="accepted anchor item two",
                        ordinal=1,
                    ),
                ),
                answer_source_labels=("A2",),
            ),
        ),
        forward_intents=(
            ForwardIntentCandidateVNext(
                intent_type=ForwardIntentTypeVNext.NEXT_STEP_NOTE,
                text="accepted next step",
                status=ForwardIntentStatusVNext.OPEN,
                source_labels=("T1",),
            ),
        ),
        reference_continuity_items=(
            ReferenceContinuityCandidateVNext(
                text="accepted reference",
                reason=ReferenceContinuityReasonVNext.LOCAL_REFERENCE,
                source_labels=("T1",),
            ),
        ),
        diagnostics=(),
    )


def _run_row(input_event: EventLogRow) -> RunRow:
    """构造测试用 RunRow。

    :param input_event: 当前 USER_INPUT_ACCEPTED EventLog row。
    :returns: RunRow。
    """

    return RunRow(
        run_id=f"run:{input_event.event_id}",
        session_id=input_event.session_id,
        status=RunStatus.QUEUED,
        client_request_id="client-request-test",
        input_event_id=input_event.event_id,
        input_event_sequence=input_event.event_sequence,
        accepted_event_id=input_event.event_id,
        accepted_event_sequence=input_event.event_sequence,
        queued_event_id=None,
        queued_event_sequence=None,
        started_event_id=None,
        started_event_sequence=None,
        terminal_event_id=None,
        terminal_event_sequence=None,
        current_attempt_id=None,
        source_run_id=None,
        source_run_relation=None,
        execution_target="local",
        queue_policy="fifo",
        created_at=_NOW,
        updated_at=_NOW,
        terminal_at=None,
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


def _snapshot_with_fact(
    *,
    snapshot_id: str,
    checkpoint_event_sequence: int,
    claim_text: str,
    provenance_event_id: str,
    tool_result_ref: str | None,
) -> ConversationMemorySnapshotVNext:
    """构造包含 evidence fact 的 snapshot。

    :param snapshot_id: snapshot id。
    :param checkpoint_event_sequence: cursor sequence。
    :param claim_text: evidence-backed fact claim text。
    :param provenance_event_id: evidence fact 来源事件 id。
    :param tool_result_ref: evidence fact 对应工具结果事件；无工具结果时为 ``None``。
    :returns: ConversationMemorySnapshotVNext。
    """

    base = _empty_snapshot(
        snapshot_id,
        checkpoint_event_sequence=checkpoint_event_sequence,
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
                    event_id=provenance_event_id,
                    event_sequence=checkpoint_event_sequence,
                    run_id="run-memory",
                    attempt_id=None,
                    execution_id=None,
                    tool_result_ref=tool_result_ref,
                    payload_ref="compact-artifact:test",
                    digest_ref="digest:fact-test",
                    source_refs=(),
                ),
                extraction_operation_ref=f"event:{provenance_event_id}",
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

    base = _snapshot_with_fact(
        snapshot_id=snapshot_id,
        checkpoint_event_sequence=checkpoint_event_sequence,
        claim_text="Revenue increased year over year",
        provenance_event_id="event-stable-memory-source",
        tool_result_ref=None,
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
