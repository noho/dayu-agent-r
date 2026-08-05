"""Host compaction whole-candidate repair 与 operation budget 测试。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from dayu.contracts.cancellation import CancellationToken
from dayu.host.compact_material import (
    InitialEvidenceMaterial,
    InitialHistoryMaterial,
    build_initial_material_pack,
    initial_segment_selection,
)
from dayu.host.compaction import (
    CompactMaterialBlockKind,
    CompactRepairFeedbackV3,
    CompactSegmentTrigger,
    SelectedBlockProvenance,
    CompactValidationIssueCodeV3,
    CompactValidationIssueV3,
    CompactValidationReportV3,
    CompactionRequest,
    CompactorProposal,
    CompactorProposalError,
)
from dayu.host.compaction_operation import (
    CompactionOperationResult,
    CompactorProposalRunInput,
    run_compaction_attempt,
    run_compaction_operation,
)
from dayu.host.context_governance import (
    build_compact_repair_feedback_v3,
    compact_output_caps_v3_from_memory_policy,
)
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.llm_compaction import LLMCompactionValidationError
from dayu.host.memory import MemoryProjectionPolicy
from tests.host.fake_cancellation import ControllableCancellationToken
from tests.host.fake_compaction import FakeContextCompactor

_DIGEST = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


class _PreparedRecordingCompactor(FakeContextCompactor):
    """记录每次 prepared input，并按 attempt 生成 candidate。"""

    def __init__(self) -> None:
        """初始化 recorder。

        :returns: ``None``。
        """

        super().__init__()
        self.prepared_inputs: list[CompactorProposalRunInput] = []
        self.run_calls = 0

    def prepare_compactor_proposal_run_input(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        compaction_operation_id: str | None,
        compaction_attempt_number: int,
        repair_feedback: CompactRepairFeedbackV3 | None,
    ) -> CompactorProposalRunInput:
        """记录与真实 fake runner 同源的 prepared input。

        :param request: immutable compaction request。
        :param cancellation_token: Host cancellation token。
        :param compaction_operation_id: operation id。
        :param compaction_attempt_number: 全局 attempt number。
        :param repair_feedback: 前次 semantic report。
        :returns: deterministic prepared input。
        """

        prepared = super().prepare_compactor_proposal_run_input(
            request,
            cancellation_token,
            compaction_operation_id=compaction_operation_id,
            compaction_attempt_number=compaction_attempt_number,
            repair_feedback=repair_feedback,
        )
        self.prepared_inputs.append(prepared)
        return prepared

    async def _valid_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """执行父类 deterministic valid proposal。

        :param prepared_input: 同源 prepared input。
        :returns: valid proposal。
        """

        return await super().run_prepared_compactor_proposal(prepared_input)


class _SemanticRejectOnceCompactor(_PreparedRecordingCompactor):
    """首次返回重复业务项，第二次完整重产。"""

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """返回一次 invalid 后的完整 valid candidate。

        :param prepared_input: 同源 prepared input。
        :returns: 当前 attempt proposal。
        """

        self.run_calls += 1
        proposal = await self._valid_proposal(prepared_input)
        if self.run_calls > 1:
            return proposal
        facts = proposal.candidate.evidence_facts
        assert facts
        return CompactorProposal(
            candidate=replace(
                proposal.candidate,
                evidence_facts=facts + facts,
            ),
            successful_response_identity=proposal.successful_response_identity,
        )


class _ParserRejectOnceCompactor(_PreparedRecordingCompactor):
    """首次模拟 raw LLM strict parser reject。"""

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """首次抛 typed validation error，第二次返回完整 candidate。

        :param prepared_input: 同源 prepared input。
        :returns: 第二次 valid proposal。
        :raises LLMCompactionValidationError: 首次 strict parser reject。
        """

        self.run_calls += 1
        if self.run_calls == 1:
            raise LLMCompactionValidationError(
                CompactValidationReportV3(
                    issues=(
                        CompactValidationIssueV3(
                            code=CompactValidationIssueCodeV3.UNKNOWN_JSON_KEY,
                            json_path="$.api_key=sk-secret-123",
                            message="顶层不允许字段；token=token-secret-456",
                            source_labels=(
                                "Bearer bearer-secret-789",
                                "password=password-secret-000",
                            ),
                        ),
                    )
                ),
                successful_response_identity=None,
            )
        return await self._valid_proposal(prepared_input)


class _ExecutionFailOnceCompactor(_PreparedRecordingCompactor):
    """首次 execution failure，第二次成功。"""

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """首次抛 ordinary execution error。

        :param prepared_input: 同源 prepared input。
        :returns: 第二次 valid proposal。
        :raises CompactorProposalError: 首次 transport failure。
        """

        self.run_calls += 1
        if self.run_calls == 1:
            raise CompactorProposalError(
                "provider transport failed",
                successful_response_identity=None,
            )
        return await self._valid_proposal(prepared_input)


class _CancelBetweenAttemptsCompactor(_PreparedRecordingCompactor):
    """attempt 1 失败后请求 parent cancellation。"""

    def __init__(self, cancellation_token: ControllableCancellationToken) -> None:
        """初始化 cancellation fake。

        :param cancellation_token: attempt 1 失败时要取消的 parent token。
        :returns: ``None``。
        """

        super().__init__()
        self._cancellation_token = cancellation_token

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """取消 parent 后返回 attempt 1 execution failure。

        :param prepared_input: 同源 prepared input。
        :returns: 不会返回。
        :raises CompactorProposalError: 始终以 attempt 1 failure 结束。
        """

        self.run_calls += 1
        self._cancellation_token.request_cancel("cancel_between_attempts")
        raise CompactorProposalError(
            "provider transport failed",
            successful_response_identity=None,
        )


class _AlwaysSemanticRejectCompactor(_SemanticRejectOnceCompactor):
    """每次都返回完整但 semantic invalid 的 candidate。"""

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """每次复用首轮 invalid 生成逻辑。

        :param prepared_input: 同源 prepared input。
        :returns: duplicate semantic item candidate。
        """

        self.run_calls = 0
        return await super().run_prepared_compactor_proposal(prepared_input)


class _HardBudgetRejectOnceCompactor(_PreparedRecordingCompactor):
    """首次超过 root hard budget，第二次返回短 candidate。"""

    async def run_prepared_compactor_proposal(
        self,
        prepared_input: CompactorProposalRunInput,
    ) -> CompactorProposal:
        """生成一次长 summary 后完整重产。

        :param prepared_input: 同源 prepared input。
        :returns: 当前 attempt proposal。
        """

        self.run_calls += 1
        proposal = await self._valid_proposal(prepared_input)
        if self.run_calls > 1:
            return proposal
        summary = proposal.candidate.session_summary
        assert summary is not None
        return CompactorProposal(
            candidate=replace(
                proposal.candidate,
                session_summary=replace(summary, text="x" * 1200),
            ),
            successful_response_identity=proposal.successful_response_identity,
        )


@pytest.mark.asyncio
async def test_semantic_reject_gets_bounded_feedback_and_full_replacement() -> None:
    """invalid candidate 后只传 feedback，并从 immutable input 完整重产。"""

    compactor = _SemanticRejectOnceCompactor()
    result = await _run(compactor, max_attempt_number=2)

    assert result.accepted_truth is not None
    assert len(result.rejected_attempts) == 1
    assert [item.repair_feedback for item in compactor.prepared_inputs] == [
        None,
        compactor.prepared_inputs[1].repair_feedback,
    ]
    feedback = compactor.prepared_inputs[1].repair_feedback
    assert feedback is not None
    assert feedback.previous_attempt_number == 1
    assert feedback.request_digest == _request().digest()
    assert feedback.source_boundary_digest == _request().source_boundary_digest()
    assert feedback.issues[0].code is CompactValidationIssueCodeV3.DUPLICATE_SEMANTIC_ITEM
    assert "完整 replacement candidate" in feedback.required_action
    assert compactor.prepared_inputs[0].compact_input == compactor.prepared_inputs[1].compact_input
    assert (
        compactor.prepared_inputs[0].compactor_input_projection_digest
        != compactor.prepared_inputs[1].compactor_input_projection_digest
    )


@pytest.mark.asyncio
async def test_raw_parser_reject_is_semantic_repair_not_execution_retry() -> None:
    """raw strict parser report 进入 semantic repair feedback。"""

    compactor = _ParserRejectOnceCompactor()
    result = await _run(compactor, max_attempt_number=2)

    assert result.accepted_truth is not None
    assert result.rejected_attempts[0].failure_category.value == "quality_check_rejected"
    feedback = compactor.prepared_inputs[1].repair_feedback
    assert feedback is not None
    assert feedback.issues[0].code is CompactValidationIssueCodeV3.UNKNOWN_JSON_KEY
    feedback_json = str(feedback.to_json())
    assert "<redacted>" in feedback_json
    for secret in (
        "sk-secret-123",
        "token-secret-456",
        "bearer-secret-789",
        "password-secret-000",
    ):
        assert secret not in feedback_json


@pytest.mark.asyncio
async def test_execution_failure_does_not_fabricate_validation_feedback() -> None:
    """ordinary execution retry 保持 repair feedback 为 None。"""

    compactor = _ExecutionFailOnceCompactor()
    result = await _run(compactor, max_attempt_number=2)

    assert result.accepted_truth is not None
    assert [item.repair_feedback for item in compactor.prepared_inputs] == [None, None]
    assert result.rejected_attempts[0].failure_category.value == "proposal_failed"


@pytest.mark.asyncio
async def test_cancellation_after_attempt_one_failure_stops_before_attempt_two() -> None:
    """attempt 1 failure 后的 parent cancellation 阻止 attempt 2 prepare。"""

    token = ControllableCancellationToken()
    compactor = _CancelBetweenAttemptsCompactor(token)
    result = await _run(
        compactor,
        max_attempt_number=2,
        cancellation_token=token,
    )

    assert result.accepted_truth is None
    assert result.failure_reason == "cancellation_requested"
    assert compactor.run_calls == 1
    assert len(compactor.prepared_inputs) == 1
    assert tuple(item.failure_category.value for item in result.rejected_attempts) == (
        "proposal_failed",
        "cancellation_requested",
    )


@pytest.mark.asyncio
async def test_all_invalid_exhaust_returns_no_partial_truth() -> None:
    """全局 attempt exhaust 不泄漏 rejected candidate 或 pass truth。"""

    compactor = _AlwaysSemanticRejectCompactor()
    result = await _run(compactor, max_attempt_number=2)

    assert result.accepted_truth is None
    assert result.accepted_attempt_number is None
    assert result.accepted_successful_response_identity is None
    assert result.failure_reason == "quality_check_rejected"
    assert len(result.rejected_attempts) == 2
    assert compactor.prepared_inputs[0].repair_feedback is None
    assert compactor.prepared_inputs[1].repair_feedback is not None


@pytest.mark.asyncio
async def test_root_hard_budget_reject_routes_whole_candidate_repair() -> None:
    """hard budget 只在 root candidate 上校验，并路由完整重产。"""

    compactor = _HardBudgetRejectOnceCompactor()
    policy = _policy(session_summary_char_cap=2000)
    result = await _run(
        compactor,
        max_attempt_number=2,
        request=_request(hard_threshold_tokens=300, policy=policy),
        policy=policy,
    )

    assert result.accepted_truth is not None
    assert len(result.rejected_attempts) == 1
    assert result.rejected_attempts[0].failure_category.value == "hard_threshold_after_compact"
    feedback = compactor.prepared_inputs[1].repair_feedback
    assert feedback is not None
    assert feedback.issues[0].code is CompactValidationIssueCodeV3.POLICY_SIZE_CAP_EXCEEDED


@pytest.mark.asyncio
async def test_cancelled_operation_never_calls_compactor() -> None:
    """Host cancellation 在 proposal 前 fail closed。"""

    token = ControllableCancellationToken()
    token.request_cancel("test_cancel")
    compactor = _PreparedRecordingCompactor()

    result = await run_compaction_operation(
        request=_request(),
        compactor=compactor,
        first_attempt_number=1,
        max_attempt_number=2,
        cancellation_token=token,
        memory_policy=_policy(),
    )

    assert result.accepted_truth is None
    assert result.failure_reason == "cancellation_requested"
    assert compactor.prepared_inputs == []


@pytest.mark.asyncio
async def test_accepted_result_missing_manifest_or_response_identity_fails_closed() -> None:
    """accepted truth 缺 manifest/response identity 时 guard 必须 fail closed。"""

    result = await _run(_PreparedRecordingCompactor(), max_attempt_number=1)

    assert result.accepted_truth is not None
    with pytest.raises(
        RuntimeError,
        match="accepted compaction is missing proposal manifest reference",
    ):
        result.required_proposal_manifest_reference()
    missing_identity = replace(
        result,
        accepted_successful_response_identity=None,
    )
    with pytest.raises(
        RuntimeError,
        match="accepted compaction is missing successful response identity",
    ):
        missing_identity.required_successful_response_identity()


@pytest.mark.asyncio
async def test_mismatched_initial_feedback_fails_before_provider_call() -> None:
    """直接注入跨 request feedback 时复用 non-repairable failure 且不调用 provider。"""

    request = _request()
    feedback = build_compact_repair_feedback_v3(
        CompactValidationReportV3(
            issues=(
                CompactValidationIssueV3(
                    code=CompactValidationIssueCodeV3.UNKNOWN_JSON_KEY,
                    json_path="$.unexpected",
                    message="unexpected key",
                    source_labels=(),
                ),
            )
        ),
        request_digest="sha256:" + ("f" * 64),
        source_boundary_digest=request.source_boundary_digest(),
        previous_attempt_number=1,
    )
    compactor = _PreparedRecordingCompactor()

    result = await run_compaction_attempt(
        request=request,
        compactor=compactor,
        attempt_number=2,
        max_attempt_number=3,
        cancellation_token=ControllableCancellationToken(),
        compaction_operation_id="operation-feedback-mismatch",
        memory_policy=_policy(),
        repair_feedback=feedback,
    )

    assert compactor.prepared_inputs == []
    assert compactor.run_calls == 0
    assert result.accepted_truth is None
    assert result.failure_reason == "proposal_failed"
    assert result.next_repair_feedback is None
    assert len(result.rejected_attempts) == 1
    assert result.rejected_attempts[0].repairable is False


@pytest.mark.asyncio
async def test_root_boundary_mismatch_fails_before_provider_call() -> None:
    """root selected ids 与 compact boundary 不一致时不产生 durable accepted truth。"""

    request = _request()
    selection = request.segment_selection
    partial_request = replace(
        request,
        segment_selection=replace(
            selection,
            selected_block_ids=selection.selected_block_ids[:-1],
            selected_block_provenance=(selection.selected_block_provenance[:-1]),
            selection_digest="sha256:" + ("9" * 64),
        ),
    )
    compactor = _PreparedRecordingCompactor()

    result = await run_compaction_operation(
        request=partial_request,
        compactor=compactor,
        first_attempt_number=1,
        max_attempt_number=2,
        cancellation_token=ControllableCancellationToken(),
        compaction_operation_id="operation-root-boundary-mismatch",
        memory_policy=_policy(),
    )

    assert compactor.prepared_inputs == []
    assert result.accepted_truth is None
    assert result.failure_reason == "proposal_failed"
    assert result.next_repair_feedback is None
    assert result.rejected_attempts[0].repairable is False


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch_kind", ("unknown_block", "source_ref", "packed_digest"))
async def test_root_selected_provenance_mismatch_fails_before_provider_call(
    mismatch_kind: str,
) -> None:
    """等数量 id/ref/digest mismatch 都不能通过 root provider boundary。

    :param mismatch_kind: 待伪造的 provenance 字段。
    """

    request = _request()
    selection = request.segment_selection
    original = selection.selected_block_provenance[0]
    if mismatch_kind == "unknown_block":
        forged = SelectedBlockProvenance(
            block_id="unknown-selected-block",
            canonical_source_refs=("unknown-source-ref",),
            packed_content_digest=original.packed_content_digest,
        )
    elif mismatch_kind == "source_ref":
        forged = replace(
            original,
            canonical_source_refs=("forged-source-ref",),
        )
    else:
        forged = replace(
            original,
            packed_content_digest="sha256:" + ("7" * 64),
        )
    forged_provenance = (forged, *selection.selected_block_provenance[1:])
    forged_ids = tuple(item.block_id for item in forged_provenance)
    forged_request = replace(
        request,
        segment_selection=replace(
            selection,
            selected_block_ids=forged_ids,
            selected_block_provenance=forged_provenance,
            selection_digest="sha256:" + ("8" * 64),
        ),
    )
    compactor = _PreparedRecordingCompactor()

    result = await run_compaction_operation(
        request=forged_request,
        compactor=compactor,
        first_attempt_number=1,
        max_attempt_number=2,
        cancellation_token=ControllableCancellationToken(),
        compaction_operation_id=f"operation-root-{mismatch_kind}",
        memory_policy=_policy(),
    )

    assert compactor.prepared_inputs == []
    assert compactor.run_calls == 0
    assert result.accepted_truth is None
    assert result.failure_reason == "proposal_failed"
    assert result.next_repair_feedback is None
    assert result.rejected_attempts[0].repairable is False


@pytest.mark.asyncio
async def test_current_input_ref_overlap_fails_before_provider_call() -> None:
    """绕过 pipeline 注入 current/source ref overlap 时 operation 仍 fail closed。"""

    request = _request()
    selected_ref = request.material_pack.evidence_material[0].canonical_source_refs[0]
    forged_pack = replace(
        request.material_pack,
        current_input_anchor=replace(
            request.material_pack.current_input_anchor,
            canonical_source_refs=(selected_ref,),
        ),
    )
    forged_request = replace(request, material_pack=forged_pack)
    compactor = _PreparedRecordingCompactor()

    result = await run_compaction_operation(
        request=forged_request,
        compactor=compactor,
        first_attempt_number=1,
        max_attempt_number=2,
        cancellation_token=ControllableCancellationToken(),
        compaction_operation_id="operation-current-ref-overlap",
        memory_policy=_policy(),
    )

    assert compactor.prepared_inputs == []
    assert compactor.run_calls == 0
    assert result.accepted_truth is None
    assert result.failure_reason == "proposal_failed"
    assert result.next_repair_feedback is None
    assert result.rejected_attempts[0].repairable is False


async def _run(
    compactor: FakeContextCompactor,
    *,
    max_attempt_number: int,
    request: CompactionRequest | None = None,
    policy: MemoryProjectionPolicy | None = None,
    cancellation_token: ControllableCancellationToken | None = None,
) -> CompactionOperationResult:
    """执行标准 operation。

    :param compactor: 测试 compactor。
    :param max_attempt_number: 全局 attempt 上限。
    :param request: 可选自定义 request。
    :param policy: 可选自定义 Memory policy。
    :param cancellation_token: 可选 parent cancellation token。
    :returns: compaction operation result。
    """

    effective_policy = _policy() if policy is None else policy
    return await run_compaction_operation(
        request=_request(policy=effective_policy) if request is None else request,
        compactor=compactor,
        first_attempt_number=1,
        max_attempt_number=max_attempt_number,
        cancellation_token=(ControllableCancellationToken() if cancellation_token is None else cancellation_token),
        compaction_operation_id="operation-test",
        memory_policy=effective_policy,
    )


def _request(
    *,
    hard_threshold_tokens: int = 4000,
    policy: MemoryProjectionPolicy | None = None,
) -> CompactionRequest:
    """构造标准 proactive compaction request。

    :param hard_threshold_tokens: operation root hard budget。
    :param policy: 与 request output caps 同源的 Memory policy。
    :returns: deterministic request。
    """

    material_pack = build_initial_material_pack(
        current_input_ref="input-current",
        current_input_text="继续分析当前问题",
        history_materials=(
            InitialHistoryMaterial(
                canonical_source_ref="input-older",
                text="此前助手给出现金流结论",
                kind=CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
            ),
        ),
        evidence_materials=(
            InitialEvidenceMaterial(
                canonical_source_ref="evidence-1",
                accepted_evidence_id="accepted-evidence-1",
                tool_result_event_ref="event-result-1",
                tool_call_event_ref="event-call-1",
                readable_tool_name="财报检索",
                readable_query_text="查询现金流",
                raw_result_text="经营现金流同比增长",
                readable_source_text="年度财报现金流量表",
                payload_refs=("payload-evidence-1",),
            ),
        ),
    )
    effective_policy = _policy() if policy is None else policy
    return CompactionRequest(
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
        session_id="session-operation",
        run_id="run-operation",
        attempt_id=None,
        execution_id=None,
        memory_snapshot_cursor=7,
        material_pack=material_pack,
        segment_selection=initial_segment_selection(
            trigger_source=CompactSegmentTrigger.PROACTIVE,
            input_cursor=2,
            material_pack=material_pack,
        ),
        evidence_backed_fact_refs=("fact-existing-1",),
        recent_raw_turn_refs=("input-current",),
        older_raw_turn_refs=("input-older",),
        existing_episode_summary_refs=("summary-1",),
        budget_before_compact=BudgetEstimate(
            estimated_input_tokens=100,
            input_budget_tokens=200,
            soft_threshold_tokens=120,
            hard_threshold_tokens=hard_threshold_tokens,
            safety_margin_tokens=20,
            estimator_digest=_DIGEST,
            overage_reason=None,
        ),
        output_caps=compact_output_caps_v3_from_memory_policy(effective_policy),
    )


def _policy(*, session_summary_char_cap: int = 1024) -> MemoryProjectionPolicy:
    """构造与 Context Governance 共用的 Memory policy。

    :param session_summary_char_cap: summary size cap。
    :returns: deterministic policy。
    """

    return MemoryProjectionPolicy(
        context_window_size=8192,
        selected_recent_window_item_cap=8,
        selected_recent_window_char_cap=4096,
        selected_recent_window_turn_floor=1,
        fallback_selected_recent_window_item_cap=4,
        fallback_selected_recent_window_char_cap=2048,
        evidence_fact_item_cap=8,
        evidence_fact_char_cap=4096,
        evidence_fact_floor=0,
        session_summary_char_cap=session_summary_char_cap,
        answer_anchor_item_cap=8,
        answer_anchor_char_cap=4096,
        forward_intent_item_cap=8,
        forward_intent_char_cap=4096,
        reference_continuity_item_cap=8,
        reference_continuity_char_cap=4096,
        reference_continuity_item_floor=0,
        max_lag_events_for_inline_delta=4,
        max_delta_repair_events=16,
        policy_ref="test-operation-v3",
    )
