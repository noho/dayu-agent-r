"""Host context compaction typed contracts。

本模块定义 Phase 10 Context Governance 使用的 compactor 输入、候选输出、
preservation evidence 与 quality check 结果。它只表达 Host-owned typed
boundary，不调用 LLM、不写 EventLog、不更新 memory projection。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.host._public_validation import (
    require_non_empty as _require_non_empty,
)
from dayu.host._public_validation import (
    require_non_negative_int as _require_non_negative_int,
)
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.evidence import OpaqueEvidenceRef

MAX_EVIDENCE_BACKED_FACT_CANDIDATES = 64
"""单个 compact candidate 允许输出的 evidence-backed fact candidate 上限。"""

MAX_MINIMUM_PRESERVE_ITEM_CANDIDATES = 32
"""单个 compact candidate 允许输出的 minimum preserve item candidate 上限。"""

MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS = 2000
"""Evidence-backed fact claim_text 字符数上限。"""

MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS = 1200
"""Minimum preserve item text 字符数上限。"""

MAX_MINIMUM_PRESERVE_ITEM_LABEL_CHARS = 120
"""Minimum preserve item label 字符数上限。"""

MAX_EVIDENCE_BACKED_FACT_ATTRIBUTES_JSON_CHARS = 4096
"""Evidence-backed fact attributes canonical JSON 字符数上限。"""

MAX_EVIDENCE_REFS_PER_FACT = 16
"""单个 evidence-backed fact candidate 允许引用的 canonical evidence refs 上限。"""

MAX_SOURCE_REFS_PER_MINIMUM_PRESERVE_ITEM = 16
"""单个 minimum preserve item candidate 允许引用的 source refs 上限。"""


class PinnedPatchOperation(StrEnum):
    """Pinned state 字段 patch 操作。"""

    MISSING = "missing"
    CLEAR = "clear"
    REPLACE = "replace"


class CompactQualityIssue(StrEnum):
    """Compact quality check 拒绝原因。"""

    CURRENT_USER_INPUT_MISSING = "current_user_input_missing"
    ACCEPTED_EVIDENCE_REFS_MISSING = "canonical_evidence_refs_missing"
    SUMMARY_PRETENDS_EVIDENCE_BACKED_FACT = "summary_pretends_evidence_backed_fact"
    EVIDENCE_LABELS_MISSING = "evidence_labels_missing"
    PRESERVATION_EVIDENCE_MISSING = "preservation_evidence_missing"
    EVIDENCE_ANCHOR_NOT_RETAINED = "evidence_anchor_not_retained"
    PINNED_PATCH_TRI_STATE_INVALID = "pinned_patch_tri_state_invalid"
    PINNED_PATCH_EVIDENCE_REF_MISSING = "pinned_patch_evidence_ref_missing"
    COMPACT_RANGE_OUTSIDE_REQUEST = "compact_range_outside_request"
    EVIDENCE_BACKED_FACT_CANDIDATE_INVALID = (
        "evidence_backed_fact_candidate_invalid"
    )
    ACCEPTED_EVIDENCE_FACT_CANDIDATE_MISSING = (
        "accepted_evidence_fact_candidate_missing"
    )
    MINIMUM_PRESERVE_ITEM_CANDIDATE_INVALID = (
        "minimum_preserve_item_candidate_invalid"
    )
    OPEN_QUESTIONS_MISSING = "open_questions_missing"


class EvidenceBackedFactKind(StrEnum):
    """Evidence-backed fact candidate 的 Host-neutral 类型。"""

    OBSERVED_VALUE = "observed_value"
    QUOTED_STATEMENT = "quoted_statement"
    TABLE_VALUE = "table_value"
    DERIVED_FROM_EVIDENCE = "derived_from_evidence"


class CompactMaterialSection(StrEnum):
    """Compact material pack 的 LLM-facing section。"""

    STABLE_INPUT = "stable_input"
    HISTORY_INPUT = "history_input"
    EVIDENCE_INPUT = "evidence_input"
    CURRENT_INPUT_ANCHOR = "current_input_anchor"


class CompactMaterialBlockKind(StrEnum):
    """Compact material block 的 Host-neutral 类型。"""

    PINNED_STATE = "pinned_state"
    EVIDENCE_BACKED_FACT = "evidence_backed_fact"
    WORKING_ASSUMPTION = "working_assumption"
    OPEN_QUESTION = "open_question"
    RAW_USER_TURN = "raw_user_turn"
    RAW_ASSISTANT_TURN = "raw_assistant_turn"
    EPISODE_SUMMARY = "episode_summary"
    ACCEPTED_TOOL_EVIDENCE = "accepted_tool_evidence"
    CURRENT_INPUT_ANCHOR = "current_input_anchor"


class CompactSegmentTrigger(StrEnum):
    """Compact segment selection 的触发来源。"""

    PROACTIVE = "proactive"
    REACTIVE = "reactive"


PromptLocalMaterialLabel = str
"""Prompt-local material label 的类型别名。"""


class MinimumPreserveReason(StrEnum):
    """Minimum preserve item 的保留原因。"""

    NEEDED_FOR_RECENT_REFERENCE = "needed_for_recent_reference"
    NEEDED_FOR_ORDERED_ITEM_REFERENCE = "needed_for_ordered_item_reference"
    NEEDED_FOR_LOCAL_FOLLOWUP = "needed_for_local_followup"


def _empty_string_tuple() -> tuple[str, ...]:
    """返回空字符串 tuple。

    :returns: 空 tuple。
    """

    return ()


@dataclass(frozen=True, slots=True)
class CompactInputRange:
    """Compact 输入范围引用。

    :param range_ref: 输入范围引用。
    :param start_input_ref: 范围起点输入 ref。
    :param end_input_ref: 范围终点输入 ref。
    """

    range_ref: str
    start_input_ref: str
    end_input_ref: str

    def __post_init__(self) -> None:
        """校验输入范围字段。

        :returns: ``None``。
        :raises ValueError: 文本字段为空时抛出。
        """

        _require_non_empty(self.range_ref, field_name="CompactInputRange.range_ref")
        _require_non_empty(
            self.start_input_ref, field_name="CompactInputRange.start_input_ref"
        )
        _require_non_empty(
            self.end_input_ref, field_name="CompactInputRange.end_input_ref"
        )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "range_ref": self.range_ref,
            "start_input_ref": self.start_input_ref,
            "end_input_ref": self.end_input_ref,
        }


@dataclass(frozen=True, slots=True)
class PromptLocalProvenanceEntry:
    """Prompt-local label 到 canonical provenance 的内部映射。

    :param label: prompt-local label。
    :param section: material section。
    :param kind: material block kind。
    :param canonical_source_refs: canonical source refs。
    :param source_event_refs: 来源 EventLog refs。
    :param content_digest: material 内容 digest。
    :param accepted_evidence_id: evidence entry 对应的 canonical evidence id。
    :param tool_result_event_ref: evidence entry 对应 TOOL_RESULT_ACCEPTED ref。
    :param tool_call_event_ref: evidence entry 对应 TOOL_CALL_REQUESTED ref。
    :param payload_refs: payload / artifact refs。
    :param artifact_refs: artifact refs。
    :param source_locator_refs: source locator refs。
    :param chunk_parent_label: evidence chunk 的父 label。
    :param chunk_ordinal: evidence chunk ordinal。
    """

    label: PromptLocalMaterialLabel
    section: CompactMaterialSection
    kind: CompactMaterialBlockKind
    canonical_source_refs: tuple[str, ...]
    source_event_refs: tuple[str, ...]
    content_digest: str
    accepted_evidence_id: str | None
    tool_result_event_ref: str | None
    tool_call_event_ref: str | None
    payload_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    source_locator_refs: tuple[OpaqueEvidenceRef, ...]
    chunk_parent_label: PromptLocalMaterialLabel | None = None
    chunk_ordinal: int | None = None

    def __post_init__(self) -> None:
        """校验 provenance entry。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_non_empty(self.label, field_name="PromptLocalProvenanceEntry.label")
        if not isinstance(self.section, CompactMaterialSection):
            raise TypeError("PromptLocalProvenanceEntry.section is invalid")
        if not isinstance(self.kind, CompactMaterialBlockKind):
            raise TypeError("PromptLocalProvenanceEntry.kind is invalid")
        _require_string_tuple(
            self.canonical_source_refs,
            field_name="PromptLocalProvenanceEntry.canonical_source_refs",
        )
        _require_string_tuple(
            self.source_event_refs,
            field_name="PromptLocalProvenanceEntry.source_event_refs",
        )
        _require_non_empty(
            self.content_digest,
            field_name="PromptLocalProvenanceEntry.content_digest",
        )
        _require_optional_non_empty(
            self.accepted_evidence_id,
            field_name="PromptLocalProvenanceEntry.accepted_evidence_id",
        )
        _require_optional_non_empty(
            self.tool_result_event_ref,
            field_name="PromptLocalProvenanceEntry.tool_result_event_ref",
        )
        _require_optional_non_empty(
            self.tool_call_event_ref,
            field_name="PromptLocalProvenanceEntry.tool_call_event_ref",
        )
        _require_string_tuple(
            self.payload_refs, field_name="PromptLocalProvenanceEntry.payload_refs"
        )
        _require_string_tuple(
            self.artifact_refs, field_name="PromptLocalProvenanceEntry.artifact_refs"
        )
        _require_opaque_ref_tuple(
            self.source_locator_refs,
            field_name="PromptLocalProvenanceEntry.source_locator_refs",
        )
        _require_optional_non_empty(
            self.chunk_parent_label,
            field_name="PromptLocalProvenanceEntry.chunk_parent_label",
        )
        if self.chunk_ordinal is not None:
            _require_non_negative_int(
                self.chunk_ordinal,
                field_name="PromptLocalProvenanceEntry.chunk_ordinal",
            )
        if self.section is CompactMaterialSection.EVIDENCE_INPUT:
            if self.accepted_evidence_id is None:
                raise ValueError(
                    "PromptLocalProvenanceEntry.accepted_evidence_id is required"
                )
            _require_non_empty(
                self.accepted_evidence_id,
                field_name="PromptLocalProvenanceEntry.accepted_evidence_id",
            )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "label": self.label,
            "section": self.section.value,
            "kind": self.kind.value,
            "canonical_source_refs": _string_list_json(self.canonical_source_refs),
            "source_event_refs": _string_list_json(self.source_event_refs),
            "content_digest": self.content_digest,
            "accepted_evidence_id": self.accepted_evidence_id,
            "tool_result_event_ref": self.tool_result_event_ref,
            "tool_call_event_ref": self.tool_call_event_ref,
            "payload_refs": _string_list_json(self.payload_refs),
            "artifact_refs": _string_list_json(self.artifact_refs),
            "source_locator_refs": _opaque_ref_list_json(self.source_locator_refs),
            "chunk_parent_label": self.chunk_parent_label,
            "chunk_ordinal": self.chunk_ordinal,
        }


