"""Host Context Governance 的 deterministic v2 accept owner。

本模块唯一负责把 strict parsed candidate 验收为可提交 truth。它不写
artifact/EventLog/Memory，也不执行 compactor retry。
"""

from __future__ import annotations

import json

from dayu.host.compaction import (
    COMPACT_ANSWER_SOURCE_KINDS_V2,
    COMPACT_FACT_CONTEXT_SOURCE_KINDS_V2,
    COMPACT_FACT_SOURCE_KINDS_V2,
    COMPACT_FORWARD_SOURCE_KINDS_V2,
    COMPACT_REFERENCE_SOURCE_KINDS_V2,
    MAX_COMPACT_REPAIR_FEEDBACK_CHARS,
    MAX_COMPACT_REPAIR_ISSUES,
    MAX_COMPACT_REPAIR_ISSUE_MESSAGE_CHARS,
    CompactAcceptedTruthV2,
    CompactAnswerAnchorV2,
    CompactCandidateDiagnosticV2,
    CompactCandidateV2,
    CompactDropReasonV2,
    CompactEvidenceFactV2,
    CompactExplicitlyDroppedCoverageV2,
    CompactForwardIntentV2,
    CompactInputV2,
    CompactReferenceContinuityV2,
    CompactRepairFeedbackV2,
    CompactRepresentedCoverageV2,
    CompactRepresentedSourceV2,
    CompactSemanticSectionV2,
    CompactSessionSummaryV2,
    CompactSourceKindV2,
    CompactValidationIssueCodeV2,
    CompactValidationIssueV2,
    CompactValidationReportV2,
    _COMPACT_ACCEPTANCE_PERMIT,
)
from dayu.host.memory import MemoryProjectionPolicy, estimate_memory_size_units
from dayu.runtime.diagnostic_text import (
    redact_sensitive_diagnostic_values,
    truncate_diagnostic_text,
)

_REPAIR_REDACTION_MARKER = "<redacted>"
_REPAIR_TRUNCATED_SUFFIX = "..."
_EVIDENCE_FACTS_SIZE_MEASUREMENT = "各 claim 字符数之和"
_ANSWER_ANCHORS_SIZE_MEASUREMENT = "每项 title、一个换行符和 detail 的字符数之和"
_FORWARD_INTENTS_SIZE_MEASUREMENT = "各 text 字符数之和"
_REFERENCE_CONTINUITY_SIZE_MEASUREMENT = "各 text 字符数之和"


CompactAcceptanceResultV2 = CompactAcceptedTruthV2 | CompactValidationReportV2
"""Host acceptance 的 success/reject 二臂结果。"""


def accept_compact_candidate_v2(
    compact_input: CompactInputV2,
    candidate: CompactCandidateV2,
    memory_policy: MemoryProjectionPolicy,
) -> CompactAcceptanceResultV2:
    """按固定顺序验收完整 v2 candidate。

    :param compact_input: immutable root/pass input。
    :param candidate: strict parser 产出的完整 candidate。
    :param memory_policy: Memory owner 的同一 typed policy instance。
    :returns: accepted truth 或 deterministic reject report。
    :raises TypeError: 参数类型非法时抛出。
    """

    if not isinstance(compact_input, CompactInputV2):
        raise TypeError("compact_input must be CompactInputV2")
    if not isinstance(candidate, CompactCandidateV2):
        raise TypeError("candidate must be CompactCandidateV2")
    if not isinstance(memory_policy, MemoryProjectionPolicy):
        raise TypeError("memory_policy must be MemoryProjectionPolicy")

    issues: list[CompactValidationIssueV2] = []
    boundary_order = {entry.source_label: index for index, entry in enumerate(compact_input.source_boundary)}
    _collect_label_and_kind_issues(compact_input, candidate, issues)
    represented = _represented_sections(candidate)
    _collect_coverage_issues(compact_input, candidate, represented, issues)
    _collect_duplicate_and_contradiction_issues(candidate, issues)
    _collect_information_issues(compact_input, candidate, represented, issues)
    _collect_policy_issues(candidate, memory_policy, issues)
    if issues:
        return _validation_report(issues)

    normalized = _canonical_candidate(candidate, boundary_order)
    normalized_represented = _represented_sections(normalized)
    represented_sources = tuple(
        CompactRepresentedSourceV2(
            source_label=entry.source_label,
            sections=normalized_represented[entry.source_label],
        )
        for entry in compact_input.source_boundary
        if entry.source_label in normalized_represented
    )
    drops_by_label = {drop.source_label: drop for drop in normalized.explicitly_dropped_sources}
    dropped = tuple(
        drops_by_label[entry.source_label]
        for entry in compact_input.source_boundary
        if entry.source_label in drops_by_label
    )
    return CompactAcceptedTruthV2(
        candidate=normalized,
        source_boundary=compact_input.source_boundary,
        represented_coverage=CompactRepresentedCoverageV2(sources=represented_sources),
        explicitly_dropped_coverage=CompactExplicitlyDroppedCoverageV2(drops=dropped),
        current_input_ref=compact_input.current_input.source_ref,
        _permit=_COMPACT_ACCEPTANCE_PERMIT,
    )


