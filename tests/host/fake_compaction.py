"""Host 测试专用 deterministic context compactor。

本模块位于 tests 包下，只允许测试显式注入一个稳定 compactor。生产代码
不得导入 tests helper；真实生产装配必须显式提供 ``ContextCompactor``。
"""

from __future__ import annotations

from dayu.host.compaction import (
    CompactInputRange,
    CompactionCandidate,
    CompactionRequest,
    ContextCompactor,
    EpisodeSummaryCandidate,
    EvidenceBackedFactCandidate,
    EvidenceBackedFactKind,
    MinimumPreserveItemCandidate,
    MinimumPreserveReason,
    PinnedPatchOperation,
    PinnedStatePatchCandidate,
    PinnedStringTupleFieldPatch,
    PinnedTextFieldPatch,
    PreservationEvidence,
)
from dayu.host.evidence import AcceptedEvidenceEnvelope

_FAKE_COMPACTION_SYSTEM_PROMPT = (
    "Deterministic fake context compactor preserving current input and accepted facts."
)
_FAKE_SUMMARY_TOKEN_ESTIMATE = 120
_HARD_THRESHOLD_ACCEPTANCE_MARGIN_TOKENS = 1
_MIN_COMPACTED_CONTEXT_BUDGET_TOKENS = 0


class FakeContextCompactor(ContextCompactor):
    """Deterministic context compactor。

    该实现只根据 typed request 构造稳定 candidate，不调用 LLM，不访问外部
    状态，不应作为生产默认 compactor。
    """

    async def compact(self, request: CompactionRequest) -> CompactionCandidate:
        """生成 deterministic compaction candidate。

        :param request: Host 构造的 compaction 请求。
        :returns: deterministic compaction candidate。
        :raises TypeError: ``request`` 类型非法时抛出。
        """

        if not isinstance(request, CompactionRequest):
            raise TypeError("request must be CompactionRequest")
        evidence = _preservation_evidence(request)
        evidence_refs = tuple(evidence_item.evidence_id for evidence_item in evidence)
        summarized_ranges = _summarized_ranges(request)
        return CompactionCandidate(
            candidate_id=f"fake-compact:{request.run_id}",
            episode_summary_candidate=EpisodeSummaryCandidate(
                candidate_id=f"fake-summary:{request.run_id}",
                episode_title=f"Session {request.session_id} compact summary",
                goal=request.current_message_summary.summary_text,
                completed_actions=_completed_actions(request),
                confirmed_fact_refs=request.evidence_backed_fact_refs,
                confirmed_fact_summaries=_confirmed_fact_summaries(request),
                user_constraints=_user_constraints(request),
                open_questions=("continue-current-run",),
                next_step="preserve current input and accepted tool facts",
                tool_finding_refs=request.accepted_evidence_refs,
                source_event_refs=request.input_event_refs,
                evidence_refs=evidence_refs,
            ),
            pinned_state_patch_candidate=PinnedStatePatchCandidate(
                candidate_id=f"fake-pinned-patch:{request.run_id}",
                current_goal=PinnedTextFieldPatch(
                    operation=PinnedPatchOperation.REPLACE,
                    value=request.current_message_summary.summary_text,
                    evidence_refs=evidence_refs,
                ),
                confirmed_subjects=PinnedStringTupleFieldPatch(
                    operation=PinnedPatchOperation.REPLACE,
                    value=_confirmed_subjects(request),
                    evidence_refs=evidence_refs,
                ),
                user_constraints=PinnedStringTupleFieldPatch(
                    operation=PinnedPatchOperation.REPLACE,
                    value=_user_constraints(request),
                    evidence_refs=evidence_refs,
                ),
                open_questions=PinnedStringTupleFieldPatch(
                    operation=PinnedPatchOperation.REPLACE,
                    value=("continue-current-run",),
                    evidence_refs=evidence_refs,
                ),
            ),
            preservation_evidence=evidence,
            evidence_backed_fact_candidates=_fact_candidates(request),
            minimum_preserve_item_candidates=_minimum_preserve_items(request),
            retained_current_user_input_ref=(
                request.current_message_summary.current_user_input_ref
            ),
            preserved_input_event_refs=request.input_event_refs,
            preserved_accepted_evidence_refs=request.accepted_evidence_refs,
            preserved_evidence_backed_fact_refs=request.evidence_backed_fact_refs,
            dropped_ranges=(),
            summarized_ranges=summarized_ranges,
            budget_after_compact=_budget_after_compact(request),
        )


