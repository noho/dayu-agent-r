"""Host public entrypoint 等待态 smoke 脚本。"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dayu.contracts import (
    AsyncDirectToolExecutionCapability,
    BatchToolExecutionContext,
    BatchToolExecutionRequest,
    ToolAwaitKind,
    ToolAwaitSpec,
    ToolAwaitingOutcome,
    ToolBundle,
    ToolBundleSourceKind,
    ToolBundleSourceRef,
    ToolCallRequest,
    ToolDefinition,
    ToolExecutionOutcome,
    ToolFunctionSchema,
    ToolParametersSchema,
    ToolResultSuccess,
    ToolSchema,
)
from dayu.engine import (
    AgentRunRequest,
    AssistantToolCallBatchSnapshot,
    AwaitingToolExecutionRecord,
    EngineEvent,
    EngineEventType,
    FinalAnswerData,
    FinishReason,
    RUN_SUSPENDED_REASON_TOOL_AWAITING,
    RunSuspendedData,
    ToolAwaitingData,
)
from dayu.host import (
    AttemptDispatchSnapshot,
    AuthorizationClaim,
    EnsureSessionRequest,
    FollowupBehavior,
    HostCallContext,
    HostTerminalStatus,
    LocalEngineWorker,
    LocalWorkerHandle,
    OpenHostOptions,
    OperationContext,
    OutboxTerminalCursor,
    ReadOutboxTerminalItemsRequest,
    ResolveWaitCompletedOutcome,
    RunStatus,
    open_host,
)
from dayu.host.wait_adapter import (
    WaitAdapterSnapshot,
    WaitExternalJobLifecycleResult,
    WaitExternalJobLifecycleUnsupported,
    WaitPollAdapterRegistration,
    WaitPollAdapterRegistry,
    WaitPollNotReady,
    WaitPollReady,
    WaitPollResult,
    WaitResumePolicy,
)
from dayu.fins.tools._ingestion_tool_helpers import AwaitingResolutionMode
from dayu.runtime.config_loader import (
    HostRuntimeConfig,
    RuntimeConfig,
    ToolDiscoveryProviderConfig,
)
from dayu.runtime.scene_prepare import (
    PreparedSceneInputs,
    SceneSourceKind,
    SceneSourceRef,
    SceneToolSelectionMode,
    SceneToolSelectionResult,
)
from dayu.service.entrypoint_runtime import (
    EntrypointActivity,
    EntrypointActivityStatus,
    EntrypointTerminalSource,
    EntrypointRuntimeRequest,
    EntrypointRuntimeResult,
    EntrypointTurnRequest,
    prepare_entrypoint_runtime,
    submit_entrypoint_turn_and_wait,
)
from dayu.service.fins_wait_adapter import (
    FINS_DOWNLOAD_AWAITING_TOOL_NAME,
    FINS_INGESTION_WAIT_ADAPTER_KEY,
    FINS_PREPROCESS_AWAITING_TOOL_NAME,
    FINS_UPLOAD_AWAITING_TOOL_NAME,
)
from dayu.service.host_assembly import (
    ServiceAssemblyOverrides,
    ServiceOpenHostAssemblyRequest,
    ServiceOpenHostAssemblyResult,
    ServiceRunOverrides,
    assemble_effective_tool_provider_configs,
    compose_open_host_options,
    discover_service_tools,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE_CONFIG_ROOT = _PROJECT_ROOT / "dayu" / "config"
_AWAITING_TOOL_NAME = FINS_PREPROCESS_AWAITING_TOOL_NAME
_ADAPTER_KEY = FINS_INGESTION_WAIT_ADAPTER_KEY
_FINS_AWAITING_PROVIDER_IDS = frozenset(
    {
        "financial-download-tools",
        "financial-preprocess-tools",
        "financial-upload-tools",
    }
)
_FINS_AWAITING_TOOL_NAMES = (
    FINS_DOWNLOAD_AWAITING_TOOL_NAME,
    FINS_PREPROCESS_AWAITING_TOOL_NAME,
    FINS_UPLOAD_AWAITING_TOOL_NAME,
)
_LOCAL_PROVIDER_ENV = {
    "DEEPSEEK_API_KEY": "local-smoke-placeholder",
    "MIMO_PLAN_API_KEY": "local-smoke-placeholder",
}
_NOW = datetime(2026, 7, 5, 0, 0, 0, tzinfo=UTC)
_FINAL_ANSWER = "等待任务已完成，已收到轮询恢复结果。"
_RESUME_TOKEN = "service-awaiting-smoke-token"
_SOURCE_REF = ToolBundleSourceRef(
    source_kind=ToolBundleSourceKind.SERVICE_COMPOSITION,
    source_id="utils.smoke_host_public_awaiting_entrypoint",
    version_ref=None,
)
_DEFAULT_WORKSPACE_PARENT = Path("workspace/tmp")
_DEFAULT_WORKSPACE_PREFIX = "host-public-awaiting-entrypoint-smoke"
_DEFAULT_SLOT_KEY_PREFIX = "manual-smoke-awaiting-entrypoint"
_TERMINAL_TIMEOUT_SECONDS = 10.0
_POLL_INTERVAL_SECONDS = 0.01


@dataclass(frozen=True, slots=True)
class SmokeArgs:
    """解析后的 smoke 参数。"""

    workspace_root: Path
    keep_workspace: bool


@dataclass(frozen=True, slots=True)
class _CompositionSmokeMatrix:
    """packaged composition smoke 的无网络分支结果。

    :param poll: packaged poll + enabled policy 结果。
    :param manual: active manual providers 结果。
    :param no_provider: 不包含 awaiting provider 的结果。
    :param provider_disabled: awaiting providers 全部 disabled 的结果。
    :param runtime_disabled: active poll + disabled runtime policy 结果。
    """

    poll: ServiceOpenHostAssemblyResult
    manual: ServiceOpenHostAssemblyResult
    no_provider: ServiceOpenHostAssemblyResult
    provider_disabled: ServiceOpenHostAssemblyResult
    runtime_disabled: ServiceOpenHostAssemblyResult


async def run_smoke(args: SmokeArgs, env: Mapping[str, str]) -> int:
    """运行 public entrypoint awaiting smoke。

    :param args: smoke 参数。
    :param env: 环境变量映射。
    :returns: 进程退出码。
    :raises RuntimeError: public 行为不符合预期时抛出。
    """

    del env
    interactive_runtime = await _prepare_packaged_entrypoint_runtime(
        workspace_root=args.workspace_root,
        scene_id="interactive",
    )
    prompt_runtime = await _prepare_packaged_entrypoint_runtime(
        workspace_root=args.workspace_root,
        scene_id="prompt",
    )
    composition_matrix = _packaged_composition_matrix(
        workspace_root=args.workspace_root,
        interactive_runtime=interactive_runtime,
        prompt_runtime=prompt_runtime,
    )
    await _open_non_poll_composition_cases(composition_matrix)
    poll_adapter = _GatedReadyPollAdapter()
    worker_factory = _AwaitingThenAnswerWorkerFactory()
    options = _deterministic_public_poll_options(
        composition_matrix.poll.options,
        worker_factory=worker_factory,
        poll_adapter=poll_adapter,
    )
    scene_inputs = _scene_inputs()
    host_assembly = replace(
        composition_matrix.poll,
        options=options,
        effective_tool_bundle=_tool_bundle(),
    )
    accepted_run_ids: list[str] = []
    activities: list[EntrypointActivity] = []
    waiting_activity_seen = asyncio.Event()

    print("SMOKE START packaged composition -> Host public awaiting entrypoint")
    print(f"SMOKE WORKSPACE_ROOT {args.workspace_root}")
    print(
        "SMOKE TYPED_PROVIDER_MODES "
        f"poll={AwaitingResolutionMode.POLL.value} "
        f"manual={AwaitingResolutionMode.MANUAL.value} "
        f"callback={AwaitingResolutionMode.CALLBACK.value}"
    )
    print(
        "SMOKE RUNTIME_POLICY "
        f"{_wait_poller_policy_summary(composition_matrix.poll.options)}"
    )
    print(
        "SMOKE COMPOSITION "
        "poll_registry=true poll_policy=true manual_poller=false "
        "callback_pre_open_failure=true no_provider_poller=false "
        "provider_disabled_poller=false runtime_disabled_poller=false "
        "prompt_interactive_same=true"
    )
    print("SMOKE CONTRACT open_host -> ensure_session -> submit_entrypoint_turn_and_wait")
    print("SMOKE WAIT_RECOVERY production poller via public wait poll adapter registry")

    async with open_host(options) as host:
        session = await host.ensure_session(
            EnsureSessionRequest(
                scope="workspace",
                slot_key=f"{_DEFAULT_SLOT_KEY_PREFIX}-{uuid4().hex[:12]}",
                metadata=(),
            )
        )
        print(f"SMOKE SESSION_ID {session.session_id}")

        def on_activity(activity: EntrypointActivity) -> None:
            """记录 Service activity 并在等待态出现时释放测试检查。

            :param activity: Service 投影后的 activity。
            :returns: ``None``。
            :raises Exception: 不主动抛出异常。
            """

            activities.append(activity)
            if activity.status is EntrypointActivityStatus.WAITING:
                waiting_activity_seen.set()

        submit_task = asyncio.create_task(
            submit_entrypoint_turn_and_wait(
                host,
                request=_turn_request(session_id=session.session_id),
                scene_inputs=scene_inputs,
                host_assembly=host_assembly,
                on_run_accepted=accepted_run_ids.append,
                on_activity=on_activity,
                poll_interval_seconds=_POLL_INTERVAL_SECONDS,
            )
        )
        try:
            await asyncio.wait_for(
                waiting_activity_seen.wait(), timeout=_TERMINAL_TIMEOUT_SECONDS
            )
            _require(len(accepted_run_ids) > 0, message="run was not accepted")
            accepted_run_id = accepted_run_ids[0]
            print(f"SMOKE ACCEPTED_RUN_ID {accepted_run_id}")
            waiting_snapshot = await host.get_run(accepted_run_id)
            _require(
                waiting_snapshot.status is RunStatus.WAITING,
                message=f"run did not enter WAITING: {waiting_snapshot.status}",
            )
            print("SMOKE OBSERVED_WAITING true")

            await asyncio.wait_for(
                _wait_for_not_ready_observation(poll_adapter),
                timeout=_TERMINAL_TIMEOUT_SECONDS,
            )
            poll_adapter.open_gate()
            result = await asyncio.wait_for(
                submit_task, timeout=_TERMINAL_TIMEOUT_SECONDS
            )

            _require(
                result.source is EntrypointTerminalSource.LIVE_EVENT,
                message=f"terminal source mismatch: {result.source}",
            )
            _require(
                result.run_id == accepted_run_id,
                message=f"terminal run id mismatch: {result.run_id}",
            )
            _require(
                result.terminal_status is HostTerminalStatus.SUCCEEDED,
                message=f"terminal status mismatch: {result.terminal_status}",
            )
            final_answer = result.final_answer
            if final_answer is None:
                raise RuntimeError("missing final answer")
            _require(final_answer.content.strip() != "", message="blank final answer")
            _require(
                worker_factory.accept_count == 2,
                message=f"worker accept count mismatch: {worker_factory.accept_count}",
            )
            _require(
                poll_adapter.not_ready_count >= 1,
                message=(
                    "poll not-ready count mismatch: "
                    f"{poll_adapter.not_ready_count}"
                ),
            )
            _require(
                poll_adapter.ready_count == 1,
                message=f"poll ready count mismatch: {poll_adapter.ready_count}",
            )
            _require(
                any(
                    activity.status is EntrypointActivityStatus.WAITING
                    for activity in activities
                ),
                message="WAITING activity was not recorded",
            )
            print(f"SMOKE TERMINAL_EVENT_ID {result.terminal_event_id}")
            print("SMOKE TERMINAL_STATUS SUCCEEDED")

            batch = await host.read_outbox_terminal_items(
                session.session_id,
                ReadOutboxTerminalItemsRequest(
                    after=OutboxTerminalCursor(event_sequence=0),
                    seen_terminal_event_ids=(),
                    limit=50,
                ),
            )
            matching_items = tuple(
                item
                for item in batch.items
                if item.run_id == accepted_run_id
                and item.terminal_status is HostTerminalStatus.SUCCEEDED
            )
            _require(
                len(matching_items) == 1,
                message=f"terminal outbox match count mismatch: {len(matching_items)}",
            )
            _require(
                matching_items[0].terminal_event_id == result.terminal_event_id,
                message="terminal outbox event id mismatch",
            )
            print("SMOKE OUTBOX_TERMINAL_MATCH true")
            print(f"SMOKE WORKER_ACCEPT_COUNT {worker_factory.accept_count}")
            print(f"SMOKE POLL_NOT_READY_COUNT {poll_adapter.not_ready_count}")
            print(f"SMOKE POLL_READY_COUNT {poll_adapter.ready_count}")
            print("SMOKE PASS Host public awaiting entrypoint")
            if args.keep_workspace:
                print("SMOKE WORKSPACE_KEPT true  # smoke never deletes Host artifacts")
            return 0
        finally:
            if not submit_task.done():
                submit_task.cancel()
                try:
                    await submit_task
                except asyncio.CancelledError:
                    pass


async def _prepare_packaged_entrypoint_runtime(
    *, workspace_root: Path, scene_id: str
) -> EntrypointRuntimeResult:
    """通过 packaged ConfigLoader 与共享 Service 路径准备 entrypoint runtime。

    :param workspace_root: smoke workspace 根目录。
    :param scene_id: ``prompt`` 或 ``interactive`` scene id。
    :returns: packaged entrypoint runtime 结果。
    :raises Exception: config、provider discovery、scene 或 composition 失败时透出。
    """

    return await prepare_entrypoint_runtime(
        EntrypointRuntimeRequest(
            workspace_root=workspace_root,
            package_config_root=_PACKAGE_CONFIG_ROOT,
            explicit_config_dir=None,
            scene_id=scene_id,
            context_slot_values={
                "fins_default_subject": "DAYU",
                "current_time": "2026-07-15 12:00:00 +08:00",
            },
            assembly_overrides=ServiceAssemblyOverrides(),
            env=_LOCAL_PROVIDER_ENV,
        )
    )


def _packaged_composition_matrix(
    *,
    workspace_root: Path,
    interactive_runtime: EntrypointRuntimeResult,
    prompt_runtime: EntrypointRuntimeResult,
) -> _CompositionSmokeMatrix:
    """验证 packaged provider modes 与 runtime policy 的完整装配分支。

    :param workspace_root: smoke workspace 根目录。
    :param interactive_runtime: packaged interactive runtime。
    :param prompt_runtime: packaged prompt runtime。
    :returns: 可用于 public Host open 的 composition matrix。
    :raises RuntimeError: 任一 registry、binding、policy 或 fail-closed 断言不成立。
    """

    poll = interactive_runtime.host_assembly
    prompt_policy = prompt_runtime.host_assembly.options.wait_poller_policy
    _require(poll.options.wait_poller_policy is not None, message="poll policy missing")
    _require(prompt_policy == poll.options.wait_poller_policy, message="prompt/interactive policy diverged")
    _require_poll_bindings(poll, expected_policy=WaitResumePolicy.POLL)

    config = interactive_runtime.runtime_config
    providers = tuple(config.tool_discovery.providers.values())
    manual = _compose_provider_case(
        workspace_root=workspace_root,
        runtime=interactive_runtime,
        config=config,
        provider_configs=_fins_provider_configs(
            providers,
            mode=AwaitingResolutionMode.MANUAL,
            enabled=True,
            include=True,
        ),
    )
    _require(manual.options.wait_poller_policy is None, message="manual policy must be absent")
    _require_poll_bindings(manual, expected_policy=WaitResumePolicy.MANUAL)
    manual_tooling = manual.options.tooling_options
    if manual_tooling is None:
        raise RuntimeError("manual tooling missing")
    _require(
        manual_tooling.wait_poll_adapter_registry is None,
        message="manual poll registry must be absent",
    )

    no_provider = _compose_provider_case(
        workspace_root=workspace_root,
        runtime=interactive_runtime,
        config=config,
        provider_configs=_fins_provider_configs(
            providers,
            mode=AwaitingResolutionMode.POLL,
            enabled=True,
            include=False,
        ),
    )
    _require(
        no_provider.options.wait_poller_policy is None,
        message="no-provider policy must be absent",
    )

    provider_disabled = _compose_provider_case(
        workspace_root=workspace_root,
        runtime=interactive_runtime,
        config=config,
        provider_configs=_fins_provider_configs(
            providers,
            mode=AwaitingResolutionMode.POLL,
            enabled=False,
            include=True,
        ),
    )
    _require(
        provider_disabled.options.wait_poller_policy is None,
        message="provider-disabled policy must be absent",
    )

    runtime_disabled = _compose_provider_case(
        workspace_root=workspace_root,
        runtime=interactive_runtime,
        config=_runtime_config_with_wait_poller_enabled(config, enabled=False),
        provider_configs=_fins_provider_configs(
            providers,
            mode=AwaitingResolutionMode.POLL,
            enabled=True,
            include=True,
        ),
    )
    disabled_policy = runtime_disabled.options.wait_poller_policy
    if disabled_policy is None:
        raise RuntimeError("runtime-disabled policy missing")
    _require(not disabled_policy.enabled, message="runtime-disabled policy was enabled")
    _require_poll_bindings(runtime_disabled, expected_policy=WaitResumePolicy.POLL)

    callback_configs = _fins_provider_configs(
        providers,
        mode=AwaitingResolutionMode.CALLBACK,
        enabled=True,
        include=True,
    )
    try:
        _compose_provider_case(
            workspace_root=workspace_root,
            runtime=interactive_runtime,
            config=config,
            provider_configs=callback_configs,
        )
    except ValueError as exc:
        _require(
            "authenticated callback transport" in str(exc),
            message=f"callback failure mismatch: {exc}",
        )
    else:
        raise RuntimeError("callback composition did not fail before open_host")

    return _CompositionSmokeMatrix(
        poll=poll,
        manual=manual,
        no_provider=no_provider,
        provider_disabled=provider_disabled,
        runtime_disabled=runtime_disabled,
    )


def _compose_provider_case(
    *,
    workspace_root: Path,
    runtime: EntrypointRuntimeResult,
    config: RuntimeConfig,
    provider_configs: tuple[ToolDiscoveryProviderConfig, ...],
) -> ServiceOpenHostAssemblyResult:
    """通过真实 provider discovery 与 Service composition 构造一个矩阵分支。

    :param workspace_root: smoke workspace 根目录。
    :param runtime: packaged entrypoint runtime，复用其 location 与 scene input。
    :param config: 当前分支的 typed runtime config。
    :param provider_configs: 当前分支的 provider owner inputs。
    :returns: Service Host assembly 结果。
    :raises Exception: provider discovery 或 composition 失败时透出。
    """

    discovered = discover_service_tools(
        assemble_effective_tool_provider_configs(
            provider_configs,
            workspace_root=workspace_root,
        )
    )
    return compose_open_host_options(
        ServiceOpenHostAssemblyRequest(
            workspace_root=workspace_root,
            config=config,
            locations=runtime.locations,
            scene_inputs=runtime.scene_inputs,
            discovered_tools=discovered,
            overrides=ServiceAssemblyOverrides(),
            env=_LOCAL_PROVIDER_ENV,
        )
    )


def _fins_provider_configs(
    provider_configs: Sequence[ToolDiscoveryProviderConfig],
    *,
    mode: AwaitingResolutionMode,
    enabled: bool,
    include: bool,
) -> tuple[ToolDiscoveryProviderConfig, ...]:
    """构造 smoke 分支的 Fins provider owner inputs。

    :param provider_configs: packaged provider configs。
    :param mode: 写入 owner config 的 closed typed mode。
    :param enabled: awaiting providers 是否启用。
    :param include: 是否保留 awaiting providers；``False`` 表示 no-provider。
    :returns: 只在 Fins awaiting provider owner input 上变化的 configs。
    :raises Exception: 不主动抛出异常。
    """

    resolved: list[ToolDiscoveryProviderConfig] = []
    for provider in provider_configs:
        if provider.provider_id not in _FINS_AWAITING_PROVIDER_IDS:
            resolved.append(provider)
            continue
        if not include:
            continue
        provider_config = dict(provider.config)
        provider_config["awaiting_resolution_mode"] = mode.value
        resolved.append(replace(provider, enabled=enabled, config=provider_config))
    return tuple(resolved)


def _runtime_config_with_wait_poller_enabled(
    config: RuntimeConfig, *, enabled: bool
) -> RuntimeConfig:
    """为 smoke 分支替换选中 runtime 的 typed policy enabled 值。

    :param config: ConfigLoader 产出的完整 runtime config。
    :param enabled: 分支期望的 runtime policy 开关。
    :returns: 除 typed enabled 字段外保持不变的 runtime config。
    :raises Exception: packaged 默认 runtime 缺失时由映射访问抛出。
    """

    runtime_id = config.host_runtime.default_host_runtime_id
    profile = config.host_runtime.runtimes[runtime_id]
    runtimes = dict(config.host_runtime.runtimes)
    runtimes[runtime_id] = replace(
        profile,
        wait_poller_policy=replace(profile.wait_poller_policy, enabled=enabled),
    )
    return replace(
        config,
        host_runtime=HostRuntimeConfig(
            default_host_runtime_id=runtime_id,
            runtimes=runtimes,
        ),
    )


def _require_poll_bindings(
    assembly: ServiceOpenHostAssemblyResult,
    *,
    expected_policy: WaitResumePolicy,
) -> None:
    """断言三个 packaged Fins awaiting binding 的精确 resume policy。

    :param assembly: Service assembly 结果。
    :param expected_policy: 当前分支期望的 Host resume policy。
    :returns: ``None``。
    :raises RuntimeError: tooling、registry 或任一 binding 不符合预期。
    """

    tooling = assembly.options.tooling_options
    if tooling is None:
        raise RuntimeError("Fins tooling missing")
    registry = tooling.wait_adapter_registry
    if registry is None:
        raise RuntimeError("Fins wait binding registry missing")
    for tool_name in _FINS_AWAITING_TOOL_NAMES:
        binding = registry.resolve_binding(
            tool_name=tool_name,
            await_kind=ToolAwaitKind.EXTERNAL_JOB,
        )
        if binding is None:
            raise RuntimeError(f"binding missing: {tool_name}")
        _require(
            binding.resume_policy is expected_policy,
            message=f"binding policy mismatch: {tool_name}",
        )


async def _open_non_poll_composition_cases(
    matrix: _CompositionSmokeMatrix,
) -> None:
    """通过 public Host opener 验证无 poller 与 disabled 分支均可安全打开关闭。

    :param matrix: 已验证的 packaged composition matrix。
    :returns: ``None``。
    :raises Exception: 任一 public Host open/close 失败时透出。
    """

    for assembly in (
        matrix.manual,
        matrix.no_provider,
        matrix.provider_disabled,
        matrix.runtime_disabled,
    ):
        async with open_host(assembly.options):
            pass


def _deterministic_public_poll_options(
    options: OpenHostOptions,
    *,
    worker_factory: _AwaitingThenAnswerWorkerFactory,
    poll_adapter: _GatedReadyPollAdapter,
) -> OpenHostOptions:
    """在真实 composition 结果上替换无网络 deterministic execution driver。

    :param options: packaged Service composition 产出的 public Host options。
    :param worker_factory: deterministic local worker factory。
    :param poll_adapter: deterministic not-ready/ready observation driver。
    :returns: 保留真实 binding/policy 的无网络 public Host options。
    :raises RuntimeError: packaged tooling 或 poll registry 缺失时抛出。
    """

    tooling = options.tooling_options
    if tooling is None:
        raise RuntimeError("packaged poll tooling missing")
    packaged_poll_registry = tooling.wait_poll_adapter_registry
    if packaged_poll_registry is None:
        raise RuntimeError("packaged poll registry missing")
    _require(
        packaged_poll_registry.resolve_adapter(_ADAPTER_KEY) is not None,
        message="packaged Fins poll adapter missing",
    )
    deterministic_tooling = replace(
        tooling,
        business_tool_bundle=_tool_bundle(),
        wait_activation_registry=None,
        wait_poll_adapter_registry=WaitPollAdapterRegistry(
            (
                WaitPollAdapterRegistration(
                    adapter_key=_ADAPTER_KEY,
                    adapter=poll_adapter,
                ),
            )
        ),
    )
    return replace(
        options,
        worker_factory=worker_factory,
        tooling_options=deterministic_tooling,
    )


async def _wait_for_not_ready_observation(adapter: _GatedReadyPollAdapter) -> None:
    """等待 production poller 至少完成一次 deterministic not-ready 观察。

    :param adapter: deterministic poll adapter。
    :returns: ``None``。
    :raises Exception: 不主动抛出；外层 ``wait_for`` 负责超时。
    """

    while adapter.not_ready_count == 0:
        await asyncio.sleep(0.01)


def _wait_poller_policy_summary(options: OpenHostOptions) -> str:
    """格式化不含凭证的完整 wait poller policy snapshot。

    :param options: Service composition 产出的 Host options。
    :returns: 十二字段紧凑摘要。
    :raises RuntimeError: packaged poll policy 缺失时抛出。
    """

    policy = options.wait_poller_policy
    if policy is None:
        raise RuntimeError("packaged wait poller policy missing")
    return (
        f"enabled={policy.enabled} poll={policy.poll_interval_seconds} "
        f"claim_ttl={policy.claim_ttl_seconds} claim_batch={policy.claim_batch_size} "
        f"backoff_initial={policy.backoff_initial_delay_seconds} "
        f"backoff_multiplier={policy.backoff_multiplier} "
        f"backoff_max={policy.backoff_max_delay_seconds} "
        f"not_ready={policy.not_ready_observe_interval_seconds} "
        f"idle={policy.idle_poll_interval_seconds} "
        f"adapter_timeout={policy.adapter_call_timeout_seconds} "
        f"close_drain={policy.close_drain_timeout_seconds} "
        f"max_outstanding={policy.max_outstanding_adapter_calls}"
    )


def parse_args(argv: Sequence[str]) -> SmokeArgs:
    """解析命令行参数。

    :param argv: 不含程序名的参数序列。
    :returns: 解析后的 smoke 参数。
    :raises SystemExit: argparse 在参数非法时抛出。
    """

    parser = argparse.ArgumentParser(
        description="Run Host public awaiting entrypoint smoke."
    )
    parser.add_argument(
        "--workspace-root",
        default=None,
        help=(
            "workspace / project root；默认使用 workspace/tmp 下的 fresh smoke "
            "workspace，避免历史 durable DB schema 污染。"
        ),
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="输出中标记保留 workspace；脚本不会删除 Host/runtime artifacts。",
    )
    namespace = parser.parse_args(list(argv))
    workspace_root_text: str | None = namespace.workspace_root
    keep_workspace: bool = namespace.keep_workspace
    return SmokeArgs(
        workspace_root=_resolve_workspace_root(workspace_root_text),
        keep_workspace=keep_workspace,
    )


def _resolve_workspace_root(workspace_root_text: str | None) -> Path:
    """解析 smoke workspace root。

    :param workspace_root_text: CLI 显式传入的 workspace root；为 ``None`` 时
        生成 fresh smoke workspace root。
    :returns: 归一化后的 workspace root。
    :raises Exception: 不主动抛出异常。
    """

    if workspace_root_text is not None:
        return Path(workspace_root_text).resolve()
    return (
        _DEFAULT_WORKSPACE_PARENT
        / f"{_DEFAULT_WORKSPACE_PREFIX}-{uuid4().hex[:12]}"
    ).resolve()


def _require(condition: bool, *, message: str) -> None:
    """校验 smoke 条件成立。

    :param condition: 待校验条件。
    :param message: 条件不成立时的错误消息。
    :returns: ``None``。
    :raises RuntimeError: 条件不成立时抛出。
    """

    if not condition:
        raise RuntimeError(message)


class _GatedReadyPollAdapter:
    """由测试门控控制 ready 时机的 poll adapter。"""

    not_ready_count: int
    ready_count: int
    _gate: asyncio.Event

    def __init__(self) -> None:
        """初始化 adapter 状态。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.not_ready_count = 0
        self.ready_count = 0
        self._gate = asyncio.Event()

    def open_gate(self) -> None:
        """允许下一次 poll 返回完成结果。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._gate.set()

    def poll_wait(self, snapshot: WaitAdapterSnapshot) -> WaitPollResult:
        """按测试门控返回未就绪或完成结果。

        :param snapshot: Host 传入的等待快照；本 smoke 不读取其字段。
        :returns: poll 结果。
        :raises Exception: 不主动抛出异常。
        """

        del snapshot
        if not self._gate.is_set():
            self.not_ready_count += 1
            return WaitPollNotReady()
        self.ready_count += 1
        return WaitPollReady(
            ResolveWaitCompletedOutcome(
                result=ToolResultSuccess(
                    ok=True,
                    value={"message": "ready"},
                    meta=None,
                ),
                payload_ref=None,
            )
        )

    def abandon_wait(
        self, snapshot: WaitAdapterSnapshot
    ) -> WaitExternalJobLifecycleResult:
        """返回当前 smoke 不支持外部放弃动作。

        :param snapshot: Host 传入的等待快照；本 smoke 不读取其字段。
        :returns: unsupported 结果。
        :raises Exception: 不主动抛出异常。
        """

        del snapshot
        return WaitExternalJobLifecycleUnsupported(reason="not-supported-in-smoke")


class _AwaitingThenAnswerWorkerFactory:
    """第一次运行进入等待态，恢复运行返回最终回答的 worker factory。"""

    accept_count: int

    def __init__(self) -> None:
        """初始化 factory。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self.accept_count = 0

    def create_worker(self, snapshot: AttemptDispatchSnapshot) -> LocalEngineWorker:
        """创建 deterministic worker。

        :param snapshot: 当前运行快照。
        :returns: worker。
        :raises Exception: 不主动抛出异常。
        """

        del snapshot
        return _AwaitingThenAnswerWorker(self)


