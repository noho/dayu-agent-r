"""Host public 多轮 smoke 的 Service-like runtime assembly 脚本。

本脚本用于人工观察真实生产式装配路径是否能把 runtime location、
``ConfigLoader``、``ToolsDiscovery``、``ScenePrepare``、Engine provider
extension helper 与 Host public ``open_host(options)`` 串起来。脚本不再保留
manual / 硬编码装配模式；配置、scene、工具发现或 provider extension 映射
缺口必须在调用 Host 前暴露。

脚本不会输出 API key、headers、完整 prompt 或完整 provider payload。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import re
import sys
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final
from uuid import uuid4

from dayu.contracts import (
    JsonValue,
    ToolBundle,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
)
from dayu.contracts.tool_call import (
    BatchToolExecutionContext,
    ToolCallRequest,
)
from dayu.contracts.tool_declaration import ToolDefinition
from dayu.contracts.tool_outcome import (
    ToolCompletedOutcome,
    ToolExecutionOutcome,
)
from dayu.contracts.tool_result import ToolResultSuccess
from dayu.contracts.tool_schema import (
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolSchema,
)
from dayu.engine import AgentFallbackMode, AgentPolicy
from dayu.engine.contracts.runner_spec import RunnerCallOptions, RunnerSpec
from dayu.engine.provider_extensions import provider_request_extension_from_json
from dayu.host import (
    CompactorRunnerBaseline,
    EnsureSessionRequest,
    FollowupBehavior,
    Host,
    HostCallContext,
    HostEvent,
    HostEventKind,
    HostToolingOptions,
    OpenHostOptions,
    OperationContext,
    OrdinaryRunExecutionBaseline,
    SubmitFollowupRequest,
    open_host,
)
from dayu.host.api import AuthorizationClaim
from dayu.host.context_policy import default_context_budget_policy
from dayu.host.local_proxy import DefaultLocalEngineWorkerFactory
from dayu.host.memory import MemoryProjectionPolicy
from dayu.runtime.assembly import (
    AgentPolicyDefaults,
    MergedAgentPolicyConfig,
    ModelRunnerHintOverride,
    RuntimeAssemblySelectionError,
    RunnerOptionHintSelection,
    effective_tool_truncate_spec_from_policy,
    merge_agent_policy_config,
    parse_model_runner_hint_override,
    select_runner_option_hint,
    tool_truncation_policy_defaults,
)
from dayu.runtime.config_loader import (
    AgentPolicyProfileConfig,
    ConfigLoader,
    ExecutionBaselineConfig,
    ExecutionProfileConfig,
    HostRuntimeProfileConfig,
    ModelConfig,
    RuntimeConfig,
    RuntimeLaneConfig,
    RunnerOptionHintConfig,
    ToolDiscoveryProviderConfig,
)
from dayu.runtime.location import RuntimeLocations, resolve_runtime_locations
from dayu.runtime.log import LogLevel, configure
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
    ToolsDiscoveryProviderOutput,
    ToolsDiscoveryProviderSpec,
)

_PROJECT_ROOT: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[1]
_PACKAGE_CONFIG_ROOT: Final[pathlib.Path] = _PROJECT_ROOT / "dayu" / "config"
_DEFAULT_SCENE_ID: Final[str] = "smoke_host_public_multiturn"
_DEFAULT_SUBJECT: Final[str] = "Dayu Host public runtime assembly smoke"
_DEFAULT_USER: Final[str] = "manual-smoke-operator"
_SMOKE_TOOL_NAME: Final[str] = "record_smoke_fact"
_SMOKE_MARKER: Final[str] = "DAYU_MEMORY_ALPHA"
_SMOKE_CLIENT_REQUEST_PREFIX: Final[str] = "runtime-assembly-smoke"
_FINAL_PREVIEW_CHARS: Final[int] = 500
_PROMPT_PAD_REPEAT: Final[int] = 90
_COMPACT_ARTIFACT_PRINT_LIMIT: Final[int] = 10
_WORKER_STARTUP_TIMEOUT_SECONDS: Final[float] = 10.0
_SQLITE_WRITE_BUSY_RETRY_COUNT: Final[int] = 8
_SQLITE_WRITE_RETRY_INITIAL_DELAY_SECONDS: Final[float] = 0.005
_SQLITE_WRITE_RETRY_BACKOFF_MULTIPLIER: Final[float] = 1.5
_SQLITE_WRITE_RETRY_MAX_DELAY_SECONDS: Final[float] = 0.05
_PAYLOAD_INLINE_THRESHOLD_BYTES: Final[int] = 4096
_ENV_PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}"
)
_WORKER_BACKEND_LOCAL: Final[str] = "local"
_HELPER_COMPOSE_OPEN_HOST_OPTIONS: Final[str] = "compose_open_host_options"
_HELPER_COMPOSE_SUBMIT_FOLLOWUP_REQUEST: Final[str] = (
    "compose_submit_followup_request"
)
_HELPER_PROVIDER_EXTENSION_FROM_CONFIG: Final[str] = (
    "provider_extension_from_config"
)


@dataclass(frozen=True, slots=True)
class SmokeArgs:
    """命令行参数。

    :param workspace_root: workspace / 项目根目录，用于 location resolver。
    :param scene_id: 需要装配的 scene id。
    :param execution_profile_id: 可选 execution profile 显式 override。
    :param host_runtime_id: 可选 Host runtime 显式 override。
    :param model_id: 可选 Run/UI 模型显式 override。
    :param runner_option_hint_id: 可选 Run/UI runner option hint 显式 override。
    :param fins_default_subject: scene context slot 的研究主体。
    :param base_user: scene context slot 的用户标识。
    :param log_level: Dayu 日志级别。
    :param keep_workspace: 是否在输出中显式标记保留 workspace。
    """

    workspace_root: pathlib.Path
    scene_id: str
    execution_profile_id: str | None
    host_runtime_id: str | None
    model_id: str | None
    runner_option_hint_id: str | None
    fins_default_subject: str
    base_user: str
    log_level: LogLevel
    keep_workspace: bool


@dataclass(frozen=True, slots=True)
class RoundResult:
    """单轮 public Host 运行摘要。

    :param label: 人工可读轮次标签。
    :param run_id: Host Run id。
    :param event: terminal HostEvent。
    """

    label: str
    run_id: str
    event: HostEvent


@dataclass(frozen=True, slots=True)
class AssemblyDiagnostics:
    """Host 调用前输出的 runtime assembly 诊断。

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
    :param agent_policy_profile_id: agent policy profile id。
    :param agent_policy_sources: Agent policy 字段来源摘要。
    :param tool_truncation_policy: tool truncation policy 摘要。
    :param ordinary_provider_extension_status: 普通 Runner provider extension 映射状态。
    :param compactor_provider_extension_status: compactor provider extension 映射状态。
    :param suggested_helper_names: 建议后续提取的 helper 名称。
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
    agent_policy_profile_id: str
    agent_policy_sources: tuple[str, ...]
    tool_truncation_policy: str
    ordinary_provider_extension_status: str
    compactor_provider_extension_status: str
    suggested_helper_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuntimeAssemblyPrepared:
    """调用 Host 前的 Service-like assembly 中间结果。

    :param config: runtime config typed view。
    :param locations: runtime 位置解析结果。
    :param host_runtime: 选中的 Host runtime profile。
    :param execution_profile: 选中的 execution profile。
    :param lane: 选中的 runtime lane。
    :param ordinary_selection: 普通 Run 模型与 runner hint 选择。
    :param compactor_selection: compactor 模型与 runner hint 选择。
    :param agent_policy_config: 合并后的 AgentPolicy 字段集。
    :param tool_bundle: 已发现并应用截断默认值的业务工具 bundle。
    :param tool_source_refs: 工具发现来源引用。
    :param scene_inputs: ScenePrepare 输出。
    :param diagnostics: 调用 Host 前的装配诊断。
    :param smoke_tool: 当前发现 bundle 中的 smoke fact 工具；没有时为 ``None``。
    :param workspace_root: workspace / 项目根目录。
    """

    config: RuntimeConfig
    locations: RuntimeLocations
    host_runtime: HostRuntimeProfileConfig
    execution_profile: ExecutionProfileConfig
    lane: RuntimeLaneConfig
    ordinary_selection: RunnerOptionHintSelection
    compactor_selection: RunnerOptionHintSelection
    agent_policy_config: MergedAgentPolicyConfig
    tool_bundle: ToolBundle
    tool_source_refs: tuple[ToolBundleSourceRef, ...]
    scene_inputs: PreparedSceneInputs
    diagnostics: AssemblyDiagnostics
    smoke_tool: "SmokeFactTool | None"
    workspace_root: pathlib.Path