PromptLocalEvidenceMap = Mapping[
    PromptLocalMaterialLabel, PromptLocalProvenanceEntry
]
"""Evidence label 到 provenance entry 的只读 typed view。"""


@dataclass(frozen=True, slots=True)
class CompactMaterialBlock:
    """Compact material pack 的普通 material block。

    :param block_label: prompt-local block label。
    :param section: material section。
    :param kind: material block kind。
    :param text: 有界可读文本。
    :param size_units: 文本 size units。
    :param source_labels: 该 block 引用的 prompt-local source labels。
    :param canonical_source_refs: canonical source refs。
    :param content_digest: 文本 digest。
    """

    block_label: PromptLocalMaterialLabel
    section: CompactMaterialSection
    kind: CompactMaterialBlockKind
    text: str
    size_units: int
    source_labels: tuple[PromptLocalMaterialLabel, ...]
    canonical_source_refs: tuple[str, ...]
    content_digest: str

    def __post_init__(self) -> None:
        """校验 material block。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_non_empty(self.block_label, field_name="CompactMaterialBlock.block_label")
        if not isinstance(self.section, CompactMaterialSection):
            raise TypeError("CompactMaterialBlock.section is invalid")
        if not isinstance(self.kind, CompactMaterialBlockKind):
            raise TypeError("CompactMaterialBlock.kind is invalid")
        _require_non_empty(self.text, field_name="CompactMaterialBlock.text")
        _require_non_negative_int(
            self.size_units, field_name="CompactMaterialBlock.size_units"
        )
        _require_string_tuple(
            self.source_labels, field_name="CompactMaterialBlock.source_labels"
        )
        _require_string_tuple(
            self.canonical_source_refs,
            field_name="CompactMaterialBlock.canonical_source_refs",
        )
        _require_non_empty(
            self.content_digest, field_name="CompactMaterialBlock.content_digest"
        )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "block_label": self.block_label,
            "section": self.section.value,
            "kind": self.kind.value,
            "text": self.text,
            "size_units": self.size_units,
            "source_labels": _string_list_json(self.source_labels),
            "canonical_source_refs": _string_list_json(self.canonical_source_refs),
            "content_digest": self.content_digest,
        }

    def llm_json(self) -> JsonValue:
        """转换为 LLM-facing JSON。

        :returns: 不含 canonical provenance key 的 JSON object。
        """

        return {
            "label": self.block_label,
            "kind": self.kind.value,
            "text": self.text,
            "source_labels": _string_list_json(self.source_labels),
        }


@dataclass(frozen=True, slots=True)
class CompactEvidenceBlock:
    """Compact material pack 的 evidence material block。

    :param evidence_label: prompt-local evidence label。
    :param readable_tool_name: LLM 可读工具名。
    :param readable_query_text: LLM 可读查询文本。
    :param raw_result_text: digest-checked raw result 文本。
    :param readable_source_text: LLM 可读来源文本。
    :param size_units: 文本 size units。
    :param canonical_source_refs: canonical source refs。
    :param content_digest: 文本 digest。
    """

    evidence_label: PromptLocalMaterialLabel
    readable_tool_name: str
    readable_query_text: str
    raw_result_text: str
    readable_source_text: str
    size_units: int
    canonical_source_refs: tuple[str, ...]
    content_digest: str

    def __post_init__(self) -> None:
        """校验 evidence material block。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_non_empty(
            self.evidence_label, field_name="CompactEvidenceBlock.evidence_label"
        )
        _require_non_empty(
            self.readable_tool_name,
            field_name="CompactEvidenceBlock.readable_tool_name",
        )
        _require_non_empty(
            self.readable_query_text,
            field_name="CompactEvidenceBlock.readable_query_text",
        )
        _require_non_empty(
            self.raw_result_text, field_name="CompactEvidenceBlock.raw_result_text"
        )
        _require_non_empty(
            self.readable_source_text,
            field_name="CompactEvidenceBlock.readable_source_text",
        )
        _require_non_negative_int(
            self.size_units, field_name="CompactEvidenceBlock.size_units"
        )
        _require_string_tuple(
            self.canonical_source_refs,
            field_name="CompactEvidenceBlock.canonical_source_refs",
        )
        _require_non_empty(
            self.content_digest, field_name="CompactEvidenceBlock.content_digest"
        )

    @property
    def block_label(self) -> PromptLocalMaterialLabel:
        """返回 evidence block label。

        :returns: prompt-local evidence label。
        """

        return self.evidence_label

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "evidence_label": self.evidence_label,
            "readable_tool_name": self.readable_tool_name,
            "readable_query_text": self.readable_query_text,
            "raw_result_text": self.raw_result_text,
            "readable_source_text": self.readable_source_text,
            "size_units": self.size_units,
            "canonical_source_refs": _string_list_json(self.canonical_source_refs),
            "content_digest": self.content_digest,
        }

    def llm_json(self) -> JsonValue:
        """转换为 LLM-facing JSON。

        :returns: 不含 canonical provenance key 的 JSON object。
        """

        return {
            "label": self.evidence_label,
            "kind": CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE.value,
            "tool_name": self.readable_tool_name,
            "query_text": self.readable_query_text,
            "result_text": self.raw_result_text,
            "source_text": self.readable_source_text,
        }