def build_compact_repair_feedback_v2(
    report: CompactValidationReportV2,
    *,
    request_digest: str,
    source_boundary_digest: str,
    previous_attempt_number: int,
) -> CompactRepairFeedbackV2:
    """从 reject report 构造 bounded、脱敏的 Host internal feedback。

    :param report: 前次 semantic validation report。
    :param request_digest: 产生报告的 immutable request digest。
    :param source_boundary_digest: 产生报告的 source boundary digest。
    :param previous_attempt_number: 前次 attempt number。
    :returns: 满足 32/240/8192 边界的 typed feedback。
    :raises TypeError: report 类型非法时抛出。
    :raises ValueError: attempt number 非正数时抛出。
    """

    if not isinstance(report, CompactValidationReportV2):
        raise TypeError("report must be CompactValidationReportV2")
    if previous_attempt_number <= 0:
        raise ValueError("previous_attempt_number must be positive")
    bounded_all = tuple(_bounded_issue_message(issue) for issue in report.issues)
    selected = list(bounded_all[:MAX_COMPACT_REPAIR_ISSUES])
    additional = len(bounded_all) - len(selected)
    feedback = CompactRepairFeedbackV2(
        request_digest=request_digest,
        source_boundary_digest=source_boundary_digest,
        previous_attempt_number=previous_attempt_number,
        issues=tuple(selected),
        additional_issue_count=additional,
    )
    while _feedback_char_count(feedback) > MAX_COMPACT_REPAIR_FEEDBACK_CHARS and len(selected) > 1:
        selected.pop()
        additional += 1
        feedback = CompactRepairFeedbackV2(
            request_digest=request_digest,
            source_boundary_digest=source_boundary_digest,
            previous_attempt_number=previous_attempt_number,
            issues=tuple(selected),
            additional_issue_count=additional,
        )
    while _feedback_char_count(feedback) > MAX_COMPACT_REPAIR_FEEDBACK_CHARS:
        only_issue = selected[0]
        if len(only_issue.source_labels) == 0:
            raise RuntimeError("bounded repair feedback exceeds total character cap")
        selected[0] = CompactValidationIssueV2(
            code=only_issue.code,
            json_path=only_issue.json_path,
            message=only_issue.message,
            source_labels=only_issue.source_labels[:-1],
        )
        feedback = CompactRepairFeedbackV2(
            request_digest=request_digest,
            source_boundary_digest=source_boundary_digest,
            previous_attempt_number=previous_attempt_number,
            issues=tuple(selected),
            additional_issue_count=additional,
        )
    return feedback


