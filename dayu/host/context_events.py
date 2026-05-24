"""Host context compaction canonical event payload helpers。

本模块集中定义 Context Governance compact 相关 canonical fact 的 payload
builder 与 validator。EventLog primitive 只保存通用 ledger row；compact
业务语义、必填字段、触发来源约束与 accepted candidate 结构校验都在本模块
完成。
"""

from __future__ import annotations

from collections.abc import Mapping

from dayu.contracts.json_value import JsonValue
from dayu.host.compaction import (
    CompactInputRange,
    CompactQualityCheckResult,
    CompactionCandidate,
    EvidenceBackedFactCandidate,
    EvidenceBackedFactKind,
    MAX_EVIDENCE_BACKED_FACT_ATTRIBUTES_JSON_CHARS,
    MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS,
    MAX_EVIDENCE_BACKED_FACT_CANDIDATES,
    MAX_EVIDENCE_REFS_PER_FACT,
    MAX_MINIMUM_PRESERVE_ITEM_CANDIDATES,
    MAX_MINIMUM_PRESERVE_ITEM_LABEL_CHARS,
    MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS,
    MAX_SOURCE_REFS_PER_MINIMUM_PRESERVE_ITEM,
    MinimumPreserveItemCandidate,
    MinimumPreserveReason,
    PinnedPatchOperation,
    PreservationEvidence,
)
from dayu.host.context_budget import ContextBudgetDecision
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.codec import canonical_json_dumps, is_sha256_digest

CONTEXT_COMPACTION_REQUESTED = "CONTEXT_COMPACTION_REQUESTED"
"""Context compaction requested canonical event type。"""

CONTEXT_COMPACTED = "CONTEXT_COMPACTED"
"""Context compact accepted canonical event type。"""

CONTEXT_COMPACTION_FAILED = "CONTEXT_COMPACTION_FAILED"
"""Context compaction failed canonical event type。"""

CONTEXT_COMPACTION_ATTEMPT_REJECTED = "CONTEXT_COMPACTION_ATTEMPT_REJECTED"
"""Context compaction semantic attempt rejected canonical event type。"""

_FIELD_TRIGGER_SOURCE = "trigger_source"
_FIELD_BUDGET_REASON = "budget_reason"
_FIELD_BUDGET_SNAPSHOT_REF = "budget_snapshot_ref"
_FIELD_INPUT_SNAPSHOT_CURSOR = "input_snapshot_cursor"
_FIELD_ESTIMATOR_DIGEST = "estimator_digest"
_FIELD_POLICY_REF = "policy_ref"
_FIELD_PROVIDER_REQUEST_ID = "provider_request_id"
_FIELD_PROVIDER_ERROR_REF = "provider_error_ref"
_FIELD_ATTEMPT_ID = "attempt_id"
_FIELD_EXECUTION_ID = "execution_id"
_FIELD_COMPACT_ARTIFACT_REF = "compact_artifact_ref"
_FIELD_COMPACT_ARTIFACT_DIGEST = "compact_artifact_digest"
_FIELD_EPISODE_SUMMARY_CANDIDATE = "episode_summary_candidate"
_FIELD_PINNED_STATE_PATCH_CANDIDATE = "pinned_state_patch_candidate"
_FIELD_PRESERVATION_EVIDENCE = "preservation_evidence"
_FIELD_EVIDENCE_BACKED_FACT_CANDIDATES = "evidence_backed_fact_candidates"
_FIELD_MINIMUM_PRESERVE_ITEM_CANDIDATES = "minimum_preserve_item_candidates"
_FIELD_PRESERVED_FACT_REFS = "preserved_fact_refs"
_FIELD_DROPPED_RANGES = "dropped_ranges"
_FIELD_SUMMARIZED_RANGES = "summarized_ranges"
_FIELD_EVIDENCE_ANCHORS_RETAINED = "evidence_anchors_retained"
_FIELD_QUALITY_CHECK_RESULT = "quality_check_result"
_FIELD_BUDGET_AFTER_COMPACT = "budget_after_compact"
_FIELD_FAILURE_REASON = "failure_reason"
_FIELD_OPERATION_ID = "operation_id"
_FIELD_ATTEMPT_NUMBER = "attempt_number"
_FIELD_FAILURE_CATEGORY = "failure_category"
_FIELD_REPAIRABLE = "repairable"
_FIELD_RUNNER_ATTEMPT_SUMMARY_REFS = "runner_attempt_summary_refs"
_FIELD_NEXT_POLICY_DECISION = "next_policy_decision"
_FIELD_POLICY_DECISION = "policy_decision"
_FIELD_RETRYABLE = "retryable"
_FIELD_DIAGNOSTIC_REFS = "diagnostic_refs"
_FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT = "budget_after_attempted_compact"
_FIELD_EVIDENCE_REFS = "evidence_refs"
_FIELD_EVIDENCE_ID = "evidence_id"
_FIELD_CANONICAL_EVIDENCE_REFS = "canonical_evidence_refs"
_FIELD_EVIDENCE_BACKED_FACT_REFS = "evidence_backed_fact_refs"
_FIELD_CANDIDATE_ID = "candidate_id"
_FIELD_ITEM_ID = "item_id"
_FIELD_CLAIM_TEXT = "claim_text"
_FIELD_EVIDENCE_KIND = "evidence_kind"
_FIELD_ATTRIBUTES = "attributes"
_FIELD_LABEL = "label"
_FIELD_TEXT = "text"
_FIELD_SOURCE_REFS = "source_refs"
_FIELD_PRESERVE_REASON = "preserve_reason"
_FIELD_CURRENT_GOAL = "current_goal"
_FIELD_USER_CONSTRAINTS = "user_constraints"
_FIELD_OPEN_QUESTIONS = "open_questions"
_FIELD_PROPOSED_EVIDENCE_BACKED_FACT_REFS = "proposed_evidence_backed_fact_refs"
_FIELD_OLD_PROPOSED_VERIFIED_FACT_REFS = "proposed_verified_fact_refs"
_FIELD_OLD_TOOL_FACT_REFS = "tool_fact_refs"
_FIELD_OLD_VERIFIED_FACT_REFS = "verified_fact_refs"
_FIELD_OLD_ACCEPTED_TOOL_FACT_REFS_RETAINED = "accepted_tool_fact_refs_retained"
_FIELD_OLD_RETAINED_EVIDENCE_REFS = "retained_evidence_refs"
_FIELD_OPERATION = "operation"
_FIELD_VALUE = "value"
_FIELD_CONFIRMED_SUBJECTS = "confirmed_subjects"
_FIELD_ACCEPTED = "accepted"
_FIELD_REJECTION_REASONS = "rejection_reasons"
_FIELD_CURRENT_USER_INPUT_RETAINED = "current_user_input_retained"
_FIELD_CANONICAL_EVIDENCE_REFS_RETAINED = "canonical_evidence_refs_retained"
_FIELD_EVIDENCE_BACKED_FACT_CANDIDATES_ACCEPTED = (
    "evidence_backed_fact_candidates_accepted"
)
_FIELD_MINIMUM_PRESERVE_ITEMS_ACCEPTED = "minimum_preserve_items_accepted"
_FIELD_OPEN_QUESTIONS_RETAINED = "open_questions_retained"
_FIELD_RETAINED_CANONICAL_EVIDENCE_REFS = "retained_canonical_evidence_refs"

