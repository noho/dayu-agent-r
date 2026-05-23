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

from dayu.contracts import ToolBundle, ToolBundleSourceRef
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.engine import AgentFallbackMode, AgentPolicy
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.engine.provider_extensions import provider_request_extension_from_json
from dayu.host.api import (
    CompactorRunnerBaseline,
    FollowupBehavior,
    HostCallContext,
    OpenHostOptions,
    OrdinaryRunExecutionBaseline,
    SubmitFollowupRequest,
)
from dayu.host.context_policy import default_context_budget_policy
from dayu.host.local_proxy import DefaultLocalEngineWorkerFactory
from dayu.host.memory import MemoryProjectionPolicy
from dayu.host.tooling import HostToolingOptions
from dayu.runtime.assembly import (
    AgentPolicyDefaults,
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
    RuntimeConfig,
    RuntimeLaneConfig,
    RunnerOptionHintConfig,
    ToolDiscoveryProviderConfig,
)
from dayu.runtime.location import RuntimeLocations
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
    ToolsDiscoveryProviderSpec,
)

_ENV_PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}"
)
_WORKER_BACKEND_LOCAL: Final[str] = "local"
_COMPACTOR_PROMPT_FRAGMENT_COUNT: Final[int] = 2


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
class ServiceDiscoveredTools:
    """Service 工具发现结果。

    :param tool_bundle: 已发现的业务工具 bundle。
    :param source_refs: 工具来源引用。
    :param provider_reports: 工具 provider 报告行。
    """

    tool_bundle: ToolBundle
    source_refs: tuple[ToolBundleSourceRef, ...]
    provider_reports: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ServiceOpenHostAssemblyRequest:
    """Service 组合 ``OpenHostOptions`` 的请求。

    :param workspace_root: workspace / 项目根目录，用于解析相对配置路径。
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
    """Compactor scene 装配后的双 prompt。

    :param system_prompt: compactor system prompt。
    :param user_prompt_template: compactor user prompt template。
    """

    system_prompt: str
    user_prompt_template: str


def discover_service_tools(config: RuntimeConfig) -> ServiceDiscoveredTools:
    """按 runtime config 执行工具发现。

    :param config: ``ConfigLoader`` 输出的 runtime typed config。
    :returns: Service 工具发现结果。
    :raises ValueError: provider spec 同时缺少 import path 与 entry point 时抛出。
    :raises Exception: ``ToolsDiscovery`` provider 失败时向上抛出。
    """

    discovery_result = ToolsDiscovery().discover(
        _tool_discovery_specs(tuple(config.tool_discovery.providers.values()))
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
    )


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
    execution_profile = config.execution_profiles.execution_profiles[
        execution_profile_id
    ]
    lane = config.runtime_lanes.lanes[host_runtime.host_execution_lane_name]
    effective_tool_bundle = _tool_bundle_with_effective_truncation(
        tool_bundle=request.discovered_tools.tool_bundle,
        execution_profile=execution_profile,
    )
    compactor_scene_inputs = _prepare_compactor_scene_inputs(
        request,
        execution_profile=execution_profile,
    )
    compactor_prompts = _compactor_prompts_from_scene_inputs(compactor_scene_inputs)
    ordinary_selection = select_runner_option_hint(
        models=config.models,
        execution_baseline=execution_profile.run_baseline,
        scene_model_hints=request.scene_inputs.model_hints,
        run_override=_model_runner_override_from_overrides(request.overrides),
        code_default=None,
    )
    compactor_selection = select_runner_option_hint(
        models=config.models,
        execution_baseline=ExecutionBaselineConfig(
            model_id=execution_profile.compactor_baseline.model_id,
            runner_option_hint_id=(
                execution_profile.compactor_baseline.runner_option_hint_id
            ),
        ),
        scene_model_hints=None,
        run_override=None,
        code_default=None,
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
        code_default=_agent_policy_defaults_from_config(
            execution_profile.agent_policy
        ),
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
    :param effective_tool_bundle: 已补齐截断默认值的工具 bundle。
    :param compactor_prompts: compactor scene 装配后的 system / user prompt。
    :returns: Host public opener options。
    :raises ValueError: worker backend 或 secret 映射失败时抛出。
    """

    if host_runtime.worker_backend != _WORKER_BACKEND_LOCAL:
        raise ValueError(f"unsupported host worker_backend: {host_runtime.worker_backend}")
    return OpenHostOptions(
        db_path=_resolve_project_path(request.workspace_root, host_runtime.sqlite.path),
        artifact_root=_resolve_project_path(
            request.workspace_root,
            host_runtime.artifact_root,
        ),
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=host_runtime.sqlite.busy_timeout_seconds,
        sqlite_write_busy_retry_count=host_runtime.sqlite.write_busy_retry_count,
        sqlite_write_retry_initial_delay_seconds=(
            host_runtime.sqlite.write_retry_initial_delay_seconds
        ),
        sqlite_write_retry_backoff_multiplier=(
            host_runtime.sqlite.write_retry_backoff_multiplier
        ),
        sqlite_write_retry_max_delay_seconds=(
            host_runtime.sqlite.write_retry_max_delay_seconds
        ),
        payload_inline_threshold_bytes=host_runtime.payload_inline_threshold_bytes,
        lane_db_path=_resolve_project_path(
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
            runner_options=_runner_options_from_hint(
                ordinary_selection.runner_option_hint
            ),
            agent_policy=_agent_policy_from_merged(agent_policy_config),
        ),
        worker_factory=DefaultLocalEngineWorkerFactory(),
        tooling_options=_tooling_options_from_discovery(
            tool_bundle=effective_tool_bundle,
            source_refs=request.discovered_tools.source_refs,
        ),
        context_budget_policy=default_context_budget_policy(
            context_window_size=ordinary_selection.model.context_window_tokens,
            soft_threshold_context_ratio=(
                execution_profile.context_budget_policy.soft_threshold_context_ratio
            ),
            hard_threshold_context_ratio=(
                execution_profile.context_budget_policy.hard_threshold_context_ratio
            ),
            max_proactive_compactions_per_run=(
                execution_profile.context_budget_policy.max_proactive_compactions_per_run
            ),
            max_reactive_compactions_per_run=(
                execution_profile.context_budget_policy.max_reactive_compactions_per_run
            ),
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
            compactor_runner_options=_runner_options_from_hint(
                compactor_selection.runner_option_hint
            ),
            compactor_system_prompt=compactor_prompts.system_prompt,
            compactor_user_prompt_template=compactor_prompts.user_prompt_template,
            compact_artifact_root=_resolve_project_path(
                request.workspace_root,
                execution_profile.compactor_baseline.artifact_root,
            ),
            compact_artifact_create_parent_dirs=True,
        ),
        memory_projection_policy=_memory_projection_policy_from_config(
            execution_profile=execution_profile,
            context_window_size=ordinary_selection.model.context_window_tokens,
        ),
        memory_projection_catchup_batch_size=(
            host_runtime.memory_projection_catch_up_batch_size
        ),
        enable_truncation_manager=(
            execution_profile.tool_truncation_policy.enabled
        ),
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
            available_tools=SceneToolCatalog.from_tool_bundle(
                request.discovered_tools.tool_bundle
            ),
        )
    )


