"""Host 内部 Conversation Memory 投影。

本模块只从 canonical ``RunEvent`` 投影运行态 memory snapshot，服务 P3
单进程顺序多轮输入构造。它不提供 public API，不实现持久化治理，也不
理解财报业务语义；证据、claim、任务框架均以 Host 中立结构承载。
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Protocol, TypeAlias

from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolFailedOutcome,
)
from dayu.engine import FinalAnswerData, ToolResultAcceptedData
from dayu.host.contracts import (
    HostRunFailedData,
    RunEvent,
    RunEventCursor,
    RunEventKind,
    RunEventType,
    ToolCursorDeniedData,
    ToolCursorExpiredData,
    ToolCursorIssuedData,
    ToolFetchMoreCompletedData,
    ToolFetchMoreFailedData,
    ToolFetchMoreRequestedData,
    ToolResultTruncatedData,
    UserInputAcceptedData,
    UserInputScope,
)

_EMPTY_TEXT: str = ""
_USER_TEXT_SUMMARY_LIMIT: int = 240
_ASSISTANT_TEXT_SUMMARY_LIMIT: int = 240
_TERMINAL_TEXT_SUMMARY_LIMIT: int = 240
_TOOL_FACT_SUMMARY_LIMIT: int = 360


class MemoryScope(StrEnum):
    """Memory 可见范围。

    P3 只实际写入 ``SESSION``，其余成员用于固定后续 direct / group /
    project / user 扩展位。
    """

    SESSION = "session"
    DIRECT_USER = "direct_user"
    GROUP = "group"
    PROJECT = "project"
    USER = "user"


class MemoryProducerKind(StrEnum):
    """Memory item 生产者类型。"""

    HOST_USER_INPUT = "host_user_input"
    ENGINE_FINAL_ANSWER = "engine_final_answer"
    ENGINE_TOOL_FACT = "engine_tool_fact"
    HOST_TOOL_RUNTIME = "host_tool_runtime"
    HOST_PROJECTION = "host_projection"
    USER_CORRECTION = "user_correction"


class MemoryIngestionPolicy(StrEnum):
    """Memory 摄取策略。"""

    PRIMARY_SESSION_CANONICAL = "primary_session_canonical"
    TOOL_FACT_CANONICAL = "tool_fact_canonical"
    EVIDENCE_BACKED_PROJECTION = "evidence_backed_projection"
    USER_CONFIRMED_CORRECTION = "user_confirmed_correction"
    DISPLAY_ONLY_EXCLUDED = "display_only_excluded"


class MemoryTrustLevel(StrEnum):
    """Memory 信任等级。"""

    USER_PROVIDED = "user_provided"
    HOST_OBSERVED = "host_observed"
    TOOL_OBSERVED = "tool_observed"
    EVIDENCE_BACKED = "evidence_backed"
    ASSISTANT_CONCLUSION = "assistant_conclusion"
    ASSUMPTION = "assumption"


class ClaimStatus(StrEnum):
    """Memory claim 状态。"""

    VERIFIED = "verified"
    ASSUMPTION = "assumption"
    ASSISTANT_CONCLUSION = "assistant_conclusion"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class MemoryProvenance:
    """Memory item 溯源元数据。

    :param source_run_id: 来源 run id。
    :param source_event_cursor: 来源 RunEvent cursor。
    :param producer_kind: 生产者类型。
    :param ingestion_policy: 摄取策略。
    :param scope: 可见范围。
    :param trust_level: 信任等级。
    """

    source_run_id: str
    source_event_cursor: RunEventCursor
    producer_kind: MemoryProducerKind
    ingestion_policy: MemoryIngestionPolicy
    scope: MemoryScope
    trust_level: MemoryTrustLevel


@dataclass(frozen=True, slots=True)
class EvidenceAnchor:
    """Host 中立证据锚点。

    :param anchor_id: 证据锚点 id。
    :param origin_event_cursor: 来源事件 cursor。
    :param tool_call_id: 可选工具调用 id。
    :param source_ref: opaque 来源引用。
    :param chunk_ref: opaque 分块引用。
    :param fingerprint: 中性指纹。
    :param summary: 人类可读中性摘要。
    :param provenance: 溯源元数据。
    """

    anchor_id: str
    origin_event_cursor: RunEventCursor
    tool_call_id: str | None
    source_ref: str | None
    chunk_ref: str | None
    fingerprint: str | None
    summary: str
    provenance: MemoryProvenance


@dataclass(frozen=True, slots=True)
class MemoryClaim:
    """Host 中立事实或结论条目。

    :param claim_id: claim id。
    :param status: claim 状态。
    :param text: 中性事实文本。
    :param source_run_id: 来源 run id。
    :param source_event_cursor: 来源事件 cursor。
    :param evidence_anchor_id: 可选证据锚点 id。
    :param scope: 可见范围。
    :param created_at: 创建时间。
    :param supersedes: 被本 claim 替代的 claim id 元组。
    :param provenance: 溯源元数据。
    """

    claim_id: str
    status: ClaimStatus
    text: str
    source_run_id: str
    source_event_cursor: RunEventCursor
    evidence_anchor_id: str | None
    scope: MemoryScope
    created_at: datetime
    supersedes: tuple[str, ...]
    provenance: MemoryProvenance


@dataclass(frozen=True, slots=True)
class TaskFrame:
    """当前任务框架槽位。

    :param topic_ref: opaque 主题引用。
    :param entity_refs: opaque 实体引用元组。
    :param period_refs: opaque 期间引用元组。
    :param basis_refs: opaque 口径或比较基准引用元组。
    :param unit_ref: opaque 单位引用。
    """

    topic_ref: str | None = None
    entity_refs: tuple[str, ...] = ()
    period_refs: tuple[str, ...] = ()
    basis_refs: tuple[str, ...] = ()
    unit_ref: str | None = None


@dataclass(frozen=True, slots=True)
class ConversationPinnedState:
    """跨轮稳定 pinned 状态。

    :param current_goal: 当前会话目标；未知时为 ``None``。
    :param confirmed_subjects: 用户已确认对象或主题。
    :param user_constraints: 用户明确约束。
    :param open_questions: 仍待回答或待澄清问题。
    """

    current_goal: str | None = None
    confirmed_subjects: tuple[str, ...] = ()
    user_constraints: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AssumptionRegister:
    """未验证假设登记簿。

    :param claims: 处于 assumption 状态的 claim 元组。
    """

    claims: tuple[MemoryClaim, ...] = ()


@dataclass(frozen=True, slots=True)
class UserPreferenceProfileRef:
    """用户偏好画像引用槽位。

    :param profile_id: opaque 偏好画像 id。
    :param scope: 偏好适用范围。
    """

    profile_id: str | None = None
    scope: MemoryScope = MemoryScope.SESSION


@dataclass(frozen=True, slots=True)
class ConversationRawTurn:
    """可回放的会话 raw turn。

    :param turn_id: turn id。
    :param user_text: 用户输入正文。
    :param assistant_final: 助手最终回答；未成功终态时为 ``None``。
    :param user_provenance: 用户输入溯源。
    :param assistant_provenance: 助手最终回答溯源；不存在时为 ``None``。
    :param terminal_summary: 非成功终态中性摘要；没有时为 ``None``。
    :param terminal_provenance: 非成功终态溯源；不存在时为 ``None``。
    """

    turn_id: str
    user_text: str
    assistant_final: str | None
    user_provenance: MemoryProvenance
    assistant_provenance: MemoryProvenance | None
    terminal_summary: str | None = None
    terminal_provenance: MemoryProvenance | None = None


@dataclass(frozen=True, slots=True)
class ConversationToolFact:
    """工具事实摘要。

    :param fact_id: tool fact id。
    :param tool_name: 工具名。
    :param tool_call_id: 工具调用 id。
    :param event_type: 来源事件类型。
    :param summary: 中性摘要。
    :param cursor_fingerprint: cursor 指纹；没有 cursor 时为 ``None``。
    :param has_more: 是否还有更多数据；未知时为 ``None``。
    :param provenance: 溯源元数据。
    """

    fact_id: str
    tool_name: str
    tool_call_id: str
    event_type: RunEventType
    summary: str
    cursor_fingerprint: str | None
    has_more: bool | None
    provenance: MemoryProvenance


@dataclass(frozen=True, slots=True)
class ConversationMemorySnapshot:
    """某个 session 的 memory 快照。

    :param session_id: 会话 id。
    :param pinned_state: 跨轮稳定 pinned 状态。
    :param task_frame: 当前任务框架。
    :param verified_claims: 已验证 claim ledger。
    :param assumptions: 假设登记簿。
    :param evidence_anchors: 证据锚点元组。
    :param recent_raw_turns: 最近 raw turn 元组。
    :param older_raw_turns: 更早 raw turn 元组。
    :param tool_facts: 工具事实摘要元组。
    :param user_preference_ref: 用户偏好画像引用槽位。
    """

    session_id: str
    pinned_state: ConversationPinnedState
    task_frame: TaskFrame
    verified_claims: tuple[MemoryClaim, ...]
    assumptions: AssumptionRegister
    evidence_anchors: tuple[EvidenceAnchor, ...]
    recent_raw_turns: tuple[ConversationRawTurn, ...]
    older_raw_turns: tuple[ConversationRawTurn, ...]
    tool_facts: tuple[ConversationToolFact, ...]
    user_preference_ref: UserPreferenceProfileRef


@dataclass(frozen=True, slots=True)
class MemoryResetPatch:
    """internal-only memory reset patch 形状。

    :param session_id: 目标 session id。
    :param scope: 清理范围。
    :param reason: 中性原因。
    """

    session_id: str
    scope: MemoryScope
    reason: str


@dataclass(frozen=True, slots=True)
class ClaimCorrectionPatch:
    """internal-only claim correction patch 形状。

    :param session_id: 目标 session id。
    :param corrected_claim: 用户确认后的修正 claim。
    :param reason: 中性原因。
    """

    session_id: str
    corrected_claim: MemoryClaim
    reason: str


@dataclass(frozen=True, slots=True)
class ScopeClearPatch:
    """internal-only scope clear patch 形状。

    :param session_id: 目标 session id。
    :param scope: 要清理的 scope。
    :param reason: 中性原因。
    """

    session_id: str
    scope: MemoryScope
    reason: str


ConversationMemoryPatch: TypeAlias = (
    MemoryResetPatch | ClaimCorrectionPatch | ScopeClearPatch
)
"""Conversation memory internal patch 封闭联合。"""


class ConversationMemoryStore(Protocol):
    """Host 内部 ConversationMemoryStore 协议。"""

    async def project_run_events(self, events: tuple[RunEvent, ...]) -> None:
        """从已落库 RunEvent 投影 memory。

        :param events: 同一 run 的 RunEvent 元组。
        :returns: 无返回值。
        :raises Exception: 具体实现投影失败时透传。
        """
        ...

    async def get_snapshot(self, session_id: str) -> ConversationMemorySnapshot:
        """读取 session memory 快照。

        :param session_id: 会话 id。
        :returns: memory 快照。
        :raises Exception: 具体实现读取失败时透传。
        """
        ...

    async def apply_patch(self, patch: ConversationMemoryPatch) -> None:
        """应用 internal-only memory patch。

        :param patch: memory patch。
        :returns: 无返回值。
        :raises Exception: 具体实现应用失败时透传。
        """
        ...


@dataclass(slots=True)
class InMemoryConversationMemoryStore:
    """单进程内存态 ConversationMemoryStore。

    :param recent_turn_limit: recent raw turn 保留数量。
    """

    recent_turn_limit: int = 4
    _snapshot_by_session: dict[str, ConversationMemorySnapshot] = field(
        default_factory=dict,
        init=False,
    )

    async def project_run_events(self, events: tuple[RunEvent, ...]) -> None:
        """从同一 run 的已落库事件投影 memory。

        只消费 canonical RunEvent；preview、reasoning delta 与 display-only
        事件不会进入 memory pool。

        :param events: 同一 run 的 RunEvent 元组。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        if not events:
            return
        canonical_events = tuple(
            event for event in events if event.kind is RunEventKind.CANONICAL
        )
        if not canonical_events:
            return
        session_id = canonical_events[0].session_id
        snapshot = self._snapshot_by_session.get(
            session_id, _empty_snapshot(session_id)
        )
        snapshot = _project_canonical_events(
            snapshot=snapshot,
            events=canonical_events,
            recent_turn_limit=self.recent_turn_limit,
        )
        self._snapshot_by_session[session_id] = snapshot

    async def get_snapshot(self, session_id: str) -> ConversationMemorySnapshot:
        """读取 session memory 快照。

        :param session_id: 会话 id。
        :returns: memory 快照；不存在时返回空快照。
        :raises Exception: 不主动抛出异常。
        """

        return self._snapshot_by_session.get(
            session_id, _empty_snapshot(session_id)
        )

    async def apply_patch(self, patch: ConversationMemoryPatch) -> None:
        """应用 internal-only memory patch。

        P3 只实现最小内存态形状：reset / scope clear 会清空 session scope，
        claim correction 只接纳用户确认的修正 claim。

        :param patch: memory patch。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        match patch:
            case MemoryResetPatch(session_id=session_id):
                self._snapshot_by_session[session_id] = _empty_snapshot(
                    session_id
                )
            case ScopeClearPatch(
                session_id=session_id, scope=MemoryScope.SESSION
            ):
                self._snapshot_by_session[session_id] = _empty_snapshot(
                    session_id
                )
            case ScopeClearPatch():
                return
            case ClaimCorrectionPatch(
                session_id=session_id, corrected_claim=claim
            ):
                snapshot = self._snapshot_by_session.get(
                    session_id, _empty_snapshot(session_id)
                )
                self._snapshot_by_session[session_id] = replace(
                    snapshot,
                    verified_claims=snapshot.verified_claims + (claim,),
                )


def _empty_snapshot(session_id: str) -> ConversationMemorySnapshot:
    """构造空 memory 快照。

    :param session_id: 会话 id。
    :returns: 空快照。
    :raises Exception: 不主动抛出异常。
    """

    return ConversationMemorySnapshot(
        session_id=session_id,
        pinned_state=ConversationPinnedState(),
        task_frame=TaskFrame(),
        verified_claims=(),
        assumptions=AssumptionRegister(),
        evidence_anchors=(),
        recent_raw_turns=(),
        older_raw_turns=(),
        tool_facts=(),
        user_preference_ref=UserPreferenceProfileRef(),
    )


def _project_canonical_events(
    *,
    snapshot: ConversationMemorySnapshot,
    events: tuple[RunEvent, ...],
    recent_turn_limit: int,
) -> ConversationMemorySnapshot:
    """从 canonical 事件投影快照。

    :param snapshot: 旧快照。
    :param events: canonical RunEvent 元组。
    :param recent_turn_limit: recent raw turn 保留数量。
    :returns: 新快照。
    :raises Exception: 不主动抛出异常。
    """

    raw_turn = _project_raw_turn(events)
    tool_facts = _project_tool_facts(events)
    evidence_anchors = tuple(_evidence_anchor_from_fact(fact) for fact in tool_facts)
    all_recent = snapshot.recent_raw_turns
    if raw_turn is not None:
        all_recent = _replace_turn(all_recent, raw_turn)
    older_turns, recent_turns = _split_turns(
        turns=snapshot.older_raw_turns + all_recent,
        recent_turn_limit=recent_turn_limit,
    )
    return replace(
        snapshot,
        recent_raw_turns=recent_turns,
        older_raw_turns=older_turns,
        tool_facts=_merge_tool_facts(snapshot.tool_facts, tool_facts),
        evidence_anchors=_merge_evidence_anchors(
            snapshot.evidence_anchors, evidence_anchors
        ),
    )


def _project_raw_turn(events: tuple[RunEvent, ...]) -> ConversationRawTurn | None:
    """从同一 run 事件投影 raw turn。

    :param events: canonical RunEvent 元组。
    :returns: raw turn；没有用户输入事件时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    user_event: RunEvent | None = None
    final_event: RunEvent | None = None
    host_failure_event: RunEvent | None = None
    for event in events:
        if (
            event.type is RunEventType.USER_INPUT_ACCEPTED
            and isinstance(event.data, UserInputAcceptedData)
        ):
            user_event = event
        elif (
            event.type is RunEventType.FINAL_ANSWER
            and isinstance(event.data, FinalAnswerData)
        ):
            final_event = event
        elif (
            event.type is RunEventType.RUN_FAILED
            and isinstance(event.data, HostRunFailedData)
        ):
            host_failure_event = event
    if user_event is None or not isinstance(
        user_event.data, UserInputAcceptedData
    ):
        return None
    user_scope = scope_from_user_input_event(user_event)
    assistant_text: str | None = None
    assistant_provenance: MemoryProvenance | None = None
    terminal_summary: str | None = None
    terminal_provenance: MemoryProvenance | None = None
    if final_event is not None and isinstance(final_event.data, FinalAnswerData):
        assistant_text = final_event.data.content
        assistant_provenance = _provenance(
            event=final_event,
            producer_kind=MemoryProducerKind.ENGINE_FINAL_ANSWER,
            ingestion_policy=MemoryIngestionPolicy.PRIMARY_SESSION_CANONICAL,
            trust_level=MemoryTrustLevel.ASSISTANT_CONCLUSION,
        )
    elif host_failure_event is not None and isinstance(
        host_failure_event.data, HostRunFailedData
    ):
        terminal_summary = _summarize_host_failure(host_failure_event.data)
        terminal_provenance = _provenance(
            event=host_failure_event,
            producer_kind=MemoryProducerKind.HOST_PROJECTION,
            ingestion_policy=MemoryIngestionPolicy.PRIMARY_SESSION_CANONICAL,
            trust_level=MemoryTrustLevel.HOST_OBSERVED,
        )
    return ConversationRawTurn(
        turn_id=user_event.data.turn_id,
        user_text=user_event.data.content,
        assistant_final=assistant_text,
        terminal_summary=terminal_summary,
        user_provenance=_provenance(
            event=user_event,
            producer_kind=MemoryProducerKind.HOST_USER_INPUT,
            ingestion_policy=MemoryIngestionPolicy.PRIMARY_SESSION_CANONICAL,
            trust_level=MemoryTrustLevel.USER_PROVIDED,
            scope=user_scope,
        ),
        assistant_provenance=assistant_provenance,
        terminal_provenance=terminal_provenance,
    )


