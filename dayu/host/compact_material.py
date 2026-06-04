"""Host compact material pack 与 prompt-local label helper。

本模块是 Phase 12.6 Slice 1 的 material/label owner。它只构造 Host
internal material pack，不读取业务工具、不写 EventLog、不向 Engine 暴露
Host provenance。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn

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
    CompactSegmentSelection,
    CompactSegmentTrigger,
    CurrentInputAnchor,
    PromptLocalEvidenceMap,
    PromptLocalMaterialLabel,
    PromptLocalProvenanceEntry,
    ReadableFactItemVNext,
    TraceReadableItemVNext,
    TraceReadableKindVNext,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.evidence import OpaqueEvidenceRef
from dayu.host.memory import (
    ConversationMemorySnapshot,
    MemoryDiagnostic,
    MemoryProjectionPolicy,
    MemoryRepairReason,
    MemoryRepairRequest,
    MemorySnapshotCursor,
    digest_memory_projection_policy,
)

_CURRENT_INPUT_PREFIX = "C"
_TRACE_PREFIX = "T"
_EVIDENCE_PREFIX = "E"
_PREVIOUS_PREFIX = "P"
_ANSWER_PREFIX = "A"
_LABEL_CHUNK_SEPARATOR = "."
_FIRST_ORDINAL = 1
_CURRENT_ANCHOR_ORDINAL = 1
_INITIAL_POLICY_DIGEST = "slice1-initial-policy"
_INITIAL_REASON_CURRENT = "slice1_current_anchor"
_INITIAL_REASON_TRACE = "slice1_trace_material"
_INITIAL_REASON_EVIDENCE = "slice1_evidence_material"
_INITIAL_REASON_PREVIOUS = "slice1_previous_compacted_view"
_INITIAL_REASON_ANSWER = "slice1_answer_material"
CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS = 1200
"""Current input anchor 允许直接暴露给 LLM 的最大字符数。"""

EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS = 4096
"""单个 evidence block 直接暴露给 LLM 前的确定性 chunk 字符上限。"""

_CURRENT_INPUT_TRUNCATED_MARKER = "\n[truncated_current_input_anchor]"
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

    snapshot: ConversationMemorySnapshot
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
    snapshot: ConversationMemorySnapshot
    inline_delta_repair_view: InlineDeltaRepairMaterialView | None
    requests_run_recovery: bool = False


@dataclass(frozen=True, slots=True)
class InitialHistoryMaterial:
    """Slice 1 初始 history material。

    :param canonical_source_ref: canonical source ref。
    :param text: 有界可读文本。
    :param kind: history block kind。
    """

    canonical_source_ref: str
    text: str
    kind: CompactMaterialBlockKind


@dataclass(frozen=True, slots=True)
class InitialEvidenceMaterial:
    """Slice 1 初始 evidence material。

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


@dataclass(frozen=True, slots=True)
class _EvidenceChunk:
    """Evidence material 的确定性 chunk 描述。"""

    label: PromptLocalMaterialLabel
    parent_label: PromptLocalMaterialLabel | None
    chunk_ordinal: int | None
    text: str
    content_digest: str


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


def evidence_chunk_label(evidence_ordinal: int, chunk_ordinal: int) -> PromptLocalMaterialLabel:
    """构造 evidence chunk prompt-local label。

    :param evidence_ordinal: evidence block ordinal。
    :param chunk_ordinal: chunk ordinal。
    :returns: prompt-local chunk label。
    :raises ValueError: ordinal 非法时抛出。
    """

    if evidence_ordinal < _FIRST_ORDINAL:
        raise ValueError("evidence_ordinal must be positive")
    if chunk_ordinal < _FIRST_ORDINAL:
        raise ValueError("chunk_ordinal must be positive")
    return f"{_EVIDENCE_PREFIX}{evidence_ordinal}" f"{_LABEL_CHUNK_SEPARATOR}{chunk_ordinal}"


