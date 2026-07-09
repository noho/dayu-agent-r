"""Host compact material pack 与 prompt-local label helper。

本模块是 Host compact material/label owner。它只构造 Host internal
material pack，不读取业务工具、不写 EventLog、不向 Engine 暴露 Host
provenance。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn

from dayu.contracts.json_value import JsonValue
from dayu.host.compaction import (
    AnswerReadableItemVNext,
    CompactInstructionVNext,
    CompactEvidenceBlock,
    CompactMaterialBlock,
    CompactMaterialBlockKind,
    CompactMaterialPack,
    CompactMaterialSection,
    CompactReadableViewVNext,
    ConversationCompactInputVNext,
    CONVERSATION_COMPACT_INPUT_SCHEMA_VERSION_VNEXT,
    CurrentInputAnchorVNext,
    EvidenceReadableItemVNext,
    ForwardIntentStatusVNext,
    ForwardIntentTypeVNext,
    CompactSegmentSelection,
    CompactSegmentTrigger,
    CurrentInputAnchor,
    PromptLocalEvidenceMap,
    PromptLocalMaterialLabel,
    PromptLocalProvenanceEntry,
    ReadableAnswerAnchorItemVNext,
    ReadableAnswerAnchorVNext,
    ReadableFactItemVNext,
    ReadableForwardIntentVNext,
    ReadableReferenceContinuityItemVNext,
    ReferenceContinuityReasonVNext,
    TraceReadableItemVNext,
    TraceReadableKindVNext,
)
from dayu.host.context_budget import BudgetTextFragment
from dayu.host.context_events import CONTEXT_COMPACTED, validate_context_compacted_payload
from dayu.host.accepted_result_projection import project_accepted_tool_result
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventClass, EventLogRow, EventLogStore
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.state import RunRow
from dayu.host.durable.transaction import HostRow, HostTransaction
from dayu.host.evidence import ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH
from dayu.host.evidence import OpaqueEvidenceRef
from dayu.host.evidence import accepted_evidence_envelope_from_payload
from dayu.host.memory import (
    ConversationMemorySnapshotVNext,
    MemoryDiagnostic,
    MemoryProjectionPolicy,
    MemoryRepairReason,
    MemoryRepairRequest,
    MemorySnapshotCursor,
    digest_memory_projection_policy,
)
from dayu.host.payload_resolution import (
    event_payload_object,
    event_payload_object_for_result_ref,
)
from dayu.host.terminal_payload import PayloadTextReadPolicy
from dayu.host._terminal_answer import assistant_final_answer_continuity_text

_CURRENT_INPUT_PREFIX = "C"
_TRACE_PREFIX = "T"
_EVIDENCE_PREFIX = "E"
_PREVIOUS_PREFIX = "P"
_ANSWER_PREFIX = "A"
_LABEL_CHUNK_SEPARATOR = "."
_FIRST_ORDINAL = 1
_CURRENT_ANCHOR_ORDINAL = 1
_INITIAL_POLICY_DIGEST = "initial-compact-material-policy"
_INITIAL_REASON_CURRENT = "initial_current_anchor"
_INITIAL_REASON_TRACE = "initial_trace_material"
_INITIAL_REASON_EVIDENCE = "initial_evidence_material"
_INITIAL_REASON_PREVIOUS = "initial_previous_compacted_view"
_INITIAL_REASON_ANSWER = "initial_answer_material"
_NO_EVENT_SEQUENCE = 0
_DEFAULT_EVENT_SUB_INDEX = 0
_REASON_SELECTED = "selected"
_REASON_PROTECTED_CURRENT_INPUT = "protected_current_input"
_REASON_PROTECTED_RECENT_RAW_FLOOR = "protected_recent_raw_floor"
_REASON_ALREADY_REPRESENTED = "already_represented"
_REASON_BUDGET_LIMIT = "budget_limit"
_REASON_NOT_IN_SEGMENT = "not_in_segment"
_REASON_PREVIOUS_COMPACTED_VIEW = "previous_compacted_view_not_selected"
_STABLE_GOALS_BLOCK_ID = "stable:goals"
_STABLE_FACTS_BLOCK_ID = "stable:evidence_backed_facts"
_STABLE_ASSUMPTIONS_BLOCK_ID = "stable:questions_assumptions"
_PREVIOUS_ANSWER_ANCHOR_PREFIX = "answer_anchor="
_PREVIOUS_FORWARD_INTENT_PREFIX = "forward_intent="
_PREVIOUS_FORWARD_STATUS_PREFIX = "status="
_PREVIOUS_FORWARD_TEXT_PREFIX = "text="
_PREVIOUS_REFERENCE_PREFIX = "reference_continuity="
_PREVIOUS_REFERENCE_TEXT_PREFIX = "text="
_EVENT_TYPE_USER_INPUT_ACCEPTED = "USER_INPUT_ACCEPTED"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_EVENT_TYPE_TOOL_CALL_REQUESTED = "TOOL_CALL_REQUESTED"
_PAYLOAD_FIELD_DISPLAY_TEXT = "display_text"
_PAYLOAD_FIELD_ACCEPTED_CANDIDATE = "accepted_candidate"
_PAYLOAD_FIELD_ACCEPTED_CANDIDATE_DIGEST = "accepted_candidate_digest"
_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS = "accepted_evidence_mapping_refs"
_PAYLOAD_FIELD_SCHEMA_VERSION = "schema_version"
_PAYLOAD_FIELD_SESSION_SUMMARY = "session_summary"
_PAYLOAD_FIELD_SUMMARY_TEXT = "summary_text"
_PAYLOAD_FIELD_EVIDENCE_BACKED_FACTS = "evidence_backed_facts"
_PAYLOAD_FIELD_CLAIM_TEXT = "claim_text"
_PAYLOAD_FIELD_EVIDENCE_LABELS = "evidence_labels"
_PAYLOAD_FIELD_ANSWER_ANCHORS = "answer_anchors"
_PAYLOAD_FIELD_ANCHOR_TITLE = "anchor_title"
_PAYLOAD_FIELD_ANCHOR_ITEMS = "anchor_items"
_PAYLOAD_FIELD_DISPLAY_TEXT_CANDIDATE = "display_text"
_PAYLOAD_FIELD_ORDINAL = "ordinal"
_PAYLOAD_FIELD_FORWARD_INTENTS = "forward_intents"
_PAYLOAD_FIELD_INTENT_TYPE = "intent_type"
_PAYLOAD_FIELD_TEXT = "text"
_PAYLOAD_FIELD_STATUS = "status"
_PAYLOAD_FIELD_REFERENCE_CONTINUITY_ITEMS = "reference_continuity_items"
_PAYLOAD_FIELD_REASON = "reason"
_PAYLOAD_FIELD_SOURCE_LABELS = "source_labels"
_PAYLOAD_REF_PREFIX = "payload"
_PRE_DISPATCH_BUDGET_FRAGMENT_CURRENT_REF = "current_input_anchor"
_PRE_DISPATCH_BUDGET_FRAGMENT_PREVIOUS_PREFIX = "previous:"

_SECTION_PREFIXES = {
    CompactMaterialSection.CURRENT_INPUT_ANCHOR: _CURRENT_INPUT_PREFIX,
    CompactMaterialSection.TRACE_MATERIAL: _TRACE_PREFIX,
    CompactMaterialSection.EVIDENCE_MATERIAL: _EVIDENCE_PREFIX,
    CompactMaterialSection.PREVIOUS_COMPACTED_VIEW: _PREVIOUS_PREFIX,
    CompactMaterialSection.ANSWER_MATERIAL: _ANSWER_PREFIX,
}

_BLOCK_KIND_ORDER = {
    CompactMaterialBlockKind.EVIDENCE_BACKED_FACT: 0,
    CompactMaterialBlockKind.SESSION_SUMMARY: 0,
    CompactMaterialBlockKind.FORWARD_INTENT: 0,
    CompactMaterialBlockKind.REFERENCE_CONTINUITY: 0,
    CompactMaterialBlockKind.USER_INPUT: 1,
    CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER: 1,
    CompactMaterialBlockKind.USER_VISIBLE_RUN_STATE: 1,
    CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE: 2,
    CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR: 3,
}
_RECOVERY_PREVIOUS_VIEW_KIND_PRIORITY = (
    CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
    CompactMaterialBlockKind.REFERENCE_CONTINUITY,
    CompactMaterialBlockKind.ANSWER_ANCHOR,
    CompactMaterialBlockKind.FORWARD_INTENT,
    CompactMaterialBlockKind.SESSION_SUMMARY,
)


class CompactMaterialBuildError(ValueError):
    """Compact material pack build 的 typed error。"""


class DuplicateMaterialSectionOwnerError(CompactMaterialBuildError):
    """同一 canonical content 被映射到多个 LLM-facing section。"""


class CompactMemorySnapshotRepairRequired(CompactMaterialBuildError):
    """Compact material build 前需要 memory projection repair。

    :param repair_request: 需要执行的 memory projection repair 请求。
    """

    repair_request: MemoryRepairRequest
    requests_run_recovery: bool

    def __init__(self, repair_request: MemoryRepairRequest) -> None:
        """初始化 typed repair-required error。

        :param repair_request: repair 请求。
        :returns: ``None``。
        """

        self.repair_request = repair_request
        self.requests_run_recovery = False
        super().__init__(
            "compact memory snapshot repair required: "
            f"reason={repair_request.reason.value}, "
            f"session_id={repair_request.session_id}, "
            f"required_event_sequence={repair_request.required_event_sequence}"
        )


@dataclass(frozen=True, slots=True)
class RunInputMaterialBlock:
    """RunInputBuilder 与 compact builder 共用的 ordinary input material view。

    :param block_id: ordinary material list 中稳定 block id。
    :param section: block 的 compact section owner。
    :param kind: block kind。
    :param text: 有界可读文本。
    :param size_units: 文本尺寸估算。
    :param canonical_source_refs: canonical source refs。
    :param content_digest: 完整内容 digest。
    :param event_sequence: 来源 EventLog sequence；stable memory block 可为 ``None``。
    :param turn_group_id: Host admitted user Run id；stable semantic block 可为 ``None``。
    :param event_sub_index: 同一 event 内的稳定子序。
    :param source_labels: prompt-local source labels。
    :param already_represented: 是否已被 accepted compact output / stable fact 充分代表。
    :param protected_recent_raw_turn: 是否属于 recent raw turn floor。
    :param accepted_evidence_id: evidence block 的 canonical evidence id。
    :param tool_result_event_ref: evidence block 对应 TOOL_RESULT_ACCEPTED ref。
    :param tool_call_event_ref: evidence block 对应 TOOL_CALL_REQUESTED ref。
    :param payload_refs: evidence payload / artifact refs。
    :param artifact_refs: evidence artifact refs。
    :param source_locator_refs: evidence source locator refs。
    :param readable_tool_name: evidence block 的可读工具名。
    :param readable_query_text: evidence block 的可读查询文本。
    :param readable_source_text: evidence block 的可读来源文本。
    """

    block_id: str
    section: CompactMaterialSection
    kind: CompactMaterialBlockKind
    text: str
    size_units: int
    canonical_source_refs: tuple[str, ...]
    content_digest: str
    event_sequence: int | None
    turn_group_id: str | None = None
    event_sub_index: int = _DEFAULT_EVENT_SUB_INDEX
    source_labels: tuple[PromptLocalMaterialLabel, ...] = ()
    already_represented: bool = False
    protected_recent_raw_turn: bool = False
    accepted_evidence_id: str | None = None
    tool_result_event_ref: str | None = None
    tool_call_event_ref: str | None = None
    payload_refs: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    source_locator_refs: tuple[OpaqueEvidenceRef, ...] = ()
    readable_tool_name: str | None = None
    readable_query_text: str | None = None
    readable_source_text: str | None = None

    def __post_init__(self) -> None:
        """校验 ordinary input material block。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_non_empty_text(self.block_id, "RunInputMaterialBlock.block_id")
        if not isinstance(self.section, CompactMaterialSection):
            raise TypeError("RunInputMaterialBlock.section is invalid")
        if not isinstance(self.kind, CompactMaterialBlockKind):
            raise TypeError("RunInputMaterialBlock.kind is invalid")
        _require_non_empty_text(self.text, "RunInputMaterialBlock.text")
        if self.size_units < 0:
            raise ValueError("RunInputMaterialBlock.size_units must be non-negative")
        _require_string_tuple(
            self.canonical_source_refs,
            "RunInputMaterialBlock.canonical_source_refs",
        )
        _require_non_empty_text(self.content_digest, "RunInputMaterialBlock.content_digest")
        if self.event_sequence is not None and self.event_sequence < 0:
            raise ValueError("RunInputMaterialBlock.event_sequence must be non-negative")
        _require_optional_text(self.turn_group_id, "RunInputMaterialBlock.turn_group_id")
        if self.event_sub_index < 0:
            raise ValueError("RunInputMaterialBlock.event_sub_index must be non-negative")
        _require_string_tuple(self.source_labels, "RunInputMaterialBlock.source_labels")
        _require_optional_text(
            self.accepted_evidence_id,
            "RunInputMaterialBlock.accepted_evidence_id",
        )
        _require_optional_text(
            self.tool_result_event_ref,
            "RunInputMaterialBlock.tool_result_event_ref",
        )
        _require_optional_text(
            self.tool_call_event_ref,
            "RunInputMaterialBlock.tool_call_event_ref",
        )
        _require_string_tuple(self.payload_refs, "RunInputMaterialBlock.payload_refs")
        _require_string_tuple(self.artifact_refs, "RunInputMaterialBlock.artifact_refs")
        _require_opaque_evidence_ref_tuple(
            self.source_locator_refs,
            "RunInputMaterialBlock.source_locator_refs",
        )
        _require_optional_text(
            self.readable_tool_name,
            "RunInputMaterialBlock.readable_tool_name",
        )
        _require_optional_text(
            self.readable_query_text,
            "RunInputMaterialBlock.readable_query_text",
        )
        _require_optional_text(
            self.readable_source_text,
            "RunInputMaterialBlock.readable_source_text",
        )
        if self.section is CompactMaterialSection.EVIDENCE_MATERIAL:
            _require_non_empty_text(
                self.accepted_evidence_id,
                "RunInputMaterialBlock.accepted_evidence_id",
            )
            _require_non_empty_text(
                self.tool_result_event_ref,
                "RunInputMaterialBlock.tool_result_event_ref",
            )
            _require_non_empty_text(
                self.tool_call_event_ref,
                "RunInputMaterialBlock.tool_call_event_ref",
            )
            _require_non_empty_text(
                self.readable_tool_name,
                "RunInputMaterialBlock.readable_tool_name",
            )
            _require_non_empty_text(
                self.readable_query_text,
                "RunInputMaterialBlock.readable_query_text",
            )
            _require_non_empty_text(
                self.readable_source_text,
                "RunInputMaterialBlock.readable_source_text",
            )


