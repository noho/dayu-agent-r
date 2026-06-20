"""层中立运行时配置加载器。

本模块只负责读取 ``dayu/config`` 默认配置与调用方显式传入的 workspace
配置目录，执行按文件类型的 overlay、单继承解析与强类型校验，然后输出
层中立 typed config view。它不构造 Host，不创建 provider client，不解释
scene manifest，不读取财报仓储，也不 import 业务层。
"""

from __future__ import annotations

import json
from collections.abc import Container, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, TypeAlias, cast

from dayu.contracts import JsonValue, ToolBundleSourceKind
from dayu.runtime._agent_policy_constants import AGENT_FALLBACK_MODES

_MODELS_FILE: Final[str] = "models.json"
_EXECUTION_PROFILES_FILE: Final[str] = "execution_profiles.json"
_HOST_RUNTIME_FILE: Final[str] = "host_runtime.json"
_RUNTIME_LANES_FILE: Final[str] = "runtime_lanes.json"
_TOOL_DISCOVERY_FILE: Final[str] = "tool_discovery.json"
_LEGACY_CONFIG_FILES: Final[frozenset[str]] = frozenset(
    {"llm_models.json", "run.json"}
)
_CONFIG_FILE_NAMES: Final[tuple[str, ...]] = (
    _MODELS_FILE,
    _EXECUTION_PROFILES_FILE,
    _HOST_RUNTIME_FILE,
    _RUNTIME_LANES_FILE,
    _TOOL_DISCOVERY_FILE,
)
_EXTENDS_FIELD: Final[str] = "extends"
_IMPORT_PATH_FIELD: Final[str] = "import_path"
_ENTRY_POINT_FIELD: Final[str] = "entry_point"
_CONFIG_ROOT: Final[Path] = Path(__file__).resolve().parents[1] / "config"
_DEFAULT_FALLBACK_PROMPT: Final[str] = (
    "请基于已获得的信息直接回答问题。信息不足时必须说明不确定性，不得编造。"
)
_FORBIDDEN_RECORD_ID_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "runtime_id",
        "host_runtime_id",
        "model_id",
        "profile_id",
        "execution_profile_id",
        "provider_id",
    }
)
_EXECUTION_PROFILE_CONTEXT_WINDOW_CLASSES: Final[frozenset[str]] = frozenset(
    {"256k", "1m"}
)
_EXECUTION_PROFILE_MIN_CONTEXT_WINDOW_TOKENS_BY_CLASS: Final[Mapping[str, int]] = {
    "256k": 262_144,
    "1m": 1_000_000,
}
_TOOL_DISCOVERY_SOURCE_KINDS: Final[frozenset[ToolBundleSourceKind]] = frozenset(
    {
        ToolBundleSourceKind.EXPLICIT_PROVIDER,
        ToolBundleSourceKind.CONFIG_BINDING,
        ToolBundleSourceKind.PACKAGE_ENTRYPOINT,
    }
)
_TOOL_DUPLICATE_GOVERNANCE_DECISIONS: Final[frozenset[str]] = frozenset(
    {
        "allow",
        "reuse",
        "hint",
        "require_justification",
        "hard_stop",
    }
)

JsonObject: TypeAlias = Mapping[str, JsonValue]
"""JSON object 的只读映射类型。"""


class ConfigLoadError(ValueError):
    """配置加载、合并或校验失败时抛出的基础错误。"""


class ConfigFileNotFoundError(ConfigLoadError):
    """必需配置文件不存在时抛出的错误。"""


class ConfigShapeError(ConfigLoadError):
    """JSON 顶层或记录结构不符合 schema 时抛出的错误。"""


class ConfigExtendsError(ConfigLoadError):
    """配置 ``extends`` 继承关系非法时抛出的错误。"""


class ConfigFieldError(ConfigLoadError):
    """字段缺失、字段类型非法或字段引用不存在时抛出的错误。"""


class RunnerKind(StrEnum):
    """Runner 配置类别。"""

    OPENAI_COMPATIBLE = "openai_compatible"


@dataclass(frozen=True, slots=True)
class RunnerOptionHintConfig:
    """模型内 semantic RunnerCallOptions hint。

    :param temperature: Runner 调用 temperature。
    :param top_p: Runner 调用 top-p。
    :param stream: 是否请求流式输出。
    """

    temperature: float
    top_p: float
    stream: bool


@dataclass(frozen=True, slots=True)
class ModelRuntimeHintsConfig:
    """模型运行期 hints。

    :param runner_option_hints: 按 semantic hint id 索引的 RunnerCallOptions
        配置片段。
    """

    runner_option_hints: Mapping[str, RunnerOptionHintConfig]


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """模型目录中的单个模型配置。

    :param model_id: 模型配置稳定标识，由 map key 注入。
    :param runner_kind: Runner 类别。
    :param provider: provider 标识。
    :param model: provider 模型名。
    :param endpoint: provider endpoint URL。
    :param api_key_ref: API key 引用；``None`` 表示未配置。
    :param headers: provider 请求 headers，按配置原样保留。
    :param supports_tool_calling: 是否支持工具调用。
    :param supports_stream: 是否支持流式输出。
    :param supports_stream_usage: 是否支持流式 usage。
    :param default_timeout_seconds: 默认请求超时秒数。
    :param max_retries: 默认最大重试次数。
    :param sse_idle_timeout_seconds: SSE 空闲超时秒数。
    :param sse_heartbeat_seconds: SSE 空闲诊断 heartbeat 秒数。
    :param provider_request_extension: provider 私有请求扩展，按 JSON 原样保留。
    :param context_window_tokens: 模型上下文窗口 token 数。
    :param runtime_hints: 模型内运行期 hints。
    """

    model_id: str
    runner_kind: RunnerKind
    provider: str
    model: str
    endpoint: str
    api_key_ref: str | None
    headers: Mapping[str, str]
    supports_tool_calling: bool
    supports_stream: bool
    supports_stream_usage: bool
    default_timeout_seconds: float
    max_retries: int
    sse_idle_timeout_seconds: float
    sse_heartbeat_seconds: float
    provider_request_extension: JsonValue
    context_window_tokens: int
    runtime_hints: ModelRuntimeHintsConfig


@dataclass(frozen=True, slots=True)
class ModelsConfig:
    """模型目录配置视图。

    :param models: 按 ``model_id`` 索引的模型配置。
    """

    models: Mapping[str, ModelConfig]


@dataclass(frozen=True, slots=True)
class ExecutionBaselineConfig:
    """普通或 compactor 执行基线。

    :param model_id: 默认模型 id。
    :param runner_option_hint_id: 模型内 semantic runner option hint id。
    """

    model_id: str
    runner_option_hint_id: str


@dataclass(frozen=True, slots=True)
class CompactorBaselineConfig:
    """Host-owned compactor 执行基线。

    :param model_id: compactor 模型 id。
    :param scene_id: compactor scene id。
    :param runner_option_hint_id: compactor runner option hint id。
    :param user_prompt_template_path: compactor user prompt template 相对
        prompt asset root 的路径。
    :param artifact_root: compact artifact 根目录。
    """

    model_id: str
    scene_id: str
    runner_option_hint_id: str
    user_prompt_template_path: str
    artifact_root: str


@dataclass(frozen=True, slots=True)
class ContextBudgetConfig:
    """上下文预算配置。

    :param soft_threshold_context_ratio: soft threshold 占上下文比例。
    :param hard_threshold_context_ratio: hard threshold 占上下文比例。
    :param max_proactive_compactions_per_run: 单个 Run proactive compact 上限。
    :param max_reactive_compactions_per_run: 单个 Run reactive compact 上限。
    :param max_compaction_attempts_per_operation: 单次 compact operation 尝试上限。
    :param policy_ref: policy snapshot / composition ref。
    """

    soft_threshold_context_ratio: float
    hard_threshold_context_ratio: float
    max_proactive_compactions_per_run: int
    max_reactive_compactions_per_run: int
    max_compaction_attempts_per_operation: int
    policy_ref: str


@dataclass(frozen=True, slots=True)
class MemoryProjectionConfig:
    """Conversation memory projection 配置。

    :param context_window_size: policy 上下文窗口。
    :param selected_recent_window_item_cap: selected recent window item 上限。
    :param selected_recent_window_char_cap: selected recent window 字符上限。
    :param selected_recent_window_turn_floor: selected recent window 近轮保底。
    :param fallback_selected_recent_window_item_cap: fallback selected recent window item 上限。
    :param fallback_selected_recent_window_char_cap: fallback selected recent window 字符上限。
    :param evidence_fact_item_cap: evidence-backed fact item 上限。
    :param evidence_fact_char_cap: evidence-backed fact 字符上限。
    :param evidence_fact_floor: evidence-backed fact 保底数量。
    :param session_summary_char_cap: session summary 字符上限。
    :param answer_anchor_item_cap: answer anchor item 上限。
    :param answer_anchor_char_cap: answer anchor 字符上限。
    :param forward_intent_item_cap: forward intent item 上限。
    :param forward_intent_char_cap: forward intent 字符上限。
    :param reference_continuity_item_cap: reference continuity item 上限。
    :param reference_continuity_char_cap: reference continuity 字符上限。
    :param reference_continuity_item_floor: reference continuity item 保底数量。
    :param max_lag_events_for_inline_delta: inline delta 最大滞后事件数。
    :param max_delta_repair_events: repair delta 最大事件数。
    :param policy_ref: policy ref。
    """

    context_window_size: int
    selected_recent_window_item_cap: int
    selected_recent_window_char_cap: int
    selected_recent_window_turn_floor: int
    fallback_selected_recent_window_item_cap: int
    fallback_selected_recent_window_char_cap: int
    evidence_fact_item_cap: int
    evidence_fact_char_cap: int
    evidence_fact_floor: int
    session_summary_char_cap: int
    answer_anchor_item_cap: int
    answer_anchor_char_cap: int
    forward_intent_item_cap: int
    forward_intent_char_cap: int
    reference_continuity_item_cap: int
    reference_continuity_char_cap: int
    reference_continuity_item_floor: int
    max_lag_events_for_inline_delta: int
    max_delta_repair_events: int
    policy_ref: str


