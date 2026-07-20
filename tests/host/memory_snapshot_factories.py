"""Host memory snapshot 测试工厂。

本模块集中构造测试用 Conversation Memory snapshot，避免业务测试直接散落
``snapshot_digest`` 中间态和重复的 digest 回填流程。
"""

from __future__ import annotations

from dataclasses import replace

from dayu.host.compaction import (
    ForwardIntentStatusVNext,
    ForwardIntentTypeVNext,
    ReferenceContinuityReasonVNext,
)
from dayu.host.memory import (
    AnswerAnchor,
    AnswerAnchorChild,
    AnswerAnchorMemoryView,
    CONVERSATION_MEMORY_CONSUMER_ID,
    ConversationMemorySnapshotVNext,
    EvidenceBackedFactView,
    EvidenceFactMemoryView,
    ForwardIntent,
    ForwardIntentMemoryView,
    MemoryEvidenceBackedFactKind,
    MemoryIncludedReason,
    MemoryProducerKind,
    MemoryProjectionPolicy,
    MemoryProvenanceRef,
    MemorySizeUnits,
    MemorySnapshotCursor,
    ReferenceContinuityItem,
    SelectedRecentWindowItem,
    SelectedRecentWindowRole,
    SessionSummaryMemoryView,
    TraceMemoryView,
    calculate_memory_snapshot_digest,
    digest_memory_projection_policy,
)

_DIGEST_PLACEHOLDER = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
_DEFAULT_BUILT_AT = "2026-05-15T01:02:03.000000Z"


def memory_policy_digest(policy: MemoryProjectionPolicy) -> str:
    """返回 memory projection policy digest。

    :param policy: memory projection policy。
    :returns: policy canonical digest。
    """

    return digest_memory_projection_policy(policy)


def memory_snapshot_cursor(
    *,
    session_id: str,
    checkpoint_event_sequence: int,
    checkpoint_event_id: str | None = None,
) -> MemorySnapshotCursor:
    """构造测试用 memory snapshot cursor。

    :param session_id: Session id。
    :param checkpoint_event_sequence: cursor 覆盖的 EventLog sequence。
    :param checkpoint_event_id: cursor 覆盖的 EventLog id；空 cursor 为 ``None``。
    :returns: memory snapshot cursor。
    :raises ValueError: cursor 字段不满足生产 dataclass 校验时抛出。
    """

    return MemorySnapshotCursor(
        consumer_id=CONVERSATION_MEMORY_CONSUMER_ID,
        checkpoint_event_sequence=checkpoint_event_sequence,
        checkpoint_event_id=checkpoint_event_id,
        session_id=session_id,
    )


def recalculate_memory_snapshot_digest(
    snapshot: ConversationMemorySnapshotVNext,
) -> ConversationMemorySnapshotVNext:
    """用生产 digest helper 回填 snapshot digest。

    :param snapshot: 待回填 digest 的 snapshot。
    :returns: 带正确 ``snapshot_digest`` 的 snapshot。
    """

    without_digest = replace(snapshot, snapshot_digest=_DIGEST_PLACEHOLDER)
    return replace(
        without_digest,
        snapshot_digest=calculate_memory_snapshot_digest(without_digest),
    )


def empty_memory_snapshot(
    *,
    snapshot_id: str,
    session_id: str,
    cursor: MemorySnapshotCursor,
    policy: MemoryProjectionPolicy,
    built_at: str = _DEFAULT_BUILT_AT,
) -> ConversationMemorySnapshotVNext:
    """构造空 Conversation Memory snapshot。

    :param snapshot_id: snapshot id。
    :param session_id: Session id。
    :param cursor: snapshot cursor。
    :param policy: memory projection policy。
    :param built_at: snapshot 构建时间。
    :returns: 空 memory snapshot。
    """

    snapshot = ConversationMemorySnapshotVNext(
        schema_version="conversation_memory_snapshot_v1",
        snapshot_id=snapshot_id,
        session_id=session_id,
        cursor=cursor,
        policy_digest=memory_policy_digest(policy),
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
        built_at=built_at,
        snapshot_digest=_DIGEST_PLACEHOLDER,
    )
    return recalculate_memory_snapshot_digest(snapshot)


