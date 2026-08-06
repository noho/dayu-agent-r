"""Host Context Governance 的严格 compact v4 类型契约。

本模块只拥有 compactor 输入、候选输出、验收真值与 material provenance
的类型边界；它不调用模型、不写 EventLog，也不更新 Memory projection。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Literal, Protocol

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.runner_identity import SuccessfulRunnerResponseIdentity
from dayu.host._public_validation import (
    require_non_empty as _require_non_empty,
)
from dayu.host._public_validation import (
    require_non_negative_int as _require_non_negative_int,
)
from dayu.host.context_budget import BudgetEstimate
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.evidence import OpaqueEvidenceRef

COMPACT_INPUT_SCHEMA_V4 = "dayu.context_compaction.input.v4"
"""严格 compactor 输入 schema。"""

COMPACT_OUTPUT_SCHEMA_V4 = "dayu.context_compaction.output.v4"
"""严格 compactor 输出 schema。"""


class CompactMaterialSection(StrEnum):
    """vNext compact material pack 的 LLM-facing section。"""

    PREVIOUS_COMPACTED_VIEW = "previous_compacted_view"
    TRACE_MATERIAL = "trace_material"
    EVIDENCE_MATERIAL = "evidence_material"
    ANSWER_MATERIAL = "answer_material"
    CURRENT_INPUT_ANCHOR = "current_input_anchor"


class CompactMaterialBlockKind(StrEnum):
    """vNext compact material block 的 Host-neutral 类型。"""

    SESSION_SUMMARY = "session_summary"
    EVIDENCE_BACKED_FACT = "evidence_backed_fact"
    ANSWER_ANCHOR = "answer_anchor"
    FORWARD_INTENT = "forward_intent"
    REFERENCE_CONTINUITY = "reference_continuity"
    USER_INPUT = "user_input"
    ASSISTANT_FINAL_ANSWER = "assistant_final_answer"
    USER_VISIBLE_RUN_STATE = "user_visible_run_state"
    ACCEPTED_TOOL_EVIDENCE = "accepted_tool_evidence"
    CURRENT_INPUT_ANCHOR = "current_input_anchor"


class CompactSourceKindV4(StrEnum):
    """source boundary 条目的业务来源类型。"""

    PREVIOUS_SESSION_SUMMARY = "previous_session_summary"
    PREVIOUS_EVIDENCE_FACT = "previous_evidence_fact"
    PREVIOUS_ANSWER_ANCHOR = "previous_answer_anchor"
    PREVIOUS_FORWARD_INTENT = "previous_forward_intent"
    PREVIOUS_REFERENCE_CONTINUITY = "previous_reference_continuity"
    TRACE_MATERIAL = "trace_material"
    EVIDENCE_MATERIAL = "evidence_material"
    ANSWER_MATERIAL = "answer_material"


class CompactSemanticSectionV4(StrEnum):
    """candidate 中可形成 represented coverage 的业务区。"""

    SESSION_SUMMARY = "session_summary"
    EVIDENCE_FACTS = "evidence_facts"
    ANSWER_ANCHORS = "answer_anchors"
    FORWARD_INTENTS = "forward_intents"
    REFERENCE_CONTINUITY = "reference_continuity"


_COMPACT_POLICY_USAGE_MEASUREMENT_RULES_V4 = MappingProxyType(
    {
        CompactSemanticSectionV4.SESSION_SUMMARY.value: "text 的字符数",
        CompactSemanticSectionV4.EVIDENCE_FACTS.value: "各项 claim 的字符数之和",
        CompactSemanticSectionV4.ANSWER_ANCHORS.value: (
            "各项 title + 一个换行符 + detail 的字符数之和"
        ),
        CompactSemanticSectionV4.FORWARD_INTENTS.value: "各项 text 的字符数之和",
        CompactSemanticSectionV4.REFERENCE_CONTINUITY.value: (
            "各项 text 的字符数之和；reason 不计入"
        ),
    }
)
"""compact v4 各业务区字符用量的唯一业务可读计量规则。"""


class TraceReadableKindVNext(StrEnum):
    """vNext trace material 的可读类型。"""

    USER_INPUT = "user_input"
    ASSISTANT_FINAL_ANSWER = "assistant_final_answer"
    USER_VISIBLE_PROGRESS = "user_visible_progress"


class CompactForwardIntentStatusV4(StrEnum):
    """vNext forward intent 状态。"""

    OPEN = "open"
    BLOCKED = "blocked"
    SUPERSEDED = "superseded"


COMPACT_FACT_SOURCE_KINDS_V4 = (CompactSourceKindV4.EVIDENCE_MATERIAL,)
"""本轮新增 evidence fact 的 support label 允许来源。"""

COMPACT_RETAIN_SOURCE_KINDS_V4 = (CompactSourceKindV4.PREVIOUS_EVIDENCE_FACT,)
"""旧 evidence fact retain selector 的唯一允许来源。"""

COMPACT_FACT_CONTEXT_SOURCE_KINDS_V4 = (
    CompactSourceKindV4.TRACE_MATERIAL,
    CompactSourceKindV4.ANSWER_MATERIAL,
)
"""evidence fact 的 context label 允许来源。"""

COMPACT_ANSWER_SOURCE_KINDS_V4 = (
    CompactSourceKindV4.PREVIOUS_ANSWER_ANCHOR,
    CompactSourceKindV4.ANSWER_MATERIAL,
)
"""answer anchor 允许来源。"""

COMPACT_FORWARD_SOURCE_KINDS_V4 = (
    CompactSourceKindV4.PREVIOUS_FORWARD_INTENT,
    CompactSourceKindV4.TRACE_MATERIAL,
    CompactSourceKindV4.ANSWER_MATERIAL,
)
"""forward intent 允许来源。"""

COMPACT_REFERENCE_SOURCE_KINDS_V4 = (
    CompactSourceKindV4.PREVIOUS_REFERENCE_CONTINUITY,
    CompactSourceKindV4.TRACE_MATERIAL,
    CompactSourceKindV4.EVIDENCE_MATERIAL,
    CompactSourceKindV4.ANSWER_MATERIAL,
)
"""reference continuity 允许来源。"""


class CompactValidationIssueCodeV4(StrEnum):
    """严格 parser 与 Host acceptance 的稳定问题码。"""

    INVALID_JSON = "invalid_json"
    DUPLICATE_JSON_KEY = "duplicate_json_key"
    UNKNOWN_JSON_KEY = "unknown_json_key"
    MISSING_REQUIRED_KEY = "missing_required_key"
    INVALID_FIELD_TYPE = "invalid_field_type"
    INVALID_ENUM_VALUE = "invalid_enum_value"
    BLANK_REQUIRED_TEXT = "blank_required_text"
    UNKNOWN_SOURCE_LABEL = "unknown_source_label"
    DUPLICATE_SOURCE_LABEL = "duplicate_source_label"
    SOURCE_KIND_MISMATCH = "source_kind_mismatch"
    NON_CANONICAL_SOURCE_LABEL_ORDER = "non_canonical_source_label_order"
    DUPLICATE_SEMANTIC_ITEM = "duplicate_semantic_item"
    CONTRADICTORY_SEMANTIC_ITEM = "contradictory_semantic_item"
    EMPTY_SEMANTIC_OUTPUT = "empty_semantic_output"
    LOW_INFORMATION_OUTPUT = "low_information_output"
    POLICY_ITEM_CAP_EXCEEDED = "policy_item_cap_exceeded"
    POLICY_SIZE_CAP_EXCEEDED = "policy_size_cap_exceeded"


class CompactSegmentTrigger(StrEnum):
    """Compact segment selection 的触发来源。"""

    PROACTIVE = "proactive"
    REACTIVE = "reactive"


class CompactSegmentSelectionScope(StrEnum):
    """Compact segment selection 的闭集治理 scope。"""

    ROOT = "root"
    TRANSIENT = "transient"


PromptLocalMaterialLabel = str
"""Prompt-local material label 的类型别名。"""


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
        _require_non_empty(self.start_input_ref, field_name="CompactInputRange.start_input_ref")
        _require_non_empty(self.end_input_ref, field_name="CompactInputRange.end_input_ref")

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
    :param canonical_evidence_refs: 该材料对应的 canonical evidence refs。
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
    canonical_evidence_refs: tuple[str, ...]
    tool_result_event_ref: str | None
    tool_call_event_ref: str | None
    payload_refs: tuple[str, ...]
    artifact_refs: tuple[str, ...]
    source_locator_refs: tuple[OpaqueEvidenceRef, ...]
    chunk_parent_label: PromptLocalMaterialLabel | None
    chunk_ordinal: int | None

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
        _require_unique_string_tuple(
            self.canonical_evidence_refs,
            field_name="PromptLocalProvenanceEntry.canonical_evidence_refs",
        )
        _require_optional_non_empty(
            self.tool_result_event_ref,
            field_name="PromptLocalProvenanceEntry.tool_result_event_ref",
        )
        _require_optional_non_empty(
            self.tool_call_event_ref,
            field_name="PromptLocalProvenanceEntry.tool_call_event_ref",
        )
        _require_string_tuple(self.payload_refs, field_name="PromptLocalProvenanceEntry.payload_refs")
        _require_string_tuple(self.artifact_refs, field_name="PromptLocalProvenanceEntry.artifact_refs")
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
        evidence_kind = self.kind is CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE
        previous_fact_kind = self.kind is CompactMaterialBlockKind.EVIDENCE_BACKED_FACT
        if evidence_kind or previous_fact_kind:
            _require_non_empty_unique_string_tuple(
                self.canonical_evidence_refs,
                field_name="PromptLocalProvenanceEntry.canonical_evidence_refs",
            )
        elif self.canonical_evidence_refs:
            raise ValueError(
                "PromptLocalProvenanceEntry.canonical_evidence_refs must be empty "
                "for non-evidence material"
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
            "canonical_evidence_refs": _string_list_json(
                self.canonical_evidence_refs
            ),
            "tool_result_event_ref": self.tool_result_event_ref,
            "tool_call_event_ref": self.tool_call_event_ref,
            "payload_refs": _string_list_json(self.payload_refs),
            "artifact_refs": _string_list_json(self.artifact_refs),
            "source_locator_refs": _opaque_ref_list_json(self.source_locator_refs),
            "chunk_parent_label": self.chunk_parent_label,
            "chunk_ordinal": self.chunk_ordinal,
        }


PromptLocalEvidenceMap = Mapping[PromptLocalMaterialLabel, PromptLocalProvenanceEntry]
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
    :param canonical_evidence_refs: previous fact 的逐事实 evidence refs。
    :param content_digest: 文本 digest。
    """

    block_label: PromptLocalMaterialLabel
    section: CompactMaterialSection
    kind: CompactMaterialBlockKind
    text: str
    size_units: int
    source_labels: tuple[PromptLocalMaterialLabel, ...]
    canonical_source_refs: tuple[str, ...]
    canonical_evidence_refs: tuple[str, ...]
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
        _require_non_negative_int(self.size_units, field_name="CompactMaterialBlock.size_units")
        _require_string_tuple(self.source_labels, field_name="CompactMaterialBlock.source_labels")
        _require_string_tuple(
            self.canonical_source_refs,
            field_name="CompactMaterialBlock.canonical_source_refs",
        )
        _require_unique_string_tuple(
            self.canonical_evidence_refs,
            field_name="CompactMaterialBlock.canonical_evidence_refs",
        )
        if self.kind is CompactMaterialBlockKind.EVIDENCE_BACKED_FACT:
            _require_non_empty_unique_string_tuple(
                self.canonical_evidence_refs,
                field_name="CompactMaterialBlock.canonical_evidence_refs",
            )
        elif self.canonical_evidence_refs:
            raise ValueError(
                "CompactMaterialBlock.canonical_evidence_refs must be empty "
                "for non-fact material"
            )
        _require_non_empty(self.content_digest, field_name="CompactMaterialBlock.content_digest")

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
            "canonical_evidence_refs": _string_list_json(
                self.canonical_evidence_refs
            ),
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

        _require_non_empty(self.evidence_label, field_name="CompactEvidenceBlock.evidence_label")
        _require_non_empty(
            self.readable_tool_name,
            field_name="CompactEvidenceBlock.readable_tool_name",
        )
        _require_non_empty(
            self.readable_query_text,
            field_name="CompactEvidenceBlock.readable_query_text",
        )
        _require_non_empty(self.raw_result_text, field_name="CompactEvidenceBlock.raw_result_text")
        _require_non_empty(
            self.readable_source_text,
            field_name="CompactEvidenceBlock.readable_source_text",
        )
        _require_non_negative_int(self.size_units, field_name="CompactEvidenceBlock.size_units")
        _require_string_tuple(
            self.canonical_source_refs,
            field_name="CompactEvidenceBlock.canonical_source_refs",
        )
        _require_non_empty(self.content_digest, field_name="CompactEvidenceBlock.content_digest")

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

        _require_non_empty(self.anchor_label, field_name="CurrentInputAnchor.anchor_label")
        _require_non_empty(self.anchor_text, field_name="CurrentInputAnchor.anchor_text")
        _require_bool(self.truncated, field_name="CurrentInputAnchor.truncated")
        _require_string_tuple(
            self.canonical_source_refs,
            field_name="CurrentInputAnchor.canonical_source_refs",
        )
        _require_non_empty(self.content_digest, field_name="CurrentInputAnchor.content_digest")

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
class CompactCurrentInputV4:
    """当前用户输入的不可引用保护锚点。

    :param source_ref: 当前输入 canonical ref；只供 Host 使用。
    :param readable_text: 投影给模型的业务可读文本。
    """

    source_ref: str
    readable_text: str

    def __post_init__(self) -> None:
        """校验 vNext current input anchor。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段为空时抛出。
        """

        _require_non_empty(self.source_ref, field_name="CompactCurrentInputV4.source_ref")
        _require_non_empty(self.readable_text, field_name="CompactCurrentInputV4.readable_text")

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {"readable_text": self.readable_text}


