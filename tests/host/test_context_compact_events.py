"""Host context compact canonical event payload 测试。"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

import dayu.host.context_events as context_events_module
from dayu.contracts.json_value import JsonValue
from dayu.engine.contracts.runner_identity import (
    ProviderRequestIdAvailability,
    SuccessfulRunnerResponseIdentity,
    build_runner_request_identity,
)
from dayu.host.api import HostEventClass, HostEventKind, HostTerminalStatus
from dayu.host.compaction import (
    COMPACT_INPUT_SCHEMA_V4,
    CompactAnswerAnchorV4,
    CompactAcceptedTruthV4,
    COMPACT_OUTPUT_SCHEMA_V4,
    CompactAcceptedReplacementV4,
    CompactCandidateV4,
    CompactCurrentInputV4,
    CompactEvidenceFactV4,
    CompactForwardIntentV4,
    CompactForwardIntentStatusV4,
    CompactReferenceContinuityV4,
    CompactRepresentedCoverageV4,
    CompactSessionSummaryV4,
    CompactInputV4,
    CompactSourceBoundaryEntryV4,
    CompactSourceKindV4,
)
from dayu.host.compact_payload import (
    accepted_compact_business_texts,
    accepted_evidence_mapping_refs,
    compact_artifact_payload_ref,
    parse_context_compacted_semantic_payload,
)
from dayu.host.context_budget import ContextBudgetDecision
from dayu.host.context_events import (
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    build_context_compaction_attempt_rejected_payload,
    build_context_compacted_payload,
    build_context_compaction_failed_payload,
    build_context_compaction_requested_payload,
    parse_context_compacted_terminal_binding,
    parse_context_compaction_attempt_rejected_terminal_binding,
    parse_successful_runner_response_identity,
    validate_context_compaction_attempt_rejected_payload,
    validate_context_compacted_payload,
    validate_context_compaction_failed_payload,
    validate_context_compaction_requested_payload,
)
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.context_governance import (
    accept_compact_candidate_v4,
    compact_output_caps_v4_from_memory_policy,
)
from dayu.host.context_events import CompactorProposalManifestReference
from dayu.host.durable.codec import format_utc_timestamp, sha256_digest_json
from dayu.host.durable.event_log import EventClass, EventLogRow
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    PayloadStoragePolicy,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.read_api import _host_event_from_row
from dayu.host.memory import default_memory_projection_policy
from tests.host.fake_compaction import accepted_truth_for_candidate

_DIGEST_A = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_DIGEST_B = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_FIELD_FALLBACK_POLICY_DECISION = "fallback_policy_decision"
_FIELD_FALLBACK_INPUT_WINDOW = "fallback_input_window"
_FIELD_FALLBACK_INPUT_DIGEST = "fallback_input_digest"
_FIELD_FALLBACK_BUDGET_RESULT = "fallback_budget_result"


def test_context_events_owner_exports_compactor_manifest_reference() -> None:
    """Context event owner 必须直接导出 compactor manifest 引用契约。

    :returns: ``None``。
    :raises AssertionError: manifest 引用类型未由 owner 模块导出时抛出。
    """

    assert "CompactorProposalManifestReference" in context_events_module.__all__
    assert "parse_successful_runner_response_identity" in (
        context_events_module.__all__
    )


def test_successful_response_public_parser_roundtrips_canonical_identity() -> None:
    """公开 strict parser 与 canonical compacted payload 使用同一 identity shape。

    :returns: ``None``。
    :raises AssertionError: parser 与 terminal binding 不同源时抛出。
    """

    payload = _valid_compacted_payload()
    identity_payload = cast(
        Mapping[str, JsonValue],
        payload["successful_response_identity"],
    )

    identity = parse_successful_runner_response_identity(identity_payload)
    binding = parse_context_compacted_terminal_binding(payload)

    assert binding.successful_response_identity == identity
    assert identity.effective_provider == "test-compactor"
    assert identity.effective_model == "test-compactor-model"
    assert identity.provider_request_id_availability is (
        ProviderRequestIdAvailability.UNAVAILABLE
    )
    assert identity.provider_request_id is None


def test_successful_response_public_parser_rejects_secret_like_extra_field() -> None:
    """canonical identity 白名单拒绝 header/credential/raw payload 扩展。

    :returns: ``None``。
    :raises AssertionError: secret-like extra field 未被拒绝时抛出。
    """

    payload = _valid_compacted_payload()
    identity_payload = dict(
        cast(
            Mapping[str, JsonValue],
            payload["successful_response_identity"],
        )
    )
    identity_payload["authorization"] = "Bearer must-not-leak"

    with pytest.raises(ValueError, match="unexpected payload fields"):
        parse_successful_runner_response_identity(identity_payload)


def test_attempt_rejected_terminal_parser_preserves_no_success_null() -> None:
    """no-success canonical rejection 由 event owner 解析为 typed null identity。

    :returns: ``None``。
    :raises AssertionError: no-success identity 或 manifest binding 错误时抛出。
    """

    manifest_reference = _proposal_manifest_reference(
        operation_id="operation-no-success",
        attempt_number=1,
        compactor_engine_run_id="compactor-run-no-success",
        manifest_payload_ref="payload-manifest-no-success",
        manifest_digest=_DIGEST_A,
    )
    payload = build_context_compaction_attempt_rejected_payload(
        operation_id="operation-no-success",
        attempt_number=1,
        failure_category="cancellation_requested",
        repairable=False,
        runner_attempt_summary_refs=("runner-attempt-1",),
        diagnostic_refs=("diagnostic-1",),
        next_policy_decision="stop",
        budget_after_attempted_compact=None,
        successful_response_identity=None,
        proposal_manifest_reference=manifest_reference,
    )

    binding = parse_context_compaction_attempt_rejected_terminal_binding(payload)

    assert binding.proposal_manifest_ref == "payload-manifest-no-success"
    assert binding.proposal_manifest_digest == _DIGEST_A
    assert binding.successful_response_identity is None


def _successful_response_identity(
    *,
    operation_id: str,
    attempt_number: int,
    compactor_engine_run_id: str,
) -> SuccessfulRunnerResponseIdentity:
    """构造与当前 durable event fixture 同源的成功响应身份。

    :param operation_id: 当前 compaction operation id。
    :param attempt_number: 当前 proposal attempt number。
    :param compactor_engine_run_id: 当前 manifest 显式绑定的 Engine run id。
    :returns: deterministic、非敏感且 event-unique 的 typed identity。
    :raises ValueError: identity 字段非法时抛出。
    """

    return SuccessfulRunnerResponseIdentity(
        effective_provider="test-compactor",
        effective_model="test-compactor-model",
        runner_request_identity=build_runner_request_identity(
            run_id=compactor_engine_run_id,
            attempt_id=None,
            execution_id=None,
            iteration_id=f"{operation_id}:attempt:{attempt_number}:iteration",
            iteration_index=0,
            runner_call_index=1,
        ),
        provider_request_id_availability=(ProviderRequestIdAvailability.UNAVAILABLE),
        provider_request_id=None,
    )


def _proposal_manifest_reference(
    *,
    operation_id: str,
    attempt_number: int,
    compactor_engine_run_id: str,
    manifest_payload_ref: str,
    manifest_digest: str,
) -> CompactorProposalManifestReference:
    """构造与当前 durable event fixture 同源的 typed manifest reference。

    :param operation_id: 当前 compaction operation id。
    :param attempt_number: 当前 proposal attempt number。
    :param compactor_engine_run_id: 当前 manifest 显式绑定的 Engine run id。
    :param manifest_payload_ref: 当前 fixture 的 manifest payload ref。
    :param manifest_digest: 当前 fixture 的 manifest digest。
    :returns: 与 operation/attempt/run 显式绑定的 manifest reference。
    :raises ValueError: manifest binding 字段非法时抛出。
    """

    return CompactorProposalManifestReference(
        manifest_event_id=f"manifest-event:{operation_id}:{attempt_number}",
        manifest_payload_ref=manifest_payload_ref,
        manifest_digest=manifest_digest,
        compactor_input_projection_ref=(f"projection:{operation_id}:{attempt_number}"),
        compactor_input_projection_digest=_DIGEST_B,
        compaction_operation_id=operation_id,
        compaction_attempt_number=attempt_number,
        compactor_engine_run_id=compactor_engine_run_id,
    )


def test_requested_payload_builder_accepts_proactive_without_attempt() -> None:
    """proactive requested payload 可以没有 attempt / execution。"""

    payload = build_context_compaction_requested_payload(
        operation_id="event-context-requested-1",
        max_compaction_attempts_per_operation=5,
        trigger_source=ContextCompactionTriggerSource.PROACTIVE,
        budget_reason="soft_threshold",
        budget_snapshot_ref="budget:snapshot-1",
        input_snapshot_cursor=12,
        estimator_digest=_DIGEST_A,
        policy_ref="policy:context",
        provider_request_id=None,
        provider_error_ref=None,
        attempt_id=None,
        execution_id=None,
        client_correlation_id=None,
        frozen_material_list_digest=_DIGEST_B,
        frozen_material_refs=("event-input-1",),
    )

    validate_context_compaction_requested_payload(payload)
    assert payload["trigger_source"] == "proactive"


def test_requested_payload_rejects_missing_required_fields() -> None:
    """requested validator 拒绝缺少顶层必填字段的 payload。"""

    with pytest.raises(ValueError, match="operation_id is required"):
        validate_context_compaction_requested_payload({})


def test_requested_payload_rejects_untyped_metadata_for_required_fields() -> None:
    """required fields 放进 metadata bag 不会被 validator 当成 typed payload。"""

    payload: dict[str, JsonValue] = {
        "metadata": {
            "trigger_source": "proactive",
            "budget_reason": "soft_threshold",
        }
    }

    with pytest.raises(ValueError, match="operation_id is required"):
        validate_context_compaction_requested_payload(payload)


def test_reactive_requested_requires_attempt_and_execution() -> None:
    """reactive requested payload 必须带 attempt / execution identity。"""

    payload = dict(
        build_context_compaction_requested_payload(
            operation_id="event-context-requested-2",
            max_compaction_attempts_per_operation=5,
            trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            budget_reason="provider_overflow",
            budget_snapshot_ref="budget:snapshot-1",
            input_snapshot_cursor=12,
            estimator_digest=_DIGEST_A,
            policy_ref="policy:context",
            provider_request_id="provider-request-1",
            provider_error_ref="provider-error-1",
            attempt_id=None,
            execution_id=None,
            client_correlation_id=None,
            frozen_material_list_digest=_DIGEST_B,
            frozen_material_refs=("event-input-1",),
        )
    )
    payload["trigger_source"] = "reactive"

    with pytest.raises(ValueError, match="reactive compaction requires"):
        validate_context_compaction_requested_payload(payload)


def test_compacted_payload_builder_emits_required_accepted_output() -> None:
    """compacted builder 输出 accepted vNext candidate 与治理字段。"""

    payload = _valid_compacted_payload()

    validate_context_compacted_payload(payload)
    assert payload["compact_artifact_ref"] == "compact-artifact:abc"
    assert payload["accepted_attempt_number"] == 2
    assert payload["accepted_proposal_digest"] == _candidate().digest()
    assert payload["budget_after_compact"] == 512


def test_compacted_semantic_parser_roundtrips_full_typed_candidate() -> None:
    """persisted semantic parser 保留五类语义、children、ordinal、digest 与 refs。"""

    payload = _valid_compacted_payload()

    semantic = parse_context_compacted_semantic_payload(payload)

    assert semantic.accepted_proposal == _candidate()
    assert semantic.accepted_proposal_digest == _candidate().digest()
    assert semantic.accepted_evidence_mapping_refs == ("evidence:E1",)
    assert semantic.compact_artifact_ref == "compact-artifact:abc"
    assert semantic.current_input_ref == "event-user-1"
    assert semantic.compacted_source_refs == ("evidence:accepted-1",)
    assert semantic.accepted_proposal.answer_anchors[0].detail == ("Revenue increased.\nMargin also expanded.")
    assert semantic.accepted_replacement.answer_anchors[0].detail == (
        "Revenue increased.\nMargin also expanded."
    )
    assert accepted_evidence_mapping_refs(payload) == ("evidence:E1",)
    assert accepted_compact_business_texts(semantic.accepted_replacement) == (
        "Q1 review focused on revenue.",
        "Revenue increased.",
        "Revenue answer",
        "Revenue increased.\nMargin also expanded.",
        "Compare quarters next.",
        "Keep revenue comparison context.",
    )


def test_whitespace_only_candidate_anchor_is_rejected_at_typed_accept_boundary() -> None:
    """candidate typed owner 必须拒绝 whitespace-only anchor，不交给 projector 补救。

    :returns: ``None``。
    :raises AssertionError: whitespace-only title 被 typed boundary 接受时抛出。
    """

    with pytest.raises(ValueError, match="CompactAnswerAnchorV4.title"):
        CompactAnswerAnchorV4(
            title="  \n\t ",
            detail="valid detail",
            source_labels=("A1",),
        )


def test_whitespace_only_persisted_replacement_is_rejected_at_read_boundary() -> None:
    """strict persisted parser 必须拒绝 blank replacement，不 skip 或默认化。

    :returns: ``None``。
    :raises AssertionError: 持久化 whitespace-only title 被 read owner 接受时抛出。
    """

    payload = _valid_compacted_payload()
    replacement = _payload_mapping(payload["accepted_replacement"])
    anchors = _mapping_list(replacement["answer_anchors"])
    anchors[0]["title"] = " \n\t "
    replacement["answer_anchors"] = cast(list[JsonValue], anchors)
    payload["accepted_replacement"] = replacement

    with pytest.raises(ValueError, match="title"):
        parse_context_compacted_semantic_payload(payload)


def test_compact_payload_public_helpers_reject_invalid_inputs() -> None:
    """compact payload public helper 对弱类型 replacement 与非法 digest fail closed。"""

    with pytest.raises(
        TypeError,
        match="replacement must be CompactAcceptedReplacementV4",
    ):
        accepted_compact_business_texts(
            cast(CompactAcceptedReplacementV4, "bad")
        )
    with pytest.raises(ValueError, match="artifact_digest must be sha256 digest"):
        compact_artifact_payload_ref("bad")


@pytest.mark.parametrize(
    "invalid_source_boundary_refs",
    (
        [],
        ["event-user-1", "event-user-1"],
        ["event-user-1", ""],
        ["event-user-1", 7],
    ),
)
def test_compacted_semantic_parser_rejects_invalid_source_boundary_refs(
    invalid_source_boundary_refs: list[JsonValue],
) -> None:
    """persisted parser 在唯一 owner boundary 拒绝非法 source refs。

    :param invalid_source_boundary_refs: 非空、唯一文本 list contract 的反例。
    """

    payload = _valid_compacted_payload()
    payload["source_boundary_refs"] = invalid_source_boundary_refs

    with pytest.raises(ValueError, match="source_boundary_refs"):
        parse_context_compacted_semantic_payload(payload)


def test_compacted_semantic_parser_rejects_missing_source_boundary_refs() -> None:
    """persisted parser 拒绝缺失 source boundary，不提供旧 payload 兼容。"""

    payload = _valid_compacted_payload()
    del payload["source_boundary_refs"]

    with pytest.raises(ValueError, match="source_boundary_refs"):
        parse_context_compacted_semantic_payload(payload)


def test_compacted_semantic_parser_rejects_missing_covered_source_refs() -> None:
    """source refs 必须与 committed coverage 同源，不得只留 current input。"""

    payload = _valid_compacted_payload()
    payload["source_boundary_refs"] = ["event-user-1"]

    with pytest.raises(
        ValueError,
        match="source_boundary_refs must equal committed derived coverage",
    ):
        parse_context_compacted_semantic_payload(payload)


def test_compacted_semantic_parser_accepts_nonempty_intent_type() -> None:
    """intent_type 是业务可读文本，不得被下游伪造成枚举。"""

    payload = _valid_compacted_payload()
    candidate = _payload_mapping(payload["accepted_proposal"])
    intents = _mapping_list(candidate["forward_intents"])
    intents[0]["intent_type"] = "custom_follow_up"
    candidate["forward_intents"] = cast(list[JsonValue], intents)
    _replace_candidate_and_digest(payload, candidate)
    replacement = _payload_mapping(payload["accepted_replacement"])
    replacement["forward_intents"] = cast(list[JsonValue], intents)
    payload["accepted_replacement"] = replacement

    semantic = parse_context_compacted_semantic_payload(payload)

    assert semantic.accepted_proposal.forward_intents[0].intent_type == ("custom_follow_up")


def test_compacted_semantic_parser_rejects_invalid_forward_intent_status() -> None:
    """persisted parser 对非法 forward intent status fail closed。"""

    payload = _valid_compacted_payload()
    candidate = _payload_mapping(payload["accepted_proposal"])
    intents = _mapping_list(candidate["forward_intents"])
    intents[0]["status"] = "unknown_status"
    candidate["forward_intents"] = cast(list[JsonValue], intents)
    _replace_candidate_and_digest(payload, candidate)

    with pytest.raises(ValueError):
        parse_context_compacted_semantic_payload(payload)


def test_compacted_semantic_parser_accepts_nonempty_reference_reason() -> None:
    """reference reason 是业务可读文本，不得被下游伪造成枚举。"""

    payload = _valid_compacted_payload()
    candidate = _payload_mapping(payload["accepted_proposal"])
    references = _mapping_list(candidate["reference_continuity"])
    references[0]["reason"] = "retain_for_next_comparison"
    candidate["reference_continuity"] = cast(list[JsonValue], references)
    _replace_candidate_and_digest(payload, candidate)
    replacement = _payload_mapping(payload["accepted_replacement"])
    replacement["reference_continuity"] = cast(list[JsonValue], references)
    payload["accepted_replacement"] = replacement

    semantic = parse_context_compacted_semantic_payload(payload)

    assert semantic.accepted_proposal.reference_continuity[0].reason == ("retain_for_next_comparison")


def test_compacted_semantic_parser_rejects_unsupported_evidence_kind_field() -> None:
    """persisted parser 不接受 unsupported evidence_kind 字段。

    :returns: ``None``。
    :raises AssertionError: persisted parser 接受 unsupported evidence_kind 字段时抛出。
    """

    payload = _valid_compacted_payload()
    candidate = _payload_mapping(payload["accepted_proposal"])
    facts = _mapping_list(candidate["evidence_facts"])
    facts[0]["evidence_kind"] = "accepted_evidence_material"
    candidate["evidence_facts"] = cast(list[JsonValue], facts)
    _replace_candidate_and_digest(payload, candidate)

    with pytest.raises(
        ValueError,
        match=r"unknown_json_key: \$\.evidence_facts\[0\]\.evidence_kind",
    ):
        parse_context_compacted_semantic_payload(payload)


def test_compacted_semantic_parser_rejects_empty_summary_source_labels_with_path() -> None:
    """persisted parser 在 owner boundary 拒绝空 summary source labels。"""

    payload = _valid_compacted_payload()
    candidate = _payload_mapping(payload["accepted_proposal"])
    summary = _payload_mapping(candidate["session_summary"])
    summary["source_labels"] = []
    candidate["session_summary"] = summary
    _replace_candidate_and_digest(payload, candidate)

    with pytest.raises(
        ValueError,
        match=r"\$\.session_summary\.source_labels",
    ):
        parse_context_compacted_semantic_payload(payload)


@pytest.mark.parametrize(
    ("label_field", "expected_path"),
    (
        (
            "support_labels",
            r"\$\.evidence_facts\[0\]\.support_labels\[1\]",
        ),
        (
            "context_labels",
            r"\$\.evidence_facts\[0\]\.context_labels\[1\]",
        ),
    ),
)
def test_compacted_semantic_parser_rejects_duplicate_fact_labels_with_indexed_path(
    label_field: str,
    expected_path: str,
) -> None:
    """persisted parser 拒绝重复 fact labels 并保留 indexed JSON path。

    :param label_field: 被破坏的 fact label 字段。
    :param expected_path: 预期错误路径 regex。
    """

    payload = _valid_compacted_payload()
    candidate = _payload_mapping(payload["accepted_proposal"])
    facts = _mapping_list(candidate["evidence_facts"])
    facts[0][label_field] = ["E1", "E1"]
    candidate["evidence_facts"] = cast(list[JsonValue], facts)
    _replace_candidate_and_digest(payload, candidate)

    with pytest.raises(ValueError, match=expected_path):
        parse_context_compacted_semantic_payload(payload)


def test_compacted_semantic_parser_rejects_duplicate_intent_source_labels_with_indexed_path() -> None:
    """persisted parser 拒绝重复 intent source labels 并保留 indexed JSON path。"""

    payload = _valid_compacted_payload()
    candidate = _payload_mapping(payload["accepted_proposal"])
    intents = _mapping_list(candidate["forward_intents"])
    intents[0]["source_labels"] = ["A1", "A1"]
    candidate["forward_intents"] = cast(list[JsonValue], intents)
    _replace_candidate_and_digest(payload, candidate)

    with pytest.raises(
        ValueError,
        match=(
            r"\$\.forward_intents\[0\]\."
            r"source_labels\[1\]"
        ),
    ):
        parse_context_compacted_semantic_payload(payload)


def test_compacted_semantic_parser_rejects_wrong_nested_shape() -> None:
    """persisted parser 拒绝错误 nested list/object shape。"""

    payload = _valid_compacted_payload()
    candidate = _payload_mapping(payload["accepted_proposal"])
    candidate["answer_anchors"] = "not-a-list"
    _replace_candidate_and_digest(payload, candidate)

    with pytest.raises(ValueError, match=r"invalid_field_type: \$\.answer_anchors"):
        parse_context_compacted_semantic_payload(payload)


def test_compacted_semantic_parser_rejects_removed_anchor_children_field() -> None:
    """fresh v4 anchor 不接受旧 child/ordinal 结构。"""

    payload = _valid_compacted_payload()
    candidate = _payload_mapping(payload["accepted_proposal"])
    anchors = _mapping_list(candidate["answer_anchors"])
    anchors[0]["anchor_items"] = [{"text": "legacy", "detail": "legacy", "ordinal": -1}]
    candidate["answer_anchors"] = cast(list[JsonValue], anchors)
    _replace_candidate_and_digest(payload, candidate)

    with pytest.raises(
        ValueError,
        match=r"unknown_json_key: \$\.answer_anchors\[0\]\.anchor_items",
    ):
        parse_context_compacted_semantic_payload(payload)


def test_compacted_semantic_parser_rejects_unknown_old_candidate_field() -> None:
    """persisted parser 不接受 current schema 之外的旧字段 alias。"""

    payload = _valid_compacted_payload()
    candidate = _payload_mapping(payload["accepted_proposal"])
    candidate["episode_summary"] = "legacy"
    _replace_candidate_and_digest(payload, candidate)

    with pytest.raises(ValueError, match=r"unknown_json_key: \$\.episode_summary"):
        parse_context_compacted_semantic_payload(payload)


def test_compacted_semantic_parser_rejects_candidate_digest_mismatch() -> None:
    """persisted parser 不接受 candidate 与 persisted digest 不一致。"""

    payload = _valid_compacted_payload()
    payload["accepted_proposal_digest"] = _DIGEST_A

    with pytest.raises(ValueError, match="accepted_proposal_digest mismatch"):
        parse_context_compacted_semantic_payload(payload)


@pytest.mark.parametrize(
    ("field_name", "tampered_value", "expected_message"),
    (
        (
            "claim",
            "Tampered durable claim.",
            "accepted_replacement must exactly bind",
        ),
        (
            "selection_labels",
            ["UNKNOWN"],
            "accepted_replacement must exactly bind",
        ),
        (
            "selection_labels",
            [],
            "selection_labels must be non-empty",
        ),
        (
            "canonical_evidence_refs",
            ["evidence:unrelated"],
            "accepted_replacement must exactly bind",
        ),
        (
            "canonical_evidence_refs",
            [],
            "canonical_evidence_refs must be non-empty",
        ),
    ),
)
def test_compacted_semantic_parser_rejects_tampered_replacement_fact_binding(
    field_name: str,
    tampered_value: JsonValue,
    expected_message: str,
) -> None:
    """strict payload parser 重验 replacement atom 的 claim/selection/refs exact binding。

    :param field_name: 被篡改的 accepted fact 字段。
    :param tampered_value: 写入 durable payload 的非法值。
    :param expected_message: owner fail-closed 错误片段。
    :returns: ``None``。
    """

    payload = _valid_compacted_payload()
    replacement = _payload_mapping(payload["accepted_replacement"])
    facts = _mapping_list(replacement["evidence_facts"])
    facts[0][field_name] = tampered_value
    replacement["evidence_facts"] = cast(list[JsonValue], facts)
    payload["accepted_replacement"] = replacement

    with pytest.raises(ValueError, match=expected_message):
        parse_context_compacted_semantic_payload(payload)


def test_compacted_semantic_parser_accepts_reverse_cross_fact_boundary_order() -> None:
    """fact 顺序可与 boundary 相反，aggregate 保持 replacement fact/entry 顺序。

    :returns: ``None``。
    :raises AssertionError: durable parser 错把跨 fact 顺序当作 boundary ordinal 时抛出。
    """

    accepted = _accepted_truth_for_ordered_evidence_boundary(
        boundary_refs=(
            ("E1", ("evidence:first",)),
            ("E2", ("evidence:second",)),
        ),
        facts=(
            CompactEvidenceFactV4(
                claim="第二项事实先出现",
                support_labels=("E2",),
                context_labels=(),
            ),
            CompactEvidenceFactV4(
                claim="第一项事实后出现",
                support_labels=("E1",),
                context_labels=(),
            ),
        ),
    )

    semantic = parse_context_compacted_semantic_payload(
        _compacted_payload_for_truth(accepted)
    )

    assert semantic.accepted_evidence_mapping_refs == (
        "evidence:second",
        "evidence:first",
    )


def test_compacted_semantic_parser_accepts_three_fact_shared_ref_ordered_dedup() -> None:
    """三 fact aggregate 按 fact/entry 顺序 unique union，并跨 fact 去重 shared ref。

    :returns: ``None``。
    """

    accepted = _accepted_truth_for_ordered_evidence_boundary(
        boundary_refs=(
            ("E1", ("evidence:first", "evidence:shared")),
            ("E2", ("evidence:shared", "evidence:second")),
            ("E3", ("evidence:third",)),
        ),
        facts=(
            CompactEvidenceFactV4(
                claim="第三项事实",
                support_labels=("E3",),
                context_labels=(),
            ),
            CompactEvidenceFactV4(
                claim="第二项事实",
                support_labels=("E2",),
                context_labels=(),
            ),
            CompactEvidenceFactV4(
                claim="第一项事实",
                support_labels=("E1",),
                context_labels=(),
            ),
        ),
    )

    semantic = parse_context_compacted_semantic_payload(
        _compacted_payload_for_truth(accepted)
    )

    assert semantic.accepted_evidence_mapping_refs == (
        "evidence:third",
        "evidence:shared",
        "evidence:second",
        "evidence:first",
    )


def test_compacted_semantic_parser_accepts_retained_then_new_aggregate() -> None:
    """retained atom 在前、new atom 在后时 aggregate 精确反映 combined replacement。

    :returns: ``None``。
    """

    policy = default_memory_projection_policy()
    compact_input = CompactInputV4(
        schema=COMPACT_INPUT_SCHEMA_V4,
        current_input=CompactCurrentInputV4(
            source_ref="event:current-retained-new",
            readable_text="继续分析",
        ),
        source_boundary=(
            CompactSourceBoundaryEntryV4(
                source_label="P1",
                source_kind=CompactSourceKindV4.PREVIOUS_EVIDENCE_FACT,
                source_refs=("event:previous",),
                canonical_evidence_refs=("evidence:previous",),
                readable_text="旧事实",
            ),
            CompactSourceBoundaryEntryV4(
                source_label="E1",
                source_kind=CompactSourceKindV4.EVIDENCE_MATERIAL,
                source_refs=("event:current-evidence",),
                canonical_evidence_refs=("evidence:current",),
                readable_text="当前证据",
            ),
        ),
        output_caps=compact_output_caps_v4_from_memory_policy(policy),
    )
    proposal = CompactCandidateV4(
        schema=COMPACT_OUTPUT_SCHEMA_V4,
        session_summary=None,
        retained_previous_evidence_fact_labels=("P1",),
        evidence_facts=(
            CompactEvidenceFactV4(
                claim="新事实",
                support_labels=("E1",),
                context_labels=(),
            ),
        ),
        answer_anchors=(),
        forward_intents=(),
        reference_continuity=(),
    )
    accepted = accept_compact_candidate_v4(compact_input, proposal, policy)
    assert isinstance(accepted, CompactAcceptedTruthV4)

    semantic = parse_context_compacted_semantic_payload(
        _compacted_payload_for_truth(accepted)
    )

    assert semantic.accepted_evidence_mapping_refs == (
        "evidence:previous",
        "evidence:current",
    )


def test_compacted_semantic_parser_accepts_empty_evidence_aggregate() -> None:
    """无 evidence facts 的合法 replacement 允许空 aggregate。

    :returns: ``None``。
    """

    accepted = accepted_truth_for_candidate(
        CompactCandidateV4(
            schema=COMPACT_OUTPUT_SCHEMA_V4,
            session_summary=CompactSessionSummaryV4(
                text="只保留会话摘要",
                source_labels=("T1",),
            ),
            retained_previous_evidence_fact_labels=(),
            evidence_facts=(),
            answer_anchors=(),
            forward_intents=(),
            reference_continuity=(),
        ),
        current_input_ref="event:current-empty-aggregate",
    )

    semantic = parse_context_compacted_semantic_payload(
        _compacted_payload_for_truth(accepted)
    )

    assert semantic.accepted_evidence_mapping_refs == ()


@pytest.mark.parametrize(
    ("aggregate", "expected_message"),
    (
        (
            ["evidence:outside"],
            "accepted_evidence_mapping_refs must be boundary evidence subset",
        ),
        (
            ["evidence:E1", "evidence:E1"],
            "accepted_evidence_mapping_refs must contain unique refs",
        ),
        (
            [],
            "accepted_evidence_mapping_refs must equal replacement refs union",
        ),
    ),
)
def test_compacted_semantic_parser_rejects_invalid_aggregate_membership_or_binding(
    aggregate: list[JsonValue],
    expected_message: str,
) -> None:
    """aggregate 对越界、重复和 replacement mismatch 分别 fail closed。

    :param aggregate: 篡改后的 durable aggregate。
    :param expected_message: owner 错误消息。
    :returns: ``None``。
    """

    payload = _valid_compacted_payload()
    payload["accepted_evidence_mapping_refs"] = aggregate

    with pytest.raises(ValueError, match=expected_message):
        parse_context_compacted_semantic_payload(payload)


def test_compacted_payload_rejects_missing_artifact_digest_pair() -> None:
    """compacted payload 没有 artifact ref / digest pair 时失败。"""

    payload = dict(_valid_compacted_payload())
    del payload["compact_artifact_digest"]

    with pytest.raises(ValueError, match="compact_artifact_digest is required"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_summary_without_preservation_evidence() -> None:
    """vNext compacted payload 拒绝旧 episode summary 字段。"""

    payload = dict(_valid_compacted_payload())
    payload["episode_summary_candidate"] = {}

    with pytest.raises(ValueError, match="unexpected payload fields: episode_summary_candidate"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_summary_proposed_evidence_backed_fact_refs() -> None:
    """vNext compacted payload 拒绝旧 proposed fact summary 字段入口。"""

    payload = dict(_valid_compacted_payload())
    payload["episode_summary_candidate"] = {"proposed_evidence_backed_fact_refs": ["fake-fact"]}

    with pytest.raises(ValueError, match="unexpected payload fields: episode_summary_candidate"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_old_summary_proposed_verified_fact_refs() -> None:
    """vNext compacted payload 拒绝旧 proposed_verified_fact_refs key。"""

    payload = dict(_valid_compacted_payload())
    payload["episode_summary_candidate"] = {"proposed_verified_fact_refs": ["fake-fact"]}

    with pytest.raises(ValueError, match="unexpected payload fields: episode_summary_candidate"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_patch_without_preservation_evidence() -> None:
    """vNext compacted payload 拒绝旧 pinned patch 字段。"""

    payload = dict(_valid_compacted_payload())
    payload["pinned_state_patch_candidate"] = {}

    with pytest.raises(ValueError, match="unexpected payload fields: pinned_state_patch_candidate"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_replace_patch_without_value() -> None:
    """vNext compacted payload 拒绝旧 replace patch 字段。"""

    payload = dict(_valid_compacted_payload())
    payload["pinned_state_patch_candidate"] = {"current_goal": {"operation": "replace"}}

    with pytest.raises(ValueError, match="unexpected payload fields: pinned_state_patch_candidate"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_direct_patch_field_without_tristate() -> None:
    """vNext compacted payload 拒绝旧 direct pinned patch 字段。"""

    payload = dict(_valid_compacted_payload())
    payload["pinned_state_patch_candidate"] = {"current_goal": "direct goal"}

    with pytest.raises(ValueError, match="unexpected payload fields: pinned_state_patch_candidate"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_free_form_confirmed_subject() -> None:
    """vNext compacted payload 拒绝旧 confirmed_subjects patch 字段。"""

    payload = dict(_valid_compacted_payload())
    payload["pinned_state_patch_candidate"] = {"confirmed_subjects": {"value": ["Apple Inc."]}}

    with pytest.raises(ValueError, match="unexpected payload fields: pinned_state_patch_candidate"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_tampered_coverage() -> None:
    """committed reader 拒绝与 candidate 派生值不一致的 coverage。"""

    payload = _valid_compacted_payload()
    payload["represented_coverage"] = {"sources": []}

    with pytest.raises(ValueError, match="coverage"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_represented_omitted_overlap() -> None:
    """represented/omitted 不是 exact partition 时 strict reader fail closed。"""

    payload = _valid_compacted_payload()
    payload["omitted_coverage"] = {"source_labels": ["E1"]}

    with pytest.raises(
        ValueError,
        match="represented and omitted coverage must be disjoint",
    ):
        validate_context_compacted_payload(payload)


def test_compacted_semantic_view_rejects_invalid_source_boundary_types() -> None:
    """typed durable view 在读取字段前拒绝非法 source boundary tuple 与 item。

    :returns: ``None``。
    :raises AssertionError: 非 tuple 或非 typed boundary item 未触发 TypeError 时抛出。
    """

    semantics = parse_context_compacted_semantic_payload(_valid_compacted_payload())

    with pytest.raises(TypeError, match="source_boundary must be tuple"):
        replace(
            semantics,
            source_boundary=cast(tuple[CompactSourceBoundaryEntryV4, ...], []),
        )
    with pytest.raises(
        TypeError,
        match="source_boundary item must be CompactSourceBoundaryEntryV4",
    ):
        replace(
            semantics,
            source_boundary=cast(
                tuple[CompactSourceBoundaryEntryV4, ...],
                ("invalid",),
            ),
        )


def test_compacted_semantic_view_rejects_invalid_represented_coverage_type() -> None:
    """typed durable view 明确拒绝非法 represented coverage 类型。

    :returns: ``None``。
    :raises AssertionError: 非 typed represented coverage 未触发 TypeError 时抛出。
    """

    semantics = parse_context_compacted_semantic_payload(_valid_compacted_payload())

    with pytest.raises(
        TypeError,
        match="represented_coverage must be CompactRepresentedCoverageV4",
    ):
        replace(
            semantics,
            represented_coverage=cast(CompactRepresentedCoverageV4, "invalid"),
        )


@pytest.mark.parametrize(
    "actual_field",
    (
        "session_summary_char_actual",
        "evidence_fact_item_actual",
        "evidence_fact_char_actual",
        "answer_anchor_item_actual",
        "answer_anchor_char_actual",
        "forward_intent_item_actual",
        "forward_intent_char_actual",
        "reference_continuity_item_actual",
        "reference_continuity_char_actual",
    ),
)
def test_compacted_payload_rejects_replacement_audit_actual_mismatch(
    actual_field: str,
) -> None:
    """九项 actual 被向下篡改时 strict reader fail closed。

    :param actual_field: 待篡改的 durable audit 字段。
    """

    payload = _valid_compacted_payload()
    audit = _payload_mapping(payload["policy_usage_audit"])
    actual = audit[actual_field]
    assert isinstance(actual, int)
    assert actual > 0
    audit[actual_field] = actual - 1
    payload["policy_usage_audit"] = audit

    with pytest.raises(
        ValueError,
        match="policy_usage_audit actuals must equal replacement-derived usage",
    ):
        validate_context_compacted_payload(payload)


@pytest.mark.parametrize(
    ("binding_field", "expected_message"),
    [
        (None, None),
        ("operation_id", "operation id mismatch"),
        ("attempt_number", "attempt number mismatch"),
        ("engine_run_id", "Engine run id mismatch"),
    ],
)
def test_compacted_payload_records_accepted_proposal_manifest_reference(
    binding_field: str | None,
    expected_message: str | None,
) -> None:
    """accepted payload 记录同源 manifest，并拒绝三类 sibling 串线。

    :param binding_field: 待串线的 manifest binding 字段；正例为 ``None``。
    :param expected_message: 负例 owner-level 拒绝消息；正例为 ``None``。
    :returns: ``None``。
    :raises AssertionError: 正例丢失 identity/manifest 或负例未 fail-closed 时抛出。
    """

    operation_id = "event-context-compaction-requested-accepted"
    attempt_number = 1
    engine_run_id = "compactor-run:accepted"
    identity = _successful_response_identity(
        operation_id=operation_id,
        attempt_number=attempt_number,
        compactor_engine_run_id=engine_run_id,
    )
    manifest_reference = _proposal_manifest_reference(
        operation_id=operation_id,
        attempt_number=attempt_number,
        compactor_engine_run_id=engine_run_id,
        manifest_payload_ref="runner-call-manifest:accepted",
        manifest_digest=_DIGEST_A,
    )
    if binding_field == "operation_id":
        manifest_reference = replace(
            manifest_reference,
            compaction_operation_id="sibling-operation",
        )
    elif binding_field == "attempt_number":
        manifest_reference = replace(
            manifest_reference,
            compaction_attempt_number=2,
        )
    elif binding_field == "engine_run_id":
        manifest_reference = replace(
            manifest_reference,
            compactor_engine_run_id="sibling-compactor-run",
        )
    elif binding_field is not None:
        raise AssertionError("unsupported binding field")
    expected_context = nullcontext() if expected_message is None else pytest.raises(ValueError, match=expected_message)
    payload: Mapping[str, JsonValue] | None = None
    with expected_context:
        payload = build_context_compacted_payload(
            operation_id=operation_id,
            accepted_attempt_number=1,
            compact_artifact_ref="compact-artifact:abc",
            compact_artifact_digest=_DIGEST_B,
            accepted_truth=_accepted_truth(),
            budget_after_compact=512,
            prompt_local_label_mapping_refs=("prompt-label:E1",),
            projection_signal="conversation_memory_projection_catchup",
            successful_response_identity=identity,
            accepted_proposal_manifest_reference=manifest_reference,
        )

    if expected_message is not None:
        return
    assert payload is not None
    validate_context_compacted_payload(payload)
    assert payload["accepted_proposal_manifest_ref"] == ("runner-call-manifest:accepted")
    assert payload["accepted_proposal_manifest_digest"] == _DIGEST_A
    successful_response_identity = cast(
        Mapping[str, JsonValue],
        payload["successful_response_identity"],
    )
    assert set(successful_response_identity) == {
        "effective_provider",
        "effective_model",
        "runner_request_identity",
        "provider_request_id_availability",
        "provider_request_id",
    }
    runner_request_identity = cast(
        Mapping[str, JsonValue],
        successful_response_identity["runner_request_identity"],
    )
    assert set(runner_request_identity) == {
        "run_id",
        "attempt_id",
        "execution_id",
        "iteration_id",
        "iteration_index",
        "runner_call_index",
        "client_correlation_id",
    }


def test_compacted_payload_requires_proposal_manifest_ref_digest_pair() -> None:
    """accepted proposal manifest ref / digest 必须成对出现。"""

    payload = _valid_compacted_payload()
    payload["accepted_proposal_manifest_ref"] = "runner-call-manifest:accepted"
    payload["accepted_proposal_manifest_digest"] = None

    with pytest.raises(ValueError, match="accepted_proposal_manifest"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_requires_non_null_proposal_manifest_pair() -> None:
    """accepted proposal manifest ref / digest 均不得为 null。

    :returns: ``None``。
    :raises AssertionError: accepted payload 接受无 manifest 记录时抛出。
    """

    payload = _valid_compacted_payload()
    payload["accepted_proposal_manifest_ref"] = None
    payload["accepted_proposal_manifest_digest"] = None

    with pytest.raises(ValueError, match="accepted_proposal_manifest_ref"):
        validate_context_compacted_payload(payload)


@pytest.mark.parametrize(
    ("nested", "field_name"),
    [
        (False, "endpoint"),
        (False, "credential"),
        (False, "Authorization"),
        (False, "provider_payload"),
        (True, "headers"),
        (True, "cookie"),
        (True, "secret"),
    ],
)
def test_compacted_payload_identity_rejects_secret_bearing_extra_fields(
    nested: bool,
    field_name: str,
) -> None:
    """strict identity object 拒绝 endpoint/credential/header/payload 等字段。

    :param nested: 是否向 runner_request_identity 注入字段。
    :param field_name: 待注入的敏感字段名。
    :returns: ``None``。
    :raises AssertionError: durable identity 接受敏感扩展字段或泄露值时抛出。
    """

    secret_value = "S5-CANARY-DO-NOT-PERSIST"
    payload = _valid_compacted_payload()
    identity = dict(
        cast(
            Mapping[str, JsonValue],
            payload["successful_response_identity"],
        )
    )
    if nested:
        runner_identity = dict(
            cast(
                Mapping[str, JsonValue],
                identity["runner_request_identity"],
            )
        )
        runner_identity[field_name] = secret_value
        identity["runner_request_identity"] = runner_identity
    else:
        identity[field_name] = secret_value
    payload["successful_response_identity"] = identity

    with pytest.raises(ValueError) as exc_info:
        validate_context_compacted_payload(payload)
    assert secret_value not in str(exc_info.value)


@pytest.mark.parametrize("mutation", ["missing", "renamed", "extra"])
def test_compacted_payload_identity_requires_exact_nested_fields(
    mutation: str,
) -> None:
    """runner request identity nested object 拒绝缺失、改名与额外字段。

    :param mutation: nested object 结构破坏方式。
    :returns: ``None``。
    :raises AssertionError: strict nested schema 接受结构漂移时抛出。
    """

    payload = _valid_compacted_payload()
    identity = dict(
        cast(
            Mapping[str, JsonValue],
            payload["successful_response_identity"],
        )
    )
    runner_identity = dict(
        cast(
            Mapping[str, JsonValue],
            identity["runner_request_identity"],
        )
    )
    if mutation == "missing":
        del runner_identity["runner_call_index"]
    elif mutation == "renamed":
        runner_identity["call_index"] = runner_identity.pop("runner_call_index")
    elif mutation == "extra":
        runner_identity["response_index"] = 1
    else:
        raise AssertionError("unsupported nested mutation")
    identity["runner_request_identity"] = runner_identity
    payload["successful_response_identity"] = identity

    with pytest.raises(ValueError):
        validate_context_compacted_payload(payload)


def test_compacted_payload_identity_rejects_noncanonical_client_correlation() -> None:
    """durable identity 不接受由别处复制的 client correlation id。

    :returns: ``None``。
    :raises AssertionError: validator 接受非 canonical 派生值时抛出。
    """

    payload = _valid_compacted_payload()
    identity = dict(
        cast(
            Mapping[str, JsonValue],
            payload["successful_response_identity"],
        )
    )
    runner_identity = dict(
        cast(
            Mapping[str, JsonValue],
            identity["runner_request_identity"],
        )
    )
    runner_identity["client_correlation_id"] = "dayu-cross-wired"
    identity["runner_request_identity"] = runner_identity
    payload["successful_response_identity"] = identity

    with pytest.raises(ValueError, match="not canonical"):
        validate_context_compacted_payload(payload)


def test_failed_payload_builder_and_validator_no_fallback() -> None:
    """failed payload builder 输出无 fallback 时的完整诊断字段。"""

    payload = build_context_compaction_failed_payload(
        operation_id="event-context-compaction-requested-1",
        failure_reason="quality_check_failed",
        policy_decision=ContextBudgetDecision.BLOCK_HARD_THRESHOLD,
        retryable=False,
        attempt_count=2,
        retry_repair_budget_exhausted=True,
        diagnostic_refs=("diagnostic:compact-1",),
        budget_after_attempted_compact=None,
    )

    validate_context_compaction_failed_payload(payload)
    assert payload["operation_id"] == "event-context-compaction-requested-1"
    assert payload["policy_decision"] == "block_hard_threshold"
    assert payload["retryable"] is False
    assert payload["attempt_count"] == 2
    assert payload["retry_repair_budget_exhausted"] is True
    assert payload["fallback_policy_decision"] is None
    assert payload["fallback_input_window"] is None
    assert payload["fallback_input_digest"] is None
    assert payload["fallback_budget_result"] is None
    assert payload["fallback_action"] == "not_applicable"


def test_failed_payload_builder_and_validator_fallback_dispatch() -> None:
    """failed payload 支持 fallback dispatch 的结构化诊断字段。"""

    payload = build_context_compaction_failed_payload(
        operation_id="event-context-compaction-requested-2",
        failure_reason="quality_check_failed",
        policy_decision="compact_failed_before_dispatch",
        retryable=False,
        attempt_count=1,
        retry_repair_budget_exhausted=True,
        diagnostic_refs=("diagnostic:compact-2",),
        budget_after_attempted_compact=180,
        fallback_policy_decision="recent_window_budget_passed",
        fallback_input_window={
            "selected_block_ids": ["block-current", "block-recent"],
            "dropped_block_ids": ["block-old"],
            "current_input_ref": "event-input-1",
        },
        fallback_input_digest=_DIGEST_A,
        fallback_budget_result={
            "estimated_input_tokens": 42,
            "hard_threshold_tokens": 128,
            "decision": "allow_dispatch",
        },
        fallback_action="dispatch",
    )

    validate_context_compaction_failed_payload(payload)
    assert payload["fallback_action"] == "dispatch"
    assert payload["fallback_input_digest"] == _DIGEST_A


def test_failed_payload_builder_and_validator_fallback_fail_closed() -> None:
    """failed payload 支持 fallback fail closed 的结构化诊断字段。"""

    payload = build_context_compaction_failed_payload(
        operation_id="event-context-compaction-requested-3",
        failure_reason="quality_check_failed",
        policy_decision="compact_failed_before_dispatch",
        retryable=False,
        attempt_count=1,
        retry_repair_budget_exhausted=True,
        diagnostic_refs=("diagnostic:compact-3",),
        budget_after_attempted_compact=180,
        fallback_policy_decision="recent_window_over_budget",
        fallback_input_window={
            "selected_block_ids": ["block-current"],
            "dropped_block_ids": ["block-old"],
            "current_input_ref": "event-input-1",
        },
        fallback_input_digest=_DIGEST_B,
        fallback_budget_result={
            "estimated_input_tokens": 256,
            "hard_threshold_tokens": 128,
            "decision": "block_hard_threshold",
        },
        fallback_action="fail_closed",
    )

    validate_context_compaction_failed_payload(payload)
    assert payload["fallback_action"] == "fail_closed"
    assert payload["fallback_budget_result"] is not None


def test_failed_payload_rejects_negative_attempt_count() -> None:
    """failed validator 拒绝负数 attempt count。"""

    payload = build_context_compaction_failed_payload(
        operation_id="event-context-compaction-requested-4",
        failure_reason="quality_check_failed",
        policy_decision="compact_failed_before_dispatch",
        retryable=False,
        attempt_count=0,
        retry_repair_budget_exhausted=False,
        diagnostic_refs=("diagnostic:compact-4",),
        budget_after_attempted_compact=None,
    )

    invalid_payload = dict(payload)
    invalid_payload["attempt_count"] = -1
    with pytest.raises(ValueError, match="attempt_count must be non-negative"):
        validate_context_compaction_failed_payload(invalid_payload)


def test_failed_payload_rejects_invalid_fallback_action() -> None:
    """failed validator 拒绝非法 fallback action。"""

    payload = build_context_compaction_failed_payload(
        operation_id="event-context-compaction-requested-5",
        failure_reason="quality_check_failed",
        policy_decision="compact_failed_before_dispatch",
        retryable=False,
        attempt_count=0,
        retry_repair_budget_exhausted=False,
        diagnostic_refs=("diagnostic:compact-5",),
        budget_after_attempted_compact=None,
    )

    invalid_payload = dict(payload)
    invalid_payload["fallback_action"] = "retry_later"
    with pytest.raises(ValueError, match="fallback_action must be"):
        validate_context_compaction_failed_payload(invalid_payload)


def test_failed_payload_rejects_not_applicable_with_fallback_fields() -> None:
    """failed validator 拒绝 not_applicable 携带 fallback 诊断字段。

    :returns: ``None``。
    :raises AssertionError: validator 未拒绝非法字段组合时抛出。
    """

    selected_block_ids: list[JsonValue] = ["block-current"]
    fallback_input_window: Mapping[str, JsonValue] = {
        "selected_block_ids": selected_block_ids,
    }
    fallback_budget_result: Mapping[str, JsonValue] = {
        "decision": "allow_dispatch",
    }
    invalid_cases: tuple[tuple[str, JsonValue, str], ...] = (
        (
            _FIELD_FALLBACK_POLICY_DECISION,
            "recent_window_budget_passed",
            "fallback_policy_decision must be null",
        ),
        (
            _FIELD_FALLBACK_INPUT_WINDOW,
            fallback_input_window,
            "fallback_input_window must be null",
        ),
        (
            _FIELD_FALLBACK_INPUT_DIGEST,
            _DIGEST_A,
            "fallback_input_digest must be null",
        ),
        (
            _FIELD_FALLBACK_BUDGET_RESULT,
            fallback_budget_result,
            "fallback_budget_result must be null",
        ),
    )

    for field_name, field_value, expected_message in invalid_cases:
        payload = build_context_compaction_failed_payload(
            operation_id="event-context-compaction-requested-6",
            failure_reason="quality_check_failed",
            policy_decision="compact_failed_before_dispatch",
            retryable=False,
            attempt_count=0,
            retry_repair_budget_exhausted=False,
            diagnostic_refs=("diagnostic:compact-6",),
            budget_after_attempted_compact=None,
        )
        invalid_payload = dict(payload)
        invalid_payload[field_name] = field_value

        with pytest.raises(ValueError, match=expected_message):
            validate_context_compaction_failed_payload(invalid_payload)


def test_failed_payload_rejects_dispatch_missing_or_null_fallback_field() -> None:
    """failed validator 拒绝 dispatch 缺失或置空必需 fallback 字段。

    :returns: ``None``。
    :raises AssertionError: validator 未拒绝非法字段组合时抛出。
    """

    missing_payload = dict(_valid_failed_payload_with_fallback("dispatch"))
    del missing_payload[_FIELD_FALLBACK_INPUT_WINDOW]
    with pytest.raises(ValueError, match="fallback_input_window is required"):
        validate_context_compaction_failed_payload(missing_payload)

    null_payload = dict(_valid_failed_payload_with_fallback("dispatch"))
    null_payload[_FIELD_FALLBACK_INPUT_WINDOW] = None
    with pytest.raises(ValueError, match="fallback_input_window must be mapping"):
        validate_context_compaction_failed_payload(null_payload)


def test_failed_payload_rejects_fail_closed_missing_or_null_fallback_field() -> None:
    """failed validator 拒绝 fail_closed 缺失或置空必需 fallback 字段。

    :returns: ``None``。
    :raises AssertionError: validator 未拒绝非法字段组合时抛出。
    """

    missing_payload = dict(_valid_failed_payload_with_fallback("fail_closed"))
    del missing_payload[_FIELD_FALLBACK_BUDGET_RESULT]
    with pytest.raises(ValueError, match="fallback_budget_result is required"):
        validate_context_compaction_failed_payload(missing_payload)

    null_payload = dict(_valid_failed_payload_with_fallback("fail_closed"))
    null_payload[_FIELD_FALLBACK_BUDGET_RESULT] = None
    with pytest.raises(ValueError, match="fallback_budget_result must be mapping"):
        validate_context_compaction_failed_payload(null_payload)


def test_failed_payload_rejects_missing_required_fields() -> None:
    """failed validator 拒绝缺少必填字段的 payload。"""

    with pytest.raises(ValueError, match="operation_id is required"):
        validate_context_compaction_failed_payload({})


def test_attempt_rejected_payload_builder_and_validator() -> None:
    """attempt rejected payload 输出 operation / attempt / diagnostics。"""

    offending_text_digest = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    payload = dict(
        build_context_compaction_attempt_rejected_payload(
            operation_id="operation-1",
            attempt_number=1,
            failure_category="quality_check_rejected",
            repairable=True,
            runner_attempt_summary_refs=("runner-attempt:1",),
            diagnostic_refs=("diagnostic:1",),
            next_policy_decision="retry_semantic_repair",
            budget_after_attempted_compact=128,
            successful_response_identity=_successful_response_identity(
                operation_id="operation-1",
                attempt_number=1,
                compactor_engine_run_id="compactor-run:operation-1:attempt-1",
            ),
            proposal_manifest_reference=_proposal_manifest_reference(
                operation_id="operation-1",
                attempt_number=1,
                compactor_engine_run_id="compactor-run:operation-1:attempt-1",
                manifest_payload_ref="runner-call-manifest:rejected",
                manifest_digest=_DIGEST_A,
            ),
            diagnostic_artifact_ref="compaction-diagnostic:event-1",
            diagnostic_artifact_digest=_DIGEST_B,
            failure_stage="previous_compacted_view_parse",
            diagnostic_suffix="ValueError:previous reference continuity text is invalid",
            parser_or_validator="previous_reference_continuity",
            exception_class="ValueError",
            exception_message="previous reference continuity text is invalid",
            offending_block_section="previous_compacted_view",
            offending_block_kind="reference_continuity",
            offending_block_label="P1",
            offending_block_ordinal=0,
            offending_block_text_digest=offending_text_digest,
            offending_block_text_length=42,
            material_pack_digest=_DIGEST_B,
        )
    )

    validate_context_compaction_attempt_rejected_payload(payload)
    assert CONTEXT_COMPACTION_ATTEMPT_REJECTED == ("CONTEXT_COMPACTION_ATTEMPT_REJECTED")
    assert payload["attempt_number"] == 1
    assert payload["proposal_manifest_ref"] == "runner-call-manifest:rejected"
    assert payload["proposal_manifest_digest"] == _DIGEST_A
    assert payload["diagnostic_artifact_ref"] == "compaction-diagnostic:event-1"
    assert payload["diagnostic_artifact_digest"] == _DIGEST_B
    assert payload["failure_stage"] == "previous_compacted_view_parse"
    assert payload["parser_or_validator"] == "previous_reference_continuity"
    assert payload["offending_block_kind"] == "reference_continuity"
    assert payload["offending_block_text_digest"] == offending_text_digest
    assert "raw_text" not in payload


def test_attempt_rejected_payload_requires_proposal_manifest_ref_digest_pair() -> None:
    """rejected proposal manifest ref / digest 必须成对出现。"""

    payload = dict(
        build_context_compaction_attempt_rejected_payload(
            operation_id="operation-1",
            attempt_number=1,
            failure_category="quality_check_rejected",
            repairable=True,
            runner_attempt_summary_refs=("runner-attempt:1",),
            diagnostic_refs=("diagnostic:1",),
            next_policy_decision="retry_semantic_repair",
            budget_after_attempted_compact=128,
            successful_response_identity=_successful_response_identity(
                operation_id="operation-1",
                attempt_number=1,
                compactor_engine_run_id="compactor-run:operation-1:attempt-1",
            ),
            proposal_manifest_reference=_proposal_manifest_reference(
                operation_id="operation-1",
                attempt_number=1,
                compactor_engine_run_id="compactor-run:operation-1:attempt-1",
                manifest_payload_ref="runner-call-manifest:rejected",
                manifest_digest=_DIGEST_A,
            ),
        )
    )
    payload["proposal_manifest_digest"] = None

    with pytest.raises(ValueError, match="proposal_manifest"):
        validate_context_compaction_attempt_rejected_payload(payload)


def test_quality_rejected_payload_requires_success_identity() -> None:
    """quality rejection 必须保留成功 final 的 identity 与 manifest。

    :returns: ``None``。
    :raises AssertionError: quality rejection 接受 null identity 时抛出。
    """

    payload = dict(_valid_attempt_rejected_payload())
    payload["successful_response_identity"] = None

    with pytest.raises(ValueError, match="requires successful response identity"):
        validate_context_compaction_attempt_rejected_payload(payload)


def test_rejected_payload_success_identity_requires_manifest() -> None:
    """任意 post-final rejection 的成功 identity 不得脱离 proposal manifest。

    :returns: ``None``。
    :raises AssertionError: validator 接受无 manifest 的成功 identity 时抛出。
    """

    payload = dict(_valid_attempt_rejected_payload())
    payload["failure_category"] = "proposal_failed"
    payload["proposal_manifest_ref"] = None
    payload["proposal_manifest_digest"] = None

    with pytest.raises(ValueError, match="requires proposal manifest reference"):
        validate_context_compaction_attempt_rejected_payload(payload)


def test_cancelled_rejected_payload_forbids_success_identity() -> None:
    """成功 final 前 cancellation rejection 必须持久化 null identity。

    :returns: ``None``。
    :raises AssertionError: cancellation 被伪造成成功 final 时抛出。
    """

    payload = dict(_valid_attempt_rejected_payload())
    payload["failure_category"] = "cancellation_requested"

    with pytest.raises(ValueError, match="forbids successful response identity"):
        validate_context_compaction_attempt_rejected_payload(payload)


def test_attempt_rejected_payload_requires_diagnostic_artifact_ref_digest_pair() -> None:
    """diagnostic artifact ref / digest 必须成对出现。"""

    payload = dict(
        build_context_compaction_attempt_rejected_payload(
            operation_id="operation-1",
            attempt_number=1,
            failure_category="proposal_failed",
            repairable=False,
            runner_attempt_summary_refs=("runner-attempt:1",),
            diagnostic_refs=("diagnostic:1",),
            next_policy_decision="fail_compaction",
            budget_after_attempted_compact=None,
            successful_response_identity=None,
            proposal_manifest_reference=None,
            diagnostic_artifact_ref="compaction-diagnostic:event-1",
            diagnostic_artifact_digest=_DIGEST_A,
        )
    )
    payload["diagnostic_artifact_digest"] = None

    with pytest.raises(ValueError, match="diagnostic_artifact"):
        validate_context_compaction_attempt_rejected_payload(payload)


def test_attempt_rejected_payload_rejects_invalid_diagnostic_digests() -> None:
    """diagnostic 小字段中的 digest 必须是 sha256 digest。"""

    payload = dict(_valid_attempt_rejected_payload())
    payload["offending_block_text_digest"] = "not-a-digest"

    with pytest.raises(ValueError, match="offending_block_text_digest"):
        validate_context_compaction_attempt_rejected_payload(payload)


def test_attempt_rejected_payload_rejects_missing_required_fields() -> None:
    """attempt rejected validator 拒绝缺少必填字段的 payload。"""

    with pytest.raises(ValueError, match="operation_id is required"):
        validate_context_compaction_attempt_rejected_payload({})


@pytest.mark.parametrize("attempt_number", [0, True, "bad"])
def test_attempt_rejected_payload_requires_positive_attempt_number(
    attempt_number: JsonValue,
) -> None:
    """attempt_number 必须是正整数且不是 bool。"""

    payload = dict(_valid_attempt_rejected_payload())
    payload["attempt_number"] = attempt_number

    with pytest.raises(ValueError, match="attempt_number"):
        validate_context_compaction_attempt_rejected_payload(payload)


@pytest.mark.parametrize(
    "field_name",
    ["runner_attempt_summary_refs", "diagnostic_refs"],
)
def test_attempt_rejected_payload_requires_non_empty_ref_lists(
    field_name: str,
) -> None:
    """runner attempt summary refs 与 diagnostic refs 都必须非空。"""

    payload = dict(_valid_attempt_rejected_payload())
    payload[field_name] = []

    with pytest.raises(ValueError, match=field_name):
        validate_context_compaction_attempt_rejected_payload(payload)


def test_attempt_rejected_payload_rejects_invalid_budget() -> None:
    """budget_after_attempted_compact 必须为非负整数或 None。"""

    payload = dict(_valid_attempt_rejected_payload())
    payload["budget_after_attempted_compact"] = -1

    with pytest.raises(ValueError, match="budget_after_attempted_compact"):
        validate_context_compaction_attempt_rejected_payload(payload)


def test_attempt_rejected_projects_to_progress_host_event(tmp_path: Path) -> None:
    """attempt rejected canonical fact 投影为 public progress HostEvent。"""

    with open_host_durable_store(_durable_options(tmp_path)) as store:

        def _operation(transaction: HostTransaction) -> HostEventKind:
            """执行 HostEvent 投影。

            :param transaction: 当前 Host read transaction。
            :returns: public HostEvent kind。
            """

            row = _attempt_rejected_row()
            return _host_event_from_row(transaction, row).kind

        assert store.transaction_runner.run_read(_operation) is HostEventKind.PROGRESS


def test_run_lost_projects_to_lost_host_event(tmp_path: Path) -> None:
    """RUN_LOST canonical fact 投影为 public lost terminal HostEvent。"""

    with open_host_durable_store(_durable_options(tmp_path)) as store:

        def _operation(
            transaction: HostTransaction,
        ) -> tuple[HostEventKind, HostEventClass, str, HostTerminalStatus | None]:
            """执行 HostEvent 投影。

            :param transaction: 当前 Host read transaction。
            :returns: public HostEvent kind、identity 与 terminal status。
            """

            host_event = _host_event_from_row(transaction, _run_lost_row())
            return (
                host_event.kind,
                host_event.event_class,
                host_event.event_type,
                host_event.terminal_status,
            )

        assert store.transaction_runner.run_read(_operation) == (
            HostEventKind.LOST,
            HostEventClass.CANONICAL_FACT,
            "RUN_LOST",
            HostTerminalStatus.LOST,
        )


def _valid_failed_payload_with_fallback(
    fallback_action: str,
) -> Mapping[str, JsonValue]:
    """构造带完整 fallback 诊断字段的 failed payload。

    :param fallback_action: fallback action，必须是 validator 允许的非空文本。
    :returns: ``CONTEXT_COMPACTION_FAILED`` payload。
    :raises ValueError: fallback action 或构造出的 payload 不合法时抛出。
    """

    return build_context_compaction_failed_payload(
        operation_id="event-context-compaction-requested-with-fallback",
        failure_reason="quality_check_failed",
        policy_decision="compact_failed_before_dispatch",
        retryable=False,
        attempt_count=1,
        retry_repair_budget_exhausted=True,
        diagnostic_refs=("diagnostic:compact-with-fallback",),
        budget_after_attempted_compact=180,
        fallback_policy_decision="recent_window_budget_checked",
        fallback_input_window={
            "selected_block_ids": ["block-current"],
            "dropped_block_ids": ["block-old"],
            "current_input_ref": "event-input-1",
        },
        fallback_input_digest=_DIGEST_A,
        fallback_budget_result={
            "estimated_input_tokens": 42,
            "hard_threshold_tokens": 128,
            "decision": "allow_dispatch",
        },
        fallback_action=fallback_action,
    )


def _valid_attempt_rejected_payload() -> Mapping[str, JsonValue]:
    """构造有效 attempt rejected payload。

    :returns: payload mapping。
    """

    return build_context_compaction_attempt_rejected_payload(
        operation_id="operation-1",
        attempt_number=1,
        failure_category="quality_check_rejected",
        repairable=False,
        runner_attempt_summary_refs=("runner-attempt:1",),
        diagnostic_refs=("diagnostic:1",),
        next_policy_decision="fail_compaction",
        budget_after_attempted_compact=None,
        successful_response_identity=_successful_response_identity(
            operation_id="operation-1",
            attempt_number=1,
            compactor_engine_run_id="compactor-run:operation-1:attempt-1",
        ),
        proposal_manifest_reference=_proposal_manifest_reference(
            operation_id="operation-1",
            attempt_number=1,
            compactor_engine_run_id="compactor-run:operation-1:attempt-1",
            manifest_payload_ref="runner-call-manifest:rejected",
            manifest_digest=_DIGEST_A,
        ),
    )


def _attempt_rejected_row() -> EventLogRow:
    """构造 attempt rejected EventLog row。

    :returns: EventLog row。
    """

    timestamp = format_utc_timestamp(datetime.now(UTC))
    return EventLogRow(
        event_sequence=1,
        event_id="event-context-compaction-attempt-rejected-test",
        event_body_digest=_DIGEST_A,
        event_class=EventClass.CANONICAL_FACT,
        session_id="session-1",
        run_id="run-1",
        attempt_id=None,
        execution_id=None,
        event_type=CONTEXT_COMPACTION_ATTEMPT_REJECTED,
        occurred_at=timestamp,
        actor="test",
        source="pytest",
        client_request_id=None,
        idempotency_key=None,
        policy_decision_json=None,
        reason_json=None,
        payload_json="{}",
        payload_ref=None,
        payload_digest=None,
        appended_at=timestamp,
    )


def _run_lost_row() -> EventLogRow:
    """构造 RUN_LOST EventLog row。

    :returns: RUN_LOST EventLog row。
    """

    timestamp = format_utc_timestamp(datetime.now(UTC))
    return EventLogRow(
        event_sequence=2,
        event_id="event-run-lost-test",
        event_body_digest=_DIGEST_B,
        event_class=EventClass.CANONICAL_FACT,
        session_id="session-1",
        run_id="run-1",
        attempt_id="attempt-1",
        execution_id="execution-1",
        event_type="RUN_LOST",
        occurred_at=timestamp,
        actor="test",
        source="pytest",
        client_request_id=None,
        idempotency_key=None,
        policy_decision_json=None,
        reason_json=None,
        payload_json='{"message":"worker lost"}',
        payload_ref=None,
        payload_digest=None,
        appended_at=timestamp,
    )


def _durable_options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造 Host durable store 选项。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "host.sqlite3",
        payload_policy=PayloadStoragePolicy(
            artifact_root=tmp_path / "artifacts",
        ),
    )


def _valid_compacted_payload() -> dict[str, JsonValue]:
    """构造可变的有效 compacted payload。

    :returns: compacted payload。
    """

    return dict(
        _compacted_payload_for_truth(_accepted_truth())
    )


def _compacted_payload_for_truth(
    accepted_truth: CompactAcceptedTruthV4,
) -> dict[str, JsonValue]:
    """把任意 production-accepted truth 包装为 strict schema-5 payload。

    :param accepted_truth: Context Governance 产生的 accepted truth。
    :returns: 可变的 canonical compacted payload。
    """

    return dict(
        build_context_compacted_payload(
            operation_id="event-context-compaction-requested-accepted",
            accepted_attempt_number=2,
            compact_artifact_ref="compact-artifact:abc",
            compact_artifact_digest=_DIGEST_B,
            accepted_truth=accepted_truth,
            budget_after_compact=512,
            prompt_local_label_mapping_refs=("prompt-label:E1", "prompt-label:A1"),
            projection_signal="conversation_memory_projection_catchup",
            successful_response_identity=_successful_response_identity(
                operation_id="event-context-compaction-requested-accepted",
                attempt_number=2,
                compactor_engine_run_id="compactor-run:accepted:attempt-2",
            ),
            accepted_proposal_manifest_reference=_proposal_manifest_reference(
                operation_id="event-context-compaction-requested-accepted",
                attempt_number=2,
                compactor_engine_run_id="compactor-run:accepted:attempt-2",
                manifest_payload_ref="runner-call-manifest:accepted:attempt-2",
                manifest_digest=_DIGEST_A,
            ),
        )
    )


def _accepted_truth_for_ordered_evidence_boundary(
    *,
    boundary_refs: tuple[tuple[str, tuple[str, ...]], ...],
    facts: tuple[CompactEvidenceFactV4, ...],
) -> CompactAcceptedTruthV4:
    """用显式 boundary 顺序验收可独立排列的 evidence facts。

    :param boundary_refs: 按 immutable boundary 顺序给出的 label/refs。
    :param facts: 按 proposal 顺序给出的 new facts。
    :returns: production Context Governance 产生的 accepted truth。
    :raises AssertionError: fixture proposal 未满足 production contract 时抛出。
    """

    policy = default_memory_projection_policy()
    compact_input = CompactInputV4(
        schema=COMPACT_INPUT_SCHEMA_V4,
        current_input=CompactCurrentInputV4(
            source_ref="event:current-aggregate-order",
            readable_text="继续分析 aggregate 顺序",
        ),
        source_boundary=tuple(
            CompactSourceBoundaryEntryV4(
                source_label=label,
                source_kind=CompactSourceKindV4.EVIDENCE_MATERIAL,
                source_refs=(f"event:{label}",),
                canonical_evidence_refs=refs,
                readable_text=f"{label} evidence material",
            )
            for label, refs in boundary_refs
        ),
        output_caps=compact_output_caps_v4_from_memory_policy(policy),
    )
    proposal = CompactCandidateV4(
        schema=COMPACT_OUTPUT_SCHEMA_V4,
        session_summary=None,
        retained_previous_evidence_fact_labels=(),
        evidence_facts=facts,
        answer_anchors=(),
        forward_intents=(),
        reference_continuity=(),
    )
    accepted = accept_compact_candidate_v4(compact_input, proposal, policy)
    assert isinstance(accepted, CompactAcceptedTruthV4)
    return accepted


def _candidate() -> CompactCandidateV4:
    """构造测试用 accepted vNext compaction candidate。

    :returns: vNext compaction candidate。
    """

    return CompactCandidateV4(
        schema=COMPACT_OUTPUT_SCHEMA_V4,
        session_summary=CompactSessionSummaryV4(
            text="Q1 review focused on revenue.",
            source_labels=("E1", "A1"),
        ),
        retained_previous_evidence_fact_labels=(),
        evidence_facts=(
            CompactEvidenceFactV4(
                claim="Revenue increased.",
                support_labels=("E1",),
                context_labels=(),
            ),
        ),
        answer_anchors=(
            CompactAnswerAnchorV4(
                title="Revenue answer",
                detail="Revenue increased.\nMargin also expanded.",
                source_labels=("A1",),
            ),
        ),
        forward_intents=(
            CompactForwardIntentV4(
                intent_type="next_step_note",
                text="Compare quarters next.",
                status=CompactForwardIntentStatusV4.OPEN,
                source_labels=("A1",),
            ),
        ),
        reference_continuity=(
            CompactReferenceContinuityV4(
                text="Keep revenue comparison context.",
                reason="local_reference",
                source_labels=("A1",),
            ),
        ),
    )


def _accepted_truth() -> CompactAcceptedTruthV4:
    """构造与 valid event fixture 同源的 accepted truth。

    :returns: production governance owner 生成的 accepted truth。
    """

    return accepted_truth_for_candidate(
        _candidate(),
        current_input_ref="event-user-1",
        source_refs_by_label={
            "E1": ("evidence:accepted-1",),
            "A1": ("evidence:accepted-1",),
        },
    )


def _payload_mapping(value: JsonValue) -> dict[str, JsonValue]:
    """把 JSON 值复制为可变 mapping。

    :param value: JSON 值。
    :returns: 可变 dict。
    :raises AssertionError: value 不是 mapping 时抛出。
    """

    assert isinstance(value, Mapping)
    return dict(value)


def _mapping_list(value: JsonValue) -> list[dict[str, JsonValue]]:
    """把 JSON object list 复制为可变 list。

    :param value: JSON 值。
    :returns: 可变 JSON object list。
    :raises AssertionError: value 不是 object list 时抛出。
    """

    assert isinstance(value, list)
    return [_payload_mapping(item) for item in value]


def _replace_candidate_and_digest(
    payload: dict[str, JsonValue],
    candidate: dict[str, JsonValue],
) -> None:
    """替换测试 payload candidate 并同步 digest。

    :param payload: 可变 compacted payload。
    :param candidate: 被测试的 candidate shape。
    :returns: ``None``。
    """

    payload["accepted_proposal"] = candidate
    payload["accepted_proposal_digest"] = sha256_digest_json(candidate)