def _collect_label_and_kind_issues(
    compact_input: CompactInputV2,
    candidate: CompactCandidateV2,
    issues: list[CompactValidationIssueV2],
) -> None:
    """收集 label existence、重复与 source-kind 问题。

    :param compact_input: strict v2 input。
    :param candidate: strict candidate。
    :param issues: issue accumulator。
    :returns: ``None``。
    """

    _check_labels(
        compact_input,
        candidate.session_summary.source_labels if candidate.session_summary else (),
        '$["session_summary"]["source_labels"]',
        None,
        issues,
    )
    for index, fact in enumerate(candidate.evidence_facts):
        _check_labels(
            compact_input,
            fact.support_labels,
            f'$["evidence_facts"][{index}]["support_labels"]',
            COMPACT_FACT_SOURCE_KINDS_V2,
            issues,
        )
        _check_labels(
            compact_input,
            fact.context_labels,
            f'$["evidence_facts"][{index}]["context_labels"]',
            COMPACT_FACT_CONTEXT_SOURCE_KINDS_V2,
            issues,
        )
    for index, anchor in enumerate(candidate.answer_anchors):
        _check_labels(
            compact_input,
            anchor.source_labels,
            f'$["answer_anchors"][{index}]["source_labels"]',
            COMPACT_ANSWER_SOURCE_KINDS_V2,
            issues,
        )
    for index, intent in enumerate(candidate.forward_intents):
        _check_labels(
            compact_input,
            intent.source_labels,
            f'$["forward_intents"][{index}]["source_labels"]',
            COMPACT_FORWARD_SOURCE_KINDS_V2,
            issues,
        )
    for index, reference in enumerate(candidate.reference_continuity):
        _check_labels(
            compact_input,
            reference.source_labels,
            f'$["reference_continuity"][{index}]["source_labels"]',
            COMPACT_REFERENCE_SOURCE_KINDS_V2,
            issues,
        )
    for index, diagnostic in enumerate(candidate.diagnostics):
        _check_labels(
            compact_input, diagnostic.source_labels, f'$["diagnostics"][{index}]["source_labels"]', None, issues
        )


def _check_labels(
    compact_input: CompactInputV2,
    labels: tuple[str, ...],
    json_path: str,
    allowed_kinds: tuple[CompactSourceKindV2, ...] | None,
    issues: list[CompactValidationIssueV2],
) -> None:
    """校验单一 label tuple。

    :param compact_input: strict v2 input。
    :param labels: 待校验 labels。
    :param json_path: label tuple path。
    :param allowed_kinds: 允许 source kinds；``None`` 表示任意 boundary kind。
    :param issues: issue accumulator。
    :returns: ``None``。
    """

    seen: set[str] = set()
    for label in labels:
        if label in seen:
            issues.append(
                _issue(
                    CompactValidationIssueCodeV2.DUPLICATE_SOURCE_LABEL,
                    json_path,
                    "同一 source label 在该列表中只能出现一次。",
                    (label,),
                )
            )
            continue
        seen.add(label)
        kind = compact_input.source_kind(label)
        if kind is None:
            issues.append(
                _issue(
                    CompactValidationIssueCodeV2.UNKNOWN_SOURCE_LABEL,
                    json_path,
                    "source label 必须来自当前 source_boundary。",
                    (label,),
                )
            )
        elif allowed_kinds is not None and kind not in allowed_kinds:
            allowed = "、".join(item.value for item in allowed_kinds)
            issues.append(
                _issue(
                    CompactValidationIssueCodeV2.SOURCE_KIND_MISMATCH,
                    json_path,
                    f"该字段只允许 source_kind：{allowed}。",
                    (label,),
                )
            )


def _collect_coverage_issues(
    compact_input: CompactInputV2,
    candidate: CompactCandidateV2,
    represented: dict[str, tuple[CompactSemanticSectionV2, ...]],
    issues: list[CompactValidationIssueV2],
) -> None:
    """收集 exact coverage partition 问题。

    :param compact_input: strict v2 input。
    :param candidate: candidate。
    :param represented: Host 派生 represented sections。
    :param issues: issue accumulator。
    :returns: ``None``。
    """

    boundary = set(compact_input.source_labels)
    drop_reasons: dict[str, CompactDropReasonV2] = {}
    for index, drop in enumerate(candidate.explicitly_dropped_sources):
        path = f'$["explicitly_dropped_sources"][{index}]["source_label"]'
        if drop.source_label not in boundary:
            issues.append(
                _issue(
                    CompactValidationIssueCodeV2.UNKNOWN_SOURCE_LABEL,
                    path,
                    "drop label 必须来自当前 source_boundary。",
                    (drop.source_label,),
                )
            )
        if drop.source_label in drop_reasons:
            issues.append(
                _issue(
                    CompactValidationIssueCodeV2.DUPLICATE_DROP_LABEL,
                    path,
                    "同一 source 只能有一个 explicit drop。",
                    (drop.source_label,),
                )
            )
            if drop_reasons[drop.source_label] != drop.reason:
                issues.append(
                    _issue(
                        CompactValidationIssueCodeV2.CONTRADICTORY_SEMANTIC_ITEM,
                        path,
                        "同一 drop label 不能声明不同 reason。",
                        (drop.source_label,),
                    )
                )
        drop_reasons[drop.source_label] = drop.reason
        if drop.source_label in represented:
            issues.append(
                _issue(
                    CompactValidationIssueCodeV2.REPRESENTED_AND_DROPPED,
                    path,
                    "同一 source 不能同时 represented 和 explicitly dropped。",
                    (drop.source_label,),
                )
            )
    covered = set(represented).union(drop_reasons)
    for label in compact_input.source_labels:
        if label not in covered:
            issues.append(
                _issue(
                    CompactValidationIssueCodeV2.UNCOVERED_SOURCE,
                    "$",
                    "source_boundary 的每个 label 都必须 represented 或 explicitly dropped。",
                    (label,),
                )
            )