_REQUESTED_REQUIRED_FIELDS = (
    _FIELD_TRIGGER_SOURCE,
    _FIELD_BUDGET_REASON,
    _FIELD_BUDGET_SNAPSHOT_REF,
    _FIELD_INPUT_SNAPSHOT_CURSOR,
    _FIELD_ESTIMATOR_DIGEST,
    _FIELD_POLICY_REF,
    _FIELD_PROVIDER_REQUEST_ID,
    _FIELD_PROVIDER_ERROR_REF,
    _FIELD_ATTEMPT_ID,
    _FIELD_EXECUTION_ID,
)
_COMPACTED_REQUIRED_FIELDS = (
    _FIELD_COMPACT_ARTIFACT_REF,
    _FIELD_COMPACT_ARTIFACT_DIGEST,
    _FIELD_EPISODE_SUMMARY_CANDIDATE,
    _FIELD_PINNED_STATE_PATCH_CANDIDATE,
    _FIELD_PRESERVATION_EVIDENCE,
    _FIELD_EVIDENCE_BACKED_FACT_CANDIDATES,
    _FIELD_MINIMUM_PRESERVE_ITEM_CANDIDATES,
    _FIELD_PRESERVED_FACT_REFS,
    _FIELD_DROPPED_RANGES,
    _FIELD_SUMMARIZED_RANGES,
    _FIELD_EVIDENCE_ANCHORS_RETAINED,
    _FIELD_QUALITY_CHECK_RESULT,
    _FIELD_BUDGET_AFTER_COMPACT,
)
_FAILED_REQUIRED_FIELDS = (
    _FIELD_FAILURE_REASON,
    _FIELD_POLICY_DECISION,
    _FIELD_RETRYABLE,
    _FIELD_DIAGNOSTIC_REFS,
    _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT,
)
_ATTEMPT_REJECTED_REQUIRED_FIELDS = (
    _FIELD_OPERATION_ID,
    _FIELD_ATTEMPT_NUMBER,
    _FIELD_FAILURE_CATEGORY,
    _FIELD_REPAIRABLE,
    _FIELD_RUNNER_ATTEMPT_SUMMARY_REFS,
    _FIELD_DIAGNOSTIC_REFS,
    _FIELD_NEXT_POLICY_DECISION,
    _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT,
)
_PATCH_ALLOWED_FIELDS = frozenset(
    (
        _FIELD_CANDIDATE_ID,
        _FIELD_CURRENT_GOAL,
        _FIELD_CONFIRMED_SUBJECTS,
        _FIELD_USER_CONSTRAINTS,
        _FIELD_OPEN_QUESTIONS,
    )
)


