"""Host context governance quality checker。

本模块实现 Host compaction candidate quality check。它不
append canonical compact events，不写 memory projection，也不执行 proactive /
reactive orchestration。
"""

from __future__ import annotations

from dayu.host.compaction import (
    CompactInputRange,
    CompactQualityCheckResult,
    CompactQualityIssue,
    CompactionCandidate,
    CompactionRequest,
    EvidenceBackedFactCandidate,
    MinimumPreserveItemCandidate,
    PinnedPatchOperation,
    PinnedStatePatchCandidate,
    PinnedStringTupleFieldPatch,
    PinnedTextFieldPatch,
    PreservationEvidence,
)


def check_compaction_candidate(
    request: CompactionRequest, candidate: CompactionCandidate
) -> CompactQualityCheckResult:
    """检查 compaction candidate 是否可被 Host 接受。

    :param request: Host 构造的 compaction 请求。
    :param candidate: compactor 输出候选。
    :returns: quality check 结果。
    :raises TypeError: ``request`` 或 ``candidate`` 类型非法时抛出。
    """

    if not isinstance(request, CompactionRequest):
        raise TypeError("request must be CompactionRequest")
    if not isinstance(candidate, CompactionCandidate):
        raise TypeError("candidate must be CompactionCandidate")

    issue_collector = _QualityIssueCollector()
    current_user_input_retained = _current_user_input_retained(request, candidate)
    canonical_evidence_refs_retained = _canonical_evidence_refs_retained(
        request, candidate
    )
    evidence_ids = _evidence_ids(candidate.preservation_evidence)
    accepted_evidence_ids = set(request.canonical_evidence_refs)
    evidence_anchors_retained = _evidence_anchors_retained(request, candidate)
    compact_ranges_from_request = _compact_ranges_from_request(request, candidate)
    fact_candidates_accepted = _fact_candidates_accepted(
        request=request,
        candidate=candidate,
        accepted_evidence_ids=accepted_evidence_ids,
    )
    minimum_preserve_items_accepted = _minimum_preserve_items_accepted(
        request=request,
        candidate=candidate,
    )
    open_questions_retained = _open_questions_retained(candidate)
    patch_valid = _pinned_patch_valid(
        candidate.pinned_state_patch_candidate,
        evidence_ids=evidence_ids,
        issue_collector=issue_collector,
    )

    if not current_user_input_retained:
        issue_collector.add(CompactQualityIssue.CURRENT_USER_INPUT_MISSING)
    if not canonical_evidence_refs_retained:
        issue_collector.add(CompactQualityIssue.ACCEPTED_EVIDENCE_REFS_MISSING)
    if _evidence_labels_missing_for_known_facts(request):
        issue_collector.add(CompactQualityIssue.EVIDENCE_LABELS_MISSING)
    if _summary_pretends_evidence_backed_fact(request, candidate):
        issue_collector.add(
            CompactQualityIssue.SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT
        )
    if len(candidate.preservation_evidence) == 0:
        issue_collector.add(CompactQualityIssue.PRESERVATION_EVIDENCE_MISSING)
    if not evidence_anchors_retained:
        issue_collector.add(CompactQualityIssue.EVIDENCE_ANCHOR_NOT_RETAINED)
    if not patch_valid:
        issue_collector.add(CompactQualityIssue.PINNED_PATCH_TRI_STATE_INVALID)
    if not compact_ranges_from_request:
        issue_collector.add(CompactQualityIssue.COMPACT_RANGE_OUTSIDE_REQUEST)
    if not fact_candidates_accepted:
        issue_collector.add(
            CompactQualityIssue.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID
        )
    if (
        len(accepted_evidence_ids) > 0
        and _retained_accepted_evidence_with_no_fact_candidate(
            request=request,
            candidate=candidate,
            accepted_evidence_ids=accepted_evidence_ids,
        )
    ):
        issue_collector.add(
            CompactQualityIssue.ACCEPTED_EVIDENCE_FACT_CANDIDATE_MISSING
        )
    if not minimum_preserve_items_accepted:
        issue_collector.add(
            CompactQualityIssue.MINIMUM_PRESERVE_ITEM_CANDIDATE_INVALID
        )
    if not open_questions_retained:
        issue_collector.add(CompactQualityIssue.OPEN_QUESTIONS_MISSING)

    reasons = issue_collector.reasons()
    return CompactQualityCheckResult(
        accepted=len(reasons) == 0,
        rejection_reasons=reasons,
        current_user_input_retained=current_user_input_retained,
        canonical_evidence_refs_retained=canonical_evidence_refs_retained,
        evidence_backed_fact_candidates_accepted=fact_candidates_accepted,
        minimum_preserve_items_accepted=minimum_preserve_items_accepted,
        evidence_anchors_retained=evidence_anchors_retained,
        open_questions_retained=open_questions_retained,
        retained_canonical_evidence_refs=tuple(
            sorted(set(candidate.preserved_canonical_evidence_refs))
        ),
        dropped_ranges=candidate.dropped_ranges,
        summarized_ranges=candidate.summarized_ranges,
    )