@dataclass(frozen=True, slots=True)
class CompactSourceBoundaryEntryV4:
    """本次 compaction 可引用、可替换的单一 source。

    :param source_label: prompt-local 不透明引用标签。
    :param source_kind: source 的业务类型。
    :param source_refs: 非空且唯一的 canonical refs；不投影给模型。
    :param canonical_evidence_refs: 逐条 evidence provenance；不投影给模型。
    :param readable_text: 自解释的业务可读文本。
    """

    source_label: str
    source_kind: CompactSourceKindV4
    source_refs: tuple[str, ...]
    canonical_evidence_refs: tuple[str, ...]
    readable_text: str

    def __post_init__(self) -> None:
        """校验 source boundary entry。

        :returns: ``None``。
        :raises TypeError: source kind 类型非法时抛出。
        :raises ValueError: 文本或 refs 非法时抛出。
        """

        _require_non_empty(self.source_label, field_name="CompactSourceBoundaryEntryV4.source_label")
        if not isinstance(self.source_kind, CompactSourceKindV4):
            raise TypeError("CompactSourceBoundaryEntryV4.source_kind is invalid")
        _require_non_empty_unique_string_tuple(
            self.source_refs,
            field_name="CompactSourceBoundaryEntryV4.source_refs",
        )
        _require_unique_string_tuple(
            self.canonical_evidence_refs,
            field_name="CompactSourceBoundaryEntryV4.canonical_evidence_refs",
        )
        evidence_kind = self.source_kind in (
            CompactSourceKindV4.PREVIOUS_EVIDENCE_FACT,
            CompactSourceKindV4.EVIDENCE_MATERIAL,
        )
        if evidence_kind:
            _require_non_empty_unique_string_tuple(
                self.canonical_evidence_refs,
                field_name="CompactSourceBoundaryEntryV4.canonical_evidence_refs",
            )
        elif self.canonical_evidence_refs:
            raise ValueError(
                "CompactSourceBoundaryEntryV4.canonical_evidence_refs must be "
                "empty for non-evidence source kind"
            )
        _require_non_empty(self.readable_text, field_name="CompactSourceBoundaryEntryV4.readable_text")

    def to_json(self) -> JsonValue:
        """转换为 LLM-facing JSON。

        :returns: 不含 canonical refs 的 JSON object。
        """

        return {
            "source_label": self.source_label,
            "source_kind": self.source_kind.value,
            "readable_text": self.readable_text,
        }

    def to_internal_json(self) -> JsonValue:
        """转换为 Host-internal durable JSON object。

        :returns: 同时包含来源 refs 与证据 refs 的完整 boundary snapshot。
        :raises Exception: 不主动抛出异常。
        """

        return {
            "source_label": self.source_label,
            "source_kind": self.source_kind.value,
            "source_refs": _string_list_json(self.source_refs),
            "canonical_evidence_refs": _string_list_json(
                self.canonical_evidence_refs
            ),
            "readable_text": self.readable_text,
        }


@dataclass(frozen=True, slots=True)
class ReadableFactItemVNext:
    """vNext previous compacted view 中的可读 fact。

    :param source_label: prompt-local source label。
    :param claim_text: fact 可读声明。
    :param source_note: 可选来源说明。
    """

    source_label: PromptLocalMaterialLabel
    claim_text: str
    source_note: str | None = None

    def __post_init__(self) -> None:
        """校验可读 fact。

        :returns: ``None``。
        :raises ValueError: 文本为空时抛出。
        """

        _require_non_empty(self.source_label, field_name="ReadableFactItemVNext.source_label")
        _require_non_empty(self.claim_text, field_name="ReadableFactItemVNext.claim_text")
        _require_optional_non_empty(self.source_note, field_name="ReadableFactItemVNext.source_note")

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {
            "source_label": self.source_label,
            "claim_text": self.claim_text,
            "source_note": self.source_note,
        }


@dataclass(frozen=True, slots=True)
class ReadableAnswerAnchorItemVNext:
    """vNext 可读 answer anchor 子项。

    :param display_text: 展示文本。
    :param ordinal: 可选序号。
    """

    display_text: str
    ordinal: int | None = None

    def __post_init__(self) -> None:
        """校验可读 answer anchor 子项。

        :returns: ``None``。
        :raises ValueError: 文本为空或序号非法时抛出。
        """

        _require_non_empty(self.display_text, field_name="ReadableAnswerAnchorItemVNext.display_text")
        if self.ordinal is not None:
            _require_non_negative_int(self.ordinal, field_name="ReadableAnswerAnchorItemVNext.ordinal")

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {"display_text": self.display_text, "ordinal": self.ordinal}


@dataclass(frozen=True, slots=True)
class ReadableAnswerAnchorVNext:
    """vNext previous compacted view 中的可读 answer anchor。

    :param source_label: prompt-local source label。
    :param anchor_title: anchor 标题。
    :param anchor_items: anchor 子项。
    """

    source_label: PromptLocalMaterialLabel
    anchor_title: str
    anchor_items: tuple[ReadableAnswerAnchorItemVNext, ...]

    def __post_init__(self) -> None:
        """校验可读 answer anchor。

        :returns: ``None``。
        :raises TypeError: 子项类型非法时抛出。
        :raises ValueError: 字段为空时抛出。
        """

        _require_non_empty(self.source_label, field_name="ReadableAnswerAnchorVNext.source_label")
        _require_non_empty(self.anchor_title, field_name="ReadableAnswerAnchorVNext.anchor_title")
        _require_readable_answer_anchor_item_tuple(
            self.anchor_items,
            field_name="ReadableAnswerAnchorVNext.anchor_items",
            require_non_empty=True,
        )

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {
            "source_label": self.source_label,
            "anchor_title": self.anchor_title,
            "anchor_items": _readable_answer_anchor_item_list_json(self.anchor_items),
        }


@dataclass(frozen=True, slots=True)
class ReadableForwardIntentVNext:
    """vNext previous compacted view 中的可读 forward intent。

    :param source_label: prompt-local source label。
    :param intent_type: intent 类型。
    :param text: intent 文本。
    :param status: intent 状态。
    """

    source_label: PromptLocalMaterialLabel
    intent_type: str
    text: str
    status: CompactForwardIntentStatusV4

    def __post_init__(self) -> None:
        """校验可读 forward intent。

        :returns: ``None``。
        :raises TypeError: enum 类型非法时抛出。
        :raises ValueError: 字段为空时抛出。
        """

        _require_non_empty(self.source_label, field_name="ReadableForwardIntentVNext.source_label")
        _require_non_empty(
            self.intent_type,
            field_name="ReadableForwardIntentVNext.intent_type",
        )
        if not isinstance(self.status, CompactForwardIntentStatusV4):
            raise TypeError("ReadableForwardIntentVNext.status is invalid")
        _require_non_empty(self.text, field_name="ReadableForwardIntentVNext.text")

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {
            "source_label": self.source_label,
            "intent_type": self.intent_type,
            "text": self.text,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True)