class _AwaitingThenAnswerWorker:
    """按运行顺序切换脚本行为的 worker。"""

    _factory: _AwaitingThenAnswerWorkerFactory

    def __init__(self, factory: _AwaitingThenAnswerWorkerFactory) -> None:
        """初始化 worker。

        :param factory: 共享状态。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._factory = factory

    async def accept(
        self,
        snapshot: AttemptDispatchSnapshot,
        request: AgentRunRequest,
    ) -> LocalWorkerHandle:
        """接受一次运行并返回脚本 handle。

        :param snapshot: 当前运行快照。
        :param request: Engine agent 请求。
        :returns: worker handle。
        :raises Exception: 不主动抛出异常。
        """

        self._factory.accept_count += 1
        if self._factory.accept_count == 1:
            return _AwaitingHandle(request=request)
        del snapshot
        return _AnswerHandle(request=request)


class _AwaitingHandle:
    """通过 public ToolExecutor 协议产生等待结果的 worker handle。"""

    _request: AgentRunRequest

    def __init__(self, *, request: AgentRunRequest) -> None:
        """初始化 handle。

        :param request: Engine agent 请求。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._request = request

    @property
    def local_worker_id(self) -> str:
        """返回 worker id。

        :returns: worker id。
        :raises Exception: 不主动抛出异常。
        """

        return "service-awaiting-agent-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """执行 public 工具协议并返回等待事件流。

        :returns: public Engine 事件流。
        :raises Exception: 底层运行失败时透传。
        """

        iteration_id = "awaiting-smoke-iteration"
        tool_call = _awaiting_tool_call()
        batch_snapshot = AssistantToolCallBatchSnapshot(
            iteration_id=iteration_id,
            tool_calls=(tool_call,),
            content=None,
            reasoning_content=None,
            provider_request_id=None,
        )
        outcome = await self._request.tool_executor.execute(
            BatchToolExecutionRequest(
                calls=(tool_call,),
                context=BatchToolExecutionContext(
                    run_id=self._request.run_id,
                    session_id=self._request.session_id,
                    iteration_id=iteration_id,
                    timeout_seconds=(
                        self._request.agent_policy.tool_execution_timeout_seconds
                    ),
                    cancellation_token=self._request.cancellation_token,
                    correlation_id=f"{self._request.run_id}:{iteration_id}:tool_batch",
                ),
            )
        )
        if len(outcome.records) != 1:
            raise RuntimeError(f"tool execution record count mismatch: {len(outcome.records)}")
        record = outcome.records[0]
        if record.tool_call_id != tool_call.tool_call_id:
            raise RuntimeError(f"tool call id mismatch: {record.tool_call_id}")
        record_outcome = record.outcome
        if not isinstance(record_outcome, ToolAwaitingOutcome):
            raise RuntimeError(
                f"tool outcome type mismatch: {type(record_outcome).__name__}"
            )
        awaiting_record = AwaitingToolExecutionRecord(
            batch_snapshot=batch_snapshot,
            call=tool_call,
            await_spec=record_outcome.await_spec,
            snapshot=record_outcome.snapshot,
        )
        yield EngineEvent(
            occurred_at=_NOW,
            session_id=self._request.session_id,
            run_id=self._request.run_id,
            type=EngineEventType.TOOL_AWAITING,
            data=ToolAwaitingData(
                iteration_id=iteration_id,
                record=awaiting_record,
            ),
            metadata=None,
        )
        yield EngineEvent(
            occurred_at=_NOW,
            session_id=self._request.session_id,
            run_id=self._request.run_id,
            type=EngineEventType.RUN_SUSPENDED,
            data=RunSuspendedData(
                reason=RUN_SUSPENDED_REASON_TOOL_AWAITING,
                resume_hint=None,
                accepted_records=(),
                awaiting_records=(awaiting_record,),
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消通知。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        del reason


class _AnswerHandle:
    """返回最终回答的 worker handle。"""

    _request: AgentRunRequest

    def __init__(self, *, request: AgentRunRequest) -> None:
        """初始化 handle。

        :param request: Engine agent 请求。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        self._request = request

    @property
    def local_worker_id(self) -> str:
        """返回 worker id。

        :returns: worker id。
        :raises Exception: 不主动抛出异常。
        """

        return "service-awaiting-answer-worker"

    async def events(self) -> AsyncIterator[EngineEvent]:
        """返回最终回答事件流。

        :returns: public Engine 事件流。
        :raises Exception: 不主动抛出异常。
        """

        yield EngineEvent(
            occurred_at=_NOW,
            session_id=self._request.session_id,
            run_id=self._request.run_id,
            type=EngineEventType.FINAL_ANSWER,
            data=FinalAnswerData(
                content=_FINAL_ANSWER,
                filtered=False,
                degraded=False,
                finish_reason=FinishReason.STOP,
            ),
            metadata=None,
        )

    async def close(self) -> None:
        """关闭 handle。

        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        return None

    def on_cancel(self, reason: str) -> None:
        """忽略取消通知。

        :param reason: 取消原因。
        :returns: ``None``。
        :raises Exception: 不主动抛出异常。
        """

        del reason


class _AwaitingTool:
    """返回等待 outcome 的业务工具。"""

    async def __call__(
        self,
        call: ToolCallRequest,
        context: BatchToolExecutionContext,
    ) -> ToolExecutionOutcome:
        """执行等待型业务工具。

        :param call: 工具调用。
        :param context: 执行上下文。
        :returns: 等待型 outcome。
        :raises Exception: 不主动抛出异常。
        """

        del call, context
        return ToolAwaitingOutcome(
            await_spec=ToolAwaitSpec(
                await_kind=ToolAwaitKind.EXTERNAL_JOB,
                deadline=None,
                resume_token=_RESUME_TOKEN,
            ),
            snapshot=None,
        )


def _awaiting_tool_call() -> ToolCallRequest:
    """构造等待型工具调用请求。

    :returns: 工具调用请求。
    :raises Exception: 不主动抛出异常。
    """

    return ToolCallRequest(
        tool_call_id="awaiting-smoke-tool-call",
        name=_AWAITING_TOOL_NAME,
        arguments={"subject": "DAYU"},
        index_in_iteration=0,
        provider_state=None,
    )


def _tool_bundle() -> ToolBundle:
    """构造等待型业务工具 bundle。

    :returns: Tool bundle。
    :raises Exception: typed schema 字段非法时由底层抛出。
    """

    return ToolBundle(
        definitions=(
            ToolDefinition(
                name=_AWAITING_TOOL_NAME,
                schema=ToolSchema(
                    type="function",
                    function=ToolFunctionSchema(
                        name=_AWAITING_TOOL_NAME,
                        description="提交一个测试财报观察任务，返回等待态。",
                        parameters=ToolParametersSchema(
                            type="object",
                            properties={
                                "subject": {
                                    "type": "string",
                                    "description": "财报主体名称。",
                                }
                            },
                            required=("subject",),
                            additional_properties=False,
                        ),
                    ),
                ),
                callable=_AwaitingTool(),
                truncate=None,
                display=None,
                tags=(),
                execution=AsyncDirectToolExecutionCapability(),
            ),
        )
    )


def _scene_inputs() -> PreparedSceneInputs:
    """构造 Service submit 所需 scene 输入。

    :returns: scene 输入。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    return PreparedSceneInputs(
        system_messages=("你是财报分析助手。",),
        system_prompt="你是财报分析助手。",
        tool_selection=SceneToolSelectionResult(
            mode=SceneToolSelectionMode.SELECT,
            tool_names=frozenset({_AWAITING_TOOL_NAME}),
        ),
        model_hints=None,
        agent_policy_override=None,
        fragment_refs=(),
        source_refs=(
            SceneSourceRef(
                source_kind=SceneSourceKind.ASSEMBLY_INPUT,
                source_id="service-awaiting-smoke",
                version_ref=None,
                content_digest="sha256:" + "0" * 64,
            ),
        ),
        content_digest="sha256:" + "1" * 64,
        capability_tags=(),
    )