class _QualityIssueCollector:
    """Quality issue 去重收集器。"""

    def __init__(self) -> None:
        """初始化收集器。

        :returns: ``None``。
        """

        self._issues: list[CompactQualityIssue] = []

    def add(self, issue: CompactQualityIssue) -> None:
        """追加拒绝原因。

        :param issue: 拒绝原因。
        :returns: ``None``。
        """

        if issue not in self._issues:
            self._issues.append(issue)

    def reasons(self) -> tuple[CompactQualityIssue, ...]:
        """返回已收集拒绝原因。

        :returns: 拒绝原因 tuple。
        """

        return tuple(self._issues)


def _current_user_input_retained(
    request: CompactionRequest, candidate: CompactionCandidate
) -> bool:
    """判断当前用户输入是否被保留。

    :param request: compaction 请求。
    :param candidate: compaction candidate。
    :returns: 已保留时返回 ``True``。
    """

    current_ref = request.current_input_ref
    return (
        candidate.retained_current_user_input_ref == current_ref
        and current_ref in candidate.preserved_material_source_refs
    )


def _canonical_evidence_refs_retained(
    request: CompactionRequest, candidate: CompactionCandidate
) -> bool:
    """判断 canonical evidence refs 是否全部保留。

    :param request: compaction 请求。
    :param candidate: compaction candidate。
    :returns: 全部保留时返回 ``True``。
    """

    return set(request.canonical_evidence_refs).issubset(
        set(candidate.preserved_canonical_evidence_refs)
    )


def _summary_pretends_evidence_backed_fact(
    request: CompactionRequest, candidate: CompactionCandidate
) -> bool:
    """判断 summary 是否试图创建 evidence-backed fact。

    :param request: compaction 请求。
    :param candidate: compaction candidate。
    :returns: 存在越权 evidence-backed fact 时返回 ``True``。
    """

    summary = candidate.episode_summary_candidate
    if len(summary.proposed_evidence_backed_fact_refs) > 0:
        return True
    evidence_labels = set(request.material_pack.evidence_labels)
    if len(evidence_labels.intersection(summary.confirmed_fact_refs)) > 0:
        return True
    if len(evidence_labels.intersection(summary.proposed_evidence_backed_fact_refs)) > 0:
        return True
    if not set(candidate.preserved_evidence_backed_fact_refs).issubset(
        set(request.evidence_backed_fact_refs)
    ):
        return True
    allowed_fact_refs = set(request.evidence_backed_fact_refs)
    return not set(summary.confirmed_fact_refs).issubset(allowed_fact_refs)


def _evidence_labels_missing_for_known_facts(request: CompactionRequest) -> bool:
    """判断 evidence-backed fact refs 存在但 prompt-local evidence labels 缺失。

    :param request: compaction 请求。
    :returns: 需要 fail-closed 时返回 ``True``。
    """

    return (
        len(request.evidence_backed_fact_refs) > 0
        and len(request.material_pack.evidence_labels) == 0
    )


def _evidence_ids(evidence_items: tuple[PreservationEvidence, ...]) -> set[str]:
    """提取 evidence id 集合。

    :param evidence_items: preservation evidence tuple。
    :returns: evidence id 集合。
    """

    return {evidence.evidence_id for evidence in evidence_items}