def _summarize_host_failure(data: HostRunFailedData) -> str:
    """生成 Host-owned failure 的中性终态摘要。

    :param data: Host-owned run 失败事实。
    :returns: 供下一轮追问连续性使用的中性摘要。
    :raises Exception: 不主动抛出异常。
    """

    return _truncate_text(
        text=(
            f"run_failed: error_code={data.error_code}; "
            f"recoverable={data.recoverable}; "
            f"exception_type={data.exception_type}; message={data.message}"
        ),
        limit=_TERMINAL_TEXT_SUMMARY_LIMIT,
    )


def _project_tool_facts(events: tuple[RunEvent, ...]) -> tuple[ConversationToolFact, ...]:
    """从 canonical 事件投影工具事实摘要。

    :param events: canonical RunEvent 元组。
    :returns: 工具事实摘要元组。
    :raises Exception: 不主动抛出异常。
    """

    facts: list[ConversationToolFact] = []
    for event in events:
        fact = _tool_fact_from_event(event)
        if fact is not None:
            facts.append(fact)
    return tuple(facts)


def _tool_fact_from_event(event: RunEvent) -> ConversationToolFact | None:
    """将单个 canonical 事件转换为工具事实摘要。

    :param event: RunEvent。
    :returns: 工具事实；非工具事实事件返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    data = event.data
    producer_kind = MemoryProducerKind.HOST_TOOL_RUNTIME
    if isinstance(data, ToolResultAcceptedData):
        producer_kind = MemoryProducerKind.ENGINE_TOOL_FACT
        return ConversationToolFact(
            fact_id=_item_id("tool_fact", event),
            tool_name=data.name,
            tool_call_id=data.tool_call_id,
            event_type=event.type,
            summary=_summarize_tool_result(data),
            cursor_fingerprint=None,
            has_more=None,
            provenance=_provenance(
                event=event,
                producer_kind=producer_kind,
                ingestion_policy=MemoryIngestionPolicy.TOOL_FACT_CANONICAL,
                trust_level=MemoryTrustLevel.TOOL_OBSERVED,
            ),
        )
    if isinstance(data, ToolResultTruncatedData):
        return ConversationToolFact(
            fact_id=_item_id("tool_fact", event),
            tool_name=data.tool_name,
            tool_call_id=data.tool_call_id,
            event_type=event.type,
            summary=(
                f"工具结果已截断：strategy={data.strategy}; "
                f"unit={data.unit}; size={data.value_summary.size}; "
                f"total_estimate={data.total_estimate}; has_more={data.has_more}"
            ),
            cursor_fingerprint=data.cursor_fingerprint,
            has_more=data.has_more,
            provenance=_provenance(
                event=event,
                producer_kind=producer_kind,
                ingestion_policy=MemoryIngestionPolicy.TOOL_FACT_CANONICAL,
                trust_level=MemoryTrustLevel.TOOL_OBSERVED,
            ),
        )
    if isinstance(data, ToolCursorIssuedData):
        return ConversationToolFact(
            fact_id=_item_id("tool_fact", event),
            tool_name=data.tool_name,
            tool_call_id=data.tool_call_id,
            event_type=event.type,
            summary=(
                f"工具补读 cursor 已签发：offset={data.offset}; "
                f"limit={data.limit}; total_estimate={data.total_estimate}"
            ),
            cursor_fingerprint=data.cursor_fingerprint,
            has_more=None,
            provenance=_provenance(
                event=event,
                producer_kind=producer_kind,
                ingestion_policy=MemoryIngestionPolicy.TOOL_FACT_CANONICAL,
                trust_level=MemoryTrustLevel.TOOL_OBSERVED,
            ),
        )
    if isinstance(data, ToolFetchMoreRequestedData):
        return ConversationToolFact(
            fact_id=_item_id("tool_fact", event),
            tool_name="unknown",
            tool_call_id=data.tool_call_id,
            event_type=event.type,
            summary=f"工具补读已请求：requested_limit={data.requested_limit}",
            cursor_fingerprint=data.cursor_fingerprint,
            has_more=None,
            provenance=_provenance(
                event=event,
                producer_kind=producer_kind,
                ingestion_policy=MemoryIngestionPolicy.TOOL_FACT_CANONICAL,
                trust_level=MemoryTrustLevel.TOOL_OBSERVED,
            ),
        )
    if isinstance(data, ToolFetchMoreCompletedData):
        return ConversationToolFact(
            fact_id=_item_id("tool_fact", event),
            tool_name=data.tool_name,
            tool_call_id=data.tool_call_id,
            event_type=event.type,
            summary=(
                f"工具补读完成：chunk_size={data.chunk_size}; "
                f"limit={data.limit}; has_more={data.has_more}; "
                f"value_size={data.value_summary.size}"
            ),
            cursor_fingerprint=data.consumed_cursor_fingerprint,
            has_more=data.has_more,
            provenance=_provenance(
                event=event,
                producer_kind=producer_kind,
                ingestion_policy=MemoryIngestionPolicy.TOOL_FACT_CANONICAL,
                trust_level=MemoryTrustLevel.TOOL_OBSERVED,
            ),
        )
    if isinstance(data, ToolFetchMoreFailedData):
        return ConversationToolFact(
            fact_id=_item_id("tool_fact", event),
            tool_name="unknown",
            tool_call_id=data.tool_call_id,
            event_type=event.type,
            summary=f"工具补读失败：error_code={data.error_code}; denied={data.denied}",
            cursor_fingerprint=data.cursor_fingerprint,
            has_more=None,
            provenance=_provenance(
                event=event,
                producer_kind=producer_kind,
                ingestion_policy=MemoryIngestionPolicy.TOOL_FACT_CANONICAL,
                trust_level=MemoryTrustLevel.TOOL_OBSERVED,
            ),
        )
    if isinstance(data, ToolCursorExpiredData):
        return ConversationToolFact(
            fact_id=_item_id("tool_fact", event),
            tool_name="unknown",
            tool_call_id=data.tool_call_id,
            event_type=event.type,
            summary="工具补读 cursor 已过期",
            cursor_fingerprint=data.cursor_fingerprint,
            has_more=None,
            provenance=_provenance(
                event=event,
                producer_kind=producer_kind,
                ingestion_policy=MemoryIngestionPolicy.TOOL_FACT_CANONICAL,
                trust_level=MemoryTrustLevel.TOOL_OBSERVED,
            ),
        )
    if isinstance(data, ToolCursorDeniedData):
        return ConversationToolFact(
            fact_id=_item_id("tool_fact", event),
            tool_name="unknown",
            tool_call_id=data.tool_call_id,
            event_type=event.type,
            summary=f"工具补读 cursor 被拒绝：reason={data.reason}",
            cursor_fingerprint=data.cursor_fingerprint,
            has_more=None,
            provenance=_provenance(
                event=event,
                producer_kind=producer_kind,
                ingestion_policy=MemoryIngestionPolicy.TOOL_FACT_CANONICAL,
                trust_level=MemoryTrustLevel.TOOL_OBSERVED,
            ),
        )
    return None


def _summarize_tool_result(data: ToolResultAcceptedData) -> str:
    """摘要 Engine 已接纳工具结果。

    :param data: Engine 工具结果事件 data。
    :returns: 中性工具结果摘要。
    :raises Exception: 不主动抛出异常。
    """

    outcome = data.outcome
    if isinstance(outcome, ToolCompletedOutcome):
        value_text = repr(outcome.result.value)
        return _truncate_text(
            text=f"工具结果已接纳：value={value_text}",
            limit=_TOOL_FACT_SUMMARY_LIMIT,
        )
    if isinstance(outcome, ToolFailedOutcome):
        return _truncate_text(
            text=(
                f"工具结果失败：error={outcome.result.error}; "
                f"message={outcome.result.message}"
            ),
            limit=_TOOL_FACT_SUMMARY_LIMIT,
        )
    return "工具结果已接纳"


def _evidence_anchor_from_fact(fact: ConversationToolFact) -> EvidenceAnchor:
    """从工具事实生成中立证据锚点。

    :param fact: 工具事实摘要。
    :returns: 证据锚点。
    :raises Exception: 不主动抛出异常。
    """

    return EvidenceAnchor(
        anchor_id=f"anchor:{fact.fact_id}",
        origin_event_cursor=fact.provenance.source_event_cursor,
        tool_call_id=fact.tool_call_id,
        source_ref=f"tool:{fact.tool_name}",
        chunk_ref=None,
        fingerprint=fact.cursor_fingerprint,
        summary=fact.summary,
        provenance=fact.provenance,
    )


def _provenance(
    *,
    event: RunEvent,
    producer_kind: MemoryProducerKind,
    ingestion_policy: MemoryIngestionPolicy,
    trust_level: MemoryTrustLevel,
    scope: MemoryScope = MemoryScope.SESSION,
) -> MemoryProvenance:
    """从 RunEvent 构造 memory 溯源。

    :param event: 来源 RunEvent。
    :param producer_kind: 生产者类型。
    :param ingestion_policy: 摄取策略。
    :param trust_level: 信任等级。
    :param scope: memory 可见范围。
    :returns: MemoryProvenance。
    :raises Exception: 不主动抛出异常。
    """

    return MemoryProvenance(
        source_run_id=event.run_id,
        source_event_cursor=event.cursor,
        producer_kind=producer_kind,
        ingestion_policy=ingestion_policy,
        scope=scope,
        trust_level=trust_level,
    )


def _replace_turn(
    turns: tuple[ConversationRawTurn, ...],
    raw_turn: ConversationRawTurn,
) -> tuple[ConversationRawTurn, ...]:
    """按 turn id 替换或追加 raw turn。

    :param turns: 原 raw turn 元组。
    :param raw_turn: 新 raw turn。
    :returns: 更新后的 raw turn 元组。
    :raises Exception: 不主动抛出异常。
    """

    kept = tuple(turn for turn in turns if turn.turn_id != raw_turn.turn_id)
    return kept + (raw_turn,)


def _split_turns(
    *,
    turns: tuple[ConversationRawTurn, ...],
    recent_turn_limit: int,
) -> tuple[tuple[ConversationRawTurn, ...], tuple[ConversationRawTurn, ...]]:
    """将 raw turn 拆分为 older / recent。

    :param turns: 全部 raw turn。
    :param recent_turn_limit: recent 保留数量。
    :returns: ``(older, recent)``。
    :raises Exception: 不主动抛出异常。
    """

    if recent_turn_limit <= 0:
        return turns, ()
    if len(turns) <= recent_turn_limit:
        return (), turns
    return turns[:-recent_turn_limit], turns[-recent_turn_limit:]


def _merge_tool_facts(
    old_facts: tuple[ConversationToolFact, ...],
    new_facts: tuple[ConversationToolFact, ...],
) -> tuple[ConversationToolFact, ...]:
    """合并工具事实并按 fact id 去重。

    :param old_facts: 旧工具事实。
    :param new_facts: 新工具事实。
    :returns: 合并后的工具事实。
    :raises Exception: 不主动抛出异常。
    """

    merged: list[ConversationToolFact] = []
    seen: set[str] = set()
    for fact in old_facts + new_facts:
        if fact.fact_id in seen:
            continue
        seen.add(fact.fact_id)
        merged.append(fact)
    return tuple(merged)


def _merge_evidence_anchors(
    old_anchors: tuple[EvidenceAnchor, ...],
    new_anchors: tuple[EvidenceAnchor, ...],
) -> tuple[EvidenceAnchor, ...]:
    """合并证据锚点并按 anchor id 去重。

    :param old_anchors: 旧证据锚点。
    :param new_anchors: 新证据锚点。
    :returns: 合并后的证据锚点。
    :raises Exception: 不主动抛出异常。
    """

    merged: list[EvidenceAnchor] = []
    seen: set[str] = set()
    for anchor in old_anchors + new_anchors:
        if anchor.anchor_id in seen:
            continue
        seen.add(anchor.anchor_id)
        merged.append(anchor)
    return tuple(merged)


def _item_id(prefix: str, event: RunEvent) -> str:
    """按来源事件构造稳定 item id。

    :param prefix: item 前缀。
    :param event: 来源 RunEvent。
    :returns: item id。
    :raises Exception: 不主动抛出异常。
    """

    return f"{prefix}:{event.run_id}:{event.cursor.sequence}"


def _truncate_text(*, text: str, limit: int) -> str:
    """按字符数截断文本。

    :param text: 原文本。
    :param limit: 最大字符数。
    :returns: 截断后的文本。
    :raises Exception: 不主动抛出异常。
    """

    if limit <= 0:
        return _EMPTY_TEXT
    if len(text) <= limit:
        return text
    return text[:limit] + "...[已裁剪]"


def summarize_raw_turn_for_builder(turn: ConversationRawTurn) -> str:
    """为 RunInputBuilder 生成 raw turn 安全摘要。

    :param turn: raw turn。
    :returns: 摘要文本。
    :raises Exception: 不主动抛出异常。
    """

    user_text = _truncate_text(
        text=turn.user_text,
        limit=_USER_TEXT_SUMMARY_LIMIT,
    )
    assistant_text = (
        _EMPTY_TEXT
        if turn.assistant_final is None
        else _truncate_text(
            text=turn.assistant_final,
            limit=_ASSISTANT_TEXT_SUMMARY_LIMIT,
        )
    )
    terminal_text = (
        _EMPTY_TEXT
        if turn.terminal_summary is None
        else _truncate_text(
            text=turn.terminal_summary,
            limit=_TERMINAL_TEXT_SUMMARY_LIMIT,
        )
    )
    parts = [f"user: {user_text}"]
    if assistant_text != _EMPTY_TEXT:
        parts.append(f"assistant_final: {assistant_text}")
    if terminal_text != _EMPTY_TEXT:
        parts.append(f"terminal: {terminal_text}")
    return "\n".join(parts)


def scope_from_user_input_event(event: RunEvent) -> MemoryScope:
    """从 USER_INPUT_ACCEPTED 事件读取 memory scope。

    :param event: 用户输入事件。
    :returns: memory scope。
    :raises TypeError: 事件 data 类型不匹配时抛出。
    :raises ValueError: scope 值不在封闭枚举中时抛出。
    """

    data = event.data
    if not isinstance(data, UserInputAcceptedData):
        raise TypeError("USER_INPUT_ACCEPTED data must be UserInputAcceptedData")
    if not isinstance(data.scope, UserInputScope):
        raise ValueError("USER_INPUT_ACCEPTED scope must be UserInputScope")
    if data.scope is UserInputScope.SESSION:
        return MemoryScope.SESSION
    raise ValueError(f"unsupported USER_INPUT_ACCEPTED scope: {data.scope.value}")


__all__ = [
    "AssumptionRegister",
    "ClaimCorrectionPatch",
    "ClaimStatus",
    "ConversationMemoryPatch",
    "ConversationMemorySnapshot",
    "ConversationMemoryStore",
    "ConversationPinnedState",
    "ConversationRawTurn",
    "ConversationToolFact",
    "EvidenceAnchor",
    "InMemoryConversationMemoryStore",
    "MemoryClaim",
    "MemoryIngestionPolicy",
    "MemoryProducerKind",
    "MemoryProvenance",
    "MemoryResetPatch",
    "MemoryScope",
    "MemoryTrustLevel",
    "ScopeClearPatch",
    "TaskFrame",
    "UserPreferenceProfileRef",
    "scope_from_user_input_event",
    "summarize_raw_turn_for_builder",
]