def _collect_duplicate_and_contradiction_issues(
    candidate: CompactCandidateV2,
    issues: list[CompactValidationIssueV2],
) -> None:
    """收集精确 duplicate 与 schema-provable contradiction。

    :param candidate: strict candidate。
    :param issues: issue accumulator。
    :returns: ``None``。
    """

    _collect_duplicate_keys(
        tuple(_canonical_text(item.claim) for item in candidate.evidence_facts), "evidence_facts", issues
    )
    _collect_duplicate_keys(
        tuple((_canonical_text(item.title), _canonical_text(item.detail)) for item in candidate.answer_anchors),
        "answer_anchors",
        issues,
    )
    intent_status: dict[tuple[str, str], str] = {}
    for index, item in enumerate(candidate.forward_intents):
        identity = (_canonical_text(item.intent_type), _canonical_text(item.text))
        if identity in intent_status:
            issues.append(
                _issue(
                    CompactValidationIssueCodeV2.DUPLICATE_SEMANTIC_ITEM,
                    f'$["forward_intents"][{index}]',
                    "intent_type+text 必须唯一。",
                )
            )
            if intent_status[identity] != item.status.value:
                issues.append(
                    _issue(
                        CompactValidationIssueCodeV2.CONTRADICTORY_SEMANTIC_ITEM,
                        f'$["forward_intents"][{index}]["status"]',
                        "同一 intent_type+text 不能有不同 status。",
                    )
                )
        intent_status[identity] = item.status.value
    reference_reasons: dict[str, str] = {}
    for index, item in enumerate(candidate.reference_continuity):
        identity = _canonical_text(item.text)
        if identity in reference_reasons:
            issues.append(
                _issue(
                    CompactValidationIssueCodeV2.DUPLICATE_SEMANTIC_ITEM,
                    f'$["reference_continuity"][{index}]',
                    "reference text 必须唯一。",
                )
            )
            if reference_reasons[identity] != item.reason:
                issues.append(
                    _issue(
                        CompactValidationIssueCodeV2.CONTRADICTORY_SEMANTIC_ITEM,
                        f'$["reference_continuity"][{index}]["reason"]',
                        "同一 reference text 不能有不同 reason。",
                    )
                )
        reference_reasons[identity] = item.reason
    _collect_duplicate_keys(
        tuple((_canonical_text(item.code), _canonical_text(item.message)) for item in candidate.diagnostics),
        "diagnostics",
        issues,
    )


def _collect_duplicate_keys(
    identities: tuple[str | tuple[str, str], ...],
    section: str,
    issues: list[CompactValidationIssueV2],
) -> None:
    """收集单一 section 的精确 duplicate identities。

    :param identities: canonical identities。
    :param section: JSON section name。
    :param issues: issue accumulator。
    :returns: ``None``。
    """

    seen: set[str | tuple[str, str]] = set()
    for index, identity in enumerate(identities):
        if identity in seen:
            issues.append(
                _issue(
                    CompactValidationIssueCodeV2.DUPLICATE_SEMANTIC_ITEM,
                    f'$["{section}"][{index}]',
                    "该业务语义项与本 section 中已有项精确重复。",
                )
            )
        seen.add(identity)


