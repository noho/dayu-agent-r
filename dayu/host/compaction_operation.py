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
    CompactQualityCheckResult,
    CompactionCandidate,
    CompactionRequest,
    ContextCompactor,
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
_ASSIGNMENT_SECRET_PATTERN = re.compile(
    r"(?i)((?:api[_-]?key|authorization|token|secret)\s*[:=]\s*)[^,\s}\]]+"
)
_ERROR_CODE_PATTERN = re.compile(r"\berror_code=([A-Za-z0-9_-]+)")
_LOGGER = logging.getLogger(__name__)


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
) -> CompactionOperationResult:
    """在事务外执行 Host semantic compaction operation。

    :param request: Host compaction request。
    :param compactor: Host internal compactor seam。
    :param max_attempts: proposal attempt 上限。
    :param cancellation_token: Host 注入 compactor 的真实取消 token。
    :returns: compaction operation 结果。
    """

    rejected: list[CompactionAttemptRejected] = []
    last_budget: int | None = None
    for attempt_number in range(1, max_attempts + 1):
        if cancellation_token.is_cancelled():
            rejected_attempt = _attempt_rejected(
                request=request,
                attempt_number=attempt_number,
                failure_category=_FAILURE_CANCELLATION_REQUESTED,
                repairable=False,
                next_policy_decision=_NEXT_DECISION_FAIL_COMPACTION,
                budget_after_attempted_compact=last_budget,
                diagnostic_suffix=_cancellation_suffix(cancellation_token),
            )
            rejected.append(rejected_attempt)
            _log_rejected_attempt(
                request=request,
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
        next_decision = (
            _NEXT_DECISION_RETRY_REPAIR
            if repairable
            else _NEXT_DECISION_FAIL_COMPACTION
        )
        try:
            candidate = await compactor.compact(request, cancellation_token)
        except Exception as exc:
            rejected_attempt = _attempt_rejected(
                request=request,
                attempt_number=attempt_number,
                failure_category=_FAILURE_PROPOSAL_FAILED,
                repairable=repairable,
                next_policy_decision=next_decision,
                budget_after_attempted_compact=None,
                diagnostic_suffix=_exception_diagnostic_suffix(exc),
            )
            rejected.append(rejected_attempt)
            _log_rejected_attempt(
                request=request,
                rejected=rejected_attempt,
                exception=exc,
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
            rejected_attempt = _attempt_rejected(
                request=request,
                attempt_number=attempt_number,
                failure_category=_FAILURE_QUALITY_CHECK_REJECTED,
                repairable=repairable,
                next_policy_decision=next_decision,
                budget_after_attempted_compact=candidate.budget_after_compact,
                diagnostic_suffix=_quality_suffix(quality),
            )
            rejected.append(rejected_attempt)
            _log_rejected_attempt(
                request=request,
                rejected=rejected_attempt,
                exception=None,
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
        if _requires_budget_acceptance(request) and (
            candidate.budget_after_compact
            >= request.budget_before_compact.hard_threshold_tokens
        ):
            rejected_attempt = _attempt_rejected(
                request=request,
                attempt_number=attempt_number,
                failure_category=_FAILURE_HARD_THRESHOLD_AFTER_COMPACT,
                repairable=repairable,
                next_policy_decision=next_decision,
                budget_after_attempted_compact=candidate.budget_after_compact,
                diagnostic_suffix=_DIAGNOSTIC_SUFFIX_HARD_THRESHOLD,
            )
            rejected.append(rejected_attempt)
            _log_rejected_attempt(
                request=request,
                rejected=rejected_attempt,
                exception=None,
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
    redacted = _BEARER_SECRET_PATTERN.sub(
        f"Bearer {_REDACTED_SECRET}", message
    )
    redacted = _ASSIGNMENT_SECRET_PATTERN.sub(
        rf"\1{_REDACTED_SECRET}", redacted
    )
    if len(redacted) <= _MAX_SAFE_EXCEPTION_MESSAGE_CHARS:
        return redacted
    body_length = _MAX_SAFE_EXCEPTION_MESSAGE_CHARS - len(_TRUNCATED_SUFFIX)
    return redacted[:body_length] + _TRUNCATED_SUFFIX


__all__ = [
    "CompactionAttemptRejected",
    "CompactionOperationResult",
    "run_compaction_operation",
]