def rich_memory_snapshot(
    *,
    session_id: str,
    policy: MemoryProjectionPolicy,
    cursor: MemorySnapshotCursor,
    snapshot_id: str,
    latest_compaction_event_ref: str | None = "event-memory-episode",
    built_at: str = _DEFAULT_BUILT_AT,
) -> ConversationMemorySnapshotVNext:
    """构造覆盖 RunInputBuilder vNext memory 分组的 rich snapshot。

    :param session_id: Session id。
    :param policy: memory projection policy。
    :param cursor: snapshot cursor。
    :param snapshot_id: snapshot id。
    :param latest_compaction_event_ref: 最新 compact event ref。
    :param built_at: snapshot 构建时间。
    :returns: rich memory snapshot。
    """

    snapshot = ConversationMemorySnapshotVNext(
        schema_version="conversation_memory_snapshot_v1",
        snapshot_id=snapshot_id,
        session_id=session_id,
        cursor=cursor,
        policy_digest=memory_policy_digest(policy),
        latest_compaction_event_ref=latest_compaction_event_ref,
        trace_memory=TraceMemoryView(
            selected_recent_window=(
                SelectedRecentWindowItem(
                    item_id="memory-item:selected-user:test",
                    role=SelectedRecentWindowRole.USER,
                    text="recent raw user",
                    event_id="event-memory-raw-user",
                    event_sequence=3,
                    run_id="run-memory",
                    source_refs=("event-memory-raw-user",),
                    included_reason=MemoryIncludedReason.SELECTED_RECENT_WINDOW,
                    excluded_reason=None,
                    size_units=MemorySizeUnits(15),
                ),
                SelectedRecentWindowItem(
                    item_id="memory-item:selected-assistant:test",
                    role=SelectedRecentWindowRole.ASSISTANT,
                    text="recent assistant conclusion",
                    event_id="event-memory-assistant",
                    event_sequence=4,
                    run_id="run-memory",
                    source_refs=("event-memory-assistant",),
                    included_reason=MemoryIncludedReason.SELECTED_RECENT_WINDOW,
                    excluded_reason=None,
                    size_units=MemorySizeUnits(27),
                ),
            ),
            reference_continuity_items=(
                ReferenceContinuityItem(
                    item_id="memory-item:reference-continuity:test",
                    text="second factor: margin mix",
                    reason=ReferenceContinuityReasonVNext.ORDINAL_REFERENCE,
                    source_refs=("event-memory-raw-user",),
                    event_id="event-memory-episode",
                    event_sequence=5,
                    size_units=MemorySizeUnits(25),
                ),
            ),
        ),
        evidence_fact_memory=EvidenceFactMemoryView(
            evidence_backed_facts=(_memory_fact_view(),),
            recent_evidence_items=(),
        ),
        session_summary_memory=SessionSummaryMemoryView(
            summary_text="compare revenue quality; use reported currency",
            source_refs=("event-memory-episode",),
            event_id="event-memory-episode",
            event_sequence=5,
            size_units=MemorySizeUnits(46),
        ),
        answer_anchor_memory=AnswerAnchorMemoryView(
            anchors=(
                AnswerAnchor(
                    item_id="memory-item:answer-anchor:test",
                    anchor_title="Revenue quality",
                    anchor_items=(
                        AnswerAnchorChild(
                            display_text="Use reported currency.",
                            ordinal=1,
                        ),
                    ),
                    source_refs=("event-memory-episode",),
                    event_id="event-memory-episode",
                    event_sequence=5,
                    size_units=MemorySizeUnits(42),
                ),
            ),
        ),
        forward_intent_memory=ForwardIntentMemoryView(
            intents=(
                ForwardIntent(
                    item_id="memory-item:forward-intent:test",
                    intent_type=ForwardIntentTypeVNext.NEXT_STEP_NOTE,
                    text="what changed in margin?",
                    status=ForwardIntentStatusVNext.OPEN,
                    source_refs=("event-memory-episode",),
                    event_id="event-memory-episode",
                    event_sequence=5,
                    size_units=MemorySizeUnits(23),
                ),
            ),
        ),
        diagnostics=(),
        built_at=built_at,
        snapshot_digest=_DIGEST_PLACEHOLDER,
    )
    return recalculate_memory_snapshot_digest(snapshot)


