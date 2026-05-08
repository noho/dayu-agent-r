"""Host 内部 context overflow compact 协调器。

本模块只处理 Host-owned context compact policy、deterministic compact
输入构造与保真 / 变短校验。它不调用 LLM compaction scene，不 import
Engine 运行状态机，也不改变原始 ``USER_INPUT_ACCEPTED`` 真源。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from dayu.engine import AgentMessageRole, SystemMessage, UserMessage
from dayu.host._conversation_memory import (
    ConversationMemorySnapshot,
    ConversationToolFact,
    EvidenceAnchor,
    MemoryClaim,
)
from dayu.host._token_estimator import (
    TOKEN_ESTIMATOR_ALGORITHM_ID,
    estimate_messages_chars,
    estimate_messages_tokens,
)
from dayu.host.contracts import (
    ContextCompactFailureReason,
    HostContextCompactCompletedData,
    HostContextCompactFailedData,
    HostContextCompactRequestedData,
    RunEvent,
    RunInput,
    StartRunRequest,
    UserInputAcceptedData,
)
from dayu.runtime.log_levels import VERBOSE_LOG_LEVEL

COMPACT_POLICY_ID: str = "host_deterministic_context_compact_v1"
_NOOP_FAILURE_MESSAGE: str = "compacted RunInput is not shorter"
_FIDELITY_FAILURE_MESSAGE: str = "compacted RunInput failed fidelity checks"
_CURRENT_USER_FAILURE_MESSAGE: str = "current USER_INPUT_ACCEPTED fact is missing"
_STABLE_CLAIM_SECTION_HEADER: str = "## Stable Claims"
_EVIDENCE_ANCHORS_SECTION_HEADER: str = "## Evidence Anchors"
_TOOL_FACTS_SECTION_HEADER: str = "## Tool Facts"
_SOURCE_EVENT_CURSOR_FIELD: str = "source_event_cursor"
_CURRENT_COMPACT_DEGRADED_ITEM_COUNT: int = 0
_LOGGER: logging.Logger = logging.getLogger(__name__)


class ContextCompactDecisionStatus(StrEnum):
    """Context compact 决策状态。"""

    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ContextCompactDecision:
    """Context compact 决策结果。

    :param status: 决策状态。
    :param requested_data: compact requested 事件 data。
    :param completed_data: compact 成功事件 data；失败时为 ``None``。
    :param failed_data: compact 失败事件 data；成功时为 ``None``。
    :param run_input: compact 后 RunInput；失败时为 ``None``。
    """

    status: ContextCompactDecisionStatus
    requested_data: HostContextCompactRequestedData
    completed_data: HostContextCompactCompletedData | None
    failed_data: HostContextCompactFailedData | None
    run_input: RunInput | None


@dataclass(frozen=True, slots=True)
class ContextCompactCoordinator:
    """Host 内部 deterministic context compact 协调器。"""

    policy_id: str = COMPACT_POLICY_ID

    def compact(
        self,
        *,
        request: StartRunRequest,
        snapshot: ConversationMemorySnapshot,
        current_user_event: RunEvent,
        attempt_index: int,
    ) -> ContextCompactDecision:
        """构造 compact 后 RunInput 并校验是否可 retry。

        :param request: 当前 attempt 使用的 StartRunRequest。
        :param snapshot: 当前 session memory 快照。
        :param current_user_event: 本 Run 原始 ``USER_INPUT_ACCEPTED`` 事件。
        :param attempt_index: 当前 attempt 序号。
        :returns: compact 决策。
        :raises TypeError: 当前用户事件 data 类型不匹配时抛出。
        """

        before_tokens = estimate_messages_tokens(request.input.messages)
        before_chars = estimate_messages_chars(request.input.messages)
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.context_compact.start session_id=%s run_id=%s "
            "attempt_index=%s policy_id=%s before_tokens=%s "
            "before_chars=%s",
            request.session_id,
            request.run_id,
            attempt_index,
            self.policy_id,
            before_tokens,
            before_chars,
        )
        requested = HostContextCompactRequestedData(
            attempt_index=attempt_index,
            policy_id=self.policy_id,
            before_token_estimate=before_tokens,
            before_char_size=before_chars,
            estimator_id=TOKEN_ESTIMATOR_ALGORITHM_ID,
        )
        current_user = _current_user_text(current_user_event)
        if current_user is None:
            decision = self._failed(
                attempt_index=attempt_index,
                requested_data=requested,
                reason=ContextCompactFailureReason.CURRENT_USER_NOT_FOUND,
                message=_CURRENT_USER_FAILURE_MESSAGE,
                before_token_estimate=before_tokens,
                before_char_size=before_chars,
                after_token_estimate=None,
                after_char_size=None,
            )
            _log_compact_decision(request=request, decision=decision)
            return decision
        compacted_input = _build_compacted_run_input(
            previous_input=request.input,
            snapshot=snapshot,
            current_user=current_user,
        )
        after_tokens = estimate_messages_tokens(compacted_input.messages)
        after_chars = estimate_messages_chars(compacted_input.messages)
        fidelity = _check_fidelity(
            run_input=compacted_input,
            snapshot=snapshot,
            current_user=current_user,
        )
        dropped_count = len(snapshot.recent_raw_turns) + len(
            snapshot.older_raw_turns
        )
        degraded_count = _count_current_compact_degraded_items()
        if after_tokens >= before_tokens or after_chars >= before_chars:
            decision = self._failed(
                attempt_index=attempt_index,
                requested_data=requested,
                reason=ContextCompactFailureReason.NOT_REDUCED,
                message=_NOOP_FAILURE_MESSAGE,
                before_token_estimate=before_tokens,
                before_char_size=before_chars,
                after_token_estimate=after_tokens,
                after_char_size=after_chars,
            )
            _log_compact_decision(request=request, decision=decision)
            return decision
        if not fidelity.preserved_all:
            decision = self._failed(
                attempt_index=attempt_index,
                requested_data=requested,
                reason=ContextCompactFailureReason.FIDELITY_FAILED,
                message=_FIDELITY_FAILURE_MESSAGE,
                before_token_estimate=before_tokens,
                before_char_size=before_chars,
                after_token_estimate=after_tokens,
                after_char_size=after_chars,
            )
            _log_compact_decision(request=request, decision=decision)
            return decision
        completed = HostContextCompactCompletedData(
            attempt_index=attempt_index,
            policy_id=self.policy_id,
            before_token_estimate=before_tokens,
            after_token_estimate=after_tokens,
            before_char_size=before_chars,
            after_char_size=after_chars,
            reduced=True,
            preserved_current_user=fidelity.preserved_current_user,
            preserved_pinned_state=fidelity.preserved_pinned_state,
            preserved_evidence_anchors=fidelity.preserved_evidence_anchors,
            preserved_source_cursors=fidelity.preserved_source_cursors,
            preserved_tool_facts=fidelity.preserved_tool_facts,
            dropped_item_count=dropped_count,
            degraded_item_count=degraded_count,
            estimator_id=TOKEN_ESTIMATOR_ALGORITHM_ID,
        )
        decision = ContextCompactDecision(
            status=ContextCompactDecisionStatus.COMPLETED,
            requested_data=requested,
            completed_data=completed,
            failed_data=None,
            run_input=compacted_input,
        )
        _log_compact_decision(request=request, decision=decision)
        return decision

    def retry_limit_failed(
        self,
        *,
        request: StartRunRequest,
        attempt_index: int,
    ) -> HostContextCompactFailedData:
        """构造 compact retry 上限耗尽失败 data。

        :param request: 当前 attempt 请求。
        :param attempt_index: 当前 attempt 序号。
        :returns: compact failed 事件 data。
        :raises Exception: 不主动抛出异常。
        """

        return HostContextCompactFailedData(
            attempt_index=attempt_index,
            policy_id=self.policy_id,
            reason=ContextCompactFailureReason.RETRY_LIMIT_EXCEEDED,
            message="context compact retry limit exceeded",
            before_token_estimate=estimate_messages_tokens(
                request.input.messages
            ),
            after_token_estimate=None,
            before_char_size=estimate_messages_chars(request.input.messages),
            after_char_size=None,
            estimator_id=TOKEN_ESTIMATOR_ALGORITHM_ID,
        )

    def exception_failed(
        self,
        *,
        request: StartRunRequest,
        attempt_index: int,
        reason: ContextCompactFailureReason,
        message: str,
    ) -> HostContextCompactFailedData:
        """构造 compact 分支异常失败 data。

        :param request: 当前 attempt 请求。
        :param attempt_index: 当前 attempt 序号。
        :param reason: 强类型失败原因。
        :param message: 中性可读说明。
        :returns: compact failed 事件 data。
        :raises Exception: 不主动抛出异常。
        """

        return HostContextCompactFailedData(
            attempt_index=attempt_index,
            policy_id=self.policy_id,
            reason=reason,
            message=message,
            before_token_estimate=estimate_messages_tokens(
                request.input.messages
            ),
            after_token_estimate=None,
            before_char_size=estimate_messages_chars(request.input.messages),
            after_char_size=None,
            estimator_id=TOKEN_ESTIMATOR_ALGORITHM_ID,
        )

    def _failed(
        self,
        *,
        attempt_index: int,
        requested_data: HostContextCompactRequestedData,
        reason: ContextCompactFailureReason,
        message: str,
        before_token_estimate: int,
        before_char_size: int,
        after_token_estimate: int | None,
        after_char_size: int | None,
    ) -> ContextCompactDecision:
        """构造失败 compact 决策。

        :param attempt_index: 当前 attempt 序号。
        :param requested_data: compact requested data。
        :param reason: 失败原因。
        :param message: 中性说明。
        :param before_token_estimate: compact 前估算 token。
        :param before_char_size: compact 前字符数。
        :param after_token_estimate: compact 后估算 token。
        :param after_char_size: compact 后字符数。
        :returns: 失败决策。
        :raises Exception: 不主动抛出异常。
        """

        failed = HostContextCompactFailedData(
            attempt_index=attempt_index,
            policy_id=self.policy_id,
            reason=reason,
            message=message,
            before_token_estimate=before_token_estimate,
            after_token_estimate=after_token_estimate,
            before_char_size=before_char_size,
            after_char_size=after_char_size,
            estimator_id=TOKEN_ESTIMATOR_ALGORITHM_ID,
        )
        return ContextCompactDecision(
            status=ContextCompactDecisionStatus.FAILED,
            requested_data=requested_data,
            completed_data=None,
            failed_data=failed,
            run_input=None,
        )


@dataclass(frozen=True, slots=True)
class _FidelityCheck:
    """Compact 保真检查结果。"""

    preserved_current_user: bool
    preserved_pinned_state: bool
    preserved_evidence_anchors: bool
    preserved_source_cursors: bool
    preserved_tool_facts: bool

    @property
    def preserved_all(self) -> bool:
        """返回全部保真检查是否通过。

        :returns: 全部通过返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return (
            self.preserved_current_user
            and self.preserved_pinned_state
            and self.preserved_evidence_anchors
            and self.preserved_source_cursors
            and self.preserved_tool_facts
        )


