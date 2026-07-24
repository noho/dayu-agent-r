"""WU-CTX-01 Slice 2 canonical context budget owner测试。"""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from dayu.host.context_anchor import (
    CompatibleContextAnchor,
    ContextAnchorResolution,
)
from dayu.host.api import (
    HostActivityKind,
    HostActivityStatus,
)
from dayu.host.context_budget import (
    BudgetEstimate,
    ContextBudgetDecision,
    ContextBudgetOverageReason,
    ContextEstimateMethod,
    ContextPressureLevel,
    ContextSizingResult,
    ContextSizingStage,
    build_conservative_context_sizing_result,
    build_context_sizing_result,
    context_sizing_pressure_and_decision,
)
from dayu.host.context_events import (
    CONTEXT_BUDGET_EVALUATED,
    ContextBudgetEvaluationIdentity,
    append_context_budget_evaluated_in_transaction,
    build_context_budget_evaluated_payload,
    context_budget_evaluated_event_id,
    load_matching_context_budget_evaluation_in_transaction,
    parse_context_budget_evaluated_payload,
)
from dayu.host.context_policy import default_context_budget_policy
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import (
    HostDurableError,
    HostEventIdentityConflictError,
)
from dayu.host.durable.event_log import EventLogStore
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.transaction import HostTransaction
from dayu.host.read_api import _host_event_from_row

_NOW = datetime(2026, 7, 24, 8, 0, tzinfo=UTC)
_CANDIDATE_DIGEST = (
    "sha256:1111111111111111111111111111111111111111111111111111111111111111"
)
_ESTIMATOR_DIGEST = (
    "sha256:2222222222222222222222222222222222222222222222222222222222222222"
)
_OTHER_ESTIMATOR_DIGEST = (
    "sha256:3333333333333333333333333333333333333333333333333333333333333333"
)


def test_soft_threshold_must_be_strictly_less_than_hard_across_boundaries() -> None:
    """typed result、decision matrix与durable parser统一拒绝相等阈值。

    :returns: ``None``。
    :raises AssertionError: 任一owner boundary接受``soft == hard``时抛出。
    """

    result = _sizing(stage=ContextSizingStage.ORDINARY, tokens=100)
    with pytest.raises(ValueError, match="less than"):
        replace(
            result,
            soft_threshold_tokens=result.hard_threshold_tokens,
        )
    with pytest.raises(ValueError, match="less than"):
        context_sizing_pressure_and_decision(
            stage=ContextSizingStage.ORDINARY,
            predicted_input_tokens=100,
            soft_threshold_tokens=900,
            hard_threshold_tokens=900,
        )

    durable_payload = dict(
        build_context_budget_evaluated_payload(
            run_id="run-budget",
            result=result,
        )
    )
    durable_payload["soft_threshold_tokens"] = durable_payload[
        "hard_threshold_tokens"
    ]
    with pytest.raises(ValueError, match="less than"):
        parse_context_budget_evaluated_payload(durable_payload)


@pytest.mark.parametrize(
    ("stage", "tokens", "expected_pressure", "expected_decision"),
    (
        (
            ContextSizingStage.ORDINARY,
            100,
            ContextPressureLevel.NORMAL,
            ContextBudgetDecision.ALLOW_DISPATCH,
        ),
        (
            ContextSizingStage.POST_COMPACT,
            700,
            ContextPressureLevel.SOFT_THRESHOLD_EXCEEDED,
            ContextBudgetDecision.ALLOW_DISPATCH,
        ),
        (
            ContextSizingStage.REACTIVE_POST_COMPACT,
            950,
            ContextPressureLevel.HARD_THRESHOLD_EXCEEDED,
            ContextBudgetDecision.ALLOW_DISPATCH,
        ),
        (
            ContextSizingStage.DISPATCH_FALLBACK,
            950,
            ContextPressureLevel.HARD_THRESHOLD_EXCEEDED,
            ContextBudgetDecision.BLOCK_HARD_THRESHOLD,
        ),
        (
            ContextSizingStage.CONTINUATION,
            950,
            ContextPressureLevel.HARD_THRESHOLD_EXCEEDED,
            ContextBudgetDecision.ALLOW_DISPATCH,
        ),
    ),
)
def test_payload_roundtrip_preserves_five_stage_pressure_and_action(
    stage: ContextSizingStage,
    tokens: int,
    expected_pressure: ContextPressureLevel,
    expected_decision: ContextBudgetDecision,
) -> None:
    """strict schema接受五stage并保留真实pressure/stage-aware action。

    :param stage: producer-owned stage。
    :param tokens: conservative prediction。
    :param expected_pressure: 期望真实pressure。
    :param expected_decision: 期望stage-aware action。
    """

    result = _sizing(stage=stage, tokens=tokens)
    parsed = parse_context_budget_evaluated_payload(
        build_context_budget_evaluated_payload(
            run_id="run-budget",
            result=result,
        )
    )

    assert parsed.sizing_stage is stage
    assert parsed.pressure_level is expected_pressure
    assert parsed.budget_decision is expected_decision
    assert parsed.estimate_method is ContextEstimateMethod.CONSERVATIVE_FALLBACK
    assert parsed.anchor_diagnostic is None