def _preservation_evidence(
    request: CompactionRequest,
) -> tuple[PreservationEvidence, ...]:
    """构造 deterministic preservation evidence。

    :param request: compaction 请求。
    :returns: preservation evidence tuple。
    """

    return (
        PreservationEvidence(
            evidence_id=f"fake-evidence:{request.run_id}:primary",
            input_event_refs=request.input_event_refs,
            accepted_evidence_refs=request.accepted_evidence_refs,
            memory_snapshot_cursor=request.memory_snapshot_cursor,
            compact_input_range=_range_for_request(request),
        ),
    )


def _range_for_request(request: CompactionRequest) -> CompactInputRange | None:
    """根据请求构造输入范围。

    :param request: compaction 请求。
    :returns: 输入范围；输入为空时为 ``None``。
    """

    if len(request.input_event_refs) == 0:
        return None
    return CompactInputRange(
        range_ref=f"fake-range:{request.run_id}:all-inputs",
        start_input_ref=request.input_event_refs[0],
        end_input_ref=request.input_event_refs[-1],
    )


def _summarized_ranges(request: CompactionRequest) -> tuple[CompactInputRange, ...]:
    """构造被摘要输入范围。

    :param request: compaction 请求。
    :returns: summarized ranges。
    """

    if len(request.older_raw_turn_refs) == 0:
        return ()
    return (
        CompactInputRange(
            range_ref=f"fake-range:{request.run_id}:older-raw-turns",
            start_input_ref=request.older_raw_turn_refs[0],
            end_input_ref=request.older_raw_turn_refs[-1],
        ),
    )


def _completed_actions(request: CompactionRequest) -> tuple[str, ...]:
    """构造 completed actions 摘要。

    :param request: compaction 请求。
    :returns: completed actions。
    """

    if len(request.older_raw_turn_refs) == 0:
        return ("preserved current turn",)
    return (f"summarized {len(request.older_raw_turn_refs)} older raw turns",)


def _confirmed_fact_summaries(request: CompactionRequest) -> tuple[str, ...]:
    """构造 confirmed fact summaries。

    :param request: compaction 请求。
    :returns: confirmed fact summaries。
    """

    if len(request.evidence_backed_fact_refs) == 0:
        return ("no evidence-backed facts in input",)
    return tuple(
        f"evidence-backed:{fact_ref}"
        for fact_ref in request.evidence_backed_fact_refs
    )


def _confirmed_subjects(request: CompactionRequest) -> tuple[str, ...]:
    """构造 pinned confirmed subjects。

    :param request: compaction 请求。
    :returns: confirmed subjects。
    """

    if len(request.evidence_backed_fact_refs) > 0:
        return tuple(
            f"subject:{fact_ref}" for fact_ref in request.evidence_backed_fact_refs
        )
    return (f"subject:{request.current_message_summary.current_user_input_ref}",)


def _fact_candidates(
    request: CompactionRequest,
) -> tuple[EvidenceBackedFactCandidate, ...]:
    """根据 accepted evidence envelope 内容构造 deterministic fact candidates。

    :param request: compaction 请求。
    :returns: fact candidate tuple。
    """

    return tuple(
        EvidenceBackedFactCandidate(
            candidate_id=f"fake-fact:{request.run_id}:{index}",
            claim_text=_fact_claim_from_envelope(envelope),
            evidence_kind=EvidenceBackedFactKind.OBSERVED_VALUE,
            evidence_refs=(envelope.evidence_id,),
            attributes={},
        )
        for index, envelope in enumerate(request.accepted_evidence_envelopes)
    )