def build_context_compaction_requested_payload(
    *,
    trigger_source: ContextCompactionTriggerSource,
    budget_reason: str,
    budget_snapshot_ref: str,
    input_snapshot_cursor: int,
    estimator_digest: str,
    policy_ref: str,
    provider_request_id: str | None,
    provider_error_ref: str | None,
    attempt_id: str | None,
    execution_id: str | None,
) -> Mapping[str, JsonValue]:
    """构造 ``CONTEXT_COMPACTION_REQUESTED`` payload。

    :param trigger_source: compact 触发来源。
    :param budget_reason: 预算触发或 provider fallback 原因。
    :param budget_snapshot_ref: budget snapshot / estimate ref。
    :param input_snapshot_cursor: 输入 snapshot cursor。
    :param estimator_digest: budget estimator digest。
    :param policy_ref: Host context policy ref。
    :param provider_request_id: provider request id；没有时为 ``None``。
    :param provider_error_ref: provider error ref；没有时为 ``None``。
    :param attempt_id: reactive compact 对应 Attempt id。
    :param execution_id: reactive compact 对应 execution id。
    :returns: 可写入 EventLog 的 JSON payload。
    :raises TypeError: 字段类型非法时抛出。
    :raises ValueError: 字段值非法时抛出。
    """

    if not isinstance(trigger_source, ContextCompactionTriggerSource):
        raise TypeError("trigger_source must be ContextCompactionTriggerSource")
    payload: Mapping[str, JsonValue] = {
        _FIELD_TRIGGER_SOURCE: trigger_source.value,
        _FIELD_BUDGET_REASON: budget_reason,
        _FIELD_BUDGET_SNAPSHOT_REF: budget_snapshot_ref,
        _FIELD_INPUT_SNAPSHOT_CURSOR: input_snapshot_cursor,
        _FIELD_ESTIMATOR_DIGEST: estimator_digest,
        _FIELD_POLICY_REF: policy_ref,
        _FIELD_PROVIDER_REQUEST_ID: provider_request_id,
        _FIELD_PROVIDER_ERROR_REF: provider_error_ref,
        _FIELD_ATTEMPT_ID: attempt_id,
        _FIELD_EXECUTION_ID: execution_id,
    }
    validate_context_compaction_requested_payload(payload)
    return payload


def validate_context_compaction_requested_payload(
    payload: Mapping[str, JsonValue],
) -> None:
    """校验 ``CONTEXT_COMPACTION_REQUESTED`` payload。

    :param payload: 待校验 JSON payload。
    :returns: ``None``。
    :raises ValueError: payload 缺少必填字段或字段非法时抛出。
    """

    _require_fields(payload, _REQUESTED_REQUIRED_FIELDS)
    trigger_source = ContextCompactionTriggerSource(
        _required_text(payload, _FIELD_TRIGGER_SOURCE)
    )
    _required_text(payload, _FIELD_BUDGET_REASON)
    _required_text(payload, _FIELD_BUDGET_SNAPSHOT_REF)
    _required_non_negative_int(payload, _FIELD_INPUT_SNAPSHOT_CURSOR)
    _required_digest(payload, _FIELD_ESTIMATOR_DIGEST)
    _required_text(payload, _FIELD_POLICY_REF)
    _optional_text(payload, _FIELD_PROVIDER_REQUEST_ID)
    _optional_text(payload, _FIELD_PROVIDER_ERROR_REF)
    attempt_id = _optional_text(payload, _FIELD_ATTEMPT_ID)
    execution_id = _optional_text(payload, _FIELD_EXECUTION_ID)
    if trigger_source is ContextCompactionTriggerSource.REACTIVE:
        if attempt_id is None or execution_id is None:
            raise ValueError("reactive compaction requires attempt_id and execution_id")


def build_context_compacted_payload(
    *,
    compact_artifact_ref: str,
    compact_artifact_digest: str,
    accepted_candidate: CompactionCandidate,
    quality_check_result: CompactQualityCheckResult,
) -> Mapping[str, JsonValue]:
    """构造 ``CONTEXT_COMPACTED`` payload。

    :param compact_artifact_ref: compact artifact payload / artifact ref。
    :param compact_artifact_digest: compact artifact digest。
    :param accepted_candidate: 通过 quality check 的 compact candidate。
    :param quality_check_result: accepted quality check 结果。
    :returns: 可写入 EventLog 的 JSON payload。
    :raises TypeError: 输入类型非法时抛出。
    :raises ValueError: payload 结构非法时抛出。
    """

    if not isinstance(accepted_candidate, CompactionCandidate):
        raise TypeError("accepted_candidate must be CompactionCandidate")
    if not isinstance(quality_check_result, CompactQualityCheckResult):
        raise TypeError("quality_check_result must be CompactQualityCheckResult")
    payload: Mapping[str, JsonValue] = {
        _FIELD_COMPACT_ARTIFACT_REF: compact_artifact_ref,
        _FIELD_COMPACT_ARTIFACT_DIGEST: compact_artifact_digest,
        _FIELD_EPISODE_SUMMARY_CANDIDATE: (
            accepted_candidate.episode_summary_candidate.to_json()
        ),
        _FIELD_PINNED_STATE_PATCH_CANDIDATE: (
            accepted_candidate.pinned_state_patch_candidate.to_json()
        ),
        _FIELD_PRESERVATION_EVIDENCE: _evidence_list_json(
            accepted_candidate.preservation_evidence
        ),
        _FIELD_EVIDENCE_BACKED_FACT_CANDIDATES: _fact_candidate_list_json(
            accepted_candidate.evidence_backed_fact_candidates
        ),
        _FIELD_MINIMUM_PRESERVE_ITEM_CANDIDATES: (
            _minimum_preserve_candidate_list_json(
                accepted_candidate.minimum_preserve_item_candidates
            )
        ),
        _FIELD_PRESERVED_FACT_REFS: {
            _FIELD_CANONICAL_EVIDENCE_REFS: _string_list_json(
                accepted_candidate.preserved_canonical_evidence_refs
            ),
            _FIELD_EVIDENCE_BACKED_FACT_REFS: _string_list_json(
                accepted_candidate.preserved_evidence_backed_fact_refs
            ),
        },
        _FIELD_DROPPED_RANGES: _range_list_json(accepted_candidate.dropped_ranges),
        _FIELD_SUMMARIZED_RANGES: _range_list_json(
            accepted_candidate.summarized_ranges
        ),
        _FIELD_EVIDENCE_ANCHORS_RETAINED: (
            quality_check_result.evidence_anchors_retained
        ),
        _FIELD_QUALITY_CHECK_RESULT: quality_check_result.to_json(),
        _FIELD_BUDGET_AFTER_COMPACT: accepted_candidate.budget_after_compact,
    }
    validate_context_compacted_payload(payload)
    return payload


