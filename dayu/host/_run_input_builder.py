"""Host 内部 RunInputBuilder。

本模块把 Conversation Memory snapshot 与当前 run 已落库的
``USER_INPUT_ACCEPTED`` 事件构造成 Engine 可消费的 ``RunInput``。它只
生成运行态输入与 internal-only trace，不把 trace 写入 RunInput 或 memory。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from dayu.engine import AgentMessageRole, SystemMessage, UserMessage
from dayu.host._conversation_memory import (
    ConversationMemorySnapshot,
    ConversationRawTurn,
    ConversationToolFact,
    EvidenceAnchor,
    MemoryClaim,
    MemoryProvenance,
    summarize_raw_turn_for_builder,
)
from dayu.host.contracts import (
    RunEvent,
    RunEventKind,
    RunEventSource,
    RunEventType,
    RunInput,
    UserInputAcceptedData,
)

_APPROX_TOKEN_CHARS: int = 4
_MEMORY_BLOCK_CHAR_BUDGET: int = 6000
_RECENT_TURN_INLINE_CHAR_LIMIT: int = 900
_OLDER_TURN_INLINE_CHAR_LIMIT: int = 360
_TRACE_SOURCE_CURRENT_USER: str = "current_user"
_TRACE_SOURCE_MEMORY_BLOCK: str = "memory_block"
_TRACE_REASON_INCLUDED: str = "included"
_TRACE_REASON_BUDGET_EXHAUSTED: str = "memory_block_budget_exhausted"
_TRACE_REASON_RECENT_TURN_DOWNGRADED: str = "recent_turn_downgraded"
_TRACE_REASON_OLDER_TURN_SUMMARIZED: str = "older_turn_summarized"
_ERROR_SNAPSHOT_SESSION_MISMATCH: str = "snapshot_session_mismatch"


class RunInputTraceStatus(StrEnum):
    """RunInputBuilder trace item 状态。"""

    INCLUDED = "included"
    EXCLUDED = "excluded"


class RunInputTraceItemKind(StrEnum):
    """RunInputBuilder trace item 类型。"""

    PINNED_STATE = "pinned_state"
    STABLE_FRAME = "stable_frame"
    VERIFIED_CLAIM = "verified_claim"
    ASSUMPTION = "assumption"
    EVIDENCE_ANCHOR = "evidence_anchor"
    TOOL_FACT = "tool_fact"
    RECENT_RAW_TURN = "recent_raw_turn"
    OLDER_RAW_TURN = "older_raw_turn"
    EPISODE_SUMMARY_SLOT = "episode_summary_slot"
    CURRENT_USER = "current_user"
    MEMORY_BLOCK = "memory_block"


@dataclass(frozen=True, slots=True)
class RunInputTraceItem:
    """RunInputBuilder 单条诊断记录。

    :param status: included / excluded 状态。
    :param item_kind: item 类型。
    :param source_id: 来源 item id。
    :param source_run_id: 来源 run id；无来源 run 时为 ``None``。
    :param source_event_cursor: 来源 cursor sequence；无来源事件时为
        ``None``。
    :param reason: included 或裁剪原因。
    :param char_size: 估算字符数。
    :param token_estimate: 估算 token 数。
    """

    status: RunInputTraceStatus
    item_kind: RunInputTraceItemKind
    source_id: str
    source_run_id: str | None
    source_event_cursor: int | None
    reason: str
    char_size: int
    token_estimate: int


@dataclass(frozen=True, slots=True)
class RunInputBuildTrace:
    """RunInputBuilder internal-only trace。

    :param session_id: 会话 id。
    :param run_id: 当前 run id。
    :param items: included / excluded item 诊断元组。
    :param total_char_size: 已进入 RunInput 的估算字符数。
    :param total_token_estimate: 已进入 RunInput 的估算 token 数。
    """

    session_id: str
    run_id: str
    items: tuple[RunInputTraceItem, ...]
    total_char_size: int
    total_token_estimate: int


@dataclass(frozen=True, slots=True)
class RunInputBuildResult:
    """RunInputBuilder 构造结果。

    :param run_input: Engine 可消费 RunInput。
    :param trace: internal-only 构造 trace。
    """

    run_input: RunInput
    trace: RunInputBuildTrace


class RunInputBuilder(Protocol):
    """Host 内部 RunInputBuilder 协议。"""

    def build(
        self,
        *,
        snapshot: ConversationMemorySnapshot,
        current_user_event: RunEvent,
    ) -> RunInputBuildResult:
        """构造 Engine RunInput。

        :param snapshot: session memory 快照。
        :param current_user_event: 已 append 的当前用户输入事件。
        :returns: RunInput 与 internal trace。
        :raises TypeError: 当前用户输入事件 data 类型不匹配时抛出。
        :raises ValueError: 当前事件不是 canonical Host 用户输入事件时抛出。
        """
        ...


@dataclass(frozen=True, slots=True)
class DefaultRunInputBuilder:
    """P3 默认 RunInputBuilder。

    :param memory_block_char_budget: memory block 最大字符预算。
    """

    memory_block_char_budget: int = _MEMORY_BLOCK_CHAR_BUDGET

    def build(
        self,
        *,
        snapshot: ConversationMemorySnapshot,
        current_user_event: RunEvent,
    ) -> RunInputBuildResult:
        """构造 Engine RunInput。

        memory block 内部顺序固定为 pinned state / stable frame /
        verified claims / assumptions / evidence anchors / recent raw turns /
        older pool / episode summary 插入位；当前用户输入作为最后一条
        user message。

        :param snapshot: session memory 快照。
        :param current_user_event: 已 append 的当前用户输入事件。
        :returns: RunInput 与 internal trace。
        :raises TypeError: 当前用户输入事件 data 类型不匹配时抛出。
        :raises ValueError: 当前事件不是 canonical Host 用户输入事件，或
            snapshot 与当前事件 session 不一致时抛出。
        """

        current_user_text = _current_user_text(current_user_event)
        if snapshot.session_id != current_user_event.session_id:
            raise ValueError(_ERROR_SNAPSHOT_SESSION_MISMATCH)
        collector = _MemoryBlockCollector(
            session_id=current_user_event.session_id,
            run_id=current_user_event.run_id,
            char_budget=self.memory_block_char_budget,
        )
        _append_pinned_state(collector=collector, snapshot=snapshot)
        _append_stable_frame(collector=collector, snapshot=snapshot)
        _append_verified_claims(collector=collector, snapshot=snapshot)
        _append_assumptions(collector=collector, snapshot=snapshot)
        _append_evidence_anchors(collector=collector, snapshot=snapshot)
        _append_recent_raw_turns(collector=collector, snapshot=snapshot)
        _append_older_raw_turns(collector=collector, snapshot=snapshot)
        collector.include_without_provenance(
            kind=RunInputTraceItemKind.EPISODE_SUMMARY_SLOT,
            source_id="episode_summary_slot",
            text="## Episode Summary Slot\nP3 未生成 episode summary。",
        )
        memory_block = collector.render()
        current_user_trace = _trace_item(
            status=RunInputTraceStatus.INCLUDED,
            kind=RunInputTraceItemKind.CURRENT_USER,
            source_id=_TRACE_SOURCE_CURRENT_USER,
            provenance=None,
            source_run_id=current_user_event.run_id,
            source_event_cursor=current_user_event.cursor.sequence,
            reason=_TRACE_REASON_INCLUDED,
            text=current_user_text,
        )
        memory_block_trace = _trace_item(
            status=RunInputTraceStatus.INCLUDED,
            kind=RunInputTraceItemKind.MEMORY_BLOCK,
            source_id=_TRACE_SOURCE_MEMORY_BLOCK,
            provenance=None,
            source_run_id=None,
            source_event_cursor=None,
            reason=_TRACE_REASON_INCLUDED,
            text=memory_block,
        )
        trace_items = collector.items + (memory_block_trace, current_user_trace)
        total_chars = len(memory_block) + len(current_user_text)
        run_input = RunInput(
            messages=(
                SystemMessage(
                    role=AgentMessageRole.SYSTEM,
                    content=memory_block,
                ),
                UserMessage(
                    role=AgentMessageRole.USER,
                    content=current_user_text,
                ),
            )
        )
        return RunInputBuildResult(
            run_input=run_input,
            trace=RunInputBuildTrace(
                session_id=current_user_event.session_id,
                run_id=current_user_event.run_id,
                items=trace_items,
                total_char_size=total_chars,
                total_token_estimate=_estimate_tokens(total_chars),
            ),
        )


@dataclass(slots=True)
class _MemoryBlockCollector:
    """memory block 与 trace 收集器。"""

    session_id: str
    run_id: str
    char_budget: int
    _parts: list[str]
    _items: list[RunInputTraceItem]
    _used_chars: int

    def __init__(
        self,
        *,
        session_id: str,
        run_id: str,
        char_budget: int,
    ) -> None:
        """初始化收集器。

        :param session_id: 会话 id。
        :param run_id: 当前 run id。
        :param char_budget: memory block 字符预算。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self.session_id = session_id
        self.run_id = run_id
        self.char_budget = char_budget
        self._parts = []
        self._items = []
        self._used_chars = 0

    @property
    def items(self) -> tuple[RunInputTraceItem, ...]:
        """返回 trace item 元组。

        :returns: trace item 元组。
        :raises Exception: 不主动抛出异常。
        """

        return tuple(self._items)

    def include(
        self,
        *,
        kind: RunInputTraceItemKind,
        source_id: str,
        text: str,
        provenance: MemoryProvenance,
    ) -> None:
        """尝试写入带溯源的 memory block item。

        :param kind: trace item 类型。
        :param source_id: 来源 item id。
        :param text: 要写入的文本。
        :param provenance: 溯源元数据。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        if not self._has_budget_for(text):
            self._items.append(
                _trace_item(
                    status=RunInputTraceStatus.EXCLUDED,
                    kind=kind,
                    source_id=source_id,
                    provenance=provenance,
                    source_run_id=None,
                    source_event_cursor=None,
                    reason=_TRACE_REASON_BUDGET_EXHAUSTED,
                    text=text,
                )
            )
            return
        self._parts.append(text)
        self._used_chars += len(text)
        self._items.append(
            _trace_item(
                status=RunInputTraceStatus.INCLUDED,
                kind=kind,
                source_id=source_id,
                provenance=provenance,
                source_run_id=None,
                source_event_cursor=None,
                reason=_TRACE_REASON_INCLUDED,
                text=text,
            )
        )

    def include_without_provenance(
        self,
        *,
        kind: RunInputTraceItemKind,
        source_id: str,
        text: str,
    ) -> None:
        """尝试写入无来源事件的 memory block item。

        :param kind: trace item 类型。
        :param source_id: 来源 item id。
        :param text: 要写入的文本。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        if not self._has_budget_for(text):
            self._items.append(
                _trace_item(
                    status=RunInputTraceStatus.EXCLUDED,
                    kind=kind,
                    source_id=source_id,
                    provenance=None,
                    source_run_id=None,
                    source_event_cursor=None,
                    reason=_TRACE_REASON_BUDGET_EXHAUSTED,
                    text=text,
                )
            )
            return
        self._parts.append(text)
        self._used_chars += len(text)
        self._items.append(
            _trace_item(
                status=RunInputTraceStatus.INCLUDED,
                kind=kind,
                source_id=source_id,
                provenance=None,
                source_run_id=None,
                source_event_cursor=None,
                reason=_TRACE_REASON_INCLUDED,
                text=text,
            )
        )

    def include_stable_without_provenance(
        self,
        *,
        kind: RunInputTraceItemKind,
        source_id: str,
        text: str,
    ) -> None:
        """预算外写入 stable memory block item。

        pinned state / stable frame 是运行态稳定层，不参与历史 pool 预算竞争。

        :param kind: trace item 类型。
        :param source_id: 来源 item id。
        :param text: 要写入的文本。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self._parts.append(text)
        self._items.append(
            _trace_item(
                status=RunInputTraceStatus.INCLUDED,
                kind=kind,
                source_id=source_id,
                provenance=None,
                source_run_id=None,
                source_event_cursor=None,
                reason=_TRACE_REASON_INCLUDED,
                text=text,
            )
        )

    def include_stable(
        self,
        *,
        kind: RunInputTraceItemKind,
        source_id: str,
        text: str,
        provenance: MemoryProvenance,
    ) -> None:
        """预算外写入带溯源的 stable memory block item。

        verified claims / assumptions 属于稳定事实层，不参与历史 pool
        预算竞争；它们仍会在 trace 中保留来源 cursor。

        :param kind: trace item 类型。
        :param source_id: 来源 item id。
        :param text: 要写入的文本。
        :param provenance: 溯源元数据。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self._parts.append(text)
        self._items.append(
            _trace_item(
                status=RunInputTraceStatus.INCLUDED,
                kind=kind,
                source_id=source_id,
                provenance=provenance,
                source_run_id=None,
                source_event_cursor=None,
                reason=_TRACE_REASON_INCLUDED,
                text=text,
            )
        )

    def reserve(
        self,
        *,
        kind: RunInputTraceItemKind,
        source_id: str,
        text: str,
        provenance: MemoryProvenance,
    ) -> bool:
        """按预算预留一个稍后渲染的 memory item。

        该方法用于 older pool：预算消费按新到旧进行，但最终文本可再按
        时间顺序渲染，保持模型可读性。

        :param kind: trace item 类型。
        :param source_id: 来源 item id。
        :param text: 要写入的文本。
        :param provenance: 溯源元数据。
        :returns: 预留成功返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        if not self._has_budget_for(text):
            self._items.append(
                _trace_item(
                    status=RunInputTraceStatus.EXCLUDED,
                    kind=kind,
                    source_id=source_id,
                    provenance=provenance,
                    source_run_id=None,
                    source_event_cursor=None,
                    reason=_TRACE_REASON_BUDGET_EXHAUSTED,
                    text=text,
                )
            )
            return False
        self._used_chars += len(text)
        self._items.append(
            _trace_item(
                status=RunInputTraceStatus.INCLUDED,
                kind=kind,
                source_id=source_id,
                provenance=provenance,
                source_run_id=None,
                source_event_cursor=None,
                reason=_TRACE_REASON_INCLUDED,
                text=text,
            )
        )
        return True

    def append_reserved_text(self, text: str) -> None:
        """追加已预留预算的文本。

        :param text: 已预留的 memory 文本。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self._parts.append(text)

    def exclude(
        self,
        *,
        kind: RunInputTraceItemKind,
        source_id: str,
        text: str,
        provenance: MemoryProvenance,
        reason: str,
    ) -> None:
        """记录被语义降级或裁剪的 item。

        :param kind: trace item 类型。
        :param source_id: 来源 item id。
        :param text: 原文本。
        :param provenance: 溯源元数据。
        :param reason: 裁剪原因。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        self._items.append(
            _trace_item(
                status=RunInputTraceStatus.EXCLUDED,
                kind=kind,
                source_id=source_id,
                provenance=provenance,
                source_run_id=None,
                source_event_cursor=None,
                reason=reason,
                text=text,
            )
        )

    def render(self) -> str:
        """渲染 memory block。

        :returns: memory block 文本。
        :raises Exception: 不主动抛出异常。
        """

        if not self._parts:
            return "## Host Memory\n当前 session 没有可注入 memory。"
        return "## Host Memory\n" + "\n\n".join(self._parts)

    def _has_budget_for(self, text: str) -> bool:
        """判断剩余预算是否足够。

        :param text: 候选文本。
        :returns: 足够返回 ``True``。
        :raises Exception: 不主动抛出异常。
        """

        return self._used_chars + len(text) <= self.char_budget


def _current_user_text(event: RunEvent) -> str:
    """从当前用户输入事件读取正文。

    :param event: 当前 run 已 append 的用户输入事件。
    :returns: 用户输入正文。
    :raises TypeError: 当前事件 data 类型不匹配时抛出。
    :raises ValueError: 当前事件不是 canonical Host 用户输入事件时抛出。
    """

    if event.type is not RunEventType.USER_INPUT_ACCEPTED:
        raise ValueError("current user event must be USER_INPUT_ACCEPTED")
    if event.kind is not RunEventKind.CANONICAL:
        raise ValueError("current user event must be canonical")
    if event.source is not RunEventSource.HOST:
        raise ValueError("current user event must be Host-owned")
    data = event.data
    if not isinstance(data, UserInputAcceptedData):
        raise TypeError("USER_INPUT_ACCEPTED data must be UserInputAcceptedData")
    return data.content


def _append_stable_frame(
    *, collector: _MemoryBlockCollector, snapshot: ConversationMemorySnapshot
) -> None:
    """写入 stable frame section。

    :param collector: memory block 收集器。
    :param snapshot: memory 快照。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    frame = snapshot.task_frame
    text = (
        "## Stable Frame\n"
        f"topic_ref={frame.topic_ref}; "
        f"entity_refs={','.join(frame.entity_refs)}; "
        f"period_refs={','.join(frame.period_refs)}; "
        f"basis_refs={','.join(frame.basis_refs)}; "
        f"unit_ref={frame.unit_ref}; "
        f"user_preference_profile_ref={snapshot.user_preference_ref.profile_id}"
    )
    collector.include_stable_without_provenance(
        kind=RunInputTraceItemKind.STABLE_FRAME,
        source_id="stable_frame",
        text=text,
    )


