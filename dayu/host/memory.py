"""Host Conversation Memory typed contracts。

本模块定义 Phase 9 session memory projection 的层中立契约。Memory 是
EventLog 的可重建 read model，不是 Host governance truth；本模块不读取
durable store，不导入 Engine / Fins / Service / UI，也不表达财报业务字段。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeAlias, TypeVar

from dayu.contracts.json_value import JsonValue
from dayu.host.context_events import (
    CONTEXT_COMPACTED as _EVENT_TYPE_CONTEXT_COMPACTED,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.terminal_summary_payload import (
    PayloadSummaryTextPolicy,
    assistant_summary_from_payload,
)

MemoryPolicyDigest: TypeAlias = str
"""Memory policy canonical JSON digest。"""

MemoryDigestRef: TypeAlias = str
"""Memory provenance 使用的 digest ref 文本。"""

HostEventRef: TypeAlias = str
"""Host EventLog ref 文本。"""

HostPayloadRef: TypeAlias = str
"""Host payload descriptor ref 文本。"""

_MemoryItemT = TypeVar("_MemoryItemT", bound="_MemoryItemWithId")

_MIN_SEQUENCE = 0
_MIN_POSITIVE_LIMIT = 1
_EMPTY_SIZE_UNITS = 0
MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS = 2000
"""Memory-owned evidence-backed fact claim_text 字符数上限。"""

MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS = 1200
"""Memory-owned continuity text 字符数上限。"""

CONVERSATION_MEMORY_CONSUMER_ID = "host.memory.session.v1"
"""Conversation memory projection consumer 稳定 id。"""

DEFAULT_MEMORY_MAX_PINNED_ITEMS = 8
DEFAULT_MEMORY_MAX_EVIDENCE_BACKED_FACTS = 16
DEFAULT_MEMORY_MAX_WORKING_ASSUMPTIONS = 8
DEFAULT_MEMORY_RECENT_RAW_TURNS_FLOOR = 2
DEFAULT_MEMORY_MAX_EPISODE_SUMMARIES_FLOOR = 1
DEFAULT_MEMORY_CONTEXT_WINDOW_SIZE = 8192
DEFAULT_MEMORY_RAW_TURN_CONTEXT_RATIO = 0.125
DEFAULT_MEMORY_RAW_TURN_SIZE_FLOOR = 256
DEFAULT_MEMORY_RAW_TURN_SIZE_CAP = 1024
DEFAULT_MEMORY_HISTORY_POOL_CONTEXT_RATIO = 0.5
DEFAULT_MEMORY_HISTORY_POOL_SIZE_FLOOR = 1024
DEFAULT_MEMORY_HISTORY_POOL_SIZE_CAP = 4096
DEFAULT_MEMORY_STABLE_LAYER_CONTEXT_RATIO = 0.25
DEFAULT_MEMORY_STABLE_LAYER_SIZE_FLOOR = 512
DEFAULT_MEMORY_STABLE_LAYER_SIZE_CAP = 2048
DEFAULT_MEMORY_MAX_LAG_EVENTS_FOR_INLINE_DELTA = 16
DEFAULT_MEMORY_MAX_DELTA_REPAIR_EVENTS = 32

_EVENT_TYPE_USER_INPUT_ACCEPTED = "USER_INPUT_ACCEPTED"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_PRODUCER_NAME_HOST_PROJECTION = "host_projection"
_SNAPSHOT_DIGEST_PENDING = "pending"
_PAYLOAD_FIELD_DISPLAY_TEXT = "display_text"
_PAYLOAD_FIELD_SUMMARY_TEXT = "summary_text"
_PAYLOAD_FIELD_EPISODE_SUMMARY_CANDIDATE = "episode_summary_candidate"
_PAYLOAD_FIELD_PINNED_STATE_PATCH_CANDIDATE = "pinned_state_patch_candidate"
_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_CANDIDATES = (
    "evidence_backed_fact_candidates"
)
_PAYLOAD_FIELD_MINIMUM_PRESERVE_ITEM_CANDIDATES = (
    "minimum_preserve_item_candidates"
)
_PAYLOAD_FIELD_COMPACT_ARTIFACT_REF = "compact_artifact_ref"
_PAYLOAD_FIELD_EPISODE_TITLE = "episode_title"
_PAYLOAD_FIELD_TITLE = "title"
_PAYLOAD_FIELD_GOAL = "goal"
_PAYLOAD_FIELD_COMPLETED_ACTIONS = "completed_actions"
_PAYLOAD_FIELD_OPEN_QUESTIONS = "open_questions"
_PAYLOAD_FIELD_NEXT_STEP = "next_step"
_PAYLOAD_FIELD_USER_CONSTRAINTS = "user_constraints"
_PAYLOAD_FIELD_CONFIRMED_FACT_REFS = "confirmed_fact_refs"
_PAYLOAD_FIELD_CONFIRMED_SUBJECTS = "confirmed_subjects"
_PAYLOAD_FIELD_CURRENT_GOAL = "current_goal"
_PAYLOAD_FIELD_OPERATION = "operation"
_PAYLOAD_FIELD_VALUE = "value"
_PAYLOAD_FIELD_REF_KIND = "ref_kind"
_PAYLOAD_FIELD_REF_ID = "ref_id"
_PAYLOAD_FIELD_DIGEST = "digest"
_PAYLOAD_FIELD_SUMMARY = "summary"
_PAYLOAD_FIELD_PAYLOAD_REF = "payload_ref"
_PAYLOAD_FIELD_PAYLOAD_DIGEST = "payload_digest"
_PAYLOAD_FIELD_RUN_ID = "run_id"
_PAYLOAD_FIELD_ATTEMPT_ID = "attempt_id"
_PAYLOAD_FIELD_EXECUTION_ID = "execution_id"
_PAYLOAD_FIELD_CANDIDATE_ID = "candidate_id"
_PAYLOAD_FIELD_CLAIM_TEXT = "claim_text"
_PAYLOAD_FIELD_EVIDENCE_KIND = "evidence_kind"
_PAYLOAD_FIELD_EVIDENCE_REFS = "evidence_refs"
_PAYLOAD_FIELD_PRESERVED_FACT_REFS = "preserved_fact_refs"
_PAYLOAD_FIELD_CANONICAL_EVIDENCE_REFS = "canonical_evidence_refs"
_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_REFS = "evidence_backed_fact_refs"
_PAYLOAD_FIELD_QUALITY_CHECK_RESULT = "quality_check_result"
_PAYLOAD_FIELD_ACCEPTED_CANDIDATE = "accepted_candidate"
_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS = "accepted_evidence_mapping_refs"
_PAYLOAD_FIELD_SESSION_SUMMARY = "session_summary"
_PAYLOAD_FIELD_EVIDENCE_BACKED_FACTS = "evidence_backed_facts"
_PAYLOAD_FIELD_REFERENCE_CONTINUITY_ITEMS = "reference_continuity_items"
_PAYLOAD_FIELD_SOURCE_LABELS = "source_labels"
_PAYLOAD_FIELD_EVIDENCE_LABELS = "evidence_labels"
_PAYLOAD_FIELD_REASON = "reason"
_PAYLOAD_FIELD_SCHEMA_VERSION = "schema_version"
_PAYLOAD_FIELD_ATTRIBUTES = "attributes"
_PAYLOAD_FIELD_ITEM_ID = "item_id"
_PAYLOAD_FIELD_LABEL = "label"
_PAYLOAD_FIELD_TEXT = "text"
_PAYLOAD_FIELD_SOURCE_REFS = "source_refs"
_PAYLOAD_FIELD_SOURCE_EVENT_REFS = "source_event_refs"
_PAYLOAD_FIELD_PRESERVE_REASON = "preserve_reason"
_EVENT_REF_PREFIX = "event:"
_SNAPSHOT_ID_DIGEST_PREFIX = "memory-snapshot-"
_ITEM_ID_PREFIX = "memory-item"
_DIAGNOSTIC_ID_PREFIX = "memory-diagnostic"


class MemoryEvidenceBackedFactKind(StrEnum):
    """Memory projection 使用的 evidence-backed fact 类型。"""

    OBSERVED_VALUE = "observed_value"
    QUOTED_STATEMENT = "quoted_statement"
    TABLE_VALUE = "table_value"
    DERIVED_FROM_EVIDENCE = "derived_from_evidence"


class MemoryContinuityPreserveReason(StrEnum):
    """Memory projection 使用的局部连续性保留原因。"""

    NEEDED_FOR_RECENT_REFERENCE = "needed_for_recent_reference"
    NEEDED_FOR_ORDERED_ITEM_REFERENCE = "needed_for_ordered_item_reference"
    NEEDED_FOR_LOCAL_FOLLOWUP = "needed_for_local_followup"


class _MemoryItemWithId(Protocol):
    """仅用于内部泛型去重的 item id 协议。"""

    @property
    def item_id(self) -> str:
        """返回 item id。

        :returns: item id。
        """

        ...


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
    EVIDENCE_BACKED_FACT = "evidence_backed_fact"
    MINIMUM_PRESERVE_ITEM = "minimum_preserve_item"
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
    MINIMUM_PRESERVE_ITEM = "minimum_preserve_item"


class MemoryDiagnosticReason(StrEnum):
    """Memory diagnostic 的结构化原因。"""

    EVIDENCE_BACKED_FACT_CANDIDATE_INVALID = (
        "evidence_backed_fact_candidate_invalid"
    )
    INLINE_DELTA_REPAIR_INCLUDED = "inline_delta_repair_included"
    SNAPSHOT_MISSING = "snapshot_missing"
    SNAPSHOT_DAMAGED = "snapshot_damaged"
    UNSUPPORTED_EVENT_TYPE = "unsupported_event_type"
    SNAPSHOT_LAG_OVER_THRESHOLD = "snapshot_lag_over_threshold"
    BUDGET_LIMIT_REACHED = "budget_limit_reached"
    EMPTY_EVENT_LOG_SNAPSHOT = "empty_event_log_snapshot"
    EVIDENCE_BACKED_FACT_SUPERSEDED = "evidence_backed_fact_superseded"
    MINIMUM_PRESERVE_ITEM_COVERED = "minimum_preserve_item_covered"


class MemoryRepairReason(StrEnum):
    """Memory snapshot 需要 repair 的结构化原因。"""

    SNAPSHOT_MISSING = "snapshot_missing"
    SNAPSHOT_DAMAGED = "snapshot_damaged"
    SNAPSHOT_LAG_OVER_THRESHOLD = "snapshot_lag_over_threshold"
    SNAPSHOT_AHEAD_OF_REQUIRED = "snapshot_ahead_of_required"


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
        object.__setattr__(
            self,
            "open_questions",
            _dedupe_text_tuple_by_normalized_text(self.open_questions),
        )


@dataclass(frozen=True, slots=True)
class EvidenceBackedFactView:
    """Evidence-backed fact memory view。

    :param item_id: item 稳定 id。
    :param claim_text: 绑定 accepted evidence 的事实声明文本。
    :param evidence_kind: 事实声明的 Host-neutral 类型。
    :param evidence_refs: 支撑该声明的 accepted evidence refs。
    :param attributes: Host 不解释的 JSON attributes。
    :param provenance: 来源 provenance，必须指向 accepted ``CONTEXT_COMPACTED``。
    :param extraction_operation_ref: Host 可信 extraction operation ref。
    :param compact_artifact_ref: 可选 compact artifact ref。
    :param candidate_id: candidate-local 诊断 id，不是权威 provenance。
    :param included_reason: 可选纳入原因。
    :param excluded_reason: 可选排除原因。
    :param size_units: 统一尺寸单位。
    """

    item_id: str
    claim_text: str
    evidence_kind: MemoryEvidenceBackedFactKind
    evidence_refs: tuple[str, ...]
    attributes: Mapping[str, JsonValue]
    provenance: MemoryProvenanceRef
    extraction_operation_ref: str
    compact_artifact_ref: str | None
    candidate_id: str
    included_reason: MemoryIncludedReason | None
    excluded_reason: MemoryExcludedReason | None
    size_units: MemorySizeUnits

    def __post_init__(self) -> None:
        """校验 evidence-backed fact 的 compact provenance 与证据引用。

        :returns: ``None``。
        :raises ValueError: id / claim / refs / provenance 非法时抛出。
        """

        _require_non_empty(self.item_id, "item_id")
        _require_non_empty(self.claim_text, "claim_text")
        if len(self.claim_text) > MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS:
            raise ValueError("claim_text exceeds maximum length")
        if not isinstance(self.evidence_kind, MemoryEvidenceBackedFactKind):
            raise ValueError("evidence_kind must be MemoryEvidenceBackedFactKind")
        if len(self.evidence_refs) == 0:
            raise ValueError("evidence_refs must be non-empty")
        _require_non_empty_items(self.evidence_refs, "evidence_refs")
        if not isinstance(self.attributes, Mapping):
            raise ValueError("attributes must be JSON mapping")
        if self.provenance.producer_kind is not MemoryProducerKind.HOST_PROJECTION:
            raise ValueError(
                "evidence-backed fact provenance producer must be HOST_PROJECTION"
            )
        _require_non_empty(self.extraction_operation_ref, "extraction_operation_ref")
        _require_optional_non_empty(self.compact_artifact_ref, "compact_artifact_ref")
        _require_non_empty(self.candidate_id, "candidate_id")
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
    :param label: 可选短标签。
    :param source_refs: continuity 来源 refs。
    :param preserve_reason: minimum preserve 保留原因。
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
    label: str | None
    source_refs: tuple[str, ...]
    preserve_reason: MemoryContinuityPreserveReason | None
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
        _require_optional_non_empty(self.label, "label")
        _require_non_empty_items(self.source_refs, "source_refs")
        if (
            self.preserve_reason is not None
            and not isinstance(self.preserve_reason, MemoryContinuityPreserveReason)
        ):
            raise ValueError("preserve_reason must be MemoryContinuityPreserveReason")
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
class MemoryRepairRequest:
    """Memory projection repair 请求。

    :param session_id: 需要 repair 的 Session id。
    :param reason: repair 结构化原因。
    :param required_event_sequence: RunInputBuilder 本次需要覆盖的 EventLog cursor。
    :param observed_cursor: 已观测到的 snapshot cursor；缺失 snapshot 时为 ``None``。
    :param policy_digest: 当前 memory policy digest。
    """

    session_id: str
    reason: MemoryRepairReason
    required_event_sequence: int
    observed_cursor: MemorySnapshotCursor | None
    policy_digest: MemoryPolicyDigest

    def __post_init__(self) -> None:
        """校验 repair 请求字段。

        :returns: ``None``。
        :raises ValueError: 字段为空、reason 非法或 required cursor 为负数时抛出。
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

    :param context_window_size: Service / composition root 显式传入的上下文窗口 token 数。
    :param max_pinned_items: pinned state 最大条目数。
    :param max_evidence_backed_facts: evidence-backed facts 最大条目数。
    :param max_working_assumptions: working assumptions 最大条目数。
    :param recent_raw_turns_floor: recent raw turns 保底条数。
    :param raw_turn_context_ratio: 单条 raw turn 尺寸占上下文窗口比例。
    :param raw_turn_size_floor: 单条 raw turn 尺寸下限。
    :param raw_turn_size_cap: 单条 raw turn 尺寸上限。
    :param history_pool_context_ratio: history pool 尺寸占上下文窗口比例。
    :param history_pool_size_floor: history pool 尺寸下限。
    :param history_pool_size_cap: history pool 尺寸上限。
    :param stable_layer_context_ratio: stable layer 尺寸占上下文窗口比例。
    :param stable_layer_size_floor: stable layer 尺寸下限。
    :param stable_layer_size_cap: stable layer 尺寸上限。
    :param max_lag_events_for_inline_delta: inline delta 允许的最大滞后事件数。
    :param max_delta_repair_events: repair delta 最大事件数。
    """

    context_window_size: int
    max_pinned_items: int
    max_evidence_backed_facts: int
    max_working_assumptions: int
    recent_raw_turns_floor: int
    raw_turn_context_ratio: float
    raw_turn_size_floor: int
    raw_turn_size_cap: int
    history_pool_context_ratio: float
    history_pool_size_floor: int
    history_pool_size_cap: int
    stable_layer_context_ratio: float
    stable_layer_size_floor: int
    stable_layer_size_cap: int
    max_lag_events_for_inline_delta: int
    max_delta_repair_events: int

    def __post_init__(self) -> None:
        """校验 policy limit。

        :returns: ``None``。
        :raises ValueError: 任一 limit 小于允许下限时抛出。
        """

        _require_positive(self.context_window_size, "context_window_size")
        _require_positive(self.max_pinned_items, "max_pinned_items")
        _require_positive(self.max_evidence_backed_facts, "max_evidence_backed_facts")
        _require_positive(
            self.max_working_assumptions, "max_working_assumptions"
        )
        _require_non_negative(
            self.recent_raw_turns_floor, "recent_raw_turns_floor"
        )
        _require_ratio(self.raw_turn_context_ratio, "raw_turn_context_ratio")
        _require_floor_cap(
            floor_value=self.raw_turn_size_floor,
            cap_value=self.raw_turn_size_cap,
            floor_field_name="raw_turn_size_floor",
            cap_field_name="raw_turn_size_cap",
        )
        _require_ratio(
            self.history_pool_context_ratio, "history_pool_context_ratio"
        )
        _require_floor_cap(
            floor_value=self.history_pool_size_floor,
            cap_value=self.history_pool_size_cap,
            floor_field_name="history_pool_size_floor",
            cap_field_name="history_pool_size_cap",
        )
        _require_ratio(
            self.stable_layer_context_ratio, "stable_layer_context_ratio"
        )
        _require_floor_cap(
            floor_value=self.stable_layer_size_floor,
            cap_value=self.stable_layer_size_cap,
            floor_field_name="stable_layer_size_floor",
            cap_field_name="stable_layer_size_cap",
        )
        _require_non_negative(
            self.max_lag_events_for_inline_delta,
            "max_lag_events_for_inline_delta",
        )
        _require_non_negative(self.max_delta_repair_events, "max_delta_repair_events")

    @property
    def max_raw_turn_size_units(self) -> int:
        """返回 Host 内部派生的单条 raw turn 最大尺寸单位。

        :returns: ratio / floor / cap 派生后的尺寸单位。
        """

        return _effective_size_units(
            context_window_size=self.context_window_size,
            ratio=self.raw_turn_context_ratio,
            floor_value=self.raw_turn_size_floor,
            cap_value=self.raw_turn_size_cap,
        )

    @property
    def history_pool_size_units(self) -> int:
        """返回 Host 内部派生的 history pool 尺寸单位。

        :returns: ratio / floor / cap 派生后的尺寸单位。
        """

        return _effective_size_units(
            context_window_size=self.context_window_size,
            ratio=self.history_pool_context_ratio,
            floor_value=self.history_pool_size_floor,
            cap_value=self.history_pool_size_cap,
        )

    @property
    def stable_layer_size_units(self) -> int:
        """返回 Host 内部派生的 stable layer 尺寸单位。

        :returns: ratio / floor / cap 派生后的尺寸单位。
        """

        return _effective_size_units(
            context_window_size=self.context_window_size,
            ratio=self.stable_layer_context_ratio,
            floor_value=self.stable_layer_size_floor,
            cap_value=self.stable_layer_size_cap,
        )


def default_memory_projection_policy(
    *, context_window_size: int = DEFAULT_MEMORY_CONTEXT_WINDOW_SIZE
) -> MemoryProjectionPolicy:
    """构造 Host 本地执行默认 conversation memory projection policy。

    :param context_window_size: Service / composition root 显式传入的上下文窗口 token 数。
    :returns: 默认 memory projection policy。
    :raises ValueError: 默认常量非法时抛出。
    """

    return MemoryProjectionPolicy(
        context_window_size=context_window_size,
        max_pinned_items=DEFAULT_MEMORY_MAX_PINNED_ITEMS,
        max_evidence_backed_facts=DEFAULT_MEMORY_MAX_EVIDENCE_BACKED_FACTS,
        max_working_assumptions=DEFAULT_MEMORY_MAX_WORKING_ASSUMPTIONS,
        recent_raw_turns_floor=DEFAULT_MEMORY_RECENT_RAW_TURNS_FLOOR,
        raw_turn_context_ratio=DEFAULT_MEMORY_RAW_TURN_CONTEXT_RATIO,
        raw_turn_size_floor=DEFAULT_MEMORY_RAW_TURN_SIZE_FLOOR,
        raw_turn_size_cap=DEFAULT_MEMORY_RAW_TURN_SIZE_CAP,
        history_pool_context_ratio=DEFAULT_MEMORY_HISTORY_POOL_CONTEXT_RATIO,
        history_pool_size_floor=DEFAULT_MEMORY_HISTORY_POOL_SIZE_FLOOR,
        history_pool_size_cap=DEFAULT_MEMORY_HISTORY_POOL_SIZE_CAP,
        stable_layer_context_ratio=DEFAULT_MEMORY_STABLE_LAYER_CONTEXT_RATIO,
        stable_layer_size_floor=DEFAULT_MEMORY_STABLE_LAYER_SIZE_FLOOR,
        stable_layer_size_cap=DEFAULT_MEMORY_STABLE_LAYER_SIZE_CAP,
        max_lag_events_for_inline_delta=(
            DEFAULT_MEMORY_MAX_LAG_EVENTS_FOR_INLINE_DELTA
        ),
        max_delta_repair_events=DEFAULT_MEMORY_MAX_DELTA_REPAIR_EVENTS,
    )


@dataclass(frozen=True, slots=True)
class ConversationMemorySnapshot:
    """Conversation memory snapshot。

    :param snapshot_id: snapshot 稳定 id。
    :param session_id: session id。
    :param cursor: snapshot 覆盖的 EventLog cursor。
    :param policy_digest: projection policy digest。
    :param pinned_state: pinned state view。
    :param evidence_backed_facts: tool evidence-backed facts。
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
    evidence_backed_facts: tuple[EvidenceBackedFactView, ...]
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