class ReadableReferenceContinuityItemVNext:
    """vNext previous compacted view 中的可读指代连续性项。

    :param source_label: prompt-local source label。
    :param text: 连续性文本。
    :param reason: 保留原因。
    """

    source_label: PromptLocalMaterialLabel
    text: str
    reason: str

    def __post_init__(self) -> None:
        """校验可读 reference continuity item。

        :returns: ``None``。
        :raises TypeError: enum 类型非法时抛出。
        :raises ValueError: 文本为空时抛出。
        """

        _require_non_empty(self.source_label, field_name="ReadableReferenceContinuityItemVNext.source_label")
        _require_non_empty(
            self.reason,
            field_name="ReadableReferenceContinuityItemVNext.reason",
        )
        _require_non_empty(self.text, field_name="ReadableReferenceContinuityItemVNext.text")

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {
            "source_label": self.source_label,
            "text": self.text,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PreviousCompactReadableView:
    """vNext previous compacted view。

    :param session_summary: 可选 session summary。
    :param evidence_backed_facts: 可读 fact 项。
    :param answer_anchors: 可读 answer anchors。
    :param forward_intents: 可读 forward intents。
    :param reference_continuity_items: 可读 reference continuity items。
    """

    session_summary: str | None
    evidence_backed_facts: tuple[ReadableFactItemVNext, ...]
    answer_anchors: tuple[ReadableAnswerAnchorVNext, ...]
    forward_intents: tuple[ReadableForwardIntentVNext, ...]
    reference_continuity_items: tuple[ReadableReferenceContinuityItemVNext, ...]

    def __post_init__(self) -> None:
        """校验 previous compacted view。

        :returns: ``None``。
        :raises TypeError: 子项类型非法时抛出。
        :raises ValueError: 文本为空时抛出。
        """

        if self.session_summary is not None:
            _require_non_empty(self.session_summary, field_name="PreviousCompactReadableView.session_summary")
        _require_readable_fact_tuple(
            self.evidence_backed_facts, field_name="PreviousCompactReadableView.evidence_backed_facts"
        )
        _require_readable_answer_anchor_tuple(
            self.answer_anchors, field_name="PreviousCompactReadableView.answer_anchors"
        )
        _require_readable_forward_intent_tuple(
            self.forward_intents, field_name="PreviousCompactReadableView.forward_intents"
        )
        _require_readable_reference_tuple(
            self.reference_continuity_items,
            field_name="PreviousCompactReadableView.reference_continuity_items",
        )

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {
            "session_summary": self.session_summary,
            "evidence_backed_facts": _readable_fact_list_json(self.evidence_backed_facts),
            "answer_anchors": _readable_answer_anchor_list_json(self.answer_anchors),
            "forward_intents": _readable_forward_intent_list_json(self.forward_intents),
            "reference_continuity_items": _readable_reference_list_json(self.reference_continuity_items),
        }


@dataclass(frozen=True, slots=True)
class TraceReadableItemVNext:
    """vNext trace material item。

    :param source_label: prompt-local source label。
    :param trace_kind: trace 类型。
    :param text: 可读文本。
    """

    source_label: PromptLocalMaterialLabel
    trace_kind: TraceReadableKindVNext
    text: str

    def __post_init__(self) -> None:
        """校验 trace material item。

        :returns: ``None``。
        :raises TypeError: enum 类型非法时抛出。
        :raises ValueError: 文本为空时抛出。
        """

        _require_non_empty(self.source_label, field_name="TraceReadableItemVNext.source_label")
        if not isinstance(self.trace_kind, TraceReadableKindVNext):
            raise TypeError("TraceReadableItemVNext.trace_kind is invalid")
        _require_non_empty(self.text, field_name="TraceReadableItemVNext.text")

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {
            "source_label": self.source_label,
            "trace_kind": self.trace_kind.value,
            "text": self.text,
        }


@dataclass(frozen=True, slots=True)
class EvidenceReadableItemVNext:
    """vNext evidence material item。

    :param source_label: prompt-local evidence label。
    :param tool_name: 可读工具名。
    :param query_text: 可选查询文本。
    :param response_text: 可读工具结果文本。
    :param source_note: 可选来源说明。
    """

    source_label: PromptLocalMaterialLabel
    tool_name: str
    query_text: str | None
    response_text: str
    source_note: str | None = None

    def __post_init__(self) -> None:
        """校验 evidence material item。

        :returns: ``None``。
        :raises ValueError: 必需文本为空时抛出。
        """

        _require_non_empty(self.source_label, field_name="EvidenceReadableItemVNext.source_label")
        _require_non_empty(self.tool_name, field_name="EvidenceReadableItemVNext.tool_name")
        _require_optional_non_empty(self.query_text, field_name="EvidenceReadableItemVNext.query_text")
        _require_non_empty(self.response_text, field_name="EvidenceReadableItemVNext.response_text")
        _require_optional_non_empty(self.source_note, field_name="EvidenceReadableItemVNext.source_note")

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {
            "source_label": self.source_label,
            "tool_name": self.tool_name,
            "query_text": self.query_text,
            "response_text": self.response_text,
            "source_note": self.source_note,
        }


@dataclass(frozen=True, slots=True)
class AnswerReadableItemVNext:
    """vNext answer material item。

    :param source_label: prompt-local answer label。
    :param answer_text: 可读 assistant final answer 文本。
    """

    source_label: PromptLocalMaterialLabel
    answer_text: str

    def __post_init__(self) -> None:
        """校验 answer material item。

        :returns: ``None``。
        :raises ValueError: 文本为空时抛出。
        """

        _require_non_empty(self.source_label, field_name="AnswerReadableItemVNext.source_label")
        _require_non_empty(self.answer_text, field_name="AnswerReadableItemVNext.answer_text")

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {"source_label": self.source_label, "answer_text": self.answer_text}


@dataclass(frozen=True, slots=True)
class CompactOutputCapsV4:
    """模型输出上限的不可变边界投影。

    该 DTO 不拥有默认值、数值校验或配置读取；所有字段只能由 Context
    Governance 从同一个 :class:`MemoryProjectionPolicy` 实例机械投影。

    :param session_summary_char_cap: session summary 字符上限。
    :param evidence_fact_item_cap: evidence fact 数量上限。
    :param evidence_fact_char_cap: evidence fact 字符上限。
    :param answer_anchor_item_cap: answer anchor 数量上限。
    :param answer_anchor_char_cap: answer anchor 字符上限。
    :param forward_intent_item_cap: forward intent 数量上限。
    :param forward_intent_char_cap: forward intent 字符上限。
    :param reference_continuity_item_cap: reference continuity 数量上限。
    :param reference_continuity_char_cap: reference continuity 字符上限。
    """

    session_summary_char_cap: int
    evidence_fact_item_cap: int
    evidence_fact_char_cap: int
    answer_anchor_item_cap: int
    answer_anchor_char_cap: int
    forward_intent_item_cap: int
    forward_intent_char_cap: int
    reference_continuity_item_cap: int
    reference_continuity_char_cap: int

    def to_json(self) -> JsonValue:
        """转换为 LLM-facing JSON object。

        :returns: 与 Memory policy 数值逐字段同源的 JSON object。
        """

        return {
            "session_summary_char_cap": self.session_summary_char_cap,
            "evidence_fact_item_cap": self.evidence_fact_item_cap,
            "evidence_fact_char_cap": self.evidence_fact_char_cap,
            "answer_anchor_item_cap": self.answer_anchor_item_cap,
            "answer_anchor_char_cap": self.answer_anchor_char_cap,
            "forward_intent_item_cap": self.forward_intent_item_cap,
            "forward_intent_char_cap": self.forward_intent_char_cap,
            "reference_continuity_item_cap": self.reference_continuity_item_cap,
            "reference_continuity_char_cap": self.reference_continuity_char_cap,
        }


@dataclass(frozen=True, slots=True)
class CompactInputV4:
    """严格 v4 compactor 输入。

    :param schema: 固定 v4 schema literal。
    :param current_input: 不可引用且必须保留的当前输入。
    :param source_boundary: 本次候选可通过 provenance 表示的 immutable sources。
    :param output_caps: 同一 Memory policy 的真实输出上限投影。
    """

    schema: Literal["dayu.context_compaction.input.v4"]
    current_input: CompactCurrentInputV4
    source_boundary: tuple[CompactSourceBoundaryEntryV4, ...]
    output_caps: CompactOutputCapsV4

    def __post_init__(self) -> None:
        """校验 vNext compactor 输入 contract。

        :returns: ``None``。
        :raises TypeError: 子项类型非法时抛出。
        :raises ValueError: schema 或 label 集合非法时抛出。
        """

        if self.schema != COMPACT_INPUT_SCHEMA_V4:
            raise ValueError("CompactInputV4.schema is invalid")
        if not isinstance(self.current_input, CompactCurrentInputV4):
            raise TypeError("CompactInputV4.current_input is invalid")
        for entry in self.source_boundary:
            if not isinstance(entry, CompactSourceBoundaryEntryV4):
                raise TypeError("CompactInputV4.source_boundary item is invalid")
        if not isinstance(self.output_caps, CompactOutputCapsV4):
            raise TypeError("CompactInputV4.output_caps is invalid")
        _require_unique_string_tuple(self.source_labels, field_name="CompactInputV4.source_labels")

    @property
    def source_labels(self) -> tuple[str, ...]:
        """返回 boundary label 的固定顺序。

        :returns: prompt-local source labels。
        """

        return tuple(entry.source_label for entry in self.source_boundary)

    def source_kind(self, label: PromptLocalMaterialLabel) -> CompactSourceKindV4 | None:
        """返回 label 对应 source kind。

        :param label: prompt-local label。
        :returns: label 所属 section；未知时返回 ``None``。
        """

        for entry in self.source_boundary:
            if entry.source_label == label:
                return entry.source_kind
        return None

    def to_json(self) -> JsonValue:
        """转换为 LLM-facing JSON object。

        :returns: 不含 Host provenance 的 JSON object。
        """

        return {
            "schema": self.schema,
            "current_input": self.current_input.to_json(),
            "source_boundary": [entry.to_json() for entry in self.source_boundary],
            "output_caps": self.output_caps.to_json(),
        }


@dataclass(frozen=True, slots=True)
class CompactSessionSummaryV4:
    """vNext session summary candidate。

    :param summary_text: summary 文本。
    :param source_labels: 支撑 summary 的 prompt-local labels。
    """

    text: str
    source_labels: tuple[PromptLocalMaterialLabel, ...]

    def __post_init__(self) -> None:
        """校验 vNext session summary candidate。

        :returns: ``None``。
        :raises ValueError: 文本或 source labels 非法时抛出。
        """

        _require_non_empty(self.text, field_name="CompactSessionSummaryV4.text")
        _require_non_empty_unique_string_tuple(
            self.source_labels,
            field_name="CompactSessionSummaryV4.source_labels",
        )

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {
            "text": self.text,
            "source_labels": _string_list_json(self.source_labels),
        }


@dataclass(frozen=True, slots=True)
class CompactEvidenceFactV4:
    """vNext evidence-backed fact candidate。

    :param claim_text: fact claim 文本。
    :param evidence_labels: 支撑事实的 evidence labels。
    :param source_labels: 可选辅助 source labels。
    """

    claim: str
    support_labels: tuple[PromptLocalMaterialLabel, ...]
    context_labels: tuple[PromptLocalMaterialLabel, ...]

    def __post_init__(self) -> None:
        """校验 vNext evidence-backed fact candidate。

        :returns: ``None``。
        :raises ValueError: 文本或 labels 非法时抛出。
        """

        _require_non_empty(self.claim, field_name="CompactEvidenceFactV4.claim")
        _require_non_empty_unique_string_tuple(
            self.support_labels,
            field_name="CompactEvidenceFactV4.support_labels",
        )
        _require_unique_string_tuple(
            self.context_labels,
            field_name="CompactEvidenceFactV4.context_labels",
        )

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {
            "claim": self.claim,
            "support_labels": _string_list_json(self.support_labels),
            "context_labels": _string_list_json(self.context_labels),
        }


@dataclass(frozen=True, slots=True)
class CompactAnswerAnchorV4:
    """vNext answer anchor candidate。

    :param anchor_title: anchor 标题。
    :param anchor_items: anchor 子项。
    :param answer_source_labels: answer material labels。
    """

    title: str
    detail: str
    source_labels: tuple[PromptLocalMaterialLabel, ...]

    def __post_init__(self) -> None:
        """校验 vNext answer anchor candidate。

        :returns: ``None``。
        :raises TypeError: 子项类型非法时抛出。
        :raises ValueError: 文本或 labels 非法时抛出。
        """

        _require_non_empty(self.title, field_name="CompactAnswerAnchorV4.title")
        _require_non_empty(self.detail, field_name="CompactAnswerAnchorV4.detail")
        _require_non_empty_unique_string_tuple(
            self.source_labels,
            field_name="CompactAnswerAnchorV4.source_labels",
        )

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {
            "title": self.title,
            "detail": self.detail,
            "source_labels": _string_list_json(self.source_labels),
        }


@dataclass(frozen=True, slots=True)
class CompactForwardIntentV4:
    """vNext forward intent candidate。

    :param intent_type: intent 类型。
    :param text: intent 文本。
    :param status: intent 状态。
    :param source_labels: 支撑该 intent 的 source labels。
    """

    intent_type: str
    text: str
    status: CompactForwardIntentStatusV4
    source_labels: tuple[PromptLocalMaterialLabel, ...]

    def __post_init__(self) -> None:
        """校验 vNext forward intent candidate。

        :returns: ``None``。
        :raises TypeError: enum 类型非法时抛出。
        :raises ValueError: 文本或 labels 非法时抛出。
        """

        _require_non_empty(self.intent_type, field_name="CompactForwardIntentV4.intent_type")
        if not isinstance(self.status, CompactForwardIntentStatusV4):
            raise TypeError("CompactForwardIntentV4.status is invalid")
        _require_non_empty(self.text, field_name="CompactForwardIntentV4.text")
        _require_non_empty_unique_string_tuple(
            self.source_labels,
            field_name="CompactForwardIntentV4.source_labels",
        )

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {
            "intent_type": self.intent_type,
            "text": self.text,
            "status": self.status.value,
            "source_labels": _string_list_json(self.source_labels),
        }


@dataclass(frozen=True, slots=True)
class CompactReferenceContinuityV4:
    """vNext reference continuity candidate。

    :param text: 连续性文本。
    :param reason: 保留原因。
    :param source_labels: 支撑该连续性项的 source labels。
    """

    text: str
    reason: str
    source_labels: tuple[PromptLocalMaterialLabel, ...]

    def __post_init__(self) -> None:
        """校验 vNext reference continuity candidate。

        :returns: ``None``。
        :raises TypeError: enum 类型非法时抛出。
        :raises ValueError: 文本或 labels 非法时抛出。
        """

        _require_non_empty(self.text, field_name="CompactReferenceContinuityV4.text")
        _require_non_empty(self.reason, field_name="CompactReferenceContinuityV4.reason")
        _require_non_empty_unique_string_tuple(
            self.source_labels,
            field_name="CompactReferenceContinuityV4.source_labels",
        )

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {
            "text": self.text,
            "reason": self.reason,
            "source_labels": _string_list_json(self.source_labels),
        }


@dataclass(frozen=True, slots=True)
class CompactCandidateV4:
    """模型可返回的七字段 proposal。

    :param schema: 固定 v4 schema literal。
    :param session_summary: nullable session summary。
    :param retained_previous_evidence_fact_labels: 要原子保留的旧事实 labels。
    :param evidence_facts: 只表达本轮新 evidence-backed facts。
    :param answer_anchors: answer anchors。
    :param forward_intents: forward intents。
    :param reference_continuity: reference continuity items。
    """

    schema: Literal["dayu.context_compaction.output.v4"]
    session_summary: CompactSessionSummaryV4 | None
    retained_previous_evidence_fact_labels: tuple[PromptLocalMaterialLabel, ...]
    evidence_facts: tuple[CompactEvidenceFactV4, ...]
    answer_anchors: tuple[CompactAnswerAnchorV4, ...]
    forward_intents: tuple[CompactForwardIntentV4, ...]
    reference_continuity: tuple[CompactReferenceContinuityV4, ...]

    def __post_init__(self) -> None:
        """校验 vNext compactor 输出 contract。

        :returns: ``None``。
        :raises TypeError: 子项类型非法时抛出。
        :raises ValueError: schema 或数量非法时抛出。
        """

        if self.schema != COMPACT_OUTPUT_SCHEMA_V4:
            raise ValueError("CompactCandidateV4.schema is invalid")
        if self.session_summary is not None and not isinstance(self.session_summary, CompactSessionSummaryV4):
            raise TypeError("CompactCandidateV4.session_summary is invalid")
        _require_unique_string_tuple(
            self.retained_previous_evidence_fact_labels,
            field_name=(
                "CompactCandidateV4.retained_previous_evidence_fact_labels"
            ),
        )
        _require_fact_candidate_vnext_tuple(self.evidence_facts)
        _require_answer_anchor_candidate_tuple(self.answer_anchors)
        _require_forward_intent_candidate_tuple(self.forward_intents)
        _require_reference_candidate_tuple(self.reference_continuity)

    def digest(self) -> str:
        """计算 vNext candidate digest。

        :returns: candidate canonical JSON 的 sha256 digest。
        """

        return sha256_digest_json(self.to_json())

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {
            "schema": self.schema,
            "session_summary": None if self.session_summary is None else self.session_summary.to_json(),
            "retained_previous_evidence_fact_labels": _string_list_json(
                self.retained_previous_evidence_fact_labels
            ),
            "evidence_facts": _fact_candidate_vnext_list_json(self.evidence_facts),
            "answer_anchors": _answer_anchor_candidate_list_json(self.answer_anchors),
            "forward_intents": _forward_intent_candidate_list_json(self.forward_intents),
            "reference_continuity": _reference_candidate_list_json(self.reference_continuity),
        }


@dataclass(frozen=True, slots=True)
class CompactAcceptedEvidenceFactV4:
    """Host 验收后的不可拆分 evidence fact atom。

    :param claim: 完整业务事实文本。
    :param selection_labels: 产生该 atom 的非空 source labels。
    :param context_labels: 不贡献 evidence provenance 的辅助 labels。
    :param canonical_evidence_refs: 该 atom 自己的非空 canonical evidence refs。
    """

    claim: str
    selection_labels: tuple[PromptLocalMaterialLabel, ...]
    context_labels: tuple[PromptLocalMaterialLabel, ...]
    canonical_evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        """校验 accepted fact 的局部不变量。

        :returns: ``None``。
        :raises ValueError: 文本、selection、context 或 evidence refs 非法时抛出。
        """

        _require_non_empty(
            self.claim,
            field_name="CompactAcceptedEvidenceFactV4.claim",
        )
        _require_non_empty_unique_string_tuple(
            self.selection_labels,
            field_name="CompactAcceptedEvidenceFactV4.selection_labels",
        )
        _require_unique_string_tuple(
            self.context_labels,
            field_name="CompactAcceptedEvidenceFactV4.context_labels",
        )
        _require_non_empty_unique_string_tuple(
            self.canonical_evidence_refs,
            field_name="CompactAcceptedEvidenceFactV4.canonical_evidence_refs",
        )

    def to_json(self) -> JsonValue:
        """转换为 durable JSON object。

        :returns: 自包含 claim、selection、context 与逐事实 evidence refs。
        :raises Exception: 不主动抛出异常。
        """

        return {
            "claim": self.claim,
            "selection_labels": _string_list_json(self.selection_labels),
            "context_labels": _string_list_json(self.context_labels),
            "canonical_evidence_refs": _string_list_json(
                self.canonical_evidence_refs
            ),
        }


@dataclass(frozen=True, slots=True)
class CompactAcceptedReplacementV4:
    """Host 验收后的五类最终 Memory 语义。

    :param session_summary: nullable session summary。
    :param evidence_facts: retained atoms 在前、new atoms 在后的事实 tuple。
    :param answer_anchors: 最终 answer anchors。
    :param forward_intents: 最终 forward intents。
    :param reference_continuity: 最终 reference continuity items。
    """

    session_summary: CompactSessionSummaryV4 | None
    evidence_facts: tuple[CompactAcceptedEvidenceFactV4, ...]
    answer_anchors: tuple[CompactAnswerAnchorV4, ...]
    forward_intents: tuple[CompactForwardIntentV4, ...]
    reference_continuity: tuple[CompactReferenceContinuityV4, ...]

    def __post_init__(self) -> None:
        """校验 replacement 五区的 child types 与 tuple shape。

        :returns: ``None``。
        :raises TypeError: 任一 child 类型或 tuple shape 非法时抛出。
        """

        if self.session_summary is not None and not isinstance(
            self.session_summary,
            CompactSessionSummaryV4,
        ):
            raise TypeError(
                "CompactAcceptedReplacementV4.session_summary is invalid"
            )
        _require_accepted_fact_tuple(self.evidence_facts)
        _require_answer_anchor_candidate_tuple(self.answer_anchors)
        _require_forward_intent_candidate_tuple(self.forward_intents)
        _require_reference_candidate_tuple(self.reference_continuity)

    @property
    def canonical_evidence_refs(self) -> tuple[str, ...]:
        """按 fact / entry 顺序派生逐事实 refs 的唯一并集。

        :returns: replacement 实际使用的 canonical evidence refs。
        :raises Exception: 不主动抛出异常。
        """

        return tuple(
            dict.fromkeys(
                ref
                for fact in self.evidence_facts
                for ref in fact.canonical_evidence_refs
            )
        )

    def to_json(self) -> JsonValue:
        """转换为 durable JSON object。

        :returns: 五类最终语义的完整 JSON object。
        :raises Exception: 不主动抛出异常。
        """

        return {
            "session_summary": (
                None
                if self.session_summary is None
                else self.session_summary.to_json()
            ),
            "evidence_facts": [fact.to_json() for fact in self.evidence_facts],
            "answer_anchors": _answer_anchor_candidate_list_json(
                self.answer_anchors
            ),
            "forward_intents": _forward_intent_candidate_list_json(
                self.forward_intents
            ),
            "reference_continuity": _reference_candidate_list_json(
                self.reference_continuity
            ),
        }


def derive_compact_accepted_replacement_v4(
    source_boundary: tuple[CompactSourceBoundaryEntryV4, ...],
    proposal: CompactCandidateV4,
) -> CompactAcceptedReplacementV4:
    """从 proposal 与 immutable boundary 唯一展开 accepted replacement。

    retained previous fact 按 boundary 顺序复制完整 claim 与 refs；new fact 按
    proposal 顺序复制 claim/labels，并按 support label 顺序合并 current evidence
    entries 的 refs。其余四区保持 proposal exact。

    :param source_boundary: 本次 compact 的 immutable source boundary。
    :param proposal: strict parse 后的七字段 proposal。
    :returns: 唯一可接受的五区 replacement。
    :raises TypeError: boundary 或 proposal 类型非法时抛出。
    :raises ValueError: label 未知、kind 不允许或 evidence refs 非法时抛出。
    """

    if not isinstance(source_boundary, tuple):
        raise TypeError("source_boundary must be tuple")
    if not isinstance(proposal, CompactCandidateV4):
        raise TypeError("proposal must be CompactCandidateV4")
    entries: dict[str, CompactSourceBoundaryEntryV4] = {}
    for entry in source_boundary:
        if not isinstance(entry, CompactSourceBoundaryEntryV4):
            raise TypeError(
                "source_boundary item must be CompactSourceBoundaryEntryV4"
            )
        if entry.source_label in entries:
            raise ValueError("source_boundary labels must be unique")
        entries[entry.source_label] = entry
    issues = compact_proposal_boundary_binding_issues_v4(
        source_boundary,
        proposal,
    )
    if issues:
        raise ValueError("proposal must satisfy immutable source boundary binding")
    retained_labels = frozenset(
        proposal.retained_previous_evidence_fact_labels
    )
    facts: list[CompactAcceptedEvidenceFactV4] = []
    for entry in source_boundary:
        if entry.source_label not in retained_labels:
            continue
        if entry.source_kind is not CompactSourceKindV4.PREVIOUS_EVIDENCE_FACT:
            raise ValueError(
                "retained label must select previous_evidence_fact source"
            )
        facts.append(
            CompactAcceptedEvidenceFactV4(
                claim=entry.readable_text,
                selection_labels=(entry.source_label,),
                context_labels=(),
                canonical_evidence_refs=entry.canonical_evidence_refs,
            )
        )
    if len(facts) != len(retained_labels):
        raise ValueError("retained label must exist in source_boundary")
    for fact in proposal.evidence_facts:
        refs: list[str] = []
        support_labels = frozenset(fact.support_labels)
        for entry in source_boundary:
            if entry.source_label in support_labels:
                refs.extend(entry.canonical_evidence_refs)
        facts.append(
            CompactAcceptedEvidenceFactV4(
                claim=fact.claim,
                selection_labels=fact.support_labels,
                context_labels=fact.context_labels,
                canonical_evidence_refs=tuple(dict.fromkeys(refs)),
            )
        )
    return CompactAcceptedReplacementV4(
        session_summary=proposal.session_summary,
        evidence_facts=tuple(facts),
        answer_anchors=proposal.answer_anchors,
        forward_intents=proposal.forward_intents,
        reference_continuity=proposal.reference_continuity,
    )


def compact_proposal_boundary_binding_issues_v4(
    source_boundary: tuple[CompactSourceBoundaryEntryV4, ...],
    proposal: CompactCandidateV4,
) -> tuple[CompactValidationIssueV4, ...]:
    """返回 proposal 对 immutable boundary 的完整 deterministic 问题集。

    本函数是 label existence、duplicate、kind 与 boundary-order canonicalization
    的唯一 owner，供 Context Governance 与 durable strict parser 共同复用。

    :param source_boundary: immutable source boundary。
    :param proposal: strict parse 后的七字段 proposal。
    :returns: 按 proposal section 顺序排列的问题 tuple。
    :raises TypeError: boundary 或 proposal 类型非法时抛出。
    :raises ValueError: boundary labels 自身重复时抛出。
    """

    if not isinstance(source_boundary, tuple):
        raise TypeError("source_boundary must be tuple")
    if not isinstance(proposal, CompactCandidateV4):
        raise TypeError("proposal must be CompactCandidateV4")
    entries: dict[str, CompactSourceBoundaryEntryV4] = {}
    boundary_order: dict[str, int] = {}
    for index, entry in enumerate(source_boundary):
        if not isinstance(entry, CompactSourceBoundaryEntryV4):
            raise TypeError(
                "source_boundary item must be CompactSourceBoundaryEntryV4"
            )
        if entry.source_label in entries:
            raise ValueError("source_boundary labels must be unique")
        entries[entry.source_label] = entry
        boundary_order[entry.source_label] = index
    issues: list[CompactValidationIssueV4] = []
    _collect_compact_label_binding_issues_v4(
        proposal.session_summary.source_labels if proposal.session_summary else (),
        json_path='$["session_summary"]["source_labels"]',
        allowed_kinds=None,
        entries=entries,
        boundary_order=boundary_order,
        issues=issues,
    )
    _collect_compact_label_binding_issues_v4(
        proposal.retained_previous_evidence_fact_labels,
        json_path='$["retained_previous_evidence_fact_labels"]',
        allowed_kinds=COMPACT_RETAIN_SOURCE_KINDS_V4,
        entries=entries,
        boundary_order=boundary_order,
        issues=issues,
    )
    for index, fact in enumerate(proposal.evidence_facts):
        _collect_compact_label_binding_issues_v4(
            fact.support_labels,
            json_path=f'$["evidence_facts"][{index}]["support_labels"]',
            allowed_kinds=COMPACT_FACT_SOURCE_KINDS_V4,
            entries=entries,
            boundary_order=boundary_order,
            issues=issues,
        )
        _collect_compact_label_binding_issues_v4(
            fact.context_labels,
            json_path=f'$["evidence_facts"][{index}]["context_labels"]',
            allowed_kinds=COMPACT_FACT_CONTEXT_SOURCE_KINDS_V4,
            entries=entries,
            boundary_order=boundary_order,
            issues=issues,
        )
    for index, anchor in enumerate(proposal.answer_anchors):
        _collect_compact_label_binding_issues_v4(
            anchor.source_labels,
            json_path=f'$["answer_anchors"][{index}]["source_labels"]',
            allowed_kinds=COMPACT_ANSWER_SOURCE_KINDS_V4,
            entries=entries,
            boundary_order=boundary_order,
            issues=issues,
        )
    for index, intent in enumerate(proposal.forward_intents):
        _collect_compact_label_binding_issues_v4(
            intent.source_labels,
            json_path=f'$["forward_intents"][{index}]["source_labels"]',
            allowed_kinds=COMPACT_FORWARD_SOURCE_KINDS_V4,
            entries=entries,
            boundary_order=boundary_order,
            issues=issues,
        )
    for index, item in enumerate(proposal.reference_continuity):
        _collect_compact_label_binding_issues_v4(
            item.source_labels,
            json_path=f'$["reference_continuity"][{index}]["source_labels"]',
            allowed_kinds=COMPACT_REFERENCE_SOURCE_KINDS_V4,
            entries=entries,
            boundary_order=boundary_order,
            issues=issues,
        )
    return tuple(issues)


def _collect_compact_label_binding_issues_v4(
    labels: tuple[str, ...],
    *,
    json_path: str,
    allowed_kinds: tuple[CompactSourceKindV4, ...] | None,
    entries: Mapping[str, CompactSourceBoundaryEntryV4],
    boundary_order: Mapping[str, int],
    issues: list[CompactValidationIssueV4],
) -> None:
    """收集单个 label tuple 的 boundary binding 问题。

    :param labels: 待校验 label tuple。
    :param json_path: proposal JSON path。
    :param allowed_kinds: 允许 kind；``None`` 表示任意 kind。
    :param entries: boundary label lookup。
    :param boundary_order: boundary ordinal lookup。
    :param issues: deterministic issue accumulator。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    seen: set[str] = set()
    for label in labels:
        if label in seen:
            issues.append(
                CompactValidationIssueV4(
                    code=CompactValidationIssueCodeV4.DUPLICATE_SOURCE_LABEL,
                    json_path=json_path,
                    message="同一 source label 在该列表中只能出现一次。",
                    source_labels=(label,),
                )
            )
            continue
        seen.add(label)
        entry = entries.get(label)
        if entry is None:
            issues.append(
                CompactValidationIssueV4(
                    code=CompactValidationIssueCodeV4.UNKNOWN_SOURCE_LABEL,
                    json_path=json_path,
                    message="source label 必须来自当前 source_boundary。",
                    source_labels=(label,),
                )
            )
        elif allowed_kinds is not None and entry.source_kind not in allowed_kinds:
            issues.append(
                CompactValidationIssueV4(
                    code=CompactValidationIssueCodeV4.SOURCE_KIND_MISMATCH,
                    json_path=json_path,
                    message="source label 的 material kind 不允许用于该字段。",
                    source_labels=(label,),
                )
            )
    known_labels = tuple(label for label in labels if label in boundary_order)
    canonical = tuple(sorted(known_labels, key=boundary_order.__getitem__))
    if known_labels != canonical:
        issues.append(
            CompactValidationIssueV4(
                code=(
                    CompactValidationIssueCodeV4.NON_CANONICAL_SOURCE_LABEL_ORDER
                ),
                json_path=json_path,
                message="source labels 必须按 source_boundary 顺序排列。",
                source_labels=known_labels,
            )
        )


def validate_compact_proposal_replacement_binding_v4(
    source_boundary: tuple[CompactSourceBoundaryEntryV4, ...],
    proposal: CompactCandidateV4,
    replacement: CompactAcceptedReplacementV4,
) -> None:
    """严格验证 durable replacement 等于 proposal/boundary 唯一展开结果。

    :param source_boundary: committed immutable source boundary。
    :param proposal: committed accepted proposal。
    :param replacement: committed accepted replacement。
    :returns: ``None``。
    :raises TypeError: replacement 类型非法时抛出。
    :raises ValueError: retained/new atom 或其余四区任一 binding 漂移时抛出。
    """

    if not isinstance(replacement, CompactAcceptedReplacementV4):
        raise TypeError("replacement must be CompactAcceptedReplacementV4")
    expected = derive_compact_accepted_replacement_v4(source_boundary, proposal)
    if replacement != expected:
        raise ValueError(
            "accepted_replacement must exactly bind accepted_proposal and source_boundary"
        )


@dataclass(frozen=True, slots=True)
class CompactRepresentedSourceV4:
    """单一 source 在业务语义区中的代表关系。

    :param source_label: boundary label。
    :param sections: 去重且按固定 enum 顺序排列的业务区。
    """

    source_label: str
    sections: tuple[CompactSemanticSectionV4, ...]

    def __post_init__(self) -> None:
        """校验 represented source。

        :returns: ``None``。
        :raises TypeError: section 类型非法时抛出。
        :raises ValueError: label、section 顺序或唯一性非法时抛出。
        """

        _require_non_empty(self.source_label, field_name="CompactRepresentedSourceV4.source_label")
        for section in self.sections:
            if not isinstance(section, CompactSemanticSectionV4):
                raise TypeError("CompactRepresentedSourceV4.sections item is invalid")
        if len(self.sections) == 0:
            raise ValueError("CompactRepresentedSourceV4.sections must not be empty")
        expected = tuple(sorted(set(self.sections), key=lambda item: list(CompactSemanticSectionV4).index(item)))
        if self.sections != expected:
            raise ValueError("CompactRepresentedSourceV4.sections must be unique and ordered")

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {"source_label": self.source_label, "sections": [section.value for section in self.sections]}


@dataclass(frozen=True, slots=True)
class CompactRepresentedCoverageV4:
    """Host 从 candidate 派生的 represented coverage。

    :param sources: 按 root boundary 顺序排列的 represented sources。
    """

    sources: tuple[CompactRepresentedSourceV4, ...]

    @property
    def source_labels(self) -> tuple[str, ...]:
        """返回 represented label set 的稳定序列。

        :returns: represented labels。
        """

        return tuple(source.source_label for source in self.sources)

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {"sources": [source.to_json() for source in self.sources]}


@dataclass(frozen=True, slots=True)
class CompactOmittedCoverageV4:
    """Host 从 immutable boundary 派生的 omitted exact complement。

    :param source_labels: 按 root boundary 顺序排列、未被 candidate provenance
        表示的 source labels；不携带任何主观原因。
    """

    source_labels: tuple[str, ...]

    def __post_init__(self) -> None:
        """校验 omitted labels 的顺序内唯一性。

        :returns: ``None``。
        :raises ValueError: label 为空或重复时抛出。
        """

        _require_unique_string_tuple(
            self.source_labels,
            field_name="CompactOmittedCoverageV4.source_labels",
        )

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {"source_labels": _string_list_json(self.source_labels)}


@dataclass(frozen=True, slots=True)
class CompactPolicyUsageAuditV4:
    """Host 从同一 Memory policy 与 estimator 派生的输出用量审计。

    :param policy_ref: Memory policy 引用。
    :param policy_digest: Memory policy canonical digest。
    :param session_summary_char_actual: summary 实际字符用量。
    :param session_summary_char_cap: summary 字符上限。
    :param evidence_fact_item_actual: fact 实际数量。
    :param evidence_fact_item_cap: fact 数量上限。
    :param evidence_fact_char_actual: fact 实际字符用量。
    :param evidence_fact_char_cap: fact 字符上限。
    :param answer_anchor_item_actual: anchor 实际数量。
    :param answer_anchor_item_cap: anchor 数量上限。
    :param answer_anchor_char_actual: anchor 实际字符用量。
    :param answer_anchor_char_cap: anchor 字符上限。
    :param forward_intent_item_actual: intent 实际数量。
    :param forward_intent_item_cap: intent 数量上限。
    :param forward_intent_char_actual: intent 实际字符用量。
    :param forward_intent_char_cap: intent 字符上限。
    :param reference_continuity_item_actual: continuity 实际数量。
    :param reference_continuity_item_cap: continuity 数量上限。
    :param reference_continuity_char_actual: continuity 实际字符用量。
    :param reference_continuity_char_cap: continuity 字符上限。
    """

    policy_ref: str
    policy_digest: str
    session_summary_char_actual: int
    session_summary_char_cap: int
    evidence_fact_item_actual: int
    evidence_fact_item_cap: int
    evidence_fact_char_actual: int
    evidence_fact_char_cap: int
    answer_anchor_item_actual: int
    answer_anchor_item_cap: int
    answer_anchor_char_actual: int
    answer_anchor_char_cap: int
    forward_intent_item_actual: int
    forward_intent_item_cap: int
    forward_intent_char_actual: int
    forward_intent_char_cap: int
    reference_continuity_item_actual: int
    reference_continuity_item_cap: int
    reference_continuity_char_actual: int
    reference_continuity_char_cap: int

    def to_json(self) -> JsonValue:
        """转换为 canonical durable JSON object。

        :returns: policy identity、actual 与 cap 的完整 JSON object。
        """

        return {
            "policy_ref": self.policy_ref,
            "policy_digest": self.policy_digest,
            "session_summary_char_actual": self.session_summary_char_actual,
            "session_summary_char_cap": self.session_summary_char_cap,
            "evidence_fact_item_actual": self.evidence_fact_item_actual,
            "evidence_fact_item_cap": self.evidence_fact_item_cap,
            "evidence_fact_char_actual": self.evidence_fact_char_actual,
            "evidence_fact_char_cap": self.evidence_fact_char_cap,
            "answer_anchor_item_actual": self.answer_anchor_item_actual,
            "answer_anchor_item_cap": self.answer_anchor_item_cap,
            "answer_anchor_char_actual": self.answer_anchor_char_actual,
            "answer_anchor_char_cap": self.answer_anchor_char_cap,
            "forward_intent_item_actual": self.forward_intent_item_actual,
            "forward_intent_item_cap": self.forward_intent_item_cap,
            "forward_intent_char_actual": self.forward_intent_char_actual,
            "forward_intent_char_cap": self.forward_intent_char_cap,
            "reference_continuity_item_actual": self.reference_continuity_item_actual,
            "reference_continuity_item_cap": self.reference_continuity_item_cap,
            "reference_continuity_char_actual": self.reference_continuity_char_actual,
            "reference_continuity_char_cap": self.reference_continuity_char_cap,
        }


@dataclass(frozen=True, slots=True)
class CompactPolicyUsageActualsV4:
    """从 accepted candidate 单一派生的九项 exact actual。

    :param session_summary_char_actual: summary 字符用量。
    :param evidence_fact_item_actual: fact 数量。
    :param evidence_fact_char_actual: fact 字符用量。
    :param answer_anchor_item_actual: anchor 数量。
    :param answer_anchor_char_actual: anchor 字符用量。
    :param forward_intent_item_actual: intent 数量。
    :param forward_intent_char_actual: intent 字符用量。
    :param reference_continuity_item_actual: reference 数量。
    :param reference_continuity_char_actual: reference 字符用量。
    """

    session_summary_char_actual: int
    evidence_fact_item_actual: int
    evidence_fact_char_actual: int
    answer_anchor_item_actual: int
    answer_anchor_char_actual: int
    forward_intent_item_actual: int
    forward_intent_char_actual: int
    reference_continuity_item_actual: int
    reference_continuity_char_actual: int


def compact_text_size_units_v4(text: str) -> int:
    """返回 compact/Memory 共用的字符计量单位。

    :param text: 待计量业务文本。
    :returns: Python 字符数。
    :raises ValueError: ``text`` 不是字符串时抛出。
    """

    if not isinstance(text, str):
        raise ValueError("text must be str")
    return len(text)


def compact_policy_usage_measurement_rules_v4() -> Mapping[str, str]:
    """投影 compact v4 各业务区的字符计量规则。

    :returns: section 名到业务可读 exact measurement 的只读映射。
    """

    return _COMPACT_POLICY_USAGE_MEASUREMENT_RULES_V4


def derive_compact_replacement_policy_usage_actuals_v4(
    replacement: CompactAcceptedReplacementV4,
) -> CompactPolicyUsageActualsV4:
    """从 accepted replacement 派生 combined 五区 policy actuals。

    :param replacement: Host 已展开 retained + new facts 的最终 replacement。
    :returns: item count 与 section 字符用量的 exact typed projection。
    :raises TypeError: ``replacement`` 类型非法时抛出。
    """

    if not isinstance(replacement, CompactAcceptedReplacementV4):
        raise TypeError("replacement must be CompactAcceptedReplacementV4")
    fact_texts = tuple(item.claim for item in replacement.evidence_facts)
    anchor_texts = tuple(
        f"{item.title}\n{item.detail}" for item in replacement.answer_anchors
    )
    intent_texts = tuple(item.text for item in replacement.forward_intents)
    reference_texts = tuple(item.text for item in replacement.reference_continuity)
    return CompactPolicyUsageActualsV4(
        session_summary_char_actual=(
            0
            if replacement.session_summary is None
            else compact_text_size_units_v4(replacement.session_summary.text)
        ),
        evidence_fact_item_actual=len(fact_texts),
        evidence_fact_char_actual=_compact_texts_size_units_v4(fact_texts),
        answer_anchor_item_actual=len(anchor_texts),
        answer_anchor_char_actual=_compact_texts_size_units_v4(anchor_texts),
        forward_intent_item_actual=len(intent_texts),
        forward_intent_char_actual=_compact_texts_size_units_v4(intent_texts),
        reference_continuity_item_actual=len(reference_texts),
        reference_continuity_char_actual=_compact_texts_size_units_v4(
            reference_texts
        ),
    )


def validate_compact_policy_usage_audit_replacement_binding_v4(
    replacement: CompactAcceptedReplacementV4,
    audit: CompactPolicyUsageAuditV4,
) -> None:
    """严格校验 durable audit 与 accepted replacement exact 同源。

    :param replacement: Host accepted replacement。
    :param audit: Host-derived durable policy usage audit。
    :returns: ``None``。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: actual 不等于派生值或 actual 超 cap 时抛出。
    """

    if not isinstance(audit, CompactPolicyUsageAuditV4):
        raise TypeError("audit must be CompactPolicyUsageAuditV4")
    actuals = derive_compact_replacement_policy_usage_actuals_v4(replacement)
    exact_pairs = (
        (audit.session_summary_char_actual, actuals.session_summary_char_actual),
        (audit.evidence_fact_item_actual, actuals.evidence_fact_item_actual),
        (audit.evidence_fact_char_actual, actuals.evidence_fact_char_actual),
        (audit.answer_anchor_item_actual, actuals.answer_anchor_item_actual),
        (audit.answer_anchor_char_actual, actuals.answer_anchor_char_actual),
        (audit.forward_intent_item_actual, actuals.forward_intent_item_actual),
        (audit.forward_intent_char_actual, actuals.forward_intent_char_actual),
        (
            audit.reference_continuity_item_actual,
            actuals.reference_continuity_item_actual,
        ),
        (
            audit.reference_continuity_char_actual,
            actuals.reference_continuity_char_actual,
        ),
    )
    if any(persisted != derived for persisted, derived in exact_pairs):
        raise ValueError(
            "policy_usage_audit actuals must equal replacement-derived usage"
        )
    cap_pairs = (
        (audit.session_summary_char_actual, audit.session_summary_char_cap),
        (audit.evidence_fact_item_actual, audit.evidence_fact_item_cap),
        (audit.evidence_fact_char_actual, audit.evidence_fact_char_cap),
        (audit.answer_anchor_item_actual, audit.answer_anchor_item_cap),
        (audit.answer_anchor_char_actual, audit.answer_anchor_char_cap),
        (audit.forward_intent_item_actual, audit.forward_intent_item_cap),
        (audit.forward_intent_char_actual, audit.forward_intent_char_cap),
        (
            audit.reference_continuity_item_actual,
            audit.reference_continuity_item_cap,
        ),
        (
            audit.reference_continuity_char_actual,
            audit.reference_continuity_char_cap,
        ),
    )
    if any(actual > cap for actual, cap in cap_pairs):
        raise ValueError("policy_usage_audit actual must not exceed cap")


def derive_compact_replacement_represented_sections_v4(
    replacement: CompactAcceptedReplacementV4,
) -> Mapping[str, tuple[CompactSemanticSectionV4, ...]]:
    """从 accepted replacement 单一派生 label 到业务 section 的映射。

    :param replacement: retained + new combined replacement。
    :returns: 按 semantic section 固定顺序规范化的只读映射。
    :raises TypeError: ``replacement`` 类型非法时抛出。
    """

    if not isinstance(replacement, CompactAcceptedReplacementV4):
        raise TypeError("replacement must be CompactAcceptedReplacementV4")
    mutable: dict[str, set[CompactSemanticSectionV4]] = {}
    if replacement.session_summary is not None:
        _add_compact_represented_sections_v4(
            mutable,
            replacement.session_summary.source_labels,
            CompactSemanticSectionV4.SESSION_SUMMARY,
        )
    for item in replacement.evidence_facts:
        _add_compact_represented_sections_v4(
            mutable,
            (*item.selection_labels, *item.context_labels),
            CompactSemanticSectionV4.EVIDENCE_FACTS,
        )
    for item in replacement.answer_anchors:
        _add_compact_represented_sections_v4(
            mutable,
            item.source_labels,
            CompactSemanticSectionV4.ANSWER_ANCHORS,
        )
    for item in replacement.forward_intents:
        _add_compact_represented_sections_v4(
            mutable,
            item.source_labels,
            CompactSemanticSectionV4.FORWARD_INTENTS,
        )
    for item in replacement.reference_continuity:
        _add_compact_represented_sections_v4(
            mutable,
            item.source_labels,
            CompactSemanticSectionV4.REFERENCE_CONTINUITY,
        )
    section_order = tuple(CompactSemanticSectionV4)
    return MappingProxyType(
        {
            label: tuple(
                section for section in section_order if section in label_sections
            )
            for label, label_sections in mutable.items()
        }
    )


def validate_compact_represented_coverage_replacement_binding_v4(
    replacement: CompactAcceptedReplacementV4,
    represented_coverage: CompactRepresentedCoverageV4,
) -> None:
    """校验 durable represented coverage 与 replacement provenance exact 同源。

    :param replacement: accepted replacement。
    :param represented_coverage: Host-derived represented coverage。
    :returns: ``None``。
    :raises TypeError: coverage 类型或 nested item 非法时抛出。
    :raises ValueError: label 重复或 sections 与 replacement 派生值不等时抛出。
    """

    if not isinstance(represented_coverage, CompactRepresentedCoverageV4):
        raise TypeError("represented_coverage must be CompactRepresentedCoverageV4")
    actual: dict[str, tuple[CompactSemanticSectionV4, ...]] = {}
    for source in represented_coverage.sources:
        if not isinstance(source, CompactRepresentedSourceV4):
            raise TypeError("represented_coverage source must be CompactRepresentedSourceV4")
        if source.source_label in actual:
            raise ValueError("represented_coverage source labels must be unique")
        actual[source.source_label] = source.sections
    if actual != derive_compact_replacement_represented_sections_v4(replacement):
        raise ValueError(
            "represented coverage must equal replacement-derived sections"
        )


def _compact_texts_size_units_v4(texts: tuple[str, ...]) -> int:
    """汇总一组 compact 业务文本的共用字符单位。

    :param texts: 待计量业务文本。
    :returns: aggregate 字符单位。
    """

    return sum(compact_text_size_units_v4(text) for text in texts)


def _add_compact_represented_sections_v4(
    sections: dict[str, set[CompactSemanticSectionV4]],
    labels: tuple[str, ...],
    section: CompactSemanticSectionV4,
) -> None:
    """向 candidate represented section accumulator 写入 labels。

    :param sections: label 到 section set 的 accumulator。
    :param labels: candidate provenance labels。
    :param section: 当前业务 section。
    :returns: ``None``。
    """

    for label in labels:
        sections.setdefault(label, set()).add(section)


@dataclass(frozen=True, slots=True)
class CompactValidationIssueV4:
    """严格 parser 或 Host acceptance 的单一确定性问题。

    :param code: 稳定问题码。
    :param json_path: 候选中的自解释 JSON path。
    :param message: 脱敏、自解释的修复提示。
    :param source_labels: 只包含 prompt-local labels。
    """

    code: CompactValidationIssueCodeV4
    json_path: str
    message: str
    source_labels: tuple[str, ...] = field(default_factory=_empty_string_tuple)

    def __post_init__(self) -> None:
        """校验 validation issue。

        :returns: ``None``。
        :raises TypeError: code 类型非法时抛出。
        :raises ValueError: path/message/labels 非法时抛出。
        """

        if not isinstance(self.code, CompactValidationIssueCodeV4):
            raise TypeError("CompactValidationIssueV4.code is invalid")
        _require_non_empty(self.json_path, field_name="CompactValidationIssueV4.json_path")
        _require_non_empty(self.message, field_name="CompactValidationIssueV4.message")
        _require_unique_string_tuple(self.source_labels, field_name="CompactValidationIssueV4.source_labels")

    def to_json(self) -> JsonValue:
        """转换为脱敏 JSON object。

        :returns: JSON object。
        """

        return {
            "code": self.code.value,
            "json_path": self.json_path,
            "message": self.message,
            "source_labels": _string_list_json(self.source_labels),
        }


@dataclass(frozen=True, slots=True)
class CompactValidationReportV4:
    """候选拒绝报告；success 不使用该 bag。

    :param issues: 稳定排序、精确去重且非空的问题。
    """

    issues: tuple[CompactValidationIssueV4, ...]

    def __post_init__(self) -> None:
        """校验 reject report。

        :returns: ``None``。
        :raises TypeError: issue 类型非法时抛出。
        :raises ValueError: issues 为空、重复或顺序不稳定时抛出。
        """

        if len(self.issues) == 0:
            raise ValueError("CompactValidationReportV4.issues must not be empty")
        for issue in self.issues:
            if not isinstance(issue, CompactValidationIssueV4):
                raise TypeError("CompactValidationReportV4.issues item is invalid")
        expected = tuple(sorted(set(self.issues), key=_validation_issue_sort_key))
        if self.issues != expected:
            raise ValueError("CompactValidationReportV4.issues must be unique and ordered")

    def to_json(self) -> JsonValue:
        """转换为 JSON object。

        :returns: JSON object。
        """

        return {"issues": [issue.to_json() for issue in self.issues]}


MAX_COMPACT_REPAIR_ISSUES = 32
"""单次 repair feedback 最多携带的问题数。"""

MAX_COMPACT_REPAIR_ISSUE_MESSAGE_CHARS = 240
"""单条 repair issue message 的字符上限。"""

MAX_COMPACT_REPAIR_FEEDBACK_CHARS = 8192
"""完整 repair feedback 的字符上限。"""

COMPACT_REPAIR_REQUIRED_ACTION = (
    "基于本次请求中的同一输入，重新生成一个符合当前输出 schema 的完整 replacement candidate（一个完整 JSON "
    "object）；必须完整替换前次输出，不是 patch；不得复制、拼接、补写或复用前次输出的任何部分。"
)
"""repair 的固定 whole-candidate 动作要求。"""


@dataclass(frozen=True, slots=True)
class CompactRepairFeedbackV4:
    """Host internal semantic repair 使用的脱敏、bounded feedback。

    :param request_digest: 产生 feedback 的 immutable request digest。
    :param source_boundary_digest: 产生 feedback 的 source boundary digest。
    :param previous_attempt_number: 产生报告的前次 attempt number。
    :param issues: bounded issues。
    :param additional_issue_count: 未携带的剩余问题数。
    :param required_action: 固定 whole-candidate replacement 要求。
    """

    request_digest: str
    source_boundary_digest: str
    previous_attempt_number: int
    issues: tuple[CompactValidationIssueV4, ...]
    additional_issue_count: int
    required_action: str = COMPACT_REPAIR_REQUIRED_ACTION

    def __post_init__(self) -> None:
        """校验 repair feedback。

        :returns: ``None``。
        :raises ValueError: attempt/count/action 或 issue 数量非法时抛出。
        """

        _require_non_empty(
            self.request_digest,
            field_name="CompactRepairFeedbackV4.request_digest",
        )
        _require_non_empty(
            self.source_boundary_digest,
            field_name="CompactRepairFeedbackV4.source_boundary_digest",
        )
        if self.previous_attempt_number <= 0:
            raise ValueError("CompactRepairFeedbackV4.previous_attempt_number must be positive")
        if len(self.issues) == 0 or len(self.issues) > MAX_COMPACT_REPAIR_ISSUES:
            raise ValueError("CompactRepairFeedbackV4.issues count is invalid")
        _require_non_negative_int(
            self.additional_issue_count,
            field_name="CompactRepairFeedbackV4.additional_issue_count",
        )
        if self.required_action != COMPACT_REPAIR_REQUIRED_ACTION:
            raise ValueError("CompactRepairFeedbackV4.required_action is invalid")

    def to_json(self) -> JsonValue:
        """转换为 durable/internal serialization JSON。

        :returns: JSON object。
        """

        return {
            "request_digest": self.request_digest,
            "source_boundary_digest": self.source_boundary_digest,
            "previous_attempt_number": self.previous_attempt_number,
            "issues": [issue.to_json() for issue in self.issues],
            "additional_issue_count": self.additional_issue_count,
            "required_action": self.required_action,
        }


class _CompactAcceptancePermit:
    """限制 accepted truth 只能由 governance owner 构造。"""

    __slots__ = ()


_COMPACT_ACCEPTANCE_PERMIT = _CompactAcceptancePermit()


@dataclass(frozen=True, slots=True)
class CompactAcceptedTruthV4:
    """Host 成功验收后唯一可提交的 compact truth。

    :param proposal: 模型提交并通过 strict parse 的七字段 proposal。
    :param replacement: Host 原子展开并验收的五类最终语义。
    :param source_boundary: immutable root source boundary。
    :param represented_coverage: Host 派生的 represented coverage。
    :param omitted_coverage: Host 从 boundary 与 represented 派生的补集。
    :param policy_usage_audit: Host 从同一 Memory policy 派生的实际用量审计。
    :param current_input_ref: 始终保留的当前输入 ref。
    :param _permit: governance owner 私有构造许可。
    """

    proposal: CompactCandidateV4
    replacement: CompactAcceptedReplacementV4
    source_boundary: tuple[CompactSourceBoundaryEntryV4, ...]
    represented_coverage: CompactRepresentedCoverageV4
    omitted_coverage: CompactOmittedCoverageV4
    policy_usage_audit: CompactPolicyUsageAuditV4
    current_input_ref: str
    _permit: _CompactAcceptancePermit = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        """校验 accepted truth 构造来源与覆盖等式。

        :returns: ``None``。
        :raises ValueError: 私有许可、current input 或覆盖等式非法时抛出。
        """

        if self._permit is not _COMPACT_ACCEPTANCE_PERMIT:
            raise ValueError("CompactAcceptedTruthV4 must be created by Context Governance")
        if not isinstance(self.proposal, CompactCandidateV4):
            raise TypeError("CompactAcceptedTruthV4.proposal is invalid")
        if not isinstance(self.replacement, CompactAcceptedReplacementV4):
            raise TypeError("CompactAcceptedTruthV4.replacement is invalid")
        for entry in self.source_boundary:
            if not isinstance(entry, CompactSourceBoundaryEntryV4):
                raise TypeError("CompactAcceptedTruthV4.source_boundary item is invalid")
        if not isinstance(self.represented_coverage, CompactRepresentedCoverageV4):
            raise TypeError("CompactAcceptedTruthV4.represented_coverage is invalid")
        if not isinstance(self.omitted_coverage, CompactOmittedCoverageV4):
            raise TypeError("CompactAcceptedTruthV4.omitted_coverage is invalid")
        if not isinstance(self.policy_usage_audit, CompactPolicyUsageAuditV4):
            raise TypeError("CompactAcceptedTruthV4.policy_usage_audit is invalid")
        _require_non_empty(self.current_input_ref, field_name="CompactAcceptedTruthV4.current_input_ref")
        boundary_labels = tuple(entry.source_label for entry in self.source_boundary)
        represented = self.represented_coverage.source_labels
        omitted = self.omitted_coverage.source_labels
        if set(represented).intersection(omitted):
            raise ValueError("represented and omitted coverage must be disjoint")
        if set(boundary_labels) != set(represented).union(omitted):
            raise ValueError("accepted coverage must exactly partition source boundary")
        if tuple(label for label in boundary_labels if label in set(represented)) != represented:
            raise ValueError("represented coverage must preserve source boundary order")
        if tuple(label for label in boundary_labels if label in set(omitted)) != omitted:
            raise ValueError("omitted coverage must preserve source boundary order")

    @property
    def covered_source_refs(self) -> tuple[str, ...]:
        """按 boundary 顺序派生 accepted coverage 的 canonical refs。

        :returns: represented 与 omitted partition 对应的唯一 refs。
        """

        refs: list[str] = []
        covered_labels = set(self.represented_coverage.source_labels).union(
            self.omitted_coverage.source_labels
        )
        for entry in self.source_boundary:
            if entry.source_label in covered_labels:
                refs.extend(entry.source_refs)
        return tuple(dict.fromkeys(refs))

    def validate_input_binding(self, compact_input: CompactInputV4) -> None:
        """验证 accepted truth 仍绑定产生它的 immutable input。

        :param compact_input: 待提交 request 派生的 strict v4 input。
        :returns: ``None``。
        :raises TypeError: ``compact_input`` 类型非法时抛出。
        :raises ValueError: current ref 或 source boundary 不同源时抛出。
        """

        if not isinstance(compact_input, CompactInputV4):
            raise TypeError("compact_input must be CompactInputV4")
        if self.current_input_ref != compact_input.current_input.source_ref:
            raise ValueError("accepted truth current input binding mismatch")
        if self.source_boundary != compact_input.source_boundary:
            raise ValueError("accepted truth source boundary binding mismatch")
        audit = self.policy_usage_audit
        caps = compact_input.output_caps
        if (
            audit.session_summary_char_cap != caps.session_summary_char_cap
            or audit.evidence_fact_item_cap != caps.evidence_fact_item_cap
            or audit.evidence_fact_char_cap != caps.evidence_fact_char_cap
            or audit.answer_anchor_item_cap != caps.answer_anchor_item_cap
            or audit.answer_anchor_char_cap != caps.answer_anchor_char_cap
            or audit.forward_intent_item_cap != caps.forward_intent_item_cap
            or audit.forward_intent_char_cap != caps.forward_intent_char_cap
            or audit.reference_continuity_item_cap
            != caps.reference_continuity_item_cap
            or audit.reference_continuity_char_cap
            != caps.reference_continuity_char_cap
        ):
            raise ValueError("accepted truth output caps binding mismatch")


def _validation_issue_sort_key(issue: CompactValidationIssueV4) -> tuple[str, str, tuple[str, ...], str]:
    """返回 validation issue 的稳定排序键。

    :param issue: validation issue。
    :returns: code/path/labels/message 排序键。
    """

    return (issue.code.value, issue.json_path, issue.source_labels, issue.message)


@dataclass(frozen=True, slots=True)
class TurnGroupMembership:
    """一个 Host Run turn group 的完整 material block membership。

    :param turn_group_id: 非空 Host Run id。
    :param member_block_ids: 按 material 稳定顺序排列的非空唯一 block ids。
    """

    turn_group_id: str
    member_block_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """校验 turn-group membership。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: group id、成员为空或成员重复时抛出。
        """

        _require_non_empty(
            self.turn_group_id,
            field_name="TurnGroupMembership.turn_group_id",
        )
        _require_unique_string_tuple(
            self.member_block_ids,
            field_name="TurnGroupMembership.member_block_ids",
        )
        if len(self.member_block_ids) == 0:
            raise ValueError("TurnGroupMembership.member_block_ids must not be empty")

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: turn-group membership JSON object。
        """

        return {
            "turn_group_id": self.turn_group_id,
            "member_block_ids": _string_list_json(self.member_block_ids),
        }


@dataclass(frozen=True, slots=True)
class SelectedBlockProvenance:
    """一个 selected source block 到最终 pack 内容的内部同源证明。

    :param block_id: selection 内部 block identity。
    :param canonical_source_refs: source block 直接提供的非空唯一 canonical refs。
    :param packed_content_digest: 最终 compact material pack 业务内容 digest。
    """

    block_id: str
    canonical_source_refs: tuple[str, ...]
    packed_content_digest: str

    def __post_init__(self) -> None:
        """校验 selected block provenance。

        :returns: ``None``。
        :raises TypeError: refs 类型非法时抛出。
        :raises ValueError: id、refs 或 digest 为空或 refs 重复时抛出。
        """

        _require_non_empty(
            self.block_id,
            field_name="SelectedBlockProvenance.block_id",
        )
        _require_non_empty_unique_string_tuple(
            self.canonical_source_refs,
            field_name="SelectedBlockProvenance.canonical_source_refs",
        )
        _require_non_empty(
            self.packed_content_digest,
            field_name="SelectedBlockProvenance.packed_content_digest",
        )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: selected block provenance JSON object。
        """

        return {
            "block_id": self.block_id,
            "canonical_source_refs": _string_list_json(self.canonical_source_refs),
            "packed_content_digest": self.packed_content_digest,
        }


@dataclass(frozen=True, slots=True)
class CompactSegmentSelection:
    """Compaction selected segment 摘要。

    :param scope: root 或 operation-private transient scope。
    :param turn_group_memberships: root material 中完整、稳定排序的 turn groups。
    :param selected_block_provenance: 与 selected block ids 同序一一对应的内部证明。
    :param root_selection_digest: transient selection 绑定的 immutable root digest。
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

    scope: CompactSegmentSelectionScope
    turn_group_memberships: tuple[TurnGroupMembership, ...]
    selected_block_provenance: tuple[SelectedBlockProvenance, ...]
    root_selection_digest: str | None
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

        if not isinstance(self.scope, CompactSegmentSelectionScope):
            raise TypeError("CompactSegmentSelection.scope is invalid")
        if not isinstance(self.turn_group_memberships, tuple):
            raise TypeError("CompactSegmentSelection.turn_group_memberships must be tuple")
        group_ids: list[str] = []
        member_ids: list[str] = []
        for membership in self.turn_group_memberships:
            if not isinstance(membership, TurnGroupMembership):
                raise TypeError("CompactSegmentSelection.turn_group_memberships item is invalid")
            group_ids.append(membership.turn_group_id)
            member_ids.extend(membership.member_block_ids)
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("CompactSegmentSelection turn_group_id values must be unique")
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("CompactSegmentSelection member block ids must be globally unique")
        if not isinstance(self.selected_block_provenance, tuple):
            raise TypeError("CompactSegmentSelection.selected_block_provenance must be tuple")
        provenance_ids: list[str] = []
        for provenance in self.selected_block_provenance:
            if not isinstance(provenance, SelectedBlockProvenance):
                raise TypeError("CompactSegmentSelection.selected_block_provenance item is invalid")
            provenance_ids.append(provenance.block_id)
        if self.scope is CompactSegmentSelectionScope.ROOT:
            if self.root_selection_digest is not None:
                raise ValueError("root selection must not bind another root selection")
        else:
            if self.root_selection_digest is None:
                raise ValueError("transient selection must bind root selection digest")
            _require_non_empty(
                self.root_selection_digest,
                field_name="CompactSegmentSelection.root_selection_digest",
            )
        _require_unique_string_tuple(
            self.selected_block_ids,
            field_name="CompactSegmentSelection.selected_block_ids",
        )
        if tuple(provenance_ids) != self.selected_block_ids:
            raise ValueError("selected block provenance must exactly match selected block ids")
        _require_unique_string_tuple(
            self.excluded_protected_ids,
            field_name="CompactSegmentSelection.excluded_protected_ids",
        )
        if not isinstance(self.trigger_source, CompactSegmentTrigger):
            raise TypeError("CompactSegmentSelection.trigger_source is invalid")
        _require_non_negative_int(self.input_cursor, field_name="CompactSegmentSelection.input_cursor")
        if self.memory_snapshot_cursor is not None:
            _require_non_negative_int(
                self.memory_snapshot_cursor,
                field_name="CompactSegmentSelection.memory_snapshot_cursor",
            )
        _require_non_empty(self.policy_digest, field_name="CompactSegmentSelection.policy_digest")
        _require_string_tuple(
            self.deterministic_reason_codes,
            field_name="CompactSegmentSelection.deterministic_reason_codes",
        )
        _require_string_mapping(
            self.excluded_reason_codes,
            field_name="CompactSegmentSelection.excluded_reason_codes",
        )
        sorted_excluded_reasons = {
            block_id: self.excluded_reason_codes[block_id]
            for block_id in sorted(self.excluded_reason_codes)
        }
        object.__setattr__(
            self,
            "excluded_reason_codes",
            MappingProxyType(sorted_excluded_reasons),
        )
        selected = set(self.selected_block_ids)
        excluded = set(self.excluded_reason_codes)
        if selected.intersection(excluded):
            raise ValueError("selected and excluded block ids must be disjoint")
        if not set(self.excluded_protected_ids).issubset(excluded):
            raise ValueError("excluded protected ids must be excluded")
        if self.scope is CompactSegmentSelectionScope.ROOT:
            for membership in self.turn_group_memberships:
                members = set(membership.member_block_ids)
                if not (members.issubset(selected) or members.issubset(excluded)):
                    raise ValueError("root turn group must be wholly selected or wholly excluded")
        _require_non_empty(
            self.selection_digest,
            field_name="CompactSegmentSelection.selection_digest",
        )

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "scope": self.scope.value,
            "turn_group_memberships": [membership.to_json() for membership in self.turn_group_memberships],
            "selected_block_provenance": [
                provenance.to_json() for provenance in self.selected_block_provenance
            ],
            "root_selection_digest": self.root_selection_digest,
            "selected_block_ids": _string_list_json(self.selected_block_ids),
            "excluded_protected_ids": _string_list_json(self.excluded_protected_ids),
            "trigger_source": self.trigger_source.value,
            "input_cursor": self.input_cursor,
            "memory_snapshot_cursor": self.memory_snapshot_cursor,
            "policy_digest": self.policy_digest,
            "deterministic_reason_codes": _string_list_json(self.deterministic_reason_codes),
            "excluded_reason_codes": _string_mapping_json(self.excluded_reason_codes),
            "selection_digest": self.selection_digest,
        }