@dataclass(frozen=True, slots=True)
class TextCharsLimitConfig:
    """文本字符截断默认 limit。

    :param max_chars: 最大字符数。
    """

    max_chars: int


@dataclass(frozen=True, slots=True)
class TextLinesLimitConfig:
    """文本行截断默认 limit。

    :param max_lines: 最大行数。
    """

    max_lines: int


@dataclass(frozen=True, slots=True)
class ListItemsLimitConfig:
    """列表条目截断默认 limit。

    :param max_items: 最大条目数。
    """

    max_items: int


@dataclass(frozen=True, slots=True)
class BinaryBytesLimitConfig:
    """二进制字节截断默认 limit。

    :param max_bytes: 最大字节数。
    """

    max_bytes: int


@dataclass(frozen=True, slots=True)
class ToolTruncationDefaultLimitsConfig:
    """工具截断默认 limits。

    :param text_chars: 文本字符 limit。
    :param text_lines: 文本行 limit。
    :param list_items: 列表条目 limit。
    :param binary_bytes: 二进制字节 limit。
    """

    text_chars: TextCharsLimitConfig
    text_lines: TextLinesLimitConfig
    list_items: ListItemsLimitConfig
    binary_bytes: BinaryBytesLimitConfig


@dataclass(frozen=True, slots=True)
class ToolTruncationPolicyConfig:
    """工具截断治理配置。

    :param enabled: 是否启用截断治理。
    :param default_cursor_ttl_seconds: 默认 fetch-more cursor TTL 秒数。
    :param default_limits: 各截断策略默认 limit。
    """

    enabled: bool
    default_cursor_ttl_seconds: float
    default_limits: ToolTruncationDefaultLimitsConfig


@dataclass(frozen=True, slots=True)
class ExecutionProfileConfig:
    """单个 execution profile 的完整配置。

    :param execution_profile_id: execution profile 稳定标识，由 map key 注入。
    :param context_window_class: profile 面向的上下文窗口分档。
    :param min_context_window_tokens: profile 要求的最小模型上下文窗口 token 数。
    :param run_baseline: 普通 Run 执行基线。
    :param compactor_baseline: compactor 执行基线。
    :param context_budget_policy: 上下文预算基线。
    :param memory_projection_policy: memory projection 基线。
    :param tool_truncation_policy: 截断治理基线。
    :param tool_duplicate_governance_policy: 工具重复调用治理基线。
    :param agent_policy: 内嵌 Agent policy 基线。
    """

    execution_profile_id: str
    context_window_class: str
    min_context_window_tokens: int
    run_baseline: ExecutionBaselineConfig
    compactor_baseline: CompactorBaselineConfig
    context_budget_policy: ContextBudgetConfig
    memory_projection_policy: MemoryProjectionConfig
    tool_truncation_policy: ToolTruncationPolicyConfig
    tool_duplicate_governance_policy: ToolDuplicateGovernancePolicyConfig
    agent_policy: AgentPolicyConfig


@dataclass(frozen=True, slots=True)
class ToolDuplicateGovernanceMessagesConfig:
    """工具重复调用治理消息配置。

    :param allow: allow 决策说明。
    :param reuse: reuse 决策说明。
    :param hint: hint 决策说明。
    :param require_justification: require_justification 决策说明。
    :param hard_stop: hard_stop 决策说明。
    :param attempt_scope_diagnostic: attempt-scoped 诊断说明。
    :param prior_accept_missing: owner 未产生 accepted fact 时的说明。
    """

    allow: str
    reuse: str
    hint: str
    require_justification: str
    hard_stop: str
    attempt_scope_diagnostic: str
    prior_accept_missing: str


@dataclass(frozen=True, slots=True)
class ToolDuplicateGovernancePolicyConfig:
    """Execution profile 内嵌工具重复调用治理配置。

    :param default_duplicate_decision: 默认重复调用治理动作。
    :param decisions_by_tool_name: 按工具名覆盖的治理动作。
    :param justification_argument_names_by_tool_name: 按工具名配置的 justification 参数名。
    :param messages: 面向模型与诊断的治理消息。
    """

    default_duplicate_decision: str
    decisions_by_tool_name: Mapping[str, str]
    justification_argument_names_by_tool_name: Mapping[str, str]
    messages: ToolDuplicateGovernanceMessagesConfig


