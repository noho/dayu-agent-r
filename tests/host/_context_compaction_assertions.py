"""Host context compaction 测试共享断言。"""

from __future__ import annotations

from collections.abc import Mapping

from dayu.contracts.json_value import JsonValue


def assert_failed_payload_no_fallback(
    payload: Mapping[str, JsonValue],
    *,
    expected_operation_id: str | None,
    expected_attempt_count: int,
    expected_retry_repair_budget_exhausted: bool,
) -> None:
    """断言 failed payload 使用无 fallback 的诊断形态。

    :param payload: ``CONTEXT_COMPACTION_FAILED`` payload。
    :param expected_operation_id: 期望 operation id；不需要精确匹配时为
        ``None``。
    :param expected_attempt_count: 期望 rejected attempt count。
    :param expected_retry_repair_budget_exhausted: 期望 retry / repair 预算耗尽标记。
    :returns: ``None``。
    :raises AssertionError: payload 字段不符合无 fallback 诊断形态时抛出。
    """

    operation_id = payload["operation_id"]
    assert isinstance(operation_id, str)
    assert operation_id != ""
    if expected_operation_id is not None:
        assert operation_id == expected_operation_id
    assert payload["attempt_count"] == expected_attempt_count
    assert (
        payload["retry_repair_budget_exhausted"]
        is expected_retry_repair_budget_exhausted
    )
    assert payload["fallback_policy_decision"] is None
    assert payload["fallback_input_window"] is None
    assert payload["fallback_input_digest"] is None
    assert payload["fallback_budget_result"] is None
    assert payload["fallback_action"] == "not_applicable"
