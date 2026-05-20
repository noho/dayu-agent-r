"""层中立运行时配置加载器。

本模块只负责读取 ``dayu/config`` 默认配置与调用方显式传入的 workspace
配置目录，执行按文件类型的 overlay、单继承解析与强类型校验，然后输出
层中立 typed config view。它不构造 Host，不创建 provider client，不解释
scene manifest，不读取财报仓储，也不 import 业务层。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final, TypeAlias, cast

from dayu.contracts import JsonValue, ToolBundleSourceKind

_MODELS_FILE: Final[str] = "models.json"
_EXECUTION_PROFILES_FILE: Final[str] = "execution_profiles.json"
_HOST_RUNTIME_FILE: Final[str] = "host_runtime.json"
_TOOL_DISCOVERY_FILE: Final[str] = "tool_discovery.json"
_LEGACY_CONFIG_FILES: Final[frozenset[str]] = frozenset(
    {"llm_models.json", "run.json"}
)
_CONFIG_FILE_NAMES: Final[tuple[str, ...]] = (
    _MODELS_FILE,
    _EXECUTION_PROFILES_FILE,
    _HOST_RUNTIME_FILE,
    _TOOL_DISCOVERY_FILE,
)
_EXTENDS_FIELD: Final[str] = "extends"
_IMPORT_PATH_FIELD: Final[str] = "import_path"
_ENTRY_POINT_FIELD: Final[str] = "entry_point"
_CONFIG_ROOT: Final[Path] = Path(__file__).resolve().parents[1] / "config"
_TOOL_DISCOVERY_SOURCE_KINDS: Final[frozenset[ToolBundleSourceKind]] = frozenset(
    {
        ToolBundleSourceKind.EXPLICIT_PROVIDER,
        ToolBundleSourceKind.CONFIG_BINDING,
        ToolBundleSourceKind.PACKAGE_ENTRYPOINT,
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
class ModelConfig:
    """模型目录中的单个模型配置。

    :param model_id: 模型配置稳定标识。
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


@dataclass(frozen=True, slots=True)
class ModelsConfig:
    """模型目录配置视图。

    :param models: 按 ``model_id`` 索引的模型配置。
    """

    models: Mapping[str, ModelConfig]


@dataclass(frozen=True, slots=True)
class OrdinaryExecutionConfig:
    """普通 Run 执行基线配置。

    :param model_id: 默认普通 Run 模型 id。
    :param runner_options_profile_id: Runner options profile id。
    :param agent_policy_profile_id: Agent policy profile id。
    """

    model_id: str
    runner_options_profile_id: str
    agent_policy_profile_id: str


@dataclass(frozen=True, slots=True)
class CompactorExecutionConfig:
    """Host-owned compactor 执行基线配置。

    :param model_id: compactor 模型 id。
    :param runner_options_profile_id: compactor runner options profile id。
    :param artifact_root: compact artifact 根目录。
    """

    model_id: str
    runner_options_profile_id: str
    artifact_root: str


@dataclass(frozen=True, slots=True)
class ContextBudgetConfig:
    """上下文预算配置。

    :param max_context_tokens: 最大上下文 token 数。
    :param reserved_response_tokens: 预留响应 token 数。
    :param compaction_trigger_tokens: 触发 compaction 的 token 阈值。
    """

    max_context_tokens: int
    reserved_response_tokens: int
    compaction_trigger_tokens: int


@dataclass(frozen=True, slots=True)
class MemoryProjectionConfig:
    """Conversation memory projection 配置。

    :param enabled: 是否启用 memory projection。
    :param stable_layer_max_items: stable layer 最大条目数。
    :param history_pool_max_items: history pool 最大条目数。
    """

    enabled: bool
    stable_layer_max_items: int
    history_pool_max_items: int


@dataclass(frozen=True, slots=True)
class TruncationConfig:
    """工具截断治理配置。

    :param enabled: 是否启用截断治理。
    :param default_max_chars: 默认最大字符数。
    :param fetch_more_tool_name: fetch-more framework 工具名。
    """

    enabled: bool
    default_max_chars: int
    fetch_more_tool_name: str


@dataclass(frozen=True, slots=True)
class ExecutionProfileConfig:
    """单个 execution profile 的完整配置。

    :param profile_id: execution profile 稳定标识。
    :param ordinary: 普通 Run 执行基线。
    :param compactor: compactor 执行基线。
    :param context_budget: 上下文预算基线。
    :param memory_projection: memory projection 基线。
    :param truncation: 截断治理基线。
    """

    profile_id: str
    ordinary: OrdinaryExecutionConfig
    compactor: CompactorExecutionConfig
    context_budget: ContextBudgetConfig
    memory_projection: MemoryProjectionConfig
    truncation: TruncationConfig


@dataclass(frozen=True, slots=True)
class RunnerOptionsProfileConfig:
    """Runner 调用参数 profile。

    :param temperature: temperature 参数。
    :param max_tokens: 最大输出 token 数。
    :param top_p: top-p 参数。
    :param stream: 是否使用流式输出。
    """

    temperature: float
    max_tokens: int
    top_p: float
    stream: bool


@dataclass(frozen=True, slots=True)
class AgentPolicyProfileConfig:
    """Agent policy profile。

    :param max_iterations: 最大 agent loop 迭代数。
    :param continuation_attempts: 长输出 continuation 次数。
    :param tool_execution_timeout_seconds: 工具执行等待超时秒数。
    :param fallback_mode: fallback 模式。
    :param fallback_prompt: fallback prompt。
    :param continuation_prompt: continuation prompt。
    :param consecutive_failed_tool_batches: 连续失败工具批次阈值。
    """

    max_iterations: int
    continuation_attempts: int
    tool_execution_timeout_seconds: float
    fallback_mode: str
    fallback_prompt: str
    continuation_prompt: str
    consecutive_failed_tool_batches: int


@dataclass(frozen=True, slots=True)
class RunnerHintConfig:
    """scene runtime runner hint 可覆盖字段。

    :param model_id: 可选模型 id 覆盖。
    :param runner_options_profile_id: 可选 runner options profile 覆盖。
    :param temperature: 可选 temperature 覆盖。
    :param max_tokens: 可选最大输出 token 覆盖。
    :param top_p: 可选 top-p 覆盖。
    :param stream: 可选流式输出覆盖。
    """

    model_id: str | None
    runner_options_profile_id: str | None
    temperature: float | None
    max_tokens: int | None
    top_p: float | None
    stream: bool | None


@dataclass(frozen=True, slots=True)
class AgentHintConfig:
    """scene runtime agent hint 可覆盖字段。

    :param agent_policy_profile_id: 可选 agent policy profile 覆盖。
    :param max_iterations: 可选最大迭代数覆盖。
    :param continuation_attempts: 可选 continuation 次数覆盖。
    :param tool_execution_timeout_seconds: 可选工具超时覆盖。
    :param fallback_mode: 可选 fallback 模式覆盖。
    :param fallback_prompt: 可选 fallback prompt 覆盖。
    :param continuation_prompt: 可选 continuation prompt 覆盖。
    :param consecutive_failed_tool_batches: 可选连续失败工具批次阈值覆盖。
    """

    agent_policy_profile_id: str | None
    max_iterations: int | None
    continuation_attempts: int | None
    tool_execution_timeout_seconds: float | None
    fallback_mode: str | None
    fallback_prompt: str | None
    continuation_prompt: str | None
    consecutive_failed_tool_batches: int | None


@dataclass(frozen=True, slots=True)
class ExecutionProfilesConfig:
    """执行 profiles 配置视图。

    :param default_profile_id: 默认 execution profile id。
    :param profiles: 完整 execution profiles。
    :param runner_options_profiles: Runner options profiles。
    :param agent_policy_profiles: Agent policy profiles。
    :param runner_hints: runner hints 可覆盖字段集合。
    :param agent_hints: agent hints 可覆盖字段集合。
    """

    default_profile_id: str
    profiles: Mapping[str, ExecutionProfileConfig]
    runner_options_profiles: Mapping[str, RunnerOptionsProfileConfig]
    agent_policy_profiles: Mapping[str, AgentPolicyProfileConfig]
    runner_hints: Mapping[str, RunnerHintConfig]
    agent_hints: Mapping[str, AgentHintConfig]


@dataclass(frozen=True, slots=True)
class SQLiteRuntimeConfig:
    """Host opener SQLite 默认配置。

    :param path: SQLite 数据库路径。
    :param busy_timeout_seconds: SQLite busy timeout 秒数。
    """

    path: str
    busy_timeout_seconds: float


@dataclass(frozen=True, slots=True)
class LaneCapacityConfig:
    """单个 runtime lane 容量配置。

    :param capacity: lane 容量。
    :param claim_ttl_seconds: claim TTL 秒数。
    :param heartbeat_interval_seconds: heartbeat 间隔秒数。
    """

    capacity: int
    claim_ttl_seconds: float
    heartbeat_interval_seconds: float


@dataclass(frozen=True, slots=True)
class LaneRuntimeConfig:
    """Host opener runtime lane 默认配置。

    :param db_path: runtime lane SQLite DB 路径。
    :param default_lane_name: 默认 lane 名。
    :param lanes: 按 lane 名索引的容量配置。
    """

    db_path: str
    default_lane_name: str
    lanes: Mapping[str, LaneCapacityConfig]


@dataclass(frozen=True, slots=True)
class HostRuntimeProfileConfig:
    """Host opener 部署默认值配置。

    :param runtime_id: runtime profile 稳定标识。
    :param store_root: Host durable store 根目录。
    :param artifact_root: Host artifact 根目录。
    :param sqlite: SQLite 默认配置。
    :param lane: runtime lane 默认配置。
    :param worker_factory_kind: worker factory 类别。
    :param dispatch_poll_interval_seconds: dispatch 轮询间隔秒数。
    :param memory_projection_catch_up_batch_size: memory catch-up 批次大小。
    :param truncation_manager_enabled: 是否启用 truncation manager。
    :param prompt_asset_root: prompt asset 根目录。
    :param scene_manifest_root: scene manifest 根目录。
    """

    runtime_id: str
    store_root: str
    artifact_root: str
    sqlite: SQLiteRuntimeConfig
    lane: LaneRuntimeConfig
    worker_factory_kind: str
    dispatch_poll_interval_seconds: float
    memory_projection_catch_up_batch_size: int
    truncation_manager_enabled: bool
    prompt_asset_root: str
    scene_manifest_root: str


@dataclass(frozen=True, slots=True)
class HostRuntimeConfig:
    """Host runtime 配置视图。

    :param default_runtime_id: 默认 Host runtime profile id。
    :param runtimes: 按 id 索引的 Host runtime profiles。
    """

    default_runtime_id: str
    runtimes: Mapping[str, HostRuntimeProfileConfig]


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

    :param provider_id: provider spec 稳定标识。
    :param import_path: 显式 ``module:attribute`` import path；与
        ``entry_point`` 二选一。
    :param entry_point: package entry point；与 ``import_path`` 二选一。
    :param source_kind: 来源类别。
    :param source_id: 来源标识。
    :param enabled: 是否启用 provider。
    :param allow_empty: 是否允许 provider 返回空工具集合。
    """

    provider_id: str
    import_path: str | None
    entry_point: ToolDiscoveryEntryPointConfig | None
    source_kind: ToolBundleSourceKind
    source_id: str
    enabled: bool
    allow_empty: bool


@dataclass(frozen=True, slots=True)
class ToolDiscoveryConfig:
    """工具发现 provider specs 配置视图。

    :param providers: 按 provider id 索引的 provider specs。
    """

    providers: Mapping[str, ToolDiscoveryProviderConfig]


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """四类 runtime assembly 配置总视图。

    :param models: 模型目录配置。
    :param execution_profiles: execution profiles 配置。
    :param host_runtime: Host runtime 配置。
    :param tool_discovery: 工具发现配置。
    """

    models: ModelsConfig
    execution_profiles: ExecutionProfilesConfig
    host_runtime: HostRuntimeConfig
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
        """加载四类配置并返回总视图。

        :param workspace_config_dir: 调用方显式提供的 workspace 覆盖配置目录；
            ``None`` 表示只读取包内默认配置。
        :returns: 四类 runtime assembly typed config view。
        :raises ConfigLoadError: 配置文件缺失、JSON shape、继承或字段校验失败
            时抛出。
        """

        models = self.load_models(workspace_config_dir=workspace_config_dir)
        execution_profiles = self.load_execution_profiles(
            workspace_config_dir=workspace_config_dir
        )
        host_runtime = self.load_host_runtime(workspace_config_dir=workspace_config_dir)
        tool_discovery = self.load_tool_discovery(
            workspace_config_dir=workspace_config_dir
        )
        _validate_execution_model_references(
            execution_profiles=execution_profiles,
            models=models,
        )
        return RuntimeConfig(
            models=models,
            execution_profiles=execution_profiles,
            host_runtime=host_runtime,
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
            map_fields=frozenset(
                {
                    "profiles",
                    "runner_options_profiles",
                    "agent_policy_profiles",
                    "runner_hints",
                    "agent_hints",
                }
            ),
        )
        profiles = _parse_execution_profile_map(root)
        runner_options_profiles = _parse_runner_options_profile_map(root)
        agent_policy_profiles = _parse_agent_policy_profile_map(root)
        runner_hints = _parse_runner_hint_map(root)
        agent_hints = _parse_agent_hint_map(root)
        default_profile_id = _require_str_field(
            root,
            field_name="default_profile_id",
            context=_EXECUTION_PROFILES_FILE,
        )
        _require_mapping_contains(
            profiles,
            key=default_profile_id,
            context="execution_profiles.default_profile_id",
        )
        _validate_execution_profile_references(
            profiles=profiles,
            runner_options_profiles=runner_options_profiles,
            agent_policy_profiles=agent_policy_profiles,
        )
        _validate_hint_references(
            runner_hints=runner_hints,
            agent_hints=agent_hints,
            runner_options_profiles=runner_options_profiles,
            agent_policy_profiles=agent_policy_profiles,
        )
        return ExecutionProfilesConfig(
            default_profile_id=default_profile_id,
            profiles=profiles,
            runner_options_profiles=runner_options_profiles,
            agent_policy_profiles=agent_policy_profiles,
            runner_hints=runner_hints,
            agent_hints=agent_hints,
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
        default_runtime_id = _require_str_field(
            root,
            field_name="default_runtime_id",
            context=_HOST_RUNTIME_FILE,
        )
        _require_mapping_contains(
            runtimes,
            key=default_runtime_id,
            context="host_runtime.default_runtime_id",
        )
        return HostRuntimeConfig(
            default_runtime_id=default_runtime_id,
            runtimes=runtimes,
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
        return ToolDiscoveryConfig(providers=providers)


def load_runtime_config(workspace_config_dir: Path | None = None) -> RuntimeConfig:
    """使用默认加载器加载 runtime assembly 配置。

    :param workspace_config_dir: 调用方显式提供的 workspace 覆盖配置目录。
    :returns: 四类 runtime assembly typed config view。
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
    :raises ConfigExtendsError: 继承循环、多继承或父项缺失时抛出。
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
    :raises ConfigExtendsError: 继承循环、多继承或父项缺失时抛出。
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
    :raises ConfigFieldError: 字段缺失、非法类型或 id 不一致时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "model_id",
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
            }
        ),
        context=f"models.{record_id}",
    )
    model_id = _require_str_field(record, field_name="model_id", context=f"models.{record_id}")
    _require_id_match(record_id=record_id, embedded_id=model_id, context="models")
    return ModelConfig(
        model_id=model_id,
        runner_kind=_parse_runner_kind(
            _require_str_field(record, field_name="runner_kind", context=f"models.{record_id}"),
            context=f"models.{record_id}.runner_kind",
        ),
        provider=_require_str_field(record, field_name="provider", context=f"models.{record_id}"),
        model=_require_str_field(record, field_name="model", context=f"models.{record_id}"),
        endpoint=_require_str_field(record, field_name="endpoint", context=f"models.{record_id}"),
        api_key_ref=_optional_str_field(record, field_name="api_key_ref", context=f"models.{record_id}"),
        headers=_require_str_mapping_field(record, field_name="headers", context=f"models.{record_id}"),
        supports_tool_calling=_require_bool_field(record, field_name="supports_tool_calling", context=f"models.{record_id}"),
        supports_stream=_require_bool_field(record, field_name="supports_stream", context=f"models.{record_id}"),
        supports_stream_usage=_require_bool_field(record, field_name="supports_stream_usage", context=f"models.{record_id}"),
        default_timeout_seconds=_require_positive_float_field(record, field_name="default_timeout_seconds", context=f"models.{record_id}"),
        max_retries=_require_non_negative_int_field(record, field_name="max_retries", context=f"models.{record_id}"),
        sse_idle_timeout_seconds=_require_positive_float_field(record, field_name="sse_idle_timeout_seconds", context=f"models.{record_id}"),
        sse_heartbeat_seconds=_require_positive_float_field(record, field_name="sse_heartbeat_seconds", context=f"models.{record_id}"),
        provider_request_extension=_require_field(record, field_name="provider_request_extension", context=f"models.{record_id}"),
        context_window_tokens=_require_positive_int_field(record, field_name="context_window_tokens", context=f"models.{record_id}"),
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


def _parse_execution_profile_map(root: JsonObject) -> Mapping[str, ExecutionProfileConfig]:
    """解析 execution profile map。

    :param root: execution_profiles.json 顶层 object。
    :returns: execution profile map。
    :raises ConfigLoadError: 记录继承或字段校验失败时抛出。
    """

    records = _resolve_record_map(
        _require_mapping_field(root, field_name="profiles", context=_EXECUTION_PROFILES_FILE),
        context="execution_profiles.profiles",
    )
    profiles: dict[str, ExecutionProfileConfig] = {}
    for profile_id, record in records.items():
        profiles[profile_id] = _parse_execution_profile(
            record_id=profile_id,
            record=record,
        )
    if not profiles:
        raise ConfigFieldError("execution_profiles profiles must not be empty")
    return profiles


def _parse_execution_profile(
    *, record_id: str, record: JsonObject
) -> ExecutionProfileConfig:
    """解析单个 execution profile。

    :param record_id: profile id。
    :param record: 继承解析后的 profile 记录。
    :returns: execution profile typed config。
    :raises ConfigFieldError: 字段缺失、非法类型或 id 不一致时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "profile_id",
                "ordinary",
                "compactor",
                "context_budget",
                "memory_projection",
                "truncation",
            }
        ),
        context=f"execution_profiles.profiles.{record_id}",
    )
    profile_id = _require_str_field(
        record,
        field_name="profile_id",
        context=f"execution_profiles.profiles.{record_id}",
    )
    _require_id_match(
        record_id=record_id,
        embedded_id=profile_id,
        context="execution_profiles.profiles",
    )
    return ExecutionProfileConfig(
        profile_id=profile_id,
        ordinary=_parse_ordinary_execution(
            _require_mapping_field(
                record,
                field_name="ordinary",
                context=f"execution_profiles.profiles.{record_id}",
            ),
            context=f"execution_profiles.profiles.{record_id}.ordinary",
        ),
        compactor=_parse_compactor_execution(
            _require_mapping_field(
                record,
                field_name="compactor",
                context=f"execution_profiles.profiles.{record_id}",
            ),
            context=f"execution_profiles.profiles.{record_id}.compactor",
        ),
        context_budget=_parse_context_budget(
            _require_mapping_field(
                record,
                field_name="context_budget",
                context=f"execution_profiles.profiles.{record_id}",
            ),
            context=f"execution_profiles.profiles.{record_id}.context_budget",
        ),
        memory_projection=_parse_memory_projection(
            _require_mapping_field(
                record,
                field_name="memory_projection",
                context=f"execution_profiles.profiles.{record_id}",
            ),
            context=f"execution_profiles.profiles.{record_id}.memory_projection",
        ),
        truncation=_parse_truncation(
            _require_mapping_field(
                record,
                field_name="truncation",
                context=f"execution_profiles.profiles.{record_id}",
            ),
            context=f"execution_profiles.profiles.{record_id}.truncation",
        ),
    )


def _parse_ordinary_execution(
    record: JsonObject, *, context: str
) -> OrdinaryExecutionConfig:
    """解析普通 Run 执行基线。

    :param record: ordinary 记录。
    :param context: 错误消息上下文。
    :returns: ordinary typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset({"model_id", "runner_options_profile_id", "agent_policy_profile_id"}),
        context=context,
    )
    return OrdinaryExecutionConfig(
        model_id=_require_str_field(record, field_name="model_id", context=context),
        runner_options_profile_id=_require_str_field(record, field_name="runner_options_profile_id", context=context),
        agent_policy_profile_id=_require_str_field(record, field_name="agent_policy_profile_id", context=context),
    )


def _parse_compactor_execution(
    record: JsonObject, *, context: str
) -> CompactorExecutionConfig:
    """解析 compactor 执行基线。

    :param record: compactor 记录。
    :param context: 错误消息上下文。
    :returns: compactor typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset({"model_id", "runner_options_profile_id", "artifact_root"}),
        context=context,
    )
    return CompactorExecutionConfig(
        model_id=_require_str_field(record, field_name="model_id", context=context),
        runner_options_profile_id=_require_str_field(record, field_name="runner_options_profile_id", context=context),
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
            {"max_context_tokens", "reserved_response_tokens", "compaction_trigger_tokens"}
        ),
        context=context,
    )
    return ContextBudgetConfig(
        max_context_tokens=_require_positive_int_field(record, field_name="max_context_tokens", context=context),
        reserved_response_tokens=_require_positive_int_field(record, field_name="reserved_response_tokens", context=context),
        compaction_trigger_tokens=_require_positive_int_field(record, field_name="compaction_trigger_tokens", context=context),
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
            {"enabled", "stable_layer_max_items", "history_pool_max_items"}
        ),
        context=context,
    )
    return MemoryProjectionConfig(
        enabled=_require_bool_field(record, field_name="enabled", context=context),
        stable_layer_max_items=_require_positive_int_field(record, field_name="stable_layer_max_items", context=context),
        history_pool_max_items=_require_positive_int_field(record, field_name="history_pool_max_items", context=context),
    )


def _parse_truncation(record: JsonObject, *, context: str) -> TruncationConfig:
    """解析 truncation 配置。

    :param record: truncation 记录。
    :param context: 错误消息上下文。
    :returns: truncation typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset({"enabled", "default_max_chars", "fetch_more_tool_name"}),
        context=context,
    )
    return TruncationConfig(
        enabled=_require_bool_field(record, field_name="enabled", context=context),
        default_max_chars=_require_positive_int_field(record, field_name="default_max_chars", context=context),
        fetch_more_tool_name=_require_str_field(record, field_name="fetch_more_tool_name", context=context),
    )


def _parse_runner_options_profile_map(
    root: JsonObject,
) -> Mapping[str, RunnerOptionsProfileConfig]:
    """解析 runner options profiles。

    :param root: execution_profiles.json 顶层 object。
    :returns: runner options profile map。
    :raises ConfigLoadError: 记录继承或字段校验失败时抛出。
    """

    records = _resolve_record_map(
        _require_mapping_field(
            root,
            field_name="runner_options_profiles",
            context=_EXECUTION_PROFILES_FILE,
        ),
        context="execution_profiles.runner_options_profiles",
    )
    profiles: dict[str, RunnerOptionsProfileConfig] = {}
    for profile_id, record in records.items():
        profiles[profile_id] = _parse_runner_options_profile(
            record,
            context=f"execution_profiles.runner_options_profiles.{profile_id}",
        )
    return profiles


def _parse_runner_options_profile(
    record: JsonObject, *, context: str
) -> RunnerOptionsProfileConfig:
    """解析单个 runner options profile。

    :param record: runner options profile 记录。
    :param context: 错误消息上下文。
    :returns: runner options profile typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset({"temperature", "max_tokens", "top_p", "stream"}),
        context=context,
    )
    return RunnerOptionsProfileConfig(
        temperature=_require_float_field(record, field_name="temperature", context=context),
        max_tokens=_require_positive_int_field(record, field_name="max_tokens", context=context),
        top_p=_require_float_field(record, field_name="top_p", context=context),
        stream=_require_bool_field(record, field_name="stream", context=context),
    )


def _parse_agent_policy_profile_map(
    root: JsonObject,
) -> Mapping[str, AgentPolicyProfileConfig]:
    """解析 agent policy profiles。

    :param root: execution_profiles.json 顶层 object。
    :returns: agent policy profile map。
    :raises ConfigLoadError: 记录继承或字段校验失败时抛出。
    """

    records = _resolve_record_map(
        _require_mapping_field(
            root,
            field_name="agent_policy_profiles",
            context=_EXECUTION_PROFILES_FILE,
        ),
        context="execution_profiles.agent_policy_profiles",
    )
    profiles: dict[str, AgentPolicyProfileConfig] = {}
    for profile_id, record in records.items():
        profiles[profile_id] = _parse_agent_policy_profile(
            record,
            context=f"execution_profiles.agent_policy_profiles.{profile_id}",
        )
    return profiles


def _parse_agent_policy_profile(
    record: JsonObject, *, context: str
) -> AgentPolicyProfileConfig:
    """解析单个 agent policy profile。

    :param record: agent policy profile 记录。
    :param context: 错误消息上下文。
    :returns: agent policy profile typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "max_iterations",
                "continuation_attempts",
                "tool_execution_timeout_seconds",
                "fallback_mode",
                "fallback_prompt",
                "continuation_prompt",
                "consecutive_failed_tool_batches",
            }
        ),
        context=context,
    )
    return AgentPolicyProfileConfig(
        max_iterations=_require_positive_int_field(record, field_name="max_iterations", context=context),
        continuation_attempts=_require_non_negative_int_field(record, field_name="continuation_attempts", context=context),
        tool_execution_timeout_seconds=_require_positive_float_field(record, field_name="tool_execution_timeout_seconds", context=context),
        fallback_mode=_require_str_field(record, field_name="fallback_mode", context=context),
        fallback_prompt=_require_str_field(record, field_name="fallback_prompt", context=context),
        continuation_prompt=_require_str_field(record, field_name="continuation_prompt", context=context),
        consecutive_failed_tool_batches=_require_positive_int_field(record, field_name="consecutive_failed_tool_batches", context=context),
    )


def _parse_runner_hint_map(root: JsonObject) -> Mapping[str, RunnerHintConfig]:
    """解析 runner hints。

    :param root: execution_profiles.json 顶层 object。
    :returns: runner hint map。
    :raises ConfigLoadError: 记录继承或字段校验失败时抛出。
    """

    records = _resolve_record_map(
        _require_mapping_field(root, field_name="runner_hints", context=_EXECUTION_PROFILES_FILE),
        context="execution_profiles.runner_hints",
    )
    hints: dict[str, RunnerHintConfig] = {}
    for hint_id, record in records.items():
        hints[hint_id] = _parse_runner_hint(
            record,
            context=f"execution_profiles.runner_hints.{hint_id}",
        )
    return hints


def _parse_runner_hint(record: JsonObject, *, context: str) -> RunnerHintConfig:
    """解析单个 runner hint。

    :param record: runner hint 记录。
    :param context: 错误消息上下文。
    :returns: runner hint typed config。
    :raises ConfigFieldError: 字段类型非法或包含未知字段时抛出。
    """

    _require_no_unknown_fields(
        record,
        allowed=frozenset(
            {
                "model_id",
                "runner_options_profile_id",
                "temperature",
                "max_tokens",
                "top_p",
                "stream",
            }
        ),
        context=context,
    )
    return RunnerHintConfig(
        model_id=_optional_str_field(record, field_name="model_id", context=context),
        runner_options_profile_id=_optional_str_field(record, field_name="runner_options_profile_id", context=context),
        temperature=_optional_float_field(record, field_name="temperature", context=context),
        max_tokens=_optional_positive_int_field(record, field_name="max_tokens", context=context),
        top_p=_optional_float_field(record, field_name="top_p", context=context),
        stream=_optional_bool_field(record, field_name="stream", context=context),
    )


def _parse_agent_hint_map(root: JsonObject) -> Mapping[str, AgentHintConfig]:
    """解析 agent hints。

    :param root: execution_profiles.json 顶层 object。
    :returns: agent hint map。
    :raises ConfigLoadError: 记录继承或字段校验失败时抛出。
    """

    records = _resolve_record_map(
        _require_mapping_field(root, field_name="agent_hints", context=_EXECUTION_PROFILES_FILE),
        context="execution_profiles.agent_hints",
    )
    hints: dict[str, AgentHintConfig] = {}
    for hint_id, record in records.items():
        hints[hint_id] = _parse_agent_hint(
            record,
            context=f"execution_profiles.agent_hints.{hint_id}",
        )
    return hints


def _parse_agent_hint(record: JsonObject, *, context: str) -> AgentHintConfig:
    """解析单个 agent hint。

    :param record: agent hint 记录。
    :param context: 错误消息上下文。
    :returns: agent hint typed config。
    :raises ConfigFieldError: 字段类型非法或包含未知字段时抛出。
    """

    _require_no_unknown_fields(
        record,
        allowed=frozenset(
            {
                "agent_policy_profile_id",
                "max_iterations",
                "continuation_attempts",
                "tool_execution_timeout_seconds",
                "fallback_mode",
                "fallback_prompt",
                "continuation_prompt",
                "consecutive_failed_tool_batches",
            }
        ),
        context=context,
    )
    return AgentHintConfig(
        agent_policy_profile_id=_optional_str_field(record, field_name="agent_policy_profile_id", context=context),
        max_iterations=_optional_positive_int_field(record, field_name="max_iterations", context=context),
        continuation_attempts=_optional_non_negative_int_field(record, field_name="continuation_attempts", context=context),
        tool_execution_timeout_seconds=_optional_positive_float_field(record, field_name="tool_execution_timeout_seconds", context=context),
        fallback_mode=_optional_str_field(record, field_name="fallback_mode", context=context),
        fallback_prompt=_optional_str_field(record, field_name="fallback_prompt", context=context),
        continuation_prompt=_optional_str_field(record, field_name="continuation_prompt", context=context),
        consecutive_failed_tool_batches=_optional_positive_int_field(record, field_name="consecutive_failed_tool_batches", context=context),
    )