@dataclass(frozen=True, slots=True)
class AgentPolicyConfig:
    """Execution profile 内嵌 Agent policy 配置。

    :param max_iterations: 最大 agent loop 迭代数。
    :param continuation_max_attempts: 长输出 continuation 次数。
    :param allow_tool_calls: 是否允许工具调用。
    :param tool_execution_timeout_seconds: 工具执行等待超时秒数。
    :param fallback_mode: fallback 模式，只允许 ``force_answer`` / ``raise_error``。
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
class ExecutionProfilesConfig:
    """执行 profiles 配置视图。

    :param default_execution_profile_id: 默认 execution profile id。
    :param execution_profiles: 完整 execution profiles。
    """

    default_execution_profile_id: str
    execution_profiles: Mapping[str, ExecutionProfileConfig]


@dataclass(frozen=True, slots=True)
class SQLiteRuntimeConfig:
    """Host opener SQLite 默认配置。

    :param path: SQLite 数据库路径。
    :param busy_timeout_seconds: SQLite busy timeout 秒数。
    :param write_busy_retry_count: ``BEGIN IMMEDIATE`` busy / locked 额外重试次数。
    :param write_retry_initial_delay_seconds: 首次写重试等待秒数。
    :param write_retry_backoff_multiplier: 写重试退避倍率。
    :param write_retry_max_delay_seconds: 写重试最大等待秒数。
    """

    path: str
    busy_timeout_seconds: float
    write_busy_retry_count: int
    write_retry_initial_delay_seconds: float
    write_retry_backoff_multiplier: float
    write_retry_max_delay_seconds: float


@dataclass(frozen=True, slots=True)
class HostRuntimeProfileConfig:
    """Host opener 部署默认值配置。

    :param host_runtime_id: Host runtime profile 稳定标识，由 map key 注入。
    :param store_root: Host durable store 根目录。
    :param artifact_root: Host artifact 根目录。
    :param sqlite: SQLite 默认配置。
    :param host_execution_lane_name: Host 执行 lane 名。
    :param worker_backend: worker backend 名。
    :param dispatch_poll_interval_seconds: dispatch 轮询间隔秒数。
    :param payload_inline_threshold_bytes: payload 内联存储阈值字节数。
    :param worker_startup_timeout_seconds: worker accept timeout 秒数。
    :param memory_projection_catch_up_batch_size: memory catch-up 批次大小。
    """

    host_runtime_id: str
    store_root: str
    artifact_root: str
    sqlite: SQLiteRuntimeConfig
    host_execution_lane_name: str
    worker_backend: str
    dispatch_poll_interval_seconds: float
    payload_inline_threshold_bytes: int
    worker_startup_timeout_seconds: float
    memory_projection_catch_up_batch_size: int


@dataclass(frozen=True, slots=True)
class HostRuntimeConfig:
    """Host runtime 配置视图。

    :param default_host_runtime_id: 默认 Host runtime profile id。
    :param runtimes: 按 id 索引的 Host runtime profiles。
    """

    default_host_runtime_id: str
    runtimes: Mapping[str, HostRuntimeProfileConfig]


@dataclass(frozen=True, slots=True)
class RuntimeLaneCoordinatorConfig:
    """Runtime lane coordinator 配置。

    :param db_path: 独立 runtime lane SQLite DB 路径。
    :param busy_timeout_seconds: coordinator SQLite busy timeout 秒数。
    :param poll_interval_seconds: acquire 轮询间隔秒数。
    """

    db_path: str
    busy_timeout_seconds: float
    poll_interval_seconds: float


@dataclass(frozen=True, slots=True)
class RuntimeLaneConfig:
    """单个 runtime lane 容量配置。

    :param lane_name: lane 名，由 map key 注入。
    :param capacity: lane 容量。
    :param default_timeout_seconds: 默认等待超时秒数；``None`` 表示不设超时。
    :param claim_ttl_seconds: claim TTL 秒数。
    :param heartbeat_interval_seconds: heartbeat 间隔秒数。
    """

    lane_name: str
    capacity: int
    default_timeout_seconds: float | None
    claim_ttl_seconds: float
    heartbeat_interval_seconds: float


@dataclass(frozen=True, slots=True)
class RuntimeLanesConfig:
    """Runtime lanes 配置视图。

    :param coordinator: runtime lane coordinator 配置。
    :param lanes: 按 lane 名索引的容量配置。
    """

    coordinator: RuntimeLaneCoordinatorConfig
    lanes: Mapping[str, RuntimeLaneConfig]


@dataclass(frozen=True, slots=True)
class ToolDiscoveryEntryPointConfig:
    """工具发现 package entry point 配置。

    :param group: entry point group。
    :param name: entry point name。
    """

    group: str
    name: str


@dataclass(frozen=True, slots=True)
class ToolDiscoveryProviderConfig:
    """工具发现 provider spec 配置视图。

    :param provider_id: provider spec 稳定标识，由 map key 注入。
    :param import_path: 显式 ``module:attribute`` import path。
    :param entry_point: package entry point。
    :param source_kind: 来源类别。
    :param source_id: 来源标识。
    :param enabled: 是否启用 provider。
    :param config: provider 自身的层中立 JSON 配置。
    """

    provider_id: str
    import_path: str | None
    entry_point: ToolDiscoveryEntryPointConfig | None
    source_kind: ToolBundleSourceKind
    source_id: str
    enabled: bool
    config: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ToolDiscoveryConfig:
    """工具发现 provider specs 配置视图。

    :param providers: 按 provider id 索引的 provider specs。
    """

    providers: Mapping[str, ToolDiscoveryProviderConfig]


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """五类 runtime assembly 配置总视图。

    :param models: 模型目录配置。
    :param execution_profiles: execution profiles 配置。
    :param host_runtime: Host runtime 配置。
    :param runtime_lanes: runtime lanes 配置。
    :param tool_discovery: 工具发现配置。
    """

    models: ModelsConfig
    execution_profiles: ExecutionProfilesConfig
    host_runtime: HostRuntimeConfig
    runtime_lanes: RuntimeLanesConfig
    tool_discovery: ToolDiscoveryConfig


class ConfigLoader:
    """层中立配置加载器。"""

    def __init__(self, package_config_dir: Path | None = None) -> None:
        """初始化配置加载器。

        :param package_config_dir: 包内默认配置目录；缺省使用当前包的
            ``dayu/config``。该参数主要用于测试。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._package_config_dir = (
            package_config_dir if package_config_dir is not None else _CONFIG_ROOT
        )

    def load(self, workspace_config_dir: Path | None = None) -> RuntimeConfig:
        """加载五类配置并返回总视图。

        :param workspace_config_dir: 调用方显式提供的 workspace 覆盖配置目录；
            ``None`` 表示只读取包内默认配置。
        :returns: 五类 runtime assembly typed config view。
        :raises ConfigLoadError: 配置文件缺失、JSON shape、继承或字段校验失败
            时抛出。
        """

        models = self.load_models(workspace_config_dir=workspace_config_dir)
        execution_profiles = self.load_execution_profiles(
            workspace_config_dir=workspace_config_dir
        )
        host_runtime = self.load_host_runtime(workspace_config_dir=workspace_config_dir)
        runtime_lanes = self.load_runtime_lanes(
            workspace_config_dir=workspace_config_dir
        )
        tool_discovery = self.load_tool_discovery(
            workspace_config_dir=workspace_config_dir
        )
        _validate_execution_model_references(
            execution_profiles=execution_profiles,
            models=models,
        )
        _validate_host_runtime_lane_references(
            host_runtime=host_runtime,
            runtime_lanes=runtime_lanes,
        )
        return RuntimeConfig(
            models=models,
            execution_profiles=execution_profiles,
            host_runtime=host_runtime,
            runtime_lanes=runtime_lanes,
            tool_discovery=tool_discovery,
        )

    def load_models(self, workspace_config_dir: Path | None = None) -> ModelsConfig:
        """加载模型目录配置。

        :param workspace_config_dir: 调用方显式提供的 workspace 覆盖配置目录。
        :returns: 模型目录 typed config view。
        :raises ConfigLoadError: 配置文件缺失、继承或字段校验失败时抛出。
        """

        root = _load_layered_config_file(
            package_config_dir=self._package_config_dir,
            workspace_config_dir=workspace_config_dir,
            file_name=_MODELS_FILE,
            map_fields=frozenset({"models"}),
        )
        _require_exact_fields(
            root,
            allowed=frozenset({"models"}),
            context=_MODELS_FILE,
        )
        records = _resolve_record_map(
            _require_mapping_field(root, field_name="models", context=_MODELS_FILE),
            context="models",
        )
        models: dict[str, ModelConfig] = {}
        for model_id, record in records.items():
            models[model_id] = _parse_model_config(
                record_id=model_id,
                record=record,
            )
        if not models:
            raise ConfigFieldError("models.json models must not be empty")
        return ModelsConfig(models=models)

    def load_execution_profiles(
        self, workspace_config_dir: Path | None = None
    ) -> ExecutionProfilesConfig:
        """加载 execution profiles 配置。

        :param workspace_config_dir: 调用方显式提供的 workspace 覆盖配置目录。
        :returns: execution profiles typed config view。
        :raises ConfigLoadError: 配置文件缺失、继承或字段校验失败时抛出。
        """

        root = _load_layered_config_file(
            package_config_dir=self._package_config_dir,
            workspace_config_dir=workspace_config_dir,
            file_name=_EXECUTION_PROFILES_FILE,
            map_fields=frozenset({"execution_profiles"}),
        )
        _require_exact_fields(
            root,
            allowed=frozenset(
                {
                    "default_execution_profile_id",
                    "execution_profiles",
                }
            ),
            context=_EXECUTION_PROFILES_FILE,
        )
        execution_profiles = _parse_execution_profile_map(root)
        default_execution_profile_id = _require_str_field(
            root,
            field_name="default_execution_profile_id",
            context=_EXECUTION_PROFILES_FILE,
        )
        _require_mapping_contains(
            execution_profiles,
            key=default_execution_profile_id,
            context="execution_profiles.default_execution_profile_id",
        )
        return ExecutionProfilesConfig(
            default_execution_profile_id=default_execution_profile_id,
            execution_profiles=execution_profiles,
        )

    def load_host_runtime(
        self, workspace_config_dir: Path | None = None
    ) -> HostRuntimeConfig:
        """加载 Host opener runtime 默认配置。

        :param workspace_config_dir: 调用方显式提供的 workspace 覆盖配置目录。
        :returns: Host runtime typed config view。
        :raises ConfigLoadError: 配置文件缺失、继承或字段校验失败时抛出。
        """

        root = _load_layered_config_file(
            package_config_dir=self._package_config_dir,
            workspace_config_dir=workspace_config_dir,
            file_name=_HOST_RUNTIME_FILE,
            map_fields=frozenset({"runtimes"}),
        )
        _require_exact_fields(
            root,
            allowed=frozenset({"default_host_runtime_id", "runtimes"}),
            context=_HOST_RUNTIME_FILE,
        )
        records = _resolve_record_map(
            _require_mapping_field(root, field_name="runtimes", context=_HOST_RUNTIME_FILE),
            context="host_runtime.runtimes",
        )
        runtimes: dict[str, HostRuntimeProfileConfig] = {}
        for runtime_id, record in records.items():
            runtimes[runtime_id] = _parse_host_runtime_profile(
                record_id=runtime_id,
                record=record,
            )
        if not runtimes:
            raise ConfigFieldError("host_runtime runtimes must not be empty")
        default_host_runtime_id = _require_str_field(
            root,
            field_name="default_host_runtime_id",
            context=_HOST_RUNTIME_FILE,
        )
        _require_mapping_contains(
            runtimes,
            key=default_host_runtime_id,
            context="host_runtime.default_host_runtime_id",
        )
        return HostRuntimeConfig(
            default_host_runtime_id=default_host_runtime_id,
            runtimes=runtimes,
        )

    def load_runtime_lanes(
        self, workspace_config_dir: Path | None = None
    ) -> RuntimeLanesConfig:
        """加载 runtime lanes 配置。

        :param workspace_config_dir: 调用方显式提供的 workspace 覆盖配置目录。
        :returns: runtime lanes typed config view。
        :raises ConfigLoadError: 配置文件缺失、继承或字段校验失败时抛出。
        """

        root = _load_layered_config_file(
            package_config_dir=self._package_config_dir,
            workspace_config_dir=workspace_config_dir,
            file_name=_RUNTIME_LANES_FILE,
            map_fields=frozenset({"lanes"}),
        )
        _require_exact_fields(
            root,
            allowed=frozenset({"coordinator", "lanes"}),
            context=_RUNTIME_LANES_FILE,
        )
        lanes = _parse_runtime_lane_map(root)
        if not lanes:
            raise ConfigFieldError("runtime_lanes.json lanes must not be empty")
        return RuntimeLanesConfig(
            coordinator=_parse_runtime_lane_coordinator(
                _require_mapping_field(
                    root,
                    field_name="coordinator",
                    context=_RUNTIME_LANES_FILE,
                )
            ),
            lanes=lanes,
        )

    def load_tool_discovery(
        self, workspace_config_dir: Path | None = None
    ) -> ToolDiscoveryConfig:
        """加载工具发现 provider specs 配置。

        :param workspace_config_dir: 调用方显式提供的 workspace 覆盖配置目录。
        :returns: 工具发现 typed config view。
        :raises ConfigLoadError: 配置文件缺失、继承或字段校验失败时抛出。
        """

        root = _load_layered_config_file(
            package_config_dir=self._package_config_dir,
            workspace_config_dir=workspace_config_dir,
            file_name=_TOOL_DISCOVERY_FILE,
            map_fields=frozenset({"providers"}),
        )
        _require_exact_fields(
            root,
            allowed=frozenset({"providers"}),
            context=_TOOL_DISCOVERY_FILE,
        )
        records = _resolve_record_map(
            _require_mapping_field(root, field_name="providers", context=_TOOL_DISCOVERY_FILE),
            context="tool_discovery.providers",
        )
        providers: dict[str, ToolDiscoveryProviderConfig] = {}
        for provider_id, record in records.items():
            providers[provider_id] = _parse_tool_discovery_provider(
                record_id=provider_id,
                record=record,
            )
        if not providers:
            raise ConfigFieldError("tool_discovery providers must not be empty")
        return ToolDiscoveryConfig(providers=providers)


def load_runtime_config(workspace_config_dir: Path | None = None) -> RuntimeConfig:
    """使用默认加载器加载 runtime assembly 配置。

    :param workspace_config_dir: 调用方显式提供的 workspace 覆盖配置目录。
    :returns: 五类 runtime assembly typed config view。
    :raises ConfigLoadError: 配置文件缺失、JSON shape、继承或字段校验失败
        时抛出。
    """

    return ConfigLoader().load(workspace_config_dir=workspace_config_dir)


def legacy_config_file_names() -> frozenset[str]:
    """返回已移除的旧配置文件名集合。

    :returns: 旧配置文件名集合；仅用于诊断或测试确认不会读取旧路径。
    :raises Exception: 不主动抛出异常。
    """

    return _LEGACY_CONFIG_FILES


def config_file_names() -> tuple[str, ...]:
    """返回当前 ConfigLoader 读取的配置文件名。

    :returns: 当前配置文件名元组。
    :raises Exception: 不主动抛出异常。
    """

    return _CONFIG_FILE_NAMES


def default_fallback_prompt() -> str:
    """返回默认 Agent fallback prompt 文本。

    :returns: 默认 fallback prompt。
    :raises Exception: 不主动抛出异常。
    """

    return _DEFAULT_FALLBACK_PROMPT


