"""Host 内部 context compaction operation helper。

本模块只执行事务外 compaction proposal attempt 循环、质量校验与 proactive
预算硬阈值校验。reactive path 不把估算值当作是否可重新 dispatch 的真源；
EventLog 写入、artifact 写入、memory projection 与 durable state recheck 仍由
调用方所在的 Host governance 路径负责。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from dayu.contracts.cancellation import CancellationToken
from dayu.host.compaction import (
    CompactInputRange,
    CompactQualityCheckResult,
    CompactionCandidate,
    CompactionRequest,
    ContextCompactor,
    EpisodeSummaryCandidate,
    EvidenceBackedFactCandidate,
    MinimumPreserveItemCandidate,
    PinnedPatchOperation,
    PinnedStatePatchCandidate,
    PinnedStringTupleFieldPatch,
    PinnedTextFieldPatch,
    PreservationEvidence,
)
from dayu.host.context_governance import check_compaction_candidate
from dayu.host.context_policy import ContextCompactionTriggerSource

_FAILURE_PROPOSAL_FAILED = "proposal_failed"
_FAILURE_QUALITY_CHECK_REJECTED = "quality_check_rejected"
_FAILURE_HARD_THRESHOLD_AFTER_COMPACT = "hard_threshold_after_compact"
_FAILURE_MAX_ATTEMPTS_EXHAUSTED = "max_compaction_attempts_exhausted"
_FAILURE_CANCELLATION_REQUESTED = "cancellation_requested"
_NEXT_DECISION_RETRY_REPAIR = "retry_semantic_repair"
_NEXT_DECISION_FAIL_COMPACTION = "fail_compaction"
_DIAGNOSTIC_SUFFIX_UNKNOWN = "unknown"
_DIAGNOSTIC_SUFFIX_CANCELLED = "cancelled"
_DIAGNOSTIC_SUFFIX_HARD_THRESHOLD = "hard_threshold"
_MAX_SAFE_EXCEPTION_MESSAGE_CHARS = 240
_TRUNCATED_SUFFIX = "..."
_REDACTED_SECRET = "<redacted>"
_BEARER_SECRET_PATTERN = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")
_ASSIGNMENT_SECRET_PATTERN = re.compile(r"(?i)((?:api[_-]?key|authorization|token|secret)\s*[:=]\s*)[^,\s}\]]+")
_ERROR_CODE_PATTERN = re.compile(r"\berror_code=([A-Za-z0-9_-]+)")
_LOGGER = logging.getLogger(__name__)
_MERGED_CANDIDATE_PREFIX = "merged:"
_MERGED_SUMMARY_CANDIDATE_PREFIX = "merged-summary:"
_MERGED_PINNED_PATCH_CANDIDATE_PREFIX = "merged-pinned-patch:"
_MERGED_TEXT_SEPARATOR = "\n\n"
_MERGED_TITLE_SEPARATOR = " / "


@dataclass(frozen=True, slots=True)
class CompactionAttemptRejected:
    """compaction semantic attempt reject 摘要。

    :param attempt_number: operation 内 proposal attempt 序号。
    :param failure_category: 失败类别。
    :param repairable: 是否可继续 repair attempt。
    :param runner_attempt_summary_refs: runner attempt 摘要 ref。
    :param diagnostic_refs: quality / parse / budget 诊断 ref。
    :param next_policy_decision: 下一步 policy decision。
    :param budget_after_attempted_compact: attempt 后预算；未知时为 ``None``。
    """

    attempt_number: int
    failure_category: str
    repairable: bool
    runner_attempt_summary_refs: tuple[str, ...]
    diagnostic_refs: tuple[str, ...]
    next_policy_decision: str
    budget_after_attempted_compact: int | None


@dataclass(frozen=True, slots=True)
class CompactionOperationResult:
    """事务外 compaction operation 结果。

    :param accepted_candidate: 被 Host 接受的 candidate；失败时为 ``None``。
    :param quality_result: accepted candidate 对应 quality result。
    :param rejected_attempts: semantic attempt reject 诊断列表。
    :param failure_reason: 最终失败原因；成功时为 ``None``。
    :param budget_after_attempted_compact: 最后一次 attempt 后预算；未知时为
        ``None``。
    """

    accepted_candidate: CompactionCandidate | None
    quality_result: CompactQualityCheckResult | None
    rejected_attempts: tuple[CompactionAttemptRejected, ...]
    failure_reason: str | None
    budget_after_attempted_compact: int | None


async def run_compaction_operation(
    *,
    request: CompactionRequest,
    compactor: ContextCompactor,
    max_attempts: int,
    cancellation_token: CancellationToken,
    pass_queue: tuple[CompactionRequest, ...] = (),
) -> CompactionOperationResult:
    """在事务外执行 Host semantic compaction operation。

    :param request: Host compaction request。
    :param compactor: Host internal compactor seam。
    :param max_attempts: proposal attempt 上限。
    :param cancellation_token: Host 注入 compactor 的真实取消 token。
    :param pass_queue: 同一 operation 内的 pass request 队列；为空时使用
        ``request`` 作为单 pass。
    :returns: compaction operation 结果。
    """

    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    requests = _operation_pass_requests(request=request, pass_queue=pass_queue)
    rejected: list[CompactionAttemptRejected] = []
    accepted_candidates: list[CompactionCandidate] = []
    last_budget: int | None = None
    attempt_number = 1
    for pass_request in requests:
        pass_accepted = False
        while attempt_number <= max_attempts and not pass_accepted:
            if cancellation_token.is_cancelled():
                rejected_attempt = _attempt_rejected(
                    request=pass_request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_CANCELLATION_REQUESTED,
                    repairable=False,
                    next_policy_decision=_NEXT_DECISION_FAIL_COMPACTION,
                    budget_after_attempted_compact=last_budget,
                    diagnostic_suffix=_cancellation_suffix(cancellation_token),
                )
                rejected.append(rejected_attempt)
                _log_rejected_attempt(
                    request=pass_request,
                    rejected=rejected_attempt,
                    exception=None,
                )
                return CompactionOperationResult(
                    accepted_candidate=None,
                    quality_result=None,
                    rejected_attempts=tuple(rejected),
                    failure_reason=_FAILURE_CANCELLATION_REQUESTED,
                    budget_after_attempted_compact=last_budget,
                )
            repairable = attempt_number < max_attempts
            next_decision = _NEXT_DECISION_RETRY_REPAIR if repairable else _NEXT_DECISION_FAIL_COMPACTION
            try:
                candidate = await compactor.compact(pass_request, cancellation_token)
            except Exception as exc:
                rejected_attempt = _attempt_rejected(
                    request=pass_request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_PROPOSAL_FAILED,
                    repairable=repairable,
                    next_policy_decision=next_decision,
                    budget_after_attempted_compact=None,
                    diagnostic_suffix=_exception_diagnostic_suffix(exc),
                )
                rejected.append(rejected_attempt)
                _log_rejected_attempt(
                    request=pass_request,
                    rejected=rejected_attempt,
                    exception=exc,
                )
                if not repairable:
                    return CompactionOperationResult(
                        accepted_candidate=None,
                        quality_result=None,
                        rejected_attempts=tuple(rejected),
                        failure_reason=_FAILURE_PROPOSAL_FAILED,
                        budget_after_attempted_compact=None,
                    )
                attempt_number += 1
                continue
            quality = check_compaction_candidate(pass_request, candidate)
            last_budget = candidate.budget_after_compact
            if not quality.accepted:
                rejected_attempt = _attempt_rejected(
                    request=pass_request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_QUALITY_CHECK_REJECTED,
                    repairable=repairable,
                    next_policy_decision=next_decision,
                    budget_after_attempted_compact=candidate.budget_after_compact,
                    diagnostic_suffix=_quality_suffix(quality),
                )
                rejected.append(rejected_attempt)
                _log_rejected_attempt(
                    request=pass_request,
                    rejected=rejected_attempt,
                    exception=None,
                )
                if not repairable:
                    return CompactionOperationResult(
                        accepted_candidate=None,
                        quality_result=None,
                        rejected_attempts=tuple(rejected),
                        failure_reason=_FAILURE_QUALITY_CHECK_REJECTED,
                        budget_after_attempted_compact=candidate.budget_after_compact,
                    )
                attempt_number += 1
                continue
            if _requires_budget_acceptance(pass_request) and (
                candidate.budget_after_compact >= pass_request.budget_before_compact.hard_threshold_tokens
            ):
                rejected_attempt = _attempt_rejected(
                    request=pass_request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_HARD_THRESHOLD_AFTER_COMPACT,
                    repairable=repairable,
                    next_policy_decision=next_decision,
                    budget_after_attempted_compact=candidate.budget_after_compact,
                    diagnostic_suffix=_DIAGNOSTIC_SUFFIX_HARD_THRESHOLD,
                )
                rejected.append(rejected_attempt)
                _log_rejected_attempt(
                    request=pass_request,
                    rejected=rejected_attempt,
                    exception=None,
                )
                if not repairable:
                    return CompactionOperationResult(
                        accepted_candidate=None,
                        quality_result=None,
                        rejected_attempts=tuple(rejected),
                        failure_reason=_FAILURE_HARD_THRESHOLD_AFTER_COMPACT,
                        budget_after_attempted_compact=candidate.budget_after_compact,
                    )
                attempt_number += 1
                continue
            accepted_candidates.append(candidate)
            pass_accepted = True
            attempt_number += 1
        if not pass_accepted:
            return CompactionOperationResult(
                accepted_candidate=None,
                quality_result=None,
                rejected_attempts=tuple(rejected),
                failure_reason=_FAILURE_MAX_ATTEMPTS_EXHAUSTED,
                budget_after_attempted_compact=last_budget,
            )
    merged_candidate = _merge_pass_candidates(request, tuple(accepted_candidates))
    merged_quality = check_compaction_candidate(request, merged_candidate)
    if not merged_quality.accepted:
        rejected.append(
            _attempt_rejected(
                request=request,
                attempt_number=attempt_number,
                failure_category=_FAILURE_QUALITY_CHECK_REJECTED,
                repairable=False,
                next_policy_decision=_NEXT_DECISION_FAIL_COMPACTION,
                budget_after_attempted_compact=merged_candidate.budget_after_compact,
                diagnostic_suffix=_DIAGNOSTIC_SUFFIX_UNKNOWN,
            )
        )
        return CompactionOperationResult(
            accepted_candidate=None,
            quality_result=None,
            rejected_attempts=tuple(rejected),
            failure_reason=_FAILURE_QUALITY_CHECK_REJECTED,
            budget_after_attempted_compact=merged_candidate.budget_after_compact,
        )
    if _requires_budget_acceptance(request) and (
        merged_candidate.budget_after_compact >= request.budget_before_compact.hard_threshold_tokens
    ):
        return CompactionOperationResult(
            accepted_candidate=None,
            quality_result=None,
            rejected_attempts=tuple(rejected),
            failure_reason=_FAILURE_HARD_THRESHOLD_AFTER_COMPACT,
            budget_after_attempted_compact=merged_candidate.budget_after_compact,
        )
    return CompactionOperationResult(
        accepted_candidate=merged_candidate,
        quality_result=merged_quality,
        rejected_attempts=tuple(rejected),
        failure_reason=None,
        budget_after_attempted_compact=merged_candidate.budget_after_compact,
    )


def _operation_pass_requests(
    *, request: CompactionRequest, pass_queue: tuple[CompactionRequest, ...]
) -> tuple[CompactionRequest, ...]:
    """返回 operation 实际 pass request 队列。

    :param request: operation root request。
    :param pass_queue: 调用方提供的 pass request 队列。
    :returns: 非空 pass request tuple。
    :raises TypeError: 队列元素类型非法时抛出。
    :raises ValueError: pass queue 与 root operation identity 不一致时抛出。
    """

    if len(pass_queue) == 0:
        return (request,)
    for pass_request in pass_queue:
        if not isinstance(pass_request, CompactionRequest):
            raise TypeError("pass_queue items must be CompactionRequest")
        if (
            pass_request.trigger_source is not request.trigger_source
            or pass_request.session_id != request.session_id
            or pass_request.run_id != request.run_id
            or pass_request.attempt_id != request.attempt_id
            or pass_request.execution_id != request.execution_id
        ):
            raise ValueError("pass_queue request identity must match root request")
    return pass_queue


def _merge_pass_candidates(
    request: CompactionRequest,
    candidates: tuple[CompactionCandidate, ...],
) -> CompactionCandidate:
    """合并同一 operation 内所有 pass candidate。

    :param request: operation root request。
    :param candidates: 已通过各 pass quality gate 的 candidate。
    :returns: 单个可写入 ``CONTEXT_COMPACTED`` 的 merged candidate。
    :raises ValueError: candidates 为空时抛出。
    """

    if len(candidates) == 0:
        raise ValueError("candidates must be non-empty")
    if len(candidates) == 1:
        return candidates[0]
    candidate_digest = request.digest().removeprefix("sha256:")
    candidate_id = _MERGED_CANDIDATE_PREFIX + candidate_digest
    return CompactionCandidate(
        candidate_id=candidate_id,
        episode_summary_candidate=_merge_episode_summary_candidate(candidate_digest, candidates),
        pinned_state_patch_candidate=_merge_pinned_state_patch_candidate(candidate_digest, candidates),
        preservation_evidence=_dedupe_preservation_evidence(candidates),
        evidence_backed_fact_candidates=_dedupe_fact_candidates(candidates),
        minimum_preserve_item_candidates=_dedupe_minimum_preserve_items(candidates),
        retained_current_user_input_ref=request.current_input_ref,
        preserved_material_source_refs=request.material_source_refs,
        preserved_canonical_evidence_refs=_dedupe_strings(
            tuple(candidate.preserved_canonical_evidence_refs for candidate in candidates)
        ),
        preserved_evidence_backed_fact_refs=_dedupe_strings(
            tuple(candidate.preserved_evidence_backed_fact_refs for candidate in candidates)
        ),
        dropped_ranges=_dedupe_ranges(tuple(item for candidate in candidates for item in candidate.dropped_ranges)),
        summarized_ranges=_dedupe_ranges(
            tuple(item for candidate in candidates for item in candidate.summarized_ranges)
        ),
        budget_after_compact=min(candidate.budget_after_compact for candidate in candidates),
    )


def _merge_episode_summary_candidate(
    candidate_digest: str, candidates: tuple[CompactionCandidate, ...]
) -> EpisodeSummaryCandidate:
    """合并 multi-pass episode summary candidate。

    :param candidate_digest: root request digest 派生的 merged candidate digest。
    :param candidates: pass candidates。
    :returns: 覆盖所有 pass 的 summary candidate。
    """

    summaries = tuple(candidate.episode_summary_candidate for candidate in candidates)
    return EpisodeSummaryCandidate(
        candidate_id=_MERGED_SUMMARY_CANDIDATE_PREFIX + candidate_digest,
        episode_title=_merge_required_text(
            tuple(summary.episode_title for summary in summaries),
            separator=_MERGED_TITLE_SEPARATOR,
        ),
        goal=_merge_required_text(
            tuple(summary.goal for summary in summaries),
            separator=_MERGED_TEXT_SEPARATOR,
        ),
        completed_actions=_dedupe_strings(tuple(summary.completed_actions for summary in summaries)),
        confirmed_fact_refs=_dedupe_strings(tuple(summary.confirmed_fact_refs for summary in summaries)),
        confirmed_fact_summaries=_dedupe_strings(tuple(summary.confirmed_fact_summaries for summary in summaries)),
        user_constraints=_dedupe_strings(tuple(summary.user_constraints for summary in summaries)),
        open_questions=_dedupe_strings(tuple(summary.open_questions for summary in summaries)),
        next_step=_merge_optional_text(
            tuple(summary.next_step for summary in summaries),
            separator=_MERGED_TEXT_SEPARATOR,
        ),
        tool_finding_refs=_dedupe_strings(tuple(summary.tool_finding_refs for summary in summaries)),
        source_event_refs=_dedupe_strings(tuple(summary.source_event_refs for summary in summaries)),
        evidence_refs=_dedupe_strings(tuple(summary.evidence_refs for summary in summaries)),
        proposed_evidence_backed_fact_refs=_dedupe_strings(
            tuple(summary.proposed_evidence_backed_fact_refs for summary in summaries)
        ),
    )


def _merge_pinned_state_patch_candidate(
    candidate_digest: str, candidates: tuple[CompactionCandidate, ...]
) -> PinnedStatePatchCandidate:
    """合并 multi-pass pinned state patch candidate。

    :param candidate_digest: root request digest 派生的 merged candidate digest。
    :param candidates: pass candidates。
    :returns: 覆盖所有 pass 的 pinned state patch candidate。
    """

    patches = tuple(candidate.pinned_state_patch_candidate for candidate in candidates)
    return PinnedStatePatchCandidate(
        candidate_id=_MERGED_PINNED_PATCH_CANDIDATE_PREFIX + candidate_digest,
        current_goal=_merge_text_field_patch(tuple(patch.current_goal for patch in patches)),
        confirmed_subjects=_merge_tuple_field_patch(tuple(patch.confirmed_subjects for patch in patches)),
        user_constraints=_merge_tuple_field_patch(tuple(patch.user_constraints for patch in patches)),
        open_questions=_merge_tuple_field_patch(tuple(patch.open_questions for patch in patches)),
    )


def _merge_text_field_patch(patches: tuple[PinnedTextFieldPatch, ...]) -> PinnedTextFieldPatch:
    """合并文本 pinned patch 字段。

    文本字段是 scalar value，无法无损拼接为一个 pinned state 值；因此按 pass
    顺序采用最后一个非 missing patch，保持 deterministic last-writer-wins。

    :param patches: pass 文本字段 patch。
    :returns: merged 文本字段 patch。
    """

    selected = PinnedTextFieldPatch(operation=PinnedPatchOperation.MISSING)
    for patch in patches:
        if patch.operation is PinnedPatchOperation.MISSING:
            continue
        selected = patch
    return selected


def _merge_tuple_field_patch(patches: tuple[PinnedStringTupleFieldPatch, ...]) -> PinnedStringTupleFieldPatch:
    """合并字符串 tuple pinned patch 字段。

    :param patches: pass tuple 字段 patch。
    :returns: merged tuple 字段 patch。
    """

    operation = PinnedPatchOperation.MISSING
    values: list[str] = []
    evidence_refs: list[str] = []
    for patch in patches:
        if patch.operation is PinnedPatchOperation.MISSING:
            continue
        if patch.operation is PinnedPatchOperation.CLEAR:
            operation = PinnedPatchOperation.CLEAR
            values = []
            evidence_refs = list(patch.evidence_refs)
            continue
        if patch.operation is PinnedPatchOperation.REPLACE:
            if operation is not PinnedPatchOperation.REPLACE:
                values = []
                evidence_refs = []
            operation = PinnedPatchOperation.REPLACE
            if patch.value is not None:
                values.extend(patch.value)
            evidence_refs.extend(patch.evidence_refs)
    if operation is PinnedPatchOperation.MISSING:
        return PinnedStringTupleFieldPatch(operation=PinnedPatchOperation.MISSING)
    if operation is PinnedPatchOperation.CLEAR:
        return PinnedStringTupleFieldPatch(
            operation=PinnedPatchOperation.CLEAR,
            evidence_refs=tuple(dict.fromkeys(evidence_refs)),
        )
    return PinnedStringTupleFieldPatch(
        operation=PinnedPatchOperation.REPLACE,
        value=tuple(dict.fromkeys(values)),
        evidence_refs=tuple(dict.fromkeys(evidence_refs)),
    )


def _merge_required_text(values: tuple[str, ...], *, separator: str) -> str:
    """合并非空文本字段。

    :param values: pass 文本值。
    :param separator: 多个不同文本之间的分隔符。
    :returns: merged 文本。
    :raises ValueError: 输入为空时抛出。
    """

    merged = tuple(dict.fromkeys(values))
    if len(merged) == 0:
        raise ValueError("values must be non-empty")
    return separator.join(merged)


def _merge_optional_text(values: tuple[str | None, ...], *, separator: str) -> str | None:
    """合并可选文本字段。

    :param values: pass 可选文本值。
    :param separator: 多个不同文本之间的分隔符。
    :returns: merged 文本；所有 pass 均为空时返回 ``None``。
    """

    non_empty = tuple(value for value in values if value is not None)
    if len(non_empty) == 0:
        return None
    return _merge_required_text(non_empty, separator=separator)


def _dedupe_strings(values: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    """按 pass 顺序去重字符串 tuple。

    :param values: pass 字符串 tuple 集合。
    :returns: 去重后的字符串 tuple。
    """

    merged: list[str] = []
    for items in values:
        merged.extend(items)
    return tuple(dict.fromkeys(merged))


def _dedupe_preservation_evidence(candidates: tuple[CompactionCandidate, ...]) -> tuple[PreservationEvidence, ...]:
    """按 evidence id 去重 preservation evidence。

    :param candidates: pass candidates。
    :returns: preservation evidence tuple。
    """

    values = []
    seen: set[str] = set()
    for candidate in candidates:
        for item in candidate.preservation_evidence:
            if item.evidence_id in seen:
                continue
            seen.add(item.evidence_id)
            values.append(item)
    return tuple(values)


def _dedupe_fact_candidates(candidates: tuple[CompactionCandidate, ...]) -> tuple[EvidenceBackedFactCandidate, ...]:
    """按 candidate id 去重 fact candidates。

    :param candidates: pass candidates。
    :returns: fact candidate tuple。
    """

    values = []
    seen: set[str] = set()
    for candidate in candidates:
        for item in candidate.evidence_backed_fact_candidates:
            if item.candidate_id in seen:
                continue
            seen.add(item.candidate_id)
            values.append(item)
    return tuple(values)


def _dedupe_minimum_preserve_items(
    candidates: tuple[CompactionCandidate, ...],
) -> tuple[MinimumPreserveItemCandidate, ...]:
    """按 item id 去重 minimum preserve items。

    :param candidates: pass candidates。
    :returns: minimum preserve item tuple。
    """

    values = []
    seen: set[str] = set()
    for candidate in candidates:
        for item in candidate.minimum_preserve_item_candidates:
            if item.item_id in seen:
                continue
            seen.add(item.item_id)
            values.append(item)
    return tuple(values)


def _dedupe_ranges(values: tuple[CompactInputRange, ...]) -> tuple[CompactInputRange, ...]:
    """按 range ref 去重 compact input ranges。

    :param values: range tuple。
    :returns: compact input range tuple。
    """

    result = []
    seen: set[str] = set()
    for item in values:
        if item.range_ref in seen:
            continue
        seen.add(item.range_ref)
        result.append(item)
    return tuple(result)


def _requires_budget_acceptance(request: CompactionRequest) -> bool:
    """判断本次 operation 是否需要 compact 后预算估算闸门。

    proactive path 在 dispatch 前使用估算值决定是否创建 Attempt；reactive path
    来自真实 provider overflow，compact 后是否足够应交给后续真实 dispatch /
    Engine event 闭环判断，避免不准估算阻断第二次 reactive compact。

    :param request: Host compaction request。
    :returns: 需要估算闸门时返回 ``True``。
    """

    return request.trigger_source is ContextCompactionTriggerSource.PROACTIVE


def _attempt_rejected(
    *,
    request: CompactionRequest,
    attempt_number: int,
    failure_category: str,
    repairable: bool,
    next_policy_decision: str,
    budget_after_attempted_compact: int | None,
    diagnostic_suffix: str,
) -> CompactionAttemptRejected:
    """构造 attempt reject 摘要。

    :param request: Host compaction request。
    :param attempt_number: proposal attempt 序号。
    :param failure_category: 失败类别。
    :param repairable: 是否可继续 repair attempt。
    :param next_policy_decision: 下一步 policy decision。
    :param budget_after_attempted_compact: attempt 后预算。
    :param diagnostic_suffix: 诊断 ref 后缀。
    :returns: attempt reject 摘要。
    """

    operation_ref = request.digest()
    return CompactionAttemptRejected(
        attempt_number=attempt_number,
        failure_category=failure_category,
        repairable=repairable,
        runner_attempt_summary_refs=(f"runner-attempt:{request.run_id}:{attempt_number}",),
        diagnostic_refs=(f"diagnostic:{failure_category}:{operation_ref}:{diagnostic_suffix}",),
        next_policy_decision=next_policy_decision,
        budget_after_attempted_compact=budget_after_attempted_compact,
    )


def _quality_suffix(quality: CompactQualityCheckResult) -> str:
    """构造 quality reject 诊断后缀。

    :param quality: quality check 结果。
    :returns: 中性诊断后缀。
    """

    if len(quality.rejection_reasons) == 0:
        return _DIAGNOSTIC_SUFFIX_UNKNOWN
    return "-".join(reason.value for reason in quality.rejection_reasons)


def _exception_diagnostic_suffix(exc: Exception) -> str:
    """构造 proposal exception 诊断后缀。

    :param exc: compactor proposal 抛出的异常。
    :returns: 包含异常类型与消息的诊断后缀。
    """

    message = _safe_exception_message(exc)
    if message == exc.__class__.__name__:
        return exc.__class__.__name__
    return f"{exc.__class__.__name__}:{message}"


def _cancellation_suffix(cancellation_token: CancellationToken) -> str:
    """构造取消拒绝诊断后缀。

    :param cancellation_token: Host 注入 compactor 的真实取消 token。
    :returns: 取消原因；token 未提供原因时返回中性取消后缀。
    :raises Exception: 不主动抛出异常。
    """

    reason = cancellation_token.cancel_reason()
    if reason is None or reason.strip() == "":
        return _DIAGNOSTIC_SUFFIX_CANCELLED
    return reason


def _log_rejected_attempt(
    *,
    request: CompactionRequest,
    rejected: CompactionAttemptRejected,
    exception: Exception | None,
) -> None:
    """记录 compaction attempt 拒绝摘要。

    :param request: Host compaction request。
    :param rejected: attempt reject 摘要。
    :param exception: proposal 异常；非异常类拒绝时为 ``None``。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    log_message = (
        "host.compaction_operation.attempt_rejected "
        "session_id=%s run_id=%s trigger_source=%s attempt_number=%s "
        "failure_category=%s repairable=%s error_code=%s message=%s "
        "diagnostic_refs=%s next_policy_decision=%s "
        "budget_after_attempted_compact=%s"
    )
    args = (
        request.session_id,
        request.run_id,
        request.trigger_source.value,
        rejected.attempt_number,
        rejected.failure_category,
        rejected.repairable,
        _exception_error_code(exception),
        _safe_exception_message(exception),
        ",".join(rejected.diagnostic_refs),
        rejected.next_policy_decision,
        rejected.budget_after_attempted_compact,
    )
    if rejected.repairable:
        _LOGGER.warning(log_message, *args)
    else:
        _LOGGER.error(log_message, *args)