@dataclass(frozen=True, slots=True)
class MemoryProjectionEvent:
    """Memory projection 使用的 Host 中立 EventLog view。

    :param event_sequence: EventLog 全局 sequence。
    :param event_id: EventLog id。
    :param event_class: EventLog class 文本。
    :param event_type: EventLog type 文本。
    :param session_id: Session id。
    :param run_id: 可选 Run id。
    :param attempt_id: 可选 Attempt id。
    :param execution_id: 可选 execution id。
    :param occurred_at: 事件发生 UTC timestamp 文本。
    :param payload_ref: 可选 payload descriptor ref。
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
        """校验 projection event 的最小字段。

        :returns: ``None``。
        :raises ValueError: 必填文本为空、sequence 非正数或 payload ref 不成对时抛出。
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


def memory_snapshot_with_cursor_and_diagnostics(
    *,
    snapshot: ConversationMemorySnapshot,
    cursor: MemorySnapshotCursor,
    diagnostics: tuple[MemoryDiagnostic, ...],
) -> ConversationMemorySnapshot:
    """返回替换 cursor 并追加 diagnostics 后的新 snapshot。

    :param snapshot: 原始 memory snapshot。
    :param cursor: 新 snapshot cursor。
    :param diagnostics: 需要追加的 diagnostics。
    :returns: 重新计算 digest 后的 snapshot。
    :raises ValueError: cursor session 与 snapshot session 不一致时抛出。
    """

    if cursor.session_id != snapshot.session_id:
        raise ValueError("cursor session_id must match snapshot session_id")
    snapshot_without_digest = ConversationMemorySnapshot(
        snapshot_id=snapshot.snapshot_id,
        session_id=snapshot.session_id,
        cursor=cursor,
        policy_digest=snapshot.policy_digest,
        pinned_state=snapshot.pinned_state,
        evidence_backed_facts=snapshot.evidence_backed_facts,
        working_assumptions=snapshot.working_assumptions,
        conversation_continuity=snapshot.conversation_continuity,
        diagnostics=_dedupe_diagnostics(snapshot.diagnostics + diagnostics),
        built_at=snapshot.built_at,
        snapshot_digest=_SNAPSHOT_DIGEST_PENDING,
    )
    return ConversationMemorySnapshot(
        snapshot_id=snapshot_without_digest.snapshot_id,
        session_id=snapshot_without_digest.session_id,
        cursor=snapshot_without_digest.cursor,
        policy_digest=snapshot_without_digest.policy_digest,
        pinned_state=snapshot_without_digest.pinned_state,
        evidence_backed_facts=snapshot_without_digest.evidence_backed_facts,
        working_assumptions=snapshot_without_digest.working_assumptions,
        conversation_continuity=snapshot_without_digest.conversation_continuity,
        diagnostics=snapshot_without_digest.diagnostics,
        built_at=snapshot_without_digest.built_at,
        snapshot_digest=calculate_memory_snapshot_digest(snapshot_without_digest),
    )