def validate_context_compacted_payload(payload: Mapping[str, JsonValue]) -> None:
    """校验 ``CONTEXT_COMPACTED`` payload。

    :param payload: 待校验 JSON payload。
    :returns: ``None``。
    :raises ValueError: payload 缺少必填字段、artifact ref/digest 不成对或
        summary / patch 缺少 preservation evidence 时抛出。
    """

    _require_fields(payload, _COMPACTED_REQUIRED_FIELDS)
    _required_text(payload, _FIELD_COMPACT_ARTIFACT_REF)
    _required_digest(payload, _FIELD_COMPACT_ARTIFACT_DIGEST)
    summary = _required_mapping(payload, _FIELD_EPISODE_SUMMARY_CANDIDATE)
    patch = _required_mapping(payload, _FIELD_PINNED_STATE_PATCH_CANDIDATE)
    evidence = _required_mapping_list(payload, _FIELD_PRESERVATION_EVIDENCE)
    evidence_ids = _evidence_ids(evidence)
    summary_evidence_refs = _required_text_list(summary, _FIELD_EVIDENCE_REFS)
    if len(summary_evidence_refs) == 0:
        raise ValueError("episode summary candidate requires preservation evidence")
    if not set(summary_evidence_refs).issubset(evidence_ids):
        raise ValueError("episode summary evidence refs must exist")
    if _FIELD_OLD_PROPOSED_VERIFIED_FACT_REFS in summary:
        raise ValueError("old proposed verified fact refs field is not supported")
    proposed_fact_refs = _optional_text_list(
        summary, _FIELD_PROPOSED_EVIDENCE_BACKED_FACT_REFS
    )
    if len(proposed_fact_refs) > 0:
        raise ValueError("compact summary must not propose evidence-backed facts")
    _validate_patch_evidence(patch, evidence_ids=evidence_ids)
    _validate_confirmed_subject_patch(patch)
    preserved_fact_refs = _required_mapping(payload, _FIELD_PRESERVED_FACT_REFS)
    _reject_old_preserved_fact_ref_fields(preserved_fact_refs)
    canonical_evidence_refs = _required_text_list(
        preserved_fact_refs, _FIELD_CANONICAL_EVIDENCE_REFS
    )
    _required_text_list(preserved_fact_refs, _FIELD_EVIDENCE_BACKED_FACT_REFS)
    _validate_fact_candidates(
        payload,
        canonical_evidence_refs=set(canonical_evidence_refs),
    )
    _validate_minimum_preserve_items(payload)
    _required_list(payload, _FIELD_DROPPED_RANGES)
    _required_list(payload, _FIELD_SUMMARIZED_RANGES)
    _required_bool(payload, _FIELD_EVIDENCE_ANCHORS_RETAINED)
    _validate_quality_check_result(
        payload,
        canonical_evidence_refs=set(canonical_evidence_refs),
    )
    _required_non_negative_int(payload, _FIELD_BUDGET_AFTER_COMPACT)


def build_context_compaction_failed_payload(
    *,
    failure_reason: str,
    policy_decision: ContextBudgetDecision | str,
    retryable: bool,
    diagnostic_refs: tuple[str, ...],
    budget_after_attempted_compact: int | None,
) -> Mapping[str, JsonValue]:
    """构造 ``CONTEXT_COMPACTION_FAILED`` payload。

    :param failure_reason: compact 失败原因。
    :param policy_decision: compact 失败后的 policy decision。
    :param retryable: 当前失败是否可重试。
    :param diagnostic_refs: 诊断 ref 列表。
    :param budget_after_attempted_compact: compact 尝试后的预算估算；未知时为
        ``None``。
    :returns: 可写入 EventLog 的 JSON payload。
    :raises TypeError: 字段类型非法时抛出。
    :raises ValueError: 字段值非法时抛出。
    """

    if isinstance(policy_decision, ContextBudgetDecision):
        policy_decision_value = policy_decision.value
    else:
        policy_decision_value = policy_decision
    payload: Mapping[str, JsonValue] = {
        _FIELD_FAILURE_REASON: failure_reason,
        _FIELD_POLICY_DECISION: policy_decision_value,
        _FIELD_RETRYABLE: retryable,
        _FIELD_DIAGNOSTIC_REFS: _string_list_json(diagnostic_refs),
        _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT: budget_after_attempted_compact,
    }
    validate_context_compaction_failed_payload(payload)
    return payload


def validate_context_compaction_failed_payload(payload: Mapping[str, JsonValue]) -> None:
    """校验 ``CONTEXT_COMPACTION_FAILED`` payload。

    :param payload: 待校验 JSON payload。
    :returns: ``None``。
    :raises ValueError: payload 缺少必填字段或字段非法时抛出。
    """

    _require_fields(payload, _FAILED_REQUIRED_FIELDS)
    _required_text(payload, _FIELD_FAILURE_REASON)
    _required_text(payload, _FIELD_POLICY_DECISION)
    _required_bool(payload, _FIELD_RETRYABLE)
    _required_text_list(payload, _FIELD_DIAGNOSTIC_REFS)
    _optional_non_negative_int(payload, _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT)


