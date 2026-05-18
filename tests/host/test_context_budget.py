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
    decide_context_budget,
    estimate_context_budget,
)
from dayu.host.context_policy import (
    ContextBudgetPolicy,
    ContextCompactionTriggerSource,
    DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO,
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
    """默认 policy 基于显式窗口和输出预留计算预算阈值。"""

    policy = default_context_budget_policy(
        context_window_size=2048,
        reserved_output_tokens=512,
    )
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

    assert estimate.input_budget_tokens == 1536
    assert estimate.soft_threshold_tokens == 1228
    assert estimate.hard_threshold_tokens == 1280
    assert estimate.safety_margin_tokens == 308
    assert estimate.estimator_digest.startswith("sha256:")
    assert DEFAULT_INPUT_SOFT_THRESHOLD_RATIO == (
        1.0 - DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO
    )
    assert decide_context_budget(estimate) == ContextBudgetDecision.ALLOW_DISPATCH


def test_static_context_budget_provider_returns_configured_policy() -> None:
    """静态 provider 返回装配时传入的 typed policy。"""

    policy = default_context_budget_policy(
        context_window_size=2048,
        reserved_output_tokens=512,
    )
    provider = StaticContextBudgetProvider(policy=policy)

    assert provider.context_budget_policy() is policy


def test_static_context_budget_provider_rejects_invalid_policy() -> None:
    """静态 provider 拒绝非 ContextBudgetPolicy 输入。"""

    with pytest.raises(TypeError, match="StaticContextBudgetProvider.policy"):
        StaticContextBudgetProvider(
            policy=cast(ContextBudgetPolicy, "bad-policy")
        )


@pytest.mark.parametrize(
    ("context_window_size", "reserved_output_tokens", "error"),
    (
        (0, 128, ValueError),
        (-1, 128, ValueError),
        (1024, 0, ValueError),
        (1024, -1, ValueError),
        (1024, 1024, ValueError),
        (1024, 2048, ValueError),
    ),
)
def test_invalid_policy_rejects_bad_window_or_reserved_tokens(
    context_window_size: int,
    reserved_output_tokens: int,
    error: type[Exception],
) -> None:
    """无效窗口或输出预留在 policy 构造期失败。"""

    with pytest.raises(error):
        default_context_budget_policy(
            context_window_size=context_window_size,
            reserved_output_tokens=reserved_output_tokens,
        )


def test_soft_threshold_requests_compaction() -> None:
    """估算输入达到 soft threshold 时返回 compact 决策。"""

    policy = default_context_budget_policy(
        context_window_size=1500,
        reserved_output_tokens=500,
        hard_threshold_tokens=900,
    )
    estimate = estimate_context_budget(
        policy,
        BudgetEstimateInput(
            session_id="session-budget",
            run_id="run-budget",
            message_fragments=(
                BudgetTextFragment(fragment_ref="message:soft", text="x" * 2400),
            ),
        ),
    )

    assert estimate.soft_threshold_tokens == 800
    assert estimate.hard_threshold_tokens == 900
    assert estimate.overage_reason == ContextBudgetOverageReason.SOFT_THRESHOLD
    assert decide_context_budget(estimate) == (
        ContextBudgetDecision.COMPACT_SOFT_THRESHOLD
    )


def test_hard_threshold_blocks_dispatch() -> None:
    """估算输入达到 hard threshold 时优先返回 block 决策。"""

    policy = default_context_budget_policy(
        context_window_size=1500,
        reserved_output_tokens=500,
        hard_threshold_tokens=900,
    )
    estimate = estimate_context_budget(
        policy,
        BudgetEstimateInput(
            session_id="session-budget",
            run_id="run-budget",
            message_fragments=(
                BudgetTextFragment(fragment_ref="message:hard", text="x" * 2700),
            ),
        ),
    )

    assert estimate.overage_reason == ContextBudgetOverageReason.HARD_THRESHOLD
    assert decide_context_budget(estimate) == ContextBudgetDecision.BLOCK_HARD_THRESHOLD


def test_explicit_hard_threshold_overrides_minimum_protection() -> None:
    """显式 hard threshold 优先于默认最小保护量计算。"""

    policy = default_context_budget_policy(
        context_window_size=2048,
        reserved_output_tokens=512,
        hard_threshold_tokens=1400,
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

    assert estimate.input_budget_tokens == 1536
    assert estimate.hard_threshold_tokens == 1400


def test_minimum_protection_tokens_zero_allows_hard_threshold_at_input_budget() -> None:
    """minimum_protection_tokens=0 是显式非负策略，允许 hard threshold 等于输入预算。"""

    policy = default_context_budget_policy(
        context_window_size=1000,
        reserved_output_tokens=200,
        safety_margin_ratio=0.0,
        minimum_protection_tokens=0,
    )
    estimate = estimate_context_budget(
        policy,
        BudgetEstimateInput(
            session_id="session-budget",
            run_id="run-budget",
            message_fragments=(),
        ),
    )

    assert estimate.input_budget_tokens == 800
    assert estimate.soft_threshold_tokens == 800
    assert estimate.hard_threshold_tokens == 800
    assert estimate.safety_margin_tokens == 0


def test_safety_margin_ratio_near_one_keeps_positive_soft_threshold() -> None:
    """safety_margin_ratio 接近 1 时 soft threshold 仍保持正数边界。"""

    policy = default_context_budget_policy(
        context_window_size=260,
        reserved_output_tokens=4,
        safety_margin_ratio=0.999,
        minimum_protection_tokens=1,
    )
    estimate = estimate_context_budget(
        policy,
        BudgetEstimateInput(
            session_id="session-budget",
            run_id="run-budget",
            message_fragments=(),
        ),
    )

    assert estimate.input_budget_tokens == 256
    assert estimate.soft_threshold_tokens == 1


def test_tool_schema_estimation_adds_schema_overhead() -> None:
    """工具 schema 片段估算包含 schema 专用 overhead。"""

    policy = default_context_budget_policy(
        context_window_size=2048,
        reserved_output_tokens=512,
    )
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