@dataclass(frozen=True, slots=True)
class RuntimeAssemblyResult:
    """完整 runtime assembly 结果。

    :param options: 可传给 ``open_host`` 的 Host 构造期输入。
    :param scene_inputs: ScenePrepare 输出。
    :param diagnostics: 调用 Host 前的装配诊断。
    :param smoke_tool: 当前发现 bundle 中的 smoke fact 工具；没有时为 ``None``。
    """

    options: OpenHostOptions
    scene_inputs: PreparedSceneInputs
    diagnostics: AssemblyDiagnostics
    smoke_tool: "SmokeFactTool | None"


class SmokeFactTool:
    """记录固定 smoke fact 的 mock business tool。"""

    def __init__(self) -> None:
        """初始化工具调用观测状态。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.call_count = 0
        self.last_marker: str | None = None

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """返回固定工具事实。

        :param call: 工具调用请求。
        :param context: 批式执行上下文。
        :returns: 成功工具 outcome。
        :raises Exception: 不主动抛出异常。
        """

        del call, context
        self.call_count += 1
        self.last_marker = _SMOKE_MARKER
        return ToolCompletedOutcome(
            result=ToolResultSuccess(
                ok=True,
                value={
                    "marker": _SMOKE_MARKER,
                    "fact": "runtime-assembly-smoke-tool-fact",
                    "note": "This fact should be visible to later Host runs.",
                },
                meta=None,
            )
        )


def discover_smoke_tools(
    spec: ToolsDiscoveryProviderSpec,
) -> ToolsDiscoveryProviderOutput:
    """ToolsDiscovery provider callable，用于提供 smoke mock tool。

    该函数仅在 workspace ``tool_discovery.json`` 显式启用 provider spec，且
    该 spec 的 import path 指向
    ``utils.smoke_host_public_multiturn:discover_smoke_tools`` 时由
    ``ToolsDiscovery`` 调用。

    :param spec: 工具发现 provider spec。
    :returns: smoke provider 输出。
    :raises ValueError: 工具定义字段非法时由底层抛出。
    """

    smoke_tool = SmokeFactTool()
    return ToolsDiscoveryProviderOutput(
        provider_id="host-public-multiturn-smoke",
        version_ref="v1",
        source_refs=(
            ToolBundleSourceRef(
                source_kind=ToolBundleSourceKind.CONFIG_BINDING,
                source_id=spec.spec_id,
            ),
        ),
        definitions=(_smoke_tool_definition(smoke_tool),),
    )


def parse_args(argv: Sequence[str]) -> SmokeArgs:
    """解析命令行参数。

    :param argv: 不含程序名的参数序列。
    :returns: 解析后的参数。
    :raises SystemExit: argparse 在参数非法时抛出。
    """

    parser = argparse.ArgumentParser(
        description="Run Host public multi-turn runtime assembly smoke."
    )
    parser.add_argument(
        "--workspace-root",
        default=str(_PROJECT_ROOT),
        help="workspace / project root；默认当前脚本所在项目根目录。",
    )
    parser.add_argument(
        "--scene-id",
        default=_DEFAULT_SCENE_ID,
        help=f"ScenePrepare 使用的 scene id；默认 {_DEFAULT_SCENE_ID}。",
    )
    parser.add_argument(
        "--execution-profile-id",
        default=None,
        help="显式 execution profile id；默认读取配置 default_execution_profile_id。",
    )
    parser.add_argument(
        "--host-runtime-id",
        default=None,
        help="显式 Host runtime id；默认读取配置 default_host_runtime_id。",
    )
    parser.add_argument(
        "--model-id",
        default=None,
        help="Run/UI 模型 override；只允许覆盖 model_id。",
    )
    parser.add_argument(
        "--runner-option-hint-id",
        default=None,
        help="Run/UI runner option hint override；只允许覆盖 runner_option_hint_id。",
    )
    parser.add_argument(
        "--fins-default-subject",
        default=_DEFAULT_SUBJECT,
        help="传给 scene context slot 的默认研究主体。",
    )
    parser.add_argument(
        "--base-user",
        default=_DEFAULT_USER,
        help="传给 scene context slot 的用户标识。",
    )
    parser.add_argument(
        "--log-level",
        choices=tuple(level.name for level in LogLevel),
        default=LogLevel.VERBOSE.name,
        help="Dayu 日志级别，默认 VERBOSE。",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="输出中标记保留 workspace；脚本不会删除 Host/runtime artifacts。",
    )
    namespace = parser.parse_args(list(argv))
    workspace_root_text: str = namespace.workspace_root
    scene_id: str = namespace.scene_id
    execution_profile_id: str | None = namespace.execution_profile_id
    host_runtime_id: str | None = namespace.host_runtime_id
    model_id: str | None = namespace.model_id
    runner_option_hint_id: str | None = namespace.runner_option_hint_id
    fins_default_subject: str = namespace.fins_default_subject
    base_user: str = namespace.base_user
    log_level_text: str = namespace.log_level
    keep_workspace: bool = namespace.keep_workspace
    return SmokeArgs(
        workspace_root=pathlib.Path(workspace_root_text).resolve(),
        scene_id=scene_id,
        execution_profile_id=execution_profile_id,
        host_runtime_id=host_runtime_id,
        model_id=model_id,
        runner_option_hint_id=runner_option_hint_id,
        fins_default_subject=fins_default_subject,
        base_user=base_user,
        log_level=LogLevel[log_level_text],
        keep_workspace=keep_workspace,
    )


async def run_smoke(args: SmokeArgs, env: Mapping[str, str]) -> int:
    """运行 Host public 多轮 smoke。

    :param args: smoke 参数。
    :param env: 环境变量映射。
    :returns: 进程退出码。
    :raises Exception: Host public path 或 provider 调用失败时向上抛出。
    """

    prepared = _prepare_runtime_assembly(args)
    _print_assembly_diagnostics(prepared.diagnostics)
    options = _compose_open_host_options(prepared=prepared, env=env)
    assembly = RuntimeAssemblyResult(
        options=options,
        scene_inputs=prepared.scene_inputs,
        diagnostics=prepared.diagnostics,
        smoke_tool=prepared.smoke_tool,
    )
    smoke_run_id = _new_smoke_run_id()

    print("SMOKE START Host public multi-turn runtime assembly")
    print(f"SMOKE WORKSPACE_ROOT {args.workspace_root}")
    print(f"SMOKE RUN_ID {smoke_run_id}")
    print("SMOKE CONTRACT open_host -> ensure_session -> submit_followup -> watch")
    print("SMOKE LOG_LEVEL", args.log_level.name)

    async with open_host(assembly.options) as host:
        session = await host.ensure_session(_ensure_request())
        watcher = host.watch_session_events(session.session_id)
        print(f"SMOKE SESSION session_id={session.session_id}")

        first = await _run_round(
            host=host,
            watcher=watcher,
            session_id=session.session_id,
            label="round1-tool-fact",
            client_request_id=_round_client_request_id(smoke_run_id, 1),
            system_prompt=_system_prompt(assembly.scene_inputs),
            prompt=(
                "请调用工具 record_smoke_fact 记录 smoke fact。"
                "工具完成后，用一句话说明你已经收到工具事实。"
            ),
            tool_names=assembly.scene_inputs.tool_selection.tool_names,
        )
        _print_round(first)

        second = await _run_round(
            host=host,
            watcher=watcher,
            session_id=session.session_id,
            label="round2-memory-and-compact",
            client_request_id=_round_client_request_id(smoke_run_id, 2),
            system_prompt=_system_prompt(assembly.scene_inputs),
            prompt=_memory_compact_prompt(),
            tool_names=frozenset(),
        )
        _print_round(second)

        third = await _run_round(
            host=host,
            watcher=watcher,
            session_id=session.session_id,
            label="round3-after-compact-continuity",
            client_request_id=_round_client_request_id(smoke_run_id, 3),
            system_prompt=_system_prompt(assembly.scene_inputs),
            prompt=(
                "继续同一个会话。请根据你可见的历史、memory 或 compact "
                f"摘要，说明是否仍能看到标记 {_SMOKE_MARKER}。"
            ),
            tool_names=frozenset(),
        )
        _print_round(third)

        final_session = await host.get_session(session.session_id)
        print(f"SMOKE SESSION_STATUS {final_session.status.value}")

    _print_tool_summary(assembly.smoke_tool)
    _print_compact_summary(assembly.options)
    print("SMOKE PASS public Host handle completed three-turn closure")
    if args.keep_workspace:
        print("SMOKE WORKSPACE_KEPT true")
    else:
        print("SMOKE WORKSPACE_KEPT true  # smoke never deletes Host/runtime artifacts")
    return 0


def _prepare_runtime_assembly(args: SmokeArgs) -> RuntimeAssemblyPrepared:
    """执行 Host 调用前的 runtime/config/tools/scene typed assembly。

    :param args: smoke 参数。
    :returns: Host options 组合前的 assembly 中间结果。
    :raises ValueError: 配置、工具发现、scene 或 override 无法映射时抛出。
    """

    locations = resolve_runtime_locations(
        project_root=args.workspace_root,
        package_config_root=_PACKAGE_CONFIG_ROOT,
    )
    config = ConfigLoader(package_config_dir=_PACKAGE_CONFIG_ROOT).load(
        workspace_config_dir=locations.config_overlay_dir
    )
    host_runtime_id = _select_host_runtime_id(config, args.host_runtime_id)
    execution_profile_id = _select_execution_profile_id(
        config, args.execution_profile_id
    )
    host_runtime = config.host_runtime.runtimes[host_runtime_id]
    execution_profile = config.execution_profiles.execution_profiles[
        execution_profile_id
    ]
    lane = config.runtime_lanes.lanes[host_runtime.host_execution_lane_name]
    discovery_result = ToolsDiscovery().discover(
        _tool_discovery_specs(tuple(config.tool_discovery.providers.values()))
    )
    effective_tool_bundle = _tool_bundle_with_effective_truncation(
        tool_bundle=discovery_result.tool_bundle,
        execution_profile=execution_profile,
    )
    scene_inputs = prepare_scene(
        ScenePrepareRequest(
            scene_id=args.scene_id,
            scene_manifest_root=locations.scene_manifest_root,
            prompt_asset_root=locations.prompt_asset_root,
            context_slot_values={
                "fins_default_subject": args.fins_default_subject,
                "base_user": args.base_user,
            },
            available_tools=SceneToolCatalog.from_tool_bundle(
                effective_tool_bundle
            ),
        )
    )
    run_override = _model_runner_override_from_args(args)
    ordinary_selection = select_runner_option_hint(
        models=config.models,
        execution_baseline=execution_profile.run_baseline,
        scene_model_hints=scene_inputs.model_hints,
        run_override=run_override,
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
    agent_profile = config.execution_profiles.agent_policy_profiles[
        execution_profile.agent_policy_profile_id
    ]
    agent_policy_config = merge_agent_policy_config(
        code_default=_agent_policy_defaults_from_profile(agent_profile),
        execution_profile=agent_profile,
        scene_override=scene_inputs.agent_policy_override,
        run_override=None,
    )
    diagnostics = _assembly_diagnostics(
        locations=locations,
        host_runtime_id=host_runtime_id,
        execution_profile_id=execution_profile_id,
        execution_profile=execution_profile,
        lane=lane,
        ordinary_selection=ordinary_selection,
        compactor_selection=compactor_selection,
        agent_policy_config=agent_policy_config,
        tool_provider_reports=tuple(
            _format_provider_report(report.provider_id, report.spec_id, report.version_ref, report.tool_names)
            for report in discovery_result.provider_reports
        ),
        scene_inputs=scene_inputs,
    )
    return RuntimeAssemblyPrepared(
        config=config,
        locations=locations,
        host_runtime=host_runtime,
        execution_profile=execution_profile,
        lane=lane,
        ordinary_selection=ordinary_selection,
        compactor_selection=compactor_selection,
        agent_policy_config=agent_policy_config,
        tool_bundle=effective_tool_bundle,
        tool_source_refs=discovery_result.source_refs,
        scene_inputs=scene_inputs,
        diagnostics=diagnostics,
        smoke_tool=_find_smoke_tool(effective_tool_bundle),
        workspace_root=args.workspace_root,
    )


def _compose_open_host_options(
    *, prepared: RuntimeAssemblyPrepared, env: Mapping[str, str]
) -> OpenHostOptions:
    """把 assembly 中间结果映射为 public ``OpenHostOptions``。

    :param prepared: runtime assembly 中间结果。
    :param env: 环境变量映射。
    :returns: Host public opener options。
    :raises ValueError: worker backend、secret 或 provider extension 映射失败时抛出。
    """

    if prepared.host_runtime.worker_backend != _WORKER_BACKEND_LOCAL:
        raise ValueError(
            "unsupported host worker_backend: "
            f"{prepared.host_runtime.worker_backend}"
        )
    return OpenHostOptions(
        db_path=_resolve_project_path(
            prepared.workspace_root,
            prepared.host_runtime.sqlite.path,
        ),
        artifact_root=_resolve_project_path(
            prepared.workspace_root,
            prepared.host_runtime.artifact_root,
        ),
        create_parent_dirs=True,
        sqlite_busy_timeout_seconds=prepared.host_runtime.sqlite.busy_timeout_seconds,
        sqlite_write_busy_retry_count=_SQLITE_WRITE_BUSY_RETRY_COUNT,
        sqlite_write_retry_initial_delay_seconds=(
            _SQLITE_WRITE_RETRY_INITIAL_DELAY_SECONDS
        ),
        sqlite_write_retry_backoff_multiplier=(
            _SQLITE_WRITE_RETRY_BACKOFF_MULTIPLIER
        ),
        sqlite_write_retry_max_delay_seconds=(
            _SQLITE_WRITE_RETRY_MAX_DELAY_SECONDS
        ),
        payload_inline_threshold_bytes=_PAYLOAD_INLINE_THRESHOLD_BYTES,
        lane_db_path=_resolve_project_path(
            prepared.workspace_root,
            prepared.config.runtime_lanes.coordinator.db_path,
        ),
        lane_name=prepared.lane.lane_name,
        lane_capacity=prepared.lane.capacity,
        lane_default_timeout_seconds=prepared.lane.default_timeout_seconds,
        lane_claim_ttl_seconds=prepared.lane.claim_ttl_seconds,
        lane_heartbeat_interval_seconds=prepared.lane.heartbeat_interval_seconds,
        worker_startup_timeout_seconds=_WORKER_STARTUP_TIMEOUT_SECONDS,
        dispatch_poll_interval_seconds=(
            prepared.host_runtime.dispatch_poll_interval_seconds
        ),
        ordinary_run_baseline=OrdinaryRunExecutionBaseline(
            runner_spec=_runner_spec_from_model(
                model=prepared.ordinary_selection.model,
                env=env,
            ),
            runner_options=_runner_options_from_hint(
                prepared.ordinary_selection.runner_option_hint
            ),
            agent_policy=_agent_policy_from_merged(
                prepared.agent_policy_config
            ),
        ),
        worker_factory=DefaultLocalEngineWorkerFactory(),
        tooling_options=_tooling_options_from_discovery(
            tool_bundle=prepared.tool_bundle,
            source_refs=prepared.tool_source_refs,
        ),
        context_budget_policy=default_context_budget_policy(
            context_window_size=(
                prepared.ordinary_selection.model.context_window_tokens
            ),
            soft_threshold_context_ratio=(
                prepared.execution_profile.context_budget_policy
                .soft_threshold_context_ratio
            ),
            hard_threshold_context_ratio=(
                prepared.execution_profile.context_budget_policy
                .hard_threshold_context_ratio
            ),
            max_proactive_compactions_per_run=(
                prepared.execution_profile.context_budget_policy
                .max_proactive_compactions_per_run
            ),
            max_reactive_compactions_per_run=(
                prepared.execution_profile.context_budget_policy
                .max_reactive_compactions_per_run
            ),
            max_compaction_attempts_per_operation=(
                prepared.execution_profile.context_budget_policy
                .max_compaction_attempts_per_operation
            ),
            policy_ref=(
                prepared.execution_profile.context_budget_policy.policy_ref
            ),
        ),
        compactor_runner_baseline=CompactorRunnerBaseline(
            compactor_runner_spec=_runner_spec_from_model(
                model=prepared.compactor_selection.model,
                env=env,
            ),
            compactor_runner_options=_runner_options_from_hint(
                prepared.compactor_selection.runner_option_hint
            ),
            compact_artifact_root=_resolve_project_path(
                prepared.workspace_root,
                prepared.execution_profile.compactor_baseline.artifact_root,
            ),
            compact_artifact_create_parent_dirs=True,
        ),
        memory_projection_policy=_memory_projection_policy_from_config(
            execution_profile=prepared.execution_profile,
            context_window_size=(
                prepared.ordinary_selection.model.context_window_tokens
            ),
        ),
        memory_projection_catchup_batch_size=(
            prepared.host_runtime.memory_projection_catch_up_batch_size
        ),
        enable_truncation_manager=(
            prepared.host_runtime.truncation_manager_enabled
        ),
    )


def _compose_submit_followup_request(
    *,
    session_id: str,
    client_request_id: str,
    system_prompt: str,
    prompt: str,
    tool_names: frozenset[str] | None,
) -> SubmitFollowupRequest:
    """把当前 Run 输入映射为 public ``SubmitFollowupRequest``。

    :param session_id: Session id。
    :param client_request_id: 幂等请求 id。
    :param system_prompt: ``ScenePrepare`` 已装配的系统消息。
    :param prompt: 调用方本轮用户输入。
    :param tool_names: 本轮工具选择；``None`` 表示全量，空集合表示禁用。
    :returns: SubmitFollowupRequest。
    :raises ValueError: 请求字段非法时由底层抛出。
    """

    return SubmitFollowupRequest(
        context=_host_context(client_request_id),
        session_id=session_id,
        client_request_id=client_request_id,
        system_prompt=system_prompt,
        user_prompt=prompt,
        tool_names=tool_names,
        runner_spec=None,
        runner_options=None,
        agent_policy=None,
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
    )


def _select_host_runtime_id(
    config: RuntimeConfig, explicit_runtime_id: str | None
) -> str:
    """选择 Host runtime id。

    :param config: runtime config 总视图。
    :param explicit_runtime_id: CLI 显式 Host runtime id。
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
    :param explicit_profile_id: CLI 显式 execution profile id。
    :returns: 已存在的 execution profile id。
    :raises RuntimeAssemblySelectionError: id 不存在时抛出。
    """

    profile_id = (
        explicit_profile_id
        if explicit_profile_id is not None
        else config.execution_profiles.default_execution_profile_id
    )
    if profile_id not in config.execution_profiles.execution_profiles:
        raise RuntimeAssemblySelectionError(
            f"execution profile not found: {profile_id}"
        )
    return profile_id


def _model_runner_override_from_args(
    args: SmokeArgs,
) -> ModelRunnerHintOverride | None:
    """把 CLI 模型 / hint 参数解析为 typed allowlist override。

    :param args: smoke 参数。
    :returns: typed model runner override；未提供时为 ``None``。
    :raises RuntimeAssemblyFieldError: 字段类型或白名单非法时由 helper 抛出。
    """

    fields: dict[str, JsonValue] = {}
    if args.model_id is not None:
        fields["model_id"] = args.model_id
    if args.runner_option_hint_id is not None:
        fields["runner_option_hint_id"] = args.runner_option_hint_id
    if not fields:
        return None
    return parse_model_runner_hint_override(fields, source_name="cli_run_override")


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
    agent_policy_config: MergedAgentPolicyConfig,
    tool_provider_reports: tuple[str, ...],
    scene_inputs: PreparedSceneInputs,
) -> AssemblyDiagnostics:
    """构造调用 Host 前的装配诊断。

    :param locations: runtime 位置解析结果。
    :param host_runtime_id: Host runtime id。
    :param execution_profile_id: execution profile id。
    :param execution_profile: execution profile 配置。
    :param lane: runtime lane 配置。
    :param ordinary_selection: 普通 Run 模型选择结果。
    :param compactor_selection: compactor 模型选择结果。
    :param agent_policy_config: 合并后的 AgentPolicy 字段集。
    :param tool_provider_reports: 工具 provider 报告行。
    :param scene_inputs: ScenePrepare 输出。
    :returns: assembly diagnostics。
    :raises ProviderExtensionConfigError: provider extension DSL 非法时由 helper 抛出。
    """

    truncation_defaults = tool_truncation_policy_defaults(
        execution_profile.tool_truncation_policy
    )
    return AssemblyDiagnostics(
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
        compactor_runner_option_hint_id=(
            compactor_selection.runner_option_hint_id
        ),
        lane_name=lane.lane_name,
        tool_provider_reports=tool_provider_reports,
        tool_selection=_format_tool_selection(scene_inputs),
        context_budget_policy_ref=(
            execution_profile.context_budget_policy.policy_ref
        ),
        agent_policy_profile_id=execution_profile.agent_policy_profile_id,
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
        suggested_helper_names=(
            _HELPER_COMPOSE_OPEN_HOST_OPTIONS,
            _HELPER_COMPOSE_SUBMIT_FOLLOWUP_REQUEST,
            _HELPER_PROVIDER_EXTENSION_FROM_CONFIG,
        ),
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
        max_tokens=hint.max_tokens,
        top_p=hint.top_p,
        stream=hint.stream,
    )


def _agent_policy_defaults_from_profile(
    profile: AgentPolicyProfileConfig,
) -> AgentPolicyDefaults:
    """从 execution profile 投影 runtime helper 所需 code default。

    :param profile: agent policy profile；调用方传入 ConfigLoader typed profile。
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

    if value == "force_answer":
        return AgentFallbackMode.FORCE_ANSWER
    if value == "raise_error":
        return AgentFallbackMode.RAISE_ERROR
    raise ValueError(f"unsupported fallback_mode: {value}")


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
        max_verified_facts=policy.max_verified_facts,
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
    :raises ProviderExtensionConfigError: provider extension DSL 非法时由 helper 抛出。
    """

    extension = provider_request_extension_from_json(
        model.provider_request_extension
    )
    if extension is None:
        return f"model={model.model_id}:none"
    return f"model={model.model_id}:ok:{type(extension).__name__}"


def _find_smoke_tool(tool_bundle: ToolBundle) -> SmokeFactTool | None:
    """从发现的工具 bundle 中找出 smoke fact 工具实例。

    :param tool_bundle: 已发现业务工具 bundle。
    :returns: smoke fact 工具实例；未发现时返回 ``None``。
    :raises Exception: 不主动抛出异常。
    """

    for definition in tool_bundle.definitions:
        if isinstance(definition.callable, SmokeFactTool):
            return definition.callable
    return None


def _smoke_tool_definition(smoke_tool: SmokeFactTool) -> ToolDefinition:
    """构造 smoke fact 工具定义。

    :param smoke_tool: 记录 smoke fact 的工具实例。
    :returns: ToolDefinition。
    :raises ValueError: schema 字段非法时由底层抛出。
    """

    properties: dict[str, JsonValue] = {
        "marker": {
            "type": "string",
            "description": "Smoke marker to record.",
        }
    }
    return ToolDefinition(
        name=_SMOKE_TOOL_NAME,
        schema=ToolSchema(
            type="function",
            function=ToolFunctionSchema(
                name=_SMOKE_TOOL_NAME,
                description=(
                    "Record the fixed Dayu Host public smoke memory marker."
                ),
                parameters=ToolParametersSchema(
                    type="object",
                    properties=properties,
                    required=("marker",),
                    additional_properties=False,
                ),
            ),
        ),
        callable=smoke_tool,
        truncate=None,
        display=None,
        tags=("manual-smoke", "fins"),
    )


def _ensure_request() -> EnsureSessionRequest:
    """构造 ensure session 请求。

    :returns: EnsureSessionRequest。
    :raises ValueError: 字段非法时由底层抛出。
    """

    return EnsureSessionRequest(
        scope="workspace",
        slot_key="runtime-assembly-host-public-multiturn-smoke",
        metadata=(),
    )


def _host_context(request_id: str) -> HostCallContext:
    """构造 HostCallContext。

    :param request_id: request id。
    :returns: HostCallContext。
    :raises ValueError: 字段非法时由底层抛出。
    """

    return HostCallContext(
        actor=_DEFAULT_USER,
        source="utils.smoke_host_public_multiturn",
        request_id=request_id,
        authorization_claims=(
            AuthorizationClaim(name="role", value="manual-smoke"),
        ),
        operation_context=OperationContext(
            operation_name="host_public_multiturn_smoke",
            operation_kind="manual_smoke",
            business_domain="host",
            business_object_type=None,
            business_object_id=None,
            scenario="phase12_1_runtime_assembly",
            correlation_id=None,
        ),
    )


async def _run_round(
    *,
    host: Host,
    watcher: AsyncIterator[HostEvent],
    session_id: str,
    label: str,
    client_request_id: str,
    system_prompt: str,
    prompt: str,
    tool_names: frozenset[str] | None,
) -> RoundResult:
    """提交一轮 prompt 并等待 terminal HostEvent。

    :param host: public Host handle。
    :param watcher: session-level HostEvent iterator。
    :param session_id: Session id。
    :param label: 轮次标签。
    :param client_request_id: 幂等请求 id。
    :param system_prompt: 本轮系统提示词。
    :param prompt: 用户 prompt。
    :param tool_names: 本轮工具选择。
    :returns: RoundResult。
    :raises RuntimeError: terminal 不是 succeeded 或缺少 final answer 时抛出。
    """

    print(f"SMOKE ROUND_START label={label}")
    accepted = await host.submit_followup(
        session_id,
        _compose_submit_followup_request(
            session_id=session_id,
            client_request_id=client_request_id,
            system_prompt=system_prompt,
            prompt=prompt,
            tool_names=tool_names,
        ),
    )
    event = await _next_terminal_for_run(watcher, accepted.accepted_run_id)
    if event.kind is not HostEventKind.SUCCEEDED:
        raise RuntimeError(
            f"round {label} terminal kind is {event.kind.value}; "
            f"run_id={accepted.accepted_run_id}"
        )
    if event.final_answer is None or event.final_answer.content.strip() == "":
        raise RuntimeError(f"round {label} returned empty final answer")
    return RoundResult(label=label, run_id=accepted.accepted_run_id, event=event)


async def _next_terminal_for_run(
    iterator: AsyncIterator[HostEvent], run_id: str
) -> HostEvent:
    """读取指定 Run 的 terminal HostEvent。

    :param iterator: HostEvent iterator。
    :param run_id: Run id。
    :returns: terminal HostEvent。
    :raises TimeoutError: 超时未收到 terminal event 时抛出。
    """

    async def read() -> HostEvent:
        """读取 iterator 直到目标 Run terminal。

        :returns: terminal HostEvent。
        :raises RuntimeError: iterator 结束前没有 terminal event 时抛出。
        """

        async for event in iterator:
            if event.run_id == run_id and event.terminal_status is not None:
                return event
        raise RuntimeError("HostEvent iterator ended before terminal event")

    return await asyncio.wait_for(read(), timeout=180.0)


def _new_smoke_run_id() -> str:
    """生成本次手工 smoke 的调用方请求批次 id。

    :returns: 用于 stdout 和 client request id 的唯一短 id。
    :raises Exception: 不主动抛出异常。
    """

    return uuid4().hex[:12]


def _round_client_request_id(smoke_run_id: str, round_index: int) -> str:
    """构造每轮 Host command 的幂等请求 id。

    :param smoke_run_id: 本次手工 smoke 批次 id。
    :param round_index: 轮次序号。
    :returns: 本轮 ``client_request_id``。
    :raises Exception: 不主动抛出异常。
    """

    return f"{_SMOKE_CLIENT_REQUEST_PREFIX}-{smoke_run_id}-round-{round_index}"


def _system_prompt(scene_inputs: PreparedSceneInputs) -> str:
    """返回 ``ScenePrepare`` 已装配的系统提示词。

    :param scene_inputs: ScenePrepare 输出。
    :returns: 系统提示词。
    :raises ValueError: scene 未提供 system messages 时抛出。
    """

    if not scene_inputs.system_messages:
        raise ValueError("prepared scene must provide system messages")
    return "\n\n".join(scene_inputs.system_messages)


def _memory_compact_prompt() -> str:
    """构造触发 memory / compact 的第二轮 prompt。

    :returns: prompt 文本。
    :raises Exception: 不主动抛出异常。
    """

    padding = " ".join(
        f"DAYU_CONTEXT_PAD_{index:03d}" for index in range(_PROMPT_PAD_REPEAT)
    )
    return (
        f"上一轮如果工具事实已进入 memory，请观察是否能看到标记 {_SMOKE_MARKER}。"
        "请用两句话回答：第一句说明你看到的上一轮事实，第二句说明这是第二轮。"
        "下面是为了触发 Host proactive compact 的人工长上下文："
        f"{padding}"
    )


def _print_assembly_diagnostics(diagnostics: AssemblyDiagnostics) -> None:
    """打印 Host 调用前 assembly diagnostics。

    :param diagnostics: assembly diagnostics。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    print("SMOKE ASSEMBLY_MODE runtime")
    print(f"SMOKE ASSEMBLY config_overlay={diagnostics.config_overlay_dir}")
    print(f"SMOKE ASSEMBLY prompt_asset_root={diagnostics.prompt_asset_root}")
    print(
        "SMOKE ASSEMBLY scene_manifest_root="
        f"{diagnostics.scene_manifest_root}"
    )
    print(f"SMOKE ASSEMBLY host_runtime_id={diagnostics.host_runtime_id}")
    print(
        "SMOKE ASSEMBLY execution_profile_id="
        f"{diagnostics.execution_profile_id}"
    )
    print(
        "SMOKE ASSEMBLY model_id="
        f"{diagnostics.model_id} source={diagnostics.model_source}"
    )
    print(
        "SMOKE ASSEMBLY runner_option_hint_id="
        f"{diagnostics.runner_option_hint_id} "
        f"source={diagnostics.runner_option_hint_source}"
    )
    print(
        "SMOKE ASSEMBLY compactor_model_id="
        f"{diagnostics.compactor_model_id}"
    )
    print(
        "SMOKE ASSEMBLY compactor_runner_option_hint_id="
        f"{diagnostics.compactor_runner_option_hint_id}"
    )
    print(f"SMOKE ASSEMBLY lane_name={diagnostics.lane_name}")
    if diagnostics.tool_provider_reports:
        for report in diagnostics.tool_provider_reports:
            print(f"SMOKE ASSEMBLY tool_provider_report={report}")
    else:
        print("SMOKE ASSEMBLY tool_provider_report=<none>")
    print(f"SMOKE ASSEMBLY tool_selection={diagnostics.tool_selection}")
    print(
        "SMOKE ASSEMBLY policy_refs="
        f"context_budget:{diagnostics.context_budget_policy_ref},"
        f"agent_policy_profile:{diagnostics.agent_policy_profile_id},"
        f"tool_truncation:{diagnostics.tool_truncation_policy}"
    )
    print(
        "SMOKE ASSEMBLY agent_policy_sources="
        f"{','.join(diagnostics.agent_policy_sources)}"
    )
    print(
        "SMOKE ASSEMBLY provider_extension_status="
        f"ordinary:{diagnostics.ordinary_provider_extension_status},"
        f"compactor:{diagnostics.compactor_provider_extension_status}"
    )
    print(
        "SMOKE ASSEMBLY suggested_helpers="
        f"{','.join(diagnostics.suggested_helper_names)}"
    )


