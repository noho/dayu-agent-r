"""Host context governance canonical event payload helpers。

本模块集中定义 Context Governance budget / compact canonical fact 的 payload
builder、strict parser 与 deterministic append。EventLog primitive 只保存通用
ledger row；业务语义、稳定 identity 与结果一致性都由本模块拥有。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, TypeVar

from dayu.contracts.json_value import JsonValue
from dayu.host.compaction import (
    CompactQualityCheckResultVNext,
    ConversationCompactOutputVNext,
)
from dayu.host.compact_payload import parse_context_compacted_semantic_payload
from dayu.host.context_budget import (
    MAX_CONTEXT_TOKEN_COUNT,
    ContextAnchorDiagnostic,
    ContextBudgetDecision,
    ContextEstimateMethod,
    ContextPressureLevel,
    ContextSizingFallbackReason,
    ContextSizingResult,
    ContextSizingStage,
    context_sizing_pressure_and_decision,
)
from dayu.host.context_policy import ContextCompactionTriggerSource
from dayu.host.durable.codec import is_sha256_digest, sha256_digest_json
from dayu.host.durable.errors import (
    HostDurableError,
    HostEventIdentityConflictError,
)
if TYPE_CHECKING:
    from dayu.host.durable.event_log import EventLogRow, EventLogStore
    from dayu.host.durable.transaction import HostTransaction

_EnumT = TypeVar("_EnumT", bound=StrEnum)

CONTEXT_BUDGET_EVALUATED = "CONTEXT_BUDGET_EVALUATED"
"""单个 dispatch-relevant candidate 的 canonical budget truth。"""

CONTEXT_BUDGET_EVALUATED_SCHEMA_VERSION = "context_budget_evaluated.v1"
"""Context budget canonical payload fresh schema。"""

_CONTEXT_BUDGET_EVENT_ID_PREFIX = "event-context-budget-evaluated-"
_CONTEXT_BUDGET_EVENT_ACTOR = "host.context_governance"
_CONTEXT_BUDGET_EVENT_SOURCE = "host.context_budget"

_BUDGET_EVALUATED_FIELDS = (
    "schema_version",
    "decision_id",
    "run_id",
    "candidate_input_cursor",
    "candidate_input_projection_ref",
    "candidate_input_digest",
    "sizing_stage",
    "policy_ref",
    "policy_snapshot_digest",
    "estimator_id",
    "estimator_version",
    "estimator_digest",
    "conservative_input_tokens",
    "estimate_method",
    "predicted_input_tokens",
    "context_window_size",
    "utilization_basis_points",
    "soft_threshold_tokens",
    "hard_threshold_tokens",
    "pressure_level",
    "budget_decision",
    "fallback_reason",
    "anchor_diagnostic",
)
_ANCHOR_DIAGNOSTIC_FIELDS = (
    "manifest_event_id",
    "manifest_payload_ref",
    "manifest_digest",
    "iteration_link_event_id",
    "usage_event_id",
    "usage_observation_digest",
    "iteration_completed_event_id",
    "usage_anchor_tokens",
    "conservative_anchor_tokens",
    "conservative_current_tokens",
    "signed_delta_tokens",
    "predicted_input_tokens",
)


@dataclass(frozen=True, slots=True)
class ContextBudgetEvaluatedPayload:
    """Strict-parsed ``CONTEXT_BUDGET_EVALUATED`` canonical payload。

    字段与 durable v1 schema 一一对应；public projection只能读取其中明确允许的
    七字段，不能直接暴露本对象。
    """

    decision_id: str
    run_id: str
    candidate_input_cursor: int
    candidate_input_projection_ref: str
    candidate_input_digest: str
    sizing_stage: ContextSizingStage
    policy_ref: str
    policy_snapshot_digest: str
    estimator_id: str
    estimator_version: str
    estimator_digest: str
    conservative_input_tokens: int
    estimate_method: ContextEstimateMethod
    predicted_input_tokens: int
    context_window_size: int
    utilization_basis_points: int
    soft_threshold_tokens: int
    hard_threshold_tokens: int
    pressure_level: ContextPressureLevel
    budget_decision: ContextBudgetDecision
    fallback_reason: ContextSizingFallbackReason | None
    anchor_diagnostic: ContextAnchorDiagnostic | None


@dataclass(frozen=True, slots=True)
class ContextBudgetEvaluationIdentity:
    """Canonical fact deterministic identity atoms。

    :param run_id: owning Run id。
    :param candidate_input_cursor: candidate source watermark。
    :param candidate_input_digest: complete candidate digest。
    :param sizing_stage: producer-owned closed stage。
    :param policy_snapshot_digest: frozen policy identity。
    :param estimator_id: estimator id。
    :param estimator_version: estimator version。
    """

    run_id: str
    candidate_input_cursor: int
    candidate_input_digest: str
    sizing_stage: ContextSizingStage
    policy_snapshot_digest: str
    estimator_id: str
    estimator_version: str


def context_budget_evaluation_identity(
    run_id: str,
    result: ContextSizingResult,
) -> ContextBudgetEvaluationIdentity:
    """从 sizing result 提取 canonical identity atoms。

    :param run_id: owning Host Run id。
    :param result: Host-owned sizing truth。
    :returns: 不含 occurrence/Attempt 随机量的 stable identity。
    :raises TypeError: ``result`` 类型非法时抛出。
    """

    if not isinstance(result, ContextSizingResult):
        raise TypeError("result must be ContextSizingResult")
    return ContextBudgetEvaluationIdentity(
        run_id=run_id,
        candidate_input_cursor=result.candidate_input_cursor,
        candidate_input_digest=result.candidate_input_digest,
        sizing_stage=result.stage,
        policy_snapshot_digest=result.policy_snapshot_digest,
        estimator_id=result.estimator_contract.estimator_id,
        estimator_version=result.estimator_contract.estimator_version,
    )


def context_budget_evaluated_decision_id(
    identity: ContextBudgetEvaluationIdentity,
) -> str:
    """计算 canonical budget decision digest。

    :param identity: plan冻结的完整 stable identity atoms。
    :returns: ``sha256:`` canonical digest。
    :raises TypeError: identity enum/type非法时抛出。
    :raises ValueError: identity 文本、cursor或digest非法时抛出。
    """

    _validate_context_budget_identity(identity)
    return sha256_digest_json(
        {
            "run_id": identity.run_id,
            "candidate_input_cursor": identity.candidate_input_cursor,
            "candidate_input_digest": identity.candidate_input_digest,
            "sizing_stage": identity.sizing_stage.value,
            "policy_snapshot_digest": identity.policy_snapshot_digest,
            "estimator_id": identity.estimator_id,
            "estimator_version": identity.estimator_version,
        }
    )


def context_budget_evaluated_event_id(
    identity: ContextBudgetEvaluationIdentity,
) -> str:
    """从 canonical decision identity 派生稳定 EventLog id。

    :param identity: 完整 stable identity atoms。
    :returns: deterministic EventLog event id。
    :raises TypeError: identity 类型非法时抛出。
    :raises ValueError: identity 字段非法时抛出。
    """

    decision_id = context_budget_evaluated_decision_id(identity)
    return _CONTEXT_BUDGET_EVENT_ID_PREFIX + decision_id.removeprefix("sha256:")


def build_context_budget_evaluated_payload(
    *,
    run_id: str,
    result: ContextSizingResult,
) -> Mapping[str, JsonValue]:
    """从唯一 sizing truth 构造 canonical payload。

    本 builder不选择usage、不读取EventLog anchor，也不改变result中的
    pressure/action。

    :param run_id: owning Host Run id。
    :param result: complete conservative sizing truth。
    :returns: strict v1 canonical JSON payload。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: result或identity不满足canonical contract时抛出。
    """

    if not isinstance(result, ContextSizingResult):
        raise TypeError("result must be ContextSizingResult")
    identity = ContextBudgetEvaluationIdentity(
        run_id=run_id,
        candidate_input_cursor=result.candidate_input_cursor,
        candidate_input_digest=result.candidate_input_digest,
        sizing_stage=result.stage,
        policy_snapshot_digest=result.policy_snapshot_digest,
        estimator_id=result.estimator_contract.estimator_id,
        estimator_version=result.estimator_contract.estimator_version,
    )
    payload: Mapping[str, JsonValue] = {
        "schema_version": CONTEXT_BUDGET_EVALUATED_SCHEMA_VERSION,
        "decision_id": context_budget_evaluated_decision_id(identity),
        "run_id": run_id,
        "candidate_input_cursor": result.candidate_input_cursor,
        "candidate_input_projection_ref": (
            result.candidate_input_projection_ref
        ),
        "candidate_input_digest": result.candidate_input_digest,
        "sizing_stage": result.stage.value,
        "policy_ref": result.policy_ref,
        "policy_snapshot_digest": result.policy_snapshot_digest,
        "estimator_id": result.estimator_contract.estimator_id,
        "estimator_version": result.estimator_contract.estimator_version,
        "estimator_digest": result.estimator_digest,
        "conservative_input_tokens": result.conservative_input_tokens,
        "estimate_method": result.estimate_method.value,
        "predicted_input_tokens": result.predicted_input_tokens,
        "context_window_size": result.context_window_size,
        "utilization_basis_points": result.utilization_basis_points,
        "soft_threshold_tokens": result.soft_threshold_tokens,
        "hard_threshold_tokens": result.hard_threshold_tokens,
        "pressure_level": result.pressure_level.value,
        "budget_decision": result.budget_decision.value,
        "fallback_reason": (
            result.fallback_reason.value
            if result.fallback_reason is not None
            else None
        ),
        "anchor_diagnostic": _anchor_diagnostic_payload(
            result.anchor_diagnostic
        ),
    }
    parse_context_budget_evaluated_payload(payload)
    return payload


def parse_context_budget_evaluated_payload(
    payload: Mapping[str, JsonValue],
) -> ContextBudgetEvaluatedPayload:
    """Strict parse canonical budget payload。

    :param payload: EventLog inline JSON object。
    :returns: 完整 typed canonical payload。
    :raises TypeError: ``payload`` 不是mapping时抛出。
    :raises ValueError: schema、enum、identity、range或结果不变量非法时抛出。
    """

    if not isinstance(payload, Mapping):
        raise TypeError("payload must be mapping")
    _require_exact_fields(payload, _BUDGET_EVALUATED_FIELDS)
    if _required_text(payload, "schema_version") != (
        CONTEXT_BUDGET_EVALUATED_SCHEMA_VERSION
    ):
        raise ValueError("unsupported context budget evaluated schema")
    decision_id = _required_digest(payload, "decision_id")
    run_id = _required_text(payload, "run_id")
    candidate_input_cursor = _required_non_negative_int(
        payload,
        "candidate_input_cursor",
    )
    candidate_input_projection_ref = _required_text(
        payload,
        "candidate_input_projection_ref",
    )
    candidate_input_digest = _required_digest(
        payload,
        "candidate_input_digest",
    )
    sizing_stage = _required_enum(
        payload,
        "sizing_stage",
        ContextSizingStage,
    )
    policy_ref = _required_text(payload, "policy_ref")
    policy_snapshot_digest = _required_digest(
        payload,
        "policy_snapshot_digest",
    )
    estimator_id = _required_text(payload, "estimator_id")
    estimator_version = _required_text(payload, "estimator_version")
    estimator_digest = _required_digest(payload, "estimator_digest")
    conservative_input_tokens = _required_non_negative_int(
        payload,
        "conservative_input_tokens",
    )
    estimate_method = _required_enum(
        payload,
        "estimate_method",
        ContextEstimateMethod,
    )
    predicted_input_tokens = _required_non_negative_int(
        payload,
        "predicted_input_tokens",
    )
    context_window_size = _required_positive_int(
        payload,
        "context_window_size",
    )
    utilization_basis_points = _required_non_negative_int(
        payload,
        "utilization_basis_points",
    )
    soft_threshold_tokens = _required_positive_int(
        payload,
        "soft_threshold_tokens",
    )
    hard_threshold_tokens = _required_positive_int(
        payload,
        "hard_threshold_tokens",
    )
    pressure_level = _required_enum(
        payload,
        "pressure_level",
        ContextPressureLevel,
    )
    budget_decision = _required_enum(
        payload,
        "budget_decision",
        ContextBudgetDecision,
    )
    fallback_reason = _optional_enum(
        payload,
        "fallback_reason",
        ContextSizingFallbackReason,
    )
    anchor_diagnostic = _parse_anchor_diagnostic(
        payload.get("anchor_diagnostic")
    )
    identity = ContextBudgetEvaluationIdentity(
        run_id=run_id,
        candidate_input_cursor=candidate_input_cursor,
        candidate_input_digest=candidate_input_digest,
        sizing_stage=sizing_stage,
        policy_snapshot_digest=policy_snapshot_digest,
        estimator_id=estimator_id,
        estimator_version=estimator_version,
    )
    if decision_id != context_budget_evaluated_decision_id(identity):
        raise ValueError("context budget decision identity mismatch")
    if (
        conservative_input_tokens > MAX_CONTEXT_TOKEN_COUNT
        or predicted_input_tokens > MAX_CONTEXT_TOKEN_COUNT
    ):
        raise ValueError("context budget token count exceeds supported range")
    if soft_threshold_tokens > hard_threshold_tokens:
        raise ValueError("context budget thresholds are out of order")
    if utilization_basis_points != (
        predicted_input_tokens * 10_000 // context_window_size
    ):
        raise ValueError("context budget utilization mismatch")
    expected_pressure, expected_decision = context_sizing_pressure_and_decision(
        stage=sizing_stage,
        predicted_input_tokens=predicted_input_tokens,
        soft_threshold_tokens=soft_threshold_tokens,
        hard_threshold_tokens=hard_threshold_tokens,
    )
    if pressure_level is not expected_pressure:
        raise ValueError("context budget pressure mismatch")
    if budget_decision is not expected_decision:
        raise ValueError("context budget decision mismatch")
    if estimate_method is ContextEstimateMethod.CONSERVATIVE_FALLBACK:
        if (
            fallback_reason is None
            or anchor_diagnostic is not None
            or predicted_input_tokens != conservative_input_tokens
        ):
            raise ValueError("conservative context budget diagnostic mismatch")
    elif estimate_method is ContextEstimateMethod.USAGE_ANCHORED:
        if fallback_reason is not None or anchor_diagnostic is None:
            raise ValueError("anchored context budget diagnostic mismatch")
        if (
            anchor_diagnostic.conservative_current_tokens
            != conservative_input_tokens
            or anchor_diagnostic.predicted_input_tokens
            != predicted_input_tokens
        ):
            raise ValueError("anchored context budget result mismatch")
    else:
        raise AssertionError("context estimate method is not exhaustive")
    return ContextBudgetEvaluatedPayload(
        decision_id=decision_id,
        run_id=run_id,
        candidate_input_cursor=candidate_input_cursor,
        candidate_input_projection_ref=candidate_input_projection_ref,
        candidate_input_digest=candidate_input_digest,
        sizing_stage=sizing_stage,
        policy_ref=policy_ref,
        policy_snapshot_digest=policy_snapshot_digest,
        estimator_id=estimator_id,
        estimator_version=estimator_version,
        estimator_digest=estimator_digest,
        conservative_input_tokens=conservative_input_tokens,
        estimate_method=estimate_method,
        predicted_input_tokens=predicted_input_tokens,
        context_window_size=context_window_size,
        utilization_basis_points=utilization_basis_points,
        soft_threshold_tokens=soft_threshold_tokens,
        hard_threshold_tokens=hard_threshold_tokens,
        pressure_level=pressure_level,
        budget_decision=budget_decision,
        fallback_reason=fallback_reason,
        anchor_diagnostic=anchor_diagnostic,
    )


def append_context_budget_evaluated_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    session_id: str,
    run_id: str,
    attempt_id: str | None,
    execution_id: str | None,
    occurred_at: datetime,
    result: ContextSizingResult,
) -> EventLogRow:
    """幂等追加 canonical context budget fact。

    已存在同identity row时strict校验row identity与payload；完全一致才复用。
    任何矛盾都以identity conflict fail closed，不执行下游transition。

    :param transaction: caller现有write transaction。
    :param event_log_store: EventLog primitive。
    :param session_id: owning Session id。
    :param run_id: owning Run id。
    :param attempt_id: allow/continuation candidate绑定的Attempt；ordinary
        soft/hard为``None``。
    :param execution_id: allow/continuation candidate绑定的execution；ordinary
        soft/hard为``None``。
    :param occurred_at: 首次append occurrence time。
    :param result: 唯一Host sizing truth。
    :returns: 新增或幂等复用的EventLog row。
    :raises HostEventIdentityConflictError: stable identity已有矛盾row时抛出。
    :raises HostDurableError: durable payload无法strict解析时抛出。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: canonical payload或identity非法时抛出。
    """

    # api -> memory -> context_events 的初始化链早于 durable schema 完成；
    # durable primitives只能在实际append边界加载，避免公共契约导入形成环。
    from dayu.host.durable.event_log import (
        EventClass,
        EventLogAppendRequest,
    )

    payload = build_context_budget_evaluated_payload(
        run_id=run_id,
        result=result,
    )
    parsed = parse_context_budget_evaluated_payload(payload)
    identity = _identity_from_payload(parsed)
    event_id = context_budget_evaluated_event_id(identity)
    existing = event_log_store.read_event_by_id(transaction, event_id)
    if existing is not None:
        _require_matching_context_budget_row(
            transaction,
            existing,
            session_id=session_id,
            run_id=run_id,
            attempt_id=attempt_id,
            execution_id=execution_id,
            expected=parsed,
            conflict=True,
        )
        return existing
    return event_log_store.append_event(
        transaction,
        EventLogAppendRequest(
            event_id=event_id,
            event_class=EventClass.CANONICAL_FACT,
            session_id=session_id,
            run_id=run_id,
            attempt_id=attempt_id,
            execution_id=execution_id,
            event_type=CONTEXT_BUDGET_EVALUATED,
            occurred_at=occurred_at,
            actor=_CONTEXT_BUDGET_EVENT_ACTOR,
            source=_CONTEXT_BUDGET_EVENT_SOURCE,
            client_request_id=None,
            idempotency_key=parsed.decision_id,
            policy_decision=None,
            reason=None,
            payload_json=payload,
            payload_ref=None,
            payload_digest=None,
        ),
    ).row


def load_matching_context_budget_evaluation_in_transaction(
    transaction: HostTransaction,
    event_log_store: EventLogStore,
    *,
    session_id: str,
    attempt_id: str,
    execution_id: str,
    identity: ContextBudgetEvaluationIdentity,
    candidate_input_projection_ref: str,
    estimator_digest: str,
    conservative_input_tokens: int,
    context_window_size: int,
    policy_ref: str,
) -> ContextBudgetEvaluatedPayload:
    """按manifest/candidate atoms strict读取matching source budget fact。

    :param transaction: caller现有transaction。
    :param event_log_store: EventLog primitive。
    :param session_id: source Session id。
    :param attempt_id: source Attempt id。
    :param execution_id: source execution id。
    :param identity: source manifest/candidate stable identity atoms。
    :param candidate_input_projection_ref: source exact candidate ref。
    :param estimator_digest: source conservative estimate digest。
    :param conservative_input_tokens: source conservative tokens。
    :param context_window_size: source frozen context window。
    :param policy_ref: source frozen policy ref。
    :returns: strict typed matching canonical payload。
    :raises HostDurableError: source fact缺失、损坏或与manifest/candidate不一致时抛出。
    """

    event_id = context_budget_evaluated_event_id(identity)
    row = event_log_store.read_event_by_id(transaction, event_id)
    if row is None:
        raise HostDurableError("source context budget fact is missing")
    parsed = _require_matching_context_budget_row(
        transaction,
        row,
        session_id=session_id,
        run_id=identity.run_id,
        attempt_id=attempt_id,
        execution_id=execution_id,
        expected=None,
        conflict=False,
    )
    if (
        _identity_from_payload(parsed) != identity
        or parsed.candidate_input_projection_ref
        != candidate_input_projection_ref
        or parsed.estimator_digest != estimator_digest
        or parsed.conservative_input_tokens != conservative_input_tokens
        or parsed.context_window_size != context_window_size
        or parsed.policy_ref != policy_ref
    ):
        raise HostDurableError(
            "source context budget fact does not match frozen manifest"
        )
    return parsed


def _identity_from_payload(
    payload: ContextBudgetEvaluatedPayload,
) -> ContextBudgetEvaluationIdentity:
    """从strict payload提取stable identity。

    :param payload: strict canonical payload。
    :returns: stable identity atoms。
    :raises Exception: 不主动抛出异常。
    """

    return ContextBudgetEvaluationIdentity(
        run_id=payload.run_id,
        candidate_input_cursor=payload.candidate_input_cursor,
        candidate_input_digest=payload.candidate_input_digest,
        sizing_stage=payload.sizing_stage,
        policy_snapshot_digest=payload.policy_snapshot_digest,
        estimator_id=payload.estimator_id,
        estimator_version=payload.estimator_version,
    )


def _validate_context_budget_identity(
    identity: ContextBudgetEvaluationIdentity,
) -> None:
    """校验stable identity atoms。

    :param identity: 待校验identity。
    :returns: ``None``。
    :raises TypeError: dataclass或stage类型非法时抛出。
    :raises ValueError: 文本、cursor或digest非法时抛出。
    """

    if not isinstance(identity, ContextBudgetEvaluationIdentity):
        raise TypeError("identity must be ContextBudgetEvaluationIdentity")
    if not isinstance(identity.sizing_stage, ContextSizingStage):
        raise TypeError("identity.sizing_stage must be ContextSizingStage")
    _require_non_empty_text_value(identity.run_id, "identity.run_id")
    if (
        isinstance(identity.candidate_input_cursor, bool)
        or not isinstance(identity.candidate_input_cursor, int)
        or identity.candidate_input_cursor < 0
    ):
        raise ValueError("identity.candidate_input_cursor must be non-negative int")
    for field_name, value in (
        ("identity.candidate_input_digest", identity.candidate_input_digest),
        ("identity.policy_snapshot_digest", identity.policy_snapshot_digest),
    ):
        if not is_sha256_digest(value):
            raise ValueError(f"{field_name} must be sha256 digest")
    _require_non_empty_text_value(identity.estimator_id, "identity.estimator_id")
    _require_non_empty_text_value(
        identity.estimator_version,
        "identity.estimator_version",
    )


def _require_matching_context_budget_row(
    transaction: HostTransaction,
    row: EventLogRow,
    *,
    session_id: str,
    run_id: str,
    attempt_id: str | None,
    execution_id: str | None,
    expected: ContextBudgetEvaluatedPayload | None,
    conflict: bool,
) -> ContextBudgetEvaluatedPayload:
    """校验deterministic event id指向exact canonical row。

    :param transaction: 当前transaction。
    :param row: 待校验EventLog row。
    :param session_id: expected Session id。
    :param run_id: expected Run id。
    :param attempt_id: expected Attempt id。
    :param execution_id: expected execution id。
    :param expected: append幂等路径的expected payload；source读取时为``None``。
    :param conflict: 是否把不一致分类为identity conflict。
    :returns: strict parsed payload。
    :raises HostEventIdentityConflictError: append幂等identity矛盾时抛出。
    :raises HostDurableError: source durable row损坏或不匹配时抛出。
    """

    from dayu.host.durable.event_log import EventClass
    from dayu.host.payload_resolution import event_payload_object

    try:
        if (
            row.event_class is not EventClass.CANONICAL_FACT
            or row.session_id != session_id
            or row.run_id != run_id
            or row.attempt_id != attempt_id
            or row.execution_id != execution_id
            or row.event_type != CONTEXT_BUDGET_EVALUATED
            or row.actor != _CONTEXT_BUDGET_EVENT_ACTOR
            or row.source != _CONTEXT_BUDGET_EVENT_SOURCE
            or row.client_request_id is not None
            or row.policy_decision_json is not None
            or row.reason_json is not None
            or row.payload_ref is not None
            or row.payload_digest is not None
        ):
            raise ValueError("context budget EventLog row identity mismatch")
        parsed = parse_context_budget_evaluated_payload(
            event_payload_object(
                transaction,
                row,
                payload_label=CONTEXT_BUDGET_EVALUATED,
            )
        )
        if row.idempotency_key != parsed.decision_id:
            raise ValueError("context budget EventLog idempotency mismatch")
        if row.event_id != context_budget_evaluated_event_id(
            _identity_from_payload(parsed)
        ):
            raise ValueError("context budget EventLog event id mismatch")
        if expected is not None and parsed != expected:
            raise ValueError("context budget canonical result mismatch")
        return parsed
    except (HostDurableError, TypeError, ValueError) as exc:
        if conflict:
            raise HostEventIdentityConflictError(
                "context budget decision identity already has conflicting truth"
            ) from exc
        raise HostDurableError("source context budget fact is invalid") from exc


def _parse_anchor_diagnostic(value: JsonValue) -> ContextAnchorDiagnostic | None:
    """Strict parse Host-only anchor diagnostic。

    :param value: canonical JSON value。
    :returns: typed diagnostic或``None``。
    :raises ValueError: shape、ref、digest或整数范围非法时抛出。
    """

    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("anchor_diagnostic must be object or null")
    _require_exact_fields(value, _ANCHOR_DIAGNOSTIC_FIELDS)
    diagnostic = ContextAnchorDiagnostic(
        manifest_event_id=_required_text(value, "manifest_event_id"),
        manifest_payload_ref=_required_text(value, "manifest_payload_ref"),
        manifest_digest=_required_digest(value, "manifest_digest"),
        iteration_link_event_id=_required_text(
            value,
            "iteration_link_event_id",
        ),
        usage_event_id=_required_text(value, "usage_event_id"),
        usage_observation_digest=_required_digest(
            value,
            "usage_observation_digest",
        ),
        iteration_completed_event_id=_required_text(
            value,
            "iteration_completed_event_id",
        ),
        usage_anchor_tokens=_required_non_negative_int(
            value,
            "usage_anchor_tokens",
        ),
        conservative_anchor_tokens=_required_non_negative_int(
            value,
            "conservative_anchor_tokens",
        ),
        conservative_current_tokens=_required_non_negative_int(
            value,
            "conservative_current_tokens",
        ),
        signed_delta_tokens=_required_int(value, "signed_delta_tokens"),
        predicted_input_tokens=_required_positive_int(
            value,
            "predicted_input_tokens",
        ),
    )
    for token_count in (
        diagnostic.usage_anchor_tokens,
        diagnostic.conservative_anchor_tokens,
        diagnostic.conservative_current_tokens,
        diagnostic.predicted_input_tokens,
    ):
        if token_count > MAX_CONTEXT_TOKEN_COUNT:
            raise ValueError("anchor diagnostic token count exceeds supported range")
    if abs(diagnostic.signed_delta_tokens) > MAX_CONTEXT_TOKEN_COUNT:
        raise ValueError("anchor signed delta exceeds supported range")
    return diagnostic


def _anchor_diagnostic_payload(
    diagnostic: ContextAnchorDiagnostic | None,
) -> Mapping[str, JsonValue] | None:
    """把typed anchor diagnostic序列化为canonical nested object。

    :param diagnostic: Host-private anchor诊断；fallback时为``None``。
    :returns: canonical JSON object或``None``。
    :raises TypeError: diagnostic类型非法时抛出。
    """

    if diagnostic is None:
        return None
    if not isinstance(diagnostic, ContextAnchorDiagnostic):
        raise TypeError("anchor diagnostic must be ContextAnchorDiagnostic")
    return {
        "manifest_event_id": diagnostic.manifest_event_id,
        "manifest_payload_ref": diagnostic.manifest_payload_ref,
        "manifest_digest": diagnostic.manifest_digest,
        "iteration_link_event_id": diagnostic.iteration_link_event_id,
        "usage_event_id": diagnostic.usage_event_id,
        "usage_observation_digest": diagnostic.usage_observation_digest,
        "iteration_completed_event_id": (
            diagnostic.iteration_completed_event_id
        ),
        "usage_anchor_tokens": diagnostic.usage_anchor_tokens,
        "conservative_anchor_tokens": (
            diagnostic.conservative_anchor_tokens
        ),
        "conservative_current_tokens": (
            diagnostic.conservative_current_tokens
        ),
        "signed_delta_tokens": diagnostic.signed_delta_tokens,
        "predicted_input_tokens": diagnostic.predicted_input_tokens,
    }

CONTEXT_COMPACTION_REQUESTED = "CONTEXT_COMPACTION_REQUESTED"
"""Context compaction requested canonical event type。"""

CONTEXT_COMPACTED = "CONTEXT_COMPACTED"
"""Context compact accepted canonical event type。"""

CONTEXT_COMPACTION_FAILED = "CONTEXT_COMPACTION_FAILED"
"""Context compaction failed canonical event type。"""

CONTEXT_COMPACTION_ATTEMPT_REJECTED = "CONTEXT_COMPACTION_ATTEMPT_REJECTED"
"""Context compaction semantic attempt rejected canonical event type。"""

_FIELD_TRIGGER_SOURCE = "trigger_source"
_FIELD_BUDGET_REASON = "budget_reason"
_FIELD_BUDGET_SNAPSHOT_REF = "budget_snapshot_ref"
_FIELD_INPUT_SNAPSHOT_CURSOR = "input_snapshot_cursor"
_FIELD_ESTIMATOR_DIGEST = "estimator_digest"
_FIELD_POLICY_REF = "policy_ref"
_FIELD_PROVIDER_REQUEST_ID = "provider_request_id"
_FIELD_PROVIDER_ERROR_REF = "provider_error_ref"
_FIELD_ATTEMPT_ID = "attempt_id"
_FIELD_EXECUTION_ID = "execution_id"
_FIELD_FROZEN_MATERIAL_LIST_DIGEST = "frozen_material_list_digest"
_FIELD_FROZEN_MATERIAL_REFS = "frozen_material_refs"
_FIELD_COMPACT_ARTIFACT_REF = "compact_artifact_ref"
_FIELD_COMPACT_ARTIFACT_DIGEST = "compact_artifact_digest"
_FIELD_ACCEPTED_ATTEMPT_NUMBER = "accepted_attempt_number"
_FIELD_ACCEPTED_CANDIDATE_DIGEST = "accepted_candidate_digest"
_FIELD_ACCEPTED_CANDIDATE = "accepted_candidate"
_FIELD_PROMPT_LOCAL_LABEL_MAPPING_REFS = "prompt_local_label_mapping_refs"
_FIELD_SOURCE_BOUNDARY_REFS = "source_boundary_refs"
_FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS = "accepted_evidence_mapping_refs"
_FIELD_PROJECTION_SIGNAL = "projection_signal"
_FIELD_ACCEPTED_PROPOSAL_MANIFEST_REF = "accepted_proposal_manifest_ref"
_FIELD_ACCEPTED_PROPOSAL_MANIFEST_DIGEST = "accepted_proposal_manifest_digest"
_FIELD_EPISODE_SUMMARY_CANDIDATE = "episode_summary_candidate"
_FIELD_PINNED_STATE_PATCH_CANDIDATE = "pinned_state_patch_candidate"
_FIELD_PRESERVATION_EVIDENCE = "preservation_evidence"
_FIELD_EVIDENCE_BACKED_FACT_CANDIDATES = "evidence_backed_fact_candidates"
_FIELD_MINIMUM_PRESERVE_ITEM_CANDIDATES = "minimum_preserve_item_candidates"
_FIELD_PRESERVED_FACT_REFS = "preserved_fact_refs"
_FIELD_DROPPED_RANGES = "dropped_ranges"
_FIELD_SUMMARIZED_RANGES = "summarized_ranges"
_FIELD_EVIDENCE_ANCHORS_RETAINED = "evidence_anchors_retained"
_FIELD_QUALITY_CHECK_RESULT = "quality_check_result"
_FIELD_BUDGET_AFTER_COMPACT = "budget_after_compact"
_FIELD_FAILURE_REASON = "failure_reason"
_FIELD_OPERATION_ID = "operation_id"
_FIELD_MAX_COMPACTION_ATTEMPTS_PER_OPERATION = (
    "max_compaction_attempts_per_operation"
)
_FIELD_CLIENT_CORRELATION_ID = "client_correlation_id"
_FIELD_ATTEMPT_NUMBER = "attempt_number"
_FIELD_FAILURE_CATEGORY = "failure_category"
_FIELD_REPAIRABLE = "repairable"
_FIELD_RUNNER_ATTEMPT_SUMMARY_REFS = "runner_attempt_summary_refs"
_FIELD_NEXT_POLICY_DECISION = "next_policy_decision"
_FIELD_POLICY_DECISION = "policy_decision"
_FIELD_RETRYABLE = "retryable"
_FIELD_ATTEMPT_COUNT = "attempt_count"
_FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED = "retry_repair_budget_exhausted"
_FIELD_DIAGNOSTIC_REFS = "diagnostic_refs"
_FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT = "budget_after_attempted_compact"
_FIELD_PROPOSAL_MANIFEST_REF = "proposal_manifest_ref"
_FIELD_PROPOSAL_MANIFEST_DIGEST = "proposal_manifest_digest"
_FIELD_DIAGNOSTIC_ARTIFACT_REF = "diagnostic_artifact_ref"
_FIELD_DIAGNOSTIC_ARTIFACT_DIGEST = "diagnostic_artifact_digest"
_FIELD_FAILURE_STAGE = "failure_stage"
_FIELD_DIAGNOSTIC_SUFFIX = "diagnostic_suffix"
_FIELD_PARSER_OR_VALIDATOR = "parser_or_validator"
_FIELD_EXCEPTION_CLASS = "exception_class"
_FIELD_EXCEPTION_MESSAGE = "exception_message"
_FIELD_OFFENDING_BLOCK_SECTION = "offending_block_section"
_FIELD_OFFENDING_BLOCK_KIND = "offending_block_kind"
_FIELD_OFFENDING_BLOCK_LABEL = "offending_block_label"
_FIELD_OFFENDING_BLOCK_ORDINAL = "offending_block_ordinal"
_FIELD_OFFENDING_BLOCK_TEXT_DIGEST = "offending_block_text_digest"
_FIELD_OFFENDING_BLOCK_TEXT_LENGTH = "offending_block_text_length"
_FIELD_MATERIAL_PACK_DIGEST = "material_pack_digest"
_FIELD_FALLBACK_POLICY_DECISION = "fallback_policy_decision"
_FIELD_FALLBACK_INPUT_WINDOW = "fallback_input_window"
_FIELD_FALLBACK_INPUT_DIGEST = "fallback_input_digest"
_FIELD_FALLBACK_BUDGET_RESULT = "fallback_budget_result"
_FIELD_FALLBACK_ACTION = "fallback_action"
_FIELD_ACCEPTED = "accepted"
_FIELD_REJECTION_REASONS = "rejection_reasons"

_REQUESTED_REQUIRED_FIELDS = (
    _FIELD_OPERATION_ID,
    _FIELD_MAX_COMPACTION_ATTEMPTS_PER_OPERATION,
    _FIELD_TRIGGER_SOURCE,
    _FIELD_BUDGET_REASON,
    _FIELD_BUDGET_SNAPSHOT_REF,
    _FIELD_INPUT_SNAPSHOT_CURSOR,
    _FIELD_ESTIMATOR_DIGEST,
    _FIELD_POLICY_REF,
    _FIELD_PROVIDER_REQUEST_ID,
    _FIELD_PROVIDER_ERROR_REF,
    _FIELD_ATTEMPT_ID,
    _FIELD_EXECUTION_ID,
    _FIELD_CLIENT_CORRELATION_ID,
    _FIELD_FROZEN_MATERIAL_LIST_DIGEST,
    _FIELD_FROZEN_MATERIAL_REFS,
)
_COMPACTED_REQUIRED_FIELDS = (
    _FIELD_OPERATION_ID,
    _FIELD_ACCEPTED_ATTEMPT_NUMBER,
    _FIELD_ACCEPTED_CANDIDATE_DIGEST,
    _FIELD_COMPACT_ARTIFACT_REF,
    _FIELD_COMPACT_ARTIFACT_DIGEST,
    _FIELD_ACCEPTED_CANDIDATE,
    _FIELD_PROMPT_LOCAL_LABEL_MAPPING_REFS,
    _FIELD_SOURCE_BOUNDARY_REFS,
    _FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS,
    _FIELD_QUALITY_CHECK_RESULT,
    _FIELD_BUDGET_AFTER_COMPACT,
    _FIELD_PROJECTION_SIGNAL,
)
_COMPACTED_OLD_FIELDS = frozenset(
    (
        _FIELD_EPISODE_SUMMARY_CANDIDATE,
        _FIELD_PINNED_STATE_PATCH_CANDIDATE,
        _FIELD_PRESERVATION_EVIDENCE,
        _FIELD_EVIDENCE_BACKED_FACT_CANDIDATES,
        _FIELD_MINIMUM_PRESERVE_ITEM_CANDIDATES,
        _FIELD_PRESERVED_FACT_REFS,
        _FIELD_DROPPED_RANGES,
        _FIELD_SUMMARIZED_RANGES,
        _FIELD_EVIDENCE_ANCHORS_RETAINED,
    )
)
_FAILED_REQUIRED_FIELDS = (
    _FIELD_OPERATION_ID,
    _FIELD_FAILURE_REASON,
    _FIELD_POLICY_DECISION,
    _FIELD_RETRYABLE,
    _FIELD_ATTEMPT_COUNT,
    _FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED,
    _FIELD_DIAGNOSTIC_REFS,
    _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT,
    _FIELD_FALLBACK_POLICY_DECISION,
    _FIELD_FALLBACK_INPUT_WINDOW,
    _FIELD_FALLBACK_INPUT_DIGEST,
    _FIELD_FALLBACK_BUDGET_RESULT,
    _FIELD_FALLBACK_ACTION,
)
_ATTEMPT_REJECTED_REQUIRED_FIELDS = (
    _FIELD_OPERATION_ID,
    _FIELD_ATTEMPT_NUMBER,
    _FIELD_FAILURE_CATEGORY,
    _FIELD_REPAIRABLE,
    _FIELD_RUNNER_ATTEMPT_SUMMARY_REFS,
    _FIELD_DIAGNOSTIC_REFS,
    _FIELD_NEXT_POLICY_DECISION,
    _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT,
)
_FALLBACK_ACTION_DISPATCH = "dispatch"
_FALLBACK_ACTION_FAIL_CLOSED = "fail_closed"
_FALLBACK_ACTION_NOT_APPLICABLE = "not_applicable"
_FALLBACK_ACTIONS = frozenset(
    (
        _FALLBACK_ACTION_DISPATCH,
        _FALLBACK_ACTION_FAIL_CLOSED,
        _FALLBACK_ACTION_NOT_APPLICABLE,
    )
)


def build_context_compaction_requested_payload(
    *,
    operation_id: str,
    max_compaction_attempts_per_operation: int,
    trigger_source: ContextCompactionTriggerSource,
    budget_reason: str,
    budget_snapshot_ref: str,
    input_snapshot_cursor: int,
    estimator_digest: str,
    policy_ref: str,
    provider_request_id: str | None,
    provider_error_ref: str | None,
    attempt_id: str | None,
    execution_id: str | None,
    client_correlation_id: str | None,
    frozen_material_list_digest: str,
    frozen_material_refs: tuple[str, ...],
) -> Mapping[str, JsonValue]:
    """构造 ``CONTEXT_COMPACTION_REQUESTED`` payload。

    :param operation_id: durable compact operation id；producer 必须与 request
        event id 使用同一预生成值。
    :param max_compaction_attempts_per_operation: 本 operation 冻结的全局预算。
    :param trigger_source: compact 触发来源。
    :param budget_reason: 预算触发或 provider fallback 原因。
    :param budget_snapshot_ref: budget snapshot / estimate ref。
    :param input_snapshot_cursor: 输入 snapshot cursor。
    :param estimator_digest: budget estimator digest。
    :param policy_ref: Host context policy ref。
    :param provider_request_id: provider request id；没有时为 ``None``。
    :param provider_error_ref: provider error ref；没有时为 ``None``。
    :param attempt_id: reactive compact 对应 Attempt id。
    :param execution_id: reactive compact 对应 execution id。
    :param client_correlation_id: reactive 客户端关联 id；proactive 为 ``None``。
    :param frozen_material_list_digest: 冻结 material list digest。
    :param frozen_material_refs: 冻结 material source refs。
    :returns: 可写入 EventLog 的 JSON payload。
    :raises TypeError: 字段类型非法时抛出。
    :raises ValueError: 字段值非法时抛出。
    """

    if not isinstance(trigger_source, ContextCompactionTriggerSource):
        raise TypeError("trigger_source must be ContextCompactionTriggerSource")
    payload: Mapping[str, JsonValue] = {
        _FIELD_OPERATION_ID: operation_id,
        _FIELD_MAX_COMPACTION_ATTEMPTS_PER_OPERATION: (
            max_compaction_attempts_per_operation
        ),
        _FIELD_TRIGGER_SOURCE: trigger_source.value,
        _FIELD_BUDGET_REASON: budget_reason,
        _FIELD_BUDGET_SNAPSHOT_REF: budget_snapshot_ref,
        _FIELD_INPUT_SNAPSHOT_CURSOR: input_snapshot_cursor,
        _FIELD_ESTIMATOR_DIGEST: estimator_digest,
        _FIELD_POLICY_REF: policy_ref,
        _FIELD_PROVIDER_REQUEST_ID: provider_request_id,
        _FIELD_PROVIDER_ERROR_REF: provider_error_ref,
        _FIELD_ATTEMPT_ID: attempt_id,
        _FIELD_EXECUTION_ID: execution_id,
        _FIELD_CLIENT_CORRELATION_ID: client_correlation_id,
        _FIELD_FROZEN_MATERIAL_LIST_DIGEST: frozen_material_list_digest,
        _FIELD_FROZEN_MATERIAL_REFS: _string_list_json(frozen_material_refs),
    }
    validate_context_compaction_requested_payload(payload)
    return payload


def validate_context_compaction_requested_payload(
    payload: Mapping[str, JsonValue],
) -> None:
    """校验 ``CONTEXT_COMPACTION_REQUESTED`` payload。

    :param payload: 待校验 JSON payload。
    :returns: ``None``。
    :raises ValueError: payload 缺少必填字段或字段非法时抛出。
    """

    _require_exact_fields(payload, _REQUESTED_REQUIRED_FIELDS)
    _required_text(payload, _FIELD_OPERATION_ID)
    _required_positive_int(
        payload,
        _FIELD_MAX_COMPACTION_ATTEMPTS_PER_OPERATION,
    )
    trigger_source = ContextCompactionTriggerSource(
        _required_text(payload, _FIELD_TRIGGER_SOURCE)
    )
    _required_text(payload, _FIELD_BUDGET_REASON)
    _required_text(payload, _FIELD_BUDGET_SNAPSHOT_REF)
    _required_non_negative_int(payload, _FIELD_INPUT_SNAPSHOT_CURSOR)
    _required_digest(payload, _FIELD_ESTIMATOR_DIGEST)
    _required_text(payload, _FIELD_POLICY_REF)
    _optional_text(payload, _FIELD_PROVIDER_REQUEST_ID)
    _optional_text(payload, _FIELD_PROVIDER_ERROR_REF)
    _optional_text(payload, _FIELD_CLIENT_CORRELATION_ID)
    _required_digest(payload, _FIELD_FROZEN_MATERIAL_LIST_DIGEST)
    _required_text_list(payload, _FIELD_FROZEN_MATERIAL_REFS)
    attempt_id = _optional_text(payload, _FIELD_ATTEMPT_ID)
    execution_id = _optional_text(payload, _FIELD_EXECUTION_ID)
    if trigger_source is ContextCompactionTriggerSource.REACTIVE:
        if attempt_id is None or execution_id is None:
            raise ValueError("reactive compaction requires attempt_id and execution_id")
    elif attempt_id is not None or execution_id is not None:
        raise ValueError("proactive compaction forbids attempt_id and execution_id")


def build_context_compacted_payload(
    *,
    operation_id: str,
    accepted_attempt_number: int,
    compact_artifact_ref: str,
    compact_artifact_digest: str,
    accepted_candidate: ConversationCompactOutputVNext,
    quality_check_result: CompactQualityCheckResultVNext,
    budget_after_compact: int,
    prompt_local_label_mapping_refs: tuple[str, ...],
    source_boundary_refs: tuple[str, ...],
    accepted_evidence_mapping_refs: tuple[str, ...],
    projection_signal: str,
    accepted_proposal_manifest_ref: str | None = None,
    accepted_proposal_manifest_digest: str | None = None,
) -> Mapping[str, JsonValue]:
    """构造 ``CONTEXT_COMPACTED`` payload。

    :param operation_id: compact operation id。
    :param accepted_attempt_number: 被接受的 operation attempt number。
    :param compact_artifact_ref: compact artifact payload / artifact ref。
    :param compact_artifact_digest: compact artifact digest。
    :param accepted_candidate: 通过 quality check 的 vNext compact output。
    :param quality_check_result: accepted vNext quality check 结果。
    :param budget_after_compact: Host 估算的 compact 后预算。
    :param prompt_local_label_mapping_refs: prompt-local label mapping refs。
    :param source_boundary_refs: source boundary refs。
    :param accepted_evidence_mapping_refs: accepted evidence mapping refs。
    :param projection_signal: memory projection signal。
    :param accepted_proposal_manifest_ref: accepted proposal manifest ref。
    :param accepted_proposal_manifest_digest: accepted proposal manifest digest。
    :returns: 可写入 EventLog 的 JSON payload。
    :raises TypeError: 输入类型非法时抛出。
    :raises ValueError: payload 结构非法时抛出。
    """

    if not isinstance(accepted_candidate, ConversationCompactOutputVNext):
        raise TypeError("accepted_candidate must be ConversationCompactOutputVNext")
    if not isinstance(quality_check_result, CompactQualityCheckResultVNext):
        raise TypeError("quality_check_result must be CompactQualityCheckResultVNext")
    payload: Mapping[str, JsonValue] = {
        _FIELD_OPERATION_ID: operation_id,
        _FIELD_ACCEPTED_ATTEMPT_NUMBER: accepted_attempt_number,
        _FIELD_ACCEPTED_CANDIDATE_DIGEST: accepted_candidate.digest(),
        _FIELD_COMPACT_ARTIFACT_REF: compact_artifact_ref,
        _FIELD_COMPACT_ARTIFACT_DIGEST: compact_artifact_digest,
        _FIELD_ACCEPTED_CANDIDATE: accepted_candidate.to_json(),
        _FIELD_PROMPT_LOCAL_LABEL_MAPPING_REFS: _string_list_json(
            prompt_local_label_mapping_refs
        ),
        _FIELD_SOURCE_BOUNDARY_REFS: _string_list_json(source_boundary_refs),
        _FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS: _string_list_json(
            accepted_evidence_mapping_refs
        ),
        _FIELD_QUALITY_CHECK_RESULT: quality_check_result.to_json(),
        _FIELD_BUDGET_AFTER_COMPACT: budget_after_compact,
        _FIELD_PROJECTION_SIGNAL: projection_signal,
        _FIELD_ACCEPTED_PROPOSAL_MANIFEST_REF: accepted_proposal_manifest_ref,
        _FIELD_ACCEPTED_PROPOSAL_MANIFEST_DIGEST: accepted_proposal_manifest_digest,
    }
    validate_context_compacted_payload(payload)
    return payload


def validate_context_compacted_payload(payload: Mapping[str, JsonValue]) -> None:
    """校验 ``CONTEXT_COMPACTED`` payload。

    :param payload: 待校验 JSON payload。
    :returns: ``None``。
    :raises ValueError: payload 缺少必填字段、artifact ref/digest 不成对或
        summary / patch 缺少 preservation evidence 时抛出。
    """

    _reject_old_compacted_fields(payload)
    _require_fields(payload, _COMPACTED_REQUIRED_FIELDS)
    _required_text(payload, _FIELD_OPERATION_ID)
    _required_positive_int(payload, _FIELD_ACCEPTED_ATTEMPT_NUMBER)
    _required_digest(payload, _FIELD_ACCEPTED_CANDIDATE_DIGEST)
    _required_text(payload, _FIELD_COMPACT_ARTIFACT_REF)
    _required_digest(payload, _FIELD_COMPACT_ARTIFACT_DIGEST)
    parse_context_compacted_semantic_payload(payload)
    _required_text_list(payload, _FIELD_PROMPT_LOCAL_LABEL_MAPPING_REFS)
    _required_text_list(payload, _FIELD_SOURCE_BOUNDARY_REFS)
    _required_text_list(payload, _FIELD_ACCEPTED_EVIDENCE_MAPPING_REFS)
    _validate_quality_check_result_vnext(payload)
    _required_non_negative_int(payload, _FIELD_BUDGET_AFTER_COMPACT)
    _required_text(payload, _FIELD_PROJECTION_SIGNAL)
    _validate_optional_ref_digest_pair(
        payload,
        ref_field=_FIELD_ACCEPTED_PROPOSAL_MANIFEST_REF,
        digest_field=_FIELD_ACCEPTED_PROPOSAL_MANIFEST_DIGEST,
    )


def build_context_compaction_failed_payload(
    *,
    operation_id: str,
    failure_reason: str,
    policy_decision: ContextBudgetDecision | str,
    retryable: bool,
    attempt_count: int,
    retry_repair_budget_exhausted: bool,
    diagnostic_refs: tuple[str, ...],
    budget_after_attempted_compact: int | None,
    fallback_policy_decision: str | None = None,
    fallback_input_window: Mapping[str, JsonValue] | None = None,
    fallback_input_digest: str | None = None,
    fallback_budget_result: Mapping[str, JsonValue] | None = None,
    fallback_action: str = _FALLBACK_ACTION_NOT_APPLICABLE,
) -> Mapping[str, JsonValue]:
    """构造 ``CONTEXT_COMPACTION_FAILED`` payload。

    :param operation_id: compact operation 诊断 id；通常为 request fact event id。
    :param failure_reason: compact 失败原因。
    :param policy_decision: compact 失败后的 policy decision。
    :param retryable: 当前失败是否可重试。
    :param attempt_count: operation 内已拒绝 proposal attempt 数。
    :param retry_repair_budget_exhausted: semantic retry / repair 预算是否耗尽。
    :param diagnostic_refs: 诊断 ref 列表。
    :param budget_after_attempted_compact: compact 尝试后的预算估算；未知时为
        ``None``。
    :param fallback_policy_decision: fallback policy decision；不适用时为
        ``None``。
    :param fallback_input_window: fallback 输入窗口结构化诊断；不适用时为
        ``None``。
    :param fallback_input_digest: fallback 输入窗口 digest；不适用时为
        ``None``。
    :param fallback_budget_result: fallback 预算重估结果；不适用时为
        ``None``。
    :param fallback_action: fallback 动作。
    :returns: 可写入 EventLog 的 JSON payload。
    :raises TypeError: 字段类型非法时抛出。
    :raises ValueError: 字段值非法时抛出。
    """

    if isinstance(policy_decision, ContextBudgetDecision):
        policy_decision_value = policy_decision.value
    else:
        policy_decision_value = policy_decision
    payload: Mapping[str, JsonValue] = {
        _FIELD_OPERATION_ID: operation_id,
        _FIELD_FAILURE_REASON: failure_reason,
        _FIELD_POLICY_DECISION: policy_decision_value,
        _FIELD_RETRYABLE: retryable,
        _FIELD_ATTEMPT_COUNT: attempt_count,
        _FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED: retry_repair_budget_exhausted,
        _FIELD_DIAGNOSTIC_REFS: _string_list_json(diagnostic_refs),
        _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT: budget_after_attempted_compact,
        _FIELD_FALLBACK_POLICY_DECISION: fallback_policy_decision,
        _FIELD_FALLBACK_INPUT_WINDOW: fallback_input_window,
        _FIELD_FALLBACK_INPUT_DIGEST: fallback_input_digest,
        _FIELD_FALLBACK_BUDGET_RESULT: fallback_budget_result,
        _FIELD_FALLBACK_ACTION: fallback_action,
    }
    validate_context_compaction_failed_payload(payload)
    return payload


def validate_context_compaction_failed_payload(payload: Mapping[str, JsonValue]) -> None:
    """校验 ``CONTEXT_COMPACTION_FAILED`` payload。

    :param payload: 待校验 JSON payload。
    :returns: ``None``。
    :raises ValueError: payload 缺少必填字段或字段非法时抛出。
    """

    _require_fields(payload, _FAILED_REQUIRED_FIELDS)
    _required_text(payload, _FIELD_OPERATION_ID)
    _required_text(payload, _FIELD_FAILURE_REASON)
    _required_text(payload, _FIELD_POLICY_DECISION)
    _required_bool(payload, _FIELD_RETRYABLE)
    _required_non_negative_int(payload, _FIELD_ATTEMPT_COUNT)
    _required_bool(payload, _FIELD_RETRY_REPAIR_BUDGET_EXHAUSTED)
    _required_text_list(payload, _FIELD_DIAGNOSTIC_REFS)
    _optional_non_negative_int(payload, _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT)
    fallback_action = _required_text(payload, _FIELD_FALLBACK_ACTION)
    if fallback_action not in _FALLBACK_ACTIONS:
        raise ValueError("fallback_action must be dispatch, fail_closed or not_applicable")
    _validate_failed_fallback_fields(payload, fallback_action=fallback_action)


def _validate_failed_fallback_fields(
    payload: Mapping[str, JsonValue], *, fallback_action: str
) -> None:
    """校验 failed payload 的 fallback 诊断字段一致性。

    :param payload: 待校验 JSON payload。
    :param fallback_action: 已校验为非空文本的 fallback action。
    :returns: ``None``。
    :raises ValueError: fallback 字段组合非法时抛出。
    """

    if fallback_action == _FALLBACK_ACTION_NOT_APPLICABLE:
        for field_name in (
            _FIELD_FALLBACK_POLICY_DECISION,
            _FIELD_FALLBACK_INPUT_WINDOW,
            _FIELD_FALLBACK_INPUT_DIGEST,
            _FIELD_FALLBACK_BUDGET_RESULT,
        ):
            if payload[field_name] is not None:
                raise ValueError(f"{field_name} must be null when fallback is not applicable")
        return
    _required_text(payload, _FIELD_FALLBACK_POLICY_DECISION)
    _required_mapping(payload, _FIELD_FALLBACK_INPUT_WINDOW)
    _required_text(payload, _FIELD_FALLBACK_INPUT_DIGEST)
    _required_mapping(payload, _FIELD_FALLBACK_BUDGET_RESULT)


def _validate_optional_ref_digest_pair(
    payload: Mapping[str, JsonValue],
    *,
    ref_field: str,
    digest_field: str,
) -> None:
    """校验可选 ref/digest 字段必须成对出现。

    :param payload: 待校验 payload。
    :param ref_field: ref 字段名。
    :param digest_field: digest 字段名。
    :returns: ``None``。
    :raises ValueError: 只出现一侧或 digest 非法时抛出。
    """

    ref = _optional_text(payload, ref_field)
    digest = _optional_text(payload, digest_field)
    if (ref is None) != (digest is None):
        raise ValueError(f"{ref_field} and {digest_field} must both be set or null")
    if digest is not None and not is_sha256_digest(digest):
        raise ValueError(f"{digest_field} must be sha256 digest")


def _reject_old_compacted_fields(payload: Mapping[str, JsonValue]) -> None:
    """拒绝旧 ``CONTEXT_COMPACTED`` 字段。

    :param payload: compacted payload。
    :returns: ``None``。
    :raises ValueError: payload 包含旧字段时抛出。
    """

    for field_name in _COMPACTED_OLD_FIELDS:
        if field_name in payload:
            raise ValueError(f"{field_name} is not supported in vNext compacted payload")


def _validate_quality_check_result_vnext(payload: Mapping[str, JsonValue]) -> None:
    """校验 vNext quality check result。

    :param payload: compacted payload。
    :returns: ``None``。
    :raises ValueError: quality result 不是 accepted vNext result 时抛出。
    """

    result = _required_mapping(payload, _FIELD_QUALITY_CHECK_RESULT)
    if not _required_bool(result, _FIELD_ACCEPTED):
        raise ValueError("compacted payload requires accepted quality result")
    reasons = _required_text_list(result, _FIELD_REJECTION_REASONS)
    if len(reasons) > 0:
        raise ValueError("accepted quality result must not include rejection reasons")


def build_context_compaction_attempt_rejected_payload(
    *,
    operation_id: str,
    attempt_number: int,
    failure_category: str,
    repairable: bool,
    runner_attempt_summary_refs: tuple[str, ...],
    diagnostic_refs: tuple[str, ...],
    next_policy_decision: str,
    budget_after_attempted_compact: int | None,
    proposal_manifest_ref: str | None = None,
    proposal_manifest_digest: str | None = None,
    diagnostic_artifact_ref: str | None = None,
    diagnostic_artifact_digest: str | None = None,
    failure_stage: str | None = None,
    diagnostic_suffix: str | None = None,
    parser_or_validator: str | None = None,
    exception_class: str | None = None,
    exception_message: str | None = None,
    offending_block_section: str | None = None,
    offending_block_kind: str | None = None,
    offending_block_label: str | None = None,
    offending_block_ordinal: int | None = None,
    offending_block_text_digest: str | None = None,
    offending_block_text_length: int | None = None,
    material_pack_digest: str | None = None,
) -> Mapping[str, JsonValue]:
    """构造 ``CONTEXT_COMPACTION_ATTEMPT_REJECTED`` payload。

    :param operation_id: compaction operation id。
    :param attempt_number: operation 内 proposal attempt 序号，从 1 开始。
    :param failure_category: 失败类别。
    :param repairable: 当前失败是否可进入下一次 semantic repair attempt。
    :param runner_attempt_summary_refs: runner attempt 摘要 ref 列表。
    :param diagnostic_refs: quality / parse / budget 诊断 ref 列表。
    :param next_policy_decision: 下一步 Host policy decision。
    :param budget_after_attempted_compact: 本次 attempt 后预算；未知时为
        ``None``。
    :param proposal_manifest_ref: 对应该 attempt 的 proposal manifest ref；
        未发起 proposal call 时为 ``None``。
    :param proposal_manifest_digest: 对应该 attempt 的 proposal manifest digest；
        未发起 proposal call 时为 ``None``。
    :param diagnostic_artifact_ref: material/proposal diagnostic artifact ref。
    :param diagnostic_artifact_digest: diagnostic artifact digest。
    :param failure_stage: 失败阶段分类。
    :param diagnostic_suffix: 与 ``diagnostic_refs`` 对齐的诊断后缀。
    :param parser_or_validator: 失败来源 parser / validator 名称。
    :param exception_class: 脱敏异常类型。
    :param exception_message: 脱敏异常消息。
    :param offending_block_section: offending material block section。
    :param offending_block_kind: offending material block kind。
    :param offending_block_label: offending material block label。
    :param offending_block_ordinal: offending block 在 previous view 中的序号。
    :param offending_block_text_digest: offending block text digest。
    :param offending_block_text_length: offending block text 字符长度。
    :param material_pack_digest: compact material pack digest。
    :returns: 可写入 EventLog 的 JSON payload。
    :raises ValueError: payload 字段非法时抛出。
    """

    payload: Mapping[str, JsonValue] = {
        _FIELD_OPERATION_ID: operation_id,
        _FIELD_ATTEMPT_NUMBER: attempt_number,
        _FIELD_FAILURE_CATEGORY: failure_category,
        _FIELD_REPAIRABLE: repairable,
        _FIELD_RUNNER_ATTEMPT_SUMMARY_REFS: _string_list_json(
            runner_attempt_summary_refs
        ),
        _FIELD_DIAGNOSTIC_REFS: _string_list_json(diagnostic_refs),
        _FIELD_NEXT_POLICY_DECISION: next_policy_decision,
        _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT: budget_after_attempted_compact,
        _FIELD_PROPOSAL_MANIFEST_REF: proposal_manifest_ref,
        _FIELD_PROPOSAL_MANIFEST_DIGEST: proposal_manifest_digest,
        _FIELD_DIAGNOSTIC_ARTIFACT_REF: diagnostic_artifact_ref,
        _FIELD_DIAGNOSTIC_ARTIFACT_DIGEST: diagnostic_artifact_digest,
        _FIELD_FAILURE_STAGE: failure_stage,
        _FIELD_DIAGNOSTIC_SUFFIX: diagnostic_suffix,
        _FIELD_PARSER_OR_VALIDATOR: parser_or_validator,
        _FIELD_EXCEPTION_CLASS: exception_class,
        _FIELD_EXCEPTION_MESSAGE: exception_message,
        _FIELD_OFFENDING_BLOCK_SECTION: offending_block_section,
        _FIELD_OFFENDING_BLOCK_KIND: offending_block_kind,
        _FIELD_OFFENDING_BLOCK_LABEL: offending_block_label,
        _FIELD_OFFENDING_BLOCK_ORDINAL: offending_block_ordinal,
        _FIELD_OFFENDING_BLOCK_TEXT_DIGEST: offending_block_text_digest,
        _FIELD_OFFENDING_BLOCK_TEXT_LENGTH: offending_block_text_length,
        _FIELD_MATERIAL_PACK_DIGEST: material_pack_digest,
    }
    validate_context_compaction_attempt_rejected_payload(payload)
    return payload


def validate_context_compaction_attempt_rejected_payload(
    payload: Mapping[str, JsonValue],
) -> None:
    """校验 ``CONTEXT_COMPACTION_ATTEMPT_REJECTED`` payload。

    :param payload: 待校验 JSON payload。
    :returns: ``None``。
    :raises ValueError: payload 缺少必填字段或字段非法时抛出。
    """

    _require_fields(payload, _ATTEMPT_REJECTED_REQUIRED_FIELDS)
    _required_text(payload, _FIELD_OPERATION_ID)
    _required_positive_int(payload, _FIELD_ATTEMPT_NUMBER)
    _required_text(payload, _FIELD_FAILURE_CATEGORY)
    _required_bool(payload, _FIELD_REPAIRABLE)
    runner_refs = _required_text_list(payload, _FIELD_RUNNER_ATTEMPT_SUMMARY_REFS)
    if len(runner_refs) == 0:
        raise ValueError("runner_attempt_summary_refs must be non-empty")
    diagnostic_refs = _required_text_list(payload, _FIELD_DIAGNOSTIC_REFS)
    if len(diagnostic_refs) == 0:
        raise ValueError("diagnostic_refs must be non-empty")
    _required_text(payload, _FIELD_NEXT_POLICY_DECISION)
    _optional_non_negative_int(payload, _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT)
    _validate_optional_ref_digest_pair(
        payload,
        ref_field=_FIELD_PROPOSAL_MANIFEST_REF,
        digest_field=_FIELD_PROPOSAL_MANIFEST_DIGEST,
    )
    _validate_optional_ref_digest_pair(
        payload,
        ref_field=_FIELD_DIAGNOSTIC_ARTIFACT_REF,
        digest_field=_FIELD_DIAGNOSTIC_ARTIFACT_DIGEST,
    )
    _optional_text(payload, _FIELD_FAILURE_STAGE)
    _optional_text(payload, _FIELD_DIAGNOSTIC_SUFFIX)
    _optional_text(payload, _FIELD_PARSER_OR_VALIDATOR)
    _optional_text(payload, _FIELD_EXCEPTION_CLASS)
    _optional_text(payload, _FIELD_EXCEPTION_MESSAGE)
    _optional_text(payload, _FIELD_OFFENDING_BLOCK_SECTION)
    _optional_text(payload, _FIELD_OFFENDING_BLOCK_KIND)
    _optional_text(payload, _FIELD_OFFENDING_BLOCK_LABEL)
    _optional_non_negative_int(payload, _FIELD_OFFENDING_BLOCK_ORDINAL)
    _validate_optional_digest(payload, _FIELD_OFFENDING_BLOCK_TEXT_DIGEST)
    _optional_non_negative_int(payload, _FIELD_OFFENDING_BLOCK_TEXT_LENGTH)
    _validate_optional_digest(payload, _FIELD_MATERIAL_PACK_DIGEST)


def _string_list_json(values: tuple[str, ...]) -> list[JsonValue]:
    """把字符串 tuple 转换为 JSON 数组。

    :param values: 字符串 tuple。
    :returns: JSON 数组。
    :raises TypeError: 输入不是 tuple 或元素不是文本时抛出。
    :raises ValueError: 元素为空时抛出。
    """

    if not isinstance(values, tuple):
        raise TypeError("values must be tuple")
    result: list[JsonValue] = []
    for value in values:
        _require_non_empty_text_value(value, "values item")
        result.append(value)
    return result


def _require_fields(payload: Mapping[str, JsonValue], fields: tuple[str, ...]) -> None:
    """校验 payload 含有全部顶层必填字段。

    :param payload: JSON payload。
    :param fields: 必填字段名。
    :returns: ``None``。
    :raises ValueError: 缺少字段时抛出。
    """

    for field_name in fields:
        if field_name not in payload:
            raise ValueError(f"{field_name} is required")


def _require_exact_fields(
    payload: Mapping[str, JsonValue],
    fields: tuple[str, ...],
) -> None:
    """校验 payload 顶层字段集合与 fresh schema 精确相等。

    :param payload: JSON payload。
    :param fields: 唯一允许的字段名。
    :returns: ``None``。
    :raises ValueError: 缺少必填字段或出现未知字段时抛出。
    """

    _require_fields(payload, fields)
    unexpected = frozenset(payload) - frozenset(fields)
    if unexpected:
        raise ValueError(
            "unexpected payload fields: " + ", ".join(sorted(unexpected))
        )


def _required_text(payload: Mapping[str, JsonValue], field_name: str) -> str:
    """读取必填非空文本字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 文本值。
    :raises ValueError: 字段缺失或不是非空文本时抛出。
    """

    value = payload.get(field_name)
    return _require_non_empty_text_value(value, field_name)


def _optional_text(payload: Mapping[str, JsonValue], field_name: str) -> str | None:
    """读取可选非空文本字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 文本值或 ``None``。
    :raises ValueError: 字段存在但不是非空文本时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    return _require_non_empty_text_value(value, field_name)