def _append_pinned_state(
    *, collector: _MemoryBlockCollector, snapshot: ConversationMemorySnapshot
) -> None:
    """写入 pinned state section。

    :param collector: memory block 收集器。
    :param snapshot: memory 快照。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    pinned = snapshot.pinned_state
    text = (
        "## Pinned State\n"
        f"current_goal={pinned.current_goal}; "
        f"confirmed_subjects={'; '.join(pinned.confirmed_subjects)}; "
        f"user_constraints={'; '.join(pinned.user_constraints)}; "
        f"open_questions={'; '.join(pinned.open_questions)}"
    )
    collector.include_stable_without_provenance(
        kind=RunInputTraceItemKind.PINNED_STATE,
        source_id="pinned_state",
        text=text,
    )


def _append_verified_claims(
    *, collector: _MemoryBlockCollector, snapshot: ConversationMemorySnapshot
) -> None:
    """写入 verified claims section。

    :param collector: memory block 收集器。
    :param snapshot: memory 快照。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if not snapshot.verified_claims:
        collector.include_stable_without_provenance(
            kind=RunInputTraceItemKind.VERIFIED_CLAIM,
            source_id="verified_claims_empty",
            text="## Verified Claims\n无已验证 claim。",
        )
        return
    for claim in snapshot.verified_claims:
        collector.include_stable(
            kind=RunInputTraceItemKind.VERIFIED_CLAIM,
            source_id=claim.claim_id,
            text=_format_claim(claim),
            provenance=claim.provenance,
        )