def build_inline_delta_repair_diagnostic(
    *,
    event_sequence: int,
    policy_digest: MemoryPolicyDigest,
) -> MemoryDiagnostic:
    """构造 inline delta repair diagnostic。

    :param event_sequence: inline repair 覆盖到的 EventLog sequence。
    :param policy_digest: 当前 memory policy digest。
    :returns: 结构化 memory diagnostic。
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
    """构造对外可复用的 memory budget diagnostic。

    :param event_sequence: 关联 EventLog sequence。
    :param item_id: 关联 memory item 或渲染 block id。
    :param policy_digest: memory policy digest。
    :param message: diagnostic message。
    :returns: 结构化 memory diagnostic。
    """

    return _budget_diagnostic(
        event_sequence=event_sequence,
        item_id=item_id,
        policy_digest=policy_digest,
        message=message,
    )


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
        evidence_backed_facts=(),
        working_assumptions=(),
        conversation_continuity=ConversationContinuityView(items=()),
        diagnostics=(),
        built_at=built_at,
        snapshot_digest=_SNAPSHOT_DIGEST_PENDING,
    )
    digest = calculate_memory_snapshot_digest(snapshot_without_digest)
    return ConversationMemorySnapshot(
        snapshot_id=snapshot_id,
        session_id=session_id,
        cursor=cursor,
        policy_digest=policy_digest,
        pinned_state=snapshot_without_digest.pinned_state,
        evidence_backed_facts=(),
        working_assumptions=(),
        conversation_continuity=snapshot_without_digest.conversation_continuity,
        diagnostics=(),
        built_at=built_at,
        snapshot_digest=digest,
    )


def build_conversation_memory_snapshot_from_events(
    *,
    events: tuple[MemoryProjectionEvent, ...],
    session_id: str,
    consumer_id: str,
    policy: MemoryProjectionPolicy,
    built_at: str,
) -> ConversationMemorySnapshot:
    """从固定 EventLog event 集合重建 session memory snapshot。

    本函数只消费传入 events，不读取 durable store。它用于 projection rebuild
    与单元测试验证“同一 EventLog + policy”可生成稳定 snapshot digest。

    :param events: 按 EventLog sequence 升序排列的 projection events。
    :param session_id: 目标 session id。
    :param consumer_id: memory projection consumer id。
    :param policy: memory projection policy。
    :param built_at: snapshot 构建时间；不参与 digest。
    :returns: 重建后的 memory snapshot。
    :raises ValueError: 输入文本为空或事件顺序倒退时抛出。
    """

    _require_non_empty(session_id, "session_id")
    _require_non_empty(consumer_id, "consumer_id")
    _require_non_empty(built_at, "built_at")
    snapshot: ConversationMemorySnapshot | None = None
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
    previous_snapshot: ConversationMemorySnapshot | None,
    event: MemoryProjectionEvent,
    policy: MemoryProjectionPolicy,
    built_at: str,
    consumer_id: str,
) -> ConversationMemorySnapshot:
    """把单个 canonical EventLog event 投影到新的 memory snapshot。

    :param previous_snapshot: 同一 session / policy 下的既有 snapshot。
    :param event: 当前 projection event。
    :param policy: memory projection policy。
    :param built_at: 新 snapshot 构建时间；不参与 digest。
    :param consumer_id: memory projection consumer id。
    :returns: 覆盖当前 event cursor 的新 snapshot。
    :raises ValueError: snapshot 与 event / policy 不一致时抛出。
    """

    _require_non_empty(built_at, "built_at")
    _require_non_empty(consumer_id, "consumer_id")
    policy_digest = digest_memory_projection_policy(policy)
    base = _empty_or_valid_previous_snapshot(
        previous_snapshot=previous_snapshot,
        event=event,
        policy_digest=policy_digest,
        consumer_id=consumer_id,
        built_at=built_at,
    )
    pinned_state = base.pinned_state
    evidence_backed_facts = base.evidence_backed_facts
    working_assumptions = base.working_assumptions
    continuity_items = base.conversation_continuity.items
    diagnostics = base.diagnostics

    if event.event_type == _EVENT_TYPE_TOOL_RESULT_ACCEPTED:
        # Accepted tool results only carry accepted evidence envelopes. Final
        # evidence-backed facts are materialized by compacted context output in
        # a later slice, not directly from raw tool result acceptance.
        pass
    elif event.event_type == _EVENT_TYPE_USER_INPUT_ACCEPTED:
        pinned_state = _pinned_state_with_user_input(
            pinned_state,
            event,
            policy=policy,
        )
        item = _raw_user_turn_from_projection_event(event)
        continuity_items = _replace_item_by_id(continuity_items, item)
    elif event.event_type == _EVENT_TYPE_RUN_SUCCEEDED:
        item = _assistant_conclusion_from_projection_event(event, policy=policy)
        continuity_items = _replace_item_by_id(continuity_items, item)
    elif event.event_type == _EVENT_TYPE_CONTEXT_COMPACTED:
        candidate_diagnostics, fact_candidates_valid = (
            _validate_compacted_payload_for_memory_projection(
                event,
                policy_digest=policy_digest,
            )
        )
        diagnostics = diagnostics + candidate_diagnostics
        materialized_facts: tuple[EvidenceBackedFactView, ...] = ()
        if fact_candidates_valid:
            materialized_facts = _evidence_backed_facts_from_compacted_event(event)
            evidence_backed_facts, superseded_diagnostics = (
                _merge_evidence_backed_facts_by_dedupe_key(
                    existing=evidence_backed_facts,
                    candidates=materialized_facts,
                    policy_digest=policy_digest,
                )
            )
            diagnostics = diagnostics + superseded_diagnostics
        _validate_compact_summary_fact_refs(
            event,
            base.evidence_backed_facts,
            materialized_facts,
        )
        item = _compact_episode_summary_from_projection_event(event, policy=policy)
        continuity_items = _replace_item_by_id(continuity_items, item)
        for preserve_item in _minimum_preserve_items_from_compacted_event(
            event,
            policy=policy,
        ):
            continuity_items = _replace_item_by_id(
                continuity_items, preserve_item
            )
        pinned_state = _apply_pinned_state_patch_candidate(
            pinned_state,
            event,
            policy=policy,
        )
    else:
        diagnostics = diagnostics + (
            _unsupported_event_type_diagnostic(
                event,
                policy_digest=policy_digest,
            ),
        )

    limited_pinned_state = _limit_pinned_state(pinned_state, policy)
    limited_evidence_backed_facts, fact_budget_diagnostics = _limit_evidence_backed_facts(
        evidence_backed_facts,
        policy=policy,
        policy_digest=policy_digest,
        pinned_state=limited_pinned_state,
        continuity_items=continuity_items,
    )
    continuity_items, preserve_cover_diagnostics = (
        _expire_covered_minimum_preserve_items(
            continuity_items,
            evidence_backed_facts=limited_evidence_backed_facts,
            policy_digest=policy_digest,
        )
    )
    limited_assumptions, assumption_budget_diagnostics = _limit_working_assumptions(
        working_assumptions,
        policy=policy,
        policy_digest=policy_digest,
    )
    limited_continuity, continuity_budget_diagnostics = _limit_continuity_items(
        continuity_items,
        policy=policy,
        policy_digest=policy_digest,
    )
    cursor = MemorySnapshotCursor(
        consumer_id=consumer_id,
        checkpoint_event_sequence=event.event_sequence,
        checkpoint_event_id=event.event_id,
        session_id=event.session_id,
    )
    snapshot_without_digest = ConversationMemorySnapshot(
        snapshot_id=stable_memory_snapshot_id(
            session_id=event.session_id,
            consumer_id=consumer_id,
            policy_digest=policy_digest,
        ),
        session_id=event.session_id,
        cursor=cursor,
        policy_digest=policy_digest,
        pinned_state=limited_pinned_state,
        evidence_backed_facts=limited_evidence_backed_facts,
        working_assumptions=limited_assumptions,
        conversation_continuity=ConversationContinuityView(
            items=limited_continuity
        ),
        diagnostics=_dedupe_diagnostics(
            diagnostics
            + fact_budget_diagnostics
            + assumption_budget_diagnostics
            + preserve_cover_diagnostics
            + continuity_budget_diagnostics
        ),
        built_at=built_at,
        snapshot_digest=_SNAPSHOT_DIGEST_PENDING,
    )
    return ConversationMemorySnapshot(
        snapshot_id=snapshot_without_digest.snapshot_id,
        session_id=snapshot_without_digest.session_id,
        cursor=snapshot_without_digest.cursor,
        policy_digest=snapshot_without_digest.policy_digest,
        pinned_state=snapshot_without_digest.pinned_state,
        evidence_backed_facts=snapshot_without_digest.evidence_backed_facts,
        working_assumptions=snapshot_without_digest.working_assumptions,
        conversation_continuity=snapshot_without_digest.conversation_continuity,
        diagnostics=snapshot_without_digest.diagnostics,
        built_at=snapshot_without_digest.built_at,
        snapshot_digest=calculate_memory_snapshot_digest(snapshot_without_digest),
    )


def stable_memory_snapshot_id(
    *,
    session_id: str,
    consumer_id: str,
    policy_digest: MemoryPolicyDigest,
) -> str:
    """派生稳定 memory snapshot id。

    :param session_id: Session id。
    :param consumer_id: memory projection consumer id。
    :param policy_digest: memory policy digest。
    :returns: 稳定 snapshot id。
    :raises ValueError: 任一文本为空时抛出。
    """

    _require_non_empty(session_id, "session_id")
    _require_non_empty(consumer_id, "consumer_id")
    _require_non_empty(policy_digest, "policy_digest")
    digest = sha256_digest_json(
        {
            "consumer_id": consumer_id,
            "policy_digest": policy_digest,
            "session_id": session_id,
        }
    ).removeprefix("sha256:")
    return f"{_SNAPSHOT_ID_DIGEST_PREFIX}{digest}"


def _empty_or_valid_previous_snapshot(
    *,
    previous_snapshot: ConversationMemorySnapshot | None,
    event: MemoryProjectionEvent,
    policy_digest: MemoryPolicyDigest,
    consumer_id: str,
    built_at: str,
) -> ConversationMemorySnapshot:
    """读取既有 snapshot 或构造同 policy 空 snapshot。

    :param previous_snapshot: 既有 snapshot 或 ``None``。
    :param event: 当前 projection event。
    :param policy_digest: 当前 policy digest。
    :param consumer_id: memory consumer id。
    :param built_at: 空 snapshot 构建时间。
    :returns: 可作为本次投影基础的 snapshot。
    :raises ValueError: 既有 snapshot 与当前 event / policy 不一致时抛出。
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


def _validate_compacted_payload_for_memory_projection(
    event: MemoryProjectionEvent, *, policy_digest: MemoryPolicyDigest
) -> tuple[tuple[MemoryDiagnostic, ...], bool]:
    """校验 compact payload，并把 fact candidate 局部错误降级为 diagnostic。

    :param event: CONTEXT_COMPACTED projection event。
    :param policy_digest: 当前 policy digest。
    :returns: diagnostic tuple 与 fact candidate 是否可物化。
    :raises ValueError: 非 fact candidate 字段不满足 accepted compact payload contract 时抛出。
    """

    try:
        _validate_memory_projection_compacted_payload(event, validate_facts=True)
        return (), True
    except ValueError as exc:
        patched_payload = dict(event.payload)
        patched_payload[_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_CANDIDATES] = []
        patched_event = MemoryProjectionEvent(
            event_sequence=event.event_sequence,
            event_id=event.event_id,
            event_class=event.event_class,
            event_type=event.event_type,
            occurred_at=event.occurred_at,
            session_id=event.session_id,
            run_id=event.run_id,
            attempt_id=event.attempt_id,
            execution_id=event.execution_id,
            payload_ref=event.payload_ref,
            payload_digest=event.payload_digest,
            payload=patched_payload,
        )
        try:
            _validate_memory_projection_compacted_payload(
                patched_event,
                validate_facts=False,
            )
        except ValueError as non_fact_exc:
            raise non_fact_exc from exc
        item_id = _item_id(event, "evidence_backed_fact_candidates")
        return (
            (
                MemoryDiagnostic(
                    diagnostic_id=_diagnostic_id(
                        MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID,
                        event_sequence=event.event_sequence,
                        item_id=item_id,
                    ),
                    reason=(
                        MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_CANDIDATE_INVALID
                    ),
                    message=(
                        "evidence-backed fact candidates invalid; "
                        f"no facts materialized: {exc}"
                    ),
                    event_sequence=event.event_sequence,
                    item_id=item_id,
                    policy_digest=policy_digest,
                    recorded_at=None,
                ),
            ),
            False,
        )


def _validate_memory_projection_compacted_payload(
    event: MemoryProjectionEvent, *, validate_facts: bool
) -> None:
    """校验 memory projection 自有 compacted payload shape。

    :param event: CONTEXT_COMPACTED projection event。
    :param validate_facts: 是否校验并物化 fact candidates。
    :returns: ``None``。
    :raises ValueError: payload shape 非法时抛出。
    """

    payload = event.payload
    if _is_vnext_compacted_payload(payload):
        _validate_memory_projection_vnext_compacted_payload(payload)
        return
    _required_payload_mapping(payload, _PAYLOAD_FIELD_EPISODE_SUMMARY_CANDIDATE)
    _required_payload_mapping(payload, _PAYLOAD_FIELD_PINNED_STATE_PATCH_CANDIDATE)
    _validate_memory_projection_minimum_preserve_candidates(payload)
    _validate_memory_projection_quality_result(payload)
    _validate_memory_projection_preserved_refs(payload)
    if validate_facts:
        _validate_memory_projection_fact_candidates(event)


def _is_vnext_compacted_payload(payload: Mapping[str, JsonValue]) -> bool:
    """判断 payload 是否为 vNext compacted event payload。

    :param payload: CONTEXT_COMPACTED payload。
    :returns: 包含 accepted_candidate 字段时返回 ``True``。
    """

    return _PAYLOAD_FIELD_ACCEPTED_CANDIDATE in payload


def _validate_memory_projection_vnext_compacted_payload(
    payload: Mapping[str, JsonValue],
) -> None:
    """校验 memory projection 可消费的 vNext compacted payload shape。

    :param payload: CONTEXT_COMPACTED payload。
    :returns: ``None``。
    :raises ValueError: vNext payload shape 非法时抛出。
    """

    candidate = _required_payload_mapping(payload, _PAYLOAD_FIELD_ACCEPTED_CANDIDATE)
    if _required_str(candidate, _PAYLOAD_FIELD_SCHEMA_VERSION) != "conversation_compact_output_v1":
        raise ValueError("accepted candidate schema_version is invalid")
    summary = _required_value(candidate, _PAYLOAD_FIELD_SESSION_SUMMARY)
    if summary is not None:
        summary_mapping = _as_mapping(summary, _PAYLOAD_FIELD_SESSION_SUMMARY)
        _required_str(summary_mapping, _PAYLOAD_FIELD_SUMMARY_TEXT)
        _required_text_tuple(summary_mapping, _PAYLOAD_FIELD_SOURCE_LABELS)
    for fact in _required_mapping_list(candidate, _PAYLOAD_FIELD_EVIDENCE_BACKED_FACTS):
        _required_str(fact, _PAYLOAD_FIELD_CLAIM_TEXT)
        _required_text_tuple(fact, _PAYLOAD_FIELD_EVIDENCE_LABELS)
    for item in _required_mapping_list(
        candidate,
        _PAYLOAD_FIELD_REFERENCE_CONTINUITY_ITEMS,
    ):
        _required_str(item, _PAYLOAD_FIELD_TEXT)
        _required_str(item, _PAYLOAD_FIELD_REASON)
        _required_text_tuple(item, _PAYLOAD_FIELD_SOURCE_LABELS)
    _required_text_tuple(payload, _PAYLOAD_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS)


def _vnext_session_summary_mapping(
    payload: Mapping[str, JsonValue],
) -> Mapping[str, JsonValue] | None:
    """读取 vNext accepted candidate 的 session summary。

    :param payload: CONTEXT_COMPACTED payload。
    :returns: session summary mapping；candidate 未提供 summary 时返回 ``None``。
    :raises ValueError: vNext candidate 或 summary 结构非法时抛出。
    """

    candidate = _required_payload_mapping(payload, _PAYLOAD_FIELD_ACCEPTED_CANDIDATE)
    summary = _required_value(candidate, _PAYLOAD_FIELD_SESSION_SUMMARY)
    if summary is None:
        return None
    return _as_mapping(summary, _PAYLOAD_FIELD_SESSION_SUMMARY)


def _validate_memory_projection_quality_result(
    payload: Mapping[str, JsonValue],
) -> None:
    """校验 memory projection compact quality result 基本 shape。

    :param payload: CONTEXT_COMPACTED payload。
    :returns: ``None``。
    :raises ValueError: quality result 缺失或未 accepted 时抛出。
    """

    quality = _required_payload_mapping(payload, _PAYLOAD_FIELD_QUALITY_CHECK_RESULT)
    accepted = _required_value(quality, "accepted")
    if accepted is not True:
        raise ValueError("compact quality result must be accepted")


def _validate_memory_projection_minimum_preserve_candidates(
    payload: Mapping[str, JsonValue],
) -> None:
    """校验 memory projection minimum preserve candidates。

    :param payload: CONTEXT_COMPACTED payload。
    :returns: ``None``。
    :raises ValueError: candidate 字段非法时抛出。
    """

    for candidate in _required_mapping_list(
        payload,
        _PAYLOAD_FIELD_MINIMUM_PRESERVE_ITEM_CANDIDATES,
    ):
        text = _required_str(candidate, _PAYLOAD_FIELD_TEXT)
        if len(text) > MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS:
            raise ValueError("minimum preserve text exceeds maximum length")
        MemoryContinuityPreserveReason(
            _required_str(candidate, _PAYLOAD_FIELD_PRESERVE_REASON)
        )