def test_payload_utilization_is_unclamped_and_public_subset_is_exact(
    tmp_path: Path,
) -> None:
    """超过context window时basis points不clamp，public只投影七字段。

    :param tmp_path: pytest临时目录。
    """

    result = _sizing(
        stage=ContextSizingStage.CONTINUATION,
        tokens=1_250,
    )
    projected: tuple[int, frozenset[str]] | None = None
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def _operation(
            transaction: HostTransaction,
        ) -> tuple[int, frozenset[str]]:
            """追加fact并读取public activity。

            :param transaction: 当前write transaction。
            :returns: utilization与public dataclass字段名集合。
            :raises Exception: append/projection错误时透传。
            """

            row = append_context_budget_evaluated_in_transaction(
                transaction,
                event_log,
                session_id="session-budget",
                run_id="run-budget",
                attempt_id="attempt-budget",
                execution_id="execution-budget",
                occurred_at=_NOW,
                result=result,
            )
            event = _host_event_from_row(transaction, row)
            assert event.activity is not None
            assert event.activity.kind is HostActivityKind.CONTEXT_USAGE
            assert event.activity.status is HostActivityStatus.INFO
            assert event.activity.context_usage is not None
            return (
                event.activity.context_usage.utilization_basis_points,
                frozenset(
                    field.name
                    for field in fields(event.activity.context_usage)
                ),
            )

        projected = store.transaction_runner.run_write(_operation)

    assert projected is not None
    utilization, public_fields = projected
    assert utilization == 12_500
    assert frozenset(public_fields) == frozenset(
        (
            "predicted_input_tokens",
            "context_window_size",
            "utilization_basis_points",
            "soft_threshold_tokens",
            "hard_threshold_tokens",
            "estimate_method",
            "pressure_level",
        )
    )
    assert "policy_ref" not in public_fields
    assert "anchor_diagnostic" not in public_fields
    assert "usage" not in public_fields


def test_anchored_fact_roundtrip_keeps_diagnostic_host_private(
    tmp_path: Path,
) -> None:
    """canonical fact保留anchor诊断，public七字段仍不泄漏refs。

    :param tmp_path: pytest临时目录。
    """

    policy = default_context_budget_policy(context_window_size=1_000)
    estimate = BudgetEstimate(
        estimated_input_tokens=650,
        input_budget_tokens=1_000,
        soft_threshold_tokens=800,
        hard_threshold_tokens=900,
        safety_margin_tokens=200,
        estimator_digest=_ESTIMATOR_DIGEST,
        overage_reason=None,
    )
    result = build_context_sizing_result(
        stage=ContextSizingStage.ORDINARY,
        candidate_input_cursor=4,
        candidate_input_projection_ref="candidate:projection",
        candidate_input_digest=_CANDIDATE_DIGEST,
        policy=policy,
        estimate=estimate,
        anchor_resolution=ContextAnchorResolution(
            anchor=CompatibleContextAnchor(
                manifest_event_id="event-manifest-anchor",
                manifest_payload_ref="payload-manifest-anchor",
                manifest_digest=sha256_digest_json({"manifest": "anchor"}),
                iteration_link_event_id="event-link-anchor",
                usage_event_id="event-usage-anchor",
                usage_observation_digest=sha256_digest_json(
                    {"usage": "anchor"}
                ),
                iteration_completed_event_id="event-completed-anchor",
                usage_anchor_tokens=620,
                conservative_anchor_tokens=600,
            ),
            fallback_reason=None,
        ),
    )
    payload = build_context_budget_evaluated_payload(
        run_id="run-budget",
        result=result,
    )
    parsed = parse_context_budget_evaluated_payload(payload)
    assert parsed.estimate_method is ContextEstimateMethod.USAGE_ANCHORED
    assert parsed.predicted_input_tokens == 670
    assert parsed.anchor_diagnostic == result.anchor_diagnostic
    with open_host_durable_store(_options(tmp_path)) as store:
        row = store.transaction_runner.run_write(
            lambda transaction: append_context_budget_evaluated_in_transaction(
                transaction,
                EventLogStore(),
                session_id="session-budget",
                run_id="run-budget",
                attempt_id="attempt-budget",
                execution_id="execution-budget",
                occurred_at=_NOW,
                result=result,
            )
        )
        event = store.transaction_runner.run_read(
            lambda transaction: _host_event_from_row(transaction, row)
        )
        assert event.activity is not None
        assert event.activity.context_usage is not None
        assert frozenset(
            field.name for field in fields(event.activity.context_usage)
        ) == frozenset(
            {
                "estimate_method",
                "predicted_input_tokens",
                "context_window_size",
                "utilization_basis_points",
                "soft_threshold_tokens",
                "hard_threshold_tokens",
                "pressure_level",
            }
        )
