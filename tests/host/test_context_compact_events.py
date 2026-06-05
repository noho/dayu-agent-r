"""Host context compact canonical event payload 测试。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dayu.contracts.json_value import JsonValue
from dayu.host.api import HostEventKind, HostTerminalStatus
from dayu.host.compaction import (
    AnswerAnchorCandidateVNext,
    AnswerAnchorChildVNext,
    CompactQualityCheckResultVNext,
    CompactQualityIssueVNext,
    CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
    ConversationCompactOutputVNext,
    EvidenceBackedFactCandidateVNext,
    FactEvidenceKindVNext,
    ForwardIntentCandidateVNext,
    ForwardIntentStatusVNext,
    ForwardIntentTypeVNext,
    ReferenceContinuityCandidateVNext,
    ReferenceContinuityReasonVNext,
    SessionSummaryCandidateVNext,
)
from dayu.host.context_budget import ContextBudgetDecision
from dayu.host.context_events import (
    CONTEXT_COMPACTION_ATTEMPT_REJECTED,
    build_context_compaction_attempt_rejected_payload,
    build_context_compacted_payload,
    build_context_compaction_failed_payload,
    build_context_compaction_requested_payload,
    validate_context_compaction_attempt_rejected_payload,
    validate_context_compacted_payload,
    validate_context_compaction_failed_payload,
    validate_context_compaction_requested_payload,
)
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.codec import format_utc_timestamp
from dayu.host.durable.event_log import EventClass, EventLogRow
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    PayloadStoragePolicy,
)
from dayu.host.durable.transaction import HostTransaction
from dayu.host.read_api import _host_event_from_row

_DIGEST_A = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_DIGEST_B = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_FIELD_FALLBACK_POLICY_DECISION = "fallback_policy_decision"
_FIELD_FALLBACK_INPUT_WINDOW = "fallback_input_window"
_FIELD_FALLBACK_INPUT_DIGEST = "fallback_input_digest"
_FIELD_FALLBACK_BUDGET_RESULT = "fallback_budget_result"


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
    """compacted builder 输出 accepted vNext candidate 与治理字段。"""

    payload = _valid_compacted_payload()

    validate_context_compacted_payload(payload)
    assert payload["compact_artifact_ref"] == "compact-artifact:abc"
    assert payload["accepted_attempt_number"] == 2
    assert payload["accepted_candidate_digest"] == _candidate().digest()
    assert payload["budget_after_compact"] == 512


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

    with pytest.raises(ValueError, match="episode_summary_candidate is not supported"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_summary_proposed_evidence_backed_fact_refs() -> None:
    """vNext compacted payload 拒绝旧 proposed fact summary 字段入口。"""

    payload = dict(_valid_compacted_payload())
    payload["episode_summary_candidate"] = {"proposed_evidence_backed_fact_refs": ["fake-fact"]}

    with pytest.raises(ValueError, match="episode_summary_candidate is not supported"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_old_summary_proposed_verified_fact_refs() -> None:
    """vNext compacted payload 拒绝旧 proposed_verified_fact_refs key。"""

    payload = dict(_valid_compacted_payload())
    payload["episode_summary_candidate"] = {"proposed_verified_fact_refs": ["fake-fact"]}

    with pytest.raises(ValueError, match="episode_summary_candidate is not supported"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_patch_without_preservation_evidence() -> None:
    """vNext compacted payload 拒绝旧 pinned patch 字段。"""

    payload = dict(_valid_compacted_payload())
    payload["pinned_state_patch_candidate"] = {}

    with pytest.raises(ValueError, match="pinned_state_patch_candidate is not supported"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_replace_patch_without_value() -> None:
    """vNext compacted payload 拒绝旧 replace patch 字段。"""

    payload = dict(_valid_compacted_payload())
    payload["pinned_state_patch_candidate"] = {"current_goal": {"operation": "replace"}}

    with pytest.raises(ValueError, match="pinned_state_patch_candidate is not supported"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_direct_patch_field_without_tristate() -> None:
    """vNext compacted payload 拒绝旧 direct pinned patch 字段。"""

    payload = dict(_valid_compacted_payload())
    payload["pinned_state_patch_candidate"] = {"current_goal": "direct goal"}

    with pytest.raises(ValueError, match="pinned_state_patch_candidate is not supported"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_free_form_confirmed_subject() -> None:
    """vNext compacted payload 拒绝旧 confirmed_subjects patch 字段。"""

    payload = dict(_valid_compacted_payload())
    payload["pinned_state_patch_candidate"] = {"confirmed_subjects": {"value": ["Apple Inc."]}}

    with pytest.raises(ValueError, match="pinned_state_patch_candidate is not supported"):
        validate_context_compacted_payload(payload)


def test_compacted_payload_rejects_rejected_quality_result() -> None:
    """CONTEXT_COMPACTED 只能承载 accepted quality check output。"""

    with pytest.raises(ValueError, match="accepted quality result"):
        build_context_compacted_payload(
            operation_id="event-context-compaction-requested-rejected",
            accepted_attempt_number=1,
            compact_artifact_ref="compact-artifact:abc",
            compact_artifact_digest=_DIGEST_B,
            accepted_candidate=_candidate(),
            quality_check_result=CompactQualityCheckResultVNext(
                accepted=False,
                rejection_reasons=(CompactQualityIssueVNext.UNKNOWN_SOURCE_LABEL,),
            ),
            budget_after_compact=512,
            prompt_local_label_mapping_refs=("prompt-label:E1",),
            source_boundary_refs=("event-user-1",),
            accepted_evidence_mapping_refs=("evidence:accepted-1",),
            projection_signal="conversation_memory_projection_catchup",
        )


def test_compacted_payload_records_accepted_proposal_manifest_reference() -> None:
    """accepted outcome payload 反向引用 accepted proposal manifest。"""

    payload = build_context_compacted_payload(
        operation_id="event-context-compaction-requested-accepted",
        accepted_attempt_number=1,
        compact_artifact_ref="compact-artifact:abc",
        compact_artifact_digest=_DIGEST_B,
        accepted_candidate=_candidate(),
        quality_check_result=_quality_result(),
        budget_after_compact=512,
        prompt_local_label_mapping_refs=("prompt-label:E1",),
        source_boundary_refs=("event-user-1",),
        accepted_evidence_mapping_refs=("evidence:accepted-1",),
        projection_signal="conversation_memory_projection_catchup",
        accepted_proposal_manifest_ref="runner-call-manifest:accepted",
        accepted_proposal_manifest_digest=_DIGEST_A,
    )

    validate_context_compacted_payload(payload)
    assert payload["accepted_proposal_manifest_ref"] == (
        "runner-call-manifest:accepted"
    )
    assert payload["accepted_proposal_manifest_digest"] == _DIGEST_A


def test_compacted_payload_requires_proposal_manifest_ref_digest_pair() -> None:
    """accepted proposal manifest ref / digest 必须成对出现。"""

    payload = _valid_compacted_payload()
    payload["accepted_proposal_manifest_ref"] = "runner-call-manifest:accepted"
    payload["accepted_proposal_manifest_digest"] = None

    with pytest.raises(ValueError, match="accepted_proposal_manifest"):
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
            proposal_manifest_ref="runner-call-manifest:rejected",
            proposal_manifest_digest=_DIGEST_A,
        )
    )

    validate_context_compaction_attempt_rejected_payload(payload)
    assert CONTEXT_COMPACTION_ATTEMPT_REJECTED == (
        "CONTEXT_COMPACTION_ATTEMPT_REJECTED"
    )
    assert payload["attempt_number"] == 1
    assert payload["proposal_manifest_ref"] == "runner-call-manifest:rejected"
    assert payload["proposal_manifest_digest"] == _DIGEST_A


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
            proposal_manifest_ref="runner-call-manifest:rejected",
            proposal_manifest_digest=_DIGEST_A,
        )
    )
    payload["proposal_manifest_digest"] = None

    with pytest.raises(ValueError, match="proposal_manifest"):
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
        ) -> tuple[HostEventKind, HostTerminalStatus | None]:
            """执行 HostEvent 投影。

            :param transaction: 当前 Host read transaction。
            :returns: public HostEvent kind 与 terminal status。
            """

            host_event = _host_event_from_row(transaction, _run_lost_row())
            return host_event.kind, host_event.terminal_status

        assert store.transaction_runner.run_read(_operation) == (
            HostEventKind.LOST,
            HostTerminalStatus.LOST,
        )


def _valid_failed_payload_with_fallback(fallback_action: str) -> Mapping[str, JsonValue]:
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
        build_context_compacted_payload(
            operation_id="event-context-compaction-requested-accepted",
            accepted_attempt_number=2,
            compact_artifact_ref="compact-artifact:abc",
            compact_artifact_digest=_DIGEST_B,
            accepted_candidate=_candidate(),
            quality_check_result=_quality_result(),
            budget_after_compact=512,
            prompt_local_label_mapping_refs=("prompt-label:E1", "prompt-label:A1"),
            source_boundary_refs=("event-user-1", "evidence:accepted-1"),
            accepted_evidence_mapping_refs=("evidence:accepted-1",),
            projection_signal="conversation_memory_projection_catchup",
        )
    )


def _candidate() -> ConversationCompactOutputVNext:
    """构造测试用 accepted vNext compaction candidate。

    :returns: vNext compaction candidate。
    """

    return ConversationCompactOutputVNext(
        schema_version=CONVERSATION_COMPACT_OUTPUT_SCHEMA_VERSION_VNEXT,
        session_summary=SessionSummaryCandidateVNext(
            summary_text="Q1 review focused on revenue.",
            source_labels=("E1", "A1"),
        ),
        evidence_backed_facts=(
            EvidenceBackedFactCandidateVNext(
                claim_text="Revenue increased.",
                evidence_labels=("E1",),
                evidence_kind=FactEvidenceKindVNext.ACCEPTED_EVIDENCE_MATERIAL,
                source_labels=("E1",),
            ),
        ),
        answer_anchors=(
            AnswerAnchorCandidateVNext(
                anchor_title="Revenue answer",
                anchor_items=(AnswerAnchorChildVNext(display_text="Revenue increased."),),
                answer_source_labels=("A1",),
            ),
        ),
        forward_intents=(
            ForwardIntentCandidateVNext(
                intent_type=ForwardIntentTypeVNext.NEXT_STEP_NOTE,
                text="Compare quarters next.",
                status=ForwardIntentStatusVNext.OPEN,
                source_labels=("A1",),
            ),
        ),
        reference_continuity_items=(
            ReferenceContinuityCandidateVNext(
                text="Keep revenue comparison context.",
                reason=ReferenceContinuityReasonVNext.LOCAL_REFERENCE,
                source_labels=("A1",),
            ),
        ),
        diagnostics=(),
    )


def _payload_mapping(value: JsonValue) -> dict[str, JsonValue]:
    """把 JSON 值复制为可变 mapping。

    :param value: JSON 值。
    :returns: 可变 dict。
    :raises AssertionError: value 不是 mapping 时抛出。
    """

    assert isinstance(value, Mapping)
    return dict(value)


def _quality_result() -> CompactQualityCheckResultVNext:
    """构造测试用 accepted vNext quality result。

    :returns: vNext quality check result。
    """

    return CompactQualityCheckResultVNext(
        accepted=True,
        rejection_reasons=(),
    )