def _validate_memory_projection_preserved_refs(
    payload: Mapping[str, JsonValue],
) -> None:
    """校验 memory projection compact preserved refs 基本 shape。

    :param payload: CONTEXT_COMPACTED payload。
    :returns: ``None``。
    :raises ValueError: preserved refs 缺失或结构非法时抛出。
    """

    preserved = _required_payload_mapping(payload, _PAYLOAD_FIELD_PRESERVED_FACT_REFS)
    _required_text_tuple(preserved, _PAYLOAD_FIELD_CANONICAL_EVIDENCE_REFS)
    _required_text_tuple(preserved, _PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_REFS)


def _validate_memory_projection_fact_candidates(event: MemoryProjectionEvent) -> None:
    """校验 memory projection compact fact candidates。

    :param event: CONTEXT_COMPACTED projection event。
    :returns: ``None``。
    :raises ValueError: fact candidate 非法时抛出。
    """

    retained_refs = set(_memory_projection_retained_evidence_refs(event.payload))
    for fact in _evidence_backed_facts_from_compacted_event(event):
        for evidence_ref in fact.evidence_refs:
            if evidence_ref not in retained_refs:
                raise ValueError("evidence ref is not retained by compact payload")


def _memory_projection_retained_evidence_refs(
    payload: Mapping[str, JsonValue],
) -> tuple[str, ...]:
    """读取 memory projection compact payload 中保留的 evidence refs。

    :param payload: CONTEXT_COMPACTED payload。
    :returns: canonical evidence refs。
    :raises ValueError: preserved refs 结构非法时抛出。
    """

    preserved = _required_payload_mapping(payload, _PAYLOAD_FIELD_PRESERVED_FACT_REFS)
    return _required_text_tuple(preserved, _PAYLOAD_FIELD_CANONICAL_EVIDENCE_REFS)


def _evidence_backed_facts_from_compacted_event(
    event: MemoryProjectionEvent,
) -> tuple[EvidenceBackedFactView, ...]:
    """从 accepted ``CONTEXT_COMPACTED`` fact candidates 物化 stable facts。

    :param event: CONTEXT_COMPACTED projection event。
    :returns: evidence-backed facts。
    :raises ValueError: candidate JSON 结构非法时抛出。
    """

    payload_ref, payload_digest = _payload_ref_pair_from_event(event)
    provenance = MemoryProvenanceRef(
        producer_kind=MemoryProducerKind.HOST_PROJECTION,
        producer_name=_PRODUCER_NAME_HOST_PROJECTION,
        event_id=event.event_id,
        event_sequence=event.event_sequence,
        run_id=event.run_id,
        attempt_id=event.attempt_id,
        execution_id=event.execution_id,
        tool_result_ref=None,
        payload_ref=payload_ref,
        digest_ref=_compact_event_digest_ref(event, payload_digest=payload_digest),
        source_refs=(),
    )
    compact_artifact_ref = _optional_payload_str(
        event.payload,
        _PAYLOAD_FIELD_COMPACT_ARTIFACT_REF,
    )
    if _is_vnext_compacted_payload(event.payload):
        return _vnext_evidence_backed_facts_from_compacted_event(
            event,
            provenance=provenance,
            compact_artifact_ref=compact_artifact_ref,
        )
    facts: list[EvidenceBackedFactView] = []
    for candidate in _required_mapping_list(
        event.payload,
        _PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_CANDIDATES,
    ):
        candidate_id = _required_str(candidate, _PAYLOAD_FIELD_CANDIDATE_ID)
        claim_text = _required_str(candidate, _PAYLOAD_FIELD_CLAIM_TEXT)
        evidence_kind = MemoryEvidenceBackedFactKind(
            _required_str(candidate, _PAYLOAD_FIELD_EVIDENCE_KIND)
        )
        evidence_refs = tuple(
            _as_str(item, _PAYLOAD_FIELD_EVIDENCE_REFS)
            for item in _required_list(
                candidate,
                _PAYLOAD_FIELD_EVIDENCE_REFS,
            )
        )
        attributes = _as_mapping(
            _required_value(candidate, _PAYLOAD_FIELD_ATTRIBUTES),
            _PAYLOAD_FIELD_ATTRIBUTES,
        )
        facts.append(
            EvidenceBackedFactView(
                item_id=_item_id(
                    event,
                    f"evidence_backed_fact:{candidate_id}",
                ),
                claim_text=claim_text,
                evidence_kind=evidence_kind,
                evidence_refs=evidence_refs,
                attributes=attributes,
                provenance=provenance,
                extraction_operation_ref=f"{_EVENT_REF_PREFIX}{event.event_id}",
                compact_artifact_ref=compact_artifact_ref,
                candidate_id=candidate_id,
                included_reason=MemoryIncludedReason.EVIDENCE_BACKED_FACT,
                excluded_reason=None,
                size_units=estimate_memory_size_units(claim_text),
            )
        )
    return tuple(facts)


def _vnext_evidence_backed_facts_from_compacted_event(
    event: MemoryProjectionEvent,
    *,
    provenance: MemoryProvenanceRef,
    compact_artifact_ref: str | None,
) -> tuple[EvidenceBackedFactView, ...]:
    """从 vNext compacted payload 物化 evidence-backed facts。

    :param event: CONTEXT_COMPACTED projection event。
    :param provenance: 当前 compact event provenance。
    :param compact_artifact_ref: 可选 compact artifact ref。
    :returns: evidence-backed facts。
    :raises ValueError: vNext fact candidate 结构非法时抛出。
    """

    candidate = _required_payload_mapping(event.payload, _PAYLOAD_FIELD_ACCEPTED_CANDIDATE)
    evidence_refs = _required_text_tuple(
        event.payload,
        _PAYLOAD_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS,
    )
    facts: list[EvidenceBackedFactView] = []
    for index, fact in enumerate(
        _required_mapping_list(candidate, _PAYLOAD_FIELD_EVIDENCE_BACKED_FACTS)
    ):
        claim_text = _required_str(fact, _PAYLOAD_FIELD_CLAIM_TEXT)
        candidate_id = f"vnext-fact-{index + 1}"
        facts.append(
            EvidenceBackedFactView(
                item_id=_item_id(
                    event,
                    f"evidence_backed_fact:{candidate_id}",
                ),
                claim_text=claim_text,
                evidence_kind=MemoryEvidenceBackedFactKind.DERIVED_FROM_EVIDENCE,
                evidence_refs=evidence_refs,
                attributes={},
                provenance=provenance,
                extraction_operation_ref=f"{_EVENT_REF_PREFIX}{event.event_id}",
                compact_artifact_ref=compact_artifact_ref,
                candidate_id=candidate_id,
                included_reason=MemoryIncludedReason.EVIDENCE_BACKED_FACT,
                excluded_reason=None,
                size_units=estimate_memory_size_units(claim_text),
            )
        )
    return tuple(facts)


def _merge_evidence_backed_facts_by_dedupe_key(
    *,
    existing: tuple[EvidenceBackedFactView, ...],
    candidates: tuple[EvidenceBackedFactView, ...],
    policy_digest: MemoryPolicyDigest,
) -> tuple[tuple[EvidenceBackedFactView, ...], tuple[MemoryDiagnostic, ...]]:
    """按 claim / evidence / kind 合并 compact fact candidates。

    :param existing: snapshot 中已有 evidence-backed facts。
    :param candidates: 当前 compact event 新物化的 fact candidates。
    :param policy_digest: 当前 memory policy digest。
    :returns: 合并后的 facts 与 superseded diagnostics。
    """

    facts = list(existing)
    diagnostics: list[MemoryDiagnostic] = []
    for candidate in candidates:
        duplicate_index = _evidence_backed_fact_duplicate_index(facts, candidate)
        if duplicate_index is None:
            facts.append(candidate)
            continue
        current = facts[duplicate_index]
        if _is_newer_or_equal_extraction(candidate, current):
            facts[duplicate_index] = candidate
            diagnostics.append(
                _superseded_fact_diagnostic(
                    superseded=current,
                    superseding=candidate,
                    policy_digest=policy_digest,
                )
            )
            continue
        diagnostics.append(
            _superseded_fact_diagnostic(
                superseded=candidate,
                superseding=current,
                policy_digest=policy_digest,
            )
        )
    return tuple(facts), tuple(diagnostics)


def _evidence_backed_fact_duplicate_index(
    facts: list[EvidenceBackedFactView], candidate: EvidenceBackedFactView
) -> int | None:
    """查找 evidence-backed fact dedupe key 相同的现有下标。

    :param facts: 已选择的 facts。
    :param candidate: 待查找的 candidate。
    :returns: duplicate 下标；不存在时返回 ``None``。
    """

    candidate_key = _evidence_backed_fact_dedupe_key(candidate)
    for index, fact in enumerate(facts):
        if _evidence_backed_fact_dedupe_key(fact) == candidate_key:
            return index
    return None


def _evidence_backed_fact_dedupe_key(
    fact: EvidenceBackedFactView,
) -> tuple[str, tuple[str, ...], MemoryEvidenceBackedFactKind]:
    """生成 evidence-backed fact 去重 key。

    :param fact: evidence-backed fact。
    :returns: normalized claim、排序后 evidence refs 与 evidence kind。
    """

    return (
        _normalized_text(fact.claim_text),
        tuple(sorted(fact.evidence_refs)),
        fact.evidence_kind,
    )


def _is_newer_or_equal_extraction(
    candidate: EvidenceBackedFactView, current: EvidenceBackedFactView
) -> bool:
    """判断 candidate 是否来自不早于 current 的 extraction event。

    :param candidate: 新 candidate。
    :param current: 已存在 fact。
    :returns: candidate event sequence 不早于 current 时返回 ``True``。
    """

    if candidate.provenance.event_sequence != current.provenance.event_sequence:
        return candidate.provenance.event_sequence > current.provenance.event_sequence
    return candidate.item_id >= current.item_id


def _superseded_fact_diagnostic(
    *,
    superseded: EvidenceBackedFactView,
    superseding: EvidenceBackedFactView,
    policy_digest: MemoryPolicyDigest,
) -> MemoryDiagnostic:
    """构造 duplicate fact 被 supersede 的 diagnostic。

    :param superseded: 被替换或被拒绝的 duplicate fact。
    :param superseding: 保留下来的 fact。
    :param policy_digest: 当前 memory policy digest。
    :returns: memory diagnostic。
    """

    return MemoryDiagnostic(
        diagnostic_id=_diagnostic_id(
            MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_SUPERSEDED,
            event_sequence=superseding.provenance.event_sequence,
            item_id=superseded.item_id,
        ),
        reason=MemoryDiagnosticReason.EVIDENCE_BACKED_FACT_SUPERSEDED,
        message=(
            "evidence-backed fact superseded by duplicate dedupe key: "
            f"superseding_item_id={superseding.item_id}"
        ),
        event_sequence=superseding.provenance.event_sequence,
        item_id=superseded.item_id,
        policy_digest=policy_digest,
        recorded_at=None,
    )


def _minimum_preserve_items_from_compacted_event(
    event: MemoryProjectionEvent, *, policy: MemoryProjectionPolicy
) -> tuple[ConversationContinuityItem, ...]:
    """从 accepted ``CONTEXT_COMPACTED`` minimum preserve candidates 物化 continuity。

    :param event: CONTEXT_COMPACTED projection event。
    :param policy: memory projection policy。
    :returns: minimum preserve continuity items。
    :raises ValueError: candidate JSON 结构非法时抛出。
    """

    if _is_vnext_compacted_payload(event.payload):
        return _vnext_reference_continuity_items_from_compacted_event(
            event,
            policy=policy,
        )
    items: list[ConversationContinuityItem] = []
    for candidate in _required_mapping_list(
        event.payload,
        _PAYLOAD_FIELD_MINIMUM_PRESERVE_ITEM_CANDIDATES,
    ):
        item_id = _required_str(candidate, _PAYLOAD_FIELD_ITEM_ID)
        label = _required_str(candidate, _PAYLOAD_FIELD_LABEL)
        candidate_text = _required_str(candidate, _PAYLOAD_FIELD_TEXT)
        source_refs = tuple(
            _as_str(item, _PAYLOAD_FIELD_SOURCE_REFS)
            for item in _required_list(candidate, _PAYLOAD_FIELD_SOURCE_REFS)
        )
        preserve_reason = MemoryContinuityPreserveReason(
            _required_str(candidate, _PAYLOAD_FIELD_PRESERVE_REASON)
        )
        text = _bounded_patch_text(
            candidate_text,
            event=event,
            policy=policy,
        )
        items.append(
            ConversationContinuityItem(
                item_id=_item_id(
                    event,
                    f"minimum_preserve_item:{item_id}",
                ),
                item_kind=ConversationContinuityKind.MINIMUM_PRESERVE_ITEM,
                producer_kind=MemoryProducerKind.HOST_PROJECTION,
                claim_status=MemoryClaimStatus.ASSUMPTION,
                event_id=event.event_id,
                event_sequence=event.event_sequence,
                run_id=event.run_id,
                summary_text=text,
                label=label,
                source_refs=source_refs,
                preserve_reason=preserve_reason,
                payload_ref=None,
                payload_digest=None,
                included_reason=MemoryIncludedReason.MINIMUM_PRESERVE_ITEM,
                excluded_reason=None,
                size_units=estimate_memory_size_units(text),
            )
        )
    return tuple(items)