@dataclass(frozen=True, slots=True)
class CompactMaterialPack:
    """Compactor LLM-facing material pack 与内部 provenance map。

    :param previous_compacted_view: previous compacted view blocks。
    :param previous_compacted_readable_view: 与 previous blocks 同源的 typed previous view。
    :param trace_material: trace material blocks。
    :param evidence_material: evidence material blocks。
    :param answer_material: answer material blocks。
    :param current_input_anchor: 当前输入 anchor。
    :param provenance_map: prompt-local label 到 canonical provenance 的完整映射。
    """

    previous_compacted_view: tuple[CompactMaterialBlock, ...]
    previous_compacted_readable_view: PreviousCompactReadableView | None
    trace_material: tuple[CompactMaterialBlock, ...]
    evidence_material: tuple[CompactEvidenceBlock, ...]
    answer_material: tuple[CompactMaterialBlock, ...]
    current_input_anchor: CurrentInputAnchor
    provenance_map: Mapping[PromptLocalMaterialLabel, PromptLocalProvenanceEntry]

    def __post_init__(self) -> None:
        """校验 material pack 与 one-section guard。

        :returns: ``None``。
        :raises TypeError: 字段类型非法时抛出。
        :raises ValueError: 字段值非法时抛出。
        """

        _require_material_block_tuple(
            self.previous_compacted_view,
            field_name="CompactMaterialPack.previous_compacted_view",
            section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
        )
        _require_previous_compacted_view_pair(
            self.previous_compacted_view,
            self.previous_compacted_readable_view,
        )
        _require_material_block_tuple(
            self.trace_material,
            field_name="CompactMaterialPack.trace_material",
            section=CompactMaterialSection.TRACE_MATERIAL,
        )
        _require_evidence_block_tuple(
            self.evidence_material,
            field_name="CompactMaterialPack.evidence_material",
        )
        _require_material_block_tuple(
            self.answer_material,
            field_name="CompactMaterialPack.answer_material",
            section=CompactMaterialSection.ANSWER_MATERIAL,
        )
        if not isinstance(self.current_input_anchor, CurrentInputAnchor):
            raise TypeError("CompactMaterialPack.current_input_anchor must be CurrentInputAnchor")
        _require_provenance_mapping(self.provenance_map)
        _require_one_section_per_canonical_content(self)

    @property
    def all_labels(self) -> tuple[PromptLocalMaterialLabel, ...]:
        """返回 material pack 中所有 prompt-local labels。

        :returns: label tuple。
        """

        labels: list[PromptLocalMaterialLabel] = []
        labels.extend(block.block_label for block in self.previous_compacted_view)
        labels.extend(block.block_label for block in self.trace_material)
        labels.extend(block.block_label for block in self.evidence_material)
        labels.extend(block.block_label for block in self.answer_material)
        labels.append(self.current_input_anchor.anchor_label)
        return tuple(labels)

    @property
    def evidence_labels(self) -> tuple[PromptLocalMaterialLabel, ...]:
        """返回 evidence material labels。

        :returns: evidence label tuple。
        """

        return tuple(block.evidence_label for block in self.evidence_material)

    @property
    def material_source_refs(self) -> tuple[str, ...]:
        """返回 material pack 覆盖的 canonical source refs。

        :returns: 去重后的 canonical source refs。
        """

        refs: list[str] = []
        ordered_labels = (
            self.current_input_anchor.anchor_label,
            *[block.block_label for block in self.trace_material],
            *[block.block_label for block in self.previous_compacted_view],
            *[block.block_label for block in self.evidence_material],
            *[block.block_label for block in self.answer_material],
        )
        for label in ordered_labels:
            entry = self.provenance_map[label]
            refs.extend(entry.canonical_source_refs)
        return tuple(dict.fromkeys(refs))

    @property
    def canonical_evidence_refs(self) -> tuple[str, ...]:
        """返回所有可选 evidence boundary entries 的有序唯一 refs。

        :returns: current evidence 与 previous fact provenance 的有序并集。
        """

        ordered_labels = (
            *[block.block_label for block in self.previous_compacted_view],
            *[block.evidence_label for block in self.evidence_material],
        )
        return tuple(
            dict.fromkeys(
                ref
                for label in ordered_labels
                for ref in self.provenance_map[label].canonical_evidence_refs
            )
        )

    def evidence_map(self) -> PromptLocalEvidenceMap:
        """返回 evidence-only prompt-local provenance view。

        :returns: evidence label 到 provenance entry 的只读 mapping。
        """

        return {label: self.provenance_map[label] for label in self.evidence_labels}

    def to_json(self) -> JsonValue:
        """转换为 canonical JSON 兼容值。

        :returns: JSON object。
        """

        return {
            "previous_compacted_view": _material_block_list_json(self.previous_compacted_view),
            "previous_compacted_readable_view": (
                None
                if self.previous_compacted_readable_view is None
                else self.previous_compacted_readable_view.to_json()
            ),
            "trace_material": _material_block_list_json(self.trace_material),
            "evidence_material": _evidence_block_list_json(self.evidence_material),
            "answer_material": _material_block_list_json(self.answer_material),
            "current_input_anchor": self.current_input_anchor.to_json(),
            "provenance_map": _provenance_map_json(self.provenance_map),
        }

    def llm_json(self) -> JsonValue:
        """转换为 LLM-facing material JSON。

        :returns: 不含 Host provenance key 的 JSON object。
        """

        return {
            "previous_compacted_view": _material_block_llm_list_json(self.previous_compacted_view),
            "trace_material": _material_block_llm_list_json(self.trace_material),
            "evidence_material": _evidence_block_llm_list_json(self.evidence_material),
            "answer_material": _material_block_llm_list_json(self.answer_material),
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
    :param output_caps: 同一 Memory policy 的 immutable v4 caps 投影。
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
    output_caps: CompactOutputCapsV4
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
        _require_optional_non_empty(self.attempt_id, field_name="CompactionRequest.attempt_id")
        _require_optional_non_empty(self.execution_id, field_name="CompactionRequest.execution_id")
        if self.trigger_source is ContextCompactionTriggerSource.REACTIVE:
            if self.attempt_id is None:
                raise ValueError("CompactionRequest.attempt_id is required for reactive compaction")
            if self.execution_id is None:
                raise ValueError("CompactionRequest.execution_id is required for reactive compaction")
        if self.memory_snapshot_cursor is not None:
            _require_non_negative_int(
                self.memory_snapshot_cursor,
                field_name="CompactionRequest.memory_snapshot_cursor",
            )
        if not isinstance(self.output_caps, CompactOutputCapsV4):
            raise TypeError("CompactionRequest.output_caps must be CompactOutputCapsV4")
        if not isinstance(self.material_pack, CompactMaterialPack):
            raise TypeError("CompactionRequest.material_pack must be CompactMaterialPack")
        if not isinstance(self.segment_selection, CompactSegmentSelection):
            raise TypeError("CompactionRequest.segment_selection must be CompactSegmentSelection")
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
            raise TypeError("CompactionRequest.budget_before_compact must be BudgetEstimate")

    def digest(self) -> str:
        """计算 compaction request digest。

        :returns: 请求 canonical JSON 的 sha256 digest。
        """

        return sha256_digest_json(self.to_json())

    def source_boundary_digest(self) -> str:
        """计算 immutable source boundary digest。

        :returns: strict v4 source boundary canonical JSON 的 sha256 digest。
        """

        return sha256_digest_json(
            [
                entry.to_internal_json()
                for entry in self.compact_input.source_boundary
            ]
        )

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
            "output_caps": self.output_caps.to_json(),
            "material_pack": self.material_pack.to_json(),
            "segment_selection": self.segment_selection.to_json(),
            "canonical_evidence_refs": _string_list_json(self.canonical_evidence_refs),
            "evidence_backed_fact_refs": _string_list_json(self.evidence_backed_fact_refs),
            "recent_raw_turn_refs": _string_list_json(self.recent_raw_turn_refs),
            "older_raw_turn_refs": _string_list_json(self.older_raw_turn_refs),
            "existing_episode_summary_refs": _string_list_json(self.existing_episode_summary_refs),
            "budget_before_compact": _budget_estimate_json(self.budget_before_compact),
        }

    def llm_material_json(self) -> JsonValue:
        """返回严格 v4 LLM-facing 输入。

        :returns: 不含 canonical refs / digest / cursor 的 v4 input JSON。
        """

        return self.compact_input.to_json()

    @property
    def compact_input(self) -> CompactInputV4:
        """从冻结 material pack 机械投影严格 v4 input。

        :returns: current input 与逐项 source boundary。
        """

        entries: list[CompactSourceBoundaryEntryV4] = []
        for block in self.material_pack.previous_compacted_view:
            provenance = self.material_pack.provenance_map[block.block_label]
            entries.append(
                CompactSourceBoundaryEntryV4(
                    source_label=block.block_label,
                    source_kind=_previous_source_kind(block.kind),
                    source_refs=block.canonical_source_refs,
                    canonical_evidence_refs=provenance.canonical_evidence_refs,
                    readable_text=block.text,
                )
            )
        for block in self.material_pack.trace_material:
            entries.append(
                CompactSourceBoundaryEntryV4(
                    source_label=block.block_label,
                    source_kind=CompactSourceKindV4.TRACE_MATERIAL,
                    source_refs=block.canonical_source_refs,
                    canonical_evidence_refs=(),
                    readable_text=block.text,
                )
            )
        for block in self.material_pack.evidence_material:
            provenance = self.material_pack.provenance_map[block.evidence_label]
            entries.append(
                CompactSourceBoundaryEntryV4(
                    source_label=block.evidence_label,
                    source_kind=CompactSourceKindV4.EVIDENCE_MATERIAL,
                    source_refs=block.canonical_source_refs,
                    canonical_evidence_refs=provenance.canonical_evidence_refs,
                    readable_text=_evidence_boundary_text(block),
                )
            )
        for block in self.material_pack.answer_material:
            entries.append(
                CompactSourceBoundaryEntryV4(
                    source_label=block.block_label,
                    source_kind=CompactSourceKindV4.ANSWER_MATERIAL,
                    source_refs=block.canonical_source_refs,
                    canonical_evidence_refs=(),
                    readable_text=block.text,
                )
            )
        return CompactInputV4(
            schema=COMPACT_INPUT_SCHEMA_V4,
            current_input=CompactCurrentInputV4(
                source_ref=self.current_input_ref,
                readable_text=self.current_input_text,
            ),
            source_boundary=tuple(entries),
            output_caps=self.output_caps,
        )

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