def _collect_information_issues(
    compact_input: CompactInputV2,
    candidate: CompactCandidateV2,
    represented: dict[str, tuple[CompactSemanticSectionV2, ...]],
    issues: list[CompactValidationIssueV2],
) -> None:
    """收集 empty、diagnostics-only 与 low-information 问题。

    :param compact_input: strict v2 input。
    :param candidate: candidate。
    :param represented: Host 派生 represented sections。
    :param issues: issue accumulator。
    :returns: ``None``。
    """

    semantic_count = _semantic_item_count(candidate)
    if semantic_count == 0 and len(candidate.diagnostics) == 0:
        issues.append(_issue(CompactValidationIssueCodeV2.EMPTY_SEMANTIC_OUTPUT, "$", "五个业务语义区不能全部为空。"))
    elif semantic_count == 0:
        issues.append(
            _issue(CompactValidationIssueCodeV2.DIAGNOSTICS_ONLY_OUTPUT, "$", "diagnostics 不能替代业务语义输出。")
        )
    if len(compact_input.source_boundary) > 0 and len(represented) == 0:
        issues.append(
            _issue(
                CompactValidationIssueCodeV2.LOW_INFORMATION_OUTPUT,
                "$",
                "非空 source_boundary 至少需要一个 represented business source。",
            )
        )


def _collect_policy_issues(
    candidate: CompactCandidateV2,
    policy: MemoryProjectionPolicy,
    issues: list[CompactValidationIssueV2],
) -> None:
    """使用 Memory owner 的 policy 与 estimator 收集 cap 问题。

    :param candidate: candidate。
    :param policy: MemoryProjectionPolicy 真源。
    :param issues: issue accumulator。
    :returns: ``None``。
    """

    if candidate.session_summary is not None:
        summary_size = estimate_memory_size_units(candidate.session_summary.text).units
    else:
        summary_size = None
    if summary_size is not None and summary_size > policy.session_summary_char_cap:
        issues.append(
            _issue(
                CompactValidationIssueCodeV2.POLICY_SIZE_CAP_EXCEEDED,
                '$["session_summary"]["text"]',
                f"session_summary.text 当前为 {summary_size} 个字符，上限 "
                f"{policy.session_summary_char_cap} 个字符；请缩减 session_summary.text 到不超过 "
                f"{policy.session_summary_char_cap} 个字符。",
            )
        )
    _section_caps(
        "evidence_facts",
        tuple(item.claim for item in candidate.evidence_facts),
        policy.evidence_fact_item_cap,
        policy.evidence_fact_char_cap,
        _EVIDENCE_FACTS_SIZE_MEASUREMENT,
        issues,
    )
    _section_caps(
        "answer_anchors",
        tuple(f"{item.title}\n{item.detail}" for item in candidate.answer_anchors),
        policy.answer_anchor_item_cap,
        policy.answer_anchor_char_cap,
        _ANSWER_ANCHORS_SIZE_MEASUREMENT,
        issues,
    )
    _section_caps(
        "forward_intents",
        tuple(item.text for item in candidate.forward_intents),
        policy.forward_intent_item_cap,
        policy.forward_intent_char_cap,
        _FORWARD_INTENTS_SIZE_MEASUREMENT,
        issues,
    )
    _section_caps(
        "reference_continuity",
        tuple(item.text for item in candidate.reference_continuity),
        policy.reference_continuity_item_cap,
        policy.reference_continuity_char_cap,
        _REFERENCE_CONTINUITY_SIZE_MEASUREMENT,
        issues,
    )


def _section_caps(
    section: str,
    texts: tuple[str, ...],
    item_cap: int,
    size_cap: int,
    size_measurement: str,
    issues: list[CompactValidationIssueV2],
) -> None:
    """检查一个 Memory semantic section 的 count/size caps。

    :param section: JSON section name。
    :param texts: section item texts。
    :param item_cap: item count cap。
    :param size_cap: aggregate size cap。
    :param size_measurement: section aggregate size 的业务可读计量说明。
    :param issues: issue accumulator。
    :returns: ``None``。
    """

    if len(texts) > item_cap:
        issues.append(
            _issue(
                CompactValidationIssueCodeV2.POLICY_ITEM_CAP_EXCEEDED,
                f'$["{section}"]',
                f"{section} 当前为 {len(texts)} 项，上限 {item_cap} 项；"
                f"请删减或合并 {section}，只保留不超过 {item_cap} 项。",
            )
        )
    total = sum(estimate_memory_size_units(text).units for text in texts)
    if total > size_cap:
        issues.append(
            _issue(
                CompactValidationIssueCodeV2.POLICY_SIZE_CAP_EXCEEDED,
                f'$["{section}"]',
                f"{section} 的{size_measurement}当前为 {total} 个字符，上限 {size_cap} 个字符；"
                f"请缩减 {section} 的文本总量到不超过 {size_cap} 个字符。",
            )
        )