def _append_assumptions(
    *, collector: _MemoryBlockCollector, snapshot: ConversationMemorySnapshot
) -> None:
    """写入 assumptions section。

    :param collector: memory block 收集器。
    :param snapshot: memory 快照。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if not snapshot.assumptions.claims:
        collector.include_stable_without_provenance(
            kind=RunInputTraceItemKind.ASSUMPTION,
            source_id="assumptions_empty",
            text="## Assumptions\n无未验证假设。",
        )
        return
    for claim in snapshot.assumptions.claims:
        collector.include_stable(
            kind=RunInputTraceItemKind.ASSUMPTION,
            source_id=claim.claim_id,
            text=_format_assumption(claim),
            provenance=claim.provenance,
        )


def _append_evidence_anchors(
    *, collector: _MemoryBlockCollector, snapshot: ConversationMemorySnapshot
) -> None:
    """写入 evidence anchors 与 tool facts section。

    :param collector: memory block 收集器。
    :param snapshot: memory 快照。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if not snapshot.evidence_anchors and not snapshot.tool_facts:
        collector.include_without_provenance(
            kind=RunInputTraceItemKind.EVIDENCE_ANCHOR,
            source_id="evidence_anchors_empty",
            text="## Evidence Anchors\n无证据锚点或工具事实。",
        )
        return
    for anchor in snapshot.evidence_anchors:
        collector.include(
            kind=RunInputTraceItemKind.EVIDENCE_ANCHOR,
            source_id=anchor.anchor_id,
            text=_format_anchor(anchor),
            provenance=anchor.provenance,
        )
    for fact in snapshot.tool_facts:
        collector.include(
            kind=RunInputTraceItemKind.TOOL_FACT,
            source_id=fact.fact_id,
            text=_format_tool_fact(fact),
            provenance=fact.provenance,
        )