def current_input_anchor_label() -> PromptLocalMaterialLabel:
    """返回 Slice 1 current input anchor label。

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
    :returns: 去除首尾空白并折叠连续空白后的文本。
    :raises TypeError: 文本类型非法时抛出。
    :raises ValueError: 规范化后为空时抛出。
    """

    if not isinstance(text, str):
        raise TypeError("text must be str")
    normalized = " ".join(text.split())
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
    recent_raw_turns_floor: int = 0,
    max_selected_size_units: int | None = None,
) -> CompactSegmentSelection:
    """按确定性规则选择 compact segment。

    :param trigger_source: proactive 或 reactive 触发来源。
    :param input_cursor: ordinary input material list 最大 EventLog cursor。
    :param memory_snapshot_cursor: memory snapshot cursor。
    :param policy_digest: context / memory policy digest。
    :param material_blocks: ordinary input 或 frozen overflow material list。
    :param recent_raw_turns_floor: 需要保护的 recent raw turn 数量。
    :param max_selected_size_units: 可选 selected segment 尺寸上限。
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
        recent_raw_turns_floor=recent_raw_turns_floor,
        max_selected_size_units=max_selected_size_units,
    )
    protected_recent_ids = _protected_recent_raw_block_ids(material_blocks, recent_raw_turns_floor)
    selected: list[str] = []
    excluded_reasons: dict[str, str] = {}
    selected_units = 0
    for block in _sorted_material_blocks(material_blocks, memory_snapshot_cursor=memory_snapshot_cursor):
        reason = _block_exclusion_reason(block, protected_recent_ids)
        if reason is not None:
            excluded_reasons[block.block_id] = reason
            continue
        if (
            max_selected_size_units is not None
            and selected_units + block.size_units > max_selected_size_units
            and len(selected) > 0
        ):
            excluded_reasons[block.block_id] = _REASON_BUDGET_LIMIT
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


def build_compact_material_pack(
    *,
    selected_segment: CompactSegmentSelection,
    material_blocks: tuple[RunInputMaterialBlock, ...],
    memory_snapshot: ConversationMemorySnapshot | None,
    inline_delta_repair_view: InlineDeltaRepairMaterialView | None,
    current_input_ref: str,
    current_input_text: str,
) -> CompactMaterialPack:
    """从 selected segment 和 memory view 构造 compact material pack。

    :param selected_segment: segment selection 输出。
    :param material_blocks: 与 selection 同源的 ordinary / frozen material list。
    :param memory_snapshot: ready memory snapshot；无 stable view 时可为 ``None``。
    :param inline_delta_repair_view: inline delta repair view；无 repair 时为 ``None``。
    :param current_input_ref: 当前 USER_INPUT_ACCEPTED canonical ref。
    :param current_input_text: 当前用户输入 display text。
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
    previous_blocks = _previous_blocks_from_snapshot(snapshot)
    trace_blocks = _pack_section_blocks(selected_blocks, CompactMaterialSection.TRACE_MATERIAL)
    evidence_blocks = _pack_evidence_blocks(selected_blocks)
    answer_blocks = _pack_section_blocks(selected_blocks, CompactMaterialSection.ANSWER_MATERIAL)
    provenance_entries = (
        *_provenance_from_blocks(previous_blocks),
        *_provenance_from_blocks(trace_blocks),
        *_provenance_from_evidence_blocks(evidence_blocks, selected_blocks),
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
    snapshot: ConversationMemorySnapshot | None,
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
            reason=MemoryRepairReason.SNAPSHOT_LAG_OVER_THRESHOLD,
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
    """构造 Slice 1 初始 compact material pack。

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
    """构造 Slice 1 初始 segment selection。

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
        for chunk in _evidence_chunks(index, material.raw_result_text):
            blocks.append(
                CompactEvidenceBlock(
                    evidence_label=chunk.label,
                    readable_tool_name=material.readable_tool_name,
                    readable_query_text=material.readable_query_text,
                    raw_result_text=chunk.text,
                    readable_source_text=material.readable_source_text,
                    size_units=len(chunk.text),
                    canonical_source_refs=(material.canonical_source_ref,),
                    content_digest=chunk.content_digest,
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
        for chunk in _evidence_chunks(index, material.raw_result_text):
            entries.append(
                PromptLocalProvenanceEntry(
                    label=chunk.label,
                    section=CompactMaterialSection.EVIDENCE_MATERIAL,
                    kind=CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
                    canonical_source_refs=(material.canonical_source_ref,),
                    source_event_refs=(material.tool_result_event_ref,),
                    content_digest=chunk.content_digest,
                    accepted_evidence_id=material.accepted_evidence_id,
                    tool_result_event_ref=material.tool_result_event_ref,
                    tool_call_event_ref=material.tool_call_event_ref,
                    payload_refs=material.payload_refs,
                    artifact_refs=material.artifact_refs,
                    source_locator_refs=material.source_locator_refs,
                    chunk_parent_label=chunk.parent_label,
                    chunk_ordinal=chunk.chunk_ordinal,
                )
            )
    return tuple(entries)


def _initial_reason_codes(pack: CompactMaterialPack) -> tuple[str, ...]:
    """构造 Slice 1 初始 reason codes。

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
    recent_raw_turns_floor: int,
    max_selected_size_units: int | None,
) -> None:
    """校验 segment selection 输入。

    :param trigger_source: 触发来源。
    :param input_cursor: 输入 cursor。
    :param memory_snapshot_cursor: memory snapshot cursor。
    :param policy_digest: policy digest。
    :param material_blocks: material blocks。
    :param recent_raw_turns_floor: protected raw turn floor。
    :param max_selected_size_units: 可选选择预算。
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
    if recent_raw_turns_floor < 0:
        raise ValueError("recent_raw_turns_floor must be non-negative")
    if max_selected_size_units is not None and max_selected_size_units < 0:
        raise ValueError("max_selected_size_units must be non-negative")


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


def _protected_recent_raw_block_ids(
    blocks: tuple[RunInputMaterialBlock, ...], recent_raw_turns_floor: int
) -> frozenset[str]:
    """计算 protected recent raw floor 对应 block ids。

    :param blocks: material blocks。
    :param recent_raw_turns_floor: recent raw turn 保底数量。
    :returns: protected block id 集合。
    """

    explicit = [block.block_id for block in blocks if block.protected_recent_raw_turn and _is_raw_turn_block(block)]
    if recent_raw_turns_floor == 0:
        return frozenset(explicit)
    raw_blocks = sorted(
        (block for block in blocks if _is_raw_turn_block(block)),
        key=lambda block: (
            _NO_EVENT_SEQUENCE if block.event_sequence is None else block.event_sequence,
            block.event_sub_index,
            block.block_id,
        ),
        reverse=True,
    )
    protected = [block.block_id for block in raw_blocks[:recent_raw_turns_floor]]
    protected.extend(explicit)
    return frozenset(protected)


def _is_raw_turn_block(block: RunInputMaterialBlock) -> bool:
    """判断 block 是否为 raw turn continuity。

    :param block: material block。
    :returns: raw user / assistant turn 返回 ``True``。
    """

    return block.kind in (
        CompactMaterialBlockKind.USER_INPUT,
        CompactMaterialBlockKind.ASSISTANT_FINAL_ANSWER,
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
    memory_snapshot: ConversationMemorySnapshot | None,
    inline_delta_repair_view: InlineDeltaRepairMaterialView | None,
) -> ConversationMemorySnapshot | None:
    """选取 material pack stable input 使用的 snapshot。

    :param memory_snapshot: ready memory snapshot。
    :param inline_delta_repair_view: inline repair view。
    :returns: 有效 snapshot 或 ``None``。
    """

    if inline_delta_repair_view is not None:
        return inline_delta_repair_view.snapshot
    return memory_snapshot


def _current_input_anchor(current_input_ref: str, current_input_text: str) -> CurrentInputAnchor:
    """构造 current input anchor。

    :param current_input_ref: current input canonical ref。
    :param current_input_text: current input display text。
    :returns: CurrentInputAnchor。
    """

    normalized = normalized_material_text(current_input_text)
    if len(normalized) <= CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS:
        anchor_text = normalized
        truncated = False
    else:
        prefix_len = CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS - len(_CURRENT_INPUT_TRUNCATED_MARKER)
        anchor_text = normalized[:prefix_len].rstrip() + _CURRENT_INPUT_TRUNCATED_MARKER
        truncated = True
    return CurrentInputAnchor(
        anchor_label=current_input_anchor_label(),
        anchor_text=anchor_text,
        truncated=truncated,
        canonical_source_refs=(current_input_ref,),
        content_digest=_text_digest(normalized),
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
    snapshot: ConversationMemorySnapshot | None,
) -> tuple[CompactMaterialBlock, ...]:
    """从 memory snapshot 构造 previous compacted view blocks。

    :param snapshot: memory snapshot。
    :returns: previous compacted view blocks。
    """

    if snapshot is None:
        return ()
    blocks: list[RunInputMaterialBlock] = []
    goals_text = _snapshot_goal_text(snapshot)
    if goals_text is not None:
        blocks.append(
            run_input_material_block(
                block_id=_STABLE_GOALS_BLOCK_ID,
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.SESSION_SUMMARY,
                text=goals_text,
                canonical_source_refs=(snapshot.snapshot_id,),
                event_sequence=None,
                event_sub_index=0,
            )
        )
    facts_text = _snapshot_facts_text(snapshot)
    if facts_text is not None:
        blocks.append(
            run_input_material_block(
                block_id=_STABLE_FACTS_BLOCK_ID,
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
                text=facts_text,
                canonical_source_refs=(snapshot.snapshot_id,),
                event_sequence=None,
                event_sub_index=1,
            )
        )
    assumptions_text = _snapshot_assumptions_text(snapshot)
    if assumptions_text is not None:
        blocks.append(
            run_input_material_block(
                block_id=_STABLE_ASSUMPTIONS_BLOCK_ID,
                section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
                kind=CompactMaterialBlockKind.FORWARD_INTENT,
                text=assumptions_text,
                canonical_source_refs=(snapshot.snapshot_id,),
                event_sequence=None,
                event_sub_index=2,
            )
        )
    return _pack_previous_blocks(tuple(blocks))


def _snapshot_goal_text(snapshot: ConversationMemorySnapshot) -> str | None:
    """构造 pinned goal / subject stable 文本。

    :param snapshot: memory snapshot。
    :returns: stable 文本；无内容时返回 ``None``。
    """

    lines: list[str] = []
    if snapshot.pinned_state.current_goal is not None:
        lines.append(f"current_goal={snapshot.pinned_state.current_goal}")
    for constraint in snapshot.pinned_state.user_constraints:
        lines.append(f"user_constraint={constraint}")
    for subject in snapshot.pinned_state.confirmed_subjects:
        lines.append(f"confirmed_subject={subject.ref_kind.value}:{subject.ref_id}")
    if not lines:
        return None
    return "\n".join(lines)


def _snapshot_facts_text(snapshot: ConversationMemorySnapshot) -> str | None:
    """构造 evidence-backed facts stable 文本。

    :param snapshot: memory snapshot。
    :returns: stable 文本；无内容时返回 ``None``。
    """

    if not snapshot.evidence_backed_facts:
        return None
    lines: list[str] = []
    for fact in snapshot.evidence_backed_facts:
        lines.append(
            "fact="
            f"claim_text={fact.claim_text}; "
            f"evidence_refs={','.join(fact.evidence_refs)}; "
            f"evidence_kind={fact.evidence_kind.value}"
        )
    return "\n".join(lines)


def _snapshot_assumptions_text(snapshot: ConversationMemorySnapshot) -> str | None:
    """构造 open questions / assumptions stable 文本。

    :param snapshot: memory snapshot。
    :returns: stable 文本；无内容时返回 ``None``。
    """

    lines: list[str] = []
    for question in snapshot.pinned_state.open_questions:
        lines.append(f"open_question={question}")
    for assumption in snapshot.working_assumptions:
        lines.append(f"working_assumption={assumption.assumption_summary}")
    if not lines:
        return None
    return "\n".join(lines)


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
        for chunk in _evidence_chunks(index, block.text):
            result.append(
                CompactEvidenceBlock(
                    evidence_label=chunk.label,
                    readable_tool_name=_required_text(
                        block.readable_tool_name,
                        "RunInputMaterialBlock.readable_tool_name",
                    ),
                    readable_query_text=_required_text(
                        block.readable_query_text,
                        "RunInputMaterialBlock.readable_query_text",
                    ),
                    raw_result_text=chunk.text,
                    readable_source_text=_required_text(
                        block.readable_source_text,
                        "RunInputMaterialBlock.readable_source_text",
                    ),
                    size_units=len(chunk.text),
                    canonical_source_refs=block.canonical_source_refs,
                    content_digest=chunk.content_digest,
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
    evidence_blocks: tuple[CompactEvidenceBlock, ...],
    selected_blocks: tuple[RunInputMaterialBlock, ...],
) -> tuple[PromptLocalProvenanceEntry, ...]:
    """构造 evidence provenance entries。

    :param evidence_blocks: prompt-local evidence blocks。
    :param selected_blocks: selected ordinary material blocks。
    :returns: provenance entries。
    """

    source_blocks = tuple(block for block in selected_blocks if block.section is CompactMaterialSection.EVIDENCE_MATERIAL)
    entries: list[PromptLocalProvenanceEntry] = []
    del evidence_blocks
    for index, source in enumerate(source_blocks, start=_FIRST_ORDINAL):
        for chunk in _evidence_chunks(index, source.text):
            entries.append(
                PromptLocalProvenanceEntry(
                    label=chunk.label,
                    section=CompactMaterialSection.EVIDENCE_MATERIAL,
                    kind=CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
                    canonical_source_refs=source.canonical_source_refs,
                    source_event_refs=(
                        _required_text(
                            source.tool_result_event_ref,
                            "RunInputMaterialBlock.tool_result_event_ref",
                        ),
                    ),
                    content_digest=chunk.content_digest,
                    accepted_evidence_id=_required_text(
                        source.accepted_evidence_id,
                        "RunInputMaterialBlock.accepted_evidence_id",
                    ),
                    tool_result_event_ref=_required_text(
                        source.tool_result_event_ref,
                        "RunInputMaterialBlock.tool_result_event_ref",
                    ),
                    tool_call_event_ref=_required_text(
                        source.tool_call_event_ref,
                        "RunInputMaterialBlock.tool_call_event_ref",
                    ),
                    payload_refs=source.payload_refs,
                    artifact_refs=source.artifact_refs,
                    source_locator_refs=source.source_locator_refs,
                    chunk_parent_label=chunk.parent_label,
                    chunk_ordinal=chunk.chunk_ordinal,
                )
            )
    return tuple(entries)


def _evidence_chunks(evidence_ordinal: int, text: str) -> tuple[_EvidenceChunk, ...]:
    """把单个 evidence text 拆成确定性 prompt-local chunks。

    :param evidence_ordinal: evidence section 内 ordinal。
    :param text: digest-checked raw evidence text。
    :returns: evidence chunk tuple；未超限时返回单个非 chunk label。
    :raises ValueError: text 为空或 ordinal 非法时抛出。
    """

    _require_non_empty_text(text, "evidence_text")
    if evidence_ordinal < _FIRST_ORDINAL:
        raise ValueError("evidence_ordinal must be positive")
    if len(text) <= EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS:
        return (
            _EvidenceChunk(
                label=material_label(
                    CompactMaterialSection.EVIDENCE_MATERIAL,
                    evidence_ordinal,
                ),
                parent_label=None,
                chunk_ordinal=None,
                text=text,
                content_digest=_text_digest(text),
            ),
        )
    chunks: list[_EvidenceChunk] = []
    parent_label = material_label(CompactMaterialSection.EVIDENCE_MATERIAL, evidence_ordinal)
    start = 0
    chunk_ordinal = _FIRST_ORDINAL
    while start < len(text):
        chunk_text = text[start : start + EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS]
        chunks.append(
            _EvidenceChunk(
                label=evidence_chunk_label(evidence_ordinal, chunk_ordinal),
                parent_label=parent_label,
                chunk_ordinal=chunk_ordinal,
                text=chunk_text,
                content_digest=_text_digest(chunk_text),
            )
        )
        start += EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS
        chunk_ordinal += 1
    return tuple(chunks)


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
    snapshot: ConversationMemorySnapshot,
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


def _trace_material_vnext(blocks: tuple[CompactMaterialBlock, ...]) -> tuple[TraceReadableItemVNext, ...]:
    """把 trace material blocks 映射为 vNext trace material。

    :param blocks: trace material blocks。
    :returns: vNext trace material tuple。
    """

    items: list[TraceReadableItemVNext] = []
    for block in blocks:
        if block.kind is CompactMaterialBlockKind.USER_INPUT:
            items.append(
                TraceReadableItemVNext(
                    source_label=block.block_label,
                    trace_kind=TraceReadableKindVNext.USER_INPUT,
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


def _previous_compacted_view_vnext(blocks: tuple[CompactMaterialBlock, ...]) -> CompactReadableViewVNext | None:
    """把 previous compacted view blocks 映射为 vNext previous view。

    :param blocks: previous compacted view material blocks。
    :returns: vNext previous compacted view；无可迁移内容时返回 ``None``。
    """

    facts = _previous_compacted_fact_material_vnext(blocks)
    if len(facts) == 0:
        return None
    return CompactReadableViewVNext(
        session_summary=None,
        evidence_backed_facts=facts,
        answer_anchors=(),
        forward_intents=(),
        reference_continuity_items=(),
    )


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


def _required_text(value: str | None, field_name: str) -> str:
    """读取非空可选文本。

    :param value: 待读取文本。
    :param field_name: 字段名。
    :returns: 非空文本。
    :raises TypeError: 字段类型非法时抛出。
    :raises ValueError: 文本为空时抛出。
    """

    _require_non_empty_text(value, field_name)
    if value is None:
        raise TypeError(f"{field_name} must be str")
    return value


__all__ = [
    "CURRENT_INPUT_ANCHOR_TEXT_MAX_CHARS",
    "EVIDENCE_BLOCK_CHUNK_TEXT_MAX_CHARS",
    "CompactMaterialBuildError",
    "CompactMemorySnapshotRepairRequired",
    "DuplicateMaterialSectionOwnerError",
    "InitialEvidenceMaterial",
    "InitialHistoryMaterial",
    "InlineDeltaRepairMaterialView",
    "RunInputMaterialBlock",
    "SnapshotCursorCheckKind",
    "SnapshotCursorCheckResult",
    "build_initial_material_pack",
    "build_compact_material_pack",
    "check_compact_memory_snapshot_cursor",
    "conversation_compact_input_vnext_from_material_pack",
    "current_input_anchor_label",
    "evidence_chunk_label",
    "initial_segment_selection",
    "material_label",
    "normalized_material_text",
    "prompt_local_evidence_map",
    "run_input_material_block",
    "select_compact_segment",
    "selected_material_source_refs",
    "validate_material_label",
]