def _compactor_prompts_from_scene_inputs(
    scene_inputs: PreparedSceneInputs,
) -> _CompactorScenePrompts:
    """从 compactor scene ordered fragments 中读取 system / user prompt。

    :param scene_inputs: compactor scene 装配输出。
    :returns: compactor 双 prompt。
    :raises ValueError: compactor scene 未提供恰好两个 prompt fragments 时抛出。
    """

    if len(scene_inputs.system_messages) != _COMPACTOR_PROMPT_FRAGMENT_COUNT:
        raise ValueError(
            "compactor scene must provide exactly two prompt fragments"
        )
    system_prompt, user_prompt_template = scene_inputs.system_messages
    return _CompactorScenePrompts(
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
    )


def _select_host_runtime_id(
    config: RuntimeConfig, explicit_runtime_id: str | None
) -> str:
    """选择 Host runtime id。

    :param config: runtime config 总视图。
    :param explicit_runtime_id: 显式 Host runtime id。
    :returns: 已存在的 Host runtime id。
    :raises RuntimeAssemblySelectionError: id 不存在时抛出。
    """

    runtime_id = (
        explicit_runtime_id
        if explicit_runtime_id is not None
        else config.host_runtime.default_host_runtime_id
    )
    if runtime_id not in config.host_runtime.runtimes:
        raise RuntimeAssemblySelectionError(f"host runtime not found: {runtime_id}")
    return runtime_id


def _select_execution_profile_id(
    config: RuntimeConfig, explicit_profile_id: str | None
) -> str:
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


def _tool_discovery_specs(
    provider_configs: Sequence[ToolDiscoveryProviderConfig],
) -> tuple[ToolsDiscoveryProviderSpec, ...]:
    """把 ConfigLoader provider view 映射为 ToolsDiscovery specs。

    :param provider_configs: 配置中的 provider specs。
    :returns: ToolsDiscovery 可消费的 provider specs。
    :raises ValueError: provider 同时缺少 import path 与 entry point 时抛出。
    """

    specs: list[ToolsDiscoveryProviderSpec] = []
    for provider_config in provider_configs:
        if provider_config.import_path is not None:
            location = PythonImportPathProvider(provider_config.import_path)
        elif provider_config.entry_point is not None:
            location = PackageEntryPointProvider(
                group=provider_config.entry_point.group,
                name=provider_config.entry_point.name,
            )
        else:
            raise ValueError(
                "tool discovery provider must declare import_path or entry_point: "
                f"{provider_config.provider_id}"
            )
        specs.append(
            ToolsDiscoveryProviderSpec(
                spec_id=provider_config.provider_id,
                location=location,
                enabled=provider_config.enabled,
                allow_empty=provider_config.allow_empty,
                config={},
            )
        )
    return tuple(specs)


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

    truncation_defaults = tool_truncation_policy_defaults(
        execution_profile.tool_truncation_policy
    )
    return ServiceOpenHostAssemblyDiagnostics(
        config_overlay_dir=locations.config_overlay_dir,
        prompt_asset_root=locations.prompt_asset_root,
        scene_manifest_root=locations.scene_manifest_root,
        host_runtime_id=host_runtime_id,
        execution_profile_id=execution_profile_id,
        model_id=ordinary_selection.model_id,
        model_source=ordinary_selection.diagnostic.selected_model_source,
        runner_option_hint_id=ordinary_selection.runner_option_hint_id,
        runner_option_hint_source=(
            ordinary_selection.diagnostic.selected_runner_option_hint_source
        ),
        compactor_model_id=compactor_selection.model_id,
        compactor_runner_option_hint_id=compactor_selection.runner_option_hint_id,
        lane_name=lane.lane_name,
        tool_provider_reports=tool_provider_reports,
        tool_selection=_format_tool_selection(scene_inputs),
        context_budget_policy_ref=execution_profile.context_budget_policy.policy_ref,
        agent_policy_sources=tuple(
            f"{field_name}:{source}"
            for field_name, source in sorted(
                agent_policy_config.field_sources.items()
            )
        ),
        tool_truncation_policy=(
            "enabled="
            f"{truncation_defaults.enabled},ttl={truncation_defaults.default_ttl_seconds}"
        ),
        ordinary_provider_extension_status=_provider_extension_status(
            ordinary_selection.model
        ),
        compactor_provider_extension_status=_provider_extension_status(
            compactor_selection.model
        ),
        ordinary_profile_compatibility=ordinary_profile_compatibility,
        compactor_profile_compatibility=compactor_profile_compatibility,
    )


def _runner_spec_from_model(
    *, model: ModelConfig, env: Mapping[str, str]
) -> RunnerSpec:
    """把 ModelConfig 映射为 Engine RunnerSpec。

    :param model: 模型配置。
    :param env: 环境变量映射。
    :returns: RunnerSpec。
    :raises ValueError: API key 引用缺失或环境变量缺失时抛出。
    """

    if model.api_key_ref is None:
        raise ValueError(f"model {model.model_id} must declare api_key_ref")
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
        supports_tool_calling=model.supports_tool_calling,
        supports_streaming=model.supports_stream,
        supports_stream_usage=model.supports_stream_usage,
        default_timeout_seconds=model.default_timeout_seconds,
        max_retries=model.max_retries,
        provider_request=provider_request_extension_from_json(
            model.provider_request_extension
        ),
        stream_idle_timeout_seconds=model.sse_idle_timeout_seconds,
        stream_idle_heartbeat_seconds=model.sse_heartbeat_seconds,
    )


def _render_headers(
    headers: Mapping[str, str], *, api_key_ref: str, env: Mapping[str, str]
) -> dict[str, str]:
    """渲染 provider headers 中的环境变量占位符。

    :param headers: 配置 headers。
    :param api_key_ref: API key 环境变量名。
    :param env: 环境变量映射。
    :returns: 渲染后的 headers。
    :raises ValueError: API key 缺失或 header 存在未解析占位符时抛出。
    """

    api_key = env.get(api_key_ref)
    if api_key is None or api_key.strip() == "":
        raise ValueError(f"missing env {api_key_ref}")
    rendered: dict[str, str] = {}
    for name, value in headers.items():
        rendered_value = value.replace(f"{{{{{api_key_ref}}}}}", api_key.strip())
        unresolved = _ENV_PLACEHOLDER_PATTERN.search(rendered_value)
        if unresolved is not None:
            raise ValueError(
                "header contains unresolved env placeholder: "
                f"{name} -> {unresolved.group(1)}"
            )
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


def _agent_policy_defaults_from_config(
    profile: AgentPolicyConfig,
) -> AgentPolicyDefaults:
    """从内嵌 Agent policy 配置投影 runtime helper 所需 code default。

    :param profile: ConfigLoader 输出的内嵌 Agent policy 配置。
    :returns: 与 profile 同值的默认字段集。
    :raises Exception: 不主动抛出异常。
    """

    return AgentPolicyDefaults(
        max_iterations=profile.max_iterations,
        continuation_max_attempts=profile.continuation_max_attempts,
        allow_tool_calls=profile.allow_tool_calls,
        tool_execution_timeout_seconds=profile.tool_execution_timeout_seconds,
        fallback_mode=profile.fallback_mode,
        fallback_prompt=profile.fallback_prompt,
        continuation_prompt=profile.continuation_prompt,
        max_consecutive_failed_tool_batches=(
            profile.max_consecutive_failed_tool_batches
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
        max_consecutive_failed_tool_batches=(
            config.max_consecutive_failed_tool_batches
        ),
    )


def _agent_fallback_mode_from_config(value: str) -> AgentFallbackMode:
    """把 runtime config fallback mode 映射为 Engine AgentFallbackMode。

    :param value: runtime config fallback mode。
    :returns: Engine AgentFallbackMode。
    :raises ValueError: fallback mode 不受支持时抛出。
    """

    return AgentFallbackMode(value)


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
        max_pinned_items=policy.max_pinned_items,
        max_evidence_backed_facts=policy.max_evidence_backed_facts,
        max_working_assumptions=policy.max_working_assumptions,
        recent_raw_turns_floor=policy.recent_raw_turns_floor,
        raw_turn_context_ratio=policy.raw_turn_context_ratio,
        raw_turn_size_floor=policy.raw_turn_size_floor,
        raw_turn_size_cap=policy.raw_turn_size_cap,
        history_pool_context_ratio=policy.history_pool_context_ratio,
        history_pool_size_floor=policy.history_pool_size_floor,
        history_pool_size_cap=policy.history_pool_size_cap,
        stable_layer_context_ratio=policy.stable_layer_context_ratio,
        stable_layer_size_floor=policy.stable_layer_size_floor,
        stable_layer_size_cap=policy.stable_layer_size_cap,
        max_lag_events_for_inline_delta=policy.max_lag_events_for_inline_delta,
        max_delta_repair_events=policy.max_delta_repair_events,
    )


def _tooling_options_from_discovery(
    *, tool_bundle: ToolBundle, source_refs: tuple[ToolBundleSourceRef, ...]
) -> HostToolingOptions | None:
    """把 ToolsDiscovery 输出映射为 HostToolingOptions。

    :param tool_bundle: 已发现业务工具 bundle。
    :param source_refs: 工具来源引用。
    :returns: HostToolingOptions；没有工具时返回 ``None``。
    :raises ValueError: source refs 缺失但工具非空时抛出。
    """

    if not tool_bundle.definitions:
        return None
    if not source_refs:
        raise ValueError("discovered tools must have source refs")
    return HostToolingOptions(
        business_tool_bundle=tool_bundle,
        source_refs=source_refs,
        wait_adapter_registry=None,
    )


def _resolve_project_path(
    workspace_root: pathlib.Path, configured_path: str
) -> pathlib.Path:
    """把配置路径解析为 workspace-root 相对路径或绝对路径。

    :param workspace_root: workspace / 项目根目录。
    :param configured_path: 配置中的路径字符串。
    :returns: 解析后的路径。
    :raises Exception: 不主动抛出异常。
    """

    path = pathlib.Path(configured_path)
    if path.is_absolute():
        return path
    return workspace_root / path


def _provider_extension_status(model: ModelConfig) -> str:
    """返回 provider extension DSL 映射诊断。

    :param model: 模型配置。
    :returns: provider extension 映射状态。
    :raises Exception: provider extension DSL 非法时由 helper 抛出。
    """

    extension = provider_request_extension_from_json(
        model.provider_request_extension
    )
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
    return (
        f"provider={provider_id},spec={spec_id},"
        f"version={version},tools={names}"
    )


def _require_optional_non_empty_text(value: str | None, *, field_name: str) -> None:
    """校验可选文本字段非空。

    :param value: 可选文本。
    :param field_name: 错误消息中的字段名。
    :returns: ``None``。
    :raises ValueError: 文本为空时抛出。
    """

    if value is not None and value.strip() == "":
        raise ValueError(f"{field_name} must not be empty")
