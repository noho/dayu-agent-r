"""Host accepted evidence envelope typed contract。

本模块定义工具结果被 Host accept barrier 接受后写入 EventLog 的中立证据
信封。信封描述 Host 可校验的事件、工具调用、digest 与不透明 refs；
它不解析财报业务 source / locator 语义，也不复制 request / query 正文。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from dayu.contracts.json_value import JsonValue
from dayu.host.durable.codec import canonical_json_dumps, is_sha256_digest

_FIELD_ACCEPTED_EVIDENCE_ENVELOPE = "accepted_evidence_envelope"
_EVIDENCE_ID_PREFIX = "evidence:"
_FIELD_DIGEST = "digest"
_FIELD_EVIDENCE_ID = "evidence_id"
_FIELD_LOCATOR_REFS = "locator_refs"
_FIELD_NORMALIZED_ARGUMENTS_DIGEST = "normalized_arguments_digest"
_FIELD_OUTCOME_DIGEST = "outcome_digest"
_FIELD_PAYLOAD_DIGEST = "payload_digest"
_FIELD_PAYLOAD_REF = "payload_ref"
_FIELD_PRODUCER_EVENT_REF = "producer_event_ref"
_FIELD_REF_ID = "ref_id"
_FIELD_REF_KIND = "ref_kind"
_FIELD_RAW_TOOL_OUTCOME = "raw_tool_outcome"
_FIELD_RESULT_PREVIEW = "result_preview"
_FIELD_RESULT_REF = "result_ref"
_FIELD_SEMANTIC_INPUT_DIGEST = "semantic_input_digest"
_FIELD_SOURCE_REFS = "source_refs"
_FIELD_TOOL_CALL_ID = "tool_call_id"
_FIELD_TOOL_CALL_REQUESTED_EVENT_REF = "tool_call_requested_event_ref"
_FIELD_TOOL_NAME = "tool_name"
_FIELD_TOOL_QUERY = "tool_query"
_FIELD_TRUNCATION_APPLIED = "truncation_applied"
ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT = "该工具结果未提供业务来源。"
"""Accepted tool result 未携带显式业务来源时的唯一 LLM-facing 文案。"""
_ENVELOPE_FIELDS = frozenset(
    {
        _FIELD_EVIDENCE_ID,
        _FIELD_PRODUCER_EVENT_REF,
        _FIELD_TOOL_NAME,
        _FIELD_TOOL_CALL_ID,
        _FIELD_TOOL_QUERY,
        _FIELD_RESULT_REF,
        _FIELD_SOURCE_REFS,
        _FIELD_LOCATOR_REFS,
    }
)
_TOOL_QUERY_FIELDS = frozenset(
    {
        _FIELD_TOOL_CALL_REQUESTED_EVENT_REF,
        _FIELD_NORMALIZED_ARGUMENTS_DIGEST,
        _FIELD_SEMANTIC_INPUT_DIGEST,
    }
)
_RESULT_REF_FIELDS = frozenset(
    {
        _FIELD_PAYLOAD_REF,
        _FIELD_PAYLOAD_DIGEST,
        _FIELD_OUTCOME_DIGEST,
        _FIELD_TRUNCATION_APPLIED,
    }
)
_OPAQUE_REF_FIELDS = frozenset({_FIELD_REF_KIND, _FIELD_REF_ID, _FIELD_DIGEST})


@dataclass(frozen=True, slots=True)
class OpaqueEvidenceRef:
    """Host 不解析语义的 evidence ref。

    :param ref_kind: ref 类型文本。
    :param ref_id: ref 不透明标识。
    :param digest: 可选 sha256 digest。
    """

    ref_kind: str
    ref_id: str
    digest: str | None

    def __post_init__(self) -> None:
        """校验 opaque evidence ref。

        :returns: ``None``。
        :raises ValueError: 文本为空或 digest 非法时抛出。
        """

        _require_non_empty_text(self.ref_kind, "ref_kind")
        _require_non_empty_text(self.ref_id, "ref_id")
        _require_optional_sha256_digest(self.digest, "digest")


class AcceptedEvidenceProducerEventRefMismatchError(ValueError):
    """Accepted evidence producer event ref 不一致的专用异常。

    :param expected_event_ref: 当前读取方期望的 producer event ref。
    :param observed_event_ref: envelope 实际携带的 producer event ref。
    """

    expected_event_ref: str
    observed_event_ref: str

    def __init__(self, *, expected_event_ref: str, observed_event_ref: str) -> None:
        """初始化 mismatch 异常。

        :param expected_event_ref: 当前读取方期望的 producer event ref。
        :param observed_event_ref: envelope 实际携带的 producer event ref。
        :returns: ``None``。
        :raises ValueError: 任一 event ref 为空时抛出。
        """

        _require_non_empty_text(expected_event_ref, "expected_event_ref")
        _require_non_empty_text(observed_event_ref, "observed_event_ref")
        self.expected_event_ref = expected_event_ref
        self.observed_event_ref = observed_event_ref
        super().__init__("accepted evidence producer_event_ref mismatch")


@dataclass(frozen=True, slots=True)
class AcceptedToolEvidenceLLMMaterial:
    """Accepted tool evidence 的 LLM-facing material。

    :param tool_name: 工具名称。
    :param query_text: producer query 或 exact canonical 参数投影。
    :param source_text: producer 显式 citation 或业务中性 unavailable 文案。
    :param result_text: 工具结果 canonical 文本。
    """

    tool_name: str
    query_text: str
    source_text: str
    result_text: str

    def __post_init__(self) -> None:
        """校验 LLM material 文本字段。

        :returns: ``None``。
        :raises ValueError: 任一字段不是非空文本时抛出。
        """

        _require_non_empty_text(self.tool_name, "AcceptedToolEvidenceLLMMaterial.tool_name")
        _require_non_empty_text(
            self.query_text,
            "AcceptedToolEvidenceLLMMaterial.query_text",
        )
        _require_non_empty_text(
            self.source_text,
            "AcceptedToolEvidenceLLMMaterial.source_text",
        )
        _require_non_empty_text(
            self.result_text,
            "AcceptedToolEvidenceLLMMaterial.result_text",
        )


def render_accepted_tool_evidence_for_llm(
    material: AcceptedToolEvidenceLLMMaterial,
) -> str:
    """渲染 accepted tool evidence 的唯一 LLM-facing 四行文本。

    :param material: accepted evidence LLM material。
    :returns: 业务可读 evidence 文本。
    :raises TypeError: material 类型非法时抛出。
    """

    if not isinstance(material, AcceptedToolEvidenceLLMMaterial):
        raise TypeError("material must be AcceptedToolEvidenceLLMMaterial")
    return "\n".join(
        (
            f"工具名称：{material.tool_name}",
            f"查询语义：{material.query_text}",
            f"业务来源：{material.source_text}",
            f"工具结果：{material.result_text}",
        )
    )


@dataclass(frozen=True, slots=True)
class AcceptedEvidenceToolQuery:
    """Accepted evidence 中的工具查询引用。

    :param tool_call_requested_event_ref: 可选 ``TOOL_CALL_REQUESTED`` event id。
    :param normalized_arguments_digest: 工具参数 canonical digest。
    :param semantic_input_digest: Host accept semantic input digest。
    """

    tool_call_requested_event_ref: str | None
    normalized_arguments_digest: str
    semantic_input_digest: str

    def __post_init__(self) -> None:
        """校验工具查询引用。

        :returns: ``None``。
        :raises ValueError: event ref 为空或 digest 非法时抛出。
        """

        _require_optional_non_empty_text(
            self.tool_call_requested_event_ref, "tool_call_requested_event_ref"
        )
        _require_sha256_digest(
            self.normalized_arguments_digest, "normalized_arguments_digest"
        )
        _require_sha256_digest(self.semantic_input_digest, "semantic_input_digest")


@dataclass(frozen=True, slots=True)
class AcceptedEvidenceResultRef:
    """Accepted evidence 中的工具结果引用。

    :param payload_ref: 可选 Host payload descriptor ref。
    :param payload_digest: 可选工具结果 payload digest。
    :param outcome_digest: 可选工具 outcome digest。
    :param truncation_applied: 工具结果是否被 Host 截断。
    """

    payload_ref: str | None
    payload_digest: str | None
    outcome_digest: str | None
    truncation_applied: bool

    def __post_init__(self) -> None:
        """校验工具结果引用。

        :returns: ``None``。
        :raises ValueError: 文本为空或 digest 非法时抛出。
        """

        _require_optional_non_empty_text(self.payload_ref, "payload_ref")
        _require_optional_sha256_digest(self.payload_digest, "payload_digest")
        _require_optional_sha256_digest(self.outcome_digest, "outcome_digest")
        if not isinstance(self.truncation_applied, bool):
            raise ValueError("truncation_applied must be bool")


@dataclass(frozen=True, slots=True)
class AcceptedEvidenceEnvelope:
    """Host accept 后的稳定证据信封。

    :param evidence_id: 稳定 evidence id，格式为 ``evidence:<accepted_event_id>``。
    :param producer_event_ref: 产生该证据的 ``TOOL_RESULT_ACCEPTED`` event id。
    :param tool_name: 工具名。
    :param tool_call_id: 工具调用 id。
    :param tool_query: 工具查询引用。
    :param result_ref: 工具结果引用。
    :param source_refs: 已存在的 opaque source refs；缺失时为空 tuple。
    :param locator_refs: 已存在的 opaque locator refs；缺失时为空 tuple。
    """

    evidence_id: str
    producer_event_ref: str
    tool_name: str
    tool_call_id: str
    tool_query: AcceptedEvidenceToolQuery
    result_ref: AcceptedEvidenceResultRef
    source_refs: tuple[OpaqueEvidenceRef, ...]
    locator_refs: tuple[OpaqueEvidenceRef, ...]

    def __post_init__(self) -> None:
        """校验 accepted evidence envelope。

        :returns: ``None``。
        :raises ValueError: 必填文本为空、类型错误或 evidence id 非法时抛出。
        """

        _require_non_empty_text(self.evidence_id, "evidence_id")
        if not self.evidence_id.startswith(_EVIDENCE_ID_PREFIX):
            raise ValueError("evidence_id must use evidence:<event_id> format")
        _require_non_empty_text(self.producer_event_ref, "producer_event_ref")
        _require_non_empty_text(self.tool_name, "tool_name")
        _require_non_empty_text(self.tool_call_id, "tool_call_id")
        if not isinstance(self.tool_query, AcceptedEvidenceToolQuery):
            raise ValueError("tool_query must be AcceptedEvidenceToolQuery")
        if not isinstance(self.result_ref, AcceptedEvidenceResultRef):
            raise ValueError("result_ref must be AcceptedEvidenceResultRef")
        for ref in self.source_refs:
            if not isinstance(ref, OpaqueEvidenceRef):
                raise ValueError("source_refs must contain OpaqueEvidenceRef")
        for ref in self.locator_refs:
            if not isinstance(ref, OpaqueEvidenceRef):
                raise ValueError("locator_refs must contain OpaqueEvidenceRef")


def derive_accepted_evidence_id(accepted_event_id: str) -> str:
    """从 accepted tool result event id 派生 evidence id。

    :param accepted_event_id: ``TOOL_RESULT_ACCEPTED`` event id。
    :returns: 稳定 evidence id。
    :raises ValueError: event id 为空时抛出。
    """

    _require_non_empty_text(accepted_event_id, "accepted_event_id")
    return f"{_EVIDENCE_ID_PREFIX}{accepted_event_id}"


def accepted_evidence_envelope_to_json_value(
    envelope: AcceptedEvidenceEnvelope,
) -> JsonValue:
    """把 accepted evidence envelope 编码为严格 JSON 值。

    :param envelope: accepted evidence envelope。
    :returns: JSON object。
    """

    return {
        _FIELD_EVIDENCE_ID: envelope.evidence_id,
        _FIELD_PRODUCER_EVENT_REF: envelope.producer_event_ref,
        _FIELD_TOOL_NAME: envelope.tool_name,
        _FIELD_TOOL_CALL_ID: envelope.tool_call_id,
        _FIELD_TOOL_QUERY: {
            _FIELD_TOOL_CALL_REQUESTED_EVENT_REF: (
                envelope.tool_query.tool_call_requested_event_ref
            ),
            _FIELD_NORMALIZED_ARGUMENTS_DIGEST: (
                envelope.tool_query.normalized_arguments_digest
            ),
            _FIELD_SEMANTIC_INPUT_DIGEST: (
                envelope.tool_query.semantic_input_digest
            ),
        },
        _FIELD_RESULT_REF: {
            _FIELD_PAYLOAD_REF: envelope.result_ref.payload_ref,
            _FIELD_PAYLOAD_DIGEST: envelope.result_ref.payload_digest,
            _FIELD_OUTCOME_DIGEST: envelope.result_ref.outcome_digest,
            _FIELD_TRUNCATION_APPLIED: envelope.result_ref.truncation_applied,
        },
        _FIELD_SOURCE_REFS: [
            _opaque_evidence_ref_to_json_value(ref)
            for ref in envelope.source_refs
        ],
        _FIELD_LOCATOR_REFS: [
            _opaque_evidence_ref_to_json_value(ref)
            for ref in envelope.locator_refs
        ],
    }


def accepted_evidence_envelope_from_json_value(
    value: JsonValue,
) -> AcceptedEvidenceEnvelope:
    """从严格 JSON 值解码 accepted evidence envelope。

    :param value: JSON object。
    :returns: accepted evidence envelope。
    :raises ValueError: 字段缺失、多余、类型错误或 digest 非法时抛出。
    """

    mapping = _required_mapping(value, "accepted_evidence_envelope")
    _require_exact_keys(mapping, _ENVELOPE_FIELDS, "accepted_evidence_envelope")
    tool_query_mapping = _required_mapping(
        _required_value(mapping, _FIELD_TOOL_QUERY), _FIELD_TOOL_QUERY
    )
    _require_exact_keys(tool_query_mapping, _TOOL_QUERY_FIELDS, _FIELD_TOOL_QUERY)
    result_ref_mapping = _required_mapping(
        _required_value(mapping, _FIELD_RESULT_REF), _FIELD_RESULT_REF
    )
    _require_exact_keys(result_ref_mapping, _RESULT_REF_FIELDS, _FIELD_RESULT_REF)
    return AcceptedEvidenceEnvelope(
        evidence_id=_required_str(mapping, _FIELD_EVIDENCE_ID),
        producer_event_ref=_required_str(mapping, _FIELD_PRODUCER_EVENT_REF),
        tool_name=_required_str(mapping, _FIELD_TOOL_NAME),
        tool_call_id=_required_str(mapping, _FIELD_TOOL_CALL_ID),
        tool_query=AcceptedEvidenceToolQuery(
            tool_call_requested_event_ref=_optional_str(
                tool_query_mapping, _FIELD_TOOL_CALL_REQUESTED_EVENT_REF
            ),
            normalized_arguments_digest=_required_str(
                tool_query_mapping, _FIELD_NORMALIZED_ARGUMENTS_DIGEST
            ),
            semantic_input_digest=_required_str(
                tool_query_mapping, _FIELD_SEMANTIC_INPUT_DIGEST
            ),
        ),
        result_ref=AcceptedEvidenceResultRef(
            payload_ref=_optional_str(result_ref_mapping, _FIELD_PAYLOAD_REF),
            payload_digest=_optional_str(result_ref_mapping, _FIELD_PAYLOAD_DIGEST),
            outcome_digest=_optional_str(result_ref_mapping, _FIELD_OUTCOME_DIGEST),
            truncation_applied=_required_bool(
                result_ref_mapping, _FIELD_TRUNCATION_APPLIED
            ),
        ),
        source_refs=tuple(
            _opaque_evidence_ref_from_json_value(item)
            for item in _required_list(mapping, _FIELD_SOURCE_REFS)
        ),
        locator_refs=tuple(
            _opaque_evidence_ref_from_json_value(item)
            for item in _required_list(mapping, _FIELD_LOCATOR_REFS)
        ),
    )


def accepted_evidence_envelope_from_payload(
    payload: Mapping[str, JsonValue],
    *,
    producer_event_ref: str,
) -> AcceptedEvidenceEnvelope | None:
    """从 ``TOOL_RESULT_ACCEPTED`` payload 读取 accepted evidence envelope。

    :param payload: ``TOOL_RESULT_ACCEPTED`` payload。
    :param producer_event_ref: 当前 producer event id，用于校验 envelope 同源。
    :returns: envelope；payload 未携带 envelope 时返回 ``None``。
    :raises ValueError: envelope 结构非法或 producer event ref 不匹配时抛出。
    """

    _require_non_empty_text(producer_event_ref, "producer_event_ref")
    envelope_value = payload.get(_FIELD_ACCEPTED_EVIDENCE_ENVELOPE)
    if envelope_value is None:
        return None
    envelope = accepted_evidence_envelope_from_json_value(envelope_value)
    if envelope.producer_event_ref != producer_event_ref:
        raise AcceptedEvidenceProducerEventRefMismatchError(
            expected_event_ref=producer_event_ref,
            observed_event_ref=envelope.producer_event_ref,
        )
    return envelope


def accepted_tool_raw_outcome_text_from_payload(
    payload: Mapping[str, JsonValue],
) -> str | None:
    """从 accepted tool result payload 读取原始工具响应文本。

    该 helper 只读取 Host accept barrier 写入的 ``raw_tool_outcome``，并拒绝旧
    ``result_preview`` 字段。返回值是 canonical JSON 文本，用于 LLM-facing
    post-compact delta / memory continuity；不得用 event id、payload ref 或 digest
    代替该文本。

    :param payload: digest-checked ``TOOL_RESULT_ACCEPTED`` payload。
    :returns: canonical raw tool outcome 文本；缺失时返回 ``None``。
    :raises ValueError: payload 中存在旧 ``result_preview`` 字段时抛出。
    """

    if _FIELD_RESULT_PREVIEW in payload:
        raise ValueError("TOOL_RESULT_ACCEPTED result_preview is not allowed")
    raw_outcome = payload.get(_FIELD_RAW_TOOL_OUTCOME)
    if raw_outcome is None:
        return None
    return canonical_json_dumps(raw_outcome)


def _opaque_evidence_ref_to_json_value(ref: OpaqueEvidenceRef) -> JsonValue:
    """把 opaque evidence ref 编码为 JSON 值。

    :param ref: opaque evidence ref。
    :returns: JSON object。
    """

    return {
        _FIELD_REF_KIND: ref.ref_kind,
        _FIELD_REF_ID: ref.ref_id,
        _FIELD_DIGEST: ref.digest,
    }


def _opaque_evidence_ref_from_json_value(value: JsonValue) -> OpaqueEvidenceRef:
    """从 JSON 值解码 opaque evidence ref。

    :param value: JSON object。
    :returns: opaque evidence ref。
    :raises ValueError: 字段缺失、多余、类型错误或 digest 非法时抛出。
    """

    mapping = _required_mapping(value, "opaque_evidence_ref")
    _require_exact_keys(mapping, _OPAQUE_REF_FIELDS, "opaque_evidence_ref")
    return OpaqueEvidenceRef(
        ref_kind=_required_str(mapping, _FIELD_REF_KIND),
        ref_id=_required_str(mapping, _FIELD_REF_ID),
        digest=_optional_str(mapping, _FIELD_DIGEST),
    )


def _required_mapping(value: JsonValue, field_name: str) -> Mapping[str, JsonValue]:
    """校验并返回 JSON object。

    :param value: JSON 值。
    :param field_name: 字段名。
    :returns: JSON mapping。
    :raises ValueError: 值不是 JSON object 时抛出。
    """

    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a JSON object")
    return value


def _required_value(mapping: Mapping[str, JsonValue], field_name: str) -> JsonValue:
    """读取必填 JSON 字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :returns: 字段值。
    :raises ValueError: 字段缺失时抛出。
    """

    if field_name not in mapping:
        raise ValueError(f"{field_name} is required")
    return mapping[field_name]


def _required_str(mapping: Mapping[str, JsonValue], field_name: str) -> str:
    """读取必填非空字符串字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :returns: 字符串值。
    :raises ValueError: 字段缺失、类型错误或为空时抛出。
    """

    value = _required_value(mapping, field_name)
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    _require_non_empty_text(value, field_name)
    return value


def _optional_str(
    mapping: Mapping[str, JsonValue], field_name: str
) -> str | None:
    """读取可选非空字符串字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :returns: 字符串值或 ``None``。
    :raises ValueError: 字段类型错误或为空时抛出。
    """

    value = _required_value(mapping, field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string or null")
    _require_non_empty_text(value, field_name)
    return value


def _required_bool(mapping: Mapping[str, JsonValue], field_name: str) -> bool:
    """读取必填 bool 字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :returns: bool 值。
    :raises ValueError: 字段缺失或类型错误时抛出。
    """

    value = _required_value(mapping, field_name)
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _required_list(
    mapping: Mapping[str, JsonValue], field_name: str
) -> list[JsonValue]:
    """读取必填 JSON array 字段。

    :param mapping: JSON object。
    :param field_name: 字段名。
    :returns: JSON 值列表。
    :raises ValueError: 字段缺失或类型错误时抛出。
    """

    value = _required_value(mapping, field_name)
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a JSON array")
    return value


def _require_exact_keys(
    mapping: Mapping[str, JsonValue], expected_keys: frozenset[str], field_name: str
) -> None:
    """校验 JSON object 的字段集合完全匹配。

    :param mapping: JSON object。
    :param expected_keys: 允许字段集合。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: 字段缺失或出现多余字段时抛出。
    """

    actual_keys = frozenset(mapping.keys())
    if actual_keys != expected_keys:
        raise ValueError(f"{field_name} has unexpected JSON fields")


def _require_non_empty_text(value: str, field_name: str) -> None:
    """校验文本非空。

    :param value: 待校验文本。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: 文本为空时抛出。
    """

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty")


def _require_optional_non_empty_text(
    value: str | None, field_name: str
) -> None:
    """校验可选文本非空。

    :param value: 文本或 ``None``。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: 文本为空时抛出。
    """

    if value is not None:
        _require_non_empty_text(value, field_name)


def _require_sha256_digest(value: str, field_name: str) -> None:
    """校验必填 sha256 digest。

    :param value: digest 文本。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: digest 非法时抛出。
    """

    if not isinstance(value, str) or not is_sha256_digest(value):
        raise ValueError(f"{field_name} must be a sha256 digest")


def _require_optional_sha256_digest(
    value: str | None, field_name: str
) -> None:
    """校验可选 sha256 digest。

    :param value: digest 文本或 ``None``。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: digest 非法时抛出。
    """

    if value is not None:
        _require_sha256_digest(value, field_name)


__all__ = [
    "ACCEPTED_EVIDENCE_SOURCE_UNAVAILABLE_TEXT",
    "AcceptedEvidenceEnvelope",
    "AcceptedEvidenceProducerEventRefMismatchError",
    "AcceptedEvidenceResultRef",
    "AcceptedEvidenceToolQuery",
    "AcceptedToolEvidenceLLMMaterial",
    "OpaqueEvidenceRef",
    "accepted_evidence_envelope_from_payload",
    "accepted_evidence_envelope_from_json_value",
    "accepted_evidence_envelope_to_json_value",
    "accepted_tool_raw_outcome_text_from_payload",
    "derive_accepted_evidence_id",
    "render_accepted_tool_evidence_for_llm",
]