def _load_layered_config_file(
    *,
    package_config_dir: Path,
    workspace_config_dir: Path | None,
    file_name: str,
    map_fields: frozenset[str],
) -> JsonObject:
    """加载单个配置文件并应用 workspace overlay。

    :param package_config_dir: 包内默认配置目录。
    :param workspace_config_dir: workspace 覆盖配置目录。
    :param file_name: 配置文件名。
    :param map_fields: 需要按稳定 id 合并的顶层 map 字段名。
    :returns: overlay 后的 JSON object。
    :raises ConfigLoadError: 文件缺失、JSON 非法或顶层 shape 非法时抛出。
    """

    package_root = _read_required_json_object(package_config_dir / file_name)
    if workspace_config_dir is None:
        return package_root
    workspace_path = workspace_config_dir / file_name
    if not workspace_path.exists():
        return package_root
    workspace_root = _read_required_json_object(workspace_path)
    return _overlay_roots(
        package_root=package_root,
        workspace_root=workspace_root,
        map_fields=map_fields,
        context=file_name,
    )


def _read_required_json_object(path: Path) -> JsonObject:
    """读取必需 JSON object 文件。

    :param path: 配置文件路径。
    :returns: JSON object。
    :raises ConfigFileNotFoundError: 文件不存在时抛出。
    :raises ConfigShapeError: JSON 解析失败或顶层不是 object 时抛出。
    """

    if not path.exists():
        raise ConfigFileNotFoundError(f"config file not found: {path}")
    try:
        value = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        raise ConfigShapeError(f"invalid JSON config file: {path}") from exc
    return _require_json_object(value, context=str(path))


def _overlay_roots(
    *,
    package_root: JsonObject,
    workspace_root: JsonObject,
    map_fields: frozenset[str],
    context: str,
) -> JsonObject:
    """对单个配置文件执行顶层 overlay。

    :param package_root: 包内默认配置顶层 object。
    :param workspace_root: workspace 配置顶层 object。
    :param map_fields: 需要按稳定 id 合并的顶层 map 字段名。
    :param context: 错误消息上下文。
    :returns: overlay 后顶层 object。
    :raises ConfigShapeError: map 字段不是 JSON object 时抛出。
    """

    merged: dict[str, JsonValue] = dict(package_root)
    for field_name, workspace_value in workspace_root.items():
        if field_name in map_fields:
            package_value = package_root.get(field_name, {})
            package_map = _require_json_object(
                package_value,
                context=f"{context}.{field_name}",
            )
            workspace_map = _require_json_object(
                workspace_value,
                context=f"{context}.{field_name}",
            )
            map_merged: dict[str, JsonValue] = dict(package_map)
            map_merged.update(workspace_map)
            merged[field_name] = map_merged
        else:
            merged[field_name] = workspace_value
    return merged


def _resolve_record_map(records: JsonObject, *, context: str) -> Mapping[str, JsonObject]:
    """解析带 ``extends`` 的记录 map。

    :param records: 按稳定 id 索引的记录 map。
    :param context: 错误消息上下文。
    :returns: 继承解析后的记录 map。
    :raises ConfigShapeError: 记录不是 JSON object 时抛出。
    :raises ConfigExtendsError: 继承循环、自引用、多继承或父项缺失时抛出。
    """

    resolved: dict[str, JsonObject] = {}
    visiting: list[str] = []
    for record_id in records:
        _resolve_record(
            record_id=record_id,
            records=records,
            resolved=resolved,
            visiting=visiting,
            context=context,
        )
    return resolved


def _resolve_record(
    *,
    record_id: str,
    records: JsonObject,
    resolved: dict[str, JsonObject],
    visiting: list[str],
    context: str,
) -> JsonObject:
    """递归解析单条记录的单继承关系。

    :param record_id: 待解析记录 id。
    :param records: 所有记录 map。
    :param resolved: 已解析记录缓存。
    :param visiting: 当前递归栈。
    :param context: 错误消息上下文。
    :returns: 解析后的记录。
    :raises ConfigShapeError: 记录 shape 非法时抛出。
    :raises ConfigExtendsError: 继承循环、自引用、多继承或父项缺失时抛出。
    """

    if record_id in resolved:
        return resolved[record_id]
    if record_id in visiting:
        chain = " -> ".join([*visiting, record_id])
        raise ConfigExtendsError(f"{context} extends cycle: {chain}")
    value = records.get(record_id)
    if value is None:
        raise ConfigExtendsError(f"{context} parent not found: {record_id}")
    record = _require_json_object(value, context=f"{context}.{record_id}")
    visiting.append(record_id)
    parent_id = _parse_extends_field(record, context=f"{context}.{record_id}")
    if parent_id is None:
        merged: dict[str, JsonValue] = {
            key: item for key, item in record.items() if key != _EXTENDS_FIELD
        }
    else:
        if parent_id == record_id:
            raise ConfigExtendsError(f"{context}.{record_id} extends self")
        if parent_id not in records:
            raise ConfigExtendsError(
                f"{context}.{record_id} extends missing parent: {parent_id}"
            )
        parent = _resolve_record(
            record_id=parent_id,
            records=records,
            resolved=resolved,
            visiting=visiting,
            context=context,
        )
        merged = dict(parent)
        for key, item in record.items():
            if key != _EXTENDS_FIELD:
                merged[key] = item
    visiting.pop()
    resolved[record_id] = merged
    return merged


def _parse_extends_field(record: JsonObject, *, context: str) -> str | None:
    """解析 ``extends`` 字段。

    :param record: 待解析记录。
    :param context: 错误消息上下文。
    :returns: 父记录 id；未配置或显式 ``null`` 时返回 ``None``。
    :raises ConfigExtendsError: ``extends`` 不是单个非空字符串时抛出。
    """

    if _EXTENDS_FIELD not in record or record[_EXTENDS_FIELD] is None:
        return None
    value = record[_EXTENDS_FIELD]
    if isinstance(value, list):
        raise ConfigExtendsError(f"{context}.extends multiple parents are not allowed")
    if not isinstance(value, str):
        raise ConfigExtendsError(f"{context}.extends must be a string or null")
    if not value.strip():
        raise ConfigExtendsError(f"{context}.extends must be non-empty")
    return value


def _parse_model_config(*, record_id: str, record: JsonObject) -> ModelConfig:
    """解析单条模型配置。

    :param record_id: 模型记录 id。
    :param record: 继承解析后的模型记录。
    :returns: 模型 typed config。
    :raises ConfigFieldError: 字段缺失、非法类型或出现重复 id 字段时抛出。
    """

    context = f"models.{record_id}"
    _require_no_forbidden_id_fields(record, context=context)
    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "runner_kind",
                "provider",
                "model",
                "endpoint",
                "api_key_ref",
                "headers",
                "supports_tool_calling",
                "supports_stream",
                "supports_stream_usage",
                "default_timeout_seconds",
                "max_retries",
                "sse_idle_timeout_seconds",
                "sse_heartbeat_seconds",
                "provider_request_extension",
                "context_window_tokens",
                "runtime_hints",
            }
        ),
        context=context,
    )
    return ModelConfig(
        model_id=record_id,
        runner_kind=_parse_runner_kind(
            _require_str_field(record, field_name="runner_kind", context=context),
            context=f"{context}.runner_kind",
        ),
        provider=_require_str_field(record, field_name="provider", context=context),
        model=_require_str_field(record, field_name="model", context=context),
        endpoint=_require_str_field(record, field_name="endpoint", context=context),
        api_key_ref=_optional_str_field(record, field_name="api_key_ref", context=context),
        headers=_require_str_mapping_field(record, field_name="headers", context=context),
        supports_tool_calling=_require_bool_field(record, field_name="supports_tool_calling", context=context),
        supports_stream=_require_bool_field(record, field_name="supports_stream", context=context),
        supports_stream_usage=_require_bool_field(record, field_name="supports_stream_usage", context=context),
        default_timeout_seconds=_require_positive_float_field(record, field_name="default_timeout_seconds", context=context),
        max_retries=_require_non_negative_int_field(record, field_name="max_retries", context=context),
        sse_idle_timeout_seconds=_require_positive_float_field(record, field_name="sse_idle_timeout_seconds", context=context),
        sse_heartbeat_seconds=_require_positive_float_field(record, field_name="sse_heartbeat_seconds", context=context),
        provider_request_extension=_require_field(record, field_name="provider_request_extension", context=context),
        context_window_tokens=_require_positive_int_field(record, field_name="context_window_tokens", context=context),
        runtime_hints=_parse_model_runtime_hints(
            _require_mapping_field(record, field_name="runtime_hints", context=context),
            context=f"{context}.runtime_hints",
        ),
    )


def _parse_runner_kind(value: str, *, context: str) -> RunnerKind:
    """解析 RunnerKind。

    :param value: 配置中的 RunnerKind 字符串。
    :param context: 错误消息上下文。
    :returns: RunnerKind。
    :raises ConfigFieldError: 值不属于已知 RunnerKind 时抛出。
    """

    try:
        return RunnerKind(value)
    except ValueError as exc:
        raise ConfigFieldError(f"{context} has unsupported runner kind: {value}") from exc


def _parse_model_runtime_hints(
    record: JsonObject, *, context: str
) -> ModelRuntimeHintsConfig:
    """解析模型 runtime hints。

    :param record: runtime_hints JSON object。
    :param context: 错误消息上下文。
    :returns: 模型 runtime hints typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset({"runner_option_hints"}),
        context=context,
    )
    raw_hints = _require_mapping_field(
        record,
        field_name="runner_option_hints",
        context=context,
    )
    hints: dict[str, RunnerOptionHintConfig] = {}
    for hint_id, hint_value in raw_hints.items():
        hint_record = _require_json_object(
            hint_value,
            context=f"{context}.runner_option_hints.{hint_id}",
        )
        hints[hint_id] = _parse_runner_option_hint(
            hint_record,
            context=f"{context}.runner_option_hints.{hint_id}",
        )
    if not hints:
        raise ConfigFieldError(f"{context}.runner_option_hints must not be empty")
    return ModelRuntimeHintsConfig(runner_option_hints=hints)


def _parse_runner_option_hint(
    record: JsonObject, *, context: str
) -> RunnerOptionHintConfig:
    """解析单个 RunnerCallOptions hint。

    :param record: hint JSON object。
    :param context: 错误消息上下文。
    :returns: RunnerCallOptions hint typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset({"temperature", "top_p", "stream"}),
        context=context,
    )
    return RunnerOptionHintConfig(
        temperature=_require_float_field(record, field_name="temperature", context=context),
        top_p=_require_float_field(record, field_name="top_p", context=context),
        stream=_require_bool_field(record, field_name="stream", context=context),
    )


