"""Host 测试专用 deterministic context compactor。

本模块位于 tests 包下，只允许测试显式注入一个稳定 compactor。生产代码
不得导入 tests helper；真实生产装配必须显式提供 ``ContextCompactor``。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from dayu.contracts.cancellation import CancellationToken
from dayu.contracts.json_value import JsonValue
from dayu.host.compaction import (
    CompactInputRange,
    CompactMaterialSection,
    CompactionCandidate,
    CompactionRequest,
    ContextCompactor,
    PinnedPatchOperation,
    PinnedStringTupleFieldPatch,
    PinnedTextFieldPatch,
)
from dayu.host.llm_compaction import _candidate_from_final_answer

_FAKE_COMPACTION_SYSTEM_PROMPT = (
    "Deterministic fake context compactor preserving current input and accepted facts."
)
_FAKE_SUMMARY_TOKEN_ESTIMATE = 120
_HARD_THRESHOLD_ACCEPTANCE_MARGIN_TOKENS = 1
_MIN_COMPACTED_CONTEXT_BUDGET_TOKENS = 0


class FakeContextCompactor(ContextCompactor):
    """Deterministic context compactor。

    该实现只根据 typed request 构造稳定 candidate，不调用 LLM，不访问外部
    状态，不应作为生产默认 compactor。
    """

    async def compact(
        self, request: CompactionRequest, cancellation_token: CancellationToken
    ) -> CompactionCandidate:
        """生成 deterministic compaction candidate。

        :param request: Host 构造的 compaction 请求。
        :param cancellation_token: Host 注入的取消 token。
        :returns: deterministic compaction candidate。
        :raises TypeError: ``request`` 类型非法时抛出。
        :raises RuntimeError: token 已取消时抛出。
        """

        if not isinstance(request, CompactionRequest):
            raise TypeError("request must be CompactionRequest")
        if cancellation_token.is_cancelled():
            raise RuntimeError("compaction cancelled")

        proposal_json = fake_compaction_proposal_from_material_json(
            _json_object(request.llm_material_json(), field_name="material")
        )
        candidate = _candidate_from_final_answer(request, proposal_json)
        return _fake_candidate_ids(request, candidate)


def fake_compaction_proposal_from_material_json(
    material_json: Mapping[str, JsonValue],
) -> str:
    """按 LLM-facing material labels 构造 deterministic fake proposal JSON。

    本 helper 只读取 material JSON 中的 prompt-local labels 与文本，不读取
    canonical Host refs。生产 ``LLMContextCompactor`` 解析该 JSON 后再由 Host
    provenance map 映射回 canonical refs。

    :param material_json: ``CompactionRequest.llm_material_json()`` 输出。
    :returns: strict JSON proposal 文本。
    :raises TypeError: material JSON 形状非法时抛出。
    :raises KeyError: material JSON 缺少必要字段时抛出。
    """

    current_anchor = _json_object(
        material_json["current_input_anchor"],
        field_name="current_input_anchor",
    )
    current_label = _required_string(current_anchor, "label")
    current_text = _required_string(current_anchor, "text")
    history_labels = _material_labels(material_json, "history_input")
    evidence_labels = _material_labels(material_json, "evidence_input")
    preserved_material_labels = _unique_strings(
        (current_label, *history_labels, *evidence_labels)
    )
    proposal: dict[str, JsonValue] = {
        "episode_summary_candidate": {
            "episode_title": "Deterministic compact summary",
            "goal": current_text,
            "completed_actions": _json_string_list(
                ("preserved current turn",)
                if len(history_labels) == 0
                else (f"summarized {len(history_labels)} older raw turns",)
            ),
            "confirmed_fact_refs": [],
            "confirmed_fact_summaries": _json_string_list(
                ("no prior evidence-backed facts in fake material",)
            ),
            "user_constraints": _json_string_list(
                (f"keep-current-input:{current_label}",)
            ),
            "open_questions": _json_string_list(("continue-current-run",)),
            "next_step": "preserve current input and accepted tool facts",
            "tool_finding_labels": _json_string_list(evidence_labels),
        },
        "pinned_state_patch_candidate": {
            "current_goal": {
                "operation": PinnedPatchOperation.REPLACE.value,
                "value": current_text,
            },
            "confirmed_subjects": {
                "operation": PinnedPatchOperation.REPLACE.value,
                "value": _json_string_list(_confirmed_subject_labels(evidence_labels)),
            },
            "user_constraints": {
                "operation": PinnedPatchOperation.REPLACE.value,
                "value": _json_string_list((f"keep-current-input:{current_label}",)),
            },
            "open_questions": {
                "operation": PinnedPatchOperation.REPLACE.value,
                "value": _json_string_list(("continue-current-run",)),
            },
        },
        "evidence_backed_fact_candidates": _fact_candidate_json(material_json),
        "minimum_preserve_item_candidates": [
            {
                "item_id": "fake-preserve-current-input",
                "label": "current input",
                "text": current_text,
                "source_labels": _json_string_list((current_label,)),
                "preserve_reason": "needed_for_recent_reference",
            }
        ],
        "preservation_evidence": [
            {
                "material_labels": _json_string_list(preserved_material_labels),
                "evidence_labels": _json_string_list(evidence_labels),
                "compact_range": _compact_range_json(history_labels),
            }
        ],
        "retained_current_input_label": current_label,
        "preserved_material_labels": _json_string_list(preserved_material_labels),
        "preserved_evidence_labels": _json_string_list(evidence_labels),
        "preserved_evidence_backed_fact_refs": [],
        "dropped_ranges": [],
        "summarized_ranges": _summarized_range_json(history_labels),
    }
    return json.dumps(proposal, ensure_ascii=False, sort_keys=True)


def _fake_candidate_ids(
    request: CompactionRequest, candidate: CompactionCandidate
) -> CompactionCandidate:
    """把 label JSON 解析出的 candidate 改写为 fake helper 稳定 id。

    :param request: compaction 请求。
    :param candidate: 生产 parser 基于 label JSON 生成的 candidate。
    :returns: 保持 fake 历史 id 约定的 candidate。
    """

    fake_evidence = tuple(
        replace(
            evidence,
            evidence_id=f"fake-evidence:{request.run_id}:primary",
            memory_snapshot_cursor=request.memory_snapshot_cursor,
            compact_input_range=_range_for_request(request),
        )
        for evidence in candidate.preservation_evidence
    )
    fake_evidence_refs = tuple(
        evidence.evidence_id for evidence in fake_evidence
    )
    return replace(
        candidate,
        candidate_id=f"fake-compact:{request.run_id}",
        episode_summary_candidate=replace(
            candidate.episode_summary_candidate,
            candidate_id=f"fake-summary:{request.run_id}",
            episode_title=f"Session {request.session_id} compact summary",
            completed_actions=_completed_actions(request),
            confirmed_fact_refs=request.evidence_backed_fact_refs,
            confirmed_fact_summaries=_confirmed_fact_summaries(request),
            evidence_refs=fake_evidence_refs,
        ),
        pinned_state_patch_candidate=replace(
            candidate.pinned_state_patch_candidate,
            candidate_id=f"fake-pinned-patch:{request.run_id}",
            current_goal=_text_patch_with_evidence_refs(
                candidate.pinned_state_patch_candidate.current_goal,
                fake_evidence_refs,
            ),
            confirmed_subjects=_tuple_patch_with_evidence_refs(
                candidate.pinned_state_patch_candidate.confirmed_subjects,
                fake_evidence_refs,
                value=_confirmed_subjects(request),
            ),
            user_constraints=_tuple_patch_with_evidence_refs(
                candidate.pinned_state_patch_candidate.user_constraints,
                fake_evidence_refs,
                value=_user_constraints(request),
            ),
            open_questions=_tuple_patch_with_evidence_refs(
                candidate.pinned_state_patch_candidate.open_questions,
                fake_evidence_refs,
                value=("continue-current-run",),
            ),
        ),
        preservation_evidence=fake_evidence,
        evidence_backed_fact_candidates=tuple(
            replace(fact, candidate_id=f"fake-fact:{request.run_id}:{index}")
            for index, fact in enumerate(candidate.evidence_backed_fact_candidates)
        ),
        minimum_preserve_item_candidates=tuple(
            replace(
                item,
                item_id=f"fake-preserve:{request.run_id}:current-input",
            )
            for item in candidate.minimum_preserve_item_candidates
        ),
        preserved_evidence_backed_fact_refs=request.evidence_backed_fact_refs,
        summarized_ranges=_summarized_ranges(request),
        budget_after_compact=_budget_after_compact(request),
    )


def _text_patch_with_evidence_refs(
    patch: PinnedTextFieldPatch, evidence_refs: tuple[str, ...]
) -> PinnedTextFieldPatch:
    """替换文本 patch 的 preservation evidence refs。

    :param patch: 原始文本 patch。
    :param evidence_refs: fake preservation evidence refs。
    :returns: 更新后的文本 patch。
    """

    return replace(patch, evidence_refs=evidence_refs)


def _tuple_patch_with_evidence_refs(
    patch: PinnedStringTupleFieldPatch,
    evidence_refs: tuple[str, ...],
    *,
    value: tuple[str, ...],
) -> PinnedStringTupleFieldPatch:
    """替换 tuple patch 的值与 preservation evidence refs。

    :param patch: 原始 tuple patch。
    :param evidence_refs: fake preservation evidence refs。
    :param value: fake helper 稳定值。
    :returns: 更新后的 tuple patch。
    """

    return replace(patch, value=value, evidence_refs=evidence_refs)


def _material_labels(
    material_json: Mapping[str, JsonValue], section_key: str
) -> tuple[str, ...]:
    """读取 material section 的 prompt-local labels。

    :param material_json: LLM-facing material JSON。
    :param section_key: section 字段名。
    :returns: label tuple。
    :raises TypeError: section 不是 JSON array 或 block 不是 JSON object 时抛出。
    :raises KeyError: block 缺少 label 时抛出。
    """

    values = _json_array(material_json[section_key], field_name=section_key)
    labels: list[str] = []
    for index, item in enumerate(values):
        block = _json_object(item, field_name=f"{section_key}[{index}]")
        labels.append(_required_string(block, "label"))
    return tuple(labels)


def _fact_candidate_json(material_json: Mapping[str, JsonValue]) -> list[JsonValue]:
    """从 evidence material labels 构造 fact candidate JSON。

    :param material_json: LLM-facing material JSON。
    :returns: JSON array。
    :raises TypeError: evidence_input 形状非法时抛出。
    :raises KeyError: evidence block 缺少字段时抛出。
    """

    values = _json_array(
        material_json["evidence_input"],
        field_name=CompactMaterialSection.EVIDENCE_INPUT.value,
    )
    candidates: list[JsonValue] = []
    for index, item in enumerate(values):
        block = _json_object(item, field_name=f"evidence_input[{index}]")
        label = _required_string(block, "label")
        raw_result = _required_string(block, "result_text")
        candidates.append(
            {
                "candidate_id": f"fake-fact-candidate-{index + 1}",
                "claim_text": f"Canonical evidence material: {raw_result}",
                "evidence_kind": "observed_value",
                "evidence_labels": _json_string_list((label,)),
                "attributes": {},
            }
        )
    return candidates


def _compact_range_json(history_labels: tuple[str, ...]) -> JsonValue:
    """构造 compact_range JSON。

    :param history_labels: history section labels。
    :returns: compact_range JSON；无 history 时为 ``None``。
    """

    if len(history_labels) == 0:
        return None
    return {
        "range_ref": "fake-range-older-raw-turns",
        "start_material_label": history_labels[0],
        "end_material_label": history_labels[-1],
    }


def _summarized_range_json(history_labels: tuple[str, ...]) -> list[JsonValue]:
    """构造 summarized_ranges JSON。

    :param history_labels: history section labels。
    :returns: summarized_ranges JSON array。
    """

    compact_range = _compact_range_json(history_labels)
    if compact_range is None:
        return []
    return [compact_range]


def _confirmed_subject_labels(evidence_labels: tuple[str, ...]) -> tuple[str, ...]:
    """构造 label-only confirmed subjects。

    :param evidence_labels: evidence material labels。
    :returns: subject label tuple。
    """

    if len(evidence_labels) == 0:
        return ("subject:current-input",)
    return tuple(f"subject:{label}" for label in evidence_labels)


def _unique_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    """按输入顺序去重字符串。

    :param values: 待去重字符串。
    :returns: 去重后的 tuple。
    """

    return tuple(dict.fromkeys(values))


def _json_string_list(values: tuple[str, ...]) -> list[JsonValue]:
    """把字符串 tuple 转为 JSON array。

    :param values: 字符串 tuple。
    :returns: JSON array。
    """

    return [value for value in values]


def _json_object(value: JsonValue, *, field_name: str) -> Mapping[str, JsonValue]:
    """校验 JSON 值为 object。

    :param value: JSON 值。
    :param field_name: 字段名。
    :returns: JSON object。
    :raises TypeError: 值不是 object 时抛出。
    """

    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be JSON object")
    return cast(Mapping[str, JsonValue], value)


def _json_array(value: JsonValue, *, field_name: str) -> tuple[JsonValue, ...]:
    """校验 JSON 值为 array。

    :param value: JSON 值。
    :param field_name: 字段名。
    :returns: JSON array tuple。
    :raises TypeError: 值不是 array 时抛出。
    """

    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be JSON array")
    return tuple(value)


def _required_string(source: Mapping[str, JsonValue], key: str) -> str:
    """读取必填 JSON string。

    :param source: JSON object。
    :param key: 字段名。
    :returns: 字符串值。
    :raises KeyError: 字段缺失时抛出。
    :raises TypeError: 字段不是 string 时抛出。
    """

    value = source[key]
    if not isinstance(value, str):
        raise TypeError(f"{key} must be string")
    return value


def _range_for_request(request: CompactionRequest) -> CompactInputRange | None:
    """根据请求构造输入范围。

    :param request: compaction 请求。
    :returns: 输入范围；输入为空时为 ``None``。
    """

    if len(request.material_source_refs) == 0:
        return None
    return CompactInputRange(
        range_ref=f"fake-range:{request.run_id}:all-inputs",
        start_input_ref=request.material_source_refs[0],
        end_input_ref=request.material_source_refs[-1],
    )


def _summarized_ranges(request: CompactionRequest) -> tuple[CompactInputRange, ...]:
    """构造被摘要输入范围。

    :param request: compaction 请求。
    :returns: summarized ranges。
    """

    if len(request.older_raw_turn_refs) == 0:
        return ()
    return (
        CompactInputRange(
            range_ref=f"fake-range:{request.run_id}:older-raw-turns",
            start_input_ref=request.older_raw_turn_refs[0],
            end_input_ref=request.older_raw_turn_refs[-1],
        ),
    )


def _confirmed_fact_summaries(request: CompactionRequest) -> tuple[str, ...]:
    """构造 confirmed fact summaries。

    :param request: compaction 请求。
    :returns: confirmed fact summaries。
    """

    if len(request.evidence_backed_fact_refs) == 0:
        return ("no evidence-backed facts in input",)
    return tuple(
        f"evidence-backed:{fact_ref}"
        for fact_ref in request.evidence_backed_fact_refs
    )


def _completed_actions(request: CompactionRequest) -> tuple[str, ...]:
    """构造 completed actions 摘要。

    :param request: compaction 请求。
    :returns: completed actions。
    """

    if len(request.older_raw_turn_refs) == 0:
        return ("preserved current turn",)
    return (f"summarized {len(request.older_raw_turn_refs)} older raw turns",)


def _confirmed_subjects(request: CompactionRequest) -> tuple[str, ...]:
    """构造 pinned confirmed subjects。

    :param request: compaction 请求。
    :returns: confirmed subjects。
    """

    if len(request.evidence_backed_fact_refs) > 0:
        return tuple(
            f"subject:{fact_ref}" for fact_ref in request.evidence_backed_fact_refs
        )
    return (f"subject:{request.current_input_ref}",)


def _user_constraints(request: CompactionRequest) -> tuple[str, ...]:
    """构造用户约束摘要。

    :param request: compaction 请求。
    :returns: 用户约束摘要。
    """

    return (f"keep-current-input:{request.current_input_ref}",)


def _budget_after_compact(request: CompactionRequest) -> int:
    """按真实 LLM compactor 语义估算 compact 后预算并约束在 hard threshold 内。

    :param request: compaction 请求。
    :returns: compact 后 token 估算。
    """

    estimated_budget = (
        request.budget_before_compact.estimated_input_tokens
        + _FAKE_SUMMARY_TOKEN_ESTIMATE
        + len(request.canonical_evidence_refs)
        + len(request.evidence_backed_fact_refs)
        + len(_FAKE_COMPACTION_SYSTEM_PROMPT)
    )
    return _cap_budget_within_hard_threshold(
        estimated_budget,
        hard_threshold_tokens=request.budget_before_compact.hard_threshold_tokens,
    )


def _cap_budget_within_hard_threshold(
    estimated_budget_tokens: int, *, hard_threshold_tokens: int
) -> int:
    """将 fake candidate 预算约束到 Host hard-threshold 可接受区间。

    Fake compactor 是测试 deterministic compactor。它复用真实 compactor 的保守
    估算作为语义基础，但不能生成会被 Host hard-threshold recheck 拒绝的
    accepted candidate。若输入 hard threshold 非正，非负 candidate 不可能满足
    ``budget < hard_threshold``，因此只返回非负下界，避免构造非法负预算。

    :param estimated_budget_tokens: 原始 compact 后 token 估算。
    :param hard_threshold_tokens: Host hard threshold token 数。
    :returns: 非负且在可表达时小于 hard threshold 的 token 估算。
    """

    if hard_threshold_tokens <= _MIN_COMPACTED_CONTEXT_BUDGET_TOKENS:
        return _MIN_COMPACTED_CONTEXT_BUDGET_TOKENS
    accepted_budget_ceiling = (
        hard_threshold_tokens - _HARD_THRESHOLD_ACCEPTANCE_MARGIN_TOKENS
    )
    if accepted_budget_ceiling < _MIN_COMPACTED_CONTEXT_BUDGET_TOKENS:
        return _MIN_COMPACTED_CONTEXT_BUDGET_TOKENS
    return min(estimated_budget_tokens, accepted_budget_ceiling)


__all__ = ["FakeContextCompactor", "fake_compaction_proposal_from_material_json"]