def build_context_compaction_attempt_rejected_payload(
    *,
    operation_id: str,
    attempt_number: int,
    failure_category: str,
    repairable: bool,
    runner_attempt_summary_refs: tuple[str, ...],
    diagnostic_refs: tuple[str, ...],
    next_policy_decision: str,
    budget_after_attempted_compact: int | None,
) -> Mapping[str, JsonValue]:
    """构造 ``CONTEXT_COMPACTION_ATTEMPT_REJECTED`` payload。

    :param operation_id: compaction operation id。
    :param attempt_number: operation 内 proposal attempt 序号，从 1 开始。
    :param failure_category: 失败类别。
    :param repairable: 当前失败是否可进入下一次 semantic repair attempt。
    :param runner_attempt_summary_refs: runner attempt 摘要 ref 列表。
    :param diagnostic_refs: quality / parse / budget 诊断 ref 列表。
    :param next_policy_decision: 下一步 Host policy decision。
    :param budget_after_attempted_compact: 本次 attempt 后预算；未知时为
        ``None``。
    :returns: 可写入 EventLog 的 JSON payload。
    :raises ValueError: payload 字段非法时抛出。
    """

    payload: Mapping[str, JsonValue] = {
        _FIELD_OPERATION_ID: operation_id,
        _FIELD_ATTEMPT_NUMBER: attempt_number,
        _FIELD_FAILURE_CATEGORY: failure_category,
        _FIELD_REPAIRABLE: repairable,
        _FIELD_RUNNER_ATTEMPT_SUMMARY_REFS: _string_list_json(
            runner_attempt_summary_refs
        ),
        _FIELD_DIAGNOSTIC_REFS: _string_list_json(diagnostic_refs),
        _FIELD_NEXT_POLICY_DECISION: next_policy_decision,
        _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT: budget_after_attempted_compact,
    }
    validate_context_compaction_attempt_rejected_payload(payload)
    return payload


def validate_context_compaction_attempt_rejected_payload(
    payload: Mapping[str, JsonValue],
) -> None:
    """校验 ``CONTEXT_COMPACTION_ATTEMPT_REJECTED`` payload。

    :param payload: 待校验 JSON payload。
    :returns: ``None``。
    :raises ValueError: payload 缺少必填字段或字段非法时抛出。
    """

    _require_fields(payload, _ATTEMPT_REJECTED_REQUIRED_FIELDS)
    _required_text(payload, _FIELD_OPERATION_ID)
    _required_positive_int(payload, _FIELD_ATTEMPT_NUMBER)
    _required_text(payload, _FIELD_FAILURE_CATEGORY)
    _required_bool(payload, _FIELD_REPAIRABLE)
    runner_refs = _required_text_list(payload, _FIELD_RUNNER_ATTEMPT_SUMMARY_REFS)
    if len(runner_refs) == 0:
        raise ValueError("runner_attempt_summary_refs must be non-empty")
    diagnostic_refs = _required_text_list(payload, _FIELD_DIAGNOSTIC_REFS)
    if len(diagnostic_refs) == 0:
        raise ValueError("diagnostic_refs must be non-empty")
    _required_text(payload, _FIELD_NEXT_POLICY_DECISION)
    _optional_non_negative_int(payload, _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT)


def _range_list_json(values: tuple[CompactInputRange, ...]) -> list[JsonValue]:
    """把 compact range tuple 转换为 JSON 数组。

    :param values: compact range tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _evidence_list_json(values: tuple[PreservationEvidence, ...]) -> list[JsonValue]:
    """把 preservation evidence tuple 转换为 JSON 数组。

    :param values: preservation evidence tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _fact_candidate_list_json(
    values: tuple[EvidenceBackedFactCandidate, ...],
) -> list[JsonValue]:
    """把 evidence-backed fact candidate tuple 转换为 JSON 数组。

    :param values: candidate tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _minimum_preserve_candidate_list_json(
    values: tuple[MinimumPreserveItemCandidate, ...],
) -> list[JsonValue]:
    """把 minimum preserve item candidate tuple 转换为 JSON 数组。

    :param values: candidate tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _string_list_json(values: tuple[str, ...]) -> list[JsonValue]:
    """把字符串 tuple 转换为 JSON 数组。

    :param values: 字符串 tuple。
    :returns: JSON 数组。
    :raises TypeError: 输入不是 tuple 或元素不是文本时抛出。
    :raises ValueError: 元素为空时抛出。
    """

    if not isinstance(values, tuple):
        raise TypeError("values must be tuple")
    result: list[JsonValue] = []
    for value in values:
        _require_non_empty_text_value(value, "values item")
        result.append(value)
    return result


def _require_fields(payload: Mapping[str, JsonValue], fields: tuple[str, ...]) -> None:
    """校验 payload 含有全部顶层必填字段。

    :param payload: JSON payload。
    :param fields: 必填字段名。
    :returns: ``None``。
    :raises ValueError: 缺少字段时抛出。
    """

    for field_name in fields:
        if field_name not in payload:
            raise ValueError(f"{field_name} is required")