def _parse_execution_profile_map(root: JsonObject) -> Mapping[str, ExecutionProfileConfig]:
    """解析 execution profile map。

    :param root: execution_profiles.json 顶层 object。
    :returns: execution profile map。
    :raises ConfigLoadError: 记录继承或字段校验失败时抛出。
    """

    records = _resolve_record_map(
        _require_mapping_field(
            root,
            field_name="execution_profiles",
            context=_EXECUTION_PROFILES_FILE,
        ),
        context="execution_profiles.execution_profiles",
    )
    profiles: dict[str, ExecutionProfileConfig] = {}
    for profile_id, record in records.items():
        profiles[profile_id] = _parse_execution_profile(
            record_id=profile_id,
            record=record,
        )
    if not profiles:
        raise ConfigFieldError("execution_profiles execution_profiles must not be empty")
    return profiles


def _parse_execution_profile(
    *, record_id: str, record: JsonObject
) -> ExecutionProfileConfig:
    """解析单个 execution profile。

    :param record_id: profile id。
    :param record: 继承解析后的 profile 记录。
    :returns: execution profile typed config。
    :raises ConfigFieldError: 字段缺失、非法类型或出现重复 id 字段时抛出。
    """

    context = f"execution_profiles.execution_profiles.{record_id}"
    _require_no_forbidden_id_fields(record, context=context)
    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "context_window_class",
                "min_context_window_tokens",
                "run_baseline",
                "compactor_baseline",
                "context_budget_policy",
                "memory_projection_policy",
                "tool_truncation_policy",
                "tool_duplicate_governance_policy",
                "agent_policy",
            }
        ),
        context=context,
    )
    context_window_class = _parse_execution_profile_context_window_class(
        _require_str_field(
            record,
            field_name="context_window_class",
            context=context,
        ),
        context=f"{context}.context_window_class",
    )
    min_context_window_tokens = _require_positive_int_field(
        record,
        field_name="min_context_window_tokens",
        context=context,
    )
    _validate_execution_profile_context_window_pair(
        context_window_class=context_window_class,
        min_context_window_tokens=min_context_window_tokens,
        context=context,
    )
    return ExecutionProfileConfig(
        execution_profile_id=record_id,
        context_window_class=context_window_class,
        min_context_window_tokens=min_context_window_tokens,
        run_baseline=_parse_execution_baseline(
            _require_mapping_field(
                record,
                field_name="run_baseline",
                context=context,
            ),
            context=f"{context}.run_baseline",
        ),
        compactor_baseline=_parse_compactor_baseline(
            _require_mapping_field(
                record,
                field_name="compactor_baseline",
                context=context,
            ),
            context=f"{context}.compactor_baseline",
        ),
        context_budget_policy=_parse_context_budget(
            _require_mapping_field(
                record,
                field_name="context_budget_policy",
                context=context,
            ),
            context=f"{context}.context_budget_policy",
        ),
        memory_projection_policy=_parse_memory_projection(
            _require_mapping_field(
                record,
                field_name="memory_projection_policy",
                context=context,
            ),
            context=f"{context}.memory_projection_policy",
        ),
        tool_truncation_policy=_parse_tool_truncation_policy(
            _require_mapping_field(
                record,
                field_name="tool_truncation_policy",
                context=context,
            ),
            context=f"{context}.tool_truncation_policy",
        ),
        tool_duplicate_governance_policy=_parse_tool_duplicate_governance_policy(
            _require_mapping_field(
                record,
                field_name="tool_duplicate_governance_policy",
                context=context,
            ),
            context=f"{context}.tool_duplicate_governance_policy",
        ),
        agent_policy=_parse_agent_policy(
            _require_mapping_field(
                record,
                field_name="agent_policy",
                context=context,
            ),
            context=f"{context}.agent_policy",
        ),
    )


def _parse_execution_profile_context_window_class(
    value: str, *, context: str
) -> str:
    """解析 execution profile 上下文窗口分档。

    :param value: 配置中的上下文窗口分档。
    :param context: 错误消息上下文。
    :returns: 合法上下文窗口分档。
    :raises ConfigFieldError: 分档值不在允许集合内时抛出。
    """

    if value not in _EXECUTION_PROFILE_CONTEXT_WINDOW_CLASSES:
        raise ConfigFieldError(
            f"{context} has unsupported value: {value}"
        )
    return value


def _validate_execution_profile_context_window_pair(
    *,
    context_window_class: str,
    min_context_window_tokens: int,
    context: str,
) -> None:
    """校验 execution profile 窗口分档与最小 token 数一致。

    :param context_window_class: 已解析的上下文窗口分档。
    :param min_context_window_tokens: 已解析的最小上下文窗口 token 数。
    :param context: 错误消息上下文。
    :returns: ``None``。
    :raises ConfigFieldError: 分档与最小 token 数不一致时抛出。
    """

    expected_tokens = _EXECUTION_PROFILE_MIN_CONTEXT_WINDOW_TOKENS_BY_CLASS[
        context_window_class
    ]
    if min_context_window_tokens != expected_tokens:
        raise ConfigFieldError(
            f"{context}.min_context_window_tokens must be {expected_tokens} "
            f"when context_window_class is {context_window_class}"
        )


def _parse_execution_baseline(
    record: JsonObject, *, context: str
) -> ExecutionBaselineConfig:
    """解析普通 Run 执行基线。

    :param record: baseline 记录。
    :param context: 错误消息上下文。
    :returns: execution baseline typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset({"model_id", "runner_option_hint_id"}),
        context=context,
    )
    return ExecutionBaselineConfig(
        model_id=_require_str_field(record, field_name="model_id", context=context),
        runner_option_hint_id=_require_str_field(
            record,
            field_name="runner_option_hint_id",
            context=context,
        ),
    )


def _parse_compactor_baseline(
    record: JsonObject, *, context: str
) -> CompactorBaselineConfig:
    """解析 compactor 执行基线。

    :param record: compactor 记录。
    :param context: 错误消息上下文。
    :returns: compactor typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "model_id",
                "scene_id",
                "runner_option_hint_id",
                "user_prompt_template_path",
                "artifact_root",
            }
        ),
        context=context,
    )
    return CompactorBaselineConfig(
        model_id=_require_str_field(record, field_name="model_id", context=context),
        scene_id=_require_str_field(record, field_name="scene_id", context=context),
        runner_option_hint_id=_require_str_field(
            record,
            field_name="runner_option_hint_id",
            context=context,
        ),
        user_prompt_template_path=_require_str_field(
            record,
            field_name="user_prompt_template_path",
            context=context,
        ),
        artifact_root=_require_str_field(record, field_name="artifact_root", context=context),
    )


def _parse_context_budget(record: JsonObject, *, context: str) -> ContextBudgetConfig:
    """解析上下文预算配置。

    :param record: context budget 记录。
    :param context: 错误消息上下文。
    :returns: context budget typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "soft_threshold_context_ratio",
                "hard_threshold_context_ratio",
                "max_proactive_compactions_per_run",
                "max_reactive_compactions_per_run",
                "max_compaction_attempts_per_operation",
                "policy_ref",
            }
        ),
        context=context,
    )
    return ContextBudgetConfig(
        soft_threshold_context_ratio=_require_float_field(record, field_name="soft_threshold_context_ratio", context=context),
        hard_threshold_context_ratio=_require_float_field(record, field_name="hard_threshold_context_ratio", context=context),
        max_proactive_compactions_per_run=_require_positive_int_field(record, field_name="max_proactive_compactions_per_run", context=context),
        max_reactive_compactions_per_run=_require_positive_int_field(record, field_name="max_reactive_compactions_per_run", context=context),
        max_compaction_attempts_per_operation=_require_positive_int_field(record, field_name="max_compaction_attempts_per_operation", context=context),
        policy_ref=_require_str_field(record, field_name="policy_ref", context=context),
    )


def _parse_memory_projection(
    record: JsonObject, *, context: str
) -> MemoryProjectionConfig:
    """解析 memory projection 配置。

    :param record: memory projection 记录。
    :param context: 错误消息上下文。
    :returns: memory projection typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "context_window_size",
                "selected_recent_window_item_cap",
                "selected_recent_window_char_cap",
                "selected_recent_window_turn_floor",
                "fallback_selected_recent_window_item_cap",
                "fallback_selected_recent_window_char_cap",
                "evidence_fact_item_cap",
                "evidence_fact_char_cap",
                "evidence_fact_floor",
                "session_summary_char_cap",
                "answer_anchor_item_cap",
                "answer_anchor_char_cap",
                "forward_intent_item_cap",
                "forward_intent_char_cap",
                "reference_continuity_item_cap",
                "reference_continuity_char_cap",
                "reference_continuity_item_floor",
                "max_lag_events_for_inline_delta",
                "max_delta_repair_events",
                "policy_ref",
            }
        ),
        context=context,
    )
    return MemoryProjectionConfig(
        context_window_size=_require_positive_int_field(record, field_name="context_window_size", context=context),
        selected_recent_window_item_cap=_require_positive_int_field(record, field_name="selected_recent_window_item_cap", context=context),
        selected_recent_window_char_cap=_require_positive_int_field(record, field_name="selected_recent_window_char_cap", context=context),
        selected_recent_window_turn_floor=_require_non_negative_int_field(record, field_name="selected_recent_window_turn_floor", context=context),
        fallback_selected_recent_window_item_cap=_require_positive_int_field(record, field_name="fallback_selected_recent_window_item_cap", context=context),
        fallback_selected_recent_window_char_cap=_require_positive_int_field(record, field_name="fallback_selected_recent_window_char_cap", context=context),
        evidence_fact_item_cap=_require_positive_int_field(record, field_name="evidence_fact_item_cap", context=context),
        evidence_fact_char_cap=_require_positive_int_field(record, field_name="evidence_fact_char_cap", context=context),
        evidence_fact_floor=_require_non_negative_int_field(record, field_name="evidence_fact_floor", context=context),
        session_summary_char_cap=_require_positive_int_field(record, field_name="session_summary_char_cap", context=context),
        answer_anchor_item_cap=_require_positive_int_field(record, field_name="answer_anchor_item_cap", context=context),
        answer_anchor_char_cap=_require_positive_int_field(record, field_name="answer_anchor_char_cap", context=context),
        forward_intent_item_cap=_require_positive_int_field(record, field_name="forward_intent_item_cap", context=context),
        forward_intent_char_cap=_require_positive_int_field(record, field_name="forward_intent_char_cap", context=context),
        reference_continuity_item_cap=_require_positive_int_field(record, field_name="reference_continuity_item_cap", context=context),
        reference_continuity_char_cap=_require_positive_int_field(record, field_name="reference_continuity_char_cap", context=context),
        reference_continuity_item_floor=_require_non_negative_int_field(record, field_name="reference_continuity_item_floor", context=context),
        max_lag_events_for_inline_delta=_require_non_negative_int_field(record, field_name="max_lag_events_for_inline_delta", context=context),
        max_delta_repair_events=_require_non_negative_int_field(record, field_name="max_delta_repair_events", context=context),
        policy_ref=_require_str_field(record, field_name="policy_ref", context=context),
    )


