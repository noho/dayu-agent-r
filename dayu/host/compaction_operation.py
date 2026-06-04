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
from dayu.host.compact_material import conversation_compact_input_vnext_from_material_pack
from dayu.host.compaction import (
    CompactQualityCheckResultVNext,
    CompactionRequest,
    ContextCompactor,
    ConversationCompactInputVNext,
    ConversationCompactOutputVNext,
)
from dayu.host.context_budget import DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS, estimate_budget_text_tokens
from dayu.host.context_governance import check_conversation_compact_output_vnext
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.runtime.diagnostic_text import (
    redact_sensitive_diagnostic_values,
    truncate_diagnostic_text,
)

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
_ERROR_CODE_PATTERN = re.compile(r"\berror_code=([A-Za-z0-9_-]+)")
_LOGGER = logging.getLogger(__name__)
_POST_COMPACT_BASE_MESSAGE_COUNT = 2


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

    accepted_candidate: ConversationCompactOutputVNext | None
    quality_result: CompactQualityCheckResultVNext | None
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
    last_budget: int | None = None
    accepted_candidate: ConversationCompactOutputVNext | None = None
    accepted_quality: CompactQualityCheckResultVNext | None = None
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
                compact_input = conversation_compact_input_vnext_from_material_pack(
                    pass_request.material_pack
                )
                candidate = await _compact_candidate(
                    compactor,
                    pass_request,
                    cancellation_token,
                )
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
            quality = check_conversation_compact_output_vnext(compact_input, candidate)
            last_budget = _budget_after_compact_candidate(pass_request, compact_input, candidate)
            if not quality.accepted:
                rejected_attempt = _attempt_rejected(
                    request=pass_request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_QUALITY_CHECK_REJECTED,
                    repairable=repairable,
                    next_policy_decision=next_decision,
                    budget_after_attempted_compact=last_budget,
                    diagnostic_suffix=_quality_suffix_vnext(quality),
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
                        budget_after_attempted_compact=last_budget,
                    )
                attempt_number += 1
                continue
            if _requires_budget_acceptance(pass_request) and (
                last_budget >= pass_request.budget_before_compact.hard_threshold_tokens
            ):
                rejected_attempt = _attempt_rejected(
                    request=pass_request,
                    attempt_number=attempt_number,
                    failure_category=_FAILURE_HARD_THRESHOLD_AFTER_COMPACT,
                    repairable=repairable,
                    next_policy_decision=next_decision,
                    budget_after_attempted_compact=last_budget,
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
                        budget_after_attempted_compact=last_budget,
                    )
                attempt_number += 1
                continue
            pass_accepted = True
            accepted_candidate = candidate
            accepted_quality = quality
            attempt_number += 1
        if not pass_accepted:
            return CompactionOperationResult(
                accepted_candidate=None,
                quality_result=None,
                rejected_attempts=tuple(rejected),
                failure_reason=_FAILURE_MAX_ATTEMPTS_EXHAUSTED,
                budget_after_attempted_compact=last_budget,
            )
    if accepted_candidate is None or accepted_quality is None:
        return CompactionOperationResult(
            accepted_candidate=None,
            quality_result=None,
            rejected_attempts=tuple(rejected),
            failure_reason=_FAILURE_MAX_ATTEMPTS_EXHAUSTED,
            budget_after_attempted_compact=last_budget,
        )
    return CompactionOperationResult(
        accepted_candidate=accepted_candidate,
        quality_result=accepted_quality,
        rejected_attempts=tuple(rejected),
        failure_reason=None,
        budget_after_attempted_compact=last_budget,
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


def _requires_budget_acceptance(request: CompactionRequest) -> bool:
    """判断本次 operation 是否需要 compact 后预算估算闸门。

    proactive path 在 dispatch 前使用估算值决定是否创建 Attempt；reactive path
    来自真实 provider overflow，compact 后是否足够应交给后续真实 dispatch /
    Engine event 闭环判断，避免不准估算阻断第二次 reactive compact。

    :param request: Host compaction request。
    :returns: 需要估算闸门时返回 ``True``。
    """

    return request.trigger_source is ContextCompactionTriggerSource.PROACTIVE


async def _compact_candidate(
    compactor: ContextCompactor,
    request: CompactionRequest,
    cancellation_token: CancellationToken,
) -> ConversationCompactOutputVNext:
    """调用 vNext compactor capability。

    :param compactor: Host internal compactor seam。
    :param request: Host compaction request。
    :param cancellation_token: Host 注入 compactor 的真实取消 token。
    :returns: vNext compact output。
    :raises TypeError: compactor 不支持 vNext capability 时抛出。
    """

    return await compactor.compact(request, cancellation_token)


def _budget_after_compact_candidate(
    request: CompactionRequest,
    compact_input: ConversationCompactInputVNext,
    candidate: ConversationCompactOutputVNext,
) -> int:
    """估算 vNext compact 后预算。

    预算是 Host governance 诊断，不由 LLM candidate 输出。本估算只读取
    accepted candidate 的业务可读文本、当前输入和必须保留的边界 refs。

    :param request: operation root request。
    :param compact_input: 本次发送给 compactor 的 vNext input。
    :param candidate: vNext compact output。
    :returns: 非负 token 估算。
    """

    fragments = (
        *_candidate_text_fragments(candidate),
        compact_input.current_input_anchor.text,
    )
    token_count = sum(max(1, estimate_budget_text_tokens(fragment)) for fragment in fragments)
    return token_count + (
        DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS * _POST_COMPACT_BASE_MESSAGE_COUNT
    )


def _candidate_text_fragments(candidate: ConversationCompactOutputVNext) -> tuple[str, ...]:
    """收集 vNext candidate 中会被后续 projection 消费的文本片段。

    :param candidate: vNext compact output。
    :returns: 文本片段 tuple。
    """

    fragments: list[str] = []
    if candidate.session_summary is not None:
        fragments.append(candidate.session_summary.summary_text)
    for fact in candidate.evidence_backed_facts:
        fragments.append(fact.claim_text)
    for anchor in candidate.answer_anchors:
        fragments.append(anchor.anchor_title)
        fragments.extend(item.display_text for item in anchor.anchor_items)
    for intent in candidate.forward_intents:
        fragments.append(intent.text)
    for item in candidate.reference_continuity_items:
        fragments.append(item.text)
    for diagnostic in candidate.diagnostics:
        fragments.append(diagnostic.code)
        fragments.append(diagnostic.text)
    return tuple(fragments)


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


def _quality_suffix_vnext(quality: CompactQualityCheckResultVNext) -> str:
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
    redacted = redact_sensitive_diagnostic_values(
        message,
        redaction_marker=_REDACTED_SECRET,
    )
    return truncate_diagnostic_text(
        redacted,
        max_chars=_MAX_SAFE_EXCEPTION_MESSAGE_CHARS,
        truncated_suffix=_TRUNCATED_SUFFIX,
    )


__all__ = [
    "CompactionAttemptRejected",
    "CompactionOperationResult",
    "run_compaction_operation",
]