@dataclass(frozen=True, slots=True)
class CurrentInputAnchor:
    """当前用户输入的 prompt-local anchor。

    :param anchor_label: prompt-local current anchor label。
    :param anchor_text: 有界当前输入文本。
    :param truncated: anchor_text 是否截断。
    :param canonical_source_refs: canonical source refs。
    :param content_digest: 完整 current input digest。
    """

    anchor_label: PromptLocalMaterialLabel
    anchor_text: str
    truncated: bool
    canonical_source_refs: tuple[str, ...]
    content_digest: str

    def __post_init__(self) -> None:
        """校验 current input anchor。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_non_empty(
            self.anchor_label, field_name="CurrentInputAnchor.anchor_label"
        )
        _require_non_empty(
            self.anchor_text, field_name="CurrentInputAnchor.anchor_text"
        )
        _require_bool(self.truncated, field_name="CurrentInputAnchor.truncated")
        _require_string_tuple(
            self.canonical_source_refs,
            field_name="CurrentInputAnchor.canonical_source_refs",
        )
        _require_non_empty(
            self.content_digest, field_name="CurrentInputAnchor.content_digest"
        )

    @property
    def block_label(self) -> PromptLocalMaterialLabel:
        """返回 current anchor label。

        :returns: prompt-local current anchor label。
        """

        return self.anchor_label

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "anchor_label": self.anchor_label,
            "anchor_text": self.anchor_text,
            "truncated": self.truncated,
            "canonical_source_refs": _string_list_json(self.canonical_source_refs),
            "content_digest": self.content_digest,
        }

    def llm_json(self) -> JsonValue:
        """转换为 LLM-facing JSON。

        :returns: 不含 canonical provenance key 的 JSON object。
        """

        return {
            "label": self.anchor_label,
            "kind": CompactMaterialBlockKind.CURRENT_INPUT_ANCHOR.value,
            "text": self.anchor_text,
            "truncated": self.truncated,
        }


@dataclass(frozen=True, slots=True)
class CompactSegmentSelection:
    """Compaction selected segment 摘要。

    :param selected_block_ids: 已选择 block ids。
    :param excluded_protected_ids: 被保护排除的 block ids。
    :param trigger_source: segment selection 触发来源。
    :param input_cursor: 输入 cursor。
    :param memory_snapshot_cursor: memory snapshot cursor。
    :param policy_digest: policy digest。
    :param deterministic_reason_codes: deterministic reason codes。
    :param excluded_reason_codes: 被排除 block id 到 reason code 的映射。
    :param selection_digest: selection canonical digest。
    """

    selected_block_ids: tuple[str, ...]
    excluded_protected_ids: tuple[str, ...]
    trigger_source: CompactSegmentTrigger
    input_cursor: int
    memory_snapshot_cursor: int | None
    policy_digest: str
    deterministic_reason_codes: tuple[str, ...]
    selection_digest: str
    excluded_reason_codes: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """校验 segment selection。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_string_tuple(
            self.selected_block_ids,
            field_name="CompactSegmentSelection.selected_block_ids",
        )
        _require_string_tuple(
            self.excluded_protected_ids,
            field_name="CompactSegmentSelection.excluded_protected_ids",
        )
        if not isinstance(self.trigger_source, CompactSegmentTrigger):
            raise TypeError("CompactSegmentSelection.trigger_source is invalid")
        _require_non_negative_int(
            self.input_cursor, field_name="CompactSegmentSelection.input_cursor"
        )
        if self.memory_snapshot_cursor is not None:
            _require_non_negative_int(
                self.memory_snapshot_cursor,
                field_name="CompactSegmentSelection.memory_snapshot_cursor",
            )
        _require_non_empty(
            self.policy_digest, field_name="CompactSegmentSelection.policy_digest"
        )
        _require_string_tuple(
            self.deterministic_reason_codes,
            field_name="CompactSegmentSelection.deterministic_reason_codes",
        )
        _require_string_mapping(
            self.excluded_reason_codes,
            field_name="CompactSegmentSelection.excluded_reason_codes",
        )
        _require_non_empty(
            self.selection_digest,
            field_name="CompactSegmentSelection.selection_digest",
        )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "selected_block_ids": _string_list_json(self.selected_block_ids),
            "excluded_protected_ids": _string_list_json(self.excluded_protected_ids),
            "trigger_source": self.trigger_source.value,
            "input_cursor": self.input_cursor,
            "memory_snapshot_cursor": self.memory_snapshot_cursor,
            "policy_digest": self.policy_digest,
            "deterministic_reason_codes": _string_list_json(
                self.deterministic_reason_codes
            ),
            "excluded_reason_codes": _string_mapping_json(
                self.excluded_reason_codes
            ),
            "selection_digest": self.selection_digest,
        }