def _vnext_reference_continuity_items_from_compacted_event(
    event: MemoryProjectionEvent, *, policy: MemoryProjectionPolicy
) -> tuple[ConversationContinuityItem, ...]:
    """从 vNext compacted payload 物化 reference continuity items。

    :param event: CONTEXT_COMPACTED projection event。
    :param policy: memory projection policy。
    :returns: continuity items。
    :raises ValueError: vNext reference item 结构非法时抛出。
    """

    candidate = _required_payload_mapping(event.payload, _PAYLOAD_FIELD_ACCEPTED_CANDIDATE)
    items: list[ConversationContinuityItem] = []
    for index, item in enumerate(
        _required_mapping_list(candidate, _PAYLOAD_FIELD_REFERENCE_CONTINUITY_ITEMS)
    ):
        text = _bounded_patch_text(
            _required_str(item, _PAYLOAD_FIELD_TEXT),
            event=event,
            policy=policy,
        )
        items.append(
            ConversationContinuityItem(
                item_id=_item_id(event, f"vnext_reference_continuity:{index + 1}"),
                item_kind=ConversationContinuityKind.MINIMUM_PRESERVE_ITEM,
                producer_kind=MemoryProducerKind.HOST_PROJECTION,
                claim_status=MemoryClaimStatus.ASSUMPTION,
                event_id=event.event_id,
                event_sequence=event.event_sequence,
                run_id=event.run_id,
                summary_text=text,
                label="reference_continuity",
                source_refs=_required_text_tuple(item, _PAYLOAD_FIELD_SOURCE_LABELS),
                preserve_reason=MemoryContinuityPreserveReason.NEEDED_FOR_LOCAL_FOLLOWUP,
                payload_ref=None,
                payload_digest=None,
                included_reason=MemoryIncludedReason.MINIMUM_PRESERVE_ITEM,
                excluded_reason=None,
                size_units=estimate_memory_size_units(text),
            )
        )
    return tuple(items)


def _compact_event_digest_ref(
    event: MemoryProjectionEvent, *, payload_digest: str | None
) -> MemoryDigestRef:
    """选择 compact extraction provenance digest ref。

    :param event: CONTEXT_COMPACTED projection event。
    :param payload_digest: 已解析 payload digest。
    :returns: 非空 digest ref。
    """

    if event.payload_digest is not None:
        return event.payload_digest
    if payload_digest is not None:
        return payload_digest
    return sha256_digest_json(event.payload)


def _raw_user_turn_from_projection_event(
    event: MemoryProjectionEvent,
) -> ConversationContinuityItem:
    """从 ``USER_INPUT_ACCEPTED`` event 构造 raw user continuity item。

    :param event: USER_INPUT_ACCEPTED projection event。
    :returns: raw user turn item。
    """

    summary_text = _user_visible_text(event)
    return ConversationContinuityItem(
        item_id=_item_id(event, "raw_user_turn"),
        item_kind=ConversationContinuityKind.RAW_USER_TURN,
        producer_kind=MemoryProducerKind.USER,
        claim_status=MemoryClaimStatus.ASSUMPTION,
        event_id=event.event_id,
        event_sequence=event.event_sequence,
        run_id=event.run_id,
        summary_text=summary_text,
        label=None,
        source_refs=(),
        preserve_reason=None,
        payload_ref=None,
        payload_digest=None,
        included_reason=MemoryIncludedReason.RECENT_RAW_TURN,
        excluded_reason=None,
        size_units=estimate_memory_size_units(summary_text),
    )


def _assistant_conclusion_from_projection_event(
    event: MemoryProjectionEvent, *, policy: MemoryProjectionPolicy
) -> ConversationContinuityItem:
    """从 ``RUN_SUCCEEDED`` event 构造 assistant conclusion continuity item。

    :param event: RUN_SUCCEEDED projection event。
    :param policy: memory projection policy。
    :returns: assistant conclusion item。
    """

    payload_ref, payload_digest = _payload_ref_pair_from_event(event)
    final_answer = assistant_summary_from_payload(
        event.payload,
        text_policy=PayloadSummaryTextPolicy.LENIENT_NON_EMPTY,
    )
    summary_text = _bounded_summary_text(
        final_answer,
        max_size_units=policy.max_raw_turn_size_units,
        prefer_ref=payload_ref is not None,
    )
    size_text = summary_text if summary_text is not None else _ref_summary_text(
        payload_ref=payload_ref,
        payload_digest=payload_digest,
        fallback_event_id=event.event_id,
    )
    return ConversationContinuityItem(
        item_id=_item_id(event, "assistant_conclusion"),
        item_kind=ConversationContinuityKind.ASSISTANT_CONCLUSION,
        producer_kind=MemoryProducerKind.ASSISTANT,
        claim_status=MemoryClaimStatus.ASSUMPTION,
        event_id=event.event_id,
        event_sequence=event.event_sequence,
        run_id=event.run_id,
        summary_text=summary_text,
        label=None,
        source_refs=(),
        preserve_reason=None,
        payload_ref=payload_ref,
        payload_digest=payload_digest,
        included_reason=MemoryIncludedReason.RECENT_RAW_TURN,
        excluded_reason=None,
        size_units=estimate_memory_size_units(size_text),
    )


def _compact_episode_summary_from_projection_event(
    event: MemoryProjectionEvent, *, policy: MemoryProjectionPolicy
) -> ConversationContinuityItem:
    """从 ``CONTEXT_COMPACTED`` event 构造 continuity navigation item。

    :param event: CONTEXT_COMPACTED projection event。
    :param policy: memory projection policy。
    :returns: episode summary item。
    """

    summary_text = _bounded_summary_text(
        _compact_episode_summary_text(event),
        max_size_units=policy.max_raw_turn_size_units,
        prefer_ref=False,
    )
    if summary_text is None:
        summary_text = _ref_summary_text(
            payload_ref=event.payload_ref,
            payload_digest=event.payload_digest,
            fallback_event_id=event.event_id,
        )
    return ConversationContinuityItem(
        item_id=_item_id(event, "episode_summary"),
        item_kind=ConversationContinuityKind.EPISODE_SUMMARY,
        producer_kind=MemoryProducerKind.HOST_PROJECTION,
        claim_status=MemoryClaimStatus.ASSUMPTION,
        event_id=event.event_id,
        event_sequence=event.event_sequence,
        run_id=event.run_id,
        summary_text=summary_text,
        label=None,
        source_refs=_compact_episode_summary_source_refs(event),
        preserve_reason=None,
        payload_ref=None,
        payload_digest=None,
        included_reason=MemoryIncludedReason.EPISODE_SUMMARY,
        excluded_reason=None,
        size_units=estimate_memory_size_units(summary_text),
    )


def _compact_episode_summary_source_refs(
    event: MemoryProjectionEvent,
) -> tuple[str, ...]:
    """读取 episode summary 可覆盖的 canonical source refs。

    :param event: CONTEXT_COMPACTED projection event。
    :returns: 去重后的 source refs。
    """

    if _is_vnext_compacted_payload(event.payload):
        summary = _vnext_session_summary_mapping(event.payload)
        if summary is None:
            return ()
        return _required_text_tuple(summary, _PAYLOAD_FIELD_SOURCE_LABELS)
    summary = _required_payload_mapping(
        event.payload,
        _PAYLOAD_FIELD_EPISODE_SUMMARY_CANDIDATE,
    )
    return _dedupe_text_tuple(
        _optional_text_tuple(summary, _PAYLOAD_FIELD_SOURCE_EVENT_REFS)
        + _optional_text_tuple(summary, _PAYLOAD_FIELD_EVIDENCE_REFS)
        + _optional_text_tuple(summary, _PAYLOAD_FIELD_CONFIRMED_FACT_REFS)
    )


def _apply_pinned_state_patch_candidate(
    pinned_state: PinnedStateView,
    event: MemoryProjectionEvent,
    *,
    policy: MemoryProjectionPolicy,
) -> PinnedStateView:
    """应用 ``CONTEXT_COMPACTED`` accepted pinned state patch candidate。

    :param pinned_state: 既有 pinned state。
    :param event: CONTEXT_COMPACTED projection event。
    :param policy: memory projection policy。
    :returns: 应用字段级三态 patch 后的 pinned state。
    :raises ValueError: patch JSON 结构或 confirmed subjects ref 非法时抛出。
    """

    if _is_vnext_compacted_payload(event.payload):
        return pinned_state
    patch = _required_payload_mapping(
        event.payload,
        _PAYLOAD_FIELD_PINNED_STATE_PATCH_CANDIDATE,
    )
    return PinnedStateView(
        current_goal=_patched_text_field(
            patch,
            _PAYLOAD_FIELD_CURRENT_GOAL,
            current_value=pinned_state.current_goal,
            event=event,
            policy=policy,
        ),
        confirmed_subjects=_patched_confirmed_subjects(
            patch,
            current_value=pinned_state.confirmed_subjects,
        ),
        user_constraints=_patched_text_tuple_field(
            patch,
            _PAYLOAD_FIELD_USER_CONSTRAINTS,
            current_value=pinned_state.user_constraints,
            event=event,
            policy=policy,
        ),
        open_questions=_patched_text_tuple_field(
            patch,
            _PAYLOAD_FIELD_OPEN_QUESTIONS,
            current_value=pinned_state.open_questions,
            event=event,
            policy=policy,
        ),
    )


def _patched_text_field(
    patch: Mapping[str, JsonValue],
    field_name: str,
    *,
    current_value: str | None,
    event: MemoryProjectionEvent,
    policy: MemoryProjectionPolicy,
) -> str | None:
    """按三态语义应用 pinned text patch 字段。

    :param patch: pinned patch candidate JSON object。
    :param field_name: 字段名。
    :param current_value: 既有字段值。
    :param event: CONTEXT_COMPACTED projection event。
    :param policy: memory projection policy。
    :returns: 更新后的字段值。
    :raises ValueError: patch 字段类型非法时抛出。
    """

    if field_name not in patch:
        return current_value
    value = patch[field_name]
    if value is None:
        return None
    if isinstance(value, str):
        return _bounded_patch_text(value, event=event, policy=policy)
    mapping = _as_mapping(value, field_name)
    operation = _patch_operation(mapping)
    if operation == "missing":
        return current_value
    if operation == "clear":
        return None
    if operation == "replace":
        return _bounded_patch_text(
            _required_str(mapping, _PAYLOAD_FIELD_VALUE),
            event=event,
            policy=policy,
        )
    raise ValueError(f"{field_name} operation is invalid")


def _patched_text_tuple_field(
    patch: Mapping[str, JsonValue],
    field_name: str,
    *,
    current_value: tuple[str, ...],
    event: MemoryProjectionEvent,
    policy: MemoryProjectionPolicy,
) -> tuple[str, ...]:
    """按三态语义应用 pinned 文本 tuple patch 字段。

    :param patch: pinned patch candidate JSON object。
    :param field_name: 字段名。
    :param current_value: 既有字段值。
    :param event: CONTEXT_COMPACTED projection event。
    :param policy: memory projection policy。
    :returns: 更新后的字段值。
    :raises ValueError: patch 字段类型非法时抛出。
    """

    if field_name not in patch:
        return current_value
    value = patch[field_name]
    if value is None:
        return ()
    if isinstance(value, list):
        return _bounded_patch_text_tuple(value, event=event, policy=policy)
    mapping = _as_mapping(value, field_name)
    operation = _patch_operation(mapping)
    if operation == "missing":
        return current_value
    if operation == "clear":
        return ()
    if operation == "replace":
        return _bounded_patch_text_tuple(
            _required_list(mapping, _PAYLOAD_FIELD_VALUE),
            event=event,
            policy=policy,
        )
    raise ValueError(f"{field_name} operation is invalid")


def _patched_confirmed_subjects(
    patch: Mapping[str, JsonValue],
    *,
    current_value: tuple[OpaqueMemoryRef, ...],
) -> tuple[OpaqueMemoryRef, ...]:
    """按三态语义应用 confirmed subjects patch 字段。

    :param patch: pinned patch candidate JSON object。
    :param current_value: 既有 confirmed subjects。
    :returns: 更新后的 confirmed subjects。
    :raises ValueError: patch 值不是 Host-neutral opaque ref 时抛出。
    """

    field_name = _PAYLOAD_FIELD_CONFIRMED_SUBJECTS
    if field_name not in patch:
        return current_value
    value = patch[field_name]
    if value is None:
        return ()
    if isinstance(value, list):
        return _opaque_ref_tuple_from_patch_values(value)
    mapping = _as_mapping(value, field_name)
    operation = _patch_operation(mapping)
    if operation == "missing":
        return current_value
    if operation == "clear":
        return ()
    if operation == "replace":
        return _opaque_ref_tuple_from_patch_values(
            _required_list(mapping, _PAYLOAD_FIELD_VALUE)
        )
    raise ValueError("confirmed_subjects operation is invalid")


def _patch_operation(mapping: Mapping[str, JsonValue]) -> str:
    """读取 patch operation。

    :param mapping: patch field JSON object。
    :returns: operation 文本。
    :raises ValueError: operation 不是三态枚举值时抛出。
    """

    operation = _required_str(mapping, _PAYLOAD_FIELD_OPERATION)
    if operation not in {"missing", "clear", "replace"}:
        raise ValueError("patch operation is invalid")
    return operation


def _bounded_patch_text(
    text: str,
    *,
    event: MemoryProjectionEvent,
    policy: MemoryProjectionPolicy,
) -> str:
    """按 memory policy 限制 compact patch 文本。

    :param text: patch 文本。
    :param event: CONTEXT_COMPACTED projection event。
    :param policy: memory projection policy。
    :returns: 原文本或中立 event ref fallback。
    """

    bounded = _bounded_summary_text(
        text,
        max_size_units=policy.max_raw_turn_size_units,
        prefer_ref=False,
    )
    if bounded is not None:
        return bounded
    return _ref_summary_text(
        payload_ref=event.payload_ref,
        payload_digest=event.payload_digest,
        fallback_event_id=event.event_id,
    )


def _bounded_patch_text_tuple(
    values: list[JsonValue],
    *,
    event: MemoryProjectionEvent,
    policy: MemoryProjectionPolicy,
) -> tuple[str, ...]:
    """按 memory policy 限制 compact patch 文本 tuple。

    :param values: patch JSON array。
    :param event: CONTEXT_COMPACTED projection event。
    :param policy: memory projection policy。
    :returns: bounded 文本 tuple。
    :raises ValueError: 元素不是非空文本时抛出。
    """

    result: list[str] = []
    for value in values:
        result.append(
            _bounded_patch_text(
                _as_str(value, "pinned patch item"),
                event=event,
                policy=policy,
            )
        )
    return tuple(result)


