"""Host Conversation Memory typed contracts。

本模块定义 Phase 9 session memory projection 的层中立契约。Memory 是
EventLog 的可重建 read model，不是 Host governance truth；本模块不读取
durable store，不导入 Engine / Fins / Service / UI，也不表达财报业务字段。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.codec import sha256_digest_json

MemoryPolicyDigest: TypeAlias = str
"""Memory policy canonical JSON digest。"""

MemoryDigestRef: TypeAlias = str
"""Memory provenance 使用的 digest ref 文本。"""

HostEventRef: TypeAlias = str
"""Host EventLog ref 文本。"""

HostPayloadRef: TypeAlias = str
"""Host payload descriptor ref 文本。"""

_MIN_SEQUENCE = 0
_MIN_POSITIVE_LIMIT = 1
_EMPTY_SIZE_UNITS = 0


class MemoryClaimStatus(StrEnum):
    """Host 中立 memory claim 状态枚举。"""

    TOOL_VERIFIED = "tool_verified"
    ASSUMPTION = "assumption"
    CANDIDATE = "candidate"
    CONFLICTED = "conflicted"
    STALE = "stale"
    SUPERSEDED = "superseded"


class MemoryProducerKind(StrEnum):
    """Host 中立 memory producer 类型枚举。"""

    TOOL = "tool"
    USER = "user"
    ASSISTANT = "assistant"
    HOST_PROJECTION = "host_projection"


class HostNeutralRefKind(StrEnum):
    """Host 中立 opaque ref 类型枚举。"""

    SOURCE = "source"
    CHUNK = "chunk"
    ENTITY = "entity"
    SUBJECT = "subject"
    TOPIC = "topic"
    EVIDENCE = "evidence"
    PAYLOAD = "payload"
    EXTERNAL = "external"


class MemoryIncludedReason(StrEnum):
    """Memory item 被纳入 snapshot 的中立原因。"""

    PINNED_STATE = "pinned_state"
    TOOL_VERIFIED_FACT = "tool_verified_fact"
    WORKING_ASSUMPTION = "working_assumption"
    RECENT_RAW_TURN = "recent_raw_turn"
    EPISODE_SUMMARY = "episode_summary"
    EMPTY_SNAPSHOT = "empty_snapshot"


class MemoryExcludedReason(StrEnum):
    """Memory item 被排除出 snapshot 的中立原因。"""

    BUDGET_LIMIT = "budget_limit"
    MISSING_PROVENANCE = "missing_provenance"
    UNSUPPORTED_EVENT_TYPE = "unsupported_event_type"
    POLICY_EXCLUDED = "policy_excluded"


class ConversationContinuityKind(StrEnum):
    """Conversation continuity item 的中立类型。"""

    RAW_USER_TURN = "raw_user_turn"
    RAW_ASSISTANT_TURN = "raw_assistant_turn"
    ASSISTANT_CONCLUSION = "assistant_conclusion"
    EPISODE_SUMMARY = "episode_summary"


class MemoryDiagnosticReason(StrEnum):
    """Memory diagnostic 的结构化原因。"""

    MISSING_FACT_SUMMARY_FALLBACK = "missing_fact_summary_fallback"
    INLINE_DELTA_REPAIR_INCLUDED = "inline_delta_repair_included"
    SNAPSHOT_MISSING = "snapshot_missing"
    SNAPSHOT_DAMAGED = "snapshot_damaged"
    SNAPSHOT_LAG_OVER_THRESHOLD = "snapshot_lag_over_threshold"
    BUDGET_LIMIT_REACHED = "budget_limit_reached"
    EMPTY_EVENT_LOG_SNAPSHOT = "empty_event_log_snapshot"


@dataclass(frozen=True, slots=True)
class MemorySizeUnits:
    """Memory item 的统一尺寸单位。

    :param units: 保守估算后的尺寸单位，必须大于等于 ``0``。
    """

    units: int

    def __post_init__(self) -> None:
        """校验尺寸单位。

        :returns: ``None``。
        :raises ValueError: ``units`` 为负数时抛出。
        """

        if self.units < _EMPTY_SIZE_UNITS:
            raise ValueError("memory size units must be non-negative")


@dataclass(frozen=True, slots=True)
class MemorySnapshotCursor:
    """Memory snapshot 覆盖的 projection cursor。

    :param consumer_id: memory projection consumer 稳定 id。
    :param checkpoint_event_sequence: 已覆盖 EventLog sequence；``0`` 表示空 cursor。
    :param checkpoint_event_id: 已覆盖 EventLog id；空 cursor 必须为 ``None``。
    :param session_id: cursor 所属 session id。
    """

    consumer_id: str
    checkpoint_event_sequence: int
    checkpoint_event_id: str | None
    session_id: str

    def __post_init__(self) -> None:
        """校验 cursor 的基础一致性。

        :returns: ``None``。
        :raises ValueError: id 为空、sequence 为负数或 event id 与 sequence 不一致时抛出。
        """

        _require_non_empty(self.consumer_id, "consumer_id")
        _require_non_empty(self.session_id, "session_id")
        _require_optional_non_empty(self.checkpoint_event_id, "checkpoint_event_id")
        if self.checkpoint_event_sequence < _MIN_SEQUENCE:
            raise ValueError("checkpoint_event_sequence must be non-negative")
        if self.checkpoint_event_sequence == _MIN_SEQUENCE:
            if self.checkpoint_event_id is not None:
                raise ValueError("zero cursor cannot carry checkpoint_event_id")
        elif self.checkpoint_event_id is None:
            raise ValueError("positive cursor requires checkpoint_event_id")


@dataclass(frozen=True, slots=True)
class OpaqueMemoryRef:
    """Host 中立 opaque memory ref。

    :param ref_kind: Host 中立 ref 类型。
    :param ref_id: 业务方或 Host 生成的不透明 id。
    :param digest: 可选 digest，用于证明 ref 指向内容的稳定性。
    """

    ref_kind: HostNeutralRefKind
    ref_id: str
    digest: str | None = None

    def __post_init__(self) -> None:
        """校验 opaque ref 字段。

        :returns: ``None``。
        :raises ValueError: ref kind 不是中立枚举、id 为空或 digest 为空字符串时抛出。
        """

        if not isinstance(self.ref_kind, HostNeutralRefKind):
            raise ValueError("ref_kind must be HostNeutralRefKind")
        _require_non_empty(self.ref_id, "ref_id")
        _require_optional_non_empty(self.digest, "digest")


@dataclass(frozen=True, slots=True)
class MemoryProvenanceRef:
    """Memory item provenance ref。

    :param producer_kind: producer 中立类型。
    :param producer_name: producer 名称，例如 tool name 或 Host projection 名称。
    :param event_id: 来源 EventLog id。
    :param event_sequence: 来源 EventLog sequence。
    :param run_id: 可选 run id。
    :param attempt_id: 可选 attempt id。
    :param execution_id: 可选 execution id。
    :param tool_result_ref: 可选 tool result event ref。
    :param payload_ref: 可选 payload descriptor ref。
    :param digest_ref: 来源内容 digest ref。
    :param source_refs: 来源 opaque refs。
    """

    producer_kind: MemoryProducerKind
    producer_name: str
    event_id: str
    event_sequence: int
    run_id: str | None
    attempt_id: str | None
    execution_id: str | None
    tool_result_ref: HostEventRef | None
    payload_ref: HostPayloadRef | None
    digest_ref: MemoryDigestRef
    source_refs: tuple[OpaqueMemoryRef, ...]

    def __post_init__(self) -> None:
        """校验 provenance ref 字段。

        :returns: ``None``。
        :raises ValueError: 枚举、id、sequence 或可选文本不合法时抛出。
        """

        if not isinstance(self.producer_kind, MemoryProducerKind):
            raise ValueError("producer_kind must be MemoryProducerKind")
        _require_non_empty(self.producer_name, "producer_name")
        _require_non_empty(self.event_id, "event_id")
        _require_non_empty(self.digest_ref, "digest_ref")
        if self.event_sequence <= _MIN_SEQUENCE:
            raise ValueError("event_sequence must be positive")
        _require_optional_non_empty(self.run_id, "run_id")
        _require_optional_non_empty(self.attempt_id, "attempt_id")
        _require_optional_non_empty(self.execution_id, "execution_id")
        _require_optional_non_empty(self.tool_result_ref, "tool_result_ref")
        _require_optional_non_empty(self.payload_ref, "payload_ref")


@dataclass(frozen=True, slots=True)
class PinnedStateView:
    """Memory pinned state view。

    :param current_goal: 当前稳定目标。
    :param confirmed_subjects: 已确认主体 opaque refs。
    :param user_constraints: 用户约束文本。
    :param open_questions: 尚待回答的问题文本。
    """

    current_goal: str | None
    confirmed_subjects: tuple[OpaqueMemoryRef, ...]
    user_constraints: tuple[str, ...]
    open_questions: tuple[str, ...]

    def __post_init__(self) -> None:
        """校验 pinned state 文本与重复问题。

        :returns: ``None``。
        :raises ValueError: 文本为空字符串或 open questions 内部重复时抛出。
        """

        _require_optional_non_empty(self.current_goal, "current_goal")
        _require_non_empty_items(self.user_constraints, "user_constraints")
        _require_non_empty_items(self.open_questions, "open_questions")
        if len(frozenset(self.open_questions)) != len(self.open_questions):
            raise ValueError("open_questions must not contain duplicates")


@dataclass(frozen=True, slots=True)
class VerifiedFactView:
    """Tool verified fact memory view。

    :param item_id: item 稳定 id。
    :param fact_summary: 工具事实的中立摘要。
    :param claim_status: claim 状态，必须为 ``TOOL_VERIFIED``。
    :param provenance: 来源 provenance，producer 必须为 ``TOOL``。
    :param evidence_anchor: 可选证据 anchor opaque ref。
    :param subject_refs: 相关主体 opaque refs。
    :param included_reason: 可选纳入原因。
    :param excluded_reason: 可选排除原因。
    :param size_units: 统一尺寸单位。
    """

    item_id: str
    fact_summary: str
    claim_status: MemoryClaimStatus
    provenance: MemoryProvenanceRef
    evidence_anchor: OpaqueMemoryRef | None
    subject_refs: tuple[OpaqueMemoryRef, ...]
    included_reason: MemoryIncludedReason | None
    excluded_reason: MemoryExcludedReason | None
    size_units: MemorySizeUnits

    def __post_init__(self) -> None:
        """校验 verified fact 的 producer 与状态。

        :returns: ``None``。
        :raises ValueError: id / summary 为空、claim status 非工具确认或 provenance 非 TOOL 时抛出。
        """

        _require_non_empty(self.item_id, "item_id")
        _require_non_empty(self.fact_summary, "fact_summary")
        if self.claim_status is not MemoryClaimStatus.TOOL_VERIFIED:
            raise ValueError("verified fact claim_status must be TOOL_VERIFIED")
        if self.provenance.producer_kind is not MemoryProducerKind.TOOL:
            raise ValueError("verified fact provenance producer must be TOOL")
        _validate_reason_pair(self.included_reason, self.excluded_reason)


@dataclass(frozen=True, slots=True)
class WorkingAssumptionView:
    """Working assumption memory view。

    :param item_id: item 稳定 id。
    :param assumption_summary: assumption 中立摘要。
    :param claim_status: claim 状态，必须为 ``ASSUMPTION``。
    :param producer_kind: 来源 producer 类型，不允许为 ``TOOL``。
    :param event_id: 来源 EventLog id。
    :param event_sequence: 来源 EventLog sequence。
    :param run_id: 可选 run id。
    :param subject_refs: 相关主体 opaque refs。
    :param included_reason: 可选纳入原因。
    :param excluded_reason: 可选排除原因。
    :param size_units: 统一尺寸单位。
    """

    item_id: str
    assumption_summary: str
    claim_status: MemoryClaimStatus
    producer_kind: MemoryProducerKind
    event_id: str
    event_sequence: int
    run_id: str | None
    subject_refs: tuple[OpaqueMemoryRef, ...]
    included_reason: MemoryIncludedReason | None
    excluded_reason: MemoryExcludedReason | None
    size_units: MemorySizeUnits

    def __post_init__(self) -> None:
        """校验 working assumption 的中立状态。

        :returns: ``None``。
        :raises ValueError: id / summary 为空、状态非 ``ASSUMPTION`` 或 producer 为 ``TOOL`` 时抛出。
        """

        _require_non_empty(self.item_id, "item_id")
        _require_non_empty(self.assumption_summary, "assumption_summary")
        _require_non_empty(self.event_id, "event_id")
        _require_optional_non_empty(self.run_id, "run_id")
        if self.event_sequence <= _MIN_SEQUENCE:
            raise ValueError("event_sequence must be positive")
        if self.claim_status is not MemoryClaimStatus.ASSUMPTION:
            raise ValueError("working assumption claim_status must be ASSUMPTION")
        if self.producer_kind is MemoryProducerKind.TOOL:
            raise ValueError("working assumption producer cannot be TOOL")
        _validate_reason_pair(self.included_reason, self.excluded_reason)


@dataclass(frozen=True, slots=True)
class ConversationContinuityItem:
    """Conversation continuity item。

    :param item_id: item 稳定 id。
    :param item_kind: continuity item 类型。
    :param producer_kind: 来源 producer 类型，不能为 ``TOOL``。
    :param claim_status: claim 状态，必须为 ``ASSUMPTION``。
    :param event_id: 来源 EventLog id。
    :param event_sequence: 来源 EventLog sequence。
    :param run_id: 可选 run id。
    :param summary_text: 可选连续性摘要。
    :param payload_ref: 可选 payload descriptor ref。
    :param payload_digest: 可选 payload digest。
    :param included_reason: 可选纳入原因。
    :param excluded_reason: 可选排除原因。
    :param size_units: 统一尺寸单位。
    """

    item_id: str
    item_kind: ConversationContinuityKind
    producer_kind: MemoryProducerKind
    claim_status: MemoryClaimStatus
    event_id: str
    event_sequence: int
    run_id: str | None
    summary_text: str | None
    payload_ref: HostPayloadRef | None
    payload_digest: str | None
    included_reason: MemoryIncludedReason | None
    excluded_reason: MemoryExcludedReason | None
    size_units: MemorySizeUnits

    def __post_init__(self) -> None:
        """校验 continuity item 的中立状态。

        :returns: ``None``。
        :raises ValueError: id、枚举、claim status、producer 或 payload ref / digest 不合法时抛出。
        """

        _require_non_empty(self.item_id, "item_id")
        if not isinstance(self.item_kind, ConversationContinuityKind):
            raise ValueError("item_kind must be ConversationContinuityKind")
        if self.producer_kind is MemoryProducerKind.TOOL:
            raise ValueError("continuity producer cannot be TOOL")
        if self.claim_status is not MemoryClaimStatus.ASSUMPTION:
            raise ValueError("continuity claim_status must be ASSUMPTION")
        _require_non_empty(self.event_id, "event_id")
        _require_optional_non_empty(self.run_id, "run_id")
        _require_optional_non_empty(self.summary_text, "summary_text")
        _require_optional_non_empty(self.payload_ref, "payload_ref")
        _require_optional_non_empty(self.payload_digest, "payload_digest")
        if self.event_sequence <= _MIN_SEQUENCE:
            raise ValueError("event_sequence must be positive")
        if (self.payload_ref is None) != (self.payload_digest is None):
            raise ValueError("payload_ref and payload_digest must be paired")
        _validate_reason_pair(self.included_reason, self.excluded_reason)


@dataclass(frozen=True, slots=True)
class ConversationContinuityView:
    """Conversation continuity view。

    :param items: continuity item 元组。
    """

    items: tuple[ConversationContinuityItem, ...]


@dataclass(frozen=True, slots=True)
class MemoryDiagnostic:
    """Memory projection diagnostic。

    :param diagnostic_id: diagnostic 稳定 id。
    :param reason: 结构化原因。
    :param message: 面向 trace / debug 的中立说明。
    :param event_sequence: 可选关联 EventLog sequence。
    :param item_id: 可选关联 memory item id。
    :param policy_digest: 可选 policy digest。
    :param recorded_at: 可选记录时间。
    """

    diagnostic_id: str
    reason: MemoryDiagnosticReason
    message: str
    event_sequence: int | None
    item_id: str | None
    policy_digest: MemoryPolicyDigest | None
    recorded_at: str | None

    def __post_init__(self) -> None:
        """校验 diagnostic 字段。

        :returns: ``None``。
        :raises ValueError: id、原因、消息或可选字段不合法时抛出。
        """

        _require_non_empty(self.diagnostic_id, "diagnostic_id")
        if not isinstance(self.reason, MemoryDiagnosticReason):
            raise ValueError("reason must be MemoryDiagnosticReason")
        _require_non_empty(self.message, "message")
        if self.event_sequence is not None and self.event_sequence <= _MIN_SEQUENCE:
            raise ValueError("event_sequence must be positive when provided")
        _require_optional_non_empty(self.item_id, "item_id")
        _require_optional_non_empty(self.policy_digest, "policy_digest")
        _require_optional_non_empty(self.recorded_at, "recorded_at")


@dataclass(frozen=True, slots=True)
class MemoryProjectionPolicy:
    """Memory projection policy。

    :param max_pinned_items: pinned state 最大条目数。
    :param max_verified_facts: verified facts 最大条目数。
    :param max_working_assumptions: working assumptions 最大条目数。
    :param recent_raw_turns_floor: recent raw turns 保底条数。
    :param max_raw_turn_size_units: 单条 raw turn 最大尺寸单位。
    :param history_pool_size_units: history pool 总尺寸单位。
    :param stable_layer_size_units: stable layer 总尺寸单位。
    :param max_lag_events_for_inline_delta: inline delta 允许的最大滞后事件数。
    :param max_delta_repair_events: repair delta 最大事件数。
    """

    max_pinned_items: int
    max_verified_facts: int
    max_working_assumptions: int
    recent_raw_turns_floor: int
    max_raw_turn_size_units: int
    history_pool_size_units: int
    stable_layer_size_units: int
    max_lag_events_for_inline_delta: int
    max_delta_repair_events: int

    def __post_init__(self) -> None:
        """校验 policy limit。

        :returns: ``None``。
        :raises ValueError: 任一 limit 小于允许下限时抛出。
        """

        _require_positive(self.max_pinned_items, "max_pinned_items")
        _require_positive(self.max_verified_facts, "max_verified_facts")
        _require_positive(
            self.max_working_assumptions, "max_working_assumptions"
        )
        _require_non_negative(
            self.recent_raw_turns_floor, "recent_raw_turns_floor"
        )
        _require_positive(
            self.max_raw_turn_size_units, "max_raw_turn_size_units"
        )
        _require_positive(self.history_pool_size_units, "history_pool_size_units")
        _require_positive(self.stable_layer_size_units, "stable_layer_size_units")
        _require_non_negative(
            self.max_lag_events_for_inline_delta,
            "max_lag_events_for_inline_delta",
        )
        _require_non_negative(self.max_delta_repair_events, "max_delta_repair_events")


@dataclass(frozen=True, slots=True)
class ConversationMemorySnapshot:
    """Conversation memory snapshot。

    :param snapshot_id: snapshot 稳定 id。
    :param session_id: session id。
    :param cursor: snapshot 覆盖的 EventLog cursor。
    :param policy_digest: projection policy digest。
    :param pinned_state: pinned state view。
    :param verified_facts: tool verified facts。
    :param working_assumptions: working assumptions。
    :param conversation_continuity: conversation continuity view。
    :param diagnostics: memory diagnostics。
    :param built_at: snapshot 构建时间。
    :param snapshot_digest: snapshot canonical digest，不包含 ``built_at`` 以及
        diagnostic id / recorded time 等非确定字段。
    """

    snapshot_id: str
    session_id: str
    cursor: MemorySnapshotCursor
    policy_digest: MemoryPolicyDigest
    pinned_state: PinnedStateView
    verified_facts: tuple[VerifiedFactView, ...]
    working_assumptions: tuple[WorkingAssumptionView, ...]
    conversation_continuity: ConversationContinuityView
    diagnostics: tuple[MemoryDiagnostic, ...]
    built_at: str
    snapshot_digest: str

    def __post_init__(self) -> None:
        """校验 snapshot 基础一致性。

        :returns: ``None``。
        :raises ValueError: id 为空、session 不一致或 digest 为空时抛出。
        """

        _require_non_empty(self.snapshot_id, "snapshot_id")
        _require_non_empty(self.session_id, "session_id")
        _require_non_empty(self.policy_digest, "policy_digest")
        _require_non_empty(self.built_at, "built_at")
        _require_non_empty(self.snapshot_digest, "snapshot_digest")
        if self.cursor.session_id != self.session_id:
            raise ValueError("snapshot session_id must match cursor session_id")


def estimate_memory_size_units(text: str) -> MemorySizeUnits:
    """用统一保守口径估算 memory 文本尺寸。

    :param text: 待估算文本。
    :returns: 以字符数为第一版口径的 memory 尺寸单位。
    :raises ValueError: ``text`` 不是有效文本时抛出。
    """

    if not isinstance(text, str):
        raise ValueError("text must be str")
    return MemorySizeUnits(units=len(text))


def digest_memory_projection_policy(
    policy: MemoryProjectionPolicy,
) -> MemoryPolicyDigest:
    """计算 memory projection policy digest。

    :param policy: memory projection policy。
    :returns: policy canonical JSON sha256 digest。
    """

    return sha256_digest_json(memory_projection_policy_to_json_value(policy))


def calculate_memory_snapshot_digest(
    snapshot: ConversationMemorySnapshot,
) -> str:
    """计算 snapshot canonical digest。

    digest 覆盖 cursor、policy digest、四类 view 与 diagnostics 的稳定语义字段；
    不包含 ``snapshot_id``、``built_at``、``snapshot_digest``，也不包含
    ``diagnostic_id`` / ``recorded_at`` 等非确定字段。

    :param snapshot: memory snapshot。
    :returns: snapshot canonical JSON sha256 digest。
    """

    return sha256_digest_json(_snapshot_digest_json_value(snapshot))


def build_empty_conversation_memory_snapshot(
    *,
    snapshot_id: str,
    session_id: str,
    consumer_id: str,
    policy_digest: MemoryPolicyDigest,
    built_at: str,
) -> ConversationMemorySnapshot:
    """构造空 EventLog 可用的空 memory snapshot。

    :param snapshot_id: snapshot 稳定 id。
    :param session_id: session id。
    :param consumer_id: memory projection consumer id。
    :param policy_digest: projection policy digest。
    :param built_at: 构建时间。
    :returns: 空 memory snapshot。
    :raises ValueError: 任一必填文本为空时抛出。
    """

    cursor = MemorySnapshotCursor(
        consumer_id=consumer_id,
        checkpoint_event_sequence=_MIN_SEQUENCE,
        checkpoint_event_id=None,
        session_id=session_id,
    )
    snapshot_without_digest = ConversationMemorySnapshot(
        snapshot_id=snapshot_id,
        session_id=session_id,
        cursor=cursor,
        policy_digest=policy_digest,
        pinned_state=PinnedStateView(
            current_goal=None,
            confirmed_subjects=(),
            user_constraints=(),
            open_questions=(),
        ),
        verified_facts=(),
        working_assumptions=(),
        conversation_continuity=ConversationContinuityView(items=()),
        diagnostics=(),
        built_at=built_at,
        snapshot_digest="pending",
    )
    digest = calculate_memory_snapshot_digest(snapshot_without_digest)
    return ConversationMemorySnapshot(
        snapshot_id=snapshot_id,
        session_id=session_id,
        cursor=cursor,
        policy_digest=policy_digest,
        pinned_state=snapshot_without_digest.pinned_state,
        verified_facts=(),
        working_assumptions=(),
        conversation_continuity=snapshot_without_digest.conversation_continuity,
        diagnostics=(),
        built_at=built_at,
        snapshot_digest=digest,
    )


def memory_projection_policy_to_json_value(
    policy: MemoryProjectionPolicy,
) -> JsonValue:
    """把 memory projection policy 转换为 canonical JSON 值。

    :param policy: memory projection policy。
    :returns: 可序列化 JSON 值。
    """

    return {
        "history_pool_size_units": policy.history_pool_size_units,
        "max_delta_repair_events": policy.max_delta_repair_events,
        "max_lag_events_for_inline_delta": policy.max_lag_events_for_inline_delta,
        "max_pinned_items": policy.max_pinned_items,
        "max_raw_turn_size_units": policy.max_raw_turn_size_units,
        "max_verified_facts": policy.max_verified_facts,
        "max_working_assumptions": policy.max_working_assumptions,
        "recent_raw_turns_floor": policy.recent_raw_turns_floor,
        "stable_layer_size_units": policy.stable_layer_size_units,
    }


def conversation_memory_snapshot_to_json_value(
    snapshot: ConversationMemorySnapshot,
) -> JsonValue:
    """把 memory snapshot 转换为 durable JSON 值。

    :param snapshot: memory snapshot。
    :returns: 可序列化 JSON 值。
    """

    return {
        "built_at": snapshot.built_at,
        "conversation_continuity": _continuity_view_to_json_value(
            snapshot.conversation_continuity
        ),
        "cursor": _cursor_to_json_value(snapshot.cursor),
        "diagnostics": [
            memory_diagnostic_to_json_value(diagnostic)
            for diagnostic in snapshot.diagnostics
        ],
        "pinned_state": _pinned_state_to_json_value(snapshot.pinned_state),
        "policy_digest": snapshot.policy_digest,
        "session_id": snapshot.session_id,
        "snapshot_digest": snapshot.snapshot_digest,
        "snapshot_id": snapshot.snapshot_id,
        "verified_facts": [
            _verified_fact_to_json_value(item) for item in snapshot.verified_facts
        ],
        "working_assumptions": [
            _working_assumption_to_json_value(item)
            for item in snapshot.working_assumptions
        ],
    }


def memory_diagnostic_to_json_value(diagnostic: MemoryDiagnostic) -> JsonValue:
    """把 memory diagnostic 转换为 durable JSON 值。

    :param diagnostic: memory diagnostic。
    :returns: 可序列化 JSON 值。
    """

    return {
        "diagnostic_id": diagnostic.diagnostic_id,
        "event_sequence": diagnostic.event_sequence,
        "item_id": diagnostic.item_id,
        "message": diagnostic.message,
        "policy_digest": diagnostic.policy_digest,
        "reason": diagnostic.reason.value,
        "recorded_at": diagnostic.recorded_at,
    }


def conversation_memory_snapshot_from_json_value(
    value: JsonValue,
) -> ConversationMemorySnapshot:
    """从 durable JSON 值恢复 memory snapshot。

    :param value: durable JSON 值。
    :returns: memory snapshot。
    :raises ValueError: JSON shape 或字段值不合法时抛出。
    """

    mapping = _as_mapping(value, "snapshot")
    return ConversationMemorySnapshot(
        snapshot_id=_required_str(mapping, "snapshot_id"),
        session_id=_required_str(mapping, "session_id"),
        cursor=_cursor_from_json_value(_required_value(mapping, "cursor")),
        policy_digest=_required_str(mapping, "policy_digest"),
        pinned_state=_pinned_state_from_json_value(
            _required_value(mapping, "pinned_state")
        ),
        verified_facts=tuple(
            _verified_fact_from_json_value(item)
            for item in _required_list(mapping, "verified_facts")
        ),
        working_assumptions=tuple(
            _working_assumption_from_json_value(item)
            for item in _required_list(mapping, "working_assumptions")
        ),
        conversation_continuity=_continuity_view_from_json_value(
            _required_value(mapping, "conversation_continuity")
        ),
        diagnostics=tuple(
            memory_diagnostic_from_json_value(item)
            for item in _required_list(mapping, "diagnostics")
        ),
        built_at=_required_str(mapping, "built_at"),
        snapshot_digest=_required_str(mapping, "snapshot_digest"),
    )


def memory_diagnostic_from_json_value(value: JsonValue) -> MemoryDiagnostic:
    """从 durable JSON 值恢复 memory diagnostic。

    :param value: durable JSON 值。
    :returns: memory diagnostic。
    :raises ValueError: JSON shape 或字段值不合法时抛出。
    """

    mapping = _as_mapping(value, "diagnostic")
    return MemoryDiagnostic(
        diagnostic_id=_required_str(mapping, "diagnostic_id"),
        reason=MemoryDiagnosticReason(_required_str(mapping, "reason")),
        message=_required_str(mapping, "message"),
        event_sequence=_optional_int(mapping, "event_sequence"),
        item_id=_optional_str(mapping, "item_id"),
        policy_digest=_optional_str(mapping, "policy_digest"),
        recorded_at=_optional_str(mapping, "recorded_at"),
    )


def _snapshot_digest_json_value(snapshot: ConversationMemorySnapshot) -> JsonValue:
    """生成 snapshot digest 专用 JSON 值。

    diagnostics 只纳入稳定语义字段，避免 diagnostic id 或 recorded time 改变
    同一 EventLog / policy / view 的 snapshot digest。

    :param snapshot: memory snapshot。
    :returns: digest 专用 JSON 值。
    """

    return {
        "conversation_continuity": _continuity_view_to_json_value(
            snapshot.conversation_continuity
        ),
        "cursor": _cursor_to_json_value(snapshot.cursor),
        "diagnostics": [
            _memory_diagnostic_digest_json_value(diagnostic)
            for diagnostic in snapshot.diagnostics
        ],
        "pinned_state": _pinned_state_to_json_value(snapshot.pinned_state),
        "policy_digest": snapshot.policy_digest,
        "session_id": snapshot.session_id,
        "verified_facts": [
            _verified_fact_to_json_value(item) for item in snapshot.verified_facts
        ],
        "working_assumptions": [
            _working_assumption_to_json_value(item)
            for item in snapshot.working_assumptions
        ],
    }


def _memory_diagnostic_digest_json_value(
    diagnostic: MemoryDiagnostic,
) -> JsonValue:
    """生成 diagnostic digest 专用 JSON 值。

    :param diagnostic: memory diagnostic。
    :returns: 只包含稳定语义字段的 JSON 值。
    """

    return {
        "event_sequence": diagnostic.event_sequence,
        "item_id": diagnostic.item_id,
        "message": diagnostic.message,
        "policy_digest": diagnostic.policy_digest,
        "reason": diagnostic.reason.value,
    }


def _cursor_to_json_value(cursor: MemorySnapshotCursor) -> JsonValue:
    """把 cursor 转换为 JSON 值。

    :param cursor: memory snapshot cursor。
    :returns: JSON 值。
    """

    return {
        "checkpoint_event_id": cursor.checkpoint_event_id,
        "checkpoint_event_sequence": cursor.checkpoint_event_sequence,
        "consumer_id": cursor.consumer_id,
        "session_id": cursor.session_id,
    }


def _cursor_from_json_value(value: JsonValue) -> MemorySnapshotCursor:
    """从 JSON 值恢复 cursor。

    :param value: JSON 值。
    :returns: memory snapshot cursor。
    """

    mapping = _as_mapping(value, "cursor")
    return MemorySnapshotCursor(
        consumer_id=_required_str(mapping, "consumer_id"),
        checkpoint_event_sequence=_required_int(
            mapping, "checkpoint_event_sequence"
        ),
        checkpoint_event_id=_optional_str(mapping, "checkpoint_event_id"),
        session_id=_required_str(mapping, "session_id"),
    )


def _pinned_state_to_json_value(view: PinnedStateView) -> JsonValue:
    """把 pinned state 转换为 JSON 值。

    :param view: pinned state view。
    :returns: JSON 值。
    """

    return {
        "confirmed_subjects": [
            _opaque_ref_to_json_value(ref) for ref in view.confirmed_subjects
        ],
        "current_goal": view.current_goal,
        "open_questions": list(view.open_questions),
        "user_constraints": list(view.user_constraints),
    }


def _pinned_state_from_json_value(value: JsonValue) -> PinnedStateView:
    """从 JSON 值恢复 pinned state。

    :param value: JSON 值。
    :returns: pinned state view。
    """

    mapping = _as_mapping(value, "pinned_state")
    return PinnedStateView(
        current_goal=_optional_str(mapping, "current_goal"),
        confirmed_subjects=tuple(
            _opaque_ref_from_json_value(item)
            for item in _required_list(mapping, "confirmed_subjects")
        ),
        user_constraints=tuple(
            _as_str(item, "user_constraints item")
            for item in _required_list(mapping, "user_constraints")
        ),
        open_questions=tuple(
            _as_str(item, "open_questions item")
            for item in _required_list(mapping, "open_questions")
        ),
    )


def _verified_fact_to_json_value(item: VerifiedFactView) -> JsonValue:
    """把 verified fact 转换为 JSON 值。

    :param item: verified fact。
    :returns: JSON 值。
    """

    return {
        "claim_status": item.claim_status.value,
        "evidence_anchor": (
            None
            if item.evidence_anchor is None
            else _opaque_ref_to_json_value(item.evidence_anchor)
        ),
        "excluded_reason": _enum_value_or_none(item.excluded_reason),
        "fact_summary": item.fact_summary,
        "included_reason": _enum_value_or_none(item.included_reason),
        "item_id": item.item_id,
        "provenance": _provenance_to_json_value(item.provenance),
        "size_units": item.size_units.units,
        "subject_refs": [
            _opaque_ref_to_json_value(ref) for ref in item.subject_refs
        ],
    }


def _verified_fact_from_json_value(value: JsonValue) -> VerifiedFactView:
    """从 JSON 值恢复 verified fact。

    :param value: JSON 值。
    :returns: verified fact。
    """

    mapping = _as_mapping(value, "verified_fact")
    evidence_value = _required_value(mapping, "evidence_anchor")
    return VerifiedFactView(
        item_id=_required_str(mapping, "item_id"),
        fact_summary=_required_str(mapping, "fact_summary"),
        claim_status=MemoryClaimStatus(_required_str(mapping, "claim_status")),
        provenance=_provenance_from_json_value(_required_value(mapping, "provenance")),
        evidence_anchor=(
            None
            if evidence_value is None
            else _opaque_ref_from_json_value(evidence_value)
        ),
        subject_refs=tuple(
            _opaque_ref_from_json_value(item)
            for item in _required_list(mapping, "subject_refs")
        ),
        included_reason=_optional_included_reason(mapping, "included_reason"),
        excluded_reason=_optional_excluded_reason(mapping, "excluded_reason"),
        size_units=MemorySizeUnits(units=_required_int(mapping, "size_units")),
    )


def _working_assumption_to_json_value(item: WorkingAssumptionView) -> JsonValue:
    """把 working assumption 转换为 JSON 值。

    :param item: working assumption。
    :returns: JSON 值。
    """

    return {
        "assumption_summary": item.assumption_summary,
        "claim_status": item.claim_status.value,
        "event_id": item.event_id,
        "event_sequence": item.event_sequence,
        "excluded_reason": _enum_value_or_none(item.excluded_reason),
        "included_reason": _enum_value_or_none(item.included_reason),
        "item_id": item.item_id,
        "producer_kind": item.producer_kind.value,
        "run_id": item.run_id,
        "size_units": item.size_units.units,
        "subject_refs": [
            _opaque_ref_to_json_value(ref) for ref in item.subject_refs
        ],
    }


def _working_assumption_from_json_value(value: JsonValue) -> WorkingAssumptionView:
    """从 JSON 值恢复 working assumption。

    :param value: JSON 值。
    :returns: working assumption。
    """

    mapping = _as_mapping(value, "working_assumption")
    return WorkingAssumptionView(
        item_id=_required_str(mapping, "item_id"),
        assumption_summary=_required_str(mapping, "assumption_summary"),
        claim_status=MemoryClaimStatus(_required_str(mapping, "claim_status")),
        producer_kind=MemoryProducerKind(_required_str(mapping, "producer_kind")),
        event_id=_required_str(mapping, "event_id"),
        event_sequence=_required_int(mapping, "event_sequence"),
        run_id=_optional_str(mapping, "run_id"),
        subject_refs=tuple(
            _opaque_ref_from_json_value(item)
            for item in _required_list(mapping, "subject_refs")
        ),
        included_reason=_optional_included_reason(mapping, "included_reason"),
        excluded_reason=_optional_excluded_reason(mapping, "excluded_reason"),
        size_units=MemorySizeUnits(units=_required_int(mapping, "size_units")),
    )


def _continuity_view_to_json_value(view: ConversationContinuityView) -> JsonValue:
    """把 continuity view 转换为 JSON 值。

    :param view: continuity view。
    :returns: JSON 值。
    """

    return {"items": [_continuity_item_to_json_value(item) for item in view.items]}


def _continuity_view_from_json_value(value: JsonValue) -> ConversationContinuityView:
    """从 JSON 值恢复 continuity view。

    :param value: JSON 值。
    :returns: continuity view。
    """

    mapping = _as_mapping(value, "conversation_continuity")
    return ConversationContinuityView(
        items=tuple(
            _continuity_item_from_json_value(item)
            for item in _required_list(mapping, "items")
        )
    )


def _continuity_item_to_json_value(item: ConversationContinuityItem) -> JsonValue:
    """把 continuity item 转换为 JSON 值。

    :param item: continuity item。
    :returns: JSON 值。
    """

    return {
        "claim_status": item.claim_status.value,
        "event_id": item.event_id,
        "event_sequence": item.event_sequence,
        "excluded_reason": _enum_value_or_none(item.excluded_reason),
        "included_reason": _enum_value_or_none(item.included_reason),
        "item_id": item.item_id,
        "item_kind": item.item_kind.value,
        "payload_digest": item.payload_digest,
        "payload_ref": item.payload_ref,
        "producer_kind": item.producer_kind.value,
        "run_id": item.run_id,
        "size_units": item.size_units.units,
        "summary_text": item.summary_text,
    }


def _continuity_item_from_json_value(value: JsonValue) -> ConversationContinuityItem:
    """从 JSON 值恢复 continuity item。

    :param value: JSON 值。
    :returns: continuity item。
    """

    mapping = _as_mapping(value, "conversation_continuity_item")
    return ConversationContinuityItem(
        item_id=_required_str(mapping, "item_id"),
        item_kind=ConversationContinuityKind(_required_str(mapping, "item_kind")),
        producer_kind=MemoryProducerKind(_required_str(mapping, "producer_kind")),
        claim_status=MemoryClaimStatus(_required_str(mapping, "claim_status")),
        event_id=_required_str(mapping, "event_id"),
        event_sequence=_required_int(mapping, "event_sequence"),
        run_id=_optional_str(mapping, "run_id"),
        summary_text=_optional_str(mapping, "summary_text"),
        payload_ref=_optional_str(mapping, "payload_ref"),
        payload_digest=_optional_str(mapping, "payload_digest"),
        included_reason=_optional_included_reason(mapping, "included_reason"),
        excluded_reason=_optional_excluded_reason(mapping, "excluded_reason"),
        size_units=MemorySizeUnits(units=_required_int(mapping, "size_units")),
    )


def _provenance_to_json_value(provenance: MemoryProvenanceRef) -> JsonValue:
    """把 provenance 转换为 JSON 值。

    :param provenance: provenance ref。
    :returns: JSON 值。
    """

    return {
        "attempt_id": provenance.attempt_id,
        "digest_ref": provenance.digest_ref,
        "event_id": provenance.event_id,
        "event_sequence": provenance.event_sequence,
        "execution_id": provenance.execution_id,
        "payload_ref": provenance.payload_ref,
        "producer_kind": provenance.producer_kind.value,
        "producer_name": provenance.producer_name,
        "run_id": provenance.run_id,
        "source_refs": [
            _opaque_ref_to_json_value(ref) for ref in provenance.source_refs
        ],
        "tool_result_ref": provenance.tool_result_ref,
    }


def _provenance_from_json_value(value: JsonValue) -> MemoryProvenanceRef:
    """从 JSON 值恢复 provenance。

    :param value: JSON 值。
    :returns: provenance ref。
    """

    mapping = _as_mapping(value, "provenance")
    return MemoryProvenanceRef(
        producer_kind=MemoryProducerKind(_required_str(mapping, "producer_kind")),
        producer_name=_required_str(mapping, "producer_name"),
        event_id=_required_str(mapping, "event_id"),
        event_sequence=_required_int(mapping, "event_sequence"),
        run_id=_optional_str(mapping, "run_id"),
        attempt_id=_optional_str(mapping, "attempt_id"),
        execution_id=_optional_str(mapping, "execution_id"),
        tool_result_ref=_optional_str(mapping, "tool_result_ref"),
        payload_ref=_optional_str(mapping, "payload_ref"),
        digest_ref=_required_str(mapping, "digest_ref"),
        source_refs=tuple(
            _opaque_ref_from_json_value(item)
            for item in _required_list(mapping, "source_refs")
        ),
    )


def _opaque_ref_to_json_value(ref: OpaqueMemoryRef) -> JsonValue:
    """把 opaque ref 转换为 JSON 值。

    :param ref: opaque ref。
    :returns: JSON 值。
    """

    return {
        "digest": ref.digest,
        "ref_id": ref.ref_id,
        "ref_kind": ref.ref_kind.value,
    }


def _opaque_ref_from_json_value(value: JsonValue) -> OpaqueMemoryRef:
    """从 JSON 值恢复 opaque ref。

    :param value: JSON 值。
    :returns: opaque ref。
    """

    mapping = _as_mapping(value, "opaque_ref")
    return OpaqueMemoryRef(
        ref_kind=HostNeutralRefKind(_required_str(mapping, "ref_kind")),
        ref_id=_required_str(mapping, "ref_id"),
        digest=_optional_str(mapping, "digest"),
    )


def _optional_included_reason(
    mapping: Mapping[str, JsonValue], field_name: str
) -> MemoryIncludedReason | None:
    """读取 optional included reason。

    :param mapping: JSON mapping。
    :param field_name: 字段名。
    :returns: included reason 或 ``None``。
    """

    value = _optional_str(mapping, field_name)
    if value is None:
        return None
    return MemoryIncludedReason(value)


def _optional_excluded_reason(
    mapping: Mapping[str, JsonValue], field_name: str
) -> MemoryExcludedReason | None:
    """读取 optional excluded reason。

    :param mapping: JSON mapping。
    :param field_name: 字段名。
    :returns: excluded reason 或 ``None``。
    """

    value = _optional_str(mapping, field_name)
    if value is None:
        return None
    return MemoryExcludedReason(value)


def _enum_value_or_none(value: StrEnum | None) -> str | None:
    """读取 enum 字符串值。

    :param value: enum 或 ``None``。
    :returns: enum value 或 ``None``。
    """

    if value is None:
        return None
    return value.value


def _validate_reason_pair(
    included_reason: MemoryIncludedReason | None,
    excluded_reason: MemoryExcludedReason | None,
) -> None:
    """校验 included / excluded reason 不同时存在。

    :param included_reason: 可选纳入原因。
    :param excluded_reason: 可选排除原因。
    :returns: ``None``。
    :raises ValueError: 两者同时存在时抛出。
    """

    if included_reason is not None and excluded_reason is not None:
        raise ValueError("included_reason and excluded_reason are mutually exclusive")


def _require_non_empty(value: str, field_name: str) -> None:
    """校验必填文本非空。

    :param value: 待校验文本。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: 文本为空时抛出。
    """

    if value == "" or value.isspace():
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_non_empty(value: str | None, field_name: str) -> None:
    """校验 optional 文本非空。

    :param value: optional 文本。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: 文本为空字符串时抛出。
    """

    if value is not None:
        _require_non_empty(value, field_name)


def _require_non_empty_items(values: tuple[str, ...], field_name: str) -> None:
    """校验文本元组内没有空字符串。

    :param values: 文本元组。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: 任一文本为空时抛出。
    """

    for value in values:
        _require_non_empty(value, field_name)


def _require_positive(value: int, field_name: str) -> None:
    """校验整数为正数。

    :param value: 整数值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: 值小于 ``1`` 时抛出。
    """

    if value < _MIN_POSITIVE_LIMIT:
        raise ValueError(f"{field_name} must be positive")


def _require_non_negative(value: int, field_name: str) -> None:
    """校验整数非负。

    :param value: 整数值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: 值小于 ``0`` 时抛出。
    """

    if value < _MIN_SEQUENCE:
        raise ValueError(f"{field_name} must be non-negative")


def _as_mapping(value: JsonValue, field_name: str) -> Mapping[str, JsonValue]:
    """把 JSON 值校验为 mapping。

    :param value: JSON 值。
    :param field_name: 字段名。
    :returns: JSON mapping。
    :raises ValueError: 值不是 mapping 时抛出。
    """

    if isinstance(value, Mapping):
        return value
    raise ValueError(f"{field_name} must be JSON mapping")


def _required_value(
    mapping: Mapping[str, JsonValue], field_name: str
) -> JsonValue:
    """读取必填 JSON 字段。

    :param mapping: JSON mapping。
    :param field_name: 字段名。
    :returns: JSON 字段值。
    :raises ValueError: 字段缺失时抛出。
    """

    if field_name not in mapping:
        raise ValueError(f"{field_name} is required")
    return mapping[field_name]


def _required_str(mapping: Mapping[str, JsonValue], field_name: str) -> str:
    """读取必填字符串字段。

    :param mapping: JSON mapping。
    :param field_name: 字段名。
    :returns: 字符串值。
    :raises ValueError: 字段缺失、非字符串或为空时抛出。
    """

    return _as_str(_required_value(mapping, field_name), field_name)


def _optional_str(
    mapping: Mapping[str, JsonValue], field_name: str
) -> str | None:
    """读取 optional 字符串字段。

    :param mapping: JSON mapping。
    :param field_name: 字段名。
    :returns: 字符串值或 ``None``。
    :raises ValueError: 字段非字符串或为空时抛出。
    """

    value = _required_value(mapping, field_name)
    if value is None:
        return None
    return _as_str(value, field_name)


def _as_str(value: JsonValue, field_name: str) -> str:
    """把 JSON 值校验为非空字符串。

    :param value: JSON 值。
    :param field_name: 字段名。
    :returns: 字符串值。
    :raises ValueError: 值非字符串或为空时抛出。
    """

    if isinstance(value, str):
        _require_non_empty(value, field_name)
        return value
    raise ValueError(f"{field_name} must be string")


def _required_int(mapping: Mapping[str, JsonValue], field_name: str) -> int:
    """读取必填整数字段。

    :param mapping: JSON mapping。
    :param field_name: 字段名。
    :returns: 整数值。
    :raises ValueError: 字段缺失或非整数时抛出。
    """

    value = _required_value(mapping, field_name)
    if isinstance(value, int):
        return value
    raise ValueError(f"{field_name} must be integer")


def _optional_int(
    mapping: Mapping[str, JsonValue], field_name: str
) -> int | None:
    """读取 optional 整数字段。

    :param mapping: JSON mapping。
    :param field_name: 字段名。
    :returns: 整数值或 ``None``。
    :raises ValueError: 字段非整数时抛出。
    """

    value = _required_value(mapping, field_name)
    if value is None:
        return None
    if isinstance(value, int):
        return value
    raise ValueError(f"{field_name} must be integer")


def _required_list(
    mapping: Mapping[str, JsonValue], field_name: str
) -> list[JsonValue]:
    """读取必填 JSON array 字段。

    :param mapping: JSON mapping。
    :param field_name: 字段名。
    :returns: JSON 值列表。
    :raises ValueError: 字段缺失或非列表时抛出。
    """

    value = _required_value(mapping, field_name)
    if isinstance(value, list):
        return value
    raise ValueError(f"{field_name} must be list")
