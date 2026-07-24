"""Host context budget estimator、adaptive sizing 与五阶段决策。

本模块实现 Host-owned typed budget 估算与阈值决策。估算
依据来自 Host RunInputBuilder / Context Governance 可提供的 typed view，
不读取 Engine spec、provider overflow payload、metadata 或 extra payload。
当前 complete candidate 始终先生成 conservative estimate；兼容 durable usage
anchor 可通过固定 signed-delta 公式校正 prediction，任何不可用或非法 anchor
均回退同一个 complete-candidate estimate。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from math import ceil, floor
from typing import TYPE_CHECKING
import unicodedata

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
from dayu.host.durable.codec import (
    canonical_json_dumps,
    is_sha256_digest,
    sha256_digest_json,
)

if TYPE_CHECKING:
    # anchor resolver消费本模块的estimator contract；此处延迟导入只用于打破
    # 两个owner类型之间的模块初始化环，不承担兼容或可选依赖语义。
    from dayu.host.context_anchor import ContextAnchorResolution

DEFAULT_INPUT_SOFT_THRESHOLD_RATIO = DEFAULT_SOFT_THRESHOLD_CONTEXT_RATIO
DEFAULT_ESTIMATOR_CHARS_PER_TOKEN = 3
DEFAULT_ESTIMATOR_CJK_CHARS_PER_TOKEN = 1
DEFAULT_ESTIMATOR_JSON_BYTES_PER_TOKEN = 3
DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS = 12
DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS = 16
CONTEXT_ESTIMATOR_ID = "dayu.host.conservative_context_budget"
CONTEXT_ESTIMATOR_VERSION = "1"
MAX_CONTEXT_TOKEN_COUNT = 2**63 - 1
_UTILIZATION_BASIS_POINTS_SCALE = 10_000
# Post-compact ordinary dispatch 固定为一条 system envelope 加当前输入 user message。
POST_COMPACT_BASE_MESSAGE_COUNT = 2
USAGE_OBSERVATION_STATUS_OBSERVED = "observed"
USAGE_OBSERVATION_STATUS_ESTIMATE_UNAVAILABLE = "estimate_unavailable"
_MIN_SOFT_THRESHOLD_TOKENS = 1
_CJK_EAST_ASIAN_WIDTH_VALUES = frozenset(("W", "F"))


class ContextBudgetDecision(StrEnum):
    """Context budget 阈值决策。"""

    ALLOW_DISPATCH = "allow_dispatch"
    COMPACT_SOFT_THRESHOLD = "compact_soft_threshold"
    BLOCK_HARD_THRESHOLD = "block_hard_threshold"


class ContextBudgetOverageReason(StrEnum):
    """Context budget 超限原因。"""

    SOFT_THRESHOLD = "soft_threshold"
    HARD_THRESHOLD = "hard_threshold"


class ContextEstimateMethod(StrEnum):
    """Context sizing 使用的估算方法。"""

    USAGE_ANCHORED = "usage_anchored"
    CONSERVATIVE_FALLBACK = "conservative_fallback"


class ContextPressureLevel(StrEnum):
    """Context sizing 的预算压力等级。"""

    NORMAL = "normal"
    SOFT_THRESHOLD_EXCEEDED = "soft_threshold_exceeded"
    HARD_THRESHOLD_EXCEEDED = "hard_threshold_exceeded"


class ContextSizingStage(StrEnum):
    """Context sizing 所属的 dispatch 阶段。"""

    ORDINARY = "ordinary"
    POST_COMPACT = "post_compact"
    REACTIVE_POST_COMPACT = "reactive_post_compact"
    DISPATCH_FALLBACK = "dispatch_fallback"
    CONTINUATION = "continuation"


class ContextSizingFallbackReason(StrEnum):
    """Context sizing conservative fallback 的封闭原因。"""

    USAGE_MISSING = "usage_missing"
    USAGE_INVALID = "usage_invalid"
    USAGE_AMBIGUOUS = "usage_ambiguous"
    ITERATION_INCOMPLETE = "iteration_incomplete"
    ITERATION_COMPLETION_AMBIGUOUS = "iteration_completion_ambiguous"
    ITERATION_FINISH_REASON_INELIGIBLE = "iteration_finish_reason_ineligible"
    ITERATION_LINK_MISSING = "iteration_link_missing"
    ITERATION_LINK_INVALID = "iteration_link_invalid"
    MANIFEST_INCOMPLETE = "manifest_incomplete"
    MANIFEST_MISMATCH = "manifest_mismatch"
    RUNNER_CALL_KIND_INELIGIBLE = "runner_call_kind_ineligible"
    PROVIDER_MISMATCH = "provider_mismatch"
    MODEL_MISMATCH = "model_mismatch"
    CONTEXT_WINDOW_MISMATCH = "context_window_mismatch"
    ESTIMATOR_CONTRACT_MISMATCH = "estimator_contract_mismatch"
    REQUEST_SEMANTICS_MISMATCH = "request_semantics_mismatch"
    ACCEPTED_COMPACT_INVALIDATED = "accepted_compact_invalidated"
    LINEAGE_GAP = "lineage_gap"
    ANCHOR_VALUE_INVALID = "anchor_value_invalid"
    PREDICTION_NON_POSITIVE = "prediction_non_positive"
    ARITHMETIC_RANGE_INVALID = "arithmetic_range_invalid"


@dataclass(frozen=True, slots=True)
class ContextEstimatorContract:
    """稳定的 conservative estimator identity。

    :param estimator_id: estimator 语义标识。
    :param estimator_version: estimator contract 版本。
    """

    estimator_id: str
    estimator_version: str

    def __post_init__(self) -> None:
        """校验 estimator identity。

        :returns: ``None``。
        :raises ValueError: 任一 identity 字段为空时抛出。
        """

        _require_non_empty(
            self.estimator_id,
            field_name="ContextEstimatorContract.estimator_id",
        )
        _require_non_empty(
            self.estimator_version,
            field_name="ContextEstimatorContract.estimator_version",
        )


CONTEXT_ESTIMATOR_CONTRACT = ContextEstimatorContract(
    estimator_id=CONTEXT_ESTIMATOR_ID,
    estimator_version=CONTEXT_ESTIMATOR_VERSION,
)


@dataclass(frozen=True, slots=True)
class ContextAnchorDiagnostic:
    """Host-private usage anchor 诊断。

    :param manifest_event_id: anchor manifest event id。
    :param manifest_payload_ref: anchor manifest payload ref。
    :param manifest_digest: anchor manifest digest。
    :param iteration_link_event_id: accepted iteration link event id。
    :param usage_event_id: paired usage observation event id。
    :param usage_observation_digest: normalized usage observation digest。
    :param iteration_completed_event_id: accepted iteration completion event id。
    :param usage_anchor_tokens: provider-reported anchor input tokens。
    :param conservative_anchor_tokens: anchor candidate conservative tokens。
    :param conservative_current_tokens: current candidate conservative tokens。
    :param signed_delta_tokens: signed conservative delta。
    :param predicted_input_tokens: anchored prediction。
    """

    manifest_event_id: str
    manifest_payload_ref: str
    manifest_digest: str
    iteration_link_event_id: str
    usage_event_id: str
    usage_observation_digest: str
    iteration_completed_event_id: str
    usage_anchor_tokens: int
    conservative_anchor_tokens: int
    conservative_current_tokens: int
    signed_delta_tokens: int
    predicted_input_tokens: int

    def __post_init__(self) -> None:
        """校验 anchor refs、digest、token 与固定公式。

        :returns: ``None``。
        :raises TypeError: 整数字段不是严格整数时抛出。
        :raises ValueError: ref、digest、范围或公式不一致时抛出。
        """

        for field_name, value in (
            ("manifest_event_id", self.manifest_event_id),
            ("manifest_payload_ref", self.manifest_payload_ref),
            ("iteration_link_event_id", self.iteration_link_event_id),
            ("usage_event_id", self.usage_event_id),
            ("iteration_completed_event_id", self.iteration_completed_event_id),
        ):
            _require_non_empty(
                value,
                field_name=f"ContextAnchorDiagnostic.{field_name}",
            )
        for field_name, value in (
            ("manifest_digest", self.manifest_digest),
            ("usage_observation_digest", self.usage_observation_digest),
        ):
            _require_sha256_digest(
                value,
                field_name=f"ContextAnchorDiagnostic.{field_name}",
            )
        for field_name, value in (
            ("usage_anchor_tokens", self.usage_anchor_tokens),
            ("conservative_anchor_tokens", self.conservative_anchor_tokens),
            ("conservative_current_tokens", self.conservative_current_tokens),
        ):
            _require_context_token_count(
                value,
                field_name=f"ContextAnchorDiagnostic.{field_name}",
            )
        _require_int(
            self.signed_delta_tokens,
            field_name="ContextAnchorDiagnostic.signed_delta_tokens",
        )
        if abs(self.signed_delta_tokens) > MAX_CONTEXT_TOKEN_COUNT:
            raise ValueError("anchor signed delta exceeds supported range")
        _require_positive_int(
            self.predicted_input_tokens,
            field_name="ContextAnchorDiagnostic.predicted_input_tokens",
        )
        if self.predicted_input_tokens > MAX_CONTEXT_TOKEN_COUNT:
            raise ValueError("anchor prediction exceeds supported range")
        expected_delta = (
            self.conservative_current_tokens
            - self.conservative_anchor_tokens
        )
        if self.signed_delta_tokens != expected_delta:
            raise ValueError("anchor signed delta mismatch")
        if (
            self.predicted_input_tokens
            != self.usage_anchor_tokens + self.signed_delta_tokens
        ):
            raise ValueError("anchor prediction formula mismatch")


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
    input_snapshot_digest: str | None = None

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
        _require_optional_non_empty(
            self.input_snapshot_digest,
            field_name="BudgetEstimateInput.input_snapshot_digest",
        )


@dataclass(frozen=True, slots=True)
class BudgetEstimate:
    """Context budget 估算结果。

    :param estimated_input_tokens: 保守估算的输入 token 数。
    :param input_budget_tokens: Host policy 的 ``context_window_size``。
    :param soft_threshold_tokens: soft threshold token 数。
    :param hard_threshold_tokens: hard threshold token 数。
    :param safety_margin_tokens: soft threshold 上方预留的安全余量 token 数。
    :param estimator_digest: 估算器契约、完整估算输入与固定估算常量的 digest。
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
class ContextSizingResult:
    """单个 complete candidate 的 Host-owned sizing truth。

    :param stage: sizing 阶段。
    :param candidate_input_cursor: candidate source watermark。
    :param candidate_input_projection_ref: identity-free candidate projection ref。
    :param candidate_input_digest: complete candidate digest。
    :param estimator_contract: stable estimator identity。
    :param estimator_digest: 当前 candidate estimate digest。
    :param conservative_input_tokens: 当前 complete candidate 的 conservative tokens。
    :param estimate_method: 当前估算方法。
    :param predicted_input_tokens: 实际预算决策 token。
    :param context_window_size: policy context window。
    :param soft_threshold_tokens: soft threshold。
    :param hard_threshold_tokens: hard threshold。
    :param utilization_basis_points: 未 clamp 的基点利用率。
    :param pressure_level: 预算压力。
    :param budget_decision: exact budget decision。
    :param policy_ref: Host context policy ref。
    :param policy_snapshot_digest: frozen context policy digest。
    :param anchor_diagnostic: usage-anchored时的Host-private诊断。
    :param fallback_reason: conservative fallback 原因。
    """

    stage: ContextSizingStage
    candidate_input_cursor: int
    candidate_input_projection_ref: str
    candidate_input_digest: str
    estimator_contract: ContextEstimatorContract
    estimator_digest: str
    conservative_input_tokens: int
    estimate_method: ContextEstimateMethod
    predicted_input_tokens: int
    context_window_size: int
    soft_threshold_tokens: int
    hard_threshold_tokens: int
    utilization_basis_points: int
    pressure_level: ContextPressureLevel
    budget_decision: ContextBudgetDecision
    policy_ref: str
    policy_snapshot_digest: str
    anchor_diagnostic: ContextAnchorDiagnostic | None
    fallback_reason: ContextSizingFallbackReason | None

    def __post_init__(self) -> None:
        """校验 anchored/fallback sizing 单一真源。

        :returns: ``None``。
        :raises TypeError: enum 或整数字段类型非法时抛出。
        :raises ValueError: token、method/decision 不变量非法时抛出。
        """

        if not isinstance(self.stage, ContextSizingStage):
            raise TypeError("ContextSizingResult.stage must be ContextSizingStage")
        if not isinstance(self.estimator_contract, ContextEstimatorContract):
            raise TypeError(
                "ContextSizingResult.estimator_contract must be "
                "ContextEstimatorContract"
            )
        if not isinstance(self.estimate_method, ContextEstimateMethod):
            raise TypeError(
                "ContextSizingResult.estimate_method must be ContextEstimateMethod"
            )
        _require_non_negative_int(
            self.candidate_input_cursor,
            field_name="ContextSizingResult.candidate_input_cursor",
        )
        for field_name, value in (
            (
                "ContextSizingResult.candidate_input_projection_ref",
                self.candidate_input_projection_ref,
            ),
            ("ContextSizingResult.candidate_input_digest", self.candidate_input_digest),
            ("ContextSizingResult.estimator_digest", self.estimator_digest),
            ("ContextSizingResult.policy_ref", self.policy_ref),
            (
                "ContextSizingResult.policy_snapshot_digest",
                self.policy_snapshot_digest,
            ),
        ):
            _require_non_empty(value, field_name=field_name)
        for field_name, value in (
            (
                "ContextSizingResult.conservative_input_tokens",
                self.conservative_input_tokens,
            ),
            (
                "ContextSizingResult.predicted_input_tokens",
                self.predicted_input_tokens,
            ),
            (
                "ContextSizingResult.utilization_basis_points",
                self.utilization_basis_points,
            ),
        ):
            _require_non_negative_int(value, field_name=field_name)
        _require_positive_int(
            self.context_window_size,
            field_name="ContextSizingResult.context_window_size",
        )
        _require_positive_int(
            self.soft_threshold_tokens,
            field_name="ContextSizingResult.soft_threshold_tokens",
        )
        _require_positive_int(
            self.hard_threshold_tokens,
            field_name="ContextSizingResult.hard_threshold_tokens",
        )
        if self.conservative_input_tokens > MAX_CONTEXT_TOKEN_COUNT:
            raise ValueError("conservative_input_tokens exceeds supported range")
        if self.predicted_input_tokens > MAX_CONTEXT_TOKEN_COUNT:
            raise ValueError("predicted_input_tokens exceeds supported range")
        if self.estimate_method is ContextEstimateMethod.CONSERVATIVE_FALLBACK:
            if not isinstance(self.fallback_reason, ContextSizingFallbackReason):
                raise TypeError(
                    "fallback sizing requires ContextSizingFallbackReason"
                )
            if self.anchor_diagnostic is not None:
                raise ValueError("fallback sizing must not carry anchor diagnostic")
            if self.predicted_input_tokens != self.conservative_input_tokens:
                raise ValueError(
                    "conservative sizing predicted_input_tokens must equal estimate"
                )
        elif self.estimate_method is ContextEstimateMethod.USAGE_ANCHORED:
            if self.fallback_reason is not None:
                raise ValueError("anchored sizing must not carry fallback reason")
            if not isinstance(self.anchor_diagnostic, ContextAnchorDiagnostic):
                raise TypeError(
                    "anchored sizing requires ContextAnchorDiagnostic"
                )
            if (
                self.anchor_diagnostic.conservative_current_tokens
                != self.conservative_input_tokens
                or self.anchor_diagnostic.predicted_input_tokens
                != self.predicted_input_tokens
            ):
                raise ValueError("anchored sizing diagnostic mismatch")
        else:
            raise AssertionError("context estimate method is not exhaustive")
        validate_context_threshold_ordering(
            soft_threshold_tokens=self.soft_threshold_tokens,
            hard_threshold_tokens=self.hard_threshold_tokens,
        )
        expected_utilization = context_utilization_basis_points(
            predicted_input_tokens=self.predicted_input_tokens,
            context_window_size=self.context_window_size,
        )
        if self.utilization_basis_points != expected_utilization:
            raise ValueError("ContextSizingResult.utilization_basis_points mismatch")
        expected_pressure, expected_decision = _pressure_and_decision(
            stage=self.stage,
            predicted_input_tokens=self.predicted_input_tokens,
            soft_threshold_tokens=self.soft_threshold_tokens,
            hard_threshold_tokens=self.hard_threshold_tokens,
        )
        if self.pressure_level is not expected_pressure:
            raise ValueError("ContextSizingResult.pressure_level mismatch")
        if self.budget_decision is not expected_decision:
            raise ValueError("ContextSizingResult.budget_decision mismatch")