@dataclass(frozen=True, slots=True)
class CompactMaterialPack:
    """Compactor LLM-facing material pack 与内部 provenance map。

    :param stable_input: stable input blocks。
    :param history_input: history input blocks。
    :param evidence_input: evidence input blocks。
    :param current_input_anchor: 当前输入 anchor。
    :param provenance_map: prompt-local label 到 canonical provenance 的完整映射。
    """

    stable_input: tuple[CompactMaterialBlock, ...]
    history_input: tuple[CompactMaterialBlock, ...]
    evidence_input: tuple[CompactEvidenceBlock, ...]
    current_input_anchor: CurrentInputAnchor
    provenance_map: Mapping[PromptLocalMaterialLabel, PromptLocalProvenanceEntry]

    def __post_init__(self) -> None:
        """校验 material pack 与 one-section guard。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_material_block_tuple(
            self.stable_input,
            field_name="CompactMaterialPack.stable_input",
            section=CompactMaterialSection.STABLE_INPUT,
        )
        _require_material_block_tuple(
            self.history_input,
            field_name="CompactMaterialPack.history_input",
            section=CompactMaterialSection.HISTORY_INPUT,
        )
        _require_evidence_block_tuple(
            self.evidence_input,
            field_name="CompactMaterialPack.evidence_input",
        )
        if not isinstance(self.current_input_anchor, CurrentInputAnchor):
            raise TypeError(
                "CompactMaterialPack.current_input_anchor must be CurrentInputAnchor"
            )
        _require_provenance_mapping(self.provenance_map)
        _require_one_section_per_canonical_content(self)

    @property
    def all_labels(self) -> tuple[PromptLocalMaterialLabel, ...]:
        """返回 material pack 中所有 prompt-local labels。

        :returns: label tuple。
        """

        labels: list[PromptLocalMaterialLabel] = []
        labels.extend(block.block_label for block in self.stable_input)
        labels.extend(block.block_label for block in self.history_input)
        labels.extend(block.block_label for block in self.evidence_input)
        labels.append(self.current_input_anchor.anchor_label)
        return tuple(labels)

    @property
    def evidence_labels(self) -> tuple[PromptLocalMaterialLabel, ...]:
        """返回 evidence material labels。

        :returns: evidence label tuple。
        """

        return tuple(block.evidence_label for block in self.evidence_input)

    @property
    def material_source_refs(self) -> tuple[str, ...]:
        """返回 material pack 覆盖的 canonical source refs。

        :returns: 去重后的 canonical source refs。
        """

        refs: list[str] = []
        ordered_labels = (
            self.current_input_anchor.anchor_label,
            *[block.block_label for block in self.history_input],
            *[block.block_label for block in self.stable_input],
            *[block.block_label for block in self.evidence_input],
        )
        for label in ordered_labels:
            entry = self.provenance_map[label]
            refs.extend(entry.canonical_source_refs)
        return tuple(dict.fromkeys(refs))

    @property
    def canonical_evidence_refs(self) -> tuple[str, ...]:
        """返回 evidence labels 映射到的 canonical canonical evidence ids。

        :returns: canonical evidence id tuple。
        """

        refs: list[str] = []
        for label in self.evidence_labels:
            evidence_id = self.provenance_map[label].accepted_evidence_id
            if evidence_id is not None:
                refs.append(evidence_id)
        return tuple(dict.fromkeys(refs))

    def evidence_map(self) -> PromptLocalEvidenceMap:
        """返回 evidence-only prompt-local provenance view。

        :returns: evidence label 到 provenance entry 的只读 mapping。
        """

        return {
            label: self.provenance_map[label]
            for label in self.evidence_labels
        }

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "stable_input": _material_block_list_json(self.stable_input),
            "history_input": _material_block_list_json(self.history_input),
            "evidence_input": _evidence_block_list_json(self.evidence_input),
            "current_input_anchor": self.current_input_anchor.to_json(),
            "provenance_map": _provenance_map_json(self.provenance_map),
        }

    def llm_json(self) -> JsonValue:
        """转换为 LLM-facing material JSON。

        :returns: 不含 Host provenance key 的 JSON object。
        """

        return {
            "stable_input": _material_block_llm_list_json(self.stable_input),
            "history_input": _material_block_llm_list_json(self.history_input),
            "evidence_input": _evidence_block_llm_list_json(self.evidence_input),
            "current_input_anchor": self.current_input_anchor.llm_json(),
        }


@dataclass(frozen=True, slots=True)
class CompactionRequest:
    """Context compaction 请求。

    :param trigger_source: compact 触发来源。
    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: reactive compact 对应 Attempt id；proactive 时为 ``None``。
    :param execution_id: reactive compact 对应 execution id；proactive 时为 ``None``。
    :param memory_snapshot_cursor: memory snapshot cursor；无 snapshot 时为 ``None``。
    :param material_pack: LLM-facing material pack 与内部 provenance map。
    :param segment_selection: compact segment selection 摘要。
    :param evidence_backed_fact_refs: 已存在 evidence-backed fact refs。
    :param recent_raw_turn_refs: 必须保留的近期 raw turn refs。
    :param older_raw_turn_refs: 可摘要的较旧 raw turn refs。
    :param existing_episode_summary_refs: 已存在 episode summary refs。
    :param budget_before_compact: compact 前预算估算。
    """

    trigger_source: ContextCompactionTriggerSource
    session_id: str
    run_id: str
    attempt_id: str | None
    execution_id: str | None
    memory_snapshot_cursor: int | None
    material_pack: CompactMaterialPack
    segment_selection: CompactSegmentSelection
    evidence_backed_fact_refs: tuple[str, ...]
    recent_raw_turn_refs: tuple[str, ...]
    older_raw_turn_refs: tuple[str, ...]
    existing_episode_summary_refs: tuple[str, ...]
    budget_before_compact: BudgetEstimate

    def __post_init__(self) -> None:
        """校验 compaction 请求。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        if not isinstance(self.trigger_source, ContextCompactionTriggerSource):
            raise TypeError("CompactionRequest.trigger_source is invalid")
        _require_non_empty(self.session_id, field_name="CompactionRequest.session_id")
        _require_non_empty(self.run_id, field_name="CompactionRequest.run_id")
        _require_optional_non_empty(
            self.attempt_id, field_name="CompactionRequest.attempt_id"
        )
        _require_optional_non_empty(
            self.execution_id, field_name="CompactionRequest.execution_id"
        )
        if self.trigger_source is ContextCompactionTriggerSource.REACTIVE:
            if self.attempt_id is None:
                raise ValueError(
                    "CompactionRequest.attempt_id is required for reactive compaction"
                )
            if self.execution_id is None:
                raise ValueError(
                    "CompactionRequest.execution_id is required for reactive compaction"
                )
        if self.memory_snapshot_cursor is not None:
            _require_non_negative_int(
                self.memory_snapshot_cursor,
                field_name="CompactionRequest.memory_snapshot_cursor",
            )
        if not isinstance(self.material_pack, CompactMaterialPack):
            raise TypeError("CompactionRequest.material_pack must be CompactMaterialPack")
        if not isinstance(self.segment_selection, CompactSegmentSelection):
            raise TypeError(
                "CompactionRequest.segment_selection must be CompactSegmentSelection"
            )
        if self.current_input_ref not in self.material_source_refs:
            raise ValueError("CompactionRequest.material_pack must include current input")
        _require_unique_string_tuple(
            self.canonical_evidence_refs,
            field_name="CompactionRequest.canonical_evidence_refs",
        )
        _require_string_tuple(
            self.evidence_backed_fact_refs,
            field_name="CompactionRequest.evidence_backed_fact_refs",
        )
        _require_string_tuple(
            self.recent_raw_turn_refs,
            field_name="CompactionRequest.recent_raw_turn_refs",
        )
        _require_string_tuple(
            self.older_raw_turn_refs,
            field_name="CompactionRequest.older_raw_turn_refs",
        )
        _require_string_tuple(
            self.existing_episode_summary_refs,
            field_name="CompactionRequest.existing_episode_summary_refs",
        )
        if not isinstance(self.budget_before_compact, BudgetEstimate):
            raise TypeError(
                "CompactionRequest.budget_before_compact must be BudgetEstimate"
            )

    def digest(self) -> str:
        """计算 compaction request digest。

        :returns: 请求 canonical JSON 的 sha256 digest。
        """

        return sha256_digest_json(self.to_json())

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "trigger_source": self.trigger_source.value,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "attempt_id": self.attempt_id,
            "execution_id": self.execution_id,
            "memory_snapshot_cursor": self.memory_snapshot_cursor,
            "material_pack": self.material_pack.to_json(),
            "segment_selection": self.segment_selection.to_json(),
            "canonical_evidence_refs": _string_list_json(
                self.canonical_evidence_refs
            ),
            "evidence_backed_fact_refs": _string_list_json(
                self.evidence_backed_fact_refs
            ),
            "recent_raw_turn_refs": _string_list_json(self.recent_raw_turn_refs),
            "older_raw_turn_refs": _string_list_json(self.older_raw_turn_refs),
            "existing_episode_summary_refs": _string_list_json(
                self.existing_episode_summary_refs
            ),
            "budget_before_compact": _budget_estimate_json(
                self.budget_before_compact
            ),
        }

    def llm_material_json(self) -> JsonValue:
        """返回只可暴露给 LLM 的 material JSON。

        :returns: 不含 EventLog / payload / digest / cursor 的 material JSON。
        """

        return self.material_pack.llm_json()

    @property
    def canonical_evidence_refs(self) -> tuple[str, ...]:
        """返回请求 material pack 内 canonical evidence ids。

        :returns: canonical evidence id tuple。
        """

        return self.material_pack.canonical_evidence_refs

    @property
    def material_source_refs(self) -> tuple[str, ...]:
        """返回请求 material pack 覆盖的 canonical source refs。

        :returns: canonical source refs。
        """

        return self.material_pack.material_source_refs

    @property
    def current_input_ref(self) -> str:
        """返回当前输入的 canonical source ref。

        :returns: current input canonical source ref。
        :raises ValueError: current input anchor 缺少 canonical source ref 时抛出。
        """

        refs = self.material_pack.current_input_anchor.canonical_source_refs
        if len(refs) == 0:
            raise ValueError("current input anchor must include canonical source ref")
        return refs[0]

    @property
    def current_input_text(self) -> str:
        """返回当前输入 anchor 文本。

        :returns: 当前输入有界文本。
        """

        return self.material_pack.current_input_anchor.anchor_text


@dataclass(frozen=True, slots=True)
class EpisodeSummaryCandidate:
    """Episode summary 候选。

    :param candidate_id: summary candidate id。
    :param episode_title: episode 标题。
    :param goal: 用户目标摘要。
    :param completed_actions: 已完成动作摘要。
    :param confirmed_fact_refs: 输入中已有 confirmed / evidence-backed fact refs。
    :param confirmed_fact_summaries: confirmed facts 的可读摘要。
    :param user_constraints: 用户约束摘要。
    :param open_questions: 未决问题。
    :param next_step: 下一步摘要；无时为 ``None``。
    :param tool_finding_refs: 工具发现 refs。
    :param source_event_refs: summary 覆盖的输入 event refs。
    :param evidence_refs: preservation evidence refs。
    :param proposed_evidence_backed_fact_refs: compactor 试图新建的 stable fact refs；正常应为空。
    """

    candidate_id: str
    episode_title: str
    goal: str
    completed_actions: tuple[str, ...]
    confirmed_fact_refs: tuple[str, ...]
    confirmed_fact_summaries: tuple[str, ...]
    user_constraints: tuple[str, ...]
    open_questions: tuple[str, ...]
    next_step: str | None
    tool_finding_refs: tuple[str, ...]
    source_event_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    proposed_evidence_backed_fact_refs: tuple[str, ...] = field(
        default_factory=_empty_string_tuple
    )

    def __post_init__(self) -> None:
        """校验 episode summary 候选。

        :returns: ``None``。
        :raises TypeError: tuple 字段类型非法时抛出。
        :raises ValueError: 文本字段为空时抛出。
        """

        _require_non_empty(
            self.candidate_id, field_name="EpisodeSummaryCandidate.candidate_id"
        )
        _require_non_empty(
            self.episode_title,
            field_name="EpisodeSummaryCandidate.episode_title",
        )
        _require_non_empty(self.goal, field_name="EpisodeSummaryCandidate.goal")
        _require_string_tuple(
            self.completed_actions,
            field_name="EpisodeSummaryCandidate.completed_actions",
        )
        _require_string_tuple(
            self.confirmed_fact_refs,
            field_name="EpisodeSummaryCandidate.confirmed_fact_refs",
        )
        _require_string_tuple(
            self.confirmed_fact_summaries,
            field_name="EpisodeSummaryCandidate.confirmed_fact_summaries",
        )
        _require_string_tuple(
            self.user_constraints,
            field_name="EpisodeSummaryCandidate.user_constraints",
        )
        _require_string_tuple(
            self.open_questions,
            field_name="EpisodeSummaryCandidate.open_questions",
        )
        _require_optional_non_empty(
            self.next_step, field_name="EpisodeSummaryCandidate.next_step"
        )
        _require_string_tuple(
            self.tool_finding_refs,
            field_name="EpisodeSummaryCandidate.tool_finding_refs",
        )
        _require_string_tuple(
            self.source_event_refs,
            field_name="EpisodeSummaryCandidate.source_event_refs",
        )
        _require_string_tuple(
            self.evidence_refs,
            field_name="EpisodeSummaryCandidate.evidence_refs",
        )
        _require_string_tuple(
            self.proposed_evidence_backed_fact_refs,
            field_name=(
                "EpisodeSummaryCandidate.proposed_evidence_backed_fact_refs"
            ),
        )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "candidate_id": self.candidate_id,
            "episode_title": self.episode_title,
            "goal": self.goal,
            "completed_actions": _string_list_json(self.completed_actions),
            "confirmed_fact_refs": _string_list_json(self.confirmed_fact_refs),
            "confirmed_fact_summaries": _string_list_json(
                self.confirmed_fact_summaries
            ),
            "user_constraints": _string_list_json(self.user_constraints),
            "open_questions": _string_list_json(self.open_questions),
            "next_step": self.next_step,
            "tool_finding_refs": _string_list_json(self.tool_finding_refs),
            "source_event_refs": _string_list_json(self.source_event_refs),
            "evidence_refs": _string_list_json(self.evidence_refs),
            "proposed_evidence_backed_fact_refs": _string_list_json(
                self.proposed_evidence_backed_fact_refs
            ),
        }