@dataclass(frozen=True, slots=True)
class CompactMaterialSourceBoundary:
    """Pre-dispatch compact material 的 EventLog 来源边界诊断。

    :param latest_compacted_event_id: 当前输入前最新 accepted compact event id。
    :param latest_compacted_event_sequence: 当前输入前最新 accepted compact sequence。
    :param post_compact_delta_start_sequence: delta material 的包含式起点。
    :param post_compact_delta_end_sequence: delta material 的排他式终点。
    :param current_input_event_sequence: 当前输入 EventLog sequence 的诊断副本。
    """

    latest_compacted_event_id: str | None
    latest_compacted_event_sequence: int | None
    post_compact_delta_start_sequence: int
    post_compact_delta_end_sequence: int
    current_input_event_sequence: int

    def __post_init__(self) -> None:
        """校验 EventLog compact material source boundary。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_optional_text(
            self.latest_compacted_event_id,
            "CompactMaterialSourceBoundary.latest_compacted_event_id",
        )
        if self.latest_compacted_event_sequence is not None:
            if self.latest_compacted_event_sequence <= 0:
                raise ValueError("latest_compacted_event_sequence must be positive")
            if self.latest_compacted_event_id is None:
                raise ValueError("latest compacted id is required with sequence")
        if self.post_compact_delta_start_sequence <= 0:
            raise ValueError("post_compact_delta_start_sequence must be positive")
        if self.post_compact_delta_end_sequence <= 0:
            raise ValueError("post_compact_delta_end_sequence must be positive")
        if self.current_input_event_sequence <= 0:
            raise ValueError("current_input_event_sequence must be positive")
        if self.post_compact_delta_start_sequence > self.post_compact_delta_end_sequence:
            raise ValueError("post compact delta boundary is inverted")
        if self.post_compact_delta_end_sequence != self.current_input_event_sequence:
            raise ValueError("delta end sequence must equal current input sequence")


@dataclass(frozen=True, slots=True)
class PreDispatchCompactMaterialView:
    """EventLog-backed pre-dispatch compact material view。

    :param material_blocks: latest compact 后、当前输入前的 delta material blocks。
    :param previous_compacted_view: latest accepted compact candidate 映射出的 previous view。
    :param current_input_text: 当前 USER_INPUT_ACCEPTED display text。
    :param source_boundary: EventLog 来源边界诊断。
    :param latest_compacted_event_id: latest accepted compact event id 便捷诊断字段。
    :param latest_compacted_event_sequence: latest accepted compact sequence 便捷诊断字段。
    :param post_compact_delta_start_sequence: delta 起点便捷诊断字段。
    :param post_compact_delta_end_sequence: delta 终点便捷诊断字段。
    :param represented_evidence_refs: latest compact accepted mapping 覆盖的 evidence refs。
    :param budget_fragments: 与 material view 同源的预算文本片段。
    """

    material_blocks: tuple[RunInputMaterialBlock, ...]
    previous_compacted_view: tuple[CompactMaterialBlock, ...]
    current_input_text: str
    source_boundary: CompactMaterialSourceBoundary
    latest_compacted_event_id: str | None
    latest_compacted_event_sequence: int | None
    post_compact_delta_start_sequence: int
    post_compact_delta_end_sequence: int
    represented_evidence_refs: tuple[str, ...]
    budget_fragments: tuple[BudgetTextFragment, ...]

    def __post_init__(self) -> None:
        """校验 pre-dispatch compact material view。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_material_block_tuple(self.material_blocks, "material_blocks")
        _require_compact_material_block_tuple(
            self.previous_compacted_view,
            "previous_compacted_view",
        )
        _require_non_empty_text(self.current_input_text, "current_input_text")
        if not isinstance(self.source_boundary, CompactMaterialSourceBoundary):
            raise TypeError("source_boundary must be CompactMaterialSourceBoundary")
        if self.latest_compacted_event_id != self.source_boundary.latest_compacted_event_id:
            raise ValueError("latest compacted event id boundary mismatch")
        if (
            self.latest_compacted_event_sequence
            != self.source_boundary.latest_compacted_event_sequence
        ):
            raise ValueError("latest compacted event sequence boundary mismatch")
        if (
            self.post_compact_delta_start_sequence
            != self.source_boundary.post_compact_delta_start_sequence
        ):
            raise ValueError("post compact delta start boundary mismatch")
        if (
            self.post_compact_delta_end_sequence
            != self.source_boundary.post_compact_delta_end_sequence
        ):
            raise ValueError("post compact delta end boundary mismatch")
        _require_string_tuple(self.represented_evidence_refs, "represented_evidence_refs")
        _require_budget_fragment_tuple(self.budget_fragments, "budget_fragments")


def build_pre_dispatch_compact_material_view(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    run: RunRow,
    current_display_text: str,
) -> PreDispatchCompactMaterialView:
    """从 EventLog durable truth 构造 pre-dispatch compact material view。

    本 builder 只读取 EventLog、payload descriptor 与 artifact-backed payload
    truth，不读取 Conversation Memory snapshot，不伪造 snapshot，也不在 source
    builder 阶段用固定条数裁剪 post-compact delta 或 accepted evidence blocks。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog store。
    :param run: 当前 Run durable row。
    :param current_display_text: 当前 ``USER_INPUT_ACCEPTED`` display text。
    :returns: EventLog-backed pre-dispatch compact material view。
    :raises HostDurableError: EventLog 边界、payload 或 artifact truth 损坏时抛出。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: 参数值非法时抛出。
    """

    if not isinstance(run, RunRow):
        raise TypeError("run must be RunRow")
    _require_non_empty_text(current_display_text, "current_display_text")
    current_event = _validated_current_input_event(
        transaction,
        event_log_store,
        run=run,
        current_display_text=current_display_text,
    )
    latest_compact = _latest_compacted_event_before_current_input(
        transaction,
        event_log_store,
        session_id=run.session_id,
        before_event_sequence=run.input_event_sequence,
    )
    represented_refs = (
        ()
        if latest_compact is None
        else _accepted_evidence_mapping_refs_from_compacted_event(
            transaction,
            latest_compact,
        )
    )
    previous_view = (
        ()
        if latest_compact is None
        else _previous_compacted_view_from_compacted_event(
            transaction,
            latest_compact,
        )
    )
    delta_start = _post_compact_delta_start_sequence(
        transaction,
        session_id=run.session_id,
        current_input_sequence=current_event.event_sequence,
        latest_compacted_event=latest_compact,
    )
    delta_rows = _post_compact_delta_rows(
        transaction,
        session_id=run.session_id,
        start_sequence=delta_start,
        end_sequence=current_event.event_sequence,
    )
    material_blocks = _pre_dispatch_delta_material_blocks(
        transaction,
        event_log_store,
        rows=delta_rows,
        represented_evidence_refs=represented_refs,
    )
    boundary = CompactMaterialSourceBoundary(
        latest_compacted_event_id=None if latest_compact is None else latest_compact.event_id,
        latest_compacted_event_sequence=(
            None if latest_compact is None else latest_compact.event_sequence
        ),
        post_compact_delta_start_sequence=delta_start,
        post_compact_delta_end_sequence=current_event.event_sequence,
        current_input_event_sequence=current_event.event_sequence,
    )
    return PreDispatchCompactMaterialView(
        material_blocks=material_blocks,
        previous_compacted_view=previous_view,
        current_input_text=current_display_text,
        source_boundary=boundary,
        latest_compacted_event_id=boundary.latest_compacted_event_id,
        latest_compacted_event_sequence=boundary.latest_compacted_event_sequence,
        post_compact_delta_start_sequence=boundary.post_compact_delta_start_sequence,
        post_compact_delta_end_sequence=boundary.post_compact_delta_end_sequence,
        represented_evidence_refs=represented_refs,
        budget_fragments=_pre_dispatch_budget_fragments(
            previous_view=previous_view,
            material_blocks=material_blocks,
            current_input_text=current_display_text,
        ),
    )


def selected_material_source_refs(
    *,
    material_blocks: tuple[RunInputMaterialBlock, ...],
    selected_block_ids: tuple[str, ...],
) -> tuple[str, ...]:
    """返回 selected material blocks 覆盖的 canonical source refs。

    :param material_blocks: ordinary / frozen material blocks。
    :param selected_block_ids: segment selection 选中的 block ids。
    :returns: 去重后的 canonical source refs。
    """

    selected = frozenset(selected_block_ids)
    refs: list[str] = []
    for block in material_blocks:
        if block.block_id in selected:
            refs.extend(block.canonical_source_refs)
    return tuple(dict.fromkeys(refs))


def selected_material_view_digest(
    selected_blocks: tuple[RunInputMaterialBlock, ...],
) -> str:
    """计算 selected material view 的稳定 digest。

    :param selected_blocks: 已按 material view 顺序选中的 blocks。
    :returns: selected view digest。
    :raises TypeError: 参数类型非法时抛出。
    """

    _require_material_block_tuple(selected_blocks, "selected_blocks")
    return sha256_digest_json(
        {
            "selected_blocks": [
                {
                    "block_id": block.block_id,
                    "canonical_source_refs": list(block.canonical_source_refs),
                    "content_digest": block.content_digest,
                }
                for block in selected_blocks
            ]
        }
    )


def conversation_compact_input_vnext_from_material_pack(
    material_pack: CompactMaterialPack,
) -> ConversationCompactInputVNext:
    """从 compact material pack 构造 vNext LLM-readable input。

    :param material_pack: production vNext material pack。
    :returns: vNext compactor input。
    :raises TypeError: material pack 类型非法时抛出。
    """

    if not isinstance(material_pack, CompactMaterialPack):
        raise TypeError("material_pack must be CompactMaterialPack")
    return ConversationCompactInputVNext(
        schema_version=CONVERSATION_COMPACT_INPUT_SCHEMA_VERSION_VNEXT,
        previous_compacted_view=_previous_compacted_view_vnext(material_pack.previous_compacted_view),
        trace_material=_trace_material_vnext(material_pack.trace_material),
        evidence_material=_evidence_material_vnext(material_pack.evidence_material),
        answer_material=_answer_material_vnext(material_pack.answer_material),
        current_input_anchor=CurrentInputAnchorVNext(
            anchor_label=material_pack.current_input_anchor.anchor_label,
            text=material_pack.current_input_anchor.anchor_text,
        ),
        instruction=CompactInstructionVNext(),
    )


@dataclass(frozen=True, slots=True)
class InlineDeltaRepairMaterialView:
    """Material pack build 可消费的 inline delta repair view。

    :param snapshot: inline delta 修复后的临时 memory snapshot。
    :param diagnostics: inline repair 诊断。
    """

    snapshot: ConversationMemorySnapshotVNext
    diagnostics: tuple[MemoryDiagnostic, ...]


class SnapshotCursorCheckKind(StrEnum):
    """Compact memory snapshot cursor 校验结果类型。"""

    READY = "ready"
    INLINE_DELTA_REPAIR = "inline_delta_repair"


@dataclass(frozen=True, slots=True)
class SnapshotCursorCheckResult:
    """Compact material build 前的 snapshot cursor 校验结果。

    :param kind: 校验结果类型。
    :param snapshot: ready 或 inline repair 后可用的 snapshot。
    :param inline_delta_repair_view: inline repair view；ready 时为 ``None``。
    :param requests_run_recovery: 是否要求 Run recovery；本 helper 永远为 ``False``。
    """

    kind: SnapshotCursorCheckKind
    snapshot: ConversationMemorySnapshotVNext
    inline_delta_repair_view: InlineDeltaRepairMaterialView | None
    requests_run_recovery: bool = False


@dataclass(frozen=True, slots=True)
class InitialHistoryMaterial:
    """初始 trace material。

    :param canonical_source_ref: canonical source ref。
    :param text: 有界可读文本。
    :param kind: history block kind。
    """

    canonical_source_ref: str
    text: str
    kind: CompactMaterialBlockKind


@dataclass(frozen=True, slots=True)
class InitialEvidenceMaterial:
    """初始 evidence material。

    :param canonical_source_ref: canonical source ref。
    :param accepted_evidence_id: canonical accepted evidence id。
    :param tool_result_event_ref: TOOL_RESULT_ACCEPTED event ref。
    :param tool_call_event_ref: TOOL_CALL_REQUESTED event ref。
    :param readable_tool_name: LLM 可读工具名。
    :param readable_query_text: LLM 可读查询文本。
    :param raw_result_text: raw evidence 文本。
    :param readable_source_text: LLM 可读来源文本。
    :param payload_refs: payload / artifact refs。
    :param artifact_refs: artifact refs。
    :param source_locator_refs: source locator refs。
    """

    canonical_source_ref: str
    accepted_evidence_id: str
    tool_result_event_ref: str
    tool_call_event_ref: str
    readable_tool_name: str
    readable_query_text: str
    raw_result_text: str
    readable_source_text: str
    payload_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...] = ()
    source_locator_refs: tuple[OpaqueEvidenceRef, ...] = ()


def material_label(section: CompactMaterialSection, ordinal: int) -> PromptLocalMaterialLabel:
    """构造普通 prompt-local material label。

    :param section: material section。
    :param ordinal: 同 section 内从 1 开始的 ordinal。
    :returns: prompt-local label。
    :raises TypeError: section 类型非法时抛出。
    :raises ValueError: ordinal 非法时抛出。
    """

    if not isinstance(section, CompactMaterialSection):
        raise TypeError("section must be CompactMaterialSection")
    if ordinal < _FIRST_ORDINAL:
        raise ValueError("ordinal must be positive")
    return f"{_SECTION_PREFIXES[section]}{ordinal}"


def current_input_anchor_label() -> PromptLocalMaterialLabel:
    """返回 current input anchor label。

    :returns: ``C1``。
    """

    return material_label(
        CompactMaterialSection.CURRENT_INPUT_ANCHOR,
        _CURRENT_ANCHOR_ORDINAL,
    )


def validate_material_label(label: PromptLocalMaterialLabel, section: CompactMaterialSection) -> None:
    """校验 prompt-local label 与 section 是否匹配。

    :param label: 待校验 label。
    :param section: 期望 material section。
    :returns: ``None``。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: label 与 section 不匹配时抛出。
    """

    if not isinstance(label, str):
        raise TypeError("label must be str")
    if not isinstance(section, CompactMaterialSection):
        raise TypeError("section must be CompactMaterialSection")
    prefix = _SECTION_PREFIXES[section]
    if not label.startswith(prefix):
        raise ValueError("label section prefix mismatch")
    ordinal_text = label.removeprefix(prefix)
    if _LABEL_CHUNK_SEPARATOR in ordinal_text:
        parent, chunk = ordinal_text.split(_LABEL_CHUNK_SEPARATOR, maxsplit=1)
        if section is not CompactMaterialSection.EVIDENCE_MATERIAL:
            raise ValueError("chunk label only belongs to evidence section")
        _validate_positive_decimal(parent)
        _validate_positive_decimal(chunk)
        return
    _validate_positive_decimal(ordinal_text)


def normalized_material_text(text: str) -> str:
    """规范化 material 可读文本。

    :param text: 原始文本。
    :returns: 去除首尾空白、折叠行内连续空白并保留非空行边界后的文本。
    :raises TypeError: 文本类型非法时抛出。
    :raises ValueError: 规范化后为空时抛出。
    """

    if not isinstance(text, str):
        raise TypeError("text must be str")
    normalized_lines = tuple(
        _normalized_material_line(line)
        for line in text.splitlines()
    )
    normalized = "\n".join(line for line in normalized_lines if line != "")
    if normalized == "":
        raise ValueError("text must be non-empty after normalization")
    return normalized


def _normalized_material_line(text: str) -> str:
    """规范化单行 material 文本。

    :param text: 原始单行文本。
    :returns: 去除首尾空白并折叠连续空白后的文本。
    """

    return " ".join(text.split())


def _normalized_structured_field_text(text: str) -> str:
    """把结构化 previous view 字段规范化为单行文本。

    :param text: 字段原始文本。
    :returns: 单行字段文本。
    :raises TypeError: 文本类型非法时抛出。
    :raises ValueError: 规范化后为空时抛出。
    """

    if not isinstance(text, str):
        raise TypeError("text must be str")
    normalized = _normalized_material_line(text)
    if normalized == "":
        raise ValueError("text must be non-empty after normalization")
    return normalized