def _append_recent_raw_turns(
    *, collector: _MemoryBlockCollector, snapshot: ConversationMemorySnapshot
) -> None:
    """写入 recent raw turns section。

    超大旧轮只注入语义摘要，并在 trace 中记录被降级的原始 item，避免
    recent floor 变成无限 token 保底。

    :param collector: memory block 收集器。
    :param snapshot: memory 快照。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if not snapshot.recent_raw_turns:
        collector.include_without_provenance(
            kind=RunInputTraceItemKind.RECENT_RAW_TURN,
            source_id="recent_raw_turns_empty",
            text="## Recent Raw Turns\n无最近会话轮次。",
        )
        return
    for turn in snapshot.recent_raw_turns:
        text = summarize_raw_turn_for_builder(turn)
        source_text = _raw_turn_source_text(turn)
        if len(source_text) > _RECENT_TURN_INLINE_CHAR_LIMIT:
            collector.exclude(
                kind=RunInputTraceItemKind.RECENT_RAW_TURN,
                source_id=turn.turn_id,
                text=source_text,
                provenance=turn.user_provenance,
                reason=_TRACE_REASON_RECENT_TURN_DOWNGRADED,
            )
        collector.include(
            kind=RunInputTraceItemKind.RECENT_RAW_TURN,
            source_id=turn.turn_id,
            text=f"## Recent Raw Turns\n{text}",
            provenance=turn.user_provenance,
        )


def _append_older_raw_turns(
    *, collector: _MemoryBlockCollector, snapshot: ConversationMemorySnapshot
) -> None:
    """写入 older pool section。

    :param collector: memory block 收集器。
    :param snapshot: memory 快照。
    :returns: 无返回值。
    :raises Exception: 不主动抛出异常。
    """

    if not snapshot.older_raw_turns:
        collector.include_without_provenance(
            kind=RunInputTraceItemKind.OLDER_RAW_TURN,
            source_id="older_pool_empty",
            text="## Older Pool\n无更早会话池。",
        )
        return
    selected_texts: list[str] = []
    for turn in reversed(snapshot.older_raw_turns):
        source_text = _raw_turn_source_text(turn)
        collector.exclude(
            kind=RunInputTraceItemKind.OLDER_RAW_TURN,
            source_id=turn.turn_id,
            text=source_text,
            provenance=turn.user_provenance,
            reason=_TRACE_REASON_OLDER_TURN_SUMMARIZED,
        )
        text = (
            "## Older Pool\n"
            + _truncate_text(
                text=summarize_raw_turn_for_builder(turn),
                limit=_OLDER_TURN_INLINE_CHAR_LIMIT,
            )
        )
        if collector.reserve(
            kind=RunInputTraceItemKind.OLDER_RAW_TURN,
            source_id=turn.turn_id,
            text=text,
            provenance=turn.user_provenance,
        ):
            selected_texts.append(text)
    for text in reversed(selected_texts):
        collector.append_reserved_text(text)


def _format_claim(claim: MemoryClaim) -> str:
    """格式化 claim。

    :param claim: Memory claim。
    :returns: claim 文本。
    :raises Exception: 不主动抛出异常。
    """

    return (
        "## Verified Claims\n"
        f"claim_id={claim.claim_id}; status={claim.status.value}; "
        f"scope={claim.scope.value}; evidence_anchor_id={claim.evidence_anchor_id}; "
        f"text={claim.text}"
    )


def _format_assumption(claim: MemoryClaim) -> str:
    """格式化 assumption claim。

    :param claim: Memory claim。
    :returns: assumption 文本。
    :raises Exception: 不主动抛出异常。
    """

    return (
        "## Assumptions\n"
        f"claim_id={claim.claim_id}; status={claim.status.value}; "
        f"scope={claim.scope.value}; evidence_anchor_id={claim.evidence_anchor_id}; "
        f"text={claim.text}"
    )


def _format_anchor(anchor: EvidenceAnchor) -> str:
    """格式化证据锚点。

    :param anchor: 证据锚点。
    :returns: 证据锚点文本。
    :raises Exception: 不主动抛出异常。
    """

    return (
        "## Evidence Anchors\n"
        f"anchor_id={anchor.anchor_id}; tool_call_id={anchor.tool_call_id}; "
        f"source_event_cursor={anchor.origin_event_cursor.sequence}; "
        f"source_ref={anchor.source_ref}; chunk_ref={anchor.chunk_ref}; "
        f"fingerprint={anchor.fingerprint}; summary={anchor.summary}"
    )


def _format_tool_fact(fact: ConversationToolFact) -> str:
    """格式化工具事实。

    :param fact: 工具事实。
    :returns: 工具事实文本。
    :raises Exception: 不主动抛出异常。
    """

    return (
        "## Evidence Anchors\n"
        f"tool_fact_id={fact.fact_id}; tool_name={fact.tool_name}; "
        f"tool_call_id={fact.tool_call_id}; event_type={fact.event_type.value}; "
        f"source_event_cursor={fact.provenance.source_event_cursor.sequence}; "
        f"cursor_fingerprint={fact.cursor_fingerprint}; "
        f"has_more={fact.has_more}; summary={fact.summary}"
    )


def _raw_turn_source_text(turn: ConversationRawTurn) -> str:
    """返回 raw turn 原始文本拼接。

    :param turn: raw turn。
    :returns: 原始文本拼接。
    :raises Exception: 不主动抛出异常。
    """

    parts = [turn.user_text]
    if turn.assistant_final is not None:
        parts.append(turn.assistant_final)
    if turn.terminal_summary is not None:
        parts.append(turn.terminal_summary)
    return "\n".join(parts)


def _trace_item(
    *,
    status: RunInputTraceStatus,
    kind: RunInputTraceItemKind,
    source_id: str,
    provenance: MemoryProvenance | None,
    source_run_id: str | None,
    source_event_cursor: int | None,
    reason: str,
    text: str,
) -> RunInputTraceItem:
    """构造 trace item。

    :param status: included / excluded 状态。
    :param kind: item 类型。
    :param source_id: 来源 item id。
    :param provenance: memory 溯源；无时使用显式来源字段。
    :param source_run_id: 显式来源 run id。
    :param source_event_cursor: 显式来源 cursor sequence。
    :param reason: included 或裁剪原因。
    :param text: 参与估算的文本。
    :returns: trace item。
    :raises Exception: 不主动抛出异常。
    """

    resolved_run_id = (
        source_run_id if provenance is None else provenance.source_run_id
    )
    resolved_cursor = (
        source_event_cursor
        if provenance is None
        else provenance.source_event_cursor.sequence
    )
    char_size = len(text)
    return RunInputTraceItem(
        status=status,
        item_kind=kind,
        source_id=source_id,
        source_run_id=resolved_run_id,
        source_event_cursor=resolved_cursor,
        reason=reason,
        char_size=char_size,
        token_estimate=_estimate_tokens(char_size),
    )


def _truncate_text(*, text: str, limit: int) -> str:
    """按字符数截断文本。

    :param text: 原文本。
    :param limit: 最大字符数。
    :returns: 截断后的文本。
    :raises Exception: 不主动抛出异常。
    """

    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "...[已裁剪]"


def _estimate_tokens(char_size: int) -> int:
    """用字符数估算 token 数。

    :param char_size: 字符数。
    :returns: 估算 token 数。
    :raises Exception: 不主动抛出异常。
    """

    if char_size <= 0:
        return 0
    return (char_size + _APPROX_TOKEN_CHARS - 1) // _APPROX_TOKEN_CHARS


__all__ = [
    "DefaultRunInputBuilder",
    "RunInputBuildResult",
    "RunInputBuildTrace",
    "RunInputBuilder",
    "RunInputTraceItem",
    "RunInputTraceItemKind",
    "RunInputTraceStatus",
]
