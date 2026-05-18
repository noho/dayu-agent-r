"""Host context compact canonical event payload 测试。"""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.compaction import (
    CompactInputRange,
    CompactQualityIssue,
    CompactQualityCheckResult,
    CompactionCandidate,
    EpisodeSummaryCandidate,
    PinnedPatchOperation,
    PinnedStatePatchCandidate,
    PinnedStringTupleFieldPatch,
    PinnedTextFieldPatch,
    PreservationEvidence,
)
from dayu.host.context_budget import ContextBudgetDecision
from dayu.host.context_events import (
    build_context_compacted_payload,
    build_context_compaction_failed_payload,
    build_context_compaction_requested_payload,
    validate_context_compacted_payload,
    validate_context_compaction_failed_payload,
    validate_context_compaction_requested_payload,
)
from dayu.host.context_policy import ContextCompactionTriggerSource

_DIGEST_A = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_DIGEST_B = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def test_requested_payload_builder_accepts_proactive_without_attempt() -> None:
    """proactive requested payload 可以没有 attempt / execution。"""

    payload = build_context_compaction_requested_payload(
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
    )

    validate_context_compaction_requested_payload(payload)
    assert payload["trigger_source"] == "proactive"


def test_requested_payload_rejects_missing_required_fields() -> None:
    """requested validator 拒绝缺少顶层必填字段的 payload。"""

    with pytest.raises(ValueError, match="trigger_source is required"):
        validate_context_compaction_requested_payload({})


def test_requested_payload_rejects_untyped_metadata_for_required_fields() -> None:
    """required fields 放进 metadata bag 不会被 validator 当成 typed payload。"""

    payload: dict[str, JsonValue] = {
        "metadata": {
            "trigger_source": "proactive",
            "budget_reason": "soft_threshold",
        }
    }

    with pytest.raises(ValueError, match="trigger_source is required"):
        validate_context_compaction_requested_payload(payload)


def test_reactive_requested_requires_attempt_and_execution() -> None:
    """reactive requested payload 必须带 attempt / execution identity。"""

    payload = dict(
        build_context_compaction_requested_payload(
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
        )
    )
    payload["trigger_source"] = "reactive"

    with pytest.raises(ValueError, match="reactive compaction requires"):
        validate_context_compaction_requested_payload(payload)


def test_compacted_payload_builder_emits_required_accepted_output() -> None:
    """compacted builder 输出 accepted summary / pinned patch / evidence 字段。"""

    payload = build_context_compacted_payload(
        compact_artifact_ref="compact-artifact:abc",
        compact_artifact_digest=_DIGEST_B,
        accepted_candidate=_candidate(),
        quality_check_result=_quality_result(),
    )

    validate_context_compacted_payload(payload)
    assert payload["compact_artifact_ref"] == "compact-artifact:abc"
    assert payload["budget_after_compact"] == 512


