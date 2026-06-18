"""Host Conversation Memory vNext typed contracts。

本模块定义 Conversation Memory 的 vNext read model。Memory 只消费已提交的
Host EventLog canonical facts 与 accepted vNext compact payload；它是可重建
projection，不是事实真源，也不导入 Engine / Service / UI / Fins。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeAlias, TypeVar

from dayu.contracts.json_value import JsonValue
from dayu.host.context_events import CONTEXT_COMPACTED as _EVENT_TYPE_CONTEXT_COMPACTED
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.evidence import (
    accepted_evidence_envelope_from_payload,
    accepted_tool_raw_outcome_text_from_payload,
)
from dayu.host.terminal_payload import (
    PayloadTextReadPolicy,
    assistant_final_answer_text_from_run_payload,
)

MemoryPolicyDigest: TypeAlias = str
"""Memory policy canonical JSON digest。"""

MemoryDigestRef: TypeAlias = str
"""Memory provenance digest ref。"""

HostEventRef: TypeAlias = str
"""Host EventLog ref。"""

HostPayloadRef: TypeAlias = str
"""Host payload descriptor ref。"""

CONVERSATION_MEMORY_CONSUMER_ID = "host.memory.session.v1"
"""Conversation Memory projection consumer 稳定 id。"""

CONVERSATION_MEMORY_SNAPSHOT_SCHEMA_VERSION = "conversation_memory_snapshot_v1"
"""ConversationMemorySnapshotVNext schema version。"""

DEFAULT_MEMORY_CONTEXT_WINDOW_SIZE = 8192
DEFAULT_SELECTED_RECENT_WINDOW_ITEM_CAP = 16
DEFAULT_SELECTED_RECENT_WINDOW_CHAR_CAP = 12000
DEFAULT_SELECTED_RECENT_WINDOW_TURN_FLOOR = 2
DEFAULT_FALLBACK_SELECTED_RECENT_WINDOW_ITEM_CAP = 8
DEFAULT_FALLBACK_SELECTED_RECENT_WINDOW_CHAR_CAP = 6000
DEFAULT_EVIDENCE_FACT_ITEM_CAP = 16
DEFAULT_EVIDENCE_FACT_CHAR_CAP = 16000
DEFAULT_EVIDENCE_FACT_FLOOR = 1
DEFAULT_SESSION_SUMMARY_CHAR_CAP = 2400
DEFAULT_ANSWER_ANCHOR_ITEM_CAP = 12
DEFAULT_ANSWER_ANCHOR_CHAR_CAP = 12000
DEFAULT_FORWARD_INTENT_ITEM_CAP = 12
DEFAULT_FORWARD_INTENT_CHAR_CAP = 8000
DEFAULT_REFERENCE_CONTINUITY_ITEM_CAP = 12
DEFAULT_REFERENCE_CONTINUITY_CHAR_CAP = 8000
DEFAULT_REFERENCE_CONTINUITY_ITEM_FLOOR = 0
DEFAULT_MEMORY_MAX_LAG_EVENTS_FOR_INLINE_DELTA = 16
DEFAULT_MEMORY_MAX_DELTA_REPAIR_EVENTS = 32
DEFAULT_MEMORY_POLICY_REF = "default-memory-projection"

_MIN_SEQUENCE = 0
_MIN_POSITIVE_LIMIT = 1
_SNAPSHOT_DIGEST_PENDING = "pending"
_SNAPSHOT_ID_DIGEST_PREFIX = "memory-snapshot-"
_ITEM_ID_PREFIX = "memory-item"
_DIAGNOSTIC_ID_PREFIX = "memory-diagnostic"
_EVENT_TYPE_USER_INPUT_ACCEPTED = "USER_INPUT_ACCEPTED"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_PAYLOAD_FIELD_DISPLAY_TEXT = "display_text"
_PAYLOAD_FIELD_CONTENT = "content"
_PAYLOAD_FIELD_ACCEPTED_CANDIDATE = "accepted_candidate"
_PAYLOAD_FIELD_SCHEMA_VERSION = "schema_version"
_PAYLOAD_FIELD_SESSION_SUMMARY = "session_summary"
_PAYLOAD_FIELD_SUMMARY_TEXT = "summary_text"
_USER_INPUT_TEXT_UNAVAILABLE = "用户输入文本不可用。"
_PAYLOAD_FIELD_SOURCE_LABELS = "source_labels"
_PAYLOAD_FIELD_EVIDENCE_BACKED_FACTS = "evidence_backed_facts"
_PAYLOAD_FIELD_CLAIM_TEXT = "claim_text"
_PAYLOAD_FIELD_EVIDENCE_LABELS = "evidence_labels"
_PAYLOAD_FIELD_ANSWER_ANCHORS = "answer_anchors"
_PAYLOAD_FIELD_ANCHOR_TITLE = "anchor_title"
_PAYLOAD_FIELD_ANCHOR_ITEMS = "anchor_items"
_PAYLOAD_FIELD_ORDINAL = "ordinal"
_PAYLOAD_FIELD_ANSWER_SOURCE_LABELS = "answer_source_labels"
_PAYLOAD_FIELD_FORWARD_INTENTS = "forward_intents"
_PAYLOAD_FIELD_INTENT_TYPE = "intent_type"
_PAYLOAD_FIELD_STATUS = "status"
_PAYLOAD_FIELD_TEXT = "text"
_PAYLOAD_FIELD_REFERENCE_CONTINUITY_ITEMS = "reference_continuity_items"
_PAYLOAD_FIELD_REASON = "reason"
_PAYLOAD_FIELD_DIAGNOSTICS = "diagnostics"
_PAYLOAD_FIELD_MESSAGE = "message"
_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS = "accepted_evidence_mapping_refs"
_PAYLOAD_FIELD_COMPACT_ARTIFACT_REF = "compact_artifact_ref"

_MemoryItemT = TypeVar("_MemoryItemT", bound="_MemoryItemWithId")


class MemoryClaimStatus(StrEnum):
    """Host 中立 memory claim 状态枚举。"""

    EVIDENCE_BACKED = "evidence_backed"
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
    """Host 中立 opaque ref 类型。"""

    SOURCE = "source"
    CHUNK = "chunk"
    ENTITY = "entity"
    SUBJECT = "subject"
    TOPIC = "topic"
    EVIDENCE = "evidence"
    PAYLOAD = "payload"
    EXTERNAL = "external"


class MemoryIncludedReason(StrEnum):
    """Memory item 被纳入 snapshot 的原因。"""

    SELECTED_RECENT_WINDOW = "selected_recent_window"
    EVIDENCE_BACKED_FACT = "evidence_backed_fact"
    SESSION_SUMMARY = "session_summary"
    ANSWER_ANCHOR = "answer_anchor"
    FORWARD_INTENT = "forward_intent"
    REFERENCE_CONTINUITY = "reference_continuity"
    RECENT_EVIDENCE = "recent_evidence"
    EMPTY_SNAPSHOT = "empty_snapshot"


class MemoryExcludedReason(StrEnum):
    """Memory item 被排除出 snapshot 的原因。"""

    BUDGET_LIMIT = "budget_limit"
    MISSING_PROVENANCE = "missing_provenance"
    UNSUPPORTED_EVENT_TYPE = "unsupported_event_type"
    POLICY_EXCLUDED = "policy_excluded"


class SelectedRecentWindowRole(StrEnum):
    """selected recent window item 的角色。"""

    USER = "user"
    ASSISTANT = "assistant"
    USER_VISIBLE_STATE = "user_visible_state"
    EVIDENCE = "evidence"


class MemoryEvidenceBackedFactKind(StrEnum):
    """Evidence-backed fact 的 Host-neutral 类型。"""

    DERIVED_FROM_EVIDENCE = "derived_from_evidence"


class MemoryDiagnosticReason(StrEnum):
    """Memory diagnostic 的结构化原因。"""

    EVIDENCE_BACKED_FACT_CANDIDATE_INVALID = (
        "evidence_backed_fact_candidate_invalid"
    )
    ACCEPTED_EVIDENCE_WITHOUT_FACT_CANDIDATE = (
        "accepted_evidence_without_fact_candidate"
    )
    INLINE_DELTA_REPAIR_INCLUDED = "inline_delta_repair_included"
    SNAPSHOT_MISSING = "snapshot_missing"
    SNAPSHOT_DAMAGED = "snapshot_damaged"
    UNSUPPORTED_EVENT_TYPE = "unsupported_event_type"
    SNAPSHOT_LAG_OVER_THRESHOLD = "snapshot_lag_over_threshold"
    BUDGET_LIMIT_REACHED = "budget_limit_reached"
    EMPTY_EVENT_LOG_SNAPSHOT = "empty_event_log_snapshot"
    EVIDENCE_BACKED_FACT_SUPERSEDED = "evidence_backed_fact_superseded"


class MemoryRepairReason(StrEnum):
    """Memory snapshot 需要 repair 的结构化原因。"""

    SNAPSHOT_MISSING = "snapshot_missing"
    SNAPSHOT_DAMAGED = "snapshot_damaged"
    SNAPSHOT_LAG_OVER_THRESHOLD = "snapshot_lag_over_threshold"
    INLINE_DELTA_REPAIR_VIEW_MISSING = "inline_delta_repair_view_missing"
    SNAPSHOT_AHEAD_OF_REQUIRED = "snapshot_ahead_of_required"


class _MemoryItemWithId(Protocol):
    """仅用于内部泛型去重的 item 协议。

    :param item_id: memory item id。
    :param event_sequence: 来源 EventLog sequence。
    :param size_units: item 文本尺寸。
    """

    @property
    def item_id(self) -> str:
        """返回 item id。

        :returns: item id。
        """

        ...

    @property
    def event_sequence(self) -> int:
        """返回来源 EventLog sequence。

        :returns: event sequence。
        """

        ...

    @property
    def size_units(self) -> MemorySizeUnits:
        """返回 item 文本尺寸。

        :returns: size units。
        """

        ...


@dataclass(frozen=True, slots=True)
class MemorySizeUnits:
    """Memory 文本尺寸单位。

    :param units: 保守估算后的字符尺寸，必须非负。
    """

    units: int

    def __post_init__(self) -> None:
        """校验尺寸单位。

        :returns: ``None``。
        :raises ValueError: ``units`` 为负数时抛出。
        """

        if self.units < 0:
            raise ValueError("memory size units must be non-negative")


@dataclass(frozen=True, slots=True)
class MemorySnapshotCursor:
    """Memory snapshot 覆盖的 projection cursor。

    :param consumer_id: memory projection consumer 稳定 id。
    :param checkpoint_event_sequence: 已覆盖 EventLog sequence。
    :param checkpoint_event_id: 已覆盖 EventLog id；空 cursor 为 ``None``。
    :param session_id: cursor 所属 session id。
    """

    consumer_id: str
    checkpoint_event_sequence: int
    checkpoint_event_id: str | None
    session_id: str

    def __post_init__(self) -> None:
        """校验 cursor。

        :returns: ``None``。
        :raises ValueError: 字段为空或 cursor 不一致时抛出。
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

    :param ref_kind: ref 类型。
    :param ref_id: ref id。
    :param digest: 可选 digest。
    """

    ref_kind: HostNeutralRefKind
    ref_id: str
    digest: str | None = None

    def __post_init__(self) -> None:
        """校验 opaque ref。

        :returns: ``None``。
        :raises ValueError: 字段非法时抛出。
        """

        if not isinstance(self.ref_kind, HostNeutralRefKind):
            raise ValueError("ref_kind must be HostNeutralRefKind")
        _require_non_empty(self.ref_id, "ref_id")
        _require_optional_non_empty(self.digest, "digest")


@dataclass(frozen=True, slots=True)
class MemoryProvenanceRef:
    """Memory item provenance ref。

    :param producer_kind: producer 类型。
    :param producer_name: producer 名称。
    :param event_id: 来源 EventLog id。
    :param event_sequence: 来源 EventLog sequence。
    :param run_id: 可选 Run id。
    :param attempt_id: 可选 Attempt id。
    :param execution_id: 可选 execution id。
    :param tool_result_ref: 可选工具结果 ref。
    :param payload_ref: 可选 payload ref。
    :param digest_ref: 来源内容 digest ref。
    :param source_refs: Host 内部来源 refs。
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
        """校验 provenance ref。

        :returns: ``None``。
        :raises ValueError: 字段非法时抛出。
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
class SelectedRecentWindowItem:
    """selected recent window 中的有界可读 item。

    :param item_id: item 稳定 id。
    :param role: item 角色。
    :param text: LLM 可读文本。
    :param event_id: 来源 EventLog id。
    :param event_sequence: 来源 EventLog sequence。
    :param run_id: 可选 Run id。
    :param source_refs: Host 内部来源 refs。
    :param included_reason: 纳入原因。
    :param excluded_reason: 排除原因。
    :param size_units: 文本尺寸。
    """

    item_id: str
    role: SelectedRecentWindowRole
    text: str
    event_id: str
    event_sequence: int
    run_id: str | None
    source_refs: tuple[str, ...]
    included_reason: MemoryIncludedReason | None
    excluded_reason: MemoryExcludedReason | None
    size_units: MemorySizeUnits

    def __post_init__(self) -> None:
        """校验 selected recent window item。

        :returns: ``None``。
        :raises ValueError: 字段非法时抛出。
        """

        _require_non_empty(self.item_id, "item_id")
        if not isinstance(self.role, SelectedRecentWindowRole):
            raise ValueError("role must be SelectedRecentWindowRole")
        _require_non_empty(self.text, "text")
        _require_non_empty(self.event_id, "event_id")
        if self.event_sequence <= _MIN_SEQUENCE:
            raise ValueError("event_sequence must be positive")
        _require_optional_non_empty(self.run_id, "run_id")
        _require_non_empty_items(self.source_refs, "source_refs")
        _validate_reason_pair(self.included_reason, self.excluded_reason)


@dataclass(frozen=True, slots=True)
class ReferenceContinuityItem:
    """Trace Memory 下的 reference continuity item。

    :param item_id: item 稳定 id。
    :param text: 连续性文本。
    :param reason: 保留原因。
    :param source_refs: Host 内部来源 refs。
    :param event_id: compact event id。
    :param event_sequence: compact event sequence。
    :param size_units: 文本尺寸。
    """

    item_id: str
    text: str
    reason: str
    source_refs: tuple[str, ...]
    event_id: str
    event_sequence: int
    size_units: MemorySizeUnits

    def __post_init__(self) -> None:
        """校验 reference continuity item。

        :returns: ``None``。
        :raises ValueError: 字段非法时抛出。
        """

        _require_non_empty(self.item_id, "item_id")
        _require_non_empty(self.text, "text")
        _require_non_empty(self.reason, "reason")
        _require_non_empty_items(self.source_refs, "source_refs")
        _require_non_empty(self.event_id, "event_id")
        if self.event_sequence <= _MIN_SEQUENCE:
            raise ValueError("event_sequence must be positive")


@dataclass(frozen=True, slots=True)
class EvidenceBackedFactView:
    """Evidence / Fact Memory 中的 evidence-backed fact。

    :param item_id: item 稳定 id。
    :param claim_text: 绑定 accepted evidence 的事实声明文本。
    :param evidence_kind: 事实声明类型。
    :param evidence_refs: accepted evidence refs。
    :param provenance: 来源 compact event provenance。
    :param extraction_operation_ref: Host extraction operation ref。
    :param compact_artifact_ref: compact artifact ref。
    :param candidate_id: candidate-local id。
    :param included_reason: 纳入原因。
    :param excluded_reason: 排除原因。
    :param size_units: 文本尺寸。
    """

    item_id: str
    claim_text: str
    evidence_kind: MemoryEvidenceBackedFactKind
    evidence_refs: tuple[str, ...]
    provenance: MemoryProvenanceRef
    extraction_operation_ref: str
    compact_artifact_ref: str | None
    candidate_id: str
    included_reason: MemoryIncludedReason | None
    excluded_reason: MemoryExcludedReason | None
    size_units: MemorySizeUnits

    def __post_init__(self) -> None:
        """校验 evidence-backed fact。

        :returns: ``None``。
        :raises ValueError: 字段非法时抛出。
        """

        _require_non_empty(self.item_id, "item_id")
        _require_non_empty(self.claim_text, "claim_text")
        if not isinstance(self.evidence_kind, MemoryEvidenceBackedFactKind):
            raise ValueError("evidence_kind must be MemoryEvidenceBackedFactKind")
        _require_non_empty_items(self.evidence_refs, "evidence_refs")
        if self.provenance.producer_kind is not MemoryProducerKind.HOST_PROJECTION:
            raise ValueError("fact provenance producer must be HOST_PROJECTION")
        _require_non_empty(self.extraction_operation_ref, "extraction_operation_ref")
        _require_optional_non_empty(self.compact_artifact_ref, "compact_artifact_ref")
        _require_non_empty(self.candidate_id, "candidate_id")
        _validate_reason_pair(self.included_reason, self.excluded_reason)

    @property
    def event_sequence(self) -> int:
        """返回 fact 来源 compact event sequence。

        :returns: compact event sequence。
        """

        return self.provenance.event_sequence


@dataclass(frozen=True, slots=True)
class SessionSummaryMemoryView:
    """Session Summary Memory view。

    :param summary_text: accepted compact session summary；无则为 ``None``。
    :param source_refs: Host 内部来源 refs。
    :param event_id: 来源 compact event id。
    :param event_sequence: 来源 compact event sequence。
    :param size_units: 文本尺寸。
    """

    summary_text: str | None
    source_refs: tuple[str, ...]
    event_id: str | None
    event_sequence: int | None
    size_units: MemorySizeUnits

    def __post_init__(self) -> None:
        """校验 session summary view。

        :returns: ``None``。
        :raises ValueError: 字段非法时抛出。
        """

        _require_optional_non_empty(self.summary_text, "summary_text")
        _require_non_empty_items(self.source_refs, "source_refs")
        _require_optional_non_empty(self.event_id, "event_id")
        if self.event_sequence is not None and self.event_sequence <= _MIN_SEQUENCE:
            raise ValueError("event_sequence must be positive")
        if (self.summary_text is None) != (self.event_id is None):
            raise ValueError("summary_text and event_id must be paired")


@dataclass(frozen=True, slots=True)
class AnswerAnchorChild:
    """Answer Anchor 子项。

    :param display_text: 展示文本。
    :param ordinal: 可选序号。
    """

    display_text: str
    ordinal: int | None

    def __post_init__(self) -> None:
        """校验 answer anchor 子项。

        :returns: ``None``。
        :raises ValueError: 字段非法时抛出。
        """

        _require_non_empty(self.display_text, "display_text")
        if self.ordinal is not None and self.ordinal < 0:
            raise ValueError("ordinal must be non-negative")


@dataclass(frozen=True, slots=True)
class AnswerAnchor:
    """Answer Anchor Memory item。

    :param item_id: item 稳定 id。
    :param anchor_title: anchor 标题。
    :param anchor_items: 子项。
    :param source_refs: Host 内部来源 refs。
    :param event_id: 来源 compact event id。
    :param event_sequence: 来源 compact event sequence。
    :param size_units: 文本尺寸。
    """

    item_id: str
    anchor_title: str
    anchor_items: tuple[AnswerAnchorChild, ...]
    source_refs: tuple[str, ...]
    event_id: str
    event_sequence: int
    size_units: MemorySizeUnits

    def __post_init__(self) -> None:
        """校验 answer anchor。

        :returns: ``None``。
        :raises ValueError: 字段非法时抛出。
        """

        _require_non_empty(self.item_id, "item_id")
        _require_non_empty(self.anchor_title, "anchor_title")
        if len(self.anchor_items) == 0:
            raise ValueError("anchor_items must be non-empty")
        _require_non_empty_items(self.source_refs, "source_refs")
        _require_non_empty(self.event_id, "event_id")
        if self.event_sequence <= _MIN_SEQUENCE:
            raise ValueError("event_sequence must be positive")


@dataclass(frozen=True, slots=True)
class ForwardIntent:
    """Forward Intent Memory item。

    :param item_id: item 稳定 id。
    :param intent_type: intent 类型。
    :param text: intent 文本。
    :param status: intent 状态。
    :param source_refs: Host 内部来源 refs。
    :param event_id: 来源 compact event id。
    :param event_sequence: 来源 compact event sequence。
    :param size_units: 文本尺寸。
    """

    item_id: str
    intent_type: str
    text: str
    status: str
    source_refs: tuple[str, ...]
    event_id: str
    event_sequence: int
    size_units: MemorySizeUnits

    def __post_init__(self) -> None:
        """校验 forward intent。

        :returns: ``None``。
        :raises ValueError: 字段非法时抛出。
        """

        _require_non_empty(self.item_id, "item_id")
        _require_non_empty(self.intent_type, "intent_type")
        _require_non_empty(self.text, "text")
        _require_non_empty(self.status, "status")
        _require_non_empty_items(self.source_refs, "source_refs")
        _require_non_empty(self.event_id, "event_id")
        if self.event_sequence <= _MIN_SEQUENCE:
            raise ValueError("event_sequence must be positive")


@dataclass(frozen=True, slots=True)
class TraceMemoryView:
    """Trace Memory view。

    :param selected_recent_window: compact 前 / post-compact delta 的 recent window。
    :param reference_continuity_items: accepted compact 生成的指代连续性项。
    """

    selected_recent_window: tuple[SelectedRecentWindowItem, ...]
    reference_continuity_items: tuple[ReferenceContinuityItem, ...]


@dataclass(frozen=True, slots=True)
class EvidenceFactMemoryView:
    """Evidence / Fact Memory view。

    :param evidence_backed_facts: accepted compact 物化的 facts。
    :param recent_evidence_items: selected recent window 中的 readable evidence。
    """

    evidence_backed_facts: tuple[EvidenceBackedFactView, ...]
    recent_evidence_items: tuple[SelectedRecentWindowItem, ...]


@dataclass(frozen=True, slots=True)
class AnswerAnchorMemoryView:
    """Answer Anchor Memory view。

    :param anchors: answer anchors。
    """

    anchors: tuple[AnswerAnchor, ...]


@dataclass(frozen=True, slots=True)
class ForwardIntentMemoryView:
    """Forward Intent Memory view。

    :param intents: forward intents。
    """

    intents: tuple[ForwardIntent, ...]


@dataclass(frozen=True, slots=True)
class MemoryDiagnostic:
    """Memory projection diagnostic。

    :param diagnostic_id: diagnostic 稳定 id。
    :param reason: 结构化原因。
    :param message: 中立说明。
    :param event_sequence: 可选 EventLog sequence。
    :param item_id: 可选 item id。
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
        """校验 diagnostic。

        :returns: ``None``。
        :raises ValueError: 字段非法时抛出。
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
class MemoryRepairRequest:
    """Memory projection repair 请求。

    :param session_id: 需要 repair 的 Session id。
    :param reason: repair 结构化原因。
    :param required_event_sequence: 本次需要覆盖的 EventLog cursor。
    :param observed_cursor: 已观测 snapshot cursor。
    :param policy_digest: 当前 memory policy digest。
    """

    session_id: str
    reason: MemoryRepairReason
    required_event_sequence: int
    observed_cursor: MemorySnapshotCursor | None
    policy_digest: MemoryPolicyDigest

    def __post_init__(self) -> None:
        """校验 repair 请求。

        :returns: ``None``。
        :raises ValueError: 字段非法时抛出。
        """

        _require_non_empty(self.session_id, "session_id")
        if not isinstance(self.reason, MemoryRepairReason):
            raise ValueError("reason must be MemoryRepairReason")
        if self.required_event_sequence < _MIN_SEQUENCE:
            raise ValueError("required_event_sequence must be non-negative")
        _require_non_empty(self.policy_digest, "policy_digest")


@dataclass(frozen=True, slots=True)
class MemoryProjectionPolicy:
    """Memory projection policy。

    :param context_window_size: effective model context window。
    :param selected_recent_window_item_cap: selected recent window item 上限。
    :param selected_recent_window_char_cap: selected recent window 字符上限。
    :param selected_recent_window_turn_floor: selected recent window 近轮保底。
    :param fallback_selected_recent_window_item_cap: fallback recent window item 上限。
    :param fallback_selected_recent_window_char_cap: fallback recent window 字符上限。
    :param evidence_fact_item_cap: evidence-backed fact item 上限。
    :param evidence_fact_char_cap: evidence-backed fact 字符上限。
    :param evidence_fact_floor: evidence-backed fact 保底数量。
    :param session_summary_char_cap: session summary 字符上限。
    :param answer_anchor_item_cap: answer anchor item 上限。
    :param answer_anchor_char_cap: answer anchor 字符上限。
    :param forward_intent_item_cap: forward intent item 上限。
    :param forward_intent_char_cap: forward intent 字符上限。
    :param reference_continuity_item_cap: reference continuity item 上限。
    :param reference_continuity_char_cap: reference continuity 字符上限。
    :param reference_continuity_item_floor: reference continuity item 保底数量。
    :param max_lag_events_for_inline_delta: inline delta 允许滞后事件数。
    :param max_delta_repair_events: repair delta 最大事件数。
    :param policy_ref: policy snapshot / composition ref。
    """

    context_window_size: int
    selected_recent_window_item_cap: int
    selected_recent_window_char_cap: int
    selected_recent_window_turn_floor: int
    fallback_selected_recent_window_item_cap: int
    fallback_selected_recent_window_char_cap: int
    evidence_fact_item_cap: int
    evidence_fact_char_cap: int
    evidence_fact_floor: int
    session_summary_char_cap: int
    answer_anchor_item_cap: int
    answer_anchor_char_cap: int
    forward_intent_item_cap: int
    forward_intent_char_cap: int
    reference_continuity_item_cap: int
    reference_continuity_char_cap: int
    reference_continuity_item_floor: int
    max_lag_events_for_inline_delta: int
    max_delta_repair_events: int
    policy_ref: str

    def __post_init__(self) -> None:
        """校验 policy limit。

        :returns: ``None``。
        :raises ValueError: 任一字段非法时抛出。
        """

        _require_positive(self.context_window_size, "context_window_size")
        _require_positive(
            self.selected_recent_window_item_cap,
            "selected_recent_window_item_cap",
        )
        _require_positive(
            self.selected_recent_window_char_cap,
            "selected_recent_window_char_cap",
        )
        _require_non_negative(
            self.selected_recent_window_turn_floor,
            "selected_recent_window_turn_floor",
        )
        _require_positive(
            self.fallback_selected_recent_window_item_cap,
            "fallback_selected_recent_window_item_cap",
        )
        _require_positive(
            self.fallback_selected_recent_window_char_cap,
            "fallback_selected_recent_window_char_cap",
        )
        _require_positive(self.evidence_fact_item_cap, "evidence_fact_item_cap")
        _require_positive(self.evidence_fact_char_cap, "evidence_fact_char_cap")
        _require_non_negative(self.evidence_fact_floor, "evidence_fact_floor")
        _require_positive(
            self.session_summary_char_cap,
            "session_summary_char_cap",
        )
        _require_positive(self.answer_anchor_item_cap, "answer_anchor_item_cap")
        _require_positive(self.answer_anchor_char_cap, "answer_anchor_char_cap")
        _require_positive(self.forward_intent_item_cap, "forward_intent_item_cap")
        _require_positive(self.forward_intent_char_cap, "forward_intent_char_cap")
        _require_positive(
            self.reference_continuity_item_cap,
            "reference_continuity_item_cap",
        )
        _require_positive(
            self.reference_continuity_char_cap,
            "reference_continuity_char_cap",
        )
        _require_non_negative(
            self.reference_continuity_item_floor,
            "reference_continuity_item_floor",
        )
        _require_non_negative(
            self.max_lag_events_for_inline_delta,
            "max_lag_events_for_inline_delta",
        )
        _require_non_negative(
            self.max_delta_repair_events,
            "max_delta_repair_events",
        )
        _require_non_empty(self.policy_ref, "policy_ref")
        if self.fallback_selected_recent_window_item_cap < (
            self.selected_recent_window_turn_floor
        ):
            raise ValueError(
                "fallback_selected_recent_window_item_cap must cover selected_recent_window_turn_floor"
            )
        if (
            self.fallback_selected_recent_window_item_cap
            > self.selected_recent_window_item_cap
        ):
            raise ValueError(
                "fallback_selected_recent_window_item_cap must not exceed selected_recent_window_item_cap"
            )
        if (
            self.fallback_selected_recent_window_char_cap
            > self.selected_recent_window_char_cap
        ):
            raise ValueError(
                "fallback_selected_recent_window_char_cap must not exceed selected_recent_window_char_cap"
            )
        if self.evidence_fact_floor > self.evidence_fact_item_cap:
            raise ValueError("evidence_fact_floor must not exceed evidence_fact_item_cap")
        if self.reference_continuity_item_floor > self.reference_continuity_item_cap:
            raise ValueError(
                "reference_continuity_item_floor must not exceed reference_continuity_item_cap"
            )


@dataclass(frozen=True, slots=True)
class ConversationMemorySnapshotVNext:
    """Conversation Memory vNext snapshot。

    :param schema_version: snapshot schema version。
    :param snapshot_id: snapshot 稳定 id。
    :param session_id: session id。
    :param cursor: snapshot 覆盖的 EventLog cursor。
    :param policy_digest: projection policy digest。
    :param latest_compaction_event_ref: 最新 accepted compact event ref。
    :param trace_memory: Trace Memory view。
    :param evidence_fact_memory: Evidence / Fact Memory view。
    :param session_summary_memory: Session Summary Memory view。
    :param answer_anchor_memory: Answer Anchor Memory view。
    :param forward_intent_memory: Forward Intent Memory view。
    :param diagnostics: projection diagnostics。
    :param built_at: snapshot 构建时间。
    :param snapshot_digest: snapshot canonical digest。
    """

    schema_version: str
    snapshot_id: str
    session_id: str
    cursor: MemorySnapshotCursor
    policy_digest: MemoryPolicyDigest
    latest_compaction_event_ref: str | None
    trace_memory: TraceMemoryView
    evidence_fact_memory: EvidenceFactMemoryView
    session_summary_memory: SessionSummaryMemoryView
    answer_anchor_memory: AnswerAnchorMemoryView
    forward_intent_memory: ForwardIntentMemoryView
    diagnostics: tuple[MemoryDiagnostic, ...]
    built_at: str
    snapshot_digest: str

    def __post_init__(self) -> None:
        """校验 snapshot。

        :returns: ``None``。
        :raises ValueError: 字段非法时抛出。
        """

        if self.schema_version != CONVERSATION_MEMORY_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("schema_version is invalid")
        _require_non_empty(self.snapshot_id, "snapshot_id")
        _require_non_empty(self.session_id, "session_id")
        _require_non_empty(self.policy_digest, "policy_digest")
        _require_optional_non_empty(
            self.latest_compaction_event_ref,
            "latest_compaction_event_ref",
        )
        _require_non_empty(self.built_at, "built_at")
        _require_non_empty(self.snapshot_digest, "snapshot_digest")
        if self.cursor.session_id != self.session_id:
            raise ValueError("snapshot session_id must match cursor session_id")


@dataclass(frozen=True, slots=True)
class MemoryProjectionEvent:
    """Memory projection 使用的 Host 中立 EventLog view。

    :param event_sequence: EventLog sequence。
    :param event_id: EventLog id。
    :param event_class: EventLog class。
    :param event_type: EventLog type。
    :param session_id: Session id。
    :param run_id: 可选 Run id。
    :param attempt_id: 可选 Attempt id。
    :param execution_id: 可选 execution id。
    :param occurred_at: 事件发生时间。
    :param payload_ref: 可选 payload ref。
    :param payload_digest: 可选 payload digest。
    :param payload: 已解析 canonical payload。
    """

    event_sequence: int
    event_id: str
    event_class: str
    event_type: str
    session_id: str
    run_id: str | None
    attempt_id: str | None
    execution_id: str | None
    occurred_at: str
    payload_ref: str | None
    payload_digest: str | None
    payload: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        """校验 projection event。

        :returns: ``None``。
        :raises ValueError: 字段非法时抛出。
        """

        if self.event_sequence <= _MIN_SEQUENCE:
            raise ValueError("event_sequence must be positive")
        _require_non_empty(self.event_id, "event_id")
        _require_non_empty(self.event_class, "event_class")
        _require_non_empty(self.event_type, "event_type")
        _require_non_empty(self.session_id, "session_id")
        _require_non_empty(self.occurred_at, "occurred_at")
        _require_optional_non_empty(self.run_id, "run_id")
        _require_optional_non_empty(self.attempt_id, "attempt_id")
        _require_optional_non_empty(self.execution_id, "execution_id")
        _require_optional_non_empty(self.payload_ref, "payload_ref")
        _require_optional_non_empty(self.payload_digest, "payload_digest")
        if (self.payload_ref is None) != (self.payload_digest is None):
            raise ValueError("payload_ref and payload_digest must be paired")


def default_memory_projection_policy(
    *, context_window_size: int = DEFAULT_MEMORY_CONTEXT_WINDOW_SIZE
) -> MemoryProjectionPolicy:
    """构造默认 Conversation Memory projection policy。

    :param context_window_size: effective model context window。
    :returns: 默认 memory projection policy。
    :raises ValueError: 默认常量非法时抛出。
    """

    return MemoryProjectionPolicy(
        context_window_size=context_window_size,
        selected_recent_window_item_cap=DEFAULT_SELECTED_RECENT_WINDOW_ITEM_CAP,
        selected_recent_window_char_cap=DEFAULT_SELECTED_RECENT_WINDOW_CHAR_CAP,
        selected_recent_window_turn_floor=DEFAULT_SELECTED_RECENT_WINDOW_TURN_FLOOR,
        fallback_selected_recent_window_item_cap=(
            DEFAULT_FALLBACK_SELECTED_RECENT_WINDOW_ITEM_CAP
        ),
        fallback_selected_recent_window_char_cap=(
            DEFAULT_FALLBACK_SELECTED_RECENT_WINDOW_CHAR_CAP
        ),
        evidence_fact_item_cap=DEFAULT_EVIDENCE_FACT_ITEM_CAP,
        evidence_fact_char_cap=DEFAULT_EVIDENCE_FACT_CHAR_CAP,
        evidence_fact_floor=DEFAULT_EVIDENCE_FACT_FLOOR,
        session_summary_char_cap=DEFAULT_SESSION_SUMMARY_CHAR_CAP,
        answer_anchor_item_cap=DEFAULT_ANSWER_ANCHOR_ITEM_CAP,
        answer_anchor_char_cap=DEFAULT_ANSWER_ANCHOR_CHAR_CAP,
        forward_intent_item_cap=DEFAULT_FORWARD_INTENT_ITEM_CAP,
        forward_intent_char_cap=DEFAULT_FORWARD_INTENT_CHAR_CAP,
        reference_continuity_item_cap=DEFAULT_REFERENCE_CONTINUITY_ITEM_CAP,
        reference_continuity_char_cap=DEFAULT_REFERENCE_CONTINUITY_CHAR_CAP,
        reference_continuity_item_floor=DEFAULT_REFERENCE_CONTINUITY_ITEM_FLOOR,
        max_lag_events_for_inline_delta=(
            DEFAULT_MEMORY_MAX_LAG_EVENTS_FOR_INLINE_DELTA
        ),
        max_delta_repair_events=DEFAULT_MEMORY_MAX_DELTA_REPAIR_EVENTS,
        policy_ref=DEFAULT_MEMORY_POLICY_REF,
    )


def estimate_memory_size_units(text: str) -> MemorySizeUnits:
    """估算 memory 文本尺寸。

    :param text: 待估算文本。
    :returns: 字符数尺寸单位。
    :raises ValueError: ``text`` 非字符串时抛出。
    """

    if not isinstance(text, str):
        raise ValueError("text must be str")
    return MemorySizeUnits(units=len(text))


def digest_memory_projection_policy(policy: MemoryProjectionPolicy) -> MemoryPolicyDigest:
    """计算 memory projection policy digest。

    :param policy: memory projection policy。
    :returns: policy canonical JSON sha256 digest。
    """

    return sha256_digest_json(memory_projection_policy_to_json_value(policy))


def calculate_memory_snapshot_digest(snapshot: ConversationMemorySnapshotVNext) -> str:
    """计算 snapshot canonical digest。

    :param snapshot: memory snapshot。
    :returns: snapshot canonical JSON sha256 digest。
    """

    return sha256_digest_json(_snapshot_digest_json_value(snapshot))


def stable_memory_snapshot_id(
    *,
    session_id: str,
    consumer_id: str,
    policy_digest: MemoryPolicyDigest,
) -> str:
    """派生稳定 memory snapshot id。

    :param session_id: Session id。
    :param consumer_id: memory consumer id。
    :param policy_digest: memory policy digest。
    :returns: 稳定 snapshot id。
    """

    digest = sha256_digest_json(
        {
            "consumer_id": consumer_id,
            "policy_digest": policy_digest,
            "session_id": session_id,
        }
    ).removeprefix("sha256:")
    return f"{_SNAPSHOT_ID_DIGEST_PREFIX}{digest}"


def build_empty_conversation_memory_snapshot(
    *,
    snapshot_id: str,
    session_id: str,
    consumer_id: str,
    policy_digest: MemoryPolicyDigest,
    built_at: str,
) -> ConversationMemorySnapshotVNext:
    """构造空 Conversation Memory snapshot。

    :param snapshot_id: snapshot id。
    :param session_id: session id。
    :param consumer_id: memory consumer id。
    :param policy_digest: memory policy digest。
    :param built_at: 构建时间。
    :returns: 空 snapshot。
    """

    cursor = MemorySnapshotCursor(
        consumer_id=consumer_id,
        checkpoint_event_sequence=_MIN_SEQUENCE,
        checkpoint_event_id=None,
        session_id=session_id,
    )
    without_digest = ConversationMemorySnapshotVNext(
        schema_version=CONVERSATION_MEMORY_SNAPSHOT_SCHEMA_VERSION,
        snapshot_id=snapshot_id,
        session_id=session_id,
        cursor=cursor,
        policy_digest=policy_digest,
        latest_compaction_event_ref=None,
        trace_memory=TraceMemoryView(
            selected_recent_window=(),
            reference_continuity_items=(),
        ),
        evidence_fact_memory=EvidenceFactMemoryView(
            evidence_backed_facts=(),
            recent_evidence_items=(),
        ),
        session_summary_memory=SessionSummaryMemoryView(
            summary_text=None,
            source_refs=(),
            event_id=None,
            event_sequence=None,
            size_units=MemorySizeUnits(0),
        ),
        answer_anchor_memory=AnswerAnchorMemoryView(anchors=()),
        forward_intent_memory=ForwardIntentMemoryView(intents=()),
        diagnostics=(),
        built_at=built_at,
        snapshot_digest=_SNAPSHOT_DIGEST_PENDING,
    )
    return _snapshot_with_digest(without_digest)


def build_conversation_memory_snapshot_from_events(
    *,
    events: tuple[MemoryProjectionEvent, ...],
    session_id: str,
    consumer_id: str,
    policy: MemoryProjectionPolicy,
    built_at: str,
) -> ConversationMemorySnapshotVNext:
    """从 EventLog event 集合重建 memory snapshot。

    :param events: 按 EventLog sequence 升序排列的 projection events。
    :param session_id: 目标 session id。
    :param consumer_id: memory consumer id。
    :param policy: memory policy。
    :param built_at: 构建时间。
    :returns: 重建后的 snapshot。
    :raises ValueError: 输入顺序倒退时抛出。
    """

    snapshot: ConversationMemorySnapshotVNext | None = None
    previous_sequence = _MIN_SEQUENCE
    for event in events:
        if event.event_sequence <= previous_sequence:
            raise ValueError("memory projection events must be ordered by sequence")
        previous_sequence = event.event_sequence
        if event.session_id != session_id:
            continue
        snapshot = project_conversation_memory_event(
            previous_snapshot=snapshot,
            event=event,
            policy=policy,
            built_at=built_at,
            consumer_id=consumer_id,
        )
    if snapshot is not None:
        return snapshot
    return build_empty_conversation_memory_snapshot(
        snapshot_id=stable_memory_snapshot_id(
            session_id=session_id,
            consumer_id=consumer_id,
            policy_digest=digest_memory_projection_policy(policy),
        ),
        session_id=session_id,
        consumer_id=consumer_id,
        policy_digest=digest_memory_projection_policy(policy),
        built_at=built_at,
    )


def project_conversation_memory_event(
    *,
    previous_snapshot: ConversationMemorySnapshotVNext | None,
    event: MemoryProjectionEvent,
    policy: MemoryProjectionPolicy,
    built_at: str,
    consumer_id: str,
) -> ConversationMemorySnapshotVNext:
    """把单个 EventLog event 投影为新 snapshot。

    :param previous_snapshot: 同 session / policy 的既有 snapshot。
    :param event: 当前 projection event。
    :param policy: memory projection policy。
    :param built_at: 新 snapshot 构建时间。
    :param consumer_id: memory consumer id。
    :returns: 覆盖当前 event cursor 的 snapshot。
    """

    policy_digest = digest_memory_projection_policy(policy)
    base = _empty_or_valid_previous_snapshot(
        previous_snapshot=previous_snapshot,
        event=event,
        policy_digest=policy_digest,
        consumer_id=consumer_id,
        built_at=built_at,
    )
    selected = base.trace_memory.selected_recent_window
    recent_evidence = base.evidence_fact_memory.recent_evidence_items
    facts = base.evidence_fact_memory.evidence_backed_facts
    reference_items = base.trace_memory.reference_continuity_items
    session_summary = base.session_summary_memory
    anchors = base.answer_anchor_memory.anchors
    intents = base.forward_intent_memory.intents
    diagnostics = base.diagnostics
    latest_compaction_event_ref = base.latest_compaction_event_ref

    if event.event_type == _EVENT_TYPE_USER_INPUT_ACCEPTED:
        selected = _replace_item_by_id(selected, _selected_user_item(event))
    elif event.event_type == _EVENT_TYPE_RUN_SUCCEEDED:
        assistant_item = _selected_assistant_item(event)
        if assistant_item is not None:
            selected = _replace_item_by_id(selected, assistant_item)
    elif event.event_type == _EVENT_TYPE_TOOL_RESULT_ACCEPTED:
        evidence_item = _selected_evidence_item(event)
        selected = _replace_item_by_id(selected, evidence_item)
        recent_evidence = _replace_item_by_id(recent_evidence, evidence_item)
    elif event.event_type == _EVENT_TYPE_CONTEXT_COMPACTED:
        accepted = _accepted_candidate_mapping(event.payload)
        latest_compaction_event_ref = event.event_id
        session_summary, summary_diagnostics = _session_summary_from_accepted_event(
            event,
            policy,
        )
        diagnostics = diagnostics + summary_diagnostics
        new_facts, fact_diagnostics = _facts_from_accepted_event(event, policy)
        diagnostics = diagnostics + fact_diagnostics
        facts = _merge_facts(facts, new_facts)
        anchors = _merge_by_id(anchors, _answer_anchors_from_accepted_event(event))
        intents = _merge_by_id(intents, _forward_intents_from_accepted_event(event))
        reference_items = _merge_by_id(
            reference_items,
            _reference_continuity_from_accepted_event(event),
        )
        del accepted
    else:
        diagnostics = diagnostics + (
            _unsupported_event_type_diagnostic(event, policy_digest=policy_digest),
        )

    selected = _limit_selected_recent_window(selected, policy=policy)
    recent_evidence = tuple(
        item
        for item in selected
        if item.role is SelectedRecentWindowRole.EVIDENCE
    )
    facts, fact_budget_diagnostics = _limit_facts(
        facts,
        policy=policy,
        policy_digest=policy_digest,
    )
    reference_items, reference_budget_diagnostics = _limit_reference_items(
        reference_items,
        policy=policy,
        policy_digest=policy_digest,
    )
    anchors, anchor_budget_diagnostics = _limit_anchors(
        anchors,
        policy=policy,
        policy_digest=policy_digest,
    )
    intents, intent_budget_diagnostics = _limit_intents(
        intents,
        policy=policy,
        policy_digest=policy_digest,
    )
    cursor = MemorySnapshotCursor(
        consumer_id=consumer_id,
        checkpoint_event_sequence=event.event_sequence,
        checkpoint_event_id=event.event_id,
        session_id=event.session_id,
    )
    without_digest = ConversationMemorySnapshotVNext(
        schema_version=CONVERSATION_MEMORY_SNAPSHOT_SCHEMA_VERSION,
        snapshot_id=stable_memory_snapshot_id(
            session_id=event.session_id,
            consumer_id=consumer_id,
            policy_digest=policy_digest,
        ),
        session_id=event.session_id,
        cursor=cursor,
        policy_digest=policy_digest,
        latest_compaction_event_ref=latest_compaction_event_ref,
        trace_memory=TraceMemoryView(
            selected_recent_window=selected,
            reference_continuity_items=reference_items,
        ),
        evidence_fact_memory=EvidenceFactMemoryView(
            evidence_backed_facts=facts,
            recent_evidence_items=recent_evidence,
        ),
        session_summary_memory=session_summary,
        answer_anchor_memory=AnswerAnchorMemoryView(anchors=anchors),
        forward_intent_memory=ForwardIntentMemoryView(intents=intents),
        diagnostics=_dedupe_diagnostics(
            diagnostics
            + fact_budget_diagnostics
            + reference_budget_diagnostics
            + anchor_budget_diagnostics
            + intent_budget_diagnostics
        ),
        built_at=built_at,
        snapshot_digest=_SNAPSHOT_DIGEST_PENDING,
    )
    return _snapshot_with_digest(without_digest)


def memory_snapshot_with_cursor_and_diagnostics(
    *,
    snapshot: ConversationMemorySnapshotVNext,
    cursor: MemorySnapshotCursor,
    diagnostics: tuple[MemoryDiagnostic, ...],
) -> ConversationMemorySnapshotVNext:
    """返回替换 cursor 并追加 diagnostics 后的新 snapshot。

    :param snapshot: 原始 snapshot。
    :param cursor: 新 cursor。
    :param diagnostics: 追加 diagnostics。
    :returns: 新 snapshot。
    """

    if cursor.session_id != snapshot.session_id:
        raise ValueError("cursor session_id must match snapshot session_id")
    return _snapshot_with_digest(
        ConversationMemorySnapshotVNext(
            schema_version=snapshot.schema_version,
            snapshot_id=snapshot.snapshot_id,
            session_id=snapshot.session_id,
            cursor=cursor,
            policy_digest=snapshot.policy_digest,
            latest_compaction_event_ref=snapshot.latest_compaction_event_ref,
            trace_memory=snapshot.trace_memory,
            evidence_fact_memory=snapshot.evidence_fact_memory,
            session_summary_memory=snapshot.session_summary_memory,
            answer_anchor_memory=snapshot.answer_anchor_memory,
            forward_intent_memory=snapshot.forward_intent_memory,
            diagnostics=_dedupe_diagnostics(snapshot.diagnostics + diagnostics),
            built_at=snapshot.built_at,
            snapshot_digest=_SNAPSHOT_DIGEST_PENDING,
        )
    )


def build_inline_delta_repair_diagnostic(
    *, event_sequence: int, policy_digest: MemoryPolicyDigest
) -> MemoryDiagnostic:
    """构造 inline delta repair diagnostic。

    :param event_sequence: inline repair 覆盖到的 EventLog sequence。
    :param policy_digest: 当前 memory policy digest。
    :returns: diagnostic。
    """

    item_id = f"cursor:{event_sequence}"
    return MemoryDiagnostic(
        diagnostic_id=_diagnostic_id(
            MemoryDiagnosticReason.INLINE_DELTA_REPAIR_INCLUDED,
            event_sequence=event_sequence,
            item_id=item_id,
        ),
        reason=MemoryDiagnosticReason.INLINE_DELTA_REPAIR_INCLUDED,
        message="memory snapshot lag repaired inline from EventLog delta",
        event_sequence=event_sequence,
        item_id=item_id,
        policy_digest=policy_digest,
        recorded_at=None,
    )


def build_memory_budget_diagnostic(
    *,
    event_sequence: int,
    item_id: str,
    policy_digest: MemoryPolicyDigest,
    message: str,
) -> MemoryDiagnostic:
    """构造 memory budget diagnostic。

    :param event_sequence: 关联 EventLog sequence。
    :param item_id: 关联 item id。
    :param policy_digest: 当前 policy digest。
    :param message: diagnostic message。
    :returns: diagnostic。
    """

    return _budget_diagnostic(
        event_sequence=event_sequence,
        item_id=item_id,
        policy_digest=policy_digest,
        message=message,
    )


def memory_projection_policy_to_json_value(policy: MemoryProjectionPolicy) -> JsonValue:
    """转换 policy 为 canonical JSON。

    :param policy: memory projection policy。
    :returns: JSON object。
    """

    return {
        "answer_anchor_char_cap": policy.answer_anchor_char_cap,
        "answer_anchor_item_cap": policy.answer_anchor_item_cap,
        "context_window_size": policy.context_window_size,
        "evidence_fact_char_cap": policy.evidence_fact_char_cap,
        "evidence_fact_floor": policy.evidence_fact_floor,
        "evidence_fact_item_cap": policy.evidence_fact_item_cap,
        "fallback_selected_recent_window_char_cap": (
            policy.fallback_selected_recent_window_char_cap
        ),
        "fallback_selected_recent_window_item_cap": (
            policy.fallback_selected_recent_window_item_cap
        ),
        "forward_intent_char_cap": policy.forward_intent_char_cap,
        "forward_intent_item_cap": policy.forward_intent_item_cap,
        "max_delta_repair_events": policy.max_delta_repair_events,
        "max_lag_events_for_inline_delta": policy.max_lag_events_for_inline_delta,
        "policy_ref": policy.policy_ref,
        "reference_continuity_char_cap": policy.reference_continuity_char_cap,
        "reference_continuity_item_cap": policy.reference_continuity_item_cap,
        "reference_continuity_item_floor": (
            policy.reference_continuity_item_floor
        ),
        "selected_recent_window_char_cap": policy.selected_recent_window_char_cap,
        "selected_recent_window_item_cap": policy.selected_recent_window_item_cap,
        "selected_recent_window_turn_floor": policy.selected_recent_window_turn_floor,
        "session_summary_char_cap": policy.session_summary_char_cap,
    }


def conversation_memory_snapshot_to_json_value(
    snapshot: ConversationMemorySnapshotVNext,
) -> JsonValue:
    """转换 snapshot 为 JSON。

    :param snapshot: memory snapshot。
    :returns: JSON object。
    """

    return _snapshot_json_value(snapshot, include_digest=True)


def conversation_memory_snapshot_from_json_value(
    value: JsonValue,
) -> ConversationMemorySnapshotVNext:
    """从 JSON 恢复 snapshot。

    :param value: JSON 值。
    :returns: typed snapshot。
    :raises ValueError: JSON shape 非法时抛出。
    """

    mapping = _as_mapping(value, "snapshot")
    cursor = _cursor_from_json_value(_required_value(mapping, "cursor"))
    snapshot = ConversationMemorySnapshotVNext(
        schema_version=_required_str(mapping, "schema_version"),
        snapshot_id=_required_str(mapping, "snapshot_id"),
        session_id=_required_str(mapping, "session_id"),
        cursor=cursor,
        policy_digest=_required_str(mapping, "policy_digest"),
        latest_compaction_event_ref=_optional_str(
            mapping,
            "latest_compaction_event_ref",
        ),
        trace_memory=_trace_memory_from_json_value(
            _required_value(mapping, "trace_memory")
        ),
        evidence_fact_memory=_evidence_memory_from_json_value(
            _required_value(mapping, "evidence_fact_memory")
        ),
        session_summary_memory=_session_summary_memory_from_json_value(
            _required_value(mapping, "session_summary_memory")
        ),
        answer_anchor_memory=_answer_anchor_memory_from_json_value(
            _required_value(mapping, "answer_anchor_memory")
        ),
        forward_intent_memory=_forward_intent_memory_from_json_value(
            _required_value(mapping, "forward_intent_memory")
        ),
        diagnostics=tuple(
            memory_diagnostic_from_json_value(item)
            for item in _required_list(mapping, "diagnostics")
        ),
        built_at=_required_str(mapping, "built_at"),
        snapshot_digest=_required_str(mapping, "snapshot_digest"),
    )
    return snapshot


def memory_diagnostic_to_json_value(diagnostic: MemoryDiagnostic) -> JsonValue:
    """转换 diagnostic 为 JSON。

    :param diagnostic: memory diagnostic。
    :returns: JSON object。
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