def _required_text(payload: Mapping[str, JsonValue], field_name: str) -> str:
    """读取必填非空文本字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 文本值。
    :raises ValueError: 字段缺失或不是非空文本时抛出。
    """

    value = payload.get(field_name)
    return _require_non_empty_text_value(value, field_name)


def _optional_text(payload: Mapping[str, JsonValue], field_name: str) -> str | None:
    """读取可选非空文本字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 文本值或 ``None``。
    :raises ValueError: 字段存在但不是非空文本时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    return _require_non_empty_text_value(value, field_name)


def _required_digest(payload: Mapping[str, JsonValue], field_name: str) -> str:
    """读取必填 sha256 digest 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: digest 文本。
    :raises ValueError: 字段缺失或 digest 非法时抛出。
    """

    value = _required_text(payload, field_name)
    if not is_sha256_digest(value):
        raise ValueError(f"{field_name} must be sha256 digest")
    return value


def _required_non_negative_int(
    payload: Mapping[str, JsonValue], field_name: str
) -> int:
    """读取必填非负整数字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 非负整数。
    :raises ValueError: 字段缺失、类型非法或为负数时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _required_positive_int(
    payload: Mapping[str, JsonValue], field_name: str
) -> int:
    """读取必填正整数字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 正整数。
    :raises ValueError: 字段缺失、类型非法或非正时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value


def _optional_non_negative_int(
    payload: Mapping[str, JsonValue], field_name: str
) -> int | None:
    """读取可选非负整数字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 非负整数或 ``None``。
    :raises ValueError: 字段存在但类型非法或为负数时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _required_bool(payload: Mapping[str, JsonValue], field_name: str) -> bool:
    """读取必填布尔字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 布尔值。
    :raises ValueError: 字段缺失或不是布尔值时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be bool")
    return value


def _required_mapping(
    payload: Mapping[str, JsonValue], field_name: str
) -> Mapping[str, JsonValue]:
    """读取必填 JSON object 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: JSON object。
    :raises ValueError: 字段缺失或不是 object 时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be mapping")
    return value