def test_compacted_payload_rejects_missing_artifact_digest_pair() -> None:
    """compacted payload 没有 artifact ref / digest pair 时失败。"""

    payload = dict(_valid_compacted_payload())
    del payload["compact_artifact_digest"]

    with pytest.raises(ValueError, match="compact_artifact_digest is required"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_summary_without_preservation_evidence() -> None:
    """summary candidate 没有 preservation evidence 时不能成为 accepted output。"""

    payload = dict(_valid_compacted_payload())
    summary = _payload_mapping(payload["episode_summary_candidate"])
    summary["evidence_refs"] = []
    payload["episode_summary_candidate"] = summary

    with pytest.raises(ValueError, match="episode summary candidate requires"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_summary_proposed_verified_fact_refs() -> None:
    """accepted compact summary 不能提议新建 verified fact。"""

    payload = dict(_valid_compacted_payload())
    summary = _payload_mapping(payload["episode_summary_candidate"])
    summary["proposed_verified_fact_refs"] = ["fake-fact"]
    payload["episode_summary_candidate"] = summary

    with pytest.raises(ValueError, match="must not propose verified facts"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_patch_without_preservation_evidence() -> None:
    """非 missing pinned patch 字段必须引用 preservation evidence。"""

    payload = dict(_valid_compacted_payload())
    patch = _payload_mapping(payload["pinned_state_patch_candidate"])
    current_goal = _payload_mapping(patch["current_goal"])
    current_goal["evidence_refs"] = []
    patch["current_goal"] = current_goal
    payload["pinned_state_patch_candidate"] = patch

    with pytest.raises(ValueError, match="pinned patch requires"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_replace_patch_without_value() -> None:
    """replace patch 必须在 validator 层带合法 value。"""

    payload = dict(_valid_compacted_payload())
    patch = _payload_mapping(payload["pinned_state_patch_candidate"])
    current_goal = _payload_mapping(patch["current_goal"])
    del current_goal["value"]
    patch["current_goal"] = current_goal
    payload["pinned_state_patch_candidate"] = patch

    with pytest.raises(ValueError, match="value must be non-empty text"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_direct_patch_field_without_tristate() -> None:
    """pinned patch 必须使用字段级三态结构，不能用直写文本绕过 evidence。"""

    payload = dict(_valid_compacted_payload())
    patch = _payload_mapping(payload["pinned_state_patch_candidate"])
    patch["current_goal"] = "direct goal"
    payload["pinned_state_patch_candidate"] = patch

    with pytest.raises(ValueError, match="pinned patch field must be mapping"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_free_form_confirmed_subject() -> None:
    """confirmed_subjects patch 不能接受自由业务字符串。"""

    payload = dict(_valid_compacted_payload())
    patch = _payload_mapping(payload["pinned_state_patch_candidate"])
    subjects = _payload_mapping(patch["confirmed_subjects"])
    subjects["value"] = ["Apple Inc."]
    patch["confirmed_subjects"] = subjects
    payload["pinned_state_patch_candidate"] = patch

    with pytest.raises(ValueError, match="opaque ref text requires kind prefix"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_rejected_quality_result() -> None:
    """CONTEXT_COMPACTED 只能承载 accepted quality check output。"""

    with pytest.raises(ValueError, match="accepted quality result"):
        build_context_compacted_payload(
            compact_artifact_ref="compact-artifact:abc",
            compact_artifact_digest=_DIGEST_B,
            accepted_candidate=_candidate(),
            quality_check_result=CompactQualityCheckResult(
                accepted=False,
                rejection_reasons=(CompactQualityIssue.PRESERVATION_EVIDENCE_MISSING,),
                current_user_input_retained=True,
                accepted_tool_fact_refs_retained=True,
                evidence_anchors_retained=True,
                open_questions_retained=True,
                retained_evidence_refs=("evidence-1",),
                dropped_ranges=(),
                summarized_ranges=(),
            ),
        )


def test_failed_payload_builder_and_validator() -> None:
    """failed payload builder 输出失败原因、policy decision 与诊断 refs。"""

    payload = build_context_compaction_failed_payload(
        failure_reason="quality_check_failed",
        policy_decision=ContextBudgetDecision.BLOCK_HARD_THRESHOLD,
        retryable=False,
        diagnostic_refs=("diagnostic:compact-1",),
        budget_after_attempted_compact=None,
    )

    validate_context_compaction_failed_payload(payload)
    assert payload["policy_decision"] == "block_hard_threshold"
    assert payload["retryable"] is False


def test_failed_payload_rejects_missing_required_fields() -> None:
    """failed validator 拒绝缺少必填字段的 payload。"""

    with pytest.raises(ValueError, match="failure_reason is required"):
        validate_context_compaction_failed_payload({})


def _valid_compacted_payload() -> dict[str, JsonValue]:
    """构造可变的有效 compacted payload。

    :returns: compacted payload。
    """

    return dict(
        build_context_compacted_payload(
            compact_artifact_ref="compact-artifact:abc",
            compact_artifact_digest=_DIGEST_B,
            accepted_candidate=_candidate(),
            quality_check_result=_quality_result(),
        )
    )


def _candidate() -> CompactionCandidate:
    """构造测试用 accepted compaction candidate。

    :returns: compaction candidate。
    """

    input_range = CompactInputRange(
        range_ref="range:older",
        start_input_ref="event-user-1",
        end_input_ref="event-user-2",
    )
    return CompactionCandidate(
        candidate_id="candidate-1",
        episode_summary_candidate=EpisodeSummaryCandidate(
            candidate_id="summary-1",
            episode_title="Q1 review",
            goal="分析收入",
            completed_actions=("read filing",),
            confirmed_fact_refs=("event-tool-1",),
            confirmed_fact_summaries=("tool fact summary",),
            user_constraints=("use fiscal year",),
            open_questions=("check margin",),
            next_step="compare quarters",
            tool_finding_refs=("event-tool-1",),
            source_event_refs=("event-user-1", "event-user-2"),
            evidence_refs=("evidence-1",),
        ),
        pinned_state_patch_candidate=PinnedStatePatchCandidate(
            candidate_id="patch-1",
            current_goal=PinnedTextFieldPatch(
                operation=PinnedPatchOperation.REPLACE,
                value="分析收入",
                evidence_refs=("evidence-1",),
            ),
            confirmed_subjects=PinnedStringTupleFieldPatch(
                operation=PinnedPatchOperation.REPLACE,
                value=("subject:issuer-a",),
                evidence_refs=("evidence-1",),
            ),
            user_constraints=PinnedStringTupleFieldPatch(
                operation=PinnedPatchOperation.REPLACE,
                value=("use fiscal year",),
                evidence_refs=("evidence-1",),
            ),
            open_questions=PinnedStringTupleFieldPatch(
                operation=PinnedPatchOperation.REPLACE,
                value=("check margin",),
                evidence_refs=("evidence-1",),
            ),
        ),
        preservation_evidence=(
            PreservationEvidence(
                evidence_id="evidence-1",
                input_event_refs=("event-user-1",),
                tool_fact_refs=("event-tool-1",),
                memory_snapshot_cursor=3,
                compact_input_range=input_range,
            ),
        ),
        retained_current_user_input_ref="event-user-2",
        preserved_input_event_refs=("event-user-1", "event-user-2"),
        preserved_tool_fact_refs=("event-tool-1",),
        preserved_verified_fact_refs=("event-tool-1",),
        dropped_ranges=(),
        summarized_ranges=(input_range,),
        budget_after_compact=512,
    )


def _payload_mapping(value: JsonValue) -> dict[str, JsonValue]:
    """把 JSON 值复制为可变 mapping。

    :param value: JSON 值。
    :returns: 可变 dict。
    :raises AssertionError: value 不是 mapping 时抛出。
    """

    assert isinstance(value, Mapping)
    return dict(value)


def _quality_result() -> CompactQualityCheckResult:
    """构造测试用 accepted quality result。

    :returns: quality check result。
    """

    return CompactQualityCheckResult(
        accepted=True,
        rejection_reasons=(),
        current_user_input_retained=True,
        accepted_tool_fact_refs_retained=True,
        evidence_anchors_retained=True,
        open_questions_retained=True,
        retained_evidence_refs=("evidence-1",),
        dropped_ranges=(),
        summarized_ranges=(),
    )
