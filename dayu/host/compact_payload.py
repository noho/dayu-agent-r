"""Host compact payload 解析辅助。

本模块集中承载 ``CONTEXT_COMPACTED`` payload 中稳定字段的宽容读取逻辑，
供 dispatch governance 与 RunInputBuilder 复用，避免两侧各自解释同一
payload schema。
"""

from __future__ import annotations

from collections.abc import Mapping

from dayu.contracts.json_value import JsonValue

_FIELD_PRESERVED_FACT_REFS = "preserved_fact_refs"
_FIELD_CANONICAL_EVIDENCE_REFS = "canonical_evidence_refs"
_FIELD_EVIDENCE_BACKED_FACT_REFS = "evidence_backed_fact_refs"


def optional_text_list_field(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[str, ...]:
    """从 JSON mapping 中读取可选文本列表字段。

    :param payload: JSON payload 映射。
    :param field_name: 待读取字段名。
    :returns: 去除空字符串后的文本 tuple；字段缺失或非法时返回空 tuple。
    """

    value = payload.get(field_name)
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip() != "":
            result.append(item)
    return tuple(result)


def preserved_canonical_evidence_refs(
    payload: Mapping[str, JsonValue],
) -> tuple[str, ...]:
    """读取 compact payload 中已 preserved 的 canonical evidence refs。

    :param payload: ``CONTEXT_COMPACTED`` payload。
    :returns: accepted canonical evidence refs；字段缺失或非法时为空 tuple。
    """

    preserved = payload.get(_FIELD_PRESERVED_FACT_REFS)
    if not isinstance(preserved, Mapping):
        return ()
    return optional_text_list_field(preserved, _FIELD_CANONICAL_EVIDENCE_REFS)


def preserved_fact_refs_summary(payload: Mapping[str, JsonValue]) -> str:
    """渲染 compact payload 中 preserved fact refs 的稳定摘要文本。

    :param payload: ``CONTEXT_COMPACTED`` payload。
    :returns: compact artifact message 使用的稳定摘要文本。
    """

    preserved = payload.get(_FIELD_PRESERVED_FACT_REFS)
    if not isinstance(preserved, Mapping):
        return ""
    canonical_evidence_refs = optional_text_list_field(
        preserved, _FIELD_CANONICAL_EVIDENCE_REFS
    )
    evidence_backed_fact_refs = optional_text_list_field(
        preserved, _FIELD_EVIDENCE_BACKED_FACT_REFS
    )
    parts = [
        f"canonical_evidence_refs={','.join(canonical_evidence_refs)}",
        f"evidence_backed_fact_refs={','.join(evidence_backed_fact_refs)}",
    ]
    return "; ".join(parts)
