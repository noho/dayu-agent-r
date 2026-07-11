"""Host accepted tool outcome codec owner 测试。"""

from __future__ import annotations

from datetime import UTC, datetime

from dayu.contracts.tool_outcome import (
    ToolCancelledOutcome,
    ToolCompletedOutcome,
    ToolFailedOutcome,
)
from dayu.contracts.tool_result import ToolResultFailure, ToolResultSuccess
from dayu.host.accepted_tool_outcome import (
    AcceptedToolOutcome,
    accepted_tool_outcome_digest,
    accepted_tool_outcome_json,
)
from dayu.host.api import (
    HostCallContext,
    HostPayloadRef,
    OperationContext,
    ResolveWaitCancelledOutcome,
    ResolveWaitCompletedOutcome,
    ResolveWaitFailedOutcome,
    ResolveWaitOutcome,
    ResolveWaitRequest,
    WaitResolutionSource,
)
from dayu.host.durable.codec import sha256_digest_json
from dayu.host.tool_runtime import _tool_outcome_digest, _tool_outcome_json
from dayu.host.waiting import _wait_resolution_payload_plan


def test_completed_failed_cancelled_share_single_accepted_outcome_atom() -> None:
    """普通工具路径与 wait resolution 路径复用同一 accepted outcome atom。

    :returns: ``None``。
    :raises AssertionError: 任一 producer 偏离 shared codec 时抛出。
    """

    completed = ToolCompletedOutcome(
        ToolResultSuccess(ok=True, value={"answer": 42}, meta=None)
    )
    _assert_wait_plan_matches_ordinary_tool_outcome(
        completed,
        ResolveWaitCompletedOutcome(result=completed.result, payload_ref=None),
    )
    failed = ToolFailedOutcome(
        ToolResultFailure(
            ok=False,
            error="provider_failed",
            message="provider failed",
            hint="retry later",
            meta=None,
        )
    )
    _assert_wait_plan_matches_ordinary_tool_outcome(
        failed,
        ResolveWaitFailedOutcome(result=failed.result, payload_ref=None),
    )
    cancelled = ToolCancelledOutcome(
        reason="timeout",
        message="tool timed out",
        hint=None,
        meta=None,
    )
    _assert_wait_plan_matches_ordinary_tool_outcome(
        cancelled,
        ResolveWaitCancelledOutcome(result=cancelled, payload_ref=None),
    )


def test_cancelled_wait_payload_ref_does_not_reshape_accepted_atom() -> None:
    """cancelled payload_ref 只影响 wait envelope，不改变 accepted outcome atom。

    :returns: ``None``。
    :raises AssertionError: payload ref 改变 accepted atom 时抛出。
    """

    outcome = ToolCancelledOutcome(
        reason="timeout",
        message="tool timed out",
        hint="check provider status",
        meta=None,
    )
    payload_ref = HostPayloadRef(
        payload_ref="payload-cancelled",
        payload_digest=sha256_digest_json({"cancelled": True}),
    )
    request = _request(
        ResolveWaitCancelledOutcome(result=outcome, payload_ref=payload_ref)
    )
    payload_plan = _wait_resolution_payload_plan(request)
    expected_atom = accepted_tool_outcome_json(outcome)

    assert payload_plan.result_json == expected_atom
    assert payload_plan.outcome_digest == accepted_tool_outcome_digest(outcome)
    assert payload_plan.payload_ref == payload_ref
    assert payload_plan.payload_digest == payload_ref.payload_digest
    assert payload_plan.result_json == {
        "kind": "cancelled",
        "reason": "timeout",
        "message": "tool timed out",
        "hint": "check provider status",
        "meta": None,
    }


def _assert_wait_plan_matches_ordinary_tool_outcome(
    outcome: AcceptedToolOutcome,
    wait_outcome: ResolveWaitOutcome,
) -> None:
    """断言 ordinary 与 wait producer 使用同一 canonical atom。

    :param outcome: 普通 ToolRuntime accepted outcome。
    :param wait_outcome: wait resolution outcome envelope。
    :returns: ``None``。
    :raises AssertionError: 两条 producer 路径不一致时抛出。
    """

    expected_atom = accepted_tool_outcome_json(outcome)
    expected_digest = accepted_tool_outcome_digest(outcome)
    payload_plan = _wait_resolution_payload_plan(_request(wait_outcome))

    assert _tool_outcome_json(outcome) == expected_atom
    assert _tool_outcome_digest(outcome) == expected_digest
    assert payload_plan.result_json == expected_atom
    assert payload_plan.outcome_digest == expected_digest


def _request(outcome: ResolveWaitOutcome) -> ResolveWaitRequest:
    """构造 resolve wait request。

    :param outcome: resolve wait outcome。
    :returns: resolve wait request。
    :raises TypeError: outcome 类型非法时由请求契约抛出。
    :raises ValueError: 请求字段非法时由请求契约抛出。
    """

    return ResolveWaitRequest(
        context=HostCallContext(
            actor="pytest",
            source="tests.host.test_accepted_tool_outcome_codec",
            request_id="operation-codec-test",
            authorization_claims=(),
            operation_context=OperationContext(
                operation_name="resolve_wait",
                operation_kind="test",
                business_domain="host",
                business_object_type=None,
                business_object_id=None,
                scenario="accepted_tool_outcome_codec",
                correlation_id=None,
            ),
        ),
        idempotency_key="resolve-codec-test",
        outcome=outcome,
        source=WaitResolutionSource.MANUAL,
        observed_at=datetime(2026, 5, 16, 1, 5, 7, tzinfo=UTC),
    )