def _parse_tool_truncation_policy(
    record: JsonObject, *, context: str
) -> ToolTruncationPolicyConfig:
    """解析 tool truncation policy。

    :param record: truncation policy 记录。
    :param context: 错误消息上下文。
    :returns: truncation policy typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset({"enabled", "default_cursor_ttl_seconds", "default_limits"}),
        context=context,
    )
    return ToolTruncationPolicyConfig(
        enabled=_require_bool_field(record, field_name="enabled", context=context),
        default_cursor_ttl_seconds=_require_positive_float_field(
            record,
            field_name="default_cursor_ttl_seconds",
            context=context,
        ),
        default_limits=_parse_tool_truncation_limits(
            _require_mapping_field(record, field_name="default_limits", context=context),
            context=f"{context}.default_limits",
        ),
    )


def _parse_tool_truncation_limits(
    record: JsonObject, *, context: str
) -> ToolTruncationDefaultLimitsConfig:
    """解析工具截断默认 limits。

    :param record: default_limits JSON object。
    :param context: 错误消息上下文。
    :returns: truncation limits typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset({"text_chars", "text_lines", "list_items", "binary_bytes"}),
        context=context,
    )
    text_chars = _require_mapping_field(record, field_name="text_chars", context=context)
    text_lines = _require_mapping_field(record, field_name="text_lines", context=context)
    list_items = _require_mapping_field(record, field_name="list_items", context=context)
    binary_bytes = _require_mapping_field(record, field_name="binary_bytes", context=context)
    _require_exact_fields(text_chars, allowed=frozenset({"max_chars"}), context=f"{context}.text_chars")
    _require_exact_fields(text_lines, allowed=frozenset({"max_lines"}), context=f"{context}.text_lines")
    _require_exact_fields(list_items, allowed=frozenset({"max_items"}), context=f"{context}.list_items")
    _require_exact_fields(binary_bytes, allowed=frozenset({"max_bytes"}), context=f"{context}.binary_bytes")
    return ToolTruncationDefaultLimitsConfig(
        text_chars=TextCharsLimitConfig(
            max_chars=_require_positive_int_field(text_chars, field_name="max_chars", context=f"{context}.text_chars")
        ),
        text_lines=TextLinesLimitConfig(
            max_lines=_require_positive_int_field(text_lines, field_name="max_lines", context=f"{context}.text_lines")
        ),
        list_items=ListItemsLimitConfig(
            max_items=_require_positive_int_field(list_items, field_name="max_items", context=f"{context}.list_items")
        ),
        binary_bytes=BinaryBytesLimitConfig(
            max_bytes=_require_positive_int_field(binary_bytes, field_name="max_bytes", context=f"{context}.binary_bytes")
        ),
    )


def _parse_tool_duplicate_governance_policy(
    record: JsonObject, *, context: str
) -> ToolDuplicateGovernancePolicyConfig:
    """解析工具重复调用治理 policy。

    :param record: duplicate governance policy JSON object。
    :param context: 错误消息上下文。
    :returns: duplicate governance policy typed config。
    :raises ConfigFieldError: 字段缺失、非法类型或决策值非法时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "default_duplicate_decision",
                "decisions_by_tool_name",
                "justification_argument_names_by_tool_name",
                "messages",
            }
        ),
        context=context,
    )
    default_duplicate_decision = _parse_tool_duplicate_governance_decision(
        _require_str_field(
            record,
            field_name="default_duplicate_decision",
            context=context,
        ),
        context=f"{context}.default_duplicate_decision",
    )
    return ToolDuplicateGovernancePolicyConfig(
        default_duplicate_decision=default_duplicate_decision,
        decisions_by_tool_name=_parse_tool_duplicate_decision_mapping(
            _require_mapping_field(
                record,
                field_name="decisions_by_tool_name",
                context=context,
            ),
            context=f"{context}.decisions_by_tool_name",
        ),
        justification_argument_names_by_tool_name=_parse_non_empty_str_mapping(
            _require_mapping_field(
                record,
                field_name="justification_argument_names_by_tool_name",
                context=context,
            ),
            context=f"{context}.justification_argument_names_by_tool_name",
        ),
        messages=_parse_tool_duplicate_governance_messages(
            _require_mapping_field(record, field_name="messages", context=context),
            context=f"{context}.messages",
        ),
    )


def _parse_tool_duplicate_governance_messages(
    record: JsonObject, *, context: str
) -> ToolDuplicateGovernanceMessagesConfig:
    """解析工具重复调用治理消息。

    :param record: messages JSON object。
    :param context: 错误消息上下文。
    :returns: duplicate governance messages typed config。
    :raises ConfigFieldError: 字段缺失、非法类型或空文本时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "allow",
                "reuse",
                "hint",
                "require_justification",
                "hard_stop",
                "attempt_scope_diagnostic",
                "prior_accept_missing",
            }
        ),
        context=context,
    )
    return ToolDuplicateGovernanceMessagesConfig(
        allow=_require_str_field(record, field_name="allow", context=context),
        reuse=_require_str_field(record, field_name="reuse", context=context),
        hint=_require_str_field(record, field_name="hint", context=context),
        require_justification=_require_str_field(
            record,
            field_name="require_justification",
            context=context,
        ),
        hard_stop=_require_str_field(record, field_name="hard_stop", context=context),
        attempt_scope_diagnostic=_require_str_field(
            record,
            field_name="attempt_scope_diagnostic",
            context=context,
        ),
        prior_accept_missing=_require_str_field(
            record,
            field_name="prior_accept_missing",
            context=context,
        ),
    )


def _parse_tool_duplicate_decision_mapping(
    record: JsonObject, *, context: str
) -> Mapping[str, str]:
    """解析工具名到重复治理决策的映射。

    :param record: 工具名到决策字符串的 JSON object。
    :param context: 错误消息上下文。
    :returns: 工具名到合法决策字符串的映射。
    :raises ConfigFieldError: 工具名为空、值非字符串或决策非法时抛出。
    """

    result: dict[str, str] = {}
    for tool_name, decision in record.items():
        if not tool_name.strip():
            raise ConfigFieldError(f"{context} contains empty tool name")
        if not isinstance(decision, str):
            raise ConfigFieldError(f"{context}.{tool_name} must be a string")
        result[tool_name] = _parse_tool_duplicate_governance_decision(
            decision,
            context=f"{context}.{tool_name}",
        )
    return result


def _parse_tool_duplicate_governance_decision(value: str, *, context: str) -> str:
    """校验工具重复调用治理决策值。

    :param value: 配置中的决策字符串。
    :param context: 错误消息上下文。
    :returns: 合法决策字符串。
    :raises ConfigFieldError: 决策值不在允许集合内时抛出。
    """

    if value not in _TOOL_DUPLICATE_GOVERNANCE_DECISIONS:
        raise ConfigFieldError(f"{context} has unsupported value: {value}")
    return value