def _opaque_ref_tuple_from_patch_values(
    values: list[JsonValue],
) -> tuple[OpaqueMemoryRef, ...]:
    """从 patch JSON array 解析 Host-neutral opaque refs。

    :param values: confirmed subjects patch value。
    :returns: opaque refs。
    :raises ValueError: 任一元素不是合法 opaque ref 时抛出。
    """

    refs: list[OpaqueMemoryRef] = []
    for value in values:
        refs.append(_opaque_ref_from_patch_value(value))
    return tuple(refs)


def _opaque_ref_from_patch_value(value: JsonValue) -> OpaqueMemoryRef:
    """从 JSON 值解析 confirmed subject opaque ref。

    :param value: JSON ref 值。
    :returns: opaque memory ref。
    :raises ValueError: 值为自由业务字符串或 ref 结构非法时抛出。
    """

    if isinstance(value, Mapping):
        return _opaque_ref_from_patch_mapping(value)
    if isinstance(value, str):
        return _opaque_ref_from_text(value)
    raise ValueError("confirmed subject ref must be opaque ref")


def _opaque_ref_from_patch_mapping(
    value: Mapping[str, JsonValue],
) -> OpaqueMemoryRef:
    """从 compact patch mapping 解析 Host-neutral opaque ref。

    :param value: opaque ref JSON object。
    :returns: opaque memory ref。
    :raises ValueError: ref kind、ref id 或 digest 非法时抛出。
    """

    return OpaqueMemoryRef(
        ref_kind=HostNeutralRefKind(_required_str(value, _PAYLOAD_FIELD_REF_KIND)),
        ref_id=_required_str(value, _PAYLOAD_FIELD_REF_ID),
        digest=_optional_patch_str(value, _PAYLOAD_FIELD_DIGEST),
    )


def _opaque_ref_from_text(value: str) -> OpaqueMemoryRef:
    """解析 ``kind:ref_id`` 形式的 Host-neutral opaque ref。

    :param value: opaque ref 文本。
    :returns: opaque memory ref。
    :raises ValueError: 文本缺少 ref kind 或 ref id 时抛出。
    """

    _require_non_empty(value, "confirmed_subjects")
    if ":" not in value:
        raise ValueError("confirmed subject ref must include Host-neutral kind")
    kind_text, ref_id = value.split(":", 1)
    _require_non_empty(ref_id, "confirmed_subjects.ref_id")
    return OpaqueMemoryRef(
        ref_kind=HostNeutralRefKind(kind_text),
        ref_id=ref_id,
        digest=None,
    )


def _validate_compact_summary_fact_refs(
    event: MemoryProjectionEvent,
    evidence_backed_facts: tuple[EvidenceBackedFactView, ...],
    materialized_facts: tuple[EvidenceBackedFactView, ...],
) -> None:
    """校验 summary confirmed fact refs 只引用已物化 evidence-backed facts。

    :param event: CONTEXT_COMPACTED projection event。
    :param evidence_backed_facts: 当前 snapshot 中已有 evidence-backed facts。
    :param materialized_facts: 当前 compact event 新物化的 evidence-backed facts。
    :returns: ``None``。
    :raises ValueError: summary 引用了未知 fact ref 时抛出。
    """

    if _is_vnext_compacted_payload(event.payload):
        return
    summary = _required_payload_mapping(
        event.payload,
        _PAYLOAD_FIELD_EPISODE_SUMMARY_CANDIDATE,
    )
    refs = _optional_text_tuple(summary, _PAYLOAD_FIELD_CONFIRMED_FACT_REFS)
    allowed_refs = _existing_evidence_backed_fact_refs(
        evidence_backed_facts + materialized_facts
    )
    if not set(refs).issubset(allowed_refs):
        raise ValueError(
            "compact summary confirmed_fact_refs must reference evidence-backed facts"
        )


def _existing_evidence_backed_fact_refs(
    evidence_backed_facts: tuple[EvidenceBackedFactView, ...],
) -> set[str]:
    """汇总已有 evidence-backed fact refs。

    :param evidence_backed_facts: 当前 snapshot 的 evidence-backed facts。
    :returns: 可被 compact summary 引用的 ref 集合。
    """

    refs: set[str] = set()
    for fact in evidence_backed_facts:
        refs.add(fact.item_id)
        refs.add(fact.candidate_id)
        refs.add(fact.provenance.event_id)
        for evidence_ref in fact.evidence_refs:
            refs.add(evidence_ref)
        if fact.provenance.payload_ref is not None:
            refs.add(fact.provenance.payload_ref)
    return refs


def _pinned_state_with_user_input(
    pinned_state: PinnedStateView,
    event: MemoryProjectionEvent,
    *,
    policy: MemoryProjectionPolicy,
) -> PinnedStateView:
    """把用户输入纳入 pinned constraints。

    :param pinned_state: 既有 pinned state。
    :param event: USER_INPUT_ACCEPTED projection event。
    :param policy: memory projection policy。
    :returns: 更新后的 pinned state。
    """

    text = _bounded_summary_text(
        _user_visible_text(event),
        max_size_units=policy.max_raw_turn_size_units,
        prefer_ref=False,
    )
    if text is None:
        text = _ref_summary_text(
            payload_ref=event.payload_ref,
            payload_digest=event.payload_digest,
            fallback_event_id=event.event_id,
        )
    current_goal = pinned_state.current_goal
    if current_goal is None:
        current_goal = text
    return PinnedStateView(
        current_goal=current_goal,
        confirmed_subjects=pinned_state.confirmed_subjects,
        user_constraints=pinned_state.user_constraints + (text,),
        open_questions=pinned_state.open_questions,
    )


def _limit_pinned_state(
    pinned_state: PinnedStateView, policy: MemoryProjectionPolicy
) -> PinnedStateView:
    """按 policy 限制 pinned state 条目数量。

    :param pinned_state: 原始 pinned state。
    :param policy: memory projection policy。
    :returns: 限制后的 pinned state。
    """

    return PinnedStateView(
        current_goal=pinned_state.current_goal,
        confirmed_subjects=pinned_state.confirmed_subjects[
            -policy.max_pinned_items :
        ],
        user_constraints=pinned_state.user_constraints[-policy.max_pinned_items :],
        open_questions=pinned_state.open_questions[-policy.max_pinned_items :],
    )


def _limit_evidence_backed_facts(
    items: tuple[EvidenceBackedFactView, ...],
    *,
    policy: MemoryProjectionPolicy,
    policy_digest: MemoryPolicyDigest,
    pinned_state: PinnedStateView,
    continuity_items: tuple[ConversationContinuityItem, ...],
) -> tuple[tuple[EvidenceBackedFactView, ...], tuple[MemoryDiagnostic, ...]]:
    """按 policy 选择 evidence-backed fact working set。

    :param items: 原始 evidence-backed facts。
    :param policy: memory projection policy。
    :param policy_digest: memory policy digest。
    :param pinned_state: 当前已物化 pinned state。
    :param continuity_items: 当前 continuity items，用于 recent reference 排序。
    :returns: 限制后的 facts 与 budget diagnostics。
    """

    if len(items) <= policy.max_evidence_backed_facts:
        return items, ()
    kept = _select_evidence_backed_fact_working_set(
        items,
        policy=policy,
        pinned_state=pinned_state,
        continuity_items=continuity_items,
    )
    kept_ids = frozenset(item.item_id for item in kept)
    first_dropped = next(item for item in items if item.item_id not in kept_ids)
    return kept, (
        _budget_diagnostic(
            event_sequence=first_dropped.provenance.event_sequence,
            item_id=first_dropped.item_id,
            policy_digest=policy_digest,
            message="evidence-backed facts limited by memory policy",
        ),
    )


def _select_evidence_backed_fact_working_set(
    items: tuple[EvidenceBackedFactView, ...],
    *,
    policy: MemoryProjectionPolicy,
    pinned_state: PinnedStateView,
    continuity_items: tuple[ConversationContinuityItem, ...],
) -> tuple[EvidenceBackedFactView, ...]:
    """按 Host-neutral relevance 选择 bounded fact working set。

    :param items: 已去重 facts。
    :param policy: memory projection policy。
    :param pinned_state: 当前 pinned state。
    :param continuity_items: 当前 continuity items。
    :returns: 被选中的 facts，按 EventLog 顺序输出。
    """

    ranked = sorted(
        items,
        key=lambda item: _evidence_backed_fact_selection_key(
            item,
            pinned_state=pinned_state,
            continuity_items=continuity_items,
        ),
    )
    selected_ids = frozenset(
        item.item_id for item in ranked[: policy.max_evidence_backed_facts]
    )
    return tuple(item for item in items if item.item_id in selected_ids)


def _evidence_backed_fact_selection_key(
    item: EvidenceBackedFactView,
    *,
    pinned_state: PinnedStateView,
    continuity_items: tuple[ConversationContinuityItem, ...],
) -> tuple[int, int, int, int, str]:
    """生成 fact working-set 排序 key。

    :param item: evidence-backed fact。
    :param pinned_state: 当前 pinned state。
    :param continuity_items: 当前 continuity items。
    :returns: Python 升序可用的排序 key。
    """

    fact_tokens = _text_tokens(item.claim_text)
    subject_tokens = _pinned_subject_tokens(pinned_state)
    goal_tokens = _text_tokens(pinned_state.current_goal or "")
    recent_tokens = _recent_user_reference_tokens(continuity_items)
    return (
        -_token_overlap_count(fact_tokens, subject_tokens),
        -_token_overlap_count(fact_tokens, goal_tokens),
        -_token_overlap_count(fact_tokens, recent_tokens),
        -item.provenance.event_sequence,
        item.item_id,
    )


def _limit_working_assumptions(
    items: tuple[WorkingAssumptionView, ...],
    *,
    policy: MemoryProjectionPolicy,
    policy_digest: MemoryPolicyDigest,
) -> tuple[tuple[WorkingAssumptionView, ...], tuple[MemoryDiagnostic, ...]]:
    """按 policy 限制 working assumptions 数量。

    :param items: 原始 working assumptions。
    :param policy: memory projection policy。
    :param policy_digest: memory policy digest。
    :returns: 限制后的 assumptions 与 budget diagnostics。
    """

    deduped_items = _dedupe_working_assumptions_by_normalized_summary(items)
    if len(deduped_items) <= policy.max_working_assumptions:
        return deduped_items, ()
    kept = deduped_items[-policy.max_working_assumptions :]
    kept_ids = frozenset(item.item_id for item in kept)
    first_dropped = next(
        item for item in deduped_items if item.item_id not in kept_ids
    )
    return kept, (
        _budget_diagnostic(
            event_sequence=first_dropped.event_sequence,
            item_id=first_dropped.item_id,
            policy_digest=policy_digest,
            message="working assumptions limited by memory policy",
        ),
    )


def _limit_continuity_items(
    items: tuple[ConversationContinuityItem, ...],
    *,
    policy: MemoryProjectionPolicy,
    policy_digest: MemoryPolicyDigest,
) -> tuple[tuple[ConversationContinuityItem, ...], tuple[MemoryDiagnostic, ...]]:
    """按 history pool policy 选择 continuity items。

    recent raw turns 使用 count-based floor；older raw turns、assistant
    conclusions 与其它非 episode continuity 先共用一个 size budget，episode
    summaries 只使用剩余 budget。

    :param items: 原始 continuity items。
    :param policy: memory projection policy。
    :param policy_digest: memory policy digest。
    :returns: 选择后的 continuity items 与 budget diagnostics。
    """

    raw_items = tuple(item for item in items if _is_raw_turn(item))
    if policy.recent_raw_turns_floor == _MIN_SEQUENCE:
        recent_raw: tuple[ConversationContinuityItem, ...] = ()
    else:
        recent_raw = raw_items[-policy.recent_raw_turns_floor :]
    recent_ids = frozenset(item.item_id for item in recent_raw)
    primary_pool_items = tuple(
        item for item in items if not _is_raw_turn(item) and not _is_episode(item)
    )
    older_raw = tuple(item for item in raw_items if item.item_id not in recent_ids)
    episode_summaries = _policy_bounded_recent_episode_summaries(
        tuple(item for item in items if _is_episode(item)),
        policy=policy,
    )
    selected_ids: set[str] = set(item.item_id for item in recent_raw)
    budget_used = _EMPTY_SIZE_UNITS
    for item in reversed(_event_ordered_items(older_raw + primary_pool_items)):
        if budget_used + item.size_units.units <= policy.history_pool_size_units:
            selected_ids.add(item.item_id)
            budget_used += item.size_units.units
    for item in reversed(episode_summaries):
        if budget_used + item.size_units.units <= policy.history_pool_size_units:
            selected_ids.add(item.item_id)
            budget_used += item.size_units.units
    selected = tuple(
        _mark_continuity_item_included(item)
        for item in items
        if item.item_id in selected_ids
    )
    if len(selected) == len(items):
        return selected, ()
    first_dropped = next(item for item in items if item.item_id not in selected_ids)
    return selected, (
        _budget_diagnostic(
            event_sequence=first_dropped.event_sequence,
            item_id=first_dropped.item_id,
            policy_digest=policy_digest,
            message="conversation continuity limited by history pool budget",
        ),
    )


def _policy_bounded_recent_episode_summaries(
    items: tuple[ConversationContinuityItem, ...],
    *,
    policy: MemoryProjectionPolicy,
) -> tuple[ConversationContinuityItem, ...]:
    """选择 policy 派生上限内的 recent episode summaries。

    :param items: episode summary items。
    :param policy: memory projection policy。
    :returns: 最近的 episode summaries。
    """

    max_items = max(
        DEFAULT_MEMORY_MAX_EPISODE_SUMMARIES_FLOOR,
        policy.recent_raw_turns_floor,
    )
    return _event_ordered_items(items)[-max_items:]


def _expire_covered_minimum_preserve_items(
    items: tuple[ConversationContinuityItem, ...],
    *,
    evidence_backed_facts: tuple[EvidenceBackedFactView, ...],
    policy_digest: MemoryPolicyDigest,
) -> tuple[tuple[ConversationContinuityItem, ...], tuple[MemoryDiagnostic, ...]]:
    """移除已被 stable fact 或更新 episode summary 覆盖的 minimum preserve。

    :param items: continuity items。
    :param evidence_backed_facts: 当前可见 stable facts。
    :param policy_digest: memory policy digest。
    :returns: 过滤后的 continuity items 与 coverage diagnostics。
    """

    kept: list[ConversationContinuityItem] = []
    diagnostics: list[MemoryDiagnostic] = []
    for item in items:
        if item.item_kind is not ConversationContinuityKind.MINIMUM_PRESERVE_ITEM:
            kept.append(item)
            continue
        if _minimum_preserve_is_covered(
            item,
            items=items,
            evidence_backed_facts=evidence_backed_facts,
        ):
            diagnostics.append(
                _minimum_preserve_covered_diagnostic(
                    item,
                    policy_digest=policy_digest,
                )
            )
            continue
        kept.append(item)
    return tuple(kept), tuple(diagnostics)