def current_input_memory_snapshot(
    *,
    session_id: str,
    policy: MemoryProjectionPolicy,
    cursor: MemorySnapshotCursor,
    current_event_id: str,
    current_event_sequence: int,
    current_run_id: str | None,
    current_prompt: str,
    built_at: str = _DEFAULT_BUILT_AT,
) -> ConversationMemorySnapshotVNext:
    """构造包含当前用户输入的测试 memory snapshot。

    :param session_id: Session id。
    :param policy: memory projection policy。
    :param cursor: snapshot cursor。
    :param current_event_id: 当前 USER_INPUT_ACCEPTED event id。
    :param current_event_sequence: 当前 USER_INPUT_ACCEPTED event sequence。
    :param current_run_id: 当前 Run id。
    :param current_prompt: 当前 prompt 文本。
    :param built_at: snapshot 构建时间。
    :returns: 当前输入 memory snapshot。
    """

    base = empty_memory_snapshot(
        snapshot_id=f"memory-snapshot-current-{session_id}",
        session_id=session_id,
        cursor=cursor,
        policy=policy,
        built_at=built_at,
    )
    return recalculate_memory_snapshot_digest(
        replace(
            base,
            trace_memory=TraceMemoryView(
                selected_recent_window=(
                    SelectedRecentWindowItem(
                        item_id="memory-item:selected-current",
                        role=SelectedRecentWindowRole.USER,
                        text=current_prompt,
                        event_id=current_event_id,
                        event_sequence=current_event_sequence,
                        run_id=current_run_id,
                        source_refs=(current_event_id,),
                        included_reason=MemoryIncludedReason.SELECTED_RECENT_WINDOW,
                        excluded_reason=None,
                        size_units=MemorySizeUnits(len(current_prompt)),
                    ),
                ),
                reference_continuity_items=(),
            ),
        )
    )


def reference_continuity_only_snapshot(
    *,
    session_id: str,
    policy: MemoryProjectionPolicy,
    cursor: MemorySnapshotCursor,
    source_event_id: str,
    producer_event_id: str,
    producer_event_sequence: int,
    preserve_text: str,
    built_at: str = _DEFAULT_BUILT_AT,
) -> ConversationMemorySnapshotVNext:
    """构造只包含 reference continuity item 的测试 snapshot。

    :param session_id: Session id。
    :param policy: memory projection policy。
    :param cursor: snapshot cursor。
    :param source_event_id: compact 前来源 event id。
    :param producer_event_id: 生成 reference continuity item 的 event id。
    :param producer_event_sequence: 生成 event sequence。
    :param preserve_text: reference continuity 文本。
    :param built_at: snapshot 构建时间。
    :returns: reference continuity memory snapshot。
    """

    base = empty_memory_snapshot(
        snapshot_id=f"memory-snapshot-reference-continuity-{session_id}",
        session_id=session_id,
        cursor=cursor,
        policy=policy,
        built_at=built_at,
    )
    return recalculate_memory_snapshot_digest(
        replace(
            base,
            latest_compaction_event_ref=producer_event_id,
            trace_memory=TraceMemoryView(
                selected_recent_window=(),
                reference_continuity_items=(
                    ReferenceContinuityItem(
                        item_id="memory-item:reference-continuity:second-factor",
                        text=preserve_text,
                        reason=ReferenceContinuityReasonVNext.ORDINAL_REFERENCE,
                        source_refs=(source_event_id,),
                        event_id=producer_event_id,
                        event_sequence=producer_event_sequence,
                        size_units=MemorySizeUnits(len(preserve_text)),
                    ),
                ),
            ),
        )
    )


def _memory_fact_view() -> EvidenceBackedFactView:
    """构造 rich snapshot 使用的 evidence-backed fact。

    :returns: evidence-backed fact view。
    """

    return EvidenceBackedFactView(
        item_id="memory-item:evidence-backed:test",
        claim_text="Revenue increased year over year",
        evidence_kind=MemoryEvidenceBackedFactKind.DERIVED_FROM_EVIDENCE,
        evidence_refs=("evidence:memory-tool",),
        provenance=MemoryProvenanceRef(
            producer_kind=MemoryProducerKind.HOST_PROJECTION,
            producer_name="conversation_memory",
            event_id="event-memory-episode",
            event_sequence=5,
            run_id="run-memory",
            attempt_id=None,
            execution_id=None,
            tool_result_ref="event-memory-tool",
            payload_ref="compact-artifact:test",
            digest_ref="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            source_refs=(),
        ),
        extraction_operation_ref="event:event-memory-episode",
        compact_artifact_ref="compact-artifact:test",
        candidate_id="fact-memory-revenue",
        included_reason=MemoryIncludedReason.EVIDENCE_BACKED_FACT,
        excluded_reason=None,
        size_units=MemorySizeUnits(31),
    )
