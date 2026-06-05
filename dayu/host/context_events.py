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
    CompactQualityCheckResultVNext,
    ConversationCompactOutputVNext,
)
from dayu.host.context_budget import ContextBudgetDecision
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.codec import is_sha256_digest, sha256_digest_json

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
_FIELD_FROZEN_MATERIAL_LIST_DIGEST = "frozen_material_list_digest"
_FIELD_FROZEN_MATERIAL_REFS = "frozen_material_refs"
_FIELD_COMPACT_ARTIFACT_REF = "compact_artifact_ref"
_FIELD_COMPACT_ARTIFACT_DIGEST = "compact_artifact_digest"
_FIELD_ACCEPTED_ATTEMPT_NUMBER = "accepted_attempt_number"
_FIELD_ACCEPTED_CANDIDATE_DIGEST = "accepted_candidate_digest"
_FIELD_ACCEPTED_CANDIDATE = "accepted_candidate"
_FIELD_PROMPT_LOCAL_LABEL_MAPPING_REFS = "prompt_local_label_mapping_refs"
_FIELD_SOURCE_BOUNDARY_REFS = "source_boundary_refs"
_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS = "accepted_evidence_mapping_refs"
_FIELD_PROJECTION_SIGNAL = "projection_signal"
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
_FIELD_ATTEMPT_COUNT = "attempt_count"
_FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED = "retry_repair_budget_exhausted"
_FIELD_DIAGNOSTIC_REFS = "diagnostic_refs"
_FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT = "budget_after_attempted_compact"
_FIELD_FALLBACK_POLICY_DECISION = "fallback_policy_decision"
_FIELD_FALLBACK_INPUT_WINDOW = "fallback_input_window"
_FIELD_FALLBACK_INPUT_DIGEST = "fallback_input_digest"
_FIELD_FALLBACK_BUDGET_RESULT = "fallback_budget_result"
_FIELD_FALLBACK_ACTION = "fallback_action"
_FIELD_ACCEPTED = "accepted"
_FIELD_REJECTION_REASONS = "rejection_reasons"

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
    _FIELD_OPERATION_ID,
    _FIELD_ACCEPTED_ATTEMPT_NUMBER,
    _FIELD_ACCEPTED_CANDIDATE_DIGEST,
    _FIELD_COMPACT_ARTIFACT_REF,
    _FIELD_COMPACT_ARTIFACT_DIGEST,
    _FIELD_ACCEPTED_CANDIDATE,
    _FIELD_PROMPT_LOCAL_LABEL_MAPPING_REFS,
    _FIELD_SOURCE_BOUNDARY_REFS,
    _FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS,
    _FIELD_QUALITY_CHECK_RESULT,
    _FIELD_BUDGET_AFTER_COMPACT,
    _FIELD_PROJECTION_SIGNAL,
)
_COMPACTED_OLD_FIELDS = frozenset(
    (
        _FIELD_EPISODE_SUMMARY_CANDIDATE,
        _FIELD_PINNED_STATE_PATCH_CANDIDATE,
        _FIELD_PRESERVATION_EVIDENCE,
        _FIELD_EVIDENCE_BACKED_FACT_CANDIDATES,
        _FIELD_MINIMUM_PRESERVE_ITEM_CANDIDATES,
        _FIELD_PRESERVED_FACT_REFS,
        _FIELD_DROPPED_RANGES,
        _FIELD_SUMMARIZED_RANGES,
        _FIELD_EVIDENCE_ANCHORS_RETAINED,
    )
)
_FAILED_REQUIRED_FIELDS = (
    _FIELD_OPERATION_ID,
    _FIELD_FAILURE_REASON,
    _FIELD_POLICY_DECISION,
    _FIELD_RETRYABLE,
    _FIELD_ATTEMPT_COUNT,
    _FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED,
    _FIELD_DIAGNOSTIC_REFS,
    _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT,
    _FIELD_FALLBACK_POLICY_DECISION,
    _FIELD_FALLBACK_INPUT_WINDOW,
    _FIELD_FALLBACK_INPUT_DIGEST,
    _FIELD_FALLBACK_BUDGET_RESULT,
    _FIELD_FALLBACK_ACTION,
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
_FALLBACK_ACTION_DISPATCH = "dispatch"
_FALLBACK_ACTION_FAIL_CLOSED = "fail_closed"
_FALLBACK_ACTION_NOT_APPLICABLE = "not_applicable"
_FALLBACK_ACTIONS = frozenset(
    (
        _FALLBACK_ACTION_DISPATCH,
        _FALLBACK_ACTION_FAIL_CLOSED,
        _FALLBACK_ACTION_NOT_APPLICABLE,
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
    frozen_material_list_digest: str | None = None,
    frozen_material_refs: tuple[str, ...] = (),
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
    :param frozen_material_list_digest: reactive overflow material list digest。
    :param frozen_material_refs: reactive overflow material source refs。
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
        _FIELD_FROZEN_MATERIAL_LIST_DIGEST: frozen_material_list_digest,
        _FIELD_FROZEN_MATERIAL_REFS: _string_list_json(frozen_material_refs),
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
    frozen_digest = _optional_text(payload, _FIELD_FROZEN_MATERIAL_LIST_DIGEST)
    if frozen_digest is not None and not is_sha256_digest(frozen_digest):
        raise ValueError("frozen_material_list_digest must be sha256 digest")
    _optional_text_list(payload, _FIELD_FROZEN_MATERIAL_REFS)
    attempt_id = _optional_text(payload, _FIELD_ATTEMPT_ID)
    execution_id = _optional_text(payload, _FIELD_EXECUTION_ID)
    if trigger_source is ContextCompactionTriggerSource.REACTIVE:
        if attempt_id is None or execution_id is None:
            raise ValueError("reactive compaction requires attempt_id and execution_id")


def build_context_compacted_payload(
    *,
    operation_id: str,
    accepted_attempt_number: int,
    compact_artifact_ref: str,
    compact_artifact_digest: str,
    accepted_candidate: ConversationCompactOutputVNext,
    quality_check_result: CompactQualityCheckResultVNext,
    budget_after_compact: int,
    prompt_local_label_mapping_refs: tuple[str, ...],
    source_boundary_refs: tuple[str, ...],
    accepted_evidence_mapping_refs: tuple[str, ...],
    projection_signal: str,
) -> Mapping[str, JsonValue]:
    """构造 ``CONTEXT_COMPACTED`` payload。

    :param operation_id: compact operation id。
    :param accepted_attempt_number: 被接受的 operation attempt number。
    :param compact_artifact_ref: compact artifact payload / artifact ref。
    :param compact_artifact_digest: compact artifact digest。
    :param accepted_candidate: 通过 quality check 的 vNext compact output。
    :param quality_check_result: accepted vNext quality check 结果。
    :param budget_after_compact: Host 估算的 compact 后预算。
    :param prompt_local_label_mapping_refs: prompt-local label mapping refs。
    :param source_boundary_refs: source boundary refs。
    :param accepted_evidence_mapping_refs: accepted evidence mapping refs。
    :param projection_signal: memory projection signal。
    :returns: 可写入 EventLog 的 JSON payload。
    :raises TypeError: 输入类型非法时抛出。
    :raises ValueError: payload 结构非法时抛出。
    """

    if not isinstance(accepted_candidate, ConversationCompactOutputVNext):
        raise TypeError("accepted_candidate must be ConversationCompactOutputVNext")
    if not isinstance(quality_check_result, CompactQualityCheckResultVNext):
        raise TypeError("quality_check_result must be CompactQualityCheckResultVNext")
    payload: Mapping[str, JsonValue] = {
        _FIELD_OPERATION_ID: operation_id,
        _FIELD_ACCEPTED_ATTEMPT_NUMBER: accepted_attempt_number,
        _FIELD_ACCEPTED_CANDIDATE_DIGEST: accepted_candidate.digest(),
        _FIELD_COMPACT_ARTIFACT_REF: compact_artifact_ref,
        _FIELD_COMPACT_ARTIFACT_DIGEST: compact_artifact_digest,
        _FIELD_ACCEPTED_CANDIDATE: accepted_candidate.to_json(),
        _FIELD_PROMPT_LOCAL_LABEL_MAPPING_REFS: _string_list_json(
            prompt_local_label_mapping_refs
        ),
        _FIELD_SOURCE_BOUNDARY_REFS: _string_list_json(source_boundary_refs),
        _FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS: _string_list_json(
            accepted_evidence_mapping_refs
        ),
        _FIELD_QUALITY_CHECK_RESULT: quality_check_result.to_json(),
        _FIELD_BUDGET_AFTER_COMPACT: budget_after_compact,
        _FIELD_PROJECTION_SIGNAL: projection_signal,
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

    _reject_old_compacted_fields(payload)
    _require_fields(payload, _COMPACTED_REQUIRED_FIELDS)
    _required_text(payload, _FIELD_OPERATION_ID)
    _required_positive_int(payload, _FIELD_ACCEPTED_ATTEMPT_NUMBER)
    _required_digest(payload, _FIELD_ACCEPTED_CANDIDATE_DIGEST)
    _required_text(payload, _FIELD_COMPACT_ARTIFACT_REF)
    _required_digest(payload, _FIELD_COMPACT_ARTIFACT_DIGEST)
    candidate = _required_mapping(payload, _FIELD_ACCEPTED_CANDIDATE)
    if _required_text(candidate, "schema_version") != "conversation_compact_output_v1":
        raise ValueError("accepted_candidate schema_version is invalid")
    if _required_text(payload, _FIELD_ACCEPTED_CANDIDATE_DIGEST) != sha256_digest_json(candidate):
        raise ValueError("accepted_candidate_digest mismatch")
    _validate_vnext_candidate_payload(candidate)
    _required_text_list(payload, _FIELD_PROMPT_LOCAL_LABEL_MAPPING_REFS)
    _required_text_list(payload, _FIELD_SOURCE_BOUNDARY_REFS)
    _required_text_list(payload, _FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS)
    _validate_quality_check_result_vnext(payload)
    _required_non_negative_int(payload, _FIELD_BUDGET_AFTER_COMPACT)
    _required_text(payload, _FIELD_PROJECTION_SIGNAL)


def build_context_compaction_failed_payload(
    *,
    operation_id: str,
    failure_reason: str,
    policy_decision: ContextBudgetDecision | str,
    retryable: bool,
    attempt_count: int,
    retry_repair_budget_exhausted: bool,
    diagnostic_refs: tuple[str, ...],
    budget_after_attempted_compact: int | None,
    fallback_policy_decision: str | None = None,
    fallback_input_window: Mapping[str, JsonValue] | None = None,
    fallback_input_digest: str | None = None,
    fallback_budget_result: Mapping[str, JsonValue] | None = None,
    fallback_action: str = _FALLBACK_ACTION_NOT_APPLICABLE,
) -> Mapping[str, JsonValue]:
    """构造 ``CONTEXT_COMPACTION_FAILED`` payload。

    :param operation_id: compact operation 诊断 id；通常为 request fact event id。
    :param failure_reason: compact 失败原因。
    :param policy_decision: compact 失败后的 policy decision。
    :param retryable: 当前失败是否可重试。
    :param attempt_count: operation 内已拒绝 proposal attempt 数。
    :param retry_repair_budget_exhausted: semantic retry / repair 预算是否耗尽。
    :param diagnostic_refs: 诊断 ref 列表。
    :param budget_after_attempted_compact: compact 尝试后的预算估算；未知时为
        ``None``。
    :param fallback_policy_decision: fallback policy decision；不适用时为
        ``None``。
    :param fallback_input_window: fallback 输入窗口结构化诊断；不适用时为
        ``None``。
    :param fallback_input_digest: fallback 输入窗口 digest；不适用时为
        ``None``。
    :param fallback_budget_result: fallback 预算重估结果；不适用时为
        ``None``。
    :param fallback_action: fallback 动作。
    :returns: 可写入 EventLog 的 JSON payload。
    :raises TypeError: 字段类型非法时抛出。
    :raises ValueError: 字段值非法时抛出。
    """

    if isinstance(policy_decision, ContextBudgetDecision):
        policy_decision_value = policy_decision.value
    else:
        policy_decision_value = policy_decision
    payload: Mapping[str, JsonValue] = {
        _FIELD_OPERATION_ID: operation_id,
        _FIELD_FAILURE_REASON: failure_reason,
        _FIELD_POLICY_DECISION: policy_decision_value,
        _FIELD_RETRYABLE: retryable,
        _FIELD_ATTEMPT_COUNT: attempt_count,
        _FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED: retry_repair_budget_exhausted,
        _FIELD_DIAGNOSTIC_REFS: _string_list_json(diagnostic_refs),
        _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT: budget_after_attempted_compact,
        _FIELD_FALLBACK_POLICY_DECISION: fallback_policy_decision,
        _FIELD_FALLBACK_INPUT_WINDOW: fallback_input_window,
        _FIELD_FALLBACK_INPUT_DIGEST: fallback_input_digest,
        _FIELD_FALLBACK_BUDGET_RESULT: fallback_budget_result,
        _FIELD_FALLBACK_ACTION: fallback_action,
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
    _required_text(payload, _FIELD_OPERATION_ID)
    _required_text(payload, _FIELD_FAILURE_REASON)
    _required_text(payload, _FIELD_POLICY_DECISION)
    _required_bool(payload, _FIELD_RETRYABLE)
    _required_non_negative_int(payload, _FIELD_ATTEMPT_COUNT)
    _required_bool(payload, _FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED)
    _required_text_list(payload, _FIELD_DIAGNOSTIC_REFS)
    _optional_non_negative_int(payload, _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT)
    fallback_action = _required_text(payload, _FIELD_FALLBACK_ACTION)
    if fallback_action not in _FALLBACK_ACTIONS:
        raise ValueError("fallback_action must be dispatch, fail_closed or not_applicable")
    _validate_failed_fallback_fields(payload, fallback_action=fallback_action)


def _validate_failed_fallback_fields(
    payload: Mapping[str, JsonValue], *, fallback_action: str
) -> None:
    """校验 failed payload 的 fallback 诊断字段一致性。

    :param payload: 待校验 JSON payload。
    :param fallback_action: 已校验为非空文本的 fallback action。
    :returns: ``None``。
    :raises ValueError: fallback 字段组合非法时抛出。
    """

    if fallback_action == _FALLBACK_ACTION_NOT_APPLICABLE:
        for field_name in (
            _FIELD_FALLBACK_POLICY_DECISION,
            _FIELD_FALLBACK_INPUT_WINDOW,
            _FIELD_FALLBACK_INPUT_DIGEST,
            _FIELD_FALLBACK_BUDGET_RESULT,
        ):
            if payload[field_name] is not None:
                raise ValueError(f"{field_name} must be null when fallback is not applicable")
        return
    _required_text(payload, _FIELD_FALLBACK_POLICY_DECISION)
    _required_mapping(payload, _FIELD_FALLBACK_INPUT_WINDOW)
    _required_text(payload, _FIELD_FALLBACK_INPUT_DIGEST)
    _required_mapping(payload, _FIELD_FALLBACK_BUDGET_RESULT)


def _reject_old_compacted_fields(payload: Mapping[str, JsonValue]) -> None:
    """拒绝旧 ``CONTEXT_COMPACTED`` 字段。

    :param payload: compacted payload。
    :returns: ``None``。
    :raises ValueError: payload 包含旧字段时抛出。
    """

    for field_name in _COMPACTED_OLD_FIELDS:
        if field_name in payload:
            raise ValueError(f"{field_name} is not supported in vNext compacted payload")


def _validate_vnext_candidate_payload(candidate: Mapping[str, JsonValue]) -> None:
    """校验 vNext accepted candidate payload 基础形状。

    :param candidate: ``accepted_candidate`` JSON object。
    :returns: ``None``。
    :raises ValueError: candidate 缺少 vNext 字段或字段类型非法时抛出。
    """

    session_summary = candidate.get("session_summary")
    if session_summary is not None:
        summary = _required_mapping(candidate, "session_summary")
        _required_text(summary, "summary_text")
        _required_text_list(summary, "source_labels")
    _validate_mapping_list(candidate, "evidence_backed_facts")
    _validate_mapping_list(candidate, "answer_anchors")
    _validate_mapping_list(candidate, "forward_intents")
    _validate_mapping_list(candidate, "reference_continuity_items")
    _validate_mapping_list(candidate, "diagnostics")


def _validate_mapping_list(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[Mapping[str, JsonValue], ...]:
    """校验必填 JSON object list 字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: JSON object tuple。
    :raises ValueError: 字段缺失或元素类型非法时抛出。
    """

    return _required_mapping_list(payload, field_name)


def _validate_quality_check_result_vnext(payload: Mapping[str, JsonValue]) -> None:
    """校验 vNext quality check result。

    :param payload: compacted payload。
    :returns: ``None``。
    :raises ValueError: quality result 不是 accepted vNext result 时抛出。
    """

    result = _required_mapping(payload, _FIELD_QUALITY_CHECK_RESULT)
    if not _required_bool(result, _FIELD_ACCEPTED):
        raise ValueError("compacted payload requires accepted quality result")
    reasons = _required_text_list(result, _FIELD_REJECTION_REASONS)
    if len(reasons) > 0:
        raise ValueError("accepted quality result must not include rejection reasons")


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