def _print_round(result: RoundResult) -> None:
    """打印一轮运行摘要。

    :param result: 轮次结果。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    final_answer = result.event.final_answer
    content = "" if final_answer is None else final_answer.content.strip()
    preview = content[:_FINAL_PREVIEW_CHARS]
    terminal = (
        result.event.terminal_status.value
        if result.event.terminal_status is not None
        else "none"
    )
    print(
        "SMOKE ROUND_DONE "
        f"label={result.label} run_id={result.run_id} "
        f"event_id={result.event.event_id} "
        f"event_sequence={result.event.event_sequence} "
        f"terminal={terminal}"
    )
    print(f"SMOKE FINAL_PREVIEW label={result.label} content={preview!r}")


def _print_tool_summary(smoke_tool: SmokeFactTool | None) -> None:
    """打印 smoke 工具调用观测摘要。

    :param smoke_tool: smoke tool 实例；没有发现时为 ``None``。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    if smoke_tool is None:
        print("SMOKE TOOL_CALL_COUNT unavailable")
        print("SMOKE TOOL_LAST_MARKER unavailable")
        return
    print(f"SMOKE TOOL_CALL_COUNT {smoke_tool.call_count}")
    print(f"SMOKE TOOL_LAST_MARKER {smoke_tool.last_marker!r}")
    if smoke_tool.call_count == 0:
        print(
            "SMOKE OBSERVE tool was not called; memory tool fact path was not "
            "exercised by this model run"
        )