def _parse_host_runtime_profile(
    *, record_id: str, record: JsonObject
) -> HostRuntimeProfileConfig:
    """解析单个 Host runtime profile。

    :param record_id: runtime profile id。
    :param record: 继承解析后的 runtime profile 记录。
    :returns: Host runtime profile typed config。
    :raises ConfigFieldError: 字段缺失、非法类型或 id 不一致时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "runtime_id",
                "store_root",
                "artifact_root",
                "sqlite",
                "lane",
                "worker_factory_kind",
                "dispatch_poll_interval_seconds",
                "memory_projection_catch_up_batch_size",
                "truncation_manager_enabled",
                "prompt_asset_root",
                "scene_manifest_root",
            }
        ),
        context=f"host_runtime.runtimes.{record_id}",
    )
    runtime_id = _require_str_field(
        record,
        field_name="runtime_id",
        context=f"host_runtime.runtimes.{record_id}",
    )
    _require_id_match(
        record_id=record_id,
        embedded_id=runtime_id,
        context="host_runtime.runtimes",
    )
    return HostRuntimeProfileConfig(
        runtime_id=runtime_id,
        store_root=_require_str_field(record, field_name="store_root", context=f"host_runtime.runtimes.{record_id}"),
        artifact_root=_require_str_field(record, field_name="artifact_root", context=f"host_runtime.runtimes.{record_id}"),
        sqlite=_parse_sqlite_runtime(
            _require_mapping_field(record, field_name="sqlite", context=f"host_runtime.runtimes.{record_id}"),
            context=f"host_runtime.runtimes.{record_id}.sqlite",
        ),
        lane=_parse_lane_runtime(
            _require_mapping_field(record, field_name="lane", context=f"host_runtime.runtimes.{record_id}"),
            context=f"host_runtime.runtimes.{record_id}.lane",
        ),
        worker_factory_kind=_require_str_field(record, field_name="worker_factory_kind", context=f"host_runtime.runtimes.{record_id}"),
        dispatch_poll_interval_seconds=_require_positive_float_field(record, field_name="dispatch_poll_interval_seconds", context=f"host_runtime.runtimes.{record_id}"),
        memory_projection_catch_up_batch_size=_require_positive_int_field(record, field_name="memory_projection_catch_up_batch_size", context=f"host_runtime.runtimes.{record_id}"),
        truncation_manager_enabled=_require_bool_field(record, field_name="truncation_manager_enabled", context=f"host_runtime.runtimes.{record_id}"),
        prompt_asset_root=_require_str_field(record, field_name="prompt_asset_root", context=f"host_runtime.runtimes.{record_id}"),
        scene_manifest_root=_require_str_field(record, field_name="scene_manifest_root", context=f"host_runtime.runtimes.{record_id}"),
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
        allowed=frozenset({"path", "busy_timeout_seconds"}),
        context=context,
    )
    return SQLiteRuntimeConfig(
        path=_require_str_field(record, field_name="path", context=context),
        busy_timeout_seconds=_require_positive_float_field(record, field_name="busy_timeout_seconds", context=context),
    )


def _parse_lane_runtime(record: JsonObject, *, context: str) -> LaneRuntimeConfig:
    """解析 runtime lane 配置。

    :param record: lane 配置记录。
    :param context: 错误消息上下文。
    :returns: lane runtime typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset({"db_path", "default_lane_name", "lanes"}),
        context=context,
    )
    lanes_root = _require_mapping_field(record, field_name="lanes", context=context)
    lanes: dict[str, LaneCapacityConfig] = {}
    for lane_name, value in lanes_root.items():
        lane_record = _require_json_object(value, context=f"{context}.lanes.{lane_name}")
        lanes[lane_name] = _parse_lane_capacity(
            lane_record,
            context=f"{context}.lanes.{lane_name}",
        )
    default_lane_name = _require_str_field(
        record,
        field_name="default_lane_name",
        context=context,
    )
    _require_mapping_contains(lanes, key=default_lane_name, context=f"{context}.default_lane_name")
    return LaneRuntimeConfig(
        db_path=_require_str_field(record, field_name="db_path", context=context),
        default_lane_name=default_lane_name,
        lanes=lanes,
    )


def _parse_lane_capacity(
    record: JsonObject, *, context: str
) -> LaneCapacityConfig:
    """解析单个 lane 容量配置。

    :param record: lane 容量记录。
    :param context: 错误消息上下文。
    :returns: lane 容量 typed config。
    :raises ConfigFieldError: 字段缺失或非法类型时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset(
            {"capacity", "claim_ttl_seconds", "heartbeat_interval_seconds"}
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
        raise ConfigFieldError(f"{context}.claim_ttl_seconds must be greater than heartbeat_interval_seconds")
    return LaneCapacityConfig(
        capacity=_require_positive_int_field(record, field_name="capacity", context=context),
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
    :raises ConfigFieldError: 字段缺失、非法类型或 id 不一致时抛出。
    """

    _require_exact_fields(
        record,
        allowed=frozenset(
            {
                "provider_id",
                "import_path",
                "entry_point",
                "source_kind",
                "source_id",
                "enabled",
                "allow_empty",
            }
        ),
        context=f"tool_discovery.providers.{record_id}",
    )
    provider_id = _require_str_field(
        record,
        field_name="provider_id",
        context=f"tool_discovery.providers.{record_id}",
    )
    _require_id_match(
        record_id=record_id,
        embedded_id=provider_id,
        context="tool_discovery.providers",
    )
    import_path = _optional_str_field(
        record,
        field_name=_IMPORT_PATH_FIELD,
        context=f"tool_discovery.providers.{record_id}",
    )
    entry_point = _optional_entry_point(
        record,
        field_name=_ENTRY_POINT_FIELD,
        context=f"tool_discovery.providers.{record_id}",
    )
    if (import_path is None) == (entry_point is None):
        raise ConfigFieldError(
            f"tool_discovery.providers.{record_id} must set exactly one of import_path or entry_point"
        )
    source_kind = _parse_tool_bundle_source_kind(
        _require_str_field(
            record,
            field_name="source_kind",
            context=f"tool_discovery.providers.{record_id}",
        ),
        context=f"tool_discovery.providers.{record_id}.source_kind",
    )
    return ToolDiscoveryProviderConfig(
        provider_id=provider_id,
        import_path=import_path,
        entry_point=entry_point,
        source_kind=source_kind,
        source_id=_require_str_field(record, field_name="source_id", context=f"tool_discovery.providers.{record_id}"),
        enabled=_require_bool_field(record, field_name="enabled", context=f"tool_discovery.providers.{record_id}"),
        allow_empty=_require_bool_field(record, field_name="allow_empty", context=f"tool_discovery.providers.{record_id}"),
    )


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