def _parse_agent_policy(
    record: JsonObject, *, context: str
) -> AgentPolicyConfig:
    """解析 execution profile 内嵌 Agent policy。

    :param record: agent policy JSON object。
    :param context: 错误消息上下文。
    :returns: Agent policy typed config。
    :raises ConfigFieldError: 字段缺失、非法类型或 fallback mode 非法时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "max_iterations",
                "continuation_max_attempts",
                "allow_tool_calls",
                "tool_execution_timeout_seconds",
                "fallback_mode",
                "fallback_prompt",
                "continuation_prompt",
                "max_consecutive_failed_tool_batches",
            }
        ),
        context=context,
    )
    fallback_mode = _require_str_field(record, field_name="fallback_mode", context=context)
    if fallback_mode not in AGENT_FALLBACK_MODES:
        raise ConfigFieldError(f"{context}.fallback_mode has unsupported value: {fallback_mode}")
    return AgentPolicyConfig(
        max_iterations=_require_positive_int_field(record, field_name="max_iterations", context=context),
        continuation_max_attempts=_require_non_negative_int_field(record, field_name="continuation_max_attempts", context=context),
        allow_tool_calls=_require_bool_field(record, field_name="allow_tool_calls", context=context),
        tool_execution_timeout_seconds=_require_positive_float_field(record, field_name="tool_execution_timeout_seconds", context=context),
        fallback_mode=fallback_mode,
        fallback_prompt=_require_str_field(record, field_name="fallback_prompt", context=context),
        continuation_prompt=_require_str_field(record, field_name="continuation_prompt", context=context),
        max_consecutive_failed_tool_batches=_require_positive_int_field(record, field_name="max_consecutive_failed_tool_batches", context=context),
    )


def _parse_host_runtime_profile(
    *, record_id: str, record: JsonObject
) -> HostRuntimeProfileConfig:
    """解析单个 Host runtime profile。

    :param record_id: runtime profile id。
    :param record: 继承解析后的 runtime profile 记录。
    :returns: Host runtime profile typed config。
    :raises ConfigFieldError: 字段缺失、非法类型或出现重复 id 字段时抛出。
    """

    context = f"host_runtime.runtimes.{record_id}"
    _require_no_forbidden_id_fields(record, context=context)
    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "store_root",
                "artifact_root",
                "sqlite",
                "host_execution_lane_name",
                "worker_backend",
                "dispatch_poll_interval_seconds",
                "payload_inline_threshold_bytes",
                "worker_startup_timeout_seconds",
                "memory_projection_catch_up_batch_size",
            }
        ),
        context=context,
    )
    return HostRuntimeProfileConfig(
        host_runtime_id=record_id,
        store_root=_require_str_field(record, field_name="store_root", context=context),
        artifact_root=_require_str_field(record, field_name="artifact_root", context=context),
        sqlite=_parse_sqlite_runtime(
            _require_mapping_field(record, field_name="sqlite", context=context),
            context=f"{context}.sqlite",
        ),
        host_execution_lane_name=_require_str_field(
            record,
            field_name="host_execution_lane_name",
            context=context,
        ),
        worker_backend=_require_str_field(record, field_name="worker_backend", context=context),
        dispatch_poll_interval_seconds=_require_positive_float_field(record, field_name="dispatch_poll_interval_seconds", context=context),
        payload_inline_threshold_bytes=_require_positive_int_field(record, field_name="payload_inline_threshold_bytes", context=context),
        worker_startup_timeout_seconds=_require_positive_float_field(record, field_name="worker_startup_timeout_seconds", context=context),
        memory_projection_catch_up_batch_size=_require_positive_int_field(record, field_name="memory_projection_catch_up_batch_size", context=context),
    )


def _parse_sqlite_runtime(
    record: JsonObject, *, context: str
) -> SQLiteRuntimeConfig:
    """解析 SQLite runtime 配置。

    :param record: SQLite 配置记录。
    :param context: 错误消息上下文。
    :returns: SQLite runtime typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "path",
                "busy_timeout_seconds",
                "write_busy_retry_count",
                "write_retry_initial_delay_seconds",
                "write_retry_backoff_multiplier",
                "write_retry_max_delay_seconds",
            }
        ),
        context=context,
    )
    return SQLiteRuntimeConfig(
        path=_require_str_field(record, field_name="path", context=context),
        busy_timeout_seconds=_require_positive_float_field(record, field_name="busy_timeout_seconds", context=context),
        write_busy_retry_count=_require_non_negative_int_field(record, field_name="write_busy_retry_count", context=context),
        write_retry_initial_delay_seconds=_require_positive_float_field(record, field_name="write_retry_initial_delay_seconds", context=context),
        write_retry_backoff_multiplier=_require_positive_float_field(record, field_name="write_retry_backoff_multiplier", context=context),
        write_retry_max_delay_seconds=_require_positive_float_field(record, field_name="write_retry_max_delay_seconds", context=context),
    )


def _parse_runtime_lane_coordinator(
    record: JsonObject,
) -> RuntimeLaneCoordinatorConfig:
    """解析 runtime lane coordinator 配置。

    :param record: coordinator JSON object。
    :returns: runtime lane coordinator typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    context = "runtime_lanes.coordinator"
    _require_exact_fields(
        record,
        allowed=frozenset({"db_path", "busy_timeout_seconds", "poll_interval_seconds"}),
        context=context,
    )
    return RuntimeLaneCoordinatorConfig(
        db_path=_require_str_field(record, field_name="db_path", context=context),
        busy_timeout_seconds=_require_positive_float_field(record, field_name="busy_timeout_seconds", context=context),
        poll_interval_seconds=_require_positive_float_field(record, field_name="poll_interval_seconds", context=context),
    )


def _parse_runtime_lane_map(root: JsonObject) -> Mapping[str, RuntimeLaneConfig]:
    """解析 runtime lane map。

    :param root: runtime_lanes.json 顶层 object。
    :returns: runtime lane map。
    :raises ConfigLoadError: 记录继承或字段校验失败时抛出。
    """

    records = _resolve_record_map(
        _require_mapping_field(root, field_name="lanes", context=_RUNTIME_LANES_FILE),
        context="runtime_lanes.lanes",
    )
    lanes: dict[str, RuntimeLaneConfig] = {}
    for lane_name, record in records.items():
        lanes[lane_name] = _parse_runtime_lane(
            record_id=lane_name,
            record=record,
        )
    return lanes


def _parse_runtime_lane(*, record_id: str, record: JsonObject) -> RuntimeLaneConfig:
    """解析单个 runtime lane。

    :param record_id: lane 名。
    :param record: lane JSON object。
    :returns: runtime lane typed config。
    :raises ConfigFieldError: 字段缺失、非法类型或 TTL 非法时抛出。
    """

    context = f"runtime_lanes.lanes.{record_id}"
    _require_no_forbidden_id_fields(record, context=context)
    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "capacity",
                "default_timeout_seconds",
                "claim_ttl_seconds",
                "heartbeat_interval_seconds",
            }
        ),
        context=context,
    )
    claim_ttl_seconds = _require_positive_float_field(
        record,
        field_name="claim_ttl_seconds",
        context=context,
    )
    heartbeat_interval_seconds = _require_positive_float_field(
        record,
        field_name="heartbeat_interval_seconds",
        context=context,
    )
    if claim_ttl_seconds <= heartbeat_interval_seconds:
        raise ConfigFieldError(
            f"{context}.claim_ttl_seconds must be greater than heartbeat_interval_seconds"
        )
    return RuntimeLaneConfig(
        lane_name=record_id,
        capacity=_require_positive_int_field(record, field_name="capacity", context=context),
        default_timeout_seconds=_optional_positive_float_field(record, field_name="default_timeout_seconds", context=context),
        claim_ttl_seconds=claim_ttl_seconds,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )


def _parse_tool_discovery_provider(
    *, record_id: str, record: JsonObject
) -> ToolDiscoveryProviderConfig:
    """解析单个工具发现 provider spec。

    :param record_id: provider id。
    :param record: 继承解析后的 provider 记录。
    :returns: 工具发现 provider typed config。
    :raises ConfigFieldError: 字段缺失、非法类型或出现重复 id 字段时抛出。
    """

    context = f"tool_discovery.providers.{record_id}"
    _require_no_forbidden_id_fields(record, context=context)
    _require_required_and_optional_fields(
        record,
        required=frozenset(
            {
                "import_path",
                "entry_point",
                "source_kind",
                "source_id",
                "enabled",
            }
        ),
        optional=frozenset({"config"}),
        context=context,
    )
    import_path = _optional_str_field(
        record,
        field_name=_IMPORT_PATH_FIELD,
        context=context,
    )
    entry_point = _optional_entry_point(
        record,
        field_name=_ENTRY_POINT_FIELD,
        context=context,
    )
    if (import_path is None) == (entry_point is None):
        raise ConfigFieldError(
            f"tool_discovery.providers.{record_id} must set exactly one of import_path or entry_point"
        )
    source_kind = _parse_tool_bundle_source_kind(
        _require_str_field(
            record,
            field_name="source_kind",
            context=context,
        ),
        context=f"{context}.source_kind",
    )
    return ToolDiscoveryProviderConfig(
        provider_id=record_id,
        import_path=import_path,
        entry_point=entry_point,
        source_kind=source_kind,
        source_id=_require_str_field(record, field_name="source_id", context=context),
        enabled=_require_bool_field(record, field_name="enabled", context=context),
        config=_optional_mapping_field(record, field_name="config", context=context),
    )


def _optional_mapping_field(
    record: JsonObject, *, field_name: str, context: str
) -> JsonObject:
    """读取可选 JSON object 字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字段 JSON object；缺失或 ``null`` 时返回空 mapping。
    :raises ConfigShapeError: 字段不是 JSON object 时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return {}
    return _require_json_object(
        record[field_name],
        context=f"{context}.{field_name}",
    )


def _require_required_and_optional_fields(
    record: JsonObject,
    *,
    required: frozenset[str],
    optional: frozenset[str],
    context: str,
) -> None:
    """校验必填字段存在并拒绝未知字段。

    :param record: 待校验 JSON object。
    :param required: 必填字段集合。
    :param optional: 可选字段集合。
    :param context: 错误消息上下文。
    :returns: 无返回值。
    :raises ConfigFieldError: 缺少必填字段或包含未知字段时抛出。
    """

    keys = frozenset(record.keys())
    missing = required - keys
    if missing:
        raise ConfigFieldError(f"{context} missing required fields: {sorted(missing)}")
    unknown = keys - required - optional
    if unknown:
        raise ConfigFieldError(f"{context} has unknown fields: {sorted(unknown)}")