def _previous_source_kind(kind: CompactMaterialBlockKind) -> CompactSourceKindV4:
    """把 previous compact block kind 映射到唯一 v4 source kind。

    :param kind: previous material block kind。
    :returns: 对应 previous-* source kind。
    :raises ValueError: kind 不属于 previous semantic sections 时抛出。
    """

    mapping = {
        CompactMaterialBlockKind.SESSION_SUMMARY: CompactSourceKindV4.PREVIOUS_SESSION_SUMMARY,
        CompactMaterialBlockKind.EVIDENCE_BACKED_FACT: CompactSourceKindV4.PREVIOUS_EVIDENCE_FACT,
        CompactMaterialBlockKind.ANSWER_ANCHOR: CompactSourceKindV4.PREVIOUS_ANSWER_ANCHOR,
        CompactMaterialBlockKind.FORWARD_INTENT: CompactSourceKindV4.PREVIOUS_FORWARD_INTENT,
        CompactMaterialBlockKind.REFERENCE_CONTINUITY: CompactSourceKindV4.PREVIOUS_REFERENCE_CONTINUITY,
    }
    try:
        return mapping[kind]
    except KeyError as exc:
        raise ValueError("previous compact material block kind is invalid") from exc


def _evidence_boundary_text(block: CompactEvidenceBlock) -> str:
    """构造自解释 evidence boundary 文本。

    :param block: 已校验 evidence material block。
    :returns: 不含内部 provenance 的业务可读文本。
    """

    return (
        f"工具：{block.readable_tool_name}\n"
        f"查询：{block.readable_query_text}\n"
        f"结果：{block.raw_result_text}\n"
        f"来源：{block.readable_source_text}"
    )