def _print_compact_summary(options: OpenHostOptions) -> None:
    """打印 compact 观测摘要。

    :param options: 本次 smoke 使用的 Host opener options。
    :returns: ``None``。
    :raises Exception: 不主动抛出异常。
    """

    compact_root = (
        options.compactor_runner_baseline.compact_artifact_root
        if options.compactor_runner_baseline is not None
        else None
    )
    if compact_root is None:
        print("SMOKE COMPACT_ARTIFACT_ROOT <none>")
        print("SMOKE COMPACT_ARTIFACT_FILE_COUNT 0")
        return
    artifacts = (
        tuple(path for path in compact_root.rglob("*") if path.is_file())
        if compact_root.exists()
        else ()
    )
    print(f"SMOKE COMPACT_ARTIFACT_ROOT {compact_root}")
    print(f"SMOKE COMPACT_ARTIFACT_FILE_COUNT {len(artifacts)}")
    for path in artifacts[:_COMPACT_ARTIFACT_PRINT_LIMIT]:
        print(f"SMOKE COMPACT_ARTIFACT {path}")


def _format_provider_report(
    provider_id: str,
    spec_id: str,
    version_ref: str | None,
    tool_names: tuple[str, ...],
) -> str:
    """格式化 ToolsDiscovery provider report。

    :param provider_id: provider 自声明身份。
    :param spec_id: provider spec id。
    :param version_ref: provider 版本引用。
    :param tool_names: provider 产出的工具名。
    :returns: stdout 友好报告行。
    :raises Exception: 不主动抛出异常。
    """

    version = "<none>" if version_ref is None else version_ref
    names = "<none>" if not tool_names else ",".join(sorted(tool_names))
    return f"provider={provider_id},spec={spec_id},version={version},tools={names}"


def _format_tool_selection(scene_inputs: PreparedSceneInputs) -> str:
    """格式化 scene tool selection 结果。

    :param scene_inputs: ScenePrepare 输出。
    :returns: stdout 友好字符串。
    :raises Exception: 不主动抛出异常。
    """

    tool_names = scene_inputs.tool_selection.tool_names
    if tool_names is None:
        names = "<all>"
    elif not tool_names:
        names = "<none>"
    else:
        names = ",".join(sorted(tool_names))
    return f"mode={scene_inputs.tool_selection.mode.value},names={names}"


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口。

    :param argv: 命令行参数；为 ``None`` 时读取 ``sys.argv[1:]``。
    :returns: 进程退出码。
    :raises Exception: 不主动抛出；异常会被转换为退出码 1。
    """

    args = parse_args(sys.argv[1:] if argv is None else argv)
    configure(level=args.log_level)
    try:
        return asyncio.run(run_smoke(args, os.environ))
    except Exception as exc:
        print(f"SMOKE FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