def run_input_material_block(
    *,
    block_id: str,
    section: CompactMaterialSection,
    kind: CompactMaterialBlockKind,
    text: str,
    canonical_source_refs: tuple[str, ...],
    event_sequence: int | None,
    turn_group_id: str | None = None,
    event_sub_index: int = _DEFAULT_EVENT_SUB_INDEX,
    source_labels: tuple[PromptLocalMaterialLabel, ...] = (),
    already_represented: bool = False,
    protected_recent_raw_turn: bool = False,
    accepted_evidence_id: str | None = None,
    tool_result_event_ref: str | None = None,
    tool_call_event_ref: str | None = None,
    payload_refs: tuple[str, ...] = (),
    artifact_refs: tuple[str, ...] = (),
    source_locator_refs: tuple[OpaqueEvidenceRef, ...] = (),
    readable_tool_name: str | None = None,
    readable_query_text: str | None = None,
    readable_source_text: str | None = None,
) -> RunInputMaterialBlock:
    """构造共享 ordinary input material block。

    :param block_id: ordinary material list 稳定 block id。
    :param section: compact section owner。
    :param kind: material kind。
    :param text: 原始或已规范化文本。
    :param canonical_source_refs: canonical source refs。
    :param event_sequence: 来源 EventLog sequence；stable block 可为 ``None``。
    :param turn_group_id: Host admitted user Run id；stable semantic block 可为 ``None``。
    :param event_sub_index: 同 event 内稳定子序。
    :param source_labels: prompt-local source labels。
    :param already_represented: 是否已被 compact output / stable fact 代表。
    :param protected_recent_raw_turn: 是否属于 recent raw floor。
    :param accepted_evidence_id: evidence block 的 canonical evidence id。
    :param tool_result_event_ref: evidence block 的 TOOL_RESULT_ACCEPTED ref。
    :param tool_call_event_ref: evidence block 的 TOOL_CALL_REQUESTED ref。
    :param payload_refs: payload / artifact refs。
    :param artifact_refs: artifact refs。
    :param source_locator_refs: source locator refs。
    :param readable_tool_name: evidence block 可读工具名。
    :param readable_query_text: evidence block 可读查询文本。
    :param readable_source_text: evidence block 可读来源文本。
    :returns: RunInputMaterialBlock。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: 参数值非法时抛出。
    """

    normalized = normalized_material_text(text)
    return RunInputMaterialBlock(
        block_id=block_id,
        section=section,
        kind=kind,
        text=normalized,
        size_units=len(normalized),
        canonical_source_refs=canonical_source_refs,
        content_digest=_text_digest(normalized),
        event_sequence=event_sequence,
        turn_group_id=turn_group_id,
        event_sub_index=event_sub_index,
        source_labels=source_labels,
        already_represented=already_represented,
        protected_recent_raw_turn=protected_recent_raw_turn,
        accepted_evidence_id=accepted_evidence_id,
        tool_result_event_ref=tool_result_event_ref,
        tool_call_event_ref=tool_call_event_ref,
        payload_refs=payload_refs,
        artifact_refs=artifact_refs,
        source_locator_refs=source_locator_refs,
        readable_tool_name=readable_tool_name,
        readable_query_text=readable_query_text,
        readable_source_text=readable_source_text,
    )


def select_compact_segment(
    *,
    trigger_source: CompactSegmentTrigger,
    input_cursor: int,
    memory_snapshot_cursor: int | None,
    policy_digest: str,
    material_blocks: tuple[RunInputMaterialBlock, ...],
    selected_recent_window_turn_floor: int = 0,
    max_selected_size_units: int | None = None,
    max_selected_item_count: int | None = None,
) -> CompactSegmentSelection:
    """按确定性规则选择 compact segment。

    :param trigger_source: proactive 或 reactive 触发来源。
    :param input_cursor: ordinary input material list 最大 EventLog cursor。
    :param memory_snapshot_cursor: memory snapshot cursor。
    :param policy_digest: context / memory policy digest。
    :param material_blocks: ordinary input 或 frozen overflow material list。
    :param selected_recent_window_turn_floor: 需要保护的 selected recent-window turn 数量。
    :param max_selected_size_units: 可选 selected segment 尺寸上限。
    :param max_selected_item_count: 可选 selected segment item 数量上限。
    :returns: CompactSegmentSelection。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: 参数值非法时抛出。
    """

    _validate_selection_inputs(
        trigger_source=trigger_source,
        input_cursor=input_cursor,
        memory_snapshot_cursor=memory_snapshot_cursor,
        policy_digest=policy_digest,
        material_blocks=material_blocks,
        selected_recent_window_turn_floor=selected_recent_window_turn_floor,
        max_selected_size_units=max_selected_size_units,
        max_selected_item_count=max_selected_item_count,
    )
    protected_recent_ids = _protected_recent_turn_group_block_ids(
        material_blocks,
        selected_recent_window_turn_floor,
    )
    selected: list[str] = []
    excluded_reasons: dict[str, str] = {}
    selected_units = 0
    budget_blocked = False
    for block in _sorted_material_blocks(material_blocks, memory_snapshot_cursor=memory_snapshot_cursor):
        if budget_blocked:
            excluded_reasons[block.block_id] = _REASON_BUDGET_LIMIT
            continue
        reason = _block_exclusion_reason(block, protected_recent_ids)
        if reason is not None:
            excluded_reasons[block.block_id] = reason
            continue
        if (
            max_selected_size_units is not None
            and selected_units + block.size_units > max_selected_size_units
            and (len(selected) > 0 or max_selected_item_count is not None)
        ):
            excluded_reasons[block.block_id] = _REASON_BUDGET_LIMIT
            if max_selected_item_count is not None:
                budget_blocked = True
            continue
        if max_selected_item_count is not None and len(selected) >= max_selected_item_count:
            excluded_reasons[block.block_id] = _REASON_BUDGET_LIMIT
            budget_blocked = True
            continue
        selected.append(block.block_id)
        selected_units += block.size_units
    protected_ids = tuple(
        block_id
        for block_id, reason in excluded_reasons.items()
        if reason
        in (
            _REASON_PROTECTED_CURRENT_INPUT,
            _REASON_PROTECTED_RECENT_RAW_FLOOR,
        )
    )
    reason_codes = _selection_reason_codes(
        selected=tuple(selected),
        excluded_reasons=excluded_reasons,
    )
    digest_input = {
        "selected_block_ids": selected,
        "excluded_protected_ids": list(protected_ids),
        "excluded_reason_codes": _ordered_reason_mapping(excluded_reasons),
        "trigger_source": trigger_source.value,
        "input_cursor": input_cursor,
        "memory_snapshot_cursor": memory_snapshot_cursor,
        "policy_digest": policy_digest,
        "deterministic_reason_codes": list(reason_codes),
    }
    return CompactSegmentSelection(
        selected_block_ids=tuple(selected),
        excluded_protected_ids=protected_ids,
        trigger_source=trigger_source,
        input_cursor=input_cursor,
        memory_snapshot_cursor=memory_snapshot_cursor,
        policy_digest=policy_digest,
        deterministic_reason_codes=reason_codes,
        selection_digest=sha256_digest_json(digest_input),
        excluded_reason_codes=excluded_reasons,
    )


def degrade_previous_compacted_view_for_recovery(
    previous_compacted_view: tuple[CompactMaterialBlock, ...]
) -> tuple[CompactMaterialBlock, ...]:
    """按 S4 recovery 优先级对 latest accepted compacted view 做 whole-drop 降级。

    该 helper 只保留最高优先级的非空 semantic section，并按确定性顺序返回
    原始 block；不会截断、改写、重写摘要或合成新的 semantic memory。

    :param previous_compacted_view: latest accepted compacted view blocks。
    :returns: 降级后的 previous compacted view blocks；无可保留项时为空元组。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: 参数值非法时抛出。
    """

    _require_compact_material_block_tuple(
        previous_compacted_view,
        "previous_compacted_view",
    )
    for kind in _RECOVERY_PREVIOUS_VIEW_KIND_PRIORITY:
        candidates = tuple(
            (index, block)
            for index, block in enumerate(previous_compacted_view)
            if block.kind is kind
        )
        if len(candidates) > 0:
            return tuple(block for _index, block in _sort_recovery_previous_blocks(candidates))
    return ()


def build_compact_material_pack(
    *,
    selected_segment: CompactSegmentSelection,
    material_blocks: tuple[RunInputMaterialBlock, ...],
    memory_snapshot: ConversationMemorySnapshotVNext | None,
    inline_delta_repair_view: InlineDeltaRepairMaterialView | None,
    current_input_ref: str,
    current_input_text: str,
    previous_compacted_view: tuple[CompactMaterialBlock, ...] | None = None,
) -> CompactMaterialPack:
    """从 selected segment 和 memory view 构造 compact material pack。

    :param selected_segment: segment selection 输出。
    :param material_blocks: 与 selection 同源的 ordinary / frozen material list。
    :param memory_snapshot: ready memory snapshot；无 stable view 时可为 ``None``。
    :param inline_delta_repair_view: inline delta repair view；无 repair 时为 ``None``。
    :param current_input_ref: 当前 USER_INPUT_ACCEPTED canonical ref。
    :param current_input_text: 当前用户输入 display text。
    :param previous_compacted_view: 显式 previous view；``None`` 时走既有 snapshot path。
    :returns: CompactMaterialPack。
    :raises DuplicateMaterialSectionOwnerError: 同一 canonical content 跨 section 重复时抛出。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: 参数值非法时抛出。
    """

    if not isinstance(selected_segment, CompactSegmentSelection):
        raise TypeError("selected_segment must be CompactSegmentSelection")
    _require_material_block_tuple(material_blocks, "material_blocks")
    _require_non_empty_text(current_input_ref, "current_input_ref")
    snapshot = _effective_snapshot(memory_snapshot, inline_delta_repair_view)
    current_anchor = _current_input_anchor(current_input_ref, current_input_text)
    selected_blocks = _selected_material_blocks(
        selected_segment.selected_block_ids,
        material_blocks,
        current_anchor=current_anchor,
    )
    if previous_compacted_view is None:
        previous_blocks = _previous_blocks_from_snapshot(snapshot)
    else:
        _require_compact_material_block_tuple(
            previous_compacted_view,
            "previous_compacted_view",
        )
        previous_blocks = previous_compacted_view
    trace_blocks = _pack_section_blocks(selected_blocks, CompactMaterialSection.TRACE_MATERIAL)
    evidence_blocks = _pack_evidence_blocks(selected_blocks)
    answer_blocks = _pack_section_blocks(selected_blocks, CompactMaterialSection.ANSWER_MATERIAL)
    provenance_entries = (
        *_provenance_from_blocks(previous_blocks),
        *_provenance_from_blocks(trace_blocks),
        *_provenance_from_evidence_blocks(selected_blocks),
        *_provenance_from_blocks(answer_blocks),
        _current_anchor_provenance(current_anchor),
    )
    _raise_on_duplicate_section_owner(provenance_entries)
    return CompactMaterialPack(
        previous_compacted_view=previous_blocks,
        trace_material=trace_blocks,
        evidence_material=evidence_blocks,
        answer_material=answer_blocks,
        current_input_anchor=current_anchor,
        provenance_map={entry.label: entry for entry in provenance_entries},
    )


def prompt_local_evidence_map(
    material_pack: CompactMaterialPack,
) -> PromptLocalEvidenceMap:
    """返回并校验 evidence-only prompt-local provenance view。

    :param material_pack: compact material pack。
    :returns: evidence label 到 canonical provenance entry 的只读 typed view。
    :raises TypeError: material_pack 类型非法时抛出。
    :raises ValueError: evidence entry 缺少 canonical evidence / tool / payload
        或 artifact provenance 时抛出。
    """

    if not isinstance(material_pack, CompactMaterialPack):
        raise TypeError("material_pack must be CompactMaterialPack")
    evidence_map = material_pack.evidence_map()
    for label, entry in evidence_map.items():
        validate_material_label(label, CompactMaterialSection.EVIDENCE_MATERIAL)
        if entry.section is not CompactMaterialSection.EVIDENCE_MATERIAL:
            raise ValueError("evidence map contains non-evidence entry")
        _require_non_empty_text(
            entry.accepted_evidence_id,
            "PromptLocalEvidenceMap.accepted_evidence_id",
        )
        _require_non_empty_text(
            entry.tool_result_event_ref,
            "PromptLocalEvidenceMap.tool_result_event_ref",
        )
        _require_non_empty_text(
            entry.tool_call_event_ref,
            "PromptLocalEvidenceMap.tool_call_event_ref",
        )
        if len(entry.payload_refs) == 0 and len(entry.artifact_refs) == 0:
            raise ValueError("PromptLocalEvidenceMap requires payload or artifact refs")
    return evidence_map


def check_compact_memory_snapshot_cursor(
    *,
    session_id: str,
    required_event_sequence: int,
    policy: MemoryProjectionPolicy,
    snapshot: ConversationMemorySnapshotVNext | None,
    inline_delta_repair_view: InlineDeltaRepairMaterialView | None = None,
) -> SnapshotCursorCheckResult:
    """校验 compact material build 前的 memory snapshot cursor。

    :param session_id: Session id。
    :param required_event_sequence: material build 需要覆盖的 EventLog cursor。
    :param policy: memory projection policy。
    :param snapshot: 已读取的 memory snapshot。
    :param inline_delta_repair_view: 可选 inline delta repair view。
    :returns: ready 或 inline repair 后的 snapshot cursor check result。
    :raises CompactMemorySnapshotRepairRequired: 缺失、损坏或 lag 超阈值时抛出。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: 参数值非法时抛出。
    """

    _require_non_empty_text(session_id, "session_id")
    if required_event_sequence < 0:
        raise ValueError("required_event_sequence must be non-negative")
    if not isinstance(policy, MemoryProjectionPolicy):
        raise TypeError("policy must be MemoryProjectionPolicy")
    policy_digest = digest_memory_projection_policy(policy)
    if snapshot is None:
        _raise_snapshot_repair_required(
            session_id=session_id,
            reason=MemoryRepairReason.SNAPSHOT_MISSING,
            required_event_sequence=required_event_sequence,
            observed_cursor=None,
            policy_digest=policy_digest,
        )
    _validate_snapshot_session(
        snapshot,
        session_id=session_id,
        required_event_sequence=required_event_sequence,
        policy_digest=policy_digest,
    )
    lag_events = required_event_sequence - snapshot.cursor.checkpoint_event_sequence
    if lag_events < 0:
        _raise_snapshot_repair_required(
            session_id=session_id,
            reason=MemoryRepairReason.SNAPSHOT_AHEAD_OF_REQUIRED,
            required_event_sequence=required_event_sequence,
            observed_cursor=snapshot.cursor,
            policy_digest=policy_digest,
        )
    if lag_events <= 0:
        return SnapshotCursorCheckResult(
            kind=SnapshotCursorCheckKind.READY,
            snapshot=snapshot,
            inline_delta_repair_view=None,
        )
    if lag_events > policy.max_lag_events_for_inline_delta:
        _raise_snapshot_repair_required(
            session_id=session_id,
            reason=MemoryRepairReason.SNAPSHOT_LAG_OVER_THRESHOLD,
            required_event_sequence=required_event_sequence,
            observed_cursor=snapshot.cursor,
            policy_digest=policy_digest,
        )
    if inline_delta_repair_view is None:
        _raise_snapshot_repair_required(
            session_id=session_id,
            reason=MemoryRepairReason.INLINE_DELTA_REPAIR_VIEW_MISSING,
            required_event_sequence=required_event_sequence,
            observed_cursor=snapshot.cursor,
            policy_digest=policy_digest,
        )
    repaired = inline_delta_repair_view.snapshot
    _validate_snapshot_session(
        repaired,
        session_id=session_id,
        required_event_sequence=required_event_sequence,
        policy_digest=policy_digest,
    )
    if repaired.cursor.checkpoint_event_sequence < required_event_sequence:
        _raise_snapshot_repair_required(
            session_id=session_id,
            reason=MemoryRepairReason.SNAPSHOT_LAG_OVER_THRESHOLD,
            required_event_sequence=required_event_sequence,
            observed_cursor=repaired.cursor,
            policy_digest=policy_digest,
        )
    return SnapshotCursorCheckResult(
        kind=SnapshotCursorCheckKind.INLINE_DELTA_REPAIR,
        snapshot=repaired,
        inline_delta_repair_view=inline_delta_repair_view,
    )