def _validate_execution_profile_references(
    *,
    profiles: Mapping[str, ExecutionProfileConfig],
    runner_options_profiles: Mapping[str, RunnerOptionsProfileConfig],
    agent_policy_profiles: Mapping[str, AgentPolicyProfileConfig],
) -> None:
    """校验 execution profile 内部引用。

    :param profiles: execution profiles。
    :param runner_options_profiles: runner options profiles。
    :param agent_policy_profiles: agent policy profiles。
    :returns: 无返回值。
    :raises ConfigFieldError: 引用不存在时抛出。
    """

    for profile_id, profile in profiles.items():
        _require_mapping_contains(
            runner_options_profiles,
            key=profile.ordinary.runner_options_profile_id,
            context=f"execution_profiles.profiles.{profile_id}.ordinary.runner_options_profile_id",
        )
        _require_mapping_contains(
            runner_options_profiles,
            key=profile.compactor.runner_options_profile_id,
            context=f"execution_profiles.profiles.{profile_id}.compactor.runner_options_profile_id",
        )
        _require_mapping_contains(
            agent_policy_profiles,
            key=profile.ordinary.agent_policy_profile_id,
            context=f"execution_profiles.profiles.{profile_id}.ordinary.agent_policy_profile_id",
        )


def _validate_hint_references(
    *,
    runner_hints: Mapping[str, RunnerHintConfig],
    agent_hints: Mapping[str, AgentHintConfig],
    runner_options_profiles: Mapping[str, RunnerOptionsProfileConfig],
    agent_policy_profiles: Mapping[str, AgentPolicyProfileConfig],
) -> None:
    """校验 hints 中显式 profile 引用。

    :param runner_hints: runner hints。
    :param agent_hints: agent hints。
    :param runner_options_profiles: runner options profiles。
    :param agent_policy_profiles: agent policy profiles。
    :returns: 无返回值。
    :raises ConfigFieldError: 引用不存在时抛出。
    """

    for hint_id, hint in runner_hints.items():
        if hint.runner_options_profile_id is not None:
            _require_mapping_contains(
                runner_options_profiles,
                key=hint.runner_options_profile_id,
                context=f"execution_profiles.runner_hints.{hint_id}.runner_options_profile_id",
            )
    for hint_id, hint in agent_hints.items():
        if hint.agent_policy_profile_id is not None:
            _require_mapping_contains(
                agent_policy_profiles,
                key=hint.agent_policy_profile_id,
                context=f"execution_profiles.agent_hints.{hint_id}.agent_policy_profile_id",
            )