def _log_compact_decision(
    *,
    request: StartRunRequest,
    decision: ContextCompactDecision,
) -> None:
    """记录 compact 决策的有界诊断信息。

    :param request: 当前 attempt 请求。
    :param decision: compact 决策。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if decision.status is ContextCompactDecisionStatus.COMPLETED:
        completed = decision.completed_data
        if completed is None:
            return
        _LOGGER.log(
            VERBOSE_LOG_LEVEL,
            "host.context_compact.completed session_id=%s run_id=%s "
            "attempt_index=%s before_tokens=%s after_tokens=%s "
            "before_chars=%s after_chars=%s dropped_item_count=%s "
            "degraded_item_count=%s",
            request.session_id,
            request.run_id,
            completed.attempt_index,
            completed.before_token_estimate,
            completed.after_token_estimate,
            completed.before_char_size,
            completed.after_char_size,
            completed.dropped_item_count,
            completed.degraded_item_count,
        )
        return
    failed = decision.failed_data
    if failed is None:
        return
    _LOGGER.debug(
        "host.context_compact.failed session_id=%s run_id=%s "
        "attempt_index=%s reason=%s before_tokens=%s after_tokens=%s "
        "before_chars=%s after_chars=%s",
        request.session_id,
        request.run_id,
        failed.attempt_index,
        failed.reason.value,
        failed.before_token_estimate,
        failed.after_token_estimate,
        failed.before_char_size,
        failed.after_char_size,
    )


def _build_compacted_run_input(
    *,
    previous_input: RunInput,
    snapshot: ConversationMemorySnapshot,
    current_user: str,
) -> RunInput:
    """构造 compact 后 RunInput。

    :param previous_input: 上一次 attempt 使用的 RunInput。
    :param snapshot: memory 快照。
    :param current_user: 当前用户问题。
    :returns: compact 后 RunInput。
    :raises Exception: 不主动抛出异常。
    """

    compact_block = _render_compact_memory(snapshot)
    caller_system_messages = tuple(
        message
        for message in previous_input.messages
        if isinstance(message, SystemMessage)
        and not _is_host_memory_system_message(message.content)
    )
    return RunInput(
        messages=(
            *caller_system_messages,
            SystemMessage(
                role=AgentMessageRole.SYSTEM,
                content=compact_block,
            ),
            UserMessage(role=AgentMessageRole.USER, content=current_user),
        )
    )


def _render_compact_memory(snapshot: ConversationMemorySnapshot) -> str:
    """渲染 deterministic compact memory block。

    :param snapshot: memory 快照。
    :returns: compact memory system block 文本。
    :raises Exception: 不主动抛出异常。
    """

    parts: list[str] = [
        "## Host Compact Memory",
        (
            "INTERNAL_ONLY: 此区块仅供模型做上下文 grounding 与校验；"
            "它不是最终回答模板，禁止原样输出 Host Memory、Tool Facts、"
            "历史工具摘要、tool_fact_id、cursor_fingerprint、"
            "source_event_cursor、scope token 或 raw EventLog metadata。"
        ),
        _format_pinned_state(snapshot),
        _format_stable_frame(snapshot),
    ]
    parts.append(
        _format_section(
            header=_STABLE_CLAIM_SECTION_HEADER,
            items=tuple(
                _format_claim(claim)
                for claim in (
                    *snapshot.verified_claims,
                    *snapshot.assumptions.claims,
                )
            ),
        )
    )
    parts.append(
        _format_section(
            header=_EVIDENCE_ANCHORS_SECTION_HEADER,
            items=tuple(
                _format_anchor(anchor) for anchor in snapshot.evidence_anchors
            ),
        )
    )
    parts.append(
        _format_section(
            header=_TOOL_FACTS_SECTION_HEADER,
            items=tuple(_format_tool_fact(fact) for fact in snapshot.tool_facts),
        )
    )
    if snapshot.recent_raw_turns or snapshot.older_raw_turns:
        parts.append(
            "## Compacted History\n"
            "older raw turns were dropped for context overflow recovery; "
            "current USER_INPUT_ACCEPTED and evidence anchors are preserved."
        )
    return "\n\n".join(part for part in parts if part)


def _format_section(*, header: str, items: tuple[str, ...]) -> str:
    """格式化 compact memory 中的多 item section。

    :param header: section 标题。
    :param items: section 正文条目。
    :returns: 有条目时返回标题加正文；无条目时返回空字符串。
    :raises Exception: 不主动抛出异常。
    """

    if not items:
        return ""
    return f"{header}\n" + "\n".join(items)


def _format_pinned_state(snapshot: ConversationMemorySnapshot) -> str:
    """格式化 pinned state。

    :param snapshot: memory 快照。
    :returns: pinned state 文本。
    :raises Exception: 不主动抛出异常。
    """

    pinned = snapshot.pinned_state
    return (
        "## Pinned State\n"
        f"current_goal={pinned.current_goal}; "
        f"confirmed_subjects={'; '.join(pinned.confirmed_subjects)}; "
        f"user_constraints={'; '.join(pinned.user_constraints)}; "
        f"open_questions={'; '.join(pinned.open_questions)}"
    )


def _format_stable_frame(snapshot: ConversationMemorySnapshot) -> str:
    """格式化 stable frame。

    :param snapshot: memory 快照。
    :returns: stable frame 文本。
    :raises Exception: 不主动抛出异常。
    """

    frame = snapshot.task_frame
    return (
        "## Stable Frame\n"
        f"topic_ref={frame.topic_ref}; "
        f"entity_refs={','.join(frame.entity_refs)}; "
        f"period_refs={','.join(frame.period_refs)}; "
        f"basis_refs={','.join(frame.basis_refs)}; "
        f"unit_ref={frame.unit_ref}; "
        f"user_preference_profile_ref={snapshot.user_preference_ref.profile_id}"
    )


def _format_claim(claim: MemoryClaim) -> str:
    """格式化 compact claim。

    :param claim: memory claim。
    :returns: claim 文本。
    :raises Exception: 不主动抛出异常。
    """

    return (
        f"claim_id={claim.claim_id}; status={claim.status.value}; "
        f"scope={claim.scope.value}; evidence_anchor_id={claim.evidence_anchor_id}; "
        f"{_SOURCE_EVENT_CURSOR_FIELD}={claim.source_event_cursor.sequence}; "
        f"text={claim.text}"
    )


def _format_anchor(anchor: EvidenceAnchor) -> str:
    """格式化 compact evidence anchor。

    :param anchor: evidence anchor。
    :returns: anchor 文本。
    :raises Exception: 不主动抛出异常。
    """

    return (
        f"anchor_id={anchor.anchor_id}; tool_call_id={anchor.tool_call_id}; "
        f"{_SOURCE_EVENT_CURSOR_FIELD}={anchor.origin_event_cursor.sequence}; "
        f"source_ref={anchor.source_ref}; chunk_ref={anchor.chunk_ref}; "
        f"fingerprint={anchor.fingerprint}; summary={anchor.summary}"
    )


def _format_tool_fact(fact: ConversationToolFact) -> str:
    """格式化 compact tool fact。

    :param fact: tool fact。
    :returns: tool fact 文本。
    :raises Exception: 不主动抛出异常。
    """

    return (
        f"tool_fact_id={fact.fact_id}; tool_name={fact.tool_name}; "
        f"tool_call_id={fact.tool_call_id}; event_type={fact.event_type.value}; "
        f"{_SOURCE_EVENT_CURSOR_FIELD}={fact.provenance.source_event_cursor.sequence}; "
        f"cursor_fingerprint={fact.cursor_fingerprint}; "
        f"has_more={fact.has_more}; summary={fact.summary}"
    )


def _is_host_memory_system_message(content: str) -> bool:
    """判断 system message 是否为 Host memory block。

    :param content: system message 正文。
    :returns: Host memory block 返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return content.startswith("## Host Memory") or content.startswith(
        "## Host Compact Memory"
    )


