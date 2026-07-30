"""层中立 runtime assembly helper。

本模块只处理 runtime typed config、scene typed hint、调用方显式 override
之间的中立选择、白名单合并与工具截断默认值补齐。它不构造 Host /
Engine typed object，不导入 Host / Engine / Service / UI / Fins，也不表达
业务 workflow。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Generic, TypeVar

from dayu.contracts import AGENT_FALLBACK_MODES, JsonValue
from dayu.contracts.tool_schema import (
    ToolTruncateSpec,
    ToolTruncationStrategy,
)
from dayu.runtime.config_loader import (
    AgentPolicyConfig,
    ExecutionBaselineConfig,
    ExecutionProfileConfig,
    ModelConfig,
    ModelsConfig,
    RunnerOptionHintConfig,
    ToolTruncationPolicyConfig,
)
from dayu.runtime.numeric import is_positive_finite_number
from dayu.runtime.scene_prepare import (
    SceneAgentPolicyOverride,
    SceneModelHints,
)
from dayu.runtime.tool_truncation import effective_tool_truncate_spec

_SOURCE_RUNTIME_BASE: Final[str] = "runtime_base"
_SOURCE_EXECUTION_PROFILE: Final[str] = "execution_profile"
_SOURCE_SCENE_OVERRIDE: Final[str] = "scene_override"
_SOURCE_RUN_OVERRIDE: Final[str] = "run_override"
_FIELD_MODEL_ID: Final[str] = "model_id"
_FIELD_RUNNER_OPTION_HINT_ID: Final[str] = "runner_option_hint_id"
_FIELD_MAX_ITERATIONS: Final[str] = "max_iterations"
_FIELD_CONTINUATION_MAX_ATTEMPTS: Final[str] = "continuation_max_attempts"
_FIELD_ALLOW_TOOL_CALLS: Final[str] = "allow_tool_calls"
_FIELD_TOOL_EXECUTION_TIMEOUT_SECONDS: Final[str] = (
    "tool_execution_timeout_seconds"
)
_FIELD_FALLBACK_MODE: Final[str] = "fallback_mode"
_FIELD_FALLBACK_PROMPT: Final[str] = "fallback_prompt"
_FIELD_CONTINUATION_PROMPT: Final[str] = "continuation_prompt"
_FIELD_MAX_CONSECUTIVE_FAILED_TOOL_BATCHES: Final[str] = (
    "max_consecutive_failed_tool_batches"
)
_AGENT_POLICY_OVERRIDE_FIELDS: Final[frozenset[str]] = frozenset(
    {
        _FIELD_MAX_ITERATIONS,
        _FIELD_CONTINUATION_MAX_ATTEMPTS,
        _FIELD_ALLOW_TOOL_CALLS,
        _FIELD_TOOL_EXECUTION_TIMEOUT_SECONDS,
        _FIELD_FALLBACK_MODE,
        _FIELD_FALLBACK_PROMPT,
        _FIELD_CONTINUATION_PROMPT,
        _FIELD_MAX_CONSECUTIVE_FAILED_TOOL_BATCHES,
    }
)
_MODEL_HINT_OVERRIDE_FIELDS: Final[frozenset[str]] = frozenset(
    {_FIELD_MODEL_ID, _FIELD_RUNNER_OPTION_HINT_ID}
)
_CONTEXT_WINDOW_CLASS_256K: Final[str] = "256k"
_CONTEXT_WINDOW_1M_MIN_TOKENS: Final[int] = 1_000_000
_PROFILE_COMPATIBILITY_COMPATIBLE: Final[str] = "compatible"
_PROFILE_COMPATIBILITY_CONSERVATIVE: Final[str] = "conservative"

_ValueT = TypeVar("_ValueT")


class RuntimeAssemblyError(ValueError):
    """runtime assembly helper 选择、合并或校验失败时抛出的基础错误。"""


class RuntimeAssemblyFieldError(RuntimeAssemblyError):
    """override 字段未知、缺失或类型非法时抛出的错误。"""


class RuntimeAssemblySelectionError(RuntimeAssemblyError):
    """catalog 选择缺失模型或 runner option hint 时抛出的错误。"""


@dataclass(frozen=True, slots=True)
class ModelFamilyIdentity:
    """resolved 模型家族的层中立 identity。

    :param provider: provider 标识。
    :param provider_model: provider 实际接收的模型名。
    :param endpoint: provider endpoint。
    :param credential_ref: credential 环境变量引用；未配置时为 ``None``。
    """

    provider: str
    provider_model: str
    endpoint: str
    credential_ref: str | None


@dataclass(frozen=True, slots=True)
class ModelRunnerHintOverride:
    """模型与 runner option hint 的显式 override。

    :param model_id: 显式模型 id；``None`` 表示不覆盖下层。
    :param runner_option_hint_id: 显式 runner option hint id；``None`` 表示不覆盖下层。
    """

    model_id: str | None = None
    runner_option_hint_id: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeSelectionDiagnostic:
    """runtime catalog 选择诊断。

    :param selected_model_id: 最终选中的模型 id。
    :param selected_model_source: 模型 id 来源层。
    :param selected_runner_option_hint_id: 最终选中的 runner option hint id。
    :param selected_runner_option_hint_source: runner option hint 来源层。
    """

    selected_model_id: str
    selected_model_source: str
    selected_runner_option_hint_id: str
    selected_runner_option_hint_source: str


@dataclass(frozen=True, slots=True)
class RunnerOptionHintSelection:
    """runtime-neutral runner option hint 选择结果。

    :param model_id: 最终模型 id。
    :param runner_option_hint_id: 最终 runner option hint id。
    :param model: 选中的 runtime 模型配置。
    :param runner_option_hint: 选中的 runtime runner option hint 配置。
    :param diagnostic: 选择来源诊断。
    """

    model_id: str
    runner_option_hint_id: str
    model: ModelConfig
    runner_option_hint: RunnerOptionHintConfig
    diagnostic: RuntimeSelectionDiagnostic


@dataclass(frozen=True, slots=True)
class ExecutionProfileCompatibilityDiagnostic:
    """execution profile 与模型上下文窗口的兼容性诊断。

    :param profile_id: 被校验的 execution profile id。
    :param context_window_class: profile 声明的上下文窗口分档。
    :param min_context_window_tokens: profile 要求的最小上下文窗口 token 数。
    :param selected_model_id: 被校验的模型 id。
    :param model_context_window_tokens: 模型声明的上下文窗口 token 数。
    :param status: 兼容状态；``compatible`` 表示分档匹配，``conservative``
        表示 profile 可运行但相对模型窗口偏保守。
    """

    profile_id: str
    context_window_class: str
    min_context_window_tokens: int
    selected_model_id: str
    model_context_window_tokens: int
    status: str


@dataclass(frozen=True, slots=True)
class AgentPolicyBaseline:
    """Agent policy runtime assembly 基线值。

    该基线来自 ConfigLoader 输出或调用方显式 assembly input，用于补齐
    runtime-neutral policy 合并链路；它不是 Engine contract 默认值，也不是
    LLM-facing prompt 文本真源。

    :param max_iterations: 最大 agent loop 迭代数。
    :param continuation_max_attempts: continuation 最大尝试次数。
    :param allow_tool_calls: 是否允许工具调用。
    :param tool_execution_timeout_seconds: 工具执行握手超时秒数。
    :param fallback_mode: fallback 模式。
    :param fallback_prompt: fallback prompt。
    :param continuation_prompt: continuation prompt。
    :param max_consecutive_failed_tool_batches: 连续失败工具批次阈值。
    """

    max_iterations: int
    continuation_max_attempts: int
    allow_tool_calls: bool
    tool_execution_timeout_seconds: float
    fallback_mode: str
    fallback_prompt: str
    continuation_prompt: str
    max_consecutive_failed_tool_batches: int


@dataclass(frozen=True, slots=True)
class AgentPolicyOverrideConfig:
    """Agent policy typed override。

    所有字段均为可选字段，``None`` 表示该层不覆盖下层。

    :param max_iterations: 最大 agent loop 迭代数。
    :param continuation_max_attempts: continuation 最大尝试次数。
    :param allow_tool_calls: 是否允许工具调用。
    :param tool_execution_timeout_seconds: 工具执行握手超时秒数。
    :param fallback_mode: fallback 模式。
    :param fallback_prompt: fallback prompt。
    :param continuation_prompt: continuation prompt。
    :param max_consecutive_failed_tool_batches: 连续失败工具批次阈值。
    """

    max_iterations: int | None = None
    continuation_max_attempts: int | None = None
    allow_tool_calls: bool | None = None
    tool_execution_timeout_seconds: float | None = None
    fallback_mode: str | None = None
    fallback_prompt: str | None = None
    max_consecutive_failed_tool_batches: int | None = None
    continuation_prompt: str | None = None


@dataclass(frozen=True, slots=True)
class MergedAgentPolicyConfig:
    """合并后的 runtime-neutral AgentPolicy 字段集。

    :param max_iterations: 最大 agent loop 迭代数。
    :param continuation_max_attempts: continuation 最大尝试次数。
    :param allow_tool_calls: 是否允许工具调用。
    :param tool_execution_timeout_seconds: 工具执行握手超时秒数。
    :param fallback_mode: fallback 模式。
    :param fallback_prompt: fallback prompt。
    :param continuation_prompt: continuation prompt。
    :param max_consecutive_failed_tool_batches: 连续失败工具批次阈值。
    :param field_sources: 每个字段最终来源层。
    """

    max_iterations: int
    continuation_max_attempts: int
    allow_tool_calls: bool
    tool_execution_timeout_seconds: float
    fallback_mode: str
    fallback_prompt: str
    continuation_prompt: str
    max_consecutive_failed_tool_batches: int
    field_sources: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ToolTruncationPolicyDefaults:
    """工具截断 policy 默认值投影。

    :param enabled: policy 是否启用；调用方可用于诊断或治理开关。
    :param default_limits_by_strategy: 按截断策略索引的默认 limit。
    :param default_ttl_seconds: 默认 cursor TTL 秒数。
    """

    enabled: bool
    default_limits_by_strategy: Mapping[ToolTruncationStrategy, int]
    default_ttl_seconds: int


@dataclass(frozen=True, slots=True)
class _SelectedValue(Generic[_ValueT]):
    """单字段选择结果。"""

    value: _ValueT
    source: str


def model_family_identity(model: ModelConfig) -> ModelFamilyIdentity:
    """从 resolved typed 模型配置构造唯一家族 identity。

    :param model: ``ConfigLoader`` 已解析的模型配置。
    :returns: provider、provider model、endpoint 与 credential ref 四字段 identity。
    :raises Exception: 不主动抛出异常。
    """

    return ModelFamilyIdentity(
        provider=model.provider,
        provider_model=model.model,
        endpoint=model.endpoint,
        credential_ref=model.api_key_ref,
    )


def parse_model_runner_hint_override(
    fields: Mapping[str, JsonValue], *, source_name: str
) -> ModelRunnerHintOverride:
    """从白名单字段解析模型选择 override。

    :param fields: 调用方提供的 JSON 字段映射。
    :param source_name: 错误消息中的来源名。
    :returns: 强类型模型 / hint override。
    :raises RuntimeAssemblyFieldError: 出现未知字段或字段类型非法时抛出。
    """

    _require_exact_field_names(
        fields,
        allowed=_MODEL_HINT_OVERRIDE_FIELDS,
        context=source_name,
    )
    return ModelRunnerHintOverride(
        model_id=_optional_non_empty_str_field(
            fields,
            field_name=_FIELD_MODEL_ID,
            context=source_name,
        ),
        runner_option_hint_id=_optional_non_empty_str_field(
            fields,
            field_name=_FIELD_RUNNER_OPTION_HINT_ID,
            context=source_name,
        ),
    )


def select_runner_option_hint(
    *,
    models: ModelsConfig,
    execution_baseline: ExecutionBaselineConfig | None,
    scene_model_hints: SceneModelHints | None,
    run_override: ModelRunnerHintOverride | None,
    base_policy: ExecutionBaselineConfig | None,
) -> RunnerOptionHintSelection:
    """按优先级选择 runtime-neutral 模型与 runner option hint。

    优先级固定为 ``run_override > scene_model_hints >
    execution_baseline > base_policy``，并按字段独立合并。

    :param models: 模型 catalog typed view。
    :param execution_baseline: execution profile 的基线选择。
    :param scene_model_hints: ScenePrepare 输出的 scene 模型 hints。
    :param run_override: UI / Run 显式 override。
    :param base_policy: runtime assembly 基线选择。
    :returns: 选中的模型、runner option hint 与来源诊断。
    :raises RuntimeAssemblySelectionError: 模型或 hint 缺失时抛出。
    """

    model_selection = _select_required_text(
        run_value=None if run_override is None else run_override.model_id,
        scene_value=(
            None if scene_model_hints is None else scene_model_hints.default_model_id
        ),
        baseline_value=(
            None if execution_baseline is None else execution_baseline.model_id
        ),
        default_value=None if base_policy is None else base_policy.model_id,
        field_name=_FIELD_MODEL_ID,
    )
    hint_selection = _select_required_text(
        run_value=(
            None if run_override is None else run_override.runner_option_hint_id
        ),
        scene_value=(
            None
            if scene_model_hints is None
            else scene_model_hints.runner_option_hint_id
        ),
        baseline_value=(
            None
            if execution_baseline is None
            else execution_baseline.runner_option_hint_id
        ),
        default_value=(
            None if base_policy is None else base_policy.runner_option_hint_id
        ),
        field_name=_FIELD_RUNNER_OPTION_HINT_ID,
    )
    model = models.models.get(model_selection.value)
    if model is None:
        raise RuntimeAssemblySelectionError(
            f"model not found: {model_selection.value}"
        )
    hint = model.runtime_hints.runner_option_hints.get(hint_selection.value)
    if hint is None:
        raise RuntimeAssemblySelectionError(
            "runner option hint not found: "
            f"model={model_selection.value}, hint={hint_selection.value}"
        )
    return RunnerOptionHintSelection(
        model_id=model_selection.value,
        runner_option_hint_id=hint_selection.value,
        model=model,
        runner_option_hint=hint,
        diagnostic=RuntimeSelectionDiagnostic(
            selected_model_id=model_selection.value,
            selected_model_source=model_selection.source,
            selected_runner_option_hint_id=hint_selection.value,
            selected_runner_option_hint_source=hint_selection.source,
        ),
    )


def validate_execution_profile_context_window(
    *, profile: ExecutionProfileConfig, model: ModelConfig
) -> ExecutionProfileCompatibilityDiagnostic:
    """校验 execution profile 与模型上下文窗口是否兼容。

    该 helper 只做 fail-fast 校验和诊断，不读取默认 profile catalog，不返回
    替代 profile id，也不会根据模型窗口自动切换 profile。

    :param profile: Service 显式选择后的 execution profile。
    :param model: Service 显式选择后的 effective model。
    :returns: 兼容性诊断。
    :raises RuntimeAssemblySelectionError: 模型上下文窗口小于 profile 最低要求时
        抛出。
    """

    if model.context_window_tokens < profile.min_context_window_tokens:
        raise RuntimeAssemblySelectionError(
            "execution profile requires larger context window: "
            f"profile={profile.execution_profile_id}, "
            f"profile_min_context_window_tokens={profile.min_context_window_tokens}, "
            f"model={model.model_id}, "
            f"model_context_window_tokens={model.context_window_tokens}"
        )
    return ExecutionProfileCompatibilityDiagnostic(
        profile_id=profile.execution_profile_id,
        context_window_class=profile.context_window_class,
        min_context_window_tokens=profile.min_context_window_tokens,
        selected_model_id=model.model_id,
        model_context_window_tokens=model.context_window_tokens,
        status=_profile_context_window_status(
            profile_class=profile.context_window_class,
            model_context_window_tokens=model.context_window_tokens,
        ),
    )


def parse_agent_policy_override_config(
    fields: Mapping[str, JsonValue], *, source_name: str
) -> AgentPolicyOverrideConfig:
    """从白名单字段解析 Agent policy typed override。

    :param fields: 调用方提供的 JSON 字段映射。
    :param source_name: 错误消息中的来源名。
    :returns: 强类型 Agent policy override。
    :raises RuntimeAssemblyFieldError: 出现未知字段、非法类型或非法枚举时抛出。
    """

    _require_exact_field_names(
        fields,
        allowed=_AGENT_POLICY_OVERRIDE_FIELDS,
        context=source_name,
    )
    fallback_mode = _optional_non_empty_str_field(
        fields,
        field_name=_FIELD_FALLBACK_MODE,
        context=source_name,
    )
    if fallback_mode is not None and fallback_mode not in AGENT_FALLBACK_MODES:
        raise RuntimeAssemblyFieldError(
            f"{source_name}.{_FIELD_FALLBACK_MODE} has unsupported value: "
            f"{fallback_mode}"
        )
    return AgentPolicyOverrideConfig(
        max_iterations=_optional_positive_int_field(
            fields,
            field_name=_FIELD_MAX_ITERATIONS,
            context=source_name,
        ),
        continuation_max_attempts=_optional_non_negative_int_field(
            fields,
            field_name=_FIELD_CONTINUATION_MAX_ATTEMPTS,
            context=source_name,
        ),
        allow_tool_calls=_optional_bool_field(
            fields,
            field_name=_FIELD_ALLOW_TOOL_CALLS,
            context=source_name,
        ),
        tool_execution_timeout_seconds=_optional_positive_float_field(
            fields,
            field_name=_FIELD_TOOL_EXECUTION_TIMEOUT_SECONDS,
            context=source_name,
        ),
        fallback_mode=fallback_mode,
        fallback_prompt=_optional_text_field(
            fields,
            field_name=_FIELD_FALLBACK_PROMPT,
            context=source_name,
        ),
        continuation_prompt=_optional_text_field(
            fields,
            field_name=_FIELD_CONTINUATION_PROMPT,
            context=source_name,
        ),
        max_consecutive_failed_tool_batches=_optional_positive_int_field(
            fields,
            field_name=_FIELD_MAX_CONSECUTIVE_FAILED_TOOL_BATCHES,
            context=source_name,
        ),
    )


def merge_agent_policy_config(
    *,
    base_policy: AgentPolicyBaseline,
    execution_profile: AgentPolicyConfig | None,
    scene_override: SceneAgentPolicyOverride | None,
    run_override: AgentPolicyOverrideConfig | None,
) -> MergedAgentPolicyConfig:
    """按固定优先级合并 Agent policy 字段。

    优先级固定为 ``run_override > scene_override > execution_profile >
    base_policy``，每层只处理 Agent policy 白名单字段，返回仍是
    runtime-neutral 字段集。

    :param base_policy: runtime assembly 基线完整字段集。
    :param execution_profile: execution profile baseline。
    :param scene_override: ScenePrepare 输出的 typed override。
    :param run_override: UI / Run 显式 typed override。
    :returns: 合并后的 Agent policy 字段与来源诊断。
    :raises RuntimeAssemblyFieldError: 默认值或 baseline 枚举非法时抛出。
    """

    _validate_fallback_mode(
        base_policy.fallback_mode,
        context=f"{_SOURCE_RUNTIME_BASE}.{_FIELD_FALLBACK_MODE}",
    )
    if execution_profile is not None:
        _validate_fallback_mode(
            execution_profile.fallback_mode,
            context=f"{_SOURCE_EXECUTION_PROFILE}.{_FIELD_FALLBACK_MODE}",
        )
    max_iterations = _select_value(
        run_value=None if run_override is None else run_override.max_iterations,
        scene_value=None if scene_override is None else scene_override.max_iterations,
        baseline_value=(
            None if execution_profile is None else execution_profile.max_iterations
        ),
        default_value=base_policy.max_iterations,
    )
    continuation_max_attempts = _select_value(
        run_value=(
            None
            if run_override is None
            else run_override.continuation_max_attempts
        ),
        scene_value=(
            None
            if scene_override is None
            else scene_override.continuation_max_attempts
        ),
        baseline_value=(
            None
            if execution_profile is None
            else execution_profile.continuation_max_attempts
        ),
        default_value=base_policy.continuation_max_attempts,
    )
    allow_tool_calls = _select_value(
        run_value=None if run_override is None else run_override.allow_tool_calls,
        scene_value=None if scene_override is None else scene_override.allow_tool_calls,
        baseline_value=(
            None if execution_profile is None else execution_profile.allow_tool_calls
        ),
        default_value=base_policy.allow_tool_calls,
    )
    tool_execution_timeout_seconds = _select_value(
        run_value=(
            None
            if run_override is None
            else run_override.tool_execution_timeout_seconds
        ),
        scene_value=(
            None
            if scene_override is None
            else scene_override.tool_execution_timeout_seconds
        ),
        baseline_value=(
            None
            if execution_profile is None
            else execution_profile.tool_execution_timeout_seconds
        ),
        default_value=base_policy.tool_execution_timeout_seconds,
    )
    fallback_mode = _select_value(
        run_value=None if run_override is None else run_override.fallback_mode,
        scene_value=_scene_fallback_mode_value(scene_override),
        baseline_value=(
            None if execution_profile is None else execution_profile.fallback_mode
        ),
        default_value=base_policy.fallback_mode,
    )
    _validate_fallback_mode(
        fallback_mode.value,
        context=f"{fallback_mode.source}.{_FIELD_FALLBACK_MODE}",
    )
    fallback_prompt = _select_value(
        run_value=None if run_override is None else run_override.fallback_prompt,
        scene_value=None if scene_override is None else scene_override.fallback_prompt,
        baseline_value=(
            None if execution_profile is None else execution_profile.fallback_prompt
        ),
        default_value=base_policy.fallback_prompt,
    )
    continuation_prompt = _select_value(
        run_value=None if run_override is None else run_override.continuation_prompt,
        scene_value=(
            None if scene_override is None else scene_override.continuation_prompt
        ),
        baseline_value=(
            None
            if execution_profile is None
            else execution_profile.continuation_prompt
        ),
        default_value=base_policy.continuation_prompt,
    )
    max_consecutive_failed_tool_batches = _select_value(
        run_value=(
            None
            if run_override is None
            else run_override.max_consecutive_failed_tool_batches
        ),
        scene_value=(
            None
            if scene_override is None
            else scene_override.max_consecutive_failed_tool_batches
        ),
        baseline_value=(
            None
            if execution_profile is None
            else execution_profile.max_consecutive_failed_tool_batches
        ),
        default_value=base_policy.max_consecutive_failed_tool_batches,
    )
    return MergedAgentPolicyConfig(
        max_iterations=max_iterations.value,
        continuation_max_attempts=continuation_max_attempts.value,
        allow_tool_calls=allow_tool_calls.value,
        tool_execution_timeout_seconds=tool_execution_timeout_seconds.value,
        fallback_mode=fallback_mode.value,
        fallback_prompt=fallback_prompt.value,
        continuation_prompt=continuation_prompt.value,
        max_consecutive_failed_tool_batches=(
            max_consecutive_failed_tool_batches.value
        ),
        field_sources=MappingProxyType(
            {
                _FIELD_MAX_ITERATIONS: max_iterations.source,
                _FIELD_CONTINUATION_MAX_ATTEMPTS: continuation_max_attempts.source,
                _FIELD_ALLOW_TOOL_CALLS: allow_tool_calls.source,
                _FIELD_TOOL_EXECUTION_TIMEOUT_SECONDS: (
                    tool_execution_timeout_seconds.source
                ),
                _FIELD_FALLBACK_MODE: fallback_mode.source,
                _FIELD_FALLBACK_PROMPT: fallback_prompt.source,
                _FIELD_CONTINUATION_PROMPT: continuation_prompt.source,
                _FIELD_MAX_CONSECUTIVE_FAILED_TOOL_BATCHES: (
                    max_consecutive_failed_tool_batches.source
                ),
            }
        ),
    )


def _profile_context_window_status(
    *, profile_class: str, model_context_window_tokens: int
) -> str:
    """计算 profile 与模型窗口的兼容状态。

    :param profile_class: profile 上下文窗口分档。
    :param model_context_window_tokens: 模型上下文窗口 token 数。
    :returns: 兼容状态字符串。
    :raises Exception: 不主动抛出异常。
    """

    if (
        profile_class == _CONTEXT_WINDOW_CLASS_256K
        and model_context_window_tokens >= _CONTEXT_WINDOW_1M_MIN_TOKENS
    ):
        return _PROFILE_COMPATIBILITY_CONSERVATIVE
    return _PROFILE_COMPATIBILITY_COMPATIBLE


def tool_truncation_policy_defaults(
    policy: ToolTruncationPolicyConfig,
) -> ToolTruncationPolicyDefaults:
    """从 runtime config policy 投影截断默认值。

    :param policy: runtime config 中的工具截断 policy。
    :returns: 按 ``ToolTruncationStrategy`` 索引的默认 limit 与 TTL。
    :raises RuntimeAssemblyFieldError: TTL 不是整数秒或默认值非法时抛出。
    """

    return ToolTruncationPolicyDefaults(
        enabled=policy.enabled,
        default_limits_by_strategy={
            ToolTruncationStrategy.TEXT_CHARS: policy.default_limits.text_chars.max_chars,
            ToolTruncationStrategy.TEXT_LINES: policy.default_limits.text_lines.max_lines,
            ToolTruncationStrategy.LIST_ITEMS: policy.default_limits.list_items.max_items,
            ToolTruncationStrategy.BINARY_BYTES: (
                policy.default_limits.binary_bytes.max_bytes
            ),
        },
        default_ttl_seconds=_ttl_seconds_as_int(
            policy.default_cursor_ttl_seconds
        ),
    )


def effective_tool_truncate_spec_from_policy(
    declaration: ToolTruncateSpec,
    *,
    policy: ToolTruncationPolicyConfig,
) -> ToolTruncateSpec:
    """按截断 policy 默认值补齐工具声明。

    :param declaration: 工具声明的截断 spec。
    :param policy: runtime config 中的截断 policy。
    :returns: 补齐后的 effective ``ToolTruncateSpec``。
    :raises RuntimeAssemblyFieldError: policy 默认值非法时抛出。
    :raises TypeError: declaration 类型非法时由底层 helper 抛出。
    :raises ValueError: declaration 与默认值组合非法时由底层 helper 抛出。
    """

    defaults = tool_truncation_policy_defaults(policy)
    return effective_tool_truncate_spec(
        declaration,
        default_limits_by_strategy=defaults.default_limits_by_strategy,
        default_ttl_seconds=defaults.default_ttl_seconds,
    )


def _select_required_text(
    *,
    run_value: str | None,
    scene_value: str | None,
    baseline_value: str | None,
    default_value: str | None,
    field_name: str,
) -> _SelectedValue[str]:
    """按优先级选择必填文本字段。

    :param run_value: run 层字段值。
    :param scene_value: scene 层字段值。
    :param baseline_value: execution profile 层字段值。
    :param default_value: runtime assembly 基线字段值。
    :param field_name: 字段名。
    :returns: 选中值与来源。
    :raises RuntimeAssemblySelectionError: 所有层均未提供值时抛出。
    """

    selection = _select_value(
        run_value=run_value,
        scene_value=scene_value,
        baseline_value=baseline_value,
        default_value=default_value,
    )
    if selection.value is None:
        raise RuntimeAssemblySelectionError(f"{field_name} is required")
    return _SelectedValue(value=selection.value, source=selection.source)


def _select_value(
    *,
    run_value: _ValueT | None,
    scene_value: _ValueT | None,
    baseline_value: _ValueT | None,
    default_value: _ValueT,
) -> _SelectedValue[_ValueT]:
    """按固定四层优先级选择单字段值。

    :param run_value: run 层字段值。
    :param scene_value: scene 层字段值。
    :param baseline_value: execution profile 层字段值。
    :param default_value: runtime assembly 基线字段值。
    :returns: 选中值与来源。
    """

    if run_value is not None:
        return _SelectedValue(value=run_value, source=_SOURCE_RUN_OVERRIDE)
    if scene_value is not None:
        return _SelectedValue(value=scene_value, source=_SOURCE_SCENE_OVERRIDE)
    if baseline_value is not None:
        return _SelectedValue(value=baseline_value, source=_SOURCE_EXECUTION_PROFILE)
    return _SelectedValue(value=default_value, source=_SOURCE_RUNTIME_BASE)


def _scene_fallback_mode_value(
    scene_override: SceneAgentPolicyOverride | None,
) -> str | None:
    """读取 scene fallback mode 的字符串值。

    :param scene_override: scene typed override。
    :returns: fallback mode 字符串或 ``None``。
    """

    if scene_override is None or scene_override.fallback_mode is None:
        return None
    return scene_override.fallback_mode.value


def _require_exact_field_names(
    fields: Mapping[str, JsonValue], *, allowed: frozenset[str], context: str
) -> None:
    """校验字段名只来自白名单。

    :param fields: 待校验字段映射。
    :param allowed: 允许字段集合。
    :param context: 错误消息上下文。
    :returns: ``None``。
    :raises RuntimeAssemblyFieldError: 出现未知字段时抛出。
    """

    unknown = set(fields) - allowed
    if unknown:
        raise RuntimeAssemblyFieldError(
            f"{context} has unknown fields: {sorted(unknown)}"
        )


def _optional_non_empty_str_field(
    fields: Mapping[str, JsonValue], *, field_name: str, context: str
) -> str | None:
    """读取可选非空字符串字段。

    :param fields: 字段映射。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字段值；缺失或 ``null`` 时返回 ``None``。
    :raises RuntimeAssemblyFieldError: 字段类型非法或为空时抛出。
    """

    value = _optional_text_field(fields, field_name=field_name, context=context)
    if value is not None and not value.strip():
        raise RuntimeAssemblyFieldError(f"{context}.{field_name} must be non-empty")
    return value


def _optional_text_field(
    fields: Mapping[str, JsonValue], *, field_name: str, context: str
) -> str | None:
    """读取可选字符串字段。

    :param fields: 字段映射。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字段值；缺失或 ``null`` 时返回 ``None``。
    :raises RuntimeAssemblyFieldError: 字段不是字符串时抛出。
    """

    if field_name not in fields or fields[field_name] is None:
        return None
    value = fields[field_name]
    if not isinstance(value, str):
        raise RuntimeAssemblyFieldError(f"{context}.{field_name} must be a string")
    return value


def _optional_bool_field(
    fields: Mapping[str, JsonValue], *, field_name: str, context: str
) -> bool | None:
    """读取可选 bool 字段。

    :param fields: 字段映射。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字段值；缺失或 ``null`` 时返回 ``None``。
    :raises RuntimeAssemblyFieldError: 字段不是 bool 时抛出。
    """

    if field_name not in fields or fields[field_name] is None:
        return None
    value = fields[field_name]
    if not isinstance(value, bool):
        raise RuntimeAssemblyFieldError(f"{context}.{field_name} must be a boolean")
    return value


def _optional_positive_int_field(
    fields: Mapping[str, JsonValue], *, field_name: str, context: str
) -> int | None:
    """读取可选正整数字段。

    :param fields: 字段映射。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字段值；缺失或 ``null`` 时返回 ``None``。
    :raises RuntimeAssemblyFieldError: 字段不是正整数时抛出。
    """

    value = _optional_int_field(fields, field_name=field_name, context=context)
    if value is not None and value < 1:
        raise RuntimeAssemblyFieldError(f"{context}.{field_name} must be positive")
    return value


def _optional_non_negative_int_field(
    fields: Mapping[str, JsonValue], *, field_name: str, context: str
) -> int | None:
    """读取可选非负整数字段。

    :param fields: 字段映射。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字段值；缺失或 ``null`` 时返回 ``None``。
    :raises RuntimeAssemblyFieldError: 字段不是非负整数时抛出。
    """

    value = _optional_int_field(fields, field_name=field_name, context=context)
    if value is not None and value < 0:
        raise RuntimeAssemblyFieldError(
            f"{context}.{field_name} must be non-negative"
        )
    return value


def _optional_int_field(
    fields: Mapping[str, JsonValue], *, field_name: str, context: str
) -> int | None:
    """读取可选整数字段。

    :param fields: 字段映射。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字段值；缺失或 ``null`` 时返回 ``None``。
    :raises RuntimeAssemblyFieldError: 字段不是整数时抛出。
    """

    if field_name not in fields or fields[field_name] is None:
        return None
    value = fields[field_name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeAssemblyFieldError(f"{context}.{field_name} must be an integer")
    return value


def _optional_positive_float_field(
    fields: Mapping[str, JsonValue], *, field_name: str, context: str
) -> float | None:
    """读取可选正数值字段。

    :param fields: 字段映射。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字段值；缺失或 ``null`` 时返回 ``None``。
    :raises RuntimeAssemblyFieldError: 字段不是正数值时抛出。
    """

    if field_name not in fields or fields[field_name] is None:
        return None
    value = fields[field_name]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeAssemblyFieldError(f"{context}.{field_name} must be a number")
    if not is_positive_finite_number(value):
        raise RuntimeAssemblyFieldError(f"{context}.{field_name} must be > 0")
    return float(value)


def _validate_fallback_mode(value: str, *, context: str) -> None:
    """校验 fallback mode 枚举值。

    :param value: fallback mode 字符串。
    :param context: 错误消息上下文。
    :returns: ``None``。
    :raises RuntimeAssemblyFieldError: 值不属于支持集合时抛出。
    """

    if value not in AGENT_FALLBACK_MODES:
        raise RuntimeAssemblyFieldError(f"{context} has unsupported value: {value}")


def _ttl_seconds_as_int(value: float) -> int:
    """把 policy TTL 秒数转换为 ToolTruncateSpec 需要的整数秒。

    :param value: policy 默认 TTL 秒数。
    :returns: 整数 TTL 秒数。
    :raises RuntimeAssemblyFieldError: TTL 非有限正整数秒时抛出。
    """

    if not is_positive_finite_number(value) or not value.is_integer():
        raise RuntimeAssemblyFieldError(
            "tool_truncation_policy.default_cursor_ttl_seconds "
            "must be positive integer seconds"
        )
    return int(value)


__all__ = [
    "AgentPolicyBaseline",
    "AgentPolicyOverrideConfig",
    "ExecutionProfileCompatibilityDiagnostic",
    "MergedAgentPolicyConfig",
    "ModelFamilyIdentity",
    "ModelRunnerHintOverride",
    "RunnerOptionHintSelection",
    "RuntimeAssemblyError",
    "RuntimeAssemblyFieldError",
    "RuntimeAssemblySelectionError",
    "RuntimeSelectionDiagnostic",
    "ToolTruncationPolicyDefaults",
    "effective_tool_truncate_spec_from_policy",
    "merge_agent_policy_config",
    "model_family_identity",
    "parse_agent_policy_override_config",
    "parse_model_runner_hint_override",
    "select_runner_option_hint",
    "tool_truncation_policy_defaults",
    "validate_execution_profile_context_window",
]