def _required_digest(payload: Mapping[str, JsonValue], field_name: str) -> str:
    """读取必填 sha256 digest 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: digest 文本。
    :raises ValueError: 字段缺失或 digest 非法时抛出。
    """

    value = _required_text(payload, field_name)
    if not is_sha256_digest(value):
        raise ValueError(f"{field_name} must be sha256 digest")
    return value


def _validate_optional_digest(
    payload: Mapping[str, JsonValue], field_name: str
) -> None:
    """校验可选 sha256 digest 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: ``None``。
    :raises ValueError: 字段存在但不是 SHA-256 digest 时抛出。
    """

    value = _optional_text(payload, field_name)
    if value is not None and not is_sha256_digest(value):
        raise ValueError(f"{field_name} must be sha256 digest")


def _required_non_negative_int(
    payload: Mapping[str, JsonValue], field_name: str
) -> int:
    """读取必填非负整数字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 非负整数。
    :raises ValueError: 字段缺失、类型非法或为负数时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _required_positive_int(
    payload: Mapping[str, JsonValue], field_name: str
) -> int:
    """读取必填正整数字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 正整数。
    :raises ValueError: 字段缺失、类型非法或非正时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value


def _required_int(
    payload: Mapping[str, JsonValue], field_name: str
) -> int:
    """读取必填严格整数字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 整数值。
    :raises ValueError: 字段缺失、为bool或不是int时抛出。
    """

    value = payload.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be int")
    return value