@dataclass(frozen=True, slots=True)
class UsageObservation:
    """Runner usage 的 Host internal observation。

    :param session_id: Session id。
    :param run_id: Run id。
    :param attempt_id: Attempt id。
    :param execution_id: execution id。
    :param iteration_id: Engine iteration id。
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
    iteration_id: str
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
        _require_non_empty(self.iteration_id, field_name="UsageObservation.iteration_id")
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


@dataclass(frozen=True, slots=True)
class UsageObservationDiagnostic:
    """Runner usage observation 的诊断与校准数据。

    :param observation_digest: usage observation 与估算关联的稳定 digest。
    :param estimator_digest: 对应估算 digest；估算不可用时为 ``None``。
    :param policy_ref: 对应 Host context budget policy ref。
    :param estimated_input_tokens: 对应估算输入 token 数；估算不可用时为 ``None``。
    :param prompt_token_delta: provider prompt token 与估算输入 token 的差值；
        估算不可用时为 ``None``。
    :param status: observation 诊断状态。
    """

    observation_digest: str
    estimator_digest: str | None
    policy_ref: str
    estimated_input_tokens: int | None
    prompt_token_delta: int | None
    status: str

    def __post_init__(self) -> None:
        """校验 usage observation diagnostic。

        :returns: ``None``。
        :raises TypeError: token 字段类型非法时抛出。
        :raises ValueError: 字符串为空或 token 为负数时抛出。
        """

        _require_non_empty(
            self.observation_digest,
            field_name="UsageObservationDiagnostic.observation_digest",
        )
        _require_optional_non_empty(
            self.estimator_digest,
            field_name="UsageObservationDiagnostic.estimator_digest",
        )
        _require_non_empty(
            self.policy_ref,
            field_name="UsageObservationDiagnostic.policy_ref",
        )
        if self.estimated_input_tokens is not None:
            _require_non_negative_int(
                self.estimated_input_tokens,
                field_name="UsageObservationDiagnostic.estimated_input_tokens",
            )
        if self.prompt_token_delta is not None:
            _require_int(
                self.prompt_token_delta,
                field_name="UsageObservationDiagnostic.prompt_token_delta",
            )
        _require_non_empty(self.status, field_name="UsageObservationDiagnostic.status")


def build_usage_observation_diagnostic(
    observation: UsageObservation,
    *,
    estimated_input_tokens: int | None,
    status: str,
) -> UsageObservationDiagnostic:
    """根据 usage observation 生成 post-call 诊断与校准数据。

    本函数只计算诊断数据，不调用 ``decide_context_budget``，不返回
    ``ContextBudgetDecision``，也不修改传入的估算或 observation。

    :param observation: Host internal usage observation。
    :param estimated_input_tokens: 对应估算输入 token 数；估算不可用时为
        ``None``。
    :param status: observation 诊断状态。
    :returns: usage observation diagnostic。
    :raises TypeError: 输入类型或 token 字段非法时抛出。
    :raises ValueError: 字符串为空、token 为负数或 digest 计算失败时抛出。
    """

    if not isinstance(observation, UsageObservation):
        raise TypeError("observation must be UsageObservation")
    if estimated_input_tokens is not None:
        _require_non_negative_int(
            estimated_input_tokens,
            field_name="estimated_input_tokens",
        )
    _require_non_empty(status, field_name="status")
    prompt_token_delta = (
        observation.prompt_tokens - estimated_input_tokens
        if estimated_input_tokens is not None
        else None
    )
    return UsageObservationDiagnostic(
        observation_digest=_usage_observation_digest(
            observation=observation,
            estimated_input_tokens=estimated_input_tokens,
            prompt_token_delta=prompt_token_delta,
            status=status,
        ),
        estimator_digest=observation.estimator_digest,
        policy_ref=observation.policy_ref,
        estimated_input_tokens=estimated_input_tokens,
        prompt_token_delta=prompt_token_delta,
        status=status,
    )


def build_conservative_context_sizing_result(
    *,
    stage: ContextSizingStage,
    candidate_input_cursor: int,
    candidate_input_projection_ref: str,
    candidate_input_digest: str,
    policy: ContextBudgetPolicy,
    estimate: BudgetEstimate,
    fallback_reason: ContextSizingFallbackReason = (
        ContextSizingFallbackReason.USAGE_MISSING
    ),
) -> ContextSizingResult:
    """从 complete candidate estimate 构造 Slice 1 conservative sizing truth。

    :param stage: 当前 sizing stage。
    :param candidate_input_cursor: candidate source watermark。
    :param candidate_input_projection_ref: identity-free candidate projection ref。
    :param candidate_input_digest: complete candidate digest。
    :param policy: Host context budget policy。
    :param estimate: 同 candidate 的 conservative estimate。
    :param fallback_reason: conservative fallback 原因。
    :returns: frozen sizing result。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: policy/estimate 不同源或字段越界时抛出。
    """

    if not isinstance(stage, ContextSizingStage):
        raise TypeError("stage must be ContextSizingStage")
    if not isinstance(policy, ContextBudgetPolicy):
        raise TypeError("policy must be ContextBudgetPolicy")
    if not isinstance(estimate, BudgetEstimate):
        raise TypeError("estimate must be BudgetEstimate")
    if estimate.input_budget_tokens != policy.context_window_size:
        raise ValueError("estimate context window does not match policy")
    return build_context_sizing_result_from_atoms(
        stage=stage,
        candidate_input_cursor=candidate_input_cursor,
        candidate_input_projection_ref=candidate_input_projection_ref,
        candidate_input_digest=candidate_input_digest,
        estimator_contract=CONTEXT_ESTIMATOR_CONTRACT,
        estimator_digest=estimate.estimator_digest,
        conservative_input_tokens=estimate.estimated_input_tokens,
        context_window_size=policy.context_window_size,
        soft_threshold_tokens=estimate.soft_threshold_tokens,
        hard_threshold_tokens=estimate.hard_threshold_tokens,
        policy_ref=policy.policy_ref,
        policy_snapshot_digest=context_budget_policy_snapshot_digest(policy),
        anchor_resolution=None,
        fallback_reason=fallback_reason,
    )


def build_conservative_context_sizing_result_from_atoms(
    *,
    stage: ContextSizingStage,
    candidate_input_cursor: int,
    candidate_input_projection_ref: str,
    candidate_input_digest: str,
    estimator_contract: ContextEstimatorContract,
    estimator_digest: str,
    conservative_input_tokens: int,
    context_window_size: int,
    soft_threshold_tokens: int,
    hard_threshold_tokens: int,
    policy_ref: str,
    policy_snapshot_digest: str,
    fallback_reason: ContextSizingFallbackReason = (
        ContextSizingFallbackReason.USAGE_MISSING
    ),
) -> ContextSizingResult:
    """从已冻结且同源的 canonical atoms 构造 conservative sizing truth。

    该入口服务不能重读当前 policy 的 continuation producer；它只消费 source
    budget fact 已承诺的 thresholds 与 manifest 已冻结的 estimator/policy atoms，
    不执行 usage 选择、anchor pairing 或当前配置重算。

    :param stage: 当前 sizing stage。
    :param candidate_input_cursor: candidate source watermark。
    :param candidate_input_projection_ref: exact candidate projection ref。
    :param candidate_input_digest: complete candidate digest。
    :param estimator_contract: frozen estimator identity。
    :param estimator_digest: 当前 candidate conservative estimate digest。
    :param conservative_input_tokens: 当前 candidate conservative tokens。
    :param context_window_size: frozen policy context window。
    :param soft_threshold_tokens: source policy soft threshold。
    :param hard_threshold_tokens: source policy hard threshold。
    :param policy_ref: frozen context policy ref。
    :param policy_snapshot_digest: frozen context policy digest。
    :param fallback_reason: conservative fallback closed reason。
    :returns: 完整 conservative sizing result。
    :raises TypeError: enum、contract 或整数字段类型非法时抛出。
    :raises ValueError: atoms 违反 sizing contract 时抛出。
    """

    if not isinstance(stage, ContextSizingStage):
        raise TypeError("stage must be ContextSizingStage")
    if not isinstance(estimator_contract, ContextEstimatorContract):
        raise TypeError("estimator_contract must be ContextEstimatorContract")
    return build_context_sizing_result_from_atoms(
        stage=stage,
        candidate_input_cursor=candidate_input_cursor,
        candidate_input_projection_ref=candidate_input_projection_ref,
        candidate_input_digest=candidate_input_digest,
        estimator_contract=estimator_contract,
        estimator_digest=estimator_digest,
        conservative_input_tokens=conservative_input_tokens,
        context_window_size=context_window_size,
        soft_threshold_tokens=soft_threshold_tokens,
        hard_threshold_tokens=hard_threshold_tokens,
        policy_ref=policy_ref,
        policy_snapshot_digest=policy_snapshot_digest,
        anchor_resolution=None,
        fallback_reason=fallback_reason,
    )


def build_context_sizing_result(
    *,
    stage: ContextSizingStage,
    candidate_input_cursor: int,
    candidate_input_projection_ref: str,
    candidate_input_digest: str,
    policy: ContextBudgetPolicy,
    estimate: BudgetEstimate,
    anchor_resolution: ContextAnchorResolution,
) -> ContextSizingResult:
    """从当前完整估算与 durable anchor resolution 构造唯一 sizing truth。

    :param stage: 当前 sizing stage。
    :param candidate_input_cursor: canonical fact identity使用的candidate cursor。
    :param candidate_input_projection_ref: exact candidate projection ref。
    :param candidate_input_digest: complete candidate digest。
    :param policy: frozen Host context policy。
    :param estimate: 当前完整candidate的conservative estimate。
    :param anchor_resolution: 同transaction resolver结果。
    :returns: usage-anchored或完整conservative fallback结果。
    :raises TypeError: 参数类型非法时抛出。
    :raises ValueError: policy/estimate/anchor不满足typed contract时抛出。
    """

    if not isinstance(policy, ContextBudgetPolicy):
        raise TypeError("policy must be ContextBudgetPolicy")
    if not isinstance(estimate, BudgetEstimate):
        raise TypeError("estimate must be BudgetEstimate")
    if estimate.input_budget_tokens != policy.context_window_size:
        raise ValueError("estimate context window does not match policy")
    return build_context_sizing_result_from_atoms(
        stage=stage,
        candidate_input_cursor=candidate_input_cursor,
        candidate_input_projection_ref=candidate_input_projection_ref,
        candidate_input_digest=candidate_input_digest,
        estimator_contract=CONTEXT_ESTIMATOR_CONTRACT,
        estimator_digest=estimate.estimator_digest,
        conservative_input_tokens=estimate.estimated_input_tokens,
        context_window_size=policy.context_window_size,
        soft_threshold_tokens=estimate.soft_threshold_tokens,
        hard_threshold_tokens=estimate.hard_threshold_tokens,
        policy_ref=policy.policy_ref,
        policy_snapshot_digest=context_budget_policy_snapshot_digest(policy),
        anchor_resolution=anchor_resolution,
        fallback_reason=None,
    )


def build_context_sizing_result_from_atoms(
    *,
    stage: ContextSizingStage,
    candidate_input_cursor: int,
    candidate_input_projection_ref: str,
    candidate_input_digest: str,
    estimator_contract: ContextEstimatorContract,
    estimator_digest: str,
    conservative_input_tokens: int,
    context_window_size: int,
    soft_threshold_tokens: int,
    hard_threshold_tokens: int,
    policy_ref: str,
    policy_snapshot_digest: str,
    anchor_resolution: ContextAnchorResolution | None,
    fallback_reason: ContextSizingFallbackReason | None,
) -> ContextSizingResult:
    """从同源atoms和可选resolver结果构造anchored/fallback sizing。

    ``anchor_resolution=None``只供已明确选择conservative的owner使用，并要求
    显式提供fallback reason；普通adaptive caller必须传resolver结果。

    :param stage: 当前 sizing stage。
    :param candidate_input_cursor: canonical fact identity使用的candidate cursor。
    :param candidate_input_projection_ref: exact candidate projection ref。
    :param candidate_input_digest: complete candidate digest。
    :param estimator_contract: frozen estimator identity。
    :param estimator_digest: 当前candidate estimator digest。
    :param conservative_input_tokens: ``E_current``。
    :param context_window_size: frozen context window。
    :param soft_threshold_tokens: frozen soft threshold。
    :param hard_threshold_tokens: frozen hard threshold。
    :param policy_ref: frozen policy ref。
    :param policy_snapshot_digest: frozen policy digest。
    :param anchor_resolution: 同transaction resolver结果；强制fallback时为``None``。
    :param fallback_reason: 强制fallback原因；resolver存在时必须为``None``。
    :returns: 完整sizing result。
    :raises TypeError: enum、contract、resolution或整数类型非法时抛出。
    :raises ValueError: atoms、resolution或公式违反contract时抛出。
    """

    from dayu.host.context_anchor import ContextAnchorResolution

    estimate_method = ContextEstimateMethod.CONSERVATIVE_FALLBACK
    predicted = conservative_input_tokens
    anchor_diagnostic: ContextAnchorDiagnostic | None = None
    resolved_fallback = fallback_reason
    if anchor_resolution is not None:
        if not isinstance(anchor_resolution, ContextAnchorResolution):
            raise TypeError("anchor_resolution must be ContextAnchorResolution")
        if fallback_reason is not None:
            raise ValueError(
                "resolver result and explicit fallback reason are mutually exclusive"
            )
        anchor = anchor_resolution.anchor
        if anchor is None:
            resolved_fallback = anchor_resolution.fallback_reason
        else:
            resolved_fallback = None
            anchor_values = (
                anchor.usage_anchor_tokens,
                anchor.conservative_anchor_tokens,
                conservative_input_tokens,
            )
            if not all(_is_context_token_count(value) for value in anchor_values):
                resolved_fallback = ContextSizingFallbackReason.ANCHOR_VALUE_INVALID
            else:
                signed_delta = (
                    conservative_input_tokens
                    - anchor.conservative_anchor_tokens
                )
                anchored_prediction = anchor.usage_anchor_tokens + signed_delta
                if (
                    abs(signed_delta) > MAX_CONTEXT_TOKEN_COUNT
                    or anchored_prediction > MAX_CONTEXT_TOKEN_COUNT
                ):
                    resolved_fallback = (
                        ContextSizingFallbackReason.ARITHMETIC_RANGE_INVALID
                    )
                elif anchored_prediction <= 0:
                    resolved_fallback = (
                        ContextSizingFallbackReason.PREDICTION_NON_POSITIVE
                    )
                else:
                    estimate_method = ContextEstimateMethod.USAGE_ANCHORED
                    predicted = anchored_prediction
                    anchor_diagnostic = ContextAnchorDiagnostic(
                        manifest_event_id=anchor.manifest_event_id,
                        manifest_payload_ref=anchor.manifest_payload_ref,
                        manifest_digest=anchor.manifest_digest,
                        iteration_link_event_id=anchor.iteration_link_event_id,
                        usage_event_id=anchor.usage_event_id,
                        usage_observation_digest=(
                            anchor.usage_observation_digest
                        ),
                        iteration_completed_event_id=(
                            anchor.iteration_completed_event_id
                        ),
                        usage_anchor_tokens=anchor.usage_anchor_tokens,
                        conservative_anchor_tokens=(
                            anchor.conservative_anchor_tokens
                        ),
                        conservative_current_tokens=(
                            conservative_input_tokens
                        ),
                        signed_delta_tokens=signed_delta,
                        predicted_input_tokens=anchored_prediction,
                    )
    if resolved_fallback is None and anchor_diagnostic is None:
        raise ValueError("fallback sizing requires a closed reason")
    pressure, decision = _pressure_and_decision(
        stage=stage,
        predicted_input_tokens=predicted,
        soft_threshold_tokens=soft_threshold_tokens,
        hard_threshold_tokens=hard_threshold_tokens,
    )
    return ContextSizingResult(
        stage=stage,
        candidate_input_cursor=candidate_input_cursor,
        candidate_input_projection_ref=candidate_input_projection_ref,
        candidate_input_digest=candidate_input_digest,
        estimator_contract=estimator_contract,
        estimator_digest=estimator_digest,
        conservative_input_tokens=conservative_input_tokens,
        estimate_method=estimate_method,
        predicted_input_tokens=predicted,
        context_window_size=context_window_size,
        soft_threshold_tokens=soft_threshold_tokens,
        hard_threshold_tokens=hard_threshold_tokens,
        utilization_basis_points=context_utilization_basis_points(
            predicted_input_tokens=predicted,
            context_window_size=context_window_size,
        ),
        pressure_level=pressure,
        budget_decision=decision,
        policy_ref=policy_ref,
        policy_snapshot_digest=policy_snapshot_digest,
        anchor_diagnostic=anchor_diagnostic,
        fallback_reason=resolved_fallback,
    )


def build_frozen_context_sizing_result_from_atoms(
    *,
    stage: ContextSizingStage,
    candidate_input_cursor: int,
    candidate_input_projection_ref: str,
    candidate_input_digest: str,
    estimator_contract: ContextEstimatorContract,
    estimator_digest: str,
    conservative_input_tokens: int,
    estimate_method: ContextEstimateMethod,
    predicted_input_tokens: int,
    context_window_size: int,
    soft_threshold_tokens: int,
    hard_threshold_tokens: int,
    policy_ref: str,
    policy_snapshot_digest: str,
    anchor_diagnostic: ContextAnchorDiagnostic | None,
    fallback_reason: ContextSizingFallbackReason | None,
) -> ContextSizingResult:
    """从已接受source fact atoms重建exact replay sizing truth。

    本入口只供 startup exact replay 使用：保留source method、prediction与
    diagnostic，不重新解析anchor或重新计算估算；仅按新stage重新派生
    pressure/action与fact identity。

    :param stage: 新 fact 的 sizing stage。
    :param candidate_input_cursor: 新 fact 的 candidate cursor。
    :param candidate_input_projection_ref: exact candidate projection ref。
    :param candidate_input_digest: exact complete candidate digest。
    :param estimator_contract: source estimator identity。
    :param estimator_digest: source estimator digest。
    :param conservative_input_tokens: source ``E_current``。
    :param estimate_method: source accepted estimate method。
    :param predicted_input_tokens: source accepted prediction。
    :param context_window_size: source frozen context window。
    :param soft_threshold_tokens: source soft threshold。
    :param hard_threshold_tokens: source hard threshold。
    :param policy_ref: source policy ref。
    :param policy_snapshot_digest: source policy digest。
    :param anchor_diagnostic: source Host-private anchor diagnostic。
    :param fallback_reason: source conservative fallback reason。
    :returns: 新identity下语义不变的sizing result。
    :raises TypeError: typed atoms非法时抛出。
    :raises ValueError: source atoms不满足sizing invariant时抛出。
    """

    if not isinstance(stage, ContextSizingStage):
        raise TypeError("stage must be ContextSizingStage")
    if not isinstance(estimator_contract, ContextEstimatorContract):
        raise TypeError("estimator_contract must be ContextEstimatorContract")
    if not isinstance(estimate_method, ContextEstimateMethod):
        raise TypeError("estimate_method must be ContextEstimateMethod")
    pressure, decision = _pressure_and_decision(
        stage=stage,
        predicted_input_tokens=predicted_input_tokens,
        soft_threshold_tokens=soft_threshold_tokens,
        hard_threshold_tokens=hard_threshold_tokens,
    )
    return ContextSizingResult(
        stage=stage,
        candidate_input_cursor=candidate_input_cursor,
        candidate_input_projection_ref=candidate_input_projection_ref,
        candidate_input_digest=candidate_input_digest,
        estimator_contract=estimator_contract,
        estimator_digest=estimator_digest,
        conservative_input_tokens=conservative_input_tokens,
        estimate_method=estimate_method,
        predicted_input_tokens=predicted_input_tokens,
        context_window_size=context_window_size,
        soft_threshold_tokens=soft_threshold_tokens,
        hard_threshold_tokens=hard_threshold_tokens,
        utilization_basis_points=context_utilization_basis_points(
            predicted_input_tokens=predicted_input_tokens,
            context_window_size=context_window_size,
        ),
        pressure_level=pressure,
        budget_decision=decision,
        policy_ref=policy_ref,
        policy_snapshot_digest=policy_snapshot_digest,
        anchor_diagnostic=anchor_diagnostic,
        fallback_reason=fallback_reason,
    )


def rebind_frozen_context_sizing_result(
    source: ContextSizingResult,
    *,
    stage: ContextSizingStage,
    candidate_input_cursor: int,
) -> ContextSizingResult:
    """为exact replay source sizing建立新stage/cursor fact identity。

    :param source: 已strict验证的source sizing truth。
    :param stage: 新 fact 的 stage。
    :param candidate_input_cursor: 新 manifest event sequence。
    :returns: method、prediction、diagnostic与source atoms不变的新结果。
    :raises TypeError: source或stage类型非法时抛出。
    :raises ValueError: 新cursor或source invariant非法时抛出。
    """

    if not isinstance(source, ContextSizingResult):
        raise TypeError("source must be ContextSizingResult")
    return build_frozen_context_sizing_result_from_atoms(
        stage=stage,
        candidate_input_cursor=candidate_input_cursor,
        candidate_input_projection_ref=(
            source.candidate_input_projection_ref
        ),
        candidate_input_digest=source.candidate_input_digest,
        estimator_contract=source.estimator_contract,
        estimator_digest=source.estimator_digest,
        conservative_input_tokens=source.conservative_input_tokens,
        estimate_method=source.estimate_method,
        predicted_input_tokens=source.predicted_input_tokens,
        context_window_size=source.context_window_size,
        soft_threshold_tokens=source.soft_threshold_tokens,
        hard_threshold_tokens=source.hard_threshold_tokens,
        policy_ref=source.policy_ref,
        policy_snapshot_digest=source.policy_snapshot_digest,
        anchor_diagnostic=source.anchor_diagnostic,
        fallback_reason=source.fallback_reason,
    )


def context_budget_policy_snapshot_digest(policy: ContextBudgetPolicy) -> str:
    """计算 Host context budget policy 的 frozen identity digest。

    :param policy: Host context budget policy。
    :returns: canonical sha256 digest。
    :raises TypeError: ``policy`` 类型非法时抛出。
    """

    if not isinstance(policy, ContextBudgetPolicy):
        raise TypeError("policy must be ContextBudgetPolicy")
    return sha256_digest_json(
        {
            "policy_ref": policy.policy_ref,
            "context_window_size": policy.context_window_size,
            "soft_threshold_context_ratio": policy.soft_threshold_context_ratio,
            "hard_threshold_context_ratio": policy.hard_threshold_context_ratio,
            "max_reactive_compactions_per_run": (
                policy.max_reactive_compactions_per_run
            ),
            "max_compaction_attempts_per_operation": (
                policy.max_compaction_attempts_per_operation
            ),
        }
    )


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
    estimated_input_tokens, digest = estimate_context_input(estimate_input)
    input_budget_tokens = policy.context_window_size
    soft_threshold_tokens = _soft_threshold_tokens(policy)
    hard_threshold_tokens = _hard_threshold_tokens(policy)
    overage_reason = _overage_reason(
        estimated_input_tokens=estimated_input_tokens,
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


def estimate_context_input(
    estimate_input: BudgetEstimateInput,
) -> tuple[int, str]:
    """不读取budget policy地估算完整Runner输入并生成stable digest。

    context window、ratio与threshold属于budget policy，不属于estimator
    identity；把它们从digest中分离后，continuation可以只复用pre-start
    manifest冻结的compatibility atoms完成同一估算。

    :param estimate_input: typed complete input。
    :returns: ``(conservative_input_tokens, estimator_digest)``。
    :raises TypeError: estimate input 类型非法时抛出。
    :raises ValueError: JSON编码或token范围非法时抛出。
    """

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
    if estimated_input_tokens > MAX_CONTEXT_TOKEN_COUNT:
        raise ValueError("estimated_input_tokens exceeds supported range")
    digest = _estimator_digest(
        estimate_input=estimate_input,
        estimated_input_tokens=estimated_input_tokens,
    )
    return (estimated_input_tokens, digest)


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


def _pressure_and_decision(
    *,
    stage: ContextSizingStage,
    predicted_input_tokens: int,
    soft_threshold_tokens: int,
    hard_threshold_tokens: int,
) -> tuple[ContextPressureLevel, ContextBudgetDecision]:
    """从唯一 prediction 与 stage 计算 pressure 和治理 action。

    :param stage: 当前 complete candidate 所处治理阶段。
    :param predicted_input_tokens: 当前预测输入 token。
    :param soft_threshold_tokens: soft threshold。
    :param hard_threshold_tokens: hard threshold。
    :returns: ``(pressure, decision)``。
    :raises AssertionError: stage 或 pressure 闭集未被穷尽时抛出。
    """

    if predicted_input_tokens >= hard_threshold_tokens:
        pressure = ContextPressureLevel.HARD_THRESHOLD_EXCEEDED
    elif predicted_input_tokens >= soft_threshold_tokens:
        pressure = ContextPressureLevel.SOFT_THRESHOLD_EXCEEDED
    else:
        pressure = ContextPressureLevel.NORMAL
    return (pressure, _stage_pressure_action(stage, pressure))


def context_sizing_pressure_and_decision(
    *,
    stage: ContextSizingStage,
    predicted_input_tokens: int,
    soft_threshold_tokens: int,
    hard_threshold_tokens: int,
) -> tuple[ContextPressureLevel, ContextBudgetDecision]:
    """按唯一五阶段矩阵派生 pressure 与 action。

    :param stage: producer 显式选择的 sizing stage。
    :param predicted_input_tokens: 当前 decision basis token 数。
    :param soft_threshold_tokens: frozen soft threshold。
    :param hard_threshold_tokens: frozen hard threshold。
    :returns: 真实 pressure 与 stage-aware action。
    :raises TypeError: stage 或整数类型非法时抛出。
    :raises ValueError: token/threshold 范围或顺序非法时抛出。
    :raises AssertionError: stage/pressure 闭集出现未覆盖成员时抛出。
    """

    if not isinstance(stage, ContextSizingStage):
        raise TypeError("stage must be ContextSizingStage")
    _require_non_negative_int(
        predicted_input_tokens,
        field_name="predicted_input_tokens",
    )
    validate_context_threshold_ordering(
        soft_threshold_tokens=soft_threshold_tokens,
        hard_threshold_tokens=hard_threshold_tokens,
    )
    return _pressure_and_decision(
        stage=stage,
        predicted_input_tokens=predicted_input_tokens,
        soft_threshold_tokens=soft_threshold_tokens,
        hard_threshold_tokens=hard_threshold_tokens,
    )


def validate_context_threshold_ordering(
    *,
    soft_threshold_tokens: int,
    hard_threshold_tokens: int,
) -> None:
    """校验 context soft/hard token threshold 的严格顺序。

    :param soft_threshold_tokens: soft threshold token 数。
    :param hard_threshold_tokens: hard threshold token 数。
    :returns: ``None``。
    :raises TypeError: threshold 不是严格整数时抛出。
    :raises ValueError: threshold 非正或 soft 不小于 hard 时抛出。
    """

    _require_positive_int(
        soft_threshold_tokens,
        field_name="soft_threshold_tokens",
    )
    _require_positive_int(
        hard_threshold_tokens,
        field_name="hard_threshold_tokens",
    )
    if soft_threshold_tokens >= hard_threshold_tokens:
        raise ValueError(
            "soft_threshold_tokens must be less than hard_threshold_tokens"
        )


def context_utilization_basis_points(
    *,
    predicted_input_tokens: int,
    context_window_size: int,
) -> int:
    """按 Host 唯一比例计算未 clamp 的 context utilization basis points。

    :param predicted_input_tokens: 当前 candidate 的预测输入 token 数。
    :param context_window_size: frozen context window token 数。
    :returns: 未 clamp 的整数 basis points。
    :raises TypeError: token 或 window 不是严格整数时抛出。
    :raises ValueError: token 为负或 window 非正时抛出。
    """

    _require_non_negative_int(
        predicted_input_tokens,
        field_name="predicted_input_tokens",
    )
    _require_positive_int(
        context_window_size,
        field_name="context_window_size",
    )
    return (
        predicted_input_tokens
        * _UTILIZATION_BASIS_POINTS_SCALE
        // context_window_size
    )


def _stage_pressure_action(
    stage: ContextSizingStage,
    pressure: ContextPressureLevel,
) -> ContextBudgetDecision:
    """按五阶段、三压力的完整矩阵返回治理动作。

    :param stage: producer 显式给出的 candidate 阶段。
    :param pressure: 唯一阈值函数派生的压力等级。
    :returns: 对应的 allow、compact 或 block 动作。
    :raises AssertionError: stage 或 pressure 闭集出现未覆盖成员时抛出。
    """

    match (stage, pressure):
        case (ContextSizingStage.ORDINARY, ContextPressureLevel.NORMAL):
            return ContextBudgetDecision.ALLOW_DISPATCH
        case (
            ContextSizingStage.ORDINARY,
            ContextPressureLevel.SOFT_THRESHOLD_EXCEEDED,
        ):
            return ContextBudgetDecision.COMPACT_SOFT_THRESHOLD
        case (
            ContextSizingStage.ORDINARY,
            ContextPressureLevel.HARD_THRESHOLD_EXCEEDED,
        ):
            return ContextBudgetDecision.BLOCK_HARD_THRESHOLD
        case (ContextSizingStage.POST_COMPACT, ContextPressureLevel.NORMAL):
            return ContextBudgetDecision.ALLOW_DISPATCH
        case (
            ContextSizingStage.POST_COMPACT,
            ContextPressureLevel.SOFT_THRESHOLD_EXCEEDED,
        ):
            return ContextBudgetDecision.ALLOW_DISPATCH
        case (
            ContextSizingStage.POST_COMPACT,
            ContextPressureLevel.HARD_THRESHOLD_EXCEEDED,
        ):
            return ContextBudgetDecision.BLOCK_HARD_THRESHOLD
        case (
            ContextSizingStage.DISPATCH_FALLBACK,
            ContextPressureLevel.NORMAL,
        ):
            return ContextBudgetDecision.ALLOW_DISPATCH
        case (
            ContextSizingStage.DISPATCH_FALLBACK,
            ContextPressureLevel.SOFT_THRESHOLD_EXCEEDED,
        ):
            return ContextBudgetDecision.ALLOW_DISPATCH
        case (
            ContextSizingStage.DISPATCH_FALLBACK,
            ContextPressureLevel.HARD_THRESHOLD_EXCEEDED,
        ):
            return ContextBudgetDecision.BLOCK_HARD_THRESHOLD
        case (
            ContextSizingStage.REACTIVE_POST_COMPACT,
            ContextPressureLevel.NORMAL,
        ):
            return ContextBudgetDecision.ALLOW_DISPATCH
        case (
            ContextSizingStage.REACTIVE_POST_COMPACT,
            ContextPressureLevel.SOFT_THRESHOLD_EXCEEDED,
        ):
            return ContextBudgetDecision.ALLOW_DISPATCH
        case (
            ContextSizingStage.REACTIVE_POST_COMPACT,
            ContextPressureLevel.HARD_THRESHOLD_EXCEEDED,
        ):
            return ContextBudgetDecision.ALLOW_DISPATCH
        case (ContextSizingStage.CONTINUATION, ContextPressureLevel.NORMAL):
            return ContextBudgetDecision.ALLOW_DISPATCH
        case (
            ContextSizingStage.CONTINUATION,
            ContextPressureLevel.SOFT_THRESHOLD_EXCEEDED,
        ):
            return ContextBudgetDecision.ALLOW_DISPATCH
        case (
            ContextSizingStage.CONTINUATION,
            ContextPressureLevel.HARD_THRESHOLD_EXCEEDED,
        ):
            return ContextBudgetDecision.ALLOW_DISPATCH
        case _:
            raise AssertionError(
                "context sizing stage/pressure matrix is not exhaustive"
            )


def estimate_budget_text_tokens(text: str) -> int:
    """按 Host 统一保守策略估算文本 token 数。

    该估算器对宽字符 / 全角字符按每字符一个 token 计算，对其它字符保留
    既有三字符约一个 token 的近似语义，避免中文、日文、韩文财报文本被
    ``chars / 3`` 严重低估。

    :param text: 待估算文本。
    :returns: 保守 token 估算；空文本返回 ``0``。
    :raises TypeError: ``text`` 不是字符串时抛出。
    """

    if not isinstance(text, str):
        raise TypeError("text must be str")
    cjk_chars = sum(1 for char in text if _is_cjk_token_char(char))
    non_cjk_chars = len(text) - cjk_chars
    non_cjk_tokens = ceil(non_cjk_chars / DEFAULT_ESTIMATOR_CHARS_PER_TOKEN)
    cjk_tokens = ceil(cjk_chars / DEFAULT_ESTIMATOR_CJK_CHARS_PER_TOKEN)
    return cjk_tokens + non_cjk_tokens


def estimate_post_compact_budget(
    *,
    compacted_business_texts: tuple[str, ...],
    current_input_text: str,
) -> int:
    """估算 accepted compact 后 ordinary dispatch 的输入预算。

    :param compacted_business_texts: accepted compact 会投影给 LLM 的业务文本。
    :param current_input_text: 当前用户输入文本。
    :returns: 非负 token 估算。
    :raises TypeError: tuple 或文本类型非法时抛出。
    """

    _require_text_tuple(
        compacted_business_texts,
        field_name="compacted_business_texts",
    )
    if not isinstance(current_input_text, str):
        raise TypeError("current_input_text must be str")
    fragments = (*compacted_business_texts, current_input_text)
    token_count = sum(max(1, estimate_budget_text_tokens(fragment)) for fragment in fragments)
    return token_count + (
        DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS * POST_COMPACT_BASE_MESSAGE_COUNT
    )


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

    return estimate_budget_text_tokens(text)


def _is_cjk_token_char(char: str) -> bool:
    """判断字符是否应按 CJK / 全角保守 token 估算。

    :param char: 单个字符。
    :returns: East Asian Width 为 wide 或 fullwidth 时返回 ``True``。
    :raises: 无主动抛出。
    """

    return unicodedata.east_asian_width(char) in _CJK_EAST_ASIAN_WIDTH_VALUES


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
    estimate_input: BudgetEstimateInput,
    estimated_input_tokens: int,
) -> str:
    """计算 estimator digest。

    :param estimate_input: 估算输入。
    :param estimated_input_tokens: 估算输入 token 数。
    :returns: sha256 digest。
    """

    payload: JsonValue = {
        "estimator_contract": {
            "estimator_id": CONTEXT_ESTIMATOR_ID,
            "estimator_version": CONTEXT_ESTIMATOR_VERSION,
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
            "input_snapshot_digest": estimate_input.input_snapshot_digest,
        },
        "constants": {
            "default_input_soft_threshold_ratio": (
                DEFAULT_INPUT_SOFT_THRESHOLD_RATIO
            ),
            "chars_per_token": DEFAULT_ESTIMATOR_CHARS_PER_TOKEN,
            "cjk_chars_per_token": DEFAULT_ESTIMATOR_CJK_CHARS_PER_TOKEN,
            "json_bytes_per_token": DEFAULT_ESTIMATOR_JSON_BYTES_PER_TOKEN,
            "message_overhead_tokens": DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS,
            "tool_schema_overhead_tokens": (
                DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS
            ),
        },
        "estimate": {
            "estimated_input_tokens": estimated_input_tokens,
        },
    }
    return sha256_digest_json(payload)


def _usage_observation_digest(
    *,
    observation: UsageObservation,
    estimated_input_tokens: int | None,
    prompt_token_delta: int | None,
    status: str,
) -> str:
    """计算 usage observation diagnostic digest。

    :param observation: usage observation。
    :param estimated_input_tokens: 对应估算输入 token 数。
    :param prompt_token_delta: provider prompt token 与估算输入 token 差值。
    :param status: observation 诊断状态。
    :returns: sha256 digest。
    """

    payload: JsonValue = {
        "observation": {
            "session_id": observation.session_id,
            "run_id": observation.run_id,
            "attempt_id": observation.attempt_id,
            "execution_id": observation.execution_id,
            "iteration_id": observation.iteration_id,
            "prompt_tokens": observation.prompt_tokens,
            "completion_tokens": observation.completion_tokens,
            "total_tokens": observation.total_tokens,
            "provider_request_id": observation.provider_request_id,
            "observed_at": observation.observed_at.isoformat(),
        },
        "diagnostic": {
            "estimator_digest": observation.estimator_digest,
            "policy_ref": observation.policy_ref,
            "estimated_input_tokens": estimated_input_tokens,
            "prompt_token_delta": prompt_token_delta,
            "status": status,
        },
    }
    return sha256_digest_json(payload)


def _require_int(value: int, *, field_name: str) -> None:
    """校验严格整数，允许负数。

    :param value: 待校验值。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: ``value`` 不是严格整数时抛出。
    """

    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")


def _is_context_token_count(value: int) -> bool:
    """判断值是否为支持范围内的严格非负token整数。

    :param value: 待判断值。
    :returns: 值是``0..MAX_CONTEXT_TOKEN_COUNT``严格整数时返回``True``。
    :raises Exception: 不主动抛出异常。
    """

    return (
        not isinstance(value, bool)
        and isinstance(value, int)
        and 0 <= value <= MAX_CONTEXT_TOKEN_COUNT
    )


def _require_context_token_count(value: int, *, field_name: str) -> None:
    """校验支持范围内的严格非负token整数。

    :param value: 待校验值。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: 值不是严格整数时抛出。
    :raises ValueError: 值不在支持范围时抛出。
    """

    _require_non_negative_int(value, field_name=field_name)
    if value > MAX_CONTEXT_TOKEN_COUNT:
        raise ValueError(f"{field_name} exceeds supported range")


def _require_sha256_digest(value: str, *, field_name: str) -> None:
    """校验sha256 digest。

    :param value: 待校验文本。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises ValueError: 值不是canonical sha256 digest时抛出。
    """

    if not isinstance(value, str) or not is_sha256_digest(value):
        raise ValueError(f"{field_name} must be sha256 digest")


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


def _require_text_tuple(value: tuple[str, ...], *, field_name: str) -> None:
    """校验文本 tuple。

    :param value: 待校验 tuple。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises TypeError: 字段或元素类型错误时抛出。
    """

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} items must be str")


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
    "CONTEXT_ESTIMATOR_CONTRACT",
    "CONTEXT_ESTIMATOR_ID",
    "CONTEXT_ESTIMATOR_VERSION",
    "ContextBudgetDecision",
    "ContextBudgetOverageReason",
    "ContextAnchorDiagnostic",
    "ContextEstimateMethod",
    "ContextEstimatorContract",
    "ContextPressureLevel",
    "ContextSizingFallbackReason",
    "ContextSizingResult",
    "ContextSizingStage",
    "DEFAULT_ESTIMATOR_CJK_CHARS_PER_TOKEN",
    "DEFAULT_ESTIMATOR_CHARS_PER_TOKEN",
    "DEFAULT_ESTIMATOR_JSON_BYTES_PER_TOKEN",
    "DEFAULT_ESTIMATOR_MESSAGE_OVERHEAD_TOKENS",
    "DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS",
    "DEFAULT_INPUT_SOFT_THRESHOLD_RATIO",
    "POST_COMPACT_BASE_MESSAGE_COUNT",
    "MAX_CONTEXT_TOKEN_COUNT",
    "UsageObservation",
    "UsageObservationDiagnostic",
    "USAGE_OBSERVATION_STATUS_ESTIMATE_UNAVAILABLE",
    "USAGE_OBSERVATION_STATUS_OBSERVED",
    "build_usage_observation_diagnostic",
    "build_conservative_context_sizing_result",
    "build_conservative_context_sizing_result_from_atoms",
    "build_context_sizing_result",
    "build_context_sizing_result_from_atoms",
    "build_frozen_context_sizing_result_from_atoms",
    "context_budget_policy_snapshot_digest",
    "context_sizing_pressure_and_decision",
    "context_utilization_basis_points",
    "decide_context_budget",
    "estimate_budget_text_tokens",
    "estimate_context_budget",
    "estimate_context_input",
    "estimate_post_compact_budget",
    "rebind_frozen_context_sizing_result",
    "validate_context_threshold_ordering",
]