@dataclass(frozen=True, slots=True)
class CompactorProposal:
    """一次成功 compactor Runner call 产生的配对 proposal。

    :param candidate: 当前成功响应解析出的 compact candidate。
    :param successful_response_identity: 产生该 candidate 的实际成功 Runner
        call 身份。
    """

    candidate: CompactCandidateV4
    successful_response_identity: SuccessfulRunnerResponseIdentity

    def __post_init__(self) -> None:
        """校验 proposal 的强类型配对值。

        :returns: 无返回值。
        :raises TypeError: candidate 或成功响应身份类型非法时抛出。
        """

        if not isinstance(self.candidate, CompactCandidateV4):
            raise TypeError("CompactorProposal.candidate must be CompactCandidateV4")
        if not isinstance(
            self.successful_response_identity,
            SuccessfulRunnerResponseIdentity,
        ):
            raise TypeError("CompactorProposal.successful_response_identity must be SuccessfulRunnerResponseIdentity")


class CompactorProposalError(RuntimeError):
    """一次 compactor proposal 失败的 typed error contract。

    :param message: 中性且安全的失败描述。
    :param successful_response_identity: 已取得成功 Engine final 时的同源
        response identity；没有成功 final 时为 ``None``。
    :param validation_report: raw LLM contract reject 的 typed report；ordinary
        execution/transport failure 时为 ``None``。
    """

    def __init__(
        self,
        message: str,
        *,
        successful_response_identity: SuccessfulRunnerResponseIdentity | None,
        validation_report: CompactValidationReportV4 | None = None,
    ) -> None:
        """初始化 proposal error。

        :param message: 中性且安全的失败描述。
        :param successful_response_identity: 已取得成功 Engine final 时的同源
            response identity；没有成功 final 时为 ``None``。
        :param validation_report: strict parser validation report。
        :returns: 无返回值。
        :raises Exception: 不主动抛出异常。
        """

        super().__init__(message)
        self.successful_response_identity = successful_response_identity
        self.validation_report = validation_report