def _required_list(
    payload: Mapping[str, JsonValue], field_name: str
) -> list[JsonValue]:
    """读取必填 JSON array 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: JSON array。
    :raises ValueError: 字段缺失或不是 array 时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be list")
    return value


def _required_mapping_list(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[Mapping[str, JsonValue], ...]:
    """读取必填 JSON object array 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: JSON object tuple。
    :raises ValueError: 字段缺失或元素不是 object 时抛出。
    """

    items = _required_list(payload, field_name)
    mappings: list[Mapping[str, JsonValue]] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError(f"{field_name} items must be mapping")
        mappings.append(item)
    return tuple(mappings)


def _required_text_list(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[str, ...]:
    """读取必填非空文本 array 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 文本 tuple。
    :raises ValueError: 字段缺失、不是 array 或元素非法时抛出。
    """

    items = _required_list(payload, field_name)
    values: list[str] = []
    for item in items:
        values.append(_require_non_empty_text_value(item, field_name))
    return tuple(values)


def _optional_text_list(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[str, ...]:
    """读取可选非空文本 array 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 文本 tuple；字段缺失时返回空 tuple。
    :raises ValueError: 字段存在但不是文本 array 时抛出。
    """

    if field_name not in payload:
        return ()
    value = payload.get(field_name)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be list")
    values: list[str] = []
    for item in value:
        values.append(_require_non_empty_text_value(item, field_name))
    return tuple(values)


def _evidence_ids(evidence_items: tuple[Mapping[str, JsonValue], ...]) -> set[str]:
    """读取 preservation evidence id 集合。

    :param evidence_items: preservation evidence JSON object tuple。
    :returns: evidence id 集合。
    :raises ValueError: evidence id 缺失或重复时抛出。
    """

    values: set[str] = set()
    for item in evidence_items:
        evidence_id = _required_text(item, _FIELD_EVIDENCE_ID)
        if evidence_id in values:
            raise ValueError("preservation evidence ids must be unique")
        values.add(evidence_id)
    if len(values) == 0:
        raise ValueError("preservation evidence is required")
    return values


def _validate_patch_evidence(
    patch: Mapping[str, JsonValue], *, evidence_ids: set[str]
) -> None:
    """校验 pinned patch 的非 missing 字段都有 evidence refs。

    :param patch: pinned patch candidate JSON object。
    :param evidence_ids: 已知 preservation evidence ids。
    :returns: ``None``。
    :raises ValueError: patch 非 missing 操作缺少 evidence refs 时抛出。
    """

    _required_text(patch, _FIELD_CANDIDATE_ID)
    for field_name, value in patch.items():
        if field_name not in _PATCH_ALLOWED_FIELDS:
            raise ValueError("pinned patch field is not supported")
        if field_name == _FIELD_CANDIDATE_ID:
            continue
        if not isinstance(value, Mapping):
            raise ValueError("pinned patch field must be mapping")
        operation = PinnedPatchOperation(_required_text(value, _FIELD_OPERATION))
        if operation is PinnedPatchOperation.MISSING:
            continue
        refs = _required_text_list(value, _FIELD_EVIDENCE_REFS)
        if len(refs) == 0:
            raise ValueError("pinned patch requires preservation evidence")
        if not set(refs).issubset(evidence_ids):
            raise ValueError("pinned patch evidence refs must exist")
        if operation is PinnedPatchOperation.REPLACE:
            _validate_replace_patch_value(value, field_name)


def _validate_confirmed_subject_patch(patch: Mapping[str, JsonValue]) -> None:
    """校验 confirmed_subjects patch 不接受自由业务字符串。

    :param patch: pinned patch candidate JSON object。
    :returns: ``None``。
    :raises ValueError: confirmed_subjects replace 值不是合法 opaque ref 时抛出。
    """

    value = patch.get(_FIELD_CONFIRMED_SUBJECTS)
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise ValueError("confirmed_subjects patch must be mapping")
    operation = PinnedPatchOperation(_required_text(value, _FIELD_OPERATION))
    if operation is not PinnedPatchOperation.REPLACE:
        return
    values = _required_list(value, _FIELD_VALUE)
    for item in values:
        _validate_confirmed_subject_item(item)


def _validate_replace_patch_value(
    patch_field: Mapping[str, JsonValue], field_name: str
) -> None:
    """校验 replace patch 的 value 类型。

    :param patch_field: pinned patch 字段 JSON object。
    :param field_name: pinned patch 字段名。
    :returns: ``None``。
    :raises ValueError: replace value 类型或内容非法时抛出。
    """

    if field_name == _FIELD_CURRENT_GOAL:
        _required_text(patch_field, _FIELD_VALUE)
        return
    values = _required_list(patch_field, _FIELD_VALUE)
    if field_name == _FIELD_CONFIRMED_SUBJECTS:
        for item in values:
            _validate_confirmed_subject_item(item)
        return
    for item in values:
        _require_non_empty_text_value(item, field_name)


def _validate_confirmed_subject_item(item: JsonValue) -> None:
    """校验 confirmed subject patch 元素。

    :param item: patch 元素。
    :returns: ``None``。
    :raises ValueError: 元素不是合法 opaque ref 时抛出。
    """

    if isinstance(item, Mapping):
        kind = _required_text(item, "ref_kind")
        _validate_opaque_ref_kind(kind)
        _required_text(item, "ref_id")
        _optional_text(item, "digest")
    elif isinstance(item, str):
        _validate_opaque_ref_text(item)
    else:
        raise ValueError("confirmed_subjects items must be opaque refs")


def _validate_fact_candidates(
    payload: Mapping[str, JsonValue], *, canonical_evidence_refs: set[str]
) -> None:
    """校验 evidence-backed fact candidates JSON 结构。

    :param payload: compacted payload。
    :param canonical_evidence_refs: 已保留 canonical evidence refs。
    :returns: ``None``。
    :raises ValueError: candidates 数量、文本或 refs 非法时抛出。
    """

    candidates = _required_mapping_list(
        payload, _FIELD_EVIDENCE_BACKED_FACT_CANDIDATES
    )
    if len(candidates) > MAX_EVIDENCE_BACKED_FACT_CANDIDATES:
        raise ValueError("evidence_backed_fact_candidates exceeds maximum count")
    for candidate in candidates:
        _required_text(candidate, _FIELD_CANDIDATE_ID)
        claim_text = _required_text(candidate, _FIELD_CLAIM_TEXT)
        if len(claim_text) > MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS:
            raise ValueError("claim_text exceeds maximum length")
        EvidenceBackedFactKind(_required_text(candidate, _FIELD_EVIDENCE_KIND))
        refs = _required_text_list(candidate, _FIELD_EVIDENCE_REFS)
        if len(refs) == 0:
            raise ValueError("evidence-backed fact requires evidence_refs")
        if len(refs) > MAX_EVIDENCE_REFS_PER_FACT:
            raise ValueError("evidence_refs exceeds maximum count")
        if not set(refs).issubset(canonical_evidence_refs):
            raise ValueError("evidence-backed fact refs must be canonical evidence")
        attributes = _required_mapping(candidate, _FIELD_ATTRIBUTES)
        attributes_json = canonical_json_dumps(attributes)
        if len(attributes_json) > MAX_EVIDENCE_BACKED_FACT_ATTRIBUTES_JSON_CHARS:
            raise ValueError("attributes exceeds maximum length")


def _reject_old_preserved_fact_ref_fields(
    preserved_fact_refs: Mapping[str, JsonValue],
) -> None:
    """拒绝旧 compact preserved fact refs 字段。

    :param preserved_fact_refs: compacted preserved_fact_refs JSON object。
    :returns: ``None``。
    :raises ValueError: 存在旧字段时抛出。
    """

    for field_name in (_FIELD_OLD_TOOL_FACT_REFS, _FIELD_OLD_VERIFIED_FACT_REFS):
        if field_name in preserved_fact_refs:
            raise ValueError("old preserved fact refs field is not supported")


def _validate_minimum_preserve_items(payload: Mapping[str, JsonValue]) -> None:
    """校验 minimum preserve item candidates JSON 结构。

    :param payload: compacted payload。
    :returns: ``None``。
    :raises ValueError: candidates 数量、文本或 refs 非法时抛出。
    """

    candidates = _required_mapping_list(
        payload, _FIELD_MINIMUM_PRESERVE_ITEM_CANDIDATES
    )
    if len(candidates) > MAX_MINIMUM_PRESERVE_ITEM_CANDIDATES:
        raise ValueError("minimum_preserve_item_candidates exceeds maximum count")
    for candidate in candidates:
        _required_text(candidate, _FIELD_ITEM_ID)
        label = _required_text(candidate, _FIELD_LABEL)
        if len(label) > MAX_MINIMUM_PRESERVE_ITEM_LABEL_CHARS:
            raise ValueError("minimum preserve label exceeds maximum length")
        text = _required_text(candidate, _FIELD_TEXT)
        if len(text) > MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS:
            raise ValueError("minimum preserve text exceeds maximum length")
        refs = _required_text_list(candidate, _FIELD_SOURCE_REFS)
        if len(refs) == 0:
            raise ValueError("minimum preserve source_refs must be non-empty")
        if len(refs) > MAX_SOURCE_REFS_PER_MINIMUM_PRESERVE_ITEM:
            raise ValueError("minimum preserve source_refs exceeds maximum count")
        MinimumPreserveReason(_required_text(candidate, _FIELD_PRESERVE_REASON))


def _validate_opaque_ref_text(value: str) -> None:
    """校验 ``kind:ref_id`` 形式的 Host-neutral opaque ref 文本。

    :param value: ref 文本。
    :returns: ``None``。
    :raises ValueError: 文本不是 opaque ref 时抛出。
    """

    _require_non_empty_text_value(value, "opaque ref")
    if ":" not in value:
        raise ValueError("opaque ref text requires kind prefix")
    kind, ref_id = value.split(":", 1)
    _validate_opaque_ref_kind(kind)
    if ref_id.strip() == "":
        raise ValueError("opaque ref id is required")


def _validate_opaque_ref_kind(kind: str) -> None:
    """校验 Host-neutral opaque ref kind。

    :param kind: ref kind 文本。
    :returns: ``None``。
    :raises ValueError: kind 不在 Host-neutral ref 集合内时抛出。
    """

    if kind not in _allowed_opaque_ref_kinds():
        raise ValueError("opaque ref kind is invalid")


def _allowed_opaque_ref_kinds() -> set[str]:
    """返回 Host-neutral opaque ref kind 集合。

    :returns: ref kind 集合。
    """

    return {
        "source",
        "chunk",
        "entity",
        "subject",
        "topic",
        "evidence",
        "payload",
        "external",
    }


def _validate_quality_check_result(
    payload: Mapping[str, JsonValue], *, canonical_evidence_refs: set[str]
) -> None:
    """校验 ``CONTEXT_COMPACTED`` 只承载 accepted quality result。

    :param payload: compacted payload。
    :param canonical_evidence_refs: canonical evidence refs 集合。
    :returns: ``None``。
    :raises ValueError: quality result 非 accepted 或 retained evidence 非法时抛出。
    """

    result = _required_mapping(payload, _FIELD_QUALITY_CHECK_RESULT)
    _reject_old_quality_result_fields(result)
    accepted = _required_bool(result, _FIELD_ACCEPTED)
    if not accepted:
        raise ValueError("context compacted requires accepted quality result")
    if len(_required_text_list(result, _FIELD_REJECTION_REASONS)) > 0:
        raise ValueError("accepted quality result must not include rejection reasons")
    for field_name in (
        _FIELD_CURRENT_USER_INPUT_RETAINED,
        _FIELD_CANONICAL_EVIDENCE_REFS_RETAINED,
        _FIELD_EVIDENCE_BACKED_FACT_CANDIDATES_ACCEPTED,
        _FIELD_MINIMUM_PRESERVE_ITEMS_ACCEPTED,
        _FIELD_EVIDENCE_ANCHORS_RETAINED,
        _FIELD_OPEN_QUESTIONS_RETAINED,
    ):
        if not _required_bool(result, field_name):
            raise ValueError(f"{field_name} must be true for accepted compact")
    retained_refs = _required_text_list(
        result, _FIELD_RETAINED_CANONICAL_EVIDENCE_REFS
    )
    if not set(retained_refs).issubset(canonical_evidence_refs):
        raise ValueError("retained canonical evidence refs must exist")
    _required_list(result, _FIELD_DROPPED_RANGES)
    _required_list(result, _FIELD_SUMMARIZED_RANGES)


def _reject_old_quality_result_fields(result: Mapping[str, JsonValue]) -> None:
    """拒绝旧 compact quality result 字段。

    :param result: quality_check_result JSON object。
    :returns: ``None``。
    :raises ValueError: 存在旧字段时抛出。
    """

    for field_name in (
        _FIELD_OLD_ACCEPTED_TOOL_FACT_REFS_RETAINED,
        _FIELD_OLD_RETAINED_EVIDENCE_REFS,
    ):
        if field_name in result:
            raise ValueError("old quality result field is not supported")


def _require_non_empty_text_value(value: JsonValue, field_name: str) -> str:
    """校验 JSON 值是非空文本。

    :param value: JSON 值。
    :param field_name: 字段名。
    :returns: 非空文本。
    :raises ValueError: 值不是非空文本时抛出。
    """

    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty text")
    return value


__all__ = [
    "CONTEXT_COMPACTED",
    "CONTEXT_COMPACTION_ATTEMPT_REJECTED",
    "CONTEXT_COMPACTION_FAILED",
    "CONTEXT_COMPACTION_REQUESTED",
    "build_context_compaction_attempt_rejected_payload",
    "build_context_compacted_payload",
    "build_context_compaction_failed_payload",
    "build_context_compaction_requested_payload",
    "validate_context_compaction_attempt_rejected_payload",
    "validate_context_compacted_payload",
    "validate_context_compaction_failed_payload",
    "validate_context_compaction_requested_payload",
]