def memory_diagnostic_from_json_value(value: JsonValue) -> MemoryDiagnostic:
    """从 JSON 恢复 diagnostic。

    :param value: JSON 值。
    :returns: memory diagnostic。
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


def _empty_or_valid_previous_snapshot(
    *,
    previous_snapshot: ConversationMemorySnapshotVNext | None,
    event: MemoryProjectionEvent,
    policy_digest: MemoryPolicyDigest,
    consumer_id: str,
    built_at: str,
) -> ConversationMemorySnapshotVNext:
    """读取既有 snapshot 或构造空 snapshot。

    :param previous_snapshot: 既有 snapshot。
    :param event: 当前 event。
    :param policy_digest: 当前 policy digest。
    :param consumer_id: consumer id。
    :param built_at: 构建时间。
    :returns: base snapshot。
    """

    if previous_snapshot is None:
        return build_empty_conversation_memory_snapshot(
            snapshot_id=stable_memory_snapshot_id(
                session_id=event.session_id,
                consumer_id=consumer_id,
                policy_digest=policy_digest,
            ),
            session_id=event.session_id,
            consumer_id=consumer_id,
            policy_digest=policy_digest,
            built_at=built_at,
        )
    if previous_snapshot.session_id != event.session_id:
        raise ValueError("previous memory snapshot belongs to another session")
    if previous_snapshot.policy_digest != policy_digest:
        raise ValueError("previous memory snapshot uses another policy")
    if previous_snapshot.cursor.consumer_id != consumer_id:
        raise ValueError("previous memory snapshot uses another consumer")
    if previous_snapshot.cursor.checkpoint_event_sequence > event.event_sequence:
        raise ValueError("memory projection event is behind previous snapshot")
    return previous_snapshot


def _selected_user_item(event: MemoryProjectionEvent) -> SelectedRecentWindowItem:
    """从用户输入 event 构造 selected recent item。

    :param event: USER_INPUT_ACCEPTED event。
    :returns: selected item。
    """

    text = _user_visible_text(event)
    return SelectedRecentWindowItem(
        item_id=_item_id(event, "selected_user"),
        role=SelectedRecentWindowRole.USER,
        text=text,
        event_id=event.event_id,
        event_sequence=event.event_sequence,
        run_id=event.run_id,
        source_refs=(event.event_id,),
        included_reason=MemoryIncludedReason.SELECTED_RECENT_WINDOW,
        excluded_reason=None,
        size_units=estimate_memory_size_units(text),
    )


def _selected_assistant_item(
    event: MemoryProjectionEvent,
) -> SelectedRecentWindowItem | None:
    """从 RUN_SUCCEEDED event 构造 selected recent item。

    :param event: RUN_SUCCEEDED event。
    :returns: selected item；缺失 final answer continuity 时返回 ``None``。
    """

    text = assistant_final_answer_text_from_run_payload(
        event.payload,
        text_policy=PayloadTextReadPolicy.LENIENT_NON_EMPTY,
    )
    if text is None:
        return None
    return SelectedRecentWindowItem(
        item_id=_item_id(event, "selected_assistant"),
        role=SelectedRecentWindowRole.ASSISTANT,
        text=text,
        event_id=event.event_id,
        event_sequence=event.event_sequence,
        run_id=event.run_id,
        source_refs=(event.event_id,),
        included_reason=MemoryIncludedReason.SELECTED_RECENT_WINDOW,
        excluded_reason=None,
        size_units=estimate_memory_size_units(text),
    )


def _selected_evidence_item(event: MemoryProjectionEvent) -> SelectedRecentWindowItem:
    """从 TOOL_RESULT_ACCEPTED event 构造 recent evidence item。

    :param event: TOOL_RESULT_ACCEPTED event。
    :returns: selected evidence item。
    """

    text = _selected_evidence_text(event)
    return SelectedRecentWindowItem(
        item_id=_item_id(event, "selected_evidence"),
        role=SelectedRecentWindowRole.EVIDENCE,
        text=text,
        event_id=event.event_id,
        event_sequence=event.event_sequence,
        run_id=event.run_id,
        source_refs=(event.event_id,),
        included_reason=MemoryIncludedReason.RECENT_EVIDENCE,
        excluded_reason=None,
        size_units=estimate_memory_size_units(text),
    )


def _selected_evidence_text(event: MemoryProjectionEvent) -> str:
    """读取 LLM-facing recent evidence 文本。

    :param event: ``TOOL_RESULT_ACCEPTED`` projection event。
    :returns: 工具结果的业务可读文本或无内部引用的 limited-signal 文本。
    :raises ValueError: accepted evidence envelope 或旧 result preview 非法时抛出。
    """

    envelope = accepted_evidence_envelope_from_payload(
        event.payload,
        producer_event_ref=event.event_id,
    )
    if envelope is not None:
        raw_text = accepted_tool_raw_outcome_text_from_payload(event.payload)
        if raw_text is not None:
            return raw_text
        raise ValueError("TOOL_RESULT_ACCEPTED raw_tool_outcome is missing")
    return "工具结果已接受；原始工具响应不可用。"


def _accepted_candidate_mapping(
    payload: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue]:
    """读取 accepted vNext compact candidate。

    :param payload: CONTEXT_COMPACTED payload。
    :returns: accepted candidate mapping。
    :raises ValueError: payload 不是 vNext accepted candidate 时抛出。
    """

    candidate = _required_payload_mapping(payload, _PAYLOAD_FIELD_ACCEPTED_CANDIDATE)
    if (
        _required_str(candidate, _PAYLOAD_FIELD_SCHEMA_VERSION)
        != "conversation_compact_output_v1"
    ):
        raise ValueError("accepted candidate schema_version is invalid")
    return candidate


def _session_summary_from_accepted_event(
    event: MemoryProjectionEvent, policy: MemoryProjectionPolicy
) -> tuple[SessionSummaryMemoryView, tuple[MemoryDiagnostic, ...]]:
    """从 accepted compact event 物化 Session Summary Memory。

    :param event: CONTEXT_COMPACTED event。
    :param policy: memory policy。
    :returns: session summary view 与 diagnostics。
    """

    candidate = _accepted_candidate_mapping(event.payload)
    value = _required_value(candidate, _PAYLOAD_FIELD_SESSION_SUMMARY)
    if value is None:
        return _empty_session_summary_memory(), ()
    summary = _as_mapping(value, _PAYLOAD_FIELD_SESSION_SUMMARY)
    text = _required_str(summary, _PAYLOAD_FIELD_SUMMARY_TEXT)
    if len(text) > policy.session_summary_char_cap:
        item_id = _item_id(event, "session_summary")
        return _empty_session_summary_memory(), (
            _budget_diagnostic(
                event_sequence=event.event_sequence,
                item_id=item_id,
                policy_digest=digest_memory_projection_policy(policy),
                message="session summary dropped by memory policy",
            ),
        )
    return SessionSummaryMemoryView(
        summary_text=text,
        source_refs=_required_text_tuple(summary, _PAYLOAD_FIELD_SOURCE_LABELS),
        event_id=event.event_id,
        event_sequence=event.event_sequence,
        size_units=estimate_memory_size_units(text),
    ), ()


def _facts_from_accepted_event(
    event: MemoryProjectionEvent,
    policy: MemoryProjectionPolicy,
) -> tuple[tuple[EvidenceBackedFactView, ...], tuple[MemoryDiagnostic, ...]]:
    """从 accepted compact event 物化 evidence-backed facts。

    :param event: CONTEXT_COMPACTED event。
    :param policy: memory policy。
    :returns: facts 与 diagnostics。
    """

    candidate = _accepted_candidate_mapping(event.payload)
    evidence_refs = _required_text_tuple(
        event.payload,
        _PAYLOAD_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS,
    )
    fact_values = _required_mapping_list(candidate, _PAYLOAD_FIELD_EVIDENCE_BACKED_FACTS)
    if len(evidence_refs) > 0 and len(fact_values) == 0:
        return (
            (),
            (
                MemoryDiagnostic(
                    diagnostic_id=_diagnostic_id(
                        MemoryDiagnosticReason.ACCEPTED_EVIDENCE_WITHOUT_FACT_CANDIDATE,
                        event_sequence=event.event_sequence,
                        item_id=_item_id(event, "accepted_evidence_without_fact"),
                    ),
                    reason=(
                        MemoryDiagnosticReason.ACCEPTED_EVIDENCE_WITHOUT_FACT_CANDIDATE
                    ),
                    message=(
                        "accepted evidence exists but compact output provided no fact candidate"
                    ),
                    event_sequence=event.event_sequence,
                    item_id=_item_id(event, "accepted_evidence_without_fact"),
                    policy_digest=digest_memory_projection_policy(policy),
                    recorded_at=None,
                ),
            ),
        )
    provenance = MemoryProvenanceRef(
        producer_kind=MemoryProducerKind.HOST_PROJECTION,
        producer_name="host_projection",
        event_id=event.event_id,
        event_sequence=event.event_sequence,
        run_id=event.run_id,
        attempt_id=event.attempt_id,
        execution_id=event.execution_id,
        tool_result_ref=None,
        payload_ref=event.payload_ref,
        digest_ref=event.payload_digest or sha256_digest_json(event.payload),
        source_refs=(),
    )
    compact_artifact_ref = _optional_payload_str(
        event.payload,
        _PAYLOAD_FIELD_COMPACT_ARTIFACT_REF,
    )
    facts: list[EvidenceBackedFactView] = []
    diagnostics: list[MemoryDiagnostic] = []
    policy_digest = digest_memory_projection_policy(policy)
    for index, fact in enumerate(fact_values):
        claim_text = _required_str(fact, _PAYLOAD_FIELD_CLAIM_TEXT)
        item_id = _item_id(event, f"evidence_fact:{index + 1}")
        if len(claim_text) > policy.evidence_fact_char_cap:
            diagnostics.append(
                _budget_diagnostic(
                    event_sequence=event.event_sequence,
                    item_id=item_id,
                    policy_digest=policy_digest,
                    message="evidence fact dropped by memory policy",
                )
            )
            continue
        labels = _required_text_tuple(fact, _PAYLOAD_FIELD_EVIDENCE_LABELS)
        if len(labels) == 0:
            diagnostics.append(
                _fact_candidate_invalid_diagnostic(
                    event,
                    policy_digest=policy_digest,
                    message="fact candidate has no evidence label",
                )
            )
            continue
        facts.append(
            EvidenceBackedFactView(
                item_id=item_id,
                claim_text=claim_text,
                evidence_kind=MemoryEvidenceBackedFactKind.DERIVED_FROM_EVIDENCE,
                evidence_refs=evidence_refs,
                provenance=provenance,
                extraction_operation_ref=f"event:{event.event_id}",
                compact_artifact_ref=compact_artifact_ref,
                candidate_id=f"vnext-fact-{index + 1}",
                included_reason=MemoryIncludedReason.EVIDENCE_BACKED_FACT,
                excluded_reason=None,
                size_units=estimate_memory_size_units(claim_text),
            )
        )
    return tuple(facts), tuple(diagnostics)


def _empty_session_summary_memory() -> SessionSummaryMemoryView:
    """构造空 Session Summary Memory view。

    :returns: 空 session summary view。
    """

    return SessionSummaryMemoryView(
        summary_text=None,
        source_refs=(),
        event_id=None,
        event_sequence=None,
        size_units=MemorySizeUnits(0),
    )


def _answer_anchors_from_accepted_event(
    event: MemoryProjectionEvent,
) -> tuple[AnswerAnchor, ...]:
    """从 accepted compact event 物化 answer anchors。

    :param event: CONTEXT_COMPACTED event。
    :returns: answer anchors。
    """

    candidate = _accepted_candidate_mapping(event.payload)
    result: list[AnswerAnchor] = []
    for index, item in enumerate(
        _required_mapping_list(candidate, _PAYLOAD_FIELD_ANSWER_ANCHORS)
    ):
        children = tuple(
            AnswerAnchorChild(
                display_text=_required_str(child, _PAYLOAD_FIELD_DISPLAY_TEXT),
                ordinal=_optional_int(child, _PAYLOAD_FIELD_ORDINAL),
            )
            for child in _required_mapping_list(item, _PAYLOAD_FIELD_ANCHOR_ITEMS)
        )
        text = "\n".join(
            ([_required_str(item, _PAYLOAD_FIELD_ANCHOR_TITLE)] + [c.display_text for c in children])
        )
        result.append(
            AnswerAnchor(
                item_id=_item_id(event, f"answer_anchor:{index + 1}"),
                anchor_title=_required_str(item, _PAYLOAD_FIELD_ANCHOR_TITLE),
                anchor_items=children,
                source_refs=_required_text_tuple(
                    item,
                    _PAYLOAD_FIELD_ANSWER_SOURCE_LABELS,
                ),
                event_id=event.event_id,
                event_sequence=event.event_sequence,
                size_units=estimate_memory_size_units(text),
            )
        )
    return tuple(result)


def _forward_intents_from_accepted_event(
    event: MemoryProjectionEvent,
) -> tuple[ForwardIntent, ...]:
    """从 accepted compact event 物化 forward intents。

    :param event: CONTEXT_COMPACTED event。
    :returns: forward intents。
    """

    candidate = _accepted_candidate_mapping(event.payload)
    result: list[ForwardIntent] = []
    for index, item in enumerate(
        _required_mapping_list(candidate, _PAYLOAD_FIELD_FORWARD_INTENTS)
    ):
        text = _required_str(item, _PAYLOAD_FIELD_TEXT)
        result.append(
            ForwardIntent(
                item_id=_item_id(event, f"forward_intent:{index + 1}"),
                intent_type=_required_str(item, _PAYLOAD_FIELD_INTENT_TYPE),
                text=text,
                status=_required_str(item, _PAYLOAD_FIELD_STATUS),
                source_refs=_required_text_tuple(item, _PAYLOAD_FIELD_SOURCE_LABELS),
                event_id=event.event_id,
                event_sequence=event.event_sequence,
                size_units=estimate_memory_size_units(text),
            )
        )
    return tuple(result)


def _reference_continuity_from_accepted_event(
    event: MemoryProjectionEvent,
) -> tuple[ReferenceContinuityItem, ...]:
    """从 accepted compact event 物化 reference continuity items。

    :param event: CONTEXT_COMPACTED event。
    :returns: reference continuity items。
    """

    candidate = _accepted_candidate_mapping(event.payload)
    result: list[ReferenceContinuityItem] = []
    for index, item in enumerate(
        _required_mapping_list(candidate, _PAYLOAD_FIELD_REFERENCE_CONTINUITY_ITEMS)
    ):
        text = _required_str(item, _PAYLOAD_FIELD_TEXT)
        result.append(
            ReferenceContinuityItem(
                item_id=_item_id(event, f"reference_continuity:{index + 1}"),
                text=text,
                reason=_required_str(item, _PAYLOAD_FIELD_REASON),
                source_refs=_required_text_tuple(item, _PAYLOAD_FIELD_SOURCE_LABELS),
                event_id=event.event_id,
                event_sequence=event.event_sequence,
                size_units=estimate_memory_size_units(text),
            )
        )
    return tuple(result)


def _limit_selected_recent_window(
    items: tuple[SelectedRecentWindowItem, ...],
    *,
    policy: MemoryProjectionPolicy,
) -> tuple[SelectedRecentWindowItem, ...]:
    """按 selected recent window policy 裁剪 item。

    :param items: 候选 items。
    :param policy: memory policy。
    :returns: 裁剪后的 items。
    :raises ValueError: floor 依赖的 eligible item 缺少 run_id 时抛出。
    """

    protected_run_ids = _protected_recent_run_ids(
        items,
        selected_recent_window_turn_floor=policy.selected_recent_window_turn_floor,
    )
    protected = tuple(item for item in items if item.run_id in protected_run_ids)
    protected_ids = {item.item_id for item in protected}
    selected_reversed: list[SelectedRecentWindowItem] = list(reversed(protected))
    used = sum(item.size_units.units for item in selected_reversed)
    for item in reversed(items):
        if item.item_id in protected_ids:
            continue
        if len(selected_reversed) >= policy.selected_recent_window_item_cap:
            break
        if used + item.size_units.units > policy.selected_recent_window_char_cap:
            continue
        selected_reversed.append(item)
        used += item.size_units.units
    selected_ids = {item.item_id for item in selected_reversed}
    return tuple(item for item in items if item.item_id in selected_ids)


def _protected_recent_run_ids(
    items: tuple[SelectedRecentWindowItem, ...],
    *,
    selected_recent_window_turn_floor: int,
) -> frozenset[str]:
    """返回最近 N 个 Host Run turn group id。

    :param items: selected recent window 候选 items。
    :param selected_recent_window_turn_floor: 需要保护的 turn group 数。
    :returns: 需要保护的 run_id 集合。
    :raises ValueError: floor 依赖的 eligible item 缺少 run_id 时抛出。
    """

    if selected_recent_window_turn_floor == 0:
        return frozenset()
    eligible = tuple(item for item in items if _is_selected_recent_turn_item(item))
    missing = tuple(item.item_id for item in eligible if item.run_id is None)
    if len(missing) > 0:
        raise ValueError("selected recent window item is missing run_id")
    latest_by_run: dict[str, tuple[int, int]] = {}
    for index, item in enumerate(eligible):
        if item.run_id is None:
            continue
        current = latest_by_run.get(item.run_id)
        candidate = (item.event_sequence, index)
        if current is None or candidate > current:
            latest_by_run[item.run_id] = candidate
    ordered = tuple(
        run_id
        for run_id, _latest in sorted(
            latest_by_run.items(),
            key=lambda pair: (pair[1][0], pair[1][1], pair[0]),
            reverse=True,
        )
    )
    return frozenset(ordered[:selected_recent_window_turn_floor])


def _is_selected_recent_turn_item(item: SelectedRecentWindowItem) -> bool:
    """判断 item 是否属于 Host Run turn group recent material。

    :param item: selected recent window item。
    :returns: 属于 user / assistant / evidence recent material 时返回 ``True``。
    """

    return item.role in (
        SelectedRecentWindowRole.USER,
        SelectedRecentWindowRole.ASSISTANT,
        SelectedRecentWindowRole.EVIDENCE,
    )


def _limit_facts(
    items: tuple[EvidenceBackedFactView, ...],
    *,
    policy: MemoryProjectionPolicy,
    policy_digest: MemoryPolicyDigest,
) -> tuple[tuple[EvidenceBackedFactView, ...], tuple[MemoryDiagnostic, ...]]:
    """按 evidence fact cap / floor 裁剪 facts。

    :param items: facts。
    :param policy: memory policy。
    :param policy_digest: policy digest。
    :returns: 裁剪后的 facts 与 diagnostics。
    """

    return _limit_items_by_count_and_chars(
        items,
        item_cap=policy.evidence_fact_item_cap,
        char_cap=policy.evidence_fact_char_cap,
        floor=policy.evidence_fact_floor,
        policy_digest=policy_digest,
        message="evidence facts limited by memory policy",
    )


def _limit_reference_items(
    items: tuple[ReferenceContinuityItem, ...],
    *,
    policy: MemoryProjectionPolicy,
    policy_digest: MemoryPolicyDigest,
) -> tuple[tuple[ReferenceContinuityItem, ...], tuple[MemoryDiagnostic, ...]]:
    """按 reference continuity cap / floor 裁剪 items。

    :param items: reference items。
    :param policy: memory policy。
    :param policy_digest: policy digest。
    :returns: 裁剪后的 items 与 diagnostics。
    """

    return _limit_items_by_count_and_chars(
        items,
        item_cap=policy.reference_continuity_item_cap,
        char_cap=policy.reference_continuity_char_cap,
        floor=policy.reference_continuity_item_floor,
        policy_digest=policy_digest,
        message="reference continuity limited by memory policy",
    )


def _limit_anchors(
    items: tuple[AnswerAnchor, ...],
    *,
    policy: MemoryProjectionPolicy,
    policy_digest: MemoryPolicyDigest,
) -> tuple[tuple[AnswerAnchor, ...], tuple[MemoryDiagnostic, ...]]:
    """按 answer anchor cap 裁剪 anchors。

    :param items: anchors。
    :param policy: memory policy。
    :param policy_digest: policy digest。
    :returns: 裁剪后的 anchors 与 diagnostics。
    """

    return _limit_items_by_count_and_chars(
        items,
        item_cap=policy.answer_anchor_item_cap,
        char_cap=policy.answer_anchor_char_cap,
        floor=0,
        policy_digest=policy_digest,
        message="answer anchors limited by memory policy",
    )


def _limit_intents(
    items: tuple[ForwardIntent, ...],
    *,
    policy: MemoryProjectionPolicy,
    policy_digest: MemoryPolicyDigest,
) -> tuple[tuple[ForwardIntent, ...], tuple[MemoryDiagnostic, ...]]:
    """按 forward intent cap 裁剪 intents。

    :param items: intents。
    :param policy: memory policy。
    :param policy_digest: policy digest。
    :returns: 裁剪后的 intents 与 diagnostics。
    """

    return _limit_items_by_count_and_chars(
        items,
        item_cap=policy.forward_intent_item_cap,
        char_cap=policy.forward_intent_char_cap,
        floor=0,
        policy_digest=policy_digest,
        message="forward intents limited by memory policy",
    )


def _limit_items_by_count_and_chars(
    items: tuple[_MemoryItemT, ...],
    *,
    item_cap: int,
    char_cap: int,
    floor: int,
    policy_digest: MemoryPolicyDigest,
    message: str,
) -> tuple[tuple[_MemoryItemT, ...], tuple[MemoryDiagnostic, ...]]:
    """按数量与字符上限裁剪带 item_id / size_units / event cursor 的 items。

    :param items: 候选 items。
    :param item_cap: 数量上限。
    :param char_cap: 字符上限。
    :param floor: 最新 item 保底数量。
    :param policy_digest: policy digest。
    :param message: diagnostic message。
    :returns: 裁剪后的 items 与 diagnostics。
    """

    protected = items[-floor:] if floor > 0 else ()
    protected_ids = {item.item_id for item in protected}
    selected_reversed: list[_MemoryItemT] = list(reversed(protected))
    used = sum(_item_size_units(item) for item in selected_reversed)
    for item in reversed(items):
        if item.item_id in protected_ids:
            continue
        if len(selected_reversed) >= item_cap:
            break
        if used + _item_size_units(item) > char_cap:
            continue
        selected_reversed.append(item)
        used += _item_size_units(item)
    selected_ids = {item.item_id for item in selected_reversed}
    selected = tuple(item for item in items if item.item_id in selected_ids)
    if len(selected) == len(items):
        return selected, ()
    first_dropped = next(item for item in items if item.item_id not in selected_ids)
    return selected, (
        _budget_diagnostic(
            event_sequence=_item_event_sequence(first_dropped),
            item_id=first_dropped.item_id,
            policy_digest=policy_digest,
            message=message,
        ),
    )


def _merge_facts(
    existing: tuple[EvidenceBackedFactView, ...],
    candidates: tuple[EvidenceBackedFactView, ...],
) -> tuple[EvidenceBackedFactView, ...]:
    """按 claim/evidence 去重合并 facts。

    :param existing: 已有 facts。
    :param candidates: 新 facts。
    :returns: 合并后的 facts。
    """

    result = list(existing)
    for candidate in candidates:
        key = (_normalized_text(candidate.claim_text), candidate.evidence_refs)
        result = [
            item
            for item in result
            if (_normalized_text(item.claim_text), item.evidence_refs) != key
        ]
        result.append(candidate)
    return tuple(result)


def _merge_by_id(
    existing: tuple[_MemoryItemT, ...],
    candidates: tuple[_MemoryItemT, ...],
) -> tuple[_MemoryItemT, ...]:
    """按 item id 合并 items。

    :param existing: 已有 items。
    :param candidates: 新 items。
    :returns: 合并后的 items。
    """

    result = existing
    for candidate in candidates:
        result = _replace_item_by_id(result, candidate)
    return result


def _replace_item_by_id(
    items: tuple[_MemoryItemT, ...],
    item: _MemoryItemT,
) -> tuple[_MemoryItemT, ...]:
    """按 item id 替换或追加 item。

    :param items: 原始 items。
    :param item: 新 item。
    :returns: 替换后的 tuple。
    """

    return tuple(existing for existing in items if existing.item_id != item.item_id) + (
        item,
    )


def _snapshot_with_digest(
    snapshot: ConversationMemorySnapshotVNext,
) -> ConversationMemorySnapshotVNext:
    """返回带正确 digest 的 snapshot。

    :param snapshot: snapshot。
    :returns: digest 已重算的 snapshot。
    """

    digest = calculate_memory_snapshot_digest(snapshot)
    return ConversationMemorySnapshotVNext(
        schema_version=snapshot.schema_version,
        snapshot_id=snapshot.snapshot_id,
        session_id=snapshot.session_id,
        cursor=snapshot.cursor,
        policy_digest=snapshot.policy_digest,
        latest_compaction_event_ref=snapshot.latest_compaction_event_ref,
        trace_memory=snapshot.trace_memory,
        evidence_fact_memory=snapshot.evidence_fact_memory,
        session_summary_memory=snapshot.session_summary_memory,
        answer_anchor_memory=snapshot.answer_anchor_memory,
        forward_intent_memory=snapshot.forward_intent_memory,
        diagnostics=snapshot.diagnostics,
        built_at=snapshot.built_at,
        snapshot_digest=digest,
    )


def _snapshot_json_value(
    snapshot: ConversationMemorySnapshotVNext, *, include_digest: bool
) -> JsonValue:
    """转换 snapshot 为 JSON object。

    :param snapshot: snapshot。
    :param include_digest: 是否包含 snapshot_digest。
    :returns: JSON object。
    """

    result: dict[str, JsonValue] = {
        "answer_anchor_memory": _answer_anchor_memory_to_json_value(
            snapshot.answer_anchor_memory
        ),
        "built_at": snapshot.built_at,
        "cursor": _cursor_to_json_value(snapshot.cursor),
        "diagnostics": [
            memory_diagnostic_to_json_value(item) for item in snapshot.diagnostics
        ],
        "evidence_fact_memory": _evidence_memory_to_json_value(
            snapshot.evidence_fact_memory
        ),
        "forward_intent_memory": _forward_intent_memory_to_json_value(
            snapshot.forward_intent_memory
        ),
        "latest_compaction_event_ref": snapshot.latest_compaction_event_ref,
        "policy_digest": snapshot.policy_digest,
        "schema_version": snapshot.schema_version,
        "session_id": snapshot.session_id,
        "session_summary_memory": _session_summary_memory_to_json_value(
            snapshot.session_summary_memory
        ),
        "snapshot_id": snapshot.snapshot_id,
        "trace_memory": _trace_memory_to_json_value(snapshot.trace_memory),
    }
    if include_digest:
        result["snapshot_digest"] = snapshot.snapshot_digest
    return result


def _snapshot_digest_json_value(snapshot: ConversationMemorySnapshotVNext) -> JsonValue:
    """返回参与 snapshot digest 的 JSON。

    :param snapshot: snapshot。
    :returns: JSON object。
    """

    return _snapshot_json_value(snapshot, include_digest=False)


def _cursor_to_json_value(cursor: MemorySnapshotCursor) -> JsonValue:
    """转换 cursor 为 JSON。

    :param cursor: cursor。
    :returns: JSON object。
    """

    return {
        "checkpoint_event_id": cursor.checkpoint_event_id,
        "checkpoint_event_sequence": cursor.checkpoint_event_sequence,
        "consumer_id": cursor.consumer_id,
        "session_id": cursor.session_id,
    }


def _cursor_from_json_value(value: JsonValue) -> MemorySnapshotCursor:
    """从 JSON 恢复 cursor。

    :param value: JSON 值。
    :returns: cursor。
    """

    mapping = _as_mapping(value, "cursor")
    return MemorySnapshotCursor(
        consumer_id=_required_str(mapping, "consumer_id"),
        checkpoint_event_sequence=_required_int(
            mapping,
            "checkpoint_event_sequence",
        ),
        checkpoint_event_id=_optional_str(mapping, "checkpoint_event_id"),
        session_id=_required_str(mapping, "session_id"),
    )


def _trace_memory_to_json_value(view: TraceMemoryView) -> JsonValue:
    """转换 Trace Memory 为 JSON。

    :param view: Trace Memory view。
    :returns: JSON object。
    """

    return {
        "reference_continuity_items": [
            _reference_item_to_json_value(item)
            for item in view.reference_continuity_items
        ],
        "selected_recent_window": [
            _selected_item_to_json_value(item)
            for item in view.selected_recent_window
        ],
    }


def _trace_memory_from_json_value(value: JsonValue) -> TraceMemoryView:
    """从 JSON 恢复 Trace Memory。

    :param value: JSON 值。
    :returns: Trace Memory view。
    """

    mapping = _as_mapping(value, "trace_memory")
    return TraceMemoryView(
        selected_recent_window=tuple(
            _selected_item_from_json_value(item)
            for item in _required_list(mapping, "selected_recent_window")
        ),
        reference_continuity_items=tuple(
            _reference_item_from_json_value(item)
            for item in _required_list(mapping, "reference_continuity_items")
        ),
    )


def _evidence_memory_to_json_value(view: EvidenceFactMemoryView) -> JsonValue:
    """转换 Evidence / Fact Memory 为 JSON。

    :param view: Evidence / Fact Memory view。
    :returns: JSON object。
    """

    return {
        "evidence_backed_facts": [
            _fact_to_json_value(item) for item in view.evidence_backed_facts
        ],
        "recent_evidence_items": [
            _selected_item_to_json_value(item) for item in view.recent_evidence_items
        ],
    }


def _evidence_memory_from_json_value(value: JsonValue) -> EvidenceFactMemoryView:
    """从 JSON 恢复 Evidence / Fact Memory。

    :param value: JSON 值。
    :returns: Evidence / Fact Memory view。
    """

    mapping = _as_mapping(value, "evidence_fact_memory")
    return EvidenceFactMemoryView(
        evidence_backed_facts=tuple(
            _fact_from_json_value(item)
            for item in _required_list(mapping, "evidence_backed_facts")
        ),
        recent_evidence_items=tuple(
            _selected_item_from_json_value(item)
            for item in _required_list(mapping, "recent_evidence_items")
        ),
    )


def _session_summary_memory_to_json_value(
    view: SessionSummaryMemoryView,
) -> JsonValue:
    """转换 Session Summary Memory 为 JSON。

    :param view: Session Summary Memory view。
    :returns: JSON object。
    """

    return {
        "event_id": view.event_id,
        "event_sequence": view.event_sequence,
        "size_units": view.size_units.units,
        "source_refs": list(view.source_refs),
        "summary_text": view.summary_text,
    }


def _session_summary_memory_from_json_value(
    value: JsonValue,
) -> SessionSummaryMemoryView:
    """从 JSON 恢复 Session Summary Memory。

    :param value: JSON 值。
    :returns: Session Summary Memory view。
    """

    mapping = _as_mapping(value, "session_summary_memory")
    return SessionSummaryMemoryView(
        summary_text=_optional_str(mapping, "summary_text"),
        source_refs=_required_text_tuple(mapping, "source_refs"),
        event_id=_optional_str(mapping, "event_id"),
        event_sequence=_optional_int(mapping, "event_sequence"),
        size_units=MemorySizeUnits(_required_int(mapping, "size_units")),
    )


def _answer_anchor_memory_to_json_value(view: AnswerAnchorMemoryView) -> JsonValue:
    """转换 Answer Anchor Memory 为 JSON。

    :param view: Answer Anchor Memory view。
    :returns: JSON object。
    """

    return {"anchors": [_answer_anchor_to_json_value(item) for item in view.anchors]}


def _answer_anchor_memory_from_json_value(value: JsonValue) -> AnswerAnchorMemoryView:
    """从 JSON 恢复 Answer Anchor Memory。

    :param value: JSON 值。
    :returns: Answer Anchor Memory view。
    """

    mapping = _as_mapping(value, "answer_anchor_memory")
    return AnswerAnchorMemoryView(
        anchors=tuple(
            _answer_anchor_from_json_value(item)
            for item in _required_list(mapping, "anchors")
        )
    )


def _forward_intent_memory_to_json_value(view: ForwardIntentMemoryView) -> JsonValue:
    """转换 Forward Intent Memory 为 JSON。

    :param view: Forward Intent Memory view。
    :returns: JSON object。
    """

    return {"intents": [_forward_intent_to_json_value(item) for item in view.intents]}


def _forward_intent_memory_from_json_value(value: JsonValue) -> ForwardIntentMemoryView:
    """从 JSON 恢复 Forward Intent Memory。

    :param value: JSON 值。
    :returns: Forward Intent Memory view。
    """

    mapping = _as_mapping(value, "forward_intent_memory")
    return ForwardIntentMemoryView(
        intents=tuple(
            _forward_intent_from_json_value(item)
            for item in _required_list(mapping, "intents")
        )
    )


def _selected_item_to_json_value(item: SelectedRecentWindowItem) -> JsonValue:
    """转换 selected recent item 为 JSON。

    :param item: selected item。
    :returns: JSON object。
    """

    return {
        "event_id": item.event_id,
        "event_sequence": item.event_sequence,
        "excluded_reason": (
            None if item.excluded_reason is None else item.excluded_reason.value
        ),
        "included_reason": (
            None if item.included_reason is None else item.included_reason.value
        ),
        "item_id": item.item_id,
        "role": item.role.value,
        "run_id": item.run_id,
        "size_units": item.size_units.units,
        "source_refs": list(item.source_refs),
        "text": item.text,
    }


def _selected_item_from_json_value(value: JsonValue) -> SelectedRecentWindowItem:
    """从 JSON 恢复 selected recent item。

    :param value: JSON 值。
    :returns: selected item。
    """

    mapping = _as_mapping(value, "selected_recent_window_item")
    return SelectedRecentWindowItem(
        item_id=_required_str(mapping, "item_id"),
        role=SelectedRecentWindowRole(_required_str(mapping, "role")),
        text=_required_str(mapping, "text"),
        event_id=_required_str(mapping, "event_id"),
        event_sequence=_required_int(mapping, "event_sequence"),
        run_id=_optional_str(mapping, "run_id"),
        source_refs=_required_text_tuple(mapping, "source_refs"),
        included_reason=_optional_included_reason(mapping, "included_reason"),
        excluded_reason=_optional_excluded_reason(mapping, "excluded_reason"),
        size_units=MemorySizeUnits(_required_int(mapping, "size_units")),
    )


def _reference_item_to_json_value(item: ReferenceContinuityItem) -> JsonValue:
    """转换 reference continuity item 为 JSON。

    :param item: reference item。
    :returns: JSON object。
    """

    return {
        "event_id": item.event_id,
        "event_sequence": item.event_sequence,
        "item_id": item.item_id,
        "reason": item.reason,
        "size_units": item.size_units.units,
        "source_refs": list(item.source_refs),
        "text": item.text,
    }


def _reference_item_from_json_value(value: JsonValue) -> ReferenceContinuityItem:
    """从 JSON 恢复 reference continuity item。

    :param value: JSON 值。
    :returns: reference item。
    """

    mapping = _as_mapping(value, "reference_continuity_item")
    return ReferenceContinuityItem(
        item_id=_required_str(mapping, "item_id"),
        text=_required_str(mapping, "text"),
        reason=_required_str(mapping, "reason"),
        source_refs=_required_text_tuple(mapping, "source_refs"),
        event_id=_required_str(mapping, "event_id"),
        event_sequence=_required_int(mapping, "event_sequence"),
        size_units=MemorySizeUnits(_required_int(mapping, "size_units")),
    )


def _fact_to_json_value(item: EvidenceBackedFactView) -> JsonValue:
    """转换 fact item 为 JSON。

    :param item: fact item。
    :returns: JSON object。
    """

    return {
        "candidate_id": item.candidate_id,
        "claim_text": item.claim_text,
        "compact_artifact_ref": item.compact_artifact_ref,
        "evidence_kind": item.evidence_kind.value,
        "evidence_refs": list(item.evidence_refs),
        "excluded_reason": (
            None if item.excluded_reason is None else item.excluded_reason.value
        ),
        "extraction_operation_ref": item.extraction_operation_ref,
        "included_reason": (
            None if item.included_reason is None else item.included_reason.value
        ),
        "item_id": item.item_id,
        "provenance": _provenance_to_json_value(item.provenance),
        "size_units": item.size_units.units,
    }


def _fact_from_json_value(value: JsonValue) -> EvidenceBackedFactView:
    """从 JSON 恢复 fact item。

    :param value: JSON 值。
    :returns: fact item。
    """

    mapping = _as_mapping(value, "evidence_backed_fact")
    return EvidenceBackedFactView(
        item_id=_required_str(mapping, "item_id"),
        claim_text=_required_str(mapping, "claim_text"),
        evidence_kind=MemoryEvidenceBackedFactKind(
            _required_str(mapping, "evidence_kind")
        ),
        evidence_refs=_required_text_tuple(mapping, "evidence_refs"),
        provenance=_provenance_from_json_value(_required_value(mapping, "provenance")),
        extraction_operation_ref=_required_str(mapping, "extraction_operation_ref"),
        compact_artifact_ref=_optional_str(mapping, "compact_artifact_ref"),
        candidate_id=_required_str(mapping, "candidate_id"),
        included_reason=_optional_included_reason(mapping, "included_reason"),
        excluded_reason=_optional_excluded_reason(mapping, "excluded_reason"),
        size_units=MemorySizeUnits(_required_int(mapping, "size_units")),
    )


def _answer_anchor_to_json_value(item: AnswerAnchor) -> JsonValue:
    """转换 answer anchor 为 JSON。

    :param item: answer anchor。
    :returns: JSON object。
    """

    return {
        "anchor_items": [
            {"display_text": child.display_text, "ordinal": child.ordinal}
            for child in item.anchor_items
        ],
        "anchor_title": item.anchor_title,
        "event_id": item.event_id,
        "event_sequence": item.event_sequence,
        "item_id": item.item_id,
        "size_units": item.size_units.units,
        "source_refs": list(item.source_refs),
    }


def _answer_anchor_from_json_value(value: JsonValue) -> AnswerAnchor:
    """从 JSON 恢复 answer anchor。

    :param value: JSON 值。
    :returns: answer anchor。
    """

    mapping = _as_mapping(value, "answer_anchor")
    children = tuple(
        AnswerAnchorChild(
            display_text=_required_str(_as_mapping(item, "anchor_child"), "display_text"),
            ordinal=_optional_int(_as_mapping(item, "anchor_child"), "ordinal"),
        )
        for item in _required_list(mapping, "anchor_items")
    )
    return AnswerAnchor(
        item_id=_required_str(mapping, "item_id"),
        anchor_title=_required_str(mapping, "anchor_title"),
        anchor_items=children,
        source_refs=_required_text_tuple(mapping, "source_refs"),
        event_id=_required_str(mapping, "event_id"),
        event_sequence=_required_int(mapping, "event_sequence"),
        size_units=MemorySizeUnits(_required_int(mapping, "size_units")),
    )


def _forward_intent_to_json_value(item: ForwardIntent) -> JsonValue:
    """转换 forward intent 为 JSON。

    :param item: forward intent。
    :returns: JSON object。
    """

    return {
        "event_id": item.event_id,
        "event_sequence": item.event_sequence,
        "intent_type": item.intent_type,
        "item_id": item.item_id,
        "size_units": item.size_units.units,
        "source_refs": list(item.source_refs),
        "status": item.status,
        "text": item.text,
    }


def _forward_intent_from_json_value(value: JsonValue) -> ForwardIntent:
    """从 JSON 恢复 forward intent。

    :param value: JSON 值。
    :returns: forward intent。
    """

    mapping = _as_mapping(value, "forward_intent")
    return ForwardIntent(
        item_id=_required_str(mapping, "item_id"),
        intent_type=_required_str(mapping, "intent_type"),
        text=_required_str(mapping, "text"),
        status=_required_str(mapping, "status"),
        source_refs=_required_text_tuple(mapping, "source_refs"),
        event_id=_required_str(mapping, "event_id"),
        event_sequence=_required_int(mapping, "event_sequence"),
        size_units=MemorySizeUnits(_required_int(mapping, "size_units")),
    )


def _provenance_to_json_value(provenance: MemoryProvenanceRef) -> JsonValue:
    """转换 provenance 为 JSON。

    :param provenance: provenance ref。
    :returns: JSON object。
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
            {
                "digest": ref.digest,
                "ref_id": ref.ref_id,
                "ref_kind": ref.ref_kind.value,
            }
            for ref in provenance.source_refs
        ],
        "tool_result_ref": provenance.tool_result_ref,
    }