def _required_enum(
    payload: Mapping[str, JsonValue],
    field_name: str,
    enum_type: type[_EnumT],
) -> _EnumT:
    """读取必填closed string enum。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :param enum_type: 目标``StrEnum``类型。
    :returns: typed enum成员。
    :raises ValueError: 字段不是非空文本或unknown value时抛出。
    """

    value = _required_text(payload, field_name)
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} has unsupported value") from exc


def _optional_enum(
    payload: Mapping[str, JsonValue],
    field_name: str,
    enum_type: type[_EnumT],
) -> _EnumT | None:
    """读取nullable closed string enum。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :param enum_type: 目标``StrEnum``类型。
    :returns: typed enum成员或``None``。
    :raises ValueError: 非null字段不是closed enum成员时抛出。
    """

    value = _optional_text(payload, field_name)
    if value is None:
        return None
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} has unsupported value") from exc


def _optional_non_negative_int(
    payload: Mapping[str, JsonValue], field_name: str
) -> int | None:
    """读取可选非负整数字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 非负整数或 ``None``。
    :raises ValueError: 字段存在但类型非法或为负数时抛出。
    """

    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _required_bool(payload: Mapping[str, JsonValue], field_name: str) -> bool:
    """读取必填布尔字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 布尔值。
    :raises ValueError: 字段缺失或不是布尔值时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be bool")
    return value


def _required_mapping(
    payload: Mapping[str, JsonValue], field_name: str
) -> Mapping[str, JsonValue]:
    """读取必填 JSON object 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: JSON object。
    :raises ValueError: 字段缺失或不是 object 时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be mapping")
    return value