@dataclass(frozen=True, slots=True)
class PinnedTextFieldPatch:
    """Pinned state 文本字段三态 patch。

    :param operation: missing / clear / replace 操作。
    :param value: replace 时的新值；其它操作为 ``None``。
    :param evidence_refs: clear / replace 操作引用的 preservation evidence refs。
    """

    operation: PinnedPatchOperation
    value: str | None = None
    evidence_refs: tuple[str, ...] = field(default_factory=_empty_string_tuple)

    def __post_init__(self) -> None:
        """校验文本 patch 基础类型。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: evidence ref 为空时抛出。
        """

        if not isinstance(self.operation, PinnedPatchOperation):
            raise TypeError("PinnedTextFieldPatch.operation is invalid")
        if self.value is not None:
            _require_non_empty(self.value, field_name="PinnedTextFieldPatch.value")
        _require_string_tuple(
            self.evidence_refs, field_name="PinnedTextFieldPatch.evidence_refs"
        )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "operation": self.operation.value,
            "value": self.value,
            "evidence_refs": _string_list_json(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class PinnedStringTupleFieldPatch:
    """Pinned state 字符串 tuple 字段三态 patch。

    :param operation: missing / clear / replace 操作。
    :param value: replace 时的新 tuple；其它操作为 ``None``。
    :param evidence_refs: clear / replace 操作引用的 preservation evidence refs。
    """

    operation: PinnedPatchOperation
    value: tuple[str, ...] | None = None
    evidence_refs: tuple[str, ...] = field(default_factory=_empty_string_tuple)

    def __post_init__(self) -> None:
        """校验 tuple patch 基础类型。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: evidence ref 为空时抛出。
        """

        if not isinstance(self.operation, PinnedPatchOperation):
            raise TypeError("PinnedStringTupleFieldPatch.operation is invalid")
        if self.value is not None:
            _require_string_tuple(
                self.value, field_name="PinnedStringTupleFieldPatch.value"
            )
        _require_string_tuple(
            self.evidence_refs,
            field_name="PinnedStringTupleFieldPatch.evidence_refs",
        )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "operation": self.operation.value,
            "value": (
                None if self.value is None else _string_list_json(self.value)
            ),
            "evidence_refs": _string_list_json(self.evidence_refs),
        }


def missing_text_patch() -> PinnedTextFieldPatch:
    """构造文本字段 missing patch。

    :returns: missing patch。
    """

    return PinnedTextFieldPatch(operation=PinnedPatchOperation.MISSING)


def missing_string_tuple_patch() -> PinnedStringTupleFieldPatch:
    """构造字符串 tuple 字段 missing patch。

    :returns: missing patch。
    """

    return PinnedStringTupleFieldPatch(operation=PinnedPatchOperation.MISSING)


@dataclass(frozen=True, slots=True)
class PinnedStatePatchCandidate:
    """Pinned state 字段级三态 patch 候选。

    :param candidate_id: patch candidate id。
    :param current_goal: current goal patch。
    :param confirmed_subjects: confirmed subjects patch。
    :param user_constraints: user constraints patch。
    :param open_questions: open questions patch。
    """

    candidate_id: str
    current_goal: PinnedTextFieldPatch = field(default_factory=missing_text_patch)
    confirmed_subjects: PinnedStringTupleFieldPatch = field(
        default_factory=missing_string_tuple_patch
    )
    user_constraints: PinnedStringTupleFieldPatch = field(
        default_factory=missing_string_tuple_patch
    )
    open_questions: PinnedStringTupleFieldPatch = field(
        default_factory=missing_string_tuple_patch
    )

    def __post_init__(self) -> None:
        """校验 pinned state patch 候选基础类型。

        :returns: ``None``。
        :raises TypeError: patch 字段类型非法时抛出。
        :raises ValueError: candidate id 为空时抛出。
        """

        _require_non_empty(
            self.candidate_id, field_name="PinnedStatePatchCandidate.candidate_id"
        )
        if not isinstance(self.current_goal, PinnedTextFieldPatch):
            raise TypeError(
                "PinnedStatePatchCandidate.current_goal must be PinnedTextFieldPatch"
            )
        _require_tuple_patch_field(
            self.confirmed_subjects,
            field_name="PinnedStatePatchCandidate.confirmed_subjects",
        )
        _require_tuple_patch_field(
            self.user_constraints,
            field_name="PinnedStatePatchCandidate.user_constraints",
        )
        _require_tuple_patch_field(
            self.open_questions,
            field_name="PinnedStatePatchCandidate.open_questions",
        )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "candidate_id": self.candidate_id,
            "current_goal": self.current_goal.to_json(),
            "confirmed_subjects": self.confirmed_subjects.to_json(),
            "user_constraints": self.user_constraints.to_json(),
            "open_questions": self.open_questions.to_json(),
        }


@dataclass(frozen=True, slots=True)
class PreservationEvidence:
    """Compact preservation evidence。

    :param evidence_id: evidence id。
    :param material_source_refs: evidence 覆盖的 material source refs。
    :param canonical_evidence_refs: evidence 覆盖的 canonical evidence refs。
    :param memory_snapshot_cursor: evidence 对应 memory cursor；无时为 ``None``。
    :param compact_input_range: evidence 对应 compact 输入范围；无时为 ``None``。
    """

    evidence_id: str
    material_source_refs: tuple[str, ...]
    canonical_evidence_refs: tuple[str, ...]
    memory_snapshot_cursor: int | None
    compact_input_range: CompactInputRange | None

    def __post_init__(self) -> None:
        """校验 preservation evidence。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_non_empty(
            self.evidence_id, field_name="PreservationEvidence.evidence_id"
        )
        _require_string_tuple(
            self.material_source_refs,
            field_name="PreservationEvidence.material_source_refs",
        )
        _require_string_tuple(
            self.canonical_evidence_refs,
            field_name="PreservationEvidence.canonical_evidence_refs",
        )
        if self.memory_snapshot_cursor is not None:
            _require_non_negative_int(
                self.memory_snapshot_cursor,
                field_name="PreservationEvidence.memory_snapshot_cursor",
            )
        if self.compact_input_range is not None and not isinstance(
            self.compact_input_range, CompactInputRange
        ):
            raise TypeError(
                "PreservationEvidence.compact_input_range must be CompactInputRange"
            )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "evidence_id": self.evidence_id,
            "material_source_refs": _string_list_json(self.material_source_refs),
            "canonical_evidence_refs": _string_list_json(
                self.canonical_evidence_refs
            ),
            "memory_snapshot_cursor": self.memory_snapshot_cursor,
            "compact_input_range": (
                None
                if self.compact_input_range is None
                else self.compact_input_range.to_json()
            ),
        }


@dataclass(frozen=True, slots=True)
class EvidenceBackedFactCandidate:
    """Compactor 输出的 evidence-backed fact 候选。

    :param candidate_id: candidate-local id，只用于诊断与去重。
    :param claim_text: 可进入 memory 的事实声明文本。
    :param evidence_kind: 事实声明类型。
    :param evidence_refs: 支撑该声明的 canonical evidence ids。
    :param attributes: Host 不解释的 JSON attributes。
    """

    candidate_id: str
    claim_text: str
    evidence_kind: EvidenceBackedFactKind
    evidence_refs: tuple[str, ...]
    attributes: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        """校验 evidence-backed fact candidate 基础边界。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_non_empty(
            self.candidate_id,
            field_name="EvidenceBackedFactCandidate.candidate_id",
        )
        _require_bounded_non_empty_text(
            self.claim_text,
            field_name="EvidenceBackedFactCandidate.claim_text",
            max_chars=MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS,
        )
        if not isinstance(self.evidence_kind, EvidenceBackedFactKind):
            raise TypeError(
                "EvidenceBackedFactCandidate.evidence_kind must be "
                "EvidenceBackedFactKind"
            )
        _require_bounded_string_tuple(
            self.evidence_refs,
            field_name="EvidenceBackedFactCandidate.evidence_refs",
            max_items=MAX_EVIDENCE_REFS_PER_FACT,
            require_non_empty=True,
        )
        _require_json_mapping(
            self.attributes,
            field_name="EvidenceBackedFactCandidate.attributes",
        )
        attributes_json = canonical_json_dumps(self.attributes)
        if len(attributes_json) > MAX_EVIDENCE_BACKED_FACT_ATTRIBUTES_JSON_CHARS:
            raise ValueError(
                "EvidenceBackedFactCandidate.attributes exceeds maximum size"
            )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "candidate_id": self.candidate_id,
            "claim_text": self.claim_text,
            "evidence_kind": self.evidence_kind.value,
            "evidence_refs": _string_list_json(self.evidence_refs),
            "attributes": self.attributes,
        }