def _fact_claim_from_envelope(envelope: AcceptedEvidenceEnvelope) -> str:
    """从 accepted evidence envelope 预览派生 fake fact claim。

    :param envelope: accepted evidence envelope。
    :returns: deterministic claim 文本。
    """

    result_preview = envelope.result_ref.result_preview
    if result_preview is None:
        return f"Accepted evidence has no preview: {envelope.evidence_id}"
    return f"Accepted evidence preview: {result_preview}"


def _minimum_preserve_items(
    request: CompactionRequest,
) -> tuple[MinimumPreserveItemCandidate, ...]:
    """根据当前输入构造 deterministic minimum preserve item。

    :param request: compaction 请求。
    :returns: minimum preserve item candidate tuple。
    """

    return (
        MinimumPreserveItemCandidate(
            item_id=f"fake-preserve:{request.run_id}:current-input",
            label="current input",
            text=request.current_message_summary.summary_text,
            source_refs=(request.current_message_summary.current_user_input_ref,),
            preserve_reason=MinimumPreserveReason.NEEDED_FOR_RECENT_REFERENCE,
        ),
    )


def _user_constraints(request: CompactionRequest) -> tuple[str, ...]:
    """构造用户约束摘要。

    :param request: compaction 请求。
    :returns: 用户约束摘要。
    """

    return (f"keep-current-input:{request.current_message_summary.current_user_input_ref}",)


def _budget_after_compact(request: CompactionRequest) -> int:
    """按真实 LLM compactor 语义估算 compact 后预算并约束在 hard threshold 内。

    :param request: compaction 请求。
    :returns: compact 后 token 估算。
    """

    estimated_budget = (
        request.budget_before_compact.estimated_input_tokens
        + _FAKE_SUMMARY_TOKEN_ESTIMATE
        + len(request.accepted_evidence_refs)
        + len(request.evidence_backed_fact_refs)
        + len(_FAKE_COMPACTION_SYSTEM_PROMPT)
    )
    return _cap_budget_within_hard_threshold(
        estimated_budget,
        hard_threshold_tokens=request.budget_before_compact.hard_threshold_tokens,
    )


def _cap_budget_within_hard_threshold(
    estimated_budget_tokens: int, *, hard_threshold_tokens: int
) -> int:
    """将 fake candidate 预算约束到 Host hard-threshold 可接受区间。

    Fake compactor 是测试 deterministic compactor。它复用真实 compactor 的保守
    估算作为语义基础，但不能生成会被 Host hard-threshold recheck 拒绝的
    accepted candidate。若输入 hard threshold 非正，非负 candidate 不可能满足
    ``budget < hard_threshold``，因此只返回非负下界，避免构造非法负预算。

    :param estimated_budget_tokens: 原始 compact 后 token 估算。
    :param hard_threshold_tokens: Host hard threshold token 数。
    :returns: 非负且在可表达时小于 hard threshold 的 token 估算。
    """

    if hard_threshold_tokens <= _MIN_COMPACTED_CONTEXT_BUDGET_TOKENS:
        return _MIN_COMPACTED_CONTEXT_BUDGET_TOKENS
    accepted_budget_ceiling = (
        hard_threshold_tokens - _HARD_THRESHOLD_ACCEPTANCE_MARGIN_TOKENS
    )
    if accepted_budget_ceiling < _MIN_COMPACTED_CONTEXT_BUDGET_TOKENS:
        return _MIN_COMPACTED_CONTEXT_BUDGET_TOKENS
    return min(estimated_budget_tokens, accepted_budget_ceiling)


__all__ = ["FakeContextCompactor"]
