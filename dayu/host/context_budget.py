"""Host context budget conservative estimator。

本模块只实现 Phase 10 Slice 1 的 typed budget 估算与阈值决策。估算
依据来自 Host RunInputBuilder / Context Governance 可提供的 typed view，
不读取 Engine spec、provider overflow payload、metadata 或 extra payload。
Runner usage 只建模为 post-call observation，不参与当前阈值动态调整。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from math import ceil, floor

from dayu.contracts.json_value import JsonValue
from dayu.host._public_validation import (
    require_non_negative_int as _require_non_negative_int,
)
from dayu.host._public_validation import (
    require_non_empty as _require_non_empty,
)
from dayu.host._public_validation import (
    require_optional_non_empty as _require_optional_non_empty,
)
from dayu.host._public_validation import require_positive_int as _require_positive_int
from dayu.host.context_policy import (
    ContextBudgetPolicy,
    DEFAULT_SOFT_THRESHOLD_CONTEXT_RATIO,
    MIN_CONTEXT_HARD_THRESHOLD_TOKENS,
)
from dayu.host.durable.codec import canonical_json_dumps, sha256_digest_json

DEFAULT_INPUT_SOFT_THRESHOLD_RATIO = DEFAULT_SOFT_THRESHOLD_CONTEXT_RATIO
DEFAULT_ESTIMATOR_CHARS_PER_TOKEN = 3
DEFAULT_ESTIMATOR_JSON_BYTES_PER_TOKEN = 3
DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS = 12
DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS = 16
_MIN_SOFT_THRESHOLD_TOKENS = 1


class ContextBudgetDecision(StrEnum):
    """Context budget 阈值决策。"""

    ALLOW_DISPATCH = "allow_dispatch"
    COMPACT_SOFT_THRESHOLD = "compact_soft_threshold"
    BLOCK_HARD_THRESHOLD = "block_hard_threshold"


class ContextBudgetOverageReason(StrEnum):
    """Context budget 超限原因。"""

    SOFT_THRESHOLD = "soft_threshold"
    HARD_THRESHOLD = "hard_threshold"


@dataclass(frozen=True, slots=True)
class BudgetTextFragment:
    """参与预算估算的文本片段。

    :param fragment_ref: Host 内部可追溯片段引用。
    :param text: 片段文本内容。
    """

    fragment_ref: str
    text: str

    def __post_init__(self) -> None:
        """校验文本片段。

        :returns: ``None``。
        :raises ValueError: 引用为空时抛出。
        """

        _require_non_empty(self.fragment_ref, field_name="BudgetTextFragment.fragment_ref")


@dataclass(frozen=True, slots=True)
class BudgetJsonFragment:
    """参与预算估算的 JSON 片段。

    :param fragment_ref: Host 内部可追溯片段引用。
    :param value: JSON 值。
    """

    fragment_ref: str
    value: JsonValue

    def __post_init__(self) -> None:
        """校验 JSON 片段。

        :returns: ``None``。
        :raises ValueError: 引用为空时抛出。
        """

        _require_non_empty(self.fragment_ref, field_name="BudgetJsonFragment.fragment_ref")


@dataclass(frozen=True, slots=True)
class BudgetEstimateInput:
    """Context budget 估算输入。

    :param session_id: Session id。
    :param run_id: Run id。
    :param message_fragments: RunInputBuilder 已构造或即将构造的消息文本片段。
    :param json_fragments: memory / scene / artifact metadata 等 JSON 片段。
    :param tool_schema_fragments: 工具 schema JSON 片段。
    :param compact_artifact_refs: 已可用 compact artifact refs。
    :param memory_snapshot_cursor: memory snapshot cursor；无 snapshot 时为 ``None``。
    :param current_prompt_ref: 当前用户输入引用；无时为 ``None``。
    """

    session_id: str
    run_id: str
    message_fragments: tuple[BudgetTextFragment, ...]
    json_fragments: tuple[BudgetJsonFragment, ...] = ()
    tool_schema_fragments: tuple[BudgetJsonFragment, ...] = ()
    compact_artifact_refs: tuple[str, ...] = ()
    memory_snapshot_cursor: int | None = None
    current_prompt_ref: str | None = None

    def __post_init__(self) -> None:
        """校验估算输入。

        :returns: ``None``。
        :raises TypeError: tuple 字段或 cursor 类型非法时抛出。
        :raises ValueError: 文本字段为空或 cursor 为负数时抛出。
        """

        _require_non_empty(self.session_id, field_name="BudgetEstimateInput.session_id")
        _require_non_empty(self.run_id, field_name="BudgetEstimateInput.run_id")
        _require_tuple_items(
            self.message_fragments,
            BudgetTextFragment,
            field_name="BudgetEstimateInput.message_fragments",
        )
        _require_tuple_items(
            self.json_fragments,
            BudgetJsonFragment,
            field_name="BudgetEstimateInput.json_fragments",
        )
        _require_tuple_items(
            self.tool_schema_fragments,
            BudgetJsonFragment,
            field_name="BudgetEstimateInput.tool_schema_fragments",
        )
        for artifact_ref in self.compact_artifact_refs:
            _require_non_empty(
                artifact_ref,
                field_name="BudgetEstimateInput.compact_artifact_refs",
            )
        if self.memory_snapshot_cursor is not None:
            _require_non_negative_int(
                self.memory_snapshot_cursor,
                field_name="BudgetEstimateInput.memory_snapshot_cursor",
            )
        _require_optional_non_empty(
            self.current_prompt_ref,
            field_name="BudgetEstimateInput.current_prompt_ref",
        )


@dataclass(frozen=True, slots=True)
class BudgetEstimate:
    """Context budget 估算结果。

    :param estimated_input_tokens: 保守估算的输入 token 数。
    :param input_budget_tokens: Host policy 的 ``context_window_size``。
    :param soft_threshold_tokens: soft threshold token 数。
    :param hard_threshold_tokens: hard threshold token 数。
    :param safety_margin_tokens: soft threshold 上方预留的安全余量 token 数。
    :param estimator_digest: 估算输入、策略与常量的 digest。
    :param overage_reason: 超限原因；未超限时为 ``None``。
    """

    estimated_input_tokens: int
    input_budget_tokens: int
    soft_threshold_tokens: int
    hard_threshold_tokens: int
    safety_margin_tokens: int
    estimator_digest: str
    overage_reason: ContextBudgetOverageReason | None

    def __post_init__(self) -> None:
        """校验估算结果。

        :returns: ``None``。
        :raises TypeError: 整数字段类型非法时抛出。
        :raises ValueError: token 数或 digest 非法时抛出。
        """

        _require_non_negative_int(
            self.estimated_input_tokens,
            field_name="BudgetEstimate.estimated_input_tokens",
        )
        _require_positive_int(
            self.input_budget_tokens,
            field_name="BudgetEstimate.input_budget_tokens",
        )
        _require_positive_int(
            self.soft_threshold_tokens,
            field_name="BudgetEstimate.soft_threshold_tokens",
        )
        _require_positive_int(
            self.hard_threshold_tokens,
            field_name="BudgetEstimate.hard_threshold_tokens",
        )
        if self.hard_threshold_tokens < MIN_CONTEXT_HARD_THRESHOLD_TOKENS:
            raise ValueError(
                "BudgetEstimate.hard_threshold_tokens must be >= "
                f"{MIN_CONTEXT_HARD_THRESHOLD_TOKENS}"
            )
        _require_non_negative_int(
            self.safety_margin_tokens,
            field_name="BudgetEstimate.safety_margin_tokens",
        )
        _require_non_empty(self.estimator_digest, field_name="BudgetEstimate.estimator_digest")
        if self.overage_reason is not None and not isinstance(
            self.overage_reason, ContextBudgetOverageReason
        ):
            raise TypeError("BudgetEstimate.overage_reason must be ContextBudgetOverageReason")


@dataclass(frozen=True, slots=True)
class UsageObservation:
    """Runner usage 的 Host internal observation。

    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :param prompt_tokens: provider 报告的 prompt token 数。
    :param completion_tokens: provider 报告的 completion token 数。
    :param total_tokens: provider 报告的 total token 数。
    :param provider_request_id: provider request id；无时为 ``None``。
    :param estimator_digest: 对应估算 digest；无对应估算时为 ``None``。
    :param policy_ref: 对应 Host policy ref。
    :param observed_at: Host 观察时间，必须是 UTC aware datetime。
    """

    session_id: str
    run_id: str
    attempt_id: str
    execution_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    provider_request_id: str | None
    estimator_digest: str | None
    policy_ref: str
    observed_at: datetime

    def __post_init__(self) -> None:
        """校验 usage observation。

        :returns: ``None``。
        :raises TypeError: token 或时间字段类型非法时抛出。
        :raises ValueError: 文本为空、token 为负数或时间非 UTC 时抛出。
        """

        _require_non_empty(self.session_id, field_name="UsageObservation.session_id")
        _require_non_empty(self.run_id, field_name="UsageObservation.run_id")
        _require_non_empty(self.attempt_id, field_name="UsageObservation.attempt_id")
        _require_non_empty(self.execution_id, field_name="UsageObservation.execution_id")
        _require_non_negative_int(
            self.prompt_tokens, field_name="UsageObservation.prompt_tokens"
        )
        _require_non_negative_int(
            self.completion_tokens,
            field_name="UsageObservation.completion_tokens",
        )
        _require_non_negative_int(
            self.total_tokens, field_name="UsageObservation.total_tokens"
        )
        _require_optional_non_empty(
            self.provider_request_id,
            field_name="UsageObservation.provider_request_id",
        )
        _require_optional_non_empty(
            self.estimator_digest,
            field_name="UsageObservation.estimator_digest",
        )
        _require_non_empty(self.policy_ref, field_name="UsageObservation.policy_ref")
        _require_utc_datetime(self.observed_at, field_name="UsageObservation.observed_at")


def estimate_context_budget(
    policy: ContextBudgetPolicy, estimate_input: BudgetEstimateInput
) -> BudgetEstimate:
    """按保守估算器生成 context budget 估算结果。

    :param policy: Host context budget policy。
    :param estimate_input: typed 估算输入。
    :returns: BudgetEstimate。
    :raises TypeError: ``policy`` 或 ``estimate_input`` 类型非法时抛出。
    :raises ValueError: JSON 片段无法 canonical encode 时抛出。
    """

    if not isinstance(policy, ContextBudgetPolicy):
        raise TypeError("policy must be ContextBudgetPolicy")
    if not isinstance(estimate_input, BudgetEstimateInput):
        raise TypeError("estimate_input must be BudgetEstimateInput")
    message_tokens = sum(
        _estimate_text_tokens(fragment.text)
        + DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS
        for fragment in estimate_input.message_fragments
    )
    json_tokens = sum(
        _estimate_json_tokens(fragment.value)
        for fragment in estimate_input.json_fragments
    )
    tool_schema_tokens = sum(
        _estimate_json_tokens(fragment.value)
        + DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS
        for fragment in estimate_input.tool_schema_fragments
    )
    estimated_input_tokens = message_tokens + json_tokens + tool_schema_tokens
    input_budget_tokens = policy.context_window_size
    soft_threshold_tokens = _soft_threshold_tokens(policy)
    hard_threshold_tokens = _hard_threshold_tokens(policy)
    overage_reason = _overage_reason(
        estimated_input_tokens=estimated_input_tokens,
        soft_threshold_tokens=soft_threshold_tokens,
        hard_threshold_tokens=hard_threshold_tokens,
    )
    digest = _estimator_digest(
        policy=policy,
        estimate_input=estimate_input,
        estimated_input_tokens=estimated_input_tokens,
        input_budget_tokens=input_budget_tokens,
        soft_threshold_tokens=soft_threshold_tokens,
        hard_threshold_tokens=hard_threshold_tokens,
    )
    return BudgetEstimate(
        estimated_input_tokens=estimated_input_tokens,
        input_budget_tokens=input_budget_tokens,
        soft_threshold_tokens=soft_threshold_tokens,
        hard_threshold_tokens=hard_threshold_tokens,
        safety_margin_tokens=input_budget_tokens - soft_threshold_tokens,
        estimator_digest=digest,
        overage_reason=overage_reason,
    )


def decide_context_budget(estimate: BudgetEstimate) -> ContextBudgetDecision:
    """根据估算结果做 context budget dispatch 决策。

    :param estimate: budget 估算结果。
    :returns: allow / compact / block 三态决策。
    :raises TypeError: ``estimate`` 不是 BudgetEstimate 时抛出。
    """

    if not isinstance(estimate, BudgetEstimate):
        raise TypeError("estimate must be BudgetEstimate")
    if estimate.estimated_input_tokens >= estimate.hard_threshold_tokens:
        return ContextBudgetDecision.BLOCK_HARD_THRESHOLD
    if estimate.estimated_input_tokens >= estimate.soft_threshold_tokens:
        return ContextBudgetDecision.COMPACT_SOFT_THRESHOLD
    return ContextBudgetDecision.ALLOW_DISPATCH


def _soft_threshold_tokens(policy: ContextBudgetPolicy) -> int:
    """计算 soft threshold。

    :param policy: Host context budget policy。
    :returns: soft threshold token 数。
    """

    return max(
        _MIN_SOFT_THRESHOLD_TOKENS,
        floor(policy.context_window_size * policy.soft_threshold_context_ratio),
    )


def _hard_threshold_tokens(policy: ContextBudgetPolicy) -> int:
    """计算 hard threshold。

    :param policy: Host context budget policy。
    :returns: hard threshold token 数。
    """

    return floor(policy.context_window_size * policy.hard_threshold_context_ratio)


def _overage_reason(
    *,
    estimated_input_tokens: int,
    soft_threshold_tokens: int,
    hard_threshold_tokens: int,
) -> ContextBudgetOverageReason | None:
    """计算超限原因。

    :param estimated_input_tokens: 估算输入 token 数。
    :param soft_threshold_tokens: soft threshold。
    :param hard_threshold_tokens: hard threshold。
    :returns: 超限原因；未超限时为 ``None``。
    """

    if estimated_input_tokens >= hard_threshold_tokens:
        return ContextBudgetOverageReason.HARD_THRESHOLD
    if estimated_input_tokens >= soft_threshold_tokens:
        return ContextBudgetOverageReason.SOFT_THRESHOLD
    return None


def _estimate_text_tokens(text: str) -> int:
    """估算文本 token 数。

    :param text: 文本内容。
    :returns: 保守 token 估算。
    """

    return ceil(len(text) / DEFAULT_ESTIMATOR_CHARS_PER_TOKEN)


def _estimate_json_tokens(value: JsonValue) -> int:
    """估算 JSON token 数。

    :param value: JSON 值。
    :returns: 保守 token 估算。
    :raises ValueError: JSON 值无法 canonical encode 时抛出。
    """

    encoded_size = len(canonical_json_dumps(value).encode("utf-8"))
    return ceil(encoded_size / DEFAULT_ESTIMATOR_JSON_BYTES_PER_TOKEN)


def _estimator_digest(
    *,
    policy: ContextBudgetPolicy,
    estimate_input: BudgetEstimateInput,
    estimated_input_tokens: int,
    input_budget_tokens: int,
    soft_threshold_tokens: int,
    hard_threshold_tokens: int,
) -> str:
    """计算 estimator digest。

    :param policy: Host context budget policy。
    :param estimate_input: 估算输入。
    :param estimated_input_tokens: 估算输入 token 数。
    :param input_budget_tokens: 输入预算 token 数。
    :param soft_threshold_tokens: soft threshold。
    :param hard_threshold_tokens: hard threshold。
    :returns: sha256 digest。
    """

    payload: JsonValue = {
        "policy": {
            "policy_ref": policy.policy_ref,
            "context_window_size": policy.context_window_size,
            "soft_threshold_context_ratio": policy.soft_threshold_context_ratio,
            "hard_threshold_context_ratio": policy.hard_threshold_context_ratio,
        },
        "input": {
            "session_id": estimate_input.session_id,
            "run_id": estimate_input.run_id,
            "message_refs": [
                fragment.fragment_ref for fragment in estimate_input.message_fragments
            ],
            "json_refs": [
                fragment.fragment_ref for fragment in estimate_input.json_fragments
            ],
            "tool_schema_refs": [
                fragment.fragment_ref
                for fragment in estimate_input.tool_schema_fragments
            ],
            "compact_artifact_refs": list(estimate_input.compact_artifact_refs),
            "memory_snapshot_cursor": estimate_input.memory_snapshot_cursor,
            "current_prompt_ref": estimate_input.current_prompt_ref,
        },
        "constants": {
            "default_input_soft_threshold_ratio": (
                DEFAULT_INPUT_SOFT_THRESHOLD_RATIO
            ),
            "chars_per_token": DEFAULT_ESTIMATOR_CHARS_PER_TOKEN,
            "json_bytes_per_token": DEFAULT_ESTIMATOR_JSON_BYTES_PER_TOKEN,
            "message_overhead_tokens": DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS,
            "tool_schema_overhead_tokens": (
                DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS
            ),
        },
        "estimate": {
            "estimated_input_tokens": estimated_input_tokens,
            "input_budget_tokens": input_budget_tokens,
            "soft_threshold_tokens": soft_threshold_tokens,
            "hard_threshold_tokens": hard_threshold_tokens,
        },
    }
    return sha256_digest_json(payload)


def _require_tuple_items(
    value: tuple[BudgetTextFragment, ...] | tuple[BudgetJsonFragment, ...],
    item_type: type[BudgetTextFragment] | type[BudgetJsonFragment],
    *,
    field_name: str,
) -> None:
    """校验 tuple 字段内元素类型。

    :param value: 待校验 tuple。
    :param item_type: 允许的元素类型。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: 字段不是 tuple 或元素类型错误时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, item_type):
            raise TypeError(f"{field_name} items must be {item_type.__name__}")


def _require_utc_datetime(value: datetime, *, field_name: str) -> None:
    """校验 UTC aware datetime。

    :param value: 待校验时间。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: ``value`` 不是 datetime 时抛出。
    :raises ValueError: ``value`` 不是 UTC aware 时抛出。
    """

    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(None):
        raise ValueError(f"{field_name} must be timezone.utc aware")


__all__ = [
    "BudgetEstimate",
    "BudgetEstimateInput",
    "BudgetJsonFragment",
    "BudgetTextFragment",
    "ContextBudgetDecision",
    "ContextBudgetOverageReason",
    "DEFAULT_ESTIMATOR_CHARS_PER_TOKEN",
    "DEFAULT_ESTIMATOR_JSON_BYTES_PER_TOKEN",
    "DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS",
    "DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS",
    "DEFAULT_INPUT_SOFT_THRESHOLD_RATIO",
    "UsageObservation",
    "decide_context_budget",
    "estimate_context_budget",
]