@dataclass(frozen=True, slots=True)
class MinimumPreserveItemCandidate:
    """Compactor 输出的最小连续性保留候选。

    :param item_id: item-local id，只用于诊断与去重。
    :param label: 短标签。
    :param text: 需要保留的连续性文本。
    :param source_refs: compact 输入范围内的来源 event refs。
    :param preserve_reason: 保留原因。
    """

    item_id: str
    label: str
    text: str
    source_refs: tuple[str, ...]
    preserve_reason: MinimumPreserveReason

    def __post_init__(self) -> None:
        """校验 minimum preserve item candidate 基础边界。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_non_empty(
            self.item_id, field_name="MinimumPreserveItemCandidate.item_id"
        )
        _require_bounded_non_empty_text(
            self.label,
            field_name="MinimumPreserveItemCandidate.label",
            max_chars=MAX_MINIMUM_PRESERVE_ITEM_LABEL_CHARS,
        )
        _require_bounded_non_empty_text(
            self.text,
            field_name="MinimumPreserveItemCandidate.text",
            max_chars=MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS,
        )
        _require_bounded_string_tuple(
            self.source_refs,
            field_name="MinimumPreserveItemCandidate.source_refs",
            max_items=MAX_SOURCE_REFS_PER_MINIMUM_PRESERVE_ITEM,
            require_non_empty=True,
        )
        if not isinstance(self.preserve_reason, MinimumPreserveReason):
            raise TypeError(
                "MinimumPreserveItemCandidate.preserve_reason must be "
                "MinimumPreserveReason"
            )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "item_id": self.item_id,
            "label": self.label,
            "text": self.text,
            "source_refs": _string_list_json(self.source_refs),
            "preserve_reason": self.preserve_reason.value,
        }


@dataclass(frozen=True, slots=True)
class CompactionCandidate:
    """Compactor 输出候选。

    :param candidate_id: compact candidate id。
    :param episode_summary_candidate: episode summary 候选。
    :param pinned_state_patch_candidate: pinned state patch 候选。
    :param preservation_evidence: preservation evidence 集合。
    :param evidence_backed_fact_candidates: evidence-backed fact 候选集合。
    :param minimum_preserve_item_candidates: minimum preserve item 候选集合。
    :param retained_current_user_input_ref: 被保留的当前用户输入 ref。
    :param preserved_material_source_refs: 被保留的 material source refs。
    :param preserved_canonical_evidence_refs: 被保留的 canonical evidence refs。
    :param preserved_evidence_backed_fact_refs: 被保留的 evidence-backed fact refs。
    :param dropped_ranges: 被丢弃的输入范围。
    :param summarized_ranges: 被摘要的输入范围。
    :param budget_after_compact: compact 后预算 token 估算。
    """

    candidate_id: str
    episode_summary_candidate: EpisodeSummaryCandidate
    pinned_state_patch_candidate: PinnedStatePatchCandidate
    preservation_evidence: tuple[PreservationEvidence, ...]
    evidence_backed_fact_candidates: tuple[EvidenceBackedFactCandidate, ...]
    minimum_preserve_item_candidates: tuple[MinimumPreserveItemCandidate, ...]
    retained_current_user_input_ref: str | None
    preserved_material_source_refs: tuple[str, ...]
    preserved_canonical_evidence_refs: tuple[str, ...]
    preserved_evidence_backed_fact_refs: tuple[str, ...]
    dropped_ranges: tuple[CompactInputRange, ...]
    summarized_ranges: tuple[CompactInputRange, ...]
    budget_after_compact: int

    def __post_init__(self) -> None:
        """校验 compaction candidate 基础类型。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_non_empty(
            self.candidate_id, field_name="CompactionCandidate.candidate_id"
        )
        if not isinstance(self.episode_summary_candidate, EpisodeSummaryCandidate):
            raise TypeError(
                "CompactionCandidate.episode_summary_candidate must be "
                "EpisodeSummaryCandidate"
            )
        if not isinstance(self.pinned_state_patch_candidate, PinnedStatePatchCandidate):
            raise TypeError(
                "CompactionCandidate.pinned_state_patch_candidate must be "
                "PinnedStatePatchCandidate"
            )
        _require_evidence_tuple(
            self.preservation_evidence,
            field_name="CompactionCandidate.preservation_evidence",
        )
        _require_fact_candidate_tuple(
            self.evidence_backed_fact_candidates,
            field_name="CompactionCandidate.evidence_backed_fact_candidates",
        )
        _require_minimum_preserve_candidate_tuple(
            self.minimum_preserve_item_candidates,
            field_name="CompactionCandidate.minimum_preserve_item_candidates",
        )
        _require_optional_non_empty(
            self.retained_current_user_input_ref,
            field_name="CompactionCandidate.retained_current_user_input_ref",
        )
        _require_string_tuple(
            self.preserved_material_source_refs,
            field_name="CompactionCandidate.preserved_material_source_refs",
        )
        _require_string_tuple(
            self.preserved_canonical_evidence_refs,
            field_name="CompactionCandidate.preserved_canonical_evidence_refs",
        )
        _require_string_tuple(
            self.preserved_evidence_backed_fact_refs,
            field_name="CompactionCandidate.preserved_evidence_backed_fact_refs",
        )
        _require_range_tuple(
            self.dropped_ranges, field_name="CompactionCandidate.dropped_ranges"
        )
        _require_range_tuple(
            self.summarized_ranges, field_name="CompactionCandidate.summarized_ranges"
        )
        _require_non_negative_int(
            self.budget_after_compact,
            field_name="CompactionCandidate.budget_after_compact",
        )

    def digest(self) -> str:
        """计算 candidate digest。

        :returns: candidate canonical JSON 的 sha256 digest。
        """

        return sha256_digest_json(self.to_json())

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "candidate_id": self.candidate_id,
            "episode_summary_candidate": self.episode_summary_candidate.to_json(),
            "pinned_state_patch_candidate": (
                self.pinned_state_patch_candidate.to_json()
            ),
            "preservation_evidence": _evidence_list_json(
                self.preservation_evidence
            ),
            "evidence_backed_fact_candidates": _fact_candidate_list_json(
                self.evidence_backed_fact_candidates
            ),
            "minimum_preserve_item_candidates": (
                _minimum_preserve_candidate_list_json(
                    self.minimum_preserve_item_candidates
                )
            ),
            "retained_current_user_input_ref": self.retained_current_user_input_ref,
            "preserved_material_source_refs": _string_list_json(
                self.preserved_material_source_refs
            ),
            "preserved_canonical_evidence_refs": _string_list_json(
                self.preserved_canonical_evidence_refs
            ),
            "preserved_evidence_backed_fact_refs": _string_list_json(
                self.preserved_evidence_backed_fact_refs
            ),
            "dropped_ranges": _range_list_json(self.dropped_ranges),
            "summarized_ranges": _range_list_json(self.summarized_ranges),
            "budget_after_compact": self.budget_after_compact,
        }


@dataclass(frozen=True, slots=True)
class CompactQualityCheckResult:
    """Compact quality check 结果。

    :param accepted: 候选是否通过 quality check。
    :param rejection_reasons: 拒绝原因集合。
    :param current_user_input_retained: 当前用户输入是否保留。
    :param canonical_evidence_refs_retained: canonical evidence refs 是否全部保留。
    :param evidence_backed_fact_candidates_accepted: fact candidates 是否通过。
    :param minimum_preserve_items_accepted: minimum preserve candidates 是否通过。
    :param evidence_anchors_retained: evidence anchors 是否保留。
    :param open_questions_retained: open questions / assumptions 是否保留。
    :param retained_canonical_evidence_refs: 被接受的 canonical evidence refs。
    :param dropped_ranges: 被丢弃的输入范围。
    :param summarized_ranges: 被摘要的输入范围。
    """

    accepted: bool
    rejection_reasons: tuple[CompactQualityIssue, ...]
    current_user_input_retained: bool
    canonical_evidence_refs_retained: bool
    evidence_backed_fact_candidates_accepted: bool
    minimum_preserve_items_accepted: bool
    evidence_anchors_retained: bool
    open_questions_retained: bool
    retained_canonical_evidence_refs: tuple[str, ...]
    dropped_ranges: tuple[CompactInputRange, ...]
    summarized_ranges: tuple[CompactInputRange, ...]

    def __post_init__(self) -> None:
        """校验 quality check 结果字段。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        if not isinstance(self.accepted, bool):
            raise TypeError("CompactQualityCheckResult.accepted must be bool")
        _require_quality_issue_tuple(
            self.rejection_reasons,
            field_name="CompactQualityCheckResult.rejection_reasons",
        )
        _require_bool(
            self.current_user_input_retained,
            field_name="CompactQualityCheckResult.current_user_input_retained",
        )
        _require_bool(
            self.canonical_evidence_refs_retained,
            field_name="CompactQualityCheckResult.canonical_evidence_refs_retained",
        )
        _require_bool(
            self.evidence_backed_fact_candidates_accepted,
            field_name=(
                "CompactQualityCheckResult."
                "evidence_backed_fact_candidates_accepted"
            ),
        )
        _require_bool(
            self.minimum_preserve_items_accepted,
            field_name="CompactQualityCheckResult.minimum_preserve_items_accepted",
        )
        _require_bool(
            self.evidence_anchors_retained,
            field_name="CompactQualityCheckResult.evidence_anchors_retained",
        )
        _require_bool(
            self.open_questions_retained,
            field_name="CompactQualityCheckResult.open_questions_retained",
        )
        _require_string_tuple(
            self.retained_canonical_evidence_refs,
            field_name="CompactQualityCheckResult.retained_canonical_evidence_refs",
        )
        _require_range_tuple(
            self.dropped_ranges,
            field_name="CompactQualityCheckResult.dropped_ranges",
        )
        _require_range_tuple(
            self.summarized_ranges,
            field_name="CompactQualityCheckResult.summarized_ranges",
        )
        if self.accepted and len(self.rejection_reasons) > 0:
            raise ValueError(
                "Accepted quality result must not include rejection reasons"
            )
        if not self.accepted and len(self.rejection_reasons) == 0:
            raise ValueError("Rejected quality result must include rejection reasons")

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "accepted": self.accepted,
            "rejection_reasons": [
                _enum_value for _enum_value in self._rejection_reason_values()
            ],
            "current_user_input_retained": self.current_user_input_retained,
            "canonical_evidence_refs_retained": (
                self.canonical_evidence_refs_retained
            ),
            "evidence_backed_fact_candidates_accepted": (
                self.evidence_backed_fact_candidates_accepted
            ),
            "minimum_preserve_items_accepted": (
                self.minimum_preserve_items_accepted
            ),
            "evidence_anchors_retained": self.evidence_anchors_retained,
            "open_questions_retained": self.open_questions_retained,
            "retained_canonical_evidence_refs": _string_list_json(
                self.retained_canonical_evidence_refs
            ),
            "dropped_ranges": _range_list_json(self.dropped_ranges),
            "summarized_ranges": _range_list_json(self.summarized_ranges),
        }

    def _rejection_reason_values(self) -> list[JsonValue]:
        """返回拒绝原因字符串列表。

        :returns: JSON 字符串列表。
        """

        values: list[JsonValue] = []
        for reason in self.rejection_reasons:
            values.append(reason.value)
        return values


class ContextCompactor(Protocol):
    """Context compactor typed port。

    真实实现可以是 LLM scene adapter；Host 只能接受 typed candidate，并且
    必须由 quality checker 通过后才可写 compact artifact / canonical event。
    """

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> CompactionCandidate:
        """生成 compaction candidate。

        :param request: Host 构造的 compaction 请求。
        :param cancellation_token: Host 注入的真实取消 token。
        :returns: compaction candidate。
        :raises RuntimeError: compactor 后端失败时可抛出运行时错误。
        """

        ...


def _require_optional_non_empty(value: str | None, *, field_name: str) -> None:
    """校验可选非空字符串。

    :param value: 待校验值。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises ValueError: 字符串存在但为空时抛出。
    """

    if value is not None:
        _require_non_empty(value, field_name=field_name)


def _require_string_tuple(value: tuple[str, ...], *, field_name: str) -> None:
    """校验字符串 tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    :raises ValueError: 元素为空时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} items must be str")
        _require_non_empty(item, field_name=field_name)


def _require_string_mapping(
    value: Mapping[str, str], *, field_name: str
) -> None:
    """校验字符串到字符串的只读 mapping。

    :param value: 待校验 mapping。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段、key 或 value 类型非法时抛出。
    :raises ValueError: key 或 value 为空时抛出。
    """

    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be mapping")
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{field_name} keys must be str")
        if not isinstance(item, str):
            raise TypeError(f"{field_name} values must be str")
        _require_non_empty(key, field_name=field_name)
        _require_non_empty(item, field_name=field_name)


def _require_unique_string_tuple(
    value: tuple[str, ...], *, field_name: str
) -> None:
    """校验字符串 tuple 且元素不重复。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    :raises ValueError: 元素为空或重复时抛出。
    """

    _require_string_tuple(value, field_name=field_name)
    if len(set(value)) != len(value):
        raise ValueError(f"{field_name} items must be unique")


def _require_bounded_string_tuple(
    value: tuple[str, ...],
    *,
    field_name: str,
    max_items: int,
    require_non_empty: bool,
) -> None:
    """校验字符串 tuple 数量边界。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :param max_items: 最大元素数量。
    :param require_non_empty: 是否要求至少一个元素。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    :raises ValueError: 元素为空、数量非法或重复时抛出。
    """

    _require_unique_string_tuple(value, field_name=field_name)
    if require_non_empty and len(value) == 0:
        raise ValueError(f"{field_name} must be non-empty")
    if len(value) > max_items:
        raise ValueError(f"{field_name} exceeds maximum item count")


def _require_bounded_non_empty_text(
    value: str, *, field_name: str, max_chars: int
) -> None:
    """校验有界非空文本。

    :param value: 待校验文本。
    :param field_name: 错误字段名。
    :param max_chars: 最大字符数。
    :returns: ``None``。
    :raises TypeError: 文本类型非法时抛出。
    :raises ValueError: 文本为空或超长时抛出。
    """

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")
    if len(value) > max_chars:
        raise ValueError(f"{field_name} exceeds maximum length")


def _require_json_mapping(
    value: Mapping[str, JsonValue], *, field_name: str
) -> None:
    """校验 JSON object mapping。

    :param value: 待校验 JSON object。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: value 或 key 类型非法时抛出。
    """

    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be mapping")
    for key in value:
        if not isinstance(key, str):
            raise TypeError(f"{field_name} keys must be str")


def _require_material_block_tuple(
    value: tuple[CompactMaterialBlock, ...],
    *,
    field_name: str,
    section: CompactMaterialSection,
) -> None:
    """校验 material block tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :param section: 期望 section。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    :raises ValueError: 元素 section 非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, CompactMaterialBlock):
            raise TypeError(f"{field_name} items must be CompactMaterialBlock")
        if item.section is not section:
            raise ValueError(f"{field_name} items must belong to {section.value}")


def _require_evidence_block_tuple(
    value: tuple[CompactEvidenceBlock, ...], *, field_name: str
) -> None:
    """校验 evidence material block tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, CompactEvidenceBlock):
            raise TypeError(f"{field_name} items must be CompactEvidenceBlock")


def _require_provenance_mapping(
    value: Mapping[PromptLocalMaterialLabel, PromptLocalProvenanceEntry],
) -> None:
    """校验 prompt-local provenance mapping。

    :param value: 待校验 mapping。
    :returns: ``None``。
    :raises TypeError: mapping 或元素类型非法时抛出。
    """

    if not isinstance(value, Mapping):
        raise TypeError("CompactMaterialPack.provenance_map must be mapping")
    for key, entry in value.items():
        if not isinstance(key, str):
            raise TypeError("CompactMaterialPack.provenance_map keys must be str")
        if not isinstance(entry, PromptLocalProvenanceEntry):
            raise TypeError(
                "CompactMaterialPack.provenance_map values must be "
                "PromptLocalProvenanceEntry"
            )
        if key != entry.label:
            raise ValueError("CompactMaterialPack.provenance_map key mismatch")