def _validate_execution_model_references(
    *,
    execution_profiles: ExecutionProfilesConfig,
    models: ModelsConfig,
) -> None:
    """校验 execution config 中的 model id 引用。

    :param execution_profiles: execution profiles typed config。
    :param models: 模型目录 typed config。
    :returns: 无返回值。
    :raises ConfigFieldError: 模型引用不存在时抛出。
    """

    for profile_id, profile in execution_profiles.profiles.items():
        _require_mapping_contains(
            models.models,
            key=profile.ordinary.model_id,
            context=f"execution_profiles.profiles.{profile_id}.ordinary.model_id",
        )
        _require_mapping_contains(
            models.models,
            key=profile.compactor.model_id,
            context=f"execution_profiles.profiles.{profile_id}.compactor.model_id",
        )
    for hint_id, hint in execution_profiles.runner_hints.items():
        if hint.model_id is not None:
            _require_mapping_contains(
                models.models,
                key=hint.model_id,
                context=f"execution_profiles.runner_hints.{hint_id}.model_id",
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


def _require_no_unknown_fields(
    record: JsonObject, *, allowed: frozenset[str], context: str
) -> None:
    """校验记录不包含未知字段。

    :param record: 待校验 JSON object。
    :param allowed: 允许字段集合。
    :param context: 错误消息上下文。
    :returns: 无返回值。
    :raises ConfigFieldError: 包含未知字段时抛出。
    """

    unknown = frozenset(record.keys()) - allowed
    if unknown:
        raise ConfigFieldError(f"{context} has unknown fields: {sorted(unknown)}")


def _require_id_match(*, record_id: str, embedded_id: str, context: str) -> None:
    """校验 map key 与记录内 id 同源。

    :param record_id: map key id。
    :param embedded_id: 记录内部 id。
    :param context: 错误消息上下文。
    :returns: 无返回值。
    :raises ConfigFieldError: 二者不一致时抛出。
    """

    if record_id != embedded_id:
        raise ConfigFieldError(
            f"{context}.{record_id} id field must match map key: {embedded_id}"
        )


def _require_mapping_contains(
    values: Mapping[str, JsonValue]
    | Mapping[str, ModelConfig]
    | Mapping[str, ExecutionProfileConfig]
    | Mapping[str, RunnerOptionsProfileConfig]
    | Mapping[str, AgentPolicyProfileConfig]
    | Mapping[str, HostRuntimeProfileConfig]
    | Mapping[str, LaneCapacityConfig],
    *,
    key: str,
    context: str,
) -> None:
    """校验映射中存在指定 key。

    :param values: 待校验映射。
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
        if not isinstance(value, str) or not value.strip():
            raise ConfigFieldError(f"{context}.{field_name}.{key} must be non-empty string")
        result[key] = value
    return result


def _require_str_field(record: JsonObject, *, field_name: str, context: str) -> str:
    """读取必填非空字符串字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字段字符串。
    :raises ConfigFieldError: 字段缺失或类型非法时抛出。
    """

    value = _require_field(record, field_name=field_name, context=context)
    if not isinstance(value, str) or not value.strip():
        raise ConfigFieldError(f"{context}.{field_name} must be non-empty string")
    return value


def _optional_str_field(
    record: JsonObject, *, field_name: str, context: str
) -> str | None:
    """读取可选非空字符串字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 字段字符串；未配置或 ``null`` 时返回 ``None``。
    :raises ConfigFieldError: 字段存在但类型非法时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    value = record[field_name]
    if not isinstance(value, str) or not value.strip():
        raise ConfigFieldError(f"{context}.{field_name} must be non-empty string or null")
    return value


def _require_bool_field(record: JsonObject, *, field_name: str, context: str) -> bool:
    """读取必填 bool 字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: bool 值。
    :raises ConfigFieldError: 字段缺失或类型非法时抛出。
    """

    value = _require_field(record, field_name=field_name, context=context)
    if not isinstance(value, bool):
        raise ConfigFieldError(f"{context}.{field_name} must be bool")
    return value


def _optional_bool_field(
    record: JsonObject, *, field_name: str, context: str
) -> bool | None:
    """读取可选 bool 字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: bool 值；未配置或 ``null`` 时返回 ``None``。
    :raises ConfigFieldError: 字段存在但类型非法时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    value = record[field_name]
    if not isinstance(value, bool):
        raise ConfigFieldError(f"{context}.{field_name} must be bool or null")
    return value


def _require_int_field(record: JsonObject, *, field_name: str, context: str) -> int:
    """读取必填整数字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 整数值。
    :raises ConfigFieldError: 字段缺失或类型非法时抛出。
    """

    value = _require_field(record, field_name=field_name, context=context)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigFieldError(f"{context}.{field_name} must be integer")
    return value


def _require_positive_int_field(
    record: JsonObject, *, field_name: str, context: str
) -> int:
    """读取必填正整数字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 正整数值。
    :raises ConfigFieldError: 字段缺失、类型非法或非正时抛出。
    """

    value = _require_int_field(record, field_name=field_name, context=context)
    if value <= 0:
        raise ConfigFieldError(f"{context}.{field_name} must be positive integer")
    return value


def _require_non_negative_int_field(
    record: JsonObject, *, field_name: str, context: str
) -> int:
    """读取必填非负整数字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 非负整数值。
    :raises ConfigFieldError: 字段缺失、类型非法或为负时抛出。
    """

    value = _require_int_field(record, field_name=field_name, context=context)
    if value < 0:
        raise ConfigFieldError(f"{context}.{field_name} must be non-negative integer")
    return value


def _optional_positive_int_field(
    record: JsonObject, *, field_name: str, context: str
) -> int | None:
    """读取可选正整数字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 正整数值；未配置或 ``null`` 时返回 ``None``。
    :raises ConfigFieldError: 字段存在但类型非法或非正时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    value = _require_int_field(record, field_name=field_name, context=context)
    if value <= 0:
        raise ConfigFieldError(f"{context}.{field_name} must be positive integer or null")
    return value


def _optional_non_negative_int_field(
    record: JsonObject, *, field_name: str, context: str
) -> int | None:
    """读取可选非负整数字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 非负整数值；未配置或 ``null`` 时返回 ``None``。
    :raises ConfigFieldError: 字段存在但类型非法或为负时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    value = _require_int_field(record, field_name=field_name, context=context)
    if value < 0:
        raise ConfigFieldError(f"{context}.{field_name} must be non-negative integer or null")
    return value


def _require_float_field(record: JsonObject, *, field_name: str, context: str) -> float:
    """读取必填数值字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 浮点值。
    :raises ConfigFieldError: 字段缺失或类型非法时抛出。
    """

    value = _require_field(record, field_name=field_name, context=context)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigFieldError(f"{context}.{field_name} must be number")
    return float(value)


def _require_positive_float_field(
    record: JsonObject, *, field_name: str, context: str
) -> float:
    """读取必填正数值字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 正浮点值。
    :raises ConfigFieldError: 字段缺失、类型非法或非正时抛出。
    """

    value = _require_float_field(record, field_name=field_name, context=context)
    if value <= 0.0:
        raise ConfigFieldError(f"{context}.{field_name} must be positive number")
    return value


def _optional_float_field(
    record: JsonObject, *, field_name: str, context: str
) -> float | None:
    """读取可选数值字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 浮点值；未配置或 ``null`` 时返回 ``None``。
    :raises ConfigFieldError: 字段存在但类型非法时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    return _require_float_field(record, field_name=field_name, context=context)


def _optional_positive_float_field(
    record: JsonObject, *, field_name: str, context: str
) -> float | None:
    """读取可选正数值字段。

    :param record: JSON object。
    :param field_name: 字段名。
    :param context: 错误消息上下文。
    :returns: 正浮点值；未配置或 ``null`` 时返回 ``None``。
    :raises ConfigFieldError: 字段存在但类型非法或非正时抛出。
    """

    if field_name not in record or record[field_name] is None:
        return None
    value = _require_float_field(record, field_name=field_name, context=context)
    if value <= 0.0:
        raise ConfigFieldError(f"{context}.{field_name} must be positive number or null")
    return value


__all__ = [
    "AgentHintConfig",
    "AgentPolicyProfileConfig",
    "CompactorExecutionConfig",
    "ConfigExtendsError",
    "ConfigFieldError",
    "ConfigFileNotFoundError",
    "ConfigLoadError",
    "ConfigLoader",
    "ConfigShapeError",
    "ContextBudgetConfig",
    "ExecutionProfileConfig",
    "ExecutionProfilesConfig",
    "HostRuntimeConfig",
    "HostRuntimeProfileConfig",
    "LaneCapacityConfig",
    "LaneRuntimeConfig",
    "MemoryProjectionConfig",
    "ModelConfig",
    "ModelsConfig",
    "OrdinaryExecutionConfig",
    "RunnerHintConfig",
    "RunnerKind",
    "RunnerOptionsProfileConfig",
    "RuntimeConfig",
    "SQLiteRuntimeConfig",
    "ToolDiscoveryConfig",
    "ToolDiscoveryEntryPointConfig",
    "ToolDiscoveryProviderConfig",
    "TruncationConfig",
    "legacy_config_file_names",
    "load_runtime_config",
]