def build_initial_material_pack(
    *,
    current_input_ref: str,
    current_input_text: str,
    history_materials: tuple[InitialHistoryMaterial, ...],
    evidence_materials: tuple[InitialEvidenceMaterial, ...],
) -> CompactMaterialPack:
    """构造初始 compact material pack。

    :param current_input_ref: 当前输入 canonical source ref。
    :param current_input_text: 当前输入有界文本。
    :param history_materials: 初始 history material。
    :param evidence_materials: 初始 evidence material。
    :returns: compact material pack。
    :raises ValueError: 文本或 ref 非法时由 typed contract 抛出。
    """

    previous_blocks: tuple[CompactMaterialBlock, ...] = ()
    ordinary_blocks = _history_blocks(history_materials)
    trace_blocks = tuple(block for block in ordinary_blocks if block.section is CompactMaterialSection.TRACE_MATERIAL)
    answer_blocks = tuple(block for block in ordinary_blocks if block.section is CompactMaterialSection.ANSWER_MATERIAL)
    evidence_blocks = _evidence_blocks(evidence_materials)
    current_anchor = CurrentInputAnchor(
        anchor_label=current_input_anchor_label(),
        anchor_text=current_input_text,
        truncated=False,
        canonical_source_refs=(current_input_ref,),
        content_digest=_text_digest(current_input_text),
    )
    provenance_entries = [
        _current_anchor_provenance(current_anchor),
        *_history_provenance(trace_blocks),
        *_history_provenance(answer_blocks),
        *_evidence_provenance(evidence_materials),
    ]
    provenance_map = {entry.label: entry for entry in provenance_entries}
    return CompactMaterialPack(
        previous_compacted_view=previous_blocks,
        trace_material=trace_blocks,
        evidence_material=evidence_blocks,
        answer_material=answer_blocks,
        current_input_anchor=current_anchor,
        provenance_map=provenance_map,
    )


def initial_segment_selection(
    *,
    trigger_source: CompactSegmentTrigger,
    input_cursor: int,
    material_pack: CompactMaterialPack,
) -> CompactSegmentSelection:
    """构造初始 segment selection。

    :param trigger_source: compact trigger。
    :param input_cursor: 当前输入 cursor。
    :param material_pack: 已构造 material pack。
    :returns: segment selection。
    """

    selected = material_pack.all_labels
    reasons = _initial_reason_codes(material_pack)
    digest = sha256_digest_json(
        {
            "selected_block_ids": list(selected),
            "trigger_source": trigger_source.value,
            "input_cursor": input_cursor,
            "policy_digest": _INITIAL_POLICY_DIGEST,
            "deterministic_reason_codes": list(reasons),
        }
    )
    return CompactSegmentSelection(
        selected_block_ids=selected,
        excluded_protected_ids=(),
        trigger_source=trigger_source,
        input_cursor=input_cursor,
        memory_snapshot_cursor=None,
        policy_digest=_INITIAL_POLICY_DIGEST,
        deterministic_reason_codes=reasons,
        selection_digest=digest,
    )


def _history_blocks(materials: tuple[InitialHistoryMaterial, ...]) -> tuple[CompactMaterialBlock, ...]:
    """把初始普通 material 转为 typed blocks。

    :param materials: 初始普通 material。
    :returns: material block tuple。
    """

    blocks: list[CompactMaterialBlock] = []
    section_ordinals: dict[CompactMaterialSection, int] = {}
    for material in materials:
        section = _initial_material_section(material.kind)
        ordinal = section_ordinals.get(section, 0) + 1
        section_ordinals[section] = ordinal
        blocks.append(
            CompactMaterialBlock(
                block_label=material_label(
                    section,
                    ordinal,
                ),
                section=section,
                kind=material.kind,
                text=material.text,
                size_units=len(material.text),
                source_labels=(),
                canonical_source_refs=(material.canonical_source_ref,),
                content_digest=_text_digest(material.text),
            )
        )
    return tuple(blocks)


def _initial_material_section(kind: CompactMaterialBlockKind) -> CompactMaterialSection:
    """按 vNext kind 决定初始普通 material section。

    :param kind: material kind。
    :returns: vNext material section。
    :raises TypeError: kind 类型非法时抛出。
    """

    if not isinstance(kind, CompactMaterialBlockKind):
        raise TypeError("kind must be CompactMaterialBlockKind")
    if kind is CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER:
        return CompactMaterialSection.ANSWER_MATERIAL
    return CompactMaterialSection.TRACE_MATERIAL


def _evidence_blocks(materials: tuple[InitialEvidenceMaterial, ...]) -> tuple[CompactEvidenceBlock, ...]:
    """把初始 evidence material 转为 typed blocks。

    :param materials: 初始 evidence material。
    :returns: evidence block tuple。
    """

    blocks: list[CompactEvidenceBlock] = []
    for index, material in enumerate(materials, start=_FIRST_ORDINAL):
        _require_non_empty_text(material.raw_result_text, "raw_result_text")
        blocks.append(
            CompactEvidenceBlock(
                evidence_label=material_label(CompactMaterialSection.EVIDENCE_MATERIAL, index),
                readable_tool_name=material.readable_tool_name,
                readable_query_text=material.readable_query_text,
                raw_result_text=material.raw_result_text,
                readable_source_text=material.readable_source_text,
                size_units=len(material.raw_result_text),
                canonical_source_refs=(material.canonical_source_ref,),
                content_digest=_text_digest(material.raw_result_text),
            )
        )
    return tuple(blocks)


def _current_anchor_provenance(
    anchor: CurrentInputAnchor,
) -> PromptLocalProvenanceEntry:
    """构造 current anchor provenance entry。

    :param anchor: current input anchor。
    :returns: provenance entry。
    """

    return PromptLocalProvenanceEntry(
        label=anchor.anchor_label,
        section=CompactMaterialSection.CURRENT_INPUT_ANCHOR,
        kind=CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR,
        canonical_source_refs=anchor.canonical_source_refs,
        source_event_refs=anchor.canonical_source_refs,
        content_digest=anchor.content_digest,
        accepted_evidence_id=None,
        tool_result_event_ref=None,
        tool_call_event_ref=None,
        payload_refs=(),
        artifact_refs=(),
        source_locator_refs=(),
    )


def _history_provenance(blocks: tuple[CompactMaterialBlock, ...]) -> tuple[PromptLocalProvenanceEntry, ...]:
    """构造 history block provenance entries。

    :param blocks: history blocks。
    :returns: provenance entries。
    """

    entries: list[PromptLocalProvenanceEntry] = []
    for block in blocks:
        entries.append(
            PromptLocalProvenanceEntry(
                label=block.block_label,
                section=block.section,
                kind=block.kind,
                canonical_source_refs=block.canonical_source_refs,
                source_event_refs=block.canonical_source_refs,
                content_digest=block.content_digest,
                accepted_evidence_id=None,
                tool_result_event_ref=None,
                tool_call_event_ref=None,
                payload_refs=(),
                artifact_refs=(),
                source_locator_refs=(),
            )
        )
    return tuple(entries)


def _evidence_provenance(
    materials: tuple[InitialEvidenceMaterial, ...],
) -> tuple[PromptLocalProvenanceEntry, ...]:
    """构造 evidence block provenance entries。

    :param materials: 初始 evidence material。
    :returns: provenance entries。
    """

    entries: list[PromptLocalProvenanceEntry] = []
    for index, material in enumerate(materials, start=_FIRST_ORDINAL):
        _require_non_empty_text(material.raw_result_text, "raw_result_text")
        entries.append(
            PromptLocalProvenanceEntry(
                label=material_label(CompactMaterialSection.EVIDENCE_MATERIAL, index),
                section=CompactMaterialSection.EVIDENCE_MATERIAL,
                kind=CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
                canonical_source_refs=(material.canonical_source_ref,),
                source_event_refs=(material.tool_result_event_ref,),
                content_digest=_text_digest(material.raw_result_text),
                accepted_evidence_id=material.accepted_evidence_id,
                tool_result_event_ref=material.tool_result_event_ref,
                tool_call_event_ref=material.tool_call_event_ref,
                payload_refs=material.payload_refs,
                artifact_refs=material.artifact_refs,
                source_locator_refs=material.source_locator_refs,
            )
        )
    return tuple(entries)


def _initial_reason_codes(pack: CompactMaterialPack) -> tuple[str, ...]:
    """构造初始 material reason codes。

    :param pack: material pack。
    :returns: reason code tuple。
    """

    reasons: list[str] = [_INITIAL_REASON_CURRENT]
    if len(pack.previous_compacted_view) > 0:
        reasons.append(_INITIAL_REASON_PREVIOUS)
    if len(pack.trace_material) > 0:
        reasons.append(_INITIAL_REASON_TRACE)
    if len(pack.evidence_material) > 0:
        reasons.append(_INITIAL_REASON_EVIDENCE)
    if len(pack.answer_material) > 0:
        reasons.append(_INITIAL_REASON_ANSWER)
    return tuple(reasons)


def _validate_positive_decimal(value: str) -> None:
    """校验正整数十进制文本。

    :param value: 待校验文本。
    :returns: ``None``。
    :raises ValueError: 文本不是正整数时抛出。
    """

    if not value.isdecimal():
        raise ValueError("label ordinal must be decimal")
    if int(value) < _FIRST_ORDINAL:
        raise ValueError("label ordinal must be positive")


def _text_digest(text: str) -> str:
    """计算文本 digest。

    :param text: 文本。
    :returns: sha256 digest。
    """

    return sha256_digest_json({"text": text})


def _validate_selection_inputs(
    *,
    trigger_source: CompactSegmentTrigger,
    input_cursor: int,
    memory_snapshot_cursor: int | None,
    policy_digest: str,
    material_blocks: tuple[RunInputMaterialBlock, ...],
    selected_recent_window_turn_floor: int,
    max_selected_size_units: int | None,
    max_selected_item_count: int | None,
) -> None:
    """校验 segment selection 输入。

    :param trigger_source: 触发来源。
    :param input_cursor: 输入 cursor。
    :param memory_snapshot_cursor: memory snapshot cursor。
    :param policy_digest: policy digest。
    :param material_blocks: material blocks。
    :param selected_recent_window_turn_floor: protected selected recent-window turn floor。
    :param max_selected_size_units: 可选选择预算。
    :param max_selected_item_count: 可选选择 item 数量上限。
    :returns: ``None``。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: 参数值非法时抛出。
    """

    if not isinstance(trigger_source, CompactSegmentTrigger):
        raise TypeError("trigger_source must be CompactSegmentTrigger")
    if input_cursor < 0:
        raise ValueError("input_cursor must be non-negative")
    if memory_snapshot_cursor is not None and memory_snapshot_cursor < 0:
        raise ValueError("memory_snapshot_cursor must be non-negative")
    _require_non_empty_text(policy_digest, "policy_digest")
    _require_material_block_tuple(material_blocks, "material_blocks")
    if selected_recent_window_turn_floor < 0:
        raise ValueError("selected_recent_window_turn_floor must be non-negative")
    if max_selected_size_units is not None and max_selected_size_units < 0:
        raise ValueError("max_selected_size_units must be non-negative")
    if max_selected_item_count is not None and max_selected_item_count < 0:
        raise ValueError("max_selected_item_count must be non-negative")


def _sort_recovery_previous_blocks(
    indexed_blocks: tuple[tuple[int, CompactMaterialBlock], ...]
) -> tuple[tuple[int, CompactMaterialBlock], ...]:
    """按 S4 Decision 5 排序 previous compacted view recovery items。

    若所有候选 item 都带可解析 source EventLog sequence，则按最大 sequence
    降序；否则回退到原 material 顺序升序，再按稳定 block label 升序。

    :param indexed_blocks: 原始 material index 与 previous compact block。
    :returns: 排序后的 indexed blocks。
    """

    sequences = tuple(
        _max_recovery_source_event_sequence(block)
        for _index, block in indexed_blocks
    )
    if len(sequences) == len(indexed_blocks) and all(sequence is not None for sequence in sequences):
        return tuple(
            sorted(
                indexed_blocks,
                key=lambda item: (
                    -_required_recovery_source_event_sequence(item[1]),
                    item[0],
                    item[1].block_label,
                ),
            )
        )
    return tuple(sorted(indexed_blocks, key=lambda item: (item[0], item[1].block_label)))


def _max_recovery_source_event_sequence(block: CompactMaterialBlock) -> int | None:
    """从 canonical source refs 中读取最大 EventLog sequence。

    当前 compacted semantic block 的 canonical refs 通常是 event id 而非
    sequence。只有 ref 自身以 ``eventlog-seq:`` 显式携带 sequence 时才使用；
    否则返回 ``None`` 并让排序回退到 material 顺序。

    :param block: previous compacted view block。
    :returns: 最大 source EventLog sequence；不可解析时为 ``None``。
    """

    sequences: list[int] = []
    for ref in block.canonical_source_refs:
        sequence = _recovery_source_event_sequence(ref)
        if sequence is None:
            return None
        sequences.append(sequence)
    if len(sequences) == 0:
        return None
    return max(sequences)


def _required_recovery_source_event_sequence(block: CompactMaterialBlock) -> int:
    """读取已确认存在的 recovery source EventLog sequence。

    :param block: previous compacted view block。
    :returns: 最大 source EventLog sequence。
    :raises ValueError: block 缺少可解析 sequence 时抛出。
    """

    sequence = _max_recovery_source_event_sequence(block)
    if sequence is None:
        raise ValueError("recovery source event sequence is missing")
    return sequence


def _recovery_source_event_sequence(ref: str) -> int | None:
    """解析 recovery source sequence ref。

    :param ref: canonical source ref。
    :returns: ``eventlog-seq:<n>`` 中的非负 sequence；不匹配时为 ``None``。
    :raises ValueError: sequence ref 为负数时抛出。
    """

    prefix = "eventlog-seq:"
    if not ref.startswith(prefix):
        return None
    value = int(ref.removeprefix(prefix))
    if value < 0:
        raise ValueError("recovery source event sequence must be non-negative")
    return value


def _sorted_material_blocks(
    blocks: tuple[RunInputMaterialBlock, ...],
    *,
    memory_snapshot_cursor: int | None,
) -> tuple[RunInputMaterialBlock, ...]:
    """按 deterministic material block order 排序。

    :param blocks: material blocks。
    :param memory_snapshot_cursor: stable block 缺省 sequence 来源。
    :returns: 排序后的 material blocks。
    """

    return tuple(
        sorted(
            blocks,
            key=lambda block: (
                _block_event_sequence(block, memory_snapshot_cursor),
                block.event_sub_index,
                _BLOCK_KIND_ORDER[block.kind],
                block.block_id,
            ),
        )
    )


