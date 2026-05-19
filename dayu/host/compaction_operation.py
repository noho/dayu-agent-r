"""Host 内部 context compaction operation helper。

本模块只执行事务外 compaction proposal attempt 循环、质量校验与预算硬阈值
校验。EventLog 写入、artifact 写入、memory projection 与 durable state recheck
仍由调用方所在的 Host governance 路径负责。
"""

from __future__ import annotations

from dataclasses import dataclass

from dayu.host.compaction import (
    CompactQualityCheckResult,
    CompactionCandidate,
    CompactionRequest,
    ContextCompactor,
)
from dayu.host.context_governance import check_compaction_candidate

_FAILURE_PROPOSAL_FAILED = "proposal_failed"
_FAILURE_QUALITY_CHECK_REJECTED = "quality_check_rejected"
_FAILURE_HARD_THRESHOLD_AFTER_COMPACT = "hard_threshold_after_compact"
_FAILURE_MAX_ATTEMPTS_EXHAUSTED = "max_compaction_attempts_exhausted"
_NEXT_DECISION_RETRY_REPAIR = "retry_semantic_repair"
_NEXT_DECISION_FAIL_COMPACTION = "fail_compaction"
_DIAGNOSTIC_SUFFIX_UNKNOWN = "unknown"
_DIAGNOSTIC_SUFFIX_HARD_THRESHOLD = "hard_threshold"


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


def run_compaction_operation(
    *,
    request: CompactionRequest,
    compactor: ContextCompactor,
    max_attempts: int,
) -> CompactionOperationResult:
    """在事务外执行 Host semantic compaction operation。

    :param request: Host compaction request。
    :param compactor: Host internal compactor seam。
    :param max_attempts: proposal attempt 上限。
    :returns: compaction operation 结果。
    """

    rejected: list[CompactionAttemptRejected] = []
    last_budget: int | None = None
    for attempt_number in range(1, max_attempts + 1):
        repairable = attempt_number < max_attempts
        next_decision = (
            _NEXT_DECISION_RETRY_REPAIR
            if repairable
            else _NEXT_DECISION_FAIL_COMPACTION
        )
        try:
            candidate = compactor.compact(request)
        except Exception as exc:
            rejected.append(
                _attempt_rejected(
                    request=request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_PROPOSAL_FAILED,
                    repairable=repairable,
                    next_policy_decision=next_decision,
                    budget_after_attempted_compact=None,
                    diagnostic_suffix=exc.__class__.__name__,
                )
            )
            if repairable:
                continue
            return CompactionOperationResult(
                accepted_candidate=None,
                quality_result=None,
                rejected_attempts=tuple(rejected),
                failure_reason=_FAILURE_PROPOSAL_FAILED,
                budget_after_attempted_compact=None,
            )
        quality = check_compaction_candidate(request, candidate)
        last_budget = candidate.budget_after_compact
        if not quality.accepted:
            rejected.append(
                _attempt_rejected(
                    request=request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_QUALITY_CHECK_REJECTED,
                    repairable=repairable,
                    next_policy_decision=next_decision,
                    budget_after_attempted_compact=candidate.budget_after_compact,
                    diagnostic_suffix=_quality_suffix(quality),
                )
            )
            if repairable:
                continue
            return CompactionOperationResult(
                accepted_candidate=None,
                quality_result=None,
                rejected_attempts=tuple(rejected),
                failure_reason=_FAILURE_QUALITY_CHECK_REJECTED,
                budget_after_attempted_compact=candidate.budget_after_compact,
            )
        if (
            candidate.budget_after_compact
            >= request.budget_before_compact.hard_threshold_tokens
        ):
            rejected.append(
                _attempt_rejected(
                    request=request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_HARD_THRESHOLD_AFTER_COMPACT,
                    repairable=repairable,
                    next_policy_decision=next_decision,
                    budget_after_attempted_compact=candidate.budget_after_compact,
                    diagnostic_suffix=_DIAGNOSTIC_SUFFIX_HARD_THRESHOLD,
                )
            )
            if repairable:
                continue
            return CompactionOperationResult(
                accepted_candidate=None,
                quality_result=None,
                rejected_attempts=tuple(rejected),
                failure_reason=_FAILURE_HARD_THRESHOLD_AFTER_COMPACT,
                budget_after_attempted_compact=candidate.budget_after_compact,
            )
        return CompactionOperationResult(
            accepted_candidate=candidate,
            quality_result=quality,
            rejected_attempts=tuple(rejected),
            failure_reason=None,
            budget_after_attempted_compact=candidate.budget_after_compact,
        )
    return CompactionOperationResult(
        accepted_candidate=None,
        quality_result=None,
        rejected_attempts=tuple(rejected),
        failure_reason=_FAILURE_MAX_ATTEMPTS_EXHAUSTED,
        budget_after_attempted_compact=last_budget,
    )


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
        runner_attempt_summary_refs=(
            f"runner-attempt:{request.run_id}:{attempt_number}",
        ),
        diagnostic_refs=(
            f"diagnostic:{failure_category}:{operation_ref}:{diagnostic_suffix}",
        ),
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


__all__ = [
    "CompactionAttemptRejected",
    "CompactionOperationResult",
    "run_compaction_operation",
]