def _evidence_anchors_retained(
    request: CompactionRequest, candidate: CompactionCandidate
) -> bool:
    """判断 evidence anchors 是否可回溯到输入。

    :param request: compaction 请求。
    :param candidate: compaction candidate。
    :returns: anchors 完整保留时返回 ``True``。
    """

    evidence_ids = _evidence_ids(candidate.preservation_evidence)
    summary_refs_valid = _refs_non_empty_and_known(
        candidate.episode_summary_candidate.evidence_refs, evidence_ids
    )
    if not summary_refs_valid:
        return False
    current_ref = request.current_input_ref
    retained_input_refs = _retained_input_refs(candidate.preservation_evidence)
    retained_tool_refs = _retained_tool_refs(candidate.preservation_evidence)
    if current_ref not in retained_input_refs:
        return False
    if not set(request.canonical_evidence_refs).issubset(retained_tool_refs):
        return False
    for evidence in candidate.preservation_evidence:
        if not _single_evidence_anchor_valid(request, evidence):
            return False
    return True


def _single_evidence_anchor_valid(
    request: CompactionRequest, evidence: PreservationEvidence
) -> bool:
    """判断单条 evidence anchor 是否来自输入。

    :param request: compaction 请求。
    :param evidence: preservation evidence。
    :returns: anchor 合法时返回 ``True``。
    """

    has_anchor = (
        len(evidence.material_source_refs) > 0
        or len(evidence.canonical_evidence_refs) > 0
        or evidence.memory_snapshot_cursor is not None
        or evidence.compact_input_range is not None
    )
    if not has_anchor:
        return False
    if not set(evidence.material_source_refs).issubset(set(request.material_source_refs)):
        return False
    if not set(evidence.canonical_evidence_refs).issubset(
        set(request.canonical_evidence_refs)
    ):
        return False
    if evidence.memory_snapshot_cursor is not None:
        if request.memory_snapshot_cursor is None:
            return False
        if evidence.memory_snapshot_cursor != request.memory_snapshot_cursor:
            return False
    if evidence.compact_input_range is not None:
        return _range_refs_from_input(request, evidence.compact_input_range)
    return True


def _range_refs_from_input(
    request: CompactionRequest, input_range: CompactInputRange
) -> bool:
    """判断 range 起止 ref 是否来自请求输入。

    :param request: compaction 请求。
    :param input_range: compact input range。
    :returns: 起止 ref 均来自输入时返回 ``True``。
    """

    input_refs = set(request.material_source_refs)
    return (
        input_range.start_input_ref in input_refs
        and input_range.end_input_ref in input_refs
    )


def _compact_ranges_from_request(
    request: CompactionRequest, candidate: CompactionCandidate
) -> bool:
    """判断 candidate 声明的 compact ranges 是否来自可摘要输入范围。

    :param request: compaction 请求。
    :param candidate: compaction candidate。
    :returns: 所有 dropped / summarized range 均来自 older raw turns 时返回 ``True``。
    """

    allowed_refs = set(request.older_raw_turn_refs)
    for input_range in candidate.dropped_ranges + candidate.summarized_ranges:
        if (
            input_range.start_input_ref not in allowed_refs
            or input_range.end_input_ref not in allowed_refs
        ):
            return False
    return True


def _retained_input_refs(
    evidence_items: tuple[PreservationEvidence, ...]
) -> set[str]:
    """汇总 evidence 保留的 input refs。

    :param evidence_items: preservation evidence tuple。
    :returns: input refs 集合。
    """

    retained: set[str] = set()
    for evidence in evidence_items:
        retained.update(evidence.material_source_refs)
    return retained


def _retained_tool_refs(
    evidence_items: tuple[PreservationEvidence, ...]
) -> set[str]:
    """汇总 evidence 保留的 canonical evidence refs。

    :param evidence_items: preservation evidence tuple。
    :returns: canonical evidence refs 集合。
    """

    retained: set[str] = set()
    for evidence in evidence_items:
        retained.update(evidence.canonical_evidence_refs)
    return retained