def _optional_entry_point(
    record: JsonObject, *, field_name: str, context: str
) -> ToolDiscoveryEntryPointConfig | None:
    """解析可选 entry point 字段。

    :param record: provider 记录。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: entry point typed config；未配置时返回 ``None``。
    :raises ConfigFieldError: 字段 shape 或类型非法时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    value = _require_mapping_field(record, field_name=field_name, context=context)
    _require_exact_fields(
        value,
        allowed=frozenset({"group", "name"}),
        context=f"{context}.{field_name}",
    )
    return ToolDiscoveryEntryPointConfig(
        group=_require_str_field(value, field_name="group", context=f"{context}.{field_name}"),
        name=_require_str_field(value, field_name="name", context=f"{context}.{field_name}"),
    )


def _parse_tool_bundle_source_kind(
    value: str, *, context: str
) -> ToolBundleSourceKind:
    """解析工具来源类别。

    :param value: source kind 字符串。
    :param context: 错误消息上下文。
    :returns: ToolBundleSourceKind。
    :raises ConfigFieldError: source kind 非法或不适用于工具发现时抛出。
    """

    try:
        source_kind = ToolBundleSourceKind(value)
    except ValueError as exc:
        raise ConfigFieldError(f"{context} has unsupported source kind: {value}") from exc
    if source_kind not in _TOOL_DISCOVERY_SOURCE_KINDS:
        raise ConfigFieldError(f"{context} is not valid for tool discovery provider")
    return source_kind


def _validate_execution_model_references(
    *,
    execution_profiles: ExecutionProfilesConfig,
    models: ModelsConfig,
) -> None:
    """校验 execution config 中的 model id 与 hint id 引用。

    :param execution_profiles: execution profiles typed config。
    :param models: 模型目录 typed config。
    :returns: 无返回值。
    :raises ConfigFieldError: 模型或 hint 引用不存在时抛出。
    """

    for profile_id, profile in execution_profiles.execution_profiles.items():
        _validate_baseline_model_reference(
            baseline=profile.run_baseline,
            models=models,
            context=f"execution_profiles.execution_profiles.{profile_id}.run_baseline",
        )
        compactor_as_baseline = ExecutionBaselineConfig(
            model_id=profile.compactor_baseline.model_id,
            runner_option_hint_id=profile.compactor_baseline.runner_option_hint_id,
        )
        _validate_baseline_model_reference(
            baseline=compactor_as_baseline,
            models=models,
            context=f"execution_profiles.execution_profiles.{profile_id}.compactor_baseline",
        )


def _validate_baseline_model_reference(
    *, baseline: ExecutionBaselineConfig, models: ModelsConfig, context: str
) -> None:
    """校验单个 baseline 的模型与 runner option hint 引用。

    :param baseline: 待校验 baseline。
    :param models: 模型目录 typed config。
    :param context: 错误消息上下文。
    :returns: 无返回值。
    :raises ConfigFieldError: 模型或 hint 引用不存在时抛出。
    """

    _require_mapping_contains(
        models.models,
        key=baseline.model_id,
        context=f"{context}.model_id",
    )
    model = models.models[baseline.model_id]
    _require_mapping_contains(
        model.runtime_hints.runner_option_hints,
        key=baseline.runner_option_hint_id,
        context=f"{context}.runner_option_hint_id",
    )


def _validate_host_runtime_lane_references(
    *, host_runtime: HostRuntimeConfig, runtime_lanes: RuntimeLanesConfig
) -> None:
    """校验 Host runtime 引用的 lane 已存在。

    :param host_runtime: Host runtime typed config。
    :param runtime_lanes: runtime lanes typed config。
    :returns: 无返回值。
    :raises ConfigFieldError: lane 引用不存在时抛出。
    """

    for runtime_id, runtime in host_runtime.runtimes.items():
        _require_mapping_contains(
            runtime_lanes.lanes,
            key=runtime.host_execution_lane_name,
            context=f"host_runtime.runtimes.{runtime_id}.host_execution_lane_name",
        )


def _require_exact_fields(
    record: JsonObject, *, allowed: frozenset[str], context: str
) -> None:
    """校验记录不包含未知字段且必填字段齐全。

    :param record: 待校验 JSON object。
    :param allowed: 允许字段集合。
    :param context: 错误消息上下文。
    :returns: 无返回值。
    :raises ConfigFieldError: 缺字段或包含未知字段时抛出。
    """

    keys = frozenset(record.keys())
    missing = allowed - keys
    if missing:
        raise ConfigFieldError(f"{context} missing required fields: {sorted(missing)}")
    unknown = keys - allowed
    if unknown:
        raise ConfigFieldError(f"{context} has unknown fields: {sorted(unknown)}")


def _require_no_forbidden_id_fields(record: JsonObject, *, context: str) -> None:
    """校验 catalog record 内不重复存储 id 字段。

    :param record: 待校验 JSON object。
    :param context: 错误消息上下文。
    :returns: 无返回值。
    :raises ConfigFieldError: 出现重复 id 字段时抛出。
    """

    forbidden = frozenset(record.keys()) & _FORBIDDEN_RECORD_ID_FIELDS
    if forbidden:
        raise ConfigFieldError(
            f"{context} must not contain embedded id fields: {sorted(forbidden)}"
        )


def _require_mapping_contains(
    values: Container[str],
    *,
    key: str,
    context: str,
) -> None:
    """校验容器中存在指定 key。

    :param values: 待校验容器。
    :param key: 必须存在的 key。
    :param context: 错误消息上下文。
    :returns: 无返回值。
    :raises ConfigFieldError: key 不存在时抛出。
    """

    if key not in values:
        raise ConfigFieldError(f"{context} references unknown id: {key}")


def _require_json_object(value: JsonValue, *, context: str) -> JsonObject:
    """校验 JSON 值是 object。

    :param value: 待校验 JSON 值。
    :param context: 错误消息上下文。
    :returns: JSON object。
    :raises ConfigShapeError: 值不是 JSON object 时抛出。
    """

    if not isinstance(value, Mapping):
        raise ConfigShapeError(f"{context} must be a JSON object")
    for key in value:
        if not isinstance(key, str):
            raise ConfigShapeError(f"{context} object key must be string")
    return value


def _require_field(record: JsonObject, *, field_name: str, context: str) -> JsonValue:
    """读取必填 JSON 字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字段 JSON 值。
    :raises ConfigFieldError: 字段缺失时抛出。
    """

    if field_name not in record:
        raise ConfigFieldError(f"{context}.{field_name} is required")
    return record[field_name]


def _require_mapping_field(
    record: JsonObject, *, field_name: str, context: str
) -> JsonObject:
    """读取必填 JSON object 字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字段 JSON object。
    :raises ConfigFieldError: 字段缺失时抛出。
    :raises ConfigShapeError: 字段不是 JSON object 时抛出。
    """

    return _require_json_object(
        _require_field(record, field_name=field_name, context=context),
        context=f"{context}.{field_name}",
    )


def _require_str_mapping_field(
    record: JsonObject, *, field_name: str, context: str
) -> Mapping[str, str]:
    """读取字符串到字符串的映射字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字符串映射。
    :raises ConfigFieldError: 字段缺失或值不是字符串时抛出。
    """

    raw = _require_mapping_field(record, field_name=field_name, context=context)
    result: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(value, str):
            raise ConfigFieldError(f"{context}.{field_name}.{key} must be a string")
        result[key] = value
    return result


def _parse_non_empty_str_mapping(
    record: JsonObject, *, context: str
) -> Mapping[str, str]:
    """解析非空字符串 key/value 映射。

    :param record: JSON object。
    :param context: 错误消息上下文。
    :returns: 非空字符串 key/value 映射。
    :raises ConfigFieldError: key 或 value 为空、value 不是字符串时抛出。
    """

    result: dict[str, str] = {}
    for key, value in record.items():
        if not key.strip():
            raise ConfigFieldError(f"{context} contains empty key")
        if not isinstance(value, str):
            raise ConfigFieldError(f"{context}.{key} must be a string")
        if not value.strip():
            raise ConfigFieldError(f"{context}.{key} must be non-empty")
        result[key] = value
    return result


def _require_str_field(record: JsonObject, *, field_name: str, context: str) -> str:
    """读取必填字符串字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字符串字段值。
    :raises ConfigFieldError: 字段缺失、不是字符串或为空时抛出。
    """

    value = _require_field(record, field_name=field_name, context=context)
    if not isinstance(value, str):
        raise ConfigFieldError(f"{context}.{field_name} must be a string")
    if not value.strip():
        raise ConfigFieldError(f"{context}.{field_name} must be non-empty")
    return value


def _optional_str_field(
    record: JsonObject, *, field_name: str, context: str
) -> str | None:
    """读取可选字符串字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字符串字段值；缺失或 ``null`` 时返回 ``None``。
    :raises ConfigFieldError: 字段存在但不是字符串或为空时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    return _require_str_field(record, field_name=field_name, context=context)


def _require_bool_field(record: JsonObject, *, field_name: str, context: str) -> bool:
    """读取必填 bool 字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: bool 字段值。
    :raises ConfigFieldError: 字段缺失或不是 bool 时抛出。
    """

    value = _require_field(record, field_name=field_name, context=context)
    if not isinstance(value, bool):
        raise ConfigFieldError(f"{context}.{field_name} must be a boolean")
    return value


def _require_float_field(
    record: JsonObject, *, field_name: str, context: str
) -> float:
    """读取必填数值字段并转为 float。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: float 字段值。
    :raises ConfigFieldError: 字段缺失、bool 或非数值时抛出。
    """

    value = _require_field(record, field_name=field_name, context=context)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigFieldError(f"{context}.{field_name} must be a number")
    return float(value)


def _require_positive_float_field(
    record: JsonObject, *, field_name: str, context: str
) -> float:
    """读取必填正数值字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 正 float 字段值。
    :raises ConfigFieldError: 字段非正数时抛出。
    """

    value = _require_float_field(record, field_name=field_name, context=context)
    if value <= 0:
        raise ConfigFieldError(f"{context}.{field_name} must be > 0")
    return value


def _optional_positive_float_field(
    record: JsonObject, *, field_name: str, context: str
) -> float | None:
    """读取可选正数值字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 正 float 字段值；缺失或 ``null`` 时返回 ``None``。
    :raises ConfigFieldError: 字段存在但非正数时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    return _require_positive_float_field(record, field_name=field_name, context=context)


def _require_positive_int_field(
    record: JsonObject, *, field_name: str, context: str
) -> int:
    """读取必填正整数字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 正整数字段值。
    :raises ConfigFieldError: 字段缺失、不是整数或非正时抛出。
    """

    value = _require_int_field(record, field_name=field_name, context=context)
    if value <= 0:
        raise ConfigFieldError(f"{context}.{field_name} must be > 0")
    return value


def _require_non_negative_int_field(
    record: JsonObject, *, field_name: str, context: str
) -> int:
    """读取必填非负整数字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 非负整数字段值。
    :raises ConfigFieldError: 字段缺失、不是整数或为负时抛出。
    """

    value = _require_int_field(record, field_name=field_name, context=context)
    if value < 0:
        raise ConfigFieldError(f"{context}.{field_name} must be >= 0")
    return value


def _require_int_field(record: JsonObject, *, field_name: str, context: str) -> int:
    """读取必填整数字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 整数字段值。
    :raises ConfigFieldError: 字段缺失、bool 或非整数时抛出。
    """

    value = _require_field(record, field_name=field_name, context=context)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigFieldError(f"{context}.{field_name} must be an integer")
    return value