def _minimum_preserve_is_covered(
    item: ConversationContinuityItem,
    *,
    items: tuple[ConversationContinuityItem, ...],
    evidence_backed_facts: tuple[EvidenceBackedFactView, ...],
) -> bool:
    """判断 minimum preserve 是否已被后续 stable / summary 覆盖。

    :param item: minimum preserve item。
    :param items: 全部 continuity items。
    :param evidence_backed_facts: 当前可见 stable facts。
    :returns: 已覆盖时返回 ``True``。
    """

    source_refs = frozenset(item.source_refs)
    if len(source_refs) == 0:
        return False
    for fact in evidence_backed_facts:
        if fact.provenance.event_sequence <= item.event_sequence:
            continue
        if source_refs.issubset(_evidence_backed_fact_cover_refs(fact)):
            return True
    for summary in items:
        if summary.item_kind is not ConversationContinuityKind.EPISODE_SUMMARY:
            continue
        if summary.event_sequence <= item.event_sequence:
            continue
        if source_refs.issubset(frozenset(summary.source_refs)):
            return True
    return False


def _evidence_backed_fact_cover_refs(
    fact: EvidenceBackedFactView,
) -> frozenset[str]:
    """汇总 stable fact 可覆盖的 refs。

    :param fact: evidence-backed fact。
    :returns: refs 集合。
    """

    refs: set[str] = set(fact.evidence_refs)
    refs.add(fact.item_id)
    refs.add(fact.candidate_id)
    refs.add(fact.provenance.event_id)
    if fact.compact_artifact_ref is not None:
        refs.add(fact.compact_artifact_ref)
    if fact.provenance.payload_ref is not None:
        refs.add(fact.provenance.payload_ref)
    return frozenset(refs)


def _minimum_preserve_covered_diagnostic(
    item: ConversationContinuityItem, *, policy_digest: MemoryPolicyDigest
) -> MemoryDiagnostic:
    """构造 minimum preserve 被覆盖后的移除 diagnostic。

    :param item: 被移除的 minimum preserve item。
    :param policy_digest: memory policy digest。
    :returns: memory diagnostic。
    """

    return MemoryDiagnostic(
        diagnostic_id=_diagnostic_id(
            MemoryDiagnosticReason.MINIMUM_PRESERVE_ITEM_COVERED,
            event_sequence=item.event_sequence,
            item_id=item.item_id,
        ),
        reason=MemoryDiagnosticReason.MINIMUM_PRESERVE_ITEM_COVERED,
        message=(
            "minimum preserve item excluded because a newer stable fact or "
            "episode summary covers its source refs"
        ),
        event_sequence=item.event_sequence,
        item_id=item.item_id,
        policy_digest=policy_digest,
        recorded_at=None,
    )


def _event_ordered_items(
    items: tuple[ConversationContinuityItem, ...],
) -> tuple[ConversationContinuityItem, ...]:
    """按 EventLog sequence 稳定排序 continuity items。

    :param items: continuity items。
    :returns: 按 event sequence 升序排列的 items。
    """

    return tuple(sorted(items, key=lambda item: item.event_sequence))


def _normalized_text(text: str) -> str:
    """按 memory 去重口径规范化文本。

    :param text: 原始文本。
    :returns: casefold 且压缩空白后的文本。
    """

    return " ".join(text.casefold().split())


def _dedupe_text_tuple_by_normalized_text(
    values: tuple[str, ...]
) -> tuple[str, ...]:
    """按 normalized text 去重文本 tuple，并保留较新的原始文本。

    :param values: 原始文本 tuple；越靠后的元素视为越新。
    :returns: 去重后的文本 tuple，保持被保留元素的原始相对顺序。
    """

    seen: set[str] = set()
    kept_reversed: list[str] = []
    for value in reversed(values):
        normalized = _normalized_text(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        kept_reversed.append(value)
    return tuple(reversed(kept_reversed))


def _dedupe_working_assumptions_by_normalized_summary(
    items: tuple[WorkingAssumptionView, ...]
) -> tuple[WorkingAssumptionView, ...]:
    """按 normalized assumption summary 去重 working assumptions。

    :param items: 原始 working assumption views。
    :returns: 去重后的 assumptions；同一 normalized summary 保留 EventLog
        sequence 更新的 view，并按 committed EventLog 顺序稳定输出。
    """

    selected_by_summary: dict[str, WorkingAssumptionView] = {}
    for item in items:
        normalized = _normalized_text(item.assumption_summary)
        existing = selected_by_summary.get(normalized)
        if existing is None or _working_assumption_dedupe_key(
            item
        ) > _working_assumption_dedupe_key(existing):
            selected_by_summary[normalized] = item
    return tuple(
        sorted(
            selected_by_summary.values(),
            key=lambda item: (item.event_sequence, item.item_id),
        )
    )


def _working_assumption_dedupe_key(
    item: WorkingAssumptionView,
) -> tuple[int, str]:
    """生成 working assumption normalized 去重优先级。

    :param item: working assumption view。
    :returns: Python 可比较的优先级；较大值代表更新、更适合保留。
    """

    return (item.event_sequence, item.item_id)


def _text_tokens(text: str) -> frozenset[str]:
    """提取 Host-neutral 文本 token。

    :param text: 原始文本。
    :returns: token 集合。
    """

    normalized_chars: list[str] = []
    for char in text.casefold():
        if char.isalnum():
            normalized_chars.append(char)
        else:
            normalized_chars.append(" ")
    return frozenset(token for token in "".join(normalized_chars).split() if token)


def _pinned_subject_tokens(pinned_state: PinnedStateView) -> frozenset[str]:
    """从 pinned subjects 提取排序用 token。

    :param pinned_state: 当前 pinned state。
    :returns: subject token 集合。
    """

    tokens: set[str] = set()
    for ref in pinned_state.confirmed_subjects:
        tokens.update(_text_tokens(ref.ref_kind.value))
        tokens.update(_text_tokens(ref.ref_id))
    return frozenset(tokens)


def _recent_user_reference_tokens(
    items: tuple[ConversationContinuityItem, ...],
) -> frozenset[str]:
    """从 recent raw user turns 提取排序用 token。

    :param items: continuity items。
    :returns: recent user token 集合。
    """

    tokens: set[str] = set()
    user_turns = tuple(
        item
        for item in items
        if item.item_kind is ConversationContinuityKind.RAW_USER_TURN
    )
    for item in user_turns[-DEFAULT_MEMORY_RECENT_RAW_TURNS_FLOOR:]:
        if item.summary_text is not None:
            tokens.update(_text_tokens(item.summary_text))
    return frozenset(tokens)


def _token_overlap_count(
    left: frozenset[str], right: frozenset[str]
) -> int:
    """计算两个 token 集合的交集大小。

    :param left: 左侧 token 集合。
    :param right: 右侧 token 集合。
    :returns: 交集 token 数。
    """

    return len(left.intersection(right))


def _dedupe_text_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    """按首次出现顺序去重文本 tuple。

    :param values: 原始文本 tuple。
    :returns: 去重后的文本 tuple。
    """

    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _replace_item_by_id(
    items: tuple[_MemoryItemT, ...], item: _MemoryItemT
) -> tuple[_MemoryItemT, ...]:
    """按 item id 替换或追加 item。

    :param items: 原始 item 元组。
    :param item: 新 item。
    :returns: 替换或追加后的 item 元组。
    """

    kept = tuple(existing for existing in items if existing.item_id != item.item_id)
    return kept + (item,)


def _dedupe_diagnostics(
    diagnostics: tuple[MemoryDiagnostic, ...],
) -> tuple[MemoryDiagnostic, ...]:
    """按 diagnostic id 去重并保持稳定顺序。

    :param diagnostics: 原始 diagnostics。
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


def _unsupported_event_type_diagnostic(
    event: MemoryProjectionEvent, *, policy_digest: MemoryPolicyDigest
) -> MemoryDiagnostic:
    """构造未知 event type 的非静默 diagnostic。

    :param event: 未识别的 projection event。
    :param policy_digest: memory policy digest。
    :returns: memory diagnostic。
    """

    item_id = _item_id(event, MemoryExcludedReason.UNSUPPORTED_EVENT_TYPE.value)
    return MemoryDiagnostic(
        diagnostic_id=_diagnostic_id(
            MemoryDiagnosticReason.UNSUPPORTED_EVENT_TYPE,
            event_sequence=event.event_sequence,
            item_id=item_id,
        ),
        reason=MemoryDiagnosticReason.UNSUPPORTED_EVENT_TYPE,
        message=(
            f"{MemoryExcludedReason.UNSUPPORTED_EVENT_TYPE.value}: "
            f"event_type={event.event_type}"
        ),
        event_sequence=event.event_sequence,
        item_id=item_id,
        policy_digest=policy_digest,
        recorded_at=None,
    )


def _payload_ref_pair_from_event(
    event: MemoryProjectionEvent,
) -> tuple[str | None, str | None]:
    """读取 event row 或 payload 内的 payload ref / digest。

    :param event: projection event。
    :returns: payload ref / digest 成对结果。
    """

    if event.payload_ref is not None and event.payload_digest is not None:
        return event.payload_ref, event.payload_digest
    nested = _optional_payload_mapping(event.payload, _PAYLOAD_FIELD_PAYLOAD_REF)
    if nested is not None:
        nested_ref = _optional_payload_str(nested, _PAYLOAD_FIELD_PAYLOAD_REF)
        nested_digest = _optional_payload_str(nested, _PAYLOAD_FIELD_PAYLOAD_DIGEST)
        if nested_ref is not None and nested_digest is not None:
            return nested_ref, nested_digest
    payload_ref = _optional_payload_str(event.payload, _PAYLOAD_FIELD_PAYLOAD_REF)
    payload_digest = _optional_payload_str(
        event.payload, _PAYLOAD_FIELD_PAYLOAD_DIGEST
    )
    if payload_ref is not None and payload_digest is not None:
        return payload_ref, payload_digest
    return None, None


def _event_or_payload_str(
    event: MemoryProjectionEvent, field_name: str
) -> str | None:
    """优先读取 event row 字段，其次读取 payload 同名字段。

    :param event: projection event。
    :param field_name: payload 字段名。
    :returns: 文本值或 ``None``。
    """

    if field_name == _PAYLOAD_FIELD_RUN_ID and event.run_id is not None:
        return event.run_id
    if field_name == _PAYLOAD_FIELD_ATTEMPT_ID and event.attempt_id is not None:
        return event.attempt_id
    if field_name == _PAYLOAD_FIELD_EXECUTION_ID and event.execution_id is not None:
        return event.execution_id
    return _optional_payload_str(event.payload, field_name)


def _user_visible_text(event: MemoryProjectionEvent) -> str:
    """读取用户输入可见文本，缺失时返回中立 ref 摘要。

    :param event: USER_INPUT_ACCEPTED projection event。
    :returns: 用户输入连续性文本。
    """

    display_text = _optional_payload_str(event.payload, _PAYLOAD_FIELD_DISPLAY_TEXT)
    if display_text is not None:
        return display_text
    return _ref_summary_text(
        payload_ref=event.payload_ref,
        payload_digest=event.payload_digest,
        fallback_event_id=event.event_id,
    )


def _compact_episode_summary_text(event: MemoryProjectionEvent) -> str:
    """读取 accepted compact episode summary 文本。

    :param event: CONTEXT_COMPACTED projection event。
    :returns: episode summary 文本。
    """

    if _is_vnext_compacted_payload(event.payload):
        summary = _vnext_session_summary_mapping(event.payload)
        if summary is not None:
            return _required_str(summary, _PAYLOAD_FIELD_SUMMARY_TEXT)
        return _ref_summary_text(
            payload_ref=event.payload_ref,
            payload_digest=event.payload_digest,
            fallback_event_id=event.event_id,
        )
    summary = _required_payload_mapping(
        event.payload,
        _PAYLOAD_FIELD_EPISODE_SUMMARY_CANDIDATE,
    )
    for field_name in (_PAYLOAD_FIELD_SUMMARY_TEXT, _PAYLOAD_FIELD_SUMMARY):
        value = _optional_payload_str(summary, field_name)
        if value is not None:
            return value
    parts = _compact_episode_summary_parts(summary)
    if len(parts) > 0:
        return "\n".join(parts)
    return _ref_summary_text(
        payload_ref=event.payload_ref,
        payload_digest=event.payload_digest,
        fallback_event_id=event.event_id,
    )


def _compact_episode_summary_parts(
    summary: Mapping[str, JsonValue],
) -> tuple[str, ...]:
    """把 typed compact summary 字段确定性拼为导航文本。

    :param summary: episode summary candidate JSON object。
    :returns: 文本片段 tuple。
    """

    parts: list[str] = []
    title = _optional_payload_str(summary, _PAYLOAD_FIELD_TITLE)
    if title is None:
        title = _optional_payload_str(summary, _PAYLOAD_FIELD_EPISODE_TITLE)
    if title is not None:
        parts.append(f"title={title}")
    goal = _optional_payload_str(summary, _PAYLOAD_FIELD_GOAL)
    if goal is not None:
        parts.append(f"goal={goal}")
    for action in _optional_text_tuple(summary, _PAYLOAD_FIELD_COMPLETED_ACTIONS):
        parts.append(f"completed_action={action}")
    for question in _optional_text_tuple(summary, _PAYLOAD_FIELD_OPEN_QUESTIONS):
        parts.append(f"open_question={question}")
    next_step = _optional_payload_str(summary, _PAYLOAD_FIELD_NEXT_STEP)
    if next_step is not None:
        parts.append(f"next_step={next_step}")
    return tuple(parts)


def _required_payload_mapping(
    payload: Mapping[str, JsonValue], field_name: str
) -> Mapping[str, JsonValue]:
    """读取必填 payload mapping 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: JSON mapping。
    :raises ValueError: 字段缺失或不是 mapping 时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, Mapping):
        return value
    raise ValueError(f"{field_name} must be JSON mapping")


def _optional_text_tuple(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[str, ...]:
    """读取 optional payload 文本数组字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 文本 tuple；字段缺失时返回空 tuple。
    :raises ValueError: 字段存在但不是文本数组时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be list")
    result: list[str] = []
    for item in value:
        result.append(_as_str(item, field_name))
    return tuple(result)


def _optional_patch_str(
    mapping: Mapping[str, JsonValue], field_name: str
) -> str | None:
    """读取 compact patch optional 字符串字段。

    :param mapping: JSON mapping。
    :param field_name: 字段名。
    :returns: 字符串值或 ``None``。
    :raises ValueError: 字段存在但不是非空字符串时抛出。
    """

    value = mapping.get(field_name)
    if value is None:
        return None
    return _as_str(value, field_name)


def _bounded_summary_text(
    text: str | None, *, max_size_units: int, prefer_ref: bool
) -> str | None:
    """按单条 raw turn cap 选择是否保留摘要文本。

    :param text: 候选摘要文本。
    :param max_size_units: policy 单条尺寸上限。
    :param prefer_ref: 有 payload ref 时是否优先不复制文本。
    :returns: 可保留文本或 ``None``。
    """

    if text is None or prefer_ref:
        return None
    if estimate_memory_size_units(text).units > max_size_units:
        return None
    return text


def _ref_summary_text(
    *,
    payload_ref: str | None,
    payload_digest: str | None,
    fallback_event_id: str,
) -> str:
    """构造 continuity 使用的中立 ref 摘要。

    :param payload_ref: 可选 payload ref。
    :param payload_digest: 可选 payload digest。
    :param fallback_event_id: 缺少 payload ref 时的 event id。
    :returns: 中立 ref 摘要。
    """

    if payload_ref is None:
        return f"event_ref={fallback_event_id}"
    if payload_digest is None:
        return f"payload_ref={payload_ref}"
    return f"payload_ref={payload_ref}; payload_digest={payload_digest}"


def _mark_continuity_item_included(
    item: ConversationContinuityItem,
) -> ConversationContinuityItem:
    """把 continuity item 标记为纳入 snapshot。

    :param item: 原始 item。
    :returns: 标记后的 item。
    """

    reason = item.included_reason
    if reason is None:
        if item.item_kind is ConversationContinuityKind.EPISODE_SUMMARY:
            reason = MemoryIncludedReason.EPISODE_SUMMARY
        else:
            reason = MemoryIncludedReason.RECENT_RAW_TURN
    return ConversationContinuityItem(
        item_id=item.item_id,
        item_kind=item.item_kind,
        producer_kind=item.producer_kind,
        claim_status=item.claim_status,
        event_id=item.event_id,
        event_sequence=item.event_sequence,
        run_id=item.run_id,
        summary_text=item.summary_text,
        label=item.label,
        source_refs=item.source_refs,
        preserve_reason=item.preserve_reason,
        payload_ref=item.payload_ref,
        payload_digest=item.payload_digest,
        included_reason=reason,
        excluded_reason=None,
        size_units=item.size_units,
    )


def _is_raw_turn(item: ConversationContinuityItem) -> bool:
    """判断 item 是否为 raw turn。

    :param item: continuity item。
    :returns: raw turn 返回 ``True``。
    """

    return item.item_kind in (
        ConversationContinuityKind.RAW_USER_TURN,
        ConversationContinuityKind.RAW_ASSISTANT_TURN,
    )


def _is_episode(item: ConversationContinuityItem) -> bool:
    """判断 item 是否为 episode summary。

    :param item: continuity item。
    :returns: episode summary 返回 ``True``。
    """

    return item.item_kind is ConversationContinuityKind.EPISODE_SUMMARY


def _budget_diagnostic(
    *,
    event_sequence: int,
    item_id: str,
    policy_digest: MemoryPolicyDigest,
    message: str,
) -> MemoryDiagnostic:
    """构造 budget limit diagnostic。

    :param event_sequence: 关联 event sequence。
    :param item_id: 关联 item id。
    :param policy_digest: memory policy digest。
    :param message: diagnostic message。
    :returns: memory diagnostic。
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


def _item_id(event: MemoryProjectionEvent, item_kind: str) -> str:
    """构造稳定 memory item id。

    :param event: projection event。
    :param item_kind: item kind 文本。
    :returns: 稳定 item id。
    """

    return f"{_ITEM_ID_PREFIX}:{item_kind}:{event.event_id}"


def _diagnostic_id(
    reason: MemoryDiagnosticReason, *, event_sequence: int, item_id: str
) -> str:
    """构造稳定 diagnostic id。

    :param reason: diagnostic reason。
    :param event_sequence: 关联 event sequence。
    :param item_id: 关联 item id。
    :returns: 稳定 diagnostic id。
    """

    digest = sha256_digest_json(
        {
            "event_sequence": event_sequence,
            "item_id": item_id,
            "reason": reason.value,
        }
    ).removeprefix("sha256:")
    return f"{_DIAGNOSTIC_ID_PREFIX}:{digest}"


def _optional_payload_mapping(
    payload: Mapping[str, JsonValue], field_name: str
) -> Mapping[str, JsonValue] | None:
    """读取 optional payload mapping 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: mapping 或 ``None``；其它类型按缺失处理。
    """

    value = payload.get(field_name)
    if isinstance(value, Mapping):
        return value
    return None


def _optional_payload_str(
    payload: Mapping[str, JsonValue], field_name: str
) -> str | None:
    """读取 optional payload 文本字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 非空文本或 ``None``。
    """

    value = payload.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    return None


def memory_projection_policy_to_json_value(
    policy: MemoryProjectionPolicy,
) -> JsonValue:
    """把 memory projection policy 转换为 canonical JSON 值。

    :param policy: memory projection policy。
    :returns: 可序列化 JSON 值。
    """

    return {
        "context_window_size": policy.context_window_size,
        "history_pool_context_ratio": policy.history_pool_context_ratio,
        "history_pool_size_cap": policy.history_pool_size_cap,
        "history_pool_size_floor": policy.history_pool_size_floor,
        "max_delta_repair_events": policy.max_delta_repair_events,
        "max_lag_events_for_inline_delta": policy.max_lag_events_for_inline_delta,
        "max_pinned_items": policy.max_pinned_items,
        "max_evidence_backed_facts": policy.max_evidence_backed_facts,
        "max_working_assumptions": policy.max_working_assumptions,
        "raw_turn_context_ratio": policy.raw_turn_context_ratio,
        "raw_turn_size_cap": policy.raw_turn_size_cap,
        "raw_turn_size_floor": policy.raw_turn_size_floor,
        "recent_raw_turns_floor": policy.recent_raw_turns_floor,
        "stable_layer_context_ratio": policy.stable_layer_context_ratio,
        "stable_layer_size_cap": policy.stable_layer_size_cap,
        "stable_layer_size_floor": policy.stable_layer_size_floor,
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
        "evidence_backed_facts": [
            _evidence_backed_fact_to_json_value(item) for item in snapshot.evidence_backed_facts
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
    if "verified_facts" in mapping:
        raise ValueError("old verified_facts snapshot key is not supported")
    return ConversationMemorySnapshot(
        snapshot_id=_required_str(mapping, "snapshot_id"),
        session_id=_required_str(mapping, "session_id"),
        cursor=_cursor_from_json_value(_required_value(mapping, "cursor")),
        policy_digest=_required_str(mapping, "policy_digest"),
        pinned_state=_pinned_state_from_json_value(
            _required_value(mapping, "pinned_state")
        ),
        evidence_backed_facts=tuple(
            _evidence_backed_fact_from_json_value(item)
            for item in _required_list(mapping, "evidence_backed_facts")
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
        "evidence_backed_facts": [
            _evidence_backed_fact_to_json_value(item) for item in snapshot.evidence_backed_facts
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


def _evidence_backed_fact_to_json_value(item: EvidenceBackedFactView) -> JsonValue:
    """把 evidence-backed fact 转换为 JSON 值。

    :param item: evidence-backed fact。
    :returns: JSON 值。
    """

    return {
        "attributes": item.attributes,
        "candidate_id": item.candidate_id,
        "claim_text": item.claim_text,
        "compact_artifact_ref": item.compact_artifact_ref,
        "evidence_kind": item.evidence_kind.value,
        "evidence_refs": list(item.evidence_refs),
        "excluded_reason": _enum_value_or_none(item.excluded_reason),
        "extraction_operation_ref": item.extraction_operation_ref,
        "included_reason": _enum_value_or_none(item.included_reason),
        "item_id": item.item_id,
        "provenance": _provenance_to_json_value(item.provenance),
        "size_units": item.size_units.units,
    }


def _evidence_backed_fact_from_json_value(value: JsonValue) -> EvidenceBackedFactView:
    """从 JSON 值恢复 evidence-backed fact。

    :param value: JSON 值。
    :returns: evidence-backed fact。
    """

    mapping = _as_mapping(value, "evidence_backed_fact")
    if "fact_summary" in mapping or "evidence_anchor" in mapping:
        raise ValueError("old evidence-backed fact JSON shape is not supported")
    return EvidenceBackedFactView(
        item_id=_required_str(mapping, "item_id"),
        claim_text=_required_str(mapping, "claim_text"),
        evidence_kind=MemoryEvidenceBackedFactKind(_required_str(mapping, "evidence_kind")),
        evidence_refs=tuple(
            _as_str(item, "evidence_refs item")
            for item in _required_list(mapping, "evidence_refs")
        ),
        attributes=_as_mapping(
            _required_value(mapping, "attributes"),
            "attributes",
        ),
        provenance=_provenance_from_json_value(_required_value(mapping, "provenance")),
        extraction_operation_ref=_required_str(mapping, "extraction_operation_ref"),
        compact_artifact_ref=_optional_str(mapping, "compact_artifact_ref"),
        candidate_id=_required_str(mapping, "candidate_id"),
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
        "label": item.label,
        "payload_digest": item.payload_digest,
        "payload_ref": item.payload_ref,
        "producer_kind": item.producer_kind.value,
        "preserve_reason": _enum_value_or_none(item.preserve_reason),
        "run_id": item.run_id,
        "size_units": item.size_units.units,
        "source_refs": list(item.source_refs),
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
        label=_optional_str(mapping, "label"),
        source_refs=tuple(
            _as_str(item, "source_refs item")
            for item in _required_list(mapping, "source_refs")
        ),
        preserve_reason=_optional_minimum_preserve_reason(
            mapping,
            "preserve_reason",
        ),
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


def _optional_minimum_preserve_reason(
    mapping: Mapping[str, JsonValue], field_name: str
) -> MemoryContinuityPreserveReason | None:
    """读取 optional minimum preserve reason。

    :param mapping: JSON mapping。
    :param field_name: 字段名。
    :returns: minimum preserve reason 或 ``None``。
    """

    value = _optional_str(mapping, field_name)
    if value is None:
        return None
    return MemoryContinuityPreserveReason(value)


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
    :raises TypeError: 值不是整数或为 bool 时抛出。
    :raises ValueError: 值小于 ``1`` 时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < _MIN_POSITIVE_LIMIT:
        raise ValueError(f"{field_name} must be positive")


def _require_non_negative(value: int, field_name: str) -> None:
    """校验整数非负。

    :param value: 整数值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 值不是整数或为 bool 时抛出。
    :raises ValueError: 值小于 ``0`` 时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < _MIN_SEQUENCE:
        raise ValueError(f"{field_name} must be non-negative")


def _require_ratio(value: float, field_name: str) -> None:
    """校验 ratio/floor/cap 模型比例位于 ``(0, 1]``。

    :param value: 比例值。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 值不是数值或为 bool 时抛出。
    :raises ValueError: 值不在允许范围时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be float")
    if value <= 0 or value > 1:
        raise ValueError(f"{field_name} must be in (0, 1]")


def _require_floor_cap(
    *,
    floor_value: int,
    cap_value: int,
    floor_field_name: str,
    cap_field_name: str,
) -> None:
    """校验尺寸下限与上限组合。

    :param floor_value: 尺寸下限。
    :param cap_value: 尺寸上限。
    :param floor_field_name: 下限字段名。
    :param cap_field_name: 上限字段名。
    :returns: ``None``。
    :raises TypeError: 字段类型非法时抛出。
    :raises ValueError: 下限或上限非法时抛出。
    """

    _require_positive(floor_value, floor_field_name)
    _require_positive(cap_value, cap_field_name)
    if floor_value > cap_value:
        raise ValueError(f"{floor_field_name} must be <= {cap_field_name}")


def _effective_size_units(
    *,
    context_window_size: int,
    ratio: float,
    floor_value: int,
    cap_value: int,
) -> int:
    """按 context window ratio / floor / cap 派生尺寸单位。

    :param context_window_size: 上下文窗口 token 数。
    :param ratio: 尺寸比例。
    :param floor_value: 尺寸下限。
    :param cap_value: 尺寸上限。
    :returns: 派生后的尺寸单位。
    """

    ratio_units = int(context_window_size * ratio)
    return min(cap_value, max(floor_value, ratio_units))


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


def _required_text_tuple(
    mapping: Mapping[str, JsonValue], field_name: str
) -> tuple[str, ...]:
    """读取必填字符串数组字段。

    :param mapping: JSON mapping。
    :param field_name: 字段名。
    :returns: 字符串 tuple。
    :raises ValueError: 字段缺失、非数组或元素非字符串时抛出。
    """

    return tuple(_as_str(item, field_name) for item in _required_list(mapping, field_name))


def _required_mapping_list(
    mapping: Mapping[str, JsonValue], field_name: str
) -> tuple[Mapping[str, JsonValue], ...]:
    """读取必填 JSON object array 字段。

    :param mapping: JSON mapping。
    :param field_name: 字段名。
    :returns: JSON object tuple。
    :raises ValueError: 字段缺失、非数组或元素非 object 时抛出。
    """

    result: list[Mapping[str, JsonValue]] = []
    for index, item in enumerate(_required_list(mapping, field_name)):
        result.append(_as_mapping(item, f"{field_name}[{index}]"))
    return tuple(result)