def _current_user_text(event: RunEvent) -> str | None:
    """从 ``USER_INPUT_ACCEPTED`` 事件读取当前用户正文。

    :param event: 当前用户输入事件。
    :returns: 用户正文；事件类型不匹配时返回 ``None``。
    :raises TypeError: data 类型错误时抛出。
    """

    data = event.data
    if not isinstance(data, UserInputAcceptedData):
        return None
    return data.content


def _check_fidelity(
    *,
    run_input: RunInput,
    snapshot: ConversationMemorySnapshot,
    current_user: str,
) -> _FidelityCheck:
    """检查 compact 后 RunInput 的必保事实。

    :param run_input: compact 后 RunInput。
    :param snapshot: memory 快照。
    :param current_user: 当前用户问题。
    :returns: 保真检查结果。
    :raises Exception: 不主动抛出异常。
    """

    combined = "\n".join(
        "" if message.content is None else message.content
        for message in run_input.messages
    )
    current_preserved = any(
        isinstance(message, UserMessage) and message.content == current_user
        for message in run_input.messages
    )
    anchor_ids = tuple(anchor.anchor_id for anchor in snapshot.evidence_anchors)
    anchor_cursors = tuple(
        str(anchor.origin_event_cursor.sequence)
        for anchor in snapshot.evidence_anchors
    )
    fact_ids = tuple(fact.fact_id for fact in snapshot.tool_facts)
    fact_cursors = tuple(
        str(fact.provenance.source_event_cursor.sequence)
        for fact in snapshot.tool_facts
    )
    return _FidelityCheck(
        preserved_current_user=current_preserved,
        preserved_pinned_state=_format_pinned_state(snapshot) in combined,
        preserved_evidence_anchors=all(
            anchor_id in combined for anchor_id in anchor_ids
        ),
        preserved_source_cursors=all(
            f"{_SOURCE_EVENT_CURSOR_FIELD}={cursor}" in combined
            for cursor in anchor_cursors + fact_cursors
        ),
        preserved_tool_facts=all(fact_id in combined for fact_id in fact_ids),
    )


def _count_current_compact_degraded_items() -> int:
    """统计本次 deterministic compact 中被降级但未丢弃的 item 数。

    当前 compact 策略只显式丢弃 raw turns，并保真渲染 pinned state、
    claim、evidence anchor 与 tool fact；没有单独的“保留但降级”动作。

    :returns: 本次 compact 降级 item 数。
    :raises Exception: 不主动抛出异常。
    """

    return _CURRENT_COMPACT_DEGRADED_ITEM_COUNT


__all__ = [
    "COMPACT_POLICY_ID",
    "ContextCompactCoordinator",
    "ContextCompactDecision",
    "ContextCompactDecisionStatus",
]