def _exception_error_code(exc: Exception | None) -> str:
    """从 proposal 异常中提取可诊断错误码。

    :param exc: proposal 异常；无异常时为 ``None``。
    :returns: 机器可读错误码。
    :raises Exception: 不主动抛出异常。
    """

    if exc is None:
        return "none"
    match = _ERROR_CODE_PATTERN.search(str(exc))
    if match is not None:
        return match.group(1)
    return exc.__class__.__name__


def _safe_exception_message(exc: Exception | None) -> str:
    """构造脱敏 proposal 异常摘要。

    :param exc: proposal 异常；无异常时为 ``None``。
    :returns: 可进入日志的有界短文本。
    :raises Exception: 不主动抛出异常。
    """

    if exc is None:
        return "none"
    message = str(exc)
    if message.strip() == "":
        return exc.__class__.__name__
    redacted = _BEARER_SECRET_PATTERN.sub(f"Bearer {_REDACTED_SECRET}", message)
    redacted = _ASSIGNMENT_SECRET_PATTERN.sub(rf"\1{_REDACTED_SECRET}", redacted)
    if len(redacted) <= _MAX_SAFE_EXCEPTION_MESSAGE_CHARS:
        return redacted
    body_length = _MAX_SAFE_EXCEPTION_MESSAGE_CHARS - len(_TRUNCATED_SUFFIX)
    return redacted[:body_length] + _TRUNCATED_SUFFIX


__all__ = [
    "CompactionAttemptRejected",
    "CompactionOperationResult",
    "run_compaction_operation",
]