def _fact_candidates_accepted(
    *,
    request: CompactionRequest,
    candidate: CompactionCandidate,
    accepted_evidence_ids: set[str],
) -> bool:
    """判断 evidence-backed fact candidates 是否满足 Host accept barrier。

    :param request: compaction 请求。
    :param candidate: compaction candidate。
    :param accepted_evidence_ids: 请求内 canonical evidence ids。
    :returns: candidates 合法时返回 ``True``。
    """

    del request
    for fact_candidate in candidate.evidence_backed_fact_candidates:
        if not _single_fact_candidate_accepted(
            fact_candidate, accepted_evidence_ids=accepted_evidence_ids
        ):
            return False
    return True


def _single_fact_candidate_accepted(
    candidate: EvidenceBackedFactCandidate, *, accepted_evidence_ids: set[str]
) -> bool:
    """判断单个 fact candidate 的 evidence refs 是否只指向 canonical evidence。

    :param candidate: fact candidate。
    :param accepted_evidence_ids: 请求内 canonical evidence ids。
    :returns: refs 合法时返回 ``True``。
    """

    return (
        len(candidate.claim_text.strip()) > 0
        and len(candidate.evidence_refs) > 0
        and set(candidate.evidence_refs).issubset(accepted_evidence_ids)
    )


def _retained_accepted_evidence_with_no_fact_candidate(
    *,
    request: CompactionRequest,
    candidate: CompactionCandidate,
    accepted_evidence_ids: set[str],
) -> bool:
    """判断是否存在已保留 canonical evidence 没有任何有效 fact candidate。

    该分支只产生 rejection diagnostic / repair outcome，不构造 fallback fact。

    :param request: compaction 请求。
    :param candidate: compaction candidate。
    :param accepted_evidence_ids: 请求内 canonical evidence ids。
    :returns: 存在缺失时返回 ``True``。
    """

    del request
    covered: set[str] = set()
    for fact_candidate in candidate.evidence_backed_fact_candidates:
        if _single_fact_candidate_accepted(
            fact_candidate, accepted_evidence_ids=accepted_evidence_ids
        ):
            covered.update(fact_candidate.evidence_refs)
    retained = set(candidate.preserved_canonical_evidence_refs).intersection(
        accepted_evidence_ids
    )
    return not retained.issubset(covered)


def _minimum_preserve_items_accepted(
    *, request: CompactionRequest, candidate: CompactionCandidate
) -> bool:
    """判断 minimum preserve item candidates 是否满足 Host accept barrier。

    :param request: compaction 请求。
    :param candidate: compaction candidate。
    :returns: candidates 合法时返回 ``True``。
    """

    allowed_source_refs = set(request.material_source_refs)
    for item in candidate.minimum_preserve_item_candidates:
        if not _single_minimum_preserve_item_accepted(
            item, allowed_source_refs=allowed_source_refs
        ):
            return False
    return True


def _single_minimum_preserve_item_accepted(
    item: MinimumPreserveItemCandidate, *, allowed_source_refs: set[str]
) -> bool:
    """判断单个 minimum preserve item candidate 的 source refs 是否来自输入。

    :param item: minimum preserve item candidate。
    :param allowed_source_refs: compact input event refs。
    :returns: item 合法时返回 ``True``。
    """

    return (
        item.text.strip() != ""
        and len(item.source_refs) > 0
        and set(item.source_refs).issubset(allowed_source_refs)
    )


def _pinned_patch_valid(
    patch: PinnedStatePatchCandidate,
    *,
    evidence_ids: set[str],
    issue_collector: _QualityIssueCollector,
) -> bool:
    """校验 pinned state patch 字段三态与 evidence refs。

    :param patch: pinned state patch candidate。
    :param evidence_ids: 已知 preservation evidence ids。
    :param issue_collector: issue 收集器。
    :returns: patch 合法时返回 ``True``。
    """

    current_goal_valid = _text_patch_valid(
        patch.current_goal,
        evidence_ids=evidence_ids,
        issue_collector=issue_collector,
    )
    confirmed_subjects_valid = _tuple_patch_valid(
        patch.confirmed_subjects,
        evidence_ids=evidence_ids,
        issue_collector=issue_collector,
    )
    user_constraints_valid = _tuple_patch_valid(
        patch.user_constraints,
        evidence_ids=evidence_ids,
        issue_collector=issue_collector,
    )
    open_questions_valid = _tuple_patch_valid(
        patch.open_questions,
        evidence_ids=evidence_ids,
        issue_collector=issue_collector,
    )
    return (
        current_goal_valid
        and confirmed_subjects_valid
        and user_constraints_valid
        and open_questions_valid
    )