def _represented_sections(
    candidate: CompactCandidateV2,
) -> dict[str, tuple[CompactSemanticSectionV2, ...]]:
    """从五个业务区唯一派生 represented source map。

    :param candidate: strict candidate。
    :returns: label 到固定顺序 semantic sections 的映射。
    """

    mutable: dict[str, set[CompactSemanticSectionV2]] = {}
    if candidate.session_summary is not None:
        _add_represented(mutable, candidate.session_summary.source_labels, CompactSemanticSectionV2.SESSION_SUMMARY)
    for item in candidate.evidence_facts:
        _add_represented(mutable, item.support_labels + item.context_labels, CompactSemanticSectionV2.EVIDENCE_FACTS)
    for item in candidate.answer_anchors:
        _add_represented(mutable, item.source_labels, CompactSemanticSectionV2.ANSWER_ANCHORS)
    for item in candidate.forward_intents:
        _add_represented(mutable, item.source_labels, CompactSemanticSectionV2.FORWARD_INTENTS)
    for item in candidate.reference_continuity:
        _add_represented(mutable, item.source_labels, CompactSemanticSectionV2.REFERENCE_CONTINUITY)
    order = tuple(CompactSemanticSectionV2)
    return {label: tuple(section for section in order if section in sections) for label, sections in mutable.items()}


def _add_represented(
    target: dict[str, set[CompactSemanticSectionV2]],
    labels: tuple[str, ...],
    section: CompactSemanticSectionV2,
) -> None:
    """向 represented map 添加一组 labels。

    :param target: mutable represented map。
    :param labels: source labels。
    :param section: semantic section。
    :returns: ``None``。
    """

    for label in labels:
        target.setdefault(label, set()).add(section)


def _canonical_candidate(candidate: CompactCandidateV2, boundary_order: dict[str, int]) -> CompactCandidateV2:
    """按 root boundary 顺序 canonicalize 每个 label tuple。

    :param candidate: 已通过全部 validation 的 candidate。
    :param boundary_order: label 到 root ordinal 的映射。
    :returns: 语义不变的 canonical candidate。
    """

    summary = (
        None
        if candidate.session_summary is None
        else CompactSessionSummaryV2(
            text=candidate.session_summary.text,
            source_labels=_ordered_labels(
                candidate.session_summary.source_labels,
                boundary_order,
            ),
        )
    )
    return CompactCandidateV2(
        schema=candidate.schema,
        session_summary=summary,
        evidence_facts=tuple(
            CompactEvidenceFactV2(
                claim=item.claim,
                support_labels=_ordered_labels(item.support_labels, boundary_order),
                context_labels=_ordered_labels(item.context_labels, boundary_order),
            )
            for item in candidate.evidence_facts
        ),
        answer_anchors=tuple(
            CompactAnswerAnchorV2(
                title=item.title,
                detail=item.detail,
                source_labels=_ordered_labels(item.source_labels, boundary_order),
            )
            for item in candidate.answer_anchors
        ),
        forward_intents=tuple(
            CompactForwardIntentV2(
                intent_type=item.intent_type,
                text=item.text,
                status=item.status,
                source_labels=_ordered_labels(item.source_labels, boundary_order),
            )
            for item in candidate.forward_intents
        ),
        reference_continuity=tuple(
            CompactReferenceContinuityV2(
                text=item.text,
                reason=item.reason,
                source_labels=_ordered_labels(item.source_labels, boundary_order),
            )
            for item in candidate.reference_continuity
        ),
        diagnostics=tuple(
            CompactCandidateDiagnosticV2(
                code=item.code,
                message=item.message,
                source_labels=_ordered_labels(item.source_labels, boundary_order),
            )
            for item in candidate.diagnostics
        ),
        explicitly_dropped_sources=tuple(
            sorted(
                candidate.explicitly_dropped_sources,
                key=lambda drop: boundary_order[drop.source_label],
            )
        ),
    )


def _ordered_labels(
    values: tuple[str, ...],
    boundary_order: dict[str, int],
) -> tuple[str, ...]:
    """按 immutable root boundary 顺序排列 labels。

    :param values: 已验证属于 boundary 的 labels。
    :param boundary_order: label 到 root ordinal 的映射。
    :returns: canonical label tuple。
    """

    return tuple(sorted(values, key=boundary_order.__getitem__))


def _semantic_item_count(candidate: CompactCandidateV2) -> int:
    """返回五个业务区的 item count。

    :param candidate: candidate。
    :returns: semantic item count。
    """

    return (
        int(candidate.session_summary is not None)
        + len(candidate.evidence_facts)
        + len(candidate.answer_anchors)
        + len(candidate.forward_intents)
        + len(candidate.reference_continuity)
    )


def _canonical_text(text: str) -> str:
    """用统一 whitespace 规则 canonicalize 文本 identity。

    :param text: typed nonblank text。
    :returns: whitespace-canonical text。
    """

    return " ".join(text.split())


def _issue(
    code: CompactValidationIssueCodeV2,
    json_path: str,
    message: str,
    source_labels: tuple[str, ...] = (),
) -> CompactValidationIssueV2:
    """构造一条脱敏 validation issue。

    :param code: issue code。
    :param json_path: JSON path。
    :param message: 自解释提示。
    :param source_labels: opaque labels。
    :returns: typed issue。
    """

    return CompactValidationIssueV2(code=code, json_path=json_path, message=message, source_labels=source_labels)


def _validation_report(issues: list[CompactValidationIssueV2]) -> CompactValidationReportV2:
    """稳定排序并精确去重 issues。

    :param issues: accumulated issues。
    :returns: deterministic reject report。
    """

    unique = set(issues)
    ordered = tuple(sorted(unique, key=_validation_issue_sort_key))
    return CompactValidationReportV2(issues=ordered)


def _validation_issue_sort_key(
    issue: CompactValidationIssueV2,
) -> tuple[str, str, tuple[str, ...], str]:
    """返回 validation issue 的 deterministic 排序键。

    :param issue: typed validation issue。
    :returns: code、path、labels、message 排序键。
    """

    return (issue.code.value, issue.json_path, issue.source_labels, issue.message)


def _bounded_issue_message(issue: CompactValidationIssueV2) -> CompactValidationIssueV2:
    """脱敏并截断所有 internal repair transport issue 字段。

    :param issue: validation issue。
    :returns: path、message 与 labels 均脱敏且 bounded 的 issue。
    """

    safe_labels = tuple(dict.fromkeys(_bounded_feedback_text(label) for label in issue.source_labels))
    return CompactValidationIssueV2(
        code=issue.code,
        json_path=_bounded_feedback_text(issue.json_path),
        message=_bounded_feedback_text(issue.message),
        source_labels=safe_labels,
    )


def _bounded_feedback_text(value: str) -> str:
    """脱敏并限制单一 repair feedback 文本字段。

    :param value: issue path、message 或 opaque source label。
    :returns: 不超过单 issue 文本上限的安全字段。
    """

    return truncate_diagnostic_text(
        redact_sensitive_diagnostic_values(
            value,
            redaction_marker=_REPAIR_REDACTION_MARKER,
        ),
        max_chars=MAX_COMPACT_REPAIR_ISSUE_MESSAGE_CHARS,
        truncated_suffix=_REPAIR_TRUNCATED_SUFFIX,
    )


def _feedback_char_count(feedback: CompactRepairFeedbackV2) -> int:
    """计算 durable/internal feedback serialization 的 JSON 字符数。

    :param feedback: typed feedback。
    :returns: UTF-8 无关的 Python 字符数。
    """

    return len(json.dumps(feedback.to_json(), ensure_ascii=False, sort_keys=True))


__all__ = [
    "CompactAcceptanceResultV2",
    "accept_compact_candidate_v2",
    "build_compact_repair_feedback_v2",
]
