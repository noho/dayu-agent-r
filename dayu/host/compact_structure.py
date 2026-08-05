"""Compact output v3 的唯一 JSON 结构 owner。

本模块只拥有 immutable exact descriptors，并由它们投影 concrete template、
JSON Schema 与 parser 的 exact-key contract。业务 dataclass 仍由
``dayu.host.compaction`` 唯一定义；本模块不拥有 acceptance、policy、durable state、
Engine transport 或 prompt 文案。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from json import JSONDecodeError

from dayu.contracts.json_value import JsonValue
from dayu.host.compaction import (
    COMPACT_OUTPUT_SCHEMA_V3,
    CompactAnswerAnchorV3,
    CompactCandidateV3,
    CompactEvidenceFactV3,
    CompactForwardIntentStatusV3,
    CompactForwardIntentV3,
    CompactReferenceContinuityV3,
    CompactSessionSummaryV3,
)
from dayu.host.durable.codec import sha256_digest_json

COMPACT_OUTPUT_JSON_SCHEMA_NAME_V3 = "dayu_context_compaction_output_v3"
"""Provider-neutral compact output v3 JSON Schema 名称。"""


class _FieldKind(StrEnum):
    """结构 descriptor 支持的封闭字段类型。"""

    CONST_TEXT = "const_text"
    TEXT = "text"
    TEXT_ARRAY = "text_array"
    ENUM = "enum"
    NULLABLE_OBJECT = "nullable_object"
    OBJECT_ARRAY = "object_array"


@dataclass(frozen=True, slots=True)
class _ObjectDescriptor:
    """一个 exact JSON object 的 immutable descriptor。

    :param fields: 按稳定输出顺序排列的字段 descriptor。
    """

    fields: tuple["_FieldDescriptor", ...]


@dataclass(frozen=True, slots=True)
class _FieldDescriptor:
    """一个 JSON 字段的 immutable structural descriptor。

    :param name: 字段名。
    :param kind: 封闭字段结构类型。
    :param const_text: const string 值，仅 ``CONST_TEXT`` 使用。
    :param enum_values: enum string 值，仅 ``ENUM`` 使用。
    :param child: nested object descriptor。
    :param allow_empty_array: ``TEXT_ARRAY`` 是否允许空 array。
    """

    name: str
    kind: _FieldKind
    const_text: str | None = None
    enum_values: tuple[str, ...] = ()
    child: _ObjectDescriptor | None = None
    allow_empty_array: bool = True


_SUMMARY = _ObjectDescriptor(
    fields=(
        _FieldDescriptor("text", _FieldKind.TEXT),
        _FieldDescriptor(
            "source_labels",
            _FieldKind.TEXT_ARRAY,
            allow_empty_array=False,
        ),
    )
)
_FACT = _ObjectDescriptor(
    fields=(
        _FieldDescriptor("claim", _FieldKind.TEXT),
        _FieldDescriptor(
            "support_labels",
            _FieldKind.TEXT_ARRAY,
            allow_empty_array=False,
        ),
        _FieldDescriptor("context_labels", _FieldKind.TEXT_ARRAY),
    )
)
_ANCHOR = _ObjectDescriptor(
    fields=(
        _FieldDescriptor("title", _FieldKind.TEXT),
        _FieldDescriptor("detail", _FieldKind.TEXT),
        _FieldDescriptor(
            "source_labels",
            _FieldKind.TEXT_ARRAY,
            allow_empty_array=False,
        ),
    )
)
_INTENT = _ObjectDescriptor(
    fields=(
        _FieldDescriptor("intent_type", _FieldKind.TEXT),
        _FieldDescriptor("text", _FieldKind.TEXT),
        _FieldDescriptor(
            "status",
            _FieldKind.ENUM,
            enum_values=tuple(item.value for item in CompactForwardIntentStatusV3),
        ),
        _FieldDescriptor(
            "source_labels",
            _FieldKind.TEXT_ARRAY,
            allow_empty_array=False,
        ),
    )
)
_REFERENCE = _ObjectDescriptor(
    fields=(
        _FieldDescriptor("text", _FieldKind.TEXT),
        _FieldDescriptor("reason", _FieldKind.TEXT),
        _FieldDescriptor(
            "source_labels",
            _FieldKind.TEXT_ARRAY,
            allow_empty_array=False,
        ),
    )
)
_ROOT = _ObjectDescriptor(
    fields=(
        _FieldDescriptor(
            "schema",
            _FieldKind.CONST_TEXT,
            const_text=COMPACT_OUTPUT_SCHEMA_V3,
        ),
        _FieldDescriptor(
            "session_summary",
            _FieldKind.NULLABLE_OBJECT,
            child=_SUMMARY,
        ),
        _FieldDescriptor("evidence_facts", _FieldKind.OBJECT_ARRAY, child=_FACT),
        _FieldDescriptor("answer_anchors", _FieldKind.OBJECT_ARRAY, child=_ANCHOR),
        _FieldDescriptor("forward_intents", _FieldKind.OBJECT_ARRAY, child=_INTENT),
        _FieldDescriptor(
            "reference_continuity",
            _FieldKind.OBJECT_ARRAY,
            child=_REFERENCE,
        ),
    )
)


def compact_output_template_v3() -> Mapping[str, JsonValue]:
    """返回从 immutable descriptors 机械生成的完整 concrete template。

    :returns: 含 root 与全部 nested exact keys 的 fresh JSON mapping。调用方修改
        返回值不会改变结构 owner 的后续投影。
    """

    return _template_object(_ROOT)


def compact_output_json_schema_v3() -> Mapping[str, JsonValue]:
    """返回从同一 descriptors 机械生成的 strict JSON Schema。

    :returns: all-fields-required、所有 object ``additionalProperties=false`` 的
        fresh canonical JSON mapping。
    """

    return _schema_object(_ROOT)


def compact_output_prompt_rules_v3() -> Mapping[str, JsonValue]:
    """返回给无状态模型阅读的精简字段结构投影。

    该投影与 formal provider JSON Schema 均从同一 descriptors 生成，但只保留
    当前动作所需的字段、类型、必填性、nullable 与 enum 信息，避免把 formal
    schema 关键字树冗余注入 prompt。

    :returns: root/nested exact fields 的 concise fresh JSON mapping。
    """

    return _prompt_rules_object(_ROOT)


def compact_output_json_schema_digest_v3() -> str:
    """计算 compact output v3 JSON Schema 的 Host canonical digest。

    :returns: ``sha256:<hex>`` schema digest。
    """

    return sha256_digest_json(compact_output_json_schema_v3())


def parse_compact_candidate_v3(text: str) -> CompactCandidateV3:
    """解析 strict compact output v3 并构造 domain candidate。

    :param text: LLM 返回的完整 JSON object 文本。
    :returns: exact keys/types 均合法的 ``CompactCandidateV3``。
    :raises TypeError: ``text`` 不是字符串时抛出。
    :raises ValueError: JSON、duplicate key、字段集合、类型或枚举非法时抛出。
    """

    if not isinstance(text, str):
        raise TypeError("text must be str")
    raw = text.strip()
    if not raw:
        raise ValueError("blank_required_text: candidate must be non-empty")
    try:
        parsed: JsonValue = json.loads(raw, object_pairs_hook=_strict_object_pairs)
    except JSONDecodeError as exc:
        raise ValueError(f"invalid_json: {exc.msg}") from exc
    root = _exact_object(parsed, _ROOT, path="$")
    schema = _required_text(root, "schema", path="$.schema")
    if schema != COMPACT_OUTPUT_SCHEMA_V3:
        raise ValueError("invalid_enum_value: $.schema")
    return CompactCandidateV3(
        schema=COMPACT_OUTPUT_SCHEMA_V3,
        session_summary=_parse_summary(root["session_summary"]),
        evidence_facts=tuple(
            _parse_fact(item, index)
            for index, item in enumerate(
                _required_array(root, "evidence_facts", path="$.evidence_facts")
            )
        ),
        answer_anchors=tuple(
            _parse_anchor(item, index)
            for index, item in enumerate(
                _required_array(root, "answer_anchors", path="$.answer_anchors")
            )
        ),
        forward_intents=tuple(
            _parse_intent(item, index)
            for index, item in enumerate(
                _required_array(root, "forward_intents", path="$.forward_intents")
            )
        ),
        reference_continuity=tuple(
            _parse_reference(item, index)
            for index, item in enumerate(
                _required_array(
                    root,
                    "reference_continuity",
                    path="$.reference_continuity",
                )
            )
        ),
    )


def _template_object(descriptor: _ObjectDescriptor) -> dict[str, JsonValue]:
    """从 object descriptor 生成包含全部字段的示例 object。

    :param descriptor: immutable object descriptor。
    :returns: fresh template object。
    """

    return {field.name: _template_value(field) for field in descriptor.fields}


def _template_value(field: _FieldDescriptor) -> JsonValue:
    """从字段 descriptor 生成 concrete 示例值。

    :param field: immutable field descriptor。
    :returns: 与字段结构匹配的 JSON 值。
    :raises RuntimeError: descriptor 自身不完整时抛出。
    """

    if field.kind is _FieldKind.CONST_TEXT:
        if field.const_text is None:
            raise RuntimeError("const text descriptor is incomplete")
        return field.const_text
    if field.kind is _FieldKind.TEXT:
        return "业务可读文本"
    if field.kind is _FieldKind.TEXT_ARRAY:
        return [] if field.allow_empty_array else ["S1"]
    if field.kind is _FieldKind.ENUM:
        if not field.enum_values:
            raise RuntimeError("enum descriptor is incomplete")
        return field.enum_values[0]
    if field.child is None:
        raise RuntimeError("object descriptor is incomplete")
    child = _template_object(field.child)
    if field.kind is _FieldKind.NULLABLE_OBJECT:
        return child
    if field.kind is _FieldKind.OBJECT_ARRAY:
        return [child]
    raise RuntimeError("unsupported field descriptor")


def _schema_object(descriptor: _ObjectDescriptor) -> dict[str, JsonValue]:
    """从 object descriptor 生成 strict object JSON Schema。

    :param descriptor: immutable object descriptor。
    :returns: fresh strict schema object。
    """

    return {
        "type": "object",
        "properties": {
            field.name: _schema_value(field) for field in descriptor.fields
        },
        "required": [field.name for field in descriptor.fields],
        "additionalProperties": False,
    }


def _schema_value(field: _FieldDescriptor) -> JsonValue:
    """从字段 descriptor 生成对应 JSON Schema。

    :param field: immutable field descriptor。
    :returns: fresh field schema。
    :raises RuntimeError: descriptor 自身不完整时抛出。
    """

    if field.kind is _FieldKind.CONST_TEXT:
        if field.const_text is None:
            raise RuntimeError("const text descriptor is incomplete")
        return {"type": "string", "const": field.const_text}
    if field.kind is _FieldKind.TEXT:
        return {"type": "string", "minLength": 1}
    if field.kind is _FieldKind.TEXT_ARRAY:
        result: dict[str, JsonValue] = {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        }
        if not field.allow_empty_array:
            result["minItems"] = 1
        return result
    if field.kind is _FieldKind.ENUM:
        return {"type": "string", "enum": list(field.enum_values)}
    if field.child is None:
        raise RuntimeError("object descriptor is incomplete")
    child = _schema_object(field.child)
    if field.kind is _FieldKind.NULLABLE_OBJECT:
        return {"anyOf": [child, {"type": "null"}]}
    if field.kind is _FieldKind.OBJECT_ARRAY:
        return {"type": "array", "items": child}
    raise RuntimeError("unsupported field descriptor")


def _prompt_rules_object(descriptor: _ObjectDescriptor) -> dict[str, JsonValue]:
    """从 object descriptor 生成精简、业务可读的字段规则。

    :param descriptor: immutable object descriptor。
    :returns: exact required fields 与各字段简明类型规则。
    """

    return {
        "required_fields": [field.name for field in descriptor.fields],
        "unknown_fields": "forbidden",
        "field_rules": {
            field.name: _prompt_field_rule(field) for field in descriptor.fields
        },
    }


def _prompt_field_rule(field: _FieldDescriptor) -> JsonValue:
    """从字段 descriptor 生成简明类型/允许值规则。

    :param field: immutable field descriptor。
    :returns: 不含 formal JSON Schema 关键字树的 concise rule。
    :raises RuntimeError: descriptor 自身不完整时抛出。
    """

    if field.kind is _FieldKind.CONST_TEXT:
        if field.const_text is None:
            raise RuntimeError("const text descriptor is incomplete")
        return {"type": "string", "allowed_value": field.const_text}
    if field.kind is _FieldKind.TEXT:
        return {"type": "non-empty string"}
    if field.kind is _FieldKind.TEXT_ARRAY:
        return {
            "type": (
                "array of unique non-empty strings; may be empty"
                if field.allow_empty_array
                else "non-empty array of unique non-empty strings"
            )
        }
    if field.kind is _FieldKind.ENUM:
        return {
            "type": "string",
            "allowed_values": list(field.enum_values),
        }
    if field.child is None:
        raise RuntimeError("object descriptor is incomplete")
    child_rules = _prompt_rules_object(field.child)
    if field.kind is _FieldKind.NULLABLE_OBJECT:
        return {"type": "object or null", "object_rules": child_rules}
    if field.kind is _FieldKind.OBJECT_ARRAY:
        return {"type": "array of objects", "item_rules": child_rules}
    raise RuntimeError("unsupported field descriptor")


def _strict_object_pairs(
    pairs: list[tuple[str, JsonValue]],
) -> dict[str, JsonValue]:
    """拒绝 duplicate key 后构造 JSON object。

    :param pairs: JSON decoder 提供的原始 key/value pairs。
    :returns: 无重复 key 的 object。
    :raises ValueError: 任一 key 重复时抛出。
    """

    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate_json_key: {key}")
        result[key] = value
    return result


def _exact_object(
    value: JsonValue,
    descriptor: _ObjectDescriptor,
    *,
    path: str,
) -> Mapping[str, JsonValue]:
    """校验 JSON object 类型与 exact keys。

    :param value: 待校验 JSON 值。
    :param descriptor: 结构真源。
    :param path: 自解释 JSON path。
    :returns: 校验后的 mapping。
    :raises ValueError: 类型、未知 key 或缺 key 时抛出。
    """

    if not isinstance(value, Mapping):
        raise ValueError(f"invalid_field_type: {path}")
    expected = frozenset(field.name for field in descriptor.fields)
    actual = frozenset(value.keys())
    unknown = sorted(actual - expected)
    if unknown:
        raise ValueError(f"unknown_json_key: {path}.{unknown[0]}")
    missing = sorted(expected - actual)
    if missing:
        raise ValueError(f"missing_required_key: {path}.{missing[0]}")
    return value


def _required_text(
    mapping: Mapping[str, JsonValue],
    key: str,
    *,
    path: str,
) -> str:
    """读取非空字符串字段。

    :param mapping: 已校验 object。
    :param key: 字段名。
    :param path: JSON path。
    :returns: 非空字符串。
    :raises ValueError: 类型非法或文本为空时抛出。
    """

    value = mapping[key]
    if not isinstance(value, str):
        raise ValueError(f"invalid_field_type: {path}")
    if not value.strip():
        raise ValueError(f"blank_required_text: {path}")
    return value


def _required_array(
    mapping: Mapping[str, JsonValue],
    key: str,
    *,
    path: str,
) -> list[JsonValue]:
    """读取 JSON array 字段。

    :param mapping: 已校验 object。
    :param key: 字段名。
    :param path: JSON path。
    :returns: JSON value list。
    :raises ValueError: 字段不是 array 时抛出。
    """

    value = mapping[key]
    if not isinstance(value, list):
        raise ValueError(f"invalid_field_type: {path}")
    return value


def _required_text_tuple(
    mapping: Mapping[str, JsonValue],
    key: str,
    *,
    path: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    """读取字符串 array 并拒绝非字符串、空项与重复项。

    :param mapping: 已校验 object。
    :param key: 字段名。
    :param path: JSON path。
    :param allow_empty: 是否允许空 array。
    :returns: 唯一字符串 tuple。
    :raises ValueError: array、item 或唯一性不合法时抛出。
    """

    values = _required_array(mapping, key, path=path)
    result: list[str] = []
    for index, item in enumerate(values):
        if not isinstance(item, str):
            raise ValueError(f"invalid_field_type: {path}[{index}]")
        if not item.strip():
            raise ValueError(f"blank_required_text: {path}[{index}]")
        if item in result:
            raise ValueError(f"duplicate_source_label: {path}[{index}]")
        result.append(item)
    if not allow_empty and not result:
        raise ValueError(f"blank_required_text: {path}")
    return tuple(result)


def _descriptor_field(
    descriptor: _ObjectDescriptor,
    name: str,
) -> _FieldDescriptor:
    """从 immutable object descriptor 读取唯一字段规则。

    :param descriptor: 字段所属 object descriptor。
    :param name: 字段名。
    :returns: 匹配的 immutable field descriptor。
    :raises RuntimeError: structure owner 缺少字段时抛出。
    """

    for field in descriptor.fields:
        if field.name == name:
            return field
    raise RuntimeError(f"structure descriptor is missing field: {name}")


def _parse_summary(value: JsonValue) -> CompactSessionSummaryV3 | None:
    """解析 required nullable session summary。

    :param value: ``session_summary`` 字段值。
    :returns: typed summary 或 ``None``。
    :raises ValueError: nested shape 非法时抛出。
    """

    if value is None:
        return None
    data = _exact_object(value, _SUMMARY, path="$.session_summary")
    return CompactSessionSummaryV3(
        text=_required_text(data, "text", path="$.session_summary.text"),
        source_labels=_required_text_tuple(
            data,
            "source_labels",
            path="$.session_summary.source_labels",
            allow_empty=_descriptor_field(
                _SUMMARY,
                "source_labels",
            ).allow_empty_array,
        ),
    )


def _parse_fact(value: JsonValue, index: int) -> CompactEvidenceFactV3:
    """解析单一 evidence fact。

    :param value: fact JSON 值。
    :param index: array index。
    :returns: typed fact。
    :raises ValueError: nested shape 非法时抛出。
    """

    path = f"$.evidence_facts[{index}]"
    data = _exact_object(value, _FACT, path=path)
    return CompactEvidenceFactV3(
        claim=_required_text(data, "claim", path=f"{path}.claim"),
        support_labels=_required_text_tuple(
            data,
            "support_labels",
            path=f"{path}.support_labels",
            allow_empty=_descriptor_field(
                _FACT,
                "support_labels",
            ).allow_empty_array,
        ),
        context_labels=_required_text_tuple(
            data,
            "context_labels",
            path=f"{path}.context_labels",
            allow_empty=_descriptor_field(
                _FACT,
                "context_labels",
            ).allow_empty_array,
        ),
    )


def _parse_anchor(value: JsonValue, index: int) -> CompactAnswerAnchorV3:
    """解析单一 answer anchor。

    :param value: anchor JSON 值。
    :param index: array index。
    :returns: typed anchor。
    :raises ValueError: nested shape 非法时抛出。
    """

    path = f"$.answer_anchors[{index}]"
    data = _exact_object(value, _ANCHOR, path=path)
    return CompactAnswerAnchorV3(
        title=_required_text(data, "title", path=f"{path}.title"),
        detail=_required_text(data, "detail", path=f"{path}.detail"),
        source_labels=_required_text_tuple(
            data,
            "source_labels",
            path=f"{path}.source_labels",
            allow_empty=_descriptor_field(
                _ANCHOR,
                "source_labels",
            ).allow_empty_array,
        ),
    )


def _parse_intent(value: JsonValue, index: int) -> CompactForwardIntentV3:
    """解析单一 forward intent。

    :param value: intent JSON 值。
    :param index: array index。
    :returns: typed intent。
    :raises ValueError: nested shape 或 status 非法时抛出。
    """

    path = f"$.forward_intents[{index}]"
    data = _exact_object(value, _INTENT, path=path)
    status_text = _required_text(data, "status", path=f"{path}.status")
    try:
        status = CompactForwardIntentStatusV3(status_text)
    except ValueError as exc:
        raise ValueError(f"invalid_enum_value: {path}.status") from exc
    return CompactForwardIntentV3(
        intent_type=_required_text(
            data,
            "intent_type",
            path=f"{path}.intent_type",
        ),
        text=_required_text(data, "text", path=f"{path}.text"),
        status=status,
        source_labels=_required_text_tuple(
            data,
            "source_labels",
            path=f"{path}.source_labels",
            allow_empty=_descriptor_field(
                _INTENT,
                "source_labels",
            ).allow_empty_array,
        ),
    )


def _parse_reference(
    value: JsonValue,
    index: int,
) -> CompactReferenceContinuityV3:
    """解析单一 reference continuity item。

    :param value: reference JSON 值。
    :param index: array index。
    :returns: typed reference item。
    :raises ValueError: nested shape 非法时抛出。
    """

    path = f"$.reference_continuity[{index}]"
    data = _exact_object(value, _REFERENCE, path=path)
    return CompactReferenceContinuityV3(
        text=_required_text(data, "text", path=f"{path}.text"),
        reason=_required_text(data, "reason", path=f"{path}.reason"),
        source_labels=_required_text_tuple(
            data,
            "source_labels",
            path=f"{path}.source_labels",
            allow_empty=_descriptor_field(
                _REFERENCE,
                "source_labels",
            ).allow_empty_array,
        ),
    )


__all__ = [
    "COMPACT_OUTPUT_JSON_SCHEMA_NAME_V3",
    "compact_output_json_schema_digest_v3",
    "compact_output_json_schema_v3",
    "compact_output_prompt_rules_v3",
    "compact_output_template_v3",
    "parse_compact_candidate_v3",
]