class ContextCompactor(Protocol):
    """vNext context compactor typed port。

    真实实现可以是 LLM scene adapter；Host operation 只能接受 vNext compact
    output，并且必须由 vNext quality checker 通过后才可写 compact artifact /
    canonical event。
    """

    async def compact(
        self,
        request: CompactionRequest,
        cancellation_token: CancellationToken,
        *,
        repair_feedback: CompactRepairFeedbackV4 | None,
    ) -> CompactorProposal:
        """生成 vNext compaction output candidate。

        :param request: Host 构造的 compaction 请求。
        :param cancellation_token: Host 注入的真实取消 token。
        :param repair_feedback: 前次 semantic validation 的脱敏反馈；首次为 ``None``。
        :returns: 与实际成功 Runner call 身份配对的 vNext proposal。
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


def _require_string_mapping(value: Mapping[str, str], *, field_name: str) -> None:
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


def _require_unique_string_tuple(value: tuple[str, ...], *, field_name: str) -> None:
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


def _require_non_empty_unique_string_tuple(
    value: tuple[str, ...],
    *,
    field_name: str,
) -> None:
    """校验字符串 tuple 非空且元素不重复。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    :raises ValueError: 元素为空、重复或 tuple 为空时抛出。
    """

    _require_unique_string_tuple(value, field_name=field_name)
    if len(value) == 0:
        raise ValueError(f"{field_name} must be non-empty")


def _require_json_mapping(value: Mapping[str, JsonValue], *, field_name: str) -> None:
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


def _require_evidence_block_tuple(value: tuple[CompactEvidenceBlock, ...], *, field_name: str) -> None:
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
            raise TypeError("CompactMaterialPack.provenance_map values must be PromptLocalProvenanceEntry")
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
        if entry.section is CompactMaterialSection.CURRENT_INPUT_ANCHOR:
            continue
        key = (tuple(sorted(entry.canonical_source_refs)), entry.content_digest)
        existing_section = seen.get(key)
        if existing_section is None:
            seen[key] = entry.section
            continue
        if existing_section is not entry.section:
            raise ValueError("material pack canonical content appears in two sections")


_PREVIOUS_VIEW_ALLOWED_KINDS = frozenset(
    (
        CompactMaterialBlockKind.SESSION_SUMMARY,
        CompactMaterialBlockKind.EVIDENCE_BACKED_FACT,
        CompactMaterialBlockKind.ANSWER_ANCHOR,
        CompactMaterialBlockKind.FORWARD_INTENT,
        CompactMaterialBlockKind.REFERENCE_CONTINUITY,
    )
)
_ANCHOR_CHILD_TEXT_PREFIX = "- "
_ANCHOR_CHILD_ORDINAL_SEPARATOR = ". "


def previous_answer_anchor_block_text(anchor: ReadableAnswerAnchorVNext) -> str:
    """返回 previous answer anchor block 的业务可读文本。

    :param anchor: typed previous answer anchor。
    :returns: 与 typed anchor 同源的 block 文本。
    """

    if not isinstance(anchor, ReadableAnswerAnchorVNext):
        raise TypeError("anchor must be ReadableAnswerAnchorVNext")
    lines = [anchor.anchor_title]
    for item in anchor.anchor_items:
        ordinal_prefix = "" if item.ordinal is None else f"{item.ordinal}{_ANCHOR_CHILD_ORDINAL_SEPARATOR}"
        lines.append(f"{_ANCHOR_CHILD_TEXT_PREFIX}{ordinal_prefix}{item.display_text}")
    return "\n".join(lines)


def validate_previous_compacted_view_pair(
    blocks: tuple[CompactMaterialBlock, ...],
    readable_view: PreviousCompactReadableView | None,
) -> None:
    """校验 previous compacted blocks 与 typed readable view 的 exact pair。

    :param blocks: previous compacted material blocks。
    :param readable_view: 同源 typed readable view。
    :returns: ``None``。
    :raises TypeError: block 或 readable view 类型非法时抛出。
    :raises ValueError: pair invariant 不成立时抛出。
    """

    _require_material_block_tuple(
        blocks,
        field_name="previous_compacted_view",
        section=CompactMaterialSection.PREVIOUS_COMPACTED_VIEW,
    )
    _require_previous_compacted_view_pair(blocks, readable_view)


def _require_previous_compacted_view_pair(
    blocks: tuple[CompactMaterialBlock, ...],
    readable_view: PreviousCompactReadableView | None,
) -> None:
    """校验 previous compacted blocks 与 typed readable view 的 exact pair。

    :param blocks: previous compacted material blocks。
    :param readable_view: 同源 typed readable view。
    :returns: ``None``。
    :raises TypeError: readable view 类型非法时抛出。
    :raises ValueError: presence、kind、label、数量或文本不一致时抛出。
    """

    if len(blocks) == 0:
        if readable_view is not None:
            raise ValueError("previous compacted readable view must be None without blocks")
        return
    if readable_view is None:
        raise ValueError("previous compacted readable view is required with blocks")
    if not isinstance(readable_view, PreviousCompactReadableView):
        raise TypeError("previous compacted readable view must be PreviousCompactReadableView")
    _require_previous_block_kind_and_label_set(blocks)
    summary_blocks = _previous_blocks_by_kind(
        blocks,
        CompactMaterialBlockKind.SESSION_SUMMARY,
    )
    if len(summary_blocks) > 1:
        raise ValueError("previous compacted view may contain one session summary")
    if readable_view.session_summary is None:
        if len(summary_blocks) != 0:
            raise ValueError("previous session summary block mismatch")
    elif len(summary_blocks) != 1 or summary_blocks[0].text != readable_view.session_summary:
        raise ValueError("previous session summary block mismatch")
    _require_previous_item_blocks(
        _previous_blocks_by_kind(blocks, CompactMaterialBlockKind.EVIDENCE_BACKED_FACT),
        tuple((item.source_label, item.claim_text) for item in readable_view.evidence_backed_facts),
        section_name="evidence_backed_facts",
    )
    _require_previous_item_blocks(
        _previous_blocks_by_kind(blocks, CompactMaterialBlockKind.ANSWER_ANCHOR),
        tuple((item.source_label, previous_answer_anchor_block_text(item)) for item in readable_view.answer_anchors),
        section_name="answer_anchors",
    )
    _require_previous_item_blocks(
        _previous_blocks_by_kind(blocks, CompactMaterialBlockKind.FORWARD_INTENT),
        tuple((item.source_label, item.text) for item in readable_view.forward_intents),
        section_name="forward_intents",
    )
    _require_previous_item_blocks(
        _previous_blocks_by_kind(blocks, CompactMaterialBlockKind.REFERENCE_CONTINUITY),
        tuple((item.source_label, item.text) for item in readable_view.reference_continuity_items),
        section_name="reference_continuity_items",
    )


def _require_previous_block_kind_and_label_set(
    blocks: tuple[CompactMaterialBlock, ...],
) -> None:
    """校验 previous blocks 的 kind 与 label 集合。

    :param blocks: previous compacted material blocks。
    :returns: ``None``。
    :raises ValueError: kind 非法或 label 重复时抛出。
    """

    labels: set[PromptLocalMaterialLabel] = set()
    for block in blocks:
        if block.kind not in _PREVIOUS_VIEW_ALLOWED_KINDS:
            raise ValueError("previous compacted view block kind is invalid")
        if block.block_label in labels:
            raise ValueError("previous compacted view block labels must be unique")
        labels.add(block.block_label)


def _previous_blocks_by_kind(
    blocks: tuple[CompactMaterialBlock, ...],
    kind: CompactMaterialBlockKind,
) -> tuple[CompactMaterialBlock, ...]:
    """按 kind 返回 previous blocks。

    :param blocks: previous compacted material blocks。
    :param kind: 目标 block kind。
    :returns: 同 kind block tuple。
    """

    return tuple(block for block in blocks if block.kind is kind)


def _require_previous_item_blocks(
    blocks: tuple[CompactMaterialBlock, ...],
    expected_items: tuple[tuple[PromptLocalMaterialLabel, str], ...],
    *,
    section_name: str,
) -> None:
    """校验 previous section 的 label 与文本逐项一致。

    :param blocks: 同 kind previous blocks。
    :param expected_items: typed view 中同 section 的 label / text tuple。
    :param section_name: 错误消息中的 section 名称。
    :returns: ``None``。
    :raises ValueError: 数量、label 或文本不一致时抛出。
    """

    if len(blocks) != len(expected_items):
        raise ValueError(f"previous {section_name} block count mismatch")
    for block, expected in zip(blocks, expected_items, strict=True):
        label, text = expected
        if block.block_label != label:
            raise ValueError(f"previous {section_name} block label mismatch")
        if block.text != text:
            raise ValueError(f"previous {section_name} block text mismatch")


def _require_opaque_ref_tuple(value: tuple[OpaqueEvidenceRef, ...], *, field_name: str) -> None:
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


def _require_range_tuple(value: tuple[CompactInputRange, ...], *, field_name: str) -> None:
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


def _require_quality_issue_vnext_tuple(value: tuple[CompactValidationIssueCodeV4, ...], *, field_name: str) -> None:
    """校验 vNext quality issue tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, CompactValidationIssueCodeV4):
            raise TypeError(f"{field_name} items must be CompactValidationIssueCodeV4")