def _text_patch_valid(
    patch: PinnedTextFieldPatch,
    *,
    evidence_ids: set[str],
    issue_collector: _QualityIssueCollector,
) -> bool:
    """校验文本字段 patch。

    :param patch: 文本字段 patch。
    :param evidence_ids: 已知 preservation evidence ids。
    :param issue_collector: issue 收集器。
    :returns: patch 合法时返回 ``True``。
    """

    if patch.operation is PinnedPatchOperation.MISSING:
        return patch.value is None and len(patch.evidence_refs) == 0
    if patch.operation is PinnedPatchOperation.CLEAR:
        return _non_missing_patch_evidence_valid(
            patch.evidence_refs,
            evidence_ids=evidence_ids,
            issue_collector=issue_collector,
        ) and patch.value is None
    if patch.operation is PinnedPatchOperation.REPLACE:
        return (
            patch.value is not None
            and _non_missing_patch_evidence_valid(
                patch.evidence_refs,
                evidence_ids=evidence_ids,
                issue_collector=issue_collector,
            )
        )
    return False


def _tuple_patch_valid(
    patch: PinnedStringTupleFieldPatch,
    *,
    evidence_ids: set[str],
    issue_collector: _QualityIssueCollector,
) -> bool:
    """校验字符串 tuple 字段 patch。

    :param patch: 字符串 tuple 字段 patch。
    :param evidence_ids: 已知 preservation evidence ids。
    :param issue_collector: issue 收集器。
    :returns: patch 合法时返回 ``True``。
    """

    if patch.operation is PinnedPatchOperation.MISSING:
        return patch.value is None and len(patch.evidence_refs) == 0
    if patch.operation is PinnedPatchOperation.CLEAR:
        return _non_missing_patch_evidence_valid(
            patch.evidence_refs,
            evidence_ids=evidence_ids,
            issue_collector=issue_collector,
        ) and patch.value is None
    if patch.operation is PinnedPatchOperation.REPLACE:
        return (
            patch.value is not None
            and len(patch.value) > 0
            and _non_missing_patch_evidence_valid(
                patch.evidence_refs,
                evidence_ids=evidence_ids,
                issue_collector=issue_collector,
            )
        )
    return False


def _non_missing_patch_evidence_valid(
    refs: tuple[str, ...],
    *,
    evidence_ids: set[str],
    issue_collector: _QualityIssueCollector,
) -> bool:
    """校验非 missing patch 的 evidence refs。

    :param refs: patch 引用的 evidence refs。
    :param evidence_ids: 已知 preservation evidence ids。
    :param issue_collector: issue 收集器。
    :returns: refs 合法时返回 ``True``。
    """

    if len(refs) == 0:
        issue_collector.add(CompactQualityIssue.PINNED_PATCH_EVIDENCE_REF_MISSING)
        return False
    if not set(refs).issubset(evidence_ids):
        issue_collector.add(CompactQualityIssue.PINNED_PATCH_EVIDENCE_REF_MISSING)
        return False
    return True


def _refs_non_empty_and_known(refs: tuple[str, ...], known_refs: set[str]) -> bool:
    """判断 refs 非空且均存在于 known refs。

    :param refs: 待校验 refs。
    :param known_refs: 已知 refs。
    :returns: refs 合法时返回 ``True``。
    """

    return len(refs) > 0 and set(refs).issubset(known_refs)


def _open_questions_retained(candidate: CompactionCandidate) -> bool:
    """判断 open questions / assumptions 是否仍可追踪。

    :param candidate: compaction candidate。
    :returns: 当前候选未丢失 open questions 时返回 ``True``。
    """

    if len(candidate.episode_summary_candidate.open_questions) > 0:
        return True
    patch = candidate.pinned_state_patch_candidate.open_questions
    if patch.operation is PinnedPatchOperation.REPLACE:
        return patch.value is not None and len(patch.value) > 0
    return False


__all__ = ["check_compaction_candidate"]