def _require_one_section_per_canonical_content(pack: CompactMaterialPack) -> None:
    """校验同一 canonical content 不跨 section 重复出现。

    :param pack: material pack。
    :returns: ``None``。
    :raises ValueError: 同一 canonical source refs + digest 跨 section 重复时抛出。
    """

    seen: dict[tuple[tuple[str, ...], str], CompactMaterialSection] = {}
    for label in pack.all_labels:
        entry = pack.provenance_map[label]
        key = (tuple(sorted(entry.canonical_source_refs)), entry.content_digest)
        existing_section = seen.get(key)
        if existing_section is None:
            seen[key] = entry.section
            continue
        if existing_section is not entry.section:
            raise ValueError("material pack canonical content appears in two sections")


def _require_opaque_ref_tuple(
    value: tuple[OpaqueEvidenceRef, ...], *, field_name: str
) -> None:
    """校验 opaque evidence ref tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, OpaqueEvidenceRef):
            raise TypeError(f"{field_name} items must be OpaqueEvidenceRef")


def _require_tuple_patch_field(
    value: PinnedStringTupleFieldPatch, *, field_name: str
) -> None:
    """校验字符串 tuple patch 字段。

    :param value: 待校验 patch。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: patch 字段类型非法时抛出。
    """

    if not isinstance(value, PinnedStringTupleFieldPatch):
        raise TypeError(f"{field_name} must be PinnedStringTupleFieldPatch")


def _require_evidence_tuple(
    value: tuple[PreservationEvidence, ...], *, field_name: str
) -> None:
    """校验 preservation evidence tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, PreservationEvidence):
            raise TypeError(f"{field_name} items must be PreservationEvidence")


def _require_fact_candidate_tuple(
    value: tuple[EvidenceBackedFactCandidate, ...], *, field_name: str
) -> None:
    """校验 evidence-backed fact candidate tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    :raises ValueError: 数量超过上限时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    if len(value) > MAX_EVIDENCE_BACKED_FACT_CANDIDATES:
        raise ValueError(f"{field_name} exceeds maximum item count")
    for item in value:
        if not isinstance(item, EvidenceBackedFactCandidate):
            raise TypeError(
                f"{field_name} items must be EvidenceBackedFactCandidate"
            )


def _require_minimum_preserve_candidate_tuple(
    value: tuple[MinimumPreserveItemCandidate, ...], *, field_name: str
) -> None:
    """校验 minimum preserve item candidate tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    :raises ValueError: 数量超过上限时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    if len(value) > MAX_MINIMUM_PRESERVE_ITEM_CANDIDATES:
        raise ValueError(f"{field_name} exceeds maximum item count")
    for item in value:
        if not isinstance(item, MinimumPreserveItemCandidate):
            raise TypeError(
                f"{field_name} items must be MinimumPreserveItemCandidate"
            )


def _require_range_tuple(
    value: tuple[CompactInputRange, ...], *, field_name: str
) -> None:
    """校验 compact input range tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, CompactInputRange):
            raise TypeError(f"{field_name} items must be CompactInputRange")


def _require_quality_issue_tuple(
    value: tuple[CompactQualityIssue, ...], *, field_name: str
) -> None:
    """校验 quality issue tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, CompactQualityIssue):
            raise TypeError(f"{field_name} items must be CompactQualityIssue")


def _require_bool(value: bool, *, field_name: str) -> None:
    """校验 bool 字段。

    :param value: 待校验值。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段不是 bool 时抛出。
    """

    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be bool")


def _string_list_json(values: tuple[str, ...]) -> list[JsonValue]:
    """把字符串 tuple 转换为 JSON 数组。

    :param values: 字符串 tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value)
    return result


def _string_mapping_json(values: Mapping[str, str]) -> JsonValue:
    """把字符串 mapping 转换为按 key 排序的 JSON object。

    :param values: 字符串 mapping。
    :returns: JSON object。
    """

    result: dict[str, JsonValue] = {}
    for key in sorted(values):
        result[key] = values[key]
    return result


def _material_block_list_json(
    values: tuple[CompactMaterialBlock, ...]
) -> list[JsonValue]:
    """把 material block tuple 转换为 JSON 数组。

    :param values: material block tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _material_block_llm_list_json(
    values: tuple[CompactMaterialBlock, ...]
) -> list[JsonValue]:
    """把 material block tuple 转换为 LLM-facing JSON 数组。

    :param values: material block tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.llm_json())
    return result


def _evidence_block_list_json(
    values: tuple[CompactEvidenceBlock, ...]
) -> list[JsonValue]:
    """把 evidence material block tuple 转换为 JSON 数组。

    :param values: evidence block tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _evidence_block_llm_list_json(
    values: tuple[CompactEvidenceBlock, ...]
) -> list[JsonValue]:
    """把 evidence material block tuple 转换为 LLM-facing JSON 数组。

    :param values: evidence block tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.llm_json())
    return result


def _provenance_map_json(
    values: Mapping[PromptLocalMaterialLabel, PromptLocalProvenanceEntry],
) -> JsonValue:
    """把 provenance map 转换为 JSON object。

    :param values: provenance mapping。
    :returns: JSON object。
    """

    result: dict[str, JsonValue] = {}
    for key, value in values.items():
        result[key] = value.to_json()
    return result


def _opaque_ref_list_json(values: tuple[OpaqueEvidenceRef, ...]) -> list[JsonValue]:
    """把 opaque evidence ref tuple 转换为 JSON 数组。

    :param values: opaque evidence refs。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(
            {
                "ref_kind": value.ref_kind,
                "ref_id": value.ref_id,
                "digest": value.digest,
            }
        )
    return result


def _range_list_json(values: tuple[CompactInputRange, ...]) -> list[JsonValue]:
    """把 compact range tuple 转换为 JSON 数组。

    :param values: range tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _evidence_list_json(values: tuple[PreservationEvidence, ...]) -> list[JsonValue]:
    """把 preservation evidence tuple 转换为 JSON 数组。

    :param values: evidence tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _fact_candidate_list_json(
    values: tuple[EvidenceBackedFactCandidate, ...],
) -> list[JsonValue]:
    """把 evidence-backed fact candidate tuple 转换为 JSON 数组。

    :param values: candidate tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _minimum_preserve_candidate_list_json(
    values: tuple[MinimumPreserveItemCandidate, ...],
) -> list[JsonValue]:
    """把 minimum preserve item candidate tuple 转换为 JSON 数组。

    :param values: candidate tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _budget_estimate_json(estimate: BudgetEstimate) -> JsonValue:
    """把 budget estimate 转换为 JSON object。

    :param estimate: budget estimate。
    :returns: JSON object。
    """

    return {
        "estimated_input_tokens": estimate.estimated_input_tokens,
        "input_budget_tokens": estimate.input_budget_tokens,
        "soft_threshold_tokens": estimate.soft_threshold_tokens,
        "hard_threshold_tokens": estimate.hard_threshold_tokens,
        "safety_margin_tokens": estimate.safety_margin_tokens,
        "estimator_digest": estimate.estimator_digest,
        "overage_reason": (
            None if estimate.overage_reason is None else estimate.overage_reason.value
        ),
    }


__all__ = [
    "CompactEvidenceBlock",
    "CompactInputRange",
    "CompactMaterialBlock",
    "CompactMaterialBlockKind",
    "CompactMaterialPack",
    "CompactMaterialSection",
    "CompactQualityCheckResult",
    "CompactQualityIssue",
    "CompactSegmentSelection",
    "CompactSegmentTrigger",
    "CompactionCandidate",
    "CompactionRequest",
    "ContextCompactor",
    "CurrentInputAnchor",
    "EpisodeSummaryCandidate",
    "EvidenceBackedFactCandidate",
    "EvidenceBackedFactKind",
    "MAX_EVIDENCE_BACKED_FACT_ATTRIBUTES_JSON_CHARS",
    "MAX_EVIDENCE_BACKED_FACT_CANDIDATES",
    "MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS",
    "MAX_EVIDENCE_REFS_PER_FACT",
    "MAX_MINIMUM_PRESERVE_ITEM_CANDIDATES",
    "MAX_MINIMUM_PRESERVE_ITEM_LABEL_CHARS",
    "MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS",
    "MAX_SOURCE_REFS_PER_MINIMUM_PRESERVE_ITEM",
    "MinimumPreserveItemCandidate",
    "MinimumPreserveReason",
    "PinnedPatchOperation",
    "PinnedStatePatchCandidate",
    "PinnedStringTupleFieldPatch",
    "PinnedTextFieldPatch",
    "PromptLocalEvidenceMap",
    "PromptLocalMaterialLabel",
    "PromptLocalProvenanceEntry",
    "PreservationEvidence",
    "missing_string_tuple_patch",
    "missing_text_patch",
]