def test_deterministic_append_reuses_same_truth_and_rejects_conflict(
    tmp_path: Path,
) -> None:
    """同decision occurrence变化仍复用，矛盾result fail closed。

    :param tmp_path: pytest临时目录。
    """

    result = _sizing(stage=ContextSizingStage.ORDINARY, tokens=100)
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def _append_twice(transaction: HostTransaction) -> tuple[str, int, int]:
            """在同transaction重复append。

            :param transaction: 当前write transaction。
            :returns: event id与两次sequence。
            :raises Exception: append错误时透传。
            """

            first = append_context_budget_evaluated_in_transaction(
                transaction,
                event_log,
                session_id="session-budget",
                run_id="run-budget",
                attempt_id="attempt-budget",
                execution_id="execution-budget",
                occurred_at=_NOW,
                result=result,
            )
            second = append_context_budget_evaluated_in_transaction(
                transaction,
                event_log,
                session_id="session-budget",
                run_id="run-budget",
                attempt_id="attempt-budget",
                execution_id="execution-budget",
                occurred_at=_NOW + timedelta(seconds=10),
                result=result,
            )
            return (first.event_id, first.event_sequence, second.event_sequence)

        event_id, first_sequence, second_sequence = (
            store.transaction_runner.run_write(_append_twice)
        )
        assert first_sequence == second_sequence
        assert event_id.startswith("event-context-budget-evaluated-")

        contradictory = replace(
            result,
            estimator_digest=_OTHER_ESTIMATOR_DIGEST,
        )

        def _append_conflict(transaction: HostTransaction) -> None:
            """尝试写入同identity矛盾result。

            :param transaction: 当前write transaction。
            :returns: ``None``。
            :raises HostEventIdentityConflictError: 始终因矛盾truth抛出。
            """

            append_context_budget_evaluated_in_transaction(
                transaction,
                event_log,
                session_id="session-budget",
                run_id="run-budget",
                attempt_id="attempt-budget",
                execution_id="execution-budget",
                occurred_at=_NOW,
                result=contradictory,
            )

        with pytest.raises(HostEventIdentityConflictError):
            store.transaction_runner.run_write(_append_conflict)


def test_matching_source_loader_rejects_manifest_atom_mismatch(
    tmp_path: Path,
) -> None:
    """source loader只接受与strict manifest/candidate同源的canonical fact。

    :param tmp_path: pytest临时目录。
    """

    result = _sizing(stage=ContextSizingStage.ORDINARY, tokens=100)
    payload = parse_context_budget_evaluated_payload(
        build_context_budget_evaluated_payload(
            run_id="run-budget",
            result=result,
        )
    )
    identity = ContextBudgetEvaluationIdentity(
        run_id=payload.run_id,
        candidate_input_cursor=payload.candidate_input_cursor,
        candidate_input_digest=payload.candidate_input_digest,
        sizing_stage=payload.sizing_stage,
        policy_snapshot_digest=payload.policy_snapshot_digest,
        estimator_id=payload.estimator_id,
        estimator_version=payload.estimator_version,
    )
    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def _seed(transaction: HostTransaction) -> None:
            """写入source fact。

            :param transaction: 当前write transaction。
            :returns: ``None``。
            :raises Exception: append错误时透传。
            """

            append_context_budget_evaluated_in_transaction(
                transaction,
                event_log,
                session_id="session-budget",
                run_id="run-budget",
                attempt_id="attempt-budget",
                execution_id="execution-budget",
                occurred_at=_NOW,
                result=result,
            )

        store.transaction_runner.run_write(_seed)

        def _load_mismatch(transaction: HostTransaction) -> None:
            """用错误estimator digest读取source。

            :param transaction: 当前read transaction。
            :returns: ``None``。
            :raises HostDurableError: source atoms不匹配时抛出。
            """

            load_matching_context_budget_evaluation_in_transaction(
                transaction,
                event_log,
                session_id="session-budget",
                attempt_id="attempt-budget",
                execution_id="execution-budget",
                identity=identity,
                candidate_input_projection_ref="candidate:projection",
                estimator_digest=_OTHER_ESTIMATOR_DIGEST,
                conservative_input_tokens=100,
                context_window_size=1_000,
                policy_ref=payload.policy_ref,
            )

        with pytest.raises(HostDurableError, match="does not match"):
            store.transaction_runner.run_read(_load_mismatch)


