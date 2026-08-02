"""WU-CM-13 compact pipeline thin helper 测试。"""

from __future__ import annotations

from dataclasses import dataclass, replace

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.engine.contracts.messages import AgentMessage, AgentMessageRole
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    SuccessfulRunnerResponseIdentity,
    build_runner_request_identity,
)
from dayu.host.api import RunStatus
from dayu.host.queue_policy import RunQueuePolicy
from dayu.host.compact_material import (
    CompactMaterialSourceBoundary,
    PreDispatchCompactMaterialView,
    RunInputMaterialBlock,
    run_input_material_block,
    selected_material_source_refs,
    selected_material_view_digest,
    conversation_compact_input_vnext_from_material_pack,
)
from dayu.host.compact_pipeline import (
    CompactPipelineSourceSnapshot,
    build_compacted_payload_input,
    build_fallback_decision_input,
    build_normal_compact_request_plan,
    build_reactive_pass_queue_plan,
    build_tier_recovery_request_plans,
    compact_pipeline_source_snapshot_from_pre_dispatch_view,
    select_ordinary_protected_raw_tail,
)
from dayu.host.compaction import (
    COMPACT_OUTPUT_SCHEMA_V2,
    CompactMaterialBlock,
    CompactMaterialBlockKind,
    PreviousCompactReadableView,
    CompactMaterialSection,
    CompactCandidateV2,
    CompactAcceptedTruthV2,
    CompactDropReasonV2,
    CompactEvidenceFactV2,
    CompactExplicitDropV2,
    CompactReferenceContinuityV2,
    CompactRepairFeedbackV2,
    CompactSourceKindV2,
    CompactionRequest,
    CompactorProposal,
    CompactorProposalError,
    ReadableFactItemVNext,
)
from dayu.host.compaction_operation import run_compaction_operation
from dayu.host.context_governance import accept_compact_candidate_v2
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_fallback import (
    FALLBACK_ACTION_DISPATCH,
    FALLBACK_ACTION_FAIL_CLOSED,
)
from dayu.host.context_policy import (
    ContextCompactionTriggerSource,
    context_budget_policy_from_threshold_tokens,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.evidence import (
    AcceptedToolEvidenceLLMMaterial,
    render_accepted_tool_evidence_for_llm,
)
from dayu.host.durable.state import RunRow
from dayu.host.memory import (
    default_memory_projection_policy,
    digest_memory_projection_policy,
)
from tests.host.fake_cancellation import ControllableCancellationToken
from tests.host.fake_compaction import (
    FakeContextCompactor,
)

_DIGEST = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


@dataclass(frozen=True, slots=True)
class _MemoryView:
    """测试用 memory view 协议实现。"""

    messages: tuple[AgentMessage, ...]
    selected_recent_source_refs: tuple[str, ...] = ()
    selected_recent_content_digests: tuple[str, ...] = ()


class _CrossPassDuplicateCompactor(FakeContextCompactor):
    """让每个 pass 产生相同 reference identity 的 deterministic compactor。"""

    def __init__(self) -> None:
        """初始化 fake 与 feedback 观测。

        :returns: ``None``。
        """

        super().__init__()
        self.observed_feedback: list[CompactRepairFeedbackV2 | None] = []

    async def compact(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        repair_feedback: CompactRepairFeedbackV2 | None,
    ) -> CompactorProposal:
        """保留完整 pass candidate，但注入可由 root 证明的跨 pass duplicate。

        :param request: 当前 immutable pass request。
        :param cancellation_token: Host cancellation token。
        :param repair_feedback: 前次 semantic feedback。
        :returns: 带同一 reference identity 的完整 proposal。
        :raises AssertionError: pass 缺少可用于 reference 的 current material。
        """

        self.observed_feedback.append(repair_feedback)
        proposal = await super().compact(
            request,
            cancellation_token,
            repair_feedback=repair_feedback,
        )
        if repair_feedback is not None:
            return proposal
        compact_input = conversation_compact_input_vnext_from_material_pack(request.material_pack)
        reference_entry = next(
            (
                entry
                for entry in compact_input.source_boundary
                if entry.source_kind
                in (
                    CompactSourceKindV2.TRACE_MATERIAL,
                    CompactSourceKindV2.EVIDENCE_MATERIAL,
                    CompactSourceKindV2.ANSWER_MATERIAL,
                )
            ),
            None,
        )
        assert reference_entry is not None
        return replace(
            proposal,
            candidate=replace(
                proposal.candidate,
                reference_continuity=(
                    CompactReferenceContinuityV2(
                        text="cross-pass duplicate",
                        reason="recent_state",
                        source_labels=(reference_entry.source_label,),
                    ),
                ),
            ),
        )


class _LaterPassFailingCompactor(FakeContextCompactor):
    """首个 reactive pass 成功，后续 pass 始终 execution failure。"""

    def __init__(self) -> None:
        """初始化调用计数。

        :returns: ``None``。
        """

        super().__init__()
        self.run_calls = 0

    async def compact(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        repair_feedback: CompactRepairFeedbackV2 | None,
    ) -> CompactorProposal:
        """只允许第一个 pass 成功。

        :param request: 当前 immutable pass request。
        :param cancellation_token: Host cancellation token。
        :param repair_feedback: execution retry 不应获得 semantic feedback。
        :returns: 第一个 pass 的合法 proposal。
        :raises CompactorProposalError: 第二个及后续 pass 始终失败。
        """

        self.run_calls += 1
        if self.run_calls > 1:
            raise CompactorProposalError(
                "later pass provider failure",
                successful_response_identity=None,
            )
        return await super().compact(
            request,
            cancellation_token,
            repair_feedback=repair_feedback,
        )


def test_source_snapshot_uses_run_and_material_view_truth() -> None:
    """source snapshot 字段来自 RunRow 与 material view，且不读取 lifecycle。"""

    run = _run_row(input_event_sequence=5)
    view = _material_view(current_input_sequence=5)

    snapshot = compact_pipeline_source_snapshot_from_pre_dispatch_view(
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
        run=run,
        material_view=view,
    )

    assert snapshot.session_id == run.session_id
    assert snapshot.run_id == run.run_id
    assert snapshot.current_input_ref == run.input_event_id
    assert snapshot.current_input_text == view.current_input_text
    assert snapshot.input_event_sequence == run.input_event_sequence
    assert snapshot.material_view_digest == selected_material_view_digest(view.material_blocks)
    assert snapshot.material_source_refs == selected_material_source_refs(
        material_blocks=view.material_blocks,
        selected_block_ids=tuple(block.block_id for block in view.material_blocks),
    )


def test_source_snapshot_rejects_input_boundary_mismatch() -> None:
    """Run input cursor 与 material source boundary 不一致时 fail closed。"""

    with pytest.raises(ValueError, match="input event sequence"):
        compact_pipeline_source_snapshot_from_pre_dispatch_view(
            trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            run=_run_row(input_event_sequence=6),
            material_view=_material_view(current_input_sequence=5),
        )


def test_normal_request_plan_keeps_current_input_out_of_selected_segment() -> None:
    """normal request plan 保护 current input anchor，不把它选为 older material。"""

    snapshot = _source_snapshot(ContextCompactionTriggerSource.PROACTIVE)
    plan = build_normal_compact_request_plan(
        source_snapshot=snapshot,
        selection_policy_digest="memory-policy-digest",
        budget_before_compact=_budget(),
        selected_recent_window_turn_floor=1,
    )

    assert plan.request.trigger_source is ContextCompactionTriggerSource.PROACTIVE
    assert plan.request.attempt_id is None
    assert plan.request.execution_id is None
    assert snapshot.current_input_ref in plan.request.recent_raw_turn_refs
    assert snapshot.current_input_ref not in plan.selected_source_refs
    assert plan.request.current_input_ref == snapshot.current_input_ref
    assert tuple(plan.request.material_pack.current_input_anchor.canonical_source_refs) == (snapshot.current_input_ref,)


def test_reactive_request_plan_sets_attempt_identity_without_semantic_drift() -> None:
    """reactive 与 proactive request 在忽略 attempt 身份后选择语义等价。"""

    proactive = build_normal_compact_request_plan(
        source_snapshot=_source_snapshot(ContextCompactionTriggerSource.PROACTIVE),
        selection_policy_digest="memory-policy-digest",
        budget_before_compact=_budget(),
        selected_recent_window_turn_floor=1,
    )
    reactive = build_normal_compact_request_plan(
        source_snapshot=_source_snapshot(ContextCompactionTriggerSource.REACTIVE),
        selection_policy_digest="memory-policy-digest",
        budget_before_compact=_budget(),
        selected_recent_window_turn_floor=1,
        attempt_id="attempt-reactive",
        execution_id="execution-reactive",
    )

    assert reactive.request.attempt_id == "attempt-reactive"
    assert reactive.request.execution_id == "execution-reactive"
    assert reactive.selected_segment.selected_block_ids == (proactive.selected_segment.selected_block_ids)
    assert reactive.selected_source_refs == proactive.selected_source_refs


def test_tier_recovery_request_plans_use_fallback_caps_degrade_and_delta_only() -> None:
    """tier recovery helper 构造 tier 1/2/3 且不调用 compactor。"""

    snapshot = _source_snapshot(ContextCompactionTriggerSource.PROACTIVE)
    root = build_normal_compact_request_plan(
        source_snapshot=snapshot,
        selection_policy_digest="memory-policy-digest",
        budget_before_compact=_budget(),
        selected_recent_window_turn_floor=0,
    )
    memory_policy = replace(
        default_memory_projection_policy(context_window_size=8192),
        selected_recent_window_turn_floor=1,
        fallback_selected_recent_window_item_cap=1,
        fallback_selected_recent_window_char_cap=40,
    )

    plans = build_tier_recovery_request_plans(
        source_snapshot=snapshot,
        root_request_plan=root,
        memory_policy=memory_policy,
    )

    assert tuple(plan.tier_name for plan in plans) == (
        "tier_1_fallback_caps",
        "tier_2_section_degrade",
        "tier_3_delta_only",
    )
    tier_1, tier_2, tier_3 = (plan.request_plan.request for plan in plans)
    assert len(tier_1.segment_selection.selected_block_ids) <= 1
    assert tier_2.segment_selection == tier_1.segment_selection
    assert tier_2.segment_selection != root.request.segment_selection
    assert tuple(block.kind for block in tier_2.material_pack.previous_compacted_view) == (
        CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
    )
    assert tier_3.material_pack.previous_compacted_view == ()


def test_reactive_pass_queue_builds_single_block_passes() -> None:
    """reactive pass queue 对多个 selected blocks 生成 one-block pass requests。"""

    snapshot = _source_snapshot(ContextCompactionTriggerSource.REACTIVE)
    root = build_normal_compact_request_plan(
        source_snapshot=snapshot,
        selection_policy_digest="memory-policy-digest",
        budget_before_compact=_budget(),
        selected_recent_window_turn_floor=0,
        attempt_id="attempt-reactive",
        execution_id="execution-reactive",
    )

    queue = build_reactive_pass_queue_plan(
        source_snapshot=snapshot,
        root_request_plan=root,
    )

    assert len(root.selected_segment.selected_block_ids) > 1
    assert len(queue.pass_requests) == len(root.selected_segment.selected_block_ids)
    assert (
        tuple(request.segment_selection.selected_block_ids[0] for request in queue.pass_requests)
        == root.selected_segment.selected_block_ids
    )
    assert all(request.current_input_ref == snapshot.current_input_ref for request in queue.pass_requests)
    root_input = conversation_compact_input_vnext_from_material_pack(root.request.material_pack)
    pass_inputs = tuple(
        conversation_compact_input_vnext_from_material_pack(request.material_pack) for request in queue.pass_requests
    )
    flattened_boundary = tuple(entry for compact_input in pass_inputs for entry in compact_input.source_boundary)
    assert {entry.source_label: entry for entry in flattened_boundary} == {
        entry.source_label: entry for entry in root_input.source_boundary
    }
    assert len({entry.source_label for entry in flattened_boundary}) == len(flattened_boundary)
    assert all(compact_input.current_input == root_input.current_input for compact_input in pass_inputs)


@pytest.mark.asyncio
async def test_reactive_multi_pass_forms_one_root_accepted_truth() -> None:
    """全部互斥 pass accepted 后只返回 root revalidated truth。"""

    snapshot = _source_snapshot(ContextCompactionTriggerSource.REACTIVE)
    root = build_normal_compact_request_plan(
        source_snapshot=snapshot,
        selection_policy_digest="memory-policy-digest",
        budget_before_compact=_budget(),
        selected_recent_window_turn_floor=0,
        attempt_id="attempt-reactive",
        execution_id="execution-reactive",
    )
    queue = build_reactive_pass_queue_plan(
        source_snapshot=snapshot,
        root_request_plan=root,
    )

    result = await run_compaction_operation(
        request=root.request,
        compactor=FakeContextCompactor(),
        first_attempt_number=1,
        max_attempt_number=len(queue.pass_requests),
        cancellation_token=ControllableCancellationToken(),
        pass_queue=queue.pass_requests,
        compaction_operation_id="operation-reactive-multi-pass",
        memory_policy=default_memory_projection_policy(),
    )

    assert result.failure_reason is None
    assert result.accepted_truth is not None
    result.accepted_truth.validate_input_binding(
        conversation_compact_input_vnext_from_material_pack(root.request.material_pack)
    )
    assert result.accepted_attempt_number == len(queue.pass_requests)


@pytest.mark.asyncio
async def test_reactive_cross_pass_duplicate_exhaust_leaks_no_partial_truth() -> None:
    """cross-pass duplicate 在 root 重验失败且预算耗尽时不泄漏 pass truth。"""

    snapshot = _source_snapshot(ContextCompactionTriggerSource.REACTIVE)
    root = build_normal_compact_request_plan(
        source_snapshot=snapshot,
        selection_policy_digest="memory-policy-digest",
        budget_before_compact=_budget(),
        selected_recent_window_turn_floor=0,
        attempt_id="attempt-reactive",
        execution_id="execution-reactive",
    )
    queue = build_reactive_pass_queue_plan(
        source_snapshot=snapshot,
        root_request_plan=root,
    )

    result = await run_compaction_operation(
        request=root.request,
        compactor=_CrossPassDuplicateCompactor(),
        first_attempt_number=1,
        max_attempt_number=len(queue.pass_requests),
        cancellation_token=ControllableCancellationToken(),
        pass_queue=queue.pass_requests,
        compaction_operation_id="operation-reactive-duplicate",
        memory_policy=default_memory_projection_policy(),
    )

    assert result.accepted_truth is None
    assert result.failure_reason == "quality_check_rejected"
    assert len(result.rejected_attempts) == 1
    assert result.next_repair_feedback is not None
    assert result.next_repair_feedback.issues[0].code.value == "duplicate_semantic_item"


@pytest.mark.asyncio
async def test_reactive_later_pass_failure_returns_no_partial_truth() -> None:
    """later pass exhaust 只返回单一 failure result，不泄漏首个 pass truth。"""

    snapshot = _source_snapshot(ContextCompactionTriggerSource.REACTIVE)
    root = build_normal_compact_request_plan(
        source_snapshot=snapshot,
        selection_policy_digest="memory-policy-digest",
        budget_before_compact=_budget(),
        selected_recent_window_turn_floor=0,
        attempt_id="attempt-reactive",
        execution_id="execution-reactive",
    )
    queue = build_reactive_pass_queue_plan(
        source_snapshot=snapshot,
        root_request_plan=root,
    )
    compactor = _LaterPassFailingCompactor()

    result = await run_compaction_operation(
        request=root.request,
        compactor=compactor,
        first_attempt_number=1,
        max_attempt_number=len(queue.pass_requests),
        cancellation_token=ControllableCancellationToken(),
        pass_queue=queue.pass_requests,
        compaction_operation_id="operation-reactive-later-pass-failure",
        memory_policy=default_memory_projection_policy(),
    )

    assert compactor.run_calls == len(queue.pass_requests)
    assert result.failure_reason == "proposal_failed"
    assert result.accepted_truth is None
    assert result.accepted_attempt_number is None
    assert result.accepted_successful_response_identity is None
    assert result.accepted_proposal_manifest_reference is None
    assert all(
        rejected.failure_category.value == "proposal_failed"
        for rejected in result.rejected_attempts
    )


@pytest.mark.asyncio
async def test_reactive_cross_pass_duplicate_routes_full_pass_repair() -> None:
    """root duplicate 路由到贡献 pass，并用 immutable input 完整重产。"""

    snapshot = _source_snapshot(ContextCompactionTriggerSource.REACTIVE)
    root = build_normal_compact_request_plan(
        source_snapshot=snapshot,
        selection_policy_digest="memory-policy-digest",
        budget_before_compact=_budget(),
        selected_recent_window_turn_floor=0,
        attempt_id="attempt-reactive",
        execution_id="execution-reactive",
    )
    queue = build_reactive_pass_queue_plan(
        source_snapshot=snapshot,
        root_request_plan=root,
    )
    compactor = _CrossPassDuplicateCompactor()

    result = await run_compaction_operation(
        request=root.request,
        compactor=compactor,
        first_attempt_number=1,
        max_attempt_number=(2 * len(queue.pass_requests)) - 1,
        cancellation_token=ControllableCancellationToken(),
        pass_queue=queue.pass_requests,
        compaction_operation_id="operation-reactive-duplicate-repair",
        memory_policy=default_memory_projection_policy(),
    )

    assert result.failure_reason is None
    assert result.accepted_truth is not None
    assert len(result.rejected_attempts) == len(queue.pass_requests) - 1
    assert compactor.observed_feedback[-1] is not None
    assert compactor.observed_feedback[-1].issues[0].code.value == "duplicate_semantic_item"


def test_compacted_payload_input_derives_semantic_refs() -> None:
    """accepted payload input 复用 compact payload helper 的 semantic refs。"""

    plan = build_normal_compact_request_plan(
        source_snapshot=_source_snapshot(ContextCompactionTriggerSource.PROACTIVE),
        selection_policy_digest="memory-policy-digest",
        budget_before_compact=_budget(),
        selected_recent_window_turn_floor=0,
    )
    compact_input = conversation_compact_input_vnext_from_material_pack(plan.request.material_pack)
    candidate = replace(
        _candidate_with_evidence_fact(),
        explicitly_dropped_sources=tuple(
            CompactExplicitDropV2(
                source_label=entry.source_label,
                reason=CompactDropReasonV2.OUT_OF_SCOPE,
            )
            for entry in compact_input.source_boundary
            if entry.source_label != "E1"
        ),
    )
    accepted_truth = accept_compact_candidate_v2(
        compact_input,
        candidate,
        default_memory_projection_policy(),
    )
    assert isinstance(accepted_truth, CompactAcceptedTruthV2)

    payload_input = build_compacted_payload_input(
        request=plan.request,
        accepted_truth=accepted_truth,
        budget_after_compact=42,
        accepted_attempt_number=2,
        accepted_proposal_manifest_ref="manifest-ref",
        accepted_proposal_manifest_digest=_DIGEST,
        successful_response_identity=_successful_response_identity(
            run_id=f"compactor:{plan.request.run_id}:attempt:2",
            iteration_id="compact-pipeline-accepted",
        ),
    )

    assert "prompt-label:E1" in payload_input.prompt_local_label_mapping_refs
    assert "prompt-label:C1" in payload_input.prompt_local_label_mapping_refs
    assert payload_input.accepted_evidence_mapping_refs == ("evidence:old",)
    assert payload_input.source_boundary_refs[0] == plan.request.current_input_ref
    assert payload_input.accepted_attempt_number == 2


def _successful_response_identity(
    *,
    run_id: str,
    iteration_id: str,
) -> SuccessfulRunnerResponseIdentity:
    """构造 compact-pipeline fixture 的 event-unique typed identity。

    :param run_id: 当前 fixture 显式提供的 compactor Engine run id。
    :param iteration_id: 当前 fixture 显式提供的 iteration id。
    :returns: provider request id 明确不可用的成功响应身份。
    :raises ValueError: identity 字段非法时抛出。
    """

    return SuccessfulRunnerResponseIdentity(
        effective_provider="test-compactor",
        effective_model="test-compactor-model",
        runner_request_identity=build_runner_request_identity(
            run_id=run_id,
            attempt_id=None,
            execution_id=None,
            iteration_id=iteration_id,
            iteration_index=0,
            runner_call_index=1,
        ),
        provider_request_id_availability=(ProviderRequestIdAvailability.UNAVAILABLE),
        provider_request_id=None,
    )


def test_fallback_decision_input_dispatch_and_fail_closed() -> None:
    """fallback decision helper 统一 selection、budget payload 与 action hint。"""

    snapshot = _source_snapshot(ContextCompactionTriggerSource.REACTIVE)
    memory_policy = default_memory_projection_policy(context_window_size=8192)
    dispatch_decision = build_fallback_decision_input(
        source_snapshot=snapshot,
        context_policy=context_budget_policy_from_threshold_tokens(
            context_window_size=4096,
            soft_threshold_tokens=3000,
            hard_threshold_tokens=3900,
        ),
        memory_policy=memory_policy,
        operation_id="operation-fallback",
        failure_reason="schema_rejected",
        attempt_count=3,
        retry_repair_budget_exhausted=True,
        budget_after_attempted_compact=None,
    )

    assert dispatch_decision.action_hint == FALLBACK_ACTION_DISPATCH
    assert dispatch_decision.selection is not None
    assert dispatch_decision.fallback_handoff is not None
    assert dispatch_decision.failed_payload_input.fallback_action == (FALLBACK_ACTION_DISPATCH)
    assert "fallback_tier" not in (dispatch_decision.failed_payload_input.fallback_input_window or {})

    fail_closed_decision = build_fallback_decision_input(
        source_snapshot=snapshot,
        context_policy=context_budget_policy_from_threshold_tokens(
            context_window_size=64,
            soft_threshold_tokens=32,
            hard_threshold_tokens=48,
        ),
        memory_policy=memory_policy,
        operation_id="operation-fallback",
        failure_reason="schema_rejected",
        attempt_count=3,
        retry_repair_budget_exhausted=True,
        budget_after_attempted_compact=None,
    )

    assert fail_closed_decision.action_hint == FALLBACK_ACTION_FAIL_CLOSED
    assert fail_closed_decision.failed_payload_input.fallback_action == (FALLBACK_ACTION_FAIL_CLOSED)


def test_ordinary_protected_raw_tail_selects_recent_group_and_memory_dedupes() -> None:
    """ordinary raw-tail helper 选择 protected recent group，并按 memory 去重。"""

    snapshot = _source_snapshot(ContextCompactionTriggerSource.PROACTIVE)

    handoff = select_ordinary_protected_raw_tail(
        source_snapshot=snapshot,
        selected_recent_window_turn_floor=1,
        memory=_MemoryView(messages=()),
    )

    assert tuple(block.turn_group_id for block in handoff.material_blocks) == (
        "run-new",
        "run-new",
    )
    assert tuple(message.role for message in handoff.messages) == (
        AgentMessageRole.USER,
        AgentMessageRole.ASSISTANT,
    )
    assert handoff.source_refs == ("event-user-new", "event-answer-new")

    deduped = select_ordinary_protected_raw_tail(
        source_snapshot=snapshot,
        selected_recent_window_turn_floor=1,
        memory=_MemoryView(
            messages=(),
            selected_recent_source_refs=("event-user-new", "event-answer-new"),
        ),
    )

    assert deduped.material_blocks == ()
    assert deduped.messages == ()


def test_ordinary_protected_raw_tail_consumes_projection_cleaned_source() -> None:
    """ordinary raw-tail evidence message 消费 projection-cleaned source。"""

    snapshot = _source_snapshot(ContextCompactionTriggerSource.PROACTIVE)
    material = AcceptedToolEvidenceLLMMaterial(
        tool_name="fins.search",
        query_text="query new",
        source_text="filing page 12",
        result_text="raw evidence new",
    )
    evidence = run_input_material_block(
        block_id="evidence-new",
        section=CompactMaterialSection.EVIDENCE_MATERIAL,
        kind=CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
        text=render_accepted_tool_evidence_for_llm(material),
        canonical_source_refs=("evidence:new",),
        event_sequence=4,
        turn_group_id="run-new",
        accepted_evidence_id="evidence:new",
        tool_result_event_ref="event-tool-result-new",
        tool_call_event_ref="event-tool-call-new",
        payload_refs=("payload-new",),
        accepted_tool_evidence=material,
    )
    raw_tail_snapshot = replace(
        snapshot,
        material_blocks=(*snapshot.material_blocks, evidence),
    )

    handoff = select_ordinary_protected_raw_tail(
        source_snapshot=raw_tail_snapshot,
        selected_recent_window_turn_floor=1,
        memory=_MemoryView(messages=()),
    )
    contents = tuple(message.content for message in handoff.messages if message.content is not None)

    assert any("业务来源：filing page 12" in content for content in contents)
    assert all("event-tool-result-new" not in content for content in contents)
    assert all("payload-new" not in content for content in contents)


def _source_snapshot(
    trigger_source: ContextCompactionTriggerSource,
) -> CompactPipelineSourceSnapshot:
    """构造测试用 source snapshot。

    :param trigger_source: compact trigger source。
    :returns: source snapshot。
    """

    return compact_pipeline_source_snapshot_from_pre_dispatch_view(
        trigger_source=trigger_source,
        run=_run_row(input_event_sequence=5),
        material_view=_material_view(current_input_sequence=5),
    )


def _material_view(*, current_input_sequence: int) -> PreDispatchCompactMaterialView:
    """构造测试用 material view。

    :param current_input_sequence: current input event sequence。
    :returns: pre-dispatch material view。
    """

    blocks = (
        _user_block("old", event_sequence=1, turn_group_id="run-old"),
        _evidence_block("old", event_sequence=2, turn_group_id="run-old"),
        _answer_block("old", event_sequence=3, turn_group_id="run-old"),
        _user_block("new", event_sequence=4, turn_group_id="run-new"),
        _answer_block("new", event_sequence=4, turn_group_id="run-new"),
    )
    boundary = CompactMaterialSourceBoundary(
        latest_compacted_event_id="event-compact-latest",
        latest_compacted_event_sequence=2,
        post_compact_delta_start_sequence=3,
        post_compact_delta_end_sequence=current_input_sequence,
        current_input_event_sequence=current_input_sequence,
    )
    return PreDispatchCompactMaterialView(
        material_blocks=blocks,
        previous_compacted_view=(
            _previous_block(
                label="P1",
                kind=CompactMaterialBlockKind.SESSION_SUMMARY,
                text="previous summary",
            ),
            _previous_block(
                label="P2",
                kind=CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
                text="previous evidence fact",
            ),
        ),
        previous_compacted_readable_view=PreviousCompactReadableView(
            session_summary="previous summary",
            evidence_backed_facts=(
                ReadableFactItemVNext(
                    source_label="P2",
                    claim_text="previous evidence fact",
                ),
            ),
            answer_anchors=(),
            forward_intents=(),
            reference_continuity_items=(),
        ),
        current_input_text="current user input",
        source_boundary=boundary,
        latest_compacted_event_id=boundary.latest_compacted_event_id,
        latest_compacted_event_sequence=boundary.latest_compacted_event_sequence,
        post_compact_delta_start_sequence=boundary.post_compact_delta_start_sequence,
        post_compact_delta_end_sequence=boundary.post_compact_delta_end_sequence,
        represented_evidence_refs=(),
        budget_fragments=(),
    )


def _user_block(suffix: str, *, event_sequence: int, turn_group_id: str) -> RunInputMaterialBlock:
    """构造 user material block。

    :param suffix: block suffix。
    :param event_sequence: event sequence。
    :param turn_group_id: turn group id。
    :returns: run input material block。
    """

    return run_input_material_block(
        block_id=f"user-{suffix}",
        section=CompactMaterialSection.TRACE_MATERIAL,
        kind=CompactMaterialBlockKind.USER_INPUT,
        text=f"user text {suffix}",
        canonical_source_refs=(f"event-user-{suffix}",),
        event_sequence=event_sequence,
        turn_group_id=turn_group_id,
    )


def _answer_block(suffix: str, *, event_sequence: int, turn_group_id: str) -> RunInputMaterialBlock:
    """构造 assistant answer material block。

    :param suffix: block suffix。
    :param event_sequence: event sequence。
    :param turn_group_id: turn group id。
    :returns: run input material block。
    """

    return run_input_material_block(
        block_id=f"answer-{suffix}",
        section=CompactMaterialSection.ANSWER_MATERIAL,
        kind=CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
        text=f"answer text {suffix}",
        canonical_source_refs=(f"event-answer-{suffix}",),
        event_sequence=event_sequence,
        turn_group_id=turn_group_id,
    )


def _evidence_block(suffix: str, *, event_sequence: int, turn_group_id: str) -> RunInputMaterialBlock:
    """构造 accepted evidence material block。

    :param suffix: block suffix。
    :param event_sequence: event sequence。
    :param turn_group_id: turn group id。
    :returns: run input material block。
    """

    material = AcceptedToolEvidenceLLMMaterial(
        tool_name="fins.search",
        query_text=f"query {suffix}",
        source_text=f"source {suffix}",
        result_text=f"raw evidence {suffix}",
    )
    return run_input_material_block(
        block_id=f"evidence-{suffix}",
        section=CompactMaterialSection.EVIDENCE_MATERIAL,
        kind=CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
        text=render_accepted_tool_evidence_for_llm(material),
        canonical_source_refs=(f"evidence:{suffix}",),
        event_sequence=event_sequence,
        turn_group_id=turn_group_id,
        accepted_evidence_id=f"evidence:{suffix}",
        tool_result_event_ref=f"event-tool-result-{suffix}",
        tool_call_event_ref=f"event-tool-call-{suffix}",
        payload_refs=(f"payload-{suffix}",),
        accepted_tool_evidence=material,
    )


def _previous_block(*, label: str, kind: CompactMaterialBlockKind, text: str) -> CompactMaterialBlock:
    """构造 previous compacted view block。

    :param label: prompt-local label。
    :param kind: material kind。
    :param text: block text。
    :returns: compact material block。
    """

    return CompactMaterialBlock(
        block_label=label,
        section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
        kind=kind,
        text=text,
        size_units=len(text),
        source_labels=(),
        canonical_source_refs=(f"previous:{label}",),
        content_digest=sha256_digest_json({"text": text}),
    )


def _run_row(*, input_event_sequence: int) -> RunRow:
    """构造测试用 RunRow。

    :param input_event_sequence: input event sequence。
    :returns: RunRow。
    """

    return RunRow(
        run_id="run-current",
        session_id="session-compact-pipeline",
        status=RunStatus.ACCEPTED,
        client_request_id="client-current",
        input_event_id="event-current-input",
        input_event_sequence=input_event_sequence,
        accepted_event_id="event-run-accepted",
        accepted_event_sequence=input_event_sequence,
        queued_event_id=None,
        queued_event_sequence=None,
        started_event_id=None,
        started_event_sequence=None,
        terminal_event_id=None,
        terminal_event_sequence=None,
        cancel_request_event_id=None,
        current_attempt_id=None,
        source_run_id=None,
        source_run_relation=None,
        execution_target="local",
        queue_policy=RunQueuePolicy.QUEUE,
        created_at="2026-06-19T00:00:00.000000Z",
        updated_at="2026-06-19T00:00:00.000000Z",
        terminal_at=None,
    )


def _budget() -> BudgetEstimate:
    """构造测试用 budget estimate。

    :returns: BudgetEstimate。
    """

    return BudgetEstimate(
        estimated_input_tokens=100,
        input_budget_tokens=4000,
        soft_threshold_tokens=3000,
        hard_threshold_tokens=3600,
        safety_margin_tokens=600,
        estimator_digest=_DIGEST,
        overage_reason=None,
    )


def _candidate_with_evidence_fact() -> CompactCandidateV2:
    """构造引用 E1 evidence label 的 accepted candidate。

    :returns: CompactCandidateV2。
    """

    return CompactCandidateV2(
        schema=COMPACT_OUTPUT_SCHEMA_V2,
        session_summary=None,
        evidence_facts=(
            CompactEvidenceFactV2(
                claim="accepted fact",
                support_labels=("E1",),
            ),
        ),
        answer_anchors=(),
        forward_intents=(),
        reference_continuity=(),
        diagnostics=(),
        explicitly_dropped_sources=(),
    )


def test_memory_policy_digest_helper_is_selection_policy_source() -> None:
    """selection policy digest 可由 memory policy digest 直接传入。"""

    memory_policy = default_memory_projection_policy(context_window_size=8192)
    snapshot = _source_snapshot(ContextCompactionTriggerSource.PROACTIVE)

    plan = build_normal_compact_request_plan(
        source_snapshot=snapshot,
        selection_policy_digest=digest_memory_projection_policy(memory_policy),
        budget_before_compact=_budget(),
        selected_recent_window_turn_floor=(memory_policy.selected_recent_window_turn_floor),
    )

    assert plan.selected_segment.policy_digest == digest_memory_projection_policy(memory_policy)