def _block_event_sequence(block: RunInputMaterialBlock, memory_snapshot_cursor: int | None) -> int:
    """返回排序使用的 event sequence。

    :param block: material block。
    :param memory_snapshot_cursor: memory snapshot cursor。
    :returns: 排序用 sequence。
    """

    if block.event_sequence is not None:
        return block.event_sequence
    if memory_snapshot_cursor is not None:
        return memory_snapshot_cursor
    return _NO_EVENT_SEQUENCE


def _protected_recent_turn_group_block_ids(
    blocks: tuple[RunInputMaterialBlock, ...], selected_recent_window_turn_floor: int
) -> frozenset[str]:
    """计算 protected recent turn-group floor 对应 block ids。

    :param blocks: material blocks。
    :param selected_recent_window_turn_floor: selected recent-window turn 保底数量。
    :returns: protected block id 集合。
    :raises ValueError: floor 依赖的 eligible block 缺少 turn_group_id 时抛出。
    """

    explicit = [
        block.block_id
        for block in blocks
        if block.protected_recent_raw_turn and is_turn_group_material_block(block)
    ]
    if selected_recent_window_turn_floor == 0:
        return frozenset(explicit)
    protected_turn_group_ids = protected_recent_turn_group_ids_for_material_blocks(
        blocks,
        selected_recent_window_turn_floor=selected_recent_window_turn_floor,
    )
    protected = [
        block.block_id
        for block in blocks
        if block.turn_group_id in protected_turn_group_ids
        and is_turn_group_material_block(block)
    ]
    protected.extend(explicit)
    return frozenset(protected)


def protected_recent_turn_group_ids_for_material_blocks(
    blocks: tuple[RunInputMaterialBlock, ...],
    *,
    selected_recent_window_turn_floor: int,
    missing_turn_group_message: str = "eligible material block is missing turn_group_id",
) -> frozenset[str]:
    """返回最近 N 个 Host Run turn group id。

    :param blocks: material blocks。
    :param selected_recent_window_turn_floor: 需要保护的 turn group 数。
    :param missing_turn_group_message: eligible block 缺 group 时使用的错误消息。
    :returns: 需要保护的 turn_group_id 集合。
    :raises ValueError: floor 依赖的 eligible block 缺少 turn_group_id 时抛出。
    """

    eligible = tuple(block for block in blocks if is_turn_group_material_block(block))
    missing = tuple(block.block_id for block in eligible if block.turn_group_id is None)
    if len(missing) > 0:
        raise ValueError(missing_turn_group_message)
    latest_by_group: dict[str, tuple[int, int, int]] = {}
    for index, block in enumerate(eligible):
        if block.turn_group_id is None:
            continue
        event_sequence = (
            _NO_EVENT_SEQUENCE if block.event_sequence is None else block.event_sequence
        )
        candidate = (event_sequence, block.event_sub_index, index)
        current = latest_by_group.get(block.turn_group_id)
        if current is None or candidate > current:
            latest_by_group[block.turn_group_id] = candidate
    ordered = tuple(
        turn_group_id
        for turn_group_id, _latest in sorted(
            latest_by_group.items(),
            key=lambda pair: (pair[1][0], pair[1][1], pair[1][2], pair[0]),
            reverse=True,
        )
    )
    return frozenset(ordered[:selected_recent_window_turn_floor])


def is_turn_group_material_block(block: RunInputMaterialBlock) -> bool:
    """判断 block 是否属于 Host Run turn group recent material。

    :param block: material block。
    :returns: user / assistant / accepted evidence block 返回 ``True``。
    """

    return block.kind in (
        CompactMaterialBlockKind.USER_INPUT,
        CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
        CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
    )


def _block_exclusion_reason(block: RunInputMaterialBlock, protected_recent_ids: frozenset[str]) -> str | None:
    """返回 block 的 deterministic exclusion reason。

    :param block: material block。
    :param protected_recent_ids: protected recent raw ids。
    :returns: reason code；可选择时返回 ``None``。
    """

    if block.section is CompactMaterialSection.CURRENT_INPUT_ANCHOR:
        return _REASON_PROTECTED_CURRENT_INPUT
    if block.block_id in protected_recent_ids:
        return _REASON_PROTECTED_RECENT_RAW_FLOOR
    if block.already_represented:
        return _REASON_ALREADY_REPRESENTED
    if block.section is CompactMaterialSection.PREVIOUS_COMPACTED_VIEW:
        return _REASON_PREVIOUS_COMPACTED_VIEW
    if block.section not in (
        CompactMaterialSection.TRACE_MATERIAL,
        CompactMaterialSection.EVIDENCE_MATERIAL,
        CompactMaterialSection.ANSWER_MATERIAL,
    ):
        return _REASON_NOT_IN_SEGMENT
    return None


def _selection_reason_codes(
    *,
    selected: tuple[str, ...],
    excluded_reasons: dict[str, str],
) -> tuple[str, ...]:
    """构造 deterministic reason code tuple。

    :param selected: selected block ids。
    :param excluded_reasons: excluded reason mapping。
    :returns: reason code tuple。
    """

    reasons: list[str] = []
    if len(selected) > 0:
        reasons.append(_REASON_SELECTED)
    for reason in (
        _REASON_PROTECTED_CURRENT_INPUT,
        _REASON_PROTECTED_RECENT_RAW_FLOOR,
        _REASON_ALREADY_REPRESENTED,
        _REASON_BUDGET_LIMIT,
        _REASON_PREVIOUS_COMPACTED_VIEW,
        _REASON_NOT_IN_SEGMENT,
    ):
        if reason in excluded_reasons.values():
            reasons.append(reason)
    return tuple(reasons)


def _ordered_reason_mapping(values: dict[str, str]) -> dict[str, str]:
    """返回按 key 排序的 reason mapping。

    :param values: 原始 reason mapping。
    :returns: 排序后的新 mapping。
    """

    return {key: values[key] for key in sorted(values)}


def _effective_snapshot(
    memory_snapshot: ConversationMemorySnapshotVNext | None,
    inline_delta_repair_view: InlineDeltaRepairMaterialView | None,
) -> ConversationMemorySnapshotVNext | None:
    """选取 material pack stable input 使用的 snapshot。

    :param memory_snapshot: ready memory snapshot。
    :param inline_delta_repair_view: inline repair view。
    :returns: 有效 snapshot 或 ``None``。
    """

    if inline_delta_repair_view is not None:
        return inline_delta_repair_view.snapshot
    return memory_snapshot


def _validated_current_input_event(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    run: RunRow,
    current_display_text: str,
) -> EventLogRow:
    """读取并校验当前 Run input 对应的 ``USER_INPUT_ACCEPTED`` row。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog store。
    :param run: 当前 Run durable row。
    :param current_display_text: 调用方持有的当前 display text。
    :returns: 已校验的 current input EventLog row。
    :raises HostDurableError: EventLog row 缺失、类型错误或 display text 不一致时抛出。
    """

    row = event_log_store.read_event_by_id(transaction, run.input_event_id)
    if row is None:
        raise HostDurableError("current input event is missing")
    _require_canonical_session_event(
        row,
        session_id=run.session_id,
        expected_event_type=_EVENT_TYPE_USER_INPUT_ACCEPTED,
    )
    if row.event_sequence != run.input_event_sequence:
        raise HostDurableError("current input event sequence mismatch")
    payload = event_payload_object(
        transaction,
        row,
        payload_label=_EVENT_TYPE_USER_INPUT_ACCEPTED,
    )
    display_text = _required_json_text(payload, _PAYLOAD_FIELD_DISPLAY_TEXT)
    if display_text != current_display_text:
        raise HostDurableError("current input display text mismatch")
    return row


def _latest_compacted_event_before_current_input(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    session_id: str,
    before_event_sequence: int,
) -> EventLogRow | None:
    """读取当前 input 前最新 accepted compact canonical fact。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog store。
    :param session_id: 当前 Session id。
    :param before_event_sequence: 当前 input EventLog sequence 排他上界。
    :returns: 最新 ``CONTEXT_COMPACTED`` row；不存在时返回 ``None``。
    :raises HostDurableError: 查询到的 row 消失或类型不匹配时抛出。
    """

    row = transaction.fetchone(
        f"""
        SELECT event_id
        FROM {TABLE_EVENT_LOG}
        WHERE session_id = ?
          AND event_type = ?
          AND event_class = ?
          AND event_sequence < ?
        ORDER BY event_sequence DESC
        LIMIT 1
        """,
        (
            session_id,
            CONTEXT_COMPACTED,
            EventClass.CANONICAL_FACT.value,
            before_event_sequence,
        ),
    )
    if row is None:
        return None
    event_id = _required_host_row_text(row, field_name="event_id")
    event = event_log_store.read_event_by_id(transaction, event_id)
    if event is None:
        raise HostDurableError("latest compacted event disappeared during read")
    _require_canonical_session_event(
        event,
        session_id=session_id,
        expected_event_type=CONTEXT_COMPACTED,
    )
    return event


def _accepted_evidence_mapping_refs_from_compacted_event(
    transaction: HostTransaction,
    row: EventLogRow,
) -> tuple[str, ...]:
    """从 accepted compact EventLog payload 读取已覆盖的 evidence refs。

    :param transaction: 当前 Host transaction。
    :param row: ``CONTEXT_COMPACTED`` EventLog row。
    :returns: 去重后的 accepted evidence mapping refs。
    :raises HostDurableError: compact payload 损坏时抛出。
    """

    payload = _validated_compacted_payload(transaction, row)
    return _required_json_text_tuple(payload, _PAYLOAD_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS)


def _previous_compacted_view_from_compacted_event(
    transaction: HostTransaction,
    row: EventLogRow,
) -> tuple[CompactMaterialBlock, ...]:
    """把 latest accepted compact candidate 映射为 previous compacted view。

    :param transaction: 当前 Host transaction。
    :param row: ``CONTEXT_COMPACTED`` EventLog row。
    :returns: prompt-local previous compacted view blocks。
    :raises HostDurableError: accepted candidate JSON 损坏或 digest 不匹配时抛出。
    """

    payload = _validated_compacted_payload(transaction, row)
    candidate = _required_json_mapping(payload, _PAYLOAD_FIELD_ACCEPTED_CANDIDATE)
    expected_digest = _required_json_text(payload, _PAYLOAD_FIELD_ACCEPTED_CANDIDATE_DIGEST)
    if sha256_digest_json(candidate) != expected_digest:
        raise HostDurableError("accepted candidate digest mismatch")
    blocks: list[RunInputMaterialBlock] = []
    summary_text = _candidate_session_summary_text(candidate)
    if summary_text is not None:
        blocks.append(
            run_input_material_block(
                block_id=f"previous:{row.event_id}:session_summary",
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.SESSION_SUMMARY,
                text=summary_text,
                canonical_source_refs=(row.event_id,),
                event_sequence=row.event_sequence,
                event_sub_index=0,
            )
        )
    for index, fact_text in enumerate(_candidate_facts_texts(candidate), start=1):
        blocks.append(
            run_input_material_block(
                block_id=f"previous:{row.event_id}:evidence_backed_fact:{index}",
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
                text=fact_text,
                canonical_source_refs=(row.event_id,),
                event_sequence=row.event_sequence,
                event_sub_index=len(blocks),
            )
        )
    for index, anchor_text in enumerate(
        _candidate_answer_anchor_texts(candidate),
        start=1,
    ):
        blocks.append(
            run_input_material_block(
                block_id=f"previous:{row.event_id}:answer_anchor:{index}",
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.ANSWER_ANCHOR,
                text=anchor_text,
                canonical_source_refs=(row.event_id,),
                event_sequence=row.event_sequence,
                event_sub_index=len(blocks),
            )
        )
    for index, intent_text in enumerate(
        _candidate_forward_intent_texts(candidate),
        start=1,
    ):
        blocks.append(
            run_input_material_block(
                block_id=f"previous:{row.event_id}:forward_intent:{index}",
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.FORWARD_INTENT,
                text=intent_text,
                canonical_source_refs=(row.event_id,),
                event_sequence=row.event_sequence,
                event_sub_index=len(blocks),
            )
        )
    for index, reference_text in enumerate(
        _candidate_reference_continuity_texts(candidate),
        start=1,
    ):
        blocks.append(
            run_input_material_block(
                block_id=f"previous:{row.event_id}:reference_continuity:{index}",
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.REFERENCE_CONTINUITY,
                text=reference_text,
                canonical_source_refs=(row.event_id,),
                event_sequence=row.event_sequence,
                event_sub_index=len(blocks),
            )
        )
    return _pack_previous_blocks(tuple(blocks))


def _validated_compacted_payload(
    transaction: HostTransaction, row: EventLogRow
) -> Mapping[str, JsonValue]:
    """读取并校验 ``CONTEXT_COMPACTED`` payload。

    :param transaction: 当前 Host transaction。
    :param row: compacted EventLog row。
    :returns: compacted payload object。
    :raises HostDurableError: payload 结构或 digest 非法时抛出。
    """

    payload = event_payload_object(transaction, row, payload_label=CONTEXT_COMPACTED)
    try:
        validate_context_compacted_payload(payload)
    except (TypeError, ValueError) as exc:
        raise HostDurableError("CONTEXT_COMPACTED payload is invalid") from exc
    return payload


def _post_compact_delta_start_sequence(
    transaction: HostTransaction,
    *,
    session_id: str,
    current_input_sequence: int,
    latest_compacted_event: EventLogRow | None,
) -> int:
    """计算 post-compact delta material 的 EventLog 起点。

    :param transaction: 当前 Host transaction。
    :param session_id: 当前 Session id。
    :param current_input_sequence: 当前 input EventLog sequence。
    :param latest_compacted_event: latest accepted compact row。
    :returns: delta 起点 sequence。
    :raises HostDurableError: EventLog 查询结果非法时抛出。
    """

    if latest_compacted_event is not None:
        return latest_compacted_event.event_sequence + 1
    row = transaction.fetchone(
        f"""
        SELECT event_sequence
        FROM {TABLE_EVENT_LOG}
        WHERE session_id = ?
          AND event_class = ?
          AND event_type IN (?, ?, ?)
          AND event_sequence < ?
        ORDER BY event_sequence ASC
        LIMIT 1
        """,
        (
            session_id,
            EventClass.CANONICAL_FACT.value,
            _EVENT_TYPE_USER_INPUT_ACCEPTED,
            _EVENT_TYPE_RUN_SUCCEEDED,
            _EVENT_TYPE_TOOL_RESULT_ACCEPTED,
            current_input_sequence,
        ),
    )
    if row is None:
        return current_input_sequence
    return _required_host_row_int(row, field_name="event_sequence")


def _post_compact_delta_rows(
    transaction: HostTransaction,
    *,
    session_id: str,
    start_sequence: int,
    end_sequence: int,
) -> tuple[EventLogRow, ...]:
    """读取 post-compact delta canonical fact rows。

    :param transaction: 当前 Host transaction。
    :param session_id: 当前 Session id。
    :param start_sequence: 包含式起点。
    :param end_sequence: 排他式终点，等于 current input sequence。
    :returns: delta rows，按 EventLog sequence 升序。
    :raises HostDurableError: EventLog row 转换失败时抛出。
    """

    rows = transaction.fetchall(
        f"""
        SELECT
          event_sequence,
          event_id,
          event_body_digest,
          event_class,
          session_id,
          run_id,
          attempt_id,
          execution_id,
          event_type,
          occurred_at,
          actor,
          source,
          client_request_id,
          idempotency_key,
          policy_decision_json,
          reason_json,
          payload_json,
          payload_ref,
          payload_digest,
          appended_at
        FROM {TABLE_EVENT_LOG}
        WHERE session_id = ?
          AND event_class = ?
          AND event_type IN (?, ?, ?)
          AND event_sequence >= ?
          AND event_sequence < ?
        ORDER BY event_sequence ASC
        """,
        (
            session_id,
            EventClass.CANONICAL_FACT.value,
            _EVENT_TYPE_USER_INPUT_ACCEPTED,
            _EVENT_TYPE_RUN_SUCCEEDED,
            _EVENT_TYPE_TOOL_RESULT_ACCEPTED,
            start_sequence,
            end_sequence,
        ),
    )
    return tuple(_event_log_row_from_host_row(row) for row in rows)


def _pre_dispatch_delta_material_blocks(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    rows: tuple[EventLogRow, ...],
    represented_evidence_refs: tuple[str, ...],
) -> tuple[RunInputMaterialBlock, ...]:
    """把 delta EventLog rows 映射为 RunInputMaterialBlock。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog store。
    :param rows: post-compact delta rows。
    :param represented_evidence_refs: latest compact 已覆盖的 accepted evidence refs。
    :returns: material block tuple。
    :raises HostDurableError: payload 损坏时抛出。
    """

    represented = frozenset(represented_evidence_refs)
    blocks: list[RunInputMaterialBlock] = []
    for row in rows:
        if row.event_type == _EVENT_TYPE_USER_INPUT_ACCEPTED:
            blocks.append(_user_input_delta_block(transaction, row))
        elif row.event_type == _EVENT_TYPE_RUN_SUCCEEDED:
            answer_block = _assistant_answer_delta_block(transaction, row)
            if answer_block is not None:
                blocks.append(answer_block)
        elif row.event_type == _EVENT_TYPE_TOOL_RESULT_ACCEPTED:
            evidence_blocks = _accepted_tool_evidence_delta_blocks(
                transaction,
                event_log_store,
                row,
                represented_evidence_refs=represented,
            )
            blocks.extend(evidence_blocks)
    return tuple(blocks)


def _user_input_delta_block(
    transaction: HostTransaction,
    row: EventLogRow,
) -> RunInputMaterialBlock:
    """把历史 ``USER_INPUT_ACCEPTED`` 映射为 trace material。

    :param transaction: 当前 Host transaction。
    :param row: 历史 user input EventLog row。
    :returns: user trace material block。
    :raises HostDurableError: payload display text 缺失或非法时抛出。
    """

    payload = event_payload_object(
        transaction,
        row,
        payload_label=_EVENT_TYPE_USER_INPUT_ACCEPTED,
    )
    return run_input_material_block(
        block_id=f"eventlog:user:{row.event_id}",
        section=CompactMaterialSection.TRACE_MATERIAL,
        kind=CompactMaterialBlockKind.USER_INPUT,
        text=_required_json_text(payload, _PAYLOAD_FIELD_DISPLAY_TEXT),
        canonical_source_refs=(row.event_id,),
        event_sequence=row.event_sequence,
        turn_group_id=row.run_id,
    )


def _assistant_answer_delta_block(
    transaction: HostTransaction,
    row: EventLogRow,
) -> RunInputMaterialBlock | None:
    """把 ``RUN_SUCCEEDED`` final answer 映射为 answer material。

    :param transaction: 当前 Host transaction。
    :param row: run succeeded EventLog row。
    :returns: answer material block；无可读 final answer continuity 时返回 ``None``。
    :raises HostDurableError: terminal payload 损坏时抛出。
    """

    payload = event_payload_object(
        transaction,
        row,
        payload_label=_EVENT_TYPE_RUN_SUCCEEDED,
    )
    answer_text = assistant_final_answer_continuity_text(
        transaction,
        payload,
        text_policy=PayloadTextReadPolicy.STRICT_NON_EMPTY,
    )
    if answer_text is None:
        return None
    return run_input_material_block(
        block_id=f"eventlog:answer:{row.event_id}",
        section=CompactMaterialSection.ANSWER_MATERIAL,
        kind=CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
        text=answer_text,
        canonical_source_refs=(row.event_id,),
        event_sequence=row.event_sequence,
        turn_group_id=row.run_id,
    )


def _accepted_tool_evidence_delta_blocks(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    row: EventLogRow,
    *,
    represented_evidence_refs: frozenset[str],
) -> tuple[RunInputMaterialBlock, ...]:
    """把 ``TOOL_RESULT_ACCEPTED`` 映射为 evidence material blocks。

    当 accepted evidence envelope 缺少 durable request atom 时，
    ``tool_call_event_ref`` 会退化为当前 producer event ref。这个 ref 只用于
    prompt-local provenance 追溯，不表示对应的 ``TOOL_CALL_REQUESTED`` event
    一定存在。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog store。
    :param row: accepted tool result EventLog row。
    :param represented_evidence_refs: latest compact 已覆盖的 evidence refs。
    :returns: evidence material blocks。
    :raises HostDurableError: evidence envelope 或 raw tool payload 损坏时抛出。
    """

    payload = event_payload_object(
        transaction,
        row,
        payload_label=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
    )
    try:
        envelope = accepted_evidence_envelope_from_payload(
            payload,
            producer_event_ref=row.event_id,
        )
    except ValueError as exc:
        if str(exc) == ACCEPTED_EVIDENCE_PRODUCER_EVENT_REF_MISMATCH:
            raise HostDurableError(str(exc)) from exc
        raise HostDurableError("canonical evidence envelope is invalid") from exc
    if envelope is None:
        return ()
    if envelope.evidence_id in represented_evidence_refs:
        return ()
    projection = project_accepted_tool_result(transaction, row)
    if projection.result_text is None:
        raise HostDurableError("TOOL_RESULT_ACCEPTED raw_tool_outcome is missing")
    tool_call_event_ref = envelope.tool_query.tool_call_requested_event_ref
    if tool_call_event_ref is None:
        # 缺少 request atom 时只保留本地 provenance 线索，不伪造 request event。
        tool_call_event_ref = row.event_id
    return (
        run_input_material_block(
            block_id=f"eventlog:evidence:{row.event_id}:{envelope.evidence_id}",
            section=CompactMaterialSection.EVIDENCE_MATERIAL,
            kind=CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
            text=projection.result_text,
            canonical_source_refs=(envelope.evidence_id,),
            event_sequence=row.event_sequence,
            turn_group_id=row.run_id,
            accepted_evidence_id=envelope.evidence_id,
            tool_result_event_ref=row.event_id,
            tool_call_event_ref=tool_call_event_ref,
            payload_refs=_payload_refs_for_event(row),
            source_locator_refs=envelope.locator_refs,
            readable_tool_name=envelope.tool_name,
            readable_query_text=projection.query.text,
            readable_source_text=projection.source.text,
        ),
    )


def _pre_dispatch_budget_fragments(
    *,
    previous_view: tuple[CompactMaterialBlock, ...],
    material_blocks: tuple[RunInputMaterialBlock, ...],
    current_input_text: str,
) -> tuple[BudgetTextFragment, ...]:
    """从同源 material view 构造预算估算文本片段。

    :param previous_view: latest compact previous view blocks。
    :param material_blocks: post-compact delta material blocks。
    :param current_input_text: 当前输入文本。
    :returns: budget text fragments。
    """

    fragments: list[BudgetTextFragment] = []
    for block in previous_view:
        fragments.append(
            BudgetTextFragment(
                fragment_ref=f"{_PRE_DISPATCH_BUDGET_FRAGMENT_PREVIOUS_PREFIX}{block.block_label}",
                text=block.text,
            )
        )
    for block in material_blocks:
        fragments.append(BudgetTextFragment(fragment_ref=block.block_id, text=block.text))
    fragments.append(
        BudgetTextFragment(
            fragment_ref=_PRE_DISPATCH_BUDGET_FRAGMENT_CURRENT_REF,
            text=current_input_text,
        )
    )
    return tuple(fragments)


def _candidate_session_summary_text(
    candidate: Mapping[str, JsonValue],
) -> str | None:
    """读取 accepted candidate 的 session summary 文本。

    :param candidate: accepted candidate JSON object。
    :returns: summary text；无 summary 时为 ``None``。
    :raises HostDurableError: candidate 结构损坏时抛出。
    """

    value = candidate.get(_PAYLOAD_FIELD_SESSION_SUMMARY)
    if value is None:
        return None
    summary = _json_mapping(value, _PAYLOAD_FIELD_SESSION_SUMMARY)
    return _required_json_text(summary, _PAYLOAD_FIELD_SUMMARY_TEXT)


def _candidate_facts_texts(candidate: Mapping[str, JsonValue]) -> tuple[str, ...]:
    """把 accepted candidate facts 渲染为 previous view 单项文本。

    :param candidate: accepted candidate JSON object。
    :returns: facts 单项文本 tuple；无 facts 时为空 tuple。
    :raises HostDurableError: candidate facts 结构损坏时抛出。
    """

    facts = _required_json_mapping_tuple(candidate, _PAYLOAD_FIELD_EVIDENCE_BACKED_FACTS)
    lines: list[str] = []
    for fact in facts:
        claim_text = _normalized_structured_field_text(
            _required_json_text(fact, _PAYLOAD_FIELD_CLAIM_TEXT)
        )
        evidence_refs = ",".join(
            _normalized_structured_field_text(label)
            for label in _required_json_text_tuple(fact, _PAYLOAD_FIELD_EVIDENCE_LABELS)
        )
        lines.append(
            "fact="
            f"claim_text={claim_text}; "
            f"evidence_refs={evidence_refs}"
        )
    return tuple(lines)


def _candidate_answer_anchor_texts(candidate: Mapping[str, JsonValue]) -> tuple[str, ...]:
    """把 accepted candidate answer anchors 渲染为 previous view 单项文本。

    :param candidate: accepted candidate JSON object。
    :returns: answer anchors 单项文本 tuple；无 anchors 时为空 tuple。
    :raises HostDurableError: candidate anchors 结构损坏时抛出。
    """

    anchors = _required_json_mapping_tuple(candidate, _PAYLOAD_FIELD_ANSWER_ANCHORS)
    lines: list[str] = []
    for anchor in anchors:
        title = _normalized_structured_field_text(
            _required_json_text(anchor, _PAYLOAD_FIELD_ANCHOR_TITLE)
        )
        lines.append(f"{_PREVIOUS_ANSWER_ANCHOR_PREFIX}{title}")
    return tuple(lines)


def _candidate_forward_intent_texts(candidate: Mapping[str, JsonValue]) -> tuple[str, ...]:
    """把 accepted candidate forward intents 渲染为 previous view 单项文本。

    :param candidate: accepted candidate JSON object。
    :returns: forward intents 单项文本 tuple；无 intents 时为空 tuple。
    :raises HostDurableError: candidate intents 结构损坏时抛出。
    """

    intents = _required_json_mapping_tuple(candidate, _PAYLOAD_FIELD_FORWARD_INTENTS)
    lines: list[str] = []
    for intent in intents:
        intent_type = _normalized_structured_field_text(
            _required_json_text(intent, _PAYLOAD_FIELD_INTENT_TYPE)
        )
        status = _normalized_structured_field_text(
            _required_json_text(intent, _PAYLOAD_FIELD_STATUS)
        )
        text = _normalized_structured_field_text(
            _required_json_text(intent, _PAYLOAD_FIELD_TEXT)
        )
        lines.append(
            f"{_PREVIOUS_FORWARD_INTENT_PREFIX}"
            f"{intent_type}; "
            f"{_PREVIOUS_FORWARD_STATUS_PREFIX}"
            f"{status}; "
            f"{_PREVIOUS_FORWARD_TEXT_PREFIX}"
            f"{text}"
        )
    return tuple(lines)


def _candidate_reference_continuity_texts(
    candidate: Mapping[str, JsonValue],
) -> tuple[str, ...]:
    """把 accepted candidate reference continuity 渲染为 previous view 单项文本。

    :param candidate: accepted candidate JSON object。
    :returns: reference continuity 单项文本 tuple；无 items 时为空 tuple。
    :raises HostDurableError: candidate references 结构损坏时抛出。
    """

    items = _required_json_mapping_tuple(
        candidate,
        _PAYLOAD_FIELD_REFERENCE_CONTINUITY_ITEMS,
    )
    lines: list[str] = []
    for item in items:
        reason = _normalized_structured_field_text(
            _required_json_text(item, _PAYLOAD_FIELD_REASON)
        )
        text = _normalized_structured_field_text(
            _required_json_text(item, _PAYLOAD_FIELD_TEXT)
        )
        lines.append(
            f"{_PREVIOUS_REFERENCE_PREFIX}"
            f"{reason}; "
            f"{_PREVIOUS_REFERENCE_TEXT_PREFIX}"
            f"{text}"
        )
    return tuple(lines)


def _current_input_anchor(current_input_ref: str, current_input_text: str) -> CurrentInputAnchor:
    """构造 current input anchor。

    :param current_input_ref: current input canonical ref。
    :param current_input_text: current input display text。
    :returns: CurrentInputAnchor。
    """

    anchor_text = normalized_material_text(current_input_text)
    return CurrentInputAnchor(
        anchor_label=current_input_anchor_label(),
        anchor_text=anchor_text,
        truncated=False,
        canonical_source_refs=(current_input_ref,),
        content_digest=_text_digest(anchor_text),
    )


def _selected_material_blocks(
    selected_block_ids: tuple[str, ...],
    material_blocks: tuple[RunInputMaterialBlock, ...],
    *,
    current_anchor: CurrentInputAnchor,
) -> tuple[RunInputMaterialBlock, ...]:
    """按 selection ids 取回 material blocks，并过滤当前输入重复 raw turn。

    :param selected_block_ids: selection 输出的 ordinary block ids。
    :param material_blocks: 同源 material list。
    :param current_anchor: current input anchor。
    :returns: selected material blocks。
    :raises ValueError: selection 引用未知 block id 时抛出。
    """

    block_by_id = {block.block_id: block for block in material_blocks}
    selected: list[RunInputMaterialBlock] = []
    for block_id in selected_block_ids:
        block = block_by_id.get(block_id)
        if block is None:
            raise ValueError("selected segment references unknown material block")
        if _is_current_input_history_duplicate(block, current_anchor):
            continue
        selected.append(block)
    return tuple(selected)


def _is_current_input_history_duplicate(block: RunInputMaterialBlock, current_anchor: CurrentInputAnchor) -> bool:
    """判断 history block 是否重复当前输入 anchor。

    :param block: material block。
    :param current_anchor: current input anchor。
    :returns: 重复当前输入时返回 ``True``。
    """

    if block.section is not CompactMaterialSection.TRACE_MATERIAL:
        return False
    if block.kind is not CompactMaterialBlockKind.USER_INPUT:
        return False
    if current_anchor.canonical_source_refs[0] in block.canonical_source_refs:
        return True
    return block.content_digest == current_anchor.content_digest


def _previous_blocks_from_snapshot(
    snapshot: ConversationMemorySnapshotVNext | None,
) -> tuple[CompactMaterialBlock, ...]:
    """从 memory snapshot 构造 previous compacted view blocks。

    :param snapshot: memory snapshot。
    :returns: previous compacted view blocks。
    """

    if snapshot is None:
        return ()
    blocks: list[RunInputMaterialBlock] = []
    summary_text = _snapshot_summary_text(snapshot)
    if summary_text is not None:
        blocks.append(
            run_input_material_block(
                block_id="previous:session_summary",
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.SESSION_SUMMARY,
                text=summary_text,
                canonical_source_refs=(snapshot.snapshot_id,),
                event_sequence=None,
                event_sub_index=0,
            )
        )
    for index, fact_text in enumerate(_snapshot_fact_texts(snapshot), start=1):
        blocks.append(
            run_input_material_block(
                block_id=f"{_STABLE_FACTS_BLOCK_ID}:{index}",
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
                text=fact_text,
                canonical_source_refs=(snapshot.snapshot_id,),
                event_sequence=None,
                event_sub_index=len(blocks),
            )
        )
    for index, anchor_text in enumerate(
        _snapshot_answer_anchor_texts(snapshot),
        start=1,
    ):
        blocks.append(
            run_input_material_block(
                block_id=f"previous:answer_anchor:{index}",
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.ANSWER_ANCHOR,
                text=anchor_text,
                canonical_source_refs=(snapshot.snapshot_id,),
                event_sequence=None,
                event_sub_index=len(blocks),
            )
        )
    for index, intent_text in enumerate(
        _snapshot_forward_intent_texts(snapshot),
        start=1,
    ):
        blocks.append(
            run_input_material_block(
                block_id=f"previous:forward_intent:{index}",
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.FORWARD_INTENT,
                text=intent_text,
                canonical_source_refs=(snapshot.snapshot_id,),
                event_sequence=None,
                event_sub_index=len(blocks),
            )
        )
    for index, reference_text in enumerate(
        _snapshot_reference_continuity_texts(snapshot),
        start=1,
    ):
        blocks.append(
            run_input_material_block(
                block_id=f"previous:reference_continuity:{index}",
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.REFERENCE_CONTINUITY,
                text=reference_text,
                canonical_source_refs=(snapshot.snapshot_id,),
                event_sequence=None,
                event_sub_index=len(blocks),
            )
        )
    return _pack_previous_blocks(tuple(blocks))


def _snapshot_summary_text(snapshot: ConversationMemorySnapshotVNext) -> str | None:
    """构造 previous session summary 文本。

    :param snapshot: memory snapshot。
    :returns: summary 文本；无内容时返回 ``None``。
    """

    return snapshot.session_summary_memory.summary_text


def _snapshot_fact_texts(snapshot: ConversationMemorySnapshotVNext) -> tuple[str, ...]:
    """构造 evidence-backed facts stable 单项文本。

    :param snapshot: memory snapshot。
    :returns: stable 单项文本 tuple；无内容时为空 tuple。
    """

    facts = snapshot.evidence_fact_memory.evidence_backed_facts
    lines: list[str] = []
    for fact in facts:
        evidence_refs = ",".join(
            _normalized_structured_field_text(ref)
            for ref in fact.evidence_refs
        )
        lines.append(
            "fact="
            f"claim_text={_normalized_structured_field_text(fact.claim_text)}; "
            f"evidence_refs={evidence_refs}"
        )
    return tuple(lines)


def _snapshot_answer_anchor_texts(snapshot: ConversationMemorySnapshotVNext) -> tuple[str, ...]:
    """构造 previous answer anchor 单项文本。

    :param snapshot: memory snapshot。
    :returns: answer anchor 单项文本 tuple；无内容时为空 tuple。
    """

    lines: list[str] = []
    for anchor in snapshot.answer_anchor_memory.anchors:
        lines.append(
            f"answer_anchor={_normalized_structured_field_text(anchor.anchor_title)}"
        )
    return tuple(lines)


def _snapshot_forward_intent_texts(snapshot: ConversationMemorySnapshotVNext) -> tuple[str, ...]:
    """构造 previous forward intent 单项文本。

    :param snapshot: memory snapshot。
    :returns: forward intent 单项文本 tuple；无内容时为空 tuple。
    """

    lines: list[str] = []
    for intent in snapshot.forward_intent_memory.intents:
        lines.append(
            f"forward_intent={_normalized_structured_field_text(intent.intent_type)}; "
            f"status={_normalized_structured_field_text(intent.status)}; "
            f"text={_normalized_structured_field_text(intent.text)}"
        )
    return tuple(lines)


def _snapshot_reference_continuity_texts(snapshot: ConversationMemorySnapshotVNext) -> tuple[str, ...]:
    """构造 previous reference continuity 单项文本。

    :param snapshot: memory snapshot。
    :returns: reference continuity 单项文本 tuple；无内容时为空 tuple。
    """

    lines: list[str] = []
    for item in snapshot.trace_memory.reference_continuity_items:
        lines.append(
            f"reference_continuity={_normalized_structured_field_text(item.reason)}; "
            f"text={_normalized_structured_field_text(item.text)}"
        )
    return tuple(lines)


def _pack_previous_blocks(blocks: tuple[RunInputMaterialBlock, ...]) -> tuple[CompactMaterialBlock, ...]:
    """把 previous material view 转为 prompt-local blocks。

    :param blocks: previous material blocks。
    :returns: CompactMaterialBlock tuple。
    """

    result: list[CompactMaterialBlock] = []
    for index, block in enumerate(blocks, start=_FIRST_ORDINAL):
        result.append(_compact_material_block(block, index))
    return tuple(result)


def _pack_section_blocks(
    blocks: tuple[RunInputMaterialBlock, ...],
    section: CompactMaterialSection,
) -> tuple[CompactMaterialBlock, ...]:
    """把 selected section material 转为 prompt-local blocks。

    :param blocks: selected material blocks。
    :param section: 目标 material section。
    :returns: CompactMaterialBlock tuple。
    """

    if not isinstance(section, CompactMaterialSection):
        raise TypeError("section must be CompactMaterialSection")
    result: list[CompactMaterialBlock] = []
    selected_blocks = tuple(block for block in blocks if block.section is section)
    for index, block in enumerate(selected_blocks, start=_FIRST_ORDINAL):
        result.append(_compact_material_block(block, index))
    return tuple(result)


def _compact_material_block(block: RunInputMaterialBlock, ordinal: int) -> CompactMaterialBlock:
    """构造普通 prompt-local material block。

    :param block: ordinary material block。
    :param ordinal: section 内 ordinal。
    :returns: CompactMaterialBlock。
    """

    return CompactMaterialBlock(
        block_label=material_label(block.section, ordinal),
        section=block.section,
        kind=block.kind,
        text=block.text,
        size_units=block.size_units,
        source_labels=block.source_labels,
        canonical_source_refs=block.canonical_source_refs,
        content_digest=block.content_digest,
    )


def _pack_evidence_blocks(blocks: tuple[RunInputMaterialBlock, ...]) -> tuple[CompactEvidenceBlock, ...]:
    """把 selected evidence material 转为 prompt-local evidence blocks。

    :param blocks: selected material blocks。
    :returns: CompactEvidenceBlock tuple。
    """

    result: list[CompactEvidenceBlock] = []
    evidence_blocks = tuple(block for block in blocks if block.section is CompactMaterialSection.EVIDENCE_MATERIAL)
    for index, block in enumerate(evidence_blocks, start=_FIRST_ORDINAL):
        if block.readable_tool_name is None:
            raise ValueError("RunInputMaterialBlock.readable_tool_name is required")
        if block.readable_query_text is None:
            raise ValueError("RunInputMaterialBlock.readable_query_text is required")
        if block.readable_source_text is None:
            raise ValueError("RunInputMaterialBlock.readable_source_text is required")
        _require_non_empty_text(block.text, "evidence_text")
        result.append(
            CompactEvidenceBlock(
                evidence_label=material_label(CompactMaterialSection.EVIDENCE_MATERIAL, index),
                readable_tool_name=block.readable_tool_name,
                readable_query_text=block.readable_query_text,
                raw_result_text=block.text,
                readable_source_text=block.readable_source_text,
                size_units=len(block.text),
                canonical_source_refs=block.canonical_source_refs,
                content_digest=block.content_digest,
            )
        )
    return tuple(result)


def _provenance_from_blocks(blocks: tuple[CompactMaterialBlock, ...]) -> tuple[PromptLocalProvenanceEntry, ...]:
    """构造普通 material provenance entries。

    :param blocks: compact material blocks。
    :returns: provenance entries。
    """

    return tuple(
        PromptLocalProvenanceEntry(
            label=block.block_label,
            section=block.section,
            kind=block.kind,
            canonical_source_refs=block.canonical_source_refs,
            source_event_refs=block.canonical_source_refs,
            content_digest=block.content_digest,
            accepted_evidence_id=None,
            tool_result_event_ref=None,
            tool_call_event_ref=None,
            payload_refs=(),
            artifact_refs=(),
            source_locator_refs=(),
        )
        for block in blocks
    )


def _provenance_from_evidence_blocks(
    selected_blocks: tuple[RunInputMaterialBlock, ...],
) -> tuple[PromptLocalProvenanceEntry, ...]:
    """构造 evidence provenance entries。

    :param selected_blocks: selected ordinary material blocks。
    :returns: provenance entries。
    """

    source_blocks = tuple(block for block in selected_blocks if block.section is CompactMaterialSection.EVIDENCE_MATERIAL)
    entries: list[PromptLocalProvenanceEntry] = []
    for index, source in enumerate(source_blocks, start=_FIRST_ORDINAL):
        if source.accepted_evidence_id is None:
            raise ValueError("RunInputMaterialBlock.accepted_evidence_id is required")
        if source.tool_result_event_ref is None:
            raise ValueError("RunInputMaterialBlock.tool_result_event_ref is required")
        if source.tool_call_event_ref is None:
            raise ValueError("RunInputMaterialBlock.tool_call_event_ref is required")
        _require_non_empty_text(source.text, "evidence_text")
        entries.append(
            PromptLocalProvenanceEntry(
                label=material_label(CompactMaterialSection.EVIDENCE_MATERIAL, index),
                section=CompactMaterialSection.EVIDENCE_MATERIAL,
                kind=CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
                canonical_source_refs=source.canonical_source_refs,
                source_event_refs=(source.tool_result_event_ref,),
                content_digest=source.content_digest,
                accepted_evidence_id=source.accepted_evidence_id,
                tool_result_event_ref=source.tool_result_event_ref,
                tool_call_event_ref=source.tool_call_event_ref,
                payload_refs=source.payload_refs,
                artifact_refs=source.artifact_refs,
                source_locator_refs=source.source_locator_refs,
            )
        )
    return tuple(entries)


def _raise_on_duplicate_section_owner(entries: tuple[PromptLocalProvenanceEntry, ...]) -> None:
    """对 builder 输出执行 duplicate section owner guard。

    :param entries: provenance entries。
    :returns: ``None``。
    :raises DuplicateMaterialSectionOwnerError: 同一 canonical content 跨 section 时抛出。
    """

    seen: dict[tuple[tuple[str, ...], str], CompactMaterialSection] = {}
    for entry in entries:
        key = (tuple(sorted(entry.canonical_source_refs)), entry.content_digest)
        existing = seen.get(key)
        if existing is None:
            seen[key] = entry.section
            continue
        if existing is not entry.section:
            raise DuplicateMaterialSectionOwnerError("material pack canonical content appears in two sections")


def _validate_snapshot_session(
    snapshot: ConversationMemorySnapshotVNext,
    *,
    session_id: str,
    required_event_sequence: int,
    policy_digest: str,
) -> None:
    """校验 snapshot 是否属于当前 session。

    :param snapshot: memory snapshot。
    :param session_id: Session id。
    :param required_event_sequence: required cursor。
    :param policy_digest: policy digest。
    :returns: ``None``。
    :raises CompactMemorySnapshotRepairRequired: snapshot 损坏时抛出。
    """

    if snapshot.session_id != session_id or snapshot.cursor.session_id != session_id:
        _raise_snapshot_repair_required(
            session_id=session_id,
            reason=MemoryRepairReason.SNAPSHOT_DAMAGED,
            required_event_sequence=required_event_sequence,
            observed_cursor=snapshot.cursor,
            policy_digest=policy_digest,
        )


def _raise_snapshot_repair_required(
    *,
    session_id: str,
    reason: MemoryRepairReason,
    required_event_sequence: int,
    observed_cursor: MemorySnapshotCursor | None,
    policy_digest: str,
) -> NoReturn:
    """抛出 compact memory snapshot repair-required typed error。

    :param session_id: Session id。
    :param reason: repair reason。
    :param required_event_sequence: required cursor。
    :param observed_cursor: observed cursor。
    :param policy_digest: policy digest。
    :raises CompactMemorySnapshotRepairRequired: 始终抛出。
    """

    raise CompactMemorySnapshotRepairRequired(
        MemoryRepairRequest(
            session_id=session_id,
            reason=reason,
            required_event_sequence=required_event_sequence,
            observed_cursor=observed_cursor,
            policy_digest=policy_digest,
        )
    )


def _require_material_block_tuple(value: tuple[RunInputMaterialBlock, ...], field_name: str) -> None:
    """校验 RunInputMaterialBlock tuple。

    :param value: 待校验 tuple。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, RunInputMaterialBlock):
            raise TypeError(f"{field_name} items must be RunInputMaterialBlock")


def _require_compact_material_block_tuple(
    value: tuple[CompactMaterialBlock, ...], field_name: str
) -> None:
    """校验 compact material block tuple。

    :param value: 待校验 tuple。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, CompactMaterialBlock):
            raise TypeError(f"{field_name} items must be CompactMaterialBlock")