def test_strict_parser_and_public_projection_fail_closed_on_corruption(
    tmp_path: Path,
) -> None:
    """unknown stage与durable result corruption均fail closed。

    :param tmp_path: pytest临时目录。
    """

    result = _sizing(stage=ContextSizingStage.ORDINARY, tokens=100)
    payload = dict(
        build_context_budget_evaluated_payload(
            run_id="run-budget",
            result=result,
        )
    )
    payload["sizing_stage"] = "future_stage"
    with pytest.raises(ValueError, match="sizing_stage"):
        parse_context_budget_evaluated_payload(payload)

    with open_host_durable_store(_options(tmp_path)) as store:
        event_log = EventLogStore()

        def _seed_and_corrupt(transaction: HostTransaction) -> str:
            """写入fact后破坏pressure字段。

            :param transaction: 当前write transaction。
            :returns: event id。
            :raises Exception: durable写入错误时透传。
            """

            row = append_context_budget_evaluated_in_transaction(
                transaction,
                event_log,
                session_id="session-budget",
                run_id="run-budget",
                attempt_id="attempt-budget",
                execution_id="execution-budget",
                occurred_at=_NOW,
                result=result,
            )
            corrupted = dict(
                build_context_budget_evaluated_payload(
                    run_id="run-budget",
                    result=result,
                )
            )
            corrupted["pressure_level"] = "hard_threshold_exceeded"
            transaction.execute(
                f"UPDATE {TABLE_EVENT_LOG} SET payload_json = ? WHERE event_id = ?",
                (canonical_json_dumps(corrupted), row.event_id),
            )
            return row.event_id

        event_id = store.transaction_runner.run_write(_seed_and_corrupt)

        def _project(transaction: HostTransaction) -> None:
            """读取并投影损坏fact。

            :param transaction: 当前read transaction。
            :returns: ``None``。
            :raises HostDurableError: strict public projection拒绝损坏payload。
            """

            row = event_log.read_event_by_id(transaction, event_id)
            assert row is not None
            _host_event_from_row(transaction, row)

        with pytest.raises(HostDurableError, match="canonical payload"):
            store.transaction_runner.run_read(_project)


def test_event_identity_uses_frozen_atoms_only() -> None:
    """event id不消费occurred_at、raw usage或public formatting。"""

    result = _sizing(stage=ContextSizingStage.CONTINUATION, tokens=100)
    payload = parse_context_budget_evaluated_payload(
        build_context_budget_evaluated_payload(
            run_id="run-budget",
            result=result,
        )
    )
    identity = ContextBudgetEvaluationIdentity(
        run_id=payload.run_id,
        candidate_input_cursor=payload.candidate_input_cursor,
        candidate_input_digest=payload.candidate_input_digest,
        sizing_stage=payload.sizing_stage,
        policy_snapshot_digest=payload.policy_snapshot_digest,
        estimator_id=payload.estimator_id,
        estimator_version=payload.estimator_version,
    )

    assert context_budget_evaluated_event_id(identity).endswith(
        payload.decision_id.removeprefix("sha256:")
    )
    assert CONTEXT_BUDGET_EVALUATED == "CONTEXT_BUDGET_EVALUATED"


def _sizing(
    *,
    stage: ContextSizingStage,
    tokens: int,
) -> ContextSizingResult:
    """构造完整conservative sizing fixture。

    :param stage: sizing stage。
    :param tokens: conservative tokens。
    :returns: ``ContextSizingResult``。
    :raises Exception: fixture违反production contract时透传。
    """

    policy = default_context_budget_policy(context_window_size=1_000)
    soft = 650
    hard = 900
    overage = (
        ContextBudgetOverageReason.HARD_THRESHOLD
        if tokens >= hard
        else (
            ContextBudgetOverageReason.SOFT_THRESHOLD
            if tokens >= soft
            else None
        )
    )
    return build_conservative_context_sizing_result(
        stage=stage,
        candidate_input_cursor=11,
        candidate_input_projection_ref="candidate:projection",
        candidate_input_digest=_CANDIDATE_DIGEST,
        policy=policy,
        estimate=BudgetEstimate(
            estimated_input_tokens=tokens,
            input_budget_tokens=1_000,
            soft_threshold_tokens=soft,
            hard_threshold_tokens=hard,
            safety_margin_tokens=350,
            estimator_digest=_ESTIMATOR_DIGEST,
            overage_reason=overage,
        ),
    )


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造fresh durable store options。

    :param tmp_path: pytest临时目录。
    :returns: Host durable options。
    :raises Exception: 不主动抛出异常。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(
            artifact_root=tmp_path / "artifacts"
        ),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )
