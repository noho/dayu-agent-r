"""Host context budget policy 与 conservative estimator 测试。"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from dayu.host.context_budget import (
    BudgetEstimate,
    BudgetEstimateInput,
    BudgetJsonFragment,
    BudgetTextFragment,
    ContextBudgetDecision,
    ContextBudgetOverageReason,
    DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS,
    DEFAULT_INPUT_SOFT_THRESHOLD_RATIO,
    UsageObservation,
    USAGE_OBSERVATION_STATUS_ESTIMATE_UNAVAILABLE,
    USAGE_OBSERVATION_STATUS_OBSERVED,
    build_usage_observation_diagnostic,
    decide_context_budget,
    estimate_context_budget,
)
from dayu.host.context_policy import (
    ContextBudgetPolicy,
    ContextCompactionTriggerSource,
    DEFAULT_SOFT_THRESHOLD_CONTEXT_RATIO,
    StaticContextBudgetProvider,
    default_context_budget_policy,
)
from dayu.host.durable.connection import open_host_durable_store
from dayu.host.durable.errors import HostDurableError
from dayu.host.durable.event_log import (
    EventClass,
    EventLogAppendRequest,
    EventPayloadTextEqualsFilter,
    EventLogStore,
    count_committed_events_by_run_and_type,
)
from dayu.host.durable.options import (
    HostDurableStoreOptions,
    HostSQLiteStoragePolicy,
    PayloadStoragePolicy,
)
from dayu.host.durable.schema import TABLE_EVENT_LOG
from dayu.host.durable.transaction import HostTransaction

_NOW = datetime(2026, 5, 18, 1, 2, 3, tzinfo=UTC)
_TRIGGER_SOURCE_VALUES = tuple(source.value for source in ContextCompactionTriggerSource)


def test_default_policy_computes_budget_thresholds_and_digest() -> None:
    """默认 policy 基于显式窗口和 ratio 计算预算阈值。"""

    policy = default_context_budget_policy(context_window_size=2048)
    estimate = estimate_context_budget(
        policy,
        BudgetEstimateInput(
            session_id="session-budget",
            run_id="run-budget",
            message_fragments=(
                BudgetTextFragment(fragment_ref="message:1", text="abcdef"),
            ),
        ),
    )

    assert estimate.input_budget_tokens == 2048
    assert estimate.soft_threshold_tokens == 1638
    assert estimate.hard_threshold_tokens == 1843
    assert estimate.safety_margin_tokens == 410
    assert estimate.estimator_digest.startswith("sha256:")
    assert DEFAULT_INPUT_SOFT_THRESHOLD_RATIO == DEFAULT_SOFT_THRESHOLD_CONTEXT_RATIO
    assert decide_context_budget(estimate) == ContextBudgetDecision.ALLOW_DISPATCH


def test_static_context_budget_provider_returns_configured_policy() -> None:
    """静态 provider 返回装配时传入的 typed policy。"""

    policy = default_context_budget_policy(context_window_size=2048)
    provider = StaticContextBudgetProvider(policy=policy)

    assert provider.context_budget_policy() is policy


def test_static_context_budget_provider_rejects_invalid_policy() -> None:
    """静态 provider 拒绝非 ContextBudgetPolicy 输入。"""

    with pytest.raises(TypeError, match="StaticContextBudgetProvider.policy"):
        StaticContextBudgetProvider(
            policy=cast(ContextBudgetPolicy, "bad-policy")
        )


@pytest.mark.parametrize(
    ("context_window_size", "soft_ratio", "hard_ratio", "error"),
    (
        (0, 0.8, 0.9, ValueError),
        (-1, 0.8, 0.9, ValueError),
        (1024, 0.0, 0.9, ValueError),
        (1024, -0.1, 0.9, ValueError),
        (1024, 0.9, 0.9, ValueError),
        (1024, 0.95, 0.9, ValueError),
    ),
)
def test_invalid_policy_rejects_bad_window_or_threshold_ratios(
    context_window_size: int,
    soft_ratio: float,
    hard_ratio: float,
    error: type[Exception],
) -> None:
    """无效窗口或阈值 ratio 在 policy 构造期失败。"""

    with pytest.raises(error):
        default_context_budget_policy(
            context_window_size=context_window_size,
            soft_threshold_context_ratio=soft_ratio,
            hard_threshold_context_ratio=hard_ratio,
        )


def test_soft_threshold_requests_compaction() -> None:
    """估算输入达到 soft threshold 时返回 compact 决策。"""

    policy = default_context_budget_policy(
        context_window_size=1500,
        soft_threshold_context_ratio=0.8,
        hard_threshold_context_ratio=0.9,
    )
    estimate = estimate_context_budget(
        policy,
        BudgetEstimateInput(
            session_id="session-budget",
            run_id="run-budget",
            message_fragments=(
                BudgetTextFragment(fragment_ref="message:soft", text="x" * 3600),
            ),
        ),
    )

    assert estimate.soft_threshold_tokens == 1200
    assert estimate.hard_threshold_tokens == 1350
    assert estimate.overage_reason == ContextBudgetOverageReason.SOFT_THRESHOLD
    assert decide_context_budget(estimate) == (
        ContextBudgetDecision.COMPACT_SOFT_THRESHOLD
    )


def test_hard_threshold_blocks_dispatch() -> None:
    """估算输入达到 hard threshold 时优先返回 block 决策。"""

    policy = default_context_budget_policy(
        context_window_size=1500,
        soft_threshold_context_ratio=0.8,
        hard_threshold_context_ratio=0.9,
    )
    estimate = estimate_context_budget(
        policy,
        BudgetEstimateInput(
            session_id="session-budget",
            run_id="run-budget",
            message_fragments=(
                BudgetTextFragment(fragment_ref="message:hard", text="x" * 4050),
            ),
        ),
    )

    assert estimate.overage_reason == ContextBudgetOverageReason.HARD_THRESHOLD
    assert decide_context_budget(estimate) == ContextBudgetDecision.BLOCK_HARD_THRESHOLD


def test_hard_threshold_ratio_derives_threshold() -> None:
    """hard threshold ratio 直接从 context window 派生阈值。"""

    policy = default_context_budget_policy(
        context_window_size=2048,
        soft_threshold_context_ratio=0.5,
        hard_threshold_context_ratio=0.75,
    )
    estimate = estimate_context_budget(
        policy,
        BudgetEstimateInput(
            session_id="session-budget",
            run_id="run-budget",
            message_fragments=(),
            json_fragments=(
                BudgetJsonFragment(
                    fragment_ref="memory:cursor",
                    value={"cursor": 1, "summary": "ok"},
                ),
            ),
        ),
    )

    assert estimate.input_budget_tokens == 2048
    assert estimate.hard_threshold_tokens == 1536


def test_hard_threshold_ratio_one_allows_threshold_at_context_window() -> None:
    """hard_threshold_context_ratio=1 允许 hard threshold 等于 context window。"""

    policy = default_context_budget_policy(
        context_window_size=1000,
        soft_threshold_context_ratio=0.8,
        hard_threshold_context_ratio=1.0,
    )
    estimate = estimate_context_budget(
        policy,
        BudgetEstimateInput(
            session_id="session-budget",
            run_id="run-budget",
            message_fragments=(),
        ),
    )

    assert estimate.input_budget_tokens == 1000
    assert estimate.soft_threshold_tokens == 800
    assert estimate.hard_threshold_tokens == 1000
    assert estimate.safety_margin_tokens == 200


def test_budget_estimate_rejects_non_dispatchable_hard_threshold() -> None:
    """BudgetEstimate 拒绝 compact 后无法留下正预算的 hard threshold。"""

    with pytest.raises(ValueError, match="hard_threshold_tokens"):
        BudgetEstimate(
            estimated_input_tokens=0,
            input_budget_tokens=2,
            soft_threshold_tokens=1,
            hard_threshold_tokens=1,
            safety_margin_tokens=1,
            estimator_digest="sha256:" + "1" * 64,
            overage_reason=None,
        )


def test_small_soft_threshold_ratio_keeps_positive_soft_threshold() -> None:
    """soft ratio 很小时 soft threshold 仍保持正数边界。"""

    policy = default_context_budget_policy(
        context_window_size=260,
        soft_threshold_context_ratio=0.001,
        hard_threshold_context_ratio=0.5,
    )
    estimate = estimate_context_budget(
        policy,
        BudgetEstimateInput(
            session_id="session-budget",
            run_id="run-budget",
            message_fragments=(),
        ),
    )

    assert estimate.input_budget_tokens == 260
    assert estimate.soft_threshold_tokens == 1


def test_tool_schema_estimation_adds_schema_overhead() -> None:
    """工具 schema 片段估算包含 schema 专用 overhead。"""

    policy = default_context_budget_policy(context_window_size=2048)
    estimate = estimate_context_budget(
        policy,
        BudgetEstimateInput(
            session_id="session-budget",
            run_id="run-budget",
            message_fragments=(),
            tool_schema_fragments=(
                BudgetJsonFragment(fragment_ref="tool-schema:1", value={}),
            ),
        ),
    )

    assert estimate.estimated_input_tokens == (
        DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS + 1
    )


def test_usage_observation_does_not_adjust_threshold_decision() -> None:
    """UsageObservation 只是 observation，不改变已有估算阈值决策。"""

    estimate = BudgetEstimate(
        estimated_input_tokens=810,
        input_budget_tokens=1000,
        soft_threshold_tokens=800,
        hard_threshold_tokens=900,
        safety_margin_tokens=200,
        estimator_digest="sha256:" + "1" * 64,
        overage_reason=ContextBudgetOverageReason.SOFT_THRESHOLD,
    )
    observation = UsageObservation(
        session_id="session-budget",
        run_id="run-budget",
        attempt_id="attempt-budget",
        execution_id="execution-budget",
        iteration_id="iter-budget",
        prompt_tokens=950,
        completion_tokens=20,
        total_tokens=970,
        provider_request_id="provider-1",
        estimator_digest=estimate.estimator_digest,
        policy_ref="policy-1",
        observed_at=_NOW,
    )

    assert observation.total_tokens == 970
    assert decide_context_budget(estimate) == (
        ContextBudgetDecision.COMPACT_SOFT_THRESHOLD
    )


def test_usage_observation_diagnostic_reports_prompt_delta() -> None:
    """usage observation diagnostic 只报告估算校准差值。"""

    estimate = BudgetEstimate(
        estimated_input_tokens=810,
        input_budget_tokens=1000,
        soft_threshold_tokens=800,
        hard_threshold_tokens=900,
        safety_margin_tokens=200,
        estimator_digest="sha256:" + "1" * 64,
        overage_reason=ContextBudgetOverageReason.SOFT_THRESHOLD,
    )
    observation = UsageObservation(
        session_id="session-budget",
        run_id="run-budget",
        attempt_id="attempt-budget",
        execution_id="execution-budget",
        iteration_id="iter-budget",
        prompt_tokens=950,
        completion_tokens=20,
        total_tokens=970,
        provider_request_id="provider-1",
        estimator_digest=estimate.estimator_digest,
        policy_ref="policy-1",
        observed_at=_NOW,
    )

    diagnostic = build_usage_observation_diagnostic(
        observation,
        estimated_input_tokens=estimate.estimated_input_tokens,
        status=USAGE_OBSERVATION_STATUS_OBSERVED,
    )
    next_iteration_observation = UsageObservation(
        session_id="session-budget",
        run_id="run-budget",
        attempt_id="attempt-budget",
        execution_id="execution-budget",
        iteration_id="iter-budget-next",
        prompt_tokens=950,
        completion_tokens=20,
        total_tokens=970,
        provider_request_id="provider-1",
        estimator_digest=estimate.estimator_digest,
        policy_ref="policy-1",
        observed_at=_NOW,
    )
    next_iteration_diagnostic = build_usage_observation_diagnostic(
        next_iteration_observation,
        estimated_input_tokens=estimate.estimated_input_tokens,
        status=USAGE_OBSERVATION_STATUS_OBSERVED,
    )

    assert diagnostic.observation_digest.startswith("sha256:")
    assert next_iteration_diagnostic.observation_digest != diagnostic.observation_digest
    assert diagnostic.estimator_digest == estimate.estimator_digest
    assert diagnostic.policy_ref == "policy-1"
    assert diagnostic.estimated_input_tokens == 810
    assert diagnostic.prompt_token_delta == 140
    assert diagnostic.status == USAGE_OBSERVATION_STATUS_OBSERVED
    assert decide_context_budget(estimate) == (
        ContextBudgetDecision.COMPACT_SOFT_THRESHOLD
    )


def test_usage_observation_diagnostic_missing_estimate_has_no_delta() -> None:
    """缺少估算时 usage observation diagnostic 不报告 token 差值。"""

    observation = UsageObservation(
        session_id="session-budget",
        run_id="run-budget",
        attempt_id="attempt-budget",
        execution_id="execution-budget",
        iteration_id="iter-budget",
        prompt_tokens=950,
        completion_tokens=20,
        total_tokens=970,
        provider_request_id=None,
        estimator_digest=None,
        policy_ref="none",
        observed_at=_NOW,
    )

    diagnostic = build_usage_observation_diagnostic(
        observation,
        estimated_input_tokens=None,
        status=USAGE_OBSERVATION_STATUS_ESTIMATE_UNAVAILABLE,
    )

    assert diagnostic.observation_digest.startswith("sha256:")
    assert diagnostic.estimator_digest is None
    assert diagnostic.policy_ref == "none"
    assert diagnostic.estimated_input_tokens is None
    assert diagnostic.prompt_token_delta is None
    assert diagnostic.status == USAGE_OBSERVATION_STATUS_ESTIMATE_UNAVAILABLE


def test_count_committed_context_compaction_events_by_trigger_source(
    tmp_path: Path,
) -> None:
    """EventLog helper 按 Run、event type 与 trigger_source 统计 committed facts。"""

    with open_host_durable_store(_options(tmp_path)) as store:

        def _operation(transaction: HostTransaction) -> int:
            event_log = EventLogStore()
            _append_compaction_requested(
                event_log,
                transaction,
                event_id="event-context-proactive",
                trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            )
            _append_compaction_requested(
                event_log,
                transaction,
                event_id="event-context-reactive",
                trigger_source=ContextCompactionTriggerSource.REACTIVE,
            )
            return count_committed_events_by_run_and_type(
                transaction,
                run_id="run-budget",
                event_type="CONTEXT_COMPACTION_REQUESTED",
                payload_filter=EventPayloadTextEqualsFilter(
                    field_name="trigger_source",
                    expected_value=ContextCompactionTriggerSource.PROACTIVE.value,
                    allowed_values=_TRIGGER_SOURCE_VALUES,
                ),
            )

        assert store.transaction_runner.run_write(_operation) == 1


@pytest.mark.parametrize(
    ("payload_json", "case_id"),
    (
        ("{}", "missing-trigger-source"),
        ('{"trigger_source":"manual"}', "invalid-trigger-source"),
        ('{"trigger_source":""}', "empty-trigger-source"),
    ),
)
def test_count_committed_context_compaction_events_fail_closed_for_bad_payload(
    tmp_path: Path,
    payload_json: str,
    case_id: str,
) -> None:
    """EventLog helper 对受损 trigger_source payload fail-closed。"""

    with open_host_durable_store(_options(tmp_path)) as store:

        def _operation(transaction: HostTransaction) -> None:
            event_log = EventLogStore()
            event_id = f"event-context-corrupt-{case_id}"
            _append_compaction_requested(
                event_log,
                transaction,
                event_id=event_id,
                trigger_source=ContextCompactionTriggerSource.PROACTIVE,
            )
            _replace_inline_payload_json(
                transaction,
                event_id=event_id,
                payload_json=payload_json,
            )
            count_committed_events_by_run_and_type(
                transaction,
                run_id="run-budget",
                event_type="CONTEXT_COMPACTION_REQUESTED",
                payload_filter=EventPayloadTextEqualsFilter(
                    field_name="trigger_source",
                    expected_value=ContextCompactionTriggerSource.PROACTIVE.value,
                    allowed_values=_TRIGGER_SOURCE_VALUES,
                ),
            )

        with pytest.raises(HostDurableError, match="payload filter field"):
            store.transaction_runner.run_write(_operation)


def _append_compaction_requested(
    event_log: EventLogStore,
    transaction: HostTransaction,
    *,
    event_id: str,
    trigger_source: ContextCompactionTriggerSource,
) -> None:
    """追加测试用 CONTEXT_COMPACTION_REQUESTED fact。

    :param event_log: EventLog store。
    :param transaction: 当前 transaction。
    :param event_id: 事件 id。
    :param trigger_source: compaction 触发来源。
    :returns: ``None``。
    """

    event_log.append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id="session-budget",
            run_id="run-budget",
            attempt_id=None,
            execution_id=None,
            event_type="CONTEXT_COMPACTION_REQUESTED",
            occurred_at=_NOW,
            actor="tester",
            source="pytest",
            client_request_id=None,
            idempotency_key=event_id,
            policy_decision=None,
            reason=None,
            payload_json={"trigger_source": trigger_source.value},
            payload_ref=None,
            payload_digest=None,
        ),
    )


def _replace_inline_payload_json(
    transaction: HostTransaction,
    *,
    event_id: str,
    payload_json: str,
) -> None:
    """在测试中直接替换 inline payload，模拟已落库受损 row。

    :param transaction: 当前 transaction。
    :param event_id: 目标事件 id。
    :param payload_json: 要写入的 payload_json 文本。
    :returns: ``None``。
    """

    transaction.execute(
        f"""
        UPDATE {TABLE_EVENT_LOG}
        SET payload_json = ?
        WHERE event_id = ?
        """,
        (payload_json, event_id),
    )


def _options(tmp_path: Path) -> HostDurableStoreOptions:
    """构造测试 durable store options。

    :param tmp_path: pytest 临时目录。
    :returns: Host durable store options。
    """

    return HostDurableStoreOptions(
        db_path=tmp_path / "durable.sqlite3",
        payload_policy=PayloadStoragePolicy(artifact_root=tmp_path / "artifacts"),
        sqlite_policy=HostSQLiteStoragePolicy(
            busy_timeout_seconds=0.25,
            write_busy_retry_count=3,
            write_retry_initial_delay_seconds=0.001,
            write_retry_backoff_multiplier=1.2,
            write_retry_max_delay_seconds=0.01,
        ),
    )