def _require_budget_fragment_tuple(
    value: tuple[BudgetTextFragment, ...], field_name: str
) -> None:
    """校验 budget text fragment tuple。

    :param value: 待校验 tuple。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, BudgetTextFragment):
            raise TypeError(f"{field_name} items must be BudgetTextFragment")


def _require_canonical_session_event(
    row: EventLogRow,
    *,
    session_id: str,
    expected_event_type: str,
) -> None:
    """校验 EventLog row 属于当前 session 的 canonical fact。

    :param row: EventLog row。
    :param session_id: 当前 Session id。
    :param expected_event_type: 期望 event type。
    :returns: ``None``。
    :raises HostDurableError: session、class 或 event type 不匹配时抛出。
    """

    if row.session_id != session_id:
        raise HostDurableError("EventLog row session mismatch")
    if row.event_class is not EventClass.CANONICAL_FACT:
        raise HostDurableError("EventLog row is not canonical fact")
    if row.event_type != expected_event_type:
        raise HostDurableError("EventLog row event type mismatch")


def _event_log_row_from_host_row(row: HostRow) -> EventLogRow:
    """把 SQL row 转为 EventLogRow。

    :param row: Host transaction row。
    :returns: EventLogRow。
    :raises HostDurableError: 字段缺失或类型非法时抛出。
    """

    try:
        event_class = EventClass(_required_host_row_text(row, field_name="event_class"))
    except ValueError as exc:
        raise HostDurableError("EventLog row event_class is invalid") from exc
    return EventLogRow(
        event_sequence=_required_host_row_int(row, field_name="event_sequence"),
        event_id=_required_host_row_text(row, field_name="event_id"),
        event_body_digest=_required_host_row_text(row, field_name="event_body_digest"),
        event_class=event_class,
        session_id=_required_host_row_text(row, field_name="session_id"),
        run_id=_optional_host_row_text(row, field_name="run_id"),
        attempt_id=_optional_host_row_text(row, field_name="attempt_id"),
        execution_id=_optional_host_row_text(row, field_name="execution_id"),
        event_type=_required_host_row_text(row, field_name="event_type"),
        occurred_at=_required_host_row_text(row, field_name="occurred_at"),
        actor=_optional_host_row_text(row, field_name="actor"),
        source=_optional_host_row_text(row, field_name="source"),
        client_request_id=_optional_host_row_text(row, field_name="client_request_id"),
        idempotency_key=_optional_host_row_text(row, field_name="idempotency_key"),
        policy_decision_json=_optional_host_row_text(
            row,
            field_name="policy_decision_json",
        ),
        reason_json=_optional_host_row_text(row, field_name="reason_json"),
        payload_json=_required_host_row_text(row, field_name="payload_json"),
        payload_ref=_optional_host_row_text(row, field_name="payload_ref"),
        payload_digest=_optional_host_row_text(row, field_name="payload_digest"),
        appended_at=_required_host_row_text(row, field_name="appended_at"),
    )


def _required_host_row_text(row: HostRow, *, field_name: str) -> str:
    """读取 HostRow 必填文本字段。

    :param row: Host transaction row。
    :param field_name: 字段名。
    :returns: 非空文本。
    :raises HostDurableError: 字段缺失或非文本时抛出。
    """

    value = row.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    raise HostDurableError(f"{field_name} must be non-empty text")


def _optional_host_row_text(row: HostRow, *, field_name: str) -> str | None:
    """读取 HostRow 可选文本字段。

    :param row: Host transaction row。
    :param field_name: 字段名。
    :returns: 文本或 ``None``。
    :raises HostDurableError: 字段存在但非文本时抛出。
    """

    value = row.get(field_name)
    if value is None:
        return None
    if isinstance(value, str) and value.strip() != "":
        return value
    raise HostDurableError(f"{field_name} must be non-empty text when provided")


def _required_host_row_int(row: HostRow, *, field_name: str) -> int:
    """读取 HostRow 必填整数字段。

    :param row: Host transaction row。
    :param field_name: 字段名。
    :returns: 整数字段值。
    :raises HostDurableError: 字段缺失或非整数时抛出。
    """

    value = row.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise HostDurableError(f"{field_name} must be integer")
    return value


def _required_json_text(payload: Mapping[str, JsonValue], field_name: str) -> str:
    """读取 JSON object 必填非空文本字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 非空文本。
    :raises HostDurableError: 字段缺失或类型非法时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, str) and value.strip() != "":
        return value
    raise HostDurableError(f"payload field {field_name} must be non-empty text")


def _required_json_mapping(
    payload: Mapping[str, JsonValue], field_name: str
) -> Mapping[str, JsonValue]:
    """读取 JSON object 必填 object 字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 子 object。
    :raises HostDurableError: 字段缺失或非 object 时抛出。
    """

    return _json_mapping(payload.get(field_name), field_name)


def _json_mapping(value: JsonValue | None, field_name: str) -> Mapping[str, JsonValue]:
    """校验 JSON 值为 object。

    :param value: JSON 值。
    :param field_name: 字段名。
    :returns: JSON object。
    :raises HostDurableError: 值不是 object 时抛出。
    """

    if not isinstance(value, Mapping):
        raise HostDurableError(f"payload field {field_name} must be object")
    return value


def _required_json_mapping_tuple(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[Mapping[str, JsonValue], ...]:
    """读取 JSON object 必填 object list 字段。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: object tuple。
    :raises HostDurableError: 字段缺失或元素类型非法时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, list):
        raise HostDurableError(f"payload field {field_name} must be list")
    result: list[Mapping[str, JsonValue]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise HostDurableError(f"payload field {field_name} item must be object")
        result.append(item)
    return tuple(result)


def _required_json_text_tuple(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[str, ...]:
    """读取 JSON object 必填文本 list 字段并去重。

    :param payload: JSON object。
    :param field_name: 字段名。
    :returns: 去重后的文本 tuple。
    :raises HostDurableError: 字段缺失或元素非法时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, list):
        raise HostDurableError(f"payload field {field_name} must be list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or item.strip() == "":
            raise HostDurableError(f"payload field {field_name} item must be text")
        result.append(item)
    return tuple(dict.fromkeys(result))


def _payload_refs_for_event(row: EventLogRow) -> tuple[str, ...]:
    """返回 accepted evidence material 的 payload provenance refs。

    :param row: EventLog row。
    :returns: payload refs。
    """

    if row.payload_ref is not None:
        return (row.payload_ref,)
    return (f"{_PAYLOAD_REF_PREFIX}:{row.event_id}",)


def _trace_material_vnext(blocks: tuple[CompactMaterialBlock, ...]) -> tuple[TraceReadableItemVNext, ...]:
    """把 trace material blocks 映射为 vNext trace material。

    :param blocks: trace material blocks。
    :returns: vNext trace material tuple。
    """

    items: list[TraceReadableItemVNext] = []
    for block in blocks:
        if block.kind in (
            CompactMaterialBlockKind.USER_INPUT,
            CompactMaterialBlockKind.USER_VISIBLE_RUN_STATE,
        ):
            trace_kind = (
                TraceReadableKindVNext.USER_INPUT
                if block.kind is CompactMaterialBlockKind.USER_INPUT
                else TraceReadableKindVNext.USER_VISIBLE_PROGRESS
            )
            items.append(
                TraceReadableItemVNext(
                    source_label=block.block_label,
                    trace_kind=trace_kind,
                    text=block.text,
                )
            )
    return tuple(items)


def _answer_material_vnext(blocks: tuple[CompactMaterialBlock, ...]) -> tuple[AnswerReadableItemVNext, ...]:
    """把 answer material blocks 映射为 vNext answer material。

    :param blocks: answer material blocks。
    :returns: vNext answer material tuple。
    """

    items: list[AnswerReadableItemVNext] = []
    for block in blocks:
        if block.kind is CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER:
            items.append(AnswerReadableItemVNext(source_label=block.block_label, answer_text=block.text))
    return tuple(items)


def _evidence_material_vnext(blocks: tuple[CompactEvidenceBlock, ...]) -> tuple[EvidenceReadableItemVNext, ...]:
    """把 evidence material blocks 映射为 vNext evidence material。

    :param blocks: accepted evidence material blocks。
    :returns: vNext evidence material tuple。
    """

    items: list[EvidenceReadableItemVNext] = []
    for block in blocks:
        items.append(
            EvidenceReadableItemVNext(
                source_label=block.evidence_label,
                tool_name=block.readable_tool_name,
                query_text=block.readable_query_text,
                response_text=block.raw_result_text,
                source_note=block.readable_source_text,
            )
        )
    return tuple(items)


def _previous_compacted_fact_material_vnext(
    blocks: tuple[CompactMaterialBlock, ...],
) -> tuple[ReadableFactItemVNext, ...]:
    """把 previous evidence-backed fact block 映射为 vNext 可读 fact。

    :param blocks: previous compacted view material blocks。
    :returns: vNext readable fact tuple。
    """

    items: list[ReadableFactItemVNext] = []
    for block in blocks:
        if block.kind is CompactMaterialBlockKind.EVIDENCE_BACKED_FACT:
            items.append(ReadableFactItemVNext(source_label=block.block_label, claim_text=block.text))
    return tuple(items)


def _previous_compacted_answer_anchors_vnext(
    blocks: tuple[CompactMaterialBlock, ...],
) -> tuple[ReadableAnswerAnchorVNext, ...]:
    """把 previous answer anchor blocks 映射为 vNext 可读 anchor。

    :param blocks: previous compacted view material blocks。
    :returns: vNext answer anchor tuple。
    """

    items: list[ReadableAnswerAnchorVNext] = []
    for block in blocks:
        if block.kind is CompactMaterialBlockKind.ANSWER_ANCHOR:
            for line in block.text.splitlines():
                anchor_title = line.removeprefix(_PREVIOUS_ANSWER_ANCHOR_PREFIX)
                if anchor_title == line:
                    raise ValueError("previous answer anchor text is invalid")
                items.append(
                    ReadableAnswerAnchorVNext(
                        source_label=block.block_label,
                        anchor_title=anchor_title,
                        anchor_items=(
                            ReadableAnswerAnchorItemVNext(
                                display_text=anchor_title,
                                ordinal=None,
                            ),
                        ),
                    )
                )
    return tuple(items)


def _previous_compacted_forward_intents_vnext(
    blocks: tuple[CompactMaterialBlock, ...],
) -> tuple[ReadableForwardIntentVNext, ...]:
    """把 previous forward intent blocks 映射为 vNext 可读 intent。

    :param blocks: previous compacted view material blocks。
    :returns: vNext forward intent tuple。
    """

    items: list[ReadableForwardIntentVNext] = []
    for block in blocks:
        if block.kind is CompactMaterialBlockKind.FORWARD_INTENT:
            for line in block.text.splitlines():
                intent_type, status, text = _parse_previous_forward_intent_text(line)
                items.append(
                    ReadableForwardIntentVNext(
                        source_label=block.block_label,
                        intent_type=intent_type,
                        text=text,
                        status=status,
                    )
                )
    return tuple(items)


def _previous_compacted_references_vnext(
    blocks: tuple[CompactMaterialBlock, ...],
) -> tuple[ReadableReferenceContinuityItemVNext, ...]:
    """把 previous reference continuity blocks 映射为 vNext 可读 continuity item。

    :param blocks: previous compacted view material blocks。
    :returns: vNext reference continuity tuple。
    """

    items: list[ReadableReferenceContinuityItemVNext] = []
    for block in blocks:
        if block.kind is CompactMaterialBlockKind.REFERENCE_CONTINUITY:
            for line in block.text.splitlines():
                reason, text = _parse_previous_reference_continuity_text(line)
                items.append(
                    ReadableReferenceContinuityItemVNext(
                        source_label=block.block_label,
                        text=text,
                        reason=reason,
                    )
                )
    return tuple(items)


def _previous_compacted_view_vnext(blocks: tuple[CompactMaterialBlock, ...]) -> CompactReadableViewVNext | None:
    """把 previous compacted view blocks 映射为 vNext previous view。

    :param blocks: previous compacted view material blocks。
    :returns: vNext previous compacted view；无可迁移内容时返回 ``None``。
    """

    session_summary = _previous_compacted_session_summary_vnext(blocks)
    facts = _previous_compacted_fact_material_vnext(blocks)
    answer_anchors = _previous_compacted_answer_anchors_vnext(blocks)
    forward_intents = _previous_compacted_forward_intents_vnext(blocks)
    references = _previous_compacted_references_vnext(blocks)
    if (
        session_summary is None
        and len(facts) == 0
        and len(answer_anchors) == 0
        and len(forward_intents) == 0
        and len(references) == 0
    ):
        return None
    return CompactReadableViewVNext(
        session_summary=session_summary,
        evidence_backed_facts=facts,
        answer_anchors=answer_anchors,
        forward_intents=forward_intents,
        reference_continuity_items=references,
    )


def _previous_compacted_session_summary_vnext(
    blocks: tuple[CompactMaterialBlock, ...],
) -> str | None:
    """返回 previous view 的 session summary 文本。

    :param blocks: previous compacted view material blocks。
    :returns: session summary；无 summary block 时返回 ``None``。
    """

    for block in blocks:
        if block.kind is CompactMaterialBlockKind.SESSION_SUMMARY:
            return block.text
    return None


def _parse_previous_forward_intent_text(
    text: str,
) -> tuple[ForwardIntentTypeVNext, ForwardIntentStatusVNext, str]:
    """解析本模块生成的 previous forward intent 文本。

    :param text: ``_snapshot_forward_intent_texts`` 生成的单项文本。
    :returns: intent type、status 与可读文本。
    :raises ValueError: 文本格式或枚举值非法时抛出。
    """

    parts = text.split("; ")
    if len(parts) != 3:
        raise ValueError("previous forward intent text is invalid")
    intent_type_text = parts[0].removeprefix(_PREVIOUS_FORWARD_INTENT_PREFIX)
    status_text = parts[1].removeprefix(_PREVIOUS_FORWARD_STATUS_PREFIX)
    readable_text = parts[2].removeprefix(_PREVIOUS_FORWARD_TEXT_PREFIX)
    if (
        intent_type_text == parts[0]
        or status_text == parts[1]
        or readable_text == parts[2]
    ):
        raise ValueError("previous forward intent text is invalid")
    return (
        ForwardIntentTypeVNext(intent_type_text),
        ForwardIntentStatusVNext(status_text),
        readable_text,
    )


def _parse_previous_reference_continuity_text(
    text: str,
) -> tuple[ReferenceContinuityReasonVNext, str]:
    """解析本模块生成的 previous reference continuity 文本。

    :param text: ``_snapshot_reference_continuity_texts`` 生成的单项文本。
    :returns: reference reason 与可读文本。
    :raises ValueError: 文本格式或枚举值非法时抛出。
    """

    parts = text.split("; ")
    if len(parts) != 2:
        raise ValueError("previous reference continuity text is invalid")
    reason_text = parts[0].removeprefix(_PREVIOUS_REFERENCE_PREFIX)
    readable_text = parts[1].removeprefix(_PREVIOUS_REFERENCE_TEXT_PREFIX)
    if reason_text == parts[0] or readable_text == parts[1]:
        raise ValueError("previous reference continuity text is invalid")
    return ReferenceContinuityReasonVNext(reason_text), readable_text


def _require_string_tuple(value: tuple[str, ...], field_name: str) -> None:
    """校验字符串 tuple。

    :param value: 待校验 tuple。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    :raises ValueError: 元素为空时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        _require_non_empty_text(item, field_name)


def _require_opaque_evidence_ref_tuple(value: tuple[OpaqueEvidenceRef, ...], field_name: str) -> None:
    """校验 OpaqueEvidenceRef tuple。

    :param value: 待校验 tuple。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 字段不是 tuple 或元素类型不正确时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, OpaqueEvidenceRef):
            raise TypeError(f"{field_name} items must be OpaqueEvidenceRef")


def _require_optional_text(value: str | None, field_name: str) -> None:
    """校验可选文本。

    :param value: 待校验文本。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 字段类型非法时抛出。
    :raises ValueError: 文本为空时抛出。
    """

    if value is None:
        return
    _require_non_empty_text(value, field_name)


def _require_non_empty_text(value: str | None, field_name: str) -> None:
    """校验非空文本。

    :param value: 待校验文本。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises TypeError: 字段类型非法时抛出。
    :raises ValueError: 文本为空时抛出。
    """

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


__all__ = [
    "CompactMaterialBuildError",
    "CompactMaterialSourceBoundary",
    "CompactMemorySnapshotRepairRequired",
    "DuplicateMaterialSectionOwnerError",
    "InitialEvidenceMaterial",
    "InitialHistoryMaterial",
    "InlineDeltaRepairMaterialView",
    "PreDispatchCompactMaterialView",
    "RunInputMaterialBlock",
    "SnapshotCursorCheckKind",
    "SnapshotCursorCheckResult",
    "build_initial_material_pack",
    "build_compact_material_pack",
    "build_pre_dispatch_compact_material_view",
    "check_compact_memory_snapshot_cursor",
    "conversation_compact_input_vnext_from_material_pack",
    "current_input_anchor_label",
    "initial_segment_selection",
    "material_label",
    "normalized_material_text",
    "prompt_local_evidence_map",
    "run_input_material_block",
    "select_compact_segment",
    "selected_material_source_refs",
    "selected_material_view_digest",
    "validate_material_label",
]
