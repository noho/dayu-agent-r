"""Host Context Governance 的 deterministic compact v4 accept owner。

本模块唯一负责把 strict parsed candidate 验收为可提交 truth。它不写
artifact/EventLog/Memory，也不执行 compactor retry。
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from dayu.host.compaction import (
    MAX_COMPACT_REPAIR_FEEDBACK_CHARS,
    MAX_COMPACT_REPAIR_ISSUES,
    MAX_COMPACT_REPAIR_ISSUE_MESSAGE_CHARS,
    CompactAcceptedReplacementV4,
    CompactAcceptedTruthV4,
    CompactAnswerAnchorV4,
    CompactCandidateV4,
    CompactEvidenceFactV4,
    CompactForwardIntentV4,
    CompactInputV4,
    CompactOmittedCoverageV4,
    CompactOutputCapsV4,
    CompactPolicyUsageAuditV4,
    CompactPolicyUsageActualsV4,
    CompactReferenceContinuityV4,
    CompactRepairFeedbackV4,
    CompactRepresentedCoverageV4,
    CompactRepresentedSourceV4,
    CompactSemanticSectionV4,
    CompactSessionSummaryV4,
    CompactValidationIssueCodeV4,
    CompactValidationIssueV4,
    CompactValidationReportV4,
    compact_policy_usage_measurement_rules_v4,
    compact_proposal_boundary_binding_issues_v4,
    derive_compact_accepted_replacement_v4,
    derive_compact_replacement_policy_usage_actuals_v4,
    derive_compact_replacement_represented_sections_v4,
    _COMPACT_ACCEPTANCE_PERMIT,
)
from dayu.host.memory import (
    MemoryProjectionPolicy,
    digest_memory_projection_policy,
    estimate_memory_size_units,
)
from dayu.runtime.diagnostic_text import (
    redact_sensitive_diagnostic_values,
    truncate_diagnostic_text,
)

_REPAIR_REDACTION_MARKER = "<redacted>"
_REPAIR_TRUNCATED_SUFFIX = "..."
_POLICY_USAGE_MEASUREMENT_RULES_V4 = compact_policy_usage_measurement_rules_v4()


CompactAcceptanceResultV4 = CompactAcceptedTruthV4 | CompactValidationReportV4
"""Host acceptance 的 success/reject 二臂结果。"""


def compact_output_caps_v4_from_memory_policy(
    policy: MemoryProjectionPolicy,
) -> CompactOutputCapsV4:
    """从唯一 Memory policy 真源机械投影 compact v4 输出上限。

    :param policy: 已由 Memory owner 校验的 projection policy。
    :returns: 不定义默认值或独立校验的 immutable boundary DTO。
    :raises TypeError: ``policy`` 不是 ``MemoryProjectionPolicy`` 时抛出。
    """

    if not isinstance(policy, MemoryProjectionPolicy):
        raise TypeError("policy must be MemoryProjectionPolicy")
    return CompactOutputCapsV4(
        session_summary_char_cap=policy.session_summary_char_cap,
        evidence_fact_item_cap=policy.evidence_fact_item_cap,
        evidence_fact_char_cap=policy.evidence_fact_char_cap,
        answer_anchor_item_cap=policy.answer_anchor_item_cap,
        answer_anchor_char_cap=policy.answer_anchor_char_cap,
        forward_intent_item_cap=policy.forward_intent_item_cap,
        forward_intent_char_cap=policy.forward_intent_char_cap,
        reference_continuity_item_cap=policy.reference_continuity_item_cap,
        reference_continuity_char_cap=policy.reference_continuity_char_cap,
    )


def accept_compact_candidate_v4(
    compact_input: CompactInputV4,
    candidate: CompactCandidateV4,
    memory_policy: MemoryProjectionPolicy,
) -> CompactAcceptanceResultV4:
    """按固定顺序验收完整 v4 candidate。

    :param compact_input: immutable root/pass input。
    :param candidate: strict parser 产出的完整 candidate。
    :param memory_policy: Memory owner 的同一 typed policy instance。
    :returns: accepted truth 或 deterministic reject report。
    :raises TypeError: 参数类型非法时抛出。
    """

    if not isinstance(compact_input, CompactInputV4):
        raise TypeError("compact_input must be CompactInputV4")
    if not isinstance(candidate, CompactCandidateV4):
        raise TypeError("candidate must be CompactCandidateV4")
    if not isinstance(memory_policy, MemoryProjectionPolicy):
        raise TypeError("memory_policy must be MemoryProjectionPolicy")
    expected_caps = compact_output_caps_v4_from_memory_policy(memory_policy)
    if compact_input.output_caps != expected_caps:
        raise ValueError("compact_input.output_caps must match memory_policy")

    issues: list[CompactValidationIssueV4] = []
    boundary_order = {
        entry.source_label: index
        for index, entry in enumerate(compact_input.source_boundary)
    }
    issues.extend(
        compact_proposal_boundary_binding_issues_v4(
            compact_input.source_boundary,
            candidate,
        )
    )
    if issues:
        return _validation_report(issues)

    normalized = _canonical_candidate(candidate, boundary_order)
    replacement = derive_compact_accepted_replacement_v4(
        compact_input.source_boundary,
        normalized,
    )
    normalized_represented = (
        derive_compact_replacement_represented_sections_v4(replacement)
    )
    _collect_duplicate_and_contradiction_issues(replacement, issues)
    _collect_information_issues(
        compact_input,
        replacement,
        normalized_represented,
        issues,
    )
    _collect_policy_issues(replacement, memory_policy, issues)
    if issues:
        return _validation_report(issues)

    represented_sources = tuple(
        CompactRepresentedSourceV4(
            source_label=entry.source_label,
            sections=normalized_represented[entry.source_label],
        )
        for entry in compact_input.source_boundary
        if entry.source_label in normalized_represented
    )
    omitted = tuple(
        entry.source_label
        for entry in compact_input.source_boundary
        if entry.source_label not in normalized_represented
    )
    return CompactAcceptedTruthV4(
        proposal=normalized,
        replacement=replacement,
        source_boundary=compact_input.source_boundary,
        represented_coverage=CompactRepresentedCoverageV4(sources=represented_sources),
        omitted_coverage=CompactOmittedCoverageV4(source_labels=omitted),
        policy_usage_audit=_policy_usage_audit(replacement, memory_policy),
        current_input_ref=compact_input.current_input.source_ref,
        _permit=_COMPACT_ACCEPTANCE_PERMIT,
    )


def build_compact_repair_feedback_v4(
    report: CompactValidationReportV4,
    *,
    request_digest: str,
    source_boundary_digest: str,
    previous_attempt_number: int,
) -> CompactRepairFeedbackV4:
    """从 reject report 构造 bounded、脱敏的 Host internal feedback。

    :param report: 前次 semantic validation report。
    :param request_digest: 产生报告的 immutable request digest。
    :param source_boundary_digest: 产生报告的 source boundary digest。
    :param previous_attempt_number: 前次 attempt number。
    :returns: 满足 32/240/8192 边界的 typed feedback。
    :raises TypeError: report 类型非法时抛出。
    :raises ValueError: attempt number 非正数时抛出。
    """

    if not isinstance(report, CompactValidationReportV4):
        raise TypeError("report must be CompactValidationReportV4")
    if previous_attempt_number <= 0:
        raise ValueError("previous_attempt_number must be positive")
    bounded_all = tuple(_bounded_issue_message(issue) for issue in report.issues)
    selected = list(bounded_all[:MAX_COMPACT_REPAIR_ISSUES])
    additional = len(bounded_all) - len(selected)
    feedback = CompactRepairFeedbackV4(
        request_digest=request_digest,
        source_boundary_digest=source_boundary_digest,
        previous_attempt_number=previous_attempt_number,
        issues=tuple(selected),
        additional_issue_count=additional,
    )
    while _feedback_char_count(feedback) > MAX_COMPACT_REPAIR_FEEDBACK_CHARS and len(selected) > 1:
        selected.pop()
        additional += 1
        feedback = CompactRepairFeedbackV4(
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
        selected[0] = CompactValidationIssueV4(
            code=only_issue.code,
            json_path=only_issue.json_path,
            message=only_issue.message,
            source_labels=only_issue.source_labels[:-1],
        )
        feedback = CompactRepairFeedbackV4(
            request_digest=request_digest,
            source_boundary_digest=source_boundary_digest,
            previous_attempt_number=previous_attempt_number,
            issues=tuple(selected),
            additional_issue_count=additional,
        )
    return feedback


def _collect_duplicate_and_contradiction_issues(
    replacement: CompactAcceptedReplacementV4,
    issues: list[CompactValidationIssueV4],
) -> None:
    """收集精确 duplicate 与 schema-provable contradiction。

    :param replacement: retained + new combined replacement。
    :param issues: issue accumulator。
    :returns: ``None``。
    """

    _collect_duplicate_keys(
        tuple(
            _canonical_text(item.claim) for item in replacement.evidence_facts
        ),
        "evidence_facts",
        issues,
    )
    _collect_duplicate_keys(
        tuple(
            (_canonical_text(item.title), _canonical_text(item.detail))
            for item in replacement.answer_anchors
        ),
        "answer_anchors",
        issues,
    )
    intent_status: dict[tuple[str, str], str] = {}
    for index, item in enumerate(replacement.forward_intents):
        identity = (_canonical_text(item.intent_type), _canonical_text(item.text))
        if identity in intent_status:
            issues.append(
                _issue(
                    CompactValidationIssueCodeV4.DUPLICATE_SEMANTIC_ITEM,
                    f'$["forward_intents"][{index}]',
                    "intent_type+text 必须唯一。",
                )
            )
            if intent_status[identity] != item.status.value:
                issues.append(
                    _issue(
                        CompactValidationIssueCodeV4.CONTRADICTORY_SEMANTIC_ITEM,
                        f'$["forward_intents"][{index}]["status"]',
                        "同一 intent_type+text 不能有不同 status。",
                    )
                )
        intent_status[identity] = item.status.value
    reference_reasons: dict[str, str] = {}
    for index, item in enumerate(replacement.reference_continuity):
        identity = _canonical_text(item.text)
        if identity in reference_reasons:
            issues.append(
                _issue(
                    CompactValidationIssueCodeV4.DUPLICATE_SEMANTIC_ITEM,
                    f'$["reference_continuity"][{index}]',
                    "reference text 必须唯一。",
                )
            )
            if reference_reasons[identity] != item.reason:
                issues.append(
                    _issue(
                        CompactValidationIssueCodeV4.CONTRADICTORY_SEMANTIC_ITEM,
                        f'$["reference_continuity"][{index}]["reason"]',
                        "同一 reference text 不能有不同 reason。",
                    )
                )
        reference_reasons[identity] = item.reason
def _collect_duplicate_keys(
    identities: tuple[str | tuple[str, str], ...],
    section: str,
    issues: list[CompactValidationIssueV4],
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
                    CompactValidationIssueCodeV4.DUPLICATE_SEMANTIC_ITEM,
                    f'$["{section}"][{index}]',
                    "该业务语义项与本 section 中已有项精确重复。",
                )
            )
        seen.add(identity)


def _collect_information_issues(
    compact_input: CompactInputV4,
    replacement: CompactAcceptedReplacementV4,
    represented: Mapping[str, tuple[CompactSemanticSectionV4, ...]],
    issues: list[CompactValidationIssueV4],
) -> None:
    """收集 empty 与 low-information 问题。

    :param compact_input: strict v4 input。
    :param replacement: retained + new combined replacement。
    :param represented: Host 派生 represented sections。
    :param issues: issue accumulator。
    :returns: ``None``。
    """

    semantic_count = _semantic_item_count(replacement)
    if semantic_count == 0:
        issues.append(_issue(CompactValidationIssueCodeV4.EMPTY_SEMANTIC_OUTPUT, "$", "五个业务语义区不能全部为空。"))
    if len(compact_input.source_boundary) > 0 and len(represented) == 0:
        issues.append(
            _issue(
                CompactValidationIssueCodeV4.LOW_INFORMATION_OUTPUT,
                "$",
                "非空 source_boundary 至少需要一个 represented business source。",
            )
        )


def _collect_policy_issues(
    replacement: CompactAcceptedReplacementV4,
    policy: MemoryProjectionPolicy,
    issues: list[CompactValidationIssueV4],
) -> None:
    """使用 Memory owner 的 policy 与 estimator 收集 cap 问题。

    :param replacement: retained + new combined replacement。
    :param policy: MemoryProjectionPolicy 真源。
    :param issues: issue accumulator。
    :returns: ``None``。
    """

    if replacement.session_summary is not None:
        summary_size = estimate_memory_size_units(
            replacement.session_summary.text
        ).units
    else:
        summary_size = None
    if summary_size is not None and summary_size > policy.session_summary_char_cap:
        issues.append(
            _issue(
                CompactValidationIssueCodeV4.POLICY_SIZE_CAP_EXCEEDED,
                '$["session_summary"]["text"]',
                f"session_summary.text 当前为 {summary_size} 个字符，上限 "
                f"{policy.session_summary_char_cap} 个字符；请缩减 session_summary.text 到不超过 "
                f"{policy.session_summary_char_cap} 个字符。",
            )
        )
    _section_caps(
        "evidence_facts",
        tuple(item.claim for item in replacement.evidence_facts),
        policy.evidence_fact_item_cap,
        policy.evidence_fact_char_cap,
        _POLICY_USAGE_MEASUREMENT_RULES_V4[
            CompactSemanticSectionV4.EVIDENCE_FACTS.value
        ],
        issues,
    )
    _section_caps(
        "answer_anchors",
        tuple(
            f"{item.title}\n{item.detail}" for item in replacement.answer_anchors
        ),
        policy.answer_anchor_item_cap,
        policy.answer_anchor_char_cap,
        _POLICY_USAGE_MEASUREMENT_RULES_V4[
            CompactSemanticSectionV4.ANSWER_ANCHORS.value
        ],
        issues,
    )
    _section_caps(
        "forward_intents",
        tuple(item.text for item in replacement.forward_intents),
        policy.forward_intent_item_cap,
        policy.forward_intent_char_cap,
        _POLICY_USAGE_MEASUREMENT_RULES_V4[
            CompactSemanticSectionV4.FORWARD_INTENTS.value
        ],
        issues,
    )
    _section_caps(
        "reference_continuity",
        tuple(item.text for item in replacement.reference_continuity),
        policy.reference_continuity_item_cap,
        policy.reference_continuity_char_cap,
        _POLICY_USAGE_MEASUREMENT_RULES_V4[
            CompactSemanticSectionV4.REFERENCE_CONTINUITY.value
        ],
        issues,
    )


def _policy_usage_audit(
    replacement: CompactAcceptedReplacementV4,
    policy: MemoryProjectionPolicy,
) -> CompactPolicyUsageAuditV4:
    """从 accepted candidate、同一 estimator 与同一 policy 构造审计。

    :param replacement: 已通过 policy cap 的 accepted replacement。
    :param policy: 产生 input caps 且执行验收的同一 Memory policy。
    :returns: 各 section actual/cap 与 policy identity 的 immutable audit。
    """

    actuals: CompactPolicyUsageActualsV4 = (
        derive_compact_replacement_policy_usage_actuals_v4(replacement)
    )
    return CompactPolicyUsageAuditV4(
        policy_ref=policy.policy_ref,
        policy_digest=digest_memory_projection_policy(policy),
        session_summary_char_actual=actuals.session_summary_char_actual,
        session_summary_char_cap=policy.session_summary_char_cap,
        evidence_fact_item_actual=actuals.evidence_fact_item_actual,
        evidence_fact_item_cap=policy.evidence_fact_item_cap,
        evidence_fact_char_actual=actuals.evidence_fact_char_actual,
        evidence_fact_char_cap=policy.evidence_fact_char_cap,
        answer_anchor_item_actual=actuals.answer_anchor_item_actual,
        answer_anchor_item_cap=policy.answer_anchor_item_cap,
        answer_anchor_char_actual=actuals.answer_anchor_char_actual,
        answer_anchor_char_cap=policy.answer_anchor_char_cap,
        forward_intent_item_actual=actuals.forward_intent_item_actual,
        forward_intent_item_cap=policy.forward_intent_item_cap,
        forward_intent_char_actual=actuals.forward_intent_char_actual,
        forward_intent_char_cap=policy.forward_intent_char_cap,
        reference_continuity_item_actual=(
            actuals.reference_continuity_item_actual
        ),
        reference_continuity_item_cap=policy.reference_continuity_item_cap,
        reference_continuity_char_actual=(
            actuals.reference_continuity_char_actual
        ),
        reference_continuity_char_cap=policy.reference_continuity_char_cap,
    )


def _section_caps(
    section: str,
    texts: tuple[str, ...],
    item_cap: int,
    size_cap: int,
    size_measurement: str,
    issues: list[CompactValidationIssueV4],
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
                CompactValidationIssueCodeV4.POLICY_ITEM_CAP_EXCEEDED,
                f'$["{section}"]',
                f"{section} 当前为 {len(texts)} 项，上限 {item_cap} 项；"
                f"请删减或合并 {section}，只保留不超过 {item_cap} 项。",
            )
        )
    total = sum(estimate_memory_size_units(text).units for text in texts)
    if total > size_cap:
        issues.append(
            _issue(
                CompactValidationIssueCodeV4.POLICY_SIZE_CAP_EXCEEDED,
                f'$["{section}"]',
                f"{section} 的{size_measurement}当前为 {total} 个字符，上限 {size_cap} 个字符；"
                f"请缩减 {section} 的文本总量到不超过 {size_cap} 个字符。",
            )
        )


def _canonical_candidate(candidate: CompactCandidateV4, boundary_order: dict[str, int]) -> CompactCandidateV4:
    """按 root boundary 顺序 canonicalize 每个 label tuple。

    :param candidate: 已通过全部 validation 的 candidate。
    :param boundary_order: label 到 root ordinal 的映射。
    :returns: 语义不变的 canonical candidate。
    """

    summary = (
        None
        if candidate.session_summary is None
        else CompactSessionSummaryV4(
            text=candidate.session_summary.text,
            source_labels=_ordered_labels(
                candidate.session_summary.source_labels,
                boundary_order,
            ),
        )
    )
    return CompactCandidateV4(
        schema=candidate.schema,
        session_summary=summary,
        retained_previous_evidence_fact_labels=_ordered_labels(
            candidate.retained_previous_evidence_fact_labels,
            boundary_order,
        ),
        evidence_facts=tuple(
            CompactEvidenceFactV4(
                claim=item.claim,
                support_labels=_ordered_labels(item.support_labels, boundary_order),
                context_labels=_ordered_labels(item.context_labels, boundary_order),
            )
            for item in candidate.evidence_facts
        ),
        answer_anchors=tuple(
            CompactAnswerAnchorV4(
                title=item.title,
                detail=item.detail,
                source_labels=_ordered_labels(item.source_labels, boundary_order),
            )
            for item in candidate.answer_anchors
        ),
        forward_intents=tuple(
            CompactForwardIntentV4(
                intent_type=item.intent_type,
                text=item.text,
                status=item.status,
                source_labels=_ordered_labels(item.source_labels, boundary_order),
            )
            for item in candidate.forward_intents
        ),
        reference_continuity=tuple(
            CompactReferenceContinuityV4(
                text=item.text,
                reason=item.reason,
                source_labels=_ordered_labels(item.source_labels, boundary_order),
            )
            for item in candidate.reference_continuity
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


def _semantic_item_count(replacement: CompactAcceptedReplacementV4) -> int:
    """返回五个业务区的 item count。

    :param replacement: accepted replacement。
    :returns: semantic item count。
    """

    return (
        int(replacement.session_summary is not None)
        + len(replacement.evidence_facts)
        + len(replacement.answer_anchors)
        + len(replacement.forward_intents)
        + len(replacement.reference_continuity)
    )


def _canonical_text(text: str) -> str:
    """用统一 whitespace 规则 canonicalize 文本 identity。

    :param text: typed nonblank text。
    :returns: whitespace-canonical text。
    """

    return " ".join(text.split())


def _issue(
    code: CompactValidationIssueCodeV4,
    json_path: str,
    message: str,
    source_labels: tuple[str, ...] = (),
) -> CompactValidationIssueV4:
    """构造一条脱敏 validation issue。

    :param code: issue code。
    :param json_path: JSON path。
    :param message: 自解释提示。
    :param source_labels: opaque labels。
    :returns: typed issue。
    """

    return CompactValidationIssueV4(code=code, json_path=json_path, message=message, source_labels=source_labels)


def _validation_report(issues: list[CompactValidationIssueV4]) -> CompactValidationReportV4:
    """稳定排序并精确去重 issues。

    :param issues: accumulated issues。
    :returns: deterministic reject report。
    """

    unique = set(issues)
    ordered = tuple(sorted(unique, key=_validation_issue_sort_key))
    return CompactValidationReportV4(issues=ordered)


def _validation_issue_sort_key(
    issue: CompactValidationIssueV4,
) -> tuple[str, str, tuple[str, ...], str]:
    """返回 validation issue 的 deterministic 排序键。

    :param issue: typed validation issue。
    :returns: code、path、labels、message 排序键。
    """

    return (issue.code.value, issue.json_path, issue.source_labels, issue.message)


def _bounded_issue_message(issue: CompactValidationIssueV4) -> CompactValidationIssueV4:
    """脱敏并截断所有 internal repair transport issue 字段。

    :param issue: validation issue。
    :returns: path、message 与 labels 均脱敏且 bounded 的 issue。
    """

    safe_labels = tuple(dict.fromkeys(_bounded_feedback_text(label) for label in issue.source_labels))
    return CompactValidationIssueV4(
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


def _feedback_char_count(feedback: CompactRepairFeedbackV4) -> int:
    """计算 durable/internal feedback serialization 的 JSON 字符数。

    :param feedback: typed feedback。
    :returns: UTF-8 无关的 Python 字符数。
    """

    return len(json.dumps(feedback.to_json(), ensure_ascii=False, sort_keys=True))


__all__ = [
    "CompactAcceptanceResultV4",
    "accept_compact_candidate_v4",
    "build_compact_repair_feedback_v4",
]