def _provenance_from_json_value(value: JsonValue) -> MemoryProvenanceRef:
    """从 JSON 恢复 provenance。

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
            OpaqueMemoryRef(
                ref_kind=HostNeutralRefKind(_required_str(_as_mapping(item, "source_ref"), "ref_kind")),
                ref_id=_required_str(_as_mapping(item, "source_ref"), "ref_id"),
                digest=_optional_str(_as_mapping(item, "source_ref"), "digest"),
            )
            for item in _required_list(mapping, "source_refs")
        ),
    )


def _optional_included_reason(
    mapping: Mapping[str, JsonValue], field_name: str
) -> MemoryIncludedReason | None:
    """读取可选 included reason。

    :param mapping: JSON mapping。
    :param field_name: 字段名。
    :returns: reason 或 ``None``。
    """

    value = _optional_str(mapping, field_name)
    return None if value is None else MemoryIncludedReason(value)


def _optional_excluded_reason(
    mapping: Mapping[str, JsonValue], field_name: str
) -> MemoryExcludedReason | None:
    """读取可选 excluded reason。

    :param mapping: JSON mapping。
    :param field_name: 字段名。
    :returns: reason 或 ``None``。
    """

    value = _optional_str(mapping, field_name)
    return None if value is None else MemoryExcludedReason(value)


def _fact_candidate_invalid_diagnostic(
    event: MemoryProjectionEvent,
    *,
    policy_digest: MemoryPolicyDigest,
    message: str,
) -> MemoryDiagnostic:
    """构造 fact candidate invalid diagnostic。

    :param event: compact event。
    :param policy_digest: policy digest。
    :param message: diagnostic message。
    :returns: diagnostic。
    """

    item_id = _item_id(event, "evidence_fact_candidate_invalid")
    return MemoryDiagnostic(
        diagnostic_id=_diagnostic_id(
            MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID,
            event_sequence=event.event_sequence,
            item_id=item_id,
        ),
        reason=MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID,
        message=message,
        event_sequence=event.event_sequence,
        item_id=item_id,
        policy_digest=policy_digest,
        recorded_at=None,
    )


def _budget_diagnostic(
    *,
    event_sequence: int,
    item_id: str,
    policy_digest: MemoryPolicyDigest,
    message: str,
) -> MemoryDiagnostic:
    """构造 budget diagnostic。

    :param event_sequence: event sequence。
    :param item_id: item id。
    :param policy_digest: policy digest。
    :param message: diagnostic message。
    :returns: diagnostic。
    """

    return MemoryDiagnostic(
        diagnostic_id=_diagnostic_id(
            MemoryDiagnosticReason.BUDGET_LIMIT_REACHED,
            event_sequence=event_sequence,
            item_id=item_id,
        ),
        reason=MemoryDiagnosticReason.BUDGET_LIMIT_REACHED,
        message=message,
        event_sequence=event_sequence,
        item_id=item_id,
        policy_digest=policy_digest,
        recorded_at=None,
    )


def _unsupported_event_type_diagnostic(
    event: MemoryProjectionEvent, *, policy_digest: MemoryPolicyDigest
) -> MemoryDiagnostic:
    """构造 unsupported event diagnostic。

    :param event: 未支持 event。
    :param policy_digest: policy digest。
    :returns: diagnostic。
    """

    item_id = _item_id(event, MemoryExcludedReason.UNSUPPORTED_EVENT_TYPE.value)
    return MemoryDiagnostic(
        diagnostic_id=_diagnostic_id(
            MemoryDiagnosticReason.UNSUPPORTED_EVENT_TYPE,
            event_sequence=event.event_sequence,
            item_id=item_id,
        ),
        reason=MemoryDiagnosticReason.UNSUPPORTED_EVENT_TYPE,
        message=f"unsupported memory event_type={event.event_type}",
        event_sequence=event.event_sequence,
        item_id=item_id,
        policy_digest=policy_digest,
        recorded_at=None,
    )


def _dedupe_diagnostics(
    diagnostics: tuple[MemoryDiagnostic, ...],
) -> tuple[MemoryDiagnostic, ...]:
    """按 diagnostic id 去重。

    :param diagnostics: diagnostics。
    :returns: 去重后的 diagnostics。
    """

    seen: set[str] = set()
    result: list[MemoryDiagnostic] = []
    for diagnostic in diagnostics:
        if diagnostic.diagnostic_id in seen:
            continue
        seen.add(diagnostic.diagnostic_id)
        result.append(diagnostic)
    return tuple(result)


def _item_id(event: MemoryProjectionEvent, local_key: str) -> str:
    """派生 memory item id。

    :param event: projection event。
    :param local_key: event-local key。
    :returns: item id。
    """

    digest = sha256_digest_json(
        {
            "event_id": event.event_id,
            "event_sequence": event.event_sequence,
            "local_key": local_key,
            "session_id": event.session_id,
        }
    ).removeprefix("sha256:")
    return f"{_ITEM_ID_PREFIX}-{digest}"


def _diagnostic_id(
    reason: MemoryDiagnosticReason, *, event_sequence: int, item_id: str
) -> str:
    """派生 diagnostic id。

    :param reason: diagnostic reason。
    :param event_sequence: event sequence。
    :param item_id: item id。
    :returns: diagnostic id。
    """

    digest = sha256_digest_json(
        {
            "event_sequence": event_sequence,
            "item_id": item_id,
            "reason": reason.value,
        }
    ).removeprefix("sha256:")
    return f"{_DIAGNOSTIC_ID_PREFIX}-{digest}"


def _item_size_units(item: _MemoryItemWithId) -> int:
    """读取 item size units。

    :param item: memory item。
    :returns: size units。
    """

    return item.size_units.units


def _item_event_sequence(item: _MemoryItemWithId) -> int:
    """读取 item event sequence。

    :param item: memory item。
    :returns: event sequence。
    """

    return item.event_sequence


def _user_visible_text(event: MemoryProjectionEvent) -> str:
    """读取用户可见文本。

    :param event: projection event。
    :returns: 用户可见文本；缺失时返回不含内部治理标识的占位文本。
    """

    display_text = _optional_payload_str(event.payload, _PAYLOAD_FIELD_DISPLAY_TEXT)
    if display_text is not None:
        return display_text
    return _USER_INPUT_TEXT_UNAVAILABLE


def _normalized_text(text: str) -> str:
    """规范化文本用于去重。

    :param text: 原始文本。
    :returns: 规范化文本。
    """

    return " ".join(text.casefold().split())


def _validate_reason_pair(
    included_reason: MemoryIncludedReason | None,
    excluded_reason: MemoryExcludedReason | None,
) -> None:
    """校验 included / excluded reason 互斥。

    :param included_reason: included reason。
    :param excluded_reason: excluded reason。
    :returns: ``None``。
    :raises ValueError: 二者同时存在时抛出。
    """

    if included_reason is not None and excluded_reason is not None:
        raise ValueError("included_reason and excluded_reason are mutually exclusive")


def _require_positive(value: int, field_name: str) -> None:
    """校验正整数。

    :param value: 待校验值。
    :param field_name: 字段名。
    :returns: ``None``。
    """

    if value < _MIN_POSITIVE_LIMIT:
        raise ValueError(f"{field_name} must be positive")


def _require_non_negative(value: int, field_name: str) -> None:
    """校验非负整数。

    :param value: 待校验值。
    :param field_name: 字段名。
    :returns: ``None``。
    """

    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_non_empty(value: str, field_name: str) -> None:
    """校验非空字符串。

    :param value: 字符串值。
    :param field_name: 字段名。
    :returns: ``None``。
    """

    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_non_empty(value: str | None, field_name: str) -> None:
    """校验可选字符串非空。

    :param value: 字符串值。
    :param field_name: 字段名。
    :returns: ``None``。
    """

    if value is not None:
        _require_non_empty(value, field_name)


def _require_non_empty_items(values: tuple[str, ...], field_name: str) -> None:
    """校验字符串 tuple 元素非空。

    :param values: 字符串 tuple。
    :param field_name: 字段名。
    :returns: ``None``。
    """

    for value in values:
        _require_non_empty(value, field_name)


def _required_value(mapping: Mapping[str, JsonValue], field_name: str) -> JsonValue:
    """读取必填 JSON 字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :returns: JSON 值。
    """

    if field_name not in mapping:
        raise ValueError(f"{field_name} is required")
    return mapping[field_name]


def _required_payload_mapping(
    payload: Mapping[str, JsonValue], field_name: str
) -> Mapping[str, JsonValue]:
    """读取必填 payload object 字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: JSON object。
    """

    return _as_mapping(_required_value(payload, field_name), field_name)


def _as_mapping(value: JsonValue, field_name: str) -> Mapping[str, JsonValue]:
    """校验 JSON 值为 object。

    :param value: JSON 值。
    :param field_name: 字段名。
    :returns: JSON object。
    """

    if isinstance(value, Mapping):
        return value
    raise ValueError(f"{field_name} must be JSON mapping")


def _required_str(mapping: Mapping[str, JsonValue], field_name: str) -> str:
    """读取必填字符串字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :returns: 字符串。
    """

    value = _required_value(mapping, field_name)
    if isinstance(value, str):
        _require_non_empty(value, field_name)
        return value
    raise ValueError(f"{field_name} must be string")


def _optional_str(
    mapping: Mapping[str, JsonValue], field_name: str
) -> str | None:
    """读取可选字符串字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :returns: 字符串或 ``None``。
    """

    value = _required_value(mapping, field_name)
    if value is None:
        return None
    if isinstance(value, str):
        _require_non_empty(value, field_name)
        return value
    raise ValueError(f"{field_name} must be string")


def _optional_payload_str(
    mapping: Mapping[str, JsonValue], field_name: str
) -> str | None:
    """读取 payload 可选字符串字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :returns: 字符串或 ``None``。
    """

    value = mapping.get(field_name)
    if value is None:
        return None
    if isinstance(value, str):
        _require_non_empty(value, field_name)
        return value
    raise ValueError(f"{field_name} must be string")


def _required_int(mapping: Mapping[str, JsonValue], field_name: str) -> int:
    """读取必填整数字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :returns: 整数。
    """

    value = _required_value(mapping, field_name)
    if isinstance(value, int):
        return value
    raise ValueError(f"{field_name} must be integer")


def _optional_int(mapping: Mapping[str, JsonValue], field_name: str) -> int | None:
    """读取可选整数字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :returns: 整数或 ``None``。
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

    :param mapping: JSON object。
    :param field_name: 字段名。
    :returns: JSON array。
    """

    value = _required_value(mapping, field_name)
    if isinstance(value, list):
        return value
    raise ValueError(f"{field_name} must be list")


def _required_text_tuple(
    mapping: Mapping[str, JsonValue], field_name: str
) -> tuple[str, ...]:
    """读取必填字符串数组字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :returns: 字符串 tuple。
    """

    result: list[str] = []
    for item in _required_list(mapping, field_name):
        if not isinstance(item, str):
            raise ValueError(f"{field_name} items must be string")
        _require_non_empty(item, field_name)
        result.append(item)
    return tuple(result)


def _required_mapping_list(
    mapping: Mapping[str, JsonValue], field_name: str
) -> tuple[Mapping[str, JsonValue], ...]:
    """读取必填 JSON object 数组字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :returns: JSON object tuple。
    """

    result: list[Mapping[str, JsonValue]] = []
    for index, item in enumerate(_required_list(mapping, field_name)):
        result.append(_as_mapping(item, f"{field_name}[{index}]"))
    return tuple(result)


__all__ = [
    "CONVERSATION_MEMORY_CONSUMER_ID",
    "CONVERSATION_MEMORY_SNAPSHOT_SCHEMA_VERSION",
    "DEFAULT_ANSWER_ANCHOR_CHAR_CAP",
    "DEFAULT_ANSWER_ANCHOR_ITEM_CAP",
    "DEFAULT_EVIDENCE_FACT_CHAR_CAP",
    "DEFAULT_EVIDENCE_FACT_FLOOR",
    "DEFAULT_EVIDENCE_FACT_ITEM_CAP",
    "DEFAULT_FALLBACK_SELECTED_RECENT_WINDOW_CHAR_CAP",
    "DEFAULT_FALLBACK_SELECTED_RECENT_WINDOW_ITEM_CAP",
    "DEFAULT_FORWARD_INTENT_CHAR_CAP",
    "DEFAULT_FORWARD_INTENT_ITEM_CAP",
    "DEFAULT_MEMORY_CONTEXT_WINDOW_SIZE",
    "DEFAULT_MEMORY_MAX_DELTA_REPAIR_EVENTS",
    "DEFAULT_MEMORY_MAX_LAG_EVENTS_FOR_INLINE_DELTA",
    "DEFAULT_MEMORY_POLICY_REF",
    "DEFAULT_REFERENCE_CONTINUITY_CHAR_CAP",
    "DEFAULT_REFERENCE_CONTINUITY_ITEM_CAP",
    "DEFAULT_REFERENCE_CONTINUITY_ITEM_FLOOR",
    "DEFAULT_SELECTED_RECENT_WINDOW_CHAR_CAP",
    "DEFAULT_SELECTED_RECENT_WINDOW_ITEM_CAP",
    "DEFAULT_SELECTED_RECENT_WINDOW_TURN_FLOOR",
    "DEFAULT_SESSION_SUMMARY_CHAR_CAP",
    "AnswerAnchor",
    "AnswerAnchorChild",
    "AnswerAnchorMemoryView",
    "ConversationMemorySnapshotVNext",
    "EvidenceBackedFactView",
    "EvidenceFactMemoryView",
    "ForwardIntent",
    "ForwardIntentMemoryView",
    "HostEventRef",
    "HostNeutralRefKind",
    "HostPayloadRef",
    "MemoryClaimStatus",
    "MemoryDiagnostic",
    "MemoryDiagnosticReason",
    "MemoryDigestRef",
    "MemoryEvidenceBackedFactKind",
    "MemoryExcludedReason",
    "MemoryIncludedReason",
    "MemoryPolicyDigest",
    "MemoryProducerKind",
    "MemoryProjectionEvent",
    "MemoryProjectionPolicy",
    "MemoryProvenanceRef",
    "MemoryRepairReason",
    "MemoryRepairRequest",
    "MemorySizeUnits",
    "MemorySnapshotCursor",
    "OpaqueMemoryRef",
    "ReferenceContinuityItem",
    "SelectedRecentWindowItem",
    "SelectedRecentWindowRole",
    "SessionSummaryMemoryView",
    "TraceMemoryView",
    "build_conversation_memory_snapshot_from_events",
    "build_empty_conversation_memory_snapshot",
    "build_inline_delta_repair_diagnostic",
    "build_memory_budget_diagnostic",
    "calculate_memory_snapshot_digest",
    "conversation_memory_snapshot_from_json_value",
    "conversation_memory_snapshot_to_json_value",
    "default_memory_projection_policy",
    "digest_memory_projection_policy",
    "estimate_memory_size_units",
    "memory_diagnostic_from_json_value",
    "memory_diagnostic_to_json_value",
    "memory_projection_policy_to_json_value",
    "memory_snapshot_with_cursor_and_diagnostics",
    "project_conversation_memory_event",
    "stable_memory_snapshot_id",
]