def _require_readable_fact_tuple(value: tuple[ReadableFactItemVNext, ...], *, field_name: str) -> None:
    """校验 vNext readable fact tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, ReadableFactItemVNext):
            raise TypeError(f"{field_name} items must be ReadableFactItemVNext")


def _require_readable_answer_anchor_tuple(value: tuple[ReadableAnswerAnchorVNext, ...], *, field_name: str) -> None:
    """校验 vNext readable answer anchor tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, ReadableAnswerAnchorVNext):
            raise TypeError(f"{field_name} items must be ReadableAnswerAnchorVNext")


def _require_readable_answer_anchor_item_tuple(
    value: tuple[ReadableAnswerAnchorItemVNext, ...],
    *,
    field_name: str,
    require_non_empty: bool,
) -> None:
    """校验 vNext readable answer anchor item tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :param require_non_empty: 是否要求非空。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    :raises ValueError: 要求非空但为空时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    if require_non_empty and len(value) == 0:
        raise ValueError(f"{field_name} must be non-empty")
    for item in value:
        if not isinstance(item, ReadableAnswerAnchorItemVNext):
            raise TypeError(f"{field_name} items must be ReadableAnswerAnchorItemVNext")


def _require_readable_forward_intent_tuple(value: tuple[ReadableForwardIntentVNext, ...], *, field_name: str) -> None:
    """校验 vNext readable forward intent tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, ReadableForwardIntentVNext):
            raise TypeError(f"{field_name} items must be ReadableForwardIntentVNext")


def _require_readable_reference_tuple(
    value: tuple[ReadableReferenceContinuityItemVNext, ...], *, field_name: str
) -> None:
    """校验 vNext readable reference continuity tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, ReadableReferenceContinuityItemVNext):
            raise TypeError(f"{field_name} items must be ReadableReferenceContinuityItemVNext")


def _require_trace_readable_tuple(value: tuple[TraceReadableItemVNext, ...], *, field_name: str) -> None:
    """校验 vNext trace readable tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, TraceReadableItemVNext):
            raise TypeError(f"{field_name} items must be TraceReadableItemVNext")


def _require_evidence_readable_tuple(value: tuple[EvidenceReadableItemVNext, ...], *, field_name: str) -> None:
    """校验 vNext evidence readable tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, EvidenceReadableItemVNext):
            raise TypeError(f"{field_name} items must be EvidenceReadableItemVNext")


def _require_answer_readable_tuple(value: tuple[AnswerReadableItemVNext, ...], *, field_name: str) -> None:
    """校验 vNext answer readable tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, AnswerReadableItemVNext):
            raise TypeError(f"{field_name} items must be AnswerReadableItemVNext")


def _require_fact_candidate_vnext_tuple(value: tuple[CompactEvidenceFactV4, ...]) -> None:
    """校验 vNext fact candidate tuple。

    :param value: 待校验 tuple。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError("CompactCandidateV4.evidence_facts must be tuple")
    for item in value:
        if not isinstance(item, CompactEvidenceFactV4):
            raise TypeError("CompactCandidateV4.evidence_facts items are invalid")


def _require_accepted_fact_tuple(
    value: tuple[CompactAcceptedEvidenceFactV4, ...],
) -> None:
    """校验 accepted evidence fact tuple。

    :param value: 待校验 tuple。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(
            "CompactAcceptedReplacementV4.evidence_facts must be tuple"
        )
    for item in value:
        if not isinstance(item, CompactAcceptedEvidenceFactV4):
            raise TypeError(
                "CompactAcceptedReplacementV4.evidence_facts items are invalid"
            )


def _require_answer_anchor_candidate_tuple(value: tuple[CompactAnswerAnchorV4, ...]) -> None:
    """校验 vNext answer anchor candidate tuple。

    :param value: 待校验 tuple。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError("CompactCandidateV4.answer_anchors must be tuple")
    for item in value:
        if not isinstance(item, CompactAnswerAnchorV4):
            raise TypeError("CompactCandidateV4.answer_anchors items are invalid")


def _require_forward_intent_candidate_tuple(value: tuple[CompactForwardIntentV4, ...]) -> None:
    """校验 vNext forward intent candidate tuple。

    :param value: 待校验 tuple。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError("CompactCandidateV4.forward_intents must be tuple")
    for item in value:
        if not isinstance(item, CompactForwardIntentV4):
            raise TypeError("CompactCandidateV4.forward_intents items are invalid")


def _require_reference_candidate_tuple(value: tuple[CompactReferenceContinuityV4, ...]) -> None:
    """校验 vNext reference continuity candidate tuple。

    :param value: 待校验 tuple。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型非法时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError("CompactCandidateV4.reference_continuity must be tuple")
    for item in value:
        if not isinstance(item, CompactReferenceContinuityV4):
            raise TypeError("CompactCandidateV4.reference_continuity items are invalid")


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


def _material_block_list_json(values: tuple[CompactMaterialBlock, ...]) -> list[JsonValue]:
    """把 material block tuple 转换为 JSON 数组。

    :param values: material block tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _material_block_llm_list_json(values: tuple[CompactMaterialBlock, ...]) -> list[JsonValue]:
    """把 material block tuple 转换为 LLM-facing JSON 数组。

    :param values: material block tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.llm_json())
    return result


def _evidence_block_list_json(values: tuple[CompactEvidenceBlock, ...]) -> list[JsonValue]:
    """把 evidence material block tuple 转换为 JSON 数组。

    :param values: evidence block tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _evidence_block_llm_list_json(values: tuple[CompactEvidenceBlock, ...]) -> list[JsonValue]:
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


def _readable_fact_list_json(values: tuple[ReadableFactItemVNext, ...]) -> list[JsonValue]:
    """把 vNext readable fact tuple 转换为 JSON 数组。

    :param values: readable fact tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _readable_answer_anchor_item_list_json(values: tuple[ReadableAnswerAnchorItemVNext, ...]) -> list[JsonValue]:
    """把 vNext readable answer anchor item tuple 转换为 JSON 数组。

    :param values: readable answer anchor item tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _readable_answer_anchor_list_json(values: tuple[ReadableAnswerAnchorVNext, ...]) -> list[JsonValue]:
    """把 vNext readable answer anchor tuple 转换为 JSON 数组。

    :param values: readable answer anchor tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _readable_forward_intent_list_json(values: tuple[ReadableForwardIntentVNext, ...]) -> list[JsonValue]:
    """把 vNext readable forward intent tuple 转换为 JSON 数组。

    :param values: readable forward intent tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _readable_reference_list_json(values: tuple[ReadableReferenceContinuityItemVNext, ...]) -> list[JsonValue]:
    """把 vNext readable reference tuple 转换为 JSON 数组。

    :param values: readable reference tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _trace_readable_list_json(values: tuple[TraceReadableItemVNext, ...]) -> list[JsonValue]:
    """把 vNext trace material tuple 转换为 JSON 数组。

    :param values: trace material tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _evidence_readable_list_json(values: tuple[EvidenceReadableItemVNext, ...]) -> list[JsonValue]:
    """把 vNext evidence material tuple 转换为 JSON 数组。

    :param values: evidence material tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _answer_readable_list_json(values: tuple[AnswerReadableItemVNext, ...]) -> list[JsonValue]:
    """把 vNext answer material tuple 转换为 JSON 数组。

    :param values: answer material tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _fact_candidate_vnext_list_json(values: tuple[CompactEvidenceFactV4, ...]) -> list[JsonValue]:
    """把 vNext fact candidate tuple 转换为 JSON 数组。

    :param values: fact candidate tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _answer_anchor_candidate_list_json(values: tuple[CompactAnswerAnchorV4, ...]) -> list[JsonValue]:
    """把 vNext answer anchor candidate tuple 转换为 JSON 数组。

    :param values: answer anchor candidate tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _forward_intent_candidate_list_json(values: tuple[CompactForwardIntentV4, ...]) -> list[JsonValue]:
    """把 vNext forward intent candidate tuple 转换为 JSON 数组。

    :param values: forward intent candidate tuple。
    :returns: JSON 数组。
    """

    result: list[JsonValue] = []
    for value in values:
        result.append(value.to_json())
    return result


def _reference_candidate_list_json(values: tuple[CompactReferenceContinuityV4, ...]) -> list[JsonValue]:
    """把 vNext reference candidate tuple 转换为 JSON 数组。

    :param values: reference candidate tuple。
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
        "overage_reason": (None if estimate.overage_reason is None else estimate.overage_reason.value),
    }


__all__ = [
    "CompactAnswerAnchorV4",
    "AnswerReadableItemVNext",
    "COMPACT_ANSWER_SOURCE_KINDS_V4",
    "COMPACT_FACT_CONTEXT_SOURCE_KINDS_V4",
    "COMPACT_FACT_SOURCE_KINDS_V4",
    "COMPACT_RETAIN_SOURCE_KINDS_V4",
    "COMPACT_FORWARD_SOURCE_KINDS_V4",
    "COMPACT_INPUT_SCHEMA_V4",
    "COMPACT_OUTPUT_SCHEMA_V4",
    "COMPACT_REFERENCE_SOURCE_KINDS_V4",
    "COMPACT_REPAIR_REQUIRED_ACTION",
    "CompactAcceptedEvidenceFactV4",
    "CompactAcceptedReplacementV4",
    "CompactAcceptedTruthV4",
    "CompactEvidenceBlock",
    "CompactOmittedCoverageV4",
    "CompactOutputCapsV4",
    "CompactPolicyUsageAuditV4",
    "CompactPolicyUsageActualsV4",
    "CompactInputRange",
    "CompactMaterialBlock",
    "CompactMaterialBlockKind",
    "CompactMaterialPack",
    "CompactMaterialSection",
    "CompactValidationReportV4",
    "CompactValidationIssueV4",
    "CompactValidationIssueCodeV4",
    "PreviousCompactReadableView",
    "CompactSegmentSelection",
    "CompactSegmentSelectionScope",
    "CompactSegmentTrigger",
    "CompactionRequest",
    "CompactorProposal",
    "CompactorProposalError",
    "CompactInputV4",
    "CompactSourceKindV4",
    "CompactSourceBoundaryEntryV4",
    "CompactSemanticSectionV4",
    "CompactRepresentedCoverageV4",
    "CompactRepresentedSourceV4",
    "CompactRepairFeedbackV4",
    "CompactCandidateV4",
    "ContextCompactor",
    "CurrentInputAnchor",
    "CompactCurrentInputV4",
    "CompactEvidenceFactV4",
    "EvidenceReadableItemVNext",
    "CompactForwardIntentV4",
    "CompactForwardIntentStatusV4",
    "PromptLocalEvidenceMap",
    "PromptLocalMaterialLabel",
    "PromptLocalProvenanceEntry",
    "ReadableAnswerAnchorItemVNext",
    "ReadableAnswerAnchorVNext",
    "ReadableFactItemVNext",
    "ReadableForwardIntentVNext",
    "ReadableReferenceContinuityItemVNext",
    "SelectedBlockProvenance",
    "CompactReferenceContinuityV4",
    "CompactSessionSummaryV4",
    "TraceReadableItemVNext",
    "TraceReadableKindVNext",
    "TurnGroupMembership",
    "MAX_COMPACT_REPAIR_FEEDBACK_CHARS",
    "MAX_COMPACT_REPAIR_ISSUES",
    "MAX_COMPACT_REPAIR_ISSUE_MESSAGE_CHARS",
    "previous_answer_anchor_block_text",
    "compact_policy_usage_measurement_rules_v4",
    "compact_proposal_boundary_binding_issues_v4",
    "compact_text_size_units_v4",
    "derive_compact_replacement_policy_usage_actuals_v4",
    "derive_compact_accepted_replacement_v4",
    "validate_compact_policy_usage_audit_replacement_binding_v4",
    "validate_compact_proposal_replacement_binding_v4",
    "validate_compact_represented_coverage_replacement_binding_v4",
    "validate_previous_compacted_view_pair",
]
