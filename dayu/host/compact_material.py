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
    CompactEvidenceBlock,
    CompactMaterialBlock,
    CompactMaterialBlockKind,
    CompactMaterialPack,
    CompactMaterialSection,
    PreviousCompactReadableView,
    EvidenceReadableItemVNext,
    CompactSegmentSelection,
    CompactSegmentSelectionScope,
    CompactSegmentTrigger,
    CurrentInputAnchor,
    CompactCandidateV3,
    PromptLocalEvidenceMap,
    PromptLocalMaterialLabel,
    PromptLocalProvenanceEntry,
    ReadableAnswerAnchorItemVNext,
    ReadableAnswerAnchorVNext,
    ReadableFactItemVNext,
    ReadableForwardIntentVNext,
    ReadableReferenceContinuityItemVNext,
    TraceReadableItemVNext,
    TraceReadableKindVNext,
    previous_answer_anchor_block_text,
    SelectedBlockProvenance,
    TurnGroupMembership,
    validate_previous_compacted_view_pair,
)
from dayu.host.context_budget import BudgetTextFragment
from dayu.host.context_event_payload import resolve_context_compacted_payload
from dayu.host.context_events import CONTEXT_COMPACTED
from dayu.host.compact_payload import parse_context_compacted_semantic_payload
from dayu.host.accepted_result_projection import (
    project_accepted_tool_result,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import EventClass, EventLogRow, EventLogStore
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.state import RunRow
from dayu.host.durable.transaction import HostRow, HostTransaction
from dayu.host.evidence import AcceptedToolEvidenceLLMMaterial
from dayu.host.evidence import render_accepted_tool_evidence_for_llm
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
_COLLECTIVE_EXCLUSION_PRECEDENCE = (
    _REASON_PROTECTED_CURRENT_INPUT,
    _REASON_PROTECTED_RECENT_RAW_FLOOR,
    _REASON_ALREADY_REPRESENTED,
    _REASON_PREVIOUS_COMPACTED_VIEW,
    _REASON_NOT_IN_SEGMENT,
)
_COLLECTIVE_EXCLUSION_PRIORITY = {reason: priority for priority, reason in enumerate(_COLLECTIVE_EXCLUSION_PRECEDENCE)}
_STABLE_GOALS_BLOCK_ID = "stable:goals"
_STABLE_FACTS_BLOCK_ID = "stable:evidence_backed_facts"
_STABLE_ASSUMPTIONS_BLOCK_ID = "stable:questions_assumptions"
_EVENT_TYPE_USER_INPUT_ACCEPTED = "USER_INPUT_ACCEPTED"
_EVENT_TYPE_RUN_SUCCEEDED = "RUN_SUCCEEDED"
_EVENT_TYPE_TOOL_RESULT_ACCEPTED = "TOOL_RESULT_ACCEPTED"
_EVENT_TYPE_TOOL_CALL_REQUESTED = "TOOL_CALL_REQUESTED"
_PAYLOAD_FIELD_DISPLAY_TEXT = "display_text"
_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS = "accepted_evidence_mapping_refs"
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
    :param accepted_tool_evidence: accepted tool evidence 的 LLM-facing typed material。
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
    accepted_tool_evidence: AcceptedToolEvidenceLLMMaterial | None = None

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
        if self.accepted_tool_evidence is not None and not isinstance(
            self.accepted_tool_evidence,
            AcceptedToolEvidenceLLMMaterial,
        ):
            raise TypeError("RunInputMaterialBlock.accepted_tool_evidence is invalid")
        is_evidence = (
            self.section is CompactMaterialSection.EVIDENCE_MATERIAL
            or self.kind is CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE
        )
        if is_evidence:
            if self.section is not CompactMaterialSection.EVIDENCE_MATERIAL:
                raise ValueError("accepted evidence block section is invalid")
            if self.kind is not CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE:
                raise ValueError("accepted evidence block kind is invalid")
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
            if len(self.payload_refs) == 0 and len(self.artifact_refs) == 0:
                raise ValueError("accepted evidence block requires payload or artifact refs")
            if self.accepted_tool_evidence is None:
                raise ValueError("accepted evidence block requires typed LLM material")
            if self.text != render_accepted_tool_evidence_for_llm(self.accepted_tool_evidence):
                raise ValueError("accepted evidence block text must use shared renderer")
        else:
            if (
                self.accepted_evidence_id is not None
                or self.tool_result_event_ref is not None
                or self.tool_call_event_ref is not None
                or len(self.payload_refs) > 0
                or len(self.artifact_refs) > 0
                or self.accepted_tool_evidence is not None
            ):
                raise ValueError("non-evidence block must not carry evidence provenance")


@dataclass(frozen=True, slots=True)
class _AtomicMaterialUnit:
    """selector 阶段一产生的原子 material unit。

    :param blocks: 按稳定 material 顺序排列的一个完整 group 或 singleton。
    :param membership: turn group 的完整 membership；singleton 时为 ``None``。
    """

    blocks: tuple[RunInputMaterialBlock, ...]
    membership: TurnGroupMembership | None


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
    :param previous_compacted_readable_view: 与 previous blocks 同源的 typed previous view。
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
    previous_compacted_readable_view: PreviousCompactReadableView | None
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
        validate_previous_compacted_view_pair(
            self.previous_compacted_view,
            self.previous_compacted_readable_view,
        )
        _require_non_empty_text(self.current_input_text, "current_input_text")
        if not isinstance(self.source_boundary, CompactMaterialSourceBoundary):
            raise TypeError("source_boundary must be CompactMaterialSourceBoundary")
        if self.latest_compacted_event_id != self.source_boundary.latest_compacted_event_id:
            raise ValueError("latest compacted event id boundary mismatch")
        if self.latest_compacted_event_sequence != self.source_boundary.latest_compacted_event_sequence:
            raise ValueError("latest compacted event sequence boundary mismatch")
        if self.post_compact_delta_start_sequence != self.source_boundary.post_compact_delta_start_sequence:
            raise ValueError("post compact delta start boundary mismatch")
        if self.post_compact_delta_end_sequence != self.source_boundary.post_compact_delta_end_sequence:
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
    previous_view, previous_readable_view = (
        ((), None)
        if latest_compact is None
        else _previous_compacted_view_pair_from_compacted_event(
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
        latest_compacted_event_sequence=(None if latest_compact is None else latest_compact.event_sequence),
        post_compact_delta_start_sequence=delta_start,
        post_compact_delta_end_sequence=current_event.event_sequence,
        current_input_event_sequence=current_event.event_sequence,
    )
    return PreDispatchCompactMaterialView(
        material_blocks=material_blocks,
        previous_compacted_view=previous_view,
        previous_compacted_readable_view=previous_readable_view,
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
    normalized_lines = tuple(_normalized_material_line(line) for line in text.splitlines())
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
    accepted_tool_evidence: AcceptedToolEvidenceLLMMaterial | None = None,
) -> RunInputMaterialBlock:
    """构造共享 ordinary input material block。

    :param block_id: ordinary material list 稳定 block id。
    :param section: compact section owner。
    :param kind: material kind。
    :param text: ordinary material 的原始文本，或 typed accepted evidence 的唯一
        renderer exact 文本。
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
    :param accepted_tool_evidence: accepted tool evidence 的 LLM-facing typed material。
    :returns: RunInputMaterialBlock。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: 参数值非法时抛出。
    """

    material_text = text if accepted_tool_evidence is not None else normalized_material_text(text)
    return RunInputMaterialBlock(
        block_id=block_id,
        section=section,
        kind=kind,
        text=material_text,
        size_units=len(material_text),
        canonical_source_refs=canonical_source_refs,
        content_digest=_text_digest(material_text),
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
        accepted_tool_evidence=accepted_tool_evidence,
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
    sorted_blocks = _sorted_material_blocks(
        material_blocks,
        memory_snapshot_cursor=memory_snapshot_cursor,
    )
    protected_recent_ids = _protected_recent_turn_group_block_ids(
        sorted_blocks,
        selected_recent_window_turn_floor,
    )
    atomic_units = _atomic_material_units(sorted_blocks)
    selected: list[str] = []
    excluded_reasons: dict[str, str] = {}
    eligible_units: list[_AtomicMaterialUnit] = []
    for unit in atomic_units:
        reason = _collective_exclusion_reason(
            unit,
            protected_recent_ids=protected_recent_ids,
        )
        if reason is None:
            eligible_units.append(unit)
            continue
        for block in unit.blocks:
            excluded_reasons[block.block_id] = reason

    selected_size_units = 0
    selected_item_count = 0
    budget_blocked = False
    for unit in eligible_units:
        if budget_blocked:
            for block in unit.blocks:
                excluded_reasons[block.block_id] = _REASON_BUDGET_LIMIT
            continue
        unit_size_units = sum(block.size_units for block in unit.blocks)
        unit_item_count = len(unit.blocks)
        exceeds_size_cap = (
            max_selected_size_units is not None and selected_size_units + unit_size_units > max_selected_size_units
        )
        exceeds_item_cap = (
            max_selected_item_count is not None and selected_item_count + unit_item_count > max_selected_item_count
        )
        if exceeds_size_cap or exceeds_item_cap:
            for block in unit.blocks:
                excluded_reasons[block.block_id] = _REASON_BUDGET_LIMIT
            budget_blocked = True
            continue
        selected.extend(block.block_id for block in unit.blocks)
        selected_size_units += unit_size_units
        selected_item_count += unit_item_count
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
    selected_provenance = selected_block_provenance_for_material_blocks(
        sorted_blocks,
        selected_block_ids=tuple(selected),
    )
    digest_input = {
        "scope": CompactSegmentSelectionScope.ROOT.value,
        "turn_group_memberships": [unit.membership.to_json() for unit in atomic_units if unit.membership is not None],
        "selected_block_provenance": [provenance.to_json() for provenance in selected_provenance],
        "root_selection_digest": None,
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
        scope=CompactSegmentSelectionScope.ROOT,
        turn_group_memberships=tuple(unit.membership for unit in atomic_units if unit.membership is not None),
        selected_block_provenance=selected_provenance,
        root_selection_digest=None,
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


def retained_previous_compacted_view_labels_for_recovery(
    previous_compacted_view: tuple[CompactMaterialBlock, ...],
) -> frozenset[PromptLocalMaterialLabel]:
    """按 recovery 优先级选择 previous compacted view 保留 labels。

    该 helper 只选择最高优先级的非空 semantic section，不直接过滤 blocks
    或 typed view；实际 pair 过滤必须走
    ``transform_previous_compacted_view_pair_for_recovery``。

    :param previous_compacted_view: latest accepted compacted view blocks。
    :returns: 保留的 prompt-local labels；无可保留项时为空集合。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: 参数值非法时抛出。
    """

    _require_compact_material_block_tuple(
        previous_compacted_view,
        "previous_compacted_view",
    )
    for kind in _RECOVERY_PREVIOUS_VIEW_KIND_PRIORITY:
        candidates = tuple((index, block) for index, block in enumerate(previous_compacted_view) if block.kind is kind)
        if len(candidates) > 0:
            return frozenset(block.block_label for _index, block in _sort_recovery_previous_blocks(candidates))
    return frozenset()


def transform_previous_compacted_view_pair_for_recovery(
    *,
    blocks: tuple[CompactMaterialBlock, ...],
    readable_view: PreviousCompactReadableView | None,
    retained_block_labels: frozenset[PromptLocalMaterialLabel],
) -> tuple[tuple[CompactMaterialBlock, ...], PreviousCompactReadableView | None]:
    """同步过滤 previous compacted blocks 与 typed readable view。

    :param blocks: 已验证 previous compacted view blocks。
    :param readable_view: 与 blocks 同源的 typed view。
    :param retained_block_labels: 需要保留的 block labels。
    :returns: 过滤后的 blocks / typed view pair。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: pair invariant 不成立时抛出。
    """

    validate_previous_compacted_view_pair(blocks, readable_view)
    if not isinstance(retained_block_labels, frozenset):
        raise TypeError("retained_block_labels must be frozenset")
    for label in retained_block_labels:
        _require_non_empty_text(label, "retained_block_labels item")
    retained_blocks = tuple(block for block in blocks if block.block_label in retained_block_labels)
    if len(retained_blocks) == 0:
        validate_previous_compacted_view_pair((), None)
        return (), None
    if readable_view is None:
        raise ValueError("readable_view is required with retained blocks")
    transformed_view = PreviousCompactReadableView(
        session_summary=(
            readable_view.session_summary
            if _has_retained_previous_kind(
                retained_blocks,
                CompactMaterialBlockKind.SESSION_SUMMARY,
            )
            else None
        ),
        evidence_backed_facts=_ordered_fact_items_for_blocks(
            retained_blocks,
            readable_view.evidence_backed_facts,
        ),
        answer_anchors=_ordered_answer_anchor_items_for_blocks(
            retained_blocks,
            readable_view.answer_anchors,
        ),
        forward_intents=_ordered_forward_intent_items_for_blocks(
            retained_blocks,
            readable_view.forward_intents,
        ),
        reference_continuity_items=_ordered_reference_items_for_blocks(
            retained_blocks,
            readable_view.reference_continuity_items,
        ),
    )
    validate_previous_compacted_view_pair(retained_blocks, transformed_view)
    return retained_blocks, transformed_view


def _has_retained_previous_kind(
    blocks: tuple[CompactMaterialBlock, ...],
    kind: CompactMaterialBlockKind,
) -> bool:
    """判断 filtered previous blocks 是否包含指定 kind。

    :param blocks: filtered previous blocks。
    :param kind: 目标 kind。
    :returns: 包含该 kind 时返回 ``True``。
    """

    return any(block.kind is kind for block in blocks)


def _ordered_fact_items_for_blocks(
    blocks: tuple[CompactMaterialBlock, ...],
    items: tuple[ReadableFactItemVNext, ...],
) -> tuple[ReadableFactItemVNext, ...]:
    """按 filtered fact block 顺序返回 typed readable facts。

    :param blocks: filtered previous blocks。
    :param items: typed readable fact items。
    :returns: 与 block 顺序一致的 fact item tuple。
    :raises ValueError: block label 找不到 typed item 时抛出。
    """

    item_by_label = {item.source_label: item for item in items}
    ordered: list[ReadableFactItemVNext] = []
    for block in blocks:
        if block.kind is not CompactMaterialBlockKind.EVIDENCE_BACKED_FACT:
            continue
        item = item_by_label.get(block.block_label)
        if item is None:
            raise ValueError("retained previous block label is missing from readable view")
        ordered.append(item)
    return tuple(ordered)


def _ordered_answer_anchor_items_for_blocks(
    blocks: tuple[CompactMaterialBlock, ...],
    items: tuple[ReadableAnswerAnchorVNext, ...],
) -> tuple[ReadableAnswerAnchorVNext, ...]:
    """按 filtered answer-anchor block 顺序返回 typed readable anchors。

    :param blocks: filtered previous blocks。
    :param items: typed readable answer anchors。
    :returns: 与 block 顺序一致的 answer anchor tuple。
    :raises ValueError: block label 找不到 typed item 时抛出。
    """

    item_by_label = {item.source_label: item for item in items}
    ordered: list[ReadableAnswerAnchorVNext] = []
    for block in blocks:
        if block.kind is not CompactMaterialBlockKind.ANSWER_ANCHOR:
            continue
        item = item_by_label.get(block.block_label)
        if item is None:
            raise ValueError("retained previous block label is missing from readable view")
        ordered.append(item)
    return tuple(ordered)


def _ordered_forward_intent_items_for_blocks(
    blocks: tuple[CompactMaterialBlock, ...],
    items: tuple[ReadableForwardIntentVNext, ...],
) -> tuple[ReadableForwardIntentVNext, ...]:
    """按 filtered forward-intent block 顺序返回 typed readable intents。

    :param blocks: filtered previous blocks。
    :param items: typed readable forward intents。
    :returns: 与 block 顺序一致的 forward intent tuple。
    :raises ValueError: block label 找不到 typed item 时抛出。
    """

    item_by_label = {item.source_label: item for item in items}
    ordered: list[ReadableForwardIntentVNext] = []
    for block in blocks:
        if block.kind is not CompactMaterialBlockKind.FORWARD_INTENT:
            continue
        item = item_by_label.get(block.block_label)
        if item is None:
            raise ValueError("retained previous block label is missing from readable view")
        ordered.append(item)
    return tuple(ordered)


def _ordered_reference_items_for_blocks(
    blocks: tuple[CompactMaterialBlock, ...],
    items: tuple[ReadableReferenceContinuityItemVNext, ...],
) -> tuple[ReadableReferenceContinuityItemVNext, ...]:
    """按 filtered reference-continuity block 顺序返回 typed readable references。

    :param blocks: filtered previous blocks。
    :param items: typed readable reference continuity items。
    :returns: 与 block 顺序一致的 reference continuity tuple。
    :raises ValueError: block label 找不到 typed item 时抛出。
    """

    item_by_label = {item.source_label: item for item in items}
    ordered: list[ReadableReferenceContinuityItemVNext] = []
    for block in blocks:
        if block.kind is not CompactMaterialBlockKind.REFERENCE_CONTINUITY:
            continue
        item = item_by_label.get(block.block_label)
        if item is None:
            raise ValueError("retained previous block label is missing from readable view")
        ordered.append(item)
    return tuple(ordered)


def build_compact_material_pack(
    *,
    selected_segment: CompactSegmentSelection,
    material_blocks: tuple[RunInputMaterialBlock, ...],
    memory_snapshot: ConversationMemorySnapshotVNext | None,
    inline_delta_repair_view: InlineDeltaRepairMaterialView | None,
    current_input_ref: str,
    current_input_text: str,
    previous_compacted_view: tuple[CompactMaterialBlock, ...] | None = None,
    previous_compacted_readable_view: PreviousCompactReadableView | None = None,
) -> CompactMaterialPack:
    """从 selected segment 和 memory view 构造 compact material pack。

    :param selected_segment: segment selection 输出。
    :param material_blocks: 与 selection 同源的 ordinary / frozen material list。
    :param memory_snapshot: ready memory snapshot；无 stable view 时可为 ``None``。
    :param inline_delta_repair_view: inline delta repair view；无 repair 时为 ``None``。
    :param current_input_ref: 当前 USER_INPUT_ACCEPTED canonical ref。
    :param current_input_text: 当前用户输入 display text。
    :param previous_compacted_view: 显式 previous view blocks。
    :param previous_compacted_readable_view: 与 previous blocks 同源的 typed previous view。
    :returns: CompactMaterialPack。
    :raises DuplicateMaterialSectionOwnerError: 同一 canonical content 跨 section 重复时抛出。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: 参数值非法时抛出。
    """

    if not isinstance(selected_segment, CompactSegmentSelection):
        raise TypeError("selected_segment must be CompactSegmentSelection")
    _require_material_block_tuple(material_blocks, "material_blocks")
    _require_non_empty_text(current_input_ref, "current_input_ref")
    current_anchor = _current_input_anchor(current_input_ref, current_input_text)
    selected_blocks = _selected_material_blocks(
        selected_segment.selected_block_ids,
        material_blocks,
    )
    if previous_compacted_view is None:
        previous_blocks = ()
        previous_readable_view = None
    else:
        _require_compact_material_block_tuple(
            previous_compacted_view,
            "previous_compacted_view",
        )
        previous_blocks = previous_compacted_view
        previous_readable_view = previous_compacted_readable_view
    validate_previous_compacted_view_pair(previous_blocks, previous_readable_view)
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
        previous_compacted_readable_view=previous_readable_view,
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
        previous_compacted_readable_view=None,
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

    selected = (
        *tuple(block.block_label for block in material_pack.trace_material),
        *tuple(block.evidence_label for block in material_pack.evidence_material),
        *tuple(block.block_label for block in material_pack.answer_material),
    )
    selected_provenance = _initial_selected_block_provenance(material_pack)
    excluded_reasons = {
        **{block.block_label: _REASON_PREVIOUS_COMPACTED_VIEW for block in material_pack.previous_compacted_view},
        material_pack.current_input_anchor.anchor_label: (_REASON_PROTECTED_CURRENT_INPUT),
    }
    reasons = _initial_reason_codes(material_pack)
    digest = sha256_digest_json(
        {
            "scope": CompactSegmentSelectionScope.ROOT.value,
            "turn_group_memberships": [],
            "selected_block_provenance": [provenance.to_json() for provenance in selected_provenance],
            "root_selection_digest": None,
            "selected_block_ids": list(selected),
            "excluded_protected_ids": [material_pack.current_input_anchor.anchor_label],
            "excluded_reason_codes": _ordered_reason_mapping(excluded_reasons),
            "trigger_source": trigger_source.value,
            "input_cursor": input_cursor,
            "policy_digest": _INITIAL_POLICY_DIGEST,
            "deterministic_reason_codes": list(reasons),
        }
    )
    return CompactSegmentSelection(
        scope=CompactSegmentSelectionScope.ROOT,
        turn_group_memberships=(),
        selected_block_provenance=selected_provenance,
        root_selection_digest=None,
        selected_block_ids=selected,
        excluded_protected_ids=(material_pack.current_input_anchor.anchor_label,),
        trigger_source=trigger_source,
        input_cursor=input_cursor,
        memory_snapshot_cursor=None,
        policy_digest=_INITIAL_POLICY_DIGEST,
        deterministic_reason_codes=reasons,
        selection_digest=digest,
        excluded_reason_codes=excluded_reasons,
    )


def _initial_selected_block_provenance(
    material_pack: CompactMaterialPack,
) -> tuple[SelectedBlockProvenance, ...]:
    """从已经构造的 initial pack 读取 selected block provenance。

    该 helper 只服务没有 raw source snapshot 的 initial test/smoke material
    builder；digest 直接消费最终 pack block，不重新解释 source 文本。

    :param material_pack: 已通过 typed validation 的 initial material pack。
    :returns: 与 initial selected labels 同序的 provenance tuple。
    """

    ordinary_blocks = (
        *material_pack.trace_material,
        *material_pack.answer_material,
    )
    ordinary_by_label = {block.block_label: block for block in ordinary_blocks}
    evidence_by_label = {block.evidence_label: block for block in material_pack.evidence_material}
    selected_labels = (
        *tuple(block.block_label for block in material_pack.trace_material),
        *tuple(block.evidence_label for block in material_pack.evidence_material),
        *tuple(block.block_label for block in material_pack.answer_material),
    )
    result: list[SelectedBlockProvenance] = []
    for label in selected_labels:
        ordinary = ordinary_by_label.get(label)
        if ordinary is not None:
            result.append(
                SelectedBlockProvenance(
                    block_id=label,
                    canonical_source_refs=ordinary.canonical_source_refs,
                    packed_content_digest=ordinary.content_digest,
                )
            )
            continue
        evidence = evidence_by_label[label]
        result.append(
            SelectedBlockProvenance(
                block_id=label,
                canonical_source_refs=evidence.canonical_source_refs,
                packed_content_digest=evidence.content_digest,
            )
        )
    return tuple(result)


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
                source_locator_refs=(),
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


def _packed_content_digest(block: RunInputMaterialBlock) -> str:
    """计算 selected source block 进入最终 material pack 后的内容 digest。

    :param block: selected source block。
    :returns: ordinary block 的 packed text digest，或 evidence result text digest。
    :raises HostDurableError: accepted evidence 缺少 typed material 时抛出。
    """

    if block.kind is CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE:
        if block.accepted_tool_evidence is None:
            raise HostDurableError("RunInputMaterialBlock.accepted_tool_evidence is required")
        return _text_digest(block.accepted_tool_evidence.result_text)
    return _text_digest(block.text)


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
    block_ids = tuple(block.block_id for block in material_blocks)
    if len(block_ids) != len(set(block_ids)):
        raise ValueError("material_blocks block_id values must be unique")
    if selected_recent_window_turn_floor < 0:
        raise ValueError("selected_recent_window_turn_floor must be non-negative")
    if max_selected_size_units is not None and max_selected_size_units < 0:
        raise ValueError("max_selected_size_units must be non-negative")
    if max_selected_item_count is not None and max_selected_item_count < 0:
        raise ValueError("max_selected_item_count must be non-negative")


def _sort_recovery_previous_blocks(
    indexed_blocks: tuple[tuple[int, CompactMaterialBlock], ...],
) -> tuple[tuple[int, CompactMaterialBlock], ...]:
    """按 S4 Decision 5 排序 previous compacted view recovery items。

    若所有候选 item 都带可解析 source EventLog sequence，则按最大 sequence
    降序；否则回退到原 material 顺序升序，再按稳定 block label 升序。

    :param indexed_blocks: 原始 material index 与 previous compact block。
    :returns: 排序后的 indexed blocks。
    """

    sequences = tuple(_max_recovery_source_event_sequence(block) for _index, block in indexed_blocks)
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


def _atomic_material_units(
    sorted_blocks: tuple[RunInputMaterialBlock, ...],
) -> tuple[_AtomicMaterialUnit, ...]:
    """把稳定排序后的 blocks 归并为 turn group 或 singleton 原子 unit。

    :param sorted_blocks: 已按 canonical material order 排序的 blocks。
    :returns: unit 按首成员位置排列，group 成员保持稳定顺序。
    :raises ValueError: turn material 缺 group id 时抛出。
    """

    grouped: dict[str, list[RunInputMaterialBlock]] = {}
    for block in sorted_blocks:
        if not is_turn_group_material_block(block):
            continue
        if block.turn_group_id is None:
            raise ValueError("turn-group material block is missing turn_group_id")
        grouped.setdefault(block.turn_group_id, []).append(block)

    emitted_groups: set[str] = set()
    units: list[_AtomicMaterialUnit] = []
    for block in sorted_blocks:
        if not is_turn_group_material_block(block):
            units.append(_AtomicMaterialUnit(blocks=(block,), membership=None))
            continue
        if block.turn_group_id is None:
            raise ValueError("turn-group material block is missing turn_group_id")
        if block.turn_group_id in emitted_groups:
            continue
        group_blocks = tuple(grouped[block.turn_group_id])
        units.append(
            _AtomicMaterialUnit(
                blocks=group_blocks,
                membership=TurnGroupMembership(
                    turn_group_id=block.turn_group_id,
                    member_block_ids=tuple(item.block_id for item in group_blocks),
                ),
            )
        )
        emitted_groups.add(block.turn_group_id)
    return tuple(units)


def turn_group_memberships_for_material_blocks(
    material_blocks: tuple[RunInputMaterialBlock, ...],
    *,
    memory_snapshot_cursor: int | None,
) -> tuple[TurnGroupMembership, ...]:
    """从 raw material blocks 派生 selector 使用的唯一完整 group proof。

    :param material_blocks: frozen source snapshot 的 raw blocks。
    :param memory_snapshot_cursor: stable block 排序所需 cursor。
    :returns: 按首成员 canonical 位置排列的完整 memberships。
    :raises TypeError: material block tuple 非法时抛出。
    :raises ValueError: block id 重复或 turn material 缺 group id 时抛出。
    """

    _require_material_block_tuple(material_blocks, "material_blocks")
    block_ids = tuple(block.block_id for block in material_blocks)
    if len(block_ids) != len(set(block_ids)):
        raise ValueError("material_blocks block_id values must be unique")
    units = _atomic_material_units(
        _sorted_material_blocks(
            material_blocks,
            memory_snapshot_cursor=memory_snapshot_cursor,
        )
    )
    return tuple(unit.membership for unit in units if unit.membership is not None)


def selected_block_provenance_for_material_blocks(
    material_blocks: tuple[RunInputMaterialBlock, ...],
    *,
    selected_block_ids: tuple[str, ...],
) -> tuple[SelectedBlockProvenance, ...]:
    """从 raw source blocks 机械派生 selected block 的最终 pack provenance。

    :param material_blocks: 同一 canonical source snapshot 的 raw blocks。
    :param selected_block_ids: selection 声明的 stable selected ids。
    :returns: 与 selected ids 同序一一对应的 provenance tuple。
    :raises TypeError: material blocks 或 selected ids 类型非法时抛出。
    :raises ValueError: block id 重复或 selected id 未知时抛出。
    :raises HostDurableError: accepted evidence 缺少 typed material 时抛出。
    """

    _require_material_block_tuple(material_blocks, "material_blocks")
    _require_string_tuple(selected_block_ids, "selected_block_ids")
    if len(selected_block_ids) != len(set(selected_block_ids)):
        raise ValueError("selected_block_ids must contain unique values")
    block_by_id = {block.block_id: block for block in material_blocks}
    if len(block_by_id) != len(material_blocks):
        raise ValueError("material_blocks block_id values must be unique")
    provenance: list[SelectedBlockProvenance] = []
    for block_id in selected_block_ids:
        block = block_by_id.get(block_id)
        if block is None:
            raise ValueError("selected block provenance references unknown material block")
        provenance.append(
            SelectedBlockProvenance(
                block_id=block.block_id,
                canonical_source_refs=block.canonical_source_refs,
                packed_content_digest=_packed_content_digest(block),
            )
        )
    return tuple(provenance)


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
        block.block_id for block in blocks if block.protected_recent_raw_turn and is_turn_group_material_block(block)
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
        if block.turn_group_id in protected_turn_group_ids and is_turn_group_material_block(block)
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
        event_sequence = _NO_EVENT_SEQUENCE if block.event_sequence is None else block.event_sequence
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


def _collective_exclusion_reason(
    unit: _AtomicMaterialUnit,
    *,
    protected_recent_ids: frozenset[str],
) -> str | None:
    """按固定 precedence 计算一个原子 unit 的 collective exclusion。

    :param unit: 完整 turn group 或 singleton unit。
    :param protected_recent_ids: protected recent raw ids。
    :returns: 全 unit 统一 reason；所有成员均 eligible 时为 ``None``。
    """

    reasons = tuple(
        reason for block in unit.blocks if (reason := _block_exclusion_reason(block, protected_recent_ids)) is not None
    )
    if len(reasons) == 0:
        return None
    return min(reasons, key=_COLLECTIVE_EXCLUSION_PRIORITY.__getitem__)


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
    try:
        return parse_context_compacted_semantic_payload(payload).accepted_evidence_mapping_refs
    except (TypeError, ValueError) as exc:
        raise HostDurableError("compact semantic payload is invalid") from exc


def _previous_compacted_view_pair_from_compacted_event(
    transaction: HostTransaction,
    row: EventLogRow,
) -> tuple[tuple[CompactMaterialBlock, ...], PreviousCompactReadableView | None]:
    """把 latest accepted compact candidate 映射为 previous compacted pair。

    :param transaction: 当前 Host transaction。
    :param row: ``CONTEXT_COMPACTED`` EventLog row。
    :returns: prompt-local previous compacted blocks 与 typed view。
    :raises HostDurableError: accepted candidate JSON 损坏或 digest 不匹配时抛出。
    """

    payload = _validated_compacted_payload(transaction, row)
    try:
        candidate = parse_context_compacted_semantic_payload(payload).accepted_candidate
    except (TypeError, ValueError) as exc:
        raise HostDurableError("compact semantic payload is invalid") from exc
    return _previous_compacted_view_pair_from_candidate(
        event_id=row.event_id,
        event_sequence=row.event_sequence,
        candidate=candidate,
    )


def _previous_compacted_view_pair_from_candidate(
    *,
    event_id: str,
    event_sequence: int,
    candidate: CompactCandidateV3,
) -> tuple[tuple[CompactMaterialBlock, ...], PreviousCompactReadableView | None]:
    """从 typed accepted candidate 原子生成 previous blocks 与 typed view。

    :param event_id: compacted EventLog id。
    :param event_sequence: compacted EventLog sequence。
    :param candidate: typed accepted candidate。
    :returns: 已通过 exact invariant 的 blocks / readable view pair。
    :raises HostDurableError: pair invariant 不成立时抛出。
    """

    blocks: list[RunInputMaterialBlock] = []
    if candidate.session_summary is not None:
        blocks.append(
            run_input_material_block(
                block_id=f"previous:{event_id}:session_summary",
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.SESSION_SUMMARY,
                text=candidate.session_summary.text,
                canonical_source_refs=(event_id,),
                event_sequence=event_sequence,
                event_sub_index=0,
            )
        )
    for index, fact in enumerate(candidate.evidence_facts, start=1):
        blocks.append(
            run_input_material_block(
                block_id=f"previous:{event_id}:evidence_backed_fact:{index}",
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
                text=fact.claim,
                canonical_source_refs=(event_id,),
                event_sequence=event_sequence,
                event_sub_index=len(blocks),
            )
        )
    readable_anchors = _readable_answer_anchors_from_candidate(candidate)
    for index, anchor in enumerate(readable_anchors, start=1):
        blocks.append(
            run_input_material_block(
                block_id=f"previous:{event_id}:answer_anchor:{index}",
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.ANSWER_ANCHOR,
                text=previous_answer_anchor_block_text(anchor),
                canonical_source_refs=(event_id,),
                event_sequence=event_sequence,
                event_sub_index=len(blocks),
            )
        )
    for index, intent in enumerate(candidate.forward_intents, start=1):
        blocks.append(
            run_input_material_block(
                block_id=f"previous:{event_id}:forward_intent:{index}",
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.FORWARD_INTENT,
                text=intent.text,
                canonical_source_refs=(event_id,),
                event_sequence=event_sequence,
                event_sub_index=len(blocks),
            )
        )
    for index, reference in enumerate(candidate.reference_continuity, start=1):
        blocks.append(
            run_input_material_block(
                block_id=f"previous:{event_id}:reference_continuity:{index}",
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.REFERENCE_CONTINUITY,
                text=reference.text,
                canonical_source_refs=(event_id,),
                event_sequence=event_sequence,
                event_sub_index=len(blocks),
            )
        )
    packed_blocks = _pack_previous_blocks(tuple(blocks))
    readable_view = _readable_previous_view_from_candidate(
        candidate,
        packed_blocks,
        readable_anchors=readable_anchors,
    )
    try:
        validate_previous_compacted_view_pair(packed_blocks, readable_view)
    except (TypeError, ValueError) as exc:
        raise HostDurableError("previous compacted view pair is invalid") from exc
    return packed_blocks, readable_view


def _readable_answer_anchors_from_candidate(
    candidate: CompactCandidateV3,
) -> tuple[ReadableAnswerAnchorVNext, ...]:
    """把 accepted candidate answer anchors 映射为无 label readable anchors。

    :param candidate: typed accepted candidate。
    :returns: 临时 label anchors；最终 label 由 packed blocks 覆盖。
    """

    anchors: list[ReadableAnswerAnchorVNext] = []
    for index, anchor in enumerate(candidate.answer_anchors, start=_FIRST_ORDINAL):
        anchors.append(
            ReadableAnswerAnchorVNext(
                source_label=material_label(
                    CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                    index,
                ),
                anchor_title=anchor.title,
                anchor_items=(
                    ReadableAnswerAnchorItemVNext(
                        display_text=anchor.detail,
                        ordinal=None,
                    ),
                ),
            )
        )
    return tuple(anchors)


def _readable_previous_view_from_candidate(
    candidate: CompactCandidateV3,
    blocks: tuple[CompactMaterialBlock, ...],
    *,
    readable_anchors: tuple[ReadableAnswerAnchorVNext, ...],
) -> PreviousCompactReadableView | None:
    """从 typed candidate 和 packed blocks 生成 typed previous view。

    :param candidate: typed accepted candidate。
    :param blocks: 已生成的 previous compacted blocks。
    :param readable_anchors: candidate answer anchors 的 typed value。
    :returns: typed previous view；candidate 无内容时返回 ``None``。
    :raises HostDurableError: block label 数量与 typed candidate 不一致时抛出。
    """

    fact_labels = _labels_for_previous_kind(
        blocks,
        CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
    )
    anchor_labels = _labels_for_previous_kind(
        blocks,
        CompactMaterialBlockKind.ANSWER_ANCHOR,
    )
    intent_labels = _labels_for_previous_kind(
        blocks,
        CompactMaterialBlockKind.FORWARD_INTENT,
    )
    reference_labels = _labels_for_previous_kind(
        blocks,
        CompactMaterialBlockKind.REFERENCE_CONTINUITY,
    )
    if (
        len(fact_labels) != len(candidate.evidence_facts)
        or len(anchor_labels) != len(readable_anchors)
        or len(intent_labels) != len(candidate.forward_intents)
        or len(reference_labels) != len(candidate.reference_continuity)
    ):
        raise HostDurableError("previous compacted view label count mismatch")
    if (
        candidate.session_summary is None
        and len(candidate.evidence_facts) == 0
        and len(candidate.answer_anchors) == 0
        and len(candidate.forward_intents) == 0
        and len(candidate.reference_continuity) == 0
    ):
        return None
    return PreviousCompactReadableView(
        session_summary=(None if candidate.session_summary is None else candidate.session_summary.text),
        evidence_backed_facts=tuple(
            ReadableFactItemVNext(
                source_label=label,
                claim_text=fact.claim,
            )
            for label, fact in zip(
                fact_labels,
                candidate.evidence_facts,
                strict=True,
            )
        ),
        answer_anchors=tuple(
            ReadableAnswerAnchorVNext(
                source_label=label,
                anchor_title=anchor.anchor_title,
                anchor_items=anchor.anchor_items,
            )
            for label, anchor in zip(anchor_labels, readable_anchors, strict=True)
        ),
        forward_intents=tuple(
            ReadableForwardIntentVNext(
                source_label=label,
                intent_type=intent.intent_type,
                text=intent.text,
                status=intent.status,
            )
            for label, intent in zip(
                intent_labels,
                candidate.forward_intents,
                strict=True,
            )
        ),
        reference_continuity_items=tuple(
            ReadableReferenceContinuityItemVNext(
                source_label=label,
                text=item.text,
                reason=item.reason,
            )
            for label, item in zip(
                reference_labels,
                candidate.reference_continuity,
                strict=True,
            )
        ),
    )


def _labels_for_previous_kind(
    blocks: tuple[CompactMaterialBlock, ...],
    kind: CompactMaterialBlockKind,
) -> tuple[PromptLocalMaterialLabel, ...]:
    """返回 previous compacted view 指定 kind 的 block labels。

    :param blocks: previous compacted blocks。
    :param kind: 目标 kind。
    :returns: label tuple。
    """

    return tuple(block.block_label for block in blocks if block.kind is kind)


def _validated_compacted_payload(transaction: HostTransaction, row: EventLogRow) -> Mapping[str, JsonValue]:
    """读取并校验 ``CONTEXT_COMPACTED`` payload。

    :param transaction: 当前 Host transaction。
    :param row: compacted EventLog row。
    :returns: compacted payload object。
    :raises HostDurableError: payload 结构或 digest 非法时抛出。
    """

    return resolve_context_compacted_payload(transaction, row)


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

    accepted evidence envelope 声明 request provenance 时，必须由共享
    accepted-result projection 证明该 ref 指向同 identity 的 canonical
    ``TOOL_CALL_REQUESTED`` request atom；缺失或不一致一律 fail closed。

    :param transaction: 当前 Host transaction。
    :param event_log_store: EventLog store。
    :param row: accepted tool result EventLog row。
    :param represented_evidence_refs: latest compact 已覆盖的 evidence refs。
    :returns: evidence material blocks。
    :raises HostDurableError: evidence envelope 或 raw tool payload 损坏时抛出。
    """

    resolved_payload = event_payload_object(
        transaction,
        row,
        payload_label=_EVENT_TYPE_TOOL_RESULT_ACCEPTED,
    )
    projection = project_accepted_tool_result(
        transaction,
        row,
        resolved_payload=resolved_payload,
    )
    if not projection.envelope_available:
        return ()
    tool_call_event_ref = projection.tool_call_requested_event_ref
    if tool_call_event_ref is None:
        raise HostDurableError("accepted evidence tool_call_requested_event_ref is missing")
    if projection.request_arguments_json is None:
        raise HostDurableError("accepted evidence tool call request provenance is invalid")
    if projection.evidence_id in represented_evidence_refs:
        return ()
    if projection.llm_material is None:
        raise HostDurableError("TOOL_RESULT_ACCEPTED raw_tool_outcome is missing")
    payload_refs = tuple(dict.fromkeys((*projection.payload_refs, *_payload_refs_for_event(row))))
    return (
        run_input_material_block(
            block_id=f"eventlog:evidence:{row.event_id}:{projection.evidence_id}",
            section=CompactMaterialSection.EVIDENCE_MATERIAL,
            kind=CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
            text=render_accepted_tool_evidence_for_llm(projection.llm_material),
            canonical_source_refs=(projection.evidence_id,),
            event_sequence=row.event_sequence,
            turn_group_id=row.run_id,
            accepted_evidence_id=projection.evidence_id,
            tool_result_event_ref=row.event_id,
            tool_call_event_ref=tool_call_event_ref,
            payload_refs=payload_refs,
            accepted_tool_evidence=projection.llm_material,
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
) -> tuple[RunInputMaterialBlock, ...]:
    """按 selection ids 一项不漏地取回 material blocks。

    :param selected_block_ids: selection 输出的 ordinary block ids。
    :param material_blocks: 同源 material list。
    :returns: selected material blocks。
    :raises ValueError: selection 引用未知 block id 时抛出。
    """

    block_by_id = {block.block_id: block for block in material_blocks}
    selected: list[RunInputMaterialBlock] = []
    for block_id in selected_block_ids:
        block = block_by_id.get(block_id)
        if block is None:
            raise ValueError("selected segment references unknown material block")
        selected.append(block)
    return tuple(selected)


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
        content_digest=_packed_content_digest(block),
    )


def _pack_evidence_blocks(blocks: tuple[RunInputMaterialBlock, ...]) -> tuple[CompactEvidenceBlock, ...]:
    """把 selected evidence material 转为 prompt-local evidence blocks。

    :param blocks: selected material blocks。
    :returns: CompactEvidenceBlock tuple。
    """

    result: list[CompactEvidenceBlock] = []
    evidence_blocks = tuple(block for block in blocks if block.section is CompactMaterialSection.EVIDENCE_MATERIAL)
    for index, block in enumerate(evidence_blocks, start=_FIRST_ORDINAL):
        if block.accepted_tool_evidence is None:
            raise HostDurableError("RunInputMaterialBlock.accepted_tool_evidence is required")
        _require_non_empty_text(block.text, "evidence_text")
        material = block.accepted_tool_evidence
        result.append(
            CompactEvidenceBlock(
                evidence_label=material_label(CompactMaterialSection.EVIDENCE_MATERIAL, index),
                readable_tool_name=material.tool_name,
                readable_query_text=material.query_text,
                raw_result_text=material.result_text,
                readable_source_text=material.source_text,
                size_units=len(material.result_text),
                canonical_source_refs=block.canonical_source_refs,
                content_digest=_packed_content_digest(block),
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

    source_blocks = tuple(
        block for block in selected_blocks if block.section is CompactMaterialSection.EVIDENCE_MATERIAL
    )
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
                content_digest=_packed_content_digest(source),
                accepted_evidence_id=source.accepted_evidence_id,
                tool_result_event_ref=source.tool_result_event_ref,
                tool_call_event_ref=source.tool_call_event_ref,
                payload_refs=source.payload_refs,
                artifact_refs=source.artifact_refs,
                source_locator_refs=(),
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
        if entry.section is CompactMaterialSection.CURRENT_INPUT_ANCHOR:
            continue
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


def _require_compact_material_block_tuple(value: tuple[CompactMaterialBlock, ...], field_name: str) -> None:
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


def _require_budget_fragment_tuple(value: tuple[BudgetTextFragment, ...], field_name: str) -> None:
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


def _required_json_text_tuple(payload: Mapping[str, JsonValue], field_name: str) -> tuple[str, ...]:
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
    "current_input_anchor_label",
    "initial_segment_selection",
    "material_label",
    "normalized_material_text",
    "prompt_local_evidence_map",
    "retained_previous_compacted_view_labels_for_recovery",
    "run_input_material_block",
    "select_compact_segment",
    "selected_material_source_refs",
    "selected_material_view_digest",
    "selected_block_provenance_for_material_blocks",
    "transform_previous_compacted_view_pair_for_recovery",
    "turn_group_memberships_for_material_blocks",
    "validate_material_label",
]