def _required_list(
    payload: Mapping[str, JsonValue], field_name: str
) -> list[JsonValue]:
    """读取必填 JSON array 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: JSON array。
    :raises ValueError: 字段缺失或不是 array 时抛出。
    """

    value = payload.get(field_name)
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be list")
    return value


def _required_mapping_list(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[Mapping[str, JsonValue], ...]:
    """读取必填 JSON object array 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: JSON object tuple。
    :raises ValueError: 字段缺失或元素不是 object 时抛出。
    """

    items = _required_list(payload, field_name)
    mappings: list[Mapping[str, JsonValue]] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError(f"{field_name} items must be mapping")
        mappings.append(item)
    return tuple(mappings)


def _required_text_list(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[str, ...]:
    """读取必填非空文本 array 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 文本 tuple。
    :raises ValueError: 字段缺失、不是 array 或元素非法时抛出。
    """

    items = _required_list(payload, field_name)
    values: list[str] = []
    for item in items:
        values.append(_require_non_empty_text_value(item, field_name))
    return tuple(values)


def _optional_text_list(
    payload: Mapping[str, JsonValue], field_name: str
) -> tuple[str, ...]:
    """读取可选非空文本 array 字段。

    :param payload: JSON payload。
    :param field_name: 字段名。
    :returns: 文本 tuple；字段缺失时返回空 tuple。
    :raises ValueError: 字段存在但不是文本 array 时抛出。
    """

    if field_name not in payload:
        return ()
    value = payload.get(field_name)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be list")
    values: list[str] = []
    for item in value:
        values.append(_require_non_empty_text_value(item, field_name))
    return tuple(values)


def _require_non_empty_text_value(value: JsonValue, field_name: str) -> str:
    """校验 JSON 值是非空文本。

    :param value: JSON 值。
    :param field_name: 字段名。
    :returns: 非空文本。
    :raises ValueError: 值不是非空文本时抛出。
    """

    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(f"{field_name} must be non-empty text")
    return value


__all__ = [
    "CONTEXT_BUDGET_EVALUATED",
    "CONTEXT_BUDGET_EVALUATED_SCHEMA_VERSION",
    "CONTEXT_COMPACTED",
    "CONTEXT_COMPACTION_ATTEMPT_REJECTED",
    "CONTEXT_COMPACTION_FAILED",
    "CONTEXT_COMPACTION_REQUESTED",
    "ContextBudgetEvaluatedPayload",
    "ContextBudgetEvaluationIdentity",
    "append_context_budget_evaluated_in_transaction",
    "build_context_budget_evaluated_payload",
    "build_context_compaction_attempt_rejected_payload",
    "build_context_compacted_payload",
    "build_context_compaction_failed_payload",
    "build_context_compaction_requested_payload",
    "context_budget_evaluated_decision_id",
    "context_budget_evaluated_event_id",
    "context_budget_evaluation_identity",
    "load_matching_context_budget_evaluation_in_transaction",
    "parse_context_budget_evaluated_payload",
    "validate_context_compaction_attempt_rejected_payload",
    "validate_context_compacted_payload",
    "validate_context_compaction_failed_payload",
    "validate_context_compaction_requested_payload",
]