def _turn_request(*, session_id: str) -> EntrypointTurnRequest:
    """构造 entrypoint turn 请求。

    :param session_id: Host session id。
    :returns: turn 请求。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    return EntrypointTurnRequest(
        context=_host_context("awaiting-smoke-submit"),
        session_id=session_id,
        client_request_id="awaiting-smoke-submit",
        user_prompt="请观察测试财报任务。",
        tool_names=frozenset({_AWAITING_TOOL_NAME}),
        behavior=FollowupBehavior.QUEUE,
        target_run_id=None,
        run_overrides=ServiceRunOverrides(),
    )


def _host_context(request_id: str) -> HostCallContext:
    """构造 Host 调用上下文。

    :param request_id: 请求 id。
    :returns: Host call context。
    :raises Exception: typed 字段非法时由底层抛出。
    """

    return HostCallContext(
        actor="analyst",
        source="utils.smoke_host_public_awaiting_entrypoint",
        request_id=request_id,
        authorization_claims=(AuthorizationClaim(name="role", value="tester"),),
        operation_context=OperationContext(
            operation_name="service_entrypoint_awaiting_smoke",
            operation_kind="manual_smoke",
            business_domain="service",
            business_object_type=None,
            business_object_id=None,
            scenario="wu_wait_04_s2",
            correlation_id=None,
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """脚本入口。

    :param argv: 命令行参数；为 ``None`` 时读取 ``sys.argv[1:]``。
    :returns: 进程退出码。
    :raises Exception: 不主动抛出；异常会被转换为退出码 1。
    """

    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return asyncio.run(run_smoke(args, os.environ))
    except Exception as exc:
        print(f"SMOKE FAIL {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
