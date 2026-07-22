"""Service 层 Host runtime assembly helper。

本模块负责在 Host 外部把层中立 runtime config、runtime locations、工具发现
结果、ScenePrepare 输出、显式 override 与 env/secret access 映射为 Host
public typed inputs。它可以依赖 Host / Engine public contracts，但不修改
Host public API，不读取 Fins storage，也不把 raw config fragment 传入 Host。
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final

from dayu.contracts import (
    JsonValue,
    ToolBundle,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
)
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts import AgentFallbackMode
from dayu.engine import AgentPolicy
from dayu.engine.contracts.runner_spec import ClientCorrelationPolicy, RunnerCallOptions, RunnerSpec
from dayu.engine.provider_extensions import provider_request_extension_from_json
from dayu.fins.ingestion.awaiting_resolution import (
    AWAITING_RESOLUTION_MODE_CONFIG_FIELD,
    AwaitingResolutionMode,
    parse_awaiting_resolution_mode,
)
from dayu.fins.ingestion.observation_handle import FinsObservationRuntime
from dayu.service.fins_wait_adapter import (
    FINS_INGESTION_WAIT_ADAPTER_KEY,
    FINS_DOWNLOAD_AWAITING_TOOL_NAME,
    FINS_PREPROCESS_AWAITING_TOOL_NAME,
    FINS_UPLOAD_AWAITING_TOOL_NAME,
    build_fins_wait_activation_registry,
    build_fins_wait_adapter_registry,
    build_fins_wait_poll_adapter_registry,
)
from dayu.fins.ingestion_runtime import FinsIngestionRuntime
from dayu.fins.service_runtime import DefaultFinsRuntime
from dayu.fins.tools.download_tools import build_fins_download_tool
from dayu.fins.tools.preprocess_tools import build_fins_preprocess_tool
from dayu.fins.tools.upload_tools import build_fins_upload_tool
from dayu.host.api import (
    CompactorRunnerBaseline,
    FollowupBehavior,
    HostCallContext,
    HostSessionEventDeliveryPolicy,
    OpenHostOptions,
    OrdinaryRunExecutionBaseline,
    SubmitFollowupRequest,
)
from dayu.host.context_policy import default_context_budget_policy
from dayu.host.local_proxy import DefaultLocalEngineWorkerFactory
from dayu.host.memory import MemoryProjectionPolicy
from dayu.host.wait_adapter import (
    WaitActivationRegistry,
    WaitAdapterRegistry,
    WaitPollAdapterRegistry,
    WaitPollerRuntimePolicy,
)
from dayu.host.tool_duplicate_governance import (
    DuplicateDecisionKind,
    DuplicateGovernanceMessages,
    DuplicateGovernancePolicy,
)
from dayu.host.tooling import HostToolingOptions
from dayu.host.tooling import ProcessCapsuleInterruptPolicy
from dayu.runtime.assembly import (
    AgentPolicyBaseline,
    ExecutionProfileCompatibilityDiagnostic,
    MergedAgentPolicyConfig,
    ModelRunnerHintOverride,
    RuntimeAssemblySelectionError,
    RunnerOptionHintSelection,
    effective_tool_truncate_spec_from_policy,
    merge_agent_policy_config,
    select_runner_option_hint,
    tool_truncation_policy_defaults,
    validate_execution_profile_context_window,
)
from dayu.runtime.config_loader import (
    AgentPolicyConfig,
    ExecutionBaselineConfig,
    ExecutionProfileConfig,
    HostRuntimeProfileConfig,
    ModelConfig,
    ProcessCapsuleInterruptPolicyConfig,
    RuntimeConfig,
    RuntimeLaneConfig,
    RunnerOptionHintConfig,
    ToolDuplicateGovernanceMessagesConfig,
    ToolDuplicateGovernancePolicyConfig,
    ToolDiscoveryProviderConfig,
    WaitPollerRuntimePolicyConfig,
)
from dayu.runtime.location import RuntimeLocations
from dayu.runtime.numeric import is_finite_number, is_positive_finite_number
from dayu.runtime.scene_prepare import (
    PreparedSceneInputs,
    ScenePrepareRequest,
    SceneToolCatalog,
    prepare_scene,
)
from dayu.runtime.tools_discovery import (
    PackageEntryPointProvider,
    PythonImportPathProvider,
    ToolsDiscovery,
    ToolsDiscoveryProviderBinding,
    ToolsDiscoveryProviderOutput,
    ToolsDiscoveryProviderSpec,
    resolve_provider_callable,
)
from dayu.runtime.workspace_paths import resolve_workspace_path

_ENV_PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")
_WORKER_BACKEND_LOCAL: Final[str] = "local"
_COMPACTOR_SYSTEM_PROMPT_FRAGMENT_COUNT: Final[int] = 1
_FINS_WORKSPACE_ROOT_CONFIG_FIELD: Final[str] = "workspace_root"
_FINS_DOWNLOAD_PROVIDER_ID: Final[str] = "financial-download-tools"
_FINS_PREPROCESS_PROVIDER_ID: Final[str] = "financial-preprocess-tools"
_FINS_UPLOAD_PROVIDER_ID: Final[str] = "financial-upload-tools"
_FINS_DOWNLOAD_SOURCE_ID: Final[str] = "dayu.fins.tools.download_provider"
_FINS_PREPROCESS_SOURCE_ID: Final[str] = "dayu.fins.tools.preprocess_provider"
_FINS_UPLOAD_SOURCE_ID: Final[str] = "dayu.fins.tools.upload_provider"
_FINS_DOWNLOAD_VERSION_REF: Final[str] = "fins-download-tools-provider-v1"
_FINS_PREPROCESS_VERSION_REF: Final[str] = "fins-preprocess-tools-provider-v1"
_FINS_UPLOAD_VERSION_REF: Final[str] = "fins-upload-tools-provider-v1"
_FINS_READ_PROVIDER_IDS: Final[frozenset[str]] = frozenset({"financial-read-tools"})
_FINS_DOWNLOAD_PROVIDER_IDS: Final[frozenset[str]] = frozenset(
    {_FINS_DOWNLOAD_PROVIDER_ID}
)
_FINS_PREPROCESS_PROVIDER_IDS: Final[frozenset[str]] = frozenset(
    {_FINS_PREPROCESS_PROVIDER_ID}
)
_FINS_UPLOAD_PROVIDER_IDS: Final[frozenset[str]] = frozenset(
    {_FINS_UPLOAD_PROVIDER_ID}
)
_FINS_READ_IMPORT_PATHS: Final[frozenset[str]] = frozenset(
    {"dayu.fins.tools.provider:discover_tools"}
)
_FINS_DOWNLOAD_IMPORT_PATHS: Final[frozenset[str]] = frozenset(
    {"dayu.fins.tools.download_provider:discover_tools"}
)
_FINS_PREPROCESS_IMPORT_PATHS: Final[frozenset[str]] = frozenset(
    {"dayu.fins.tools.preprocess_provider:discover_tools"}
)
_FINS_UPLOAD_IMPORT_PATHS: Final[frozenset[str]] = frozenset(
    {"dayu.fins.tools.upload_provider:discover_tools"}
)
_FINS_READ_SOURCE_IDS: Final[frozenset[str]] = frozenset(
    {"dayu.fins.tools.provider"}
)
_FINS_DOWNLOAD_SOURCE_IDS: Final[frozenset[str]] = frozenset(
    {_FINS_DOWNLOAD_SOURCE_ID}
)
_FINS_PREPROCESS_SOURCE_IDS: Final[frozenset[str]] = frozenset(
    {_FINS_PREPROCESS_SOURCE_ID}
)
_FINS_UPLOAD_SOURCE_IDS: Final[frozenset[str]] = frozenset(
    {_FINS_UPLOAD_SOURCE_ID}
)
_WEB_TOOLS_PROVIDER_IDS: Final[frozenset[str]] = frozenset({"web-tools"})
_WEB_TOOLS_IMPORT_PATHS: Final[frozenset[str]] = frozenset(
    {"dayu.tools.web:discover_tools"}
)
_WEB_TOOLS_SOURCE_IDS: Final[frozenset[str]] = frozenset({"dayu.tools.web"})
_WEB_PLAYWRIGHT_STORAGE_STATE_DIR_CONFIG_FIELD: Final[str] = (
    "playwright_storage_state_dir"
)


@dataclass(frozen=True, slots=True)
class ServiceAssemblyOverrides:
    """Service assembly 显式 override。

    :param host_runtime_id: 显式 Host runtime id；``None`` 表示使用配置默认值。
    :param execution_profile_id: 显式 execution profile id；``None`` 表示使用配置默认值。
    :param model_id: 普通 Run 模型显式 override；``None`` 表示不覆盖。
    :param runner_option_hint_id: 普通 Run runner option hint 显式 override；
        ``None`` 表示不覆盖。
    """

    host_runtime_id: str | None = None
    execution_profile_id: str | None = None
    model_id: str | None = None
    runner_option_hint_id: str | None = None


@dataclass(frozen=True, slots=True)
class ServiceRunOverrides:
    """Service 单次 Run 显式 override。

    :param temperature: Runner 调用温度；``None`` 表示使用当前 assembly baseline。
    :param tool_execution_timeout_seconds: 工具执行握手超时秒数；``None`` 表示
        使用当前 AgentPolicy baseline。
    :param max_iterations: Agent loop 最大迭代数；``None`` 表示使用 baseline。
    :param fallback_mode: Agent fallback 模式；``None`` 表示使用 baseline。
    :param fallback_prompt: Agent fallback prompt；``None`` 表示使用 baseline。
    :param max_consecutive_failed_tool_batches: 连续失败工具批次阈值；``None``
        表示使用 baseline。
    """

    temperature: float | None = None
    tool_execution_timeout_seconds: float | None = None
    max_iterations: int | None = None
    fallback_mode: str | None = None
    fallback_prompt: str | None = None
    max_consecutive_failed_tool_batches: int | None = None

    def __post_init__(self) -> None:
        """校验单次 Run override 字段。

        :returns: ``None``。
        :raises ValueError: 数值字段非法、fallback 模式非法或 prompt 为空时抛出。
        """

        _require_optional_finite_float(
            self.temperature,
            field_name="ServiceRunOverrides.temperature",
        )
        _require_optional_positive_float(
            self.tool_execution_timeout_seconds,
            field_name="ServiceRunOverrides.tool_execution_timeout_seconds",
        )
        _require_optional_positive_int(
            self.max_iterations,
            field_name="ServiceRunOverrides.max_iterations",
        )
        if self.fallback_mode is not None:
            try:
                _agent_fallback_mode_from_config(self.fallback_mode)
            except ValueError as exc:
                raise ValueError(
                    "ServiceRunOverrides.fallback_mode has unsupported value: "
                    f"{self.fallback_mode}"
                ) from exc
        _require_optional_non_empty_text(
            self.fallback_prompt,
            field_name="ServiceRunOverrides.fallback_prompt",
        )
        _require_optional_positive_int(
            self.max_consecutive_failed_tool_batches,
            field_name="ServiceRunOverrides.max_consecutive_failed_tool_batches",
        )


@dataclass(frozen=True, slots=True)
class ServiceDiscoveredTools:
    """Service 工具发现结果。

    :param tool_bundle: 已发现的业务工具 bundle。
    :param source_refs: 工具来源引用。
    :param provider_reports: 工具 provider 报告行。
    :param effective_provider_configs: 本次工具发现实际使用的 effective provider
        configs，供后续 Host tooling assembly 复用。
    :param fins_awaiting_runtime: Service 为启用的 Fins awaiting providers
        共享装配的 ingestion runtime；没有启用 Fins awaiting provider 时为
        ``None``；调用方仍须显式传入该已验证状态。
    :param _fins_awaiting_providers: provider-assembly boundary 一次构造的
        active typed metadata collection，供 binding、registry 与 composition
        复用；没有 active provider 时调用方须显式传入空 tuple。
    """

    tool_bundle: ToolBundle
    source_refs: tuple[ToolBundleSourceRef, ...]
    provider_reports: tuple[str, ...]
    effective_provider_configs: tuple[ToolDiscoveryProviderConfig, ...]
    fins_awaiting_runtime: FinsObservationRuntime | None
    _fins_awaiting_providers: tuple[_FinsAwaitingProviderMetadata, ...]


@dataclass(frozen=True, slots=True)
class ServiceOpenHostAssemblyRequest:
    """Service 组合 ``OpenHostOptions`` 的请求。

    :param workspace_root: workspace 根目录，用于解析相对配置路径。
    :param config: ``ConfigLoader`` 输出的 runtime typed config。
    :param locations: runtime location resolver 输出的位置。
    :param scene_inputs: ``ScenePrepare`` 输出。
    :param discovered_tools: ``ToolsDiscovery`` 输出及诊断。
    :param overrides: Service / UI 显式 override。
    :param env: env / secret 映射；只用于解析模型 header secret 占位符。
    """

    workspace_root: pathlib.Path
    config: RuntimeConfig
    locations: RuntimeLocations
    scene_inputs: PreparedSceneInputs
    discovered_tools: ServiceDiscoveredTools
    overrides: ServiceAssemblyOverrides
    env: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ServiceOpenHostAssemblyDiagnostics:
    """Host 调用前的 Service assembly 诊断。

    :param config_overlay_dir: workspace config overlay 目录。
    :param prompt_asset_root: prompt asset 根目录。
    :param scene_manifest_root: scene manifest 根目录。
    :param host_runtime_id: Host runtime id。
    :param execution_profile_id: execution profile id。
    :param model_id: 普通 Run 模型 id。
    :param model_source: 模型 id 来源层。
    :param runner_option_hint_id: 普通 Run runner option hint id。
    :param runner_option_hint_source: runner option hint 来源层。
    :param compactor_model_id: compactor 模型 id。
    :param compactor_runner_option_hint_id: compactor runner option hint id。
    :param lane_name: runtime lane 名。
    :param tool_provider_reports: 工具 provider 报告行。
    :param tool_selection: scene 工具选择摘要。
    :param context_budget_policy_ref: context budget policy ref。
    :param agent_policy_sources: Agent policy 字段来源摘要。
    :param tool_truncation_policy: tool truncation policy 摘要。
    :param ordinary_provider_extension_status: 普通 Runner provider extension 映射状态。
    :param compactor_provider_extension_status: compactor provider extension 映射状态。
    :param ordinary_profile_compatibility: 普通 Run profile / model 兼容诊断。
    :param compactor_profile_compatibility: compactor profile / model 兼容诊断。
    """

    config_overlay_dir: pathlib.Path | None
    prompt_asset_root: pathlib.Path
    scene_manifest_root: pathlib.Path
    host_runtime_id: str
    execution_profile_id: str
    model_id: str
    model_source: str
    runner_option_hint_id: str
    runner_option_hint_source: str
    compactor_model_id: str
    compactor_runner_option_hint_id: str
    lane_name: str
    tool_provider_reports: tuple[str, ...]
    tool_selection: str
    context_budget_policy_ref: str
    agent_policy_sources: tuple[str, ...]
    tool_truncation_policy: str
    ordinary_provider_extension_status: str
    compactor_provider_extension_status: str
    ordinary_profile_compatibility: ExecutionProfileCompatibilityDiagnostic
    compactor_profile_compatibility: ExecutionProfileCompatibilityDiagnostic


@dataclass(frozen=True, slots=True)
class ServiceOpenHostAssemblyResult:
    """完整 Host opener assembly 结果。

    :param options: 可传给 ``open_host`` 的 Host public opener options。
    :param diagnostics: 调用 Host 前的 Service assembly 诊断。
    :param host_runtime: 选中的 Host runtime profile。
    :param execution_profile: 选中的 execution profile。
    :param lane: 选中的 runtime lane。
    :param ordinary_selection: 普通 Run 模型与 runner hint 选择。
    :param compactor_selection: compactor 模型与 runner hint 选择。
    :param agent_policy_config: 合并后的 AgentPolicy 字段集。
    :param effective_tool_bundle: 已应用截断默认值的工具 bundle。
    """

    options: OpenHostOptions
    diagnostics: ServiceOpenHostAssemblyDiagnostics
    host_runtime: HostRuntimeProfileConfig
    execution_profile: ExecutionProfileConfig
    lane: RuntimeLaneConfig
    ordinary_selection: RunnerOptionHintSelection
    compactor_selection: RunnerOptionHintSelection
    agent_policy_config: MergedAgentPolicyConfig
    effective_tool_bundle: ToolBundle


@dataclass(frozen=True, slots=True)
class _CompactorScenePrompts:
    """Compactor scene / baseline 装配后的 compactor 输入。

    :param system_prompt: compactor system prompt。
    :param user_prompt_template: compactor user prompt template。
    :param agent_policy: compactor Agent policy。
    """

    system_prompt: str
    user_prompt_template: str
    agent_policy: AgentPolicy


@dataclass(frozen=True, slots=True)
class _FinsAwaitingProviderMetadata:
    """Fins awaiting provider 的稳定 discovery 输出元数据。

    :param spec_id: ConfigLoader provider map 中的稳定标识。
    :param tool_name: provider 产出的 awaiting 工具名。
    :param provider_id: provider 自声明身份。
    :param version_ref: provider 版本引用。
    :param source_id: provider source ref。
    :param workspace_root: provider 的绝对 Fins workspace root。
    :param mode: Fins owner parser 产出的 typed 恢复模式。
    """

    spec_id: str
    tool_name: str
    provider_id: str
    version_ref: str
    source_id: str
    workspace_root: pathlib.Path
    mode: AwaitingResolutionMode


@dataclass(frozen=True, slots=True)
class _FinsAwaitingProviderCallable:
    """共享 ingestion runtime 的 Fins awaiting discovery provider callable。

    :param metadata: provider 输出元数据。
    :param runtime: 本次 Service discovery 为同一 Fins workspace 创建的共享
        ingestion runtime。
    """

    metadata: _FinsAwaitingProviderMetadata
    runtime: FinsIngestionRuntime

    def __call__(
        self, spec: ToolsDiscoveryProviderSpec
    ) -> ToolsDiscoveryProviderOutput:
        """返回 Fins awaiting 工具声明。

        :param spec: ToolsDiscovery provider spec；仅用于保留 discovery 协议形状。
        :returns: provider 输出。
        :raises ValueError: 工具名不受支持时抛出。
        """

        del spec
        return ToolsDiscoveryProviderOutput(
            provider_id=self.metadata.provider_id,
            version_ref=self.metadata.version_ref,
            source_refs=(
                ToolBundleSourceRef(
                    source_kind=ToolBundleSourceKind.EXPLICIT_PROVIDER,
                    source_id=self.metadata.source_id,
                    version_ref=self.metadata.version_ref,
                    content_digest=None,
                ),
            ),
            definitions=(
                _fins_awaiting_tool_definition(
                    tool_name=self.metadata.tool_name,
                    runtime=self.runtime,
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class _DisabledProviderCallable:
    """禁用 provider 的占位 callable。

    该 callable 只用于保持 ``ToolsDiscoveryProviderBinding`` 的强类型形状；
    ``ToolsDiscovery.discover_from_bindings`` 会在调用前跳过 disabled spec。
    """

    def __call__(
        self, spec: ToolsDiscoveryProviderSpec
    ) -> ToolsDiscoveryProviderOutput:
        """禁用 provider callable 被调用时立即失败。

        :param spec: disabled provider spec。
        :returns: 不会正常返回。
        :raises RuntimeError: 该 sentinel 被错误调用时抛出。
        """

        del spec
        raise RuntimeError(
            "disabled tools discovery provider callable must not be invoked"
        )


def discover_service_tools(
    effective_provider_configs: Sequence[ToolDiscoveryProviderConfig],
) -> ServiceDiscoveredTools:
    """按 effective provider configs 执行工具发现。

    :param effective_provider_configs: 已由调用方完成 config 与运行时参数装配
        的 provider configs。
    :returns: Service 工具发现结果。
    :raises ValueError: provider spec 同时缺少 import path 与 entry point 时抛出。
    :raises Exception: ``ToolsDiscovery`` provider 失败时向上抛出。
    """

    provider_config_tuple = tuple(effective_provider_configs)
    fins_awaiting_providers = _fins_awaiting_provider_metadata_from_configs(
        provider_config_tuple
    )
    fins_awaiting_runtime = _shared_fins_awaiting_runtime_from_provider_metadata(
        fins_awaiting_providers
    )
    discovery_result = ToolsDiscovery().discover_from_bindings(
        _tool_discovery_bindings(
            provider_config_tuple,
            fins_awaiting_providers=fins_awaiting_providers,
            fins_awaiting_runtime=fins_awaiting_runtime,
        )
    )
    available_tool_names = frozenset(
        definition.name for definition in discovery_result.tool_bundle.definitions
    )
    active_fins_awaiting_providers = _active_fins_awaiting_provider_metadata(
        fins_awaiting_providers,
        available_tool_names=available_tool_names,
    )
    return ServiceDiscoveredTools(
        tool_bundle=discovery_result.tool_bundle,
        source_refs=discovery_result.source_refs,
        provider_reports=tuple(
            _format_provider_report(
                output.provider_id,
                output.spec_id,
                output.version_ref,
                output.tool_names,
            )
            for output in discovery_result.provider_reports
        ),
        effective_provider_configs=provider_config_tuple,
        fins_awaiting_runtime=fins_awaiting_runtime,
        _fins_awaiting_providers=active_fins_awaiting_providers,
    )


def assemble_effective_tool_provider_configs(
    provider_configs: Sequence[ToolDiscoveryProviderConfig],
    *,
    workspace_root: pathlib.Path | None,
    fins_workspace_root_override: pathlib.Path | None = None,
) -> tuple[ToolDiscoveryProviderConfig, ...]:
    """装配工具 provider 的 effective configs。

    :param provider_configs: ConfigLoader 产出的 raw provider typed configs。
    :param workspace_root: 当前运行时 workspace root；为 ``None`` 时不注入。
    :param fins_workspace_root_override: 仅在调用方显式提供时强制作为
        Fins provider 的绝对 effective workspace root。raw 配置仍先通过
        现行类型与非空语法校验。
    :returns: provider config tuple，必要时替换为 effective config。
    :raises ValueError: override 不是绝对路径，或 raw provider 路径语法
        非法时抛出。
    """

    effective_configs: list[ToolDiscoveryProviderConfig] = []
    for provider_config in provider_configs:
        effective_config = _effective_tool_provider_config(
            provider_config,
            workspace_root=workspace_root,
            fins_workspace_root_override=fins_workspace_root_override,
        )
        if effective_config == provider_config.config:
            effective_configs.append(provider_config)
        else:
            effective_configs.append(replace(provider_config, config=effective_config))
    return tuple(effective_configs)


def compose_open_host_options(
    request: ServiceOpenHostAssemblyRequest,
) -> ServiceOpenHostAssemblyResult:
    """把 Service assembly 请求映射为 Host public opener options。

    :param request: Service Host opener assembly 请求。
    :returns: Host opener options 与诊断。
    :raises ValueError: runtime、profile、worker backend、secret 或 provider
        extension 映射失败时抛出。
    """

    config = request.config
    host_runtime_id = _select_host_runtime_id(
        config,
        request.overrides.host_runtime_id,
    )
    execution_profile_id = _select_execution_profile_id(
        config,
        request.overrides.execution_profile_id,
    )
    host_runtime = config.host_runtime.runtimes[host_runtime_id]
    execution_profile = config.execution_profiles.execution_profiles[execution_profile_id]
    lane = config.runtime_lanes.lanes[host_runtime.host_execution_lane_name]
    effective_tool_bundle = _tool_bundle_with_effective_truncation(
        tool_bundle=request.discovered_tools.tool_bundle,
        execution_profile=execution_profile,
    )
    compactor_scene_inputs = _prepare_compactor_scene_inputs(
        request,
        execution_profile=execution_profile,
    )
    compactor_prompts = _compactor_prompts_from_scene_inputs(
        compactor_scene_inputs,
        user_prompt_template=_read_compactor_user_prompt_template(
            request,
            execution_profile=execution_profile,
        ),
    )
    ordinary_selection = select_runner_option_hint(
        models=config.models,
        execution_baseline=execution_profile.run_baseline,
        scene_model_hints=request.scene_inputs.model_hints,
        run_override=_model_runner_override_from_overrides(request.overrides),
        base_policy=None,
    )
    compactor_selection = select_runner_option_hint(
        models=config.models,
        execution_baseline=ExecutionBaselineConfig(
            model_id=execution_profile.compactor_baseline.model_id,
            runner_option_hint_id=(execution_profile.compactor_baseline.runner_option_hint_id),
        ),
        scene_model_hints=None,
        run_override=None,
        base_policy=None,
    )
    ordinary_profile_compatibility = validate_execution_profile_context_window(
        profile=execution_profile,
        model=ordinary_selection.model,
    )
    compactor_profile_compatibility = validate_execution_profile_context_window(
        profile=execution_profile,
        model=compactor_selection.model,
    )
    agent_policy_config = merge_agent_policy_config(
        base_policy=_agent_policy_baseline_from_config(execution_profile.agent_policy),
        execution_profile=execution_profile.agent_policy,
        scene_override=request.scene_inputs.agent_policy_override,
        run_override=None,
    )
    options = _compose_options(
        request=request,
        host_runtime=host_runtime,
        execution_profile=execution_profile,
        lane=lane,
        ordinary_selection=ordinary_selection,
        compactor_selection=compactor_selection,
        agent_policy_config=agent_policy_config,
        effective_tool_bundle=effective_tool_bundle,
        compactor_prompts=compactor_prompts,
    )
    diagnostics = _assembly_diagnostics(
        locations=request.locations,
        host_runtime_id=host_runtime_id,
        execution_profile_id=execution_profile_id,
        execution_profile=execution_profile,
        lane=lane,
        ordinary_selection=ordinary_selection,
        compactor_selection=compactor_selection,
        ordinary_profile_compatibility=ordinary_profile_compatibility,
        compactor_profile_compatibility=compactor_profile_compatibility,
        agent_policy_config=agent_policy_config,
        tool_provider_reports=request.discovered_tools.provider_reports,
        scene_inputs=request.scene_inputs,
    )
    return ServiceOpenHostAssemblyResult(
        options=options,
        diagnostics=diagnostics,
        host_runtime=host_runtime,
        execution_profile=execution_profile,
        lane=lane,
        ordinary_selection=ordinary_selection,
        compactor_selection=compactor_selection,
        agent_policy_config=agent_policy_config,
        effective_tool_bundle=effective_tool_bundle,
    )


def compose_submit_followup_request(
    *,
    context: HostCallContext,
    session_id: str,
    client_request_id: str,
    scene_inputs: PreparedSceneInputs,
    user_prompt: str,
    tool_names: frozenset[str] | None,
    behavior: FollowupBehavior,
    target_run_id: str | None,
) -> SubmitFollowupRequest:
    """把 Service 本轮输入映射为 public ``SubmitFollowupRequest``。

    :param context: Host 调用上下文。
    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :param scene_inputs: ``ScenePrepare`` 输出。
    :param user_prompt: 本轮用户输入。
    :param tool_names: 本轮工具选择；``None`` 表示全量，空集合表示禁用。
    :param behavior: Host followup 行为。
    :param target_run_id: 目标 Run id；无目标时为 ``None``。
    :returns: SubmitFollowupRequest。
    :raises ValueError: 请求字段非法时由底层抛出。
    """

    return SubmitFollowupRequest(
        context=context,
        session_id=session_id,
        client_request_id=client_request_id,
        system_prompt=scene_inputs.system_prompt,
        user_prompt=user_prompt,
        tool_names=tool_names,
        runner_spec=None,
        runner_options=None,
        agent_policy=None,
        behavior=behavior,
        target_run_id=target_run_id,
    )


def compose_submit_followup_request_with_overrides(
    *,
    context: HostCallContext,
    session_id: str,
    client_request_id: str,
    scene_inputs: PreparedSceneInputs,
    user_prompt: str,
    tool_names: frozenset[str] | None,
    behavior: FollowupBehavior,
    target_run_id: str | None,
    host_assembly: ServiceOpenHostAssemblyResult,
    run_overrides: ServiceRunOverrides,
) -> SubmitFollowupRequest:
    """把 Service 本轮输入与单次 Run override 映射为 follow-up 请求。

    :param context: Host 调用上下文。
    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :param scene_inputs: ``ScenePrepare`` 输出。
    :param user_prompt: 本轮用户输入。
    :param tool_names: 本轮工具选择；``None`` 表示全量，空集合表示禁用。
    :param behavior: Host followup 行为。
    :param target_run_id: 目标 Run id；无目标时为 ``None``。
    :param host_assembly: 当前 Host opener assembly 结果。
    :param run_overrides: 本轮可映射的显式 override。
    :returns: 带完整 ``runner_options`` 与 ``agent_policy`` 的
        SubmitFollowupRequest。
    :raises ValueError: override 字段非法时由底层校验抛出。
    """

    base_request = compose_submit_followup_request(
        context=context,
        session_id=session_id,
        client_request_id=client_request_id,
        scene_inputs=scene_inputs,
        user_prompt=user_prompt,
        tool_names=tool_names,
        behavior=behavior,
        target_run_id=target_run_id,
    )
    return replace(
        base_request,
        runner_options=_runner_options_with_run_overrides(
            host_assembly=host_assembly,
            run_overrides=run_overrides,
        ),
        agent_policy=_agent_policy_with_run_overrides(
            host_assembly=host_assembly,
            run_overrides=run_overrides,
        ),
    )


def _compose_options(
    *,
    request: ServiceOpenHostAssemblyRequest,
    host_runtime: HostRuntimeProfileConfig,
    execution_profile: ExecutionProfileConfig,
    lane: RuntimeLaneConfig,
    ordinary_selection: RunnerOptionHintSelection,
    compactor_selection: RunnerOptionHintSelection,
    agent_policy_config: MergedAgentPolicyConfig,
    effective_tool_bundle: ToolBundle,
    compactor_prompts: _CompactorScenePrompts,
) -> OpenHostOptions:
    """组合 ``OpenHostOptions``。

    :param request: Service Host opener assembly 请求。
    :param host_runtime: 选中的 Host runtime profile。
    :param execution_profile: 选中的 execution profile。
    :param lane: 选中的 runtime lane。
    :param ordinary_selection: 普通 Run runner 选择。
    :param compactor_selection: compactor runner 选择。
    :param agent_policy_config: 合并后的 AgentPolicy 配置。
    :param effective_tool_bundle: 已补齐截断默认值的工具 bundle；没有业务工具时
        为 ``None``。
    :param compactor_prompts: compactor scene / baseline 装配后的输入。
    :returns: Host public opener options。
    :raises ValueError: worker backend 或 secret 映射失败时抛出。
    """

    if host_runtime.worker_backend != _WORKER_BACKEND_LOCAL:
        raise ValueError(f"unsupported host worker_backend: {host_runtime.worker_backend}")
    fins_awaiting_providers = request.discovered_tools._fins_awaiting_providers
    if any(
        metadata.mode is AwaitingResolutionMode.CALLBACK
        for metadata in fins_awaiting_providers
    ):
        raise ValueError(
            "active callback awaiting provider requires an authenticated callback "
            "transport before open_host"
        )
    tooling_options = _tooling_options_from_discovery(
        tool_bundle=effective_tool_bundle,
        source_refs=request.discovered_tools.source_refs,
        fins_awaiting_providers=fins_awaiting_providers,
        fins_awaiting_runtime=request.discovered_tools.fins_awaiting_runtime,
        duplicate_governance_policy_config=(
            execution_profile.tool_duplicate_governance_policy
        ),
        process_capsule_interrupt_policy_config=(
            host_runtime.process_capsule_interrupt_policy
        ),
    )
    wait_poller_policy = _wait_poller_policy_for_composition(
        config=host_runtime.wait_poller_policy,
        fins_awaiting_providers=fins_awaiting_providers,
        tooling_options=tooling_options,
    )
    return OpenHostOptions(
        db_path=resolve_workspace_path(request.workspace_root, host_runtime.sqlite.path),
        artifact_root=resolve_workspace_path(
            request.workspace_root,
            host_runtime.artifact_root,
        ),
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=host_runtime.sqlite.busy_timeout_seconds,
        sqlite_write_busy_retry_count=host_runtime.sqlite.write_busy_retry_count,
        sqlite_write_retry_initial_delay_seconds=(host_runtime.sqlite.write_retry_initial_delay_seconds),
        sqlite_write_retry_backoff_multiplier=(host_runtime.sqlite.write_retry_backoff_multiplier),
        sqlite_write_retry_max_delay_seconds=(host_runtime.sqlite.write_retry_max_delay_seconds),
        payload_inline_threshold_bytes=host_runtime.payload_inline_threshold_bytes,
        lane_db_path=resolve_workspace_path(
            request.workspace_root,
            request.config.runtime_lanes.coordinator.db_path,
        ),
        lane_name=lane.lane_name,
        lane_capacity=lane.capacity,
        lane_default_timeout_seconds=lane.default_timeout_seconds,
        lane_claim_ttl_seconds=lane.claim_ttl_seconds,
        lane_heartbeat_interval_seconds=lane.heartbeat_interval_seconds,
        worker_startup_timeout_seconds=host_runtime.worker_startup_timeout_seconds,
        dispatch_poll_interval_seconds=host_runtime.dispatch_poll_interval_seconds,
        ordinary_run_baseline=OrdinaryRunExecutionBaseline(
            runner_spec=_runner_spec_from_model(
                model=ordinary_selection.model,
                env=request.env,
            ),
            runner_options=_runner_options_from_hint(ordinary_selection.runner_option_hint),
            agent_policy=_agent_policy_from_merged(agent_policy_config),
        ),
        worker_factory=DefaultLocalEngineWorkerFactory(),
        tooling_options=tooling_options,
        context_budget_policy=default_context_budget_policy(
            context_window_size=ordinary_selection.model.context_window_tokens,
            soft_threshold_context_ratio=(execution_profile.context_budget_policy.soft_threshold_context_ratio),
            hard_threshold_context_ratio=(execution_profile.context_budget_policy.hard_threshold_context_ratio),
            max_proactive_compactions_per_run=(
                execution_profile.context_budget_policy.max_proactive_compactions_per_run
            ),
            max_reactive_compactions_per_run=(execution_profile.context_budget_policy.max_reactive_compactions_per_run),
            max_compaction_attempts_per_operation=(
                execution_profile.context_budget_policy.max_compaction_attempts_per_operation
            ),
            policy_ref=execution_profile.context_budget_policy.policy_ref,
        ),
        compactor_runner_baseline=CompactorRunnerBaseline(
            compactor_runner_spec=_runner_spec_from_model(
                model=compactor_selection.model,
                env=request.env,
            ),
            compactor_runner_options=_runner_options_from_hint(compactor_selection.runner_option_hint),
            compactor_agent_policy=compactor_prompts.agent_policy,
            compactor_system_prompt=compactor_prompts.system_prompt,
            compactor_user_prompt_template=compactor_prompts.user_prompt_template,
            compact_artifact_root=resolve_workspace_path(
                request.workspace_root,
                execution_profile.compactor_baseline.artifact_root,
            ),
            compact_artifact_create_parent_dirs=True,
        ),
        memory_projection_policy=_memory_projection_policy_from_config(
            execution_profile=execution_profile,
            context_window_size=ordinary_selection.model.context_window_tokens,
        ),
        memory_projection_catchup_batch_size=(host_runtime.memory_projection_catch_up_batch_size),
        enable_truncation_manager=(execution_profile.tool_truncation_policy.enabled),
        session_event_delivery_policy=HostSessionEventDeliveryPolicy(
            transient_mailbox_max_items=(
                host_runtime.session_event_delivery_policy.transient_mailbox_max_items
            ),
            max_subscriptions_per_session=(
                host_runtime.session_event_delivery_policy.max_subscriptions_per_session
            ),
        ),
        wait_poller_policy=wait_poller_policy,
    )


def _wait_poller_policy_for_composition(
    *,
    config: WaitPollerRuntimePolicyConfig,
    fins_awaiting_providers: tuple[_FinsAwaitingProviderMetadata, ...],
    tooling_options: HostToolingOptions | None,
) -> WaitPollerRuntimePolicy | None:
    """按 active typed modes 组合最终 Host wait poller policy。

    :param config: ConfigLoader 产出的完整 layer-neutral policy snapshot。
    :param fins_awaiting_providers: active Fins typed metadata collection。
    :param tooling_options: 已按同一 collection 构造的 Host tooling options。
    :returns: 有 active poll provider 时的一对一 Host policy；否则为 ``None``。
    :raises ValueError: enabled policy 对应的 poll registry 缺失或为空时抛出。
    """

    if not any(
        metadata.mode is AwaitingResolutionMode.POLL
        for metadata in fins_awaiting_providers
    ):
        return None
    policy = _wait_poller_runtime_policy_from_config(config)
    if policy.enabled:
        registry = (
            None
            if tooling_options is None
            else tooling_options.wait_poll_adapter_registry
        )
        if (
            registry is None
            or registry.resolve_adapter(FINS_INGESTION_WAIT_ADAPTER_KEY) is None
        ):
            raise ValueError(
                "enabled wait poller policy requires a non-empty poll adapter "
                "registry before open_host"
            )
    return policy


def _wait_poller_runtime_policy_from_config(
    config: WaitPollerRuntimePolicyConfig,
) -> WaitPollerRuntimePolicy:
    """把 ConfigLoader policy snapshot 一对一投影为 Host 值对象。

    :param config: 完整 layer-neutral wait poller policy snapshot。
    :returns: 字段值不变的 Host typed policy。
    :raises ValueError: Host 值对象校验失败时抛出。
    """

    return WaitPollerRuntimePolicy(
        enabled=config.enabled,
        poll_interval_seconds=config.poll_interval_seconds,
        claim_ttl_seconds=config.claim_ttl_seconds,
        claim_batch_size=config.claim_batch_size,
        backoff_initial_delay_seconds=config.backoff_initial_delay_seconds,
        backoff_multiplier=config.backoff_multiplier,
        backoff_max_delay_seconds=config.backoff_max_delay_seconds,
        not_ready_observe_interval_seconds=(
            config.not_ready_observe_interval_seconds
        ),
        idle_poll_interval_seconds=config.idle_poll_interval_seconds,
        adapter_call_timeout_seconds=config.adapter_call_timeout_seconds,
        close_drain_timeout_seconds=config.close_drain_timeout_seconds,
        max_outstanding_adapter_calls=config.max_outstanding_adapter_calls,
    )


def _prepare_compactor_scene_inputs(
    request: ServiceOpenHostAssemblyRequest,
    *,
    execution_profile: ExecutionProfileConfig,
) -> PreparedSceneInputs:
    """装配 Host-owned compactor 使用的 configured compactor scene。

    :param request: Service open_host assembly 请求。
    :param execution_profile: 选中的 execution profile。
    :returns: compactor scene 装配输出。
    :raises ScenePrepareError: compactor scene asset 违反 scene contract 时抛出。
    """

    return prepare_scene(
        ScenePrepareRequest(
            scene_id=execution_profile.compactor_baseline.scene_id,
            scene_manifest_root=request.locations.scene_manifest_root,
            prompt_asset_root=request.locations.prompt_asset_root,
            context_slot_values={},
            available_tools=SceneToolCatalog.from_tool_bundle(request.discovered_tools.tool_bundle),
        )
    )


def _compactor_prompts_from_scene_inputs(
    scene_inputs: PreparedSceneInputs,
    *,
    user_prompt_template: str,
) -> _CompactorScenePrompts:
    """从 compactor scene 与 baseline prompt asset 中读取 compactor 输入。

    :param scene_inputs: compactor scene 装配输出。
    :param user_prompt_template: compactor baseline 指向的 user prompt template。
    :returns: compactor prompt 与 Agent policy。
    :raises ValueError: compactor scene 未提供恰好一个 system prompt
        fragment，或未声明完整 Agent policy 时抛出。
    """

    if len(scene_inputs.system_messages) != _COMPACTOR_SYSTEM_PROMPT_FRAGMENT_COUNT:
        raise ValueError("compactor scene must provide exactly one system prompt fragment")
    return _CompactorScenePrompts(
        system_prompt=scene_inputs.system_messages[0],
        user_prompt_template=user_prompt_template,
        agent_policy=_compactor_agent_policy_from_scene_inputs(scene_inputs),
    )


def _read_compactor_user_prompt_template(
    request: ServiceOpenHostAssemblyRequest,
    *,
    execution_profile: ExecutionProfileConfig,
) -> str:
    """读取 compactor baseline 指向的 user prompt template。

    :param request: Service Host opener assembly 请求。
    :param execution_profile: 选中的 execution profile。
    :returns: user prompt template 文本。
    :raises ValueError: 路径是绝对路径或逃逸 prompt asset root 时抛出。
    :raises OSError: prompt asset 文件读取失败时抛出。
    """

    template_path = _resolve_prompt_asset_path(
        request.locations.prompt_asset_root,
        execution_profile.compactor_baseline.user_prompt_template_path,
        field_name="compactor_baseline.user_prompt_template_path",
    )
    return template_path.read_text(encoding="utf-8")


def _resolve_prompt_asset_path(
    prompt_asset_root: pathlib.Path,
    configured_path: str,
    *,
    field_name: str,
) -> pathlib.Path:
    """解析 prompt asset 相对路径并禁止逃逸根目录。

    :param prompt_asset_root: prompt asset 根目录。
    :param configured_path: 配置中的相对路径。
    :param field_name: 错误消息字段名。
    :returns: 解析后的 prompt asset 路径。
    :raises ValueError: 路径为空、绝对路径或逃逸根目录时抛出。
    """

    _require_non_empty_text(configured_path, field_name=field_name)
    path = pathlib.Path(configured_path)
    if path.is_absolute():
        raise ValueError(f"{field_name} must be relative")
    resolved_root = prompt_asset_root.resolve()
    resolved_path = (resolved_root / path).resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"{field_name} escapes prompt asset root") from exc
    return resolved_path


def _require_non_empty_text(value: str, *, field_name: str) -> str:
    """校验必填文本字段非空。

    :param value: 待校验文本。
    :param field_name: 错误消息中的字段名。
    :returns: 原文本。
    :raises ValueError: 文本为空时抛出。
    """

    if value.strip() == "":
        raise ValueError(f"{field_name} must not be empty")
    return value


def _compactor_agent_policy_from_scene_inputs(
    scene_inputs: PreparedSceneInputs,
) -> AgentPolicy:
    """从 compactor scene agent_policy 生成完整 AgentPolicy。

    :param scene_inputs: compactor scene 装配输出。
    :returns: compactor Agent policy。
    :raises ValueError: scene 未声明完整 compactor Agent policy 时抛出。
    """

    override = scene_inputs.agent_policy_override
    if override is None:
        raise ValueError("compactor scene must declare agent_policy")
    if override.max_iterations is None:
        raise ValueError("compactor scene agent_policy.max_iterations is required")
    if override.continuation_max_attempts is None:
        raise ValueError("compactor scene agent_policy.continuation_max_attempts is required")
    if override.allow_tool_calls is None:
        raise ValueError("compactor scene agent_policy.allow_tool_calls is required")
    if override.tool_execution_timeout_seconds is None:
        raise ValueError("compactor scene agent_policy.tool_execution_timeout_seconds is required")
    if override.fallback_mode is None:
        raise ValueError("compactor scene agent_policy.fallback_mode is required")
    if override.fallback_prompt is None:
        raise ValueError("compactor scene agent_policy.fallback_prompt is required")
    if override.continuation_prompt is None:
        raise ValueError("compactor scene agent_policy.continuation_prompt is required")
    if override.max_consecutive_failed_tool_batches is None:
        raise ValueError("compactor scene agent_policy.max_consecutive_failed_tool_batches " "is required")
    return AgentPolicy(
        max_iterations=override.max_iterations,
        continuation_max_attempts=override.continuation_max_attempts,
        allow_tool_calls=override.allow_tool_calls,
        tool_execution_timeout_seconds=override.tool_execution_timeout_seconds,
        fallback_mode=_agent_fallback_mode_from_config(override.fallback_mode.value),
        fallback_prompt=override.fallback_prompt,
        continuation_prompt=override.continuation_prompt,
        max_consecutive_failed_tool_batches=(override.max_consecutive_failed_tool_batches),
    )


def _select_host_runtime_id(config: RuntimeConfig, explicit_runtime_id: str | None) -> str:
    """选择 Host runtime id。

    :param config: runtime config 总视图。
    :param explicit_runtime_id: 显式 Host runtime id。
    :returns: 已存在的 Host runtime id。
    :raises RuntimeAssemblySelectionError: id 不存在时抛出。
    """

    runtime_id = explicit_runtime_id if explicit_runtime_id is not None else config.host_runtime.default_host_runtime_id
    if runtime_id not in config.host_runtime.runtimes:
        raise RuntimeAssemblySelectionError(f"host runtime not found: {runtime_id}")
    return runtime_id


def _select_execution_profile_id(config: RuntimeConfig, explicit_profile_id: str | None) -> str:
    """选择 execution profile id。

    :param config: runtime config 总视图。
    :param explicit_profile_id: 显式 execution profile id。
    :returns: 已存在的 execution profile id。
    :raises RuntimeAssemblySelectionError: id 不存在时抛出。
    """

    profile_id = (
        explicit_profile_id
        if explicit_profile_id is not None
        else config.execution_profiles.default_execution_profile_id
    )
    if profile_id not in config.execution_profiles.execution_profiles:
        raise RuntimeAssemblySelectionError(f"execution profile not found: {profile_id}")
    return profile_id


def _model_runner_override_from_overrides(
    overrides: ServiceAssemblyOverrides,
) -> ModelRunnerHintOverride | None:
    """把显式模型 / hint override 转为 runtime helper 输入。

    :param overrides: Service assembly 显式 override。
    :returns: typed model runner override；未提供时为 ``None``。
    :raises ValueError: override 文本为空时抛出。
    """

    if overrides.model_id is None and overrides.runner_option_hint_id is None:
        return None
    _require_optional_non_empty_text(
        overrides.model_id,
        field_name="ServiceAssemblyOverrides.model_id",
    )
    _require_optional_non_empty_text(
        overrides.runner_option_hint_id,
        field_name="ServiceAssemblyOverrides.runner_option_hint_id",
    )
    return ModelRunnerHintOverride(
        model_id=overrides.model_id,
        runner_option_hint_id=overrides.runner_option_hint_id,
    )


def _tool_discovery_spec(
    provider_config: ToolDiscoveryProviderConfig,
) -> ToolsDiscoveryProviderSpec:
    """把单个 provider config 映射为 ToolsDiscovery spec。

    :param provider_config: 已完成运行时参数装配的 provider config。
    :returns: ToolsDiscovery 可消费的 provider spec。
    :raises ValueError: provider 同时缺少 import path 与 entry point 时抛出。
    """

    if provider_config.import_path is not None:
        location = PythonImportPathProvider(provider_config.import_path)
    elif provider_config.entry_point is not None:
        location = PackageEntryPointProvider(
            group=provider_config.entry_point.group,
            name=provider_config.entry_point.name,
        )
    else:
        raise ValueError(
            "tool discovery provider must declare import_path or entry_point: " f"{provider_config.provider_id}"
        )
    return ToolsDiscoveryProviderSpec(
        spec_id=provider_config.provider_id,
        location=location,
        enabled=provider_config.enabled,
        config=provider_config.config,
    )


def _fins_awaiting_provider_metadata_from_configs(
    provider_configs: Sequence[ToolDiscoveryProviderConfig],
) -> tuple[_FinsAwaitingProviderMetadata, ...]:
    """一次校验 provider configs 并构造 active Fins typed metadata。

    本函数先遍历全部 effective configs 完成 owner 路由与恢复模式校验，再由
    ``enabled`` 决定是否进入 active collection。后续消费者不得重读 raw mode。

    :param provider_configs: 已完成 workspace 等层中立参数装配的 configs。
    :returns: active Fins awaiting provider typed metadata。
    :raises ValueError: Fins mode 非法、recognized non-awaiting provider 误用字段、
        workspace root 非法或 active spec id 重复时抛出。
    """

    metadata: list[_FinsAwaitingProviderMetadata] = []
    for provider_config in provider_configs:
        tool_name = _fins_awaiting_tool_name_from_provider_config(provider_config)
        if tool_name is None:
            if (
                _is_recognized_non_awaiting_provider_config(provider_config)
                and AWAITING_RESOLUTION_MODE_CONFIG_FIELD in provider_config.config
            ):
                raise ValueError(
                    "non-awaiting provider "
                    f"{provider_config.provider_id} must not declare "
                    "config.awaiting_resolution_mode"
                )
            continue
        mode = parse_awaiting_resolution_mode(provider_config.config)
        if not provider_config.enabled:
            continue
        workspace_root = _fins_workspace_root_from_provider_config(provider_config)
        metadata.append(
            _fins_awaiting_provider_metadata(
                provider_config=provider_config,
                tool_name=tool_name,
                workspace_root=workspace_root,
                mode=mode,
            )
        )
    result = tuple(metadata)
    _fins_awaiting_metadata_by_spec_id(result)
    return result


def _fins_awaiting_metadata_by_spec_id(
    metadata: Sequence[_FinsAwaitingProviderMetadata],
) -> dict[str, _FinsAwaitingProviderMetadata]:
    """按 provider spec id 索引 active Fins typed metadata。

    :param metadata: provider-assembly boundary 产出的 typed metadata。
    :returns: spec id 到 metadata 的私有索引。
    :raises ValueError: active provider spec id 重复时抛出。
    """

    result: dict[str, _FinsAwaitingProviderMetadata] = {}
    for item in metadata:
        if item.spec_id in result:
            raise ValueError(f"duplicate Fins awaiting provider id: {item.spec_id}")
        result[item.spec_id] = item
    return result


def _active_fins_awaiting_provider_metadata(
    metadata: Sequence[_FinsAwaitingProviderMetadata],
    *,
    available_tool_names: frozenset[str],
) -> tuple[_FinsAwaitingProviderMetadata, ...]:
    """在 owner parse 后按 enabled discovery output 收敛 active metadata。

    :param metadata: 已通过 owner parser 且 enabled 的 Fins metadata。
    :param available_tool_names: 本次 ToolBundle 实际包含的工具名。
    :returns: 只包含实际可用 awaiting 工具的 typed metadata。
    :raises Exception: 不主动抛出异常。
    """

    return tuple(
        item for item in metadata if item.tool_name in available_tool_names
    )


def _tool_discovery_bindings(
    provider_configs: Sequence[ToolDiscoveryProviderConfig],
    *,
    fins_awaiting_providers: tuple[_FinsAwaitingProviderMetadata, ...],
    fins_awaiting_runtime: FinsObservationRuntime | None,
) -> tuple[ToolsDiscoveryProviderBinding, ...]:
    """构造 ToolsDiscovery provider bindings。

    Fins awaiting providers 由 Service 使用同一个 ingestion runtime 生成等价
    provider output；其它 provider 仍走 runtime discovery 的动态解析。

    :param provider_configs: 已完成运行时参数装配的 provider configs。
    :param fins_awaiting_providers: 一次解析得到的 active Fins typed metadata。
    :param fins_awaiting_runtime: Fins awaiting 共享 runtime；无 Fins awaiting
        provider 时为 ``None``。
    :returns: provider bindings。
    :raises ValueError: 启用 Fins awaiting provider 但缺少共享 runtime 时抛出。
    """

    metadata_by_spec_id = _fins_awaiting_metadata_by_spec_id(
        fins_awaiting_providers
    )
    bindings: list[ToolsDiscoveryProviderBinding] = []
    for provider_config in provider_configs:
        spec = _tool_discovery_spec(provider_config)
        metadata = metadata_by_spec_id.get(provider_config.provider_id)
        if not provider_config.enabled:
            bindings.append(
                ToolsDiscoveryProviderBinding(
                    spec=spec,
                    provider=_DisabledProviderCallable(),
                )
            )
        elif metadata is not None:
            if not isinstance(fins_awaiting_runtime, FinsIngestionRuntime):
                raise ValueError(
                    "enabled Fins awaiting provider requires shared ingestion runtime"
                )
            bindings.append(
                ToolsDiscoveryProviderBinding(
                    spec=spec,
                    provider=_FinsAwaitingProviderCallable(
                        metadata=metadata,
                        runtime=fins_awaiting_runtime,
                    ),
                )
            )
        else:
            bindings.append(
                ToolsDiscoveryProviderBinding(
                    spec=spec,
                    provider=resolve_provider_callable(spec),
                )
            )
    return tuple(bindings)


def _shared_fins_awaiting_runtime_from_provider_metadata(
    metadata: tuple[_FinsAwaitingProviderMetadata, ...],
) -> FinsIngestionRuntime | None:
    """从 active Fins typed metadata 创建共享 ingestion runtime。

    :param metadata: provider-assembly boundary 一次解析的 active metadata。
    :returns: 共享 ingestion runtime；没有启用 Fins awaiting provider 时为
        ``None``。
    :raises ValueError: workspace root 缺失、非绝对或不一致时抛出。
    :raises OSError: Fins runtime 仓储初始化失败时抛出。
    """

    if not metadata:
        return None
    workspace_root = _single_fins_workspace_root(
        tuple(item.workspace_root for item in metadata)
    )
    return DefaultFinsRuntime.create(
        workspace_root=workspace_root
    ).get_ingestion_runtime()


def _fins_awaiting_provider_metadata(
    *,
    provider_config: ToolDiscoveryProviderConfig,
    tool_name: str,
    workspace_root: pathlib.Path,
    mode: AwaitingResolutionMode,
) -> _FinsAwaitingProviderMetadata:
    """按 Fins awaiting 工具名返回 provider 元数据。

    :param provider_config: 当前 effective provider config。
    :param tool_name: Fins awaiting 工具名。
    :param workspace_root: 已校验的绝对 workspace root。
    :param mode: Fins owner parser 产出的 typed 恢复模式。
    :returns: provider 元数据。
    :raises ValueError: 工具名不受支持时抛出。
    """

    if tool_name == FINS_DOWNLOAD_AWAITING_TOOL_NAME:
        return _FinsAwaitingProviderMetadata(
            spec_id=provider_config.provider_id,
            tool_name=tool_name,
            provider_id=_FINS_DOWNLOAD_PROVIDER_ID,
            version_ref=_FINS_DOWNLOAD_VERSION_REF,
            source_id=_FINS_DOWNLOAD_SOURCE_ID,
            workspace_root=workspace_root,
            mode=mode,
        )
    if tool_name == FINS_PREPROCESS_AWAITING_TOOL_NAME:
        return _FinsAwaitingProviderMetadata(
            spec_id=provider_config.provider_id,
            tool_name=tool_name,
            provider_id=_FINS_PREPROCESS_PROVIDER_ID,
            version_ref=_FINS_PREPROCESS_VERSION_REF,
            source_id=_FINS_PREPROCESS_SOURCE_ID,
            workspace_root=workspace_root,
            mode=mode,
        )
    if tool_name == FINS_UPLOAD_AWAITING_TOOL_NAME:
        return _FinsAwaitingProviderMetadata(
            spec_id=provider_config.provider_id,
            tool_name=tool_name,
            provider_id=_FINS_UPLOAD_PROVIDER_ID,
            version_ref=_FINS_UPLOAD_VERSION_REF,
            source_id=_FINS_UPLOAD_SOURCE_ID,
            workspace_root=workspace_root,
            mode=mode,
        )
    raise ValueError(f"unsupported Fins awaiting tool: {tool_name}")


def _fins_awaiting_tool_definition(
    *,
    tool_name: str,
    runtime: FinsIngestionRuntime,
) -> ToolDefinition:
    """按工具名构造共享 runtime 的 Fins awaiting 工具声明。

    :param tool_name: Fins awaiting 工具名。
    :param runtime: 共享 ingestion runtime。
    :returns: 工具声明。
    :raises ValueError: 工具名不受支持时抛出。
    """

    if tool_name == FINS_DOWNLOAD_AWAITING_TOOL_NAME:
        return build_fins_download_tool(runtime)
    if tool_name == FINS_PREPROCESS_AWAITING_TOOL_NAME:
        return build_fins_preprocess_tool(runtime)
    if tool_name == FINS_UPLOAD_AWAITING_TOOL_NAME:
        return build_fins_upload_tool(runtime)
    raise ValueError(f"unsupported Fins awaiting tool: {tool_name}")


def _effective_tool_provider_config(
    provider_config: ToolDiscoveryProviderConfig,
    *,
    workspace_root: pathlib.Path | None,
    fins_workspace_root_override: pathlib.Path | None,
) -> Mapping[str, JsonValue]:
    """生成传给工具发现 provider 的 effective config。

    :param provider_config: ConfigLoader 产出的 provider typed config。
    :param workspace_root: 当前运行时 workspace root；为 ``None`` 时不注入。
    :param fins_workspace_root_override: 显式 Fins effective workspace root override。
    :returns: provider 可直接消费的 effective config。
    :raises ValueError: Fins workspace root 或 Web storage state 目录配置类型
        非法，或相对路径缺少解析基准时抛出。
    """

    effective_config: dict[str, JsonValue] = dict(provider_config.config)
    changed = False
    if _is_fins_workspace_bound_provider_config(provider_config):
        effective_workspace_root = _effective_fins_workspace_root_config_value(
            provider_config,
            workspace_root=workspace_root,
            fins_workspace_root_override=fins_workspace_root_override,
        )
        if effective_workspace_root is not None:
            effective_config[_FINS_WORKSPACE_ROOT_CONFIG_FIELD] = (
                effective_workspace_root
            )
            changed = True
    effective_storage_state_dir = _effective_web_storage_state_dir_config_value(
        provider_config,
        workspace_root=workspace_root,
    )
    if effective_storage_state_dir is not None:
        effective_config[_WEB_PLAYWRIGHT_STORAGE_STATE_DIR_CONFIG_FIELD] = (
            effective_storage_state_dir
        )
        changed = True
    if not changed:
        return provider_config.config
    return effective_config


def _effective_fins_workspace_root_config_value(
    provider_config: ToolDiscoveryProviderConfig,
    *,
    workspace_root: pathlib.Path | None,
    fins_workspace_root_override: pathlib.Path | None,
) -> str | None:
    """解析 Fins provider effective workspace root 配置值。

    :param provider_config: ConfigLoader 产出的 provider typed config。
    :param workspace_root: 当前运行时 workspace root；为 ``None`` 时无法解析
        相对路径。
    :param fins_workspace_root_override: 已由调用方明确产生的 Fins 绝对
        effective root；非 ``None`` 时在 raw 语法校验后支配路径选择。
    :returns: 需要写入 effective config 的绝对 workspace root 字符串；返回
        ``None`` 表示保留原始 config。
    :raises ValueError: 已配置 workspace root 不是字符串、为空字符串，或相对
        路径缺少解析基准时抛出。
    """

    configured_workspace_root = provider_config.config.get(
        _FINS_WORKSPACE_ROOT_CONFIG_FIELD
    )
    stripped_workspace_root: str | None = None
    if configured_workspace_root is not None:
        if not isinstance(configured_workspace_root, str):
            raise ValueError(
                "Fins provider "
                f"{provider_config.provider_id} config.workspace_root must be a string"
            )
        stripped_workspace_root = configured_workspace_root.strip()
        if stripped_workspace_root == "":
            raise ValueError(
                "Fins provider "
                f"{provider_config.provider_id} config.workspace_root must be non-empty"
            )
    if fins_workspace_root_override is not None:
        expanded_override = fins_workspace_root_override.expanduser()
        if not expanded_override.is_absolute():
            raise ValueError("Fins workspace root override must be absolute")
        return str(expanded_override.resolve(strict=False))
    if stripped_workspace_root is None:
        if workspace_root is None:
            return None
        return str(workspace_root.expanduser().resolve(strict=False))
    configured_path = pathlib.Path(stripped_workspace_root).expanduser()
    if configured_path.is_absolute():
        return str(configured_path.resolve(strict=False))
    if workspace_root is None:
        raise ValueError(
            "Fins provider "
            f"{provider_config.provider_id} relative config.workspace_root requires runtime workspace_root"
        )
    return str(resolve_workspace_path(workspace_root, stripped_workspace_root))


def _effective_web_storage_state_dir_config_value(
    provider_config: ToolDiscoveryProviderConfig,
    *,
    workspace_root: pathlib.Path | None,
) -> str | None:
    """解析 Web provider effective storage state 目录。

    :param provider_config: ConfigLoader 产出的 provider typed config。
    :param workspace_root: 当前运行时 workspace root；为 ``None`` 时无法解析
        相对路径。
    :returns: 需要写入 effective config 的绝对目录字符串；返回 ``None`` 表示
        保留原始 config。
    :raises ValueError: 已配置 storage state 目录不是字符串，或相对路径缺少
        解析基准时抛出。
    """

    if not _is_web_tools_provider_config(provider_config):
        return None
    configured_dir = provider_config.config.get(
        _WEB_PLAYWRIGHT_STORAGE_STATE_DIR_CONFIG_FIELD
    )
    if configured_dir is None:
        return None
    if not isinstance(configured_dir, str):
        raise ValueError(
            "Web provider "
            f"{provider_config.provider_id} config.playwright_storage_state_dir "
            "must be a string"
        )
    stripped_dir = configured_dir.strip()
    if stripped_dir == "":
        return configured_dir
    configured_path = pathlib.Path(stripped_dir).expanduser()
    if configured_path.is_absolute():
        return str(configured_path.resolve(strict=False))
    if workspace_root is None:
        raise ValueError(
            "Web provider "
            f"{provider_config.provider_id} relative "
            "config.playwright_storage_state_dir requires runtime workspace_root"
        )
    return str(resolve_workspace_path(workspace_root, stripped_dir))


def _is_fins_workspace_bound_provider_config(
    provider_config: ToolDiscoveryProviderConfig,
) -> bool:
    """判断 provider 是否需要 Fins workspace root 进入 effective spec。

    :param provider_config: ConfigLoader 产出的 provider typed config。
    :returns: 是 Fins workspace-bound provider 时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    if (
        provider_config.provider_id in _FINS_READ_PROVIDER_IDS
        or provider_config.import_path in _FINS_READ_IMPORT_PATHS
        or provider_config.source_id in _FINS_READ_SOURCE_IDS
    ):
        return True
    return _fins_awaiting_tool_name_from_provider_config(provider_config) is not None


def _is_web_tools_provider_config(
    provider_config: ToolDiscoveryProviderConfig,
) -> bool:
    """判断 provider 是否是 Web tools provider。

    :param provider_config: ConfigLoader 产出的 provider typed config。
    :returns: 是 Web tools provider 时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return (
        provider_config.provider_id in _WEB_TOOLS_PROVIDER_IDS
        or provider_config.import_path in _WEB_TOOLS_IMPORT_PATHS
        or provider_config.source_id in _WEB_TOOLS_SOURCE_IDS
    )


def _tool_bundle_with_effective_truncation(
    *,
    tool_bundle: ToolBundle,
    execution_profile: ExecutionProfileConfig,
) -> ToolBundle:
    """按 tool truncation policy 补齐工具声明的 effective truncate spec。

    :param tool_bundle: ToolsDiscovery 输出的业务工具 bundle。
    :param execution_profile: 当前 execution profile。
    :returns: 补齐截断默认值后的业务工具 bundle。
    :raises ValueError: 截断声明与 policy 默认值组合非法时抛出。
    """

    if not tool_bundle.definitions:
        return tool_bundle
    if not execution_profile.tool_truncation_policy.enabled:
        return tool_bundle
    definitions: list[ToolDefinition] = []
    for definition in tool_bundle.definitions:
        if definition.truncate is None:
            definitions.append(definition)
            continue
        definitions.append(
            replace(
                definition,
                truncate=effective_tool_truncate_spec_from_policy(
                    definition.truncate,
                    policy=execution_profile.tool_truncation_policy,
                ),
            )
        )
    return ToolBundle(definitions=tuple(definitions))


def _assembly_diagnostics(
    *,
    locations: RuntimeLocations,
    host_runtime_id: str,
    execution_profile_id: str,
    execution_profile: ExecutionProfileConfig,
    lane: RuntimeLaneConfig,
    ordinary_selection: RunnerOptionHintSelection,
    compactor_selection: RunnerOptionHintSelection,
    ordinary_profile_compatibility: ExecutionProfileCompatibilityDiagnostic,
    compactor_profile_compatibility: ExecutionProfileCompatibilityDiagnostic,
    agent_policy_config: MergedAgentPolicyConfig,
    tool_provider_reports: tuple[str, ...],
    scene_inputs: PreparedSceneInputs,
) -> ServiceOpenHostAssemblyDiagnostics:
    """构造调用 Host 前的 assembly diagnostics。

    :param locations: runtime 位置解析结果。
    :param host_runtime_id: Host runtime id。
    :param execution_profile_id: execution profile id。
    :param execution_profile: execution profile 配置。
    :param lane: runtime lane 配置。
    :param ordinary_selection: 普通 Run 模型选择结果。
    :param compactor_selection: compactor 模型选择结果。
    :param ordinary_profile_compatibility: 普通 Run profile / model 兼容诊断。
    :param compactor_profile_compatibility: compactor profile / model 兼容诊断。
    :param agent_policy_config: 合并后的 AgentPolicy 字段集。
    :param tool_provider_reports: 工具 provider 报告行。
    :param scene_inputs: ScenePrepare 输出。
    :returns: assembly diagnostics。
    :raises Exception: provider extension DSL 非法时由 helper 抛出。
    """

    truncation_defaults = tool_truncation_policy_defaults(execution_profile.tool_truncation_policy)
    return ServiceOpenHostAssemblyDiagnostics(
        config_overlay_dir=locations.config_overlay_dir,
        prompt_asset_root=locations.prompt_asset_root,
        scene_manifest_root=locations.scene_manifest_root,
        host_runtime_id=host_runtime_id,
        execution_profile_id=execution_profile_id,
        model_id=ordinary_selection.model_id,
        model_source=ordinary_selection.diagnostic.selected_model_source,
        runner_option_hint_id=ordinary_selection.runner_option_hint_id,
        runner_option_hint_source=(ordinary_selection.diagnostic.selected_runner_option_hint_source),
        compactor_model_id=compactor_selection.model_id,
        compactor_runner_option_hint_id=compactor_selection.runner_option_hint_id,
        lane_name=lane.lane_name,
        tool_provider_reports=tool_provider_reports,
        tool_selection=_format_tool_selection(scene_inputs),
        context_budget_policy_ref=execution_profile.context_budget_policy.policy_ref,
        agent_policy_sources=tuple(
            f"{field_name}:{source}" for field_name, source in sorted(agent_policy_config.field_sources.items())
        ),
        tool_truncation_policy=(
            "enabled=" f"{truncation_defaults.enabled},ttl={truncation_defaults.default_ttl_seconds}"
        ),
        ordinary_provider_extension_status=_provider_extension_status(ordinary_selection.model),
        compactor_provider_extension_status=_provider_extension_status(compactor_selection.model),
        ordinary_profile_compatibility=ordinary_profile_compatibility,
        compactor_profile_compatibility=compactor_profile_compatibility,
    )


def _runner_spec_from_model(*, model: ModelConfig, env: Mapping[str, str]) -> RunnerSpec:
    """把 ModelConfig 映射为 Engine RunnerSpec。

    :param model: 模型配置。
    :param env: 环境变量映射。
    :returns: RunnerSpec。
    :raises ValueError: 需要 API key 但环境变量缺失，或 header 存在未解析
        占位符时抛出。
    """

    return RunnerSpec(
        provider=model.provider,
        model=model.model,
        endpoint=model.endpoint,
        api_key_ref=model.api_key_ref,
        headers=_render_headers(
            model.headers,
            api_key_ref=model.api_key_ref,
            env=env,
        ),
        client_correlation_policy=(
            ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID
        ),
        supports_tool_calling=model.supports_tool_calling,
        supports_streaming=model.supports_stream,
        supports_stream_usage=model.supports_stream_usage,
        default_timeout_seconds=model.default_timeout_seconds,
        max_retries=model.max_retries,
        provider_request=provider_request_extension_from_json(model.provider_request_extension),
        stream_idle_timeout_seconds=model.sse_idle_timeout_seconds,
        stream_idle_heartbeat_seconds=model.sse_heartbeat_seconds,
    )


def _render_headers(headers: Mapping[str, str], *, api_key_ref: str | None, env: Mapping[str, str]) -> dict[str, str]:
    """渲染 provider headers 中的环境变量占位符。

    :param headers: 配置 headers。
    :param api_key_ref: API key 环境变量名；``None`` 表示无需注入 API key。
    :param env: 环境变量映射。
    :returns: 渲染后的 headers。
    :raises ValueError: 需要 API key 但环境变量缺失，或 header 存在未解析
        占位符时抛出。
    """

    api_key: str | None = None
    if api_key_ref is not None:
        api_key = env.get(api_key_ref)
        if api_key is None or api_key.strip() == "":
            raise ValueError(f"missing env {api_key_ref}")
    rendered: dict[str, str] = {}
    for name, value in headers.items():
        rendered_value = value
        if api_key_ref is not None and api_key is not None:
            rendered_value = value.replace(
                f"{{{{{api_key_ref}}}}}",
                api_key.strip(),
            )
        unresolved = _ENV_PLACEHOLDER_PATTERN.search(rendered_value)
        if unresolved is not None:
            raise ValueError("header contains unresolved env placeholder: " f"{name} -> {unresolved.group(1)}")
        rendered[name] = rendered_value
    return rendered


def _runner_options_from_hint(
    hint: RunnerOptionHintConfig,
) -> RunnerCallOptions:
    """把 runtime runner option hint 映射为 RunnerCallOptions。

    :param hint: 选中的 runner option hint。
    :returns: RunnerCallOptions。
    :raises ValueError: 字段非法时由底层抛出。
    """

    return RunnerCallOptions(
        temperature=hint.temperature,
        max_tokens=None,
        top_p=hint.top_p,
        stream=hint.stream,
    )


def _runner_options_with_run_overrides(
    *,
    host_assembly: ServiceOpenHostAssemblyResult,
    run_overrides: ServiceRunOverrides,
) -> RunnerCallOptions:
    """按本轮 override 生成完整 RunnerCallOptions。

    :param host_assembly: 当前 Host opener assembly 结果。
    :param run_overrides: 单次 Run 显式 override。
    :returns: 完整 RunnerCallOptions。
    :raises ValueError: override 字段非法时由 dataclass 校验抛出。
    """

    baseline = _runner_options_from_hint(
        host_assembly.ordinary_selection.runner_option_hint
    )
    if run_overrides.temperature is None:
        return baseline
    return replace(baseline, temperature=run_overrides.temperature)


def _agent_policy_baseline_from_config(
    profile: AgentPolicyConfig,
) -> AgentPolicyBaseline:
    """从内嵌 Agent policy 配置投影 runtime helper 所需基线字段。

    :param profile: ConfigLoader 输出的内嵌 Agent policy 配置。
    :returns: 与 profile 同值的基线字段集。
    :raises Exception: 不主动抛出异常。
    """

    return AgentPolicyBaseline(
        max_iterations=profile.max_iterations,
        continuation_max_attempts=profile.continuation_max_attempts,
        allow_tool_calls=profile.allow_tool_calls,
        tool_execution_timeout_seconds=profile.tool_execution_timeout_seconds,
        fallback_mode=profile.fallback_mode,
        fallback_prompt=profile.fallback_prompt,
        continuation_prompt=profile.continuation_prompt,
        max_consecutive_failed_tool_batches=(profile.max_consecutive_failed_tool_batches),
    )


def _agent_policy_with_run_overrides(
    *,
    host_assembly: ServiceOpenHostAssemblyResult,
    run_overrides: ServiceRunOverrides,
) -> AgentPolicy:
    """按本轮 override 生成完整 AgentPolicy。

    :param host_assembly: 当前 Host opener assembly 结果。
    :param run_overrides: 单次 Run 显式 override。
    :returns: 完整 AgentPolicy。
    :raises ValueError: fallback mode 或 AgentPolicy 字段非法时抛出。
    """

    baseline = _agent_policy_from_merged(host_assembly.agent_policy_config)
    fallback_mode = (
        baseline.fallback_mode
        if run_overrides.fallback_mode is None
        else _agent_fallback_mode_from_config(run_overrides.fallback_mode)
    )
    return AgentPolicy(
        max_iterations=(
            baseline.max_iterations
            if run_overrides.max_iterations is None
            else run_overrides.max_iterations
        ),
        continuation_max_attempts=baseline.continuation_max_attempts,
        allow_tool_calls=baseline.allow_tool_calls,
        tool_execution_timeout_seconds=(
            baseline.tool_execution_timeout_seconds
            if run_overrides.tool_execution_timeout_seconds is None
            else run_overrides.tool_execution_timeout_seconds
        ),
        fallback_mode=fallback_mode,
        fallback_prompt=(
            baseline.fallback_prompt
            if run_overrides.fallback_prompt is None
            else run_overrides.fallback_prompt
        ),
        continuation_prompt=baseline.continuation_prompt,
        max_consecutive_failed_tool_batches=(
            baseline.max_consecutive_failed_tool_batches
            if run_overrides.max_consecutive_failed_tool_batches is None
            else run_overrides.max_consecutive_failed_tool_batches
        ),
    )


def _agent_policy_from_merged(config: MergedAgentPolicyConfig) -> AgentPolicy:
    """把 runtime-neutral merged AgentPolicy 字段映射为 Engine AgentPolicy。

    :param config: 合并后的 AgentPolicy 字段集。
    :returns: Engine AgentPolicy。
    :raises ValueError: fallback mode 非法时抛出。
    """

    return AgentPolicy(
        max_iterations=config.max_iterations,
        continuation_max_attempts=config.continuation_max_attempts,
        allow_tool_calls=config.allow_tool_calls,
        tool_execution_timeout_seconds=config.tool_execution_timeout_seconds,
        fallback_mode=_agent_fallback_mode_from_config(config.fallback_mode),
        fallback_prompt=config.fallback_prompt,
        continuation_prompt=config.continuation_prompt,
        max_consecutive_failed_tool_batches=(config.max_consecutive_failed_tool_batches),
    )


def _agent_fallback_mode_from_config(value: str) -> AgentFallbackMode:
    """把 runtime config fallback mode 映射为共享 AgentFallbackMode。

    :param value: runtime config fallback mode。
    :returns: 共享 AgentFallbackMode。
    :raises ValueError: fallback mode 不受支持时抛出。
    """

    return AgentFallbackMode(value)


def _require_optional_finite_float(value: float | None, *, field_name: str) -> None:
    """校验可选浮点数字段为有限数。

    :param value: 待校验值。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises ValueError: 值不是有限数时抛出。
    """

    if value is not None and not is_finite_number(value):
        raise ValueError(f"{field_name} must be finite")


def _require_optional_positive_float(value: float | None, *, field_name: str) -> None:
    """校验可选浮点数字段为有限正数。

    :param value: 待校验值。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises ValueError: 值不是有限正数时抛出。
    """

    if value is None:
        return
    if not is_positive_finite_number(value):
        raise ValueError(f"{field_name} must be finite and > 0")


def _require_optional_positive_int(value: int | None, *, field_name: str) -> None:
    """校验可选整数字段为正整数。

    :param value: 待校验值。
    :param field_name: 错误消息字段名。
    :returns: ``None``。
    :raises ValueError: 值不是正整数时抛出。
    """

    if value is not None and value < 1:
        raise ValueError(f"{field_name} must be >= 1")


def _memory_projection_policy_from_config(
    *, execution_profile: ExecutionProfileConfig, context_window_size: int
) -> MemoryProjectionPolicy:
    """把 runtime memory projection config 映射为 Host policy。

    :param execution_profile: 当前 execution profile。
    :param context_window_size: effective model context window。
    :returns: Host MemoryProjectionPolicy。
    :raises ValueError: 字段非法时由底层抛出。
    """

    policy = execution_profile.memory_projection_policy
    return MemoryProjectionPolicy(
        context_window_size=context_window_size,
        selected_recent_window_item_cap=policy.selected_recent_window_item_cap,
        selected_recent_window_char_cap=policy.selected_recent_window_char_cap,
        selected_recent_window_turn_floor=policy.selected_recent_window_turn_floor,
        fallback_selected_recent_window_item_cap=(
            policy.fallback_selected_recent_window_item_cap
        ),
        fallback_selected_recent_window_char_cap=(
            policy.fallback_selected_recent_window_char_cap
        ),
        evidence_fact_item_cap=policy.evidence_fact_item_cap,
        evidence_fact_char_cap=policy.evidence_fact_char_cap,
        evidence_fact_floor=policy.evidence_fact_floor,
        session_summary_char_cap=policy.session_summary_char_cap,
        answer_anchor_item_cap=policy.answer_anchor_item_cap,
        answer_anchor_char_cap=policy.answer_anchor_char_cap,
        forward_intent_item_cap=policy.forward_intent_item_cap,
        forward_intent_char_cap=policy.forward_intent_char_cap,
        reference_continuity_item_cap=policy.reference_continuity_item_cap,
        reference_continuity_char_cap=policy.reference_continuity_char_cap,
        reference_continuity_item_floor=policy.reference_continuity_item_floor,
        max_lag_events_for_inline_delta=policy.max_lag_events_for_inline_delta,
        max_delta_repair_events=policy.max_delta_repair_events,
        policy_ref=policy.policy_ref,
    )


def _tooling_options_from_discovery(
    *,
    tool_bundle: ToolBundle,
    source_refs: tuple[ToolBundleSourceRef, ...],
    fins_awaiting_providers: tuple[_FinsAwaitingProviderMetadata, ...],
    fins_awaiting_runtime: FinsObservationRuntime | None,
    duplicate_governance_policy_config: ToolDuplicateGovernancePolicyConfig,
    process_capsule_interrupt_policy_config: (
        ProcessCapsuleInterruptPolicyConfig | None
    ) = None,
) -> HostToolingOptions | None:
    """把 ToolsDiscovery 输出映射为 HostToolingOptions。

    :param tool_bundle: 已发现业务工具 bundle。
    :param source_refs: 工具来源引用。
    :param fins_awaiting_providers: provider-assembly boundary 产出的 active
        Fins typed metadata collection。
    :param fins_awaiting_runtime: Service discovery 为 Fins awaiting providers
        创建的共享 runtime；没有 Fins awaiting provider 时显式传 ``None``。
    :param duplicate_governance_policy_config: execution profile 中的重复调用治理配置。
    :param process_capsule_interrupt_policy_config: host runtime 中的
        process-backed cleanup interrupt 配置；``None`` 表示使用 Host typed 默认值。
    :returns: HostToolingOptions；没有业务工具时为 ``None``。
    :raises ValueError: source refs 缺失但工具非空时抛出。
    """

    if not tool_bundle.definitions:
        return None
    if not source_refs:
        raise ValueError("discovered tools must have source refs")
    wait_adapter_registry = _fins_wait_adapter_registry_from_provider_metadata(
        fins_awaiting_providers,
    )
    wait_activation_registry = _fins_wait_activation_registry_from_provider_metadata(
        fins_awaiting_providers,
        fins_awaiting_runtime=fins_awaiting_runtime,
    )
    wait_poll_adapter_registry = _fins_wait_poll_adapter_registry_from_provider_metadata(
        fins_awaiting_providers,
        fins_awaiting_runtime=fins_awaiting_runtime,
    )
    return HostToolingOptions(
        business_tool_bundle=tool_bundle,
        source_refs=source_refs,
        wait_adapter_registry=wait_adapter_registry,
        wait_activation_registry=wait_activation_registry,
        wait_poll_adapter_registry=wait_poll_adapter_registry,
        duplicate_governance_policy=_duplicate_governance_policy_from_config(
            duplicate_governance_policy_config
        ),
        process_capsule_interrupt_policy=(
            _process_capsule_interrupt_policy_from_config(
                process_capsule_interrupt_policy_config
            )
        ),
    )


def _process_capsule_interrupt_policy_from_config(
    config: ProcessCapsuleInterruptPolicyConfig | None,
) -> ProcessCapsuleInterruptPolicy:
    """把 runtime config 映射为 Host process capsule interrupt policy。

    :param config: ConfigLoader 输出的可选 cleanup interrupt 配置。
    :returns: Host typed process capsule interrupt policy。
    :raises ValueError: Host typed policy 校验失败时抛出。
    """

    if config is None:
        return ProcessCapsuleInterruptPolicy()
    return ProcessCapsuleInterruptPolicy(
        terminate_grace_seconds=config.terminate_grace_seconds,
        kill_grace_seconds=config.kill_grace_seconds,
    )


def _fins_wait_adapter_registry_from_provider_metadata(
    metadata: tuple[_FinsAwaitingProviderMetadata, ...],
) -> WaitAdapterRegistry | None:
    """从 active typed metadata 构造 Fins wait binding registry。

    :param metadata: provider-assembly boundary 产出的 active typed metadata。
    :returns: Fins wait adapter registry；没有 active provider 时为 ``None``。
    :raises ValueError: workspace root 不一致或工具 binding 重复时抛出。
    """

    if not metadata:
        return None
    ordered = tuple(sorted(metadata, key=lambda item: item.spec_id))
    return build_fins_wait_adapter_registry(
        workspace_root=_single_fins_workspace_root(
            tuple(item.workspace_root for item in ordered)
        ),
        tool_modes=tuple((item.tool_name, item.mode) for item in ordered),
    )


def _fins_wait_activation_registry_from_provider_metadata(
    metadata: tuple[_FinsAwaitingProviderMetadata, ...],
    *,
    fins_awaiting_runtime: FinsObservationRuntime | None,
) -> WaitActivationRegistry | None:
    """从全部 active typed metadata 构造 Fins wait activation registry。

    :param metadata: provider-assembly boundary 产出的 active typed metadata。
    :param fins_awaiting_runtime: Service discovery 创建的共享 Fins awaiting
        runtime；无 Fins awaiting provider 时为 ``None``。
    :returns: Fins wait activation registry；没有可绑定 awaiting 工具时为
        ``None``。
    :raises ValueError: workspace root 缺失、非绝对、不一致，或共享 runtime
        缺失时抛出。
    """

    if not metadata:
        return None
    if fins_awaiting_runtime is None:
        raise ValueError("Fins wait activation registry requires shared runtime")
    if not isinstance(fins_awaiting_runtime, FinsIngestionRuntime):
        raise ValueError("Fins wait activation registry requires ingestion runtime")
    # 生产路径中 awaiting tool callable、poll adapter 与 activation adapter
    # 必须共享同一个 runtime，避免 accepted activation 看不到工具准备的 observation。
    return build_fins_wait_activation_registry(
        runtime=fins_awaiting_runtime,
        tool_names=tuple(item.tool_name for item in metadata),
    )


def _fins_wait_poll_adapter_registry_from_provider_metadata(
    metadata: tuple[_FinsAwaitingProviderMetadata, ...],
    *,
    fins_awaiting_runtime: FinsObservationRuntime | None,
) -> WaitPollAdapterRegistry | None:
    """只从 mode=poll 的 active typed metadata 构造 poll registry。

    :param metadata: provider-assembly boundary 产出的 active typed metadata。
    :param fins_awaiting_runtime: Service discovery 创建的共享 Fins awaiting
        runtime；无 Fins awaiting provider 时为 ``None``。
    :returns: Fins wait poll adapter registry；没有可绑定 awaiting 工具时为
        ``None``。
    :raises ValueError: workspace root 缺失、非绝对、不一致，或共享 runtime
        缺失时抛出。
    """

    poll_metadata = tuple(
        item for item in metadata if item.mode is AwaitingResolutionMode.POLL
    )
    if not poll_metadata:
        return None
    if fins_awaiting_runtime is None:
        raise ValueError("Fins wait poll adapter registry requires shared runtime")
    if not isinstance(fins_awaiting_runtime, FinsIngestionRuntime):
        raise ValueError("Fins wait poll adapter registry requires ingestion runtime")
    return build_fins_wait_poll_adapter_registry(
        runtime=fins_awaiting_runtime,
        tool_names=tuple(item.tool_name for item in poll_metadata),
    )


def _fins_awaiting_tool_name_from_provider_config(
    provider_config: ToolDiscoveryProviderConfig,
) -> str | None:
    """识别显式配置中的 Fins awaiting provider 对应工具名。

    :param provider_config: 单个工具发现 provider typed 配置。
    :returns: Fins awaiting 工具名；非 Fins awaiting provider 时为 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if (
        provider_config.provider_id in _FINS_DOWNLOAD_PROVIDER_IDS
        or provider_config.import_path in _FINS_DOWNLOAD_IMPORT_PATHS
        or provider_config.source_id in _FINS_DOWNLOAD_SOURCE_IDS
    ):
        return FINS_DOWNLOAD_AWAITING_TOOL_NAME
    if (
        provider_config.provider_id in _FINS_PREPROCESS_PROVIDER_IDS
        or provider_config.import_path in _FINS_PREPROCESS_IMPORT_PATHS
        or provider_config.source_id in _FINS_PREPROCESS_SOURCE_IDS
    ):
        return FINS_PREPROCESS_AWAITING_TOOL_NAME
    if (
        provider_config.provider_id in _FINS_UPLOAD_PROVIDER_IDS
        or provider_config.import_path in _FINS_UPLOAD_IMPORT_PATHS
        or provider_config.source_id in _FINS_UPLOAD_SOURCE_IDS
    ):
        return FINS_UPLOAD_AWAITING_TOOL_NAME
    return None


def _is_recognized_non_awaiting_provider_config(
    provider_config: ToolDiscoveryProviderConfig,
) -> bool:
    """判断 Service 已识别的 non-awaiting Fins read / Web provider。

    本 helper 只用于拒绝 ``awaiting_resolution_mode`` 字段误用，不读取或解析
    字段值，也不为未知第三方 provider 发明语义。

    :param provider_config: 单个工具发现 provider typed 配置。
    :returns: 当前 provider 是已识别 non-awaiting provider 时返回 ``True``。
    :raises Exception: 不主动抛出异常。
    """

    return (
        provider_config.provider_id in _FINS_READ_PROVIDER_IDS
        or provider_config.import_path in _FINS_READ_IMPORT_PATHS
        or provider_config.source_id in _FINS_READ_SOURCE_IDS
        or provider_config.provider_id in _WEB_TOOLS_PROVIDER_IDS
        or provider_config.import_path in _WEB_TOOLS_IMPORT_PATHS
        or provider_config.source_id in _WEB_TOOLS_SOURCE_IDS
    )


def _fins_workspace_root_from_provider_config(
    provider_config: ToolDiscoveryProviderConfig,
) -> pathlib.Path:
    """从 Fins awaiting provider config 解析绝对 workspace root。

    :param provider_config: Fins awaiting provider typed 配置。
    :returns: 解析后的绝对 workspace root。
    :raises ValueError: workspace root 缺失、不是字符串或不是绝对路径时抛出。
    """

    value = provider_config.config.get(_FINS_WORKSPACE_ROOT_CONFIG_FIELD)
    if not isinstance(value, str) or value.strip() == "":
        raise ValueError(
            f"Fins awaiting provider {provider_config.provider_id} config.workspace_root must be a non-empty absolute path"
        )
    workspace_root = pathlib.Path(value).expanduser()
    if not workspace_root.is_absolute():
        raise ValueError(
            f"Fins awaiting provider {provider_config.provider_id} config.workspace_root must be absolute"
        )
    return workspace_root.resolve(strict=False)


def _single_fins_workspace_root(
    workspace_roots: Sequence[pathlib.Path],
) -> pathlib.Path:
    """校验本次 assembly 的 Fins awaiting providers 使用同一 workspace。

    :param workspace_roots: 已解析的 workspace root 列表。
    :returns: 唯一 workspace root。
    :raises ValueError: 列表为空或存在多个不同 workspace root 时抛出。
    """

    if not workspace_roots:
        raise ValueError("Fins awaiting provider workspace_root is required")
    first = workspace_roots[0]
    for workspace_root in workspace_roots[1:]:
        if workspace_root != first:
            raise ValueError(
                "Fins awaiting providers must use the same absolute workspace_root"
            )
    return first


def _duplicate_governance_policy_from_config(
    config: ToolDuplicateGovernancePolicyConfig,
) -> DuplicateGovernancePolicy:
    """把 runtime config 映射为 Host duplicate governance policy。

    :param config: execution profile 中的重复调用治理配置。
    :returns: Host duplicate governance policy。
    :raises ValueError: 决策字符串无法映射为 Host enum 时抛出。
    """

    return DuplicateGovernancePolicy(
        default_duplicate_decision=_duplicate_decision_from_config(
            config.default_duplicate_decision
        ),
        decisions_by_tool_name={
            tool_name: _duplicate_decision_from_config(decision)
            for tool_name, decision in config.decisions_by_tool_name.items()
        },
        justification_argument_names_by_tool_name=(
            dict(config.justification_argument_names_by_tool_name)
        ),
        messages=_duplicate_governance_messages_from_config(config.messages),
    )


def _duplicate_governance_messages_from_config(
    config: ToolDuplicateGovernanceMessagesConfig,
) -> DuplicateGovernanceMessages:
    """把 runtime config 映射为 Host duplicate governance messages。

    :param config: execution profile 中的重复调用治理消息配置。
    :returns: Host duplicate governance messages。
    :raises ValueError: 消息字段非法时由 Host typed contract 抛出。
    """

    return DuplicateGovernanceMessages(
        allow=config.allow,
        reuse=config.reuse,
        hint=config.hint,
        require_justification=config.require_justification,
        hard_stop=config.hard_stop,
        attempt_scope_diagnostic=config.attempt_scope_diagnostic,
        prior_accept_missing=config.prior_accept_missing,
    )


def _duplicate_decision_from_config(value: str) -> DuplicateDecisionKind:
    """把配置字符串映射为 Host duplicate decision enum。

    :param value: runtime config 中的 duplicate decision 字符串。
    :returns: Host duplicate decision enum。
    :raises ValueError: 字符串不是 Host 支持的 duplicate decision 时抛出。
    """

    try:
        return DuplicateDecisionKind(value)
    except ValueError as exc:
        raise ValueError(
            f"unsupported duplicate governance decision: {value}"
        ) from exc


def _provider_extension_status(model: ModelConfig) -> str:
    """返回 provider extension DSL 映射诊断。

    :param model: 模型配置。
    :returns: provider extension 映射状态。
    :raises Exception: provider extension DSL 非法时由 helper 抛出。
    """

    extension = provider_request_extension_from_json(model.provider_request_extension)
    if extension is None:
        return f"model={model.model_id}:none"
    return f"model={model.model_id}:ok:{type(extension).__name__}"


def _format_tool_selection(scene_inputs: PreparedSceneInputs) -> str:
    """格式化 scene tool selection 诊断。

    :param scene_inputs: ScenePrepare 输出。
    :returns: 工具选择诊断字符串。
    :raises Exception: 不主动抛出异常。
    """

    tool_names = scene_inputs.tool_selection.tool_names
    if tool_names is None:
        names = "*"
    elif not tool_names:
        names = "-"
    else:
        names = ",".join(sorted(tool_names))
    return f"mode={scene_inputs.tool_selection.mode.value},tools={names}"


def _format_provider_report(
    provider_id: str,
    spec_id: str,
    version_ref: str | None,
    tool_names: tuple[str, ...],
) -> str:
    """格式化工具 provider 诊断行。

    :param provider_id: provider 标识。
    :param spec_id: provider spec 标识。
    :param version_ref: provider 版本引用；无版本时为 ``None``。
    :param tool_names: provider 输出工具名。
    :returns: 诊断行。
    :raises Exception: 不主动抛出异常。
    """

    names = "-" if not tool_names else ",".join(tool_names)
    version = "-" if version_ref is None else version_ref
    return f"provider={provider_id},spec={spec_id}," f"version={version},tools={names}"


def _require_optional_non_empty_text(value: str | None, *, field_name: str) -> None:
    """校验可选文本字段非空。

    :param value: 可选文本。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises ValueError: 文本为空时抛出。
    """

    if value is not None and value.strip() == "":
        raise ValueError(f"{field_name} must not be empty")
