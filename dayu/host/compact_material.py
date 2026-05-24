"""Host compact material pack 与 prompt-local label helper。

本模块是 Phase 12.6 Slice 1 的 material/label owner。它只构造 Host
internal material pack，不读取业务工具、不写 EventLog、不向 Engine 暴露
Host provenance。
"""

from __future__ import annotations

from dataclasses import dataclass

from dayu.host.compaction import (
    CompactEvidenceBlock,
    CompactMaterialBlock,
    CompactMaterialBlockKind,
    CompactMaterialPack,
    CompactMaterialSection,
    CompactSegmentSelection,
    CompactSegmentTrigger,
    CurrentInputAnchor,
    PromptLocalMaterialLabel,
    PromptLocalProvenanceEntry,
)
from dayu.host.durable.codec import sha256_digest_json

_CURRENT_INPUT_PREFIX = "C"
_HISTORY_PREFIX = "H"
_EVIDENCE_PREFIX = "E"
_STABLE_PREFIX = "S"
_LABEL_CHUNK_SEPARATOR = "."
_FIRST_ORDINAL = 1
_CURRENT_ANCHOR_ORDINAL = 1
_INITIAL_POLICY_DIGEST = "slice1-initial-policy"
_INITIAL_REASON_CURRENT = "slice1_current_anchor"
_INITIAL_REASON_HISTORY = "slice1_history_material"
_INITIAL_REASON_EVIDENCE = "slice1_evidence_material"
_INITIAL_REASON_STABLE = "slice1_stable_material"

_SECTION_PREFIXES = {
    CompactMaterialSection.CURRENT_INPUT_ANCHOR: _CURRENT_INPUT_PREFIX,
    CompactMaterialSection.HISTORY_INPUT: _HISTORY_PREFIX,
    CompactMaterialSection.EVIDENCE_INPUT: _EVIDENCE_PREFIX,
    CompactMaterialSection.STABLE_INPUT: _STABLE_PREFIX,
}


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


def material_label(
    section: CompactMaterialSection, ordinal: int
) -> PromptLocalMaterialLabel:
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


def evidence_chunk_label(
    evidence_ordinal: int, chunk_ordinal: int
) -> PromptLocalMaterialLabel:
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
    return (
        f"{_EVIDENCE_PREFIX}{evidence_ordinal}"
        f"{_LABEL_CHUNK_SEPARATOR}{chunk_ordinal}"
    )


def current_input_anchor_label() -> PromptLocalMaterialLabel:
    """返回 Slice 1 current input anchor label。

    :returns: ``C1``。
    """

    return material_label(
        CompactMaterialSection.CURRENT_INPUT_ANCHOR,
        _CURRENT_ANCHOR_ORDINAL,
    )


def validate_material_label(
    label: PromptLocalMaterialLabel, section: CompactMaterialSection
) -> None:
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
        if section is not CompactMaterialSection.EVIDENCE_INPUT:
            raise ValueError("chunk label only belongs to evidence section")
        _validate_positive_decimal(parent)
        _validate_positive_decimal(chunk)
        return
    _validate_positive_decimal(ordinal_text)


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

    stable_blocks: tuple[CompactMaterialBlock, ...] = ()
    history_blocks = _history_blocks(history_materials)
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
        *_history_provenance(history_blocks),
        *_evidence_provenance(evidence_blocks, evidence_materials),
    ]
    provenance_map = {entry.label: entry for entry in provenance_entries}
    return CompactMaterialPack(
        stable_input=stable_blocks,
        history_input=history_blocks,
        evidence_input=evidence_blocks,
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


def _history_blocks(
    materials: tuple[InitialHistoryMaterial, ...]
) -> tuple[CompactMaterialBlock, ...]:
    """把初始 history material 转为 typed blocks。

    :param materials: 初始 history material。
    :returns: material block tuple。
    """

    blocks: list[CompactMaterialBlock] = []
    for index, material in enumerate(materials, start=_FIRST_ORDINAL):
        blocks.append(
            CompactMaterialBlock(
                block_label=material_label(
                    CompactMaterialSection.HISTORY_INPUT,
                    index,
                ),
                section=CompactMaterialSection.HISTORY_INPUT,
                kind=material.kind,
                text=material.text,
                size_units=len(material.text),
                source_labels=(),
                canonical_source_refs=(material.canonical_source_ref,),
                content_digest=_text_digest(material.text),
            )
        )
    return tuple(blocks)


def _evidence_blocks(
    materials: tuple[InitialEvidenceMaterial, ...]
) -> tuple[CompactEvidenceBlock, ...]:
    """把初始 evidence material 转为 typed blocks。

    :param materials: 初始 evidence material。
    :returns: evidence block tuple。
    """

    blocks: list[CompactEvidenceBlock] = []
    for index, material in enumerate(materials, start=_FIRST_ORDINAL):
        blocks.append(
            CompactEvidenceBlock(
                evidence_label=material_label(
                    CompactMaterialSection.EVIDENCE_INPUT,
                    index,
                ),
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


def _history_provenance(
    blocks: tuple[CompactMaterialBlock, ...]
) -> tuple[PromptLocalProvenanceEntry, ...]:
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
    blocks: tuple[CompactEvidenceBlock, ...],
    materials: tuple[InitialEvidenceMaterial, ...],
) -> tuple[PromptLocalProvenanceEntry, ...]:
    """构造 evidence block provenance entries。

    :param blocks: evidence blocks。
    :param materials: 初始 evidence material。
    :returns: provenance entries。
    """

    entries: list[PromptLocalProvenanceEntry] = []
    for block, material in zip(blocks, materials, strict=True):
        entries.append(
            PromptLocalProvenanceEntry(
                label=block.evidence_label,
                section=CompactMaterialSection.EVIDENCE_INPUT,
                kind=CompactMaterialBlockKind.ACCEPTED_TOOL_EVIDENCE,
                canonical_source_refs=block.canonical_source_refs,
                source_event_refs=(material.tool_result_event_ref,),
                content_digest=block.content_digest,
                accepted_evidence_id=material.accepted_evidence_id,
                tool_result_event_ref=material.tool_result_event_ref,
                tool_call_event_ref=material.tool_call_event_ref,
                payload_refs=material.payload_refs,
                artifact_refs=(),
                source_locator_refs=(),
            )
        )
    return tuple(entries)


def _initial_reason_codes(pack: CompactMaterialPack) -> tuple[str, ...]:
    """构造 Slice 1 初始 reason codes。

    :param pack: material pack。
    :returns: reason code tuple。
    """

    reasons: list[str] = [_INITIAL_REASON_CURRENT]
    if len(pack.stable_input) > 0:
        reasons.append(_INITIAL_REASON_STABLE)
    if len(pack.history_input) > 0:
        reasons.append(_INITIAL_REASON_HISTORY)
    if len(pack.evidence_input) > 0:
        reasons.append(_INITIAL_REASON_EVIDENCE)
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


__all__ = [
    "InitialEvidenceMaterial",
    "InitialHistoryMaterial",
    "build_initial_material_pack",
    "current_input_anchor_label",
    "evidence_chunk_label",
    "initial_segment_selection",
    "material_label",
    "validate_material_label",
]
